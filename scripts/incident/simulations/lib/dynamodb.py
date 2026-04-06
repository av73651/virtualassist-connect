"""DynamoDB correlation table operations for simulations."""

import time
import boto3
from datetime import datetime, timezone, timedelta

from . import config

_ddb = boto3.resource("dynamodb", region_name=config.REGION)
_table = _ddb.Table(config.DYNAMODB_TABLE)


def get_record(incident_key: str) -> dict | None:
    """Get a correlation record by incident_key. Returns None if not found."""
    resp = _table.get_item(Key={"incident_key": incident_key})
    return resp.get("Item")


def put_record(item: dict) -> None:
    """Direct PutItem — used to inject GRACE records for escalation simulation."""
    _table.put_item(Item=item)


def delete_record(incident_key: str) -> None:
    """Delete a single record."""
    _table.delete_item(Key={"incident_key": incident_key})


def wait_for_record(incident_key: str, timeout: int = 60, poll: int = 3) -> dict | None:
    """Poll until record appears. Returns record or None on timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        record = get_record(incident_key)
        if record:
            return record
        time.sleep(poll)
    return None


def wait_for_status(incident_key: str, status: str, timeout: int = 60, poll: int = 3) -> dict | None:
    """Poll until record reaches expected status. Returns record or None."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        record = get_record(incident_key)
        if record and record.get("status") == status:
            return record
        time.sleep(poll)
    return None


def wait_for_deletion(incident_key: str, timeout: int = 60, poll: int = 3) -> bool:
    """Poll until record is deleted. Returns True if deleted within timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        record = get_record(incident_key)
        if record is None:
            return True
        time.sleep(poll)
    return False


def scan_sim_records() -> list[dict]:
    """Scan for all records with sim- prefix in incident_key."""
    items = []
    resp = _table.scan(
        FilterExpression="begins_with(incident_key, :prefix)",
        ExpressionAttributeValues={":prefix": f"{config.SIM_PREFIX}-"},
    )
    items.extend(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        resp = _table.scan(
            FilterExpression="begins_with(incident_key, :prefix)",
            ExpressionAttributeValues={":prefix": f"{config.SIM_PREFIX}-"},
            ExclusiveStartKey=resp["LastEvaluatedKey"],
        )
        items.extend(resp.get("Items", []))
    return items


def delete_sim_records() -> list[str]:
    """Delete all simulation records. Returns deleted incident_keys."""
    records = scan_sim_records()
    for record in records:
        delete_record(record["incident_key"])
    return [r["incident_key"] for r in records]


def build_grace_record(incident_key: str, jira_ticket_id: str, severity: str = "SEV-1") -> dict:
    """Build a GRACE status record for escalation simulation."""
    now = datetime.now(timezone.utc)
    ttl = int((now + timedelta(hours=24)).timestamp())
    return {
        "incident_key": incident_key,
        "jira_ticket_id": jira_ticket_id,
        "severity": severity,
        "status": "GRACE",
        "created_at": now.isoformat(),
        "ttl": ttl,
        "gsi_pk": "ALL",
    }
