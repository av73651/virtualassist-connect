# OpenTelemetry Template

## Purpose

This pattern defines the **mandatory observability instrumentation** for all AWS Lambda functions using native **OpenTelemetry (OTel)** with the AWS Distro for OpenTelemetry (ADOT).

## When to Use

**MANDATORY** for ALL Lambda handler functions in the project to ensure vendor-neutral, distributed tracing, and metrics collection.

## Template

### Python Lambda Handler with OpenTelemetry

```python
import json
import logging
from opentelemetry import trace, metrics
from opentelemetry.trace.status import Status, StatusCode

# 1. Initialize standard Python structured logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# 2. Acquire standard OTel Tracer and Meter
tracer = trace.get_tracer(__name__)
meter = metrics.get_meter("VirtualAssist.UserAPI")

# 3. Create Meters proactively
request_counter = meter.create_counter(
    "request_received", 
    description="Number of API requests received"
)

def lambda_handler(event, context):
    """
    Lambda handler with OpenTelemetry observability.
    
    Note: ADOT Lambda layer automatically traces the Lambda invocation. 
    We only need to manually trace inner business logic.
    """
    
    # Extract trace context for logging correlation
    current_span = trace.get_current_span()
    trace_id = format(current_span.get_span_context().trace_id, '032x')
    
    logger.info(
        json.dumps({
            "message": "Processing request",
            "event_type": event.get("type"),
            "trace_id": trace_id
        })
    )

    request_counter.add(1, {"environment": "prod"})

    # Manually trace business logic
    with tracer.start_as_current_span("business_logic") as span:
        try:
            result = process_request(event)
            span.set_status(Status(StatusCode.OK))
        except Exception as e:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            logger.error("Request failed", extra={"error": str(e), "trace_id": trace_id})
            raise e

    logger.info("Request succeeded", extra={"trace_id": trace_id})
    return result

def process_request(event):
    """Business logic"""
    return {"statusCode": 200, "body": "Success"}
```

## Required Components

### 1. Tracing (AWS Distro for OpenTelemetry)
AWS handles the root Lambda invocation trace. You only need to trace custom logic.
```python
tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("database_call") as span:
    span.set_attribute("db.table", "Users")
    db.query()
```

### 2. Logging (Standard JSON Logging)
Since OTel manages traces, we use Python's built-in `logging` module, formatting everything as JSON and explicitly injecting the `trace_id` for correlation.

### 3. Metrics (OTel API)
Synchronous counters and histograms for business instrumentation.
```python
meter = metrics.get_meter(__name__)
counter = meter.create_counter("item_created")
counter.add(1, {"item_type": "premium"})
```

## CDK Configuration

To enable OpenTelemetry in AWS CDK, you MUST attach the ADOT Lambda Layer to the function and set the appropriate environment variables to enable auto-instrumentation.

```python
from aws_cdk import Stack, aws_lambda as lambda_

# MANDATORY: Do NOT hardcode the region in ADOT ARN.
# Use Stack.of(self).region to avoid cross-region 403 authorization failures.
adot_layer_arn = (
    f"arn:aws:lambda:{Stack.of(self).region}:901920570463"
    ":layer:aws-otel-python-amd64-ver-1-20-0:1"
)

function = lambda_.Function(
    self, 'Function',
    runtime=lambda_.Runtime.PYTHON_3_12,
    handler='handler.lambda_handler',
    code=lambda_.Code.from_asset('path/to/code'),
    layers=[
        lambda_.LayerVersion.from_layer_version_arn(self, "AdotLayer", adot_layer_arn)
    ],
    environment={
        'AWS_LAMBDA_EXEC_WRAPPER': '/opt/otel-instrument',
        'OTEL_SERVICE_NAME': 'user-service',
        'OTEL_PROPAGATORS': 'tracecontext,baggage,xray',
        'OPENTELEMETRY_COLLECTOR_CONFIG_FILE': '/var/task/collector.yaml'
    },
    tracing=lambda_.Tracing.ACTIVE  # Must be enabled for X-Ray
)
```

## Dependencies

Add to `requirements.txt`:
```
opentelemetry-api
opentelemetry-sdk
```
*Note: The actual exporter and instrumentation libraries are provided by the ADOT Lambda layer globally, preventing bundle bloat.*

## References
- **Enforced by**: `code-review.md` (Observability validation)
- **Used in Skills**: `code-generation.md`, `technology-standards.md`
