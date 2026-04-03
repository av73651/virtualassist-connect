---
name: incident-management-eventbridge
description: "EventBridge incident patterns — failed invocations, DLQ depth, rule failures, pattern mismatches."
---

# Incident Management — EventBridge (Addendum)

> Extends `incident-management.md`. Covers Amazon EventBridge-specific alarms, failure patterns, queries, and decision trees.

---

## ALARM DEFINITIONS

| Alarm Type | Metric / Namespace | Statistic | Direction | Threshold | Period |
|-----------|-------------------|-----------|-----------|-----------|--------|
| `failed-invocations` | FailedInvocations — AWS/Events | Sum | high | 1 | 60s × 3 |
| `throttled-rules` | ThrottledRules — AWS/Events | Sum | high | 0 | 60s × 3 |
| `dlq-depth` | ApproximateNumberOfMessagesVisible — AWS/SQS (DLQ) | Sum | high | 10 | 300s × 2 |
| `invocation-latency` | InvocationCreated to target execution — Custom | p99 | high | 5000ms | 60s × 5 |
| `matched-events` | MatchedEvents — AWS/Events | Sum | low | 50% below baseline | 300s × 3 |

### Context: EventBridge in the Incident Manager

The incident-manager uses EventBridge to orchestrate between Lambdas:
- Detection Lambda → publishes `IncidentCreated` event → triggers Triage Lambda
- Triage Lambda → publishes `TriageComplete` event → triggers Escalation Lambda

Source: `incident-manager` (from `incident_config.json: eventbridge_source`)

---

## FAILURE MODE CLASSIFICATION

| Pattern | Indicators | Classification | Confidence |
|---------|-----------|---------------|------------|
| Target permission error | FailedInvocations > 0 + target Lambda not invoked | `target-permission-error` | high |
| Target unavailable | FailedInvocations > 0 + target Lambda throttled or erroring | `target-failure` | high |
| Rule throttling | ThrottledRules > 0 | `rule-throttle` | high |
| DLQ accumulation | DLQ depth increasing over time | `dlq-depth-increasing` | high |
| Event pattern mismatch | MatchedEvents = 0 but source is publishing | `pattern-mismatch` | medium |
| Stale rule | Rule exists but target was deleted/changed | `stale-rule` | medium |

---

## DIAGNOSTIC QUERIES

**EventBridge does not emit logs by default.** Diagnosis relies on:

1. **CloudWatch Metrics** — FailedInvocations, ThrottledRules, MatchedEvents
2. **Target Lambda logs** — errors from the target function
3. **DLQ messages** — failed events land here with error details
4. **CloudTrail** — PutEvents API calls for audit

**Target Lambda error query** (log group: `/aws/lambda/{target-function}-{stage}`):
```
fields @timestamp, @message, @requestId
| filter @message like /ERROR|Exception/
| parse @message '"error_type":"*"' as error_type
| sort @timestamp desc | limit 50
```

**DLQ message inspection** (via SQS):
```bash
aws sqs receive-message \
  --queue-url {dlq-url} \
  --max-number-of-messages 5 \
  --attribute-names All \
  --message-attribute-names All
```

**Verify rule and targets:**
```bash
# List rules on the bus
aws events list-rules --event-bus-name default --name-prefix incident

# Check rule targets
aws events list-targets-by-rule --rule {rule-name}

# Test event pattern matching
aws events test-event-pattern \
  --event-pattern '{"source":["incident-manager"]}' \
  --event '{"source":"incident-manager","detail-type":"IncidentCreated","detail":{}}'
```

**CloudTrail audit (who published what):**
```
fields @timestamp, eventName, requestParameters.source, requestParameters.detailType
| filter eventSource = "events.amazonaws.com" and eventName = "PutEvents"
| sort @timestamp desc | limit 20
```

---

## DECISION TREE

```
ALARM FIRES
│
├─ failed-invocations
│   ├─ Target Lambda has permission to be invoked?
│   │   └─ NO → PERMISSION ERROR → fix resource-based policy → ESCALATE
│   ├─ Target Lambda erroring?
│   │   └─ YES → TARGET FAILURE → see Lambda addendum
│   ├─ Target Lambda throttled?
│   │   └─ YES → TARGET THROTTLE → increase Lambda concurrency → see Lambda addendum
│   └─ Target was deleted/moved?
│       └─ STALE RULE → update rule target ARN → ESCALATE
│
├─ throttled-rules
│   └─ Too many rules matching same event?
│       └─ RULE FANOUT → consolidate rules or request limit increase → ESCALATE
│
├─ dlq-depth
│   ├─ Messages are failed invocations?
│   │   └─ Inspect DLQ → fix target → redrive messages [MANUAL]
│   ├─ Messages are poison events (bad format)?
│   │   └─ POISON EVENT → fix publisher, purge bad messages → ESCALATE
│   └─ DLQ growing despite target being healthy?
│       └─ RETRY EXHAUSTION → check retry policy, increase retries → ESCALATE
│
├─ matched-events (low)
│   ├─ Source still publishing? (check PutEvents in CloudTrail)
│   │   └─ NO → SOURCE STOPPED → check source Lambda health → see Lambda addendum
│   └─ Event pattern changed?
│       └─ PATTERN MISMATCH → verify rule event pattern matches source → ESCALATE
│
└─ invocation-latency
    └─ Target Lambda cold starting?
        ├─ YES → see Lambda addendum (cold-start-rate)
        └─ NO → EventBridge service latency → monitor → ESCALATE
```

---

## REMEDIATION ACTIONS

| Classification | Action | Automation |
|---------------|--------|-----------|
| `target-permission-error` | Fix Lambda resource-based policy | MANUAL |
| `target-failure` | Delegate to Lambda addendum | AUTO (via Lambda) |
| `rule-throttle` | Consolidate rules, request limit increase | MANUAL |
| `dlq-depth-increasing` | Inspect, fix target, redrive DLQ | MANUAL |
| `pattern-mismatch` | Update event pattern on rule | MANUAL |
| `stale-rule` | Update or delete rule target | MANUAL |

**Proposed addition to `remediation_catalog`:**
```json
"dlq-depth-increasing": {
  "action": "eventbridge-redrive-dlq",
  "description": "Redrive failed events from DLQ back to EventBridge"
}
```

---

## SERVICE-SPECIFIC GOTCHAS

**Retry policy**: EventBridge retries failed invocations for up to 24 hours with exponential backoff by default. After exhaustion, events go to the DLQ (if configured) or are dropped silently. Always configure a DLQ.

**Event pattern matching is exact**: `{"detail-type": ["IncidentCreated"]}` will NOT match `{"detail-type": "incidentcreated"}`. Case-sensitive, no wildcards on field values (only prefix matching with `prefix`).

**PutEvents limit**: 10,000 entries per second per account per region (soft limit). Storm detection in the incident-manager (`storm_detection.threshold: 5` in `storm_detection.window_seconds: 120`) prevents flooding.

**Cross-account / cross-region**: If rules target resources in other accounts, both the rule and the target need explicit permissions. Missing cross-account permissions cause silent FailedInvocations.

**Archive and replay**: EventBridge can archive events and replay them. Use this for incident recovery instead of custom DLQ redrive when full event replay is needed.

**Ordering**: EventBridge does not guarantee ordering. If the incident-manager depends on `IncidentCreated` arriving before `TriageComplete`, design for idempotency and out-of-order handling (which is already implemented via `CorrelationRecord`).
