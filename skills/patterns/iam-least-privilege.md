# IAM Least Privilege Pattern

## Purpose

This pattern defines **least privilege IAM policies** for AWS Lambda functions, following security best practices.

## Principle

**Grant only the permissions required to perform the task - no more, no less.**

- Specific actions (not wildcards)
- Specific resources (not *)
- Conditions where applicable
- Time-bound permissions (session policies when appropriate)

---

## Standard Patterns

### 1. DynamoDB Access

#### Read/Write Access to Specific Table

```python
from aws_cdk import aws_iam as iam

function.add_to_role_policy(
    iam.PolicyStatement(
        effect=iam.Effect.ALLOW,
        actions=[
            'dynamodb:GetItem',
            'dynamodb:PutItem',
            'dynamodb:UpdateItem',
            'dynamodb:Query'
        ],
        resources=[
            table.table_arn,  # Main table
            f'{table.table_arn}/index/*'  # GSIs
        ]
    )
)
```

#### Read-Only Access

```python
function.add_to_role_policy(
    iam.PolicyStatement(
        effect=iam.Effect.ALLOW,
        actions=[
            'dynamodb:GetItem',
            'dynamodb:Query',
            'dynamodb:Scan'  # Use sparingly
        ],
        resources=[table.table_arn]
    )
)
```

#### DynamoDB Streams Access

```python
function.add_to_role_policy(
    iam.PolicyStatement(
        effect=iam.Effect.ALLOW,
        actions=[
            'dynamodb:GetRecords',
            'dynamodb:GetShardIterator',
            'dynamodb:DescribeStream',
            'dynamodb:ListStreams'
        ],
        resources=[f'{table.table_arn}/stream/*']
    )
)
```

---

### 2. S3 Access

#### Read Access to Specific Bucket

```python
function.add_to_role_policy(
    iam.PolicyStatement(
        effect=iam.Effect.ALLOW,
        actions=[
            's3:GetObject',
            's3:ListBucket'
        ],
        resources=[
            bucket.bucket_arn,  # For ListBucket
            f'{bucket.bucket_arn}/*'  # For GetObject
        ]
    )
)
```

#### Write Access to Specific Prefix

```python
function.add_to_role_policy(
    iam.PolicyStatement(
        effect=iam.Effect.ALLOW,
        actions=[
            's3:PutObject',
            's3:PutObjectAcl'
        ],
        resources=[f'{bucket.bucket_arn}/uploads/*']
    )
)
```

---

### 3. Secrets Manager Access

#### Read Specific Secret

```python
function.add_to_role_policy(
    iam.PolicyStatement(
        effect=iam.Effect.ALLOW,
        actions=['secretsmanager:GetSecretValue'],
        resources=[
            f'arn:aws:secretsmanager:{region}:{account}:secret:virtualassist/*'
        ]
    )
)
```

---

### 4. Bedrock Access

#### Invoke Claude Models

```python
function.add_to_role_policy(
    iam.PolicyStatement(
        effect=iam.Effect.ALLOW,
        actions=[
            'bedrock:InvokeModel',
            'bedrock:InvokeModelWithResponseStream'
        ],
        resources=[
            f'arn:aws:bedrock:{region}::foundation-model/anthropic.claude-*'
        ]
    )
)
```

---

### 5. EventBridge Access

#### Put Events to Specific Event Bus

```python
function.add_to_role_policy(
    iam.PolicyStatement(
        effect=iam.Effect.ALLOW,
        actions=['events:PutEvents'],
        resources=[event_bus.event_bus_arn]
    )
)
```

---

### 6. SQS Access

#### Send Messages to Queue

```python
function.add_to_role_policy(
    iam.PolicyStatement(
        effect=iam.Effect.ALLOW,
        actions=[
            'sqs:SendMessage',
            'sqs:GetQueueAttributes'
        ],
        resources=[queue.queue_arn]
    )
)
```

#### Receive and Delete Messages

```python
function.add_to_role_policy(
    iam.PolicyStatement(
        effect=iam.Effect.ALLOW,
        actions=[
            'sqs:ReceiveMessage',
            'sqs:DeleteMessage',
            'sqs:GetQueueAttributes'
        ],
        resources=[queue.queue_arn]
    )
)
```

---

### 7. CloudWatch Logs (Basic Execution Role)

**ALWAYS required** for Lambda functions:

```python
from aws_cdk import aws_iam as iam

role = iam.Role(
    self, 'LambdaRole',
    assumed_by=iam.ServicePrincipal('lambda.amazonaws.com'),
    managed_policies=[
        iam.ManagedPolicy.from_aws_managed_policy_name(
            'service-role/AWSLambdaBasicExecutionRole'
        )
    ]
)
```

This grants:
- `logs:CreateLogGroup`
- `logs:CreateLogStream`
- `logs:PutLogEvents`

---

## Common Violations

### ❌ VIOLATION: Wildcard Actions

```python
# WRONG
function.add_to_role_policy(
    iam.PolicyStatement(
        effect=iam.Effect.ALLOW,
        actions=['dynamodb:*'],  # ❌ Too broad
        resources=['*']  # ❌ All resources
    )
)
```

### ✅ CORRECT: Specific Actions and Resources

```python
# CORRECT
function.add_to_role_policy(
    iam.PolicyStatement(
        effect=iam.Effect.ALLOW,
        actions=['dynamodb:GetItem', 'dynamodb:PutItem', 'dynamodb:Query'],
        resources=[
            f'arn:aws:dynamodb:{region}:{account}:table/users',
            f'arn:aws:dynamodb:{region}:{account}:table/users/index/*'
        ]
    )
)
```

---

### ❌ VIOLATION: Resource Wildcard in Production

```python
# WRONG (especially in production)
function.add_to_role_policy(
    iam.PolicyStatement(
        effect=iam.Effect.ALLOW,
        actions=['s3:GetObject'],
        resources=['arn:aws:s3:::*/*']  # ❌ All S3 objects
    )
)
```

### ✅ CORRECT: Specific Bucket

```python
# CORRECT
function.add_to_role_policy(
    iam.PolicyStatement(
        effect=iam.Effect.ALLOW,
        actions=['s3:GetObject'],
        resources=[f'arn:aws:s3:::{bucket_name}/*']
    )
)
```

---

## Conditions for Enhanced Security

### Restrict by Source IP

```python
function.add_to_role_policy(
    iam.PolicyStatement(
        effect=iam.Effect.ALLOW,
        actions=['dynamodb:GetItem'],
        resources=[table.table_arn],
        conditions={
            'IpAddress': {
                'aws:SourceIp': ['10.0.0.0/8']
            }
        }
    )
)
```

### Restrict by VPC

```python
function.add_to_role_policy(
    iam.PolicyStatement(
        effect=iam.Effect.ALLOW,
        actions=['s3:GetObject'],
        resources=[f'{bucket.bucket_arn}/*'],
        conditions={
            'StringEquals': {
                'aws:SourceVpc': vpc_id
            }
        }
    )
)
```

### Require MFA

```python
function.add_to_role_policy(
    iam.PolicyStatement(
        effect=iam.Effect.ALLOW,
        actions=['dynamodb:DeleteItem'],
        resources=[table.table_arn],
        conditions={
            'Bool': {
                'aws:MultiFactorAuthPresent': 'true'
            }
        }
    )
)
```

---

## Environment-Specific Policies

### Development
More permissive (for debugging):
```python
if environment == 'dev':
    function.add_to_role_policy(
        iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                'dynamodb:Scan',  # Allowed in dev for debugging
                'cloudwatch:GetMetricStatistics'
            ],
            resources=['*']
        )
    )
```

### Production
Strict least privilege:
```python
if environment == 'prod':
    function.add_to_role_policy(
        iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=['dynamodb:GetItem', 'dynamodb:PutItem'],
            resources=[table.table_arn]  # Specific resource only
        )
    )
```

---

## Role Patterns

### Single Role Per Function

**RECOMMENDED**: Each Lambda function has its own IAM role.

```python
user_function_role = iam.Role(
    self, 'UserFunctionRole',
    assumed_by=iam.ServicePrincipal('lambda.amazonaws.com'),
    description='Role for user management function'
)

user_function = lambda_.Function(
    self, 'UserFunction',
    role=user_function_role,
    # ...
)

# Add specific permissions
user_function_role.add_to_policy(
    iam.PolicyStatement(
        actions=['dynamodb:GetItem', 'dynamodb:PutItem'],
        resources=[users_table.table_arn]
    )
)
```

### ❌ AVOID: Shared Roles Across Functions

```python
# WRONG: Sharing role gives excessive permissions
shared_role = iam.Role(...)

function1 = lambda_.Function(self, 'Func1', role=shared_role)
function2 = lambda_.Function(self, 'Func2', role=shared_role)

# Function1 now has permissions Function2 needs (and vice versa) ❌
```

---

## Verification Checklist

Before deploying IAM policies:

- [ ] Actions are specific (no `*` in production)
- [ ] Resources are specific (no wildcard ARNs in production)
- [ ] Conditions applied where appropriate
- [ ] Each function has its own role
- [ ] Development vs production policies differentiated
- [ ] Policies tested in lower environment
- [ ] Policy reviewed by security team (production)
- [ ] Unused permissions removed

---

## CDK Complete Example

```python
from aws_cdk import (
    Stack,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_dynamodb as dynamodb
)
from constructs import Construct

class UserApiStack(Stack):
    def __init__(self, scope: Construct, id: str, environment: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        # DynamoDB table
        users_table = dynamodb.Table(
            self, 'UsersTable',
            partition_key=dynamodb.Attribute(name='PK', type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST
        )

        # Lambda role with least privilege
        user_function_role = iam.Role(
            self, 'UserFunctionRole',
            assumed_by=iam.ServicePrincipal('lambda.amazonaws.com'),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    'service-role/AWSLambdaBasicExecutionRole'
                )
            ]
        )

        # Grant specific DynamoDB permissions
        user_function_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    'dynamodb:GetItem',
                    'dynamodb:PutItem',
                    'dynamodb:Query',
                    'dynamodb:UpdateItem'
                ],
                resources=[
                    users_table.table_arn,
                    f'{users_table.table_arn}/index/*'
                ]
            )
        )

        # Grant Secrets Manager access
        user_function_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=['secretsmanager:GetSecretValue'],
                resources=[
                    f'arn:aws:secretsmanager:{self.region}:{self.account}:secret:virtualassist/api-keys-*'
                ]
            )
        )

        # Lambda function
        user_function = lambda_.Function(
            self, 'UserFunction',
            role=user_function_role,
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler='handler.lambda_handler',
            code=lambda_.Code.from_asset('path/to/code')
        )
```

---

## References

- **Used in Skills**: code-generation.md, code-review.md, technology-standards.md
- **Enforced by**: code-review.md (Security Review - IAM)
- **Severity**: CRITICAL for wildcard violations in production

---

**Follow this pattern to ensure security and compliance with least privilege principle.**
