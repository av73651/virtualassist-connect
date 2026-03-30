# Calculator Multi-Operator Enhancement - Glossary

**Date**: 2026-03-28

---

**Term**: Operand
**Definition**: A numeric value (integer or float) provided as input to a calculation. Each operation requires exactly two operands: "a" and "b".

**Term**: Operation
**Definition**: The mathematical function applied to two operands. Supported operations: add, subtract, multiply, divide.

**Term**: Division by Zero
**Definition**: An error condition where the divisor (operand "b") is zero. This is mathematically undefined and must return an error response.

**Term**: IEEE 754
**Definition**: The standard for floating-point arithmetic that defines how decimal numbers are represented and calculated in computing. Python's `float` type uses IEEE 754 double precision (64-bit).

**Term**: Overflow
**Definition**: When a calculation result exceeds the maximum representable float value (~1.8e308). Python returns `inf` or `-inf` in these cases.

**Term**: AC
**Definition**: Acceptance Criteria - conditions that define when a requirement is satisfied.

**Term**: Correlation ID
**Definition**: A unique trace identifier (X-Trace-Id) included in API responses for request tracking and debugging.
