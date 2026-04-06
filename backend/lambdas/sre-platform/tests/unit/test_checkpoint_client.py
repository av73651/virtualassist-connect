"""Tests for CheckpointClient SDK — 36 unit tests with moto.

Covers: write_checkpoint, mark_progress, mark_progress_buffered, flush_progress,
log_failure, heartbeat, complete, get_pending for both item_tracking and index_based modes.
Includes 8 negative tests for all ValueError paths.

Uses mock_checkpoint_client / mock_checkpoint_table from conftest.py (single source of truth
for table schema and @observe mock).
"""

import json
import time

import pytest

from src.checkpoint.client import _sanitize_error_key
from tests.conftest import CHECKPOINT_BUCKET_NAME


# ------------------------------------------------------------------ #
# Aliases — conftest fixtures used as: client, table, s3
# ------------------------------------------------------------------ #

@pytest.fixture
def client(mock_checkpoint_client):
    """Alias for conftest's mock_checkpoint_client."""
    return mock_checkpoint_client


@pytest.fixture
def table(mock_checkpoint_table):
    """Direct table reference for assertions."""
    _, _, tbl = mock_checkpoint_table
    return tbl


@pytest.fixture
def s3(mock_checkpoint_table):
    """Direct S3 client for manifest assertions."""
    _, s3_client, _ = mock_checkpoint_table
    return s3_client


def _get_item(table, checkpoint_id):
    """Helper to get checkpoint item from DynamoDB."""
    return table.get_item(Key={"checkpoint_id": checkpoint_id}).get("Item")


# ------------------------------------------------------------------ #
# 1. write_checkpoint
# ------------------------------------------------------------------ #

class TestWriteCheckpoint:

    def test_creates_item_tracking_checkpoint(self, client, table):
        client.write_checkpoint(
            checkpoint_id="batch:api:b-001",
            service="batch-processor-api-dev",
            operation="batch-insert",
            item_ids=["txn-1", "txn-2", "txn-3"],
            mode="item_tracking",
        )

        item = _get_item(table, "batch:api:b-001")
        assert item is not None
        assert item["status"] == "in_progress"
        assert item["service"] == "batch-processor-api-dev"
        assert item["operation"] == "batch-insert"
        assert item["checkpoint_mode"] == "item_tracking"
        assert item["total_items"] == 3
        assert item["all_item_ids"] == {"txn-1", "txn-2", "txn-3"}
        assert "completed_items" not in item
        assert "last_heartbeat" in item
        assert "ttl" in item

    def test_s3_sideloading_above_threshold(self, client, table, s3):
        item_ids = [f"item-{i}" for i in range(600)]

        client.write_checkpoint(
            checkpoint_id="batch:api:b-big",
            service="batch-api-dev",
            operation="import",
            item_ids=item_ids,
        )

        item = _get_item(table, "batch:api:b-big")
        assert isinstance(item["all_item_ids"], str)
        assert item["all_item_ids"].startswith("s3://")
        assert item["total_items"] == 600

        resp = s3.get_object(Bucket=CHECKPOINT_BUCKET_NAME, Key="batch:api:b-big/items.json")
        manifest = json.loads(resp["Body"].read())
        assert len(manifest) == 600

    def test_index_based_mode(self, client, table):
        client.write_checkpoint(
            checkpoint_id="import:csv:2024",
            service="data-import-dev",
            operation="csv-import",
            total_items=50000,
            mode="index_based",
        )

        item = _get_item(table, "import:csv:2024")
        assert item["checkpoint_mode"] == "index_based"
        assert item["total_items"] == 50000
        assert item["completed_index"] == 0
        assert "all_item_ids" not in item

    def test_with_metadata(self, client, table):
        client.write_checkpoint(
            checkpoint_id="batch:api:b-meta",
            service="batch-api-dev",
            operation="insert",
            item_ids=["a", "b"],
            metadata={"target_table": "batch-transactions-dev"},
        )

        item = _get_item(table, "batch:api:b-meta")
        assert item["metadata"]["target_table"] == "batch-transactions-dev"

    def test_ttl_computed_correctly(self, client, table):
        client.write_checkpoint(
            checkpoint_id="batch:api:b-ttl",
            service="api-dev",
            operation="op",
            item_ids=["a"],
            timeout_seconds=28800,
            ttl_hours=24,
        )

        item = _get_item(table, "batch:api:b-ttl")
        now_epoch = time.time()
        assert item["ttl"] > now_epoch + (28800 * 4) - 60


# ------------------------------------------------------------------ #
# 2. mark_progress
# ------------------------------------------------------------------ #

class TestMarkProgress:

    def test_adds_to_stringset(self, client, table):
        client.write_checkpoint(
            checkpoint_id="batch:api:b-mp",
            service="api-dev", operation="op",
            item_ids=["txn-1", "txn-2", "txn-3"],
        )
        client.mark_progress(checkpoint_id="batch:api:b-mp", item_id="txn-1")

        item = _get_item(table, "batch:api:b-mp")
        assert item["completed_items"] == {"txn-1"}

    def test_index_based_updates_completed_index(self, client, table):
        client.write_checkpoint(
            checkpoint_id="import:idx",
            service="api-dev", operation="op",
            total_items=100, mode="index_based",
        )
        client.mark_progress(checkpoint_id="import:idx", index=42)

        assert _get_item(table, "import:idx")["completed_index"] == 42

    def test_updates_heartbeat(self, client, table):
        client.write_checkpoint(
            checkpoint_id="batch:api:b-hb",
            service="api-dev", operation="op",
            item_ids=["txn-1"],
        )
        old_hb = _get_item(table, "batch:api:b-hb")["last_heartbeat"]

        time.sleep(0.01)
        client.mark_progress(checkpoint_id="batch:api:b-hb", item_id="txn-1")

        assert _get_item(table, "batch:api:b-hb")["last_heartbeat"] >= old_hb

    def test_duplicate_is_idempotent(self, client, table):
        client.write_checkpoint(
            checkpoint_id="batch:api:b-dup",
            service="api-dev", operation="op",
            item_ids=["txn-1", "txn-2"],
        )
        client.mark_progress(checkpoint_id="batch:api:b-dup", item_id="txn-1")
        client.mark_progress(checkpoint_id="batch:api:b-dup", item_id="txn-1")

        assert _get_item(table, "batch:api:b-dup")["completed_items"] == {"txn-1"}


# ------------------------------------------------------------------ #
# 3. mark_progress_buffered
# ------------------------------------------------------------------ #

class TestMarkProgressBuffered:

    def test_flushes_at_count_threshold(self, client, table):
        client.write_checkpoint(
            checkpoint_id="batch:api:b-buf",
            service="api-dev", operation="op",
            item_ids=[f"txn-{i}" for i in range(10)],
        )
        for i in range(5):
            client.mark_progress_buffered(
                checkpoint_id="batch:api:b-buf", item_id=f"txn-{i}", flush_every=5,
            )

        assert _get_item(table, "batch:api:b-buf")["completed_items"] == {f"txn-{i}" for i in range(5)}

    def test_flushes_at_time_threshold(self, client, table):
        client.write_checkpoint(
            checkpoint_id="batch:api:b-time",
            service="api-dev", operation="op",
            item_ids=[f"txn-{i}" for i in range(100)],
        )
        client.mark_progress_buffered(
            checkpoint_id="batch:api:b-time", item_id="txn-0",
            flush_every=1000, flush_interval_seconds=0,
        )
        client.mark_progress_buffered(
            checkpoint_id="batch:api:b-time", item_id="txn-1",
            flush_every=1000, flush_interval_seconds=0,
        )

        assert "txn-0" in _get_item(table, "batch:api:b-time").get("completed_items", set())


# ------------------------------------------------------------------ #
# 4. flush_progress
# ------------------------------------------------------------------ #

class TestFlushProgress:

    def test_writes_buffered_items(self, client, table):
        client.write_checkpoint(
            checkpoint_id="batch:api:b-flush",
            service="api-dev", operation="op",
            item_ids=[f"txn-{i}" for i in range(10)],
        )
        for i in range(3):
            client.mark_progress_buffered(
                checkpoint_id="batch:api:b-flush", item_id=f"txn-{i}",
                flush_every=1000,
            )

        assert "completed_items" not in _get_item(table, "batch:api:b-flush")

        client.flush_progress(checkpoint_id="batch:api:b-flush")

        assert _get_item(table, "batch:api:b-flush")["completed_items"] == {"txn-0", "txn-1", "txn-2"}

    def test_noop_when_buffer_empty(self, client, table):
        client.write_checkpoint(
            checkpoint_id="batch:api:b-noop",
            service="api-dev", operation="op",
            item_ids=["txn-1"],
        )
        client.flush_progress(checkpoint_id="batch:api:b-noop")
        client.flush_progress(checkpoint_id="nonexistent-checkpoint")


# ------------------------------------------------------------------ #
# 5. log_failure
# ------------------------------------------------------------------ #

class TestLogFailure:

    def test_stores_error_and_increments_counter(self, client, table):
        client.write_checkpoint(
            checkpoint_id="batch:api:b-err",
            service="api-dev", operation="op",
            item_ids=["txn-1", "txn-2"],
        )
        client.log_failure(checkpoint_id="batch:api:b-err", item_id="txn-1", error_message="ReadTimeout: downstream API")

        item = _get_item(table, "batch:api:b-err")
        assert item["last_error"] == "ReadTimeout: downstream API"
        assert item["first_failed_id"] == "txn-1"
        assert item["error_counts"][_sanitize_error_key("ReadTimeout: downstream API")] == 1

    def test_preserves_first_failed_id(self, client, table):
        client.write_checkpoint(
            checkpoint_id="batch:api:b-first",
            service="api-dev", operation="op",
            item_ids=["txn-1", "txn-2", "txn-3"],
        )
        client.log_failure(checkpoint_id="batch:api:b-first", item_id="txn-1", error_message="Error A")
        client.log_failure(checkpoint_id="batch:api:b-first", item_id="txn-2", error_message="Error B")

        item = _get_item(table, "batch:api:b-first")
        assert item["first_failed_id"] == "txn-1"
        assert item["last_error"] == "Error B"

    def test_increments_same_error_counter(self, client, table):
        client.write_checkpoint(
            checkpoint_id="batch:api:b-inc",
            service="api-dev", operation="op",
            item_ids=["txn-1", "txn-2", "txn-3"],
        )
        for i in range(1, 4):
            client.log_failure(checkpoint_id="batch:api:b-inc", item_id=f"txn-{i}", error_message="Timeout")

        assert _get_item(table, "batch:api:b-inc")["error_counts"][_sanitize_error_key("Timeout")] == 3


# ------------------------------------------------------------------ #
# 6. heartbeat
# ------------------------------------------------------------------ #

class TestHeartbeat:

    def test_updates_heartbeat_only(self, client, table):
        client.write_checkpoint(
            checkpoint_id="batch:api:b-beat",
            service="api-dev", operation="op",
            item_ids=["txn-1"],
        )
        old_hb = _get_item(table, "batch:api:b-beat")["last_heartbeat"]
        time.sleep(0.01)

        client.heartbeat(checkpoint_id="batch:api:b-beat")

        new_item = _get_item(table, "batch:api:b-beat")
        assert new_item["last_heartbeat"] >= old_hb
        assert new_item["status"] == "in_progress"
        assert "completed_items" not in new_item


# ------------------------------------------------------------------ #
# 7. complete
# ------------------------------------------------------------------ #

class TestComplete:

    def test_sets_status_completed(self, client, table):
        client.write_checkpoint(
            checkpoint_id="batch:api:b-done",
            service="api-dev", operation="op",
            item_ids=["txn-1"],
        )
        client.mark_progress(checkpoint_id="batch:api:b-done", item_id="txn-1")
        client.complete(checkpoint_id="batch:api:b-done")

        assert _get_item(table, "batch:api:b-done")["status"] == "completed"

    def test_flushes_buffer_first(self, client, table):
        client.write_checkpoint(
            checkpoint_id="batch:api:b-cbuf",
            service="api-dev", operation="op",
            item_ids=["txn-1", "txn-2"],
        )
        client.mark_progress_buffered(checkpoint_id="batch:api:b-cbuf", item_id="txn-1", flush_every=1000)
        client.mark_progress_buffered(checkpoint_id="batch:api:b-cbuf", item_id="txn-2", flush_every=1000)

        assert "completed_items" not in _get_item(table, "batch:api:b-cbuf")

        client.complete(checkpoint_id="batch:api:b-cbuf")

        item = _get_item(table, "batch:api:b-cbuf")
        assert item["status"] == "completed"
        assert item["completed_items"] == {"txn-1", "txn-2"}

    def test_idempotent_on_completed(self, client, table):
        client.write_checkpoint(
            checkpoint_id="batch:api:b-idem",
            service="api-dev", operation="op",
            item_ids=["txn-1"],
        )
        client.complete(checkpoint_id="batch:api:b-idem")
        client.complete(checkpoint_id="batch:api:b-idem")

        assert _get_item(table, "batch:api:b-idem")["status"] == "completed"


# ------------------------------------------------------------------ #
# 8. get_pending
# ------------------------------------------------------------------ #

class TestGetPending:

    def test_item_tracking_returns_delta(self, client, table):
        client.write_checkpoint(
            checkpoint_id="batch:api:b-pend",
            service="api-dev", operation="op",
            item_ids=["txn-1", "txn-2", "txn-3", "txn-4", "txn-5"],
        )
        client.mark_progress(checkpoint_id="batch:api:b-pend", item_id="txn-1")
        client.mark_progress(checkpoint_id="batch:api:b-pend", item_id="txn-2")

        assert set(client.get_pending(checkpoint_id="batch:api:b-pend")) == {"txn-3", "txn-4", "txn-5"}

    def test_s3_manifest_delta(self, client, table):
        item_ids = [f"item-{i}" for i in range(600)]
        client.write_checkpoint(
            checkpoint_id="batch:api:b-s3",
            service="api-dev", operation="op",
            item_ids=item_ids,
        )
        for i in range(300):
            client.mark_progress(checkpoint_id="batch:api:b-s3", item_id=f"item-{i}")

        pending = client.get_pending(checkpoint_id="batch:api:b-s3")
        assert len(pending) == 300
        assert "item-300" in pending
        assert "item-0" not in pending

    def test_index_based_returns_resume_point(self, client, table):
        client.write_checkpoint(
            checkpoint_id="import:idx:pend",
            service="api-dev", operation="op",
            total_items=50000, mode="index_based",
        )
        client.mark_progress(checkpoint_id="import:idx:pend", index=22500)

        assert client.get_pending(checkpoint_id="import:idx:pend") == 22501

    def test_no_progress_returns_all(self, client, table):
        client.write_checkpoint(
            checkpoint_id="batch:api:b-all",
            service="api-dev", operation="op",
            item_ids=["txn-1", "txn-2", "txn-3"],
        )
        assert set(client.get_pending(checkpoint_id="batch:api:b-all")) == {"txn-1", "txn-2", "txn-3"}

    def test_all_completed_returns_empty(self, client, table):
        client.write_checkpoint(
            checkpoint_id="batch:api:b-empty",
            service="api-dev", operation="op",
            item_ids=["txn-1", "txn-2"],
        )
        client.mark_progress(checkpoint_id="batch:api:b-empty", item_id="txn-1")
        client.mark_progress(checkpoint_id="batch:api:b-empty", item_id="txn-2")

        assert client.get_pending(checkpoint_id="batch:api:b-empty") == []


# ------------------------------------------------------------------ #
# Error key sanitization (pure function — no fixtures needed)
# ------------------------------------------------------------------ #

class TestSanitizeErrorKey:

    def test_replaces_special_chars(self):
        result = _sanitize_error_key("ReadTimeout: downstream API")
        assert ":" not in result
        assert " " not in result
        assert "." not in result

    def test_replaces_brackets_and_hash(self):
        result = _sanitize_error_key("KeyError: ['index'] #ref not found")
        assert "[" not in result
        assert "]" not in result
        assert "#" not in result
        assert "'" not in result

    def test_truncates_long_messages(self):
        assert len(_sanitize_error_key("x" * 200)) <= 120


# ------------------------------------------------------------------ #
# Negative tests — ValueError paths
# ------------------------------------------------------------------ #

class TestValidationErrors:

    def test_write_checkpoint_item_tracking_no_item_ids(self, client):
        with pytest.raises(ValueError, match="item_ids required"):
            client.write_checkpoint(checkpoint_id="cp-1", service="svc", operation="op", item_ids=None)

    def test_write_checkpoint_item_tracking_empty_item_ids(self, client):
        with pytest.raises(ValueError, match="item_ids required"):
            client.write_checkpoint(checkpoint_id="cp-2", service="svc", operation="op", item_ids=[])

    def test_write_checkpoint_index_based_no_total_items(self, client):
        with pytest.raises(ValueError, match="total_items required"):
            client.write_checkpoint(checkpoint_id="cp-3", service="svc", operation="op", mode="index_based")

    def test_write_checkpoint_unknown_mode(self, client):
        with pytest.raises(ValueError, match="Unknown checkpoint mode"):
            client.write_checkpoint(checkpoint_id="cp-4", service="svc", operation="op", mode="unknown")

    def test_mark_progress_both_item_id_and_index(self, client):
        with pytest.raises(ValueError, match="item_id or index, not both"):
            client.mark_progress(checkpoint_id="cp-5", item_id="txn-1", index=0)

    def test_mark_progress_neither_item_id_nor_index(self, client):
        with pytest.raises(ValueError, match="Either item_id or index"):
            client.mark_progress(checkpoint_id="cp-6")

    def test_mark_progress_buffered_no_item_id(self, client):
        with pytest.raises(ValueError, match="item_id required"):
            client.mark_progress_buffered(checkpoint_id="cp-7")

    def test_get_pending_nonexistent_checkpoint(self, client):
        with pytest.raises(ValueError, match="Checkpoint not found"):
            client.get_pending(checkpoint_id="nonexistent-cp")
