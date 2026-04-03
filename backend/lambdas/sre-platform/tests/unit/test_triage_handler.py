"""Tests for Triage Lambda handler — EventBridge event parsing and TriageService delegation."""

import pytest
from unittest.mock import Mock, patch, MagicMock


# ------------------------------------------------------------------ #
# Triage Handler — Passes recovery_model
# ------------------------------------------------------------------ #

class TestTriageHandler:
    """Handler parses EventBridge event and delegates to TriageService."""

    @patch("src.handlers.triage_handler._triage_service", None)
    @patch("src.handlers.triage_handler._init_services")
    def test_initializes_on_cold_start(self, mock_init, incident_created_event, lambda_context):
        """Cold start triggers _init_services."""
        from src.handlers.triage_handler import lambda_handler

        mock_service = Mock()
        mock_service.triage.return_value = "auto-resolved"

        def set_service():
            import src.handlers.triage_handler as module
            module._triage_service = mock_service

        mock_init.side_effect = set_service

        result = lambda_handler(incident_created_event, lambda_context)
        mock_init.assert_called_once()

    @patch("src.handlers.triage_handler._triage_service")
    def test_passes_incident_key(self, mock_service, incident_created_event, lambda_context):
        mock_service.triage.return_value = "auto-resolved"

        from src.handlers.triage_handler import lambda_handler
        lambda_handler(incident_created_event, lambda_context)

        call_kwargs = mock_service.triage.call_args[1]
        assert call_kwargs["incident_key"] == "calculator-error-rate-prod"

    @patch("src.handlers.triage_handler._triage_service")
    def test_passes_jira_ticket_id(self, mock_service, incident_created_event, lambda_context):
        mock_service.triage.return_value = "auto-resolved"

        from src.handlers.triage_handler import lambda_handler
        lambda_handler(incident_created_event, lambda_context)

        call_kwargs = mock_service.triage.call_args[1]
        assert call_kwargs["jira_ticket_id"] == "INC-142"

    @patch("src.handlers.triage_handler._triage_service")
    def test_passes_service_and_stage(self, mock_service, incident_created_event, lambda_context):
        mock_service.triage.return_value = "auto-resolved"

        from src.handlers.triage_handler import lambda_handler
        lambda_handler(incident_created_event, lambda_context)

        call_kwargs = mock_service.triage.call_args[1]
        assert call_kwargs["service"] == "calculator"
        assert call_kwargs["stage"] == "prod"

    @patch("src.handlers.triage_handler._triage_service")
    def test_passes_severity(self, mock_service, incident_created_event, lambda_context):
        mock_service.triage.return_value = "auto-resolved"

        from src.handlers.triage_handler import lambda_handler
        lambda_handler(incident_created_event, lambda_context)

        call_kwargs = mock_service.triage.call_args[1]
        assert call_kwargs["severity"] == "SEV-1"

    @patch("src.handlers.triage_handler._triage_service")
    def test_passes_service_type(self, mock_service, incident_created_event, lambda_context):
        """service_type propagated from event detail."""
        mock_service.triage.return_value = "auto-resolved"

        from src.handlers.triage_handler import lambda_handler
        lambda_handler(incident_created_event, lambda_context)

        call_kwargs = mock_service.triage.call_args[1]
        assert call_kwargs["service_type"] == "lambda"

    @patch("src.handlers.triage_handler._triage_service")
    def test_defaults_service_type_to_lambda(self, mock_service, lambda_context):
        """If service_type missing from event, default to lambda."""
        mock_service.triage.return_value = "auto-resolved"

        event = {
            "source": "sre-platform",
            "detail-type": "IncidentCreated",
            "detail": {
                "incident_key": "calculator-error-rate-prod",
                "jira_ticket_id": "INC-142",
                "service": "calculator",
                "stage": "prod",
                "severity": "SEV-1",
            },
        }

        from src.handlers.triage_handler import lambda_handler
        lambda_handler(event, lambda_context)

        call_kwargs = mock_service.triage.call_args[1]
        assert call_kwargs["service_type"] == "lambda"

    @patch("src.handlers.triage_handler._triage_service")
    def test_passes_recovery_model_stateless(self, mock_service, incident_created_event, lambda_context):
        """recovery_model=stateless propagated to service."""
        mock_service.triage.return_value = "auto-resolved"

        from src.handlers.triage_handler import lambda_handler
        lambda_handler(incident_created_event, lambda_context)

        call_kwargs = mock_service.triage.call_args[1]
        assert call_kwargs["recovery_model"] == "stateless"

    @patch("src.handlers.triage_handler._triage_service")
    def test_passes_recovery_model_replay(self, mock_service, lambda_context):
        """recovery_model=replay propagated to service."""
        mock_service.triage.return_value = "auto-resolved"

        event = {
            "source": "sre-platform",
            "detail-type": "IncidentCreated",
            "detail": {
                "incident_key": "payments-queue-backlog-prod",
                "jira_ticket_id": "INC-200",
                "service": "payments",
                "stage": "prod",
                "severity": "SEV-2",
                "recovery_model": "replay",
                "storm_detected": False,
            },
        }

        from src.handlers.triage_handler import lambda_handler
        lambda_handler(event, lambda_context)

        call_kwargs = mock_service.triage.call_args[1]
        assert call_kwargs["recovery_model"] == "replay"

    @patch("src.handlers.triage_handler._triage_service")
    def test_passes_enriched_fields(self, mock_service, incident_created_event, lambda_context):
        """alarm_name, function_name, log_group propagated from event detail."""
        mock_service.triage.return_value = "auto-resolved"

        from src.handlers.triage_handler import lambda_handler
        lambda_handler(incident_created_event, lambda_context)

        call_kwargs = mock_service.triage.call_args[1]
        assert call_kwargs["alarm_name"] == "calculator-high-error-rate-prod"
        assert call_kwargs["function_name"] == "calculator-api-prod"
        assert call_kwargs["log_group"] == "/aws/lambda/calculator-api-prod"

    @patch("src.handlers.triage_handler._triage_service")
    def test_passes_storm_detected(self, mock_service, incident_created_event, lambda_context):
        mock_service.triage.return_value = "escalated"

        from src.handlers.triage_handler import lambda_handler
        lambda_handler(incident_created_event, lambda_context)

        call_kwargs = mock_service.triage.call_args[1]
        assert call_kwargs["storm_detected"] is False

    @patch("src.handlers.triage_handler._triage_service")
    def test_returns_status(self, mock_service, incident_created_event, lambda_context):
        mock_service.triage.return_value = "auto-resolved"

        from src.handlers.triage_handler import lambda_handler
        result = lambda_handler(incident_created_event, lambda_context)

        assert result["incident_key"] == "calculator-error-rate-prod"
        assert result["status"] == "auto-resolved"

    @patch("src.handlers.triage_handler._triage_service")
    def test_handles_exception_gracefully(self, mock_service, incident_created_event, lambda_context):
        mock_service.triage.side_effect = Exception("Unexpected error")

        from src.handlers.triage_handler import lambda_handler
        result = lambda_handler(incident_created_event, lambda_context)

        assert result["status"] == "error"
        assert "Unexpected error" in result["error"]

    @patch("src.handlers.triage_handler._triage_service")
    def test_defaults_recovery_model_to_stateless(self, mock_service, lambda_context):
        """If recovery_model missing from event, default to stateless."""
        mock_service.triage.return_value = "auto-resolved"

        event = {
            "source": "sre-platform",
            "detail-type": "IncidentCreated",
            "detail": {
                "incident_key": "calculator-error-rate-prod",
                "jira_ticket_id": "INC-142",
                "service": "calculator",
                "stage": "prod",
                "severity": "SEV-1",
            },
        }

        from src.handlers.triage_handler import lambda_handler
        lambda_handler(event, lambda_context)

        call_kwargs = mock_service.triage.call_args[1]
        assert call_kwargs["recovery_model"] == "stateless"
        assert call_kwargs["storm_detected"] is False
