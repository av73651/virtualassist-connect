# Calculator Multi-Operator Enhancement - Traceability Matrix

**Date**: 2026-03-28

---

## Subtraction Traceability

**Persona**: API Consumer
  -> **User Need**: Perform subtraction of two numbers via HTTP API
    -> **FR-005**: System must accept two numeric values and return the difference
      -> **User Story**: As an API consumer, I want to subtract two numbers so I can get the difference without implementing calculation logic
        -> **AC-013**: Positive integers subtraction
        -> **AC-014**: Negative integers subtraction
        -> **AC-015**: Mixed signs subtraction
        -> **AC-016**: Floating-point subtraction
        -> **AC-017**: Zero operand subtraction

---

## Multiplication Traceability

**Persona**: API Consumer
  -> **User Need**: Perform multiplication of two numbers via HTTP API
    -> **FR-006**: System must accept two numeric values and return the product
      -> **User Story**: As an API consumer, I want to multiply two numbers so I can get the product without implementing calculation logic
        -> **AC-018**: Positive integers multiplication
        -> **AC-019**: Negative integers multiplication
        -> **AC-020**: Mixed signs multiplication
        -> **AC-021**: Floating-point multiplication
        -> **AC-022**: Zero operand multiplication

---

## Division Traceability

**Persona**: API Consumer
  -> **User Need**: Perform division of two numbers via HTTP API
    -> **FR-007**: System must accept two numeric values and return the quotient
      -> **User Story**: As an API consumer, I want to divide two numbers so I can get the quotient without implementing calculation logic
        -> **AC-023**: Positive integers division
        -> **AC-024**: Negative integers division
        -> **AC-025**: Mixed signs division
        -> **AC-026**: Floating-point division
        -> **AC-027**: Zero dividend division

---

## Division by Zero Traceability

**Persona**: API Consumer
  -> **User Need**: Receive clear error when dividing by zero
    -> **FR-008**: System must reject division requests where the divisor is zero
      -> **User Story**: As an API consumer, I want a clear error when I divide by zero so I can handle the error gracefully
        -> **AC-028**: Division by zero returns 400 with DIVISION_BY_ZERO errorCode
        -> **AC-029**: Division by zero error format consistent with existing errors

---

## Response Consistency Traceability

**Persona**: API Consumer
  -> **User Need**: Use consistent API interface across all operations
    -> **FR-009**: All operations must use the same response structure
      -> **AC-030**: Subtraction response format
      -> **AC-031**: Multiplication response format
      -> **AC-032**: Division response format

---

## Validation Traceability

**Persona**: API Consumer
  -> **User Need**: Receive clear error messages for invalid requests
    -> **FR-010**: All new operations must enforce the same input validation
      -> **AC-033**: Missing operand validation
      -> **AC-034**: Non-numeric operand validation
      -> **AC-035**: Null operand validation

---

## Full AC Coverage Matrix

| AC ID  | Requirement | Operation    | Status   |
|--------|-------------|-------------|----------|
| AC-013 | FR-005      | Subtract    | Passed   |
| AC-014 | FR-005      | Subtract    | Passed   |
| AC-015 | FR-005      | Subtract    | Passed   |
| AC-016 | FR-005      | Subtract    | Passed   |
| AC-017 | FR-005      | Subtract    | Passed   |
| AC-018 | FR-006      | Multiply    | Passed   |
| AC-019 | FR-006      | Multiply    | Passed   |
| AC-020 | FR-006      | Multiply    | Passed   |
| AC-021 | FR-006      | Multiply    | Passed   |
| AC-022 | FR-006      | Multiply    | Passed   |
| AC-023 | FR-007      | Divide      | Passed   |
| AC-024 | FR-007      | Divide      | Passed   |
| AC-025 | FR-007      | Divide      | Passed   |
| AC-026 | FR-007      | Divide      | Passed   |
| AC-027 | FR-007      | Divide      | Passed   |
| AC-028 | FR-008      | Divide      | Passed   |
| AC-029 | FR-008      | Divide      | Passed   |
| AC-030 | FR-009      | All New     | Passed   |
| AC-031 | FR-009      | All New     | Passed   |
| AC-032 | FR-009      | All New     | Passed   |
| AC-033 | FR-010      | All New     | Passed   |
| AC-034 | FR-010      | All New     | Passed   |
| AC-035 | FR-010      | All New     | Passed   |
