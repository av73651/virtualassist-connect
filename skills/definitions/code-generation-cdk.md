# Code Generation Skill - AWS CDK
## Directive
This skill generates production-ready AWS CDK Infrastructure as Code that MUST enforce architectural standards, least privilege, zero-hardcoding rules, and enterprise-grade quality constraints.

**Primary Goal**: Generate secure, multi-environment, deterministic infrastructure with strict parameter mapping.


## 1. INFRASTRUCTURE (AWS CDK)

### 1.1 Stack Requirements (MANDATORY)

**MUST Extract Configurations:**
- **NEVER** hardcode environments (Account, Region), Memory, Timeouts, or API Gateway throttling limits directly in the Stack.
- **ALWAYS** load these from `infra/config.json` via a multi-environment mapping (e.g., `dev` vs `prod`).
- Pass the resulting dictionary to the Stack constructor.

**MUST Use Dynamic Regions for Layers:**
- **NEVER** hardcode `us-east-1` or `us-west-2` inside AWS Layer ARNs if deploying cross-region.
- **ALWAYS** use `Stack.of(self).region` for dynamic mapping (e.g., `f"arn:aws:lambda:{Stack.of(self).region}:..."`).

**MUST Handle Python Cross-Compilation Natively (Pydantic/Rust):**
- When packaging ZIP payloads on macOS/Windows that contain C/Rust extensions (e.g. `pydantic_core`), the local compile will fail on AWS Amazon Linux.
- **ALWAYS** script a bundler that extracts native Linux wheels before CDK synthesis:
  `pip install <packages> --platform manylinux2014_x86_64 --target package/ --only-binary=:all: --python-version 3.12`

```python
from aws_cdk import (
    Stack,
    aws_lambda as lambda_,
    aws_apigateway as apigw,
    aws_logs as logs,
    aws_iam as iam,
    Tags,
    RemovalPolicy,
    Duration
)
from constructs import Construct

class UserApiStack(Stack):
    """Stack for User API with enforced best practices."""

    def __init__(self, scope: Construct, id: str, config: dict, **kwargs):
        super().__init__(scope, id, **kwargs)
        self.config = config

        # Lambda function with best practices mapped from config.json
        user_function = lambda_.Function(
            self, 'UserFunction',
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler='src.handlers.user_handler.lambda_handler',
            code=lambda_.Code.from_asset('../backend/lambdas/user/package'), # Target pre-compiled wheel folder
            timeout=Duration.seconds(self.config["lambda"]["timeout"]),
            memory_size=self.config["lambda"]["memory_size"],
            environment={
                'ENVIRONMENT': self.config["stage"],
                'OTEL_SERVICE_NAME': 'user-api',
                'LOG_LEVEL': self.config["lambda"]["log_level"]
            },
            tracing=lambda_.Tracing.ACTIVE,  # MANDATORY: X-Ray tracing
            log_retention=logs.RetentionDays.ONE_WEEK  # MANDATORY: Log retention
        )

        # MANDATORY: Least privilege IAM
        user_function.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=['dynamodb:GetItem', 'dynamodb:PutItem', 'dynamodb:Query'],
                resources=[f'arn:aws:dynamodb:{self.region}:{self.account}:table/users*']
            )
        )

        # MANDATORY: Resource tagging
        Tags.of(user_function).add('Environment', environment)
        Tags.of(user_function).add('Service', 'user-api')
        Tags.of(user_function).add('ManagedBy', 'CDK')

        # API Gateway with security
        api = apigw.RestApi(
            self, 'UserApi',
            rest_api_name=f'user-api-{environment}',
            cloud_watch_role=True,  # MANDATORY: CloudWatch logging
            deploy_options=apigw.StageOptions(
                stage_name=environment,
                logging_level=apigw.MethodLoggingLevel.INFO,
                data_trace_enabled=True,
                metrics_enabled=True,  # MANDATORY: Metrics
                tracing_enabled=True   # MANDATORY: X-Ray
            )
        )
```

### 1.2 CDK Aspects (MANDATORY)

```python
from aws_cdk import IAspect, Aspects
from constructs import IConstruct
from aws_cdk import aws_s3 as s3

class EnforceEncryption(IAspect):
    """Enforce encryption on all S3 buckets."""

    def visit(self, node: IConstruct) -> None:
        if isinstance(node, s3.CfnBucket):
            if not node.bucket_encryption:
                node.bucket_encryption = s3.CfnBucket.BucketEncryptionProperty(
                    server_side_encryption_configuration=[
                        s3.CfnBucket.ServerSideEncryptionRuleProperty(
                            server_side_encryption_by_default=s3.CfnBucket.ServerSideEncryptionByDefaultProperty(
                                sse_algorithm='AES256'
                            )
                        )
                    ]
                )

# Apply aspect to stack
Aspects.of(stack).add(EnforceEncryption())
```

---

## 2. OUTPUT FORMAT (STRICT)
ALL generated code MUST be returned in this format:

```
FILE: infra/stacks/example_stack.py
<complete file content>
```

## 3. QUALITY GATES (MANDATORY)
Before returning generated CDK code, verify:
- [ ] No hardcoded AWS Account IDs or Regions.
- [ ] No hardcoded compute limits (Memory, Timeout).
- [ ] Variables bind dynamically to `config.json` map.
- [ ] Cross-region layer ARNs map dynamically using `Stack.of(self).region`.
- [ ] IAM least privilege (Resource-scoped DB actions).
- [ ] S3 bucket encryption enforced.
- [ ] Python Lambda architectures containing Rust/C dependencies package Linux wheels natively via pip `--platform manylinux2014_x86_64` payload extraction.
- [ ] Standardized Enterprise tags applied.
- [ ] Code compiles logically via `aws-cdk synth`.

## 4. EXECUTION CHECKLIST
1. **Identify resources** 
2. **Apply explicit config dictionary bindings**
3. **Inject security boundaries and tags**
4. **Enforce cross-compilation pipeline for Python lambdas**
5. **Run CDK quality gates**
6. **Return output**
