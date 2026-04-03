"""CheckpointRepository — platform-internal read layer for checkpoint data.

Separated from CheckpointClient (application write SDK) per ARCH-002:
- CheckpointClient: write-only SDK used by application teams
- CheckpointRepository: read-only queries used by SRE Platform

Different audience, different IAM permissions, different access patterns.
All observability concerns (tracing, metrics, logging) handled by @observe decorator."""

import json
import logging
from datetime import datetime, timezone, timedelta

import boto3

from shared.middleware.observability import observe

logger = logging.getLogger(__name__)


class CheckpointRepository:
    """Read-only queries on the checkpoint table for the SRE Platform."""

    def __init__(self, table_name: str, bucket_name: str, dynamodb=None, s3=None, table=None):
        self._dynamodb = dynamodb or boto3.resource("dynamodb")
        self._table = table or self._dynamodb.Table(table_name)
        self._s3 = s3 or boto3.client("s3")
        self._bucket_name = bucket_name

    @observe(
        operation="scan_incomplete",
        metric_prefix="sre.checkpoint_repo.scan_incomplete",
        context_kwarg_keys=["service_name"],
    )
    def scan_incomplete(self, *, service_name: str) -> list[dict]:
        """Query GSI: service + status=in_progress. Returns checkpoint items."""
        resp = self._table.query(
            IndexName="service-status-index",
            KeyConditionExpression="#svc = :svc AND #st = :st",
            ExpressionAttributeNames={"#svc": "service", "#st": "status"},
            ExpressionAttributeValues={":svc": service_name, ":st": "in_progress"},
        )
        return resp.get("Items", [])

    @observe(
        operation="get_checkpoint",
        metric_prefix="sre.checkpoint_repo.get",
        context_kwarg_keys=["checkpoint_id"],
    )
    def get_checkpoint(self, *, checkpoint_id: str) -> dict | None:
        """GetItem by checkpoint_id. Returns None if not found."""
        resp = self._table.get_item(Key={"checkpoint_id": checkpoint_id})
        return resp.get("Item")

    @observe(
        operation="get_pending",
        metric_prefix="sre.checkpoint_repo.pending",
        context_kwarg_keys=["checkpoint_id"],
    )
    def get_pending(self, *, checkpoint: dict) -> list[str] | int:
        """Compute pending items from checkpoint data.

        Item tracking: all_item_ids - completed_items (loads from S3 if URI).
        Index-based: completed_index + 1.
        """
        mode = checkpoint.get("checkpoint_mode", "item_tracking")

        if mode == "index_based":
            return int(checkpoint.get("completed_index", 0)) + 1

        all_ids = checkpoint.get("all_item_ids", set())

        if isinstance(all_ids, str) and all_ids.startswith("s3://"):
            all_ids = set(self._download_manifest_from_s3(all_ids))

        completed = checkpoint.get("completed_items", set())
        return list(all_ids - completed)

    @observe(
        operation="detect_zombie",
        metric_prefix="sre.checkpoint_repo.zombie",
    )
    def detect_zombie(self, checkpoint: dict) -> bool:
        """Return True if last_heartbeat is older than 2x timeout_seconds."""
        timeout = int(checkpoint.get("timeout_seconds", 300))
        last_hb_str = checkpoint.get("last_heartbeat")
        if not last_hb_str:
            return True

        last_hb = datetime.fromisoformat(last_hb_str)
        threshold = timedelta(seconds=timeout * 2)
        return (datetime.now(timezone.utc) - last_hb) > threshold

    def _download_manifest_from_s3(self, uri: str) -> list[str]:
        """Download item ID list from S3 URI."""
        parts = uri.replace("s3://", "").split("/", 1)
        resp = self._s3.get_object(Bucket=parts[0], Key=parts[1])
        return json.loads(resp["Body"].read().decode("utf-8"))
