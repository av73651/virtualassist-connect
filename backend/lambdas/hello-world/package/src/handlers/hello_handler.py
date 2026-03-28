"""Hello World Lambda Handler.

This module contains the Lambda entry point for API Gateway requests.
Handles routing, response formatting, error handling, and domain-to-DTO conversion.

Handler layer responsibilities:
- Parse API Gateway events
- Convert domain objects to DTOs
- Format HTTP responses
- Handle errors

Uses structured logging with 'extra' dictionaries for proper JSON formatting.
"""

import json
import logging
from typing import Any

# Configure structured logging on import (before other imports)
from src.config.logging_config import configure_structured_logging
configure_structured_logging()

from src.services.hello_service import HelloService
from src.dto.response import HelloResponse
from src.middleware.api_gateway import api_gateway_handler

@api_gateway_handler
def lambda_handler(event: dict, context: Any, trace_id: str) -> dict:
    """Lambda entry point for API Gateway requests.

    Args:
        event: API Gateway proxy event
        context: Lambda context
        trace_id: Extracted X-Ray trace ID provided by AOP middleware

    Returns:
        dict: The DTO payload. @api_gateway_handler will automatically format it
              as a proper HTTP 200 JSON API Gateway response.
    """
    return handle_hello_request()


def handle_hello_request() -> dict:
    """Handle GET /hello request.

    Handler layer responsibilities:
    1. Call service layer (gets domain object)
    2. Convert domain object to DTO

    Returns:
        dict: The JSON-serializable DTO response payload
    """
    # Instantiate service
    hello_service = HelloService()

    # Get domain object from service layer
    hello_message = hello_service.get_hello_message()

    # Convert domain object to DTO (handler layer responsibility)
    hello_response = HelloResponse.create(
        message=hello_message.message,
        timestamp=hello_message.timestamp
    )

    return hello_response.to_dict()
