"""ObservabilityRepository — CloudWatch Logs and Alarms operations.

Used for cool-off checks, log analysis, and post-remediation verification.
All observability concerns (tracing, metrics, logging) handled by @observe decorator."""

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3

from shared.middleware.observability import observe

logger = logging.getLogger(__name__)

# Timezone-aware datetime constant for sorting datapoints with missing timestamps
_MIN_DATETIME_UTC = datetime.min.replace(tzinfo=timezone.utc)


class ObservabilityRepository:
    """CloudWatch Logs and Alarms — same operational domain."""

    def __init__(self, logs_client=None, cloudwatch_client=None, lambda_client=None):
        self._logs = logs_client or boto3.client("logs")
        self._cloudwatch = cloudwatch_client or boto3.client("cloudwatch")
        self._lambda = lambda_client or boto3.client("lambda")

    # ------------------------------------------------------------------ #
    # Alarm operations
    # ------------------------------------------------------------------ #

    @observe(operation="check_alarm_state", metric_prefix="alarm_check")
    def get_alarm_state(self, alarm_name: str) -> str:
        """Returns current alarm state: ALARM, OK, or INSUFFICIENT_DATA."""
        response = self._cloudwatch.describe_alarms(AlarmNames=[alarm_name])
        alarms = response.get("MetricAlarms", [])
        if not alarms:
            return "INSUFFICIENT_DATA"
        return alarms[0].get("StateValue", "INSUFFICIENT_DATA")

    @observe(operation="get_alarm_history", metric_prefix="alarm_history")
    def get_state_change_time(self, alarm_name: str) -> datetime | None:
        """Returns when alarm last entered ALARM state."""
        response = self._cloudwatch.describe_alarm_history(
            AlarmName=alarm_name,
            HistoryItemType="StateUpdate",
            MaxRecords=1,
        )
        items = response.get("AlarmHistoryItems", [])
        if not items:
            return None
        return items[0].get("Timestamp")

    # ------------------------------------------------------------------ #
    # Log operations
    # ------------------------------------------------------------------ #

    @observe(operation="collect_error_logs", metric_prefix="log_analysis")
    def collect_errors(
        self, log_group: str, start_time: datetime, end_time: datetime, max_events: int = 500
    ) -> list[dict]:
        """Pulls error logs within bounded window using Logs Insights async query."""
        start_epoch_s = int(start_time.timestamp())
        end_epoch_s = int(end_time.timestamp())

        query = (
            "fields @timestamp, @message, @logStream, @requestId "
            "| filter @message like /ERROR|Error|Exception|Traceback|FAILED|failed|Timeout|timeout|ImportError|ModuleNotFoundError|SyntaxError/ "
            "| parse @message '\"error_type\":\"*\"' as error_type "
            "| parse @message '\"operation\":\"*\"' as operation "
            "| parse @message '\"user_id\":\"*\"' as user_id "
            f"| sort @timestamp desc | limit {max_events}"
        )

        return self._run_insights_query(log_group, start_epoch_s, end_epoch_s, query)

    @observe(operation="collect_recent_logs", metric_prefix="log_recent")
    def collect_recent(
        self, log_group: str, minutes: int = 5, max_events: int = 100
    ) -> list[dict]:
        """Pulls recent logs for verification or resolution evidence.

        Uses synchronous filter_log_events (small window, low volume)."""
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=minutes)

        try:
            response = self._logs.filter_log_events(
                logGroupName=log_group,
                startTime=int(start_time.timestamp() * 1000),
                endTime=int(end_time.timestamp() * 1000),
                limit=max_events,
            )
            return [
                {
                    "message": event.get("message", ""),
                    "timestamp": event.get("timestamp", 0),
                    "log_stream": event.get("logStreamName", ""),
                }
                for event in response.get("events", [])
            ]
        except Exception:
            logger.exception("Failed to collect recent logs from %s", log_group)
            return []

    # ------------------------------------------------------------------ #
    # Error payload extraction
    # ------------------------------------------------------------------ #

    @observe(operation="collect_error_payloads", metric_prefix="log_payloads")
    def collect_error_payloads(
        self,
        log_group: str,
        request_ids: list[str],
        start_time: datetime,
        end_time: datetime,
        max_payloads: int = 5,
    ) -> list[dict]:
        """Retrieves input event/payload log entries for failed Lambda invocations.

        Queries for log entries matching the given request_ids that contain
        event payload data (logged by handler on invocation start).
        Returns up to max_payloads results for Jira attachment."""
        if not request_ids:
            return []

        ids = request_ids[:max_payloads]
        id_filter = " or ".join(f'@requestId = "{rid}"' for rid in ids)

        query = (
            "fields @timestamp, @message, @requestId "
            f"| filter ({id_filter}) "
            "| filter @message like /event_payload|request_body|input_event|lambda_handler.*event/ "
            f"| sort @timestamp asc | limit {max_payloads}"
        )

        start_epoch_s = int(start_time.timestamp())
        end_epoch_s = int(end_time.timestamp())

        return self._run_insights_query(log_group, start_epoch_s, end_epoch_s, query)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _run_insights_query(
        self, log_group: str, start_epoch_s: int, end_epoch_s: int, query: str
    ) -> list[dict]:
        """Submits a Logs Insights query and polls for results with exponential backoff."""
        try:
            response = self._logs.start_query(
                logGroupName=log_group,
                startTime=start_epoch_s,
                endTime=end_epoch_s,
                queryString=query,
            )
            query_id = response["queryId"]
        except Exception:
            logger.exception("Failed to start Logs Insights query on %s", log_group)
            return []

        wait = 0.5
        elapsed = 0.0
        max_wait = 30.0

        while elapsed < max_wait:
            try:
                result = self._logs.get_query_results(queryId=query_id)
                status = result.get("status", "")

                if status == "Complete":
                    return self._parse_query_results(result.get("results", []))
                if status in ("Failed", "Cancelled"):
                    logger.warning("Logs Insights query %s ended with status: %s", query_id, status)
                    return []

                time.sleep(wait)
                elapsed += wait
                wait = min(wait * 2, 5.0)
            except Exception:
                logger.exception("Failed polling Logs Insights query %s", query_id)
                return []

        logger.warning("Logs Insights query %s timed out after %.0fs", query_id, max_wait)
        return []

    @staticmethod
    def _parse_query_results(raw_results: list[list[dict]]) -> list[dict]:
        """Converts Logs Insights result format to flat dicts."""
        parsed = []
        for row in raw_results:
            entry = {}
            for field in row:
                entry[field.get("field", "")] = field.get("value", "")
            parsed.append(entry)
        return parsed

    # ------------------------------------------------------------------ #
    # Metrics collection (Phase 1 enhancement)
    # ------------------------------------------------------------------ #

    @observe(operation="get_alarm_metric_data", metric_prefix="metrics")
    def get_alarm_metric_data(self, alarm_name: str, lookback_minutes: int = 15) -> dict[str, Any]:
        """Retrieves alarm configuration and recent metric datapoints.

        Returns:
            {
                "alarm_config": {
                    "metric_name": str,
                    "namespace": str,
                    "threshold": float,
                    "comparison_operator": str,
                    "evaluation_periods": int,
                    "datapoints_to_alarm": int
                },
                "datapoints": [{"timestamp": str, "value": float}, ...],
                "current_state": str
            }

        On error: returns empty structure with empty lists/dicts.
        """
        try:
            response = self._cloudwatch.describe_alarms(AlarmNames=[alarm_name])
            alarms = response.get("MetricAlarms", [])

            if not alarms:
                return {"alarm_config": {}, "datapoints": [], "current_state": "NOT_FOUND"}

            alarm = alarms[0]

            alarm_config = {
                "metric_name": alarm.get("MetricName", ""),
                "namespace": alarm.get("Namespace", ""),
                "threshold": alarm.get("Threshold", 0.0),
                "comparison_operator": alarm.get("ComparisonOperator", ""),
                "evaluation_periods": alarm.get("EvaluationPeriods", 0),
                "datapoints_to_alarm": alarm.get("DatapointsToAlarm", 0)
            }

            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(minutes=lookback_minutes)

            dimensions = alarm.get("Dimensions", [])
            metric_name = alarm.get("MetricName", "")
            namespace = alarm.get("Namespace", "")
            period = alarm.get("Period", 60)

            stats_response = self._cloudwatch.get_metric_statistics(
                Namespace=namespace,
                MetricName=metric_name,
                Dimensions=dimensions,
                StartTime=start_time,
                EndTime=end_time,
                Period=period,
                Statistics=["Average", "Sum", "Maximum"]
            )

            datapoints = [
                {
                    "timestamp": dp.get("Timestamp").isoformat() if dp.get("Timestamp") else "",
                    "value": dp.get("Average", dp.get("Sum", dp.get("Maximum", 0.0)))
                }
                for dp in sorted(stats_response.get("Datapoints", []), key=lambda x: x.get("Timestamp") or _MIN_DATETIME_UTC)
            ]

            return {
                "alarm_config": alarm_config,
                "datapoints": datapoints,
                "current_state": alarm.get("StateValue", "UNKNOWN")
            }

        except Exception:
            return {"alarm_config": {}, "datapoints": [], "current_state": "ERROR"}

    @observe(operation="get_lambda_metrics", metric_prefix="metrics")
    def get_lambda_metrics(self, function_name: str, lookback_minutes: int = 15) -> dict[str, Any]:
        """Retrieves Lambda runtime metrics (errors, invocations, throttles, duration, concurrency).

        Uses parallel execution to collect 5 metrics concurrently (~150ms total vs 900ms sequential).

        Returns:
            {
                "invocations": int,
                "errors": int,
                "throttles": int,
                "duration_avg": float (milliseconds),
                "concurrent_executions_max": int,
                "error_rate": float (percentage)
            }

        On error: returns structure with all values set to 0.0.
        """
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=lookback_minutes)

        try:
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = {
                    executor.submit(
                        self._get_single_metric, function_name, metric_name, statistic, start_time, end_time
                    ): (metric_name, statistic)
                    for metric_name, statistic in [
                        ("Invocations", "Sum"),
                        ("Errors", "Sum"),
                        ("Throttles", "Sum"),
                        ("Duration", "Average"),
                        ("ConcurrentExecutions", "Maximum"),
                    ]
                }

                results = {}
                for future in futures:
                    metric_name, statistic = futures[future]
                    try:
                        results[f"{metric_name}_{statistic}"] = future.result()
                    except Exception:
                        results[f"{metric_name}_{statistic}"] = 0.0

            invocations = results.get("Invocations_Sum", 0.0)
            errors = results.get("Errors_Sum", 0.0)
            throttles = results.get("Throttles_Sum", 0.0)
            duration_avg = results.get("Duration_Average", 0.0)
            concurrent_max = results.get("ConcurrentExecutions_Maximum", 0.0)

            error_rate = (errors / invocations * 100.0) if invocations > 0 else 0.0

            return {
                "invocations": int(invocations),
                "errors": int(errors),
                "throttles": int(throttles),
                "duration_avg": duration_avg,
                "concurrent_executions_max": int(concurrent_max),
                "error_rate": round(error_rate, 2)
            }

        except Exception:
            return {
                "invocations": 0,
                "errors": 0,
                "throttles": 0,
                "duration_avg": 0.0,
                "concurrent_executions_max": 0,
                "error_rate": 0.0
            }

    def _get_single_metric(
        self, function_name: str, metric_name: str, statistic: str, start_time: datetime, end_time: datetime
    ) -> float:
        """Helper method to fetch a single Lambda metric.

        Returns metric value or 0.0 on error (no exceptions raised).
        """
        try:
            response = self._cloudwatch.get_metric_statistics(
                Namespace="AWS/Lambda",
                MetricName=metric_name,
                Dimensions=[{"Name": "FunctionName", "Value": function_name}],
                StartTime=start_time,
                EndTime=end_time,
                Period=60,
                Statistics=[statistic]
            )

            datapoints = response.get("Datapoints", [])
            if not datapoints:
                return 0.0

            sorted_points = sorted(datapoints, key=lambda x: x.get("Timestamp") or _MIN_DATETIME_UTC, reverse=True)
            return sorted_points[0].get(statistic, 0.0)

        except Exception:
            return 0.0

    @observe(operation="get_recent_deployments", metric_prefix="deployments")
    def get_recent_deployments(self, function_name: str, lookback_minutes: int = 60) -> list[dict]:
        """Retrieves recent Lambda deployments (versions) to correlate incidents with code changes.

        Returns up to 10 most recent versions published within lookback window.

        Returns:
            [
                {
                    "timestamp": str (ISO 8601),
                    "version": str,
                    "code_sha256": str,
                    "runtime": str,
                    "memory_size": int,
                    "timeout": int
                },
                ...
            ]

        On error: returns empty list.
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)

        try:
            response = self._lambda.list_versions_by_function(FunctionName=function_name)
            versions = response.get("Versions", [])

            deployments = []
            for version in versions:
                if version.get("Version") == "$LATEST":
                    continue

                last_modified_str = version.get("LastModified", "")
                if not last_modified_str:
                    continue

                try:
                    last_modified = datetime.fromisoformat(last_modified_str.replace("+0000", "+00:00"))
                except Exception:
                    continue

                if last_modified < cutoff_time:
                    continue

                deployments.append({
                    "timestamp": last_modified.isoformat(),
                    "version": version.get("Version", ""),
                    "code_sha256": version.get("CodeSha256", ""),
                    "runtime": version.get("Runtime", ""),
                    "memory_size": version.get("MemorySize", 0),
                    "timeout": version.get("Timeout", 0)
                })

            deployments.sort(key=lambda x: x["timestamp"], reverse=True)
            return deployments[:10]

        except Exception:
            return []
