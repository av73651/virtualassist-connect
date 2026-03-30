# Incident Management Pipeline — Requirements

## Overview

Automated incident detection, self-healing, and escalation pipeline built in three legs:

- **Leg 1 — Incident Detection & Creation**: Alarm fires → cool-off check → deduplication → create incident record in DynamoDB and Jira (minimal ticket)
- **Leg 2 — Automated Triage & Self-Healing**: Log analysis → root cause classification → blast radius assessment → remediation attempt → if resolved, close incident; if not, escalate to Leg 3
- **Leg 3 — Engineer Escalation & Resolution**: Enrich Jira ticket with full diagnostics and analysis → notify support engineer → track resolution through to closure

The system tries to resolve the incident automatically before engaging a human. When escalation is necessary, the support engineer receives a fully analyzed ticket — not raw logs.

## Actors

| Actor | Description |
|-------|-------------|
| CloudWatch Alarm | Triggers pipeline on threshold breach or recovery |
| Incident Manager Lambda | Processes alarm events, orchestrates all three legs |
| Support Engineer | Engaged only after self-healing fails; receives analyzed ticket |
| Jira (API Service Desk) | Ticket system — tracks incident through full lifecycle |
| Remediation Engine | Automated self-healing actions based on alarm type |

## Incident Lifecycle & Status Flow

```
ALARM fires
  → DETECTED (Leg 1: cool-off, dedup, record created, minimal Jira ticket)
    → TRIAGING (Leg 2: log analysis, root cause classification, blast radius)
      ├─ remediation available:
      │   → REMEDIATING (execute remediation action)
      │     → VERIFYING (wait verification period, run 3-point check)
      │       ├─ all checks pass:
      │       │   → AUTO-RESOLVED (collect evidence, update Jira, close, enter grace period)
      │       │     └─ alarm recurs within grace period:
      │       │         → ESCALATED (reopen, skip remediation, go to Leg 3)
      │       └─ any check fails:
      │           → ESCALATED (Leg 3: enrich ticket, notify engineer)
      └─ no remediation available:
          → ESCALATED (Leg 3: enrich ticket, notify engineer)
            → INVESTIGATING (engineer working)
              → RESOLVED (engineer confirms fix, alarm clears)

ALARM recovers (OK)
  → If OPEN/ESCALATED incident exists: collect resolution data, update Jira, close record
  → If no matching incident: log and skip
```

Each status transition SHALL be recorded in the DynamoDB incident record and reflected as a Jira ticket comment with timestamp.

---

# LEG 1 — INCIDENT DETECTION & CREATION

Triggered when a CloudWatch alarm transitions to ALARM state. Goal: quickly confirm the alarm is real, deduplicate, and create an incident record. No human engaged yet.

## Functional Requirements — Leg 1

### FR-001: Alarm Ingestion via SNS
The system SHALL accept CloudWatch Alarm state change notifications via a shared SNS topic. Any service stack's alarms can publish to this topic.

### FR-002: Severity Classification
The system SHALL classify incident severity from the alarm name using convention-based pattern matching:
- `*-high-error-rate-*` → SEV-1 (Critical)
- `*-high-latency-*` → SEV-2 (Major)
- `*-high-4xx-*` → SEV-3 (Minor)

### FR-003: Service and Environment Identification
The system SHALL extract the following metadata from the alarm name convention:

`{service}-high-{type}-{stage}`

Captured attributes SHALL include:
- **service name** (e.g., `calculator`, `hello-world`)
- **alarm type** (e.g., `error-rate`, `latency`, `4xx-errors`)
- **deployment stage** (e.g., `dev`, `staging`, `prod`)

These attributes SHALL construct the incident key and determine routing logic.

### FR-004: Cool-Off Stabilization Check
The system SHALL implement a cool-off period before creating an incident to filter transient spikes.

- When an ALARM event is received and no OPEN incident exists, the system SHALL re-check the alarm state after a configurable cool-off period.
- If the alarm is still in ALARM state after cool-off, proceed with incident creation.
- If the alarm has returned to OK during cool-off, log as transient spike and skip.
- Cool-off periods per severity:
  - SEV-1: 30 seconds (fast escalation for critical issues)
  - SEV-2: 60 seconds
  - SEV-3: 120 seconds
- The cool-off check SHALL use the CloudWatch `describe-alarms` API.

### FR-005: Incident Deduplication
The system SHALL prevent duplicate incidents for the same active alarm.

- The **incident key** (`{service}-{alarm-type}-{stage}`) is the system's primary correlation identifier. All lookups, deduplication, and lifecycle transitions SHALL use this key.
- Check DynamoDB for an existing OPEN incident with the same key.
- If OPEN incident exists:
  - Do NOT create a new Jira ticket.
  - Append a comment to the existing Jira ticket with timestamp and current alarm state.
- If no OPEN incident exists:
  - Create a new incident record and Jira ticket.
- **Atomic creation**: The system SHALL use DynamoDB conditional writes (`attribute_not_exists(incident_key)` or `status = RESOLVED`) to prevent race conditions where concurrent alarm deliveries create duplicate incidents for the same key.

### FR-006: Incident Record Creation
The system SHALL create an incident record in DynamoDB with status DETECTED and a minimal Jira ticket (summary, severity, alarm details only — no logs yet). The ticket signals that automated triage is in progress.

Jira ticket at this stage:
- **Summary**: `[SEV-X] {service} ({stage}): {alarm description}`
- **Priority**: SEV-1→Highest, SEV-2→High, SEV-3→Medium
- **Labels**: `incident`, `automated`, `{service}`, `{stage}`
- **Description**: "Incident detected. Automated triage in progress..."
- **Status comment**: "Incident detected at {timestamp}. Automated analysis starting."

### FR-007: Scalable Onboarding
New services SHALL onboard by adding a single alarm action pointing to the shared SNS topic. No changes to the Incident Manager Lambda required.

---

# LEG 2 — AUTOMATED TRIAGE & SELF-HEALING

Triggered immediately after Leg 1 creates an incident. Goal: analyze the problem, classify root cause, assess blast radius, attempt self-healing. If resolved, close. If not, prepare the ticket for human escalation.

## Functional Requirements — Leg 2

### FR-008: Log Collection and Error Analysis
The system SHALL pull recent logs from the affected service and produce structured analysis.

**Bounded analysis window**: Log analysis SHALL be limited to a fixed time window (default: 15 minutes) and a maximum of 500 log events per query to control processing cost and Lambda execution time. If the log volume exceeds the limit, the system SHALL analyze the most recent events and note the truncation in the error summary.

Analysis outputs:
- **Error summary**: Total error count, errors grouped by type, top error messages
- **Error timeline**: Error rate over 1-minute buckets to show trend (spike vs sustained)
- **Affected operations**: Which API endpoints/operations are failing (from `path` and `operation` log fields)
- **Affected users**: Count of distinct `user_id` values in error logs (from enhanced middleware logging)
- **Sample errors**: Up to 5 full error log entries with stack traces for representative failures

### FR-009: Root Cause Classification
The system SHALL analyze the collected logs and classify the probable root cause:

| Pattern Detected | Classification | Confidence |
|-----------------|---------------|------------|
| Single error type dominates (>80%) | Specific bug (e.g., DivisionByZeroError) | High |
| ImportError / SyntaxError in logs | Bad deployment | High |
| No application errors, but high latency | Performance degradation / cold starts | Medium |
| Mixed error types after recent deploy | Bad deployment (broad failure) | Medium |
| Sudden spike then stabilizing | Transient load spike | Medium |
| Throttling errors (429) | Rate limit / capacity | High |
| Auth errors (401/403) dominating | Authentication/authorization issue | High |
| No clear pattern | Unknown — requires investigation | Low |

The classification SHALL be included in the Jira ticket and incident record.

### FR-010: Blast Radius Assessment
The system SHALL assess the impact of the incident:

- **Affected endpoints**: Which operations are returning errors
- **Affected users**: Distinct user count from error logs
- **Error rate**: Current vs baseline (percentage of requests failing)
- **Duration**: How long the alarm has been active

This assessment SHALL be summarized as: `Impact: {X} users affected, {Y}% error rate on {endpoints} for {duration}`

### FR-011: Automated Remediation Attempt
The system SHALL attempt self-healing based on the root cause classification.

**Single attempt constraint**: The system SHALL execute at most ONE remediation attempt per incident. The `remediation_result` field in DynamoDB tracks whether remediation has been attempted. If remediation has already been attempted (regardless of outcome), the system SHALL NOT retry and SHALL escalate to Leg 3. This prevents automation loops and uncontrolled infrastructure changes.

**Step 1 — Remediation Lookup:**
- The system SHALL evaluate the root cause classification against a remediation registry (configuration mapping root cause → action).
- If no remediation exists for the classification, skip to escalation (Leg 3) with Jira comment: "No automated remediation available for {classification}."

**Step 2 — Execute Remediation:**
- Update incident status to REMEDIATING.
- Add Jira comment: "Attempting remediation: {action description}."
- Execute the remediation action (see remediation catalog below).
- Log the action taken, start time, and any output/errors.

**Step 3 — Verification Wait:**
- After remediation executes, the system SHALL wait a verification period for the fix to take effect:
  - SEV-1: 60 seconds
  - SEV-2: 90 seconds
  - SEV-3: 120 seconds

**Step 4 — Post-Remediation Verification:**
The system SHALL perform a multi-point verification to confirm the issue is resolved:

1. **Alarm state check**: Query CloudWatch `describe-alarms` API to verify alarm has returned to OK.
2. **Health check**: Execute endpoint health checks against the affected service (same logic as `health-check.sh`).
3. **Error rate check**: Pull the last 2 minutes of logs and verify error count is below the alarm threshold.

**Verification outcomes:**
- All three checks pass → remediation succeeded → proceed to auto-resolution (FR-012).
- Any check fails → remediation failed → proceed to escalation (Leg 3) with Jira comment documenting which checks failed.

**Remediation Catalog:**

| Root Cause Classification | Remediation Action | Description |
|--------------------------|-------------------|-------------|
| Bad deployment (ImportError/SyntaxError) | Lambda version rollback | Revert to the previous published Lambda version using `update-function-configuration` to restore last known good code |
| Performance degradation / cold starts | Lambda memory increase | Temporarily increase Lambda memory allocation by one tier (e.g., 512→1024 MB) to reduce cold start and execution time |
| Rate limit / capacity (429s) | Concurrency increase | Increase Lambda reserved concurrency and/or API Gateway throttle limits |
| Specific bug (single error type) | No auto-remediation | Classification logged; requires code fix — escalate to engineer |
| Authentication/authorization issue | No auto-remediation | Requires Cognito/IAM investigation — escalate to engineer |
| Unknown | No auto-remediation | Escalate to engineer |

### FR-012: Auto-Resolution Process
When post-remediation verification succeeds (all three checks pass), the system SHALL execute the full auto-resolution workflow:

**Step 1 — Collect Resolution Evidence:**
- Recovery timestamp
- Incident duration (detection to resolution)
- Remediation action that was taken
- Post-remediation verification results (alarm state, health check, error rate)
- Resolution window logs: last 5 minutes of logs showing the error rate dropping to normal

**Step 2 — Update Incident Record:**
- Set status to AUTO-RESOLVED
- Set `resolved_at` timestamp
- Set `remediation_result` to "succeeded"
- Set `remediation_action` to the action taken (e.g., "lambda-version-rollback")

**Step 3 — Update Jira Ticket:**
Add a resolution comment containing:
```
=== INCIDENT AUTO-RESOLVED ===

Resolution: Automated remediation successful
Action taken: {remediation action description}
Duration: {X minutes Y seconds}
Resolved at: {timestamp}

Post-recovery verification:
  ✓ Alarm state: OK
  ✓ Health check: All endpoints responding (X/X passed)
  ✓ Error rate: {current}% (below threshold of {threshold}%)

Resolution logs attached: resolution-logs-{timestamp}.txt
```

Attach resolution logs showing the error rate dropping after remediation.

**Step 4 — Close Jira Ticket:**
- Transition the Jira ticket to a resolved/closed state (if workflow supports it).
- If workflow transition is not available, add the `auto-resolved` label.

**Step 5 — No Engineer Notification:**
- AUTO-RESOLVED incidents SHALL NOT trigger SNS notifications to engineers.
- The resolved Jira ticket serves as the audit trail.

**Step 6 — Monitoring Grace Period:**
- After auto-resolution, the system SHALL retain the incident key in a "grace" state for 15 minutes.
- If the same alarm fires again within the grace period, the system SHALL:
  - Reopen the incident (not create a new one).
  - Skip remediation (already tried).
  - Escalate directly to Leg 3 with Jira comment: "Incident recurred after auto-remediation. Previous fix was not durable. Escalating to engineer."
  - This prevents remediation loops for flapping alarms.

### FR-013: Incident Status Updates
Every step in Leg 2 SHALL update the incident status and add a timestamped comment to the Jira ticket:

- `DETECTED → TRIAGING`: "Analyzing logs... collecting error data."
- `TRIAGING → REMEDIATING`: "Root cause classified as {classification} ({confidence}). Attempting remediation: {action}."
- `REMEDIATING → VERIFYING`: "Remediation executed. Waiting {X}s for verification..."
- `VERIFYING → AUTO-RESOLVED`: "All verification checks passed. Incident auto-resolved. Duration: {X}m."
- `VERIFYING → ESCALATED`: "Verification failed ({which checks}). Escalating to support engineer."
- `TRIAGING → ESCALATED` (no remediation available): "No automated remediation available for {classification}. Escalating."
- `AUTO-RESOLVED → ESCALATED` (recurrence within grace period): "Incident recurred after auto-remediation. Fix not durable. Escalating."

---

# LEG 3 — ENGINEER ESCALATION & RESOLUTION

Triggered when Leg 2 cannot resolve the incident. Goal: enrich the Jira ticket with all diagnostic data and analysis so the support engineer can act immediately.

## Functional Requirements — Leg 3

### FR-014: Jira Ticket Enrichment
The system SHALL update the Jira ticket with full diagnostic context. The support engineer SHALL NOT need to download logs or run scripts to begin investigation.

**Ticket description updated with:**
- Incident metadata (key, service, stage, severity, alarm, duration)
- Root cause classification and confidence level
- Blast radius assessment (users affected, error rate, endpoints)
- Remediation actions attempted and outcomes

**Attached to the ticket:**
- Error log extract (`error-logs-{timestamp}.txt`)
- Top failing request traces (`request-traces-{timestamp}.txt`)
- Error timeline and trend data

**Links included:**
- CloudWatch dashboard (direct URL for the service)
- X-Ray trace console (filtered by service and time window)
- CloudWatch Logs Insights (pre-built query, ready to run in console)
- Runbook: `docs/runbooks/{service}-debug.md`

**Investigation commands (copy-paste ready):**
```
./scripts/incident/download-logs.sh --stage {stage} --service {service} --minutes 30
./scripts/incident/trace-lookup.sh --stage {stage} --correlation-id {sample-trace-id}
./scripts/incident/health-check.sh --stage {stage}
```

### FR-015: Engineer Notification
The system SHALL send SNS notification for SEV-1 and SEV-2 incidents only, after Leg 2 has failed to resolve:

- Incident key and severity
- Root cause classification
- Blast radius summary
- Jira ticket link (with all diagnostics already attached)
- Time elapsed since alarm triggered

SEV-3 incidents that reach Leg 3 are tracked via enriched Jira ticket only (no notification).

### FR-016: Resolution Tracking
The system SHALL process incident resolution (manual or alarm recovery):

**On alarm recovery (OK state):**
- Locate corresponding OPEN/ESCALATED incident via incident key
- Collect resolution-time diagnostics:
  - Recovery timestamp and incident duration
  - Post-recovery health check result
  - Resolution window logs (last 5 minutes before recovery)
- Update Jira ticket with resolution comment and attached resolution logs
- Update DynamoDB record: status → RESOLVED, set `resolved_at`

**If no matching OPEN incident exists:**
- Log and skip (e.g., transient spike filtered by cool-off)

---

# SHARED REQUIREMENTS

## Incident Registry — DynamoDB Table

Table name: `incident-registry-{stage}`

| Attribute | Description |
|-----------|-------------|
| `incident_key` | PK — unique key from `{service}-{alarm-type}-{stage}` |
| `incident_id` | Generated ID (e.g., `INC-20260330-calculator-abc123`) |
| `service` | Affected service name |
| `stage` | Deployment stage |
| `severity` | SEV-1, SEV-2, or SEV-3 |
| `alarm_name` | Full CloudWatch alarm name |
| `alarm_type` | Extracted alarm type (error-rate, latency, 4xx-errors) |
| `status` | DETECTED → TRIAGING → REMEDIATING → VERIFYING → AUTO-RESOLVED / ESCALATED → RESOLVED |
| `root_cause` | Classification from FR-009 |
| `blast_radius` | Impact assessment from FR-010 |
| `jira_ticket` | Jira ticket key (e.g., ASD-42) |
| `error_summary` | Log analysis results |
| `remediation_result` | not_attempted / attempted / succeeded / failed |
| `remediation_action` | What was attempted (e.g., "lambda-restart") |
| `created_at` | Detection timestamp |
| `escalated_at` | When escalated to engineer (null if auto-resolved) |
| `resolved_at` | Resolution timestamp |
| `ttl` | Expiration timestamp for automatic cleanup of resolved records |

## Non-Functional Requirements

### NFR-001: Observability
The Incident Manager Lambda SHALL use the standard `@observe` decorator and emit structured logs. Every log entry during incident processing SHALL include the `incident_key` as the primary correlation identifier, enabling end-to-end tracing of an incident across all three legs.

Required structured log fields:
- `incident_key` — primary correlation identifier (present in ALL log entries)
- `incident_status` — current status at time of log entry
- `processing_leg` — 1, 2, or 3
- `service` and `stage`
- `severity`
- `cool_off_result` — passed / filtered (Leg 1)
- `dedup_result` — new / duplicate / atomic_conflict (Leg 1)
- `root_cause` and `root_cause_confidence` (Leg 2)
- `remediation_action` and `remediation_result` (Leg 2)
- `jira_ticket` — Jira ticket key
- `escalation_reason` — why escalated, if applicable (Leg 3)

### NFR-002: Security
Jira API credentials SHALL be stored in AWS Secrets Manager (`incident-manager/jira-credentials`) and never in code, config, or environment variables. The Lambda IAM role SHALL follow least-privilege.

### NFR-003: Reliability
Failures in any single step (Jira, log collection, SNS, remediation) SHALL NOT prevent other steps from executing. Each step is independent and failures are logged with the incident.

### NFR-004: Architecture Compliance
The Incident Manager Lambda SHALL follow the platform's hexagonal architecture (handlers → services → domain → repositories → DTOs) and use the shared middleware layer.

### NFR-005: Idempotent Processing
Duplicate SNS deliveries SHALL NOT create duplicate incidents. Deduplication enforced via the incident registry in DynamoDB using the incident key and atomic conditional writes.

### NFR-006: Failure Capture and Replay
If the Incident Manager Lambda fails to process an alarm event (unhandled exception, timeout, or dependency failure), the event SHALL NOT be lost.

- The SNS subscription SHALL be configured with a Dead Letter Queue (SQS DLQ).
- Failed events SHALL be retained in the DLQ for manual or automated replay.
- The DLQ depth SHALL be monitored with a CloudWatch alarm to alert on processing failures.
- A replay mechanism SHALL allow re-processing of DLQ events (manual trigger or scheduled).

### NFR-007: Operational Metrics and Telemetry
The Incident Manager SHALL emit custom CloudWatch metrics to monitor system effectiveness:

| Metric | Type | Description |
|--------|------|-------------|
| `incidents_created_total` | Counter | Total incidents created, by severity and service |
| `incidents_auto_resolved_total` | Counter | Incidents resolved by automated remediation |
| `incidents_escalated_total` | Counter | Incidents escalated to engineers |
| `incidents_filtered_total` | Counter | Transient spikes filtered by cool-off |
| `incidents_deduplicated_total` | Counter | Duplicate alarms suppressed |
| `remediation_attempts_total` | Counter | Remediation attempts, by action and outcome |
| `incident_detection_to_resolution_ms` | Histogram | Time from detection to resolution (auto or manual) |
| `incident_detection_to_escalation_ms` | Histogram | Time from detection to engineer escalation |
| `log_analysis_duration_ms` | Histogram | Time spent on log analysis |
| `jira_api_duration_ms` | Histogram | Jira API call latency |

These metrics SHALL power a CloudWatch dashboard for incident management system health.

### NFR-008: Incident Retention Policy
DynamoDB incident records SHALL follow a tiered retention policy:

| Status | Retention | Mechanism |
|--------|-----------|-----------|
| OPEN / ESCALATED | Indefinite | No TTL — active incidents never expire |
| AUTO-RESOLVED | 30 days | TTL set at resolution time |
| RESOLVED | 90 days | TTL set at resolution time |
| Grace period (post-auto-resolve) | 15 minutes | TTL on grace marker record |

- TTL SHALL be calculated and set when the incident status changes to a resolved state.
- Resolved records are retained for audit trail purposes before automatic cleanup.
- Active incidents (OPEN, ESCALATED, TRIAGING, REMEDIATING, VERIFYING) SHALL NOT have a TTL set.

---

## Acceptance Criteria

### Leg 1 — Incident Detection & Creation

| ID | Criterion | Requirement |
|----|-----------|-------------|
| AC-001 | CloudWatch alarm (ALARM state) triggers pipeline via SNS | FR-001 |
| AC-002 | Error rate alarm classified as SEV-1 | FR-002 |
| AC-003 | Latency alarm classified as SEV-2 | FR-002 |
| AC-004 | 4xx alarm classified as SEV-3 | FR-002 |
| AC-005 | Service, alarm type, and stage correctly extracted | FR-003 |
| AC-006 | Transient spike (recovers within cool-off) does not create incident | FR-004 |
| AC-007 | Persistent alarm (still ALARM after cool-off) creates incident | FR-004 |
| AC-008 | Duplicate alarms do not create new incidents | FR-005 |
| AC-009 | Existing Jira ticket gets comment on duplicate alarm | FR-005 |
| AC-010 | Incident record created in DynamoDB with status DETECTED | FR-006 |
| AC-011 | Minimal Jira ticket created with "triage in progress" message | FR-006 |
| AC-012 | New service onboards with only an alarm action change | FR-007 |

### Leg 2 — Automated Triage & Self-Healing

| ID | Criterion | Requirement |
|----|-----------|-------------|
| AC-013 | Error logs collected and grouped by type | FR-008 |
| AC-014 | Affected operations and user count identified | FR-008 |
| AC-015 | Root cause classified with confidence level | FR-009 |
| AC-016 | Blast radius assessed (users, error rate, endpoints, duration) | FR-010 |
| AC-017 | Remediation attempted when runbook available | FR-011 |
| AC-018 | Verification wait period observed after remediation | FR-011 |
| AC-019 | 3-point verification performed (alarm state, health check, error rate) | FR-011 |
| AC-020 | All verification checks pass → AUTO-RESOLVED | FR-012 |
| AC-021 | Resolution evidence collected (duration, action, verification results) | FR-012 |
| AC-022 | Jira ticket updated with resolution comment and logs attached | FR-012 |
| AC-023 | Jira ticket closed or labeled auto-resolved | FR-012 |
| AC-024 | No engineer notification for auto-resolved incidents | FR-012 |
| AC-025 | Grace period prevents remediation loops on recurrence | FR-012 |
| AC-026 | Recurrence within grace period escalates directly to Leg 3 | FR-012 |
| AC-027 | Any verification check fails → escalation to Leg 3 | FR-011 |
| AC-028 | No remediation available → escalation to Leg 3 | FR-011 |
| AC-029 | Every status change adds timestamped Jira comment | FR-013 |

### Leg 3 — Engineer Escalation & Resolution

| ID | Criterion | Requirement |
|----|-----------|-------------|
| AC-030 | Jira ticket enriched with root cause and blast radius | FR-014 |
| AC-031 | Error logs and request traces attached to ticket | FR-014 |
| AC-032 | Dashboard, X-Ray, and Logs Insights links in ticket | FR-014 |
| AC-033 | Investigation commands included (copy-paste ready) | FR-014 |
| AC-034 | Engineer can investigate without downloading logs or running scripts | FR-014 |
| AC-035 | SNS notification sent for SEV-1 only after Leg 2 fails | FR-015 |
| AC-036 | SNS notification sent for SEV-2 only after Leg 2 fails | FR-015 |
| AC-037 | No SNS notification for SEV-3 | FR-015 |
| AC-038 | Alarm recovery resolves matching OPEN/ESCALATED incident | FR-016 |
| AC-039 | Resolution logs and duration attached to Jira ticket | FR-016 |
| AC-040 | DynamoDB record updated with resolved_at | FR-016 |

### Shared

| ID | Criterion | Requirement |
|----|-----------|-------------|
| AC-041 | Jira failure does not block DynamoDB or other steps | NFR-003 |
| AC-042 | SNS failure does not block other steps | NFR-003 |
| AC-043 | Jira credentials from Secrets Manager only | NFR-002 |
| AC-044 | Hexagonal architecture (handlers/services/domain/dto/repos) | NFR-004 |
| AC-045 | Unit test coverage ≥ 80% | NFR-004 |
| AC-046 | Duplicate SNS deliveries do not create duplicate incidents | NFR-005 |
| AC-047 | Atomic conditional write prevents race condition on incident creation | NFR-005, FR-005 |
| AC-048 | Failed alarm events land in DLQ, not lost | NFR-006 |
| AC-049 | DLQ depth alarm fires when unprocessed events accumulate | NFR-006 |
| AC-050 | Operational metrics emitted (created, auto-resolved, escalated, filtered) | NFR-007 |
| AC-051 | Incident management dashboard shows system effectiveness | NFR-007 |
| AC-052 | Resolved incidents have TTL set per retention policy | NFR-008 |
| AC-053 | Active incidents do not have TTL (never auto-expire) | NFR-008 |
| AC-054 | incident_key present in every structured log entry | NFR-001 |
| AC-055 | Single remediation attempt per incident enforced | FR-011 |
| AC-056 | Log analysis bounded to 500 events / 15 min window | FR-008 |

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
| Credentials | AWS Secrets Manager: `incident-manager/jira-credentials` |

## Out of Scope

- Slack/PagerDuty integration (future enhancement)
- Multi-region incident correlation
- Incident dashboard UI
- Custom remediation runbook authoring UI
