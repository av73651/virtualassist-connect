"""Tests for checkpoint DynamoDB table schema — GSI queries + TTL + concurrency.

Validates:
1. GSI query: service + status=in_progress returns targeted results (not scan)
2. GSI query: no matching results returns empty
3. GSI query: multiple checkpoints for same service returns all
4. TTL attribute stored correctly for DynamoDB auto-expiry
5. Concurrent writes to same checkpoint_id — last-writer-wins for status
"""

import time

from boto3.dynamodb.conditions import Key


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _query_gsi(table, service: str, status: str) -> list[dict]:
    """Query service-status-index GSI."""
    resp = table.query(
        IndexName="service-status-index",
        KeyConditionExpression=Key("service").eq(service) & Key("status").eq(status),
    )
    return resp.get("Items", [])


# ------------------------------------------------------------------ #
# 1. GSI query: service + status=in_progress (targeted lookup)
# ------------------------------------------------------------------ #

class TestGSIQuery:

    def test_gsi_returns_in_progress_for_service(self, mock_checkpoint_client, mock_checkpoint_table):
        """GSI query returns only in_progress checkpoints for a specific service."""
        _, _, table = mock_checkpoint_table

        # Create 2 checkpoints for same service
        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="batch:api:b-001",
            service="batch-processor-api-dev",
            operation="batch-insert",
            item_ids=["txn-1", "txn-2"],
        )
        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="batch:api:b-002",
            service="batch-processor-api-dev",
            operation="csv-import",
            item_ids=["row-1"],
        )

        # Complete one of them
        mock_checkpoint_client.complete(checkpoint_id="batch:api:b-001")

        # GSI query: only in_progress for this service
        in_progress = _query_gsi(table, "batch-processor-api-dev", "in_progress")
        assert len(in_progress) == 1
        assert in_progress[0]["checkpoint_id"] == "batch:api:b-002"

        # Completed one also queryable
        completed = _query_gsi(table, "batch-processor-api-dev", "completed")
        assert len(completed) == 1
        assert completed[0]["checkpoint_id"] == "batch:api:b-001"

    # ------------------------------------------------------------------ #
    # 2. GSI query: no results
    # ------------------------------------------------------------------ #

    def test_gsi_returns_empty_when_no_match(self, mock_checkpoint_table):
        """GSI query for nonexistent service returns empty list."""
        _, _, table = mock_checkpoint_table

        result = _query_gsi(table, "nonexistent-service", "in_progress")
        assert result == []

    # ------------------------------------------------------------------ #
    # 3. GSI query: multiple checkpoints for same service
    # ------------------------------------------------------------------ #

    def test_gsi_returns_all_for_service(self, mock_checkpoint_client, mock_checkpoint_table):
        """GSI query returns all in_progress checkpoints for a service."""
        _, _, table = mock_checkpoint_table

        for i in range(5):
            mock_checkpoint_client.write_checkpoint(
                checkpoint_id=f"batch:api:b-{i:03d}",
                service="multi-batch-dev",
                operation="import",
                item_ids=[f"item-{i}"],
            )

        in_progress = _query_gsi(table, "multi-batch-dev", "in_progress")
        assert len(in_progress) == 5
        ids = {item["checkpoint_id"] for item in in_progress}
        assert ids == {f"batch:api:b-{i:03d}" for i in range(5)}


# ------------------------------------------------------------------ #
# 4. TTL attribute
# ------------------------------------------------------------------ #

class TestTTLAttribute:

    def test_ttl_is_future_epoch(self, mock_checkpoint_client, mock_checkpoint_table):
        """TTL stored as epoch seconds in the future."""
        _, _, table = mock_checkpoint_table

        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="batch:api:b-ttl",
            service="api-dev",
            operation="op",
            item_ids=["a"],
            timeout_seconds=300,
            ttl_hours=24,
        )

        resp = table.get_item(Key={"checkpoint_id": "batch:api:b-ttl"})
        item = resp["Item"]

        assert "ttl" in item
        now_epoch = int(time.time())
        # TTL should be at least 24h from now (86400s)
        assert item["ttl"] > now_epoch + 86000  # small tolerance
        # TTL should be less than 48h from now
        assert item["ttl"] < now_epoch + 172800

    def test_ttl_uses_timeout_multiplier_when_larger(self, mock_checkpoint_client, mock_checkpoint_table):
        """TTL = max(ttl_hours * 3600, timeout_seconds * 4)."""
        _, _, table = mock_checkpoint_table

        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="batch:api:b-ttl2",
            service="api-dev",
            operation="op",
            item_ids=["a"],
            timeout_seconds=86400,  # 24h * 4 = 96h > 24h
            ttl_hours=24,
        )

        resp = table.get_item(Key={"checkpoint_id": "batch:api:b-ttl2"})
        item = resp["Item"]

        now_epoch = int(time.time())
        # TTL should be at least 96h from now (timeout * 4)
        assert item["ttl"] > now_epoch + (86400 * 4) - 60


# ------------------------------------------------------------------ #
# 5. Concurrent writes — last-writer-wins
# ------------------------------------------------------------------ #

class TestConcurrentWrites:

    def test_last_writer_wins_on_status(self, mock_checkpoint_client, mock_checkpoint_table):
        """Two status updates to same checkpoint — last write determines final state."""
        _, _, table = mock_checkpoint_table

        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="batch:api:b-race",
            service="api-dev",
            operation="op",
            item_ids=["txn-1", "txn-2"],
        )

        # Simulate two concurrent operations
        mock_checkpoint_client.mark_progress(checkpoint_id="batch:api:b-race", item_id="txn-1")
        mock_checkpoint_client.complete(checkpoint_id="batch:api:b-race")

        resp = table.get_item(Key={"checkpoint_id": "batch:api:b-race"})
        item = resp["Item"]
        assert item["status"] == "completed"

    def test_gsi_reflects_latest_status(self, mock_checkpoint_client, mock_checkpoint_table):
        """GSI query reflects the latest status after update."""
        _, _, table = mock_checkpoint_table

        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="batch:api:b-gsi-update",
            service="gsi-test-dev",
            operation="op",
            item_ids=["txn-1"],
        )

        # Initially in_progress
        in_progress = _query_gsi(table, "gsi-test-dev", "in_progress")
        assert len(in_progress) == 1

        # Complete it
        mock_checkpoint_client.complete(checkpoint_id="batch:api:b-gsi-update")

        # GSI should now show completed, not in_progress
        in_progress_after = _query_gsi(table, "gsi-test-dev", "in_progress")
        completed_after = _query_gsi(table, "gsi-test-dev", "completed")
        assert len(in_progress_after) == 0
        assert len(completed_after) == 1
