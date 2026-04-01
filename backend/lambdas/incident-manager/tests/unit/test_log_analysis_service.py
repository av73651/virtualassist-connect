"""Tests for LogAnalysisService — centralized log retrieval and analysis."""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from freezegun import freeze_time

from src.services.log_analysis_service import LogAnalysisService


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

@pytest.fixture
def log_analysis_service(mock_observability_repo, incident_config):
    return LogAnalysisService(mock_observability_repo, incident_config)


# ------------------------------------------------------------------ #
# analyze_errors
# ------------------------------------------------------------------ #

class TestAnalyzeErrors:
    """Tests for analyze_errors — error collection + pattern grouping."""

    @freeze_time("2026-03-30T12:00:00Z")
    def test_returns_grouped_patterns(self, log_analysis_service, mock_observability_repo):
        mock_observability_repo.collect_errors.return_value = [
            {"@message": "ImportError: No module named 'foo'"},
            {"@message": "ImportError: No module named 'foo'"},
            {"@message": "KeyError: 'bar'"},
        ]

        result = log_analysis_service.analyze_errors("/aws/lambda/calc-prod")

        assert result["error_count"] == 3
        assert result["unique_errors"] == 2
        assert result["error_patterns"]["ImportError: No module named 'foo'"] == 2
        assert result["error_patterns"]["KeyError: 'bar'"] == 1

    @freeze_time("2026-03-30T12:00:00Z")
    def test_empty_logs_returns_zero_counts(self, log_analysis_service, mock_observability_repo):
        mock_observability_repo.collect_errors.return_value = []

        result = log_analysis_service.analyze_errors("/aws/lambda/calc-prod")

        assert result["error_count"] == 0
        assert result["unique_errors"] == 0
        assert result["error_patterns"] == {}
        assert result["sample_payloads"] == []

    @freeze_time("2026-03-30T12:00:00Z")
    def test_limits_sample_payloads(self, log_analysis_service, mock_observability_repo, incident_config):
        mock_observability_repo.collect_errors.return_value = [
            {"@message": f"Error {i}"} for i in range(20)
        ]

        result = log_analysis_service.analyze_errors("/aws/lambda/calc-prod")

        assert len(result["sample_payloads"]) == incident_config.max_sample_payloads

    @freeze_time("2026-03-30T12:00:00Z")
    def test_calls_observability_with_correct_params(self, log_analysis_service, mock_observability_repo, incident_config):
        mock_observability_repo.collect_errors.return_value = []

        log_analysis_service.analyze_errors("/aws/lambda/calc-prod")

        call_kwargs = mock_observability_repo.collect_errors.call_args[1]
        assert call_kwargs["log_group"] == "/aws/lambda/calc-prod"
        assert call_kwargs["max_events"] == incident_config.max_log_events

    @freeze_time("2026-03-30T12:00:00Z")
    def test_handles_message_key_variants(self, log_analysis_service, mock_observability_repo):
        """Handles both '@message' and 'message' keys."""
        mock_observability_repo.collect_errors.return_value = [
            {"@message": "error via @message"},
            {"message": "error via message"},
        ]

        result = log_analysis_service.analyze_errors("/aws/lambda/calc-prod")

        assert result["error_count"] == 2
        assert "error via @message" in result["error_patterns"]
        assert "error via message" in result["error_patterns"]


# ------------------------------------------------------------------ #
# collect_diagnostics
# ------------------------------------------------------------------ #

class TestCollectDiagnostics:

    @freeze_time("2026-03-30T12:00:00Z")
    def test_returns_error_logs(self, log_analysis_service, mock_observability_repo):
        expected = [{"@message": "err1"}, {"@message": "err2"}]
        mock_observability_repo.collect_errors.return_value = expected

        result = log_analysis_service.collect_diagnostics("/aws/lambda/calc-prod")

        assert result == expected


# ------------------------------------------------------------------ #
# collect_recent
# ------------------------------------------------------------------ #

class TestCollectRecent:

    def test_delegates_to_observability(self, log_analysis_service, mock_observability_repo):
        expected = [{"message": "log1"}]
        mock_observability_repo.collect_recent.return_value = expected

        result = log_analysis_service.collect_recent("/aws/lambda/calc-prod")

        assert result == expected
        mock_observability_repo.collect_recent.assert_called_once()

    def test_uses_custom_minutes(self, log_analysis_service, mock_observability_repo):
        mock_observability_repo.collect_recent.return_value = []

        log_analysis_service.collect_recent("/aws/lambda/calc-prod", minutes=10)

        call_args = mock_observability_repo.collect_recent.call_args
        assert call_args[1]["minutes"] == 10


# ------------------------------------------------------------------ #
# check_health
# ------------------------------------------------------------------ #

class TestCheckHealth:

    def test_healthy_when_no_errors(self, log_analysis_service, mock_observability_repo):
        mock_observability_repo.collect_recent.return_value = [
            {"message": "INFO: all good"},
        ]

        health_ok, error_rate_ok = log_analysis_service.check_health("/aws/lambda/calc-prod")

        assert health_ok is True
        assert error_rate_ok is True

    def test_unhealthy_when_errors_present(self, log_analysis_service, mock_observability_repo):
        mock_observability_repo.collect_recent.return_value = [
            {"message": "ERROR: something broke"},
        ]

        health_ok, error_rate_ok = log_analysis_service.check_health("/aws/lambda/calc-prod")

        assert health_ok is False

    def test_error_rate_ok_when_below_threshold(self, log_analysis_service, mock_observability_repo):
        mock_observability_repo.collect_recent.return_value = [
            {"message": "ERROR: one error"},
            {"message": "INFO: fine"},
        ]

        health_ok, error_rate_ok = log_analysis_service.check_health("/aws/lambda/calc-prod")

        assert health_ok is False
        assert error_rate_ok is True  # 1 < threshold (5)

    def test_error_rate_not_ok_when_above_threshold(self, log_analysis_service, mock_observability_repo, incident_config):
        errors = [{"message": "ERROR: broke"} for _ in range(10)]
        mock_observability_repo.collect_recent.return_value = errors

        health_ok, error_rate_ok = log_analysis_service.check_health("/aws/lambda/calc-prod")

        assert health_ok is False
        assert error_rate_ok is False


# ------------------------------------------------------------------ #
# format_log_attachment (static)
# ------------------------------------------------------------------ #

class TestFormatLogAttachment:

    def test_formats_error_logs(self):
        logs = [
            {"timestamp": "2026-03-30T12:00:00Z", "@message": "ImportError: no module"},
            {"timestamp": "2026-03-30T12:00:01Z", "@message": "ImportError: no module"},
        ]
        result = LogAnalysisService.format_log_attachment(logs)

        assert "[2026-03-30T12:00:00Z] ImportError: no module" in result
        assert result.count("\n") == 1  # 2 lines, 1 newline

    def test_respects_limit(self):
        logs = [{"timestamp": f"t{i}", "message": f"err{i}"} for i in range(100)]
        result = LogAnalysisService.format_log_attachment(logs, limit=5)

        assert result.count("\n") == 4  # 5 lines

    def test_empty_logs(self):
        result = LogAnalysisService.format_log_attachment([])
        assert result == ""
