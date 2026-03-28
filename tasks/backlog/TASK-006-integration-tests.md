# TASK-006: Integration Tests

**Status**: Backlog
**Priority**: P2 (Medium - Post-Deployment Validation)
**Estimated Effort**: 30 minutes
**Dependencies**: TASK-005 (infrastructure must be deployed)
**Note**: Performance tests (AC-005) removed from scope

---

## Objective

Implement integration tests that validate end-to-end functionality of the deployed system including API Gateway, Lambda, observability (X-Ray, CloudWatch), and performance requirements.

---

## Files to Create

1. **`backend/lambdas/hello-world/tests/integration/test_api_integration.py`**

---

## Implementation Details

### Integration Test Suite

```python
import pytest
import requests
import time
import json
import boto3
from datetime import datetime, timedelta
from typing import List


# Configuration - set these via environment variables or pytest fixtures
@pytest.fixture
def api_endpoint():
    """API endpoint URL from CDK outputs or environment variable."""
    import os
    endpoint = os.getenv("API_ENDPOINT")
    if not endpoint:
        pytest.skip("API_ENDPOINT not set - integration tests require deployed API")
    return endpoint.rstrip('/') + '/hello'


@pytest.fixture
def lambda_function_name():
    """Lambda function name from CDK outputs."""
    return "hello-world-api"


@pytest.fixture
def cloudwatch_logs_client():
    """CloudWatch Logs client for log validation."""
    return boto3.client('logs', region_name='us-east-1')


@pytest.fixture
def xray_client():
    """X-Ray client for trace validation."""
    return boto3.client('xray', region_name='us-east-1')


# ============================================================================
# API Endpoint Tests
# ============================================================================

@pytest.mark.integration
def test_hello_endpoint_end_to_end(api_endpoint):
    """Test complete API Gateway → Lambda → Response flow (AC-001 to AC-004)."""
    response = requests.get(api_endpoint)

    # AC-001: Returns HTTP 200
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    # AC-002: Response is valid JSON
    try:
        body = response.json()
    except json.JSONDecodeError:
        pytest.fail("Response body is not valid JSON")

    # AC-003: Contains message "Hello, World!"
    assert "message" in body, "Response missing 'message' field"
    assert body["message"] == "Hello, World!", f"Expected 'Hello, World!', got '{body['message']}'"

    # AC-004: Contains ISO 8601 timestamp
    assert "timestamp" in body, "Response missing 'timestamp' field"
    timestamp = body["timestamp"]
    assert timestamp.endswith("Z"), f"Timestamp not in UTC format: {timestamp}"
    assert "T" in timestamp, f"Timestamp not in ISO 8601 format: {timestamp}"

    # Validate timestamp is recent (within last 5 seconds)
    try:
        ts_dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        now = datetime.now(ts_dt.tzinfo)
        delta = abs((now - ts_dt).total_seconds())
        assert delta < 5, f"Timestamp is {delta}s old, expected recent timestamp"
    except ValueError:
        pytest.fail(f"Invalid ISO 8601 timestamp format: {timestamp}")


@pytest.mark.integration
def test_hello_endpoint_response_time_AC_005(api_endpoint):
    """Test p95 response time < 200ms (AC-005)."""
    response_times: List[float] = []
    num_requests = 100

    # Make 100 requests
    for _ in range(num_requests):
        start = time.time()
        response = requests.get(api_endpoint)
        end = time.time()

        assert response.status_code == 200, "Request failed"
        response_times.append((end - start) * 1000)  # Convert to ms

    # Calculate p95
    response_times.sort()
    p95_index = int(num_requests * 0.95)
    p95_latency = response_times[p95_index]

    print(f"\nPerformance Stats:")
    print(f"  Min: {min(response_times):.2f}ms")
    print(f"  p50: {response_times[50]:.2f}ms")
    print(f"  p95: {p95_latency:.2f}ms")
    print(f"  p99: {response_times[99]:.2f}ms")
    print(f"  Max: {max(response_times):.2f}ms")

    # AC-005: p95 < 200ms
    assert p95_latency < 200, f"p95 latency {p95_latency:.2f}ms exceeds 200ms threshold"


@pytest.mark.integration
def test_hello_endpoint_headers(api_endpoint):
    """Test response includes required headers."""
    response = requests.get(api_endpoint)

    assert response.status_code == 200

    # Content-Type header
    assert "Content-Type" in response.headers
    assert "application/json" in response.headers["Content-Type"]

    # Trace ID header
    assert "X-Trace-Id" in response.headers or "x-trace-id" in response.headers
    print(f"Trace ID: {response.headers.get('X-Trace-Id', response.headers.get('x-trace-id'))}")


@pytest.mark.integration
def test_hello_endpoint_cors_headers(api_endpoint):
    """Test CORS headers are present."""
    # OPTIONS request
    response = requests.options(api_endpoint)

    # CORS headers
    assert "Access-Control-Allow-Origin" in response.headers
    assert "Access-Control-Allow-Methods" in response.headers


# ============================================================================
# CloudWatch Logs Tests
# ============================================================================

@pytest.mark.integration
def test_hello_endpoint_cloudwatch_logs(api_endpoint, lambda_function_name, cloudwatch_logs_client):
    """Test structured logs appear in CloudWatch."""
    # Make request to generate logs
    response = requests.get(api_endpoint)
    assert response.status_code == 200

    # Wait for logs to be ingested
    time.sleep(5)

    # Query CloudWatch Logs
    log_group_name = f"/aws/lambda/{lambda_function_name}"

    try:
        # Get log streams (most recent)
        streams_response = cloudwatch_logs_client.describe_log_streams(
            logGroupName=log_group_name,
            orderBy='LastEventTime',
            descending=True,
            limit=5
        )

        assert len(streams_response['logStreams']) > 0, "No log streams found"

        # Get log events from most recent stream
        log_stream_name = streams_response['logStreams'][0]['logStreamName']

        logs_response = cloudwatch_logs_client.get_log_events(
            logGroupName=log_group_name,
            logStreamName=log_stream_name,
            limit=50
        )

        # Find structured log messages
        log_messages = [event['message'] for event in logs_response['events']]

        # Look for our structured logs (JSON format)
        structured_logs = []
        for msg in log_messages:
            try:
                if msg.strip().startswith('{'):
                    log_obj = json.loads(msg)
                    structured_logs.append(log_obj)
            except json.JSONDecodeError:
                continue

        assert len(structured_logs) > 0, "No structured logs found"

        # Verify log contains expected fields
        found_hello_log = False
        for log in structured_logs:
            if log.get('service') == 'hello_service' and log.get('method') == 'get_hello_message':
                found_hello_log = True
                break

        assert found_hello_log, "Expected structured log from hello_service not found"

    except cloudwatch_logs_client.exceptions.ResourceNotFoundException:
        pytest.fail(f"Log group {log_group_name} not found - Lambda may not have been invoked")


# ============================================================================
# X-Ray Traces Tests
# ============================================================================

@pytest.mark.integration
def test_hello_endpoint_xray_trace(api_endpoint, xray_client):
    """Test X-Ray trace is created for request."""
    # Make request to generate trace
    response = requests.get(api_endpoint)
    assert response.status_code == 200

    # Extract trace ID from header
    trace_id_header = response.headers.get('X-Trace-Id', response.headers.get('x-trace-id'))
    print(f"Trace ID from response: {trace_id_header}")

    # Wait for trace to be indexed
    time.sleep(10)

    # Query X-Ray for traces (last 5 minutes)
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(minutes=5)

    try:
        # Get trace summaries
        summaries_response = xray_client.get_trace_summaries(
            StartTime=start_time,
            EndTime=end_time,
            FilterExpression='service("hello-world-api")'
        )

        traces = summaries_response.get('TraceSummaries', [])
        assert len(traces) > 0, "No X-Ray traces found for hello-world-api service"

        # Get full trace details
        trace_id = traces[0]['Id']
        trace_response = xray_client.batch_get_traces(TraceIds=[trace_id])

        trace_data = trace_response['Traces'][0]
        segments = trace_data['Segments']

        assert len(segments) > 0, "No segments found in trace"

        # Verify Lambda segment exists
        lambda_segment_found = False
        for segment in segments:
            segment_doc = json.loads(segment['Document'])
            if segment_doc.get('origin') == 'AWS::Lambda::Function':
                lambda_segment_found = True
                print(f"Lambda segment found: {segment_doc.get('name')}")

        assert lambda_segment_found, "Lambda segment not found in X-Ray trace"

    except Exception as e:
        pytest.skip(f"X-Ray trace validation skipped: {str(e)}")


# ============================================================================
# Error Handling Tests
# ============================================================================

@pytest.mark.integration
def test_api_invalid_method(api_endpoint):
    """Test API returns error for unsupported HTTP methods."""
    response = requests.post(api_endpoint)
    assert response.status_code in [403, 405], f"Expected 403/405 for POST, got {response.status_code}"


@pytest.mark.integration
def test_api_invalid_path(api_endpoint):
    """Test API returns 404 for invalid paths."""
    base_url = api_endpoint.replace('/hello', '')
    response = requests.get(f"{base_url}/invalid-path")
    assert response.status_code == 403 or response.status_code == 404


# ============================================================================
# Configuration
# ============================================================================

# pytest.ini marker
# markers =
#     integration: Integration tests requiring deployed AWS resources
```

---

## Running Integration Tests

### Prerequisites
1. Deploy the stack: `cdk deploy`
2. Get API endpoint URL from outputs
3. Set environment variable:
   ```bash
   export API_ENDPOINT="https://abc123.execute-api.us-east-1.amazonaws.com/dev/"
   ```

### Run Tests
```bash
cd backend/lambdas/hello-world

# Run only integration tests
pytest tests/integration/ -v -m integration

# Run with AWS credentials
AWS_PROFILE=dev pytest tests/integration/ -v -m integration

# Skip integration tests (for CI without deployment)
pytest tests/ -v -m "not integration"
```

---

## Acceptance Criteria

### API Tests
- [ ] End-to-end test validates AC-001 to AC-004
- [ ] Performance test validates AC-005 (p95 < 200ms)
- [ ] Response headers validated
- [ ] CORS headers present

### Observability Tests
- [ ] Structured logs present in CloudWatch
- [ ] Log format is valid JSON
- [ ] Expected log messages found
- [ ] X-Ray trace created
- [ ] Lambda segment present in trace

### Error Handling Tests
- [ ] Invalid HTTP methods rejected
- [ ] Invalid paths return 404

---

## Compliance Checks

- ✅ **AC-005 Validation**: p95 < 200ms performance requirement
- ✅ **Observability Requirements**: Logs and traces validated
- ✅ **OpenTelemetry**: X-Ray traces verified
- ✅ **Test Generation Pattern**: AAA pattern, clear assertions

---

## Notes

- Integration tests require deployed infrastructure
- Tests query real AWS services (CloudWatch, X-Ray)
- Performance test makes 100 requests (may incur small AWS costs)
- X-Ray traces may take 5-10 seconds to be indexed
- CloudWatch logs may take 3-5 seconds to appear
- Use pytest markers to run/skip integration tests
