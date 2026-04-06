"""NotificationRepository — SNS engineer notifications.

All observability concerns (tracing, metrics, logging) handled by @observe decorator."""

import boto3

from shared.middleware.observability import observe


class NotificationRepository:
    """SNS — publish escalation notifications to on-call engineers."""

    def __init__(self, sns_client=None):
        self._sns_client = sns_client or boto3.client("sns")

    @observe(operation="notify_engineer", metric_prefix="sns_notify")
    def notify_engineer(self, topic_arn: str, message: str, severity: str) -> bool:
        """Publishes escalation notification to SNS topic. Returns False on failure."""
        try:
            self._sns_client.publish(
                TopicArn=topic_arn,
                Subject=f"[{severity}] Incident Escalation",
                Message=message,
            )
            return True

        except Exception:
            return False
