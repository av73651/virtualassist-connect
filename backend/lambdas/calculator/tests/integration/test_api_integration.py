"""Integration tests for Calculator API.

These tests require a deployed API and validate end-to-end functionality,
response headers, CORS configuration, and error handling.

Note: These tests hit real deployed infrastructure and require API_ENDPOINT
environment variable to be set.
"""

import pytest
import requests
import json
from datetime import datetime


@pytest.fixture
def api_base():
    """API base URL from environment variable.

    Returns:
        str: API base URL for /calculator

    Raises:
        pytest.skip: If API_ENDPOINT not set
    """
    import os
    endpoint = os.getenv("API_ENDPOINT")
    if not endpoint:
        pytest.skip("API_ENDPOINT not set - integration tests require deployed API")
    return endpoint.rstrip('/') + '/calculator'


@pytest.fixture
def api_endpoint(api_base):
    """API endpoint URL for /calculator/add (backward compatible).

    Returns:
        str: API endpoint URL for /calculator/add
    """
    return api_base + '/add'


# ============================================================================
# API Endpoint Tests
# ============================================================================

@pytest.mark.integration
def test_calculator_add_end_to_end(api_endpoint):
    """Test complete API Gateway -> Lambda -> Response flow for addition (AC-001 to AC-004)."""
    # Arrange
    payload = {"a": 5.5, "b": 3.2}

    # Act
    response = requests.post(api_endpoint, json=payload)

    # AC-001: Returns HTTP 200
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    # AC-002: Response is valid JSON
    try:
        body = response.json()
    except json.JSONDecodeError:
        pytest.fail("Response body is not valid JSON")

    # AC-003: Contains expected calculation fields
    assert "a" in body, "Response missing 'a' field"
    assert "b" in body, "Response missing 'b' field"
    assert "operation" in body, "Response missing 'operation' field"
    assert "result" in body, "Response missing 'result' field"
    assert "timestamp" in body, "Response missing 'timestamp' field"

    # AC-004: Verify calculation result
    assert body["a"] == 5.5, f"Expected a=5.5, got {body['a']}"
    assert body["b"] == 3.2, f"Expected b=3.2, got {body['b']}"
    assert body["operation"] == "add", f"Expected operation='add', got '{body['operation']}'"
    assert body["result"] == 8.7, f"Expected result=8.7, got {body['result']}"

    # Verify timestamp format (ISO 8601 UTC)
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
def test_calculator_add_with_negative_numbers(api_endpoint):
    """Test addition with negative operands."""
    # Arrange
    payload = {"a": -10.0, "b": -5.5}

    # Act
    response = requests.post(api_endpoint, json=payload)

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["result"] == -15.5


@pytest.mark.integration
def test_calculator_add_with_zero(api_endpoint):
    """Test addition with zero operands."""
    # Arrange
    payload = {"a": 0, "b": 0}

    # Act
    response = requests.post(api_endpoint, json=payload)

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["result"] == 0.0


# ============================================================================
# Response Header Tests
# ============================================================================

@pytest.mark.integration
def test_calculator_response_headers(api_endpoint):
    """Test response includes required headers."""
    # Arrange
    payload = {"a": 1, "b": 2}

    # Act
    response = requests.post(api_endpoint, json=payload)

    # Assert
    assert response.status_code == 200

    # Content-Type header
    assert "Content-Type" in response.headers
    assert "application/json" in response.headers["Content-Type"]

    # Trace ID header
    assert "X-Trace-Id" in response.headers or "x-trace-id" in response.headers
    trace_id = response.headers.get('X-Trace-Id', response.headers.get('x-trace-id'))
    print(f"Trace ID: {trace_id}")


# ============================================================================
# CORS Tests
# ============================================================================

@pytest.mark.integration
def test_calculator_cors_headers(api_endpoint):
    """Test CORS headers are present."""
    # Act - OPTIONS preflight request
    response = requests.options(api_endpoint)

    # Assert - CORS headers
    assert "Access-Control-Allow-Origin" in response.headers
    assert "Access-Control-Allow-Methods" in response.headers


# ============================================================================
# Error Handling Tests
# ============================================================================

@pytest.mark.integration
def test_calculator_invalid_method(api_endpoint):
    """Test API returns error for unsupported HTTP methods (AC-002)."""
    # Act - GET is not supported for /calculator/add
    response = requests.get(api_endpoint)

    # Assert
    assert response.status_code in [403, 405], f"Expected 403/405 for GET, got {response.status_code}"


@pytest.mark.integration
def test_calculator_invalid_path(api_endpoint):
    """Test API returns error for invalid paths."""
    # Arrange
    base_url = api_endpoint.replace('/calculator/add', '')

    # Act
    response = requests.get(f"{base_url}/invalid-path")

    # Assert
    assert response.status_code in [403, 404], f"Expected 403/404, got {response.status_code}"


@pytest.mark.integration
def test_calculator_invalid_body(api_endpoint):
    """Test API returns error for invalid request body (AC-003)."""
    # Arrange - non-numeric values
    payload = {"a": "not_a_number", "b": 3.2}

    # Act
    response = requests.post(api_endpoint, json=payload)

    # Assert
    assert response.status_code == 400, f"Expected 400, got {response.status_code}"

    body = response.json()
    assert "errorCode" in body, "Error response missing 'errorCode' field"
    assert body["errorCode"] == "VALIDATION_ERROR"


@pytest.mark.integration
def test_calculator_missing_fields(api_endpoint):
    """Test API returns error for missing required fields (AC-003)."""
    # Arrange - missing 'b' field
    payload = {"a": 5.5}

    # Act
    response = requests.post(api_endpoint, json=payload)

    # Assert
    assert response.status_code == 400, f"Expected 400, got {response.status_code}"

    body = response.json()
    assert "errorCode" in body
    assert body["errorCode"] == "VALIDATION_ERROR"


@pytest.mark.integration
def test_calculator_empty_body(api_endpoint):
    """Test API returns error for empty request body (AC-003)."""
    # Act
    response = requests.post(
        api_endpoint,
        data="",
        headers={"Content-Type": "application/json"}
    )

    # Assert
    assert response.status_code == 400, f"Expected 400, got {response.status_code}"


# ============================================================================
# Subtraction Endpoint Tests (FR-005)
# ============================================================================

@pytest.mark.integration
def test_calculator_subtract_end_to_end(api_base):
    """Test POST /calculator/subtract returns correct difference."""
    payload = {"a": 10, "b": 3}
    response = requests.post(f"{api_base}/subtract", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["operation"] == "subtract"
    assert body["result"] == 7
    assert body["a"] == 10
    assert body["b"] == 3


@pytest.mark.integration
def test_calculator_subtract_negative_result(api_base):
    """Test subtraction producing negative result."""
    payload = {"a": 3, "b": 10}
    response = requests.post(f"{api_base}/subtract", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["result"] == -7


@pytest.mark.integration
def test_calculator_subtract_invalid_body(api_base):
    """Test subtract returns 400 for invalid input."""
    payload = {"a": "text", "b": 3}
    response = requests.post(f"{api_base}/subtract", json=payload)

    assert response.status_code == 400
    body = response.json()
    assert body["errorCode"] == "VALIDATION_ERROR"


# ============================================================================
# Multiplication Endpoint Tests (FR-006)
# ============================================================================

@pytest.mark.integration
def test_calculator_multiply_end_to_end(api_base):
    """Test POST /calculator/multiply returns correct product."""
    payload = {"a": 4, "b": 5}
    response = requests.post(f"{api_base}/multiply", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["operation"] == "multiply"
    assert body["result"] == 20
    assert body["a"] == 4
    assert body["b"] == 5


@pytest.mark.integration
def test_calculator_multiply_by_zero(api_base):
    """Test multiplication by zero returns zero."""
    payload = {"a": 100, "b": 0}
    response = requests.post(f"{api_base}/multiply", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["result"] == 0


@pytest.mark.integration
def test_calculator_multiply_invalid_body(api_base):
    """Test multiply returns 400 for invalid input."""
    payload = {"a": 5}
    response = requests.post(f"{api_base}/multiply", json=payload)

    assert response.status_code == 400


# ============================================================================
# Division Endpoint Tests (FR-007)
# ============================================================================

@pytest.mark.integration
def test_calculator_divide_end_to_end(api_base):
    """Test POST /calculator/divide returns correct quotient."""
    payload = {"a": 10, "b": 2}
    response = requests.post(f"{api_base}/divide", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["operation"] == "divide"
    assert body["result"] == 5.0
    assert body["a"] == 10
    assert body["b"] == 2


@pytest.mark.integration
def test_calculator_divide_by_zero_returns_400(api_base):
    """Test division by zero returns 400 with DIVISION_BY_ZERO error (AC-028)."""
    payload = {"a": 10, "b": 0}
    response = requests.post(f"{api_base}/divide", json=payload)

    assert response.status_code == 400
    body = response.json()
    assert body["errorCode"] == "DIVISION_BY_ZERO"
    assert "correlationId" in body
    assert "timestamp" in body


@pytest.mark.integration
def test_calculator_divide_invalid_body(api_base):
    """Test divide returns 400 for null operand."""
    payload = {"a": None, "b": 3}
    response = requests.post(f"{api_base}/divide", json=payload)

    assert response.status_code == 400
