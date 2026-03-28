# Calculator Multi-Operator Enhancement - Infrastructure Design

**Date**: 2026-03-28
**Status**: Draft
**Version**: 1.0
**Based on**: calculator-multi-ops-app-design.md v1.0

---

## 1. Infrastructure Overview

### Approach
Extend the existing calculator CDK stack to add three new API Gateway resources pointing to the same Lambda function. No new Lambda functions or DynamoDB tables required.

### Changes Summary
- Add 3 new API Gateway resources: `/calculator/subtract`, `/calculator/multiply`, `/calculator/divide`
- All route to existing calculator Lambda (same integration pattern as `/calculator/add`)
- Update CloudWatch dashboard with per-operation widgets
- Add CloudWatch alarms for new operations

---

## 2. API Gateway Changes

### New Resources

```python
# Existing
calculator_resource = api.root.add_resource("calculator")
add_resource = calculator_resource.add_resource("add")

# New resources (same pattern)
subtract_resource = calculator_resource.add_resource("subtract")
multiply_resource = calculator_resource.add_resource("multiply")
divide_resource = calculator_resource.add_resource("divide")

# All POST methods use same Lambda integration
for resource in [subtract_resource, multiply_resource, divide_resource]:
    resource.add_method(
        "POST",
        calculator_integration,  # Same LambdaIntegration
        method_responses=[
            apigw.MethodResponse(status_code="200"),
            apigw.MethodResponse(status_code="400")
        ]
    )

    # CORS support
    resource.add_method(
        "OPTIONS",
        apigw.MockIntegration(...)
    )
```

### Throttling (Unchanged)
- Steady state: 500 RPS (shared across all calculator operations)
- Burst: 1000 RPS
- Per-method throttling not required for MVP

---

## 3. Lambda Configuration (Unchanged)

No changes to Lambda function configuration:
- **Runtime**: Python 3.12
- **Memory**: From `infra/config.json`
- **Timeout**: From `infra/config.json`
- **Handler**: Points to existing calculator handler (which now routes by path)
- **ADOT Layer**: Existing OpenTelemetry layer for tracing

---

## 4. CloudWatch Dashboard Enhancement

### New Widgets

```python
# Per-operation invocation counts
dashboard.add_widgets(
    cloudwatch.GraphWidget(
        title="Calculator Operations - Invocation Count",
        left=[
            calculator_lambda.metric_invocations(
                dimensions_map={"Operation": "subtract"},
                label="Subtract"
            ),
            calculator_lambda.metric_invocations(
                dimensions_map={"Operation": "multiply"},
                label="Multiply"
            ),
            calculator_lambda.metric_invocations(
                dimensions_map={"Operation": "divide"},
                label="Divide"
            ),
        ]
    )
)

# Per-operation latency
dashboard.add_widgets(
    cloudwatch.GraphWidget(
        title="Calculator Operations - Latency (ms)",
        left=[
            # Custom metrics from @observe decorator
            cloudwatch.Metric(
                namespace="Calculator",
                metric_name="calculator_subtract_duration",
                statistic="p95"
            ),
            cloudwatch.Metric(
                namespace="Calculator",
                metric_name="calculator_multiply_duration",
                statistic="p95"
            ),
            cloudwatch.Metric(
                namespace="Calculator",
                metric_name="calculator_divide_duration",
                statistic="p95"
            ),
        ]
    )
)

# Division by zero error count
dashboard.add_widgets(
    cloudwatch.GraphWidget(
        title="Division by Zero Errors",
        left=[
            cloudwatch.Metric(
                namespace="Calculator",
                metric_name="calculator_divide_total",
                dimensions_map={"status": "error"},
                statistic="Sum"
            )
        ]
    )
)
```

---

## 5. CloudWatch Alarms

### New Alarms

```python
# High error rate across all calculator operations
cloudwatch.Alarm(
    scope=self,
    id="CalculatorHighErrorRate",
    metric=calculator_lambda.metric_errors(
        period=Duration.minutes(5)
    ),
    threshold=10,
    evaluation_periods=2,
    alarm_description="Calculator Lambda error rate > 10 errors in 5 min"
)

# Division by zero spike (potential abuse)
cloudwatch.Alarm(
    scope=self,
    id="DivisionByZeroSpike",
    metric=cloudwatch.Metric(
        namespace="Calculator",
        metric_name="calculator_divide_total",
        dimensions_map={"status": "error"},
        period=Duration.minutes(5),
        statistic="Sum"
    ),
    threshold=50,
    evaluation_periods=1,
    alarm_description="High division-by-zero rate - potential abuse"
)
```

---

## 6. IAM Permissions (Unchanged)

No new IAM permissions needed. The calculator Lambda does not access any AWS services (no DynamoDB, S3, etc.). Existing execution role with CloudWatch Logs write permission is sufficient.

---

## 7. WAF / Security (Unchanged)

No changes to WAF or security configuration. API Gateway throttling provides protection against abuse. The same CORS and rate limiting settings apply to new endpoints.

---

## 8. Cost Impact

### Estimated Additional Cost

| Resource | Change | Cost Impact |
|----------|--------|-------------|
| API Gateway | 3 new routes | Negligible (pay per request) |
| Lambda | Same function, more invocations | ~$0.20/million additional requests |
| CloudWatch | Additional metrics + alarms | ~$3/month (6 custom metrics + 2 alarms) |
| **Total** | | **~$3-5/month** at expected traffic |

No new resources provisioned - purely additive API routes to existing infrastructure.

---

## 9. Deployment Strategy

1. CDK stack update adds new API Gateway resources
2. Lambda code deployed with multi-operation handler
3. No breaking changes to existing `/calculator/add` endpoint
4. Rollback: Remove new API Gateway resources (add endpoint unaffected)

### Deployment Order
1. Deploy Lambda code with routing + new operations (backward compatible)
2. Deploy CDK stack with new API Gateway resources
3. Run smoke tests against all 4 endpoints
4. Monitor CloudWatch dashboard for errors
