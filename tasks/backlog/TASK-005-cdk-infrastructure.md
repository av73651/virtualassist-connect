# TASK-005: CDK Infrastructure Stack

**Status**: Backlog
**Priority**: P1 (High - Deployment Foundation)
**Estimated Effort**: 60 minutes
**Dependencies**: TASK-001, TASK-002, TASK-003 (Lambda code must exist)

---

## Objective

Implement AWS CDK infrastructure stack to provision Lambda function, API Gateway, CloudWatch dashboard, alarms, and IAM roles with least privilege.

---

## Files to Create

1. **`infra/stacks/hello_world_stack.py`** - CDK stack definition
2. **`infra/app.py`** - CDK app entry point (if not exists)
3. **`infra/requirements.txt`** - CDK dependencies

---

## Implementation Details

### CDK Stack Structure

```python
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
    """CDK stack for Hello World API."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

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
        """Create Lambda function with ADOT layer and observability."""

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

        # ADOT Lambda Layer ARN (Python, us-east-1)
        adot_layer_arn = "arn:aws:lambda:us-east-1:901920570463:layer:aws-otel-python-amd64-ver-1-20-0:1"

        # Lambda Function
        hello_lambda = lambda_.Function(
            self, "HelloWorldFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="src.handlers.hello_handler.lambda_handler",
            code=lambda_.Code.from_asset("../backend/lambdas/hello-world"),
            function_name="hello-world-api",
            description="Hello World API Lambda function",
            memory_size=512,
            timeout=Duration.seconds(30),
            role=lambda_role,
            tracing=lambda_.Tracing.ACTIVE,
            layers=[
                lambda_.LayerVersion.from_layer_version_arn(
                    self, "ADOTLayer", adot_layer_arn
                )
            ],
            environment={
                "POWERTOOLS_SERVICE_NAME": "hello-world-api",
                "LOG_LEVEL": "INFO",
                "OTEL_SERVICE_NAME": "hello-world-api",
                "OTEL_TRACES_SAMPLER": "always_on"
            },
            log_retention=logs.RetentionDays.ONE_WEEK
        )

        return hello_lambda

    def _create_api_gateway(self) -> apigw.RestApi:
        """Create API Gateway with /hello endpoint."""

        # REST API
        api = apigw.RestApi(
            self, "HelloWorldApi",
            rest_api_name="hello-world-api",
            description="Hello World REST API",
            deploy_options=apigw.StageOptions(
                stage_name="dev",
                throttling_rate_limit=500,
                throttling_burst_limit=1000,
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
```

### CDK App Entry Point (`infra/app.py`)

```python
#!/usr/bin/env python3
from aws_cdk import App
from stacks.hello_world_stack import HelloWorldStack

app = App()

HelloWorldStack(
    app,
    "HelloWorldStack",
    description="Hello World API Stack with Lambda, API Gateway, and Observability"
)

app.synth()
```

### CDK Dependencies (`infra/requirements.txt`)

```
aws-cdk-lib==2.133.0
constructs>=10.0.0,<11.0.0
```

---

## Acceptance Criteria

### Lambda Configuration
- [ ] Runtime: Python 3.12
- [ ] Handler: `src.handlers.hello_handler.lambda_handler`
- [ ] Memory: 512 MB
- [ ] Timeout: 30 seconds
- [ ] X-Ray tracing enabled
- [ ] ADOT Python layer attached
- [ ] Environment variables configured
- [ ] Log retention: 1 week

### IAM Role (Least Privilege)
- [ ] AWSLambdaBasicExecutionRole (CloudWatch Logs)
- [ ] AWSXRayDaemonWriteAccess (X-Ray tracing)
- [ ] NO unnecessary permissions

### API Gateway
- [ ] REST API (not HTTP API)
- [ ] /hello resource with GET method
- [ ] Lambda proxy integration
- [ ] CORS enabled
- [ ] Throttling configured (500 rate, 1000 burst)
- [ ] Deployed to "dev" stage
- [ ] Logging and metrics enabled

### Observability
- [ ] CloudWatch dashboard created
- [ ] Invocation count widget
- [ ] Error count widget
- [ ] Duration widget (p50, p95, p99)
- [ ] API Gateway request count widget
- [ ] API Gateway latency widget

### Alarms
- [ ] High error rate alarm (>10 errors in 2 periods)
- [ ] High latency alarm (p99 >500ms in 2 periods)

### Outputs
- [ ] API endpoint URL
- [ ] Lambda function name
- [ ] Lambda function ARN

---

## Compliance Checks

- ✅ **Technology Standards**: Lambda, API Gateway, CloudWatch, X-Ray
- ✅ **Observability Requirements**: Dashboard, logs, metrics, traces
- ✅ **OpenTelemetry Template**: ADOT layer, environment variables
- ✅ **IAM Least Privilege**: Only necessary permissions granted
- ✅ **Development Best Practices**: Type hints, clean code

---

## Deployment Commands

```bash
# Install dependencies
cd infra
pip install -r requirements.txt

# Synthesize CloudFormation template
cdk synth

# Deploy stack
cdk deploy

# View outputs
cdk deploy --outputs-file outputs.json
```

---

## Testing

After deployment:
```bash
# Get API endpoint from outputs
API_URL=$(aws cloudformation describe-stacks --stack-name HelloWorldStack --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' --output text)

# Test endpoint
curl ${API_URL}hello

# Expected response:
# {"message": "Hello, World!", "timestamp": "2026-03-27T10:00:00.000Z"}
```

---

## Notes

- CDK version: v2.133.0
- ADOT layer ARN is region-specific (us-east-1 example provided)
- Update ADOT layer ARN for different regions
- Stack name: HelloWorldStack
- API stage: dev
- No DynamoDB needed for hello world service
