"""Tests for Escalation Lambda handler — EventBridge event parsing and delegation."""

import pytest
from unittest.mock import Mock, patch

from src.handlers import escalation_handler


@pytest.fixture(autouse=True)
def reset_handler():
    """Reset module-level singleton between tests."""
    escalation_handler._escalation_service = None
    escalation_handler._config = None
    yield
    escalation_handler._escalation_service = None
    escalation_handler._config = None


@pytest.fixture
def mock_escalation_service():
    service = Mock()
    service.escalate.return_value = "escalated"
    return service


class TestEscalationHandler:
    """Handler parses EventBridge event and passes fields correctly."""

    def test_passes_all_fields(
        self, escalation_required_event, mock_escalation_service, lambda_context
    ):
        escalation_handler._escalation_service = mock_escalation_service

        result = escalation_handler.lambda_handler(escalation_required_event, lambda_context)

        assert result["status"] == "escalated"
        assert result["incident_key"] == "calculator-error-rate-prod"

        mock_escalation_service.escalate.assert_called_once_with(
            incident_key="calculator-error-rate-prod",
            jira_ticket_id="INC-142",
            service="calculator",
            stage="prod",
            severity="SEV-1",
            reason="verification-failed",
            function_name="calculator-api-prod",
            verification=None,
            root_cause="",
            confidence="",
            service_type="lambda",
            alarm_type="",
            remediation_outcome="",
            log_analysis="",
        )

    def test_passes_reason(self, mock_escalation_service, lambda_context):
        event = {
            "detail": {
                "incident_key": "payments-queue-backlog-prod",
                "jira_ticket_id": "INC-200",
                "service": "payments",
                "stage": "prod",
                "severity": "SEV-2",
                "reason": "incident-storm",
                "function_name": "payments-api-prod",
                "root_cause": "rate-limit",
            }
        }
        escalation_handler._escalation_service = mock_escalation_service

        result = escalation_handler.lambda_handler(event, lambda_context)

        call_kwargs = mock_escalation_service.escalate.call_args[1]
        assert call_kwargs["reason"] == "incident-storm"
        assert call_kwargs["root_cause"] == "rate-limit"

    def test_passes_verification_details(self, mock_escalation_service, lambda_context):
        event = {
            "detail": {
                "incident_key": "calc-error-rate-prod",
                "jira_ticket_id": "INC-300",
                "service": "calc",
                "stage": "prod",
                "severity": "SEV-1",
                "reason": "verification-failed",
                "verification": {
                    "alarm_ok": False,
                    "health_ok": True,
                    "error_rate_ok": True,
                },
            }
        }
        escalation_handler._escalation_service = mock_escalation_service

        escalation_handler.lambda_handler(event, lambda_context)

        call_kwargs = mock_escalation_service.escalate.call_args[1]
        assert call_kwargs["verification"]["alarm_ok"] is False

    def test_defaults_for_optional_fields(self, mock_escalation_service, lambda_context):
        event = {
            "detail": {
                "incident_key": "svc-error-rate-dev",
                "jira_ticket_id": "INC-400",
                "service": "svc",
                "stage": "dev",
                "severity": "SEV-3",
            }
        }
        escalation_handler._escalation_service = mock_escalation_service

        escalation_handler.lambda_handler(event, lambda_context)

        call_kwargs = mock_escalation_service.escalate.call_args[1]
        assert call_kwargs["reason"] == "unknown"
        assert call_kwargs["function_name"] == ""
        assert call_kwargs["root_cause"] == ""

    def test_error_returns_error_status(self, mock_escalation_service, lambda_context):
        mock_escalation_service.escalate.side_effect = RuntimeError("boom")
        escalation_handler._escalation_service = mock_escalation_service

        event = {
            "detail": {
                "incident_key": "svc-err-prod",
                "jira_ticket_id": "INC-500",
                "service": "svc",
                "stage": "prod",
                "severity": "SEV-1",
                "reason": "test",
            }
        }
        result = escalation_handler.lambda_handler(event, lambda_context)
        assert result["status"] == "error"
        assert "boom" in result["error"]

    def test_missing_detail_returns_error(self, mock_escalation_service, lambda_context):
        escalation_handler._escalation_service = mock_escalation_service
        result = escalation_handler.lambda_handler({}, lambda_context)
        assert result["status"] == "error"
