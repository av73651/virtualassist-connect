# New Lambda Checklist - MANDATORY for All New Lambda Functions

This checklist MUST be followed when creating ANY new Lambda function to ensure all enforcement mechanisms are in place.

## CRITICAL: Use Scaffolding Script

**DO NOT create Lambda directories manually. Use the scaffolding script:**

```bash
./scripts/create-new-lambda.sh <lambda-name>
```

This script automatically creates a Lambda with:
- ✅ Correct requirements.txt (HTTP exporter, boto3)
- ✅ Docker build script (x86_64 architecture)
- ✅ Test structure (80% coverage requirement)
- ✅ Layer architecture templates
- ✅ Observability decorators
- ✅ Pre-configured pytest and flake8

---

## Pre-Creation Checklist

Before creating a new Lambda, verify:

- [ ] **Reviewed existing Lambdas** to avoid duplication
- [ ] **Checked memory** for relevant lessons: `~/.claude/memory/MEMORY.md`
- [ ] **Reviewed layer architecture**: `skills/patterns/layer-architecture.md`
- [ ] **Reviewed technology standards**: `skills/definitions/technology-standards.md`
- [ ] **Have requirements documented** in `docs/specs/<service>/<service>-requirements.md`
- [ ] **Have design documented** in `docs/specs/<service>/<service>-app-design.md`

---

## Creation Checklist

### Step 1: Create Lambda Using Scaffold

```bash
cd /Users/rameshnagarajan/virtualassist-connect
./scripts/create-new-lambda.sh payment-processor
```

**Verification:**
- [ ] Directory structure created: `backend/lambdas/payment-processor/`
- [ ] `requirements.txt` has HTTP exporter (NOT gRPC)
- [ ] `requirements.txt` has boto3==1.34.0
- [ ] `build-in-docker.sh` exists and is executable
- [ ] Handler template created
- [ ] Service template created
- [ ] Test template created
- [ ] README.md created

### Step 2: Implement Business Logic

**Handler** (`src/handlers/<name>_handler.py`):
- [ ] Uses `@api_gateway_handler` decorator
- [ ] NO business logic in handler
- [ ] Only parse/route/format
- [ ] Delegates to service layer

**Service** (`src/services/<name>_service.py`):
- [ ] Uses `@observe` decorator on all public methods
- [ ] Contains business logic ONLY
- [ ] No HTTP/API Gateway parsing
- [ ] No database parsing

**Repository** (`src/repositories/<name>_repository.py` - if needed):
- [ ] Data access ONLY
- [ ] Returns domain models
- [ ] No business logic

### Step 3: Write Tests

- [ ] Unit tests cover ≥80% of code
- [ ] Tests trace to acceptance criteria
- [ ] Tests follow naming: `test_<feature>_ac_<number>`
- [ ] Integration tests marked with `@pytest.mark.integration`

### Step 4: Build Package (MANDATORY)

```bash
cd backend/lambdas/payment-processor
./build-in-docker.sh
```

**Verification:**
- [ ] Build uses Docker with `--platform linux/amd64`
- [ ] Package size >10MB (has dependencies)
- [ ] `package/pydantic` directory exists
- [ ] `package/boto3` directory exists
- [ ] `package/opentelemetry` directory exists
- [ ] `package/shared` directory exists
- [ ] `package/src` directory exists

### Step 5: Run Pre-Deploy Validation (MANDATORY)

```bash
cd /Users/rameshnagarajan/virtualassist-connect
./scripts/pre-deploy-validation.sh payment-processor
```

**Verification:**
- [ ] Memory files check passed
- [ ] Package dependencies check passed
- [ ] Package size check passed
- [ ] Local Docker import test passed
- [ ] Architecture check passed (x86_64)
- [ ] HTTP exporter check passed

### Step 6: Create CDK Stack

**Stack File** (`infra/stacks/<name>_stack.py`):
- [ ] Uses `add_sre_monitoring()` for custom metrics
- [ ] Sets `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`
- [ ] Sets `SERVICE_NAME=<lambda-name>`
- [ ] Attaches ADOT Layer 1-32-0:2
- [ ] Attaches shared code layer
- [ ] Grants CloudWatch PutMetricData permission
- [ ] Creates CloudWatch alarms
- [ ] Uses least-privilege IAM policies

**Update** (`infra/app.py`):
- [ ] Added stack import
- [ ] Added stack instantiation with correct dependencies

### Step 7: Update Jenkinsfile (if using Jenkins)

```python
LAMBDAS = [
    'hello-world',
    'calculator',
    'sre-platform',
    'payment-processor'  // Add new Lambda here
]
```

### Step 8: Deploy to Dev First

```bash
./scripts/deploy.sh dev payment-processor
```

**Post-Deployment Validation:**
- [ ] Lambda invocation succeeds
- [ ] No import errors in CloudWatch logs
- [ ] Custom metrics appearing in CloudWatch
- [ ] OpenTelemetry traces in X-Ray
- [ ] CloudWatch alarms created

### Step 9: Documentation

- [ ] README.md updated (created by scaffold)
- [ ] API documentation generated
- [ ] Runbook created (if incident-related)
- [ ] CLAUDE.md updated with new Lambda

### Step 10: Memory Update

If you encountered any issues during creation:
- [ ] Documented lesson in `~/.claude/memory/`
- [ ] Updated `MEMORY.md` index
- [ ] Updated relevant skills if needed

---

## Common Mistakes to Avoid

### ❌ NEVER DO THIS

1. **Create Lambda directories manually**
   - Always use `./scripts/create-new-lambda.sh`

2. **Use gRPC exporter**
   ```python
   # WRONG
   opentelemetry-exporter-otlp-proto-grpc==1.32.0
   
   # CORRECT
   opentelemetry-exporter-otlp-proto-http==1.32.0
   ```

3. **Build with pip on local machine**
   ```bash
   # WRONG
   pip install -r requirements.txt -t package/
   
   # CORRECT
   ./build-in-docker.sh
   ```

4. **Skip pre-deploy validation**
   ```bash
   # WRONG
   cdk deploy SomeStack-dev
   
   # CORRECT
   ./scripts/pre-deploy-validation.sh some-lambda
   # THEN deploy
   ```

5. **Forget boto3 in requirements.txt**
   - Custom metrics will fail without boto3

6. **Forget SERVICE_NAME environment variable**
   - Custom metrics won't be emitted

7. **Skip local testing**
   - Runtime errors will occur in production

---

## Enforcement Points for New Lambdas

### Enforcement 1: Scaffolding Script
When Claude creates a new Lambda, I MUST:
1. Run `./scripts/create-new-lambda.sh <name>`
2. NOT create directories manually
3. Use the generated templates

**User can verify:** Check tool calls show scaffold script execution

### Enforcement 2: Pre-Deploy Validation
Before deploying any new Lambda, I MUST:
1. Run `./scripts/pre-deploy-validation.sh <name>`
2. Show validation results
3. NOT deploy if validation fails

**User can verify:** Check tool calls show validation before deploy

### Enforcement 3: Requirements.txt Standard
Every new Lambda MUST have:
- `opentelemetry-exporter-otlp-proto-http` (HTTP, not gRPC)
- `boto3==1.34.0`
- All dependencies from template

**User can verify:** Check requirements.txt in new Lambda directory

### Enforcement 4: Build Script Presence
Every new Lambda MUST have:
- `build-in-docker.sh` script
- Script uses `--platform linux/amd64`

**User can verify:** Check build script exists and has correct flags

### Enforcement 5: Test Coverage
Every new Lambda MUST have:
- pytest.ini with `--cov-fail-under=80`
- Unit tests achieving ≥80% coverage

**User can verify:** Run `pytest tests/` and check coverage report

---

## Quick Reference: New Lambda Commands

```bash
# Create new Lambda
./scripts/create-new-lambda.sh <lambda-name>

# Build package
cd backend/lambdas/<lambda-name>
./build-in-docker.sh

# Run tests
pytest tests/

# Validate (MANDATORY before deploy)
cd /Users/rameshnagarajan/virtualassist-connect
./scripts/pre-deploy-validation.sh <lambda-name>

# Deploy to dev
./scripts/deploy.sh dev <lambda-name>

# Test deployed Lambda
aws lambda invoke --function-name <lambda-name>-dev \
  --payload '{"test":"data"}' \
  --cli-binary-format raw-in-base64-out /tmp/test.json
```

---

## Success Criteria

A new Lambda is considered "correctly created" when:

1. ✅ Created using `create-new-lambda.sh` script
2. ✅ Has correct requirements.txt (HTTP exporter, boto3)
3. ✅ Has build-in-docker.sh script
4. ✅ Has test structure with ≥80% coverage
5. ✅ Follows layer architecture (handler → service → repository)
6. ✅ Uses observability decorators (`@observe`, `@api_gateway_handler`)
7. ✅ Passes `pre-deploy-validation.sh`
8. ✅ Deploys successfully to dev
9. ✅ No runtime errors in CloudWatch logs
10. ✅ Custom metrics appearing in CloudWatch

---

## Integration with Memory Protocol

This checklist is referenced by:
- `docs/CLAUDE-MEMORY-PROTOCOL.md` - Mandates using scaffold for new Lambdas
- `skills/definitions/deployment.md` - Deployment process for new Lambdas
- `~/.claude/memory/deployment_local_testing_requirement_2026-04-04.md` - Testing requirements

**When creating a new Lambda, I MUST:**
1. Check this checklist first
2. Use scaffolding script
3. Follow all steps
4. NOT skip validation
5. Document any new lessons learned

---

## Version History

- **v1.0** (2026-04-04): Initial creation with enforcement mechanisms

---

**This checklist is MANDATORY for all new Lambda functions.**
**Deviation from this process requires explicit user approval.**
