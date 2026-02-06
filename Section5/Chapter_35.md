# Chapter 35: Metrics Collection System

---

# Introduction

Every production system generates signals—request counts, error rates, latency percentiles, CPU usage, queue depths. A metrics collection system is the infrastructure that captures these signals, stores them as time-series data, and makes them queryable for dashboards and alerts. Without it, you're operating blind: you can't tell if your system is healthy, can't detect regressions, and can't investigate incidents.

I've built metrics pipelines that ingested 5 million data points per second from thousands of microservices, debugged silent data loss where an overloaded collector was dropping 20% of metrics and nobody noticed for a week because the dashboards still "looked normal," and designed retention policies that kept costs manageable while preserving the data engineers actually need during incidents. The lesson: a metrics system that loses data or delivers it late is worse than no metrics system, because it creates false confidence.

This chapter covers a metrics collection system as a Senior Engineer owns it: ingestion, storage, querying, alerting, and the operational reality of keeping the system that monitors everything else reliable.

**The Senior Engineer's First Law of Metrics**: The metrics system is the last system that should go down. If it's unreliable, every other system becomes unobservable.

---

# Part 1: Problem Definition & Motivation

## What Is a Metrics Collection System?

A metrics collection system collects numerical measurements (counters, gauges, histograms) from applications and infrastructure, stores them as time-series data indexed by metric name and labels, and serves queries for dashboards, alerts, and ad-hoc analysis. It answers the question: "What is happening in my systems right now, and what happened in the last hour/day/week?"

### Simple Example

```
METRICS COLLECTION OPERATIONS:

    EMIT:
        Application increments counter:
            http_requests_total{service="api", method="GET", status="200"} += 1
        
        Application records latency:
            http_request_duration_ms{service="api", endpoint="/users"} = 42

    COLLECT:
        Collector scrapes or receives metrics every 15 seconds
        → Batch of ~1,000 data points per service instance
        → Write to time-series storage

    QUERY:
        Engineer asks: "What's the P99 latency for /users endpoint over last hour?"
        → Query: histogram_quantile(0.99, rate(http_request_duration_ms{endpoint="/users"}[1h]))
        → Returns: Time-series of P99 values, one point per 15-second interval

    ALERT:
        Rule: IF error_rate{service="api"} > 5% FOR 5 minutes THEN page on-call
        → Evaluates every 60 seconds
        → Fires alert → routes to PagerDuty/Slack
```

## Why Metrics Collection Systems Exist

You cannot improve what you cannot measure, and you cannot debug what you cannot observe.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    WHY BUILD A METRICS SYSTEM?                              │
│                                                                             │
│   WITHOUT METRICS:                                                          │
│   ├── SSH into each server and grep logs for errors (doesn't scale)         │
│   ├── Discover problems from user complaints (too late)                     │
│   ├── No quantitative capacity planning ("feels slow" vs "P99 = 800ms")     │
│   ├── No automated alerting (human eyeballs on dashboards 24/7)             │
│   └── Postmortems without data ("we think it started around 2 AM")          │
│                                                                             │
│   WITH METRICS:                                                             │
│   ├── Real-time visibility into all services (dashboards)                   │
│   ├── Automated alerting on anomalies (error rate, latency, saturation)     │
│   ├── Quantified SLOs: "99.9% of requests under 200ms" (provable)           │
│   ├── Capacity planning: "At current growth, we exhaust DB connections      │
│   │   in 6 weeks"                                                           │
│   ├── Incident investigation: "Latency spiked at 14:32, correlated with     │
│   │   deploy at 14:30"                                                      │
│   └── Trend analysis: "Error rate increasing 0.1% per week since v2.3"      │
│                                                                             │
│   KEY INSIGHT:                                                              │
│   Metrics are NOT logs. Logs are events (text, high cardinality, expensive  │
│   to query). Metrics are aggregated numerical measurements (low cardinality,│
│   cheap to query, purpose-built for time-series analysis).                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Problem 1: Scale of Observability Data

```
CHALLENGE:

500 microservice instances, each emitting 200 unique metrics
    - With 10 label combinations each: 500 × 200 × 10 = 1,000,000 active time series
    - Collected every 15 seconds: ~67,000 data points/second
    - Stored for 30 days: ~170 billion data points

Log-based approach: grep + awk across 500 servers
    - Latency: minutes to hours
    - No aggregation (must compute percentiles manually)
    - No alerting capability

Metrics approach: Pre-aggregated time-series database
    - Query: rate(http_requests_total{service="api"}[5m])
    - Latency: < 500ms
    - Alerting: Continuous evaluation, sub-minute detection
```

### Problem 2: The Freshness-Cost Tension

```
TENSION:

Engineers want:
    - Real-time metrics (< 30 second delay)
    - High resolution (1-second granularity)
    - Long retention (1 year of history)
    - High cardinality (per-user, per-request-ID)

Reality:
    - 1-second resolution × 1M series × 365 days = 31.5 trillion data points
    - Storage: ~250 TB (uncompressed)
    - Query: Full-year query scans billions of rows

SENIOR APPROACH:
    - High resolution (15s) for recent data (48 hours)
    - Downsampled (5m average) for medium-term (30 days)
    - Further downsampled (1h average) for long-term (1 year)
    - Cost: ~5 TB total (50× reduction)
    
    This is a trade-off, not a limitation. A Senior engineer designs
    the retention policy based on actual query patterns:
    - Incident investigation: needs 15s resolution (last 48 hours)
    - Trend analysis: 5m resolution is sufficient
    - Capacity planning: 1h resolution is plenty
```

---

# Part 2: Users & Use Cases

## User Categories

| Category | Who | How They Use Metrics |
|----------|-----|---------------------|
| **Service engineers** | Developers owning microservices | Dashboards, ad-hoc queries, incident debugging |
| **SREs / On-call** | Reliability engineers | Alerts, incident response, SLO tracking |
| **Platform team** | Infrastructure operators | Capacity planning, infrastructure health |
| **Automated systems** | Alert evaluator, autoscalers | Continuous metric queries for decisions |

## Core Use Cases

```
USE CASE 1: REAL-TIME MONITORING
    Engineer opens dashboard → sees current QPS, latency, error rate
    Freshness: < 30 seconds
    Resolution: 15 seconds

USE CASE 2: ALERTING
    Alert rule: error_rate > 5% for 5 minutes
    System evaluates rule every 60 seconds
    Fires alert → routes to on-call via PagerDuty
    Requirement: No false negatives (missed real alerts)

USE CASE 3: INCIDENT INVESTIGATION
    2 AM page: "API latency elevated"
    Engineer queries: latency by endpoint, by region, by instance
    Correlates with: deploy time, error count, dependency latency
    Requirement: Ad-hoc queries with < 2 second response

USE CASE 4: SLO TRACKING
    "99.9% of requests complete under 200ms over trailing 30 days"
    Requires: Accurate percentile computation over 30 days of data
    Used for: Error budget calculation, release decisions

USE CASE 5: CAPACITY PLANNING
    "At current growth rate, DB connection pool exhausts in 6 weeks"
    Requires: Trend analysis over weeks/months
    Resolution: 1-hour averages are sufficient
```

## Non-Goals

```
NON-GOALS (Explicitly Out of Scope):

1. LOG AGGREGATION
   Logs are text events with high cardinality. Metrics are numerical
   aggregates. Different storage, different query patterns, different systems.

2. DISTRIBUTED TRACING
   Tracing tracks individual request flows across services. Metrics
   track aggregated measurements. Complementary but separate systems.

3. BUSINESS ANALYTICS
   Revenue, user signups, conversion funnels—these belong in a data
   warehouse (BigQuery, Snowflake), not a metrics system.

4. PER-REQUEST / PER-USER METRICS
   High-cardinality labels (user_id, request_id) explode time-series count.
   Metrics system handles bounded cardinality labels only.

5. MULTI-CLUSTER FEDERATION
   V1: Single cluster. Cross-cluster aggregation is V2.
```

---

# Part 3: Functional Requirements

## Write Flows (Metric Ingestion)

```
FLOW 1: PUSH-BASED INGESTION

    Application → Metrics Agent (local) → Collector → Storage

    Steps:
    1. Application instruments code (counter, gauge, histogram)
    2. Metrics library buffers locally (in-memory, 15s window)
    3. Agent scrapes or application pushes to local agent
    4. Agent batches and forwards to collector endpoint
    5. Collector validates, aggregates, writes to storage
    6. ACK returned to agent

FLOW 2: PULL-BASED INGESTION (Prometheus-style)

    Collector → scrapes → Application /metrics endpoint

    Steps:
    1. Application exposes /metrics HTTP endpoint
    2. Collector discovers targets (service discovery)
    3. Collector scrapes each target every 15 seconds
    4. Response: text-based metric exposition format
    5. Collector parses, labels, writes to storage

    TRADE-OFF:
    Pull: Collector controls rate; easier to debug (just curl the endpoint)
    Push: Works for short-lived jobs; doesn't require inbound connectivity
    
    V1 DECISION: Pull-based (simpler, better debuggability)
    Support push gateway for batch/cron jobs
```

## Read Flows (Querying)

```
FLOW 3: DASHBOARD QUERY

    Dashboard → Query API → Query Engine → Storage → Response

    Steps:
    1. Dashboard sends query: rate(http_requests_total{service="api"}[5m])
    2. Query API parses expression
    3. Query engine identifies time range and series
    4. Storage returns raw data points
    5. Query engine computes rate(), aggregates
    6. Returns JSON: [{timestamp, value}, ...]
    7. Dashboard renders chart

    Latency target: < 500ms for single-service, last-hour query

FLOW 4: ALERT EVALUATION

    Alert Manager → Query API → evaluate rule → fire/resolve

    Steps:
    1. Alert manager reads alert rules from config
    2. Every 60 seconds: evaluate each rule
    3. Query metrics system for rule condition
    4. If condition true for configured duration: fire alert
    5. Route alert to configured channel (PagerDuty, Slack, email)
    6. If condition resolves: send resolution notification
```

## Behavior Under Partial Failure

```
PARTIAL FAILURE: Collector cannot reach 10% of targets

    Behavior:
    - Metrics from unreachable targets: gap in time series
    - Dashboard: Shows gap or last known value
    - Alert: "up" metric = 0 for unreachable targets
    - No data fabrication (gaps are visible, not hidden)

    Recovery:
    - When target reachable again: resume scraping
    - Gap remains (no backfill from target side)
    - Alert: "up" metric returns to 1

PARTIAL FAILURE: Storage write latency elevated

    Behavior:
    - Collector buffers in memory (bounded: 5 minutes of data)
    - If buffer fills: drop oldest data points (prefer fresh data)
    - Alert: "metrics_dropped_total" counter increasing
    
    Recovery:
    - Storage recovers → buffer drains → normal operation
    - Dropped points are permanently lost (acceptable for metrics)
```

---

# Part 4: Non-Functional Requirements (Senior Bar)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    NON-FUNCTIONAL REQUIREMENTS                              │
│                                                                             │
│   LATENCY:                                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Ingestion: < 30 seconds end-to-end (emit → queryable)              │   │
│   │  Simple query (single series, 1h): P50 < 100ms, P99 < 500ms         │   │
│   │  Complex query (aggregation across 100 series, 24h): P99 < 2s       │   │
│   │  Alert evaluation: < 5 seconds per rule evaluation cycle            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   AVAILABILITY:                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Write path: 99.9% (brief drops acceptable; data can be buffered)   │   │
│   │  Read path: 99.9% (dashboards and alerts must work)                 │   │
│   │  Alert evaluation: 99.95% (missed alerts are critical)              │   │
│   │                                                                     │   │
│   │  WHY 99.9% not 99.99%:                                              │   │
│   │  Metrics are best-effort signals, not transactional data.           │   │
│   │  A few seconds of missing metrics is tolerable.                     │   │
│   │  Losing a transaction or payment is not.                            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   CONSISTENCY:                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Eventual consistency (acceptable)                                  │   │
│   │  - Metric emitted at T may be queryable at T+30s                    │   │
│   │  - Two engineers querying at same time may see slightly different   │   │
│   │    results for the last 30 seconds (acceptable)                     │   │
│   │  - Older data (> 1 minute): consistent across readers               │   │
│   │                                                                     │   │
│   │  WHY eventual is fine:                                              │   │
│   │  Metrics are aggregates over time windows. A 15-second delay        │   │
│   │  doesn't change the shape of the graph or the alert outcome.        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   DURABILITY:                                                               │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Best-effort durability for raw metrics                             │   │
│   │  - Losing a few data points during node failure: acceptable         │   │
│   │  - Losing hours of data: NOT acceptable                             │   │
│   │  - Replication factor: 2 (enough for single-node failure)           │   │
│   │                                                                     │   │
│   │  Alert rules and dashboards: Stored durably (separate config DB)    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   TRADE-OFFS ACCEPTED:                                                      │
│   - Ingestion availability > query availability (data in > data out)        │
│   - Freshness > precision (15s resolution is fine; 1s is premature)         │
│   - Bounded cardinality (no per-user metrics; keeps cost predictable)       │
│   - Drop oldest data under pressure (fresh data is more valuable)           │
│                                                                             │
│   TRADE-OFFS NOT ACCEPTED:                                                  │
│   - Silent data loss (must be detectable via meta-metrics)                  │
│   - Alert evaluation downtime > 5 minutes (impacts incident response)       │
│   - Query results from wrong time range (must be time-accurate)             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 5: Scale & Capacity Planning

## Scale Estimates

```
ASSUMPTIONS:

    Services: 200 microservices
    Instances: 500 total (average 2.5 instances per service)
    Metrics per instance: 200 unique metric names
    Labels per metric: Average 10 unique label combinations
    
    Active time series: 500 × 200 × 10 = 1,000,000 (1M series)
    
    Collection interval: 15 seconds
    Data points per second: 1,000,000 / 15 ≈ 67,000 points/sec
    Data points per day: 67,000 × 86,400 ≈ 5.8 billion/day
    
    Bytes per data point: ~16 bytes (8-byte timestamp + 8-byte float)
    Raw data per day: 5.8B × 16 = ~93 GB/day (uncompressed)
    
    With compression (gorilla/delta encoding): ~10:1 ratio
    Compressed data per day: ~9.3 GB/day
    
    30-day retention at 15s resolution: ~280 GB
    1-year retention (downsampled to 1h): ~3.5 GB
    
    Total storage: ~300 GB

READ LOAD:
    Active dashboards: 50 dashboards, auto-refresh every 30s
    Queries per dashboard: ~10 queries
    Dashboard QPS: 50 × 10 / 30 = ~17 QPS
    
    Alert rules: 500 rules, evaluated every 60s
    Alert QPS: 500 / 60 ≈ 8 QPS
    
    Ad-hoc queries: ~5 QPS (engineers investigating)
    
    Total read QPS: ~30 QPS (read is light; write is heavy)

WRITE:READ RATIO: ~2000:1 (write-dominant system)
```

## What Breaks First

```
SCALE GROWTH:

| Scale | Series | Ingest Rate | What Changes | What Breaks First |
|-------|--------|-------------|--------------|-------------------|
| 1× | 1M | 67K pts/s | Baseline | Nothing |
| 3× | 3M | 200K pts/s | More collectors | Series index size |
| 10× | 10M | 670K pts/s | Shard storage | Query fan-out |
| 30× | 30M | 2M pts/s | Architecture change | Cardinality explosion |

MOST FRAGILE ASSUMPTION: Bounded cardinality.

If developers add high-cardinality labels (user_id, trace_id):
    - 1M series → 100M series overnight
    - Storage: 300 GB → 30 TB
    - Ingestion rate: 67K → 6.7M pts/sec
    - Query performance: 500ms → 60 seconds
    
    THIS IS THE #1 OPERATIONAL RISK.
    
MITIGATION:
    - Cardinality limits per metric (max 10,000 series per metric name)
    - Label validation at ingestion (reject known-bad labels: user_id, request_id)
    - Alert on cardinality growth: "metric X exceeded 5,000 series"
```

---

# Part 6: High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    METRICS SYSTEM ARCHITECTURE                              │
│                                                                             │
│   DATA SOURCES (applications, infrastructure)                               │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐              │
│   │Service A │    │Service B │    │Service C │    │  Infra   │              │
│   │ /metrics │    │ /metrics │    │ /metrics │    │  agents  │              │
│   └────┬─────┘    └────┬─────┘    └────┬─────┘    └────┬─────┘              │
│        └───────────────┼───────────────┼───────────────┘                    │
│                        │ scrape (pull) every 15s                            │
│                        ▼                                                    │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    COLLECTORS (stateless, horizontally scalable)    │   │
│   │                                                                     │   │
│   │   ┌────────────┐  ┌────────────┐  ┌────────────┐                    │   │
│   │   │Collector 0 │  │Collector 1 │  │Collector 2 │                    │   │
│   │   │(targets    │  │(targets    │  │(targets    │                    │   │
│   │   │ 0-166)     │  │ 167-333)   │  │ 334-500)   │                    │   │
│   │   └─────┬──────┘  └─────┬──────┘  └─────┬──────┘                    │   │
│   │         └───────────────┼───────────────┘                           │   │
│   └─────────────────────────┼───────────────────────────────────────────┘   │
│                             │ write batches                                 │
│                             ▼                                               │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │              WRITE PATH (ingestion router)                          │   │
│   │              - Validate labels                                      │   │
│   │              - Enforce cardinality limits                           │   │
│   │              - Route to correct storage shard                       │   │
│   └─────────────────────────┬───────────────────────────────────────────┘   │
│                             │                                               │
│                             ▼                                               │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │              TIME-SERIES STORAGE (sharded by metric hash)           │   │
│   │                                                                     │   │
│   │   ┌────────────┐  ┌────────────┐  ┌────────────┐                    │   │
│   │   │  Shard 0   │  │  Shard 1   │  │  Shard 2   │                    │   │
│   │   │  (333K     │  │  (333K     │  │  (333K     │                    │   │
│   │   │   series)  │  │   series)  │  │   series)  │                    │   │
│   │   └────────────┘  └────────────┘  └────────────┘                    │   │
│   │                                                                     │   │
│   │   Each shard: In-memory write buffer + on-disk compressed blocks    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                             ▲                                               │
│                             │ query                                         │
│   ┌─────────────────────────┴───────────────────────────────────────────┐   │
│   │              QUERY ENGINE (scatter-gather across shards)            │   │
│   │              - Parse PromQL-like expression                         │   │
│   │              - Fan out to relevant shards                           │   │
│   │              - Merge and compute (rate, sum, quantile)              │   │
│   └─────────────────────────┬───────────────────────────────────────────┘   │
│                             ▲                                               │
│              ┌──────────────┼──────────────┐                                │
│              │              │              │                                │
│   ┌──────────┴──┐   ┌───────┴────┐   ┌─────┴──────┐                         │
│   │ Dashboards  │   │   Alert    │   │  Ad-hoc    │                         │
│   │ (Grafana)   │   │  Evaluator │   │  Queries   │                         │
│   └─────────────┘   └────────────┘   └────────────┘                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Architecture Decisions

```
DECISION 1: Pull-based collection (Prometheus-style)

    WHY:
    - Collector controls scrape rate (no thundering herd)
    - Easy to debug: curl http://target:9090/metrics
    - If target is down, collector knows immediately (scrape fails)
    - Push: Requires clients to know collector address; risk of overwhelming collector
    
    TRADE-OFF: Short-lived jobs can't be scraped → Push Gateway for cron/batch jobs

DECISION 2: Sharded storage, not single node

    WHY:
    - 1M series × 15s interval = 67K writes/sec
    - Single node TSDB handles ~50K writes/sec (e.g., Prometheus)
    - Need horizontal scaling for ingest AND query
    
    SHARDING KEY: Hash of metric name + label set
    - Ensures same time series always lands on same shard
    - Queries for a single series: single shard (fast)
    - Aggregation queries: fan out to all shards (acceptable)

DECISION 3: Stateless collectors, stateful storage

    WHY:
    - Collectors: Easy to scale, replace, restart
    - Storage: Must be stateful (holds data); harder to replace
    - Separation: Collector failure = brief gap; storage failure = data loss risk
```

---

# Part 7: Component-Level Design

## Collector

```
COLLECTOR RESPONSIBILITIES:
    - Discover targets (via service discovery or static config)
    - Scrape metrics from targets on schedule (every 15s)
    - Parse metric exposition format
    - Add metadata labels (cluster, region, job name)
    - Batch and forward to write path

KEY DATA STRUCTURES:

    Target Registry:
        Map<target_id, TargetInfo>
        TargetInfo: { address, labels, scrape_interval, last_scrape, health }

    Scrape Buffer:
        Ring buffer of scraped samples, capacity = 5 minutes of data
        If write path is slow: buffer absorbs backpressure
        If buffer full: drop oldest (prefer fresh data)

CONCURRENCY:

    - One goroutine/thread per scrape target
    - Scrapes execute in parallel (500 targets × 15s interval = ~33 scrapes/sec)
    - Thread-safe write to shared buffer
    - No global lock (each target has its own state)

FAILURE BEHAVIOR:

    Target unreachable:
        - Record up=0 for that target
        - Retry on next scrape interval (15s later)
        - Alert if target down for > 2 minutes
    
    Write path unreachable:
        - Buffer in memory (5-minute capacity)
        - If buffer fills: drop oldest data, increment metrics_dropped counter
        - Resume forwarding when write path recovers

// Pseudocode: Scrape loop
FUNCTION scrape_loop(target):
    WHILE running:
        start = now()
        TRY:
            response = http_get(target.address + "/metrics", timeout=10s)
            samples = parse_metrics(response.body)
            
            // Add metadata labels
            FOR sample IN samples:
                sample.labels["instance"] = target.address
                sample.labels["job"] = target.job_name
            
            write_buffer.append(samples)
            record_metric("scrape_duration_seconds", now() - start)
            record_metric("up", 1, target.labels)
        CATCH timeout_error:
            record_metric("up", 0, target.labels)
            record_metric("scrape_errors_total", 1)
        
        sleep_until(start + target.scrape_interval)
```

## Write Path (Ingestion Router)

```
WRITE PATH RESPONSIBILITIES:
    - Receive batches from collectors
    - Validate labels (reject high-cardinality labels)
    - Enforce per-metric series limits
    - Route samples to correct storage shard
    - Return ACK to collector

VALIDATION:

    // Pseudocode: Label validation
    FUNCTION validate_sample(sample):
        // Reject reserved label names
        IF sample.labels contains "user_id" OR "request_id" OR "trace_id":
            reject("high-cardinality label: " + label_name)
            increment(ingestion_rejected_total)
            RETURN false
        
        // Check series cardinality
        series_key = hash(sample.metric_name + sorted(sample.labels))
        current_count = series_count_per_metric[sample.metric_name]
        IF current_count > 10000:
            reject("cardinality limit exceeded for " + sample.metric_name)
            RETURN false
        
        RETURN true

ROUTING:
    shard_id = hash(metric_name + sorted(labels)) % num_shards
    
    WHY hash of full label set:
    - Same series always goes to same shard (required for correct append)
    - Uniform distribution across shards
    - No hot shards (unless one metric has millions of series)

BATCHING:
    - Collect samples for 1 second before forwarding to shard
    - Batch size: ~1,000-5,000 samples per shard per batch
    - Reduces per-sample overhead (network + storage write amplification)
```

## Storage Engine (Per Shard)

```
STORAGE ENGINE DESIGN (per shard):

    In-Memory Layer (Head Block):
        - Last 2 hours of data
        - Append-only, fast writes
        - Data structure: Map<series_id, [(timestamp, value)]>
        - Supports real-time queries
    
    On-Disk Layer (Persistent Blocks):
        - 2-hour blocks, compressed with gorilla encoding
        - Immutable once written (no random writes)
        - Index: Inverted index on labels for series lookup
        - Sorted by time within each series
    
    Compaction:
        - Merge small blocks into larger blocks (2h → 24h → 7d)
        - Downsample: 15s → 5m average for blocks > 48 hours old
        - Delete blocks older than retention period
        - Background process, low priority

WRITE PATH (per shard):

    FUNCTION write(samples):
        FOR sample IN samples:
            series_id = get_or_create_series(sample.metric_name, sample.labels)
            head_block[series_id].append(sample.timestamp, sample.value)
        
        // WAL for durability
        wal.write(samples)
        
        // When head block reaches 2 hours of data:
        // Flush to disk as compressed block + clear head

READ PATH (per shard):

    FUNCTION query(metric_name, label_matchers, time_range):
        // Find matching series using inverted label index
        matching_series = label_index.match(metric_name, label_matchers)
        
        results = []
        FOR series_id IN matching_series:
            // Check head block (recent data)
            IF time_range overlaps head_block time:
                results.append(head_block[series_id].read(time_range))
            
            // Check disk blocks (older data)
            FOR block IN disk_blocks overlapping time_range:
                results.append(block.read(series_id, time_range))
        
        RETURN results

COMPRESSION (Gorilla/Delta Encoding):
    - Timestamps: Delta-of-delta encoding
      Consecutive timestamps 15s apart: delta = 15, delta-of-delta = 0
      Encoded as single bit per timestamp (after first two)
    
    - Values: XOR encoding
      Consecutive values of similar magnitude: XOR has many leading zeros
      Encoded as variable-length bit string
    
    - Compression ratio: ~10:1 for typical metrics data
    - 16 bytes/point → ~1.6 bytes/point compressed
```

## Query Engine

```
QUERY ENGINE RESPONSIBILITIES:
    - Parse query expression (PromQL-like)
    - Plan query execution (which shards, which time range)
    - Fan out to shards (scatter-gather)
    - Merge results
    - Apply functions (rate, sum, avg, histogram_quantile)

QUERY EXECUTION:

    // Pseudocode: Query execution
    FUNCTION execute_query(expression, time_range):
        parsed = parse(expression)
        
        // Identify which series are needed
        series_selectors = extract_selectors(parsed)
        
        // Fan out to shards
        shard_results = PARALLEL FOR shard IN shards:
            shard.query(series_selectors, time_range)
        
        // Merge results from all shards
        merged = merge_series(shard_results)
        
        // Apply functions (rate, aggregation, etc.)
        result = evaluate(parsed, merged)
        
        RETURN result

QUERY OPTIMIZATIONS:
    - If query specifies exact metric name + labels → single shard (no fan-out)
    - Time range pushdown: Only read blocks covering requested time range
    - Label pushdown: Only read matching series from inverted index
    - Result cache: Cache query results for 15 seconds (matches scrape interval)
```

## Alert Evaluator

```
ALERT EVALUATOR RESPONSIBILITIES:
    - Load alert rules from configuration
    - Evaluate each rule on schedule (every 60 seconds)
    - Track alert state (inactive, pending, firing)
    - Send notifications via configured channels

STATE MACHINE:

    INACTIVE → (condition true) → PENDING
    PENDING → (condition true for `for` duration) → FIRING
    FIRING → (condition false) → RESOLVED
    PENDING → (condition false) → INACTIVE

    // Pseudocode: Alert evaluation loop
    FUNCTION evaluate_alerts():
        FOR rule IN alert_rules:
            result = query_engine.execute(rule.expression, last_5_minutes)
            
            IF result exceeds rule.threshold:
                IF rule.state == INACTIVE:
                    rule.state = PENDING
                    rule.pending_since = now()
                ELSE IF rule.state == PENDING AND (now() - rule.pending_since) > rule.for_duration:
                    rule.state = FIRING
                    send_notification(rule)
            ELSE:
                IF rule.state == FIRING:
                    rule.state = RESOLVED
                    send_resolution(rule)
                rule.state = INACTIVE

NOTIFICATION ROUTING:
    Alert → Route by severity and team:
        critical → PagerDuty (pages on-call)
        warning → Slack channel
        info → Dashboard annotation only
    
    Deduplication: Same alert only fires once until resolved
    Grouping: Related alerts (same service) grouped into single notification
```

---

# Part 8: Data Model & Storage

## Time-Series Data Model

```
CORE DATA MODEL:

    A time series is uniquely identified by:
        metric_name + sorted set of labels

    Example:
        http_requests_total{service="api", method="GET", status="200"}
    
    Internally:
        series_id = hash("http_requests_total" + "method=GET,service=api,status=200")

    Data points:
        (timestamp_ms, float64_value)
        (1706745600000, 42.0)
        (1706745615000, 43.0)   // 15 seconds later

METRIC TYPES:

    COUNTER (monotonically increasing):
        http_requests_total → 1, 2, 3, ..., 1000
        Reset to 0 on process restart
        Queried via rate(): rate(http_requests_total[5m]) = requests/sec

    GAUGE (arbitrary value):
        temperature_celsius → 22.5, 23.0, 22.8
        memory_usage_bytes → 1073741824
        Queried directly or with avg/min/max

    HISTOGRAM (distribution):
        http_request_duration_ms_bucket{le="50"} = 900
        http_request_duration_ms_bucket{le="100"} = 950
        http_request_duration_ms_bucket{le="200"} = 990
        http_request_duration_ms_bucket{le="+Inf"} = 1000
        http_request_duration_ms_sum = 75000
        http_request_duration_ms_count = 1000
        
        Queried via histogram_quantile():
        P99 = histogram_quantile(0.99, rate(http_request_duration_ms_bucket[5m]))
```

## Storage Schema

```
ON-DISK BLOCK FORMAT:

    Block directory structure:
        /data/shard_0/
            01_1706745600_1706752800/   (block: 2-hour window)
                index       (inverted index: label → series IDs)
                chunks/     (compressed time-series data)
                    000001  (chunk file, ~128 MB)
                    000002
                meta.json   (block metadata: time range, series count)
                tombstones  (deleted series markers)

    Index structure:
        Postings: label_name=label_value → [series_id_1, series_id_2, ...]
        
        Example:
            service="api" → [1, 5, 12, 89, 201, ...]
            method="GET"  → [1, 3, 5, 12, 56, ...]
        
        Query: service="api" AND method="GET"
            → Intersect posting lists → [1, 5, 12, ...]

    Chunk format (per series):
        [series_id][num_samples][timestamp_encoding][value_encoding]
        Gorilla encoding for timestamps and values
        ~1.6 bytes per data point (vs 16 bytes uncompressed)

SERIES METADATA TABLE (in-memory + persisted):

    series_id     | metric_name          | labels                              | first_seen  | last_seen
    ──────────────┼──────────────────────┼─────────────────────────────────────┼─────────────┼───────────
    1             | http_requests_total  | {service=api, method=GET, status=200}| 2024-01-01 | active
    2             | http_requests_total  | {service=api, method=POST,status=200}| 2024-01-01 | active
    ...
```

## Retention & Downsampling

```
RETENTION POLICY:

    Tier 1 (Raw): 15-second resolution, 48 hours
        - Used for: Real-time dashboards, incident investigation
        - Storage: ~18 GB (at 1M series)
    
    Tier 2 (5-min average): 30 days
        - Used for: Week-over-week comparisons, SLO calculation
        - Storage: ~5 GB
        - Downsampled from Tier 1 by background compaction
    
    Tier 3 (1-hour average): 1 year
        - Used for: Capacity planning, long-term trends
        - Storage: ~3.5 GB
        - Downsampled from Tier 2
    
    Total: ~27 GB (vs ~3.4 TB if everything kept at 15s for 1 year)

DOWNSAMPLING PROCESS:
    
    // Pseudocode: Downsample 15s → 5m
    FUNCTION downsample(series, source_block):
        raw_points = source_block.read(series)
        
        // Group into 5-minute windows
        windows = group_by_time(raw_points, 5_minutes)
        
        FOR window IN windows:
            downsampled_point = {
                timestamp: window.start,
                min: min(window.values),
                max: max(window.values),
                avg: avg(window.values),
                count: len(window.values),
                sum: sum(window.values)
            }
            write_to_tier2(series, downsampled_point)
    
    WHY store min/max/avg/count/sum:
    - Preserves ability to compute any aggregate from downsampled data
    - avg(avg) is incorrect if window sizes differ; but avg = sum/count works
    - max(max) correctly preserves global maximum
```

## Schema Evolution

```
ADDING A NEW METRIC:
    - No schema migration needed
    - New metric auto-discovered when first data point arrives
    - Series metadata created on-the-fly
    - This is a strength of schema-less time-series storage

ADDING A NEW LABEL:
    - Existing series unaffected (new label creates new series)
    - Risk: Cardinality explosion if label is high-cardinality
    - Mitigation: Cardinality limit check at ingestion

CHANGING METRIC TYPE (e.g., counter → histogram):
    - Breaking change: Old data has different structure
    - Approach: New metric name (http_request_duration_v2)
    - Old metric: Keep until retention expires
    - Dashboard: Update queries to new metric name
```

---

# Part 9: Consistency, Concurrency & Idempotency

## Consistency Model

```
CONSISTENCY GUARANTEES:

    Write path:
    - At-most-once delivery from collector to storage
    - If collector retries a scrape batch: same timestamps, same values
    - Idempotent: Writing same (series, timestamp, value) twice = no effect
    
    Read path:
    - Eventual consistency within a shard (head block → queryable in seconds)
    - Cross-shard: No global ordering guarantee (acceptable for metrics)
    - Stale reads during compaction: Possible but brief (seconds)
    
    Alert evaluation:
    - Reads from storage (eventual consistency)
    - `for` duration (5 minutes) absorbs brief inconsistencies
    - A 15-second stale read doesn't affect 5-minute alert threshold

WHY THIS IS FINE:
    Metrics are inherently approximate. A data point at T=14:32:15 represents
    an observation at that moment, not a transaction. Slight delays or
    reordering don't change the aggregate picture.
```

## Concurrency Control

```
CONCURRENT WRITES TO SAME SERIES:

    Scenario: Two collectors scrape the same target (misconfiguration or failover)
    
    Behavior:
    - Both write to same series (same series_id, same shard)
    - If same timestamp: Last write wins (idempotent, same value expected)
    - If different timestamps: Both appended (correct)
    
    Protection:
    - Per-series append lock (lightweight, per-shard)
    - WAL serializes writes within a shard
    
    // Pseudocode: Concurrent write handling
    FUNCTION append(series_id, timestamp, value):
        lock = series_locks[series_id]
        lock.acquire()
        TRY:
            last_ts = head_block[series_id].last_timestamp
            IF timestamp <= last_ts:
                // Out-of-order or duplicate: reject silently
                increment(out_of_order_samples_total)
                RETURN
            head_block[series_id].append(timestamp, value)
            wal.write(series_id, timestamp, value)
        FINALLY:
            lock.release()

CONCURRENT READS AND WRITES:

    - Head block supports concurrent read + append (lock-free reads with atomic pointer swap)
    - Disk blocks are immutable (no concurrency issue)
    - Compaction creates new blocks, then atomically swaps block list
    - Readers never see partial state
```

## Idempotency

```
IDEMPOTENT OPERATIONS:

    Ingestion:
    - Same (series_id, timestamp, value): Ignored if already exists
    - Collector restart: Re-scrapes same targets; timestamps advance, no duplicates
    
    Alert evaluation:
    - Evaluating same rule twice in same cycle: Same result (deterministic query)
    - Notification: Deduplication key = alert_name + labels + state
    - Same alert doesn't fire twice while already FIRING
    
    Compaction:
    - Merging same blocks twice: Produces identical output
    - Crash during compaction: Restart from source blocks (source not deleted until new block verified)
    
HANDLING OUT-OF-ORDER WRITES:
    - Metrics arrive out of order (network delay, clock skew)
    - Head block accepts writes within a 5-minute out-of-order window
    - Writes older than 5 minutes: Rejected (too stale)
    - Why 5 minutes: Covers collector buffering + network delay
    - If stricter ordering needed: Increase window (costs more memory)
```

---

# Part 10: Failure Handling & Reliability

## Partial Failure Behavior

```
PARTIAL FAILURE: One storage shard slow or unavailable

SITUATION: Shard 1 disk is degraded; write latency 10× normal

BEHAVIOR:
- Collectors writing to shard 1: Buffer backs up
- Other shards: Unaffected (independent)
- Queries involving shard 1: Slow (timeout after 5s)
- Queries NOT involving shard 1: Normal
- Dashboard: Partial data (series on shard 1 show gaps or stale values)

USER IMPACT:
- Dashboards for services whose metrics hash to shard 1: Incomplete
- Alerts evaluating metrics on shard 1: May miss threshold (stale data)
- Other services: Unaffected

DETECTION:
- Per-shard write latency metric
- Per-shard query latency metric
- Collector buffer fullness alert
- Alert: "shard_1 P99 write latency > 500ms"

MITIGATION:
- If disk: Failover to shard replica
- If load: Identify hot metric (cardinality explosion?) and throttle
- Short-term: Route queries to shard replica for reads

---

PARTIAL FAILURE: One collector down

SITUATION: Collector 1 process crashes

BEHAVIOR:
- Targets assigned to collector 1: No scraping (metrics gap)
- Other collectors: Unaffected
- Storage: Normal (just fewer writes from collector 1's targets)
- Alert: up=0 for all targets assigned to collector 1

USER IMPACT:
- Metrics gap for ~170 targets (1/3 of fleet)
- Dashboards show flat lines or gaps
- Alerts: May fire "target down" alerts (correct behavior)

DETECTION:
- Collector health check fails
- Multiple "target down" alerts simultaneously (pattern)
- Collector heartbeat metric missing

MITIGATION:
1. Auto-restart collector (systemd, Kubernetes)
2. If persistent: Redistribute targets to remaining collectors
3. Gap in metrics: Acceptable (no backfill for pull-based metrics)
```

## Dependency Failures

### Storage Disk Full

```
SCENARIO: One shard's disk fills up (retention not running, or unexpected growth)

DETECTION:
- Disk usage alert: "> 85% disk"
- Write errors: "no space left on device" in shard logs
- ingestion_failed_total counter increasing

IMPACT:
- Shard stops accepting new writes
- Head block cannot flush to disk
- If WAL also fills: Data loss risk for that shard
- Queries for existing data: Still work (reads don't need space)

RECOVERY:
1. Emergency: Delete oldest blocks (manual retention)
2. Identify cause: Cardinality explosion? Retention not running?
3. If cardinality: Identify offending metric, drop high-cardinality series
4. Expand disk or add shard

// Pseudocode: Emergency space reclamation
FUNCTION emergency_disk_free(shard):
    blocks = list_blocks_sorted_by_age(shard)  // oldest first
    WHILE disk_usage(shard) > 80%:
        oldest = blocks.pop_first()
        delete_block(oldest)
        log("Emergency deleted block: " + oldest.time_range)
    alert("Emergency disk cleanup performed on shard " + shard.id)
```

### Service Discovery Failure

```
SCENARIO: Service discovery (Consul/K8s API) unavailable

DETECTION:
- Collector logs: "Failed to refresh target list"
- Target count metric drops to 0

IMPACT:
- Collector can't discover NEW targets
- Existing targets: Still scraped (collector caches last known list)
- New deployments: Not monitored until discovery recovers

RECOVERY:
- Service discovery recovers → collector refreshes target list
- Mitigation: Collector caches last known targets with TTL = 1 hour
- If sustained: Static fallback config with known-critical targets
```

## Realistic Production Failure Scenario

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   FAILURE SCENARIO: CARDINALITY EXPLOSION FROM BAD INSTRUMENTATION          │
│                                                                             │
│   TRIGGER:                                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Developer adds metric with user_id label:                          │   │
│   │  http_requests_total{user_id="abc123", endpoint="/api/users"}       │   │
│   │  1M users × 10 endpoints = 10M new series (from 1M baseline)        │   │
│   │  Deployed to production during morning traffic ramp.                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   WHAT BREAKS:                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  T+0:    New metric deployed; series count starts growing           │   │
│   │  T+5min: Series count: 1M → 3M (growing fast)                       │   │
│   │  T+15min: Ingestion rate: 67K → 250K pts/sec; storage overloaded    │   │
│   │  T+20min: Shard memory usage spiking (head block too large)         │   │
│   │  T+30min: Query latency degraded: 200ms → 5s (index scan larger)    │   │
│   │  T+45min: OOM kill on shard node; writes failing                    │   │
│   │                                                                     │   │
│   │  SECONDARY EFFECTS:                                                 │   │
│   │  - Dashboard slow for ALL teams (shared storage)                    │   │
│   │  - Alerts delayed or missed (query too slow for evaluation)         │   │
│   │  - The metrics system that monitors everything is itself degraded   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   DETECTION:                                                                │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  - Alert: "active_series_count > 2M" (cardinality alert)            │   │
│   │  - Alert: "ingestion_rate > 150K pts/sec"                           │   │
│   │  - Alert: "query_latency_p99 > 3s"                                  │   │
│   │  - Correlation: New deployment in service X                         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   SENIOR ENGINEER RESPONSE:                                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  IMMEDIATE (0-10 min):                                              │   │
│   │  1. Identify: Which metric has exploding cardinality?               │   │
│   │     → topk(10, count by (__name__) ({__name__=~".+"}))              │   │
│   │  2. Drop the offending metric at ingestion (config update):         │   │
│   │     drop: metric_name="http_requests_total" label="user_id"         │   │
│   │  3. Apply config: Collectors stop forwarding that metric            │   │
│   │                                                                     │   │
│   │  MITIGATION (10-30 min):                                            │   │
│   │  4. Contact deploying team: "Remove user_id label"                  │   │
│   │  5. Run compaction to clean up orphaned series from memory          │   │
│   │  6. Monitor: Series count dropping, query latency recovering        │   │
│   │                                                                     │   │
│   │  POST-INCIDENT:                                                     │   │
│   │  1. Enforce cardinality limits at ingestion (reject > 10K series    │   │
│   │     per metric)                                                     │   │
│   │  2. Add pre-deploy metric review (lint rules: no user_id labels)    │   │
│   │  3. Alert on rate-of-change of series count (not just absolute)     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Timeout and Retry Configuration

```
TIMEOUT CONFIGURATION:

Scrape (collector → target):
    Timeout: 10 seconds (generous; some targets slow)
    No retry: Next scrape in 15 seconds (effectively a retry)
    
Write (collector → storage):
    Timeout: 5 seconds per batch
    Retry: 3 attempts, exponential backoff with jitter (1s ±0.5s, 3s ±1s, 10s ±3s)
    WHY jitter: Without jitter, all collectors retry at the same time after
    a storage blip → thundering herd → storage overloaded again
    After max retries: Drop batch, increment metrics_dropped counter
    
Query (client → query engine):
    Timeout: 30 seconds (complex queries can be slow)
    No retry for dashboard (auto-refresh in 30s)
    Alert evaluator: 1 retry after 5 seconds
    
Alert notification (evaluator → PagerDuty):
    Timeout: 10 seconds
    Retry: 5 attempts, backoff (5s, 15s, 30s, 60s, 120s)
    After max retries: Log error, retry next evaluation cycle
    Critical: Notification failures are themselves alerted on (meta-alert)
```

---

# Part 11: Performance & Optimization

## Hot Path Analysis

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        METRICS INGESTION HOT PATH                           │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. Scrape: HTTP GET to target /metrics     ~50ms (network + parse) │   │
│   │  2. Label validation + cardinality check    ~0.1ms per sample       │   │
│   │  3. Hash series key → determine shard       ~0.01ms per sample      │   │
│   │  4. Batch samples by shard                  ~0.1ms per batch        │   │
│   │  5. Network: Collector → shard              ~1ms per batch          │   │
│   │  6. WAL write (sequential, fsync batched)   ~1ms per batch          │   │
│   │  7. Head block append (in-memory)           ~0.01ms per sample      │   │
│   │  ─────────────────────────────────────────────────                  │   │
│   │  TOTAL per sample: ~0.1ms (batching amortizes fixed costs)          │   │
│   │  TOTAL per scrape cycle: ~100ms for 500 targets                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   BIGGEST FACTORS:                                                          │
│   - Scrape latency (depends on target; out of our control)                  │
│   - WAL fsync (dominates write latency; batch to amortize)                  │
│   - Head block memory (must fit in RAM; cardinality = memory)               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                        METRICS QUERY HOT PATH                               │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. Parse query expression                  ~1ms                    │   │
│   │  2. Label index lookup (inverted index)     ~5ms                    │   │
│   │  3. Read head block (in-memory)             ~2-10ms                 │   │
│   │  4. Read disk blocks (compressed)           ~10-50ms (if needed)    │   │
│   │  5. Decompress + scan data points           ~5-20ms                 │   │
│   │  6. Compute function (rate, quantile)       ~2-10ms                 │   │
│   │  7. Merge across shards (if multi-shard)    ~5ms                    │   │
│   │  ─────────────────────────────────────────────────                  │   │
│   │  TOTAL: ~30-100ms (single series), ~200-500ms (aggregation)         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   BIGGEST FACTORS:                                                          │
│   - Number of series matched (label selectivity)                            │
│   - Time range (longer = more blocks to read)                               │
│   - Function complexity (histogram_quantile > rate > sum)                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Optimizations Applied

### 1. Gorilla Compression (Most Critical for Storage)

```
PROBLEM: 67K data points/sec × 16 bytes = 1 MB/sec uncompressed

SOLUTION: Gorilla (Facebook) / double-delta encoding

HOW:
    Timestamps: Delta-of-delta encoding
        T0 = 1706745600
        T1 = 1706745615 (delta = 15)
        T2 = 1706745630 (delta = 15, delta-of-delta = 0 → 1 bit)
        
    Values: XOR encoding
        V0 = 42.5
        V1 = 42.7 (XOR has mostly zero bits → few bits stored)
    
RESULT: 16 bytes → 1.6 bytes per point (10× compression)
    Daily storage: 93 GB → 9.3 GB
```

### 2. Query Result Cache

```
PROBLEM: Dashboards auto-refresh every 30 seconds; same queries repeated

SOLUTION: Cache query results with TTL = scrape interval (15 seconds)

HOW:
    Cache key: hash(query_expression + time_range_aligned_to_15s)
    Cache value: serialized result
    TTL: 15 seconds
    
    Hit rate: ~60-80% for dashboard queries (same query repeated)
    
BENEFIT: 2-3× reduction in storage reads for dashboard traffic
    
INVALIDATION: TTL-based only (no explicit invalidation needed;
    metrics are append-only, old results are correct for their time range)
```

### 3. Write-Ahead Log Batching

```
PROBLEM: fsync per sample = 67,000 fsyncs/sec (disk can't handle it)

SOLUTION: Batch WAL writes; fsync once per batch (1 second of data)

HOW:
    Collect samples in memory for 1 second
    Write batch to WAL (single sequential write)
    fsync (one disk operation)
    
TRADE-OFF: Up to 1 second of data loss on crash (acceptable for metrics)
    
BENEFIT: 67,000 fsyncs/sec → 1 fsync/sec (67,000× improvement)
```

## Optimizations NOT Done

```
INTENTIONALLY DEFERRED:

1. CROSS-SHARD QUERY CACHING (premature)
   - Would cache aggregated results across shards
   - Complexity: Invalidation when any shard updates
   - DEFER UNTIL: Query fan-out latency exceeds 2 seconds consistently

2. PRE-COMPUTED AGGREGATIONS (premature)
   - Pre-compute common aggregations (e.g., per-service error rate)
   - Complexity: Must define which aggregations to pre-compute; storage doubles
   - DEFER UNTIL: Alert evaluation latency exceeds SLA

3. TIERED STORAGE (COLD TO OBJECT STORE)
   - Move old blocks to S3/GCS for cheap long-term storage
   - Complexity: Query engine must handle multi-tier reads; latency increases
   - DEFER UNTIL: Disk cost exceeds $X/month or retention > 1 year needed

4. EXEMPLARS (linking metrics to traces)
   - Store trace IDs alongside metric data points
   - Complexity: Increases storage, requires trace system integration
   - DEFER UNTIL: Tracing system is mature and engineers request it
```

---

# Part 12: Cost & Operational Considerations

## Major Cost Drivers

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     METRICS SYSTEM COST BREAKDOWN                           │
│                                                                             │
│   For 1M active series, 67K pts/sec:                                        │
│                                                                             │
│   1. COMPUTE (50% of cost)                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Storage nodes (3): $600/month each = $1,800/month                  │   │
│   │  Collectors (3): $150/month each = $450/month                       │   │
│   │  Query engine (2): $300/month each = $600/month                     │   │
│   │  Alert evaluator (1): $150/month                                    │   │
│   │  Total compute: ~$3,000/month                                       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   2. STORAGE (30% of cost)                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  SSD: 300 GB × 3 (replication) × $0.10/GB = $90/month               │   │
│   │  WAL: 50 GB × $0.10/GB = $5/month                                   │   │
│   │  Total storage: ~$95/month                                          │   │
│   │  (Storage is cheap relative to compute; RAM is the real cost)       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   3. RAM (critical resource, within compute cost)                           │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1M series × ~1 KB per series (head block) = ~1 GB in-memory        │   │
│   │  With 2h head block: ~4 GB RAM per shard for data                   │   │
│   │  Cardinality explosion to 10M: 40 GB RAM → OOM on 32 GB nodes       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   4. INFRASTRUCTURE (20% of cost)                                           │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Monitoring/Logging: $100/month                                     │   │
│   │  Alerting (PagerDuty/OpsGenie): $200/month                          │   │
│   │  Service discovery: Shared infrastructure ($0 incremental)          │   │
│   │  Total infra: ~$300/month                                           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   TOTAL MONTHLY COST: ~$3,400                                               │
│   COST PER 1M ACTIVE SERIES: ~$3.40/month                                   │
│                                                                             │
│   KEY INSIGHT: Metrics cost is dominated by RAM (for head block / index).   │
│   Cardinality directly controls cost: 2× series = 2× RAM = 2× cost.         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Cost Analysis Table (L5 Checklist)

| Cost Driver | Current | At Scale (10×) | Optimization |
|-------------|---------|----------------|--------------|
| Compute (storage nodes + collectors + query) | ~$3,000/mo | ~$30,000/mo | Right-size nodes; spot instances for collectors; query result caching |
| Storage (SSD + WAL) | ~$95/mo | ~$950/mo | Tiered storage (move old blocks to object store); aggressive downsampling |
| RAM (head block + index) | Within compute | Dominant cost at 10× | Enforce cardinality limits; drop stale series proactively |
| Infrastructure (alerting, discovery) | ~$300/mo | ~$600/mo | Shared infrastructure; sampling for meta-metrics |

**Senior cost discipline:** Intentionally not building tiered storage to S3, pre-computed aggregations, or cross-cluster federation in V1. Cost-cutting is safe on collectors (stateless, use spot) and older storage tiers (downsample aggressively). Dangerous: cutting RAM on storage nodes (causes OOM), or cutting replication (single point of failure).

| Decision | Cost Impact | Operability Impact | On-Call Impact |
|----------|-------------|---------------------|----------------|
| Enforce cardinality limits | Prevents runaway cost | Prevents OOM incidents | Fewer pages |
| Aggressive downsampling | -30% storage | Lose fine-grained old data | No impact |
| Spot instances for collectors | -40% collector cost | May lose collector briefly | Brief scrape gap (auto-recover) |

## On-Call Burden Analysis

```
ON-CALL REALITY:

EXPECTED PAGES (monthly):
    - Cardinality spike: 1-2 (new deployment with bad labels)
    - Storage node issue: 0-1 (disk, OOM)
    - Collector crash: 1-2 (auto-restarts; page only if repeated)
    - Query latency spike: 0-1 (expensive query or compaction)
    
    Total: 2-6 pages/month

HIGH-BURDEN:
    1. Cardinality explosion
       - Requires identifying offending metric + dropping it
       - Duration: 15-30 minutes to identify and mitigate
       - Impact: System-wide (all dashboards and alerts degraded)
    
    2. Storage node OOM
       - Requires restart + possible shard failover
       - Duration: 5-15 minutes
       - Risk: Data loss for in-memory head block

LOW-BURDEN (AUTOMATED):
    - Collector restart → Auto-restart by orchestrator
    - Compaction → Background, self-scheduling
    - Retention → Automatic block deletion
```

## Misleading Signals & Debugging Reality

```
MISLEADING SIGNALS:

| Metric | Looks Healthy | Actually Broken |
|--------|---------------|-----------------|
| Ingestion rate stable | 67K pts/sec | But 20% of targets unreachable (fewer unique metrics) |
| Query latency P50 fine | 100ms | P99 = 8 seconds (one shard slow, tail latency) |
| Disk usage < 80% | Looks fine | But RAM at 95% (head block growing from cardinality) |
| Alert evaluator running | No errors | But alert evaluation taking 50 seconds (alerts delayed) |

REAL SIGNALS:
    - Active series count (THE most important metric to watch)
    - Per-shard ingestion rate and latency (not aggregate)
    - Head block memory usage (RAM, not disk)
    - Alert evaluation duration (must be < rule interval)
    - Scrape failures rate (are we actually collecting from all targets?)

DEBUGGING: "Dashboards are slow"

1. Is it query engine or storage?
   → Check query_latency_seconds by component (parse, fetch, compute)
2. Is it one shard or all?
   → Check per-shard query latency
3. Is it a specific query or all queries?
   → Check slow query log (queries > 5 seconds)
4. Is it cardinality-related?
   → Check active_series_count trend; check head block memory
5. Is it compaction-related?
   → Check if compaction is running; compaction contends with queries on I/O

Common causes:
    - Cardinality growth (40%)
    - Expensive query (regex label matcher, long time range) (25%)
    - Compaction I/O contention (15%)
    - Disk degradation (10%)
    - Genuine traffic growth (10%)
```

---

# Part 12b: Rollout, Rollback & Operational Safety

## Deployment Strategy

```
METRICS SYSTEM DEPLOYMENT:

COMPONENT TYPES AND STRATEGY:

1. Collectors (stateless)
   Strategy: Rolling deployment
   Bake time: 10 minutes per batch
   Risk: Brief scrape gap during restart (~15 seconds)

2. Storage nodes (stateful)
   Strategy: Rolling restart, one node at a time
   - Drain writes (redirect to replicas)
   - Restart with new version
   - Wait for WAL replay + head block recovery
   - Verify: Node healthy, ingestion resumed
   Bake time: 15 minutes per node
   
3. Query engine (stateless)
   Strategy: Rolling deployment
   Bake time: 5 minutes per instance
   
4. Alert evaluator (single instance with standby)
   Strategy: Blue-green
   - Start new evaluator
   - Verify: Rules loaded, evaluations running
   - Stop old evaluator
   - Risk window: ~10 seconds of no evaluation

5. Config changes (scrape targets, alert rules, cardinality limits)
   Strategy: Config reload (no restart needed)
   - Collectors: Watch config file, reload on change
   - Alert evaluator: Reload rules from config store
   - Validation: Config syntax check before apply

CANARY CRITERIA:
    - Ingestion rate delta < 10%
    - Query latency P99 delta < 50%
    - Active series count stable
    - Alert evaluation duration stable
    - No scrape errors spike
```

## Rollback Safety

```
ROLLBACK TRIGGERS:
    - Ingestion rate drops > 20%
    - Query latency P99 > 3× baseline
    - Active series count spike > 50%
    - Alert evaluator failing to evaluate
    - On-call judgment

ROLLBACK MECHANISM:
    - Collectors/Query: Redeploy previous version (2 minutes)
    - Storage: Restart with previous binary (5-10 minutes)
    - Config: Revert config file (instant reload)
    - Alert rules: Revert rules config (instant reload)

ROLLBACK TIME:
    - Stateless components: 2-5 minutes
    - Storage nodes: 10-15 minutes (WAL replay)
    - Config: < 1 minute

DATA COMPATIBILITY:
    - Storage format: Backward compatible (new version reads old blocks)
    - Forward compatible: Test before deploy (old version must read new WAL)
    - If incompatible: Migration with dual-write period
```

## Concrete Scenario: Bad Collector Version

```
SCENARIO: New collector version has bug that doubles scrape frequency (15s → 7.5s)

1. CHANGE DEPLOYED
   - New collector binary rolled out
   - Expected: Same behavior, performance improvements
   - Actual: Bug in scrape scheduler; interval halved

2. BREAKAGE TYPE
   - Subtle: No errors, no crashes
   - Ingestion rate: 67K → 134K pts/sec
   - Storage write load doubles
   - Disk fills faster; RAM usage increases
   - Targets receive 2× scrape load

3. DETECTION SIGNALS
   - Ingestion rate doubled (alert: "ingestion_rate > 100K")
   - Scrape interval metric: 7.5s instead of 15s
   - Target-side: HTTP request rate to /metrics doubled
   - Disk growth rate accelerated

4. ROLLBACK STEPS
   a. Rollback collector binary to previous version
   b. Verify: Scrape interval returns to 15s
   c. Verify: Ingestion rate returns to 67K
   d. Extra data points already written: Harmless (just higher resolution temporarily)

5. GUARDRAILS ADDED
   - Integration test: Verify scrape interval matches config
   - Canary: Deploy to 1 collector first; compare scrape interval metric
   - Alert: Ingestion rate anomaly detection (> 50% change from baseline)
```

## Rushed Decision Scenario

```
RUSHED DECISION SCENARIO

CONTEXT:
- SRE team needs per-endpoint error rates for a new service launching in
  48 hours. Ideal: Proper metric naming convention, dashboard template,
  alert rules, runbook, load test on metrics system.

DECISION MADE:
- Ship raw counter metrics with ad-hoc label names. Create Grafana
  dashboard manually. Single alert rule: error_rate > 5%. No runbook, no
  load test.
- Why acceptable: Unblocks launch; provides basic observability. Service
  has low expected traffic (< 100 QPS); won't stress metrics system.

TECHNICAL DEBT INTRODUCED:
- Non-standard metric names → Can't use org-wide dashboard templates.
- No runbook → On-call engineer must figure out context from scratch.
- When we fix: Rename metrics (breaking change for dashboards), write
  runbook, add to standard monitoring. Cost: ~2 days of SRE time.
- Carrying debt: Service team asks "why doesn't the standard dashboard
  work for us?" documented as known limitation.
```

---

# Part 13: Security Basics & Abuse Prevention

## Authentication & Authorization

```
AUTHENTICATION:
    Write path (ingestion):
        - Collectors are internal services → mTLS between collector and storage
        - Application /metrics endpoints: Internal network only (no auth)
        - Push gateway: API key per service

    Read path (query):
        - Dashboard (Grafana): OAuth/SSO login
        - Query API: Bearer token (service account or user token)
        - Alert evaluator: Internal service account (mTLS)

AUTHORIZATION:
    V1: All metrics visible to all authenticated users
    
    WHY: Metrics are operational data, not user PII. Hiding metrics from
    engineers slows incident response. Principle: "Anyone on-call can see
    any metric."
    
    V2 (if needed): Tenant isolation for multi-team:
        - Label-based access: Team A can only query metrics where team="A"
        - Used for: Multi-tenant SaaS, compliance requirements
```

## Abuse Prevention

```
ABUSE VECTORS:

1. CARDINALITY BOMB (Most Common)
   Attack: Deploy metric with high-cardinality label (user_id)
   Impact: OOM, system-wide degradation
   Defense: Per-metric series limit (10K); label validation (reject known-bad)

2. EXPENSIVE QUERY (DoS)
   Attack: Query with regex matcher across all metrics, 1-year range
   Impact: Query engine saturated; dashboards and alerts degraded
   Defense:
       - Query timeout (30 seconds)
       - Max samples per query (50M)
       - Max time range for high-resolution queries (48 hours)
       - Slow query log and kill switch

3. SCRAPE TARGET OVERLOAD
   Attack: Misconfigured scrape interval (1 second instead of 15s)
   Impact: Target overwhelmed with HTTP requests
   Defense: Minimum scrape interval enforced (10 seconds)

4. DATA EXFILTRATION (LOW RISK)
   Attack: Read metrics to learn about internal infrastructure
   Impact: Information leakage (service names, topology)
   Defense: Internal network only; mTLS; OAuth for dashboards

V1 NON-NEGOTIABLE:
    - Cardinality limits at ingestion
    - Query timeout and sample limits
    - mTLS for internal communication
```

---

# Part 14: System Evolution

## V1: Minimal Viable Metrics System

```
V1 SCOPE:
    - Pull-based collection (Prometheus-style)
    - 3 collectors, 3 storage shards, 2 query engines
    - 1M active series, 67K pts/sec
    - 30-day retention (15s resolution)
    - Basic dashboards (Grafana)
    - Alert evaluation (500 rules)
    - No downsampling (store raw 15s data for 30 days)
    
    WHAT'S MISSING IN V1:
    - No downsampling (fine for 30 days; storage cost manageable)
    - No recording rules (pre-computed aggregations)
    - No multi-cluster
    - No tenant isolation
```

## V1.1: First Scaling Fix (Triggered by Cardinality Incident)

```
TRIGGER: Cardinality explosion incident (see Part 10)

CHANGES:
    1. Cardinality limits enforced at ingestion (10K series per metric)
    2. Label validation rules (reject user_id, request_id labels)
    3. Cardinality dashboard for platform team
    4. Alert: "Series count growth rate > 10% per hour"
    5. Runbook: "How to handle cardinality explosion"

ALSO:
    - Add downsampling (15s → 5m for data > 48 hours)
    - Reduces 30-day storage from ~280 GB to ~100 GB
    - Enables extending retention to 90 days at same cost

TIMELINE: 2-3 weeks after V1 launch
```

## V2: Incremental Improvements (Quarter 2)

```
TRIGGERED BY: Growth to 3M series, requests for longer retention

CHANGES:
    1. Tiered retention (15s/48h, 5m/90d, 1h/1y)
    2. Recording rules (pre-compute common aggregations)
       - e.g., service:http_errors:rate5m = pre-computed every 5 minutes
       - Alert rules query recording rules (faster, more stable)
    3. Cold storage to object store (S3/GCS) for > 90-day data
    4. Query federation: Query both local and cold storage transparently
    
    NOT IN V2:
    - Multi-cluster (still single cluster)
    - Per-tenant isolation
    - Exemplars / tracing integration
```

---

# Part 15: Alternatives & Trade-offs

## Alternative 1: Push-Based Ingestion (StatsD/Datadog-style)

```
WHAT IT IS:
    Applications push metrics to a central collector.
    No /metrics endpoint on applications.
    
WHY CONSIDERED:
    - Works for short-lived processes (cron jobs, lambdas)
    - No need for service discovery
    - Application controls what and when to send
    
WHY REJECTED FOR V1:
    - Collector can be overwhelmed (no rate control)
    - Hard to debug: Can't curl the application to see its metrics
    - If application sends garbage: Harder to detect and drop
    - Pull: Collector controls rate; knows immediately when target is down
    
TRADE-OFF:
    Pull loses visibility into short-lived jobs → Mitigated with push gateway.
    Pull requires service discovery → Complexity but also gives target health.
    
COMPROMISE: Pull for long-running services; push gateway for batch/cron.
```

## Alternative 2: Use Existing Database (PostgreSQL + TimescaleDB)

```
WHAT IT IS:
    Store metrics in PostgreSQL with TimescaleDB extension.
    SQL queries instead of PromQL.
    
WHY CONSIDERED:
    - Team already knows PostgreSQL
    - SQL is familiar; no new query language
    - TimescaleDB handles time-series partitioning
    
WHY REJECTED:
    - Ingestion rate: PostgreSQL handles ~10-20K inserts/sec (with tuning)
    - Our requirement: 67K pts/sec (3-6× higher)
    - Storage: No gorilla compression; 5-10× more disk
    - Cardinality: SQL indexes struggle with 1M+ unique label combinations
    - Query: PromQL functions (rate, histogram_quantile) would need custom SQL
    
TRADE-OFF:
    Custom TSDB is more work to build/operate, but handles our scale.
    TimescaleDB could work for smaller deployments (< 100K series).
    
WHEN TO RECONSIDER: If team size is < 2 engineers and scale is < 100K series,
    TimescaleDB is simpler to operate than custom TSDB.
```

---

# Part 16: Interview Calibration (L5 Focus)

## What Interviewers Evaluate

| Signal | How It's Assessed |
|--------|-------------------|
| Scope management | Do they clarify: How many services? What metrics types? What retention? |
| Trade-off reasoning | Pull vs push, resolution vs cost, cardinality vs flexibility |
| Failure thinking | What if storage is full? What if cardinality explodes? What if collectors fail? |
| Scale awareness | Data point rate calculation, compression ratios, storage estimates |
| Operational ownership | Who pages when dashboards are slow? How do you handle a cardinality bomb? |

## Example Strong L5 Phrases

- "First, let me estimate the ingestion rate: services × instances × metrics × label combinations ÷ scrape interval."
- "I'll use pull-based collection because the collector controls the rate. Push is riskier for thundering herd."
- "The #1 operational risk is cardinality explosion. I'll enforce limits at ingestion, not just hope developers are careful."
- "For retention, I'll downsample: 15-second resolution for 48 hours, 5-minute for 30 days. This gives 50× storage reduction."
- "If one storage shard is slow, queries return partial results. Dashboards show gaps, not wrong data."

## How Google Interviews Probe Metrics Systems

```
COMMON INTERVIEWER QUESTIONS:

1. "How do you handle high cardinality?"

   L4: "We'll add an index."
   
   L5: "Cardinality is the single biggest cost and reliability risk in a
   metrics system. We enforce limits at two levels:
   1) Ingestion: Reject metrics with > 10K series per metric name
   2) Validation: Block known high-cardinality labels (user_id, request_id)
   3) Alerting: Monitor series count growth rate
   
   If someone deploys a bad metric, we can drop it at the ingestion layer
   without restarting storage."

2. "What's your storage strategy?"

   L4: "Store everything in a database with timestamps."
   
   L5: "Time-series storage with gorilla compression—delta-of-delta for
   timestamps, XOR encoding for values. 10:1 compression ratio.
   
   In-memory head block for recent data (fast writes + reads); immutable
   on-disk blocks for older data. Tiered retention: high-res for incident
   investigation, downsampled for trends.
   
   The most fragile assumption is 'head block fits in RAM.' Cardinality
   explosion breaks this assumption. That's why cardinality limits are
   non-negotiable."

3. "What if a collector goes down?"

   L4: "We'll add redundancy."
   
   L5: "If one collector crashes, its targets aren't scraped. We get a gap
   in those metrics. The gap is visible (not hidden), and the alert system
   fires 'target down' for affected targets.
   
   Recovery: Orchestrator restarts the collector. It rediscovers targets
   from service discovery and resumes scraping within one interval (15s).
   
   The gap is acceptable because metrics are best-effort. What's NOT
   acceptable is the gap being silent—we must detect it."
```

## Common L4 Mistakes

```
L4 MISTAKE: "Store metrics in the same database as application data"

WHY IT'S L4: Doesn't understand that time-series data has fundamentally
different access patterns (append-heavy, range-scan queries, compression).
A general-purpose database can't handle 67K writes/sec efficiently.

L5 APPROACH: Purpose-built time-series storage with append-only writes,
columnar compression, and inverted label index.


L4 MISTAKE: "Allow any labels on any metric for flexibility"

WHY IT'S L4: Ignores cardinality explosion—the #1 operational risk.
Unbounded labels → unbounded series → unbounded RAM → OOM.

L5 APPROACH: Enforce cardinality limits at ingestion. Flexibility is
not worth the operational risk. Engineers who need per-user metrics
should use a different system (logs, tracing).


BORDERLINE L5 MISTAKE: "Real-time metrics with 1-second resolution"

WHY IT'S BORDERLINE: Shows ambition for freshness but doesn't reason about
cost. 1s resolution = 15× more data points, storage, and RAM.

L5 FIX: 15-second resolution for V1. 1-second resolution for specific
critical metrics only (e.g., error rate), not all metrics.


BORDERLINE L5 MISTAKE: Good architecture but no discussion of failure modes or operational burden

WHY IT'S BORDERLINE: Shows skill but not ownership mentality.
Problem: Interviewer can't tell if candidate has been on-call for this system.

L5 FIX: Proactively discuss "what happens when cardinality explodes,"
"how we detect silent data loss," and "what pages the on-call at 2 AM."
```

---

# Part 17: Diagrams

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    METRICS COLLECTION ARCHITECTURE                          │
│                                                                             │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐   ┌──────────┐                   │
│   │Service A │  │Service B │  │Service C │   │  Infra   │                   │
│   │ :9090    │  │ :9090    │  │ :9090    │   │  Agents  │                   │
│   │ /metrics │  │ /metrics │  │ /metrics │   │ /metrics │                   │
│   └──┬───────┘  └──┬───────┘  └──┬───────┘   └──┬───────┘                   │
│      │             │             │              │                           │
│      │◄─────── scrape (HTTP GET, every 15s) ───►│                           │
│      └──────────────┼─────────────┼──────────────┘                          │
│                     ▼             ▼                                         │
│   ┌─────────────────────────────────────────────────────┐                   │
│   │                COLLECTORS (×3)                      │                   │
│   │   Discover targets │ Scrape │ Validate │ Forward    │                   │
│   └─────────────────────────────┬───────────────────────┘                   │
│                                 │ batched writes                            │
│                                 ▼                                           │
│   ┌─────────────────────────────────────────────────────┐                   │
│   │           INGESTION ROUTER (write path)             │                   │
│   │   Validate labels │ Cardinality check │ Route       │                   │
│   └──────┬──────────────────┬──────────────────┬────────┘                   │
│          │                  │                  │                            │
│          ▼                  ▼                  ▼                            │
│   ┌────────────┐    ┌────────────┐    ┌────────────┐                        │
│   │  Shard 0   │    │  Shard 1   │    │  Shard 2   │                        │
│   │ ┌────────┐ │    │ ┌────────┐ │    │ ┌────────┐ │                        │
│   │ │  Head  │ │    │ │  Head  │ │    │ │  Head  │ │                        │
│   │ │ Block  │ │    │ │ Block  │ │    │ │ Block  │ │                        │
│   │ │(in-mem)│ │    │ │(in-mem)│ │    │ │(in-mem)│ │                        │
│   │ ├────────┤ │    │ ├────────┤ │    │ ├────────┤ │                        │
│   │ │  Disk  │ │    │ │  Disk  │ │    │ │  Disk  │ │                        │
│   │ │ Blocks │ │    │ │ Blocks │ │    │ │ Blocks │ │                        │
│   │ └────────┘ │    │ └────────┘ │    │ └────────┘ │                        │
│   └──────┬─────┘    └──────┬─────┘    └──────┬─────┘                        │
│          └─────────────────┼─────────────────┘                              │
│                            │ query (scatter-gather)                         │
│                            ▼                                                │
│   ┌─────────────────────────────────────────────────────┐                   │
│   │             QUERY ENGINE (×2, stateless)            │                   │
│   │   Parse │ Fan-out │ Merge │ Compute (rate, sum, ...)│                   │
│   └──────┬──────────────────┬──────────────────┬────────┘                   │
│          │                  │                  │                            │
│          ▼                  ▼                  ▼                            │
│   ┌──────────┐     ┌────────────┐     ┌──────────────┐                      │
│   │Dashboards│     │   Alert    │     │   Ad-hoc     │                      │
│   │(Grafana) │     │ Evaluator  │     │   Queries    │                      │
│   └──────────┘     └─────┬──────┘     └──────────────┘                      │
│                          │                                                  │
│                          ▼                                                  │
│                   ┌────────────┐                                            │
│                   │ PagerDuty  │                                            │
│                   │  / Slack   │                                            │
│                   └────────────┘                                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Ingestion + Query Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│               WRITE PATH + READ PATH DATA FLOW                              │
│                                                                             │
│   Application   Collector   Ingestion    Shard        Query      Dashboard  │
│       │            │        Router         │         Engine         │       │
│       │            │          │            │            │           │       │
│       │ ◄── GET /metrics ──-  │            │            │           │       │
│       │ ── response ──────►   │            │            │           │       │
│       │            │          │            │            │           │       │
│       │            │ parse +  │            │            │           │       │
│       │            │ validate │            │            │           │       │
│       │            │          │            │            │           │       │
│       │            │── batch ─▶│           │            │           │       │
│       │            │          │ validate   │            │           │       │
│       │            │          │ labels     │            │           │       │
│       │            │          │ cardinality│            │           │       │
│       │            │          │ check      │            │           │       │
│       │            │          │── route ──▶│            │           │       │
│       │            │          │            │ WAL write  │           │       │
│       │            │          │            │ Head append│           │       │
│       │            │          │◀── ACK ──-─│            │           │       │
│       │            │◀── ACK ──│            │            │           │       │
│       │            │          │            │            │           │       │
│       │            │          │            │     ◄── query ────-──  │       │
│       │            │          │            │ ◄── scatter ─────-─    │       │
│       │            │          │            │ ── results ─────-─►    │       │
│       │            │          │            │     ── merge+compute -▶│       │
│       │            │          │            │            │── JSON -─▶│       │
│       │            │          │            │            │           │       │
│                                                                             │
│   WRITE TIMING: Scrape → queryable in 15-30 seconds                         │
│   QUERY TIMING: Request → results in 50-500ms                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 18: Brainstorming & Senior-Level Exercises (MANDATORY)

---

## A. Scale & Load Thought Experiments

### Experiment A1: Traffic Growth

| Scale | Active Series | Ingest Rate | Shards | What Changes | What Breaks First |
|-------|---------------|-------------|--------|--------------|-------------------|
| Current | 1M | 67K pts/s | 3 | Baseline | Nothing |
| 3× | 3M | 200K pts/s | 6 | More shards + collectors | Head block RAM |
| 10× | 10M | 670K pts/s | 15 | Many more shards | Query fan-out latency |
| 30× | 30M | 2M pts/s | 50 | Architecture change | Ingestion router bottleneck |

```
AT 3× (3M series, 200K pts/s):
    Changes: Double shards (6); add collectors; increase RAM per shard
    First stress: Head block memory (3 GB → 9 GB per shard)
    Action: Increase instance size (32 GB → 64 GB RAM), or add shards

AT 10× (10M series, 670K pts/s):
    Changes: 15 shards; query fan-out to 15 shards
    First stress: Query latency (scatter to 15 shards; tail latency)
    Action:
    - Recording rules for common queries (pre-compute, single-shard read)
    - Query result cache with longer TTL for non-real-time queries
    - Per-shard query timeout (500ms) to bound tail latency

AT 30× (30M series, 2M pts/s):
    Changes: Architecture may need stream processing for ingestion
    First stress: Single ingestion router can't handle 2M pts/s
    Action:
    - Horizontally scale ingestion routers
    - Kafka between collectors and storage (decouple ingestion from storage)
    - Or: Direct collector-to-shard writes (skip router, use consistent hashing)
```

#### Scale Estimates Table (L5 Checklist)

| Metric | Current | 10× Scale | Breaking Point |
|--------|---------|-----------|----------------|
| Active series | 1M | 10M | When head block exceeds available RAM per shard |
| Ingest rate | 67K pts/s | 670K pts/s | When ingestion router becomes bottleneck |
| Storage nodes | 3 | 15 | When operational burden of managing shards becomes unsustainable |
| Query latency P99 | 500ms | 2-5s | When fan-out to all shards creates unacceptable tail latency |
| RAM (head block) | ~4 GB/shard | ~40 GB/shard | When cardinality exceeds shard memory capacity |

**Scale analysis:** The most fragile assumption is *bounded cardinality*. At 10×, the first thing that breaks is RAM (head block must fit in memory per shard). Back-of-envelope: 10M series × 1 KB/series = 10 GB for series metadata alone; with 2h of head block data, ~40 GB per shard. Needs 64 GB+ nodes or more shards.

### Experiment A2: Most Fragile Assumption

```
FRAGILE ASSUMPTION: "Developers emit bounded-cardinality metrics"

Why it's fragile:
- No technical enforcement in many metrics libraries
- A single bad deploy can go from 1M → 10M series in minutes
- Unlike traffic growth (gradual), cardinality explosion is sudden

What breaks:
    If cardinality 10×:
    - RAM: 4 GB → 40 GB per shard (OOM on 32 GB nodes)
    - Ingestion rate: 67K → 670K pts/sec (may overwhelm storage)
    - Query: Label index 10× larger; all queries slower
    - Cost: Proportional to series count; 10× cost overnight

Detection: Active series count + rate of change alert

Mitigation:
    - Hard limit at ingestion (reject > 10K series per metric)
    - Emergency metric drop (config change, no restart needed)
    - Pre-deploy linting (flag high-cardinality labels in CI)
```

---

## B. Failure Injection Scenarios

### Scenario B1: Slow Storage Shard (10× Latency)

```
SITUATION: Shard 1 disk degraded; write latency 10×, read latency 5×

IMMEDIATE BEHAVIOR:
- Writes to shard 1: Buffer in collector (5-minute capacity)
- Reads from shard 1: Slow (500ms → 2.5 seconds for that shard)
- Other shards: Unaffected

USER SYMPTOMS:
- Dashboards: Some panels slow (those querying metrics on shard 1)
- Alerts: Evaluation may timeout for rules touching shard 1

DETECTION:
- Per-shard write/read latency metrics
- Collector buffer fullness alert
- Query timeout rate increasing

MITIGATION:
1. Failover reads to shard 1 replica
2. Investigate disk: Replace if failing
3. If sustained: Redistribute shard 1 data to new node

PERMANENT FIX: Replace disk; add monitoring for disk latency (not just errors)
```

### Scenario B2: Collector OOM (Repeated Crashes)

```
SITUATION: Collector repeatedly OOM-kills due to target returning massive /metrics response

IMMEDIATE BEHAVIOR:
- Collector crashes mid-scrape cycle
- Targets assigned to this collector: No data
- Orchestrator restarts collector → OOM again → restart loop

USER SYMPTOMS:
- Metrics gap for ~170 targets
- Multiple "target down" alerts firing

DETECTION:
- OOM-kill events in orchestrator logs
- Collector uptime metric: < 1 minute repeatedly
- Pattern: Same collector crashing

MITIGATION:
1. Identify which target has oversized /metrics response
2. Temporarily exclude that target from collector's scrape list
3. Investigate: Why is target returning 100 MB of metrics? (Cardinality issue on target side)
4. Restart collector without problematic target

PERMANENT FIX: Per-scrape response size limit (10 MB); drop scrape if too large
```

### Scenario B3: Query Engine Overload (Expensive Query)

```
SITUATION: Engineer runs regex query: {__name__=~".*"} (match ALL metrics, ALL time)

IMMEDIATE BEHAVIOR:
- Query engine fans out to all shards
- Each shard scans entire index
- Query takes 60+ seconds, consuming all query engine resources
- Other queries queued behind it

USER SYMPTOMS:
- Dashboards slow or timing out
- Alert evaluation delayed

DETECTION:
- Slow query log: Query X took 65 seconds
- Query engine CPU at 100%
- Dashboard timeout errors

MITIGATION:
1. Kill the expensive query (query kill switch)
2. Alert: "Query duration > 30s" → auto-kill
3. Short-term: Add query concurrency limit (max 10 concurrent queries)

PERMANENT FIX: Query cost estimator; reject queries that would scan > 50M samples
```

### Scenario B4: Cache Unavailability (Query Cache Down)

```
SITUATION: Query result cache (if using external cache like Redis) unavailable

IMMEDIATE BEHAVIOR:
- All queries go directly to storage (no cache layer)
- Query latency: 2-3× higher (no cache hits)
- Storage read load: 3-5× higher
- If storage can handle it: Slower but functional

USER SYMPTOMS:
- Dashboards load slower (500ms → 1.5s)
- No missing data (cache is optimization, not requirement)

DETECTION:
- Cache connection error in query engine logs
- Query latency increase
- Storage read IOPS increase

MITIGATION:
- Query engine: Fall through to storage (no cache = slower, not broken)
- V1: Use in-process cache (no external dependency)

PERMANENT FIX: In-process LRU cache (no Redis dependency for V1);
external cache only when in-process isn't enough
```

### Scenario B5: Database Failover (Storage Shard Primary → Replica)

```
SITUATION: Primary for shard 2 fails; replica promoted to primary

IMMEDIATE BEHAVIOR:
- Writes: Brief pause during failover (5-10 seconds)
- Collectors: Buffer data for shard 2 during failover
- Reads: Redirect to new primary; slight stale data (replica may be 1-2s behind)
- Other shards: Unaffected

USER SYMPTOMS:
- Brief gap in metrics for series on shard 2 (5-10 seconds)
- Dashboards: Gap visible, then resumes
- Alerts: Evaluation continues; 5-second gap absorbed by `for` duration

DETECTION:
- Shard health check: Primary unreachable
- Failover event in orchestrator logs
- Brief ingestion error spike (during transition)

MITIGATION:
1. Automatic: Replica promoted, collectors rerouted
2. Verify: New primary accepting writes and serving reads
3. Investigate: Why old primary failed (disk, network, OOM)
4. Replace failed node; sync as new replica

PERMANENT FIX: Automatic failover with health checks; WAL replay on new replica for gap data
```

### Scenario B6: Retry Storm (Collector Retries During Storage Slowdown)

```
SITUATION: Storage slow → collectors timeout → retry → doubled write load → storage slower

IMMEDIATE BEHAVIOR:
- Storage write latency elevated (e.g., 2 seconds)
- Collectors: Timeout after 5 seconds; retry immediately
- Effective write load: 2× (original + retries)
- Storage: Even slower under doubled load → more timeouts → more retries

USER SYMPTOMS:
- Metrics ingestion lagging
- Dashboards showing stale data
- Potential data loss if collector buffers fill

DETECTION:
- Ingestion retry rate increasing
- Storage write latency increasing exponentially
- Collector buffer fullness approaching limit

MITIGATION:
1. Collectors: Exponential backoff (1s, 3s, 10s); not immediate retry
2. Circuit breaker: If shard error rate > 50%, stop writing for 30s
3. Prefer dropping data over amplifying load (shed load)
4. Fix root cause: What made storage slow?

PERMANENT FIX: Exponential backoff with jitter; circuit breaker per shard; load shedding when buffer > 80% full
```

---

## C. Cost & Trade-off Exercises

### Exercise C1: Cost at 10× Scale

```
CURRENT COST: $3,400/month (1M series)

AT 10× (10M series):
    Storage nodes: 3 → 15 ($600 × 15 = $9,000)
    Collectors: 3 → 10 ($150 × 10 = $1,500)
    Query engines: 2 → 5 ($300 × 5 = $1,500)
    Storage (disk): $95 → $950
    Infrastructure: $300 → $600
    
    TOTAL: ~$13,500/month (4× cost for 10× scale; sub-linear)
    
    WHY sub-linear:
    - Compression efficiency improves with more data (better delta encoding)
    - Infrastructure costs (alerting, monitoring) grow slowly
    - Main cost driver: Storage nodes (proportional to series count)
```

### Exercise C2: 30% Cost Reduction

```
CURRENT COST: $3,400/month

OPTIONS:

Option A: Aggressive downsampling (-$400)
    - Downsample to 5m after 24h instead of 48h
    - Trade-off: Less fine-grained data for incident investigation (24-48h ago)
    - Recommendation: YES (most incidents investigated within 12 hours)

Option B: Fewer collectors (3 → 2) (-$150)
    - Trade-off: Each collector handles 250 targets instead of 170
    - Risk: Slower scrape cycle; if one fails, 50% of fleet not scraped
    - Recommendation: NO (too risky)

Option C: Spot instances for collectors (-$200)
    - Trade-off: Collector may be preempted; brief scrape gap
    - Recommendation: YES (collectors are stateless; brief gap is fine)

Option D: Reduce replication (2 → 1) (-$600)
    - Trade-off: Single shard failure = data loss + downtime for affected series
    - Recommendation: NO for storage; YES for query engine (stateless)

SENIOR RECOMMENDATION:
    Options A + C = ~$600 savings (18%)
    Stretch: Smaller storage instances + optimize head block memory = additional $400
    TOTAL: ~$1,000 savings (29%)
```

### Exercise C3: Cost of an Hour of Downtime

```
COST OF METRICS DOWNTIME:

Direct cost:
    - No metrics → engineers can't see if OTHER systems are healthy
    - Alerts not firing → incidents go undetected
    - Estimated: 1 missed incident per hour of downtime

Indirect cost:
    - MTTR increases for ALL services (no observability)
    - If a separate production incident happens during metrics outage:
      diagnosis takes 3-5× longer (grep logs instead of dashboards)
    
    Industry estimate: 1 hour of outage for critical internal service = $10-50K
    (depending on company size and whether other incidents overlap)

THIS IS WHY: Metrics system availability target is 99.9% (not lower).
    Even though metrics are "best effort," the blast radius of metrics
    downtime affects every other team's ability to operate.
```

---

## D. Ownership Under Pressure

```
SCENARIO: 30-minute mitigation window

2 AM alert: "Query latency P99 > 5 seconds; alert evaluations timing out"
(Baseline P99: 500ms. Dashboards barely loading. Alerts delayed.)

1. What do you check first?
   - Per-shard query latency: Is one shard slow or all?
   - Active series count: Cardinality spike? (most common cause)
   - Recent deploys or config changes (collector version, alert rules, scrape targets)
   - Storage node health: CPU, RAM, disk I/O, OOM events
   - Slow query log: Is one expensive query consuming all resources?

2. What do you explicitly AVOID touching?
   - Storage shard configuration (shard count, replication)
   - Compaction settings (can make things worse under load)
   - Alert rule changes (could mask real problems)
   - WAL settings (risk of data loss)

3. Escalation criteria?
   - If all shards slow + no cardinality spike: Likely infrastructure → engage infra team
   - If one shard OOM: Restart shard, failover to replica → handle solo
   - If cardinality explosion: Identify metric, drop at ingestion → handle solo, notify deploying team
   - If expensive query: Kill query → handle solo
   - If alert evaluator completely down: Engage team lead (alerting is critical)

4. Communication?
   "Metrics system query latency elevated. Dashboards and alerts may be
   delayed. Investigating root cause. No data loss. Will update in 10 minutes.
   If you have a production incident, use direct log access as fallback."
```

---

## E. Correctness & Data Integrity

### Exercise D1: Idempotency Under Retries

```
QUESTION: Collector retries a batch of 1,000 data points. What happens?

ANSWER:
    Each data point is (series_id, timestamp, value).
    If same (series_id, timestamp) already exists: Ignored (last-write-wins, same value).
    If timestamp is newer: Appended normally.
    
    Net effect: Retry is safe. No duplicates.
    
    WHY:
    - Metrics are immutable observations at a point in time
    - Same timestamp = same observation = idempotent
    - WAL replay also idempotent (replay after crash is safe)
```

### Exercise D2: Preventing Corruption During Partial Failure

```
QUESTION: Power loss during block compaction. Is data corrupted?

ANSWER:
    Compaction process:
    1. Read source blocks (immutable, on disk)
    2. Write new merged block to temporary directory
    3. Atomic rename: temp → final block directory
    4. Delete source blocks ONLY after new block verified
    
    If crash at step 2: Temp directory is incomplete; ignored on startup
    If crash at step 3: Rename is atomic on most filesystems (ext4, xfs)
    If crash at step 4: Source blocks still exist; compaction re-runs
    
    Net effect: No data loss. At worst, wasted disk space from temp files.
```

### Exercise D3: Detecting Silent Data Loss

```
QUESTION: How do you know if the metrics system is silently losing data?

ANSWER:
    Meta-metrics (the metrics system monitors itself):
    
    1. scrape_samples_scraped — How many samples each scrape returns
       If suddenly 0 for a target: Target is broken or unreachable
    
    2. ingestion_samples_total — How many samples written to storage
       Compare with expected rate (services × metrics × labels / interval)
    
    3. active_series_count — Total unique time series
       If dropping unexpectedly: Series being lost
    
    4. storage_head_active_appenders — Active write operations
       If 0: Nothing being written (bad)
    
    5. meta_metrics_freshness — Freshness of self-monitoring metrics
       If stale: The metrics system itself is degraded
    
    KEY RULE: The metrics system must monitor itself using a SEPARATE
    mechanism (not itself). At minimum: Heartbeat from external watchdog.
```

---

## F. Incremental Evolution & Ownership

### Exercise E1: Adding Recording Rules (2 weeks)

```
REQUIRED CHANGES:
- New component: Rule evaluator (runs PromQL expressions on schedule)
- Writes computed results back to storage as new time series
- Example: service:error_rate:5m = rate(http_errors_total[5m]) by (service)
- Alert rules can then query pre-computed series (faster, more stable)

RISKS:
- Recording rules consume query capacity (they ARE queries)
- Circular dependency: If recording rule queries are slow → alerts slow
- New time series created → increases cardinality

DE-RISKING:
- Run recording rules on dedicated query engine (separate from user queries)
- Limit number of recording rules (100 initially)
- Monitor: recording_rule_evaluation_duration_seconds
```

### Exercise E2: Safe Schema Migration (Storage Format Change)

```
SCENARIO: Need to change on-disk block format (new compression algorithm)

SAFE PROCEDURE:

Phase 1: New code reads both old and new format
    - Deploy new binary that reads old blocks + writes new format
    - Old blocks: Untouched, readable
    - New blocks: Written in new format

Phase 2: Compaction converts old → new
    - Background compaction merges old blocks into new-format blocks
    - Gradual conversion over days/weeks
    - No downtime, no data loss

Phase 3: After all blocks converted
    - Remove old-format read code (simplify)
    - All data in new format

ROLLBACK:
    Phase 1: Rollback binary reads new blocks → must retain old-format read code
    Plan: Keep dual-format read code for 30 days after Phase 2 completes
```

### Exercise E3: Adding Push Gateway for Short-Lived Jobs

```
REQUIRED CHANGES:
- New component: Push Gateway (HTTP endpoint, accepts metric pushes)
- Push Gateway stores last-pushed metrics in memory
- Collectors scrape Push Gateway like any other target
- Short-lived job pushes metrics → Push Gateway holds them → Collector scrapes

RISKS:
- Push Gateway is a single point of failure for batch job metrics
- Stale metrics: If job doesn't push, Push Gateway serves stale values
- Abuse: Jobs could push high-cardinality metrics

DE-RISKING:
- Push Gateway: Stateless (backed by in-memory store; loss = brief gap only)
- TTL on pushed metrics: Expire after 5 minutes if not refreshed
- Same cardinality limits as pull-based ingestion
```

---

## G. Interview-Oriented Thought Prompts

### Prompt F1: Clarifying Questions to Ask First

```
1. "How many services and instances are we collecting from?"
   → Determines: Active series count, ingestion rate, storage size

2. "What metrics types? Counters, gauges, histograms?"
   → Determines: Storage per data point (histograms generate many series)

3. "What resolution and retention do we need?"
   → Determines: Storage strategy, downsampling, cost

4. "What's the alerting latency requirement?"
   → Determines: Ingestion pipeline freshness target

5. "Is this single-tenant or multi-tenant?"
   → Determines: Isolation, authorization, cardinality management
```

### Prompt F2: What You Explicitly Don't Build

```
1. LOG AGGREGATION (V1)
   "Metrics and logs are different systems. Metrics: numerical, low cardinality,
   cheap. Logs: text, high cardinality, expensive. Don't conflate them."

2. PER-USER METRICS
   "Bounded cardinality is non-negotiable. Per-user metrics belong in an
   analytics system, not the metrics pipeline."

3. MULTI-CLUSTER FEDERATION
   "V1: Single cluster. Federation adds query complexity (fan-out to remote
   clusters), consistency challenges, and operational burden."

4. ANOMALY DETECTION
   "V1: Static thresholds for alerting. ML-based anomaly detection requires
   historical baseline, model training, false-positive tuning. Too complex for V1."

5. REAL-TIME STREAMING (SUB-SECOND)
   "15-second resolution is sufficient. Sub-second adds 15× data volume
   and requires stream processing (Kafka Streams, Flink). Not justified yet."
```

### Prompt F3: Pushing Back on Scope Creep

```
INTERVIEWER: "What if we also need to support log search?"

L5 RESPONSE: "I'd push back on combining logs and metrics. They have
fundamentally different data models, storage requirements, and query
patterns. Logs are text-based, high-cardinality events; metrics are
numerical aggregates. Combining them increases complexity without
improving either use case.

I'd recommend a separate log aggregation system (like ELK or Loki)
and link the two via timestamps and service labels for correlation
during incident investigation."
```

---

# Final Verification

```
✓ This chapter MEETS Google Senior Software Engineer (L5) expectations.

SENIOR-LEVEL SIGNALS COVERED:

A. Design Correctness & Clarity:
✓ End-to-end: Scrape → Collect → Validate → Store → Query → Alert
✓ Component responsibilities clear (collector, ingestion router, storage, query engine, alert evaluator)
✓ Pull vs push justified; time-series storage vs relational DB justified

B. Trade-offs & Technical Judgment:
✓ Pull vs push, 15s vs 1s resolution, bounded cardinality
✓ Compression trade-off (gorilla encoding: 10× reduction)
✓ Explicit non-goals and deferred optimizations

C. Failure Handling & Reliability:
✓ Partial failure (slow shard, collector down, partial results)
✓ Cardinality explosion scenario (realistic production failure)
✓ Timeout and retry configuration
✓ Retry storm prevention

D. Scale & Performance:
✓ Scale Estimates Table (Current / 10× / Breaking Point)
✓ Concrete numbers (1M series, 67K pts/s, 300 GB storage)
✓ 10× scale analysis (head block RAM as bottleneck)
✓ Cardinality as most fragile assumption

E. Cost & Operability:
✓ $3.4K/month breakdown
✓ Cost Analysis Table (Current / At Scale / Optimization)
✓ Misleading signals section (ingestion rate normal but targets unreachable)
✓ On-call burden analysis

F. Ownership & On-Call Reality:
✓ Debugging "dashboards are slow"
✓ 30-minute mitigation scenario (Ownership Under Pressure) with explicit Q&A
✓ Self-monitoring: "Who watches the watchmen?"
✓ Retry jitter justified (prevents thundering herd on storage recovery)

G. Rollout & Operational Safety:
✓ Deployment strategy (rolling for stateless, blue-green for alert evaluator)
✓ Rollback triggers and mechanism
✓ Bad collector version scenario
✓ Rushed Decision scenario (shipping ad-hoc metrics for launch)

H. Interview Calibration:
✓ L4 vs L5 mistakes with WHY IT'S L4 / L5 FIX
✓ Borderline L5 mistakes (1s resolution, no failure discussion)
✓ Strong L5 signals and phrases
✓ Clarifying questions and non-goals

Brainstorming (Part 18):
✓ Failure scenarios: Slow shard, collector OOM, expensive query, cache down, database failover (B5), retry storm (B6)
✓ Ownership Under Pressure: 30-minute mitigation scenario with explicit answers (check first, avoid, escalate, communicate)
✓ Cost exercises: 10× scale, 30% reduction, downtime cost
✓ Correctness: Idempotency, corruption prevention, silent data loss detection
✓ Evolution: Recording rules, schema migration, push gateway
```

---

*This chapter provides the foundation for confidently designing and owning a metrics collection system as a Senior Software Engineer. The core insight: metrics are write-heavy, append-only, bounded-cardinality numerical data—and that shapes every design decision from compression (gorilla encoding) to storage (time-series blocks) to the #1 operational risk (cardinality explosion). Master the ingestion pipeline, enforce cardinality discipline, and you can observe any system at scale.*
