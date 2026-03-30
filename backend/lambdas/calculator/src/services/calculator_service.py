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
        """
        calculation = Calculation.create_addition(a, b)
        calculation.validate()
        return calculation

    @observe(operation="subtract_numbers", metric_prefix="calculator_subtract")
    def subtract(self, a: float, b: float) -> Calculation:
        """Perform subtraction of two numbers (FR-005, BR-006).

        Returns domain object with operation='subtract', result = a - b.
        """
        calculation = Calculation.create_subtraction(a, b)
        calculation.validate()
        return calculation

    @observe(operation="multiply_numbers", metric_prefix="calculator_multiply")
    def multiply(self, a: float, b: float) -> Calculation:
        """Perform multiplication of two numbers (FR-006).

        Returns domain object with operation='multiply', result = a * b.
        """
        calculation = Calculation.create_multiplication(a, b)
        calculation.validate()
        return calculation

    @observe(operation="divide_numbers", metric_prefix="calculator_divide")
    def divide(self, a: float, b: float) -> Calculation:
        """Perform division of two numbers (FR-007, BR-005, BR-007).

        DivisionByZeroError propagation:
        Domain (raises) -> @observe (logs/metrics/traces) -> Handler (no catch) -> Middleware (HTTP 400)
        """
        calculation = Calculation.create_division(a, b)
        calculation.validate()
        return calculation
