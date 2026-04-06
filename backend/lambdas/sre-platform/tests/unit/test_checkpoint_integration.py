"""TC3: Checkpoint SDK integration tests — 8 multi-step scenarios against moto.

Validates end-to-end SDK lifecycle: write → progress → complete/crash → get_pending.
Each scenario exercises a realistic batch processing pattern.

Uses mock_checkpoint_client / mock_checkpoint_table from conftest.py.
"""

from datetime import datetime, timezone, timedelta


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _get_item(table, checkpoint_id):
    return table.get_item(Key={"checkpoint_id": checkpoint_id}).get("Item")


def _is_zombie(item: dict) -> bool:
    """Replicate zombie detection: last_heartbeat older than 2x timeout_seconds."""
    timeout = int(item.get("timeout_seconds", 300))
    last_hb = datetime.fromisoformat(item["last_heartbeat"])
    threshold = timedelta(seconds=timeout * 2)
    return (datetime.now(timezone.utc) - last_hb) > threshold


# ================================================================== #
# Scenario 1: Happy path — full lifecycle
# ================================================================== #

class TestScenario1HappyPath:

    def test_write_progress_all_complete(self, mock_checkpoint_client, mock_checkpoint_table):
        """write → 10 mark_progress → complete → status=completed, 0 pending."""
        _, _, table = mock_checkpoint_table
        ids = [f"txn-{i}" for i in range(10)]

        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="batch:api:s1",
            service="batch-api-dev",
            operation="batch-insert",
            item_ids=ids,
        )

        for item_id in ids:
            mock_checkpoint_client.mark_progress(checkpoint_id="batch:api:s1", item_id=item_id)

        mock_checkpoint_client.complete(checkpoint_id="batch:api:s1")

        item = _get_item(table, "batch:api:s1")
        assert item["status"] == "completed"
        assert item["completed_items"] == set(ids)
        assert mock_checkpoint_client.get_pending(checkpoint_id="batch:api:s1") == []


# ================================================================== #
# Scenario 2: Partial failure — crash after 5/10
# ================================================================== #

class TestScenario2PartialFailure:

    def test_crash_after_5_of_10(self, mock_checkpoint_client, mock_checkpoint_table):
        """write → 5 mark_progress → 'crash' → get_pending = 5 remaining IDs."""
        _, _, table = mock_checkpoint_table
        all_ids = [f"txn-{i}" for i in range(10)]

        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="batch:api:s2",
            service="batch-api-dev",
            operation="batch-insert",
            item_ids=all_ids,
        )

        for item_id in all_ids[:5]:
            mock_checkpoint_client.mark_progress(checkpoint_id="batch:api:s2", item_id=item_id)

        # Simulate crash — no complete() call
        pending = mock_checkpoint_client.get_pending(checkpoint_id="batch:api:s2")
        assert set(pending) == {f"txn-{i}" for i in range(5, 10)}
        assert len(pending) == 5

        # Status still in_progress
        assert _get_item(table, "batch:api:s2")["status"] == "in_progress"


# ================================================================== #
# Scenario 3: Buffered partial — crash loses unflushed buffer
# ================================================================== #

class TestScenario3BufferedPartial:

    def test_buffered_crash_loses_unflushed(self, mock_checkpoint_client, mock_checkpoint_table):
        """write → 137 buffered(flush_every=50) → crash → get_pending = 137 - 100 flushed."""
        _, _, table = mock_checkpoint_table
        all_ids = [f"item-{i}" for i in range(200)]

        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="batch:api:s3",
            service="batch-api-dev",
            operation="csv-import",
            item_ids=all_ids,
        )

        # Buffer 137 items with flush_every=50 → flushes at 50 and 100
        for i in range(137):
            mock_checkpoint_client.mark_progress_buffered(
                checkpoint_id="batch:api:s3",
                item_id=f"item-{i}",
                flush_every=50,
                flush_interval_seconds=9999,  # disable time flush
            )

        # Crash — buffer has 37 unflushed items (items 100-136)
        # DynamoDB only has items 0-99 (flushed at 50 and 100)
        pending = mock_checkpoint_client.get_pending(checkpoint_id="batch:api:s3")
        flushed_count = 100  # 2 flushes of 50
        assert len(pending) == 200 - flushed_count

        # Explicit flush recovers the remaining 37
        mock_checkpoint_client.flush_progress(checkpoint_id="batch:api:s3")
        pending_after = mock_checkpoint_client.get_pending(checkpoint_id="batch:api:s3")
        assert len(pending_after) == 200 - 137


# ================================================================== #
# Scenario 4: Index-based partial
# ================================================================== #

class TestScenario4IndexBased:

    def test_index_based_resume_point(self, mock_checkpoint_client, mock_checkpoint_table):
        """write(total=50000) → mark_progress(index=22500) → get_pending = 22501."""
        _, _, table = mock_checkpoint_table

        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="import:csv:s4",
            service="data-import-dev",
            operation="csv-import",
            total_items=50000,
            mode="index_based",
        )

        mock_checkpoint_client.mark_progress(checkpoint_id="import:csv:s4", index=22500)

        resume_point = mock_checkpoint_client.get_pending(checkpoint_id="import:csv:s4")
        assert resume_point == 22501

        item = _get_item(table, "import:csv:s4")
        assert item["completed_index"] == 22500
        assert item["status"] == "in_progress"


# ================================================================== #
# Scenario 5: Mixed success + failures
# ================================================================== #

class TestScenario5WithFailures:

    def test_success_and_failures_tracked(self, mock_checkpoint_client, mock_checkpoint_table):
        """write → 3 success + 2 failures → get_pending = 5, error_counts populated."""
        _, _, table = mock_checkpoint_table
        all_ids = [f"txn-{i}" for i in range(10)]

        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="batch:api:s5",
            service="batch-api-dev",
            operation="batch-insert",
            item_ids=all_ids,
        )

        # 3 successes
        for i in range(3):
            mock_checkpoint_client.mark_progress(checkpoint_id="batch:api:s5", item_id=f"txn-{i}")

        # 2 failures (still count as "attempted" but not "completed")
        mock_checkpoint_client.log_failure(
            checkpoint_id="batch:api:s5", item_id="txn-3", error_message="ReadTimeout: downstream API",
        )
        mock_checkpoint_client.log_failure(
            checkpoint_id="batch:api:s5", item_id="txn-4", error_message="ReadTimeout: downstream API",
        )

        # 7 pending (failures don't mark progress)
        pending = mock_checkpoint_client.get_pending(checkpoint_id="batch:api:s5")
        assert len(pending) == 7
        assert "txn-0" not in pending  # completed
        assert "txn-3" in pending      # failed but not completed

        # Error context populated
        item = _get_item(table, "batch:api:s5")
        assert item["first_failed_id"] == "txn-3"
        assert item["last_error"] == "ReadTimeout: downstream API"
        assert sum(item["error_counts"].values()) == 2


# ================================================================== #
# Scenario 6: S3 side-loading with large manifest
# ================================================================== #

class TestScenario6S3SideLoading:

    def test_large_manifest_s3_delta(self, mock_checkpoint_client, mock_checkpoint_table):
        """write(1000 items) → 500 mark_progress → get_pending = 500 (loaded from S3)."""
        _, s3, table = mock_checkpoint_table
        all_ids = [f"item-{i}" for i in range(1000)]

        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="batch:api:s6",
            service="batch-api-dev",
            operation="import",
            item_ids=all_ids,
        )

        # Verify S3 manifest was created
        item = _get_item(table, "batch:api:s6")
        assert isinstance(item["all_item_ids"], str)
        assert item["all_item_ids"].startswith("s3://")

        # Process first 500
        for i in range(500):
            mock_checkpoint_client.mark_progress(checkpoint_id="batch:api:s6", item_id=f"item-{i}")

        # Delta = 500 (manifest loaded from S3, completed subtracted)
        pending = mock_checkpoint_client.get_pending(checkpoint_id="batch:api:s6")
        assert len(pending) == 500
        assert "item-0" not in pending
        assert "item-999" in pending


# ================================================================== #
# Scenario 7: Zombie detection — stale heartbeat
# ================================================================== #

class TestScenario7ZombieDetection:

    def test_stale_heartbeat_is_zombie(self, mock_checkpoint_client, mock_checkpoint_table):
        """write(timeout=1s) → no heartbeat → detect zombie via stale last_heartbeat."""
        _, _, table = mock_checkpoint_table

        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="batch:api:s7",
            service="batch-api-dev",
            operation="op",
            item_ids=["txn-1"],
            timeout_seconds=1,  # 1 second timeout → zombie threshold = 2s
        )

        # Manually backdate last_heartbeat to simulate stale checkpoint
        table.update_item(
            Key={"checkpoint_id": "batch:api:s7"},
            UpdateExpression="SET last_heartbeat = :old",
            ExpressionAttributeValues={
                ":old": (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
            },
        )

        item = _get_item(table, "batch:api:s7")
        assert _is_zombie(item) is True


# ================================================================== #
# Scenario 8: Not zombie — recent heartbeat
# ================================================================== #

class TestScenario8NotZombie:

    def test_recent_heartbeat_not_zombie(self, mock_checkpoint_client, mock_checkpoint_table):
        """write → heartbeat within timeout → not zombie."""
        _, _, table = mock_checkpoint_table

        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="batch:api:s8",
            service="batch-api-dev",
            operation="op",
            item_ids=["txn-1"],
            timeout_seconds=300,
        )

        mock_checkpoint_client.heartbeat(checkpoint_id="batch:api:s8")

        item = _get_item(table, "batch:api:s8")
        assert _is_zombie(item) is False
