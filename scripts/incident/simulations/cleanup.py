#!/usr/bin/env python3
"""Remove all stale simulation resources from AWS.

Safe to run anytime. Finds and deletes:
- CloudWatch alarms with sim-* prefix
- DynamoDB records with sim-* incident_key prefix
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib import cloudwatch, dynamodb, printer


def main():
    printer.header("Simulation Cleanup")

    # CloudWatch alarms
    printer.step(1, 2, "Scanning for simulation CloudWatch alarms...")
    alarms = cloudwatch.delete_sim_alarms()
    if alarms:
        for name in alarms:
            printer.info(f"  Deleted: {name}")
        printer.passed(f"Deleted {len(alarms)} alarm(s).")
    else:
        printer.info("No simulation alarms found.")

    # DynamoDB records
    printer.step(2, 2, "Scanning for simulation DynamoDB records...")
    keys = dynamodb.delete_sim_records()
    if keys:
        for key in keys:
            printer.info(f"  Deleted: {key}")
        printer.passed(f"Deleted {len(keys)} record(s).")
    else:
        printer.info("No simulation records found.")

    print("\nCleanup complete.\n")


if __name__ == "__main__":
    main()
