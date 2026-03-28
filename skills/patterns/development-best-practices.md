# Development Best Practices & Patterns

## Purpose
Establish the core coding standards, architectural patterns, and AOP (Aspect-Oriented Programming) principles for the repository. This pattern enforces strict typings, clean architecture boundaries, the separation of cross-cutting concerns, and test-driven traceability directly to Acceptance Criteria (ACs).

---

## 1. Clean Architecture Separation

To ensure long-term maintainability, the codebase MUST adhere to strict layer separation.

1. **Domain Layer**: Contains pure business logic and entities. 
   - *Rule*: Cannot import anything from `aws_*` (boto3) or external HTTP clients.
2. **Application (Service) Layer**: Orchestrates use cases. Interacts with Repositories and Domain models.
   - *Rule*: Cannot format HTTP responses or parse API Gateway events.
3. **Infrastructure (Repository) Layer**: Handles external I/O (DynamoDB, S3, APIs).
   - *Rule*: Cannot contain business decision logic.
4. **App (Handler) Layer**: The entry point.
   - *Rule*: Cannot contain business logic. Exists only to parse events, pass them to the Service layer, and format the HTTP response via DTOs/Exceptions.

---

## 2. Aspect-Oriented Programming (AOP)

Enforce the separation of cross-cutting concerns (like logging, authentication, validation, and error handling) from core business logic using Python Decorators and Middleware. This ensures that Service and Domain layers remain pure, readable, and highly testable.

### 2.1 Observability (OpenTelemetry)
Native OpenTelemetry (OTel) is our standard for distributed tracing and metrics.
- **Best Practice:** Use the AWS Distro for OpenTelemetry (ADOT) Lambda layer to handle global invocation tracing automatically. Inside the domain, use `with tracer.start_as_current_span(...)` and structured JSON `logger.info("...", extra={...})` directly with standard Python libraries.

### 2.2 Input Validation
Handlers should never manually inspect `event.get('body')` and write `if` statements.
- **Best Practice:** Create a validation decorator that parses the payload into a strictly typed Pydantic model (DTO), passing the validated DTO to the hander.

### 2.3 Global Exception Handling
Domain and Service layers should throw specific, custom Python Exceptions (e.g., `UserNotFoundError`). They should **never** return HTTP status codes.
- **Best Practice:** An AOP decorator at the Handler level catches these semantic errors and automatically maps them to standardized API responses.

### 2.4 Authentication and Authorization
Security checks must be intercepted before the Handler executes.
- **Best Practice:** Use API Gateway Authorizers for Layer-7 AOP. When in-code checks are required (e.g., fine-grained resource authorization), use AOP security decorators (e.g. `@require_permission()`).

---

## 3. Strong Typing (Python 3.11+)

Dynamically typed code implicitly creates runtime errors and makes reasoning about large codebases impossible.

**Mandatory Rules:**
- Every function argument MUST have a type hint.
- Every function MUST have a return type hint (including `-> None`).
- Use explicit data shapes (e.g., `Pydantic BaseModel` or `dataclasses`) instead of passing generic `dict` structures anywhere outside the immediate Infrastructure parsing layer.
- `mypy` checks MUST pass without ignoring (`# type: ignore`) unless aggressively justified.

**Best Practice:**
```python
from pydantic import BaseModel

class User(BaseModel):
    id: str
    email: str

def fetch_user(user_id: str) -> User | None:
    data = db_repo.get_item(user_id)
    return User(**data) if data else None
```

---

## 4. Function Design & Single Responsibility

- Functions should be short and do exactly one thing.
- If a function contains the word "and" in its natural language description (e.g., "This function fetches the user *and* sends a welcome email"), it is violating single responsibility.
- Use **Early Returns** (Guard Clauses) to avoid deeply nested `if/else` ladders.

**Best Practice (Guard Clauses):**
```python
def process(data: dict) -> bool:
    if not data:
        return False
    
    if not data.get("valid"):
        return False
        
    # logic
    return True
```

---

## 5. Test-Driven Traceability

Tests dictate the behavior of the system. In a spec-driven environment, tests must explicitly trace back to defined Acceptance Criteria (ACs) or Requirements (REQs).

**Mandatory Rules:**
- Avoid testing implementation details (e.g., "Does it call MockDynamoDB.put_item with exactly this structure?"). Test the observable behavior.
- Test names SHOULD reference the AC or REQ ID they satisfy where applicable.

**Testing Pattern (Arrange, Act, Assert):**
```python
def test_user_creation_enforces_unique_email_AC_REQ_001() -> None:
    # Arrange
    service = UserService(mock_user_repo)
    
    # Act & Assert
    with pytest.raises(DuplicateEmailError):
        service.create_user("test@example.com")
```

---

## 6. Ambiguity Resolution

If a requirement is ambiguous or contradictory during development:
- **Rule**: DO NOT GUESS.
- Implementors must halt feature work that relies on the ambiguity, document the issue explicitly as "Open Questions / Ambiguities", propose 1-2 technically safe options, and wait for stakeholder clarification.

---

## 7. Infrastructure as Code (CDK) Best Practices

Cloud infrastructure MUST mirror the strictness of the application code.

**Mandatory Rules:**
- **Zero Hardcoding**: AWS Accounts, Regions, Lambda Memory, Timeouts, and API Gateway Throttling quotas MUST NEVER be hardcoded in Python Stack template definitions.
- **Environment Context Mapping**: All variables across environments (`dev`, `staging`, `prod`) MUST exist in a standalone configuration map (e.g., `infra/config.json`) mapped dynamically into the CDK App.
- **Dynamic ARN Resolution**: When referencing AWS-managed Layers (like OpenTelemetry/ADOT), NEVER hardcode the region string inside the ARN. Use `Stack.of(self).region` to avoid cross-region 403 authorization failures.
- **Native Cross Compilation**: When deploying Python payloads targeting Amazon Linux which contain OS-specific Rust/C binaries (like `pydantic_core`), the deployment process MUST intercept and pull `manylinux2014_x86_64` wheels directly into the `package/` folder via PIP to bypass Docker compilation limits.
