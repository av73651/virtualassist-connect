"""Leg Test 1: Detection — SNS alarm → Detection Lambda → DDB record + Jira ticket.

Tests Leg 1 in isolation without log group creation or Insights indexing wait.
Expected runtime: ~45s (30s cool-off + 15s processing)."""

from lib import cloudwatch, sns, dynamodb, printer, config

NAME = "Leg 1: Detection"
ALARM_NAME = f"{config.SIM_PREFIX}-leg-detection-high-{config.ALARM_TYPE}-{config.STAGE}"
INCIDENT_KEY = f"{config.SIM_PREFIX}-leg-detection-{config.ALARM_TYPE}-{config.STAGE}"
TOTAL_STEPS = 6


def run() -> dict:
    """Run leg 1 test. Returns dict with status and optional ticket_id."""
    printer.header(f"Leg Test 1: {NAME}")
    result = {"status": "passed", "ticket_id": None}

    # Step 1: Pre-clean
    printer.step(1, TOTAL_STEPS, "Pre-cleaning stale records...")
    dynamodb.delete_record(INCIDENT_KEY)
    cloudwatch.delete_alarm(ALARM_NAME)
    printer.info("Clean.")

    # Step 2: Create alarm, set ALARM
    printer.step(2, TOTAL_STEPS, f"Creating alarm {ALARM_NAME} and setting to ALARM...")
    cloudwatch.ensure_alarm(ALARM_NAME)
    cloudwatch.set_state(ALARM_NAME, "ALARM")
    state = cloudwatch.get_state(ALARM_NAME)
    if state == "ALARM":
        printer.passed(f"Alarm state: {state}")
    else:
        printer.failed(f"Alarm state: {state}", "Expected ALARM")
        _cleanup()
        return {"status": "failed", "ticket_id": None}

    # Step 3: Publish ALARM to SNS
    printer.step(3, TOTAL_STEPS, "Publishing ALARM event to SNS...")
    try:
        msg_id = sns.publish_alarm(ALARM_NAME, state="ALARM")
        printer.info(f"MessageId: {msg_id}")
    except Exception as e:
        printer.failed("SNS publish failed", str(e))
        _cleanup()
        return {"status": "failed", "ticket_id": None}

    # Step 4: Wait for cool-off + processing
    printer.step(4, TOTAL_STEPS, "Waiting for cool-off + processing...")
    printer.countdown(config.COOLOFF_SECONDS + 15, "Cool-off + processing")

    # Step 5: Verify DynamoDB record
    printer.step(5, TOTAL_STEPS, "Verifying DynamoDB record...")
    record = dynamodb.wait_for_record(INCIDENT_KEY, timeout=35)
    if record and record.get("status") == "DETECTED" and record.get("jira_ticket_id"):
        ticket = record["jira_ticket_id"]
        printer.passed(f"Record found: status=DETECTED, ticket={ticket}")
        result["ticket_id"] = ticket
    else:
        printer.failed("DynamoDB record not found or missing jira_ticket_id", str(record))
        result["status"] = "failed"

    # Step 6: Cleanup
    _cleanup()

    return result


def _cleanup():
    printer.step(TOTAL_STEPS, TOTAL_STEPS, "Cleaning up alarm...")
    cloudwatch.delete_alarm(ALARM_NAME)
    printer.info("Done.")
