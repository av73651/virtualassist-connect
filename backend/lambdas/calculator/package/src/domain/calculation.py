"""Calculation Domain Entity.

This module contains the pure domain object for mathematical calculations.
Implements business rules for calculation operations.

Domain layer has zero external dependencies - only Python standard library.
"""

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Calculation:
    """Pure domain object representing a mathematical calculation.

    Attributes:
        operand_a: First numeric operand
        operand_b: Second numeric operand
        operation: Type of operation performed ("add")
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

        Example:
            >>> calc = Calculation.create_addition(5.5, 3.2)
            >>> calc.result
            8.7
        """
        result = a + b
        return cls(
            operand_a=a,
            operand_b=b,
            operation="add",
            result=result,
            timestamp=datetime.now(timezone.utc)
        )

    def validate(self) -> bool:
        """Validate calculation consistency.

        Business Rules:
        - Operation must be "add"
        - Result must match expected calculation
        - Timestamp must be timezone-aware UTC

        Returns:
            bool: True if valid

        Raises:
            ValueError: If validation fails
        """
        # Validate operation type
        if self.operation != "add":
            raise ValueError(f"Unknown operation: {self.operation}")

        # Validate result correctness (with float comparison tolerance)
        expected = self.operand_a + self.operand_b
        tolerance = 1e-10
        if abs(self.result - expected) > tolerance:
            raise ValueError(
                f"Calculation result is incorrect. Expected {expected}, got {self.result}"
            )

        # Validate timestamp is timezone-aware
        if self.timestamp.tzinfo is None:
            raise ValueError("Timestamp must be timezone-aware")

        return True
