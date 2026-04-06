"""EscalationService — incident escalation orchestration (Leg 3).

Receives EscalationRequired events from Triage Lambda. Enriches Jira ticket
with AI-powered log analysis, structured ADF formatting, and diagnostic links.
Notifies engineers via SNS for SEV-1/SEV-2.

All observability concerns (tracing, metrics, logging) handled by @observe decorator."""

import logging
from datetime import datetime, timezone

from shared.middleware.observability import observe

from src.domain.aws_resource_ids import build_function_name
from src.domain.jira_formatting import (
    build_escalation_adf,
    build_notification_message,
)
from src.models.enums import CorrelationStatus
from src.models.timestamps import utc_timestamp
from src.services.log_analysis_service import LogAnalysisService

logger = logging.getLogger(__name__)


class EscalationService:
    """Leg 3: AI-enriched Jira -> attach diagnostics -> notify engineer."""

    def __init__(
        self,
        correlation_repo,
        log_analysis_service: LogAnalysisService,
        ticketing_repo,
        notification_repo,
        notification_topic_arn: str = "",
        ai_service=None,
        region: str = "us-west-2",
        delta_report_service=None,
        metrics_collection_service=None,
    ):
        self._correlation = correlation_repo
        self._log_analysis = log_analysis_service
        self._ticketing = ticketing_repo
        self._notification = notification_repo
        self._notification_topic_arn = notification_topic_arn
        self._ai_service = ai_service
        self._region = region
        self._delta_report = delta_report_service
        self._metrics_service = metrics_collection_service

    @observe(operation="escalate_incident", metric_prefix="escalation")
    def escalate(
        self,
        incident_key: str,
        jira_ticket_id: str,
        service: str,
        stage: str,
        severity: str,
        reason: str,
        function_name: str = "",
        verification: dict | None = None,
        root_cause: str = "",
        confidence: str = "",
        service_type: str = "lambda",
        alarm_type: str = "",
        remediation_outcome: str = "",
        log_analysis: str = "",
        recovery_model: str = "stateless",
        alarm_name: str = "",
    ) -> str:
        """Main entry point. Returns 'escalated'.

        Flow:
        1. Update DynamoDB -> ESCALATED
        2. Collect diagnostic data (error logs)
        3. AI-analyze logs via AIAnalysisService (optional, graceful fallback)
        4. Enrich Jira with ADF-formatted comment (clickable links, headings, code blocks)
        5. Attach error logs as file
        6. Delta report for checkpoint-aware recovery models (reprocess)
        7. Notify engineer via SNS (SEV-1/SEV-2 only)"""
        now = datetime.now(timezone.utc)

        # Step 1: Update DynamoDB -> ESCALATED
        existing = self._correlation.get(incident_key)
        if existing:
            self._correlation.update(existing.to_status(CorrelationStatus.ESCALATED))

        # Step 1.5: Collect metrics timeline (Detection baseline vs Current state)
        detection_metrics = None
        current_metrics = None
        if self._metrics_service and existing:
            detection_metrics = existing.metrics
            effective_fn = function_name or build_function_name(service, stage)
            try:
                current_metrics = self._metrics_service.collect_incident_metrics(
                    incident_key=incident_key,
                    function_name=effective_fn,
                    alarm_name=alarm_name,
                    lookback_minutes=15,
                    force_refresh=True,
                )
            except Exception:
                pass

        # Step 2: Collect diagnostic data
        effective_fn = function_name or build_function_name(service, stage)
        log_group = f"/aws/lambda/{effective_fn}"
        error_logs = self._log_analysis.collect_diagnostics(log_group)

        # Step 3: AI log analysis (optional — graceful degradation)
        ai_analysis = None
        ai_references = []
        if self._ai_service:
            try:
                ai_result = self._ai_service.analyze_for_escalation(
                    error_logs=error_logs,
                    service=service,
                    stage=stage,
                    function_name=effective_fn,
                    service_type=service_type,
                    alarm_type=alarm_type,
                    reason=reason,
                    root_cause=root_cause,
                    confidence=confidence,
                    remediation_outcome=remediation_outcome,
                    verification=verification,
                    log_analysis=log_analysis,
                    detection_metrics=detection_metrics,
                    current_metrics=current_metrics,
                )
                if ai_result:
                    ai_analysis = ai_result["text"]
                    ai_references = ai_result.get("references", [])

                    # Synthesize better root cause from AI if original is "unknown"
                    if root_cause == "unknown" and ai_analysis:
                        # Extract "Root Cause:" line from AI analysis
                        for line in ai_analysis.split("\n"):
                            if line.startswith("**Root Cause**:"):
                                synthesized = line.replace("**Root Cause**:", "").strip()
                                # Remove markdown formatting and take first sentence
                                synthesized = synthesized.replace("**", "").split(". ")[0]
                                if synthesized and len(synthesized) > 10:
                                    root_cause = synthesized[:150]  # Limit length
                                break
            except Exception:
                logger.warning("AI analysis failed, continuing without AI insights")

        # Step 4: Build ADF-formatted Jira comment
        adf_content = build_escalation_adf(
            incident_key=incident_key,
            service=service,
            stage=stage,
            severity=severity,
            reason=reason,
            function_name=effective_fn,
            log_group=log_group,
            error_logs=error_logs,
            verification=verification,
            root_cause=root_cause,
            timestamp=utc_timestamp(now),
            ai_analysis=ai_analysis,
            ai_references=ai_references,
            region=self._region,
            detection_metrics=detection_metrics,
            current_metrics=current_metrics,
        )
        self._ticketing.add_jira_comment_adf(jira_ticket_id, adf_content)

        # Step 5: Attach error logs as file
        if error_logs:
            self._ticketing.attach_jira_file(
                jira_ticket_id,
                f"error-logs-{incident_key}.txt",
                LogAnalysisService.format_log_attachment(error_logs),
            )

        # Step 6: Delta report for checkpoint-aware recovery models
        if recovery_model == "reprocess" and self._delta_report:
            try:
                result = self._delta_report.generate_and_post(
                    service_name=service, jira_ticket_id=jira_ticket_id,
                )
                logger.info(
                    "Delta report generated",
                    extra={
                        "checkpoints_found": result.get("checkpoints_found", 0),
                        "total_pending": result.get("total_pending", 0),
                    },
                )
            except Exception:
                logger.warning("Delta report generation failed", exc_info=True)

        # Step 7: Notify engineer (SEV-1/SEV-2 only)
        if severity in ("SEV-1", "SEV-2") and self._notification_topic_arn:
            message = build_notification_message(
                incident_key=incident_key,
                jira_ticket_id=jira_ticket_id,
                severity=severity,
                reason=reason,
                service=service,
                stage=stage,
            )
            self._notification.notify_engineer(
                self._notification_topic_arn, message, severity
            )

        return "escalated"
