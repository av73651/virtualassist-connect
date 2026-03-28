# Code Generation Skill - Enterprise Specification

## Directive

This skill generates production-ready code that MUST enforce architectural standards, separation of concerns, and enterprise-grade quality constraints.

**Primary Goal**: Generate simple, maintainable, deterministic code with strong architectural discipline.

**Non-Negotiables**:
- Follow clean architecture patterns
- Enforce separation of concerns
- Include observability by default
- Pass all quality gates
- Remain simple and readable

---

## 1. BACKEND ARCHITECTURE (Python Lambda)

### 1.1 Mandatory Directory Structure

ALL backend code MUST follow this structure:

**CRITICAL RULE**: Each API/service must have its own separate Lambda directory. DO NOT add new APIs to existing Lambda directories.

```
backend/
├── shared/                      # ✅ Shared code used by ALL Lambdas
│   ├── middleware/
│   │   ├── api_gateway.py      # @api_gateway_handler decorator
│   │   └── observability.py    # @observe decorator
│   └── config/
│       └── logging_config.py   # Structured JSON logging
│
└── lambdas/
    ├── {api_name_1}/            # ✅ Each API gets its own directory
    │   ├── src/
    │   │   ├── handlers/        # HTTP/event handlers ONLY
    │   │   ├── services/        # Business logic ONLY
    │   │   ├── repositories/    # Data access ONLY (if needed)
    │   │   ├── domain/          # Business entities
    │   │   └── dto/             # Request/response schemas
    │   ├── tests/
    │   │   ├── unit/
    │   │   └── integration/
    │   └── requirements.txt
    │
    └── {api_name_2}/            # ✅ Another API = Another directory
        ├── src/
        │   ├── handlers/
        │   ├── services/
        │   ├── domain/
        │   └── dto/
        ├── tests/
        │   ├── unit/
        │   └── integration/
        └── requirements.txt
```

**REMOVED FROM INDIVIDUAL LAMBDAS**: `middleware/`, `utils/`, `config/` directories are now in `backend/shared/` to avoid code duplication.

**Imports in Lambda code**:
```python
# ✅ CORRECT: Import from shared
from shared.middleware.api_gateway import api_gateway_handler
from shared.middleware.observability import observe
from shared.config.logging_config import configure_structured_logging

# ❌ WRONG: Do not create duplicate middleware in each Lambda
# from src.middleware.api_gateway import api_gateway_handler
```

**Before Creating New Code**:
1. Check if this is a NEW API (requires new Lambda directory) or adding to existing API
2. If NEW API: Create `backend/lambdas/{new_api_name}/` directory structure
3. NEVER add handlers/services for different APIs into the same Lambda directory
4. Example: Calculator API should NOT be in `backend/lambdas/hello-world/`, it needs its own `backend/lambdas/calculator/` directory

### 1.2 Layer Responsibilities (STRICT)

#### Handlers (`src/handlers/`)
**ALLOWED**:
- Parse request (extract path params, query params, body)
- Apply middleware/decorators
- Call service layer
- Return response

**FORBIDDEN**:
- Business logic
- Database queries
- External API calls
- Data transformation beyond simple parsing

**Template**:
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
        
    # Exceptions are automatically caught and mapped to HTTP Error Responses (e.g. 404, 500)
    raise ValueError(f"Route not found: {method} {path}")

def create_user(event):
    """Handler for POST /users."""
    # Parse and validate request
    body = json.loads(event.get('body', '{}'))
    request_data = CreateUserRequest(**body)

    # Call service layer
    service = UserService()
    user = service.create_user(request_data)

    # Format HTTP response. The decorator handles trace_id injection, standard headers, and logging.
    return {
        "statusCode": 201, 
        "body": json.dumps(UserResponse.from_domain(user).dict())
    }
```

#### Services (`src/services/`)
**ALLOWED**:
- Business logic implementation
- Orchestrate multiple repositories
- Apply business rules
- Transaction coordination

**FORBIDDEN**:
- Direct database access (use repositories)
- HTTP request/response handling
- Parsing request bodies
- Cross-cutting concerns (manual entry/exit logging, auth, etc. - use decorators)
- Returning DTOs (must return domain objects only)

**Template**:
```python
from typing import Optional
import logging
import json
from src.domain.user import User
from src.repositories.user_repository import UserRepository
from src.dto.request import CreateUserRequest
from opentelemetry import trace, metrics

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

        with tracer.start_as_current_span("save_user_to_db"):
            # Persist via repository
            created_user = self.repository.save(user)

        # Track business metrics
        meter.create_counter("user_creations").add(1)

        # Structured logging using extra
        logger.info("User created", extra={"user_id": created_user.id})
        return created_user
```

#### Repositories (`src/repositories/`)
**ALLOWED**:
- Database/data store operations
- Query construction
- Data mapping (DB model <-> Domain model)

**FORBIDDEN**:
- Business logic
- Business rules
- Transaction logic beyond single operations

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

#### Domain Objects (`src/domain/`)
**ALLOWED**:
- Business entity definitions
- Simple business logic methods
- Value objects

**FORBIDDEN**:
- Database operations
- External service calls
- Framework dependencies

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

#### DTOs (`src/dto/`)
**ALLOWED**:
- Request/response schemas
- Validation rules
- Serialization/deserialization

**FORBIDDEN**:
- Business logic
- Data access

**Template**:
```python
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from src.domain.user import User

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

class ErrorResponse(BaseModel):
    """Standard error response."""

    errorCode: str
    message: str
    correlationId: str
```

#### Middleware (`src/middleware/`)
**PURPOSE**: Cross-cutting concerns using decorators

**Template**:
```python
from functools import wraps
from typing import Callable
import logging
import json

logger = logging.getLogger(__name__)

def require_auth(func: Callable) -> Callable:
    """Decorator for authentication enforcement."""

    @wraps(func)
    def wrapper(event, context):
        # Extract token from request header
        headers = event.get('headers', {})
        auth_header = headers.get('Authorization') or headers.get('authorization')
        if not auth_header:
            return {
                "statusCode": 401,
                "body": {"errorCode": "UNAUTHORIZED", "message": "Missing authorization"}
            }

        # Validate token (simplified)
        # In production, validate JWT or Cognito token

        return func(event, context)

    return wrapper
```

### 1.3 Observability Requirements (MANDATORY)

ALL handler functions MUST include:

```python
import logging
import json
from opentelemetry import trace, metrics

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)

def lambda_handler(event, context, trace_id):
    # Traced automatically by ADOT lambda layer and AOP decorators
    # Handler implementation
    pass
```

**Required**:
- Structured JSON logging (use `extra={...}` parameter, NOT `json.dumps()`)
- Correlation ID in all logs
- Distributed tracing
- Metrics for: invocations, errors, latency
- Log levels: INFO (default), ERROR (failures)

### 1.4 Error Handling (MANDATORY)

ALL errors MUST return standardized format:

```python
{
    "errorCode": "ERROR_TYPE",
    "message": "Human-readable description",
    "correlationId": "uuid-from-logger"
}
```

**Allowed Error Codes**:
- `VALIDATION_ERROR` - Invalid input
- `NOT_FOUND` - Resource not found
- `UNAUTHORIZED` - Missing/invalid auth
- `FORBIDDEN` - Insufficient permissions
- `INTERNAL_ERROR` - System failure

**NO hidden retries or self-healing** - fail fast and surface errors.

### 1.5 Security Requirements (MANDATORY)

```python
# Config management
from shared.config.secrets import get_secret

# CORRECT
api_key = get_secret("anthropic/api_key")

# FORBIDDEN
api_key = "sk-ant-..."  # NEVER hardcode secrets
```

**ALL inputs MUST be validated** using Pydantic models in DTOs.

### 1.6 Testing Requirements

**MUST generate**:
- Unit tests for services
- Unit tests for repositories
- Integration test for handler

**Template**:
```python
# tests/unit/test_user_service.py
import pytest
from unittest.mock import Mock
from src.services.user_service import UserService
from src.dto.request import CreateUserRequest

def test_create_user_success():
    """Test successful user creation."""
    # Arrange
    mock_repo = Mock()
    mock_repo.exists_by_email.return_value = False
    service = UserService(repository=mock_repo)

    request = CreateUserRequest(
        email="test@example.com",
        name="Test User"
    )

    # Act
    user = service.create_user(request)

    # Assert
    assert user.email == "test@example.com"
    mock_repo.save.assert_called_once()

def test_create_user_duplicate_email():
    """Test duplicate email rejection."""
    # Arrange
    mock_repo = Mock()
    mock_repo.exists_by_email.return_value = True
    service = UserService(repository=mock_repo)

    request = CreateUserRequest(
        email="test@example.com",
        name="Test User"
    )

    # Act & Assert
    with pytest.raises(ValueError, match="already exists"):
        service.create_user(request)
```

---

## 2. FRONTEND ARCHITECTURE (Angular)

### 2.1 Mandatory Directory Structure

```
frontend/src/app/
  core/           # Singleton services, guards, interceptors
  shared/         # Shared components, pipes, directives
  features/       # Feature modules
    {feature}/
      components/
      services/
      models/
      {feature}.routes.ts
  services/       # Global services
  interceptors/   # HTTP interceptors
  guards/         # Route guards
  models/         # Shared models
```

### 2.2 Component Requirements (STRICT)

**MUST use standalone components**:

```typescript
import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-user-form',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './user-form.component.html',
  styleUrls: ['./user-form.component.scss']
})
export class UserFormComponent {
  // Implementation
}
```

**MUST use OnPush change detection**:

```typescript
import { ChangeDetectionStrategy } from '@angular/core';

@Component({
  changeDetection: ChangeDetectionStrategy.OnPush,
  // ...
})
```

**MUST use strict typing**:

```typescript
// tsconfig.json must have
{
  "compilerOptions": {
    "strict": true,
    "noImplicitAny": true,
    "strictNullChecks": true
  }
}
```

### 2.3 Service Layer

**MUST use RxJS for async operations**:

```typescript
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError, map, retry } from 'rxjs/operators';
import { User, CreateUserRequest } from '../models/user.model';

@Injectable({ providedIn: 'root' })
export class UserService {
  private readonly apiUrl = '/api/users';

  constructor(private http: HttpClient) {}

  createUser(request: CreateUserRequest): Observable<User> {
    return this.http.post<User>(this.apiUrl, request).pipe(
      retry(1),
      catchError(this.handleError)
    );
  }

  private handleError(error: any): Observable<never> {
    console.error('API Error:', error);
    return throwError(() => new Error(error.error?.message || 'Server error'));
  }
}
```

### 2.4 HTTP Interceptor (MANDATORY)

```typescript
import { Injectable } from '@angular/core';
import { HttpInterceptor, HttpRequest, HttpHandler, HttpEvent } from '@angular/common/http';
import { Observable } from 'rxjs';
import { v4 as uuidv4 } from 'uuid';

@Injectable()
export class CorrelationIdInterceptor implements HttpInterceptor {
  intercept(req: HttpRequest<any>, next: HttpHandler): Observable<HttpEvent<any>> {
    const correlationId = uuidv4();

    const clonedRequest = req.clone({
      setHeaders: {
        'X-Correlation-Id': correlationId,
        'Authorization': `Bearer ${this.getToken()}`
      }
    });

    return next.handle(clonedRequest);
  }

  private getToken(): string {
    return localStorage.getItem('authToken') || '';
  }
}
```

### 2.5 Route Guards

```typescript
import { Injectable } from '@angular/core';
import { CanActivate, Router } from '@angular/router';
import { AuthService } from '../services/auth.service';

@Injectable({ providedIn: 'root' })
export class AuthGuard implements CanActivate {
  constructor(
    private authService: AuthService,
    private router: Router
  ) {}

  canActivate(): boolean {
    if (this.authService.isAuthenticated()) {
      return true;
    }

    this.router.navigate(['/login']);
    return false;
  }
}
```

---


## 3. DESIGN PATTERNS (ALLOWED)

**ONLY use these patterns**:
- ✅ Service Layer
- ✅ Repository Pattern
- ✅ Dependency Injection
- ✅ Strategy Pattern (only when multiple implementations exist)
- ✅ Decorator Pattern (for middleware)

**FORBIDDEN patterns**:
- ❌ Visitor
- ❌ Mediator
- ❌ Abstract Factory
- ❌ Complex event buses
- ❌ Meta-programming

---

## 4. OUTPUT FORMAT (STRICT)

ALL generated code MUST be returned in this format:

```
FILE: backend/lambdas/user/src/handlers/user_handler.py
<complete file content>

FILE: backend/lambdas/user/src/services/user_service.py
<complete file content>

FILE: backend/lambdas/user/tests/unit/test_user_service.py
<complete file content>
```

**NEVER** merge multiple modules into one file.

---

## 5. QUALITY GATES (MANDATORY)

Before returning generated code, verify:

- [ ] Follows architectural structure (handlers/services/repositories)
- [ ] No business logic in handlers
- [ ] Services return Domain objects, not DTOs
- [ ] All cross-cutting concerns in middleware/decorators (no manual entry/exit logging in services)
- [ ] Observability included (structured logging via `extra`, tracing, OTel metrics for business ops)
- [ ] No deprecated Python functions (e.g. use `datetime.now(timezone.utc)` instead of `datetime.utcnow()`)
- [ ] Error handling with standard format
- [ ] Security: no hardcoded secrets
- [ ] Secrets from AWS Secrets Manager/SSM
- [ ] Input validation via Pydantic/schema
- [ ] Type hints on all functions (Python)
- [ ] Strict typing enabled (TypeScript)
- [ ] Unit tests included
- [ ] Code compiles without errors
- [ ] Follows language best practices (PEP 8, Angular style guide)

---

## 6. SIMPLICITY MANDATE

**Code MUST be understandable by a mid-level engineer within 5 minutes.**

**Avoid**:
- Unnecessary abstractions
- Meta-programming
- Dynamic code generation
- Overly generic frameworks
- Clever tricks

**Prefer**:
- Explicit over implicit
- Verbose over clever
- Standard patterns over novel approaches
- Boring, predictable code

---

## 7. WHAT NOT TO GENERATE

**NEVER introduce**:
- Autonomous refactoring behavior
- Self-healing logic
- Hidden retry mechanisms
- Unnecessary architectural complexity
- Academic design patterns
- Framework-building abstractions

---

## 8. EXECUTION CHECKLIST

When generating code:

1. **Identify layer** (handler, service, repository, etc.)
2. **Verify separation of concerns** enforced
3. **Add observability hooks** (logging, tracing, metrics)
4. **Implement error handling** with standard format
5. **Add security** (no secrets, validate inputs)
6. **Generate tests** (unit minimum)
7. **Verify simplicity** (5-minute rule)
8. **Format output** (FILE: path format)
9. **Run quality gates** (all checkboxes)
10. **Return code**

---

**END OF SPECIFICATION**

This skill generates code that is simple, maintainable, observable, secure, and architecturally sound. No exceptions.
