# Checkpoint & Clarity Framework (v1) — Implementation Plan

## Source Documents

| Document | Location |
|----------|----------|
| v1 Spec | `docs/specs/sre-platform/checkpoint-recovery-framework.md` |
| v2 Roadmap | `docs/specs/sre-platform/checkpoint-recovery-v2-roadmap.md` |
| Batch Simulation Spec | `docs/specs/incident-manager/batch-failure-simulation.md` |
| Batch Recovery Runbook | `docs/runbooks/batch-recovery.md` |
| Existing Implementation Plan | `docs/specs/incident-manager/implementation-plan.md` |

---

## Design Review Resolutions

Two architectural issues were identified in the design review (`reviews/design-review-report.md`) and resolved before implementation:

### ARCH-001: SDK Package Location (RESOLVED)

**Decision**: Place CheckpointClient in the Lambda Layer at `backend/lambda-layer/python/sre_platform/checkpoint/client.py`.

**Rationale**: The SDK is consumed by application Lambdas (batch-processor, future services), not just the incident-manager. Placing it in the shared Lambda Layer matches the existing pattern for `shared/middleware/observability.py` and `shared/middleware/api_gateway.py`. Import path: `from sre_platform.checkpoint import CheckpointClient`.

```
backend/lambda-layer/python/
    shared/
        middleware/
            observability.py      ← existing @observe decorator
            api_gateway.py        ← existing @api_gateway_handler
    sre_platform/
        checkpoint/
            __init__.py
            client.py             ← NEW: CheckpointClient SDK
```

### ARCH-002: Separate Read (Platform) from Write (Application) (RESOLVED)

**Decision**: Create `src/repositories/checkpoint_repository.py` inside incident-manager for platform-internal read operations. The CheckpointClient SDK remains a write-only library for application teams.

**Rationale**: Two audiences, two permission models. Applications write checkpoints (PutItem, UpdateItem on their own prefix). The platform reads checkpoints (Query GSI, GetItem on any prefix). Mixing both in one class conflates permissions and responsibilities.

```
CheckpointClient (Lambda Layer — applications write)
    write_checkpoint(), mark_progress(), log_failure(), heartbeat(), complete()

CheckpointRepository (incident-manager — platform reads)
    scan_incomplete(service), get_checkpoint(id), get_pending(id), detect_zombie(checkpoint)
```

The DeltaReportService depends on CheckpointRepository (not CheckpointClient).

---

## Build Strategy

**Principle**: Deliver the Delta Report to Jira within one week. The SDK must be trivially easy to integrate — if it takes more than 30 minutes for a new service to onboard, v1 failed.

**Risk ordering**: Build the SDK first (the thing apps call), then the Delta Report Service (the thing that produces value), then CDK + simulation (the thing that proves it works).

### MVP Groupings

```
┌─────────────────────────────────────┐
│  MVP A: The Witness                 │  "Can we capture batch state?"
│  TC1 → TC2 → TC3                   │
│  Checkpoint SDK + DynamoDB table    │
│  Prove: write → progress → delta    │
└────────────────┬────────────────────┘
                 │
┌────────────────▼────────────────────┐
│  MVP B: The Clarity                 │  "Can we see the truth in Jira?"
│  TC4 → TC5                         │
│  Delta Report Service + wiring      │
│  Prove: failure → Jira delta report │
└────────────────┬────────────────────┘
                 │
┌────────────────▼────────────────────┐
│  MVP C: Proof of Life               │  "Does it work end-to-end in AWS?"
│  TC6 → TC7                         │
│  CDK + Simulation + Verification    │
│  Prove: batch fails → Jira shows    │
│  exactly which 5 items are pending  │
└─────────────────────────────────────┘
```

| MVP | Tasks | What It Proves | Success Metric |
|-----|-------|---------------|----------------|
| **MVP A** | TC1-TC3 | SDK captures state, DynamoDB schema works, delta computation is correct | `get_pending()` returns exactly the unprocessed items after simulated failure (unit tests) |
| **MVP B** | TC4-TC5 | Delta Report Service produces structured Jira comments, integrates with existing triage flow | Mocked triage → Delta Report formatted correctly with pending IDs, error context, zombie status |
| **MVP C** | TC6-TC7 | Full pipeline works in AWS: batch fails → incident detected → Delta Report in Jira | Engineer opens Jira ticket, sees the exact 5 pending items — zero detective work |

---

## TC1: Checkpoint SDK — Core API

### Objective

Build the CheckpointClient that applications call to report progress. This is the foundation — every other component depends on it.

### Design Decisions

- **Lambda Layer location** — `backend/lambda-layer/python/sre_platform/checkpoint/client.py`. Import: `from sre_platform.checkpoint import CheckpointClient`. Matches existing `shared/middleware/` pattern. (ARCH-001 resolved)
- **Write-only SDK** — Applications write checkpoints. Platform reads via CheckpointRepository (TC4). No read methods on this class beyond `get_pending()` for application-side diagnostics. (ARCH-002 resolved)
- **Pure DynamoDB client** — no queue, no event, just writes. Fire-and-forget.
- **StringSet (SS) for `completed_items`** — `ADD` is atomic and idempotent on Sets. Does NOT work on Lists.
- **Omit `completed_items` on initial write** — DynamoDB does not allow empty StringSets. First `mark_progress()` creates the attribute via `ADD`. `get_pending()` treats absent `completed_items` as empty set. (QUALITY-002 resolved)
- **S3 side-loading** at 500 items — keeps DynamoDB items under 400KB.
- **Hybrid buffered flush** — flush on count OR time, whichever fires first. Call `flush_progress()` before any `time.sleep()` or long I/O, not just at end of processing. (QUALITY-001 resolved)
- **`log_failure()` error key sanitization** — error messages stored in `error_counts` map are hashed/truncated to avoid DynamoDB expression path issues with special characters (colons, spaces). (DYNAMO-001 resolved)
- **`log_failure()`** — optional but high-value. Captures the "Why" alongside the "What."
- **Metric emission** — `write_checkpoint()` emits `sre.checkpoint.created` counter. `complete()` emits `sre.checkpoint.completed` counter. (COMPLETE-001 resolved)

### Files Created

| File | Purpose |
|------|---------|
| `backend/lambda-layer/python/sre_platform/__init__.py` | Package init |
| `backend/lambda-layer/python/sre_platform/checkpoint/__init__.py` | Package init, re-exports `CheckpointClient` |
| `backend/lambda-layer/python/sre_platform/checkpoint/client.py` | CheckpointClient: write, mark_progress, buffered, flush, log_failure, heartbeat, complete, get_pending |
| `backend/lambdas/incident-manager/tests/unit/test_checkpoint_client.py` | 25+ unit tests with moto |

### API Surface

```python
class CheckpointClient:
    def __init__(self, table_name: str, bucket_name: str, dynamodb=None, s3=None): ...

    def write_checkpoint(self, checkpoint_id, service, operation, *,
                         item_ids=None, total_items=None, mode="item_tracking",
                         metadata=None, timeout_seconds=300, ttl_hours=24): ...

    def mark_progress(self, checkpoint_id, *, item_id=None, index=None): ...

    def mark_progress_buffered(self, checkpoint_id, *, item_id=None, index=None,
                                flush_every=100, flush_interval_seconds=5): ...

    def flush_progress(self, checkpoint_id): ...

    def log_failure(self, checkpoint_id, item_id, error_message): ...

    def heartbeat(self, checkpoint_id): ...

    def complete(self, checkpoint_id): ...

    def get_pending(self, checkpoint_id) -> list[str] | int: ...
```

### Implementation Notes

**`write_checkpoint()`**:
- Creates DynamoDB item with `status=in_progress`, `last_heartbeat=now`, `ttl=max(24h, timeout_seconds*4)`
- If `mode="item_tracking"` and `len(item_ids) > 500`: upload to S3, store URI in `all_item_ids`
- If `mode="index_based"`: store `total_items`, `completed_index=0`

**`mark_progress()`**:
- Item tracking: `UpdateExpression: ADD completed_items :item` with `:item = SS([item_id])`
- Index-based: `UpdateExpression: SET completed_index = :idx`
- Also updates `last_heartbeat` and `updated_at`

**`mark_progress_buffered()`**:
- Accumulates in `self._buffers[checkpoint_id]` (list)
- Flushes when `len(buffer) >= flush_every` OR `time.time() - last_flush_time >= flush_interval_seconds`
- Flush = single `ADD completed_items :batch` with all buffered IDs as StringSet

**`log_failure()`**:
- `UpdateExpression: SET last_error = :err, updated_at = :now`
- `ADD error_counts.#msg :one` (increment counter for this error message)
- `SET first_failed_id = if_not_exists(first_failed_id, :id)` — only captures the first

**`get_pending()`**:
- Item tracking: loads `all_item_ids` (from DynamoDB or S3) and `completed_items`, returns difference
- Index-based: returns `completed_index + 1`

### Test Scenarios

| # | Scenario | What It Proves |
|---|----------|---------------|
| 1 | write_checkpoint creates DynamoDB item | Schema correct, status=in_progress, heartbeat set |
| 2 | write_checkpoint with S3 side-loading (>500 items) | S3 upload, URI in all_item_ids |
| 3 | write_checkpoint index_based mode | total_items stored, no all_item_ids |
| 4 | mark_progress adds to StringSet | ADD on SS is atomic, idempotent |
| 5 | mark_progress index_based updates completed_index | SET overwrite works |
| 6 | mark_progress updates heartbeat | last_heartbeat refreshed |
| 7 | mark_progress_buffered flushes at count threshold | Buffer accumulates, flushes at flush_every |
| 8 | mark_progress_buffered flushes at time threshold | Time-based flush fires even if count not reached |
| 9 | flush_progress writes buffered items | Explicit flush empties buffer |
| 10 | flush_progress is no-op when buffer empty | Safe to call multiple times |
| 11 | log_failure stores error and increments counter | last_error, error_counts, first_failed_id set |
| 12 | log_failure preserves first_failed_id | Second call doesn't overwrite first |
| 13 | log_failure increments same error counter | error_counts accumulates |
| 14 | heartbeat updates last_heartbeat only | No side effects |
| 15 | complete sets status=completed | Terminal state |
| 16 | complete flushes buffer first | Buffer flushed before status change |
| 17 | get_pending item_tracking returns delta | all_item_ids - completed_items |
| 18 | get_pending item_tracking with S3 manifest | Loads from S3, computes delta |
| 19 | get_pending index_based returns resume point | completed_index + 1 |
| 20 | get_pending with no progress returns all items | 0 completed = all pending |
| 21 | get_pending with all completed returns empty | Full completion = nothing pending |
| 22 | TTL computed correctly | max(24h, timeout_seconds * 4) |
| 23 | Duplicate mark_progress is idempotent | Same item_id twice = 1 entry in SS |
| 24 | write_checkpoint with metadata | metadata map stored correctly |
| 25 | complete on already-completed is no-op | Idempotent terminal state |

### Done When
- `pytest tests/unit/test_checkpoint_client.py` — 25+ pass (moto)
- SDK covers both modes (item_tracking, index_based)
- Buffered flush works by count AND time
- `log_failure()` captures error context
- `get_pending()` returns correct delta for all edge cases

---

## TC2: Checkpoint Table — DynamoDB Schema + Fixtures

### Objective

Define the DynamoDB table schema as a reusable fixture (for tests) and CDK construct (for deployment). Validate the GSI query pattern.

### Files Created

| File | Purpose |
|------|---------|
| `tests/conftest.py` (modified) | Add `mock_checkpoint_table` and `mock_checkpoint_client` fixtures |
| `tests/unit/test_checkpoint_table.py` | GSI query tests: service-status-index lookups |

### DynamoDB Table Schema

```python
# Table: sre-checkpoints-{stage}
table = dynamodb.Table(
    table_name=f"sre-checkpoints-{stage}",
    partition_key=Attribute(name="checkpoint_id", type=AttributeType.STRING),
    billing_mode=BillingMode.PAY_PER_REQUEST,
    time_to_live_attribute="ttl",
    removal_policy=RemovalPolicy.DESTROY,  # dev only
)

table.add_global_secondary_index(
    index_name="service-status-index",
    partition_key=Attribute(name="service", type=AttributeType.STRING),
    sort_key=Attribute(name="status", type=AttributeType.STRING),
    projection_type=ProjectionType.ALL,
)
```

### Test Scenarios

| # | Scenario | What It Proves |
|---|----------|---------------|
| 1 | GSI query: service + status=in_progress | Targeted lookup, not scan |
| 2 | GSI query: no results | Empty result set handled |
| 3 | GSI query: multiple checkpoints for same service | All returned |
| 4 | TTL attribute set correctly | DynamoDB auto-expiry works |
| 5 | Concurrent writes to same checkpoint_id | Last-writer-wins (expected for status updates) |

### Done When
- GSI query pattern validated with moto
- Test fixtures available for all subsequent tasks
- Schema matches v1 spec Section 2

---

## TC3: Checkpoint SDK — Integration Test (Local)

### Objective

End-to-end test of the SDK against moto: simulate a batch processing failure and verify the delta is correct.

### Files Created

| File | Purpose |
|------|---------|
| `tests/unit/test_checkpoint_integration.py` | Multi-step scenario: write → progress × 5 → "crash" → get_pending = 5 |

### Test Scenarios

| # | Scenario | What It Proves |
|---|----------|---------------|
| 1 | Happy path: write → 10 mark_progress → complete | Full lifecycle, status=completed |
| 2 | Partial failure: write → 5 mark_progress → get_pending | Delta = 5 pending IDs |
| 3 | Buffered partial: write → 137 buffered → crash → get_pending | Delta = N - (last flush count) |
| 4 | Index-based partial: write(total=50000) → mark_progress(index=22500) → get_pending | Returns 22501 |
| 5 | With log_failure: write → 3 success + 2 failures → get_pending | Delta correct + error_counts populated |
| 6 | S3 side-loading: write(1000 items) → 500 mark_progress → get_pending | S3 manifest loaded, delta = 500 |
| 7 | Zombie simulation: write → no heartbeat for 2x timeout | is_zombie() returns True |
| 8 | Not zombie: write → heartbeat within timeout | is_zombie() returns False |

### Done When
- All 8 multi-step scenarios pass
- Delta computation is mathematically correct for all modes
- **MVP A complete** — checkpoint SDK captures state correctly

---

## TC4: Delta Report Service + Checkpoint Repository

### Objective

Build the platform-internal read layer (CheckpointRepository) and the service that transforms checkpoint data into structured Jira comments (DeltaReportService). This is the primary value delivery of v1.

### Files Created

| File | Purpose |
|------|---------|
| `src/repositories/checkpoint_repository.py` | `CheckpointRepository`: GSI queries, get_pending(), zombie detection — platform reads (ARCH-002) |
| `src/services/delta_report_service.py` | `DeltaReportService`: compute delta, format report, post to Jira |
| `tests/unit/test_checkpoint_repository.py` | 8+ tests for repository query methods |
| `tests/unit/test_delta_report_service.py` | 15+ tests for report formatting and Jira posting |

### CheckpointRepository (Platform Read Layer)

```python
class CheckpointRepository:
    """Platform-internal read operations on the checkpoint table.

    Separated from CheckpointClient (application write SDK) per ARCH-002.
    Different audience, different IAM permissions."""

    def __init__(self, table_name: str, bucket_name: str, dynamodb=None, s3=None):
        self._table = dynamodb.Table(table_name)
        self._bucket_name = bucket_name
        self._s3 = s3

    @observe(operation="scan_incomplete", metric_prefix="checkpoint_repo")
    def scan_incomplete(self, service_name: str) -> list[dict]:
        """Query GSI: service + status=in_progress. Returns checkpoint items."""

    @observe(operation="get_checkpoint", metric_prefix="checkpoint_repo")
    def get_checkpoint(self, checkpoint_id: str) -> dict | None:
        """GetItem by checkpoint_id."""

    @observe(operation="get_pending", metric_prefix="checkpoint_repo")
    def get_pending(self, checkpoint: dict) -> list[str] | int:
        """Compute pending items from checkpoint data.
        Item tracking: all_item_ids - completed_items (loads from S3 if URI).
        Index-based: completed_index + 1."""

    def detect_zombie(self, checkpoint: dict) -> bool:
        """2x heartbeat threshold. Returns True if zombie."""
```

### DeltaReportService (Value Layer)

```python
class DeltaReportService:
    def __init__(self, checkpoint_repo: CheckpointRepository, ticketing_repo, config):
        self._checkpoint_repo = checkpoint_repo
        self._ticketing = ticketing_repo
        self._config = config

    @observe(operation="generate_delta_report", metric_prefix="checkpoint_delta")
    def generate_and_post(self, service_name: str, jira_ticket_id: str) -> dict:
        """Scan checkpoints for service, compute deltas, post report to Jira.

        Emits sre.checkpoint.items_pending and sre.checkpoint.zombie_detected metrics.

        Returns: {checkpoints_found, total_pending, report_posted}"""

    def _compute_delta(self, checkpoint: dict) -> dict:
        """Calls checkpoint_repo.get_pending() and enriches with error context."""

    def _format_report(self, deltas: list[dict]) -> str:
        """Formats the Delta Report as Jira comment text.
        Small batch (<50 pending): list IDs.
        Large batch (>50 pending): summarize + S3 link.
        Multiple checkpoints: grouped summary.
        Includes timestamp: 'Snapshot at {ts} — run get_pending() for current state'."""

    def _summarize_errors(self, checkpoint: dict) -> str:
        """Format error_counts into 'Top Error: ... (N occurrences)' + 'Other Errors: ...'"""
```

### Report Formatting Rules

| Condition | Format |
|---|---|
| 1 checkpoint, < 50 pending | Full detail: counts + pending IDs + error context |
| 1 checkpoint, >= 50 pending | Counts + S3 manifest link + error context |
| N checkpoints | Grouped summary: per-checkpoint line + totals |
| Zombie detected | `Zombie: YES (no heartbeat for Xs)` flag |
| Error context available | `Top Error: {message} ({count} occurrences)` |
| No error context | `Failure Context: Not reported by application` |

### Test Scenarios

| # | Scenario | What It Proves |
|---|----------|---------------|
| 1 | Single checkpoint, 5 pending, with errors | Full Delta Report format matches spec |
| 2 | Single checkpoint, 100 pending | Large batch summary (no individual IDs, S3 link) |
| 3 | Three checkpoints for same service | Grouped report with per-checkpoint lines + totals |
| 4 | Zero pending (all completed) | `Nothing pending — batch completed before detection` |
| 5 | Zero completed (no progress) | `0% complete — no items processed` |
| 6 | Zombie detected | Zombie flag in report |
| 7 | Not zombie (recent heartbeat) | No zombie flag |
| 8 | Error context: top error + count | `Top Error: ReadTimeout (52 occurrences)` |
| 9 | Error context: multiple errors | Top + "Other Errors" line |
| 10 | Error context: first_failed_id shown | `First Failed ID: POL-776` |
| 11 | No error context (app didn't call log_failure) | Graceful fallback message |
| 12 | Index-based checkpoint report | `resume from index 22,501` format |
| 13 | Jira comment posted successfully | ticketing_repo.add_jira_comment called with formatted text |
| 14 | Jira comment failed | Returns report_posted=False, does not raise |
| 15 | No incomplete checkpoints found | Returns {checkpoints_found: 0}, no Jira comment |

### Done When
- `pytest tests/unit/test_delta_report_service.py` — 15+ pass
- Report format matches v1 spec Section 6 exactly
- Zombie detection uses 2x threshold
- Error context summarized correctly

---

## TC5: Wiring — Delta Report into Existing Pipeline

### Objective

Connect the Delta Report Service to the existing triage/resolution flow. When the Triage Lambda processes a `checkpoint_aware` incident, it invokes the Delta Report Service instead of (or before) triggering recovery.

### Design Decision: Where to Wire

The Delta Report runs inside `ResolutionService.trigger_recovery()` when `checkpoint_aware: true`:

```
ResolutionService.trigger_recovery("reprocess", ...)
    │
    ├── Check recovery_catalog → checkpoint_aware: true?
    │     │
    │     ├── YES → DeltaReportService.generate_and_post(service, jira_ticket_id)
    │     │         Post Delta Report to Jira (this is the v1 value)
    │     │         Return ("delta-reported", "Delta Report posted: 5 pending items")
    │     │
    │     └── NO  → Existing behavior (trigger Step Function or Lambda)
    │
    └── Return (recovery_status, detail)
```

This means:
- **Zero changes to Detection or Escalation Lambdas** — Delta Report is internal to triage/resolution
- **Zero changes to the TriageService orchestration** — it already calls `trigger_recovery()`
- **Backward compatible** — existing non-checkpoint services work unchanged
- **Forward compatible** — v2 auto-recovery adds behavior after the Delta Report, not instead of it

### Files Modified

| File | Change |
|------|--------|
| `src/services/resolution_service.py` | Add `_handle_checkpoint_recovery()` path when `checkpoint_aware: true`. Accepts `DeltaReportService` in `__init__()`. |
| `src/handlers/triage_handler.py` | Wire `CheckpointRepository` + `DeltaReportService` into `_init_services()` singleton, pass to `ResolutionService` |
| `src/models/config.py` | Parse `checkpoint_aware` and `auto_recover` from recovery catalog entries (COMPLETE-002) |
| `src/models/enums.py` | Add `DELTA_REPORTED` to `RecoveryStatus` |
| `incident_config.json` | Add `checkpoint_aware: true, auto_recover: false` to `reprocess` catalog entry |
| `tests/unit/test_resolution_service.py` | Tests for checkpoint-aware path |
| `tests/conftest.py` | Add `mock_checkpoint_repo` and `mock_delta_report_service` fixtures |

### Recovery Catalog Change

```json
"reprocess": {
  "type": "step_function",
  "workflow_arn_env": "REPROCESS_BATCH_WORKFLOW_ARN",
  "recovery_handler_env": "BATCH_RECOVERY_FUNCTION_NAME",
  "checkpoint_aware": true,
  "auto_recover": false,
  "max_retries": 3,
  "description": "Reprocess pending batch items using checkpoint data"
}
```

**`auto_recover: false`** = v1 behavior (Delta Report only).
**`auto_recover: true`** = v2 behavior (Delta Report + Step Function trigger).

### New RecoveryStatus Value

Add to `src/models/enums.py`:
```python
class RecoveryStatus(str, Enum):
    ...
    DELTA_REPORTED = "delta-reported"  # v1: checkpoint delta posted to Jira
```

### Test Scenarios

| # | Scenario | What It Proves |
|---|----------|---------------|
| 1 | checkpoint_aware=true, auto_recover=false | Delta Report generated, no Step Function triggered |
| 2 | checkpoint_aware=true, auto_recover=true (future) | Delta Report + Step Function (placeholder for v2) |
| 3 | checkpoint_aware=false (existing behavior) | No Delta Report, existing recovery path unchanged |
| 4 | checkpoint_aware not in catalog entry | Treated as false (backward compatible) |
| 5 | Delta Report Service returns 0 pending | "Nothing pending" status, still considered success |
| 6 | Delta Report Service fails to post to Jira | Returns delta-reported with failure note, no crash |
| 7 | Resolution returns DELTA_REPORTED to Triage | Triage reports recovery_status="delta-reported" to Jira/EventBridge |

### Done When
- `pytest tests/unit/test_resolution_service.py` — all pass (existing + new)
- `checkpoint_aware: true` → Delta Report path
- `checkpoint_aware: false` or missing → existing behavior unchanged
- **MVP B complete** — Delta Report flows through the existing pipeline

---

## TC6: CDK Infrastructure + Redeployment

### Objective

Deploy the checkpoint DynamoDB table, S3 bucket, IAM permissions, and redeploy the Triage Lambda with TC4+TC5 code changes (DeltaReportService, CheckpointRepository, resolution wiring).

### Files Modified

| File | Change |
|------|--------|
| `infra/stacks/incident_manager_stack.py` | Add: `sre-checkpoints-{stage}` table + GSI, `sre-checkpoint-manifests-{stage}` S3 bucket, IAM grants, Triage Lambda env vars for checkpoint table/bucket |
| `infra/config.json` | Add `checkpoint` config block |

### New CDK Resources

| Resource | Name | Purpose |
|---|---|---|
| DynamoDB Table | `sre-checkpoints-{stage}` | Shared checkpoint storage |
| DynamoDB GSI | `service-status-index` | Targeted query by service + status |
| S3 Bucket | `sre-checkpoint-manifests-{stage}` | Large manifest side-loading, 30-day lifecycle rule (WARN-001) |

### S3 Lifecycle Rule

```python
bucket.add_lifecycle_rule(
    expiration=Duration.days(30),
    id="expire-checkpoint-manifests",
)
```

### Triage Lambda Environment Variables (New)

```python
"CHECKPOINT_TABLE_NAME": f"sre-checkpoints-{stage}",
"CHECKPOINT_BUCKET_NAME": f"sre-checkpoint-manifests-{stage}",
```

### IAM Grants

| Principal | Resource | Actions |
|---|---|---|
| Triage Lambda | `sre-checkpoints-{stage}` | Query (GSI), GetItem |
| Triage Lambda | `sre-checkpoint-manifests-{stage}` | GetObject |
| Batch Processor (simulation) | `sre-checkpoints-{stage}` | PutItem, UpdateItem (prefix: `batch:batch-processor-*`) |
| Batch Processor (simulation) | `sre-checkpoint-manifests-{stage}` | PutObject (prefix: `batch:batch-processor-*`) |

### Config Addition

```json
{
  "incident_manager": {
    ...
    "checkpoint": {
      "table_name_suffix": "sre-checkpoints",
      "bucket_name_suffix": "sre-checkpoint-manifests",
      "default_ttl_hours": 24
    }
  }
}
```

### Deployment Sequence

This task includes redeployment of the Triage Lambda with all code from TC4 (CheckpointRepository, DeltaReportService) and TC5 (ResolutionService wiring, config changes). The sequence:

1. `rsync` Lambda package with TC4+TC5 code changes
2. `cdk synth` — verify checkpoint table, GSI, S3 bucket, IAM, env vars in template
3. `cdk deploy` — stack updated (new resources + Triage Lambda redeployed)
4. Verify DynamoDB table exists: `aws dynamodb describe-table --table-name sre-checkpoints-dev`
5. Verify S3 bucket exists with lifecycle: `aws s3api get-bucket-lifecycle-configuration --bucket sre-checkpoint-manifests-dev`
6. Verify Triage Lambda has new env vars: `aws lambda get-function-configuration --function-name incident-triage-dev --query 'Environment.Variables'`

### Done When
- Checkpoint table deployed with GSI and TTL
- S3 bucket deployed with 30-day lifecycle
- Triage Lambda redeployed with DeltaReportService + CheckpointRepository
- IAM permissions scoped by prefix
- Existing incident manager resources unchanged

---

## TC7: Simulation — Batch Failure with Delta Report

### Objective

Build a simulation that proves the full v1 pipeline: batch fails → checkpoint survives → Delta Report appears in Jira with exactly the right pending items. This is the "Zero Blind Spots" proof.

### Simulation Design

The simulation has two phases:

**Phase 1: Create the Failure State** (direct DynamoDB writes — no deployed batch Lambda needed)
- Write a checkpoint record to `sre-checkpoints-dev` simulating a batch that wrote 5/10 items
- Write 5 TXN records to `batch-transactions-dev` (the "completed" work)
- This simulates the state after a batch processor timed out

**Phase 2: Trigger the Incident Pipeline** (real Detection → Triage → Delta Report)
- Create a CloudWatch alarm and publish ALARM event to SNS
- Detection Lambda creates Jira ticket, publishes IncidentCreated
- Triage Lambda classifies root cause, invokes `trigger_recovery("reprocess")`
- Resolution Service sees `checkpoint_aware: true`, invokes Delta Report Service
- Delta Report Service scans `sre-checkpoints-dev`, computes delta, posts to Jira
- Verify: Jira ticket has Delta Report with 5 pending items listed

### Why Phase 1 Uses Direct DynamoDB (Not a Deployed Lambda)

v1 is about observability, not about the batch processor itself. Deploying a batch Lambda, API Gateway route, and batch-transactions table would be v2 simulation infrastructure. For v1, we prove:
1. The SDK **schema** is correct (by writing the checkpoint record directly)
2. The Delta Report **reads** checkpoint data correctly
3. The pipeline **routes** checkpoint-aware incidents to the Delta Report

The deployed batch processor + recovery handler is a TC8+ concern (out of v1 scope).

### Files Created

| File | Purpose |
|------|---------|
| `scripts/incident/simulations/scenarios/checkpoint_clarity.py` | Scenario 9: Checkpoint & Clarity simulation |
| `scripts/incident/simulations/lib/checkpoint.py` | Checkpoint table helper: write mock checkpoints, read state, cleanup |

### Simulation Flow (12 Steps)

```
Step  Action                                                  Validates
────  ──────────────────────────────────────────────────────  ──────────────────────────
 1    Pre-clean: delete stale checkpoint + incident records    Clean state
 2    Write checkpoint to sre-checkpoints-dev:                 SDK schema
        checkpoint_id = batch:batch-processor-api-dev:b-sim-001
        status = in_progress
        total_items = 10
        completed_items = {txn-1..txn-5}
        error_counts = {"ReadTimeout: downstream API unresponsive": 3}
        first_failed_id = txn-6
        last_heartbeat = 5 minutes ago (stale but not zombie)
 3    Write 5 TXN records to batch-transactions-dev            Application state
 4    Verify: get_pending() returns [txn-6..txn-10]            Delta computation
 5    Create alarm sim-batch-high-batch-failure-dev             Alarm convention
 6    Publish ALARM to SNS with FunctionName dimension          Detection trigger
 7    Wait for Detection (cool-off + Jira creation)             Pipeline initiation
 8    Verify DynamoDB incident record (DETECTED, ticket)        Correlation store
 9    Wait for Triage → Delta Report pipeline                   Processing time
10    Verify Triage logs: checkpoint-aware recovery path         Pipeline routing
11    Verify Jira ticket has Delta Report comment:               THE DELIVERABLE
        - Total: 10, Succeeded: 5, Pending: 5
        - Pending IDs: txn-6, txn-7, txn-8, txn-9, txn-10
        - Top Error: ReadTimeout (3 occurrences)
        - First Failed ID: txn-6
        - Note: Manual intervention required
12    Cleanup: delete checkpoint, incident record, alarm         Clean teardown
```

### Simulation Lib: `lib/checkpoint.py`

```python
"""Checkpoint table helpers for simulation scenarios."""

import boto3
import time
from datetime import datetime, timezone, timedelta
from lib import config

_dynamodb = boto3.resource("dynamodb", region_name=config.REGION)
_checkpoint_table = _dynamodb.Table(f"sre-checkpoints-{config.STAGE}")

def write_mock_checkpoint(checkpoint_id, service, total_items, completed_items,
                          error_counts=None, first_failed_id=None,
                          timeout_seconds=300, heartbeat_age_seconds=0):
    """Write a checkpoint record simulating a partial failure."""
    now = datetime.now(timezone.utc)
    heartbeat = now - timedelta(seconds=heartbeat_age_seconds)
    ttl = int((now + timedelta(hours=24)).timestamp())

    item = {
        "checkpoint_id": checkpoint_id,
        "service": service,
        "operation": "batch-insert",
        "checkpoint_mode": "item_tracking",
        "status": "in_progress",
        "total_items": total_items,
        "completed_items": set(completed_items),
        "all_item_ids": set([f"txn-{i}" for i in range(1, total_items + 1)]),
        "last_heartbeat": heartbeat.isoformat(),
        "created_at": (now - timedelta(minutes=5)).isoformat(),
        "updated_at": heartbeat.isoformat(),
        "timeout_seconds": timeout_seconds,
        "ttl": ttl,
        "metadata": {"target_table": f"batch-transactions-{config.STAGE}"},
    }

    if error_counts:
        item["error_counts"] = error_counts
    if first_failed_id:
        item["first_failed_id"] = first_failed_id

    _checkpoint_table.put_item(Item=item)
    return item

def get_checkpoint(checkpoint_id):
    """Get a checkpoint record."""
    resp = _checkpoint_table.get_item(Key={"checkpoint_id": checkpoint_id})
    return resp.get("Item")

def delete_checkpoint(checkpoint_id):
    """Delete a checkpoint record."""
    _checkpoint_table.delete_item(Key={"checkpoint_id": checkpoint_id})

def query_service_checkpoints(service, status="in_progress"):
    """Query GSI for service + status."""
    resp = _checkpoint_table.query(
        IndexName="service-status-index",
        KeyConditionExpression="service = :svc AND #s = :st",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":svc": service, ":st": status},
    )
    return resp.get("Items", [])
```

### Scenario 9: `checkpoint_clarity.py`

```python
"""Scenario 9: Checkpoint & Clarity — Partial failure → Delta Report in Jira.

Validates the v1 Checkpoint & Clarity Framework:
  - Checkpoint record captures partial batch state
  - SRE Platform detects the failure via CloudWatch alarm
  - Triage recognizes checkpoint_aware recovery model
  - Delta Report Service computes correct delta (5 pending items)
  - Delta Report posted to Jira with exact pending IDs + error context
"""
```

### Zombie Detection Bonus Step (Optional)

If time allows, add a step between 2 and 3 that writes a **zombie** checkpoint:

```
 2b   Write zombie checkpoint (heartbeat > 2x timeout)         Zombie detection
        last_heartbeat = 15 minutes ago, timeout_seconds = 300
 ...
 11b  Verify Jira Delta Report includes:                        Zombie awareness
        Zombie: YES (no heartbeat for 900s)
```

### Test Assertions (Step 11 Detail)

The simulation verifies the Jira ticket comment contains:

```
MUST contain (substring match):
  ✓ "Total Items"    and "10"
  ✓ "Succeeded"      and "5"
  ✓ "Pending"        and "5"
  ✓ "txn-6"          (at least one pending ID)
  ✓ "ReadTimeout"    (error context)
  ✓ "Manual intervention required"  (v1 note)

MUST NOT contain:
  ✗ "RETRY"          (no retry button in v1)
  ✗ "auto-recovery"  (no auto-recovery in v1)
```

### Done When
- `python scripts/incident/simulations/run.py --scenario 9` — 12/12 steps pass
- Jira ticket shows Delta Report with exact pending items
- Engineer can open the Jira ticket and immediately know what to fix
- **MVP C complete** — full v1 pipeline proven in AWS

---

## Cross-Reference: Tasks to v1 Spec Deliverables

| v1 Deliverable (Spec Section 10) | Built In | Tested In |
|----------------------------------|----------|-----------|
| 1. `sre_platform/checkpoint/client.py` — CheckpointClient SDK (Lambda Layer) | TC1 | TC1, TC3 |
| 2. `src/repositories/checkpoint_repository.py` — Platform read layer | TC4 | TC4 |
| 3. `src/services/delta_report_service.py` — Delta Report | TC4 | TC4, TC7 |
| 4. `sre-checkpoints-{stage}` DynamoDB table + GSI | TC6 | TC2 (moto), TC7 (live) |
| 5. `sre-checkpoint-manifests-{stage}` S3 bucket + lifecycle | TC6 | TC1 (moto), TC7 (live) |
| 6. `resolution_service.py` enhanced for checkpoint-aware | TC5 | TC5 |
| 7. Batch processor simulation | TC7 | TC7 |
| 8. CloudWatch metrics (5) + 2 alarms | TC1 (SDK metrics), TC4 (report metrics), TC6 (alarms) | TC7 |

## Cross-Reference: Tasks to v1 Success Criteria

| Success Criterion (Spec Section 11) | Verified By |
|--------------------------------------|-------------|
| Zero Blind Spots | TC7 Step 11: Jira shows exact pending items |
| Zombie Awareness | TC3 Scenario 7-8: is_zombie() tests; TC7 optional zombie step |
| Low Friction | TC1: SDK API surface (5 lines of code to integrate) |
| Correct Delta | TC3 Scenarios 1-6: get_pending() returns exact delta |
| Error Context | TC4 Scenarios 8-11: error_counts, first_failed_id in report |
| IAM Isolation | TC6: prefix-scoped IAM grants |
| No False Zombies | TC3 Scenario 8: 2x threshold prevents false positives |

---

## Cumulative Progress by Task

| After Task | MVP | Tests | AWS Resources |
|------------|-----|-------|---------------|
| TC1 | A | ~25 (SDK unit tests) | None |
| TC2 | A | ~30 (+ table/GSI tests) | None |
| **TC3** | **A** | **~38 (+ integration)** | **None** |
| | | **MVP A: Checkpoint SDK captures state correctly** | |
| TC4 | B | ~61 (+ repository 8 + Delta Report 15) | None |
| **TC5** | **B** | **~68 (+ wiring 7)** | **None** |
| | | **MVP B: Delta Report flows through pipeline** | |
| TC6 | C | ~68 (same) | DynamoDB table + S3 bucket (30d lifecycle) + IAM + Triage Lambda redeployed |
| **TC7** | **C** | **~68 + live simulation** | **Same (simulation uses deployed resources)** |
| | | **MVP C: Full v1 pipeline proven — Delta Report in Jira** | |

---

## Execution Status

_Last updated: 2026-04-02_

| Task | Status | Notes |
|------|--------|-------|
| TC1: Checkpoint SDK | PENDING | |
| TC2: Checkpoint Table Schema | PENDING | |
| TC3: SDK Integration Test | PENDING | |
| TC4: Delta Report Service | PENDING | |
| TC5: Pipeline Wiring | PENDING | |
| TC6: CDK Infrastructure | PENDING | |
| TC7: Simulation | PENDING | |
