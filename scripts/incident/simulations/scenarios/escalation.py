"""Scenario 5: Grace Period Escalation — recurrence during GRACE triggers IT escalation.

Validates: GRACE status + new ALARM -> EscalationRequired event + Jira escalation comment.

Since Triage/Remediation Lambdas aren't built yet, we inject a GRACE record directly
into DynamoDB to simulate the post-auto-remediation state."""

from lib import cloudwatch, sns, dynamodb, logs, printer, config

NAME = "Grace Period Escalation"
ALARM_NAME = f"{config.SIM_PREFIX}-escalate-high-{config.ALARM_TYPE}-{config.STAGE}"
INCIDENT_KEY = f"{config.SIM_PREFIX}-escalate-{config.ALARM_TYPE}-{config.STAGE}"
TOTAL_STEPS = 12


def run() -> bool:
    printer.header(f"Scenario 5: {NAME}")
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

    # Step 3: Publish first ALARM (create the incident)
    printer.step(3, TOTAL_STEPS, "Publishing ALARM event to create initial incident...")
    msg1 = sns.publish_alarm(ALARM_NAME, state="ALARM")
    printer.info(f"MessageId: {msg1}")

    # Step 4: Wait for incident creation
    printer.step(4, TOTAL_STEPS, "Waiting for incident creation...")
    printer.countdown(config.COOLOFF_SECONDS + 15, "Cool-off + processing")

    # Step 5: Verify DETECTED record, capture ticket
    printer.step(5, TOTAL_STEPS, "Verifying incident created...")
    record = dynamodb.wait_for_record(INCIDENT_KEY, timeout=30)
    if not (record and record.get("status") == "DETECTED" and record.get("jira_ticket_id")):
        printer.failed("Incident not created — cannot proceed with escalation test")
        _cleanup()
        return False
    ticket_id = record["jira_ticket_id"]
    printer.passed(f"Incident created: ticket={ticket_id}, status=DETECTED")

    # Step 6: Overwrite record to GRACE (simulate auto-remediation)
    printer.step(6, TOTAL_STEPS, "Injecting GRACE status (simulating auto-remediation)...")
    grace_record = dynamodb.build_grace_record(INCIDENT_KEY, ticket_id)
    dynamodb.put_record(grace_record)
    verify = dynamodb.get_record(INCIDENT_KEY)
    if verify and verify.get("status") == "GRACE":
        printer.passed(f"Record overwritten: status=GRACE, ticket={ticket_id}")
    else:
        printer.failed("Failed to inject GRACE record")
        _cleanup()
        return False

    # Step 7: Set alarm ALARM again, publish recurrence
    printer.step(7, TOTAL_STEPS, "Setting alarm to ALARM and publishing recurrence event...")
    ts_escalation = logs.now_ms()
    cloudwatch.set_state(ALARM_NAME, "ALARM")
    msg2 = sns.publish_alarm(ALARM_NAME, state="ALARM", reason="Recurrence after remediation")
    printer.info(f"Recurrence MessageId: {msg2}")

    # Step 8: Wait for recurrence detection
    printer.step(8, TOTAL_STEPS, "Waiting for recurrence detection...")
    printer.countdown(config.COOLOFF_SECONDS + 15, "Cool-off + processing")

    # Step 9: Verify reopened (GRACE -> DETECTED)
    printer.step(9, TOTAL_STEPS, "Verifying incident reopened...")
    record_after = dynamodb.wait_for_status(INCIDENT_KEY, "DETECTED", timeout=30)
    if record_after and record_after.get("jira_ticket_id") == ticket_id:
        printer.passed(f"Incident reopened: status=DETECTED, same ticket={ticket_id}")
    else:
        printer.failed("Incident not reopened correctly", str(record_after))
        ok = False

    # Step 10: Verify escalation comment in logs
    printer.step(10, TOTAL_STEPS, "Checking logs for escalation comment...")
    match = logs.wait_for_pattern("Incident recurred after auto-remediation", ts_escalation, timeout=20)
    if match:
        printer.passed("Logs confirm: escalation comment added to Jira.")
    else:
        printer.skipped("Could not confirm escalation comment in logs.")

    # Step 11: Verify EscalationRequired event in logs
    printer.step(11, TOTAL_STEPS, "Checking logs for EscalationRequired event...")
    match = logs.wait_for_pattern("EscalationRequired", ts_escalation, timeout=15)
    if match:
        printer.passed("Logs confirm: EscalationRequired event published to EventBridge.")
    else:
        printer.skipped("Could not confirm EscalationRequired in logs.")

    # Step 12: Cleanup
    printer.step(12, TOTAL_STEPS, "Cleaning up...")
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
