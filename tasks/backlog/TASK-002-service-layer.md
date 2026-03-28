# TASK-002: Service Layer Implementation

**Status**: Backlog
**Priority**: P0 (Critical - Core Business Logic)
**Estimated Effort**: 30 minutes
**Dependencies**: TASK-001 (needs HelloResponse DTO)

---

## Objective

Implement the service layer containing business logic for generating hello world responses. Service layer is framework-agnostic with no HTTP concerns.

---

## Files to Create

1. **`backend/lambdas/hello-world/src/services/hello_service.py`**
   - `HelloService` class
   - `get_hello_message()` method

---

## Implementation Details

### HelloService Class

```python
import logging
import json
from datetime import datetime
from opentelemetry import trace
from src.dto.response import HelloResponse

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class HelloService:
    """Service for generating hello world responses.

    Implements business logic for BR-001: Message format requirements.
    """

    def __init__(self):
        """Initialize HelloService."""
        pass

    @tracer.start_as_current_span("get_hello_message")
    def get_hello_message(self) -> HelloResponse:
        """
        Generate hello world response with current timestamp.

        Business Rules:
        - BR-001: Message must be exactly "Hello, World!"
        - BR-001: Timestamp in ISO 8601 format (UTC)

        Returns:
            HelloResponse: Response DTO with message and timestamp
        """
        logger.info(json.dumps({
            "message": "Generating hello world response",
            "service": "hello_service",
            "method": "get_hello_message"
        }))

        message = "Hello, World!"
        timestamp = datetime.utcnow()

        response = HelloResponse.create(message, timestamp)

        logger.info(json.dumps({
            "message": "Hello world response generated",
            "service": "hello_service",
            "method": "get_hello_message",
            "timestamp": response.timestamp
        }))

        return response
```

---

## Acceptance Criteria

- [ ] `HelloService` class implemented
- [ ] `get_hello_message()` method returns `HelloResponse` DTO
- [ ] Message is exactly "Hello, World!" (BR-001)
- [ ] Timestamp is ISO 8601 format in UTC
- [ ] OpenTelemetry span created for tracing
- [ ] Structured logging emitted (JSON format)
- [ ] Type hints on all methods
- [ ] No HTTP concerns in service layer
- [ ] No API Gateway event parsing

---

## Compliance Checks

- ✅ **Layer Architecture**: Service layer contains only business logic
- ✅ **Aspect-Oriented Programming**: OpenTelemetry tracing decorator
- ✅ **Observability Requirements**: Structured logging in JSON format
- ✅ **OpenTelemetry Template**: Tracer configured, span created
- ✅ **Development Best Practices**: Type hints, clean code, SRP
- ✅ **Business Rules**: BR-001 implemented correctly

---

## Observability

### Structured Logs
```json
{
    "message": "Generating hello world response",
    "service": "hello_service",
    "method": "get_hello_message"
}
```

### X-Ray Traces
- Span name: `get_hello_message`
- Parent: Lambda function span
- Attributes: None needed for this simple service

---

## Testing

Unit tests will be created in TASK-004 to validate:
- Correct message returned
- Valid ISO 8601 timestamp
- UTC timezone
- Logging emitted
- HelloResponse DTO returned

---

## Notes

- Service layer is pure Python - no AWS SDK dependencies
- OpenTelemetry provided by ADOT Lambda layer
- Logging uses standard Python `logging` module
- No Lambda Powertools (per technology-standards.md)
- Service has no state - can be instantiated per request
