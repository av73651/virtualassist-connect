# Deployment Skill - Jenkins CI/CD & AWS CDK

## Directive
This skill manages deployments for the VirtualAssist Connect platform using Jenkins CI/CD pipeline and AWS CDK for infrastructure provisioning.

**Primary Goal**: Provide consistent, repeatable deployments across environments (dev, staging, prod) with proper validation gates.

---

## 1. DEPLOYMENT STRATEGIES

### 1.1 Jenkins CI/CD Pipeline (Recommended for Production)

**Purpose**: Reproducible builds using Docker containers with automated testing and artifact creation.

**When to Use**:
- Production deployments
- Staging deployments requiring full test suite
- When you need artifact traceability
- Multi-Lambda builds in parallel

**Pipeline Stages**:
1. **Checkout**: Pull source code from Git
2. **Build CI Images**: Docker build for each Lambda (Python 3.12)
3. **Quality Checks**: Lint (flake8) + Security (safety, bandit)
4. **Unit Tests**: pytest with 80% coverage requirement
5. **Integration Tests**: API endpoint validation (main branch only)
6. **Package ZIP**: Create deployment artifacts
7. **Archive**: Store ZIP files for CDK deployment

**Trigger Methods**:
```bash
# Method 1: Push to branch (auto-triggers Jenkins webhook)
git push origin <branch-name>

# Method 2: Manual trigger via Jenkins CLI
java -jar jenkins-cli.jar -s http://jenkins-url:8080/ \
  -auth <user>:<token> \
  build virtualassist-connect \
  -p BRANCH=feature/calculator-enhancements

# Method 3: Trigger via API (see section 2.1)
```

**Artifacts Location**: `dist/<lambda>/<lambda>-<build-number>.zip`

---

### 1.2 Direct CDK Deployment (Local Development)

**Purpose**: Fast iteration for development and testing.

**When to Use**:
- Local development testing
- Quick infrastructure changes
- Non-production environments
- Emergency hotfixes (with approval)

**Prerequisites**:
1. Lambda packages built in `backend/lambdas/<lambda>/package/`
2. AWS credentials configured
3. CDK CLI installed (`npm install -g aws-cdk`)

**Commands**:
```bash
# Deploy to dev environment
cd infra
cdk deploy --all --context env=dev

# Deploy specific stack
cdk deploy HelloWorldStack-dev --context env=dev
cdk deploy CalculatorStack-dev --context env=dev
cdk deploy SrePlatformStack-dev --context env=dev

# Preview changes before deploy
cdk diff --all --context env=dev

# Destroy stack (careful!)
cdk destroy HelloWorldStack-dev --context env=dev
```

---

## 2. JENKINS INTEGRATION

### 2.1 Jenkins Build Trigger (API)

**Endpoint**: `POST http://<jenkins-url>/job/virtualassist-connect/build`

**Authentication**: Use Jenkins API token

**Example**:
```bash
# Trigger Jenkins build via API
curl -X POST \
  http://jenkins-url:8080/job/virtualassist-connect/build \
  --user <username>:<api-token> \
  --data token=<build-token>
```

### 2.2 GitHub Webhook Integration

**Setup**: Configure GitHub webhook to trigger Jenkins on push

**Events**: `push`, `pull_request`

**Automatic Triggers**:
- Any push to `main` branch → Full pipeline (including integration tests)
- Any push to feature branches → Build + Unit tests only

---

## 3. ENVIRONMENT CONFIGURATION

### 3.1 Environment Selection

Controlled via `infra/config.json`:
```json
{
  "dev": { "account": "...", "region": "us-west-2", ... },
  "staging": { "account": "...", "region": "us-west-2", ... },
  "prod": { "account": "...", "region": "us-west-2", ... }
}
```

**CDK Context**: `--context env=<environment>`

### 3.2 Environment-Specific Settings

| Setting | Dev | Prod |
|---------|-----|------|
| Lambda Memory | 512 MB | 1024 MB |
| Lambda Timeout | 30s | 60s |
| Log Retention | 7 days | 30 days |
| API Throttling | 500/1000 | 2000/5000 |
| Tracing | always_on | parentbased_traceidratio |

---

## 4. DEPLOYMENT VALIDATION

### 4.1 Pre-Deployment Checks

**MUST verify before deploying**:
```bash
# 1. Check code compiles
cd backend/lambdas/calculator
python -m py_compile src/**/*.py

# 2. Run unit tests
pytest tests/unit/ -v

# 3. Run linter
flake8 src/

# 4. Verify CDK synth
cd infra
cdk synth --context env=dev
```

### 4.2 Post-Deployment Validation

**MUST validate after deployment**:
```bash
# 1. Check Lambda function deployed
aws lambda get-function --function-name calculator-api-dev

# 2. Check API Gateway endpoint
curl -X POST https://<api-id>.execute-api.us-west-2.amazonaws.com/dev/calculator/add \
  -H "Content-Type: application/json" \
  -d '{"a": 5, "b": 3}'

# 3. Check CloudWatch logs
aws logs tail /aws/lambda/calculator-api-dev --follow

# 4. Check X-Ray traces
aws xray get-trace-summaries --start-time $(date -u -d '5 minutes ago' +%s) --end-time $(date -u +%s)
```

---

## 5. ROLLBACK PROCEDURES

### 5.1 Lambda Rollback

**Publish versions on each deploy**:
```bash
# Rollback to previous version
aws lambda update-alias \
  --function-name calculator-api-dev \
  --name current \
  --function-version <previous-version>
```

### 5.2 CDK Stack Rollback

**Option 1: Redeploy previous code**
```bash
git checkout <previous-commit>
cd infra
cdk deploy --all --context env=dev
```

**Option 2: CloudFormation rollback**
```bash
aws cloudformation cancel-update-stack \
  --stack-name CalculatorStack-dev
```

---

## 6. DEPLOYMENT SCRIPT

### 6.1 Quick Deploy Script

**Location**: `scripts/deploy.sh`

**Usage**:
```bash
# Deploy to dev
./scripts/deploy.sh dev

# Deploy specific lambda to dev
./scripts/deploy.sh dev calculator

# Deploy to prod (requires confirmation)
./scripts/deploy.sh prod
```

**Script Actions**:
1. Validates environment
2. Rebuilds Lambda packages (if needed)
3. Runs CDK diff
4. Prompts for confirmation
5. Deploys infrastructure
6. Validates deployment

---

## 7. TROUBLESHOOTING

### 7.1 Common Deployment Failures

**Issue**: `Resource handler returned message: "Invalid request provided"`
- **Cause**: Lambda layer incompatibility
- **Fix**: Verify ADOT layer ARN matches Python runtime version

**Issue**: `BUILD FAILED: pydantic-core compilation error`
- **Cause**: Local Python version incompatible (e.g., Python 3.14)
- **Fix**: Use Jenkins Docker build (Python 3.12) or use virtual environment with Python 3.12

**Issue**: `OpenTelemetry import errors at runtime`
- **Cause**: Version mismatch between ADOT layer and requirements.txt
- **Fix**: Ensure OpenTelemetry packages match ADOT layer version (see requirements.txt)

**Issue**: `CDK deploy fails with 'Stack does not exist'`
- **Cause**: First-time deployment or wrong environment context
- **Fix**: Verify `--context env=<env>` and check config.json

### 7.2 Debug Commands

```bash
# Check CDK bootstrap
aws cloudformation describe-stacks \
  --stack-name CDKToolkit

# List deployed stacks
aws cloudformation list-stacks \
  --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE

# Check Lambda function logs
aws logs tail /aws/lambda/<function-name> --follow --since 10m

# Test Lambda function directly
aws lambda invoke \
  --function-name calculator-api-dev \
  --payload '{"body": "{\"a\": 5, \"b\": 3}"}' \
  response.json
```

---

## 8. DEPLOYMENT CHECKLIST

### 8.1 Production Deployment Checklist

- [ ] All unit tests passing (>80% coverage)
- [ ] All integration tests passing
- [ ] Code review approved
- [ ] Design review approved (if applicable)
- [ ] Security scan passed (no critical vulnerabilities)
- [ ] Staging deployment successful
- [ ] Rollback plan documented
- [ ] Stakeholders notified
- [ ] Deployment window scheduled
- [ ] On-call engineer available
- [ ] CloudWatch alarms configured
- [ ] Runbooks updated

### 8.2 Post-Deployment Checklist

- [ ] All Lambda functions healthy
- [ ] API endpoints responding
- [ ] CloudWatch metrics normal
- [ ] X-Ray traces showing no errors
- [ ] Alarms not triggered
- [ ] Integration tests passing against live environment
- [ ] Stakeholders notified of completion

---

## 9. CI/CD BEST PRACTICES

### 9.1 Branch Strategy

- `main`: Production-ready code, requires approval
- `feature/*`: Feature development, auto-builds on push
- `hotfix/*`: Emergency fixes, fast-tracked approval

### 9.2 Deployment Gates (MANDATORY)

Follow `WORKFLOW-GATES.md`:
1. Requirements Review → WAIT for approval
2. Design Review → WAIT for approval (MOST CRITICAL)
3. Task Breakdown → WAIT for approval
4. Code + Test Review (per task) → WAIT for approval
5. Integration Review → WAIT for approval
6. Documentation Review → WAIT for approval

**Never skip gates or deploy without approval.**

### 9.3 Artifact Management

- Jenkins archives all ZIP artifacts
- Artifacts tagged with build number
- Artifacts retained for 10 builds (configurable)
- Download artifacts: `http://jenkins-url/job/virtualassist-connect/<build-number>/artifact/dist/`

---

## 10. SKILLS INTEGRATION

**Use with other skills**:
- After `/code-generation-cdk`: Deploy generated infrastructure
- After `/code-review`: If passed, proceed to deployment
- After `/test-generation`: Run tests before deployment
- After `/integration-review`: Deploy to production

**Example workflow**:
```
/system-design → Design Review (WAIT for approval) →
/code-generation-app → /code-review → 
/test-generation → Jenkins build →
/deployment dev → Integration tests →
/deployment prod (with approval)
```

---

## EXECUTION CHECKLIST

When using this skill:
1. [ ] Determine deployment target (Jenkins vs CDK direct)
2. [ ] Verify environment (dev/staging/prod)
3. [ ] Check pre-deployment validations
4. [ ] Trigger deployment
5. [ ] Monitor deployment progress
6. [ ] Validate post-deployment
7. [ ] Update documentation if needed
8. [ ] Notify stakeholders

---

**For detailed Jenkins pipeline configuration, see `Jenkinsfile` in project root.**
**For CDK stack details, see `infra/stacks/` directory.**
