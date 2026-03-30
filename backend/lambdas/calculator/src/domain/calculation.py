"""Calculation Domain Entity.

This module contains the pure domain object for mathematical calculations.
Implements business rules for calculation operations.

Domain layer depends only on Python standard library and shared base exceptions.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from shared.exceptions.business_rule_error import BusinessRuleError


class DivisionByZeroError(BusinessRuleError):
    """Raised when division by zero is attempted.

    Business Rule BR-005: Division by zero must be rejected.

    AOP Propagation Path:
        Domain (raises) -> @observe (logs/metrics/traces) -> Handler (no catch) -> @api_gateway_handler (HTTP 400)
    """

    def __init__(self, message: str = "Division by zero is not allowed") -> None:
        super().__init__(message, error_code="DIVISION_BY_ZERO")


VALID_OPERATIONS = {"add", "subtract", "multiply", "divide"}

_OPERATION_COMPUTE = {
    "add": lambda a, b: a + b,
    "subtract": lambda a, b: a - b,
    "multiply": lambda a, b: a * b,
    "divide": lambda a, b: a / b,
}


@dataclass(frozen=True)
class Calculation:
    """Pure domain object representing a mathematical calculation.

    Attributes:
        operand_a: First numeric operand
        operand_b: Second numeric operand
        operation: Type of operation performed ("add", "subtract", "multiply", "divide")
        result: Calculated result
        timestamp: When calculation was performed (UTC)
    """

    operand_a: float
    operand_b: float
    operation: str
    result: float
    timestamp: datetime

    @classmethod
    def create_addition(cls, a: float, b: float) -> "Calculation":
        """Factory method to create addition calculation.

        Business Rules:
        - BR-001: Both operands must be numeric (enforced by type hints)
        - BR-003: Result maintains Python float precision

        Args:
            a: First operand
            b: Second operand

        Returns:
            Calculation: Domain object with computed result
        """
        return cls(
            operand_a=a,
            operand_b=b,
            operation="add",
            result=a + b,
            timestamp=datetime.now(timezone.utc)
        )

    @classmethod
    def create_subtraction(cls, a: float, b: float) -> "Calculation":
        """Factory method to create subtraction calculation (FR-005, BR-006).

        Args:
            a: First operand (minuend)
            b: Second operand (subtrahend)

        Returns:
            Calculation: Domain object with result = a - b
        """
        return cls(
            operand_a=a,
            operand_b=b,
            operation="subtract",
            result=a - b,
            timestamp=datetime.now(timezone.utc)
        )

    @classmethod
    def create_multiplication(cls, a: float, b: float) -> "Calculation":
        """Factory method to create multiplication calculation (FR-006).

        Args:
            a: First operand
            b: Second operand

        Returns:
            Calculation: Domain object with result = a * b
        """
        return cls(
            operand_a=a,
            operand_b=b,
            operation="multiply",
            result=a * b,
            timestamp=datetime.now(timezone.utc)
        )

    @classmethod
    def create_division(cls, a: float, b: float) -> "Calculation":
        """Factory method to create division calculation (FR-007, BR-005, BR-007).

        Uses Python true division (/) returning float (TR-015).

        Args:
            a: First operand (dividend)
            b: Second operand (divisor)

        Returns:
            Calculation: Domain object with result = a / b

        Raises:
            DivisionByZeroError: If b is zero (BR-005)
        """
        if b == 0:
            raise DivisionByZeroError()
        return cls(
            operand_a=a,
            operand_b=b,
            operation="divide",
            result=a / b,
            timestamp=datetime.now(timezone.utc)
        )

    def validate(self) -> bool:
        """Validate calculation consistency.

        Business Rules:
        - Operation must be one of: add, subtract, multiply, divide
        - Result must match expected calculation
        - Timestamp must be timezone-aware UTC

        Returns:
            bool: True if valid

        Raises:
            ValueError: If validation fails
        """
        if self.operation not in VALID_OPERATIONS:
            raise ValueError(f"Unknown operation: {self.operation}")

        expected = _OPERATION_COMPUTE[self.operation](self.operand_a, self.operand_b)
        tolerance = 1e-10
        if abs(self.result - expected) > tolerance:
            raise ValueError(
                f"Calculation result is incorrect. Expected {expected}, got {self.result}"
            )

        if self.timestamp.tzinfo is None:
            raise ValueError("Timestamp must be timezone-aware")

        return True
