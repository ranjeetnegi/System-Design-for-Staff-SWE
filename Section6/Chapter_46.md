# Chapter 46. Metrics / Observability System

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
│   RIGHT Framing: "Ingest millions of time-series at sub-second latency,   │
│                   store them cost-efficiently for years, and enable        │
│                   millisecond queries during live production incidents"    │
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
│                  THE THREE PILLARS OF OBSERVABILITY                          │
│                                                                             │
│   ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐         │
│   │     METRICS      │  │      LOGS        │  │     TRACES       │         │
│   │                  │  │                  │  │                  │         │
│   │ What:            │  │ What:            │  │ What:            │         │
│   │ Numeric values   │  │ Discrete events  │  │ Request paths    │         │
│   │ over time        │  │ with context     │  │ across services  │         │
│   │                  │  │                  │  │                  │         │
│   │ When:            │  │ When:            │  │ When:            │         │
│   │ "Is latency up?" │  │ "Why did this    │  │ "Where is the    │         │
│   │ "How many 5xx?"  │  │  request fail?"  │  │  bottleneck?"    │         │
│   │                  │  │                  │  │                  │         │
│   │ Volume:          │  │ Volume:          │  │ Volume:          │         │
│   │ Medium           │  │ Very high        │  │ Low (sampled)    │         │
│   │ (aggregated)     │  │ (per-event)      │  │ (per-request)    │         │
│   │                  │  │                  │  │                  │         │
│   │ Cost:            │  │ Cost:            │  │ Cost:            │         │
│   │ Low per series   │  │ Very high at     │  │ Medium           │         │
│   │                  │  │ scale            │  │ (sampling helps) │         │
│   └──────────────────┘  └──────────────────┘  └──────────────────┘         │
│                                                                             │
│   THIS CHAPTER FOCUSES ON METRICS                                           │
│   (Logs and traces referenced where they intersect)                         │
│                                                                             │
│   Staff insight: Metrics DETECT problems. Logs and traces DIAGNOSE them.   │
│   Design the metrics path for speed and reliability. Design the logs/trace │
│   path for depth and context.                                              │
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
│   • Heart rate below 40 or above 150? → Page the doctor                    │
│   • Blood oxygen below 90%? → Critical alarm                               │
│   ↓                                                                         │
│   MEDICAL RECORDS (long-term storage)                                       │
│   • Trends over days/months for diagnosis                                   │
│   • Aggregate statistics for research                                       │
│                                                                             │
│   COMPLICATIONS AT SCALE:                                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  What if you have 10 million patients? (10M services/containers)   │   │
│   │  → Can't have a nurse per patient; need automated monitoring       │   │
│   │                                                                     │   │
│   │  What if each patient has 500 vital signs? (500 metrics per host)  │   │
│   │  → Can't display all at once; need smart aggregation and ranking   │   │
│   │                                                                     │   │
│   │  What if the monitoring system itself gets sick?                    │   │
│   │  → Must be more reliable than the systems it monitors              │   │
│   │                                                                     │   │
│   │  What if historical records fill the warehouse?                     │   │
│   │  → Need to summarize: hourly stats not per-second after 30 days    │   │
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
│              OBSERVABILITY SYSTEM FAILURE MODES                              │
│                                                                             │
│   FAILURE MODE 1: FLYING BLIND                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  No metrics → No alerts → No awareness → User-reported outages     │   │
│   │  Detection shifts from seconds to hours                            │   │
│   │  MTTR (Mean Time To Recovery) increases 10-50×                     │   │
│   │                                                                     │   │
│   │  Real example: A silent data corruption bug ran for 3 weeks        │   │
│   │  because there were no data integrity metrics.                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   FAILURE MODE 2: ALERT FATIGUE                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Bad metrics → Too many false alerts → On-call ignores alerts      │   │
│   │  → Real incident missed because it looked like another false alarm │   │
│   │                                                                     │   │
│   │  This is WORSE than no alerts. False confidence kills.             │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   FAILURE MODE 3: OBSERVABILITY SYSTEM ITSELF OVERLOADED                    │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  During traffic spike, metrics pipeline also overloads             │   │
│   │  → Metrics delayed or lost during the exact moment you need them   │   │
│   │  → Dashboards show stale data → Wrong diagnosis → Wrong fix        │   │
│   │                                                                     │   │
│   │  Staff insight: The observability system must be provisioned for   │   │
│   │  the WORST day, not the average day.                               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   FAILURE MODE 4: CARDINALITY EXPLOSION                                     │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Developer adds user_id as a metric label                          │   │
│   │  → 100M users × 50 metrics = 5 BILLION time series                 │   │
│   │  → TSDB runs out of memory → All metrics unavailable               │   │
│   │  → One bad label takes down entire observability stack              │   │
│   │                                                                     │   │
│   │  This is the #1 operational incident in metrics systems.           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   FAILURE MODE 5: METRIC MISINTERPRETATION                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Average latency looks fine at 50ms → But P99 is 12 seconds        │   │
│   │  → 1% of users having terrible experience                          │   │
│   │  → Dashboard shows green → No investigation                        │   │
│   │                                                                     │   │
│   │  Staff insight: Averages lie. Always use percentiles.              │   │
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
│   P50: < 1μs  │  P99: < 10μs  │  Budget: ZERO blocking to application     │
│   WHY: A metric call inside a request path that adds 1ms per call          │
│   at 100 calls/request adds 100ms of latency. Unacceptable.               │
│                                                                             │
│   INGESTION (end-to-end, emission to queryable):                            │
│   P50: < 10s  │  P99: < 30s                                                │
│   WHY: During incidents, 30s staleness is tolerable. Beyond 60s,           │
│   dashboards become misleading—you're debugging with stale data.           │
│                                                                             │
│   DASHBOARD QUERY (standard time range):                                    │
│   P50: < 500ms  │  P99: < 3s                                               │
│   WHY: On-call engineer refreshing dashboard during incident.              │
│   More than 3 seconds → they'll open another tab and lose context.         │
│                                                                             │
│   ALERT EVALUATION (rule check cycle):                                      │
│   P50: < 15s  │  P99: < 60s                                                │
│   WHY: Alerts should fire within 1–2 minutes of condition onset.           │
│   60s evaluation + 60s "for" duration = ~2 min detection latency.          │
│                                                                             │
│   AD-HOC QUERY (wide time range, many series):                              │
│   P50: < 5s  │  P99: < 30s                                                 │
│   WHY: Exploratory queries during post-mortem. Users tolerate waiting      │
│   but will abort and simplify query if > 30s.                              │
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
│  ┌─────────┐  ┌─────────┐  ┌─────────┐                                    │
│  │ Service │  │ Service │  │ Service │  ... (millions)                     │
│  │   A     │  │   B     │  │   C     │                                    │
│  └────┬────┘  └────┬────┘  └────┬────┘                                    │
│       │            │            │                                           │
│       ▼            ▼            ▼                                           │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐                                    │
│  │ Agent / │  │ Agent / │  │ Agent / │  (per-host or sidecar)             │
│  │ Sidecar │  │ Sidecar │  │ Sidecar │                                    │
│  └────┬────┘  └────┬────┘  └────┬────┘                                    │
│       │            │            │                                           │
│       └────────────┼────────────┘                                           │
│                    ▼                                                        │
│  ┌──────────────────────────────────────────────────┐                      │
│  │           INGESTION LAYER                         │                      │
│  │  ┌──────────────────────────────────────────────┐│                      │
│  │  │  Collector Fleet (stateless, horizontally    ││                      │
│  │  │  scalable, validates, routes, pre-aggregates)││                      │
│  │  └──────────────────────────────────────────────┘│                      │
│  └─────────────────────┬────────────────────────────┘                      │
│                        │                                                    │
│            ┌───────────┼───────────────┐                                    │
│            ▼           ▼               ▼                                    │
│  ┌─────────────┐ ┌──────────┐ ┌────────────────┐                          │
│  │ Write-Ahead │ │ Streaming│ │ Cardinality    │                          │
│  │ Log / Queue │ │ Aggreg.  │ │ Enforcer       │                          │
│  │ (buffer)    │ │ Engine   │ │ (reject/drop)  │                          │
│  └──────┬──────┘ └─────┬────┘ └────────────────┘                          │
│         │              │                                                    │
│         ▼              ▼                                                    │
│  ┌──────────────────────────────────────────────────┐                      │
│  │           STORAGE LAYER                           │                      │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │                      │
│  │  │  HOT     │  │  WARM    │  │   COLD       │   │                      │
│  │  │  (TSDB)  │  │  (Object │  │   (Object    │   │                      │
│  │  │  In-mem  │  │   Store  │  │    Store,    │   │                      │
│  │  │  + SSD   │  │   1min   │  │    1hr agg)  │   │                      │
│  │  │  Raw 48h │  │   agg)   │  │              │   │                      │
│  │  └──────────┘  └──────────┘  └──────────────┘   │                      │
│  └──────────────────────┬───────────────────────────┘                      │
│                         │                                                   │
│  ┌──────────────────────┼───────────────────────────┐                      │
│  │           QUERY LAYER                             │                      │
│  │  ┌──────────────────────────────────────────────┐│                      │
│  │  │  Query Engine (fan-out to storage tiers,     ││                      │
│  │  │  merge results, compute aggregations)         ││                      │
│  │  └──────────────────────────────────────────────┘│                      │
│  └──────────┬──────────────────┬────────────────────┘                      │
│             │                  │                                             │
│    ┌────────▼────────┐  ┌─────▼──────────┐                                 │
│    │   DASHBOARDS    │  │  ALERT ENGINE  │                                 │
│    │   (Grafana,     │  │  (Evaluates    │                                 │
│    │    custom UI)   │  │   rules,       │                                 │
│    │                 │  │   routes        │                                 │
│    │                 │  │   notifications)│                                 │
│    └─────────────────┘  └────────────────┘                                 │
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
│ Tier   │ Resolution │ Retention │ Storage         │ Cost/GB/month    │
├────────────────────────────────────────────────────────────────────────┤
│ Hot    │ 15 seconds │ 48 hours  │ Local SSD/NVMe  │ $$$$ (highest)   │
│ Warm   │ 1 minute   │ 30 days   │ Object store    │ $$               │
│ Cold   │ 1 hour     │ 1 year    │ Object store IA │ $                │
│ Archive│ 1 day      │ 5 years   │ Glacier/archive │ ¢ (cheapest)     │
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
│                  COST BREAKDOWN (TYPICAL)                                    │
│                                                                             │
│   40% │ STORAGE                                                             │
│       │ ├── Hot (SSD): High $/GB, fast, 48h retention → 15% of total       │
│       │ ├── Warm (Object store): Low $/GB, 30-day retention → 20%          │
│       │ └── Cold (Archive): Very low $/GB, 1+ year → 5%                    │
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
  │  ┌────────┐  ┌──────────┐  ┌──────────┐  ┌────────────────────┐ │
  │  │ Agents │→│Collectors │→│  TSDB     │→│ Object Store (Warm)│ │
  │  └────────┘  └──────────┘  │ (Sharded) │  └────────────────────┘ │
  │                            └─────┬─────┘                         │
  │                                  │        ┌─────────────────┐    │
  │              ┌───────────────────┤        │ Alert Engine    │    │
  │              │                   │        │ (Isolated)      │    │
  │              ▼                   ▼        └─────────────────┘    │
  │  ┌──────────────┐      ┌──────────────┐                         │
  │  │ Query Engine │      │ Streaming    │                         │
  │  │ (Regional)   │      │ Aggregation  │                         │
  │  └──────┬───────┘      └──────────────┘                         │
  │         │                                                        │
  └─────────┼────────────────────────────────────────────────────────┘
            │ (Aggregated metrics)
            ▼
  ┌──────────────────────────┐
  │  GLOBAL VIEW             │
  │  ┌──────────────────┐   │
  │  │ Global TSDB      │   │ ← Receives aggregated from all regions
  │  │ (Aggregated only) │   │
  │  └────────┬─────────┘   │
  │           │              │
  │  ┌────────▼─────────┐   │
  │  │ Global Query Eng │   │
  │  └────────┬─────────┘   │
  │           │              │
  │  ┌────────▼─────────┐   │
  │  │ Global Alerts    │   │
  │  │ Global Dashboards│   │
  │  └──────────────────┘   │
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

---

# Part 17: Diagrams

## Diagram 1: Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   METRICS SYSTEM: COMPONENT INTERACTION                      │
│                                                                             │
│  TEACH: How data flows from application to dashboard                        │
│                                                                             │
│  APPLICATION CODE                                                           │
│  ┌─────────────────────────┐                                               │
│  │ counter.increment()     │ ← O(1), non-blocking, < 1μs                  │
│  │ histogram.observe(val)  │                                               │
│  └──────────┬──────────────┘                                               │
│             │ (batched locally)                                              │
│             ▼                                                               │
│  AGENT (per-host)                                                           │
│  ┌─────────────────────────┐                                               │
│  │ Buffer → Batch → Ship   │ ← 10-15s flush interval                      │
│  │ Pre-aggregate            │                                               │
│  └──────────┬──────────────┘                                               │
│             │ (compressed batches)                                           │
│             ▼                                                               │
│  COLLECTOR FLEET (stateless)                                                │
│  ┌─────────────────────────────────────────────────────────┐               │
│  │ Validate → Cardinality Check → Route to Shard           │               │
│  └──────────┬──────────────────────┬───────────────────────┘               │
│             │                      │                                        │
│             ▼                      ▼                                        │
│  TSDB SHARD (hot)           STREAMING AGGREGATION                          │
│  ┌───────────────────┐     ┌────────────────────────┐                      │
│  │ WAL → Head → Block │     │ Pre-compute common     │                      │
│  │ Index (in-memory)  │     │ aggregations            │                      │
│  └─────────┬─────────┘     └────────────┬───────────┘                      │
│            │                            │                                   │
│            ├────────────────────────────┘                                   │
│            ▼                                                                │
│  QUERY ENGINE                                                               │
│  ┌─────────────────────────────────────────────────────────┐               │
│  │ Parse → Plan → Fetch → Compute → Return                 │               │
│  │ (with caching, cost limits, priority queuing)            │               │
│  └──────────┬──────────────────────┬───────────────────────┘               │
│             │                      │                                        │
│             ▼                      ▼                                        │
│  DASHBOARDS (Grafana)      ALERT ENGINE (isolated)                         │
│  ┌───────────────────┐     ┌────────────────────────┐                      │
│  │ Visualize metrics  │     │ Evaluate rules → Notify │                      │
│  │ for humans         │     │ (PagerDuty, Slack, etc) │                      │
│  └───────────────────┘     └────────────────────────┘                      │
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
│  T+0ms:     counter.increment({service:"api", status:"200"})               │
│             │                                                               │
│             ▼ Atomic add, no lock                                           │
│  T+0.001ms: In-memory counter = 42,847                                     │
│             │                                                               │
│             │ (Agent scrapes every 15 seconds)                              │
│             ▼                                                               │
│  T+15s:     Agent collects: http_requests_total{...} = 42847 @T=1705312200│
│             │                                                               │
│             ▼ Batch with ~5000 other samples, compress with Snappy          │
│  T+15.1s:   Agent ships batch to collector (500KB compressed)              │
│             │                                                               │
│             ▼ Collector validates + cardinality check (< 1ms per sample)   │
│  T+15.2s:   Collector routes to TSDB shard (hash of series fingerprint)    │
│             │                                                               │
│             ▼ TSDB writes to Write-Ahead Log                               │
│  T+15.3s:   WAL entry: (series_id=7A3F2B1C, ts=1705312200, val=42847)    │
│             │                                                               │
│             ▼ TSDB updates in-memory head block                            │
│  T+15.4s:   Head block chunk appended (Gorilla-compressed)                 │
│             │                                                               │
│             ╔════════════════════════════════════════════╗                  │
│             ║  SAMPLE IS NOW QUERYABLE                   ║                  │
│             ║  Total latency: ~15 seconds (dominated by  ║                  │
│             ║  scrape interval, not processing time)      ║                  │
│             ╚════════════════════════════════════════════╝                  │
│                                                                             │
│  LATER (every 2 hours):                                                     │
│             Head block full → Flush to immutable on-disk block             │
│                                                                             │
│  LATER (every 6 hours):                                                     │
│             Compaction merges small blocks into larger blocks               │
│                                                                             │
│  LATER (every 48 hours):                                                    │
│             Downsampling: Raw data → 1-minute roll-ups → Warm storage      │
│                                                                             │
│  LATER (every 30 days):                                                     │
│             1-minute roll-ups → 1-hour roll-ups → Cold storage             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 3: Failure Propagation

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   FAILURE PROPAGATION MAP                                    │
│                                                                             │
│  TEACH: How a single component failure propagates (or doesn't)              │
│                                                                             │
│  ┌──────────────┐                                                          │
│  │  TSDB SHARD  │─── FAILS ───┐                                           │
│  │  CRASHES     │             │                                            │
│  └──────────────┘             │                                            │
│                               ▼                                             │
│                    ┌─────────────────────────────┐                          │
│                    │ DIRECT IMPACT                │                          │
│                    │ • 1/N of series unavailable  │                          │
│                    │ • Writes queue in collectors │                          │
│                    │ • Reads return partial data  │                          │
│                    └──────────┬──────────────────┘                          │
│                               │                                             │
│              ┌────────────────┼────────────────────┐                       │
│              ▼                ▼                     ▼                       │
│  ┌──────────────────┐ ┌─────────────────┐ ┌──────────────────┐            │
│  │ COLLECTOR IMPACT  │ │ QUERY IMPACT    │ │ ALERT IMPACT     │            │
│  │ • Buffers fill    │ │ • Dashboards    │ │ • Rules touching │            │
│  │ • After 10min:    │ │   show gaps     │ │   lost series    │            │
│  │   drops samples   │ │ • Users see     │ │   show "no data" │            │
│  │   for that shard  │ │   partial data  │ │ • Meta-alert     │            │
│  │                   │ │                 │ │   fires           │            │
│  └──────────────────┘ └─────────────────┘ └──────────────────┘            │
│                                                                             │
│  ╔═══════════════════════════════════════════════════════════════════╗      │
│  ║  ISOLATION BOUNDARIES (what does NOT propagate):                   ║      │
│  ║                                                                    ║      │
│  ║  ✓ Other TSDB shards: Unaffected (independent)                    ║      │
│  ║  ✓ Application performance: Unaffected (agents buffer, non-block) ║      │
│  ║  ✓ Alert engine for other shards: Unaffected (isolated)           ║      │
│  ║  ✓ Dashboard for other services: Unaffected (different shards)    ║      │
│  ╚═══════════════════════════════════════════════════════════════════╝      │
│                                                                             │
│  CONTRAST: CARDINALITY EXPLOSION (worst-case failure)                       │
│                                                                             │
│  ┌──────────────┐                                                          │
│  │  BAD LABEL   │─── EXPLODES ──┐                                         │
│  │  DEPLOYED    │               │                                          │
│  └──────────────┘               │                                          │
│                                 ▼                                           │
│              ┌─────────────────────────────────────────────┐               │
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
│              │ MOST IMPORTANT FUNCTION IN THE SYSTEM         │               │
│              └─────────────────────────────────────────────┘               │
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
│  V1: STARTUP (1K hosts, 1M series)                                         │
│  ┌─────────────────────────────────────────────────────┐                   │
│  │  App → StatsD (UDP) → Single InfluxDB → Grafana    │                   │
│  │                                                     │                   │
│  │  ✓ Simple  ✓ Fast to set up  ✓ Low cost            │                   │
│  │  ✗ No redundancy  ✗ No cardinality control          │                   │
│  │  ✗ UDP drops  ✗ Single point of failure             │                   │
│  └─────────────────────────────────────────────────────┘                   │
│                        │                                                    │
│     BREAKS: OOM from cardinality, UDP loss, single TSDB saturated          │
│                        │                                                    │
│                        ▼                                                    │
│  V2: GROWTH (50K hosts, 100M series)                                       │
│  ┌─────────────────────────────────────────────────────┐                   │
│  │  App → Agent → Collector Fleet → Sharded TSDB       │                   │
│  │       (buffer)   (stateless)     (hash-partitioned) │                   │
│  │                                                     │                   │
│  │  + Buffering  + Horizontal scale  + Cardinality     │                   │
│  │  + Tiered retention  + Namespace isolation           │                   │
│  │  + Separate alert engine                            │                   │
│  │  ✗ Single region  ✗ Alert/query coupled             │                   │
│  │  ✗ Manual downsampling                              │                   │
│  └─────────────────────────────────────────────────────┘                   │
│                        │                                                    │
│     BREAKS: Regional, alert delays during overload, storage cost           │
│                        │                                                    │
│                        ▼                                                    │
│  V3: MATURE PLATFORM (500K hosts, 5B series)                               │
│  ┌─────────────────────────────────────────────────────┐                   │
│  │  Multi-region with global view                      │                   │
│  │  Isolated alert infrastructure                      │                   │
│  │  Streaming aggregation                              │                   │
│  │  Automated downsampling                             │                   │
│  │  Query cost protection                              │                   │
│  │  Self-monitoring with external dead-man's switch    │                   │
│  │  Object-store long-term retention                   │                   │
│  │  Zero-downtime upgrades                             │                   │
│  │                                                     │                   │
│  │  ✓ Scales to billions of series                     │                   │
│  │  ✓ Survives regional failures                       │                   │
│  │  ✓ Self-monitoring                                  │                   │
│  │  ✓ Cost-efficient ($0.002/series/month)             │                   │
│  └─────────────────────────────────────────────────────┘                   │
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
