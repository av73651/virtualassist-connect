"""Calculator Service.

This module contains business logic for calculator operations.
Implements business rules for mathematical calculations.

Service layer returns domain objects only - no DTOs.
All observability concerns (tracing, metrics, logging) handled by @observe decorator.
"""

from src.domain.calculation import Calculation
from shared.middleware.observability import observe


class CalculatorService:
    """Service for calculator operations.

    Implements business logic for mathematical calculations.
    Returns domain objects only - DTOs are handled in the handler layer.
    All cross-cutting concerns handled by observability middleware.
    """

    def __init__(self) -> None:
        """Initialize CalculatorService."""
        pass

    @observe(operation="add_numbers", metric_prefix="calculator_add")
    def add(self, a: float, b: float) -> Calculation:
        """Perform addition of two numbers.

        Business Rules:
        - BR-001: Both operands must be numeric (enforced by type hints)
        - BR-003: Result maintains float precision

        Observability:
        - Tracing, metrics, and logging handled by @observe decorator
        - Creates OpenTelemetry span with status
        - Records counter + histogram metrics
        - Logs entry/exit with structured context

        Args:
            a: First operand
            b: Second operand

        Returns:
            Calculation: Domain object with result

        Example:
            >>> service = CalculatorService()
            >>> calc = service.add(5.5, 3.2)
            >>> calc.result
            8.7
        """
        # Pure business logic - no observability boilerplate
        calculation = Calculation.create_addition(a, b)
        calculation.validate()
        return calculation
