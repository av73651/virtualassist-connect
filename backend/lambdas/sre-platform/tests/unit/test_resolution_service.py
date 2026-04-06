"""Tests for ResolutionService — auto-remediation, verification, and self-healing.

Covers:
- attempt_auto_remediation (skill-file-driven dispatch)
- verify (3-point verification)
- remediate_and_verify (combined flow)
- trigger_recovery (Step Function / Lambda recovery workflows)"""

import os
import pytest
from unittest.mock import Mock, patch
from freezegun import freeze_time

from src.services.remediation.engine import RemediationEngine
from src.services.resolution_service import ResolutionService


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

@pytest.fixture
def resolution_service(
    mock_remediation_repo, mock_recovery_repo, mock_observability_repo,
    mock_log_analysis_service, incident_config,
):
    return ResolutionService(
        remediation_engine=RemediationEngine(),
        remediation_repo=mock_remediation_repo,
        recovery_repo=mock_recovery_repo,
        observability_repo=mock_observability_repo,
        log_analysis_service=mock_log_analysis_service,
        config=incident_config,
    )


_RESOURCE_CTX = {"function_name": "calculator-api-prod"}


# ------------------------------------------------------------------ #
# Auto-remediation
# ------------------------------------------------------------------ #

class TestAttemptAutoRemediation:
    """Verify remediation engine dispatch via skill files."""

    def test_bad_deployment_calls_rollback(self, resolution_service, mock_remediation_repo):
        mock_remediation_repo.rollback_lambda_version.return_value = {"status": "success"}
        result = resolution_service.attempt_auto_remediation("lambda", "bad-deployment", _RESOURCE_CTX)
        assert result is True
        mock_remediation_repo.rollback_lambda_version.assert_called_once_with(function_name="calculator-api-prod")

    def test_performance_degradation_calls_memory_increase(self, resolution_service, mock_remediation_repo):
        mock_remediation_repo.increase_lambda_memory.return_value = {"status": "success"}
        result = resolution_service.attempt_auto_remediation("lambda", "performance-degradation", _RESOURCE_CTX)
        assert result is True
        mock_remediation_repo.increase_lambda_memory.assert_called_once_with(function_name="calculator-api-prod")

    def test_rate_limit_calls_increase_concurrency(self, resolution_service, mock_remediation_repo):
        mock_remediation_repo.increase_concurrency.return_value = {"status": "success"}
        result = resolution_service.attempt_auto_remediation("lambda", "rate-limit", _RESOURCE_CTX)
        assert result is True
        mock_remediation_repo.increase_concurrency.assert_called_once_with(function_name="calculator-api-prod")

    def test_unknown_root_cause_returns_none(self, resolution_service):
        result = resolution_service.attempt_auto_remediation("lambda", "unknown", _RESOURCE_CTX)
        assert result is None

    def test_remediation_failure_returns_false(self, resolution_service, mock_remediation_repo):
        mock_remediation_repo.rollback_lambda_version.return_value = {"status": "failed"}
        result = resolution_service.attempt_auto_remediation("lambda", "bad-deployment", _RESOURCE_CTX)
        assert result is False

    def test_unknown_service_type_returns_none(self, resolution_service):
        result = resolution_service.attempt_auto_remediation("unknown", "bad-deployment", _RESOURCE_CTX)
        assert result is None


# ------------------------------------------------------------------ #
# Verification
# ------------------------------------------------------------------ #

class TestAiRecommendedActionPassthrough:
    """Verify ai_recommended_action is passed through to the engine."""

    def test_passes_ai_action_to_engine(self, resolution_service, mock_remediation_repo):
        """ai_recommended_action flows from resolution_service to engine."""
        mock_remediation_repo.increase_concurrency.return_value = {"status": "success"}
        result = resolution_service.attempt_auto_remediation(
            "lambda", "bad-deployment", _RESOURCE_CTX,
            ai_recommended_action="increase-concurrency",
        )
        assert result is True
        mock_remediation_repo.increase_concurrency.assert_called_once()
        mock_remediation_repo.rollback_lambda_version.assert_not_called()

    def test_none_ai_action_uses_catalog(self, resolution_service, mock_remediation_repo):
        result = resolution_service.attempt_auto_remediation(
            "lambda", "bad-deployment", _RESOURCE_CTX,
            ai_recommended_action=None,
        )
        assert result is True
        mock_remediation_repo.rollback_lambda_version.assert_called_once()

    @patch("time.sleep")
    def test_remediate_and_verify_passes_ai_action(
        self, mock_sleep, resolution_service, mock_remediation_repo,
        mock_observability_repo, mock_log_analysis_service,
    ):
        mock_remediation_repo.increase_concurrency.return_value = {"status": "success"}
        mock_observability_repo.get_alarm_state.return_value = "OK"
        mock_log_analysis_service.check_health.return_value = (True, True)

        outcome, verification = resolution_service.remediate_and_verify(
            service_type="lambda",
            root_cause="bad-deployment",
            resource_context=_RESOURCE_CTX,
            alarm_name="test",
            log_group="/test",
            wait_seconds=60,
            ai_recommended_action="increase-concurrency",
        )
        assert outcome == "success"
        mock_remediation_repo.increase_concurrency.assert_called_once()


# ------------------------------------------------------------------ #
# Verification
# ------------------------------------------------------------------ #

class TestVerify:
    """Verify 3-point verification after remediation."""

    def test_all_checks_pass(self, resolution_service, mock_observability_repo, mock_log_analysis_service):
        mock_observability_repo.get_alarm_state.return_value = "OK"
        mock_log_analysis_service.check_health.return_value = (True, True)

        result = resolution_service.verify(
            "calculator-high-error-rate-prod", "/aws/lambda/calculator-prod"
        )
        assert result["alarm_ok"] is True
        assert result["health_ok"] is True
        assert result["error_rate_ok"] is True

    def test_alarm_still_in_alarm_state(self, resolution_service, mock_observability_repo, mock_log_analysis_service):
        mock_observability_repo.get_alarm_state.return_value = "ALARM"
        mock_log_analysis_service.check_health.return_value = (True, True)

        result = resolution_service.verify(
            "calculator-high-error-rate-prod", "/aws/lambda/calculator-prod"
        )
        assert result["alarm_ok"] is False
        assert result["health_ok"] is True

    def test_health_check_fails(self, resolution_service, mock_observability_repo, mock_log_analysis_service):
        mock_observability_repo.get_alarm_state.return_value = "OK"
        mock_log_analysis_service.check_health.return_value = (False, True)

        result = resolution_service.verify(
            "calculator-high-error-rate-prod", "/aws/lambda/calculator-prod"
        )
        assert result["alarm_ok"] is True
        assert result["health_ok"] is False


# ------------------------------------------------------------------ #
# remediate_and_verify (combined flow)
# ------------------------------------------------------------------ #

class TestRemediateAndVerify:
    """Tests for the combined remediate -> wait -> verify flow."""

    @patch("time.sleep")
    def test_success_flow(self, mock_sleep, resolution_service, mock_remediation_repo, mock_observability_repo, mock_log_analysis_service):
        mock_remediation_repo.rollback_lambda_version.return_value = {"status": "success"}
        mock_observability_repo.get_alarm_state.return_value = "OK"
        mock_log_analysis_service.check_health.return_value = (True, True)

        outcome, verification = resolution_service.remediate_and_verify(
            service_type="lambda",
            root_cause="bad-deployment",
            resource_context=_RESOURCE_CTX,
            alarm_name="calculator-high-error-rate-prod",
            log_group="/aws/lambda/calculator-prod",
            wait_seconds=60,
        )

        assert outcome == "success"
        assert verification["alarm_ok"] is True
        mock_sleep.assert_called_once_with(60)

    def test_no_remediation_available(self, resolution_service):
        outcome, verification = resolution_service.remediate_and_verify(
            service_type="lambda",
            root_cause="unknown",
            resource_context=_RESOURCE_CTX,
            alarm_name="test",
            log_group="/test",
            wait_seconds=60,
        )

        assert outcome == "no-remediation"
        assert verification is None

    def test_remediation_failed(self, resolution_service, mock_remediation_repo):
        mock_remediation_repo.rollback_lambda_version.return_value = {"status": "failed"}

        outcome, verification = resolution_service.remediate_and_verify(
            service_type="lambda",
            root_cause="bad-deployment",
            resource_context=_RESOURCE_CTX,
            alarm_name="test",
            log_group="/test",
            wait_seconds=60,
        )

        assert outcome == "remediation-failed"
        assert verification is None

    @patch("time.sleep")
    def test_verification_failed(self, mock_sleep, resolution_service, mock_remediation_repo, mock_observability_repo, mock_log_analysis_service):
        mock_remediation_repo.rollback_lambda_version.return_value = {"status": "success"}
        mock_observability_repo.get_alarm_state.return_value = "ALARM"
        mock_log_analysis_service.check_health.return_value = (True, True)

        outcome, verification = resolution_service.remediate_and_verify(
            service_type="lambda",
            root_cause="bad-deployment",
            resource_context=_RESOURCE_CTX,
            alarm_name="calculator-high-error-rate-prod",
            log_group="/aws/lambda/calculator-prod",
            wait_seconds=60,
        )

        assert outcome == "verification-failed"
        assert verification["alarm_ok"] is False


# ------------------------------------------------------------------ #
# Recovery: Step Functions
# ------------------------------------------------------------------ #

class TestRecoveryStepFunction:
    """Recovery via Step Functions (replay, reprocess, data-correction)."""

    @patch.dict(os.environ, {"REPLAY_DLQ_WORKFLOW_ARN": "arn:aws:states:us-west-2:320644769527:stateMachine:ReplayDLQ"})
    def test_replay_triggers_step_function(self, resolution_service, mock_recovery_repo):
        status, detail = resolution_service.trigger_recovery(
            "replay", "calculator-error-rate-prod", "INC-142", "SEV-1"
        )

        assert status == "triggered"
        mock_recovery_repo.trigger_step_function.assert_called_once()
        payload = mock_recovery_repo.trigger_step_function.call_args[0][1]
        assert payload["incident_key"] == "calculator-error-rate-prod"
        assert payload["jira_ticket_id"] == "INC-142"
        assert "execution_id" in payload

    @patch.dict(os.environ, {"REPROCESS_BATCH_WORKFLOW_ARN": "arn:aws:states:us-west-2:320644769527:stateMachine:Reprocess"})
    def test_reprocess_triggers_step_function(self, resolution_service, mock_recovery_repo):
        status, _ = resolution_service.trigger_recovery(
            "reprocess", "calc-error-prod", "INC-143", "SEV-1"
        )
        assert status == "triggered"
        mock_recovery_repo.trigger_step_function.assert_called_once()

    @patch.dict(os.environ, {"RECONCILIATION_WORKFLOW_ARN": "arn:aws:states:us-west-2:320644769527:stateMachine:Reconcile"})
    def test_data_correction_triggers_step_function(self, resolution_service, mock_recovery_repo):
        status, _ = resolution_service.trigger_recovery(
            "data-correction", "calc-error-prod", "INC-144", "SEV-1"
        )
        assert status == "triggered"

    @patch.dict(os.environ, {"REPLAY_DLQ_WORKFLOW_ARN": "arn:aws:states:us-west-2:320644769527:stateMachine:ReplayDLQ"})
    def test_sfn_failure_returns_failed(self, resolution_service, mock_recovery_repo):
        mock_recovery_repo.trigger_step_function.return_value = None

        status, detail = resolution_service.trigger_recovery(
            "replay", "calc-error-prod", "INC-142", "SEV-1"
        )
        assert status == "failed"

    @patch.dict(os.environ, {"REPLAY_DLQ_WORKFLOW_ARN": ""})
    def test_missing_arn_returns_not_configured(self, resolution_service):
        status, detail = resolution_service.trigger_recovery(
            "replay", "calc-error-prod", "INC-142", "SEV-1"
        )
        assert status == "not-configured"


# ------------------------------------------------------------------ #
# Recovery: Lambda
# ------------------------------------------------------------------ #

class TestRecoveryLambda:
    """Recovery via Lambda invocation (backlog-drain)."""

    @patch.dict(os.environ, {"BACKLOG_DRAIN_FUNCTION_NAME": "backlog-drain-prod"})
    def test_backlog_drain_invokes_lambda(self, resolution_service, mock_recovery_repo):
        status, detail = resolution_service.trigger_recovery(
            "backlog-drain", "calc-error-prod", "INC-142", "SEV-1"
        )

        assert status == "triggered"
        mock_recovery_repo.trigger_recovery_lambda.assert_called_once()
        payload = mock_recovery_repo.trigger_recovery_lambda.call_args[0][1]
        assert payload["incident_key"] == "calc-error-prod"
        assert payload["recovery_model"] == "backlog-drain"

    @patch.dict(os.environ, {"BACKLOG_DRAIN_FUNCTION_NAME": "backlog-drain-prod"})
    def test_lambda_failure_returns_failed(self, resolution_service, mock_recovery_repo):
        mock_recovery_repo.trigger_recovery_lambda.return_value = None

        status, _ = resolution_service.trigger_recovery(
            "backlog-drain", "calc-error-prod", "INC-142", "SEV-1"
        )
        assert status == "failed"

    @patch.dict(os.environ, {"BACKLOG_DRAIN_FUNCTION_NAME": ""})
    def test_missing_fn_name_returns_not_configured(self, resolution_service):
        status, _ = resolution_service.trigger_recovery(
            "backlog-drain", "calc-error-prod", "INC-142", "SEV-1"
        )
        assert status == "not-configured"


# ------------------------------------------------------------------ #
# Recovery: Edge Cases
# ------------------------------------------------------------------ #

class TestRecoveryEdgeCases:

    def test_stateless_returns_not_required(self, resolution_service):
        status, detail = resolution_service.trigger_recovery(
            "stateless", "calc-error-prod", "INC-142", "SEV-1"
        )
        assert status == "not-required"
        assert detail == ""

    def test_unknown_model_returns_not_configured(self, resolution_service):
        status, detail = resolution_service.trigger_recovery(
            "nonexistent-model", "calc-error-prod", "INC-142", "SEV-1"
        )
        assert status == "not-configured"

    @patch.dict(os.environ, {"REPLAY_DLQ_WORKFLOW_ARN": "arn:aws:states:us-west-2:320644769527:stateMachine:ReplayDLQ"})
    def test_payload_includes_idempotency_keys(self, resolution_service, mock_recovery_repo):
        resolution_service.trigger_recovery(
            "replay", "calculator-error-rate-prod", "INC-142", "SEV-1"
        )

        payload = mock_recovery_repo.trigger_step_function.call_args[0][1]
        assert payload["incident_key"] == "calculator-error-rate-prod"
        assert payload["jira_ticket_id"] == "INC-142"
        assert "execution_id" in payload
        assert payload["execution_id"].startswith("calculator-error-rate-prod-")


# ------------------------------------------------------------------ #
# Recovery: Checkpoint-aware Delta Report
# ------------------------------------------------------------------ #

class TestRecoveryCheckpointAware:
    """Recovery via checkpoint delta report (reprocess with checkpoint_aware=True)."""

    @pytest.fixture
    def mock_delta_report(self):
        return Mock()

    @pytest.fixture
    def resolution_with_delta(
        self, mock_remediation_repo, mock_recovery_repo, mock_observability_repo,
        mock_log_analysis_service, incident_config, mock_delta_report,
    ):
        return ResolutionService(
            remediation_engine=RemediationEngine(),
            remediation_repo=mock_remediation_repo,
            recovery_repo=mock_recovery_repo,
            observability_repo=mock_observability_repo,
            log_analysis_service=mock_log_analysis_service,
            config=incident_config,
            delta_report_service=mock_delta_report,
        )

    def test_checkpoint_aware_triggers_delta_report(self, resolution_with_delta, mock_delta_report, mock_recovery_repo):
        mock_delta_report.generate_and_post.return_value = {
            "checkpoints_found": 2, "total_pending": 45, "zombies_found": 0, "report_posted": True,
        }

        status, detail = resolution_with_delta.trigger_recovery(
            "reprocess", "batch-api-error-prod", "INC-200", "SEV-1",
            service_name="batch-api-dev",
        )

        assert status == "delta-reported"
        assert "2 checkpoints" in detail
        assert "45 pending" in detail
        mock_delta_report.generate_and_post.assert_called_once_with(
            service_name="batch-api-dev", jira_ticket_id="INC-200",
        )
        mock_recovery_repo.trigger_step_function.assert_not_called()

    def test_checkpoint_aware_includes_zombie_count(self, resolution_with_delta, mock_delta_report):
        mock_delta_report.generate_and_post.return_value = {
            "checkpoints_found": 1, "total_pending": 10, "zombies_found": 1, "report_posted": True,
        }

        status, detail = resolution_with_delta.trigger_recovery(
            "reprocess", "batch-api-error-prod", "INC-201", "SEV-1",
            service_name="batch-api-dev",
        )

        assert status == "delta-reported"
        assert "1 zombies" in detail

    def test_service_name_forwarded_to_delta_report(self, resolution_with_delta, mock_delta_report):
        mock_delta_report.generate_and_post.return_value = {
            "checkpoints_found": 0, "total_pending": 0, "zombies_found": 0, "report_posted": False,
        }

        resolution_with_delta.trigger_recovery(
            "reprocess", "batch-api-error-prod", "INC-202", "SEV-1",
            service_name="my-batch-service",
        )

        call_kwargs = mock_delta_report.generate_and_post.call_args[1]
        assert call_kwargs["service_name"] == "my-batch-service"
        assert call_kwargs["jira_ticket_id"] == "INC-202"

    @patch.dict(os.environ, {"REPROCESS_BATCH_WORKFLOW_ARN": "arn:aws:states:us-west-2:123:stateMachine:Reprocess"})
    def test_non_checkpoint_aware_still_triggers_sfn(self, resolution_service, mock_recovery_repo):
        """Without delta_report_service, reprocess falls back to Step Function."""
        status, _ = resolution_service.trigger_recovery(
            "reprocess", "calc-error-prod", "INC-203", "SEV-1"
        )
        assert status == "triggered"
        mock_recovery_repo.trigger_step_function.assert_called_once()

    def test_no_delta_service_falls_through_to_sfn(
        self, mock_remediation_repo, mock_recovery_repo, mock_observability_repo,
        mock_log_analysis_service, incident_config,
    ):
        """When delta_report_service is None, checkpoint_aware flag is ignored."""
        svc = ResolutionService(
            remediation_engine=RemediationEngine(),
            remediation_repo=mock_remediation_repo,
            recovery_repo=mock_recovery_repo,
            observability_repo=mock_observability_repo,
            log_analysis_service=mock_log_analysis_service,
            config=incident_config,
            delta_report_service=None,
        )
        with patch.dict(os.environ, {"REPROCESS_BATCH_WORKFLOW_ARN": "arn:aws:states:us-west-2:123:stateMachine:R"}):
            status, _ = svc.trigger_recovery("reprocess", "calc-error", "INC-204", "SEV-1")
        assert status == "triggered"

    @patch.dict(os.environ, {"REPLAY_DLQ_WORKFLOW_ARN": "arn:aws:states:us-west-2:123:stateMachine:Replay"})
    def test_non_checkpoint_aware_model_ignores_delta_service(self, resolution_with_delta, mock_delta_report, mock_recovery_repo):
        """replay is not checkpoint_aware — should trigger Step Function, not delta report."""
        status, _ = resolution_with_delta.trigger_recovery(
            "replay", "calc-error-prod", "INC-205", "SEV-1"
        )
        assert status == "triggered"
        mock_delta_report.generate_and_post.assert_not_called()
        mock_recovery_repo.trigger_step_function.assert_called_once()
