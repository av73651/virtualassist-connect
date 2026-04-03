"""Incident manager domain enums."""

from enum import Enum


class CorrelationStatus(str, Enum):
    RESERVED = "RESERVED"
    DETECTED = "DETECTED"
    TRIAGING = "TRIAGING"
    ESCALATED = "ESCALATED"
    GRACE = "GRACE"


class Severity(str, Enum):
    SEV_1 = "SEV-1"
    SEV_2 = "SEV-2"
    SEV_3 = "SEV-3"


class RecoveryModel(str, Enum):
    """Classifies what needs to happen AFTER service restoration."""
    STATELESS = "stateless"
    REPLAY = "replay"
    REPROCESS = "reprocess"
    DATA_CORRECTION = "data-correction"
    BACKLOG_DRAIN = "backlog-drain"


class ResolutionOutcome(str, Enum):
    """Outcome of remediate_and_verify."""
    SUCCESS = "success"
    NO_REMEDIATION = "no-remediation"
    REMEDIATION_FAILED = "remediation-failed"
    VERIFICATION_FAILED = "verification-failed"


class RecoveryStatus(str, Enum):
    """Status of post-resolution recovery workflow trigger."""
    NOT_REQUIRED = "not-required"
    TRIGGERED = "triggered"
    FAILED = "failed"
    NOT_CONFIGURED = "not-configured"
    DELTA_REPORTED = "delta-reported"


class EscalationReason(str, Enum):
    """Reason for escalation, published in EscalationRequired events."""
    VERIFICATION_FAILED = "verification-failed"
    NO_REMEDIATION = "no-remediation-available"
    REMEDIATION_FAILED = "remediation-failed"
    INCIDENT_STORM = "incident-storm"
    GRACE_RECURRENCE = "grace-period-recurrence"
    TRIAGE_TIMEOUT = "triage-timeout"
