"""AlarmEvent — parsed from SNS CloudWatch Alarm message.

Immutable representation of a CloudWatch Alarm notification.
Alarm name convention: {service}-{high|low}-{alarm_type}-{stage}
Examples:
  calculator-high-error-rate-prod → service=calculator, type=error-rate, stage=prod
  calculator-low-traffic-prod     → service=calculator, type=traffic,    stage=prod"""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from src.models.enums import Severity
from src.models.exceptions import AlarmParsingError

# Alarm naming convention: {service}-{high|low}-{type}-{stage}
_ALARM_NAME_PATTERN = re.compile(r"^(.+)-(high|low)-(.+)-(.+)$")

# CloudWatch metric namespace → service_type mapping
_NAMESPACE_TO_SERVICE_TYPE: dict[str, str] = {
    "AWS/Lambda": "lambda",
    "Custom/Lambda": "lambda",
    "AWS/ApiGateway": "api-gateway",
    "AWS/ES": "elasticsearch",
    "AWS/OpenSearch": "elasticsearch",
}


@dataclass(frozen=True)
class AlarmEvent:
    """Parsed from SNS CloudWatch Alarm message."""

    alarm_name: str
    alarm_description: str
    new_state: str
    old_state: str
    reason: str
    state_change_time: datetime
    region: str
    account_id: str
    alarm_arn: str                          # Full CloudWatch alarm ARN
    trigger_dimensions: dict[str, str]      # Metric dimensions (e.g., {"FunctionName": "calc-api-prod"})
    metric_name: str                         # CloudWatch metric name (e.g., "Errors", "Duration")
    metric_namespace: str                    # CloudWatch namespace (e.g., "AWS/Lambda")

    # Derived from alarm_name convention
    service: str
    alarm_type: str
    stage: str
    severity: Severity

    recovery_model: str
    service_type: str

    @classmethod
    def from_sns_message(cls, message: dict, severity_mapping: dict[str, dict]) -> "AlarmEvent":
        """Factory: parses CloudWatch Alarm SNS message JSON.
        Extracts service, alarm_type, stage from alarm name.
        Extracts alarm_arn and trigger_dimensions from message.
        Classifies severity and recovery_model from externalized severity_mapping."""
        if isinstance(message, str):
            message = json.loads(message)

        alarm_name = message.get("AlarmName", "")
        match = _ALARM_NAME_PATTERN.match(alarm_name)
        if not match:
            raise AlarmParsingError(
                f"Alarm name '{alarm_name}' does not match pattern "
                "'{service}-{{high|low}}-{type}-{stage}'"
            )

        service = match.group(1)
        # group(2) is threshold direction (high/low) — used in naming only
        alarm_type = match.group(3)
        stage = match.group(4)

        mapping = severity_mapping.get(
            alarm_type, {"severity": "SEV-3", "recovery_model": "stateless"}
        )
        severity = Severity(mapping["severity"])
        recovery_model = mapping.get("recovery_model", "stateless")

        state_change_str = message.get("StateChangeTime", "")
        try:
            state_change_time = datetime.strptime(
                state_change_str, "%Y-%m-%dT%H:%M:%S.%f%z"
            )
        except (ValueError, TypeError):
            state_change_time = datetime.now(timezone.utc)

        # Extract alarm ARN
        alarm_arn = message.get("AlarmArn", "")

        # Extract trigger dimensions: [{name, value}] → {name: value}
        trigger = message.get("Trigger", {})
        raw_dimensions = trigger.get("Dimensions", [])
        trigger_dimensions = {
            d["name"]: d["value"]
            for d in raw_dimensions
            if "name" in d and "value" in d
        }

        # Extract metric context from trigger
        namespace = trigger.get("Namespace", "")
        metric_name = trigger.get("MetricName", "")
        service_type = _NAMESPACE_TO_SERVICE_TYPE.get(namespace, "unknown")

        return cls(
            alarm_name=alarm_name,
            alarm_description=message.get("AlarmDescription", ""),
            new_state=message.get("NewStateValue", ""),
            old_state=message.get("OldStateValue", ""),
            reason=message.get("NewStateReason", ""),
            state_change_time=state_change_time,
            region=message.get("Region", ""),
            account_id=message.get("AWSAccountId", ""),
            alarm_arn=alarm_arn,
            trigger_dimensions=trigger_dimensions,
            metric_name=metric_name,
            metric_namespace=namespace,
            service=service,
            alarm_type=alarm_type,
            stage=stage,
            severity=severity,
            recovery_model=recovery_model,
            service_type=service_type,
        )

    @property
    def incident_key(self) -> str:
        return f"{self.service}-{self.alarm_type}-{self.stage}"

    @property
    def function_name(self) -> str | None:
        """Lambda function name from trigger dimensions, or None."""
        return self.trigger_dimensions.get("FunctionName")

    @property
    def log_group(self) -> str | None:
        """CloudWatch log group for the source Lambda, or None."""
        name = self.function_name
        return f"/aws/lambda/{name}" if name else None

    @property
    def is_alarm(self) -> bool:
        return self.new_state == "ALARM"

    @property
    def is_recovery(self) -> bool:
        return self.new_state == "OK"
