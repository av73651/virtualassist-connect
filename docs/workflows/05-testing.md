# Phase 5: Testing

## Objective
Ensure code quality, functionality, and reliability through comprehensive shift-left testing strategy.

## Shift-Left Approach

Testing begins in **Phase 2 (Design)**, not after implementation:
1. **Phase 2**: Generate test plan from acceptance criteria (traceability matrix)
2. **Phase 3**: Prepare test fixtures and data
3. **Phase 4**: Write tests alongside code (TDD)
4. **Phase 5**: Execute full test suite, gap analysis, coverage validation

See `skills/definitions/test-generation.md` for the complete shift-left strategy.

## Testing Pyramid

```
        /\
       /E2E\          (Few - High-level scenarios)
      /------\
     /  INTEG \       (Some - Component interactions)
    /----------\
   /    UNIT    \     (Many - Individual functions)
  /--------------\
```

## 1. Unit Testing

### Backend Unit Tests
**Location**: `backend/lambdas/{name}/tests/unit/`

**What to Test:**
- Individual Lambda handler functions
- Service layer business logic
- DTO validation (Pydantic models)
- Domain models
- Shared middleware (observability, error handling)

**Tools:**
- pytest
- pytest-cov (coverage)
- moto (AWS service mocking)

**Example:**
```python
# backend/lambdas/calculator/tests/unit/test_calculator_service.py
import pytest
from src.services.calculator_service import CalculatorService
from src.dto.request import CalculatorRequest

class TestCalculatorService:
    """Tests for CalculatorService — maps to AC-001 through AC-004."""

    def setup_method(self):
        self.service = CalculatorService()

    def test_add_positive_numbers(self):
        """AC-001: Addition returns correct result."""
        request = CalculatorRequest(num1=2, num2=3, operation="add")
        response = self.service.calculate(request)
        assert response.result == 5.0

    def test_divide_by_zero_raises_error(self):
        """AC-004: Division by zero returns VALIDATION_ERROR."""
        request = CalculatorRequest(num1=10, num2=0, operation="divide")
        with pytest.raises(ValueError, match="Cannot divide by zero"):
            self.service.calculate(request)
```

**Standards:**
- Test all public functions
- Test edge cases and error conditions
- Mock external dependencies (AWS services via moto)
- Reference acceptance criteria in test docstrings
- Aim for >80% coverage

### Frontend Unit Tests
**Location**: `frontend/src/app/**/*.spec.ts`

**What to Test:**
- Component logic
- Services
- Pipes and directives
- Guards and interceptors (especially `ErrorInterceptor`)

**Tools:**
- Jasmine
- Karma
- Angular Testing utilities

**Standards:**
- Test component inputs/outputs
- Test service methods
- Mock HTTP calls
- Test error handling against standard `ApiError` interface

## 2. Integration Testing

**Location**: `backend/lambdas/{name}/tests/integration/`

**What to Test:**
- API Gateway + Lambda integration
- Lambda + DynamoDB interactions
- Cognito authentication flows
- Error response format compliance
- CORS headers
- OpenTelemetry trace propagation

**Approach:**
- Deploy to dev environment
- Test actual AWS service interactions
- Verify data flow between components
- Test error scenarios return standard `ErrorResponse` format

**Example:**
```python
# backend/lambdas/calculator/tests/integration/test_api_integration.py
import os
import pytest
import requests

API_ENDPOINT = os.environ.get("API_ENDPOINT")

@pytest.mark.integration
class TestCalculatorAPIIntegration:
    """Integration tests — requires deployed stack and valid auth token."""

    def test_add_endpoint_returns_correct_result(self, auth_token):
        """AC-001: POST /calculate with add operation."""
        response = requests.post(
            f"{API_ENDPOINT}/calculate",
            json={"num1": 5, "num2": 3, "operation": "add"},
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["result"] == 8.0

    def test_unauthenticated_request_returns_401(self):
        """AC-010: Requests without token return UNAUTHORIZED."""
        response = requests.post(
            f"{API_ENDPOINT}/calculate",
            json={"num1": 1, "num2": 1, "operation": "add"}
        )
        assert response.status_code == 401
```

## 3. End-to-End Testing

**Location**: `tests/e2e/`

**What to Test:**
- Complete user workflows
- Multi-step processes
- Cross-service interactions
- Real-world scenarios

**Tools:**
- Playwright or Cypress (frontend)
- Postman/Newman (API)
- AWS SDK (infrastructure validation)

## 4. Performance Testing

**Objectives:**
- Validate response times against acceptance criteria
- Test under load
- Identify bottlenecks
- Verify Lambda concurrency and API Gateway throttling

**Tools:**
- Artillery or k6 (load testing)
- AWS X-Ray + OpenTelemetry traces (distributed tracing)
- CloudWatch dashboards (custom OTel metrics)

**Key Metrics:**
- API response time (p50, p95, p99)
- Lambda cold start times
- Concurrent user capacity
- DynamoDB read/write capacity consumption

## 5. Security Testing

**What to Test:**
- Cognito authentication/authorization
- Input validation (Pydantic DTO rejection)
- Injection protection
- XSS prevention
- WAF rule effectiveness
- API rate limiting (WAF + API Gateway)
- Secrets management

**Tools:**
- OWASP ZAP
- AWS Security Hub
- Snyk or Dependabot (dependency scanning)

**Checklist:**
- [ ] No secrets in code
- [ ] All API endpoints require Cognito auth
- [ ] Input validation via Pydantic DTOs on all endpoints
- [ ] CORS properly configured (origins from config)
- [ ] HTTPS enforced
- [ ] IAM roles follow least privilege (`skills/patterns/iam-least-privilege.md`)
- [ ] WAF WebACL attached to all API Gateways

## 6. Traceability Validation

**Mandatory step** — verify bidirectional traceability:

```
Requirement (REQ-XXX) <-> Acceptance Criteria (AC-XXX) <-> Test Case (test_xxx)
```

- Every acceptance criterion must have at least one test
- Every test must reference its acceptance criterion (in docstring)
- Run gap analysis: identify untested acceptance criteria
- Document gaps in `docs/specs/{service-name}/test-plan.md`

## Testing Workflow

### 1. Continuous Testing (During Development)
```bash
# Run unit tests for a specific Lambda
cd backend/lambdas/calculator && pytest tests/unit/ -v

# Run frontend tests
cd frontend && ng test

# Watch mode for rapid feedback
pytest tests/unit/ --watch
ng test --watch
```

### 2. Pre-Commit Testing
```bash
# Run all unit tests with coverage
cd backend/lambdas/calculator && pytest tests/unit/ --cov=src --cov-report=term-missing

# Lint code
flake8 backend/
ng lint
```

### 3. Integration Testing (After Deployment to Dev)
```bash
# Deploy to dev environment
cd infra && cdk deploy --all -c env=dev

# Run integration tests
API_ENDPOINT=https://xxx.execute-api.region.amazonaws.com/dev \
  pytest backend/lambdas/calculator/tests/integration/ -m integration
```

### 4. E2E Testing (Before Production)
```bash
# Run E2E test suite
cd tests/e2e && npx playwright test
```

## AI Skills Used

| Skill | File | Purpose |
|-------|------|---------|
| Test Generation | `skills/definitions/test-generation.md` | Generate test cases from code and acceptance criteria |
| Test Review | `skills/definitions/test-review.md` | Review test quality, coverage, and traceability |

## Test Documentation

**Location**: `docs/specs/{service-name}/`

Documents to maintain:
- `test-plan.md` — Shift-left test plan with traceability matrix (generated in Phase 2)
- Test results tracked in CI/CD pipeline

## Quality Gates

### Before Merging to Main:
- [ ] All unit tests passing
- [ ] Code coverage >80%
- [ ] No linting errors
- [ ] Traceability matrix: all acceptance criteria covered

### Before Production Deployment:
- [ ] All integration tests passing
- [ ] E2E tests passing
- [ ] Performance tests meet SLAs from acceptance criteria
- [ ] Security scan clean
- [ ] Test review passed (`skills/definitions/test-review.md`)

## APPROVAL GATE - STOP HERE

**CRITICAL**: After completing test execution:
1. Run test-review skill (`skills/definitions/test-review.md`)
2. Verify traceability matrix completeness
3. Present coverage report and gap analysis to developer
4. **STOP - Do NOT proceed to Phase 6**
5. **WAIT for explicit approval**

Only proceed to Phase 6 after developer says "approved" or "proceed"

## Test Maintenance

- Review and update tests with code changes
- Remove obsolete tests
- Keep test data current
- Monitor test execution times
- Refactor slow tests

## Outputs
- Comprehensive test suite (unit + integration + E2E)
- All tests passing
- Test coverage reports (>80%)
- Traceability matrix validated (no gaps)
- Performance test results
- Security scan reports
- Quality gates passed

## Next Phase
-> [Phase 6: Deployment](06-deployment.md)
