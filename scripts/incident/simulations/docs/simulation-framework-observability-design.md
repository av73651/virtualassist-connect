# Simulation Framework Observability Design

**Date**: 2026-04-03  
**Component**: SRE Platform Simulation Framework  
**Type**: Test Infrastructure Enhancement

---

## 1. Context

The simulation framework is test infrastructure that validates the SRE incident management platform by invoking production Lambda functions (incident-detection, incident-triage, incident-escalation) and verifying their behavior.

**Current State:**
- Basic logging with `logger.info()` and `extra={}` fields
- Error handling with contextual messages
- Environment-based configuration

**Gap:**
- No distributed tracing (test operations not traced)
- No metrics collection
- No correlation between test execution and Lambda traces
- Manual logging without trace context
- Not following OpenTelemetry patterns

---

## 2. Design Goals

1. **Traceability**: Link test execution traces to production Lambda traces
2. **Observability**: Apply same observability standards as production code
3. **Debugging**: Enable quick diagnosis of test failures
4. **Metrics**: Track test execution patterns and success rates
5. **Standards Compliance**: Follow `patterns/observability-requirements.md`

---

## 3. Architecture Decision: Test Infrastructure Observability

### 3.1 Key Consideration

**Question**: Should test infrastructure follow the same observability patterns as production Lambda code?

**Answer**: YES, with adaptations:

| Aspect | Production Lambdas | Test Infrastructure |
|--------|-------------------|---------------------|
| **Runtime** | AWS Lambda + ADOT Layer | Local Python + OTel SDK |
| **Tracing** | Automatic via ADOT wrapper | Manual via `tracer.start_as_current_span()` |
| **Logging** | JSON with trace_id via ADOT | JSON with trace_id via OTel SDK |
| **Metrics** | OTel meter + CloudWatch | OTel meter + CloudWatch |
| **Trace Propagation** | Automatic (ADOT) | Manual (inject traceparent header) |

**Rationale:**
1. Test traces can be correlated with Lambda execution traces
2. Test metrics provide insights into test suite health
3. Consistent observability patterns across all code
4. Enables debugging test failures in production-like manner

---

## 4. Technology Stack

### 4.1 OpenTelemetry SDK (Not ADOT Layer)

```python
# requirements.txt additions
opentelemetry-api==1.22.0
opentelemetry-sdk==1.22.0
opentelemetry-exporter-otlp==1.22.0
opentelemetry-instrumentation-boto3==0.43b0  # Auto-instrument boto3 calls
```

**Why OTel SDK, not ADOT Layer:**
- ADOT Layer is for AWS Lambda runtime only
- Test infrastructure runs as CLI script (not Lambda)
- OTel SDK provides same functionality for non-Lambda environments

### 4.2 Trace Exporter

**Option 1**: OTLP to CloudWatch (via AWS Distro for OTel Collector)  
**Option 2**: X-Ray exporter directly  
**Chosen**: X-Ray exporter directly (simpler, no collector needed)

```python
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# OR for X-Ray
from opentelemetry.exporter.xray import XRaySpanExporter
```

---

## 5. Implementation Design

### 5.1 Initialization Module (`lib/observability.py`)

**Purpose**: Initialize OpenTelemetry once for entire test suite

```python
"""OpenTelemetry initialization for simulation framework.

Provides tracer, meter, and logger configured with X-Ray export.
"""

import logging
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.resources import Resource

from . import config

# Service resource identification
resource = Resource.create({
    "service.name": "sre-simulation-framework",
    "service.version": "1.0.0",
    "deployment.environment": config.STAGE,
})

# Trace provider setup
trace_provider = TracerProvider(resource=resource)
trace_exporter = OTLPSpanExporter(
    endpoint="https://api.honeycomb.io",  # Or AWS X-Ray endpoint
    headers={"x-honeycomb-team": "API_KEY"}  # From env var
)
trace_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
trace.set_tracer_provider(trace_provider)

# Metrics provider setup
metric_reader = PeriodicExportingMetricReader(
    OTLPMetricExporter(endpoint="https://api.honeycomb.io")
)
meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
metrics.set_meter_provider(meter_provider)

# Module exports
tracer = trace.get_tracer("simulation-framework")
meter = metrics.get_meter("simulation-framework")

# Structured logger with trace context
logger = logging.getLogger("simulation-framework")
logger.setLevel(logging.INFO)


def get_trace_id() -> str:
    """Get current trace ID for logging correlation."""
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        return format(span.get_span_context().trace_id, '032x')
    return "no-trace"


def log_with_trace(level: str, message: str, **extra):
    """Log with automatic trace ID injection."""
    extra["trace_id"] = get_trace_id()
    getattr(logger, level)(message, extra=extra)
```

### 5.2 Instrumented Lambda Invocation (`lib/eventbridge.py`)

**Before (Current - No Tracing):**
```python
def _invoke_lambda_sync(function_name: str, event: dict) -> dict:
    logger.info("Invoking Lambda", extra={"function_name": function_name})
    resp = _lambda.invoke(...)
    return payload
```

**After (With Tracing):**
```python
from .observability import tracer, meter, log_with_trace
from opentelemetry.trace import SpanKind, Status, StatusCode
from opentelemetry import propagate

# Metrics
lambda_invocations = meter.create_counter(
    "lambda.invocations",
    description="Number of Lambda invocations",
)
lambda_errors = meter.create_counter(
    "lambda.errors",
    description="Number of Lambda invocation errors",
)
lambda_duration = meter.create_histogram(
    "lambda.duration",
    description="Lambda invocation duration in seconds",
)

def _invoke_lambda_sync(function_name: str, event: dict) -> dict:
    """Invoke Lambda synchronously with distributed tracing.
    
    Creates a span and propagates trace context to Lambda.
    """
    with tracer.start_as_current_span(
        f"invoke_lambda:{function_name}",
        kind=SpanKind.CLIENT,
        attributes={
            "aws.lambda.function_name": function_name,
            "aws.region": config.REGION,
            "event.type": event.get("detail-type", "unknown"),
            "incident.key": event.get("detail", {}).get("incident_key", "unknown"),
        }
    ) as span:
        start_time = time.time()
        
        # Inject trace context into Lambda event (for propagation)
        carrier = {}
        propagate.inject(carrier)
        if "detail" not in event:
            event["detail"] = {}
        event["detail"]["_trace_context"] = carrier  # Lambda can extract this
        
        log_with_trace("info", "Invoking Lambda", 
            function_name=function_name,
            event_type=event.get("detail-type")
        )
        
        try:
            resp = _lambda.invoke(
                FunctionName=function_name,
                InvocationType="RequestResponse",
                Payload=json.dumps(event),
            )
            
            payload = json.loads(resp["Payload"].read())
            duration = time.time() - start_time
            
            # Record metrics
            lambda_invocations.add(1, {
                "function_name": function_name,
                "stage": config.STAGE,
            })
            lambda_duration.record(duration, {
                "function_name": function_name,
                "stage": config.STAGE,
            })
            
            # Check for Lambda function errors
            if "FunctionError" in resp:
                error_type = resp.get("FunctionError", "Unknown")
                error_message = payload.get("errorMessage", str(payload))
                
                # Record error span status
                span.set_status(Status(StatusCode.ERROR, error_message))
                span.record_exception(Exception(error_message))
                
                # Record error metric
                lambda_errors.add(1, {
                    "function_name": function_name,
                    "error_type": error_type,
                    "stage": config.STAGE,
                })
                
                log_with_trace("error", "Lambda execution failed",
                    function_name=function_name,
                    error_type=error_type,
                    error_message=error_message,
                    status_code=resp.get("StatusCode"),
                )
                
                raise RuntimeError(
                    f"Lambda '{function_name}' execution failed ({error_type}): {error_message}"
                )
            
            # Success
            span.set_status(Status(StatusCode.OK))
            span.set_attribute("lambda.response.status", payload.get("status", "unknown"))
            
            log_with_trace("info", "Lambda invocation successful",
                function_name=function_name,
                status_code=resp.get("StatusCode"),
                response_status=payload.get("status", "unknown"),
                duration_ms=int(duration * 1000),
            )
            
            return payload
            
        except _lambda.exceptions.ResourceNotFoundException as e:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            
            lambda_errors.add(1, {
                "function_name": function_name,
                "error_type": "ResourceNotFound",
                "stage": config.STAGE,
            })
            
            log_with_trace("error", "Lambda function not found",
                function_name=function_name,
                error=str(e),
            )
            
            raise RuntimeError(
                f"Lambda function '{function_name}' not found. "
                f"Ensure function exists in {config.REGION} for stage {config.STAGE}."
            ) from e
            
        except Exception as e:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            
            lambda_errors.add(1, {
                "function_name": function_name,
                "error_type": type(e).__name__,
                "stage": config.STAGE,
            })
            
            log_with_trace("error", "Lambda invocation failed",
                function_name=function_name,
                error_type=type(e).__name__,
                error=str(e),
            )
            
            raise RuntimeError(
                f"Failed to invoke Lambda '{function_name}': {str(e)}"
            ) from e
```

### 5.3 Test Scenario Tracing (`scenarios/leg_*.py`)

**Pattern**: Each test scenario gets a root span

```python
from lib.observability import tracer, meter, log_with_trace

# Test metrics
test_executions = meter.create_counter("test.executions")
test_failures = meter.create_counter("test.failures")
test_duration = meter.create_histogram("test.duration")

def run() -> dict:
    """Run leg test with distributed tracing."""
    with tracer.start_as_current_span(
        f"test:{NAME}",
        attributes={
            "test.name": NAME,
            "test.type": "leg",
            "test.stage": config.STAGE,
        }
    ) as span:
        start_time = time.time()
        result = {"status": "passed"}
        
        try:
            # Test steps (existing logic)
            _step_1_cleanup()
            _step_2_setup()
            _step_3_invoke()
            _step_4_verify()
            
            # Success
            span.set_status(Status(StatusCode.OK))
            test_executions.add(1, {"test": NAME, "result": "passed"})
            
        except Exception as e:
            # Failure
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            result["status"] = "failed"
            
            test_executions.add(1, {"test": NAME, "result": "failed"})
            test_failures.add(1, {"test": NAME, "error": type(e).__name__})
            
            log_with_trace("error", "Test failed",
                test=NAME,
                error=str(e),
            )
        finally:
            _cleanup()
            duration = time.time() - start_time
            test_duration.record(duration, {"test": NAME})
            span.set_attribute("test.duration_seconds", duration)
        
        return result


def _step_3_invoke():
    """Step 3: Invoke Lambda (sub-span)."""
    with tracer.start_as_current_span("step:invoke_lambda"):
        # Existing invoke logic
        response = eventbridge.invoke_triage(event)
```

### 5.4 Runner Integration (`run.py`)

```python
from lib.observability import tracer, meter, log_with_trace

def main():
    """Run tests with top-level trace."""
    with tracer.start_as_current_span(
        "test_suite",
        attributes={
            "test.suite": "simulation-framework",
            "test.mode": "legs" if run_legs else "e2e",
            "stage": config.STAGE,
        }
    ):
        # Existing test runner logic
        for test in tests:
            result = test.run()  # Each test creates its own span
```

---

## 6. Configuration

### 6.1 Environment Variables

```python
# lib/config.py additions
OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv(
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "http://localhost:4317"  # Local OTLP collector
)
OTEL_EXPORTER_OTLP_HEADERS = os.getenv(
    "OTEL_EXPORTER_OTLP_HEADERS",
    ""  # e.g., "x-honeycomb-team=API_KEY"
)
OTEL_TRACES_ENABLED = os.getenv("OTEL_TRACES_ENABLED", "true").lower() == "true"
OTEL_METRICS_ENABLED = os.getenv("OTEL_METRICS_ENABLED", "true").lower() == "true"
```

### 6.2 Deployment Configuration

**Local Development:**
```bash
# Traces export to local collector or disabled
export OTEL_TRACES_ENABLED=false
python3 run.py
```

**CI/CD:**
```bash
# Traces export to CloudWatch via OTLP
export OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp.us-west-2.amazonaws.com
export OTEL_TRACES_ENABLED=true
python3 run.py
```

---

## 7. Trace Hierarchy

```
test_suite (root span)
├── test:Leg 1: Detection
│   ├── step:cleanup
│   ├── step:setup_alarm
│   ├── step:publish_sns
│   ├── step:verify_ddb
│   └── step:cleanup
├── test:Leg 2: Triage
│   ├── step:cleanup
│   ├── step:seed_ddb
│   ├── step:invoke_lambda
│   │   └── invoke_lambda:incident-triage-dev (CLIENT span)
│   │       └── [Lambda execution span - in Lambda trace]
│   ├── step:verify_response
│   └── step:cleanup
└── test:Leg 3: Escalation
    └── ...
```

---

## 8. Metrics Catalog

| Metric | Type | Description | Labels |
|--------|------|-------------|--------|
| `lambda.invocations` | Counter | Lambda invocation count | `function_name`, `stage` |
| `lambda.errors` | Counter | Lambda invocation errors | `function_name`, `error_type`, `stage` |
| `lambda.duration` | Histogram | Lambda invocation duration (s) | `function_name`, `stage` |
| `test.executions` | Counter | Test execution count | `test`, `result` |
| `test.failures` | Counter | Test failure count | `test`, `error` |
| `test.duration` | Histogram | Test duration (s) | `test` |

---

## 9. Log Structure

**Format**: JSON with trace context

```json
{
  "timestamp": "2026-04-03T10:15:30.123Z",
  "level": "INFO",
  "message": "Lambda invocation successful",
  "trace_id": "5e8c9f2a4b1d3e6f7a8b9c0d1e2f3a4b",
  "span_id": "1a2b3c4d5e6f7a8b",
  "function_name": "incident-triage-dev",
  "status_code": 200,
  "response_status": "auto-resolved",
  "duration_ms": 1234
}
```

---

## 10. Requirements Traceability

| Observability Requirement | Implementation |
|---------------------------|----------------|
| **Structured Logging** | `log_with_trace()` helper with `extra={}` |
| **Trace Context** | `tracer.start_as_current_span()` context managers |
| **Trace Propagation** | `propagate.inject()` into Lambda event |
| **Metrics Collection** | OTel meter with counters/histograms |
| **Error Recording** | `span.record_exception()` + error metrics |
| **No PII** | Only technical fields logged |
| **CloudWatch Export** | OTLP exporter to CloudWatch |

---

## 11. Non-Functional Requirements

| Aspect | Requirement | Design |
|--------|-------------|--------|
| **Performance** | <5% overhead | Async span export, no blocking |
| **Reliability** | Tests work if tracing fails | Graceful degradation if OTLP endpoint unavailable |
| **Debuggability** | Trace test failures | Full trace context in logs and spans |
| **Cost** | Minimal CloudWatch cost | Sampling if needed, metrics aggregation |

---

## 12. Rollout Plan

### Phase 1: Core Instrumentation
- Add `lib/observability.py`
- Instrument `lib/eventbridge.py`
- Update `run.py` for top-level span

### Phase 2: Scenario Instrumentation
- Add tracing to all `scenarios/leg_*.py`
- Add tracing to all `scenarios/*.py` (e2e tests)

### Phase 3: Metrics & Dashboards
- Add CloudWatch dashboard for test metrics
- Add alarms for test failure rate

---

## 13. Verification

### Verification Criteria:
- [ ] All Lambda invocations create spans
- [ ] Trace IDs present in all log entries
- [ ] Traces visible in X-Ray or CloudWatch
- [ ] Metrics exported to CloudWatch
- [ ] Test failures include trace context
- [ ] Trace propagation to Lambda functions

### Test Commands:
```bash
# Local test with tracing
export OTEL_TRACES_ENABLED=true
python3 run.py --leg L2

# Verify trace in CloudWatch
aws xray get-trace-summaries --start-time $(date -u +%s) --end-time $(date -u +%s)
```

---

## 14. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| OTel SDK adds dependencies | MEDIUM | Pin versions, minimal dependencies |
| Tracing overhead slows tests | LOW | Async export, no blocking I/O |
| CloudWatch cost increase | MEDIUM | Sampling, metric aggregation |
| OTLP endpoint unavailable | LOW | Graceful degradation, local fallback |

---

## 15. Alternatives Considered

### Alternative 1: No Observability (Keep Current State)
**Pros**: Simple, no dependencies  
**Cons**: No trace correlation, limited debugging  
**Decision**: REJECTED - Doesn't meet enterprise standards

### Alternative 2: Basic Logging Only
**Pros**: Lightweight, no OTel  
**Cons**: No distributed tracing, no metrics  
**Decision**: REJECTED - Incomplete observability

### Alternative 3: Full ADOT Layer (Lambda-style)
**Pros**: Matches production pattern exactly  
**Cons**: Not possible - ADOT Layer requires Lambda runtime  
**Decision**: REJECTED - Technical limitation

### Alternative 4: OTel SDK with Manual Instrumentation (CHOSEN)
**Pros**: Full observability, trace correlation, metrics  
**Cons**: More complex, additional dependencies  
**Decision**: ACCEPTED - Best balance of observability and feasibility

---

## 16. Dependencies

**New Python Packages:**
```
opentelemetry-api==1.22.0
opentelemetry-sdk==1.22.0
opentelemetry-exporter-otlp==1.22.0
opentelemetry-instrumentation-boto3==0.43b0
```

**AWS Services:**
- CloudWatch (logs, metrics, traces)
- X-Ray (trace visualization)
- OTLP endpoint (if using OTLP collector)

---

## 17. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Trace Coverage | 100% of Lambda invocations | Span count = invocation count |
| Log Correlation | 100% of logs have trace_id | Grep logs for trace_id field |
| Test Failure Debugging Time | <5 min to identify root cause | Time to find failing Lambda from trace |
| Overhead | <5% increase in test duration | Before/after timing comparison |

---

## Approval Checklist

Design reviewer must verify:
- [ ] Follows `patterns/observability-requirements.md`
- [ ] Uses OpenTelemetry SDK (not ADOT Layer - correct for non-Lambda)
- [ ] Implements structured logging with trace context
- [ ] Implements metrics collection
- [ ] Implements distributed tracing
- [ ] Configuration via environment variables
- [ ] No hardcoded credentials
- [ ] Trace propagation to Lambda functions
- [ ] Error handling and span status
- [ ] Graceful degradation if tracing unavailable
