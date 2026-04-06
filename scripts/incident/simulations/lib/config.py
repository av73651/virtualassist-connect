"""Simulation configuration — AWS resource constants.

Configuration values can be overridden via environment variables:
- AWS_REGION
- AWS_ACCOUNT_ID
- STAGE
- JIRA_BASE_URL
- TEST_SERVICE (service name for triage/escalation tests)
"""

import os

# Environment-specific configuration with dev defaults
REGION = os.getenv("AWS_REGION", "us-west-2")
ACCOUNT_ID = os.getenv("AWS_ACCOUNT_ID", "320644769527")
STAGE = os.getenv("STAGE", "dev")
JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "https://rameshnag2002.atlassian.net")

# Test service for leg tests (must have logs available)
TEST_SERVICE = os.getenv("TEST_SERVICE", "calculator-api")

# Derived AWS resource ARNs/names
SNS_TOPIC_ARN = f"arn:aws:sns:{REGION}:{ACCOUNT_ID}:incident-alarm-ingestion-{STAGE}"
DYNAMODB_TABLE = f"incident-correlation-{STAGE}"
LAMBDA_NAME = f"incident-detection-{STAGE}"
LOG_GROUP = f"/aws/lambda/{LAMBDA_NAME}"
TRIAGE_FUNCTION = f"incident-triage-{STAGE}"
ESCALATION_FUNCTION = f"incident-escalation-{STAGE}"

# All simulation alarms use this prefix to avoid collision with real alarms
SIM_PREFIX = "sim"

# Alarm type: error-rate maps to SEV-1 (30s cool-off) — fastest for simulations
ALARM_TYPE = "error-rate"
COOLOFF_SECONDS = 30

# CloudWatch metric namespace for simulation alarms
METRIC_NAMESPACE = "Simulation/Incidents"
METRIC_NAME = "SimulationTrigger"

# Test data constants
TEST_TTL_NEVER_EXPIRE = 9999999999  # Far future timestamp (year 2286) for test data

# OpenTelemetry configuration
OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv(
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "http://localhost:4317"  # Local OTLP collector for development
)
OTEL_TRACES_ENABLED = os.getenv("OTEL_TRACES_ENABLED", "false").lower() == "true"
OTEL_METRICS_ENABLED = os.getenv("OTEL_METRICS_ENABLED", "false").lower() == "true"
