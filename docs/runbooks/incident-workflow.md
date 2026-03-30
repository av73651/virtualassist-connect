# Incident Management Workflow

## Severity Levels

| Level | Definition | Response | Update |
|-------|-----------|----------|--------|
| **SEV-1** | Service down or all users impacted | 15 min | Every 30 min |
| **SEV-2** | Degraded (high latency, partial failures) | 30 min | Every 1 hr |
| **SEV-3** | Limited impact, workaround exists | 4 hrs | Daily |

## Incident Lifecycle

```
DETECT → TRIAGE → INVESTIGATE → RESOLVE → VERIFY → PIR
```

### 1. Detect
- CloudWatch alarm fires (error rate, latency, 4xx/5xx)
- Customer report or anomaly spotted on dashboard
- Health check script failure

### 2. Triage
- Open the CloudWatch dashboard for the affected service (`calculator-api-dashboard-{stage}`)
- Classify severity using the table above
- If SEV-1/2: notify engineering lead immediately

### 3. Investigate
Use the debug runbook and scripts:
```bash
# Quick health check
./scripts/incident/health-check.sh --stage prod

# Pull recent logs with error summary
./scripts/incident/download-logs.sh --stage prod --minutes 30

# Trace a specific failed request
./scripts/incident/trace-lookup.sh --stage prod --correlation-id <id>
```

### 4. Resolve
Apply the appropriate fix — see [Resolution Actions](#resolution-actions) below.

### 5. Verify
```bash
# Confirm service is healthy
./scripts/incident/health-check.sh --stage prod

# Monitor error rate for 10 minutes on dashboard
# Confirm alarms return to OK state
```

### 6. Post-Incident Review (SEV-1/2 only)
Complete within 48 hours. Blameless format:

- **Timeline**: When detected, triaged, resolved, verified
- **Impact**: Duration, users affected, requests failed
- **Root cause**: 5 Whys analysis
- **What went well / what didn't**
- **Action items**: Owner + due date for each

---

## Resolution Actions

| Issue | Diagnosis | Fix |
|-------|----------|-----|
| **Bad deployment** | Errors started after recent `cdk deploy` | Rollback: `git revert <commit> && cdk deploy` |
| **Lambda crash loop** | Repeated 5xx, high error count | Rollback Lambda to previous version (see below) |
| **High latency** | p99 > SLA, no errors | Check Lambda memory/timeout config, cold starts, downstream deps |
| **Validation spike** | High 4xx rate, `VALIDATION_ERROR` | Likely client issue — check request patterns in logs |
| **Division by zero spike** | High 4xx, `DIVISION_BY_ZERO` | Client issue — notify API consumers |
| **Auth failures** | 401/403 spike | Check Cognito user pool status, token expiry, authorizer config |
| **Throttling** | 429 responses | Check API Gateway throttle limits, Lambda concurrency |
| **AWS outage** | Multiple services degraded | Check [AWS Health Dashboard](https://health.aws.amazon.com/) — wait or failover |

---

## Rollback Procedures

### Lambda Version Rollback
```bash
# List recent versions
aws lambda list-versions-by-function \
  --function-name calculator-api-prod \
  --query 'Versions[-5:].[Version,Description,LastModified]' \
  --output table

# Point alias to previous version (if using aliases)
aws lambda update-alias \
  --function-name calculator-api-prod \
  --name live \
  --function-version <previous-version>
```

### CDK Stack Rollback
```bash
# Option 1: Revert code and redeploy
git revert <bad-commit>
cd infra && cdk deploy CalculatorStack-prod

# Option 2: CloudFormation rollback (if deploy failed mid-way)
aws cloudformation rollback-stack --stack-name CalculatorStack-prod
```

### Config Rollback
```bash
# Revert config.json to previous state
git checkout HEAD~1 -- infra/config.json
cd infra && cdk deploy CalculatorStack-prod
```

---

## Escalation

```
CloudWatch Alarm
  → On-call engineer (15 min to acknowledge)
  → Engineering lead (if no ack in 15 min, or SEV-1)
  → VP Engineering (if no resolution in 30 min for SEV-1)
```
