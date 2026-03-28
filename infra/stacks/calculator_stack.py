"""Calculator CDK Stack.

This module defines the AWS infrastructure for the Calculator API using AWS CDK.
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


class CalculatorStack(Stack):
    """CDK stack for Calculator API.

    Creates Lambda function, API Gateway, CloudWatch dashboard, and alarms.
    """

    def __init__(self, scope: Construct, construct_id: str, config: dict, **kwargs) -> None:
        """Initialize Calculator stack.

        Args:
            scope: CDK app or stage
            construct_id: Unique identifier for this stack
            config: Configuration dictionary loaded from config.json
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)
        self.config = config

        # Lambda Function
        self.calculator_lambda = self._create_lambda_function()

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
            self, "CalculatorLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Execution role for Calculator Lambda",
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
        adot_layer_arn = self.config.get("adot_layer_arn", f"arn:aws:lambda:{Stack.of(self).region}:901920570463:layer:aws-otel-python-amd64-ver-1-20-0:1")

        # Lambda Function (ZIP Package)
        calculator_lambda = lambda_.Function(
            self, "CalculatorFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="src.handlers.calculator_handler.lambda_handler",
            code=lambda_.Code.from_asset("../backend/lambdas/calculator/package"),
            function_name=f"calculator-api-{self.config['api_gateway']['stage_name']}",
            description="Calculator API Lambda function with mathematical operations",
            memory_size=self.config["lambda"]["memory_size"],
            timeout=Duration.seconds(self.config["lambda"]["timeout_seconds"]),
            role=lambda_role,
            tracing=lambda_.Tracing.ACTIVE,
            layers=[
                shared_layer,  # Shared code layer (MUST be first for Python path)
                lambda_.LayerVersion.from_layer_version_arn(
                    self, "ADOTLayer", adot_layer_arn
                )
            ],
            environment={
                "POWERTOOLS_SERVICE_NAME": "calculator-api",
                "LOG_LEVEL": self.config["lambda"]["log_level"],
                # OpenTelemetry configuration
                "OTEL_SERVICE_NAME": "calculator-api",
                "OTEL_TRACES_SAMPLER": "always_on",
                "OTEL_METRICS_EXPORTER": "otlp",
                "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc",
                # Metrics export to CloudWatch via ADOT
                "OTEL_RESOURCE_ATTRIBUTES": "service.name=calculator-api,service.namespace=calculator"
            },
            log_retention=logs.RetentionDays.ONE_WEEK
        )

        return calculator_lambda

    def _create_api_gateway(self) -> apigw.RestApi:
        """Create API Gateway with /calculator/add endpoint.

        Returns:
            apigw.RestApi: The created REST API
        """
        # REST API
        api = apigw.RestApi(
            self, "CalculatorApi",
            rest_api_name=f"calculator-api-{self.config['api_gateway']['stage_name']}",
            description="Calculator REST API",
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
                allow_methods=["POST", "OPTIONS"],
                allow_headers=["Content-Type", "X-Amz-Date", "Authorization"]
            )
        )

        # /calculator resource
        calculator_resource = api.root.add_resource("calculator")

        # /calculator/add resource
        add_resource = calculator_resource.add_resource("add")

        # POST /calculator/add integration
        add_integration = apigw.LambdaIntegration(
            self.calculator_lambda,
            proxy=True,
            integration_responses=[
                apigw.IntegrationResponse(status_code="200"),
                apigw.IntegrationResponse(status_code="400"),
                apigw.IntegrationResponse(status_code="500")
            ]
        )

        add_resource.add_method(
            "POST",
            add_integration,
            method_responses=[
                apigw.MethodResponse(status_code="200"),
                apigw.MethodResponse(status_code="400"),
                apigw.MethodResponse(status_code="500")
            ]
        )

        return api

    def _create_dashboard(self) -> None:
        """Create CloudWatch dashboard for observability."""
        dashboard = cloudwatch.Dashboard(
            self, "CalculatorDashboard",
            dashboard_name="calculator-api-dashboard"
        )

        # Lambda metrics
        dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Lambda Invocations",
                left=[self.calculator_lambda.metric_invocations()],
                width=12
            ),
            cloudwatch.GraphWidget(
                title="Lambda Errors",
                left=[
                    self.calculator_lambda.metric_errors(),
                    self.calculator_lambda.metric_throttles()
                ],
                width=12
            )
        )

        dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Lambda Duration",
                left=[
                    self.calculator_lambda.metric_duration(statistic="p50"),
                    self.calculator_lambda.metric_duration(statistic="p95"),
                    self.calculator_lambda.metric_duration(statistic="p99")
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
                title="Calculator Operations (Success vs Error)",
                left=[
                    cloudwatch.Metric(
                        namespace="calculator-api",
                        metric_name="calculator_add_total",
                        dimensions_map={"status": "success"},
                        statistic="Sum",
                        label="Success",
                        color="#2ca02c"
                    ),
                    cloudwatch.Metric(
                        namespace="calculator-api",
                        metric_name="calculator_add_total",
                        dimensions_map={"status": "error"},
                        statistic="Sum",
                        label="Error",
                        color="#d62728"
                    )
                ],
                width=12
            ),
            cloudwatch.GraphWidget(
                title="Calculator Operation Latency (p50, p95, p99)",
                left=[
                    cloudwatch.Metric(
                        namespace="calculator-api",
                        metric_name="calculator_add_duration_seconds",
                        statistic="p50",
                        label="p50",
                        color="#1f77b4"
                    ),
                    cloudwatch.Metric(
                        namespace="calculator-api",
                        metric_name="calculator_add_duration_seconds",
                        statistic="p95",
                        label="p95",
                        color="#ff7f0e"
                    ),
                    cloudwatch.Metric(
                        namespace="calculator-api",
                        metric_name="calculator_add_duration_seconds",
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
                                namespace="calculator-api",
                                metric_name="calculator_add_total",
                                dimensions_map={"status": "error"},
                                statistic="Sum"
                            ),
                            "total": cloudwatch.Metric(
                                namespace="calculator-api",
                                metric_name="calculator_add_total",
                                statistic="Sum"
                            )
                        },
                        color="#d62728"
                    )
                ],
                width=24
            )
        )

        # Request/Response size distribution
        dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="API Gateway 4XX Errors",
                left=[
                    cloudwatch.Metric(
                        namespace="AWS/ApiGateway",
                        metric_name="4XXError",
                        dimensions_map={"ApiName": self.api.rest_api_name},
                        statistic="Sum",
                        label="Client Errors (400, 404, etc.)",
                        color="#ff7f0e"
                    )
                ],
                width=12
            ),
            cloudwatch.GraphWidget(
                title="API Gateway 5XX Errors",
                left=[
                    cloudwatch.Metric(
                        namespace="AWS/ApiGateway",
                        metric_name="5XXError",
                        dimensions_map={"ApiName": self.api.rest_api_name},
                        statistic="Sum",
                        label="Server Errors (500, 502, etc.)",
                        color="#d62728"
                    )
                ],
                width=12
            )
        )

    def _create_alarms(self) -> None:
        """Create CloudWatch alarms for monitoring."""
        # High error rate alarm
        cloudwatch.Alarm(
            self, "HighErrorRateAlarm",
            alarm_name="calculator-high-error-rate",
            metric=self.calculator_lambda.metric_errors(statistic="Sum"),
            threshold=10,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description="Alert when error count exceeds threshold"
        )

        # High latency alarm
        cloudwatch.Alarm(
            self, "HighLatencyAlarm",
            alarm_name="calculator-high-latency",
            metric=self.calculator_lambda.metric_duration(statistic="p99"),
            threshold=500,  # 500ms
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description="Alert when p99 latency exceeds 500ms"
        )

        # High 4XX error rate alarm (validation errors)
        cloudwatch.Alarm(
            self, "High4XXErrorAlarm",
            alarm_name="calculator-high-4xx-errors",
            metric=cloudwatch.Metric(
                namespace="AWS/ApiGateway",
                metric_name="4XXError",
                dimensions_map={"ApiName": self.api.rest_api_name},
                statistic="Sum"
            ),
            threshold=50,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description="Alert when 4XX error count exceeds threshold (high validation error rate)"
        )

    def _create_outputs(self) -> None:
        """Create stack outputs."""
        CfnOutput(
            self, "ApiEndpoint",
            value=self.api.url,
            description="Calculator API endpoint URL",
            export_name="CalculatorApiUrl"
        )

        CfnOutput(
            self, "CalculatorAddEndpoint",
            value=f"{self.api.url}calculator/add",
            description="Calculator addition endpoint URL",
            export_name="CalculatorAddUrl"
        )

        CfnOutput(
            self, "LambdaFunctionName",
            value=self.calculator_lambda.function_name,
            description="Lambda function name",
            export_name="CalculatorLambdaName"
        )

        CfnOutput(
            self, "LambdaFunctionArn",
            value=self.calculator_lambda.function_arn,
            description="Lambda function ARN",
            export_name="CalculatorLambdaArn"
        )
