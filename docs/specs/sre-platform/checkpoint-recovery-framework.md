# SRE Platform — Checkpoint & Clarity Framework (v1)

## Objective: "The Truth in Real-Time"

v1 pivots from active recovery to **passive observability**. The goal is to provide immediate, structured clarity when a batch process fails or hangs — eliminating the detective work usually required to find the delta.

**v1 Mantra: Stop the "War Room." Answer the "What" and "Why" automatically.**

```
Batch API fails mid-processing
       │
       ▼
SRE Platform detects failure
       │
       ├── Scans checkpoint table → computes delta
       └── Posts Delta Report to Jira:

             🔍 SRE Platform: Batch Delta Report
             Status: 🔴 FAILED (Lambda Timeout)
             Service: batch-processor-api-dev

             Total: 10 | Succeeded: 5 | Pending: 5
             Top Error: ReadTimeout: downstream API unresponsive
             Pending IDs: txn-6, txn-7, txn-8, txn-9, txn-10

             Note: Auto-recovery is disabled. Manual intervention required.
```

An engineer opens the Jira ticket and sees exactly what broke — no log queries, no DynamoDB scans, no guessing.

### What v1 Does NOT Do

- **The "Big Red Button"**: No UI or API to trigger a retry
- **Recovery Handlers**: Applications do not need to build specialized recovery logic
- **Auto-Recovery**: No Step Function triggers or automated remediation
- **Parallel Fan-out**: No complex chunking or Map-state orchestration

These are documented in `checkpoint-recovery-v2-roadmap.md` with explicit triggers for when to build each.

**Implementation Plan**: `checkpoint-clarity-implementation-plan.md` — 7 tasks across 3 MVPs, one-week scope.

---

## 1. The Problem

When an API or batch process fails mid-execution, every team asks the same three questions:

1. **What was intended?** (the full scope of work)
2. **What completed?** (progress before failure)
3. **What is pending?** (the delta to recover)

Today, answering these requires log diving, DynamoDB scans, and tribal knowledge. Each application builds its own ad-hoc checkpoint logic. This doesn't scale.

### Responsibility Split

```
┌─────────────────────────────────────┬──────────────────────────────────────┐
│  SRE Platform (generic)             │  Application (specific)              │
├─────────────────────────────────────┼──────────────────────────────────────┤
│  Checkpoint table (DynamoDB)        │  Calls checkpoint SDK during work    │
│  S3 bucket for large manifests      │  Reports progress + errors           │
│  Delta Report Service               │  Knows its own item IDs              │
│  Zombie detection                   │  Uses heartbeat() in long loops      │
│  Jira integration                   │                                      │
│  CloudWatch metrics + alarms        │                                      │
└─────────────────────────────────────┴──────────────────────────────────────┘
```

The platform captures state. The application reports state. Humans decide what to do.

---

## 2. The Checkpoint Table (The Witness)

A centralized DynamoDB table that acts as the single source of truth for in-flight work.

**Table**: `sre-checkpoints-{stage}`

| Attribute | Type | Description |
|---|---|---|
| `checkpoint_id` (PK) | String | Unique ID, e.g., `batch:batch-processor-api-dev:b-001` |
| `service` | String | Source service name, e.g., `batch-processor-api-dev` |
| `operation` | String | Operation type, e.g., `batch-insert` |
| `checkpoint_mode` | String | `item_tracking` or `index_based` |
| `status` | String | `in_progress`, `completed`, `failed` |
| `total_items` | Number | Total items in the work scope |
| `all_item_ids` | StringSet (SS) / String | Full intended item IDs. S3 URI if > 500 items. Only for `item_tracking` mode |
| `completed_items` | StringSet (SS) | Item IDs processed. DynamoDB String Set for atomic `ADD`. Only for `item_tracking` mode |
| `completed_index` | Number | Last successfully processed index (0-based). Only for `index_based` mode |
| `last_error` | String | Specific exception string from the first or most recent failure |
| `error_counts` | Map | Error message → count, e.g., `{"ReadTimeout: ...": 52, "ValidationError: ...": 3}` |
| `first_failed_id` | String | The first item ID that encountered an error |
| `timeout_seconds` | Number | Max expected duration before zombie alert |
| `last_heartbeat` | String | ISO 8601 — updated periodically by the running application |
| `created_at` | String | ISO 8601 |
| `updated_at` | String | ISO 8601 |
| `ttl` | Number | Epoch seconds, configurable per checkpoint (default: 24h) |
| `metadata` | Map | Application-specific context (e.g., `{"target_table": "batch-transactions-dev"}`) |

**GSI**: `service-status-index` (partition: `service`, sort: `status`) — targeted query, not scan.

**S3 Bucket**: `sre-checkpoint-manifests-{stage}` — for item lists exceeding 500 items (DynamoDB 400KB limit).

### Why StringSet (SS), Not List (L)

`completed_items` uses DynamoDB StringSet because `ADD` works atomically on Sets. `ADD` does NOT work on Lists (L type) — using a List would cause `ValidationException` in production. StringSet also provides built-in deduplication.

---

## 3. Two Checkpoint Modes

### Item Tracking (Default for v1)

For unordered workloads where items can be processed in any order.

```python
checkpoint.write_checkpoint(
    checkpoint_id="batch:api:b-001",
    service="batch-processor-api-dev",
    operation="batch-insert",
    item_ids=["txn-1", "txn-2", ..., "txn-10"],
    mode="item_tracking",
)
```

Stores `all_item_ids` + `completed_items`. Delta = `all_item_ids - completed_items`.

**Use when**: Batch API inserts, event fan-out, any unordered set of discrete items.

### Index-Based (Ordered Workloads)

For workloads processed sequentially where recovery can resume from a position.

```python
checkpoint.write_checkpoint(
    checkpoint_id="import:pipeline:csv-2024-04-02",
    service="data-import-pipeline-dev",
    operation="csv-import",
    total_items=50000,
    mode="index_based",
)
```

Stores `total_items` + `completed_index` (single number). Pending = items from `completed_index + 1` onward.

**DynamoDB cost**: 1 write per flush vs N writes. No item size concerns.

**Use when**: CSV imports, stream replay, ordered batch jobs, migrations.

### Mode Selection (80/20 Rule)

| Mode | Tracking Style | Best Use Case |
|---|---|---|
| Item Tracking | Tracks every ID in a Set | Unordered batches (APIs, fan-outs). **Default for v1.** |
| Index-Based | Tracks a single "Last Row" number | Ordered sequences (CSV imports, stream replays) |

---

## 4. The Minimalist SDK (Reporting In)

The SDK is a "fire and forget" wrapper for application teams. It requires zero infrastructure changes — only a few lines of code to report progress.

```python
# Installed via shared Lambda Layer (backend/lambda-layer/python/sre_platform/checkpoint/)
from sre_platform.checkpoint import CheckpointClient

checkpoint = CheckpointClient(
    table_name="sre-checkpoints-dev",
    bucket_name="sre-checkpoint-manifests-dev",
)
```

### `write_checkpoint(checkpoint_id, service, operation, ...)`

Called **before** processing begins. Declares the full scope of work.

```python
checkpoint.write_checkpoint(
    checkpoint_id=f"batch:{function_name}:{batch_id}",
    service=function_name,
    operation="batch-insert",
    item_ids=["txn-1", ..., "txn-10"],
    mode="item_tracking",
    metadata={"target_table": "batch-transactions-dev"},
    timeout_seconds=900,
    ttl_hours=24,
)
```

If `len(item_ids) > 500`: uploads list to S3, stores URI in `all_item_ids`.

### `mark_progress(checkpoint_id, item_id=None, index=None)`

Called after each item is successfully processed.

**Item tracking**: `ADD completed_items :item` — DynamoDB String Set, atomic and idempotent.

**Index-based**: `SET completed_index = :idx` — simple overwrite.

### `mark_progress_buffered(checkpoint_id, ..., flush_every=100, flush_interval_seconds=5)`

Hybrid flush: buffers in memory, flushes when **either** buffer count OR time interval is reached.

```python
for txn_id in txn_ids:
    write_to_dynamo(txn_id, ...)
    checkpoint.mark_progress_buffered(checkpoint_id, item_id=txn_id,
                                      flush_every=100, flush_interval_seconds=5)

checkpoint.flush_progress(checkpoint_id)  # MUST call at end
```

**Trade-off**: Up to `flush_every - 1` items may appear as "pending" on crash even if processed. Application writes must be idempotent.

| Batch Size | flush_every | DynamoDB Writes | Max Ghost Pending |
|---|---|---|---|
| < 100 | 1 (use `mark_progress`) | N | 0 |
| 100–1,000 | 50 | N/50 | 49 |
| 1,000–10,000 | 100 | N/100 | 99 |
| > 10,000 | 200 | N/200 | 199 |

### `flush_progress(checkpoint_id)`

Flushes buffer to DynamoDB. Also updates `last_heartbeat` (implicit heartbeat).

### `log_failure(checkpoint_id, item_id, error_message)`

**(Optional)** Reports the "Why" for a specific item. Updates `last_error`, increments `error_counts[error_message]`, and sets `first_failed_id` if not already set.

```python
try:
    call_downstream(item)
    checkpoint.mark_progress(checkpoint_id, item_id=item.id)
except ReadTimeout as e:
    checkpoint.log_failure(checkpoint_id, item_id=item.id, error_message=str(e))
    raise  # or continue processing remaining items
```

### `heartbeat(checkpoint_id)`

Updates `last_heartbeat` only. Use between slow operations where flush isn't frequent enough.

### `complete(checkpoint_id)`

Flushes remaining buffer, updates status to `completed`.

### `get_pending(checkpoint_id) → list[str] | int`

- **Item tracking**: Returns `all_item_ids - completed_items`
- **Index-based**: Returns `completed_index + 1` (resume point)

Used internally by the Delta Report Service. Available to applications for their own diagnostics.

### Integration Example

```python
# In your batch handler — 5 lines of checkpoint code
checkpoint.write_checkpoint(
    checkpoint_id=f"batch:{FUNCTION_NAME}:{batch_id}",
    service=FUNCTION_NAME, operation="batch-insert",
    item_ids=txn_ids, mode="item_tracking",
    metadata={"target_table": TABLE_NAME}, timeout_seconds=300,
)

for txn_id in txn_ids:
    try:
        write_to_dynamo(txn_id, ...)
        checkpoint.mark_progress(checkpoint_id, item_id=txn_id)
    except Exception as e:
        checkpoint.log_failure(checkpoint_id, item_id=txn_id, error_message=str(e))
        raise

checkpoint.complete(checkpoint_id)
```

30 minutes of dev work. Zero infrastructure changes.

---

## 5. S3 Side-Loading (Large Manifests)

**DynamoDB item size limit**: 400KB. 5,000 UUIDs ~ 180KB.

**Rule**: `len(item_ids) > 500` → upload to S3, store URI in `all_item_ids`.

```
all_item_ids: "s3://sre-checkpoint-manifests-dev/batch:api:b-001/items.json"
```

**completed_items growth**: For >5,000 items, `flush_progress()` offloads completed set to S3 and resets DynamoDB set.

```
get_pending() merges: all_item_ids(S3) - (completed in S3 + completed in DynamoDB)
```

---

## 6. The Delta Report Service (The Value)

This is the primary deliverable for v1. An automated service that monitors the checkpoint table and posts structured Delta Reports to Jira.

### How It Works

```
Incident detected (Lambda error / CloudWatch alarm)
       │
       ├── Step 1: Query GSI: service + status = "in_progress"
       │            (targeted query, NOT a full table scan)
       │
       ├── Step 2: For each incomplete checkpoint:
       │            a. Check zombie (2x heartbeat threshold)
       │            b. Compute pending = get_pending(checkpoint_id)
       │            c. Summarize error patterns from error_counts
       │
       ├── Step 3: Build Delta Report
       │
       └── Step 4: Post to Jira ticket as structured comment
```

### Small Batch (< 50 pending — list IDs)

```
🔍 SRE Platform: Batch Delta Report

Status:    🔴 FAILED (Lambda Timeout)
Service:   batch-processor-api-dev
Operation: batch-insert
Checkpoint: batch:batch-processor-api-dev:b-001

Progress Summary:
  Total Items:  10
  Succeeded:    5
  Pending:      5

Failure Context:
  Top Error:       ReadTimeout: downstream API unresponsive (4 occurrences)
  First Failed ID: txn-6
  Zombie Status:   False (Process crashed, did not hang)

Pending IDs:
  txn-6, txn-7, txn-8, txn-9, txn-10

Target: batch-transactions-dev

Note: Auto-recovery is disabled for this service. Manual intervention
      required for the 5 pending items.
```

### Large Batch (> 50 pending — summarize)

```
🔍 SRE Platform: Batch Delta Report

Status:    🔴 FAILED (Lambda Timeout)
Service:   policy-migration-api-dev
Operation: policy-import

Progress Summary:
  Total Items:  1,000
  Succeeded:    940
  Pending:      60

Failure Context:
  Top Error:       ReadTimeout: Duck Creek API unresponsive (52 occurrences)
  Other Errors:    ValidationError: missing field 'coverage_type' (8 occurrences)
  First Failed ID: POL-776
  Zombie Status:   False (Process crashed, did not hang)

Manifest Link: [S3 — 60 pending item IDs]

Note: Auto-recovery is disabled for this service. Manual intervention
      required for the 60 pending items.
```

### Multiple Checkpoints

```
🔍 SRE Platform: Batch Delta Report — 3 incomplete batches

  b-001: 50% complete (5/10 pending)
         Top Error: ReadTimeout (4 occurrences)
  b-002: 70% complete (3/10 pending)
         Top Error: ThrottlingException (3 occurrences)
  b-003: 0% complete (10/10 pending — no items processed)
         Zombie: 🟡 YES (no heartbeat for 180s)

Total pending: 18 items across 3 batches

Note: Auto-recovery is disabled. Manual intervention required.
```

### Zombie Detection

A checkpoint is "zombie" if the application hangs without crashing:

```python
def is_zombie(checkpoint):
    if checkpoint.status != "in_progress":
        return False
    heartbeat_age = now - checkpoint.last_heartbeat
    return heartbeat_age > (checkpoint.timeout_seconds * 2)  # 2x threshold
```

**2x threshold**: Avoids false zombies from Lambda freeze, network blips, GC pauses. With `timeout_seconds=30`, a zombie is detected at 60 seconds — flagged within the next scan cycle.

**On detection**: Status → `failed`, CloudWatch metric emitted, Jira comment posted with zombie flag.

---

## 7. Safety Mechanisms

### 7a. IAM Security (Per-Service Isolation)

Each service can only write checkpoints for itself:

```python
checkpoint_table.grant(
    batch_processor_lambda,
    actions=["dynamodb:PutItem", "dynamodb:UpdateItem"],
    conditions={"ForAllValues:StringEquals": {
        "dynamodb:LeadingKeys": ["batch:batch-processor-api-*"]
    }}
)
```

| Principal | Checkpoint Table | Manifest S3 Bucket |
|---|---|---|
| Application Lambda | PutItem, UpdateItem (own prefix only) | PutObject (own prefix) |
| Delta Report Service | Query, GetItem (read-only, any) | GetObject (any) |

### 7b. TTL Configuration

Configurable per checkpoint:

```python
checkpoint.write_checkpoint(..., ttl_hours=168)  # 7 days for migrations
```

| Workload | Recommended TTL |
|---|---|
| API batch processing | 24 hours |
| CSV import | 48 hours |
| Migration script | 7 days |

Default: `max(24h, timeout_seconds * 4)` — prevents TTL from expiring before the Delta Report Service scans.

---

## 8. Observability

### CloudWatch Metrics

| Metric | Description |
|---|---|
| `sre.checkpoint.created` | write_checkpoint() called |
| `sre.checkpoint.completed` | Normal completion |
| `sre.checkpoint.items_pending` | Pending count at Delta Report time |
| `sre.checkpoint.zombie_detected` | Heartbeat-based zombie flagged |
| `sre.checkpoint.failed_terminal` | Checkpoint marked failed (zombie or application error) |

### CloudWatch Alarms

| Alarm | Condition | Action |
|---|---|---|
| `sre-checkpoint-failed-{stage}` | `failed_terminal` > 0 in 5 min | PagerDuty |
| `sre-checkpoint-zombie-{stage}` | `zombie_detected` > 0 in 5 min | Slack + Jira |

---

## 9. State Machine

```
                    write_checkpoint()
                          │
                          ▼
                   ┌─────────────┐
            ┌─────│ in_progress  │
            │     └──────┬──────┘
            │            │
        heartbeat()      │
            │  ┌─────────┼───────────┐
            │  │         │           │
            └──┘    complete()    Zombie detected
                        │        (heartbeat stale 2x)
                        ▼             │
                 ┌──────────┐         ▼
                 │ completed │   ┌─────────┐
                 └──────────┘   │  failed  │
                                └─────────┘
```

**Terminal states**: `completed` (normal success), `failed` (zombie or application-reported failure).

Simple. Three states. No recovery transitions — that's v2.

---

## 10. Deliverables

| # | Component | Purpose |
|---|---|---|
| 1 | `sre_platform/checkpoint/client.py` (Lambda Layer) | CheckpointClient SDK: write, mark_progress, buffered, flush, log_failure, heartbeat, complete, get_pending |
| 2 | `src/repositories/checkpoint_repository.py` | Platform-internal read layer: scan_incomplete, get_pending, detect_zombie |
| 3 | `src/services/delta_report_service.py` | Computes delta from checkpoint data, formats and posts to Jira |
| 4 | `sre-checkpoints-{stage}` DynamoDB table + GSI | CDK — shared checkpoint storage |
| 5 | `sre-checkpoint-manifests-{stage}` S3 bucket | CDK — large manifest side-loading (30-day lifecycle) |
| 6 | `src/services/resolution_service.py` (enhanced) | Checkpoint-aware path: Delta Report on `checkpoint_aware: true` |
| 7 | Batch processor simulation (Scenario 9) | Validates full pipeline: failure state → Delta Report in Jira |
| 8 | CloudWatch metrics (5) + 2 alarms | Observability baseline |

8 deliverables. One-week scope.

---

## 11. Success Criteria

| Criterion | How Verified |
|---|---|
| **Zero Blind Spots** | An engineer opens a Jira ticket and sees the exact list of pending items — no log queries, no DynamoDB scans, no guessing |
| **Zombie Awareness** | Any batch process that hangs for > 2x its timeout is flagged within 60 seconds of detection |
| **Low Friction** | A new service can integrate with the SDK and start reporting checkpoints in under 30 minutes of dev work |
| **Correct Delta** | `get_pending()` returns exactly the unprocessed items after a simulated mid-batch failure |
| **Error Context** | Delta Report shows top error message and occurrence count, not just "it failed" |
| **IAM Isolation** | Lambda can only write checkpoints with its own prefix — verified by IAM policy test |
| **No False Zombies** | 2x heartbeat threshold prevents false positives from Lambda freeze or network blips |
