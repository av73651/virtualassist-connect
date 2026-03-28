# Test Generation Skill - Enterprise Specification

## Directive

This skill generates comprehensive, high-quality test suites derived from requirements and acceptance criteria using a **shift-left testing approach**. Tests are designed from requirements BEFORE or alongside code — not after implementation.

**Primary Goal**: Generate tests that are traceable to requirements, complete, maintainable, and provide confidence in implementation quality.

**Non-Negotiables**:
- Test cases derived from acceptance criteria and requirements (not reverse-engineered from code)
- All acceptance criteria have corresponding tests
- Test plan created before or alongside implementation
- Code coverage ≥ 80%
- Tests follow Arrange-Act-Assert pattern
- Tests are independent and deterministic
- Proper mocking of external dependencies

---

## 1. SHIFT-LEFT TEST STRATEGY

### 1.1 Test Design from Requirements

Tests MUST be derived from requirements artifacts — NOT from implementation code. The primary inputs for test design are:

1. **Acceptance Criteria** (from `requirements.md`) → Unit and integration test cases
2. **Business Rules** (from `business-rules.md`) → Service layer test cases
3. **Workflows** (from `workflows.md`) → E2E test scenarios
4. **External Interfaces** (from `external-interfaces.md`) → Integration test cases
5. **Technical Requirements** (from `technical-requirements.md`) → Performance/load test criteria

### 1.2 Test Plan Generation

Before writing test code, generate a **test plan** that maps requirements to test cases:

```
Test Plan: {service-name}

Source: docs/specs/{service-name}/requirements.md

| AC ID   | AC Description              | Test Type   | Test Name                                       | Layer     |
|---------|------------------------------|-------------|------------------------------------------------|-----------|
| AC-001  | Create user with valid data  | Unit        | test_create_user_with_valid_data_AC_001        | Service   |
| AC-001  | Create user with valid data  | Integration | test_create_user_api_returns_201_AC_001        | Handler   |
| AC-002  | Reject duplicate email       | Unit        | test_create_user_duplicate_email_AC_002        | Service   |
| AC-003  | Validate email format        | Unit        | test_invalid_email_format_AC_003               | DTO       |
| BR-001  | Auth required for messages   | Integration | test_unauthenticated_request_returns_401       | Handler   |
| WF-001  | User registration flow       | E2E         | test_complete_registration_workflow            | E2E       |
```

**The test plan MUST be generated as the first output artifact**, before any test code.

### 1.3 Test Design Workflow

```
1. Requirements Analysis complete
   ↓
2. Test Plan generated from acceptance criteria, business rules, and workflows
   ↓
3. System Design complete
   ↓
4. Test fixtures and mocks designed from data models and interfaces
   ↓
5. Test code generated (can happen alongside or before implementation)
   ↓
6. Implementation code generated (tests already exist to validate)
   ↓
7. Tests executed, coverage measured, gaps addressed
```

### 1.4 Test Scope

Generate tests for:
- **Unit Tests**: Test individual functions/classes in isolation
- **Integration Tests**: Test component interactions
- **E2E Tests**: Test complete workflows
- **Fixtures & Mocks**: Test data and dependency mocks

**Test Framework**: pytest (Python), Jasmine/Karma (Angular)

---

## 2. UNIT TEST GENERATION

### 2.1 Backend Unit Tests (Python + pytest)

#### Test Structure

**Directory Layout**:
```
backend/lambdas/{function_name}/
  tests/
    unit/
      test_handlers.py
      test_services.py
      test_repositories.py
      test_domain.py
      test_dto.py
    conftest.py
    __init__.py
```

#### Test Naming Convention
- File: `test_{module_name}.py`
- Class: `Test{ClassName}` (optional, for grouping)
- Function: `test_{function}_{scenario}_{expected_outcome}`
- Reference AC: `test_{function}_{scenario}_AC_{id}` (when applicable)

**Examples**:
- `test_create_user_with_valid_data_succeeds()`
- `test_create_user_with_duplicate_email_raises_error_AC_002()`
- `test_get_user_by_id_returns_user_AC_005()`
- `test_get_user_with_invalid_id_returns_none()`

---

### 2.2 Handler Layer Tests

**What to Test**:
- Request parsing
- Response formatting
- Status codes
- Error handling
- Middleware/decorator application

**What to Mock**:
- Service layer
- AWS context
- Cognito authorizer claims

**Template**:
```python
import json
import pytest
from unittest.mock import Mock, patch
from src.handlers.user_handler import lambda_handler, create_user
from src.dto.request import CreateUserDto
from src.dto.response import UserResponse
from src.domain.user import User
from src.services.user_service import UserService

class TestUserHandler:
    """Tests for user handler Lambda function."""

    def test_lambda_handler_routes_post_users(self, mock_service):
        """Test lambda_handler routes POST /users correctly."""
        # Arrange
        event = {
            'resource': '/users',
            'httpMethod': 'POST',
            'body': json.dumps({
                'email': 'test@example.com',
                'name': 'Test User'
            })
        }
        context = Mock()

        # Mock service
        mock_user = User(
            id='usr_123',
            email='test@example.com',
            name='Test User'
        )
        with patch('src.handlers.user_handler.UserService') as MockService:
            MockService.return_value.create_user.return_value = mock_user

            # Act
            response = lambda_handler(event, context)

        # Assert
        assert response['statusCode'] == 201
        body = json.loads(response['body'])
        assert body['id'] == 'usr_123'
        assert body['email'] == 'test@example.com'

    def test_create_user_with_valid_data_returns_201_AC_001(self):
        """Test create_user returns 201 with valid data (AC-001)."""
        # Arrange
        event = {
            'body': json.dumps({
                'email': 'john@example.com',
                'name': 'John Doe'
            })
        }
        mock_user = User(
            id='usr_abc',
            email='john@example.com',
            name='John Doe'
        )

        with patch('src.handlers.user_handler.UserService') as MockService:
            MockService.return_value.create_user.return_value = mock_user

            # Act
            response = create_user(event, 'trace_123')

        # Assert
        assert response['statusCode'] == 201
        body = json.loads(response['body'])
        assert body['email'] == 'john@example.com'

    def test_create_user_with_invalid_email_returns_400(self):
        """Test create_user returns 400 with invalid email format."""
        # Arrange
        event = {
            'body': json.dumps({
                'email': 'invalid-email',
                'name': 'Test'
            })
        }

        # Act
        response = create_user(event, 'trace_123')

        # Assert
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['errorCode'] == 'VALIDATION_ERROR'
        assert 'trace_123' in body['correlationId']

    def test_create_user_with_missing_body_returns_400(self):
        """Test create_user returns 400 when body is missing."""
        # Arrange
        event = {}  # No body

        # Act
        response = create_user(event, 'trace_123')

        # Assert
        assert response['statusCode'] == 400

    def test_create_user_with_malformed_json_returns_400(self):
        """Test create_user returns 400 with malformed JSON."""
        # Arrange
        event = {
            'body': 'not-valid-json{'
        }

        # Act
        response = create_user(event, 'trace_123')

        # Assert
        assert response['statusCode'] == 400
```

---

### 2.3 Service Layer Tests

**What to Test**:
- Business logic correctness
- Orchestration of repositories
- Domain model manipulation
- Business rule enforcement
- Exception handling

**What to Mock**:
- Repositories
- External services
- Time/date functions (for deterministic tests)

**Template**:
```python
import pytest
from unittest.mock import Mock
from datetime import datetime
from src.services.user_service import UserService
from src.repositories.user_repository import UserRepository
from src.dto.request import CreateUserDto
from src.domain.user import User
from src.domain.exceptions import DuplicateEmailError, UserNotFoundError

class TestUserService:
    """Tests for UserService business logic."""

    @pytest.fixture
    def mock_repository(self):
        """Create mock user repository."""
        return Mock(spec=UserRepository)

    @pytest.fixture
    def service(self, mock_repository):
        """Create UserService with mock repository."""
        return UserService(mock_repository)

    def test_create_user_with_valid_data_succeeds_AC_001(
        self, service, mock_repository
    ):
        """Test create_user creates user with valid data (AC-001)."""
        # Arrange
        request = CreateUserDto(
            email='john.doe@example.com',
            name='John Doe'
        )
        mock_repository.find_by_email.return_value = None

        # Act
        result = service.create_user(request)

        # Assert
        assert result.email == 'john.doe@example.com'
        assert result.name == 'John Doe'
        assert result.id is not None
        mock_repository.save.assert_called_once()

    def test_create_user_with_duplicate_email_raises_error_AC_002(
        self, service, mock_repository
    ):
        """Test create_user raises error for duplicate email (AC-002)."""
        # Arrange
        request = CreateUserDto(
            email='duplicate@example.com',
            name='Duplicate User'
        )
        existing_user = User(
            id='usr_existing',
            email='duplicate@example.com',
            name='Existing User'
        )
        mock_repository.find_by_email.return_value = existing_user

        # Act & Assert
        with pytest.raises(DuplicateEmailError) as exc_info:
            service.create_user(request)

        assert 'duplicate@example.com' in str(exc_info.value)
        mock_repository.save.assert_not_called()

    def test_create_user_generates_unique_id(self, service, mock_repository):
        """Test create_user generates unique ID for each user."""
        # Arrange
        request1 = CreateUserDto(email='user1@example.com', name='User 1')
        request2 = CreateUserDto(email='user2@example.com', name='User 2')
        mock_repository.find_by_email.return_value = None

        # Act
        user1 = service.create_user(request1)
        user2 = service.create_user(request2)

        # Assert
        assert user1.id != user2.id
        assert user1.id.startswith('usr_')
        assert user2.id.startswith('usr_')

    def test_get_user_by_id_returns_user_AC_005(
        self, service, mock_repository
    ):
        """Test get_user returns user when found (AC-005)."""
        # Arrange
        user_id = 'usr_123'
        expected_user = User(
            id=user_id,
            email='found@example.com',
            name='Found User'
        )
        mock_repository.find_by_id.return_value = expected_user

        # Act
        result = service.get_user(user_id)

        # Assert
        assert result == expected_user
        mock_repository.find_by_id.assert_called_once_with(user_id)

    def test_get_user_by_id_returns_none_when_not_found(
        self, service, mock_repository
    ):
        """Test get_user returns None when user not found."""
        # Arrange
        user_id = 'usr_nonexistent'
        mock_repository.find_by_id.return_value = None

        # Act
        result = service.get_user(user_id)

        # Assert
        assert result is None

    def test_update_user_updates_fields_AC_008(
        self, service, mock_repository
    ):
        """Test update_user updates user fields (AC-008)."""
        # Arrange
        user_id = 'usr_123'
        existing_user = User(
            id=user_id,
            email='old@example.com',
            name='Old Name'
        )
        mock_repository.find_by_id.return_value = existing_user

        # Act
        result = service.update_user(
            user_id,
            name='New Name'
        )

        # Assert
        assert result.name == 'New Name'
        assert result.email == 'old@example.com'  # Unchanged
        mock_repository.save.assert_called_once()

    def test_delete_user_removes_user_AC_010(
        self, service, mock_repository
    ):
        """Test delete_user removes user (AC-010)."""
        # Arrange
        user_id = 'usr_123'
        existing_user = User(id=user_id, email='test@example.com', name='Test')
        mock_repository.find_by_id.return_value = existing_user

        # Act
        service.delete_user(user_id)

        # Assert
        mock_repository.delete.assert_called_once_with(user_id)

    def test_delete_user_raises_error_when_not_found(
        self, service, mock_repository
    ):
        """Test delete_user raises error when user not found."""
        # Arrange
        user_id = 'usr_nonexistent'
        mock_repository.find_by_id.return_value = None

        # Act & Assert
        with pytest.raises(UserNotFoundError):
            service.delete_user(user_id)

        mock_repository.delete.assert_not_called()
```

---

### 2.4 Repository Layer Tests

**What to Test**:
- Data access operations
- Query construction
- DynamoDB operations (with mocking)
- Error handling
- Data transformation (raw dict → domain model)

**What to Mock**:
- boto3 DynamoDB resource/client
- Use `moto` library for AWS service mocking

**Template**:
```python
import pytest
from unittest.mock import Mock, patch
from moto import mock_dynamodb
import boto3
from src.repositories.user_repository import UserRepository
from src.domain.user import User

class TestUserRepository:
    """Tests for UserRepository data access."""

    @pytest.fixture
    def dynamodb_table(self):
        """Create mock DynamoDB table for testing."""
        with mock_dynamodb():
            dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
            table = dynamodb.create_table(
                TableName='Users',
                KeySchema=[
                    {'AttributeName': 'PK', 'KeyType': 'HASH'},
                    {'AttributeName': 'SK', 'KeyType': 'RANGE'}
                ],
                AttributeDefinitions=[
                    {'AttributeName': 'PK', 'AttributeType': 'S'},
                    {'AttributeName': 'SK', 'AttributeType': 'S'},
                    {'AttributeName': 'email', 'AttributeType': 'S'}
                ],
                GlobalSecondaryIndexes=[
                    {
                        'IndexName': 'email-index',
                        'KeySchema': [
                            {'AttributeName': 'email', 'KeyType': 'HASH'}
                        ],
                        'Projection': {'ProjectionType': 'ALL'},
                        'ProvisionedThroughput': {
                            'ReadCapacityUnits': 1,
                            'WriteCapacityUnits': 1
                        }
                    }
                ],
                ProvisionedThroughput={
                    'ReadCapacityUnits': 1,
                    'WriteCapacityUnits': 1
                }
            )
            yield table

    @pytest.fixture
    def repository(self, dynamodb_table):
        """Create UserRepository with mock table."""
        return UserRepository(table=dynamodb_table)

    def test_save_creates_item_in_dynamodb(self, repository, dynamodb_table):
        """Test save creates item in DynamoDB."""
        # Arrange
        user = User(
            id='usr_123',
            email='test@example.com',
            name='Test User'
        )

        # Act
        repository.save(user)

        # Assert
        response = dynamodb_table.get_item(
            Key={'PK': 'USER#usr_123', 'SK': 'METADATA'}
        )
        assert 'Item' in response
        assert response['Item']['email'] == 'test@example.com'
        assert response['Item']['name'] == 'Test User'

    def test_find_by_id_returns_user_when_exists(
        self, repository, dynamodb_table
    ):
        """Test find_by_id returns user when exists."""
        # Arrange
        dynamodb_table.put_item(
            Item={
                'PK': 'USER#usr_123',
                'SK': 'METADATA',
                'id': 'usr_123',
                'email': 'found@example.com',
                'name': 'Found User'
            }
        )

        # Act
        result = repository.find_by_id('usr_123')

        # Assert
        assert result is not None
        assert result.id == 'usr_123'
        assert result.email == 'found@example.com'

    def test_find_by_id_returns_none_when_not_exists(self, repository):
        """Test find_by_id returns None when user doesn't exist."""
        # Arrange & Act
        result = repository.find_by_id('usr_nonexistent')

        # Assert
        assert result is None

    def test_find_by_email_uses_gsi(self, repository, dynamodb_table):
        """Test find_by_email queries GSI."""
        # Arrange
        dynamodb_table.put_item(
            Item={
                'PK': 'USER#usr_123',
                'SK': 'METADATA',
                'id': 'usr_123',
                'email': 'test@example.com',
                'name': 'Test User'
            }
        )

        # Act
        result = repository.find_by_email('test@example.com')

        # Assert
        assert result is not None
        assert result.email == 'test@example.com'

    def test_delete_removes_item(self, repository, dynamodb_table):
        """Test delete removes item from DynamoDB."""
        # Arrange
        dynamodb_table.put_item(
            Item={
                'PK': 'USER#usr_123',
                'SK': 'METADATA',
                'id': 'usr_123',
                'email': 'test@example.com',
                'name': 'Test'
            }
        )

        # Act
        repository.delete('usr_123')

        # Assert
        response = dynamodb_table.get_item(
            Key={'PK': 'USER#usr_123', 'SK': 'METADATA'}
        )
        assert 'Item' not in response
```

---

### 2.5 Domain & DTO Tests

**What to Test**:
- Model validation (Pydantic)
- Business rules in domain models
- Model serialization/deserialization
- Edge cases (empty strings, None values, boundaries)

**Template**:
```python
import pytest
from pydantic import ValidationError
from src.dto.request import CreateUserDto, UpdateUserDto
from src.domain.user import User

class TestCreateUserDto:
    """Tests for CreateUserDto validation."""

    def test_valid_dto_succeeds(self):
        """Test DTO creation with valid data."""
        # Arrange & Act
        dto = CreateUserDto(
            email='test@example.com',
            name='Test User'
        )

        # Assert
        assert dto.email == 'test@example.com'
        assert dto.name == 'Test User'

    def test_invalid_email_format_raises_error(self):
        """Test DTO validation rejects invalid email."""
        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            CreateUserDto(email='invalid-email', name='Test')

        assert 'email' in str(exc_info.value)

    def test_missing_email_raises_error(self):
        """Test DTO validation requires email."""
        # Act & Assert
        with pytest.raises(ValidationError):
            CreateUserDto(name='Test')

    def test_empty_name_raises_error(self):
        """Test DTO validation rejects empty name."""
        # Act & Assert
        with pytest.raises(ValidationError):
            CreateUserDto(email='test@example.com', name='')

    def test_long_name_within_limit_succeeds(self):
        """Test DTO accepts name up to 255 characters."""
        # Arrange
        long_name = 'A' * 255

        # Act
        dto = CreateUserDto(email='test@example.com', name=long_name)

        # Assert
        assert len(dto.name) == 255

    def test_name_exceeding_limit_raises_error(self):
        """Test DTO rejects name over 255 characters."""
        # Arrange
        too_long_name = 'A' * 256

        # Act & Assert
        with pytest.raises(ValidationError):
            CreateUserDto(email='test@example.com', name=too_long_name)

class TestUser:
    """Tests for User domain model."""

    def test_user_creation(self):
        """Test User domain model creation."""
        # Arrange & Act
        user = User(
            id='usr_123',
            email='test@example.com',
            name='Test User'
        )

        # Assert
        assert user.id == 'usr_123'
        assert user.email == 'test@example.com'
        assert user.name == 'Test User'

    def test_user_equality(self):
        """Test User equality based on ID."""
        # Arrange
        user1 = User(id='usr_123', email='test@example.com', name='Test')
        user2 = User(id='usr_123', email='other@example.com', name='Other')

        # Act & Assert
        assert user1 == user2  # Same ID

    def test_user_to_dict(self):
        """Test User serialization to dict."""
        # Arrange
        user = User(
            id='usr_123',
            email='test@example.com',
            name='Test User'
        )

        # Act
        result = user.dict()

        # Assert
        assert result['id'] == 'usr_123'
        assert result['email'] == 'test@example.com'
        assert result['name'] == 'Test User'
```

---

## 3. INTEGRATION TEST GENERATION

### 3.1 Integration Test Structure

**Directory Layout**:
```
backend/lambdas/{function_name}/
  tests/
    integration/
      test_api_integration.py
      test_dynamodb_integration.py
      test_eventbridge_integration.py
```

### 3.2 API Gateway + Lambda Integration Tests

**What to Test**:
- Complete API request/response flow
- Authentication via Cognito
- Request validation
- Response formatting
- Error handling

**Environment**: Use localstack or dev AWS environment

**Template**:
```python
import pytest
import requests
import json
import boto3
from moto import mock_dynamodb

@pytest.mark.integration
class TestUserApiIntegration:
    """Integration tests for User API."""

    @pytest.fixture(scope='class')
    def api_url(self):
        """Get API Gateway URL from environment or config."""
        return 'https://api.dev.example.com'

    @pytest.fixture(scope='class')
    def auth_token(self):
        """Get valid JWT token for testing."""
        # In real scenario, authenticate with Cognito
        return 'valid-jwt-token'

    def test_create_user_end_to_end(self, api_url, auth_token):
        """Test complete user creation flow."""
        # Arrange
        headers = {
            'Authorization': f'Bearer {auth_token}',
            'Content-Type': 'application/json'
        }
        payload = {
            'email': 'integration-test@example.com',
            'name': 'Integration Test User'
        }

        # Act
        response = requests.post(
            f'{api_url}/users',
            headers=headers,
            json=payload
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert 'id' in data
        assert data['email'] == 'integration-test@example.com'
        assert data['name'] == 'Integration Test User'

        # Cleanup
        user_id = data['id']
        requests.delete(
            f'{api_url}/users/{user_id}',
            headers=headers
        )

    def test_get_user_end_to_end(self, api_url, auth_token):
        """Test complete user retrieval flow."""
        # Arrange: Create a user first
        headers = {
            'Authorization': f'Bearer {auth_token}',
            'Content-Type': 'application/json'
        }
        create_response = requests.post(
            f'{api_url}/users',
            headers=headers,
            json={'email': 'get-test@example.com', 'name': 'Get Test'}
        )
        user_id = create_response.json()['id']

        # Act: Retrieve the user
        response = requests.get(
            f'{api_url}/users/{user_id}',
            headers=headers
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data['id'] == user_id
        assert data['email'] == 'get-test@example.com'

        # Cleanup
        requests.delete(f'{api_url}/users/{user_id}', headers=headers)

    def test_create_user_without_auth_returns_401(self, api_url):
        """Test API requires authentication."""
        # Act
        response = requests.post(
            f'{api_url}/users',
            json={'email': 'test@example.com', 'name': 'Test'}
        )

        # Assert
        assert response.status_code == 401
```

---

### 3.3 Lambda + DynamoDB Integration Tests

**Template**:
```python
import pytest
import boto3
from moto import mock_dynamodb
from src.handlers.user_handler import lambda_handler

@pytest.mark.integration
@mock_dynamodb
class TestLambdaDynamoDbIntegration:
    """Integration tests for Lambda and DynamoDB."""

    @pytest.fixture(scope='class')
    def dynamodb_table(self):
        """Create real DynamoDB table for integration testing."""
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.create_table(
            TableName='Users',
            KeySchema=[
                {'AttributeName': 'PK', 'KeyType': 'HASH'},
                {'AttributeName': 'SK', 'KeyType': 'RANGE'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'PK', 'AttributeType': 'S'},
                {'AttributeName': 'SK', 'AttributeType': 'S'}
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 1,
                'WriteCapacityUnits': 1
            }
        )
        yield table

    def test_lambda_persists_data_to_dynamodb(self, dynamodb_table):
        """Test Lambda handler persists data to DynamoDB."""
        # Arrange
        event = {
            'resource': '/users',
            'httpMethod': 'POST',
            'body': json.dumps({
                'email': 'persist@example.com',
                'name': 'Persist Test'
            })
        }
        context = Mock()

        # Act
        response = lambda_handler(event, context)

        # Assert: Response successful
        assert response['statusCode'] == 201
        user_id = json.loads(response['body'])['id']

        # Assert: Data in DynamoDB
        db_response = dynamodb_table.get_item(
            Key={'PK': f'USER#{user_id}', 'SK': 'METADATA'}
        )
        assert 'Item' in db_response
        assert db_response['Item']['email'] == 'persist@example.com'
```

---

## 4. E2E TEST GENERATION

### 4.1 E2E Test Structure

**What to Test**:
- Complete user workflows
- Multi-step processes
- Cross-component interactions
- Event-driven flows

**Template**:
```python
import pytest
import time
import requests
import boto3

@pytest.mark.e2e
class TestUserRegistrationWorkflow:
    """E2E tests for complete user registration workflow."""

    def test_complete_user_registration_flow(self):
        """
        Test complete user registration workflow:
        1. POST /users (create user)
        2. User.Created event published to EventBridge
        3. Email Lambda triggered
        4. Welcome email sent via SES
        5. User can login
        """
        # Step 1: Create user
        response = requests.post(
            'https://api.dev.example.com/users',
            json={'email': 'e2e-test@example.com', 'name': 'E2E Test'},
            headers={'Authorization': 'Bearer admin-token'}
        )
        assert response.status_code == 201
        user_id = response.json()['id']

        # Step 2: Wait for async processing
        time.sleep(3)

        # Step 3: Verify email was sent (check SES or email service)
        # This would check your email service logs or mock SES

        # Step 4: Verify user can be retrieved
        get_response = requests.get(
            f'https://api.dev.example.com/users/{user_id}',
            headers={'Authorization': 'Bearer admin-token'}
        )
        assert get_response.status_code == 200

        # Cleanup
        requests.delete(
            f'https://api.dev.example.com/users/{user_id}',
            headers={'Authorization': 'Bearer admin-token'}
        )
```

---

## 5. TEST FIXTURES & MOCKS

### 5.1 Shared Fixtures (conftest.py)

**Purpose**: Reusable test data and setup

**Template**:
```python
# tests/conftest.py
import pytest
from unittest.mock import Mock
from src.repositories.user_repository import UserRepository
from src.dto.request import CreateUserDto
from src.domain.user import User

@pytest.fixture
def valid_create_user_dto():
    """Fixture for valid CreateUserDto."""
    return CreateUserDto(
        email='test@example.com',
        name='Test User'
    )

@pytest.fixture
def sample_user():
    """Fixture for sample User domain model."""
    return User(
        id='usr_123',
        email='test@example.com',
        name='Test User'
    )

@pytest.fixture
def mock_user_repository():
    """Fixture for mocked UserRepository."""
    return Mock(spec=UserRepository)

@pytest.fixture
def api_gateway_event():
    """Fixture for API Gateway event structure."""
    return {
        'resource': '/users',
        'httpMethod': 'POST',
        'headers': {
            'Content-Type': 'application/json'
        },
        'body': None,  # Override in tests
        'requestContext': {
            'authorizer': {
                'claims': {
                    'sub': 'user_123',
                    'email': 'authorized@example.com'
                }
            }
        }
    }

@pytest.fixture
def lambda_context():
    """Fixture for Lambda context."""
    context = Mock()
    context.function_name = 'test-function'
    context.memory_limit_in_mb = 512
    context.invoked_function_arn = 'arn:aws:lambda:us-east-1:123456789012:function:test'
    return context
```

---

## 6. TEST BEST PRACTICES

### 6.1 Arrange-Act-Assert Pattern

**Always structure tests in three sections**:
```python
def test_example():
    # Arrange: Set up test data and mocks
    user = User(id='usr_123', email='test@example.com', name='Test')
    mock_repo = Mock()

    # Act: Execute the function under test
    result = service.process_user(user)

    # Assert: Verify expectations
    assert result.status == 'processed'
    mock_repo.save.assert_called_once()
```

### 6.2 Test Independence

**Each test must run independently**:
- No shared state between tests
- Tests can run in any order
- Each test sets up its own data
- Each test cleans up after itself

### 6.3 Descriptive Test Names

**Test names should describe scenario and expectation**:
- ✅ `test_create_user_with_duplicate_email_raises_error()`
- ✅ `test_get_user_by_id_returns_user_when_exists_AC_005()`
- ❌ `test_user()`
- ❌ `test_1()`

### 6.4 One Behavior Per Test

**Focus each test on a single behavior**:
```python
# Good: Separate tests for different behaviors
def test_create_user_saves_to_database():
    service.create_user(request)
    mock_repo.save.assert_called_once()

def test_create_user_returns_user_with_id():
    result = service.create_user(request)
    assert result.id is not None

# Bad: Testing multiple behaviors
def test_create_user():
    result = service.create_user(request)
    assert result.id is not None
    mock_repo.save.assert_called_once()
    assert service.count() == 1
```

---

## 7. TEST COVERAGE REQUIREMENTS

### Coverage Targets
- **Overall**: ≥ 80%
- **Handler layer**: ≥ 90%
- **Service layer**: ≥ 95%
- **Repository layer**: ≥ 85%
- **Domain/DTOs**: ≥ 100%

### Generate Coverage Report
```bash
pytest --cov=src --cov-report=term-missing --cov-report=html
```

### Coverage Configuration (pytest.ini)
```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts =
    --cov=src
    --cov-report=term-missing
    --cov-report=html
    --cov-fail-under=80
    -v
markers =
    unit: Unit tests
    integration: Integration tests
    e2e: End-to-end tests
```

---

## 8. ACCEPTANCE CRITERIA TRACEABILITY

### Traceability is Mandatory (Shift-Left)

Every test MUST trace back to a requirement, acceptance criterion, or business rule. Tests that exist without traceability to a requirement indicate either:
- A missing requirement (update requirements)
- An unnecessary test (remove it)

**Every acceptance criterion MUST have at least one test**:
```
REQ-001: User can create account with email and name
  AC-001: User created successfully with valid data
    → test_create_user_with_valid_data_succeeds_AC_001()
  AC-002: System rejects duplicate email addresses
    → test_create_user_with_duplicate_email_raises_error_AC_002()
  AC-003: System validates email format
    → test_create_user_with_invalid_email_returns_400_AC_003()
```

### Traceability Matrix

The traceability matrix MUST be generated as part of the test plan (Section 1.2) and validated during test review:

| Source | ID | Description | Test Type | Test Name | Status |
|--------|----|-------------|-----------|-----------|--------|
| AC | AC-001 | Create with valid data | Unit | test_create_user_...AC_001 | ✅ |
| AC | AC-002 | Reject duplicate email | Unit | test_create_user_...AC_002 | ✅ |
| AC | AC-003 | Validate email format | Unit | test_create_user_...AC_003 | ✅ |
| BR | BR-001 | Auth required | Integration | test_unauth_returns_401 | ✅ |
| TR | TR-001 | Latency < 200ms | Performance | test_api_latency_p95 | ⬜ |

**Gap Analysis**: Any AC, BR, or TR without a corresponding test is a coverage gap that MUST be addressed before test review approval.

---

## 9. INTEGRATION WITH WORKFLOW

### Phase 2 (Requirements Analysis) → Test Plan
- Extract acceptance criteria, business rules, and workflows
- Generate test plan with traceability matrix (Section 1.2)
- Identify test types needed per requirement (unit, integration, E2E)
- **Output**: `docs/specs/{service-name}/test-plan.md`

### Phase 3 (System Design) → Test Fixtures
- Design test fixtures from data models
- Design mocks from external interface definitions
- Identify integration test boundaries from service decomposition

### Phase 4 (Implementation) → Test Code
- Generate test code from test plan (tests can be written before implementation)
- Unit tests for each layer (derived from ACs, not from code)
- Integration tests for service boundaries
- Test coverage tracked continuously

### Phase 5 (Testing) → Execution & Validation
- Run all tests against implementation
- Generate coverage report
- Validate traceability: every AC has a passing test
- Run test review
- Fix failing tests
- Address coverage gaps

---

## 10. TEST EXECUTION

### Run All Tests
```bash
pytest tests/
```

### Run Unit Tests Only
```bash
pytest tests/unit/
```

### Run Integration Tests Only
```bash
pytest tests/integration/ -m integration
```

### Run E2E Tests
```bash
pytest tests/ -m e2e
```

### Run with Coverage
```bash
pytest --cov=src --cov-report=term-missing --cov-report=html
```

---

## 11. OUTPUT ARTIFACTS

Test generation MUST produce the following artifacts in `docs/specs/{service-name}/`:

### 1. test-plan.md (Generated FIRST)
- Traceability matrix: AC/BR/TR → test cases
- Test types per requirement (unit, integration, E2E)
- Coverage gap analysis

### 2. Test Code
- Unit tests: `tests/unit/`
- Integration tests: `tests/integration/`
- E2E tests: `tests/e2e/` (when applicable)
- Shared fixtures: `tests/conftest.py`

---

## 12. QUALITY EXPECTATIONS

Generated tests must:
- [ ] Be derived from acceptance criteria and business rules (not reverse-engineered from code)
- [ ] Have a test plan with traceability matrix generated before test code
- [ ] Follow Arrange-Act-Assert pattern
- [ ] Be independent (no shared state)
- [ ] Have descriptive names with AC/BR IDs where applicable
- [ ] Cover happy path and error paths
- [ ] Include edge cases derived from requirements
- [ ] Properly mock external dependencies
- [ ] Be syntactically correct
- [ ] Run successfully
- [ ] Provide ≥80% code coverage
- [ ] Have zero untested acceptance criteria

---

**Tests are a first-class artifact derived from requirements — not an afterthought of implementation. This skill ensures all code is validated against the requirements it was built to satisfy.**
