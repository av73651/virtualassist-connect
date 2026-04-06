"""Leg Test 3: Escalation — inject EscalationRequired event → Escalation Lambda → Jira enrichment.

Tests Leg 3 in isolation by invoking Escalation Lambda directly.
Expected runtime: ~25s."""

from lib import eventbridge, dynamodb, printer, config

NAME = "Leg 3: Escalation"
INCIDENT_KEY = f"{config.SIM_PREFIX}-leg-escalation-{config.STAGE}"
TOTAL_STEPS = 5


def run() -> dict:
    """Run leg 3 test. Returns dict with status."""
    printer.header(f"Leg Test 3: {NAME}")
    result = {"status": "passed"}

    # Step 1: Pre-clean DynamoDB
    printer.step(1, TOTAL_STEPS, "Pre-cleaning stale records...")
    dynamodb.delete_record(INCIDENT_KEY)
    printer.info("Clean.")

    # Step 2: Pre-seed DDB record with DETECTED status
    printer.step(2, TOTAL_STEPS, "Injecting DETECTED record with Jira ticket...")
    test_ticket_id = f"ASD-{config.STAGE.upper()}-LEG3"
    dynamodb.put_record({
        "incident_key": INCIDENT_KEY,
        "status": "DETECTED",
        "jira_ticket_id": test_ticket_id,
        "severity": "SEV-1",
        "created_at": "2026-04-03T12:00:00Z",
        "ttl": config.TEST_TTL_NEVER_EXPIRE,
    })
    printer.info(f"Record created: {INCIDENT_KEY} → {test_ticket_id}")

    # Step 3: Build EscalationRequired event and invoke Escalation Lambda
    printer.step(3, TOTAL_STEPS, "Invoking Escalation Lambda with EscalationRequired event...")
    event = eventbridge.build_escalation_required_event(
        incident_key=INCIDENT_KEY,
        jira_ticket_id=test_ticket_id,
        service=config.TEST_SERVICE,
        stage=config.STAGE,
        severity="SEV-1",
        recovery_model="stateless",
        reason="NO_REMEDIATION",
        root_cause="test-escalation",
        confidence="high",
    )

    try:
        response = eventbridge.invoke_escalation(event)
        printer.info(f"Escalation response: {response}")
    except Exception as e:
        printer.failed("Escalation Lambda invocation failed", str(e))
        _cleanup()
        return {"status": "failed"}

    # Step 4: Verify response status
    printer.step(4, TOTAL_STEPS, "Verifying response status...")
    response_status = response.get("status", "")
    if response_status == "escalated":
        printer.passed(f"Response status: {response_status}")
    else:
        printer.failed(f"Unexpected response status: {response_status}", "Expected escalated")
        result["status"] = "failed"

    # Step 5: Verify DynamoDB status
    printer.step(5, TOTAL_STEPS, "Verifying DynamoDB status=ESCALATED...")
    record = dynamodb.get_record(INCIDENT_KEY)
    if record:
        ddb_status = record.get("status", "")
        if ddb_status == "ESCALATED":
            printer.passed(f"DDB status: {ddb_status}")
        else:
            printer.failed(f"DDB status: {ddb_status}", "Expected ESCALATED")
            result["status"] = "failed"
    else:
        printer.failed("DDB record not found after escalation", "Expected record")
        result["status"] = "failed"

    # Cleanup
    _cleanup()

    return result


def _cleanup():
    printer.info("Cleaning up DynamoDB record...")
    dynamodb.delete_record(INCIDENT_KEY)
    printer.info("Done.")
