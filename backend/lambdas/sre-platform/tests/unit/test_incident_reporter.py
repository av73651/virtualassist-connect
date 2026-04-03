"""Tests for IncidentReporter — all Jira ticket interactions."""

import pytest
from unittest.mock import Mock

from src.services.incident_reporter import IncidentReporter


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

@pytest.fixture
def reporter(mock_ticketing_repo, incident_config):
    return IncidentReporter(mock_ticketing_repo, incident_config)


# ------------------------------------------------------------------ #
# Triage phase reports
# ------------------------------------------------------------------ #

class TestTriageReports:

    def test_report_triage_started(self, reporter, mock_ticketing_repo):
        reporter.report_triage_started("INC-142", "calculator-error-rate-prod")

        mock_ticketing_repo.add_jira_comment.assert_called_once()
        args = mock_ticketing_repo.add_jira_comment.call_args[0]
        assert args[0] == "INC-142"
        assert "Triage started" in args[1]
        assert "calculator-error-rate-prod" in args[1]

    def test_report_analysis_results(self, reporter, mock_ticketing_repo):
        reporter.report_analysis_results(
            "INC-142", "bad-deployment", "high",
            "ImportError(6)", {"affected_users": "~12 estimated", "error_rate": "6%", "duration": "15min"},
        )

        args = mock_ticketing_repo.add_jira_comment.call_args[0]
        assert "bad-deployment" in args[1]
        assert "high" in args[1]

    def test_report_storm_detected(self, reporter, mock_ticketing_repo):
        reporter.report_storm_detected("INC-142")

        args = mock_ticketing_repo.add_jira_comment.call_args[0]
        assert "storm" in args[1].lower()

    def test_report_remediation_unavailable(self, reporter, mock_ticketing_repo):
        reporter.report_remediation_unavailable("INC-142", "unknown")

        args = mock_ticketing_repo.add_jira_comment.call_args[0]
        assert "No remediation" in args[1]
        assert "unknown" in args[1]

    def test_report_remediation_failed(self, reporter, mock_ticketing_repo):
        reporter.report_remediation_failed("INC-142", "bad-deployment")

        args = mock_ticketing_repo.add_jira_comment.call_args[0]
        assert "failed" in args[1].lower()
        assert "bad-deployment" in args[1]

    def test_report_verification_failed(self, reporter, mock_ticketing_repo):
        verification = {"alarm_ok": False, "health_ok": True, "error_rate_ok": True}
        reporter.report_verification_failed("INC-142", verification)

        args = mock_ticketing_repo.add_jira_comment.call_args[0]
        assert "alarm_ok=False" in args[1]
        assert "health_ok=True" in args[1]

    def test_report_auto_resolved(self, reporter, mock_ticketing_repo):
        reporter.report_auto_resolved("INC-142")

        args = mock_ticketing_repo.add_jira_comment.call_args[0]
        assert "verification checks passed" in args[1].lower()


# ------------------------------------------------------------------ #
# Recovery phase
# ------------------------------------------------------------------ #

class TestRecoveryReports:

    def test_report_recovery_status_with_detail(self, reporter, mock_ticketing_repo):
        reporter.report_recovery_status("INC-142", "triggered", "Recovery workflow triggered: replay")

        mock_ticketing_repo.add_jira_comment.assert_called_once()
        args = mock_ticketing_repo.add_jira_comment.call_args[0]
        assert "Recovery workflow triggered" in args[1]

    def test_report_recovery_status_no_detail_skips_comment(self, reporter, mock_ticketing_repo):
        reporter.report_recovery_status("INC-142", "not-required", "")

        mock_ticketing_repo.add_jira_comment.assert_not_called()


# ------------------------------------------------------------------ #
# Resolution
# ------------------------------------------------------------------ #

# ------------------------------------------------------------------ #
# Detection phase reports
# ------------------------------------------------------------------ #

class TestDetectionReports:

    def test_report_duplicate_alarm(self, reporter, mock_ticketing_repo):
        reporter.report_duplicate_alarm("INC-142", "calculator-error-rate-prod")

        args = mock_ticketing_repo.add_jira_comment.call_args[0]
        assert args[0] == "INC-142"
        assert "Duplicate alarm" in args[1]
        assert "calculator-error-rate-prod" in args[1]

    def test_report_grace_recurrence(self, reporter, mock_ticketing_repo):
        reporter.report_grace_recurrence("INC-142")

        args = mock_ticketing_repo.add_jira_comment.call_args[0]
        assert "recurred" in args[1].lower()

    def test_report_alarm_recovered(self, reporter, mock_ticketing_repo):
        reporter.report_alarm_recovered(
            "INC-142", alarm_state="OK",
            recovery_timestamp="2026-03-30T12:30:00+00:00", log_count=5,
        )

        args = mock_ticketing_repo.add_jira_comment.call_args[0]
        assert args[0] == "INC-142"
        assert "recovered" in args[1].lower()
        assert "OK" in args[1]
        assert "5" in args[1]

    def test_attach_log_file(self, reporter, mock_ticketing_repo):
        reporter.attach_log_file("INC-142", "recovery-logs-calc.txt", "log content here")

        mock_ticketing_repo.attach_jira_file.assert_called_once_with(
            "INC-142", "recovery-logs-calc.txt", "log content here"
        )


# ------------------------------------------------------------------ #
# Resolution
# ------------------------------------------------------------------ #

class TestResolveTicket:

    def test_resolve_ticket_transitions_to_done(self, reporter, mock_ticketing_repo):
        reporter.resolve_ticket("INC-142")

        mock_ticketing_repo.transition_jira_ticket.assert_called_once_with("INC-142", "Done")
