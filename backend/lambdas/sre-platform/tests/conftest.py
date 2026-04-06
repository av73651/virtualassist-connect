"""Shared test fixtures for SRE Platform tests."""

import json
import pytest
import boto3
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone, timedelta

from moto import mock_aws

from src.models.alarm_event import AlarmEvent
from src.models.correlation_record import CorrelationRecord
from src.models.enums import CorrelationStatus, Severity, RecoveryModel
from src.models.config import IncidentConfig

# Mock @observe before importing CheckpointClient — tests don't need OTel infra
_mock_observe = MagicMock(side_effect=lambda **kwargs: lambda fn: fn)
with patch.dict("sys.modules", {"shared": MagicMock(), "shared.middleware": MagicMock(), "shared.middleware.observability": MagicMock(observe=_mock_observe)}):
    from src.checkpoint.client import CheckpointClient
    from src.repositories.checkpoint_repository import CheckpointRepository
    from src.services.delta_report_service import DeltaReportService


# ------------------------------------------------------------------ #
# Configuration
# ------------------------------------------------------------------ #

@pytest.fixture
def severity_mapping():
    """Standard severity mapping for testing."""
    return {
        "error-rate": {"severity": "SEV-1", "recovery_model": "stateless"},
        "latency": {"severity": "SEV-2", "recovery_model": "stateless"},
        "4xx-errors": {"severity": "SEV-3", "recovery_model": "stateless"},
        "queue-backlog": {"severity": "SEV-2", "recovery_model": "replay"},
        "batch-failure": {"severity": "SEV-1", "recovery_model": "reprocess"},
        "data-integrity": {"severity": "SEV-1", "recovery_model": "data-correction"},
        "throttle": {"severity": "SEV-2", "recovery_model": "backlog-drain"},
        "concurrency": {"severity": "SEV-1", "recovery_model": "backlog-drain"},
        "dynamo-throttle": {"severity": "SEV-2", "recovery_model": "replay"},
        "traffic": {"severity": "SEV-1", "recovery_model": "stateless"},
        "cold-start-rate": {"severity": "SEV-2", "recovery_model": "stateless"},
    }


@pytest.fixture
def incident_config():
    """Standard incident config for testing."""
    return IncidentConfig(
        # Jira integration
        jira_issue_type="Incident",
        jira_service_desk_id="2",
        jira_request_type_id="16",
        jira_transition_resolve="Done",
        jira_transition_investigate="Investigate",
        jira_labels_prefix=["incident", "automated"],
        jira_priority_map={"SEV-1": "Highest", "SEV-2": "High", "SEV-3": "Medium"},
        jira_http_timeout_seconds=30,
        # EventBridge / Lambda
        eventbridge_source="sre-platform",
        lambda_alias_name="live",
        lambda_memory_tiers=[128, 256, 512, 1024, 1536, 2048, 3008, 4096, 5120, 6144, 7168, 8192, 9216, 10240],
        # Operational tuning
        severity_mapping={
            "error-rate": {"severity": "SEV-1", "recovery_model": "stateless"},
            "latency": {"severity": "SEV-2", "recovery_model": "stateless"},
            "4xx-errors": {"severity": "SEV-3", "recovery_model": "stateless"},
            "queue-backlog": {"severity": "SEV-2", "recovery_model": "replay"},
            "batch-failure": {"severity": "SEV-1", "recovery_model": "reprocess"},
            "data-integrity": {"severity": "SEV-1", "recovery_model": "data-correction"},
            "throttle": {"severity": "SEV-2", "recovery_model": "backlog-drain"},
            "concurrency": {"severity": "SEV-1", "recovery_model": "backlog-drain"},
            "dynamo-throttle": {"severity": "SEV-2", "recovery_model": "replay"},
            "traffic": {"severity": "SEV-1", "recovery_model": "stateless"},
            "cold-start-rate": {"severity": "SEV-2", "recovery_model": "stateless"},
        },
        cool_off_seconds={"SEV-1": 30, "SEV-2": 60, "SEV-3": 120},
        verification_wait_seconds={"SEV-1": 60, "SEV-2": 90, "SEV-3": 120},
        grace_period_seconds=900,
        reservation_timeout_seconds=180,
        triage_timeout_seconds=120,
        log_analysis_window_minutes=15,
        max_log_events=500,
        correlation_ttl_hours=24,
        recovery_log_minutes=5,
        storm_window_seconds=120,
        storm_threshold=5,
        # Triage tuning
        verification_window_minutes=2,
        verification_error_threshold=5,
        max_sample_payloads=5,
        sample_payload_max_length=500,
        pattern_key_max_length=100,
        # Catalogs and rules
        remediation_catalog={
            "lambda": {
                "bad-deployment": {"action": "lambda-version-rollback"},
                "performance-degradation": {"action": "lambda-memory-increase"},
                "rate-limit": {"action": "increase-concurrency"},
            },
            "api-gateway": {
                "bad-deployment": {"action": "apigw-deployment-rollback"},
                "rate-limit": {"action": "apigw-throttle-increase"},
            },
            "elasticsearch": {
                "performance-degradation": {"action": "opensearch-scale-up"},
                "storage-exhaustion": {"action": "opensearch-storage-increase"},
            },
        },
        recovery_catalog={
            "replay": {"type": "step_function", "workflow_arn_env": "REPLAY_DLQ_WORKFLOW_ARN"},
            "reprocess": {"type": "step_function", "workflow_arn_env": "REPROCESS_BATCH_WORKFLOW_ARN", "checkpoint_aware": True},
            "data-correction": {"type": "step_function", "workflow_arn_env": "RECONCILIATION_WORKFLOW_ARN"},
            "backlog-drain": {"type": "lambda", "function_name_env": "BACKLOG_DRAIN_FUNCTION_NAME"},
        },
        classification_rules=[
            {"pattern": "import_or_syntax_error", "classification": "bad-deployment", "confidence": "high"},
            {"pattern": "single_error_dominant", "classification": "specific-bug", "confidence": "high"},
            {"pattern": "throttling_errors", "classification": "rate-limit", "confidence": "high"},
        ],
        # Bedrock Knowledge Base (disabled in tests by default)
        bedrock_knowledge_base_id="",
        bedrock_model_arn="",
    )


# ------------------------------------------------------------------ #
# Datetime
# ------------------------------------------------------------------ #

@pytest.fixture
def fixed_now():
    """Fixed datetime for deterministic tests."""
    return datetime(2026, 3, 30, 12, 0, 0, tzinfo=timezone.utc)


# ------------------------------------------------------------------ #
# SNS message fixtures
# ------------------------------------------------------------------ #

@pytest.fixture
def sns_alarm_message():
    """Raw CloudWatch Alarm SNS message dict (ALARM state)."""
    return {
        "AlarmName": "calculator-high-error-rate-prod",
        "AlarmDescription": "Error rate exceeds threshold",
        "NewStateValue": "ALARM",
        "OldStateValue": "OK",
        "NewStateReason": "Threshold crossed",
        "StateChangeTime": "2026-03-30T12:00:00.000+0000",
        "Region": "US West (Oregon)",
        "AWSAccountId": "320644769527",
        "AlarmArn": "arn:aws:cloudwatch:us-west-2:320644769527:alarm:calculator-high-error-rate-prod",
        "Trigger": {
            "MetricName": "Errors",
            "Namespace": "AWS/Lambda",
            "Dimensions": [
                {"name": "FunctionName", "value": "calculator-api-prod"}
            ],
        },
    }


@pytest.fixture
def sns_recovery_message():
    """Raw CloudWatch Alarm SNS message dict (OK state)."""
    return {
        "AlarmName": "calculator-high-error-rate-prod",
        "AlarmDescription": "Error rate exceeds threshold",
        "NewStateValue": "OK",
        "OldStateValue": "ALARM",
        "NewStateReason": "Threshold returned to normal",
        "StateChangeTime": "2026-03-30T12:30:00.000+0000",
        "Region": "US West (Oregon)",
        "AWSAccountId": "320644769527",
        "AlarmArn": "arn:aws:cloudwatch:us-west-2:320644769527:alarm:calculator-high-error-rate-prod",
        "Trigger": {
            "MetricName": "Errors",
            "Namespace": "AWS/Lambda",
            "Dimensions": [
                {"name": "FunctionName", "value": "calculator-api-prod"}
            ],
        },
    }


@pytest.fixture
def sns_queue_backlog_message():
    """Raw CloudWatch Alarm SNS message for queue-backlog (replay recovery)."""
    return {
        "AlarmName": "payments-high-queue-backlog-prod",
        "AlarmDescription": "SQS queue depth exceeds threshold",
        "NewStateValue": "ALARM",
        "OldStateValue": "OK",
        "NewStateReason": "Queue depth > 50000",
        "StateChangeTime": "2026-03-30T12:00:00.000+0000",
        "Region": "US West (Oregon)",
        "AWSAccountId": "320644769527",
        "AlarmArn": "arn:aws:cloudwatch:us-west-2:320644769527:alarm:payments-high-queue-backlog-prod",
        "Trigger": {
            "MetricName": "ApproximateNumberOfMessagesVisible",
            "Namespace": "AWS/SQS",
            "Dimensions": [
                {"name": "QueueName", "value": "payments-queue-prod"}
            ],
        },
    }


@pytest.fixture
def sns_traffic_drop_message():
    """Raw CloudWatch Alarm SNS message for traffic drop (low direction)."""
    return {
        "AlarmName": "calculator-low-traffic-prod",
        "AlarmDescription": "Lambda invocations dropped below threshold",
        "NewStateValue": "ALARM",
        "OldStateValue": "OK",
        "NewStateReason": "Invocations < 10 for 5 minutes",
        "StateChangeTime": "2026-03-30T12:00:00.000+0000",
        "Region": "US West (Oregon)",
        "AWSAccountId": "320644769527",
        "AlarmArn": "arn:aws:cloudwatch:us-west-2:320644769527:alarm:calculator-low-traffic-prod",
        "Trigger": {
            "MetricName": "Invocations",
            "Namespace": "AWS/Lambda",
            "Dimensions": [
                {"name": "FunctionName", "value": "calculator-api-prod"}
            ],
        },
    }


@pytest.fixture
def sns_throttle_message():
    """Raw CloudWatch Alarm SNS message for Lambda throttle (saturation)."""
    return {
        "AlarmName": "calculator-high-throttle-prod",
        "AlarmDescription": "Lambda throttles exceeded threshold",
        "NewStateValue": "ALARM",
        "OldStateValue": "OK",
        "NewStateReason": "Throttles > 50",
        "StateChangeTime": "2026-03-30T12:00:00.000+0000",
        "Region": "US West (Oregon)",
        "AWSAccountId": "320644769527",
        "AlarmArn": "arn:aws:cloudwatch:us-west-2:320644769527:alarm:calculator-high-throttle-prod",
        "Trigger": {
            "MetricName": "Throttles",
            "Namespace": "AWS/Lambda",
            "Dimensions": [
                {"name": "FunctionName", "value": "calculator-api-prod"}
            ],
        },
    }


@pytest.fixture
def sns_cold_start_message():
    """Raw CloudWatch Alarm SNS message for cold start rate."""
    return {
        "AlarmName": "calculator-high-cold-start-rate-prod",
        "AlarmDescription": "Cold start rate exceeds threshold",
        "NewStateValue": "ALARM",
        "OldStateValue": "OK",
        "NewStateReason": "ColdStartRate > 30%",
        "StateChangeTime": "2026-03-30T12:00:00.000+0000",
        "Region": "US West (Oregon)",
        "AWSAccountId": "320644769527",
        "AlarmArn": "arn:aws:cloudwatch:us-west-2:320644769527:alarm:calculator-high-cold-start-rate-prod",
        "Trigger": {
            "MetricName": "ColdStartRate",
            "Namespace": "Custom/Lambda",
            "Dimensions": [
                {"name": "FunctionName", "value": "calculator-api-prod"}
            ],
        },
    }


# ------------------------------------------------------------------ #
# AlarmEvent fixtures
# ------------------------------------------------------------------ #

@pytest.fixture
def alarm_event_sev1(fixed_now):
    """SEV-1 error-rate alarm (stateless recovery)."""
    return AlarmEvent(
        alarm_name="calculator-high-error-rate-prod",
        alarm_description="Error rate exceeds threshold",
        new_state="ALARM",
        old_state="OK",
        reason="Threshold crossed",
        state_change_time=fixed_now,
        region="us-west-2",
        account_id="320644769527",
        alarm_arn="arn:aws:cloudwatch:us-west-2:320644769527:alarm:calculator-high-error-rate-prod",
        trigger_dimensions={"FunctionName": "calculator-api-prod"},
        service="calculator",
        alarm_type="error-rate",
        stage="prod",
        severity=Severity.SEV_1,
        recovery_model="stateless",
        service_type="lambda",
    )


@pytest.fixture
def alarm_event_queue_backlog(fixed_now):
    """SEV-2 queue-backlog alarm (replay recovery)."""
    return AlarmEvent(
        alarm_name="payments-high-queue-backlog-prod",
        alarm_description="SQS queue depth exceeds threshold",
        new_state="ALARM",
        old_state="OK",
        reason="Queue depth > 50000",
        state_change_time=fixed_now,
        region="us-west-2",
        account_id="320644769527",
        alarm_arn="arn:aws:cloudwatch:us-west-2:320644769527:alarm:payments-high-queue-backlog-prod",
        trigger_dimensions={"QueueName": "payments-queue-prod"},
        service="payments",
        alarm_type="queue-backlog",
        stage="prod",
        severity=Severity.SEV_2,
        recovery_model="replay",
        service_type="unknown",
    )


@pytest.fixture
def recovery_event(fixed_now):
    """Recovery event (OK state transition)."""
    return AlarmEvent(
        alarm_name="calculator-high-error-rate-prod",
        alarm_description="Error rate exceeds threshold",
        new_state="OK",
        old_state="ALARM",
        reason="Threshold returned to normal",
        state_change_time=fixed_now,
        region="us-west-2",
        account_id="320644769527",
        alarm_arn="arn:aws:cloudwatch:us-west-2:320644769527:alarm:calculator-high-error-rate-prod",
        trigger_dimensions={"FunctionName": "calculator-api-prod"},
        service="calculator",
        alarm_type="error-rate",
        stage="prod",
        severity=Severity.SEV_1,
        recovery_model="stateless",
        service_type="lambda",
    )


# ------------------------------------------------------------------ #
# CorrelationRecord fixtures
# ------------------------------------------------------------------ #

@pytest.fixture
def reserved_record(fixed_now):
    """DynamoDB record in RESERVED state."""
    return CorrelationRecord(
        incident_key="calculator-error-rate-prod",
        jira_ticket_id=None,
        severity="SEV-1",
        status=CorrelationStatus.RESERVED,
        created_at=fixed_now,
        ttl=int((fixed_now + timedelta(hours=24)).timestamp()),
    )


@pytest.fixture
def detected_record(fixed_now):
    """DynamoDB record in DETECTED state."""
    return CorrelationRecord(
        incident_key="calculator-error-rate-prod",
        jira_ticket_id="INC-142",
        severity="SEV-1",
        status=CorrelationStatus.DETECTED,
        created_at=fixed_now,
        ttl=int((fixed_now + timedelta(hours=24)).timestamp()),
    )


@pytest.fixture
def grace_record(fixed_now):
    """DynamoDB record in GRACE state."""
    return CorrelationRecord(
        incident_key="calculator-error-rate-prod",
        jira_ticket_id="INC-142",
        severity="SEV-1",
        status=CorrelationStatus.GRACE,
        created_at=fixed_now,
        ttl=int((fixed_now + timedelta(minutes=15)).timestamp()),
    )


# ------------------------------------------------------------------ #
# SNS Event fixtures (Lambda event format)
# ------------------------------------------------------------------ #

@pytest.fixture
def sns_alarm_event(sns_alarm_message):
    """Full SNS Lambda event wrapping a CloudWatch Alarm notification."""
    return {
        "Records": [{
            "Sns": {
                "Message": json.dumps(sns_alarm_message)
            }
        }]
    }


@pytest.fixture
def sns_recovery_event(sns_recovery_message):
    """Full SNS Lambda event wrapping a CloudWatch Alarm OK notification."""
    return {
        "Records": [{
            "Sns": {
                "Message": json.dumps(sns_recovery_message)
            }
        }]
    }


# ------------------------------------------------------------------ #
# EventBridge Event fixtures
# ------------------------------------------------------------------ #

@pytest.fixture
def incident_created_event():
    """EventBridge IncidentCreated event for Triage Lambda."""
    return {
        "source": "sre-platform",
        "detail-type": "IncidentCreated",
        "detail": {
            "incident_key": "calculator-error-rate-prod",
            "jira_ticket_id": "INC-142",
            "service": "calculator",
            "service_type": "lambda",
            "function_name": "calculator-api-prod",
            "alarm_name": "calculator-high-error-rate-prod",
            "log_group": "/aws/lambda/calculator-api-prod",
            "stage": "prod",
            "severity": "SEV-1",
            "recovery_model": "stateless",
            "storm_detected": False,
            "timestamp": "2026-03-30T12:00:00Z",
        },
    }


@pytest.fixture
def escalation_required_event():
    """EventBridge EscalationRequired event for Escalation Lambda."""
    return {
        "source": "sre-platform",
        "detail-type": "EscalationRequired",
        "detail": {
            "incident_key": "calculator-error-rate-prod",
            "jira_ticket_id": "INC-142",
            "service": "calculator",
            "function_name": "calculator-api-prod",
            "stage": "prod",
            "severity": "SEV-1",
            "reason": "verification-failed",
            "root_cause": "",
            "timestamp": "2026-03-30T12:10:00Z",
        },
    }


# ------------------------------------------------------------------ #
# Mock repositories
# ------------------------------------------------------------------ #

@pytest.fixture
def mock_correlation_repo():
    """Mock CorrelationRepository."""
    repo = Mock()
    repo.get.return_value = None
    repo.reserve.return_value = True
    repo.update.return_value = None
    repo.delete.return_value = None
    repo.count_recent.return_value = 0
    return repo


@pytest.fixture
def mock_observability_repo():
    """Mock ObservabilityRepository."""
    repo = Mock()
    repo.get_alarm_state.return_value = "ALARM"
    repo.get_state_change_time.return_value = datetime(2026, 3, 30, 12, 0, 0, tzinfo=timezone.utc)
    repo.collect_errors.return_value = [{"message": "DivisionByZeroError", "timestamp": "2026-03-30T12:00:00Z"}]
    repo.collect_recent.return_value = []
    return repo


@pytest.fixture
def mock_ticketing_repo():
    """Mock TicketingRepository."""
    repo = Mock()
    repo.create_jira_ticket.return_value = "INC-142"
    repo.add_jira_comment.return_value = True
    repo.add_jira_comment_adf.return_value = True
    repo.attach_jira_file.return_value = True
    repo.transition_jira_ticket.return_value = True
    return repo


@pytest.fixture
def mock_event_bus_repo():
    """Mock EventBusRepository."""
    repo = Mock()
    repo.publish_event.return_value = True
    return repo


@pytest.fixture
def mock_remediation_repo():
    """Mock RemediationRepository."""
    repo = Mock()
    repo.rollback_lambda_version.return_value = {"status": "success"}
    repo.increase_lambda_memory.return_value = {"status": "success"}
    repo.increase_concurrency.return_value = {"status": "success"}
    repo.rollback_apigw_deployment.return_value = {"status": "success"}
    repo.update_apigw_throttle.return_value = {"status": "success"}
    repo.scale_opensearch_domain.return_value = {"status": "success"}
    repo.increase_opensearch_storage.return_value = {"status": "success"}
    return repo


@pytest.fixture
def mock_notification_repo():
    """Mock NotificationRepository."""
    repo = Mock()
    repo.notify_engineer.return_value = True
    return repo


@pytest.fixture
def mock_recovery_repo():
    """Mock RecoveryRepository."""
    repo = Mock()
    repo.trigger_step_function.return_value = "arn:aws:states:us-west-2:320644769527:execution:ReplayDLQ:exec-123"
    repo.trigger_recovery_lambda.return_value = {"StatusCode": 202}
    return repo


@pytest.fixture
def mock_log_analysis_service():
    """Mock LogAnalysisService."""
    service = Mock()
    service.analyze_errors.return_value = {
        "error_patterns": {"DivisionByZeroError": 1},
        "error_count": 1,
        "unique_errors": 1,
        "sample_payloads": ["DivisionByZeroError"],
    }
    service.collect_diagnostics.return_value = [
        {"message": "DivisionByZeroError", "timestamp": "2026-03-30T12:00:00Z"}
    ]
    service.collect_recent.return_value = []
    service.check_health.return_value = (True, True)
    service.format_log_attachment = Mock(return_value="[N/A] DivisionByZeroError")
    return service


@pytest.fixture
def mock_resolution_service():
    """Mock ResolutionService."""
    service = Mock()
    service.remediate_and_verify.return_value = ("success", {"alarm_ok": True, "health_ok": True, "error_rate_ok": True})
    service.trigger_recovery.return_value = ("not-required", "")
    return service


@pytest.fixture
def mock_ai_service():
    """Mock AIAnalysisService."""
    service = Mock()
    service.classify_incident.return_value = None
    service.analyze_for_escalation.return_value = None
    service.generate_resolution_summary.return_value = None
    return service


@pytest.fixture
def mock_incident_reporter():
    """Mock IncidentReporter."""
    reporter = Mock()
    reporter.report_triage_started.return_value = None
    reporter.report_analysis_results.return_value = None
    reporter.report_storm_detected.return_value = None
    reporter.report_remediation_unavailable.return_value = None
    reporter.report_remediation_failed.return_value = None
    reporter.report_verification_failed.return_value = None
    reporter.report_auto_resolved.return_value = None
    reporter.report_recovery_status.return_value = None
    reporter.resolve_ticket.return_value = None
    return reporter


@pytest.fixture
def lambda_context():
    """Mock Lambda context."""
    context = Mock()
    context.function_name = "incident-detection-dev"
    context.aws_request_id = "test-request-id"
    return context


# ------------------------------------------------------------------ #
# Checkpoint fixtures
# ------------------------------------------------------------------ #

CHECKPOINT_TABLE_NAME = "sre-checkpoints-test"
CHECKPOINT_BUCKET_NAME = "sre-checkpoint-manifests-test"


def backdate_heartbeat(table, checkpoint_id: str, seconds_ago: int):
    """Set last_heartbeat to N seconds in the past (shared test helper)."""
    old = (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat()
    table.update_item(
        Key={"checkpoint_id": checkpoint_id},
        UpdateExpression="SET last_heartbeat = :old",
        ExpressionAttributeValues={":old": old},
    )


@pytest.fixture
def mock_checkpoint_table():
    """Moto DynamoDB checkpoint table with service-status-index GSI.

    Schema matches v1 spec Section 2:
    - PK: checkpoint_id (S)
    - GSI: service-status-index (service S, status S)
    - TTL: ttl attribute
    - Billing: PAY_PER_REQUEST

    Yields (dynamodb_resource, s3_client, table) for direct assertions.
    """
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-west-2")
        s3 = boto3.client("s3", region_name="us-west-2")

        table = dynamodb.create_table(
            TableName=CHECKPOINT_TABLE_NAME,
            KeySchema=[{"AttributeName": "checkpoint_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "checkpoint_id", "AttributeType": "S"},
                {"AttributeName": "service", "AttributeType": "S"},
                {"AttributeName": "status", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[{
                "IndexName": "service-status-index",
                "KeySchema": [
                    {"AttributeName": "service", "KeyType": "HASH"},
                    {"AttributeName": "status", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }],
            BillingMode="PAY_PER_REQUEST",
        )

        s3.create_bucket(
            Bucket=CHECKPOINT_BUCKET_NAME,
            CreateBucketConfiguration={"LocationConstraint": "us-west-2"},
        )

        yield dynamodb, s3, table


@pytest.fixture
def mock_checkpoint_client(mock_checkpoint_table):
    """CheckpointClient wired to moto resources. Ready for any test that needs checkpoint SDK."""
    dynamodb, s3, _ = mock_checkpoint_table
    return CheckpointClient(
        table_name=CHECKPOINT_TABLE_NAME,
        bucket_name=CHECKPOINT_BUCKET_NAME,
        dynamodb=dynamodb,
        s3=s3,
    )


@pytest.fixture
def mock_checkpoint_repo(mock_checkpoint_table):
    """CheckpointRepository wired to moto resources (platform read layer)."""
    dynamodb, s3, table = mock_checkpoint_table
    return CheckpointRepository(
        table_name=CHECKPOINT_TABLE_NAME,
        bucket_name=CHECKPOINT_BUCKET_NAME,
        dynamodb=dynamodb,
        s3=s3,
        table=table,
    )
