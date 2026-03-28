"""Response Data Transfer Objects.

This module defines Pydantic models for API responses with validation
and serialization methods.
"""

from datetime import datetime, timezone
from pydantic import BaseModel, Field


class HelloResponse(BaseModel):
    """Response DTO for hello world endpoint.

    Attributes:
        message: Greeting message
        timestamp: ISO 8601 timestamp in UTC
    """

    message: str = Field(
        ...,
        description="Greeting message",
        example="Hello, World!"
    )
    timestamp: str = Field(
        ...,
        description="ISO 8601 timestamp in UTC",
        example="2026-03-27T10:00:00.000Z"
    )

    @classmethod
    def create(cls, message: str, timestamp: datetime) -> "HelloResponse":
        """Factory method to create HelloResponse."""
        return cls(
            message=message,
            timestamp=timestamp.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "message": self.message,
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

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "errorCode": self.errorCode,
            "message": self.message,
            "correlationId": self.correlationId,
            "timestamp": self.timestamp
        }
