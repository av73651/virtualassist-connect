# SRE Platform - Metrics Integration (Phase 2)

**Feature**: Centralized Metrics Collection Service with Detection/Escalation Integration  
**Phase**: 2 - Metrics Integration into Incident Workflow  
**Status**: 🔄 Design In Progress  
**Date**: 2026-04-03  
**Owner**: SRE Platform Team  
**Depends On**: Phase 1 (Metrics Collection Enhancement - ✅ Complete)

---

## Executive Summary

Phase 1 delivered the foundational metrics collection infrastructure (`ObservabilityRepository` methods). Phase 2 creates a **centralized MetricsCollectionService** that provides incident-focused metrics bundles with enrichment (trend analysis, deployment correlation, threshold validation) to Detection, Triage, and Escalation services.

**Impact**: 
- Improve incident ticket usefulness from 3-4/10 to 7-8/10 (Phase 2 target)
- Enable metrics-based auto-escalation rules
- Provide timeline-aware metrics (detection vs escalation state)
- Eliminate redundant CloudWatch API calls via intelligent caching

---

## Problem Statement

### Current State (Post Phase 1)
- ObservabilityRepository provides raw metrics collection methods
- No centralized service layer for metrics orchestration
- Detection and Escalation services would duplicate collection logic
- No enrichment (trends, deployment correlation, threshold validation)
- No caching strategy (redundant API calls)
- Metrics not integrated into incident workflow

### Issues
1. **Duplication Risk**: Detection and Escalation both need metrics → duplicate implementation
2. **No Context**: Raw metrics without interpretation (is error rate improving? recent deploy?)
3. **Redundant API Calls**: Both services hit CloudWatch independently (cost + latency)
4. **Stale Data Problem**: Escalation needs CURRENT metrics, not 5-minute-old Detection metrics
5. **Manual Correlation**: Engineers manually correlate metrics with deployments/trends

### Target State (Phase 2)
- Single `MetricsCollectionService` orchestrates metrics collection with enrichment
- Detection collects metrics at T0, stores in DDB, passes to Triage via event
- Triage uses metrics for auto-escalation rules (deployment correlation, threshold validation)
- Escalation collects fresh metrics at T+N, compares with Detection baseline
- Jira tickets show timeline: "Alarm State (10:00)" vs "Current State (10:05)"
- Smart caching avoids redundant API calls when metrics are fresh

---

## Requirements

### Functional Requirements

**FR-1: Centralized Metrics Collection**
- MUST provide single entry point for incident metrics collection
- MUST return standardized metrics bundle (alarm + lambda + deployments)
- MUST support force refresh (bypass cache) for Escalation use case
- MUST handle missing/partial data gracefully (never raise exceptions)

**FR-2: Metrics Enrichment**
- MUST calculate error rate trend (increasing/stable/decreasing)
- MUST detect recent deployments within 15/60 min windows
- MUST correlate errors with deployments (high/medium/low/none)
- MUST validate alarm threshold exceeded (detect false alarms)
- MUST include collection timestamp for staleness detection

**FR-3: Intelligent Caching**
- MUST cache metrics in DynamoDB via CorrelationRecord
- MUST reuse cached metrics if < 2 minutes old (configurable)
- MUST support force refresh for Escalation time-series comparison
- MUST track metrics_collected_at timestamp

**FR-4: Detection Integration**
- MUST collect metrics during Detection Lambda execution
- MUST store metrics in DynamoDB CorrelationRecord
- MUST include metrics in IncidentCreated EventBridge payload
- MUST NOT block incident creation on metrics failure (graceful degradation)

**FR-5: Triage Integration**
- MUST receive metrics from IncidentCreated event payload
- MUST use metrics for auto-escalation rules
- MUST escalate on: recent deployment correlation, alarm misconfiguration, threshold violations
- MUST NOT collect metrics (pure consumer of Detection metrics)

**FR-6: Escalation Integration**
- MUST collect fresh metrics at escalation time (T+N)
- MUST retrieve Detection metrics from DynamoDB (baseline)
- MUST include BOTH timelines in Jira ticket (detection vs current state)
- MUST show trend arrows (↑ increasing, ↓ decreasing, → stable)

### Non-Functional Requirements

**NFR-1: Performance**
- Metrics collection MUST complete in < 500ms (P95)
- Cache hit MUST avoid CloudWatch API calls (0ms data access overhead)
- Detection Lambda total time MUST remain < 5s with metrics collection
- Escalation Lambda total time MUST remain < 8s with metrics collection

**NFR-2: Reliability**
- Metrics collection failure MUST NOT block incident workflow
- MUST return empty enrichment on API failures (graceful degradation)
- MUST handle partial data (e.g., alarm found but no deployments)

**NFR-3: Cost**
- CloudWatch API calls MUST be minimized via caching
- Target: < 10 GetMetricStatistics calls per incident (Detection: 5, Escalation: 5 if fresh)
- Estimated cost: ~$3-5/month for 100 incidents/day

**NFR-4: Observability**
- MUST use @observe decorator (no manual logging)
- MUST emit metrics: collection_duration, cache_hit_rate, api_call_count
- MUST trace metrics collection through Detection → Triage → Escalation

---

## Architecture

### System Context

```
┌─────────────────────────────────────────────────────────────────┐
│                     Incident Workflow                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  CloudWatch Alarm → SNS → Detection Lambda                       │
│                              ↓                                    │
│                     MetricsCollectionService.collect()           │
│                              ↓                                    │
│                     Store in DynamoDB (CorrelationRecord)        │
│                              ↓                                    │
│                     Publish IncidentCreated (with metrics)       │
│                              ↓                                    │
│                          Triage Lambda                           │
│                              ↓                                    │
│              Read metrics from event payload                     │
│              Apply metrics-based escalation rules                │
│                              ↓                                    │
│                    [Escalation Required]                         │
│                              ↓                                    │
│                       Escalation Lambda                          │
│                              ↓                                    │
│                MetricsCollectionService.collect(force=True)      │
│                              ↓                                    │
│              Compare with Detection baseline                     │
│              Build timeline (T0 vs T+N)                          │
│              Enrich Jira with trend analysis                     │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Component Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                   Application Layer                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ Detection    │  │ Triage       │  │ Escalation   │          │
│  │ Service      │  │ Service      │  │ Service      │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         │                  │                  │                   │
│         └──────────┬───────┴──────────────────┘                  │
│                    ↓                                              │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │        MetricsCollectionService (NEW)                       ││
│  │  ┌──────────────────────────────────────────────────────┐  ││
│  │  │ collect_incident_metrics()                           │  ││
│  │  │  - Orchestrate collection                            │  ││
│  │  │  - Check cache (CorrelationRecord)                   │  ││
│  │  │  - Enrich with trends/deployment correlation         │  ││
│  │  │  - Store results                                      │  ││
│  │  └──────────────────────────────────────────────────────┘  ││
│  │  ┌──────────────────────────────────────────────────────┐  ││
│  │  │ _enrich_metrics()                                    │  ││
│  │  │  - Calculate trend (increasing/stable/decreasing)    │  ││
│  │  │  - Correlate deployments with errors                 │  ││
│  │  │  - Validate alarm threshold                          │  ││
│  │  └──────────────────────────────────────────────────────┘  ││
│  └─────────────────────┬───────────────────────────────────────┘│
│                        ↓                                         │
└──────────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────────┐
│                   Domain Layer                                   │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  ObservabilityRepository (Phase 1)                          ││
│  │   - get_alarm_metric_data()                                 ││
│  │   - get_lambda_metrics()                                    ││
│  │   - get_recent_deployments()                                ││
│  └─────────────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  CorrelationRepository (Enhanced)                           ││
│  │   - get() → includes metrics field                          ││
│  │   - update() → stores metrics bundle                        ││
│  └─────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────────┐
│              AWS Infrastructure                                  │
│  CloudWatch API  │  DynamoDB  │  EventBridge                    │
└──────────────────────────────────────────────────────────────────┘
```

---

## Detailed Design

### 1. MetricsCollectionService

**File**: `backend/lambdas/sre-platform/src/services/metrics_collection_service.py`

**Class Structure**:
```python
from datetime import datetime, timedelta, timezone
from typing import Any

from shared.middleware.observability import observe

from src.repositories.observability_repository import ObservabilityRepository
from src.repositories.correlation_repository import CorrelationRepository


class MetricsCollectionService:
    """Centralized metrics collection with caching and enrichment.
    
    Orchestrates metrics collection from ObservabilityRepository,
    adds incident-focused enrichment (trends, deployment correlation),
    and manages caching via CorrelationRepository.
    
    All observability concerns handled by @observe decorator."""
    
    def __init__(
        self,
        observability_repo: ObservabilityRepository,
        correlation_repo: CorrelationRepository,
        cache_ttl_seconds: int = 120,  # 2 minutes default (prod), 60s for dev
    ):
        self._observability = observability_repo
        self._correlation = correlation_repo
        self._cache_ttl = cache_ttl_seconds
    
    # Public Methods
    
    @observe(operation="collect_incident_metrics", metric_prefix="metrics_collection")
    def collect_incident_metrics(
        self,
        incident_key: str,
        function_name: str,
        alarm_name: str,
        lookback_minutes: int = 15,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        """Collects comprehensive metrics bundle for incident.
        
        Args:
            incident_key: Unique incident identifier
            function_name: Lambda function name (e.g., calculator-api-prod)
            alarm_name: CloudWatch alarm name
            lookback_minutes: Time window for metrics (default 15)
            force_refresh: Bypass cache, always collect fresh (for Escalation)
        
        Returns:
            {
                "alarm_metrics": {
                    "alarm_config": {...},
                    "datapoints": [...],
                    "current_state": "ALARM" | "OK" | "INSUFFICIENT_DATA"
                },
                "lambda_metrics": {
                    "invocations": int,
                    "errors": int,
                    "throttles": int,
                    "duration_avg": float,
                    "concurrent_executions_max": int,
                    "error_rate": float
                },
                "deployments": [
                    {
                        "timestamp": str,
                        "version": str,
                        "code_sha256": str,
                        ...
                    }
                ],
                "enrichment": {
                    "error_rate_trend": "increasing" | "stable" | "decreasing",
                    "recent_deployment_detected": bool,
                    "recent_deployment_version": str | None,
                    "deployment_correlation": "high" | "medium" | "low" | "none",
                    "deployment_time_delta_minutes": int | None,
                    "alarm_threshold_exceeded": bool,
                    "alarm_threshold_value": float,
                    "current_metric_value": float,
                    "collected_at": str (ISO 8601),
                    "cache_hit": bool,
                },
                "collection_metadata": {
                    "incident_key": str,
                    "function_name": str,
                    "alarm_name": str,
                    "lookback_minutes": int,
                }
            }
        
        On error: Returns structure with empty/zero values for graceful degradation.
        """
    
    # Private Methods
    
    def _check_cache(self, incident_key: str) -> dict[str, Any] | None:
        """Checks if metrics exist in DDB and are fresh enough (< cache_ttl).
        
        Returns cached metrics bundle if fresh, None otherwise."""
    
    def _enrich_metrics(
        self,
        alarm_metrics: dict,
        lambda_metrics: dict,
        deployments: list[dict],
        now: datetime,
    ) -> dict[str, Any]:
        """Adds incident-focused enrichment to raw metrics.
        
        Returns enrichment dict with trend, deployment correlation, threshold validation."""
    
    def _store_metrics(self, incident_key: str, bundle: dict, collected_at: datetime) -> None:
        """Stores metrics bundle in DynamoDB via CorrelationRecord.
        
        Storage failure doesn't block metrics return (graceful degradation)."""
    
    def _empty_metrics_bundle(
        self, incident_key: str, function_name: str, alarm_name: str
    ) -> dict[str, Any]:
        """Returns empty structure on collection failure (graceful degradation)."""
```

**Method: `collect_incident_metrics()` - Implementation Logic**:
```python
def collect_incident_metrics(...) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    
    # Step 1: Check cache (unless force_refresh)
    if not force_refresh:
        cached = self._check_cache(incident_key)
        if cached:
            cached["enrichment"]["cache_hit"] = True
            return cached
    
    # Step 2: Collect raw metrics (parallel via ObservabilityRepository)
    try:
        alarm_metrics = self._observability.get_alarm_metric_data(
            alarm_name, lookback_minutes
        )
        lambda_metrics = self._observability.get_lambda_metrics(
            function_name, lookback_minutes
        )
        deployments = self._observability.get_recent_deployments(
            function_name, lookback_minutes=60  # Wider window for deployments
        )
    except Exception:
        # Graceful degradation - return empty structure
        return self._empty_metrics_bundle(incident_key, function_name, alarm_name)
    
    # Step 3: Enrich metrics
    enrichment = self._enrich_metrics(
        alarm_metrics, lambda_metrics, deployments, now
    )
    enrichment["cache_hit"] = False
    
    # Step 4: Build bundle
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
        }
    }
    
    # Step 5: Store in DDB (via CorrelationRecord update)
    self._store_metrics(incident_key, bundle, now)
    
    return bundle
```

**Method: `_check_cache()` - Cache Strategy**:
```python
def _check_cache(self, incident_key: str) -> dict[str, Any] | None:
    """Checks if metrics exist in DDB and are fresh enough."""
    try:
        record = self._correlation.get(incident_key)
        if not record or not record.metrics:
            return None
        
        # Check staleness
        now = datetime.now(timezone.utc)
        age = now - record.metrics_collected_at
        
        if age.total_seconds() < self._cache_ttl:
            return record.metrics
        
        return None  # Stale
    except Exception:
        return None  # Cache miss
```

**Method: `_enrich_metrics()` - Enrichment Logic**:
```python
def _enrich_metrics(
    self,
    alarm_metrics: dict,
    lambda_metrics: dict,
    deployments: list[dict],
    now: datetime,
) -> dict[str, Any]:
    """Adds incident-focused enrichment to raw metrics.
    
    Returns enrichment dict with trend, deployment correlation, threshold validation."""
    
    # Limit deployments list to most recent 10 (prevent large DDB items)
    deployments = deployments[:10] if deployments else []
    
    # 1. Error Rate Trend
    error_rate = lambda_metrics.get("error_rate", 0.0)
    if error_rate > 10.0:
        trend = "increasing"
    elif error_rate < 2.0:
        trend = "decreasing"
    else:
        trend = "stable"
    
    # 2. Recent Deployment Detection
    recent_deployment = None
    deployment_correlation = "none"
    deployment_delta_minutes = None
    
    if deployments:
        most_recent = deployments[0]  # Already sorted by timestamp desc
        deploy_time = datetime.fromisoformat(most_recent["timestamp"])
        delta = now - deploy_time
        delta_minutes = int(delta.total_seconds() / 60)
        
        # Deployment correlation windows: 15 min = high, 30 min = medium, 60 min = low
        if delta < timedelta(minutes=15):
            recent_deployment = most_recent["version"]
            deployment_delta_minutes = delta_minutes
            
            # High correlation if errors AND recent deploy
            if error_rate > 5.0:
                deployment_correlation = "high"
            else:
                deployment_correlation = "medium"
        elif delta < timedelta(minutes=30):
            recent_deployment = most_recent["version"]
            deployment_delta_minutes = delta_minutes
            deployment_correlation = "medium"
        elif delta < timedelta(hours=1):
            recent_deployment = most_recent["version"]
            deployment_delta_minutes = delta_minutes
            deployment_correlation = "low"
    
    # 3. Alarm Threshold Validation
    alarm_config = alarm_metrics.get("alarm_config", {})
    threshold = alarm_config.get("threshold", 0.0)
    
    datapoints = alarm_metrics.get("datapoints", [])
    current_value = 0.0
    if datapoints:
        # Use most recent datapoint
        current_value = datapoints[-1].get("value", 0.0)
    
    threshold_exceeded = current_value > threshold
    
    return {
        "error_rate_trend": trend,
        "recent_deployment_detected": recent_deployment is not None,
        "recent_deployment_version": recent_deployment,
        "deployment_correlation": deployment_correlation,
        "deployment_time_delta_minutes": deployment_delta_minutes,
        "alarm_threshold_exceeded": threshold_exceeded,
        "alarm_threshold_value": threshold,
        "current_metric_value": current_value,
        "collected_at": now.isoformat(),
    }
```

**Method: `_store_metrics()` - Persistence**:
```python
def _store_metrics(self, incident_key: str, bundle: dict, collected_at: datetime) -> None:
    """Stores metrics bundle in DynamoDB via CorrelationRecord."""
    try:
        record = self._correlation.get(incident_key)
        if record:
            updated = record.with_metrics(bundle, collected_at)
            self._correlation.update(updated)
    except Exception:
        # Storage failure doesn't block metrics return
        pass
```

**Method: `_empty_metrics_bundle()` - Graceful Degradation**:
```python
def _empty_metrics_bundle(
    self, incident_key: str, function_name: str, alarm_name: str
) -> dict[str, Any]:
    """Returns empty structure on collection failure."""
    return {
        "alarm_metrics": {"alarm_config": {}, "datapoints": [], "current_state": "ERROR"},
        "lambda_metrics": {
            "invocations": 0, "errors": 0, "throttles": 0,
            "duration_avg": 0.0, "concurrent_executions_max": 0, "error_rate": 0.0
        },
        "deployments": [],
        "enrichment": {
            "error_rate_trend": "unknown",
            "recent_deployment_detected": False,
            "recent_deployment_version": None,
            "deployment_correlation": "none",
            "deployment_time_delta_minutes": None,
            "alarm_threshold_exceeded": False,
            "alarm_threshold_value": 0.0,
            "current_metric_value": 0.0,
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "cache_hit": False,
        },
        "collection_metadata": {
            "incident_key": incident_key,
            "function_name": function_name,
            "alarm_name": alarm_name,
            "lookback_minutes": 15,
        }
    }
```

---

### 2. CorrelationRecord Enhancement

**File**: `backend/lambdas/sre-platform/src/models/correlation_record.py`

**Changes**:
```python
class CorrelationRecord:
    def __init__(
        self,
        incident_key: str,
        service: str,
        stage: str,
        severity: str,
        jira_ticket_id: str = "",
        status: str = "",
        # ... existing fields ...
        metrics: dict | None = None,  # NEW
        metrics_collected_at: datetime | None = None,  # NEW
    ):
        # ... existing init ...
        self.metrics = metrics
        self.metrics_collected_at = metrics_collected_at
    
    def with_metrics(self, metrics: dict, collected_at: datetime) -> "CorrelationRecord":
        """Returns new record with metrics bundle stored.
        
        Args:
            metrics: Full metrics bundle from MetricsCollectionService
            collected_at: Timestamp when metrics were collected
        """
        self.metrics = metrics
        self.metrics_collected_at = collected_at
        return self
    
    def to_item(self) -> dict:
        """Serialize to DynamoDB item (includes metrics)."""
        item = {
            # ... existing fields ...
        }
        
        if self.metrics:
            item["metrics"] = self.metrics
            item["metrics_collected_at"] = self.metrics_collected_at.isoformat()
        
        return item
    
    @staticmethod
    def from_item(item: dict) -> "CorrelationRecord":
        """Deserialize from DynamoDB item (includes metrics)."""
        # ... existing parsing ...
        
        metrics = item.get("metrics")
        metrics_collected_at = None
        if item.get("metrics_collected_at"):
            metrics_collected_at = datetime.fromisoformat(item["metrics_collected_at"])
        
        return CorrelationRecord(
            # ... existing fields ...
            metrics=metrics,
            metrics_collected_at=metrics_collected_at,
        )
```

**DynamoDB Schema Update**:
```json
{
  "incident_key": "calculator-high-error-rate-prod-2026-04-03T10:00:00",
  "status": "DETECTED",
  "jira_ticket_id": "INCIDENT-123",
  "metrics": {
    "alarm_metrics": {...},
    "lambda_metrics": {...},
    "deployments": [...],
    "enrichment": {...}
  },
  "metrics_collected_at": "2026-04-03T10:00:15Z"
}
```

**Metrics Retention Strategy**:
- **Phase 2 Decision**: Metrics stored indefinitely in DynamoDB
- **Storage Cost**: $0.004/month for 3000 incidents (negligible)
- **Rationale**: Simplifies Phase 2 implementation; cost acceptable even at scale
- **Future Enhancement**: If storage becomes concern, implement 7-day cleanup via:
  - Option A: Scheduled Lambda clears `metrics` field after 7 days (keeps CorrelationRecord)
  - Option B: DynamoDB Streams trigger removes stale metrics
  - Option C: Accept indefinite storage (recommended - simplest, lowest operational overhead)

---

### 3. Detection Service Integration

**File**: `backend/lambdas/sre-platform/src/services/detection_service.py`

**Changes** (estimated location: after line 80, before DDB record creation):
```python
class DetectionService:
    def __init__(
        self,
        # ... existing dependencies ...
        metrics_collection_service,  # NEW
    ):
        # ... existing init ...
        self._metrics_service = metrics_collection_service
    
    @observe(operation="detect_incident", metric_prefix="detection")
    def detect(
        self,
        alarm_name: str,
        alarm_state: str,
        service: str,
        stage: str,
        # ... existing params ...
    ) -> str:
        # ... existing logic lines 1-80 ...
        
        # NEW: Collect metrics (after alarm validation, before DDB insert)
        function_name = build_function_name(service, stage)
        
        metrics_bundle = None
        try:
            metrics_bundle = self._metrics_service.collect_incident_metrics(
                incident_key=incident_key,
                function_name=function_name,
                alarm_name=alarm_name,
                lookback_minutes=15,
                force_refresh=False,
            )
        except Exception:
            # Graceful degradation - don't block incident creation
            pass
        
        # Create CorrelationRecord with metrics
        record = CorrelationRecord(
            incident_key=incident_key,
            # ... existing fields ...
        )
        
        if metrics_bundle:
            record = record.with_metrics(
                metrics_bundle,
                datetime.now(timezone.utc)
            )
        
        self._correlation.create(record)
        
        # ... existing Jira creation ...
        
        # Publish IncidentCreated with metrics in payload
        self._event_bus.publish_event(
            "IncidentCreated",
            {
                "incident_key": incident_key,
                "jira_ticket_id": ticket_id,
                "service": service,
                "stage": stage,
                "severity": severity,
                "function_name": function_name,
                "alarm_name": alarm_name,
                "metrics": metrics_bundle,  # NEW: Pass to Triage
                # ... existing fields ...
            },
        )
        
        return "detected"
```

---

### 4. Triage Service Integration

**File**: `backend/lambdas/sre-platform/src/services/triage_service.py`

**Changes** (line 59, add metrics parameter):
```python
@observe(operation="triage_incident", metric_prefix="triage")
def triage(
    self,
    incident_key: str,
    jira_ticket_id: str,
    service: str,
    stage: str,
    severity: str,
    service_type: str = "lambda",
    storm_detected: bool = False,
    recovery_model: str = "stateless",
    alarm_name: str = "",
    function_name: str = "",
    log_group: str = "",
    metric_name: str = "",
    metrics: dict | None = None,  # NEW: Metrics from Detection
) -> str:
    """Main entry point. Returns 'auto-resolved' or 'escalated'.
    
    Flow:
    1. Update DynamoDB -> TRIAGING
    2. Report triage started
    3. Analyze logs -> classify root cause -> assess blast radius
    4. Apply metrics-based escalation rules (NEW)
    5. Report analysis results
    6. Storm/timeout gates -> escalate if triggered
    7. Delegate remediation + verification -> escalate on failure
    8. Resolve: report + close ticket + GRACE + publish event
    """
    # ... existing lines 70-139 ...
    
    # NEW: Step 4.5 - Metrics-based escalation rules (after classification, before storm check)
    if metrics:
        enrichment = metrics.get("enrichment", {})
        
        # Rule 1: Recent deployment with high error correlation
        if enrichment.get("deployment_correlation") == "high":
            deployment_version = enrichment.get("recent_deployment_version")
            delta_min = enrichment.get("deployment_time_delta_minutes", 0)
            
            self._reporter.report_deployment_correlation(
                jira_ticket_id,
                deployment_version,
                delta_min,
                enrichment.get("error_rate_trend"),
            )
            
            return self._escalate(
                escalation_base,
                EscalationReason.RECENT_DEPLOYMENT,
                remediation_outcome="not-attempted",
                deployment_version=deployment_version,
                deployment_delta_minutes=delta_min,
                **escalation_context,
            )
        
        # Rule 2: Alarm threshold NOT exceeded (false alarm / metric lag)
        if not enrichment.get("alarm_threshold_exceeded"):
            threshold = enrichment.get("alarm_threshold_value", 0.0)
            current = enrichment.get("current_metric_value", 0.0)
            
            self._reporter.report_alarm_misconfiguration(
                jira_ticket_id,
                alarm_name,
                threshold,
                current,
            )
            
            return self._escalate(
                escalation_base,
                EscalationReason.ALARM_MISCONFIGURATION,
                remediation_outcome="not-attempted",
                alarm_threshold=threshold,
                current_metric_value=current,
                **escalation_context,
            )
        
        # Rule 3: Error rate decreasing (system self-healing)
        # Note: Don't auto-escalate, but flag for remediation priority
        if enrichment.get("error_rate_trend") == "decreasing":
            self._reporter.report_trend_analysis(
                jira_ticket_id,
                "decreasing",
                "System appears to be self-healing. Monitoring remediation urgency.",
            )
    
    # Continue with existing flow (lines 140-251)
    # ... existing storm check, timeout check, remediation, resolution ...
```

**New EscalationReason Enum Values**:
```python
# Add to src/models/enums.py
class EscalationReason:
    # ... existing reasons ...
    RECENT_DEPLOYMENT = "recent-deployment"  # NEW
    ALARM_MISCONFIGURATION = "alarm-misconfiguration"  # NEW
```

**New IncidentReporter Methods**:
```python
# Add to src/services/incident_reporter.py
def report_deployment_correlation(
    self, jira_ticket_id: str, version: str, delta_minutes: int, trend: str
) -> None:
    """Reports deployment correlation finding to Jira."""
    
def report_alarm_misconfiguration(
    self, jira_ticket_id: str, alarm_name: str, threshold: float, current: float
) -> None:
    """Reports alarm threshold validation failure to Jira."""
    
def report_trend_analysis(
    self, jira_ticket_id: str, trend: str, interpretation: str
) -> None:
    """Reports error rate trend analysis to Jira."""
```

---

### 5. Escalation Service Integration

**File**: `backend/lambdas/sre-platform/src/services/escalation_service.py`

**Changes** (line 29, add metrics_collection_service):
```python
def __init__(
    self,
    correlation_repo,
    log_analysis_service: LogAnalysisService,
    ticketing_repo,
    notification_repo,
    notification_topic_arn: str = "",
    ai_service=None,
    region: str = "us-west-2",
    delta_report_service=None,
    metrics_collection_service=None,  # NEW
):
    # ... existing init ...
    self._metrics_service = metrics_collection_service
```

**Changes** (line 85, after DDB update):
```python
@observe(operation="escalate_incident", metric_prefix="escalation")
def escalate(
    self,
    incident_key: str,
    jira_ticket_id: str,
    service: str,
    stage: str,
    severity: str,
    reason: str,
    function_name: str = "",
    # ... existing params ...
) -> str:
    """Main entry point. Returns 'escalated'.
    
    Flow:
    1. Update DynamoDB -> ESCALATED
    2. Collect fresh metrics (NEW - Timeline comparison)
    3. Collect diagnostic data (error logs)
    4. AI-analyze logs via AIAnalysisService (optional, graceful fallback)
    5. Enrich Jira with ADF-formatted comment (NEW - includes metrics timeline)
    6. Attach error logs as file
    7. Delta report for checkpoint-aware recovery models (reprocess)
    8. Notify engineer via SNS (SEV-1/SEV-2 only)
    """
    now = datetime.now(timezone.utc)
    
    # Step 1: Update DynamoDB -> ESCALATED
    existing = self._correlation.get(incident_key)
    if existing:
        self._correlation.update(existing.to_status(CorrelationStatus.ESCALATED))
    
    # NEW Step 2: Collect fresh metrics for timeline comparison
    effective_fn = function_name or build_function_name(service, stage)
    
    detection_metrics = None
    current_metrics = None
    
    if self._metrics_service:
        try:
            # Get Detection-time metrics from DDB
            if existing and existing.metrics:
                detection_metrics = existing.metrics
            
            # Collect fresh metrics (force refresh)
            alarm_name_derived = existing.alarm_name if existing else ""
            current_metrics = self._metrics_service.collect_incident_metrics(
                incident_key=incident_key,
                function_name=effective_fn,
                alarm_name=alarm_name_derived,
                lookback_minutes=15,
                force_refresh=True,  # Always get latest state
            )
        except Exception:
            # Graceful degradation
            pass
    
    # Step 3: Collect diagnostic data (existing)
    log_group = f"/aws/lambda/{effective_fn}"
    error_logs = self._log_analysis.collect_diagnostics(log_group)
    
    # ... existing AI analysis (lines 90-113) ...
    
    # Step 4: Build ADF-formatted Jira comment (ENHANCED with metrics timeline)
    adf_content = build_escalation_adf(
        incident_key=incident_key,
        service=service,
        stage=stage,
        severity=severity,
        reason=reason,
        function_name=effective_fn,
        log_group=log_group,
        error_logs=error_logs,
        verification=verification,
        root_cause=root_cause,
        timestamp=utc_timestamp(now),
        ai_analysis=ai_analysis,
        ai_references=ai_references,
        region=self._region,
        detection_metrics=detection_metrics,  # NEW
        current_metrics=current_metrics,      # NEW
    )
    self._ticketing.add_jira_comment_adf(jira_ticket_id, adf_content)
    
    # ... existing file attachment, delta report, notification (lines 135-171) ...
    
    return "escalated"
```

---

### 6. Jira ADF Formatting Enhancement

**File**: `backend/lambdas/sre-platform/src/domain/jira_formatting.py`

**Function**: `build_escalation_adf()` - Add metrics timeline section

**Changes** (add after line 150, before diagnostic links):
```python
def build_escalation_adf(
    incident_key: str,
    service: str,
    stage: str,
    severity: str,
    reason: str,
    function_name: str,
    log_group: str,
    error_logs: list[dict],
    verification: dict | None,
    root_cause: str,
    timestamp: str,
    ai_analysis: str | None,
    ai_references: list[str],
    region: str,
    detection_metrics: dict | None = None,  # NEW
    current_metrics: dict | None = None,     # NEW
) -> dict:
    """Builds ADF-formatted escalation comment with metrics timeline."""
    
    # ... existing heading, timestamp, reason sections ...
    
    # NEW: Metrics Timeline Section (if available)
    if detection_metrics and current_metrics:
        nodes.extend(_build_metrics_timeline_section(detection_metrics, current_metrics))
    
    # ... existing root cause, AI analysis, diagnostic links ...
    
    return {"version": 1, "type": "doc", "content": nodes}


def _build_metrics_timeline_section(
    detection_metrics: dict, current_metrics: dict
) -> list[dict]:
    """Builds ADF nodes for metrics timeline comparison.
    
    Shows Detection state (T0) vs Current state (T+N) with trend arrows."""
    
    det_lambda = detection_metrics.get("lambda_metrics", {})
    det_enrichment = detection_metrics.get("enrichment", {})
    det_time = det_enrichment.get("collected_at", "unknown")
    
    cur_lambda = current_metrics.get("lambda_metrics", {})
    cur_enrichment = current_metrics.get("enrichment", {})
    cur_time = cur_enrichment.get("collected_at", "unknown")
    
    # Calculate deltas
    det_error_rate = det_lambda.get("error_rate", 0.0)
    cur_error_rate = cur_lambda.get("error_rate", 0.0)
    error_rate_delta = cur_error_rate - det_error_rate
    
    det_errors = det_lambda.get("errors", 0)
    cur_errors = cur_lambda.get("errors", 0)
    
    # Trend indicators
    if error_rate_delta > 2:
        error_trend = f"↑ WORSENING (+{error_rate_delta:.1f}%)"
        error_emoji = "🔴"
    elif error_rate_delta < -2:
        error_trend = f"↓ IMPROVING ({error_rate_delta:.1f}%)"
        error_emoji = "🟢"
    else:
        error_trend = f"→ STABLE ({error_rate_delta:+.1f}%)"
        error_emoji = "🟡"
    
    # Deployment correlation
    deployment_note = ""
    if cur_enrichment.get("recent_deployment_detected"):
        version = cur_enrichment.get("recent_deployment_version")
        delta_min = cur_enrichment.get("deployment_time_delta_minutes", 0)
        correlation = cur_enrichment.get("deployment_correlation", "none")
        deployment_note = f"\n🚀 Recent Deployment: v{version} ({delta_min}min ago, correlation: {correlation.upper()})"
    
    nodes = [
        {
            "type": "heading",
            "attrs": {"level": 2},
            "content": [{"type": "text", "text": "📊 Metrics Timeline"}],
        },
        {
            "type": "table",
            "attrs": {"isNumberColumnEnabled": False, "layout": "default"},
            "content": [
                # Header row
                {
                    "type": "tableRow",
                    "content": [
                        {"type": "tableHeader", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Metric"}]}]},
                        {"type": "tableHeader", "content": [{"type": "paragraph", "content": [{"type": "text", "text": f"Detection ({det_time[:19]})"}]}]},
                        {"type": "tableHeader", "content": [{"type": "paragraph", "content": [{"type": "text", "text": f"Current ({cur_time[:19]})"}]}]},
                        {"type": "tableHeader", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Trend"}]}]},
                    ],
                },
                # Error Rate row
                {
                    "type": "tableRow",
                    "content": [
                        {"type": "tableCell", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Error Rate"}]}]},
                        {"type": "tableCell", "content": [{"type": "paragraph", "content": [{"type": "text", "text": f"{det_error_rate:.1f}%"}]}]},
                        {"type": "tableCell", "content": [{"type": "paragraph", "content": [{"type": "text", "text": f"{cur_error_rate:.1f}%"}]}]},
                        {"type": "tableCell", "content": [{"type": "paragraph", "content": [{"type": "text", "text": f"{error_emoji} {error_trend}"}]}]},
                    ],
                },
                # Error Count row
                {
                    "type": "tableRow",
                    "content": [
                        {"type": "tableCell", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Error Count"}]}]},
                        {"type": "tableCell", "content": [{"type": "paragraph", "content": [{"type": "text", "text": str(det_errors)}]}]},
                        {"type": "tableCell", "content": [{"type": "paragraph", "content": [{"type": "text", "text": str(cur_errors)}]}]},
                        {"type": "tableCell", "content": [{"type": "paragraph", "content": [{"type": "text", "text": f"{cur_errors - det_errors:+d}"}]}]},
                    ],
                },
                # Invocations row
                {
                    "type": "tableRow",
                    "content": [
                        {"type": "tableCell", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Invocations"}]}]},
                        {"type": "tableCell", "content": [{"type": "paragraph", "content": [{"type": "text", "text": str(det_lambda.get("invocations", 0))}]}]},
                        {"type": "tableCell", "content": [{"type": "paragraph", "content": [{"type": "text", "text": str(cur_lambda.get("invocations", 0))}]}]},
                        {"type": "tableCell", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "-"}]}]},
                    ],
                },
            ],
        },
    ]
    
    # Add deployment note if present
    if deployment_note:
        nodes.append({
            "type": "paragraph",
            "content": [{"type": "text", "text": deployment_note, "marks": [{"type": "strong"}]}],
        })
    
    return nodes
```

**Example Jira Ticket Output**:
```
🚨 INCIDENT ESCALATED: calculator-api-prod

⏰ TIMELINE
─────────────
10:00:00 - Alarm fired (high-error-rate)
10:05:23 - Escalated (no remediation available)

📊 METRICS TIMELINE
───────────────────────────────────────────────────────────────────
Metric          | Detection (10:00:15)  | Current (10:05:23)    | Trend
─────────────────────────────────────────────────────────────────── 
Error Rate      | 15.3%                 | 8.2%                  | 🟢 ↓ IMPROVING (-7.1%)
Error Count     | 50                    | 18                    | -32
Invocations     | 327                   | 220                   | -

🚀 Recent Deployment: v42 (12min ago, correlation: HIGH)

💡 ANALYSIS
─────────────
Root Cause: timeout_errors (medium confidence)
Evidence: ReadTimeout(15), ConnectionTimeout(10)

Likely Cause: Recent deployment v42 introduced performance regression.
Recommendation: Consider rollback to v41.

🔍 DIAGNOSTICS
─────────────
[CloudWatch Logs] [Lambda Function] [Recent Deployments]
```

---

## Infrastructure Changes

### IAM Policy Updates

**Required IAM Permissions** for CloudWatch API access:

#### Detection Lambda IAM Policy

**File**: `infra/stacks/detection_stack.py` (or equivalent)

```python
from aws_cdk import (
    aws_iam as iam,
    aws_lambda as lambda_,
)

# Grant CloudWatch metrics read permissions
detection_function.add_to_role_policy(
    iam.PolicyStatement(
        effect=iam.Effect.ALLOW,
        actions=[
            'cloudwatch:GetMetricStatistics',
            'cloudwatch:DescribeAlarms',
        ],
        resources=[
            f'arn:aws:cloudwatch:{region}:{account}:alarm:*',
        ],
        sid='AllowCloudWatchMetricsRead'
    )
)

# Grant Lambda function metadata read permissions
detection_function.add_to_role_policy(
    iam.PolicyStatement(
        effect=iam.Effect.ALLOW,
        actions=[
            'lambda:ListVersionsByFunction',
        ],
        resources=[
            f'arn:aws:lambda:{region}:{account}:function:*',
        ],
        sid='AllowLambdaMetadataRead'
    )
)
```

**Justification**:
- `cloudwatch:GetMetricStatistics`: Required for ObservabilityRepository.get_lambda_metrics()
- `cloudwatch:DescribeAlarms`: Required for ObservabilityRepository.get_alarm_metric_data()
- `lambda:ListVersionsByFunction`: Required for ObservabilityRepository.get_recent_deployments()

**Resource-Level Permissions**:
- CloudWatch alarms: `*` scoped to account (Detection can read any alarm that fires)
- Lambda functions: `*` scoped to account (Detection can query any function's deployments)

#### Triage Lambda IAM Policy

**No new permissions required** - Triage reads metrics from EventBridge event payload (no direct CloudWatch API calls).

#### Escalation Lambda IAM Policy

**File**: `infra/stacks/escalation_stack.py` (or equivalent)

```python
# Same as Detection Lambda (Escalation collects fresh metrics)
escalation_function.add_to_role_policy(
    iam.PolicyStatement(
        effect=iam.Effect.ALLOW,
        actions=[
            'cloudwatch:GetMetricStatistics',
            'cloudwatch:DescribeAlarms',
        ],
        resources=[
            f'arn:aws:cloudwatch:{region}:{account}:alarm:*',
        ],
        sid='AllowCloudWatchMetricsRead'
    )
)

escalation_function.add_to_role_policy(
    iam.PolicyStatement(
        effect=iam.Effect.ALLOW,
        actions=[
            'lambda:ListVersionsByFunction',
        ],
        resources=[
            f'arn:aws:lambda:{region}:{account}:function:*',
        ],
        sid='AllowLambdaMetadataRead'
    )
)
```

### Lambda Configuration Updates

#### Detection Lambda Timeout Verification

**Action**: Verify current timeout configuration supports +500ms metrics collection overhead.

**Current State**:
- Detection Lambda baseline: ~1.4s
- With metrics collection: ~1.9s

**Required Configuration**:
```python
detection_function = lambda_.Function(
    self, 'DetectionFunction',
    timeout=Duration.seconds(10),  # Ensure at least 5s, recommend 10s for safety margin
    # ... other config
)
```

**Verification Steps** (Phase 2A):
1. Check current timeout: `aws lambda get-function-configuration --function-name detection-{env}`
2. If timeout < 5s, update to 10s (provides 5x safety margin for 1.9s execution)
3. Deploy updated timeout before Phase 2B (Detection integration)

### DynamoDB Schema Changes

**Table**: `correlation-records-{env}`

**New Fields** (additive only, backward compatible):
- `metrics` (Map, optional): Full metrics bundle from MetricsCollectionService
- `metrics_collected_at` (String, ISO 8601, optional): Timestamp when metrics were collected

**Schema Evolution Strategy**:
- ✅ Additive only (no breaking changes)
- ✅ Old records without metrics field remain valid
- ✅ New records with metrics field readable by old code (ignored)
- ✅ No migration required (field presence checked at runtime)

**Item Size Impact**:
- Baseline CorrelationRecord: ~1 KB
- With metrics bundle: ~3-6 KB (depends on deployment count)
- Limit: 400 KB (DynamoDB max item size)
- Safety margin: 60x (well within limits)

### Environment-Specific Configuration

**Cache TTL Per Environment**:

```python
# In CDK stack or config
CACHE_TTL_SECONDS = {
    'dev': 60,      # 1 minute (faster iteration, more API calls)
    'staging': 120,  # 2 minutes (matches prod)
    'prod': 120,     # 2 minutes (balance freshness vs cost)
}

metrics_service = MetricsCollectionService(
    observability_repo=observability_repo,
    correlation_repo=correlation_repo,
    cache_ttl_seconds=CACHE_TTL_SECONDS.get(environment, 120),
)
```

---

## Metrics-Based Escalation Rules

### Rule Definitions (Phase 2)

| Rule ID | Trigger Condition | Escalation Reason | Rationale |
|---------|-------------------|-------------------|-----------|
| **MER-1** | `deployment_correlation == "high"` | `RECENT_DEPLOYMENT` | Errors correlate with deployment within 15 min → likely bad release |
| **MER-2** | `alarm_threshold_exceeded == false` | `ALARM_MISCONFIGURATION` | Alarm fired but threshold not exceeded → false alarm or metric lag |

**Implementation Location**: TriageService lines 746-790 (after classification, before storm check, before remediation)

**Configuration** (add to `incident_config.json`):
```json
{
  "metrics_escalation_rules": {
    "deployment_correlation_threshold": "high",
    "alarm_threshold_tolerance": 0.1
  }
}
```

**Future Rules (Phase 3 or later)**:
- MER-3: `error_rate_trend == "increasing"` AND `remediation == "attempted"` → escalate VERIFICATION_FAILED_TREND (requires post-remediation metrics)
- MER-4: `throttles > 0` AND `concurrent_executions_max > 50` → escalate CAPACITY_EXHAUSTION (requires capacity planning baseline)

---

## Performance Analysis

### Timeline Breakdown

**Detection Lambda** (with metrics collection):
```
┌────────────────────────────────────────────────────────────────┐
│ Detection Lambda Execution                                     │
├────────────────────────────────────────────────────────────────┤
│ 1. Alarm validation                    50ms                    │
│ 2. Cooloff check (DDB)                100ms                    │
│ 3. Metrics collection (NEW)           450ms  ← Added           │
│    - get_alarm_metric_data()          150ms                    │
│    - get_lambda_metrics() (parallel)  150ms                    │
│    - get_recent_deployments()         150ms                    │
│ 4. Enrichment logic                    50ms  ← Added           │
│ 5. DDB insert (with metrics)          150ms                    │
│ 6. Jira ticket creation                500ms                   │
│ 7. EventBridge publish                 100ms                   │
├────────────────────────────────────────────────────────────────┤
│ TOTAL: 1.4s → 1.9s (+500ms)           ✅ Under 5s budget      │
└────────────────────────────────────────────────────────────────┘
```

**Triage Lambda** (reads from event):
```
┌────────────────────────────────────────────────────────────────┐
│ Triage Lambda Execution                                        │
├────────────────────────────────────────────────────────────────┤
│ 1. Parse event (includes metrics)       10ms  ← No change     │
│ 2. Metrics-based rules check (NEW)      20ms  ← Added         │
│ 3. Log analysis                         800ms                  │
│ 4. AI classification                   2000ms                  │
│ 5. Remediation + verification          1500ms                  │
│ 6. DDB update + Jira                    300ms                  │
├────────────────────────────────────────────────────────────────┤
│ TOTAL: 4.6s → 4.62s (+20ms)            ✅ Under 10s budget    │
└────────────────────────────────────────────────────────────────┘
```

**Escalation Lambda** (force refresh):
```
┌────────────────────────────────────────────────────────────────┐
│ Escalation Lambda Execution                                    │
├────────────────────────────────────────────────────────────────┤
│ 1. DDB read (get Detection metrics)    100ms                   │
│ 2. Fresh metrics collection (NEW)      450ms  ← Added         │
│ 3. Log diagnostics                      300ms                  │
│ 4. AI analysis                         2000ms                  │
│ 5. Build ADF (with timeline, NEW)      150ms  ← +50ms         │
│ 6. Jira enrichment + attachment         800ms                  │
│ 7. SNS notification                     100ms                  │
├────────────────────────────────────────────────────────────────┤
│ TOTAL: 3.4s → 4.0s (+600ms)            ✅ Under 8s budget     │
└────────────────────────────────────────────────────────────────┘
```

### Cache Performance (Escalation Scenario)

**Scenario**: Escalation occurs < 2 minutes after Detection

**Without Cache** (force_refresh=True):
- CloudWatch API calls: 5
- Latency: 450ms
- Cost: $0.00005 per incident

**With Cache** (stale check passes):
- CloudWatch API calls: 0
- Latency: 10ms (DDB read only)
- Cost: $0 (no CloudWatch calls)

**Cache Hit Rate** (estimated):
- Fast escalations (< 2min): 30% of incidents → cache hit
- Slow escalations (> 2min): 70% of incidents → cache miss (force refresh)
- **Effective API call reduction**: 15% (30% cache hit rate on 50% of API calls)

---

## Cost Analysis

### CloudWatch API Costs

**Pricing** (us-west-2):
- GetMetricStatistics: $0.01 per 1,000 requests
- DescribeAlarms: $0.01 per 1,000 requests
- Lambda ListVersionsByFunction: Free (control plane API)

**Per-Incident Breakdown**:
| Stage | API Calls | Cost per Incident |
|-------|-----------|-------------------|
| Detection | 5 calls (alarm + 5 metrics + deployments) | $0.00007 |
| Escalation (no cache) | 5 calls | $0.00007 |
| Escalation (cache hit) | 0 calls | $0 |

**Monthly Estimate** (100 incidents/day):
- Total incidents: 3,000/month
- Escalations: 1,500/month (50% escalation rate)
- Cache hits: 450/month (30% of escalations)
- Cache misses: 1,050/month

**Total API calls**:
- Detection: 3,000 × 5 = 15,000 calls
- Escalation: 1,050 × 5 = 5,250 calls
- **Total**: 20,250 calls/month

**Monthly Cost**: 20,250 ÷ 1,000 × $0.01 = **$0.20/month**

**Conclusion**: Negligible cost impact.

---

## Testing Strategy

### Unit Tests

**Test Files**:
1. `tests/unit/test_metrics_collection_service.py` - 250 lines, 15 test cases
2. `tests/unit/test_correlation_record.py` - Add metrics serialization tests (3 cases)
3. `tests/unit/test_detection_service.py` - Add metrics collection tests (2 cases)
4. `tests/unit/test_triage_service.py` - Add metrics-based escalation rule tests (4 cases)
5. `tests/unit/test_escalation_service.py` - Add fresh metrics collection tests (3 cases)

**Coverage Target**: 95% for new code

**Test Scenarios**:
- MetricsCollectionService:
  - ✅ Successful collection (all APIs return data)
  - ✅ Cache hit (metrics < 2 min old)
  - ✅ Cache miss (metrics > 2 min old)
  - ✅ Force refresh bypasses cache
  - ✅ Partial failure (alarm found, Lambda metrics fail)
  - ✅ Complete failure (graceful degradation)
  - ✅ Enrichment: deployment correlation high
  - ✅ Enrichment: deployment correlation medium/low/none
  - ✅ Enrichment: alarm threshold validation
  - ✅ Enrichment: error rate trend (increasing/stable/decreasing)
  - ✅ Storage success
  - ✅ Storage failure (doesn't block return)

- CorrelationRecord:
  - ✅ Serialize with metrics
  - ✅ Deserialize with metrics
  - ✅ with_metrics() updates correctly

- Detection Integration:
  - ✅ Metrics collected and stored in DDB
  - ✅ Metrics included in EventBridge payload
  - ✅ Metrics failure doesn't block incident creation

- Triage Integration:
  - ✅ Escalation rule MER-1: deployment correlation high
  - ✅ Escalation rule MER-2: alarm misconfiguration
  - ✅ No escalation: error rate decreasing (self-healing trend flagged but not escalated)

- Escalation Integration:
  - ✅ Fresh metrics collected (force_refresh=True)
  - ✅ Detection metrics retrieved from DDB
  - ✅ Timeline comparison in ADF output

### Integration Tests

**Test Files**:
1. `tests/integration/test_metrics_workflow_e2e.py` - 200 lines, 5 scenarios

**Scenarios**:
1. **Happy Path**: Detection → Triage (auto-resolved) with metrics
2. **Escalation Path**: Detection → Triage (escalate) → Escalation with timeline
3. **Cache Hit Path**: Detection at T0, Escalation at T+1min (cache hit)
4. **Deployment Correlation**: Recent deploy + high errors → auto-escalate
5. **False Alarm**: Alarm fires but threshold not exceeded → auto-escalate

**Requirements**: Real AWS resources (CloudWatch, DynamoDB, Lambda)

---

## Migration Plan

### Phase 2A: Infrastructure (Week 1)
1. ✅ Create `MetricsCollectionService` class
2. ✅ Add `metrics` and `metrics_collected_at` fields to `CorrelationRecord`
3. ✅ Add IAM policies to Detection and Escalation Lambda CDK stacks (CloudWatch + Lambda API permissions)
4. ✅ Verify Detection Lambda timeout configuration (ensure ≥5s, recommend 10s)
5. ✅ Configure environment-specific cache TTL (dev: 60s, staging/prod: 120s)
6. ✅ Write unit tests for `MetricsCollectionService` (15 tests)
7. ✅ Write unit tests for `CorrelationRecord` enhancements (3 tests)

### Phase 2B: Detection Integration (Week 2)
1. ✅ Update `DetectionService` to inject `MetricsCollectionService`
2. ✅ Add metrics collection after alarm validation
3. ✅ Update DDB schema (add metrics fields)
4. ✅ Update EventBridge payload (include metrics)
5. ✅ Write unit tests for Detection integration (2 tests)
6. ✅ Deploy Detection Lambda

### Phase 2C: Triage Integration (Week 2)
1. ✅ Update `TriageService.triage()` signature (add metrics param)
2. ✅ Implement metrics-based escalation rules (MER-1: deployment correlation, MER-2: alarm misconfiguration)
3. ✅ Add new `EscalationReason` enum values (RECENT_DEPLOYMENT, ALARM_MISCONFIGURATION)
4. ✅ Update `IncidentReporter` with new methods (report_deployment_correlation, report_alarm_misconfiguration, report_trend_analysis)
5. ✅ Write unit tests for Triage integration (3 tests: MER-1, MER-2, self-healing flag)
6. ✅ Deploy Triage Lambda

### Phase 2D: Escalation Integration (Week 3)
1. ✅ Update `EscalationService` to inject `MetricsCollectionService`
2. ✅ Add fresh metrics collection (force_refresh=True)
3. ✅ Update `build_escalation_adf()` with timeline section
4. ✅ Implement `_build_metrics_timeline_section()` (200 lines)
5. ✅ Write unit tests for Escalation integration (3 tests)
6. ✅ Deploy Escalation Lambda

### Phase 2E: Integration Testing (Week 3)
1. ✅ Write end-to-end integration tests (5 scenarios)
2. ✅ Run against dev environment
3. ✅ Validate Jira ticket formatting
4. ✅ Measure performance (Detection, Triage, Escalation latencies)

### Phase 2F: Production Deployment (Week 4)
1. ✅ Deploy to staging
2. ✅ Run smoke tests (10 simulated incidents)
3. ✅ Monitor metrics: cache_hit_rate, api_call_count, collection_duration
4. ✅ Deploy to production (blue-green)
5. ✅ Post-deployment validation (next real incident)

---

## Success Criteria

### Quantitative Metrics

| Metric | Baseline (Phase 1) | Target (Phase 2) | Measurement |
|--------|-------------------|------------------|-------------|
| Incident Ticket Usefulness | 3-4/10 | 7-8/10 | SRE survey (5 engineers) |
| Time to Diagnosis | ~15 min | ~8 min | CloudWatch Insights (MTTR) |
| False Escalations | 30% | 15% | % of escalations closed as "false alarm" |
| Cache Hit Rate | N/A | 30% | CloudWatch metric |
| Detection Lambda P95 | 1.4s | < 2.0s | CloudWatch metric |
| Escalation Lambda P95 | 3.4s | < 4.5s | CloudWatch metric |

### Qualitative Goals

✅ Engineers can see timeline evolution (Detection state vs Current state)  
✅ Recent deployments auto-flagged with correlation strength  
✅ Alarm misconfiguration detected automatically  
✅ Metrics collection failures don't break incident workflow  
✅ Jira tickets contain actionable context (trend arrows, deployment notes)

---

## Rollback Plan

### Triggers
- Detection/Triage/Escalation Lambda errors > 5%
- DynamoDB throttling on metrics writes
- Incident creation latency > 5s (P95)
- Cache corruption (stale data served)

### Rollback Steps
1. Deploy previous Lambda versions (blue-green rollback)
2. EventBridge continues to work (metrics field optional)
3. Old Lambdas ignore metrics field (graceful degradation)
4. DynamoDB schema backward compatible (metrics fields optional)

### Data Integrity
- Metrics fields are **additive only** (no breaking changes)
- Old records without metrics field still valid
- New records with metrics field readable by old code (ignored)

---

## Design Decisions

### Resolved Design Questions

1. **Metrics Retention**: ✅ **DECIDED: Indefinite storage (Phase 2)**
   - Metrics stored indefinitely in DynamoDB (no automatic cleanup in Phase 2)
   - Storage cost: $0.004/month for 3000 incidents (negligible)
   - Rationale: Simplifies Phase 2 implementation; cost acceptable even at scale
   - Future Enhancement: If needed, implement 7-day cleanup in future phase (deferred)

2. **Cache TTL Configuration**: ✅ **DECIDED: Environment-specific**
   - Dev: 60s (faster iteration, more frequent API calls acceptable)
   - Staging: 120s (matches prod behavior)
   - Prod: 120s (balance freshness vs cost)
   - Configuration: See "Infrastructure Changes" section above

3. **Metrics-Based Auto-Resolution**: ✅ **DECIDED: Deferred to Phase 3**
   - NOT included in Phase 2 scope
   - Rationale: Risk of premature resolution if transient improvement
   - Plan: Observe Phase 2 operational data, design Phase 3 with auto-resolution rules
   - Example future rule: Error rate < 1% AND trend = "decreasing" for 5 consecutive minutes → auto-resolve

4. **Deployment Correlation Thresholds**: ✅ **DECIDED: 15/30/60 min calibration**
   - 0-15 min: HIGH correlation (deployment very recent)
   - 15-30 min: MEDIUM correlation (deployment recent)
   - 30-60 min: LOW correlation (deployment older, less likely cause)
   - \>60 min: NONE (deployment too old to be primary cause)
   - Implementation: See `_enrich_metrics()` method above
   - Note: Thresholds may be tuned in Phase 2E integration testing with real data

---

## References

- [Phase 1 Design: Metrics Collection Enhancement](./metrics-collection-enhancement.md)
- [Phase 1 Review](./reviews/metrics-collection-enhancement-review.md)
- [AWS CloudWatch Metrics API](https://docs.aws.amazon.com/AmazonCloudWatch/latest/APIReference/API_GetMetricStatistics.html)
- [AWS Lambda Metrics](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-metrics.html)
- [Jira ADF Specification](https://developer.atlassian.com/cloud/jira/platform/apis/document/structure/)

---

**Status**: 🔄 Design In Progress  
**Next Steps**: 
1. Run `/system-design` skill for requirements validation
2. Run `/design-review` for architecture validation
3. Seek approval before implementation
