"""Tests for EscalationService — Jira enrichment, SNS notifications, Bedrock AI analysis."""

import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch
from freezegun import freeze_time

from src.models.enums import CorrelationStatus
from src.models.correlation_record import CorrelationRecord
from src.services.escalation_service import EscalationService


# ------------------------------------------------------------------ #
# ADF text extraction helper
# ------------------------------------------------------------------ #

def _adf_to_text(adf_blocks: list[dict]) -> str:
    """Recursively extract all text from ADF content blocks."""
    texts = []
    for block in adf_blocks:
        _extract_texts(block, texts)
    return "".join(texts)


def _extract_texts(node: dict, texts: list):
    if node.get("type") == "text":
        texts.append(node.get("text", ""))
    for child in node.get("content", []):
        _extract_texts(child, texts)


def _find_adf_links(adf_blocks: list[dict]) -> list[dict]:
    """Find all link nodes in ADF content."""
    links = []
    for block in adf_blocks:
        _extract_links(block, links)
    return links


def _extract_links(node: dict, links: list):
    if node.get("type") == "text":
        for mark in node.get("marks", []):
            if mark.get("type") == "link":
                links.append({"text": node["text"], "href": mark["attrs"]["href"]})
    for child in node.get("content", []):
        _extract_links(child, links)


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

@pytest.fixture
def escalation_service(mock_correlation_repo, mock_log_analysis_service, mock_ticketing_repo, mock_notification_repo):
    return EscalationService(
        correlation_repo=mock_correlation_repo,
        log_analysis_service=mock_log_analysis_service,
        ticketing_repo=mock_ticketing_repo,
        notification_repo=mock_notification_repo,
        notification_topic_arn="arn:aws:sns:us-west-2:320644769527:incident-engineer-notifications-dev",
    )


@pytest.fixture
def escalation_service_no_sns(mock_correlation_repo, mock_log_analysis_service, mock_ticketing_repo, mock_notification_repo):
    """Escalation service with no SNS topic configured."""
    return EscalationService(
        correlation_repo=mock_correlation_repo,
        log_analysis_service=mock_log_analysis_service,
        ticketing_repo=mock_ticketing_repo,
        notification_repo=mock_notification_repo,
        notification_topic_arn="",
    )


@pytest.fixture
def mock_ai_service():
    """Mock AIAnalysisService for AI log analysis."""
    service = Mock()
    service.analyze_for_escalation.return_value = {
        "text": (
            "Root cause analysis: The ImportError indicates a missing module 'missing_module' "
            "which suggests a bad deployment. The Lambda package is missing a required dependency. "
            "Recommended action: Roll back to the previous Lambda version immediately."
        ),
        "references": [
            {"source": "s3://kb-bucket/incident-management-lambda.md", "content": "Lambda rollback procedure"},
        ],
    }
    return service


@pytest.fixture
def escalation_service_with_ai(
    mock_correlation_repo, mock_log_analysis_service, mock_ticketing_repo, mock_notification_repo,
    mock_ai_service,
):
    """Escalation service with AI analysis enabled."""
    return EscalationService(
        correlation_repo=mock_correlation_repo,
        log_analysis_service=mock_log_analysis_service,
        ticketing_repo=mock_ticketing_repo,
        notification_repo=mock_notification_repo,
        notification_topic_arn="arn:aws:sns:us-west-2:320644769527:incident-engineer-notifications-dev",
        ai_service=mock_ai_service,
    )


@pytest.fixture
def detected_record_for_escalation(fixed_now):
    return CorrelationRecord(
        incident_key="calculator-error-rate-prod",
        jira_ticket_id="INC-142",
        severity="SEV-1",
        status=CorrelationStatus.TRIAGING,
        created_at=fixed_now,
        ttl=int((fixed_now + timedelta(hours=24)).timestamp()),
    )


@pytest.fixture
def setup_escalation(mock_correlation_repo, mock_log_analysis_service, detected_record_for_escalation):
    mock_correlation_repo.get.return_value = detected_record_for_escalation
    mock_log_analysis_service.collect_diagnostics.return_value = [
        {"@message": "ImportError: No module named 'missing_module'", "timestamp": "2026-03-30T12:00:00Z"},
        {"@message": "ImportError: No module named 'missing_module'", "timestamp": "2026-03-30T12:00:01Z"},
        {"@message": "ImportError: No module named 'missing_module'", "timestamp": "2026-03-30T12:00:02Z"},
    ]


_ESCALATION_KWARGS = {
    "incident_key": "calculator-error-rate-prod",
    "jira_ticket_id": "INC-142",
    "service": "calculator",
    "stage": "prod",
    "severity": "SEV-1",
    "reason": "verification-failed",
    "function_name": "calculator-api-prod",
    "root_cause": "bad-deployment",
}


# ------------------------------------------------------------------ #
# SEV-1 Full Enrichment + Notification
# ------------------------------------------------------------------ #

class TestSev1FullEscalation:
    """SEV-1 escalation with full enrichment and SNS notification."""

    @freeze_time("2026-03-30T12:00:00Z")
    def test_returns_escalated(self, escalation_service, setup_escalation):
        result = escalation_service.escalate(**_ESCALATION_KWARGS)
        assert result == "escalated"

    @freeze_time("2026-03-30T12:00:00Z")
    def test_updates_dynamo_to_escalated(
        self, escalation_service, setup_escalation, mock_correlation_repo
    ):
        escalation_service.escalate(**_ESCALATION_KWARGS)

        update_call = mock_correlation_repo.update.call_args[0][0]
        assert update_call.status == CorrelationStatus.ESCALATED
        assert update_call.incident_key == "calculator-error-rate-prod"

    @freeze_time("2026-03-30T12:00:00Z")
    def test_uses_adf_formatted_comment(
        self, escalation_service, setup_escalation, mock_ticketing_repo
    ):
        escalation_service.escalate(**_ESCALATION_KWARGS)

        mock_ticketing_repo.add_jira_comment_adf.assert_called_once()
        adf_content = mock_ticketing_repo.add_jira_comment_adf.call_args[0][1]
        assert isinstance(adf_content, list)
        assert any(b.get("type") == "heading" for b in adf_content)

    @freeze_time("2026-03-30T12:00:00Z")
    def test_adds_enriched_jira_comment(
        self, escalation_service, setup_escalation, mock_ticketing_repo
    ):
        escalation_service.escalate(**_ESCALATION_KWARGS)

        adf_content = mock_ticketing_repo.add_jira_comment_adf.call_args[0][1]
        text = _adf_to_text(adf_content)
        assert "Escalation" in text
        assert "verification-failed" in text
        assert "SEV-1" in text
        assert "bad-deployment" in text

    @freeze_time("2026-03-30T12:00:00Z")
    def test_enriched_comment_includes_diagnostics(
        self, escalation_service, setup_escalation, mock_ticketing_repo
    ):
        escalation_service.escalate(**_ESCALATION_KWARGS)

        adf_content = mock_ticketing_repo.add_jira_comment_adf.call_args[0][1]
        text = _adf_to_text(adf_content)
        assert "Diagnostics" in text
        assert "calculator-api-prod" in text
        assert "Error Count: 3" in text

    @freeze_time("2026-03-30T12:00:00Z")
    def test_enriched_comment_includes_clickable_links(
        self, escalation_service, setup_escalation, mock_ticketing_repo
    ):
        escalation_service.escalate(**_ESCALATION_KWARGS)

        adf_content = mock_ticketing_repo.add_jira_comment_adf.call_args[0][1]
        text = _adf_to_text(adf_content)
        assert "Useful Links" in text

        links = _find_adf_links(adf_content)
        link_texts = [l["text"] for l in links]
        assert "CloudWatch Logs" in link_texts
        assert "Lambda Function" in link_texts

        cw_link = next(l for l in links if l["text"] == "CloudWatch Logs")
        assert "console.aws.amazon.com" in cw_link["href"]

    @freeze_time("2026-03-30T12:00:00Z")
    def test_enriched_comment_includes_commands(
        self, escalation_service, setup_escalation, mock_ticketing_repo
    ):
        escalation_service.escalate(**_ESCALATION_KWARGS)

        adf_content = mock_ticketing_repo.add_jira_comment_adf.call_args[0][1]
        text = _adf_to_text(adf_content)
        assert "CLI Commands" in text
        assert "aws logs tail" in text
        assert "aws cloudwatch describe-alarms" in text

    @freeze_time("2026-03-30T12:00:00Z")
    def test_attaches_error_logs(
        self, escalation_service, setup_escalation, mock_ticketing_repo
    ):
        escalation_service.escalate(**_ESCALATION_KWARGS)

        mock_ticketing_repo.attach_jira_file.assert_called_once()
        filename = mock_ticketing_repo.attach_jira_file.call_args[0][1]
        assert "error-logs-calculator-error-rate-prod" in filename

    @freeze_time("2026-03-30T12:00:00Z")
    def test_notifies_engineer_sev1(
        self, escalation_service, setup_escalation, mock_notification_repo
    ):
        escalation_service.escalate(**_ESCALATION_KWARGS)

        mock_notification_repo.notify_engineer.assert_called_once()
        topic_arn = mock_notification_repo.notify_engineer.call_args[0][0]
        message = mock_notification_repo.notify_engineer.call_args[0][1]
        severity = mock_notification_repo.notify_engineer.call_args[0][2]
        assert "incident-engineer-notifications" in topic_arn
        assert "calculator-error-rate-prod" in message
        assert "INC-142" in message
        assert severity == "SEV-1"

    @freeze_time("2026-03-30T12:00:00Z")
    def test_notifies_engineer_sev2(
        self, escalation_service, setup_escalation, mock_notification_repo
    ):
        escalation_service.escalate(**{**_ESCALATION_KWARGS, "severity": "SEV-2"})
        mock_notification_repo.notify_engineer.assert_called_once()

    @freeze_time("2026-03-30T12:00:00Z")
    def test_enriched_comment_includes_top_errors(
        self, escalation_service, setup_escalation, mock_ticketing_repo
    ):
        escalation_service.escalate(**_ESCALATION_KWARGS)

        adf_content = mock_ticketing_repo.add_jira_comment_adf.call_args[0][1]
        text = _adf_to_text(adf_content)
        assert "Top Errors" in text
        assert "3x" in text

    @freeze_time("2026-03-30T12:00:00Z")
    def test_code_blocks_present(
        self, escalation_service, setup_escalation, mock_ticketing_repo
    ):
        """ADF comment includes codeBlock nodes for commands and error patterns."""
        escalation_service.escalate(**_ESCALATION_KWARGS)

        adf_content = mock_ticketing_repo.add_jira_comment_adf.call_args[0][1]
        code_blocks = [b for b in adf_content if b.get("type") == "codeBlock"]
        assert len(code_blocks) >= 2  # top errors + CLI commands


# ------------------------------------------------------------------ #
# SEV-3 No Notification
# ------------------------------------------------------------------ #

class TestSev3NoNotification:
    """SEV-3 escalation enriches Jira but does NOT send SNS notification."""

    @freeze_time("2026-03-30T12:00:00Z")
    def test_sev3_returns_escalated(self, escalation_service, setup_escalation):
        result = escalation_service.escalate(**{**_ESCALATION_KWARGS, "severity": "SEV-3"})
        assert result == "escalated"

    @freeze_time("2026-03-30T12:00:00Z")
    def test_sev3_enriches_jira(
        self, escalation_service, setup_escalation, mock_ticketing_repo
    ):
        escalation_service.escalate(**{**_ESCALATION_KWARGS, "severity": "SEV-3"})
        mock_ticketing_repo.add_jira_comment_adf.assert_called_once()

    @freeze_time("2026-03-30T12:00:00Z")
    def test_sev3_no_sns_notification(
        self, escalation_service, setup_escalation, mock_notification_repo
    ):
        escalation_service.escalate(**{**_ESCALATION_KWARGS, "severity": "SEV-3"})
        mock_notification_repo.notify_engineer.assert_not_called()

    @freeze_time("2026-03-30T12:00:00Z")
    def test_no_sns_topic_configured(
        self, escalation_service_no_sns, setup_escalation, mock_notification_repo
    ):
        """Even SEV-1 should not notify if topic ARN is empty."""
        escalation_service_no_sns.escalate(**_ESCALATION_KWARGS)
        mock_notification_repo.notify_engineer.assert_not_called()


# ------------------------------------------------------------------ #
# Reason-Specific Messaging
# ------------------------------------------------------------------ #

class TestReasonSpecificMessaging:
    """Each escalation reason produces correct context in Jira comment."""

    _REASONS = [
        ("verification-failed", "post-remediation verification failed"),
        ("no-remediation-available", "No automated remediation exists"),
        ("remediation-failed", "remediation was attempted but the action itself failed"),
        ("incident-storm", "Multiple incidents detected"),
        ("grace-period-recurrence", "alarm fired again within the grace period"),
        ("triage-timeout", "triage exceeded the allowed time"),
    ]

    @freeze_time("2026-03-30T12:00:00Z")
    @pytest.mark.parametrize("reason,expected_text", _REASONS)
    def test_reason_context_in_jira_comment(
        self, reason, expected_text, escalation_service, setup_escalation, mock_ticketing_repo
    ):
        escalation_service.escalate(**{**_ESCALATION_KWARGS, "reason": reason})

        adf_content = mock_ticketing_repo.add_jira_comment_adf.call_args[0][1]
        text = _adf_to_text(adf_content)
        assert expected_text in text

    @freeze_time("2026-03-30T12:00:00Z")
    def test_unknown_reason_includes_raw_reason(
        self, escalation_service, setup_escalation, mock_ticketing_repo
    ):
        escalation_service.escalate(**{**_ESCALATION_KWARGS, "reason": "custom-reason"})

        adf_content = mock_ticketing_repo.add_jira_comment_adf.call_args[0][1]
        text = _adf_to_text(adf_content)
        assert "custom-reason" in text

    @freeze_time("2026-03-30T12:00:00Z")
    def test_verification_details_included(
        self, escalation_service, setup_escalation, mock_ticketing_repo
    ):
        escalation_service.escalate(
            **{
                **_ESCALATION_KWARGS,
                "reason": "verification-failed",
                "verification": {"alarm_ok": False, "health_ok": True, "error_rate_ok": True},
            }
        )

        adf_content = mock_ticketing_repo.add_jira_comment_adf.call_args[0][1]
        text = _adf_to_text(adf_content)
        assert "alarm_ok=False" in text
        assert "health_ok=True" in text


# ------------------------------------------------------------------ #
# Bedrock AI Log Analysis
# ------------------------------------------------------------------ #

class TestAIAnalysis:
    """AI-powered log analysis in escalation comments via AIAnalysisService."""

    @freeze_time("2026-03-30T12:00:00Z")
    def test_ai_analysis_included_in_comment(
        self, escalation_service_with_ai, setup_escalation, mock_ticketing_repo
    ):
        escalation_service_with_ai.escalate(**_ESCALATION_KWARGS)

        adf_content = mock_ticketing_repo.add_jira_comment_adf.call_args[0][1]
        text = _adf_to_text(adf_content)
        assert "AI Analysis" in text
        assert "ImportError" in text
        assert "Roll back" in text

    @freeze_time("2026-03-30T12:00:00Z")
    def test_ai_service_called_with_context(
        self, escalation_service_with_ai, setup_escalation, mock_ai_service
    ):
        escalation_service_with_ai.escalate(**_ESCALATION_KWARGS)

        mock_ai_service.analyze_for_escalation.assert_called_once()
        call_kwargs = mock_ai_service.analyze_for_escalation.call_args[1]
        assert call_kwargs["function_name"] == "calculator-api-prod"
        assert call_kwargs["root_cause"] == "bad-deployment"
        assert call_kwargs["reason"] == "verification-failed"

    @freeze_time("2026-03-30T12:00:00Z")
    def test_no_ai_section_without_ai_service(
        self, escalation_service, setup_escalation, mock_ticketing_repo
    ):
        """Without AI service configured, no AI Analysis section appears."""
        escalation_service.escalate(**_ESCALATION_KWARGS)

        adf_content = mock_ticketing_repo.add_jira_comment_adf.call_args[0][1]
        text = _adf_to_text(adf_content)
        assert "AI Analysis" not in text

    @freeze_time("2026-03-30T12:00:00Z")
    def test_ai_failure_graceful_fallback(
        self, escalation_service_with_ai, setup_escalation,
        mock_ai_service, mock_ticketing_repo
    ):
        """AI failure -> no AI section, rest of comment still works."""
        mock_ai_service.analyze_for_escalation.return_value = None

        escalation_service_with_ai.escalate(**_ESCALATION_KWARGS)

        adf_content = mock_ticketing_repo.add_jira_comment_adf.call_args[0][1]
        text = _adf_to_text(adf_content)
        assert "AI Analysis" not in text
        assert "Diagnostics" in text
        assert "Useful Links" in text

    @freeze_time("2026-03-30T12:00:00Z")
    def test_ai_exception_graceful_fallback(
        self, escalation_service_with_ai, setup_escalation,
        mock_ai_service, mock_ticketing_repo
    ):
        """AI exception -> no AI section, escalation still succeeds."""
        mock_ai_service.analyze_for_escalation.side_effect = RuntimeError("AI unavailable")

        result = escalation_service_with_ai.escalate(**_ESCALATION_KWARGS)

        assert result == "escalated"
        adf_content = mock_ticketing_repo.add_jira_comment_adf.call_args[0][1]
        text = _adf_to_text(adf_content)
        assert "AI Analysis" not in text


# ------------------------------------------------------------------ #
# Edge Cases
# ------------------------------------------------------------------ #

class TestEscalationEdgeCases:
    """Edge case handling."""

    @freeze_time("2026-03-30T12:00:00Z")
    def test_no_existing_correlation(
        self, escalation_service, mock_correlation_repo, mock_log_analysis_service
    ):
        """Escalation works even if DynamoDB record is missing."""
        mock_correlation_repo.get.return_value = None
        mock_log_analysis_service.collect_diagnostics.return_value = []

        result = escalation_service.escalate(**_ESCALATION_KWARGS)
        assert result == "escalated"
        mock_correlation_repo.update.assert_not_called()

    @freeze_time("2026-03-30T12:00:00Z")
    def test_no_error_logs(
        self, escalation_service, setup_escalation, mock_log_analysis_service, mock_ticketing_repo
    ):
        """No error logs -> no file attachment, but Jira still enriched."""
        mock_log_analysis_service.collect_diagnostics.return_value = []

        escalation_service.escalate(**_ESCALATION_KWARGS)
        mock_ticketing_repo.add_jira_comment_adf.assert_called_once()
        mock_ticketing_repo.attach_jira_file.assert_not_called()

    @freeze_time("2026-03-30T12:00:00Z")
    def test_default_function_name(
        self, escalation_service, setup_escalation, mock_ticketing_repo
    ):
        """When function_name not provided, derives from service + stage."""
        escalation_service.escalate(
            **{**_ESCALATION_KWARGS, "function_name": ""}
        )

        adf_content = mock_ticketing_repo.add_jira_comment_adf.call_args[0][1]
        text = _adf_to_text(adf_content)
        assert "calculator-api-prod" in text
