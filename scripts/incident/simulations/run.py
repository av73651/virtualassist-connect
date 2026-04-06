#!/usr/bin/env python3
"""Incident Management Simulation Runner.

Usage:
    python run.py                    # Run leg tests only (default, ~2.5 min)
    python run.py --e2e              # Run e2e tests only (~10 min)
    python run.py --all              # Run legs then e2e (~12.5 min)
    python run.py --leg L1 L4        # Run specific leg tests
    python run.py --scenario 1 4     # Run specific e2e tests (backward compat)
    python run.py --list             # List available tests
"""

import argparse
import sys
import os

# Add simulations directory to path so lib/ is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib import printer
from scenarios import (
    leg_detection,
    leg_triage,
    leg_escalation,
    leg_escalation_delta,
    full_lifecycle,
    duplicate,
    storm,
    recovery_skip,
    escalation,
    happy_path_e2e,
    real_observability_e2e,
)

LEG_TESTS = {
    "L1": ("Leg 1: Detection", leg_detection),
    "L2": ("Leg 2: Triage", leg_triage),
    "L3": ("Leg 3: Escalation", leg_escalation),
    "L4": ("Leg 4: Escalation Delta Report", leg_escalation_delta),
}

E2E_TESTS = {
    1: ("Full Lifecycle", full_lifecycle),
    2: ("Duplicate Detection", duplicate),
    3: ("Storm Detection", storm),
    4: ("Recovery Skip", recovery_skip),
    5: ("Grace Period Escalation", escalation),
    6: ("Happy Path E2E (3-Lambda Pipeline)", happy_path_e2e),
    7: ("Real Observability E2E (Custom Metrics + Alarm)", real_observability_e2e),
}


def main():
    parser = argparse.ArgumentParser(description="Incident Management Simulation Runner")
    parser.add_argument(
        "--legs", action="store_true",
        help="Run leg tests only (default)",
    )
    parser.add_argument(
        "--e2e", action="store_true",
        help="Run e2e tests only",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Run both leg and e2e tests",
    )
    parser.add_argument(
        "--leg", type=str, nargs="+",
        help="Run specific leg tests (e.g., --leg L1 L4)",
    )
    parser.add_argument(
        "--scenario", "-s", type=int, nargs="+",
        help="Run specific e2e tests (e.g., --scenario 1 4)",
    )
    parser.add_argument(
        "--list", "-l", action="store_true",
        help="List available tests",
    )
    args = parser.parse_args()

    if args.list:
        print("\nLeg Tests (~2.5 min total):")
        for leg_id, (name, _) in LEG_TESTS.items():
            print(f"  {leg_id}. {name}")
        print("\nE2E Tests (~10 min total):")
        for num, (name, _) in E2E_TESTS.items():
            print(f"  {num}. {name}")
        print("\nUsage:")
        print("  python run.py              # Run leg tests (default)")
        print("  python run.py --e2e        # Run e2e tests")
        print("  python run.py --all        # Run both")
        print("  python run.py --leg L1 L4  # Run specific leg tests")
        print("  python run.py --scenario 1 4  # Run specific e2e tests")
        return

    # Determine what to run
    run_legs = args.legs or args.all or args.leg or (not args.e2e and not args.scenario)
    run_e2e = args.e2e or args.all or args.scenario

    results = []

    # Run leg tests
    if run_legs:
        if args.leg:
            # Run specific leg tests
            leg_ids = args.leg
            for leg_id in leg_ids:
                if leg_id not in LEG_TESTS:
                    print(f"Error: Unknown leg test {leg_id}. Use --list to see available tests.")
                    sys.exit(1)
        else:
            # Run all leg tests
            leg_ids = sorted(LEG_TESTS.keys())

        printer.header("Leg Tests (Targeted Lambda Invocation)")
        print(f"  Running {len(leg_ids)} leg test(s): {', '.join(LEG_TESTS[lid][0] for lid in leg_ids)}\n")

        for leg_id in leg_ids:
            name, module = LEG_TESTS[leg_id]
            try:
                result = module.run()
                # Leg tests return dict with status
                passed = result.get("status") == "passed"
                results.append((f"{leg_id}. {name}", passed))
            except Exception as e:
                printer.failed(f"Leg test {leg_id} crashed", str(e))
                results.append((f"{leg_id}. {name}", False))

    # Run e2e tests
    if run_e2e:
        if args.scenario:
            # Run specific e2e tests
            scenario_nums = args.scenario
            for num in scenario_nums:
                if num not in E2E_TESTS:
                    print(f"Error: Unknown e2e test {num}. Use --list to see available tests.")
                    sys.exit(1)
        else:
            # Run all e2e tests
            scenario_nums = sorted(E2E_TESTS.keys())

        printer.header("E2E Tests (Full AWS Infrastructure)")
        print(f"  Running {len(scenario_nums)} e2e test(s): {', '.join(E2E_TESTS[n][0] for n in scenario_nums)}\n")

        for num in scenario_nums:
            name, module = E2E_TESTS[num]
            try:
                passed = module.run()
                results.append((f"{num}. {name}", passed))
            except Exception as e:
                printer.failed(f"E2E test {num} crashed", str(e))
                results.append((f"{num}. {name}", False))

    printer.summary(results)

    # Exit with failure code if any test failed
    if not all(ok for _, ok in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
