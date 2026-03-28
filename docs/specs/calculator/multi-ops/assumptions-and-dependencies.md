# Calculator Multi-Operator Enhancement - Assumptions and Dependencies

**Date**: 2026-03-28

---

## Assumptions

### A-001
**Type**: Assumption
**Description**: The existing calculator Lambda function and API Gateway configuration can be extended with new routes without requiring a separate Lambda deployment.
**Impact if Invalid**: Infrastructure design would need separate Lambda functions per operation, increasing deployment complexity.

### A-002
**Type**: Assumption
**Description**: Division by zero is the only division-specific error case. Non-zero divisors always produce valid results within float range.
**Impact if Invalid**: Additional error handling may be needed for edge cases like NaN results.

### A-003
**Type**: Assumption
**Description**: All four operations share the same request validation rules (both operands required, must be numeric).
**Impact if Invalid**: Operation-specific validation rules would increase DTO complexity.

### A-004
**Type**: Assumption
**Description**: Existing test infrastructure (pytest, moto, conftest fixtures) supports adding tests for new operations without structural changes.
**Impact if Invalid**: Test infrastructure refactoring would be needed before implementation.

---

## Dependencies

### D-001
**Type**: Dependency
**Description**: Existing shared middleware (@api_gateway_handler, @observe) supports routing multiple operations within a single Lambda.
**Impact if Invalid**: Middleware may need enhancement to support multi-endpoint routing.

### D-002
**Type**: Dependency
**Description**: Existing Pydantic DTO structure (CalculatorRequest) can be reused across all operations without modification.
**Impact if Invalid**: New request DTOs would need to be created per operation.

### D-003
**Type**: Dependency
**Description**: Existing CDK stack supports adding new API Gateway resources to the calculator endpoint.
**Impact if Invalid**: CDK stack modifications would be needed before implementation.
