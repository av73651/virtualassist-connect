"""SRE Platform CDK Stack.

Detection Lambda + DynamoDB + SNS + DLQ.
Triage Lambda + EventBridge rule + DLQ + Bedrock IAM.
Escalation Lambda + EventBridge rule + notification SNS + DLQ.
Event-driven architecture — no API Gateway or Cognito."""

from aws_cdk import (
    Stack,
    aws_lambda as lambda_,
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
    aws_sns as sns,
    aws_sns_subscriptions as subs,
    aws_sqs as sqs,
    aws_events as events,
    aws_events_targets as targets,
    aws_logs as logs,
    aws_iam as iam,
    aws_secretsmanager as secretsmanager,
    Duration,
    CfnOutput,
    RemovalPolicy,
)
from constructs import Construct


# Map config log_retention_days to CDK enum
_LOG_RETENTION_MAP = {
    7: logs.RetentionDays.ONE_WEEK,
    30: logs.RetentionDays.ONE_MONTH,
    90: logs.RetentionDays.THREE_MONTHS,
    365: logs.RetentionDays.ONE_YEAR,
}


class SrePlatformStack(Stack):
    """CDK stack for SRE Platform Pipeline.

    Detection Lambda, DynamoDB correlation table, SNS alarm ingestion.
    Triage Lambda, EventBridge rule (IncidentCreated -> Triage), Bedrock IAM.
    Escalation Lambda, EventBridge rule (EscalationRequired -> Escalation), notification SNS.
    No API Gateway — event-driven via SNS and EventBridge."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        config: dict,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.config = config
        self.stage = config["api_gateway"]["stage_name"]
        self.im_config = config["sre_platform"]
        self.log_retention = _LOG_RETENTION_MAP.get(
            config.get("log_retention_days", 7),
            logs.RetentionDays.ONE_WEEK,
        )

        # Core resources
        self.correlation_table = self._create_dynamodb_table()
        self.alarm_topic = self._create_alarm_sns_topic()
        self.jira_secret = self._lookup_jira_secret()
        self.shared_layer = self._create_shared_layer()
        self.adot_layer = self._create_adot_layer()

        # Notification SNS topic (for escalation alerts)
        self.notification_topic = self._create_notification_sns_topic()

        # Checkpoint clarity resources
        self.checkpoint_table = self._create_checkpoint_table()
        self.checkpoint_bucket = self._create_checkpoint_bucket()

        # Lambdas
        self.detection_lambda = self._create_detection_lambda()
        self.triage_lambda = self._create_triage_lambda()
        self.escalation_lambda = self._create_escalation_lambda()

        # SNS -> Detection Lambda subscription + DLQ
        self.detection_dlq = self._create_sns_subscription()

        # EventBridge rules
        self.triage_dlq, self.escalation_dlq = self._create_eventbridge_rules()

        # Outputs
        self._create_outputs()

    # ------------------------------------------------------------------ #
    # Shared helpers
    # ------------------------------------------------------------------ #

    def _create_lambda_role(
        self, name: str, policy_statements: list[iam.PolicyStatement]
    ) -> iam.Role:
        """Create least-privilege IAM role for a Lambda."""
        role = iam.Role(
            self,
            f"{name}Role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description=f"Execution role for SRE Platform {name} Lambda",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AWSXRayDaemonWriteAccess"
                ),
            ],
        )
        for stmt in policy_statements:
            role.add_to_policy(stmt)
        return role

    def _common_lambda_env(self, service_name: str) -> dict:
        """Common environment variables for all SRE Platform Lambdas."""
        return {
            "LOG_LEVEL": self.config["lambda"]["log_level"],
            "STAGE": self.stage,
            "CORRELATION_TABLE_NAME": self.correlation_table.table_name,
            "JIRA_SECRET_NAME": self.im_config["jira_secret_name"],
            "JIRA_URL": self.im_config["jira_url"],
            "JIRA_PROJECT_KEY": self.im_config.get("jira_project_key", "ASD"),
            "EVENT_BUS_NAME": "default",
            # ADOT auto-instrumentation
            "AWS_LAMBDA_EXEC_WRAPPER": "/opt/otel-instrument",
            "OTEL_SERVICE_NAME": service_name,
            "OTEL_TRACES_SAMPLER": self.config.get("trace_sampling", "always_on"),
            "OTEL_METRICS_EXPORTER": "otlp",
            "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc",
            "OTEL_PROPAGATORS": "tracecontext,baggage,xray",
            "OTEL_RESOURCE_ATTRIBUTES": f"service.name={service_name},service.namespace=VirtualAssist",
        }

    # ------------------------------------------------------------------ #
    # DynamoDB
    # ------------------------------------------------------------------ #

    def _create_dynamodb_table(self) -> dynamodb.Table:
        """Correlation table with GSI for storm detection and TTL."""
        table = dynamodb.Table(
            self,
            "CorrelationTable",
            table_name=f"incident-correlation-{self.stage}",
            partition_key=dynamodb.Attribute(
                name="incident_key", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=(
                RemovalPolicy.DESTROY if self.stage == "dev" else RemovalPolicy.RETAIN
            ),
            time_to_live_attribute="ttl",
            point_in_time_recovery=self.stage == "prod",
        )

        table.add_global_secondary_index(
            index_name="created_at-index",
            partition_key=dynamodb.Attribute(
                name="gsi_pk", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="created_at", type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.KEYS_ONLY,
        )

        return table

    def _create_checkpoint_table(self) -> dynamodb.Table:
        """Checkpoint table for batch processing tracking (Checkpoint Clarity v1)."""
        table = dynamodb.Table(
            self,
            "CheckpointTable",
            table_name=f"sre-checkpoints-{self.stage}",
            partition_key=dynamodb.Attribute(
                name="checkpoint_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=(
                RemovalPolicy.DESTROY if self.stage == "dev" else RemovalPolicy.RETAIN
            ),
            point_in_time_recovery=self.stage == "prod",
        )

        table.add_global_secondary_index(
            index_name="service-status-index",
            partition_key=dynamodb.Attribute(
                name="service", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="status", type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        return table

    def _create_checkpoint_bucket(self) -> s3.Bucket:
        """S3 bucket for checkpoint manifests (large item ID lists)."""
        return s3.Bucket(
            self,
            "CheckpointManifestBucket",
            bucket_name=f"sre-checkpoint-manifests-{self.stage}-{Stack.of(self).account}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=(
                RemovalPolicy.DESTROY if self.stage == "dev" else RemovalPolicy.RETAIN
            ),
            auto_delete_objects=self.stage == "dev",
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="expire-manifests",
                    expiration=Duration.days(30),
                ),
            ],
        )

    # ------------------------------------------------------------------ #
    # SNS
    # ------------------------------------------------------------------ #

    def _create_alarm_sns_topic(self) -> sns.Topic:
        """SNS topic for CloudWatch alarm ingestion."""
        return sns.Topic(
            self,
            "AlarmIngestionTopic",
            topic_name=f"{self.im_config['sns_alarm_topic_name']}-{self.stage}",
            display_name="SRE Platform - Alarm Ingestion",
        )

    def _create_notification_sns_topic(self) -> sns.Topic:
        """SNS topic for engineer escalation notifications."""
        return sns.Topic(
            self,
            "NotificationTopic",
            topic_name=f"{self.im_config['sns_notification_topic_name']}-{self.stage}",
            display_name="SRE Platform - Engineer Notifications",
        )

    # ------------------------------------------------------------------ #
    # Secrets Manager
    # ------------------------------------------------------------------ #

    def _lookup_jira_secret(self) -> secretsmanager.ISecret:
        """Reference existing Jira credentials secret."""
        return secretsmanager.Secret.from_secret_name_v2(
            self,
            "JiraSecret",
            self.im_config["jira_secret_name"],
        )

    # ------------------------------------------------------------------ #
    # Lambda Layers
    # ------------------------------------------------------------------ #

    def _create_shared_layer(self) -> lambda_.LayerVersion:
        """Shared code layer (middleware, config)."""
        return lambda_.LayerVersion(
            self,
            "SharedCodeLayer",
            code=lambda_.Code.from_asset("../backend/lambda-layer"),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            description="Shared middleware and config for all Lambdas",
        )

    def _create_adot_layer(self) -> lambda_.ILayerVersion:
        """ADOT Lambda layer for OpenTelemetry auto-instrumentation."""
        adot_layer_arn = self.config.get(
            "adot_layer_arn",
            f"arn:aws:lambda:{Stack.of(self).region}:901920570463:layer:aws-otel-python-amd64-ver-1-20-0:1",
        )
        return lambda_.LayerVersion.from_layer_version_arn(
            self, "ADOTLayer", adot_layer_arn
        )

    # ------------------------------------------------------------------ #
    # Detection Lambda
    # ------------------------------------------------------------------ #

    def _create_detection_lambda(self) -> lambda_.Function:
        """Detection Lambda — processes SNS alarm events (Leg 1)."""
        lam_config = self.im_config["detection_lambda"]

        role = self._create_lambda_role("Detection", [
            # DynamoDB: CRUD + GSI query
            iam.PolicyStatement(
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:DeleteItem",
                    "dynamodb:Query",
                ],
                resources=[
                    self.correlation_table.table_arn,
                    f"{self.correlation_table.table_arn}/index/*",
                ],
            ),
            # Secrets Manager: Jira credentials
            iam.PolicyStatement(
                actions=["secretsmanager:GetSecretValue"],
                resources=[
                    f"arn:aws:secretsmanager:{Stack.of(self).region}:{Stack.of(self).account}:secret:{self.im_config['jira_secret_name']}*"
                ],
            ),
            # EventBridge: publish incident events
            iam.PolicyStatement(
                actions=["events:PutEvents"],
                resources=[
                    f"arn:aws:events:{Stack.of(self).region}:{Stack.of(self).account}:event-bus/default"
                ],
            ),
            # CloudWatch Logs: log analysis for recovery flow
            iam.PolicyStatement(
                actions=[
                    "logs:FilterLogEvents",
                    "logs:GetLogEvents",
                    "logs:StartQuery",
                    "logs:GetQueryResults",
                    "logs:StopQuery",
                ],
                resources=[
                    f"arn:aws:logs:{Stack.of(self).region}:{Stack.of(self).account}:log-group:/aws/lambda/*:*"
                ],
            ),
            # CloudWatch: alarm state check (cool-off) + alarm history
            iam.PolicyStatement(
                actions=["cloudwatch:DescribeAlarms", "cloudwatch:DescribeAlarmHistory"],
                resources=[
                    f"arn:aws:cloudwatch:{Stack.of(self).region}:{Stack.of(self).account}:alarm:*"
                ],
            ),
        ])

        detection = lambda_.Function(
            self,
            "DetectionFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="src.handlers.detection_handler.lambda_handler",
            code=lambda_.Code.from_asset("../backend/lambdas/sre-platform/package"),
            function_name=f"incident-detection-{self.stage}",
            description="Incident Detection Lambda (Leg 1) — SNS alarm ingestion",
            memory_size=lam_config["memory_size"],
            timeout=Duration.seconds(lam_config["timeout_seconds"]),
            role=role,
            tracing=lambda_.Tracing.ACTIVE,
            layers=[self.shared_layer, self.adot_layer],
            environment=self._common_lambda_env("incident-detection"),
            log_retention=self.log_retention,
            retry_attempts=0,
        )

        return detection

    # ------------------------------------------------------------------ #
    # Triage Lambda
    # ------------------------------------------------------------------ #

    def _create_triage_lambda(self) -> lambda_.Function:
        """Triage Lambda — EventBridge trigger, analysis + remediation (Leg 2)."""
        lam_config = self.im_config["triage_lambda"]

        policy_statements = [
            # DynamoDB: get, put (full overwrite for status transitions), delete
            iam.PolicyStatement(
                actions=["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem"],
                resources=[self.correlation_table.table_arn],
            ),
            # CloudWatch: alarm state check (verification)
            iam.PolicyStatement(
                actions=["cloudwatch:DescribeAlarms"],
                resources=[
                    f"arn:aws:cloudwatch:{Stack.of(self).region}:{Stack.of(self).account}:alarm:*"
                ],
            ),
            # CloudWatch Logs: error analysis
            iam.PolicyStatement(
                actions=[
                    "logs:FilterLogEvents",
                    "logs:GetLogEvents",
                    "logs:StartQuery",
                    "logs:GetQueryResults",
                    "logs:StopQuery",
                ],
                resources=[
                    f"arn:aws:logs:{Stack.of(self).region}:{Stack.of(self).account}:log-group:/aws/lambda/*:*"
                ],
            ),
            # Secrets Manager: Jira credentials
            iam.PolicyStatement(
                actions=["secretsmanager:GetSecretValue"],
                resources=[
                    f"arn:aws:secretsmanager:{Stack.of(self).region}:{Stack.of(self).account}:secret:{self.im_config['jira_secret_name']}*"
                ],
            ),
            # EventBridge: publish EscalationRequired, IncidentAutoResolved
            iam.PolicyStatement(
                actions=["events:PutEvents"],
                resources=[
                    f"arn:aws:events:{Stack.of(self).region}:{Stack.of(self).account}:event-bus/default"
                ],
            ),
            # Lambda control plane: remediation actions (rollback, memory, concurrency)
            iam.PolicyStatement(
                actions=[
                    "lambda:GetFunction",
                    "lambda:GetFunctionConfiguration",
                    "lambda:UpdateFunctionConfiguration",
                    "lambda:ListVersionsByFunction",
                    "lambda:GetAlias",
                    "lambda:UpdateAlias",
                    "lambda:PutFunctionConcurrency",
                    "lambda:InvokeFunction",
                ],
                resources=[
                    f"arn:aws:lambda:{Stack.of(self).region}:{Stack.of(self).account}:function:*"
                ],
            ),
            # Step Functions: recovery workflow triggers (replay, reprocess, data-correction)
            iam.PolicyStatement(
                actions=["states:StartExecution"],
                resources=[
                    f"arn:aws:states:{Stack.of(self).region}:{Stack.of(self).account}:stateMachine:*"
                ],
            ),
            # Checkpoint table: read-only for delta report (Query GSI + GetItem)
            iam.PolicyStatement(
                actions=["dynamodb:Query", "dynamodb:GetItem"],
                resources=[
                    self.checkpoint_table.table_arn,
                    f"{self.checkpoint_table.table_arn}/index/*",
                ],
            ),
            # Checkpoint manifests: read-only for delta report (S3 manifest download)
            iam.PolicyStatement(
                actions=["s3:GetObject"],
                resources=[f"{self.checkpoint_bucket.bucket_arn}/*"],
            ),
        ]

        # Bedrock: Knowledge Base retrieval + model invocation (AI classification)
        bedrock_kb_id = self.im_config.get("bedrock_knowledge_base_id", "")
        if bedrock_kb_id:
            policy_statements.append(
                iam.PolicyStatement(
                    actions=["bedrock:RetrieveAndGenerate", "bedrock:Retrieve"],
                    resources=[
                        f"arn:aws:bedrock:{Stack.of(self).region}:{Stack.of(self).account}:knowledge-base/{bedrock_kb_id}"
                    ],
                )
            )
            # InvokeModel and GetInferenceProfile do not support resource-level permissions
            policy_statements.append(
                iam.PolicyStatement(
                    actions=["bedrock:InvokeModel", "bedrock:GetInferenceProfile"],
                    resources=["*"],
                )
            )

        role = self._create_lambda_role("Triage", policy_statements)

        triage_env = {
            **self._common_lambda_env("incident-triage"),
            # Bedrock Knowledge Base (empty = disabled, falls back to rule-based)
            "BEDROCK_KNOWLEDGE_BASE_ID": self.im_config.get("bedrock_knowledge_base_id", ""),
            "BEDROCK_MODEL_ARN": self.im_config.get("bedrock_model_arn", ""),
            # Recovery workflow ARNs (populated when workflows exist; empty = skip)
            "REPLAY_DLQ_WORKFLOW_ARN": self.im_config.get("replay_dlq_workflow_arn", ""),
            "REPROCESS_BATCH_WORKFLOW_ARN": self.im_config.get("reprocess_batch_workflow_arn", ""),
            "RECONCILIATION_WORKFLOW_ARN": self.im_config.get("reconciliation_workflow_arn", ""),
            "BACKLOG_DRAIN_FUNCTION_NAME": self.im_config.get("backlog_drain_function_name", ""),
            # Checkpoint clarity
            "CHECKPOINT_TABLE_NAME": self.checkpoint_table.table_name,
            "CHECKPOINT_BUCKET_NAME": self.checkpoint_bucket.bucket_name,
        }

        triage = lambda_.Function(
            self,
            "TriageFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="src.handlers.triage_handler.lambda_handler",
            code=lambda_.Code.from_asset("../backend/lambdas/sre-platform/package"),
            function_name=f"incident-triage-{self.stage}",
            description="Incident Triage Lambda (Leg 2) — analysis, remediation, verification",
            memory_size=lam_config["memory_size"],
            timeout=Duration.seconds(lam_config["timeout_seconds"]),
            role=role,
            tracing=lambda_.Tracing.ACTIVE,
            layers=[self.shared_layer, self.adot_layer],
            environment=triage_env,
            log_retention=self.log_retention,
            retry_attempts=0,
        )

        return triage

    # ------------------------------------------------------------------ #
    # Escalation Lambda
    # ------------------------------------------------------------------ #

    def _create_escalation_lambda(self) -> lambda_.Function:
        """Escalation Lambda — EventBridge trigger, Jira enrichment + SNS notification (Leg 3)."""
        lam_config = self.im_config["escalation_lambda"]

        policy_statements = [
            # DynamoDB: get + update status to ESCALATED
            iam.PolicyStatement(
                actions=["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"],
                resources=[self.correlation_table.table_arn],
            ),
            # CloudWatch Logs: collect diagnostics for Jira attachment
            iam.PolicyStatement(
                actions=[
                    "logs:FilterLogEvents",
                    "logs:GetLogEvents",
                    "logs:StartQuery",
                    "logs:GetQueryResults",
                    "logs:StopQuery",
                ],
                resources=[
                    f"arn:aws:logs:{Stack.of(self).region}:{Stack.of(self).account}:log-group:/aws/lambda/*:*"
                ],
            ),
            # Secrets Manager: Jira credentials
            iam.PolicyStatement(
                actions=["secretsmanager:GetSecretValue"],
                resources=[
                    f"arn:aws:secretsmanager:{Stack.of(self).region}:{Stack.of(self).account}:secret:{self.im_config['jira_secret_name']}*"
                ],
            ),
            # SNS: publish engineer notifications
            iam.PolicyStatement(
                actions=["sns:Publish"],
                resources=[self.notification_topic.topic_arn],
            ),
        ]

        # Bedrock: Knowledge Base retrieval for AI log analysis
        bedrock_kb_id = self.im_config.get("bedrock_knowledge_base_id", "")
        if bedrock_kb_id:
            policy_statements.append(
                iam.PolicyStatement(
                    actions=["bedrock:RetrieveAndGenerate", "bedrock:Retrieve"],
                    resources=[
                        f"arn:aws:bedrock:{Stack.of(self).region}:{Stack.of(self).account}:knowledge-base/{bedrock_kb_id}"
                    ],
                )
            )
            policy_statements.append(
                iam.PolicyStatement(
                    actions=["bedrock:InvokeModel", "bedrock:GetInferenceProfile"],
                    resources=["*"],
                )
            )

        role = self._create_lambda_role("Escalation", policy_statements)

        escalation_env = {
            **self._common_lambda_env("incident-escalation"),
            "NOTIFICATION_TOPIC_ARN": self.notification_topic.topic_arn,
            # Bedrock Knowledge Base (empty = disabled, no AI log analysis)
            "BEDROCK_KNOWLEDGE_BASE_ID": self.im_config.get("bedrock_knowledge_base_id", ""),
            "BEDROCK_MODEL_ARN": self.im_config.get("bedrock_model_arn", ""),
            # Checkpoint clarity — delta report during escalation for reprocess recovery model
            "CHECKPOINT_TABLE_NAME": self.checkpoint_table.table_name,
            "CHECKPOINT_BUCKET_NAME": self.checkpoint_bucket.bucket_name,
        }

        escalation = lambda_.Function(
            self,
            "EscalationFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="src.handlers.escalation_handler.lambda_handler",
            code=lambda_.Code.from_asset("../backend/lambdas/sre-platform/package"),
            function_name=f"incident-escalation-{self.stage}",
            description="Incident Escalation Lambda (Leg 3) — enrichment, notifications",
            memory_size=lam_config["memory_size"],
            timeout=Duration.seconds(lam_config["timeout_seconds"]),
            role=role,
            tracing=lambda_.Tracing.ACTIVE,
            layers=[self.shared_layer, self.adot_layer],
            environment=escalation_env,
            log_retention=self.log_retention,
            retry_attempts=0,
        )

        return escalation

    # ------------------------------------------------------------------ #
    # SNS Subscription + DLQ
    # ------------------------------------------------------------------ #

    def _create_sns_subscription(self) -> sqs.Queue:
        """Subscribe Detection Lambda to alarm SNS topic with DLQ."""
        dlq = sqs.Queue(
            self,
            "DetectionDLQ",
            queue_name=f"incident-detection-dlq-{self.stage}",
            retention_period=Duration.days(14),
        )

        self.alarm_topic.add_subscription(
            subs.LambdaSubscription(
                self.detection_lambda,
                dead_letter_queue=dlq,
            )
        )

        return dlq

    # ------------------------------------------------------------------ #
    # EventBridge Rules
    # ------------------------------------------------------------------ #

    def _create_eventbridge_rules(self) -> tuple[sqs.Queue, sqs.Queue]:
        """Create EventBridge rules for the incident pipeline.

        1. IncidentCreated -> Triage Lambda
        2. EscalationRequired -> Escalation Lambda"""
        triage_dlq = sqs.Queue(
            self,
            "TriageDLQ",
            queue_name=f"incident-triage-dlq-{self.stage}",
            retention_period=Duration.days(14),
        )

        events.Rule(
            self,
            "IncidentCreatedRule",
            rule_name=f"incident-created-to-triage-{self.stage}",
            description="Routes IncidentCreated events to Triage Lambda",
            event_pattern=events.EventPattern(
                source=["sre-platform"],
                detail_type=["IncidentCreated"],
            ),
            targets=[
                targets.LambdaFunction(
                    self.triage_lambda,
                    dead_letter_queue=triage_dlq,
                    retry_attempts=2,
                )
            ],
        )

        escalation_dlq = sqs.Queue(
            self,
            "EscalationDLQ",
            queue_name=f"incident-escalation-dlq-{self.stage}",
            retention_period=Duration.days(14),
        )

        events.Rule(
            self,
            "EscalationRequiredRule",
            rule_name=f"escalation-required-to-escalation-{self.stage}",
            description="Routes EscalationRequired events to Escalation Lambda",
            event_pattern=events.EventPattern(
                source=["sre-platform"],
                detail_type=["EscalationRequired"],
            ),
            targets=[
                targets.LambdaFunction(
                    self.escalation_lambda,
                    dead_letter_queue=escalation_dlq,
                    retry_attempts=2,
                )
            ],
        )

        return triage_dlq, escalation_dlq

    # ------------------------------------------------------------------ #
    # Outputs
    # ------------------------------------------------------------------ #

    def _create_outputs(self) -> None:
        """Stack outputs for cross-stack references."""
        CfnOutput(
            self,
            "AlarmTopicArn",
            value=self.alarm_topic.topic_arn,
            description="SNS topic ARN for alarm ingestion",
            export_name=f"IncidentAlarmTopicArn-{self.stage}",
        )

        CfnOutput(
            self,
            "CorrelationTableName",
            value=self.correlation_table.table_name,
            description="DynamoDB correlation table name",
            export_name=f"IncidentCorrelationTable-{self.stage}",
        )

        CfnOutput(
            self,
            "DetectionLambdaName",
            value=self.detection_lambda.function_name,
            description="Detection Lambda function name",
            export_name=f"IncidentDetectionLambda-{self.stage}",
        )

        CfnOutput(
            self,
            "TriageLambdaName",
            value=self.triage_lambda.function_name,
            description="Triage Lambda function name",
            export_name=f"IncidentTriageLambda-{self.stage}",
        )

        CfnOutput(
            self,
            "DetectionDLQUrl",
            value=self.detection_dlq.queue_url,
            description="Detection DLQ URL",
            export_name=f"IncidentDetectionDLQ-{self.stage}",
        )

        CfnOutput(
            self,
            "TriageDLQUrl",
            value=self.triage_dlq.queue_url,
            description="Triage DLQ URL",
            export_name=f"IncidentTriageDLQ-{self.stage}",
        )

        CfnOutput(
            self,
            "EscalationLambdaName",
            value=self.escalation_lambda.function_name,
            description="Escalation Lambda function name",
            export_name=f"IncidentEscalationLambda-{self.stage}",
        )

        CfnOutput(
            self,
            "NotificationTopicArn",
            value=self.notification_topic.topic_arn,
            description="SNS topic for engineer escalation notifications",
            export_name=f"IncidentNotificationTopicArn-{self.stage}",
        )

        CfnOutput(
            self,
            "EscalationDLQUrl",
            value=self.escalation_dlq.queue_url,
            description="Escalation DLQ URL",
            export_name=f"IncidentEscalationDLQ-{self.stage}",
        )

        CfnOutput(
            self,
            "CheckpointTableName",
            value=self.checkpoint_table.table_name,
            description="Checkpoint DynamoDB table name",
            export_name=f"SreCheckpointTable-{self.stage}",
        )

        CfnOutput(
            self,
            "CheckpointBucketName",
            value=self.checkpoint_bucket.bucket_name,
            description="Checkpoint manifest S3 bucket name",
            export_name=f"SreCheckpointBucket-{self.stage}",
        )
