"""DeltaReportService — compute checkpoint deltas and post to Jira.

The primary value delivery of Checkpoint & Clarity v1: when an incident is
detected for a batch service, scan its checkpoints, compute what's pending,
and post a structured report to the Jira ticket so the on-call engineer
knows exactly where the batch stalled.

All observability concerns (tracing, metrics, logging) handled by @observe decorator."""

import logging
from datetime import datetime, timezone

from shared.middleware.observability import observe

logger = logging.getLogger(__name__)

# Threshold: above this, don't list individual IDs in Jira
LARGE_BATCH_THRESHOLD = 50


class DeltaReportService:
    """Scan checkpoints for a service, compute deltas, post report to Jira."""

    def __init__(self, checkpoint_repo, ticketing_repo, config=None):
        self._checkpoint_repo = checkpoint_repo
        self._ticketing = ticketing_repo
        self._config = config

    @observe(
        operation="generate_delta_report",
        metric_prefix="sre.checkpoint.delta_report",
        context_kwarg_keys=["service_name", "jira_ticket_id"],
    )
    def generate_and_post(self, *, service_name: str, jira_ticket_id: str) -> dict:
        """Scan checkpoints for service, compute deltas, post report to Jira.

        Returns: {checkpoints_found, total_pending, zombies_found, report_posted}
        """
        checkpoints = self._checkpoint_repo.scan_incomplete(service_name=service_name)

        if not checkpoints:
            return {
                "checkpoints_found": 0,
                "total_pending": 0,
                "zombies_found": 0,
                "report_posted": False,
            }

        deltas = []
        for cp in checkpoints:
            delta = self._compute_delta(cp)
            deltas.append(delta)

        report = self._format_report(deltas)

        report_posted = False
        try:
            self._ticketing.add_jira_comment(jira_ticket_id, report)
            report_posted = True
        except Exception:
            logger.warning("Failed to post delta report to Jira",
                           extra={"jira_ticket_id": jira_ticket_id})

        total_pending = sum(
            d["pending_count"] for d in deltas
        )
        zombies = sum(1 for d in deltas if d["is_zombie"])

        return {
            "checkpoints_found": len(checkpoints),
            "total_pending": total_pending,
            "zombies_found": zombies,
            "report_posted": report_posted,
        }

    def _compute_delta(self, checkpoint: dict) -> dict:
        """Compute pending items and enrich with error context."""
        pending = self._checkpoint_repo.get_pending(checkpoint=checkpoint)
        is_zombie = self._checkpoint_repo.detect_zombie(checkpoint)

        if isinstance(pending, int):
            # Index-based: pending is the resume index
            pending_count = int(checkpoint.get("total_items", 0)) - int(checkpoint.get("completed_index", 0))
            pending_ids = None
            resume_index = pending
        else:
            pending_count = len(pending)
            pending_ids = pending
            resume_index = None

        total_items = int(checkpoint.get("total_items", 0))
        completed_count = total_items - pending_count

        return {
            "checkpoint_id": checkpoint["checkpoint_id"],
            "operation": checkpoint.get("operation", "unknown"),
            "mode": checkpoint.get("checkpoint_mode", "item_tracking"),
            "total_items": total_items,
            "completed_count": completed_count,
            "pending_count": pending_count,
            "pending_ids": pending_ids,
            "resume_index": resume_index,
            "is_zombie": is_zombie,
            "timeout_seconds": int(checkpoint.get("timeout_seconds", 300)),
            "last_heartbeat": checkpoint.get("last_heartbeat", ""),
            "error_summary": self._summarize_errors(checkpoint),
            "first_failed_id": checkpoint.get("first_failed_id"),
        }

    def _format_report(self, deltas: list[dict]) -> str:
        """Format Delta Report as Jira comment text."""
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        lines = [f"*Checkpoint Delta Report* (snapshot at {ts})", ""]

        if len(deltas) == 1:
            lines.extend(self._format_single(deltas[0]))
        else:
            lines.extend(self._format_multiple(deltas))

        lines.append("")
        lines.append("_Run get_pending() for current state._")
        return "\n".join(lines)

    def _format_single(self, delta: dict) -> list[str]:
        """Format report for a single checkpoint."""
        lines = [
            f"Checkpoint: {delta['checkpoint_id']}",
            f"Operation: {delta['operation']}",
            f"Progress: {delta['completed_count']}/{delta['total_items']} "
            f"({self._pct(delta['completed_count'], delta['total_items'])})",
        ]

        if delta["pending_count"] == 0:
            lines.append("Status: Nothing pending -- batch completed before detection")
            return lines

        if delta["mode"] == "index_based":
            lines.append(f"Resume from index: {delta['resume_index']:,}")
        elif delta["pending_count"] < LARGE_BATCH_THRESHOLD:
            lines.append(f"Pending IDs ({delta['pending_count']}): {', '.join(sorted(delta['pending_ids']))}")
        else:
            lines.append(f"Pending: {delta['pending_count']:,} items (too many to list)")

        # Zombie flag
        if delta["is_zombie"]:
            lines.append(f"Zombie: YES (no heartbeat for {delta['timeout_seconds'] * 2}s)")

        # Error context
        lines.append("")
        if delta["error_summary"]:
            lines.append(delta["error_summary"])
        else:
            lines.append("Failure Context: Not reported by application")

        if delta["first_failed_id"]:
            lines.append(f"First Failed ID: {delta['first_failed_id']}")

        return lines

    def _format_multiple(self, deltas: list[dict]) -> list[str]:
        """Format grouped summary for multiple checkpoints."""
        lines = [f"Checkpoints found: {len(deltas)}", ""]

        total_pending = 0
        for d in deltas:
            total_pending += d["pending_count"]
            zombie_flag = " [ZOMBIE]" if d["is_zombie"] else ""
            lines.append(
                f"- {d['checkpoint_id']}: {d['completed_count']}/{d['total_items']} "
                f"({self._pct(d['completed_count'], d['total_items'])}), "
                f"{d['pending_count']} pending{zombie_flag}"
            )

        lines.append("")
        lines.append(f"Total pending across all checkpoints: {total_pending:,}")

        # Error summaries
        for d in deltas:
            if d["error_summary"]:
                lines.append(f"[{d['checkpoint_id']}] {d['error_summary']}")

        return lines

    def _summarize_errors(self, checkpoint: dict) -> str:
        """Format error_counts into readable summary."""
        error_counts = checkpoint.get("error_counts")
        if not error_counts:
            return ""

        sorted_errors = sorted(error_counts.items(), key=lambda x: int(x[1]), reverse=True)
        top_key, top_count = sorted_errors[0]
        parts = [f"Top Error: {top_key} ({int(top_count)} occurrences)"]

        if len(sorted_errors) > 1:
            others = [f"{k} ({int(v)})" for k, v in sorted_errors[1:]]
            parts.append(f"Other Errors: {', '.join(others)}")

        return " | ".join(parts)

    @staticmethod
    def _pct(completed: int, total: int) -> str:
        if total == 0:
            return "0%"
        return f"{completed * 100 // total}%"
