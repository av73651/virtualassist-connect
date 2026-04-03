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
        references: list[dict] | None = None,
        metrics: dict | None = None,
    ) -> None:
        # Core classification info — synthesize better root cause if "unknown"
        if root_cause == "unknown" and log_analysis:
            # Extract first sentence of log_analysis as synthesized root cause
            synthesized = log_analysis.split(". ")[0] if ". " in log_analysis else log_analysis[:100]
            parts = [f"Root cause classified as {root_cause} ({confidence}). {synthesized}."]
        else:
            parts = [f"Root cause classified as {root_cause} ({confidence})."]

        # Alarm datapoints evidence (THE KEY DIAGNOSTIC)
        if metrics:
            alarm_metrics = metrics.get("alarm_metrics", {})
            datapoints = alarm_metrics.get("datapoints", [])
            alarm_config = alarm_metrics.get("alarm_config", {})

            # Always show alarm config, even with zero datapoints (indicates WHY no data)
            if alarm_config:
                metric_name = alarm_config.get("metric_name", "value").lower()
                threshold = alarm_config.get("threshold", 0.0)
                comparison_op = alarm_config.get("comparison_operator", "")
                eval_periods = alarm_config.get("evaluation_periods", 0)
                datapoints_to_alarm = alarm_config.get("datapoints_to_alarm", 0)

                if datapoints:
                    # Format last 10 datapoints for visibility
                    recent = datapoints[-10:]
                    datapoint_lines = "\n".join(
                        f"  {dp['timestamp'][11:16]} {metric_name}={int(dp['value'])}"
                        for dp in recent
                    )
                    parts.append(
                        f"\nAlarm Evidence (last {len(recent)} datapoints):\n{datapoint_lines}\n"
                        f"Threshold: {threshold} ({comparison_op})\n"
                        f"Evaluation: {datapoints_to_alarm}/{eval_periods} datapoints"
                    )
                else:
                    # No datapoints = new alarm OR metric lag OR alarm misconfiguration
                    parts.append(
                        f"\nAlarm Configuration:\n"
                        f"Threshold: {threshold} ({comparison_op})\n"
                        f"Evaluation: {datapoints_to_alarm}/{eval_periods} datapoints\n"
                        f"Datapoints: 0 collected (new alarm, metric lag, or misconfiguration)"
                    )

        # Blast radius — heuristic assessment
        parts.append(
            f"Blast radius: {blast_radius.get('affected_users', 'unknown')} users, "
            f"{blast_radius.get('error_rate', 'unknown')} error rate, "
            f"duration: {blast_radius.get('duration', 'unknown')}."
        )

        parts.append(f"Evidence: {evidence}")

        # AI-enriched fields
        if log_analysis:
            parts.append(f"\nLog Analysis: {log_analysis}")
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

    @observe(operation="report_deployment_correlation", metric_prefix="reporter")
    def report_deployment_correlation(
        self, jira_ticket_id: str, deployment_version: str, delta_minutes: int, trend: str
    ) -> None:
        self._ticketing.add_jira_comment(
            jira_ticket_id,
            f"Deployment correlation detected (high confidence). "
            f"Version {deployment_version} deployed {delta_minutes} minutes before alarm. "
            f"Error rate trend: {trend}. Consider rollback.",
        )

    @observe(operation="report_alarm_misconfiguration", metric_prefix="reporter")
    def report_alarm_misconfiguration(
        self, jira_ticket_id: str, alarm_name: str, threshold: float, current_value: float
    ) -> None:
        self._ticketing.add_jira_comment(
            jira_ticket_id,
            f"Alarm threshold validation failed. "
            f"Alarm: {alarm_name}, Threshold: {threshold}, Current: {current_value}. "
            f"Alarm may be misconfigured or metric lag detected.",
        )

    @observe(operation="report_trend_analysis", metric_prefix="reporter")
    def report_trend_analysis(
        self, jira_ticket_id: str, trend: str, interpretation: str
    ) -> None:
        self._ticketing.add_jira_comment(
            jira_ticket_id,
            f"Error rate trend: {trend}. {interpretation}",
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

    @observe(operation="report_diagnostics", metric_prefix="reporter")
    def report_diagnostics(
        self, jira_ticket_id: str, function_name: str, log_group: str,
        service: str, stage: str, error_count: int = 0,
    ) -> None:
        """Add diagnostics section with function, log group, links, CLI commands."""
        region = "us-west-2"
        log_group_encoded = log_group.replace("/", "$252F")
        cw_logs_url = f"https://console.aws.amazon.com/cloudwatch/home?region={region}#logsV2:log-groups/log-group/{log_group_encoded}"
        lambda_url = f"https://console.aws.amazon.com/lambda/home?region={region}#/functions/{function_name}"

        diagnostics = f"""Diagnostics
Function: {function_name}
Log Group: {log_group}
Error Count: {error_count}

Useful Links
CloudWatch Logs  |  Lambda Function

CLI Commands
```
# Tail recent logs
aws logs tail {log_group} --since 15m --follow
# Check alarm state
aws cloudwatch describe-alarms --alarm-names "{service}-high-*-{stage}" --query 'MetricAlarms[].{{Name:AlarmName,State:StateValue}}'
# Check Lambda errors
aws lambda get-function --function-name {function_name} --query 'Configuration.{{State:State,LastModified:LastModified}}'
```"""
        self._ticketing.add_jira_comment(jira_ticket_id, diagnostics)

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
