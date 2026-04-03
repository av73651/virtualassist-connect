---
name: incident-management
description: "Guide incident detection, diagnosis, and resolution across all VirtualAssist services using logs, traces, and metrics."
---

# Incident Management Skill - Enterprise Specification

## Directive

This skill guides incident response, production debugging, and service recovery for all VirtualAssist platform services. It defines how to detect, diagnose, and resolve production issues using the platform's observability stack.

**Primary Goal**: Enable fast, structured incident resolution with minimal MTTR (Mean Time To Resolution) by leveraging structured logs, OpenTelemetry traces, CloudWatch metrics, and automated tooling.

**Scope**:
- Incident detection and triage
- Log analysis and root cause identification
- Trace correlation across services
- Resolution and rollback procedures
- Post-incident review

---

## 1. INCIDENT DETECTION

### CloudWatch Alarms (Auto-Detection)

Every service stack deploys standard alarms. When an alarm fires:

1. Check the service dashboard: `{service}-api-dashboard-{stage}`
2. Identify which metric is breaching (error rate, latency, 4xx)
3. Classify severity per `docs/runbooks/incident-workflow.md`

### Health Check (Manual Detection)

```bash
./scripts/incident/health-check.sh --stage <stage>
```

Validates all endpoints return expected status codes. Exit code 1 = unhealthy.

---

## 2. LOG ANALYSIS

### Log Structure

All services emit structured JSON logs via `shared/config/logging_config.py` with these fields:

| Field | Source | Always Present |
|-------|--------|---------------|
| `timestamp` | logging_config | Yes |
| `level` | logging_config | Yes |
| `logger` | logging_config | Yes |
| `message` | logging_config | Yes |
| `trace_id` | @api_gateway_handler | Yes (in handlers) |
| `request_id` | @api_gateway_handler | Yes (in handlers) |
| `http_method` | @api_gateway_handler | Yes (in handlers) |
| `path` | @api_gateway_handler | Yes (in handlers) |
| `user_id` | @api_gateway_handler (Cognito sub) | Yes (in handlers) |
| `operation` | @observe | Yes (in services) |
| `service` | @observe | Yes (in services) |
| `status` | @observe | Yes (in services) |
| `duration_ms` | @observe | Yes (in services) |
| `error_type` | @observe / @api_gateway_handler | On error |
| `error` | @observe / @api_gateway_handler | On error |
| `request_body` | @api_gateway_handler | On error only |

### Log Retrieval

```bash
# Download and auto-summarize
./scripts/incident/download-logs.sh --stage <stage> --minutes 30

# Find specific request
./scripts/incident/trace-lookup.sh --stage <stage> --correlation-id <id>
```

### CloudWatch Logs Insights

Log group naming: `/aws/lambda/{service}-api-{stage}`

Standard queries are documented in `docs/runbooks/calculator-debug.md`. Key patterns:

- **Errors by type**: Filter `level = "ERROR"`, group by `error_type`
- **Slow requests**: Filter `duration_ms > threshold`, sort descending
- **Request trace**: Filter by `trace_id` to see full request lifecycle
- **Error rate over time**: Count errors per 5-min bucket

---

## 3. TRACE CORRELATION

### Request Flow

Every request follows this observable path:

```
API Gateway → Lambda Handler (@api_gateway_handler logs entry + trace_id)
  → Service Method (@observe logs start/complete/fail + metrics)
    → Domain Logic (raises BusinessRuleError if invalid)
  → @api_gateway_handler formats HTTP response + X-Trace-Id header
```

### Correlation Points

- **X-Trace-Id response header**: Returned to client in every response (success and error)
- **correlationId in error body**: Included in all 4xx/5xx JSON error responses
- **X-Ray trace**: Available in AWS X-Ray console for visual service map

### Investigation Steps

1. Get `X-Trace-Id` from client or error response body `correlationId`
2. Search CloudWatch logs by that ID to see all log entries for the request
3. Check X-Ray console for latency breakdown and downstream failures

---

## 4. ERROR CLASSIFICATION

### Error Response Format

All errors follow the standard in `skills/patterns/error-response-format.md`:

```json
{
  "errorCode": "DIVISION_BY_ZERO",
  "message": "Cannot divide by zero",
  "correlationId": "Root=1-abc-def",
  "timestamp": "2026-03-30T10:00:00Z"
}
```

### Error Propagation Path

```
Domain (raises BusinessRuleError with error_code)
  → @observe (logs error + records metric with status=error)
  → Handler (no catch — passes through)
  → @api_gateway_handler (catches and maps to HTTP response)
    - ValidationError → 400 + VALIDATION_ERROR
    - BusinessRuleError → 400 + custom error_code
    - Unhandled → 500 + INTERNAL_ERROR
```

### Severity by Error Type

| Error Code | HTTP Status | Severity | Action |
|-----------|-------------|----------|--------|
| `VALIDATION_ERROR` | 400 | Low | Client issue — check request format |
| `DIVISION_BY_ZERO` | 400 | Low | Client issue — validate input |
| `INTERNAL_ERROR` | 500 | High | Investigate immediately — check logs for stack trace |

---

## 5. RESOLUTION ACTIONS

### Rollback Decision Tree

```
Is the issue caused by a recent deployment?
  YES → Rollback (Lambda version or CDK revert)
  NO  → Is it a config issue?
    YES → Fix config.json, redeploy
    NO  → Is it an AWS service issue?
      YES → Monitor AWS Health Dashboard, wait or failover
      NO  → Debug with logs/traces, fix code, deploy
```

### Rollback Commands

See `docs/runbooks/incident-workflow.md` for:
- Lambda version rollback
- CDK stack rollback
- Config rollback

---

## 6. METRICS REFERENCE

### Standard Metrics (via @observe decorator)

| Metric | Type | Namespace | Dimensions |
|--------|------|-----------|------------|
| `{operation}_total` | Counter | VirtualAssist | service.name, status |
| `{operation}_duration` | Histogram | VirtualAssist | service.name, status |

### Infrastructure Metrics (via CDK)

| Metric | Namespace | Dashboard Widget |
|--------|-----------|-----------------|
| Lambda Invocations | AWS/Lambda | Invocations graph |
| Lambda Errors | AWS/Lambda | Errors graph |
| Lambda Duration | AWS/Lambda | Duration p50/p95/p99 |
| API Gateway Count | AWS/ApiGateway | Request count |
| API Gateway Latency | AWS/ApiGateway | Latency p95 |
| API Gateway 4XXError | AWS/ApiGateway | 4xx rate |
| API Gateway 5XXError | AWS/ApiGateway | 5xx rate |

---

## 7. RUNBOOK CREATION STANDARD

When adding a new service, create a debug runbook in `docs/runbooks/{service}-debug.md` covering:

1. **Triage checklist** — dashboard link, alarm states, health check command
2. **Symptom-cause-fix table** — common failure patterns and resolutions
3. **CloudWatch Logs Insights queries** — pre-built queries for the service's log group
4. **Key log fields** — service-specific fields beyond the standard set

---

## 8. TOOLING

All incident scripts live in `scripts/incident/`:

| Script | Purpose |
|--------|---------|
| `download-logs.sh` | Pull CloudWatch logs + auto-summarize errors |
| `trace-lookup.sh` | Find request by correlation ID, trace ID, or request ID |
| `health-check.sh` | Validate all endpoints return expected responses |

Scripts accept `--stage` to target the right environment and auto-detect endpoints from CloudFormation.

---

## 9. SERVICE-SPECIFIC ADDENDA

Each AWS service has unique alarm definitions, failure patterns, Logs Insights queries, and decision trees. These live in focused addenda that extend this parent skill:

| Service | Addendum | Key Failure Modes |
|---------|----------|-------------------|
| Lambda | `incident-management-lambda.md` | Function errors, OOM, throttling, timeouts, cold starts |
| API Gateway | `incident-management-api-gateway.md` | 5xx/4xx spikes, latency, WAF blocks, integration timeouts |
| DynamoDB | `incident-management-dynamodb.md` | Throttling, hot partitions, GSI issues, stream lag |
| OpenSearch | `incident-management-opensearch.md` | Cluster health, disk/JVM pressure, indexing failures |
| EventBridge | `incident-management-eventbridge.md` | Failed invocations, DLQ depth, rule failures |

**How to use**: Start with this parent file for the general incident framework (detection, log structure, trace correlation, resolution process). Then open the relevant service addendum for service-specific alarm tables, classification patterns, diagnostic queries, and decision trees.
