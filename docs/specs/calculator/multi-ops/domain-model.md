# Calculator Multi-Operator Enhancement - Domain Model

**Date**: 2026-03-28

---

## Updated Domain Entity

### Calculation (Enhanced)
**Description**: Represents a mathematical calculation operation. Extended to support multiple operation types.
**Key Attributes**:
- operand_a: First numeric value (float)
- operand_b: Second numeric value (float)
- operation: Type of calculation ("add", "subtract", "multiply", "divide")
- result: Calculated result (float)
- timestamp: When calculation was performed (UTC datetime)

### Supported Operations
| Operation   | Symbol | Formula    | Special Rules                    |
|-------------|--------|------------|----------------------------------|
| add         | +      | a + b      | None                             |
| subtract    | -      | a - b      | None                             |
| multiply    | *      | a * b      | None                             |
| divide      | /      | a / b      | b must not be zero               |

### Entity Relationships
- Calculation is the sole domain entity
- Each Calculation represents exactly one operation on two operands
- The operation field determines which mathematical function was applied
- Factory methods encapsulate creation logic per operation type
