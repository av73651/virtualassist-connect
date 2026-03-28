"""Structured Logging Configuration.

Configures Python logging to output structured JSON logs compatible with
CloudWatch Logs Insights and enterprise logging frameworks.

This module sets up a JSON formatter that properly handles the 'extra'
dictionaries passed to logger calls.
"""

import logging
import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict


class StructuredJsonFormatter(logging.Formatter):
    """JSON formatter for structured logging.

    Formats log records as JSON with proper handling of 'extra' fields.
    Compatible with CloudWatch Logs Insights and ELK/Splunk.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON.

        Args:
            record: Log record to format

        Returns:
            str: JSON-formatted log message
        """
        # Base log fields
        log_data: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add any extra fields passed via extra={}
        # Exclude standard fields that are already handled
        excluded_keys = {
            'name', 'msg', 'args', 'created', 'filename', 'funcName',
            'levelname', 'levelno', 'lineno', 'module', 'msecs',
            'message', 'pathname', 'process', 'processName',
            'relativeCreated', 'thread', 'threadName', 'exc_info',
            'exc_text', 'stack_info', 'asctime'
        }

        for key, value in record.__dict__.items():
            if key not in excluded_keys and not key.startswith('_'):
                log_data[key] = value

        return json.dumps(log_data, default=str)


def configure_structured_logging(level: str = "INFO") -> None:
    """Configure structured JSON logging for the application.

    Sets up the root logger with JSON formatting for all log outputs.
    Should be called once at application startup (e.g., in Lambda handler init).

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Example:
        >>> configure_structured_logging("INFO")
        >>> logger = logging.getLogger(__name__)
        >>> logger.info("User logged in", extra={"user_id": "123", "ip": "1.2.3.4"})
        {"timestamp": "2026-03-27T10:00:00.000Z", "level": "INFO", "logger": "__main__",
         "message": "User logged in", "user_id": "123", "ip": "1.2.3.4"}
    """
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler with JSON formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(StructuredJsonFormatter())

    # Add handler to root logger
    root_logger.addHandler(console_handler)


# Auto-configure on import (Lambda will use this)
# Can be overridden by explicitly calling configure_structured_logging()
import os
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
configure_structured_logging(LOG_LEVEL)
