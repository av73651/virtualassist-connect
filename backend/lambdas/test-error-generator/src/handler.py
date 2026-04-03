"""Test Error Generator Handler - generates errors for integration testing.

This Lambda is used by simulation tests to generate REAL errors with REAL logs
and metrics, enabling end-to-end testing of the SRE platform's observability
and incident management capabilities.

Usage:
    {
        "error_type": "division_by_zero" | "null_pointer" | "timeout" | "memory_exhaustion" | "import_error",
        "error_count": 10,
        "error_message": "Custom error context"
    }
"""

import json
import logging
import time
from datetime import datetime, timezone

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _error_division_by_zero():
    """Simulates arithmetic error."""
    return 1 / 0


def _error_null_pointer():
    """Simulates attribute error."""
    obj = None
    return obj.some_method()


def _error_type_error():
    """Simulates type error."""
    return "string" + 42


def _error_key_error():
    """Simulates key error."""
    data = {}
    return data["missing_key"]


def _error_index_error():
    """Simulates index error."""
    items = []
    return items[10]


def _error_import_error():
    """Simulates import error."""
    import nonexistent_module
    return nonexistent_module.do_something()


def _error_value_error():
    """Simulates value error."""
    return int("not_a_number")


def _error_timeout_simulation():
    """Simulates timeout by sleeping."""
    time.sleep(15)  # Exceeds most Lambda timeouts


def _error_memory_exhaustion():
    """Simulates memory exhaustion."""
    # Allocate large list to consume memory
    data = [0] * (10 ** 8)
    return len(data)


ERROR_GENERATORS = {
    "division_by_zero": _error_division_by_zero,
    "null_pointer": _error_null_pointer,
    "type_error": _error_type_error,
    "key_error": _error_key_error,
    "index_error": _error_index_error,
    "import_error": _error_import_error,
    "value_error": _error_value_error,
    "timeout": _error_timeout_simulation,
    "memory_exhaustion": _error_memory_exhaustion,
}


def lambda_handler(event, context):
    """Generate configurable errors for testing.

    Args:
        event: {
            "error_type": str,  # One of ERROR_GENERATORS keys
            "error_count": int,  # Number of errors to generate (default: 10)
            "error_message": str  # Optional context message
        }
        context: Lambda context

    Returns:
        {"statusCode": 500, "body": "..."}
    """
    error_type = event.get("error_type", "division_by_zero")
    error_count = event.get("error_count", 10)
    error_message = event.get("error_message", "Test error generation")

    if error_type not in ERROR_GENERATORS:
        logger.error(f"Unknown error_type: {error_type}. Available: {list(ERROR_GENERATORS.keys())}")
        return {
            "statusCode": 400,
            "body": json.dumps({
                "error": f"Unknown error_type: {error_type}",
                "available": list(ERROR_GENERATORS.keys())
            })
        }

    logger.info(json.dumps({
        "message": "Starting error generation",
        "error_type": error_type,
        "error_count": error_count,
        "context": error_message,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }))

    errors_generated = 0
    for i in range(error_count):
        try:
            ERROR_GENERATORS[error_type]()
        except Exception as e:
            errors_generated += 1
            # Structured error log for log analysis
            logger.error(json.dumps({
                "message": f"Generated test error {i+1}/{error_count}",
                "error_type": type(e).__name__,
                "error_message": str(e),
                "error_index": i + 1,
                "test_context": error_message,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }), exc_info=True)

    logger.info(json.dumps({
        "message": "Error generation complete",
        "errors_generated": errors_generated,
        "error_type": error_type,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }))

    return {
        "statusCode": 500,
        "body": json.dumps({
            "errors_generated": errors_generated,
            "error_type": error_type,
            "error_count": error_count
        })
    }
