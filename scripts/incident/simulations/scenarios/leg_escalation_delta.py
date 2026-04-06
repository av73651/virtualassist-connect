"""Leg Test 4: Escalation Delta Report — checkpoint + EscalationRequired with recovery_model=reprocess → delta report.

Tests Leg 3 delta report path: creates checkpoint with partial progress,
invokes Escalation Lambda with reprocess model, verifies delta report posted to Jira.
Expected runtime: ~30s (no log group creation, no Insights wait)."""

from lib import eventbridge, dynamodb, checkpoint, printer, config

NAME = "Leg 3: Delta Report"
TEST_SERVICE = "sim"  # Service name for checkpoint
INCIDENT_KEY = f"{config.SIM_PREFIX}-leg-delta-{config.STAGE}"
CHECKPOINT_ID = f"{config.SIM_PREFIX}-batch-delta-{config.STAGE}"
TOTAL_STEPS = 6


def run() -> dict:
    """Run leg 4 test (delta report). Returns dict with status."""
    printer.header(f"Leg Test 4: {NAME}")
    result = {"status": "passed"}

    # Step 1: Pre-clean checkpoint + DynamoDB
    printer.step(1, TOTAL_STEPS, "Pre-cleaning stale checkpoint and DDB record...")
    checkpoint.delete_checkpoint(CHECKPOINT_ID)
    dynamodb.delete_record(INCIDENT_KEY)
    printer.info("Clean.")

    # Step 2: Write checkpoint with 100 items, mark 50 complete, log failure at item-50
    printer.step(2, TOTAL_STEPS, "Creating checkpoint: 100 items, 50 complete, failure at item-50...")
    item_ids = [f"item-{i:03d}" for i in range(1, 101)]
    checkpoint.write_checkpoint(
        checkpoint_id=CHECKPOINT_ID,
        service=TEST_SERVICE,
        operation="batch-process",
        item_ids=item_ids,
        timeout_seconds=300,
    )

    # Mark first 50 items complete
    completed_ids = item_ids[:50]
    checkpoint.mark_progress(CHECKPOINT_ID, completed_ids)

    # Log failure at item-50
    checkpoint.log_failure(CHECKPOINT_ID, "item-050", "Simulated batch failure at item-50")
    printer.info(f"Checkpoint created: {CHECKPOINT_ID} (50/100 complete, failure logged)")

    # Step 3: Pre-seed DDB record with Jira ticket
    printer.step(3, TOTAL_STEPS, "Injecting DETECTED record with Jira ticket...")
    test_ticket_id = f"ASD-{config.STAGE.upper()}-LEG4"
    dynamodb.put_record({
        "incident_key": INCIDENT_KEY,
        "status": "DETECTED",
        "jira_ticket_id": test_ticket_id,
        "severity": "SEV-1",
        "created_at": "2026-04-03T12:00:00Z",
        "ttl": config.TEST_TTL_NEVER_EXPIRE,
    })
    printer.info(f"Record created: {INCIDENT_KEY} → {test_ticket_id}")

    # Step 4: Build EscalationRequired event with recovery_model=reprocess and invoke Escalation Lambda
    printer.step(4, TOTAL_STEPS, "Invoking Escalation Lambda with recovery_model=reprocess...")
    event = eventbridge.build_escalation_required_event(
        incident_key=INCIDENT_KEY,
        jira_ticket_id=test_ticket_id,
        service=TEST_SERVICE,
        stage=config.STAGE,
        severity="SEV-1",
        recovery_model="reprocess",
        reason="REMEDIATION_FAILED",
        root_cause="batch-processing-failure",
        confidence="high",
    )

    try:
        response = eventbridge.invoke_escalation(event)
        printer.info(f"Escalation response: {response}")
    except Exception as e:
        printer.failed("Escalation Lambda invocation failed", str(e))
        _cleanup()
        return {"status": "failed"}

    # Step 5: Verify response status
    printer.step(5, TOTAL_STEPS, "Verifying response status=escalated...")
    response_status = response.get("status", "")
    if response_status == "escalated":
        printer.passed(f"Response status: {response_status}")
    else:
        printer.failed(f"Unexpected response status: {response_status}", "Expected escalated")
        result["status"] = "failed"

    # Step 6: Verify DDB status
    printer.step(6, TOTAL_STEPS, "Verifying DynamoDB status=ESCALATED...")
    record = dynamodb.get_record(INCIDENT_KEY)
    if record:
        ddb_status = record.get("status", "")
        if ddb_status == "ESCALATED":
            printer.passed(f"DDB status: {ddb_status}")
            printer.info(f"✓ Delta report should be posted to Jira ticket {test_ticket_id}")
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
    printer.info("Cleaning up checkpoint and DynamoDB record...")
    checkpoint.delete_checkpoint(CHECKPOINT_ID)
    dynamodb.delete_record(INCIDENT_KEY)
    printer.info("Done.")
