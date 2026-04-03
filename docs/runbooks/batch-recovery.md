# Runbook: Batch Processing Recovery

## Purpose

Operational procedures for managing batch processing failures in the Batch Insert API (`batch-processor-api-{stage}`). Covers automated recovery verification, manual intervention, and escalation paths.

**Related systems**: Batch Insert API, SRE Platform Pipeline, Step Function `batch-reprocess-{stage}`, DynamoDB `batch-transactions-{stage}`, Checkpoint Table `sre-checkpoints-{stage}`

---

## 1. How Batch Recovery Works

### Normal Flow (No Failure)
```
Client → POST /batch/insert {batch_id, txn_ids}
           │
           ├── checkpoint.write_checkpoint()          ← platform checkpoint
           ├── Write TXN records (one per item)
           │     └── checkpoint.mark_progress(txn_id) ← after each item
           ├── checkpoint.complete()                   ← all done
           └── Return 200 {status: completed}
```

### Failure + Automated Recovery Flow
```
Client → POST /batch/insert {batch_id, txn_ids}
           │
           ├── checkpoint.write_checkpoint()            ← checkpoint created
           ├── Write TXN#1..TXN#5                       ← partial success
           │     └── mark_progress() for each
           └── ⚡ Lambda timeout / error
                    │
           CloudWatch Alarm → SRE Platform
                    │
                    ├── Detection: Jira ticket created
                    ├── Triage: classified as "batch-timeout"
                    ├── Auto-resolve (transient failure)
                    └── Recovery engine (platform):
                              │
                    ├── Scan sre-checkpoints-{stage}: status=in_progress
                    ├── get_pending() → [txn-6..txn-10]
                    ├── Build enriched payload
                    └── Start Step Function → batch-recovery-{stage} Lambda
                              │
                    Recovery handler (application):
                    ├── Receives: {pending_items, metadata}
                    ├── Writes TXN#6..TXN#10 to batch-transactions-{stage}
                    ├── checkpoint.complete()
                    └── Returns summary
```

### Key Principle

The **platform checkpoint** (`sre-checkpoints-{stage}`) is the source of truth for recovery. It is written before any item processing begins. If the Lambda is killed at any point after the checkpoint write, the platform's recovery engine can determine:
- What was intended (`total_items` + `item_ids` in checkpoint)
- What was completed (`completed_items` in checkpoint)
- What is pending (`get_pending()` = item_ids - completed_items)

---

## 2. Identifying Batch Failures

### Check Platform Checkpoint Table

```bash
STAGE="dev"

# Scan for all in_progress checkpoints for the batch service
aws dynamodb query \
  --table-name sre-checkpoints-${STAGE} \
  --index-name service-status-index \
  --key-condition-expression "service = :svc AND #s = :ip" \
  --expression-attribute-names '{"#s": "status"}' \
  --expression-attribute-values '{":svc": {"S": "batch-processor-api-'${STAGE}'"}, ":ip": {"S": "in_progress"}}' \
  --projection-expression "checkpoint_id, total_items, #s, created_at"
```

### Check Specific Checkpoint

```bash
BATCH_ID="b-001"
STAGE="dev"
CHECKPOINT_ID="batch:batch-processor-api-${STAGE}:${BATCH_ID}"

# Get checkpoint details
aws dynamodb get-item \
  --table-name sre-checkpoints-${STAGE} \
  --key "{\"checkpoint_id\": {\"S\": \"${CHECKPOINT_ID}\"}}" \
  --query 'Item.{status:status.S,total_items:total_items.N,completed_items:completed_items.SS}'
```

### Check Application Data

```bash
BATCH_ID="b-001"
STAGE="dev"

# Count completed TXN records
aws dynamodb query \
  --table-name batch-transactions-${STAGE} \
  --index-name batch_id-index \
  --key-condition-expression "batch_id = :b" \
  --expression-attribute-values "{\":b\": {\"S\": \"${BATCH_ID}\"}}" \
  --select COUNT
```

### Check CloudWatch Logs

```bash
STAGE="dev"

# Recent errors from batch processor
aws logs tail /aws/lambda/batch-processor-api-${STAGE} --since 30m --filter-pattern "ERROR"

# Check if recovery Lambda ran
aws logs tail /aws/lambda/batch-recovery-${STAGE} --since 30m --filter-pattern "recovery"
```

---

## 3. Verifying Automated Recovery

After the SRE Platform triggers recovery, verify:

### Step 1: Check Step Function Execution

```bash
STAGE="dev"
SFN_ARN=$(aws lambda get-function-configuration \
  --function-name incident-triage-${STAGE} \
  --query 'Environment.Variables.REPROCESS_BATCH_WORKFLOW_ARN' --output text)

# List recent executions
aws stepfunctions list-executions \
  --state-machine-arn ${SFN_ARN} \
  --max-results 5 \
  --query 'executions[].{name:name,status:status,start:startDate}'
```

**Expected**: Most recent execution shows `SUCCEEDED`.

### Step 2: Check Recovery Handler Output

```bash
EXECUTION_ARN=$(aws stepfunctions list-executions \
  --state-machine-arn ${SFN_ARN} \
  --max-results 1 --query 'executions[0].executionArn' --output text)

aws stepfunctions describe-execution \
  --execution-arn ${EXECUTION_ARN} \
  --query '{status:status,output:output}'
```

**Expected output**:
```json
{
  "status": "SUCCEEDED",
  "output": "{\"status\": \"success\", \"processed_count\": 5, \"failed_count\": 0, \"details\": \"Reprocessed 5 items\"}"
}
```

### Step 3: Verify Checkpoint Status

```bash
BATCH_ID="b-001"
STAGE="dev"
CHECKPOINT_ID="batch:batch-processor-api-${STAGE}:${BATCH_ID}"

# Checkpoint should be completed
aws dynamodb get-item \
  --table-name sre-checkpoints-${STAGE} \
  --key "{\"checkpoint_id\": {\"S\": \"${CHECKPOINT_ID}\"}}" \
  --query 'Item.status.S'
# Expected: "completed"
```

### Step 4: Verify Data Integrity

```bash
BATCH_ID="b-001"
STAGE="dev"

# All TXN records should exist
aws dynamodb query \
  --table-name batch-transactions-${STAGE} \
  --index-name batch_id-index \
  --key-condition-expression "batch_id = :b" \
  --expression-attribute-values "{\":b\": {\"S\": \"${BATCH_ID}\"}}" \
  --select COUNT
# Expected: 10 TXN records
```

---

## 4. Manual Recovery

Use when automated recovery failed or was not triggered.

### 4a. Trigger Recovery Manually via Step Function

```bash
STAGE="dev"
SFN_ARN=$(aws lambda get-function-configuration \
  --function-name incident-triage-${STAGE} \
  --query 'Environment.Variables.REPROCESS_BATCH_WORKFLOW_ARN' --output text)

aws stepfunctions start-execution \
  --state-machine-arn ${SFN_ARN} \
  --name "manual-recovery-$(date +%s)" \
  --input '{"incident_key": "manual", "recovery_model": "reprocess", "execution_id": "manual-'$(date +%s)'"}'
```

The platform's recovery engine will scan `sre-checkpoints-{stage}` for ALL `in_progress` checkpoints and invoke the recovery handler with pending items.

### 4b. Recover a Specific Batch Manually

If the recovery engine or Step Function is unavailable:

```bash
BATCH_ID="b-001"
STAGE="dev"
CHECKPOINT_ID="batch:batch-processor-api-${STAGE}:${BATCH_ID}"
TABLE="batch-transactions-${STAGE}"
CHECKPOINT_TABLE="sre-checkpoints-${STAGE}"

# 1. Get checkpoint — shows what was intended and what was completed
CHECKPOINT=$(aws dynamodb get-item --table-name ${CHECKPOINT_TABLE} \
  --key "{\"checkpoint_id\": {\"S\": \"${CHECKPOINT_ID}\"}}")
echo "Checkpoint: ${CHECKPOINT}"

# 2. Extract item_ids and completed_items from checkpoint
# (Use the checkpoint data to determine pending items)
# item_ids = all intended items
# completed_items = items already processed
# pending = item_ids - completed_items

# 3. Write each pending item directly to application table
for TXN_ID in ${PENDING_IDS}; do
  echo "Writing: ${TXN_ID}"
  TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)
  TTL=$(python3 -c "import time; print(int(time.time()) + 86400)")
  aws dynamodb put-item --table-name ${TABLE} \
    --item "{
      \"txn_id\": {\"S\": \"TXN#${TXN_ID}\"},
      \"batch_id\": {\"S\": \"${BATCH_ID}\"},
      \"status\": {\"S\": \"processed\"},
      \"timestamp\": {\"S\": \"${TIMESTAMP}\"},
      \"ttl\": {\"N\": \"${TTL}\"}
    }"
done

# 4. Update checkpoint to completed
aws dynamodb update-item --table-name ${CHECKPOINT_TABLE} \
  --key "{\"checkpoint_id\": {\"S\": \"${CHECKPOINT_ID}\"}}" \
  --update-expression "SET #s = :c, updated_at = :ts" \
  --expression-attribute-names '{"#s": "status"}' \
  --expression-attribute-values "{\":c\": {\"S\": \"completed\"}, \":ts\": {\"S\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}}"

echo "Manual recovery complete for batch ${BATCH_ID}"
```

### 4c. Re-run the Entire Batch (Last Resort)

If the checkpoint is missing (Lambda died before writing it), re-invoke the Batch API with the known transaction IDs **without** the chaos flag:

```bash
STAGE="dev"
FUNCTION="batch-processor-api-${STAGE}"

aws lambda invoke \
  --function-name ${FUNCTION} \
  --payload '{
    "httpMethod": "POST",
    "path": "/batch/insert",
    "body": "{\"batch_id\": \"b-001-retry\", \"txn_ids\": [\"txn-1\",\"txn-2\",\"txn-3\",\"txn-4\",\"txn-5\",\"txn-6\",\"txn-7\",\"txn-8\",\"txn-9\",\"txn-10\"], \"force_partial_failure\": false}",
    "headers": {"Content-Type": "application/json"}
  }' /tmp/batch-response.json

cat /tmp/batch-response.json
```

**Warning**: This creates a NEW batch (b-001-retry) with a NEW checkpoint, not a recovery of the original. Use only when the original checkpoint is lost. The original records from b-001 will remain as orphans.

---

## 5. Troubleshooting

### Recovery Engine Found No Pending Work

**Symptom**: Step Function SUCCEEDED but `processed_count: 0`.

**Possible causes**:
1. **API Gateway timeout, Lambda finished**: All items were actually written. The 504 was misleading. Check the checkpoint — if `completed_items` contains all item_ids, this is the cause.
2. **Another recovery already ran**: Check Step Function execution history for a prior successful run.
3. **Checkpoint not written**: Lambda timed out before writing the checkpoint. No checkpoint exists — use manual recovery (4c).

### Recovery Handler Failed

**Symptom**: Step Function execution FAILED.

```bash
aws stepfunctions describe-execution \
  --execution-arn ${EXECUTION_ARN} \
  --query '{status:status,error:error,cause:cause}'
```

**Common causes**:
- **DynamoDB throttling**: Recovery writes too fast. Add exponential backoff or increase table capacity.
- **IAM permissions**: Recovery Lambda missing `dynamodb:PutItem` on `batch-transactions-{stage}` or `dynamodb:UpdateItem` on `sre-checkpoints-{stage}`.
- **Lambda timeout**: Recovery Lambda timeout too short for the number of pending items.

**Resolution**: Fix the root cause, then re-trigger (section 4a). Recovery is idempotent — safe to retry.

### Checkpoint Exists But Status Is Wrong

```bash
# Force-update checkpoint status to allow re-processing
aws dynamodb update-item --table-name sre-checkpoints-${STAGE} \
  --key "{\"checkpoint_id\": {\"S\": \"${CHECKPOINT_ID}\"}}" \
  --update-expression "SET #s = :s" \
  --expression-attribute-names '{"#s": "status"}' \
  --expression-attribute-values '{":s": {"S": "in_progress"}}'
```

Then trigger recovery (section 4a).

### Multiple Incomplete Checkpoints

```bash
# List all incomplete checkpoints for the batch service
aws dynamodb query \
  --table-name sre-checkpoints-${STAGE} \
  --index-name service-status-index \
  --key-condition-expression "service = :svc AND #s = :ip" \
  --expression-attribute-names '{"#s": "status"}' \
  --expression-attribute-values '{":svc": {"S": "batch-processor-api-'${STAGE}'"}, ":ip": {"S": "in_progress"}}' \
  --projection-expression "checkpoint_id, total_items, created_at"
```

Triggering recovery (section 4a) processes ALL incomplete checkpoints in a single execution.

---

## 6. Escalation

### When to Escalate

| Condition | Action |
|---|---|
| Automated recovery succeeded | No action needed — verify data integrity |
| Recovery failed once, retry succeeded | Monitor — may indicate intermittent issue |
| Recovery failed twice | Escalate to engineering — check DynamoDB capacity, IAM, Lambda config |
| Checkpoint missing (not written) | Escalate — need to determine original batch contents from caller/upstream |
| Data integrity mismatch after recovery | Escalate — possible DynamoDB consistency issue |
| Recovery causing downstream side effects | STOP — review recovery handler for unintended writes |

### Escalation Contacts

| Severity | Who | Channel |
|---|---|---|
| SEV-1 (data loss risk) | On-call engineer | PagerDuty + Slack #incidents |
| SEV-2 (recovery failed) | Service owner | Jira ticket (auto-created by SRE Platform) |
| SEV-3 (monitoring) | Team lead | Slack #batch-processing |

---

## 7. Monitoring

### CloudWatch Alarms

| Alarm | Condition | Action |
|---|---|---|
| `batch-processor-high-batch-failure-{stage}` | Error count > 0 in 1 min | Triggers incident pipeline |
| `batch-recovery-high-error-rate-{stage}` | Recovery Lambda errors > 0 | Alerts on-call — recovery itself is failing |

### Key Metrics to Watch

```bash
# Batch processor error rate
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --dimensions Name=FunctionName,Value=batch-processor-api-${STAGE} \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Sum

# Incomplete checkpoint count (custom metric — emitted by recovery engine)
# If this stays > 0 for extended periods, recovery is not completing
```

### Jira Ticket Review

Every batch failure creates a Jira ticket via the SRE Platform. Check:
- **Status**: Should be "Resolved" after automated recovery
- **Recovery comment**: Should show "Reprocessed N items" with checkpoint details
- **Attached logs**: Error log file from the batch processor Lambda
