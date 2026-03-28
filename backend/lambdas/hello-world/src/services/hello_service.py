"""Hello World Service.

This module contains business logic for generating hello world messages.
Implements BR-001: Message format requirements.

Service layer returns domain objects only - no DTOs.
All observability concerns (tracing, metrics, logging) handled by @observe decorator.
"""

from src.domain.hello_message import HelloMessage
from shared.middleware.observability import observe


class HelloService:
    """Service for generating hello world messages.

    Implements business logic for BR-001: Message format requirements.
    Returns domain objects only - DTOs are handled in the handler layer.
    All cross-cutting concerns handled by observability middleware.
    """

    def __init__(self) -> None:
        """Initialize HelloService."""
        pass

    @observe(operation="get_hello_message", metric_prefix="hello_message")
    def get_hello_message(self) -> HelloMessage:
        """Generate hello world message with current timestamp.

        Business Rules:
        - BR-001: Message must be exactly "Hello, World!"

        Observability:
        - Tracing, metrics, and logging handled by @observe decorator
        - Creates OpenTelemetry span with status
        - Records counter + histogram metrics
        - Logs entry/exit with structured context

        Returns:
            HelloMessage: Domain object with message and timestamp
        """
        # Pure business logic - no observability boilerplate
        hello_message = HelloMessage.create("Hello, World!")
        hello_message.validate()
        return hello_message
