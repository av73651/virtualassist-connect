"""Tests for incident manager model layer — AlarmEvent, CorrelationRecord, IncidentConfig."""

import json
import os
import pytest
from datetime import datetime, timezone, timedelta
from freezegun import freeze_time

from src.models.alarm_event import AlarmEvent
from src.models.correlation_record import CorrelationRecord
from src.models.enums import CorrelationStatus, Severity, RecoveryModel
from src.models.config import IncidentConfig
from src.models.exceptions import AlarmParsingError, DuplicateIncidentError, IncidentError


# ------------------------------------------------------------------ #
# AlarmEvent Parsing
# ------------------------------------------------------------------ #

class TestAlarmEventParsing:
    """AlarmEvent.from_sns_message parses correctly."""

    def test_alarm_event_metadata_extraction(self, sns_alarm_message, severity_mapping):
        """Service, alarm_type, stage extracted from alarm name."""
        event = AlarmEvent.from_sns_message(sns_alarm_message, severity_mapping)

        assert event.service == "calculator"
        assert event.alarm_type == "error-rate"
        assert event.stage == "prod"
        assert event.incident_key == "calculator-error-rate-prod"

    def test_alarm_event_severity_classification(self, sns_alarm_message, severity_mapping):
        """Severity classified from severity_mapping."""
        event = AlarmEvent.from_sns_message(sns_alarm_message, severity_mapping)

        assert event.severity == Severity.SEV_1

    def test_alarm_event_recovery_model_classification(self, sns_alarm_message, severity_mapping):
        """Recovery model extracted from severity_mapping."""
        event = AlarmEvent.from_sns_message(sns_alarm_message, severity_mapping)

        assert event.recovery_model == "stateless"

    def test_alarm_event_state_flags(self, sns_alarm_message, severity_mapping):
        """is_alarm and is_recovery flags correct."""
        event = AlarmEvent.from_sns_message(sns_alarm_message, severity_mapping)

        assert event.is_alarm is True
        assert event.is_recovery is False

    def test_recovery_event_state_flags(self, sns_recovery_message, severity_mapping):
        """OK state transition sets is_recovery=True."""
        event = AlarmEvent.from_sns_message(sns_recovery_message, severity_mapping)

        assert event.is_alarm is False
        assert event.is_recovery is True

    def test_alarm_event_from_json_string(self, sns_alarm_message, severity_mapping):
        """from_sns_message accepts JSON string input."""
        event = AlarmEvent.from_sns_message(
            json.dumps(sns_alarm_message), severity_mapping
        )

        assert event.service == "calculator"
        assert event.severity == Severity.SEV_1

    def test_alarm_event_frozen(self, sns_alarm_message, severity_mapping):
        """AlarmEvent is immutable (frozen dataclass)."""
        event = AlarmEvent.from_sns_message(sns_alarm_message, severity_mapping)

        with pytest.raises(AttributeError):
            event.service = "modified"

    def test_alarm_arn_extracted(self, sns_alarm_message, severity_mapping):
        """AlarmArn extracted from SNS message."""
        event = AlarmEvent.from_sns_message(sns_alarm_message, severity_mapping)

        assert event.alarm_arn == "arn:aws:cloudwatch:us-west-2:320644769527:alarm:calculator-high-error-rate-prod"

    def test_trigger_dimensions_extracted(self, sns_alarm_message, severity_mapping):
        """Trigger dimensions converted from [{name,value}] to dict."""
        event = AlarmEvent.from_sns_message(sns_alarm_message, severity_mapping)

        assert event.trigger_dimensions == {"FunctionName": "calculator-api-prod"}

    def test_function_name_from_dimensions(self, sns_alarm_message, severity_mapping):
        """function_name property returns FunctionName from trigger dimensions."""
        event = AlarmEvent.from_sns_message(sns_alarm_message, severity_mapping)

        assert event.function_name == "calculator-api-prod"

    def test_log_group_from_function_name(self, sns_alarm_message, severity_mapping):
        """log_group property returns /aws/lambda/{function_name}."""
        event = AlarmEvent.from_sns_message(sns_alarm_message, severity_mapping)

        assert event.log_group == "/aws/lambda/calculator-api-prod"

    def test_function_name_none_when_no_dimensions(self, severity_mapping):
        """function_name is None when Trigger has no FunctionName dimension."""
        message = {
            "AlarmName": "payments-high-queue-backlog-prod",
            "AlarmDescription": "Queue depth",
            "NewStateValue": "ALARM",
            "OldStateValue": "OK",
            "NewStateReason": "Threshold crossed",
            "StateChangeTime": "2026-03-30T12:00:00.000+0000",
            "Region": "US West (Oregon)",
            "AWSAccountId": "320644769527",
            "Trigger": {
                "Dimensions": [{"name": "QueueName", "value": "payments-queue-prod"}],
            },
        }
        event = AlarmEvent.from_sns_message(message, severity_mapping)

        assert event.function_name is None
        assert event.log_group is None
        assert event.trigger_dimensions == {"QueueName": "payments-queue-prod"}

    def test_missing_trigger_defaults_to_empty_dimensions(self, severity_mapping):
        """Missing Trigger field defaults to empty dimensions dict."""
        message = {
            "AlarmName": "calculator-high-error-rate-prod",
            "AlarmDescription": "Error rate",
            "NewStateValue": "ALARM",
            "OldStateValue": "OK",
            "NewStateReason": "Threshold crossed",
            "StateChangeTime": "2026-03-30T12:00:00.000+0000",
            "Region": "US West (Oregon)",
            "AWSAccountId": "320644769527",
        }
        event = AlarmEvent.from_sns_message(message, severity_mapping)

        assert event.trigger_dimensions == {}
        assert event.alarm_arn == ""
        assert event.function_name is None

    def test_unknown_alarm_type_defaults_to_sev3(self, severity_mapping):
        """Unknown alarm type defaults to SEV-3 stateless."""
        message = {
            "AlarmName": "calculator-high-unknown-type-prod",
            "AlarmDescription": "Unknown",
            "NewStateValue": "ALARM",
            "OldStateValue": "OK",
            "NewStateReason": "Threshold crossed",
            "StateChangeTime": "2026-03-30T12:00:00.000+0000",
            "Region": "US West (Oregon)",
            "AWSAccountId": "320644769527",
        }
        event = AlarmEvent.from_sns_message(message, severity_mapping)

        assert event.severity == Severity.SEV_3
        assert event.recovery_model == "stateless"


# ------------------------------------------------------------------ #
# AlarmEvent Recovery Model Classification
# ------------------------------------------------------------------ #

class TestAlarmEventRecoveryModel:
    """severity_mapping returns {severity, recovery_model} correctly."""

    def test_queue_backlog_replay_model(self, sns_queue_backlog_message, severity_mapping):
        """queue-backlog maps to SEV-2, replay."""
        event = AlarmEvent.from_sns_message(sns_queue_backlog_message, severity_mapping)

        assert event.severity == Severity.SEV_2
        assert event.recovery_model == "replay"

    def test_batch_failure_reprocess_model(self, severity_mapping):
        """batch-failure maps to SEV-1, reprocess."""
        message = {
            "AlarmName": "settlement-high-batch-failure-prod",
            "AlarmDescription": "Batch failed",
            "NewStateValue": "ALARM",
            "OldStateValue": "OK",
            "NewStateReason": "Batch job failed",
            "StateChangeTime": "2026-03-30T12:00:00.000+0000",
            "Region": "US West (Oregon)",
            "AWSAccountId": "320644769527",
        }
        event = AlarmEvent.from_sns_message(message, severity_mapping)

        assert event.severity == Severity.SEV_1
        assert event.recovery_model == "reprocess"

    def test_data_integrity_correction_model(self, severity_mapping):
        """data-integrity maps to SEV-1, data-correction."""
        message = {
            "AlarmName": "payments-high-data-integrity-prod",
            "AlarmDescription": "Duplicate transactions",
            "NewStateValue": "ALARM",
            "OldStateValue": "OK",
            "NewStateReason": "Duplicates detected",
            "StateChangeTime": "2026-03-30T12:00:00.000+0000",
            "Region": "US West (Oregon)",
            "AWSAccountId": "320644769527",
        }
        event = AlarmEvent.from_sns_message(message, severity_mapping)

        assert event.severity == Severity.SEV_1
        assert event.recovery_model == "data-correction"


# ------------------------------------------------------------------ #
# Golden Signals — Saturation, Traffic, Cold Start
# ------------------------------------------------------------------ #

class TestGoldenSignalsAlarmTypes:
    """New alarm types for saturation, traffic drops, and cold starts."""

    def test_traffic_drop_low_direction(self, sns_traffic_drop_message, severity_mapping):
        """Low-direction alarm: traffic drop parsed correctly."""
        event = AlarmEvent.from_sns_message(sns_traffic_drop_message, severity_mapping)

        assert event.service == "calculator"
        assert event.alarm_type == "traffic"
        assert event.stage == "prod"
        assert event.severity == Severity.SEV_1
        assert event.recovery_model == "stateless"
        assert event.incident_key == "calculator-traffic-prod"

    def test_throttle_saturation(self, sns_throttle_message, severity_mapping):
        """Lambda throttle alarm parsed correctly."""
        event = AlarmEvent.from_sns_message(sns_throttle_message, severity_mapping)

        assert event.service == "calculator"
        assert event.alarm_type == "throttle"
        assert event.stage == "prod"
        assert event.severity == Severity.SEV_2
        assert event.recovery_model == "backlog-drain"
        assert event.incident_key == "calculator-throttle-prod"

    def test_cold_start_rate(self, sns_cold_start_message, severity_mapping):
        """Cold start rate alarm parsed correctly."""
        event = AlarmEvent.from_sns_message(sns_cold_start_message, severity_mapping)

        assert event.service == "calculator"
        assert event.alarm_type == "cold-start-rate"
        assert event.stage == "prod"
        assert event.severity == Severity.SEV_2
        assert event.recovery_model == "stateless"
        assert event.incident_key == "calculator-cold-start-rate-prod"

    def test_concurrency_exhaustion(self, severity_mapping):
        """Concurrency alarm maps to SEV-1, backlog-drain."""
        message = {
            "AlarmName": "calculator-high-concurrency-prod",
            "AlarmDescription": "Concurrency > 80% of limit",
            "NewStateValue": "ALARM",
            "OldStateValue": "OK",
            "NewStateReason": "ConcurrentExecutions > 800",
            "StateChangeTime": "2026-03-30T12:00:00.000+0000",
            "Region": "US West (Oregon)",
            "AWSAccountId": "320644769527",
        }
        event = AlarmEvent.from_sns_message(message, severity_mapping)

        assert event.severity == Severity.SEV_1
        assert event.recovery_model == "backlog-drain"

    def test_dynamo_throttle(self, severity_mapping):
        """DynamoDB throttle alarm maps to SEV-2, replay."""
        message = {
            "AlarmName": "payments-high-dynamo-throttle-prod",
            "AlarmDescription": "DynamoDB throttled requests > threshold",
            "NewStateValue": "ALARM",
            "OldStateValue": "OK",
            "NewStateReason": "ThrottledRequests > 10",
            "StateChangeTime": "2026-03-30T12:00:00.000+0000",
            "Region": "US West (Oregon)",
            "AWSAccountId": "320644769527",
            "Trigger": {
                "Dimensions": [{"name": "TableName", "value": "payments-table-prod"}],
            },
        }
        event = AlarmEvent.from_sns_message(message, severity_mapping)

        assert event.severity == Severity.SEV_2
        assert event.recovery_model == "replay"
        assert event.alarm_type == "dynamo-throttle"
        assert event.function_name is None
        assert event.trigger_dimensions == {"TableName": "payments-table-prod"}

    def test_low_direction_preserves_function_name(self, sns_traffic_drop_message, severity_mapping):
        """Low-direction alarms still extract trigger dimensions."""
        event = AlarmEvent.from_sns_message(sns_traffic_drop_message, severity_mapping)

        assert event.function_name == "calculator-api-prod"
        assert event.log_group == "/aws/lambda/calculator-api-prod"


# ------------------------------------------------------------------ #
# AlarmEvent Invalid Alarm Name
# ------------------------------------------------------------------ #

class TestAlarmEventInvalidName:
    """Malformed alarm names raise AlarmParsingError."""

    def test_malformed_alarm_name(self, severity_mapping):
        """Alarm name without 'high' pattern raises AlarmParsingError."""
        message = {
            "AlarmName": "malformed-alarm-name",
            "NewStateValue": "ALARM",
            "OldStateValue": "OK",
        }

        with pytest.raises(AlarmParsingError):
            AlarmEvent.from_sns_message(message, severity_mapping)

    def test_empty_alarm_name(self, severity_mapping):
        """Empty alarm name raises AlarmParsingError."""
        message = {"AlarmName": "", "NewStateValue": "ALARM"}

        with pytest.raises(AlarmParsingError):
            AlarmEvent.from_sns_message(message, severity_mapping)

    def test_alarm_parsing_error_is_incident_error(self):
        """AlarmParsingError is a subclass of IncidentError."""
        assert issubclass(AlarmParsingError, IncidentError)

    def test_duplicate_incident_error_is_incident_error(self):
        """DuplicateIncidentError is a subclass of IncidentError."""
        assert issubclass(DuplicateIncidentError, IncidentError)


# ------------------------------------------------------------------ #
# CorrelationRecord Reserve Factory
# ------------------------------------------------------------------ #

class TestCorrelationRecordReserve:
    """CorrelationRecord.reserve creates correct placeholder."""

    @freeze_time("2026-03-30T12:00:00Z")
    def test_reserve_creates_reserved_record(self):
        """Reserve factory creates RESERVED record with correct fields."""
        now = datetime(2026, 3, 30, 12, 0, 0, tzinfo=timezone.utc)
        record = CorrelationRecord.reserve("calculator-error-rate-prod", "SEV-1", now=now)

        assert record.incident_key == "calculator-error-rate-prod"
        assert record.jira_ticket_id is None
        assert record.severity == "SEV-1"
        assert record.status == CorrelationStatus.RESERVED
        assert record.created_at == now

    @freeze_time("2026-03-30T12:00:00Z")
    def test_reserve_ttl_is_24_hours(self):
        """TTL set to created_at + 24 hours."""
        now = datetime(2026, 3, 30, 12, 0, 0, tzinfo=timezone.utc)
        expected_ttl = int((now + timedelta(hours=24)).timestamp())

        record = CorrelationRecord.reserve("calculator-error-rate-prod", "SEV-1", now=now)

        assert record.ttl == expected_ttl

    def test_associate_jira_ticket_transitions_to_detected(self, reserved_record):
        """associate_jira_ticket updates jira_ticket_id and status to DETECTED."""
        detected = reserved_record.associate_jira_ticket("INC-142")

        assert detected.jira_ticket_id == "INC-142"
        assert detected.status == CorrelationStatus.DETECTED
        assert detected.incident_key == reserved_record.incident_key
        assert detected.severity == reserved_record.severity
        assert detected.ttl == reserved_record.ttl


# ------------------------------------------------------------------ #
# CorrelationRecord to_grace Transition
# ------------------------------------------------------------------ #

class TestCorrelationRecordGrace:
    """to_grace transitions correctly."""

    def test_to_grace_status_and_ttl(self, detected_record):
        """GRACE record has correct status and TTL (resolved_at + 15min)."""
        resolved_at = datetime(2026, 3, 30, 14, 0, 0, tzinfo=timezone.utc)
        grace = detected_record.to_grace(resolved_at, 900)

        assert grace.status == CorrelationStatus.GRACE
        expected_ttl = int((resolved_at + timedelta(seconds=900)).timestamp())
        assert grace.ttl == expected_ttl

    def test_to_grace_preserves_ticket_id(self, detected_record):
        """GRACE record preserves jira_ticket_id."""
        resolved_at = datetime(2026, 3, 30, 14, 0, 0, tzinfo=timezone.utc)
        grace = detected_record.to_grace(resolved_at, 900)

        assert grace.jira_ticket_id == "INC-142"


# ------------------------------------------------------------------ #
# CorrelationRecord DynamoDB Roundtrip
# ------------------------------------------------------------------ #

class TestCorrelationRecordRoundtrip:
    """to_dynamodb_item / from_dynamodb_item roundtrip."""

    def test_roundtrip_detected_record(self, detected_record):
        """Roundtrip preserves all fields for DETECTED record."""
        item = detected_record.to_dynamodb_item()
        restored = CorrelationRecord.from_dynamodb_item(item)

        assert restored.incident_key == detected_record.incident_key
        assert restored.jira_ticket_id == detected_record.jira_ticket_id
        assert restored.severity == detected_record.severity
        assert restored.status == detected_record.status
        assert restored.created_at == detected_record.created_at
        assert restored.ttl == detected_record.ttl

    def test_roundtrip_reserved_record(self, reserved_record):
        """Roundtrip preserves None jira_ticket_id for RESERVED record."""
        item = reserved_record.to_dynamodb_item()
        restored = CorrelationRecord.from_dynamodb_item(item)

        assert restored.jira_ticket_id is None
        assert restored.status == CorrelationStatus.RESERVED

    def test_roundtrip_grace_record(self, grace_record):
        """Roundtrip preserves GRACE status."""
        item = grace_record.to_dynamodb_item()
        restored = CorrelationRecord.from_dynamodb_item(item)

        assert restored.status == CorrelationStatus.GRACE

    def test_dynamodb_item_includes_gsi_pk(self, detected_record):
        """DynamoDB item includes gsi_pk='ALL' for storm detection GSI."""
        item = detected_record.to_dynamodb_item()

        assert item["gsi_pk"] == "ALL"


# ------------------------------------------------------------------ #
# IncidentConfig Load
# ------------------------------------------------------------------ #

class TestIncidentConfigLoad:
    """IncidentConfig loads from JSON correctly."""

    def test_config_load_from_file(self):
        """Config loaded from incident_config.json with all fields."""
        config_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "incident_config.json"
        )
        config = IncidentConfig.load(config_path)

        assert config.storm_threshold == 5
        assert config.storm_window_seconds == 120
        assert config.grace_period_seconds == 900
        assert config.reservation_timeout_seconds == 180
        assert config.triage_timeout_seconds == 120
        assert config.correlation_ttl_hours == 24
        assert config.log_analysis_window_minutes == 15
        assert config.max_log_events == 500

    def test_config_severity_mapping(self):
        """severity_mapping has correct structure."""
        config_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "incident_config.json"
        )
        config = IncidentConfig.load(config_path)

        assert "error-rate" in config.severity_mapping
        assert config.severity_mapping["error-rate"]["severity"] == "SEV-1"
        assert config.severity_mapping["error-rate"]["recovery_model"] == "stateless"
        assert config.severity_mapping["queue-backlog"]["recovery_model"] == "replay"

    def test_config_recovery_catalog(self):
        """recovery_catalog loaded with correct entries."""
        config_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "incident_config.json"
        )
        config = IncidentConfig.load(config_path)

        assert "replay" in config.recovery_catalog
        assert config.recovery_catalog["replay"]["type"] == "step_function"
        assert "backlog-drain" in config.recovery_catalog
        assert config.recovery_catalog["backlog-drain"]["type"] == "lambda"

    def test_config_is_frozen(self):
        """IncidentConfig is immutable (frozen dataclass)."""
        config_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "incident_config.json"
        )
        config = IncidentConfig.load(config_path)

        with pytest.raises(AttributeError):
            config.storm_threshold = 999

    def test_config_remediation_catalog(self):
        """remediation_catalog loaded with correct entries."""
        config_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "incident_config.json"
        )
        config = IncidentConfig.load(config_path)

        assert "lambda" in config.remediation_catalog
        assert "bad-deployment" in config.remediation_catalog["lambda"]
        assert config.remediation_catalog["lambda"]["bad-deployment"]["action"] == "lambda-version-rollback"

    def test_config_classification_rules(self):
        """classification_rules loaded as list of dicts."""
        config_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "incident_config.json"
        )
        config = IncidentConfig.load(config_path)

        assert len(config.classification_rules) == 11
        assert config.classification_rules[0]["pattern"] == "import_or_syntax_error"
        assert config.classification_rules[0]["classification"] == "bad-deployment"


# ------------------------------------------------------------------ #
# Enum tests
# ------------------------------------------------------------------ #

class TestEnums:
    """Enum values and membership."""

    def test_correlation_status_values(self):
        """All 5 status values exist."""
        assert len(CorrelationStatus) == 5
        assert CorrelationStatus.RESERVED.value == "RESERVED"
        assert CorrelationStatus.GRACE.value == "GRACE"

    def test_severity_values(self):
        """All 3 severity values exist."""
        assert len(Severity) == 3
        assert Severity.SEV_1.value == "SEV-1"

    def test_recovery_model_values(self):
        """All 5 recovery model values exist."""
        assert len(RecoveryModel) == 5
        assert RecoveryModel.STATELESS.value == "stateless"
        assert RecoveryModel.DATA_CORRECTION.value == "data-correction"

    def test_enums_are_string_enums(self):
        """All enums are str-based for JSON serialization."""
        assert isinstance(CorrelationStatus.RESERVED, str)
        assert isinstance(Severity.SEV_1, str)
        assert isinstance(RecoveryModel.STATELESS, str)
