# Incident Management Platform — Design Principles

These principles guide all architectural and design decisions for the incident management pipeline. They prioritize decoupling, resilience, automation-first operations, and operational safety.

---

## 1. Event-Driven Architecture

The system SHALL be designed as an event-driven pipeline where each stage reacts to events rather than directly invoking downstream components.

Events signal workflow progression between pipeline legs:
- `IncidentCreated` — Detection completed, triage needed
- `EscalationRequired` — Automation failed or unavailable, engineer needed
- `IncidentAutoResolved` — Self-healing succeeded, audit trail

Events carry minimal metadata (incident_key, jira_ticket_id, severity). Consuming Lambdas read full state from the system of record. No component should require synchronous orchestration across the entire pipeline.

## 2. Loose Coupling Between Processing Stages

Each logical stage MUST operate independently: Detection, Triage, Escalation.

Stages interact only through well-defined event contracts and the correlation store. Stages must NOT depend on internal implementation of other stages or synchronous completion of downstream processing.

## 3. Idempotent Processing

All processing steps MUST be idempotent. Duplicate events (SNS retries, concurrency) MUST NOT create duplicate incidents or corrupt state. DynamoDB conditional writes and the reserve-then-create pattern provide the primary idempotency mechanism.

## 4. Clear System Ownership

Each system in the architecture has exactly one responsibility:

| System | Responsibility |
|--------|---------------|
| CloudWatch | Detects failure |
| SNS | Event delivery |
| Lambda | Processing logic |
| Jira | Incident system of record (full lifecycle, diagnostics, history) |
| DynamoDB | Idempotency + correlation store (incident_key -> jira_ticket_id) |
| EventBridge | Workflow orchestration between pipeline legs |

Jira is the single system of record. Engineers look only at Jira. DynamoDB is minimal — correlation and deduplication only, not a full incident store. Records are deleted on resolution and auto-expire via TTL.

## 5. Automation-First, Human-Last

The system MUST prioritize automated remediation before human escalation. Engineers engaged only when automation is unavailable, failed, confidence is too low, or an incident storm is detected. Escalation provides complete diagnostic context, not raw telemetry.

## 6. Failure Isolation

Failure in any processing step MUST NOT break the overall pipeline. Each pipeline leg runs in its own Lambda with independent failure boundaries. The system must log the failure, update the correlation record, and continue processing where possible. External integration failures (Jira, SNS) return None/False — callers decide how to proceed.

## 7. Safe Automation

Automated remediation MUST follow strict safety controls:

- **Single attempt**: One remediation attempt per incident
- **Verification before success**: 3-point check (alarm state, health check, error rate)
- **Grace period**: Configurable window after auto-resolution before cleanup
- **Storm detection**: When incident rate exceeds threshold (configurable), automation is disabled system-wide and all incidents escalate directly to engineers — preventing automation from amplifying dependency failure outages
- **Deterministic scope**: Remediation actions are bounded and catalog-driven

Automation must never create infinite remediation loops or secondary outages.

## 8. Observability by Design

Every stage MUST produce structured telemetry answering: What happened? When? Why? What action was taken? Was automation successful? Telemetry includes logs, metrics, correlation identifiers, and lifecycle transition timestamps. All telemetry flows through the `@observe` decorator.

## 9. Bounded Processing Scope

All automated analysis operates within defined time and data limits (log analysis window, verification windows, cool-off periods). Limits are externalized in configuration for operational tuning. This ensures predictable performance, cost control, and reliable automation behavior.

## 10. Graceful Degradation

When parts fail, the platform degrades gracefully. If log analysis fails, escalate with limited context. If remediation fails, escalate to engineer. If Jira is unreachable, retain correlation record and retry. Core incident tracking capability is always preserved.

## 11. Deterministic Decision Logic

Root cause classification, remediation selection, and escalation decisions must be deterministic, reproducible, rule-based, auditable, and configurable.

Classification rules and remediation catalogs are externalized in a JSON config file loaded at Lambda cold start. This separates operational tuning (what changes) from workflow logic (what stays in code). Config changes do not require code deployments.

## 12. Minimal Shared Knowledge

Components share event contracts and the correlation key, not internal logic. Detection produces structured metadata (incident_key, jira_ticket_id, service, stage, severity, storm_detected). Downstream stages rely only on this contract.

## 13. Immutable Incident Evidence

Log extracts, error summaries, analysis results, and verification evidence are preserved as immutable artifacts in Jira (comments, attachments) for auditability and post-incident learning. Triage always performs analysis even during incident storms, ensuring engineers receive full diagnostics regardless of whether automation runs.

## 14. Design for Operational Simplicity

Prioritize clarity and predictability over cleverness. Each system has one clear role. Favor simple workflows, transparent state, and clear failure handling over complex automation that is difficult to debug.

Keep infrastructure minimal: one DynamoDB table (correlation only), three Lambdas (one per pipeline leg), EventBridge for orchestration. Avoid deep domain modeling, excessive abstraction layers, and complex object hierarchies — this is a workflow processor, not a large domain application.

## 15. Recovery-Aware Automation

Restoring infrastructure does not always restore system correctness. The system SHALL classify incidents by recovery model — what needs to happen *after* service restoration:

| Recovery Model | What Needs Fixing | Example |
|----------------|-------------------|---------|
| Stateless | Just restore the service | API error spike, Lambda timeout |
| Replay | Replay lost events/messages | DLQ backlog, consumer crash |
| Reprocess | Rerun failed jobs/workflows | ETL failure, batch settlement |
| Data Correction | Repair incorrect data | Duplicate transactions, partial updates |
| Backlog Drain | Scale consumers to drain queue | Traffic spike, dependency slowdown |

The incident system is a **control plane for recovery**, not a data processor:
- Impacted records remain in their source systems (DLQs, retry queues, staging tables, event logs)
- Recovery workflows are external (Step Functions, Lambda, Glue jobs)
- The incident system only triggers and tracks recovery — it never processes business data
- Recovery actions are externalized in the `recovery_catalog` section of `incident_config.json`

A complete incident automation system must answer two questions: *How do we fix the system?* (remediation) and *How do we recover the work/data affected?* (recovery).

## 16. Evolutionary Architecture

The architecture must allow new capabilities without disrupting existing workflows. The externalized config file (`incident_config.json`) is the primary evolution mechanism:

- New classification rules added without code changes
- New remediation strategies added to the catalog
- New recovery workflows added to the recovery catalog
- Thresholds and timeouts tuned operationally
- Severity mappings (with recovery models) adjusted per team needs

Future enhancements (AI-assisted diagnosis, cross-service correlation, runbook recommendation, analytics dashboards) must be incrementally addable via new EventBridge consumers without modifying existing pipeline legs.

---

## Guiding Principle

> The incident platform should behave like a reliable operations assistant: Detect problems, understand the issue, fix what it safely can, recover affected work/data, and escalate with full context when humans are needed. Automation should reduce operational burden, not introduce operational complexity. When many things break at once, the system should recognize the pattern and get humans involved immediately rather than making things worse. When the system is restored, the platform should ensure not just system health but system correctness.
