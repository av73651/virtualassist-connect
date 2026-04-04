"""Reusable SRE Platform monitoring construct.

Adds CloudWatch alarms connected to SRE Platform for ANY Lambda function.
Usage: add_sre_monitoring(self, my_lambda, "my-service", "dev")
"""

from aws_cdk import (
    Duration,
    Fn,
    aws_lambda as lambda_,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_sns as sns,
)
from constructs import Construct


def add_sre_monitoring(
    scope: Construct,
    lambda_fn: lambda_.Function,
    service_name: str,
    stage: str,
    error_threshold: int = 10,
    evaluation_periods: int = 2,
) -> cloudwatch.Alarm:
    """Add SRE Platform monitoring to any Lambda function.

    Creates a CloudWatch alarm monitoring custom error metrics emitted by
    the @observe decorator. Connects alarm to SRE Platform SNS topic for
    automated incident detection and triage.

    Args:
        scope: CDK construct scope
        lambda_fn: Lambda function to monitor
        service_name: Service name (used in alarm name and metric namespace)
        stage: Deployment stage (dev, staging, prod)
        error_threshold: Error count threshold (default: 10)
        evaluation_periods: Number of periods to evaluate (default: 2)

    Returns:
        cloudwatch.Alarm: Created alarm (for further customization if needed)

    Example:
        # In any Lambda stack:
        add_sre_monitoring(self, my_lambda, "user-service", "dev")

        # Custom threshold:
        add_sre_monitoring(self, my_lambda, "order-service", "prod", error_threshold=5)
    """
    # Import SRE Platform SNS topic
    alarm_topic_arn = Fn.import_value(f"IncidentAlarmTopicArn-{stage}")
    alarm_topic = sns.Topic.from_topic_arn(
        scope,
        f"{service_name}SREAlarmTopic",
        alarm_topic_arn
    )

    # Create alarm on custom error metrics
    alarm = cloudwatch.Alarm(
        scope,
        f"{service_name}CustomErrorRate",
        alarm_name=f"{service_name}-custom-error-rate-{stage}",
        metric=cloudwatch.Metric(
            namespace=f"CustomMetrics/{service_name}",
            metric_name="Errors",
            statistic="Sum",
            period=Duration.minutes(5)
        ),
        threshold=error_threshold,
        evaluation_periods=evaluation_periods,
        comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
        alarm_description=f"Alert when {service_name} error count exceeds threshold",
        treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
    )

    # Connect alarm to SRE Platform
    alarm.add_alarm_action(cw_actions.SnsAction(alarm_topic))

    # Add SERVICE_NAME environment variable to Lambda (required for @observe)
    lambda_fn.add_environment("SERVICE_NAME", service_name)

    # Grant Lambda permission to publish custom metrics
    lambda_fn.add_to_role_policy(
        statement=_create_cloudwatch_metrics_policy()
    )

    return alarm


def _create_cloudwatch_metrics_policy():
    """Create IAM policy statement for publishing CloudWatch metrics.

    Note: CloudWatch IAM conditions on namespace don't work reliably because
    the namespace is not available during IAM authorization evaluation.
    Instead, we grant PutMetricData permission and rely on application code
    to only emit metrics to CustomMetrics/* namespaces.
    """
    from aws_cdk import aws_iam as iam

    return iam.PolicyStatement(
        actions=["cloudwatch:PutMetricData"],
        resources=["*"],  # CloudWatch metrics are not ARN-addressable
        # Note: Removed namespace condition - doesn't work with PutMetricData
    )
