# Layer Architecture Pattern

## Purpose

This pattern defines the **mandatory clean architecture separation** for backend code: Handlers, Services, Repositories, Domain objects, DTOs, and Middleware.

## Architecture Overview

```
Request → Handler → Service → Repository → Database
            ↓          ↓           ↓
          DTO     Domain Model  DB Model
            ↑
       Middleware
```

## Directory Structure (MANDATORY)

**Per Lambda** (`backend/lambdas/{function_name}/`):
```
src/
  handlers/       # HTTP/event handlers ONLY
  services/       # Business logic ONLY
  repositories/   # Data access ONLY
  domain/         # Business entities
  dto/            # Request/response schemas
```

**Shared code** (`backend/shared/`) — NOT duplicated per Lambda:
```
shared/
  middleware/     # Cross-cutting concerns (@api_gateway_handler, @observe, @require_auth)
  config/         # Configuration management (logging_config, aws_clients, secrets)
```

---

## Layer Responsibilities

### 1. Handlers (`src/handlers/`)

**ALLOWED**:
- Parse request (extract path params, query params, body)
- Apply middleware/decorators
- Call service layer
- Return response
- Format HTTP responses

**FORBIDDEN**:
- Business logic
- Database queries
- External API calls
- Data transformation beyond simple parsing
- Validation logic (use DTOs)

**Template**:
```python
import logging
import json
from opentelemetry import trace, metrics
from src.dto.request import CreateUserRequest
from src.dto.response import UserResponse, ErrorResponse
from src.services.user_service import UserService
from shared.middleware.auth import require_auth
from shared.middleware.api_gateway import api_gateway_handler

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

@require_auth
@api_gateway_handler
def lambda_handler(event, context, trace_id):
    """Lambda entry point. Trace extraction, error mapping, and logging are handled by decorator."""
    path = event.get('resource')
    method = event.get('httpMethod')

    if path == '/users' and method == 'POST':
        return create_user(event)

    raise ValueError(f"Route not found: {method} {path}")

def create_user(event):
    """Handler for POST /users."""
    body = json.loads(event.get('body', '{}'))
    request_data = CreateUserRequest(**body)

    service = UserService()
    user = service.create_user(request_data)

    return {
        "statusCode": 201,
        "body": json.dumps(UserResponse.from_domain(user).dict())
    }
```

---

### 2. Services (`src/services/`)

**ALLOWED**:
- Business logic implementation
- Orchestrate multiple repositories
- Apply business rules
- Transaction coordination
- Domain object manipulation

**FORBIDDEN**:
- Direct database access (use repositories)
- HTTP request/response handling
- Parsing request bodies
- Cross-cutting concerns (logging, auth - use middleware)

**Template**:
```python
from typing import Optional
import logging
from opentelemetry import trace, metrics
from src.domain.user import User
from src.repositories.user_repository import UserRepository
from src.dto.request import CreateUserRequest

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)

class UserService:
    """User business logic service."""

    def __init__(self, repository: Optional[UserRepository] = None):
        """Initialize service with repository dependency."""
        self.repository = repository or UserRepository()

    def create_user(self, request: CreateUserRequest) -> User:
        """
        Create a new user with business rules applied.

        Args:
            request: Validated user creation request

        Returns:
            Created user domain object

        Raises:
            ValueError: If business rules violated
        """
        # Business rule: email must be unique
        if self.repository.exists_by_email(request.email):
            raise ValueError(f"User with email {request.email} already exists")

        # Business rule: apply default role if not specified
        role = request.role or "user"

        # Create domain object
        user = User(
            email=request.email,
            name=request.name,
            role=role
        )

        # Persist via repository
        created_user = self.repository.save(user)

        logger.info("User created", extra={"user_id": created_user.id})
        return created_user
```

---

### 3. Repositories (`src/repositories/`)

**ALLOWED**:
- Database/data store operations
- Query construction
- Data mapping (DB model ↔ Domain model)
- Connection management

**FORBIDDEN**:
- Business logic
- Business rules
- Transaction logic beyond single operations
- Calling other services

**Template**:
```python
from typing import Optional
import logging
from boto3.dynamodb.conditions import Key
from src.domain.user import User
from shared.config.aws_clients import get_dynamodb_table
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

class UserRepository:
    """User data access repository."""

    def __init__(self):
        """Initialize repository with DynamoDB table."""
        self.table = get_dynamodb_table("users")

    def save(self, user: User) -> User:
        """
        Persist user to database.

        Args:
            user: User domain object

        Returns:
            Saved user with generated ID
        """
        item = {
            "PK": f"USER#{user.id}",
            "SK": "PROFILE",
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "created_at": user.created_at.isoformat()
        }

        self.table.put_item(Item=item)
        return user

    def exists_by_email(self, email: str) -> bool:
        """Check if user with email exists."""
        response = self.table.query(
            IndexName="EmailIndex",
            KeyConditionExpression=Key("email").eq(email),
            Limit=1
        )
        return response["Count"] > 0
```

---

### 4. Domain Objects (`src/domain/`)

**ALLOWED**:
- Business entity definitions
- Simple business logic methods
- Value objects
- Domain validation

**FORBIDDEN**:
- Database operations
- External service calls
- Framework dependencies
- HTTP handling

**Template**:
```python
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

@dataclass
class User:
    """User domain entity."""

    email: str
    name: str
    role: str
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = True

    def deactivate(self) -> None:
        """Deactivate user account."""
        self.is_active = False

    def has_role(self, role: str) -> bool:
        """Check if user has specific role."""
        return self.role == role
```

---

### 5. DTOs (`src/dto/`)

**ALLOWED**:
- Request/response schemas
- Validation rules
- Serialization/deserialization
- Format conversion

**FORBIDDEN**:
- Business logic
- Data access

**Request DTO Template**:
```python
from pydantic import BaseModel, EmailStr, Field
from typing import Optional

class CreateUserRequest(BaseModel):
    """Request schema for user creation."""

    email: EmailStr = Field(..., description="User email address")
    name: str = Field(..., min_length=1, max_length=100)
    role: Optional[str] = Field(None, pattern="^(admin|user|guest)$")

    class Config:
        schema_extra = {
            "example": {
                "email": "user@example.com",
                "name": "John Doe",
                "role": "user"
            }
        }
```

**Response DTO Template**:
```python
from pydantic import BaseModel
from src.domain.user import User

class UserResponse(BaseModel):
    """Response schema for user data."""

    id: str
    email: str
    name: str
    role: str
    is_active: bool

    @classmethod
    def from_domain(cls, user: User) -> "UserResponse":
        """Convert domain object to response DTO."""
        return cls(
            id=user.id,
            email=user.email,
            name=user.name,
            role=user.role,
            is_active=user.is_active
        )
```

**Error Response Template**:
```python
from pydantic import BaseModel

class ErrorResponse(BaseModel):
    """Standard error response."""

    errorCode: str
    message: str
    correlationId: str
```

---

### 6. Middleware (`src/middleware/`)

**PURPOSE**: Cross-cutting concerns using decorators

**ALLOWED**:
- Authentication
- Authorization
- Logging
- Error handling
- Request validation
- Rate limiting

**Template**:
```python
from functools import wraps
from typing import Callable
import logging

logger = logging.getLogger(__name__)

def require_auth(func: Callable) -> Callable:
    """Decorator for authentication enforcement."""

    @wraps(func)
    def wrapper(event, context, *args, **kwargs):
        headers = event.get('headers', {})
        auth_header = headers.get('Authorization') or headers.get('authorization')
        if not auth_header:
            return {
                "statusCode": 401,
                "body": {"errorCode": "UNAUTHORIZED", "message": "Missing authorization"}
            }

        # API Gateway Cognito authorizer handles JWT validation
        # Lambda only performs authorization (permission checks)

        return func(event, context, *args, **kwargs)

    return wrapper
```

---

## Common Violations

### ❌ VIOLATION: Business Logic in Handler
```python
# WRONG
@app.post("/users")
def create_user():
    data = app.current_event.json_body

    # ❌ Email validation is business logic
    if not data.get('email') or '@' not in data['email']:
        return {"error": "Invalid email"}, 400

    # ❌ Direct database access in handler
    table.put_item(Item=data)
    return {"message": "User created"}, 201
```

### ✅ CORRECT: Handler Delegates to Service
```python
# CORRECT
@app.post("/users")
def create_user():
    request_data = CreateUserRequest(**app.current_event.json_body)
    service = UserService()
    user = service.create_user(request_data)
    return UserResponse.from_domain(user).dict(), 201
```

---

### ❌ VIOLATION: Services Performing HTTP Handling
```python
# WRONG
class UserService:
    def create_user(self, email: str, name: str):
        # Business logic...

        # ❌ Service returning HTTP response
        return {
            "statusCode": 201,
            "body": json.dumps({"user": user_data})
        }
```

### ✅ CORRECT: Service Returns Domain Object
```python
# CORRECT
class UserService:
    def create_user(self, request: CreateUserRequest) -> User:
        # Business logic...
        return created_user  # Domain object
```

---

### ❌ VIOLATION: Repositories Calling Services
```python
# WRONG
class UserRepository:
    def save(self, user):
        # ❌ Repository calling service
        notification_service = NotificationService()
        notification_service.send_welcome_email(user.email)

        return self.table.put_item(Item=user.to_dict())
```

### ✅ CORRECT: Service Orchestrates
```python
# CORRECT
class UserService:
    def create_user(self, request):
        # Create user
        user = self.repository.save(request)

        # Orchestrate notification (service layer responsibility)
        self.notification_service.send_welcome_email(user.email)

        return user
```

---

## Dependency Injection

Use constructor injection for testability:

```python
class UserService:
    def __init__(
        self,
        repository: Optional[UserRepository] = None,
        notification_service: Optional[NotificationService] = None
    ):
        self.repository = repository or UserRepository()
        self.notification_service = notification_service or NotificationService()
```

## Testing

Each layer tests independently:

**Handler Test** (integration test):
```python
def test_create_user_handler():
    event = {
        "httpMethod": "POST",
        "path": "/users",
        "body": json.dumps({"email": "test@example.com", "name": "Test"})
    }
    response = lambda_handler(event, None)
    assert response["statusCode"] == 201
```

**Service Test** (unit test with mocked repository):
```python
def test_create_user_service():
    mock_repo = Mock()
    mock_repo.exists_by_email.return_value = False
    service = UserService(repository=mock_repo)

    user = service.create_user(CreateUserRequest(
        email="test@example.com",
        name="Test User"
    ))

    assert user.email == "test@example.com"
    mock_repo.save.assert_called_once()
```

**Repository Test** (integration test with DynamoDB):
```python
def test_save_user():
    repo = UserRepository()
    user = User(email="test@example.com", name="Test", role="user")
    saved_user = repo.save(user)
    assert saved_user.id is not None
```

## References

- **Used in Skills**: code-generation.md, code-review.md
- **Enforced by**: code-review.md (Architecture Compliance Review)
- **Violations flagged**: CRITICAL severity

---

**This pattern ensures clean separation of concerns, testability, and maintainability.**
