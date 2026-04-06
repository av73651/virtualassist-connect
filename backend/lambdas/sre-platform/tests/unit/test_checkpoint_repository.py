"""Tests for CheckpointRepository — platform read layer (ARCH-002).

8 tests: scan_incomplete, get_checkpoint, get_pending (item + index + S3), detect_zombie.
Uses mock_checkpoint_client to write data, mock_checkpoint_repo to read it.
"""

from tests.conftest import backdate_heartbeat


# ================================================================== #
# scan_incomplete
# ================================================================== #

class TestScanIncomplete:

    def test_returns_in_progress_checkpoints(self, mock_checkpoint_client, mock_checkpoint_repo):
        """GSI query returns only in_progress checkpoints for a service."""
        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="batch:api:r-001",
            service="batch-api-dev",
            operation="import",
            item_ids=["a", "b"],
        )
        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="batch:api:r-002",
            service="batch-api-dev",
            operation="export",
            item_ids=["c"],
        )
        # Complete one
        mock_checkpoint_client.complete(checkpoint_id="batch:api:r-001")

        result = mock_checkpoint_repo.scan_incomplete(service_name="batch-api-dev")
        assert len(result) == 1
        assert result[0]["checkpoint_id"] == "batch:api:r-002"

    def test_returns_empty_for_unknown_service(self, mock_checkpoint_repo):
        assert mock_checkpoint_repo.scan_incomplete(service_name="nonexistent") == []


# ================================================================== #
# get_checkpoint
# ================================================================== #

class TestGetCheckpoint:

    def test_returns_checkpoint(self, mock_checkpoint_client, mock_checkpoint_repo):
        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="batch:api:r-get",
            service="api-dev",
            operation="op",
            item_ids=["a"],
        )
        cp = mock_checkpoint_repo.get_checkpoint(checkpoint_id="batch:api:r-get")
        assert cp is not None
        assert cp["checkpoint_id"] == "batch:api:r-get"

    def test_returns_none_for_missing(self, mock_checkpoint_repo):
        assert mock_checkpoint_repo.get_checkpoint(checkpoint_id="nope") is None


# ================================================================== #
# get_pending
# ================================================================== #

class TestGetPending:

    def test_item_tracking_delta(self, mock_checkpoint_client, mock_checkpoint_repo):
        """get_pending computes all_item_ids - completed_items."""
        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="batch:api:r-pend",
            service="api-dev",
            operation="op",
            item_ids=["a", "b", "c", "d", "e"],
        )
        mock_checkpoint_client.mark_progress(checkpoint_id="batch:api:r-pend", item_id="a")
        mock_checkpoint_client.mark_progress(checkpoint_id="batch:api:r-pend", item_id="b")

        cp = mock_checkpoint_repo.get_checkpoint(checkpoint_id="batch:api:r-pend")
        pending = mock_checkpoint_repo.get_pending(checkpoint=cp)
        assert set(pending) == {"c", "d", "e"}

    def test_index_based_resume(self, mock_checkpoint_client, mock_checkpoint_repo):
        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="import:r-idx",
            service="api-dev",
            operation="op",
            total_items=1000,
            mode="index_based",
        )
        mock_checkpoint_client.mark_progress(checkpoint_id="import:r-idx", index=499)

        cp = mock_checkpoint_repo.get_checkpoint(checkpoint_id="import:r-idx")
        assert mock_checkpoint_repo.get_pending(checkpoint=cp) == 500

    def test_s3_manifest_delta(self, mock_checkpoint_client, mock_checkpoint_repo):
        """Large manifest loaded from S3 for delta computation."""
        ids = [f"item-{i}" for i in range(600)]
        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="batch:api:r-s3",
            service="api-dev",
            operation="op",
            item_ids=ids,
        )
        for i in range(300):
            mock_checkpoint_client.mark_progress(checkpoint_id="batch:api:r-s3", item_id=f"item-{i}")

        cp = mock_checkpoint_repo.get_checkpoint(checkpoint_id="batch:api:r-s3")
        pending = mock_checkpoint_repo.get_pending(checkpoint=cp)
        assert len(pending) == 300


# ================================================================== #
# detect_zombie
# ================================================================== #

class TestDetectZombie:

    def test_stale_heartbeat_is_zombie(self, mock_checkpoint_client, mock_checkpoint_repo, mock_checkpoint_table):
        _, _, table = mock_checkpoint_table

        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="batch:api:r-zombie",
            service="api-dev",
            operation="op",
            item_ids=["a"],
            timeout_seconds=60,
        )
        backdate_heartbeat(table, "batch:api:r-zombie", seconds_ago=200)

        cp = mock_checkpoint_repo.get_checkpoint(checkpoint_id="batch:api:r-zombie")
        assert mock_checkpoint_repo.detect_zombie(cp) is True

    def test_recent_heartbeat_not_zombie(self, mock_checkpoint_client, mock_checkpoint_repo):
        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="batch:api:r-alive",
            service="api-dev",
            operation="op",
            item_ids=["a"],
            timeout_seconds=300,
        )
        mock_checkpoint_client.heartbeat(checkpoint_id="batch:api:r-alive")

        cp = mock_checkpoint_repo.get_checkpoint(checkpoint_id="batch:api:r-alive")
        assert mock_checkpoint_repo.detect_zombie(cp) is False
