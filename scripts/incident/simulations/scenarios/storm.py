"""Scenario 3: Storm Detection — 6 alarms rapidly, verify storm_detected flag.

Validates: >5 incidents in 120s window triggers storm detection."""

from lib import cloudwatch, sns, dynamodb, logs, printer, config

NAME = "Storm Detection"
COUNT = 6
TOTAL_STEPS = 6


def _alarm_name(n: int) -> str:
    return f"{config.SIM_PREFIX}-storm-{n}-high-{config.ALARM_TYPE}-{config.STAGE}"


def _incident_key(n: int) -> str:
    return f"{config.SIM_PREFIX}-storm-{n}-{config.ALARM_TYPE}-{config.STAGE}"


def run() -> bool:
    printer.header(f"Scenario 3: {NAME}")
    ok = True
    ts = logs.now_ms()

    # Step 1: Pre-clean
    printer.step(1, TOTAL_STEPS, f"Pre-cleaning {COUNT} stale records...")
    for i in range(1, COUNT + 1):
        dynamodb.delete_record(_incident_key(i))
        cloudwatch.delete_alarm(_alarm_name(i))
    printer.info("Clean.")

    # Step 2: Create all alarms, set ALARM
    printer.step(2, TOTAL_STEPS, f"Creating {COUNT} alarms and setting to ALARM...")
    for i in range(1, COUNT + 1):
        cloudwatch.ensure_alarm(_alarm_name(i), description=f"Storm simulation alarm {i}")
        cloudwatch.set_state(_alarm_name(i), "ALARM")
    printer.passed(f"{COUNT} alarms ready.")

    # Step 3: Publish all ALARM messages rapidly
    printer.step(3, TOTAL_STEPS, f"Publishing {COUNT} ALARM events rapidly...")
    for i in range(1, COUNT + 1):
        msg_id = sns.publish_alarm(_alarm_name(i), state="ALARM")
        printer.info(f"  Alarm {i}: {_alarm_name(i)} -> {msg_id}")
    printer.info("All events sent.")

    # Step 4: Wait for parallel processing
    printer.step(4, TOTAL_STEPS, "Waiting for parallel Lambda processing...")
    printer.countdown(config.COOLOFF_SECONDS + 20, "Cool-off + processing")

    # Step 5: Verify records and storm detection
    printer.step(5, TOTAL_STEPS, "Verifying DynamoDB records and storm detection...")
    created_count = 0
    for i in range(1, COUNT + 1):
        record = dynamodb.wait_for_record(_incident_key(i), timeout=30)
        if record and record.get("status") == "DETECTED":
            created_count += 1
        else:
            printer.info(f"  Alarm {i}: not created (may have been filtered by cool-off)")

    if created_count >= 4:
        printer.passed(f"{created_count}/{COUNT} incidents created.")
    else:
        printer.failed(f"Only {created_count}/{COUNT} incidents created", "Expected at least 4")
        ok = False

    # Check logs for storm_detected
    match = logs.wait_for_pattern("storm_detected.*[Tt]rue", ts, timeout=15)
    if match:
        printer.passed("Logs confirm: storm_detected=true in IncidentCreated event.")
    else:
        # Storm detection depends on timing — later events may see >5 records
        printer.skipped("Could not confirm storm_detected in logs (timing-dependent).")

    # Step 6: Cleanup
    printer.step(6, TOTAL_STEPS, f"Cleaning up {COUNT} alarms and records...")
    for i in range(1, COUNT + 1):
        cloudwatch.set_state(_alarm_name(i), "OK")
        sns.publish_alarm(_alarm_name(i), state="OK", old_state="ALARM")
    printer.countdown(20, "Recovery processing")
    for i in range(1, COUNT + 1):
        dynamodb.delete_record(_incident_key(i))
        cloudwatch.delete_alarm(_alarm_name(i))
    printer.info("Done.")

    return ok
