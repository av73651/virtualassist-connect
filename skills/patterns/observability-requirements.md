# Observability Requirements Pattern

## Purpose

This pattern defines **mandatory observability requirements** for all services using native **OpenTelemetry (ADOT)** to ensure monitoring, debugging, and operational excellence without heavy vendor-locked decorators.

## Three Pillars of Observability

1. **Logging**: Structured JSON logs for event tracking, enriched with Trace IDs
2. **Metrics**: Quantitative measurements via OpenTelemetry Metrics SDK
3. **Tracing**: Distributed request tracking (W3C standard)

---

## 1. LOGGING

### Required: Structured JSON Logging

ALL services MUST use standard Python `logging` formatted explicitly as JSON strings, with the current Trace ID injected.

**Configuration**:
```python
import logging
import json
from opentelemetry import trace

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
```

**Usage**:
```python
# Use extra={} for structured fields — NOT json.dumps()
span = trace.get_current_span()
trace_id = format(span.get_span_context().trace_id, '032x') if span else "none"

logger.info("User created successfully", extra={
    "trace_id": trace_id,
    "user_id": "user-123",
    "action": "user_creation"
})

logger.error("Operation failed", extra={
    "trace_id": trace_id,
    "error": str(e),
    "action": "user_creation"
})
```

### Log Levels
- **INFO**: Normal operations (User created, request processed)
- **ERROR**: Failures (Validation failed, service unavailable)

### Incident Debugging Context

The `@api_gateway_handler` middleware automatically enriches logs with:

- **`user_id`**: Cognito `sub` claim from JWT (all log entries — request, success, error)
- **`request_body`**: Raw request body (error log entries only — not on success to reduce noise)

These fields enable filtering by affected user and inspecting the payload that caused failures.

```python
# Automatically available in CloudWatch logs:
# - "user_id": "cognito-sub-uuid" (or "anonymous" if unauthenticated)
# - "request_body": "{\"a\": \"bad\"}" (on errors only)
```

#### DON'T: Log PII
Never log passwords, Social Security Numbers, or credit card info. Request bodies are logged on error only and must not contain sensitive fields. If a service handles PII in request bodies, override this behavior by sanitizing before logging.

---

## 2. METRICS

### Required: OpenTelemetry Metrics

ALL services MUST emit custom metrics via the OTel SDK API. ADOT exports them to CloudWatch.

**Configuration**:
```python
from opentelemetry import metrics

meter = metrics.get_meter("VirtualAssist.UserService")
user_created_counter = meter.create_counter(
    "user_created",
    description="Number of users created"
)
```

**Usage**:
```python
user_created_counter.add(1, {"environment": "prod", "role": "admin"})
```

---

## 3. TRACING

### Required: AWS Distro for OpenTelemetry (ADOT)

ALL Lambda functions MUST use the ADOT layer. The handler invocation is automatically traced by the ADOT wrapper script. Inside your code, you MUST trace sub-operations.

**Configuration**:
```python
from opentelemetry import trace
from opentelemetry.trace.status import Status, StatusCode

tracer = trace.get_tracer(__name__)
```

### Method Tracing (Context Manager)

Substitute decorators with the explicit `start_as_current_span` context block.

```python
def process_data(data):
    with tracer.start_as_current_span("process_data") as span:
        try:
            span.set_attribute("data.size", len(data))
            result = transform(data)
            span.set_status(Status(StatusCode.OK))
            return result
        except Exception as e:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            raise
```

---

## 4. CORRELATION ID PROPAGATION

### Purpose
Correlation IDs (Trace IDs) link logs, metrics, and traces across distributed services. OpenTelemetry uses the standard `traceparent` (W3C) headers.

This is automatically handled by the ADOT layer across API Gateway, EventBridge, and SQS if `OTEL_PROPAGATORS=tracecontext` is set in the environment variables.

To manually extract the Trace ID for logging:
```python
span = trace.get_current_span()
trace_id = format(span.get_span_context().trace_id, '032x')
```

---

## 5. CLOUDWATCH CONFIGURATION

CloudWatch is the backend store for the telemetry signals managed by AWS CDK.

```python
from aws_cdk import aws_logs as logs

log_group = logs.LogGroup(
    self, 'LogGroup',
    log_group_name=f'/aws/lambda/{function_name}',
    retention=logs.RetentionDays.ONE_WEEK,
    removal_policy=RemovalPolicy.DESTROY
)
```

---

## 6. VERIFICATION CHECKLIST

Before deploying:

- [ ] ADOT Lambda Layer attached via CDK
- [ ] `AWS_LAMBDA_EXEC_WRAPPER=/opt/otel-instrument` set in environment
- [ ] Manual logging implemented purely via JSON serialization
- [ ] No PII in logs
- [ ] Standard OTel `trace.get_tracer(__name__)` used
- [ ] `opentelemetry-api` in `requirements.txt`
