# Documentation Review Skill - Enterprise Specification

## Directive

This skill validates documentation accuracy, completeness, and usability before final deployment.

**Primary Goal**: Ensure documentation is accurate, complete, and enables operations, maintenance, and future development.

**Critical Gate**: Deployment proceeds with complete documentation that accurately reflects implementation.

---

## 1. REVIEW SCOPE

The documentation review validates:
- API documentation (`docs/api/`)
- Architecture documentation (`docs/specs/architecture.md`)
- Deployment guides (`docs/deployment/`)
- Operations runbooks (`docs/operations/`)
- Setup guides (`docs/setup/`)
- Code documentation (docstrings, comments)

**Output**: `docs/reviews/documentation-review-report.md`

---

## 2. REVIEW DIMENSIONS

### 2.1 API Documentation

#### OpenAPI/Swagger Specification
- [ ] **CRITICAL**: OpenAPI spec exists and complete
- [ ] All endpoints documented
- [ ] Request schemas defined
- [ ] Response schemas defined (success and error)
- [ ] Authentication requirements specified
- [ ] Examples provided for requests/responses
- [ ] Status codes documented (200, 201, 400, 401, 403, 404, 500)
- [ ] Headers documented
- [ ] Query parameters documented
- [ ] Path parameters documented

#### API Documentation Accuracy
- [ ] **CRITICAL**: Documentation matches actual implementation
- [ ] Endpoint paths correct
- [ ] HTTP methods correct
- [ ] Request/response formats match code
- [ ] Status codes match implementation
- [ ] Error responses match actual errors
- [ ] Authentication requirements match implementation

**Validation Method**: Compare OpenAPI spec against:
- API Gateway configuration
- Lambda handler code
- DTO definitions
- Error response format

#### API Examples
- [ ] Request examples realistic and working
- [ ] Response examples match actual responses
- [ ] curl commands provided and tested
- [ ] Examples cover happy path and error cases
- [ ] Examples include authentication headers

**Example Quality Check**:
```yaml
# Good Example
POST /users
Request:
{
  "email": "john.doe@example.com",
  "name": "John Doe",
  "role": "user"
}
Response (201):
{
  "id": "usr_abc123",
  "email": "john.doe@example.com",
  "name": "John Doe",
  "role": "user",
  "createdAt": "2024-03-27T10:00:00Z"
}

# Bad Example
POST /users
Request: { "data": "..." }
Response: { "result": "success" }
```

#### API Usage Guide
- [ ] Getting started guide present
- [ ] Authentication flow explained
- [ ] Rate limits documented
- [ ] Pagination explained (if applicable)
- [ ] Filtering/sorting explained
- [ ] Error handling guide
- [ ] Common use cases documented

**Score**: API Documentation: __/100

---

### 2.2 Architecture Documentation

#### Architecture Diagrams
- [ ] **CRITICAL**: High-level architecture diagram exists
- [ ] Component diagram showing all Lambdas
- [ ] Data flow diagrams
- [ ] Event flow diagrams
- [ ] Network architecture (if VPC used)
- [ ] Deployment architecture
- [ ] Diagrams have legends
- [ ] Diagrams are up-to-date with implementation

#### Architecture Description
- [ ] System overview clear
- [ ] Technology stack documented
- [ ] Design decisions explained
- [ ] Trade-offs documented
- [ ] Constraints documented
- [ ] Scalability considerations explained
- [ ] Security architecture described

#### Component Documentation
- [ ] All Lambda functions documented
- [ ] Lambda responsibilities clear
- [ ] Lambda dependencies listed
- [ ] DynamoDB tables documented
- [ ] S3 buckets documented
- [ ] EventBridge buses/rules documented
- [ ] API Gateway configuration documented

#### Accuracy
- [ ] **CRITICAL**: Architecture docs match actual infrastructure
- [ ] Diagrams reflect deployed resources
- [ ] Component descriptions match implementation
- [ ] No outdated information

**Score**: Architecture Documentation: __/100

---

### 2.3 Deployment Documentation

#### Deployment Guide
- [ ] **CRITICAL**: Deployment guide exists
- [ ] Prerequisites listed (AWS CLI, CDK, credentials)
- [ ] Step-by-step deployment instructions
- [ ] Environment configuration explained
- [ ] CDK commands documented
- [ ] Environment variables documented
- [ ] Secrets setup documented
- [ ] Cognito setup documented (if manual steps)
- [ ] Custom domain setup (if applicable)

#### Deployment Accuracy
- [ ] **CRITICAL**: Deployment steps work when followed
- [ ] Commands are copy-paste ready
- [ ] No missing steps
- [ ] No incorrect commands
- [ ] Environment-specific instructions clear

**Example Deployment Steps**:
```bash
# Prerequisites
- AWS CLI v2.x
- AWS CDK v2.x
- Python 3.12+
- Valid AWS credentials

# Step 1: Install dependencies
cd infra
pip install -r requirements.txt

# Step 2: Bootstrap CDK (first time only)
cdk bootstrap aws://ACCOUNT-ID/us-east-1

# Step 3: Deploy all stacks
cdk deploy --all --context env=dev

# Step 4: Verify deployment
curl https://api.dev.example.com/health
```

#### Rollback Procedures
- [ ] Rollback steps documented
- [ ] How to identify issues
- [ ] How to roll back CDK stacks
- [ ] Data rollback considerations
- [ ] Emergency contacts

#### Environment Management
- [ ] Dev environment setup documented
- [ ] Staging environment setup documented
- [ ] Production environment setup documented
- [ ] Differences between environments clear
- [ ] How to promote between environments

**Score**: Deployment Documentation: __/100

---

### 2.4 Operations Documentation

#### Runbooks
- [ ] **CRITICAL**: Runbooks exist for common scenarios
- [ ] How to investigate errors
- [ ] How to check system health
- [ ] How to view logs
- [ ] How to query metrics
- [ ] How to trace requests
- [ ] How to scale resources
- [ ] How to update configuration

#### Incident Response
- [ ] Incident response procedures documented
- [ ] How to identify incidents (alarms, metrics)
- [ ] Incident severity levels defined
- [ ] Escalation procedures
- [ ] Communication templates
- [ ] Post-mortem template

#### Monitoring & Alerting
- [ ] Monitoring strategy documented
- [ ] Key metrics documented
- [ ] CloudWatch dashboard links
- [ ] X-Ray service map link
- [ ] Log query examples
- [ ] Alarm thresholds documented
- [ ] Alert destinations documented

#### Common Issues
- [ ] Troubleshooting guide present
- [ ] Common errors documented with solutions
- [ ] Known issues and workarounds
- [ ] FAQ section

**Example Runbook**:
```markdown
## Runbook: High Error Rate

### Symptoms
- Error rate > 1% in CloudWatch
- Alarm triggered: "HighErrorRate"

### Investigation Steps
1. Check CloudWatch dashboard: [link]
2. Query recent errors:
   ```
   fields @timestamp, @message, level, errorCode
   | filter level = "ERROR"
   | sort @timestamp desc
   | limit 50
   ```
3. Check X-Ray for failed traces: [link]
4. Identify error pattern (validation, database, external API)

### Resolution
- **If validation errors**: Check recent code changes
- **If database errors**: Check DynamoDB metrics, throttling
- **If external API errors**: Check third-party status pages

### Escalation
If unresolved after 30 minutes, contact: [team/person]
```

**Score**: Operations Documentation: __/100

---

### 2.5 Setup & Configuration

#### Development Setup
- [ ] Local development setup guide
- [ ] Required tools and versions
- [ ] IDE setup recommendations
- [ ] How to run tests locally
- [ ] How to run Lambda locally (if applicable)
- [ ] How to use localstack

#### Configuration Guide
- [ ] Environment variables documented
- [ ] Secrets configuration documented
- [ ] Feature flags (if any)
- [ ] How to update configuration
- [ ] Configuration validation

#### Testing Guide
- [ ] How to run unit tests
- [ ] How to run integration tests
- [ ] How to generate coverage report
- [ ] How to run linters
- [ ] How to run type checking

**Score**: Setup Documentation: __/100

---

### 2.6 Code Documentation

#### Docstrings
- [ ] All modules have docstrings
- [ ] All classes have docstrings
- [ ] All public functions have docstrings
- [ ] Docstrings follow convention (Google, NumPy, or reStructuredText)
- [ ] Parameters documented
- [ ] Return values documented
- [ ] Exceptions documented
- [ ] Examples in docstrings (for complex functions)

**Good Docstring Example**:
```python
def create_user(request: CreateUserDto) -> User:
    """
    Create a new user in the system.

    Args:
        request: User creation request containing email and name.

    Returns:
        User: Created user with generated ID and timestamps.

    Raises:
        DuplicateEmailError: If user with email already exists.
        ValidationError: If email format is invalid.

    Example:
        >>> request = CreateUserDto(email="test@example.com", name="Test")
        >>> user = create_user(request)
        >>> print(user.id)
        usr_abc123
    """
```

#### Inline Comments
- [ ] Complex logic has explanatory comments
- [ ] Comments explain "why", not "what"
- [ ] No outdated comments
- [ ] No commented-out code

**Good Comment**:
```python
# Use composite key to avoid hot partition for status queries
partition_key = f"{user.status}#{uuid.uuid4()}"
```

**Bad Comment**:
```python
# Set partition key
partition_key = f"{user.status}#{uuid.uuid4()}"
```

#### README Files
- [ ] Root README exists and complete
- [ ] Module-level READMEs where appropriate
- [ ] README explains project structure
- [ ] README links to other documentation

**Score**: Code Documentation: __/100

---

### 2.7 Documentation Completeness

#### Coverage
- [ ] All implemented features documented
- [ ] All API endpoints documented
- [ ] All CDK stacks documented
- [ ] All Lambda functions documented
- [ ] All DynamoDB tables documented
- [ ] All EventBridge events documented

#### Missing Documentation
Identify any gaps:
- Features implemented but not documented
- Endpoints missing from API docs
- Operations procedures missing
- Troubleshooting scenarios missing

#### Outdated Documentation
- [ ] No references to removed features
- [ ] No references to old technologies
- [ ] Version numbers current
- [ ] Screenshots up-to-date

**Score**: Completeness: __/100

---

### 2.8 Documentation Quality

#### Clarity
- [ ] Documentation clear and easy to understand
- [ ] Technical terms defined or linked
- [ ] Audience appropriate (developers, operators, users)
- [ ] Consistent terminology
- [ ] Active voice used

#### Organization
- [ ] Logical structure
- [ ] Table of contents for long documents
- [ ] Consistent formatting
- [ ] Easy navigation
- [ ] Cross-references work

#### Accuracy
- [ ] **CRITICAL**: All documentation matches implementation
- [ ] Code examples syntactically correct
- [ ] Commands tested and working
- [ ] No broken links
- [ ] Diagrams accurate

#### Usability
- [ ] Quick start guide available
- [ ] Examples provided
- [ ] Common tasks easy to find
- [ ] Troubleshooting easy to navigate
- [ ] Search-friendly (if docs system has search)

**Score**: Documentation Quality: __/100

---

## 3. REVIEW OUTPUT FORMAT

### 3.1 Review Report Structure

**File**: `docs/reviews/documentation-review-report.md`

```markdown
# Documentation Review Report

**Date**: YYYY-MM-DD
**Reviewer**: [AI/Developer Name]
**Documentation Version**: [Git commit]
**Status**: [PASS / CONDITIONAL PASS / FAIL]

---

## Executive Summary

[2-3 paragraph summary of documentation quality]

**Overall Documentation Score**: __/100

**Recommendation**:
- [ ] ✅ APPROVED - Documentation complete and accurate
- [ ] ⚠️ CONDITIONAL - Address gaps below
- [ ] ❌ BLOCKED - Major documentation missing or inaccurate

---

## Score Breakdown

| Dimension | Score | Status |
|-----------|-------|--------|
| API Documentation | __/100 | PASS/FAIL |
| Architecture Documentation | __/100 | PASS/FAIL |
| Deployment Documentation | __/100 | PASS/FAIL |
| Operations Documentation | __/100 | PASS/FAIL |
| Setup Documentation | __/100 | PASS/FAIL |
| Code Documentation | __/100 | PASS/FAIL |
| Completeness | __/100 | PASS/FAIL |
| Quality | __/100 | PASS/FAIL |
| **TOTAL** | **__/100** | **PASS/FAIL** |

**Passing Criteria**:
- Overall score ≥ 80%
- API documentation complete and accurate
- Deployment guide working
- Operations runbooks present
- No CRITICAL inaccuracies

---

## Detailed Findings

### 1. API Documentation

#### ✅ Documented Endpoints (count: X)
- POST /users - Complete with examples
- GET /users/{id} - Complete with examples
- PUT /users/{id} - Complete with examples
- DELETE /users/{id} - Complete

#### ❌ Issues (count: X)

**[API-DOC-001] Missing error response schemas**
- **Endpoints**: GET /users, POST /orders
- **Impact**: HIGH - Developers don't know error format
- **Location**: `docs/api/openapi.yaml`
- **Fix**: Add error response schemas for 400, 404, 500

**[API-DOC-002] Request example incorrect**
- **Endpoint**: PUT /users/{id}
- **Issue**: Example shows "username" field, but API expects "name"
- **Impact**: HIGH - Misleading to developers
- **Location**: `docs/api/openapi.yaml:145`
- **Fix**: Correct field name to "name"

**[API-DOC-003] Status code mismatch**
- **Endpoint**: POST /users
- **Documentation**: Says returns 200
- **Actual**: Returns 201
- **Impact**: MEDIUM
- **Fix**: Update docs to show 201

---

### 2. Architecture Documentation

#### ✅ Present
- High-level architecture diagram
- Component diagram
- Technology stack documented

#### ❌ Missing/Issues

**[ARCH-DOC-001] Data flow diagram missing**
- **Impact**: MEDIUM
- **Need**: Show how data flows through system
- **Fix**: Add data flow diagram showing API → Lambda → DynamoDB → EventBridge

**[ARCH-DOC-002] Event schema documentation missing**
- **Impact**: HIGH
- **Need**: Document EventBridge event schemas
- **Fix**: Add section with all event types and schemas

**[ARCH-DOC-003] Lambda function descriptions incomplete**
- **Functions**: order-processor, notification-sender
- **Impact**: MEDIUM
- **Fix**: Add purpose, inputs, outputs, dependencies

---

### 3. Deployment Documentation

#### ✅ Good Coverage
- Prerequisites clear
- Step-by-step instructions
- Commands copy-paste ready

#### ⚠️ Issues

**[DEPLOY-DOC-001] Missing Secrets Manager setup**
- **Impact**: HIGH - Deployment will fail without secrets
- **Fix**: Add step for creating secrets:
  ```bash
  aws secretsmanager create-secret \
    --name virtualassist/dev/api-key \
    --secret-string "your-api-key"
  ```

**[DEPLOY-DOC-002] Cognito user pool setup not documented**
- **Impact**: HIGH
- **Fix**: Add manual steps or CDK configuration for Cognito

**[DEPLOY-DOC-003] Rollback procedure incomplete**
- **Impact**: MEDIUM
- **Fix**: Add detailed rollback steps

---

### 4. Operations Documentation

#### ✅ Present
- Basic runbooks exist
- CloudWatch dashboard linked

#### ❌ Missing

**[OPS-DOC-001] No runbook for database migration issues**
- **Impact**: HIGH
- **Fix**: Add runbook for DynamoDB migration failures

**[OPS-DOC-002] No incident response procedure**
- **Impact**: MEDIUM
- **Fix**: Add incident response guide with severity levels

**[OPS-DOC-003] Common issues section empty**
- **Impact**: MEDIUM
- **Fix**: Document known issues and resolutions

**[OPS-DOC-004] Log query examples insufficient**
- **Impact**: LOW
- **Fix**: Add more CloudWatch Insights query examples

---

### 5. Setup Documentation

#### ✅ Good
- Local development setup clear
- Testing guide present

#### ⚠️ Issues

**[SETUP-DOC-001] IDE setup recommendations missing**
- **Impact**: LOW
- **Fix**: Add VSCode/PyCharm setup guide

**[SETUP-DOC-002] localstack setup not documented**
- **Impact**: MEDIUM
- **Fix**: Add localstack configuration for local testing

---

### 6. Code Documentation

#### Docstring Coverage
- **Modules with docstrings**: 12/15 (80%)
- **Classes with docstrings**: 18/20 (90%)
- **Functions with docstrings**: 45/60 (75%)

#### ⚠️ Issues

**[CODE-DOC-001] Missing docstrings in repositories/**
- **Files**: user_repository.py, order_repository.py
- **Impact**: MEDIUM
- **Fix**: Add docstrings to all repository methods

**[CODE-DOC-002] Service layer docstrings incomplete**
- **Issue**: Missing exception documentation
- **Impact**: MEDIUM
- **Fix**: Document all exceptions that methods can raise

**[CODE-DOC-003] Complex lambda handler lacks comments**
- **File**: order_handler.py
- **Impact**: LOW
- **Fix**: Add comments explaining complex routing logic

---

### 7. Completeness

#### Missing Documentation
- [ ] EventBridge event schemas
- [ ] Database migration guide
- [ ] Disaster recovery procedures
- [ ] Performance tuning guide
- [ ] Security best practices for operators

#### Outdated Documentation
- [OUTDATED-001] Architecture diagram shows Lambda at 256MB, actual is 512MB
- [OUTDATED-002] README mentions DynamoDB on-demand, now provisioned

---

### 8. Documentation Quality

#### ✅ Strengths
- Clear writing
- Good examples in API docs
- Consistent formatting

#### ⚠️ Areas for Improvement
- Some broken internal links
- Screenshots would help deployment guide
- More diagrams needed for complex flows

---

## Issue Summary

| Severity | Count | Must Fix |
|----------|-------|----------|
| ❌ CRITICAL | X | YES |
| ⚠️ MAJOR | X | YES |
| ⚠️ MINOR | X | NO (recommended) |
| ℹ️ INFO | X | NO |

---

## Documentation Accuracy Validation

### API Documentation vs Implementation
- ✅ Endpoints match API Gateway
- ❌ 3 status code mismatches
- ❌ 2 request schema mismatches
- ✅ Response schemas accurate

### Architecture Documentation vs Infrastructure
- ✅ Diagrams mostly accurate
- ⚠️ Some resource configurations outdated
- ❌ Missing new EventBridge rules

### Deployment Guide Validation
- ✅ Commands tested and working
- ❌ Missing prerequisite: Secrets Manager setup
- ❌ Missing step: Cognito configuration

---

## Recommended Actions

### Before Deployment (CRITICAL/MAJOR):
1. [API-DOC-001] Add missing error response schemas
2. [API-DOC-002] Fix incorrect request examples
3. [DEPLOY-DOC-001] Add Secrets Manager setup steps
4. [DEPLOY-DOC-002] Document Cognito setup
5. [ARCH-DOC-002] Document EventBridge event schemas
6. [OPS-DOC-001] Add database migration runbook

### Recommended Improvements (MINOR):
1. [ARCH-DOC-001] Add data flow diagram
2. [CODE-DOC-001] Add repository docstrings
3. [OPS-DOC-002] Add incident response guide
4. [SETUP-DOC-002] Document localstack setup
5. Fix broken links
6. Update outdated diagrams

---

## Documentation Coverage

| Document Type | Status | Notes |
|---------------|--------|-------|
| API Docs (OpenAPI) | ⚠️ INCOMPLETE | Missing error schemas |
| Architecture Diagrams | ⚠️ OUTDATED | Update resource configs |
| Deployment Guide | ⚠️ GAPS | Missing secrets/Cognito setup |
| Operations Runbooks | ⚠️ INCOMPLETE | Need more scenarios |
| Setup Guide | ✅ COMPLETE | - |
| Code Docstrings | ⚠️ INCOMPLETE | 75% coverage |
| README | ✅ COMPLETE | - |

---

## Usability Assessment

### Can a new developer:
- [ ] ⚠️ Understand the architecture? (Missing diagrams)
- [ ] ✅ Set up local development? (Yes)
- [ ] ⚠️ Deploy to AWS? (Missing steps)
- [ ] ✅ Run tests? (Yes)
- [ ] ⚠️ Understand API? (Some inaccuracies)
- [ ] ⚠️ Troubleshoot issues? (Limited runbooks)

---

## Quality Checklist

Developer must verify:
- [ ] All CRITICAL issues resolved
- [ ] All MAJOR issues resolved or documented
- [ ] API documentation matches implementation
- [ ] Deployment guide tested and working
- [ ] Operations runbooks cover common scenarios
- [ ] Code documentation adequate
- [ ] No broken links
- [ ] No outdated information

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
1. Documentation complete
2. Ready for deployment
3. Consider ongoing documentation maintenance plan

If CHANGES REQUESTED:
1. Address issues listed in "Recommended Actions"
2. Update documentation
3. Verify accuracy
4. Re-run documentation review
5. Obtain approval

If REJECTED:
1. Major documentation gaps or inaccuracies
2. Comprehensive documentation update needed
3. Re-review after updates
```

---

## 4. REVIEW PROCESS

### 4.1 Review Execution Steps

1. **Load All Documentation**
   - Read docs/api/
   - Read docs/specs/
   - Read docs/deployment/
   - Read docs/operations/
   - Read docs/setup/
   - Read code docstrings

2. **Validate API Documentation**
   - Compare OpenAPI spec to implementation
   - Check Lambda handlers for endpoints
   - Verify request/response DTOs
   - Test API examples with curl

3. **Validate Architecture Documentation**
   - Compare diagrams to deployed infrastructure
   - Check CDK stacks against architecture docs
   - Verify component descriptions

4. **Test Deployment Guide**
   - Follow deployment steps
   - Execute commands
   - Identify missing steps
   - Verify success

5. **Review Operations Documentation**
   - Check runbooks for completeness
   - Verify log queries work
   - Validate dashboard links
   - Check troubleshooting guide

6. **Check Code Documentation**
   - Scan for missing docstrings
   - Validate docstring quality
   - Check inline comments

7. **Identify Gaps**
   - Missing documentation
   - Outdated documentation
   - Inaccurate documentation

8. **Generate Report**
   - Document all findings
   - Categorize issues
   - Provide recommendations

9. **Developer Approval Gate**
   - Developer reviews report
   - Developer tests documentation
   - Developer addresses issues
   - Developer explicitly approves

---

## 5. SEVERITY DEFINITIONS

### ❌ CRITICAL
- **Definition**: Documentation inaccuracy that will cause failure
- **Impact**: Deployment or operations blocked
- **Must Fix**: YES
- **Examples**: Wrong commands, missing required steps, incorrect API schemas

### ⚠️ MAJOR
- **Definition**: Significant documentation gap
- **Impact**: Difficulty in operations or development
- **Must Fix**: YES
- **Examples**: Missing runbooks, incomplete deployment guide, missing API docs

### ⚠️ MINOR
- **Definition**: Documentation improvement opportunity
- **Impact**: Minor inconvenience
- **Must Fix**: NO, but recommended
- **Examples**: Missing examples, formatting issues, minor gaps

### ℹ️ INFO
- **Definition**: Suggestion or enhancement
- **Impact**: None
- **Must Fix**: NO

---

## 6. APPROVAL CRITERIA

### PASS (Documentation Complete)
- Overall score ≥ 80%
- API documentation accurate and complete
- Deployment guide working
- Operations runbooks present
- No CRITICAL inaccuracies
- Developer sign-off

### CONDITIONAL PASS
- Overall score ≥ 70%
- Minor gaps or inaccuracies
- Most critical docs complete
- Developer sign-off with conditions

### FAIL (Documentation Incomplete)
- Overall score < 70%
- Major gaps or inaccuracies
- Critical documentation missing
- Deployment guide not working

---

## 7. COMMON DOCUMENTATION ISSUES

### Issue: API Documentation Out of Sync
- **Problem**: Code changed but docs not updated
- **Prevention**: Generate docs from code (OpenAPI from DTOs)
- **Fix**: Automate doc generation in CI/CD

### Issue: Broken Links
- **Problem**: Internal links break when files move
- **Prevention**: Link checker in CI/CD
- **Fix**: Use relative links, run link checker

### Issue: Outdated Diagrams
- **Problem**: Architecture changes but diagrams don't
- **Prevention**: Diagrams as code (Mermaid, PlantUML)
- **Fix**: Update diagrams in each PR

### Issue: Missing Runbooks
- **Problem**: Incidents occur but no procedures
- **Prevention**: Create runbooks during development
- **Fix**: Document as issues are resolved

---

## 8. DOCUMENTATION MAINTENANCE

### Keep Documentation Current
- Update docs in same PR as code changes
- Review docs in code review
- Run documentation review periodically
- Use automation where possible (OpenAPI generation)

### Documentation Standards
- Markdown for text documents
- OpenAPI 3.0 for API docs
- Mermaid or PlantUML for diagrams
- Google or NumPy style for docstrings

---

**Good documentation is essential for system maintainability and knowledge transfer. This review ensures documentation is accurate, complete, and useful.**
