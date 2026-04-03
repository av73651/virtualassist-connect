"""Detection Lambda handler — SNS alarm events.

Parses SNS records, delegates to DetectionService.
Processes records independently (P6: failure isolation).

Flow:
    1. Cold start: _init_services() loads config, creates repos and service (once)
    2. Per invocation: iterate Records, parse SNS message, route by alarm state
    3. ALARM -> DetectionService.process_alarm() -> Jira + DynamoDB + EventBridge
    4. OK -> DetectionService.process_recovery() -> Jira resolved + DynamoDB deleted

Note: This is an SNS-triggered Lambda (not API Gateway), so it uses
@observe on service/repo methods for observability rather than
@api_gateway_handler middleware."""

import json
import logging
import os

from shared.config.logging_config import configure_structured_logging

from src.models.alarm_event import AlarmEvent
from src.models.config import IncidentConfig
from src.models.exceptions import AlarmParsingError
from src.repositories.correlation_repository import CorrelationRepository
from src.repositories.ticketing_repository import TicketingRepository
from src.repositories.event_bus_repository import EventBusRepository
from src.repositories.observability_repository import ObservabilityRepository
from src.services.detection_service import DetectionService
from src.services.incident_reporter import IncidentReporter
from src.services.log_analysis_service import LogAnalysisService

configure_structured_logging()
logger = logging.getLogger(__name__)

# Module-level singleton — initialized on first cold start, reused across warm invocations
_detection_service: DetectionService | None = None
_config: IncidentConfig | None = None

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "incident_config.json")


def _init_services():
    """Lazy init on cold start. Creates repos and service singleton.

    Reads config once from incident_config.json and environment variables.
    All subsequent warm invocations reuse the same instances."""
    global _detection_service, _config

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

    log_analysis_service = LogAnalysisService(observability_repo, _config)
    incident_reporter = IncidentReporter(ticketing_repo, _config)

    _detection_service = DetectionService(
        correlation_repo=correlation_repo,
        observability_repo=observability_repo,
        ticketing_repo=ticketing_repo,
        event_bus_repo=event_bus_repo,
        log_analysis_service=log_analysis_service,
        incident_reporter=incident_reporter,
        config=_config,
    )


def _process_record(record: dict, severity_mapping: dict) -> dict:
    """Process a single SNS record. Returns result dict."""
    sns_envelope = record.get("Sns")
    if not sns_envelope or "Message" not in sns_envelope:
        raise AlarmParsingError("Invalid SNS record structure: missing Sns.Message")

    sns_message = sns_envelope["Message"]
    alarm_message = json.loads(sns_message) if isinstance(sns_message, str) else sns_message

    alarm_event = AlarmEvent.from_sns_message(alarm_message, severity_mapping)

    if alarm_event.is_recovery:
        recovered = _detection_service.process_recovery(alarm_event)
        return {
            "incident_key": alarm_event.incident_key,
            "status": "recovered" if recovered else "recovery_skipped",
            "service": alarm_event.service,
            "severity": alarm_event.severity.value,
        }

    jira_ticket_id = _detection_service.process_alarm(alarm_event)

    if jira_ticket_id:
        return {
            "incident_key": alarm_event.incident_key,
            "jira_ticket_id": jira_ticket_id,
            "status": "created",
            "service": alarm_event.service,
            "severity": alarm_event.severity.value,
            "recovery_model": alarm_event.recovery_model,
        }

    return {
        "incident_key": alarm_event.incident_key,
        "status": "filtered",
        "service": alarm_event.service,
        "severity": alarm_event.severity.value,
    }


def lambda_handler(event: dict, context) -> dict:
    """Main Lambda entry point for SNS alarm events.

    Args:
        event: SNS event with Records[].Sns.Message containing CloudWatch Alarm JSON.
        context: Lambda context (function name, request ID, etc.).

    Returns:
        Dict with 'processed' count and 'results' list."""
    global _detection_service, _config

    if _detection_service is None:
        _init_services()

    results = []
    for record in event.get("Records", []):
        try:
            result = _process_record(record, _config.severity_mapping)
            results.append(result)
        except AlarmParsingError as e:
            results.append({"status": "error", "error": str(e)})
        except Exception as e:
            logger.error("Failed to process record", exc_info=True)
            results.append({"status": "error", "error": str(e)})

    return {"processed": len(results), "results": results}
