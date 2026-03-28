# Design Review Skill - Enterprise Specification

## Directive

This skill validates system design artifacts against technology standards, architectural patterns, and requirements before implementation begins.

**Primary Goal**: Ensure design completeness, architectural compliance, and technical feasibility before any code is written.

**Critical Gate**: No code generation proceeds until design review passes and receives explicit developer approval.

---

## 1. REVIEW SCOPE

The design review validates the following artifacts:
- `docs/specs/requirements.md` (input from Stage 1)
- `docs/specs/architecture.md`
- `docs/specs/api-design.md`
- `docs/specs/data-model.md`
- `docs/specs/implementation-plan.md`
- `docs/specs/observability-design.md`
- `docs/specs/security-design.md`

**Output**: `docs/reviews/design-review-report.md`

---

## 2. REVIEW DIMENSIONS

### 2.1 Technology Standards Compliance

**Validation Against**: `definitions/technology-standards.md`

#### Compute Layer Compliance
- [ ] **CRITICAL**: Only AWS Lambda used for compute
- [ ] **CRITICAL**: Python 3.12 runtime specified
- [ ] Lambda memory configuration: 512 MB - 1024 MB
- [ ] Lambda timeout: 30s (API) or 60s (background)
- [ ] X-Ray tracing enabled in design
- [ ] Environment variables used for config (no hardcoded values)
- [ ] Lambda layers specified for shared dependencies

**Forbidden Technologies Check**:
- [ ] ❌ No EC2 instances for application hosting
- [ ] ❌ No ECS/EKS containers (unless explicitly justified)
- [ ] ❌ No self-managed compute infrastructure

#### API Layer Compliance
- [ ] **CRITICAL**: API Gateway (REST or HTTP API) used
- [ ] CORS configuration specified
- [ ] Request validation at API Gateway level
- [ ] API Gateway authorizers specified (Cognito or Lambda)
- [ ] Throttling and rate limiting configured
- [ ] API keys or usage plans if needed

**Forbidden**:
- [ ] ❌ No custom API servers (Express, FastAPI, etc.)
- [ ] ❌ No Application Load Balancer + containers

#### Data Layer Compliance
- [ ] **CRITICAL**: DynamoDB used for primary data storage
- [ ] DynamoDB tables have GSIs designed for access patterns
- [ ] S3 used for object/file storage
- [ ] S3 lifecycle policies specified
- [ ] Encryption at rest enabled (DynamoDB and S3)
- [ ] Backup and recovery strategy defined

**Forbidden**:
- [ ] ❌ No RDS or relational databases (unless explicitly justified)
- [ ] ❌ No ElastiCache (unless explicitly justified)
- [ ] ❌ No self-hosted databases

#### Messaging & Events Compliance
- [ ] EventBridge used for event-driven patterns
- [ ] Event schemas defined
- [ ] SQS queues for async processing
- [ ] Dead-letter queues configured
- [ ] Event retry policies defined

**Forbidden**:
- [ ] ❌ No Kafka or self-managed messaging
- [ ] ❌ No SNS (use EventBridge instead)

#### AI/ML Compliance
- [ ] Amazon Bedrock used for AI capabilities
- [ ] Claude models specified
- [ ] Prompt templates designed
- [ ] Token limits and costs considered

**Forbidden**:
- [ ] ❌ No self-hosted LLMs
- [ ] ❌ No direct OpenAI API calls (use Bedrock)

#### Frontend Compliance
- [ ] Angular 17+ specified
- [ ] Standalone components architecture
- [ ] S3 + CloudFront for hosting
- [ ] CloudFront caching strategy
- [ ] Security headers configured

**Forbidden**:
- [ ] ❌ No React, Vue, or other frameworks
- [ ] ❌ No Vercel, Netlify (use S3 + CloudFront)

#### Infrastructure Compliance
- [ ] **CRITICAL**: AWS CDK (Python) used for all infrastructure
- [ ] All resources defined in CDK stacks
- [ ] No manual resource creation
- [ ] Stack organization follows best practices
- [ ] Resource tagging strategy defined
- [ ] Environment separation (dev/staging/prod)

**Forbidden**:
- [ ] ❌ No Terraform, CloudFormation YAML
- [ ] ❌ No manual console configurations

#### Security Compliance
- [ ] Cognito user pools for authentication
- [ ] IAM roles follow least privilege
- [ ] Secrets Manager for sensitive data
- [ ] No secrets in environment variables
- [ ] VPC configuration if needed (rare)

**Score**: Technology Standards Compliance: __/100

---

### 2.2 Architectural Patterns Compliance

**Validation Against**: All files in `patterns/`

#### Layer Architecture (`patterns/layer-architecture.md`)

**Handler Layer Design**:
- [ ] **CRITICAL**: Handlers only route requests, no business logic
- [ ] Handler responsibilities clearly defined:
  - Parse request (path params, query params, body)
  - Apply middleware/decorators
  - Call service layer
  - Return response
- [ ] **FORBIDDEN CHECKS**:
  - [ ] Handlers do NOT contain business logic
  - [ ] Handlers do NOT make database queries
  - [ ] Handlers do NOT call external APIs directly
  - [ ] Handlers do NOT transform data (beyond parsing)

**Service Layer Design**:
- [ ] **CRITICAL**: Service layer contains ALL business logic
- [ ] Service methods have clear signatures defined
- [ ] Services orchestrate repositories and domain models
- [ ] Services throw domain-specific exceptions (not HTTP codes)
- [ ] **FORBIDDEN CHECKS**:
  - [ ] Services do NOT parse HTTP events
  - [ ] Services do NOT format HTTP responses
  - [ ] Services do NOT import boto3 or AWS SDK

**Repository Layer Design**:
- [ ] **CRITICAL**: Repositories only handle data access
- [ ] Repository methods clearly defined (save, find, delete)
- [ ] DynamoDB queries mapped to repository methods
- [ ] Repositories return domain models, not raw dicts
- [ ] **FORBIDDEN CHECKS**:
  - [ ] Repositories do NOT contain business logic
  - [ ] Repositories do NOT make business decisions
  - [ ] Repositories do NOT throw business exceptions

**Domain Layer Design**:
- [ ] Domain models defined (pure Python classes or Pydantic)
- [ ] Domain models are technology-agnostic
- [ ] Domain models contain business rules
- [ ] Domain models do not import AWS services

**DTO Layer Design**:
- [ ] Request DTOs defined with Pydantic
- [ ] Response DTOs defined
- [ ] DTO validation rules specified
- [ ] DTOs separate from domain models

**Directory Structure**:
- [ ] Implementation plan specifies exact directory structure:
  ```
  backend/lambdas/{function}/
    src/
      handlers/
      services/
      repositories/
      domain/
      dto/
      middleware/
      config/
  ```

#### Aspect-Oriented Programming (`patterns/aspect-oriented-programming.md`)

**Decorator Usage Design**:
- [ ] **CRITICAL**: Cross-cutting concerns handled via decorators
- [ ] Decorators specified in implementation plan:
  - [ ] `@require_auth` for authentication
  - [ ] `@tracer.start_as_current_span()` for tracing
  - [ ] `@validate_schema(DTO)` for input validation
  - [ ] `@handle_exceptions` for error handling
- [ ] Business logic remains pure (no logging/auth/validation mixed in)

**Observability Aspects**:
- [ ] Tracing spans defined for service methods
- [ ] Structured logging strategy defined
- [ ] Metrics collection points identified
- [ ] No manual print statements or logging in domain layer

**Security Aspects**:
- [ ] API Gateway authorizers specified (Layer-7 security)
- [ ] Fine-grained authorization decorators if needed
- [ ] Security checks happen before handler execution

**Validation Aspects**:
- [ ] Pydantic models validate at handler boundary
- [ ] No manual validation in service layer
- [ ] Validation errors mapped to 400 responses

#### Development Best Practices (`patterns/development-best-practices.md`)

**Strong Typing**:
- [ ] **CRITICAL**: All function signatures have type hints in design
- [ ] Function parameters typed
- [ ] Return types specified (including `-> None`)
- [ ] Domain models use Pydantic or dataclasses (no raw dicts)
- [ ] No `Any` types unless absolutely necessary

**Single Responsibility**:
- [ ] Each function/method does one thing
- [ ] Function names clearly describe purpose
- [ ] No "and" in function descriptions
- [ ] Guard clauses specified for complex logic

**Test-Driven Traceability**:
- [ ] Test scenarios derived from acceptance criteria
- [ ] Each acceptance criterion has mapped test cases
- [ ] Test names reference AC/REQ IDs

#### Observability Requirements (`patterns/observability-requirements.md`)

**OpenTelemetry Design** (`patterns/opentelemetry-template.md`):
- [ ] **CRITICAL**: OpenTelemetry instrumentation designed
- [ ] ADOT Lambda layer specified in CDK
- [ ] Trace propagation across Lambda boundaries
- [ ] Custom spans for service methods
- [ ] Trace IDs included in log messages
- [ ] Metrics defined (custom business metrics)
- [ ] CloudWatch log groups with retention
- [ ] X-Ray integration enabled

**Structured Logging**:
- [ ] JSON log format specified
- [ ] Log levels defined (INFO, WARN, ERROR)
- [ ] Trace correlation in logs
- [ ] No PII in logs

**Metrics**:
- [ ] Business metrics defined (user_created, order_placed, etc.)
- [ ] Technical metrics (latency, errors, throttles)
- [ ] CloudWatch dashboard design

**Tracing**:
- [ ] End-to-end trace spans designed
- [ ] Trace context propagation defined
- [ ] X-Ray service map expected behavior

#### DynamoDB Configuration (`patterns/dynamodb-configuration.md`)

**Table Design**:
- [ ] **CRITICAL**: Access patterns identified and documented
- [ ] Primary key (PK, SK) design for each table
- [ ] GSI designs for secondary access patterns
- [ ] Single-table design if appropriate
- [ ] Item structure examples
- [ ] Query patterns mapped to indexes

**Data Access**:
- [ ] Query operations preferred over Scan
- [ ] Batch operations for multiple items
- [ ] Conditional writes for consistency
- [ ] TTL for auto-expiring data if needed

**Performance**:
- [ ] RCU/WCU capacity planning
- [ ] On-demand vs provisioned decision
- [ ] Hot partition avoidance strategy

#### Error Response Format (`patterns/error-response-format.md`)

**Error Design**:
- [ ] **CRITICAL**: Standardized error response format specified
- [ ] Error response structure:
  ```json
  {
    "errorCode": "RESOURCE_NOT_FOUND",
    "message": "User with ID 123 not found",
    "correlationId": "trace-id-here",
    "timestamp": "2024-03-27T10:00:00Z",
    "details": {}
  }
  ```
- [ ] Error codes catalog defined
- [ ] HTTP status code mapping:
  - 400: Validation errors
  - 401: Authentication failures
  - 403: Authorization failures
  - 404: Resource not found
  - 409: Conflict errors
  - 500: Internal errors
- [ ] Custom exception classes designed
- [ ] Exception-to-response mapping specified

#### IAM Least Privilege (`patterns/iam-least-privilege.md`)

**IAM Policy Design**:
- [ ] **CRITICAL**: Each Lambda has minimal IAM permissions
- [ ] IAM policies specified in CDK design
- [ ] Resource-level permissions (no wildcards)
- [ ] Conditions for additional restrictions
- [ ] No `Action: "*"` or `Resource: "*"`
- [ ] Service-specific policies:
  - [ ] DynamoDB: Specific table ARNs
  - [ ] S3: Specific bucket ARNs
  - [ ] Secrets Manager: Specific secret ARNs
  - [ ] EventBridge: Specific bus ARNs

**Security Best Practices**:
- [ ] Separate IAM roles per Lambda
- [ ] No overly permissive policies
- [ ] Least privilege principle applied

**Score**: Architectural Patterns Compliance: __/100

---

### 2.3 Design Completeness

#### Requirements Coverage
- [ ] **CRITICAL**: All requirements from Stage 1 mapped to design
- [ ] Traceability matrix: REQ-ID → Design Component
- [ ] All user stories addressed
- [ ] All acceptance criteria have design solutions
- [ ] Non-functional requirements addressed:
  - [ ] Performance requirements
  - [ ] Security requirements
  - [ ] Scalability requirements
  - [ ] Availability requirements
  - [ ] Compliance requirements

#### API Design Completeness (`docs/specs/api-design.md`)
- [ ] **CRITICAL**: All API endpoints defined
- [ ] For each endpoint:
  - [ ] HTTP method specified (GET, POST, PUT, DELETE)
  - [ ] Path with parameters: `/users/{userId}`
  - [ ] Request schema (headers, query params, body)
  - [ ] Response schema (success and error cases)
  - [ ] Status codes (200, 201, 400, 404, 500)
  - [ ] Authentication requirements
  - [ ] Authorization rules
  - [ ] Rate limiting
- [ ] Request/Response examples provided
- [ ] OpenAPI/Swagger specification ready to generate

#### Data Model Completeness (`docs/specs/data-model.md`)
- [ ] **CRITICAL**: All data entities defined
- [ ] For each DynamoDB table:
  - [ ] Table name
  - [ ] Primary key (PK, SK)
  - [ ] Attributes and types
  - [ ] GSI definitions (index name, keys, projections)
  - [ ] Access patterns mapped to queries
  - [ ] Item size estimates
  - [ ] Example items
- [ ] For each S3 bucket:
  - [ ] Bucket name and purpose
  - [ ] Object key structure
  - [ ] Lifecycle policies
  - [ ] Access patterns
- [ ] Data relationships defined
- [ ] Data flow diagrams

#### Implementation Plan Completeness (`docs/specs/implementation-plan.md`)
- [ ] **CRITICAL**: File-by-file structure for all Lambdas
- [ ] For each Lambda function:
  - [ ] Function name and purpose
  - [ ] Directory structure (handlers, services, repositories, etc.)
  - [ ] Class and function signatures:
    ```python
    class UserService:
        def create_user(self, request: CreateUserDto) -> User
        def get_user(self, user_id: str) -> User | None
        def update_user(self, user_id: str, updates: UpdateUserDto) -> User
        def delete_user(self, user_id: str) -> None
    ```
  - [ ] Decorators specified for each function
  - [ ] Exception handling strategy
  - [ ] Dependencies and imports
  - [ ] Environment variables needed
- [ ] CDK stack structure defined
- [ ] CDK resource definitions outlined
- [ ] Lambda-to-Lambda communication patterns
- [ ] Event schemas for EventBridge

#### Architecture Completeness (`docs/specs/architecture.md`)
- [ ] System architecture diagram (high-level)
- [ ] Component diagram showing all Lambdas
- [ ] Data flow diagrams
- [ ] Event flow diagrams
- [ ] Integration points with external systems
- [ ] Infrastructure topology
- [ ] Network architecture (if VPC used)
- [ ] Deployment architecture (multi-region, DR)

#### Observability Design Completeness (`docs/specs/observability-design.md`)
- [ ] Logging strategy defined
- [ ] Tracing spans identified
- [ ] Metrics catalog:
  - [ ] Business metrics
  - [ ] Technical metrics
  - [ ] SLI/SLO definitions if applicable
- [ ] CloudWatch Logs structure
- [ ] CloudWatch dashboard designs
- [ ] X-Ray tracing strategy
- [ ] Alerting rules defined
- [ ] Monitoring runbooks outlined

#### Security Design Completeness (`docs/specs/security-design.md`)
- [ ] Authentication flow designed (Cognito)
- [ ] Authorization model defined (RBAC, ABAC)
- [ ] IAM policies for each Lambda
- [ ] Secrets management strategy
- [ ] Data encryption (at rest and in transit)
- [ ] Input validation strategy
- [ ] Security headers (CloudFront)
- [ ] CORS configuration
- [ ] Rate limiting and DDoS protection
- [ ] Audit logging for security events
- [ ] Compliance requirements addressed

**Score**: Design Completeness: __/100

---

### 2.4 Design Quality

#### Architectural Quality
- [ ] **Separation of Concerns**: Clear boundaries between layers
- [ ] **Loose Coupling**: Components can change independently
- [ ] **High Cohesion**: Related functionality grouped together
- [ ] **Dependency Direction**: Dependencies point inward (Domain ← Service ← Handler)
- [ ] **No Circular Dependencies**: Clean dependency graph
- [ ] **Interface Segregation**: Interfaces/ABCs defined where needed
- [ ] **DRY Principle**: Shared logic identified and extracted
- [ ] **SOLID Principles**: Design follows SOLID
- [ ] **Scalability**: Design supports horizontal scaling
- [ ] **Fault Tolerance**: Failure modes considered

#### API Design Quality
- [ ] RESTful principles followed (if REST)
- [ ] Consistent naming conventions
- [ ] Versioning strategy defined
- [ ] Resource-oriented design
- [ ] HTTP methods used correctly (GET=read, POST=create, PUT=update, DELETE=delete)
- [ ] Idempotency considered for non-GET methods
- [ ] Pagination for list endpoints
- [ ] Filtering and sorting parameters
- [ ] Consistent error responses
- [ ] HATEOAS if applicable

#### Data Model Quality
- [ ] **Access Pattern First**: Tables designed for query patterns, not entities
- [ ] **Denormalization**: Data duplicated to avoid joins (NoSQL best practice)
- [ ] **Hot Partition Avoidance**: Keys distributed to avoid hot partitions
- [ ] **Item Size**: Items within DynamoDB 400 KB limit
- [ ] **GSI Efficiency**: GSIs support queries without over-fetching
- [ ] **Consistency Model**: Eventual vs strong consistency decisions documented
- [ ] **Data Lifecycle**: TTL, archival, deletion strategies
- [ ] **Migration Strategy**: How to handle schema changes

#### Error Handling Quality
- [ ] All error scenarios identified
- [ ] Custom exceptions for business errors
- [ ] Error propagation strategy
- [ ] Retry logic for transient failures
- [ ] Dead-letter queues for failed messages
- [ ] Circuit breaker patterns if needed
- [ ] Graceful degradation strategies
- [ ] User-friendly error messages (no stack traces to users)

#### Performance Considerations
- [ ] Latency requirements defined
- [ ] Throughput requirements defined
- [ ] Lambda cold start mitigation (provisioned concurrency if needed)
- [ ] DynamoDB capacity planning
- [ ] Caching strategy (if needed)
- [ ] Batch operations where applicable
- [ ] Async processing for long-running tasks
- [ ] No N+1 query patterns

#### Security Considerations
- [ ] OWASP Top 10 addressed
- [ ] Input validation at boundaries
- [ ] SQL injection prevention (parameterized queries)
- [ ] XSS prevention (output encoding)
- [ ] CSRF protection
- [ ] Authentication on all protected endpoints
- [ ] Authorization checks in handlers
- [ ] Sensitive data encrypted
- [ ] No secrets in code or logs
- [ ] Audit trails for sensitive operations

**Score**: Design Quality: __/100

---

### 2.5 Feasibility & Risk Assessment

#### Technical Feasibility
- [ ] All proposed technologies are approved and available
- [ ] Team has expertise in proposed stack
- [ ] No experimental or deprecated technologies
- [ ] Third-party integrations feasible
- [ ] AWS service quotas sufficient
- [ ] Lambda limits considered (timeout, memory, package size)
- [ ] DynamoDB limits considered (item size, throughput)

#### Cost Feasibility
- [ ] Lambda invocation costs estimated
- [ ] DynamoDB costs estimated (storage + RCU/WCU)
- [ ] S3 storage costs estimated
- [ ] Data transfer costs considered
- [ ] Bedrock API costs estimated
- [ ] CloudWatch costs (logs, metrics, traces)
- [ ] Cost optimization strategies identified

#### Implementation Risk Assessment
- [ ] **HIGH RISK**: Complex components identified
- [ ] **MEDIUM RISK**: Moderate complexity components
- [ ] **LOW RISK**: Straightforward components
- [ ] Dependencies on external systems
- [ ] Data migration complexity
- [ ] Integration testing complexity
- [ ] Deployment complexity
- [ ] Rollback strategy defined

#### Identified Risks
Document all design risks:
- Risk description
- Impact (HIGH/MEDIUM/LOW)
- Likelihood (HIGH/MEDIUM/LOW)
- Mitigation strategy

**Score**: Feasibility: __/100

---

### 2.6 Design Consistency

#### Naming Consistency
- [ ] Consistent naming conventions (PascalCase, snake_case, kebab-case)
- [ ] Consistent terminology (e.g., "user" vs "account")
- [ ] Resource naming follows standards (e.g., `virtualassist-{env}-{resource}`)

#### Pattern Consistency
- [ ] Same patterns used across similar components
- [ ] Error handling consistent across all endpoints
- [ ] Logging format consistent
- [ ] Response format consistent

#### Technology Consistency
- [ ] Same technology for same purpose (e.g., all auth via Cognito)
- [ ] No mixing of equivalent technologies
- [ ] Consistent use of AWS services

**Score**: Consistency: __/100

---

### 2.7 Documentation Quality

#### Clarity
- [ ] Design documents clear and unambiguous
- [ ] Technical terms defined
- [ ] Diagrams legible and accurate
- [ ] Examples provided

#### Completeness
- [ ] All sections of design docs filled
- [ ] No "TBD" or "TODO" in design
- [ ] All diagrams have legends
- [ ] All decisions explained

#### Accuracy
- [ ] Diagrams match text descriptions
- [ ] Code examples syntactically correct
- [ ] Data models match API designs
- [ ] No contradictions between documents

**Score**: Documentation Quality: __/100

---

## 3. REVIEW OUTPUT FORMAT

### 3.1 Review Report Structure

**File**: `docs/reviews/design-review-report.md`

```markdown
# Design Review Report

**Date**: YYYY-MM-DD
**Reviewer**: [AI/Developer Name]
**Design Version**: [Git commit or version]
**Status**: [PASS / CONDITIONAL PASS / FAIL]

---

## Executive Summary

[2-3 paragraph summary of review findings]

**Overall Score**: __/100

**Recommendation**:
- [ ] ✅ APPROVED - Proceed to implementation
- [ ] ⚠️ CONDITIONAL - Address issues below before proceeding
- [ ] ❌ BLOCKED - Major redesign required

---

## Score Breakdown

| Dimension | Score | Status |
|-----------|-------|--------|
| Technology Standards Compliance | __/100 | PASS/FAIL |
| Architectural Patterns Compliance | __/100 | PASS/FAIL |
| Design Completeness | __/100 | PASS/FAIL |
| Design Quality | __/100 | PASS/FAIL |
| Feasibility | __/100 | PASS/FAIL |
| Consistency | __/100 | PASS/FAIL |
| Documentation Quality | __/100 | PASS/FAIL |
| **TOTAL** | **__/100** | **PASS/FAIL** |

**Passing Criteria**:
- Overall score ≥ 80%
- No CRITICAL issues
- All MAJOR issues addressed or have mitigation plans

---

## Detailed Findings

### 1. Technology Standards Compliance

#### ✅ Passed Checks (count: X)
- Lambda used for all compute
- Python 3.12 runtime
- DynamoDB for primary data storage
- ...

#### ⚠️ Warnings (count: X)
- [WARNING-001] Lambda timeout set to 90s, exceeds recommended 60s for background tasks
  - **Impact**: MEDIUM
  - **Recommendation**: Reduce timeout or justify exception
  - **Location**: `docs/specs/implementation-plan.md:45`

#### ❌ Critical Issues (count: X)
- [CRITICAL-001] EC2 instance specified for application hosting
  - **Impact**: HIGH - Violates serverless-first principle
  - **Requirement**: MUST use Lambda
  - **Location**: `docs/specs/architecture.md:78`
  - **Action Required**: Remove EC2, redesign with Lambda

#### 🚫 Forbidden Technologies Found (count: X)
- [FORBIDDEN-001] RDS PostgreSQL specified
  - **Impact**: HIGH
  - **Requirement**: Use DynamoDB or justify exception
  - **Location**: `docs/specs/data-model.md:23`

---

### 2. Architectural Patterns Compliance

#### Layer Architecture
✅ **Passed**: XX/YY checks
❌ **Failed**: XX/YY checks

**Issues**:
- [ARCH-001] Service layer method `UserService.get_user()` parses HTTP event
  - **Impact**: HIGH - Violates layer separation
  - **Pattern**: `patterns/layer-architecture.md`
  - **Location**: `docs/specs/implementation-plan.md:123`
  - **Fix**: Move HTTP parsing to handler, pass only `user_id: str` to service

#### Aspect-Oriented Programming
✅ **Passed**: XX/YY checks
⚠️ **Warnings**:
- [AOP-001] No decorator specified for input validation
  - **Impact**: MEDIUM
  - **Recommendation**: Add `@validate_schema(CreateUserDto)` decorator
  - **Location**: `docs/specs/implementation-plan.md:145`

#### OpenTelemetry
✅ **Passed**: XX/YY checks

---

### 3. Design Completeness

#### Requirements Coverage
- ✅ All functional requirements covered: 15/15
- ⚠️ Missing non-functional requirements: 2/7
  - [COMPLETE-001] Performance SLAs not defined
  - [COMPLETE-002] Disaster recovery strategy missing

#### API Design
- ✅ All endpoints defined: 12/12
- ❌ Missing response schemas: 3/12
  - [API-001] GET /users/{id} missing 404 error response
  - [API-002] POST /users missing 409 conflict response
  - [API-003] PUT /users/{id} missing 400 validation error response

#### Data Model
- ✅ All tables defined: 4/4
- ⚠️ Missing access patterns: 2/4 tables
  - [DATA-001] Users table: "Find users by role" access pattern not mapped to GSI

#### Implementation Plan
- ⚠️ Function signatures incomplete
  - [IMPL-001] UserRepository missing `find_by_email()` method signature
  - [IMPL-002] OrderService missing exception specifications

---

### 4. Design Quality

#### Architectural Quality
✅ Strong separation of concerns
✅ Low coupling between components
⚠️ One circular dependency found:
  - [QUALITY-001] ServiceA → ServiceB → ServiceA
  - **Fix**: Extract shared logic to domain model

#### API Design Quality
✅ RESTful principles followed
✅ Consistent naming
⚠️ No pagination on list endpoints
  - [QUALITY-002] GET /users should support pagination

#### Data Model Quality
✅ Access patterns drive design
⚠️ Potential hot partition
  - [QUALITY-003] Status field as partition key may create hot partition for "ACTIVE" status
  - **Fix**: Use composite key with UUID prefix

---

### 5. Feasibility

✅ All technologies approved
✅ Team expertise confirmed
⚠️ Cost concerns:
  - [COST-001] Bedrock usage estimated at $XXX/month - validate budget

---

### 6. Consistency

✅ Naming conventions consistent
✅ Pattern usage consistent
✅ Technology usage consistent

---

### 7. Documentation Quality

✅ Clear and well-written
⚠️ Missing diagrams:
  - [DOC-001] Event flow diagram missing
  - [DOC-002] Data flow diagram incomplete

---

## Issue Summary

| Severity | Count | Must Fix Before Approval |
|----------|-------|--------------------------|
| 🚫 FORBIDDEN | X | YES |
| ❌ CRITICAL | X | YES |
| ⚠️ MAJOR | X | YES |
| ⚠️ MINOR | X | NO (but recommended) |
| ℹ️ INFO | X | NO |

---

## Recommended Actions

### Before Implementation Can Begin:
1. [CRITICAL-001] Remove EC2, replace with Lambda
2. [FORBIDDEN-001] Replace RDS with DynamoDB or provide justification
3. [ARCH-001] Fix layer separation violation in UserService
4. [API-001, 002, 003] Complete API error response schemas
5. [COMPLETE-001] Define performance SLAs
6. [COMPLETE-002] Document disaster recovery strategy

### Recommended Improvements (Can be addressed in implementation):
1. [WARNING-001] Reduce Lambda timeout to 60s
2. [AOP-001] Add validation decorators
3. [QUALITY-002] Add pagination to list endpoints
4. [QUALITY-003] Fix hot partition risk in data model
5. [DOC-001, 002] Complete missing diagrams

---

## Requirements Traceability Matrix

| Requirement ID | Design Component | Status |
|----------------|------------------|--------|
| REQ-001 | User Management Lambda | ✅ Covered |
| REQ-002 | Authentication Flow | ✅ Covered |
| REQ-003 | Order Processing | ✅ Covered |
| ... | ... | ... |

---

## Technology Standards Compliance Summary

| Category | Compliant | Issues |
|----------|-----------|--------|
| Compute | ❌ | EC2 usage |
| API | ✅ | - |
| Data | ⚠️ | RDS usage |
| Messaging | ✅ | - |
| AI/ML | ✅ | - |
| Frontend | ✅ | - |
| Infrastructure | ✅ | - |
| Security | ✅ | - |

---

## Architectural Patterns Compliance Summary

| Pattern | Compliance Score | Issues |
|---------|------------------|--------|
| Layer Architecture | 85% | Service layer violation |
| AOP | 90% | Missing decorators |
| Best Practices | 95% | Minor typing issues |
| Observability | 100% | - |
| OpenTelemetry | 100% | - |
| DynamoDB Config | 85% | Hot partition risk |
| Error Format | 100% | - |
| IAM Least Privilege | 100% | - |

---

## Risk Register

| Risk ID | Description | Impact | Likelihood | Mitigation |
|---------|-------------|--------|------------|------------|
| RISK-001 | Complex EventBridge routing | HIGH | MEDIUM | Add comprehensive integration tests |
| RISK-002 | DynamoDB hot partition | MEDIUM | LOW | Use composite key with UUID |
| ... | ... | ... | ... | ... |

---

## Design Debt

Items intentionally deferred or accepted as technical debt:

1. **[DEBT-001]** Caching layer not included in v1
   - **Rationale**: Premature optimization, add if performance issues
   - **Plan**: Monitor latency, add ElastiCache if p99 > 500ms

---

## Approval Checklist

Developer must verify:
- [ ] All CRITICAL issues resolved
- [ ] All MAJOR issues resolved or have mitigation plans
- [ ] Requirements traceability complete
- [ ] Technology standards compliance achieved
- [ ] Architectural patterns followed
- [ ] Implementation plan ready for coding
- [ ] Team capacity to implement design

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
1. Proceed to Stage 3: Task Elaboration
2. Break implementation-plan.md into tasks
3. Begin code generation

If CHANGES REQUESTED:
1. Address issues listed in "Recommended Actions"
2. Update design documents
3. Re-run design review
4. Obtain approval

If REJECTED:
1. Major redesign required
2. Schedule design review meeting
3. Revise architecture based on feedback
```

---

## 4. REVIEW PROCESS

### 4.1 Review Execution Steps

1. **Load Design Artifacts**
   - Read all files in `docs/specs/`
   - Read requirements from Stage 1

2. **Validate Technology Standards**
   - Load `definitions/technology-standards.md`
   - Check every technology choice against approved list
   - Flag forbidden technologies

3. **Validate Architectural Patterns**
   - Load all `patterns/*.md` files
   - Verify layer architecture compliance
   - Verify AOP patterns applied
   - Verify observability designed
   - Verify data model follows DynamoDB patterns
   - Verify error handling follows standard format
   - Verify IAM follows least privilege

4. **Check Completeness**
   - Verify all requirements mapped to design
   - Verify API design complete
   - Verify data model complete
   - Verify implementation plan has file-level detail

5. **Assess Quality**
   - Check architectural principles (SOLID, DRY, etc.)
   - Check for design smells (circular deps, tight coupling)
   - Check API design quality
   - Check data model quality

6. **Assess Feasibility**
   - Check technical feasibility
   - Estimate costs
   - Identify risks

7. **Generate Report**
   - Create `docs/reviews/design-review-report.md`
   - Categorize issues by severity
   - Provide actionable recommendations
   - Calculate scores

8. **Developer Approval Gate**
   - Developer reviews report
   - Developer addresses critical issues
   - Developer explicitly approves or requests changes

---

## 5. SEVERITY DEFINITIONS

### 🚫 FORBIDDEN
- **Definition**: Unapproved technology used
- **Impact**: Violates platform standards
- **Must Fix**: YES, before any implementation
- **Examples**: EC2 for compute, RDS for data, custom API server

### ❌ CRITICAL
- **Definition**: Architectural violation or missing critical component
- **Impact**: Implementation will fail or violate principles
- **Must Fix**: YES, before implementation
- **Examples**: Business logic in handler, no layer separation, missing IAM policies

### ⚠️ MAJOR
- **Definition**: Incomplete design or quality issue
- **Impact**: Implementation will be difficult or incorrect
- **Must Fix**: YES, before implementation (but may have workarounds)
- **Examples**: Missing error responses, incomplete data model, missing observability

### ⚠️ MINOR
- **Definition**: Best practice violation or improvement opportunity
- **Impact**: Code will work but not optimal
- **Must Fix**: NO, but strongly recommended
- **Examples**: No pagination, suboptimal indexing, missing documentation

### ℹ️ INFO
- **Definition**: Informational note or suggestion
- **Impact**: None
- **Must Fix**: NO
- **Examples**: Consider adding caching, alternative approach available

---

## 6. APPROVAL CRITERIA

### PASS (Approved for Implementation)
- Overall score ≥ 80%
- Zero FORBIDDEN issues
- Zero CRITICAL issues
- Zero MAJOR issues (or all have documented mitigation plans)
- All requirements covered
- Implementation plan complete
- Developer sign-off obtained

### CONDITIONAL PASS (Approved with Conditions)
- Overall score ≥ 70%
- Zero FORBIDDEN issues
- Zero CRITICAL issues
- Some MAJOR issues with documented mitigation plans
- Developer sign-off obtained with conditions

### FAIL (Not Approved)
- Overall score < 70%
- Any FORBIDDEN issues
- Any unresolved CRITICAL issues
- Incomplete design
- No developer sign-off

---

## 7. INTEGRATION WITH WORKFLOW

### Before Design Review:
- Stage 1 (Requirements) complete and approved
- All design artifacts created

### During Design Review:
- AI loads design-review.md skill
- AI executes review process
- AI generates review report

### After Design Review:
- Developer reviews report
- Developer addresses issues
- Developer provides explicit approval
- If approved → Stage 3 (Task Elaboration)
- If rejected → Revise design, repeat review

---

## 8. CONTINUOUS IMPROVEMENT

### Design Review Metrics
Track over time:
- Average review score
- Number of issues per category
- Most common violations
- Time to address issues
- Pass rate on first review

### Update Review Skill When:
- New patterns added to `patterns/`
- Technology standards updated
- Common issues identified
- Team feedback on review process

---

## 9. EXAMPLE REVIEW SCENARIOS

### Scenario 1: Clean Design (PASS)
- All technologies approved
- Layer architecture perfect
- Complete implementation plan
- Zero critical issues
- **Result**: APPROVED, proceed to implementation

### Scenario 2: Forbidden Technology (FAIL)
- Design uses EC2 instead of Lambda
- **Result**: BLOCKED, redesign with Lambda

### Scenario 3: Incomplete Design (CONDITIONAL)
- Architecture sound
- Missing some error response schemas
- Missing performance SLAs
- **Result**: CONDITIONAL, address minor issues during implementation

### Scenario 4: Architectural Violation (FAIL)
- Business logic in handlers
- Services parse HTTP events
- **Result**: BLOCKED, fix layer separation

---

## 10. QUALITY EXPECTATIONS

Reviewers (AI or human) using this skill must:
- Be thorough and systematic
- Check every dimension
- Provide specific, actionable feedback
- Reference exact file locations and line numbers
- Explain WHY something is an issue
- Suggest concrete fixes
- Be objective and consistent
- Focus on architecture, not implementation details

---

**This design review is the most critical gate in the SDLC. A perfect design makes implementation straightforward. A flawed design leads to technical debt, rework, and maintenance issues.**
