# DynamoDB Configuration Pattern

## Purpose

This pattern defines **standard DynamoDB table configuration** following AWS best practices for serverless applications.

## Standard Table Configuration

### CDK Template

```python
from aws_cdk import (
    aws_dynamodb as dynamodb,
    RemovalPolicy,
    Duration
)

table = dynamodb.Table(
    self, 'Table',
    table_name=f'{service_name}-{environment}',

    # Keys
    partition_key=dynamodb.Attribute(
        name='PK',
        type=dynamodb.AttributeType.STRING
    ),
    sort_key=dynamodb.Attribute(
        name='SK',
        type=dynamodb.AttributeType.STRING
    ),

    # Billing
    billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,  # On-demand

    # Encryption
    encryption=dynamodb.TableEncryption.AWS_MANAGED,  # SSE

    # Backup
    point_in_time_recovery=True if environment == 'prod' else False,

    # Streams
    stream=dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,

    # Time to Live
    time_to_live_attribute='ttl',

    # Removal policy
    removal_policy=RemovalPolicy.RETAIN if environment == 'prod' else RemovalPolicy.DESTROY
)
```

---

## 1. PRIMARY KEYS

### Single-Table Design Pattern

**RECOMMENDED**: Use generic `PK` and `SK` for flexibility.

```
PK (Partition Key): String
SK (Sort Key): String
```

**Key Pattern Examples**:
```
User:
  PK: USER#<user_id>
  SK: PROFILE

User Orders:
  PK: USER#<user_id>
  SK: ORDER#<order_id>

Order:
  PK: ORDER#<order_id>
  SK: METADATA
```

### Partition Key Design

**Goal**: Evenly distribute data across partitions.

**✅ GOOD**: High cardinality keys
- `USER#<uuid>`
- `ORDER#<uuid>`
- `SESSION#<uuid>`

**❌ BAD**: Low cardinality keys (hot partitions)
- `STATUS#active` (only a few values)
- `DATE#2024-01-15` (limited values)
- `TYPE#user` (all users in one partition)

### Sort Key for Query Flexibility

Sort keys enable:
- Range queries
- Filtering within partition
- Different entity types in same partition

**Example**:
```python
# Query all orders for a user
response = table.query(
    KeyConditionExpression=Key('PK').eq('USER#123') &
                           Key('SK').begins_with('ORDER#')
)
```

---

## 2. GLOBAL SECONDARY INDEXES (GSI)

### When to Use GSIs

- Query by alternate access pattern
- Query across partitions
- Inverted index (swap PK/SK)

### GSI Best Practices

**Sparse Indexes**: Only items with GSI attributes are indexed (saves cost).

```python
# Email index for user lookup
email_index = table.add_global_secondary_index(
    index_name='EmailIndex',
    partition_key=dynamodb.Attribute(
        name='email',
        type=dynamodb.AttributeType.STRING
    ),
    projection_type=dynamodb.ProjectionType.ALL
)
```

**Projection Types**:
- `KEYS_ONLY`: Only keys (smallest, cheapest)
- `INCLUDE`: Keys + specified attributes
- `ALL`: All attributes (largest, most expensive)

**Example with INCLUDE**:
```python
status_index = table.add_global_secondary_index(
    index_name='StatusIndex',
    partition_key=dynamodb.Attribute(name='status', type=dynamodb.AttributeType.STRING),
    sort_key=dynamodb.Attribute(name='created_at', type=dynamodb.AttributeType.STRING),
    projection_type=dynamodb.ProjectionType.INCLUDE,
    non_key_attributes=['email', 'name']  # Include only these
)
```

---

## 3. BILLING MODE

### On-Demand (RECOMMENDED for most cases)

```python
billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST
```

**Pros**:
- No capacity planning
- Automatic scaling
- Pay per request
- Good for unpredictable traffic

**Cons**:
- Higher per-request cost
- Can be expensive at high volume

### Provisioned (for predictable workloads)

```python
billing_mode=dynamodb.BillingMode.PROVISIONED,
read_capacity=5,
write_capacity=5,
```

**Pros**:
- Lower cost at high volume
- Predictable pricing

**Cons**:
- Requires capacity planning
- Throttling if exceeded
- Need to configure auto-scaling

**Auto-Scaling**:
```python
table.auto_scale_read_capacity(
    min_capacity=5,
    max_capacity=100
).scale_on_utilization(target_utilization_percent=70)
```

---

## 4. ENCRYPTION

### AWS Managed Keys (RECOMMENDED)

```python
encryption=dynamodb.TableEncryption.AWS_MANAGED
```

**Pros**:
- Free
- Automatic key rotation
- No key management

### Customer Managed KMS Keys

```python
from aws_cdk import aws_kms as kms

encryption_key = kms.Key(
    self, 'TableKey',
    enable_key_rotation=True
)

table = dynamodb.Table(
    self, 'Table',
    encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED,
    encryption_key=encryption_key
)
```

**Use when**:
- Compliance requires customer-managed keys
- Need audit trail of key usage
- Multi-region replication with CMK

---

## 5. POINT-IN-TIME RECOVERY (PITR)

### MANDATORY for Production

```python
point_in_time_recovery=True if environment == 'prod' else False
```

**Features**:
- Continuous backups
- 35-day retention
- Restore to any point in time
- No performance impact

**Cost**: ~$0.20 per GB-month

---

## 6. DYNAMODB STREAMS

### Enable for Event-Driven Patterns

```python
stream=dynamodb.StreamViewType.NEW_AND_OLD_IMAGES
```

**Stream View Types**:
- `KEYS_ONLY`: Only key attributes
- `NEW_IMAGE`: New item after modification
- `OLD_IMAGE`: Old item before modification
- `NEW_AND_OLD_IMAGES`: Both (RECOMMENDED)

**Use Cases**:
- Trigger Lambda on data changes
- Real-time aggregations
- Change data capture (CDC)
- Audit logs

**Example Lambda Trigger**:
```python
from aws_cdk import aws_lambda_event_sources as lambda_sources

stream_function = lambda_.Function(...)

stream_function.add_event_source(
    lambda_sources.DynamoEventSource(
        table=table,
        starting_position=lambda_.StartingPosition.LATEST,
        batch_size=100,
        max_batching_window=Duration.seconds(5)
    )
)
```

---

## 7. TIME TO LIVE (TTL)

### Automatic Item Expiration

```python
time_to_live_attribute='ttl'
```

**How it works**:
- Add `ttl` attribute (Unix timestamp)
- DynamoDB automatically deletes expired items
- Free (no WCU consumed)
- Deletion happens within 48 hours of expiration

**Example**:
```python
import time

# Set item to expire in 24 hours
item = {
    'PK': 'SESSION#abc',
    'SK': 'DATA',
    'data': 'session_data',
    'ttl': int(time.time()) + 86400  # Current time + 24 hours
}

table.put_item(Item=item)
```

**Use Cases**:
- Session data
- Temporary tokens
- Cache entries
- Audit logs with retention policy

---

## 8. TAGGING

### MANDATORY Tags

```python
from aws_cdk import Tags

Tags.of(table).add('Environment', environment)
Tags.of(table).add('Service', service_name)
Tags.of(table).add('ManagedBy', 'CDK')
Tags.of(table).add('CostCenter', cost_center)
```

---

## 9. DATA ACCESS PATTERNS

### Query (EFFICIENT)

```python
from boto3.dynamodb.conditions import Key

# Query by partition key
response = table.query(
    KeyConditionExpression=Key('PK').eq('USER#123')
)

# Query with sort key condition
response = table.query(
    KeyConditionExpression=Key('PK').eq('USER#123') &
                           Key('SK').begins_with('ORDER#')
)

# Query with filter (applied after query)
response = table.query(
    KeyConditionExpression=Key('PK').eq('USER#123'),
    FilterExpression=Attr('status').eq('active')
)
```

### Scan (AVOID in production)

```python
# ❌ Expensive - reads entire table
response = table.scan(
    FilterExpression=Attr('email').eq('user@example.com')
)

# ✅ Better - Use GSI with Query
response = table.query(
    IndexName='EmailIndex',
    KeyConditionExpression=Key('email').eq('user@example.com')
)
```

### Get Item (EFFICIENT)

```python
response = table.get_item(
    Key={
        'PK': 'USER#123',
        'SK': 'PROFILE'
    }
)

if 'Item' in response:
    user = response['Item']
```

### Batch Get (EFFICIENT for multiple items)

```python
from boto3.dynamodb.table import BatchWriter

response = dynamodb_client.batch_get_item(
    RequestItems={
        'users-table': {
            'Keys': [
                {'PK': 'USER#123', 'SK': 'PROFILE'},
                {'PK': 'USER#456', 'SK': 'PROFILE'}
            ]
        }
    }
)
```

### Put Item

```python
table.put_item(
    Item={
        'PK': 'USER#123',
        'SK': 'PROFILE',
        'email': 'user@example.com',
        'name': 'John Doe',
        'created_at': datetime.utcnow().isoformat()
    }
)
```

### Update Item (Atomic updates)

```python
table.update_item(
    Key={'PK': 'USER#123', 'SK': 'PROFILE'},
    UpdateExpression='SET #status = :status, updated_at = :timestamp',
    ExpressionAttributeNames={
        '#status': 'status'
    },
    ExpressionAttributeValues={
        ':status': 'active',
        ':timestamp': datetime.utcnow().isoformat()
    }
)
```

---

## 10. BEST PRACTICES

### ✅ DO

- Use single-table design when possible
- Use on-demand billing unless predictable high volume
- Enable point-in-time recovery for production
- Create GSIs for alternate access patterns
- Use sparse indexes to reduce costs
- Enable DynamoDB Streams for event-driven patterns
- Use TTL for automatic data expiration
- Query instead of Scan
- Use batch operations for multiple items
- Add appropriate tags for cost tracking

### ❌ DON'T

- Don't use Scan in production (use Query with GSI)
- Don't create too many GSIs (max 20, but fewer is better)
- Don't use ALL projection unless necessary
- Don't store large items (>400 KB item size limit)
- Don't create hot partitions (even distribution of keys)
- Don't use sequential IDs as partition keys
- Don't forget encryption at rest
- Don't skip point-in-time recovery for production

---

## 11. COST OPTIMIZATION

### Strategies

1. **On-Demand vs Provisioned**: Choose based on traffic predictability
2. **GSI Projection**: Use `KEYS_ONLY` or `INCLUDE` instead of `ALL`
3. **Sparse Indexes**: Index only items that need it
4. **TTL**: Automatically delete expired data
5. **Batch Operations**: Reduce request count
6. **Query vs Scan**: Always prefer Query
7. **Item Size**: Keep items small (<1 KB ideal)

---

## 12. COMPLETE EXAMPLE

```python
from aws_cdk import (
    Stack,
    aws_dynamodb as dynamodb,
    aws_lambda as lambda_,
    aws_lambda_event_sources as lambda_sources,
    RemovalPolicy,
    Duration,
    Tags
)
from constructs import Construct

class DataStack(Stack):
    def __init__(self, scope: Construct, id: str, environment: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        # Main table
        users_table = dynamodb.Table(
            self, 'UsersTable',
            table_name=f'users-{environment}',

            # Keys
            partition_key=dynamodb.Attribute(name='PK', type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name='SK', type=dynamodb.AttributeType.STRING),

            # Configuration
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            point_in_time_recovery=True if environment == 'prod' else False,
            stream=dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,
            time_to_live_attribute='ttl',

            # Removal policy
            removal_policy=RemovalPolicy.RETAIN if environment == 'prod' else RemovalPolicy.DESTROY
        )

        # GSI for email lookup
        users_table.add_global_secondary_index(
            index_name='EmailIndex',
            partition_key=dynamodb.Attribute(name='email', type=dynamodb.AttributeType.STRING),
            projection_type=dynamodb.ProjectionType.INCLUDE,
            non_key_attributes=['name', 'status']
        )

        # GSI for status queries
        users_table.add_global_secondary_index(
            index_name='StatusIndex',
            partition_key=dynamodb.Attribute(name='status', type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name='created_at', type=dynamodb.AttributeType.STRING),
            projection_type=dynamodb.ProjectionType.KEYS_ONLY
        )

        # Tagging
        Tags.of(users_table).add('Environment', environment)
        Tags.of(users_table).add('Service', 'user-service')
        Tags.of(users_table).add('ManagedBy', 'CDK')

        # Lambda to process stream
        stream_processor = lambda_.Function(
            self, 'StreamProcessor',
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler='handler.lambda_handler',
            code=lambda_.Code.from_asset('path/to/code')
        )

        # Add DynamoDB Stream as event source
        stream_processor.add_event_source(
            lambda_sources.DynamoEventSource(
                table=users_table,
                starting_position=lambda_.StartingPosition.LATEST,
                batch_size=100,
                max_batching_window=Duration.seconds(5)
            )
        )
```

---

## References

- **Used in Skills**: code-generation.md, code-review.md, technology-standards.md
- **Enforced by**: code-review.md (Infrastructure Review)
- **Technology Stack**: technology-standards.md (DynamoDB as primary datastore)

---

**Follow this pattern for optimized, scalable DynamoDB table configuration.**
