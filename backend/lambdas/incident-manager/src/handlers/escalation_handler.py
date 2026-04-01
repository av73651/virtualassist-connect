"""Escalation Lambda handler — EventBridge EscalationRequired events.

Parses EventBridge event detail, delegates to EscalationService.

Flow:
    1. Cold start: _init_services() loads config, creates repos and service (once)
    2. Per invocation: extract detail from EventBridge event
    3. Delegate to EscalationService.escalate() -> enrich Jira + notify

Note: This is an EventBridge-triggered Lambda (not API Gateway), so it uses
@observe on service/repo methods for observability rather than
@api_gateway_handler middleware."""

import logging
import os

from shared.config.logging_config import configure_structured_logging

from src.models.config import IncidentConfig
from src.repositories.correlation_repository import CorrelationRepository
from src.repositories.ticketing_repository import TicketingRepository
from src.repositories.notification_repository import NotificationRepository
from src.repositories.observability_repository import ObservabilityRepository
from src.services.ai_analysis_service import create_ai_service
from src.services.escalation_service import EscalationService
from src.services.log_analysis_service import LogAnalysisService

configure_structured_logging()
logger = logging.getLogger(__name__)

# Module-level singleton
_escalation_service: EscalationService | None = None
_config: IncidentConfig | None = None

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "incident_config.json")


def _init_services():
    """Lazy init on cold start."""
    global _escalation_service, _config

    _config = IncidentConfig.load(_CONFIG_PATH)

    correlation_repo = CorrelationRepository(
        table_name=os.environ.get("CORRELATION_TABLE_NAME", "incident-correlation-dev"),
    )

    observability_repo = ObservabilityRepository()

    ticketing_repo = TicketingRepository(
        config=_config,
        jira_url=os.environ.get("JIRA_URL", ""),
        jira_project_key=os.environ.get("JIRA_PROJECT_KEY", "ASD"),
        jira_secret_name=os.environ.get("JIRA_SECRET_NAME", "incident-manager/jira-credentials"),
    )

    notification_repo = NotificationRepository()

    notification_topic_arn = os.environ.get("NOTIFICATION_TOPIC_ARN", "")

    # AI analysis service (optional — disabled if env vars are empty)
    ai_service = create_ai_service(_config)
    if ai_service:
        logger.info("AI analysis service enabled for escalation")

    log_analysis_service = LogAnalysisService(observability_repo, _config)

    _escalation_service = EscalationService(
        correlation_repo=correlation_repo,
        log_analysis_service=log_analysis_service,
        ticketing_repo=ticketing_repo,
        notification_repo=notification_repo,
        notification_topic_arn=notification_topic_arn,
        ai_service=ai_service,
        region=os.environ.get("AWS_REGION", "us-west-2"),
    )


def lambda_handler(event: dict, context) -> dict:
    """Main Lambda entry point for EventBridge EscalationRequired events.

    Returns dict with incident_key and status."""
    global _escalation_service

    if _escalation_service is None:
        _init_services()

    try:
        detail = event.get("detail", {})
        incident_key = detail["incident_key"]
        jira_ticket_id = detail["jira_ticket_id"]
        service = detail["service"]
        stage = detail["stage"]
        severity = detail["severity"]
        reason = detail.get("reason", "unknown")
        function_name = detail.get("function_name", "")
        verification = detail.get("verification")
        root_cause = detail.get("root_cause", "")
        confidence = detail.get("confidence", "")
        service_type = detail.get("service_type", "lambda")
        alarm_type = detail.get("alarm_type", "")
        remediation_outcome = detail.get("remediation_outcome", "")
        log_analysis = detail.get("log_analysis", "")

        status = _escalation_service.escalate(
            incident_key=incident_key,
            jira_ticket_id=jira_ticket_id,
            service=service,
            stage=stage,
            severity=severity,
            reason=reason,
            function_name=function_name,
            verification=verification,
            root_cause=root_cause,
            confidence=confidence,
            service_type=service_type,
            alarm_type=alarm_type,
            remediation_outcome=remediation_outcome,
            log_analysis=log_analysis,
        )

        return {
            "incident_key": incident_key,
            "status": status,
        }

    except Exception as e:
        logger.error("Failed to process escalation event", exc_info=True)
        return {
            "incident_key": event.get("detail", {}).get("incident_key", "unknown"),
            "status": "error",
            "error": str(e),
        }
