# Chapter 52. Metrics / Observability System

---

# Introduction

Observability systems are the nervous system of every large-scale distributed system. I've spent years building and operating metrics pipelines at Google, and I'll be blunt: the hardest part isn't collecting data—any engineer can slap a counter on a function. The hard part is collecting billions of data points per second, storing them efficiently for years, querying them in milliseconds during a production fire, and doing it all without the observability system itself becoming the outage.

This chapter covers metrics and observability system design at Staff Engineer depth: with deep understanding of the cardinality explosions that silently kill time-series databases, awareness of the ingestion-vs-query trade-offs that define architectural choices, and judgment about when approximate answers are better than perfect ones.

**The Staff Engineer's First Law of Observability**: The observability system is the last thing allowed to fail. When everything else is broken, this is the tool you use to understand *why*. If it goes down with the systems it monitors, it has failed its one job.

---

## Quick Visual: Metrics / Observability System at a Glance

```
┌─────────────────────────────────────────────────────────────────────────────┐
│          METRICS / OBSERVABILITY SYSTEM: THE STAFF ENGINEER VIEW            │
│                                                                             │
│   WRONG Framing: "Collect and display metrics"                              │
│   RIGHT Framing: "Ingest millions of time-series at sub-second latency,     │
│                   store them cost-efficiently for years, and enable         │
│                   millisecond queries during live production incidents"     │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Before designing, understand:                                      │   │
│   │                                                                     │   │
│   │  1. What is the cardinality of your label space?                    │   │
│   │  2. What query latency do you need during incidents? (P99?)         │   │
│   │  3. How long must you retain raw vs. aggregated data?               │   │
│   │  4. Who are the consumers: humans (dashboards) or machines (alerts)?│   │
│   │  5. Push-based or pull-based collection? Why?                       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   THE UNCOMFORTABLE TRUTH:                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Perfect accuracy + high cardinality + long retention + fast query  │   │
│   │  + low cost is IMPOSSIBLE. You must choose which to sacrifice.      │   │
│   │  Most systems sacrifice accuracy (via aggregation/downsampling)     │   │
│   │  and retention (tiered storage) to keep queries fast and costs low. │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## L5 vs L6 Metrics / Observability Decisions

| Scenario | L5 Approach | L6 Approach |
|----------|-------------|-------------|
| **Cardinality** | "Store every unique label combination as a separate time series" | "Cardinality is the single biggest threat to TSDB stability. Enforce per-metric cardinality limits, reject unbounded labels (user_id, request_id), and pre-aggregate where possible." |
| **Ingestion** | "Send every data point to a central TSDB" | "Buffer locally, pre-aggregate at the edge, and use streaming aggregation before hitting storage. The ingestion path must be cheaper than the data it carries." |
| **Retention** | "Keep everything for 1 year at full resolution" | "Raw data for 48 hours, 1-minute roll-ups for 30 days, 1-hour roll-ups for 1 year, daily roll-ups for 5 years. 99.9% of queries touch the last hour." |
| **Alerting** | "Query dashboards to detect anomalies" | "Alerting is a streaming problem, not a query problem. Evaluate alert rules on the ingestion path. Never couple alerting latency to query-engine performance." |
| **Query performance** | "Index everything for fast queries" | "Optimize for the 3 query patterns that matter during incidents: single metric over time, metric across hosts, and top-N contributors. Accept slow ad-hoc exploratory queries." |

**Key Difference**: L6 engineers recognize that an observability system's primary customer is an on-call engineer at 3 AM during an incident. Every design decision should optimize for that moment: fast queries, reliable alerting, clear signal-to-noise. Everything else is secondary.

---

# Part 1: Foundations — What a Metrics / Observability System Is and Why It Exists

## What Is a Metrics / Observability System?

A metrics and observability system continuously collects, stores, and analyzes quantitative measurements from distributed systems to enable engineers to understand system behavior, detect problems, diagnose root causes, and plan capacity.

It answers three fundamental questions:
1. **Is the system healthy right now?** (Monitoring and alerting)
2. **Why is the system broken right now?** (Diagnosis and debugging)
3. **How should the system evolve?** (Capacity planning and trending)

### The Three Pillars of Observability

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                  THE THREE PILLARS OF OBSERVABILITY                         │
│                                                                             │
│   ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐          │
│   │     METRICS      │  │      LOGS        │  │     TRACES       │          │
│   │                  │  │                  │  │                  │          │
│   │ What:            │  │ What:            │  │ What:            │          │
│   │ Numeric values   │  │ Discrete events  │  │ Request paths    │          │
│   │ over time        │  │ with context     │  │ across services  │          │
│   │                  │  │                  │  │                  │          │
│   │ When:            │  │ When:            │  │ When:            │          │
│   │ "Is latency up?" │  │ "Why did this    │  │ "Where is the    │          │
│   │ "How many 5xx?"  │  │  request fail?"  │  │  bottleneck?"    │          │
│   │                  │  │                  │  │                  │          │
│   │ Volume:          │  │ Volume:          │  │ Volume:          │          │
│   │ Medium           │  │ Very high        │  │ Low (sampled)    │          │
│   │ (aggregated)     │  │ (per-event)      │  │ (per-request)    │          │
│   │                  │  │                  │  │                  │          │
│   │ Cost:            │  │ Cost:            │  │ Cost:            │          │
│   │ Low per series   │  │ Very high at     │  │ Medium           │          │
│   │                  │  │ scale            │  │ (sampling helps) │          │
│   └──────────────────┘  └──────────────────┘  └──────────────────┘          │
│                                                                             │
│   THIS CHAPTER FOCUSES ON METRICS                                           │
│   (Logs and traces referenced where they intersect)                         │
│                                                                             │
│   Staff insight: Metrics DETECT problems. Logs and traces DIAGNOSE them.    │
│   Design the metrics path for speed and reliability. Design the logs/trace  │
│   path for depth and context.                                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### The Simplest Mental Model

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                  METRICS: THE BODY'S VITAL SIGNS ANALOGY                    │
│                                                                             │
│   Think of a metrics system as hospital patient monitoring:                 │
│                                                                             │
│   PATIENT (your production system)                                          │
│   ↓                                                                         │
│   SENSORS (instrumentation in your code)                                    │
│   • Heart rate → Request rate                                               │
│   • Blood pressure → Latency percentiles                                    │
│   • Temperature → Error rate                                                │
│   • Blood oxygen → Saturation / resource utilization                        │
│   ↓                                                                         │
│   BEDSIDE MONITOR (dashboards)                                              │
│   • Shows live readings in real time                                        │
│   • Historical trends for comparison                                        │
│   ↓                                                                         │
│   ALARM SYSTEM (alerting)                                                   │
│   • Heart rate below 40 or above 150? → Page the doctor                     │
│   • Blood oxygen below 90%? → Critical alarm                                │
│   ↓                                                                         │
│   MEDICAL RECORDS (long-term storage)                                       │
│   • Trends over days/months for diagnosis                                   │
│   • Aggregate statistics for research                                       │
│                                                                             │
│   COMPLICATIONS AT SCALE:                                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  What if you have 10 million patients? (10M services/containers)    │   │
│   │  → Can't have a nurse per patient; need automated monitoring        │   │
│   │                                                                     │   │
│   │  What if each patient has 500 vital signs? (500 metrics per host)   │   │
│   │  → Can't display all at once; need smart aggregation and ranking    │   │
│   │                                                                     │   │
│   │  What if the monitoring system itself gets sick?                    │   │
│   │  → Must be more reliable than the systems it monitors               │   │
│   │                                                                     │   │
│   │  What if historical records fill the warehouse?                     │   │
│   │  → Need to summarize: hourly stats not per-second after 30 days     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Why a Metrics / Observability System Exists

### 1. You Cannot Fix What You Cannot See

Production systems are opaque by default. Without metrics, the only way to know something is wrong is user complaints. By then, the problem has been ongoing for minutes or hours:

```
Without observability:
T+0min:   Latency spike begins (database connection pool exhausted)
T+5min:   Users experience slowness, some start leaving
T+12min:  Support tickets filed: "Site is slow"
T+18min:  Support escalates to engineering
T+20min:  Engineer logs in, starts investigating
T+35min:  Engineer identifies connection pool issue
T+40min:  Fix deployed
TOTAL: 40 minutes of user impact

With observability:
T+0min:   Latency spike begins
T+0.5min: Alert fires: "P99 latency > 500ms for 30s"
T+1min:   On-call engineer paged, opens dashboard
T+3min:   Dashboard shows connection pool saturation at 98%
T+5min:   Fix deployed (increase pool size + investigate root cause)
TOTAL: 5 minutes of user impact
```

### 2. Understanding System Behavior Under Normal Conditions

Most of the value of metrics comes from knowing what "normal" looks like:

```
Without baselines:
"CPU at 72%—is that bad?"  → No idea
"Latency at 230ms—is that normal?" → No idea
"Error rate at 0.5%—has it always been this?" → No idea

With baselines (from metrics history):
"CPU at 72% vs 40% normal → Something is wrong" → Investigate
"Latency at 230ms vs 200ms normal → Minor drift" → Monitor
"Error rate at 0.5% vs 0.01% normal → 50× increase" → Alert
```

### 3. Capacity Planning and Cost Optimization

Metrics over weeks and months reveal growth trends:

```
Capacity planning conversation (impossible without metrics):

"Traffic has grown 3% week-over-week for 6 months.
 At current rate, we exhaust database IOPS in 11 weeks.
 Recommendation: Shard the database before week 8,
 leaving 3 weeks buffer for unexpected spikes."

Cost optimization (impossible without metrics):

"Cache hit rate dropped from 95% to 82% last month.
 This shifted 1.3M requests/day back to the database.
 Root cause: New feature introduced cache-unfriendly access patterns.
 Fix: Add a secondary cache key → saves $47K/month in DB costs."
```

### 4. Incident Post-Mortem and Organizational Learning

After incidents, metrics provide the objective record:

```
Post-mortem without metrics:
"Something broke around 2 PM. We think it was related to the deploy.
 Someone noticed errors going up. We rolled back and things got better."

Post-mortem with metrics:
"At 14:02:17, error rate increased from 0.01% to 4.7% (470× normal).
 The spike correlated with deploy v2.3.1 reaching 50% canary traffic.
 CPU utilization on affected pods jumped from 35% to 92%.
 Root cause: Quadratic algorithm in new code path.
 Detection time: 43 seconds (alert on error rate).
 Mitigation time: 3 minutes (automated canary rollback).
 User impact: 2,847 requests returned 500 errors."
```

## What Happens If a Metrics / Observability System Does NOT Exist (or Fails)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              OBSERVABILITY SYSTEM FAILURE MODES                             │
│                                                                             │
│   FAILURE MODE 1: FLYING BLIND                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  No metrics → No alerts → No awareness → User-reported outages      │   │
│   │  Detection shifts from seconds to hours                             │   │
│   │  MTTR (Mean Time To Recovery) increases 10-50×                      │   │
│   │                                                                     │   │
│   │  Real example: A silent data corruption bug ran for 3 weeks         │   │
│   │  because there were no data integrity metrics.                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   FAILURE MODE 2: ALERT FATIGUE                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Bad metrics → Too many false alerts → On-call ignores alerts       │   │
│   │  → Real incident missed because it looked like another false alarm  │   │
│   │                                                                     │   │
│   │  This is WORSE than no alerts. False confidence kills.              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   FAILURE MODE 3: OBSERVABILITY SYSTEM ITSELF OVERLOADED                    │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  During traffic spike, metrics pipeline also overloads              │   │
│   │  → Metrics delayed or lost during the exact moment you need them    │   │
│   │  → Dashboards show stale data → Wrong diagnosis → Wrong fix         │   │
│   │                                                                     │   │
│   │  Staff insight: The observability system must be provisioned for    │   │
│   │  the WORST day, not the average day.                                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   FAILURE MODE 4: CARDINALITY EXPLOSION                                     │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Developer adds user_id as a metric label                           │   │
│   │  → 100M users × 50 metrics = 5 BILLION time series                  │   │
│   │  → TSDB runs out of memory → All metrics unavailable                │   │
│   │  → One bad label takes down entire observability stack              │   │
│   │                                                                     │   │
│   │  This is the #1 operational incident in metrics systems.            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   FAILURE MODE 5: METRIC MISINTERPRETATION                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Average latency looks fine at 50ms → But P99 is 12 seconds         │   │
│   │  → 1% of users having terrible experience                           │   │
│   │  → Dashboard shows green → No investigation                         │   │
│   │                                                                     │   │
│   │  Staff insight: Averages lie. Always use percentiles.               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 2: Functional Requirements

## Core Use Cases

### 1. Metric Emission (Instrumentation)

```
Use Case: Application code emits a metric data point

Types of metrics:

COUNTER (monotonically increasing):
  http_requests_total{method="GET", status="200", service="api"} += 1
  → "How many requests have we served?"

GAUGE (point-in-time value):
  connection_pool_active{service="api", pool="primary"} = 47
  → "How many connections are in use right now?"

HISTOGRAM (distribution of values):
  http_request_duration_seconds{method="GET", endpoint="/users"}
    .observe(0.237)
  → "What is the distribution of request latencies?"

SUMMARY (pre-computed percentiles):
  http_request_duration_seconds{quantile="0.99"} = 0.482
  → "What is the P99 latency?"

Each data point includes:
  - Metric name (string)
  - Labels/tags (key-value pairs)
  - Value (float64)
  - Timestamp (millisecond precision)
```

### 2. Metric Collection (Ingestion)

```
Use Case: Metrics pipeline collects data from thousands of sources

PUSH model (application sends to collector):
  Application → Agent/Sidecar → Collector → Storage
  
  Advantages:
  • Works behind firewalls/NATs
  • Application controls emission rate
  • Works for short-lived processes (batch jobs, lambdas)
  
  Disadvantages:
  • Application must know collector address
  • Can overwhelm collector during spikes
  • No way to know if a target is "down" vs "not emitting"

PULL model (collector scrapes application):
  Collector → HTTP GET /metrics → Application returns current values
  
  Advantages:
  • Collector controls scrape rate (backpressure)
  • "Target down" is immediately detectable
  • Simpler application code (just expose endpoint)
  
  Disadvantages:
  • Requires network path from collector to application
  • Can't handle short-lived processes easily
  • Scrape interval limits resolution

Staff decision: Most large-scale systems use PUSH for ingestion and PULL
for service discovery / health. Hybrid approaches dominate in practice.
```

### 3. Metric Storage

```
Use Case: Store billions of time-series data points efficiently

Input: Stream of (metric_name, labels, value, timestamp) tuples

Storage requirements:
  - Write throughput: Millions of samples/second
  - Compression: 1-2 bytes per sample (down from 16 bytes raw)
  - Query: Fast retrieval by metric + labels + time range
  - Retention: Hours to years, with resolution degradation

Schema concept:
  Time series = unique combination of (metric_name + all label values)
  
  Example: Two distinct time series:
    http_requests_total{method="GET", status="200"}  → series_id: 1
    http_requests_total{method="GET", status="500"}  → series_id: 2

  Each series stores ordered (timestamp, value) pairs:
    series_id: 1 → [(t1, 42), (t2, 43), (t3, 47), (t4, 49), ...]
```

### 4. Metric Querying

```
Use Case: Engineer queries metrics during an incident

Query types:

INSTANT QUERY (point-in-time):
  "What is the current error rate for service=api?"
  → rate(http_requests_total{service="api", status="500"}[5m])
  → Returns: 12.3 errors/second

RANGE QUERY (over time window):
  "Show me error rate for the last 6 hours"
  → rate(http_requests_total{service="api", status="500"}[5m])
    over range [now-6h, now] step 15s
  → Returns: 1,440 data points for graphing

AGGREGATION QUERY (across many series):
  "What is the total QPS across all API servers?"
  → sum(rate(http_requests_total{service="api"}[5m])) by (status)
  → Returns: {status="200": 45,000, status="500": 12.3, ...}

TOP-N QUERY:
  "Which endpoints have the highest P99 latency?"
  → topk(10, histogram_quantile(0.99, 
      rate(http_request_duration_bucket[5m])))
  → Returns: Top 10 endpoints ranked by P99
```

### 5. Alerting

```
Use Case: Automatically detect anomalies and page on-call

Alert rule definition:
  NAME: HighErrorRate
  EXPRESSION: rate(http_requests_total{status="500"}[5m]) > 10
  FOR: 2 minutes (must be true for 2 consecutive evaluations)
  SEVERITY: critical
  ANNOTATIONS:
    summary: "High 5xx error rate: {{ $value }} errors/sec"
    dashboard: "https://grafana/d/api-errors"

Alert lifecycle:
  1. INACTIVE → Expression evaluates to false
  2. PENDING  → Expression evaluates to true, "FOR" duration not met
  3. FIRING   → Expression true for >= "FOR" duration → Notify
  4. RESOLVED → Expression evaluates to false again → Notify resolution

Notification channels:
  - PagerDuty (on-call paging)
  - Slack/Chat (team awareness)
  - Email (non-urgent)
  - Webhooks (automated remediation)
```

### 6. Dashboarding

```
Use Case: Visualize system health on a shared dashboard

Dashboard components:
  - Time-series graphs (latency, throughput, error rate over time)
  - Single-stat panels (current value with threshold coloring)
  - Heatmaps (latency distribution over time)
  - Tables (top-N contributors, per-service breakdowns)
  - Alert status panels (which alerts are firing)

Dashboard hierarchy:
  L0 (Executive): "Are SLOs met? Red/Yellow/Green per service"
  L1 (On-call): "What's broken? Which service? Which endpoint?"
  L2 (Deep dive): "Why is it broken? Resource utilization, dependencies"
  L3 (Debug): "Per-instance metrics, per-pod, per-container"
```

## Read Paths

```
1. Dashboard rendering:
   User opens dashboard → Browser sends queries → Query engine evaluates
   → Returns time-series data → Browser renders graphs
   Latency target: < 2 seconds for default time range

2. Ad-hoc exploration:
   Engineer types query → Query engine evaluates over arbitrary range
   → Returns raw or aggregated results
   Latency target: < 10 seconds for most queries, minutes for expensive

3. Alert evaluation:
   Alert manager periodically evaluates rules → Queries recent data
   → Compares against thresholds → Fires/resolves alerts
   Latency target: < 30 seconds evaluation cycle

4. Reporting / SLO:
   Scheduled jobs query long time ranges → Compute SLI/SLO compliance
   → Generate reports
   Latency target: Minutes (batch, not interactive)
```

## Write Paths

```
1. Metric emission:
   Application code → Local aggregation buffer → Push to collector
   Latency target: < 10ms local (non-blocking to application)

2. Metric ingestion:
   Collector receives samples → Validates → Routes to storage
   Latency target: < 5 seconds end-to-end from emission to queryable

3. Downsampling:
   Background job reads raw data → Computes aggregates → Writes roll-ups
   Latency target: Minutes (asynchronous, not on critical path)
```

## Control / Admin Paths

```
1. Metric registration:
   Define new metric → Set cardinality limits → Configure labels
   
2. Alert rule management:
   Create / update / delete alert rules
   Test alert expressions against historical data ("dry run")
   
3. Dashboard management:
   Create / clone / share dashboards
   Set permissions (team-level, organization-level)
   
4. Retention policy management:
   Configure per-metric or per-namespace retention
   Trigger manual downsampling or deletion
   
5. Cardinality management:
   View top cardinality offenders
   Set per-metric cardinality caps
   Block or drop specific label values
```

## Edge Cases

```
1. Cardinality explosion:
   A new label with unbounded values (user_id, trace_id)
   → Must be detected and rejected before reaching storage

2. Clock skew:
   Different hosts report timestamps minutes apart
   → Out-of-order writes must be handled or rejected

3. Late-arriving data:
   Network partition resolved → Burst of stale data arrives
   → Must decide: accept (causes backfill) or reject (data loss)

4. Counter reset:
   Application restarts → Counter resets to 0
   → Query engine must detect resets and compute correct rate

5. Metric name collision:
   Two teams independently create metrics with the same name
   → Namespace isolation prevents data corruption

6. Query of death:
   A query touches millions of time series, exhausting memory
   → Query must be killed, not allowed to OOM the query engine
```

## Intentionally Out of Scope

```
• Log aggregation and search (separate system, different data model)
• Distributed tracing (separate system, though correlated via trace_id)
• Application Performance Monitoring (APM) code-level profiling
• Synthetic monitoring / uptime checks
• Business intelligence / analytics (different query patterns, different storage)

WHY: Each of these is a full system design in its own right. Trying to
build one system that does all of them results in a system that does
none of them well. In practice, these systems share infrastructure
(networking, storage backends) but have separate ingestion and query paths.
```

---

# Part 3: Non-Functional Requirements

## Latency Expectations

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                  LATENCY REQUIREMENTS BY PATH                               │
│                                                                             │
│   METRIC EMISSION (in-process):                                             │
│   P50: < 1μs  │  P99: < 10μs  │  Budget: ZERO blocking to application       │
│   WHY: A metric call inside a request path that adds 1ms per call           │
│   at 100 calls/request adds 100ms of latency. Unacceptable.                 │
│                                                                             │
│   INGESTION (end-to-end, emission to queryable):                            │
│   P50: < 10s  │  P99: < 30s                                                 │
│   WHY: During incidents, 30s staleness is tolerable. Beyond 60s,            │
│   dashboards become misleading—you're debugging with stale data.            │
│                                                                             │
│   DASHBOARD QUERY (standard time range):                                    │
│   P50: < 500ms  │  P99: < 3s                                                │
│   WHY: On-call engineer refreshing dashboard during incident.               │
│   More than 3 seconds → they'll open another tab and lose context.          │
│                                                                             │
│   ALERT EVALUATION (rule check cycle):                                      │
│   P50: < 15s  │  P99: < 60s                                                 │
│   WHY: Alerts should fire within 1–2 minutes of condition onset.            │
│   60s evaluation + 60s "for" duration = ~2 min detection latency.           │
│                                                                             │
│   AD-HOC QUERY (wide time range, many series):                              │
│   P50: < 5s  │  P99: < 30s                                                  │
│   WHY: Exploratory queries during post-mortem. Users tolerate waiting       │
│   but will abort and simplify query if > 30s.                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Availability Expectations

```
Target: 99.99% availability for ingestion and alerting paths
Target: 99.9% availability for query/dashboard path

WHY the asymmetry:
- If ingestion drops, data is LOST forever (unless buffered)
- If alerting drops, incidents go UNDETECTED
- If queries drop, engineers can wait 5 minutes and retry

IMPLICATION:
- Ingestion path must be over-provisioned with multi-layer buffering
- Alert evaluation must run on separate, isolated infrastructure
- Query path can tolerate brief degradation (show stale data)
```

## Consistency Needs

```
Eventual consistency is acceptable for most metrics use cases:

ACCEPTABLE:
- Dashboard shows data 10–30 seconds behind real-time
- Two engineers looking at the same dashboard see slightly different values
  (within seconds of each other)
- Downsampled data doesn't perfectly match raw data
  (mathematical artifacts of aggregation)

NOT ACCEPTABLE:
- Alert fires on stale data (condition already resolved)
  → Alert evaluation must use freshest available data
- Counter goes backward (resets should only happen on process restart)
  → Monotonicity must be preserved per-series
- Same query returns different results within the same dashboard load
  → Read-after-write consistency within a single user session
```

## Durability

```
RAW METRICS (< 48 hours):
- Durability: Best-effort (no replication for cost)
- Loss tolerance: Acceptable to lose individual data points
- WHY: Raw data volume is enormous; replicating it doubles cost

DOWNSAMPLED METRICS (> 48 hours):
- Durability: Replicated, 99.99% durability
- Loss tolerance: Unacceptable to lose aggregated data
- WHY: Aggregated data is small and represents irreplaceable history

ALERT RULES and DASHBOARD CONFIGS:
- Durability: 99.999% (stored in replicated config store)
- WHY: Losing alert rules means flying blind; losing dashboards
  means days of engineer time to rebuild
```

## Correctness vs User Experience Trade-offs

```
TRADE-OFF 1: Accuracy vs Query Speed
Decision: Accept 1–5% error in aggregated queries for 10× faster response
WHY: During incidents, approximate answers in 500ms beat exact answers in 30s

TRADE-OFF 2: Completeness vs Ingestion Reliability
Decision: Drop data points during overload rather than backpressuring applications
WHY: Application health > metric completeness. Never let the monitoring system
cause the outage it's supposed to detect.

TRADE-OFF 3: Resolution vs Cost
Decision: Downsample aggressively after 48 hours
WHY: 15-second resolution data for 1 year costs 100× more than 1-minute roll-ups.
Nobody queries last Tuesday at 15-second resolution.

TRADE-OFF 4: Cardinality vs Flexibility
Decision: Reject metrics exceeding cardinality limits
WHY: One unbounded label can take down the entire TSDB. Protecting the system
is more important than capturing every label an engineer wants.
```

## Security Implications

```
THREAT: Metric data reveals system architecture
- Metric names, labels, and values expose internal service topology
- An attacker with metrics access knows: service names, endpoint paths,
  traffic patterns, resource capacities, deployment schedules
- MITIGATION: Strict access control, namespace isolation, audit logging

THREAT: Alert rule manipulation
- Attacker disables alerts → Outages go undetected
- MITIGATION: Alert rule changes require approval, audit trail

THREAT: Ingestion abuse (DoS via metric flood)
- Attacker sends millions of fake metrics → Overwhelms storage
- MITIGATION: Authentication for ingestion, per-source rate limits

THREAT: Query abuse
- Expensive queries consume resources, starving legitimate queries
- MITIGATION: Query cost limits, timeouts, per-user quotas
```

---

# Part 4: Scale & Load Modeling

## Users and Sources

```
Large-scale metrics system (Google / hyperscaler scale):

Metric sources:
  - 10 million containers / pods
  - 500 metrics per container (avg)
  - 50 labels per metric (avg)
  
  = 5 BILLION active time series

Metric consumers:
  - 50,000 engineers with dashboard access
  - 500,000 alert rules (evaluated every 15–60 seconds)
  - 10,000 dashboards (loaded by multiple engineers)

Typical enterprise scale (for contrast):
  - 100,000 containers
  - 200 metrics per container
  - 20 million active time series
```

## QPS and Throughput

```
INGESTION (WRITES):

Per container: 500 metrics × 1 sample per 15 seconds = 33 samples/sec
10M containers × 33 samples/sec = 330 MILLION samples/second (peak)

Average: ~200M samples/second (not all containers emit simultaneously)
Peak: ~500M samples/second (deploy waves, scrape alignment)

Each sample: ~150 bytes raw (metric name + labels + value + timestamp)
Raw ingestion bandwidth: 200M × 150B = 30 GB/sec sustained

With compression (8–16 bytes/sample stored): ~3 GB/sec to storage

QUERIES (READS):

Dashboard loads: 10,000 concurrent dashboards × 20 panels × 1 query/15sec
  = 13,000 queries/second (dashboard)

Alert evaluations: 500,000 rules × 1 eval/30sec = 16,700 evals/second

Ad-hoc queries: ~100 queries/second (human-driven, bursty)

Total read QPS: ~30,000 queries/second

BUT: Each query touches 10–10,000 time series and reads 100–10,000 points
So effective read amplification is 100–1000× → Millions of series scanned/sec
```

## Read/Write Ratio

```
By QPS: Writes (200M samples/sec) >>> Reads (30K queries/sec)
         Ratio: ~7000:1 write-heavy by sample count

By I/O: Each query reads many samples, so actual I/O is closer to 10:1 write

By cost: Storage cost dominates writes; Compute cost dominates reads

This is a WRITE-HEAVY system for ingestion
but a READ-INTENSIVE system for query compute.

Staff insight: This dual nature means ingestion and query paths must be
designed independently. They have different bottlenecks, different SLOs,
and different failure modes.
```

## Growth Assumptions

```
Organic growth:
- Containers grow 30–50% year-over-year (Kubernetes adoption, microservices)
- Metrics per container grow 10–20% year-over-year (more instrumentation)
- Combined: ~50–70% year-over-year time-series growth

Step-function growth:
- New service onboards → 1M new time series overnight
- Team adds a new high-cardinality label → 10× series for that metric
- Deployment across new region → 2× all existing series

Most dangerous assumption:
"Cardinality will grow linearly."
REALITY: Cardinality grows combinatorially. Adding one new label with
100 values to a metric that has 10 other label combinations multiplies
series count by 100. This is how 1M series becomes 100M overnight.
```

## Burst Behavior

```
SCRAPE ALIGNMENT:
If all scrapers collect at exactly T+0, T+15, T+30...
→ Massive write spike every 15 seconds, idle in between
→ Must jitter scrape times to smooth ingestion

DEPLOY WAVES:
Rolling deploy of 10,000 pods → All pods restart → Counter resets
→ Burst of "new" time series (old series expire, new ones created)
→ TSDB churn (new index entries, compaction)

INCIDENT TRAFFIC:
During outage: 100 engineers simultaneously open dashboards
→ 100 × 20 panels × immediate query = 2,000 simultaneous queries
→ All queries hitting the same time range (last 30 minutes)
→ Hot read path on recent data

CARDINALITY BOMB:
Bad deploy adds user_id as label to a metric
→ Within minutes: 10M new time series
→ Ingestion queue backs up → TSDB runs out of memory
→ MUST detect and kill within seconds, not minutes
```

## What Breaks First at Scale

```
1. CARDINALITY (breaks at ~100M active series per TSDB node):
   Index size exceeds memory → Falls to disk → 100× slower queries

2. INGESTION THROUGHPUT (breaks at sustained write > disk I/O capacity):
   WAL writes backed up → Ingestion queue overflow → Data loss

3. QUERY FANOUT (breaks when single query touches > 100K series):
   Memory allocation per query exceeds limit → OOM or timeout

4. COMPACTION (breaks when TSDB can't compact fast enough):
   Block count grows → Query must scan more blocks → Slower and slower

5. NETWORK (breaks when metric traffic competes with application traffic):
   Metric egress saturates NIC → Application latency increases
   → Irony: Monitoring causes the outage
```

---

# Part 5: High-Level Architecture

## Core Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   METRICS SYSTEM ARCHITECTURE                               │
│                                                                             │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐                                      │
│  │ Service │  │ Service │  │ Service │  ... (millions)                      │
│  │   A     │  │   B     │  │   C     │                                      │
│  └────┬────┘  └────┬────┘  └────┬────┘                                      │
│       │            │            │                                           │
│       ▼            ▼            ▼                                           │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐                                      │
│  │ Agent / │  │ Agent / │  │ Agent / │  (per-host or sidecar)               │
│  │ Sidecar │  │ Sidecar │  │ Sidecar │                                      │
│  └────┬────┘  └────┬────┘  └────┬────┘                                      │
│       │            │            │                                           │
│       └────────────┼────────────┘                                           │
│                    ▼                                                        │
│  ┌──────────────────────────────────────────────────┐                       │ 
│  │           INGESTION LAYER                        │                       │
│  │  ┌──────────────────────────────────────────────┐│                       │
│  │  │  Collector Fleet (stateless, horizontally    ││                       │
│  │  │  scalable, validates, routes, pre-aggregates)││                       │
│  │  └──────────────────────────────────────────────┘│                       │
│  └─────────────────────┬────────────────────────────┘                       │
│                        │                                                    │
│            ┌───────────┼───────────────┐                                    │
│            ▼           ▼               ▼                                    │
│  ┌─────────────┐ ┌──────────┐ ┌────────────────┐                            │
│  │ Write-Ahead │ │ Streaming│ │ Cardinality    │                            │
│  │ Log / Queue │ │ Aggreg.  │ │ Enforcer       │                            │
│  │ (buffer)    │ │ Engine   │ │ (reject/drop)  │                            │
│  └──────┬──────┘ └─────┬────┘ └────────────────┘                            │
│         │              │                                                    │
│         ▼              ▼                                                    │
│  ┌──────────────────────────────────────────────────┐                       │
│  │           STORAGE LAYER                          │                       │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────┐    │                       │
│  │  │  HOT     │  │  WARM    │  │   COLD       │    │                       │
│  │  │  (TSDB)  │  │  (Object │  │   (Object    │    │                       │
│  │  │  In-mem  │  │   Store  │  │    Store,    │    │                       │
│  │  │  + SSD   │  │   1min   │  │    1hr agg)  │    │                       │
│  │  │  Raw 48h │  │   agg)   │  │              │    │                       │
│  │  └──────────┘  └──────────┘  └──────────────┘    │                       │
│  └──────────────────────┬───────────────────────────┘                       │
│                         │                                                   │
│  ┌──────────────────────┼───────────────────────────┐                       │
│  │           QUERY LAYER                            │                       │
│  │  ┌──────────────────────────────────────────────┐│                       │
│  │  │  Query Engine (fan-out to storage tiers,     ││                       │
│  │  │  merge results, compute aggregations)        ││                       │
│  │  └──────────────────────────────────────────────┘│                       │
│  └──────────┬──────────────────┬────────────────────┘                       │
│             │                  │                                            │
│    ┌────────▼────────┐  ┌─────▼──────────┐                                  │
│    │   DASHBOARDS    │  │  ALERT ENGINE  │                                  │
│    │   (Grafana,     │  │  (Evaluates    │                                  │
│    │    custom UI)   │  │   rules,       │                                  │
│    │                 │  │  routes        │                                  │
│    │                 │  │  notifications)│                                  │
│    └─────────────────┘  └────────────────┘                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

```
AGENT / SIDECAR (per-host):
  - Collects metrics from local application(s)
  - Local buffering (survives brief network issues)
  - Pre-aggregation (reduces samples before shipping)
  - Stateless except for local buffer

COLLECTOR FLEET (ingestion layer):
  - Receives metric samples from thousands of agents
  - Validates: metric name format, label format, value range
  - Cardinality enforcement: reject metrics exceeding limits
  - Routes: partition samples to correct TSDB shard
  - Stateless, horizontally scalable

WRITE-AHEAD LOG / QUEUE (buffer):
  - Decouples ingestion from storage
  - Absorbs write bursts without backpressuring producers
  - Enables replay after storage failures

STREAMING AGGREGATION ENGINE:
  - Pre-computes common aggregations on the ingestion path
  - Example: sum across all pods → single series per deployment
  - Reduces query load (common aggregations are pre-computed)

CARDINALITY ENFORCER:
  - Tracks unique label combinations per metric
  - Rejects/drops samples when cardinality exceeds threshold
  - Alerts metric owners about cardinality violations

TIME-SERIES DATABASE (TSDB, hot storage):
  - Stores raw time-series data for recent window (24–48 hours)
  - Optimized for sequential writes and time-range reads
  - In-memory index for label lookups
  - Compressed on-disk storage for sample data

WARM / COLD STORAGE:
  - Downsampled data in object storage
  - Queryable but slower (100ms–1s per read vs 1ms for hot)
  - Dramatically cheaper per GB

QUERY ENGINE:
  - Parses and plans queries
  - Fan-out to appropriate storage tiers
  - Merges results, computes aggregations
  - Enforces query cost limits (timeout, memory, series count)

ALERT ENGINE:
  - Periodically evaluates alert rules against recent data
  - Manages alert state machine (inactive → pending → firing → resolved)
  - Routes notifications to appropriate channels
  - Handles silencing, grouping, deduplication

DASHBOARD SERVICE:
  - Stores dashboard definitions (JSON)
  - Translates dashboard panels to metric queries
  - Renders visualizations in browser
```

## Stateless vs Stateful Decisions

```
STATELESS (scale horizontally, no coordination):
  - Agents (buffer is ephemeral, loss-tolerant)
  - Collectors (pure routing/validation)
  - Query engines (process queries, hold no state)
  - Dashboard service (all state in config DB)

STATEFUL (requires careful partitioning):
  - TSDB nodes (own a shard of time series)
  - Alert engine (must track alert state across evaluations)
  - Streaming aggregation (maintains windows of partial results)

Staff insight: Keep the stateful surface area minimal. Every stateful
component is a shard boundary, a failure domain, and a migration headache.
```

## Data Flow: Write Path

```
1. Application increments counter:
     http_requests_total{status="200"} += 1
     
2. Metric library batches locally (< 1ms, non-blocking):
     Buffer: {metric: "http_requests_total", labels: {...}, value: 147, ts: now}
     
3. Agent flushes batch to collector every 10–15 seconds:
     POST /ingest → batch of 500–5000 samples (compressed)
     
4. Collector validates:
     - Metric name: valid format? ✓
     - Labels: cardinality within limits? ✓
     - Timestamp: within acceptable window? ✓
     
5. Collector routes to correct TSDB shard:
     shard = hash(metric_name + sorted_labels) % num_shards
     
6. TSDB shard writes:
     a. Append to Write-Ahead Log (WAL) → durable immediately
     b. Buffer in memory (head block)
     c. When head block full → flush to disk (compressed block)
     
7. Data queryable within seconds of step 6a
```

## Data Flow: Read Path

```
1. Engineer opens dashboard (or alert engine evaluates rule):
     Query: rate(http_requests_total{service="api"}[5m])
     
2. Query engine parses and plans:
     - Time range: [now-5m, now]
     - Label matchers: {service="api"}
     - Function: rate()
     - Estimated cost: ~500 series, ~20,000 points
     
3. Query engine resolves label matchers → series IDs:
     Uses inverted index: label "service"="api" → [series_1, series_42, ...]
     
4. For each series, fetch samples in time range:
     Hot path: Read from in-memory head block + recent on-disk blocks
     (For queries spanning longer ranges: also read from warm/cold storage)
     
5. Apply function (rate):
     For each series: compute per-second rate from counter values
     
6. Return result set:
     [{labels: {service:"api", method:"GET", status:"200"}, values: [...]},
      {labels: {service:"api", method:"POST", status:"200"}, values: [...]},
      ...]
     
7. Dashboard renders graph from result set
```

---

# Part 6: Deep Component Design

## Component 1: Metric Client Library (In-Process)

### Internal Data Structures

```
COUNTER:
  Atomic float64 value (monotonically increasing)
  Per-label-set: one float64
  
  Implementation:
  counters = HashMap<LabelSet, AtomicFloat64>
  
  When observe(labels, increment):
    counter = counters.get_or_create(labels)
    counter.add(increment)  // atomic, lock-free

HISTOGRAM:
  Array of bucket counters + sum + count
  
  Implementation:
  struct Histogram:
    buckets: [AtomicFloat64; N]   // e.g., [0.005, 0.01, 0.025, 0.05, ...]
    sum: AtomicFloat64            // sum of all observed values
    count: AtomicUint64           // count of all observations
    
  When observe(labels, value):
    FOR i, bound IN bucket_boundaries:
      IF value <= bound:
        buckets[i].increment()
    sum.add(value)
    count.increment()

GAUGE:
  Simple atomic float64 (can go up or down)
  
  Implementation:
  gauges = HashMap<LabelSet, AtomicFloat64>
  
  When set(labels, value):
    gauge = gauges.get_or_create(labels)
    gauge.set(value)

EXPOSITION:
  When scraper calls /metrics (or agent flushes):
    FOR metric IN all_registered_metrics:
      FOR label_set, value IN metric.values:
        EMIT line: "metric_name{label1="v1",label2="v2"} value timestamp"
```

### Why This Design

```
Lock-free atomics: Metric operations are in the hot path of every request.
Any locking → contention → latency. Atomic operations provide O(1)
thread-safe updates with no contention.

Pre-allocated buckets: Histograms use fixed buckets rather than dynamic
because:
1. No memory allocation on observe() (hot path)
2. Predictable cardinality (number of series = label combinations × buckets)
3. Merge across instances is trivial (just sum the buckets)

HashMap for label sets: O(1) lookup by labels. The alternative—searching
a list—is O(N) and becomes a bottleneck with many label combinations.

WHY simpler alternatives fail:
- "Just log every value": Logs are 100× more expensive than counters.
  At 100K requests/sec, logging each request = 100K log lines/sec vs
  updating a counter 100K times/sec in-memory.
- "Compute percentiles in-process": Requires storing all values (unbounded
  memory) or using t-digest/DDSketch (CPU-expensive on hot path).
  Histograms with fixed buckets are O(1) CPU and O(1) memory.
```

## Component 2: Agent / Sidecar

### Internal Data Structures

```
struct Agent:
  scrape_targets: List<Target>    // discovered via service discovery
  sample_buffer: RingBuffer<Sample>  // bounded buffer, drops oldest on overflow
  batch_queue: Channel<Batch>     // outbound batches to collector
  
  // Local pre-aggregation
  aggregation_rules: List<AggregationRule>
  // e.g., "sum http_requests_total by (service, status)" → reduces per-pod to per-service

struct Target:
  url: string          // e.g., "http://10.0.1.5:8080/metrics"
  scrape_interval: Duration  // e.g., 15 seconds
  last_scrape: Timestamp
  health: enum { UP, DOWN, UNKNOWN }

struct Sample:
  metric: string
  labels: HashMap<string, string>
  value: float64
  timestamp: int64
```

### Algorithms

```
SCRAPE LOOP:

FUNCTION scrape_loop(target):
  WHILE running:
    SLEEP until next_scrape_time (with jitter ± 2 seconds)
    
    response = HTTP_GET(target.url, timeout=5s)
    
    IF response.failed:
      target.health = DOWN
      EMIT metric: up{target=target.url} = 0
      CONTINUE
    
    target.health = UP
    EMIT metric: up{target=target.url} = 1
    
    samples = parse_exposition_format(response.body)
    
    FOR sample IN samples:
      IF passes_relabeling_rules(sample):
        sample_buffer.push(sample)  // drops oldest if full
    
    EMIT metric: scrape_duration_seconds{target=target.url} = elapsed

BATCH AND SHIP:

FUNCTION batch_and_ship():
  WHILE running:
    batch = sample_buffer.drain(max=5000, timeout=10s)
    compressed = snappy_compress(serialize(batch))
    
    success = send_to_collector(compressed, timeout=5s)
    
    IF NOT success:
      // Re-enqueue for retry (limited retries to prevent memory growth)
      retry_buffer.push(batch)
      EMIT metric: agent_send_failures_total += 1
```

### Failure Behavior

```
COLLECTOR UNREACHABLE:
  - Buffer locally in ring buffer (bounded, e.g., 10 minutes of data)
  - Continue scraping (don't lose current data while waiting)
  - Exponential backoff on reconnection attempts
  - If buffer fills: DROP OLDEST data (recent data is more valuable)
  - NEVER backpressure the application

TARGET UNREACHABLE:
  - Mark target as DOWN
  - Continue attempting scrape at normal interval
  - Emit "up" metric = 0 (visible in dashboards)
  - After configurable timeout: generate "target_down" alert

AGENT ITSELF CRASHES:
  - Local buffer is lost (acceptable: data is ephemeral)
  - On restart: resume scraping immediately
  - Gap in data visible in dashboards
  - No cascading failure (applications continue serving)
```

## Component 3: Collector Fleet

### Internal Design

```
struct Collector:
  // Stateless - routes and validates, holds no persistent state
  
  inbound: GRPCServer         // receives from agents
  outbound: ShardedWriter     // sends to TSDB shards
  
  cardinality_cache: BloomFilter<SeriesFingerprint>  // approximate tracking
  rate_limiter: TokenBucket<SourceID>  // per-source rate limiting
  
  routing_table: ConsistentHashRing<TSDBShard>

FUNCTION handle_ingest(request):
  FOR sample IN request.samples:
    // Step 1: Validate
    IF NOT valid_metric_name(sample.metric):
      rejected_total += 1
      CONTINUE
      
    IF sample.timestamp < now() - MAX_STALENESS:
      stale_dropped_total += 1
      CONTINUE
    
    // Step 2: Cardinality check
    fingerprint = hash(sample.metric + sorted(sample.labels))
    IF cardinality_exceeds_limit(sample.metric, fingerprint):
      cardinality_rejected_total += 1
      CONTINUE
    
    // Step 3: Route to correct TSDB shard
    shard = routing_table.get_shard(fingerprint)
    outbound.send(shard, sample)
  
  RETURN ACK to agent
```

### Cardinality Enforcement (Critical)

```
WHY this is the most important function in the collector:

A single metric with unbounded labels can create millions of time series.
Example: http_request_duration{user_id="..."} with 100M users
= 100M time series from ONE metric.

TSDB behavior under cardinality explosion:
  1. Index grows beyond memory → Falls to disk → 100× slower
  2. Compaction can't keep up → Block count grows → Queries slow
  3. Memory exhaustion → OOM kill → All metrics for that shard lost

ENFORCEMENT ALGORITHM:

struct CardinalityEnforcer:
  // Per metric, track approximate unique series count
  series_counts: HashMap<MetricName, HyperLogLog>
  limits: HashMap<MetricName, uint64>  // configurable per metric
  default_limit: uint64  // e.g., 10,000 series per metric

FUNCTION cardinality_exceeds_limit(metric, fingerprint):
  hll = series_counts.get_or_create(metric)
  hll.add(fingerprint)
  
  estimated_count = hll.estimate()
  limit = limits.get(metric, default_limit)
  
  IF estimated_count > limit:
    ALERT("Cardinality limit exceeded", metric=metric, 
          estimated=estimated_count, limit=limit)
    RETURN true
  
  RETURN false

WHY HyperLogLog:
  - O(1) add and estimate
  - ~12KB memory per metric (tracks billions of unique values)
  - 2% error is acceptable for cardinality limiting
  - Alternative (exact counting) requires unbounded memory
```

### Why Simpler Alternatives Fail

```
"Just send everything directly to TSDB":
  - No validation → bad data corrupts storage
  - No cardinality control → single bad metric kills entire shard
  - No buffering → agent-to-TSDB coupling means agent failures cascade

"Use a message queue (Kafka) between agents and TSDB":
  - Adds latency (10–30s for queue + consumer lag)
  - Kafka doesn't understand metric semantics (can't enforce cardinality)
  - Queue ordering doesn't match time-series ordering
  - Extra infrastructure to operate
  
  Staff nuance: A WAL buffer IS appropriate, but a general-purpose
  message queue is over-engineering for most metrics pipelines.

"Single collector process":
  - Single point of failure
  - Vertical scaling limit (~1M samples/sec per process)
  - Fleet of stateless collectors scales horizontally with zero coordination
```

## Component 4: Time-Series Database (TSDB)

### Internal Data Structures

```
The TSDB is the heart of the system. Understanding its internals is
critical for Staff-level design.

INVERTED INDEX (for label lookups):
  Maps label key-value pairs to series IDs
  
  Posting list structure:
    label_index:
      "service" = "api"     → [series_1, series_42, series_108, ...]
      "service" = "auth"    → [series_2, series_43, ...]
      "method"  = "GET"     → [series_1, series_2, series_42, ...]
      "status"  = "200"     → [series_1, series_43, series_108, ...]
  
  Query: {service="api", method="GET"}
    → Intersect posting lists: [series_1, series_42, ...] ∩ [series_1, series_2, ...]
    → Result: [series_1, ...]
  
  Implementation: Sorted arrays with binary intersection
  (same technique as search engine inverted indexes)

HEAD BLOCK (in-memory, recent data):
  struct HeadBlock:
    series: HashMap<SeriesID, MemorySeries>
    min_time: Timestamp
    max_time: Timestamp  // grows with incoming data
  
  struct MemorySeries:
    labels: LabelSet
    chunks: List<MemoryChunk>
    
  struct MemoryChunk:
    // Uses delta-of-delta encoding for timestamps
    // Uses XOR encoding for values (Gorilla compression)
    encoded_data: ByteArray
    num_samples: uint32
    min_time: Timestamp
    max_time: Timestamp

PERSISTENT BLOCKS (on-disk, immutable):
  struct Block:
    meta: BlockMeta  // time range, series count, sample count
    index: IndexFile  // label index + posting lists for this block
    chunks: ChunkFiles // compressed time-series data
    tombstones: TombstoneFile // deletions (sparse, applied lazily)
  
  Directory structure:
    data/
    ├── head/           # in-memory, WAL-backed
    │   └── wal/        # write-ahead log for crash recovery
    ├── 01GB3F5S.../    # block covering 2h window
    │   ├── meta.json   # block metadata
    │   ├── index       # inverted index
    │   ├── chunks/     # compressed samples
    │   └── tombstones  # deletions
    ├── 01GB3F6T.../    # next 2h block
    └── ...
```

### Compression: Gorilla Encoding

```
WHY compression matters:
  Raw sample: 8 bytes timestamp + 8 bytes value = 16 bytes
  Compressed: ~1.37 bytes per sample (Gorilla paper, Facebook 2015)
  Compression ratio: ~12×
  
  At 200M samples/sec: Raw = 3.2 GB/s. Compressed = 274 MB/s.
  That's the difference between "works" and "doesn't work."

TIMESTAMP COMPRESSION (delta-of-delta):
  Timestamps in a series are usually evenly spaced (every 15 seconds).
  
  Raw:     [1000, 1015, 1030, 1045, 1060]
  Delta:   [1000, 15,   15,   15,   15  ]
  Δ-of-Δ: [1000, 15,   0,    0,    0   ]
  
  Encoding: The first timestamp uses 64 bits.
  Subsequent Δ-of-Δ = 0 → encode as single bit (0)
  
  For perfectly regular scraping: 1 bit per timestamp!

VALUE COMPRESSION (XOR encoding):
  Adjacent values in a time series are often similar.
  
  XOR of adjacent IEEE 754 floats:
  If values are similar → XOR has many leading/trailing zeros
  → Encode only the "meaningful" bits
  
  Example:
  value_1 = 42.5 (IEEE 754: 0x4045400000000000)
  value_2 = 42.7 (IEEE 754: 0x4045599999999999)
  XOR     =        0x0000199999999999
  → 20 leading zeros, 24 meaningful bits
  → Encode: (leading_zeros=20, significant_bits=24, value)
  
  Typical: 2–4 bytes per value (vs 8 bytes raw)
```

### Block Lifecycle and Compaction

```
BLOCK LIFECYCLE:

Time ─────────────────────────────────────────────────────→

  HEAD BLOCK (in-memory, 2 hours):
  ├──────────── collecting samples ────────────────┤
  
  When head block reaches 2 hours:
  1. Create new head block
  2. Flush old head to disk as immutable block
  3. New samples go to new head block
  
  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌─ HEAD ─┐
  │ 0-2h │ │ 2-4h │ │ 4-6h │ │ 6-8h │ │ 8-10h  │
  └──────┘ └──────┘ └──────┘ └──────┘ └────────┘

COMPACTION:
  Problem: Many small blocks → query must scan many files → slow
  Solution: Merge adjacent blocks into larger blocks
  
  Level 0: 2-hour blocks
  Level 1: Merge 3 × 2h → 1 × 6h block
  Level 2: Merge 3 × 6h → 1 × 18h block
  Level 3: Merge 2 × 18h → 1 × 36h block
  
  Benefits:
  - Fewer files to scan per query
  - Better compression (more samples to compress together)
  - Remove tombstoned (deleted) data
  
  Risks:
  - Compaction I/O competes with query I/O
  - Large blocks take longer to compact (must complete before next cycle)
  - If compaction falls behind → Block count grows → Queries slow

WRITE-AHEAD LOG (WAL):
  Every sample written to head block is FIRST appended to WAL (on disk).
  
  Purpose: If TSDB crashes, replay WAL to recover head block.
  
  WAL segments:
  wal/
  ├── 000001  # oldest active segment
  ├── 000002
  └── 000003  # newest segment (currently being written)
  
  Each segment: ~128MB
  Retention: Deleted after head block is flushed to disk block
```

### State Management

```
TSDB SHARD STATE:
  - Head block (in-memory): Active data, WAL-backed
  - On-disk blocks: Immutable, compacted periodically
  - Inverted index: In-memory (rebuilt from blocks on startup)
  
STARTUP SEQUENCE:
  1. Read block meta.json files → build block list
  2. Replay WAL → rebuild head block
  3. Build inverted index from all blocks + head
  4. Begin accepting writes and queries
  
  Startup time: Proportional to WAL size + index size
  Typical: 30s–5min depending on series count
  
  Staff concern: Long startup times mean slow recovery after crashes.
  Mitigation: Checkpoint the index periodically, replay only recent WAL.
```

### Failure Behavior

```
TSDB NODE CRASH:
  Impact: Shard unavailable for writes and queries
  Recovery: Restart → Replay WAL → Rebuild index
  Data loss: Only samples not yet WAL'd (< 1 second of data)
  
DISK FULL:
  Impact: WAL can't append → Ingestion stops for this shard
  Symptom: Write errors propagate to collectors
  Mitigation: Pre-allocated disk space, aggressive compaction, alerts at 80%

OUT OF MEMORY:
  Impact: Process killed → Same as crash
  Root cause: Usually cardinality explosion (index too large for RAM)
  Prevention: Cardinality enforcement at collector level

COMPACTION FAILURE:
  Impact: Block count grows → Queries progressively slower
  Symptom: Query latency increases over hours/days
  Mitigation: Compaction retry, alerting on block count, manual compaction
```

### TSDB Shard Rebalancing (Resharding)

```
PROBLEM: The system starts with 200 TSDB shards. Growth requires 300 shards.
How do you add 100 shards without losing data or causing downtime?

WHY THIS IS HARD:
  Routing: shard = hash(fingerprint) % 200
  After: shard = hash(fingerprint) % 300
  
  ~33% of series now hash to different shards.
  Those series exist on old shards but new data goes to new shards.
  Queries must check BOTH old and new shard for affected series.

MIGRATION STRATEGY:

Phase 1: DUAL-WRITE (duration: 48 hours)
  - New routing table: hash % 300
  - For series that moved: Write to BOTH old shard and new shard
  - Queries: Query BOTH and deduplicate results
  - Cost: ~33% more writes and queries temporarily

Phase 2: BACKFILL (duration: hours, background)
  - Copy historical data for moved series from old shard to new shard
  - Only copy data within hot retention window (48h)
  - Warm/cold data: Remains queryable via old metadata
    (object store data doesn't move, just update the metadata index)

Phase 3: CUTOVER
  - Stop dual-writing
  - Old shards: Still serve queries for data from before migration
  - New shards: Serve queries for data from after migration start
  - Query engine: Union results from both

Phase 4: CLEANUP (duration: days)
  - After hot retention expires (48h), old shard data ages out
  - Old shards that lost all series: Decommission
  - Old shards that retained some series: Continue serving

ALTERNATIVE: CONSISTENT HASHING
  Use consistent hash ring instead of modulo hashing.
  Adding 100 shards to 200: Only ~33% of series move (same as modulo)
  BUT: Movement is distributed evenly across all shards (not biased)
  AND: Virtual nodes allow fine-grained load balancing
  
  Staff decision: Consistent hashing from day 1. Modulo hashing makes
  resharding a nightmare. This is a V1 vs V2 decision that's hard to change later.

FAILURE BEHAVIOR IF IGNORED:
  Without a resharding strategy, the only option is vertical scaling
  of existing shards. When you hit the ceiling of a single node
  (RAM, disk, CPU), you're stuck.
  
  Staff teams have been known to delay resharding until a shard OOMs,
  causing a frantic emergency migration under production pressure.
  Plan the resharding mechanism BEFORE you need it.

REAL-WORLD COST:
  A poorly planned resharding at a major company caused 4 hours of
  partial metric loss while engineers manually moved data between shards.
  The fix: Pre-built resharding automation triggered by capacity alerts.
```

## Component 5: Query Engine

### Query Execution

```
QUERY PLANNING:

Input: rate(http_requests_total{service="api", status=~"5.."}[5m])

Step 1: Parse → AST
  rate(
    selector: {__name__="http_requests_total", service="api", status=~"5.."}
    range: 5m
  )

Step 2: Determine time range
  Range query: [now-6h, now] with step 15s
  For rate() with 5m range: need data from [now-6h-5m, now]

Step 3: Resolve selectors → series IDs
  Inverted index lookup:
    __name__ = "http_requests_total" → [1, 2, 3, ..., 1000]
    service = "api"                  → [1, 2, 50, 51, ...]
    status =~ "5.."                  → [2, 51, 200, ...]
    
  Intersect: [2, 51, ...]  → 47 matching series

Step 4: Cost estimation
  47 series × (6h + 5m) / 15s step ≈ 47 × 1460 = 68,620 samples
  Estimated memory: ~2MB → Under query limit → Proceed

Step 5: Fetch samples
  FOR each series:
    Identify blocks covering time range
    Read compressed chunks
    Decompress
    
Step 6: Apply rate() function
  FOR each series:
    FOR each step timestamp:
      Window = samples in [t - 5m, t]
      rate = (last_value - first_value) / (last_time - first_time)
      Handle counter resets (detect decrease, add previous total)

Step 7: Return result matrix
  [{metric: {...}, values: [[t1, r1], [t2, r2], ...]}, ...]
```

### Query Cost Protection

```
WHY this matters:
A single unbounded query can consume all memory on a query engine node,
causing all concurrent queries (including alert evaluations) to fail.

PROTECTION LAYERS:

Layer 1: Series limit
  IF resolved_series_count > MAX_SERIES (e.g., 500,000):
    RETURN error("query exceeded max series limit")
  
Layer 2: Sample limit
  IF estimated_samples > MAX_SAMPLES (e.g., 50,000,000):
    RETURN error("query exceeded max sample limit")

Layer 3: Memory limit
  Monitor memory allocation during query execution
  IF allocated > MAX_QUERY_MEMORY (e.g., 2GB):
    ABORT query, free memory

Layer 4: Timeout
  IF query_execution_time > MAX_TIMEOUT (e.g., 120s):
    ABORT query

Layer 5: Concurrency limit
  IF active_queries > MAX_CONCURRENT (e.g., 20):
    Queue or reject new queries

PRIORITY:
  Alert evaluation queries: HIGH priority (never queued)
  Dashboard queries: MEDIUM priority
  Ad-hoc queries: LOW priority (first to be shed under load)
```

### Cross-Tier Query Stitching

```
PROBLEM: A dashboard shows "error rate over 7 days."
  Last 48 hours: Hot storage (15-second resolution)
  Days 3-7: Warm storage (1-minute resolution)
  
  The query engine must seamlessly combine data at different resolutions
  into a single, coherent time-series graph.

WHY THIS IS TRICKY:
  1. RESOLUTION MISMATCH:
     Hot: data point every 15s → 4 points per minute
     Warm: data point every 1m → 1 point per minute
     
     If graphed naively: Hot portion appears 4× "denser" than warm
     Rates computed over different windows give different values
     
  2. BOUNDARY ARTIFACTS:
     At the hot/warm boundary (48 hours ago):
     rate() over a 5-minute window that straddles the boundary
     uses 15s data for part and 1m data for part
     → Computed rate may have a discontinuity
     
  3. DIFFERENT AGGREGATE SEMANTICS:
     Hot: raw counter values → rate() computes exact per-second rate
     Warm: pre-computed (min, max, sum, count) → rate must be derived
     from sum/count, not from raw counter increments

SOLUTION:

FUNCTION cross_tier_query(expression, start, end, step):
  // Determine which tiers cover the time range
  tiers = resolve_tiers(start, end)
  // e.g., [{tier: "hot", range: [now-48h, now]}, 
  //        {tier: "warm", range: [now-7d, now-48h]}]
  
  results = []
  FOR tier IN tiers:
    // Adjust step to match tier resolution
    effective_step = max(step, tier.native_resolution)
    
    sub_result = query_tier(tier, expression, tier.range, effective_step)
    results.append(sub_result)
  
  // Merge results, handling resolution differences
  merged = merge_cross_tier(results)
  
  // Align to requested step (downsample hot portion if needed)
  aligned = align_to_step(merged, step)
  
  RETURN aligned

FUNCTION merge_cross_tier(results):
  // At tier boundaries, prefer higher-resolution data
  // If overlap exists (dual-write period), use hot data
  // Handle rate() discontinuities by extrapolating at boundary
  
  FOR boundary IN tier_boundaries:
    // Compute rate from both tiers at boundary
    hot_rate = rate_from_hot(boundary - 5min, boundary)
    warm_rate = rate_from_warm(boundary, boundary + 5min)
    
    // If discontinuity > 10%: Log warning, don't try to smooth
    // Users accept the visual discontinuity as "resolution changed here"
    // Trying to smooth introduces false data

STAFF TRADE-OFF:
  Option A: Hide resolution differences (interpolate/smooth)
    Pro: Smooth-looking graph
    Con: Introduces false precision, masks real behavior
    
  Option B: Show resolution change visually (annotation or step change)
    Pro: Honest representation of data
    Con: Looks "weird" to non-technical users
  
  Staff decision: Option B. Annotate the boundary. Never fabricate data.
  "The graph shows what we actually measured, at the resolution we stored it."
```

## Component 6: Alert Engine

### Internal Design

```
struct AlertEngine:
  rules: List<AlertRule>
  state: HashMap<AlertFingerprint, AlertState>
  
  // Runs independently from query engine
  // Has its own data access path for reliability

struct AlertRule:
  name: string
  expression: string        // e.g., "rate(errors[5m]) > 10"
  for_duration: Duration    // e.g., 2 minutes
  labels: HashMap<string, string>  // e.g., severity="critical"
  annotations: HashMap<string, string>  // e.g., dashboard URL

struct AlertState:
  status: enum { INACTIVE, PENDING, FIRING, RESOLVED }
  active_since: Timestamp       // when expression first became true
  firing_since: Timestamp       // when "for" duration was met
  resolved_at: Timestamp        // when expression became false
  last_evaluation: Timestamp
  current_value: float64

EVALUATION LOOP:

FUNCTION evaluate_rules():
  EVERY evaluation_interval (e.g., 15 seconds):
    FOR rule IN rules:
      result = query_engine.instant_query(rule.expression)
      
      FOR series IN result:
        fingerprint = hash(rule.name + series.labels)
        current_state = state.get(fingerprint, INACTIVE)
        
        IF series.value meets threshold:
          IF current_state == INACTIVE:
            state.set(fingerprint, PENDING, active_since=now())
          ELSE IF current_state == PENDING:
            IF now() - state.active_since >= rule.for_duration:
              state.set(fingerprint, FIRING, firing_since=now())
              NOTIFY(rule, series, "firing")
          // FIRING stays FIRING (don't re-notify)
        ELSE:
          IF current_state == FIRING:
            state.set(fingerprint, RESOLVED, resolved_at=now())
            NOTIFY(rule, series, "resolved")
          ELSE:
            state.set(fingerprint, INACTIVE)
```

### Alert Grouping and Deduplication

```
PROBLEM: If 100 pods of service "api" all have high error rates,
you don't want 100 separate pages to the on-call.

SOLUTION: Alert grouping

GROUP BY: {service, alertname}

All 100 alerts with alertname="HighErrorRate" and service="api"
are grouped into ONE notification:

  "[FIRING: 100] HighErrorRate - service=api
   100 instances affected:
   - pod-abc: 15.3 errors/sec
   - pod-def: 12.1 errors/sec
   - pod-ghi: 11.8 errors/sec
   ... and 97 more"

DEDUPLICATION:
  If alert is already FIRING, don't re-notify.
  Re-notify only if:
  - Alert RESOLVES (send resolution)
  - Alert changes severity
  - Configured repeat_interval expires (e.g., every 4 hours if still firing)

INHIBITION:
  If "cluster_down" alert is firing, suppress all alerts from that cluster.
  WHY: If the entire cluster is down, individual pod alerts are noise.
```

### Why Alert Engine Must Be Isolated

```
SCENARIO: Traffic spike → All services emit more metrics → TSDB overloaded
→ Queries slow down → Alert evaluation falls behind → Alerts don't fire

THIS IS THE WORST POSSIBLE FAILURE: The observability system fails to detect
the very incident it exists to detect.

ISOLATION STRATEGIES:

1. Dedicated query path for alerts:
   Alert engine has its own data replicas or read path
   Not shared with dashboard/ad-hoc queries

2. Pre-computed alert data:
   Common alert expressions are computed on the ingestion path
   (streaming aggregation) → Alert engine reads pre-computed values
   → No query fan-out needed

3. Alert engine on separate infrastructure:
   Different cluster, different failure domain
   Even if TSDB is overloaded, alert engine continues evaluating
   from its local data copy

4. Heartbeat monitoring:
   Alert engine itself is monitored by a SEPARATE system
   "Dead man's switch": If alert engine stops sending heartbeat
   → External system pages on-call

Staff principle: "Who watches the watchers?" The alert engine must be
monitored by something outside the metrics system.
```

## Component 7: Downsampling / Roll-up Engine

### Design

```
PURPOSE: Convert high-resolution data to lower resolution for long-term storage

RAW DATA (15-second intervals):
  Time: 10:00:00  10:00:15  10:00:30  10:00:45  10:01:00
  Value:    42        45        43        47        44

1-MINUTE ROLL-UP:
  Time: 10:00:00 → 10:01:00
  min: 42, max: 47, sum: 221, count: 5, avg: 44.2

1-HOUR ROLL-UP:
  Time: 10:00:00 → 11:00:00
  min: 38, max: 52, sum: 2,650, count: 60, avg: 44.17

WHY store min/max/sum/count (not just avg):
  - avg(avg) ≠ avg (mathematical error compounds)
  - sum(sum) = sum (correct)
  - max(max) = max (correct)
  - count(count) = count (correct for re-aggregation)
  - With sum and count: avg = sum/count (exact)

DOWNSAMPLING PIPELINE:

FUNCTION downsample():
  EVERY 1 hour:
    // 15s → 1min roll-up (keep for 30 days)
    raw_data = read_raw(time_range=[-2h, -1h])  // process 1h of data
    FOR series IN raw_data:
      FOR minute_window IN 1_minute_windows(series):
        roll_up = compute_rollup(minute_window)
        write_to_warm_storage(series.labels, roll_up)
    
  EVERY 1 day:
    // 1min → 1hr roll-up (keep for 1 year)
    minute_data = read_warm(time_range=[-48h, -24h])
    FOR series IN minute_data:
      FOR hour_window IN 1_hour_windows(series):
        roll_up = compute_rollup(hour_window)
        write_to_cold_storage(series.labels, roll_up)

STORAGE COST IMPACT:

  Resolution      Samples/day/series    Bytes/day/series (compressed)
  15-second       5,760                 ~8 KB
  1-minute        1,440                 ~2 KB
  1-hour          24                    ~48 bytes
  1-day           1                     ~16 bytes

  For 5 BILLION time series:
  Raw 15s for 1 year: 5B × 8KB × 365 = 14.6 PETABYTES
  1-min for 1 year:   5B × 2KB × 365 =  3.65 PB
  1-hr for 1 year:    5B × 48B × 365 =  87.6 TB
  1-day for 5 years:  5B × 16B × 1825 = 146 TB

  Downsampling saves >99% of storage cost for long-term retention.
```

## Component 8: Service Discovery at Scale

```
PROBLEM: In a pull-based or hybrid collection model, the system must know
WHERE all scrape targets are. At 10M containers, this is a service
discovery problem in its own right.

SCALE CHALLENGE:
  10M containers × 3 metadata fields (IP, port, labels) = 30M records
  Container churn: 10% per hour (Kubernetes pod restarts, deploys)
  = 1M service discovery updates per hour = ~280 updates/second

APPROACHES:

1. CENTRALIZED SERVICE REGISTRY (e.g., Consul, etcd):
   Agents register themselves → Collectors read registry
   Problem at scale: Single registry becomes bottleneck at 10M entries
   with 280 updates/sec. etcd watch streams become expensive.
   
2. KUBERNETES API (for K8s-native environments):
   Collectors watch K8s API for pod events
   Problem: K8s API server handles ~100 watchers well, not 200 agent
   scrapers all watching simultaneously.
   
3. HIERARCHICAL DISCOVERY (Google's approach):
   ┌──────────────────┐
   │ Global Registry  │ (knows which clusters exist)
   └────────┬─────────┘
            │
   ┌────────▼─────────┐
   │ Cluster Registry │ (knows which pods exist in this cluster)
   └────────┬─────────┘
            │
   ┌────────▼─────────┐
   │ Agent on Node    │ (knows which pods exist on this node)
   └──────────────────┘
   
   Each agent scrapes LOCAL pods (already knows them via kubelet)
   → No global service discovery needed for scraping
   → Agent pushes to collector (collector doesn't need to know targets)
   
   This is WHY push-based wins at hyperscale: You eliminate the
   service discovery problem entirely. Each agent knows its local pods.

FAILURE BEHAVIOR IF IGNORED:
  - Stale service registry → Scraping dead IPs → False "target down" alerts
  - Missing registrations → New pods not monitored → Silent blind spots
  - Registry overload → All scrapers lose target list → Mass data gap

Staff insight: "At Google scale, we moved from pull to push partly because
service discovery for pull doesn't scale gracefully beyond ~100K targets.
Push with per-node agents makes the discovery problem trivially local."
```

---

# Part 7: Data Model & Storage Decisions

## What Data Is Stored

```
1. TIME-SERIES SAMPLES:
   (metric_name, labels, timestamp, value)
   
   Example:
   ("http_requests_total", {service:"api", method:"GET", status:"200"}, 
    1705312200, 42847.0)

2. METADATA:
   - Metric descriptions (HELP text)
   - Metric types (counter, gauge, histogram, summary)
   - Label schemas (expected labels per metric)
   - Cardinality limits per metric

3. INDEX DATA:
   - Inverted index: label → series_id mapping
   - Forward index: series_id → label set
   - Series fingerprint → shard mapping

4. ALERT STATE:
   - Alert rule definitions
   - Current alert state (inactive/pending/firing)
   - Notification history
   - Silence rules

5. DASHBOARD DEFINITIONS:
   - JSON dashboard configs
   - Query templates
   - Permissions
   - Version history

6. ROLL-UP DATA:
   - Aggregated time-series (min, max, sum, count per window)
   - Stored in separate storage tier from raw data
```

## How Data Is Keyed

```
TIME-SERIES IDENTIFICATION:

Primary key: Series fingerprint
  fingerprint = hash(metric_name + sorted(label_key_value_pairs))
  
  Example:
  metric: "http_requests_total"
  labels: {service:"api", method:"GET", status:"200"}
  fingerprint: hash("http_requests_total" + "method=GET|service=api|status=200")
             = 0x7A3F2B1C

  WHY sorted labels: {service:"api", method:"GET"} must equal 
  {method:"GET", service:"api"}. Sorting ensures canonical form.

DATA ACCESS PATTERNS:

Pattern 1: Point lookup (given series + time range):
  Key: (fingerprint, start_time, end_time)
  Use: "Show me this specific metric over the last hour"

Pattern 2: Label query (given label matchers + time range):
  Key: Label matchers → inverted index → set of fingerprints → data
  Use: "Show me all metrics where service=api"

Pattern 3: Aggregation (given label matchers + aggregation function):
  Key: Same as Pattern 2, but with server-side computation
  Use: "Sum of all requests across all pods for service=api"
```

## How Data Is Partitioned

```
PARTITIONING STRATEGY: Hash-based on series fingerprint

shard_id = fingerprint % num_shards

WHY hash-based (not time-based):
  - All data for a series is on one shard → No cross-shard queries for single series
  - Even distribution regardless of label cardinality
  - No hotspots from popular metrics (unless hash collision)

WHY NOT time-based partitioning:
  - All writes go to the "current" time partition → Write hotspot
  - A single series spans all time partitions → Cross-partition query
  - Compaction must happen within each partition → More I/O

SHARD SIZING:

Target: 10–50M active time series per shard
  Why lower bound: Below 10M, overhead of running a shard isn't justified
  Why upper bound: Above 50M, index exceeds comfortable memory footprint
  
For 5B active series:
  5B / 25M per shard = 200 TSDB shards

REPLICATION:
  Hot data: Replication factor 2 (write to primary + 1 replica)
  Warm/cold data: Object store replication (3× by default in S3/GCS)
  
  WHY only RF=2 for hot:
  - Hot data is ephemeral (48h retention)
  - Losing a shard loses 48h of data for that shard's series
  - Data can be re-scraped (agents have 10-minute buffer)
  - RF=3 would cost 50% more for data that's replaced in 48 hours
```

## Retention Policies

```
TIERED RETENTION:

┌────────────────────────────────────────────────────────────────────────┐
│ Tier   │ Resolution │ Retention │ Storage         │ Cost/GB/month      │
├────────────────────────────────────────────────────────────────────────┤
│ Hot    │ 15 seconds │ 48 hours  │ Local SSD/NVMe  │ $$$$ (highest)     │
│ Warm   │ 1 minute   │ 30 days   │ Object store    │ $$                 │
│ Cold   │ 1 hour     │ 1 year    │ Object store IA │ $                  │
│ Archive│ 1 day      │ 5 years   │ Glacier/archive │ ¢ (cheapest)       │
└────────────────────────────────────────────────────────────────────────┘

PER-NAMESPACE OVERRIDES:
  - Critical business metrics: Raw for 7 days, 1-min for 1 year
  - Infrastructure metrics: Raw for 24h, 1-min for 30 days
  - Debug metrics: Raw for 6h, no long-term retention
  
  Staff insight: Not all metrics are equal. Let teams configure retention
  per namespace, but set org-wide defaults that optimize for cost.
```

## Schema Evolution

```
CHALLENGE: Metrics schemas change over time

SCENARIO 1: Label added
  Before: http_requests_total{service="api", status="200"}
  After:  http_requests_total{service="api", status="200", region="us-east"}
  
  Impact: New time series created (different label set = different fingerprint)
  Old series: Stops receiving data (goes stale)
  Queries spanning the change: Must handle both labeled and unlabeled series
  Solution: Query engine treats missing labels as empty string

SCENARIO 2: Label renamed
  Before: http_requests_total{svc="api"}
  After:  http_requests_total{service="api"}
  
  Impact: Complete break. Old data uses "svc", new data uses "service"
  Solution: Recording rules that map old labels to new labels
  OR: Relabeling at ingestion time (rewrite "svc" → "service")
  
  Staff warning: Label renames are expensive. Avoid them.

SCENARIO 3: Metric type changed
  Before: request_latency (gauge, point-in-time snapshot)
  After:  request_latency (histogram, with buckets)
  
  Impact: Complete semantic break. Old data can't be queried as histogram.
  Solution: Create new metric name (request_latency_seconds_bucket)
  
  Staff principle: NEVER change a metric's type. Create a new metric.

SCENARIO 4: Unit change
  Before: request_latency (milliseconds)
  After:  request_latency_seconds (seconds)
  
  Impact: Dashboards and alerts using old metric show wrong values
  Solution: Always include units in metric names from the start
  Convention: {metric}_{unit} (e.g., request_duration_seconds)
```

## Why Other Data Models Were Rejected

```
RELATIONAL DATABASE (PostgreSQL):
  Rejected because:
  - Row-per-sample: 200M inserts/sec overwhelms any RDBMS
  - Column-per-metric: Schema changes for every new metric
  - B-tree index: Not optimized for time-range scans
  - Compression: 10–50× worse than Gorilla encoding
  Where it works: Alert rule storage, dashboard config, metadata

DOCUMENT DATABASE (MongoDB):
  Rejected because:
  - JSON overhead per sample (10–50× more than compressed TSDB)
  - No native time-range scan optimization
  - Index per label would be enormous
  Where it works: Nowhere for time-series at scale

KEY-VALUE STORE (Redis, DynamoDB):
  Rejected because:
  - No native range queries (must store as sorted sets)
  - Memory cost for hot data is 100× TSDB with compression
  - No built-in downsampling
  Where it works: Real-time alerting state (small data set)

WIDE-COLUMN STORE (Cassandra, HBase):
  Partially suitable:
  + Good write throughput (append-only, LSM-tree)
  + Horizontal scaling
  - No time-series-specific compression
  - Query planning must be external
  - Compaction behavior not optimized for time-series patterns
  Where it works: As a backing store for TSDB warm tier
  
  Staff example: Many production TSDB implementations (Cortex, Thanos)
  use object storage or Cassandra for long-term storage, with a TSDB
  format on top providing compression and indexing.
```

## Histogram Bucket Boundary Selection

```
PROBLEM: Histogram bucket boundaries are chosen at metric definition time
and CANNOT be changed retroactively without losing comparability with
historical data.

WHY THIS MATTERS:
  Bucket boundaries: [5ms, 10ms, 25ms, 50ms, 100ms, 250ms, 500ms, 1s, 2.5s, 5s, 10s]
  
  If your service typically responds in 1-5ms:
  → 99% of values fall in the first bucket [0, 5ms]
  → You can't distinguish P50=1ms from P99=4ms
  → The histogram is useless for this service
  
  If your service typically responds in 500ms-2s:
  → Only 3 buckets cover this range [500ms, 1s, 2.5s]
  → P90 vs P99 has very low resolution
  
  WRONG bucket boundaries are an IRREVERSIBLE design mistake
  if you need to compare across time.

SELECTION STRATEGY:

1. SERVICE-SPECIFIC BUCKETS:
   Allow each service to define custom bucket boundaries.
   API service: [1ms, 5ms, 10ms, 25ms, 50ms, 100ms, 250ms, 500ms]
   Batch service: [100ms, 500ms, 1s, 5s, 10s, 30s, 60s, 300s]
   
2. GEOMETRIC PROGRESSION (default safe choice):
   boundaries = [base × ratio^i for i in 0..N]
   Example: base=1ms, ratio=2, N=15
   → [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384ms]
   
   Provides uniform resolution on a log scale.
   
3. NATIVE HISTOGRAMS (emerging approach):
   Dynamic buckets that adapt to the observed distribution.
   No pre-defined boundaries → No mis-configuration risk.
   
   Trade-off: Higher cardinality (more series per histogram),
   more complex merging across instances.
   
   Staff assessment: Native histograms are the future but not yet
   mature in most TSDB implementations. Design for fixed buckets
   with per-service customization, plan for native histogram migration.

FAILURE BEHAVIOR IF IGNORED:
  - SLO reports show P99 as "250ms" when it's actually "490ms"
    (because there's no bucket between 250ms and 500ms)
  - Capacity planning decisions based on inaccurate percentiles
  - Performance regressions go undetected (hidden within a bucket)

REAL-WORLD APPLICATION (Notification Delivery System):
  Notification delivery latency varies from 50ms (push) to 30s (email).
  Default buckets: [5ms, 10ms, 25ms, ...] → All email notifications
  fall in the last bucket. Can't measure email P50 vs P99.
  
  Fix: Service-specific buckets:
  Push: [10ms, 25ms, 50ms, 100ms, 250ms, 500ms, 1s]
  Email: [1s, 2s, 5s, 10s, 15s, 20s, 30s, 60s]
  SMS: [500ms, 1s, 2s, 5s, 10s, 15s, 30s]
```

---

# Part 8: Consistency, Concurrency & Ordering

## Strong vs Eventual Consistency

```
WRITE PATH: Eventual consistency is acceptable

Scenario: Sample written at T=100 is queryable at T=105
  5 seconds of staleness is fine for dashboards.
  
  WHY strong consistency would be harmful:
  - Synchronous replication doubles write latency
  - Consensus protocol (Raft/Paxos) limits write throughput
  - Metrics are high-volume, low-value-per-sample data
  - Losing a few samples during failures is acceptable

READ PATH: Read-your-writes consistency within a session

Scenario: Engineer creates alert rule, then checks if it's evaluating
  Must see the rule they just created.
  
  Implementation: Sticky routing to the same query engine for a session
  OR: Alert rule store uses strongly consistent database

CROSS-SHARD QUERIES: Eventual consistency

Scenario: Query spans multiple TSDB shards
  Each shard may be at slightly different ingestion offsets
  → Results from shard A might include T=100 while shard B only has T=95
  
  Acceptable because:
  - 5-second skew is invisible on a 6-hour dashboard
  - Aggregations (sum, avg) tolerate small timing differences
  - Alternative (global clock synchronization) is prohibitively expensive
```

## Race Conditions

```
RACE 1: Concurrent writes to same series

Scenario: Two agents report the same metric simultaneously
(can happen with misconfigured service discovery)

  Agent A: write(series_1, t=100, value=42)
  Agent B: write(series_1, t=100, value=43)

Resolution: Last-write-wins (LWW)
  Both writes go to WAL → Both appear in head block
  During compaction: If same (series, timestamp), keep latest value
  
  WHY this is acceptable: Metric values from the same series at the same
  timestamp should be identical (they come from the same source).
  If they're different, it indicates a configuration error.

RACE 2: Query during compaction

Scenario: Query reads block A while compaction replaces block A with block B

Resolution: Block immutability + reference counting
  - Blocks are immutable once written
  - Compaction creates NEW block, then atomically swaps the pointer
  - Old block stays readable until all active queries finish
  - Garbage collection deletes old block only when ref_count = 0

RACE 3: Alert evaluation vs dashboard query

Scenario: Alert evaluates at T=100, dashboard loads at T=100
  Both should see the same data → But may not if data is arriving

Resolution: Accept the race
  - Alert uses latest available data
  - Dashboard uses latest available data
  - They might see slightly different values (seconds apart)
  - This is acceptable; both are "correct" for their evaluation time

RACE 4: Downsampling vs raw query

Scenario: Downsampling job reads raw data while new raw data arrives

Resolution: Downsampling operates on closed time windows
  - Only downsample [T-2h, T-1h] (already past, no new data arriving)
  - Raw data for current hour is still being written
  - No conflict between downsampling and ingestion
```

## Idempotency

```
INGESTION IDEMPOTENCY:

Scenario: Agent retries sending a batch (network timeout, didn't see ACK)
  → Same samples sent twice

Design: Writes are naturally idempotent in TSDB
  - Same (series, timestamp, value) → Written again → Same result
  - Even if written twice in WAL, compaction deduplicates
  
  Edge case: Same (series, timestamp) with DIFFERENT value
  → LWW resolution (implementation-dependent which "wins")
  → Not a correctness problem because this indicates a bug in the agent

ALERT NOTIFICATION IDEMPOTENCY:

Scenario: Alert engine evaluates, fires notification, crashes before 
recording that it notified → On restart, evaluates again, fires again

Design: Notification deduplication
  - Generate deterministic notification_id from (alert_fingerprint, firing_since)
  - Notification channel deduplicates by notification_id
  - Downstream (PagerDuty, Slack) also deduplicate
```

## Ordering Guarantees

```
WITHIN A SINGLE TIME SERIES:
  Samples MUST be ordered by timestamp.
  Out-of-order writes are typically REJECTED (with error metric).
  
  WHY: TSDB compression assumes monotonically increasing timestamps.
  Out-of-order data breaks delta-of-delta encoding.
  
  Mitigation: Agents sort samples by timestamp before sending.
  Tolerance: Some TSDBs accept out-of-order within a small window (e.g., 5 min)
  using a separate out-of-order head block.

ACROSS TIME SERIES:
  No ordering guarantee. Series are independent.
  
  This is fine because queries aggregate across series,
  and aggregation functions (sum, avg, max) are commutative.

ACROSS SHARDS:
  No ordering guarantee. Each shard processes independently.
  
  Impact: A query spanning shards may see shard A at T=100 and shard B at T=95.
  Mitigation: Query engine aligns timestamps during merge.
```

## Clock Assumptions

```
PROBLEM: Metric timestamps come from the reporting host's clock.
If host clocks are skewed, metrics are misaligned.

TYPICAL CLOCK SKEW:
  With NTP: < 100ms between hosts in same datacenter
  Without NTP: Minutes to hours of drift
  Across regions: ~1ms with PTP, ~50ms with NTP

IMPACT OF SKEW:
  - Two services' metrics don't line up on dashboards
  - Cause-and-effect analysis is wrong ("A happened before B" is incorrect)
  - Rate calculations are inaccurate (rate = Δvalue / Δtime; wrong Δtime = wrong rate)

MITIGATION:
  1. Use server-side timestamping when possible (collector stamps the sample)
  2. Reject samples with timestamps too far from server time (> 5 minutes)
  3. For cross-service correlation, use logical ordering (trace IDs) not timestamps

WHAT BUGS APPEAR IF MISHANDLED:
  - "Negative rate" alerts: Counter appears to go backward due to clock jump
  - "Phantom spike" in dashboards: Samples with future timestamps appear as spike
  - "Missing data" in dashboards: Samples with past timestamps fall outside query range
```

---

# Part 9: Failure Modes & Degradation

## Failure Mode 1: TSDB Shard Failure

```
FAILURE: Single TSDB shard crashes (OOM, disk failure, kernel panic)

BLAST RADIUS:
  - 1/200 of all time series are temporarily unavailable
  - Queries touching those series return partial results or errors
  - Alert rules touching those series may miss firing
  - Ingestion for those series queues in collectors (buffer)

USER-VISIBLE SYMPTOMS:
  - Dashboards show gaps in some panels
  - Some alert rules show "evaluation error"
  - "No data" for specific services/endpoints

DEGRADATION STRATEGY:
  1. Collectors buffer data for failed shard (10-minute ring buffer)
  2. Query engine returns partial results with warning header
  3. Alert engine marks affected rules as "evaluation_failure" 
     → Separate meta-alert fires: "alert evaluation failing"
  4. Replica shard (if configured) serves reads

RECOVERY:
  1. Shard restarts → Replays WAL → Rebuilds index
  2. Collectors drain buffer → Shard catches up
  3. Gap in data: 0 to WAL size (typically < 1 minute)

TIMELINE:
  T+0s:    Shard crashes
  T+1s:    Collectors detect connection failure
  T+5s:    Collectors start buffering
  T+10s:   Alert: "TSDB shard X unreachable"
  T+30s:   Shard auto-restarted by orchestrator
  T+60s:   WAL replay complete, shard accepting writes
  T+90s:   Collector buffer drained, data gap < 30 seconds
  T+120s:  Full recovery, alert resolves
```

## Failure Mode 2: Collector Fleet Degradation

```
FAILURE: 30% of collector fleet becomes unavailable (bad deploy, resource contention)

BLAST RADIUS:
  - Remaining collectors handle 1.43× normal traffic
  - If at capacity: Some metric samples dropped
  - Agents retry → More load on remaining collectors

USER-VISIBLE SYMPTOMS:
  - Intermittent gaps in metrics
  - Dashboard auto-refresh shows flickering data
  - Some alerts become noisy (flapping on/off)

DEGRADATION STRATEGY:
  1. Load balancer detects unhealthy collectors, routes to healthy ones
  2. Agents use client-side load balancing with circuit breakers
  3. Collectors activate load shedding: Drop low-priority metrics first
     Priority: alert-relevant > SLO > infrastructure > debug
  4. Auto-scaler provisions replacement collectors

RECOVERY:
  Auto-scaling brings fleet to sufficient capacity within 2–5 minutes.
  Data gap: Duration of the degradation × percentage of dropped samples.
```

## Failure Mode 3: Cardinality Explosion

```
FAILURE: Engineer deploys code that adds request_id as a label to a histogram

TIMELINE:
  T+0min:   Deploy starts rolling out
  T+2min:   100 pods have new code, each emitting 1000 new series/second
  T+5min:   100,000 new time series created per minute
  T+10min:  TSDB shard index growth accelerates
  T+15min:  TSDB shard memory usage at 80% → Warning alert
  T+20min:  Cardinality enforcer detects limit breach → Starts rejecting
  T+25min:  If enforcer missed it: TSDB shard at 95% memory → Critical
  T+30min:  If not stopped: OOM → Shard crash → Cascading failure to
            other shards as ingestion reroutes

USER-VISIBLE SYMPTOMS:
  - "Metric cardinality limit exceeded" alerts
  - Specific metric queries slow down dramatically
  - Dashboard timeouts for affected metric

PREVENTION (more important than recovery):
  1. Cardinality enforcer at collector (HLL-based, < 1ms overhead)
  2. CI/CD check: Reject metric definitions with unbounded labels
  3. Pre-production metric testing environment
  4. Per-metric cardinality quotas

RECOVERY:
  1. Identify the offending metric and label
  2. Block the label at collector level (instant, no deploy needed)
  3. Delete the excess time series from TSDB
  4. Roll back the offending deploy
```

## Failure Mode 4: Query Engine Overload

```
FAILURE: 100 engineers open incident dashboards simultaneously
(coincides with the incident causing high metric volumes)

BLAST RADIUS:
  - Query engine saturated → All queries slow
  - Alert evaluation queries delayed → Alerts late or missing
  - Dashboard loading takes 30+ seconds → Engineers frustrated

DEGRADATION STRATEGY:
  1. Priority queuing: Alert queries > dashboard > ad-hoc
  2. Query result caching: Same dashboard panels share query results
  3. Load shedding: Reject ad-hoc queries under load
  4. Rate limiting per user: No single engineer can monopolize capacity
  5. Stale cache serving: Show slightly stale dashboard data (10s old)
     rather than waiting for fresh query

PREVENTION:
  - Alert evaluation on separate query infrastructure
  - Dashboard queries pre-cached on schedule (not on-demand)
  - Query cost estimation rejects expensive queries proactively
```

## Failure Mode 5: Network Partition

```
FAILURE: Network split between agent fleet and collector fleet

Agents in partition A: Can reach Collector A but not Collector B
Agents in partition B: Can reach Collector B but not Collector A

IMPACT:
  - TSDB continues receiving data from reachable agents
  - Unreachable agents buffer locally (10-minute buffer)
  - Dashboards show partial data (only one side of partition)
  - Alerts may fire incorrectly (seeing 50% traffic as a "drop")

MITIGATION:
  1. Agents use multiple collector endpoints (retry different endpoint on failure)
  2. Collectors are deployed across availability zones
  3. Alert rules account for partial data: 
     "IF request_rate < threshold AND up{service="api"} > 0.5"
     (Only alert if more than 50% of targets are reporting)
  
  Staff insight: The most dangerous partition is between the alert engine
  and TSDB. Use dedicated low-latency links for this path.
```

## Failure Timeline Walkthrough

```
SCENARIO: Major incident with cascading observability failures

T-5min:   Database primary fails over
T-0:      Application error rate spikes from 0.01% to 15%
T+15s:    Alert rule evaluates: error_rate > 1% for 30s → PENDING
T+45s:    Alert rule evaluates again: still > 1% → FIRING
T+46s:    PagerDuty notification sent to on-call
T+50s:    On-call opens incident dashboard
T+52s:    Dashboard loads (showing data up to T+40s due to ingestion lag)
T+1min:   On-call sees error spike, checks per-endpoint breakdown
T+2min:   Metric volume spikes 3× (error logging increases counters)
T+3min:   Collector fleet at 70% capacity (handling burst)
T+4min:   All hands on deck → 50 engineers open dashboards
T+5min:   Query engine load doubles from dashboard queries
T+5.5min: Alert evaluation delayed (query engine contention)
          → Alert re-evaluations taking 45s instead of 15s
T+6min:   Load shedding activates: Ad-hoc queries deprioritized
T+7min:   Alert evaluation stabilizes at 30s intervals
T+8min:   Root cause identified via dashboards: DB failover caused
          connection errors in service-A
T+10min:  Service-A restarted with new DB connection string
T+12min:  Error rate returns to normal
T+13min:  Alert resolves → Resolution notification sent
T+15min:  Dashboard metric volume returns to baseline
T+20min:  Query engine load returns to normal

LESSONS:
1. Alert evaluation was nearly impacted by dashboard query load (should be isolated)
2. Ingestion lag of ~15s was acceptable but noticeable during diagnosis
3. Load shedding worked but should have activated sooner
4. 50 engineers opening dashboards simultaneously is a predictable load pattern
   → Pre-cache dashboards during incidents
```

## Failure Mode 6: Slow Dependency Behavior

```
SCENARIO: Object store (warm tier) experiences 10× latency increase
(responds, but at 500ms instead of 50ms)

WHY THIS IS HARDER THAN TOTAL FAILURE:
  Total failure: Circuit breaker trips → Fallback to degraded mode → Clear signal
  Slow dependency: Requests succeed → But consume threads/connections longer
  → Thread pool exhaustion → Cascading slowness → Looks like "everything is slow"

TIMELINE:
  T+0min:   Object store latency increases from 50ms to 500ms
  T+1min:   Query engine threads for warm-tier queries held 10× longer
  T+2min:   Thread pool occupancy rises from 30% to 90%
  T+3min:   New queries queue behind slow queries → Dashboard load times 5×
  T+4min:   Alert evaluation queries also delayed (if sharing thread pool)
  T+5min:   Engineers open dashboards to investigate slowness
            → More queries → Thread pool saturated → Everything halts
  T+7min:   Timeout cascades: Queries time out, get retried, more load

MITIGATION:
  1. SEPARATE THREAD POOLS per storage tier
     Hot queries: Dedicated pool (never starved by warm/cold)
     Warm queries: Dedicated pool with aggressive timeout (2s)
     Cold queries: Dedicated pool with very aggressive timeout (5s)
     
  2. LATENCY-BASED CIRCUIT BREAKING
     IF p99_latency(object_store) > 200ms for 30 seconds:
       Stop sending warm-tier queries
       Return "data unavailable for this time range" for warm tier
       Continue serving hot-tier data normally
     
  3. TIMEOUT HIERARCHY
     Query timeout: 30s (overall)
     Per-shard timeout: 5s (fail fast, return partial)
     Object store read timeout: 2s (don't wait for slow storage)
     
     If any sub-request exceeds its timeout:
       Return partial result with "incomplete" annotation
       DO NOT retry automatically (retry storms kill you here)

REAL-WORLD APPLICATION (applied to API Gateway metrics):
  An API gateway team queries "P99 latency over 7 days" for capacity planning.
  This query spans hot (48h) + warm (remaining 5 days).
  If warm storage is slow:
  - Hot portion returns in 200ms (good)
  - Warm portion takes 8s (slow)
  - Without tier-specific timeouts: User waits 8s, all panels on dashboard block
  - With tier-specific timeouts: Hot portion renders instantly,
    warm portion shows "loading" or "data unavailable", user still gets
    actionable data for the recent 48 hours

Staff insight: Partial answers fast are ALWAYS better than complete answers slow
during an incident. The on-call engineer cares about the last hour, not last week.
```

## Failure Mode 7: Retry Storms Under Partial Collector Failure

```
SCENARIO: 30% of collector fleet goes down → Agents retry to remaining 70%

WHY THIS IS DANGEROUS:
  Normal: 100 collectors handle 200M samples/sec = 2M samples/sec each
  After failure: 70 collectors must handle 200M samples/sec = 2.86M each
  PLUS: Failed sends from agents retry → 30% of traffic retried → 260M effective
  70 collectors now face: 260M / 70 = 3.71M/sec each (1.86× normal)
  
  If collectors were at 60% capacity: Now at 111% → Overloaded
  Overloaded collectors start dropping → Agents retry those too → Cascade

FAILURE BEHAVIOR IF IGNORED:
  T+0:    30% collectors fail
  T+10s:  Agents detect failure, retry to remaining collectors
  T+20s:  Remaining collectors at 110% → Start dropping
  T+30s:  Agents see more failures → Retry harder
  T+40s:  Remaining collectors at 150% → OOM risk
  T+60s:  50% of all metrics lost → Dashboards show massive gaps
  T+90s:  Alert engine misses real incidents due to data loss

MITIGATION:
  1. EXPONENTIAL BACKOFF WITH JITTER at agent level
     Base: 1s, Max: 60s, Jitter: ± 50%
     Prevents synchronized retry waves
     
  2. AGENT-SIDE CIRCUIT BREAKER
     After 3 consecutive failures to a collector:
       Mark collector as unhealthy for 30 seconds
       Don't retry to it → Spread load across healthy collectors
     
  3. LOAD-AWARE ROUTING
     Agents periodically receive load reports from collectors
     Route preferentially to least-loaded collector
     
  4. COLLECTOR ADMISSION CONTROL
     When load > 80%: Accept only priority-1 metrics (SLO-related)
     When load > 90%: Accept only from known agents (reject unknown sources)
     When load > 95%: Return 503 immediately (don't process, let agent buffer)

  5. COLLECTOR AUTO-SCALING TRIGGER
     IF collector_fleet_utilization > 70% for 60 seconds:
       Scale up by 50% (not 10%—you need headroom for cascading load)
     Scaling must complete in < 2 minutes to be useful

EXPLICIT TRADE-OFFS:
  - Aggressive backoff: Reduces retry storm but increases data loss window
  - Load shedding: Protects collectors but drops metrics
  - Auto-scaling: Adds capacity but takes 1-2 minutes (gap remains)
  
  Staff decision: All three simultaneously. Backoff buys time, load shedding
  protects the surviving fleet, auto-scaling provides permanent relief.
```

## Failure Mode 8: Cascading Platform Deploy Causes Self-Monitoring Blindness

```
SCENARIO: Bad collector deploy breaks metric ingestion → 
Platform's own metrics stop flowing → 
Meta-alerts can't evaluate → 
Nobody knows the platform is broken.

CASCADING FAILURE TIMELINE:

T+0min:   Bad config pushed to 100% of collectors simultaneously
          (skipped canary — "it's just a config change")
T+0min:   Config causes collectors to reject all samples with
          a specific label format (regex bug)
T+1min:   40% of all metrics silently dropped (matching the bad regex)
T+2min:   Remaining 60% still flowing → TSDB looks "slightly lower"
          but not alarmingly so
T+3min:   Platform team's own metrics: collector_ingestion_rate drops
          BUT: This metric is emitted by the collectors themselves
          → Collectors still emit their OWN metrics (they work)
          → Drop only visible in APPLICATION metrics
T+5min:   Alert rules evaluate: Some show "no data" (dropped metrics)
          → Alert engine marks these as "evaluation_failure"
          → Meta-alert: "5% of alert rules failing evaluation"
T+8min:   Teams notice dashboards showing lower-than-expected traffic
          → Support tickets: "Our dashboard shows half the traffic"
T+10min:  Platform on-call investigates
          → Platform's own dashboards look FINE
          (collectors are healthy, TSDB is healthy)
          → Application dashboards are broken
T+15min:  On-call realizes: It's not an application issue,
          it's a COLLECTOR FILTERING issue
T+18min:  Config rollback initiated
T+20min:  Config deployed → Metrics resume
T+25min:  Buffered data from agents partially backfills (10-min buffer)
T+30min:  Gap in data: 10-30 minutes for affected metrics

USER-VISIBLE IMPACT:
  - 20 minutes of missing metrics for 40% of all services
  - Alerts for 40% of services were non-functional
  - During those 20 minutes, 2 real incidents were missed
  - Total blast radius: 40% of organization blind for 20 minutes

ROOT CAUSE ANALYSIS:
  1. Config change skipped canary → 100% blast radius
  2. Platform metrics and application metrics are different paths
     → Platform looks healthy while applications are blind
  3. No "end-to-end canary metric" to detect filtering bugs

PREVENTION:
  1. NEVER deploy collector config to 100% without canary
  2. END-TO-END CANARY: Inject a known synthetic metric at the application
     level → Verify it arrives in TSDB within 60 seconds
     IF canary metric missing → IMMEDIATE alert via external system
  3. Compare collector "received" count vs "forwarded" count
     IF divergence > 1% → Alert: "Collector filtering more than expected"
```

## On-Call Runbooks for the Metrics Platform Itself

```
THE IRONY: The system designed to help on-call engineers IS a system
that needs on-call engineers. The metrics platform's own operational
maturity must exceed its customers' expectations.

RUNBOOK 1: HIGH INGESTION LATENCY
  Alert: ingestion_lag_seconds > 30 for 5 minutes
  
  Diagnosis steps:
  1. Check collector fleet utilization
     → IF > 80%: Scale up collectors (auto-scaling may be delayed)
  2. Check TSDB write queue depth per shard
     → IF one shard hot: Likely cardinality bomb on that shard
     → Check cardinality enforcer metrics
  3. Check network utilization between collectors and TSDB
     → IF saturated: Either traffic spike or network issue
  4. Check for recent deploys to collector fleet
     → IF yes: Canary regression, rollback
  
  Escalation: If not resolved in 15 minutes, page secondary on-call

RUNBOOK 2: TSDB SHARD OOM
  Alert: tsdb_shard_memory_usage > 90% OR tsdb_shard_down
  
  IMMEDIATE:
  1. Identify the shard (from alert labels)
  2. Check if cardinality spike is active (cardinality_enforcer_rejections)
     → IF yes: Identify offending metric, block at collector level
  3. If shard crashed:
     → Verify auto-restart initiated
     → Monitor WAL replay progress
     → Estimate data gap from collector buffer metrics
  4. If shard at 90% but not crashed:
     → Manually trigger compaction (reduce memory pressure)
     → Consider emergency series deletion for obvious junk series

RUNBOOK 3: ALERT EVALUATION DELAYED
  Alert: alertmanager_evaluation_duration_seconds > 60
  
  This is a P0 because delayed alerts = missed incidents.
  
  IMMEDIATE:
  1. Check if alert engine has its own data path (should be isolated)
  2. Check query engine load (dashboard thundering herd?)
  3. Check for expensive alert rules (new rule added?)
     → Top-N alert rules by evaluation time
  4. If dashboard load is the cause:
     → Verify load shedding is active for ad-hoc queries
     → Scale query engine (will take 2-5 minutes)
  5. If specific rule is slow:
     → Disable the rule temporarily
     → Investigate and optimize (usually missing recording rule)

RUNBOOK 4: STORAGE COST SPIKE
  Alert: monthly_projected_cost > budget * 1.2
  
  Not an emergency but needs action within days:
  1. Run cost attribution report (per-team breakdown)
  2. Identify top growth contributors
  3. Check for cardinality growth (new labels added without registration)
  4. Check for retention policy compliance (data not being downsampled?)
  5. Notify team leads of top offenders with cost data
  6. If immediate action needed: Increase downsampling aggressiveness

META-MONITORING (who watches the watchers):
  The metrics platform CANNOT monitor itself with its own metrics
  (circular dependency). External monitoring required:
  
  1. EXTERNAL HEARTBEAT:
     Separate system (could be as simple as a cron job on a different server)
     sends a "canary" metric every 60 seconds.
     IF canary metric not received for 3 minutes → Page via separate channel
     
  2. BLACK-BOX PROBING:
     External prober sends a query every 30 seconds:
     GET /api/v1/query?query=up{job="metrics_canary"}
     IF response time > 10s OR status != 200 → Page
     
  3. ALTERNATE ALERTING PATH:
     Critical meta-alerts route through a DIFFERENT notification system
     (e.g., if primary is PagerDuty, backup is OpsGenie or direct SMS)
     
     Never have the metrics platform's own alerts go through the same
     alert engine that might be the thing that's broken.
```

---

# Part 10: Performance Optimization & Hot Paths

## Critical Paths

```
PATH 1: METRIC EMISSION (In-process)
  Budget: < 1μs per metric update
  
  Optimizations:
  - Lock-free atomic counters (no mutex contention)
  - Pre-allocated label sets (no memory allocation on hot path)
  - Lazy serialization (only serialize when scraped/flushed)
  
  Anti-pattern: "Metric per request" with dynamic label generation
  → String allocation + map lookup + hash computation on EVERY request

PATH 2: INGESTION (Agent → Collector → TSDB)
  Budget: < 10 seconds end-to-end
  
  Bottleneck: TSDB write (WAL append + head block update)
  Optimization: Batch writes (500+ samples per write operation)
  
  Anti-pattern: Individual sample writes
  → 200M individual WAL fsyncs/sec is impossible
  → Batch: 200M samples in 40K batches of 5000 = 40K fsyncs/sec (achievable)

PATH 3: DASHBOARD QUERY (Interactive)
  Budget: < 500ms for standard dashboard panel
  
  Bottleneck: Series resolution (label match → series IDs)
  Optimization:
  - In-memory inverted index (microsecond lookups)
  - Result caching (same panel query doesn't re-execute)
  - Partial response (return available data immediately, fill gaps)
  
PATH 4: ALERT EVALUATION
  Budget: < 15 seconds per evaluation cycle
  
  Optimization:
  - Pre-computed common aggregations (streaming aggregation)
  - Incremental evaluation (only re-evaluate changed data)
  - Parallel rule evaluation across alert engine instances
```

## Caching Strategies

```
LAYER 1: QUERY RESULT CACHE

  Key: (query_expression, time_range, step)
  Value: Query result matrix
  TTL: min(step_interval, 15 seconds)
  
  Hit rate: 60–80% for dashboards (panels refresh every 15s with same query)
  
  Invalidation: Time-based (TTL), NOT data-based
  WHY: Data-based invalidation requires tracking which series changed,
  which is more expensive than re-executing the query.

LAYER 2: SERIES RESOLUTION CACHE

  Key: Label matchers (e.g., {service="api", status="200"})
  Value: Set of series IDs matching those matchers
  TTL: 5 minutes
  
  WHY: Label → series ID resolution is expensive (inverted index intersection).
  Series membership changes slowly (new pods, new deployments).
  5-minute staleness means a new pod's metrics appear with up to 5-min delay.

LAYER 3: CHUNK CACHE

  Key: (series_id, block_id, chunk_offset)
  Value: Decompressed chunk data
  
  WHY: Decompression is CPU-intensive. Caching decompressed chunks avoids
  repeated decompression of frequently queried series.
  
  Size: 10–30% of hot data fits in chunk cache
  Hit rate: 80%+ for dashboard queries (same time range, same series)

LAYER 4: BLOCK INDEX CACHE

  Key: block_id
  Value: In-memory representation of block's posting lists
  
  WHY: Loading block index from disk on every query adds 10–50ms.
  Keeping recent block indexes in memory eliminates this.
```

## Precomputation vs Runtime Work

```
PRECOMPUTATION (Streaming Aggregation):

What: Compute common aggregations on the ingestion path

Example:
  Raw: http_requests_total{service="api", pod="pod-1", status="200"} = 42
       http_requests_total{service="api", pod="pod-2", status="200"} = 38
       http_requests_total{service="api", pod="pod-3", status="200"} = 51

  Pre-aggregated: http_requests_total:sum_by_service{service="api", status="200"} = 131

  Query that would touch 1000 series → Now touches 1 series

WHEN to precompute:
  - Aggregation used by alerts (must be fast)
  - Aggregation used by many dashboards (shared cost)
  - Aggregation across many series (high fan-out reduction)

WHEN NOT to precompute:
  - Ad-hoc queries (can't predict what users will query)
  - Drill-down queries (need per-pod data, not aggregated)
  - Low-cardinality metrics (aggregation cost is trivial)

RECORDING RULES:
  Declarative pre-computation:
  
  rule: "api_error_rate_5m"
  expression: "rate(http_requests_total{service='api', status='500'}[5m]) / 
               rate(http_requests_total{service='api'}[5m])"
  evaluation_interval: 15s
  
  Result: New time series "api_error_rate_5m" written to TSDB
  Alert rules and dashboards use the pre-computed series → 10–100× faster
```

## Backpressure

```
BACKPRESSURE CHAIN:

  Application → Agent → Collector → TSDB
  
  If TSDB is slow:
  1. TSDB write queue fills → Returns backpressure signal to collector
  2. Collector buffers in memory (bounded) → Returns 429 to agents
  3. Agent buffers locally (ring buffer) → Continues scraping
  4. Agent buffer fills → DROPS oldest samples
  5. Application is NEVER backpressured (non-blocking metrics)

CRITICAL DESIGN DECISION: Application is NEVER slowed by metrics.
  The monitoring system must not cause the outage.
  
  Implementation:
  - Agent uses non-blocking channel for sample submission
  - If channel full → Drop sample, increment dropped_total counter
  - Application metric call returns immediately (< 1μs) regardless
```

## Load Shedding

```
When system is overloaded, shed load in priority order:

PRIORITY 1 (Never shed): Alert evaluation queries
PRIORITY 2 (Shed last): Dashboard queries for active incidents
PRIORITY 3 (Shed early): Ad-hoc exploration queries
PRIORITY 4 (Shed first): Batch reporting queries

IMPLEMENTATION:
  Query engine assigns priority based on:
  - Source: alert_engine > dashboard > api > batch
  - Query cost: Expensive queries more likely to be shed
  - User: Rate limit per user to prevent monopolization

  When load > threshold:
  1. Reject PRIORITY 4 queries with 429
  2. Queue PRIORITY 3 with timeout
  3. Serve PRIORITY 1 and 2 normally
  4. If still overloaded: Serve stale cached results for PRIORITY 2
```

## Why Some Optimizations Are Intentionally NOT Done

```
NOT DONE: Exact percentile computation
  WHY NOT: Requires storing all raw values or using complex sketches.
  Histogram buckets are good enough (< 5% error) and 100× cheaper.
  Exact percentiles only matter for SLO compliance, where recording rules
  pre-compute the exact value from histograms.

NOT DONE: Sub-second ingestion latency
  WHY NOT: Batching at 10–15 second intervals reduces network overhead 100×.
  The 10-second ingestion lag is invisible for dashboards and alerting.
  Systems needing sub-second would use a separate streaming pipeline.

NOT DONE: Global time-series ordering
  WHY NOT: Ordering across all series requires global coordination.
  Series are independent; cross-series ordering adds complexity
  with zero benefit (aggregations are commutative).

NOT DONE: Per-query adaptive resolution
  WHY NOT: Automatically adjusting resolution (e.g., returning 1-minute data
  instead of 15-second for wide time ranges) seems smart but confuses users.
  A 6-hour dashboard showing different resolution than a 1-hour dashboard
  leads to "why do the numbers not match?" confusion. Let users explicitly
  choose resolution.
```

---

# Part 11: Cost & Efficiency

## Major Cost Drivers

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                  COST BREAKDOWN (TYPICAL)                                   │
│                                                                             │
│   40% │ STORAGE                                                             │
│       │ ├── Hot (SSD): High $/GB, fast, 48h retention → 15% of total        │
│       │ ├── Warm (Object store): Low $/GB, 30-day retention → 20%           │
│       │ └── Cold (Archive): Very low $/GB, 1+ year → 5%                     │
│       │                                                                     │
│   30% │ COMPUTE (QUERY)                                                     │
│       │ ├── Query engine CPU/RAM → 20%                                      │
│       │ └── Alert evaluation CPU → 10%                                      │
│       │                                                                     │
│   20% │ COMPUTE (INGESTION)                                                 │
│       │ ├── Collector fleet → 10%                                           │
│       │ ├── TSDB write path → 8%                                            │
│       │ └── Streaming aggregation → 2%                                      │
│       │                                                                     │
│   10% │ NETWORK                                                             │
│       │ ├── Agent → Collector (intra-DC): Low cost                          │
│       │ └── Cross-region replication: Higher cost                           │
│       │                                                                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

## How Cost Scales with Traffic

```
INGESTION COST: Linear with time-series count
  2× more series = 2× more collector capacity, 2× more storage

  BUT cardinality is the real driver:
  Doubling container count → 2× series (linear, predictable)
  Adding one label with 100 values → 100× series (combinatorial, dangerous)

QUERY COST: Super-linear with series count
  Query touching N series costs O(N) for data scan + O(N log N) for sort
  But most queries aggregate → O(N) is dominant
  
  Dashboard refresh cost is proportional to:
  (number of panels) × (series per panel) × (time range / step)

STORAGE COST:
  Short-term: Dominated by active series count × resolution × retention
  Long-term: Dominated by unique series ever created × retention
  
  "Dead series" problem: A pod that existed for 1 hour creates time series
  that occupy index space for the entire retention period.
  At Google scale: 10M container churn per day = 10M × 500 = 5B dead series
  created per day. Without cleanup, storage grows without bound.

  Solution: Series lifecycle management
  - Mark series "stale" after no samples for 5 minutes
  - Stale series excluded from index after compaction
  - Data retained per retention policy, but index pressure reduced
```

## Trade-offs Between Cost and Reliability

```
TRADE-OFF 1: Hot storage duration vs query performance
  Longer hot retention: Better query performance, higher cost
  Shorter hot retention: Cheaper, but queries spanning boundary are slow
  
  Decision: 48 hours hot, with chunk cache for warm tier
  This covers 99.9% of incident investigation queries in hot storage.

TRADE-OFF 2: Replication factor vs cost
  RF=3: Highest reliability, 3× storage cost
  RF=2: Good reliability, 2× storage cost
  RF=1: Cost-optimal, data loss on failure
  
  Decision: RF=2 for hot (ephemeral data), RF=3 for warm/cold (via object store)

TRADE-OFF 3: Ingestion buffer size vs data loss risk
  Large buffers: Survive longer outages, more memory cost
  Small buffers: Cheaper, but data loss during brief outages
  
  Decision: 10-minute buffer at agent, 5-minute buffer at collector
  Covers 99% of transient failures.
```

## What Over-Engineering Looks Like

```
OVER-ENGINEERING 1: Exactly-once ingestion semantics
  Cost: 2–3× complexity, ~50% throughput reduction for consensus
  Benefit: Zero duplicate samples
  Reality: Duplicate samples are harmless (deduplicated by TSDB)
  Decision: At-least-once is sufficient

OVER-ENGINEERING 2: Strong consistency across TSDB shards
  Cost: Cross-shard coordination, 10× write latency
  Benefit: Consistent reads across all series
  Reality: 5-second cross-shard staleness is invisible
  Decision: Eventual consistency

OVER-ENGINEERING 3: ML-based anomaly detection for all metrics
  Cost: GPU clusters, training pipelines, false positive management
  Benefit: Detect anomalies humans would miss
  Reality: Most anomalies are detectable with simple threshold alerts
  Decision: ML for a few critical SLO metrics; static thresholds for rest

OVER-ENGINEERING 4: Per-sample encryption at rest
  Cost: 2× CPU for encrypt/decrypt, key management complexity
  Benefit: Compliance for sensitive metrics
  Reality: Most metrics (CPU, latency, error rate) are not sensitive
  Decision: Encrypt the storage volume, not individual samples
```

## Cost-Aware Redesign

```
SCENARIO: Budget cut requires 40% cost reduction

Current: 5B active series, 15s resolution, 48h hot, 30d warm, 1y cold

OPTIONS:

Option A: Reduce hot retention from 48h to 24h
  Savings: ~7% (hot storage is only 15% of cost, halving it saves ~7%)
  Risk: Incident investigation spanning > 24h hits warm storage (slower)
  Decision: Acceptable

Option B: Increase scrape interval from 15s to 30s
  Savings: ~30% (half the samples = half the ingestion + storage)
  Risk: Alert detection latency increases, dashboard resolution decreases
  Decision: Apply to non-critical metrics only (80% of series)
  → 80% × 30% = 24% savings

Option C: Aggressive pre-aggregation
  Current: Store per-pod metrics → 100 pods × 200 metrics = 20K series per service
  Proposed: Pre-aggregate to per-service → 200 series per service (100× reduction)
  Savings: 20% (eliminates per-pod storage for non-debug metrics)
  Risk: Can't drill down to per-pod during incidents
  Decision: Keep per-pod in hot tier, pre-aggregate for warm/cold
  → ~15% savings

Combined: A + B + C = 7% + 24% + 15% = 46% savings
```

## Chargeback / Showback Cost Attribution Mechanism

```
PROBLEM: At 5B time series costing $20M/year, someone must pay.
Without cost attribution, the platform team absorbs all cost,
teams have no incentive to clean up, and the CFO asks
"why is monitoring costing us $20M?"

ATTRIBUTION MODEL:

COST FORMULA PER TEAM:
  team_cost = (ingestion_cost × team_ingestion_fraction)
            + (storage_cost × team_storage_fraction)
            + (query_cost × team_query_fraction)

MEASURING EACH COMPONENT:

1. INGESTION FRACTION:
   Each metric sample carries a namespace label (e.g., team="api-platform")
   Collector tracks: samples_ingested_total{namespace="..."} per team
   Team's fraction = team_samples / total_samples

2. STORAGE FRACTION:
   Each time series tagged with owning namespace
   TSDB reports: active_series{namespace="..."} per team
   Team's fraction = team_series / total_series
   
   IMPORTANT: Storage cost includes DEAD series (created but no longer active)
   Teams must be charged for dead series to incentivize cleanup.

3. QUERY FRACTION:
   Query engine logs: query_cost_units{user_namespace="..."} per query
   Cost units = series_touched × samples_read × wall_time
   Team's fraction = team_query_cost / total_query_cost

DASHBOARD (self-service):
  Each team sees:
  ┌───────────────────────────────────────────-─┐
  │  Team: API-Platform                         │
  │  Monthly Cost: $18,500                      │
  │  Trend: +12% month-over-month               │
  │                                             │
  │  Top 5 Metrics by Cost:                     │
  │  1. http_request_duration_seconds  $4,200   │
  │  2. grpc_server_handled_total      $3,100   │
  │  3. connection_pool_metrics        $2,800   │
  │  4. cache_hit_ratio                $1,200   │
  │  5. custom_business_metric         $1,100   │
  │                                             │
  │  Unused Metrics (no queries in 30d): $2,800 │
  │  → [Clean Up Now] button                    │
  │                                             │
  │  Quota: 50M series (used: 32M, 64%)         │
  └────────────────────────────────────────────-┘

WHY SHOWBACK (not chargeback) IS USUALLY BETTER:
  Chargeback: Team is actually billed, deducted from their budget
  Showback: Team sees the cost but doesn't directly pay
  
  Staff experience: Chargeback leads to teams hiding metrics
  (under-instrumenting to save money) which is WORSE than over-spending.
  Showback with soft nudges (monthly reports, unused metric alerts)
  achieves 80% of the cost reduction without the perverse incentive.
  
  Exception: At hyperscaler scale, chargeback is necessary because
  the absolute numbers are too large for showback alone to control.
```

---

# Part 12: Multi-Region & Global Considerations

## Data Locality

```
PRINCIPLE: Metrics should be stored close to where they are generated.

REGION A (US-East):
  Services emit metrics → Ingested by REGION A collectors → Stored in REGION A TSDB
  Engineers in REGION A query REGION A TSDB → Low latency

REGION B (EU-West):
  Services emit metrics → Ingested by REGION B collectors → Stored in REGION B TSDB
  Engineers in REGION B query REGION B TSDB → Low latency

CROSS-REGION QUERIES:
  "Show me error rate for service=api across ALL regions"
  
  Two approaches:
  
  1. QUERY FAN-OUT (query time):
     Global query engine sends sub-queries to each region
     Each region returns results → Global engine merges
     
     Pros: No data replication, always fresh
     Cons: Query latency = max(regional latency) + network round-trip
           If one region is slow, entire query is slow
  
  2. GLOBAL VIEW (pre-replicated):
     Each region pushes aggregated metrics to a global TSDB
     Global queries hit the global TSDB
     
     Pros: Fast queries (local read)
     Cons: Replication cost, ingestion lag (30–60s behind regional)
           Not suitable for per-pod granularity (cardinality explosion)
  
  Staff decision: Hybrid
  - Per-pod metrics: Local only (query fan-out for cross-region)
  - Aggregated metrics: Replicated to global view
  - Alert evaluation: Regional (each region evaluates its own alerts)
  - Global alerts: Evaluated on global view (e.g., "total revenue across regions")
```

## Replication Strategies

```
WITHIN REGION:
  TSDB: Synchronous replication within AZ (RF=2)
  Object store: Managed by cloud provider (RF=3, cross-AZ)

ACROSS REGIONS:
  Raw data: NOT replicated (too expensive, too much data)
  Aggregated data: Async replication to global view (30–60s lag)
  Alert rules: Synchronously replicated (strong consistency via config store)
  Dashboard configs: Synchronously replicated (small data, critical)

CONFLICT RESOLUTION:
  Metrics are append-only → No write conflicts
  Alert rules: Last-write-wins with version vector
  Dashboard configs: Last-write-wins with manual merge for conflicts
```

## Traffic Routing

```
METRIC INGESTION ROUTING:
  Agents always push to local regional collectors (never cross-region)
  WHY: Cross-region ingestion adds 50–200ms latency and egress cost

QUERY ROUTING:
  Dashboard → Check query scope
  IF query is regional: Route to regional query engine
  IF query is global: Route to global query engine
  IF query fan-out needed: Global engine → regional engines → merge

  Optimization: Dashboards auto-detect scope from label matchers
  {region="us-east"} → Route to US-East only
  {service="api"} (no region label) → Route to global view or fan-out
```

## Failure Across Regions

```
SCENARIO: EU-West region is completely offline

IMPACT:
  - EU-West metrics stop being collected (agents buffer locally)
  - Global dashboards show gap for EU-West data
  - Global aggregations are partial (sum across regions is low)
  - EU-West regional alerts stop evaluating

MITIGATION:
  1. Global alert rules detect missing region:
     "IF absent(up{region='eu-west'}) for 5 minutes → Page"
  2. Global dashboards show "EU-West data unavailable" annotation
  3. Global aggregations exclude EU-West (partial result with caveat)
  4. EU-West agents buffer locally (10 minutes)
  5. On recovery: Agents drain buffer → Backfill ~10 minutes of data
  6. Gap > 10 minutes: Lost data (acceptable for regional outage scenario)

Staff insight: A regional failure that takes down the observability system
for THAT region is acceptable (you can't observe a dead region). What's
NOT acceptable is a regional failure taking down GLOBAL observability.
The global view must remain operational even if one region is offline.
```

## When Multi-Region Is NOT Worth It

```
FOR THE METRICS SYSTEM ITSELF:
  Multi-region is ALWAYS worth it if your application is multi-region.
  You need observability in each region where your services run.

HOWEVER, global view is NOT worth it when:
  1. < 3 regions: Query fan-out to 2 regions is fast enough
  2. No global SLOs: If each region has independent SLOs, no need for global view
  3. Cost-constrained: Global view adds replication cost
  4. Low query rate: If only 2 engineers ever look at global dashboards,
     fan-out latency is acceptable

Decision heuristic: If cross-region queries happen > 100 times/day,
build a global view. Otherwise, use query fan-out.
```

---

# Part 13: Security & Abuse Considerations

## Abuse Vectors

```
VECTOR 1: METRIC FLOOD (intentional or accidental)
  Attack: Send millions of fake metric samples to collectors
  Impact: Overwhelm ingestion → Real metrics delayed or lost
  
  Mitigation:
  - Authentication for all ingestion (mTLS or API key)
  - Per-source rate limiting (max samples/sec per agent)
  - Per-namespace quotas (team can't use more than allocated cardinality)

VECTOR 2: CARDINALITY BOMB
  Attack: Submit metrics with high-cardinality labels (random strings)
  Impact: Exhaust TSDB memory → Crash → All metrics unavailable
  
  Mitigation:
  - Cardinality enforcer at collector (HyperLogLog-based)
  - Label value validation (reject labels matching suspicious patterns)
  - Alert on cardinality growth rate (> 10% increase per hour)

VECTOR 3: QUERY OF DEATH
  Attack: Submit extremely expensive query (e.g., ".*" regex on all metrics)
  Impact: Query engine consumes all memory → OOM → Other queries fail
  
  Mitigation:
  - Query cost estimation before execution
  - Per-query memory limits
  - Per-user concurrency limits
  - Query abort on timeout

VECTOR 4: ALERT MANIPULATION
  Attack: Modify alert rules to suppress real alerts or create false ones
  Impact: Incidents go undetected (suppression) or on-call fatigue (false)
  
  Mitigation:
  - Alert rule changes require approval (code review)
  - Audit log for all alert rule modifications
  - "Canary" alerts that must always be firing (integrity check)
```

## Rate Abuse

```
SCENARIO: Runaway application emitting 100× normal metric volume

This is not malicious but has the same impact as an attack.

DETECTION:
  - Per-source ingestion rate tracked at collector
  - Alert when source exceeds 2× historical baseline

RESPONSE (automated):
  1. Rate limit the source to 2× baseline
  2. Alert the source's team: "Your service is emitting excessive metrics"
  3. Buffer excess in dead letter queue for manual review
  4. If sustained: Escalate to team lead

PREVENTION:
  - Client libraries enforce emission rate limits
  - CI/CD checks for metric cardinality in new code
  - Quota management per team/namespace
```

## Data Exposure

```
SENSITIVE DATA IN METRICS:
  Metric values themselves are usually not sensitive
  (CPU utilization, request count are not PII)
  
  BUT labels can be sensitive:
  - user_id, email, ip_address in labels → PII exposure
  - internal service names → Architecture exposure
  - error messages in labels → Potential secret leakage

MITIGATION:
  - Label allowlisting: Only pre-approved labels accepted
  - PII scanning: Reject labels matching PII patterns
  - Namespace isolation: Team A cannot query Team B's metrics
  - Dashboard permissions: Role-based access to dashboards
  - Audit logging: Track who queries what
```

## Privilege Boundaries

```
ROLES:

METRIC EMITTER (application):
  - Can: Push metrics within their namespace
  - Cannot: Push to other namespaces, query metrics, modify alerts

DASHBOARD VIEWER:
  - Can: View dashboards, run queries within their namespace
  - Cannot: Modify dashboards, create alerts, access other namespaces

ALERT AUTHOR:
  - Can: Create/modify alert rules within their namespace
  - Cannot: Modify other teams' alerts, access admin functions

PLATFORM ADMIN:
  - Can: Manage global config, cardinality limits, retention policies
  - Cannot: (Full access, but actions are audit-logged)

SEPARATION:
  Ingestion path (write) and query path (read) have separate auth.
  Compromising a query API key doesn't allow metric injection.
  Compromising an ingestion API key doesn't allow data extraction.
```

## Why Perfect Security Is Impossible

```
1. Metric data must be accessible during incidents:
   Restricting access too tightly means the on-call can't see metrics
   when the building is on fire. Availability > perfect security.

2. Label content is controlled by application developers:
   You can validate format but not semantic content.
   A developer can name a label "x" and put a user_id in it.
   
3. Side-channel information:
   Even without direct access, metric PATTERNS reveal information:
   "Traffic dropped 50% at 3 AM" reveals business information.
   Fully preventing side-channel leakage requires impractical isolation.

4. The observability system itself needs observability:
   Metrics about the metrics system must be accessible to debug it.
   This creates a recursive trust boundary problem.

PRACTICAL STANCE: Defense in depth with accept-and-monitor.
Apply reasonable controls, assume they'll be bypassed occasionally,
and audit everything.
```

## Multi-Team Governance and Platform Ownership

```
PROBLEM: A metrics platform serving 500 teams needs clear governance.
Without it, you get tragedy of the commons: everyone emits metrics,
nobody cleans up, costs explode, and cardinality bombs are weekly events.

ORGANIZATIONAL STRUCTURE:

PLATFORM TEAM (5-10 engineers):
  Owns: Collector fleet, TSDB, query engine, alert engine, storage
  Provides: Self-service onboarding, documentation, client libraries
  SLOs: Ingestion availability, query latency, data completeness
  
SERVICE TEAMS (500 teams):
  Own: Their metrics definitions, alert rules, dashboards
  Responsible for: Staying within cardinality quotas, meaningful alerts
  Self-service: Register metrics, create dashboards, define alerts

GOVERNANCE MECHANISMS:

1. METRIC REGISTRATION (self-service with guardrails):
   Developer defines new metric in config file:
     name: http_request_duration_seconds
     type: histogram
     labels: [service, method, status, endpoint]
     max_cardinality: 5000
     owner: team-api
     retention_tier: 2  (30-day warm)
   
   CI/CD pipeline validates:
   - Label names are in allowed set (no PII patterns)
   - Estimated cardinality < quota
   - Metric name follows naming convention
   - Type is appropriate for use case
   
   Deployed to production: Collector fleet accepts this metric.
   Unregistered metrics: REJECTED at collector.

2. QUOTA MANAGEMENT:
   Each team has allocated:
   - Max active series: 50M (default, adjustable)
   - Max ingestion rate: 5M samples/sec
   - Max storage: 10TB warm tier
   
   Quotas are:
   - Visible via self-service dashboard
   - Alerting at 80% and 95%
   - Hard limit at 100% (reject excess)
   - Increase requires approval (capacity planning)

3. COST ATTRIBUTION:
   Monthly cost report per team:
   
   Team: API-Platform
   Active series: 32M (64% of 50M quota)
   Ingestion rate: 2.1M samples/sec
   Storage used: 4.7TB
   Query volume: 45K queries/day
   Estimated monthly cost: $18,500
   Top cost drivers:
     - http_request_duration_seconds: $4,200 (22%)
     - grpc_server_handled_total: $3,100 (17%)
     - Unused metrics (no queries in 30 days): $2,800 (15%) ← ACTION NEEDED

4. UNUSED METRIC DETECTION:
   FUNCTION detect_unused_metrics():
     FOR metric IN all_metrics:
       last_queried = query_audit_log(metric)
       IF last_queried > 30 days ago:
         NOTIFY owner: "Metric X hasn't been queried in 30 days.
           Cost: $Y/month. Will be auto-disabled in 14 days."
       IF last_queried > 44 days ago AND no objection:
         DISABLE metric at collector (stop ingesting)
         Historical data retained per policy
   
   This alone typically saves 15-25% of total platform cost.

5. ALERT QUALITY MANAGEMENT:
   Track per-team:
   - Alerts that fire but are immediately silenced (noise)
   - Alerts that fire for > 24 hours with no action (ignored)
   - Alerts with > 10 fires/week (potentially too sensitive)
   
   Monthly report to team leads:
   "Your team has 47 alert rules. 12 fired last month.
    3 were immediately silenced (recommend: delete or fix).
    2 fired 15+ times (recommend: increase threshold or aggregate)."

WHY THIS MATTERS AT L6:
  A Staff Engineer designing a metrics system that serves 500 teams
  MUST address governance. Without it:
  - Costs grow 3× annually from unused metrics alone
  - Cardinality bombs happen weekly (no registration = no validation)
  - On-call for the platform is miserable (constant firefighting)
  - Teams blame the platform for performance problems caused by their own
    high-cardinality metrics
  
  The governance model is as important as the technical architecture.
  Staff engineers design SYSTEMS that include people and processes, not just code.
```

---

# Part 14: Evolution Over Time

## V1: Naive Design

```
V1 ARCHITECTURE (startup, 1000 hosts):

  Application → StatsD (UDP) → Single InfluxDB → Grafana

CHARACTERISTICS:
  - Single database, no sharding
  - UDP for ingestion (fire-and-forget)
  - All metrics in one namespace
  - Fixed dashboards, manual alerts
  - No retention management (keep everything)

WHAT WORKS:
  - Simple to set up (1 hour from zero to dashboards)
  - Low operational overhead
  - Fast queries (small data set)
  - UDP doesn't backpressure applications

SCALE LIMITS:
  - Single InfluxDB: ~1M active time series
  - Single disk: ~100K samples/second write
  - Single query engine: ~100 concurrent queries
  - No redundancy: DB crash = total blindness
```

## What Breaks First

```
BREAK 1: InfluxDB runs out of memory (12 months in)
  Symptom: Queries time out, then OOM crash
  Root cause: Cardinality growth from new services, no limits
  Fix: Manual cleanup of old series, add cardinality monitoring
  
BREAK 2: UDP packet loss during traffic spikes (18 months)
  Symptom: Dashboards show dips that don't match reality
  Root cause: UDP drops under load, no acknowledgment
  Fix: Switch to TCP-based ingestion with buffering

BREAK 3: Single dashboard serves all teams (24 months)
  Symptom: 500 users hitting Grafana simultaneously → Grafana slow
  Root cause: No caching, every panel load = fresh query
  Fix: Add query result cache, dashboard CDN

BREAK 4: No multi-tenancy → "Who used all the disk?" (30 months)
  Symptom: Storage fills up, nobody knows which team is responsible
  Root cause: No per-team quotas or usage tracking
  Fix: Add namespace-based accounting and quotas
```

## V2: Intermediate Design

```
V2 ARCHITECTURE (growth phase, 50K hosts):

  Application → Agent (buffer) → Collector Fleet → Sharded TSDB → Grafana
  
  Added:
  + Agent-based collection (buffer survives transient failures)
  + Collector fleet (stateless, horizontally scalable)
  + Sharded TSDB (hash-based partitioning)
  + Cardinality enforcement (per-metric limits)
  + Namespace isolation (per-team quotas)
  + Tiered retention (hot/warm/cold)
  + Alert engine (separate from query path)

WHAT WORKS:
  - Scales to 100M time series
  - Survives individual node failures
  - Per-team cost attribution
  - Automated alerting

REMAINING PROBLEMS:
  - Single region only
  - Alert engine shares query infrastructure
  - Downsampling is manual
  - No streaming aggregation (all queries are at-query-time)
  - TSDB upgrades require downtime
```

## V3: Long-Term Stable Architecture

```
V3 ARCHITECTURE (mature platform, 500K+ hosts):

  Everything from V2, plus:
  
  + Multi-region with global view
  + Isolated alert evaluation infrastructure
  + Streaming aggregation (recording rules on ingestion path)
  + Automated downsampling pipeline
  + Query cost protection (limits, priorities, load shedding)
  + Self-service metric registration with CI/CD validation
  + Platform observability (metrics about the metrics system)
  + Federated querying across TSDB clusters
  + Object-store-backed long-term storage (infinite retention at low cost)

OPERATIONAL MATURITY:
  - Zero-downtime upgrades (rolling, canary-based)
  - Automated cardinality remediation
  - Capacity planning from historical growth trends
  - SLOs for the metrics system itself:
    • Ingestion availability: 99.99%
    • Alert evaluation latency: P99 < 60s
    • Dashboard query latency: P99 < 3s
    • Data completeness: > 99.9% of emitted samples stored

ARCHITECTURE DIAGRAM:

  ┌───────────────────────────────────────────────────────────────────┐
  │  REGION A                                                         │
  │  ┌────────┐  ┌──────────┐  ┌──────────-┐  ┌────────────────────┐  │
  │  │ Agents │→ │Collectors│-→│  TSDB     │-→│ Object Store (Warm)│  │
  │  └────────┘  └──────────┘  │ (Sharded) │  └────────────────────┘  │
  │                            └─────┬─────┘                          │
  │                                  │        ┌─────────────────┐     │
  │              ┌───────────────────┤        │ Alert Engine    │     │
  │              │                   │        │ (Isolated)      │     │
  │              ▼                   ▼        └─────────────────┘     │
  │  ┌──────────────┐      ┌──────────────┐                           │
  │  │ Query Engine │      │ Streaming    │                           │
  │  │ (Regional)   │      │ Aggregation  │                           │
  │  └──────┬───────┘      └──────────────┘                           │
  │         │                                                         │
  └─────────┼────────────────────────────────────────────────────────-┘
            │ (Aggregated metrics)
            ▼
  ┌──────────────────────────┐
  │  GLOBAL VIEW             │
  │  ┌──────────────────┐    │
  │  │ Global TSDB      │    │ ← Receives aggregated from all regions
  │  │ (Aggregated only)│    │
  │  └────────┬─────────┘    │
  │           │              │
  │  ┌────────▼─────────┐    │
  │  │ Global Query Eng │    │
  │  └────────┬─────────┘    │
  │           │              │
  │  ┌────────▼─────────┐    │
  │  │ Global Alerts    │    │
  │  │ Global Dashboards│    │
  │  └──────────────────┘    │
  └──────────────────────────┘
```

## How Incidents Drive Redesign

```
INCIDENT 1: "Cardinality explosion took down all dashboards for 2 hours"
  → Added: Cardinality enforcer at collector level
  → Added: Per-metric cardinality limits (configurable)
  → Added: Automated blocking of runaway labels

INCIDENT 2: "Alert engine was 15 minutes behind during traffic spike"
  → Redesign: Separated alert evaluation from general query path
  → Added: Dedicated alert data replicas
  → Added: Pre-computed alert data via streaming aggregation

INCIDENT 3: "Query of death OOM'd the query engine, affecting all users"
  → Added: Per-query memory limits and timeouts
  → Added: Query priority system (alerts > dashboards > ad-hoc)
  → Added: Load shedding for low-priority queries

INCIDENT 4: "Storage cost grew 300% in 6 months without corresponding traffic growth"
  → Root cause: Unused metrics never cleaned up, dead series accumulating
  → Added: Automated stale series detection and cleanup
  → Added: Per-team cost dashboards and alerting
  → Added: Metric usage tracking (who queries which metrics)

INCIDENT 5: "Region-B failure caused global dashboards to time out"
  → Redesign: Global view receives pre-aggregated data (not query fan-out)
  → Added: Circuit breaker for cross-region queries
  → Added: Graceful degradation (show partial data with annotation)
```

## Real Incident: Structured Analysis

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│  REAL INCIDENT: CASCADING METRICS PLATFORM DEPLOY BLINDS 40% OF ORGANIZATION                  │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│  Context         │ Bad collector config deployed to 100% of fleet, skipping canary.            │
│                  │ "Just a config change" treated as low-risk. Regex bug in label filter.     │
├──────────────────┼──────────────────────────────────────────────────────────────────────────┤
│  Trigger         │ Config change causes collectors to reject all samples matching a specific │
│                  │ label format. 40% of org metrics silently dropped.                        │
├──────────────────┼──────────────────────────────────────────────────────────────────────────┤
│  Propagation     │ T+0: Config pushed to 100% of collectors simultaneously.                   │
│                  │ T+1min: 40% of metrics dropped. T+3min: Platform metrics still flowing    │
│                  │ (collectors emit their own metrics—platform dashboards look healthy).     │
│                  │ T+5min: Alert rules show "evaluation_failure." T+10min: Support tickets  │
│                  │ from teams: "Our dashboard shows half the traffic."                       │
├──────────────────┼──────────────────────────────────────────────────────────────────────────┤
│  User impact     │ 20 minutes of missing metrics for 40% of all services. 2 real incidents   │
│                  │ missed during the 20-minute window (no alerting for affected teams).       │
│                  │ Application dashboards showed gaps; platform dashboards looked fine.       │
├──────────────────┼──────────────────────────────────────────────────────────────────────────┤
│  Engineer resp.  │ T+10min: Platform on-call investigates. Platform dashboards healthy →    │
│                  │ initially assumed application issue. T+15min: Realization that collector   │
│                  │ filtering is the cause. T+18min: Config rollback. T+20min: Metrics       │
│                  │ resume. T+25min: Partial backfill from agent buffers.                    │
├──────────────────┼──────────────────────────────────────────────────────────────────────────┤
│  Root cause      │ 1. Config change skipped canary → 100% blast radius.                       │
│                  │ 2. Platform metrics vs application metrics on different paths → platform  │
│                  │ looked healthy while applications were blind.                             │
│                  │ 3. No end-to-end canary metric to detect filtering bugs.                   │
├──────────────────┼──────────────────────────────────────────────────────────────────────────┤
│  Design change   │ 1. NEVER deploy collector config to 100% without canary.                  │
│                  │ 2. End-to-end canary: inject synthetic metric at app level → verify        │
│                  │ arrival in TSDB; alert externally if canary missing.                      │
│                  │ 3. Collector "received" vs "forwarded" divergence alert if > 1%.          │
├──────────────────┼──────────────────────────────────────────────────────────────────────────┤
│  Lesson          │ "The metrics platform is self-concealing: its own health hides application│
│                  │ blindness. The blast radius of a bad platform deploy is the entire org.    │
│                  │ Canary every change—especially 'just config.'"                            │
└──────────────────┴──────────────────────────────────────────────────────────────────────────┘
```

**Staff relevance**: This incident exemplifies the observability paradox—the system that detects outages cannot detect its own failure to detect. L6 judgment: design for self-concealing failure by adding external verification (dead-man's switch, end-to-end canary) and never treating platform deploys as low-risk.

## Canary Deployment for the Metrics Platform

```
PROBLEM: A bad deploy to the metrics platform can take down ALL
observability for the entire organization. This is categorically
different from a bad deploy to a single application.

BLAST RADIUS OF BAD PLATFORM DEPLOY:
  - Bug in collector: All metric ingestion affected
  - Bug in TSDB: All metric storage/query affected
  - Bug in query engine: All dashboards and alerts affected
  - Bug in alert engine: All alerting affected
  
  A single bad config change took down a major company's entire
  monitoring stack for 45 minutes. During that 45 minutes, three
  separate production incidents went undetected.

CANARY STRATEGY:

1. SHADOW TRAFFIC (pre-production):
   Fork 1% of live ingestion traffic to a staging TSDB
   Deploy new version to staging
   Compare: Ingestion rate, query correctness, resource usage
   IF deviation > 5% on any metric: BLOCK production deploy

2. ROLLING CANARY (production):
   Stage 1: Deploy to 1 collector (out of 500)
     Monitor for 30 minutes: Ingestion errors, latency, memory
     Automated rollback if: Error rate > 0.1% OR latency > 2× baseline
     
   Stage 2: Deploy to 5% of collectors
     Monitor for 1 hour
     
   Stage 3: Deploy to 25% of collectors
     Monitor for 2 hours
     
   Stage 4: Deploy to 100% of collectors
   
   Total deployment time: ~4 hours
   
   CRITICAL: At each stage, the canary collectors' metrics are compared
   against non-canary collectors. The metrics system can observe its own
   canary health because the non-canary portion is still healthy.

3. TSDB DEPLOY (most dangerous):
   TSDB stores state. A bad TSDB deploy can corrupt data.
   
   Strategy: Deploy to ONE shard first.
   That shard handles 1/200 of traffic.
   Monitor for 4 hours: Ingestion, query, compaction, memory.
   
   IF problem: Rollback that one shard.
   Impact: 0.5% of time series briefly unavailable.
   
   NEVER deploy TSDB changes to all shards simultaneously.

4. QUERY ENGINE DEPLOY:
   Stateless → Safer to canary.
   Deploy to 5% of query engine instances.
   Route specific dashboard queries to canary instances.
   Compare query results: canary vs production.
   IF results diverge: Rollback immediately.

5. ALERT ENGINE DEPLOY (highest risk):
   Alert engine changes can suppress real alerts.
   
   Strategy: Run NEW alert engine in parallel with OLD.
   Both evaluate the same rules.
   Compare outputs: If new engine misses an alert that old catches
   → BLOCK deploy, investigate.
   
   Only cut over after 24 hours of parallel evaluation with no divergence.

STAFF PRINCIPLE:
  "The blast radius of a bad metrics platform deploy is the entire company.
  The deployment velocity of the metrics platform should be the SLOWEST
  of any system in the organization. Move deliberately, not fast."
```

---

# Part 15: Alternatives & Explicit Rejections

## Alternative 1: Pull-Only Architecture (Prometheus Model)

```
DESIGN:
  Central Prometheus server scrapes all targets via HTTP
  All data stored locally on Prometheus server
  PromQL for queries, Alertmanager for alerts

WHY IT SEEMS ATTRACTIVE:
  - Simple operational model (one binary)
  - Excellent for Kubernetes (service discovery built-in)
  - Strong ecosystem (Grafana, exporters, libraries)
  - PromQL is powerful and well-understood

WHY A STAFF ENGINEER REJECTS IT (at scale):
  1. Pull model doesn't scale beyond ~10M series per instance
     → Requires federation, which adds query complexity
  2. Local storage means data loss on crash (no replication by default)
  3. Can't handle short-lived processes (job finishes before scrape)
  4. Scrape interval limits resolution (can't go below ~5s practically)
  5. Federation creates a hierarchy that's hard to query across

WHERE IT FITS:
  - Single cluster, < 5M time series
  - Kubernetes-native environments
  - Teams that want simplicity over scale
  - V1 architecture before scaling pressures

Staff verdict: "Prometheus is an excellent starting point. But if you're
designing a platform to serve 5000 engineers across 10 regions, you need
the push-based, horizontally-sharded architecture described in this chapter."
```

## Alternative 2: Log-Based Metrics (ELK / Splunk Approach)

```
DESIGN:
  Applications log structured events → Log aggregator → Compute metrics at query time
  "Store everything as logs, derive metrics when needed"

WHY IT SEEMS ATTRACTIVE:
  - Single pipeline for logs AND metrics
  - Maximum flexibility (any aggregation possible post-hoc)
  - No pre-definition of metrics needed
  - Familiar (everyone knows how to log)

WHY A STAFF ENGINEER REJECTS IT:
  1. COST: Storing raw events is 100–1000× more expensive than storing aggregated metrics
     Example: 100K req/sec × 1KB per log × 86,400 sec/day = 8.6 TB/day of logs
     Same data as metrics: ~100 time series × 2 bytes per sample = ~11 MB/day
     
  2. QUERY LATENCY: Computing "P99 latency for the last hour" requires scanning
     millions of log entries. Pre-aggregated metrics return in milliseconds.
     
  3. ALERT LATENCY: Evaluating alerts by querying logs takes seconds to minutes.
     Evaluating pre-computed metrics takes milliseconds.
     
  4. CARDINALITY EXPLOSION: Logs have unbounded cardinality by nature.
     Metrics systems can bound cardinality; log systems cannot.

WHERE IT FITS:
  - Low-volume systems (< 1K events/second)
  - Debugging and root cause analysis (complement to metrics)
  - Business event analytics (where per-event detail matters)

Staff verdict: "Logs and metrics serve different purposes. Using logs
for metrics is like using a microscope when you need a telescope.
The right tool for monitoring is purpose-built metrics infrastructure."
```

## Alternative 3: Fully Managed Cloud Metrics (CloudWatch / Datadog / New Relic)

```
DESIGN:
  Use a cloud provider or SaaS vendor's metrics platform
  Application → Vendor SDK → Vendor's infrastructure → Vendor's dashboards

WHY IT SEEMS ATTRACTIVE:
  - Zero operational overhead (vendor manages everything)
  - Instant setup (minutes to first dashboard)
  - Integrated with cloud provider (AWS CloudWatch, GCP Cloud Monitoring)
  - Vendor handles scaling, retention, multi-region

WHY A STAFF ENGINEER REJECTS IT (at hyperscaler scale):
  1. COST AT SCALE: Vendor pricing is per-metric or per-host
     Example: Datadog at 500 custom metrics/host × 10M hosts × $0.05/metric/month
     = $250M/year (!!!!)
     Self-hosted: ~$20M/year for equivalent infrastructure
     
  2. LOCK-IN: Query language, alert format, dashboard format are all proprietary
     Migrating 10,000 dashboards and 500,000 alerts is a multi-year project
     
  3. CONTROL: Can't customize ingestion pipeline, cardinality enforcement,
     or query optimization. What the vendor gives you is what you get.
     
  4. DATA SOVEREIGNTY: Metrics go to vendor's infrastructure
     May violate data residency requirements (GDPR, etc.)
     
  5. RELIABILITY COUPLING: If vendor has an outage, your observability is gone
     During YOUR outage + vendor outage = flying completely blind

WHERE IT FITS:
  - Small to medium companies (< 10K hosts)
  - Teams without platform engineering capacity
  - Non-critical workloads where cost isn't a primary concern
  - As a secondary/backup to self-hosted (defense in depth)

Staff verdict: "Managed metrics are the right default for most companies.
But at Google/hyperscaler scale, the cost and control trade-offs make
self-hosted essential. Know where your company is on this spectrum."
```

---

# Part 16: Interview Calibration (Staff Signal)

## How Interviewers Probe This System

```
PROBE 1: "How do you handle a metric with 1 billion unique label combinations?"
  Testing: Understanding of cardinality as the primary scaling constraint
  
PROBE 2: "Walk me through what happens when a TSDB shard runs out of memory"
  Testing: Failure mode reasoning, blast radius assessment
  
PROBE 3: "Why not just store everything in Kafka and query it?"
  Testing: Understanding of time-series-specific storage optimizations
  
PROBE 4: "How do you ensure alerts fire even when the system is overloaded?"
  Testing: Isolation principle, separation of concerns
  
PROBE 5: "Your storage costs are growing 70% year-over-year. What do you do?"
  Testing: Cost awareness, practical trade-off reasoning
  
PROBE 6: "A dashboard query is taking 30 seconds. How do you diagnose it?"
  Testing: Understanding of query execution, performance analysis

PROBE 7: "How do you add a new region to this system?"
  Testing: Understanding of data locality, replication, and operational complexity
```

## Common L5 Mistakes

```
MISTAKE 1: Ignoring cardinality
  L5: "We'll store any label the developer wants"
  Problem: This is how you get 10 billion time series and a dead TSDB
  Fix: Discuss cardinality limits, enforcement, and monitoring

MISTAKE 2: Coupling alerts to the query path
  L5: "Alerts just query the same database as dashboards"
  Problem: Overloaded query engine → Alerts stop evaluating → Incidents missed
  Fix: Discuss isolation of alert evaluation infrastructure

MISTAKE 3: Storing everything at full resolution forever
  L5: "We'll keep all data at 15-second resolution for a year"
  Problem: This costs 100× more than tiered retention
  Fix: Discuss downsampling, tiered storage, retention policies

MISTAKE 4: Designing for average load
  L5: "At 200M samples/sec, we need X collectors"
  Problem: Peak load during incidents is 2–5× average
  Fix: Discuss burst behavior, backpressure, buffer sizing

MISTAKE 5: Treating all metrics equally
  L5: "All metrics get the same pipeline, same storage, same priority"
  Problem: Debug metrics don't need the same reliability as SLO metrics
  Fix: Discuss metric classification, priority tiers, differentiated SLOs

MISTAKE 6: No discussion of the metrics system's own observability
  L5: (doesn't mention it)
  Problem: "Who watches the watchers?"
  Fix: Discuss meta-monitoring, dead-man's switches, external health checks
```

## Staff-Level Answers

```
STAFF ANSWER 1 (on cardinality):
"Cardinality is the single most important constraint in a metrics system.
I'd enforce limits at three levels: client libraries reject unbounded labels,
collectors use HyperLogLog to detect cardinality explosions in real-time,
and TSDB has hard limits that reject writes beyond threshold. The key insight
is that preventing cardinality problems is 100× cheaper than recovering from them."

STAFF ANSWER 2 (on alerting reliability):
"The alert engine must be the last thing to fail. I'd isolate it on dedicated
infrastructure with its own data path—either a replicated TSDB or pre-computed
aggregations from the ingestion pipeline. And I'd monitor the alert engine
with a separate system entirely—a dead-man's switch that fires if the alert
engine stops sending heartbeats. The question 'who watches the watchers'
must have an answer in the design."

STAFF ANSWER 3 (on cost):
"The cost discussion starts with recognizing that not all metrics are equal.
I'd classify metrics into tiers: Tier 1 (SLO-critical) gets full retention
and replication. Tier 2 (operational) gets 30-day retention with downsampling.
Tier 3 (debug) gets 24-hour retention, no warm storage. This alone typically
saves 50–60% versus treating everything equally."

STAFF ANSWER 4 (on multi-region):
"Regional metrics stay regional—it's too expensive and unnecessary to replicate
per-pod data globally. For global visibility, I'd push pre-aggregated metrics
to a global view with 30–60 second lag. The critical design constraint is:
a regional failure must not impact global observability. The global view
must be available even when a region is completely offline."
```

## Example Phrases a Staff Engineer Uses

```
"The cardinality of the label space determines whether this system works or dies."

"We need to decide: is the observability system allowed to impact application latency?
My answer is no—metric emission must be non-blocking and < 1 microsecond."

"During an incident, the observability system experiences its peak load at the
exact moment it's most critical. We must design for the worst day, not the average day."

"Averages lie. I'd use histogram buckets with pre-defined boundaries and compute
percentiles from those. The 1–5% error from bucketing is acceptable; the
30× cost reduction compared to exact percentiles is not optional."

"Not all metrics deserve the same treatment. Let me classify them into tiers
and apply differentiated retention, replication, and query priority."

"Who watches the watchers? The alert engine must be monitored by something
outside the metrics system—a completely independent heartbeat check."

"The most common incident in metrics infrastructure is a cardinality explosion.
I'd invest heavily in prevention at the ingestion layer."

"Streaming aggregation on the ingestion path converts a 10,000-series alert
query into a 1-series lookup. That's the difference between alerts that
fire in 15 seconds and alerts that fire in 5 minutes."
```

### Additional Google L6 Interview Calibration

```
ADDITIONAL INTERVIEWER PROBES:

PROBE 8: "How do you handle governance when 500 teams share this platform?"
  Testing: Organizational awareness, platform thinking
  L5 answer: "We'll set global limits"
  L6 answer: "Self-service registration with CI/CD validation, per-team quotas
  with showback dashboards, automated unused metric detection, and quarterly
  review with team leads. Governance is as important as the architecture."

PROBE 9: "Walk me through deploying a change to the collector fleet."
  Testing: Operational maturity, blast-radius awareness
  L5 answer: "Rolling deploy with health checks"
  L6 answer: "Shadow traffic validation in staging, 1-node canary for 30 minutes
  with automated rollback on error rate deviation, then 5% → 25% → 100% over
  4 hours. End-to-end synthetic metric canary at every stage. The metrics
  platform is the last thing you want to break with a fast deploy."

PROBE 10: "The object store is returning 500ms instead of 50ms. What happens?"
  Testing: Slow dependency reasoning (distinct from total failure)
  L5 answer: "Queries will be slower"
  L6 answer: "Separate thread pools per storage tier prevent cascading.
  Latency-based circuit breaker on the warm tier trips at 200ms.
  Hot-tier queries (last 48h) are completely unaffected.
  Warm-tier queries show 'data unavailable' rather than waiting 10×.
  The on-call investigating a production incident sees real-time data
  perfectly; only historical exploration is degraded."

ADDITIONAL STAFF SIGNALS:

1. PROACTIVE GOVERNANCE DISCUSSION:
   The candidate brings up "who owns this platform and how do
   500 teams share it responsibly" without being asked.
   This signals Staff thinking: Systems include people and processes.

2. DEPLOY SAFETY AWARENESS:
   The candidate says "the biggest risk to this system is our own deploy"
   and describes a canary strategy. This signals operational maturity.

3. COST AS A DESIGN INPUT:
   The candidate says "let me classify metrics into tiers before
   designing the storage layer" — using cost to inform architecture,
   not as an afterthought.

4. SELF-MONITORING DEPTH:
   The candidate says "who watches the watchers?" and describes
   external heartbeat monitoring, end-to-end canary metrics, and
   alternate notification paths. This is the hallmark of someone
   who has been on-call for a platform.

COMMON L5 MISTAKE (ADDITIONAL):

MISTAKE 7: Treating the metrics platform as "just another service"
  L5: Designs it with the same deployment velocity and testing standards
  as any application service
  Problem: A bad deploy to the metrics platform blinds the entire org.
  Unlike a bad deploy to a single service (which metrics detect),
  a bad deploy to the metrics platform is self-concealing.
  
  L6 fix: The metrics platform has the SLOWEST deployment cadence,
  the MOST conservative canary strategy, and the MOST rigorous
  testing of any system in the organization. "We deploy weekly,
  not hourly, and that's intentional."
```

---

# Part 17: Diagrams

## Diagram 1: Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   METRICS SYSTEM: COMPONENT INTERACTION                     │
│                                                                             │
│  TEACH: How data flows from application to dashboard                        │
│                                                                             │
│  APPLICATION CODE                                                           │
│  ┌─────────────────────────┐                                                │
│  │ counter.increment()     │ ← O(1), non-blocking, < 1μs                    │
│  │ histogram.observe(val)  │                                                │
│  └──────────┬──────────────┘                                                │
│             │ (batched locally)                                             │
│             ▼                                                               │
│  AGENT (per-host)                                                           │
│  ┌─────────────────────────┐                                                │
│  │ Buffer → Batch → Ship   │ ← 10-15s flush interval                        │
│  │ Pre-aggregate           │                                                │
│  └──────────┬──────────────┘                                                │
│             │ (compressed batches)                                          │
│             ▼                                                               │
│  COLLECTOR FLEET (stateless)                                                │
│  ┌─────────────────────────────────────────────────────────┐                │
│  │ Validate → Cardinality Check → Route to Shard           │                │
│  └──────────┬──────────────────────┬───────────────────────┘                │
│             │                      │                                        │
│             ▼                      ▼                                        │
│  TSDB SHARD (hot)           STREAMING AGGREGATION                           │
│  ┌───────────────────┐     ┌────────────────────────┐                       │
│  │ WAL → Head → Block│     │ Pre-compute common     │                       │
│  │ Index (in-memory) │     │ aggregations           │                       │
│  └─────────┬─────────┘     └────────────┬───────────┘                       │
│            │                            │                                   │
│            ├────────────────────────────┘                                   │
│            ▼                                                                │
│  QUERY ENGINE                                                               │
│  ┌─────────────────────────────────────────────────────────┐                │
│  │ Parse → Plan → Fetch → Compute → Return                 │                │
│  │ (with caching, cost limits, priority queuing)           │                │
│  └──────────┬──────────────────────┬───────────────────────┘                │
│             │                      │                                        │
│             ▼                      ▼                                        │
│  DASHBOARDS (Grafana)      ALERT ENGINE (isolated)                          │
│  ┌───────────────────┐     ┌────────────────────────┐                       │
│  │ Visualize metrics │     │ Evaluate rules → Notify│                       │
│  │ for humans        │     │ (PagerDuty, Slack, etc)│                       │
│  └───────────────────┘     └────────────────────────┘                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 2: Data Flow — Write Path Detail

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   WRITE PATH: SAMPLE LIFECYCLE                              │
│                                                                             │
│  TEACH: What happens to a single metric sample, end to end                  │
│                                                                             │
│  T+0ms:     counter.increment({service:"api", status:"200"})                │
│             │                                                               │
│             ▼ Atomic add, no lock                                           │
│  T+0.001ms: In-memory counter = 42,847                                      │
│             │                                                               │
│             │ (Agent scrapes every 15 seconds)                              │
│             ▼                                                               │
│  T+15s:     Agent collects: http_requests_total{...} = 42847 @T=1705312200  │
│             │                                                               │
│             ▼ Batch with ~5000 other samples, compress with Snappy          │
│  T+15.1s:   Agent ships batch to collector (500KB compressed)               │
│             │                                                               │
│             ▼ Collector validates + cardinality check (< 1ms per sample)    │
│  T+15.2s:   Collector routes to TSDB shard (hash of series fingerprint)     │
│             │                                                               │
│             ▼ TSDB writes to Write-Ahead Log                                │
│  T+15.3s:   WAL entry: (series_id=7A3F2B1C, ts=1705312200, val=42847)       │
│             │                                                               │
│             ▼ TSDB updates in-memory head block                             │
│  T+15.4s:   Head block chunk appended (Gorilla-compressed)                  │
│             │                                                               │
│             ╔════════════════════════════════════════════╗                  │
│             ║  SAMPLE IS NOW QUERYABLE                   ║                  │
│             ║  Total latency: ~15 seconds (dominated by  ║                  │
│             ║  scrape interval, not processing time)     ║                  │
│             ╚════════════════════════════════════════════╝                  │
│                                                                             │
│  LATER (every 2 hours):                                                     │
│             Head block full → Flush to immutable on-disk block              │
│                                                                             │
│  LATER (every 6 hours):                                                     │
│             Compaction merges small blocks into larger blocks               │
│                                                                             │
│  LATER (every 48 hours):                                                    │
│             Downsampling: Raw data → 1-minute roll-ups → Warm storage       │
│                                                                             │
│  LATER (every 30 days):                                                     │
│             1-minute roll-ups → 1-hour roll-ups → Cold storage              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 3: Failure Propagation

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   FAILURE PROPAGATION MAP                                   │
│                                                                             │
│  TEACH: How a single component failure propagates (or doesn't)              │
│                                                                             │
│  ┌──────────────┐                                                           │
│  │  TSDB SHARD  │─── FAILS ───┐                                             │
│  │  CRASHES     │             │                                             │
│  └──────────────┘             │                                             │
│                               ▼                                             │
│                    ┌─────────────────────────────┐                          │
│                    │ DIRECT IMPACT               │                          │
│                    │ • 1/N of series unavailable │                          │
│                    │ • Writes queue in collectors│                          │
│                    │ • Reads return partial data │                          │
│                    └──────────┬──────────────────┘                          │
│                               │                                             │
│              ┌────────────────┼────────────────────┐                        │
│              ▼                ▼                    ▼                        │
│  ┌──────────────────┐ ┌─────────────────┐ ┌──────────────────┐              │
│  │ COLLECTOR IMPACT │ │ QUERY IMPACT    │ │ ALERT IMPACT     │              │
│  │ • Buffers fill   │ │ • Dashboards    │ │ • Rules touching │              │
│  │ • After 10min:   │ │   show gaps     │ │   lost series    │              │
│  │   drops samples  │ │ • Users see     │ │   show "no data" │              │
│  │   for that shard │ │   partial data  │ │ • Meta-alert     │              │
│  │                  │ │                 │ │   fires          │              │
│  └──────────────────┘ └─────────────────┘ └──────────────────┘              │
│                                                                             │
│  ╔═══════════════════════════════════════════════════════════════════╗      │
│  ║  ISOLATION BOUNDARIES (what does NOT propagate):                  ║      │
│  ║                                                                   ║      │
│  ║  ✓ Other TSDB shards: Unaffected (independent)                    ║      │
│  ║  ✓ Application performance: Unaffected (agents buffer, non-block) ║      │
│  ║  ✓ Alert engine for other shards: Unaffected (isolated)           ║      │
│  ║  ✓ Dashboard for other services: Unaffected (different shards)    ║      │
│  ╚═══════════════════════════════════════════════════════════════════╝      │
│                                                                             │
│  CONTRAST: CARDINALITY EXPLOSION (worst-case failure)                       │
│                                                                             │
│  ┌──────────────┐                                                           │
│  │  BAD LABEL   │─── EXPLODES ──┐                                           │
│  │  DEPLOYED    │               │                                           │
│  └──────────────┘               │                                           │
│                                 ▼                                           │
│              ┌───────────────────────────────────────────-──┐               │
│              │ IF NOT CAUGHT BY CARDINALITY ENFORCER:       │               │
│              │                                              │               │
│              │ TSDB shard OOM → Crash                       │               │
│              │ ↓                                            │               │
│              │ Ingestion reroutes to replica → Replica OOM  │               │
│              │ ↓                                            │               │
│              │ Shard fully unavailable → Collector buffers  │               │
│              │ ↓                                            │               │
│              │ All shards affected (cardinality on all)     │               │
│              │ ↓                                            │               │
│              │ TOTAL OBSERVABILITY OUTAGE                   │               │
│              │                                              │               │
│              │ THIS IS WHY CARDINALITY ENFORCEMENT IS THE   │               │
│              │ MOST IMPORTANT FUNCTION IN THE SYSTEM        │               │
│              └─────────────────────────────────────────────-┘               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 4: Evolution Over Time

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   SYSTEM EVOLUTION: V1 → V2 → V3                            │
│                                                                             │
│  TEACH: How the system evolves from simple to production-grade              │
│                                                                             │
│  V1: STARTUP (1K hosts, 1M series)                                          │
│  ┌─────────────────────────────────────────────────────┐                    │
│  │  App → StatsD (UDP) → Single InfluxDB → Grafana     │                    │
│  │                                                     │                    │
│  │  ✓ Simple  ✓ Fast to set up  ✓ Low cost             │                    │
│  │  ✗ No redundancy  ✗ No cardinality control          │                    │
│  │  ✗ UDP drops  ✗ Single point of failure             │                    │
│  └─────────────────────────────────────────────────────┘                    │
│                        │                                                    │
│     BREAKS: OOM from cardinality, UDP loss, single TSDB saturated           │
│                        │                                                    │
│                        ▼                                                    │
│  V2: GROWTH (50K hosts, 100M series)                                        │
│  ┌─────────────────────────────────────────────────────┐                    │
│  │  App → Agent → Collector Fleet → Sharded TSDB       │                    │
│  │       (buffer)   (stateless)     (hash-partitioned) │                    │
│  │                                                     │                    │
│  │  + Buffering  + Horizontal scale  + Cardinality     │                    │
│  │  + Tiered retention  + Namespace isolation          │                    │
│  │  + Separate alert engine                            │                    │
│  │  ✗ Single region  ✗ Alert/query coupled             │                    │
│  │  ✗ Manual downsampling                              │                    │
│  └─────────────────────────────────────────────────────┘                    │
│                        │                                                    │
│     BREAKS: Regional, alert delays during overload, storage cost            │
│                        │                                                    │
│                        ▼                                                    │
│  V3: MATURE PLATFORM (500K hosts, 5B series)                                │
│  ┌─────────────────────────────────────────────────────┐                    │
│  │  Multi-region with global view                      │                    │
│  │  Isolated alert infrastructure                      │                    │
│  │  Streaming aggregation                              │                    │
│  │  Automated downsampling                             │                    │
│  │  Query cost protection                              │                    │
│  │  Self-monitoring with external dead-man's switch    │                    │
│  │  Object-store long-term retention                   │                    │
│  │  Zero-downtime upgrades                             │                    │
│  │                                                     │                    │
│  │  ✓ Scales to billions of series                     │                    │
│  │  ✓ Survives regional failures                       │                    │
│  │  ✓ Self-monitoring                                  │                    │
│  │  ✓ Cost-efficient ($0.002/series/month)             │                    │
│  └─────────────────────────────────────────────────────┘                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 5: Multi-Tenant Containment Boundaries

```
┌─────────────────────────────────────────────────────────────────────────────┐
│           MULTI-TENANT CONTAINMENT BOUNDARIES                               │
│                                                                             │
│  TEACH: How tenant isolation prevents one team's failure from               │
│         affecting another team's observability                              │
│                                                                             │
│  ┌───────────────────────────────────────────────────────┐                  │
│  │  TEAM A (API Platform)                                │                  │
│  │  Quota: 50M series, 5M samples/sec                    │                  │
│  │  ┌─────────────────────────────────────────────────┐  │                  │
│  │  │ Their metrics → Their namespace → Their quota   │  │                  │
│  │  │ Cardinality bomb? → Only THEIR metrics rejected │  │                  │
│  │  │ Query of death? → Only THEIR query killed       │  │                  │
│  │  │ Alert misconfigured? → Only THEIR alerts noisy  │  │                  │
│  │  └─────────────────────────────────────────────────┘  │                  │
│  └───────────────────────────────────────────────────────┘                  │
│                                                                             │
│  ┌───────────────────────────────────────────────────────┐                  │
│  │  TEAM B (Payment Processing)                          │                  │
│  │  Quota: 20M series, 2M samples/sec                    │                  │
│  │  ┌─────────────────────────────────────────────────┐  │                  │
│  │  │ Completely isolated from Team A's failures      │  │                  │
│  │  │ Even if Team A uses 100% of their quota,        │  │                  │
│  │  │ Team B's quota is RESERVED and UNAFFECTED       │  │                  │
│  │  └─────────────────────────────────────────────────┘  │                  │
│  └───────────────────────────────────────────────────────┘                  │
│                                                                             │
│  ╔═══════════════════════════════════════════════════════════╗              │
│  ║  ISOLATION ENFORCED AT:                                   ║              │
│  ║                                                           ║              │
│  ║  1. INGESTION: Per-namespace rate limits at collector     ║              │
│  ║     → Team A flooding doesn't slow Team B's ingestion     ║              │
│  ║                                                           ║              │
│  ║  2. CARDINALITY: Per-namespace limits at cardinality      ║              │
│  ║     enforcer → Team A's bad label doesn't affect Team B   ║              │
│  ║                                                           ║              │
│  ║  3. STORAGE: Per-namespace series quota in TSDB           ║              │
│  ║     → Team A can't consume Team B's storage               ║              │
│  ║                                                           ║              │
│  ║  4. QUERY:Per-namespace concurrency limits in query engine║              │
│  ║     → Team A's expensive queries don't starve Team B      ║              │
│  ║                                                           ║              │
│  ║  5. ALERTING: Per-namespace rule count limits             ║              │
│  ║     → Team A's 10,000 alert rules don't slow evaluation   ║              │
│  ╚═══════════════════════════════════════════════════════════╝              │
│                                                                             │
│  ┌───────────────────────────────────────────────────────┐                  │
│  │  SHARED RESOURCES (failure domain for ALL teams):     │                  │
│  │                                                       │                  │
│  │  • Collector fleet (stateless — scales independently) │                  │
│  │  • TSDB shards (hash partitioned — one team's data    │                  │
│  │    may share a shard, but quota enforcement prevents  │                  │
│  │    one team from overwhelming the shard)              │                  │
│  │  • Query engine (per-user limits protect shared pool) │                  │
│  │                                                       │                  │
│  │  RISK: A platform-level bug (not a tenant bug) can    │                  │
│  │  affect all teams. This is why platform deploys need  │                  │
│  │  the MOST conservative canary strategy.               │                  │
│  └───────────────────────────────────────────────────────┘                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 18: Brainstorming, Exercises & Redesigns

## "What If X Changes?" Questions

```
Q1: What if scrape interval must be 1 second instead of 15 seconds?
  Impact: 15× more samples/sec → 15× more storage → 15× more ingestion throughput
  Changes needed:
  - Streaming aggregation becomes mandatory (can't query raw at this volume)
  - Hot storage retention shrinks to 6 hours
  - Per-sample compression even more critical
  - Push model becomes necessary (pull at 1s interval too expensive for targets)

Q2: What if we need 5-year retention at full resolution?
  Impact: Storage cost increases 100×
  Changes needed:
  - Columnar storage format for cold data (Parquet, better compression)
  - Query engine must efficiently scan cold storage (predicate pushdown)
  - Probably not feasible for all metrics → Tier 1 only
  - Consider approximate query engines (sampling + estimation)

Q3: What if the number of active time series grows from 5B to 50B?
  Impact: 10× more TSDB shards, 10× more index memory, 10× more query fan-out
  Changes needed:
  - More aggressive pre-aggregation (reduce queryable series)
  - Hierarchical query routing (regional → cluster → global)
  - Index compression or on-disk index with SSD
  - Tighter cardinality enforcement

Q4: What if we need sub-100ms alert detection?
  Impact: Cannot use periodic evaluation (even 1s evaluation is 500ms avg latency)
  Changes needed:
  - Stream-processing alert evaluation (evaluate on ingestion, not polling)
  - Push-based ingestion (no scrape interval delay)
  - In-memory alert state with replication
  - Fundamentally different architecture (CEP engine rather than TSDB + query)

Q5: What if metrics must be end-to-end encrypted (zero trust)?
  Impact: TSDB cannot read values → Cannot compute aggregations server-side
  Changes needed:
  - Client-side aggregation only (or homomorphic encryption, impractical)
  - Fundamentally breaks the metrics model (server can't aggregate across sources)
  - Alternative: Encrypt at rest, strict access control at query layer
```

## Redesign Under New Constraints

```
CONSTRAINT REDESIGN 1: Budget is $0 (open source only, own hardware)

Changes:
  - Prometheus + Thanos for TSDB + long-term storage
  - MinIO for S3-compatible object storage (on-premise)
  - Grafana for dashboards
  - Alertmanager for alerting
  - Custom collector fleet (or VictoriaMetrics vminsert)
  
  Trade-offs:
  - Higher operational burden (no managed services)
  - Scaling ceiling based on hardware procurement timeline
  - But: Full control, no vendor lock-in, no per-series pricing

CONSTRAINT REDESIGN 2: Must handle 100B active time series

Changes:
  - Fundamental architecture change: Two-level TSDB
    Level 1: Streaming aggregation reduces raw series → 1B aggregated
    Level 2: Traditional TSDB stores 1B aggregated series
  - Raw data stored in append-only log (no index) for forensic queries
  - All dashboards use pre-aggregated data
  - Per-pod drill-down only for recent data (last 1 hour, fan-out to raw log)
  - Approximate query engine for ad-hoc (sampling-based)

CONSTRAINT REDESIGN 3: Metrics system must have 99.999% availability

Changes:
  - Multi-region active-active for ingestion (write to nearest region)
  - Synchronous replication within region (RF=3)
  - Cross-region async replication for reads
  - Alert engine runs in 3+ regions simultaneously (majority vote on alert state)
  - No single points of failure anywhere in the pipeline
  - Cost increase: ~3× compared to 99.99% design
  - Is it worth it? Only if the metrics system is THE ONLY way to detect outages
```

## Failure Injection Exercises

```
EXERCISE 1: TSDB Shard Disk Failure
  Inject: Kill disk I/O for one TSDB shard
  Expected behavior:
  - WAL writes fail → Shard stops accepting new data
  - Head block serves queries from memory (until data ages out)
  - Collectors buffer for this shard
  - Alert fires: "TSDB shard X disk failure"
  - Shard migrated to new node, WAL replayed from collectors' buffers
  
  Questions to answer:
  - How long until data loss? (Buffer duration)
  - How long until queries are affected? (Immediately for new data)
  - Is the failure detected? (Yes, by meta-monitoring)

EXERCISE 2: Collector Fleet Network Partition
  Inject: Block network between 50% of agents and all collectors
  Expected behavior:
  - Affected agents buffer locally (10 minutes)
  - Metric volume drops 50% from the monitoring system's perspective
  - Alerts based on absolute thresholds may fire incorrectly
    (50% traffic looks like 50% drop)
  - Alerts based on ratio/percentage unaffected
    (error rate still accurate for reporting agents)
  
  Questions to answer:
  - Which alerts are safe to trust? (Ratios, not absolutes)
  - How do you distinguish "real 50% traffic drop" from "50% agents partitioned"?
    (Check agent health metric: up{} / expected_targets)

EXERCISE 3: Query Engine Memory Exhaustion
  Inject: Submit 100 expensive queries simultaneously
  Expected behavior:
  - First queries execute, memory rises
  - Memory limit reached → Load shedding activates
  - New queries queued or rejected by priority
  - Alert queries continue (highest priority)
  - Offensive queries killed (timeout)
  
  Questions to answer:
  - Does the alert engine continue evaluating? (Must: yes)
  - How long until recovery? (Seconds, after offensive queries killed)
  - What's the user experience? (429 for ad-hoc, stale cache for dashboards)

EXERCISE 4: Cardinality Bomb During Deploy
  Inject: Deploy service that adds trace_id as metric label
  Expected behavior:
  - First minute: Cardinality grows rapidly (10K new series/second)
  - Cardinality enforcer detects limit breach → Starts rejecting
  - Alert: "Cardinality limit exceeded for metric X"
  - Operator blocks the label → Stop the bleeding
  - Rollback deploy → New series stop being created
  - TSDB compaction cleans up short-lived series
  
  Questions to answer:
  - How fast is detection? (Seconds, via HyperLogLog at collector)
  - What if the enforcer misses it? (TSDB OOM → Much worse outcome)
  - Can it be prevented entirely? (CI/CD check for cardinality)
```

## Trade-Off Debates

```
DEBATE 1: Push vs Pull for metric collection

  Push advocates:
  "Push works for short-lived processes, behind firewalls, and
  gives applications control over emission timing."
  
  Pull advocates:
  "Pull gives the collector control over scrape rate (natural backpressure),
  makes 'target down' detection trivial, and simplifies the application."
  
  Resolution: Hybrid. Pull for long-lived services, push for batch jobs
  and serverless. This is the pragmatic Staff answer—don't pick a side,
  pick the right tool for each context.

DEBATE 2: Histograms vs Summaries for latency measurement

  Histogram advocates:
  "Fixed buckets, mergeable across instances, predictable cardinality,
  can compute any percentile after the fact."
  
  Summary advocates:
  "Pre-computed percentiles are more accurate, no bucket boundary errors,
  client computes once rather than server computing on every query."
  
  Resolution: Histograms for almost everything. Summaries only when you
  need exact percentiles AND don't need to aggregate across instances.
  At scale, mergeability wins.

DEBATE 3: Separate metrics and logs systems vs unified observability platform

  Separate advocates:
  "Different data models, different query patterns, different scale 
  characteristics. Purpose-built systems excel; unified systems compromise."
  
  Unified advocates:
  "Correlation between metrics, logs, and traces is the killer feature.
  Separate systems require manual correlation. Context switching kills MTTR."
  
  Resolution: Separate systems with shared correlation keys (trace_id, 
  request_id). Each system optimized for its data model, but linked
  for cross-system navigation. "Federated, not monolithic."

DEBATE 4: Pre-aggregation vs at-query-time aggregation

  Pre-aggregation advocates:
  "Compute common aggregations once, query many times. 10–100× faster
  for dashboards and alerts."
  
  At-query advocates:
  "Maximum flexibility. No wasted computation on aggregations nobody queries.
  Storage is cheap; compute is the bottleneck."
  
  Resolution: Pre-aggregate what's known (alerts, common dashboards).
  Leave the rest for query time. Review quarterly: if a query is popular,
  promote it to pre-aggregation. This is the evolutionary approach.

DEBATE 5: Metric names vs structured labels for organization

  Names: http_api_get_users_requests_total
  Labels: http_requests_total{method="GET", endpoint="/users"}

  Names advocates:
  "Simple, grep-able, no cardinality concerns."
  
  Labels advocates:
  "Queryable dimensions, can aggregate across endpoints, slice and dice."
  
  Resolution: Labels are strictly superior for any metric that has dimensions.
  Names only for truly singleton metrics (e.g., process_start_time).
  The entire modern metrics ecosystem is built around labels.
```


## Additional Brainstorming Questions

```
Q6: What if the metrics platform must support 50 different client languages?
  Impact: Client library maintenance burden grows linearly
  Changes needed:
  - OpenTelemetry as universal instrumentation API (one spec, many implementations)
  - Protocol standardization (OTLP) so any client works with any backend
  - Auto-instrumentation where possible (bytecode injection, eBPF)
  - Staff insight: Standardize the PROTOCOL, not the library.
    Let language communities own their client libraries.

Q7: What if a regulator requires you to delete all metrics for a specific user?
  (GDPR right to erasure applied to metrics)
  Impact: Metrics typically don't contain user_id... but what if labels do?
  Changes needed:
  - PII scanning at ingestion (reject labels containing user identifiers)
  - If already stored: Metrics are immutable in TSDB blocks
    → Must rewrite blocks with offending data removed (extremely expensive)
  - Staff insight: Prevention > remediation. Block PII in labels at ingestion.
    This is a 5-minute CI/CD check vs a multi-week block rewrite.

Q8: What if the metrics system must support multi-tenancy across 
  different ORGANIZATIONS (not just teams within one org)?
  Impact: Tenant isolation must be cryptographic, not just logical
  Changes needed:
  - Per-tenant encryption keys (not shared key)
  - Per-tenant TSDB shards (no shared storage)
  - Network isolation (separate collector endpoints per tenant)
  - Audit logging for cross-tenant access attempts
  - This is 5× more expensive than single-org multi-tenancy

Q9: What if you need to support querying the UNION of metrics and logs?
  "Show me the error rate, AND the actual error log messages, in one view"
  Impact: Fundamentally different data models must be correlated
  Changes needed:
  - Shared correlation key (trace_id, request_id) across both systems
  - Federated query engine that can query TSDB and log store
  - Linked navigation: Click on metric spike → Show matching log entries
  - Staff insight: Don't try to store both in one system. Federate.
    The performance and cost characteristics are too different.

Q10: What if metric ingestion must survive a COMPLETE datacenter loss
  with ZERO data loss?
  Impact: Must synchronously replicate before acknowledging writes
  Changes needed:
  - Synchronous cross-DC replication for WAL (doubles write latency)
  - Or: Agent-side durable buffer (write to local disk + remote)
  - Cost: 3-5× for ingestion path
  - Staff assessment: Almost never worth it for metrics.
    Metrics during a DC-level event are useful but not critical.
    The 10-minute agent buffer covers the 99th percentile scenario.
    Accept data loss for the 1% scenario where the DC is actually gone.
```

## Additional Full Design Exercises

```
FULL DESIGN EXERCISE 1: SLO MONITORING SUBSYSTEM
────────────────────────────────────────────────────────
Requirement: Build an SLO monitoring layer on top of the metrics system.
Teams define SLOs: "99.9% of requests complete in < 500ms over 30 days."

Design considerations:
• Rolling window vs calendar window for SLO period
• Error budget calculation: How much budget remaining?
• Error budget burn rate alerting: "At current rate, budget exhausted in 4 hours"
• Multi-window burn rate: Fast burn (1h window) vs slow burn (6h window)
• Composite SLOs: "Service A AND Service B both meet SLO"
• SLO data must survive metrics system outages (separate storage?)

This exercise tests:
• Understanding of SLI/SLO semantics at a mathematical level
• Building RELIABLE computation on top of eventually-consistent data
• Trade-offs between SLO precision and system complexity

FULL DESIGN EXERCISE 2: METRICS-DRIVEN AUTO-REMEDIATION
────────────────────────────────────────────────────────
Requirement: When specific metric conditions are met, automatically
execute remediation (e.g., scale up, restart, drain traffic).

Design considerations:
• How to prevent remediation loops (fix → problem recurs → fix → ...)
• Rate limiting remediation actions (max 3 restarts per hour)
• Approval gates: Critical actions require human confirmation
• Audit trail: Every automated action logged with metric context
• Rollback: If remediation makes things worse, auto-rollback
• Testing: How to test remediation without breaking production

This exercise tests:
• Safety boundaries around automated actions
• Understanding that automated remediation CAN BE the outage
• Rate limiting and circuit breaking for actions (not just data)

FULL DESIGN EXERCISE 3: METRICS PLATFORM MIGRATION
────────────────────────────────────────────────────────
Requirement: Migrate from a Prometheus federation to the
horizontally-sharded TSDB architecture described in this chapter.
Without losing data. Without dashboards going down. With 500 teams.

Design considerations:
• Dual-write period: Both systems receive all data
• Query fan-out: Queries check both old and new, merge results
• Dashboard migration: 10,000 dashboards with PromQL queries
  → Must work against new TSDB (compatible query language?)
• Alert rule migration: 500,000 rules, cannot have a gap in evaluation
• Cutover strategy: Per-team? Per-region? Big-bang?
• Rollback plan: If new system has issues, revert to old

This is a HARD L6 exercise that tests:
• Migration planning (the hardest problem in platform engineering)
• Risk management under uncertainty
• Organizational coordination across 500 teams
• The ability to design a system AND the migration path to it

FULL DESIGN EXERCISE 4: OBSERVABILITY FOR SERVERLESS
────────────────────────────────────────────────────────
Requirement: Extend the metrics system to support serverless functions
(AWS Lambda-style) that exist for 100ms–15min.

Design considerations:
• Traditional scraping can't work (function gone before scrape)
• Push model required: Function pushes metrics before termination
• Cold start metrics: Function init time is a key metric
• Concurrency: 100,000 function invocations/second, each emitting metrics
• Cardinality: function_name × version × region × error_type
  Could explode quickly with many functions
• Cost: Functions run millions of times; storing per-invocation metrics
  is prohibitively expensive → Must aggregate before storage

CONSTRAINT REDESIGN 4: Zero External Dependencies
────────────────────────────────────────────────────────
Requirement: The metrics system cannot depend on any cloud service
(no S3, no managed Kubernetes, no cloud LB). Bare metal only.

Changes:
  - MinIO for object storage (self-hosted)
  - HAProxy for load balancing
  - CoreDNS for service discovery
  - Local NVMe for TSDB hot storage
  - Ceph or similar for distributed warm storage
  
  Trade-offs:
  - Operational burden increases 5×
  - Hardware procurement adds weeks to scaling
  - But: Zero vendor dependency, full control
  - When it makes sense: Financial institutions, government, air-gapped environments

CONSTRAINT REDESIGN 5: The Metrics System Has a $50K/year Budget
────────────────────────────────────────────────────────
(10,000 hosts, 20M active series)

  - Prometheus with aggressive federation (no commercial TSDB)
  - Thanos for long-term storage on cheap object store ($5/TB/month)
  - 3 dedicated servers for TSDB ($1,500/month)
  - 1 server for query/alert engine ($500/month)
  - Object storage for warm/cold ($200/month)
  - Total: ~$26K/year (under budget)
  
  What you sacrifice:
  - No multi-region (single cluster only)
  - No streaming aggregation (query-time only)
  - Manual cardinality management (no automated enforcement)
  - Limited retention (30 days hot, 6 months warm)
  
  This is the RIGHT design for a company with 10K hosts.
  Over-engineering to the V3 architecture would waste $200K+/year.
```

## Additional Trade-Off Debates

```
DEBATE 6: Fixed histogram buckets vs native histograms vs DDSketch

  Fixed buckets: "Simple, predictable, mergeable. Good enough accuracy."
  Native histograms: "Adaptive, no bucket selection problem, higher accuracy."
  DDSketch: "Mathematically guaranteed relative error, but complex and
  not widely supported in TSDB ecosystems."
  
  Resolution: Fixed histograms for now (ecosystem maturity), with a
  migration path to native histograms as TSDB support matures.
  DDSketch for use cases requiring guaranteed relative error (SLO compliance).

DEBATE 7: Central platform team vs embedded SREs for metrics

  Central team: "Efficiency, consistency, deep platform expertise."
  Embedded SREs: "Context-aware, faster response, better customer empathy."
  
  Resolution: Central platform team for infrastructure (TSDB, collectors,
  query engine) + embedded advocates per business unit for onboarding,
  dashboard design, and alert tuning. The platform is centrally owned;
  the usage is locally owned.

DEBATE 8: Real-time streaming alerts vs periodic batch evaluation

  Streaming: "Sub-second alert latency. Evaluate as data arrives."
  Batch: "Simpler, cheaper, 15-second granularity is sufficient."
  
  Resolution: Batch for 99% of alerts (15s evaluation cycle is fine).
  Streaming only for the 1% that truly need sub-second detection
  (e.g., "payment processing completely stopped"). The cost of
  streaming everything is 10× for a benefit that matters rarely.
```

---

# Part 19: Master Review Check & L6 Dimension Table

## Master Review Check (11 Items)

```
Before considering this chapter complete for L6 readiness, verify:

[✓] 1. Judgment: Trade-offs documented (accuracy vs latency, cost vs retention, cardinality vs flexibility)
[✓] 2. Failure/blast-radius: Failure modes enumerated with propagation, recovery, Real Incident table
[✓] 3. Scale/time: Concrete numbers (5B series, 200M samples/sec), bottlenecks, scaling limits
[✓] 4. Cost: Drivers, scaling analysis, cost-aware redesign, chargeback, over-engineering traps
[✓] 5. Real-world-ops: Runbooks, canary deployment, meta-monitoring, ownership
[✓] 6. Memorability: Staff Law, one-liners table, mental models, Quick Visual
[✓] 7. Data/consistency: Eventual consistency, counter resets, cross-tier stitching
[✓] 8. Security/compliance: Metric abuse, query abuse, PII in labels, access control
[✓] 9. Observability: Meta-observability, external heartbeat, self-monitoring
[✓] 10. Interview calibration: Probes, Staff signals, common L5 mistakes, phrases, leadership explanation
[✓] 11. Exercises & brainstorming: "What if" questions, redesigns, failure injection, full design exercises
```

## L6 Dimension Coverage Table (A–J)

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                    L6 DIMENSION COVERAGE (Metrics / Observability System)                    │
├───────┬─────────────────────────────┬─────────────────────────────────────────────────────┤
│ Dim   │ Dimension                    │ Where Covered                                        │
├───────┼─────────────────────────────┼─────────────────────────────────────────────────────┤
│ A     │ Judgment                    │ L5 vs L6 table; accuracy vs query speed; cardinality│
│       │                             │ vs flexibility; completeness vs ingestion reliability│
├───────┼─────────────────────────────┼─────────────────────────────────────────────────────┤
│ B     │ Failure/blast-radius        │ Part 9 (TSDB, collector, cardinality, query overload)│
│       │                             │ Real Incident table; retry storms; cascading deploy    │
├───────┼─────────────────────────────┼─────────────────────────────────────────────────────┤
│ C     │ Scale/time                  │ Part 4 (5B series, 200M samples/sec); Part 9 timeline│
│       │                             │ Burst behavior; what breaks first                      │
├───────┼─────────────────────────────┼─────────────────────────────────────────────────────┤
│ D     │ Cost                        │ Part 11 (drivers, scaling, chargeback); cost-aware    │
│       │                             │ redesign; tiered retention; over-engineering          │
├───────┼─────────────────────────────┼─────────────────────────────────────────────────────┤
│ E     │ Real-world-ops              │ Runbooks (Part 9); canary (Part 14); meta-monitoring │
│       │                             │ On-call burden; governance for 500 teams               │
├───────┼─────────────────────────────┼─────────────────────────────────────────────────────┤
│ F     │ Memorability                │ Staff Law; Staff One-Liners table; Quick Visual;     │
│       │                             │ "Metrics detect; logs diagnose"                       │
├───────┼─────────────────────────────┼─────────────────────────────────────────────────────┤
│ G     │ Data/consistency            │ Part 3, Part 8; eventual consistency; counter resets; │
│       │                             │ cross-tier query stitching; late-arriving data        │
├───────┼─────────────────────────────┼─────────────────────────────────────────────────────┤
│ H     │ Security/compliance         │ Part 13; metric abuse; query abuse; PII in labels;    │
│       │                             │ GDPR deletion; access control                         │
├───────┼─────────────────────────────┼─────────────────────────────────────────────────────┤
│ I     │ Observability               │ Meta-observability; external heartbeat; self-monitor;│
│       │                             │ (Metrics system observing itself)                     │
├───────┼─────────────────────────────┼─────────────────────────────────────────────────────┤
│ J     │ Cross-team                  │ Cost attribution; per-team quotas; 500-team governance│
│       │                             │ Ownership model; showback vs chargeback               │
└───────┴─────────────────────────────┴─────────────────────────────────────────────────────┘
```

---

# Summary

Metrics and observability systems are the foundation upon which all operational excellence is built. The core challenge isn't collecting numbers—it's doing it at massive scale, with ruthless cost efficiency, while guaranteeing the system remains available during the exact moments when everything else is failing.

**Key Staff-Level Insights:**

1. **Cardinality is the existential threat.** Every other scaling concern is solvable with more hardware. Cardinality explosion kills the system regardless of how much hardware you throw at it. Enforce limits at every layer.

2. **The alert path is sacred.** Design the alerting infrastructure as if it's the last thing standing during an outage—because it should be. Isolate it from everything else.

3. **Not all metrics are equal.** Classify metrics into tiers. Apply differentiated retention, resolution, replication, and query priority. This is how you get 10× cost efficiency without sacrificing reliability where it matters.

4. **Design for the worst day.** The observability system experiences peak load during incidents—exactly when it's most critical. Over-provision ingestion and query paths. Buffer aggressively. Shed load gracefully.

5. **Compression makes or breaks feasibility.** Without Gorilla-style compression (12× reduction), storing 200M samples/second is economically impossible. Understand why time-series-specific compression exists.

6. **Downsampling is the long-term cost strategy.** Raw data for hours, minute-aggregates for weeks, hour-aggregates for months. This saves >99% of long-term storage cost with minimal information loss.

**The Staff Engineer Difference:**

An L5 might design a working metrics collection system. An L6 designs a metrics platform that enforces cardinality boundaries, isolates the alert path from the query path, tiers storage for cost efficiency, degrades gracefully under load, monitors itself with external systems, and evolves without downtime. The difference is understanding that the observability system isn't just another service—it's the service that makes every other service operable.

---

### Topic Coverage in Exercises:

| Topic | Questions/Exercises |
|-------|---------------------|
| **Cardinality & Labels** | Q1, Q3, Exercise 4, Debate 5 |
| **Alerting & Reliability** | Q4, Exercise 3, Debate 3 |
| **Storage & Retention** | Q2, Redesign 1, Debate 4 |
| **Scale Stress** | Q3, Redesign 2, Exercise 1 |
| **Cost Optimization** | Redesign 1, Debate 4 |
| **Multi-Region** | Q5, Redesign 3 |
| **Collection Model** | Q1, Debate 1, Exercise 2 |
| **Failure & Resilience** | Exercise 1-4 |
| **Full Trade-Off Debates** | Debates 1-5 |

### Remaining Considerations (Not Gaps):

1. **Distributed tracing** is explicitly out of scope (separate system, different data model)
2. **Log aggregation** is out of scope (referenced where it intersects with metrics)
3. **APM / code profiling** is out of scope (different granularity and purpose)
4. **Synthetic monitoring** is out of scope (separate probing infrastructure)

These are intentional scope boundaries, not gaps. Each could be a separate chapter.

### Pseudo-Code Convention:

All code examples in this chapter use language-agnostic pseudo-code:
- `FUNCTION` keyword for function definitions
- `IF/ELSE/FOR/WHILE` for control flow
- Descriptive variable names in snake_case
- No language-specific syntax (no `def`, `public void`, `func`, etc.)
- Comments explain intent, not syntax

### How to Use This Chapter in Interview:

1. Start with the "L5 vs L6 Decisions" table to frame your approach
2. Lead with cardinality as the primary design constraint—this signals Staff-level awareness
3. Discuss tiered retention and cost before the interviewer asks—this shows proactive thinking
4. Use the failure timeline to demonstrate operational maturity
5. Reference the alert isolation principle when discussing reliability
6. Practice the brainstorming questions to anticipate follow-ups
7. Study the common L5 mistakes section to avoid interview pitfalls

---