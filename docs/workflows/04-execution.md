# Phase 4: Task Execution (Implementation)

## Objective
Implement tasks following best practices with AI assistance while maintaining code quality.

## Process

### 1. Task Selection
- Pick task from sprint backlog
- Verify dependencies are complete
- Review task specification and acceptance criteria
- Review shift-left test plan (`docs/specs/{service-name}/test-plan.md`)
- Move task to `tasks/in_progress/`

### 2. Implementation Setup
- Create feature branch: `git checkout -b feature/TASK-XXX`
- Review related design documents in `docs/specs/{service-name}/`
- Identify files to create/modify
- Set up local development environment

### 3. AI-Assisted Development

**Use AI Skills:**

| Skill | File | Purpose |
|-------|------|---------|
| Code Generation (App) | `skills/definitions/code-generation-app.md` | Generate Lambda handlers, services, DTOs |
| Code Generation (CDK) | `skills/definitions/code-generation-cdk.md` | Generate CDK stack definitions |
| Code Review | `skills/definitions/code-review.md` | Automated code review |
| Test Generation | `skills/definitions/test-generation.md` | Generate unit and integration tests |
| Documentation Generation | `skills/definitions/documentation-generation.md` | Generate API and service documentation |

**Best Practices:**
- Follow Python PEP 8 style guide
- Use type hints in Python code
- Follow Angular style guide for frontend
- Write clean, readable, maintainable code
- Add comments only where necessary (code should be self-documenting)
- Handle errors using standard `ErrorResponse` format
- Instrument with OpenTelemetry using the `@observe` decorator

### 4. Code Development Standards

**Backend (Python) — Clean Architecture:**
```python
# Handler layer — thin, delegates to service
from src.services.calculator_service import CalculatorService
from src.dto.request import CalculatorRequest
from src.dto.response import CalculatorResponse, ErrorResponse
from shared.middleware.api_gateway_handler import api_gateway_handler

@api_gateway_handler(service_class=CalculatorService)
def lambda_handler(event, context):
    pass  # Decorator handles routing, error mapping, CORS

# Service layer — business logic with observability
from shared.middleware.observability import observe

class CalculatorService:
    @observe(operation="calculate", metric_prefix="calculator")
    def calculate(self, request: CalculatorRequest) -> CalculatorResponse:
        # Pure business logic only
        result = request.num1 + request.num2
        return CalculatorResponse(result=result)

# DTO layer — Pydantic models for validation
from pydantic import BaseModel, validator

class CalculatorRequest(BaseModel):
    num1: float
    num2: float
    operation: str

    @validator('operation')
    def validate_operation(cls, v):
        if v not in ('add', 'subtract', 'multiply', 'divide'):
            raise ValueError(f"Unsupported operation: {v}")
        return v
```

**Frontend (Angular):**
- Use TypeScript strict mode
- Follow component-service pattern
- Use RxJS observables for async operations
- Implement proper error handling with `ErrorInterceptor`
- Use Angular best practices

**Infrastructure (CDK):**
- Use `self.config` dictionary pattern from `infra/config.json`
- Shared Cognito User Pool from `AuthStack` (never create per-stack)
- ADOT Lambda Layer for OpenTelemetry (mandatory `AWS_LAMBDA_EXEC_WRAPPER`)
- WAF WebACL with AWS Managed Rules on every API Gateway
- `data_trace_enabled=(stage != "prod")` — never in production
- CORS origins from config
- Follow `skills/definitions/code-generation-cdk.md`

### 5. Testing During Development
- Write unit tests alongside code (TDD when possible)
- Tests located at `backend/lambdas/{name}/tests/unit/`
- Integration tests at `backend/lambdas/{name}/tests/integration/`
- Reference shift-left test plan for required coverage
- Test edge cases and error conditions
- Run tests locally before committing
- Aim for >80% code coverage

### 6. Code Review Process
1. Self-review: Review your own code first
2. Run code-review skill (`skills/definitions/code-review.md`)
3. Run all tests
4. Check linting and formatting
5. Verify acceptance criteria met
6. Create pull request
7. Address review feedback

### 7. Documentation
Update relevant documentation:
- API documentation via `skills/definitions/documentation-generation.md`
- Service docs in `docs/specs/{service-name}/`
- Architecture decision records (ADRs)

### 8. Commit Standards
Follow conventional commits:
```bash
feat: add user authentication handler
fix: resolve API Gateway CORS issue
docs: update API documentation
test: add integration tests for agents
refactor: simplify Lambda layer structure
```

## Patterns Referenced

| Pattern | File | When to Apply |
|---------|------|---------------|
| Layer Architecture | `skills/patterns/layer-architecture.md` | All backend code |
| Error Response Format | `skills/patterns/error-response-format.md` | All API error handling |
| OpenTelemetry Template | `skills/patterns/opentelemetry-template.md` | All Lambda functions |
| Observability Requirements | `skills/patterns/observability-requirements.md` | All services |
| IAM Least Privilege | `skills/patterns/iam-least-privilege.md` | All IAM roles |
| API Routing Strategy | `skills/patterns/api-routing-strategy.md` | All API endpoints |
| DynamoDB Configuration | `skills/patterns/dynamodb-configuration.md` | All DynamoDB tables |
| Development Best Practices | `skills/patterns/development-best-practices.md` | All code |
| Scaffolding Strategy | `skills/patterns/scaffolding-strategy.md` | New service creation |

## Development Workflow

```
1. Pick task from backlog
2. Create feature branch
3. Review shift-left test plan
4. Use AI to generate initial code (code-generation-app / code-generation-cdk)
5. Instrument with @observe decorator and structured logging
6. Write tests (reference test-plan.md traceability matrix)
7. Run tests locally
8. Run code-review skill
9. Fix issues
10. Commit with conventional commit message
11. Push to remote
12. Create pull request
13. Address feedback
14. Merge to main
15. Move task to completed
```

## Quality Gates
Before marking task complete:
- [ ] All acceptance criteria met
- [ ] Unit tests written and passing
- [ ] Integration tests passing (if applicable)
- [ ] Code reviewed (self + code-review skill)
- [ ] OpenTelemetry instrumentation in place (@observe decorator)
- [ ] Error responses follow standard format (ErrorResponse DTO)
- [ ] Documentation updated
- [ ] No linting errors
- [ ] Committed to version control

## Outputs
- Working code committed to repository
- Tests passing
- Documentation updated in `docs/specs/{service-name}/`
- Task moved to `tasks/completed/`
- Ready for Phase 5 (Testing)

## Next Phase
-> [Phase 5: Testing](05-testing.md)
