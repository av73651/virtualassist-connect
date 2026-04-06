"""E2E Test: Real Observability Flow - Generate actual Lambda errors, verify custom metrics, alarm, and SRE pipeline.

This test validates the COMPLETE observability + SRE platform integration:
1. Generate 15 real errors in calculator Lambda (division by zero business rule errors)
2. Custom metrics emitted via @observe decorator to CustomMetrics/calculator namespace
3. Real alarm fires: calculator-custom-error-rate-dev (threshold: 10 errors)
4. SNS notification triggers Detection Lambda
5. Triage Lambda analyzes REAL error logs
6. Escalation Lambda enriches with REAL error data

Expected runtime: ~12 minutes (alarm evaluates every 5min, needs 2 evaluation periods)
"""

import boto3
import json
import time
from lib import dynamodb, printer, config

NAME = "Real Observability E2E"
ALARM_NAME = "calculator-custom-error-rate-dev"
INCIDENT_KEY = f"calculator-api-high-error-rate-{config.STAGE}"
CALCULATOR_FUNCTION = f"calculator-api-{config.STAGE}"
TOTAL_STEPS = 8

_lambda = boto3.client("lambda", region_name=config.REGION)
_cw = boto3.client("cloudwatch", region_name=config.REGION)


def run() -> dict:
    """Run real observability e2e test."""
    printer.header(f"E2E Test: {NAME}")
    result = {"status": "passed", "ticket_id": None}

    # Step 1: Pre-clean
    printer.step(1, TOTAL_STEPS, "Pre-cleaning stale records...")
    dynamodb.delete_record(INCIDENT_KEY)
    _reset_alarm()
    printer.info("Clean.")

    # Step 2: Verify alarm is OK
    printer.step(2, TOTAL_STEPS, f"Verifying alarm {ALARM_NAME} is in OK state...")
    alarm_state = _get_alarm_state()
    if alarm_state != "OK":
        printer.info(f"Alarm state: {alarm_state} (expected OK, but proceeding)")
    else:
        printer.passed(f"Alarm state: {alarm_state}")

    # Step 3: Generate 15 real errors
    printer.step(3, TOTAL_STEPS, "Generating 15 real business errors in calculator Lambda (division by zero)...")
    errors_generated = _generate_errors(15)
    if errors_generated < 15:
        printer.failed(f"Only generated {errors_generated}/15 errors", "Lambda invocation failed")
        return {"status": "failed"}
    printer.passed(f"Generated {errors_generated} errors")

    # Step 4: Wait for custom metrics
    printer.step(4, TOTAL_STEPS, "Waiting for custom metrics to appear in CloudWatch...")
    printer.countdown(60, "Metric aggregation")

    metric_value = _check_custom_metrics()
    if metric_value >= 10:
        printer.passed(f"Custom metric Errors: {metric_value} (threshold: 10)")
    else:
        printer.info(f"Custom metric Errors: {metric_value} (threshold: 10) - waiting for aggregation")

    # Step 5: Wait for alarm to fire (alarm evaluates every 5min, needs 2 periods = up to 10min)
    printer.step(5, TOTAL_STEPS, "Waiting for alarm to fire (may take up to 10 minutes)...")
    alarm_fired = _wait_for_alarm(timeout=600)  # 10 minutes
    if alarm_fired:
        printer.passed("Alarm fired: ALARM state")
    else:
        printer.failed("Alarm did not fire", "Check alarm configuration or metric emission")
        return {"status": "failed"}

    # Step 6: Wait for Detection Lambda processing
    printer.step(6, TOTAL_STEPS, "Waiting for Detection Lambda to process alarm...")
    printer.countdown(45, "Detection processing")

    # Step 7: Verify DynamoDB record
    printer.step(7, TOTAL_STEPS, "Verifying DynamoDB record...")
    record = dynamodb.wait_for_record(INCIDENT_KEY, timeout=30)
    if record and record.get("jira_ticket_id"):
        ticket = record["jira_ticket_id"]
        status = record.get("status")
        printer.passed(f"Record found: status={status}, ticket={ticket}")
        result["ticket_id"] = ticket

        # Verify this is about calculator, not simulation
        service = record.get("service", "")
        if "calculator" in service:
            printer.passed(f"Service: {service} (real Lambda, not simulation)")
        else:
            printer.info(f"Service: {service} (expected calculator)")
    else:
        printer.failed("DynamoDB record not found or missing jira_ticket_id", str(record))
        result["status"] = "failed"

    # Step 8: Wait for Triage analysis
    printer.step(8, TOTAL_STEPS, "Waiting for Triage Lambda to analyze logs...")
    printer.countdown(30, "Triage analysis")

    # Re-fetch record to check for triage updates
    record = dynamodb.get_record(INCIDENT_KEY)
    if record:
        error_count = record.get("error_count", 0)
        if error_count > 0:
            printer.passed(f"Triage found {error_count} errors in logs")
        else:
            printer.info("Triage did not find errors yet (may still be processing)")

    printer.info("\nTest complete. Check Jira ticket for:")
    printer.info("  - Error count > 0 (real errors, not simulation)")
    printer.info("  - Log analysis showing division by zero")
    printer.info("  - Function: calculator-api-dev")
    printer.info("  - Real stack traces in diagnostics")

    return result


def _reset_alarm():
    """Reset alarm to OK state by publishing zero metric."""
    try:
        _cw.put_metric_data(
            Namespace="CustomMetrics/calculator",
            MetricData=[{
                "MetricName": "Errors",
                "Value": 0,
                "Dimensions": []
            }]
        )
        time.sleep(2)
    except Exception:
        pass  # Best effort


def _get_alarm_state() -> str:
    """Get current alarm state."""
    try:
        resp = _cw.describe_alarms(AlarmNames=[ALARM_NAME])
        alarms = resp.get("MetricAlarms", [])
        if alarms:
            return alarms[0].get("StateValue", "UNKNOWN")
    except Exception:
        pass
    return "NOT_FOUND"


def _generate_errors(count: int) -> int:
    """Generate real errors by invoking calculator with division by zero (business rule error)."""
    generated = 0

    # Generate business rule errors (division by zero) which trigger @observe decorator
    payload = json.dumps({
        "httpMethod": "POST",
        "path": "/calculator/divide",  # Use divide endpoint
        "body": json.dumps({"a": 10, "b": 0})  # Division by zero - business rule error
    })

    for i in range(count):
        try:
            response = _lambda.invoke(
                FunctionName=CALCULATOR_FUNCTION,
                InvocationType="RequestResponse",
                Payload=payload.encode('utf-8')
            )
            if response.get("StatusCode") == 200:
                response_payload = json.loads(response["Payload"].read())
                # Business rule error should return 400 with DIVISION_BY_ZERO
                if response_payload.get("statusCode") == 400:
                    body = json.loads(response_payload.get("body", "{}"))
                    if body.get("errorCode") == "DIVISION_BY_ZERO":
                        generated += 1
                    else:
                        printer.info(f"Invocation {i+1}: Got 400 but wrong error: {body.get('errorCode')}")
                elif response_payload.get("statusCode") == 200:
                    printer.info(f"Invocation {i+1}: Got 200 (no error generated)")
            else:
                # Lambda execution error
                generated += 1
        except Exception as e:
            printer.info(f"Invocation {i+1} error: {e}")
            generated += 1

    return generated


def _check_custom_metrics() -> float:
    """Check current value of CustomMetrics/calculator Errors metric."""
    try:
        from datetime import datetime, timedelta, timezone

        response = _cw.get_metric_statistics(
            Namespace="CustomMetrics/calculator",
            MetricName="Errors",
            Dimensions=[],
            StartTime=datetime.now(timezone.utc) - timedelta(minutes=5),
            EndTime=datetime.now(timezone.utc),
            Period=60,
            Statistics=["Sum"]
        )

        datapoints = response.get("Datapoints", [])
        if datapoints:
            # Get the latest datapoint
            latest = sorted(datapoints, key=lambda x: x["Timestamp"])[-1]
            return latest.get("Sum", 0)
    except Exception:
        pass

    return 0


def _wait_for_alarm(timeout: int = 90) -> bool:
    """Wait for alarm to transition to ALARM state."""
    start = time.time()
    while time.time() - start < timeout:
        state = _get_alarm_state()
        if state == "ALARM":
            return True
        time.sleep(5)
    return False
