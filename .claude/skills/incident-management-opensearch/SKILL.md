---
name: incident-management-opensearch
description: "OpenSearch incident patterns — cluster health, disk/JVM pressure, indexing failures, search latency."
---

# Incident Management — OpenSearch (Addendum)

> Extends `incident-management.md`. Covers Amazon OpenSearch Service-specific alarms, failure patterns, queries, and decision trees.

---

## ALARM DEFINITIONS

| Alarm Type | Metric / Namespace | Statistic | Direction | Threshold | Period |
|-----------|-------------------|-----------|-----------|-----------|--------|
| `cluster-red` | ClusterStatus.red — AWS/ES | Max | high | 1 | 60s × 1 |
| `cluster-yellow` | ClusterStatus.yellow — AWS/ES | Max | high | 1 | 60s × 5 |
| `free-storage` | FreeStorageSpace — AWS/ES | Min | low | 20% of total | 300s × 3 |
| `jvm-memory-pressure` | JVMMemoryPressure — AWS/ES | Max | high | 80% | 300s × 3 |
| `cpu-utilization` | CPUUtilization — AWS/ES | Average | high | 80% | 300s × 3 |
| `indexing-latency` | IndexingLatency — AWS/ES | Average | high | 100ms | 60s × 5 |
| `search-latency` | SearchLatency — AWS/ES | p99 | high | 500ms | 60s × 5 |
| `snapshot-failure` | AutomatedSnapshotFailure — AWS/ES | Max | high | 1 | 300s × 1 |
| `write-rejected` | ThreadpoolWriteRejected — AWS/ES | Sum | high | 0 | 60s × 3 |
| `search-rejected` | ThreadpoolSearchRejected — AWS/ES | Sum | high | 0 | 60s × 3 |

---

## FAILURE MODE CLASSIFICATION

| Pattern | Indicators | Classification | Confidence |
|---------|-----------|---------------|------------|
| `cluster_health_red` | ClusterStatus.red = 1, unassigned primary shards | `data-loss-risk` | critical |
| `cluster_health_yellow` | ClusterStatus.yellow = 1, unassigned replica shards | `reduced-redundancy` | high |
| `disk_pressure_pattern` | FreeStorageSpace < 20%, write rejections increasing | `disk-pressure` | high |
| JVM memory pressure | JVMMemoryPressure > 80%, GC pauses | `jvm-pressure` | high |
| Write rejection | ThreadpoolWriteRejected > 0, indexing latency spike | `write-saturation` | high |
| Search degradation | SearchLatency p99 spike, ThreadpoolSearchRejected | `search-saturation` | medium |
| Snapshot failure | AutomatedSnapshotFailure = 1 | `backup-failure` | medium |

---

## DIAGNOSTIC QUERIES

**Cluster health check (API):**
```bash
GET _cluster/health
GET _cluster/allocation/explain  # why shards are unassigned
GET _cat/shards?v&h=index,shard,prirep,state,unassigned.reason
```

**Slow log analysis** (if slow logs enabled, log group: `/aws/opensearch/domains/{domain}/slow-logs`):
```
fields @timestamp, @message
| parse @message 'took[*]' as duration_ms
| filter duration_ms > 500
| stats count() as slow_queries, avg(duration_ms) as avg_slow by bin(5m)
```

**Index error log analysis** (log group: `/aws/opensearch/domains/{domain}/index-slow-logs`):
```
fields @timestamp, @message
| filter @message like /rejected|BulkItemResponse|MapperParsingException/
| stats count() as errors by bin(5m)
```

**Hot index identification (API):**
```bash
GET _cat/indices?v&s=docs.count:desc&h=index,docs.count,store.size,pri,rep
GET _cat/indices?v&s=store.size:desc&h=index,store.size,docs.count
```

**Shard distribution (API):**
```bash
GET _cat/shards?v&h=index,shard,prirep,state,node,store
GET _cat/allocation?v  # disk usage per node
```

---

## DECISION TREE

```
ALARM FIRES
│
├─ cluster-red
│   ├─ Unassigned primary shards?
│   │   ├─ Node failure? → wait for auto-recovery (if zone-aware) → ESCALATE
│   │   └─ Disk full on node? → delete old indices → force shard allocation → ESCALATE
│   └─ Snapshot restore failed?
│       └─ RESTORE ISSUE → check snapshot status → ESCALATE
│
├─ cluster-yellow
│   ├─ Insufficient nodes for replicas?
│   │   └─ Scale data nodes → ESCALATE
│   └─ Recently created index with pending replicas?
│       └─ TRANSIENT → monitor, should resolve within minutes
│
├─ free-storage (low)
│   ├─ Old indices consuming space?
│   │   └─ DELETE OLD INDICES → apply retention policy [MANUAL]
│   ├─ Index bloat (deleted docs not reclaimed)?
│   │   └─ FORCE MERGE → run _forcemerge on read-only indices [MANUAL]
│   └─ Data volume growing faster than expected?
│       └─ SCALE STORAGE → increase volume size or add data nodes → ESCALATE
│
├─ jvm-memory-pressure
│   ├─ Large aggregation queries?
│   │   └─ QUERY ISSUE → optimize queries, add circuit breaker → ESCALATE
│   ├─ Too many shards per node?
│   │   └─ SHARD OVERALLOCATION → merge small indices, reduce shard count → ESCALATE
│   └─ Field data cache too large?
│       └─ FIELD DATA → use keyword fields, set fielddata circuit breaker → ESCALATE
│
├─ indexing-latency / write-rejected
│   ├─ Disk I/O saturated?
│   │   └─ DISK BOTTLENECK → upgrade to gp3/io1 volumes → ESCALATE
│   ├─ Bulk indexing too large?
│   │   └─ BULK SIZE → reduce bulk request size → ESCALATE
│   └─ Mapping explosion (too many fields)?
│       └─ MAPPING ISSUE → set strict mapping, limit dynamic fields → ESCALATE
│
├─ search-latency / search-rejected
│   ├─ Expensive queries (wildcard, deep pagination)?
│   │   └─ QUERY OPTIMIZATION → rewrite queries, use search_after → ESCALATE
│   └─ Too few data nodes for query volume?
│       └─ SCALE → add data nodes → ESCALATE
│
└─ snapshot-failure
    └─ Check S3 bucket permissions, repo registration → ESCALATE
```

---

## REMEDIATION ACTIONS

| Classification | Action | Automation |
|---------------|--------|-----------|
| `data-loss-risk` | Investigate unassigned shards, restore from snapshot | MANUAL (critical) |
| `reduced-redundancy` | Scale data nodes, rebalance shards | MANUAL |
| `disk-pressure` | Delete old indices, force merge | MANUAL |
| `jvm-pressure` | Optimize queries, reduce shard count | MANUAL |
| `write-saturation` | Reduce bulk size, scale data nodes | MANUAL |
| `search-saturation` | Optimize queries, add data nodes | MANUAL |
| `backup-failure` | Fix S3 permissions, re-register snapshot repo | MANUAL |

**Proposed additions to `remediation_catalog`:**
```json
"disk-pressure":  { "action": "opensearch-delete-old-indices" }
"data-loss-risk": { "action": "opensearch-scale-data-nodes" }
```

All OpenSearch remediations are MANUAL due to the risk of data loss from automated actions on a stateful system.

---

## SERVICE-SPECIFIC GOTCHAS

**Disk watermarks**: At 85% disk usage, OpenSearch stops allocating new shards. At 90%, it starts relocating shards. At 95%, it enforces a read-only index block. Monitor before 85%.

**Shard sizing rule of thumb**: Target 10-50GB per shard. Too many small shards waste JVM heap. Too few large shards cause slow recovery and uneven distribution.

**Zone awareness**: Multi-AZ deployments require an even number of data nodes across AZs. Losing one AZ should not cause red status if replicas are in the surviving AZ.

**UltraWarm and cold storage**: For log/time-series data, move old indices to UltraWarm (cheaper, slower) rather than deleting. Reduces cost without losing data.

**Index lifecycle**: Use ISM (Index State Management) policies to automate rollover, warm migration, and deletion. Missing ISM policies are the top cause of disk-pressure incidents.
