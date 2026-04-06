# Incident Management Pipeline -- Test Plan

## Source

- `docs/specs/incident-manager/requirements.md` (FR-001 through FR-020, FR-015a, NFR-001 through NFR-008)
- `docs/specs/incident-manager/app-design.md` (architecture, models, services, repositories, flows)

## Test Strategy

### Approach

The incident manager is event-driven (SNS/EventBridge), not HTTP-triggered. Testing focuses on:

1. **Unit tests** -- per layer (models, services, handlers, repositories) with mocked dependencies
2. **Integration tests** -- end-to-end pipeline flows using moto (DynamoDB) + mocked external services (Jira, CloudWatch Logs)
3. **Scenario tests** -- complex multi-step scenarios (storm detection, race conditions, recovery models, grace period)

### Tools

| Tool | Purpose |
|------|---------|
| pytest 7.4.3 | Test framework |
| pytest-cov | Coverage measurement |
| pytest-mock | Mock/patch utilities |
| moto | AWS service mocking (DynamoDB, SQS, SNS, EventBridge, CloudWatch, Step Functions) |
| freezegun | Deterministic datetime for TTL, cool-off, and grace period tests |

### Coverage Target

80% minimum per Lambda (per CLAUDE.md). Target breakdown:

| Layer | Target |
|-------|--------|
| Models (alarm_event, correlation_record, config, enums) | 95%+ |
| Services (detection, triage, escalation) | 85%+ |
| Handlers (detection, triage, escalation) | 80%+ |
| Repositories (correlation, observability, integration) | 80%+ |

### Test File Structure

```
backend/lambdas/incident-manager/tests/
+-- conftest.py                        # Shared fixtures (events, records, config, mocks)
+-- unit/
|   +-- test_models.py                 # AlarmEvent, CorrelationRecord, IncidentConfig, enums
|   +-- test_detection_service.py      # DetectionService logic
|   +-- test_triage_service.py         # TriageService logic
|   +-- test_escalation_service.py     # EscalationService logic
|   +-- test_detection_handler.py      # Detection Lambda handler
|   +-- test_triage_handler.py         # Triage Lambda handler
|   +-- test_escalation_handler.py     # Escalation Lambda handler
|   +-- test_correlation_repository.py # DynamoDB operations (moto)
|   +-- test_observability_repository.py # CloudWatch operations (moto)
|   +-- test_integration_repository.py # Jira/SNS/EventBridge/SFN operations (mock)
+-- integration/
    +-- test_pipeline.py               # End-to-end pipeline flow tests
```

---

## Shared Test Fixtures (`conftest.py`)

```python
"""Shared test fixtures for incident manager tests."""

import pytest
import json
from unittest.mock import Mock, MagicMock
from datetime import datetime, timezone, timedelta
from freezegun import freeze_time
from moto import mock_dynamodb

from src.models.alarm_event import AlarmEvent
from src.models.correlation_record import CorrelationRecord
from src.models.enums import CorrelationStatus, Severity, RecoveryModel
from src.models.config import IncidentConfig
from src.models.exceptions import DuplicateIncidentError, AlarmParsingError


# ------------------------------------------------------------------ #
# Configuration
# ------------------------------------------------------------------ #

@pytest.fixture
def incident_config():
    """Standard incident config for testing."""
    return IncidentConfig(
        severity_mapping={
            "error-rate": {"severity": "SEV-1", "recovery_model": "stateless"},
            "latency": {"severity": "SEV-2", "recovery_model": "stateless"},
            "4xx-errors": {"severity": "SEV-3", "recovery_model": "stateless"},
            "queue-backlog": {"severity": "SEV-2", "recovery_model": "replay"},
            "batch-failure": {"severity": "SEV-1", "recovery_model": "reprocess"},
            "data-integrity": {"severity": "SEV-1", "recovery_model": "data-correction"},
        },
        cool_off_seconds={"SEV-1": 30, "SEV-2": 60, "SEV-3": 120},
        verification_wait_seconds={"SEV-1": 60, "SEV-2": 90, "SEV-3": 120},
        grace_period_seconds=900,
        reservation_timeout_seconds=180,
        triage_timeout_seconds=120,
        log_analysis_window_minutes=15,
        max_log_events=500,
        correlation_ttl_hours=24,
        storm_window_seconds=120,
        storm_threshold=5,
        remediation_catalog={
            "bad-deployment": {"action": "lambda-version-rollback"},
            "performance-degradation": {"action": "lambda-memory-increase"},
            "rate-limit": {"action": "increase-concurrency"},
        },
        recovery_catalog={
            "replay": {"type": "step_function", "workflow_arn_env": "REPLAY_DLQ_WORKFLOW_ARN"},
            "reprocess": {"type": "step_function", "workflow_arn_env": "REPROCESS_BATCH_WORKFLOW_ARN"},
            "data-correction": {"type": "step_function", "workflow_arn_env": "RECONCILIATION_WORKFLOW_ARN"},
            "backlog-drain": {"type": "lambda", "function_name_env": "BACKLOG_DRAIN_FUNCTION_NAME"},
        },
        classification_rules=[
            {"pattern": "import_or_syntax_error", "classification": "bad-deployment", "confidence": "high"},
            {"pattern": "single_error_dominant", "classification": "specific-bug", "confidence": "high"},
            {"pattern": "throttling_errors", "classification": "rate-limit", "confidence": "high"},
        ],
    )


# ------------------------------------------------------------------ #
# Datetime
# ------------------------------------------------------------------ #

@pytest.fixture
def fixed_now():
    """Fixed datetime for deterministic tests."""
    return datetime(2026, 3, 30, 12, 0, 0, tzinfo=timezone.utc)


# ------------------------------------------------------------------ #
# AlarmEvent fixtures
# ------------------------------------------------------------------ #

@pytest.fixture
def alarm_event_sev1(fixed_now):
    """SEV-1 error-rate alarm (stateless recovery)."""
    return AlarmEvent(
        alarm_name="calculator-high-error-rate-prod",
        alarm_description="Error rate exceeds threshold",
        new_state="ALARM",
        old_state="OK",
        reason="Threshold crossed",
        state_change_time=fixed_now,
        region="us-west-2",
        account_id="320644769527",
        service="calculator",
        alarm_type="error-rate",
        stage="prod",
        severity=Severity.SEV_1,
        recovery_model="stateless",
    )


@pytest.fixture
def alarm_event_sev2_latency(fixed_now):
    """SEV-2 latency alarm (stateless recovery)."""
    return AlarmEvent(
        alarm_name="calculator-high-latency-prod",
        alarm_description="Latency exceeds threshold",
        new_state="ALARM",
        old_state="OK",
        reason="Threshold crossed",
        state_change_time=fixed_now,
        region="us-west-2",
        account_id="320644769527",
        service="calculator",
        alarm_type="latency",
        stage="prod",
        severity=Severity.SEV_2,
        recovery_model="stateless",
    )


@pytest.fixture
def alarm_event_queue_backlog(fixed_now):
    """SEV-2 queue-backlog alarm (replay recovery)."""
    return AlarmEvent(
        alarm_name="payments-high-queue-backlog-prod",
        alarm_description="SQS queue depth exceeds threshold",
        new_state="ALARM",
        old_state="OK",
        reason="Queue depth > 50000",
        state_change_time=fixed_now,
        region="us-west-2",
        account_id="320644769527",
        service="payments",
        alarm_type="queue-backlog",
        stage="prod",
        severity=Severity.SEV_2,
        recovery_model="replay",
    )


@pytest.fixture
def alarm_event_batch_failure(fixed_now):
    """SEV-1 batch-failure alarm (reprocess recovery)."""
    return AlarmEvent(
        alarm_name="settlement-high-batch-failure-prod",
        alarm_description="Daily settlement batch failed",
        new_state="ALARM",
        old_state="OK",
        reason="Batch job failed",
        state_change_time=fixed_now,
        region="us-west-2",
        account_id="320644769527",
        service="settlement",
        alarm_type="batch-failure",
        stage="prod",
        severity=Severity.SEV_1,
        recovery_model="reprocess",
    )


@pytest.fixture
def alarm_event_data_integrity(fixed_now):
    """SEV-1 data-integrity alarm (data-correction recovery)."""
    return AlarmEvent(
        alarm_name="payments-high-data-integrity-prod",
        alarm_description="Duplicate transactions detected",
        new_state="ALARM",
        old_state="OK",
        reason="Duplicate transaction count > threshold",
        state_change_time=fixed_now,
        region="us-west-2",
        account_id="320644769527",
        service="payments",
        alarm_type="data-integrity",
        stage="prod",
        severity=Severity.SEV_1,
        recovery_model="data-correction",
    )


@pytest.fixture
def recovery_event(fixed_now):
    """Recovery event (OK state transition)."""
    return AlarmEvent(
        alarm_name="calculator-high-error-rate-prod",
        alarm_description="Error rate exceeds threshold",
        new_state="OK",
        old_state="ALARM",
        reason="Threshold returned to normal",
        state_change_time=fixed_now,
        region="us-west-2",
        account_id="320644769527",
        service="calculator",
        alarm_type="error-rate",
        stage="prod",
        severity=Severity.SEV_1,
        recovery_model="stateless",
    )


# ------------------------------------------------------------------ #
# CorrelationRecord fixtures
# ------------------------------------------------------------------ #

@pytest.fixture
def reserved_record(fixed_now):
    """DynamoDB record in RESERVED state (no Jira ticket yet)."""
    return CorrelationRecord(
        incident_key="calculator-error-rate-prod",
        jira_ticket_id=None,
        severity="SEV-1",
        status=CorrelationStatus.RESERVED,
        created_at=fixed_now,
        ttl=int((fixed_now + timedelta(hours=24)).timestamp()),
    )


@pytest.fixture
def detected_record(fixed_now):
    """DynamoDB record in DETECTED state (Jira ticket exists)."""
    return CorrelationRecord(
        incident_key="calculator-error-rate-prod",
        jira_ticket_id="INC-142",
        severity="SEV-1",
        status=CorrelationStatus.DETECTED,
        created_at=fixed_now,
        ttl=int((fixed_now + timedelta(hours=24)).timestamp()),
    )


@pytest.fixture
def triaging_record(fixed_now):
    """DynamoDB record in TRIAGING state."""
    return CorrelationRecord(
        incident_key="calculator-error-rate-prod",
        jira_ticket_id="INC-142",
        severity="SEV-1",
        status=CorrelationStatus.TRIAGING,
        created_at=fixed_now,
        ttl=int((fixed_now + timedelta(hours=24)).timestamp()),
    )


@pytest.fixture
def grace_record(fixed_now):
    """DynamoDB record in GRACE state (auto-resolved, 15-min TTL)."""
    return CorrelationRecord(
        incident_key="calculator-error-rate-prod",
        jira_ticket_id="INC-142",
        severity="SEV-1",
        status=CorrelationStatus.GRACE,
        created_at=fixed_now,
        ttl=int((fixed_now + timedelta(minutes=15)).timestamp()),
    )


# ------------------------------------------------------------------ #
# SNS Event fixtures
# ------------------------------------------------------------------ #

@pytest.fixture
def sns_alarm_event():
    """SNS event wrapping a CloudWatch Alarm ALARM notification."""
    return {
        "Records": [{
            "Sns": {
                "Message": json.dumps({
                    "AlarmName": "calculator-high-error-rate-prod",
                    "AlarmDescription": "Error rate exceeds threshold",
                    "NewStateValue": "ALARM",
                    "OldStateValue": "OK",
                    "NewStateReason": "Threshold crossed",
                    "StateChangeTime": "2026-03-30T12:00:00.000+0000",
                    "Region": "US West (Oregon)",
                    "AWSAccountId": "320644769527",
                })
            }
        }]
    }


@pytest.fixture
def sns_recovery_event():
    """SNS event wrapping a CloudWatch Alarm OK notification."""
    return {
        "Records": [{
            "Sns": {
                "Message": json.dumps({
                    "AlarmName": "calculator-high-error-rate-prod",
                    "AlarmDescription": "Error rate exceeds threshold",
                    "NewStateValue": "OK",
                    "OldStateValue": "ALARM",
                    "NewStateReason": "Threshold returned to normal",
                    "StateChangeTime": "2026-03-30T12:30:00.000+0000",
                    "Region": "US West (Oregon)",
                    "AWSAccountId": "320644769527",
                })
            }
        }]
    }


# ------------------------------------------------------------------ #
# EventBridge Event fixtures
# ------------------------------------------------------------------ #

@pytest.fixture
def incident_created_event():
    """EventBridge IncidentCreated event for Triage Lambda."""
    return {
        "source": "incident-manager",
        "detail-type": "IncidentCreated",
        "detail": {
            "incident_key": "calculator-error-rate-prod",
            "jira_ticket_id": "INC-142",
            "service": "calculator",
            "stage": "prod",
            "severity": "SEV-1",
            "recovery_model": "stateless",
            "storm_detected": False,
            "timestamp": "2026-03-30T12:00:00Z",
        },
    }


@pytest.fixture
def incident_created_storm_event():
    """EventBridge IncidentCreated event with storm_detected=True."""
    return {
        "source": "incident-manager",
        "detail-type": "IncidentCreated",
        "detail": {
            "incident_key": "calculator-error-rate-prod",
            "jira_ticket_id": "INC-142",
            "service": "calculator",
            "stage": "prod",
            "severity": "SEV-1",
            "recovery_model": "stateless",
            "storm_detected": True,
            "active_incident_count": 12,
            "timestamp": "2026-03-30T12:00:00Z",
        },
    }


@pytest.fixture
def incident_created_replay_event():
    """EventBridge IncidentCreated event with replay recovery model."""
    return {
        "source": "incident-manager",
        "detail-type": "IncidentCreated",
        "detail": {
            "incident_key": "payments-queue-backlog-prod",
            "jira_ticket_id": "INC-200",
            "service": "payments",
            "stage": "prod",
            "severity": "SEV-2",
            "recovery_model": "replay",
            "storm_detected": False,
            "timestamp": "2026-03-30T12:00:00Z",
        },
    }


@pytest.fixture
def escalation_required_event():
    """EventBridge EscalationRequired event for Escalation Lambda."""
    return {
        "source": "incident-manager",
        "detail-type": "EscalationRequired",
        "detail": {
            "incident_key": "calculator-error-rate-prod",
            "jira_ticket_id": "INC-142",
            "service": "calculator",
            "stage": "prod",
            "severity": "SEV-1",
            "reason": "verification-failed",
            "timestamp": "2026-03-30T12:10:00Z",
        },
    }


# ------------------------------------------------------------------ #
# Mock repositories
# ------------------------------------------------------------------ #

@pytest.fixture
def mock_correlation_repo():
    """Mock CorrelationRepository."""
    repo = Mock()
    repo.get.return_value = None
    repo.reserve.return_value = True
    repo.update.return_value = None
    repo.delete.return_value = None
    repo.count_recent.return_value = 0
    return repo


@pytest.fixture
def mock_observability_repo():
    """Mock ObservabilityRepository."""
    repo = Mock()
    repo.get_alarm_state.return_value = "ALARM"
    repo.get_state_change_time.return_value = datetime(2026, 3, 30, 12, 0, 0, tzinfo=timezone.utc)
    repo.collect_errors.return_value = [{"message": "DivisionByZeroError", "timestamp": "2026-03-30T12:00:00Z"}]
    repo.collect_recent.return_value = []
    return repo


@pytest.fixture
def mock_integration_repo():
    """Mock IntegrationRepository."""
    repo = Mock()
    repo.create_jira_ticket.return_value = "INC-142"
    repo.add_jira_comment.return_value = True
    repo.attach_jira_file.return_value = True
    repo.transition_jira_ticket.return_value = True
    repo.rollback_lambda_version.return_value = {"status": "success"}
    repo.increase_lambda_memory.return_value = {"status": "success"}
    repo.increase_concurrency.return_value = {"status": "success"}
    repo.notify_engineer.return_value = True
    repo.publish_event.return_value = True
    repo.trigger_step_function.return_value = "arn:aws:states:us-west-2:320644769527:execution:ReplayDLQ:exec-123"
    repo.trigger_recovery_lambda.return_value = {"StatusCode": 202}
    return repo


@pytest.fixture
def lambda_context():
    """Mock Lambda context."""
    context = Mock()
    context.function_name = "incident-detection-dev"
    context.aws_request_id = "test-request-id"
    return context
```

---

## Traceability Matrix

### Leg 1 -- Detection

| AC | Description | Test Type | Test Name | Layer |
|----|-------------|-----------|-----------|-------|
| AC-001 | CloudWatch ALARM triggers Detection Lambda via SNS | Unit | test_handler_processes_sns_alarm_record | Handler |
| AC-002 | Severity + recovery_model classified from externalized severity_mapping | Unit | test_alarm_event_severity_classification | Model |
| AC-002 | Recovery model extracted from severity_mapping | Unit | test_alarm_event_recovery_model_classification | Model |
| AC-003 | Service, alarm type, stage extracted from alarm name | Unit | test_alarm_event_metadata_extraction | Model |
| AC-004 | Transient spike filtered by cool-off | Unit | test_cool_off_filters_transient_spike | Service |
| AC-005 | Persistent alarm creates incident | Unit | test_persistent_alarm_creates_incident | Service |
| AC-006 | Reserve-then-create prevents duplicate Jira tickets | Unit | test_reserve_then_create_prevents_duplicates | Service |
| AC-007 | RESERVED conflict exits silently | Unit | test_conflict_reserved_exits_silently | Service |
| AC-008 | DETECTED conflict adds duplicate comment | Unit | test_conflict_detected_adds_jira_comment | Service |
| AC-009 | GRACE conflict handles recurrence | Unit | test_conflict_grace_handles_recurrence | Service |
| AC-010 | Jira creation failure deletes reserved record | Unit | test_jira_failure_cleans_up_reservation | Service |
| AC-011 | Storm detected when threshold exceeded | Unit | test_storm_detected_above_threshold | Service |
| AC-012 | Storm flag in IncidentCreated event | Unit | test_storm_flag_in_event | Service |
| AC-013 | Jira ticket created with correct fields | Unit | test_jira_ticket_creation_fields | Service |
| AC-014 | IncidentCreated published to EventBridge with recovery_model | Unit | test_incident_created_event_published | Service |
| AC-015 | New service onboards with alarm action only | Integration | test_new_service_alarm_onboarding | Pipeline |

### Leg 2 -- Triage

| AC | Description | Test Type | Test Name | Layer |
|----|-------------|-----------|-----------|-------|
| AC-016 | Error logs collected within bounded window | Unit | test_log_collection_bounded | Service |
| AC-017 | Error summary includes grouping and affected ops | Unit | test_error_analysis_summary | Service |
| AC-018 | Root cause classified with confidence | Unit | test_root_cause_classification | Service |
| AC-019 | Blast radius assessed | Unit | test_blast_radius_assessment | Service |
| AC-020 | Storm: analysis runs, remediation skipped | Unit | test_storm_skips_remediation_runs_analysis | Service |
| AC-021 | Single remediation attempt enforced | Unit | test_single_remediation_attempt | Service |
| AC-022 | Remediation looked up from catalog | Unit | test_remediation_catalog_lookup | Service |
| AC-023 | No catalog match escalates | Unit | test_no_remediation_escalates | Service |
| AC-024 | Verification wait observed | Unit | test_verification_wait_period | Service |
| AC-025 | 3-point verification performed | Unit | test_three_point_verification | Service |
| AC-026 | All checks pass: resolved + GRACE | Unit | test_auto_resolution_grace_transition | Service |
| AC-027 | Resolution evidence attached to Jira | Unit | test_resolution_evidence_in_jira | Service |
| AC-028 | IncidentAutoResolved published with recovery_model | Unit | test_auto_resolved_event_with_recovery | Service |
| AC-029 | No notification for auto-resolved | Unit | test_no_notification_on_auto_resolve | Service |
| AC-030 | Grace recurrence escalates | Unit | test_grace_recurrence_escalates | Service |
| AC-031 | Verification failure escalates | Unit | test_verification_failure_escalates | Service |
| AC-032 | Triage steps add Jira comments | Unit | test_triage_jira_comments | Service |

### Leg 3 -- Escalation

| AC | Description | Test Type | Test Name | Layer |
|----|-------------|-----------|-----------|-------|
| AC-033 | Jira enriched with diagnostics | Unit | test_jira_enrichment_content | Service |
| AC-034 | Logs and traces attached | Unit | test_log_attachment_to_jira | Service |
| AC-035 | Links included in ticket | Unit | test_dashboard_links_in_jira | Service |
| AC-036 | Copy-paste commands included | Unit | test_investigation_commands | Service |
| AC-037 | Engineer can investigate without scripts | Unit | test_enrichment_completeness | Service |
| AC-038 | Escalation reason in enrichment | Unit | test_escalation_reason_in_jira | Service |
| AC-039 | SNS for SEV-1 and SEV-2 | Unit | test_notification_sev1_sev2 | Service |
| AC-040 | No SNS for SEV-3 | Unit | test_no_notification_sev3 | Service |

### Recovery & Resolution

| AC | Description | Test Type | Test Name | Layer |
|----|-------------|-----------|-----------|-------|
| AC-041 | Recovery resolves matching incident | Unit | test_recovery_resolves_incident | Service |
| AC-042 | Resolution diagnostics collected | Unit | test_recovery_diagnostics_collected | Service |
| AC-043 | Recovery logs attached to Jira | Unit | test_recovery_logs_attached | Service |
| AC-044 | DynamoDB deleted on recovery | Unit | test_recovery_deletes_dynamodb | Service |
| AC-045 | No matching incident: log and skip | Unit | test_recovery_no_match_skips | Service |
| AC-061 | Stateless: no recovery action | Unit | test_stateless_no_recovery_action | Service |
| AC-062 | Replay: DLQ workflow triggered | Unit | test_replay_triggers_dlq_workflow | Service |
| AC-063 | Reprocess: batch workflow triggered | Unit | test_reprocess_triggers_batch_workflow | Service |
| AC-064 | Data-correction: reconciliation triggered | Unit | test_data_correction_triggers_reconciliation | Service |
| AC-065 | Backlog-drain: scaling triggered | Unit | test_backlog_drain_triggers_scaling | Service |
| AC-066 | Recovery catalog from config | Unit | test_recovery_catalog_lookup | Service |
| AC-067 | Execution ID in Jira comment | Unit | test_recovery_execution_id_in_jira | Service |
| AC-068 | Recovery failure doesn't block resolution | Unit | test_recovery_failure_still_resolves | Service |
| AC-069 | System never processes business data | Unit | test_recovery_is_orchestration_only | Service |
| AC-070 | Recovery payloads include idempotency keys | Unit | test_recovery_idempotency_keys | Service |
| AC-071 | Stale RESERVED record reclaimed | Unit | test_stale_reserved_recovery | Service |
| AC-072 | Triage timeout escalates | Unit | test_triage_timeout_escalation | Service |
| AC-073 | Root cause classification string-based | Unit | test_root_cause_string_classification | Service |

### Cross-Cutting

| AC | Description | Test Type | Test Name | Layer |
|----|-------------|-----------|-----------|-------|
| AC-046 | @observe decorator with domain context | Unit | test_observe_domain_context | Service |
| AC-047 | incident_key in every log entry | Unit | test_incident_key_in_logs | Service |
| AC-048 | Jira credentials from Secrets Manager | Unit | test_jira_credentials_source | Repository |
| AC-049 | Least-privilege IAM | Infra | (CDK assertion) | Stack |
| AC-050 | Failure isolation between steps | Unit | test_step_failure_isolation | Service |
| AC-051 | Hexagonal architecture | Structural | (import analysis) | All |
| AC-052 | Duplicate SNS/EventBridge safe | Unit | test_idempotent_processing | Service |
| AC-053 | Failed events in DLQ | Integration | test_dlq_capture | Pipeline |
| AC-054 | DLQ depth alarm | Infra | (CDK assertion) | Stack |
| AC-055 | Operational metrics emitted | Unit | test_metrics_emission | Service |
| AC-056 | Dashboard shows effectiveness | Infra | (CDK assertion) | Stack |
| AC-057 | Active TTL = 24 hours | Unit | test_active_record_ttl | Model |
| AC-058 | GRACE TTL = 15 minutes | Unit | test_grace_record_ttl | Model |
| AC-059 | Lambda timeouts correct | Infra | (CDK assertion) | Stack |
| AC-060 | Config loaded at cold start | Unit | test_config_cold_start_load | Model |

---

## Practice Scenarios

These scenarios define the exact test logic. Each becomes a test function during implementation.

---

### Scenario Group 1: Model Layer

#### S1.1: AlarmEvent Parsing

```
GIVEN  an SNS message with AlarmName "calculator-high-error-rate-prod"
AND    severity_mapping has "error-rate" -> {severity: "SEV-1", recovery_model: "stateless"}
WHEN   AlarmEvent.from_sns_message(message, severity_mapping)
THEN   alarm_event.service == "calculator"
AND    alarm_event.alarm_type == "error-rate"
AND    alarm_event.stage == "prod"
AND    alarm_event.severity == Severity.SEV_1
AND    alarm_event.recovery_model == "stateless"
AND    alarm_event.incident_key == "calculator-error-rate-prod"
AND    alarm_event.is_alarm == True
AND    alarm_event.is_recovery == False
```

#### S1.2: AlarmEvent Recovery Model Classification

```
GIVEN  severity_mapping has "queue-backlog" -> {severity: "SEV-2", recovery_model: "replay"}
AND    an SNS message with AlarmName "payments-high-queue-backlog-prod"
WHEN   AlarmEvent.from_sns_message(message, severity_mapping)
THEN   alarm_event.severity == Severity.SEV_2
AND    alarm_event.recovery_model == "replay"
```

#### S1.3: AlarmEvent Invalid Alarm Name

```
GIVEN  an SNS message with AlarmName "malformed-alarm-name"
WHEN   AlarmEvent.from_sns_message(message, severity_mapping)
THEN   raises AlarmParsingError
```

#### S1.4: CorrelationRecord Reserve Factory

```
GIVEN  alarm_event with incident_key="calculator-error-rate-prod", severity=SEV-1
AND    current time = 2026-03-30T12:00:00Z
WHEN   CorrelationRecord.reserve(alarm_event)
THEN   record.incident_key == "calculator-error-rate-prod"
AND    record.jira_ticket_id is None
AND    record.status == CorrelationStatus.RESERVED
AND    record.severity == "SEV-1"
AND    record.ttl == epoch(2026-03-31T12:00:00Z)  # +24h
```

#### S1.5: CorrelationRecord to_grace Transition

```
GIVEN  a DETECTED record with jira_ticket_id="INC-142"
AND    resolved_at = 2026-03-30T14:00:00Z
AND    grace_period_seconds = 900
WHEN   record.to_grace(resolved_at, grace_period_seconds)
THEN   result.status == CorrelationStatus.GRACE
AND    result.ttl == epoch(2026-03-30T14:15:00Z)  # +15min
AND    result.jira_ticket_id == "INC-142"  # preserved
```

#### S1.6: CorrelationRecord DynamoDB Roundtrip

```
GIVEN  a CorrelationRecord with all fields populated
WHEN   item = record.to_dynamodb_item()
AND    restored = CorrelationRecord.from_dynamodb_item(item)
THEN   restored == record  # roundtrip preserves all fields
```

#### S1.7: IncidentConfig Load

```
GIVEN  a valid incident_config.json file
WHEN   IncidentConfig.load(config_path)
THEN   config.storm_threshold == 5
AND    config.grace_period_seconds == 900
AND    config.recovery_catalog["replay"]["type"] == "step_function"
AND    config is frozen (immutable)
```

---

### Scenario Group 2: Detection Service -- Happy Path

#### S2.1: New Incident -- Full Flow (Stateless)

```
GIVEN  alarm_event: calculator-error-rate-prod, SEV-1, stateless
AND    no existing DynamoDB record
AND    alarm state is still ALARM after cool-off
AND    storm count = 2 (below threshold of 5)
WHEN   detection_service.process_alarm(alarm_event)
THEN   correlation_repo.reserve called with RESERVED record
AND    integration_repo.create_jira_ticket called with correct summary, priority, labels
AND    correlation_repo.update called with jira_ticket_id="INC-142", status=DETECTED
AND    integration_repo.publish_event called with:
       event_type="IncidentCreated"
       detail.incident_key="calculator-error-rate-prod"
       detail.storm_detected=False
       detail.recovery_model="stateless"
AND    returns "INC-142"
```

#### S2.2: New Incident -- Replay Recovery Model

```
GIVEN  alarm_event: payments-queue-backlog-prod, SEV-2, replay
AND    no existing DynamoDB record
AND    alarm still active after cool-off
WHEN   detection_service.process_alarm(alarm_event)
THEN   publish_event called with detail.recovery_model="replay"
```

#### S2.3: Cool-Off Filters Transient Spike

```
GIVEN  alarm_event: calculator-error-rate-prod
AND    no existing DynamoDB record
AND    after cool-off (30s), alarm state = "OK"
WHEN   detection_service.process_alarm(alarm_event)
THEN   correlation_repo.reserve NOT called
AND    integration_repo.create_jira_ticket NOT called
AND    returns None
```

---

### Scenario Group 3: Detection Service -- Race Conditions

#### S3.1: Concurrent Alarm -- RESERVED Conflict

```
GIVEN  alarm_event: calculator-error-rate-prod
AND    alarm is still active after cool-off
AND    correlation_repo.reserve raises DuplicateIncidentError
AND    correlation_repo.get returns record with status=RESERVED, jira_ticket_id=None
WHEN   detection_service.process_alarm(alarm_event)
THEN   integration_repo.create_jira_ticket NOT called
AND    integration_repo.add_jira_comment NOT called  # no ticket to comment on
AND    returns None
```

#### S3.2: Concurrent Alarm -- DETECTED Conflict

```
GIVEN  alarm_event: calculator-error-rate-prod
AND    alarm is still active after cool-off
AND    correlation_repo.reserve raises DuplicateIncidentError
AND    correlation_repo.get returns record with status=DETECTED, jira_ticket_id="INC-142"
WHEN   detection_service.process_alarm(alarm_event)
THEN   integration_repo.add_jira_comment called with ticket_key="INC-142"
AND    comment contains "Duplicate alarm"
AND    returns None
```

#### S3.3: Concurrent Alarm -- GRACE Conflict (Recurrence)

```
GIVEN  alarm_event: calculator-error-rate-prod
AND    alarm is still active after cool-off
AND    correlation_repo.reserve raises DuplicateIncidentError
AND    correlation_repo.get returns record with status=GRACE, jira_ticket_id="INC-142"
WHEN   detection_service.process_alarm(alarm_event)
THEN   integration_repo.add_jira_comment called with "recurrence" message
AND    correlation_repo.update called with status=DETECTED, fresh 24h TTL
AND    integration_repo.publish_event called with:
       event_type="EscalationRequired"
       detail.reason="grace-period-recurrence"
```

#### S3.5: Stale RESERVED Record Recovery

```
GIVEN  alarm_event: calculator-error-rate-prod
AND    alarm is still active after cool-off
AND    correlation_repo.reserve raises DuplicateIncidentError
AND    correlation_repo.get returns record with status=RESERVED, jira_ticket_id=None
AND    record.created_at is 200 seconds ago (> reservation_timeout_seconds of 180s)
WHEN   detection_service.process_alarm(alarm_event)
THEN   correlation_repo.delete called (stale RESERVED cleanup)
AND    correlation_repo.reserve called again (retry)
AND    integration_repo.create_jira_ticket called (new ticket created)
AND    returns jira_ticket_id
```

#### S3.4: Jira Creation Failure -- Cleanup

```
GIVEN  alarm_event: calculator-error-rate-prod
AND    no existing DynamoDB record
AND    alarm still active
AND    correlation_repo.reserve returns True
AND    integration_repo.create_jira_ticket returns None (Jira failure)
WHEN   detection_service.process_alarm(alarm_event)
THEN   correlation_repo.delete called with "calculator-error-rate-prod"
AND    returns None
```

---

### Scenario Group 4: Storm Detection

#### S4.1: Normal -- Below Threshold

```
GIVEN  alarm_event: calculator-error-rate-prod
AND    no existing record
AND    alarm still active
AND    correlation_repo.count_recent returns 3 (below threshold of 5)
WHEN   detection_service.process_alarm(alarm_event)
THEN   publish_event detail.storm_detected == False
```

#### S4.2: Storm Detected -- Above Threshold

```
GIVEN  alarm_event: calculator-error-rate-prod
AND    no existing record
AND    alarm still active
AND    correlation_repo.count_recent returns 8 (above threshold of 5)
WHEN   detection_service.process_alarm(alarm_event)
THEN   publish_event detail.storm_detected == True
AND    publish_event detail.active_incident_count == 8
AND    Jira ticket still created (incidents still tracked during storms)
```

#### S4.3: Storm -- Triage Skips Remediation

```
GIVEN  triage called with storm_detected=True
AND    correlation_repo.get returns DETECTED record
WHEN   triage_service.triage(incident_key, jira_ticket_id, storm_detected=True)
THEN   _analyze_logs called (analysis still runs)
AND    _classify_root_cause called (classification still runs)
AND    _attempt_remediation NOT called
AND    publish_event called with:
       event_type="EscalationRequired"
       detail.reason="incident-storm"
```

#### S4.4: Storm -- Multiple Services

```
GIVEN  6 alarm events from different services (payments, orders, inventory, notifications, auth, search)
AND    all arrive within 2 minutes
WHEN   each calls detection_service.process_alarm()
THEN   first 5 have storm_detected=False
AND    6th has storm_detected=True, active_incident_count=6
AND    all 6 create Jira tickets (incidents still tracked)
```

---

### Scenario Group 5: Triage Service -- Remediation & Verification

#### S5.1: Successful Remediation -- Bad Deployment (Stateless)

```
GIVEN  incident_key="calculator-error-rate-prod", jira_ticket_id="INC-142"
AND    recovery_model="stateless"
AND    log analysis classifies root_cause="bad-deployment", confidence="high"
AND    remediation_catalog has bad-deployment -> lambda-version-rollback
AND    after verification wait, all 3 checks pass (alarm OK, health OK, error rate OK)
WHEN   triage_service.triage(incident_key, jira_ticket_id, recovery_model="stateless")
THEN   integration_repo.rollback_lambda_version called
AND    _trigger_recovery NOT called (stateless = no recovery)
AND    Jira updated with resolution comment
AND    correlation_repo.update called with GRACE status + 15min TTL
AND    publish_event called with "IncidentAutoResolved"
AND    returns "auto-resolved"
```

#### S5.2: Verification Fails -- Escalation

```
GIVEN  incident with remediation attempted
AND    after verification: alarm_ok=True, health_ok=True, error_rate_ok=False
WHEN   triage_service._verify_remediation(alarm_name, service)
THEN   returns (True, True, False)
AND    triage publishes EscalationRequired with reason="verification-failed"
AND    Jira comment documents which checks failed
```

#### S5.3: No Remediation Available -- Escalation

```
GIVEN  root_cause="specific-bug" (no entry in remediation_catalog)
WHEN   triage_service._attempt_remediation("calculator", "specific-bug")
THEN   returns None
AND    triage publishes EscalationRequired with reason="no-remediation-available"
AND    Jira comment: "No automated remediation available for specific-bug"
```

#### S5.5: Triage Timeout -- Forced Escalation

```
GIVEN  incident_key="calculator-error-rate-prod", jira_ticket_id="INC-142"
AND    triage_timeout_seconds = 120
AND    log analysis + classification takes 130 seconds (exceeds timeout)
WHEN   triage_service.triage(incident_key, jira_ticket_id)
THEN   analysis results preserved in Jira (comments added before timeout)
AND    _attempt_remediation NOT called
AND    publish EscalationRequired with reason="triage-timeout"
AND    Jira comment: "Triage timeout exceeded (120s). Analysis preserved. Escalating."
AND    returns "escalated"
```

#### S5.4: Remediation Action Fails

```
GIVEN  root_cause="bad-deployment"
AND    integration_repo.rollback_lambda_version raises Exception
WHEN   triage processes remediation
THEN   error logged
AND    Jira comment: "Remediation failed: {error}"
AND    publish EscalationRequired with reason="verification-failed"
```

---

### Scenario Group 6: Recovery Models

#### S6.1: Stateless Recovery -- No Action Needed

```
GIVEN  triage succeeds, 3-point verification passes
AND    recovery_model="stateless"
WHEN   triage_service._trigger_recovery("stateless", incident_key, jira_ticket_id, service)
THEN   returns {recovery_model: "stateless", recovery_action: "none", status: "not-required"}
AND    integration_repo.trigger_step_function NOT called
AND    integration_repo.trigger_recovery_lambda NOT called
AND    Jira comment: "Recovery model: stateless. No post-remediation recovery needed."
```

#### S6.2: Replay Recovery -- DLQ Workflow Triggered

```
GIVEN  triage succeeds for queue-backlog incident
AND    recovery_model="replay"
AND    recovery_catalog has replay -> {type: "step_function", workflow_arn_env: "REPLAY_DLQ_WORKFLOW_ARN"}
AND    env REPLAY_DLQ_WORKFLOW_ARN = "arn:aws:states:us-west-2:320644769527:stateMachine:ReplayDLQ"
WHEN   triage_service._trigger_recovery("replay", "payments-queue-backlog-prod", "INC-200", "payments")
THEN   integration_repo.trigger_step_function called with:
       workflow_arn="arn:aws:states:...ReplayDLQ"
       input_payload contains incident_key, jira_ticket_id, service
AND    returns {recovery_model: "replay", recovery_action: "step_function", execution_id: "arn:...exec-123", status: "triggered"}
AND    Jira comment includes execution ARN
```

#### S6.3: Reprocess Recovery -- Batch Workflow Triggered

```
GIVEN  triage succeeds for batch-failure incident
AND    recovery_model="reprocess"
AND    recovery_catalog has reprocess -> {type: "step_function", workflow_arn_env: "REPROCESS_BATCH_WORKFLOW_ARN"}
WHEN   _trigger_recovery("reprocess", "settlement-batch-failure-prod", "INC-300", "settlement")
THEN   trigger_step_function called with REPROCESS_BATCH_WORKFLOW_ARN
AND    Jira comment: "Recovery: Triggered batch rerun workflow. Execution: {arn}"
```

#### S6.4: Data Correction Recovery -- Reconciliation Triggered

```
GIVEN  triage succeeds for data-integrity incident
AND    recovery_model="data-correction"
WHEN   _trigger_recovery("data-correction", "payments-data-integrity-prod", "INC-400", "payments")
THEN   trigger_step_function called with RECONCILIATION_WORKFLOW_ARN
AND    Jira comment includes "data reconciliation" and execution ARN
```

#### S6.5: Backlog Drain Recovery -- Lambda Triggered

```
GIVEN  recovery_model="backlog-drain"
AND    recovery_catalog has backlog-drain -> {type: "lambda", function_name_env: "BACKLOG_DRAIN_FUNCTION_NAME"}
AND    env BACKLOG_DRAIN_FUNCTION_NAME = "backlog-drain-payments-prod"
WHEN   _trigger_recovery("backlog-drain", incident_key, jira_ticket_id, "payments")
THEN   integration_repo.trigger_recovery_lambda called with function_name="backlog-drain-payments-prod"
AND    NOT trigger_step_function
```

#### S6.6: Recovery Workflow Failure -- Does Not Block Resolution

```
GIVEN  recovery_model="replay"
AND    integration_repo.trigger_step_function returns None (workflow trigger failed)
WHEN   triage processes recovery
THEN   error logged
AND    Jira comment: "Recovery workflow trigger failed: {error}. Manual recovery may be required."
AND    incident STILL resolved (Jira resolved, DynamoDB -> GRACE)
AND    IncidentAutoResolved published with recovery_status="failed"
AND    returns "auto-resolved" (not "escalated")
```

#### S6.7: Recovery Catalog Entry Missing

```
GIVEN  recovery_model="replay"
AND    recovery_catalog does NOT have "replay" entry
WHEN   _trigger_recovery("replay", ...)
THEN   Jira comment: "Recovery model 'replay' not configured in recovery catalog. Manual recovery required."
AND    incident STILL resolved
```

#### S6.9: Recovery Workflow Receives Idempotency Keys

```
GIVEN  triage succeeds for queue-backlog incident
AND    recovery_model="replay"
WHEN   triage_service._trigger_recovery("replay", "payments-queue-backlog-prod", "INC-200", "payments")
THEN   integration_repo.trigger_step_function called with input_payload containing:
       incident_key="payments-queue-backlog-prod"
       jira_ticket_id="INC-200"
       execution_id matches UUID format
AND    execution_id used as Step Functions execution name
```

#### S6.8: Recovery Workflow ARN Not Configured

```
GIVEN  recovery_model="replay"
AND    recovery_catalog has replay -> {type: "step_function", workflow_arn_env: "REPLAY_DLQ_WORKFLOW_ARN"}
AND    env REPLAY_DLQ_WORKFLOW_ARN = "" (empty)
WHEN   _trigger_recovery("replay", ...)
THEN   Jira comment: "Recovery workflow not configured (REPLAY_DLQ_WORKFLOW_ARN not set). Manual recovery required."
AND    incident STILL resolved
```

---

### Scenario Group 7: Grace Period & Recurrence

#### S7.1: Auto-Resolution Creates GRACE Record

```
GIVEN  triage auto-resolves incident at 2026-03-30T14:00:00Z
AND    grace_period_seconds=900
WHEN   triage updates DynamoDB
THEN   correlation_repo.update called with:
       status=CorrelationStatus.GRACE
       ttl=epoch(2026-03-30T14:15:00Z)
```

#### S7.2: Alarm Recurs Within Grace Period

```
GIVEN  GRACE record exists for "calculator-error-rate-prod" with jira_ticket_id="INC-142"
AND    same alarm fires again at 2026-03-30T14:10:00Z (within 15-min window)
WHEN   detection_service.process_alarm(alarm_event)
THEN   cool-off is SKIPPED
AND    Jira comment: "Incident recurred after auto-remediation. Escalating."
AND    DynamoDB updated: status=DETECTED, fresh 24h TTL
AND    publish EscalationRequired with reason="grace-period-recurrence"
```

#### S7.3: Alarm Fires After Grace Expires (New Incident)

```
GIVEN  GRACE record expired (TTL passed, DynamoDB deleted it)
AND    same alarm fires again
WHEN   detection_service.process_alarm(alarm_event)
THEN   treated as new incident (full flow: cool-off, reserve, create Jira, etc.)
AND    new Jira ticket created (not reopen of old one)
```

---

### Scenario Group 8: Recovery Flow (SNS OK)

#### S8.1: Alarm Recovers -- Active Incident

```
GIVEN  recovery_event: calculator-error-rate-prod, OK state
AND    DynamoDB has ESCALATED record with jira_ticket_id="INC-142"
WHEN   detection_service.process_recovery(recovery_event)
THEN   observability_repo.collect_recent called (recovery logs)
AND    observability_repo.get_alarm_state called (confirm OK)
AND    integration_repo.add_jira_comment called with resolution summary + diagnostics
AND    integration_repo.attach_jira_file called with recovery logs
AND    integration_repo.transition_jira_ticket called to resolve
AND    correlation_repo.delete called with "calculator-error-rate-prod"
AND    returns True
```

#### S8.2: Alarm Recovers -- No Matching Incident

```
GIVEN  recovery_event: calculator-error-rate-prod
AND    correlation_repo.get returns None
WHEN   detection_service.process_recovery(recovery_event)
THEN   logged as "No matching incident for recovery"
AND    returns False
```

---

### Scenario Group 9: Escalation Service

#### S9.1: SEV-1 Escalation -- Full Enrichment

```
GIVEN  escalation: calculator-error-rate-prod, INC-142, reason="verification-failed"
AND    severity=SEV-1
WHEN   escalation_service.escalate(incident_key, jira_ticket_id, reason)
THEN   correlation_repo.update called with status=ESCALATED
AND    Jira ticket updated with enriched description (root cause, blast radius, history)
AND    Error logs attached as file
AND    Links include dashboard URL, X-Ray URL, Logs Insights URL
AND    Commands include download-logs, trace-lookup, health-check
AND    integration_repo.notify_engineer called (SEV-1)
AND    returns "escalated"
```

#### S9.2: SEV-3 Escalation -- No Notification

```
GIVEN  escalation with severity=SEV-3
WHEN   escalation_service.escalate(...)
THEN   Jira ticket enriched (same as SEV-1)
AND    integration_repo.notify_engineer NOT called
```

#### S9.3: Escalation Reasons -- Correct Messaging

```
FOR EACH reason IN ["verification-failed", "no-remediation-available", "incident-storm", "grace-period-recurrence", "triage-timeout"]:
  GIVEN  escalation with reason={reason}
  WHEN   escalation_service._build_enriched_description(...)
  THEN   description includes reason-specific context
```

---

### Scenario Group 10: Handler Layer

#### S10.1: Detection Handler -- Routes ALARM to process_alarm

```
GIVEN  SNS event with NewStateValue="ALARM"
WHEN   detection_handler.lambda_handler(sns_event, context)
THEN   detection_service.process_alarm called
AND    returns {processed: 1, results: [...]}
```

#### S10.2: Detection Handler -- Routes OK to process_recovery

```
GIVEN  SNS event with NewStateValue="OK"
WHEN   detection_handler.lambda_handler(sns_event, context)
THEN   detection_service.process_recovery called
```

#### S10.3: Detection Handler -- Bad Record Does Not Block Others

```
GIVEN  SNS event with 3 records: [valid_alarm, malformed, valid_recovery]
WHEN   detection_handler.lambda_handler(event, context)
THEN   record 1: process_alarm called
AND    record 2: error logged, result includes error
AND    record 3: process_recovery called
AND    returns {processed: 3}
```

#### S10.4: Triage Handler -- Passes recovery_model

```
GIVEN  EventBridge IncidentCreated event with recovery_model="replay"
WHEN   triage_handler.lambda_handler(event, context)
THEN   triage_service.triage called with recovery_model="replay"
```

#### S10.5: Escalation Handler -- Passes reason

```
GIVEN  EventBridge EscalationRequired event with reason="verification-failed"
WHEN   escalation_handler.lambda_handler(event, context)
THEN   escalation_service.escalate called with reason="verification-failed"
```

---

### Scenario Group 11: Repository Layer (moto)

#### S11.1: CorrelationRepository -- Reserve with Conditional Write

```
GIVEN  empty DynamoDB table
AND    record with incident_key="calculator-error-rate-prod"
WHEN   repo.reserve(record)
THEN   returns True
AND    get("calculator-error-rate-prod") returns the record
```

#### S11.2: CorrelationRepository -- Reserve Conflict

```
GIVEN  existing record for "calculator-error-rate-prod"
AND    new record with same key
WHEN   repo.reserve(new_record)
THEN   raises DuplicateIncidentError
AND    existing record unchanged
```

#### S11.3: CorrelationRepository -- Count Recent (Storm Detection)

```
GIVEN  6 records with created_at within last 2 minutes
AND    2 records with created_at > 2 minutes ago
WHEN   repo.count_recent(since=now - 120s)
THEN   returns 6
```

#### S11.4: CorrelationRepository -- TTL Attribute Set

```
GIVEN  record created at 2026-03-30T12:00:00Z
WHEN   repo.reserve(record)
THEN   DynamoDB item has ttl = epoch(2026-03-31T12:00:00Z)
```

---

### Scenario Group 12: End-to-End Pipeline (Integration)

#### S12.1: Full Pipeline -- Stateless Auto-Resolution

```
GIVEN  CloudWatch alarm fires for calculator-error-rate-prod
WHEN   Detection Lambda processes SNS event
AND    Triage Lambda processes IncidentCreated event
THEN   DynamoDB transitions: RESERVED -> DETECTED -> TRIAGING -> GRACE
AND    Jira: created -> analysis comments -> resolution comment
AND    EventBridge: IncidentCreated -> IncidentAutoResolved
AND    No engineer notification
```

#### S12.2: Full Pipeline -- Replay Recovery Auto-Resolution

```
GIVEN  CloudWatch alarm fires for payments-queue-backlog-prod
WHEN   Detection processes -> creates incident with recovery_model="replay"
AND    Triage processes -> remediates (restart consumer) -> verifies -> triggers DLQ replay workflow
THEN   DynamoDB transitions: RESERVED -> DETECTED -> TRIAGING -> GRACE
AND    Jira: created -> analysis -> remediation -> recovery triggered (execution ARN) -> resolved
AND    Step Function started with incident context
AND    EventBridge: IncidentCreated(recovery_model=replay) -> IncidentAutoResolved(recovery_status=triggered)
```

#### S12.3: Full Pipeline -- Escalation Path

```
GIVEN  alarm fires -> Detection creates incident
AND    Triage: analysis ok, remediation attempted, verification FAILS
WHEN   Escalation Lambda processes EscalationRequired
THEN   DynamoDB transitions: RESERVED -> DETECTED -> TRIAGING -> ESCALATED
AND    Jira: created -> analysis -> remediation failed -> enriched with full diagnostics
AND    SNS notification sent (if SEV-1/SEV-2)
```

#### S12.4: Full Pipeline -- Storm Scenario

```
GIVEN  8 alarms fire within 2 minutes (dependency failure)
WHEN   Detection processes all 8
AND    Triage processes all 8 (each with storm_detected=True)
AND    Escalation processes all 8 EscalationRequired events
THEN   8 Jira tickets created (each with full analysis but NO remediation)
AND    8 engineer notifications (if SEV-1/SEV-2)
AND    0 remediation attempts
```

#### S12.5: Full Pipeline -- Grace Period Recurrence

```
GIVEN  alarm fires -> auto-resolved -> GRACE record exists
AND    same alarm fires again 10 minutes later
WHEN   Detection processes the recurrence
THEN   DynamoDB: GRACE -> DETECTED (fresh TTL)
AND    Jira: reopened with recurrence comment
AND    EscalationRequired published with reason="grace-period-recurrence"
AND    Escalation enriches and notifies
```

#### S12.6: Full Pipeline -- Data Correction Recovery

```
GIVEN  data-integrity alarm fires for payments service
WHEN   full pipeline executes (Detection -> Triage -> auto-resolve)
THEN   reconciliation Step Function triggered after remediation verification
AND    Jira comment: "Recovery: Triggered data reconciliation workflow. Execution: {arn}"
AND    IncidentAutoResolved event includes recovery_model="data-correction", recovery_status="triggered"
```

---

## Test Coverage Summary

| Category | Scenarios | Tests (Est.) |
|----------|-----------|-------------|
| Model Layer | S1.1 -- S1.7 | 12 |
| Detection Service | S2.1 -- S2.3 | 6 |
| Race Conditions | S3.1 -- S3.5 | 10 |
| Storm Detection | S4.1 -- S4.4 | 8 |
| Triage Remediation | S5.1 -- S5.5 | 12 |
| Recovery Models | S6.1 -- S6.9 | 18 |
| Grace Period | S7.1 -- S7.3 | 6 |
| Recovery Flow | S8.1 -- S8.2 | 4 |
| Escalation Service | S9.1 -- S9.3 | 8 |
| Handler Layer | S10.1 -- S10.5 | 8 |
| Repository Layer | S11.1 -- S11.4 | 8 |
| End-to-End Pipeline | S12.1 -- S12.6 | 12 |
| **Total** | **55 scenarios** | **~114 tests** |

## Coverage Gaps (Known)

| Gap | Reason | Mitigation |
|-----|--------|------------|
| Performance testing | No load test for Lambda cold start / warm invocation | Manual benchmark after deployment |
| Jira API contract | Cannot mock Jira REST API responses perfectly | Integration test against Jira sandbox |
| Step Functions execution | Recovery workflows are external | Verify trigger call only; workflow testing is separate |
| DLQ replay | Replay mechanism not yet designed | Tracked as future enhancement |
| Multi-region | Out of scope | N/A |

## Out of Scope

- CDK infrastructure assertions (separate infra test file)
- Performance / load testing
- Recovery workflow internal logic (Step Functions own their tests)
- Jira REST API contract testing (mock boundary)
