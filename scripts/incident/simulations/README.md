# SRE Platform Simulation Framework

Automated test suite for the SRE incident management platform. Tests the full incident lifecycle from detection → triage → escalation through targeted leg tests and end-to-end scenarios.

## Quick Start

### Installation

```bash
# Install dependencies (OpenTelemetry for observability)
pip3 install -r requirements.txt

# Or with virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Running Tests

```bash
# Run leg tests (default, ~2.5 min)
python3 run.py

# Run e2e tests (~10 min)
python3 run.py --e2e

# Run everything (~12.5 min)
python3 run.py --all

# List available tests
python3 run.py --list
```

## Test Suites

### Leg Tests (Targeted Lambda Invocation)
Fast, isolated tests that invoke each Lambda directly:

- **L1: Detection** — SNS alarm → Detection Lambda → DDB record + Jira ticket (~45s)
- **L2: Triage** — IncidentCreated event → Triage Lambda → classification (~30s)
- **L3: Escalation** — EscalationRequired event → Escalation Lambda → Jira enrichment (~25s)
- **L4: Escalation Delta Report** — Checkpoint + reprocess → delta report (~30s)

### E2E Tests (Full AWS Infrastructure)
Complete workflows through live AWS services:

1. **Full Lifecycle** — ALARM → Jira → OK → resolve
2. **Duplicate Detection** — Same alarm twice → single incident
3. **Storm Detection** — Multiple alarms → storm flag
4. **Recovery Skip** — Already recovered alarm → skip processing
5. **Grace Period Escalation** — Recurrence within grace → escalate
6. **Happy Path E2E** — Detection → Triage → Escalation pipeline

## Configuration

Environment variables (all optional, defaults to `dev`):

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_REGION` | `us-west-2` | AWS region for resources |
| `AWS_ACCOUNT_ID` | `320644769527` | AWS account ID |
| `STAGE` | `dev` | Environment stage (dev/staging/prod) |
| `JIRA_BASE_URL` | `https://rameshnag2002.atlassian.net` | Jira instance URL |
| `TEST_SERVICE` | `calculator-api` | Service name for triage tests (must have logs) |

### Example: Run Against Staging

```bash
export STAGE=staging
export AWS_REGION=us-east-1
python3 run.py --legs
```

## Architecture

```
simulations/
├── lib/                    # Shared utilities
│   ├── config.py          # Environment configuration
│   ├── eventbridge.py     # Lambda invocation helpers
│   ├── dynamodb.py        # DDB test helpers
│   ├── cloudwatch.py      # Alarm management
│   ├── sns.py             # SNS publishing
│   ├── logs.py            # CloudWatch Logs helpers
│   ├── checkpoint.py      # Checkpoint table helpers
│   └── printer.py         # Test output formatting
├── scenarios/             # Test scenarios
│   ├── leg_*.py          # Leg tests (targeted)
│   └── *.py              # E2E tests
├── run.py                 # Test runner
└── cleanup.py             # Resource cleanup utility
```

## Running Specific Tests

```bash
# Specific leg tests
python3 run.py --leg L1 L4

# Specific e2e tests
python3 run.py --scenario 1 3 6

# Both in one run
python3 run.py --leg L2 --scenario 5
```

## Observability

The simulation framework uses **OpenTelemetry** for comprehensive observability, matching production Lambda patterns.

### Features

**✅ Distributed Tracing**
- Every Lambda invocation creates a trace span
- Test execution traces link to Lambda execution traces
- Trace IDs included in all log entries
- Export to CloudWatch X-Ray or OTLP endpoint

**✅ Structured JSON Logging**
- All logs in JSON format for easy querying
- Automatic trace ID correlation
- Entry/exit logging with duration
- Error logging with stack traces

**✅ Metrics**
- Lambda invocation success/failure counts
- Lambda invocation duration histograms
- Error categorization by type
- Export to CloudWatch Metrics

### Configuration

Observability is **disabled by default** for local development. Enable for debugging or CI/CD:

```bash
# Enable tracing (exports to OTLP endpoint)
export OTEL_TRACES_ENABLED=true
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

# Run tests with tracing
python3 run.py
```

### Log Format

All logs are structured JSON with trace context:

```json
{
  "level": "INFO",
  "timestamp": "2026-04-03T10:15:30.123Z",
  "trace_id": "5e8c9f2a4b1d3e6f7a8b9c0d1e2f3a4b",
  "operation": "invoke_lambda",
  "function": "_invoke_lambda_sync",
  "stage": "dev",
  "duration_ms": 1234,
  "message": "invoke_lambda completed successfully"
}
```

### Viewing Traces

Traces can be viewed in:
- **CloudWatch X-Ray**: Service map and trace timeline
- **CloudWatch Logs Insights**: Query by trace_id
- **Local OTLP collector**: Jaeger, Zipkin, etc.

### Decorator Pattern

The framework uses the `@observe` decorator (matching production Lambda pattern):

```python
from lib.observability import observe

@observe(operation="invoke_lambda", metric_prefix="lambda")
def invoke_lambda(function_name: str, event: dict) -> dict:
    # Automatically provides:
    # - Distributed tracing span
    # - Entry/exit structured logging
    # - Success/error metrics
    # - Duration tracking
    return result
```

## Cleanup

If tests fail and leave resources:

```bash
python3 cleanup.py
```

Removes all simulation alarms (prefix: `sim-`) and DDB records.

## Requirements

- Python 3.12+
- AWS credentials configured (`aws configure` or IAM role)
- Access to:
  - Lambda functions: `incident-detection-{STAGE}`, `incident-triage-{STAGE}`, `incident-escalation-{STAGE}`
  - DynamoDB tables: `incident-correlation-{STAGE}`, `sre-checkpoints-{STAGE}`
  - SNS topic: `incident-alarm-ingestion-{STAGE}`
  - CloudWatch Alarms and Logs
  - Jira API (via service credentials in Secrets Manager)

## Troubleshooting

### Lambda Not Found
```
RuntimeError: Lambda function 'incident-triage-dev' not found
```
**Fix:** Ensure the stage is deployed. Check `STAGE` environment variable matches deployment.

### Permission Denied
```
AccessDeniedException: User is not authorized to perform: lambda:InvokeFunction
```
**Fix:** Add IAM policy:
```json
{
  "Effect": "Allow",
  "Action": "lambda:InvokeFunction",
  "Resource": "arn:aws:lambda:*:*:function:incident-*"
}
```

### Test Service Has No Logs
```
Log group /aws/lambda/calculator-api-dev not found
```
**Fix:** Set `TEST_SERVICE` to a Lambda with recent logs, or invoke it once to create logs.

## Development

### Adding a New Leg Test

1. Create `scenarios/leg_new_test.py`:
```python
from lib import eventbridge, dynamodb, printer, config

NAME = "Leg X: Test Name"
INCIDENT_KEY = f"{config.SIM_PREFIX}-leg-newtest-{config.STAGE}"
TOTAL_STEPS = 5

def run() -> dict:
    """Run leg test. Returns dict with status."""
    printer.header(f"Leg Test: {NAME}")
    result = {"status": "passed"}
    
    # Test steps...
    
    return result
```

2. Register in `run.py`:
```python
from scenarios import leg_new_test

LEG_TESTS = {
    "L5": ("Leg 5: Test Name", leg_new_test),
}
```

### Adding a New E2E Test

1. Create `scenarios/new_scenario.py` following existing patterns
2. Register in `run.py`:
```python
E2E_TESTS = {
    7: ("New Scenario", new_scenario),
}
```

## CI/CD Integration

```yaml
# .github/workflows/test.yml
- name: Run Simulation Tests
  run: |
    cd scripts/incident/simulations
    python3 run.py --legs
  env:
    AWS_REGION: us-west-2
    STAGE: dev
```

## License

Internal use only. Part of VirtualAssist SRE platform.
