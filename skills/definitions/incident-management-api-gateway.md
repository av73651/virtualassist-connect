# Incident Management — API Gateway (Addendum)

> Extends `incident-management.md`. Covers API Gateway-specific alarms, failure patterns, queries, and decision trees.

---

## ALARM DEFINITIONS

| Alarm Type | Metric / Namespace | Statistic | Direction | Threshold | Period |
|-----------|-------------------|-----------|-----------|-----------|--------|
| `5xx-error-rate` | 5XXError — AWS/ApiGateway | Average | high | 1% | 60s × 3 |
| `4xx-error-rate` | 4XXError — AWS/ApiGateway | Average | high | 10% | 60s × 5 |
| `latency-p99` | Latency — AWS/ApiGateway | p99 | high | 5000ms | 60s × 3 |
| `integration-latency` | IntegrationLatency — AWS/ApiGateway | p99 | high | 4000ms | 60s × 3 |
| `count-traffic` | Count — AWS/ApiGateway | Sum | low | 50% below baseline | 300s × 3 |
| `waf-blocked` | BlockedRequests — AWS/WAFV2 | Sum | high | 100 | 300s × 2 |

### Key Metric Distinction

```
Total Latency = API Gateway Overhead + Integration Latency

IntegrationLatency ≈ Latency  → problem is in backend Lambda
IntegrationLatency << Latency → problem is in API Gateway layer (authorizer, WAF, mapping)
```

---

## FAILURE MODE CLASSIFICATION

| Pattern | Indicators | Classification | Confidence |
|---------|-----------|---------------|------------|
| Backend Lambda failure | 5xx spike + Lambda error-rate alarm also firing | `backend-lambda-error` | high |
| Integration timeout | 5xx + IntegrationLatency near 29s | `integration-timeout` | high |
| Stage throttling | 429 spike + Count near stage limit (10k RPS) | `api-throttle` | high |
| WAF false positive | 403 spike + WAF BlockedRequests spike | `waf-misconfiguration` | medium |
| Auth failure | 401/403 spike, no WAF blocks | `auth-issue` | high |
| Route missing | 404 spike after deployment | `bad-deployment` | medium |
| Client error spike | 400 spike, no backend errors | `client-error-spike` | low |

---

## LOGS INSIGHTS QUERIES

Requires API Gateway access logging enabled. Log group: `API-Gateway-Execution-Logs_{api-id}/{stage}`.

**Error breakdown by path:**
```
fields @timestamp, status, httpMethod, resourcePath, responseLatency, ip
| filter status >= 400
| stats count() as errors by status, httpMethod, resourcePath
| sort errors desc | limit 20
```

**Latency by endpoint:**
```
fields resourcePath, responseLatency, integrationLatency
| stats avg(responseLatency) as avg_total, avg(integrationLatency) as avg_backend,
        pct(responseLatency, 99) as p99_total, pct(integrationLatency, 99) as p99_backend
        by resourcePath
| sort p99_total desc
```

**Throttled requests (429):**
```
fields @timestamp, status, resourcePath, ip
| filter status = 429
| stats count() as throttled by resourcePath, ip
| sort throttled desc | limit 20
```

**Top callers (traffic anomaly):**
```
fields ip, httpMethod, resourcePath
| stats count() as requests by ip
| sort requests desc | limit 20
```

---

## DECISION TREE

```
ALARM FIRES
│
├─ 5xx-error-rate
│   ├─ Lambda error-rate alarm also firing? → BACKEND → see Lambda addendum
│   ├─ IntegrationLatency near 29s? → INTEGRATION TIMEOUT → check Lambda duration → ESCALATE
│   ├─ 502 "Bad Gateway"? → INVALID RESPONSE FORMAT → fix Lambda response → ESCALATE
│   └─ No Lambda invocations? → MAPPING TEMPLATE ERROR → ESCALATE
│
├─ 4xx-error-rate
│   ├─ Mostly 429? → THROTTLING → check stage/usage plan limits → ESCALATE
│   ├─ Mostly 403 + WAF? → WAF FALSE POSITIVE → review rules → ESCALATE
│   ├─ Mostly 401? → AUTH ISSUE → check Cognito authorizer → ESCALATE
│   ├─ Mostly 404 after deploy? → ROUTE MISSING → redeploy stage → ESCALATE
│   └─ Mostly 400? → CLIENT ERRORS → monitor, low severity
│
├─ latency-p99
│   ├─ IntegrationLatency also high? → BACKEND → see Lambda addendum
│   └─ IntegrationLatency normal? → API GW OVERHEAD → check authorizer caching → ESCALATE
│
├─ count-traffic (low) → check DNS/Route 53, upstream routing → ESCALATE
│
└─ waf-blocked → legitimate traffic? → adjust rules (MANUAL) or monitor
```

---

## REMEDIATION ACTIONS

| Classification | Action | Auto | Trigger | Verify |
|---------------|--------|------|---------|--------|
| `backend-lambda-error` | Delegate to Lambda addendum | AUTO (via Lambda) | 5xx spike + Lambda error-rate alarm also firing | 5xx rate drops to 0%, Lambda alarm returns to OK |
| `integration-timeout` | Delegate to Lambda addendum (duration) | AUTO (via Lambda) | 5xx + IntegrationLatency near 29s hard limit | IntegrationLatency p99 < 10s, no 504 errors |
| `api-throttle` | Increase stage/usage plan limits | MANUAL | 429 spike + request Count near stage limit (10k RPS default) | 429 rate drops to 0%, Count within new limit |
| `waf-misconfiguration` | Update WAF rule set | MANUAL | 403 spike + WAF BlockedRequests spike on legitimate traffic | BlockedRequests drops, legitimate 200 responses resume |
| `auth-issue` | Check Cognito pool, token TTL | MANUAL | 401/403 spike, no WAF blocks; Cognito authorizer errors | Auth errors drop to 0%, successful authentications resume |
| `bad-deployment` | Redeploy previous stage | MANUAL | 404 spike after deployment; routes missing from stage | 404 rate drops to baseline, all routes respond correctly |

Most API Gateway issues require manual remediation due to configuration/security implications.

---

## SERVICE-SPECIFIC GOTCHAS

**29s hard timeout**: API Gateway REST APIs have a non-configurable 29-second integration timeout. Lambda must complete within this window or the client gets 504 while Lambda continues running.

**Stage deployment required**: Resource changes (routes, methods, models) require explicit stage deployment. Without it, the old configuration continues serving traffic — new routes return 404.

**Throttling hierarchy**: Account (10k RPS) → Stage → Usage Plan → Method. Check broadest to narrowest. All levels return 429.

**Authorizer caching**: Default 300s TTL. Too short adds latency (every request hits Cognito). Too long keeps revoked tokens valid.
