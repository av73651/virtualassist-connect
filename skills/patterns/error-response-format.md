# Error Response Format Pattern

## Purpose

This pattern defines the **standard error response format** for all API endpoints to ensure consistency and proper error handling.

## Standard Format

ALL error responses MUST use this exact format:

```json
{
    "errorCode": "ERROR_TYPE",
    "message": "Human-readable error description",
    "correlationId": "uuid-from-logger",
    "timestamp": "ISO-8601-utc-timestamp"
}
```

---

## Error Codes (STANDARD)

### Client Errors (4xx)

#### VALIDATION_ERROR (400)
**When**: Request data fails validation
**Example**:
```json
{
    "errorCode": "VALIDATION_ERROR",
    "message": "Email format is invalid",
    "correlationId": "a3f7c8d1-4b2e-4c9f-b1a2-3d4e5f6g7h8i"
}
```

#### UNAUTHORIZED (401)
**When**: Missing or invalid authentication
**Example**:
```json
{
    "errorCode": "UNAUTHORIZED",
    "message": "Missing authorization token",
    "correlationId": "a3f7c8d1-4b2e-4c9f-b1a2-3d4e5f6g7h8i"
}
```

#### FORBIDDEN (403)
**When**: User lacks required permissions
**Example**:
```json
{
    "errorCode": "FORBIDDEN",
    "message": "Insufficient permissions to access this resource",
    "correlationId": "a3f7c8d1-4b2e-4c9f-b1a2-3d4e5f6g7h8i"
}
```

#### NOT_FOUND (404)
**When**: Resource does not exist
**Example**:
```json
{
    "errorCode": "NOT_FOUND",
    "message": "User with ID xyz not found",
    "correlationId": "a3f7c8d1-4b2e-4c9f-b1a2-3d4e5f6g7h8i"
}
```

#### CONFLICT (409)
**When**: Resource already exists or state conflict
**Example**:
```json
{
    "errorCode": "CONFLICT",
    "message": "User with email already exists",
    "correlationId": "a3f7c8d1-4b2e-4c9f-b1a2-3d4e5f6g7h8i"
}
```

#### RATE_LIMIT_EXCEEDED (429)
**When**: Too many requests
**Example**:
```json
{
    "errorCode": "RATE_LIMIT_EXCEEDED",
    "message": "Rate limit exceeded. Try again in 60 seconds",
    "correlationId": "a3f7c8d1-4b2e-4c9f-b1a2-3d4e5f6g7h8i"
}
```

### Server Errors (5xx)

#### INTERNAL_ERROR (500)
**When**: Unexpected server error
**Example**:
```json
{
    "errorCode": "INTERNAL_ERROR",
    "message": "An internal server error occurred",
    "correlationId": "a3f7c8d1-4b2e-4c9f-b1a2-3d4e5f6g7h8i"
}
```

#### SERVICE_UNAVAILABLE (503)
**When**: External service unavailable
**Example**:
```json
{
    "errorCode": "SERVICE_UNAVAILABLE",
    "message": "AI service temporarily unavailable",
    "correlationId": "a3f7c8d1-4b2e-4c9f-b1a2-3d4e5f6g7h8i"
}
```

---

## Implementation

### Python Handler Implementation

Note: In practice, the `@api_gateway_handler` decorator centralizes error mapping and trace injection. This example shows the underlying error handling logic for reference.

```python
import logging
import json
from opentelemetry import trace
from src.dto.response import ErrorResponse

logger = logging.getLogger(__name__)

def get_trace_id() -> str:
    """Extract OTel trace ID for use as correlation ID."""
    span = trace.get_current_span()
    return format(span.get_span_context().trace_id, '032x')

def create_user(event):
    """Handler for POST /users."""
    try:
        body = json.loads(event.get('body', '{}'))
        request_data = CreateUserRequest(**body)

        service = UserService()
        user = service.create_user(request_data)

        return {
            "statusCode": 201,
            "body": json.dumps(UserResponse.from_domain(user).dict())
        }

    except ValueError as e:
        logger.error("Validation error", extra={"error": str(e)})
        return {
            "statusCode": 400,
            "body": json.dumps(ErrorResponse(
                errorCode="VALIDATION_ERROR",
                message=str(e),
                correlationId=get_trace_id()
            ).dict())
        }

    except KeyError as e:
        logger.error("Resource not found", extra={"error": str(e)})
        return {
            "statusCode": 404,
            "body": json.dumps(ErrorResponse(
                errorCode="NOT_FOUND",
                message=f"Resource {str(e)} not found",
                correlationId=get_trace_id()
            ).dict())
        }

    except Exception as e:
        logger.exception("Unexpected error occurred")
        return {
            "statusCode": 500,
            "body": json.dumps(ErrorResponse(
                errorCode="INTERNAL_ERROR",
                message="An internal server error occurred",
                correlationId=get_trace_id()
            ).dict())
        }
```

### ErrorResponse DTO

```python
from pydantic import BaseModel

class ErrorResponse(BaseModel):
    """Standard error response format."""

    errorCode: str
    message: str
    correlationId: str
    timestamp: str

    class Config:
        schema_extra = {
            "example": {
                "errorCode": "VALIDATION_ERROR",
                "message": "Email format is invalid",
                "correlationId": "a3f7c8d1-4b2e-4c9f-b1a2-3d4e5f6g7h8i",
                "timestamp": "2026-03-28T10:00:00.000Z"
            }
        }
```

---

## HTTP Status Code Mapping

| Error Code | HTTP Status | Description |
|------------|-------------|-------------|
| VALIDATION_ERROR | 400 | Bad Request - Invalid input |
| UNAUTHORIZED | 401 | Unauthorized - Missing/invalid auth |
| FORBIDDEN | 403 | Forbidden - Insufficient permissions |
| NOT_FOUND | 404 | Not Found - Resource doesn't exist |
| CONFLICT | 409 | Conflict - Duplicate or state conflict |
| RATE_LIMIT_EXCEEDED | 429 | Too Many Requests |
| INTERNAL_ERROR | 500 | Internal Server Error |
| SERVICE_UNAVAILABLE | 503 | Service Unavailable |

---

## Error Handling Best Practices

### 1. Don't Expose Internal Details

❌ **WRONG**: Exposing stack traces
```json
{
    "error": "Traceback (most recent call last): File...",
    "message": "NoneType object has no attribute 'id'"
}
```

✅ **CORRECT**: Generic error message
```json
{
    "errorCode": "INTERNAL_ERROR",
    "message": "An internal server error occurred",
    "correlationId": "uuid"
}
```

### 2. Include Correlation ID

The correlation ID allows debugging in logs without exposing internal details to users.

```python
logger.error(
    "Database connection failed",
    extra={
        "error": str(e),
        "stack_trace": traceback.format_exc()
    }
)

return ErrorResponse(
    errorCode="INTERNAL_ERROR",
    message="An internal server error occurred",
    correlationId=get_trace_id()  # Link to logs
).dict(), 500
```

### 3. Be Specific for Client Errors

Help clients understand what went wrong:

❌ **VAGUE**:
```json
{"errorCode": "VALIDATION_ERROR", "message": "Invalid input"}
```

✅ **SPECIFIC**:
```json
{"errorCode": "VALIDATION_ERROR", "message": "Email format is invalid. Expected format: user@domain.com"}
```

### 4. Log Before Returning Error

Always log errors with context:

```python
try:
    user = service.create_user(request_data)
except ValueError as e:
    logger.error(
        "User creation failed",
        extra={
            "error": str(e),
            "email": request_data.email,
            "action": "create_user"
        }
    )
    return ErrorResponse(
        errorCode="VALIDATION_ERROR",
        message=str(e),
        correlationId=get_trace_id()
    ).dict(), 400
```

---

## API Gateway Error Responses

API Gateway also needs CORS headers for errors:

```python
def error_response(status_code: int, error_code: str, message: str) -> dict:
    """Build error response with CORS headers."""
    # MANDATORY: Use specific allowed origin, NOT wildcard "*" (security standards violation)
    allowed_origin = os.environ.get("CORS_ALLOWED_ORIGIN", "https://app.example.com")
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": allowed_origin,
            "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Correlation-Id"
        },
        "body": json.dumps({
            "errorCode": error_code,
            "message": message,
            "correlationId": get_trace_id()
        })
    }
```

---

## Frontend Error Handling

### TypeScript Error Interface

```typescript
export interface ApiError {
  errorCode: string;
  message: string;
  correlationId: string;
}
```

### Angular HTTP Interceptor

```typescript
import { Injectable } from '@angular/core';
import { HttpInterceptor, HttpRequest, HttpHandler, HttpEvent, HttpErrorResponse } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';

@Injectable()
export class ErrorInterceptor implements HttpInterceptor {

  intercept(req: HttpRequest<any>, next: HttpHandler): Observable<HttpEvent<any>> {
    return next.handle(req).pipe(
      catchError((error: HttpErrorResponse) => {
        if (error.error && error.error.errorCode) {
          // Standard error format
          const apiError: ApiError = error.error;
          console.error(`API Error [${apiError.errorCode}]:`, apiError.message);
          console.error(`Correlation ID: ${apiError.correlationId}`);

          // Handle specific error codes
          switch (apiError.errorCode) {
            case 'UNAUTHORIZED':
              // Redirect to login
              break;
            case 'FORBIDDEN':
              // Show access denied message
              break;
            case 'VALIDATION_ERROR':
              // Show validation error to user
              break;
            default:
              // Generic error message
              break;
          }
        }

        return throwError(() => error);
      })
    );
  }
}
```

---

## Testing Error Responses

### Unit Test

```python
def test_create_user_validation_error():
    """Test validation error response format."""
    event = {
        "httpMethod": "POST",
        "body": json.dumps({"email": "invalid-email", "name": "Test"})
    }

    response = lambda_handler(event, None)

    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert body["errorCode"] == "VALIDATION_ERROR"
    assert "correlationId" in body
    assert "message" in body
```

### Integration Test

```python
def test_api_error_response():
    """Test error response via API Gateway."""
    response = requests.post(
        f"{api_url}/users",
        json={"email": "invalid", "name": "Test"}
    )

    assert response.status_code == 400
    error = response.json()
    assert error["errorCode"] == "VALIDATION_ERROR"
    assert "correlationId" in error
```

---

## Common Violations

### ❌ VIOLATION: Inconsistent Error Format

```python
# WRONG: Different error structures
# Handler 1
return {"error": "Not found"}, 404

# Handler 2
return {"message": "Invalid input", "code": "VAL_001"}, 400

# Handler 3
return {"errorMessage": "Server error"}, 500
```

### ✅ CORRECT: Consistent Format

```python
# CORRECT: All handlers use ErrorResponse
return ErrorResponse(
    errorCode="NOT_FOUND",
    message="User not found",
    correlationId=get_trace_id()
).dict(), 404
```

---

## References

- **Used in Skills**: code-generation.md, code-review.md
- **Enforced by**: code-review.md (API Design Review)
- **Documented in**: documentation-generation.md (API documentation)

---

**Follow this pattern for consistent, debuggable error responses across all APIs.**
