# Code Review Skill - Enterprise Specification

## Directive

This skill performs comprehensive enterprise-grade code reviews that MUST enforce architectural standards, security requirements, observability practices, and infrastructure best practices.

**Primary Goal**: Ensure code is production-ready by detecting architectural violations, security risks, performance issues, and maintainability problems before human review.

**Review Scope**:
- Architecture compliance
- Security vulnerabilities
- Observability implementation
- Infrastructure configuration
- Code simplicity and maintainability
- Test coverage and quality
- API design consistency
- Performance optimization

---

## 1. ARCHITECTURE COMPLIANCE REVIEW

### 1.1 Backend Structure Validation

**REQUIRED Structure**:
```
src/
  handlers/       # HTTP/event handlers ONLY
  services/       # Business logic ONLY
  repositories/   # Data access ONLY
  domain/         # Business entities
  dto/            # Request/response schemas
  middleware/     # Cross-cutting concerns
  utils/          # Pure utility functions
  config/         # Configuration management
```

### 1.2 Layer Responsibility Violations

#### CRITICAL: Business Logic in Handlers

**Violation Example**:
```python
# WRONG: Business logic in handler
@app.post("/users")
def create_user():
    data = app.current_event.json_body

    # ❌ VIOLATION: Email validation is business logic
    if not data.get('email') or '@' not in data['email']:
        return {"error": "Invalid email"}, 400

    # ❌ VIOLATION: Direct database access in handler
    table.put_item(Item=data)

    return {"message": "User created"}, 201
```

**Review Finding**:
```
Issue Type: Architecture Violation
Severity: Critical
File: src/handlers/user_handler.py:15-25
Description: Handler contains business logic (email validation) and direct database access. Handlers must ONLY parse requests, call services, and return responses.
Recommendation: Move email validation to service layer. Move database access to repository layer. Handler should only call UserService.create_user().
```

**Correct Pattern**:
```python
# CORRECT: Handler delegates to service
@app.post("/users")
def create_user():
    request_data = CreateUserRequest(**app.current_event.json_body)
    service = UserService()
    user = service.create_user(request_data)
    return UserResponse.from_domain(user).dict(), 201
```

#### CRITICAL: Services Performing HTTP Handling

**Violation Example**:
```python
# WRONG: Service handling HTTP response
class UserService:
    def create_user(self, email: str, name: str):
        # Business logic...

        # ❌ VIOLATION: Service returning HTTP response
        return {
            "statusCode": 201,
            "body": json.dumps({"user": user_data})
        }
```

**Review Finding**:
```
Issue Type: Architecture Violation
Severity: Critical
File: src/services/user_service.py:45-50
Description: Service returns HTTP response structure. Services must return domain objects only.
Recommendation: Return User domain object. Let handler convert to HTTP response format.
```

#### CRITICAL: Repositories Calling Services

**Violation Example**:
```python
# WRONG: Repository calling service
class UserRepository:
    def save(self, user):
        # ❌ VIOLATION: Repository calling service
        notification_service = NotificationService()
        notification_service.send_welcome_email(user.email)

        return self.table.put_item(Item=user.to_dict())
```

**Review Finding**:
```
Issue Type: Architecture Violation
Severity: Critical
File: src/repositories/user_repository.py:30-35
Description: Repository calling service layer. Repositories must ONLY perform data access operations.
Recommendation: Remove service call. If notification needed, orchestrate in service layer: create user -> save to repo -> send notification.
```

#### HIGH: Circular Dependencies

**Violation Detection**:
```python
# File: src/services/user_service.py
from src.services.order_service import OrderService

# File: src/services/order_service.py
from src.services.user_service import UserService  # ❌ CIRCULAR
```

**Review Finding**:
```
Issue Type: Architecture Violation
Severity: High
Files: src/services/user_service.py, src/services/order_service.py
Description: Circular dependency detected between UserService and OrderService.
Recommendation: Extract shared logic to separate service or use dependency injection to break cycle.
```

### 1.3 Architectural Review Checklist

- [ ] Handlers contain ONLY request/response logic
- [ ] Services contain ONLY business logic
- [ ] Repositories contain ONLY data access
- [ ] No circular dependencies
- [ ] Domain objects have no external dependencies
- [ ] DTOs used for request/response validation
- [ ] Proper dependency injection used
- [ ] No layer skipping (handler -> repository directly)

---

## 2. ASPECT ENFORCEMENT REVIEW

### 2.1 Required Cross-Cutting Concerns

ALL handlers MUST implement these aspects via middleware/decorators:
- Logging
- Authentication
- Authorization
- Error handling
- Correlation ID propagation
- Metrics
- Distributed tracing

### 2.2 Missing Observability

**Violation Example**:
```python
# WRONG: No observability
def lambda_handler(event, context):
    # ❌ Missing logging, tracing, metrics
    user_service = UserService()
    result = user_service.create_user(event['body'])
    return {"statusCode": 200, "body": result}
```

**Review Finding**:
```
Issue Type: Missing Observability
Severity: Critical
File: src/handlers/user_handler.py:10-15
Description: Handler missing OpenTelemetry trace extraction and structured JSON logging.
Recommendation: Initialize OTel tracer/meter and extract trace_id for logger context.
```

**Correct Pattern**:
```python
import logging
import json
from opentelemetry import trace, metrics

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

def lambda_handler(event, context):
    span = trace.get_current_span()
    trace_id = format(span.get_span_context().trace_id, '032x')
    logger.info(json.dumps({"message": "Processing", "trace_id": trace_id}))
    # Implementation
```

### 2.3 Duplicated Cross-Cutting Logic

**Violation Example**:
```python
# WRONG: Logging duplicated in every method
class UserService:
    def create_user(self, request):
        # ❌ VIOLATION: Manual logging in business logic
        print(f"Creating user: {request.email}")
        user = self.repository.save(request)
        print(f"User created: {user.id}")
        return user

    def update_user(self, user_id, request):
        # ❌ VIOLATION: Same logging pattern duplicated
        print(f"Updating user: {user_id}")
        user = self.repository.update(user_id, request)
        print(f"User updated: {user.id}")
        return user
```

**Review Finding**:
```
Issue Type: Aspect Duplication
Severity: Medium
File: src/services/user_service.py:20-35
Description: Logging logic duplicated across methods. Cross-cutting concerns should be implemented via decorators.
Recommendation: Remove manual logging. Use @logger.inject_lambda_context at handler level. Use logger.info() for business events only.
```

### 2.4 Missing Authentication

**Violation Example**:
```python
# WRONG: No authentication check
@app.post("/users")
def create_user():
    # ❌ No authentication decorator
    service = UserService()
    return service.create_user(request_data)
```

**Review Finding**:
```
Issue Type: Missing Security Aspect
Severity: Critical
File: src/handlers/user_handler.py:25
Description: Endpoint missing authentication decorator.
Recommendation: Add @require_auth decorator or implement authentication middleware.
```

### 2.5 Manual API Gateway Handling (Missing Middleware)

**Violation Example**:
```python
# WRONG: Handler contains manual boilerplate
def lambda_handler(event, context):
    try:
        trace_id = event.get('headers', {}).get('X-Amzn-Trace-Id')
        logger.info("Request received")
        # Logic...
        return {"statusCode": 200, "body": "{}"}
    except Exception as e:
        logger.error("Error", exc_info=True)
        return {"statusCode": 500, "body": "{}"}
```

**Review Finding**:
```
Issue Type: Aspect Duplication (Handler Boilerplate)
Severity: High
File: src/handlers/user_handler.py:15-30
Description: Handler manually extracts trace IDs, manages entry/exit logging, and maps exceptions to HTTP status codes.
Recommendation: Remove manual try/except blocks and generic logging. Wrap the handler with an `@api_gateway_handler` decorator that centrally manages all HTTP-level cross-cutting concerns.
```

### 2.6 Aspect Enforcement Checklist

- [ ] All handlers emit OpenTelemetry traces/metrics and JSON logs
- [ ] Authentication enforced via middleware/decorator
- [ ] Authorization enforced via middleware/decorator
- [ ] Correlation ID propagated through all layers
- [ ] No duplicated cross-cutting logic in services
- [ ] Error handling centralized
- [ ] Metrics captured at handler level
- [ ] Distributed tracing enabled

---

## 3. OBSERVABILITY REVIEW

### 3.1 Structured Logging Validation

**Violation Example**:
```python
# WRONG: Unstructured logging
print(f"User {user_id} created successfully")
logger.info(f"Creating user with email {email}")
```

**Review Finding**:
```
Issue Type: Observability Violation
Severity: High
File: src/services/user_service.py:42
Description: Unstructured logging with string formatting. Logs must be structured JSON for proper querying.
Recommendation: Use logger.info("User created", extra={"user_id": user_id, "email": email})
```

**Correct Pattern**:
```python
# CORRECT: Structured logging
logger.info("User created", extra={
    "user_id": user.id,
    "email": user.email,
    "action": "user_creation"
})
```

### 3.2 Missing Correlation ID

**Violation Example**:
```python
# WRONG: Manual correlation ID handling
def lambda_handler(event, context):
    correlation_id = str(uuid4())
    # ❌ Manual tracking, not propagated properly
```

**Review Finding**:
```
Issue Type: Observability Violation
Severity: High
File: src/handlers/user_handler.py:15
Description: Manual correlation ID generation. Must use OpenTelemetry trace ID for correlation.
Recommendation: Use trace_id = format(trace.get_current_span().get_span_context().trace_id, '032x').
```

### 3.3 Missing Metrics

**Violation Example**:
```python
# WRONG: No metrics collection
def create_user(request):
    # ❌ No metrics for operation
    user = self.repository.save(request)
    return user
```

**Review Finding**:
```
Issue Type: Missing Metrics
Severity: Medium
File: src/services/user_service.py:30-35
Description: Critical operation missing metrics collection.
Recommendation: Add meter.create_counter("UserCreated").add(1) or use appropriate OTel metrics.
```

### 3.4 Missing Tracing

**Violation Example**:
```python
# WRONG: No tracing spans
def lambda_handler(event, context):
    # ❌ No @tracer decorator
    return process_request(event)
```

**Review Finding**:
```
Issue Type: Missing Tracing
Severity: Medium
File: src/handlers/user_handler.py:20
Description: Handler missing distributed tracing decorator.
Recommendation: Add with tracer.start_as_current_span("method_name") on service methods.
```

### 3.5 Observability Checklist

- [ ] Structured JSON logging used
- [ ] Correlation ID automatically propagated
- [ ] Metrics collected for: invocations, errors, latency
- [ ] Distributed tracing enabled (X-Ray)
- [ ] Log levels appropriate (INFO for events, ERROR for failures)
- [ ] No PII in logs
- [ ] Business metrics tracked
- [ ] CloudWatch log groups configured with retention

---

## 4. SECURITY REVIEW

### 4.1 Hardcoded Secrets Detection

**Violation Example**:
```python
# WRONG: Hardcoded credentials
ANTHROPIC_API_KEY = "sk-ant-api03-xxxxx"  # ❌ CRITICAL
DATABASE_PASSWORD = "mypassword123"        # ❌ CRITICAL
AWS_SECRET_KEY = "abc123def456"            # ❌ CRITICAL
```

**Review Finding**:
```
Issue Type: Security Violation
Severity: Critical
File: src/config/settings.py:10-12
Description: Hardcoded secrets detected. Secrets must NEVER be in code.
Recommendation: Use AWS Secrets Manager or SSM Parameter Store. Access via boto3 at runtime.
```

**Correct Pattern**:
```python
from src.config.secrets import get_secret

api_key = get_secret("virtualassist/anthropic-api-key")
```

### 4.2 Missing Input Validation

**Violation Example**:
```python
# WRONG: No input validation
@app.post("/users")
def create_user():
    data = app.current_event.json_body  # ❌ No validation
    service.create_user(data['email'], data['name'])
```

**Review Finding**:
```
Issue Type: Security Violation
Severity: Critical
File: src/handlers/user_handler.py:25-28
Description: Request data used without validation. Vulnerable to injection attacks.
Recommendation: Use Pydantic model (CreateUserRequest) to validate all inputs before processing.
```

### 4.3 Insecure IAM Policies

**Violation Example**:
```python
# WRONG: Overly permissive IAM
user_function.add_to_role_policy(
    iam.PolicyStatement(
        effect=iam.Effect.ALLOW,
        actions=['dynamodb:*'],        # ❌ Too broad
        resources=['*']                 # ❌ All resources
    )
)
```

**Review Finding**:
```
Issue Type: Security Violation - IAM
Severity: Critical
File: infra/stacks/user_stack.py:45-50
Description: IAM policy grants excessive permissions (dynamodb:* on all resources). Violates least privilege principle.
Recommendation: Restrict to specific actions (GetItem, PutItem, Query) and specific table ARN.
```

**Correct Pattern**:
```python
user_function.add_to_role_policy(
    iam.PolicyStatement(
        effect=iam.Effect.ALLOW,
        actions=['dynamodb:GetItem', 'dynamodb:PutItem', 'dynamodb:Query'],
        resources=[f'arn:aws:dynamodb:{region}:{account}:table/users']
    )
)
```

### 4.4 Missing Authentication Check

**Violation Example**:
```python
# WRONG: No authentication
@app.delete("/users/{user_id}")
def delete_user(user_id: str):
    # ❌ No authentication check
    service.delete_user(user_id)
```

**Review Finding**:
```
Issue Type: Security Violation
Severity: Critical
File: src/handlers/user_handler.py:60-63
Description: DELETE endpoint missing authentication. Any user can delete any account.
Recommendation: Add @require_auth decorator and verify user owns the resource.
```

### 4.5 SQL Injection Risk

**Violation Example**:
```python
# WRONG: String concatenation for queries (if using SQL)
query = f"SELECT * FROM users WHERE email = '{email}'"  # ❌ SQL INJECTION
cursor.execute(query)
```

**Review Finding**:
```
Issue Type: Security Violation - SQL Injection
Severity: Critical
File: src/repositories/user_repository.py:55
Description: SQL query uses string formatting. Vulnerable to SQL injection.
Recommendation: Use parameterized queries: cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
```

### 4.6 Missing HTTPS Enforcement

**Violation Example (CDK)**:
```python
# WRONG: HTTP allowed
api = apigw.RestApi(
    self, 'Api',
    # ❌ No HTTPS enforcement
)
```

**Review Finding**:
```
Issue Type: Security Violation - Transport
Severity: High
File: infra/stacks/api_stack.py:30
Description: API Gateway not configured to enforce HTTPS.
Recommendation: Set endpoint_configuration with only HTTPS protocol or use CloudFront distribution.
```

### 4.7 Security Review Checklist

- [ ] No hardcoded secrets
- [ ] Secrets retrieved from Secrets Manager/SSM
- [ ] All inputs validated via schema models
- [ ] Authentication enforced on protected endpoints
- [ ] Authorization checks present
- [ ] IAM policies follow least privilege
- [ ] SQL injection prevention (parameterized queries)
- [ ] XSS prevention (output encoding)
- [ ] HTTPS enforced
- [ ] CORS properly configured
- [ ] Rate limiting implemented
- [ ] No PII in logs

---

## 5. INFRASTRUCTURE REVIEW (AWS CDK)

### 5.1 Missing Encryption

**Violation Example**:
```python
# WRONG: No encryption
bucket = s3.Bucket(
    self, 'DataBucket',
    # ❌ No encryption specified
)
```

**Review Finding**:
```
Issue Type: Infrastructure Violation - Security
Severity: Critical
File: infra/stacks/storage_stack.py:25-28
Description: S3 bucket created without encryption.
Recommendation: Add encryption=s3.BucketEncryption.S3_MANAGED or KMS_MANAGED.
```

### 5.2 Missing Log Groups

**Violation Example**:
```python
# WRONG: No log retention configured
api_function = lambda_.Function(
    self, 'ApiFunction',
    # ❌ No log_retention specified
)
```

**Review Finding**:
```
Issue Type: Infrastructure Violation - Observability
Severity: High
File: infra/stacks/api_stack.py:40-45
Description: Lambda function missing log retention configuration. Logs will be retained indefinitely, increasing costs.
Recommendation: Add log_retention=logs.RetentionDays.ONE_WEEK or appropriate retention period.
```

### 5.3 Missing Resource Tags

**Violation Example**:
```python
# WRONG: No tags
user_function = lambda_.Function(
    self, 'UserFunction',
    # ❌ No tags for cost tracking and management
)
```

**Review Finding**:
```
Issue Type: Infrastructure Violation - Governance
Severity: Medium
File: infra/stacks/user_stack.py:50-55
Description: Lambda function missing resource tags. Required for cost allocation and resource management.
Recommendation: Add Tags.of(user_function).add('Environment', env), Tags.of(user_function).add('Service', 'user-api')
```

### 5.4 Missing Environment Configuration

**Violation Example**:
```python
# WRONG: Hardcoded values
user_function = lambda_.Function(
    self, 'UserFunction',
    environment={
        'TABLE_NAME': 'users-prod'  # ❌ Hardcoded environment
    }
)
```

**Review Finding**:
```
Issue Type: Infrastructure Violation - Configuration
Severity: High
File: infra/stacks/user_stack.py:60
Description: Environment-specific value hardcoded. Stack not reusable across environments.
Recommendation: Use parameter: environment={'TABLE_NAME': f'users-{environment}'}
```

### 5.5 Missing Tracing

**Violation Example**:
```python
# WRONG: No tracing
api_function = lambda_.Function(
    self, 'ApiFunction',
    # ❌ No tracing=lambda_.Tracing.ACTIVE
)
```

**Review Finding**:
```
Issue Type: Infrastructure Violation - Observability
Severity: Medium
File: infra/stacks/api_stack.py:70-75
Description: Lambda function missing X-Ray tracing configuration.
Recommendation: Add tracing=lambda_.Tracing.ACTIVE for distributed tracing support.
```

### 5.6 Overly Permissive Security Groups

**Violation Example**:
```python
# WRONG: Open to all
security_group.add_ingress_rule(
    peer=ec2.Peer.any_ipv4(),          # ❌ 0.0.0.0/0
    connection=ec2.Port.all_traffic()  # ❌ All ports
)
```

**Review Finding**:
```
Issue Type: Infrastructure Violation - Security
Severity: Critical
File: infra/stacks/network_stack.py:40-43
Description: Security group allows all traffic from anywhere. Major security risk.
Recommendation: Restrict to specific CIDR blocks and specific ports only.
```

### 5.7 Infrastructure Review Checklist

- [ ] Encryption enabled (S3, RDS, EBS, etc.)
- [ ] Log groups configured with retention
- [ ] Resource tagging applied (Environment, Service, ManagedBy)
- [ ] IAM policies follow least privilege
- [ ] Lambda tracing enabled (X-Ray)
- [ ] Environment-specific configuration supported
- [ ] CloudWatch alarms configured
- [ ] Security groups restrictive
- [ ] Backup policies configured
- [ ] Removal policies appropriate for environment
- [ ] Cost optimization settings applied

---

## 6. DEPENDENCY REVIEW

### 6.1 Unused Dependencies

**Violation Example**:
```python
# requirements.txt
boto3==1.34.0
anthropic==0.40.0
langchain==0.3.0
pandas==2.1.0        # ❌ Imported but never used
numpy==1.26.0        # ❌ Not needed
```

**Review Finding**:
```
Issue Type: Dependency Violation
Severity: Low
File: backend/lambdas/user/requirements.txt:4-5
Description: Unused dependencies detected (pandas, numpy). Increases package size and deployment time.
Recommendation: Remove unused dependencies to reduce Lambda package size.
```

### 6.2 Vulnerable Dependencies

**Violation Example**:
```python
# requirements.txt
requests==2.25.0  # ❌ Known CVE vulnerabilities
```

**Review Finding**:
```
Issue Type: Security Violation - Dependencies
Severity: High
File: backend/requirements.txt:8
Description: requests 2.25.0 has known security vulnerabilities.
Recommendation: Upgrade to requests>=2.31.0. Run 'pip audit' to check for vulnerabilities.
```

### 6.3 Unpinned Dependencies

**Violation Example**:
```python
# requirements.txt
boto3                # ❌ No version specified
opentelemetry-api    # ❌ No version
```

**Review Finding**:
```
Issue Type: Dependency Violation
Severity: Medium
File: backend/requirements.txt:10-11
Description: Dependencies without version pinning. Can cause unexpected behavior across deployments.
Recommendation: Pin versions: boto3==1.34.0, opentelemetry-api==1.22.0
```

### 6.4 Dependency Review Checklist

- [ ] All dependencies used in code
- [ ] No known vulnerabilities (run `pip audit`)
- [ ] Versions pinned
- [ ] No deprecated packages
- [ ] License compliance verified
- [ ] Minimal dependency count

---

## 7. API DESIGN REVIEW

### 7.1 Missing API Versioning

**Violation Example**:
```python
# WRONG: No versioning
@app.post("/users")  # ❌ No version in path
def create_user():
    pass
```

**Review Finding**:
```
Issue Type: API Design Violation
Severity: High
File: src/handlers/user_handler.py:25
Description: API endpoint missing version prefix. Breaking changes will affect all clients.
Recommendation: Use versioned path: @app.post("/api/v1/users")
```

### 7.2 Inconsistent HTTP Status Codes

**Violation Example**:
```python
# WRONG: Inconsistent status codes
def create_user():
    return user_data, 200  # ❌ Should be 201 for creation

def get_user(user_id):
    if not user:
        return {"error": "Not found"}, 400  # ❌ Should be 404
```

**Review Finding**:
```
Issue Type: API Design Violation
Severity: Medium
File: src/handlers/user_handler.py:30,45
Description: Incorrect HTTP status codes. POST returns 200 instead of 201. Not found returns 400 instead of 404.
Recommendation: Use 201 for creation, 404 for not found, 400 for validation errors.
```

### 7.3 Inconsistent Error Response Format

**Violation Example**:
```python
# WRONG: Different error formats
# Handler 1
return {"error": "Not found"}, 404

# Handler 2
return {"message": "Invalid input", "code": "VAL_001"}, 400

# Handler 3
return {"errorMessage": "Server error"}, 500
```

**Review Finding**:
```
Issue Type: API Design Violation
Severity: High
File: Multiple handlers
Description: Inconsistent error response structure across endpoints. Clients cannot parse errors reliably.
Recommendation: Standardize error format: {"errorCode": "ERROR_TYPE", "message": "Description", "correlationId": "uuid"}
```

### 7.4 Missing Pagination

**Violation Example**:
```python
# WRONG: No pagination
@app.get("/users")
def list_users():
    # ❌ Returns all users, could be thousands
    return service.get_all_users()
```

**Review Finding**:
```
Issue Type: API Design Violation
Severity: High
File: src/handlers/user_handler.py:70
Description: List endpoint returns all records without pagination. Performance and scalability risk.
Recommendation: Add pagination parameters (limit, offset or cursor) and return paginated response with metadata.
```

### 7.5 API Design Checklist

- [ ] API versioned (e.g., /api/v1/)
- [ ] Consistent HTTP status codes (200, 201, 400, 401, 404, 500)
- [ ] Standardized error response format
- [ ] Pagination on list endpoints
- [ ] Consistent naming conventions (camelCase or snake_case)
- [ ] Request/response schemas documented
- [ ] RESTful design principles followed
- [ ] CORS properly configured

---

## 8. CODE SIMPLICITY REVIEW

### 8.1 Unnecessary Abstraction

**Violation Example**:
```python
# WRONG: Over-engineered
class AbstractUserFactory:
    def create_user_strategy(self):
        pass

class ConcreteUserFactoryImpl(AbstractUserFactory):
    def create_user_strategy(self):
        return DefaultUserCreationStrategy()

class DefaultUserCreationStrategy(UserCreationStrategy):
    def execute(self, params):
        # Simple user creation that doesn't need all this
        return User(email=params.email, name=params.name)
```

**Review Finding**:
```
Issue Type: Code Complexity
Severity: Medium
File: src/services/user_factory.py:10-30
Description: Unnecessary abstraction layers for simple user creation. Violates simplicity rule.
Recommendation: Remove abstract factory. Use simple UserService.create_user() method directly.
```

### 8.2 Premature Optimization

**Violation Example**:
```python
# WRONG: Premature optimization
class UserCache:
    def __init__(self):
        self.cache = {}
        self.lru_queue = deque()
        self.access_count = defaultdict(int)

    # ❌ Complex caching for feature that may not need it
    def get(self, key):
        # 50 lines of complex cache management...
```

**Review Finding**:
```
Issue Type: Code Complexity
Severity: Medium
File: src/utils/cache.py:15-65
Description: Complex caching implementation added without demonstrated need. Premature optimization.
Recommendation: Start with simple dict cache or use AWS ElastiCache. Add complexity only if performance testing shows need.
```

### 8.3 Unused Code

**Violation Example**:
```python
# WRONG: Dead code
class UserService:
    def create_user(self, request):
        return self.repository.save(request)

    def legacy_create_user(self, data):  # ❌ Never called
        # Old implementation...
        pass

    def experimental_feature(self):  # ❌ Never used
        pass
```

**Review Finding**:
```
Issue Type: Code Cleanliness
Severity: Low
File: src/services/user_service.py:45-60
Description: Unused methods detected (legacy_create_user, experimental_feature). Increases maintenance burden.
Recommendation: Remove unused code. If needed for reference, check git history.
```

### 8.4 Overly Complex Logic

**Violation Example**:
```python
# WRONG: Complex nested logic
def process_user(user, request, config, flags):
    if user:
        if request:
            if config.get('feature_enabled'):
                if flags['new_flow']:
                    if user.is_active:
                        # 6 levels deep...
```

**Review Finding**:
```
Issue Type: Code Complexity
Severity: Medium
File: src/services/user_service.py:85-100
Description: Deeply nested conditionals (6 levels). Difficult to understand and test.
Recommendation: Extract guard clauses, use early returns, or split into smaller functions.
```

### 8.5 Code Simplicity Checklist

- [ ] No unnecessary abstraction layers
- [ ] No premature optimization
- [ ] No unused/dead code
- [ ] Functions under 30 lines
- [ ] Cyclomatic complexity under 10
- [ ] No deep nesting (max 3 levels)
- [ ] Clear, descriptive variable names
- [ ] Code understandable by mid-level engineer in 5 minutes

---

## 9. TEST QUALITY REVIEW

### 9.1 Missing Edge Cases

**Violation Example**:
```python
# WRONG: Only happy path tested
def test_create_user():
    user = service.create_user(CreateUserRequest(
        email="test@example.com",
        name="Test User"
    ))
    assert user.email == "test@example.com"
    # ❌ No edge cases: duplicate email, invalid format, empty name, etc.
```

**Review Finding**:
```
Issue Type: Test Quality
Severity: High
File: tests/unit/test_user_service.py:15-22
Description: Test only covers happy path. Missing edge cases: duplicate email, invalid email, empty name, None values.
Recommendation: Add test cases for all failure scenarios and boundary conditions.
```

### 9.2 Brittle Tests

**Violation Example**:
```python
# WRONG: Test depends on external state
def test_get_user():
    # ❌ Assumes user exists in database
    user = service.get_user("real-user-id-from-db")
    assert user.email == "existing@example.com"
```

**Review Finding**:
```
Issue Type: Test Quality
Severity: High
File: tests/integration/test_user_service.py:30-33
Description: Test depends on external database state. Will fail if data changes.
Recommendation: Use fixtures or mocks to create test data. Tests must be idempotent and independent.
```

### 9.3 Improper Mocking

**Violation Example**:
```python
# WRONG: Mocking internal implementation details
def test_create_user():
    mock_repo = Mock()
    mock_repo.table.put_item.return_value = {}  # ❌ Mocking internal details
    service = UserService(repository=mock_repo)
```

**Review Finding**:
```
Issue Type: Test Quality
Severity: Medium
File: tests/unit/test_user_service.py:40-44
Description: Test mocks internal implementation (table.put_item). Test is fragile and coupled to implementation.
Recommendation: Mock repository interface (save, find_by_email) not internal database operations.
```

### 9.4 Missing Negative Tests

**Violation Example**:
```python
# WRONG: No error scenario tests
class TestUserService:
    def test_create_user_success(self):
        # Happy path...

    # ❌ No tests for ValueError, duplicate email, etc.
```

**Review Finding**:
```
Issue Type: Test Coverage
Severity: High
File: tests/unit/test_user_service.py
Description: Test suite missing negative test cases. No tests for exceptions or error conditions.
Recommendation: Add tests for: duplicate email raises ValueError, invalid data raises ValidationError, etc.
```

### 9.5 Test Quality Checklist

- [ ] Happy path tested
- [ ] Edge cases tested
- [ ] Error scenarios tested
- [ ] Boundary conditions tested
- [ ] Tests are independent and idempotent
- [ ] Proper mocking (mock external dependencies, not internals)
- [ ] Descriptive test names
- [ ] Arrange-Act-Assert pattern followed
- [ ] No environment-dependent tests
- [ ] Code coverage >80%

---

## 10. PERFORMANCE REVIEW

### 10.1 N+1 Query Problem

**Violation Example**:
```python
# WRONG: N+1 queries
def get_users_with_orders():
    users = repository.get_all_users()  # 1 query
    for user in users:
        user.orders = order_repo.get_orders(user.id)  # N queries
    return users
```

**Review Finding**:
```
Issue Type: Performance Issue
Severity: High
File: src/services/user_service.py:120-125
Description: N+1 query problem. Gets all users then queries orders for each user individually.
Recommendation: Use batch query or JOIN to fetch users with orders in single query.
```

### 10.2 Missing Caching

**Violation Example**:
```python
# WRONG: No caching for frequently accessed data
def get_configuration():
    # ❌ Queries database every time, even though config rarely changes
    return config_repo.get_all_config()
```

**Review Finding**:
```
Issue Type: Performance Issue
Severity: Medium
File: src/services/config_service.py:35-37
Description: Configuration data fetched from database on every request. Config rarely changes but is frequently accessed.
Recommendation: Add caching layer (ElastiCache or in-memory cache with TTL) for configuration data.
```

### 10.3 Inefficient Loops

**Violation Example**:
```python
# WRONG: Inefficient nested loops
def find_matching_users(criteria):
    results = []
    for user in all_users:  # O(n)
        for criterion in criteria:  # O(m)
            if criterion_matches(user, criterion):  # O(k)
                results.append(user)
    # ❌ O(n*m*k) complexity
    return results
```

**Review Finding**:
```
Issue Type: Performance Issue
Severity: High
File: src/services/user_service.py:150-157
Description: Nested loops with high complexity O(n*m*k). Performance degrades with data growth.
Recommendation: Use set operations or dictionary lookup for O(n) or O(n log n) complexity.
```

### 10.4 Excessive API Calls

**Violation Example**:
```python
# WRONG: Multiple API calls in loop
def enrich_users(users):
    for user in users:
        # ❌ External API call for each user
        profile = external_api.get_profile(user.id)
        user.profile = profile
```

**Review Finding**:
```
Issue Type: Performance Issue
Severity: High
File: src/services/enrichment_service.py:45-49
Description: External API called in loop. For 100 users, makes 100 API calls serially.
Recommendation: Use batch API endpoint if available, or implement parallel requests with concurrency limit.
```

### 10.5 Missing Database Indexes

**Violation Example**:
```python
# WRONG: Query on unindexed column
def find_by_email(self, email: str):
    # ❌ No index on email column
    response = self.table.scan(
        FilterExpression=Attr('email').eq(email)
    )
```

**Review Finding**:
```
Issue Type: Performance Issue
Severity: Critical
File: src/repositories/user_repository.py:70-74
Description: Table scan on email lookup. Extremely inefficient for large datasets.
Recommendation: Create GSI (Global Secondary Index) on email field. Use Query instead of Scan.
```

### 10.6 Performance Review Checklist

- [ ] No N+1 query problems
- [ ] Appropriate caching for frequently accessed data
- [ ] Efficient algorithms (avoid O(n²) or worse)
- [ ] Batch operations where possible
- [ ] Database queries optimized with indexes
- [ ] Pagination on large result sets
- [ ] Parallel processing where appropriate
- [ ] No blocking operations in async code
- [ ] Connection pooling used
- [ ] Timeout limits configured

---

## 11. REVIEW OUTPUT FORMAT

### 11.1 Standard Finding Format

ALL review findings MUST use this exact format:

```
Issue Type: [Category]
Severity: [Critical | High | Medium | Low]
File: [path/to/file.py:line_number]
Description: [Clear description of the issue]
Recommendation: [Specific, actionable fix]
```

### 11.2 Severity Definitions

**Critical**:
- Security vulnerabilities (hardcoded secrets, SQL injection, no authentication)
- Architecture violations that break separation of concerns
- Production-breaking issues

**High**:
- Missing observability (no logging, tracing, metrics)
- Performance issues that impact scalability
- Missing input validation
- Overly permissive IAM policies

**Medium**:
- Code complexity issues
- Missing tests
- Suboptimal patterns
- Missing pagination

**Low**:
- Style/formatting issues
- Unused code
- Missing documentation
- Minor optimizations

### 11.3 Review Summary Template

```markdown
# Code Review Summary

## Overview
Files Reviewed: X
Total Issues: Y
Critical: Z1 | High: Z2 | Medium: Z3 | Low: Z4

## Critical Issues (Must Fix Before Merge)
[List all critical findings]

## High Priority Issues (Should Fix Before Merge)
[List all high findings]

## Medium Priority Issues (Consider Fixing)
[List all medium findings]

## Low Priority Issues (Optional)
[List all low findings]

## Positive Observations
[What was done well]

## Overall Recommendation
[Approve | Request Changes | Reject]

Reason: [Brief explanation]
```

---

## 12. REVIEW EXECUTION CHECKLIST

When performing code review, systematically check:

1. **Architecture** (Critical)
   - [ ] Proper layer separation
   - [ ] No business logic in handlers
   - [ ] No circular dependencies

2. **Security** (Critical)
   - [ ] No hardcoded secrets
   - [ ] Input validation present
   - [ ] Authentication enforced
   - [ ] IAM least privilege

3. **Observability** (High)
   - [ ] Structured logging
   - [ ] Correlation ID propagation
   - [ ] Metrics collection
   - [ ] Tracing enabled

4. **Infrastructure** (High)
   - [ ] Encryption enabled
   - [ ] Resource tags applied
   - [ ] Log retention configured
   - [ ] Tracing enabled

5. **API Design** (High)
   - [ ] Versioned endpoints
   - [ ] Consistent status codes
   - [ ] Standard error format
   - [ ] Pagination on lists

6. **Code Quality** (Medium)
   - [ ] Simple and readable
   - [ ] No unnecessary complexity
   - [ ] Proper error handling
   - [ ] No code duplication

7. **Testing** (High)
   - [ ] Unit tests present
   - [ ] Edge cases covered
   - [ ] Negative scenarios tested
   - [ ] Proper mocking

8. **Performance** (Medium)
   - [ ] No N+1 queries
   - [ ] Efficient algorithms
   - [ ] Appropriate caching
   - [ ] Database indexes

9. **Dependencies** (Low)
   - [ ] No unused packages
   - [ ] Versions pinned
   - [ ] No vulnerabilities

10. **Documentation** (Low)
    - [ ] Docstrings present
    - [ ] Complex logic commented
    - [ ] README updated

---

## 13. INTEGRATION WITH CI/CD

This review skill should be integrated into:

- **Pre-commit hooks**: Run architecture and security checks
- **Pull request automation**: Generate review findings on PR creation
- **CI/CD pipeline**: Block deployment if critical issues found
- **IDE integration**: Real-time feedback during development

---

**END OF SPECIFICATION**

This skill ensures code meets enterprise production standards through comprehensive, systematic review across architecture, security, observability, performance, and maintainability dimensions.
