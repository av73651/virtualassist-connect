"""EventBridge event construction and Lambda invocation for leg tests."""

import json
import boto3
from datetime import datetime, timezone

from opentelemetry import trace

from . import config
from .observability import observe

_lambda = boto3.client("lambda", region_name=config.REGION)


def build_incident_created_event(
    incident_key: str,
    jira_ticket_id: str,
    service: str,
    stage: str = "dev",
    severity: str = "SEV-1",
    recovery_model: str = "stateless",
    service_type: str = "lambda",
    alarm_name: str = "",
    function_name: str = "",
    log_group: str = "",
    metric_name: str = "Errors",
    storm_detected: bool = False,
    active_incident_count: int = 0,
) -> dict:
    """Build an IncidentCreated EventBridge event payload.

    Matches the structure published by detection_service.py."""
    now = datetime.now(timezone.utc)
    event_detail = {
        "incident_key": incident_key,
        "jira_ticket_id": jira_ticket_id,
        "service": service,
        "stage": stage,
        "severity": severity,
        "recovery_model": recovery_model,
        "service_type": service_type,
        "alarm_name": alarm_name,
        "function_name": function_name or "",
        "log_group": log_group or "",
        "metric_name": metric_name,
        "storm_detected": storm_detected,
        "timestamp": now.isoformat(),
    }
    if storm_detected:
        event_detail["active_incident_count"] = active_incident_count

    return {
        "version": "0",
        "id": f"sim-{incident_key}",
        "detail-type": "IncidentCreated",
        "source": "sre.incident-detection",
        "account": config.ACCOUNT_ID,
        "time": now.isoformat(),
        "region": config.REGION,
        "detail": event_detail,
    }


def build_escalation_required_event(
    incident_key: str,
    jira_ticket_id: str,
    service: str,
    stage: str = "dev",
    severity: str = "SEV-1",
    recovery_model: str = "stateless",
    reason: str = "NO_REMEDIATION",
    **extra,
) -> dict:
    """Build an EscalationRequired EventBridge event payload.

    Matches the structure published by triage_service.py.

    extra can include: root_cause, confidence, service_type, alarm_type,
    function_name, log_analysis, remediation_outcome, verification."""
    now = datetime.now(timezone.utc)
    event_detail = {
        "incident_key": incident_key,
        "jira_ticket_id": jira_ticket_id,
        "service": service,
        "stage": stage,
        "severity": severity,
        "recovery_model": recovery_model,
        "reason": reason,
        "timestamp": now.isoformat(),
        **extra,
    }

    return {
        "version": "0",
        "id": f"sim-escalation-{incident_key}",
        "detail-type": "EscalationRequired",
        "source": "sre.incident-triage",
        "account": config.ACCOUNT_ID,
        "time": now.isoformat(),
        "region": config.REGION,
        "detail": event_detail,
    }


@observe(operation="invoke_lambda", metric_prefix="lambda")
def _invoke_lambda_sync(function_name: str, event: dict) -> dict:
    """Invoke Lambda synchronously and return parsed payload.

    Observability provided by @observe decorator:
    - Distributed tracing with span
    - Structured JSON logging
    - Success/error metrics
    - Duration tracking

    Raises:
        RuntimeError: If Lambda invocation fails or function doesn't exist.
    """
    # Add span attributes for better observability
    span = trace.get_current_span()
    span.set_attribute("aws.lambda.function_name", function_name)
    span.set_attribute("aws.region", config.REGION)
    span.set_attribute("event.type", event.get("detail-type", "unknown"))
    span.set_attribute("incident.key", event.get("detail", {}).get("incident_key", "unknown"))

    try:
        resp = _lambda.invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(event),
        )

        payload = json.loads(resp["Payload"].read())

        # Check for Lambda function errors
        if "FunctionError" in resp:
            error_type = resp.get("FunctionError", "Unknown")
            error_message = payload.get("errorMessage", str(payload))

            # Add error attributes to span
            span.set_attribute("lambda.error_type", error_type)
            span.set_attribute("lambda.status_code", resp.get("StatusCode"))

            raise RuntimeError(
                f"Lambda '{function_name}' execution failed ({error_type}): {error_message}"
            )

        # Success attributes
        span.set_attribute("lambda.status_code", resp.get("StatusCode"))
        span.set_attribute("lambda.response_status", payload.get("status", "unknown"))

        return payload

    except _lambda.exceptions.ResourceNotFoundException as e:
        span.set_attribute("error.category", "ResourceNotFound")
        raise RuntimeError(
            f"Lambda function '{function_name}' not found. "
            f"Ensure function exists in {config.REGION} for stage {config.STAGE}."
        ) from e

    except _lambda.exceptions.InvalidRequestContentException as e:
        span.set_attribute("error.category", "InvalidRequest")
        raise RuntimeError(
            f"Invalid payload for Lambda '{function_name}': {str(e)}"
        ) from e

    except _lambda.exceptions.TooManyRequestsException as e:
        span.set_attribute("error.category", "Throttled")
        raise RuntimeError(
            f"Lambda '{function_name}' throttled. Too many concurrent executions."
        ) from e

    except Exception as e:
        span.set_attribute("error.category", "UnknownError")
        raise RuntimeError(
            f"Failed to invoke Lambda '{function_name}': {str(e)}"
        ) from e


def invoke_triage(event: dict) -> dict:
    """Invoke Triage Lambda synchronously with an EventBridge event.

    Returns the parsed response payload."""
    return _invoke_lambda_sync(config.TRIAGE_FUNCTION, event)


def invoke_escalation(event: dict) -> dict:
    """Invoke Escalation Lambda synchronously with an EventBridge event.

    Returns the parsed response payload."""
    return _invoke_lambda_sync(config.ESCALATION_FUNCTION, event)
