"""CloudWatch Logs helpers for verifying Lambda execution."""

import re
import time
import boto3

from . import config

_logs = boto3.client("logs", region_name=config.REGION)


def get_recent(since_ms: int, limit: int = 100, log_group: str = "") -> list[dict]:
    """Fetch recent Lambda log events since a timestamp (epoch ms)."""
    group = log_group or config.LOG_GROUP
    try:
        resp = _logs.filter_log_events(
            logGroupName=group,
            startTime=since_ms,
            limit=limit,
            interleaved=True,
        )
        return resp.get("events", [])
    except Exception:
        return []


def wait_for_pattern(
    pattern: str,
    since_ms: int,
    timeout: int = 60,
    poll: int = 5,
    log_group: str = "",
) -> str | None:
    """Poll logs until a regex pattern is found. Returns matching message or None."""
    regex = re.compile(pattern)
    deadline = time.time() + timeout
    while time.time() < deadline:
        events = get_recent(since_ms, limit=200, log_group=log_group)
        for event in events:
            msg = event.get("message", "")
            if regex.search(msg):
                return msg
        time.sleep(poll)
    return None


def now_ms() -> int:
    """Current time as epoch milliseconds (for log queries)."""
    return int(time.time() * 1000)


# Simulation log stream name for synthetic error logs
SIM_LOG_STREAM = "sim-error-stream"


def seed_error_logs(
    log_group: str,
    messages: list[str],
    age_seconds: int = 300,
) -> None:
    """Write synthetic error log events into a CloudWatch log group.

    Events are timestamped `age_seconds` in the past so they fall outside
    the triage verification window (2 min) but inside the analysis window (15 min).
    Creates the log group and stream if they don't exist."""
    stream_name = SIM_LOG_STREAM

    # Ensure log group exists
    try:
        _logs.create_log_group(logGroupName=log_group)
    except _logs.exceptions.ResourceAlreadyExistsException:
        pass

    # Ensure log stream exists
    try:
        _logs.create_log_stream(logGroupName=log_group, logStreamName=stream_name)
    except _logs.exceptions.ResourceAlreadyExistsException:
        pass

    base_ts = now_ms() - (age_seconds * 1000)
    log_events = [
        {"timestamp": base_ts + (i * 1000), "message": msg}
        for i, msg in enumerate(messages)
    ]

    _logs.put_log_events(
        logGroupName=log_group,
        logStreamName=stream_name,
        logEvents=log_events,
    )


def delete_log_group(log_group: str) -> None:
    """Delete a CloudWatch log group (ignores if not found)."""
    try:
        _logs.delete_log_group(logGroupName=log_group)
    except _logs.exceptions.ResourceNotFoundException:
        pass
