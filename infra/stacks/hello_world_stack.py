"""Hello World CDK Stack.

This module defines the AWS infrastructure for the Hello World API using AWS CDK.
"""

from aws_cdk import (
    Stack,
    aws_lambda as lambda_,
    aws_apigateway as apigw,
    aws_logs as logs,
    aws_iam as iam,
    aws_cloudwatch as cloudwatch,
    aws_cognito as cognito,
    aws_wafv2 as wafv2,
    Duration,
    CfnOutput,
    RemovalPolicy
)
from constructs import Construct


# Map config log_retention_days to CDK enum
_LOG_RETENTION_MAP = {
    7: logs.RetentionDays.ONE_WEEK,
    30: logs.RetentionDays.ONE_MONTH,
    90: logs.RetentionDays.THREE_MONTHS,
    365: logs.RetentionDays.ONE_YEAR
}


class HelloWorldStack(Stack):
    """CDK stack for Hello World API.

    Creates Lambda function, API Gateway with Cognito auth, WAF,
    CloudWatch dashboard, and alarms.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        config: dict,
        user_pool: cognito.IUserPool,
        **kwargs
    ) -> None:
        """Initialize Hello World stack.

        Args:
            scope: CDK app or stage
            construct_id: Unique identifier for this stack
            config: Configuration dictionary loaded from config.json
            user_pool: Shared Cognito User Pool from AuthStack
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)
        self.config = config
        self.user_pool = user_pool

        # Lambda Function
        self.hello_lambda = self._create_lambda_function()

        # API Gateway
        self.api = self._create_api_gateway()

        # WAF
        self._create_waf()

        # CloudWatch Dashboard
        self._create_dashboard()

        # CloudWatch Alarms
        self._create_alarms()

        # Outputs
        self._create_outputs()

    def _create_lambda_function(self) -> lambda_.Function:
        """Create Lambda function with ADOT layer and observability.

        Returns:
            lambda_.Function: The created Lambda function
        """
        # IAM Role with least privilege
        lambda_role = iam.Role(
            self, "HelloLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Execution role for Hello World Lambda",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AWSXRayDaemonWriteAccess"
                )
            ]
        )

        # Shared code Lambda Layer (middleware, config)
        shared_layer = lambda_.LayerVersion(
            self, "SharedCodeLayer",
            code=lambda_.Code.from_asset("../backend/lambda-layer"),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            description="Shared middleware and config for all Lambdas"
        )

        # ADOT Lambda Layer ARN (Python)
        adot_layer_arn = self.config.get(
            "adot_layer_arn",
            f"arn:aws:lambda:{Stack.of(self).region}:901920570463:layer:aws-otel-python-amd64-ver-1-20-0:1"
        )

        stage = self.config["api_gateway"]["stage_name"]
        log_retention = _LOG_RETENTION_MAP.get(
            self.config.get("log_retention_days", 7),
            logs.RetentionDays.ONE_WEEK
        )

        # Lambda Function (ZIP Package)
        hello_lambda = lambda_.Function(
            self, "HelloWorldFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="src.handlers.hello_handler.lambda_handler",
            code=lambda_.Code.from_asset("../backend/lambdas/hello-world/package"),
            function_name=f"hello-world-api-{stage}",
            description="Hello World API Lambda function",
            memory_size=self.config["lambda"]["memory_size"],
            timeout=Duration.seconds(self.config["lambda"]["timeout_seconds"]),
            role=lambda_role,
            tracing=lambda_.Tracing.ACTIVE,
            layers=[
                shared_layer,
                lambda_.LayerVersion.from_layer_version_arn(
                    self, "ADOTLayer", adot_layer_arn
                )
            ],
            environment={
                "LOG_LEVEL": self.config["lambda"]["log_level"],
                # ADOT auto-instrumentation (MANDATORY)
                "AWS_LAMBDA_EXEC_WRAPPER": "/opt/otel-instrument",
                # OpenTelemetry configuration
                "OTEL_SERVICE_NAME": "hello-world-api",
                "OTEL_TRACES_SAMPLER": self.config.get("trace_sampling", "always_on"),
                "OTEL_METRICS_EXPORTER": "otlp",
                "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc",
                "OTEL_PROPAGATORS": "tracecontext,baggage,xray",
                "OTEL_RESOURCE_ATTRIBUTES": "service.name=hello-world-api,service.namespace=VirtualAssist"
            },
            log_retention=log_retention
        )

        return hello_lambda

    def _create_api_gateway(self) -> apigw.RestApi:
        """Create API Gateway with Cognito auth and /hello endpoint.

        Returns:
            apigw.RestApi: The created REST API
        """
        stage = self.config["api_gateway"]["stage_name"]

        # Cognito Authorizer
        authorizer = apigw.CognitoUserPoolsAuthorizer(
            self, "CognitoAuthorizer",
            cognito_user_pools=[self.user_pool],
            authorizer_name=f"hello-world-authorizer-{stage}"
        )

        # REST API
        api = apigw.RestApi(
            self, "HelloWorldApi",
            rest_api_name=f"hello-world-api-{stage}",
            description="Hello World REST API",
            deploy_options=apigw.StageOptions(
                stage_name=stage,
                throttling_rate_limit=self.config["api_gateway"]["throttling_rate_limit"],
                throttling_burst_limit=self.config["api_gateway"]["throttling_burst_limit"],
                logging_level=apigw.MethodLoggingLevel.INFO,
                data_trace_enabled=(stage != "prod"),
                metrics_enabled=True,
                tracing_enabled=True
            ),
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=self.config.get("cors_allowed_origins", ["http://localhost:4200"]),
                allow_methods=["GET", "OPTIONS"],
                allow_headers=["Content-Type", "X-Amz-Date", "Authorization", "X-Correlation-Id"]
            )
        )

        # /hello resource
        hello_resource = api.root.add_resource("hello")

        # GET /hello integration with Cognito auth
        hello_integration = apigw.LambdaIntegration(
            self.hello_lambda,
            proxy=True,
            integration_responses=[
                apigw.IntegrationResponse(status_code="200")
            ]
        )

        hello_resource.add_method(
            "GET",
            hello_integration,
            authorizer=authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO,
            method_responses=[
                apigw.MethodResponse(status_code="200")
            ]
        )

        return api

    def _create_waf(self) -> None:
        """Create WAF WebACL with AWS managed rules and rate limiting."""
        stage = self.config["api_gateway"]["stage_name"]

        web_acl = wafv2.CfnWebACL(
            self, "WebACL",
            default_action=wafv2.CfnWebACL.DefaultActionProperty(allow={}),
            scope="REGIONAL",
            visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                metric_name=f"hello-world-waf-{stage}",
                sampled_requests_enabled=True
            ),
            rules=[
                wafv2.CfnWebACL.RuleProperty(
                    name="AWSManagedRulesCommonRuleSet",
                    priority=1,
                    statement=wafv2.CfnWebACL.StatementProperty(
                        managed_rule_group_statement=wafv2.CfnWebACL.ManagedRuleGroupStatementProperty(
                            vendor_name="AWS",
                            name="AWSManagedRulesCommonRuleSet"
                        )
                    ),
                    override_action=wafv2.CfnWebACL.OverrideActionProperty(none={}),
                    visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name="AWSManagedRulesCommonRuleSet",
                        sampled_requests_enabled=True
                    )
                ),
                wafv2.CfnWebACL.RuleProperty(
                    name="RateLimitRule",
                    priority=2,
                    statement=wafv2.CfnWebACL.StatementProperty(
                        rate_based_statement=wafv2.CfnWebACL.RateBasedStatementProperty(
                            limit=2000,
                            aggregate_key_type="IP"
                        )
                    ),
                    action=wafv2.CfnWebACL.RuleActionProperty(block={}),
                    visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name="RateLimitRule",
                        sampled_requests_enabled=True
                    )
                )
            ]
        )

        # Associate WAF with API Gateway stage
        wafv2.CfnWebACLAssociation(
            self, "WebACLAssociation",
            resource_arn=self.api.deployment_stage.stage_arn,
            web_acl_arn=web_acl.attr_arn
        )

    def _create_dashboard(self) -> None:
        """Create CloudWatch dashboard for observability."""
        dashboard = cloudwatch.Dashboard(
            self, "HelloWorldDashboard",
            dashboard_name="hello-world-api-dashboard"
        )

        # Lambda metrics
        dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Lambda Invocations",
                left=[self.hello_lambda.metric_invocations()],
                width=12
            ),
            cloudwatch.GraphWidget(
                title="Lambda Errors",
                left=[
                    self.hello_lambda.metric_errors(),
                    self.hello_lambda.metric_throttles()
                ],
                width=12
            )
        )

        dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Lambda Duration",
                left=[
                    self.hello_lambda.metric_duration(statistic="p50"),
                    self.hello_lambda.metric_duration(statistic="p95"),
                    self.hello_lambda.metric_duration(statistic="p99")
                ],
                width=24
            )
        )

        # API Gateway metrics
        dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="API Gateway Requests",
                left=[
                    cloudwatch.Metric(
                        namespace="AWS/ApiGateway",
                        metric_name="Count",
                        dimensions_map={"ApiName": self.api.rest_api_name}
                    )
                ],
                width=12
            ),
            cloudwatch.GraphWidget(
                title="API Gateway Latency",
                left=[
                    cloudwatch.Metric(
                        namespace="AWS/ApiGateway",
                        metric_name="Latency",
                        dimensions_map={"ApiName": self.api.rest_api_name},
                        statistic="p95"
                    )
                ],
                width=12
            )
        )

        # Custom OpenTelemetry metrics (exported via ADOT)
        otel_namespace = "VirtualAssist"
        dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Hello Messages Generated (Success vs Error)",
                left=[
                    cloudwatch.Metric(
                        namespace=otel_namespace,
                        metric_name="hello_message_total",
                        dimensions_map={"service.name": "hello-world-api", "status": "success"},
                        statistic="Sum",
                        label="Success",
                        color="#2ca02c"
                    ),
                    cloudwatch.Metric(
                        namespace=otel_namespace,
                        metric_name="hello_message_total",
                        dimensions_map={"service.name": "hello-world-api", "status": "error"},
                        statistic="Sum",
                        label="Error",
                        color="#d62728"
                    )
                ],
                width=12
            ),
            cloudwatch.GraphWidget(
                title="Message Generation Latency (p50, p95, p99)",
                left=[
                    cloudwatch.Metric(
                        namespace=otel_namespace,
                        metric_name="hello_message_duration",
                        dimensions_map={"service.name": "hello-world-api"},
                        statistic="p50",
                        label="p50",
                        color="#1f77b4"
                    ),
                    cloudwatch.Metric(
                        namespace=otel_namespace,
                        metric_name="hello_message_duration",
                        dimensions_map={"service.name": "hello-world-api"},
                        statistic="p95",
                        label="p95",
                        color="#ff7f0e"
                    ),
                    cloudwatch.Metric(
                        namespace=otel_namespace,
                        metric_name="hello_message_duration",
                        dimensions_map={"service.name": "hello-world-api"},
                        statistic="p99",
                        label="p99",
                        color="#d62728"
                    )
                ],
                width=12
            )
        )

        # Error rate widget
        dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Error Rate (%)",
                left=[
                    cloudwatch.MathExpression(
                        expression="(errors / total) * 100",
                        label="Error Rate %",
                        using_metrics={
                            "errors": cloudwatch.Metric(
                                namespace=otel_namespace,
                                metric_name="hello_message_total",
                                dimensions_map={"service.name": "hello-world-api", "status": "error"},
                                statistic="Sum"
                            ),
                            "total": cloudwatch.Metric(
                                namespace=otel_namespace,
                                metric_name="hello_message_total",
                                dimensions_map={"service.name": "hello-world-api"},
                                statistic="Sum"
                            )
                        },
                        color="#d62728"
                    )
                ],
                width=24
            )
        )

    def _create_alarms(self) -> None:
        """Create CloudWatch alarms for monitoring."""
        # High error rate alarm
        cloudwatch.Alarm(
            self, "HighErrorRateAlarm",
            alarm_name="hello-world-high-error-rate",
            metric=self.hello_lambda.metric_errors(statistic="Sum"),
            threshold=10,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description="Alert when error count exceeds threshold"
        )

        # High latency alarm
        cloudwatch.Alarm(
            self, "HighLatencyAlarm",
            alarm_name="hello-world-high-latency",
            metric=self.hello_lambda.metric_duration(statistic="p99"),
            threshold=500,  # 500ms
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description="Alert when p99 latency exceeds 500ms"
        )

    def _create_outputs(self) -> None:
        """Create stack outputs."""
        CfnOutput(
            self, "ApiEndpoint",
            value=self.api.url,
            description="Hello World API endpoint URL",
            export_name="HelloWorldApiUrl"
        )

        CfnOutput(
            self, "LambdaFunctionName",
            value=self.hello_lambda.function_name,
            description="Lambda function name",
            export_name="HelloWorldLambdaName"
        )

        CfnOutput(
            self, "LambdaFunctionArn",
            value=self.hello_lambda.function_arn,
            description="Lambda function ARN",
            export_name="HelloWorldLambdaArn"
        )
