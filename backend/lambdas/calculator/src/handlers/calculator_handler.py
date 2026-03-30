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

    Routes to appropriate operation handler based on API Gateway path.
    All error handling via AOP decorators - no try/catch here.

    Args:
        event: API Gateway proxy event
        context: Lambda context
        trace_id: Extracted X-Ray trace ID provided by AOP middleware

    Returns:
        dict: The DTO payload. @api_gateway_handler will automatically format it
              as a proper HTTP 200 JSON API Gateway response.
    """
    path = event.get('path', '')

    if path.endswith('/subtract'):
        return handle_subtract_request(event)
    elif path.endswith('/multiply'):
        return handle_multiply_request(event)
    elif path.endswith('/divide'):
        return handle_divide_request(event)
    else:
        return handle_add_request(event)


def _parse_request(event: dict) -> CalculatorRequest:
    """Parse and validate request body from API Gateway event.

    Args:
        event: API Gateway proxy event

    Returns:
        CalculatorRequest: Validated request DTO

    Raises:
        ValidationError: If request body validation fails (Pydantic)
    """
    body = json.loads(event.get('body', '{}'))
    return CalculatorRequest(**body)


def handle_add_request(event: dict) -> dict:
    """Handle POST /calculator/add request."""
    request_dto = _parse_request(event)
    calculation = _calculator_service.add(request_dto.a, request_dto.b)
    return CalculatorResponse.from_calculation(calculation).to_dict()


def handle_subtract_request(event: dict) -> dict:
    """Handle POST /calculator/subtract request (FR-005)."""
    request_dto = _parse_request(event)
    calculation = _calculator_service.subtract(request_dto.a, request_dto.b)
    return CalculatorResponse.from_calculation(calculation).to_dict()


def handle_multiply_request(event: dict) -> dict:
    """Handle POST /calculator/multiply request (FR-006)."""
    request_dto = _parse_request(event)
    calculation = _calculator_service.multiply(request_dto.a, request_dto.b)
    return CalculatorResponse.from_calculation(calculation).to_dict()


def handle_divide_request(event: dict) -> dict:
    """Handle POST /calculator/divide request (FR-007).

    DivisionByZeroError propagation path:
    Domain (raises) -> @observe (logs/metrics/traces) -> Handler (no catch) -> @api_gateway_handler (HTTP 400)
    """
    request_dto = _parse_request(event)
    calculation = _calculator_service.divide(request_dto.a, request_dto.b)
    return CalculatorResponse.from_calculation(calculation).to_dict()
