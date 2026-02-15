# Chapter 61. Log Aggregation & Query System

---

# Introduction

A log aggregation and query system collects every log line emitted by every service in a distributed infrastructure, stores them durably, and makes them searchable within seconds. I've built and operated log systems that ingested 20TB of compressed logs per day from 500,000 hosts across 6 regions, and I'll be direct: the ingestion pipeline is straightforward engineering — any competent team can build a collector that ships logs to a central store. The hard part is the query engine that lets an on-call engineer, at 3 AM during a SEV-1, type a query like `service=payments AND level=ERROR AND trace_id=abc123` and get results back from 20TB of data in under 5 seconds; the storage engine that compresses and indexes petabytes of semi-structured text without bankrupting the company; the retention system that enforces "7 days hot, 30 days warm, 365 days cold" without losing a single log line that's needed for a post-mortem or compliance audit; and the tail pipeline that lets a developer run `log tail --service=checkout --level=ERROR` and see live logs from 200 instances in real-time with sub-second latency.

This chapter covers the design of a Log Aggregation & Query System at Staff Engineer depth. We focus on the infrastructure: how logs are collected from heterogeneous sources, transported reliably, stored efficiently, indexed for fast search, and queried under production pressure. We deliberately simplify log analysis (no ML anomaly detection, no AIOps) because the Staff Engineer's job is building the platform that makes logs reliable, searchable, and affordable — not building intelligence on top of it.

**The Staff Engineer's First Law of Logging**: A log system that ingests everything but can't search anything is a write-only database. A log system that searches fast but drops logs under load is a lie. The engineering challenge is doing BOTH — high-throughput ingestion AND low-latency search — on data that grows 40% year-over-year, with a budget that doesn't.

---

## Quick Visual: Log Aggregation & Query System at a Glance

```
┌─────────────────────────────────────────────────────────────────────────────┐
│     LOG AGGREGATION & QUERY SYSTEM: THE STAFF ENGINEER VIEW                 │
│                                                                             │
│   WRONG Framing: "A system that collects logs and stores them in a          │
│                   searchable database"                                      │
│   RIGHT Framing: "A real-time data pipeline that ingests 2M log lines/sec  │
│                   from 500K hosts, compresses them 10:1 into columnar      │
│                   storage with inverted indexes, supports sub-5-second     │
│                   full-text search across 15 days of data (200TB), enables │
│                   live tailing with <2s latency, enforces multi-tier       │
│                   retention (hot/warm/cold), and degrades gracefully under │
│                   10× burst — all while costing less per GB than the       │
│                   revenue each GB protects during incident investigation"   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Before designing, understand:                                      │   │
│   │                                                                     │   │
│   │  1. How many log-producing hosts? (100? 10K? 500K?)                │   │
│   │  2. Average log line size? (200B? 500B? 2KB?)                      │   │
│   │  3. What's the search pattern? (grep-style? SQL? structured?)      │   │
│   │  4. Retention requirements? (7 days? 90 days? 7 years?)            │   │
│   │  5. Who queries? (Engineers debugging? Security auditing? ML?)      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   THE UNCOMFORTABLE TRUTH:                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Logs are the most voluminous data in any infrastructure. They      │   │
│   │  grow faster than any other data type (40% YoY). They're looked    │   │
│   │  at intensely for 24 hours (during incidents) and then almost      │   │
│   │  never again. 95% of logs are never searched. But you don't know   │   │
│   │  WHICH 95% until you need the other 5%. This asymmetry — write     │   │
│   │  everything, read almost nothing — drives every architectural       │   │
│   │  decision: optimize for write throughput and storage efficiency,    │   │
│   │  accept higher query latency for older data.                       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## L5 vs L6 Log System Decisions

| Scenario | L5 Approach | L6 Approach |
|----------|-------------|-------------|
| **Log ingestion** | "Ship all logs to a central Kafka cluster" | "Multi-tier collection: Local agent buffers on disk, batches and compresses before shipping. Agent has a 10GB disk buffer so it survives a 30-minute network partition without losing logs. Backpressure signals from the pipeline cause agents to reduce sampling for DEBUG logs, not drop ERROR logs." |
| **Storage format** | "Store logs as JSON in a distributed filesystem" | "Columnar storage with dictionary encoding for repeated fields (service name, host, level), LZ4 compression on message bodies, inverted index on indexed fields (service, level, trace_id, user_id). 10:1 compression ratio. Separate hot tier (SSD, indexed, fast query) from warm tier (HDD, compressed, slower query) from cold tier (object storage, archived, minutes to query)." |
| **Query execution** | "Full scan through all log files matching the time range" | "Query planner that uses the inverted index to narrow to matching segments BEFORE scanning. For `service=payments AND level=ERROR AND time=[last 1h]`: Index lookup → 200 matching segments out of 50,000 → scan only those 200. 250× less I/O than full scan." |
| **Retention** | "Keep everything for 90 days, then delete" | "Tiered retention with different SLAs: Hot (0-7 days, SSD, <5s query), Warm (7-30 days, HDD, <30s query), Cold (30-365 days, object storage, <5min query). Each tier has different storage cost, query speed, and availability guarantee. Transition is automated, transparent to queries." |
| **Live tailing** | "Poll the search API every second" | "Dedicated tailing pipeline: Logs fork at ingestion — one path to storage, one path to a fan-out service that pushes matching logs to open tail sessions via WebSocket. Tailing latency: <2 seconds from log emission to engineer's terminal. No polling. No search API load." |
| **Multi-tenancy** | "Shared cluster, best-effort" | "Per-tenant ingestion quotas (GB/day), per-tenant query quotas (concurrent queries, scanned bytes/query). Noisy-neighbor isolation: Tenant A's 500GB/day DEBUG log dump doesn't degrade Tenant B's ERROR log search during an incident. Chargeback: Each team sees their log cost." |

**Key Difference**: L6 engineers design the log system around the fundamental asymmetry — massive writes, sparse reads — and optimize each path independently. They think about what happens when the system is needed most (during incidents, when everyone is searching simultaneously) and ensure it performs well precisely when load is highest and stakes are greatest.

## Staff vs Senior: The Log System Divide

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    STAFF vs SENIOR: LOG SYSTEM MINDSET                        │
│                                                                             │
│   Senior optimizes for the happy path; Staff optimizes for the incident.     │
│                                                                             │
├──────────────────────────────┬──────────────────────────────────────────────┤
│ Senior (L5)                  │ Staff (L6)                                   │
├──────────────────────────────┼──────────────────────────────────────────────┤
│ "Ship logs to a central DB"  │ Asks: Write throughput? Read pattern?        │
│                              │ Cost at 40% YoY growth? Failure modes?       │
├──────────────────────────────┼──────────────────────────────────────────────┤
│ "Search = scan time range"   │ "Index-first: 10-100× scan reduction.       │
│                              │  Full scan is the fallback, not the design."  │
├──────────────────────────────┼──────────────────────────────────────────────┤
│ "Pipeline down → logs lost"  │ "Agent disk buffer. 10GB. 55 hours.         │
│                              │  ERROR never dropped. Design for outage."     │
├──────────────────────────────┼──────────────────────────────────────────────┤
│ "One storage tier, one SLA"  │ "Hot/warm/cold. Each tier: different cost,   │
│                              │  different latency. Tiered = viability."      │
├──────────────────────────────┼──────────────────────────────────────────────┤
│ "Incident = edge case"      │ "Incident = design case. 5× burst + 10×      │
│                              │  search storm. Cache, auto-scale, isolation." │
└──────────────────────────────┴──────────────────────────────────────────────┘

SCALE INFLECTION: Senior approach works until ~50 hosts, <10GB/day.
Staff approach required when: 500+ hosts, multi-tenant, incident search
storm would overload search, or storage cost exceeds $10K/month.
```

---

# Part 1: Foundations — What a Log Aggregation & Query System Is and Why It Exists

## What Is a Log Aggregation & Query System?

A log aggregation and query system collects log output from every service, server, container, and infrastructure component in a distributed system, stores it centrally, and provides fast search capabilities so engineers can debug issues, investigate incidents, and audit system behavior.

### The Simplest Mental Model

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    THE SIMPLEST MENTAL MODEL                                │
│                                                                             │
│   A log aggregation system is a LIBRARY CATALOG FOR MACHINE OUTPUT:        │
│                                                                             │
│   COLLECTION (gathering the books):                                         │
│   → 500,000 hosts each produce log lines                                   │
│   → Each line: timestamp, service, level, message, metadata                │
│   → Example: "2024-01-15 10:23:45 payments ERROR Failed to charge          │
│     card ending 4242: timeout from payment processor, trace_id=abc123"     │
│   → 2 million log lines per second across the fleet                        │
│   → Each line: ~500 bytes average (some 100B, some 5KB)                    │
│                                                                             │
│   TRANSPORT (shipping to the library):                                      │
│   → Log agents on each host collect, batch, compress, and ship             │
│   → Network transport to central ingestion service                         │
│   → Ingestion writes to storage with indexing                              │
│                                                                             │
│   STORAGE (organizing on shelves):                                          │
│   → Logs stored in time-partitioned, indexed segments                      │
│   → Hot storage (SSD): Last 7 days — fast search                          │
│   → Warm storage (HDD): 7-30 days — moderate search speed                 │
│   → Cold storage (object store): 30-365 days — slow but cheap             │
│                                                                             │
│   SEARCH (finding the book you need):                                       │
│   → Engineer at 3 AM: "Show me all ERROR logs from payments service        │
│     in the last hour with trace_id=abc123"                                 │
│   → System uses inverted index → narrows to relevant segments              │
│   → Scans matching segments → returns results in 2-5 seconds              │
│   → Engineer finds: The payment processor timed out 47 times in            │
│     the last hour. Root cause: Network partition to processor's DC.        │
│                                                                             │
│   LIVE TAILING (watching books being written):                              │
│   → Developer: "Show me live ERROR logs from my service"                   │
│   → System streams matching logs in real-time (<2 second delay)            │
│   → Like `tail -f` but across 200 instances simultaneously                │
│                                                                             │
│   SCALE:                                                                    │
│   → 500,000 hosts producing logs                                           │
│   → 2 million log lines/sec (170 billion/day)                              │
│   → ~1TB/hour raw, ~100GB/hour compressed                                  │
│   → 15 days hot: 36TB compressed (SSD)                                     │
│   → 30 days warm: ~72TB compressed (HDD)                                   │
│   → 365 days cold: ~900TB compressed (object storage)                      │
│   → Search QPS: ~500 queries/sec (engineers + automated alerts)            │
│   → During incidents: Search QPS spikes 10-20×                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### What the System Does on Every Log Line

```
FOR each log line emitted by any service:

  1. AGENT COLLECTION (on the host)
     Log line written to stdout/file → local agent reads it
     → Agent: Parse, add host metadata (hostname, region, pod_id)
     → Agent: Buffer locally (memory + disk spillover)
     → Agent: Batch (accumulate 1000 lines or 1 second, whichever first)
     → Agent: Compress batch (LZ4 → ~10:1 for text)
     → Agent: Ship to ingestion endpoint
     Cost: ~0.1ms per line (amortized over batch)

  2. INGESTION (central service)
     Receive compressed batch → decompress → validate
     → Parse structured fields (timestamp, service, level, trace_id)
     → Route to correct storage partition (by time + tenant)
     → Write to write-ahead log (durability)
     → Build inverted index entries for indexed fields
     → Write to columnar segment (append-only)
     Cost: ~0.5ms per line (amortized over batch of 1000)

  3. INDEXING (inline with ingestion)
     For each indexed field (service, level, host, trace_id):
     → Update inverted index: field_value → [segment_id, offset]
     → Example: "service=payments" → [seg_4521, seg_4522, seg_4523]
     → Index is updated every segment flush (every 30 seconds)
     Cost: ~0.2ms per line (amortized)

  4. SEGMENT FLUSH (every 30 seconds or 64MB, whichever first)
     Buffered log lines → written as immutable segment file
     → Segment: Columnar format, compressed, with local inverted index
     → Segment metadata registered in catalog (time range, size, fields)
     → Segment available for search within ~30 seconds of log emission
     Cost: One I/O operation per segment (not per line)

  5. AVAILABLE FOR QUERY
     → Log line searchable: ~30 seconds after emission (hot tier)
     → Log line searchable: ~1 second via live tailing pipeline

TOTAL INGESTION OVERHEAD: ~0.8ms per line (amortized)
  → At 2M lines/sec: 1,600 CPU-seconds/sec → ~50 ingestion instances
  → Primary bottleneck: Disk I/O for segment writes, not CPU
```

## Why Does a Log Aggregation & Query System Exist?

### The Core Problem

In a distributed system with 500,000 hosts running thousands of microservices, understanding what happened requires correlating information across many machines:

1. **Logs are produced everywhere, needed in one place.** A single user request touches 12 services across 40 hosts. The error is in service 7, but the symptom appears in service 12. Without centralized logs, the on-call engineer must SSH into 40 hosts, grep through local files, and mentally correlate timestamps. At 3 AM during a SEV-1 with 10,000 users affected, this takes hours.

2. **Local logs are ephemeral.** Containers restart. VMs are recycled. Auto-scaling removes hosts. Local log files are lost with the host. The log line that explains WHY the service crashed is ON the host that crashed — and is gone.

3. **Incidents require fast search across massive volumes.** "Show me all errors with trace_id X" must search through hours of data across all services. Without an index, this is a full scan of terabytes — minutes to hours. With an index: seconds.

4. **Compliance and audit require long-term retention.** Regulatory requirements (SOX, HIPAA, PCI-DSS) demand log retention for 1-7 years. Storing a year of logs on local disks across 500K hosts is operationally impossible and prohibitively expensive.

5. **Alerting requires real-time log analysis.** "If any service logs > 100 ERROR lines/minute, page the on-call." This requires a streaming view of logs across the entire fleet — impossible with local files.

### What Happens If This System Does NOT Exist

```
WITHOUT A LOG AGGREGATION SYSTEM:

  MINUTE 0: PagerDuty fires. "Payment success rate dropped to 82%."
  MINUTE 1: On-call SSH's into payments-1. Greps /var/log/payments.log.
    → "Connection timeout to card-processor." OK, but which card processor?
  MINUTE 3: SSH into card-processor-gateway-1. Grep error logs.
    → No errors. Maybe it's a different gateway instance.
  MINUTE 5: SSH into card-processor-gateway-2 through gateway-15.
    → Instance 7 has errors: "DNS resolution failed for processor.bank.com"
  MINUTE 10: Found the problem on one instance. But are OTHER services affected?
    SSH into order-service, inventory-service, notification-service...
  MINUTE 20: Still SSH'ing. Found 3 more services with DNS-related errors.
    The DNS resolver in us-east-2b is failing.
  MINUTE 25: Realize the DNS issue is also affecting logging infrastructure
    in us-east-2b. Some hosts can't even send their logs.
  MINUTE 30: Escalate. 30 minutes for an issue that takes 30 SECONDS with
    centralized log search: "level=ERROR AND message=*DNS* AND time=[last 30min]"

  ONE YEAR LATER:
  → Security audit: "Show us all access logs for user X from March-June."
  → Logs from March? Those hosts were recycled 8 months ago. Logs are gone.
  → Audit finding: "Insufficient logging." Fine: $500K.

  COST OF NOT HAVING CENTRALIZED LOGS:
  → MTTR (Mean Time To Resolve): 5× longer without log search
  → MTTR × hourly revenue impact = $50K-500K per major incident in lost revenue
  → 20 major incidents/year = $1M-10M in extended downtime
  → Plus: Compliance fines, security audit failures, engineer burnout
```

---

# Part 2: Functional Requirements (Deep Enumeration)

## Core Use Cases

```
1. LOG INGESTION
   Collect logs from all hosts and ship to central storage
   Input: Log lines (stdout, files, syslog, structured JSON)
   Output: Logs persisted in indexed storage, searchable
   Volume: 2M lines/sec, ~1TB/hour raw, ~100GB/hour compressed
   Latency: < 30 seconds from emission to searchable

2. FULL-TEXT SEARCH
   Find logs matching a query across time range and services
   Input: Query (field filters + free-text + time range)
   Output: Matching log lines, sorted by time (newest first)
   QPS: ~500/sec normal, ~5000/sec during incidents
   Latency: < 5 seconds for hot tier (last 7 days), < 30 seconds for warm

3. LIVE TAILING
   Stream matching logs in real-time as they're produced
   Input: Filter (service, level, free-text pattern)
   Output: Streaming log lines matching filter, < 2 second delay
   Concurrent sessions: ~2,000 (developers + automated tools)

4. LOG-BASED ALERTING
   Trigger alerts when log patterns match defined rules
   Input: Alert rule (pattern, threshold, window)
   Output: Alert fired when threshold exceeded
   Examples: "> 100 ERROR lines/min from service X", "OOM killed detected"
   Volume: ~5,000 alert rules evaluated continuously

5. LOG ANALYTICS / AGGREGATION
   Count, group, and aggregate log fields over time ranges
   Input: Aggregation query ("count errors by service, last 24h")
   Output: Aggregated results (table or time-series)
   QPS: ~100/sec (dashboards, automated reports)
   Latency: < 10 seconds for last 24 hours

6. LOG EXPORT / ARCHIVE
   Export logs to external systems (compliance, long-term analytics)
   Input: Export definition (filter, time range, destination)
   Output: Logs written to cold storage or external system
   Frequency: Continuous (streaming) or scheduled (daily batch)
```

## Read Paths

```
1. SEARCH QUERY (most common)
   → "service=payments AND level=ERROR AND time=[last 1h]"
   → QPS: 500/sec normal, 5000/sec during incident
   → Latency budget: < 5 seconds (hot), < 30 seconds (warm)
   → Pattern: Filter by indexed fields → scan matching segments → return

2. LIVE TAIL
   → "tail --service=checkout --level=ERROR"
   → Concurrent: ~2,000 sessions
   → Latency: < 2 seconds from emission
   → Pattern: Fan-out on ingestion path → filter → push to client

3. LOG CONTEXT (around a specific log line)
   → "Show me 50 lines before and after this log line, same host"
   → QPS: ~200/sec (used during debugging)
   → Latency: < 2 seconds
   → Pattern: Seek to offset in segment → read surrounding lines

4. AGGREGATION QUERY
   → "Count errors by service, by minute, last 24 hours"
   → QPS: ~100/sec (dashboards)
   → Latency: < 10 seconds
   → Pattern: Scan segments for time range → aggregate in query engine

5. TRACE CORRELATION
   → "Show all logs with trace_id=abc123 across all services"
   → QPS: ~100/sec (trace investigation)
   → Latency: < 5 seconds
   → Pattern: Inverted index lookup on trace_id → retrieve from segments

6. COMPLIANCE QUERY (cold storage)
   → "Show all access logs for user_id=456 from March 2023"
   → QPS: ~5/sec (rare, high-value)
   → Latency budget: < 5 minutes
   → Pattern: Scan cold storage → restore to warm → query
```

## Write Paths

```
1. LOG INGESTION (dominant write)
   → 2M lines/sec from 500K hosts
   → Batch writes: 1000 lines per batch → 2000 batches/sec
   → Each batch: Compressed, ~50KB
   → Write path: Agent → ingestion → WAL → segment → index

2. INDEX UPDATES (inline with ingestion)
   → Inverted index updated per segment flush (every 30 seconds)
   → 2000 new segments/30 seconds = ~67 segments/sec across the cluster
   → Each segment: ~30 seconds of logs for one partition

3. SEGMENT METADATA
   → Catalog updated when segments are created, merged, or transitioned
   → ~100 metadata writes/sec
   → Small (< 1KB per write)

4. ALERT RULE DEFINITIONS
   → ~50 changes/day (create, update, delete rules)
   → Negligible write volume

5. RETENTION POLICY EXECUTION
   → Hot → warm transition: ~4,000 segments/day moved
   → Warm → cold transition: ~4,000 segments/day archived
   → Cold expiry: ~4,000 segments/day deleted
   → Runs as background batch process
```

## Control / Admin Paths

```
1. TENANT MANAGEMENT
   → Create/configure tenants (teams, services)
   → Set ingestion quotas, retention policies, query limits
   → View usage dashboards

2. RETENTION POLICY MANAGEMENT
   → Define hot/warm/cold tier durations per tenant
   → Override retention for compliance-tagged logs
   → Manually extend retention for post-mortem data

3. INDEX CONFIGURATION
   → Define which fields are indexed (service, level, trace_id, user_id)
   → Adding a new indexed field triggers re-indexing of recent data
   → Removing an indexed field frees storage

4. ALERT RULE MANAGEMENT
   → Create/edit/delete log-based alert rules
   → Set notification targets (PagerDuty, Slack, email)
   → View alert history and metrics

5. CLUSTER OPERATIONS
   → Capacity planning (add storage nodes, ingestion instances)
   → Rebalance partitions across storage nodes
   → Rolling upgrades of ingestion/query/storage components
```

## Edge Cases

```
1. LOG BURST (10× normal volume)
   Service enters a tight error loop → 100× normal log output.
   → 10,000 lines/sec from ONE host instead of 100.
   → Agent: Rate-limit per host. Drop DEBUG, sample INFO, keep all ERROR.
   → Pipeline: Absorb burst in buffer. If sustained: Enforce tenant quota.
   → RISK: Burst from one service floods the pipeline → other tenants delayed.
   → SOLUTION: Per-tenant ingestion queues. Isolation, not shared buffer.

2. MALFORMED LOG LINES
   Service emits binary data, multi-MB stack traces, or non-UTF-8 bytes.
   → Agent: Truncate lines > 10KB. Replace non-UTF-8 with replacement char.
   → Ingestion: Parse best-effort. Unparseable lines stored with raw_message.
   → NEVER drop a log line because it's malformed. Malformed logs during
     an incident are often the most diagnostic.

3. CLOCK SKEW
   Host clock is 5 minutes ahead → logs appear from "the future."
   → Ingestion: Record BOTH source_timestamp (host clock) and
     ingest_timestamp (server clock, reliable).
   → Query: Default to ingest_timestamp for time range filtering.
   → Display: Show source_timestamp to user (preserves causal ordering).

4. AGENT HOST CRASH
   Host crashes → agent dies → buffered logs in agent's disk buffer.
   → On host restart: Agent resumes from disk buffer, ships unsent logs.
   → If host is terminated (spot instance): Disk buffer lost.
   → MITIGATION: Agent flushes to central pipeline frequently (every 1 second).
     Worst case: ~1 second of logs lost on hard crash without restart.

5. PIPELINE BACKLOG
   Ingestion pipeline can't keep up with volume → consumer lag grows.
   → Logs still being produced. Agent disk buffer grows.
   → If backlog persists > 30 minutes: Agent buffer may fill (10GB limit).
   → RESPONSE: Agent starts dropping lowest-priority logs (DEBUG first).
   → Guarantee: ERROR and higher are NEVER dropped by the agent.

6. QUERY OF DEATH
   A query scans 30 days of data with no filters → scans petabytes.
   → PROTECTION: Per-query scan limit (max 1TB). Query killed if exceeded.
   → PROTECTION: Time range required (can't query "all time" without override).
   → PROTECTION: Concurrent query limit per user (max 5).
```

## What Is Intentionally OUT of Scope

```
1. APPLICATION PERFORMANCE MONITORING (APM)
   Distributed tracing, flame graphs, latency analysis.
   → Log system stores log lines. Tracing system stores spans.
   → INTEGRATION: trace_id in logs links to the tracing system.
   → They share the transport layer but different storage and query engines.

2. METRICS COLLECTION
   Time-series metrics (CPU, memory, request rate, latency percentiles).
   → Metrics are numeric, sampled, aggregated by time.
   → Logs are textual, complete, grouped by source.
   → Different storage engines, different query patterns, different costs.

3. LOG-BASED ML / ANOMALY DETECTION
   Automatically detecting anomalous patterns in logs.
   → The log system PROVIDES data for anomaly detection.
   → The anomaly detection system is a CONSUMER, not part of the platform.

4. SECURITY INFORMATION & EVENT MANAGEMENT (SIEM)
   Security-specific log analysis, correlation, and threat detection.
   → SIEM systems consume logs from our system (export/streaming API).
   → SIEM has different indexing, retention, and query requirements.

WHY: The log system is on the critical path of EVERY debug session and
EVERY incident investigation. Coupling it with APM, metrics, or SIEM
creates a monolith where a metrics pipeline OOM crashes log ingestion.
The log system must be independently available and independently scalable.
```

---

# Part 3: Non-Functional Requirements (Reality-Based)

## Latency Expectations

```
INGESTION (log emission to searchable):
  P50: < 10 seconds
  P95: < 30 seconds
  P99: < 60 seconds
  RATIONALE: Logs must be searchable DURING an incident. If it takes 5
  minutes for a log to appear in search, the on-call engineer is flying
  blind for 5 minutes. 30 seconds is the sweet spot: Fast enough for
  incident investigation, slow enough to batch and compress efficiently.

LIVE TAILING (log emission to engineer's screen):
  P50: < 1 second
  P95: < 2 seconds
  P99: < 5 seconds
  RATIONALE: Live tailing must feel "real-time." Developers use it like
  `tail -f` — if there's a 10-second delay, they switch to SSH + grep.
  The tailing pipeline is a SEPARATE path from the indexing pipeline.

SEARCH (hot tier, last 7 days):
  P50: < 2 seconds
  P95: < 5 seconds
  P99: < 15 seconds
  RATIONALE: Search is used during incidents when every second matters.
  Sub-5-second response for common queries (service + level + time range)
  is the minimum acceptable experience. Queries spanning larger time ranges
  or using free-text search take longer (acceptable).

SEARCH (warm tier, 7-30 days):
  P50: < 10 seconds
  P95: < 30 seconds
  P99: < 60 seconds
  RATIONALE: Warm data is for post-mortem analysis, not live debugging.
  30 seconds is acceptable because the engineer is writing a report, not
  responding to an active incident.

SEARCH (cold tier, 30-365 days):
  P50: < 2 minutes
  P95: < 5 minutes
  P99: < 15 minutes
  RATIONALE: Cold data is for compliance, audit, and historical analysis.
  Minutes are acceptable. Data may need to be "thawed" (restored from
  object storage to queryable format) before search.

AGGREGATION (last 24h):
  P50: < 5 seconds
  P95: < 15 seconds
  RATIONALE: Aggregation powers dashboards. Dashboard refresh every 30
  seconds → 15-second query time is acceptable.
```

## Availability Expectations

```
INGESTION: 99.99% (four nines)
  If ingestion is down:
  → Log agents buffer locally (10GB disk buffer per host)
  → At 100 lines/sec per host × 500B/line = 50KB/sec → 10GB lasts ~55 hours
  → Agents flush buffer when ingestion recovers
  → IF ingestion down > 55 hours: Agents start dropping oldest buffered logs
  → CRITICAL: Log loss during extended outages is tolerable for DEBUG/INFO.
    ERROR and WARN must survive (agent prioritizes).

SEARCH: 99.9% (three nines)
  If search is down:
  → Engineers can't search logs → incident investigation severely impacted
  → MITIGATION: Engineers can still use live tailing (separate pipeline)
  → MITIGATION: Pre-built dashboards may still be served from cache
  → Search outage during a SEV-1 is itself a SEV-1.

LIVE TAILING: 99.9%
  If tailing is down:
  → Developers lose real-time log visibility
  → MITIGATION: Search still works (with 30-second delay)
  → Less critical than search (debugging, not incident response)

STORAGE (hot tier): 99.99%
  If hot storage nodes fail:
  → Replicated across 3 nodes. 1 node failure: No impact.
  → 2 node failures: Degraded (read from remaining replica, slower).
  → All 3 replicas lost: Data loss for that partition. Extremely rare.
```

## Consistency Needs

```
INGESTION: At-least-once delivery
  → Log lines may be delivered twice (agent retry after timeout)
  → Deduplication: Optional, at query time (by log_id if present)
  → ACCEPTABLE: Seeing a log line twice is far better than missing it.
    During incidents, missing the ONE log line that explains the root
    cause costs hours. A duplicate costs a scroll.

SEARCH: Point-in-time consistency (read your writes within 30 seconds)
  → Engineer emits a log line → searches for it → should find it
    within 30 seconds.
  → Stale results acceptable for aggregation (± 1 minute freshness).

RETENTION: Strongly consistent transitions
  → When data transitions from hot → warm: Data is available in warm
    BEFORE being deleted from hot. Never a gap.
  → When data expires from cold: Deletion is idempotent. Double-delete
    is a no-op.

ORDERING: Best-effort within a source, no global ordering guarantee
  → Logs from the SAME host appear in emission order (agent preserves order).
  → Logs from DIFFERENT hosts: Ordered by ingest_timestamp, not source_timestamp.
  → Cross-host causality: Use trace_id to reconstruct causal order.
```

## Durability

```
HOT TIER: Replicated 3× across storage nodes
  → Can survive 2 simultaneous node failures per partition
  → Data persisted to disk before acknowledgment to agent

WARM TIER: Replicated 2× (HDD, erasure-coded)
  → Lower replication than hot (cost optimization)
  → Acceptable: Warm data is also available in cold archive (backup)

COLD TIER: Object storage (inherently durable, 11 nines)
  → Object store handles replication internally
  → Log data archived in immutable format

AGENT DISK BUFFER: NOT durable across host termination
  → If host is forcefully terminated: Up to 1 second of logs lost
  → If host restarts normally: Buffer survives, logs shipped on restart
```

## Correctness vs User Experience Trade-offs

```
TRADE-OFF 1: Complete logs vs fast ingestion
  COMPLETE: Parse every field, validate schema, reject malformed lines
  FAST: Accept everything, parse best-effort, store malformed as raw
  RESOLUTION: Fast. Never reject a log line. Malformed logs are stored
  as raw_message with a "parse_failed" flag. Engineers can still search
  for them. The worst outcome is losing a log line that would have
  explained a production issue.

TRADE-OFF 2: Query accuracy vs query speed
  ACCURATE: Scan all segments in time range for complete results
  FAST: Use index to narrow to likely segments, may miss edge cases
  RESOLUTION: Index-first query with completeness verification.
  If index says 0 results but query has free-text → fall back to scan.
  Index covers 99%+ of queries; full scan is the safety net.

TRADE-OFF 3: Low ingestion latency vs compression efficiency
  LOW LATENCY: Flush segments every 5 seconds → small segments, poor compression
  HIGH COMPRESSION: Flush every 5 minutes → better compression, higher latency
  RESOLUTION: 30-second flush interval. Balanced: Good compression (10:1),
  acceptable latency (30 seconds to searchable). Background compaction
  merges small segments into larger, better-compressed segments.
```

## Security Implications (Conceptual)

```
1. LOGS CONTAIN SENSITIVE DATA
   Logs often contain: User IDs, IP addresses, request parameters,
   error messages with stack traces that may include variable values.
   → Access control: Per-tenant permissions. Team A can't search Team B's logs.
   → PII masking: Agent-side or ingestion-side masking of known PII patterns
     (credit card numbers, SSNs, email addresses).
   → Audit log: Every search query is logged (who searched for what, when).

2. LOG TAMPERING
   Attacker gains access to a host → modifies local logs to cover tracks.
   → DEFENSE: Logs are shipped to central storage within 1 second.
     Attacker would need to compromise the central storage to erase evidence.
   → Central storage: Append-only. No in-place edits. Deletion only via
     retention policy (time-based, not user-initiated).

3. LOG EXFILTRATION
   Insider searches for sensitive data in logs (user activity, passwords).
   → DEFENSE: Search audit logging. Alert on unusual search patterns
     (e.g., "engineer searching for specific user_ids they don't own").
   → DEFENSE: Access tiers. Most engineers see their team's service logs.
     Audit/security logs require elevated permissions.
```

---

# Part 4: Scale & Load Modeling (Concrete Numbers)

## Workload Profile

```
HOSTS: 500,000 log-producing hosts (VMs, containers, infra)
LOG LINES PER SECOND: 2 million (fleet-wide)
AVERAGE LOG LINE SIZE: 500 bytes (raw), 50 bytes (compressed, 10:1)
RAW THROUGHPUT: 1 GB/sec = 3.6 TB/hour = 86 TB/day
COMPRESSED THROUGHPUT: 100 MB/sec = 360 GB/hour = 8.6 TB/day
INDEXED FIELDS: service, level, host, trace_id, user_id (5 fields)
SEARCH QPS (normal): 500 queries/sec
SEARCH QPS (incident): 5,000-10,000 queries/sec
LIVE TAIL SESSIONS: 2,000 concurrent
ALERT RULES: 5,000 continuously evaluated
```

## QPS Modeling

```
INGESTION:
  2M lines/sec, batched in groups of 1,000
  → 2,000 batch writes/sec to storage
  → Each batch: ~50KB compressed
  → Write throughput: 100 MB/sec sustained
  → Ingestion instances: ~50 (2M lines/sec / ~40K lines/sec per instance)

SEARCH (normal):
  500 queries/sec
  → Average query scans: ~200 segments (with index) out of ~200K hot segments
  → Average data scanned per query: ~100MB (from ~10TB of hot data)
  → Query latency: 2-5 seconds
  → Query instances: ~30 (500 QPS / ~17 QPS per instance at full load)

SEARCH (incident burst):
  5,000 queries/sec (10× normal)
  → Same query patterns but 10× concurrency
  → Query instances must scale: 30 → 300 (auto-scale within 2 minutes)
  → OR: Query result caching. During incidents, many engineers search
    for the SAME thing (same service, same time range, same error).
    Cache hit rate during incidents: 40-60%.
  → Effective load with caching: 5,000 × 0.5 = 2,500 unique queries/sec
  → Instances needed with caching: ~150

LIVE TAILING:
  2,000 concurrent sessions
  → Each session: Filter applied to ingestion stream
  → Match rate: ~0.1% of all logs match a typical tail filter
  → 2M lines/sec × 0.1% = 2,000 matching lines/sec across all sessions
  → Fan-out service instances: ~10

ALERTING:
  5,000 rules evaluated every 60 seconds
  → Each rule: Count matching logs in last N minutes
  → Uses pre-aggregated counts (not raw search)
  → Alerting instances: ~5
```

## Read/Write Ratio

```
INGESTION (WRITE-DOMINANT):
  Write: 2M lines/sec (100 MB/sec compressed)
  Read: 500 queries/sec, each scanning ~100MB = ~50 GB/sec scan rate
  Write:Read bytes: ~2:1 during normal operations
  BUT: During incidents, read volume spikes 10× → read exceeds write

LOG SYSTEM IS WRITE-HEAVY IN VOLUME BUT READ-CRITICAL IN VALUE.
  → 99% of logs are never searched.
  → The 1% that IS searched is worth $millions (incident investigation).
  → Design for write throughput, optimize for read performance.
```

## Growth Assumptions

```
HOST GROWTH: 20% YoY (infrastructure expansion)
LOG VOLUME GROWTH: 40% YoY (more hosts + more verbose logging)
  → WHY 40% > 20%: Each new microservice logs more than the monolith
    it replaced. Distributed tracing adds correlation IDs to every line.
    Structured logging adds JSON overhead. Engineers add more log statements
    because "storage is cheap" (it's not, at scale).
SEARCH QPS GROWTH: 25% YoY (more engineers, more automation)
RETENTION GROWTH: Flat (retention policies prevent growth, not storage)

WHAT BREAKS FIRST AT SCALE:

  1. Storage cost (FIRST TO BREAK)
     → 8.6 TB/day compressed × 365 days cold = 3.1 PB/year
     → At $0.004/GB/month (object storage): $12.8K/month for cold alone
     → At 40% growth: 4.4 PB next year, 6.1 PB year after
     → SOLUTION: Aggressive compression (columnar, dictionary encoding),
       tiered retention (not everything needs 365 days)

  2. Ingestion throughput
     → 2M lines/sec today → 3.9M in 2 years → 5.5M in 3 years
     → Ingestion scales horizontally (add instances)
     → BUT: Storage write throughput is bounded by disk/network I/O
     → SOLUTION: Better compression (fewer bytes to write), partitioning

  3. Search performance on larger datasets
     → Hot tier: 36TB today → 70TB in 2 years
     → Same query scans more data → slower results
     → SOLUTION: Better indexing (more indexed fields, bloom filters),
       segment pruning (skip segments that can't match)

  4. Index size
     → Inverted index: ~5% of data size. 36TB hot → 1.8TB index
     → At 40% growth: 3.5TB index in 2 years → must fit on SSD for speed
     → SOLUTION: Index only high-cardinality fields worth indexing.
       Don't index message body (use segment scan for free-text).

MOST DANGEROUS ASSUMPTIONS:
  1. "Log volume is proportional to traffic" — It's not. A single
     deployment bug can 100× log volume in minutes (tight error loop).
  2. "Engineers will follow logging best practices" — They won't.
     Someone will log the full HTTP request body (including file uploads)
     at INFO level. Per-host rate limits are essential.
  3. "Cold data is never accessed" — It is, during compliance audits,
     security investigations, and "what changed 6 months ago?" questions.
     Cold storage must be queryable, not just archival.
```

## Burst Behavior

```
BURST 1: Deployment error loop (single service)
  → Service deployed with a bug → logs 10,000 ERROR lines/sec (100× normal)
  → Single service can flood the pipeline for all tenants
  → SOLUTION: Per-host rate limit (1,000 lines/sec). Per-tenant quota.
  → Agent drops excess with sampling, preserving ERROR log lines.

BURST 2: Incident search storm (many engineers searching simultaneously)
  → SEV-1 incident → 200 engineers all search for the same error
  → Search QPS: 500 → 5,000 in 2 minutes
  → SOLUTION: Query result cache. Cache keyed by (query, time_range).
    First engineer's query: Cache miss, full execution.
    Next 199 engineers: Cache hit. ~5ms response.
  → Search auto-scaling: Spin up more query instances in 2 minutes.

BURST 3: Cascading failure (many services logging errors simultaneously)
  → Database goes down → 50 services log "connection refused" ERROR
  → Log volume 5× normal, concentrated in ERROR level
  → SOLUTION: Ingestion pipeline sized for 3× burst. Beyond that:
    Agent-side backpressure (buffer locally, ship when pipeline catches up).

BURST 4: Log pipeline recovery after outage
  → Ingestion down for 30 minutes → 500K hosts buffer locally
  → Pipeline recovers → 500K hosts flush simultaneously
  → Burst: 30 minutes × 2M lines/sec = 3.6B lines → shipped in ~30 minutes
  → Effective burst: ~4M lines/sec (2× normal) for 30 minutes
  → SOLUTION: Pipeline sized for 3× sustained. Recovery burst fits within.
```

---

# Part 5: High-Level Architecture (First Working Design)

## Core Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│       LOG AGGREGATION & QUERY SYSTEM ARCHITECTURE                           │
│                                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                     │
│  │ Host 1       │  │ Host 2       │  │ Host N       │                     │
│  │ ┌──────────┐ │  │ ┌──────────┐ │  │ ┌──────────┐ │                     │
│  │ │ Log Agent│ │  │ │ Log Agent│ │  │ │ Log Agent│ │                     │
│  │ │          │ │  │ │          │ │  │ │          │ │                     │
│  │ │ Buffer   │ │  │ │ Buffer   │ │  │ │ Buffer   │ │                     │
│  │ │ (10GB)   │ │  │ │ (10GB)   │ │  │ │ (10GB)   │ │                     │
│  │ └────┬─────┘ │  │ └────┬─────┘ │  │ └────┬─────┘ │                     │
│  └──────┼───────┘  └──────┼───────┘  └──────┼───────┘                     │
│         │                 │                  │                              │
│         └────────────────┬┘──────────────────┘                             │
│                          │                                                  │
│                          ▼                                                  │
│                ┌──────────────────┐                                         │
│                │ INGESTION SERVICE │                                         │
│                │ (50 instances)    │                                         │
│                │                  │                                         │
│                │ • Receive batches│──────────┐                              │
│                │ • Parse / enrich │          │                              │
│                │ • Route to store │          │  ┌──────────────────┐        │
│                │ • Build index    │          ├──│ TAIL FAN-OUT     │        │
│                │ • WAL write      │          │  │ SERVICE          │        │
│                └──────┬───────────┘          │  │                  │        │
│                       │                      │  │ • Filter match   │        │
│                       │                      │  │ • Push to clients│        │
│                       ▼                      │  │ • WebSocket      │        │
│         ┌─────────────────────────────┐      │  └──────────────────┘        │
│         │       STORAGE CLUSTER        │      │                              │
│         │                             │      │  ┌──────────────────┐        │
│         │  ┌───────────────────────┐  │      └──│ ALERT EVALUATOR  │        │
│         │  │ HOT TIER (SSD)        │  │         │                  │        │
│         │  │ Last 7 days           │  │         │ • Pattern match  │        │
│         │  │ 36TB compressed       │  │         │ • Threshold check│        │
│         │  │ Inverted index        │  │         │ • Fire alerts    │        │
│         │  │ < 5 sec query         │  │         └──────────────────┘        │
│         │  └───────────┬───────────┘  │                                     │
│         │              │ (transition)  │                                     │
│         │  ┌───────────▼───────────┐  │                                     │
│         │  │ WARM TIER (HDD)       │  │                                     │
│         │  │ 7-30 days             │  │                                     │
│         │  │ ~72TB compressed      │  │                                     │
│         │  │ Sparse index          │  │                                     │
│         │  │ < 30 sec query        │  │                                     │
│         │  └───────────┬───────────┘  │                                     │
│         │              │ (archive)     │                                     │
│         │  ┌───────────▼───────────┐  │                                     │
│         │  │ COLD TIER (Obj Store) │  │                                     │
│         │  │ 30-365 days           │  │                                     │
│         │  │ ~900TB compressed     │  │                                     │
│         │  │ Metadata only         │  │                                     │
│         │  │ < 5 min query         │  │                                     │
│         │  └───────────────────────┘  │                                     │
│         └─────────────────────────────┘                                     │
│                       │                                                     │
│                       ▼                                                     │
│         ┌──────────────────────────────┐                                    │
│         │ QUERY ENGINE (30+ instances)  │                                    │
│         │                              │                                    │
│         │ • Parse query                │                                    │
│         │ • Index lookup               │                                    │
│         │ • Scatter to storage nodes   │                                    │
│         │ • Gather and merge results   │                                    │
│         │ • Cache results              │                                    │
│         └──────────────────────────────┘                                    │
│                       │                                                     │
│                       ▼                                                     │
│         ┌──────────────────────────────┐                                    │
│         │ LOG UI / API                  │                                    │
│         │                              │                                    │
│         │ • Search interface           │                                    │
│         │ • Live tail view             │                                    │
│         │ • Dashboards                 │                                    │
│         │ • Alert management           │                                    │
│         └──────────────────────────────┘                                    │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                    SEGMENT CATALOG                                    │   │
│  │  Metadata for all segments: time range, size, tier, indexed fields   │   │
│  │  Used by query engine to plan which segments to scan                  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Responsibilities of Each Component

```
LOG AGENT (deployed on every host):
  → Reads log output (stdout, files, syslog)
  → Parses structured fields (JSON logs) or applies grok patterns
  → Adds host metadata (hostname, region, availability zone, pod_id)
  → Buffers in memory (1MB) and disk (10GB) for resilience
  → Batches log lines (1,000 per batch or 1 second, whichever first)
  → Compresses batch (LZ4)
  → Ships to ingestion service endpoint (round-robin across instances)
  → Handles backpressure: If ingestion slow → buffer more → if full →
    drop DEBUG first, then INFO, NEVER drop ERROR/WARN
  → Reports agent health metrics (buffer usage, drop rate, latency)

INGESTION SERVICE (stateless, horizontally scaled):
  → Receives compressed batches from agents
  → Decompresses and validates (rejects oversized batches, rate-limits per tenant)
  → Parses structured fields (timestamp, service, level, trace_id, message)
  → Enriches: Adds ingest_timestamp, partition_key
  → Writes to WAL (write-ahead log) for durability
  → Appends to in-memory segment buffer (accumulating logs for current segment)
  → When segment buffer reaches threshold (64MB or 30 seconds):
    → Flushes segment to hot storage
    → Builds local inverted index for segment
    → Registers segment in catalog
  → Forks log stream to: Tail fan-out service, alert evaluator

STORAGE CLUSTER (stateful, partitioned):
  → Manages segment files across three tiers (hot/warm/cold)
  → Hot tier: SSD nodes, 3× replication, inverted index per segment
  → Warm tier: HDD nodes, 2× replication (or erasure coding), sparse index
  → Cold tier: Object storage, archived segments, metadata-only index
  → Background: Compaction (merge small segments into large), transition
    (hot → warm → cold based on age), deletion (expired cold segments)

QUERY ENGINE (stateless, auto-scaled):
  → Parses query: Extracts field filters, time range, free-text patterns
  → Consults segment catalog: Which segments overlap the query time range?
  → Uses inverted index: Narrow from all segments to matching segments
  → Scans matching segments: Decompress, filter, extract matching lines
  → Merges results from multiple storage nodes (scatter-gather)
  → Sorts by timestamp, applies limit, returns to client
  → Caches results (TTL=30 seconds, keyed by query hash)

TAIL FAN-OUT SERVICE (stateful per session):
  → Receives forked log stream from ingestion (all logs, or per-partition)
  → Maintains registry of active tail sessions and their filters
  → For each incoming log batch: Evaluate all active session filters
  → Push matching logs to connected clients via WebSocket/gRPC stream
  → Session lifecycle: Create on client connect, destroy on disconnect/timeout

ALERT EVALUATOR (streaming):
  → Receives forked log stream from ingestion
  → Pre-aggregates: Counts matching logs per rule per window (1-minute tumbling)
  → Evaluates 5,000 rules every 60 seconds
  → If threshold breached: Fire alert to notification system
  → Stateful: Maintains running counts and dedup state (alert cooldown)

SEGMENT CATALOG (replicated metadata store):
  → Stores metadata for every segment: {segment_id, time_range, tier,
    storage_node, size, indexed_fields, partition_key}
  → Small dataset: ~500K active segments × ~500 bytes = ~250MB
  → Highly available: Replicated 3×. Queried by every search.
  → Updated by: Ingestion (new segments), compaction (merged segments),
    tier transition (moved segments), deletion (expired segments)
```

## Stateless vs Stateful Decisions

```
STATELESS (horizontally scalable):
  → Log agent: Stateless between batches (disk buffer is local, not shared)
  → Ingestion service: Stateless (segment buffer is transient, WAL is durable)
  → Query engine: Stateless (reads from storage, caches in local memory)
  → Log UI/API: Stateless web servers

STATEFUL (requires careful scaling):
  → Storage cluster: Owns segment files, manages replication, tiers
  → Segment catalog: Metadata for all segments
  → Tail fan-out: Maintains active session state
  → Alert evaluator: Maintains running counts and alert state
  → Inverted index: Maintained per storage node, updated with segments

CRITICAL DESIGN DECISION: Ingestion is stateless; storage is stateful.
  → Ingestion instances can be added/removed freely (no data to migrate).
  → Storage nodes hold data; adding/removing requires rebalancing partitions.
  → This separation means ingestion scales independently of storage.
```

## Data Flow: Log Line Lifecycle

```
PHASE 1: EMISSION
  Service code: log.error("Failed to charge card", {trace_id: "abc123"})
  → Log framework serializes: {"timestamp": "2024-01-15T10:23:45Z",
    "service": "payments", "level": "ERROR", "message": "Failed to charge
    card", "trace_id": "abc123"}
  → Written to stdout (container logs) or file

PHASE 2: COLLECTION
  Agent on host reads the log line
  → Parse structured fields (JSON → key-value pairs)
  → Add metadata: hostname, region, pod_id
  → Buffer in memory. Batch with other lines.
  → Compress batch (LZ4). Ship to ingestion endpoint.
  → Latency: < 1 second from emission to shipped

PHASE 3: INGESTION
  Ingestion service receives batch
  → Decompress. Validate. Parse indexed fields.
  → Write to WAL (durability).
  → Append to in-memory segment buffer.
  → Fork to tail fan-out service (for live tailing).
  → Fork to alert evaluator (for alerting).
  → When buffer full: Flush segment to hot storage.

PHASE 4: SEGMENT CREATION
  Segment flushed to hot storage
  → Columnar format: Fields stored separately (service column, level column,
    message column). Efficient compression per column.
  → Local inverted index: {service=payments: [offset 0, offset 47, ...]}
  → Segment registered in catalog: {seg_12345, time=[10:23:00, 10:23:30],
    tier=hot, node=storage-7}

PHASE 5: SEARCHABLE
  Engineer queries: service=payments AND level=ERROR AND time=[last 1h]
  → Query engine: Catalog → segments in time range → index lookup →
    matching segments → scan → results
  → Log line found. Displayed to engineer.
  → Latency from emission to searchable: ~30 seconds

PHASE 6: TIER TRANSITION
  After 7 days: Segment moved from hot (SSD) to warm (HDD)
  → Segment re-compressed (higher ratio for warm, slower decompression OK)
  → Index thinned (remove low-value index entries, keep service + level)
  → Catalog updated: tier=warm

  After 30 days: Segment archived to cold (object storage)
  → Segment written as immutable object
  → Only metadata retained in catalog (time range, partition, size)
  → Full segment must be restored to query

  After 365 days: Segment deleted
  → Object deleted from cold storage
  → Catalog entry removed
  → Gone forever (unless extended by compliance policy)
```

---

# Part 6: Deep Component Design (NO SKIPPING)

## Log Agent

### Internal Data Structures

```
AGENT STATE:
{
  // Input sources
  sources: [
    {type: "file", path: "/var/log/app.log", position: 284729},
    {type: "stdout", container_id: "abc123"},
    {type: "syslog", port: 514}
  ]
  
  // Memory buffer (fast, limited)
  memory_buffer: {
    lines: [...]           // Unbatched lines waiting for batch threshold
    size: 847KB            // Current buffer usage
    max_size: 1MB          // Flush to disk if exceeded
  }
  
  // Disk buffer (large, resilient)
  disk_buffer: {
    path: "/var/lib/log-agent/buffer/"
    files: ["batch_001.lz4", "batch_002.lz4", ...]
    total_size: 2.3GB      // Current usage
    max_size: 10GB         // Start dropping if exceeded
    oldest_batch: "2024-01-15T10:20:00Z"
  }
  
  // Backpressure state
  backpressure: {
    pipeline_healthy: true
    drop_level: NONE       // NONE → DEBUG → INFO (never ERROR/WARN)
    consecutive_failures: 0
  }
  
  // Host metadata (added to every line)
  metadata: {
    hostname: "payments-prod-7a3b"
    region: "us-east-1"
    az: "us-east-1b"
    pod_id: "payments-7a3b-xk9f"
    agent_version: "3.2.1"
  }
}
```

### Algorithms

```
BATCHING ALGORITHM:

  function collect_and_ship():
    while true:
      line = read_next_log_line(sources)
      
      // Parse and enrich
      parsed = parse_line(line)  // Extract timestamp, level, fields
      parsed.metadata = agent.metadata
      
      // Rate limit per host
      if lines_this_second > MAX_LINES_PER_SECOND (1000):
        if parsed.level in [DEBUG, INFO] and backpressure.drop_level >= parsed.level:
          increment(dropped_counter, parsed.level)
          continue  // Drop low-priority under pressure
      
      // Add to memory buffer
      memory_buffer.append(parsed)
      
      // Flush batch when threshold reached
      if memory_buffer.size >= 1MB or time_since_last_flush >= 1 second:
        batch = memory_buffer.drain()
        compressed = lz4_compress(serialize(batch))
        
        if pipeline_healthy:
          success = send_to_ingestion(compressed)
          if not success:
            disk_buffer.write(compressed)
            backpressure.consecutive_failures += 1
            update_drop_level()
        else:
          disk_buffer.write(compressed)
        
        // Try to flush disk buffer
        if pipeline_healthy and disk_buffer.size > 0:
          flush_disk_buffer()

DISK BUFFER MANAGEMENT:

  function flush_disk_buffer():
    // Ship oldest batches first (FIFO)
    while disk_buffer.size > 0:
      batch = disk_buffer.read_oldest()
      success = send_to_ingestion(batch)
      if success:
        disk_buffer.delete_oldest()
      else:
        break  // Pipeline still unhealthy, stop flushing
  
  function manage_disk_pressure():
    if disk_buffer.size > max_size * 0.9:  // 90% full
      // Start dropping oldest DEBUG logs to make room
      drop_oldest_by_level(DEBUG)
    if disk_buffer.size > max_size * 0.95:  // 95% full
      // Drop oldest INFO logs too
      drop_oldest_by_level(INFO)
    // NEVER drop ERROR or WARN from disk buffer

BACKPRESSURE SIGNALING:

  function update_drop_level():
    if consecutive_failures > 10:
      drop_level = DEBUG     // Drop DEBUG, keep INFO+
    if consecutive_failures > 50:
      drop_level = INFO      // Drop INFO+DEBUG, keep WARN+ERROR
    if consecutive_failures == 0:
      drop_level = NONE      // Ship everything
```

### Failure Behavior

```
AGENT CRASH:
  → Agent process restarts (systemd/supervisord auto-restart)
  → On restart: Read file positions from checkpoint file
  → Resume reading from last checkpoint → may re-read some lines (at-least-once)
  → Disk buffer survives crash (files on disk)
  → Lines in memory buffer lost (< 1MB, < 1 second of data)

HOST CRASH (ungraceful):
  → Agent and disk buffer lost
  → Lines in disk buffer (~2 seconds to 30 minutes) lost
  → Lines already shipped: Safe in central storage
  → ACCEPTABLE: 1-2 seconds of logs per host crash. Unavoidable without
    synchronous shipping (which would add 50ms latency to every log line).

PIPELINE UNREACHABLE (network partition):
  → Agent buffers to disk (10GB capacity)
  → At 100 lines/sec × 500B = 50KB/sec → 10GB lasts ~55 hours
  → After 55 hours: Agent starts dropping DEBUG (extending buffer life)
  → On network recovery: Agent flushes disk buffer (may take 30+ minutes
    for full buffer at agent's shipping rate)

AGENT CPU/MEMORY LIMITS:
  → Agent is capped at 100MB memory, 5% CPU on the host
  → If log volume exceeds what agent can process within limits:
    → Agent buffers to disk (slower but within limits)
    → If both CPU and disk are saturated: Drop lowest-priority logs
```

## Ingestion Service

### Internal Data Structures

```
INGESTION INSTANCE STATE:
{
  // Per-partition segment buffer
  segment_buffers: {
    "partition_0": {
      lines: [...]
      size: 42MB
      start_time: "2024-01-15T10:23:00Z"
      line_count: 87432
    },
    "partition_1": { ... },
    // 100 partitions per instance
  }
  
  // Write-ahead log (for durability before segment flush)
  wal: {
    path: "/data/wal/"
    current_file: "wal_00247.log"
    current_size: 23MB
    rotation_threshold: 64MB
  }
  
  // Tenant quotas
  quotas: {
    "team_payments": {rate: 50000 lines/sec, used: 32100, window: 1sec},
    "team_ml": {rate: 200000 lines/sec, used: 187400, window: 1sec},
    // ... 200 tenants
  }
  
  // Metrics
  metrics: {
    lines_ingested: Counter
    bytes_ingested: Counter
    lines_dropped_quota: Counter
    segment_flush_duration: Histogram
    wal_write_duration: Histogram
  }
}
```

### Algorithms

```
INGESTION PIPELINE:

  function ingest_batch(compressed_batch):
    batch = decompress(compressed_batch)
    tenant = extract_tenant(batch)
    
    // Quota enforcement
    if quotas[tenant].used + batch.line_count > quotas[tenant].rate:
      // Over quota: Accept ERROR/WARN, reject DEBUG/INFO
      batch = filter_by_priority(batch, min_level=WARN)
      increment(lines_dropped_quota, batch.dropped_count)
    
    for line in batch.lines:
      // Parse structured fields
      parsed = parse_structured_fields(line)
      // {timestamp, service, level, host, trace_id, message, ...}
      
      // Determine partition
      partition = hash(parsed.service + parsed.host) % NUM_PARTITIONS
      
      // Write to WAL (durability)
      wal.append(partition, serialize(parsed))
      
      // Add to segment buffer
      segment_buffers[partition].append(parsed)
      
      // Fork to tail fan-out
      tail_fanout.send(parsed)
      
      // Fork to alert evaluator
      alert_evaluator.send(parsed)
    
    // Check segment flush thresholds
    for partition, buffer in segment_buffers:
      if buffer.size >= 64MB or buffer.age >= 30 seconds:
        flush_segment(partition, buffer)

SEGMENT FLUSH:

  function flush_segment(partition, buffer):
    // Build columnar segment
    segment = build_columnar_segment(buffer.lines)
    // Columns: timestamp[], service[], level[], host[], message[], ...
    // Each column compressed independently (dictionary + LZ4)
    
    // Build local inverted index
    index = build_inverted_index(buffer.lines, INDEXED_FIELDS)
    // index: {service=payments: [0, 47, 102, ...], level=ERROR: [47, 203, ...]}
    
    // Write to hot storage
    segment_id = generate_segment_id()
    hot_storage.write(segment_id, segment, index)
    
    // Register in catalog
    catalog.register({
      segment_id: segment_id,
      partition: partition,
      time_range: [buffer.start_time, now],
      tier: HOT,
      storage_node: assigned_node(partition),
      size: segment.compressed_size,
      line_count: buffer.line_count,
      indexed_fields: INDEXED_FIELDS
    })
    
    // Clear buffer and WAL
    buffer.clear()
    wal.truncate(partition, up_to=now)
```

### Failure Behavior

```
INGESTION INSTANCE CRASH:
  → In-memory segment buffer lost (up to 64MB or 30 seconds of data)
  → WAL survives on disk. On restart: Replay WAL → rebuild segment buffer.
  → Agents retry sending to other ingestion instances (round-robin)
  → Impact: 0-30 seconds of data delayed (replayed from WAL), not lost.

STORAGE NODE UNREACHABLE:
  → Segment flush fails for partitions on that node
  → Buffer grows in memory → if > 256MB: Write overflow segments to
    alternate storage node (temporary). Rebalance when original recovers.
  → WAL continues accumulating → disk usage grows on ingestion instance.
  → If ingestion instance disk fills: Backpressure to agents (slow down).

WAL CORRUPTION:
  → WAL entry has bad checksum → skip corrupted entries
  → Impact: ~1000 log lines lost (one batch, ~1MB)
  → ACCEPTABLE: WAL corruption is extremely rare (hardware failure).
    Losing 1 second of logs is tolerable.
```

## Query Engine

### Internal Data Structures

```
QUERY PLAN:
{
  query: "service=payments AND level=ERROR AND message=*timeout*"
  time_range: [now - 1h, now]
  
  // Plan steps
  steps: [
    {type: "catalog_lookup", time_range: [...], result: "candidate_segments"},
    {type: "index_lookup", field: "service", value: "payments",
     input: "candidate_segments", result: "filtered_1"},
    {type: "index_lookup", field: "level", value: "ERROR",
     input: "filtered_1", result: "filtered_2"},
    {type: "segment_scan", segments: "filtered_2", 
     filter: "message CONTAINS 'timeout'", result: "matches"},
    {type: "sort", input: "matches", by: "timestamp DESC"},
    {type: "limit", input: "sorted", n: 1000}
  ]
  
  // Execution stats
  stats: {
    segments_considered: 2400,
    segments_after_index: 87,
    bytes_scanned: 340MB,
    lines_matched: 2847,
    execution_time: 2.3s
  }
}
```

### Algorithms

```
QUERY EXECUTION:

  function execute_query(query):
    // Step 1: Parse query
    parsed = parse_query(query)
    // {field_filters: [{service, =, payments}, {level, =, ERROR}],
    //  text_filter: "*timeout*", time_range: [T1, T2], limit: 1000}
    
    // Step 2: Catalog lookup — which segments overlap the time range?
    candidate_segments = catalog.find_segments(
      time_range = parsed.time_range,
      partition = infer_partition(parsed)  // If service filter → narrow partitions
    )
    // Typical: 2,400 segments for 1 hour of data
    
    // Step 3: Index pruning — which segments contain matching values?
    for filter in parsed.field_filters:
      candidate_segments = index.lookup(
        field = filter.field,
        value = filter.value,
        segments = candidate_segments
      )
    // After index: 87 segments (96% pruned)
    
    // Step 4: Scatter — send scan requests to storage nodes
    node_requests = group_by_storage_node(candidate_segments)
    futures = []
    for node, segments in node_requests:
      futures.append(node.scan(segments, parsed.text_filter, parsed.limit))
    
    // Step 5: Gather — collect and merge results
    all_results = []
    for future in futures:
      results = future.get(timeout=15s)
      all_results.extend(results)
    
    // Step 6: Sort and limit
    all_results.sort(by=timestamp, order=DESC)
    return all_results[:parsed.limit]

INDEX LOOKUP (inverted index):

  function index_lookup(field, value, candidate_segments):
    // Inverted index maps: (field, value) → set of segment_ids
    matching_segment_ids = inverted_index.get(field, value)
    return candidate_segments.intersect(matching_segment_ids)

SEGMENT SCAN (on storage node):

  function scan_segment(segment_id, text_filter, limit):
    segment = storage.read(segment_id)
    // Segment is columnar: Read only needed columns
    
    matches = []
    // Read the message column (for text filter)
    message_column = segment.read_column("message")
    // Read timestamp column (for sorting)
    timestamp_column = segment.read_column("timestamp")
    
    for i in range(segment.line_count):
      if text_filter.matches(message_column[i]):
        matches.append(reconstruct_line(segment, i))
        if len(matches) >= limit:
          break
    
    return matches
```

### Failure Behavior

```
QUERY ENGINE INSTANCE CRASH:
  → Client query fails → client retries on another instance
  → No state lost (query engine is stateless)
  → Impact: ~5 second delay for that one query

STORAGE NODE SLOW / UNREACHABLE:
  → Scatter request to that node times out (15 second timeout)
  → Query returns partial results (missing data from unreachable node)
  → Response includes: "WARNING: Partial results. Node storage-12 unreachable."
  → ALTERNATIVE: Query engine reads from replica node (if available)

QUERY OF DEATH (scans too much data):
  → Per-query byte scan limit: 1TB
  → Per-query time limit: 60 seconds
  → If exceeded: Query killed. Return partial results + error.
  → Client: "Query exceeded scan limit. Add more filters or narrow time range."
```

---

# Part 7: Data Model & Storage Decisions

## What Data Is Stored

```
1. LOG SEGMENTS (hot, dominant volume)
   → Columnar format: Each field stored as a separate column
   → Columns: timestamp, service, level, host, trace_id, message, metadata
   → Volume: ~67 new segments/sec (2M lines / 30sec flush / 1000 lines per segment)
   → Segment size: ~64MB compressed (after 30 seconds of buffering)
   → Total hot: 36TB compressed (7 days × 8.6TB/day × some overhead)

2. INVERTED INDEX (per segment, co-located)
   → Maps: (field, value) → list of line offsets within segment
   → Indexed fields: service, level, host, trace_id, user_id
   → Size: ~5% of segment size = ~1.8TB for hot tier
   → Updated: On segment creation (immutable after flush)

3. SEGMENT CATALOG (metadata, small)
   → One entry per segment: {segment_id, time_range, tier, node, size, ...}
   → Volume: ~500K active segments × ~500 bytes = ~250MB
   → Updated: On segment create, merge, transition, delete

4. WAL (write-ahead log, transient)
   → Durability for log lines between receipt and segment flush
   → Volume: ~2GB per ingestion instance (30 seconds of data)
   → Retention: Truncated after segment flush
   → Total: 50 instances × 2GB = ~100GB

5. ALERT RULES (configuration, small)
   → 5,000 rules × ~2KB = ~10MB
   → Updated: ~50 changes/day

6. TENANT CONFIGURATION (small)
   → 200 tenants × ~5KB = ~1MB
   → Quotas, retention policies, access controls
```

## How Data Is Keyed

```
LOG SEGMENTS:
  Partition key: hash(service + host) → partition (100 partitions)
  → WHY service+host: Logs from the same service instance are co-located.
    "Show me all logs from payments on host-7" scans one partition.
  Sort key: timestamp (within a segment, lines are time-ordered)
  → WHY: Time-range queries (the most common pattern) are sequential reads.

INVERTED INDEX:
  Key: (field_name, field_value) → set of (segment_id, offsets)
  → Example: ("service", "payments") → [(seg_001, [0,47,102]), (seg_002, [0,15])]
  → Partitioned: Same as segments (index is co-located with segments)

SEGMENT CATALOG:
  Primary key: segment_id
  Secondary indexes: time_range, partition, tier, storage_node
  → Queries: "All segments in partition P with time range overlapping [T1,T2]"
```

## How Data Is Partitioned

```
SEGMENTS (primary partitioning):
  Strategy: Hash(service + host) → partition
  Partitions: 100 (balanced across storage nodes)
  → Each partition: ~1% of total log volume
  → Storage nodes: 50 nodes, each hosting 2 partitions
  → Replication: Each partition replicated on 3 nodes (hot), 2 nodes (warm)

  WHY service+host (not time):
  → Time-based partitioning creates hot partitions (current time bucket gets
    all writes). hash(service+host) distributes writes evenly.
  → Time-range queries span ALL partitions → scatter-gather required anyway.
  → Service-based co-location: "All logs for service X" reads fewer partitions.

SEGMENTS (time-based sub-partitioning within a partition):
  → Within each partition: Segments are organized by time
  → Directory structure: /partition_07/2024-01-15/hour_10/seg_12345.col
  → Time-based pruning: Query for "last 1 hour" skips all older directories

INVERTED INDEX:
  → Co-located with segments (same partition, same storage node)
  → Per-segment index: Small, fast to load
  → Global index: NOT maintained (too expensive at this write rate)
  → Query engine: Reads segment-level indexes, merges results

COLD STORAGE:
  → Partitioned by: tenant + date (daily objects)
  → Object key: /tenant_payments/2024-01-15/partition_07/seg_12345.col.zst
  → Enables: Per-tenant retention policies, per-date expiry
```

## Retention Policies

```
TIER            │ DURATION     │ STORAGE    │ INDEX    │ QUERY SLA
────────────────┼──────────────┼────────────┼──────────┼──────────────
Hot (SSD)       │ 0-7 days     │ 3× replicated│ Full    │ < 5 seconds
Warm (HDD)      │ 7-30 days    │ 2× or EC   │ Sparse  │ < 30 seconds
Cold (Obj Store)│ 30-365 days  │ 11 nines   │ Metadata│ < 5 minutes
Archive         │ 365+ days    │ Deep archive│ None    │ Hours (restore)

TRANSITION RULES:
  → Hot → Warm: After 7 days. Background job moves segments.
    Re-compresses with higher ratio (Zstd level 15 vs LZ4).
    Thins index (keep service + level, drop trace_id + host).
  → Warm → Cold: After 30 days. Archive to object storage.
    Only segment metadata in catalog. Must restore to query.
  → Cold → Delete: After 365 days. Object deleted.
    Catalog entry removed.

OVERRIDES:
  → Compliance-tagged logs: Extended to 7 years (cold + archive)
  → Post-mortem hold: Manual retention extension for specific time ranges
  → Per-tenant override: ML team gets 3 days hot (verbose, low value)
    Security team gets 90 days hot (audit, high value)
```

## Schema Evolution

```
LOG LINE EVOLUTION:
  V1: {timestamp, message}
  V2: + {service, level, host}   (structured logging)
  V3: + {trace_id, span_id}     (distributed tracing)
  V4: + {user_id, request_id}   (request correlation)
  V5: + {deployment_id, canary}  (deployment awareness)

  Strategy: Schema-on-read. Log lines are stored with whatever fields
  are present. Old logs without trace_id: trace_id=null in queries.
  New fields are automatically detected and added to the schema registry.

SEGMENT FORMAT EVOLUTION:
  V1: Line-oriented (newline-delimited JSON)
  V2: Columnar (separate column per field, better compression)
  V3: Columnar + dictionary encoding (repeated values stored once)

  Strategy: Segment header includes format version. Query engine
  supports reading all versions. Old segments are NOT re-encoded
  (too expensive). They age out through retention naturally.

INDEX EVOLUTION:
  Adding a new indexed field (e.g., deployment_id):
  → New segments: Index includes deployment_id immediately
  → Existing segments: NOT re-indexed (too expensive)
  → Impact: Queries on deployment_id only use index for recent segments.
    Older segments: Fall back to segment scan (slower but correct).
  → Re-indexing: Optional background job for high-value fields.
```

## Why Other Data Models Were Rejected

```
ELASTICSEARCH (inverted index for everything):
  ✓ Full-text search with scoring and relevance ranking
  ✗ 2× storage overhead for full inverted index at log scale
  ✗ Segment merge storms under high write throughput (2M lines/sec)
  ✗ JVM GC pauses cause query latency spikes
  ✗ No native tiered storage (hot/warm/cold requires manual management)
  
  WHY REJECTED: Elasticsearch is designed for search workloads (moderate write,
  heavy read). Log systems are the opposite (heavy write, sparse read).
  The full inverted index doubles storage cost for fields that are rarely
  searched (message body). Columnar storage with selective indexing is
  10× more cost-efficient.

RELATIONAL DATABASE:
  ✗ 2M inserts/sec exceeds any single relational database
  ✗ Full-text search on message body is slow without custom indexing
  ✗ Row-oriented storage is 5× less space-efficient than columnar for logs
  ✗ No native time-series optimization (time-based partitioning is manual)
  
  WHY REJECTED: Logs are append-only, time-series, semi-structured data.
  Relational databases are designed for transactional CRUD on structured data.

RAW FILES ON DISTRIBUTED FILESYSTEM:
  ✓ Simple: Write files, grep to search
  ✗ grep across 36TB takes hours, not seconds
  ✗ No indexing → every query is a full scan
  ✗ No compression optimization → 10× more storage
  ✗ No tiered retention → manual management
  
  WHY REJECTED: Works for 10GB of logs. At 36TB, full scan is not a query
  strategy. Indexing is required for interactive search.
```

---

# Part 8: Consistency, Concurrency & Ordering

## Strong vs Eventual Consistency

```
INGESTION: Eventually consistent (seconds)
  → Log line emitted → agent buffers → shipped → ingested → segment flushed
  → Searchable after segment flush: ~30 seconds from emission
  → During those 30 seconds: Line exists in WAL but not in search index
  → ACCEPTABLE: 30-second staleness is fine for search.
    Live tailing provides real-time visibility (separate pipeline).

SEGMENT CATALOG: Strongly consistent for writes, eventually consistent for reads
  → New segment registered: Catalog write is synchronous.
  → Query engine reads catalog: May see segment registered 1-2 seconds ago.
  → Impact: Extremely recent segments may not appear in query results.
  → ACCEPTABLE: The WAL ensures durability. The 1-2 second catalog lag
    is within the 30-second ingestion-to-searchable budget.

REPLICATION: Synchronous write to primary, async replication to followers
  → Hot tier: Write to primary replica, acknowledge to ingestion.
    Async replicate to 2 followers (< 5 seconds lag).
  → If primary fails before replication: Up to 5 seconds of segments
    on that node are at risk. WAL on ingestion allows replay.

TIER TRANSITIONS: Atomic (hot → warm)
  → Data written to warm FIRST. Catalog updated (warm available).
  → Then: Hot copy deleted. If deletion fails → data in both tiers
    (wastes space but doesn't lose data).
  → NEVER: Delete from hot before confirming warm write.

SEARCH RESULTS: Snapshot consistency
  → Query sees a consistent snapshot of segment catalog at query start time.
  → Segments created during query execution: NOT included in results.
  → Segments deleted during query execution: Already read or skipped.
  → No "torn reads" — each segment is read atomically.
```

## Race Conditions

```
RACE 1: Segment flush during query

  Timeline:
    T=0: Query engine reads catalog. Segment S1 exists (hot, node-7).
    T=1: Ingestion flushes new segment S2 to node-7. S2 added to catalog.
    T=2: Query engine scans S1. Does NOT see S2 (not in query's catalog snapshot).
    T=3: Query returns results. Missing lines from S2.
  → Impact: Most recent ~30 seconds of logs may not appear in query.
  → ACCEPTABLE: Within the 30-second ingestion-to-searchable window.

RACE 2: Tier transition during query

  Timeline:
    T=0: Query starts. Segment S1 is in hot tier on node-7.
    T=1: Background job transitions S1 to warm tier on node-15.
    T=2: Query tries to read S1 from node-7 → segment not found.
  → Impact: Query gets an error for one segment.
  → MITIGATION: Query engine retries on warm tier (catalog shows both
    tiers during transition). Double-check: Read from warm if hot fails.

RACE 3: Agent ships duplicate batch (retry after timeout)

  Timeline:
    T=0: Agent ships batch to ingestion instance A. Timeout (network slow).
    T=1: Agent retries on ingestion instance B. Batch accepted.
    T=2: Instance A actually received the batch (slow, but received).
    → Same log lines ingested twice (by A and B).
  → Impact: Duplicate log lines in storage.
  → MITIGATION: Optional dedup at query time (by log_id or content hash).
  → WHY NOT DEDUP AT INGESTION: Dedup requires checking every line against
    existing data → adds latency and state to the ingestion path.
    At-least-once is acceptable for logs.

RACE 4: Two ingestion instances flush segments for same partition simultaneously

  Timeline:
    T=0: Instance A and B both receive logs for partition 7.
    T=1: Both flush segments at the same time → two segments for same
         time range in the same partition.
  → Impact: Overlapping segments. Query returns correct results (both
    segments scanned). Slightly more storage used.
  → MITIGATION: Background compaction merges overlapping segments.
```

## Idempotency

```
LOG INGESTION: Idempotent at batch level (with retry)
  → Same batch shipped twice → stored twice (at-least-once)
  → Dedup not enforced at ingestion (too expensive for write throughput)
  → Dedup available at query time (by log_id if present)

SEGMENT CREATION: Idempotent (segment_id is unique)
  → If segment flush is retried → same segment_id → upsert (no duplicate)

TIER TRANSITION: Idempotent
  → Transitioning same segment twice: Second transition is a no-op
    (already in target tier, catalog already updated)

SEGMENT DELETION: Idempotent
  → Deleting a segment that doesn't exist: No-op
```

## Ordering Guarantees

```
WITHIN A HOST: Ordered
  → Agent reads log lines in order → ships in order → stored in order
  → Lines from the same host appear in emission order within a segment

ACROSS HOSTS: No global ordering guarantee
  → Host A's log at T=10:00:00.001 may appear AFTER Host B's log at T=10:00:00.002
  → Clock skew between hosts: ±100ms typical, ±seconds rare
  → MITIGATION: Display sorted by ingest_timestamp (server-assigned, reliable)
    or source_timestamp (user-visible, may have skew)

ACROSS PARTITIONS: No ordering guarantee
  → Query merges results from multiple partitions
  → Results sorted by timestamp during merge (query engine)
  → Ties broken by: ingest_timestamp, then segment_id, then offset
```

## Clock Assumptions

```
HOST CLOCKS: NTP-synchronized, ±100ms typical
  → Source timestamp in log line: From host clock
  → May be skewed relative to other hosts
  → MITIGATION: Agent also captures ingest_timestamp from server

SERVER CLOCKS (ingestion): NTP-synchronized, ±10ms
  → Ingest timestamp: Reliable, used for time-range queries
  → All ingestion instances use server clock for ingest_timestamp

SEGMENT TIME RANGES: Based on ingest_timestamp
  → Segment time range: [min(ingest_timestamp), max(ingest_timestamp)] of lines
  → Query time-range pruning uses these ranges → accurate with server clocks

CLIENT CLOCKS (in mobile/browser logs): Unreliable
  → Client logs may have timestamps hours off
  → MITIGATION: Store both client_timestamp and ingest_timestamp
  → Query on ingest_timestamp for reliability
```

---

# Part 9: Failure Modes & Degradation (MANDATORY)

## Partial Failures

```
FAILURE 1: Single storage node down (hot tier)
  SYMPTOM: Read/write failures for partitions on that node
  IMPACT:
  → Writes: Ingestion fails for those partitions → WAL accumulates
  → Reads: Queries for data on that node → read from replica
  → 2 of 50 storage nodes host each partition → 1 node down = read from other
  DETECTION: Storage node health check fails
  RESPONSE:
  → Read: Automatic failover to replica node
  → Write: Ingestion redirects to replica for new segments
  → Recovery: When node returns, rebalance and catch up from replicas
  BLAST RADIUS: 2% of hot data affected (1 of 50 nodes). Read latency may
  increase 2× for those partitions (reading from non-local replica).

FAILURE 2: Ingestion pipeline overwhelmed (burst)
  SYMPTOM: Consumer lag growing, agents reporting send failures
  IMPACT:
  → New logs delayed (not lost — buffered by agents)
  → Search results stale (recent logs not yet indexed)
  → Live tailing: Delayed or missing recent logs
  DETECTION: Ingestion lag metric > threshold (> 5 minutes)
  RESPONSE:
  → Auto-scale ingestion instances (add capacity within 2 minutes)
  → If sustained: Enforce tenant quotas more aggressively
  → Agents: Buffer on disk, backpressure on low-priority logs
  BLAST RADIUS: All tenants experience search staleness. No data loss
  (agents buffer). Live tailing degrades.

FAILURE 3: Query engine overloaded (incident search storm)
  SYMPTOM: Query latency > 30 seconds, timeouts
  IMPACT:
  → Engineers can't search logs during an active incident
  → THIS IS THE WORST FAILURE MODE: Log search is needed most when
    the system is under the most stress (incidents = high search + high logs)
  DETECTION: Query latency P95 > threshold, queue depth growing
  RESPONSE:
  → Query result caching (cache common incident queries)
  → Auto-scale query instances (30 → 300 in 2 minutes)
  → Query prioritization: Admin queries get priority over dashboard queries
  → Load shedding: Kill queries running > 60 seconds, reject queries
    scanning > 1TB
  BLAST RADIUS: All users experience degraded search. Mitigation: Caching
  reduces effective load by 50% during incidents (same queries by many people).

FAILURE 4: Segment catalog unavailable
  SYMPTOM: Query engine can't look up which segments to scan
  IMPACT:
  → All searches fail (query engine doesn't know where data is)
  → Ingestion continues (writes to WAL and storage, but can't register
    new segments in catalog)
  DETECTION: Catalog health check fails
  RESPONSE:
  → Catalog replicated 3× — failover to replica
  → If all replicas down: Emergency mode — query engine falls back to
    scanning all segments on all storage nodes (slow but functional)
  BLAST RADIUS: Total search outage until catalog recovers. Ingestion
  continues (data not lost, but not searchable until catalog returns).
```

## Slow Dependencies

```
SLOW DEPENDENCY 1: Object storage (affects cold tier queries)
  Normal: Cold segment retrieval in 5 seconds
  Slow: Retrieval takes 60 seconds
  IMPACT: Cold tier queries take minutes instead of seconds
  RESPONSE: Increase cold query timeout. Warn user: "Cold data query in progress."
  → Hot and warm queries: UNAFFECTED (different storage backend)

SLOW DEPENDENCY 2: Network between agents and ingestion
  Normal: Agent batch shipping in 50ms
  Slow: 500ms (congestion, cross-AZ)
  IMPACT: Agent disk buffer grows. Ingestion latency increases.
  RESPONSE: Agents increase batch size (fewer, larger shipments).
  → If persistent: Route agents to closer ingestion endpoint.

SLOW DEPENDENCY 3: Storage disk I/O (affects segment flush)
  Normal: Segment flush in 200ms
  Slow: 2 seconds (disk saturation from compaction + queries)
  IMPACT: Segment buffer grows in memory → increased memory usage on
  ingestion instances → potential OOM
  RESPONSE: Rate-limit background compaction during peak ingestion.
  Compaction priority < ingestion priority.
```

## Retry Storms

```
SCENARIO: Ingestion service restarts → agents retry all buffered batches

  Timeline:
  T=0: Ingestion service rolling restart (deployment).
  T=1: 500K agents detect connection failure. Start retrying.
  T=2: Ingestion service comes back. 500K agents send batches simultaneously.
  T=3: Ingestion receives 10× normal batch rate. Overwhelmed.
  T=4: Ingestion starts dropping batches → agents retry → more load.

PREVENTION:
  1. AGENT JITTERED RETRY
     → First retry: Random delay 1-5 seconds (not all at once)
     → Second retry: 5-15 seconds. Third: 15-60 seconds.
     → Jitter spreads 500K retries over 60 seconds instead of 1 second.

  2. AGENT BATCH COALESCING
     → During retry period: Continue collecting logs into larger batches
     → Ship one large batch (5,000 lines) instead of five small ones (1,000)
     → Reduces QPS to ingestion by 5× during recovery

  3. INGESTION ADMISSION CONTROL
     → If queue depth > threshold: Reject new batches with "retry later"
     → Rejected batches stay in agent disk buffer (not lost)
     → Gradually admit as capacity frees up

  4. ROLLING RESTART STRATEGY
     → Restart ingestion instances one at a time (not all at once)
     → Each instance handles ~40K lines/sec → loss of one instance:
       2% of capacity. Agents redistribute to other instances.
```

## Data Corruption

```
SCENARIO 1: Segment written with corrupt data (disk error)
  CAUSE: Bit flip during segment write → checksum mismatch on read
  DETECTION: Segment read → checksum validation fails → segment marked corrupt
  IMPACT: Lines in that segment (~30 seconds of data for one partition) unreadable
  RECOVERY: If segment was replicated: Read from replica.
  If all replicas corrupt (extremely unlikely): Data lost for that 30-second window.
  PREVENTION: Checksums per segment, per column, per block.

SCENARIO 2: Inverted index drift (index says segment has "payments" but it doesn't)
  CAUSE: Bug in index building during segment flush
  IMPACT: Index returns false positives (segments scanned but no matches found)
  → Query works correctly but slower (unnecessary scans)
  DETECTION: Query stats: "Index returned 200 segments, only 50 had matches"
  → High false positive rate → investigate index building.
  PREVENTION: Index validation during compaction (rebuild index, compare).

SCENARIO 3: Agent mislabels host metadata
  CAUSE: Agent on host A sends logs with hostname=B (config error)
  IMPACT: Logs attributed to wrong host. Debug workflow broken.
  DETECTION: Duplicate hostnames in metadata. IP address doesn't match hostname.
  PREVENTION: Agent derives hostname from OS, not config file.
  Cross-validation: hostname + IP must match known inventory.
```

## Control-Plane Failures

```
CATALOG CORRUPTION:
  → Segment exists in storage but not in catalog → invisible to queries
  → Segment in catalog but deleted from storage → query fails for that segment
  DETECTION: Reconciliation job (daily): Compare catalog entries vs storage contents
  RESPONSE: Add missing entries, remove orphaned entries
  PREVENTION: Catalog writes are synchronous with segment writes.
  Delete from catalog AFTER confirming storage deletion.

QUOTA SERVICE DOWN:
  → Tenant quotas not enforced → all tenants can ingest unlimited
  → Risk: One tenant floods the pipeline
  RESPONSE: Fail-closed — if quota service unreachable, use LAST KNOWN quotas.
  Conservative default: If no quota info, apply default limit.
```

## Blast Radius Analysis

```
COMPONENT FAILURE        │ BLAST RADIUS                │ USER-VISIBLE IMPACT
─────────────────────────┼─────────────────────────────┼─────────────────────
1 storage node (of 50)   │ 2% of partitions affected   │ Queries slower for
                         │ Replicas serve reads         │ those partitions
All ingestion down       │ All new logs buffered at     │ Search shows stale
                         │ agents (not lost)            │ data (30min+)
Query engine overloaded  │ All search users affected    │ Search slow/timeout
Segment catalog down     │ All search fails             │ Complete search outage
Agent crash (1 host)     │ 1 of 500K hosts affected     │ Invisible to users
Network partition (1 AZ) │ ~20% of hosts can't ship     │ 20% of recent logs
                         │ logs (buffered locally)      │ delayed
Cold storage unavailable │ Historical queries fail      │ No impact on recent
                         │                              │ log search
```

## Failure Timeline Walkthrough

```
SCENARIO: Storage node failure during a production incident that's already
generating 5× normal log volume and 10× search traffic.

T=0:00  Production incident begins. Database connection pool exhausted.
        50 services start logging "connection refused" at ERROR level.
        Log volume: 2M/sec → 10M/sec (5× burst).

T=0:02  Engineers start searching: "level=ERROR AND time=[last 5min]"
        Search QPS: 500 → 3,000 (engineers + automated alerts).

T=0:05  Storage node storage-12 fails (disk array failure).
        storage-12 hosted 2 of 100 partitions (partitions 23, 67).
        
T=0:05  IMMEDIATE IMPACT:
        → Writes to partitions 23, 67: Fail on primary → redirect to replicas
        → Reads: Automatic failover to replica nodes
        → Ingestion instances: Detect write failure, buffer for those partitions
          temporarily in WAL, retry on replica

T=0:06  Query engine: 3,000 QPS. Some queries touch partitions 23, 67.
        → Replica reads: 2× latency (reading from non-local replica)
        → Queries touching only healthy partitions: Unaffected

T=0:08  Ingestion burst: 10M lines/sec exceeds pipeline capacity (designed for 6M).
        → Ingestion lag growing: 1 minute → 3 minutes → 5 minutes
        → Most recent 5 minutes of logs: NOT yet searchable
        → Engineers searching: "Why am I not seeing the latest errors?"

T=0:10  Auto-scaling kicks in:
        → Ingestion instances: 50 → 80 (absorb burst)
        → Query instances: 30 → 200 (absorb search storm)
        → Query cache: 40% hit rate (many engineers search same thing)

T=0:15  Pipeline catches up. Ingestion lag: 1 minute (acceptable).
        Engineers can now search recent logs (with ~1 minute delay).

T=0:20  storage-12 repair underway. Data on storage-12: Safe on replicas.
        No data loss.

T=1:00  storage-12 back online. Rebalance starts.

TOTAL IMPACT:
  → 5 minutes of increased search latency for 2% of partitions
  → 10 minutes of search staleness (ingestion lag) for ALL data
  → 0 log lines lost (agents buffered, WAL preserved)
  → 0 query failures (replica failover worked)

WHAT MADE THIS SURVIVABLE:
  → Storage replication (reads survived node failure)
  → Agent disk buffer (logs survived ingestion lag)
  → Query cache (reduced effective search load by 40%)
  → Auto-scaling (absorbed both ingestion burst and search storm)
  → The worst-case scenario (incident + node failure + burst) was
    designed for, not just the average case.
```

---

# Part 10: Performance Optimization & Hot Paths

## Critical Paths

```
CRITICAL PATH 1: Ingestion (log emission to segment flush)
  Agent → network → ingestion → WAL → segment buffer → segment flush
  TOTAL BUDGET: < 30 seconds (emission to searchable)
  BREAKDOWN:
  → Agent buffer + ship: ~1 second
  → Network transit: ~50ms
  → Ingestion parse + WAL: ~5ms per batch
  → Segment buffer accumulation: up to 30 seconds
  → Segment flush to disk: ~200ms
  → Index build: ~100ms
  → Catalog registration: ~50ms
  BOTTLENECK: Segment buffer time (30 seconds). This is intentional —
  batching improves compression and reduces segment count.

CRITICAL PATH 2: Search query (query to results)
  Parse → catalog → index → scatter → scan → gather → sort → respond
  TOTAL BUDGET: < 5 seconds (hot tier)
  BREAKDOWN:
  → Parse query: ~1ms
  → Catalog lookup: ~10ms (in-memory catalog cache)
  → Index lookup: ~50ms (per field, from SSD-backed index)
  → Scatter to storage nodes: ~10ms (network)
  → Segment scan: 1-3 seconds (dominant cost, I/O-bound)
  → Gather + merge: ~100ms (CPU-bound, sorting)
  → Respond: ~5ms
  BOTTLENECK: Segment scan. Reading and decompressing segments from disk
  is the dominant cost. Index pruning reduces scan volume 10-100×.

CRITICAL PATH 3: Live tailing (log emission to engineer's screen)
  Agent → ingestion → tail fan-out → filter → WebSocket → client
  TOTAL BUDGET: < 2 seconds
  BREAKDOWN:
  → Agent → ingestion: ~1 second (batching delay)
  → Ingestion → tail fan-out: ~10ms (in-process fork)
  → Filter evaluation: ~1ms per line per session
  → WebSocket push: ~50ms
  BOTTLENECK: Agent batching (1 second). For lower tailing latency,
  agent can use a smaller batch size for tail-eligible lines (100ms).
```

## Caching Strategies

```
CACHE 1: Segment catalog (in-memory on query engines)
  WHAT: Full catalog of all segments (250MB)
  STRATEGY: Loaded at startup, refreshed every 5 seconds (incremental)
  HIT RATE: 100% (always cached, always fresh within 5 seconds)
  WHY: Catalog lookup is on every query path. 10ms from memory vs 100ms from DB.

CACHE 2: Query result cache (on query engine instances)
  WHAT: Recent query results (keyed by query hash)
  STRATEGY: LRU cache, 10GB per instance, TTL=30 seconds
  HIT RATE: 10% normal, 40-60% during incidents (same queries by many people)
  WHY: During incidents, 200 engineers search for the same service+error.
  Cache converts 200 identical queries into 1 scan + 199 cache hits.

CACHE 3: Hot segment cache (on storage nodes)
  WHAT: Frequently accessed segments cached in page cache / SSD cache
  STRATEGY: OS page cache. Most recent segments are "naturally hot" because
  they're written recently and queried frequently.
  HIT RATE: ~60% for queries in the last 1 hour (data still in page cache)
  WHY: Avoids disk read for the most commonly queried data.

CACHE 4: Inverted index cache (on storage nodes)
  WHAT: Inverted index for recent segments
  STRATEGY: Loaded into memory when segment is flushed (already in memory)
  → Recent segments' index: In memory. Older segments' index: On SSD.
  HIT RATE: ~80% (most queries target recent data)
  WHY: Index lookup from memory: ~1ms. From SSD: ~10ms. From HDD: ~50ms.
```

## Precomputation vs Runtime Work

```
PRECOMPUTED:
  → Inverted index: Built at segment flush time (not at query time)
  → Column statistics: Min/max timestamp per segment (for range pruning)
  → Bloom filters: Per-segment bloom filter for high-cardinality fields
    (trace_id). Query engine checks bloom filter before scanning segment.
    False positive rate: 1% → 99% of non-matching segments skipped instantly.
  → Aggregation rollups: Pre-aggregated counts by (service, level, minute)
    for dashboard queries (avoid scanning raw segments for "count errors
    by service, last 24h")

RUNTIME (cannot precompute):
  → Free-text search in message body (unpredictable query terms)
  → Complex boolean queries (AND/OR combinations of field filters)
  → Context queries (lines before/after a specific log line)

THE CRITICAL OPTIMIZATION:
  Bloom filters for trace_id:
  → Without bloom filter: Query for trace_id=abc123 scans ALL segments
    in time range. Each segment: Decompress + scan. 2,400 segments × 10ms = 24s.
  → With bloom filter: Check bloom filter for each segment. 99% say "definitely
    not here." Only 24 segments scanned. 24 × 10ms = 240ms. 100× faster.
  → Cost: ~1% of segment size. ROI: 100× query speedup for trace_id queries.
```

## Backpressure

```
BACKPRESSURE POINT 1: Agents → Ingestion (network boundary)
  SIGNAL: Ingestion returns HTTP 429 (rate limit) or TCP connection refused
  RESPONSE:
  → Agent: Buffer to disk. Increase batch size. Reduce shipping frequency.
  → Agent: If disk buffer > 80%: Start dropping DEBUG logs.
  → Agent: NEVER drops ERROR/WARN.

BACKPRESSURE POINT 2: Ingestion → Storage (disk I/O boundary)
  SIGNAL: Segment flush takes > 1 second (normally 200ms)
  RESPONSE:
  → Ingestion: Increase segment buffer size (accumulate more before flushing)
  → Storage: Rate-limit compaction (free disk I/O for ingestion)
  → If persistent: Add storage nodes (horizontal scaling)

BACKPRESSURE POINT 3: Query engine → Storage (read I/O boundary)
  SIGNAL: Segment scan takes > 5 seconds per segment (normally 100ms)
  RESPONSE:
  → Query engine: Increase timeout. Return partial results with warning.
  → Storage: Prioritize query reads over compaction reads.
  → If persistent: Query engine uses replica nodes (spread read load)
```

## Load Shedding

```
LOAD SHEDDING HIERARCHY:

  1. Shed aggregation rollup computation (defer to next cycle)
     → Dashboards show slightly stale data. No impact on search.

  2. Shed cold tier queries (return "temporarily unavailable")
     → Historical queries fail. Recent search unaffected.

  3. Shed compaction (background merging of segments)
     → Segment count increases. Query slightly slower. Ingestion unaffected.

  4. Reduce query scan limit (1TB → 500GB per query)
     → Broad queries fail. Narrow queries work.

  5. Shed warm tier queries (only hot tier available)
     → Last 7 days searchable. Older data unavailable.

  6. NEVER shed hot tier search
     → Hot tier search is the core product. Used during incidents.
     → If hot search fails during an incident, engineers are blind.

  7. NEVER shed ingestion
     → Lost logs are lost forever. Even degraded ingestion (sampling
       DEBUG, dropping INFO) is better than stopped ingestion.
```

## Why Some Optimizations Are Intentionally NOT Done

```
"INDEX THE MESSAGE BODY (full-text inverted index)"
  → Full inverted index on free-text message body: Every unique word indexed
  → WHY NOT: Message body is high-cardinality (millions of unique words).
    Full inverted index doubles storage size (~36TB → ~72TB for hot tier).
    Marginal benefit: Free-text search is used in <5% of queries.
    Bloom filter + segment scan is sufficient for occasional free-text search.

"DEDUPLICATE LOGS AT INGESTION"
  → Check every log line against recent lines: If duplicate → discard
  → WHY NOT: At 2M lines/sec, dedup requires maintaining state for every
    recent line. State size: 60 seconds × 2M lines × 32B hash = ~3.8GB.
    Lookup cost: ~0.5ms per line → 1,000 CPU-seconds/sec → doubles ingestion cost.
    Duplicates are rare (<1% from agent retries). Not worth the cost.

"COMPRESS SEGMENTS WITH HIGHEST COMPRESSION RATIO"
  → Use Zstd level 22 (maximum compression) for all segments
  → WHY NOT: Level 22 compression is 10× slower than level 3. At 2M lines/sec,
    compression is on the critical path. Level 3 gives 8:1 ratio. Level 22
    gives 12:1. The 50% compression improvement doesn't justify 10× CPU cost.
  → Warm/cold tiers: Higher compression IS used (not on critical path).
```

---

# Part 11: Cost & Efficiency

## Major Cost Drivers

```
1. STORAGE (dominant cost: ~65% of total)

   HOT TIER (SSD):
   36TB SSD × $0.10/GB/month = $3,600/month
   × 3 replicas = $10,800/month
   + Index storage (~1.8TB SSD): $540/month (shared with segment replicas)
   HOT TOTAL: ~$11,300/month

   WARM TIER (HDD):
   72TB HDD × $0.02/GB/month = $1,440/month
   × 2 replicas = $2,880/month
   WARM TOTAL: ~$2,900/month

   COLD TIER (Object Storage):
   900TB × $0.004/GB/month = $3,600/month
   COLD TOTAL: ~$3,600/month

   TOTAL STORAGE: ~$17,800/month

2. COMPUTE (ingestion + query + background: ~25% of total)

   INGESTION: 50 instances × $0.15/hr = $7.50/hr = $5,400/month
   QUERY ENGINE: 30 instances (normal) × $0.15/hr = $3,240/month
   (Burst: 300 instances for hours during incidents → +$2,000/month amortized)
   TAIL + ALERTING: 15 instances = $1,620/month
   COMPACTION / TRANSITION: 10 instances = $1,080/month
   TOTAL COMPUTE: ~$13,300/month

3. NETWORK (agent → ingestion: ~10% of total)
   100 MB/sec sustained = 259 TB/month
   Cross-AZ: ~30% of traffic = 78 TB × $0.01/GB = $780/month
   Cross-region: ~5% = 13 TB × $0.02/GB = $260/month
   TOTAL NETWORK: ~$1,000/month

TOTAL MONTHLY COST:
  Storage:  $17,800  (55%)
  Compute:  $13,300  (41%)
  Network:  $1,000   (3%)
  INFRASTRUCTURE TOTAL: ~$32,100/month

KEY INSIGHT: Storage dominates. Hot tier SSD is the most expensive
component ($11K/month). Reducing hot retention from 7 days to 3 days
saves $6K/month. But: 3 days may not be enough for post-mortem analysis
(incidents can take 3+ days to fully investigate).
```

## How Cost Scales with Traffic

```
LINEAR SCALING:
  → Storage: Proportional to log volume × retention
  → Ingestion compute: Proportional to log volume
  → Network: Proportional to log volume

SUBLINEAR SCALING:
  → Query compute: Grows with query QPS, NOT with log volume
    (index pruning keeps scan volume bounded as data grows)
  → Segment catalog: Grows with segment count, NOT with total data
  → Alerting: Grows with rule count, NOT with log volume

COST SCALING INSIGHT:
  Doubling log volume (2M → 4M lines/sec):
  → Storage cost doubles ($17.8K → $35.6K)
  → Ingestion compute doubles ($5.4K → $10.8K)
  → Query compute: Unchanged (if query QPS stays constant)
  → TOTAL: ~$32K → ~$50K (56% increase, not 100%, because query is sublinear)
```

## Cost-Aware Redesign

```
IF STORAGE COST GROWS TOO FAST:

  1. Reduce hot tier retention (7 days → 3 days)
     → Saves: 57% of hot SSD cost = ~$6.4K/month
     → Trade-off: 3-7 day old data has 30-second query SLA instead of 5-second

  2. Better compression (LZ4 → Zstd level 3 on hot tier)
     → 8:1 → 12:1 compression = 33% less storage
     → Saves: ~$5.9K/month across all tiers
     → Trade-off: 30% more CPU for compression (add 5 ingestion instances: +$540)

  3. Per-tenant retention policies
     → ML team (verbose, low-value logs): 3 days hot, 14 days total
     → Security team (audit logs): 30 days hot, 365 days total
     → Default team: 7 days hot, 90 days total
     → Saves: 30-50% of storage (tenant-appropriate retention)

  4. Log sampling for DEBUG level
     → Store 10% of DEBUG logs (sampled at agent level)
     → DEBUG is typically 60% of volume but < 5% of search value
     → Saves: ~50% of total storage cost

IF QUERY COST GROWS TOO FAST:

  1. Better indexing (add bloom filters for trace_id and user_id)
     → Reduces scan volume 10× for trace queries
     → Saves compute by scanning fewer segments

  2. Aggressive caching (increase cache TTL from 30s to 5 min)
     → Saves: ~30% of query compute during incidents
     → Trade-off: Results may be up to 5 minutes stale

WHAT A STAFF ENGINEER INTENTIONALLY DOES NOT BUILD:
  → Custom storage engine (use existing columnar storage)
  → Real-time indexing on all fields (index only high-value fields)
  → Per-line deduplication (too expensive, duplicates are rare)
  → ML-based log compression (marginal gains, high complexity)
```

---

# Part 12: Multi-Region & Global Considerations

## Data Locality

```
LOG DATA: Region-local (not replicated globally)
  → Logs generated in US-East → stored in US-East
  → Logs generated in EU-West → stored in EU-West
  → WHY: Log volume (86TB/day raw) is too large for cross-region replication.
    Cross-region transfer: 86TB/day × $0.02/GB = $1,720/day = $51,600/month.
    NOT worth it.

SEGMENT CATALOG: Regionally independent
  → Each region has its own catalog for its own segments
  → Cross-region search: Query sent to each region, results merged

CONFIGURATION: Globally replicated
  → Tenant configs, alert rules, retention policies: Small (~10MB)
  → Replicated to all regions for consistent behavior
  → Config change in any region → propagated globally in < 30 seconds

QUERY ENGINE: Region-local with cross-region fan-out
  → Query goes to the nearest region's query engine
  → If query specifies region=all: Fan-out to all regions, merge results
  → Cross-region query latency: +100-200ms per additional region
```

## Replication Strategies

```
WITHIN A REGION:
  → Hot tier: 3× replication across availability zones (within region)
  → Warm tier: 2× replication or erasure coding (6+3)
  → Cold tier: Object storage handles replication internally (11 nines)

ACROSS REGIONS:
  → Log data: NOT replicated (too expensive, see above)
  → Configuration: Async replicated (< 30 seconds lag)
  → Alert rules: Async replicated
  → Segment catalog: NOT replicated (region-local)
```

## Traffic Routing

```
NORMAL: Agents ship to regional ingestion endpoint
  → Agent in US-East → us-east-ingestion.logs.internal
  → Minimizes network latency and cross-region cost

FAILOVER: If regional ingestion is down
  → Agents: Buffer locally (disk buffer, 10GB per host)
  → If down > 1 hour: Route to nearest healthy region (cross-region shipping)
  → Cross-region logs: Stored in the failover region, tagged with origin_region
  → When original region recovers: Logs stay in failover region (no back-migration)
  → Queries for the outage period: Include failover region in search

CROSS-REGION SEARCH:
  → Engineer queries "all regions" → query dispatched to each region
  → Each region executes locally → results streamed back
  → Query engine merges and sorts by timestamp
  → Latency: Max(regional latencies) + 100ms merge overhead
```

## Failure Across Regions

```
SCENARIO: EU-West region completely down

IMPACT:
  → EU-West logs: Not being ingested (hosts buffer locally)
  → EU-West search: Unavailable (storage is region-local)
  → US-East search: Fully operational (independent)
  → Cross-region queries: Return partial results (EU-West missing)

MITIGATION:
  → EU agents: Buffer locally (10GB, ~55 hours of capacity)
  → If extended outage: Route EU agents to US-East ingestion
    (cross-region shipping, higher latency, more cost)
  → EU-West search: Unavailable until region recovers
  → No data loss (agents buffer, or cross-region shipping)

RTO: Ingestion: Immediate (failover to agent buffer or cross-region).
     Search: When region recovers (hours to days).
RPO: 0-1 seconds (agent buffer) to 55 hours (disk buffer capacity).
```

## When Multi-Region Is NOT Worth It

```
CROSS-REGION LOG REPLICATION: NOT worth it.
  → Cost: $51K/month for replication alone (86TB/day cross-region)
  → Benefit: Search availability during full region outage
  → Region outages are rare (< 1/year for major cloud providers)
  → Agent disk buffers provide 55 hours of protection
  → ROI: Negative. $620K/year for protection against < 1 event/year

CROSS-REGION ACTIVE-ACTIVE SEARCH: NOT worth it.
  → Requires replicating all segments to all regions
  → Doubles storage cost for marginal search availability improvement
  → Engineers can search in the region where the incident is occurring

WHAT IS WORTH IT:
  → Cross-region config replication (tiny, cheap, ensures consistency)
  → Cross-region query fan-out (search multiple regions from one query)
  → Agent cross-region failover (if regional ingestion is down)
```

---

# Part 13: Security & Abuse Considerations

## Abuse Vectors

```
VECTOR 1: Log injection (attacker injects crafted log lines)
  ATTACK: Attacker controls input that gets logged. Crafts log line that
  looks like a different service's ERROR log to trigger alerts or confuse
  investigators.
  → Example: HTTP header contains "]\n2024-01-15 10:00:00 AUTH ERROR
    Unauthorized access from admin"
  DEFENSE:
  → Structured logging: Log fields are separate columns, not a single string.
    Injected text stays in the "message" field, doesn't affect "service" or "level."
  → Log line escaping: Newlines in message body are escaped before storage.
  → Source verification: Each log line carries agent_id and host_id (verified
    by mTLS between agent and ingestion). Can't forge source identity.

VECTOR 2: Log flooding (DoS via excessive logging)
  ATTACK: Malicious service intentionally logs millions of lines/sec to
  overwhelm the pipeline and delay other tenants' logs.
  DEFENSE:
  → Per-host rate limit: 1,000 lines/sec max per agent
  → Per-tenant quota: GB/day limit enforced at ingestion
  → Quota breach: DROP excess logs from that tenant, not from others
  → Alert: "Tenant X exceeded quota by 5×. Possible log flood."

VECTOR 3: Sensitive data in logs (accidental PII exposure)
  ATTACK: Developer logs request body containing credit card number.
  → Credit card number now in centralized log storage, searchable.
  DEFENSE:
  → Agent-side PII scrubbing: Regex patterns for CC numbers, SSNs, emails
    → Matched patterns replaced with "[REDACTED]" before shipping
  → Ingestion-side scrubbing: Second layer of pattern matching
  → Access controls: PII-containing log fields require elevated permissions
  → Retention: PII-flagged logs have shorter retention (7 days max)
```

## Rate Abuse

```
SEARCH ABUSE:
  → Automated script runs 10,000 queries/sec against the query API
  → Per-user rate limit: 50 queries/sec
  → Per-IP rate limit: 100 queries/sec
  → Queries without authentication: Rejected

LOG EXPORT ABUSE:
  → Insider exports 30 days of all logs to external system
  → Export requires admin approval for > 1TB
  → Export audit log: Who exported what, when, to where
```

## Privilege Boundaries

```
TENANT ENGINEER:
  → CAN: Search their team's service logs
  → CAN: Set up alerts for their services
  → CANNOT: Search other teams' logs
  → CANNOT: Modify retention policies

TENANT ADMIN:
  → CAN: Manage their team's log configuration
  → CAN: Adjust their team's alert rules and dashboards
  → CANNOT: Access other teams' data

PLATFORM ADMIN:
  → CAN: Manage all tenants, quotas, retention policies
  → CAN: Access any team's logs (for incident investigation)
  → Audit logged: Every cross-tenant access recorded

SECURITY TEAM:
  → CAN: Search all logs (for security investigation)
  → CAN: Set up security-specific alert rules
  → CANNOT: Modify or delete logs
  → Audit logged: Every search recorded
```

---

# Part 14: Evolution Over Time (CRITICAL FOR STAFF)

## V1: Naive Design (Month 0-6)

```
ARCHITECTURE:
  → Each service writes to local log files
  → Engineers SSH into hosts and grep log files
  → Log rotation: Files older than 7 days deleted automatically
  → No central storage, no search, no correlation

WHAT WORKS:
  → Simple: Zero infrastructure cost for logging
  → Works for: < 50 hosts, < 5 services
  → grep is fast on one file (< 1GB)

TECH DEBT ACCUMULATING:
  → No correlation across hosts (SSH into each, mentally merge)
  → Logs lost when containers restart or hosts recycled
  → grep across 50 hosts takes 30+ minutes
  → No alerting (nobody watches 50 log files simultaneously)
  → No retention management (disks fill, services crash)
```

## What Breaks First (Month 6-12)

```
INCIDENT 1: "The Missing Log" (Month 7)
  → SEV-1 incident. Root cause is on a container that restarted.
  → Container logs are gone (ephemeral filesystem).
  → On-call spent 2 hours recreating the issue to get the log output.
  → FIX: Must ship logs to durable central storage before container dies.

INCIDENT 2: "The SSH Marathon" (Month 9)
  → Service spanning 200 hosts. One host has the error.
  → Engineer SSH's into hosts one by one. Took 45 minutes to find it.
  → Meanwhile, 5,000 users affected.
  → FIX: Need centralized search. "grep across all hosts" in seconds.

INCIDENT 3: "The Disk Full" (Month 11)
  → Production database server: /var/log filled to 100%.
  → Database couldn't write WAL → crashed → outage for 200K users.
  → Root cause: Application logging at 10GB/hour (verbose debug logging
    accidentally left on in production).
  → FIX: Need per-host rate limits, log rotation, centralized management.
```

## Real Incident Table (Structured)

| Context | Trigger | Propagation | User Impact | Engineer Response | Root Cause | Design Change | Lesson |
|---------|---------|-------------|-------------|-------------------|------------|---------------|--------|
| **The Missing Log** | SEV-1 incident. Root cause suspected on container that restarted 10 minutes ago. | Container logs stored on ephemeral filesystem. Container restart = logs gone. No central collection. | On-call spent 2 hours recreating the issue to obtain log output. 2-hour extended outage. | Manual reproduction. No automated recovery. | No durable central storage. Logs existed only on container filesystem. | Agent-based collection to central store before container dies. Disk buffer on agent survives restarts. | Logs are worthless if they exist only where they were emitted. Ship to durable storage before the source dies. |
| **The SSH Marathon** | Service spanning 200 hosts. One host logging errors. Unknown which. | Engineer SSHs into hosts sequentially. No centralized search. grep per-host. | 45 minutes to find the offending host. 5,000 users affected during investigation. | Manual host-by-host inspection. No tooling. | No centralized search. Logs scattered across 200 filesystems. | Centralized ingestion and index. "grep across all hosts" in seconds from single query. | When you have 200 places to look, centralized search is not a feature — it's the only viable strategy. |
| **The Disk Full** | Production database. Application accidentally left verbose DEBUG logging enabled. | /var/log fills at 10GB/hour. Database WAL write fails when disk full. | Database crash. 200K users offline for 2 hours. | Emergency disk cleanup. Database restart. Manual log purge. | Unbounded local log growth. No per-host rate limits. No centralized management. | Log agents with per-host rate limits (1,000 lines/sec). Priority-based dropping (DEBUG first). Central rotation. | Local disks are a single point of failure. Bounded local state + central control = survivable. |
| **Search Storm Crash** | SEV-1 incident. 200 engineers all search for the same error pattern simultaneously. | Single search path. No caching. 200 identical queries = 200× segment scans. Query engine overloaded. | Search times out. Engineers cannot find root cause. Incident extended by 90 minutes. | Manual query throttling. "Stop searching" directive. No systemic fix. | No query result caching. No incident-aware scaling. Search capacity sized for average load. | Query result cache (40-60% hit rate during incidents). Auto-scale query fleet within 2 minutes. Per-user limits. | The system is needed most when under the most stress. Design for the incident case, not the average case. |
| **Noisy Neighbor Log Flood** | One team deploys bug. Service logs 100× normal volume (error loop). | Shared ingestion pipeline. No per-tenant quotas. One tenant's burst consumes pipeline capacity. | Other teams' logs delayed or dropped. Search for unaffected services returns stale or empty. | Manual isolation. Disable verbose service. No automated containment. | Shared pipeline without tenant isolation. No backpressure or quotas. | Per-tenant ingestion quotas. Per-host rate limits. Priority-based dropping (ERROR never dropped). | One team's logging mistake must not degrade everyone else's ability to debug. Isolation is a platform requirement. |
| **Pipeline Restart Data Loss** | Ingestion pipeline down for 45 minutes (rolling deploy bug). Agents continue producing logs. | Agents had memory-only buffer (~1MB). 45 minutes of logs = lost when pipeline unreachable. | Log gap during incident window. Root cause logs from the failure moment — gone. | Post-incident: No recovery. Had to infer from metrics and partial data. | Agent buffers too small. No disk buffer. No WAL for in-flight data. | Agent disk buffer (10GB). Survives 55+ hours of pipeline outage. WAL on ingestion for durability. | The agent is the first line of defense. If the pipeline is down, the agent must hold until it recovers. |

### How Incidents Drive Redesign (from table)

```
"Missing log" (container restart)     → Central durable storage (V2)
"SSH marathon" (manual host hopping)   → Centralized search (V2)
"Disk full" (unbounded local logs)    → Agent rate limiting (V2)
"Search storm crash"                  → Query caching + auto-scaling (V3)
"Noisy neighbor flood"                → Multi-tenant quotas + isolation (V3)
"Pipeline restart data loss"          → Agent disk buffer + WAL (V3)
```

## V2: Improved Design (Month 12-24)

```
ARCHITECTURE:
  → Log agents on every host ship to central message queue
  → Message queue → storage (simple file-based, time-partitioned)
  → Basic search UI: grep-like interface, scans all files in time range
  → No indexing (full scan on every query)
  → Single tier (all data on same storage, same query speed)
  → Basic alerting: Pattern matching on the ingestion stream

NEW PROBLEMS IN V2:
  → Full scan search: "Find trace_id X" scans ALL logs in time range → slow
  → No tiered storage: 90 days of logs on SSD → expensive
  → No multi-tenancy: One team's verbose logging slows everyone's search
  → No backpressure: Log burst overwhelms message queue → data loss
  → No compression optimization: Raw JSON stored → 10× more storage than needed
  → Search during incidents: 200 engineers grep simultaneously → search crashes

WHAT DROVE V2:
  → "Missing log" incident → central storage
  → "SSH marathon" incident → centralized search
  → "Disk full" incident → log agents with rate limiting
```

## V3: Long-Term Stable Architecture (Month 24+)

```
ARCHITECTURE:
  → Log agents: Disk buffer, compression, backpressure, rate limiting
  → Ingestion: Stateless, horizontally scaled, WAL for durability
  → Storage: Columnar segments, inverted index, three tiers (hot/warm/cold)
  → Query: Index-first search, scatter-gather, result caching
  → Tailing: Dedicated fan-out pipeline, WebSocket streaming
  → Alerting: Streaming evaluation on ingestion fork
  → Multi-tenancy: Per-tenant quotas, isolation, chargeback

WHAT MAKES V3 STABLE:
  → Columnar storage: 10:1 compression vs raw JSON. 10× cost reduction.
  → Inverted index: 10-100× query speedup vs full scan
  → Tiered storage: Hot (SSD, 7d), warm (HDD, 30d), cold (obj, 365d)
    → Each tier optimized for its access pattern
  → Agent resilience: 10GB disk buffer survives 55 hours of pipeline outage
  → Multi-tenancy: Noisy-neighbor isolation at ingestion AND query
  → Query caching: 40-60% hit rate during incidents (when needed most)
  → Auto-scaling: Ingestion and query scale independently

REMAINING CHALLENGES:
  → Cross-service log correlation without trace_id (ad-hoc correlation)
  → Log anomaly detection (what's "abnormal" in 170B lines/day?)
  → Cost attribution per log line (should this ERROR be charged to the
    service that emitted it or the library that caused it?)
```

## How Incidents Drive Redesign

```
INCIDENT → REDESIGN MAPPING:

"Missing log" (container restart)     → Central durable storage (V2)
"SSH marathon" (manual host hopping)  → Centralized search (V2)
"Disk full" (unbounded local logs)    → Agent rate limiting (V2)
"Search is too slow"                  → Inverted index (V3)
"Storage cost 10× budget"            → Columnar compression + tiering (V3)
"One team's logs broke search"       → Multi-tenant quotas + isolation (V3)
"Can't search during incident"       → Query caching + auto-scaling (V3)
"Lost logs during pipeline restart"  → Agent disk buffer + WAL (V3)
"Can't see live errors from my       → Live tailing pipeline (V3)
 service across 200 instances"

PATTERN: Every major platform feature was preceded by an operational pain
point or incident. The platform evolves to eliminate the MOST PAINFUL
gap between "what engineers need during incidents" and "what the log
system provides." The evolution is driven by MTTR — every feature that
reduces time-to-root-cause is worth building.
```

---

# Part 15: Alternatives & Explicit Rejections

## Alternative 1: Elasticsearch for Everything

```
DESCRIPTION:
  Use Elasticsearch as the single storage and query engine for all logs.
  Full inverted index on all fields and message body.

WHY IT SEEMS ATTRACTIVE:
  → Mature ecosystem, well-understood
  → Full-text search with relevance scoring
  → Rich query DSL (aggregations, nested queries)
  → Kibana for visualization

WHY A STAFF ENGINEER REJECTS IT (at scale):
  → COST: Full inverted index is 1.5-2× the raw data size. At 86TB/day,
    that's 170TB/day of index + data. 10× more expensive than columnar
    storage with selective indexing.
  → JVM GC PAUSES: Under high write load (2M lines/sec), Elasticsearch
    nodes experience GC pauses (100ms-2s) that impact query latency.
    During incidents (high write + high read), GC pauses are worst.
  → SEGMENT MERGE STORMS: ES merges segments continuously. Under high
    write throughput, merge I/O competes with query I/O → both degrade.
  → TIERED STORAGE: ES has rudimentary hot/warm/cold support, but
    tier transitions are operationally complex and error-prone.
  → OPERATIONAL BURDEN: ES clusters at this scale (hundreds of nodes)
    require dedicated operations expertise. Shard management, rebalancing,
    and recovery from split-brain are operationally expensive.

WHEN IT'S ACCEPTABLE:
  → < 10 TB/day of logs
  → Need full-text search with relevance scoring
  → Team has Elasticsearch operational expertise
  → Budget allows 2× storage cost for full indexing
```

## Alternative 2: Object Storage + Athena-Style SQL

```
DESCRIPTION:
  Ship all logs directly to object storage (S3/GCS). Query using
  serverless SQL engine (like Athena) that scans objects on demand.

WHY IT SEEMS ATTRACTIVE:
  → Cheapest possible storage ($0.004/GB/month)
  → No cluster management (serverless query)
  → SQL queries (familiar to all engineers)
  → Infinite storage capacity

WHY A STAFF ENGINEER REJECTS IT (for primary log search):
  → LATENCY: Every query scans object storage. Even with partitioning,
    "find trace_id=abc123 in last 1 hour" scans ~100GB of objects.
    Object storage throughput: ~100MB/sec per stream → 1,000 seconds → 17 minutes.
    Not acceptable for incident investigation.
  → NO LIVE TAILING: Object storage is batch-write. No streaming path.
  → NO INDEX: Every query is a full scan within the time partition.
    No inverted index means no sub-second lookups.
  → COLD START: Serverless query engines have 5-30 second cold start.
    During incidents, you need results in seconds, not after a cold start.

WHEN IT'S ACCEPTABLE:
  → Cold/archive tier (30+ day old logs)
  → Compliance queries (run infrequently, minutes acceptable)
  → Log analytics (aggregation over large time ranges)
  → Not for interactive incident investigation
```

## Alternative 3: Metrics Instead of Logs

```
DESCRIPTION:
  Instead of storing every log line, extract metrics from logs at the
  edge (agent side). Store only metrics (counts, rates, percentiles).
  "Why store the actual log lines when you can just count errors?"

WHY IT SEEMS ATTRACTIVE:
  → 1,000× less data (metrics are numbers, not text)
  → Faster query (time-series databases are optimized for numeric aggregation)
  → Lower storage cost

WHY A STAFF ENGINEER REJECTS IT:
  → METRICS TELL YOU WHAT, NOT WHY: "Error count spiked at 10:23" — but
    WHAT error? Which request? What was the stack trace? Which host?
    Metrics indicate a problem. Logs diagnose it.
  → YOU CAN'T PRE-DEFINE ALL USEFUL METRICS: During an incident, you need
    to search for patterns you didn't anticipate. "Show me all logs with
    'DNS' in the message" — you can't create a metric for every possible
    word in every possible log message.
  → METRICS AND LOGS COMPLEMENT EACH OTHER: Metrics for detection (alerts,
    dashboards). Logs for diagnosis (root cause, context). Replacing one
    with the other is like replacing your eyes with a thermometer.

WHEN IT'S ACCEPTABLE:
  → As a COMPLEMENT to logs (both, not either/or)
  → For services where log volume is extremely high and search is rare
    (network switches logging every packet — extract metrics, sample logs)
```

---

# Part 16: Interview Calibration (Staff Signal)

## How Interviewers Probe This System

```
PROBE 1: "How do you handle 2M log lines per second?"
  PURPOSE: Tests understanding of write throughput at scale
  EXPECTED DEPTH: Agent batching + compression, partitioned ingestion,
  WAL for durability, segment-based storage, horizontal scaling of
  ingestion layer. Specific numbers: batch size, compression ratio,
  segment flush interval.

PROBE 2: "How does search work when you have petabytes of logs?"
  PURPOSE: Tests understanding of query optimization at scale
  EXPECTED DEPTH: Inverted index for indexed fields, bloom filters for
  high-cardinality fields, segment pruning by time range, scatter-gather
  across storage nodes, query result caching. Explain WHY full scan
  doesn't work and HOW indexing reduces scan volume 10-100×.

PROBE 3: "What happens when the ingestion pipeline goes down?"
  PURPOSE: Tests failure thinking and data durability
  EXPECTED DEPTH: Agent disk buffer (10GB, 55 hours), WAL on ingestion
  instances, replay on recovery, graceful degradation (buffer → sample →
  drop by priority). NEVER lose ERROR/WARN logs.

PROBE 4: "How do you make search fast during incidents when everyone is
  searching at the same time?"
  PURPOSE: Tests understanding of system behavior under stress
  EXPECTED DEPTH: The system is needed most when under the most stress.
  Query result caching (40-60% hit rate during incidents), auto-scaling,
  query prioritization, per-user limits. The incident search storm is
  the DESIGN CASE, not an edge case.

PROBE 5: "How do you manage cost when log volume grows 40% per year?"
  PURPOSE: Tests cost awareness (critical for Staff)
  EXPECTED DEPTH: Tiered storage (hot/warm/cold with different costs),
  columnar compression (10:1), per-tenant retention policies, log
  sampling for DEBUG, selective indexing (not all fields). Specific
  cost numbers for each tier.

PROBE 6: "How is live tailing different from search?"
  PURPOSE: Tests understanding of separate read paths
  EXPECTED DEPTH: Tailing is a PUSH pipeline (fork at ingestion, filter,
  WebSocket to client). Search is a PULL pipeline (index lookup, scatter-
  gather, scan segments). They share the ingestion path but diverge after.
  Different latency targets: Tailing < 2s, search < 5s.
```

## Common L5 Mistakes

```
MISTAKE 1: "Store everything in Elasticsearch"
  L5: "We'll use Elasticsearch, it handles indexing and search."
  PROBLEM: At 2M lines/sec, ES write throughput becomes the bottleneck.
  Full inverted index on message body doubles storage cost. GC pauses
  under load degrade query performance precisely when it matters most.
  L6: Columnar storage with selective indexing. Index the 5 fields
  people actually filter on, not the entire message body.

MISTAKE 2: No tiered storage
  L5: "Keep everything on SSD for fast search."
  PROBLEM: 365 days × 8.6TB/day × 3 replicas = 9.4 PB on SSD.
  Cost: $940K/month for SSD alone. 95% of that data is never searched.
  L6: Three tiers. SSD for 7 days ($11K), HDD for 30 days ($3K),
  object storage for 365 days ($4K). Total: $18K/month vs $940K.

MISTAKE 3: No backpressure from agents
  L5: "Agents ship all logs to the central pipeline."
  PROBLEM: Service enters error loop → 100× log output → floods pipeline →
  ALL tenants' logs delayed → during an active incident, other teams
  can't search their logs.
  L6: Agent-side rate limiting (1,000 lines/sec per host), tenant quotas,
  priority-based dropping (DEBUG first, never ERROR), per-tenant
  ingestion isolation.

MISTAKE 4: Full scan for every query
  L5: "For search, we scan all logs in the time range."
  PROBLEM: 1 hour of data = 360GB compressed. Full scan at 100MB/sec =
  3,600 seconds = 60 minutes. Not useful during an incident.
  L6: Inverted index reduces scan to matching segments only. "service=
  payments AND level=ERROR AND last 1 hour" → index narrows to 87 of
  2,400 segments → scan 3.6GB instead of 360GB → 36 seconds → 2 seconds
  with parallel scan.

MISTAKE 5: Search and tailing use the same path
  L5: "For live tailing, poll the search API every second."
  PROBLEM: 2,000 tail sessions × 1 poll/sec = 2,000 QPS on search API.
  Each poll scans recent segments. Search infrastructure handles
  2,500 total QPS → live tailing consumes 80% of search capacity.
  During an incident: Both tailing AND search users compete.
  L6: Dedicated tailing pipeline. Fork at ingestion → filter → push.
  Zero search API load. Zero segment scans. O(1) per matching line.

MISTAKE 6: No query result caching
  L5: "Each query is executed independently."
  PROBLEM: SEV-1 incident. 200 engineers search "service=payments AND
  level=ERROR AND last 1 hour." 200 identical queries, each scanning
  the same segments. 200× the necessary work.
  L6: Query result cache. First query: Full execution (3 seconds).
  Next 199 queries: Cache hit (5ms). During incidents, cache hit
  rate is 40-60%.
```

## Staff-Level Answers

```
STAFF ANSWER 1: Architecture Overview
  "I split the system into three layers: COLLECTION (agents with disk
  buffers and priority-based backpressure), INGESTION (stateless,
  horizontally scaled, WAL for durability, segment-based storage with
  columnar compression and inverted index), and QUERY (index-first
  search with scatter-gather and result caching, separate tailing
  pipeline for real-time streaming). The key insight is that write
  and read paths are optimized independently — writes optimize for
  throughput and compression, reads optimize for index-driven pruning
  and caching."

STAFF ANSWER 2: Cost Management
  "Three levers. First, tiered storage: 7 days on SSD, 30 on HDD,
  365 on object storage — each tier is 5-25× cheaper than the one above.
  Second, columnar compression with dictionary encoding gives 10:1
  compression on log data. Third, selective indexing: I index 5 fields
  that people actually filter on, not the message body. Full-text
  indexing would double storage cost for 5% of queries."

STAFF ANSWER 3: Incident Readiness
  "The system is designed for the worst case: incident in progress, log
  volume 5× normal, 200 engineers all searching simultaneously, and one
  storage node just failed. Agent disk buffers handle ingestion burst.
  Query result caching handles the search storm — 200 identical queries
  become 1 scan plus 199 cache hits. Auto-scaling adds query capacity
  in 2 minutes. Storage replication handles node failure transparently.
  This is the design case, not the edge case."
```

## Example Phrases a Staff Engineer Uses

```
"Logs are write-heavy, read-critical. 95% are never searched, but you
don't know which 95% until you need the other 5%. Every design decision
flows from this asymmetry."

"The agent is the first line of defense. 10GB disk buffer, priority-based
dropping, LZ4 compression. The agent must survive a 30-minute pipeline
outage without losing ERROR logs."

"Inverted index on 5 fields gives me 10-100× scan reduction. Full-text
index on the message body doubles storage for marginal benefit. I'll
use bloom filters for trace_id — 1% of segment size, 100× speedup
for trace queries."

"During incidents, the cache hit rate is 40-60% because everyone searches
for the same thing. That's not luck — it's the design. The cache turns
200 identical queries into 1 scan and 199 instant responses."

"Hot tier at $11K/month. If I kept everything on SSD for a year, it'd
be $940K/month. Tiered storage isn't an optimization — it's the
difference between a viable system and a bankrupt one."

"The tailing pipeline is separate from the search pipeline. Tailing
forks at ingestion and pushes via WebSocket. Zero impact on search
capacity. If I used polling, 2,000 tail sessions would consume 80%
of my search budget."
```

## Staff Signals (What Interviewers Listen For)

```
SIGNAL 1: Leads with asymmetry
  Staff: "Logs are write-heavy, read-critical. 95% never searched."
  Senior: "We need to store and search logs."

SIGNAL 2: Designs for the incident case
  Staff: "During a SEV-1, 200 engineers search simultaneously. That's
  the design case. Query cache, auto-scale, per-tenant isolation."
  Senior: "Normal load is 500 QPS. We size for that."

SIGNAL 3: Cost-awareness with concrete numbers
  Staff: "Hot tier $11K. All SSD for 365 days = $940K. Tiered storage
  isn't optional — it's the difference between viable and bankrupt."
  Senior: "We'll use SSD for fast queries."

SIGNAL 4: Agent as first line of defense
  Staff: "10GB disk buffer. 55 hours of pipeline outage. ERROR never
  dropped. The agent is the most critical component."
  Senior: "Agents ship logs. If the pipeline is down, we buffer in memory."

SIGNAL 5: Rejects full-text index on message body
  Staff: "Index 5 fields. Full-text on message doubles storage for
  5% of queries. Columnar + selective indexing."
  Senior: "We'll index everything for fast search."
```

## Common Senior Mistake Phrases (Red Flags)

```
"We'll use [vendor] — it handles logs at scale."
  → Doesn't articulate write throughput, storage cost, or query patterns.

"Search scans the time range and filters."
  → No index. Full scan. Doesn't scale.

"Agents ship to a central queue. If the queue is down, we retry."
  → No disk buffer. Logs lost during extended outage.

"Everything on SSD for fast search."
  → Ignores cost. At 86TB/day × 365 days, unaffordable.

"Live tailing = poll the search API every second."
  → Consumes search capacity. Wrong architecture.

"During incidents, we'll add more query nodes."
  → Reactive. Doesn't mention caching or auto-scaling.
```

## How to Teach This System (For Interviewers)

```
1. START WITH THE ASYMMETRY
   "95% of logs are never searched. But you don't know which 95%.
   How does that change your storage and indexing design?"
   → Tests: Write vs read optimization, tiered storage rationale.

2. STRESS THE INCIDENT CASE
   "It's 3 AM. SEV-1. 200 engineers searching. Log volume 5× normal.
   One storage node just failed. What does your system do?"
   → Tests: Caching, auto-scaling, replication, isolation.

3. COST AS A CONSTRAINT
   "Log volume grows 40% YoY. Budget is flat. How do you survive?"
   → Tests: Tiered retention, compression, selective indexing, sampling.

4. AGENT RESILIENCE
   "Ingestion pipeline is down for 2 hours. What happens to the logs?"
   → Tests: Disk buffer, priority dropping, WAL, backpressure.

5. SEPARATE TAILING FROM SEARCH
   "How does live tailing work? Same as search?"
   → Tests: Push vs pull, fork at ingestion, WebSocket, capacity isolation.
```

## Leadership Explanation (One Paragraph for Non-Technical Stakeholders)

```
"Our log system collects 2 million log lines per second from 500,000
hosts, stores them so engineers can search petabytes in under 5 seconds,
and costs ~$32K/month instead of $940K. The key insight: we design for
when the system is needed most — during incidents, when everyone is
searching at once. We use tiered storage (7 days fast, 365 days cheap),
selective indexing (index 5 fields, not everything), and query caching
so 200 engineers searching for the same error become 1 query plus 199
cache hits. The system survives pipeline outages for 55 hours via agent
disk buffers, and one team's log burst never degrades another team's
search. It's built for the worst case, not the average case."
```

---

# Part 17: Diagrams (MANDATORY)

## Diagram 1: High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│       LOG SYSTEM ARCHITECTURE — THREE LAYERS                                │
│                                                                             │
│  ╔═══════════════════════════════════════════════════════════════════════╗   │
│  ║ COLLECTION LAYER (500K hosts, agent per host)                       ║   │
│  ║                                                                      ║   │
│  ║  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           ║   │
│  ║  │ Host 1   │  │ Host 2   │  │ Host 3   │  │ Host N   │           ║   │
│  ║  │ Agent    │  │ Agent    │  │ Agent    │  │ Agent    │           ║   │
│  ║  │ 10GB buf │  │ 10GB buf │  │ 10GB buf │  │ 10GB buf │           ║   │
│  ║  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘           ║   │
│  ║       └──────────────┴──────────────┴──────────────┘               ║   │
│  ╚═══════════════════════════════════╤════════════════════════════════╝   │
│                                      │ Compressed batches (100MB/sec)     │
│  ╔═══════════════════════════════════▼════════════════════════════════╗   │
│  ║ INGESTION LAYER (50 stateless instances)                          ║   │
│  ║                                                                      ║   │
│  ║  Parse → WAL → Segment Buffer → Flush → Index → Catalog Register  ║   │
│  ║         │                                                           ║   │
│  ║         ├──→ Tail Fan-out (→ WebSocket → Engineers)                ║   │
│  ║         └──→ Alert Evaluator (→ PagerDuty / Slack)                ║   │
│  ╚═══════════════════════════════════╤════════════════════════════════╝   │
│                                      │ Segments (columnar, compressed)    │
│  ╔═══════════════════════════════════▼════════════════════════════════╗   │
│  ║ STORAGE + QUERY LAYER                                              ║   │
│  ║                                                                      ║   │
│  ║  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐               ║   │
│  ║  │ HOT (SSD)    │  │ WARM (HDD)   │  │ COLD (Obj)   │               ║   │
│  ║  │ 7 days       │  │ 30 days      │  │ 365 days     │               ║   │
│  ║  │ 36TB         │──│ 72TB         │──│ 900TB        │               ║   │
│  ║  │ Indexed      │  │ Sparse idx   │  │ Metadata     │               ║   │
│  ║  │ < 5s query   │  │ < 30s query  │  │ < 5min query │               ║   │
│  ║  └──────────────┘  └──────────────┘  └──────────────┘               ║   │
│  ║                                                                      ║   │
│  ║  ┌────────────────────────────────────────────────────────┐        ║   │
│  ║  │ QUERY ENGINE (30-300 instances, auto-scaled)            │        ║   │
│  ║  │ Index lookup → Scatter to storage → Gather → Cache      │        ║   │
│  ║  └────────────────────────────────────────────────────────┘        ║   │
│  ╚═══════════════════════════════════════════════════════════════════════╝   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 2: Query Execution Flow (Index-Driven Search)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│       QUERY EXECUTION: HOW INDEX REDUCES SCAN 100×                          │
│                                                                             │
│  Query: "service=payments AND level=ERROR AND time=[last 1h]"              │
│                                                                             │
│  STEP 1: CATALOG LOOKUP                                                    │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │ Catalog: "Which segments overlap the last 1 hour?"                 │    │
│  │ → 2,400 segments (across 100 partitions × 24 segments/hr/partition)│    │
│  │ → 2,400 segments × 64MB = ~150GB of data to potentially scan      │    │
│  └───────────────────────────────┬────────────────────────────────────┘    │
│                                  │                                         │
│  STEP 2: INDEX PRUNING (service=payments)                                  │
│  ┌───────────────────────────────▼────────────────────────────────────┐    │
│  │ Inverted index: service=payments → [seg_101, seg_102, ... seg_347] │    │
│  │ 247 segments contain "payments" logs (of 2,400 total)              │    │
│  │ PRUNED: 90% of segments eliminated                                 │    │
│  └───────────────────────────────┬────────────────────────────────────┘    │
│                                  │                                         │
│  STEP 3: INDEX PRUNING (level=ERROR)                                       │
│  ┌───────────────────────────────▼────────────────────────────────────┐    │
│  │ Inverted index: level=ERROR → intersect with 247 segments          │    │
│  │ 87 segments contain payments ERROR logs                            │    │
│  │ PRUNED: 96% of original segments eliminated                        │    │
│  │ 87 segments × 64MB = ~5.6GB to scan (vs 150GB without index)      │    │
│  └───────────────────────────────┬────────────────────────────────────┘    │
│                                  │                                         │
│  STEP 4: SCATTER TO STORAGE NODES                                          │
│  ┌───────────────────────────────▼────────────────────────────────────┐    │
│  │ 87 segments distributed across ~15 storage nodes                   │    │
│  │ Send scan request to each node in parallel                         │    │
│  │ Each node: Decompress + scan its segments + return matches         │    │
│  └───────────────────────────────┬────────────────────────────────────┘    │
│                                  │                                         │
│  STEP 5: GATHER, MERGE, RESPOND                                            │
│  ┌───────────────────────────────▼────────────────────────────────────┐    │
│  │ Merge results from 15 nodes. Sort by timestamp. Apply limit.       │    │
│  │ Total lines scanned: ~500K (in 87 segments)                        │    │
│  │ Matching lines: 2,847                                              │    │
│  │ Execution time: 2.3 seconds                                        │    │
│  │                                                                    │    │
│  │ WITHOUT index: Scan 2,400 segments → 150GB → ~60 seconds          │    │
│  │ WITH index: Scan 87 segments → 5.6GB → ~2.3 seconds               │    │
│  │ SPEEDUP: 27×                                                       │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 3: Agent Backpressure and Resilience

```
┌─────────────────────────────────────────────────────────────────────────────┐
│       AGENT RESILIENCE: HOW LOGS SURVIVE PIPELINE FAILURES                  │
│                                                                             │
│  NORMAL OPERATION (pipeline healthy):                                       │
│  ┌──────┐    ┌──────────────────┐    ┌──────────────────┐                 │
│  │ App  │───→│ Memory Buffer    │───→│ Ship to Ingestion │───→ STORED     │
│  │ Logs │    │ (1MB, ~1 sec)    │    │ (batch, compress)  │                │
│  └──────┘    └──────────────────┘    └──────────────────┘                 │
│                                                                             │
│  PIPELINE SLOW (ingestion lagging):                                         │
│  ┌──────┐    ┌──────────────────┐    ┌──────────────────┐                 │
│  │ App  │───→│ Memory Buffer    │───→│ Disk Buffer       │───→ (queued)   │
│  │ Logs │    │ (1MB)            │    │ (10GB capacity)    │                │
│  └──────┘    └──────────────────┘    │ FIFO: Ship when   │                │
│                                       │ pipeline recovers │                │
│                                       └──────────────────┘                 │
│                                                                             │
│  PIPELINE DOWN (> 30 minutes):                                              │
│  ┌──────┐    ┌──────────────────┐    ┌──────────────────┐                 │
│  │ App  │───→│ Memory Buffer    │───→│ Disk Buffer       │───→ (queued)   │
│  │ Logs │    │ (1MB)            │    │ 90% full (9GB)     │                │
│  └──────┘    └──────────────────┘    └────────┬─────────┘                 │
│                                                │                            │
│                                       ┌────────▼─────────┐                 │
│                                       │ PRIORITY DROP     │                 │
│                                       │                   │                 │
│                                       │ Drop: DEBUG first │                 │
│                                       │ Then: INFO        │                 │
│                                       │ KEEP: WARN, ERROR │                 │
│                                       │ NEVER drop ERROR  │                 │
│                                       └──────────────────┘                 │
│                                                                             │
│  PIPELINE RECOVERY:                                                         │
│  ┌──────────────────┐                                                      │
│  │ Disk Buffer       │───→ Flush oldest first (FIFO)                       │
│  │ (draining)        │───→ Rate-limited (don't flood pipeline)             │
│  │ Ship + new logs   │───→ New logs interleaved with buffered              │
│  └──────────────────┘                                                      │
│                                                                             │
│  CAPACITY:                                                                  │
│  10GB disk buffer ÷ 50KB/sec (100 lines/sec × 500B) = 55 hours            │
│  With DEBUG dropping: ~200+ hours of ERROR/WARN retention                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 4: System Evolution (V1 → V2 → V3)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    LOG SYSTEM EVOLUTION: V1 → V2 → V3                       │
│                                                                             │
│  V1 (Month 0-6): LOCAL FILES + SSH                                          │
│  ─────────────────────────────────                                          │
│                                                                             │
│  ┌────────┐  ┌────────┐  ┌────────┐                                       │
│  │ Host 1 │  │ Host 2 │  │ Host 3 │     Engineer: ssh host1; grep error   │
│  │ /var/  │  │ /var/  │  │ /var/  │     → ssh host2; grep error           │
│  │ log/   │  │ log/   │  │ log/   │     → ssh host3; grep error           │
│  └────────┘  └────────┘  └────────┘     → ... 50 hosts later → found it  │
│                                                                             │
│  ✗ Logs lost on container restart  ✗ 45 minutes to find one error          │
│  ✗ No search across hosts          ✗ Disk fills → service crash            │
│                                                                             │
│  INCIDENTS: Missing log → SSH marathon → Disk full                          │
│             │               │               │                               │
│             ▼               ▼               ▼                               │
│                                                                             │
│  V2 (Month 12-24): CENTRALIZED STORAGE + GREP                              │
│  ────────────────────────────────────────────                               │
│                                                                             │
│  ┌────────┐   ┌───────────┐   ┌──────────────┐   ┌──────────┐            │
│  │ Agents │──→│ Message   │──→│ File Storage  │──→│ Search   │            │
│  │ (ship) │   │ Queue     │   │ (time-part.)  │   │ (scan)   │            │
│  └────────┘   └───────────┘   └──────────────┘   └──────────┘            │
│                                                                             │
│  ✓ Central storage  ✓ Basic search   ✗ Full scan (slow at scale)          │
│  ✗ No index          ✗ No tiering     ✗ No backpressure                   │
│  ✗ No compression    ✗ No isolation   ✗ Search crashes under load          │
│                                                                             │
│  INCIDENTS: Slow search → Cost explosion → Noisy neighbor → Search crash  │
│             │               │                │                │            │
│             ▼               ▼                ▼                ▼            │
│                                                                             │
│  V3 (Month 24+): INDEXED, TIERED, RESILIENT                                │
│  ───────────────────────────────────────────                                │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────┐              │
│  │ Agents: 10GB disk buffer, compression, backpressure       │              │
│  │ Ingestion: Stateless, WAL, columnar segments, indexing    │              │
│  │ Storage: Hot (SSD, 7d) → Warm (HDD, 30d) → Cold (Obj, 1y)│              │
│  │ Query: Index-first, scatter-gather, result cache           │              │
│  │ Tailing: Dedicated push pipeline, WebSocket                │              │
│  │ Multi-tenant: Quotas, isolation, chargeback                │              │
│  └──────────────────────────────────────────────────────────┘              │
│                                                                             │
│  ✓ Indexed search (100× faster)    ✓ Tiered storage (50× cheaper)         │
│  ✓ Agent resilience (55hr buffer)  ✓ Query caching (40% hit rate)         │
│  ✓ Multi-tenant isolation          ✓ Live tailing (< 2s)                  │
│  ✓ Auto-scaling for incidents      ✓ Columnar compression (10:1)          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 18: Brainstorming, Exercises & Redesigns

## "What if X Changes?" Questions

```
QUESTION 1: What if log volume doubles overnight (acquisition, new product)?
  IMPACT: 4M lines/sec → ingestion and storage capacity insufficient.
  REDESIGN:
  → Short-term: Reduce hot retention (7 days → 3 days). Free 57% of hot SSD.
  → Short-term: Enable aggressive DEBUG sampling (10% sample rate).
  → Medium-term: Add storage nodes and ingestion instances (horizontal scale).
  → Long-term: Better compression (Zstd level 3 → dictionary-trained codec).
  → Trade-off: Reduced hot retention means 3-7 day old data is slower to query.

QUESTION 2: What if you need to search across 5 years of logs (regulatory)?
  IMPACT: 5 years × 8.6TB/day × 365 days = ~15.7PB of compressed logs.
  REDESIGN:
  → Archive tier: Deep archive (glacier-class), $0.001/GB/month = ~$16K/month.
  → Query: Pre-scheduled restore (request data 12-24 hours before querying).
  → Index: Only metadata index (date, service, level). No full text.
  → Trade-off: 24-hour restore time. Only for compliance, not interactive search.

QUESTION 3: What if structured logging adoption goes from 30% to 100%?
  IMPACT: All logs are JSON with well-defined fields. No more free-text grep.
  REDESIGN:
  → Columnar storage becomes MUCH more efficient (every field is a column).
  → Inverted index covers more fields (all JSON keys are indexable).
  → Free-text search becomes less necessary (field-based queries dominate).
  → Compression improves (dictionary encoding on repeated field names).
  → Net effect: 2× better compression, 5× faster queries.

QUESTION 4: What if engineers want SQL queries on logs?
  IMPACT: SQL adds aggregation, joins, subqueries to query language.
  REDESIGN:
  → SQL query layer on top of columnar storage (natural fit — columns = tables).
  → "SELECT service, COUNT(*) FROM logs WHERE level='ERROR' GROUP BY service"
  → Aggregation rollups become essential (pre-computed for common GROUP BY).
  → Trade-off: SQL parsing + planning adds latency. Simple filters still use
    the fast path. SQL for analytics; filter-based for incident investigation.

QUESTION 5: What if data residency regulations require EU logs stay in EU?
  IMPACT: Can't use cross-region failover. EU logs MUST stay in EU.
  REDESIGN:
  → Strict region isolation: EU logs in EU storage, US logs in US storage.
  → No cross-region shipping even during failover.
  → EU region down → EU logs buffer on agents (up to 55 hours).
    If EU down > 55 hours → logs lost (regulation prevents cross-region).
  → Cross-region search: Query routes to each region separately. EU results
    only available from EU query engines.
  → Trade-off: Longer RPO during region outage. Regulatory compliance > availability.
```

## Redesign Under New Constraints

```
CONSTRAINT 1: Edge deployment (no central datacenter)
  → Devices produce logs locally (IoT, retail stores, edge nodes)
  → Network to central may be unreliable (satellite, cellular)
  → Agent disk buffer becomes critical (days, not hours, of buffering)
  → Logs compressed and shipped in batches when connectivity available
  → Local search: Lightweight local index for immediate debugging
  → Challenge: Agents must be self-sufficient for days without central

CONSTRAINT 2: Logs must be encrypted at rest and in transit
  → Agent → ingestion: TLS encryption (already standard)
  → Storage: Encrypted at rest (AES-256)
  → Index: Also encrypted (but still searchable — encrypted index)
  → Challenge: Encrypted search is 10-100× slower than plaintext search.
  → Compromise: Encrypt cold/warm. Hot tier: Encrypted at rest, decrypted
    at query time (within secure storage node boundary).

CONSTRAINT 3: Multi-cloud (logs from AWS, GCP, and on-prem)
  → Log agents on all platforms (same agent binary, multi-platform)
  → Ingestion: Regional endpoints per cloud provider
  → Storage: Unified format across clouds (own columnar format, not
    vendor-specific). Can store on any object storage (S3, GCS, HDFS).
  → Query: Unified query engine that reads from all backends.
```

## Failure Injection Exercises

```
EXERCISE 1: Kill 2 of 3 storage replicas for one partition
  OBSERVE: Does the remaining replica serve reads? How does write
  availability degrade? When replicas return, how long does recovery take?

EXERCISE 2: Introduce 50% packet loss between agents and ingestion
  OBSERVE: How fast do agent disk buffers fill? When does DEBUG dropping
  kick in? How long until pipeline is stable again after recovery?

EXERCISE 3: Inject a segment catalog that's 5 minutes stale
  OBSERVE: Do queries miss recent segments? How do users experience this?
  Does the system detect the staleness and alert?

EXERCISE 4: One tenant starts logging 100× normal volume (error loop)
  OBSERVE: Does the tenant's burst impact other tenants' ingestion latency?
  Does the per-tenant quota kick in? Which log levels get dropped?

EXERCISE 5: Kill the query result cache during a simulated incident
  OBSERVE: How does query latency change when 200 engineers search
  simultaneously without caching? Does auto-scaling compensate?

EXERCISE 6: Corrupt 10% of inverted index entries on hot storage
  OBSERVE: Do queries return incorrect results or just slower results?
  Does the reconciliation job detect the corruption? How long to repair?
```

## Trade-Off Debates

```
DEBATE 1: Push-based vs pull-based agent shipping
  PUSH (current design):
  → Agent pushes batches to ingestion endpoint when ready
  → Pro: Agent controls timing (buffer management is local)
  → Pro: Simple (agent knows when batch is ready, ships it)
  → Con: 500K agents pushing simultaneously → ingestion must handle burst

  PULL:
  → Ingestion pulls logs from agents (agent exposes an endpoint)
  → Pro: Ingestion controls its own load (pulls when capacity available)
  → Con: 500K agents to poll → ingestion becomes O(N) poller
  → Con: Agent must expose a network endpoint (security, firewall issues)
  → Con: Higher latency (wait for next poll cycle)

  STAFF DECISION: Push. Agent-initiated shipping is simpler, lower latency,
  and avoids the O(N) polling problem. Burst handling is solved by agent
  jitter, backpressure, and ingestion auto-scaling — not by pull-based
  flow control.

DEBATE 2: Per-segment index vs global index
  PER-SEGMENT INDEX (current design):
  → Each segment has its own small inverted index
  → Pro: Index built at segment flush time (inline with ingestion)
  → Pro: Segment is self-contained (can be moved between tiers independently)
  → Pro: No global index to maintain, update, or repair
  → Con: Query must check many segment indexes (scatter across segments)

  GLOBAL INDEX:
  → One inverted index for ALL segments
  → Pro: Single index lookup → instant (O(1) for any field query)
  → Con: Index must be updated on EVERY segment flush (hot path)
  → Con: Global index is a SPOF (corruption → all queries break)
  → Con: Index size: 5% of ALL data = 50TB for a year → impractical on SSD

  STAFF DECISION: Per-segment index. Self-contained segments are simpler
  to manage, move, and delete. Query engine merges per-segment results
  efficiently (scatter-gather). Global index is a scaling trap — it
  becomes a bottleneck as data grows.

DEBATE 3: Columnar vs row-oriented segment format
  COLUMNAR (current design):
  → Fields stored in separate columns within a segment
  → Pro: 2-5× better compression (same field values compress together)
  → Pro: Faster aggregation (only read columns needed for query)
  → Pro: Dictionary encoding for low-cardinality fields (service, level)
  → Con: Reading a full log line requires reading ALL columns → more I/O

  ROW-ORIENTED:
  → Each log line stored as a complete record
  → Pro: Reading a single log line: One I/O (all fields together)
  → Pro: Simpler implementation
  → Con: Poor compression (mixed field types in same block)
  → Con: Aggregation requires reading entire records (wasted I/O)

  STAFF DECISION: Columnar. Log search queries typically filter on 2-3
  fields (service, level, time) and display the message. Columnar format
  allows reading ONLY the filter columns for pruning, then reading the
  message column only for matching lines. At 86TB/day, the 2-5× compression
  advantage of columnar is worth $50K+/year in storage savings.

DEBATE 4: Dedicated log storage vs general-purpose data lake
  DEDICATED (current design):
  → Purpose-built storage and query engine for logs
  → Pro: Optimized for log access patterns (time-range, field filter)
  → Pro: Tiered storage with automated transitions
  → Pro: Live tailing and alerting built-in
  → Con: Another system to build and maintain

  DATA LAKE (send everything to a shared analytics platform):
  → Logs go to the same place as metrics, events, analytics data
  → Pro: Single platform to operate
  → Pro: Cross-data-type queries (join logs with metrics)
  → Con: Log-specific features (live tailing, agent resilience) not built-in
  → Con: Log volume (86TB/day) may overwhelm a general-purpose platform
  → Con: Different SLAs (log search: 5 seconds; analytics: 5 minutes)

  STAFF DECISION: Dedicated. Logs have unique requirements: massive write
  throughput, live tailing, agent resilience, tiered retention, and search
  that MUST work during incidents. A general-purpose data lake trades log-
  specific optimizations for generality. The cost of operating a dedicated
  system (~$32K/month) is far less than the cost of logs that aren't
  searchable during a SEV-1 (hours of extended MTTR × revenue impact).
```

---

# Master Review Check & L6 Dimension Table

## Master Review Check (11 Items)

```
[ ] A. Judgment: Trade-offs explicitly stated (at-least-once vs exactly-once,
      compression vs latency, index coverage vs storage cost)? Alternatives
      rejected with rationale (Elasticsearch, object-storage-only, metrics-only)?
[ ] B. Failure/Blast Radius: Agent crash, pipeline down, storage node failure,
      search storm, noisy neighbor — each has defined behavior and mitigation?
[ ] C. Scale/Time: Concrete numbers (2M lines/sec, 500K hosts, 86TB/day)?
      Growth assumptions (40% YoY)? What breaks first at 2× scale?
[ ] D. Cost: Storage/compute/network breakdown? Major cost drivers identified?
      Tiered storage cost delta ($11K vs $940K) explained?
[ ] E. Real-World Ops: Agent disk buffer (55 hr survival)? WAL? Rolling upgrades?
      Incident response (search storm, pipeline recovery)?
[ ] F. Memorability: Mental model (write-heavy, read-critical)? One-liners for
      agent resilience, index pruning, tiered storage?
[ ] G. Data/Consistency: At-least-once ingestion? Point-in-time search?
      Tier transition atomicity?
[ ] H. Security/Compliance: PII masking? Per-tenant access? Audit logging?
      Append-only storage (tampering resistance)?
[ ] I. Observability: Agent metrics (buffer usage, drop rate)? Ingestion
      throughput? Query latency? Cache hit rate?
[ ] J. Cross-Team: Multi-tenant quotas? Chargeback? Platform vs consumer team
      ownership? Cross-region search?
[ ] Exercises & Brainstorming: "What if X changes?" Failure injection?
      Trade-off debates? Redesign under constraints?
```

## L6 Dimension Table (A–J)

| Dim | Name | GAP? | Staff Treatment in This Chapter |
|-----|------|------|--------------------------------|
| A | **Judgment** | — | Trade-offs: at-least-once vs dedup, compression vs latency, index selectivity. Rejects Elasticsearch (cost), object-storage-only (latency), metrics-only (diagnosis). |
| B | **Failure/Blast Radius** | — | Agent crash, pipeline down 55 hr, storage node fail, search storm, noisy neighbor — each sectioned. Priority-based dropping limits blast. |
| C | **Scale/Time** | — | 2M lines/sec, 500K hosts, 86TB/day. 40% YoY growth. Burst: 10× volume, 10× query. "What breaks first" enumerated. |
| D | **Cost** | — | Storage 55%, compute 41%, network 3%. Hot $11K vs all-SSD $940K. Tiered retention, compression, selective indexing. |
| E | **Real-World Ops** | — | Agent disk buffer, WAL, rolling upgrades. Real Incident table. Evolution V1→V2→V3 driven by outages. |
| F | **Memorability** | — | "Write-heavy, read-critical." "Agent is first line of defense." "Incident is design case." Staff phrases, one-liners. |
| G | **Data/Consistency** | — | At-least-once ingestion. Snapshot consistency for search. Tier transitions atomic. |
| H | **Security/Compliance** | — | PII masking, per-tenant access, audit logging. Append-only. Compliance retention overrides. |
| I | **Observability** | — | Agent health (buffer, drops). Ingestion throughput, segment flush. Query latency, cache hit rate. |
| J | **Cross-Team** | — | Multi-tenant quotas, chargeback. Platform owns ingestion/query/storage. Consumer teams own agent config. |

---

# Summary

This chapter has covered the design of a Log Aggregation & Query System at Staff Engineer depth, from agent-based collection with disk-buffered resilience through columnar segment storage with inverted indexing, tiered retention management, and incident-optimized search with result caching and auto-scaling.

### Mental Model One-Liners (Quick Recall)

```
• "Write-heavy, read-critical" — 95% never searched; 5% decides MTTR.
• "Agent = first line of defense" — 10GB buffer, 55 hr survival, ERROR never dropped.
• "Index 5 fields, not the message" — 10-100× scan reduction, half the storage cost.
• "Tiered storage = viability" — $11K hot vs $940K all-SSD; not optional.
• "Incident = design case" — 5× burst + 10× search storm; cache, scale, isolate.
• "Tailing forks; search pulls" — Separate pipelines; tailing zero impact on search.
```

### Key Staff-Level Takeaways

```
1. Write-heavy, read-critical asymmetry drives every decision.
   95% of logs are never searched. But the 5% that IS searched determines
   whether an incident takes 5 minutes or 5 hours to resolve. Design for
   write throughput. Optimize for read performance at query time.

2. The agent is the first line of defense.
   10GB disk buffer survives 55 hours of pipeline outage. Priority-based
   dropping ensures ERROR logs are never lost. The agent is the most
   important component — if it fails, logs are lost forever.

3. Inverted index is the single most impactful query optimization.
   Index on 5 high-value fields reduces scan volume 10-100×. This is the
   difference between 60-second and 2-second queries. Full-text indexing
   on message body is rejected — doubles storage for 5% of queries.

4. Tiered storage is not an optimization — it's a viability requirement.
   SSD for 7 days: $11K. SSD for 365 days: $940K. Three tiers (hot/warm/cold)
   provide 50× cost reduction while maintaining query SLAs per tier.

5. Design for the incident case, not the average case.
   5× log burst + 10× search storm + storage node failure — simultaneously.
   Query caching (40-60% hit rate), auto-scaling, agent buffering, and
   storage replication make this survivable. The incident is the design case.

6. Separate tailing from search.
   Tailing is a push pipeline (fork at ingestion → filter → WebSocket).
   Search is a pull pipeline (index → scatter-gather → scan). Combining
   them causes tailing to consume search capacity at the worst moment.

7. Storage cost dominates — manage it actively.
   Tiered retention, columnar compression (10:1), selective indexing,
   per-tenant policies, and DEBUG sampling are the cost control levers.
   Without them, log storage grows 40% YoY to unaffordable levels.
```

### How to Use This Chapter in an Interview

```
OPENING (0-5 min):
  → Clarify: How many hosts? Log volume? Retention requirements?
  → State: "I'll design the system as three layers: COLLECTION (agents with
    disk buffer and backpressure), INGESTION (stateless, WAL, columnar segments
    with selective indexing), and QUERY (index-first search with caching,
    separate live tailing pipeline)."

FRAMEWORK (5-15 min):
  → Requirements: Durable ingestion, fast search, live tailing, tiered retention
  → Scale: 500K hosts, 2M lines/sec, 86TB/day raw, 500 search QPS
  → NFRs: Ingestion < 30s to searchable, search < 5s, tailing < 2s

ARCHITECTURE (15-30 min):
  → Draw: Agents → ingestion → storage (hot/warm/cold) → query engine
  → Draw: Separate tailing pipeline forking from ingestion
  → Explain: Columnar segments, inverted index, three-tier storage

DEEP DIVES (30-45 min):
  → When asked about throughput: Agent batching, compression, WAL, segment flush
  → When asked about search: Inverted index, segment pruning, scatter-gather, cache
  → When asked about failures: Agent disk buffer, WAL replay, replica failover
  → When asked about cost: Tiered storage (SSD vs HDD vs object), compression ratio
  → When asked about incidents: Cache hit rate, auto-scaling, priority-based search
```
