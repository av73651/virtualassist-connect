"""Response Data Transfer Objects.

This module defines Pydantic models for API responses with validation
and serialization methods.
"""

from datetime import datetime, timezone
from pydantic import BaseModel, Field
from src.domain.calculation import Calculation


class CalculatorResponse(BaseModel):
    """Response DTO for calculator operations.

    Attributes:
        a: First operand
        b: Second operand
        operation: Operation performed
        result: Calculation result
        timestamp: ISO 8601 timestamp in UTC
    """

    a: float = Field(..., description="First operand")
    b: float = Field(..., description="Second operand")
    operation: str = Field(..., description="Operation performed")
    result: float = Field(..., description="Calculation result")
    timestamp: str = Field(
        ...,
        description="ISO 8601 timestamp in UTC",
        example="2026-03-27T10:00:00.123456Z"
    )

    @classmethod
    def from_calculation(cls, calc: Calculation) -> "CalculatorResponse":
        """Convert domain object to DTO.

        Args:
            calc: Calculation domain object

        Returns:
            CalculatorResponse: Response DTO
        """
        return cls(
            a=calc.operand_a,
            b=calc.operand_b,
            operation=calc.operation,
            result=calc.result,
            timestamp=calc.timestamp.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        )

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "a": self.a,
            "b": self.b,
            "operation": self.operation,
            "result": self.result,
            "timestamp": self.timestamp
        }


class ErrorResponse(BaseModel):
    """Standard error response DTO.

    Attributes:
        errorCode: Error code identifier
        message: Human-readable error message
        correlationId: Trace ID for correlation
        timestamp: ISO 8601 timestamp
    """

    errorCode: str = Field(..., description="Error code identifier")
    message: str = Field(..., description="Human-readable error message")
    correlationId: str = Field(..., description="Trace ID for correlation")
    timestamp: str = Field(..., description="ISO 8601 timestamp")

    @classmethod
    def create_internal_error(cls, correlation_id: str) -> "ErrorResponse":
        """Create standard internal error response."""
        return cls(
            errorCode="INTERNAL_ERROR",
            message="An internal error occurred",
            correlationId=correlation_id,
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        )

    @classmethod
    def create_validation_error(cls, correlation_id: str, details: str) -> "ErrorResponse":
        """Create validation error response.

        Args:
            correlation_id: Trace ID for request correlation
            details: Validation error details from Pydantic

        Returns:
            ErrorResponse: Validation error with 400 status
        """
        return cls(
            errorCode="VALIDATION_ERROR",
            message=f"Request validation failed: {details}",
            correlationId=correlation_id,
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        )

    @classmethod
    def create_business_rule_error(cls, correlation_id: str, error_code: str, message: str) -> "ErrorResponse":
        """Create error response for any business rule violation.

        Generic factory - works for DivisionByZeroError or any future BusinessRuleError subclass.
        The error_code and message come from the exception itself.

        Args:
            correlation_id: Trace ID for request correlation
            error_code: Machine-readable error code from BusinessRuleError.error_code
            message: Human-readable message from the exception

        Returns:
            ErrorResponse: Business rule error with 400 status
        """
        return cls(
            errorCode=error_code,
            message=message,
            correlationId=correlation_id,
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "errorCode": self.errorCode,
            "message": self.message,
            "correlationId": self.correlationId,
            "timestamp": self.timestamp
        }
