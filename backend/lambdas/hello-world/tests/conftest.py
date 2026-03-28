"""Shared test fixtures for unit and integration tests."""

import pytest
from unittest.mock import Mock
from datetime import datetime, timezone
from src.services.hello_service import HelloService
from src.domain.hello_message import HelloMessage


@pytest.fixture
def mock_hello_service():
    """Mock HelloService for handler tests.

    Returns domain object (HelloMessage) as per architecture.

    Returns:
        Mock: Mocked HelloService with predefined domain object
    """
    service = Mock(spec=HelloService)
    service.get_hello_message.return_value = HelloMessage(
        message="Hello, World!",
        timestamp=datetime(2026, 3, 27, 10, 0, 0, tzinfo=timezone.utc)
    )
    return service


@pytest.fixture
def fixed_datetime():
    """Fixed datetime for deterministic tests.

    Returns:
        datetime: Fixed datetime object (2026-03-27 10:00:00 UTC, timezone-aware)
    """
    return datetime(2026, 3, 27, 10, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def api_gateway_event():
    """API Gateway proxy event structure.

    Returns:
        dict: Sample API Gateway event
    """
    return {
        'resource': '/hello',
        'httpMethod': 'GET',
        'headers': {
            'Content-Type': 'application/json'
        },
        'requestContext': {
            'requestId': 'test-request-id'
        }
    }


@pytest.fixture
def lambda_context():
    """Mock Lambda context.

    Returns:
        Mock: Mocked Lambda context object
    """
    context = Mock()
    context.function_name = 'hello-world-function'
    context.request_id = 'test-request-id'
    return context
