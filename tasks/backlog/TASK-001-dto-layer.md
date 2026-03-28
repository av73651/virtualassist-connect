# TASK-001: DTO Layer and Project Structure

**Status**: Backlog
**Priority**: P0 (Critical - Foundation)
**Estimated Effort**: 30 minutes
**Dependencies**: None

---

## Objective

Create project directory structure and implement DTO (Data Transfer Object) layer with Pydantic models for request/response validation.

---

## Files to Create

### Directory Structure
```
backend/lambdas/hello-world/
├── src/
│   ├── __init__.py
│   ├── handlers/__init__.py
│   ├── services/__init__.py
│   ├── dto/__init__.py
│   ├── middleware/__init__.py (empty)
│   └── config/__init__.py (empty)
├── tests/
│   ├── __init__.py
│   ├── unit/__init__.py
│   └── integration/__init__.py
├── requirements.txt
└── pytest.ini
```

### Implementation Files

1. **`backend/lambdas/hello-world/src/dto/response.py`**
   - `HelloResponse` class (Pydantic BaseModel)
     - Fields: `message` (str), `timestamp` (str)
     - `create()` factory method
     - `to_dict()` serialization method
   - `ErrorResponse` class (Pydantic BaseModel)
     - Fields: `errorCode`, `message`, `correlationId`, `timestamp`
     - `create_internal_error()` factory method
     - `to_dict()` serialization method

2. **`backend/lambdas/hello-world/requirements.txt`**
   ```
   pydantic==2.6.0
   pytest==7.4.3
   pytest-cov==4.1.0
   pytest-mock==3.12.0
   moto[dynamodb,s3]==5.0.0
   ```

3. **`backend/lambdas/hello-world/pytest.ini`**
   - Configure testpaths, markers (unit, integration)
   - Coverage settings (≥80%)
   - Verbose output

---

## Implementation Details

### HelloResponse Model
```python
from pydantic import BaseModel, Field
from datetime import datetime

class HelloResponse(BaseModel):
    """Response DTO for hello world endpoint."""

    message: str = Field(..., description="Greeting message", example="Hello, World!")
    timestamp: str = Field(..., description="ISO 8601 timestamp in UTC", example="2026-03-27T10:00:00.000Z")

    @classmethod
    def create(cls, message: str, timestamp: datetime) -> "HelloResponse":
        """Factory method to create HelloResponse."""
        return cls(
            message=message,
            timestamp=timestamp.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {"message": self.message, "timestamp": self.timestamp}
```

### ErrorResponse Model
```python
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

## Acceptance Criteria

- [ ] All directory structure created
- [ ] All `__init__.py` files created
- [ ] `response.py` with `HelloResponse` class implemented
- [ ] `response.py` with `ErrorResponse` class implemented
- [ ] Both classes have factory methods
- [ ] Both classes have `to_dict()` methods
- [ ] Pydantic validation configured correctly
- [ ] Type hints on all methods
- [ ] `requirements.txt` created with all dependencies
- [ ] `pytest.ini` configured

---

## Compliance Checks

- ✅ **Layer Architecture**: DTOs are in dedicated `dto/` directory
- ✅ **Type Hints**: All parameters and returns typed
- ✅ **Development Best Practices**: Factory methods, clean code
- ✅ **Error Response Format**: Standard ErrorResponse structure

---

## Testing

Unit tests will be created in TASK-004 after all core components exist.

---

## Notes

- DTOs use Pydantic for validation and serialization
- ErrorResponse follows standard error-response-format.md pattern
- Timestamp formatting: ISO 8601 with milliseconds and Z suffix
- No business logic in DTOs - pure data structures
