# Calculator Multi-Operator Enhancement - Business Rules

**Date**: 2026-03-28

---

## Existing Business Rules (Unchanged)

BR-001 through BR-004 from `calculator-requirements.md` remain in effect for all operations.

---

## New Business Rules

### BR-005: Division by Zero Prohibited
**Description**: Division by zero must be rejected as an invalid operation
**Conditions**: Division operation requested with b = 0
**Expected Outcome**: Return 400 Bad Request with errorCode "DIVISION_BY_ZERO" and descriptive message

### BR-006: Subtraction Order
**Description**: Subtraction must compute a - b (first operand minus second operand)
**Conditions**: Subtraction operation requested
**Expected Outcome**: Result equals a minus b

### BR-007: Division Order
**Description**: Division must compute a / b (first operand divided by second operand)
**Conditions**: Division operation requested
**Expected Outcome**: Result equals a divided by b using true division (float result)

### BR-008: Multiplication Overflow
**Description**: When multiplication result exceeds float range, Python native inf/-inf behavior applies
**Conditions**: Multiplication of very large numbers
**Expected Outcome**: Return inf or -inf per IEEE 754

---

## Summary

**New Business Rules**: 4 (BR-005 to BR-008)
**Total Business Rules**: 8 (BR-001 to BR-008)
