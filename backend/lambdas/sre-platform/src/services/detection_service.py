"""DetectionService — incident detection orchestration.

Manages the alarm-to-incident pipeline: cool-off → dedup → storm check → Jira → EventBridge.
Handles conflict resolution (RESERVED/DETECTED/GRACE) and alarm recovery flows.

All observability concerns (tracing, metrics, logging) handled by @observe decorator.
Domain (raises) -> @observe (logs/metrics/traces) -> Handler (catches) -> Lambda response"""

import time
from datetime import datetime, timedelta, timezone

from shared.middleware.observability import observe

from src.domain.aws_resource_ids import build_log_group
from src.domain.jira_formatting import format_ticket_summary, format_ticket_description, build_ticket_labels
from src.models.alarm_event import AlarmEvent
from src.models.config import IncidentConfig
from src.models.correlation_record import CorrelationRecord
from src.models.enums import CorrelationStatus, EscalationReason
from src.models.exceptions import DuplicateIncidentError
from src.models.timestamps import utc_timestamp
from src.services.log_analysis_service import LogAnalysisService


class DetectionService:
    """Orchestrates incident detection: cool-off -> dedup -> storm -> DynamoDB -> Jira -> EventBridge."""

    def __init__(self, correlation_repo, observability_repo, ticketing_repo, event_bus_repo, log_analysis_service, incident_reporter, config: IncidentConfig):
        self._correlation = correlation_repo
        self._observability = observability_repo
        self._ticketing = ticketing_repo
        self._event_bus = event_bus_repo
        self._log_analysis = log_analysis_service
        self._reporter = incident_reporter
        self._config = config

    @observe(operation="process_alarm", metric_prefix="detection")
    def process_alarm(self, alarm_event: AlarmEvent) -> str | None:
        """Process incoming alarm event. Returns jira_ticket_id or None.

        Flow: cool-off -> reserve -> conflict handling -> Jira -> DynamoDB -> storm -> EventBridge"""
        incident_key = alarm_event.incident_key
        severity = alarm_event.severity.value
        now = datetime.now(timezone.utc)

        if not self._cool_off_check(alarm_event):
            return None

        record = CorrelationRecord.reserve(
            incident_key, severity,
            ttl_hours=self._config.correlation_ttl_hours, now=now,
        )

        try:
            self._correlation.reserve(record)
        except DuplicateIncidentError:
            return self._handle_conflict(alarm_event, now)

        return self._complete_incident_creation(alarm_event, record, now)

    def _complete_incident_creation(
        self, alarm_event: AlarmEvent, record: CorrelationRecord, now: datetime
    ) -> str | None:
        """Create Jira ticket, update DynamoDB, check storm, publish event.

        Shared by process_alarm (happy path) and _retry_after_stale_reclaim."""
        incident_key = alarm_event.incident_key
        severity = alarm_event.severity.value

        jira_ticket_id = self._create_jira_ticket(alarm_event, incident_key)
        if not jira_ticket_id:
            self._correlation.delete(incident_key)
            return None

        detected = record.associate_jira_ticket(jira_ticket_id)
        self._correlation.update(detected)

        storm_detected, active_count = self._check_storm()

        event_detail = {
            "incident_key": incident_key,
            "jira_ticket_id": jira_ticket_id,
            "service": alarm_event.service,
            "stage": alarm_event.stage,
            "severity": severity,
            "recovery_model": alarm_event.recovery_model,
            "service_type": alarm_event.service_type,
            "alarm_name": alarm_event.alarm_name,
            "function_name": alarm_event.function_name or "",
            "log_group": alarm_event.log_group or "",
            "metric_name": alarm_event.metric_name,
            "storm_detected": storm_detected,
            "timestamp": utc_timestamp(now),
        }
        if storm_detected:
            event_detail["active_incident_count"] = active_count

        self._event_bus.publish_event("IncidentCreated", event_detail)

        return jira_ticket_id

    @observe(operation="cool_off_check", metric_prefix="detection_cooloff")
    def _cool_off_check(self, alarm_event: AlarmEvent) -> bool:
        """Waits cool-off period, re-checks alarm state.
        Returns True if alarm still active (should proceed)."""
        cool_off = self._config.cool_off_seconds.get(alarm_event.severity.value, 30)
        time.sleep(cool_off)

        current_state = self._observability.get_alarm_state(alarm_event.alarm_name)
        return current_state == "ALARM"

    @observe(operation="check_storm", metric_prefix="detection_storm")
    def _check_storm(self) -> tuple[bool, int]:
        """Counts incidents created within storm_window_seconds.
        Returns (storm_detected, active_incident_count)."""
        since = datetime.now(timezone.utc) - timedelta(
            seconds=self._config.storm_window_seconds
        )
        count = self._correlation.count_recent(since.isoformat())
        storm_detected = count > self._config.storm_threshold
        return storm_detected, count

    def _handle_conflict(self, alarm_event: AlarmEvent, now: datetime) -> str | None:
        """Handles DuplicateIncidentError by dispatching on existing record status."""
        existing = self._correlation.get(alarm_event.incident_key)
        if existing is None:
            return None

        handler = {
            CorrelationStatus.RESERVED: self._handle_reserved_conflict,
            CorrelationStatus.DETECTED: self._handle_detected_conflict,
            CorrelationStatus.GRACE: self._handle_grace_conflict,
        }.get(existing.status)

        return handler(alarm_event, existing, now) if handler else None

    def _handle_reserved_conflict(
        self, alarm_event: AlarmEvent, existing: CorrelationRecord, now: datetime
    ) -> str | None:
        """Fresh reservation: skip. Stale reservation: reclaim and retry."""
        age = (now - existing.created_at).total_seconds()
        if age > self._config.reservation_timeout_seconds:
            self._correlation.delete(existing.incident_key)
            return self._retry_after_stale_reclaim(alarm_event, now)
        return None

    def _handle_detected_conflict(
        self, alarm_event: AlarmEvent, existing: CorrelationRecord, now: datetime
    ) -> str | None:
        """Duplicate alarm for an existing incident — comment and skip."""
        self._reporter.report_duplicate_alarm(existing.jira_ticket_id, existing.incident_key)
        return None

    def _handle_grace_conflict(
        self, alarm_event: AlarmEvent, existing: CorrelationRecord, now: datetime
    ) -> str | None:
        """Recurrence within grace period — reopen record and escalate."""
        self._reporter.report_grace_recurrence(existing.jira_ticket_id)

        reopened = existing.reopen(now, self._config.correlation_ttl_hours)
        self._correlation.update(reopened)

        self._event_bus.publish_event(
            "EscalationRequired",
            {
                "incident_key": existing.incident_key,
                "jira_ticket_id": existing.jira_ticket_id,
                "service": alarm_event.service,
                "stage": alarm_event.stage,
                "severity": alarm_event.severity.value,
                "reason": EscalationReason.GRACE_RECURRENCE,
                "timestamp": utc_timestamp(now),
            },
        )
        return None

    def _retry_after_stale_reclaim(self, alarm_event: AlarmEvent, now: datetime) -> str | None:
        """Retry reserve + create after reclaiming a stale RESERVED record."""
        incident_key = alarm_event.incident_key
        severity = alarm_event.severity.value

        record = CorrelationRecord.reserve(
            incident_key, severity,
            ttl_hours=self._config.correlation_ttl_hours, now=now,
        )
        try:
            self._correlation.reserve(record)
        except DuplicateIncidentError:
            return None

        return self._complete_incident_creation(alarm_event, record, now)

    def _create_jira_ticket(self, alarm_event: AlarmEvent, incident_key: str) -> str | None:
        """Creates Jira incident ticket. Returns ticket key or None."""
        return self._ticketing.create_jira_ticket(
            summary=format_ticket_summary(alarm_event),
            description=format_ticket_description(alarm_event),
            priority=alarm_event.severity.value,
            labels=build_ticket_labels(self._config, alarm_event),
            incident_key=incident_key,
        )

    @observe(operation="process_recovery", metric_prefix="detection_recovery")
    def process_recovery(self, alarm_event: AlarmEvent) -> bool:
        """Handles OK transition: collect diagnostics, resolve Jira, delete correlation record."""
        incident_key = alarm_event.incident_key
        existing = self._correlation.get(incident_key)

        if existing is None:
            return False

        log_group = alarm_event.log_group or build_log_group(alarm_event.service, alarm_event.stage)
        recovery_logs = self._log_analysis.collect_recent(log_group)
        current_state = self._observability.get_alarm_state(alarm_event.alarm_name)

        if existing.jira_ticket_id:
            self._reporter.report_alarm_recovered(
                existing.jira_ticket_id,
                alarm_state=current_state,
                recovery_timestamp=alarm_event.state_change_time.isoformat(),
                log_count=len(recovery_logs),
            )

            if recovery_logs:
                self._reporter.attach_log_file(
                    existing.jira_ticket_id,
                    f"recovery-logs-{alarm_event.service}.txt",
                    LogAnalysisService.format_log_attachment(recovery_logs),
                )

            # Only auto-resolve if not escalated — escalated incidents need manual attention
            if existing.status != CorrelationStatus.ESCALATED:
                self._reporter.resolve_ticket(existing.jira_ticket_id)

        self._correlation.delete(incident_key)

        return True
