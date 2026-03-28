# TASK-003: Handler Layer Implementation

**Status**: Backlog
**Priority**: P0 (Critical - Lambda Entry Point)
**Estimated Effort**: 40 minutes
**Dependencies**: TASK-001 (DTOs), TASK-002 (Service)

---

## Objective

Implement the handler layer that serves as the Lambda entry point. Handles API Gateway events, routes to service layer, formats HTTP responses, and manages errors.

---

## Files to Create

1. **`backend/lambdas/hello-world/src/handlers/hello_handler.py`**
   - `lambda_handler()` - Lambda entry point
   - `handle_hello_request()` - Request processing
   - Error handling with standard ErrorResponse

---

## Implementation Details

### Handler Implementation

```python
import json
import logging
from typing import Any
from src.services.hello_service import HelloService
from src.dto.response import ErrorResponse

logger = logging.getLogger(__name__)


def lambda_handler(event: dict, context: Any) -> dict:
    """
    Lambda entry point for API Gateway requests.

    Args:
        event: API Gateway proxy event
        context: Lambda context

    Returns:
        dict: API Gateway proxy response with statusCode and body
    """
    try:
        # Extract trace ID from X-Ray
        trace_id = event.get('headers', {}).get('X-Amzn-Trace-Id', context.request_id)

        logger.info(json.dumps({
            "message": "Request received",
            "method": event.get('httpMethod'),
            "path": event.get('path'),
            "trace_id": trace_id
        }))

        # Route to handler
        response = handle_hello_request(trace_id)

        logger.info(json.dumps({
            "message": "Request completed successfully",
            "status_code": response['statusCode'],
            "trace_id": trace_id
        }))

        return response

    except Exception as e:
        logger.error(json.dumps({
            "message": "Request failed with error",
            "error": str(e),
            "trace_id": context.request_id
        }))

        error_response = ErrorResponse.create_internal_error(context.request_id)

        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'X-Trace-Id': context.request_id
            },
            'body': json.dumps(error_response.to_dict())
        }


def handle_hello_request(trace_id: str) -> dict:
    """
    Handle GET /hello request.

    Args:
        trace_id: X-Ray trace ID for correlation

    Returns:
        dict: HTTP response dict with statusCode 200 and JSON body
    """
    # Instantiate service
    hello_service = HelloService()

    # Get response from service layer
    hello_response = hello_service.get_hello_message()

    # Format as HTTP response
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'X-Trace-Id': trace_id
        },
        'body': json.dumps(hello_response.to_dict())
    }
```

---

## Acceptance Criteria

- [ ] `lambda_handler()` function implemented as Lambda entry point
- [ ] Parses API Gateway event correctly
- [ ] Extracts X-Ray trace ID from headers or context
- [ ] Routes to `handle_hello_request()`
- [ ] Returns HTTP 200 status code (AC-001)
- [ ] Response body is valid JSON (AC-002)
- [ ] Response contains "Hello, World!" message (AC-003)
- [ ] Response contains ISO 8601 timestamp (AC-004)
- [ ] X-Trace-Id included in response headers
- [ ] Exception handling returns 500 with ErrorResponse
- [ ] Structured logging for request/response/errors
- [ ] Type hints on all functions
- [ ] NO business logic in handler (only routing)

---

## Compliance Checks

- ✅ **Layer Architecture**: Handler only routes, no business logic
- ✅ **Aspect-Oriented Programming**: Logging aspects applied
- ✅ **Observability Requirements**: Structured logs, trace ID propagation
- ✅ **Error Response Format**: Standard ErrorResponse on errors
- ✅ **Development Best Practices**: Type hints, guard clauses, clean code

---

## HTTP Response Format

### Success Response (200)
```json
{
    "statusCode": 200,
    "headers": {
        "Content-Type": "application/json",
        "X-Trace-Id": "1-5f5e4d3c-2b1a0987654321fedcba"
    },
    "body": "{\"message\": \"Hello, World!\", \"timestamp\": \"2026-03-27T10:00:00.000Z\"}"
}
```

### Error Response (500)
```json
{
    "statusCode": 500,
    "headers": {
        "Content-Type": "application/json",
        "X-Trace-Id": "test-request-id"
    },
    "body": "{\"errorCode\": \"INTERNAL_ERROR\", \"message\": \"An internal error occurred\", \"correlationId\": \"test-request-id\", \"timestamp\": \"2026-03-27T10:00:00.000Z\"}"
}
```

---

## Observability

### Structured Logs
```json
{"message": "Request received", "method": "GET", "path": "/hello", "trace_id": "..."}
{"message": "Request completed successfully", "status_code": 200, "trace_id": "..."}
{"message": "Request failed with error", "error": "...", "trace_id": "..."}
```

### X-Ray Tracing
- Handler creates root span
- Service layer span is child of handler span
- Trace ID propagated in response headers

---

## Testing

Unit tests will be created in TASK-004 to validate:
- Returns HTTP 200 (AC-001)
- Response is valid JSON (AC-002)
- Contains correct message (AC-003)
- Contains ISO 8601 timestamp (AC-004)
- Exception handling returns 500
- Trace ID in response headers

---

## Notes

- Handler is the ONLY layer that knows about API Gateway events
- Handler is the ONLY layer that formats HTTP responses
- Service layer is called with plain Python types
- No boto3 calls in handler (none needed)
- Error handling catches ALL exceptions at handler level
