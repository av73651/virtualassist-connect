# Real Error Generation for Integration Tests

## Problem

Current simulations use **synthetic alarms** that don't generate real Lambda errors, logs, or metrics. This limits test coverage:

- ❌ No real error logs for log analysis service to parse
- ❌ No real CloudWatch metrics
- ❌ No real blast radius signals
- ❌ Log analysis always returns empty results
- ❌ Can't test root cause classification with real data

**Current**: CloudWatch Alarm API → SNS → Detection Lambda (processes alarm metadata only)
**Needed**: Real Lambda errors → Real logs/metrics → Real alarm → SNS → Full pipeline

---

## Solution: Test Error Generator Lambda

Create a dedicated Lambda that throws errors on demand for testing.

### Architecture

```
Simulation Test
    ↓
Invoke test-error-generator-{stage} Lambda
    → Throws configurable error type
    → Writes structured logs
    → Increments error metrics
    ↓
CloudWatch Logs + Metrics populated
    ↓
CloudWatch Alarm triggers (real threshold breach)
    ↓
SNS → Detection → Triage → Escalation
    → Log analysis parses REAL error logs
    → Blast radius calculated from REAL metrics
    → Classification uses REAL error patterns
```

---

## Implementation

### 1. Test Error Generator Lambda

**Location**: `backend/lambdas/test-error-generator/`

```python
# src/handler.py
import logging
import random
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ERROR_TYPES = {
    "division_by_zero": lambda: 1 / 0,
    "null_pointer": lambda: None.some_method(),
    "timeout": lambda: time.sleep(10),  # Exceeds Lambda timeout
    "memory_exhaustion": lambda: [0] * (10**9),  # OOM
    "api_error": lambda: requests.get("http://nonexistent.invalid"),
    "database_error": lambda: pymongo.MongoClient("mongodb://invalid:27017").test.test.find_one(),
}

def lambda_handler(event, context):
    error_type = event.get("error_type", "division_by_zero")
    error_count = event.get("error_count", 10)
    
    logger.info(f"Generating {error_count} errors of type: {error_type}")
    
    for i in range(error_count):
        try:
            ERROR_TYPES[error_type]()
        except Exception as e:
            logger.error(f"Error {i+1}/{error_count}: {type(e).__name__}: {str(e)}", 
                        exc_info=True)
    
    return {
        "statusCode": 500,
        "body": f"Generated {error_count} {error_type} errors"
    }
```

### 2. CDK Infrastructure

```python
# infra/stacks/test_infrastructure_stack.py (new)

error_generator = lambda_.Function(
    self, "TestErrorGenerator",
    function_name=f"test-error-generator-{stage}",
    runtime=lambda_.Runtime.PYTHON_3_12,
    handler="src.handler.lambda_handler",
    code=lambda_.Code.from_asset("backend/lambdas/test-error-generator"),
    timeout=Duration.seconds(60),
    memory_size=512,
    tracing=lambda_.Tracing.ACTIVE,
)

# Alarm for error rate
error_alarm = cloudwatch.Alarm(
    self, "TestErrorGeneratorAlarm",
    alarm_name=f"test-error-generator-high-error-rate-{stage}",
    metric=error_generator.metric_errors(),
    threshold=5,
    evaluation_periods=1,
    comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
)

# Subscribe to SNS
error_alarm.add_alarm_action(
    cw_actions.SnsAction(sns_topic)  # incident-alarm-ingestion-{stage}
)
```

### 3. Updated Simulation Flow

```python
# scenarios/leg_detection.py

def run() -> dict:
    printer.header(f"Leg Test 1: {NAME}")
    result = {"status": "passed"}

    # Step 1: Pre-clean
    printer.step(1, TOTAL_STEPS, "Pre-cleaning stale records...")
    dynamodb.delete_record(INCIDENT_KEY)
    printer.info("Clean.")

    # Step 2: Generate REAL errors via test Lambda
    printer.step(2, TOTAL_STEPS, "Generating real Lambda errors...")
    error_event = {
        "error_type": "division_by_zero",
        "error_count": 10,
    }
    lambda_client.invoke(
        FunctionName=f"test-error-generator-{config.STAGE}",
        InvocationType="RequestResponse",
        Payload=json.dumps(error_event),
    )
    printer.info(f"Generated 10 errors in test-error-generator-{config.STAGE}")

    # Step 3: Wait for logs to populate and alarm to trigger
    printer.step(3, TOTAL_STEPS, "Waiting for logs and alarm to trigger...")
    printer.countdown(60, "Logs + Alarm propagation")

    # Step 4: Verify alarm state
    printer.step(4, TOTAL_STEPS, "Verifying alarm state...")
    alarm_name = f"test-error-generator-high-error-rate-{config.STAGE}"
    state = cloudwatch.get_state(alarm_name)
    if state == "ALARM":
        printer.passed(f"Alarm state: {state}")
    else:
        printer.failed(f"Alarm state: {state}", "Expected ALARM")
        return {"status": "failed"}

    # Step 5: Verify Detection Lambda processed the REAL alarm
    printer.step(5, TOTAL_STEPS, "Verifying DynamoDB record...")
    incident_key = f"test-error-generator-error-rate-{config.STAGE}"
    record = dynamodb.wait_for_record(incident_key, timeout=30)
    
    if record and record.get("status") == "DETECTED":
        printer.passed(f"Record found: status=DETECTED")
    else:
        printer.failed("Detection failed or incomplete", str(record))
        result["status"] = "failed"

    # Step 6: Verify Triage analyzed REAL logs
    printer.step(6, TOTAL_STEPS, "Checking Jira for log analysis...")
    # Read Jira ticket comments to verify log analysis ran
    # Should contain actual error patterns from CloudWatch Logs

    return result
```

---

## Benefits

✅ **Real Observability Data**: Tests process actual logs, metrics, and alarms
✅ **Log Analysis Coverage**: LogAnalysisService parses real error patterns
✅ **Blast Radius Validation**: Metrics show real error counts and rates
✅ **Classification Accuracy**: AI service sees real error signatures
✅ **End-to-End Realism**: Full production-like data flow

---

## Tradeoffs

**Pros**:
- Much more realistic integration tests
- Validates log parsing and classification logic
- Tests alarm threshold tuning
- Exposes issues that synthetic alarms miss

**Cons**:
- Longer test execution (~60s for log propagation)
- Requires deploying test Lambda to all environments
- Additional infrastructure to maintain
- Test Lambda errors appear in CloudWatch metrics (might confuse)

---

## Implementation Plan

### Phase 1: Core Infrastructure
1. Create `test-error-generator` Lambda
2. Add CDK stack for test infrastructure
3. Deploy to dev environment
4. Validate error generation manually

### Phase 2: Update Leg Tests
1. Update L1 (Detection) to use real errors
2. Update L2 (Triage) to invoke real error Lambda first
3. Adjust timeouts for log propagation

### Phase 3: Error Type Coverage
1. Add error types for each classification category:
   - `bad-deployment` → deployment marker + errors
   - `downstream-timeout` → timeout exceptions
   - `permission-denied` → IAM errors
   - `resource-exhausted` → memory/throttling errors

### Phase 4: E2E Tests
1. Update e2e tests to use real errors
2. Validate full pipeline with real data

---

## Alternative: Hybrid Approach

Keep synthetic alarms for **connectivity tests** (L1-L4 legs), add real error tests separately:

```
Leg Tests (current):
  L1-L4: Synthetic alarms → test pipeline connectivity

Real Error Tests (new):
  R1: Real Lambda errors → Full Detection → Verify log analysis
  R2: Real Lambda errors → Full Triage → Verify classification
  R3: Real Lambda errors → Full Escalation → Verify enrichment
```

This avoids slowing down fast leg tests while adding deeper integration coverage.

---

## Decision

**Recommendation**: Hybrid approach
- Keep fast leg tests (synthetic alarms, ~2.5 min)
- Add new real error test suite (real errors, ~8-10 min)
- Run leg tests in CI/CD for every PR
- Run real error tests nightly or pre-release

**Next Steps**:
1. Review and approve design
2. Implement test-error-generator Lambda
3. Deploy to dev
4. Create R1-R3 real error test scenarios
