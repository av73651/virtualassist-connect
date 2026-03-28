"""Unit tests for response DTOs."""

import pytest
from datetime import datetime
from src.dto.response import HelloResponse, ErrorResponse


def test_hello_response_creation():
    """Test HelloResponse DTO creation with direct instantiation."""
    response = HelloResponse(message="Test", timestamp="2026-03-27T10:00:00.000Z")
    assert response.message == "Test"
    assert response.timestamp == "2026-03-27T10:00:00.000Z"


def test_hello_response_factory_method():
    """Test HelloResponse factory method with datetime object."""
    dt = datetime(2026, 3, 27, 10, 0, 0)
    response = HelloResponse.create("Hello, World!", dt)
    assert response.message == "Hello, World!"
    assert response.timestamp == "2026-03-27T10:00:00.000000Z"


def test_hello_response_to_dict():
    """Test HelloResponse to_dict() serialization."""
    response = HelloResponse(message="Test", timestamp="2026-03-27T10:00:00.000Z")
    result = response.to_dict()
    assert result == {"message": "Test", "timestamp": "2026-03-27T10:00:00.000Z"}


def test_hello_response_pydantic_validation():
    """Test Pydantic validation rejects missing fields."""
    with pytest.raises(Exception):
        HelloResponse(message="Test")  # Missing timestamp


def test_error_response_creation():
    """Test ErrorResponse DTO creation."""
    error = ErrorResponse(
        errorCode="TEST_ERROR",
        message="Test message",
        correlationId="123",
        timestamp="2026-03-27T10:00:00.000Z"
    )
    assert error.errorCode == "TEST_ERROR"
    assert error.correlationId == "123"


def test_error_response_factory_method():
    """Test ErrorResponse factory method for internal errors."""
    error = ErrorResponse.create_internal_error("trace-123")
    assert error.errorCode == "INTERNAL_ERROR"
    assert error.message == "An internal error occurred"
    assert error.correlationId == "trace-123"
    assert len(error.timestamp) > 0


def test_error_response_to_dict():
    """Test ErrorResponse to_dict() serialization."""
    error = ErrorResponse(
        errorCode="TEST",
        message="Test",
        correlationId="123",
        timestamp="2026-03-27T10:00:00.000Z"
    )
    result = error.to_dict()
    assert result["errorCode"] == "TEST"
    assert result["correlationId"] == "123"
