"""IncidentConfig — externalized operational configuration.

Loaded from incident_config.json at Lambda cold start.
Contains all tunable parameters: severity mapping, cool-off windows,
storm detection thresholds, remediation/recovery catalogs, and classification rules."""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class IncidentConfig:
    """Immutable operational configuration for incident management pipeline.

    Loaded once per Lambda cold start from incident_config.json.
    All time values are in seconds unless noted otherwise."""

    # Jira integration
    jira_issue_type: str                       # Jira issue type name
    jira_service_desk_id: str                  # JSM service desk ID
    jira_request_type_id: str                  # JSM request type ID ("Report a system problem")
    jira_transition_resolve: str               # Jira transition name for resolving tickets
    jira_transition_investigate: str            # Jira transition name for triage (In Progress)
    jira_labels_prefix: list[str]              # static label prefixes for Jira tickets
    jira_priority_map: dict[str, str]          # severity → Jira priority name
    jira_http_timeout_seconds: int             # HTTP timeout for Jira API calls

    # EventBridge / Lambda
    eventbridge_source: str                    # EventBridge source name
    lambda_alias_name: str                     # Lambda alias name for rollback operations
    lambda_memory_tiers: list[int]             # ordered list of Lambda memory tiers (MB)

    # Operational tuning
    severity_mapping: dict[str, dict]          # alarm_type → {severity, recovery_model}
    cool_off_seconds: dict[str, int]           # severity → seconds to wait before confirming
    verification_wait_seconds: dict[str, int]  # severity → seconds to wait for verification
    grace_period_seconds: int                  # window after auto-resolve for recurrence detection
    reservation_timeout_seconds: int           # max age of RESERVED record before stale recovery
    triage_timeout_seconds: int                # max triage duration before escalation
    log_analysis_window_minutes: int           # how far back to search logs (minutes)
    max_log_events: int                        # max log events to retrieve
    correlation_ttl_hours: int                 # DynamoDB record TTL (hours)
    recovery_log_minutes: int                  # how far back to collect recovery logs (minutes)
    storm_window_seconds: int                  # time window for storm detection
    storm_threshold: int                       # incident count above which storm is declared

    # Triage tuning
    verification_window_minutes: int           # post-remediation verification window
    verification_error_threshold: int          # max errors allowed during verification
    max_sample_payloads: int                   # max sample payloads to collect
    sample_payload_max_length: int             # max chars per sample payload
    pattern_key_max_length: int                # max chars for error pattern keys

    # Catalogs and rules
    remediation_catalog: dict[str, dict[str, dict]]  # service_type → {root_cause → {action}}
    recovery_catalog: dict[str, dict]          # recovery_model → {type, workflow_arn_env}
    classification_rules: list[dict]           # ordered rules for root cause classification

    # Bedrock Knowledge Base (empty = disabled, falls back to rule-based)
    bedrock_knowledge_base_id: str             # Bedrock KB ID for AI classification
    bedrock_model_arn: str                     # Foundation model ARN for RetrieveAndGenerate

    @classmethod
    def load(cls, config_path: str | None = None) -> "IncidentConfig":
        """Load config from JSON file.

        Args:
            config_path: Absolute path to config JSON. Defaults to incident_config.json
                        in the project root (two levels up from this module).

        Returns:
            Frozen IncidentConfig instance.

        Raises:
            FileNotFoundError: If config file does not exist.
            json.JSONDecodeError: If config file contains invalid JSON.
            KeyError: If required config keys are missing."""
        path = config_path or str(
            Path(__file__).parent.parent.parent / "incident_config.json"
        )

        with open(path) as f:
            data = json.load(f)

        jira = data.get("jira", {})
        triage_tuning = data.get("triage_tuning", {})

        return cls(
            # Jira integration
            jira_issue_type=jira.get("issue_type", "Incident"),
            jira_service_desk_id=jira.get("service_desk_id", ""),
            jira_request_type_id=jira.get("request_type_id", ""),
            jira_transition_resolve=jira.get("transition_resolve", "Resolve"),
            jira_transition_investigate=jira.get("transition_investigate", "Investigate"),
            jira_labels_prefix=jira.get("labels_prefix", ["incident", "automated"]),
            jira_priority_map=jira.get("priority_map", {"SEV-1": "Highest", "SEV-2": "High", "SEV-3": "Medium"}),
            jira_http_timeout_seconds=jira.get("http_timeout_seconds", 30),
            # EventBridge / Lambda
            eventbridge_source=data.get("eventbridge_source", "incident-manager"),
            lambda_alias_name=data.get("lambda_alias_name", "live"),
            lambda_memory_tiers=data.get("lambda_memory_tiers", [128, 256, 512, 1024, 1536, 2048, 3008]),
            # Operational tuning
            severity_mapping=data["severity_mapping"],
            cool_off_seconds=data["cool_off_seconds"],
            verification_wait_seconds=data["verification_wait_seconds"],
            grace_period_seconds=data["grace_period_seconds"],
            reservation_timeout_seconds=data.get("reservation_timeout_seconds", 180),
            triage_timeout_seconds=data.get("triage_timeout_seconds", 120),
            log_analysis_window_minutes=data["log_analysis"]["window_minutes"],
            max_log_events=data["log_analysis"]["max_events"],
            correlation_ttl_hours=data["correlation_ttl_hours"],
            recovery_log_minutes=data.get("recovery_log_minutes", 5),
            storm_window_seconds=data["storm_detection"]["window_seconds"],
            storm_threshold=data["storm_detection"]["threshold"],
            # Triage tuning
            verification_window_minutes=triage_tuning.get("verification_window_minutes", 2),
            verification_error_threshold=triage_tuning.get("verification_error_threshold", 5),
            max_sample_payloads=triage_tuning.get("max_sample_payloads", 5),
            sample_payload_max_length=triage_tuning.get("sample_payload_max_length", 500),
            pattern_key_max_length=triage_tuning.get("pattern_key_max_length", 100),
            # Catalogs and rules
            remediation_catalog=data["remediation_catalog"],
            recovery_catalog=data.get("recovery_catalog", {}),
            classification_rules=data["classification_rules"],
            # Bedrock Knowledge Base
            bedrock_knowledge_base_id=data.get("bedrock", {}).get("knowledge_base_id", ""),
            bedrock_model_arn=data.get("bedrock", {}).get("model_arn", ""),
        )
