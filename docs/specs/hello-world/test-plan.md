# Test Plan: hello-world

## Source
docs/specs/hello-world/hello-world-requirements.md

## Traceability Matrix

| Source | ID | Description | Test Type | Test Name | Layer | Status |
|--------|----|-------------|-----------|-----------|-------|--------|
| AC | AC-001 | GET /hello returns HTTP 200 status code | Unit | test_lambda_handler_returns_200_AC_001 | Handler | mapped |
| AC | AC-002 | Response body is valid JSON format | Unit | test_lambda_handler_response_is_valid_json_AC_002 | Handler | mapped |
| AC | AC-003 | Response contains "message" field with value "Hello, World!" | Unit | test_handle_hello_request_contains_message_AC_003 | Handler | mapped |
| AC | AC-004 | Response includes "timestamp" field with current ISO 8601 timestamp | Unit | test_handle_hello_request_contains_timestamp_AC_004 | Handler | mapped |
| AC | AC-005 | Response time is under 200ms for 95% of requests | Performance | -- | -- | gap |
| BR | BR-001 | Message text must be exactly "Hello, World!", timestamp in ISO 8601 UTC | Unit | test_hello_message_business_rule_br001 | Domain | mapped |
| BR | BR-001 | Timestamp is UTC timezone | Unit | test_get_hello_message_timestamp_is_utc | Service | mapped |
| BR | BR-002 | Same request always returns same message; only timestamp changes | Unit | test_get_hello_message_has_correct_message | Service | mapped |
| NFR | NFR-003 | Structured JSON logging | Unit | test_get_hello_message_logs_correctly | Service | mapped |
| NFR | NFR-003 | Metrics collected (invocation count, duration) | Unit | test_get_hello_message_records_metrics | Service | mapped |
| NFR | NFR-003 | Trace IDs in responses | Unit | test_lambda_handler_includes_trace_id_in_response | Handler | mapped |
| NFR | NFR-003 | Trace ID extraction from headers | Unit | test_lambda_handler_extracts_trace_id_from_headers | Handler | mapped |
| NFR | NFR-004 | Error responses do not expose internals | Unit | test_lambda_handler_with_exception_returns_500 | Handler | mapped |
| TECH | TECH-002 | Content-Type application/json | Unit | test_lambda_handler_content_type_header | Handler | mapped |

## Additional Tests (not directly mapped to ACs)

| Test Name | Layer | Purpose |
|-----------|-------|---------|
| test_hello_message_creation | Domain | Domain object instantiation |
| test_hello_message_is_immutable | Domain | Frozen dataclass enforcement |
| test_hello_message_factory_method | Domain | Factory method with current timestamp |
| test_hello_message_validate_success | Domain | Domain validation happy path |
| test_hello_message_validate_empty_message | Domain | Rejects empty message |
| test_hello_message_validate_whitespace_message | Domain | Rejects whitespace-only message |
| test_hello_message_validate_none_timestamp | Domain | Rejects None timestamp |
| test_hello_message_timezone_aware | Domain | Ensures timezone-aware datetime |
| test_get_hello_message_returns_domain_object | Service | Returns domain object, not DTO |
| test_get_hello_message_has_datetime_timestamp | Service | Timestamp is datetime type |
| test_get_hello_message_with_fixed_datetime | Service | Deterministic timestamp testing |
| test_get_hello_message_validates_domain_object | Service | Service validates before returning |
| test_get_hello_message_records_error_metrics | Service | Error metrics recording |

## Test Coverage Summary
- Total ACs: 5
- Mapped to tests: 4
- Coverage gaps: 1

### Coverage Gaps
- **AC-005** (Response time < 200ms at p95): No performance/load test exists. This requires an integration or E2E test against a deployed environment, not a unit test. Recommend adding a load test using a tool such as Locust or k6.

## Test Types
- Unit tests: 22
- Integration tests: 0
- E2E tests: 0
- Performance tests: 0

## Test File Locations
- `backend/lambdas/hello-world/tests/unit/test_hello_handler.py` (8 tests)
- `backend/lambdas/hello-world/tests/unit/test_hello_service.py` (9 tests)
- `backend/lambdas/hello-world/tests/unit/test_hello_message_domain.py` (9 tests - note: file name referenced from glob; 4 additional domain tests not in the 9 listed)

## Shift-Left Observations
- Domain layer tests cover immutability, validation, and business rules -- good shift-left practice.
- Service layer tests verify metrics, logging, and domain object usage.
- Handler layer tests confirm HTTP contract (status codes, headers, JSON format).
- **Gap**: No integration tests to verify API Gateway + Lambda wiring.
- **Gap**: No E2E tests to confirm deployed endpoint behavior.
- **Gap**: No performance tests for AC-005 (p95 latency requirement).
