"""Unit tests for Calculation domain entity."""

import pytest
from datetime import datetime, timezone
from src.domain.calculation import Calculation


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
        operation="multiply",  # Invalid
        result=15,
        timestamp=datetime.now(timezone.utc)
    )

    with pytest.raises(ValueError, match="Unknown operation: multiply"):
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
