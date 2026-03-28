"""Calculator Lambda Handler.

This module contains the Lambda entry point for Calculator API requests.
Handles request validation, domain-to-DTO conversion, and response formatting.

Handler layer responsibilities:
- Parse and validate API Gateway events
- Convert domain objects to DTOs
- Format HTTP responses
- Handle validation errors

Uses structured logging with 'extra' dictionaries for proper JSON formatting.
"""

import json
import logging
from typing import Any

from src.services.calculator_service import CalculatorService
from src.dto.request import CalculatorRequest
from src.dto.response import CalculatorResponse
from shared.middleware.api_gateway import api_gateway_handler

logger = logging.getLogger(__name__)

# Module-level singleton - instantiated once per Lambda container lifecycle
_calculator_service = CalculatorService()


@api_gateway_handler
def lambda_handler(event: dict, context: Any, trace_id: str) -> dict:
    """Lambda entry point for Calculator API requests.

    Args:
        event: API Gateway proxy event
        context: Lambda context
        trace_id: Extracted X-Ray trace ID provided by AOP middleware

    Returns:
        dict: The DTO payload. @api_gateway_handler will automatically format it
              as a proper HTTP 200 JSON API Gateway response.

    Raises:
        ValidationError: If request body is invalid (caught by middleware → 400)
        Exception: Any unexpected error (caught by middleware → 500)
    """
    return handle_add_request(event)


def handle_add_request(event: dict) -> dict:
    """Handle POST /calculator/add request.

    Handler layer responsibilities:
    1. Parse and validate request body (DTO)
    2. Call service layer (gets domain object)
    3. Convert domain object to DTO

    Args:
        event: API Gateway proxy event

    Returns:
        dict: The JSON-serializable DTO response payload

    Raises:
        ValidationError: If request body validation fails (Pydantic)
    """
    # Parse request body
    body_str = event.get('body', '{}')
    body = json.loads(body_str)

    # Validate using Pydantic DTO (raises ValidationError if invalid)
    request_dto = CalculatorRequest(**body)

    # Use module-level singleton (efficient, reuses instance across invocations)
    calculation = _calculator_service.add(request_dto.a, request_dto.b)

    # Convert domain object to DTO (handler layer responsibility)
    response_dto = CalculatorResponse.from_calculation(calculation)

    return response_dto.to_dict()
