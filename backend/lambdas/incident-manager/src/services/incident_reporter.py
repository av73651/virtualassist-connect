"""IncidentReporter — all Jira ticket interactions during incident lifecycle.

Owns formatting and posting of every Jira comment, transition, and attachment
during triage, remediation, and recovery. The orchestrator passes results,
the reporter decides how to format and post.

All observability concerns (tracing, metrics, logging) handled by @observe decorator."""

from shared.middleware.observability import observe

from src.models.config import IncidentConfig


class IncidentReporter:
    """Jira ticket updates for the incident lifecycle."""

    def __init__(self, ticketing_repo, config: IncidentConfig):
        self._ticketing = ticketing_repo
        self._config = config

    # ------------------------------------------------------------------ #
    # Triage phase
    # ------------------------------------------------------------------ #

    @observe(operation="report_triage_started", metric_prefix="reporter")
    def report_triage_started(self, jira_ticket_id: str, incident_key: str) -> None:
        self._ticketing.transition_jira_ticket(
            jira_ticket_id, self._config.jira_transition_investigate
        )
        self._ticketing.add_jira_comment(
            jira_ticket_id,
            f"Triage started for {incident_key}. Analyzing logs and collecting error data.",
        )

    @observe(operation="report_analysis_results", metric_prefix="reporter")
    def report_analysis_results(
        self,
        jira_ticket_id: str,
        root_cause: str,
        confidence: str,
        evidence: str,
        blast_radius: dict,
        log_analysis: str | None = None,
        verification_guidance: str | None = None,
        references: list[dict] | None = None,
    ) -> None:
        # Core classification info
        parts = [
            f"Root cause classified as {root_cause} ({confidence}).",
        ]

        # Blast radius — AI or heuristic
        if blast_radius.get("source") == "ai":
            parts.append(f"Blast radius (AI): {blast_radius.get('ai_assessment', 'unknown')}.")
        else:
            parts.append(
                f"Blast radius: {blast_radius.get('affected_users', 'unknown')} users, "
                f"{blast_radius.get('error_rate', 'unknown')} error rate, "
                f"duration: {blast_radius.get('duration', 'unknown')}."
            )

        parts.append(f"Evidence: {evidence}")

        # AI-enriched fields
        if log_analysis:
            parts.append(f"\nLog Analysis: {log_analysis}")
        if verification_guidance:
            parts.append(f"\nVerification Guidance: {verification_guidance}")
        if references:
            ref_lines = ", ".join(ref.get("source", "") for ref in references)
            parts.append(f"\nKB References: {ref_lines}")

        self._ticketing.add_jira_comment(jira_ticket_id, " ".join(parts))

    @observe(operation="report_storm_detected", metric_prefix="reporter")
    def report_storm_detected(self, jira_ticket_id: str) -> None:
        self._ticketing.add_jira_comment(
            jira_ticket_id,
            "Incident storm detected. Skipping automated remediation. Escalating to on-call engineer.",
        )

    @observe(operation="report_remediation_unavailable", metric_prefix="reporter")
    def report_remediation_unavailable(self, jira_ticket_id: str, root_cause: str) -> None:
        self._ticketing.add_jira_comment(
            jira_ticket_id,
            f"No remediation available for root cause: {root_cause}. Escalating.",
        )

    @observe(operation="report_remediation_failed", metric_prefix="reporter")
    def report_remediation_failed(self, jira_ticket_id: str, root_cause: str) -> None:
        self._ticketing.add_jira_comment(
            jira_ticket_id,
            f"Remediation action failed for root cause: {root_cause}. Escalating.",
        )

    @observe(operation="report_verification_failed", metric_prefix="reporter")
    def report_verification_failed(self, jira_ticket_id: str, verification: dict) -> None:
        self._ticketing.add_jira_comment(
            jira_ticket_id,
            f"Verification failed: alarm_ok={verification.get('alarm_ok')}, "
            f"health_ok={verification.get('health_ok')}, "
            f"error_rate_ok={verification.get('error_rate_ok')}. Escalating.",
        )

    @observe(operation="report_auto_resolved", metric_prefix="reporter")
    def report_auto_resolved(self, jira_ticket_id: str) -> None:
        self._ticketing.add_jira_comment(
            jira_ticket_id,
            "All verification checks passed. Incident auto-resolved.",
        )

    # ------------------------------------------------------------------ #
    # Recovery phase
    # ------------------------------------------------------------------ #

    @observe(operation="report_recovery_status", metric_prefix="reporter")
    def report_recovery_status(
        self, jira_ticket_id: str, recovery_status: str, detail: str = ""
    ) -> None:
        if detail:
            self._ticketing.add_jira_comment(jira_ticket_id, detail)

    # ------------------------------------------------------------------ #
    # Detection phase (duplicate/grace/recovery notifications)
    # ------------------------------------------------------------------ #

    @observe(operation="report_duplicate_alarm", metric_prefix="reporter")
    def report_duplicate_alarm(self, jira_ticket_id: str, incident_key: str) -> None:
        self._ticketing.add_jira_comment(
            jira_ticket_id,
            f"Duplicate alarm received for {incident_key}. "
            f"Existing incident already being processed.",
        )

    @observe(operation="report_grace_recurrence", metric_prefix="reporter")
    def report_grace_recurrence(self, jira_ticket_id: str) -> None:
        self._ticketing.add_jira_comment(
            jira_ticket_id,
            "Incident recurred after auto-remediation. Escalating.",
        )

    @observe(operation="report_alarm_recovered", metric_prefix="reporter")
    def report_alarm_recovered(
        self, jira_ticket_id: str, alarm_state: str,
        recovery_timestamp: str, log_count: int,
    ) -> None:
        self._ticketing.add_jira_comment(
            jira_ticket_id,
            f"Alarm recovered (state: {alarm_state}). "
            f"Recovery timestamp: {recovery_timestamp}. "
            f"Collected {log_count} recovery log entries.",
        )

    @observe(operation="attach_log_file", metric_prefix="reporter")
    def attach_log_file(
        self, jira_ticket_id: str, filename: str, content: str,
    ) -> None:
        self._ticketing.attach_jira_file(jira_ticket_id, filename, content)

    # ------------------------------------------------------------------ #
    # Resolution
    # ------------------------------------------------------------------ #

    @observe(operation="report_resolution_summary", metric_prefix="reporter")
    def report_resolution_summary(
        self, jira_ticket_id: str, summary: str, references: list[dict] | None = None,
    ) -> None:
        parts = [f"Post-Incident Summary (AI-generated):\n{summary}"]
        if references:
            ref_lines = ", ".join(ref.get("source", "") for ref in references)
            parts.append(f"\nKB References: {ref_lines}")
        self._ticketing.add_jira_comment(jira_ticket_id, "\n".join(parts))

    @observe(operation="resolve_ticket", metric_prefix="reporter")
    def resolve_ticket(self, jira_ticket_id: str) -> None:
        self._ticketing.transition_jira_ticket(
            jira_ticket_id, self._config.jira_transition_resolve
        )
