# Incident Management — AWS Lambda (Addendum)

> Extends `incident-management.md`. Covers Lambda-specific alarms, failure patterns, queries, and decision trees.

---

## ALARM DEFINITIONS

| Alarm Type | Metric / Namespace | Statistic | Direction | Threshold | Period |
|-----------|-------------------|-----------|-----------|-----------|--------|
| `error-rate` | Errors / Invocations — AWS/Lambda | Average | high | 5% | 60s × 3 |
| `throttle-count` | Throttles — AWS/Lambda | Sum | high | 10 | 60s × 2 |
| `duration-p99` | Duration — AWS/Lambda | p99 | high | 80% of timeout | 60s × 3 |
| `cold-start-rate` | Init Duration count / Invocations — Custom | Average | high | 30% | 300s × 2 |
| `concurrent-executions` | ConcurrentExecutions — AWS/Lambda | Max | high | 80% of reserved | 60s × 3 |
| `iterator-age` | IteratorAge — AWS/Lambda | Max | high | 60000ms | 60s × 5 |
| `memory-utilization` | MaxMemoryUsed / MemorySize — Custom | Average | high | 85% | 300s × 3 |
| `traffic` | Invocations — AWS/Lambda | Sum | low | 50% below baseline | 300s × 3 |

---

## FAILURE MODE CLASSIFICATION

| Pattern | Indicators | Classification | Confidence |
|---------|-----------|---------------|------------|
| `import_or_syntax_error` | `ImportError`, `SyntaxError`, `ModuleNotFoundError`; 100% error rate | `bad-deployment` | high |
| `single_error_dominant` | One error type > 70% of total errors | `specific-bug` | high |
| `throttling_errors` | `TooManyRequestsException`, `Rate exceeded` | `rate-limit` | high |
| `throttling_with_concurrency` | Throttle alarm + ConcurrentExecutions near limit | `concurrency-exhaustion` | high |
| `high_latency_no_errors` | Duration p99 breaching, error rate normal | `performance-degradation` | medium |
| `mixed_errors_recent_deploy` | Multiple error types within 15 min of deploy | `bad-deployment` | medium |
| `cold_start_spike` | Init Duration count > 3x baseline | `cold-start-storm` | medium |
| `timeout_chain` | `Task timed out after X seconds` | `timeout-exhaustion` | high |
| `oom_kill` | `Runtime.ExitError`, `signal: killed`, MaxMemoryUsed > 90% | `memory-exhaustion` | high |

---

## LOGS INSIGHTS QUERIES

**Error extraction with structured fields:**
```
fields @timestamp, @message, @logStream, @requestId
| filter @message like /ERROR|Error|Exception|Traceback/
| parse @message '"error_type":"*"' as error_type
| parse @message '"operation":"*"' as operation
| sort @timestamp desc | limit 100
```

**OOM detection:**
```
fields @timestamp, @memorySize, @maxMemoryUsed
| filter @type = "REPORT"
| filter @maxMemoryUsed / @memorySize > 0.90
| stats count() as near_oom, avg(@maxMemoryUsed) as avg_mem
```

**Timeout detection:**
```
fields @timestamp, @message, @duration
| filter @message like /Task timed out/
| stats count() as timeouts by bin(5m)
```

**Cold start analysis:**
```
fields @timestamp, @initDuration, @duration
| filter ispresent(@initDuration)
| stats count() as cold_starts, avg(@initDuration) as avg_init_ms, pct(@initDuration, 99) as p99_init_ms by bin(5m)
```

**Memory trend:**
```
fields @timestamp, @memorySize, @maxMemoryUsed
| filter @type = "REPORT"
| stats avg(@maxMemoryUsed / @memorySize * 100) as avg_pct by bin(5m)
```

---

## DECISION TREE

```
ALARM FIRES
│
├─ error-rate
│   ├─ 100% + ImportError/SyntaxError → rollback-lambda [AUTO]
│   ├─ Single error > 70% → collect samples, attach to Jira [AUTO] → ESCALATE
│   ├─ Runtime.ExitError / memory > 90% → increase-lambda-memory [AUTO]
│   ├─ "Task timed out" → check downstream dependencies → ESCALATE
│   └─ Mixed errors + recent deploy → rollback-lambda [AUTO]
│
├─ throttle-count
│   ├─ ConcurrentExecutions near limit → increase-concurrency [AUTO]
│   └─ Account-level → ESCALATE (AWS Support limit increase)
│
├─ duration-p99
│   ├─ Downstream latency → see DynamoDB/API Gateway addendum → ESCALATE
│   ├─ Memory near ceiling → increase-lambda-memory [AUTO]
│   └─ Code regression after deploy → rollback-lambda [AUTO]
│
├─ cold-start-rate → increase provisioned concurrency → ESCALATE
│
├─ traffic (low) → check upstream (API Gateway / EventBridge) → ESCALATE
│
└─ iterator-age → check consumer errors/throttling → fix or ESCALATE
```

---

## REMEDIATION ACTIONS

| Classification | Action | Auto | Trigger | Verify |
|---------------|--------|------|---------|--------|
| `bad-deployment` | `lambda-version-rollback` | AUTO | ImportError/SyntaxError at 100% error rate; mixed errors within 15 min of deploy | Error rate drops to 0%, alarm returns to OK, no new errors in 5 min |
| `performance-degradation` | `lambda-memory-increase` | AUTO | Runtime.ExitError + memory > 90%; duration p99 breaching with memory near ceiling | MaxMemoryUsed/MemorySize < 85%, duration p99 normalizes to baseline |
| `rate-limit` | `increase-concurrency` | AUTO | TooManyRequestsException/Rate exceeded; ConcurrentExecutions near reserved limit | Throttle count drops to 0, no new TooManyRequestsException |
| `concurrency-exhaustion` | `increase-concurrency` | AUTO | Throttle alarm + ConcurrentExecutions at reserved limit | Same as rate-limit |
| `memory-exhaustion` | `lambda-memory-increase` | AUTO | Runtime.ExitError, signal: killed, MaxMemoryUsed > 90% of configured memory | MaxMemoryUsed/MemorySize < 85%, no Runtime.ExitError |
| `timeout-exhaustion` | `increase-lambda-timeout` | MANUAL | Task timed out after X seconds; check downstream dependency latency first | Duration p99 within timeout, no timeout errors; verify downstream health |
| `cold-start-storm` | `increase-provisioned-concurrency` | MANUAL | Init Duration count > 3x baseline, latency p99 elevated from cold starts | Init Duration count returns to baseline, latency p99 normalizes |

---

## SERVICE-SPECIFIC GOTCHAS

**Timeout cascade**: API Gateway hard limit is 29s. Lambda timeout must be < 29s, downstream call timeout < Lambda timeout. Mismatch causes 504 to client while Lambda continues executing.

**Reserved vs unreserved concurrency**: A function with reserved concurrency throttles at its own limit even if account has spare capacity. A function without it competes for the shared unreserved pool.

**Stream-based Lambdas** (SQS, DynamoDB Streams, Kinesis): Use iterator-age alarm instead of error-rate. Batch failures need partial-batch-response analysis. See `incident-management-dynamodb.md` and `incident-management-eventbridge.md`.

**Alias rollback**: Always roll back the `live` alias (config: `lambda_alias_name`), not the function itself. Memory tiers are defined in `lambda_memory_tiers`.
