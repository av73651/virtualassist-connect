# Technology Standards Skill - Enterprise Specification

## Directive

This skill defines the **approved technology baseline** for the platform and acts as **architectural constraints** for all system design and implementation activities.

**Primary Goal**: Ensure architectural consistency, reduce complexity, and prevent introduction of unnecessary or unsupported technologies across the platform.

**Enforcement**: ALL downstream skills (System Design, Code Generation, Code Review, Documentation) MUST follow these standards.

---

## 1. PLATFORM ARCHITECTURE PRINCIPLE

### 1.1 Serverless-First Architecture

The platform follows a **serverless-first architecture** built on **AWS managed services**.

**Design Philosophy**:
- ✅ Serverless services (Lambda, API Gateway, DynamoDB)
- ✅ Managed AWS services
- ✅ Minimal operational overhead
- ✅ Horizontal scalability by default
- ✅ Observability built-in
- ✅ Pay-per-use cost model

**Avoid**:
- ❌ Self-managed infrastructure
- ❌ Container orchestration (Kubernetes, ECS) unless explicitly required
- ❌ Self-hosted databases
- ❌ Infrastructure requiring heavy operational management
- ❌ Virtual machines (EC2) for application hosting

### 1.2 Core Principles

**Stateless Compute**:
- Functions must be stateless
- State stored in DynamoDB or S3
- No reliance on in-memory state across invocations

**Event-Driven Communication**:
- Asynchronous communication via EventBridge or SQS
- Synchronous communication via API Gateway
- Loose coupling between components

**Infrastructure as Code**:
- All infrastructure defined in AWS CDK
- No manual resource creation
- Version-controlled infrastructure definitions

**Observability by Default**:
- OpenTelemetry instrumentation required
- Structured logging mandatory
- Distributed tracing enabled
- Metrics collected automatically

---

## 2. APPROVED TECHNOLOGY STACK

### 2.1 Compute Layer

**PRIMARY**: AWS Lambda

**Runtime**: Python 3.12

**Configuration Standards**:
- Memory: 512 MB - 1024 MB (right-sized per function)
- Timeout: 30 seconds (API), 60 seconds (background processing)
- Concurrency: Reserved concurrency configured per environment
- Provisioned concurrency: Only for latency-critical functions

**Required Features**:
- X-Ray tracing enabled
- CloudWatch log groups with retention policies
- Environment variables for configuration
- Lambda layers for shared dependencies

**Handler Structure**:
```python
import logging
from opentelemetry import trace, metrics

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)
meter = metrics.get_meter("VirtualAssist")

def lambda_handler(event, context):
    # ADOT layer handles initial trace; extract trace ID for logs
    current_span = trace.get_current_span()
    trace_id = format(current_span.get_span_context().trace_id, '032x')
    
    logger.info("Request received", extra={"trace_id": trace_id})
    # Implementation
    pass
```

**FORBIDDEN**:
- ❌ EC2 instances for application hosting
- ❌ ECS/EKS containers (unless explicitly justified)
- ❌ Non-Python runtimes (unless explicitly justified)

### 2.2 API Layer

**PRIMARY**: Amazon API Gateway (REST API)

**Configuration Standards**:
- REST API (not HTTP API or WebSocket unless required)
- Regional endpoints (not private or edge-optimized unless required)
- CloudWatch logging enabled (INFO level)
- X-Ray tracing enabled
- Request/response validation enabled
- CORS configured for specific origins

**Authentication**:
- AWS Cognito User Pools
- Lambda authorizers for custom auth logic
- API keys for service-to-service (when appropriate)

**API Design Standards**:
- Versioned paths: `/api/v1/resource`
- RESTful resource naming
- Standard HTTP methods (GET, POST, PUT, DELETE)
- Consistent error response format

**CDK Example**:
```python
api = apigw.RestApi(
    self, 'Api',
    rest_api_name=f'{service_name}-api-{environment}',
    deploy_options=apigw.StageOptions(
        stage_name=environment,
        logging_level=apigw.MethodLoggingLevel.INFO,
        data_trace_enabled=(environment != 'prod'),  # Never log full payloads in production (PII risk)
        metrics_enabled=True,
        tracing_enabled=True
    ),
    default_cors_preflight_options=apigw.CorsOptions(
        allow_origins=['https://app.example.com'],
        allow_methods=apigw.Cors.ALL_METHODS,
        allow_headers=['Content-Type', 'Authorization', 'X-Correlation-Id']
    )
)
```

**FORBIDDEN**:
- ❌ Self-hosted API gateways (Kong, Tyk, etc.)
- ❌ Application Load Balancer for APIs (unless WebSocket required)
- ❌ Direct Lambda function URLs for production APIs

### 2.3 Data Storage

**PRIMARY DATASTORE**: Amazon DynamoDB

**Use Cases**:
- Transactional data (users, sessions, orders, etc.)
- High-throughput reads/writes
- Key-value or document storage
- Real-time data access

**Configuration Standards**:
- On-demand billing mode (unless predictable traffic)
- Point-in-time recovery enabled (production)
- Encryption at rest enabled (AWS managed keys)
- DynamoDB Streams enabled (for event-driven patterns)
- Global Secondary Indexes (GSI) for query patterns
- Time-to-Live (TTL) for expiring data

**Table Design Principles**:
- Single-table design for related entities
- Partition key design for even distribution
- Sort keys for query flexibility
- GSIs for alternate access patterns

**CDK Example**:
```python
table = dynamodb.Table(
    self, 'Table',
    table_name=f'{service_name}-{environment}',
    partition_key=dynamodb.Attribute(
        name='PK',
        type=dynamodb.AttributeType.STRING
    ),
    sort_key=dynamodb.Attribute(
        name='SK',
        type=dynamodb.AttributeType.STRING
    ),
    billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
    encryption=dynamodb.TableEncryption.AWS_MANAGED,
    point_in_time_recovery=True if environment == 'prod' else False,
    stream=dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,
    removal_policy=RemovalPolicy.RETAIN if environment == 'prod' else RemovalPolicy.DESTROY
)
```

**SECONDARY STORAGE**: Amazon S3

**Use Cases**:
- Large objects (files, documents, images)
- Static website hosting (frontend)
- Data lakes and archives
- Backups

**Configuration Standards**:
- Encryption enabled (SSE-S3 or SSE-KMS)
- Versioning enabled (critical buckets)
- Lifecycle policies for cost optimization
- Block public access (unless serving public content)
- CloudFront for content delivery

**FORBIDDEN**:
- ❌ Self-hosted databases (PostgreSQL, MySQL on EC2)
- ❌ RDS (unless complex relational queries required)
- ❌ MongoDB, Cassandra (unless specific requirements)
- ❌ Redis/Memcached (use DynamoDB DAX or in-memory caching in Lambda)

### 2.4 Messaging and Eventing

**EVENT BUS**: Amazon EventBridge

**Use Cases**:
- Service-to-service event notifications
- Business event broadcasting
- Integration with AWS services
- Scheduled events (cron-like)

**Configuration Standards**:
- Custom event bus per domain
- Event schemas defined and versioned
- Archive and replay enabled (production)
- Dead-letter queue configured

**Event Pattern Example**:
```python
rule = events.Rule(
    self, 'Rule',
    event_bus=event_bus,
    event_pattern=events.EventPattern(
        source=['virtualassist.users'],
        detail_type=['UserCreated']
    )
)
rule.add_target(targets.LambdaFunction(handler_function))
```

**QUEUE SERVICE**: Amazon SQS

**Use Cases**:
- Asynchronous task processing
- Request buffering
- Load leveling
- Decoupling services

**Configuration Standards**:
- Standard queue (unless FIFO ordering required)
- Visibility timeout: 6x function timeout
- Dead-letter queue configured
- Encryption enabled
- Message retention: 4 days (default)

**CDK Example**:
```python
dlq = sqs.Queue(
    self, 'DLQ',
    encryption=sqs.QueueEncryption.KMS_MANAGED
)

queue = sqs.Queue(
    self, 'Queue',
    visibility_timeout=Duration.seconds(180),
    dead_letter_queue=sqs.DeadLetterQueue(
        queue=dlq,
        max_receive_count=3
    ),
    encryption=sqs.QueueEncryption.KMS_MANAGED
)
```

**FORBIDDEN**:
- ❌ Self-hosted message brokers (RabbitMQ, Kafka)
- ❌ Amazon MQ (unless legacy system integration)
- ❌ SNS for service-to-service messaging (use EventBridge)

### 2.5 AI Services

**PRIMARY**: Amazon Bedrock

**Model**: Claude (Anthropic) via Bedrock

**Supported Claude Models**:
- `anthropic.claude-3-5-sonnet-20241022-v2:0` (recommended for production)
- `anthropic.claude-3-5-haiku-20241022-v1:0` (cost-optimized)
- `anthropic.claude-3-opus-20240229-v1:0` (highest capability)

**Configuration Standards**:
- Model ID configured via environment variable
- Streaming responses for long content
- Error handling with exponential backoff
- Request/response logging (without PII)
- Token usage metrics collected

**Python Client Example**:
```python
import boto3
import json

bedrock = boto3.client('bedrock-runtime')

def invoke_claude(prompt: str, max_tokens: int = 4096) -> str:
    """Invoke Claude via Bedrock."""
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    })

    response = bedrock.invoke_model(
        modelId='anthropic.claude-3-5-sonnet-20241022-v2:0',
        body=body
    )

    response_body = json.loads(response['body'].read())
    return response_body['content'][0]['text']
```

**IAM Permissions Required**:
```python
bedrock_policy = iam.PolicyStatement(
    effect=iam.Effect.ALLOW,
    actions=[
        'bedrock:InvokeModel',
        'bedrock:InvokeModelWithResponseStream'
    ],
    resources=[
        f'arn:aws:bedrock:{region}::foundation-model/anthropic.claude-*'
    ]
)
```

**ALTERNATIVE**: Direct Anthropic API (only if Bedrock unavailable in region)

**FORBIDDEN**:
- ❌ Self-hosted LLM models
- ❌ OpenAI API (unless specific requirement)
- ❌ Other third-party AI services without justification

### 2.6 Observability

**INSTRUMENTATION**: OpenTelemetry

**Required for All Lambda Functions**:

```python
# Use OpenTelemetry standard SDK built via ADOT Lambda Layer
import logging
from opentelemetry import trace, metrics

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("user-service")
meter = metrics.get_meter("VirtualAssist.user-service")
```

**Logging Standards**:
- Structured JSON logging (Standard Python logging formatted as JSON)
- Log level: INFO (default), ERROR (failures)
- Correlation ID propagation
- No PII in logs
- Log retention: 7 days (dev), 30 days (prod)

**Metrics Standards**:
- CloudWatch Metrics namespace: `VirtualAssist`
- Standard dimensions: Service, Environment, Function
- Custom metrics: Business events (e.g., UserCreated)
- Lambda metrics: Invocations, Errors, Duration, ConcurrentExecutions

**Tracing Standards**:
- AWS X-Ray enabled on all Lambda functions
- X-Ray enabled on API Gateway
- Service map generated automatically
- Trace sampling: 100% (dev), 10% (prod)

**CloudWatch Configuration**:
```python
# Log group with retention
logs.LogGroup(
    self, 'LogGroup',
    log_group_name=f'/aws/lambda/{function_name}',
    retention=logs.RetentionDays.ONE_WEEK if environment == 'dev' else logs.RetentionDays.ONE_MONTH,
    removal_policy=RemovalPolicy.DESTROY
)
```

**FORBIDDEN**:
- ❌ Third-party observability platforms as primary (Datadog, New Relic) unless justified
- ❌ Self-hosted monitoring (Prometheus, Grafana) as primary
- ❌ Application-level metrics that duplicate CloudWatch

### 2.7 Infrastructure as Code

**PRIMARY**: AWS CDK (Python)

**Version**: AWS CDK v2

**Standards**:
- Python for CDK code (matches Lambda runtime)
- Stack per logical service boundary
- Environment-specific configuration via parameters
- Construct reusability via custom constructs
- CDK Aspects for cross-cutting concerns

**MANDATORY: ADOT Globally Applied**:
- The AWS Distro for OpenTelemetry (ADOT) Lambda Layer MUST be applied globally to all functions via a customized base Construct or CDK Aspect.
- Do NOT hardcode regional ADOT Layer ARNs in individual function definitions (Risk of cross-region deployment breaks).

**Project Structure**:
```
infra/
  stacks/
    api_stack.py
    data_stack.py
    frontend_stack.py
  constructs/
    lambda_function.py
    api_gateway.py
  aspects/
    tagging_aspect.py
    encryption_aspect.py
  app.py
  cdk.json
  requirements.txt
```

**Stack Example**:
```python
from aws_cdk import Stack, Tags
from constructs import Construct

class ApiStack(Stack):
    def __init__(self, scope: Construct, id: str, environment: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        # Resource definitions...

        # Tagging
        Tags.of(self).add('Environment', environment)
        Tags.of(self).add('Service', 'user-api')
        Tags.of(self).add('ManagedBy', 'CDK')
```

**FORBIDDEN**:
- ❌ CloudFormation YAML/JSON templates (use CDK)
- ❌ Terraform (unless multi-cloud requirement)
- ❌ AWS SAM (use CDK)
- ❌ Manual resource creation via console

### 2.8 Security

**AUTHENTICATION**: AWS Cognito User Pools

**Standards**:
- User Pools per environment
- MFA enforcement (production)
- Password policies enforced
- JWT tokens with appropriate expiration

**MANDATORY: Layer 7 Security Boundary**:
- ALL Authentication MUST be strictly handled by API Gateway via a Cognito User Pool Authorizer.
- Lambdas MUST NOT decode, parse, or validate JWT tokens. The API Gateway will inject the validated `user_id` context into the Lambda event.
- Python code inside the Lambda is reserved strictly for *Authorization* (Does User A have permission to access Resource B?), never *Authentication*.

**Cognito Configuration**:
```python
user_pool = cognito.UserPool(
    self, 'UserPool',
    user_pool_name=f'{service_name}-users-{environment}',
    self_sign_up_enabled=True,
    sign_in_aliases=cognito.SignInAliases(email=True),
    auto_verify=cognito.AutoVerifiedAttrs(email=True),
    password_policy=cognito.PasswordPolicy(
        min_length=12,
        require_lowercase=True,
        require_uppercase=True,
        require_digits=True,
        require_symbols=True
    ),
    mfa=cognito.Mfa.OPTIONAL if environment == 'dev' else cognito.Mfa.REQUIRED,
    account_recovery=cognito.AccountRecovery.EMAIL_ONLY
)
```

**AUTHORIZATION**: AWS IAM

**Standards**:
- Least privilege principle
- Service-specific IAM roles
- No wildcard permissions in production
- Resource-level permissions where possible
- Conditions for enhanced security

**IAM Role Example**:
```python
role = iam.Role(
    self, 'LambdaRole',
    assumed_by=iam.ServicePrincipal('lambda.amazonaws.com'),
    managed_policies=[
        iam.ManagedPolicy.from_aws_managed_policy_name('service-role/AWSLambdaBasicExecutionRole')
    ]
)

# Least privilege policy
role.add_to_policy(iam.PolicyStatement(
    effect=iam.Effect.ALLOW,
    actions=['dynamodb:GetItem', 'dynamodb:PutItem', 'dynamodb:Query'],
    resources=[table.table_arn, f'{table.table_arn}/index/*']
))
```

**SECRETS MANAGEMENT**: AWS Secrets Manager

**Standards**:
- All secrets stored in Secrets Manager
- Rotation enabled (where supported)
- Access via IAM permissions
- Never hardcode secrets in code or environment variables

**Secrets Access Example**:
```python
import boto3
import json

def get_secret(secret_name: str) -> dict:
    """Retrieve secret from Secrets Manager."""
    client = boto3.client('secretsmanager')
    response = client.get_secret_value(SecretId=secret_name)
    return json.loads(response['SecretString'])

# Usage
anthropic_secret = get_secret('virtualassist/anthropic-api-key')
api_key = anthropic_secret['api_key']
```

**NETWORK SECURITY**:
- TLS 1.2+ for all network communication
- API Gateway HTTPS enforcement
- CORS configured for specific origins
- Security groups (if VPC used) with minimal ingress

**FORBIDDEN**:
- ❌ Hardcoded secrets in code
- ❌ Secrets in environment variables (use Secrets Manager reference)
- ❌ Custom authentication systems (use Cognito)
- ❌ Wildcard IAM permissions (`*`) in production

### 2.9 Frontend (Angular)

**Framework**: Angular 17+

**Standards**:
- Standalone components
- TypeScript strict mode
- RxJS for async operations
- Signals for state management (Angular 17+)
- HTTP interceptors for API calls
- Route guards for authorization

**Hosting**:
- S3 bucket for static files
- CloudFront distribution for content delivery
- Origin Access Identity for S3 security

**CDK Configuration**:
```python
# S3 bucket
bucket = s3.Bucket(
    self, 'FrontendBucket',
    encryption=s3.BucketEncryption.S3_MANAGED,
    block_public_access=s3.BlockPublicAccess.BLOCK_ALL
)

# CloudFront distribution
distribution = cloudfront.Distribution(
    self, 'Distribution',
    default_behavior=cloudfront.BehaviorOptions(
        origin=origins.S3Origin(bucket),
        viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS
    ),
    default_root_object='index.html',
    error_responses=[
        cloudfront.ErrorResponse(
            http_status=404,
            response_http_status=200,
            response_page_path='/index.html'
        )
    ]
)
```

---

## 3. TECHNOLOGY USAGE RULES

### 3.1 Default Technology Selection

**MANDATORY**: Use the approved technology stack for all new development.

**Rule**: System design MUST use approved technologies unless a specific requirement cannot be satisfied.

### 3.2 Alternative Technology Justification

Alternative technologies MAY be proposed ONLY if:

1. **Technical Requirement Cannot Be Met**: The approved stack cannot satisfy a documented requirement
   - Example: Real-time bidirectional communication requires WebSocket (API Gateway WebSocket API)
   - Example: Complex relational queries require RDS

2. **Clearly Justified**: Business or technical justification documented
   - Performance requirements exceed DynamoDB capabilities
   - Compliance requirements mandate specific technology
   - Cost analysis favors alternative

3. **Trade-offs Documented**: Pros/cons analysis completed
   - Operational overhead impact
   - Cost implications
   - Team expertise requirements
   - Migration complexity

### 3.3 Justification Template

When proposing alternative technology:

```markdown
## Alternative Technology Proposal

### Requirement
[Requirement ID and description that cannot be met]

### Limitation of Standard Stack
[Specific limitation of approved technology]

### Proposed Alternative
[Technology being proposed]

### Justification
[Why this alternative is necessary]

### Trade-offs

**Benefits**:
- [Benefit 1]
- [Benefit 2]

**Costs**:
- Operational overhead: [Description]
- Team expertise: [Required skills]
- Integration complexity: [Challenges]
- Cost impact: [Estimated difference]

### Approval Required
[Stakeholder or architect approval needed]
```

### 3.4 Forbidden Technologies (Without Justification)

**NEVER introduce without explicit justification**:
- ❌ Kubernetes or container orchestration
- ❌ Self-managed databases (PostgreSQL, MySQL on EC2)
- ❌ Self-hosted message brokers (Kafka, RabbitMQ)
- ❌ Self-hosted monitoring solutions
- ❌ Non-Python backend runtimes (Node.js, Java, Go) for Lambda
- ❌ GraphQL (unless specific frontend requirement)
- ❌ Microservices frameworks (Spring Boot, Express.js) - use serverless patterns

---

## 4. SERVERLESS DESIGN PATTERNS

### 4.1 Stateless Compute

**Pattern**: Lambda functions MUST be stateless.

**Implementation**:
- No in-memory state relied upon between invocations
- State stored in DynamoDB or S3
- Connection pooling avoided (use AWS SDK connection reuse)

### 4.2 Event-Driven Architecture

**Pattern**: Use events for asynchronous communication.

**Implementation**:
```
Service A → EventBridge → Service B Lambda
Service A → SQS Queue → Service B Lambda
```

**Use Cases**:
- User created → Send welcome email
- Order placed → Process payment + Update inventory
- File uploaded → Process file + Store metadata

### 4.3 API Gateway + Lambda

**Pattern**: Synchronous API requests via API Gateway.

**Implementation**:
```
Client → API Gateway → Lambda Authorizer (auth)
                    → Lambda Handler (business logic)
                    → DynamoDB (data)
```

### 4.4 Fan-Out Pattern

**Pattern**: One event triggers multiple processors.

**Implementation**:
```
Source Lambda → EventBridge Event → Multiple Target Lambdas
```

**Example**:
```
User Registration Event
  → Email Service Lambda (send welcome email)
  → Analytics Lambda (track signup)
  → CRM Integration Lambda (create lead)
```

### 4.5 DynamoDB Streams Processing

**Pattern**: React to database changes.

**Implementation**:
```
DynamoDB Table (with Streams enabled)
  → Lambda Function (processes stream records)
  → Secondary action (audit log, cache update, etc.)
```

---

## 5. OBSERVABILITY REQUIREMENTS

### 5.1 Mandatory Telemetry

ALL Lambda functions MUST include:

1. **Structured Logging**:
   ```python
   logger.info("User created", extra={
       "user_id": user.id,
       "email": user.email,
       "action": "user_creation"
   })
   ```

2. **Distributed Tracing** (via ADOT Lambda Layer + OpenTelemetry SDK):
   ```python
   from opentelemetry import trace

   tracer = trace.get_tracer(__name__)

   def lambda_handler(event, context):
       # ADOT layer creates the root span automatically
       with tracer.start_as_current_span("process_request"):
           # Business logic traced
           pass
   ```

3. **Metrics** (OpenTelemetry SDK):
   ```python
   from opentelemetry import metrics

   meter = metrics.get_meter("VirtualAssist")
   user_created_counter = meter.create_counter("UserCreated")

   # In business logic
   user_created_counter.add(1, {"service": "user-api"})
   ```

4. **Correlation ID Propagation** (via OpenTelemetry trace context):
   ```python
   from opentelemetry import trace

   def lambda_handler(event, context):
       # ADOT propagates trace context automatically; extract trace_id for logging
       span = trace.get_current_span()
       trace_id = format(span.get_span_context().trace_id, '032x')
       logger.info("Processing request", extra={"trace_id": trace_id})
       # trace_id serves as the correlation ID across all services
   ```

### 5.2 CloudWatch Integration

**Log Groups**: Automatically created for Lambda functions

**Metrics Namespace**: `VirtualAssist`

**X-Ray Service Name**: Matches Lambda function name

### 5.3 Alarming

**Required Alarms** (Production):
- Lambda errors > 5% for 5 minutes
- Lambda throttles > 10 in 5 minutes
- API Gateway 5xx errors > 5% for 5 minutes
- DynamoDB throttles > 10 in 5 minutes

**Alarm Configuration Example**:
```python
alarm = cloudwatch.Alarm(
    self, 'HighErrorRateAlarm',
    metric=lambda_function.metric_errors(statistic='Sum', period=Duration.minutes(5)),
    threshold=10,
    evaluation_periods=1,
    alarm_description='Lambda function error rate too high'
)
```

---

## 6. SECURITY DEFAULTS

### 6.1 Encryption

**At Rest**:
- DynamoDB: AWS managed encryption (default)
- S3: SSE-S3 or SSE-KMS
- Secrets Manager: KMS encryption (automatic)
- CloudWatch Logs: KMS encryption (optional, recommended for prod)

**In Transit**:
- API Gateway: HTTPS enforced
- Lambda to AWS services: TLS via AWS SDK
- Frontend to backend: HTTPS only

### 6.2 IAM Best Practices

- One IAM role per Lambda function
- Least privilege permissions
- No wildcard resources in production
- Conditions for additional security

### 6.3 Network Security

**Default**: No VPC for Lambda (unless specific requirement)

**If VPC Required**:
- Private subnets only
- NAT Gateway for internet access
- VPC endpoints for AWS services
- Security groups with minimal ingress

**When VPC is Required**:
- RDS access (if RDS used)
- ElastiCache access (if caching layer added)
- Legacy system integration

---

## 7. INTEGRATION WITH OTHER SKILLS

### 7.1 System Design Skill

**MUST**:
- Use technologies defined by Technology Standards Skill
- NOT independently select technology stacks
- Implement architecture patterns using approved platform services
- Document rationale if alternative technology required

**System Design Process**:
1. Read Technology Standards Skill
2. Design system using approved stack
3. If approved stack insufficient, document justification
4. Proceed with design using constraints

### 7.2 Code Generation Skill

**MUST generate code compatible with platform stack**:
- Python 3.12 for backend
- AWS Lambda handler structure
- OpenTelemetry SDK (via ADOT Lambda Layer) for observability
- DynamoDB data access via boto3
- API Gateway integration
- Bedrock Claude integration for AI capabilities
- CDK for infrastructure

### 7.3 Code Review Skill

**MUST verify adherence to platform standards**:

**Check**:
- ✅ Lambda functions used (not EC2, containers)
- ✅ DynamoDB used for data (not unsupported databases)
- ✅ OpenTelemetry instrumentation present (via ADOT)
- ✅ AWS SDK usage aligned with patterns
- ✅ Cognito for authentication
- ✅ Secrets Manager for secrets
- ✅ CDK for infrastructure

**Flag Violations**:
- ❌ Non-approved technologies introduced
- ❌ Missing observability instrumentation
- ❌ Hardcoded secrets
- ❌ Non-standard authentication
- ❌ Manual infrastructure

### 7.4 Documentation Skill

**MUST**:
- Reflect platform architecture in documentation
- Explain how system uses standard stack
- Document any approved deviations
- Reference AWS services by name
- Include links to AWS documentation

---

## 8. WORKFLOW INTEGRATION

### 8.1 Development Workflow Sequence

```
1. Requirements Analysis
   ↓ (defines what to build)

2. Technology Standards ← YOU ARE HERE
   ↓ (defines technology constraints)

3. System Design
   ↓ (designs architecture within constraints)

4. Code Generation
   ↓ (generates code using approved stack)

5. Code Review
   ↓ (verifies standards compliance)

6. Documentation
   ↓ (documents using standard stack)

7. Deployment
```

### 8.2 Decision Gates

**Before System Design**:
- ✅ Technology Standards reviewed
- ✅ Requirements mapped to approved technologies
- ✅ Alternative technology needs identified (if any)

**Before Code Generation**:
- ✅ Design uses approved stack
- ✅ Any alternatives justified and approved

**Before Deployment**:
- ✅ Code review passed standards compliance
- ✅ Observability instrumentation present
- ✅ Security defaults applied

---

## 9. PLATFORM EVOLUTION

### 9.1 Technology Adoption Process

**Adding New Technology to Approved Stack**:

1. **Proposal**: Document technology and use case
2. **Evaluation**: Assess benefits, costs, operational impact
3. **Pilot**: Test in non-production environment
4. **Documentation**: Update Technology Standards Skill
5. **Training**: Ensure team proficiency
6. **Adoption**: Roll out to projects

### 9.2 Deprecation Process

**Removing Technology from Approved Stack**:

1. **Assessment**: Identify dependencies
2. **Migration Plan**: Plan transition to alternative
3. **Timeline**: Set deprecation timeline
4. **Communication**: Notify all stakeholders
5. **Support**: Provide migration support
6. **Removal**: Update Technology Standards Skill

---

## 10. EXCEPTIONS AND WAIVERS

### 10.1 Exception Request

If a project requires deviation from approved stack:

**Required Information**:
- Project name and requirement ID
- Technology requested
- Justification (why standard stack insufficient)
- Trade-off analysis
- Operational impact assessment
- Security review (if applicable)

**Approval Authority**: Platform Architect

### 10.2 Temporary Waivers

Short-term exceptions MAY be granted for:
- Proof of concept / experimentation
- Legacy system migration (transition period)
- Vendor-specific requirements

**Conditions**:
- Time-bound (specify end date)
- Migration plan to standard stack
- Regular review of waiver status

---

## 11. ANTI-PATTERNS

### 11.1 Architecture Anti-Patterns

**AVOID**:
- ❌ Monolithic Lambda functions (>1000 lines)
- ❌ Lambda functions managing state in memory
- ❌ Synchronous chains of Lambda invocations (use Step Functions if needed)
- ❌ Polling DynamoDB for changes (use Streams)
- ❌ Direct Lambda-to-Lambda invocation (use EventBridge or SQS)

### 11.2 Technology Anti-Patterns

**AVOID**:
- ❌ Introducing Kubernetes "because we might need it later"
- ❌ RDS "because we know SQL" (use DynamoDB unless complex queries required)
- ❌ Custom authentication "because Cognito is complex" (learn Cognito)
- ❌ Third-party CI/CD "because we're familiar with it" (use AWS native tools)

### 11.3 Operational Anti-Patterns

**AVOID**:
- ❌ Manual infrastructure changes
- ❌ Console-based deployments
- ❌ Missing observability instrumentation
- ❌ Hardcoded configuration values
- ❌ Shared IAM roles across functions

---

## 12. REFERENCE ARCHITECTURE

### 12.1 Standard Web Application

```
User → CloudFront → S3 (Angular frontend)
User → API Gateway → Lambda Authorizer (Cognito)
                   → Lambda Handlers
                   → DynamoDB
                   → Bedrock (AI features)
                   → EventBridge (async events)
                   → SQS (background tasks)

All Lambda functions:
- OpenTelemetry SDK (via ADOT Lambda Layer)
- X-Ray tracing
- CloudWatch logs/metrics
```

### 12.2 Event-Driven Microservices

```
Service A Lambda → EventBridge → Service B Lambda
                                → Service C Lambda

Each service:
- Own Lambda functions
- Own DynamoDB table
- Own event bus (optional)
- Standard observability
```

### 12.3 Data Processing Pipeline

```
S3 Upload → Lambda Trigger → Process File
                           → Store Results (DynamoDB)
                           → Emit Event (EventBridge)
                           → Downstream Lambdas
```

---

## 13. COMPLIANCE AND GOVERNANCE

### 13.1 Standards Compliance

**Mandatory for All Projects**:
- Use approved technology stack
- Follow serverless design patterns
- Include observability instrumentation
- Apply security defaults
- Document any deviations

### 13.2 Audit and Review

**Regular Reviews**:
- Architecture reviews verify compliance
- Code reviews check technology usage
- Security reviews validate security controls

**Non-Compliance**:
- Flagged in code review
- Requires remediation or exception approval
- Tracked as technical debt

---

## 14. SUMMARY CHECKLIST

Before proceeding with system design or implementation, verify:

**Technology Stack**:
- [ ] Compute: AWS Lambda (Python 3.12)
- [ ] API: Amazon API Gateway
- [ ] Data: Amazon DynamoDB + S3
- [ ] Messaging: EventBridge + SQS
- [ ] AI: Amazon Bedrock (Claude)
- [ ] Observability: OpenTelemetry + CloudWatch + X-Ray
- [ ] IaC: AWS CDK (Python)
- [ ] Security: Cognito + IAM + Secrets Manager
- [ ] Frontend: Angular + S3 + CloudFront

**Design Principles**:
- [ ] Serverless-first architecture
- [ ] Stateless compute
- [ ] Event-driven communication
- [ ] Managed services preferred
- [ ] Observability by default

**Compliance**:
- [ ] No unapproved technologies introduced
- [ ] Alternative technologies justified (if any)
- [ ] Security defaults applied
- [ ] Infrastructure as code (CDK)

---

**END OF SPECIFICATION**

This skill establishes the technology foundation for the platform. All downstream activities must operate within these constraints to ensure consistency, maintainability, and operational excellence.
