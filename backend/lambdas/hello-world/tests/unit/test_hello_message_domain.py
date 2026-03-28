"""Unit tests for HelloMessage domain model.

Tests pure domain logic with no framework dependencies.
"""

import pytest
from datetime import datetime, timezone
from src.domain.hello_message import HelloMessage


def test_hello_message_creation():
    """Test HelloMessage domain object creation."""
    message = HelloMessage(message="Test", timestamp=datetime(2026, 3, 27, 10, 0, 0, tzinfo=timezone.utc))
    assert message.message == "Test"
    assert message.timestamp == datetime(2026, 3, 27, 10, 0, 0, tzinfo=timezone.utc)


def test_hello_message_is_immutable():
    """Test HelloMessage is immutable (frozen dataclass)."""
    message = HelloMessage(message="Test", timestamp=datetime.now(timezone.utc))

    with pytest.raises(Exception):
        message.message = "Changed"  # Should raise FrozenInstanceError


def test_hello_message_factory_method():
    """Test HelloMessage factory method creates with current timestamp."""
    message = HelloMessage.create("Hello, World!")

    assert message.message == "Hello, World!"
    assert isinstance(message.timestamp, datetime)
    assert message.timestamp.tzinfo == timezone.utc  # Verify timezone-aware

    # Verify timestamp is recent (within last second)
    now = datetime.now(timezone.utc)
    delta = abs((now - message.timestamp).total_seconds())
    assert delta < 1


def test_hello_message_validate_success():
    """Test validation passes for valid domain object."""
    message = HelloMessage(message="Test", timestamp=datetime.now(timezone.utc))
    assert message.validate() is True


def test_hello_message_validate_empty_message():
    """Test validation fails for empty message."""
    message = HelloMessage(message="", timestamp=datetime.now(timezone.utc))

    with pytest.raises(ValueError, match="Message cannot be empty"):
        message.validate()


def test_hello_message_validate_whitespace_message():
    """Test validation fails for whitespace-only message."""
    message = HelloMessage(message="   ", timestamp=datetime.now(timezone.utc))

    with pytest.raises(ValueError, match="Message cannot be empty"):
        message.validate()


def test_hello_message_validate_none_timestamp():
    """Test validation fails for None timestamp."""
    message = HelloMessage(message="Test", timestamp=None)

    with pytest.raises(ValueError, match="Timestamp cannot be None"):
        message.validate()


def test_hello_message_business_rule_br001():
    """Test HelloMessage supports BR-001 (Hello, World! message)."""
    message = HelloMessage.create("Hello, World!")

    assert message.message == "Hello, World!"
    assert message.validate() is True


def test_hello_message_timezone_aware():
    """Test HelloMessage uses timezone-aware datetime (Python 3.12+ requirement)."""
    message = HelloMessage.create("Test")

    # Verify timestamp is timezone-aware
    assert message.timestamp.tzinfo is not None
    assert message.timestamp.tzinfo == timezone.utc
