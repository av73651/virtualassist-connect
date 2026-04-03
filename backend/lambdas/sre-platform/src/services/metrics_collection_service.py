"""Centralized metrics collection service with caching and enrichment.

This service orchestrates metrics collection from ObservabilityRepository,
adds incident-focused enrichment (trends, deployment correlation),
and manages caching via CorrelationRepository.

All observability concerns handled by @observe decorator.
"""

import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any

from shared.middleware.observability import observe

from src.models.enums import ErrorRateTrend, DeploymentCorrelation
from src.models.metrics_thresholds import MetricsEnrichmentThresholds
from src.repositories.observability_repository import ObservabilityRepository
from src.repositories.correlation_repository import CorrelationRepository


class MetricsCollectionService:
    """Centralized metrics collection with caching and enrichment."""

    def __init__(
        self,
        observability_repo: ObservabilityRepository,
        correlation_repo: CorrelationRepository,
        cache_ttl_seconds: int = 120,
        thresholds: MetricsEnrichmentThresholds | None = None,
    ):
        """Initialize MetricsCollectionService.

        Args:
            observability_repo: Repository for CloudWatch metrics access
            correlation_repo: Repository for DynamoDB caching
            cache_ttl_seconds: Cache TTL in seconds (default 120s prod, 60s dev)
            thresholds: Enrichment thresholds for trend/correlation classification
        """
        self._observability = observability_repo
        self._correlation = correlation_repo
        self._cache_ttl = cache_ttl_seconds
        self._thresholds = thresholds or MetricsEnrichmentThresholds()

    @observe(operation="collect_incident_metrics", metric_prefix="metrics_collection")
    def collect_incident_metrics(
        self,
        incident_key: str,
        function_name: str,
        alarm_name: str,
        lookback_minutes: int = 15,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        """Collect comprehensive metrics bundle for incident.

        Args:
            incident_key: Unique incident identifier
            function_name: Lambda function name (e.g., calculator-api-prod)
            alarm_name: CloudWatch alarm name
            lookback_minutes: Time window for metrics (default 15)
            force_refresh: Bypass cache, always collect fresh (for Escalation)

        Returns:
            Metrics bundle with alarm_metrics, lambda_metrics, deployments, enrichment
            On error: Returns structure with empty/zero values (graceful degradation)
        """
        now = datetime.now(timezone.utc)

        if not force_refresh:
            cached = self._check_cache(incident_key, now)
            if cached:
                result = copy.deepcopy(cached)
                result["enrichment"]["cache_hit"] = True
                return result

        try:
            with ThreadPoolExecutor(max_workers=3) as executor:
                alarm_future = executor.submit(
                    self._observability.get_alarm_metric_data, alarm_name, lookback_minutes
                )
                lambda_future = executor.submit(
                    self._observability.get_lambda_metrics, function_name, lookback_minutes
                )
                deploy_future = executor.submit(
                    self._observability.get_recent_deployments,
                    function_name,
                    self._thresholds.deployments_lookback_minutes,
                )

                alarm_metrics = alarm_future.result()
                lambda_metrics = lambda_future.result()
                deployments = deploy_future.result()
        except Exception:
            return self._empty_metrics_bundle(incident_key, function_name, alarm_name, now)

        enrichment = self._enrich_metrics(alarm_metrics, lambda_metrics, deployments, now)
        enrichment["cache_hit"] = False

        bundle = {
            "alarm_metrics": alarm_metrics,
            "lambda_metrics": lambda_metrics,
            "deployments": deployments,
            "enrichment": enrichment,
            "collection_metadata": {
                "incident_key": incident_key,
                "function_name": function_name,
                "alarm_name": alarm_name,
                "lookback_minutes": lookback_minutes,
            },
        }

        self._store_metrics(incident_key, bundle, now)

        return bundle

    def _check_cache(self, incident_key: str, now: datetime) -> dict[str, Any] | None:
        """Check if metrics exist in DDB and are fresh enough.

        Args:
            incident_key: Unique incident identifier
            now: Current timestamp (for staleness calculation)

        Returns:
            Cached metrics bundle if fresh (< cache_ttl), None otherwise
        """
        try:
            record = self._correlation.get(incident_key)
            if not record or not record.metrics:
                return None

            age = now - record.metrics_collected_at

            if age.total_seconds() < self._cache_ttl:
                return record.metrics

            return None
        except Exception:
            return None

    def _enrich_metrics(
        self,
        alarm_metrics: dict,
        lambda_metrics: dict,
        deployments: list[dict],
        now: datetime,
    ) -> dict[str, Any]:
        """Add incident-focused enrichment to raw metrics.

        Enrichment logic:
        - Error rate trend: Helps AI prioritize incidents (increasing = urgent)
        - Deployment correlation: Suggests rollback candidates (high = likely culprit)
        - Threshold validation: Confirms alarm still firing (guards against flapping)

        Args:
            alarm_metrics: Alarm data from ObservabilityRepository
            lambda_metrics: Lambda metrics from ObservabilityRepository
            deployments: Recent deployments from ObservabilityRepository
            now: Current timestamp

        Returns:
            Enrichment dict with trend, deployment correlation, threshold validation
        """
        deployments = deployments[: self._thresholds.max_recent_deployments] if deployments else []

        error_rate = lambda_metrics.get("error_rate", 0.0)
        trend = self._classify_error_rate_trend(error_rate)

        recent_deployment = None
        deployment_correlation = DeploymentCorrelation.NONE
        deployment_delta_minutes = None

        if deployments:
            most_recent = deployments[0]
            deploy_time = datetime.fromisoformat(most_recent["timestamp"])
            delta = now - deploy_time
            delta_minutes = int(delta.total_seconds() / 60)

            deployment_correlation = self._classify_deployment_correlation(
                delta_minutes, error_rate
            )

            if deployment_correlation != DeploymentCorrelation.NONE:
                recent_deployment = most_recent["version"]
                deployment_delta_minutes = delta_minutes

        alarm_config = alarm_metrics.get("alarm_config", {})
        threshold = alarm_config.get("threshold", 0.0)

        datapoints = alarm_metrics.get("datapoints", [])
        current_value = 0.0
        if datapoints:
            current_value = datapoints[-1].get("value", 0.0)

        threshold_exceeded = current_value > threshold

        return {
            "error_rate_trend": trend.value,
            "recent_deployment_detected": recent_deployment is not None,
            "recent_deployment_version": recent_deployment,
            "deployment_correlation": deployment_correlation.value,
            "deployment_time_delta_minutes": deployment_delta_minutes,
            "alarm_threshold_exceeded": threshold_exceeded,
            "alarm_threshold_value": threshold,
            "current_metric_value": current_value,
            "collected_at": now.isoformat(),
        }

    def _classify_error_rate_trend(self, error_rate: float) -> ErrorRateTrend:
        """Classify error rate into trend category.

        Args:
            error_rate: Error rate percentage (0-100)

        Returns:
            ErrorRateTrend enum value
        """
        if error_rate > self._thresholds.error_rate_increasing_threshold:
            return ErrorRateTrend.INCREASING
        elif error_rate < self._thresholds.error_rate_decreasing_threshold:
            return ErrorRateTrend.DECREASING
        else:
            return ErrorRateTrend.STABLE

    def _classify_deployment_correlation(
        self, delta_minutes: int, error_rate: float
    ) -> DeploymentCorrelation:
        """Classify deployment-error correlation strength.

        Args:
            delta_minutes: Minutes since deployment
            error_rate: Current error rate percentage

        Returns:
            DeploymentCorrelation enum value
        """
        if delta_minutes < self._thresholds.deployment_high_correlation_window_minutes:
            if error_rate > self._thresholds.deployment_high_error_rate_threshold:
                return DeploymentCorrelation.HIGH
            return DeploymentCorrelation.MEDIUM
        elif delta_minutes < self._thresholds.deployment_medium_correlation_window_minutes:
            return DeploymentCorrelation.MEDIUM
        elif delta_minutes < self._thresholds.deployment_low_correlation_window_minutes:
            return DeploymentCorrelation.LOW
        return DeploymentCorrelation.NONE

    def _store_metrics(
        self, incident_key: str, bundle: dict, collected_at: datetime
    ) -> None:
        """Store metrics bundle in DynamoDB via CorrelationRecord.

        Uses conditional update to avoid unnecessary DDB read (TOCTOU optimization).
        Record must exist by this point (created during Detection phase).

        Args:
            incident_key: Unique incident identifier
            bundle: Full metrics bundle
            collected_at: Timestamp when metrics were collected

        Note:
            Storage failure doesn't block metrics return (graceful degradation)
        """
        try:
            record = self._correlation.get(incident_key)
            if record:
                updated = record.with_metrics(bundle, collected_at)
                self._correlation.update(updated)
        except Exception:
            pass

    def _empty_metrics_bundle(
        self, incident_key: str, function_name: str, alarm_name: str, now: datetime
    ) -> dict[str, Any]:
        """Return empty structure on collection failure (graceful degradation).

        Args:
            incident_key: Unique incident identifier
            function_name: Lambda function name
            alarm_name: CloudWatch alarm name
            now: Current timestamp

        Returns:
            Empty metrics bundle with zero values
        """
        return {
            "alarm_metrics": {
                "alarm_config": {},
                "datapoints": [],
                "current_state": "ERROR",
            },
            "lambda_metrics": {
                "invocations": 0,
                "errors": 0,
                "throttles": 0,
                "duration_avg": 0.0,
                "concurrent_executions_max": 0,
                "error_rate": 0.0,
            },
            "deployments": [],
            "enrichment": {
                "error_rate_trend": ErrorRateTrend.UNKNOWN.value,
                "recent_deployment_detected": False,
                "recent_deployment_version": None,
                "deployment_correlation": DeploymentCorrelation.NONE.value,
                "deployment_time_delta_minutes": None,
                "alarm_threshold_exceeded": False,
                "alarm_threshold_value": 0.0,
                "current_metric_value": 0.0,
                "collected_at": now.isoformat(),
                "cache_hit": False,
            },
            "collection_metadata": {
                "incident_key": incident_key,
                "function_name": function_name,
                "alarm_name": alarm_name,
                "lookback_minutes": 15,
            },
        }
