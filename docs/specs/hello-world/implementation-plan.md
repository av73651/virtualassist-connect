# Implementation Plan - Hello World API

**Project**: Hello World Lambda API
**Version**: 1.0
**Date**: 2026-03-27

---

## 1. Project Structure

```
virtualassist-connect/
├── backend/
│   └── lambdas/
│       └── hello-world/
│           ├── src/
│           │   ├── domain/
│           │   │   └── hello_message.py
│           │   ├── handlers/
│           │   │   └── hello_handler.py
│           │   ├── services/
│           │   │   └── hello_service.py
│           │   ├── dto/
│           │   │   ├── request.py (empty for now)
│           │   │   └── response.py
│           │   ├── middleware/
│           │   │   └── __init__.py (empty for now)
│           │   ├── config/
│           │   │   └── __init__.py (empty for now)
│           │   └── __init__.py
│           ├── tests/
│           │   ├── unit/
│           │   │   ├── test_hello_handler.py
│           │   │   ├── test_hello_service.py
│           │   │   └── test_response_dto.py
│           │   ├── integration/
│           │   │   └── test_api_integration.py
│           │   ├── conftest.py
│           │   └── __init__.py
│           ├── requirements.txt
│           └── pytest.ini
├── infra/
│   └── stacks/
│       └── hello_world_stack.py
└── docs/ (already created)
```

---

## 2. Lambda Function Implementation

### 2.0 Domain Layer (`src/domain/hello_message.py`)

**Purpose**: Pure business objects with no external dependencies

**Responsibilities**:
- Define business entities
- Domain validation logic
- Business invariants
- **NO framework dependencies**
- **NO DTOs or HTTP concerns**

**Domain Model**:

```python
@dataclass(frozen=True)
class HelloMessage:
    """Pure domain object for hello world message."""

    message: str
    timestamp: datetime  # Native Python datetime

    @classmethod
    def create(cls, message: str) -> "HelloMessage":
        """Factory method with current UTC timestamp."""
        return cls(message=message, timestamp=datetime.utcnow())

    def validate(self) -> bool:
        """Validate domain invariants."""
        if not self.message or not self.message.strip():
            raise ValueError("Message cannot be empty")
        if self.timestamp is None:
            raise ValueError("Timestamp cannot be None")
        return True
```

---

### 2.1 Handler Layer (`src/handlers/hello_handler.py`)

**Purpose**: Entry point for Lambda, routes requests, converts domain ↔ DTO

**Responsibilities** (per layer-architecture.md):
- Parse API Gateway event
- Extract trace context
- Route to service layer
- **Convert domain objects to DTOs**
- Format HTTP response
- **NO business logic**

**Decorators to Apply** (per aspect-oriented-programming.md):
- OpenTelemetry tracing (via ADOT layer)
- Structured logging

**Function Signatures**:

```python
def lambda_handler(event: dict, context: Any) -> dict:
    """
    Lambda entry point for API Gateway requests.

    Args:
        event: API Gateway proxy event
        context: Lambda context

    Returns:
        dict: API Gateway proxy response with statusCode and body
    """

def handle_hello_request(trace_id: str) -> dict:
    """
    Handle GET /hello request.

    Args:
        trace_id: X-Ray trace ID for correlation

    Returns:
        dict: HTTP response dict with statusCode 200 and JSON body
    """
```

**Error Handling**:
- Catch all exceptions
- Return 500 with standard error format
- Log errors with trace ID

**HTTP Response Format**:
```python
{
    "statusCode": 200,
    "headers": {
        "Content-Type": "application/json",
        "X-Trace-Id": "trace-id-here"
    },
    "body": '{"message": "Hello, World!", "timestamp": "..."}'
}
```

---

### 2.2 Service Layer (`src/services/hello_service.py`)

**Purpose**: Business logic for generating hello world messages

**Responsibilities**:
- Create domain objects
- Apply business rules (BR-001: exact message format)
- Validate domain invariants
- **Returns domain objects only (NO DTOs)**
- **NO HTTP concerns**
- **NO parsing API Gateway events**

**Architecture Rule**: Service layer MUST return domain objects, never DTOs.
Handler layer is responsible for domain ↔ DTO conversion.

**Function Signatures**:

```python
class HelloService:
    """Service for generating hello world messages."""

    def __init__(self):
        """Initialize HelloService."""
        pass

    def get_hello_message(self) -> HelloMessage:
        """
        Generate hello world message with current timestamp.

        Business Rules:
        - BR-001: Message must be exactly "Hello, World!"

        Returns:
            HelloMessage: Domain object (NOT DTO)
        """
```

**Tracing** (per opentelemetry-template.md):
```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

@tracer.start_as_current_span("get_hello_message")
def get_hello_message(self) -> HelloResponse:
    # Implementation
```

**Logging** (per observability-requirements.md):
```python
import logging
import json

logger = logging.getLogger(__name__)

def get_hello_message(self) -> HelloResponse:
    logger.info(json.dumps({
        "message": "Generating hello world response",
        "service": "hello_service",
        "method": "get_hello_message"
    }))
    # Implementation
```

---

### 2.3 DTO Layer (`src/dto/response.py`)

**Purpose**: Define response data transfer objects with validation

**Pydantic Models**:

```python
from pydantic import BaseModel, Field
from datetime import datetime

class HelloResponse(BaseModel):
    """Response DTO for hello world endpoint."""

    message: str = Field(
        ...,
        description="Greeting message",
        example="Hello, World!"
    )
    timestamp: str = Field(
        ...,
        description="ISO 8601 timestamp in UTC",
        example="2026-03-27T10:00:00.000Z"
    )

    @classmethod
    def create(cls, message: str, timestamp: datetime) -> "HelloResponse":
        """
        Factory method to create HelloResponse.

        Args:
            message: Greeting message
            timestamp: Python datetime object

        Returns:
            HelloResponse: Validated response DTO
        """
        return cls(
            message=message,
            timestamp=timestamp.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "message": self.message,
            "timestamp": self.timestamp
        }


class ErrorResponse(BaseModel):
    """Standard error response DTO."""

    errorCode: str = Field(..., description="Error code identifier")
    message: str = Field(..., description="Human-readable error message")
    correlationId: str = Field(..., description="Trace ID for correlation")
    timestamp: str = Field(..., description="ISO 8601 timestamp")

    @classmethod
    def create_internal_error(cls, correlation_id: str) -> "ErrorResponse":
        """Create standard internal error response."""
        return cls(
            errorCode="INTERNAL_ERROR",
            message="An internal error occurred",
            correlationId=correlation_id,
            timestamp=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "errorCode": self.errorCode,
            "message": self.message,
            "correlationId": self.correlationId,
            "timestamp": self.timestamp
        }
```

---

## 3. Test Implementation

### 3.1 Unit Tests

#### `tests/unit/test_hello_handler.py`

**Test Cases** (map to acceptance criteria):

```python
# Test Cases:
def test_lambda_handler_returns_200_AC_001():
    """Test lambda_handler returns HTTP 200 (AC-001)."""

def test_lambda_handler_response_is_valid_json_AC_002():
    """Test response body is valid JSON (AC-002)."""

def test_handle_hello_request_contains_message_AC_003():
    """Test response contains message 'Hello, World!' (AC-003)."""

def test_handle_hello_request_contains_timestamp_AC_004():
    """Test response contains ISO 8601 timestamp (AC-004)."""

def test_lambda_handler_with_exception_returns_500():
    """Test exception handling returns 500 with error response."""

def test_lambda_handler_includes_trace_id_in_response():
    """Test response includes X-Trace-Id header."""
```

**Mocking**:
- Mock `HelloService` class
- Mock Lambda context
- Mock OpenTelemetry trace context

#### `tests/unit/test_hello_service.py`

**Test Cases**:

```python
# Test Cases:
def test_get_hello_message_returns_hello_response():
    """Test get_hello_message returns HelloResponse DTO."""

def test_get_hello_message_has_correct_message():
    """Test message is exactly 'Hello, World!'."""

def test_get_hello_message_has_iso8601_timestamp():
    """Test timestamp is valid ISO 8601 format."""

def test_get_hello_message_timestamp_is_utc():
    """Test timestamp is in UTC timezone."""

def test_get_hello_message_logs_correctly():
    """Test structured logging is emitted."""
```

**Mocking**:
- Mock `datetime.utcnow()` for deterministic timestamp

#### `tests/unit/test_response_dto.py`

**Test Cases**:

```python
# Test Cases:
def test_hello_response_creation():
    """Test HelloResponse DTO creation."""

def test_hello_response_validation():
    """Test Pydantic validation."""

def test_hello_response_to_dict():
    """Test to_dict() serialization."""

def test_error_response_creation():
    """Test ErrorResponse DTO creation."""

def test_error_response_factory_method():
    """Test create_internal_error() factory."""
```

---

### 3.2 Integration Tests

#### `tests/integration/test_api_integration.py`

**Test Cases** (AC-005):

```python
# Test Cases (requires deployment or localstack):
@pytest.mark.integration
def test_hello_endpoint_response_time_AC_005():
    """Test p95 response time < 200ms (AC-005)."""
    # Make 100 requests, calculate p95

@pytest.mark.integration
def test_hello_endpoint_end_to_end():
    """Test complete API Gateway → Lambda → Response flow."""

@pytest.mark.integration
def test_hello_endpoint_xray_trace():
    """Test X-Ray trace is created."""

@pytest.mark.integration
def test_hello_endpoint_cloudwatch_logs():
    """Test structured logs appear in CloudWatch."""
```

---

### 3.3 Test Configuration

#### `pytest.ini`

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
markers =
    unit: Unit tests (fast, mocked dependencies)
    integration: Integration tests (requires AWS resources)
addopts =
    --cov=src
    --cov-report=term-missing
    --cov-report=html
    --cov-fail-under=80
    -v
```

#### `tests/conftest.py`

```python
# Shared fixtures:
import pytest
from unittest.mock import Mock
from datetime import datetime

@pytest.fixture
def mock_hello_service():
    """Mock HelloService for handler tests."""
    return Mock(spec=HelloService)

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

## 4. Dependencies

### `requirements.txt`

```
# Pydantic for DTOs and validation
pydantic==2.6.0

# Testing
pytest==7.4.3
pytest-cov==4.1.0
pytest-mock==3.12.0
moto[dynamodb,s3]==5.0.0
```

**Note**:
- OpenTelemetry provided by ADOT Lambda layer (not in requirements.txt)
- Structured logging uses standard Python `logging` library with JSON formatting
- NO Lambda Powertools - we use native OpenTelemetry

---

## 5. Infrastructure Implementation

### `infra/stacks/hello_world_stack.py`

**CDK Stack Components**:

```python
from aws_cdk import (
    Stack,
    aws_lambda as lambda_,
    aws_apigateway as apigw,
    aws_logs as logs,
    aws_iam as iam,
    Duration,
    CfnOutput
)

class HelloWorldStack(Stack):
    """CDK stack for Hello World API."""

    def __init__(self, scope, construct_id, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # Lambda Function
        self.hello_lambda = self._create_lambda_function()

        # API Gateway
        self.api = self._create_api_gateway()

        # CloudWatch Dashboard
        self._create_dashboard()

        # CloudWatch Alarms
        self._create_alarms()

        # Outputs
        self._create_outputs()

    def _create_lambda_function(self) -> lambda_.Function:
        """Create Lambda function with ADOT layer."""

    def _create_api_gateway(self) -> apigw.RestApi:
        """Create API Gateway with /hello resource."""

    def _create_dashboard(self):
        """Create CloudWatch dashboard."""

    def _create_alarms(self):
        """Create CloudWatch alarms."""

    def _create_outputs(self):
        """Create stack outputs."""
```

**Lambda Configuration**:
- Runtime: `lambda_.Runtime.PYTHON_3_12`
- Handler: `src.handlers.hello_handler.lambda_handler`
- Memory: `512 MB`
- Timeout: `Duration.seconds(30)`
- Tracing: `lambda_.Tracing.ACTIVE`
- Layers: ADOT Python layer ARN

**IAM Role** (least privilege per iam-least-privilege.md):
```python
lambda_role = iam.Role(
    self, "HelloLambdaRole",
    assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
    managed_policies=[
        iam.ManagedPolicy.from_aws_managed_policy_name(
            "service-role/AWSLambdaBasicExecutionRole"
        ),
        iam.ManagedPolicy.from_aws_managed_policy_name(
            "AWSXRayDaemonWriteAccess"
        )
    ]
)
```

**API Gateway Configuration**:
- REST API (not HTTP API)
- /hello resource with GET method
- Lambda proxy integration
- CORS enabled
- Throttling: 1000 burst, 500 rate
- Deploy to "dev" stage

**CloudWatch Dashboard Widgets**:
- Invocation count
- Error count and rate
- Duration (p50, p95, p99)
- Throttle count
- Lambda logs widget

**CloudWatch Alarms**:
- High error rate (> 1%)
- High latency (p99 > 500ms)

---

## 6. Implementation Sequence

### Phase 1: Core Implementation
1. Create directory structure
2. Implement DTOs (`response.py`)
3. Implement Service layer (`hello_service.py`)
4. Implement Handler layer (`hello_handler.py`)
5. Create `requirements.txt`

### Phase 2: Testing
6. Create test fixtures (`conftest.py`)
7. Write unit tests for DTOs
8. Write unit tests for Service
9. Write unit tests for Handler
10. Run tests, ensure >80% coverage

### Phase 3: Infrastructure
11. Implement CDK stack (`hello_world_stack.py`)
12. Add CloudWatch dashboard
13. Add CloudWatch alarms
14. Test CDK synthesis

### Phase 4: Integration Testing
15. Deploy to dev environment
16. Run integration tests
17. Verify observability (logs, metrics, traces)

---

## 7. File-by-File Checklist

### Backend Files
- [ ] `backend/lambdas/hello-world/src/__init__.py`
- [ ] `backend/lambdas/hello-world/src/handlers/__init__.py`
- [ ] `backend/lambdas/hello-world/src/handlers/hello_handler.py`
- [ ] `backend/lambdas/hello-world/src/services/__init__.py`
- [ ] `backend/lambdas/hello-world/src/services/hello_service.py`
- [ ] `backend/lambdas/hello-world/src/dto/__init__.py`
- [ ] `backend/lambdas/hello-world/src/dto/response.py`
- [ ] `backend/lambdas/hello-world/requirements.txt`
- [ ] `backend/lambdas/hello-world/pytest.ini`

### Test Files
- [ ] `backend/lambdas/hello-world/tests/__init__.py`
- [ ] `backend/lambdas/hello-world/tests/conftest.py`
- [ ] `backend/lambdas/hello-world/tests/unit/__init__.py`
- [ ] `backend/lambdas/hello-world/tests/unit/test_hello_handler.py`
- [ ] `backend/lambdas/hello-world/tests/unit/test_hello_service.py`
- [ ] `backend/lambdas/hello-world/tests/unit/test_response_dto.py`
- [ ] `backend/lambdas/hello-world/tests/integration/__init__.py`
- [ ] `backend/lambdas/hello-world/tests/integration/test_api_integration.py`

### Infrastructure Files
- [ ] `infra/stacks/hello_world_stack.py`
- [ ] `infra/app.py` (if not exists)
- [ ] `infra/requirements.txt` (CDK dependencies)

---

## 8. Observability Implementation

### Structured Logging Format

```python
{
    "timestamp": "2026-03-27T10:00:00.000Z",
    "level": "INFO",
    "message": "Request received",
    "trace_id": "1-5f5e4d3c-2b1a0987654321fedcba",
    "service": "hello-world-api",
    "function": "lambda_handler",
    "cold_start": false
}
```

### X-Ray Subsegments

```python
with tracer.start_as_current_span("get_hello_message"):
    # Service logic
    pass
```

### Custom Metrics

```python
from opentelemetry import metrics

meter = metrics.get_meter("hello-world-api")
request_counter = meter.create_counter(
    "hello_world_requests",
    description="Count of hello world requests"
)

request_counter.add(1)
```

---

## 9. Acceptance Criteria Mapping

| AC ID | Implementation Location | Test Location |
|-------|-------------------------|---------------|
| AC-001 | `hello_handler.lambda_handler()` returns 200 | `test_lambda_handler_returns_200_AC_001()` |
| AC-002 | `hello_handler.handle_hello_request()` returns JSON | `test_lambda_handler_response_is_valid_json_AC_002()` |
| AC-003 | `hello_service.get_hello_message()` sets message | `test_handle_hello_request_contains_message_AC_003()` |
| AC-004 | `HelloResponse.create()` formats timestamp | `test_handle_hello_request_contains_timestamp_AC_004()` |
| AC-005 | Integration test with 100 requests | `test_hello_endpoint_response_time_AC_005()` |

---

## 10. Code Generation Guidance

### Type Hints (per development-best-practices.md)
- All function parameters typed
- All return values typed (including `-> None`)
- Use Pydantic models for structured data (not raw dicts)

### Guard Clauses (per development-best-practices.md)
- Early returns for error conditions
- Avoid deep nesting

### Error Handling (per error-response-format.md)
- Handler catches all exceptions
- Returns standard ErrorResponse format
- Includes trace ID for correlation

### No Implementation Details in Handler
- Handler only routes and formats
- All business logic in Service layer
- No direct boto3 calls in Service (none needed for hello world)

---

## Blueprint Complete

**This implementation plan provides**:
- ✅ Complete directory structure
- ✅ File-by-file list with responsibilities
- ✅ Function signatures with type hints
- ✅ Test cases mapped to acceptance criteria
- ✅ CDK infrastructure components
- ✅ Observability instrumentation
- ✅ Compliance with all architectural patterns

**Code generation can now proceed mechanically by following this blueprint.**
