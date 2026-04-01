"""Tests for ObservabilityRepository — CloudWatch Logs + Alarms.

Tests alarm state checks, alarm history, collect_errors (Logs Insights async),
and collect_recent (filter_log_events)."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, call


from src.repositories.observability_repository import ObservabilityRepository


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

@pytest.fixture
def mock_cloudwatch():
    return Mock()


@pytest.fixture
def mock_logs():
    return Mock()


@pytest.fixture
def obs_repo(mock_logs, mock_cloudwatch):
    return ObservabilityRepository(
        logs_client=mock_logs,
        cloudwatch_client=mock_cloudwatch,
    )


# ------------------------------------------------------------------ #
# get_alarm_state
# ------------------------------------------------------------------ #

class TestGetAlarmState:
    """Alarm state retrieval for cool-off checks."""

    def test_returns_alarm_state(self, obs_repo, mock_cloudwatch):
        mock_cloudwatch.describe_alarms.return_value = {
            "MetricAlarms": [{"StateValue": "ALARM"}]
        }

        result = obs_repo.get_alarm_state("calculator-high-error-rate-prod")

        assert result == "ALARM"
        mock_cloudwatch.describe_alarms.assert_called_once_with(
            AlarmNames=["calculator-high-error-rate-prod"]
        )

    def test_returns_ok_state(self, obs_repo, mock_cloudwatch):
        mock_cloudwatch.describe_alarms.return_value = {
            "MetricAlarms": [{"StateValue": "OK"}]
        }

        result = obs_repo.get_alarm_state("calculator-high-error-rate-prod")
        assert result == "OK"

    def test_returns_insufficient_data_when_no_alarms(self, obs_repo, mock_cloudwatch):
        mock_cloudwatch.describe_alarms.return_value = {"MetricAlarms": []}

        result = obs_repo.get_alarm_state("nonexistent-alarm")
        assert result == "INSUFFICIENT_DATA"

    def test_returns_insufficient_data_when_missing_state(self, obs_repo, mock_cloudwatch):
        mock_cloudwatch.describe_alarms.return_value = {
            "MetricAlarms": [{}]
        }

        result = obs_repo.get_alarm_state("alarm-no-state")
        assert result == "INSUFFICIENT_DATA"


# ------------------------------------------------------------------ #
# get_state_change_time
# ------------------------------------------------------------------ #

class TestGetStateChangeTime:
    """Alarm history for state change timestamps."""

    def test_returns_timestamp(self, obs_repo, mock_cloudwatch):
        ts = datetime(2026, 3, 30, 12, 0, 0, tzinfo=timezone.utc)
        mock_cloudwatch.describe_alarm_history.return_value = {
            "AlarmHistoryItems": [{"Timestamp": ts}]
        }

        result = obs_repo.get_state_change_time("calculator-high-error-rate-prod")

        assert result == ts
        mock_cloudwatch.describe_alarm_history.assert_called_once_with(
            AlarmName="calculator-high-error-rate-prod",
            HistoryItemType="StateUpdate",
            MaxRecords=1,
        )

    def test_returns_none_when_no_history(self, obs_repo, mock_cloudwatch):
        mock_cloudwatch.describe_alarm_history.return_value = {
            "AlarmHistoryItems": []
        }

        result = obs_repo.get_state_change_time("new-alarm")
        assert result is None


# ------------------------------------------------------------------ #
# collect_errors (Logs Insights async)
# ------------------------------------------------------------------ #

class TestCollectErrors:
    """Logs Insights async query pattern: start_query -> poll -> parse."""

    def test_successful_query(self, obs_repo, mock_logs):
        """Full async flow: start_query -> get_query_results -> parse."""
        mock_logs.start_query.return_value = {"queryId": "query-123"}
        mock_logs.get_query_results.return_value = {
            "status": "Complete",
            "results": [
                [
                    {"field": "@timestamp", "value": "2026-03-30T12:00:00Z"},
                    {"field": "@message", "value": '{"error_type":"DivisionByZeroError","operation":"divide","user_id":"u-123"}'},
                    {"field": "@logStream", "value": "stream-1"},
                    {"field": "@requestId", "value": "req-aaa"},
                    {"field": "error_type", "value": "DivisionByZeroError"},
                    {"field": "operation", "value": "divide"},
                    {"field": "user_id", "value": "u-123"},
                ],
                [
                    {"field": "@timestamp", "value": "2026-03-30T12:01:00Z"},
                    {"field": "@message", "value": "ERROR: NullPointerException"},
                    {"field": "@logStream", "value": "stream-2"},
                    {"field": "@requestId", "value": "req-bbb"},
                    {"field": "error_type", "value": ""},
                    {"field": "operation", "value": ""},
                    {"field": "user_id", "value": ""},
                ],
            ],
        }

        start = datetime(2026, 3, 30, 11, 45, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 30, 12, 0, 0, tzinfo=timezone.utc)

        results = obs_repo.collect_errors("/aws/lambda/calculator-prod", start, end)

        assert len(results) == 2
        assert results[0]["@requestId"] == "req-aaa"
        assert results[0]["error_type"] == "DivisionByZeroError"
        assert results[0]["operation"] == "divide"
        assert results[0]["user_id"] == "u-123"
        assert results[1]["@requestId"] == "req-bbb"

        mock_logs.start_query.assert_called_once()
        call_kwargs = mock_logs.start_query.call_args[1]
        assert call_kwargs["logGroupName"] == "/aws/lambda/calculator-prod"
        assert "ERROR" in call_kwargs["queryString"]
        assert "@requestId" in call_kwargs["queryString"]
        assert "error_type" in call_kwargs["queryString"]
        assert "operation" in call_kwargs["queryString"]
        assert "user_id" in call_kwargs["queryString"]

    @patch("src.repositories.observability_repository.time.sleep")
    def test_polls_until_complete(self, mock_sleep, obs_repo, mock_logs):
        """Polls get_query_results with backoff until Complete."""
        mock_logs.start_query.return_value = {"queryId": "query-456"}
        mock_logs.get_query_results.side_effect = [
            {"status": "Running", "results": []},
            {"status": "Running", "results": []},
            {"status": "Complete", "results": [
                [{"field": "@message", "value": "ERROR: timeout"}]
            ]},
        ]

        start = datetime(2026, 3, 30, 11, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 30, 12, 0, 0, tzinfo=timezone.utc)

        results = obs_repo.collect_errors("/aws/lambda/test", start, end)

        assert len(results) == 1
        assert mock_logs.get_query_results.call_count == 3
        assert mock_sleep.call_count == 2

    def test_returns_empty_on_start_query_failure(self, obs_repo, mock_logs):
        """Returns [] when start_query fails."""
        mock_logs.start_query.side_effect = Exception("Access denied")

        start = datetime(2026, 3, 30, 11, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 30, 12, 0, 0, tzinfo=timezone.utc)

        results = obs_repo.collect_errors("/aws/lambda/test", start, end)
        assert results == []

    def test_returns_empty_on_query_failed_status(self, obs_repo, mock_logs):
        """Returns [] when query status is Failed."""
        mock_logs.start_query.return_value = {"queryId": "query-789"}
        mock_logs.get_query_results.return_value = {
            "status": "Failed",
            "results": [],
        }

        start = datetime(2026, 3, 30, 11, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 30, 12, 0, 0, tzinfo=timezone.utc)

        results = obs_repo.collect_errors("/aws/lambda/test", start, end)
        assert results == []

    def test_respects_max_events_in_query(self, obs_repo, mock_logs):
        """max_events parameter is included in Logs Insights query."""
        mock_logs.start_query.return_value = {"queryId": "q1"}
        mock_logs.get_query_results.return_value = {
            "status": "Complete",
            "results": [],
        }

        start = datetime(2026, 3, 30, 11, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 30, 12, 0, 0, tzinfo=timezone.utc)

        obs_repo.collect_errors("/aws/lambda/test", start, end, max_events=100)

        query = mock_logs.start_query.call_args[1]["queryString"]
        assert "limit 100" in query


# ------------------------------------------------------------------ #
# collect_error_payloads
# ------------------------------------------------------------------ #

class TestCollectErrorPayloads:
    """Retrieves input event/payload entries for failed request IDs."""

    def test_returns_payloads_for_request_ids(self, obs_repo, mock_logs):
        mock_logs.start_query.return_value = {"queryId": "qp-1"}
        mock_logs.get_query_results.return_value = {
            "status": "Complete",
            "results": [
                [
                    {"field": "@timestamp", "value": "2026-03-30T11:59:58Z"},
                    {"field": "@message", "value": '{"event_payload": {"path": "/divide", "body": {"a": 1, "b": 0}}}'},
                    {"field": "@requestId", "value": "req-aaa"},
                ],
            ],
        }

        start = datetime(2026, 3, 30, 11, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 30, 12, 0, 0, tzinfo=timezone.utc)

        results = obs_repo.collect_error_payloads(
            "/aws/lambda/calculator-prod", ["req-aaa", "req-bbb"], start, end
        )

        assert len(results) == 1
        assert results[0]["@requestId"] == "req-aaa"
        assert "event_payload" in results[0]["@message"]

        call_kwargs = mock_logs.start_query.call_args[1]
        assert '@requestId = "req-aaa"' in call_kwargs["queryString"]
        assert '@requestId = "req-bbb"' in call_kwargs["queryString"]

    def test_returns_empty_when_no_request_ids(self, obs_repo, mock_logs):
        start = datetime(2026, 3, 30, 11, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 30, 12, 0, 0, tzinfo=timezone.utc)

        results = obs_repo.collect_error_payloads(
            "/aws/lambda/test", [], start, end
        )

        assert results == []
        mock_logs.start_query.assert_not_called()

    def test_limits_request_ids_to_max_payloads(self, obs_repo, mock_logs):
        mock_logs.start_query.return_value = {"queryId": "qp-2"}
        mock_logs.get_query_results.return_value = {
            "status": "Complete",
            "results": [],
        }

        start = datetime(2026, 3, 30, 11, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 30, 12, 0, 0, tzinfo=timezone.utc)

        # Pass 10 IDs but max_payloads=3
        ids = [f"req-{i}" for i in range(10)]
        obs_repo.collect_error_payloads(
            "/aws/lambda/test", ids, start, end, max_payloads=3
        )

        query = mock_logs.start_query.call_args[1]["queryString"]
        # Only first 3 IDs should be in query
        assert 'req-0' in query
        assert 'req-2' in query
        assert 'req-3' not in query

    def test_returns_empty_on_start_query_failure(self, obs_repo, mock_logs):
        mock_logs.start_query.side_effect = Exception("Access denied")

        start = datetime(2026, 3, 30, 11, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 30, 12, 0, 0, tzinfo=timezone.utc)

        results = obs_repo.collect_error_payloads(
            "/aws/lambda/test", ["req-1"], start, end
        )
        assert results == []


# ------------------------------------------------------------------ #
# collect_recent (filter_log_events)
# ------------------------------------------------------------------ #

class TestCollectRecent:
    """Synchronous filter_log_events for recent logs."""

    def test_returns_recent_logs(self, obs_repo, mock_logs):
        mock_logs.filter_log_events.return_value = {
            "events": [
                {
                    "message": "INFO: Health check OK",
                    "timestamp": 1711800000000,
                    "logStreamName": "stream-1",
                },
                {
                    "message": "INFO: Request processed",
                    "timestamp": 1711800001000,
                    "logStreamName": "stream-1",
                },
            ]
        }

        results = obs_repo.collect_recent("/aws/lambda/calculator-prod", minutes=5)

        assert len(results) == 2
        assert results[0]["message"] == "INFO: Health check OK"
        assert results[0]["log_stream"] == "stream-1"
        assert results[1]["timestamp"] == 1711800001000

    def test_returns_empty_on_failure(self, obs_repo, mock_logs):
        mock_logs.filter_log_events.side_effect = Exception("Log group not found")

        results = obs_repo.collect_recent("/aws/lambda/nonexistent")
        assert results == []

    def test_passes_correct_parameters(self, obs_repo, mock_logs):
        mock_logs.filter_log_events.return_value = {"events": []}

        obs_repo.collect_recent("/aws/lambda/test", minutes=10, max_events=50)

        call_kwargs = mock_logs.filter_log_events.call_args[1]
        assert call_kwargs["logGroupName"] == "/aws/lambda/test"
        assert call_kwargs["limit"] == 50

    def test_returns_empty_list_when_no_events(self, obs_repo, mock_logs):
        mock_logs.filter_log_events.return_value = {"events": []}

        results = obs_repo.collect_recent("/aws/lambda/test")
        assert results == []


# ------------------------------------------------------------------ #
# _parse_query_results
# ------------------------------------------------------------------ #

class TestParseQueryResults:
    """Logs Insights result parsing."""

    def test_parses_flat_dict(self):
        raw = [
            [
                {"field": "@timestamp", "value": "2026-03-30T12:00:00Z"},
                {"field": "@message", "value": "ERROR: something"},
            ]
        ]

        result = ObservabilityRepository._parse_query_results(raw)

        assert len(result) == 1
        assert result[0]["@timestamp"] == "2026-03-30T12:00:00Z"
        assert result[0]["@message"] == "ERROR: something"

    def test_handles_empty_results(self):
        assert ObservabilityRepository._parse_query_results([]) == []
