"""ObservabilityRepository — CloudWatch Logs and Alarms operations.

Used for cool-off checks, log analysis, and post-remediation verification.
All observability concerns (tracing, metrics, logging) handled by @observe decorator."""

import logging
import time
from datetime import datetime, timedelta, timezone

import boto3

from shared.middleware.observability import observe

logger = logging.getLogger(__name__)


class ObservabilityRepository:
    """CloudWatch Logs and Alarms — same operational domain."""

    def __init__(self, logs_client=None, cloudwatch_client=None):
        self._logs = logs_client or boto3.client("logs")
        self._cloudwatch = cloudwatch_client or boto3.client("cloudwatch")

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
            "| filter @message like /ERROR|Error|Exception|Traceback/ "
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
