# Phase 5: Testing

## Objective
Ensure code quality, functionality, and reliability through comprehensive testing strategy.

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
**Location**: `backend/tests/unit/`

**What to Test:**
- Individual Lambda handler functions
- Business logic in layers
- Utility functions
- Data models

**Tools:**
- pytest
- pytest-cov (coverage)
- moto (AWS mocking)

**Example:**
```python
# test_handler.py
import pytest
from lambdas.api.handler import lambda_handler

def test_successful_request():
    event = {'httpMethod': 'GET', 'path': '/api/test'}
    response = lambda_handler(event, None)
    assert response['statusCode'] == 200
```

**Standards:**
- Test all public functions
- Test edge cases and error conditions
- Mock external dependencies
- Aim for >80% coverage

### Frontend Unit Tests
**Location**: `frontend/src/app/**/*.spec.ts`

**What to Test:**
- Component logic
- Services
- Pipes and directives
- Guards and interceptors

**Tools:**
- Jasmine
- Karma
- Angular Testing utilities

**Standards:**
- Test component inputs/outputs
- Test service methods
- Mock HTTP calls
- Test error handling

## 2. Integration Testing

**Location**: `tests/integration/`

**What to Test:**
- API Gateway + Lambda integration
- Lambda + AWS services (S3, DynamoDB, etc.)
- Frontend + Backend API integration
- Authentication flows

**Approach:**
- Deploy to test environment
- Test actual AWS service interactions
- Verify data flow between components
- Test error scenarios

**Example Scenarios:**
- User authentication end-to-end
- Data persistence and retrieval
- File upload and storage
- AI agent request/response cycle

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

**Example Scenarios:**
```
1. User Registration Flow
   - Navigate to signup page
   - Fill registration form
   - Verify email
   - Login successfully
   - Access dashboard

2. AI Assistant Interaction
   - Login to application
   - Send message to AI assistant
   - Verify response received
   - Check conversation history
   - Logout
```

## 4. Performance Testing

**Objectives:**
- Validate response times
- Test under load
- Identify bottlenecks
- Verify auto-scaling

**Tools:**
- Artillery or k6 (load testing)
- AWS X-Ray (tracing)
- CloudWatch metrics

**Key Metrics:**
- API response time (p50, p95, p99)
- Lambda cold start times
- Concurrent user capacity
- Database query performance

## 5. Security Testing

**What to Test:**
- Authentication/authorization
- Input validation
- SQL injection protection
- XSS prevention
- API rate limiting
- Secrets management

**Tools:**
- OWASP ZAP
- AWS Security Hub
- Snyk or Dependabot (dependency scanning)

**Checklist:**
- [ ] No secrets in code
- [ ] API endpoints authenticated
- [ ] Input validation on all endpoints
- [ ] CORS properly configured
- [ ] HTTPS enforced
- [ ] IAM roles follow least privilege

## Testing Workflow

### 1. Continuous Testing (During Development)
```bash
# Run unit tests
cd backend && pytest tests/unit/

# Run frontend tests
cd frontend && ng test

# Watch mode for rapid feedback
pytest --watch
ng test --watch
```

### 2. Pre-Commit Testing
```bash
# Run all unit tests
pytest tests/unit/ --cov

# Lint code
flake8 backend/
ng lint
```

### 3. Integration Testing (After Deployment)
```bash
# Deploy to test environment
cd infra && cdk deploy --all -c environment=test

# Run integration tests
pytest tests/integration/

# Run API tests
newman run tests/postman/collection.json
```

### 4. E2E Testing (Before Production)
```bash
# Run E2E test suite
cd tests/e2e
npx playwright test

# Or for API E2E
pytest tests/e2e/
```

## AI Skills to Use

- `test-generator`: Generate test cases from code
- `test-coverage-analyzer`: Identify untested code paths
- `test-data-generator`: Create realistic test data
- `bug-predictor`: Identify potential bug-prone areas

## Test Documentation

**Location**: `docs/testing/`

Documents to maintain:
- `test-plan.md`: Overall testing strategy
- `test-cases.md`: Manual test scenarios
- `test-results.md`: Test execution results

## Quality Gates

### Before Merging to Main:
- [ ] All unit tests passing
- [ ] Code coverage >80%
- [ ] No linting errors
- [ ] Security scan passed

### Before Production Deployment:
- [ ] All integration tests passing
- [ ] E2E tests passing
- [ ] Performance tests meet SLAs
- [ ] Security scan clean
- [ ] Manual smoke testing complete

## Test Maintenance

- Review and update tests with code changes
- Remove obsolete tests
- Keep test data current
- Monitor test execution times
- Refactor slow tests

## Outputs
- ✅ Comprehensive test suite
- ✅ All tests passing
- ✅ Test coverage reports
- ✅ Performance test results
- ✅ Security scan reports
- ✅ Quality gates passed

## Next Phase
→ [Phase 6: Deployment](06-deployment.md)
