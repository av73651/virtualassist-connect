"""Tests for CorrelationRepository — DynamoDB CRUD, conditional writes, GSI storm detection.

Uses moto for DynamoDB mocking."""

import boto3
import pytest
from datetime import datetime, timezone, timedelta
from moto import mock_aws

from src.models.correlation_record import CorrelationRecord
from src.models.enums import CorrelationStatus
from src.models.exceptions import DuplicateIncidentError
from src.repositories.correlation_repository import CorrelationRepository


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

@pytest.fixture
def dynamodb_table():
    """Create moto DynamoDB table with GSI for storm detection."""
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-west-2")
        table = dynamodb.create_table(
            TableName="incident-correlation-dev",
            KeySchema=[{"AttributeName": "incident_key", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "incident_key", "AttributeType": "S"},
                {"AttributeName": "gsi_pk", "AttributeType": "S"},
                {"AttributeName": "created_at", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "created_at-index",
                    "KeySchema": [
                        {"AttributeName": "gsi_pk", "KeyType": "HASH"},
                        {"AttributeName": "created_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                    "ProvisionedThroughput": {
                        "ReadCapacityUnits": 5,
                        "WriteCapacityUnits": 5,
                    },
                }
            ],
            ProvisionedThroughput={
                "ReadCapacityUnits": 5,
                "WriteCapacityUnits": 5,
            },
        )
        table.meta.client.get_waiter("table_exists").wait(
            TableName="incident-correlation-dev"
        )
        yield dynamodb


@pytest.fixture
def repo(dynamodb_table):
    """CorrelationRepository backed by moto DynamoDB."""
    return CorrelationRepository(
        table_name="incident-correlation-dev",
        dynamodb_resource=dynamodb_table,
    )


@pytest.fixture
def sample_record(fixed_now):
    """RESERVED record for testing."""
    return CorrelationRecord.reserve("calculator-error-rate-prod", "SEV-1", now=fixed_now)


# ------------------------------------------------------------------ #
# Reserve with Conditional Write
# ------------------------------------------------------------------ #

class TestReserve:
    """Reserve creates record with conditional write."""

    def test_reserve_success(self, repo, sample_record):
        """Reserve succeeds on empty table, returns True."""
        result = repo.reserve(sample_record)

        assert result is True

    def test_reserve_creates_record(self, repo, sample_record):
        """Reserved record retrievable via get."""
        repo.reserve(sample_record)

        retrieved = repo.get("calculator-error-rate-prod")
        assert retrieved is not None
        assert retrieved.incident_key == "calculator-error-rate-prod"
        assert retrieved.status == CorrelationStatus.RESERVED
        assert retrieved.severity == "SEV-1"
        assert retrieved.jira_ticket_id is None


# ------------------------------------------------------------------ #
# Reserve Conflict Raises DuplicateIncidentError
# ------------------------------------------------------------------ #

class TestReserveConflict:
    """Duplicate reserve raises DuplicateIncidentError."""

    def test_duplicate_reserve_raises_error(self, repo, sample_record):
        """Second reserve with same key raises DuplicateIncidentError."""
        repo.reserve(sample_record)

        with pytest.raises(DuplicateIncidentError):
            repo.reserve(sample_record)

    def test_existing_record_unchanged_after_conflict(self, repo, sample_record):
        """Original record not modified by failed reserve."""
        repo.reserve(sample_record)

        try:
            repo.reserve(sample_record)
        except DuplicateIncidentError:
            pass

        retrieved = repo.get("calculator-error-rate-prod")
        assert retrieved.status == CorrelationStatus.RESERVED
        assert retrieved.created_at == sample_record.created_at


# ------------------------------------------------------------------ #
# Get
# ------------------------------------------------------------------ #

class TestGet:
    """Get retrieves records or returns None."""

    def test_get_existing_record(self, repo, sample_record):
        """Get returns record when it exists."""
        repo.reserve(sample_record)

        result = repo.get("calculator-error-rate-prod")
        assert result is not None
        assert result.incident_key == "calculator-error-rate-prod"

    def test_get_nonexistent_returns_none(self, repo):
        """Get returns None for missing key."""
        result = repo.get("nonexistent-key")
        assert result is None


# ------------------------------------------------------------------ #
# Update
# ------------------------------------------------------------------ #

class TestUpdate:
    """Update modifies existing records."""

    def test_update_status_to_detected(self, repo, sample_record):
        """Update transitions RESERVED to DETECTED with ticket ID."""
        repo.reserve(sample_record)

        detected = sample_record.associate_jira_ticket("INC-142")
        repo.update(detected)

        retrieved = repo.get("calculator-error-rate-prod")
        assert retrieved.status == CorrelationStatus.DETECTED
        assert retrieved.jira_ticket_id == "INC-142"

    def test_update_to_grace(self, repo, sample_record, fixed_now):
        """Update transitions to GRACE with new TTL."""
        repo.reserve(sample_record)
        detected = sample_record.associate_jira_ticket("INC-142")
        repo.update(detected)

        resolved_at = fixed_now + timedelta(hours=2)
        grace = detected.to_grace(resolved_at, 900)
        repo.update(grace)

        retrieved = repo.get("calculator-error-rate-prod")
        assert retrieved.status == CorrelationStatus.GRACE
        expected_ttl = int((resolved_at + timedelta(seconds=900)).timestamp())
        assert retrieved.ttl == expected_ttl

    def test_update_preserves_all_fields(self, repo, sample_record):
        """Update preserves incident_key, severity, created_at."""
        repo.reserve(sample_record)
        detected = sample_record.associate_jira_ticket("INC-142")
        repo.update(detected)

        retrieved = repo.get("calculator-error-rate-prod")
        assert retrieved.severity == "SEV-1"
        assert retrieved.created_at == sample_record.created_at


# ------------------------------------------------------------------ #
# Delete
# ------------------------------------------------------------------ #

class TestDelete:
    """Delete removes records."""

    def test_delete_existing_record(self, repo, sample_record):
        """Delete removes record, get returns None after."""
        repo.reserve(sample_record)
        repo.delete("calculator-error-rate-prod")

        result = repo.get("calculator-error-rate-prod")
        assert result is None

    def test_delete_nonexistent_no_error(self, repo):
        """Delete on missing key does not raise."""
        repo.delete("nonexistent-key")  # Should not raise


# ------------------------------------------------------------------ #
# Count Recent (Storm Detection via GSI)
# ------------------------------------------------------------------ #

class TestCountRecent:
    """Storm detection query via GSI."""

    def test_count_recent_within_window(self, repo):
        """Counts only records within the time window (gt, not gte)."""
        now = datetime(2026, 3, 30, 12, 10, 0, tzinfo=timezone.utc)

        # 6 records within last 2 minutes (created_at > since)
        for i in range(6):
            ts = now - timedelta(seconds=15 * i)  # 0s, 15s, 30s, 45s, 60s, 75s back
            record = CorrelationRecord.reserve(f"service-{i}-error-rate-prod", "SEV-1", now=ts)
            repo.reserve(record)

        # 2 records older than 2 minutes
        for i in range(2):
            ts = now - timedelta(minutes=3, seconds=i * 30)
            record = CorrelationRecord.reserve(f"old-{i}-error-rate-prod", "SEV-2", now=ts)
            repo.reserve(record)

        since = (now - timedelta(seconds=120)).isoformat()
        count = repo.count_recent(since)

        assert count == 6

    def test_count_recent_empty_table(self, repo):
        """Returns 0 on empty table."""
        since = datetime(2026, 3, 30, 12, 0, 0, tzinfo=timezone.utc).isoformat()
        count = repo.count_recent(since)

        assert count == 0

    def test_count_recent_all_outside_window(self, repo):
        """Returns 0 when all records are outside the window."""
        old_time = datetime(2026, 3, 30, 10, 0, 0, tzinfo=timezone.utc)
        record = CorrelationRecord.reserve("service-error-rate-prod", "SEV-1", now=old_time)
        repo.reserve(record)

        since = datetime(2026, 3, 30, 12, 0, 0, tzinfo=timezone.utc).isoformat()
        count = repo.count_recent(since)

        assert count == 0


# ------------------------------------------------------------------ #
# TTL Attribute Set Correctly
# ------------------------------------------------------------------ #

class TestTTLAttribute:
    """TTL values correct in DynamoDB."""

    def test_reserved_ttl_24_hours(self, repo, fixed_now):
        """RESERVED record TTL = created_at + 24 hours."""
        record = CorrelationRecord.reserve("calc-error-rate-prod", "SEV-1", now=fixed_now)
        repo.reserve(record)

        retrieved = repo.get("calc-error-rate-prod")
        expected_ttl = int((fixed_now + timedelta(hours=24)).timestamp())
        assert retrieved.ttl == expected_ttl

    def test_grace_ttl_15_minutes(self, repo, fixed_now):
        """GRACE record TTL = resolved_at + grace_period_seconds."""
        record = CorrelationRecord.reserve("calc-error-rate-prod", "SEV-1", now=fixed_now)
        repo.reserve(record)

        detected = record.associate_jira_ticket("INC-142")
        resolved_at = fixed_now + timedelta(hours=2)
        grace = detected.to_grace(resolved_at, 900)
        repo.update(grace)

        retrieved = repo.get("calc-error-rate-prod")
        expected_ttl = int((resolved_at + timedelta(seconds=900)).timestamp())
        assert retrieved.ttl == expected_ttl

    def test_gsi_pk_attribute_stored(self, repo, sample_record):
        """DynamoDB item includes gsi_pk='ALL' for storm detection GSI."""
        repo.reserve(sample_record)

        # Direct table scan to verify raw item
        table = repo._table
        response = table.get_item(Key={"incident_key": "calculator-error-rate-prod"})
        assert response["Item"]["gsi_pk"] == "ALL"


# ------------------------------------------------------------------ #
# Roundtrip integrity
# ------------------------------------------------------------------ #

class TestRoundtrip:
    """Full CRUD roundtrip through DynamoDB."""

    def test_full_lifecycle(self, repo, fixed_now):
        """Reserve -> get -> update(DETECTED) -> update(GRACE) -> delete."""
        # Reserve
        record = CorrelationRecord.reserve("calc-error-rate-prod", "SEV-1", now=fixed_now)
        repo.reserve(record)

        # Get
        retrieved = repo.get("calc-error-rate-prod")
        assert retrieved.status == CorrelationStatus.RESERVED

        # Update to DETECTED
        detected = retrieved.associate_jira_ticket("INC-142")
        repo.update(detected)
        retrieved = repo.get("calc-error-rate-prod")
        assert retrieved.status == CorrelationStatus.DETECTED
        assert retrieved.jira_ticket_id == "INC-142"

        # Update to GRACE
        resolved_at = fixed_now + timedelta(hours=2)
        grace = retrieved.to_grace(resolved_at, 900)
        repo.update(grace)
        retrieved = repo.get("calc-error-rate-prod")
        assert retrieved.status == CorrelationStatus.GRACE

        # Delete
        repo.delete("calc-error-rate-prod")
        assert repo.get("calc-error-rate-prod") is None
