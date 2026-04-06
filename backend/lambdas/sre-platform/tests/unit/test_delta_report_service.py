"""Tests for DeltaReportService — 15 scenarios covering report formatting and Jira posting.

Uses mock_checkpoint_client to set up checkpoint state, mock_checkpoint_repo for reads,
and a Mock ticketing_repo for Jira assertions.
"""

from unittest.mock import Mock

import pytest

from tests.conftest import DeltaReportService, backdate_heartbeat


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

@pytest.fixture
def mock_ticketing():
    repo = Mock()
    repo.add_jira_comment.return_value = True
    return repo


@pytest.fixture
def delta_service(mock_checkpoint_repo, mock_ticketing):
    return DeltaReportService(
        checkpoint_repo=mock_checkpoint_repo,
        ticketing_repo=mock_ticketing,
    )


# ================================================================== #
# 1. Single checkpoint, small pending, with errors
# ================================================================== #

class TestSingleCheckpointSmall:

    def test_full_delta_report(self, mock_checkpoint_client, delta_service, mock_ticketing, mock_checkpoint_table):
        _, _, table = mock_checkpoint_table

        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="batch:api:d-001",
            service="batch-api-dev",
            operation="batch-insert",
            item_ids=[f"txn-{i}" for i in range(10)],
        )
        for i in range(5):
            mock_checkpoint_client.mark_progress(checkpoint_id="batch:api:d-001", item_id=f"txn-{i}")
        mock_checkpoint_client.log_failure(
            checkpoint_id="batch:api:d-001", item_id="txn-5", error_message="ReadTimeout",
        )

        result = delta_service.generate_and_post(
            service_name="batch-api-dev", jira_ticket_id="INC-100",
        )

        assert result["checkpoints_found"] == 1
        assert result["total_pending"] == 5
        assert result["report_posted"] is True

        comment = mock_ticketing.add_jira_comment.call_args[0][1]
        assert "batch:api:d-001" in comment
        assert "5/10" in comment
        assert "Pending IDs" in comment
        assert "Top Error: ReadTimeout" in comment


# ================================================================== #
# 2. Single checkpoint, large pending (>50)
# ================================================================== #

class TestSingleCheckpointLarge:

    def test_large_batch_summary(self, mock_checkpoint_client, delta_service, mock_ticketing):
        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="batch:api:d-large",
            service="large-batch-dev",
            operation="import",
            item_ids=[f"item-{i}" for i in range(200)],
        )
        for i in range(100):
            mock_checkpoint_client.mark_progress(checkpoint_id="batch:api:d-large", item_id=f"item-{i}")

        result = delta_service.generate_and_post(
            service_name="large-batch-dev", jira_ticket_id="INC-101",
        )

        assert result["total_pending"] == 100
        comment = mock_ticketing.add_jira_comment.call_args[0][1]
        assert "too many to list" in comment
        assert "Pending IDs" not in comment


# ================================================================== #
# 3. Multiple checkpoints for same service
# ================================================================== #

class TestMultipleCheckpoints:

    def test_grouped_summary(self, mock_checkpoint_client, delta_service, mock_ticketing):
        for i in range(3):
            mock_checkpoint_client.write_checkpoint(
                checkpoint_id=f"batch:api:d-multi-{i}",
                service="multi-dev",
                operation=f"op-{i}",
                item_ids=[f"item-{i}-{j}" for j in range(10)],
            )
            for j in range(i + 1):  # 1, 2, 3 completed respectively
                mock_checkpoint_client.mark_progress(
                    checkpoint_id=f"batch:api:d-multi-{i}", item_id=f"item-{i}-{j}",
                )

        result = delta_service.generate_and_post(
            service_name="multi-dev", jira_ticket_id="INC-102",
        )

        assert result["checkpoints_found"] == 3
        # 9 + 8 + 7 = 24 pending
        assert result["total_pending"] == 24
        comment = mock_ticketing.add_jira_comment.call_args[0][1]
        assert "Checkpoints found: 3" in comment
        assert "Total pending" in comment


# ================================================================== #
# 4. Zero pending — all completed
# ================================================================== #

class TestZeroPending:

    def test_batch_completed_before_detection(self, mock_checkpoint_client, delta_service, mock_ticketing):
        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="batch:api:d-done",
            service="done-dev",
            operation="op",
            item_ids=["a", "b"],
        )
        mock_checkpoint_client.mark_progress(checkpoint_id="batch:api:d-done", item_id="a")
        mock_checkpoint_client.mark_progress(checkpoint_id="batch:api:d-done", item_id="b")
        # Note: NOT calling complete() — status still in_progress so scan_incomplete finds it

        result = delta_service.generate_and_post(
            service_name="done-dev", jira_ticket_id="INC-103",
        )

        assert result["total_pending"] == 0
        comment = mock_ticketing.add_jira_comment.call_args[0][1]
        assert "completed before detection" in comment


# ================================================================== #
# 5. Zero completed — no progress
# ================================================================== #

class TestZeroCompleted:

    def test_no_progress_report(self, mock_checkpoint_client, delta_service, mock_ticketing):
        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="batch:api:d-zero",
            service="zero-dev",
            operation="op",
            item_ids=[f"item-{i}" for i in range(100)],
        )

        result = delta_service.generate_and_post(
            service_name="zero-dev", jira_ticket_id="INC-104",
        )

        assert result["total_pending"] == 100
        comment = mock_ticketing.add_jira_comment.call_args[0][1]
        assert "0/100" in comment
        assert "0%" in comment


# ================================================================== #
# 6. Zombie detected
# ================================================================== #

class TestZombieDetected:

    def test_zombie_flag_in_report(self, mock_checkpoint_client, delta_service, mock_ticketing, mock_checkpoint_table):
        _, _, table = mock_checkpoint_table

        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="batch:api:d-zombie",
            service="zombie-dev",
            operation="op",
            item_ids=["a", "b"],
            timeout_seconds=60,
        )
        backdate_heartbeat(table, "batch:api:d-zombie", seconds_ago=200)

        result = delta_service.generate_and_post(
            service_name="zombie-dev", jira_ticket_id="INC-105",
        )

        assert result["zombies_found"] == 1
        comment = mock_ticketing.add_jira_comment.call_args[0][1]
        assert "Zombie: YES" in comment


# ================================================================== #
# 7. Not zombie — recent heartbeat
# ================================================================== #

class TestNotZombie:

    def test_no_zombie_flag(self, mock_checkpoint_client, delta_service, mock_ticketing):
        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="batch:api:d-alive",
            service="alive-dev",
            operation="op",
            item_ids=["a"],
            timeout_seconds=300,
        )
        mock_checkpoint_client.heartbeat(checkpoint_id="batch:api:d-alive")

        result = delta_service.generate_and_post(
            service_name="alive-dev", jira_ticket_id="INC-106",
        )

        assert result["zombies_found"] == 0
        comment = mock_ticketing.add_jira_comment.call_args[0][1]
        assert "Zombie" not in comment


# ================================================================== #
# 8. Error context: top error + count
# ================================================================== #

class TestErrorContext:

    def test_top_error_displayed(self, mock_checkpoint_client, delta_service, mock_ticketing):
        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="batch:api:d-err",
            service="err-dev",
            operation="op",
            item_ids=[f"txn-{i}" for i in range(10)],
        )
        for i in range(5):
            mock_checkpoint_client.log_failure(
                checkpoint_id="batch:api:d-err", item_id=f"txn-{i}", error_message="ReadTimeout",
            )

        delta_service.generate_and_post(service_name="err-dev", jira_ticket_id="INC-107")

        comment = mock_ticketing.add_jira_comment.call_args[0][1]
        assert "Top Error:" in comment
        assert "5 occurrences" in comment


# ================================================================== #
# 9. Error context: multiple errors
# ================================================================== #

class TestMultipleErrors:

    def test_other_errors_line(self, mock_checkpoint_client, delta_service, mock_ticketing):
        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="batch:api:d-multi-err",
            service="multi-err-dev",
            operation="op",
            item_ids=[f"txn-{i}" for i in range(10)],
        )
        for i in range(3):
            mock_checkpoint_client.log_failure(
                checkpoint_id="batch:api:d-multi-err", item_id=f"txn-{i}", error_message="ReadTimeout",
            )
        mock_checkpoint_client.log_failure(
            checkpoint_id="batch:api:d-multi-err", item_id="txn-3", error_message="ConnectionReset",
        )

        delta_service.generate_and_post(service_name="multi-err-dev", jira_ticket_id="INC-108")

        comment = mock_ticketing.add_jira_comment.call_args[0][1]
        assert "Top Error:" in comment
        assert "Other Errors:" in comment


# ================================================================== #
# 10. First failed ID shown
# ================================================================== #

class TestFirstFailedId:

    def test_first_failed_id_in_report(self, mock_checkpoint_client, delta_service, mock_ticketing):
        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="batch:api:d-fid",
            service="fid-dev",
            operation="op",
            item_ids=["POL-776", "POL-777"],
        )
        mock_checkpoint_client.log_failure(
            checkpoint_id="batch:api:d-fid", item_id="POL-776", error_message="Timeout",
        )

        delta_service.generate_and_post(service_name="fid-dev", jira_ticket_id="INC-109")

        comment = mock_ticketing.add_jira_comment.call_args[0][1]
        assert "First Failed ID: POL-776" in comment


# ================================================================== #
# 11. No error context — app didn't call log_failure
# ================================================================== #

class TestNoErrorContext:

    def test_graceful_fallback(self, mock_checkpoint_client, delta_service, mock_ticketing):
        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="batch:api:d-noerr",
            service="noerr-dev",
            operation="op",
            item_ids=["a", "b", "c"],
        )

        delta_service.generate_and_post(service_name="noerr-dev", jira_ticket_id="INC-110")

        comment = mock_ticketing.add_jira_comment.call_args[0][1]
        assert "Not reported by application" in comment


# ================================================================== #
# 12. Index-based checkpoint report
# ================================================================== #

class TestIndexBasedReport:

    def test_resume_from_index_format(self, mock_checkpoint_client, delta_service, mock_ticketing):
        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="import:csv:d-idx",
            service="idx-dev",
            operation="csv-import",
            total_items=50000,
            mode="index_based",
        )
        mock_checkpoint_client.mark_progress(checkpoint_id="import:csv:d-idx", index=22500)

        delta_service.generate_and_post(service_name="idx-dev", jira_ticket_id="INC-111")

        comment = mock_ticketing.add_jira_comment.call_args[0][1]
        assert "Resume from index: 22,501" in comment
        assert "22500/50000" in comment


# ================================================================== #
# 13. Jira comment posted successfully
# ================================================================== #

class TestJiraPostSuccess:

    def test_report_posted_flag(self, mock_checkpoint_client, delta_service, mock_ticketing):
        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="batch:api:d-jira",
            service="jira-dev",
            operation="op",
            item_ids=["a"],
        )

        result = delta_service.generate_and_post(
            service_name="jira-dev", jira_ticket_id="INC-112",
        )

        assert result["report_posted"] is True
        mock_ticketing.add_jira_comment.assert_called_once()


# ================================================================== #
# 14. Jira comment failed
# ================================================================== #

class TestJiraPostFailure:

    def test_returns_false_no_raise(self, mock_checkpoint_client, delta_service, mock_ticketing):
        mock_ticketing.add_jira_comment.side_effect = Exception("Jira unavailable")

        mock_checkpoint_client.write_checkpoint(
            checkpoint_id="batch:api:d-jfail",
            service="jfail-dev",
            operation="op",
            item_ids=["a"],
        )

        result = delta_service.generate_and_post(
            service_name="jfail-dev", jira_ticket_id="INC-113",
        )

        assert result["report_posted"] is False
        assert result["checkpoints_found"] == 1


# ================================================================== #
# 15. No incomplete checkpoints found
# ================================================================== #

class TestNoCheckpointsFound:

    def test_returns_zero_no_comment(self, delta_service, mock_ticketing):
        result = delta_service.generate_and_post(
            service_name="empty-dev", jira_ticket_id="INC-114",
        )

        assert result == {
            "checkpoints_found": 0,
            "total_pending": 0,
            "zombies_found": 0,
            "report_posted": False,
        }
        mock_ticketing.add_jira_comment.assert_not_called()
