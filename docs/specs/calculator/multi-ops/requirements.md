# Calculator Multi-Operator Enhancement - Functional Requirements

**Date**: 2026-03-28
**Status**: Draft
**Version**: 1.0

---

## Existing Requirements (Unchanged)

FR-001 through FR-004 from `calculator-requirements.md` remain in effect. The new requirements below extend the calculator with additional operations.

---

## New Functional Requirements

### FR-005: Subtraction Operation
**Description**: System must accept two numeric values and return the difference (a - b)
**Persona**: API Consumer
**Priority**: Must

**Acceptance Criteria**:

**AC-013**: Given two positive integers, when subtraction is requested, then system returns correct difference
- Example: 10 - 3 = 7

**AC-014**: Given two negative integers, when subtraction is requested, then system returns correct difference
- Example: -5 - (-3) = -2

**AC-015**: Given one positive and one negative integer, when subtraction is requested, then system returns correct difference
- Example: 5 - (-3) = 8

**AC-016**: Given two floating-point numbers, when subtraction is requested, then system returns correct difference with decimal precision
- Example: 5.5 - 3.2 = 2.3

**AC-017**: Given zero as one operand, when subtraction is requested, then system returns correct result
- Example: 5 - 0 = 5, 0 - 5 = -5

---

### FR-006: Multiplication Operation
**Description**: System must accept two numeric values and return the product (a * b)
**Persona**: API Consumer
**Priority**: Must

**Acceptance Criteria**:

**AC-018**: Given two positive integers, when multiplication is requested, then system returns correct product
- Example: 5 * 3 = 15

**AC-019**: Given two negative integers, when multiplication is requested, then system returns correct product
- Example: -5 * (-3) = 15

**AC-020**: Given one positive and one negative integer, when multiplication is requested, then system returns correct product
- Example: 5 * (-3) = -15

**AC-021**: Given two floating-point numbers, when multiplication is requested, then system returns correct product with decimal precision
- Example: 2.5 * 4.0 = 10.0

**AC-022**: Given zero as one operand, when multiplication is requested, then system returns zero
- Example: 5 * 0 = 0

---

### FR-007: Division Operation
**Description**: System must accept two numeric values and return the quotient (a / b)
**Persona**: API Consumer
**Priority**: Must

**Acceptance Criteria**:

**AC-023**: Given two positive integers, when division is requested, then system returns correct quotient
- Example: 10 / 2 = 5.0

**AC-024**: Given two negative integers, when division is requested, then system returns correct quotient
- Example: -10 / (-2) = 5.0

**AC-025**: Given one positive and one negative integer, when division is requested, then system returns correct quotient
- Example: 10 / (-2) = -5.0

**AC-026**: Given two floating-point numbers, when division is requested, then system returns correct quotient with decimal precision
- Example: 7.5 / 2.5 = 3.0

**AC-027**: Given zero as the dividend (a=0), when division is requested, then system returns zero
- Example: 0 / 5 = 0.0

---

### FR-008: Division by Zero Handling
**Description**: System must reject division requests where the divisor is zero
**Persona**: API Consumer
**Priority**: Must

**Acceptance Criteria**:

**AC-028**: Given zero as the divisor (b=0), when division is requested, then system returns 400 Bad Request with error code "DIVISION_BY_ZERO"

**AC-029**: Given zero as the divisor, when error is returned, then error response includes errorCode, message, and correlationId consistent with existing error format

---

### FR-009: Consistent Response Format Across Operations
**Description**: All operations must use the same response structure with operation-specific values
**Persona**: API Consumer
**Priority**: Must

**Acceptance Criteria**:

**AC-030**: Given a valid subtraction request, then response includes a, b, operation="subtract", result, and timestamp

**AC-031**: Given a valid multiplication request, then response includes a, b, operation="multiply", result, and timestamp

**AC-032**: Given a valid division request, then response includes a, b, operation="divide", result, and timestamp

---

### FR-010: Request Validation for New Operations
**Description**: All new operations must enforce the same input validation as addition
**Persona**: API Consumer
**Priority**: Must

**Acceptance Criteria**:

**AC-033**: Given missing operand on any new operation, then system returns 400 Bad Request with error details

**AC-034**: Given non-numeric operand on any new operation, then system returns 400 Bad Request with error details

**AC-035**: Given null operand on any new operation, then system returns 400 Bad Request with error details

---

## Summary

**New Functional Requirements**: 6 (FR-005 to FR-010)
**New Acceptance Criteria**: 23 (AC-013 to AC-035)
**Total Functional Requirements**: 10 (FR-001 to FR-010)
**Total Acceptance Criteria**: 35 (AC-001 to AC-035)
