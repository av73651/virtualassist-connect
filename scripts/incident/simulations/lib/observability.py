"""OpenTelemetry observability for simulation framework.

Provides @observe decorator matching production Lambda pattern, adapted for CLI/test environment.
Uses AWS X-Ray for traces, CloudWatch for logs and metrics.
"""

import functools
import json
import logging
import time
from datetime import datetime
from typing import Any, Callable

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader, ConsoleMetricExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.trace import Status, StatusCode
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

from . import config

# Service resource identification
_resource = Resource.create({
    "service.name": "sre-simulation-framework",
    "service.version": "1.0.0",
    "deployment.environment": config.STAGE,
})

# Initialize trace provider with X-Ray exporter
_trace_provider = None
_meter_provider = None

try:
    # Use OTLP exporter to CloudWatch (AWS managed endpoint)
    # In production, this would be AWS X-Ray exporter or ADOT collector
    _trace_exporter = OTLPSpanExporter(
        endpoint=config.OTEL_EXPORTER_OTLP_ENDPOINT,
    )
    _trace_provider = TracerProvider(resource=_resource)
    _trace_provider.add_span_processor(BatchSpanProcessor(_trace_exporter))
    trace.set_tracer_provider(_trace_provider)
except Exception as e:
    # Graceful degradation: use no-op provider if tracing unavailable
    logging.warning(f"Tracing initialization failed: {e}. Using no-op tracer.")
    _trace_provider = TracerProvider(resource=_resource)
    trace.set_tracer_provider(_trace_provider)

try:
    # Metrics export to console for local dev, CloudWatch in production
    _metric_reader = PeriodicExportingMetricReader(ConsoleMetricExporter())
    _meter_provider = MeterProvider(resource=_resource, metric_readers=[_metric_reader])
    metrics.set_meter_provider(_meter_provider)
except Exception as e:
    logging.warning(f"Metrics initialization failed: {e}. Metrics disabled.")

# Module exports
tracer = trace.get_tracer("simulation-framework")
meter = metrics.get_meter("simulation-framework")

# Standard logger (will be used by decorator)
logger = logging.getLogger("simulation-framework")
logger.setLevel(logging.INFO)


def get_trace_id() -> str:
    """Get current trace ID for logging correlation."""
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        return format(span.get_span_context().trace_id, '032x')
    return "no-trace"


def observe(operation: str, metric_prefix: str = "simulation"):
    """Decorator for observability (tracing, metrics, structured logging).

    Mirrors production @observe decorator from shared/middleware/observability.py.
    Adapted for test infrastructure (non-Lambda environment).

    Usage:
        @observe(operation="invoke_lambda", metric_prefix="test")
        def invoke_triage(event: dict) -> dict:
            # Function implementation
            return result

    Provides:
    - Distributed tracing with OpenTelemetry spans
    - Structured JSON logging with trace IDs
    - Success/error metrics
    - Duration metrics
    - Automatic error handling and span status
    """
    def decorator(func: Callable) -> Callable:
        # Create metrics for this operation
        counter = meter.create_counter(
            f"{metric_prefix}.{operation}.invocations",
            description=f"Number of {operation} invocations",
        )
        error_counter = meter.create_counter(
            f"{metric_prefix}.{operation}.errors",
            description=f"Number of {operation} errors",
        )
        duration_histogram = meter.create_histogram(
            f"{metric_prefix}.{operation}.duration",
            description=f"Duration of {operation} in seconds",
        )

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Start span
            with tracer.start_as_current_span(
                f"{metric_prefix}.{operation}",
                attributes={
                    "operation": operation,
                    "function": func.__name__,
                    "stage": config.STAGE,
                }
            ) as span:
                start_time = time.time()
                trace_id = get_trace_id()

                # Entry log (structured JSON)
                entry_log = {
                    "level": "INFO",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "trace_id": trace_id,
                    "operation": operation,
                    "function": func.__name__,
                    "stage": config.STAGE,
                    "message": f"{operation} started",
                }
                logger.info(json.dumps(entry_log))

                try:
                    # Execute function
                    result = func(*args, **kwargs)

                    # Success metrics
                    duration = time.time() - start_time
                    counter.add(1, {"status": "success", "stage": config.STAGE})
                    duration_histogram.record(duration, {"status": "success", "stage": config.STAGE})

                    # Success span status
                    span.set_status(Status(StatusCode.OK))
                    span.set_attribute("duration_seconds", duration)

                    # Success log (structured JSON)
                    success_log = {
                        "level": "INFO",
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "trace_id": trace_id,
                        "operation": operation,
                        "function": func.__name__,
                        "stage": config.STAGE,
                        "duration_ms": int(duration * 1000),
                        "message": f"{operation} completed successfully",
                    }
                    logger.info(json.dumps(success_log))

                    return result

                except Exception as e:
                    # Error metrics
                    duration = time.time() - start_time
                    counter.add(1, {"status": "error", "stage": config.STAGE})
                    error_counter.add(1, {
                        "error_type": type(e).__name__,
                        "stage": config.STAGE,
                    })
                    duration_histogram.record(duration, {"status": "error", "stage": config.STAGE})

                    # Error span status
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.set_attribute("error.type", type(e).__name__)
                    span.set_attribute("error.message", str(e))

                    # Error log (structured JSON)
                    error_log = {
                        "level": "ERROR",
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "trace_id": trace_id,
                        "operation": operation,
                        "function": func.__name__,
                        "stage": config.STAGE,
                        "duration_ms": int(duration * 1000),
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "message": f"{operation} failed",
                    }
                    logger.error(json.dumps(error_log))

                    # Re-raise exception
                    raise

        return wrapper
    return decorator
