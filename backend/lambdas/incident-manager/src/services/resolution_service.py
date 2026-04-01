"""ResolutionService — auto-remediation, verification, and self-healing recovery.

Owns the full incident resolution spectrum:
- Auto-remediation: immediate automated fix (rollback, scale up, increase concurrency)
- Verification: 3-point check that the fix worked (alarm state, health, error rate)
- Self-healing: post-fix recovery workflows (DLQ replay, batch reprocess, data reconciliation)

All observability concerns (tracing, metrics, logging) handled by @observe decorator."""

import os
import uuid

from shared.middleware.observability import observe

from src.models.config import IncidentConfig
from src.models.enums import ResolutionOutcome, RecoveryStatus
from src.services.remediation.engine import RemediationEngine


class ResolutionService:
    """Auto-remediation + verification + self-healing recovery."""

    def __init__(
        self,
        remediation_engine: RemediationEngine,
        remediation_repo,
        recovery_repo,
        observability_repo,
        log_analysis_service,
        config: IncidentConfig,
    ):
        self._remediation_engine = remediation_engine
        self._remediation = remediation_repo
        self._recovery = recovery_repo
        self._observability = observability_repo
        self._log_analysis = log_analysis_service
        self._config = config

    # ------------------------------------------------------------------ #
    # Auto-remediation
    # ------------------------------------------------------------------ #

    @observe(operation="attempt_auto_remediation", metric_prefix="resolution_remediate")
    def attempt_auto_remediation(
        self,
        service_type: str,
        root_cause: str,
        resource_context: dict,
        ai_recommended_action: str | None = None,
    ) -> bool | None:
        """Execute automated remediation via skill-file-driven engine.

        Returns True if succeeded, False if failed, None if not available."""
        return self._remediation_engine.attempt(
            service_type, root_cause, resource_context, self._remediation, self._config,
            ai_recommended_action=ai_recommended_action,
        )

    # ------------------------------------------------------------------ #
    # Verification
    # ------------------------------------------------------------------ #

    @observe(operation="verify_remediation", metric_prefix="resolution_verify")
    def verify(self, alarm_name: str, log_group: str) -> dict:
        """3-point verification after remediation.

        Returns dict with alarm_ok, health_ok, error_rate_ok."""
        alarm_state = self._observability.get_alarm_state(alarm_name)
        alarm_ok = alarm_state == "OK"

        health_ok, error_rate_ok = self._log_analysis.check_health(log_group)

        return {
            "alarm_ok": alarm_ok,
            "health_ok": health_ok,
            "error_rate_ok": error_rate_ok,
        }

    # ------------------------------------------------------------------ #
    # Combined: remediate → wait → verify
    # ------------------------------------------------------------------ #

    @observe(operation="remediate_and_verify", metric_prefix="resolution_full")
    def remediate_and_verify(
        self,
        service_type: str,
        root_cause: str,
        resource_context: dict,
        alarm_name: str,
        log_group: str,
        wait_seconds: int,
        ai_recommended_action: str | None = None,
    ) -> tuple[str, dict | None]:
        """Full resolution attempt: remediate, wait, verify.

        Returns (outcome, verification_result):
        - outcome: ResolutionOutcome enum value
        - verification_result: dict with alarm_ok/health_ok/error_rate_ok, or None"""
        import time

        result = self.attempt_auto_remediation(
            service_type, root_cause, resource_context,
            ai_recommended_action=ai_recommended_action,
        )

        if result is None:
            return ResolutionOutcome.NO_REMEDIATION, None

        if result is False:
            return ResolutionOutcome.REMEDIATION_FAILED, None

        time.sleep(wait_seconds)

        verification = self.verify(alarm_name, log_group)

        if not (verification["alarm_ok"] and verification["health_ok"] and verification["error_rate_ok"]):
            return ResolutionOutcome.VERIFICATION_FAILED, verification

        return ResolutionOutcome.SUCCESS, verification

    # ------------------------------------------------------------------ #
    # Self-healing recovery
    # ------------------------------------------------------------------ #

    @observe(operation="trigger_recovery", metric_prefix="resolution_recovery")
    def trigger_recovery(
        self,
        recovery_model: str,
        incident_key: str,
        jira_ticket_id: str,
        severity: str,
    ) -> tuple[str, str]:
        """Triggers post-resolution recovery workflow based on recovery_model.

        Returns (recovery_status, detail):
        - recovery_status: "not-required" | "triggered" | "failed" | "not-configured"
        - detail: human-readable detail for reporting"""
        if recovery_model == "stateless":
            return RecoveryStatus.NOT_REQUIRED, ""

        catalog_entry = self._config.recovery_catalog.get(recovery_model)
        if not catalog_entry:
            return RecoveryStatus.NOT_CONFIGURED, f"Recovery model '{recovery_model}' not found in catalog"

        recovery_type = catalog_entry.get("type")
        execution_id = f"{incident_key}-{uuid.uuid4().hex[:8]}"

        payload = {
            "incident_key": incident_key,
            "jira_ticket_id": jira_ticket_id,
            "severity": severity,
            "recovery_model": recovery_model,
            "execution_id": execution_id,
        }

        if recovery_type == "step_function":
            return self._trigger_step_function(catalog_entry, payload, recovery_model)

        if recovery_type == "lambda":
            return self._trigger_lambda(catalog_entry, payload, recovery_model)

        return RecoveryStatus.NOT_CONFIGURED, f"Unknown recovery type '{recovery_type}' for model {recovery_model}"

    def _trigger_step_function(
        self, catalog_entry: dict, payload: dict, recovery_model: str
    ) -> tuple[str, str]:
        """Triggers Step Function recovery workflow."""
        arn_env = catalog_entry.get("workflow_arn_env", "")
        workflow_arn = os.environ.get(arn_env, "")
        if not workflow_arn:
            return RecoveryStatus.NOT_CONFIGURED, f"Recovery workflow ARN not configured (env: {arn_env})"

        result = self._recovery.trigger_step_function(workflow_arn, payload)
        if result:
            return RecoveryStatus.TRIGGERED, f"Recovery workflow triggered: {recovery_model}. Execution: {result}"
        return RecoveryStatus.FAILED, f"Recovery workflow trigger failed for {recovery_model}"

    def _trigger_lambda(
        self, catalog_entry: dict, payload: dict, recovery_model: str
    ) -> tuple[str, str]:
        """Triggers Lambda recovery function."""
        fn_env = catalog_entry.get("function_name_env", "")
        fn_name = os.environ.get(fn_env, "")
        if not fn_name:
            return RecoveryStatus.NOT_CONFIGURED, f"Recovery function not configured (env: {fn_env})"

        result = self._recovery.trigger_recovery_lambda(fn_name, payload)
        if result:
            return RecoveryStatus.TRIGGERED, f"Recovery Lambda triggered: {recovery_model}. Function: {fn_name}"
        return RecoveryStatus.FAILED, f"Recovery Lambda trigger failed for {recovery_model}"
