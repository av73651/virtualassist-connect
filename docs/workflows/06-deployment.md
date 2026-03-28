# Phase 6: Deployment

## Objective
Deploy application to AWS environments safely and reliably with rollback capabilities.

## Deployment Environments

### 1. Development (dev)
- **Purpose**: Active development and testing
- **Deployment**: Automatic on merge to `develop` branch
- **Access**: Development team
- **Data**: Synthetic/test data

### 2. Staging (staging)
- **Purpose**: Pre-production testing and validation
- **Deployment**: Manual trigger from `main` branch
- **Access**: QA team and stakeholders
- **Data**: Anonymized production-like data

### 3. Production (prod)
- **Purpose**: Live application serving users
- **Deployment**: Manual approval required
- **Access**: End users
- **Data**: Real production data
- **Backup**: Automated, tested recovery

## Deployment Process

### 1. Pre-Deployment Checklist
- [ ] All tests passing (unit, integration, E2E)
- [ ] Code review approved
- [ ] Documentation updated
- [ ] Security scan clean
- [ ] Performance tests passed
- [ ] Database migrations tested
- [ ] Rollback plan ready
- [ ] Monitoring alerts configured

### 2. Infrastructure Deployment (CDK)

```bash
# Set environment
export ENVIRONMENT=dev  # or staging, prod

# Verify changes
cd infra
cdk diff

# Deploy infrastructure
cdk deploy --all --require-approval never

# Verify deployment
aws cloudformation describe-stacks \
  --stack-name VirtualAssistConnectApi-${ENVIRONMENT}
```

### 3. Backend Deployment

Lambda functions are deployed via CDK:
- Code packaged automatically
- Layers updated if dependencies changed
- API Gateway updated
- Environment variables configured

**Deployment Steps:**
```bash
# Package Lambda code
cd backend
pip install -r requirements.txt -t ./package

# CDK handles deployment
cd ../infra
cdk deploy ApiStack
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

### 5. Database Migrations

If using DynamoDB or RDS:
```bash
# Backup first
aws dynamodb create-backup --table-name users-prod \
  --backup-name users-backup-$(date +%Y%m%d)

# Run migration scripts
python scripts/migrate_db.py --environment prod

# Verify migration
python scripts/verify_migration.py
```

## Deployment Strategies

### Blue-Green Deployment (Recommended for Production)

1. Deploy new version (Green) alongside current (Blue)
2. Run smoke tests on Green
3. Gradually shift traffic to Green (10%, 50%, 100%)
4. Monitor metrics and errors
5. Keep Blue running for quick rollback

**Implementation:**
- Use Lambda aliases and weighted routing
- CloudFront distribution points to new S3 version
- API Gateway canary deployments

### Rolling Deployment

- Deploy to small percentage of instances
- Monitor health
- Gradually increase percentage
- Complete deployment

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

### CI/CD Pipeline (GitHub Actions Example)

**Location**: `.github/workflows/deploy.yml`

```yaml
# Pipeline stages:
# 1. Build and Test
# 2. Deploy to Dev (automatic)
# 3. Deploy to Staging (manual approval)
# 4. Deploy to Production (manual approval with additional checks)
```

**Pipeline Steps:**
1. Code checkout
2. Run linting
3. Run unit tests
4. Build application
5. Run integration tests
6. Security scan
7. Deploy infrastructure
8. Deploy application
9. Run smoke tests
10. Health check validation

## Monitoring Post-Deployment

### 1. Health Checks
- API endpoint availability
- Lambda function errors
- Database connectivity
- External service integration

### 2. Key Metrics to Monitor
```
- API Gateway: Request count, latency, 4xx/5xx errors
- Lambda: Invocations, duration, errors, throttles
- CloudFront: Cache hit ratio, requests, bandwidth
- Application: User actions, feature usage
```

### 3. Alerts Configuration
- Error rate threshold exceeded
- Response time degradation
- High Lambda concurrent executions
- Cost anomalies

### 4. Dashboards
- CloudWatch dashboard for infrastructure metrics
- Application dashboard for business metrics
- Cost dashboard for spend tracking

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
  --function-name api-handler \
  --name prod \
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
# Rollback CDK stack
cd infra
git checkout <previous-commit>
cdk deploy --all
```

## Post-Deployment Validation

### Smoke Tests
- [ ] Homepage loads
- [ ] User can login
- [ ] AI assistant responds
- [ ] API endpoints accessible
- [ ] Database queries working

### Verification Script
```bash
#!/bin/bash
# smoke-test.sh

API_URL=$1

echo "Running smoke tests..."

# Test health endpoint
curl -f ${API_URL}/health || exit 1

# Test API endpoint
curl -f ${API_URL}/api/test || exit 1

# Test authentication
# Add more tests...

echo "✅ All smoke tests passed"
```

## Deployment Documentation

### Release Notes Template
```markdown
# Release v1.2.3 - 2026-03-27

## New Features
- Feature 1 description
- Feature 2 description

## Bug Fixes
- Fix 1 description

## Infrastructure Changes
- Updated Lambda runtime to Python 3.12
- Added CloudWatch alarms

## Migration Steps
1. Step 1
2. Step 2

## Rollback Instructions
If issues occur, follow: [rollback procedure]

## Known Issues
- Issue 1 (workaround: ...)
```

## AI Skills to Use

- `deployment-validator`: Verify deployment readiness
- `smoke-test-generator`: Generate smoke tests
- `release-notes-generator`: Create release documentation
- `rollback-planner`: Generate rollback procedures

## Deployment Checklist

### Pre-Deployment
- [ ] Code merged to appropriate branch
- [ ] All tests passing
- [ ] Stakeholders notified
- [ ] Deployment window scheduled
- [ ] Rollback plan ready

### During Deployment
- [ ] Deploy infrastructure (CDK)
- [ ] Deploy backend (Lambda)
- [ ] Deploy frontend (S3/CloudFront)
- [ ] Run smoke tests
- [ ] Verify metrics

### Post-Deployment
- [ ] All smoke tests passed
- [ ] Monitoring shows healthy metrics
- [ ] No critical errors in logs
- [ ] Stakeholders notified of completion
- [ ] Release notes published
- [ ] Team debriefing scheduled

## Outputs
- ✅ Application deployed to target environment
- ✅ All services healthy and operational
- ✅ Monitoring and alerts active
- ✅ Documentation updated
- ✅ Release notes published
- ✅ Team notified

## Continuous Improvement
- Review deployment process
- Identify bottlenecks
- Automate manual steps
- Update runbooks
- Share learnings with team

---

**End of SDLC Workflow**

After deployment, cycle back to [Phase 1: Requirements](01-requirements.md) for new features or improvements.
