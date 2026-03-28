"""Unit tests for Calculator request and response DTOs."""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError
from src.dto.request import CalculatorRequest
from src.dto.response import CalculatorResponse, ErrorResponse
from src.domain.calculation import Calculation


# ============================================================================
# CalculatorRequest DTO Tests
# ============================================================================

class TestCalculatorRequest:
    """Tests for CalculatorRequest DTO validation."""

    def test_valid_request_with_floats(self):
        """Test CalculatorRequest accepts valid float operands (AC-001)."""
        # Arrange
        data = {"a": 5.5, "b": 3.2}

        # Act
        request = CalculatorRequest(**data)

        # Assert
        assert request.a == 5.5
        assert request.b == 3.2

    def test_valid_request_with_integers(self):
        """Test CalculatorRequest accepts integer operands coerced to float."""
        # Arrange
        data = {"a": 10, "b": -3}

        # Act
        request = CalculatorRequest(**data)

        # Assert
        assert request.a == 10.0
        assert request.b == -3.0

    def test_valid_request_with_zero(self):
        """Test CalculatorRequest accepts zero values."""
        # Arrange
        data = {"a": 0, "b": 0}

        # Act
        request = CalculatorRequest(**data)

        # Assert
        assert request.a == 0.0
        assert request.b == 0.0

    def test_valid_request_with_negative_numbers(self):
        """Test CalculatorRequest accepts negative operands."""
        # Arrange
        data = {"a": -100.5, "b": -200.3}

        # Act
        request = CalculatorRequest(**data)

        # Assert
        assert request.a == -100.5
        assert request.b == -200.3

    def test_missing_field_a_raises_validation_error(self):
        """Test CalculatorRequest rejects missing 'a' field (AC-002)."""
        # Arrange
        data = {"b": 3.2}

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            CalculatorRequest(**data)
        assert "a" in str(exc_info.value)

    def test_missing_field_b_raises_validation_error(self):
        """Test CalculatorRequest rejects missing 'b' field (AC-002)."""
        # Arrange
        data = {"a": 5.5}

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            CalculatorRequest(**data)
        assert "b" in str(exc_info.value)

    def test_missing_both_fields_raises_validation_error(self):
        """Test CalculatorRequest rejects empty body (AC-002)."""
        # Arrange
        data = {}

        # Act & Assert
        with pytest.raises(ValidationError):
            CalculatorRequest(**data)

    def test_non_numeric_field_a_raises_validation_error(self):
        """Test CalculatorRequest rejects non-numeric 'a' value (AC-003)."""
        # Arrange
        data = {"a": "not_a_number", "b": 3.2}

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            CalculatorRequest(**data)
        assert "a" in str(exc_info.value)

    def test_non_numeric_field_b_raises_validation_error(self):
        """Test CalculatorRequest rejects non-numeric 'b' value (AC-003)."""
        # Arrange
        data = {"a": 5.5, "b": "abc"}

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            CalculatorRequest(**data)
        assert "b" in str(exc_info.value)

    def test_null_field_a_raises_validation_error(self):
        """Test CalculatorRequest rejects null 'a' value."""
        # Arrange
        data = {"a": None, "b": 3.2}

        # Act & Assert
        with pytest.raises(ValidationError):
            CalculatorRequest(**data)

    def test_null_field_b_raises_validation_error(self):
        """Test CalculatorRequest rejects null 'b' value."""
        # Arrange
        data = {"a": 5.5, "b": None}

        # Act & Assert
        with pytest.raises(ValidationError):
            CalculatorRequest(**data)


# ============================================================================
# CalculatorResponse DTO Tests
# ============================================================================

class TestCalculatorResponse:
    """Tests for CalculatorResponse DTO creation and serialization."""

    def test_calculator_response_creation(self):
        """Test CalculatorResponse DTO creation with direct instantiation."""
        # Arrange & Act
        response = CalculatorResponse(
            a=5.5,
            b=3.2,
            operation="add",
            result=8.7,
            timestamp="2026-03-28T10:00:00.000000Z"
        )

        # Assert
        assert response.a == 5.5
        assert response.b == 3.2
        assert response.operation == "add"
        assert response.result == 8.7
        assert response.timestamp == "2026-03-28T10:00:00.000000Z"

    def test_calculator_response_from_calculation_factory(self):
        """Test CalculatorResponse.from_calculation factory method (AC-004)."""
        # Arrange
        calc = Calculation(
            operand_a=5.5,
            operand_b=3.2,
            operation="add",
            result=8.7,
            timestamp=datetime(2026, 3, 28, 10, 0, 0, tzinfo=timezone.utc)
        )

        # Act
        response = CalculatorResponse.from_calculation(calc)

        # Assert
        assert response.a == 5.5
        assert response.b == 3.2
        assert response.operation == "add"
        assert response.result == 8.7
        assert response.timestamp == "2026-03-28T10:00:00.000000Z"

    def test_calculator_response_from_calculation_maps_operand_names(self):
        """Test from_calculation maps operand_a/operand_b to a/b."""
        # Arrange
        calc = Calculation(
            operand_a=100.0,
            operand_b=-50.0,
            operation="add",
            result=50.0,
            timestamp=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        )

        # Act
        response = CalculatorResponse.from_calculation(calc)

        # Assert
        assert response.a == calc.operand_a
        assert response.b == calc.operand_b

    def test_calculator_response_to_dict(self):
        """Test CalculatorResponse to_dict() serialization."""
        # Arrange
        response = CalculatorResponse(
            a=5.5,
            b=3.2,
            operation="add",
            result=8.7,
            timestamp="2026-03-28T10:00:00.000000Z"
        )

        # Act
        result = response.to_dict()

        # Assert
        assert result == {
            "a": 5.5,
            "b": 3.2,
            "operation": "add",
            "result": 8.7,
            "timestamp": "2026-03-28T10:00:00.000000Z"
        }

    def test_calculator_response_to_dict_is_json_serializable(self):
        """Test to_dict() output can be serialized to JSON."""
        import json

        # Arrange
        response = CalculatorResponse(
            a=5.5,
            b=3.2,
            operation="add",
            result=8.7,
            timestamp="2026-03-28T10:00:00.000000Z"
        )

        # Act
        result = json.dumps(response.to_dict())

        # Assert
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert parsed["result"] == 8.7

    def test_calculator_response_missing_field_raises_error(self):
        """Test Pydantic validation rejects missing fields."""
        # Act & Assert
        with pytest.raises(ValidationError):
            CalculatorResponse(a=5.5, b=3.2, operation="add")  # Missing result, timestamp


# ============================================================================
# ErrorResponse DTO Tests
# ============================================================================

class TestErrorResponse:
    """Tests for ErrorResponse DTO creation and serialization."""

    def test_error_response_creation(self):
        """Test ErrorResponse DTO creation with direct instantiation."""
        # Arrange & Act
        error = ErrorResponse(
            errorCode="TEST_ERROR",
            message="Test message",
            correlationId="trace-123",
            timestamp="2026-03-28T10:00:00.000000Z"
        )

        # Assert
        assert error.errorCode == "TEST_ERROR"
        assert error.message == "Test message"
        assert error.correlationId == "trace-123"
        assert error.timestamp == "2026-03-28T10:00:00.000000Z"

    def test_error_response_create_internal_error(self):
        """Test ErrorResponse.create_internal_error factory method."""
        # Arrange
        correlation_id = "trace-abc-123"

        # Act
        error = ErrorResponse.create_internal_error(correlation_id)

        # Assert
        assert error.errorCode == "INTERNAL_ERROR"
        assert error.message == "An internal error occurred"
        assert error.correlationId == "trace-abc-123"
        assert len(error.timestamp) > 0
        assert "T" in error.timestamp
        assert error.timestamp.endswith("Z")

    def test_error_response_create_validation_error(self):
        """Test ErrorResponse.create_validation_error factory method (AC-003)."""
        # Arrange
        correlation_id = "trace-val-456"
        details = "field 'a' is required"

        # Act
        error = ErrorResponse.create_validation_error(correlation_id, details)

        # Assert
        assert error.errorCode == "VALIDATION_ERROR"
        assert "Request validation failed" in error.message
        assert details in error.message
        assert error.correlationId == "trace-val-456"
        assert len(error.timestamp) > 0

    def test_error_response_to_dict(self):
        """Test ErrorResponse to_dict() serialization."""
        # Arrange
        error = ErrorResponse(
            errorCode="TEST",
            message="Test message",
            correlationId="123",
            timestamp="2026-03-28T10:00:00.000000Z"
        )

        # Act
        result = error.to_dict()

        # Assert
        assert result == {
            "errorCode": "TEST",
            "message": "Test message",
            "correlationId": "123",
            "timestamp": "2026-03-28T10:00:00.000000Z"
        }

    def test_error_response_to_dict_contains_all_fields(self):
        """Test to_dict() includes all required error fields."""
        # Arrange
        error = ErrorResponse.create_internal_error("trace-xyz")

        # Act
        result = error.to_dict()

        # Assert
        assert "errorCode" in result
        assert "message" in result
        assert "correlationId" in result
        assert "timestamp" in result
        assert len(result) == 4

    def test_error_response_missing_field_raises_error(self):
        """Test Pydantic validation rejects missing fields."""
        # Act & Assert
        with pytest.raises(ValidationError):
            ErrorResponse(errorCode="TEST", message="Test")  # Missing correlationId, timestamp
