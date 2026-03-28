"""Unit tests for calculator_handler."""

import pytest
import json
from unittest.mock import patch, Mock
from datetime import datetime, timezone
from pydantic import ValidationError
from src.handlers.calculator_handler import lambda_handler, handle_add_request
from src.domain.calculation import Calculation


def test_lambda_handler_returns_200(calculator_request_event, lambda_context, mock_calculator_service):
    """Test lambda_handler returns HTTP 200 for valid request."""
    with patch('src.handlers.calculator_handler._calculator_service', mock_calculator_service):
        response = lambda_handler(calculator_request_event, lambda_context)
        assert response['statusCode'] == 200


def test_lambda_handler_response_is_valid_json(calculator_request_event, lambda_context, mock_calculator_service):
    """Test response body is valid JSON."""
    with patch('src.handlers.calculator_handler._calculator_service', mock_calculator_service):
        response = lambda_handler(calculator_request_event, lambda_context)
        body = json.loads(response['body'])
        assert isinstance(body, dict)


def test_handle_add_request_contains_result_AC_009(calculator_request_event, mock_calculator_service):
    """Test response contains all required fields (AC-009)."""
    with patch('src.handlers.calculator_handler._calculator_service', mock_calculator_service):
        response_payload = handle_add_request(calculator_request_event)

        assert 'a' in response_payload
        assert 'b' in response_payload
        assert 'operation' in response_payload
        assert 'result' in response_payload
        assert 'timestamp' in response_payload


def test_handle_add_request_correct_values(calculator_request_event, mock_calculator_service):
    """Test response contains correct calculation values."""
    with patch('src.handlers.calculator_handler._calculator_service', mock_calculator_service):
        response_payload = handle_add_request(calculator_request_event)

        assert response_payload['a'] == 5.5
        assert response_payload['b'] == 3.2
        assert response_payload['operation'] == "add"
        assert abs(response_payload['result'] - 8.7) < 1e-10


def test_lambda_handler_content_type_header_AC_010(calculator_request_event, lambda_context, mock_calculator_service):
    """Test response has correct Content-Type header (AC-010)."""
    with patch('src.handlers.calculator_handler._calculator_service', mock_calculator_service):
        response = lambda_handler(calculator_request_event, lambda_context)
        assert response['headers']['Content-Type'] == 'application/json'


def test_lambda_handler_includes_trace_id_in_response(calculator_request_event, lambda_context, mock_calculator_service):
    """Test response includes X-Trace-Id header."""
    with patch('src.handlers.calculator_handler._calculator_service', mock_calculator_service):
        response = lambda_handler(calculator_request_event, lambda_context)
        assert 'X-Trace-Id' in response['headers']


def test_lambda_handler_extracts_trace_id_from_headers(lambda_context, mock_calculator_service):
    """Test trace ID extraction from X-Amzn-Trace-Id header."""
    event = {
        'httpMethod': 'POST',
        'path': '/calculator/add',
        'headers': {'X-Amzn-Trace-Id': 'custom-trace-id'},
        'body': json.dumps({"a": 5, "b": 3})
    }

    with patch('src.handlers.calculator_handler._calculator_service', mock_calculator_service):
        response = lambda_handler(event, lambda_context)
        assert response['headers']['X-Trace-Id'] == 'custom-trace-id'


def test_lambda_handler_missing_field_returns_400_AC_006(lambda_context):
    """Test missing operand returns 400 Bad Request (AC-006)."""
    event = {
        'httpMethod': 'POST',
        'path': '/calculator/add',
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({"a": 5})  # Missing 'b'
    }

    response = lambda_handler(event, lambda_context)

    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert body['errorCode'] == 'VALIDATION_ERROR'


def test_lambda_handler_non_numeric_returns_400_AC_007(lambda_context):
    """Test non-numeric operand returns 400 Bad Request (AC-007)."""
    event = {
        'httpMethod': 'POST',
        'path': '/calculator/add',
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({"a": "invalid", "b": 3})
    }

    response = lambda_handler(event, lambda_context)

    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert body['errorCode'] == 'VALIDATION_ERROR'


def test_lambda_handler_null_operand_returns_400_AC_008(lambda_context):
    """Test null operand returns 400 Bad Request (AC-008)."""
    event = {
        'httpMethod': 'POST',
        'path': '/calculator/add',
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({"a": None, "b": 3})
    }

    response = lambda_handler(event, lambda_context)

    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert body['errorCode'] == 'VALIDATION_ERROR'


def test_lambda_handler_empty_body_returns_400(lambda_context):
    """Test empty body returns 400 Bad Request."""
    event = {
        'httpMethod': 'POST',
        'path': '/calculator/add',
        'headers': {'Content-Type': 'application/json'},
        'body': '{}'
    }

    response = lambda_handler(event, lambda_context)

    assert response['statusCode'] == 400


def test_lambda_handler_with_exception_returns_500_AC_012(calculator_request_event, lambda_context):
    """Test internal exception returns 500 with error response (AC-012)."""
    with patch('src.handlers.calculator_handler._calculator_service') as mock_service:
        mock_service.add.side_effect = Exception("Test error")

        response = lambda_handler(calculator_request_event, lambda_context)

        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert body['errorCode'] == 'INTERNAL_ERROR'


def test_lambda_handler_error_includes_correlation_id_AC_011(calculator_request_event, lambda_context):
    """Test error response includes correlationId (AC-011)."""
    with patch('src.handlers.calculator_handler._calculator_service') as mock_service:
        mock_service.add.side_effect = Exception("Test error")

        response = lambda_handler(calculator_request_event, lambda_context)

        body = json.loads(response['body'])
        assert 'correlationId' in body
        assert body['correlationId'] is not None


def test_handle_add_request_negative_numbers(mock_calculator_service):
    """Test handler processes negative numbers correctly."""
    event = {
        'body': json.dumps({"a": -5, "b": -3})
    }

    with patch('src.handlers.calculator_handler._calculator_service', mock_calculator_service):
        mock_calculator_service.add.return_value = Calculation(
            operand_a=-5,
            operand_b=-3,
            operation="add",
            result=-8,
            timestamp=datetime.now(timezone.utc)
        )

        response_payload = handle_add_request(event)

        assert response_payload['result'] == -8


def test_handle_add_request_zero_operands(mock_calculator_service):
    """Test handler processes zero operands correctly."""
    event = {
        'body': json.dumps({"a": 0, "b": 0})
    }

    with patch('src.handlers.calculator_handler._calculator_service', mock_calculator_service):
        mock_calculator_service.add.return_value = Calculation(
            operand_a=0,
            operand_b=0,
            operation="add",
            result=0,
            timestamp=datetime.now(timezone.utc)
        )

        response_payload = handle_add_request(event)

        assert response_payload['result'] == 0


def test_handle_add_request_uses_singleton_service():
    """Test handler uses module-level singleton service."""
    event = {
        'body': json.dumps({"a": 5, "b": 3})
    }

    # Verify the singleton is called, not a new instance
    with patch('src.handlers.calculator_handler._calculator_service') as mock_service:
        mock_service.add.return_value = Calculation(
            operand_a=5,
            operand_b=3,
            operation="add",
            result=8,
            timestamp=datetime.now(timezone.utc)
        )

        handle_add_request(event)

        # Verify the singleton's add method was called
        mock_service.add.assert_called_once_with(5, 3)


def test_handle_add_request_large_numbers(mock_calculator_service):
    """Test handler processes large numbers correctly."""
    event = {
        'body': json.dumps({"a": 1e100, "b": 2e100})
    }

    with patch('src.handlers.calculator_handler._calculator_service', mock_calculator_service):
        mock_calculator_service.add.return_value = Calculation(
            operand_a=1e100,
            operand_b=2e100,
            operation="add",
            result=3e100,
            timestamp=datetime.now(timezone.utc)
        )

        response_payload = handle_add_request(event)

        assert response_payload['result'] == 3e100
