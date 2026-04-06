"""Checkpoint table operations for simulations."""

from datetime import datetime, timezone

import boto3

from . import config

CHECKPOINT_TABLE = f"sre-checkpoints-{config.STAGE}"

_ddb = boto3.resource("dynamodb", region_name=config.REGION)
_table = _ddb.Table(CHECKPOINT_TABLE)


def write_checkpoint(
    checkpoint_id: str,
    service: str,
    operation: str,
    item_ids: list[str],
    timeout_seconds: int = 300,
) -> dict:
    """Write a checkpoint record directly to DynamoDB."""
    now = datetime.now(timezone.utc).isoformat()
    item = {
        "checkpoint_id": checkpoint_id,
        "service": service,
        "operation": operation,
        "status": "in_progress",
        "checkpoint_mode": "item_tracking",
        "all_item_ids": set(item_ids),
        "total_items": len(item_ids),
        "timeout_seconds": timeout_seconds,
        "last_heartbeat": now,
        "created_at": now,
        "updated_at": now,
    }
    # DynamoDB does not allow empty sets — omit completed_items until first progress
    _table.put_item(Item=item)
    return item


def mark_progress(checkpoint_id: str, item_ids: list[str]) -> None:
    """Mark items as completed in a checkpoint."""
    _table.update_item(
        Key={"checkpoint_id": checkpoint_id},
        UpdateExpression="ADD completed_items :ids SET updated_at = :now",
        ExpressionAttributeValues={
            ":ids": set(item_ids),
            ":now": datetime.now(timezone.utc).isoformat(),
        },
    )


def log_failure(checkpoint_id: str, item_id: str, error_message: str) -> None:
    """Log a failure against a checkpoint."""
    now = datetime.now(timezone.utc).isoformat()
    _table.update_item(
        Key={"checkpoint_id": checkpoint_id},
        UpdateExpression=(
            "SET last_error = :err, "
            "first_failed_id = if_not_exists(first_failed_id, :fid), "
            "updated_at = :now"
        ),
        ExpressionAttributeValues={
            ":err": error_message,
            ":fid": item_id,
            ":now": now,
        },
    )


def get_checkpoint(checkpoint_id: str) -> dict | None:
    """Get a checkpoint record."""
    resp = _table.get_item(Key={"checkpoint_id": checkpoint_id})
    return resp.get("Item")


def query_service_checkpoints(service_name: str) -> list[dict]:
    """Query incomplete checkpoints for a service via GSI."""
    resp = _table.query(
        IndexName="service-status-index",
        KeyConditionExpression="#svc = :svc AND #st = :st",
        ExpressionAttributeNames={"#svc": "service", "#st": "status"},
        ExpressionAttributeValues={":svc": service_name, ":st": "in_progress"},
    )
    return resp.get("Items", [])


def delete_checkpoint(checkpoint_id: str) -> None:
    """Delete a checkpoint record."""
    _table.delete_item(Key={"checkpoint_id": checkpoint_id})
