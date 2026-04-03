# Incident Management Pipeline -- Requirements

## Overview

Automated incident detection, self-healing, and escalation pipeline built as three independent Lambdas:

- **Leg 1 -- Detection Lambda**: Alarm fires -> cool-off check -> deduplication -> storm check -> create Jira incident -> emit event
- **Leg 2 -- Triage Lambda**: Log analysis -> root cause classification -> blast radius -> remediation attempt -> verify -> recovery workflow -> resolve or escalate
- **Leg 3 -- Escalation Lambda**: Enrich Jira ticket with full diagnostics -> notify engineer

The system tries to resolve incidents automatically before engaging a human. When escalation is necessary, the engineer receives a fully analyzed Jira ticket -- not raw logs.

**Key architectural decisions**:
- **3 independent Lambdas** (one per pipeline leg) for failure isolation and scoped permissions
- **Jira is the system of record** -- owns full incident lifecycle, diagnostics, and history
- **DynamoDB is minimal** -- correlation and idempotency only (incident_key -> jira_ticket_id)
- **EventBridge** for event-driven orchestration between Lambdas
- **Incident storm detection** -- disables automation when many alarms fire simultaneously
- **Recovery models** -- classifies incidents by what needs fixing after service restoration (stateless, replay, reprocess, data-correction, backlog-drain); triggers external recovery workflows
- **Externalized configuration** -- operational tuning in `incident_config.json`, workflow logic in code

## Actors

| Actor | Description |
|-------|-------------|
| CloudWatch Alarm | Triggers pipeline on threshold breach or recovery |
| Detection Lambda | Leg 1: processes SNS alarm events, creates Jira incidents, publishes IncidentCreated |
| Triage Lambda | Leg 2: analyzes, remediates, verifies; publishes EscalationRequired or IncidentAutoResolved |
| Escalation Lambda | Leg 3: enriches Jira, notifies engineer |
| Support Engineer | Engaged only after self-healing fails; receives analyzed Jira ticket |
| Jira (API Service Desk) | System of record -- incident lifecycle, diagnostics, history |
| DynamoDB | Correlation store -- incident_key -> jira_ticket_id, idempotency, storm detection |
| EventBridge | Workflow orchestration between pipeline legs |

## Incident Lifecycle & Status Flow

```
ALARM fires
  -> Detection Lambda:
    -> cool-off check (transient? -> log, skip)
    -> deduplication (existing? -> add Jira comment, skip)
    -> reserve incident_key in DynamoDB (RESERVED)
    -> create Jira incident
    -> update DynamoDB with jira_ticket_id (DETECTED)
    -> storm detection check
    -> publish IncidentCreated to EventBridge (includes storm_detected flag + recovery_model)

  -> Triage Lambda (EventBridge: IncidentCreated):
    -> update DynamoDB (TRIAGING)
    -> analyze logs, classify root cause, assess blast radius
    -> update Jira with analysis
    +-- storm detected:
    |     -> publish EscalationRequired (reason: "incident-storm")
    +-- no remediation available:
    |     -> publish EscalationRequired (reason: "no-remediation-available")
    +-- remediation available:
          -> execute single remediation attempt
          -> wait verification period
          -> 3-point verification
            +-- all pass:
            |     -> determine recovery model (from IncidentCreated event)
            |     -> trigger recovery workflow if not stateless
            |     -> Jira: resolved (with recovery action), DynamoDB: GRACE (15-min TTL)
            |     -> publish IncidentAutoResolved (includes recovery_model, recovery_status)
            +-- any fail:
                  -> publish EscalationRequired (reason: "verification-failed")

  -> Escalation Lambda (EventBridge: EscalationRequired):
    -> update DynamoDB (ESCALATED)
    -> enrich Jira with diagnostics, logs, links, commands
    -> notify engineer via SNS (SEV-1/SEV-2 only)

ALARM recovers (OK)
  -> Detection Lambda:
    -> lookup incident_key in DynamoDB
    -> not found -> log, skip
    -> collect resolution-time diagnostics (recovery logs, health check)
    -> update Jira: resolved (with resolution comment + attached logs)
    -> delete DynamoDB record

Grace period recurrence:
  -> Detection Lambda detects GRACE record for same incident_key
    -> reopen incident in Jira
    -> DynamoDB: GRACE -> DETECTED (fresh 24h TTL)
    -> publish EscalationRequired (reason: "grace-period-recurrence")
```

### DynamoDB Status Values

| Status | Meaning | Set By |
|--------|---------|--------|
| `RESERVED` | Placeholder before Jira ticket creation (race-condition guard) | Detection Lambda |
| `DETECTED` | Incident confirmed, Jira ticket created, triage pending | Detection Lambda |
| `TRIAGING` | Triage Lambda is actively processing | Triage Lambda |
| `ESCALATED` | Engineer escalation in progress | Escalation Lambda |
| `GRACE` | Auto-resolved; 15-minute recurrence detection window (TTL = resolved_at + 900s) | Triage Lambda |

---

# LEG 1 -- INCIDENT DETECTION & CREATION

Triggered when a CloudWatch alarm transitions to ALARM state via SNS. Goal: confirm the alarm is real, deduplicate, detect storms, create Jira incident. No human engaged yet.

## Functional Requirements -- Leg 1

### FR-001: Alarm Ingestion via SNS
The Detection Lambda SHALL accept CloudWatch Alarm state change notifications via a shared SNS topic. Any service stack's alarms can publish to this topic.

### FR-002: Severity and Recovery Model Classification (Externalized)
The Detection Lambda SHALL classify incident severity and recovery model from the alarm name using the `severity_mapping` in `incident_config.json`:

```json
{
  "severity_mapping": {
    "error-rate": {"severity": "SEV-1", "recovery_model": "stateless"},
    "latency": {"severity": "SEV-2", "recovery_model": "stateless"},
    "4xx-errors": {"severity": "SEV-3", "recovery_model": "stateless"},
    "queue-backlog": {"severity": "SEV-2", "recovery_model": "replay"},
    "batch-failure": {"severity": "SEV-1", "recovery_model": "reprocess"},
    "data-integrity": {"severity": "SEV-1", "recovery_model": "data-correction"},
    "throttle": {"severity": "SEV-2", "recovery_model": "backlog-drain"},
    "concurrency": {"severity": "SEV-1", "recovery_model": "backlog-drain"},
    "dynamo-throttle": {"severity": "SEV-2", "recovery_model": "replay"},
    "traffic": {"severity": "SEV-1", "recovery_model": "stateless"},
    "cold-start-rate": {"severity": "SEV-2", "recovery_model": "stateless"}
  }
}
```

Each alarm type maps to both a severity level and a recovery model. The recovery model determines what needs to happen *after* service restoration. New mappings are added to the config file without code changes.

**Golden Signals coverage**:

| Golden Signal | Alarm Types | Direction |
|---|---|---|
| **Errors** | `error-rate`, `4xx-errors`, `batch-failure`, `data-integrity` | high |
| **Latency** | `latency`, `cold-start-rate` | high |
| **Saturation** | `throttle`, `concurrency`, `dynamo-throttle`, `queue-backlog` | high |
| **Traffic** | `traffic` | low (drop detection) |

### FR-003: Service and Environment Identification
The Detection Lambda SHALL extract metadata from the alarm name convention:

`{service}-{high|low}-{type}-{stage}`

The threshold direction (`high` or `low`) indicates whether the alarm fires on an upper or lower threshold breach:
- `high` — metric exceeded upper threshold (errors, latency, throttles, cold starts)
- `low` — metric dropped below lower threshold (traffic drops, invocation drops)

Examples:
- `calculator-high-error-rate-prod` — error rate exceeded threshold
- `calculator-low-traffic-prod` — invocation count dropped below threshold
- `calculator-high-throttle-prod` — Lambda throttles exceeded threshold
- `calculator-high-cold-start-rate-prod` — cold start rate exceeded threshold

Captured attributes: service name, alarm type, deployment stage. These construct the `incident_key` (`{service}-{alarm_type}-{stage}`).

The Detection Lambda SHALL also extract from the CloudWatch Alarm SNS message:
- **Alarm ARN** (`AlarmArn` field): full CloudWatch alarm ARN for direct linking
- **Trigger dimensions** (`Trigger.Dimensions` array): metric dimensions including `FunctionName` (the Lambda function that triggered the alarm)

The `FunctionName` dimension identifies the exact Lambda source (e.g., `calculator-api-prod`) and is propagated to Jira tickets and EventBridge events.

### FR-004: Cool-Off Stabilization Check
The Detection Lambda SHALL re-check alarm state after a configurable cool-off period to filter transient spikes.

- Cool-off periods per severity (from `incident_config.json`):
  - SEV-1: 30 seconds
  - SEV-2: 60 seconds
  - SEV-3: 120 seconds
- If alarm returned to OK during cool-off, log as transient and skip.
- If alarm still active, proceed with incident creation.
- The cool-off check uses the CloudWatch `describe-alarms` API.

### FR-005: Incident Deduplication
The Detection Lambda SHALL prevent duplicate incidents for the same active alarm.

- Check DynamoDB for an existing record with the same `incident_key`.
- If record exists with `jira_ticket_id`: add comment to existing Jira ticket, skip creation.
- If no record exists: proceed to reserve-then-create.
- **Race condition protection**: DynamoDB conditional writes (`attribute_not_exists(incident_key)`) serialize concurrent Lambda invocations.

### FR-006: Reserve-Then-Create Pattern
The Detection Lambda SHALL use a two-phase write to prevent duplicate Jira tickets:

1. **Reserve**: Write placeholder to DynamoDB (`status: RESERVED`, `jira_ticket_id: null`) with `attribute_not_exists(incident_key)` condition.
2. **Create**: Create Jira incident ticket -> returns `jira_ticket_id`.
3. **Update**: Update DynamoDB record with `jira_ticket_id`, `status: DETECTED`.

**Conflict handling** (conditional write fails):
- `RESERVED` (no jira_ticket_id):
  - If `created_at` age > `reservation_timeout_seconds` (default: 180s): stale reservation — delete and retry reserve-then-create (one retry only).
  - If fresh: another Lambda is creating the ticket -> exit silently.
- `DETECTED`/`TRIAGING`/`ESCALATED` (jira_ticket_id exists): add duplicate comment to existing Jira ticket -> exit.
- `GRACE` (jira_ticket_id exists): handle per grace period rules (FR-016).

**Jira creation failure**: delete reserved DynamoDB record, log error, rely on SNS retry or DLQ.

### FR-007: Incident Storm Detection
The Detection Lambda SHALL detect incident storms (dependency failure causing many alarms simultaneously).

- Count DynamoDB records where `created_at > now - storm_window_seconds` (via GSI).
- If count exceeds `storm_threshold` (from `incident_config.json`):
  - `storm_detected = true`
  - Incident is still created (Jira ticket + DynamoDB record)
  - IncidentCreated event includes `storm_detected: true` and `active_incident_count`
  - Triage Lambda skips automated remediation and escalates directly.

Default thresholds (configurable): `storm_threshold: 5`, `storm_window_seconds: 120`.

### FR-008: Jira Incident Creation
The Detection Lambda SHALL create a Jira incident ticket with:

- **Summary**: `[SEV-X] {service} ({stage}): {alarm description}`
- **Priority**: SEV-1->Highest, SEV-2->High, SEV-3->Medium
- **Labels**: `incident`, `automated`, `{service}`, `{stage}`
- **Description**: Includes incident metadata with:
  - Lambda function name (from alarm trigger dimensions, e.g., `calculator-api-prod`)
  - Alarm ARN (direct link to CloudWatch alarm)
  - "Incident detected. Automated triage in progress..."
- **Custom field**: `incident_key` for correlation
- **Comment**: "Incident detected at {timestamp}. Source: {function_name}. Automated analysis starting."

### FR-009: EventBridge Event Publishing
The Detection Lambda SHALL publish `IncidentCreated` to EventBridge after successful incident creation:

```json
{
  "source": "sre.incident-detection",
  "detail-type": "IncidentCreated",
  "detail": {
    "incident_key": "payments-error-rate-prod",
    "jira_ticket_id": "INC-142",
    "service": "payments",
    "function_name": "payments-api-prod",
    "stage": "prod",
    "severity": "SEV-1",
    "recovery_model": "stateless",
    "storm_detected": false,
    "timestamp": "2026-03-30T10:15:00Z"
  }
}
```

### FR-010: Scalable Onboarding
New services SHALL onboard by adding a single alarm action pointing to the shared SNS topic. No changes to the incident manager Lambdas required.

---

# LEG 2 -- AUTOMATED TRIAGE & SELF-HEALING

Triggered by EventBridge `IncidentCreated` event. Goal: analyze the problem, classify root cause, assess blast radius, attempt self-healing. If resolved, transition to GRACE. If not, escalate.

## Functional Requirements -- Leg 2

### FR-011: Log Collection and Error Analysis
The Triage Lambda SHALL collect error logs from the affected service and produce structured analysis.

**Bounded analysis** (from `incident_config.json`): `window_minutes: 15`, `max_events: 500`. If log volume exceeds the limit, analyze most recent events and note truncation.

The log group is derived from the Lambda function name (`/aws/lambda/{function_name}`) when available from alarm trigger dimensions, ensuring logs are collected from the exact source Lambda.

Analysis outputs:
- **Error summary**: Total count, errors grouped by type, top error messages
- **Error timeline**: Error rate over 1-minute buckets (spike vs sustained)
- **Affected operations**: Failing API endpoints/operations
- **Affected users**: Distinct `user_id` count from error logs
- **Sample errors**: Up to 5 full error entries with stack traces
- **Sample payloads**: Up to 5 error-triggering request/event payloads extracted from structured logs (the input event or request body that caused each failure). Requires source Lambdas to log incoming events via the `@observe` decorator or structured logging.

### FR-012: Root Cause Classification (Externalized Rules)
The Triage Lambda SHALL classify root cause using rules from `incident_config.json`:

```json
{
  "classification_rules": [
    {"pattern": "import_or_syntax_error", "classification": "bad-deployment", "confidence": "high"},
    {"pattern": "single_error_dominant", "classification": "specific-bug", "confidence": "high"},
    {"pattern": "throttling_errors", "classification": "rate-limit", "confidence": "high"},
    {"pattern": "auth_errors", "classification": "auth-issue", "confidence": "high"},
    {"pattern": "high_latency_no_errors", "classification": "performance-degradation", "confidence": "medium"},
    {"pattern": "mixed_errors_recent_deploy", "classification": "bad-deployment", "confidence": "medium"},
    {"pattern": "spike_then_stable", "classification": "transient-spike", "confidence": "medium"},
    {"pattern": "throttling_with_concurrency", "classification": "concurrency-exhaustion", "confidence": "high"},
    {"pattern": "dynamo_throttle_pattern", "classification": "dynamo-capacity-exceeded", "confidence": "high"},
    {"pattern": "traffic_drop", "classification": "upstream-outage", "confidence": "medium"},
    {"pattern": "cold_start_spike", "classification": "cold-start-storm", "confidence": "medium"}
  ]
}
```

New classification rules added to config without code changes. Classification is deterministic, reproducible, and auditable.

### FR-013: Blast Radius Assessment
The Triage Lambda SHALL assess incident impact:

- Affected endpoints, affected users (distinct count), error rate (current vs baseline), duration.
- Summary format: `Impact: {X} users affected, {Y}% error rate on {endpoints} for {duration}`

### FR-014: Automated Remediation (Externalized Catalog, Multi-Service)
The Triage Lambda SHALL attempt self-healing based on root cause classification and service type.

**Single attempt constraint**: At most ONE remediation attempt per incident. This prevents automation loops.

**Triage timeout guardrail**: If triage elapsed time exceeds `triage_timeout_seconds` (default: 120s from config), skip remaining steps (remediation, verification, recovery) and escalate with reason `"triage-timeout"`. Analysis work already done is preserved in Jira. This prevents Lambda timeout from silently losing progress.

**Storm override**: When `storm_detected = true`, skip remediation entirely and escalate with reason `"incident-storm"`. Analysis still runs -- engineers receive full diagnostics.

**Service type detection**: The `service_type` is derived from the CloudWatch alarm's `Trigger.Namespace` at detection time and propagated through the IncidentCreated event:

| Namespace | Service Type |
|-----------|-------------|
| `AWS/Lambda`, `Custom/Lambda` | `lambda` |
| `AWS/ApiGateway` | `api-gateway` |
| `AWS/ES`, `AWS/OpenSearch` | `elasticsearch` |

**Skill-file-driven remediation**: Each service type has a JSON skill file (`src/services/remediation/skills/{service_type}.json`) that describes its available remediation actions, the integration method to call, and what parameters to extract from the resource context. A generic `RemediationEngine` reads these skill files and dispatches remediation. Adding a new service type requires only a new skill file and the corresponding repository methods -- zero engine changes.

**Remediation lookup**: Match `service_type` and `root_cause` against the nested `remediation_catalog` in `incident_config.json`:

```json
{
  "remediation_catalog": {
    "lambda": {
      "bad-deployment": {"action": "lambda-version-rollback"},
      "performance-degradation": {"action": "lambda-memory-increase"},
      "rate-limit": {"action": "increase-concurrency"},
      "concurrency-exhaustion": {"action": "increase-concurrency"}
    },
    "api-gateway": {
      "bad-deployment": {"action": "apigw-deployment-rollback"},
      "rate-limit": {"action": "apigw-throttle-increase"}
    },
    "elasticsearch": {
      "performance-degradation": {"action": "opensearch-scale-up"},
      "storage-exhaustion": {"action": "opensearch-storage-increase"}
    }
  }
}
```

No catalog match for the service_type + root_cause -> publish `EscalationRequired` with reason `"no-remediation-available"`.

**Remediation actions**:

| Service Type | Action | Description |
|-------------|--------|-------------|
| `lambda` | `lambda-version-rollback` | Revert Lambda to previous published version |
| `lambda` | `lambda-memory-increase` | Increase memory by one tier (e.g., 512->1024 MB) |
| `lambda` | `increase-concurrency` | Increase Lambda reserved concurrency |
| `api-gateway` | `apigw-deployment-rollback` | Revert API Gateway stage to previous deployment |
| `api-gateway` | `apigw-throttle-increase` | Increase API Gateway stage throttle limits |
| `elasticsearch` | `opensearch-scale-up` | Scale up OpenSearch instance type or count |
| `elasticsearch` | `opensearch-storage-increase` | Increase OpenSearch EBS volume size |

**Verification wait** (from `incident_config.json`): SEV-1: 60s, SEV-2: 90s, SEV-3: 120s.

**3-point verification**:
1. Alarm state check (CloudWatch `describe-alarms` -> OK)
2. Health check (endpoint health check against affected service)
3. Error rate check (last 2 min of logs, error count below threshold)

All pass -> auto-resolution (FR-015). Any fail -> publish `EscalationRequired` with reason `"verification-failed"`.

New service types added via skill files + repository methods without engine changes. New remediation strategies for existing service types added to config without code changes.

### FR-015: Auto-Resolution
When 3-point verification passes, the Triage Lambda SHALL:

1. Collect resolution evidence (duration, action taken, verification results, resolution logs)
2. Determine recovery model (from IncidentCreated event detail)
3. If recovery model is not `stateless`: trigger recovery workflow (FR-015a)
4. Update Jira ticket with resolution comment, recovery action, and attach resolution logs
5. Transition Jira ticket to resolved status
6. Update DynamoDB: `status -> GRACE`, `ttl = resolved_at + grace_period_seconds` (default: 900s / 15 min)
7. Publish `IncidentAutoResolved` to EventBridge (includes `recovery_model` and `recovery_status`)
8. No engineer notification for auto-resolved incidents

### FR-015a: Recovery Model Classification and Workflow Triggering
The Triage Lambda SHALL classify incidents by recovery model and trigger appropriate recovery workflows after successful service remediation.

**Recovery models**:

| Recovery Model | What Needs Fixing | Example Failure | Recovery Action |
|----------------|-------------------|-----------------|-----------------|
| `stateless` | Nothing -- just restore the service | API error spike, deployment bug | No recovery action |
| `replay` | Replay lost events/messages | DLQ backlog, consumer crash | Trigger DLQ replay workflow |
| `reprocess` | Rerun failed jobs/workflows | ETL failure, batch settlement | Trigger batch rerun workflow |
| `data-correction` | Repair incorrect data | Duplicate transactions, partial updates | Trigger reconciliation workflow |
| `backlog-drain` | Scale consumers to drain queue | Traffic spike, dependency slowdown | Trigger consumer scaling |

**Key design principle**: The incident system is a control plane for recovery. It orchestrates but NEVER processes business data itself. Impacted records remain in their source systems (DLQs, retry queues, staging tables, event logs).

**Recovery catalog** (externalized in `incident_config.json`):

```json
{
  "recovery_catalog": {
    "replay": {
      "type": "step_function",
      "workflow_arn_env": "REPLAY_DLQ_WORKFLOW_ARN",
      "description": "Replay unprocessed messages from DLQ"
    },
    "reprocess": {
      "type": "step_function",
      "workflow_arn_env": "REPROCESS_BATCH_WORKFLOW_ARN",
      "description": "Rerun failed batch job or ETL pipeline"
    },
    "data-correction": {
      "type": "step_function",
      "workflow_arn_env": "RECONCILIATION_WORKFLOW_ARN",
      "description": "Trigger data reconciliation workflow"
    },
    "backlog-drain": {
      "type": "lambda",
      "function_name_env": "BACKLOG_DRAIN_FUNCTION_NAME",
      "description": "Scale consumers to drain accumulated backlog"
    }
  }
}
```

**Recovery workflow triggering**:
- `type: step_function`: Start Step Functions execution with incident context as input
- `type: lambda`: Invoke Lambda asynchronously with incident context as payload
- Workflow ARNs / function names are passed via Lambda environment variables (referenced by `*_env` keys in config)
- Recovery trigger result (execution ARN, status) recorded in Jira comment
- Recovery workflow failure does NOT block auto-resolution -- it is logged in Jira and the incident is still resolved

**Recovery workflow idempotency**: All recovery triggers SHALL include idempotency keys in the payload: `incident_key`, `jira_ticket_id`, and a unique `execution_id` (UUID). Recovery workflows MUST detect duplicate executions using these keys to prevent double-replay, double-reprocessing, or duplicate data corrections on triage retries. For Step Functions, the `execution_id` is used as the execution name for built-in deduplication.

**Idempotency ownership boundary**: The incident system (provider) is responsible for generating and passing idempotency keys. Recovery workflow owners (consumers) are responsible for implementing dedup using their runtime's native mechanism — Step Functions uses execution name dedup; Lambda-based workflows should check against their own state store (e.g., DynamoDB conditional write on execution_id). There is no centralized idempotency library; each recovery workflow uses the mechanism natural to its runtime.

**Where impacted records live** (NOT in the incident system):

| Failure Type | Where Impacted Records Live |
|-------------|----------------------------|
| Queue processing failure | DLQ / message queue |
| Batch processing failure | Job staging tables / checkpoints |
| Streaming pipeline failure | Event log / Kafka / Kinesis |
| Partial transaction failure | Operational database |
| Integration failure | Retry queue |

New recovery workflows are added to the catalog without code changes.

### FR-016: Grace Period Recurrence Detection
After auto-resolution, the DynamoDB record transitions to `GRACE` status with 15-minute TTL.

If the same alarm fires again while a `GRACE` record exists:
- Detection Lambda skips cool-off and remediation
- Reopens incident in Jira
- Updates DynamoDB: `GRACE -> DETECTED` with fresh 24-hour TTL
- Publishes `EscalationRequired` with reason `"grace-period-recurrence"`

This prevents remediation loops for flapping alarms.

### FR-017: Jira Status Updates
Every processing step in Leg 2 SHALL update Jira with timestamped comments:

- Triage started: "Analyzing logs... collecting error data."
- Analysis complete: "Root cause classified as {classification} ({confidence}). Blast radius: {summary}."
- Remediation started: "Attempting remediation: {action}."
- Verification started: "Remediation executed. Waiting {X}s for verification..."
- Auto-resolved: "All verification checks passed. Incident auto-resolved. Duration: {X}m."
- Verification failed: "Verification failed ({which checks}). Escalating."
- No remediation: "No automated remediation available for {classification}. Escalating."
- Storm escalation: "Incident storm detected ({N} active incidents). Skipping automation, escalating."

---

# LEG 3 -- ENGINEER ESCALATION & RESOLUTION

Triggered by EventBridge `EscalationRequired` event. Goal: enrich Jira ticket with all diagnostics so the engineer can act immediately.

## Functional Requirements -- Leg 3

### FR-018: Jira Ticket Enrichment
The Escalation Lambda SHALL update the Jira ticket with full diagnostic context. The engineer SHALL NOT need to download logs or run scripts to begin investigation.

**Ticket description updated with**:
- Incident metadata (key, service, **Lambda function name**, stage, severity, alarm ARN, duration)
- Escalation reason (verification-failed, no-remediation-available, incident-storm, grace-period-recurrence)
- Root cause classification and confidence level
- Blast radius assessment
- Remediation actions attempted and outcomes
- **Sample error-triggering payloads** (up to 5 request/event bodies that caused failures)

**Attached to the ticket**:
- Error log extract (`error-logs-{timestamp}.txt`)
- Error-triggering payloads (`error-payloads-{timestamp}.txt`) — request/event bodies from failed invocations
- Top failing request traces (`request-traces-{timestamp}.txt`)
- Error timeline and trend data

**Links included**:
- CloudWatch dashboard (direct URL for the service)
- X-Ray trace console (filtered by service and time window)
- CloudWatch Logs Insights (pre-built query)
- Runbook: `docs/runbooks/{service}-debug.md`

**Investigation commands (copy-paste ready)**:
```
./scripts/incident/download-logs.sh --stage {stage} --service {service} --minutes 30
./scripts/incident/trace-lookup.sh --stage {stage} --correlation-id {sample-trace-id}
./scripts/incident/health-check.sh --stage {stage}
```

### FR-019: Engineer Notification
The Escalation Lambda SHALL send SNS notification for SEV-1 and SEV-2 incidents only:

- Incident key and severity
- Escalation reason
- Root cause classification
- Blast radius summary
- Jira ticket link (with diagnostics already attached)
- Time elapsed since alarm triggered

SEV-3 incidents are tracked via enriched Jira ticket only (no notification).

### FR-020: Resolution Tracking (Alarm Recovery)
The Detection Lambda SHALL process alarm recovery (OK state):

1. Lookup `incident_key` in DynamoDB -> not found -> log, skip
2. Collect resolution-time diagnostics:
   - Recovery logs (recent logs around state change)
   - Health check (confirm alarm state is OK)
3. Update Jira ticket: resolved (with resolution comment + attached recovery logs)
4. Delete DynamoDB record immediately

Jira retains the full audit trail. DynamoDB record is removed on resolution.

---

# SHARED REQUIREMENTS

## DynamoDB Correlation Table

**Design principle**: DynamoDB is a correlation and idempotency store only. Jira is the system of record. Lambdas delete DynamoDB records on resolution; historical data lives in Jira.

**Table**: `incident_correlation`
**Partition key**: `incident_key`

| Attribute | Type | Purpose |
|-----------|------|---------|
| `incident_key` | String (PK) | Correlation key: `{service}-{alarm_type}-{stage}` |
| `jira_ticket_id` | String | Jira ticket key (e.g., `INC-142`); null during RESERVED |
| `severity` | String | SEV-1, SEV-2, or SEV-3 |
| `status` | String | `RESERVED`, `DETECTED`, `TRIAGING`, `ESCALATED`, `GRACE` |
| `created_at` | String (ISO 8601) | When the incident was created |
| `ttl` | Number (epoch) | Auto-expiry; see TTL rules below |

**GSI**: `created_at-index` (partition key: fixed `"ALL"`, sort key: `created_at`) -- enables storm detection time-range queries.

**TTL rules**:

| Status | TTL Value | Purpose |
|--------|-----------|---------|
| `RESERVED`, `DETECTED`, `TRIAGING`, `ESCALATED` | created_at + 24 hours | Auto-cleanup if alarm never recovers |
| `GRACE` | resolved_at + 900 seconds (15 min) | Recurrence window after auto-resolution |

- Active record TTL is set at creation and never updated.
- On auto-resolution, record transitions to `GRACE` with TTL = resolved_at + 900s.
- On manual resolution (alarm OK recovery), the DynamoDB record is deleted immediately.
- No record is retained beyond its TTL; Jira is the audit trail.

## EventBridge Event Contracts

| Event | Publisher | Consumer | Trigger |
|-------|-----------|----------|---------|
| `IncidentCreated` | Detection Lambda | Triage Lambda | New incident needs analysis |
| `EscalationRequired` | Triage Lambda | Escalation Lambda | Self-healing failed or unavailable |
| `IncidentAutoResolved` | Triage Lambda | (logged, no consumer) | Self-healing succeeded; audit trail |

Events carry `incident_key`, `jira_ticket_id`, and minimal metadata. Consuming Lambdas read full state from Jira and DynamoDB.

`EscalationRequired` includes a `reason` field with valid values: `verification-failed`, `no-remediation-available`, `incident-storm`, `grace-period-recurrence`, `triage-timeout`.

## Externalized Configuration

All operational tuning lives in `incident_config.json`, loaded once at Lambda cold start:

| Config | Purpose | Why Externalized |
|--------|---------|-----------------|
| `severity_mapping` | Alarm type -> {severity, recovery_model} | Teams reclassify and assign recovery strategies without code changes |
| `cool_off_seconds` | Per-severity cool-off periods | Operations tunes based on alarm behavior |
| `classification_rules` | Log pattern -> root cause | Refined as new incident patterns emerge |
| `remediation_catalog` | Root cause -> action | New automation strategies added over time |
| `recovery_catalog` | Recovery model -> workflow | New recovery workflows added as systems grow |
| `storm_detection` | Threshold + window | Adjusted as system grows |
| `log_analysis` | Window + max events | Cost and performance tuning |
| `reservation_timeout_seconds` | Max age for RESERVED records before reclaim | Tuned to match Detection Lambda timeout |
| `triage_timeout_seconds` | Max triage duration before forced escalation | Tuned based on observed triage durations |
| `grace_period_seconds` | Recurrence window | Operations adjusts based on experience |
| `verification_wait_seconds` | Per-severity wait | Tuned per severity level |
| `correlation_ttl_hours` | DynamoDB active record TTL | Adjusted based on alarm recovery patterns |

Workflow logic (state transitions, orchestration, verification, reserve-then-create) stays in code.

---

## Non-Functional Requirements

### NFR-001: Observability
All three Lambdas SHALL use the `@observe` decorator with `context_kwarg_keys` for domain context propagation. Every log entry SHALL include `incident_key` as the primary correlation identifier.

Required structured log fields:
- `incident_key` -- primary correlation identifier (present in ALL log entries)
- `service` and `stage`
- `severity`
- `jira_ticket_id` -- Jira ticket key
- Processing-leg-specific fields:
  - Leg 1: `cool_off_result`, `dedup_result`, `storm_detected`
  - Leg 2: `root_cause`, `root_cause_confidence`, `remediation_action`, `remediation_result`
  - Leg 3: `escalation_reason`

### NFR-002: Security
Jira API credentials SHALL be stored in AWS Secrets Manager (`sre-platform/jira-credentials`) and never in code, config, or environment variables. Each Lambda IAM role SHALL follow least-privilege (scoped to only the AWS resources it needs).

### NFR-003: Reliability
Failure in any processing step (Jira, log collection, SNS, remediation) SHALL NOT prevent other steps from executing. External integration methods return None/False on failure -- callers decide how to proceed. Each pipeline leg runs in its own Lambda with independent failure boundaries.

### NFR-004: Architecture Compliance
All three Lambdas SHALL follow the platform's hexagonal architecture (handlers -> services -> models -> repositories) and use the shared middleware layer. Because the system is SNS/EventBridge-triggered (not HTTP), there is no DTO layer; input validation is performed inline in model factories.

### NFR-005: Idempotent Processing
Duplicate SNS deliveries and EventBridge retries SHALL NOT create duplicate incidents or corrupt state. DynamoDB conditional writes and the reserve-then-create pattern provide the primary idempotency mechanism.

### NFR-006: Failure Capture and Replay
Failed events SHALL NOT be lost:

- SNS subscription: SQS DLQ for Detection Lambda failures
- EventBridge: built-in retry (up to 24h) + DLQ for Triage/Escalation Lambda failures
- DLQ depth monitored with CloudWatch alarm
- Replay mechanism for manual or automated DLQ reprocessing

### NFR-007: Operational Metrics
All three Lambdas SHALL emit custom CloudWatch metrics (via `@observe` decorator) to monitor system effectiveness:

| Metric | Type | Description |
|--------|------|-------------|
| `detection_total` | Counter | Incidents created, by severity and service |
| `detection_cooloff_total` | Counter | Transient spikes filtered by cool-off |
| `detection_storm_total` | Counter | Storm detection checks |
| `triage_total` | Counter | Triage completions, by outcome |
| `triage_remediate_total` | Counter | Remediation attempts, by action and outcome |
| `escalation_total` | Counter | Engineer escalations, by reason |
| `detection_duration` | Histogram | Detection processing time |
| `triage_duration` | Histogram | Triage processing time |
| `escalation_duration` | Histogram | Escalation processing time |
| `jira_create_duration` | Histogram | Jira API call latency |

These metrics power the incident management CloudWatch dashboard.

### NFR-008: Lambda Timeout Configuration
Lambda timeouts SHALL accommodate worst-case sleep durations:

| Lambda | Timeout | Reason |
|--------|---------|--------|
| Detection | 180 seconds | Cool-off sleep up to 120s (SEV-3) + DynamoDB/Jira/EventBridge calls |
| Triage | 300 seconds | Verification wait up to 120s (SEV-3) + log analysis + remediation + Jira updates |
| Escalation | 30 seconds | No sleeps -- Jira enrichment + SNS notification only |

Synchronous sleeps are a deliberate trade-off: simpler architecture (no Step Functions) at the cost of Lambda execution time. Cost is bounded and acceptable for low-frequency alarm events.

---

## Acceptance Criteria

### Leg 1 -- Detection

| ID | Criterion | Requirement |
|----|-----------|-------------|
| AC-001 | CloudWatch alarm (ALARM state) triggers Detection Lambda via SNS | FR-001 |
| AC-002 | Severity and recovery_model classified from alarm name using externalized severity_mapping | FR-002 |
| AC-003 | Service, alarm type, and stage correctly extracted from alarm name | FR-003 |
| AC-004 | Transient spike (recovers within cool-off) does not create incident | FR-004 |
| AC-005 | Persistent alarm (still ALARM after cool-off) creates incident | FR-004 |
| AC-006 | Reserve-then-create pattern prevents duplicate Jira tickets under concurrency | FR-006 |
| AC-007 | RESERVED conflict: exit silently (winner is still creating ticket) | FR-006 |
| AC-008 | DETECTED/TRIAGING/ESCALATED conflict: add duplicate comment to existing Jira ticket | FR-006 |
| AC-009 | GRACE conflict: handle per grace period rules (reopen + escalate) | FR-006, FR-016 |
| AC-010 | Jira creation failure: reserved DynamoDB record deleted, event retryable via DLQ | FR-006 |
| AC-011 | Storm detected when >threshold incidents in window (configurable) | FR-007 |
| AC-012 | Storm flag included in IncidentCreated event | FR-007 |
| AC-013 | Jira incident ticket created with correct summary, priority, labels, incident_key | FR-008 |
| AC-014 | IncidentCreated event published to EventBridge with recovery_model | FR-009 |
| AC-015 | New service onboards with only an alarm action change | FR-010 |
| AC-015a | Alarm ARN and trigger dimensions extracted from SNS message | FR-003 |
| AC-015b | Lambda function name (from trigger dimensions) included in Jira ticket description | FR-008 |
| AC-015c | Lambda function name propagated in EventBridge events | FR-009 |

### Leg 2 -- Triage

| ID | Criterion | Requirement |
|----|-----------|-------------|
| AC-016 | Error logs collected within bounded window (500 events, 15 min) | FR-011 |
| AC-017 | Error summary includes count, grouping, timeline, affected ops/users | FR-011 |
| AC-017a | Log analysis targets exact log group using function_name when available | FR-011 |
| AC-017b | Sample error-triggering payloads (up to 5) extracted from structured logs | FR-011 |
| AC-018 | Root cause classified using externalized rules with confidence level | FR-012 |
| AC-019 | Blast radius assessed (users, error rate, endpoints, duration) | FR-013 |
| AC-020 | Storm detected: analysis runs but remediation skipped, escalates with reason "incident-storm" | FR-014 |
| AC-021 | Single remediation attempt per incident enforced | FR-014 |
| AC-022 | Remediation action looked up from externalized catalog | FR-014 |
| AC-023 | No catalog match: escalates with reason "no-remediation-available" | FR-014 |
| AC-024 | Verification wait period observed after remediation (per-severity, configurable) | FR-014 |
| AC-025 | 3-point verification performed (alarm state, health check, error rate) | FR-014 |
| AC-026 | All verification checks pass: Jira resolved, DynamoDB GRACE (15-min TTL) | FR-015 |
| AC-027 | Resolution evidence collected and attached to Jira | FR-015 |
| AC-028 | IncidentAutoResolved event published with recovery_model and recovery_status | FR-015 |
| AC-029 | No engineer notification for auto-resolved incidents | FR-015 |
| AC-030 | Grace period recurrence: reopen incident, escalate with reason "grace-period-recurrence" | FR-016 |
| AC-031 | Any verification check fails: escalates with reason "verification-failed" | FR-014 |
| AC-032 | Every triage step adds timestamped Jira comment | FR-017 |

### Leg 3 -- Escalation

| ID | Criterion | Requirement |
|----|-----------|-------------|
| AC-033 | Jira ticket enriched with root cause, blast radius, remediation history | FR-018 |
| AC-033a | Jira ticket includes Lambda function name and alarm ARN | FR-018 |
| AC-034 | Error logs, error-triggering payloads, and request traces attached to Jira ticket | FR-018 |
| AC-035 | Dashboard, X-Ray, and Logs Insights links in Jira ticket | FR-018 |
| AC-036 | Copy-paste investigation commands included in Jira ticket | FR-018 |
| AC-037 | Engineer can investigate without downloading logs or running scripts | FR-018 |
| AC-038 | Escalation reason included in Jira enrichment and notification | FR-018, FR-019 |
| AC-039 | SNS notification sent for SEV-1 and SEV-2 only | FR-019 |
| AC-040 | No SNS notification for SEV-3 | FR-019 |

### Recovery & Resolution

| ID | Criterion | Requirement |
|----|-----------|-------------|
| AC-041 | Alarm recovery (OK) resolves matching incident in Jira with diagnostics | FR-020 |
| AC-042 | Resolution-time diagnostics collected (recovery logs, health check) | FR-020 |
| AC-043 | Recovery logs attached to Jira ticket | FR-020 |
| AC-044 | DynamoDB record deleted on manual resolution | FR-020 |
| AC-045 | No matching incident on recovery: log and skip | FR-020 |

### Shared / Cross-Cutting

| ID | Criterion | Requirement |
|----|-----------|-------------|
| AC-046 | All three Lambdas use @observe decorator with domain context | NFR-001 |
| AC-047 | incident_key present in every structured log entry | NFR-001 |
| AC-048 | Jira credentials from Secrets Manager only | NFR-002 |
| AC-049 | Each Lambda IAM role follows least-privilege | NFR-002 |
| AC-050 | Failure in one step does not block other steps | NFR-003 |
| AC-051 | Hexagonal architecture: handlers -> services -> models -> repositories | NFR-004 |
| AC-052 | Duplicate SNS/EventBridge deliveries do not create duplicate incidents | NFR-005 |
| AC-053 | Failed events captured in DLQ, not lost | NFR-006 |
| AC-054 | DLQ depth alarm fires on unprocessed events | NFR-006 |
| AC-055 | Operational metrics emitted per @observe decorator | NFR-007 |
| AC-056 | Incident management dashboard shows system effectiveness | NFR-007 |
| AC-057 | Active DynamoDB records have TTL = created_at + 24 hours | NFR-008 |
| AC-058 | GRACE records have TTL = resolved_at + 15 minutes | NFR-008 |
| AC-059 | Lambda timeouts: Detection 180s, Triage 300s, Escalation 30s | NFR-008 |
| AC-060 | Externalized config loaded at cold start, no code changes for threshold tuning | FR-002, FR-012, FR-014 |
| AC-061 | Stateless recovery model: no recovery action triggered after remediation | FR-015a |
| AC-062 | Replay recovery model: DLQ replay workflow triggered after remediation | FR-015a |
| AC-063 | Reprocess recovery model: batch rerun workflow triggered after remediation | FR-015a |
| AC-064 | Data-correction recovery model: reconciliation workflow triggered after remediation | FR-015a |
| AC-065 | Backlog-drain recovery model: consumer scaling triggered after remediation | FR-015a |
| AC-066 | Recovery catalog looked up from externalized config | FR-015a |
| AC-067 | Recovery workflow execution ID recorded in Jira comment | FR-015a |
| AC-068 | Recovery workflow failure does not block auto-resolution | FR-015a |
| AC-069 | Incident system never processes business data -- only triggers external workflows | FR-015a |
| AC-070 | Recovery workflow payloads include idempotency keys (incident_key, jira_ticket_id, execution_id) | FR-015a |
| AC-071 | Stale RESERVED record (older than reservation_timeout_seconds) reclaimed and retried | FR-006 |
| AC-072 | Triage timeout: escalates with reason "triage-timeout" when elapsed time exceeds triage_timeout_seconds | FR-014 |
| AC-073 | Root cause classification uses string-based rules from config, not a fixed enum | FR-012 |

---

## Jira Configuration

| Setting | Value |
|---------|-------|
| Instance URL | https://rameshnag2002.atlassian.net |
| Project Key | ASD |
| Project Name | API Service Desk |
| Issue Type | Incident |
| Request Type | Report a system problem |
| Default Reporter | Service Account (incident-bot) |
| Credentials | AWS Secrets Manager: `sre-platform/jira-credentials` |

## Out of Scope

- Slack/PagerDuty integration (future enhancement)
- Multi-region incident correlation
- Incident dashboard UI
- Custom remediation runbook authoring UI
- Step Functions orchestration (deliberate trade-off for simplicity)
- AI-assisted diagnosis (future EventBridge consumer)
