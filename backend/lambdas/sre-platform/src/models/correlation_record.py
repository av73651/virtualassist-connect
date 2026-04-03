"""CorrelationRecord — DynamoDB correlation store model.

This module provides the domain model for incident correlation records stored in DynamoDB.
The correlation store is the single source of truth for linking CloudWatch Alarms
(via incident_key) to Jira incidents (via jira_ticket_id).

It enables:
1. Idempotency: Preventing duplicate Jira tickets for the same alarm via the "Reserve-then-Create" pattern.
2. Resilience: Tracking incident lifecycle status (RESERVED -> DETECTED -> GRACE).
3. Storm Detection: GSI-based counting of recent incidents using the 'gsi_pk' field.
4. Auto-cleanup: Leveraging DynamoDB TTL for automatic record expiration.
"""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone

from src.models.enums import CorrelationStatus


@dataclass
class CorrelationRecord:
    """Represents an active or recently resolved incident correlation in DynamoDB.

    Attributes:
        incident_key: Partition key, formatted as "{service}-{alarm_type}-{stage}".
        jira_ticket_id: The unique ID of the associated Jira incident (e.g., "INC-123").
            Is None during the RESERVED phase before the ticket is created.
        severity: The incident severity level (e.g., "SEV-1").
        status: The current lifecycle state (RESERVED, DETECTED, TRIAGING, ESCALATED, GRACE).
        created_at: UTC timestamp when the record was first reserved.
        ttl: DynamoDB Time-To-Live (epoch seconds). Records are automatically deleted
            by DynamoDB after this time to keep the table size manageable.
        metrics: Metrics bundle from MetricsCollectionService (Phase 2 enhancement).
            Contains alarm_metrics, lambda_metrics, deployments, and enrichment.
        metrics_collected_at: UTC timestamp when metrics were collected (Phase 2).
    """

    incident_key: str
    jira_ticket_id: str | None
    severity: str
    status: CorrelationStatus
    created_at: datetime
    ttl: int
    metrics: dict | None = None
    metrics_collected_at: datetime | None = None

    @classmethod
    def reserve(
        cls, incident_key: str, severity: str, ttl_hours: int = 24, now: datetime | None = None
    ) -> "CorrelationRecord":
        """Factory: creates a placeholder record in the RESERVED state.

        This is the first step of the "Reserve-then-Create" pattern. By writing this
        record to DynamoDB with a conditional 'attribute_not_exists(incident_key)',
        we ensure that only one Lambda instance proceeds to create a Jira ticket.

        Args:
            incident_key: Unique correlation key for the alarm.
            severity: Classified severity of the incident.
            ttl_hours: Record expiration window (default 24h).
            now: Current time (injected for testing).

        Returns:
            A new CorrelationRecord instance in RESERVED state.
        """
        now = now or datetime.now(timezone.utc)
        ttl = int((now + timedelta(hours=ttl_hours)).timestamp())
        return cls(
            incident_key=incident_key,
            jira_ticket_id=None,
            severity=severity,
            status=CorrelationStatus.RESERVED,
            created_at=now,
            ttl=ttl,
        )

    def associate_jira_ticket(self, jira_ticket_id: str) -> "CorrelationRecord":
        """Updates the record with a Jira ticket ID and transitions status to DETECTED.

        Called after the Jira ticket has been successfully created.

        Args:
            jira_ticket_id: The ID returned by the Jira API.

        Returns:
            A new CorrelationRecord instance in DETECTED state.
        """
        return replace(
            self,
            jira_ticket_id=jira_ticket_id,
            status=CorrelationStatus.DETECTED,
        )

    def to_status(self, status: CorrelationStatus) -> "CorrelationRecord":
        """Transitions the record to a new status (e.g., TRIAGING, ESCALATED).

        Args:
            status: The target CorrelationStatus.

        Returns:
            A new CorrelationRecord instance with the updated status.
        """
        return replace(self, status=status)

    def reopen(self, now: datetime, ttl_hours: int) -> "CorrelationRecord":
        """Reopens an incident from GRACE back to DETECTED status.

        Used when the same alarm fires again within the 15-minute grace window.
        Reset's the 'created_at' and 'ttl' to provide a fresh 24h window.

        Args:
            now: Current time.
            ttl_hours: Fresh TTL window (typically 24h).

        Returns:
            A new CorrelationRecord instance in DETECTED state.
        """
        ttl = int((now + timedelta(hours=ttl_hours)).timestamp())
        return replace(self, status=CorrelationStatus.DETECTED, created_at=now, ttl=ttl)

    def to_grace(self, resolved_at: datetime, grace_period_seconds: int) -> "CorrelationRecord":
        """Transitions the record to GRACE status after auto-resolution.

        The grace period (typically 15 minutes) allows the system to detect
        recurring incidents and reopen the same Jira ticket instead of creating a new one.

        Args:
            resolved_at: Time of resolution.
            grace_period_seconds: Duration of the grace window.

        Returns:
            A new CorrelationRecord instance in GRACE state with a short TTL.
        """
        ttl = int((resolved_at + timedelta(seconds=grace_period_seconds)).timestamp())
        return replace(self, status=CorrelationStatus.GRACE, ttl=ttl)

    def with_metrics(self, metrics: dict, collected_at: datetime) -> "CorrelationRecord":
        """Stores metrics bundle in the record (Phase 2 enhancement).

        Used by MetricsCollectionService to cache metrics in DynamoDB.
        Enables metrics reuse across Detection → Triage → Escalation workflow
        and supports timeline comparison (Detection T0 vs Escalation T+N).

        Args:
            metrics: Full metrics bundle from MetricsCollectionService containing
                alarm_metrics, lambda_metrics, deployments, and enrichment.
            collected_at: Timestamp when metrics were collected.

        Returns:
            A new CorrelationRecord instance with metrics stored.
        """
        return replace(self, metrics=metrics, metrics_collected_at=collected_at)

    def to_dynamodb_item(self) -> dict:
        """Converts the model to a DynamoDB-compatible dictionary.

        DynamoDB serialization notes:
        - jira_ticket_id: None is serialized as an empty string (DynamoDB does not support null strings).
        - gsi_pk: Fixed 'ALL' partition key used by the 'created_at-index' GSI.
          This enables efficient time-range queries across all incidents for storm detection.
        - created_at: ISO 8601 string for human readability and GSI sort key queries.
        - metrics: Optional metrics bundle (Phase 2). Only included if present.
        - metrics_collected_at: ISO 8601 timestamp (Phase 2). Only included if metrics present.

        Returns:
            A dictionary containing the DynamoDB item attributes.
        """
        item = {
            "incident_key": self.incident_key,
            "jira_ticket_id": self.jira_ticket_id or "",
            "severity": self.severity,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "ttl": self.ttl,
            "gsi_pk": "ALL",
        }

        if self.metrics:
            item["metrics"] = self.metrics
            item["metrics_collected_at"] = self.metrics_collected_at.isoformat()

        return item

    @classmethod
    def from_dynamodb_item(cls, item: dict) -> "CorrelationRecord":
        """Reconstructs the model from a DynamoDB item dictionary.

        Args:
            item: The attribute dictionary returned by DynamoDB.

        Returns:
            A reconstructed CorrelationRecord instance.
        """
        jira_ticket_id = item.get("jira_ticket_id", "")

        metrics = item.get("metrics")
        metrics_collected_at = None
        if item.get("metrics_collected_at"):
            metrics_collected_at = datetime.fromisoformat(item["metrics_collected_at"])

        return cls(
            incident_key=item["incident_key"],
            jira_ticket_id=jira_ticket_id if jira_ticket_id else None,
            severity=item["severity"],
            status=CorrelationStatus(item["status"]),
            created_at=datetime.fromisoformat(item["created_at"]),
            ttl=int(item["ttl"]),
            metrics=metrics,
            metrics_collected_at=metrics_collected_at,
        )
