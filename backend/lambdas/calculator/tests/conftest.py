"""Shared test fixtures for calculator unit and integration tests."""

import pytest
import json
from unittest.mock import Mock
from datetime import datetime, timezone
from src.services.calculator_service import CalculatorService
from src.domain.calculation import Calculation


@pytest.fixture
def mock_calculator_service():
    """Mock CalculatorService for handler tests.

    Returns domain object (Calculation) as per architecture.

    Returns:
        Mock: Mocked CalculatorService with predefined domain object
    """
    service = Mock(spec=CalculatorService)
    service.add.return_value = Calculation(
        operand_a=5.5,
        operand_b=3.2,
        operation="add",
        result=8.7,
        timestamp=datetime(2026, 3, 28, 10, 0, 0, tzinfo=timezone.utc)
    )
    return service


@pytest.fixture
def calculator_request_event():
    """API Gateway event for POST /calculator/add request.

    Returns:
        dict: Sample calculator API Gateway event with valid JSON body
    """
    return {
        'resource': '/calculator/add',
        'httpMethod': 'POST',
        'path': '/calculator/add',
        'headers': {
            'Content-Type': 'application/json'
        },
        'requestContext': {
            'requestId': 'test-request-id'
        },
        'body': json.dumps({
            "a": 5.5,
            "b": 3.2
        })
    }


@pytest.fixture
def lambda_context():
    """Mock Lambda context.

    Returns:
        Mock: Mocked Lambda context object
    """
    context = Mock()
    context.function_name = 'calculator-function'
    context.request_id = 'test-request-id'
    return context


@pytest.fixture
def fixed_datetime():
    """Fixed datetime for deterministic tests.

    Returns:
        datetime: Fixed datetime object (2026-03-28 10:00:00 UTC, timezone-aware)
    """
    return datetime(2026, 3, 28, 10, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def subtract_request_event():
    """API Gateway event for POST /calculator/subtract request."""
    return {
        'resource': '/calculator/subtract',
        'httpMethod': 'POST',
        'path': '/calculator/subtract',
        'headers': {
            'Content-Type': 'application/json'
        },
        'requestContext': {
            'requestId': 'test-request-id'
        },
        'body': json.dumps({
            "a": 10,
            "b": 3
        })
    }


@pytest.fixture
def multiply_request_event():
    """API Gateway event for POST /calculator/multiply request."""
    return {
        'resource': '/calculator/multiply',
        'httpMethod': 'POST',
        'path': '/calculator/multiply',
        'headers': {
            'Content-Type': 'application/json'
        },
        'requestContext': {
            'requestId': 'test-request-id'
        },
        'body': json.dumps({
            "a": 4,
            "b": 5
        })
    }


@pytest.fixture
def divide_request_event():
    """API Gateway event for POST /calculator/divide request."""
    return {
        'resource': '/calculator/divide',
        'httpMethod': 'POST',
        'path': '/calculator/divide',
        'headers': {
            'Content-Type': 'application/json'
        },
        'requestContext': {
            'requestId': 'test-request-id'
        },
        'body': json.dumps({
            "a": 10,
            "b": 2
        })
    }
