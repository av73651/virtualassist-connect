"""Tests for Detection Lambda handler — SNS event parsing, routing, error handling."""

import json
import pytest
from unittest.mock import patch, Mock, MagicMock
from freezegun import freeze_time

from src.handlers.detection_handler import lambda_handler, _process_record, _detection_service
import src.handlers.detection_handler as handler_module


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

@pytest.fixture
def mock_detection_service():
    """Mock DetectionService injected into handler module."""
    service = Mock()
    service.process_alarm.return_value = "INC-142"
    service.process_recovery.return_value = True
    return service


@pytest.fixture(autouse=True)
def inject_mock_service(mock_detection_service, incident_config):
    """Inject mock service and config, reset after each test."""
    handler_module._detection_service = mock_detection_service
    handler_module._config = incident_config
    yield
    handler_module._detection_service = None
    handler_module._config = None


# ------------------------------------------------------------------ #
# Handler processes SNS alarm record
# ------------------------------------------------------------------ #

class TestHandlerProcessesSNSAlarm:
    """Handler parses SNS event and delegates to DetectionService."""

    def test_handler_returns_processed_count(self, sns_alarm_event, severity_mapping):
        result = lambda_handler(sns_alarm_event, Mock())
        assert result["processed"] == 1

    def test_handler_creates_incident(self, sns_alarm_event, mock_detection_service):
        lambda_handler(sns_alarm_event, Mock())

        mock_detection_service.process_alarm.assert_called_once()
        alarm_event = mock_detection_service.process_alarm.call_args[0][0]
        assert alarm_event.service == "calculator"
        assert alarm_event.incident_key == "calculator-error-rate-prod"

    def test_handler_result_includes_ticket(self, sns_alarm_event):
        result = lambda_handler(sns_alarm_event, Mock())

        assert result["results"][0]["status"] == "created"
        assert result["results"][0]["jira_ticket_id"] == "INC-142"

    def test_handler_result_includes_metadata(self, sns_alarm_event):
        result = lambda_handler(sns_alarm_event, Mock())

        assert result["results"][0]["service"] == "calculator"
        assert result["results"][0]["severity"] == "SEV-1"
        assert result["results"][0]["recovery_model"] == "stateless"


# ------------------------------------------------------------------ #
# Handler routes OK to process_recovery
# ------------------------------------------------------------------ #

class TestHandlerRecoveryEvent:
    """Handler routes OK state to process_recovery."""

    def test_recovery_event_calls_process_recovery(self, sns_recovery_event, mock_detection_service):
        """OK event calls process_recovery, not process_alarm."""
        result = lambda_handler(sns_recovery_event, Mock())

        mock_detection_service.process_recovery.assert_called_once()
        mock_detection_service.process_alarm.assert_not_called()

        recovery_event = mock_detection_service.process_recovery.call_args[0][0]
        assert recovery_event.is_recovery is True
        assert recovery_event.incident_key == "calculator-error-rate-prod"

    def test_recovery_success_returns_recovered(self, sns_recovery_event, mock_detection_service):
        """Successful recovery returns status=recovered."""
        mock_detection_service.process_recovery.return_value = True

        result = lambda_handler(sns_recovery_event, Mock())
        assert result["results"][0]["status"] == "recovered"

    def test_recovery_skip_returns_recovery_skipped(self, sns_recovery_event, mock_detection_service):
        """No matching incident returns status=recovery_skipped."""
        mock_detection_service.process_recovery.return_value = False

        result = lambda_handler(sns_recovery_event, Mock())
        assert result["results"][0]["status"] == "recovery_skipped"


# ------------------------------------------------------------------ #
# Filtered result (duplicate / no ticket)
# ------------------------------------------------------------------ #

class TestHandlerFilteredResult:
    """Handler returns filtered status when process_alarm returns None."""

    def test_filtered_when_no_ticket(self, sns_alarm_event, mock_detection_service):
        mock_detection_service.process_alarm.return_value = None

        result = lambda_handler(sns_alarm_event, Mock())

        assert result["results"][0]["status"] == "filtered"
        assert "jira_ticket_id" not in result["results"][0]


# ------------------------------------------------------------------ #
# Error handling + mixed record isolation
# ------------------------------------------------------------------ #

class TestHandlerErrorHandling:
    """Handler handles parse errors and exceptions gracefully."""

    def test_malformed_alarm_name_error(self, severity_mapping):
        event = {
            "Records": [{
                "Sns": {
                    "Message": json.dumps({
                        "AlarmName": "bad-name",
                        "NewStateValue": "ALARM",
                        "OldStateValue": "OK",
                    })
                }
            }]
        }

        result = lambda_handler(event, Mock())

        assert result["processed"] == 1
        assert result["results"][0]["status"] == "error"
        assert "error" in result["results"][0]

    def test_empty_records(self):
        result = lambda_handler({"Records": []}, Mock())

        assert result["processed"] == 0
        assert result["results"] == []

    def test_multiple_records_processed_independently(self, sns_alarm_event, mock_detection_service):
        """Each record processed independently (P6: failure isolation)."""
        event = {
            "Records": [
                sns_alarm_event["Records"][0],
                {
                    "Sns": {
                        "Message": json.dumps({
                            "AlarmName": "bad-name",
                            "NewStateValue": "ALARM",
                            "OldStateValue": "OK",
                        })
                    }
                },
            ]
        }

        result = lambda_handler(event, Mock())

        assert result["processed"] == 2
        assert result["results"][0]["status"] == "created"
        assert result["results"][1]["status"] == "error"

    def test_service_exception_caught(self, sns_alarm_event, mock_detection_service):
        mock_detection_service.process_alarm.side_effect = RuntimeError("unexpected")

        result = lambda_handler(sns_alarm_event, Mock())

        assert result["results"][0]["status"] == "error"
        assert "unexpected" in result["results"][0]["error"]

    def test_mixed_alarm_malformed_recovery_isolation(self, sns_alarm_event, sns_recovery_event, mock_detection_service):
        """3 records [valid_alarm, malformed, valid_recovery] — all processed independently."""
        event = {
            "Records": [
                sns_alarm_event["Records"][0],
                {
                    "Sns": {
                        "Message": json.dumps({
                            "AlarmName": "bad-name",
                            "NewStateValue": "ALARM",
                            "OldStateValue": "OK",
                        })
                    }
                },
                sns_recovery_event["Records"][0],
            ]
        }

        result = lambda_handler(event, Mock())

        assert result["processed"] == 3
        assert result["results"][0]["status"] == "created"
        assert result["results"][1]["status"] == "error"
        assert result["results"][2]["status"] == "recovered"

        mock_detection_service.process_alarm.assert_called_once()
        mock_detection_service.process_recovery.assert_called_once()
