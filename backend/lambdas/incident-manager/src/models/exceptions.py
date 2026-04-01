"""Incident manager domain exceptions."""


class IncidentError(Exception):
    """Base exception for incident domain errors."""


class DuplicateIncidentError(IncidentError):
    """Conditional write detected existing active incident."""


class AlarmParsingError(IncidentError):
    """Alarm name doesn't match expected convention."""
