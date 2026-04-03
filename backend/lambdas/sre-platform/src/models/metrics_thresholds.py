"""Configurable thresholds for metrics enrichment logic."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MetricsEnrichmentThresholds:
    """Thresholds for classifying error rate trends and deployment correlations.

    All thresholds are configurable to support operational tuning without code changes.
    Values calibrated from Phase 2E integration testing with real incident data.
    """

    # Error rate trend classification (percentage)
    error_rate_increasing_threshold: float = 10.0
    error_rate_decreasing_threshold: float = 2.0

    # Deployment correlation time windows (minutes)
    deployment_high_correlation_window_minutes: int = 15
    deployment_medium_correlation_window_minutes: int = 30
    deployment_low_correlation_window_minutes: int = 60

    # Deployment-error correlation threshold (percentage)
    deployment_high_error_rate_threshold: float = 5.0

    # Max recent deployments to analyze (DDB item size optimization)
    max_recent_deployments: int = 10

    # Deployments API lookback window (minutes)
    deployments_lookback_minutes: int = 60
