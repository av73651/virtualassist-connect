# Incident Management — DynamoDB (Addendum)

> Extends `incident-management.md`. Covers DynamoDB-specific alarms, failure patterns, diagnostic approaches, and decision trees.

---

## ALARM DEFINITIONS

| Alarm Type | Metric / Namespace | Statistic | Direction | Threshold | Period |
|-----------|-------------------|-----------|-----------|-----------|--------|
| `read-throttle` | ReadThrottleEvents — AWS/DynamoDB | Sum | high | 0 | 60s × 3 |
| `write-throttle` | WriteThrottleEvents — AWS/DynamoDB | Sum | high | 0 | 60s × 3 |
| `read-latency` | SuccessfulRequestLatency (GetItem) — AWS/DynamoDB | p99 | high | 20ms | 60s × 5 |
| `write-latency` | SuccessfulRequestLatency (PutItem) — AWS/DynamoDB | p99 | high | 25ms | 60s × 5 |
| `system-errors` | SystemErrors — AWS/DynamoDB | Sum | high | 1 | 60s × 2 |
| `replication-latency` | ReplicationLatency — AWS/DynamoDB | Average | high | 5000ms | 300s × 3 |
| `stream-iterator-age` | IteratorAge — AWS/Lambda (stream consumer) | Max | high | 60000ms | 60s × 5 |
| `gsi-throttle` | ReadThrottleEvents (GSI) — AWS/DynamoDB | Sum | high | 0 | 60s × 3 |

### Severity Mapping (from `incident_config.json`)

```json
"dynamo-throttle": { "severity": "SEV-2", "recovery_model": "replay" }
```

---

## FAILURE MODE CLASSIFICATION

| Pattern | Indicators | Classification | Confidence |
|---------|-----------|---------------|------------|
| `dynamo_throttle_pattern` | ReadThrottleEvents or WriteThrottleEvents > 0 | `dynamo-capacity-exceeded` | high |
| Hot partition | Throttling on specific keys (Contributor Insights) | `hot-partition` | high |
| GSI throttle | GSI ThrottleEvents > 0, base table fine | `gsi-capacity-exceeded` | high |
| Provisioned capacity exhaustion | ConsumedRCU/WCU near ProvisionedRCU/WCU | `capacity-ceiling` | medium |
| Stream processing lag | IteratorAge increasing, consumer Lambda errors | `stream-consumer-failure` | high |
| Item size issue | ValidationException in consumer logs, large items | `item-size-limit` | medium |

---

## DIAGNOSTIC APPROACH

DynamoDB does not emit application logs to CloudWatch Logs. Diagnosis relies on:

1. **CloudWatch Metrics** — throttle events, latency, consumed capacity
2. **Contributor Insights** — identifies hot partition keys
3. **Consumer Lambda logs** — for stream processing failures (log group: `/aws/lambda/{consumer}-{stage}`)

**Consumer Lambda error query (stream processing):**
```
fields @timestamp, @message, @requestId
| filter @message like /ERROR|DynamoDBStreamError|ValidationException/
| parse @message '"error_type":"*"' as error_type
| sort @timestamp desc | limit 50
```

**Conditional check failure query (in calling Lambda):**
```
fields @timestamp, @message
| filter @message like /ConditionalCheckFailedException/
| stats count() as failures by bin(5m)
```

**Capacity utilization (CloudWatch Metrics Insights):**
```
SELECT AVG(ConsumedReadCapacityUnits), AVG(ProvisionedReadCapacityUnits),
       AVG(ConsumedWriteCapacityUnits), AVG(ProvisionedWriteCapacityUnits)
FROM "AWS/DynamoDB"
WHERE TableName = '{table-name}'
GROUP BY bin(5m)
```

---

## DECISION TREE

```
ALARM FIRES
│
├─ read-throttle / write-throttle
│   ├─ Contributor Insights shows hot key?
│   │   └─ HOT PARTITION → redesign partition key → ESCALATE
│   ├─ ConsumedCapacity near ProvisionedCapacity?
│   │   └─ CAPACITY CEILING → switch to on-demand or increase provisioned [MANUAL]
│   └─ Burst capacity exhausted (short spikes)?
│       └─ BURST EXHAUSTION → enable auto-scaling or switch to on-demand → ESCALATE
│
├─ gsi-throttle
│   └─ GSI provisioned capacity independent of base table
│       → increase GSI capacity or switch GSI to on-demand → ESCALATE
│
├─ read-latency / write-latency
│   ├─ Item sizes large (>4KB reads, >1KB writes)?
│   │   └─ ITEM SIZE → optimize data model, compress attributes → ESCALATE
│   ├─ Scan operations instead of Query?
│   │   └─ INEFFICIENT ACCESS → add GSI or change to Query → ESCALATE
│   └─ System errors also elevated?
│       └─ AWS SERVICE ISSUE → check AWS Health Dashboard → ESCALATE
│
├─ system-errors → AWS internal issue → monitor Health Dashboard → ESCALATE
│
├─ stream-iterator-age
│   ├─ Consumer Lambda erroring? → see Lambda addendum
│   ├─ Consumer Lambda throttled? → increase concurrency → see Lambda addendum
│   └─ Batch size too small? → increase batch size → ESCALATE
│
└─ replication-latency → global table replication lag
    → check source region health, item sizes → ESCALATE
```

---

## REMEDIATION ACTIONS

| Classification | Action | Auto | Trigger | Verify |
|---------------|--------|------|---------|--------|
| `dynamo-capacity-exceeded` | Switch to on-demand / increase provisioned | MANUAL | ReadThrottleEvents or WriteThrottleEvents > 0; ConsumedRCU/WCU near ProvisionedRCU/WCU | ThrottleEvents = 0, ConsumedCapacity well below provisioned or on-demand limit |
| `hot-partition` | Redesign partition key, add write sharding | MANUAL | Throttling on specific keys (Contributor Insights); uneven partition distribution | No per-key throttling, even distribution across partitions |
| `gsi-capacity-exceeded` | Increase GSI capacity | MANUAL | GSI ThrottleEvents > 0, base table fine; GSI capacity independent of base table | GSI ThrottleEvents = 0, GSI consumed capacity within limit |
| `stream-consumer-failure` | Fix consumer Lambda (delegate to Lambda addendum) | AUTO (via Lambda) | IteratorAge increasing, consumer Lambda errors or throttled | IteratorAge decreasing to near 0, consumer Lambda healthy |
| `capacity-ceiling` | Enable auto-scaling with target utilization 70% | MANUAL | ConsumedRCU/WCU consistently near ProvisionedRCU/WCU; burst credits exhausted | Auto-scaling active, utilization stable around target 70% |

---

## SERVICE-SPECIFIC GOTCHAS

**Provisioned vs on-demand**: Provisioned mode throttles when consumed > provisioned (after burst credits). On-demand mode auto-scales but costs more and has an initial ramp-up limit (previous peak or 50% above).

**GSI capacity is independent**: A GSI has its own provisioned capacity. Base table writes can succeed while GSI updates throttle, causing eventual consistency lag.

**Conditional writes and idempotency**: `ConditionalCheckFailedException` is expected in idempotent patterns (reserve-then-create). High volumes are normal for the incident-manager's `CorrelationRecord.reserve()` — don't alert on these.

**Item size limits**: Max 400KB per item. Approaching limits causes latency spikes on reads (RCU consumption = ceiling(item_size / 4KB)).

**Contributor Insights**: Must be enabled per table. Shows most-accessed and most-throttled partition keys. Essential for diagnosing hot partition issues.
