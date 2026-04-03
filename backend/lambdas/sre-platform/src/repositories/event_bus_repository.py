"""EventBusRepository — EventBridge incident lifecycle events.

All observability concerns (tracing, metrics, logging) handled by @observe decorator."""

import json

import boto3

from shared.middleware.observability import observe

from src.models.config import IncidentConfig


class EventBusRepository:
    """EventBridge — publish incident lifecycle events."""

    def __init__(
        self,
        config: IncidentConfig,
        event_bus_name: str = "default",
        eventbridge_client=None,
    ):
        self._config = config
        self._event_bus_name = event_bus_name
        self._eventbridge_client = eventbridge_client or boto3.client("events")

    @observe(operation="publish_incident_event", metric_prefix="eventbridge_publish")
    def publish_event(self, event_type: str, detail: dict) -> bool:
        """Publishes incident lifecycle event to EventBridge. Returns False on failure."""
        try:
            self._eventbridge_client.put_events(
                Entries=[
                    {
                        "Source": self._config.eventbridge_source,
                        "DetailType": event_type,
                        "Detail": json.dumps(detail),
                        "EventBusName": self._event_bus_name,
                    }
                ]
            )
            return True

        except Exception:
            return False
