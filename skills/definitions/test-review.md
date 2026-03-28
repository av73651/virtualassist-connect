# Test Review Skill - Enterprise Specification

## Directive

This skill validates test quality, coverage, and traceability to acceptance criteria before marking implementation as complete.

**Primary Goal**: Ensure comprehensive, high-quality test suites that validate all requirements and acceptance criteria.

**Critical Gate**: No task marked complete until test review passes and receives explicit developer approval.

---

## 1. REVIEW SCOPE

The test review validates:
- Unit tests in `backend/lambdas/{function}/tests/unit/`
- Integration tests in `backend/lambdas/{function}/tests/integration/`
- Test fixtures and mocks
- Test configuration files (pytest.ini, conftest.py)
- Acceptance criteria from `docs/specs/lambdas/{name}/{name}-requirements.md`
- Implementation from current task

**Output**: `docs/specs/{service-name}/reviews/test-review-{task-id}-report.md`

---

## 2. REVIEW DIMENSIONS

### 2.1 Test Coverage

#### Code Coverage Metrics
- [ ] **CRITICAL**: Overall coverage ≥ 80%
- [ ] Handler layer coverage ≥ 90%
- [ ] Service layer coverage ≥ 95%
- [ ] Repository layer coverage ≥ 85%
- [ ] DTO/Domain models coverage ≥ 100%
- [ ] Utility functions coverage ≥ 90%
- [ ] Line coverage reported
- [ ] Branch coverage reported
- [ ] Function coverage reported

**Coverage Tool**: pytest-cov
```bash
pytest --cov=src --cov-report=term-missing --cov-report=html
```

#### Uncovered Code Analysis
- [ ] Identify uncovered lines
- [ ] Justify any uncovered critical code
- [ ] Ensure uncovered code is truly unreachable or defensive

**Acceptable Uncovered Code**:
- Defensive error handling that's hard to trigger
- Main/CLI entry points (not handlers)
- Type checking code blocks (if TYPE_CHECKING)

**Unacceptable Uncovered Code**:
- Business logic
- Error handling for common scenarios
- Data transformation logic
- Validation logic

**Score**: Coverage: __/100

---

### 2.2 Acceptance Criteria Traceability

#### AC-to-Test Mapping
- [ ] **CRITICAL**: Every acceptance criterion has at least one test
- [ ] Test names reference AC IDs where applicable
- [ ] Traceability matrix generated: AC ↔ Test

**Example Mapping**:
```
REQ-001: User can log in with valid credentials
  AC-001: Login succeeds with correct email and password
    → test_login_success_with_valid_credentials_AC_001()
  AC-002: Login returns JWT token valid for 24 hours
    → test_login_returns_valid_jwt_token_AC_002()
  AC-003: Login completes within 2 seconds
    → test_login_response_time_under_2_seconds_AC_003()
```

#### Missing Test Coverage
- [ ] Identify ACs without tests
- [ ] Identify tests not mapped to ACs (nice but not critical)
- [ ] Prioritize missing critical AC tests

**Traceability Matrix Template**:
| AC ID | AC Description | Test Name | Status |
|-------|----------------|-----------|--------|
| AC-001 | Login succeeds | test_login_success_AC_001 | ✅ PASS |
| AC-002 | Returns JWT | test_login_jwt_AC_002 | ✅ PASS |
| AC-003 | < 2 sec | test_login_latency_AC_003 | ⚠️ MISSING |

**Score**: AC Traceability: __/100

---

### 2.3 Test Quality

#### Arrange-Act-Assert Pattern
- [ ] **CRITICAL**: All tests follow AAA pattern
- [ ] Clear separation between setup, execution, assertion
- [ ] Comments or blank lines separate sections

**Good Example**:
```python
def test_create_user_with_valid_data():
    # Arrange
    user_repo = Mock(UserRepository)
    service = UserService(user_repo)
    request = CreateUserDto(email="test@example.com", name="Test User")

    # Act
    result = service.create_user(request)

    # Assert
    assert result.email == "test@example.com"
    assert result.name == "Test User"
    user_repo.save.assert_called_once()
```

**Bad Example**:
```python
def test_user():
    service = UserService(Mock())
    result = service.create_user(CreateUserDto(email="test@example.com", name="Test"))
    assert result.email == "test@example.com"
    # Mixed arrange/act/assert
```

#### Test Independence
- [ ] **CRITICAL**: Tests run independently
- [ ] No shared state between tests
- [ ] Tests can run in any order
- [ ] Tests clean up after themselves
- [ ] No test depends on another test

**Anti-Pattern**:
```python
# BAD: Shared state
class TestUserService:
    user = None

    def test_create_user(self):
        self.user = service.create_user(...)  # Sets shared state

    def test_get_user(self):
        user = service.get_user(self.user.id)  # Depends on previous test
```

**Good Pattern**:
```python
# GOOD: Each test independent
def test_create_user():
    user = service.create_user(...)
    assert user.id is not None

def test_get_user():
    # Arrange: Set up test data independently
    existing_user = service.create_user(...)

    # Act: Test retrieval
    retrieved_user = service.get_user(existing_user.id)

    # Assert
    assert retrieved_user.id == existing_user.id
```

#### Test Naming
- [ ] Test names descriptive and clear
- [ ] Test names follow convention: `test_{function}_{scenario}_{expected_outcome}`
- [ ] Test names reference AC IDs when applicable

**Good Names**:
- `test_create_user_with_valid_data_succeeds()`
- `test_create_user_with_duplicate_email_raises_error()`
- `test_login_with_invalid_password_returns_401_AC_005()`

**Bad Names**:
- `test_user()` (too vague)
- `test_1()` (meaningless)
- `test_create()` (incomplete)

#### Single Assertion Principle
- [ ] Tests focus on one behavior
- [ ] Multiple assertions OK if testing same behavior
- [ ] Complex tests split into multiple tests

**Good**:
```python
def test_create_user_saves_to_repository():
    # Single behavior: user is saved
    service.create_user(request)
    user_repo.save.assert_called_once()

def test_create_user_returns_user_with_id():
    # Single behavior: returns user
    result = service.create_user(request)
    assert result.id is not None
```

**Bad**:
```python
def test_create_user():
    # Multiple unrelated behaviors
    result = service.create_user(request)
    assert result.id is not None
    user_repo.save.assert_called_once()
    assert len(result.email) > 0
    assert service.count() == 1
```

**Score**: Test Quality: __/100

---

### 2.4 Test Scenarios

#### Happy Path Coverage
- [ ] **CRITICAL**: All happy paths tested
- [ ] Successful operations verified
- [ ] Expected outputs validated
- [ ] Side effects verified (e.g., database saves)

#### Error Path Coverage
- [ ] **CRITICAL**: All error scenarios tested
- [ ] Validation errors tested
- [ ] Business rule violations tested
- [ ] External system failures tested (API, database)
- [ ] Exception types verified
- [ ] Error messages validated

#### Edge Cases
- [ ] Boundary values tested (min, max, zero, negative)
- [ ] Empty inputs tested (empty string, empty list)
- [ ] Null/None inputs tested
- [ ] Large inputs tested (within reason)
- [ ] Special characters tested (in strings)
- [ ] Concurrent scenarios tested (if applicable)

#### Example Scenario Coverage for User Creation:
- [ ] Valid user data (happy path)
- [ ] Duplicate email (error path)
- [ ] Invalid email format (validation error)
- [ ] Missing required fields (validation error)
- [ ] Empty string fields (edge case)
- [ ] Very long name (edge case)
- [ ] Special characters in name (edge case)
- [ ] Database failure (error path)
- [ ] Repository raises exception (error path)

**Score**: Scenario Coverage: __/100

---

### 2.5 Mocking Strategy

#### Proper Mocking
- [ ] **CRITICAL**: External dependencies mocked
- [ ] AWS services mocked (boto3 calls)
- [ ] External APIs mocked
- [ ] Time/date functions mocked (if time-sensitive)
- [ ] Random functions mocked (for determinism)
- [ ] Mocks verify correct usage

**What to Mock**:
- boto3 DynamoDB/S3 clients
- HTTP requests (requests library)
- datetime.now() / time.time()
- random.random()
- External service SDKs
- File system operations (in unit tests)

**What NOT to Mock**:
- Code under test (the actual function being tested)
- Simple data classes (DTOs, domain models)
- Pure utility functions
- Standard library data structures (list, dict)

#### Mock Quality
- [ ] Mocks return realistic data
- [ ] Mocks simulate both success and failure
- [ ] Mock assertions verify calls
- [ ] Mock setup clear and readable

**Good Mocking Example**:
```python
def test_get_user_calls_repository():
    # Arrange
    mock_repo = Mock(spec=UserRepository)
    mock_repo.find_by_id.return_value = User(id="123", email="test@example.com")
    service = UserService(mock_repo)

    # Act
    result = service.get_user("123")

    # Assert
    mock_repo.find_by_id.assert_called_once_with("123")
    assert result.id == "123"
```

#### Fixture Usage
- [ ] Test fixtures defined in conftest.py
- [ ] Fixtures reusable across tests
- [ ] Fixtures provide realistic test data
- [ ] Fixtures documented

**Good Fixture Example**:
```python
# conftest.py
import pytest

@pytest.fixture
def valid_user_dto():
    return CreateUserDto(
        email="test@example.com",
        name="Test User"
    )

@pytest.fixture
def mock_user_repository():
    return Mock(spec=UserRepository)

# test_user_service.py
def test_create_user(valid_user_dto, mock_user_repository):
    service = UserService(mock_user_repository)
    service.create_user(valid_user_dto)
    mock_user_repository.save.assert_called_once()
```

**Score**: Mocking Quality: __/100

---

### 2.6 Integration Tests

#### Integration Test Coverage
- [ ] API Gateway → Lambda integration tested
- [ ] Lambda → DynamoDB integration tested
- [ ] Lambda → S3 integration tested
- [ ] Lambda → EventBridge integration tested
- [ ] Lambda → Lambda communication tested (if applicable)
- [ ] End-to-end workflows tested

#### Integration Test Quality
- [ ] Use real AWS services (localstack, moto, or dev environment)
- [ ] Test complete request/response flow
- [ ] Verify data persistence
- [ ] Test error handling across boundaries
- [ ] Test authentication/authorization flow

**Integration Test Example**:
```python
@pytest.mark.integration
def test_create_user_end_to_end():
    # Arrange: Set up real DynamoDB table (localstack)
    dynamodb = boto3.resource('dynamodb', endpoint_url='http://localhost:4566')
    table = dynamodb.Table('Users')

    # Act: Invoke Lambda with API Gateway event
    event = {
        'httpMethod': 'POST',
        'path': '/users',
        'body': json.dumps({'email': 'test@example.com', 'name': 'Test'})
    }
    response = lambda_handler(event, {})

    # Assert: Verify response
    assert response['statusCode'] == 201

    # Assert: Verify data persisted in DynamoDB
    item = table.get_item(Key={'PK': 'USER#123'})
    assert item['Item']['email'] == 'test@example.com'
```

#### Integration Test Markers
- [ ] Integration tests marked with `@pytest.mark.integration`
- [ ] Can run unit tests separately from integration tests
- [ ] Integration tests in separate directory or clearly marked

**Score**: Integration Tests: __/100

---

### 2.7 Test Configuration

#### pytest Configuration
- [ ] `pytest.ini` or `pyproject.toml` present
- [ ] Test discovery configured
- [ ] Coverage thresholds set
- [ ] Markers defined (unit, integration, slow)

**Example pytest.ini**:
```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
markers =
    unit: Unit tests (fast, mocked dependencies)
    integration: Integration tests (slower, real services)
    slow: Slow tests
addopts =
    --cov=src
    --cov-report=term-missing
    --cov-report=html
    --cov-fail-under=80
    -v
```

#### Test Dependencies
- [ ] requirements.txt or pyproject.toml includes test dependencies
- [ ] pytest
- [ ] pytest-cov (coverage)
- [ ] pytest-mock (mocking)
- [ ] moto (AWS mocking) or localstack
- [ ] faker (test data generation)

#### conftest.py
- [ ] Shared fixtures defined
- [ ] Setup/teardown logic
- [ ] Mock configurations

**Score**: Test Configuration: __/100

---

### 2.8 Test Maintainability

#### Code Duplication
- [ ] Test setup extracted to fixtures
- [ ] Common assertions extracted to helpers
- [ ] No copy-paste test code

#### Readability
- [ ] Tests easy to understand
- [ ] Test intent clear from name and structure
- [ ] Comments used sparingly (only for complex setup)

#### Test Data
- [ ] Test data realistic and meaningful
- [ ] Use faker or factory patterns for complex data
- [ ] Avoid magic numbers/strings

**Good Test Data**:
```python
def test_create_user():
    # Clear, realistic test data
    request = CreateUserDto(
        email="john.doe@example.com",
        name="John Doe",
        role="admin"
    )
```

**Bad Test Data**:
```python
def test_create_user():
    # Meaningless test data
    request = CreateUserDto(
        email="a@b.c",
        name="x",
        role="r"
    )
```

**Score**: Maintainability: __/100

---

## 3. REVIEW OUTPUT FORMAT

### 3.1 Review Report Structure

**File**: `docs/specs/{service-name}/reviews/test-review-{task-id}-report.md`

```markdown
# Test Review Report - {Task ID}

**Date**: YYYY-MM-DD
**Reviewer**: [AI/Developer Name]
**Task**: {Task ID} - {Task Name}
**Code Version**: [Git commit]
**Status**: [PASS / CONDITIONAL PASS / FAIL]

---

## Executive Summary

[2-3 paragraph summary of test quality]

**Overall Test Score**: __/100

**Recommendation**:
- [ ] ✅ APPROVED - Tests complete and high quality
- [ ] ⚠️ CONDITIONAL - Address issues below before marking task complete
- [ ] ❌ BLOCKED - Insufficient test coverage or quality

---

## Score Breakdown

| Dimension | Score | Status |
|-----------|-------|--------|
| Code Coverage | __/100 | PASS/FAIL |
| AC Traceability | __/100 | PASS/FAIL |
| Test Quality | __/100 | PASS/FAIL |
| Scenario Coverage | __/100 | PASS/FAIL |
| Mocking Quality | __/100 | PASS/FAIL |
| Integration Tests | __/100 | PASS/FAIL |
| Test Configuration | __/100 | PASS/FAIL |
| Maintainability | __/100 | PASS/FAIL |
| **TOTAL** | **__/100** | **PASS/FAIL** |

**Passing Criteria**:
- Overall score ≥ 80%
- Code coverage ≥ 80%
- All acceptance criteria have tests
- No CRITICAL issues

---

## Coverage Report

### Overall Coverage: XX%

| Module | Coverage | Status |
|--------|----------|--------|
| handlers/ | XX% | PASS/FAIL |
| services/ | XX% | PASS/FAIL |
| repositories/ | XX% | PASS/FAIL |
| domain/ | XX% | PASS/FAIL |
| dto/ | XX% | PASS/FAIL |

### Uncovered Code

**Critical Uncovered Lines**:
- `src/services/user_service.py:45-48` - Business logic for duplicate check
- `src/repositories/user_repository.py:67` - Error handling for DynamoDB failure

**Acceptable Uncovered Lines**:
- `src/handlers/user_handler.py:12` - Defensive error handling (hard to trigger)

**Action Required**:
- Add tests for critical uncovered lines
- Justify or remove acceptable uncovered code if possible

---

## Acceptance Criteria Traceability

### Traceability Matrix

| AC ID | AC Description | Test Name | Status |
|-------|----------------|-----------|--------|
| AC-001 | User created with valid data | test_create_user_with_valid_data_AC_001 | ✅ PASS |
| AC-002 | Duplicate email rejected | test_create_user_duplicate_email_AC_002 | ✅ PASS |
| AC-003 | Invalid email format rejected | test_create_user_invalid_email_AC_003 | ❌ MISSING |
| AC-004 | User saved to database | test_create_user_saves_to_db_AC_004 | ✅ PASS |

### Missing AC Tests (count: X)
- [AC-MISSING-001] AC-003 has no corresponding test
  - **Impact**: HIGH - Validation requirement not verified
  - **Action**: Add test for invalid email format

---

## Test Quality Analysis

### ✅ High-Quality Tests (count: X)
- `test_create_user_with_valid_data_AC_001()` - Clear AAA pattern, good assertions
- `test_get_user_by_id_AC_005()` - Proper mocking, verifies repository call

### ❌ Quality Issues (count: X)

**[QUALITY-001] Test does not follow AAA pattern**
- **Test**: `test_update_user()`
- **Location**: `tests/unit/test_user_service.py:45`
- **Issue**: Arrange/Act/Assert mixed together
- **Impact**: MEDIUM - Hard to understand
- **Fix**: Separate into clear AAA sections

**[QUALITY-002] Test has shared state**
- **Test**: `TestUserService` class
- **Location**: `tests/unit/test_user_service.py:12-50`
- **Issue**: Tests share class-level variables
- **Impact**: HIGH - Tests not independent, may fail randomly
- **Fix**: Remove shared state, use fixtures

**[QUALITY-003] Test name not descriptive**
- **Test**: `test_user()`
- **Location**: `tests/unit/test_user_service.py:78`
- **Issue**: Name doesn't describe scenario or expectation
- **Impact**: LOW - Hard to understand test purpose
- **Fix**: Rename to `test_create_user_with_valid_data_succeeds()`

---

## Scenario Coverage Analysis

### Happy Path Coverage
✅ All happy paths covered

### Error Path Coverage
⚠️ Missing error scenarios:
- [ERROR-001] No test for DynamoDB connection failure
  - **Impact**: HIGH - Error handling not verified
  - **Action**: Add test with mocked boto3 exception

- [ERROR-002] No test for invalid JSON in request body
  - **Impact**: MEDIUM
  - **Action**: Add test for malformed JSON

### Edge Case Coverage
⚠️ Missing edge cases:
- [EDGE-001] No test for empty string in name field
  - **Impact**: MEDIUM
  - **Action**: Add test for boundary condition

- [EDGE-002] No test for very long name (>255 characters)
  - **Impact**: LOW
  - **Action**: Add test for maximum length validation

---

## Mocking Analysis

### ✅ Good Mocking Examples
- `test_create_user()` properly mocks UserRepository
- `test_get_user()` verifies repository method called with correct args

### ❌ Mocking Issues

**[MOCK-001] Real DynamoDB client used in unit test**
- **Test**: `test_save_user()`
- **Location**: `tests/unit/test_user_repository.py:23`
- **Issue**: Uses real boto3 client instead of mock
- **Impact**: HIGH - Unit test calling external service
- **Fix**: Use moto or Mock(boto3.resource)

**[MOCK-002] Mock not verified**
- **Test**: `test_create_user()`
- **Location**: `tests/unit/test_user_service.py:34`
- **Issue**: Mock created but no assertions on calls
- **Impact**: MEDIUM - Not verifying dependency usage
- **Fix**: Add `mock_repo.save.assert_called_once_with(...)`

---

## Integration Test Analysis

### Integration Test Count: X

### ✅ Good Integration Tests
- `test_create_user_end_to_end()` - Tests full API → Lambda → DynamoDB flow

### ⚠️ Integration Test Gaps
- [INTEGRATION-001] No integration test for authentication flow
  - **Impact**: HIGH
  - **Action**: Add test with Cognito mock

- [INTEGRATION-002] No integration test for error responses
  - **Impact**: MEDIUM
  - **Action**: Add test for 400/500 error scenarios

---

## Test Configuration Review

### pytest.ini
- ✅ Present and properly configured
- ✅ Coverage threshold set to 80%
- ✅ Markers defined

### Test Dependencies
- ✅ All required test libraries in requirements.txt
- ⚠️ Missing moto for AWS mocking
  - **Action**: Add `moto[dynamodb,s3]` to requirements.txt

### conftest.py
- ✅ Fixtures defined
- ⚠️ Some fixtures could be more generic
  - **Suggestion**: Extract common user fixtures

---

## Issue Summary

| Severity | Count | Must Fix Before Approval |
|----------|-------|--------------------------|
| ❌ CRITICAL | X | YES |
| ⚠️ MAJOR | X | YES |
| ⚠️ MINOR | X | NO (but recommended) |
| ℹ️ INFO | X | NO |

---

## Recommended Actions

### Before Task Can Be Marked Complete (CRITICAL/MAJOR):
1. [COVERAGE] Increase coverage to 80% (currently XX%)
2. [AC-MISSING-001] Add test for AC-003
3. [ERROR-001] Add test for DynamoDB failure
4. [MOCK-001] Replace real DynamoDB with mock in unit tests
5. [QUALITY-002] Fix shared state in TestUserService

### Recommended Improvements (MINOR):
1. [QUALITY-003] Rename vague test names
2. [EDGE-001] Add edge case tests
3. [INTEGRATION-001] Add authentication integration test

---

## Test Execution Results

```
======================== test session starts =========================
collected 15 items

tests/unit/test_user_handler.py::test_create_user_handler PASSED
tests/unit/test_user_service.py::test_create_user PASSED
tests/unit/test_user_service.py::test_get_user PASSED
tests/unit/test_user_repository.py::test_save_user PASSED
...

---------- coverage: platform linux, python 3.12.0 -----------
Name                          Stmts   Miss  Cover   Missing
-----------------------------------------------------------
src/handlers/user_handler.py     45      5    89%   12, 45-48
src/services/user_service.py     67      8    88%   34, 67-72
src/repositories/user_repo.py    34      4    88%   23, 45, 67
-----------------------------------------------------------
TOTAL                           146     17    88%

======================== 15 passed in 2.34s ==========================
```

**Result**: 15/15 tests passed, 88% coverage (target: 80%)

---

## Quality Checklist

Developer must verify:
- [ ] All CRITICAL and MAJOR issues resolved
- [ ] Code coverage ≥ 80%
- [ ] All acceptance criteria have tests
- [ ] All tests pass
- [ ] No shared state between tests
- [ ] Proper mocking strategy
- [ ] Integration tests cover critical paths
- [ ] Tests are maintainable and readable

---

## Developer Sign-Off

**Status**: [ ] APPROVED / [ ] CHANGES REQUESTED / [ ] REJECTED

**Developer Name**: _______________
**Date**: _______________
**Comments**:

[Developer comments and additional notes]

---

## Next Steps

If APPROVED:
1. Mark task as complete
2. Merge code to main branch
3. Proceed to next task

If CHANGES REQUESTED:
1. Address issues listed in "Recommended Actions"
2. Add missing tests
3. Re-run tests and coverage
4. Re-run test review
5. Obtain approval

If REJECTED:
1. Significant test gaps or quality issues
2. Revise test strategy
3. Add comprehensive tests
```

---

## 4. REVIEW PROCESS

### 4.1 Review Execution Steps

1. **Run Tests**
   ```bash
   pytest tests/ -v
   ```

2. **Generate Coverage Report**
   ```bash
   pytest --cov=src --cov-report=term-missing --cov-report=html
   ```

3. **Load Acceptance Criteria**
   - Read from `docs/specs/lambdas/{name}/{name}-requirements.md`
   - Identify all ACs for current task

4. **Check Coverage**
   - Verify overall coverage ≥ 80%
   - Identify uncovered critical code
   - Validate coverage by module

5. **Validate AC Traceability**
   - Map each AC to test(s)
   - Identify missing AC tests
   - Create traceability matrix

6. **Assess Test Quality**
   - Check AAA pattern
   - Verify test independence
   - Review test naming
   - Check for single assertion principle

7. **Review Test Scenarios**
   - Verify happy path coverage
   - Check error path coverage
   - Identify missing edge cases

8. **Validate Mocking**
   - Check proper mocking of dependencies
   - Verify mock assertions
   - Check fixture quality

9. **Review Integration Tests**
   - Verify integration test presence
   - Check end-to-end coverage
   - Validate real service usage

10. **Generate Report**
    - Create test review report
    - Categorize issues
    - Provide recommendations

11. **Developer Approval Gate**
    - Developer reviews report
    - Developer runs tests locally
    - Developer addresses issues
    - Developer explicitly approves

---

## 5. SEVERITY DEFINITIONS

### ❌ CRITICAL
- **Definition**: Major test gap or quality issue
- **Impact**: Implementation not validated
- **Must Fix**: YES
- **Examples**: Coverage < 80%, missing AC tests, tests not independent

### ⚠️ MAJOR
- **Definition**: Significant test issue
- **Impact**: Test suite unreliable or incomplete
- **Must Fix**: YES
- **Examples**: Missing error scenarios, poor mocking, no integration tests

### ⚠️ MINOR
- **Definition**: Test quality improvement opportunity
- **Impact**: Tests work but not optimal
- **Must Fix**: NO, but recommended
- **Examples**: Test naming, minor edge cases missing

### ℹ️ INFO
- **Definition**: Suggestion or best practice
- **Impact**: None
- **Must Fix**: NO

---

## 6. APPROVAL CRITERIA

### PASS (Task Complete)
- Overall score ≥ 80%
- Code coverage ≥ 80%
- All acceptance criteria have tests
- All tests pass
- No CRITICAL issues
- No MAJOR issues
- Developer sign-off

### CONDITIONAL PASS
- Overall score ≥ 70%
- Code coverage ≥ 75%
- Most ACs have tests
- Some MAJOR issues with mitigation plans
- Developer sign-off with conditions

### FAIL (Task Not Complete)
- Overall score < 70%
- Code coverage < 75%
- Missing critical AC tests
- Tests failing
- Unresolved CRITICAL issues

---

## 7. INTEGRATION WITH WORKFLOW

### When to Run Test Review
- After code generation complete
- After tests generated/written
- Before marking task complete
- Before merging to main branch

### Review Frequency
- Per task (for granular feedback)
- OR per feature (for batch of related tasks)
- Always before PR approval

---

**Comprehensive, high-quality tests are essential for maintaining code quality and preventing regressions. This review ensures tests validate all requirements and provide confidence in the implementation.**
