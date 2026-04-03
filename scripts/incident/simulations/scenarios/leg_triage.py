"""Leg Test 2: Triage — inject IncidentCreated event → Triage Lambda → classification + escalation/resolution.

Tests Leg 2 in isolation by invoking Triage Lambda directly.
Expected runtime: ~30s."""

from lib import eventbridge, dynamodb, printer, config

NAME = "Leg 2: Triage"
INCIDENT_KEY = f"{config.SIM_PREFIX}-leg-triage-{config.STAGE}"
TOTAL_STEPS = 5


def run() -> dict:
    """Run leg 2 test. Returns dict with status."""
    printer.header(f"Leg Test 2: {NAME}")
    result = {"status": "passed"}

    # Step 1: Pre-clean DynamoDB
    printer.step(1, TOTAL_STEPS, "Pre-cleaning stale records...")
    dynamodb.delete_record(INCIDENT_KEY)
    printer.info("Clean.")

    # Step 2: Create DDB record with DETECTED status + Jira ticket
    printer.step(2, TOTAL_STEPS, "Injecting DETECTED record with Jira ticket...")
    test_ticket_id = f"ASD-{config.STAGE.upper()}-LEG2"
    dynamodb.put_record({
        "incident_key": INCIDENT_KEY,
        "status": "DETECTED",
        "jira_ticket_id": test_ticket_id,
        "severity": "SEV-1",
        "created_at": "2026-04-03T12:00:00Z",
        "ttl": config.TEST_TTL_NEVER_EXPIRE,
    })
    printer.info(f"Record created: {INCIDENT_KEY} → {test_ticket_id}")

    # Step 3: Build IncidentCreated event and invoke Triage Lambda
    printer.step(3, TOTAL_STEPS, "Invoking Triage Lambda with IncidentCreated event...")
    event = eventbridge.build_incident_created_event(
        incident_key=INCIDENT_KEY,
        jira_ticket_id=test_ticket_id,
        service=config.TEST_SERVICE,
        stage=config.STAGE,
        severity="SEV-1",
        recovery_model="stateless",
        service_type="lambda",
        function_name=f"{config.TEST_SERVICE}-{config.STAGE}",
        metric_name="Errors",
        storm_detected=False,
    )

    try:
        response = eventbridge.invoke_triage(event)
        printer.info(f"Triage response: {response}")
    except Exception as e:
        printer.failed("Triage Lambda invocation failed", str(e))
        _cleanup()
        return {"status": "failed"}

    # Step 4: Verify response status
    printer.step(4, TOTAL_STEPS, "Verifying response status...")
    response_status = response.get("status", "")
    if response_status in ["auto-resolved", "escalated"]:
        printer.passed(f"Response status: {response_status}")
    else:
        printer.failed(f"Unexpected response status: {response_status}", "Expected auto-resolved or escalated")
        result["status"] = "failed"

    # Step 5: Verify DynamoDB status transition
    printer.step(5, TOTAL_STEPS, "Verifying DynamoDB status transition...")
    record = dynamodb.get_record(INCIDENT_KEY)
    if record:
        ddb_status = record.get("status", "")
        if ddb_status in ["GRACE", "ESCALATED"]:
            printer.passed(f"DDB status transitioned: {ddb_status}")
        else:
            printer.failed(f"DDB status unchanged: {ddb_status}", "Expected GRACE or ESCALATED")
            result["status"] = "failed"
    else:
        printer.failed("DDB record not found after triage", "Expected record")
        result["status"] = "failed"

    # Cleanup
    _cleanup()

    return result


def _cleanup():
    printer.info("Cleaning up DynamoDB record...")
    dynamodb.delete_record(INCIDENT_KEY)
    printer.info("Done.")
