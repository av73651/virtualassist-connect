"""Formatting and presentation logic for incident management.

Pure functions — no I/O, no external dependencies. Used by services to build
Jira tickets, ADF comments, and SNS notification messages.

ADF = Atlassian Document Format (Jira's rich-text JSON schema)."""

from src.models.alarm_event import AlarmEvent
from src.models.config import IncidentConfig
from src.models.enums import EscalationReason


# ------------------------------------------------------------------ #
# ADF (Atlassian Document Format) node builders
# ------------------------------------------------------------------ #

def adf_heading(level: int, text: str) -> dict:
    """ADF heading node."""
    return {"type": "heading", "attrs": {"level": level}, "content": [{"type": "text", "text": text}]}


def adf_text(text: str, bold: bool = False) -> dict:
    """ADF inline text node, optionally bold."""
    node = {"type": "text", "text": text}
    if bold:
        node["marks"] = [{"type": "strong"}]
    return node


def adf_link(text: str, href: str) -> dict:
    """ADF inline link node — renders as clickable link in Jira."""
    return {"type": "text", "text": text, "marks": [{"type": "link", "attrs": {"href": href}}]}


def adf_paragraph(*nodes) -> dict:
    """ADF paragraph wrapping inline nodes."""
    return {"type": "paragraph", "content": list(nodes)}


def adf_code_block(text: str, language: str = "bash") -> dict:
    """ADF code block with syntax highlighting."""
    return {"type": "codeBlock", "attrs": {"language": language}, "content": [{"type": "text", "text": text}]}


def adf_rule() -> dict:
    """ADF horizontal rule (divider)."""
    return {"type": "rule"}


# ------------------------------------------------------------------ #
# Reason-specific messaging for escalation
# ------------------------------------------------------------------ #

REASON_CONTEXT = {
    EscalationReason.VERIFICATION_FAILED: "Automated remediation was attempted but post-remediation verification failed. The service may still be degraded.",
    EscalationReason.NO_REMEDIATION: "No automated remediation exists for the identified root cause. Manual intervention is required.",
    EscalationReason.REMEDIATION_FAILED: "Automated remediation was attempted but the action itself failed. Manual intervention is required.",
    EscalationReason.INCIDENT_STORM: "Multiple incidents detected simultaneously. Automated remediation was disabled to prevent cascading actions.",
    EscalationReason.GRACE_RECURRENCE: "This alarm fired again within the grace period after a previous auto-resolution. The original fix may not have been effective.",
    EscalationReason.TRIAGE_TIMEOUT: "Automated triage exceeded the allowed time. Analysis results are preserved in the comments above.",
}


# ------------------------------------------------------------------ #
# Error pattern grouping
# ------------------------------------------------------------------ #

def group_error_patterns(
    error_logs: list[dict],
    truncate_length: int = 200,
    max_samples: int = 3,
    sample_truncate_length: int | None = None,
) -> tuple[dict[str, int], list[str]]:
    """Group error log messages by truncated pattern, return (pattern_counts, samples).

    sample_truncate_length defaults to truncate_length when not provided."""
    sample_max = sample_truncate_length if sample_truncate_length is not None else truncate_length
    patterns: dict[str, int] = {}
    samples: list[str] = []
    for e in error_logs:
        msg = e.get("@message", e.get("message", ""))
        truncated = msg[:truncate_length] if msg else "unknown"
        patterns[truncated] = patterns.get(truncated, 0) + 1
        if len(samples) < max_samples:
            samples.append(msg[:sample_max] if msg else "unknown")
    return patterns, samples


# ------------------------------------------------------------------ #
# Jira ticket formatting (detection)
# ------------------------------------------------------------------ #

def format_ticket_summary(alarm_event: AlarmEvent) -> str:
    """Builds Jira ticket summary line from alarm event."""
    severity = alarm_event.severity.value
    return (
        f"[{severity}] {alarm_event.service} ({alarm_event.stage}): "
        f"{alarm_event.alarm_description}"
    )


def format_ticket_description(alarm_event: AlarmEvent) -> str:
    """Builds Jira ticket description from alarm event."""
    severity = alarm_event.severity.value
    return (
        f"Incident detected. Automated triage in progress.\n\n"
        f"Service: {alarm_event.service}\n"
        f"Stage: {alarm_event.stage}\n"
        f"Severity: {severity}\n"
        f"Recovery Model: {alarm_event.recovery_model}\n"
        f"Alarm: {alarm_event.alarm_name}\n"
        f"Reason: {alarm_event.reason}\n"
        f"Time: {alarm_event.state_change_time.isoformat()}"
    )


def build_ticket_labels(config: IncidentConfig, alarm_event: AlarmEvent) -> list[str]:
    """Builds Jira ticket labels from config prefix + alarm metadata."""
    return list(config.jira_labels_prefix) + [alarm_event.service, alarm_event.stage]


# ------------------------------------------------------------------ #
# Escalation ADF comment
# ------------------------------------------------------------------ #

def build_escalation_adf(
    incident_key: str,
    service: str,
    stage: str,
    severity: str,
    reason: str,
    function_name: str,
    log_group: str,
    error_logs: list[dict],
    verification: dict | None,
    root_cause: str,
    timestamp: str,
    ai_analysis: str | None = None,
    ai_references: list[dict] | None = None,
    region: str = "us-west-2",
) -> list[dict]:
    """Builds ADF content blocks for rich Jira escalation comment.

    Returns list of ADF block nodes with headings, clickable links,
    code blocks, and optional AI analysis section."""
    log_group_encoded = log_group.replace("/", "$252F")
    cw_logs_url = f"https://console.aws.amazon.com/cloudwatch/home?region={region}#logsV2:log-groups/log-group/{log_group_encoded}"
    lambda_url = f"https://console.aws.amazon.com/lambda/home?region={region}#/functions/{function_name}"

    reason_text = REASON_CONTEXT.get(reason, f"Escalation reason: {reason}")

    blocks: list[dict] = []

    # --- Escalation header ---
    blocks.append(adf_heading(2, f"Escalation — {severity}"))
    blocks.append(adf_paragraph(
        adf_text("Severity: ", bold=True), adf_text(f"{severity}  |  "),
        adf_text("Reason: ", bold=True), adf_text(f"{reason}  |  "),
        adf_text("Time: ", bold=True), adf_text(timestamp),
    ))
    blocks.append(adf_paragraph(adf_text(reason_text)))

    if root_cause:
        blocks.append(adf_paragraph(
            adf_text("Root Cause: ", bold=True), adf_text(root_cause),
        ))

    if verification:
        blocks.append(adf_paragraph(
            adf_text("Verification: ", bold=True),
            adf_text(f"alarm_ok={verification.get('alarm_ok')}, "
                      f"health_ok={verification.get('health_ok')}, "
                      f"error_rate_ok={verification.get('error_rate_ok')}"),
        ))

    blocks.append(adf_rule())

    # --- AI Analysis (when Bedrock is available) ---
    if ai_analysis:
        blocks.append(adf_heading(3, "AI Analysis"))
        blocks.append(adf_paragraph(adf_text(ai_analysis)))
        if ai_references:
            blocks.append(adf_paragraph(adf_text("KB References:", bold=True)))
            ref_lines = "\n".join(
                f"- {ref.get('source', 'unknown')}" for ref in ai_references
            )
            blocks.append(adf_code_block(ref_lines, language="text"))
        blocks.append(adf_rule())

    # --- Diagnostics ---
    blocks.append(adf_heading(3, "Diagnostics"))
    blocks.append(adf_paragraph(
        adf_text("Function: ", bold=True), adf_text(function_name),
    ))
    blocks.append(adf_paragraph(
        adf_text("Log Group: ", bold=True), adf_text(log_group),
    ))
    blocks.append(adf_paragraph(
        adf_text(f"Error Count: {len(error_logs)}"),
    ))

    if error_logs:
        patterns, _ = group_error_patterns(error_logs, truncate_length=100)
        top_lines = [
            f"[{count}x] {pat}"
            for pat, count in sorted(patterns.items(), key=lambda x: x[1], reverse=True)[:5]
        ]

        blocks.append(adf_paragraph(adf_text("Top Errors:", bold=True)))
        blocks.append(adf_code_block("\n".join(top_lines), language="text"))

    blocks.append(adf_rule())

    # --- Useful Links (clickable) ---
    blocks.append(adf_heading(3, "Useful Links"))
    blocks.append(adf_paragraph(
        adf_link("CloudWatch Logs", cw_logs_url),
        adf_text("  |  "),
        adf_link("Lambda Function", lambda_url),
    ))

    blocks.append(adf_rule())

    # --- CLI Commands ---
    blocks.append(adf_heading(3, "CLI Commands"))
    commands = (
        f"# Tail recent logs\n"
        f"aws logs tail {log_group} --since 15m --follow\n\n"
        f"# Check alarm state\n"
        f"aws cloudwatch describe-alarms --alarm-names \"{service}-high-*-{stage}\""
        f" --query 'MetricAlarms[].{{Name:AlarmName,State:StateValue}}'\n\n"
        f"# Check Lambda errors\n"
        f"aws lambda get-function --function-name {function_name}"
        f" --query 'Configuration.{{State:State,LastModified:LastModified}}'"
    )
    blocks.append(adf_code_block(commands))

    return blocks


# ------------------------------------------------------------------ #
# SNS notification message
# ------------------------------------------------------------------ #

def build_notification_message(
    incident_key: str,
    jira_ticket_id: str,
    severity: str,
    reason: str,
    service: str,
    stage: str,
) -> str:
    """Builds SNS notification message for on-call engineer."""
    reason_text = REASON_CONTEXT.get(reason, reason)
    return (
        f"[{severity}] Incident escalated: {incident_key}\n"
        f"Jira: {jira_ticket_id}\n"
        f"Service: {service} ({stage})\n"
        f"Reason: {reason_text}\n"
        f"Action required: Review Jira ticket for full diagnostics and remediation commands."
    )
