"""Scenario 1: Full Lifecycle — ALARM -> Jira ticket -> OK -> resolve -> cleanup.

Validates the complete happy path: incident creation and recovery."""

from lib import cloudwatch, sns, dynamodb, logs, printer, config

NAME = "Full Lifecycle"
ALARM_NAME = f"{config.SIM_PREFIX}-lifecycle-high-{config.ALARM_TYPE}-{config.STAGE}"
INCIDENT_KEY = f"{config.SIM_PREFIX}-lifecycle-{config.ALARM_TYPE}-{config.STAGE}"
TOTAL_STEPS = 9


def run() -> bool:
    printer.header(f"Scenario 1: {NAME}")
    ok = True
    ts = logs.now_ms()

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
        ok = False

    # Step 3: Publish ALARM
    printer.step(3, TOTAL_STEPS, "Publishing ALARM event to SNS...")
    msg_id = sns.publish_alarm(ALARM_NAME, state="ALARM")
    printer.info(f"MessageId: {msg_id}")

    # Step 4: Wait for cool-off + processing
    printer.step(4, TOTAL_STEPS, "Waiting for Lambda cool-off + processing...")
    printer.countdown(config.COOLOFF_SECONDS + 15, "Cool-off + processing")

    # Step 5: Verify DynamoDB record
    printer.step(5, TOTAL_STEPS, "Verifying DynamoDB record...")
    record = dynamodb.wait_for_record(INCIDENT_KEY, timeout=30)
    if record and record.get("status") == "DETECTED" and record.get("jira_ticket_id"):
        ticket = record["jira_ticket_id"]
        printer.passed(f"Record found: status=DETECTED, ticket={ticket}")
    else:
        printer.failed("DynamoDB record not found or unexpected status", str(record))
        _cleanup()
        return False

    # Step 6: Trigger recovery
    printer.step(6, TOTAL_STEPS, "Setting alarm to OK and publishing recovery event...")
    cloudwatch.set_state(ALARM_NAME, "OK", reason="Simulation recovery")
    sns.publish_alarm(ALARM_NAME, state="OK", old_state="ALARM", reason="Threshold returned to normal")
    printer.info("Recovery event sent.")

    # Step 7: Wait for recovery
    printer.step(7, TOTAL_STEPS, "Waiting for recovery processing...")
    printer.countdown(20, "Recovery processing")

    # Step 8: Verify deletion
    printer.step(8, TOTAL_STEPS, "Verifying DynamoDB record deleted...")
    deleted = dynamodb.wait_for_deletion(INCIDENT_KEY, timeout=30)
    if deleted:
        printer.passed("Record deleted — incident fully resolved.")
    else:
        printer.failed("Record still exists after recovery")
        ok = False

    # Step 9: Cleanup
    _cleanup()

    return ok


def _cleanup():
    printer.step(TOTAL_STEPS, TOTAL_STEPS, "Cleaning up alarm...")
    cloudwatch.delete_alarm(ALARM_NAME)
    printer.info("Done.")
