"""Unit tests for hello_handler."""

import pytest
import json
from unittest.mock import patch, Mock
from src.handlers.hello_handler import lambda_handler, handle_hello_request
from src.dto.response import HelloResponse


def test_lambda_handler_returns_200_AC_001(api_gateway_event, lambda_context, mock_hello_service):
    """Test lambda_handler returns HTTP 200 (AC-001)."""
    with patch('src.handlers.hello_handler._hello_service', mock_hello_service):
        response = lambda_handler(api_gateway_event, lambda_context)
        assert response['statusCode'] == 200


def test_lambda_handler_response_is_valid_json_AC_002(api_gateway_event, lambda_context, mock_hello_service):
    """Test response body is valid JSON (AC-002)."""
    with patch('src.handlers.hello_handler._hello_service', mock_hello_service):
        response = lambda_handler(api_gateway_event, lambda_context)
        body = json.loads(response['body'])
        assert isinstance(body, dict)


def test_handle_hello_request_contains_message_AC_003(mock_hello_service):
    """Test response contains message 'Hello, World!' (AC-003)."""
    with patch('src.handlers.hello_handler._hello_service', mock_hello_service):
        response_payload = handle_hello_request()
        assert response_payload['message'] == "Hello, World!"


def test_handle_hello_request_contains_timestamp_AC_004(mock_hello_service):
    """Test response contains ISO 8601 timestamp (AC-004)."""
    with patch('src.handlers.hello_handler._hello_service', mock_hello_service):
        response_payload = handle_hello_request()
        assert 'timestamp' in response_payload
        assert response_payload['timestamp'].endswith('Z') or '+00:00' in response_payload['timestamp']


def test_lambda_handler_with_exception_returns_500(api_gateway_event, lambda_context):
    """Test exception handling returns 500 with error response."""
    # Patch the module-level singleton service instance
    with patch('src.handlers.hello_handler._hello_service') as mock_service:
        mock_service.get_hello_message.side_effect = Exception("Test error")

        response = lambda_handler(api_gateway_event, lambda_context)

        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert body['errorCode'] == 'INTERNAL_ERROR'


def test_lambda_handler_includes_trace_id_in_response(api_gateway_event, lambda_context, mock_hello_service):
    """Test response includes X-Trace-Id header."""
    with patch('src.handlers.hello_handler._hello_service', mock_hello_service):
        response = lambda_handler(api_gateway_event, lambda_context)
        assert 'X-Trace-Id' in response['headers']


def test_lambda_handler_content_type_header(api_gateway_event, lambda_context, mock_hello_service):
    """Test lambda_handler response has correct Content-Type header."""
    with patch('src.handlers.hello_handler._hello_service', mock_hello_service):
        response = lambda_handler(api_gateway_event, lambda_context)
        assert response['headers']['Content-Type'] == 'application/json'


def test_lambda_handler_extracts_trace_id_from_headers(lambda_context, mock_hello_service):
    """Test trace ID extraction from X-Amzn-Trace-Id header."""
    event = {
        'httpMethod': 'GET',
        'path': '/hello',
        'headers': {'X-Amzn-Trace-Id': 'custom-trace-id'}
    }

    with patch('src.handlers.hello_handler._hello_service', mock_hello_service):
        response = lambda_handler(event, lambda_context)
        assert response['headers']['X-Trace-Id'] == 'custom-trace-id'
