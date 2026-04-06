"""RemediationRepository — AWS service control plane operations for auto-remediation.

Covers Lambda, API Gateway, and OpenSearch remediation actions.
Method names match the skill file action definitions for dynamic dispatch
by RemediationEngine via getattr().

All observability concerns (tracing, metrics, logging) handled by @observe decorator."""

import boto3

from shared.middleware.observability import observe

from src.models.config import IncidentConfig


class RemediationRepository:
    """AWS control plane operations for incident remediation."""

    def __init__(
        self,
        config: IncidentConfig,
        lambda_client=None,
        apigw_client=None,
        opensearch_client=None,
    ):
        self._config = config
        self._lambda_client = lambda_client or boto3.client("lambda")
        self._apigw_client = apigw_client or boto3.client("apigateway")
        self._opensearch_client = opensearch_client or boto3.client("opensearch")

    # ------------------------------------------------------------------ #
    # Lambda remediation
    # ------------------------------------------------------------------ #

    @observe(operation="rollback_lambda_version", metric_prefix="remediation_rollback")
    def rollback_lambda_version(self, function_name: str) -> dict:
        """Reverts Lambda alias to the previous published version.

        Returns {"status": "success"|"failed", ...}."""
        try:
            response = self._lambda_client.list_versions_by_function(
                FunctionName=function_name,
            )
            versions = [
                v for v in response.get("Versions", [])
                if v["Version"] != "$LATEST"
            ]
            if len(versions) < 2:
                return {"status": "failed", "reason": "no-previous-version"}

            previous = versions[-2]["Version"]

            self._lambda_client.update_alias(
                FunctionName=function_name,
                Name=self._config.lambda_alias_name,
                FunctionVersion=previous,
            )
            return {"status": "success", "previous_version": previous}

        except Exception:
            return {"status": "failed"}

    @observe(operation="increase_lambda_memory", metric_prefix="remediation_memory")
    def increase_lambda_memory(self, function_name: str, current_mb: int = 0) -> dict:
        """Increases Lambda memory by one tier.

        Returns {"status": "success"|"failed", "new_memory": int}."""
        tiers = self._config.lambda_memory_tiers
        try:
            if current_mb == 0:
                config = self._lambda_client.get_function_configuration(
                    FunctionName=function_name,
                )
                current_mb = config["MemorySize"]

            new_mb = current_mb
            for tier in tiers:
                if tier > current_mb:
                    new_mb = tier
                    break

            if new_mb == current_mb:
                return {"status": "failed", "reason": "already-at-max"}

            self._lambda_client.update_function_configuration(
                FunctionName=function_name,
                MemorySize=new_mb,
            )
            return {"status": "success", "new_memory": new_mb}

        except Exception:
            return {"status": "failed"}

    @observe(operation="increase_concurrency", metric_prefix="remediation_concurrency")
    def increase_concurrency(self, function_name: str, current: int = 0) -> dict:
        """Increases reserved concurrency (2x or +100, whichever is greater).

        Returns {"status": "success"|"failed", "new_concurrency": int}."""
        try:
            if current == 0:
                try:
                    resp = self._lambda_client.get_function_concurrency(
                        FunctionName=function_name,
                    )
                    current = resp.get("ReservedConcurrentExecutions", 100)
                except Exception:
                    current = 100

            new_val = max(current * 2, current + 100)

            self._lambda_client.put_function_concurrency(
                FunctionName=function_name,
                ReservedConcurrentExecutions=new_val,
            )
            return {"status": "success", "new_concurrency": new_val}

        except Exception:
            return {"status": "failed"}

    # ------------------------------------------------------------------ #
    # API Gateway remediation
    # ------------------------------------------------------------------ #

    @observe(operation="rollback_apigw_deployment", metric_prefix="remediation_apigw_rollback")
    def rollback_apigw_deployment(self, rest_api_id: str, stage_name: str) -> dict:
        """Reverts API Gateway stage to the previous deployment.

        Returns {"status": "success"|"failed", ...}."""
        try:
            response = self._apigw_client.get_deployments(
                restApiId=rest_api_id,
                limit=10,
            )
            deployments = response.get("items", [])
            if len(deployments) < 2:
                return {"status": "failed", "reason": "no-previous-deployment"}

            previous = deployments[1]["id"]

            self._apigw_client.update_stage(
                restApiId=rest_api_id,
                stageName=stage_name,
                patchOperations=[
                    {
                        "op": "replace",
                        "path": "/deploymentId",
                        "value": previous,
                    }
                ],
            )
            return {"status": "success", "previous_deployment": previous}

        except Exception:
            return {"status": "failed"}

    @observe(operation="update_apigw_throttle", metric_prefix="remediation_apigw_throttle")
    def update_apigw_throttle(self, rest_api_id: str, stage_name: str) -> dict:
        """Doubles API Gateway stage throttle rate and burst limits.

        Returns {"status": "success"|"failed", ...}."""
        try:
            stage = self._apigw_client.get_stage(
                restApiId=rest_api_id,
                stageName=stage_name,
            )
            current_rate = stage.get("methodSettings", {}).get("*/*", {}).get("throttlingRateLimit", 1000)
            current_burst = stage.get("methodSettings", {}).get("*/*", {}).get("throttlingBurstLimit", 500)

            new_rate = current_rate * 2
            new_burst = current_burst * 2

            self._apigw_client.update_stage(
                restApiId=rest_api_id,
                stageName=stage_name,
                patchOperations=[
                    {"op": "replace", "path": "/*/*/throttling/rateLimit", "value": str(new_rate)},
                    {"op": "replace", "path": "/*/*/throttling/burstLimit", "value": str(new_burst)},
                ],
            )
            return {"status": "success", "new_rate": new_rate, "new_burst": new_burst}

        except Exception:
            return {"status": "failed"}

    # ------------------------------------------------------------------ #
    # OpenSearch remediation
    # ------------------------------------------------------------------ #

    @observe(operation="scale_opensearch_domain", metric_prefix="remediation_opensearch_scale")
    def scale_opensearch_domain(self, domain_name: str) -> dict:
        """Adds 2 data nodes to OpenSearch cluster.

        Returns {"status": "success"|"failed", ...}."""
        try:
            config = self._opensearch_client.describe_domain(
                DomainName=domain_name,
            )
            cluster_config = config["DomainStatus"]["ClusterConfig"]
            current_count = cluster_config.get("InstanceCount", 2)
            new_count = current_count + 2

            self._opensearch_client.update_domain_config(
                DomainName=domain_name,
                ClusterConfig={"InstanceCount": new_count},
            )
            return {"status": "success", "new_instance_count": new_count}

        except Exception:
            return {"status": "failed"}

    @observe(operation="increase_opensearch_storage", metric_prefix="remediation_opensearch_storage")
    def increase_opensearch_storage(self, domain_name: str) -> dict:
        """Increases OpenSearch EBS volume size by 50%.

        Returns {"status": "success"|"failed", ...}."""
        try:
            config = self._opensearch_client.describe_domain(
                DomainName=domain_name,
            )
            ebs_options = config["DomainStatus"]["EBSOptions"]
            current_size = ebs_options.get("VolumeSize", 100)
            new_size = int(current_size * 1.5)

            self._opensearch_client.update_domain_config(
                DomainName=domain_name,
                EBSOptions={"VolumeSize": new_size},
            )
            return {"status": "success", "new_volume_size_gb": new_size}

        except Exception:
            return {"status": "failed"}
