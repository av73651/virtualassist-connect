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
    Duration,
    CfnOutput,
    RemovalPolicy
)
from constructs import Construct


class HelloWorldStack(Stack):
    """CDK stack for Hello World API.

    Creates Lambda function, API Gateway, CloudWatch dashboard, and alarms.
    """

    def __init__(self, scope: Construct, construct_id: str, config: dict, **kwargs) -> None:
        """Initialize Hello World stack.

        Args:
            scope: CDK app or stage
            construct_id: Unique identifier for this stack
            config: Configuration dictionary loaded from config.json
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)
        self.config = config

        # Lambda Function
        self.hello_lambda = self._create_lambda_function()

        # API Gateway
        self.api = self._create_api_gateway()

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

        # ADOT Lambda Layer ARN (Python)
        adot_layer_arn = self.config.get("adot_layer_arn", f"arn:aws:lambda:{Stack.of(self).region}:901920570463:layer:aws-otel-python-amd64-ver-1-20-0:1")

        # Lambda Function (ZIP Package)
        hello_lambda = lambda_.Function(
            self, "HelloWorldFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="src.handlers.hello_handler.lambda_handler",
            code=lambda_.Code.from_asset("../backend/lambdas/hello-world/package"),
            function_name=f"hello-world-api-{self.config['api_gateway']['stage_name']}",
            description="Hello World API Lambda function with Pydantic core wheels",
            memory_size=self.config["lambda"]["memory_size"],
            timeout=Duration.seconds(self.config["lambda"]["timeout_seconds"]),
            role=lambda_role,
            tracing=lambda_.Tracing.ACTIVE,
            layers=[
                lambda_.LayerVersion.from_layer_version_arn(
                    self, "ADOTLayer", adot_layer_arn
                )
            ],
            environment={
                "POWERTOOLS_SERVICE_NAME": "hello-world-api",
                "LOG_LEVEL": self.config["lambda"]["log_level"],
                # OpenTelemetry configuration
                "OTEL_SERVICE_NAME": "hello-world-api",
                "OTEL_TRACES_SAMPLER": "always_on",
                "OTEL_METRICS_EXPORTER": "otlp",
                "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc",
                # Metrics export to CloudWatch via ADOT
                "OTEL_RESOURCE_ATTRIBUTES": "service.name=hello-world-api,service.namespace=hello-world"
            },
            log_retention=logs.RetentionDays.ONE_WEEK
        )

        return hello_lambda

    def _create_api_gateway(self) -> apigw.RestApi:
        """Create API Gateway with /hello endpoint.

        Returns:
            apigw.RestApi: The created REST API
        """
        # REST API
        api = apigw.RestApi(
            self, "HelloWorldApi",
            rest_api_name=f"hello-world-api-{self.config['api_gateway']['stage_name']}",
            description="Hello World REST API",
            deploy_options=apigw.StageOptions(
                stage_name=self.config["api_gateway"]["stage_name"],
                throttling_rate_limit=self.config["api_gateway"]["throttling_rate_limit"],
                throttling_burst_limit=self.config["api_gateway"]["throttling_burst_limit"],
                logging_level=apigw.MethodLoggingLevel.INFO,
                data_trace_enabled=True,
                metrics_enabled=True
            ),
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=["GET", "OPTIONS"],
                allow_headers=["Content-Type", "X-Amz-Date", "Authorization"]
            )
        )

        # /hello resource
        hello_resource = api.root.add_resource("hello")

        # GET /hello integration
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
            method_responses=[
                apigw.MethodResponse(status_code="200")
            ]
        )

        return api

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
        dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Hello Messages Generated (Success vs Error)",
                left=[
                    cloudwatch.Metric(
                        namespace="hello-world-api",
                        metric_name="hello_messages_generated",
                        dimensions_map={"status": "success"},
                        statistic="Sum",
                        label="Success",
                        color="#2ca02c"
                    ),
                    cloudwatch.Metric(
                        namespace="hello-world-api",
                        metric_name="hello_messages_generated",
                        dimensions_map={"status": "error"},
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
                        namespace="hello-world-api",
                        metric_name="hello_message_generation_duration",
                        statistic="p50",
                        label="p50",
                        color="#1f77b4"
                    ),
                    cloudwatch.Metric(
                        namespace="hello-world-api",
                        metric_name="hello_message_generation_duration",
                        statistic="p95",
                        label="p95",
                        color="#ff7f0e"
                    ),
                    cloudwatch.Metric(
                        namespace="hello-world-api",
                        metric_name="hello_message_generation_duration",
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
                                namespace="hello-world-api",
                                metric_name="hello_messages_generated",
                                dimensions_map={"status": "error"},
                                statistic="Sum"
                            ),
                            "total": cloudwatch.Metric(
                                namespace="hello-world-api",
                                metric_name="hello_messages_generated",
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
