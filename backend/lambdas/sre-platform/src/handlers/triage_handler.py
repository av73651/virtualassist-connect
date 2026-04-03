"""Triage Lambda handler — EventBridge IncidentCreated events.

Parses EventBridge event detail, delegates to TriageService.

Flow:
    1. Cold start: _init_services() loads config, creates repos and service (once)
    2. Per invocation: extract detail from EventBridge event
    3. Delegate to TriageService.triage() -> auto-resolve or escalate

Note: This is an EventBridge-triggered Lambda (not API Gateway), so it uses
@observe on service/repo methods for observability rather than
@api_gateway_handler middleware."""

import logging
import os

from shared.config.logging_config import configure_structured_logging

from src.models.config import IncidentConfig
from src.repositories.correlation_repository import CorrelationRepository
from src.repositories.ticketing_repository import TicketingRepository
from src.repositories.event_bus_repository import EventBusRepository
from src.repositories.remediation_repository import RemediationRepository
from src.repositories.recovery_repository import RecoveryRepository
from src.repositories.observability_repository import ObservabilityRepository
from src.services.ai_analysis_service import create_ai_service
from src.services.remediation.engine import RemediationEngine
from src.services.log_analysis_service import LogAnalysisService
from src.repositories.checkpoint_repository import CheckpointRepository
from src.services.delta_report_service import DeltaReportService
from src.services.resolution_service import ResolutionService
from src.services.incident_reporter import IncidentReporter
from src.services.triage_service import TriageService

configure_structured_logging()
logger = logging.getLogger(__name__)

# Module-level singleton — initialized on first cold start, reused across warm invocations
_triage_service: TriageService | None = None
_config: IncidentConfig | None = None

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "incident_config.json")


def _init_services():
    """Lazy init on cold start. Creates repos and service singleton.

    Reads config once from incident_config.json and environment variables.
    All subsequent warm invocations reuse the same instances."""
    global _triage_service, _config

    _config = IncidentConfig.load(_CONFIG_PATH)

    correlation_repo = CorrelationRepository(
        table_name=os.environ.get("CORRELATION_TABLE_NAME", "incident-correlation-dev"),
    )

    observability_repo = ObservabilityRepository()

    ticketing_repo = TicketingRepository(
        config=_config,
        jira_url=os.environ.get("JIRA_URL", ""),
        jira_project_key=os.environ.get("JIRA_PROJECT_KEY", "ASD"),
        jira_secret_name=os.environ.get("JIRA_SECRET_NAME", "sre-platform/jira-credentials"),
    )

    event_bus_repo = EventBusRepository(
        config=_config,
        event_bus_name=os.environ.get("EVENT_BUS_NAME", "default"),
    )

    remediation_repo = RemediationRepository(config=_config)
    recovery_repo = RecoveryRepository()
    remediation_engine = RemediationEngine()

    # Shared services
    log_analysis_service = LogAnalysisService(observability_repo, _config)

    # Checkpoint clarity — delta report service (optional, env-var gated)
    checkpoint_table_name = os.environ.get("CHECKPOINT_TABLE_NAME", "")
    checkpoint_bucket_name = os.environ.get("CHECKPOINT_BUCKET_NAME", "")
    delta_report_service = None
    if checkpoint_table_name and checkpoint_bucket_name:
        checkpoint_repo = CheckpointRepository(
            table_name=checkpoint_table_name,
            bucket_name=checkpoint_bucket_name,
        )
        delta_report_service = DeltaReportService(
            checkpoint_repo=checkpoint_repo,
            ticketing_repo=ticketing_repo,
        )

    resolution_service = ResolutionService(
        remediation_engine=remediation_engine,
        remediation_repo=remediation_repo,
        recovery_repo=recovery_repo,
        observability_repo=observability_repo,
        log_analysis_service=log_analysis_service,
        config=_config,
        delta_report_service=delta_report_service,
    )

    incident_reporter = IncidentReporter(ticketing_repo, _config)

    # AI analysis service (optional — disabled if env vars are empty)
    ai_service = create_ai_service(_config)
    if ai_service:
        logger.info("AI analysis service enabled")

    _triage_service = TriageService(
        correlation_repo=correlation_repo,
        event_bus_repo=event_bus_repo,
        config=_config,
        log_analysis_service=log_analysis_service,
        ai_service=ai_service,
        resolution_service=resolution_service,
        incident_reporter=incident_reporter,
    )


def lambda_handler(event: dict, context) -> dict:
    """Main Lambda entry point for EventBridge IncidentCreated events.

    Args:
        event: EventBridge event with detail containing incident_key,
               jira_ticket_id, storm_detected, recovery_model.
        context: Lambda context (function name, request ID, etc.).

    Returns:
        Dict with incident_key and status ('auto-resolved' or 'escalated')."""
    global _triage_service

    if _triage_service is None:
        _init_services()

    try:
        detail = event.get("detail", {})
        incident_key = detail["incident_key"]
        jira_ticket_id = detail["jira_ticket_id"]
        service = detail["service"]
        stage = detail["stage"]
        severity = detail["severity"]
        service_type = detail.get("service_type", "lambda")
        storm_detected = detail.get("storm_detected", False)
        recovery_model = detail.get("recovery_model", "stateless")
        alarm_name = detail.get("alarm_name", "")
        function_name = detail.get("function_name", "")
        log_group = detail.get("log_group", "")
        metric_name = detail.get("metric_name", "")

        status = _triage_service.triage(
            incident_key=incident_key,
            jira_ticket_id=jira_ticket_id,
            service=service,
            stage=stage,
            severity=severity,
            service_type=service_type,
            storm_detected=storm_detected,
            recovery_model=recovery_model,
            alarm_name=alarm_name,
            function_name=function_name,
            log_group=log_group,
            metric_name=metric_name,
        )

        return {
            "incident_key": incident_key,
            "status": status,
        }

    except Exception as e:
        logger.error("Failed to process triage event", exc_info=True)
        return {
            "incident_key": event.get("detail", {}).get("incident_key", "unknown"),
            "status": "error",
            "error": str(e),
        }
