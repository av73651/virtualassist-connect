"""CheckpointClient — write-only SDK for application progress tracking.

Applications call this to report progress during batch processing.
The SRE Platform reads checkpoint data via CheckpointRepository (separate class).

Design decisions:
- Write-only SDK (ARCH-002): apps write, platform reads via CheckpointRepository
- StringSet (SS) for completed_items: ADD is atomic and idempotent on Sets
- Omit completed_items on initial write: DynamoDB disallows empty StringSets (QUALITY-002)
- S3 side-loading at 500 items: keeps DynamoDB items under 400KB
- Hybrid buffered flush: by count OR time, whichever fires first (QUALITY-001)
- Error key sanitization: hash/truncate for DynamoDB map key safety (DYNAMO-001)
- @observe on every public method: tracing, metrics, structured logging (OBS-001)
- All params in context_kwarg_keys are keyword-only (after *) so @observe can capture them
"""

import hashlib
import json
import logging
import re
import time
from datetime import datetime, timezone, timedelta

import boto3
from botocore.exceptions import ClientError

from shared.middleware.observability import observe

logger = logging.getLogger(__name__)

# S3 side-loading threshold (item count)
S3_SIDELOAD_THRESHOLD = 500

# Max length for error message keys in DynamoDB map
ERROR_KEY_MAX_LENGTH = 120


_UNSAFE_CHAR_RE = re.compile(r"[^a-zA-Z0-9_]")


def _sanitize_error_key(error_message: str) -> str:
    """Sanitize error message for use as DynamoDB map key.

    DynamoDB expression paths have issues with special characters (#, [, ], ., :, etc.).
    Replace all non-alphanumeric characters with underscore, then truncate with hash suffix."""
    sanitized = _UNSAFE_CHAR_RE.sub("_", error_message)
    if len(sanitized) > ERROR_KEY_MAX_LENGTH:
        msg_hash = hashlib.md5(error_message.encode(), usedforsecurity=False).hexdigest()[:8]
        sanitized = sanitized[:ERROR_KEY_MAX_LENGTH - 9] + "_" + msg_hash
    return sanitized


class CheckpointClient:
    """Fire-and-forget checkpoint SDK for application teams.

    Single-threaded only (designed for AWS Lambda). Buffer state is held in
    instance memory — do not share across threads.

    All public method parameters are keyword-only (after *) so that the
    @observe decorator can capture them via context_kwarg_keys.

    Usage:
        checkpoint = CheckpointClient(table_name="sre-checkpoints-dev",
                                       bucket_name="sre-checkpoint-manifests-dev")

        checkpoint.write_checkpoint(checkpoint_id=f"batch:{fn}:{batch_id}",
                                     service=fn, operation="batch-insert",
                                     item_ids=txn_ids, mode="item_tracking")

        for txn_id in txn_ids:
            process(txn_id)
            checkpoint.mark_progress(checkpoint_id=checkpoint_id, item_id=txn_id)

        checkpoint.complete(checkpoint_id=checkpoint_id)
    """

    def __init__(self, table_name: str, bucket_name: str, dynamodb=None, s3=None):
        """Args:
            table_name: DynamoDB checkpoint table name
            bucket_name: S3 bucket for large manifests
            dynamodb: boto3.resource("dynamodb") — injected for testing
            s3: boto3.client("s3") — injected for testing
        """
        self._dynamodb = dynamodb or boto3.resource("dynamodb")
        self._table = self._dynamodb.Table(table_name)
        self._s3 = s3 or boto3.client("s3")
        self._bucket_name = bucket_name
        self._buffers: dict[str, set[str]] = {}
        self._last_flush_time: dict[str, float] = {}

    # ------------------------------------------------------------------ #
    # write_checkpoint
    # ------------------------------------------------------------------ #

    @observe(
        operation="write_checkpoint",
        metric_prefix="sre.checkpoint.created",
        context_kwarg_keys=["checkpoint_id", "service", "mode"],
    )
    def write_checkpoint(
        self,
        *,
        checkpoint_id: str,
        service: str,
        operation: str,
        item_ids: list[str] | None = None,
        total_items: int | None = None,
        mode: str = "item_tracking",
        metadata: dict | None = None,
        timeout_seconds: int = 300,
        ttl_hours: int = 24,
    ) -> None:
        """Create a checkpoint before processing begins.

        Args:
            checkpoint_id: Unique ID, e.g. "batch:batch-processor-api-dev:b-001"
            service: Source service name
            operation: Operation type, e.g. "batch-insert"
            item_ids: Full list of item IDs (item_tracking mode)
            total_items: Total item count (index_based mode)
            mode: "item_tracking" or "index_based"
            metadata: Application-specific context
            timeout_seconds: Max expected duration before zombie alert
            ttl_hours: Hours before DynamoDB auto-deletes record
        """
        now = datetime.now(timezone.utc)
        ttl_seconds = max(ttl_hours * 3600, timeout_seconds * 4)
        ttl_epoch = int((now + timedelta(seconds=ttl_seconds)).timestamp())

        item = {
            "checkpoint_id": checkpoint_id,
            "service": service,
            "operation": operation,
            "checkpoint_mode": mode,
            "status": "in_progress",
            "timeout_seconds": timeout_seconds,
            "last_heartbeat": now.isoformat(),
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "ttl": ttl_epoch,
        }

        if metadata is not None:
            item["metadata"] = metadata

        if mode == "item_tracking":
            if not item_ids:
                raise ValueError("item_ids required for item_tracking mode")
            item["total_items"] = len(item_ids)

            if len(item_ids) > S3_SIDELOAD_THRESHOLD:
                uri = self._upload_manifest_to_s3(checkpoint_id, item_ids)
                item["all_item_ids"] = uri
            else:
                item["all_item_ids"] = set(item_ids)
            # completed_items omitted — DynamoDB disallows empty StringSet

        elif mode == "index_based":
            if total_items is None:
                raise ValueError("total_items required for index_based mode")
            item["total_items"] = total_items
            item["completed_index"] = 0

        else:
            raise ValueError(f"Unknown checkpoint mode: {mode}")

        self._table.put_item(Item=item)

    # ------------------------------------------------------------------ #
    # mark_progress
    # ------------------------------------------------------------------ #

    @observe(
        operation="mark_progress",
        metric_prefix="sre.checkpoint.progress",
        context_kwarg_keys=["checkpoint_id"],
    )
    def mark_progress(
        self, *, checkpoint_id: str, item_id: str | None = None, index: int | None = None
    ) -> None:
        """Mark a single item as completed.

        Item tracking: ADD completed_items (StringSet, atomic, idempotent)
        Index-based: SET completed_index
        """
        if item_id is not None and index is not None:
            raise ValueError("Provide item_id or index, not both")

        now = datetime.now(timezone.utc).isoformat()

        if item_id is not None:
            self._table.update_item(
                Key={"checkpoint_id": checkpoint_id},
                UpdateExpression="ADD completed_items :item SET last_heartbeat = :hb, updated_at = :now",
                ExpressionAttributeValues={
                    ":item": {item_id},
                    ":hb": now,
                    ":now": now,
                },
            )
        elif index is not None:
            self._table.update_item(
                Key={"checkpoint_id": checkpoint_id},
                UpdateExpression="SET completed_index = :idx, last_heartbeat = :hb, updated_at = :now",
                ExpressionAttributeValues={
                    ":idx": index,
                    ":hb": now,
                    ":now": now,
                },
            )
        else:
            raise ValueError("Either item_id or index must be provided")

    # ------------------------------------------------------------------ #
    # mark_progress_buffered  (no @observe — delegates to flush_progress/mark_progress
    #                          which already have it; avoids double-span noise)
    # ------------------------------------------------------------------ #

    def mark_progress_buffered(
        self,
        *,
        checkpoint_id: str,
        item_id: str | None = None,
        index: int | None = None,
        flush_every: int = 100,
        flush_interval_seconds: int = 5,
    ) -> None:
        """Buffer progress in memory, flush when count OR time threshold reached.

        Item tracking: accumulates item_ids, flushes as single ADD.
        Index-based: delegates to mark_progress (no buffering needed).
        """
        if index is not None:
            self.mark_progress(checkpoint_id=checkpoint_id, index=index)
            return

        if item_id is None:
            raise ValueError("item_id required for buffered item_tracking progress")

        if checkpoint_id not in self._buffers:
            self._buffers[checkpoint_id] = set()
            self._last_flush_time[checkpoint_id] = time.time()

        self._buffers[checkpoint_id].add(item_id)

        should_flush = (
            len(self._buffers[checkpoint_id]) >= flush_every
            or (time.time() - self._last_flush_time[checkpoint_id]) >= flush_interval_seconds
        )

        if should_flush:
            self.flush_progress(checkpoint_id=checkpoint_id)

    # ------------------------------------------------------------------ #
    # flush_progress
    # ------------------------------------------------------------------ #

    @observe(
        operation="flush_progress",
        metric_prefix="sre.checkpoint.flush",
        context_kwarg_keys=["checkpoint_id"],
    )
    def flush_progress(self, *, checkpoint_id: str) -> None:
        """Flush buffered items to DynamoDB. Safe to call when buffer is empty."""
        buffer = set(self._buffers.get(checkpoint_id, set()))  # defensive copy
        if not buffer:
            return

        now = datetime.now(timezone.utc).isoformat()
        self._table.update_item(
            Key={"checkpoint_id": checkpoint_id},
            UpdateExpression="ADD completed_items :items SET last_heartbeat = :hb, updated_at = :now",
            ExpressionAttributeValues={
                ":items": buffer,
                ":hb": now,
                ":now": now,
            },
        )

        self._buffers[checkpoint_id] = set()
        self._last_flush_time[checkpoint_id] = time.time()

    # ------------------------------------------------------------------ #
    # log_failure
    # ------------------------------------------------------------------ #

    @observe(
        operation="log_failure",
        metric_prefix="sre.checkpoint.failure",
        context_kwarg_keys=["checkpoint_id", "item_id"],
    )
    def log_failure(self, *, checkpoint_id: str, item_id: str, error_message: str) -> None:
        """Record an item failure with error context.

        Updates last_error, increments error_counts[sanitized_message],
        and sets first_failed_id (only on first call — if_not_exists).

        Two-phase approach: try single-call increment first (fast path when
        error_counts map exists). On ValidationException, initialize the map
        with the counter set to 1 in a single atomic call (no partial state).
        """
        now = datetime.now(timezone.utc).isoformat()
        safe_key = _sanitize_error_key(error_message)

        # Fast path: single-call increment (works when error_counts map already exists)
        try:
            self._table.update_item(
                Key={"checkpoint_id": checkpoint_id},
                UpdateExpression=(
                    "SET last_error = :err, "
                    "first_failed_id = if_not_exists(first_failed_id, :fid), "
                    "updated_at = :now "
                    "ADD error_counts.#ekey :one"
                ),
                ExpressionAttributeNames={"#ekey": safe_key},
                ExpressionAttributeValues={
                    ":err": error_message,
                    ":fid": item_id,
                    ":now": now,
                    ":one": 1,
                },
            )
        except ClientError as e:
            if e.response["Error"]["Code"] != "ValidationException":
                raise
            # error_counts map doesn't exist yet — initialize empty map, then
            # retry the fast-path ADD (works for concurrent callers with different keys)
            logger.warning("Initializing error_counts map",
                           extra={"checkpoint_id": checkpoint_id, "error_key": safe_key})
            self._table.update_item(
                Key={"checkpoint_id": checkpoint_id},
                UpdateExpression="SET error_counts = if_not_exists(error_counts, :empty)",
                ExpressionAttributeValues={":empty": {}},
            )
            # Retry: map now exists, ADD will work
            self._table.update_item(
                Key={"checkpoint_id": checkpoint_id},
                UpdateExpression=(
                    "SET last_error = :err, "
                    "first_failed_id = if_not_exists(first_failed_id, :fid), "
                    "updated_at = :now "
                    "ADD error_counts.#ekey :one"
                ),
                ExpressionAttributeNames={"#ekey": safe_key},
                ExpressionAttributeValues={
                    ":err": error_message,
                    ":fid": item_id,
                    ":now": now,
                    ":one": 1,
                },
            )

    # ------------------------------------------------------------------ #
    # heartbeat
    # ------------------------------------------------------------------ #

    @observe(
        operation="heartbeat",
        metric_prefix="sre.checkpoint.heartbeat",
        context_kwarg_keys=["checkpoint_id"],
    )
    def heartbeat(self, *, checkpoint_id: str) -> None:
        """Update last_heartbeat only. Use between slow operations."""
        now = datetime.now(timezone.utc).isoformat()
        self._table.update_item(
            Key={"checkpoint_id": checkpoint_id},
            UpdateExpression="SET last_heartbeat = :hb, updated_at = :now",
            ExpressionAttributeValues={":hb": now, ":now": now},
        )

    # ------------------------------------------------------------------ #
    # complete
    # ------------------------------------------------------------------ #

    @observe(
        operation="complete_checkpoint",
        metric_prefix="sre.checkpoint.completed",
        context_kwarg_keys=["checkpoint_id"],
    )
    def complete(self, *, checkpoint_id: str) -> None:
        """Mark checkpoint as completed. Flushes buffer first. Idempotent."""
        self.flush_progress(checkpoint_id=checkpoint_id)

        now = datetime.now(timezone.utc).isoformat()
        try:
            self._table.update_item(
                Key={"checkpoint_id": checkpoint_id},
                UpdateExpression="SET #s = :completed, updated_at = :now",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":completed": "completed", ":now": now},
                ConditionExpression="attribute_exists(checkpoint_id)",
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.warning("Checkpoint not found or already expired",
                               extra={"checkpoint_id": checkpoint_id})
            else:
                raise

    # ------------------------------------------------------------------ #
    # get_pending
    # ------------------------------------------------------------------ #

    @observe(
        operation="get_pending",
        metric_prefix="sre.checkpoint.get_pending",
        context_kwarg_keys=["checkpoint_id"],
    )
    def get_pending(self, *, checkpoint_id: str) -> list[str] | int:
        """Compute pending items.

        Item tracking: returns list of item_ids not yet completed.
        Index-based: returns the next index to process (completed_index + 1).
        """
        resp = self._table.get_item(Key={"checkpoint_id": checkpoint_id})
        item = resp.get("Item")
        if not item:
            raise ValueError(f"Checkpoint not found: {checkpoint_id}")

        mode = item.get("checkpoint_mode", "item_tracking")

        if mode == "index_based":
            return item.get("completed_index", 0) + 1

        # Item tracking: all_item_ids - completed_items
        all_ids = item.get("all_item_ids", set())

        # S3 side-loaded manifest
        if isinstance(all_ids, str) and all_ids.startswith("s3://"):
            all_ids = set(self._download_manifest_from_s3(all_ids))

        completed = item.get("completed_items", set())
        return list(all_ids - completed)

    # ------------------------------------------------------------------ #
    # S3 helpers (private — no @observe needed)
    # ------------------------------------------------------------------ #

    def _upload_manifest_to_s3(self, checkpoint_id: str, item_ids: list[str]) -> str:
        """Upload item ID list to S3, return s3:// URI."""
        key = f"{checkpoint_id}/items.json"
        self._s3.put_object(
            Bucket=self._bucket_name,
            Key=key,
            Body=json.dumps(item_ids),
            ContentType="application/json",
        )
        return f"s3://{self._bucket_name}/{key}"

    def _download_manifest_from_s3(self, uri: str) -> list[str]:
        """Download item ID list from S3 URI."""
        # Parse s3://bucket/key
        parts = uri.replace("s3://", "").split("/", 1)
        bucket = parts[0]
        key = parts[1]
        resp = self._s3.get_object(Bucket=bucket, Key=key)
        return json.loads(resp["Body"].read().decode("utf-8"))
