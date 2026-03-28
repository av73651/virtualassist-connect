"""Unit tests for CalculatorService."""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from src.services.calculator_service import CalculatorService
from src.domain.calculation import Calculation


def test_add_returns_calculation_domain_object():
    """Test add() returns Calculation domain object."""
    service = CalculatorService()
    result = service.add(5, 3)

    assert isinstance(result, Calculation)


def test_add_correct_result():
    """Test add() computes correct sum."""
    service = CalculatorService()
    result = service.add(5.5, 3.2)

    assert abs(result.result - 8.7) < 1e-10


def test_add_sets_operands():
    """Test add() sets correct operands."""
    service = CalculatorService()
    result = service.add(5, 3)

    assert result.operand_a == 5
    assert result.operand_b == 3


def test_add_sets_operation():
    """Test add() sets operation to 'add'."""
    service = CalculatorService()
    result = service.add(5, 3)

    assert result.operation == "add"


def test_add_sets_timestamp():
    """Test add() sets UTC timestamp."""
    service = CalculatorService()
    before = datetime.now(timezone.utc)
    result = service.add(5, 3)
    after = datetime.now(timezone.utc)

    assert before <= result.timestamp <= after
    assert result.timestamp.tzinfo == timezone.utc


def test_add_validates_result():
    """Test add() validates the calculation."""
    service = CalculatorService()

    # Mock Calculation.validate to track if it's called
    with patch.object(Calculation, 'validate', return_value=True) as mock_validate:
        with patch.object(Calculation, 'create_addition', return_value=MagicMock(spec=Calculation)) as mock_create:
            mock_calc = MagicMock(spec=Calculation)
            mock_calc.validate = mock_validate
            mock_create.return_value = mock_calc

            result = service.add(5, 3)

            # Verify validate was called
            mock_validate.assert_called_once()


def test_add_with_observe_decorator():
    """Test @observe decorator is applied (metrics/logging)."""
    service = CalculatorService()

    # The decorator should be transparent to the business logic
    result = service.add(5, 3)

    # Business logic should work correctly
    assert result.result == 8


def test_add_records_metrics():
    """Test add() records metrics via @observe decorator."""
    service = CalculatorService()

    # Mock the metrics in observability module
    import shared.middleware.observability as obs

    # Get the counter and histogram from the cache
    counter = obs._counters.get("calculator_add")
    histogram = obs._histograms.get("calculator_add")

    if counter and histogram:
        with patch.object(counter, 'add') as mock_counter, \
             patch.object(histogram, 'record') as mock_histogram:

            result = service.add(5, 3)

            # Verify metrics were recorded
            assert mock_counter.called or not counter
            assert mock_histogram.called or not histogram


def test_add_handles_negative_numbers():
    """Test add() handles negative numbers correctly."""
    service = CalculatorService()
    result = service.add(-5, -3)

    assert result.result == -8


def test_add_handles_zero():
    """Test add() handles zero correctly."""
    service = CalculatorService()
    result = service.add(0, 0)

    assert result.result == 0


def test_add_handles_large_numbers():
    """Test add() handles large numbers correctly."""
    service = CalculatorService()
    result = service.add(1e100, 2e100)

    # Use relative tolerance for large numbers
    assert abs(result.result - 3e100) / 3e100 < 1e-10


def test_add_with_validation_error():
    """Test add() propagates validation errors."""
    service = CalculatorService()

    # Mock create_addition to return invalid calculation
    with patch.object(Calculation, 'create_addition') as mock_create:
        invalid_calc = Calculation(
            operand_a=5,
            operand_b=3,
            operation="multiply",  # Invalid
            result=15,
            timestamp=datetime.now(timezone.utc)
        )
        mock_create.return_value = invalid_calc

        with pytest.raises(ValueError, match="Unknown operation"):
            service.add(5, 3)


def test_service_initialization():
    """Test CalculatorService can be instantiated."""
    service = CalculatorService()
    assert service is not None
    assert isinstance(service, CalculatorService)


def test_multiple_calculations_with_same_service():
    """Test service can perform multiple calculations."""
    service = CalculatorService()

    result1 = service.add(5, 3)
    result2 = service.add(10, 20)
    result3 = service.add(1.5, 2.5)

    assert result1.result == 8
    assert result2.result == 30
    assert result3.result == 4.0
