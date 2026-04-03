# Incident Management Pipeline -- Infrastructure Design

## Overview

CDK infrastructure for the incident management pipeline. One new stack (`IncidentManagerStack`) containing all resources for the 3-Lambda pipeline. Follows patterns established in `calculator_stack.py`.

**Key difference from calculator/hello-world stacks**: No API Gateway, no Cognito authorizer, no WAF. This stack is event-driven (SNS + EventBridge triggers), not HTTP-triggered.

---

## 1. Stack Architecture

```
IncidentManagerStack
  |
  +-- SNS Topic (alarm ingestion)
  |     +-- SQS DLQ (failed Detection Lambda invocations)
  |
  +-- Detection Lambda (SNS trigger)
  |     +-- IAM Role (DynamoDB, CloudWatch, Jira secrets, EventBridge, Logs)
  |     +-- Log Group (structured JSON, retention per env)
  |
  +-- Triage Lambda (EventBridge trigger)
  |     +-- IAM Role (DynamoDB, CloudWatch, Jira secrets, EventBridge, Lambda control plane, Logs)
  |     +-- Log Group
  |
  +-- Escalation Lambda (EventBridge trigger)
  |     +-- IAM Role (DynamoDB, CloudWatch, Jira secrets, SNS notifications, Logs)
  |     +-- Log Group
  |
  +-- DynamoDB Table (incident_correlation)
  |     +-- GSI: created_at-index (storm detection)
  |     +-- TTL enabled on `ttl` attribute
  |
  +-- EventBridge Rules
  |     +-- IncidentCreated -> Triage Lambda
  |     +-- EscalationRequired -> Escalation Lambda
  |     +-- DLQs for each rule
  |
  +-- SNS Topic (engineer notifications)
  |
  +-- Secrets Manager (Jira credentials reference)
  |
  +-- CloudWatch Dashboard
  +-- CloudWatch Alarms
```

---

## 2. Config Extension

Add incident manager config to `infra/config.json`:

```json
{
  "dev": {
    "incident_manager": {
      "detection_lambda": {
        "memory_size": 512,
        "timeout_seconds": 180
      },
      "triage_lambda": {
        "memory_size": 512,
        "timeout_seconds": 300
      },
      "escalation_lambda": {
        "memory_size": 256,
        "timeout_seconds": 30
      },
      "dynamodb": {
        "billing_mode": "PAY_PER_REQUEST"
      },
      "sns_alarm_topic_name": "incident-alarm-ingestion",
      "sns_notification_topic_name": "incident-engineer-notifications",
      "jira_secret_name": "incident-manager/jira-credentials",
      "jira_url": "https://rameshnag2002.atlassian.net"
    }
  },
  "prod": {
    "incident_manager": {
      "detection_lambda": {
        "memory_size": 1024,
        "timeout_seconds": 180
      },
      "triage_lambda": {
        "memory_size": 1024,
        "timeout_seconds": 300
      },
      "escalation_lambda": {
        "memory_size": 512,
        "timeout_seconds": 30
      },
      "dynamodb": {
        "billing_mode": "PAY_PER_REQUEST"
      },
      "sns_alarm_topic_name": "incident-alarm-ingestion",
      "sns_notification_topic_name": "incident-engineer-notifications",
      "jira_secret_name": "incident-manager/jira-credentials",
      "jira_url": "https://rameshnag2002.atlassian.net"
    }
  }
}
```

**Notes**:
- Lambda timeouts are fixed by design (based on worst-case sleep durations), not tuneable per env.
- Memory is tuneable per env (prod gets more for faster cold starts).
- DynamoDB uses PAY_PER_REQUEST -- low-frequency alarm events don't justify provisioned capacity.

---

## 3. CDK Stack Definition

**File**: `infra/stacks/incident_manager_stack.py`

```python
"""Incident Manager CDK Stack.

Infrastructure for the 3-Lambda incident management pipeline:
Detection (SNS trigger), Triage (EventBridge trigger), Escalation (EventBridge trigger).
"""

from aws_cdk import (
    Stack,
    aws_lambda as lambda_,
    aws_dynamodb as dynamodb,
    aws_sns as sns,
    aws_sns_subscriptions as subs,
    aws_sqs as sqs,
    aws_events as events,
    aws_events_targets as targets,
    aws_logs as logs,
    aws_iam as iam,
    aws_cloudwatch as cloudwatch,
    aws_secretsmanager as secretsmanager,
    Duration,
    RemovalPolicy,
    CfnOutput
)
from constructs import Construct


_LOG_RETENTION_MAP = {
    7: logs.RetentionDays.ONE_WEEK,
    30: logs.RetentionDays.ONE_MONTH,
    90: logs.RetentionDays.THREE_MONTHS,
    365: logs.RetentionDays.ONE_YEAR
}


class IncidentManagerStack(Stack):
    """CDK stack for the Incident Management Pipeline.

    Creates 3 Lambdas, DynamoDB correlation table, SNS topics,
    EventBridge rules, CloudWatch dashboard, and alarms.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        config: dict,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.config = config
        self.im_config = config["incident_manager"]
        self.stage = config["api_gateway"]["stage_name"]
        self.log_retention = _LOG_RETENTION_MAP.get(
            config.get("log_retention_days", 7),
            logs.RetentionDays.ONE_WEEK
        )

        # Core resources
        self.correlation_table = self._create_dynamodb_table()
        self.alarm_topic = self._create_alarm_sns_topic()
        self.notification_topic = self._create_notification_sns_topic()
        self.jira_secret = self._reference_jira_secret()

        # Lambdas
        self.detection_lambda = self._create_detection_lambda()
        self.triage_lambda = self._create_triage_lambda()
        self.escalation_lambda = self._create_escalation_lambda()

        # SNS -> Detection Lambda subscription
        self._create_sns_subscription()

        # EventBridge rules
        self._create_eventbridge_rules()

        # Observability
        self._create_dashboard()
        self._create_alarms()

        # Outputs
        self._create_outputs()

    # ------------------------------------------------------------------ #
    # DynamoDB
    # ------------------------------------------------------------------ #

    def _create_dynamodb_table(self) -> dynamodb.Table:
        """Create incident_correlation table with GSI and TTL."""
        table = dynamodb.Table(
            self, "CorrelationTable",
            table_name=f"incident-correlation-{self.stage}",
            partition_key=dynamodb.Attribute(
                name="incident_key",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY if self.stage == "dev" else RemovalPolicy.RETAIN,
            time_to_live_attribute="ttl",
            point_in_time_recovery=True if self.stage == "prod" else False
        )

        # GSI for storm detection: count recent incidents by created_at
        table.add_global_secondary_index(
            index_name="created_at-index",
            partition_key=dynamodb.Attribute(
                name="gsi_pk",       # Fixed value "ALL" written by application
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="created_at",
                type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.KEYS_ONLY
        )

        return table

    # ------------------------------------------------------------------ #
    # SNS Topics
    # ------------------------------------------------------------------ #

    def _create_alarm_sns_topic(self) -> sns.Topic:
        """Shared SNS topic for CloudWatch alarm ingestion."""
        return sns.Topic(
            self, "AlarmIngestionTopic",
            topic_name=f"{self.im_config['sns_alarm_topic_name']}-{self.stage}",
            display_name="Incident Manager - Alarm Ingestion"
        )

    def _create_notification_sns_topic(self) -> sns.Topic:
        """SNS topic for engineer notifications (SEV-1/SEV-2)."""
        return sns.Topic(
            self, "EngineerNotificationTopic",
            topic_name=f"{self.im_config['sns_notification_topic_name']}-{self.stage}",
            display_name="Incident Manager - Engineer Notifications"
        )

    # ------------------------------------------------------------------ #
    # Secrets Manager
    # ------------------------------------------------------------------ #

    def _reference_jira_secret(self) -> secretsmanager.ISecret:
        """Reference existing Jira credentials secret.
        Secret must be pre-created with Jira API token."""
        return secretsmanager.Secret.from_secret_name_v2(
            self, "JiraSecret",
            secret_name=self.im_config["jira_secret_name"]
        )

    # ------------------------------------------------------------------ #
    # Lambda Functions
    # ------------------------------------------------------------------ #

    def _create_lambda_role(self, name: str, policy_statements: list[iam.PolicyStatement]) -> iam.Role:
        """Create least-privilege IAM role for a Lambda."""
        role = iam.Role(
            self, f"{name}Role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description=f"Execution role for {name} Lambda",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AWSXRayDaemonWriteAccess"
                )
            ]
        )
        for stmt in policy_statements:
            role.add_to_policy(stmt)
        return role

    def _common_lambda_env(self, service_name: str) -> dict:
        """Common environment variables for all incident manager Lambdas."""
        return {
            "LOG_LEVEL": self.config["lambda"]["log_level"],
            "CORRELATION_TABLE_NAME": self.correlation_table.table_name,
            "JIRA_SECRET_NAME": self.im_config["jira_secret_name"],
            "JIRA_URL": self.im_config["jira_url"],
            "EVENT_BUS_NAME": "default",
            "STAGE": self.stage,
            # ADOT auto-instrumentation
            "AWS_LAMBDA_EXEC_WRAPPER": "/opt/otel-instrument",
            "OTEL_SERVICE_NAME": service_name,
            "OTEL_TRACES_SAMPLER": self.config.get("trace_sampling", "always_on"),
            "OTEL_METRICS_EXPORTER": "otlp",
            "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc",
            "OTEL_PROPAGATORS": "tracecontext,baggage,xray",
            "OTEL_RESOURCE_ATTRIBUTES": f"service.name={service_name},service.namespace=VirtualAssist"
        }

    def _shared_layers(self) -> list[lambda_.ILayerVersion]:
        """Shared Lambda layers: application code layer + ADOT."""
        shared_layer = lambda_.LayerVersion(
            self, "SharedCodeLayer",
            code=lambda_.Code.from_asset("../backend/lambda-layer"),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            description="Shared middleware and config for all Lambdas"
        )

        adot_layer_arn = self.config.get(
            "adot_layer_arn",
            f"arn:aws:lambda:{Stack.of(self).region}:901920570463:layer:aws-otel-python-amd64-ver-1-20-0:1"
        )
        adot_layer = lambda_.LayerVersion.from_layer_version_arn(
            self, "ADOTLayer", adot_layer_arn
        )

        return [shared_layer, adot_layer]

    def _create_detection_lambda(self) -> lambda_.Function:
        """Detection Lambda -- SNS trigger, Leg 1."""
        lam_config = self.im_config["detection_lambda"]

        role = self._create_lambda_role("Detection", [
            # DynamoDB: full CRUD + GSI query (reserve, get, update, delete, count_recent)
            iam.PolicyStatement(
                actions=[
                    "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
                    "dynamodb:DeleteItem", "dynamodb:Query"
                ],
                resources=[
                    self.correlation_table.table_arn,
                    f"{self.correlation_table.table_arn}/index/*"
                ]
            ),
            # CloudWatch: alarm state check (cool-off)
            iam.PolicyStatement(
                actions=["cloudwatch:DescribeAlarms"],
                resources=["*"]
            ),
            # CloudWatch Logs: collect recovery logs
            iam.PolicyStatement(
                actions=["logs:FilterLogEvents", "logs:GetLogEvents", "logs:StartQuery", "logs:GetQueryResults", "logs:StopQuery"],
                resources=[f"arn:aws:logs:{Stack.of(self).region}:{Stack.of(self).account}:log-group:*"]
            ),
            # Secrets Manager: Jira credentials
            iam.PolicyStatement(
                actions=["secretsmanager:GetSecretValue"],
                resources=[self.jira_secret.secret_arn]
            ),
            # EventBridge: publish IncidentCreated
            iam.PolicyStatement(
                actions=["events:PutEvents"],
                resources=[f"arn:aws:events:{Stack.of(self).region}:{Stack.of(self).account}:event-bus/default"]
            ),
        ])

        detection = lambda_.Function(
            self, "DetectionFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="src.handlers.detection_handler.lambda_handler",
            code=lambda_.Code.from_asset("../backend/lambdas/incident-manager/package"),
            function_name=f"incident-detection-{self.stage}",
            description="Incident Detection Lambda (Leg 1) - SNS alarm ingestion",
            memory_size=lam_config["memory_size"],
            timeout=Duration.seconds(lam_config["timeout_seconds"]),
            role=role,
            tracing=lambda_.Tracing.ACTIVE,
            layers=self._shared_layers(),
            environment=self._common_lambda_env("incident-detection"),
            log_retention=self.log_retention,
            retry_attempts=0  # SNS handles retries; avoid double-processing
        )

        return detection

    def _create_triage_lambda(self) -> lambda_.Function:
        """Triage Lambda -- EventBridge trigger, Leg 2."""
        lam_config = self.im_config["triage_lambda"]

        role = self._create_lambda_role("Triage", [
            # DynamoDB: get, update (status transitions)
            iam.PolicyStatement(
                actions=["dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem"],
                resources=[self.correlation_table.table_arn]
            ),
            # CloudWatch: alarm state (verification), logs (analysis)
            iam.PolicyStatement(
                actions=["cloudwatch:DescribeAlarms"],
                resources=["*"]
            ),
            iam.PolicyStatement(
                actions=["logs:FilterLogEvents", "logs:GetLogEvents", "logs:StartQuery", "logs:GetQueryResults", "logs:StopQuery"],
                resources=[f"arn:aws:logs:{Stack.of(self).region}:{Stack.of(self).account}:log-group:*"]
            ),
            # Secrets Manager: Jira credentials
            iam.PolicyStatement(
                actions=["secretsmanager:GetSecretValue"],
                resources=[self.jira_secret.secret_arn]
            ),
            # EventBridge: publish EscalationRequired, IncidentAutoResolved
            iam.PolicyStatement(
                actions=["events:PutEvents"],
                resources=[f"arn:aws:events:{Stack.of(self).region}:{Stack.of(self).account}:event-bus/default"]
            ),
            # Lambda control plane: remediation actions (rollback, memory, concurrency)
            iam.PolicyStatement(
                actions=[
                    "lambda:GetFunction", "lambda:GetFunctionConfiguration",
                    "lambda:UpdateFunctionConfiguration",
                    "lambda:ListVersionsByFunction", "lambda:GetAlias", "lambda:UpdateAlias",
                    "lambda:PutFunctionConcurrency",
                    "lambda:InvokeFunction"  # Recovery: backlog-drain Lambda trigger
                ],
                resources=[f"arn:aws:lambda:{Stack.of(self).region}:{Stack.of(self).account}:function:*"]
            ),
            # Step Functions: recovery workflow triggers (replay, reprocess, data-correction)
            iam.PolicyStatement(
                actions=["states:StartExecution"],
                resources=[f"arn:aws:states:{Stack.of(self).region}:{Stack.of(self).account}:stateMachine:*"]
            ),
        ])

        triage = lambda_.Function(
            self, "TriageFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="src.handlers.triage_handler.lambda_handler",
            code=lambda_.Code.from_asset("../backend/lambdas/incident-manager/package"),
            function_name=f"incident-triage-{self.stage}",
            description="Incident Triage Lambda (Leg 2) - analysis, remediation, verification, recovery",
            memory_size=lam_config["memory_size"],
            timeout=Duration.seconds(lam_config["timeout_seconds"]),
            role=role,
            tracing=lambda_.Tracing.ACTIVE,
            layers=self._shared_layers(),
            environment={
                **self._common_lambda_env("incident-triage"),
                # Recovery workflow ARNs (populated when workflows exist; empty = skip)
                "REPLAY_DLQ_WORKFLOW_ARN": self.im_config.get("replay_dlq_workflow_arn", ""),
                "REPROCESS_BATCH_WORKFLOW_ARN": self.im_config.get("reprocess_batch_workflow_arn", ""),
                "RECONCILIATION_WORKFLOW_ARN": self.im_config.get("reconciliation_workflow_arn", ""),
                "BACKLOG_DRAIN_FUNCTION_NAME": self.im_config.get("backlog_drain_function_name", ""),
            },
            log_retention=self.log_retention,
            retry_attempts=0  # EventBridge handles retries
        )

        return triage

    def _create_escalation_lambda(self) -> lambda_.Function:
        """Escalation Lambda -- EventBridge trigger, Leg 3."""
        lam_config = self.im_config["escalation_lambda"]

        role = self._create_lambda_role("Escalation", [
            # DynamoDB: get, update (status -> ESCALATED)
            iam.PolicyStatement(
                actions=["dynamodb:GetItem", "dynamodb:UpdateItem"],
                resources=[self.correlation_table.table_arn]
            ),
            # CloudWatch Logs: collect diagnostic logs for Jira attachments
            iam.PolicyStatement(
                actions=["logs:FilterLogEvents", "logs:GetLogEvents", "logs:StartQuery", "logs:GetQueryResults", "logs:StopQuery"],
                resources=[f"arn:aws:logs:{Stack.of(self).region}:{Stack.of(self).account}:log-group:*"]
            ),
            # Secrets Manager: Jira credentials
            iam.PolicyStatement(
                actions=["secretsmanager:GetSecretValue"],
                resources=[self.jira_secret.secret_arn]
            ),
            # SNS: engineer notifications
            iam.PolicyStatement(
                actions=["sns:Publish"],
                resources=[self.notification_topic.topic_arn]
            ),
        ])

        escalation = lambda_.Function(
            self, "EscalationFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="src.handlers.escalation_handler.lambda_handler",
            code=lambda_.Code.from_asset("../backend/lambdas/incident-manager/package"),
            function_name=f"incident-escalation-{self.stage}",
            description="Incident Escalation Lambda (Leg 3) - Jira enrichment, engineer notification",
            memory_size=lam_config["memory_size"],
            timeout=Duration.seconds(lam_config["timeout_seconds"]),
            role=role,
            tracing=lambda_.Tracing.ACTIVE,
            layers=self._shared_layers(),
            environment={
                **self._common_lambda_env("incident-escalation"),
                "NOTIFICATION_TOPIC_ARN": self.notification_topic.topic_arn
            },
            log_retention=self.log_retention,
            retry_attempts=0
        )

        return escalation

    # ------------------------------------------------------------------ #
    # SNS Subscription (Alarm -> Detection Lambda)
    # ------------------------------------------------------------------ #

    def _create_sns_subscription(self) -> None:
        """Subscribe Detection Lambda to alarm ingestion SNS topic with DLQ."""
        dlq = sqs.Queue(
            self, "DetectionDLQ",
            queue_name=f"incident-detection-dlq-{self.stage}",
            retention_period=Duration.days(14)
        )

        self.alarm_topic.add_subscription(
            subs.LambdaSubscription(
                self.detection_lambda,
                dead_letter_queue=dlq
            )
        )

        self.detection_dlq = dlq

    # ------------------------------------------------------------------ #
    # EventBridge Rules
    # ------------------------------------------------------------------ #

    def _create_eventbridge_rules(self) -> None:
        """Create EventBridge rules for pipeline orchestration."""

        # DLQ for failed EventBridge -> Lambda deliveries
        triage_dlq = sqs.Queue(
            self, "TriageDLQ",
            queue_name=f"incident-triage-dlq-{self.stage}",
            retention_period=Duration.days(14)
        )

        escalation_dlq = sqs.Queue(
            self, "EscalationDLQ",
            queue_name=f"incident-escalation-dlq-{self.stage}",
            retention_period=Duration.days(14)
        )

        # IncidentCreated -> Triage Lambda
        events.Rule(
            self, "IncidentCreatedRule",
            rule_name=f"incident-created-to-triage-{self.stage}",
            description="Routes IncidentCreated events to Triage Lambda",
            event_pattern=events.EventPattern(
                source=["incident-manager"],
                detail_type=["IncidentCreated"]
            ),
            targets=[
                targets.LambdaFunction(
                    self.triage_lambda,
                    dead_letter_queue=triage_dlq,
                    retry_attempts=2
                )
            ]
        )

        # EscalationRequired -> Escalation Lambda
        events.Rule(
            self, "EscalationRequiredRule",
            rule_name=f"escalation-required-to-escalation-{self.stage}",
            description="Routes EscalationRequired events to Escalation Lambda",
            event_pattern=events.EventPattern(
                source=["incident-manager"],
                detail_type=["EscalationRequired"]
            ),
            targets=[
                targets.LambdaFunction(
                    self.escalation_lambda,
                    dead_letter_queue=escalation_dlq,
                    retry_attempts=2
                )
            ]
        )

        self.triage_dlq = triage_dlq
        self.escalation_dlq = escalation_dlq

    # ------------------------------------------------------------------ #
    # CloudWatch Dashboard
    # ------------------------------------------------------------------ #

    def _create_dashboard(self) -> None:
        """Create CloudWatch dashboard for incident management observability."""
        dashboard = cloudwatch.Dashboard(
            self, "IncidentDashboard",
            dashboard_name=f"incident-manager-dashboard-{self.stage}"
        )

        # Row 1: Lambda invocations (all 3 Lambdas)
        dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Lambda Invocations",
                left=[
                    self.detection_lambda.metric_invocations(label="Detection"),
                    self.triage_lambda.metric_invocations(label="Triage"),
                    self.escalation_lambda.metric_invocations(label="Escalation"),
                ],
                width=12
            ),
            cloudwatch.GraphWidget(
                title="Lambda Errors",
                left=[
                    self.detection_lambda.metric_errors(label="Detection"),
                    self.triage_lambda.metric_errors(label="Triage"),
                    self.escalation_lambda.metric_errors(label="Escalation"),
                ],
                width=12
            )
        )

        # Row 2: Lambda duration (p50, p95 per Lambda)
        dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Detection Duration (ms)",
                left=[
                    self.detection_lambda.metric_duration(statistic="p50", label="p50"),
                    self.detection_lambda.metric_duration(statistic="p95", label="p95"),
                ],
                width=8
            ),
            cloudwatch.GraphWidget(
                title="Triage Duration (ms)",
                left=[
                    self.triage_lambda.metric_duration(statistic="p50", label="p50"),
                    self.triage_lambda.metric_duration(statistic="p95", label="p95"),
                ],
                width=8
            ),
            cloudwatch.GraphWidget(
                title="Escalation Duration (ms)",
                left=[
                    self.escalation_lambda.metric_duration(statistic="p50", label="p50"),
                    self.escalation_lambda.metric_duration(statistic="p95", label="p95"),
                ],
                width=8
            )
        )

        # Row 3: Custom OTel metrics (incident pipeline effectiveness)
        otel_ns = "VirtualAssist"
        dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Incidents Created vs Auto-Resolved vs Escalated",
                left=[
                    cloudwatch.Metric(
                        namespace=otel_ns,
                        metric_name="detection_total",
                        dimensions_map={"service.name": "incident-detection", "status": "success"},
                        statistic="Sum", label="Created", color="#1f77b4"
                    ),
                    cloudwatch.Metric(
                        namespace=otel_ns,
                        metric_name="triage_total",
                        dimensions_map={"service.name": "incident-triage", "status": "success"},
                        statistic="Sum", label="Triaged", color="#2ca02c"
                    ),
                    cloudwatch.Metric(
                        namespace=otel_ns,
                        metric_name="escalation_total",
                        dimensions_map={"service.name": "incident-escalation", "status": "success"},
                        statistic="Sum", label="Escalated", color="#d62728"
                    ),
                ],
                width=12
            ),
            cloudwatch.GraphWidget(
                title="Cool-Off Filter Rate",
                left=[
                    cloudwatch.Metric(
                        namespace=otel_ns,
                        metric_name="detection_cooloff_total",
                        dimensions_map={"service.name": "incident-detection", "status": "success"},
                        statistic="Sum", label="Filtered (transient)", color="#ff7f0e"
                    ),
                ],
                width=12
            )
        )

        # Row 4: DLQ depth
        dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="DLQ Messages (Unprocessed Events)",
                left=[
                    self.detection_dlq.metric_approximate_number_of_messages_visible(label="Detection DLQ"),
                    self.triage_dlq.metric_approximate_number_of_messages_visible(label="Triage DLQ"),
                    self.escalation_dlq.metric_approximate_number_of_messages_visible(label="Escalation DLQ"),
                ],
                width=24
            )
        )

        # Row 5: DynamoDB
        dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="DynamoDB Read/Write Capacity",
                left=[
                    self.correlation_table.metric_consumed_read_capacity_units(label="Reads"),
                    self.correlation_table.metric_consumed_write_capacity_units(label="Writes"),
                ],
                width=12
            ),
            cloudwatch.GraphWidget(
                title="DynamoDB Throttles",
                left=[
                    self.correlation_table.metric("ReadThrottleEvents", statistic="Sum", label="Read Throttles"),
                    self.correlation_table.metric("WriteThrottleEvents", statistic="Sum", label="Write Throttles"),
                ],
                width=12
            )
        )

    # ------------------------------------------------------------------ #
    # CloudWatch Alarms
    # ------------------------------------------------------------------ #

    def _create_alarms(self) -> None:
        """Create CloudWatch alarms for operational monitoring."""

        # Detection Lambda errors
        cloudwatch.Alarm(
            self, "DetectionErrorAlarm",
            alarm_name=f"incident-detection-errors-{self.stage}",
            metric=self.detection_lambda.metric_errors(statistic="Sum"),
            threshold=5,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description="Detection Lambda error rate exceeds threshold"
        )

        # Triage Lambda errors
        cloudwatch.Alarm(
            self, "TriageErrorAlarm",
            alarm_name=f"incident-triage-errors-{self.stage}",
            metric=self.triage_lambda.metric_errors(statistic="Sum"),
            threshold=3,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description="Triage Lambda error rate exceeds threshold"
        )

        # Escalation Lambda errors
        cloudwatch.Alarm(
            self, "EscalationErrorAlarm",
            alarm_name=f"incident-escalation-errors-{self.stage}",
            metric=self.escalation_lambda.metric_errors(statistic="Sum"),
            threshold=3,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description="Escalation Lambda error rate exceeds threshold"
        )

        # Detection Lambda duration (approaching timeout)
        cloudwatch.Alarm(
            self, "DetectionDurationAlarm",
            alarm_name=f"incident-detection-duration-{self.stage}",
            metric=self.detection_lambda.metric_duration(statistic="p99"),
            threshold=150000,  # 150s (timeout is 180s)
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description="Detection Lambda approaching timeout (150s of 180s)"
        )

        # Triage Lambda duration (approaching timeout)
        cloudwatch.Alarm(
            self, "TriageDurationAlarm",
            alarm_name=f"incident-triage-duration-{self.stage}",
            metric=self.triage_lambda.metric_duration(statistic="p99"),
            threshold=270000,  # 270s (timeout is 300s)
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description="Triage Lambda approaching timeout (270s of 300s)"
        )

        # DLQ depth alarms (NFR-006)
        for name, queue in [
            ("Detection", self.detection_dlq),
            ("Triage", self.triage_dlq),
            ("Escalation", self.escalation_dlq),
        ]:
            cloudwatch.Alarm(
                self, f"{name}DLQDepthAlarm",
                alarm_name=f"incident-{name.lower()}-dlq-depth-{self.stage}",
                metric=queue.metric_approximate_number_of_messages_visible(),
                threshold=1,
                evaluation_periods=1,
                comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
                alarm_description=f"{name} DLQ has unprocessed events -- investigate failed incident processing"
            )

        # DynamoDB throttle alarm
        cloudwatch.Alarm(
            self, "DynamoDBThrottleAlarm",
            alarm_name=f"incident-dynamodb-throttle-{self.stage}",
            metric=self.correlation_table.metric("WriteThrottleEvents", statistic="Sum"),
            threshold=1,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            alarm_description="DynamoDB correlation table experiencing write throttles"
        )

    # ------------------------------------------------------------------ #
    # Outputs
    # ------------------------------------------------------------------ #

    def _create_outputs(self) -> None:
        """Create stack outputs for cross-stack references."""
        CfnOutput(self, "AlarmTopicArn",
                  value=self.alarm_topic.topic_arn,
                  description="SNS topic ARN for CloudWatch alarm ingestion",
                  export_name=f"IncidentAlarmTopicArn-{self.stage}")

        CfnOutput(self, "NotificationTopicArn",
                  value=self.notification_topic.topic_arn,
                  description="SNS topic ARN for engineer notifications",
                  export_name=f"IncidentNotificationTopicArn-{self.stage}")

        CfnOutput(self, "CorrelationTableName",
                  value=self.correlation_table.table_name,
                  description="DynamoDB correlation table name",
                  export_name=f"IncidentCorrelationTable-{self.stage}")

        CfnOutput(self, "DetectionFunctionName",
                  value=self.detection_lambda.function_name,
                  description="Detection Lambda function name",
                  export_name=f"IncidentDetectionLambda-{self.stage}")

        CfnOutput(self, "TriageFunctionName",
                  value=self.triage_lambda.function_name,
                  description="Triage Lambda function name",
                  export_name=f"IncidentTriageLambda-{self.stage}")

        CfnOutput(self, "EscalationFunctionName",
                  value=self.escalation_lambda.function_name,
                  description="Escalation Lambda function name",
                  export_name=f"IncidentEscalationLambda-{self.stage}")
```

---

## 4. CDK App Registration

Add to `infra/app.py`:

```python
from stacks.incident_manager_stack import IncidentManagerStack

# Incident Manager Stack
IncidentManagerStack(
    app,
    f"IncidentManagerStack-{target_env}",
    env=aws_env,
    config=config,
    description=f"Incident Management Pipeline Stack ({target_env})"
)
```

**Note**: Unlike calculator/hello-world stacks, the incident manager stack does NOT take `user_pool` -- it has no API Gateway or Cognito authorizer.

---

## 5. Service Stack Alarm Integration

Existing service stacks (calculator, hello-world, future services) onboard by adding the alarm SNS topic as an alarm action. Example change to `calculator_stack.py`:

```python
# Import the alarm topic ARN from IncidentManagerStack output
alarm_topic_arn = Fn.import_value(f"IncidentAlarmTopicArn-{stage}")
alarm_topic = sns.Topic.from_topic_arn(self, "IncidentAlarmTopic", alarm_topic_arn)

# Add alarm action to existing alarms
high_error_alarm.add_alarm_action(cloudwatch_actions.SnsAction(alarm_topic))
high_error_alarm.add_ok_action(cloudwatch_actions.SnsAction(alarm_topic))

high_latency_alarm.add_alarm_action(cloudwatch_actions.SnsAction(alarm_topic))
high_latency_alarm.add_ok_action(cloudwatch_actions.SnsAction(alarm_topic))
```

This is the only change needed to onboard a service -- alarm action pointing to the shared SNS topic (FR-010).

---

## 6. IAM Permission Summary

Least-privilege per Lambda:

| Permission | Detection | Triage | Escalation |
|------------|-----------|--------|------------|
| DynamoDB GetItem | Yes | Yes | Yes |
| DynamoDB PutItem | Yes (reserve) | -- | -- |
| DynamoDB UpdateItem | Yes | Yes | Yes |
| DynamoDB DeleteItem | Yes (recovery) | Yes (grace) | -- |
| DynamoDB Query (GSI) | Yes (storm) | -- | -- |
| CloudWatch DescribeAlarms | Yes (cool-off) | Yes (verify) | -- |
| CloudWatch Logs FilterLogEvents | Yes (recovery) | Yes (analysis) | Yes (diagnostics) |
| Secrets Manager GetSecretValue | Yes | Yes | Yes |
| EventBridge PutEvents | Yes | Yes | -- |
| Lambda GetFunction/UpdateConfig | -- | Yes (remediation) | -- |
| Lambda PutFunctionConcurrency | -- | Yes (remediation) | -- |
| Lambda InvokeFunction | -- | Yes (recovery: backlog-drain) | -- |
| Step Functions StartExecution | -- | Yes (recovery: replay, reprocess, data-correction) | -- |
| SNS Publish (notifications) | -- | -- | Yes |
| X-Ray write | Yes | Yes | Yes |

---

## 7. Resource Naming Convention

All resources follow `{purpose}-{stage}` pattern:

| Resource | Name Pattern | Example (dev) |
|----------|-------------|---------------|
| Detection Lambda | `incident-detection-{stage}` | `incident-detection-dev` |
| Triage Lambda | `incident-triage-{stage}` | `incident-triage-dev` |
| Escalation Lambda | `incident-escalation-{stage}` | `incident-escalation-dev` |
| DynamoDB table | `incident-correlation-{stage}` | `incident-correlation-dev` |
| Alarm SNS topic | `incident-alarm-ingestion-{stage}` | `incident-alarm-ingestion-dev` |
| Notification SNS topic | `incident-engineer-notifications-{stage}` | `incident-engineer-notifications-dev` |
| Detection DLQ | `incident-detection-dlq-{stage}` | `incident-detection-dlq-dev` |
| Triage DLQ | `incident-triage-dlq-{stage}` | `incident-triage-dlq-dev` |
| Escalation DLQ | `incident-escalation-dlq-{stage}` | `incident-escalation-dlq-dev` |
| Dashboard | `incident-manager-dashboard-{stage}` | `incident-manager-dashboard-dev` |

---

## 8. Deployment Prerequisites

Before `cdk deploy`:

1. **Jira credentials in Secrets Manager**: Create secret `incident-manager/jira-credentials` with:
   ```json
   {
     "email": "incident-bot@example.com",
     "api_token": "<jira-api-token>",
     "account_id": "<jira-account-id>"
   }
   ```
   The `account_id` is the Jira Cloud account ID of the service account. It is used to set the reporter on incident tickets so they appear as created by the system, not by the authenticated user. Find it via: `GET /rest/api/3/myself` using the service account credentials.

2. **Engineer notification subscription**: After deploy, add email/SMS subscriptions to the notification SNS topic for on-call engineers.

3. **Service alarm actions**: Update existing service stacks to point alarms at the shared alarm ingestion topic (Section 5).

4. **Recovery workflows** (optional, added incrementally): Create Step Functions / Lambda for each recovery model used:
   - `REPLAY_DLQ_WORKFLOW_ARN` -- Step Function to replay DLQ messages
   - `REPROCESS_BATCH_WORKFLOW_ARN` -- Step Function to rerun failed batch jobs
   - `RECONCILIATION_WORKFLOW_ARN` -- Step Function to run data reconciliation
   - `BACKLOG_DRAIN_FUNCTION_NAME` -- Lambda to scale consumers for queue draining

   These are external to the incident manager stack. Add their ARNs/names to the incident manager config when ready. Recovery workflows are additive -- the incident system gracefully skips recovery if the workflow ARN is not configured.

---

## 9. Design Principle Alignment

| Principle | How Applied in Infrastructure |
|-----------|-------------------------------|
| P1: Event-Driven | SNS triggers Detection; EventBridge routes to Triage and Escalation |
| P2: Loose Coupling | Lambdas interact via EventBridge events, not direct invocation |
| P4: Clear System Ownership | DynamoDB = correlation, Jira = SoR, EventBridge = orchestration |
| P6: Failure Isolation | 3 independent Lambdas, each with own DLQ, own IAM role |
| P8: Observability | ADOT layers, X-Ray tracing, CloudWatch dashboard + alarms |
| P14: Operational Simplicity | 1 table, 3 Lambdas, EventBridge, SNS -- minimal infrastructure |
| P15: Recovery-Aware Automation | Step Functions + Lambda permissions for recovery workflow orchestration |
| P16: Evolutionary Architecture | New EventBridge consumers addable without modifying existing stack |
