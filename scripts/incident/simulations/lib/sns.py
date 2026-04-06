"""SNS message publishing for simulations."""

import json
import boto3
from datetime import datetime, timezone

from . import config

_sns = boto3.client("sns", region_name=config.REGION)


def publish_alarm(
    alarm_name: str,
    state: str = "ALARM",
    old_state: str = "OK",
    reason: str = "Test alarm trigger",
    description: str = "Test alarm",
    function_name: str = "",
    metric_namespace: str = "AWS/Lambda",
    metric_name: str = "Errors",
) -> str:
    """Publish a CloudWatch Alarm format message to the SNS topic.

    Includes Trigger.Dimensions with FunctionName for proper log group derivation.
    Returns the MessageId."""
    now = datetime.now(timezone.utc)

    # Build alarm ARN
    alarm_arn = f"arn:aws:cloudwatch:{config.REGION}:{config.ACCOUNT_ID}:alarm:{alarm_name}"

    message = {
        "AlarmName": alarm_name,
        "AlarmDescription": description,
        "NewStateValue": state,
        "OldStateValue": old_state,
        "NewStateReason": reason,
        "StateChangeTime": now.strftime("%Y-%m-%dT%H:%M:%S.%f%z"),
        "Region": "US West (Oregon)",
        "AWSAccountId": config.ACCOUNT_ID,
        "AlarmArn": alarm_arn,
        "Trigger": {
            "MetricName": metric_name,
            "Namespace": metric_namespace,
            "Dimensions": (
                [{"name": "FunctionName", "value": function_name}]
                if function_name
                else []
            ),
        },
    }

    resp = _sns.publish(
        TopicArn=config.SNS_TOPIC_ARN,
        Message=json.dumps(message),
        Subject=f"{state}: {alarm_name}",
    )
    return resp["MessageId"]
