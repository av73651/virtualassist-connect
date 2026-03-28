"""Request Data Transfer Objects.

This module defines Pydantic models for API request validation.
"""

from pydantic import BaseModel, Field, ConfigDict


class CalculatorRequest(BaseModel):
    """Request DTO for calculator operations.

    Validates incoming request body for /calculator/add endpoint.

    Attributes:
        a: First operand (numeric)
        b: Second operand (numeric)
    """

    a: float = Field(
        ...,
        description="First operand for calculation"
    )
    b: float = Field(
        ...,
        description="Second operand for calculation"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "a": 5.5,
                    "b": 3.2
                },
                {
                    "a": 10,
                    "b": -3
                }
            ]
        }
    )
