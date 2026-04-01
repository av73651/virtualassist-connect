#!/usr/bin/env python3
"""Incident Management Simulation Runner.

Usage:
    python run.py                    # Run all scenarios
    python run.py --scenario 1 4     # Run selected scenarios
    python run.py --list             # List available scenarios
"""

import argparse
import sys
import os

# Add simulations directory to path so lib/ is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib import printer
from scenarios import full_lifecycle, duplicate, storm, recovery_skip, escalation, happy_path_e2e

SCENARIOS = {
    1: ("Full Lifecycle", full_lifecycle),
    2: ("Duplicate Detection", duplicate),
    3: ("Storm Detection", storm),
    4: ("Recovery Skip", recovery_skip),
    5: ("Grace Period Escalation", escalation),
    6: ("Happy Path E2E (3-Lambda Pipeline)", happy_path_e2e),
}


def main():
    parser = argparse.ArgumentParser(description="Incident Management Simulation Runner")
    parser.add_argument(
        "--scenario", "-s", type=int, nargs="+",
        help="Scenario numbers to run (e.g., --scenario 1 4)",
    )
    parser.add_argument(
        "--list", "-l", action="store_true",
        help="List available scenarios",
    )
    args = parser.parse_args()

    if args.list:
        print("\nAvailable scenarios:")
        for num, (name, _) in SCENARIOS.items():
            print(f"  {num}. {name}")
        print(f"\nUsage: python run.py --scenario {' '.join(str(n) for n in SCENARIOS)}")
        return

    to_run = args.scenario if args.scenario else sorted(SCENARIOS.keys())

    # Validate
    for num in to_run:
        if num not in SCENARIOS:
            print(f"Error: Unknown scenario {num}. Use --list to see available scenarios.")
            sys.exit(1)

    printer.header("Incident Management Simulation Suite")
    print(f"  Running {len(to_run)} scenario(s): {', '.join(SCENARIOS[n][0] for n in to_run)}\n")

    results = []
    for num in to_run:
        name, module = SCENARIOS[num]
        try:
            passed = module.run()
            results.append((f"{num}. {name}", passed))
        except Exception as e:
            printer.failed(f"Scenario {num} crashed", str(e))
            results.append((f"{num}. {name}", False))

    printer.summary(results)

    # Exit with failure code if any scenario failed
    if not all(ok for _, ok in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
