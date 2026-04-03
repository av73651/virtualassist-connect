"""TriageService — incident triage workflow orchestrator (Leg 2).

Manages the incident workflow: analyze -> classify -> decide -> delegate.
All execution (log analysis, remediation, verification, recovery, Jira updates)
is delegated to specialized services.

All observability concerns (tracing, metrics, logging) handled by @observe decorator."""

import logging
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

from shared.middleware.observability import observe

from src.domain.aws_resource_ids import build_log_group, build_function_name, derive_alarm_type, derive_alarm_name
from src.models.config import IncidentConfig
from src.models.enums import CorrelationStatus, EscalationReason, ResolutionOutcome
from src.models.timestamps import utc_timestamp


class TriageService:
    """Leg 2: Workflow orchestrator — analyze -> classify -> remediate-or-escalate."""

    def __init__(
        self,
        correlation_repo,
        event_bus_repo,
        config: IncidentConfig,
        log_analysis_service,
        ai_service,
        resolution_service,
        incident_reporter,
    ):
        self._correlation = correlation_repo
        self._event_bus = event_bus_repo
        self._config = config
        self._log_analysis = log_analysis_service
        self._ai_service = ai_service
        self._resolution = resolution_service
        self._reporter = incident_reporter

    @observe(operation="triage_incident", metric_prefix="triage")
    def triage(
        self,
        incident_key: str,
        jira_ticket_id: str,
        service: str,
        stage: str,
        severity: str,
        service_type: str = "lambda",
        storm_detected: bool = False,
        recovery_model: str = "stateless",
        alarm_name: str = "",
        function_name: str = "",
        log_group: str = "",
        metric_name: str = "",
        metrics: dict | None = None,
    ) -> str:
        """Main entry point. Returns 'auto-resolved' or 'escalated'.

        Flow:
        1. Update DynamoDB -> TRIAGING
        2. Report triage started
        3. Analyze logs -> classify root cause -> assess blast radius
        4. Report analysis results
        4.5. Apply metrics-based escalation rules (Phase 2)
        5. Storm/timeout gates -> escalate if triggered
        6. Delegate remediation + verification -> escalate on failure
        7. Resolve: report + close ticket + GRACE + recovery + publish event"""
        now = datetime.now(timezone.utc)
        triage_start = time.time()
        effective_fn = function_name or build_function_name(service, stage)
        alarm_type = derive_alarm_type(alarm_name)

        escalation_base = {
            "incident_key": incident_key,
            "jira_ticket_id": jira_ticket_id,
            "service": service,
            "stage": stage,
            "severity": severity,
            "recovery_model": recovery_model,
            "timestamp": utc_timestamp(now),
        }

        # Step 1: Update DynamoDB -> TRIAGING
        existing = self._correlation.get(incident_key)
        if existing:
            self._correlation.update(existing.to_status(CorrelationStatus.TRIAGING))

        # Step 2: Report triage started
        self._reporter.report_triage_started(jira_ticket_id, incident_key)

        # Step 3: Analyze -> classify -> assess
        effective_log_group = log_group or build_log_group(service, stage)
        error_data = self._log_analysis.analyze_errors(effective_log_group)

        # Build service architecture context from registry
        service_context = self._build_service_context(service)

        classification_result = self._classify_root_cause(
            error_data,
            service_type=service_type,
            alarm_type=alarm_type,
            resource_identifier=effective_fn,
            stage=stage,
            service_context=service_context,
            metric_name=metric_name,
            metrics=metrics,
        )

        root_cause = classification_result["root_cause"]
        confidence = classification_result["confidence"]
        evidence = classification_result["evidence"]

        # Blast radius: use heuristic assessment (detailed analysis in escalation)
        blast_radius = self._assess_blast_radius(error_data)

        # Step 4: Report analysis results
        self._reporter.report_analysis_results(
            jira_ticket_id, root_cause, confidence, evidence, blast_radius,
            log_analysis=classification_result.get("log_analysis"),
            references=classification_result.get("references", []),
            metrics=metrics,
        )

        # Step 4a: Escalation validation - don't escalate false positives
        error_count = error_data.get("error_count", 0)
        if error_count == 0 and confidence == "low":
            # False positive: no errors + low confidence classification
            # Mark for monitoring instead of escalating
            existing = self._correlation.get(incident_key)
            if existing:
                monitored = existing.to_status(CorrelationStatus.GRACE)
                self._correlation.update(monitored)

            # Add diagnostics for monitoring decision
            self._reporter.report_diagnostics(
                jira_ticket_id,
                function_name=effective_fn,
                log_group=effective_log_group,
                service=service,
                stage=stage,
                error_count=error_count,
            )

            self._reporter.report_resolution_summary(
                jira_ticket_id,
                "Incident marked for monitoring. No errors detected and classification confidence is low. "
                "Metric lag, alarm misconfiguration, or transient spike that self-resolved. "
                "System will continue monitoring. If alarm persists or errors appear, incident will be reopened.",
            )
            return "monitoring"

        # Build enriched escalation context
        effective_alarm = alarm_name or derive_alarm_name(incident_key)
        escalation_context = {
            "root_cause": root_cause,
            "confidence": confidence,
            "service_type": service_type,
            "alarm_type": alarm_type,
            "function_name": effective_fn,
            "alarm_name": effective_alarm,
            "log_analysis": classification_result.get("log_analysis", ""),
        }

        # Step 4.5: Metrics-based escalation rules (Phase 2)
        if metrics:
            enrichment = metrics.get("enrichment", {})

            # Rule MER-1: Recent deployment with high error correlation
            if enrichment.get("deployment_correlation") == "high":
                deployment_version = enrichment.get("recent_deployment_version")
                delta_min = enrichment.get("deployment_time_delta_minutes", 0)

                self._reporter.report_deployment_correlation(
                    jira_ticket_id,
                    deployment_version,
                    delta_min,
                    enrichment.get("error_rate_trend"),
                )

                return self._escalate(
                    escalation_base,
                    EscalationReason.RECENT_DEPLOYMENT,
                    remediation_outcome="not-attempted",
                    deployment_version=deployment_version,
                    deployment_delta_minutes=delta_min,
                    **escalation_context,
                )

            # Rule MER-2: Alarm threshold NOT exceeded (false alarm / metric lag)
            if not enrichment.get("alarm_threshold_exceeded"):
                threshold = enrichment.get("alarm_threshold_value", 0.0)
                current = enrichment.get("current_metric_value", 0.0)

                self._reporter.report_alarm_misconfiguration(
                    jira_ticket_id,
                    alarm_name or derive_alarm_name(incident_key),
                    threshold,
                    current,
                )

                return self._escalate(
                    escalation_base,
                    EscalationReason.ALARM_MISCONFIGURATION,
                    remediation_outcome="not-attempted",
                    alarm_threshold=threshold,
                    current_metric_value=current,
                    **escalation_context,
                )

            # Trend flag: Error rate decreasing (self-healing observed)
            if enrichment.get("error_rate_trend") == "decreasing":
                self._reporter.report_trend_analysis(
                    jira_ticket_id,
                    "decreasing",
                    "System appears to be self-healing. Monitoring remediation urgency.",
                )

        # Step 5a: Storm override -> escalate
        if storm_detected:
            self._reporter.report_storm_detected(jira_ticket_id)
            return self._escalate(
                escalation_base, EscalationReason.INCIDENT_STORM,
                remediation_outcome="not-attempted", **escalation_context,
            )

        # Step 5b: Timeout check -> escalate
        if time.time() - triage_start > self._config.triage_timeout_seconds:
            return self._escalate(
                escalation_base, EscalationReason.TRIAGE_TIMEOUT,
                remediation_outcome="not-attempted", **escalation_context,
            )

        # Step 6: Remediate + verify
        wait_seconds = self._config.verification_wait_seconds.get(severity, 60)

        ai_recommended_action = classification_result.get("recommended_action")
        automation_level = classification_result.get("automation_level", "manual")

        outcome, verification = self._resolution.remediate_and_verify(
            service_type=service_type,
            root_cause=root_cause,
            resource_context={
                "function_name": effective_fn,
                "service": service,
                "stage": stage,
            },
            alarm_name=effective_alarm,
            log_group=effective_log_group,
            wait_seconds=wait_seconds,
            ai_recommended_action=ai_recommended_action if automation_level == "auto" else None,
        )

        if outcome == ResolutionOutcome.NO_REMEDIATION:
            self._reporter.report_remediation_unavailable(jira_ticket_id, root_cause)
            return self._escalate(
                escalation_base, EscalationReason.NO_REMEDIATION,
                remediation_outcome=outcome, **escalation_context,
            )

        if outcome == ResolutionOutcome.REMEDIATION_FAILED:
            self._reporter.report_remediation_failed(jira_ticket_id, root_cause)
            return self._escalate(
                escalation_base, EscalationReason.REMEDIATION_FAILED,
                remediation_outcome=outcome, **escalation_context,
            )

        if outcome == ResolutionOutcome.VERIFICATION_FAILED:
            self._reporter.report_verification_failed(jira_ticket_id, verification)
            return self._escalate(
                escalation_base, EscalationReason.VERIFICATION_FAILED,
                verification=verification, remediation_outcome=outcome,
                **escalation_context,
            )

        # Step 7: All checks passed — resolve
        self._reporter.report_auto_resolved(jira_ticket_id)
        self._reporter.resolve_ticket(jira_ticket_id)

        # Step 7b: Post-resolution AI summary (optional)
        if self._ai_service:
            summary_result = self._ai_service.generate_resolution_summary(
                service=service,
                stage=stage,
                service_type=service_type,
                root_cause=root_cause,
                confidence=confidence,
                remediation_action=ai_recommended_action or "catalog-action",
                recovery_model=recovery_model,
                alarm_type=alarm_type,
                error_data=error_data,
                log_analysis=classification_result.get("log_analysis", ""),
            )
            if summary_result:
                self._reporter.report_resolution_summary(
                    jira_ticket_id,
                    summary_result["text"],
                    references=summary_result.get("references", []),
                )

        if existing:
            self._correlation.update(
                existing.to_grace(now, self._config.grace_period_seconds)
            )

        # Step 8: Self-healing recovery
        recovery_status, recovery_detail = self._resolution.trigger_recovery(
            recovery_model, incident_key, jira_ticket_id, severity,
            service_name=service,
        )
        self._reporter.report_recovery_status(jira_ticket_id, recovery_status, recovery_detail)

        # Step 9: Publish IncidentAutoResolved
        self._event_bus.publish_event(
            "IncidentAutoResolved",
            {
                "incident_key": incident_key,
                "jira_ticket_id": jira_ticket_id,
                "service": service,
                "stage": stage,
                "severity": severity,
                "recovery_model": recovery_model,
                "recovery_status": recovery_status,
                "root_cause": root_cause,
                "timestamp": utc_timestamp(now),
            },
        )

        return "auto-resolved"

    # ------------------------------------------------------------------ #
    # Escalation helper
    # ------------------------------------------------------------------ #

    def _escalate(self, base: dict, reason: str, **extra) -> str:
        """Publishes EscalationRequired event and returns 'escalated'."""
        self._event_bus.publish_event(
            "EscalationRequired", {**base, "reason": reason, **extra}
        )
        return "escalated"

    # ------------------------------------------------------------------ #
    # Classification (AI-first, rule-based fallback)
    # ------------------------------------------------------------------ #

    @observe(operation="classify_root_cause", metric_prefix="triage_classify")
    def _classify_root_cause(
        self,
        error_data: dict,
        service_type: str = "lambda",
        alarm_type: str = "",
        resource_identifier: str = "",
        stage: str = "",
        service_context: str = "",
        metric_name: str = "",
        metrics: dict | None = None,
    ) -> dict:
        """Classify root cause: AI service first, then rule-based fallback.

        Returns dict with root_cause, confidence, evidence, and optional AI fields."""
        if self._ai_service is not None:
            try:
                result = self._ai_service.classify_incident(
                    error_data, service_type, alarm_type, resource_identifier, stage,
                    service_context=service_context,
                    metric_name=metric_name,
                    metrics=metrics,
                )
                if result is not None:
                    return {
                        "root_cause": result["classification"],
                        "confidence": result["confidence"],
                        "evidence": result.get("reasoning", "AI-classified"),
                        "recommended_action": result.get("recommended_action"),
                        "automation_level": result.get("automation_level"),
                        "log_analysis": result.get("log_analysis"),
                        "references": result.get("references", []),
                    }
            except Exception:
                logger.warning("AI classification failed, falling back to rule-based")

        root_cause, confidence, evidence = self._classify_root_cause_rules(error_data)
        return {
            "root_cause": root_cause,
            "confidence": confidence,
            "evidence": evidence,
            "recommended_action": None,
            "automation_level": None,
            "log_analysis": None,
            "references": [],
        }

    def _classify_root_cause_rules(self, error_data: dict) -> tuple[str, str, str]:
        """Rule-based classification using classification_rules from config."""
        patterns = error_data.get("error_patterns", {})
        error_count = error_data.get("error_count", 0)
        unique_errors = error_data.get("unique_errors", 0)

        top_errors = sorted(patterns.items(), key=lambda x: x[1], reverse=True)[:3]
        evidence = "; ".join(f"{pat[:50]}({cnt})" for pat, cnt in top_errors)

        # Pre-compute once for all rule checks
        all_messages = " ".join(error_data.get("sample_payloads", [])).lower()

        for rule in self._config.classification_rules:
            if self._matches_pattern(rule["pattern"], error_data, all_messages):
                return (rule["classification"], rule["confidence"], evidence)

        if error_count > 0 and unique_errors == 1:
            return ("specific-bug", "medium", evidence)

        return ("unknown", "low", evidence or "no-errors-found")

    @staticmethod
    def _matches_pattern(pattern_name: str, error_data: dict, all_messages: str) -> bool:
        """Checks if error data matches a named pattern from classification_rules."""
        patterns = error_data.get("error_patterns", {})
        error_count = error_data.get("error_count", 0)
        unique_errors = error_data.get("unique_errors", 0)

        if pattern_name == "import_or_syntax_error":
            return any(
                kw in all_messages
                for kw in ["importerror", "syntaxerror", "modulenotfounderror"]
            )

        if pattern_name == "timeout_errors":
            return any(
                kw in all_messages
                for kw in ["readtimeout", "connectiontimeout", "timed out", "timeout", "downstream", "unreachable"]
            )

        if pattern_name == "single_error_dominant":
            if unique_errors == 1 and error_count > 5:
                return True
            if unique_errors > 0:
                top_count = max(patterns.values()) if patterns else 0
                return top_count > error_count * 0.8
            return False

        if pattern_name == "throttling_errors":
            return any(kw in all_messages for kw in ["throttl", "rate exceeded", "too many requests"])

        if pattern_name == "auth_errors":
            return any(kw in all_messages for kw in ["unauthorized", "forbidden", "accessdenied", "auth"])

        if pattern_name == "high_latency_no_errors":
            return error_count == 0

        if pattern_name == "mixed_errors_recent_deploy":
            return unique_errors > 3 and error_count > 10

        if pattern_name == "spike_then_stable":
            return error_count > 0 and error_count < 5

        if pattern_name == "throttling_with_concurrency":
            return any(kw in all_messages for kw in ["concurrency", "reserved"]) and any(
                kw in all_messages for kw in ["throttl"]
            )

        if pattern_name == "dynamo_throttle_pattern":
            return any(
                kw in all_messages
                for kw in ["provisionedthroughputexceeded", "dynamodb", "throttl"]
            )

        if pattern_name == "traffic_drop":
            return error_count == 0

        if pattern_name == "cold_start_spike":
            return any(kw in all_messages for kw in ["cold start", "init duration"])

        return False

    # ------------------------------------------------------------------ #
    # Service context builder
    # ------------------------------------------------------------------ #

    def _build_service_context(self, service: str) -> str:
        """Build human-readable service architecture context from registry.

        Returns formatted string for AI prompt, or empty string if service unknown."""
        registry = self._config.service_registry
        entry = registry.get(service)
        if not entry:
            return ""

        lines = [
            f"Service: {service} — {entry.get('description', 'unknown')}",
            f"Architecture: {entry.get('service_type', 'unknown')} / {entry.get('trigger_type', 'unknown')}",
            f"Processing model: {entry.get('processing_model', 'unknown')}",
        ]
        if entry.get("data_sources"):
            lines.append(f"Data sources: {', '.join(entry['data_sources'])}")
        if entry.get("downstream"):
            lines.append(f"Downstream: {', '.join(entry['downstream'])}")
        if entry.get("critical_modules"):
            lines.append(f"Critical modules: {', '.join(entry['critical_modules'])}")
        if entry.get("known_failure_modes"):
            lines.append("Known failure modes:")
            for mode in entry["known_failure_modes"]:
                lines.append(f"  - {mode}")

        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Blast radius assessment (pure logic)
    # ------------------------------------------------------------------ #

    @observe(operation="assess_blast_radius", metric_prefix="triage_blast")
    def _assess_blast_radius(self, error_data: dict) -> dict:
        """Estimates impact from error data."""
        error_count = error_data.get("error_count", 0)
        patterns = error_data.get("error_patterns", {})

        if error_count > 100:
            affected_users = f"~{error_count * 2} estimated"
        elif error_count > 10:
            affected_users = f"~{error_count * 5} estimated"
        else:
            affected_users = "< 50 estimated"

        error_rate = f"{min(error_count, 100)}% of requests" if error_count > 0 else "0%"

        return {
            "affected_users": affected_users,
            "error_rate": error_rate,
            "affected_operations": list(patterns.keys())[:5],
            "duration": f"{self._config.log_analysis_window_minutes}min window",
        }
