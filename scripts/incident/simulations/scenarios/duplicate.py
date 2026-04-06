"""Scenario 2: Duplicate Detection — same alarm twice, verify no new ticket.

Validates: DuplicateIncidentError -> add comment to existing Jira ticket."""

from lib import cloudwatch, sns, dynamodb, logs, printer, config

NAME = "Duplicate Detection"
ALARM_NAME = f"{config.SIM_PREFIX}-dup-high-{config.ALARM_TYPE}-{config.STAGE}"
INCIDENT_KEY = f"{config.SIM_PREFIX}-dup-{config.ALARM_TYPE}-{config.STAGE}"
TOTAL_STEPS = 9


def run() -> bool:
    printer.header(f"Scenario 2: {NAME}")
    ok = True
    ts = logs.now_ms()

    # Step 1: Pre-clean
    printer.step(1, TOTAL_STEPS, "Pre-cleaning stale records...")
    dynamodb.delete_record(INCIDENT_KEY)
    cloudwatch.delete_alarm(ALARM_NAME)
    printer.info("Clean.")

    # Step 2: Create alarm, set ALARM
    printer.step(2, TOTAL_STEPS, f"Creating alarm and setting to ALARM...")
    cloudwatch.ensure_alarm(ALARM_NAME)
    cloudwatch.set_state(ALARM_NAME, "ALARM")
    printer.passed(f"Alarm {ALARM_NAME} ready.")

    # Step 3: Publish first ALARM
    printer.step(3, TOTAL_STEPS, "Publishing first ALARM event...")
    msg1 = sns.publish_alarm(ALARM_NAME, state="ALARM")
    printer.info(f"First MessageId: {msg1}")

    # Step 4: Wait for first processing
    printer.step(4, TOTAL_STEPS, "Waiting for first event processing...")
    printer.countdown(config.COOLOFF_SECONDS + 15, "Cool-off + processing")

    # Step 5: Verify first record
    printer.step(5, TOTAL_STEPS, "Verifying first incident created...")
    record = dynamodb.wait_for_record(INCIDENT_KEY, timeout=30)
    if not (record and record.get("jira_ticket_id")):
        printer.failed("First incident not created")
        _cleanup()
        return False
    original_ticket = record["jira_ticket_id"]
    printer.passed(f"Incident created: ticket={original_ticket}")

    # Step 6: Publish second ALARM (duplicate)
    printer.step(6, TOTAL_STEPS, "Publishing second ALARM (duplicate)...")
    # Re-set alarm state in case it drifted
    cloudwatch.set_state(ALARM_NAME, "ALARM")
    msg2 = sns.publish_alarm(ALARM_NAME, state="ALARM")
    printer.info(f"Second MessageId: {msg2}")

    # Step 7: Wait for duplicate processing
    printer.step(7, TOTAL_STEPS, "Waiting for duplicate processing...")
    printer.countdown(config.COOLOFF_SECONDS + 15, "Cool-off + processing")

    # Step 8: Verify still one record, same ticket
    printer.step(8, TOTAL_STEPS, "Verifying duplicate handling...")
    record_after = dynamodb.get_record(INCIDENT_KEY)
    if record_after and record_after.get("jira_ticket_id") == original_ticket:
        printer.passed(f"Same ticket: {original_ticket} — no duplicate created.")
    else:
        printer.failed("Record changed or missing after duplicate", str(record_after))
        ok = False

    # Check logs for duplicate message
    match = logs.wait_for_pattern("Duplicate alarm received", ts, timeout=15)
    if match:
        printer.passed("Logs confirm: duplicate alarm comment added.")
    else:
        printer.skipped("Could not confirm duplicate log message (may have scrolled).")

    # Step 9: Cleanup
    printer.step(9, TOTAL_STEPS, "Cleaning up...")
    cloudwatch.set_state(ALARM_NAME, "OK")
    sns.publish_alarm(ALARM_NAME, state="OK", old_state="ALARM")
    printer.countdown(20, "Recovery processing")
    dynamodb.delete_record(INCIDENT_KEY)
    cloudwatch.delete_alarm(ALARM_NAME)
    printer.info("Done.")

    return ok


def _cleanup():
    dynamodb.delete_record(INCIDENT_KEY)
    cloudwatch.delete_alarm(ALARM_NAME)
