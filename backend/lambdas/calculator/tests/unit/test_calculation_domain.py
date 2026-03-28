"""Unit tests for Calculation domain entity."""

import pytest
from datetime import datetime, timezone
from src.domain.calculation import Calculation, DivisionByZeroError


def test_calculation_creation():
    """Test Calculation can be created with all fields."""
    timestamp = datetime.now(timezone.utc)
    calc = Calculation(
        operand_a=5.5,
        operand_b=3.2,
        operation="add",
        result=8.7,
        timestamp=timestamp
    )

    assert calc.operand_a == 5.5
    assert calc.operand_b == 3.2
    assert calc.operation == "add"
    assert calc.result == 8.7
    assert calc.timestamp == timestamp


def test_calculation_is_frozen():
    """Test Calculation is immutable (frozen dataclass)."""
    calc = Calculation.create_addition(5, 3)

    with pytest.raises(AttributeError):
        calc.result = 100  # Should fail - frozen dataclass


def test_create_addition_positive_integers_AC_001():
    """Test addition with two positive integers (AC-001)."""
    calc = Calculation.create_addition(5, 3)

    assert calc.operand_a == 5
    assert calc.operand_b == 3
    assert calc.operation == "add"
    assert calc.result == 8


def test_create_addition_negative_integers_AC_002():
    """Test addition with two negative integers (AC-002)."""
    calc = Calculation.create_addition(-5, -3)

    assert calc.operand_a == -5
    assert calc.operand_b == -3
    assert calc.operation == "add"
    assert calc.result == -8


def test_create_addition_mixed_signs_AC_003():
    """Test addition with one positive and one negative (AC-003)."""
    calc = Calculation.create_addition(5, -3)

    assert calc.operand_a == 5
    assert calc.operand_b == -3
    assert calc.operation == "add"
    assert calc.result == 2


def test_create_addition_floats_AC_004():
    """Test addition with floating-point numbers (AC-004)."""
    calc = Calculation.create_addition(5.5, 3.2)

    assert calc.operand_a == 5.5
    assert calc.operand_b == 3.2
    assert calc.operation == "add"
    assert abs(calc.result - 8.7) < 1e-10  # Float comparison tolerance


def test_create_addition_zero_operand_AC_005():
    """Test addition with zero as one operand (AC-005)."""
    calc = Calculation.create_addition(0, 5)

    assert calc.operand_a == 0
    assert calc.operand_b == 5
    assert calc.operation == "add"
    assert calc.result == 5


def test_create_addition_sets_timestamp():
    """Test factory method sets current UTC timestamp."""
    before = datetime.now(timezone.utc)
    calc = Calculation.create_addition(1, 2)
    after = datetime.now(timezone.utc)

    assert before <= calc.timestamp <= after
    assert calc.timestamp.tzinfo == timezone.utc


def test_validate_success():
    """Test validation passes for valid calculation."""
    calc = Calculation.create_addition(5, 3)
    assert calc.validate() is True


def test_validate_invalid_operation():
    """Test validation fails for unknown operation."""
    calc = Calculation(
        operand_a=5,
        operand_b=3,
        operation="modulo",  # Invalid - not in VALID_OPERATIONS
        result=2,
        timestamp=datetime.now(timezone.utc)
    )

    with pytest.raises(ValueError, match="Unknown operation: modulo"):
        calc.validate()


def test_validate_incorrect_result():
    """Test validation fails for incorrect calculation."""
    calc = Calculation(
        operand_a=5,
        operand_b=3,
        operation="add",
        result=100,  # Wrong result
        timestamp=datetime.now(timezone.utc)
    )

    with pytest.raises(ValueError, match="Calculation result is incorrect"):
        calc.validate()


def test_validate_naive_timestamp():
    """Test validation fails for timezone-naive timestamp."""
    calc = Calculation(
        operand_a=5,
        operand_b=3,
        operation="add",
        result=8,
        timestamp=datetime.now()  # Naive datetime (no timezone)
    )

    with pytest.raises(ValueError, match="Timestamp must be timezone-aware"):
        calc.validate()


def test_large_numbers():
    """Test addition with large numbers."""
    calc = Calculation.create_addition(1e100, 2e100)

    # Use relative tolerance for large numbers
    assert abs(calc.result - 3e100) / 3e100 < 1e-10


def test_very_small_numbers():
    """Test addition with very small numbers."""
    calc = Calculation.create_addition(1e-100, 2e-100)

    assert abs(calc.result - 3e-100) < 1e-110


def test_infinity_handling():
    """Test addition resulting in infinity (overflow)."""
    calc = Calculation.create_addition(1e308, 1e308)

    # Python returns inf for overflow
    assert calc.result == float('inf')


def test_negative_infinity_handling():
    """Test addition resulting in negative infinity."""
    calc = Calculation.create_addition(-1e308, -1e308)

    assert calc.result == float('-inf')


# --- Subtraction Tests (FR-005) ---


def test_create_subtraction_positive_integers_AC_013():
    """Test subtraction with two positive integers (AC-013)."""
    calc = Calculation.create_subtraction(10, 3)

    assert calc.operand_a == 10
    assert calc.operand_b == 3
    assert calc.operation == "subtract"
    assert calc.result == 7


def test_create_subtraction_negative_integers_AC_014():
    """Test subtraction with two negative integers (AC-014)."""
    calc = Calculation.create_subtraction(-5, -3)

    assert calc.result == -2


def test_create_subtraction_mixed_signs_AC_015():
    """Test subtraction with mixed signs (AC-015)."""
    calc = Calculation.create_subtraction(5, -3)

    assert calc.result == 8


def test_create_subtraction_floats_AC_016():
    """Test subtraction with floating-point numbers (AC-016)."""
    calc = Calculation.create_subtraction(5.5, 3.2)

    assert abs(calc.result - 2.3) < 1e-10


def test_create_subtraction_zero_operand_AC_017():
    """Test subtraction with zero operand (AC-017)."""
    calc1 = Calculation.create_subtraction(5, 0)
    assert calc1.result == 5

    calc2 = Calculation.create_subtraction(0, 5)
    assert calc2.result == -5


def test_create_subtraction_sets_timestamp():
    """Test subtraction factory sets UTC timestamp."""
    before = datetime.now(timezone.utc)
    calc = Calculation.create_subtraction(10, 3)
    after = datetime.now(timezone.utc)

    assert before <= calc.timestamp <= after


def test_validate_subtraction_success():
    """Test validation passes for valid subtraction."""
    calc = Calculation.create_subtraction(10, 3)
    assert calc.validate() is True


# --- Multiplication Tests (FR-006) ---


def test_create_multiplication_positive_integers_AC_018():
    """Test multiplication with two positive integers (AC-018)."""
    calc = Calculation.create_multiplication(5, 3)

    assert calc.operand_a == 5
    assert calc.operand_b == 3
    assert calc.operation == "multiply"
    assert calc.result == 15


def test_create_multiplication_negative_integers_AC_019():
    """Test multiplication with two negative integers (AC-019)."""
    calc = Calculation.create_multiplication(-5, -3)

    assert calc.result == 15


def test_create_multiplication_mixed_signs_AC_020():
    """Test multiplication with mixed signs (AC-020)."""
    calc = Calculation.create_multiplication(5, -3)

    assert calc.result == -15


def test_create_multiplication_floats_AC_021():
    """Test multiplication with floating-point numbers (AC-021)."""
    calc = Calculation.create_multiplication(2.5, 4.0)

    assert abs(calc.result - 10.0) < 1e-10


def test_create_multiplication_zero_operand_AC_022():
    """Test multiplication with zero operand (AC-022)."""
    calc = Calculation.create_multiplication(5, 0)

    assert calc.result == 0


def test_validate_multiplication_success():
    """Test validation passes for valid multiplication."""
    calc = Calculation.create_multiplication(5, 3)
    assert calc.validate() is True


def test_multiplication_overflow():
    """Test multiplication resulting in infinity (overflow)."""
    calc = Calculation.create_multiplication(1e308, 2)

    assert calc.result == float('inf')


# --- Division Tests (FR-007) ---


def test_create_division_positive_integers_AC_023():
    """Test division with two positive integers (AC-023)."""
    calc = Calculation.create_division(10, 2)

    assert calc.operand_a == 10
    assert calc.operand_b == 2
    assert calc.operation == "divide"
    assert calc.result == 5.0


def test_create_division_negative_integers_AC_024():
    """Test division with two negative integers (AC-024)."""
    calc = Calculation.create_division(-10, -2)

    assert calc.result == 5.0


def test_create_division_mixed_signs_AC_025():
    """Test division with mixed signs (AC-025)."""
    calc = Calculation.create_division(10, -2)

    assert calc.result == -5.0


def test_create_division_floats_AC_026():
    """Test division with floating-point numbers (AC-026)."""
    calc = Calculation.create_division(7.5, 2.5)

    assert abs(calc.result - 3.0) < 1e-10


def test_create_division_zero_dividend_AC_027():
    """Test division with zero dividend (AC-027)."""
    calc = Calculation.create_division(0, 5)

    assert calc.result == 0.0


def test_create_division_true_division():
    """Test division uses true division, not integer division (TR-015)."""
    calc = Calculation.create_division(7, 2)

    assert calc.result == 3.5  # Not 3


def test_validate_division_success():
    """Test validation passes for valid division."""
    calc = Calculation.create_division(10, 2)
    assert calc.validate() is True


# --- Division by Zero Tests (FR-008) ---


def test_create_division_by_zero_raises_error_AC_028():
    """Test division by zero raises DivisionByZeroError (AC-028)."""
    with pytest.raises(DivisionByZeroError, match="Division by zero is not allowed"):
        Calculation.create_division(10, 0)


def test_division_by_zero_error_is_business_rule_error():
    """Test DivisionByZeroError inherits from BusinessRuleError."""
    from shared.exceptions.business_rule_error import BusinessRuleError

    with pytest.raises(BusinessRuleError):
        Calculation.create_division(10, 0)


def test_division_by_zero_error_code():
    """Test DivisionByZeroError has correct error_code."""
    with pytest.raises(DivisionByZeroError) as exc_info:
        Calculation.create_division(10, 0)

    assert exc_info.value.error_code == "DIVISION_BY_ZERO"
