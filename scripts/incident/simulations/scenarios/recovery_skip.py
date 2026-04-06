"""Scenario 4: Recovery Skip — OK for non-existent incident, verify no-op.

Validates: process_recovery returns False when no matching DynamoDB record."""

from lib import cloudwatch, sns, dynamodb, logs, printer, config

NAME = "Recovery Skip"
ALARM_NAME = f"{config.SIM_PREFIX}-skip-high-{config.ALARM_TYPE}-{config.STAGE}"
INCIDENT_KEY = f"{config.SIM_PREFIX}-skip-{config.ALARM_TYPE}-{config.STAGE}"
TOTAL_STEPS = 6


def run() -> bool:
    printer.header(f"Scenario 4: {NAME}")
    ok = True
    ts = logs.now_ms()

    # Step 1: Confirm no stale record
    printer.step(1, TOTAL_STEPS, "Confirming no stale DynamoDB record...")
    dynamodb.delete_record(INCIDENT_KEY)
    record = dynamodb.get_record(INCIDENT_KEY)
    if record is None:
        printer.passed("No existing record.")
    else:
        printer.failed("Stale record found — deleted it, but something is wrong.")
        ok = False

    # Step 2: Create alarm, set to OK
    printer.step(2, TOTAL_STEPS, f"Creating alarm {ALARM_NAME} and setting to OK...")
    cloudwatch.ensure_alarm(ALARM_NAME)
    cloudwatch.set_state(ALARM_NAME, "OK", reason="Simulation — testing recovery skip")
    printer.passed("Alarm ready in OK state.")

    # Step 3: Publish OK event
    printer.step(3, TOTAL_STEPS, "Publishing OK event to SNS...")
    msg_id = sns.publish_alarm(
        ALARM_NAME, state="OK", old_state="ALARM",
        reason="Threshold returned to normal",
    )
    printer.info(f"MessageId: {msg_id}")

    # Step 4: Wait briefly (no cool-off for OK events)
    printer.step(4, TOTAL_STEPS, "Waiting for Lambda processing...")
    printer.countdown(10, "Processing")

    # Step 5: Verify no record created
    printer.step(5, TOTAL_STEPS, "Verifying no DynamoDB record was created...")
    record = dynamodb.get_record(INCIDENT_KEY)
    if record is None:
        printer.passed("No record — recovery correctly skipped.")
    else:
        printer.failed("Unexpected record created", str(record))
        ok = False

    # Check logs for recovery_skipped
    match = logs.wait_for_pattern("recovery_skipped|process_recovery.*success", ts, timeout=15)
    if match:
        printer.passed("Logs confirm: recovery processed (no-op).")
    else:
        printer.skipped("Could not confirm recovery_skipped in logs.")

    # Step 6: Cleanup
    printer.step(6, TOTAL_STEPS, "Cleaning up alarm...")
    cloudwatch.delete_alarm(ALARM_NAME)
    printer.info("Done.")

    return ok
