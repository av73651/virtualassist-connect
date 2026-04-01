"""LogAnalysisService — centralized log retrieval and analysis.

Wraps ObservabilityRepository with reusable high-level operations used by
triage, escalation, and detection services. Consolidates error collection,
pattern grouping, health checking, and attachment formatting.

All observability concerns (tracing, metrics, logging) handled by @observe decorator."""

from datetime import datetime, timedelta, timezone

from shared.middleware.observability import observe

from src.domain.jira_formatting import group_error_patterns
from src.models.config import IncidentConfig


class LogAnalysisService:
    """Centralized log retrieval, analysis, and health checking."""

    def __init__(self, observability_repo, config: IncidentConfig):
        self._observability = observability_repo
        self._config = config

    @observe(operation="analyze_errors", metric_prefix="log_analysis")
    def analyze_errors(self, log_group: str) -> dict:
        """Collects error logs and groups by pattern.

        Returns dict with error_patterns, error_count, unique_errors, sample_payloads."""
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(minutes=self._config.log_analysis_window_minutes)

        errors = self._observability.collect_errors(
            log_group=log_group,
            start_time=start_time,
            end_time=now,
            max_events=self._config.max_log_events,
        )

        error_patterns, sample_payloads = group_error_patterns(
            errors,
            truncate_length=self._config.pattern_key_max_length,
            max_samples=self._config.max_sample_payloads,
            sample_truncate_length=self._config.sample_payload_max_length,
        )

        return {
            "error_patterns": error_patterns,
            "error_count": len(errors),
            "unique_errors": len(error_patterns),
            "sample_payloads": sample_payloads,
        }

    @observe(operation="collect_diagnostics", metric_prefix="log_diagnostics")
    def collect_diagnostics(self, log_group: str) -> list[dict]:
        """Collects recent error logs for diagnostic attachment."""
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(minutes=self._config.log_analysis_window_minutes)
        return self._observability.collect_errors(
            log_group=log_group,
            start_time=start_time,
            end_time=now,
            max_events=self._config.max_log_events,
        )

    @observe(operation="collect_recent_logs", metric_prefix="log_recent")
    def collect_recent(self, log_group: str, minutes: int | None = None) -> list[dict]:
        """Collects recent log entries (all levels) for recovery evidence or verification."""
        return self._observability.collect_recent(
            log_group=log_group,
            minutes=minutes or self._config.recovery_log_minutes,
        )

    @observe(operation="check_health", metric_prefix="log_health")
    def check_health(self, log_group: str) -> tuple[bool, bool]:
        """Checks recent logs for errors after remediation.

        Returns (health_ok, error_rate_ok):
        - health_ok: no error keywords in recent logs
        - error_rate_ok: error count below verification threshold"""
        recent_logs = self._observability.collect_recent(
            log_group, minutes=self._config.verification_window_minutes
        )
        error_logs = [
            log for log in recent_logs
            if any(kw in log.get("message", "") for kw in ["ERROR", "Error", "Exception"])
        ]
        health_ok = len(error_logs) == 0
        error_rate_ok = len(error_logs) < self._config.verification_error_threshold
        return health_ok, error_rate_ok

    @staticmethod
    def format_log_attachment(error_logs: list[dict], limit: int = 50) -> str:
        """Formats error logs into a string for Jira file attachment."""
        return "\n".join(
            f"[{e.get('timestamp', 'N/A')}] {e.get('message', e.get('@message', ''))}"
            for e in error_logs[:limit]
        )
