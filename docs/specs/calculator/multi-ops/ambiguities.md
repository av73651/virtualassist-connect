# Calculator Multi-Operator Enhancement - Ambiguities

**Date**: 2026-03-28

---

### AMBIGUITY DETECTED: Integer Division vs True Division
**Requirement**: FR-007 (Division Operation)
**Issue**: Should division of two integers (e.g., 7 / 2) return an integer (3) or float (3.5)?
**Suggested Clarification**: Specify division behavior explicitly
**Resolution**: Use Python's true division (/) returning float. Added as TR-015. Example: 7 / 2 = 3.5

---

### AMBIGUITY DETECTED: Division by Zero Error Code
**Requirement**: FR-008 (Division by Zero Handling)
**Issue**: Should division by zero return HTTP 400 (client error - invalid input) or HTTP 422 (unprocessable entity)?
**Suggested Clarification**: Specify HTTP status code for division by zero
**Resolution**: Use HTTP 400 Bad Request, consistent with existing validation errors. The divisor being zero is a form of invalid input.

---

### AMBIGUITY DETECTED: Multiplication/Subtraction Overflow
**Requirement**: FR-005, FR-006
**Issue**: Requirements don't specify behavior when subtraction or multiplication results exceed float range
**Suggested Clarification**: Define overflow behavior per operation
**Resolution**: Apply same assumption as addition (BR-008) - use Python's native inf/-inf behavior per IEEE 754

---

### AMBIGUITY DETECTED: Negative Zero
**Requirement**: FR-005 (Subtraction)
**Issue**: Subtraction can produce -0.0 in IEEE 754 (e.g., 0.0 - 0.0 = 0.0, but -0.0 + 0.0 edge cases exist). Should -0.0 be normalized to 0.0?
**Suggested Clarification**: Specify negative zero handling
**Resolution**: Use Python's native behavior. -0.0 == 0.0 in Python comparisons, so no special handling needed.

---

### AMBIGUITY DETECTED: API Routing Pattern
**Requirement**: TR-009, TR-010, TR-011
**Issue**: Should each operation be a separate Lambda handler function, or should one handler route based on the path?
**Suggested Clarification**: This is an implementation/design decision, not a requirements decision
**Resolution**: Deferred to Phase 2 (Design). The requirement only specifies the endpoint paths.

---

## Summary

**Ambiguities Detected**: 5
**Resolved**: 5 (all resolved with assumptions documented)
**Unresolved**: 0
