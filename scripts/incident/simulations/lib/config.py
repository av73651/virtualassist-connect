"""Simulation configuration — AWS resource constants for dev stage."""

REGION = "us-west-2"
ACCOUNT_ID = "320644769527"
STAGE = "dev"
JIRA_BASE_URL = "https://rameshnag2002.atlassian.net"

SNS_TOPIC_ARN = f"arn:aws:sns:{REGION}:{ACCOUNT_ID}:incident-alarm-ingestion-{STAGE}"
DYNAMODB_TABLE = f"incident-correlation-{STAGE}"
LAMBDA_NAME = f"incident-detection-{STAGE}"
LOG_GROUP = f"/aws/lambda/{LAMBDA_NAME}"

# All simulation alarms use this prefix to avoid collision with real alarms
SIM_PREFIX = "sim"

# Alarm type: error-rate maps to SEV-1 (30s cool-off) — fastest for simulations
ALARM_TYPE = "error-rate"
COOLOFF_SECONDS = 30

# CloudWatch metric namespace for simulation alarms
METRIC_NAMESPACE = "Simulation/Incidents"
METRIC_NAME = "SimulationTrigger"
