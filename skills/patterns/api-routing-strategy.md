# API Routing Strategy: The Micro-Lambda Pattern

## Purpose
By migrating from Lambda Powertools to standard OpenTelemetry, we removed the proprietary `APIGatewayRestResolver`. AWS Lambda natively has **no routing capabilities**. 

To prevent developers from building brittle string-matching routers inside Lambdas, we strictly enforce the **Micro-Lambda Pattern**.

---

## The Rule: 1 API = 1 Lambda Function (Separate Directory)

A Lambda function MUST serve exactly one specific purpose corresponding to one API endpoint and HTTP method.

**CRITICAL**: Each distinct API must have its own Lambda directory under `backend/lambdas/{api_name}/`. This is NOT just about having separate handler files - it's about having completely isolated deployment units.

### Lambda Directory = Independent Microservice

```
backend/lambdas/
├── hello-world/          # ✅ Microservice 1: Separate directory, separate deployment
│   └── src/handlers/hello_handler.py
└── calculator/           # ✅ Microservice 2: Separate directory, separate deployment
    └── src/handlers/calculator_handler.py
```

**Each directory becomes**:
- A separate Lambda deployment package
- An independent AWS Lambda function
- Separately scalable
- Independently deployable
- Isolated failure domain

### ❌ Anti-Pattern: The Monolithic Router

**FORBIDDEN**: Building a giant `if/else` block inside a single monolithic Lambda to handle an entire domain.

```python
# ANTI-PATTERN: DO NOT DO THIS
def lambda_handler(event, context):
    path = event.get('resource')
    method = event.get('httpMethod')

    if path == '/users' and method == 'GET':
        return get_all_users()
    elif path == '/users' and method == 'POST':
        return create_user(event)
    elif path == '/users/{id}' and method == 'GET':
        return get_user_by_id(event)
    elif path == '/users/{id}' and method == 'DELETE':
        return delete_user(event)
    else:
        return {"statusCode": 404, "body": "Not Found"}
```

**Why it's forbidden**:
1. Bloats the Lambda deployment package size.
2. Complicates IAM Least Privilege (the lambda needs permissions for *every* database action).
3. Breaks Single Responsibility.
4. Makes OpenTelemetry tracing metrics heavily skewed (all invocations clump into one function metric).

---

## ✅ Best Practice: Micro-Lambda Integration

Every distinct operation gets its own Lambda Handler. The routing is performed by **Amazon API Gateway** via the CDK.

### 1. The Handlers
```
src/handlers/
  create_user.py
  get_user.py
  delete_user.py
```

Each handler receives the event and IMMEDIATELY passes it to the Service layer. There is no routing logic.

```python
# src/handlers/create_user.py
import json
import logging
from opentelemetry import trace
from src.services.user_service import UserService

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

def lambda_handler(event, context):
    span = trace.get_current_span()
    trace_id = format(span.get_span_context().trace_id, '032x')
    
    # NO ROUTING. Just parse and pass.
    body = json.loads(event.get('body', '{}'))
    user = UserService().create_user(body)
    
    return {"statusCode": 201, "body": json.dumps(user)}
```

### 2. The CDK Routing
API Gateway uses the AWS CDK to map specific endpoints directly to specific Micro-Lambdas.

```python
from aws_cdk import aws_apigateway as apigw

api = apigw.RestApi(self, 'UserApi')
users_resource = api.root.add_resource('users')

# Route: POST /users -> CreateUser Lambda
users_resource.add_method('POST', apigw.LambdaIntegration(create_user_lambda))

# Route: GET /users/{id} -> GetUser Lambda
user_id_resource = users_resource.add_resource('{id}')
user_id_resource.add_method('GET', apigw.LambdaIntegration(get_user_lambda))
```

### Exceptions
The only exception to this rule is a tightly coupled GraphQL handler (like AppSync or Apollo Server), where a single endpoint (`POST /graphql`) handles the routing via standard GraphQL schema resolution. For standard REST APIs, the Micro-Lambda pattern is mandatory.
