"""Observability Middleware - Enterprise AOP Decorator.

This module provides cross-cutting concerns for observability:
- OpenTelemetry distributed tracing
- OpenTelemetry metrics (counter + histogram)
- Structured logging with context
- Automatic error handling and recording

Usage:
    @observe(operation="get_hello_message", metric_prefix="hello_message")
    def get_hello_message(self) -> HelloMessage:
        # Pure business logic only
        return HelloMessage.create("Hello, World!")
"""

import time
import logging
from functools import wraps
from typing import Callable, Any, Dict, Optional
from opentelemetry import trace, metrics
from opentelemetry.trace import Status, StatusCode

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)

# Global cache for metrics to avoid recreating them
_counters: Dict[str, metrics.Counter] = {}
_histograms: Dict[str, metrics.Histogram] = {}


def _get_or_create_counter(metric_name: str) -> metrics.Counter:
    """Get or create a counter metric with caching.

    Args:
        metric_name: Base name for the counter metric

    Returns:
        metrics.Counter: Cached or newly created counter
    """
    if metric_name not in _counters:
        _counters[metric_name] = meter.create_counter(
            name=f"{metric_name}_total",
            description=f"Total number of {metric_name} operations",
            unit="1"
        )
    return _counters[metric_name]


def _get_or_create_histogram(metric_name: str) -> metrics.Histogram:
    """Get or create a histogram metric with caching.

    Args:
        metric_name: Base name for the histogram metric

    Returns:
        metrics.Histogram: Cached or newly created histogram
    """
    if metric_name not in _histograms:
        _histograms[metric_name] = meter.create_histogram(
            name=f"{metric_name}_duration",
            description=f"Duration of {metric_name} operation in milliseconds",
            unit="ms"
        )
    return _histograms[metric_name]


def observe(
    operation: str,
    metric_prefix: Optional[str] = None,
    include_result_attrs: bool = False
) -> Callable:
    """Enterprise observability decorator with tracing, metrics, and logging.

    Provides comprehensive cross-cutting concerns:
    - Creates OpenTelemetry span for distributed tracing
    - Records counter metric (success/error)
    - Records histogram metric (duration with status)
    - Logs entry/exit with structured context
    - Handles exceptions with full observability

    Args:
        operation: Operation name for span and logging (e.g., "get_hello_message")
        metric_prefix: Metric name prefix (defaults to operation)
        include_result_attrs: Whether to include result attributes in span (default: False)

    Returns:
        Callable: Decorated function with full observability

    Example:
        @observe(operation="get_hello_message", metric_prefix="hello_message")
        def get_hello_message(self) -> HelloMessage:
            return HelloMessage.create("Hello, World!")

    Observability Output:
        - Trace: Span named "get_hello_message" with status
        - Metrics: hello_message_total{status=success/error}
        - Metrics: hello_message_duration{status=success/error}
        - Logs: Structured JSON with service, method, duration
    """
    metric_name = metric_prefix or operation

    # Get or create metrics once at decoration time
    counter = _get_or_create_counter(metric_name)
    histogram = _get_or_create_histogram(metric_name)

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract service/class name from first argument (self)
            service_name = (
                args[0].__class__.__name__
                if args and hasattr(args[0], "__class__")
                else func.__module__.split(".")[-1]
            )
            method_name = func.__name__

            # Create base log context
            log_context = {
                "service": service_name,
                "method": method_name,
                "operation": operation,
            }

            # Start OpenTelemetry span
            with tracer.start_as_current_span(operation) as span:
                # Add span attributes
                span.set_attribute("service.name", service_name)
                span.set_attribute("method.name", method_name)

                # Entry logging
                logger.info(
                    f"Starting {operation.replace('_', ' ')}",
                    extra=log_context,
                )

                start_time = time.time()

                try:
                    # Execute business logic
                    result = func(*args, **kwargs)

                    # Calculate duration
                    duration_ms = (time.time() - start_time) * 1000

                    # Record success metrics
                    counter.add(1, {"status": "success"})
                    histogram.record(duration_ms, {"status": "success"})

                    # Update span with success
                    span.set_status(Status(StatusCode.OK))
                    span.set_attribute("operation.status", "success")
                    span.set_attribute("operation.duration_ms", round(duration_ms, 2))

                    # Optionally include result attributes in span
                    if include_result_attrs and hasattr(result, "__dict__"):
                        for key, value in result.__dict__.items():
                            if not key.startswith("_"):
                                span.set_attribute(f"result.{key}", str(value)[:100])

                    # Exit logging
                    logger.info(
                        f"Completed {operation.replace('_', ' ')}",
                        extra={
                            **log_context,
                            "status": "success",
                            "duration_ms": round(duration_ms, 2),
                        },
                    )

                    return result

                except Exception as e:
                    # Calculate duration
                    duration_ms = (time.time() - start_time) * 1000

                    # Record error metrics
                    counter.add(1, {"status": "error"})
                    histogram.record(duration_ms, {"status": "error"})

                    # Update span with error
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.set_attribute("operation.status", "error")
                    span.set_attribute("operation.duration_ms", round(duration_ms, 2))
                    span.set_attribute("error.type", type(e).__name__)
                    span.set_attribute("error.message", str(e))
                    span.record_exception(e)  # Record exception in span

                    # Error logging with full context
                    logger.error(
                        f"Failed {operation.replace('_', ' ')}",
                        extra={
                            **log_context,
                            "status": "error",
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "duration_ms": round(duration_ms, 2),
                        },
                        exc_info=True,  # Include full stack trace
                    )

                    # Re-raise to preserve exception semantics
                    raise

        return wrapper

    return decorator


# Legacy alias for backward compatibility
def record_business_metrics(metric_base_name: str) -> Callable:
    """Legacy decorator name - use observe() instead.

    Args:
        metric_base_name: Metric prefix name

    Returns:
        Callable: Decorator function

    Deprecated: Use observe() for new code.
    """
    return observe(operation=metric_base_name, metric_prefix=metric_base_name)
