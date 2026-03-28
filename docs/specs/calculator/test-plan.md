# Test Plan: calculator

## Source
docs/specs/calculator/calculator-requirements.md

## Traceability Matrix

| Source | ID | Description | Test Type | Test Name | Layer | Status |
|--------|----|-------------|-----------|-----------|-------|--------|
| AC | AC-001 | Two positive integers return correct sum (5 + 3 = 8) | Unit | test_create_addition_positive_integers_AC_001 | Domain | mapped |
| AC | AC-002 | Two negative integers return correct sum (-5 + -3 = -8) | Unit | test_create_addition_negative_integers_AC_002 | Domain | mapped |
| AC | AC-002 | Negative numbers through service layer | Unit | test_add_handles_negative_numbers | Service | mapped |
| AC | AC-002 | Negative numbers through handler layer | Unit | test_handle_add_request_negative_numbers | Handler | mapped |
| AC | AC-003 | One positive and one negative integer return correct sum (5 + -3 = 2) | Unit | test_create_addition_mixed_signs_AC_003 | Domain | mapped |
| AC | AC-004 | Two floating-point numbers return correct sum (5.5 + 3.2 = 8.7) | Unit | test_create_addition_floats_AC_004 | Domain | mapped |
| AC | AC-004 | Float precision through service layer | Unit | test_add_correct_result | Service | mapped |
| AC | AC-004 | Float values through handler layer | Unit | test_handle_add_request_correct_values | Handler | mapped |
| AC | AC-005 | Zero as one operand returns the other operand (0 + 5 = 5) | Unit | test_create_addition_zero_operand_AC_005 | Domain | mapped |
| AC | AC-005 | Zero operands through service layer | Unit | test_add_handles_zero | Service | mapped |
| AC | AC-005 | Zero operands through handler layer | Unit | test_handle_add_request_zero_operands | Handler | mapped |
| AC | AC-006 | Missing operand returns 400 Bad Request with error details | Unit | test_lambda_handler_missing_field_returns_400_AC_006 | Handler | mapped |
| AC | AC-007 | Non-numeric operand returns 400 Bad Request with error details | Unit | test_lambda_handler_non_numeric_returns_400_AC_007 | Handler | mapped |
| AC | AC-008 | Null operand returns 400 Bad Request with error details | Unit | test_lambda_handler_null_operand_returns_400_AC_008 | Handler | mapped |
| AC | AC-009 | Response includes result, operands, operation, and timestamp | Unit | test_handle_add_request_contains_result_AC_009 | Handler | mapped |
| AC | AC-010 | Content-Type is application/json | Unit | test_lambda_handler_content_type_header_AC_010 | Handler | mapped |
| AC | AC-011 | Error response includes errorCode, message, and correlationId | Unit | test_lambda_handler_error_includes_correlation_id_AC_011 | Handler | mapped |
| AC | AC-012 | Internal error returns 500 with generic error message (no sensitive data) | Unit | test_lambda_handler_with_exception_returns_500_AC_012 | Handler | mapped |
| TR | TR-001 | API response time < 100ms at p95 | Performance | -- | -- | gap |
| TR | TR-007 | IEEE 754 double precision support | Unit | test_large_numbers, test_very_small_numbers | Domain | mapped |
| TR | TR-008 | Values from -1e308 to +1e308 | Unit | test_infinity_handling, test_negative_infinity_handling | Domain | mapped |
| BR | BR-003 | Result maintains float precision | Unit | test_create_addition_floats_AC_004 | Domain | mapped |
| BR | BR-004 | Timestamp in ISO 8601 UTC format | Unit | test_create_addition_sets_timestamp, test_add_sets_timestamp | Domain/Service | mapped |

## Additional Tests (not directly mapped to ACs)

| Test Name | Layer | Purpose |
|-----------|-------|---------|
| test_calculation_creation | Domain | Domain object instantiation |
| test_calculation_is_frozen | Domain | Frozen dataclass enforcement |
| test_validate_success | Domain | Domain validation happy path |
| test_validate_invalid_operation | Domain | Rejects unknown operation |
| test_validate_incorrect_result | Domain | Rejects wrong calculation result |
| test_validate_naive_timestamp | Domain | Rejects timezone-naive datetime |
| test_add_returns_calculation_domain_object | Service | Returns domain object, not DTO |
| test_add_sets_operands | Service | Operand values are preserved |
| test_add_sets_operation | Service | Operation is set to "add" |
| test_add_validates_result | Service | Service validates before returning |
| test_add_with_observe_decorator | Service | Metrics decorator transparency |
| test_add_records_metrics | Service | Metrics recording via @observe |
| test_add_handles_large_numbers | Service | Large number handling |
| test_add_with_validation_error | Service | Validation error propagation |
| test_service_initialization | Service | Service instantiation |
| test_multiple_calculations_with_same_service | Service | Stateless service verification |
| test_lambda_handler_returns_200 | Handler | HTTP 200 for valid request |
| test_lambda_handler_response_is_valid_json | Handler | Valid JSON response body |
| test_lambda_handler_includes_trace_id_in_response | Handler | Trace ID in response headers |
| test_lambda_handler_extracts_trace_id_from_headers | Handler | Trace ID extraction |
| test_lambda_handler_empty_body_returns_400 | Handler | Empty body validation |
| test_handle_add_request_uses_singleton_service | Handler | Singleton service usage |
| test_handle_add_request_large_numbers | Handler | Large number handling |

## Test Coverage Summary
- Total ACs: 12
- Mapped to tests: 12
- Coverage gaps: 0

### Coverage Gaps (Non-AC)
- **TR-001** (API response time < 100ms at p95): No performance/load test exists. This requires an integration or E2E test against a deployed environment. Recommend adding a load test using a tool such as Locust or k6.

## Test Types
- Unit tests: 40
- Integration tests: 0
- E2E tests: 0
- Performance tests: 0

## Test File Locations
- `backend/lambdas/calculator/tests/unit/test_calculator_handler.py` (18 tests)
- `backend/lambdas/calculator/tests/unit/test_calculator_service.py` (13 tests)
- `backend/lambdas/calculator/tests/unit/test_calculation_domain.py` (13 tests - note: includes 4 domain edge-case tests)

## Shift-Left Observations
- All 12 acceptance criteria (AC-001 through AC-012) have corresponding unit tests -- full AC coverage.
- Domain layer tests validate core arithmetic, immutability, and edge cases (infinity, precision).
- Service layer tests verify domain object creation, validation, and metrics.
- Handler layer tests cover HTTP contract, validation errors (400), and internal errors (500).
- **Gap**: No integration tests to verify API Gateway + Lambda wiring or POST /calculator/add routing.
- **Gap**: No E2E tests to confirm deployed endpoint behavior.
- **Gap**: No performance tests for TR-001 (p95 latency < 100ms requirement).
