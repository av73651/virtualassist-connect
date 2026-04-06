"""Shared timestamp utilities."""

from datetime import datetime


def utc_timestamp(dt: datetime) -> str:
    """Format UTC datetime as ISO 8601 with Z suffix."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
