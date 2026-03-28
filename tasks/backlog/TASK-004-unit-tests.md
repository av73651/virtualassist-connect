# TASK-004: Unit Tests Implementation

**Status**: Backlog
**Priority**: P0 (Critical - Quality Gate)
**Estimated Effort**: 60 minutes
**Dependencies**: TASK-001, TASK-002, TASK-003 (all core components)

---

## Objective

Implement comprehensive unit tests for all core components (DTO, Service, Handler) with ≥80% code coverage. Tests must map to acceptance criteria and validate business rules.

---

## Files to Create

1. **`backend/lambdas/hello-world/tests/conftest.py`** - Shared fixtures
2. **`backend/lambdas/hello-world/tests/unit/test_response_dto.py`** - DTO tests
3. **`backend/lambdas/hello-world/tests/unit/test_hello_service.py`** - Service tests
4. **`backend/lambdas/hello-world/tests/unit/test_hello_handler.py`** - Handler tests

---

## Implementation Details

### 1. Shared Fixtures (`tests/conftest.py`)

```python
import pytest
from unittest.mock import Mock
from datetime import datetime
from src.services.hello_service import HelloService
from src.dto.response import HelloResponse


@pytest.fixture
def mock_hello_service():
    """Mock HelloService for handler tests."""
    service = Mock(spec=HelloService)
    service.get_hello_message.return_value = HelloResponse(
        message="Hello, World!",
        timestamp="2026-03-27T10:00:00.000Z"
    )
    return service


@pytest.fixture
def fixed_datetime():
    """Fixed datetime for deterministic tests."""
    return datetime(2026, 3, 27, 10, 0, 0)


@pytest.fixture
def api_gateway_event():
    """API Gateway proxy event structure."""
    return {
        'resource': '/hello',
        'httpMethod': 'GET',
        'headers': {
            'Content-Type': 'application/json'
        },
        'requestContext': {
            'requestId': 'test-request-id'
        }
    }


@pytest.fixture
def lambda_context():
    """Mock Lambda context."""
    context = Mock()
    context.function_name = 'hello-world-function'
    context.request_id = 'test-request-id'
    return context
```

---

### 2. DTO Tests (`tests/unit/test_response_dto.py`)

```python
import pytest
from datetime import datetime
from src.dto.response import HelloResponse, ErrorResponse


def test_hello_response_creation():
    """Test HelloResponse DTO creation with direct instantiation."""
    response = HelloResponse(message="Test", timestamp="2026-03-27T10:00:00.000Z")
    assert response.message == "Test"
    assert response.timestamp == "2026-03-27T10:00:00.000Z"


def test_hello_response_factory_method():
    """Test HelloResponse factory method with datetime object."""
    dt = datetime(2026, 3, 27, 10, 0, 0)
    response = HelloResponse.create("Hello, World!", dt)
    assert response.message == "Hello, World!"
    assert response.timestamp == "2026-03-27T10:00:00.000000Z"


def test_hello_response_to_dict():
    """Test HelloResponse to_dict() serialization."""
    response = HelloResponse(message="Test", timestamp="2026-03-27T10:00:00.000Z")
    result = response.to_dict()
    assert result == {"message": "Test", "timestamp": "2026-03-27T10:00:00.000Z"}


def test_hello_response_pydantic_validation():
    """Test Pydantic validation rejects missing fields."""
    with pytest.raises(Exception):
        HelloResponse(message="Test")  # Missing timestamp


def test_error_response_creation():
    """Test ErrorResponse DTO creation."""
    error = ErrorResponse(
        errorCode="TEST_ERROR",
        message="Test message",
        correlationId="123",
        timestamp="2026-03-27T10:00:00.000Z"
    )
    assert error.errorCode == "TEST_ERROR"
    assert error.correlationId == "123"


def test_error_response_factory_method():
    """Test ErrorResponse factory method for internal errors."""
    error = ErrorResponse.create_internal_error("trace-123")
    assert error.errorCode == "INTERNAL_ERROR"
    assert error.message == "An internal error occurred"
    assert error.correlationId == "trace-123"
    assert len(error.timestamp) > 0


def test_error_response_to_dict():
    """Test ErrorResponse to_dict() serialization."""
    error = ErrorResponse(
        errorCode="TEST",
        message="Test",
        correlationId="123",
        timestamp="2026-03-27T10:00:00.000Z"
    )
    result = error.to_dict()
    assert result["errorCode"] == "TEST"
    assert result["correlationId"] == "123"
```

---

### 3. Service Tests (`tests/unit/test_hello_service.py`)

```python
import pytest
from datetime import datetime
from unittest.mock import patch, Mock
from src.services.hello_service import HelloService
from src.dto.response import HelloResponse


def test_get_hello_message_returns_hello_response():
    """Test get_hello_message returns HelloResponse DTO."""
    service = HelloService()
    result = service.get_hello_message()
    assert isinstance(result, HelloResponse)


def test_get_hello_message_has_correct_message():
    """Test message is exactly 'Hello, World!' (BR-001)."""
    service = HelloService()
    result = service.get_hello_message()
    assert result.message == "Hello, World!"


def test_get_hello_message_has_iso8601_timestamp():
    """Test timestamp is valid ISO 8601 format."""
    service = HelloService()
    result = service.get_hello_message()
    # Should match format: 2026-03-27T10:00:00.000000Z
    assert result.timestamp.endswith("Z")
    assert "T" in result.timestamp


def test_get_hello_message_timestamp_is_utc():
    """Test timestamp is in UTC timezone."""
    service = HelloService()
    result = service.get_hello_message()
    # UTC timestamps end with Z
    assert result.timestamp.endswith("Z")


@patch('src.services.hello_service.datetime')
def test_get_hello_message_with_fixed_datetime(mock_datetime):
    """Test with deterministic timestamp for reproducible tests."""
    fixed_dt = datetime(2026, 3, 27, 10, 0, 0)
    mock_datetime.utcnow.return_value = fixed_dt

    service = HelloService()
    result = service.get_hello_message()

    assert result.message == "Hello, World!"
    assert result.timestamp == "2026-03-27T10:00:00.000000Z"


@patch('src.services.hello_service.logger')
def test_get_hello_message_logs_correctly(mock_logger):
    """Test structured logging is emitted."""
    service = HelloService()
    service.get_hello_message()

    # Verify logger.info was called
    assert mock_logger.info.call_count >= 1
```

---

### 4. Handler Tests (`tests/unit/test_hello_handler.py`)

```python
import pytest
import json
from unittest.mock import patch, Mock
from src.handlers.hello_handler import lambda_handler, handle_hello_request
from src.dto.response import HelloResponse


def test_lambda_handler_returns_200_AC_001(api_gateway_event, lambda_context, mock_hello_service):
    """Test lambda_handler returns HTTP 200 (AC-001)."""
    with patch('src.handlers.hello_handler.HelloService', return_value=mock_hello_service):
        response = lambda_handler(api_gateway_event, lambda_context)
        assert response['statusCode'] == 200


def test_lambda_handler_response_is_valid_json_AC_002(api_gateway_event, lambda_context, mock_hello_service):
    """Test response body is valid JSON (AC-002)."""
    with patch('src.handlers.hello_handler.HelloService', return_value=mock_hello_service):
        response = lambda_handler(api_gateway_event, lambda_context)
        body = json.loads(response['body'])
        assert isinstance(body, dict)


def test_handle_hello_request_contains_message_AC_003(mock_hello_service):
    """Test response contains message 'Hello, World!' (AC-003)."""
    with patch('src.handlers.hello_handler.HelloService', return_value=mock_hello_service):
        response = handle_hello_request("trace-123")
        body = json.loads(response['body'])
        assert body['message'] == "Hello, World!"


def test_handle_hello_request_contains_timestamp_AC_004(mock_hello_service):
    """Test response contains ISO 8601 timestamp (AC-004)."""
    with patch('src.handlers.hello_handler.HelloService', return_value=mock_hello_service):
        response = handle_hello_request("trace-123")
        body = json.loads(response['body'])
        assert 'timestamp' in body
        assert body['timestamp'].endswith('Z')


def test_lambda_handler_with_exception_returns_500(api_gateway_event, lambda_context):
    """Test exception handling returns 500 with error response."""
    with patch('src.handlers.hello_handler.HelloService') as mock_service:
        mock_service.return_value.get_hello_message.side_effect = Exception("Test error")

        response = lambda_handler(api_gateway_event, lambda_context)

        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert body['errorCode'] == 'INTERNAL_ERROR'
        assert body['correlationId'] == lambda_context.request_id


def test_lambda_handler_includes_trace_id_in_response(api_gateway_event, lambda_context, mock_hello_service):
    """Test response includes X-Trace-Id header."""
    with patch('src.handlers.hello_handler.HelloService', return_value=mock_hello_service):
        response = lambda_handler(api_gateway_event, lambda_context)
        assert 'X-Trace-Id' in response['headers']


def test_handle_hello_request_content_type_header(mock_hello_service):
    """Test response has correct Content-Type header."""
    with patch('src.handlers.hello_handler.HelloService', return_value=mock_hello_service):
        response = handle_hello_request("trace-123")
        assert response['headers']['Content-Type'] == 'application/json'


def test_lambda_handler_extracts_trace_id_from_headers(lambda_context, mock_hello_service):
    """Test trace ID extraction from X-Amzn-Trace-Id header."""
    event = {
        'httpMethod': 'GET',
        'path': '/hello',
        'headers': {'X-Amzn-Trace-Id': 'custom-trace-id'}
    }

    with patch('src.handlers.hello_handler.HelloService', return_value=mock_hello_service):
        response = lambda_handler(event, lambda_context)
        assert 'X-Trace-Id' in response['headers']
```

---

## Acceptance Criteria

### Test Coverage
- [ ] ≥80% code coverage overall
- [ ] 100% coverage on DTO layer
- [ ] ≥90% coverage on Service layer
- [ ] ≥90% coverage on Handler layer

### Test Quality
- [ ] All tests follow AAA pattern (Arrange, Act, Assert)
- [ ] Tests are independent (no shared state)
- [ ] Tests use fixtures for common setups
- [ ] Mocks used appropriately (no real AWS calls)
- [ ] Test names clearly describe what is tested

### Acceptance Criteria Mapping
- [ ] AC-001: HTTP 200 status code - `test_lambda_handler_returns_200_AC_001()`
- [ ] AC-002: Valid JSON response - `test_lambda_handler_response_is_valid_json_AC_002()`
- [ ] AC-003: Contains "Hello, World!" - `test_handle_hello_request_contains_message_AC_003()`
- [ ] AC-004: Contains ISO 8601 timestamp - `test_handle_hello_request_contains_timestamp_AC_004()`

### Business Rules
- [ ] BR-001: Message exactly "Hello, World!" - `test_get_hello_message_has_correct_message()`
- [ ] BR-001: ISO 8601 timestamp format - `test_get_hello_message_has_iso8601_timestamp()`

---

## Compliance Checks

- ✅ **Test Generation Pattern**: AAA pattern, independent tests
- ✅ **Test Coverage**: ≥80% requirement
- ✅ **AC Traceability**: All AC mapped to specific tests
- ✅ **Mocking Strategy**: External dependencies mocked
- ✅ **Fixtures**: Shared setup in conftest.py

---

## Running Tests

```bash
cd backend/lambdas/hello-world
pytest tests/unit/ --cov=src --cov-report=term-missing -v
```

Expected output:
```
tests/unit/test_response_dto.py::test_hello_response_creation PASSED
tests/unit/test_response_dto.py::test_hello_response_factory_method PASSED
...
======================== 20 passed in 0.45s ========================
Coverage: 85%
```

---

## Notes

- Unit tests run fast (<1 second total)
- No AWS resources needed for unit tests
- Integration tests covered in TASK-007
- Coverage reports generated in HTML format
- All tests must pass before code review
