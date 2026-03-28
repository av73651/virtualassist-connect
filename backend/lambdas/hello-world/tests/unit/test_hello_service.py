"""Unit tests for HelloService.

Tests that service layer returns domain objects (HelloMessage), not DTOs.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch
from src.services.hello_service import HelloService
from src.domain.hello_message import HelloMessage


def test_get_hello_message_returns_domain_object():
    """Test get_hello_message returns HelloMessage domain object (not DTO)."""
    service = HelloService()
    result = service.get_hello_message()
    assert isinstance(result, HelloMessage)


def test_get_hello_message_has_correct_message():
    """Test message is exactly 'Hello, World!' (BR-001)."""
    service = HelloService()
    result = service.get_hello_message()
    assert result.message == "Hello, World!"


def test_get_hello_message_has_datetime_timestamp():
    """Test timestamp is a datetime object (domain layer uses native types)."""
    service = HelloService()
    result = service.get_hello_message()
    assert isinstance(result.timestamp, datetime)


def test_get_hello_message_timestamp_is_utc():
    """Test timestamp is recent UTC time and timezone-aware."""
    service = HelloService()
    result = service.get_hello_message()

    # Verify timestamp is timezone-aware (Python 3.12+ requirement)
    assert result.timestamp.tzinfo is not None
    assert result.timestamp.tzinfo == timezone.utc

    # Verify it's a recent timestamp (within last 5 seconds)
    now = datetime.now(timezone.utc)
    delta = abs((now - result.timestamp).total_seconds())
    assert delta < 5, f"Timestamp is {delta}s old, expected recent"


@patch('src.domain.hello_message.datetime')
def test_get_hello_message_with_fixed_datetime(mock_datetime):
    """Test with deterministic timestamp for reproducible tests."""
    fixed_dt = datetime(2026, 3, 27, 10, 0, 0, tzinfo=timezone.utc)
    mock_datetime.now.return_value = fixed_dt
    mock_datetime.timezone = timezone  # Mock the timezone module

    service = HelloService()
    result = service.get_hello_message()

    assert result.message == "Hello, World!"
    assert result.timestamp == fixed_dt


@patch('shared.middleware.observability.logger')
def test_get_hello_message_logs_correctly(mock_logger):
    """Test structured logging is emitted."""
    service = HelloService()
    service.get_hello_message()

    # Verify logger.info was called at least once
    assert mock_logger.info.call_count >= 1


def test_get_hello_message_validates_domain_object():
    """Test that service validates domain object before returning."""
    service = HelloService()
    result = service.get_hello_message()

    # Domain object should pass validation
    assert result.validate() is True


def test_get_hello_message_records_metrics():
    """Test that OpenTelemetry metrics are recorded."""
    service = HelloService()
    import shared.middleware.observability as obs

    counter = obs._counters["hello_message"]
    histogram = obs._histograms["hello_message"]

    # Mock the metrics
    with patch.object(counter, 'add') as mock_counter, \
         patch.object(histogram, 'record') as mock_histogram:

        result = service.get_hello_message()

        # Verify counter was incremented with success status
        mock_counter.assert_called_once()
        call_args = mock_counter.call_args
        assert call_args[0][0] == 1  # Increment by 1
        assert call_args[0][1]['status'] == 'success'

        # Verify histogram was recorded with duration
        mock_histogram.assert_called_once()
        histogram_args = mock_histogram.call_args
        assert histogram_args[0][0] >= 0  # Duration should be non-negative
        assert histogram_args[0][1]['status'] == 'success'


def test_get_hello_message_records_error_metrics():
    """Test that metrics are recorded on errors."""
    service = HelloService()
    import shared.middleware.observability as obs

    counter = obs._counters["hello_message"]
    histogram = obs._histograms["hello_message"]

    # Mock HelloMessage.create to raise an exception
    with patch('src.services.hello_service.HelloMessage.create', side_effect=ValueError("Test error")), \
         patch.object(counter, 'add') as mock_counter, \
         patch.object(histogram, 'record') as mock_histogram:

        with pytest.raises(ValueError):
            service.get_hello_message()

        # Verify counter was incremented with error status
        mock_counter.assert_called_once()
        call_args = mock_counter.call_args
        assert call_args[0][0] == 1
        assert call_args[0][1]['status'] == 'error'

        # Verify histogram was recorded with error status
        mock_histogram.assert_called_once()
        histogram_args = mock_histogram.call_args
        assert histogram_args[0][1]['status'] == 'error'
