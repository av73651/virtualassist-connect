import json
import logging
from functools import wraps
from typing import Callable, Any
from src.dto.response import ErrorResponse

logger = logging.getLogger(__name__)

def api_gateway_handler(func: Callable) -> Callable:
    """AOP Decorator for API Gateway Lambda Handlers.
    
    Handles:
    - Trace ID extraction
    - Standardized entry/exit logging
    - Global exception catching and mapping to HTTP 500
    - Response formatting
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

        except Exception as e:
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
