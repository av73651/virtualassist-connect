# Architecture Document - Hello World API

**Project**: Hello World Lambda API
**Version**: 1.0
**Date**: 2026-03-27

---

## 1. System Overview

**Purpose**: Simple REST API endpoint that returns a "Hello World" message to validate the complete AI-driven development lifecycle and infrastructure.

**Architecture Style**: Serverless-first, event-driven

**Key Components**:
- Amazon API Gateway (REST API)
- AWS Lambda (Python 3.12)
- AWS X-Ray (distributed tracing)
- Amazon CloudWatch (logs and metrics)

---

## 2. High-Level Architecture

```
┌──────────────┐
│   Internet   │
│  (API Client)│
└──────┬───────┘
       │ HTTPS
       │
       ▼
┌─────────────────────────┐
│   Amazon API Gateway    │
│   (REST API)            │
│   - /hello (GET)        │
│   - Request validation  │
│   - Throttling          │
└──────────┬──────────────┘
           │ Lambda Proxy Integration
           │
           ▼
┌─────────────────────────┐
│    AWS Lambda           │
│  hello-world-function   │
│  - Python 3.12          │
│  - ADOT Layer           │
│  - 512MB memory         │
└──────────┬──────────────┘
           │
           ├─────────────────────┐
           │                     │
           ▼                     ▼
    ┌────────────┐      ┌──────────────┐
    │ CloudWatch │      │   X-Ray      │
    │   Logs     │      │  Traces      │
    └────────────┘      └──────────────┘
```

---

## 3. Component Architecture

### 3.1 API Gateway

**Configuration**:
- **Type**: REST API
- **Stage**: dev
- **Endpoint Type**: Regional
- **Protocol**: HTTPS only

**Resources**:
```
/
└── /hello (GET)
    ├── Method Request: None required
    ├── Integration: Lambda Proxy
    ├── Method Response: 200, 500
    └── CORS: Enabled
```

**Throttling**:
- Burst limit: 1000 requests
- Rate limit: 500 requests/second

**Security**:
- HTTPS enforced
- No authentication (public endpoint for validation)
- Request validation enabled

---

### 3.2 Lambda Function

**Function Name**: `virtualassist-dev-hello-world`

**Configuration**:
- Runtime: Python 3.12
- Handler: `src.handlers.hello_handler.lambda_handler`
- Memory: 512 MB
- Timeout: 30 seconds
- Architecture: x86_64

**Layers**:
- AWS Distro for OpenTelemetry (ADOT) Lambda Layer
  - ARN: `arn:aws:lambda:us-east-1:901920570463:layer:aws-otel-python-amd64-ver-1-21-0:1`

**Environment Variables**:
```python
{
    "OTEL_SERVICE_NAME": "hello-world-function",
    "AWS_LAMBDA_EXEC_WRAPPER": "/opt/otel-instrument",
    "OTEL_PROPAGATORS": "tracecontext",
    "OTEL_PYTHON_LOG_CORRELATION": "true"
}
```

**Note**: Using pure OpenTelemetry via ADOT Lambda layer. No Lambda Powertools.

**IAM Role**:
```
- AWSLambdaBasicExecutionRole (CloudWatch Logs)
- AWSXRayDaemonWriteAccess (X-Ray tracing)
```

---

### 3.3 Observability Stack

**CloudWatch Logs**:
- Log Group: `/aws/lambda/virtualassist-dev-hello-world`
- Retention: 7 days (dev), 30 days (prod)
- Format: JSON structured logs

**X-Ray Tracing**:
- Active tracing enabled
- Trace all requests
- Subsegments for internal operations

**CloudWatch Metrics**:
- Standard Lambda metrics (Invocations, Duration, Errors, Throttles)
- Custom metrics:
  - `hello_world_requests` (count)
  - `hello_world_latency` (milliseconds)

**CloudWatch Dashboard**:
- Invocation count (5-minute intervals)
- Error rate (percentage)
- Duration p50, p95, p99
- Throttle count
- X-Ray service map embed

---

## 4. Data Flow

### Request Flow

```
1. Client → HTTPS GET /hello
   ↓
2. API Gateway
   - Validate request
   - Apply throttling
   - Forward to Lambda
   ↓
3. Lambda Handler
   - Extract trace context
   - Log request received
   - Call service layer
   ↓
4. Service Layer
   - Generate timestamp
   - Create response DTO
   ↓
5. Lambda Handler
   - Format HTTP response
   - Return 200 + JSON body
   ↓
6. API Gateway
   - Add CORS headers
   - Return to client
   ↓
7. Client ← HTTP 200
   {"message": "Hello, World!", "timestamp": "..."}
```

### Observability Flow

```
Request arrives
   ↓
X-Ray: Start trace segment
   ├─> API Gateway segment
   └─> Lambda segment
       ├─> Handler subsegment
       └─> Service subsegment
   ↓
CloudWatch Logs: Structured JSON
   - trace_id: xxx
   - level: INFO
   - message: Request received
   ↓
CloudWatch Metrics:
   - Increment hello_world_requests
   - Record hello_world_latency
```

---

## 5. Technology Stack

**Approved Technologies** (per technology-standards.md):

| Layer | Technology | Justification |
|-------|------------|---------------|
| Compute | AWS Lambda (Python 3.12) | Serverless, auto-scaling |
| API | API Gateway (REST) | Managed API service |
| Observability | OpenTelemetry + X-Ray | Native AWS tracing |
| Logging | CloudWatch Logs | Native AWS logging |
| Metrics | CloudWatch Metrics | Native AWS metrics |
| Infrastructure | AWS CDK (Python) | Infrastructure as code |

**No unapproved technologies used.** ✅

---

## 6. Security Architecture

### 6.1 Network Security
- **HTTPS Only**: API Gateway enforces TLS 1.2+
- **No VPC**: Lambda runs in AWS managed VPC (no custom VPC needed)
- **Public API**: No authentication required (validation endpoint)

### 6.2 IAM Security
- **Lambda Execution Role**: Least privilege
  - CloudWatch Logs: PutLogEvents only
  - X-Ray: PutTraceSegments only
  - No broad permissions (no wildcards)

### 6.3 Data Security
- **No PII**: Response contains no personally identifiable information
- **No Secrets**: No secrets in environment variables
- **No Storage**: No data persistence (stateless)

---

## 7. Scalability & Performance

### 7.1 Scalability
- **Lambda Concurrency**: Auto-scales to 1000 concurrent invocations
- **API Gateway**: Handles up to 10,000 req/sec (default limit)
- **No bottlenecks**: Stateless, no database

### 7.2 Performance Targets
- **p50 latency**: < 100ms
- **p95 latency**: < 200ms
- **p99 latency**: < 500ms
- **Cold start**: First invocation may take 500-1000ms (acceptable)

### 7.3 Performance Optimization
- Lambda memory: 512MB (optimal for Python)
- No provisioned concurrency (unnecessary for validation)
- No external API calls (minimize latency)

---

## 8. Error Handling

### Error Scenarios

| Error Type | HTTP Status | Error Code | Handling |
|------------|-------------|------------|----------|
| Lambda timeout | 500 | INTERNAL_ERROR | Return generic error, log details |
| Lambda crash | 500 | INTERNAL_ERROR | Return generic error, log stack trace |
| API Gateway throttle | 429 | TOO_MANY_REQUESTS | Built-in API Gateway response |
| Malformed request | 400 | BAD_REQUEST | API Gateway validation |

### Error Response Format

```json
{
  "errorCode": "INTERNAL_ERROR",
  "message": "An internal error occurred",
  "correlationId": "trace-id-here",
  "timestamp": "2026-03-27T10:00:00.000Z"
}
```

---

## 9. Deployment Architecture

### Environments

| Environment | Purpose | Configuration |
|-------------|---------|---------------|
| dev | Development testing | Full observability, 7-day log retention |
| staging | Pre-production validation | Full observability, 30-day log retention |
| prod | Production | Full observability, 90-day log retention |

### Deployment Strategy
- **Blue/Green**: Lambda aliases for zero-downtime
- **Rollback**: CDK stack rollback on failure
- **Testing**: Automated smoke tests post-deployment

---

## 10. Monitoring & Alerting

### Key Metrics to Monitor

1. **Invocation Count**: Track request volume
2. **Error Rate**: Alert if > 1%
3. **Duration p99**: Alert if > 500ms
4. **Throttle Count**: Alert if > 0

### CloudWatch Alarms

```
Alarm: HighErrorRate
  Metric: Errors
  Threshold: > 1% for 2 consecutive periods (5 min each)
  Action: SNS notification

Alarm: HighLatency
  Metric: Duration
  Statistic: p99
  Threshold: > 500ms for 2 consecutive periods
  Action: SNS notification
```

### Dashboards

**Hello World Dashboard**:
- Invocation count (last 1 hour, 24 hours)
- Error rate (percentage)
- Duration (p50, p95, p99)
- Throttle count
- X-Ray service map
- Sample logs (recent errors)

---

## 11. Cost Estimation

### Monthly Cost (Dev Environment)

| Service | Usage | Cost |
|---------|-------|------|
| Lambda | 100K invocations, 50ms avg | ~$0.20 |
| API Gateway | 100K requests | ~$0.35 |
| CloudWatch Logs | 1 GB ingestion | ~$0.50 |
| X-Ray | 100K traces | ~$0.50 |
| **Total** | | **~$1.55/month** |

**Production costs**: Scale linearly with traffic.

---

## 12. Disaster Recovery

### RTO/RPO
- **RTO (Recovery Time Objective)**: < 5 minutes
- **RPO (Recovery Point Objective)**: 0 (stateless, no data loss)

### Recovery Procedures
1. **Lambda Failure**: Auto-retry (built-in)
2. **Region Failure**: Redeploy to secondary region (manual)
3. **Configuration Error**: Rollback CDK stack

### Backup & Restore
- **No backup needed**: Stateless function, no data
- **Code backup**: Git repository
- **Infrastructure backup**: CDK code in Git

---

## 13. Compliance & Governance

### AWS Best Practices
- ✅ Least privilege IAM
- ✅ Encryption in transit (HTTPS)
- ✅ Logging and monitoring enabled
- ✅ Infrastructure as code (CDK)
- ✅ No hardcoded credentials

### Tagging Strategy
```
Environment: dev | staging | prod
Project: hello-world-api
ManagedBy: cdk
CostCenter: development
Owner: platform-team
```

---

## 14. Design Decisions & Trade-offs

### Decision 1: No Database
**Rationale**: Hello world doesn't need persistence, keeps architecture simple
**Trade-off**: Can't track historical requests (acceptable for validation)

### Decision 2: Public API (No Auth)
**Rationale**: Validation endpoint, simplifies testing
**Trade-off**: Anyone can call it (acceptable for dev, remove for prod)
**Mitigation**: API Gateway throttling prevents abuse

### Decision 3: 512MB Memory
**Rationale**: Optimal for Python runtime, not memory-intensive
**Trade-off**: Slightly higher cost than 128MB (negligible $0.05/month)

### Decision 4: No Provisioned Concurrency
**Rationale**: Cold starts acceptable for validation endpoint
**Trade-off**: First invocation slower (~500ms vs 100ms)
**Mitigation**: Can add later if needed

---

## 15. Future Enhancements (Out of Scope for v1)

- [ ] Add Cognito authentication
- [ ] Add DynamoDB for request logging
- [ ] Add API versioning (/v1/hello)
- [ ] Add more endpoints (POST, PUT, DELETE)
- [ ] Add request/response caching (API Gateway cache)
- [ ] Multi-region deployment
- [ ] Custom domain name (api.example.com)
- [ ] WAF for DDoS protection

---

## Diagrams

### Sequence Diagram

```
Client          API Gateway        Lambda           CloudWatch       X-Ray
  │                 │                 │                 │              │
  ├─GET /hello─────>│                 │                 │              │
  │                 ├─Start Trace────>│                 │              ├─Trace Start
  │                 ├─Invoke─────────>│                 │              │
  │                 │                 ├─Log Request────>│              │
  │                 │                 ├─Subsegment─────>│              ├─Subsegment
  │                 │                 ├─Generate Response              │
  │                 │                 ├─Log Response───>│              │
  │                 │<──200 + JSON────┤                 │              │
  │<──200 + JSON────┤                 │                 │              ├─Trace End
  │                 │                 │                 │              │
```

---

## Architecture Compliance

✅ **Technology Standards**: All approved technologies used
✅ **Serverless-First**: Lambda + API Gateway
✅ **Observability**: OpenTelemetry + CloudWatch + X-Ray
✅ **Security**: HTTPS, IAM least privilege, no secrets
✅ **Infrastructure as Code**: AWS CDK
✅ **Scalability**: Auto-scaling Lambda
✅ **Monitoring**: CloudWatch dashboards and alarms

**Ready for implementation plan.**
