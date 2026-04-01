"""Tests for TriageService — workflow orchestration (delegation-based).

TriageService is a thin orchestrator that delegates to:
- LogAnalysisService (log collection + analysis)
- ResolutionService (remediation + verification + recovery)
- IncidentReporter (all Jira interactions)
- AIAnalysisService (AI/rule-based root cause classification)

Tests verify correct delegation, workflow decisions, and event publishing."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch
from freezegun import freeze_time

from src.models.enums import CorrelationStatus
from src.models.correlation_record import CorrelationRecord
from src.services.triage_service import TriageService


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

@pytest.fixture
def triage_service(
    mock_correlation_repo,
    mock_event_bus_repo,
    mock_log_analysis_service,
    mock_resolution_service,
    mock_incident_reporter,
    incident_config,
):
    """TriageService with mocked dependencies."""
    return TriageService(
        correlation_repo=mock_correlation_repo,
        event_bus_repo=mock_event_bus_repo,
        config=incident_config,
        log_analysis_service=mock_log_analysis_service,
        ai_service=None,
        resolution_service=mock_resolution_service,
        incident_reporter=mock_incident_reporter,
    )


@pytest.fixture
def detected_record_for_triage(fixed_now):
    """DETECTED record ready for triage."""
    return CorrelationRecord(
        incident_key="calculator-error-rate-prod",
        jira_ticket_id="INC-142",
        severity="SEV-1",
        status=CorrelationStatus.DETECTED,
        created_at=fixed_now,
        ttl=int((fixed_now + timedelta(hours=24)).timestamp()),
    )


# Standard triage kwargs used across all tests
_TRIAGE_KWARGS = {
    "incident_key": "calculator-error-rate-prod",
    "jira_ticket_id": "INC-142",
    "service": "calculator",
    "stage": "prod",
    "severity": "SEV-1",
    "service_type": "lambda",
    "recovery_model": "stateless",
}


@pytest.fixture
def setup_happy_path(
    mock_correlation_repo,
    mock_log_analysis_service,
    mock_resolution_service,
    detected_record_for_triage,
):
    """Configure mocks for the happy path: bad-deployment -> auto-resolve."""
    mock_correlation_repo.get.return_value = detected_record_for_triage

    mock_log_analysis_service.analyze_errors.return_value = {
        "error_patterns": {"ImportError: No module named 'missing_module'": 6},
        "error_count": 6,
        "unique_errors": 1,
        "sample_payloads": [
            "ImportError: No module named 'missing_module'",
            "ImportError: No module named 'missing_module'",
            "ImportError: No module named 'missing_module'",
            "ImportError: No module named 'missing_module'",
            "ImportError: No module named 'missing_module'",
            "ImportError: No module named 'missing_module'",
        ],
    }

    mock_resolution_service.remediate_and_verify.return_value = (
        "success",
        {"alarm_ok": True, "health_ok": True, "error_rate_ok": True},
    )
    mock_resolution_service.trigger_recovery.return_value = ("not-required", "")


# ------------------------------------------------------------------ #
# Successful Remediation — Happy Path
# ------------------------------------------------------------------ #

class TestSuccessfulRemediation:
    """Full triage -> auto-resolution flow via delegation."""

    @freeze_time("2026-03-30T12:00:00Z")
    def test_returns_auto_resolved(self, triage_service, setup_happy_path):
        result = triage_service.triage(**_TRIAGE_KWARGS)
        assert result == "auto-resolved"

    @freeze_time("2026-03-30T12:00:00Z")
    def test_updates_dynamo_to_triaging(
        self, triage_service, setup_happy_path, mock_correlation_repo
    ):
        triage_service.triage(**_TRIAGE_KWARGS)

        first_update = mock_correlation_repo.update.call_args_list[0][0][0]
        assert first_update.status == CorrelationStatus.TRIAGING
        assert first_update.incident_key == "calculator-error-rate-prod"

    @freeze_time("2026-03-30T12:00:00Z")
    def test_updates_dynamo_to_grace(
        self, triage_service, setup_happy_path, mock_correlation_repo
    ):
        triage_service.triage(**_TRIAGE_KWARGS)

        last_update = mock_correlation_repo.update.call_args_list[-1][0][0]
        assert last_update.status == CorrelationStatus.GRACE
        assert last_update.incident_key == "calculator-error-rate-prod"
        assert last_update.jira_ticket_id == "INC-142"

    @freeze_time("2026-03-30T12:00:00Z")
    def test_grace_ttl_is_15_minutes(
        self, triage_service, setup_happy_path, mock_correlation_repo
    ):
        triage_service.triage(**_TRIAGE_KWARGS)

        grace_record = mock_correlation_repo.update.call_args_list[-1][0][0]
        now = datetime(2026, 3, 30, 12, 0, 0, tzinfo=timezone.utc)
        expected_ttl = int((now + timedelta(seconds=900)).timestamp())
        assert grace_record.ttl == expected_ttl

    @freeze_time("2026-03-30T12:00:00Z")
    def test_delegates_triage_started_to_reporter(
        self, triage_service, setup_happy_path, mock_incident_reporter
    ):
        triage_service.triage(**_TRIAGE_KWARGS)
        mock_incident_reporter.report_triage_started.assert_called_once_with(
            "INC-142", "calculator-error-rate-prod"
        )

    @freeze_time("2026-03-30T12:00:00Z")
    def test_delegates_analysis_to_log_service(
        self, triage_service, setup_happy_path, mock_log_analysis_service
    ):
        triage_service.triage(**_TRIAGE_KWARGS)
        mock_log_analysis_service.analyze_errors.assert_called_once()
        call_args = mock_log_analysis_service.analyze_errors.call_args[0]
        assert call_args[0] == "/aws/lambda/calculator-prod"

    @freeze_time("2026-03-30T12:00:00Z")
    def test_delegates_analysis_results_to_reporter(
        self, triage_service, setup_happy_path, mock_incident_reporter
    ):
        triage_service.triage(**_TRIAGE_KWARGS)
        mock_incident_reporter.report_analysis_results.assert_called_once()
        call_args = mock_incident_reporter.report_analysis_results.call_args
        assert call_args[0][1] == "bad-deployment"  # root_cause
        assert call_args[0][2] == "high"  # confidence

    @freeze_time("2026-03-30T12:00:00Z")
    def test_delegates_auto_resolved_to_reporter(
        self, triage_service, setup_happy_path, mock_incident_reporter
    ):
        triage_service.triage(**_TRIAGE_KWARGS)
        mock_incident_reporter.report_auto_resolved.assert_called_once_with("INC-142")

    @freeze_time("2026-03-30T12:00:00Z")
    def test_delegates_resolve_ticket_to_reporter(
        self, triage_service, setup_happy_path, mock_incident_reporter
    ):
        triage_service.triage(**_TRIAGE_KWARGS)
        mock_incident_reporter.resolve_ticket.assert_called_once_with("INC-142")

    @freeze_time("2026-03-30T12:00:00Z")
    def test_delegates_remediation_to_resolution_service(
        self, triage_service, setup_happy_path, mock_resolution_service
    ):
        triage_service.triage(**_TRIAGE_KWARGS)
        mock_resolution_service.remediate_and_verify.assert_called_once()
        call_kwargs = mock_resolution_service.remediate_and_verify.call_args[1]
        assert call_kwargs["service_type"] == "lambda"
        assert call_kwargs["root_cause"] == "bad-deployment"
        assert call_kwargs["resource_context"]["function_name"] == "calculator-api-prod"

    @freeze_time("2026-03-30T12:00:00Z")
    def test_publishes_incident_auto_resolved(
        self, triage_service, setup_happy_path, mock_event_bus_repo
    ):
        triage_service.triage(**_TRIAGE_KWARGS)

        mock_event_bus_repo.publish_event.assert_called_once()
        event_type = mock_event_bus_repo.publish_event.call_args[0][0]
        detail = mock_event_bus_repo.publish_event.call_args[0][1]

        assert event_type == "IncidentAutoResolved"
        assert detail["incident_key"] == "calculator-error-rate-prod"
        assert detail["jira_ticket_id"] == "INC-142"
        assert detail["service"] == "calculator"
        assert detail["stage"] == "prod"
        assert detail["severity"] == "SEV-1"
        assert detail["recovery_model"] == "stateless"
        assert detail["recovery_status"] == "not-required"
        assert detail["root_cause"] == "bad-deployment"

    @freeze_time("2026-03-30T12:00:00Z")
    def test_delegates_recovery_to_resolution_service(
        self, triage_service, setup_happy_path, mock_resolution_service
    ):
        triage_service.triage(**_TRIAGE_KWARGS)
        mock_resolution_service.trigger_recovery.assert_called_once_with(
            "stateless", "calculator-error-rate-prod", "INC-142", "SEV-1"
        )

    @freeze_time("2026-03-30T12:00:00Z")
    def test_reports_recovery_status(
        self, triage_service, setup_happy_path, mock_incident_reporter
    ):
        triage_service.triage(**_TRIAGE_KWARGS)
        mock_incident_reporter.report_recovery_status.assert_called_once_with(
            "INC-142", "not-required", ""
        )

    @freeze_time("2026-03-30T12:00:00Z")
    def test_uses_stage_from_parameter(
        self, triage_service, setup_happy_path, mock_resolution_service
    ):
        """Verify function_name uses stage from event, not hardcoded 'prod'."""
        triage_service.triage(
            incident_key="calculator-error-rate-dev",
            jira_ticket_id="INC-142",
            service="calculator",
            stage="dev",
            severity="SEV-1",
        )

        call_kwargs = mock_resolution_service.remediate_and_verify.call_args[1]
        assert call_kwargs["resource_context"]["function_name"] == "calculator-api-dev"


# ------------------------------------------------------------------ #
# Recovery model propagation
# ------------------------------------------------------------------ #

class TestRecoveryModelPropagation:
    """Verify recovery_model is passed through to event and resolution service."""

    @freeze_time("2026-03-30T12:00:00Z")
    def test_replay_recovery_model_in_event(
        self, triage_service, setup_happy_path, mock_event_bus_repo
    ):
        triage_service.triage(**{**_TRIAGE_KWARGS, "recovery_model": "replay"})

        detail = mock_event_bus_repo.publish_event.call_args[0][1]
        assert detail["recovery_model"] == "replay"

    @freeze_time("2026-03-30T12:00:00Z")
    def test_recovery_model_passed_to_resolution_service(
        self, triage_service, setup_happy_path, mock_resolution_service
    ):
        triage_service.triage(**{**_TRIAGE_KWARGS, "recovery_model": "replay"})
        mock_resolution_service.trigger_recovery.assert_called_once_with(
            "replay", "calculator-error-rate-prod", "INC-142", "SEV-1"
        )


# ------------------------------------------------------------------ #
# Classification Logic Tests (still on TriageService)
# ------------------------------------------------------------------ #

class TestClassifyRootCause:
    """Verify rule-based classification produces correct root causes."""

    def test_import_error_classifies_as_bad_deployment(self, triage_service):
        error_data = {
            "error_patterns": {"ImportError: No module named 'foo'": 10},
            "error_count": 10,
            "unique_errors": 1,
            "sample_payloads": ["ImportError: No module named 'foo'"],
        }
        result = triage_service._classify_root_cause(error_data)
        assert result["root_cause"] == "bad-deployment"
        assert result["confidence"] == "high"

    def test_syntax_error_classifies_as_bad_deployment(self, triage_service):
        error_data = {
            "error_patterns": {"SyntaxError: invalid syntax": 5},
            "error_count": 5,
            "unique_errors": 1,
            "sample_payloads": ["SyntaxError: invalid syntax at line 42"],
        }
        result = triage_service._classify_root_cause(error_data)
        assert result["root_cause"] == "bad-deployment"

    def test_throttling_classifies_as_rate_limit(self, triage_service):
        error_data = {
            "error_patterns": {
                "TooManyRequestsException: Rate exceeded": 10,
                "ThrottlingException: Too many requests": 8,
                "TimeoutError: connection timed out": 2,
            },
            "error_count": 20,
            "unique_errors": 3,
            "sample_payloads": [
                "TooManyRequestsException: Rate exceeded",
                "ThrottlingException: Too many requests",
                "TimeoutError: connection timed out",
            ],
        }
        result = triage_service._classify_root_cause(error_data)
        assert result["root_cause"] == "rate-limit"
        assert result["confidence"] == "high"

    def test_single_dominant_error_classifies_as_specific_bug(self, triage_service):
        error_data = {
            "error_patterns": {"KeyError: 'missing_field'": 15},
            "error_count": 15,
            "unique_errors": 1,
            "sample_payloads": ["KeyError: 'missing_field'"],
        }
        result = triage_service._classify_root_cause(error_data)
        assert result["root_cause"] == "specific-bug"

    def test_no_errors_returns_unknown(self, triage_service):
        error_data = {
            "error_patterns": {},
            "error_count": 0,
            "unique_errors": 0,
            "sample_payloads": [],
        }
        result = triage_service._classify_root_cause(error_data)
        assert result["root_cause"] == "unknown"
        assert result["confidence"] == "low"


# ------------------------------------------------------------------ #
# Blast Radius Assessment Tests (still on TriageService)
# ------------------------------------------------------------------ #

class TestAssessBlastRadius:
    """Verify blast radius estimation."""

    def test_high_error_count(self, triage_service):
        error_data = {"error_count": 200, "error_patterns": {"err1": 200}}
        result = triage_service._assess_blast_radius(error_data)
        assert "400" in result["affected_users"]

    def test_low_error_count(self, triage_service):
        error_data = {"error_count": 3, "error_patterns": {"err1": 3}}
        result = triage_service._assess_blast_radius(error_data)
        assert "< 50" in result["affected_users"]

    def test_zero_errors(self, triage_service):
        error_data = {"error_count": 0, "error_patterns": {}}
        result = triage_service._assess_blast_radius(error_data)
        assert result["error_rate"] == "0%"


# ================================================================== #
# Edge Cases and Escalation Paths
# ================================================================== #


# ------------------------------------------------------------------ #
# Storm Skips Remediation
# ------------------------------------------------------------------ #

class TestStormOverride:
    """When storm_detected=True, analysis runs but remediation is skipped."""

    @freeze_time("2026-03-30T12:00:00Z")
    def test_storm_returns_escalated(self, triage_service, setup_happy_path):
        result = triage_service.triage(**{**_TRIAGE_KWARGS, "storm_detected": True})
        assert result == "escalated"

    @freeze_time("2026-03-30T12:00:00Z")
    def test_storm_publishes_escalation_with_storm_reason(
        self, triage_service, setup_happy_path, mock_event_bus_repo
    ):
        triage_service.triage(**{**_TRIAGE_KWARGS, "storm_detected": True})

        event_type = mock_event_bus_repo.publish_event.call_args[0][0]
        detail = mock_event_bus_repo.publish_event.call_args[0][1]
        assert event_type == "EscalationRequired"
        assert detail["reason"] == "incident-storm"
        assert detail["incident_key"] == "calculator-error-rate-prod"

    @freeze_time("2026-03-30T12:00:00Z")
    def test_storm_still_runs_analysis(
        self, triage_service, setup_happy_path, mock_log_analysis_service
    ):
        triage_service.triage(**{**_TRIAGE_KWARGS, "storm_detected": True})
        mock_log_analysis_service.analyze_errors.assert_called_once()

    @freeze_time("2026-03-30T12:00:00Z")
    def test_storm_reports_to_jira(
        self, triage_service, setup_happy_path, mock_incident_reporter
    ):
        triage_service.triage(**{**_TRIAGE_KWARGS, "storm_detected": True})
        mock_incident_reporter.report_triage_started.assert_called_once()
        mock_incident_reporter.report_analysis_results.assert_called_once()
        mock_incident_reporter.report_storm_detected.assert_called_once()

    @freeze_time("2026-03-30T12:00:00Z")
    def test_storm_skips_remediation(
        self, triage_service, setup_happy_path, mock_resolution_service
    ):
        triage_service.triage(**{**_TRIAGE_KWARGS, "storm_detected": True})
        mock_resolution_service.remediate_and_verify.assert_not_called()

    @freeze_time("2026-03-30T12:00:00Z")
    def test_storm_includes_root_cause_in_escalation(
        self, triage_service, setup_happy_path, mock_event_bus_repo
    ):
        triage_service.triage(**{**_TRIAGE_KWARGS, "storm_detected": True})

        detail = mock_event_bus_repo.publish_event.call_args[0][1]
        assert "root_cause" in detail
        assert detail["root_cause"] == "bad-deployment"


# ------------------------------------------------------------------ #
# Remediation Action Fails
# ------------------------------------------------------------------ #

class TestRemediationFailure:
    """When remediation fails, escalate."""

    @freeze_time("2026-03-30T12:00:00Z")
    def test_remediation_failure_returns_escalated(
        self, triage_service, setup_happy_path, mock_resolution_service
    ):
        mock_resolution_service.remediate_and_verify.return_value = ("remediation-failed", None)
        result = triage_service.triage(**_TRIAGE_KWARGS)
        assert result == "escalated"

    @freeze_time("2026-03-30T12:00:00Z")
    def test_remediation_failure_publishes_escalation(
        self, triage_service, setup_happy_path, mock_resolution_service, mock_event_bus_repo
    ):
        mock_resolution_service.remediate_and_verify.return_value = ("remediation-failed", None)
        triage_service.triage(**_TRIAGE_KWARGS)

        event_type = mock_event_bus_repo.publish_event.call_args[0][0]
        detail = mock_event_bus_repo.publish_event.call_args[0][1]
        assert event_type == "EscalationRequired"
        assert detail["reason"] == "remediation-failed"
        assert detail["root_cause"] == "bad-deployment"

    @freeze_time("2026-03-30T12:00:00Z")
    def test_remediation_failure_reports_to_jira(
        self, triage_service, setup_happy_path, mock_resolution_service, mock_incident_reporter
    ):
        mock_resolution_service.remediate_and_verify.return_value = ("remediation-failed", None)
        triage_service.triage(**_TRIAGE_KWARGS)
        mock_incident_reporter.report_remediation_failed.assert_called_once()


# ------------------------------------------------------------------ #
# Verification Fails
# ------------------------------------------------------------------ #

class TestVerificationFailure:
    """When verification fails after remediation, escalate."""

    @freeze_time("2026-03-30T12:00:00Z")
    def test_verification_failure_returns_escalated(
        self, triage_service, setup_happy_path, mock_resolution_service
    ):
        mock_resolution_service.remediate_and_verify.return_value = (
            "verification-failed",
            {"alarm_ok": False, "health_ok": True, "error_rate_ok": True},
        )
        result = triage_service.triage(**_TRIAGE_KWARGS)
        assert result == "escalated"

    @freeze_time("2026-03-30T12:00:00Z")
    def test_verification_failure_publishes_escalation(
        self, triage_service, setup_happy_path, mock_resolution_service, mock_event_bus_repo
    ):
        mock_resolution_service.remediate_and_verify.return_value = (
            "verification-failed",
            {"alarm_ok": False, "health_ok": True, "error_rate_ok": True},
        )
        triage_service.triage(**_TRIAGE_KWARGS)

        event_type = mock_event_bus_repo.publish_event.call_args[0][0]
        detail = mock_event_bus_repo.publish_event.call_args[0][1]
        assert event_type == "EscalationRequired"
        assert detail["reason"] == "verification-failed"
        assert detail["verification"]["alarm_ok"] is False

    @freeze_time("2026-03-30T12:00:00Z")
    def test_verification_failure_reports_to_jira(
        self, triage_service, setup_happy_path, mock_resolution_service, mock_incident_reporter
    ):
        verification = {"alarm_ok": False, "health_ok": True, "error_rate_ok": True}
        mock_resolution_service.remediate_and_verify.return_value = (
            "verification-failed", verification,
        )
        triage_service.triage(**_TRIAGE_KWARGS)
        mock_incident_reporter.report_verification_failed.assert_called_once_with(
            "INC-142", verification
        )


# ------------------------------------------------------------------ #
# No Remediation Available
# ------------------------------------------------------------------ #

class TestNoRemediationAvailable:
    """When no remediation exists for the root cause, escalate."""

    @freeze_time("2026-03-30T12:00:00Z")
    def test_no_remediation_returns_escalated(
        self, triage_service, setup_happy_path, mock_resolution_service
    ):
        mock_resolution_service.remediate_and_verify.return_value = ("no-remediation", None)
        result = triage_service.triage(**_TRIAGE_KWARGS)
        assert result == "escalated"

    @freeze_time("2026-03-30T12:00:00Z")
    def test_no_remediation_publishes_escalation(
        self, triage_service, setup_happy_path, mock_resolution_service, mock_event_bus_repo
    ):
        mock_resolution_service.remediate_and_verify.return_value = ("no-remediation", None)
        triage_service.triage(**_TRIAGE_KWARGS)

        event_type = mock_event_bus_repo.publish_event.call_args[0][0]
        detail = mock_event_bus_repo.publish_event.call_args[0][1]
        assert event_type == "EscalationRequired"
        assert detail["reason"] == "no-remediation-available"

    @freeze_time("2026-03-30T12:00:00Z")
    def test_no_remediation_reports_to_jira(
        self, triage_service, setup_happy_path, mock_resolution_service, mock_incident_reporter
    ):
        mock_resolution_service.remediate_and_verify.return_value = ("no-remediation", None)
        triage_service.triage(**_TRIAGE_KWARGS)
        mock_incident_reporter.report_remediation_unavailable.assert_called_once()


# ------------------------------------------------------------------ #
# Triage Timeout
# ------------------------------------------------------------------ #

class TestTriageTimeout:
    """When triage exceeds timeout, escalate."""

    @freeze_time("2026-03-30T12:00:00Z")
    def test_timeout_returns_escalated(
        self, triage_service, setup_happy_path, incident_config
    ):
        object.__setattr__(incident_config, 'triage_timeout_seconds', -1)
        result = triage_service.triage(**_TRIAGE_KWARGS)
        object.__setattr__(incident_config, 'triage_timeout_seconds', 120)
        assert result == "escalated"

    @freeze_time("2026-03-30T12:00:00Z")
    def test_timeout_publishes_escalation(
        self, triage_service, setup_happy_path, mock_event_bus_repo, incident_config
    ):
        object.__setattr__(incident_config, 'triage_timeout_seconds', -1)
        triage_service.triage(**_TRIAGE_KWARGS)
        object.__setattr__(incident_config, 'triage_timeout_seconds', 120)

        event_type = mock_event_bus_repo.publish_event.call_args[0][0]
        detail = mock_event_bus_repo.publish_event.call_args[0][1]
        assert event_type == "EscalationRequired"
        assert detail["reason"] == "triage-timeout"

    @freeze_time("2026-03-30T12:00:00Z")
    def test_timeout_preserves_analysis(
        self, triage_service, setup_happy_path, mock_incident_reporter, incident_config
    ):
        """Analysis report should already be posted before timeout check."""
        object.__setattr__(incident_config, 'triage_timeout_seconds', -1)
        triage_service.triage(**_TRIAGE_KWARGS)
        object.__setattr__(incident_config, 'triage_timeout_seconds', 120)

        mock_incident_reporter.report_analysis_results.assert_called_once()
