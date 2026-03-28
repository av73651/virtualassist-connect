# Phase 6: Deployment

## Objective
Deploy application to AWS environments safely and reliably with rollback capabilities.

## Deployment Environments

### 1. Development (dev)
- **Purpose**: Active development and testing
- **Deployment**: Automatic on merge to `develop` branch
- **Access**: Development team
- **Data**: Synthetic/test data
- **Config**: `infra/config.json` -> `dev` section

### 2. Production (prod)
- **Purpose**: Live application serving users
- **Deployment**: Manual approval required
- **Access**: End users
- **Data**: Real production data
- **Backup**: DynamoDB PITR enabled, automated recovery
- **Config**: `infra/config.json` -> `prod` section

## Deployment Process

### 1. Pre-Deployment Checklist
- [ ] All tests passing (unit, integration, E2E)
- [ ] Code review approved (`skills/definitions/code-review.md`)
- [ ] Test review approved (`skills/definitions/test-review.md`)
- [ ] Documentation updated (`docs/specs/{service-name}/`)
- [ ] Security scan clean
- [ ] Performance tests passed
- [ ] Rollback plan ready
- [ ] CloudWatch alarms configured in CDK stack

### 2. Infrastructure Deployment (CDK)

```bash
# Set environment context
cd infra

# Verify changes before deploying
cdk diff -c env=dev

# Deploy all stacks (AuthStack first, then service stacks)
cdk deploy --all -c env=dev

# Verify deployment
aws cloudformation describe-stacks \
  --stack-name AuthStack-dev
aws cloudformation describe-stacks \
  --stack-name HelloWorldStack-dev
aws cloudformation describe-stacks \
  --stack-name CalculatorStack-dev
```

**CDK Stack Deployment Order:**
1. `AuthStack` — Shared Cognito User Pool (must deploy first)
2. Service stacks (`HelloWorldStack`, `CalculatorStack`) — depend on AuthStack outputs

### 3. Backend Deployment

Lambda functions are deployed via CDK:
- Code packaged from `backend/lambdas/{name}/package/`
- Shared layer from `backend/lambda-layer/`
- ADOT Lambda Layer for OpenTelemetry (auto-instrumentation)
- API Gateway updated with Cognito authorizer
- WAF WebACL attached to API Gateway stage
- Environment variables configured (OTel, CORS, log level)

**Deployment Steps:**
```bash
# Package Lambda code (if not using CDK asset bundling)
cd backend/lambdas/hello-world
pip install -r requirements.txt -t ./package/

# CDK handles the rest
cd ../../../infra
cdk deploy HelloWorldStack-dev -c env=dev
```

### 4. Frontend Deployment

```bash
# Build Angular app
cd frontend
ng build --configuration=production

# Deploy to S3
aws s3 sync dist/ s3://virtualassist-connect-frontend-prod/ \
  --delete

# Invalidate CloudFront cache
aws cloudfront create-invalidation \
  --distribution-id ${DISTRIBUTION_ID} \
  --paths "/*"
```

### 5. Post-Deploy Verification

```bash
# Verify Lambda function is healthy
aws lambda invoke \
  --function-name hello-world-api-dev \
  --payload '{}' response.json

# Verify API Gateway endpoint
curl -H "Authorization: Bearer ${TOKEN}" \
  https://xxx.execute-api.region.amazonaws.com/dev/hello

# Check CloudWatch for OTel metrics
aws cloudwatch get-metric-data \
  --metric-data-queries '[{"Id":"m1","MetricStat":{"Metric":{"Namespace":"VirtualAssist","MetricName":"hello_message_total"},"Period":300,"Stat":"Sum"}}]' \
  --start-time $(date -u -v-5M +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S)
```

## Deployment Strategies

### Blue-Green Deployment (Recommended for Production)

1. Deploy new version (Green) alongside current (Blue)
2. Run smoke tests on Green
3. Gradually shift traffic to Green (10%, 50%, 100%)
4. Monitor CloudWatch metrics and OTel traces
5. Keep Blue running for quick rollback

**Implementation:**
- Use Lambda aliases and weighted routing
- CloudFront distribution points to new S3 version
- API Gateway canary deployments

### Canary Deployment

```python
# CDK implementation
deployment = apigw.Deployment(self, 'Deployment',
    api=api,
    description='Canary deployment'
)

stage = apigw.Stage(self, 'prod',
    deployment=deployment,
    canary_settings=apigw.CanarySettings(
        percent_traffic=10,  # 10% to canary
        use_stage_cache=False
    )
)
```

## Deployment Automation

### CI/CD Pipeline

See `skills/patterns/ci-cd-enforcement.md` for pipeline standards.

**Pipeline Steps:**
1. Code checkout
2. Run linting (flake8, ng lint)
3. Run unit tests (`backend/lambdas/{name}/tests/unit/`)
4. Build application
5. Run integration tests (`backend/lambdas/{name}/tests/integration/`)
6. Security scan
7. CDK diff (review infrastructure changes)
8. CDK deploy (AuthStack first, then service stacks)
9. Run smoke tests
10. Health check validation
11. Verify OTel metrics flowing to CloudWatch

## Monitoring Post-Deployment

### 1. Health Checks
- API endpoint availability (all endpoints behind Cognito auth)
- Lambda function errors (CloudWatch Alarms)
- DynamoDB table health
- WAF blocked request rate

### 2. Key Metrics to Monitor

**AWS Native Metrics:**
- API Gateway: Request count, latency, 4xx/5xx errors
- Lambda: Invocations, duration, errors, throttles, cold starts
- CloudFront: Cache hit ratio, requests, bandwidth

**Custom OTel Metrics (VirtualAssist namespace):**
- `{service}_total` — Operation count by status (success/error)
- `{service}_duration` — Operation latency (p50, p95, p99)
- Error rate % — Computed metric on CloudWatch dashboard

### 3. Alerts Configuration (CDK-Defined)
- High error rate alarm (>10 errors in 2 evaluation periods)
- High latency alarm (p99 > 500ms in 2 evaluation periods)
- Lambda throttle alarm
- WAF blocked request spike

### 4. Dashboards
Each service stack creates a CloudWatch dashboard with:
- Lambda invocations, errors, duration (p50/p95/p99)
- API Gateway requests and latency
- Custom OTel success/error counters
- OTel latency histograms (p50/p95/p99)
- Error rate % (computed)

## Rollback Procedures

### Automatic Rollback Triggers
- Error rate > 5% for 5 minutes
- P95 latency > 3 seconds
- Health check failures

### Manual Rollback

**Lambda Functions:**
```bash
# Revert to previous version
aws lambda update-alias \
  --function-name hello-world-api-dev \
  --name live \
  --function-version $PREVIOUS_VERSION
```

**Frontend:**
```bash
# Rollback S3 content
aws s3 sync s3://backup-bucket/previous-version/ \
  s3://frontend-bucket/ --delete

# Invalidate CloudFront
aws cloudfront create-invalidation \
  --distribution-id ${DISTRIBUTION_ID} \
  --paths "/*"
```

**Infrastructure:**
```bash
# Rollback CDK stack to previous commit
cd infra
git checkout <previous-commit>
cdk deploy --all -c env=dev
```

## Post-Deployment Validation

### Smoke Tests
- [ ] API endpoints accessible (with valid Cognito token)
- [ ] Correct response format (JSON with expected fields)
- [ ] Error responses follow standard format (`ErrorResponse` DTO)
- [ ] CORS headers present
- [ ] OTel traces visible in X-Ray
- [ ] Custom metrics flowing to CloudWatch VirtualAssist namespace

### Verification Script
```bash
#!/bin/bash
# smoke-test.sh
API_URL=$1
TOKEN=$2

echo "Running smoke tests..."

# Test hello endpoint
curl -sf -H "Authorization: Bearer ${TOKEN}" \
  ${API_URL}/hello || exit 1
echo "  /hello OK"

# Test calculator endpoint
curl -sf -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"num1":2,"num2":3,"operation":"add"}' \
  ${API_URL}/calculate || exit 1
echo "  /calculate OK"

echo "All smoke tests passed"
```

## AI Skills Used

| Skill | File | Purpose |
|-------|------|---------|
| Documentation Generation | `skills/definitions/documentation-generation.md` | Generate release notes and deployment docs |
| Documentation Review | `skills/definitions/documentation-review.md` | Review deployment documentation |
| Integration Review | `skills/definitions/integration-review.md` | Validate cross-service integration |

## Patterns Referenced
- `skills/patterns/ci-cd-enforcement.md` — CI/CD pipeline standards
- `skills/patterns/observability-requirements.md` — Post-deployment monitoring standards
- `skills/patterns/opentelemetry-template.md` — OTel verification

## Deployment Checklist

### Pre-Deployment
- [ ] Code merged to appropriate branch
- [ ] All tests passing (unit + integration)
- [ ] Traceability matrix validated (no gaps)
- [ ] Stakeholders notified
- [ ] Deployment window scheduled
- [ ] Rollback plan ready

### During Deployment
- [ ] Deploy AuthStack (if changed)
- [ ] Deploy service stacks (CDK)
- [ ] Verify Lambda functions healthy
- [ ] Run smoke tests
- [ ] Verify CloudWatch metrics

### Post-Deployment
- [ ] All smoke tests passed
- [ ] CloudWatch dashboard shows healthy metrics
- [ ] OTel traces visible in X-Ray
- [ ] No critical errors in logs
- [ ] WAF not blocking legitimate requests
- [ ] Stakeholders notified of completion
- [ ] Release notes published
- [ ] Team debriefing scheduled

## Outputs
- Application deployed to target environment
- All services healthy and operational
- Monitoring and alerts active (CloudWatch + OTel)
- Documentation updated
- Release notes published
- Team notified

## Continuous Improvement
- Review deployment process
- Identify bottlenecks
- Automate manual steps
- Update runbooks
- Share learnings with team

---

**End of SDLC Workflow**

After deployment, cycle back to [Phase 1: Requirements](01-requirements.md) for new features or improvements.
