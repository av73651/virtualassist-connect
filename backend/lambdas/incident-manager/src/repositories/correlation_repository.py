"""CorrelationRepository — DynamoDB operations for incident correlation.

CRUD + conditional writes + GSI storm detection query.
All observability concerns (tracing, metrics, logging) handled by @observe decorator."""

import boto3
from boto3.dynamodb.conditions import Key, Attr

from shared.middleware.observability import observe

from src.models.correlation_record import CorrelationRecord
from src.models.exceptions import DuplicateIncidentError


class CorrelationRepository:
    """DynamoDB operations for incident correlation store."""

    def __init__(self, table_name: str, dynamodb_resource=None):
        self._dynamodb = dynamodb_resource or boto3.resource("dynamodb")
        self._table = self._dynamodb.Table(table_name)

    @observe(operation="get_correlation", metric_prefix="dynamo_get")
    def get(self, incident_key: str) -> CorrelationRecord | None:
        """Retrieve correlation record by key. Returns None if not found."""
        response = self._table.get_item(Key={"incident_key": incident_key})
        item = response.get("Item")
        if not item:
            return None
        return CorrelationRecord.from_dynamodb_item(item)

    @observe(operation="reserve_correlation", metric_prefix="dynamo_reserve")
    def reserve(self, record: CorrelationRecord) -> bool:
        """Reserve incident_key with conditional write.

        Uses attribute_not_exists to prevent duplicates.
        Returns True if reserved.
        Raises DuplicateIncidentError if key already exists."""
        try:
            self._table.put_item(
                Item=record.to_dynamodb_item(),
                ConditionExpression=Attr("incident_key").not_exists(),
            )
            return True
        except self._dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
            raise DuplicateIncidentError(
                f"Incident key already exists: {record.incident_key}"
            )

    @observe(operation="update_correlation", metric_prefix="dynamo_update")
    def update(self, record: CorrelationRecord) -> None:
        """Update correlation record (status transitions, add ticket ID)."""
        self._table.put_item(Item=record.to_dynamodb_item())

    @observe(operation="delete_correlation", metric_prefix="dynamo_delete")
    def delete(self, incident_key: str) -> None:
        """Delete correlation record."""
        self._table.delete_item(Key={"incident_key": incident_key})

    @observe(operation="count_recent_incidents", metric_prefix="dynamo_storm_query")
    def count_recent(self, since: str) -> int:
        """Count correlation records created after `since` (ISO 8601 string).

        Queries GSI with partition key 'ALL' and sort key created_at > since.
        Used for incident storm detection."""
        response = self._table.query(
            IndexName="created_at-index",
            KeyConditionExpression=(
                Key("gsi_pk").eq("ALL") & Key("created_at").gt(since)
            ),
            Select="COUNT",
        )
        return response["Count"]
