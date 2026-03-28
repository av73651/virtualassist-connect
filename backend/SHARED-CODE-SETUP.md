# Shared Code Setup for Lambdas

**Date**: 2026-03-28
**Purpose**: Document how shared code (middleware, config) is used across multiple Lambda functions

---

## Directory Structure

```
backend/
├── shared/                     # ✅ Shared code used by all Lambdas
│   ├── __init__.py
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── api_gateway.py     # @api_gateway_handler decorator
│   │   └── observability.py   # @observe decorator
│   └── config/
│       ├── __init__.py
│       └── logging_config.py  # Structured JSON logging
│
└── lambdas/
    ├── hello-world/            # Lambda 1
    │   ├── src/
    │   │   ├── domain/
    │   │   ├── dto/
    │   │   ├── services/
    │   │   └── handlers/
    │   └── tests/
    │
    └── calculator/             # Lambda 2
        ├── src/
        │   ├── domain/
        │   ├── dto/
        │   ├── services/
        │   └── handlers/
        └── tests/
```

---

## Why Shared Code?

### **Problem Without Shared Code**
- ❌ Duplicate middleware in every Lambda
- ❌ Bug fixes require updating multiple files
- ❌ Inconsistent implementations across Lambdas
- ❌ Violates DRY (Don't Repeat Yourself) principle

### **Solution With Shared Code**
- ✅ Single source of truth for common code
- ✅ Bug fixes update all Lambdas automatically
- ✅ Consistent behavior across all APIs
- ✅ Follows microservices best practices

---

## Shared Modules

### 1. **shared/middleware/api_gateway.py**
**Purpose**: AOP decorator for API Gateway Lambda handlers

**Features**:
- Trace ID extraction from X-Ray headers
- Request/response logging with structured context
- Exception handling (ValidationError → 400, Exception → 500)
- HTTP response formatting
- CORS headers management

**Usage**:
```python
from shared.middleware.api_gateway import api_gateway_handler

@api_gateway_handler
def lambda_handler(event, context, trace_id):
    return {"message": "Hello"}
```

---

### 2. **shared/middleware/observability.py**
**Purpose**: AOP decorator for OpenTelemetry tracing, metrics, and logging

**Features**:
- OpenTelemetry distributed tracing (span creation)
- Metrics collection (counter + histogram)
- Structured logging (entry/exit/error)
- Performance timing
- Error recording in spans

**Usage**:
```python
from shared.middleware.observability import observe

@observe(operation="add_numbers", metric_prefix="calculator_add")
def add(self, a, b):
    return a + b
```

---

### 3. **shared/config/logging_config.py**
**Purpose**: Structured JSON logging configuration

**Features**:
- JSON formatter for CloudWatch Logs Insights
- Timezone-aware timestamps
- Extra fields support for structured context
- Exception stack trace formatting

**Usage**:
```python
from shared.config.logging_config import configure_structured_logging

configure_structured_logging()
logger = logging.getLogger(__name__)
logger.info("Request received", extra={"user_id": "123"})
```

---

## Import Strategy

### Local Development

**PYTHONPATH Setup**:
```bash
# In each Lambda directory, set PYTHONPATH to include backend root
export PYTHONPATH="/path/to/virtualassist-connect/backend:$PYTHONPATH"

# Then imports work:
from shared.middleware.api_gateway import api_gateway_handler
```

### Testing

**pytest.ini** (in each Lambda):
```ini
[pytest]
pythonpath = /path/to/virtualassist-connect/backend
```

**Or use sys.path in tests/conftest.py**:
```python
import sys
from pathlib import Path

# Add backend root to path
backend_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(backend_root))
```

---

## Lambda Deployment Strategy

### Option 1: Lambda Layers (RECOMMENDED) ✅

**Create shared layer**:
```bash
cd backend
mkdir -p lambda-layer/python
cp -r shared lambda-layer/python/
cd lambda-layer
zip -r shared-layer.zip python/
```

**Upload as Lambda Layer**:
```bash
aws lambda publish-layer-version \
  --layer-name shared-middleware \
  --zip-file fileb://shared-layer.zip \
  --compatible-runtimes python3.12
```

**Attach to Lambdas** (in CDK):
```python
shared_layer = lambda_.LayerVersion.from_layer_version_arn(
    self, "SharedLayer",
    layer_version_arn="arn:aws:lambda:us-west-2:123456:layer:shared-middleware:1"
)

hello_lambda = lambda_.Function(
    self, "HelloWorldFunction",
    # ... other config ...
    layers=[shared_layer, adot_layer]
)

calculator_lambda = lambda_.Function(
    self, "CalculatorFunction",
    # ... other config ...
    layers=[shared_layer, adot_layer]
)
```

**Benefits**:
- ✅ Shared code deployed once, used by all Lambdas
- ✅ Reduces deployment package size
- ✅ Update layer to update all Lambdas
- ✅ Versioned layers enable rollback

---

### Option 2: Include in Each Deployment Package

**Copy shared code to each Lambda package**:
```bash
# In each Lambda directory
cp -r ../../shared ./
zip -r function.zip src/ shared/
```

**Benefits**:
- ✅ Simpler deployment (no layer management)
- ✅ Each Lambda is self-contained

**Drawbacks**:
- ❌ Duplicate code in each package
- ❌ Larger deployment packages
- ❌ Must redeploy all Lambdas for shared code changes

---

## CDK Integration

### Separate Lambda Functions

**infra/stacks/api_stack.py**:
```python
class ApiStack(Stack):
    def __init__(self, scope, construct_id, config, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # Shared layer
        shared_layer = self._create_shared_layer()

        # Hello World Lambda
        self.hello_lambda = lambda_.Function(
            self, "HelloWorldFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="src.handlers.hello_handler.lambda_handler",
            code=lambda_.Code.from_asset("../lambdas/hello-world"),
            layers=[shared_layer, adot_layer],
            # ... other config ...
        )

        # Calculator Lambda
        self.calculator_lambda = lambda_.Function(
            self, "CalculatorFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="src.handlers.calculator_handler.lambda_handler",
            code=lambda_.Code.from_asset("../lambdas/calculator"),
            layers=[shared_layer, adot_layer],
            # ... other config ...
        )

        # API Gateway with multiple integrations
        api = apigw.RestApi(self, "Api", ...)

        hello_resource = api.root.add_resource("hello")
        hello_resource.add_method("GET", apigw.LambdaIntegration(self.hello_lambda))

        calculator_resource = api.root.add_resource("calculator")
        add_resource = calculator_resource.add_resource("add")
        add_resource.add_method("POST", apigw.LambdaIntegration(self.calculator_lambda))

    def _create_shared_layer(self):
        return lambda_.LayerVersion(
            self, "SharedLayer",
            code=lambda_.Code.from_asset("../shared"),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            description="Shared middleware and config for all Lambdas"
        )
```

---

## Testing with Shared Code

### Unit Tests

**tests/conftest.py** (in each Lambda):
```python
import sys
from pathlib import Path

# Add backend root to Python path for shared imports
backend_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(backend_root))
```

**Test imports work**:
```python
from shared.middleware.api_gateway import api_gateway_handler  # ✅ Works
from shared.middleware.observability import observe            # ✅ Works
```

### Run Tests

```bash
cd backend/lambdas/hello-world
pytest tests/

cd backend/lambdas/calculator
pytest tests/
```

---

## Maintenance

### Updating Shared Code

**Process**:
1. Update code in `backend/shared/`
2. Run tests for ALL Lambdas to verify no breakage:
   ```bash
   cd backend/lambdas/hello-world && pytest
   cd backend/lambdas/calculator && pytest
   ```
3. Update Lambda layer version
4. Redeploy Lambdas (or they'll pick up new layer on next deployment)

### Adding New Shared Modules

**Example: Add shared DTO validation**:
```bash
mkdir backend/shared/dto
touch backend/shared/dto/__init__.py
# Create backend/shared/dto/validation.py
```

**Use in Lambdas**:
```python
from shared.dto.validation import validate_email
```

---

## Best Practices

### ✅ DO

1. **Keep shared code stable** - Many Lambdas depend on it
2. **Version Lambda layers** - Enable rollback if issues
3. **Test shared code changes across all Lambdas** - Avoid breaking changes
4. **Document shared module APIs** - Other teams will use them
5. **Use type hints** - Makes shared code easier to use

### ❌ DON'T

1. **Don't put Lambda-specific logic in shared code** - Keep it generic
2. **Don't make breaking changes** - Use versioning for major changes
3. **Don't duplicate shared code** - Always import from shared/
4. **Don't skip testing** - Shared code bugs affect all Lambdas

---

## Current Shared Modules

| Module | Purpose | Used By |
|--------|---------|---------|
| `shared.middleware.api_gateway` | HTTP request/response handling | All Lambda handlers |
| `shared.middleware.observability` | Tracing, metrics, logging | All service layers |
| `shared.config.logging_config` | Structured JSON logging | All modules |

---

## Future Shared Modules

Candidates for shared code:
- `shared.dto.error` - Standard error response DTOs
- `shared.auth.jwt` - JWT token validation
- `shared.database.dynamodb` - DynamoDB connection pool
- `shared.utils.datetime` - Timezone-aware datetime helpers
- `shared.validators.input` - Common input validators

---

## Summary

**Current Architecture**: ✅ **Correct**

```
backend/
├── shared/              # Single source of truth
│   ├── middleware/
│   └── config/
└── lambdas/
    ├── hello-world/     # Uses shared code
    └── calculator/      # Uses shared code
```

**Benefits**:
- ✅ No code duplication
- ✅ Consistent behavior
- ✅ Easy maintenance
- ✅ Follows DRY principle
- ✅ Microservices best practices

**Deployment**: Use Lambda Layers for production efficiency.
