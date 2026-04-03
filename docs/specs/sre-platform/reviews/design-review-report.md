# Design Review Report — Checkpoint & Clarity Framework (v1)

**Date**: 2026-04-02
**Reviewer**: Claude Opus 4.6 (AI)
**Design Version**: feature/calculator-enhancements (uncommitted)
**Status**: CONDITIONAL PASS → PASS (ARCH-001, ARCH-002 resolved 2026-04-02)

---

## Executive Summary

The Checkpoint & Clarity Framework v1 implementation plan is a well-scoped, focused design for platform-owned batch observability. The plan delivers maximum value with minimal complexity — the "See It, Click It" (minus the "Fix It") philosophy is sound. The SDK-first approach, 3-MVP structure, and simulation-driven verification are all strong design choices.

The primary strength is the sharp scope discipline: v1 is pure observability with zero recovery mechanics, making it deliverable in one week. The Delta Report format is the clear value centerpiece. The SDK API surface (7 methods) is minimal yet sufficient.

Three issues require attention before implementation: (1) the CheckpointClient lives inside the incident-manager Lambda but is a platform SDK that other services consume — the packaging and import path need clarification; (2) the DeltaReportService needs a CheckpointClient instance with query permissions, but the client is designed for applications to write — a read-only query method is needed; (3) the simulation's Phase 1 writes checkpoint records directly to DynamoDB, bypassing the SDK — this doesn't validate the SDK schema contract end-to-end.

**Overall Score**: 82/100

**Recommendation**:
- [x] APPROVED — ARCH-001 and ARCH-002 resolved. Proceed to implementation.

---

## Score Breakdown

| Dimension | Score | Status |
|-----------|-------|--------|
| Technology Standards Compliance | 92/100 | PASS |
| Architectural Patterns Compliance | 78/100 | CONDITIONAL |
| Design Completeness | 80/100 | PASS |
| Design Quality | 85/100 | PASS |
| Feasibility | 90/100 | PASS |
| Consistency | 80/100 | PASS |
| Documentation Quality | 72/100 | CONDITIONAL |
| **TOTAL** | **82/100** | **CONDITIONAL** |

---

## Detailed Findings

### 1. Technology Standards Compliance (92/100)

#### Passed Checks (16/18)
- [x] AWS Lambda used for all compute (Triage Lambda hosts Delta Report Service)
- [x] Python 3.12 runtime (inherits from existing incident-manager stack)
- [x] DynamoDB for checkpoint storage (PAY_PER_REQUEST, GSI, TTL)
- [x] S3 for large manifest side-loading
- [x] AWS CDK (Python) for infrastructure
- [x] Pydantic for DTOs (implicit — existing conftest fixtures)
- [x] EventBridge for event routing (existing IncidentCreated events)
- [x] No forbidden technologies used
- [x] Secrets Manager for Jira credentials (existing pattern)
- [x] IAM least-privilege with prefix-scoped conditions
- [x] No hardcoded credentials or secrets
- [x] Environment variables for configuration
- [x] X-Ray tracing via ADOT Lambda Layer (inherited)
- [x] `@observe` decorator for cross-cutting concerns
- [x] DynamoDB encryption at rest (AWS-managed default)
- [x] S3 encryption at rest (default)

#### Warnings (2)

- **[WARN-001]** S3 bucket `sre-checkpoint-manifests-{stage}` missing lifecycle policy
  - **Impact**: LOW — simulation data and small manifests won't auto-expire
  - **Recommendation**: Add S3 lifecycle rule to expire objects after 30 days (or match checkpoint TTL). TC6 CDK should include:
    ```python
    bucket.add_lifecycle_rule(expiration=Duration.days(30))
    ```

- **[WARN-002]** No CloudWatch Log retention specified for checkpoint-related operations
  - **Impact**: LOW — logs will accumulate indefinitely in dev
  - **Recommendation**: Specify retention period (14 days dev, 90 days prod) in TC6 CDK

#### Forbidden Technologies: None found

---

### 2. Architectural Patterns Compliance (78/100)

#### Layer Architecture (CONDITIONAL)

**Passed Checks (8/11)**:
- [x] CheckpointClient is a data-access class (repository-like) — correct layer
- [x] DeltaReportService is a service-layer class — correct orchestration
- [x] Resolution wiring uses existing service → service delegation (no handler changes)
- [x] Domain logic (delta computation) is in the SDK, not in DynamoDB expressions
- [x] No business logic in handlers
- [x] Existing handler singleton pattern preserved
- [x] `@observe` decorator for all public methods
- [x] Test structure follows existing convention (unit/ with moto)

**Issues (3)**:

- **[ARCH-001] SDK Package Location Ambiguity** (MAJOR)
  - **Issue**: Plan places `src/checkpoint/client.py` inside `backend/lambdas/incident-manager/src/checkpoint/`. But CheckpointClient is a **platform SDK** consumed by application Lambdas (batch-processor, future services). Placing it inside incident-manager creates a circular import dependency: the batch processor Lambda would need to import from incident-manager's source.
  - **Impact**: HIGH — Other Lambdas cannot import from incident-manager's `src/` directory. Packaging will fail.
  - **Pattern Violation**: `patterns/layer-architecture.md` — shared code belongs in `backend/shared/` or a Lambda Layer, not inside a specific Lambda's `src/`.
  - **Fix Options**:
    1. **Option A (Recommended)**: Place SDK in `backend/lambda-layer/python/sre_platform/checkpoint/client.py` — shared via Lambda Layer (already deployed for `shared/middleware/`). Import path: `from sre_platform.checkpoint import CheckpointClient`.
    2. **Option B**: Place in `backend/shared/checkpoint/client.py` — bundled via CDK ZIP Asset into each Lambda that needs it.
  - **Decision needed**: Which option aligns with existing shared middleware pattern? The existing `@observe` decorator lives in `backend/lambda-layer/python/shared/middleware/observability.py` — so Option A (Lambda Layer) is the established pattern.

- **[ARCH-002] DeltaReportService Needs Read-Only Query, Not CheckpointClient** (MAJOR)
  - **Issue**: The DeltaReportService (TC4) is initialized with a `checkpoint_client` to call `get_pending()` and scan checkpoints. But CheckpointClient is designed as an **application-facing write SDK** (write_checkpoint, mark_progress, etc.). The DeltaReportService needs a **platform-internal read path**: query the GSI, load checkpoints, compute deltas.
  - **Impact**: MEDIUM — Mixing the application-facing SDK with the platform-internal query path conflates two audiences and two permission models.
  - **Fix**: Either:
    1. Add `scan_incomplete(service_name)` and `get_pending(checkpoint_id)` as read-only methods on CheckpointClient (simpler, but mixes audiences).
    2. Create a thin `CheckpointRepository` class in the incident-manager's `src/repositories/` that wraps the DynamoDB query logic for the Delta Report Service. The CheckpointClient (SDK) writes; the CheckpointRepository (platform) reads. This aligns with the hexagonal architecture: different ports for different consumers.
  - **Recommendation**: Option 2 (separate repository). It keeps the SDK clean for application teams and the query logic scoped to the platform.

- **[ARCH-003] Simulation Bypasses SDK** (MINOR)
  - **Issue**: TC7 Phase 1 writes checkpoint records directly to DynamoDB using `lib/checkpoint.py` helpers, bypassing the CheckpointClient SDK. This validates the Delta Report Service but does NOT validate the SDK's `write_checkpoint()` → DynamoDB → `get_pending()` contract.
  - **Impact**: LOW — SDK is unit-tested in TC1-TC3, but there's no live AWS test proving SDK writes produce correct Delta Reports.
  - **Fix**: Add a TC7 pre-step that uses the actual SDK (deployed in the Lambda Layer) to write the checkpoint, replacing the direct DynamoDB write. Or accept this gap and add it as a TC8 follow-up.

#### Aspect-Oriented Programming

**Passed Checks (3/3)**:
- [x] `@observe` decorator specified for `generate_and_post()` in DeltaReportService
- [x] Cross-cutting concerns (logging, tracing, metrics) delegated to decorator
- [x] No manual logging in business logic methods

#### DynamoDB Configuration

**Passed Checks (7/8)**:
- [x] PAY_PER_REQUEST billing mode (correct for unpredictable workload)
- [x] GSI designed for primary access pattern (service + status)
- [x] TTL configured for auto-expiry
- [x] StringSet (SS) for `completed_items` — correct DynamoDB type for `ADD`
- [x] S3 side-loading for items > 500 (400KB limit awareness)
- [x] No Scan operations in design — all lookups via GSI query or GetItem
- [x] Conditional expressions considered for status transitions

**Issue (1)**:

- **[DYNAMO-001] `error_counts` Map Attribute — Concurrent Update Risk** (MINOR)
  - **Issue**: `log_failure()` increments `error_counts.#msg` using `ADD`. If the error message contains characters that need escaping in DynamoDB expression attribute names (dots, hyphens, spaces — common in Python exception strings), the `ADD` expression will fail.
  - **Example**: `ReadTimeout: Duck Creek API unresponsive` contains a colon and spaces — these are safe in attribute values but the map key `error_counts.ReadTimeout: Duck Creek API unresponsive` cannot be used directly in an UpdateExpression path.
  - **Fix**: Use expression attribute names for the nested key: `SET error_counts.#errkey = if_not_exists(error_counts.#errkey, :zero) + :one` with `#errkey` mapped to a sanitized key (e.g., hash or truncated). Or store error_counts as a flat list of `{message, count}` pairs instead of a map.

#### IAM Least Privilege

**Passed Checks (4/4)**:
- [x] Prefix-scoped `dynamodb:LeadingKeys` conditions per service
- [x] Triage Lambda: read-only (Query, GetItem) on checkpoint table
- [x] Application Lambdas: write-only (PutItem, UpdateItem) on own prefix
- [x] S3 prefix isolation per service

#### Error Response Format
- N/A — This is an internal platform service, not an API Gateway endpoint. No HTTP error responses needed.

---

### 3. Design Completeness (80/100)

#### v1 Spec Coverage

| v1 Deliverable | Plan Coverage | Status |
|---|---|---|
| CheckpointClient SDK (7 methods) | TC1 — full API surface, 25 tests | COMPLETE |
| DeltaReportService | TC4 — format rules, 15 tests | COMPLETE |
| `sre-checkpoints-{stage}` table + GSI | TC2/TC6 — schema, CDK | COMPLETE |
| `sre-checkpoint-manifests-{stage}` S3 bucket | TC6 — CDK | COMPLETE |
| ResolutionService enhancement | TC5 — wiring, 7 tests | COMPLETE |
| Batch processor simulation | TC7 — 12-step scenario | COMPLETE |
| CloudWatch metrics + alarms | TC6 — mentioned | PARTIAL |

#### Missing Elements

- **[COMPLETE-001] CloudWatch Metrics Implementation Detail** (MINOR)
  - The v1 spec (Section 8) defines 5 metrics (`sre.checkpoint.created`, `completed`, `items_pending`, `zombie_detected`, `failed_terminal`). TC6 mentions "CloudWatch metrics + 2 alarms" but doesn't specify where the metrics are emitted. The `@observe` decorator handles generic operation metrics, but the checkpoint-specific business metrics (e.g., `items_pending` gauge at Delta Report time) need explicit emit points.
  - **Fix**: Add to TC4 — DeltaReportService emits `sre.checkpoint.items_pending` and `sre.checkpoint.zombie_detected` during `generate_and_post()`. TC1 — CheckpointClient emits `sre.checkpoint.created` in `write_checkpoint()` and `sre.checkpoint.completed` in `complete()`.

- **[COMPLETE-002] Recovery Catalog Schema Change Not Explicit** (MINOR)
  - TC5 shows the recovery catalog entry with `checkpoint_aware: true, auto_recover: false`, but doesn't specify that `IncidentConfig` dataclass needs a new field or that the catalog entry parsing needs to handle the new keys. The existing `recovery_catalog` in `incident_config.json` has `type`, `workflow_arn_env` only.
  - **Fix**: TC5 should explicitly list `src/models/config.py` as modified to parse `checkpoint_aware` and `auto_recover` from catalog entries.

- **[COMPLETE-003] `DELTA_REPORTED` Status in EventBridge Event** (MINOR)
  - TC5 adds `RecoveryStatus.DELTA_REPORTED` but doesn't specify how this surfaces in the `IncidentAutoResolved` EventBridge event. The existing triage flow publishes `recovery_status` in the event — confirm that `delta-reported` is a valid value downstream consumers can handle.
  - **Fix**: Document in TC5 that the EventBridge event `recovery_status` field will contain `"delta-reported"` and that no downstream consumer currently depends on specific values (safe to add).

#### API Design Completeness
- N/A for v1 — no new API Gateway endpoints (Big Red Button is v2). Correct scope decision.

#### Implementation Plan File-Level Detail
- [x] All files listed per task
- [x] Class signatures defined (CheckpointClient, DeltaReportService)
- [x] Test scenarios enumerated with expected outcomes
- [x] Dependencies between tasks clear (TC1 → TC2 → TC3, TC4 → TC5)

---

### 4. Design Quality (85/100)

#### Architectural Quality

**Strengths**:
- **Sharp scope boundary**: v1 = observability only. No feature creep.
- **Forward compatibility**: `auto_recover: false` → `true` is a config change, not a code change. Excellent v1 → v2 bridge.
- **SDK simplicity**: 7 methods, fire-and-forget. The 30-minute onboarding target is achievable.
- **Hybrid flush strategy**: Flush by count OR time prevents both hot DynamoDB writes (fast batches) and stale checkpoints (slow batches).
- **`log_failure()` as optional**: Applications don't need to implement error reporting — but if they do, the Delta Report gets dramatically more useful. Smart API design.
- **Simulation design**: Phase 1 (create failure state) + Phase 2 (trigger real pipeline) is a pragmatic approach that avoids deploying a batch Lambda just for v1.

**Concerns**:

- **[QUALITY-001] Buffer State Lost on Lambda Freeze** (MINOR)
  - `mark_progress_buffered()` accumulates items in `self._buffers[checkpoint_id]` (in-memory). If Lambda is frozen between flushes (Lambda runtime freeze, not timeout), the buffer is lost. On thaw, the buffer is empty — items processed during the frozen window appear as "pending" in the Delta Report.
  - **Impact**: LOW — this is documented as a trade-off ("Up to `flush_every - 1` items may appear as pending"). The idempotency requirement on application writes handles the reprocessing case.
  - **Recommendation**: Add a note in the SDK docstring that `flush_progress()` should be called before any `time.sleep()` or long I/O operation, not just at the end of processing.

- **[QUALITY-002] StringSet Empty Set Edge Case** (MINOR)
  - DynamoDB does not allow empty StringSets. If `write_checkpoint()` creates `completed_items` as an empty SS, the PutItem will fail. The initial write should either omit `completed_items` entirely or write a sentinel.
  - **Fix**: `write_checkpoint()` should NOT include `completed_items` in the initial PutItem. The first `mark_progress()` call will create the attribute via `ADD`. `get_pending()` should handle `completed_items` being absent (treat as empty set).

- **[QUALITY-003] Delta Report Timing — Race Condition** (MINOR)
  - The Delta Report runs inside `trigger_recovery()`, which runs during the Triage phase. If the batch processor is still running (slow but not dead), the checkpoint `completed_items` may grow between the Delta Report computation and the Jira comment. The report could show 5 pending items, but by the time an engineer reads it, only 3 are actually pending.
  - **Impact**: LOW — the cool-off period (30s for SEV-1) and triage processing time (~6s) provide a natural buffer. If the batch was going to complete, it likely would have done so during cool-off.
  - **Recommendation**: Add a note to the Delta Report: `"Snapshot at {timestamp} — run get_pending() for current state"`.

#### Data Model Quality
- [x] Access patterns drive GSI design (service + status query)
- [x] High-cardinality partition key (`checkpoint_id` is globally unique)
- [x] No hot partition risk (checkpoints are per-batch, well-distributed)
- [x] TTL prevents unbounded growth
- [x] StringSet for `completed_items` is the correct DynamoDB type

#### Dependency Direction
```
CheckpointClient (SDK, Lambda Layer)
       ↑ writes
Application Lambdas (batch-processor, etc.)

       ↓ reads (via CheckpointRepository)
DeltaReportService (incident-manager service layer)
       ↓ posts
TicketingRepository (Jira API)
```
Clean unidirectional dependency. No circular references.

---

### 5. Feasibility (90/100)

#### Technical Feasibility
- [x] All technologies are approved and deployed (DynamoDB, S3, Lambda Layer, CDK)
- [x] Team has expertise (incident-manager already uses same patterns)
- [x] No experimental technologies
- [x] AWS service quotas sufficient (checkpoint table is low-volume in v1)
- [x] Lambda limits not a concern (Delta Report runs inside Triage Lambda, well within 5min timeout)

#### Cost Feasibility

| Resource | Estimated Monthly Cost (dev) | Notes |
|---|---|---|
| DynamoDB `sre-checkpoints-dev` | < $1 | PAY_PER_REQUEST, low volume |
| S3 `sre-checkpoint-manifests-dev` | < $0.10 | Small manifests, 30-day lifecycle |
| Additional Triage Lambda duration | < $0.50 | Delta Report adds ~1-2s per triage |
| CloudWatch metrics (5 custom) | $1.50 | $0.30 per metric |
| **Total incremental** | **< $4/month** | |

No cost concerns.

#### Implementation Risk Assessment

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| SDK package location confusion (ARCH-001) | HIGH | HIGH | Resolve before TC1 — use Lambda Layer path |
| DynamoDB empty StringSet (QUALITY-002) | MEDIUM | HIGH | Handle in TC1 write_checkpoint() |
| Delta Report format not useful to engineers | MEDIUM | LOW | Validate format with team before TC4 coding |
| Simulation writes don't match SDK schema | LOW | MEDIUM | Use SDK in simulation or add schema validation test |

#### One-Week Delivery Feasibility
- TC1-TC3 (SDK): 2 days — 7 methods + 33 tests is achievable
- TC4-TC5 (Delta Report + wiring): 2 days — follows existing service patterns
- TC6-TC7 (CDK + simulation): 1 day — CDK additions are small, simulation reuses existing lib

**Assessment**: One-week delivery is feasible if ARCH-001 is resolved upfront.

---

### 6. Consistency (80/100)

#### Naming Consistency
- [x] Table naming: `sre-checkpoints-{stage}` follows existing `incident-correlation-{stage}` pattern
- [x] S3 naming: `sre-checkpoint-manifests-{stage}` follows platform convention
- [x] Checkpoint ID format: `{type}:{service}:{id}` is consistent and parseable
- [x] Service naming: `batch-processor-api-dev` follows `{service}-api-{stage}` convention
- [x] Test file naming: `test_checkpoint_client.py`, `test_delta_report_service.py` — consistent

#### Pattern Consistency
- [x] `@observe` decorator on all public methods — matches existing services
- [x] Moto for DynamoDB tests — matches existing test pattern
- [x] Mock fixtures in conftest.py — matches existing pattern
- [x] Service → repository delegation — matches existing pattern

#### Issue

- **[CONSIST-001] Inconsistent Module Path** (MINOR)
  - Plan says `src/checkpoint/client.py` but also says `from sre_platform.checkpoint import CheckpointClient` (in the v1 spec). These are different import paths. Need to resolve based on ARCH-001 decision.

---

### 7. Documentation Quality (72/100)

#### Strengths
- Excellent MVP grouping with clear "what it proves" per MVP
- Test scenarios are specific and enumerable
- Cross-reference tables (tasks → deliverables, tasks → success criteria)
- Simulation flow is detailed with 12 numbered steps and validation points
- Cumulative progress table is clear

#### Issues

- **[DOC-001] Missing Architecture Diagram** (MINOR)
  - No visual diagram showing how CheckpointClient, DeltaReportService, ResolutionService, and the existing pipeline connect. The v1 spec has a responsibility split table, but the implementation plan should show the data flow with component names.

- **[DOC-002] Missing Class Signatures for DeltaReportService** (MINOR)
  - TC4 shows method signatures but not constructor parameters. Compare with TC1 which shows the full `__init__` signature for CheckpointClient.
  - **Fix**: Add `__init__(self, table_name, bucket_name, ticketing_repo, config)` or clarify the dependency injection pattern.

- **[DOC-003] TC5 Wiring Flow Could Be Clearer** (MINOR)
  - The pseudo-code shows the decision branch but doesn't specify exactly which lines of `resolution_service.py` change. Given the existing file is 191 lines and well-structured, a before/after snippet for `trigger_recovery()` would be clearer.

- **[DOC-004] No Deployment Sequence** (MINOR)
  - TC6 deploys CDK. TC7 runs simulation. But TC5 modifies Resolution Service code — when is the Triage Lambda redeployed? The plan should note that TC6 includes redeployment of the Triage Lambda with the TC4+TC5 code changes.

---

## Issue Summary

| Severity | Count | Must Fix Before Implementation |
|----------|-------|-------------------------------|
| CRITICAL | 0 | -- |
| MAJOR | 2 | YES |
| MINOR | 9 | NO (but recommended) |
| INFO/WARN | 2 | NO |

---

## Recommended Actions

### RESOLVED (2026-04-02)

1. **[ARCH-001] SDK package location** — RESOLVED. Lambda Layer at `backend/lambda-layer/python/sre_platform/checkpoint/client.py`. TC1 file paths updated.

2. **[ARCH-002] Separate CheckpointRepository from CheckpointClient** — RESOLVED. `src/repositories/checkpoint_repository.py` added to TC4. SDK writes, repository reads. DeltaReportService depends on repository.

### Recommended Improvements (Address During Implementation)

3. **[QUALITY-002]** Handle empty StringSet in `write_checkpoint()` — omit `completed_items` from initial PutItem.
4. **[DYNAMO-001]** Sanitize error message keys in `error_counts` map — use truncated hash or escaped key.
5. **[COMPLETE-001]** Specify metric emit points in TC1 and TC4.
6. **[COMPLETE-002]** Add `checkpoint_aware` and `auto_recover` to IncidentConfig parsing in TC5.
7. **[DOC-004]** Clarify that TC6 includes Triage Lambda redeployment with TC4+TC5 code.
8. **[WARN-001]** Add S3 lifecycle rule in TC6 CDK.
9. **[ARCH-003]** Consider using SDK (not direct DynamoDB) in simulation Phase 1.

---

## Requirements Traceability

| v1 Success Criterion | Implementation Task | Verification |
|---|---|---|
| Zero Blind Spots | TC4 (Delta Report) + TC7 (simulation step 11) | Jira shows exact pending items |
| Zombie Awareness | TC1 (`heartbeat`) + TC4 (`_detect_zombie`) + TC3 (tests 7-8) | 2x threshold detection |
| Low Friction | TC1 (SDK API surface) | 7 methods, 30-min integration |
| Correct Delta | TC1 (`get_pending`) + TC3 (tests 1-6) | Unit tests + integration |
| Error Context | TC1 (`log_failure`) + TC4 (report format tests 8-11) | error_counts in report |
| IAM Isolation | TC6 (CDK prefix-scoped grants) | IAM policy test |
| No False Zombies | TC1/TC3 (2x threshold) + TC4 (`_detect_zombie`) | Unit tests |

---

## Approval Checklist

Developer must verify:
- [ ] ARCH-001 resolved: SDK package location decided
- [ ] ARCH-002 resolved: CheckpointRepository vs CheckpointClient separation decided
- [ ] All MINOR items acknowledged (fix during implementation or defer)
- [ ] One-week timeline still achievable with the above changes
- [ ] Team reviewed Delta Report format (TC4) for usefulness

---

## Developer Sign-Off

**Status**: [ ] APPROVED / [ ] CHANGES REQUESTED / [ ] REJECTED

**Developer Name**: _______________
**Date**: _______________
**Comments**:

---

## Next Steps

If APPROVED:
1. Resolve ARCH-001 and ARCH-002 decisions
2. Update implementation plan with resolved file paths
3. Begin TC1: Checkpoint SDK
4. Follow MVP sequence: TC1 → TC2 → TC3 (MVP A) → TC4 → TC5 (MVP B) → TC6 → TC7 (MVP C)
