"""AWS resource identifier conventions for incident management.

Pure functions that build CloudWatch log group paths, Lambda function names,
and alarm name mappings from service/stage identifiers. Used across all
incident services to ensure consistent naming."""


def build_log_group(service: str, stage: str) -> str:
    """Builds CloudWatch log group path from service and stage."""
    return f"/aws/lambda/{service}-{stage}"


def build_function_name(service: str, stage: str) -> str:
    """Builds Lambda function name from service and stage."""
    return f"{service}-api-{stage}"


def derive_alarm_type(alarm_name: str) -> str:
    """Extract alarm type from alarm name.

    alarm_name format: service-high-alarm_type-stage
    Returns alarm_type portion or empty string."""
    parts = alarm_name.split("-")
    if len(parts) >= 4:
        return "-".join(parts[2:-1])
    return ""


def derive_alarm_name(incident_key: str) -> str:
    """Derives CloudWatch alarm name from incident key.

    incident_key format: service-alarm_type-stage
    alarm_name format: service-high-alarm_type-stage"""
    parts = incident_key.split("-")
    if len(parts) >= 3:
        service = parts[0]
        stage = parts[-1]
        alarm_type = "-".join(parts[1:-1])
        return f"{service}-high-{alarm_type}-{stage}"
    return incident_key
