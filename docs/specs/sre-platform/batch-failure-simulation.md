# Simulation Spec: Batch Failure & Self-Healing Recovery

## Overview

Validates the SRE Platform's ability to detect a partial batch API failure and self-heal by reprocessing pending records. This is the first simulation that exercises the **reprocess** recovery model end-to-end, using the platform's checkpoint framework.

### The Story

A Batch Insert API accepts 10 transaction records and writes them to DynamoDB. Mid-batch, the API times out after inserting 5 of 10 records — leaving a partially completed batch with no response to the caller. The SRE Platform detects the failure, classifies it as a batch timeout, auto-resolves the incident, and triggers checkpoint-aware recovery. The recovery engine scans the checkpoint table for incomplete work, computes the delta, and invokes the application's recovery handler with only the pending items. The recovery handler writes the missing records directly to DynamoDB and marks the checkpoint complete.

### Failure Cases Addressed

| Case | What Happens | How Recovery Handles It |
|---|---|---|
| Lambda timeout (killed) | 5/10 written, no response, logs may not flush | Checkpoint has 5 completed_items → get_pending() returns 5 |
| API Gateway timeout (Lambda continues) | All 10 written, but caller got 504 | Checkpoint has 10 completed_items → get_pending() returns 0 (no-op) |
| Application error mid-batch | 5/10 written, exception raised | Same as Lambda timeout — checkpoint + delta |
| Recovery also fails | Recovery writes 3/5 pending, then fails | Re-run recovery — checkpoint recalculates delta, writes remaining 2 |
| Multiple concurrent batches | Batch b-001 and b-002 both fail | Each has its own checkpoint — recovery engine processes all `in_progress` checkpoints |
| Duplicate recovery trigger | Step Function triggered twice | Idempotent — second run finds nothing pending |

### What This Proves

| Capability | How It's Verified |
|---|---|
| Partial batch detection | Real API call inserts 5/10 records, then times out |
| Platform checkpoint persistence | Checkpoint record survives Lambda timeout |
| Correct severity/recovery mapping | `batch-failure` alarm → SEV-1, recovery_model=`reprocess` |
| AI/rule classification | Root cause classified as `batch-timeout` (not `bad-deployment`) |
| Recovery-only triage path | Auto-resolve without remediation attempt |
| Checkpoint-aware recovery engine | Platform scans sre-checkpoints, computes delta, builds enriched payload |
| Recovery handler contract | Handler receives `{checkpoint_id, pending_items, metadata}`, writes items, completes checkpoint |
| Data integrity | All 10 records exist in DynamoDB after recovery |
| Idempotent recovery | Re-running recovery on a completed checkpoint is a no-op |
| Jira lifecycle | Open → Investigating → Resolved with recovery summary |

---

## 1. The Batch Insert API

### 1a. Architecture

```
POST /batch/insert
     │
     ▼
API Gateway  ──►  batch-processor-api-{stage} Lambda
                         │
                         ├── 1. Platform checkpoint: write_checkpoint()
                         ├── 2. Write TXN records (one per item)
                         │      └── After each: checkpoint.mark_progress(txn_id)
                         ├── 3. On success: checkpoint.complete()
                         └── 4. On timeout/error: checkpoint stays in_progress
                                (5 items in completed_items, 5 pending)
```

### 1b. API Contract

**Endpoint**: `POST /batch/insert`

**Request**:
```json
{
  "batch_id": "b-001",
  "txn_ids": ["txn-1", "txn-2", ..., "txn-10"],
  "force_partial_failure": false
}
```

**Success Response** (200):
```json
{
  "status": "completed",
  "batch_id": "b-001",
  "total_processed": 10
}
```

**Partial Failure** (no response — Lambda killed by timeout or 500 with error body):
```json
{
  "status": "partial_failure",
  "batch_id": "b-001",
  "processed_count": 5,
  "error": "BatchTimeoutError: Processing timed out after 5/10 records"
}
```

### 1c. DynamoDB Table Design

**Table**: `batch-transactions-{stage}`

| PK (`txn_id`) | `batch_id` | `status` | `data` | `timestamp` | `ttl` |
|---|---|---|---|---|---|
| `TXN#txn-1` | `b-001` | `processed` | `{"amount": 100}` | ISO 8601 | 24h |
| `TXN#txn-2` | `b-001` | `processed` | `{"amount": 200}` | ISO 8601 | 24h |
| ... | | | | | |
| `TXN#txn-5` | `b-001` | `processed` | `{"amount": 500}` | ISO 8601 | 24h |

**After timeout**: Only 5 `TXN#` records exist. The checkpoint table (not this table) tracks what was intended vs completed.

**GSI**: `batch_id-index` (partition: `batch_id`, sort: `txn_id`) — enables querying all records for a specific batch.

**TTL**: 24h on all records — simulation data auto-expires.

### 1d. Checkpoint Integration

The Batch API uses the platform's checkpoint client to record progress:

```
Checkpoint table: sre-checkpoints-{stage}

checkpoint_id:    batch:batch-processor-api-dev:b-001
service:          batch-processor-api-dev
operation:        batch-insert
status:           in_progress
total_items:      10
completed_items:  [txn-1, txn-2, txn-3, txn-4, txn-5]   ← 5 after timeout
metadata:         {"target_table": "batch-transactions-dev"}
```

This separates the checkpoint (platform-owned) from the application data (batch-transactions table).

### 1e. Handler Logic (`batch_processor_handler.py`)

```
@api_gateway_handler
def lambda_handler(event, context):
    request = parse_batch_request(event)

    # Step 1: Write platform checkpoint FIRST
    checkpoint_id = f"batch:{function_name}:{request.batch_id}"
    checkpoint.write_checkpoint(
        checkpoint_id=checkpoint_id,
        service=function_name,
        operation="batch-insert",
        item_ids=request.txn_ids,
        metadata={"target_table": f"batch-transactions-{stage}"},
    )

    # Step 2: Process items one by one
    processed = 0
    for txn_id in request.txn_ids:
        if request.force_partial_failure and processed == 5:
            raise BatchTimeoutError(f"Processing timed out after {processed}/{len(request.txn_ids)} records")

        write_transaction(txn_id, request.batch_id)
        checkpoint.mark_progress(checkpoint_id, txn_id)  # atomic append
        processed += 1

    # Step 3: Mark checkpoint complete (only reached if no error)
    checkpoint.complete(checkpoint_id)

    return {"status": "completed", "batch_id": request.batch_id, "total_processed": processed}
```

**Critical design point**: The checkpoint is written **before** any item processing. If Lambda is killed at any point after step 1, the checkpoint exists and the platform's recovery engine can discover it.

---

## 2. The Recovery Workflow

### 2a. Platform Recovery Engine (Checkpoint-Aware)

When `ResolutionService.trigger_recovery("reprocess")` fires, the platform's recovery engine:

1. Looks up the recovery catalog → finds `checkpoint_aware: true`
2. Scans `sre-checkpoints-{stage}` for `service=batch-processor-api-{stage}` + `status=in_progress`
3. For each incomplete checkpoint, calls `get_pending()` to compute the delta
4. Builds an enriched recovery payload with pending items
5. Starts the Step Function with the enriched payload
6. Step Function invokes the application's recovery handler

```
ResolutionService.trigger_recovery("reprocess")
         │
         ▼
Recovery Engine (platform)
  ├── Scan sre-checkpoints-{stage}: service + status=in_progress
  ├── get_pending("batch:batch-processor-api-dev:b-001")
  │     → ["txn-6", "txn-7", "txn-8", "txn-9", "txn-10"]
  ├── Build enriched payload with pending_items + metadata
  └── Start Step Function → batch-reprocess-{stage}
                │
                ▼
         batch-recovery-{stage} Lambda (application handler)
           ├── Receives: {checkpoint_id, pending_items, metadata}
           ├── Writes TXN#txn-6..TXN#txn-10 to batch-transactions-dev
           ├── Calls checkpoint.complete(checkpoint_id)
           └── Returns {status, processed_count, details}
```

### 2b. Why Recovery Is a Separate Lambda

The recovery handler is **NOT** the Batch API. It is a dedicated function because:

| Concern | Batch API | Recovery Handler |
|---|---|---|
| Trigger | API Gateway (user request) | Step Function (platform recovery engine) |
| Input | `{batch_id, txn_ids}` | `{checkpoint_id, pending_items, metadata}` |
| Writes | Creates items + writes checkpoint | Writes only missing items |
| Side effects | May trigger notifications | Must NOT re-trigger notifications |
| Error handling | Returns 500 to caller | Reports to Jira via platform |
| Timeout risk | Subject to API Gateway 29s limit | Lambda-only, can run up to 15 min |

### 2c. Recovery Handler Logic (`batch_recovery_handler.py`)

Conforms to the platform's recovery handler contract:

```
def lambda_handler(event, context):
    checkpoint_id = event["checkpoint_id"]
    pending_items = event["pending_items"]
    metadata = event["metadata"]
    target_table = metadata["target_table"]

    # Write ONLY pending items (direct DynamoDB, not via API)
    for txn_id in pending_items:
        write_transaction(txn_id, batch_id, table=target_table)

    # Mark checkpoint complete via platform API
    checkpoint.complete(checkpoint_id)

    return {
        "status": "success",
        "processed_count": len(pending_items),
        "failed_count": 0,
        "details": f"Reprocessed {len(pending_items)} items"
    }
```

**Key properties**:
- **Idempotent**: Running twice is safe (DynamoDB PutItem is idempotent, second complete() is a no-op)
- **Focused**: Receives exactly what to write — no discovery logic needed
- **No side effects**: Writes directly to DynamoDB, doesn't go through API

### 2d. Step Function (`batch-reprocess-{stage}`)

Single-step state machine:

```json
{
  "StartAt": "RecoverPendingBatches",
  "States": {
    "RecoverPendingBatches": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:...:batch-recovery-{stage}",
      "End": true
    }
  }
}
```

**Input** (enriched by platform recovery engine):
```json
{
  "incident_key": "sim-batch-batch-failure-dev",
  "jira_ticket_id": "ASD-XX",
  "severity": "SEV-1",
  "recovery_model": "reprocess",
  "execution_id": "uuid",
  "checkpoints": [
    {
      "checkpoint_id": "batch:batch-processor-api-dev:b-001",
      "service": "batch-processor-api-dev",
      "operation": "batch-insert",
      "pending_items": ["txn-6", "txn-7", "txn-8", "txn-9", "txn-10"],
      "total_items": 10,
      "completed_count": 5,
      "metadata": {"target_table": "batch-transactions-dev"}
    }
  ]
}
```

### 2e. How It Connects to the Existing Pipeline

```
Batch API timeout
       │
       ▼
CloudWatch Alarm fires ──► SNS ──► Detection Lambda
                                         │
                                   Creates Jira ticket (JSM "Report a system problem")
                                   DynamoDB: RESERVED → DETECTED
                                   Publishes IncidentCreated → EventBridge
                                         │
                                         ▼
                                   Triage Lambda
                                         │
                                   ├── Classifies: "batch-timeout" (high confidence)
                                   ├── Recovery-only path (skip remediation)
                                   ├── Auto-resolve: DETECTED → GRACE
                                   ├── Resolve Jira ticket
                                   └── trigger_recovery("reprocess")
                                              │
                                              ▼
                                   ResolutionService.trigger_recovery()
                                   Recovery catalog: reprocess → checkpoint_aware=true
                                              │
                                              ▼
                                   Recovery Engine (platform)
                                   ├── Scan sre-checkpoints-dev: in_progress
                                   ├── get_pending() → compute delta
                                   ├── Build enriched payload
                                   └── Start Step Function
                                              │
                                              ▼
                                   batch-recovery-dev Lambda (app handler)
                                   ├── Receives {pending_items, metadata}
                                   ├── Writes pending TXN records to DynamoDB
                                   ├── checkpoint.complete()
                                   └── Returns summary
                                              │
                                              ▼
                                   Platform reports recovery to Jira
                                   "Recovery complete: reprocessed 5 items in batch b-001"
```

---

## 3. Configuration Changes

### 3a. Classification Rule

Add to `incident_config.json` → `classification_rules`:

```json
{"pattern": "batch_timeout", "classification": "batch-timeout", "confidence": "high"}
```

Add to `TriageService._matches_pattern()`:

```python
if pattern_name == "batch_timeout":
    return any(
        kw in all_messages
        for kw in ["batch processing timed out", "transactions pending", "batchtimeouterror"]
    )
```

### 3b. Recovery Catalog (Enhanced)

```json
"reprocess": {
  "type": "step_function",
  "workflow_arn_env": "REPROCESS_BATCH_WORKFLOW_ARN",
  "recovery_handler_env": "BATCH_RECOVERY_FUNCTION_NAME",
  "checkpoint_aware": true,
  "max_retries": 3,
  "description": "Reprocess pending batch items using checkpoint data"
}
```

### 3c. Recovery-Only Path in Triage

New concept: root causes that need **recovery but not remediation**. After classification, check:

```python
RECOVERY_ONLY_ROOT_CAUSES = {"batch-timeout"}

if root_cause in RECOVERY_ONLY_ROOT_CAUSES and confidence == "high":
    # Skip remediation → verification → escalation cycle
    # Go straight to resolve + recovery
```

---

## 4. Infrastructure (CDK)

### New Resources

| Resource | Name | Purpose |
|---|---|---|
| DynamoDB Table | `batch-transactions-{stage}` | Application data (TXN records) |
| Lambda | `batch-processor-api-{stage}` | Batch Insert API handler |
| API Gateway Route | `POST /batch/insert` | API endpoint |
| Lambda | `batch-recovery-{stage}` | Recovery handler — writes pending items |
| Step Function | `batch-reprocess-{stage}` | Recovery workflow |
| Env var (Triage Lambda) | `REPROCESS_BATCH_WORKFLOW_ARN` | Points to Step Function |

**Platform resources** (from checkpoint-recovery-framework.md):

| Resource | Name | Purpose |
|---|---|---|
| DynamoDB Table | `sre-checkpoints-{stage}` | Shared checkpoint storage |

### IAM Permissions

| Principal | Access |
|---|---|
| `batch-processor-api-{stage}` | DynamoDB `batch-transactions-{stage}` (PutItem, UpdateItem) |
| `batch-processor-api-{stage}` | DynamoDB `sre-checkpoints-{stage}` (PutItem, UpdateItem) |
| `batch-recovery-{stage}` | DynamoDB `batch-transactions-{stage}` (PutItem) |
| `batch-recovery-{stage}` | DynamoDB `sre-checkpoints-{stage}` (UpdateItem) |
| `batch-reprocess-{stage}` SFN | Lambda:InvokeFunction (`batch-recovery-{stage}`) |
| Triage Lambda | DynamoDB `sre-checkpoints-{stage}` (Query, Scan) |
| Triage Lambda | StepFunctions:StartExecution (`batch-reprocess-{stage}`) |

---

## 5. Simulation Flow (14 Steps)

```
Step  Action                                             Validates
────  ─────────────────────────────────────────────────  ──────────────────────────
 1    Invoke Batch API: 10 txns with chaos flag          Partial failure, 5/10 written
 2    Verify: checkpoint=in_progress, 5 TXN records      Platform checkpoint survived timeout
 3    Pre-clean stale incident records and alarms         Clean state
 4    Wait 90s for CW Logs Insights indexing              Log queryability
 5    Create alarm sim-batch-high-batch-failure-dev       Alarm naming convention
 6    Publish ALARM to SNS with FunctionName dimension    Detection trigger
 7    Wait for Detection (cool-off + Jira creation)       Pipeline initiation
 8    Verify DynamoDB incident record (DETECTED, ticket)  Correlation store
 9    Wait for Triage → Recovery pipeline                  Processing time
10    Check Triage logs: batch-timeout classification      AI/rule classification
11    Check Triage logs: recovery trigger                   Step Function fired
12    Verify Step Function execution (SUCCEEDED)           Recovery ran
13    Verify: checkpoint=completed, ALL 10 TXN records    Data integrity proof
14    Cleanup                                              Clean teardown
```

### Key Verification Points

**Step 2** — Proves the checkpoint mechanism works:
```bash
# Check platform checkpoint
aws dynamodb get-item --table-name sre-checkpoints-dev \
  --key '{"checkpoint_id": {"S": "batch:batch-processor-api-dev:b-001"}}'
# Expected: status=in_progress, total_items=10, completed_items has 5 entries

# Count application records
aws dynamodb query --table-name batch-transactions-dev \
  --index-name batch_id-index \
  --key-condition-expression "batch_id = :b" \
  --expression-attribute-values '{":b": {"S": "b-001"}}' \
  --select COUNT
# Expected: 5 TXN records
```

**Step 13** — Proves recovery completed the batch:
```bash
# Checkpoint should be completed
aws dynamodb get-item --table-name sre-checkpoints-dev \
  --key '{"checkpoint_id": {"S": "batch:batch-processor-api-dev:b-001"}}'
# Expected: status=completed

# All application records should exist
aws dynamodb query --table-name batch-transactions-dev \
  --index-name batch_id-index \
  --key-condition-expression "batch_id = :b" \
  --expression-attribute-values '{":b": {"S": "b-001"}}' \
  --select COUNT
# Expected: 10 TXN records
```

---

## 6. Files

### New Files

| File | Purpose |
|---|---|
| `src/checkpoint/client.py` | Platform checkpoint API client (shared) |
| `src/handlers/batch_processor_handler.py` | Batch Insert API (writes TXN records + checkpoint) |
| `src/handlers/batch_recovery_handler.py` | Recovery handler (receives pending_items, writes to app table) |
| `src/dto/batch_request.py` | Pydantic models for batch API request/response |
| `src/repositories/batch_repository.py` | DynamoDB operations for batch-transactions table |
| `scenarios/batch_failure_recovery.py` | 14-step simulation with real API + DynamoDB verification |
| `docs/runbooks/batch-recovery.md` | Operational runbook for batch recovery |

### Modified Files

| File | Change |
|---|---|
| `incident_config.json` | Add `batch-timeout` classification rule, enhanced recovery catalog |
| `src/services/triage_service.py` | Add `batch_timeout` pattern + recovery-only path |
| `src/services/resolution_service.py` | Enhanced with checkpoint-aware recovery payload |
| `infra/stacks/incident_manager_stack.py` | Add DynamoDB tables, 2 Lambdas, Step Function, API GW route |

### Deleted Files

| File | Reason |
|---|---|
| `simulations/mocks/batch_processor.py` | Replaced by real Lambda handler |
| `simulations/mocks/batch_recovery.py` | Replaced by real Lambda handler |

---

## 7. Verification Plan

### Automated (Simulation Run)

```bash
python3 scripts/incident/simulations/run.py --scenario 8
```

**Success Criteria**:
- [ ] 14/14 steps pass
- [ ] Platform checkpoint written before item processing
- [ ] 5/10 items in DynamoDB after failure, checkpoint status=`in_progress` with 5 completed_items
- [ ] Jira ticket: SEV-1, "Report a system problem"
- [ ] Root cause: `batch-timeout` (not `bad-deployment`)
- [ ] Ticket status: Open → Investigating → Resolved
- [ ] Recovery engine scanned sre-checkpoints-dev, computed delta of 5 items
- [ ] Step Function `batch-reprocess-dev` execution SUCCEEDED
- [ ] **All 10 items in DynamoDB after recovery, checkpoint status=`completed`**
- [ ] Jira recovery comment with reprocessed count
- [ ] Error log file attached

### Idempotency Test

Run recovery Step Function manually a second time:
```bash
aws stepfunctions start-execution \
  --state-machine-arn $REPROCESS_BATCH_WORKFLOW_ARN \
  --input '{"incident_key":"test","recovery_model":"reprocess"}'
```
Expected: SUCCEEDED with `batches_recovered: 0` (nothing pending — checkpoint already completed).

### Manual (DynamoDB Verification)

See runbook: `docs/runbooks/batch-recovery.md`
