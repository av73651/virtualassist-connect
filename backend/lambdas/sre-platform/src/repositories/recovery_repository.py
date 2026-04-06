"""RecoveryRepository — post-resolution recovery workflow triggers.

Supports Step Functions and async Lambda invocations for recovery models
(replay, reprocess, data-correction, backlog-drain).

All observability concerns (tracing, metrics, logging) handled by @observe decorator."""

import json

import boto3

from shared.middleware.observability import observe


class RecoveryRepository:
    """Step Functions and Lambda async — recovery workflow triggers."""

    def __init__(self, sfn_client=None, lambda_client=None):
        self._sfn_client = sfn_client or boto3.client("stepfunctions")
        self._lambda_client = lambda_client or boto3.client("lambda")

    @observe(operation="trigger_step_function", metric_prefix="recovery_sfn")
    def trigger_step_function(self, workflow_arn: str, input_payload: dict) -> str | None:
        """Starts Step Functions execution. Returns execution ARN or None on failure."""
        try:
            execution_name = input_payload.get("execution_id", "")
            response = self._sfn_client.start_execution(
                stateMachineArn=workflow_arn,
                name=execution_name,
                input=json.dumps(input_payload),
            )
            return response.get("executionArn")

        except Exception:
            return None

    @observe(operation="trigger_recovery_lambda", metric_prefix="recovery_lambda")
    def trigger_recovery_lambda(self, function_name: str, payload: dict) -> dict | None:
        """Invokes Lambda asynchronously for recovery. Returns response or None on failure."""
        try:
            response = self._lambda_client.invoke(
                FunctionName=function_name,
                InvocationType="Event",
                Payload=json.dumps(payload),
            )
            return {"StatusCode": response.get("StatusCode", 0)}

        except Exception:
            return None
