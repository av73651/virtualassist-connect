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
