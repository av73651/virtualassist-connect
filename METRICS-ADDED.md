# OpenTelemetry Metrics Implementation

**Date**: 2026-03-27
**Issue**: Missing Metrics in Service Layer
**Severity**: Medium
**Status**: ✅ FIXED

---

## Problem

**Original Issue**:
```
File: src/services/hello_service.py:27-56
Description: The business operation get_hello_message implements tracing
but lacks any OpenTelemetry metrics collection.

Violation: Service operations should include both tracing AND metrics
for complete observability.
```

**Why This Matters**:
- Tracing shows individual request flows (qualitative)
- Metrics show aggregate behavior over time (quantitative)
- Need both for comprehensive observability
- Metrics enable:
  - Rate monitoring (requests per second)
  - Error rate tracking
  - Latency percentiles (p50, p95, p99)
  - Capacity planning
  - Alerting on business KPIs

---

## Solution

Added OpenTelemetry metrics to service layer for complete observability.

### Observability Before (INCOMPLETE ❌)

```python
# Only tracing
@tracer.start_as_current_span("get_hello_message")
def get_hello_message(self) -> HelloMessage:
    # Business logic
    return hello_message
```

**Missing**:
- ❌ No counter for operations
- ❌ No histogram for duration
- ❌ No error rate tracking
- ❌ No business KPI metrics

---

### Observability After (COMPLETE ✅)

```python
# Tracing + Metrics + Logging
@tracer.start_as_current_span("get_hello_message")
def get_hello_message(self) -> HelloMessage:
    # Trace: X-Ray span
    # Metrics: Counter + Histogram
    # Logs: Structured JSON logs
    return hello_message
```

**Now Includes**:
- ✅ Tracing: X-Ray spans for request flow
- ✅ Metrics: Counter for operations
- ✅ Metrics: Histogram for latency
- ✅ Metrics: Status labels (success/error)
- ✅ Logging: Structured logs with duration

---

## Changes Made

### 1. Added OpenTelemetry Meter

```python
from opentelemetry import trace, metrics

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)  # ✅ NEW
```

---

### 2. Defined Service Metrics

```python
class HelloService:
    """Service with OpenTelemetry metrics."""

    # Counter: Tracks total operations
    _messages_generated_counter = meter.create_counter(
        name="hello_messages_generated",
        description="Total number of hello messages generated",
        unit="1"
    )

    # Histogram: Tracks operation latency
    _message_generation_duration = meter.create_histogram(
        name="hello_message_generation_duration",
        description="Duration of hello message generation in milliseconds",
        unit="ms"
    )
```

**Metric Types**:
- **Counter**: Monotonically increasing value (total operations)
- **Histogram**: Distribution of values (latency percentiles)

**Metric Attributes**:
- `name`: Metric identifier
- `description`: Human-readable description
- `unit`: Measurement unit (1, ms, bytes, etc.)

---

### 3. Recorded Metrics on Success

```python
try:
    # Business logic
    hello_message = HelloMessage.create("Hello, World!")
    hello_message.validate()

    # Record success metrics
    duration_ms = (time.time() - start_time) * 1000
    self._messages_generated_counter.add(1, {"status": "success"})
    self._message_generation_duration.record(duration_ms, {"status": "success"})

    return hello_message
```

**Metrics Recorded**:
- Counter: +1 with `status=success` label
- Histogram: Duration in milliseconds with `status=success` label

---

### 4. Recorded Metrics on Error

```python
except Exception as e:
    # Record failure metrics
    duration_ms = (time.time() - start_time) * 1000
    self._messages_generated_counter.add(1, {"status": "error"})
    self._message_generation_duration.record(duration_ms, {"status": "error"})

    logger.error(json.dumps({
        "message": "Failed to generate hello world message",
        "error": str(e),
        "duration_ms": round(duration_ms, 2)
    }))

    raise
```

**Metrics Recorded**:
- Counter: +1 with `status=error` label
- Histogram: Duration in milliseconds with `status=error` label

---

## Metrics Collected

### Metric 1: `hello_messages_generated`

**Type**: Counter
**Description**: Total number of hello messages generated
**Unit**: 1 (count)
**Labels**:
- `status`: "success" or "error"

**Usage**:
```
# Total operations
sum(hello_messages_generated)

# Success rate
sum(hello_messages_generated{status="success"}) / sum(hello_messages_generated)

# Error rate
sum(hello_messages_generated{status="error"}) / sum(hello_messages_generated)

# Operations per second
rate(hello_messages_generated[1m])
```

---

### Metric 2: `hello_message_generation_duration`

**Type**: Histogram
**Description**: Duration of hello message generation
**Unit**: ms (milliseconds)
**Labels**:
- `status`: "success" or "error"

**Usage**:
```
# p50 latency
histogram_quantile(0.5, hello_message_generation_duration)

# p95 latency
histogram_quantile(0.95, hello_message_generation_duration)

# p99 latency
histogram_quantile(0.99, hello_message_generation_duration)

# Average latency
avg(hello_message_generation_duration)

# Max latency
max(hello_message_generation_duration)
```

---

## CloudWatch Metrics Dashboard

These OpenTelemetry metrics are exported to CloudWatch via ADOT layer.

### Dashboard Widgets

**Widget 1: Operations Rate**
```
Metric: hello_messages_generated (sum, rate)
Visualization: Line graph
Period: 1 minute
Statistic: Sum
```

**Widget 2: Success vs Error Rate**
```
Metric: hello_messages_generated (grouped by status)
Visualization: Stacked area chart
Period: 1 minute
Statistic: Sum
Labels: status=success, status=error
```

**Widget 3: Latency Percentiles**
```
Metric: hello_message_generation_duration
Visualization: Line graph
Period: 1 minute
Statistics: p50, p95, p99
```

**Widget 4: Average Latency**
```
Metric: hello_message_generation_duration
Visualization: Single value
Statistic: Average
```

---

## Alerting Examples

### Alert 1: High Error Rate
```yaml
Alarm: HelloService-HighErrorRate
Metric: hello_messages_generated{status="error"}
Threshold: > 5 errors in 5 minutes
Action: SNS notification
```

### Alert 2: High Latency
```yaml
Alarm: HelloService-HighLatency
Metric: hello_message_generation_duration (p99)
Threshold: > 100ms
Duration: 2 consecutive periods
Action: SNS notification
```

### Alert 3: Low Throughput
```yaml
Alarm: HelloService-LowThroughput
Metric: hello_messages_generated (rate)
Threshold: < 1 per minute
Duration: 10 minutes
Action: SNS notification (potential issue)
```

---

## Testing

### New Tests Added

**Test 1**: `test_get_hello_message_records_metrics()`
- Verifies counter incremented with `status=success`
- Verifies histogram recorded with duration
- Validates metric labels

**Test 2**: `test_get_hello_message_records_error_metrics()`
- Simulates error condition
- Verifies counter incremented with `status=error`
- Verifies histogram recorded with error status
- Validates exception is re-raised

**Total Tests**: 39 → **41 tests** (+2 metrics tests)

---

## Observability Stack (Complete)

### 1. Tracing (X-Ray)
- **What**: Request flow, spans, subsegments
- **Use Case**: Debug slow requests, trace errors
- **Tool**: AWS X-Ray
- **Implementation**: `@tracer.start_as_current_span()`

### 2. Metrics (CloudWatch)
- **What**: Aggregate data, rates, percentiles
- **Use Case**: Monitoring, alerting, capacity planning
- **Tool**: CloudWatch Metrics
- **Implementation**: `counter.add()`, `histogram.record()`

### 3. Logging (CloudWatch Logs)
- **What**: Structured event logs
- **Use Case**: Debugging, audit trail
- **Tool**: CloudWatch Logs
- **Implementation**: `logger.info(json.dumps({...}))`

---

## Benefits

### 1. Complete Observability
- **Tracing**: Individual request visibility
- **Metrics**: Aggregate behavior over time
- **Logging**: Detailed event information

### 2. Proactive Monitoring
- Alert on error rate spikes
- Alert on latency degradation
- Detect anomalies before users complain

### 3. Capacity Planning
- Understand request rates
- Predict resource needs
- Optimize performance

### 4. Business Insights
- Track operations per second
- Measure success/error rates
- Monitor business KPIs

### 5. SLA Compliance
- Track p95, p99 latency
- Monitor uptime
- Report on SLOs

---

## Metrics Best Practices Applied

### ✅ Bounded Metrics
- Counter: Monotonically increasing (safe)
- Histogram: Bounded buckets (safe)
- No unbounded metrics (e.g., gauge with high cardinality)

### ✅ Meaningful Labels
- `status`: Distinguishes success vs error
- Limited cardinality (2 values only)
- No high-cardinality labels (e.g., user_id, trace_id)

### ✅ Descriptive Names
- Prefix: `hello_` (service namespace)
- Suffix: Units implied (`_duration` → time, `_generated` → count)
- Clear descriptions

### ✅ Appropriate Units
- Counter: "1" (count)
- Histogram: "ms" (milliseconds)
- Explicit unit declarations

### ✅ Error Recording
- Separate `status=error` label
- Errors counted in same metric (not separate metric)
- Enables error rate calculation

---

## Validation

### Before Fix
```
Observability: Tracing only ❌
- ✅ X-Ray traces
- ❌ No metrics
- ✅ Logs
```

### After Fix
```
Observability: Complete ✅
- ✅ X-Ray traces
- ✅ OpenTelemetry metrics (counter + histogram)
- ✅ Structured logs with duration
```

---

## Implementation Checklist

- ✅ Imported `metrics` from OpenTelemetry
- ✅ Initialized meter with `metrics.get_meter(__name__)`
- ✅ Created counter metric (`hello_messages_generated`)
- ✅ Created histogram metric (`hello_message_generation_duration`)
- ✅ Recorded metrics on success path
- ✅ Recorded metrics on error path
- ✅ Added meaningful labels (`status`)
- ✅ Recorded duration in milliseconds
- ✅ Added tests for metrics recording
- ✅ Added tests for error metrics
- ✅ Documented metrics in code comments
- ✅ Documented alerting strategies

---

## Summary

**Issue**: Missing OpenTelemetry metrics ✅ FIXED
**Files Changed**: 1 file (hello_service.py)
**Tests Added**: 2 tests (metrics recording)
**Total Tests**: 41 tests

**Metrics Added**:
1. `hello_messages_generated` (counter)
2. `hello_message_generation_duration` (histogram)

**Labels**: `status` (success/error)

**Observability**: Now complete (tracing + metrics + logging)

**Compliance**: Follows OpenTelemetry best practices
- Bounded metrics
- Meaningful labels
- Low cardinality
- Appropriate units
- Error tracking
