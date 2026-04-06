# SRE Platform — Checkpoint & Recovery Framework: v2 Roadmap

**Parent spec**: `checkpoint-recovery-framework.md` (v1)

This document captures enhancements deferred from v1. Each section includes a **Trigger** — the concrete condition under which building it becomes justified. Nothing here should be built speculatively.

---

## Overview

v1 delivers visibility (Delta Report) and manual retry (Big Red Button). v2 extends toward automated, scalable, and event-driven recovery — but only when operational volume or failure frequency demands it.

```
v1: See It, Click It, Fix It     →   v2: See It, Auto-Fix It (with guardrails)
    Delta Report + Retry Button        Auto-recovery + Parallel Fan-Out + Audit Trail
```

---

## 1. Auto-Recovery (Step Function Auto-Trigger)

**What**: When an incident is detected for a `checkpoint_aware` service, the platform automatically invokes the recovery handler instead of waiting for a human click.

**How**: Config change only — `auto_recover: true` in the recovery catalog:

```json
"reprocess": {
  "type": "step_function",
  "workflow_arn_env": "REPROCESS_BATCH_WORKFLOW_ARN",
  "recovery_handler_env": "BATCH_RECOVERY_FUNCTION_NAME",
  "checkpoint_aware": true,
  "auto_recover": true,
  "max_retries": 3,
  "description": "Reprocess pending batch items using checkpoint data"
}
```

**Flow change**: After computing the delta and posting the Delta Report to Jira, the recovery engine continues:

```
ResolutionService.trigger_recovery(...)
       │
       ├── Steps 1–3: Same as v1 (scan, compute delta, post Delta Report)
       │
       ├── Step 4 (NEW): auto_recover == true?
       │     ├── YES → Lock checkpoint → Start Step Function → recovery handler
       │     │          On success: complete(), update Jira with result
       │     │          On failure: increment retry_count, unlock, post error to Jira
       │     └── NO  → Done. Human clicks retry (v1 behavior).
       └── Done.
```

**Safety guardrails**:
- Delta Report is ALWAYS posted first, even in auto mode — visibility is never sacrificed
- `max_retries` enforced (default: 3) — prevents infinite recovery loops
- Auto-recovery disabled during incident storms (active_count > storm_threshold)
- Jira ticket updated with auto-recovery status so operators have full audit trail

**Trigger**: Build when teams are clicking the retry button on >80% of incidents within 5 minutes of the Delta Report — at that point, auto-trigger saves consistent toil without adding risk.

---

## 2. Parallel Recovery (Map State Fan-Out)

**What**: For large pending sets (>500 items), split recovery into parallel chunks using Step Functions Map state.

**Why deferred**: v1 batches are <100 items. Sequential processing in the recovery handler completes in seconds. The complexity of chunking, aggregation, and partial failure tracking is not justified.

**Architecture**:

```
Step Function (Map State)
       │
       ├── Chunker Lambda
       │     Splits pending_items into N chunks of configurable size
       │     Returns: [{chunk_id: 1, items: [...]}, {chunk_id: 2, items: [...]}, ...]
       │
       ├── Map State (max_concurrency = N)
       │     Each iteration invokes recovery handler with one chunk
       │
       └── Aggregator Lambda
             Collects results from all iterations
             Reports: total_processed, total_failed, per-chunk status
             Updates checkpoint: complete() or partial failure
```

**Step Function definition sketch**:

```json
{
  "StartAt": "ChunkPendingItems",
  "States": {
    "ChunkPendingItems": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:...:chunk-pending-items",
      "Next": "ParallelRecover"
    },
    "ParallelRecover": {
      "Type": "Map",
      "ItemsPath": "$.chunks",
      "MaxConcurrency": 10,
      "Iterator": {
        "StartAt": "RecoverChunk",
        "States": {
          "RecoverChunk": {
            "Type": "Task",
            "Resource": "arn:aws:lambda:...:recovery-handler",
            "End": true
          }
        }
      },
      "Next": "AggregateResults"
    },
    "AggregateResults": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:...:aggregate-recovery",
      "End": true
    }
  }
}
```

**Partial failure handling**: If 3 of 10 chunks fail, the aggregator:
1. Marks the checkpoint with the items that succeeded (updates `completed_items`)
2. Stores chunk failure details in `last_error`
3. Leaves status as `in_progress` so the next retry only picks up remaining items
4. Posts partial recovery result to Jira

**Trigger**: Build when a single recovery handler execution exceeds its Lambda timeout (15 min) due to pending item count, or when teams report recovery taking too long for operational comfort.

---

## 3. Recovery Payload S3 Reference

**What**: For large pending sets, pass an S3 URI in the Step Function payload instead of embedding the full item list.

**Why deferred**: Step Functions have a 256KB payload limit. v1 batches are <100 items (~4KB), well under the limit.

**Approach**:

```python
if len(pending_items) > PAYLOAD_THRESHOLD:  # e.g., 1000 items
    uri = upload_to_s3(
        bucket=f"sre-checkpoint-manifests-{stage}",
        key=f"{checkpoint_id}/pending.json",
        body=json.dumps(pending_items),
    )
    payload = {
        "checkpoint_id": checkpoint_id,
        "pending_items_uri": uri,  # S3 reference
        "pending_count": len(pending_items),
        "metadata": metadata,
    }
else:
    payload = {
        "checkpoint_id": checkpoint_id,
        "pending_items": pending_items,  # inline
        "metadata": metadata,
    }
```

The recovery handler checks for `pending_items_uri` and downloads from S3 if present:

```python
def lambda_handler(event, context):
    if "pending_items_uri" in event:
        pending = download_from_s3(event["pending_items_uri"])
    else:
        pending = event["pending_items"]
    # ... process pending items
```

**Trigger**: Build when any service has >1,000 pending items in a single recovery, or when payload size errors appear in Step Function execution logs.

---

## 4. S3 Manifest Partitioning + Compression

**What**: For very large manifests (>50K items), partition the S3 manifest file and apply gzip compression.

**Approach**:

```
s3://sre-checkpoint-manifests-{stage}/
    {checkpoint_id}/
        manifest/
            part-0000.json.gz    # Items 0–9,999
            part-0001.json.gz    # Items 10,000–19,999
            ...
        completed/
            part-0000.json.gz    # Completed items (flushed from DynamoDB)
```

**get_pending() merge**:
```python
all_items = set()
for part in list_s3_parts(f"{checkpoint_id}/manifest/"):
    all_items.update(decompress_and_parse(part))

completed = checkpoint.completed_items  # DynamoDB SS
for part in list_s3_parts(f"{checkpoint_id}/completed/"):
    completed.update(decompress_and_parse(part))

pending = all_items - completed
```

**Compression savings**: JSON list of 50K UUIDs ≈ 1.8MB uncompressed → ~400KB gzipped.

**Trigger**: Build when any service registers >50K items in a single checkpoint, or when S3 read latency in `get_pending()` exceeds 5 seconds.

---

## 5. Recovery Audit Log

**What**: A DynamoDB table (`sre-checkpoint-audit-{stage}`) that records every recovery attempt for compliance and post-incident review.

**Schema**:

| Attribute | Type | Description |
|---|---|---|
| `audit_id` (PK) | String | `{checkpoint_id}:{attempt_number}` |
| `checkpoint_id` | String | Reference to checkpoint |
| `triggered_by` | String | `auto`, `manual:{user_id}`, `retry-all:{user_id}` |
| `triggered_at` | String | ISO 8601 |
| `pending_count` | Number | Items pending at trigger time |
| `result` | String | `success`, `partial`, `failed` |
| `processed_count` | Number | Items successfully processed |
| `failed_count` | Number | Items that failed |
| `duration_ms` | Number | Wall-clock recovery duration |
| `error_message` | String | Error details if failed |
| `execution_arn` | String | Step Function execution ARN |
| `ttl` | Number | Epoch seconds (90 days default) |

**GSI**: `checkpoint-index` (partition: `checkpoint_id`, sort: `triggered_at`) — view full recovery history for one checkpoint.

**Uses**:
- Post-incident review: "How many times did we retry? What failed?"
- Compliance: "Who triggered recovery and when?"
- Operational metrics: "Average recovery duration by service"

**Trigger**: Build when the team needs formal post-incident documentation, or when compliance requires an audit trail for automated actions on production data.

---

## 6. Event-Driven Recovery (DynamoDB Streams)

**What**: Instead of the recovery engine polling/scanning the checkpoint table on incident detection, use DynamoDB Streams to react to checkpoint state changes in real-time.

**Architecture**:

```
DynamoDB Streams (sre-checkpoints-{stage})
       │
       ├── Filter: status changed to "in_progress" for >timeout_seconds
       │   OR: last_heartbeat stale (zombie detection)
       │
       └── EventBridge rule → Recovery Engine Lambda
             │
             ├── Compute delta
             ├── Post Delta Report
             └── (v2 auto mode) Trigger recovery handler
```

**Benefits**:
- No scheduled polling — responds immediately to state changes
- Zombie detection becomes reactive: heartbeat update triggers stream, absence of updates triggers alarm
- Decouples incident detection from checkpoint recovery — they can evolve independently

**Why deferred**: v1's incident-triggered scan is sufficient when failure volume is low. Stream processing adds operational complexity (DLQ, shard management, ordering guarantees) that isn't justified until checkpoint volume is high.

**Trigger**: Build when checkpoint table has >100 active checkpoints per hour, or when teams need sub-minute recovery detection latency.

---

## 7. SQS / Kafka / Kinesis Integration Patterns

**What**: Extend the checkpoint framework to support message-based workloads, not just batch API calls.

### 7a. SQS Integration

```
SQS Queue → Lambda (batch window)
       │
       ├── checkpoint.write_checkpoint(
       │     checkpoint_id=f"sqs:{queue}:{batch_id}",
       │     item_ids=[msg.message_id for msg in batch],
       │     mode="item_tracking",
       │ )
       │
       ├── Process messages
       │     checkpoint.mark_progress(item_id=msg.message_id)
       │
       ├── checkpoint.complete()
       └── batch_item_failures response (SQS partial batch)
```

**SQS-specific considerations**:
- SQS already has built-in retry via visibility timeout + DLQ
- Checkpoint adds visibility layer: "which messages in a batch failed?"
- Recovery handler re-drives from DLQ with checkpoint context
- `MessageDeduplicationId` (FIFO) = `{checkpoint_id}:{message_id}` for idempotency

### 7b. Kafka (MSK) Integration

```
MSK Topic → Lambda (ESM with batch)
       │
       ├── checkpoint.write_checkpoint(
       │     checkpoint_id=f"kafka:{topic}:{partition}:{offset_range}",
       │     total_items=batch_size,
       │     mode="index_based",    ← Kafka is inherently ordered
       │ )
       │
       ├── Process records
       │     checkpoint.mark_progress(index=offset)
       │
       ├── checkpoint.complete()
       └── ESM manages offset commit
```

**Kafka-specific considerations**:
- Use `index_based` mode — Kafka offsets are sequential
- Recovery = replay from `completed_index + 1` to end of batch
- Partition-level isolation: one checkpoint per partition per batch window
- Coordinate with ESM offset commit to avoid duplicate processing

### 7c. Kinesis Integration

```
Kinesis Stream → Lambda (ESM)
       │
       ├── checkpoint.write_checkpoint(
       │     checkpoint_id=f"kinesis:{stream}:{shard}:{sequence_range}",
       │     total_items=record_count,
       │     mode="index_based",
       │ )
       │
       ├── Process records
       │     checkpoint.mark_progress(index=i)
       │
       ├── checkpoint.complete()
       └── ESM manages iterator
```

**Kinesis-specific considerations**:
- Similar to Kafka — ordered, index-based
- Shard-level checkpointing (one checkpoint per shard per batch)
- Recovery interacts with Kinesis iterator management
- Enhanced fan-out for high-throughput recovery

### Integration Mode Selection

| Source | Checkpoint Mode | Recovery Model | Idempotency Mechanism |
|---|---|---|---|
| API batch | `item_tracking` | Invoke recovery handler with pending IDs | DynamoDB PutItem (same key = overwrite) |
| SQS | `item_tracking` | Re-drive from DLQ with context | `MessageDeduplicationId` (FIFO) |
| Kafka (MSK) | `index_based` | Replay from last committed offset | Consumer offset management |
| Kinesis | `index_based` | Replay from sequence number | Shard iterator + dedup |
| S3 event | `item_tracking` | Re-invoke with pending object keys | S3 ETag / version ID |

**Trigger**: Build when the first SQS/Kafka/Kinesis-backed service onboards to the SRE Platform and needs checkpoint-based recovery visibility.

---

## 8. Full CloudWatch Dashboard

**What**: A comprehensive CloudWatch dashboard showing checkpoint health across all services.

**Widgets**:

| Widget | Type | Source |
|---|---|---|
| Active Checkpoints by Service | Bar chart | `sre.checkpoint.created` - `sre.checkpoint.completed` |
| Pending Items (Total) | Single value | `sre.checkpoint.items_pending` |
| Recovery Success Rate | Line graph | `retry_triggered` vs `completed` over time |
| Average Recovery Duration | Line graph | Custom metric from audit log (v2.5) |
| Zombie Detection Rate | Line graph | `sre.checkpoint.zombie_detected` |
| Failed (Terminal) Checkpoints | Alarm widget | `sre.checkpoint.failed_terminal` |
| Retry Heatmap by Service | Heatmap | `retry_triggered` grouped by service dimension |
| Checkpoint Completion Rate | Pie chart | completed / (completed + failed + recovered) |

**Trigger**: Build when >3 services are using the checkpoint framework, making per-service monitoring insufficient.

---

## 9. Priority and Sequencing

| Priority | Enhancement | Dependency | Estimated Effort |
|---|---|---|---|
| **P1** | Auto-Recovery | v1 complete + operational confidence | Small (config flag + flow extension) |
| **P1** | Recovery Audit Log | v1 complete | Small (new table + write on each retry) |
| **P2** | Recovery Payload S3 Reference | Auto-Recovery or large batch onboarding | Small (conditional S3 upload) |
| **P2** | Full CloudWatch Dashboard | v1 metrics baseline | Medium (dashboard CDK + custom metrics) |
| **P3** | Parallel Recovery (Map State) | Auto-Recovery + large batch onboarding | Large (chunker, aggregator, partial failure) |
| **P3** | S3 Manifest Partitioning | Large batch onboarding (>50K items) | Medium (partitioned read/write) |
| **P3** | Event-Driven Recovery (Streams) | High checkpoint volume | Large (DynamoDB Streams + EventBridge) |
| **P4** | SQS/Kafka/Kinesis Integration | Service onboarding demand | Large per integration |

### Recommended Sequence

```
v1 GA (Delta Report + Retry)
  │
  ├─→ v2.0: Auto-Recovery + Audit Log        ← first services trusting auto-fix
  │
  ├─→ v2.1: Payload S3 Reference + Dashboard ← scaling beyond small batches
  │
  ├─→ v2.2: Parallel Recovery + Partitioning  ← large-scale batch services
  │
  └─→ v2.3: Event-Driven + Integrations       ← high-volume, multi-source
```

---

## 10. Migration from v1 to v2

The v1 → v2 transition is designed to be non-breaking:

| v2 Feature | Migration Path |
|---|---|
| Auto-Recovery | Set `auto_recover: true` in recovery catalog — no code change |
| Audit Log | New table, writes added to retry flow — no API change |
| Payload S3 Reference | Recovery handler adds `pending_items_uri` check — backward compatible |
| Parallel Recovery | New Step Function definition — existing recovery handlers work as chunk processors unchanged |
| Dashboard | Additive — new CDK construct, no changes to existing resources |
| Event-Driven | New DynamoDB Stream + EventBridge rules — existing scan path remains as fallback |

**Key principle**: Every v2 feature is additive. The v1 Delta Report + Retry Button continues to work exactly as before. v2 features layer on top.
