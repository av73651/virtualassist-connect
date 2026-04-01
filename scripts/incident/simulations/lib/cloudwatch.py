"""CloudWatch alarm management for simulations."""

import boto3
from datetime import datetime, timezone

from . import config

_cw = boto3.client("cloudwatch", region_name=config.REGION)


def ensure_alarm(alarm_name: str, description: str = "Simulation test alarm") -> None:
    """Create a metric alarm. Uses a dummy metric so we can control state."""
    _cw.put_metric_alarm(
        AlarmName=alarm_name,
        AlarmDescription=description,
        MetricName=config.METRIC_NAME,
        Namespace=config.METRIC_NAMESPACE,
        Statistic="Maximum",
        Period=300,
        EvaluationPeriods=1,
        Threshold=0,
        ComparisonOperator="GreaterThanThreshold",
        TreatMissingData="notBreaching",
    )


def set_state(alarm_name: str, state: str, reason: str = "Simulation") -> None:
    """Force alarm state AND push metric data so state persists through cool-off."""
    _cw.set_alarm_state(
        AlarmName=alarm_name,
        StateValue=state,
        StateReason=reason,
    )
    # Push metric data to keep alarm in desired state through evaluation
    if state == "ALARM":
        _cw.put_metric_data(
            Namespace=config.METRIC_NAMESPACE,
            MetricData=[{
                "MetricName": config.METRIC_NAME,
                "Value": 100.0,
                "Timestamp": datetime.now(timezone.utc),
            }],
        )


def get_state(alarm_name: str) -> str:
    """Get current alarm state."""
    resp = _cw.describe_alarms(AlarmNames=[alarm_name])
    alarms = resp.get("MetricAlarms", [])
    if not alarms:
        return "NOT_FOUND"
    return alarms[0].get("StateValue", "UNKNOWN")


def delete_alarm(alarm_name: str) -> None:
    """Delete a single alarm."""
    _cw.delete_alarms(AlarmNames=[alarm_name])


def list_sim_alarms() -> list[str]:
    """List all alarms with the simulation prefix."""
    alarms = []
    paginator = _cw.get_paginator("describe_alarms")
    for page in paginator.paginate():
        for alarm in page.get("MetricAlarms", []):
            name = alarm["AlarmName"]
            if name.startswith(f"{config.SIM_PREFIX}-"):
                alarms.append(name)
    return alarms


def delete_sim_alarms() -> list[str]:
    """Delete all simulation alarms. Returns list of deleted names."""
    names = list_sim_alarms()
    if names:
        # delete_alarms accepts max 100 at a time
        for i in range(0, len(names), 100):
            _cw.delete_alarms(AlarmNames=names[i:i + 100])
    return names
