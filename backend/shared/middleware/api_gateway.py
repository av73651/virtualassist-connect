import json
import logging
from functools import wraps
from typing import Callable, Any
from pydantic import ValidationError
from src.dto.response import ErrorResponse
from shared.exceptions.business_rule_error import BusinessRuleError

logger = logging.getLogger(__name__)

def api_gateway_handler(func: Callable) -> Callable:
    """AOP Decorator for API Gateway Lambda Handlers.

    Handles:
    - Trace ID extraction
    - Standardized entry/exit logging
    - Global exception catching and mapping to appropriate HTTP status codes
    - Response formatting

    Exception Mapping:
    - ValidationError (Pydantic) → 400 Bad Request
    - Exception (all others) → 500 Internal Server Error
    """
    @wraps(func)
    def wrapper(event: dict, context: Any) -> dict:
        request_id = getattr(context, 'request_id', 'unknown-request-id')
        trace_id = event.get('headers', {}).get('X-Amzn-Trace-Id', request_id)

        logger.info(
            "API Request received",
            extra={
                "http_method": event.get('httpMethod'),
                "path": event.get('path'),
                "trace_id": trace_id,
                "request_id": request_id
            }
        )

        try:
            # Delegate to business handler
            result = func(event, context, trace_id)
            
            # If the handler returned a raw dict with statusCode, return as is
            if isinstance(result, dict) and 'statusCode' in result:
                response = result
            else:
                # Default success formatting
                response = {
                    'statusCode': 200,
                    'headers': {
                        'Content-Type': 'application/json',
                        'X-Trace-Id': trace_id
                    },
                    'body': json.dumps(result)
                }

            logger.info(
                "API Request completed successfully",
                extra={
                    "status_code": response.get('statusCode', 200),
                    "trace_id": trace_id
                }
            )
            return response

        except ValidationError as e:
            # Client error - invalid request format/data
            logger.warning(
                "API Request failed validation",
                extra={
                    "error": str(e),
                    "error_type": "ValidationError",
                    "trace_id": trace_id,
                    "validation_errors": e.errors()
                }
            )

            error_response = ErrorResponse.create_validation_error(trace_id, str(e))

            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'X-Trace-Id': trace_id
                },
                'body': json.dumps(error_response.to_dict())
            }

        except BusinessRuleError as e:
            # Business rule violation - domain raised, @observe already logged/traced
            logger.warning(
                "API Request failed business rule validation",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "error_code": e.error_code,
                    "trace_id": trace_id
                }
            )

            error_response = ErrorResponse.create_business_rule_error(
                trace_id, e.error_code, str(e)
            )

            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'X-Trace-Id': trace_id
                },
                'body': json.dumps(error_response.to_dict())
            }

        except Exception as e:
            # Server error - unexpected exception
            logger.error(
                "API Request failed with systemic error",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "trace_id": trace_id
                },
                exc_info=True
            )

            error_response = ErrorResponse.create_internal_error(trace_id)

            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'X-Trace-Id': trace_id
                },
                'body': json.dumps(error_response.to_dict())
            }

    return wrapper
