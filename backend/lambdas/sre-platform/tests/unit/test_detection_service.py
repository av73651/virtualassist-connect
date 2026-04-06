"""Tests for DetectionService — alarm processing, conflict handling, storm detection, recovery."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, call, patch
from freezegun import freeze_time

from src.models.enums import Severity, CorrelationStatus
from src.models.correlation_record import CorrelationRecord
from src.models.exceptions import DuplicateIncidentError
from src.services.detection_service import DetectionService


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

@pytest.fixture
def detection_service(mock_correlation_repo, mock_observability_repo, mock_ticketing_repo, mock_event_bus_repo, mock_log_analysis_service, mock_incident_reporter, incident_config):
    """DetectionService with mocked repos and reporter."""
    return DetectionService(
        correlation_repo=mock_correlation_repo,
        observability_repo=mock_observability_repo,
        ticketing_repo=mock_ticketing_repo,
        event_bus_repo=mock_event_bus_repo,
        log_analysis_service=mock_log_analysis_service,
        incident_reporter=mock_incident_reporter,
        config=incident_config,
    )


# ------------------------------------------------------------------ #
# New Incident — Full Flow (Stateless)
# ------------------------------------------------------------------ #

class TestNewIncidentFullFlow:
    """Happy path — alarm creates incident end-to-end."""

    @freeze_time("2026-03-30T12:00:00Z")
    @patch("src.services.detection_service.time.sleep")
    def test_returns_jira_ticket_id(self, mock_sleep, detection_service, alarm_event_sev1):
        result = detection_service.process_alarm(alarm_event_sev1)
        assert result == "INC-142"

    @freeze_time("2026-03-30T12:00:00Z")
    @patch("src.services.detection_service.time.sleep")
    def test_reserves_incident_key(self, mock_sleep, detection_service, alarm_event_sev1, mock_correlation_repo):
        detection_service.process_alarm(alarm_event_sev1)

        mock_correlation_repo.reserve.assert_called_once()
        record = mock_correlation_repo.reserve.call_args[0][0]
        assert record.incident_key == "calculator-error-rate-prod"
        assert record.status == CorrelationStatus.RESERVED
        assert record.severity == "SEV-1"
        assert record.jira_ticket_id is None

    @freeze_time("2026-03-30T12:00:00Z")
    @patch("src.services.detection_service.time.sleep")
    def test_creates_jira_ticket(self, mock_sleep, detection_service, alarm_event_sev1, mock_ticketing_repo):
        detection_service.process_alarm(alarm_event_sev1)

        mock_ticketing_repo.create_jira_ticket.assert_called_once()
        call_kwargs = mock_ticketing_repo.create_jira_ticket.call_args[1]
        assert "[SEV-1]" in call_kwargs["summary"]
        assert "calculator" in call_kwargs["summary"]
        assert "(prod)" in call_kwargs["summary"]
        assert call_kwargs["priority"] == "SEV-1"
        assert "incident" in call_kwargs["labels"]
        assert "automated" in call_kwargs["labels"]
        assert call_kwargs["incident_key"] == "calculator-error-rate-prod"

    @freeze_time("2026-03-30T12:00:00Z")
    @patch("src.services.detection_service.time.sleep")
    def test_updates_dynamo_to_detected(self, mock_sleep, detection_service, alarm_event_sev1, mock_correlation_repo):
        detection_service.process_alarm(alarm_event_sev1)

        mock_correlation_repo.update.assert_called_once()
        record = mock_correlation_repo.update.call_args[0][0]
        assert record.status == CorrelationStatus.DETECTED
        assert record.jira_ticket_id == "INC-142"

    @freeze_time("2026-03-30T12:00:00Z")
    @patch("src.services.detection_service.time.sleep")
    def test_publishes_incident_created_event(self, mock_sleep, detection_service, alarm_event_sev1, mock_event_bus_repo):
        detection_service.process_alarm(alarm_event_sev1)

        mock_event_bus_repo.publish_event.assert_called_once()
        args = mock_event_bus_repo.publish_event.call_args
        assert args[0][0] == "IncidentCreated"
        detail = args[0][1]
        assert detail["incident_key"] == "calculator-error-rate-prod"
        assert detail["jira_ticket_id"] == "INC-142"
        assert detail["severity"] == "SEV-1"
        assert detail["recovery_model"] == "stateless"
        assert detail["storm_detected"] is False
        assert detail["alarm_name"] == "calculator-high-error-rate-prod"
        assert detail["function_name"] == "calculator-api-prod"
        assert detail["log_group"] == "/aws/lambda/calculator-api-prod"

    @freeze_time("2026-03-30T12:00:00Z")
    @patch("src.services.detection_service.time.sleep")
    def test_cool_off_sleep_called(self, mock_sleep, detection_service, alarm_event_sev1):
        """Cool-off sleep is called with correct duration for SEV-1 (30s)."""
        detection_service.process_alarm(alarm_event_sev1)
        mock_sleep.assert_called_with(30)

    @freeze_time("2026-03-30T12:00:00Z")
    @patch("src.services.detection_service.time.sleep")
    def test_jira_description_contains_metadata(self, mock_sleep, detection_service, alarm_event_sev1, mock_ticketing_repo):
        detection_service.process_alarm(alarm_event_sev1)

        call_kwargs = mock_ticketing_repo.create_jira_ticket.call_args[1]
        desc = call_kwargs["description"]
        assert "calculator" in desc
        assert "prod" in desc
        assert "SEV-1" in desc
        assert "stateless" in desc


# ------------------------------------------------------------------ #
# New Incident — Replay Recovery Model
# ------------------------------------------------------------------ #

class TestRecoveryModelRelay:
    """Replay recovery model flows through to EventBridge."""

    @freeze_time("2026-03-30T12:00:00Z")
    @patch("src.services.detection_service.time.sleep")
    def test_replay_recovery_model_in_event(self, mock_sleep, detection_service, alarm_event_queue_backlog, mock_event_bus_repo):
        detection_service.process_alarm(alarm_event_queue_backlog)

        detail = mock_event_bus_repo.publish_event.call_args[0][1]
        assert detail["recovery_model"] == "replay"
        assert detail["severity"] == "SEV-2"

    @freeze_time("2026-03-30T12:00:00Z")
    @patch("src.services.detection_service.time.sleep")
    def test_replay_returns_ticket_id(self, mock_sleep, detection_service, alarm_event_queue_backlog):
        result = detection_service.process_alarm(alarm_event_queue_backlog)
        assert result == "INC-142"


# ------------------------------------------------------------------ #
# Cool-Off Filters Transient Spike
# ------------------------------------------------------------------ #

class TestCoolOffFiltersTransient:
    """Alarm recovers during cool-off -> skip."""

    @freeze_time("2026-03-30T12:00:00Z")
    @patch("src.services.detection_service.time.sleep")
    def test_transient_alarm_returns_none(self, mock_sleep, detection_service, alarm_event_sev1, mock_observability_repo):
        """Alarm state = OK after cool-off -> returns None."""
        mock_observability_repo.get_alarm_state.return_value = "OK"

        result = detection_service.process_alarm(alarm_event_sev1)
        assert result is None

    @freeze_time("2026-03-30T12:00:00Z")
    @patch("src.services.detection_service.time.sleep")
    def test_transient_no_reservation(self, mock_sleep, detection_service, alarm_event_sev1, mock_observability_repo, mock_correlation_repo):
        """No DynamoDB reservation when alarm recovers during cool-off."""
        mock_observability_repo.get_alarm_state.return_value = "OK"

        detection_service.process_alarm(alarm_event_sev1)
        mock_correlation_repo.reserve.assert_not_called()

    @freeze_time("2026-03-30T12:00:00Z")
    @patch("src.services.detection_service.time.sleep")
    def test_transient_no_jira_ticket(self, mock_sleep, detection_service, alarm_event_sev1, mock_observability_repo, mock_ticketing_repo):
        """No Jira ticket when alarm recovers during cool-off."""
        mock_observability_repo.get_alarm_state.return_value = "OK"

        detection_service.process_alarm(alarm_event_sev1)
        mock_ticketing_repo.create_jira_ticket.assert_not_called()


# ------------------------------------------------------------------ #
# RESERVED Conflict — Another Lambda Won
# ------------------------------------------------------------------ #

class TestReservedConflict:
    """Fresh RESERVED record exists — exit silently."""

    @freeze_time("2026-03-30T12:00:00Z")
    @patch("src.services.detection_service.time.sleep")
    def test_reserved_conflict_returns_none(self, mock_sleep, detection_service, alarm_event_sev1, mock_correlation_repo, fixed_now):
        mock_correlation_repo.reserve.side_effect = DuplicateIncidentError("exists")
        mock_correlation_repo.get.return_value = CorrelationRecord(
            incident_key="calculator-error-rate-prod",
            jira_ticket_id=None,
            severity="SEV-1",
            status=CorrelationStatus.RESERVED,
            created_at=fixed_now,
            ttl=int((fixed_now + timedelta(hours=24)).timestamp()),
        )

        result = detection_service.process_alarm(alarm_event_sev1)
        assert result is None

    @freeze_time("2026-03-30T12:00:00Z")
    @patch("src.services.detection_service.time.sleep")
    def test_reserved_conflict_no_jira(self, mock_sleep, detection_service, alarm_event_sev1, mock_correlation_repo, mock_ticketing_repo, mock_incident_reporter, fixed_now):
        mock_correlation_repo.reserve.side_effect = DuplicateIncidentError("exists")
        mock_correlation_repo.get.return_value = CorrelationRecord(
            incident_key="calculator-error-rate-prod",
            jira_ticket_id=None,
            severity="SEV-1",
            status=CorrelationStatus.RESERVED,
            created_at=fixed_now,
            ttl=int((fixed_now + timedelta(hours=24)).timestamp()),
        )

        detection_service.process_alarm(alarm_event_sev1)
        mock_ticketing_repo.create_jira_ticket.assert_not_called()
        mock_incident_reporter.report_duplicate_alarm.assert_not_called()


# ------------------------------------------------------------------ #
# DETECTED Conflict — Add Duplicate Comment
# ------------------------------------------------------------------ #

class TestDetectedConflict:
    """DETECTED record exists — add comment to existing ticket."""

    @freeze_time("2026-03-30T12:00:00Z")
    @patch("src.services.detection_service.time.sleep")
    def test_detected_conflict_reports_duplicate(self, mock_sleep, detection_service, alarm_event_sev1, mock_correlation_repo, mock_incident_reporter, detected_record):
        mock_correlation_repo.reserve.side_effect = DuplicateIncidentError("exists")
        mock_correlation_repo.get.return_value = detected_record

        result = detection_service.process_alarm(alarm_event_sev1)

        assert result is None
        mock_incident_reporter.report_duplicate_alarm.assert_called_once_with(
            "INC-142", "calculator-error-rate-prod"
        )

    @freeze_time("2026-03-30T12:00:00Z")
    @patch("src.services.detection_service.time.sleep")
    def test_detected_conflict_no_new_ticket(self, mock_sleep, detection_service, alarm_event_sev1, mock_correlation_repo, mock_ticketing_repo, mock_incident_reporter, detected_record):
        mock_correlation_repo.reserve.side_effect = DuplicateIncidentError("exists")
        mock_correlation_repo.get.return_value = detected_record

        detection_service.process_alarm(alarm_event_sev1)
        mock_ticketing_repo.create_jira_ticket.assert_not_called()


# ------------------------------------------------------------------ #
# GRACE Conflict — Recurrence
# ------------------------------------------------------------------ #

class TestGraceConflict:
    """GRACE record exists — recurrence, escalate."""

    @freeze_time("2026-03-30T12:00:00Z")
    @patch("src.services.detection_service.time.sleep")
    def test_grace_recurrence_reports_to_jira(self, mock_sleep, detection_service, alarm_event_sev1, mock_correlation_repo, mock_incident_reporter, grace_record):
        mock_correlation_repo.reserve.side_effect = DuplicateIncidentError("exists")
        mock_correlation_repo.get.return_value = grace_record

        detection_service.process_alarm(alarm_event_sev1)

        mock_incident_reporter.report_grace_recurrence.assert_called_once_with("INC-142")

    @freeze_time("2026-03-30T12:00:00Z")
    @patch("src.services.detection_service.time.sleep")
    def test_grace_recurrence_updates_to_detected(self, mock_sleep, detection_service, alarm_event_sev1, mock_correlation_repo, grace_record):
        mock_correlation_repo.reserve.side_effect = DuplicateIncidentError("exists")
        mock_correlation_repo.get.return_value = grace_record

        detection_service.process_alarm(alarm_event_sev1)

        mock_correlation_repo.update.assert_called_once()
        record = mock_correlation_repo.update.call_args[0][0]
        assert record.status == CorrelationStatus.DETECTED
        assert record.jira_ticket_id == "INC-142"

    @freeze_time("2026-03-30T12:00:00Z")
    @patch("src.services.detection_service.time.sleep")
    def test_grace_recurrence_publishes_escalation(self, mock_sleep, detection_service, alarm_event_sev1, mock_correlation_repo, mock_event_bus_repo, grace_record):
        mock_correlation_repo.reserve.side_effect = DuplicateIncidentError("exists")
        mock_correlation_repo.get.return_value = grace_record

        detection_service.process_alarm(alarm_event_sev1)

        mock_event_bus_repo.publish_event.assert_called_once()
        args = mock_event_bus_repo.publish_event.call_args
        assert args[0][0] == "EscalationRequired"
        detail = args[0][1]
        assert detail["reason"] == "grace-period-recurrence"
        assert detail["incident_key"] == "calculator-error-rate-prod"
        assert detail["jira_ticket_id"] == "INC-142"

    @freeze_time("2026-03-30T12:00:00Z")
    @patch("src.services.detection_service.time.sleep")
    def test_grace_recurrence_fresh_ttl(self, mock_sleep, detection_service, alarm_event_sev1, mock_correlation_repo, grace_record):
        """GRACE -> DETECTED gets fresh 24h TTL."""
        mock_correlation_repo.reserve.side_effect = DuplicateIncidentError("exists")
        mock_correlation_repo.get.return_value = grace_record

        detection_service.process_alarm(alarm_event_sev1)

        record = mock_correlation_repo.update.call_args[0][0]
        now = datetime(2026, 3, 30, 12, 0, 0, tzinfo=timezone.utc)
        expected_ttl = int((now + timedelta(hours=24)).timestamp())
        assert record.ttl == expected_ttl


# ------------------------------------------------------------------ #
# Stale RESERVED Record Recovery
# ------------------------------------------------------------------ #

class TestStaleReservedRecovery:
    """Stale RESERVED record reclaimed and retried."""

    @freeze_time("2026-03-30T12:00:00Z")
    @patch("src.services.detection_service.time.sleep")
    def test_stale_reserved_reclaimed(self, mock_sleep, detection_service, alarm_event_sev1, mock_correlation_repo):
        """Stale RESERVED (>180s) is deleted and reserve retried."""
        stale_time = datetime(2026, 3, 30, 11, 56, 0, tzinfo=timezone.utc)  # 4 min ago > 180s
        stale_record = CorrelationRecord(
            incident_key="calculator-error-rate-prod",
            jira_ticket_id=None,
            severity="SEV-1",
            status=CorrelationStatus.RESERVED,
            created_at=stale_time,
            ttl=int((stale_time + timedelta(hours=24)).timestamp()),
        )

        # First reserve fails, get returns stale record, then retry reserve succeeds
        mock_correlation_repo.reserve.side_effect = [
            DuplicateIncidentError("exists"),
            True,
        ]
        mock_correlation_repo.get.return_value = stale_record

        result = detection_service.process_alarm(alarm_event_sev1)

        assert result == "INC-142"
        mock_correlation_repo.delete.assert_called_with("calculator-error-rate-prod")
        assert mock_correlation_repo.reserve.call_count == 2

    @freeze_time("2026-03-30T12:00:00Z")
    @patch("src.services.detection_service.time.sleep")
    def test_stale_reserved_creates_ticket(self, mock_sleep, detection_service, alarm_event_sev1, mock_correlation_repo, mock_ticketing_repo, mock_event_bus_repo):
        """After stale reclaim, new Jira ticket is created."""
        stale_time = datetime(2026, 3, 30, 11, 56, 0, tzinfo=timezone.utc)
        stale_record = CorrelationRecord(
            incident_key="calculator-error-rate-prod",
            jira_ticket_id=None,
            severity="SEV-1",
            status=CorrelationStatus.RESERVED,
            created_at=stale_time,
            ttl=int((stale_time + timedelta(hours=24)).timestamp()),
        )

        mock_correlation_repo.reserve.side_effect = [
            DuplicateIncidentError("exists"),
            True,
        ]
        mock_correlation_repo.get.return_value = stale_record

        detection_service.process_alarm(alarm_event_sev1)

        mock_ticketing_repo.create_jira_ticket.assert_called_once()
        mock_event_bus_repo.publish_event.assert_called_once()


# ------------------------------------------------------------------ #
# Jira Failure — Cleanup
# ------------------------------------------------------------------ #

class TestJiraFailureRollback:
    """Jira creation failure rolls back DynamoDB reservation."""

    @freeze_time("2026-03-30T12:00:00Z")
    @patch("src.services.detection_service.time.sleep")
    def test_jira_failure_returns_none(self, mock_sleep, detection_service, alarm_event_sev1, mock_ticketing_repo):
        mock_ticketing_repo.create_jira_ticket.return_value = None

        result = detection_service.process_alarm(alarm_event_sev1)
        assert result is None

    @freeze_time("2026-03-30T12:00:00Z")
    @patch("src.services.detection_service.time.sleep")
    def test_jira_failure_deletes_reservation(self, mock_sleep, detection_service, alarm_event_sev1, mock_ticketing_repo, mock_correlation_repo):
        mock_ticketing_repo.create_jira_ticket.return_value = None

        detection_service.process_alarm(alarm_event_sev1)
        mock_correlation_repo.delete.assert_called_once_with("calculator-error-rate-prod")

    @freeze_time("2026-03-30T12:00:00Z")
    @patch("src.services.detection_service.time.sleep")
    def test_jira_failure_no_event_published(self, mock_sleep, detection_service, alarm_event_sev1, mock_ticketing_repo, mock_event_bus_repo):
        mock_ticketing_repo.create_jira_ticket.return_value = None

        detection_service.process_alarm(alarm_event_sev1)
        mock_event_bus_repo.publish_event.assert_not_called()

    @freeze_time("2026-03-30T12:00:00Z")
    @patch("src.services.detection_service.time.sleep")
    def test_jira_failure_no_dynamo_update(self, mock_sleep, detection_service, alarm_event_sev1, mock_ticketing_repo, mock_correlation_repo):
        mock_ticketing_repo.create_jira_ticket.return_value = None

        detection_service.process_alarm(alarm_event_sev1)
        mock_correlation_repo.update.assert_not_called()


# ------------------------------------------------------------------ #
# Duplicate Incident — simple DuplicateIncidentError (no existing record)
# ------------------------------------------------------------------ #

class TestDuplicateIncident:
    """Duplicate reserve with no existing record returns None."""

    @freeze_time("2026-03-30T12:00:00Z")
    @patch("src.services.detection_service.time.sleep")
    def test_duplicate_returns_none(self, mock_sleep, detection_service, alarm_event_sev1, mock_correlation_repo):
        mock_correlation_repo.reserve.side_effect = DuplicateIncidentError("exists")
        mock_correlation_repo.get.return_value = None

        result = detection_service.process_alarm(alarm_event_sev1)
        assert result is None

    @freeze_time("2026-03-30T12:00:00Z")
    @patch("src.services.detection_service.time.sleep")
    def test_duplicate_no_jira_call(self, mock_sleep, detection_service, alarm_event_sev1, mock_correlation_repo, mock_ticketing_repo):
        mock_correlation_repo.reserve.side_effect = DuplicateIncidentError("exists")
        mock_correlation_repo.get.return_value = None

        detection_service.process_alarm(alarm_event_sev1)
        mock_ticketing_repo.create_jira_ticket.assert_not_called()


# ------------------------------------------------------------------ #
# Storm Detection — Below Threshold
# ------------------------------------------------------------------ #

class TestStormBelowThreshold:
    """count_recent returns 3 (below threshold of 5) — no storm."""

    @freeze_time("2026-03-30T12:00:00Z")
    @patch("src.services.detection_service.time.sleep")
    def test_no_storm_below_threshold(self, mock_sleep, detection_service, alarm_event_sev1, mock_correlation_repo, mock_event_bus_repo):
        mock_correlation_repo.count_recent.return_value = 3

        detection_service.process_alarm(alarm_event_sev1)

        detail = mock_event_bus_repo.publish_event.call_args[0][1]
        assert detail["storm_detected"] is False
        assert "active_incident_count" not in detail


# ------------------------------------------------------------------ #
# Storm Detection — Above Threshold
# ------------------------------------------------------------------ #

class TestStormAboveThreshold:
    """count_recent returns 8 (above threshold of 5) — storm detected."""

    @freeze_time("2026-03-30T12:00:00Z")
    @patch("src.services.detection_service.time.sleep")
    def test_storm_detected_above_threshold(self, mock_sleep, detection_service, alarm_event_sev1, mock_correlation_repo, mock_event_bus_repo):
        mock_correlation_repo.count_recent.return_value = 8

        detection_service.process_alarm(alarm_event_sev1)

        detail = mock_event_bus_repo.publish_event.call_args[0][1]
        assert detail["storm_detected"] is True
        assert detail["active_incident_count"] == 8

    @freeze_time("2026-03-30T12:00:00Z")
    @patch("src.services.detection_service.time.sleep")
    def test_storm_still_creates_jira_ticket(self, mock_sleep, detection_service, alarm_event_sev1, mock_correlation_repo, mock_ticketing_repo):
        """Jira ticket still created during storms (incidents still tracked)."""
        mock_correlation_repo.count_recent.return_value = 8

        result = detection_service.process_alarm(alarm_event_sev1)

        assert result == "INC-142"
        mock_ticketing_repo.create_jira_ticket.assert_called_once()


# ------------------------------------------------------------------ #
# Alarm Recurs Within Grace Period
# Already covered in TestGraceConflict above.
# ------------------------------------------------------------------ #


# ------------------------------------------------------------------ #
# Alarm After Grace Expires — New Incident
# ------------------------------------------------------------------ #

class TestPostGraceNewIncident:
    """Grace expired (TTL deleted record) — treated as new incident."""

    @freeze_time("2026-03-30T14:30:00Z")
    @patch("src.services.detection_service.time.sleep")
    def test_post_grace_full_flow(self, mock_sleep, detection_service, alarm_event_sev1, mock_correlation_repo, mock_ticketing_repo, mock_event_bus_repo):
        """After grace expiry, reserve succeeds — full new incident flow."""
        # No existing record (DynamoDB TTL deleted it)
        mock_correlation_repo.reserve.return_value = True

        result = detection_service.process_alarm(alarm_event_sev1)

        assert result == "INC-142"
        mock_ticketing_repo.create_jira_ticket.assert_called_once()
        mock_event_bus_repo.publish_event.assert_called_once()
        assert mock_event_bus_repo.publish_event.call_args[0][0] == "IncidentCreated"


# ------------------------------------------------------------------ #
# Recovery — Active Incident
# ------------------------------------------------------------------ #

class TestRecoveryActiveIncident:
    """OK state resolves active incident."""

    def test_recovery_resolves_incident(self, detection_service, recovery_event, mock_correlation_repo, mock_log_analysis_service, mock_observability_repo, detected_record):
        mock_correlation_repo.get.return_value = detected_record
        mock_log_analysis_service.collect_recent.return_value = [
            {"message": "INFO: Health check OK", "timestamp": 1711800000000, "log_stream": "s1"}
        ]
        mock_observability_repo.get_alarm_state.return_value = "OK"

        result = detection_service.process_recovery(recovery_event)

        assert result is True

    def test_recovery_reports_alarm_recovered(self, detection_service, recovery_event, mock_correlation_repo, mock_incident_reporter, mock_log_analysis_service, mock_observability_repo, detected_record):
        mock_correlation_repo.get.return_value = detected_record
        mock_log_analysis_service.collect_recent.return_value = []
        mock_observability_repo.get_alarm_state.return_value = "OK"

        detection_service.process_recovery(recovery_event)

        mock_incident_reporter.report_alarm_recovered.assert_called_once()
        call_kwargs = mock_incident_reporter.report_alarm_recovered.call_args[1]
        assert call_kwargs["alarm_state"] == "OK"
        assert call_kwargs["log_count"] == 0

    def test_recovery_attaches_logs_via_reporter(self, detection_service, recovery_event, mock_correlation_repo, mock_incident_reporter, mock_log_analysis_service, mock_observability_repo, detected_record):
        mock_correlation_repo.get.return_value = detected_record
        mock_log_analysis_service.collect_recent.return_value = [
            {"message": "INFO: Recovery log entry", "timestamp": 1711800000000, "log_stream": "s1"}
        ]
        mock_observability_repo.get_alarm_state.return_value = "OK"

        detection_service.process_recovery(recovery_event)

        mock_incident_reporter.attach_log_file.assert_called_once()
        call_args = mock_incident_reporter.attach_log_file.call_args[0]
        assert call_args[0] == "INC-142"
        assert "recovery-logs" in call_args[1]

    def test_recovery_resolves_ticket_via_reporter(self, detection_service, recovery_event, mock_correlation_repo, mock_incident_reporter, mock_log_analysis_service, mock_observability_repo, detected_record):
        mock_correlation_repo.get.return_value = detected_record
        mock_log_analysis_service.collect_recent.return_value = []
        mock_observability_repo.get_alarm_state.return_value = "OK"

        detection_service.process_recovery(recovery_event)

        mock_incident_reporter.resolve_ticket.assert_called_once_with("INC-142")

    def test_recovery_deletes_dynamo_record(self, detection_service, recovery_event, mock_correlation_repo, mock_log_analysis_service, mock_observability_repo, detected_record):
        mock_correlation_repo.get.return_value = detected_record
        mock_log_analysis_service.collect_recent.return_value = []
        mock_observability_repo.get_alarm_state.return_value = "OK"

        detection_service.process_recovery(recovery_event)

        mock_correlation_repo.delete.assert_called_once_with("calculator-error-rate-prod")

    def test_recovery_collects_recent_logs(self, detection_service, recovery_event, mock_correlation_repo, mock_log_analysis_service, mock_observability_repo, detected_record):
        mock_correlation_repo.get.return_value = detected_record
        mock_log_analysis_service.collect_recent.return_value = []
        mock_observability_repo.get_alarm_state.return_value = "OK"

        detection_service.process_recovery(recovery_event)

        mock_log_analysis_service.collect_recent.assert_called_once()
        # Uses alarm_event.log_group (from trigger dimensions FunctionName)
        assert "/aws/lambda/calculator-api-prod" in str(mock_log_analysis_service.collect_recent.call_args)


# ------------------------------------------------------------------ #
# Recovery — No Matching Incident
# ------------------------------------------------------------------ #

class TestRecoveryNoMatch:
    """No DynamoDB record for recovery — skip."""

    def test_no_match_returns_false(self, detection_service, recovery_event, mock_correlation_repo):
        mock_correlation_repo.get.return_value = None

        result = detection_service.process_recovery(recovery_event)
        assert result is False

    def test_no_match_no_jira_calls(self, detection_service, recovery_event, mock_correlation_repo, mock_incident_reporter):
        mock_correlation_repo.get.return_value = None

        detection_service.process_recovery(recovery_event)

        mock_incident_reporter.report_alarm_recovered.assert_not_called()
        mock_incident_reporter.resolve_ticket.assert_not_called()
