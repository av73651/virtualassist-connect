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
def mock_lambda():
    return Mock()


@pytest.fixture
def obs_repo(mock_logs, mock_cloudwatch, mock_lambda):
    return ObservabilityRepository(
        logs_client=mock_logs,
        cloudwatch_client=mock_cloudwatch,
        lambda_client=mock_lambda,
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


# ------------------------------------------------------------------ #
# get_alarm_metric_data (Phase 1 enhancement)
# ------------------------------------------------------------------ #

class TestGetAlarmMetricData:
    """Retrieves alarm configuration and recent metric datapoints."""

    def test_returns_alarm_config_and_datapoints(self, obs_repo, mock_cloudwatch):
        """Full success case: alarm found, datapoints retrieved."""
        mock_cloudwatch.describe_alarms.return_value = {
            "MetricAlarms": [{
                "MetricName": "Errors",
                "Namespace": "AWS/Lambda",
                "Threshold": 5.0,
                "ComparisonOperator": "GreaterThanThreshold",
                "EvaluationPeriods": 3,
                "DatapointsToAlarm": 2,
                "StateValue": "ALARM",
                "Dimensions": [{"Name": "FunctionName", "Value": "test-function"}],
                "Period": 60,
            }]
        }

        mock_cloudwatch.get_metric_statistics.return_value = {
            "Datapoints": [
                {"Timestamp": datetime(2026, 3, 30, 12, 0, 0, tzinfo=timezone.utc), "Average": 10.0},
                {"Timestamp": datetime(2026, 3, 30, 12, 1, 0, tzinfo=timezone.utc), "Sum": 15.0},
            ]
        }

        result = obs_repo.get_alarm_metric_data("test-alarm", lookback_minutes=15)

        assert result["alarm_config"]["metric_name"] == "Errors"
        assert result["alarm_config"]["namespace"] == "AWS/Lambda"
        assert result["alarm_config"]["threshold"] == 5.0
        assert result["alarm_config"]["comparison_operator"] == "GreaterThanThreshold"
        assert result["alarm_config"]["evaluation_periods"] == 3
        assert result["alarm_config"]["datapoints_to_alarm"] == 2
        assert result["current_state"] == "ALARM"
        assert len(result["datapoints"]) == 2
        assert result["datapoints"][0]["timestamp"] == "2026-03-30T12:00:00+00:00"
        assert result["datapoints"][0]["value"] == 10.0
        assert result["datapoints"][1]["value"] == 15.0

    def test_returns_not_found_when_alarm_missing(self, obs_repo, mock_cloudwatch):
        """Returns NOT_FOUND state when alarm doesn't exist."""
        mock_cloudwatch.describe_alarms.return_value = {"MetricAlarms": []}

        result = obs_repo.get_alarm_metric_data("nonexistent-alarm")

        assert result["alarm_config"] == {}
        assert result["datapoints"] == []
        assert result["current_state"] == "NOT_FOUND"

    def test_returns_error_on_exception(self, obs_repo, mock_cloudwatch):
        """Returns ERROR state when API call fails."""
        mock_cloudwatch.describe_alarms.side_effect = Exception("Access denied")

        result = obs_repo.get_alarm_metric_data("test-alarm")

        assert result["alarm_config"] == {}
        assert result["datapoints"] == []
        assert result["current_state"] == "ERROR"

    def test_sorts_datapoints_by_timestamp(self, obs_repo, mock_cloudwatch):
        """Datapoints are sorted chronologically."""
        mock_cloudwatch.describe_alarms.return_value = {
            "MetricAlarms": [{
                "MetricName": "Errors",
                "Namespace": "AWS/Lambda",
                "Threshold": 1.0,
                "ComparisonOperator": "GreaterThanThreshold",
                "EvaluationPeriods": 1,
                "DatapointsToAlarm": 1,
                "StateValue": "OK",
                "Dimensions": [],
                "Period": 60,
            }]
        }

        mock_cloudwatch.get_metric_statistics.return_value = {
            "Datapoints": [
                {"Timestamp": datetime(2026, 3, 30, 12, 2, 0, tzinfo=timezone.utc), "Average": 3.0},
                {"Timestamp": datetime(2026, 3, 30, 12, 0, 0, tzinfo=timezone.utc), "Average": 1.0},
                {"Timestamp": datetime(2026, 3, 30, 12, 1, 0, tzinfo=timezone.utc), "Average": 2.0},
            ]
        }

        result = obs_repo.get_alarm_metric_data("test-alarm")

        assert result["datapoints"][0]["value"] == 1.0
        assert result["datapoints"][1]["value"] == 2.0
        assert result["datapoints"][2]["value"] == 3.0

    def test_handles_missing_datapoints(self, obs_repo, mock_cloudwatch):
        """Handles case with no metric datapoints."""
        mock_cloudwatch.describe_alarms.return_value = {
            "MetricAlarms": [{
                "MetricName": "Errors",
                "Namespace": "AWS/Lambda",
                "Threshold": 1.0,
                "ComparisonOperator": "GreaterThanThreshold",
                "EvaluationPeriods": 1,
                "DatapointsToAlarm": 1,
                "StateValue": "INSUFFICIENT_DATA",
                "Dimensions": [],
                "Period": 60,
            }]
        }

        mock_cloudwatch.get_metric_statistics.return_value = {"Datapoints": []}

        result = obs_repo.get_alarm_metric_data("test-alarm")

        assert result["datapoints"] == []
        assert result["current_state"] == "INSUFFICIENT_DATA"


# ------------------------------------------------------------------ #
# get_lambda_metrics (Phase 1 enhancement)
# ------------------------------------------------------------------ #

class TestGetLambdaMetrics:
    """Retrieves Lambda runtime metrics with parallel execution."""

    @patch.object(ObservabilityRepository, '_get_single_metric')
    def test_returns_all_metrics_successfully(self, mock_get_single, obs_repo):
        """Parallel execution retrieves all 5 metrics."""
        def get_metric_side_effect(function_name, metric_name, statistic, start_time, end_time):
            metric_values = {
                ("Invocations", "Sum"): 100.0,
                ("Errors", "Sum"): 5.0,
                ("Throttles", "Sum"): 2.0,
                ("Duration", "Average"): 250.0,
                ("ConcurrentExecutions", "Maximum"): 10.0,
            }
            return metric_values.get((metric_name, statistic), 0.0)

        mock_get_single.side_effect = get_metric_side_effect

        result = obs_repo.get_lambda_metrics("test-function", lookback_minutes=15)

        assert result["invocations"] == 100
        assert result["errors"] == 5
        assert result["throttles"] == 2
        assert result["duration_avg"] == 250.0
        assert result["concurrent_executions_max"] == 10
        assert result["error_rate"] == 5.0  # 5/100 * 100 = 5%
        assert mock_get_single.call_count == 5

    @patch.object(ObservabilityRepository, '_get_single_metric')
    def test_calculates_error_rate_correctly(self, mock_get_single, obs_repo):
        """Error rate calculated as (errors / invocations) * 100."""
        def get_metric_side_effect(function_name, metric_name, statistic, start_time, end_time):
            metric_values = {
                ("Invocations", "Sum"): 200.0,
                ("Errors", "Sum"): 10.0,
                ("Throttles", "Sum"): 0.0,
                ("Duration", "Average"): 100.0,
                ("ConcurrentExecutions", "Maximum"): 5.0,
            }
            return metric_values.get((metric_name, statistic), 0.0)

        mock_get_single.side_effect = get_metric_side_effect

        result = obs_repo.get_lambda_metrics("test-function")

        assert result["error_rate"] == 5.0  # 10/200 * 100 = 5%

    @patch.object(ObservabilityRepository, '_get_single_metric')
    def test_handles_zero_invocations(self, mock_get_single, obs_repo):
        """Error rate is 0 when invocations = 0 (avoids division by zero)."""
        mock_get_single.return_value = 0.0

        result = obs_repo.get_lambda_metrics("test-function")

        assert result["invocations"] == 0
        assert result["error_rate"] == 0.0

    @patch.object(ObservabilityRepository, '_get_single_metric')
    def test_handles_missing_datapoints_for_single_metric(self, mock_get_single, obs_repo):
        """Individual metric failures return 0.0 without affecting others."""
        def get_metric_side_effect(function_name, metric_name, statistic, start_time, end_time):
            metric_values = {
                ("Invocations", "Sum"): 50.0,
                ("Errors", "Sum"): 0.0,  # Missing data
                ("Throttles", "Sum"): 1.0,
                ("Duration", "Average"): 200.0,
                ("ConcurrentExecutions", "Maximum"): 3.0,
            }
            return metric_values.get((metric_name, statistic), 0.0)

        mock_get_single.side_effect = get_metric_side_effect

        result = obs_repo.get_lambda_metrics("test-function")

        assert result["invocations"] == 50
        assert result["errors"] == 0  # Missing datapoint returns 0
        assert result["throttles"] == 1
        assert result["duration_avg"] == 200.0

    def test_returns_zeros_on_complete_failure(self, obs_repo, mock_cloudwatch):
        """Returns all zeros when outer try block fails."""
        mock_cloudwatch.get_metric_statistics.side_effect = Exception("Service unavailable")

        result = obs_repo.get_lambda_metrics("test-function")

        assert result["invocations"] == 0
        assert result["errors"] == 0
        assert result["throttles"] == 0
        assert result["duration_avg"] == 0.0
        assert result["concurrent_executions_max"] == 0
        assert result["error_rate"] == 0.0


# ------------------------------------------------------------------ #
# get_recent_deployments (Phase 1 enhancement)
# ------------------------------------------------------------------ #

class TestGetRecentDeployments:
    """Retrieves recent Lambda deployments for incident correlation."""

    @patch('src.repositories.observability_repository.datetime')
    def test_returns_recent_versions(self, mock_datetime, obs_repo, mock_lambda):
        """Returns versions published within lookback window."""
        # Fix current time to 2026-03-30T12:30:00
        mock_datetime.now.return_value = datetime(2026, 3, 30, 12, 30, 0, tzinfo=timezone.utc)
        mock_datetime.fromisoformat = datetime.fromisoformat

        mock_lambda.list_versions_by_function.return_value = {
            "Versions": [
                {
                    "Version": "$LATEST",
                    "LastModified": "2026-03-30T12:25:00.000+0000",
                },
                {
                    "Version": "5",
                    "LastModified": "2026-03-30T12:20:00.000+0000",
                    "CodeSha256": "sha-5",
                    "Runtime": "python3.12",
                    "MemorySize": 512,
                    "Timeout": 30,
                },
                {
                    "Version": "4",
                    "LastModified": "2026-03-30T12:15:00.000+0000",
                    "CodeSha256": "sha-4",
                    "Runtime": "python3.12",
                    "MemorySize": 512,
                    "Timeout": 30,
                },
            ]
        }

        result = obs_repo.get_recent_deployments("test-function", lookback_minutes=60)

        assert len(result) == 2  # $LATEST excluded
        assert result[0]["version"] == "5"
        assert result[0]["code_sha256"] == "sha-5"
        assert result[0]["runtime"] == "python3.12"
        assert result[1]["version"] == "4"

    @patch('src.repositories.observability_repository.datetime')
    def test_filters_by_time_window(self, mock_datetime, obs_repo, mock_lambda):
        """Only returns versions within lookback_minutes."""
        # Fix current time to 2026-03-30T13:00:00
        mock_datetime.now.return_value = datetime(2026, 3, 30, 13, 0, 0, tzinfo=timezone.utc)
        mock_datetime.fromisoformat = datetime.fromisoformat

        mock_lambda.list_versions_by_function.return_value = {
            "Versions": [
                {
                    "Version": "3",
                    "LastModified": "2026-03-30T12:50:00.000+0000",  # 10 min ago (within 60 min window)
                    "CodeSha256": "sha-3",
                    "Runtime": "python3.12",
                    "MemorySize": 512,
                    "Timeout": 30,
                },
                {
                    "Version": "2",
                    "LastModified": "2026-03-30T10:00:00.000+0000",  # 3 hours ago (outside window)
                    "CodeSha256": "sha-2",
                    "Runtime": "python3.12",
                    "MemorySize": 512,
                    "Timeout": 30,
                },
            ]
        }

        result = obs_repo.get_recent_deployments("test-function", lookback_minutes=60)

        assert len(result) == 1
        assert result[0]["version"] == "3"

    @patch('src.repositories.observability_repository.datetime')
    def test_sorts_by_timestamp_descending(self, mock_datetime, obs_repo, mock_lambda):
        """Most recent version first."""
        # Fix current time to 2026-03-30T12:30:00
        mock_datetime.now.return_value = datetime(2026, 3, 30, 12, 30, 0, tzinfo=timezone.utc)
        mock_datetime.fromisoformat = datetime.fromisoformat

        mock_lambda.list_versions_by_function.return_value = {
            "Versions": [
                {
                    "Version": "1",
                    "LastModified": "2026-03-30T12:00:00.000+0000",
                    "CodeSha256": "sha-1",
                    "Runtime": "python3.12",
                    "MemorySize": 512,
                    "Timeout": 30,
                },
                {
                    "Version": "3",
                    "LastModified": "2026-03-30T12:20:00.000+0000",
                    "CodeSha256": "sha-3",
                    "Runtime": "python3.12",
                    "MemorySize": 512,
                    "Timeout": 30,
                },
                {
                    "Version": "2",
                    "LastModified": "2026-03-30T12:10:00.000+0000",
                    "CodeSha256": "sha-2",
                    "Runtime": "python3.12",
                    "MemorySize": 512,
                    "Timeout": 30,
                },
            ]
        }

        result = obs_repo.get_recent_deployments("test-function", lookback_minutes=60)

        assert result[0]["version"] == "3"  # Most recent
        assert result[1]["version"] == "2"
        assert result[2]["version"] == "1"

    @patch('src.repositories.observability_repository.datetime')
    def test_limits_to_10_results(self, mock_datetime, obs_repo, mock_lambda):
        """Returns max 10 deployments."""
        # Fix current time to 2026-03-30T12:30:00
        mock_datetime.now.return_value = datetime(2026, 3, 30, 12, 30, 0, tzinfo=timezone.utc)
        mock_datetime.fromisoformat = datetime.fromisoformat

        versions = [
            {
                "Version": str(i),
                "LastModified": "2026-03-30T12:00:00.000+0000",
                "CodeSha256": f"sha-{i}",
                "Runtime": "python3.12",
                "MemorySize": 512,
                "Timeout": 30,
            }
            for i in range(1, 16)  # 15 versions
        ]
        mock_lambda.list_versions_by_function.return_value = {"Versions": versions}

        result = obs_repo.get_recent_deployments("test-function", lookback_minutes=60)

        assert len(result) == 10

    def test_skips_latest_pseudo_version(self, obs_repo, mock_lambda):
        """$LATEST is always excluded."""
        mock_lambda.list_versions_by_function.return_value = {
            "Versions": [
                {
                    "Version": "$LATEST",
                    "LastModified": "2026-03-30T12:30:00.000+0000",
                    "CodeSha256": "sha-latest",
                    "Runtime": "python3.12",
                    "MemorySize": 512,
                    "Timeout": 30,
                },
            ]
        }

        result = obs_repo.get_recent_deployments("test-function")

        assert len(result) == 0

    def test_handles_missing_timestamp(self, obs_repo, mock_lambda):
        """Skips versions with missing LastModified."""
        mock_lambda.list_versions_by_function.return_value = {
            "Versions": [
                {
                    "Version": "1",
                    # Missing LastModified
                    "CodeSha256": "sha-1",
                    "Runtime": "python3.12",
                    "MemorySize": 512,
                    "Timeout": 30,
                },
            ]
        }

        result = obs_repo.get_recent_deployments("test-function")

        assert len(result) == 0

    def test_returns_empty_on_exception(self, obs_repo, mock_lambda):
        """Returns empty list when API call fails."""
        mock_lambda.list_versions_by_function.side_effect = Exception("Function not found")

        result = obs_repo.get_recent_deployments("nonexistent-function")

        assert result == []
