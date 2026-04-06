# Calculator API — Debug Runbook

## Quick Triage Checklist

1. Open dashboard: `calculator-api-dashboard-{stage}` in CloudWatch
2. Check alarm states: error rate, latency, 4xx
3. Run health check: `./scripts/incident/health-check.sh --stage <stage>`
4. Pull logs: `./scripts/incident/download-logs.sh --stage <stage> --minutes 15`

---

## Symptom → Cause → Fix

| Symptom | Likely Cause | Investigation | Fix |
|---------|-------------|---------------|-----|
| All endpoints return 5xx | Lambda crash, bad deploy | Download logs, check for ImportError/SyntaxError | Rollback Lambda version |
| Single operation 5xx (e.g. /divide) | Bug in operation handler | `download-logs.sh` filtered by path | Fix code, redeploy |
| High 4xx on /divide | Clients sending b=0 | Check logs for `DIVISION_BY_ZERO` | Client-side — notify consumers |
| High 4xx across all ops | Bad client payload format | Check logs for `VALIDATION_ERROR` | Client-side — check API contract |
| Slow responses (p99 > 500ms) | Cold starts or memory | Check Lambda duration + init duration | Increase memory or add provisioned concurrency |
| 401/403 errors | Auth misconfiguration | Check Cognito authorizer, token validity | Verify user pool, recheck authorizer |
| 429 Too Many Requests | Rate limit hit | Check API Gateway throttle metrics | Raise limits in config.json or WAF |
| Intermittent timeouts | Lambda timeout too low | Check `duration_ms` in logs vs timeout config | Increase `timeout_seconds` in config.json |

---

## CloudWatch Logs Insights Queries

**Log group**: `/aws/lambda/calculator-api-{stage}`

### All Errors in Last Hour
```
fields @timestamp, @message
| filter level = "ERROR"
| sort @timestamp desc
| limit 50
```

### Errors by Type
```
fields error_type, error
| filter level = "ERROR"
| stats count(*) as error_count by error_type, error
| sort error_count desc
```

### Errors by Operation
```
fields operation, error_type
| filter level = "ERROR"
| stats count(*) as count by operation, error_type
| sort count desc
```

### Slow Requests (> 200ms)
```
fields @timestamp, operation, duration_ms
| filter duration_ms > 200
| sort duration_ms desc
| limit 20
```

### Find Request by Trace ID
```
fields @timestamp, @message
| filter trace_id = "YOUR_TRACE_ID_HERE"
| sort @timestamp asc
```

### Request Volume by Operation
```
fields operation
| filter message like /Starting/
| stats count(*) as requests by operation
| sort requests desc
```

### Errors for a Specific User
```
fields @timestamp, path, error_type, error, request_body
| filter level in ["ERROR", "WARNING"] and user_id = "USER_ID_HERE"
| sort @timestamp desc
| limit 20
```

### Affected Users Count
```
fields user_id
| filter level in ["ERROR", "WARNING"]
| stats count(*) as errors by user_id
| sort errors desc
| limit 20
```

### Cold Start Impact
```
filter @type = "REPORT"
| fields @duration, @initDuration, @memorySize, @maxMemoryUsed
| filter @initDuration > 0
| stats count(*) as cold_starts, avg(@initDuration) as avg_init_ms, max(@initDuration) as max_init_ms
```

### Error Rate Over Time (5-min buckets)
```
fields @timestamp
| stats count(*) as total,
        sum(level = "ERROR") as errors
        by bin(5m) as time_bucket
| sort time_bucket desc
```

### Division by Zero Frequency
```
fields @timestamp, trace_id
| filter error_type = "DivisionByZeroError"
| stats count(*) as count by bin(1h)
| sort count desc
```

---

## Trace Investigation

When a customer reports a failed request:

1. Get the `X-Trace-Id` from the response header (or correlation ID from error response)
2. Look up the full request lifecycle:

```bash
# Find all log entries for a specific request
./scripts/incident/trace-lookup.sh --stage prod --correlation-id <trace-id>
```

3. In X-Ray console: search by trace ID to see the full service map and latency breakdown

---

## Key Log Fields Reference

| Field | Source | Example | When |
|-------|--------|---------|------|
| `trace_id` | API Gateway middleware | `Root=1-abc-def` | Always |
| `request_id` | Lambda context | `12345-abcde` | Always |
| `user_id` | Cognito JWT `sub` claim | `a1b2c3-uuid` | Always |
| `http_method` | API Gateway event | `POST` | Always |
| `path` | API Gateway event | `/calculator/divide` | Always |
| `request_body` | API Gateway event | `{"a":10,"b":0}` | On error |
| `operation` | @observe decorator | `divide_numbers` | Always |
| `service` | @observe decorator | `CalculatorService` | Always |
| `status` | @observe decorator | `success` / `error` | Always |
| `duration_ms` | @observe decorator | `12.34` | Always |
| `error_type` | Exception class | `DivisionByZeroError` | On error |
| `error` | Exception message | `Cannot divide by zero` | On error |
| `errorCode` | HTTP error response | `DIVISION_BY_ZERO` | On error |
| `correlationId` | HTTP error response | `Root=1-abc-def` | On error |
