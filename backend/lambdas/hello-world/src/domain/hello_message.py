"""Hello Message Domain Model.

Pure domain object representing a hello world message.
No dependencies on frameworks, DTOs, or infrastructure.
"""

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class HelloMessage:
    """Domain model for a hello world message.

    This is a pure domain object with no external dependencies.
    It represents the business concept of a greeting message.

    Attributes:
        message: The greeting message content
        timestamp: When the message was created
    """

    message: str
    timestamp: datetime

    @classmethod
    def create(cls, message: str) -> "HelloMessage":
        """Factory method to create a HelloMessage with current timestamp.

        Args:
            message: The greeting message content

        Returns:
            HelloMessage: New domain object with current UTC timestamp (timezone-aware)
        """
        return cls(message=message, timestamp=datetime.now(timezone.utc))

    def validate(self) -> bool:
        """Validate domain object invariants.

        Returns:
            bool: True if valid, raises exception otherwise

        Raises:
            ValueError: If message is empty or timestamp is None
        """
        if not self.message or not self.message.strip():
            raise ValueError("Message cannot be empty")
        if self.timestamp is None:
            raise ValueError("Timestamp cannot be None")
        return True
