#!/usr/bin/env python3
"""Bedrock KB — End-to-End Classification POC Demo.

Demonstrates AI-powered incident classification using Bedrock Knowledge Base
and compares results with rule-based classification.

Usage:
    python demo_classify.py --kb-id <KB_ID> --model-arn <MODEL_ARN>
    python demo_classify.py --kb-id <KB_ID> --model-arn <MODEL_ARN> --region us-west-2

Requires:
    - Bedrock KB created and ingested (setup_kb.py + ingest.py)
    - AWS credentials with bedrock:RetrieveAndGenerate permissions
"""

import argparse
import json
import os
import sys
import time

# Add the incident-manager source to path for imports
INCIDENT_MANAGER_ROOT = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "backend", "lambdas", "incident-manager"
)
sys.path.insert(0, os.path.abspath(INCIDENT_MANAGER_ROOT))

# Stub the shared middleware so we don't need OpenTelemetry installed locally
import types
shared_mod = types.ModuleType("shared")
shared_middleware = types.ModuleType("shared.middleware")
shared_config = types.ModuleType("shared.config")
shared_config_logging = types.ModuleType("shared.config.logging_config")

def _noop_observe(**kwargs):
    def decorator(fn):
        return fn
    return decorator

shared_middleware.observability = types.ModuleType("shared.middleware.observability")
shared_middleware.observability.observe = _noop_observe
shared_config_logging.configure_structured_logging = lambda: None

shared_mod.middleware = shared_middleware
shared_mod.config = shared_config
sys.modules["shared"] = shared_mod
sys.modules["shared.middleware"] = shared_middleware
sys.modules["shared.middleware.observability"] = shared_middleware.observability
sys.modules["shared.config"] = shared_config
sys.modules["shared.config.logging_config"] = shared_config_logging

import boto3

from src.repositories.bedrock_repository import BedrockRepository
from src.services.bedrock_classifier import BedrockClassifier
from src.models.config import IncidentConfig
from src.services.triage_service import TriageService


# ------------------------------------------------------------------ #
# Sample Error Payloads
# ------------------------------------------------------------------ #

SAMPLE_SCENARIOS = [
    {
        "name": "ImportError (100% failures)",
        "service_type": "lambda",
        "alarm_type": "error-rate",
        "expected_classification": "bad-deployment",
        "expected_confidence": "high",
        "error_data": {
            "error_patterns": {
                "ImportError: No module named 'payment_processor'": 150,
            },
            "error_count": 150,
            "unique_errors": 1,
            "sample_payloads": [
                "ImportError: No module named 'payment_processor'",
                "ImportError: No module named 'payment_processor'",
                "ImportError: No module named 'payment_processor'",
            ],
        },
    },
    {
        "name": "TooManyRequestsException (throttling)",
        "service_type": "lambda",
        "alarm_type": "throttle",
        "expected_classification": "rate-limit",
        "expected_confidence": "high",
        "error_data": {
            "error_patterns": {
                "TooManyRequestsException: Rate exceeded": 80,
                "ThrottlingException: Rate exceeded": 20,
            },
            "error_count": 100,
            "unique_errors": 2,
            "sample_payloads": [
                "TooManyRequestsException: Rate exceeded",
                "ThrottlingException: Rate exceeded",
            ],
        },
    },
    {
        "name": "Mixed errors after deploy",
        "service_type": "lambda",
        "alarm_type": "error-rate",
        "expected_classification": "bad-deployment",
        "expected_confidence": "medium",
        "error_data": {
            "error_patterns": {
                "TypeError: 'NoneType' object is not subscriptable": 8,
                "KeyError: 'user_id'": 6,
                "ValueError: invalid literal for int()": 4,
                "AttributeError: 'dict' object has no attribute 'items'": 3,
            },
            "error_count": 21,
            "unique_errors": 4,
            "sample_payloads": [
                "TypeError: 'NoneType' object is not subscriptable",
                "KeyError: 'user_id'",
                "ValueError: invalid literal for int()",
            ],
        },
    },
    {
        "name": "No errors (latency spike)",
        "service_type": "lambda",
        "alarm_type": "latency",
        "expected_classification": "performance-degradation",
        "expected_confidence": "medium",
        "error_data": {
            "error_patterns": {},
            "error_count": 0,
            "unique_errors": 0,
            "sample_payloads": [],
        },
    },
    {
        "name": "Unknown / ambiguous pattern",
        "service_type": "api-gateway",
        "alarm_type": "5xx-error-rate",
        "expected_classification": "unknown",
        "expected_confidence": "low",
        "error_data": {
            "error_patterns": {
                "502 Bad Gateway": 3,
                "Connection reset by peer": 2,
            },
            "error_count": 5,
            "unique_errors": 2,
            "sample_payloads": [
                "502 Bad Gateway",
                "Connection reset by peer",
            ],
        },
    },
]


# ------------------------------------------------------------------ #
# Rule-based classification (for comparison)
# ------------------------------------------------------------------ #

def classify_rule_based(error_data: dict) -> tuple[str, str, str]:
    """Run rule-based classification using TriageService (no Bedrock)."""
    config_path = os.path.join(INCIDENT_MANAGER_ROOT, "incident_config.json")
    config = IncidentConfig.load(config_path)

    # Create minimal TriageService with no Bedrock
    from unittest.mock import Mock
    service = TriageService(
        correlation_repo=Mock(),
        observability_repo=Mock(),
        integration_repo=Mock(),
        config=config,
        bedrock_classifier=None,
    )

    return service._classify_root_cause_rules(error_data)


# ------------------------------------------------------------------ #
# Main
# ------------------------------------------------------------------ #

def main():
    parser = argparse.ArgumentParser(description="Bedrock KB Classification POC Demo")
    parser.add_argument("--kb-id", required=True, help="Bedrock Knowledge Base ID")
    parser.add_argument(
        "--model-arn", required=True,
        help="Foundation model ARN (e.g., arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-3-5-haiku-20241022-v1:0)",
    )
    parser.add_argument("--region", default="us-west-2", help="AWS region")
    args = parser.parse_args()

    print("=" * 70)
    print("Bedrock KB — Classification POC Demo")
    print("=" * 70)
    print(f"KB ID:     {args.kb_id}")
    print(f"Model:     {args.model_arn}")
    print(f"Region:    {args.region}")
    print(f"Scenarios: {len(SAMPLE_SCENARIOS)}")

    # Initialize Bedrock classifier
    bedrock_client = boto3.client("bedrock-agent-runtime", region_name=args.region)
    bedrock_repo = BedrockRepository(bedrock_agent_client=bedrock_client)
    classifier = BedrockClassifier(bedrock_repo, args.kb_id, args.model_arn)

    results = []

    for i, scenario in enumerate(SAMPLE_SCENARIOS, 1):
        print(f"\n{'─' * 70}")
        print(f"Scenario {i}/{len(SAMPLE_SCENARIOS)}: {scenario['name']}")
        print(f"  Service: {scenario['service_type']} | Alarm: {scenario['alarm_type']}")
        print(f"  Errors:  {scenario['error_data']['error_count']} total, "
              f"{scenario['error_data']['unique_errors']} unique")
        print(f"  Expected: {scenario['expected_classification']} ({scenario['expected_confidence']})")

        # Rule-based classification
        rule_class, rule_conf, rule_evidence = classify_rule_based(scenario["error_data"])
        print(f"\n  [RULES]   classification={rule_class}, confidence={rule_conf}")
        print(f"            evidence={rule_evidence[:80]}")

        # Bedrock AI classification
        print(f"\n  [BEDROCK] Querying KB...")
        start = time.time()
        bedrock_result = classifier.classify(
            scenario["error_data"],
            service_type=scenario["service_type"],
            alarm_type=scenario["alarm_type"],
        )
        elapsed = time.time() - start

        if bedrock_result:
            print(f"  [BEDROCK] classification={bedrock_result['classification']}, "
                  f"confidence={bedrock_result['confidence']} ({elapsed:.1f}s)")
            print(f"            action={bedrock_result['recommended_action']}, "
                  f"automation={bedrock_result['automation_level']}")
            print(f"            reasoning={bedrock_result['reasoning'][:120]}")
        else:
            print(f"  [BEDROCK] FAILED (returned None) ({elapsed:.1f}s)")

        # Comparison
        bedrock_class = bedrock_result["classification"] if bedrock_result else "FAILED"
        match_expected = bedrock_class == scenario["expected_classification"]
        match_rules = bedrock_class == rule_class

        results.append({
            "scenario": scenario["name"],
            "expected": scenario["expected_classification"],
            "rules": rule_class,
            "bedrock": bedrock_class,
            "match_expected": match_expected,
            "match_rules": match_rules,
            "latency_s": elapsed,
        })

    # Summary
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    print(f"\n{'Scenario':<35} {'Expected':<18} {'Rules':<18} {'Bedrock':<18} {'Match'}")
    print("-" * 105)

    matches = 0
    for r in results:
        match_marker = "YES" if r["match_expected"] else "NO"
        print(f"  {r['scenario']:<33} {r['expected']:<18} {r['rules']:<18} {r['bedrock']:<18} {match_marker}")
        if r["match_expected"]:
            matches += 1

    total = len(results)
    print(f"\nBedrock accuracy: {matches}/{total} ({matches/total*100:.0f}%) matched expected classifications")
    avg_latency = sum(r["latency_s"] for r in results) / total
    print(f"Average latency:  {avg_latency:.1f}s per classification")

    return results


if __name__ == "__main__":
    main()
