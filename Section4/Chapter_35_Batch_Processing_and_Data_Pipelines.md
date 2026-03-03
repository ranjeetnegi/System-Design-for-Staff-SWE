# Chapter 33 Supplement: Batch Processing and Data Pipelines

---

# Introduction

Chapter 24 (Queues, Logs, Streams) and Chapter 33 (Event-Driven) cover streaming and real-time processing. But many workloads are **batch**: periodic ETL jobs, nightly reports, data warehouse loading, analytics aggregation. Batch and stream are complementary—different tools for different latency and throughput profiles. This supplement fills that gap.

At Staff level, you're asked when to use batch vs stream, how to design data pipelines that scale, and when a "daily job" becomes a distributed batch system. This supplement gives you the depth to answer those questions with precision.

**The Staff Engineer's Batch Principle**: Batch processing handles large volumes of data at rest—process it all, then done. Stream processing handles data in motion—process as it arrives. Use batch when latency of hours is acceptable and throughput matters. Use stream when latency of seconds matters. Many systems need both (Lambda architecture, or batch for historical + stream for real-time).

**How to use this supplement**: Read it alongside Chapter 33. When the main chapter discusses event-driven processing, this supplement covers the complementary world of batch. For interview prep, focus on the batch vs stream decision tree, the data pipeline architecture patterns, the orchestration section, and the production incidents. For deep dives, work through the Spark architecture, the Lambda vs Kappa comparison, and the data quality section. The goal is to build intuition about when batch is the right tool, how to design pipelines that are reliable at scale, and what breaks when batch systems grow.

---

## Quick Visual: Batch vs Stream at a Glance

```
┌─────────────────────────────────────────────────────────────────────────────┐
│     BATCH vs STREAM: WHEN TO USE WHICH                                       │
│                                                                             │
│   L5 Framing: "We have a nightly job" or "We use Kafka for everything"      │
│   L6 Framing: "Batch for high-throughput, bounded latency (ETL, reports).   │
│                Stream for low-latency, unbounded data (events, alerts).      │
│                Batch: process 1TB in 2 hours. Stream: process 10K events/s   │
│                in real time. Hybrid: batch for backfill, stream for new."     │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  BATCH:                                                              │   │
│   │  • Input: Bounded (files, DB snapshot, date partition)               │   │
│   │  • Process: All at once (MapReduce, Spark, SQL)                      │   │
│   │  • Output: Done when job completes                                   │   │
│   │  • Latency: Minutes to hours                                         │   │
│   │  • Failure: Retry entire job or failed partition                     │   │
│   │  • Examples: ETL, nightly reports, ML training, data warehouse load  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  STREAM:                                                             │   │
│   │  • Input: Unbounded (Kafka, event hub, change stream)                │   │
│   │  • Process: As data arrives (per-event or micro-batch)               │   │
│   │  • Output: Continuous, near real-time                                │   │
│   │  • Latency: Milliseconds to seconds                                  │   │
│   │  • Failure: Checkpoint and resume from last offset                   │   │
│   │  • Examples: Real-time dashboards, fraud detection, alerting         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   USE BATCH: ETL, reporting, ML training, data lake ingestion, backfill    │
│   USE STREAM: Real-time dashboards, alerts, event-driven workflows         │
│   USE BOTH: Batch for historical + stream for real-time (Lambda/Kappa)     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## L5 vs L6: Batch vs Stream Thinking

| Scenario | L5 Approach | L6 Approach |
|----------|-------------|-------------|
| **Choosing batch vs stream** | "Kafka for everything" or "Cron job is fine" | "Batch when: (1) latency of hours OK, (2) high throughput (TB), (3) full scan or aggregation. Stream when: (1) latency of seconds matters, (2) event-driven, (3) incremental updates. Many systems need both." |
| **Batch at scale** | "We'll just run a bigger job" | "Single-node job fails at 100GB+. Need distributed batch: Spark, Flink batch mode, or MapReduce. Partition data, process in parallel, handle skew (some partitions larger)." |
| **Data pipeline** | "We load the warehouse nightly" | "Pipeline stages: Extract (DB, files, API) → Transform (clean, aggregate) → Load (warehouse, lake). Failure at any stage: retry, idempotency, exactly-once semantics. Orchestration: Airflow, Prefect, Dagster." |
| **Failure handling** | "Rerun the job" | "Idempotent jobs: re-run produces same result. Partition by date → reprocess one day, not all. Checkpoint intermediate results for long jobs. Dead-letter for poison records." |
| **Cost** | "Spark cluster is always on" | "Ephemeral clusters: spin up for job, tear down after. Spot instances for 60-70% cost reduction. Serverless (BigQuery, Athena) for ad-hoc—pay per query, not per cluster." |
| **Data quality** | "We'll fix bad data later" | "Validate at ingestion: null checks, type checks, range checks. Data contracts between producer and consumer teams. Quarantine bad records. SLOs for data freshness and completeness." |

**Key Difference**: L6 engineers see batch processing as an engineering discipline—not "just cron jobs." They design for idempotency, handle failure gracefully, optimize cost, and enforce data quality at every stage.

---

# Part 1: Batch Processing Foundations

## What Makes Something "Batch"?

Batch processing operates on a **bounded** dataset. The input is finite, the processing runs to completion, and the output is produced when the job finishes.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   BATCH: THE MENTAL MODEL                                                    │
│                                                                             │
│   Input (bounded)        Process              Output                        │
│   ┌─────────────┐       ┌──────────┐         ┌─────────────┐               │
│   │ All orders   │       │ Aggregate│         │ Daily revenue│               │
│   │ from         │ ────► │ by region│ ──────► │ report       │               │
│   │ 2024-03-01   │       │ and SKU  │         │ (complete)   │               │
│   └─────────────┘       └──────────┘         └─────────────┘               │
│                                                                             │
│   KEY PROPERTIES:                                                           │
│   1. Input is known upfront (yesterday's data, last hour's logs)           │
│   2. Processing has a defined end (not continuous)                          │
│   3. Output is produced once, not incrementally                            │
│   4. Can be retried: same input → same output (if idempotent)              │
│   5. Latency measured in minutes to hours, not seconds                     │
│                                                                             │
│   CONTRAST WITH STREAM:                                                     │
│   Stream: Input arrives continuously. No "end." Output is incremental.      │
│   Batch: Input is complete. Job finishes. Output is final.                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## MapReduce: The Foundational Model

MapReduce is the conceptual foundation of all distributed batch processing. Even if you never use Hadoop, understanding MapReduce explains why Spark, Flink, and BigQuery work the way they do.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   MAPREDUCE: THREE PHASES                                                    │
│                                                                             │
│   INPUT DATA (distributed across nodes):                                    │
│   ┌───────────────────────────────────────────────────────────────────┐     │
│   │  Node 1: [log1, log2, log3, ...]                                  │     │
│   │  Node 2: [log4, log5, log6, ...]                                  │     │
│   │  Node 3: [log7, log8, log9, ...]                                  │     │
│   └───────────────────────────────────────────────────────────────────┘     │
│                    │                                                        │
│                    ▼                                                        │
│   PHASE 1 — MAP:   Process each record independently.                      │
│                     Emit (key, value) pairs.                               │
│   ┌───────────────────────────────────────────────────────────────────┐     │
│   │  map(log1) → ("us-east", $50)                                     │     │
│   │  map(log2) → ("eu-west", $30)                                     │     │
│   │  map(log3) → ("us-east", $70)                                     │     │
│   │  ...                                                               │     │
│   └───────────────────────────────────────────────────────────────────┘     │
│                    │                                                        │
│                    ▼                                                        │
│   PHASE 2 — SHUFFLE: Group all values by key.                              │
│                       Network transfer between nodes.                      │
│   ┌───────────────────────────────────────────────────────────────────┐     │
│   │  "us-east" → [$50, $70, $20, ...]                                 │     │
│   │  "eu-west" → [$30, $45, ...]                                      │     │
│   │  "ap-south" → [$15, $25, ...]                                     │     │
│   └───────────────────────────────────────────────────────────────────┘     │
│                    │                                                        │
│                    ▼                                                        │
│   PHASE 3 — REDUCE: Aggregate values per key.                              │
│                      Emit final result.                                    │
│   ┌───────────────────────────────────────────────────────────────────┐     │
│   │  reduce("us-east", [$50, $70, $20]) → ("us-east", $140)          │     │
│   │  reduce("eu-west", [$30, $45])       → ("eu-west", $75)          │     │
│   │  reduce("ap-south", [$15, $25])      → ("ap-south", $40)         │     │
│   └───────────────────────────────────────────────────────────────────┘     │
│                                                                             │
│   KEY INSIGHT:                                                              │
│   Map and Reduce are embarrassingly parallel.                              │
│   Shuffle is the expensive part — network transfer of all data.            │
│   Minimizing shuffle = maximizing performance.                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### MapReduce Limitations

| Limitation | Problem | Why It Matters |
|-----------|---------|----------------|
| **Disk I/O** | Every MapReduce step writes to disk | Iterative algorithms (ML) read/write disk N times |
| **Single shuffle** | One Map → one Shuffle → one Reduce | Complex pipelines need chaining (job1 → job2 → ...) |
| **No in-memory** | Intermediate data always on disk | 10-100× slower than in-memory for iterative |
| **Fixed model** | Only Map and Reduce primitives | Joins, windowing require awkward workarounds |

These limitations drove the creation of Spark, Flink, and modern SQL engines.

---

# Part 2: Apache Spark — The Distributed Batch Engine

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   SPARK ARCHITECTURE: DRIVER + EXECUTORS                                     │
│                                                                             │
│   ┌──────────────────────────────────────────────────────────────────┐      │
│   │  DRIVER (Master Process)                                          │      │
│   │  • Parses user code into DAG of stages                           │      │
│   │  • Optimizes query plan (Catalyst optimizer)                     │      │
│   │  • Schedules tasks across executors                              │      │
│   │  • Tracks task progress and handles failures                     │      │
│   └───────────────────────┬──────────────────────────────────────────┘      │
│                           │ assigns tasks                                   │
│              ┌────────────┼────────────┐                                    │
│              ▼            ▼            ▼                                    │
│   ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                       │
│   │  Executor 1  │ │  Executor 2  │ │  Executor 3  │                       │
│   │              │ │              │ │              │                       │
│   │  ┌────────┐  │ │  ┌────────┐  │ │  ┌────────┐  │                       │
│   │  │ Task 1 │  │ │  │ Task 3 │  │ │  │ Task 5 │  │                       │
│   │  │ Task 2 │  │ │  │ Task 4 │  │ │  │ Task 6 │  │                       │
│   │  └────────┘  │ │  └────────┘  │ │  └────────┘  │                       │
│   │              │ │              │ │              │                       │
│   │  Cache       │ │  Cache       │ │  Cache       │                       │
│   │  (in-memory) │ │  (in-memory) │ │  (in-memory) │                       │
│   └──────────────┘ └──────────────┘ └──────────────┘                       │
│                                                                             │
│   CLUSTER MANAGERS: YARN, Kubernetes, Mesos, Standalone                    │
│                                                                             │
│   KEY ADVANTAGE OVER MAPREDUCE:                                             │
│   In-memory caching. Iterative algorithms (ML) are 10-100× faster.        │
│   DAG execution: no forced disk write between stages.                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Spark Execution: DAG, Stages, Tasks

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   SPARK DAG EXECUTION                                                        │
│                                                                             │
│   User code:                                                                │
│   df = spark.read.parquet("orders/")                                        │
│       .filter(col("date") == "2024-03-01")                                  │
│       .groupBy("region")                                                    │
│       .agg(sum("amount").alias("total"))                                    │
│       .write.parquet("output/")                                             │
│                                                                             │
│   Spark transforms this into:                                               │
│                                                                             │
│   ┌────────────────────────────────────────────────────────────────┐        │
│   │  LOGICAL PLAN (what the user wants)                             │        │
│   │  Read → Filter → GroupBy → Aggregate → Write                    │        │
│   └──────────────────────┬─────────────────────────────────────────┘        │
│                          │ Catalyst optimizer                               │
│                          ▼                                                  │
│   ┌────────────────────────────────────────────────────────────────┐        │
│   │  PHYSICAL PLAN (how Spark executes it)                          │        │
│   │  Scan(parquet) → Filter(pushdown) → Partial Agg → Shuffle      │        │
│   │  → Final Agg → Write(parquet)                                   │        │
│   └──────────────────────┬─────────────────────────────────────────┘        │
│                          │                                                  │
│                          ▼                                                  │
│   ┌────────────────────────────────────────────────────────────────┐        │
│   │  DAG OF STAGES:                                                 │        │
│   │                                                                 │        │
│   │  Stage 1 (no shuffle):           Stage 2 (after shuffle):       │        │
│   │  ┌──────────────────────┐       ┌──────────────────────┐       │        │
│   │  │ Scan → Filter →      │  ───► │ Final Agg → Write    │       │        │
│   │  │ Partial Agg          │shuffle│                      │       │        │
│   │  └──────────────────────┘       └──────────────────────┘       │        │
│   │                                                                 │        │
│   │  Stage boundary = shuffle (data redistribution across nodes)   │        │
│   └────────────────────────────────────────────────────────────────┘        │
│                                                                             │
│   RULE: Fewer shuffles = faster job. Spark optimizes to minimize shuffles. │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Spark Optimization Techniques

| Technique | What It Does | When to Use |
|-----------|-------------|-------------|
| **Predicate pushdown** | Filter at source (e.g., Parquet column filter) | Always enabled; design data layout for it |
| **Partition pruning** | Skip entire partitions (e.g., date=2024-03-01) | Partition data by common filter column |
| **Broadcast join** | Send small table to all executors | Small dimension table (<10MB) joined with large fact table |
| **Bucketing** | Pre-shuffle data by join key | Repeated joins on same key (e.g., user_id) |
| **Caching** | Keep intermediate results in memory | Iterative algorithms, reused DataFrames |
| **Adaptive Query Execution (AQE)** | Re-optimize during execution | Spark 3.0+. Handles skew, coalesces partitions dynamically |

### Spark Failure Modes

| Problem | Symptom | Diagnosis | Solution |
|---------|---------|-----------|----------|
| **OOM on driver** | Driver crashes, job fails | Large collect() or broadcast | Avoid collect(); increase driver memory; use take() |
| **OOM on executor** | Task fails, retries, then job fails | Large partition, skewed data | Increase executor memory; repartition; handle skew |
| **Shuffle spill** | Slow job, excessive disk I/O | Shuffle data exceeds executor memory | Increase memory; reduce shuffle data; pre-aggregate |
| **Data skew** | One task takes 100× longer than others | One partition has disproportionate data | Salting: add random prefix to skewed key, aggregate in 2 passes |
| **Small files** | Slow read, many tasks for little data | Too many small output files | Coalesce output; compact files post-write |
| **Long tail** | 99% tasks done, 1 stuck | Speculative execution disabled, or data skew | Enable speculation; increase partition count |

### Data Skew: The Most Common Batch Problem

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   DATA SKEW: WHY ONE TASK TAKES 100× LONGER                                 │
│                                                                             │
│   GROUP BY user_id:                                                         │
│   ┌──────────────────────────────────────────────────────────┐              │
│   │  User A:    ███████████████████████████████████ 50M rows │              │
│   │  User B:    ██ 500K rows                                 │              │
│   │  User C:    █ 100K rows                                  │              │
│   │  User D:    █ 80K rows                                   │              │
│   │  ...                                                     │              │
│   └──────────────────────────────────────────────────────────┘              │
│                                                                             │
│   User A's partition: 50M rows → one executor processes for 2 hours        │
│   All other partitions: done in 2 minutes                                  │
│   Job completion time: 2 hours (dominated by skewed partition)             │
│                                                                             │
│   FIX — SALTING:                                                            │
│   1. Add random salt (0-9) to skewed key: user_A_0, user_A_1, ...          │
│   2. First aggregation: GROUP BY (user_id, salt) → 10 partitions for A    │
│   3. Second aggregation: GROUP BY user_id → combine salted results         │
│   4. Result: 50M rows split into 10 × 5M rows → 12 minutes, not 2 hours  │
│                                                                             │
│   SPARK 3.0 AQE: Handles skew automatically by splitting large partitions │
│   during execution. Enable: spark.sql.adaptive.enabled = true              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 3: Data Pipelines — ETL and ELT

## Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   DATA PIPELINE: EXTRACT → TRANSFORM → LOAD                                 │
│                                                                             │
│   SOURCES                 PROCESSING              DESTINATIONS              │
│   ┌─────────────┐        ┌─────────────┐         ┌─────────────┐           │
│   │ Databases   │        │             │         │ Data        │           │
│   │ (MySQL,     │        │ Transform:  │         │ Warehouse   │           │
│   │  Postgres)  │──┐     │ • Clean     │    ┌──► │ (Snowflake, │           │
│   └─────────────┘  │     │ • Validate  │    │    │  BigQuery,  │           │
│   ┌─────────────┐  │     │ • Aggregate │    │    │  Redshift)  │           │
│   │ Files       │  ├───► │ • Join      │────┤    └─────────────┘           │
│   │ (S3, GCS,   │  │     │ • Enrich    │    │    ┌─────────────┐           │
│   │  HDFS)      │  │     │ • Dedupe    │    │    │ Data Lake   │           │
│   └─────────────┘  │     │             │    └──► │ (S3, GCS,   │           │
│   ┌─────────────┐  │     └─────────────┘         │  Delta Lake)│           │
│   │ APIs        │──┘                             └─────────────┘           │
│   │ (REST, gRPC)│                                ┌─────────────┐           │
│   └─────────────┘                                │ Downstream  │           │
│   ┌─────────────┐                                │ Services    │           │
│   │ Kafka       │──────────────────────────────► │ (ML, Search,│           │
│   │ (CDC, events)                                │  Analytics) │           │
│   └─────────────┘                                └─────────────┘           │
│                                                                             │
│   ORCHESTRATION: Airflow, Prefect, Dagster                                 │
│   MONITORING: Job duration, data freshness, row counts, schema drift       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## ETL vs ELT

| Property | ETL | ELT |
|----------|-----|-----|
| **Transform location** | Before loading (in Spark, Airflow) | After loading (in warehouse SQL) |
| **Raw data stored?** | No (only transformed) | Yes (raw in lake, transformed in warehouse) |
| **Flexibility** | Low (must re-extract to re-transform) | High (re-transform with SQL anytime) |
| **Cost** | Lower storage (only transformed) | Higher storage (raw + transformed) |
| **Schema changes** | Require pipeline changes | Handle with SQL, dbt |
| **Use case** | Legacy, specific transform needs | Modern data stack, analytics-heavy |
| **Tools** | Spark, custom code | dbt, SQL, warehouse-native transforms |

### The Modern Data Stack

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   MODERN DATA STACK: ELT PATTERN                                             │
│                                                                             │
│   ┌──────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────┐     │
│   │ Sources  │    │ Ingestion    │    │ Warehouse    │    │ BI/ML    │     │
│   │          │──► │              │──► │              │──► │          │     │
│   │ DB, API, │    │ Fivetran,    │    │ Snowflake,   │    │ Looker,  │     │
│   │ SaaS     │    │ Airbyte,     │    │ BigQuery,    │    │ Tableau, │     │
│   │          │    │ Stitch       │    │ Redshift     │    │ ML model │     │
│   └──────────┘    └──────────────┘    └──────┬───────┘    └──────────┘     │
│                                              │                              │
│                                     ┌────────┴────────┐                     │
│                                     │   dbt           │                     │
│                                     │ (transform      │                     │
│                                     │  with SQL,      │                     │
│                                     │  version        │                     │
│                                     │  controlled)    │                     │
│                                     └─────────────────┘                     │
│                                                                             │
│   KEY SHIFT: Transform happens IN the warehouse, not before it.            │
│   Raw data is always available for re-processing.                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Change Data Capture (CDC)

CDC extracts changes from source databases incrementally—no full table scans.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   CDC: INCREMENTAL EXTRACTION                                                │
│                                                                             │
│   FULL EXTRACT (naive):                                                     │
│   Every run: SELECT * FROM orders → copy all 100M rows                     │
│   Problem: 100M rows × 4 times/day = 400M row reads. Slow. Expensive.      │
│                                                                             │
│   CDC (smart):                                                              │
│   Every run: read only CHANGES since last run                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Source DB (Postgres)                                                │   │
│   │  ┌───────────────┐                                                  │   │
│   │  │  WAL (write-  │ ──► Debezium ──► Kafka ──► Consumer             │   │
│   │  │  ahead log)   │     (reads WAL)   (CDC     (loads to            │   │
│   │  └───────────────┘                   topic)    warehouse)          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Methods:                                                                  │
│   • WAL-based (Debezium): reads DB transaction log. No query load on DB.  │
│   • Timestamp-based: SELECT WHERE updated_at > last_run. Simple but       │
│     misses deletes and has clock skew issues.                              │
│   • Trigger-based: DB triggers write changes to changelog table. Overhead. │
│                                                                             │
│   RECOMMENDATION: WAL-based (Debezium) for production. Most reliable,     │
│   captures deletes, no query load on source.                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 4: Data Storage Layers — Lake, Warehouse, Lakehouse

## Comparison

| Property | Data Lake | Data Warehouse | Lakehouse |
|----------|-----------|----------------|-----------|
| **Storage** | Object store (S3, GCS) | Managed (Snowflake, BQ) | Object store + metadata layer |
| **Format** | Any (Parquet, JSON, CSV) | Proprietary internal | Open (Parquet, ORC) |
| **Schema** | Schema-on-read | Schema-on-write | Schema-on-write with flexibility |
| **Query engine** | Spark, Presto, Athena | Built-in SQL | Spark, Presto, built-in |
| **ACID transactions** | No (without Delta/Iceberg) | Yes | Yes (Delta Lake, Iceberg) |
| **Cost** | Cheap storage, pay-per-query | Expensive compute | Cheap storage, pay-per-query |
| **Use case** | Raw data, ML training | BI, analytics, reporting | Unified: raw + analytics |
| **Governance** | Manual | Built-in | Emerging (Unity Catalog) |

### Table Formats: Delta Lake, Iceberg, Hudi

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   TABLE FORMATS: ACID ON OBJECT STORAGE                                      │
│                                                                             │
│   Problem: Object stores (S3) don't support transactions.                   │
│   Writing new data while reading = inconsistent results.                    │
│                                                                             │
│   Solution: Table formats add a metadata layer on top of object storage.   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Object Store (S3/GCS)                                               │   │
│   │  ├── data/                                                          │   │
│   │  │   ├── part-0001.parquet                                          │   │
│   │  │   ├── part-0002.parquet                                          │   │
│   │  │   └── part-0003.parquet                                          │   │
│   │  └── _delta_log/ (or metadata/)                                     │   │
│   │      ├── 000001.json  ← "add part-0001, part-0002"                  │   │
│   │      ├── 000002.json  ← "add part-0003"                            │   │
│   │      └── 000003.json  ← "remove part-0001, add part-0004"          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   CAPABILITIES:                                                             │
│   • ACID transactions (atomic writes, snapshot isolation)                   │
│   • Time travel (query data as of yesterday)                               │
│   • Schema evolution (add columns without rewriting)                       │
│   • Upserts and deletes (MERGE INTO)                                       │
│                                                                             │
│   Delta Lake: Databricks. Spark-native. Most mature.                       │
│   Iceberg: Netflix/Apache. Engine-agnostic. Growing fast.                  │
│   Hudi: Uber/Apache. Good for CDC and incremental processing.             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 5: Orchestration — Managing Pipeline DAGs

## Why Orchestration Matters

A data pipeline isn't one job—it's a directed acyclic graph (DAG) of dependent jobs. Orchestration handles scheduling, dependencies, retries, and monitoring.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   PIPELINE DAG: DEPENDENCIES BETWEEN JOBS                                    │
│                                                                             │
│   ┌──────────┐     ┌──────────┐     ┌──────────┐                           │
│   │ Extract  │     │ Extract  │     │ Extract  │                           │
│   │ Orders   │     │ Products │     │ Users    │                           │
│   └────┬─────┘     └────┬─────┘     └────┬─────┘                           │
│        │                │                │                                  │
│        └────────┬───────┘                │                                  │
│                 ▼                        │                                  │
│        ┌──────────────┐                  │                                  │
│        │ Join Orders  │◄─────────────────┘                                  │
│        │ + Products   │                                                     │
│        │ + Users      │                                                     │
│        └──────┬───────┘                                                     │
│               │                                                             │
│        ┌──────┴──────┐                                                      │
│        ▼             ▼                                                      │
│   ┌──────────┐  ┌──────────┐                                               │
│   │ Revenue  │  │ User     │                                               │
│   │ Report   │  │ Cohort   │                                               │
│   │ (daily)  │  │ Analysis │                                               │
│   └──────────┘  └──────────┘                                               │
│                                                                             │
│   ORCHESTRATOR RESPONSIBILITIES:                                            │
│   • Schedule: run daily at 2 AM UTC                                        │
│   • Dependencies: Revenue Report waits for Join to complete                │
│   • Retry: if Extract Orders fails, retry 3× with backoff                  │
│   • Alert: if still failing after retries, page on-call                    │
│   • Idempotency: re-running yesterday's pipeline produces same result     │
│   • Backfill: reprocess last 30 days after bug fix                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Orchestration Tools

| Tool | Architecture | Pros | Cons |
|------|-------------|------|------|
| **Apache Airflow** | Python DAGs, central scheduler, workers | Widely adopted, large community, plugin ecosystem | Operational overhead, DAG parsing slow at scale, testing is hard |
| **Prefect** | Python, hybrid cloud/self-hosted | Better developer experience, dynamic DAGs, native observability | Smaller community, newer |
| **Dagster** | Python, asset-based, type-safe | Asset lineage, type checking, testing framework, better dev UX | Learning curve, newer |
| **dbt** | SQL transforms only, not general orchestrator | SQL-native, version controlled, documentation | Only transforms; needs orchestrator for extraction |
| **Temporal** | Workflow engine, not data-specific | Durable execution, language SDKs, retry/timeout built-in | General purpose; not data-pipeline specific |
| **Cloud-native** | Step Functions, Cloud Composer, Dataflow | Managed, integrated with cloud services | Vendor lock-in, less flexibility |

### Airflow DAG Patterns

| Pattern | Description | When to Use |
|---------|-------------|-------------|
| **Date-partitioned** | Each run processes one date partition | Daily/hourly ETL |
| **Sensor + trigger** | Wait for external condition (file exists, API ready) | Cross-system dependencies |
| **Fan-out/fan-in** | Parallelize tasks, then join results | Independent sub-tasks |
| **Backfill** | Re-run historical dates | After bug fix or schema change |
| **Short-circuit** | Skip downstream if condition not met | Conditional processing |

---

# Part 6: Idempotency and Exactly-Once for Batch

## Why Idempotency Matters

Batch jobs fail. Networks partition. Nodes crash. If re-running a job produces different results, you have a data quality problem.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   IDEMPOTENCY: RE-RUN = SAME RESULT                                         │
│                                                                             │
│   NON-IDEMPOTENT (dangerous):                                               │
│   Run 1: INSERT INTO sales VALUES (...)  → 1000 rows                       │
│   Run 2: INSERT INTO sales VALUES (...)  → 2000 rows (duplicates!)         │
│                                                                             │
│   IDEMPOTENT (safe):                                                        │
│   Run 1: DELETE WHERE date='2024-03-01'; INSERT WHERE date='2024-03-01';  │
│           → 1000 rows                                                       │
│   Run 2: DELETE WHERE date='2024-03-01'; INSERT WHERE date='2024-03-01';  │
│           → 1000 rows (same result)                                        │
│                                                                             │
│   STRATEGIES:                                                               │
│   1. Partition overwrite: write to date partition; overwrite on re-run     │
│   2. Upsert with key: MERGE INTO on primary key                           │
│   3. Tombstone + insert: delete existing, then insert fresh                │
│   4. Atomic swap: write to temp table, then swap with production table    │
│                                                                             │
│   MOST COMMON: Partition by date. Each run overwrites its partition.       │
│   Re-run yesterday → only yesterday's data is affected.                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Exactly-Once Semantics in Batch

| Approach | How It Works | Guarantees | Trade-off |
|----------|-------------|------------|-----------|
| **Partition overwrite** | Write entire partition atomically | Idempotent (overwrite = same result) | Must process full partition each time |
| **Upsert (MERGE)** | Insert or update based on key | Idempotent (upsert = same result) | Requires unique key; slower than append |
| **Two-phase commit** | Write + commit marker (success file) | Atomic (incomplete run has no marker) | Complexity; reader checks for marker |
| **Transactional write** | Delta Lake / Iceberg ACID writes | Atomic, isolated | Requires table format support |

---

# Part 7: Lambda vs Kappa Architecture

## When You Need Both Batch and Stream

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   LAMBDA ARCHITECTURE: BATCH + STREAM IN PARALLEL                            │
│                                                                             │
│                          ┌──────────────┐                                   │
│                     ┌──► │ Batch Layer  │ ──► Batch View                    │
│                     │    │ (Spark, daily │     (complete,                    │
│   All Data ─────────┤    │  reprocesses  │      accurate)                   │
│   (Kafka)           │    │  everything)  │         │                        │
│                     │    └──────────────┘         │                        │
│                     │                             ▼                        │
│                     │                     ┌──────────────┐                  │
│                     │                     │ Serving Layer│ ← Query here    │
│                     │                     │ (merge batch │                  │
│                     │                     │  + speed)    │                  │
│                     │                     └──────────────┘                  │
│                     │                             ▲                        │
│                     │    ┌──────────────┐         │                        │
│                     └──► │ Speed Layer  │ ──► Speed View                    │
│                          │ (Flink, real- │     (recent,                     │
│                          │  time stream) │      approximate)               │
│                          └──────────────┘                                   │
│                                                                             │
│   PROS: Accurate (batch) + low-latency (stream)                            │
│   CONS: Two codebases, two pipelines, merge logic, operational burden     │
│                                                                             │
│   ─────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│   KAPPA ARCHITECTURE: STREAM ONLY                                           │
│                                                                             │
│   All Data ──► Stream Layer ──► Serving Layer                               │
│   (Kafka)      (Flink)          (query here)                                │
│                                                                             │
│   For reprocessing: replay Kafka from beginning                            │
│   Requires: Kafka with sufficient retention (or tiered storage)            │
│                                                                             │
│   PROS: One codebase, simpler operations                                   │
│   CONS: Reprocessing is slow (replay entire stream); not all workloads fit │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### When to Use Which

| Factor | Lambda | Kappa |
|--------|--------|-------|
| **Need exact batch results + real-time** | Yes | — |
| **Complex reprocessing logic** | Better (dedicated batch) | Harder (replay stream) |
| **Operational simplicity** | — | Yes (one pipeline) |
| **Kafka retention feasible?** | Not required | Required for reprocessing |
| **Team size** | Larger (two pipelines) | Smaller (one pipeline) |

**Staff insight**: Lambda architecture is often over-engineered for most use cases. Start with Kappa (stream only) if Kafka retention is feasible. Add a batch layer only when reprocessing requirements exceed stream replay capabilities—typically when historical data exceeds Kafka retention.

---

# Part 8: Data Quality and Validation

## The Data Quality Stack

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   DATA QUALITY: TRUST YOUR DATA                                              │
│                                                                             │
│   Layer 1 — SCHEMA VALIDATION (at ingestion):                               │
│   • Column types match expected (id is int, not string)                     │
│   • Required columns present                                                │
│   • No unexpected columns (schema drift detection)                          │
│                                                                             │
│   Layer 2 — VALUE VALIDATION (at transform):                                │
│   • Null checks: critical fields not null                                   │
│   • Range checks: amount > 0, date within expected range                   │
│   • Referential: order.user_id exists in users table                       │
│   • Uniqueness: no duplicate primary keys                                  │
│                                                                             │
│   Layer 3 — STATISTICAL VALIDATION (at load):                               │
│   • Row count: within expected range (±20% of historical)                  │
│   • Distribution: no sudden spikes or drops                                │
│   • Freshness: data arrived within expected time window                    │
│   • Completeness: all expected partitions present                          │
│                                                                             │
│   Layer 4 — CROSS-PIPELINE VALIDATION (post-load):                          │
│   • Sum of parts = whole (regional totals = global total)                  │
│   • Source-to-target reconciliation (DB count = warehouse count)           │
│   • Cross-pipeline consistency (orders pipeline ∩ payments pipeline)       │
│                                                                             │
│   TOOLS: Great Expectations, dbt tests, Soda, Monte Carlo, custom checks  │
│                                                                             │
│   QUARANTINE: Bad records → dead-letter table for investigation.           │
│   Don't fail the entire pipeline for 0.01% bad records.                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Data Contracts

| Element | Description |
|---------|-------------|
| **Schema** | Exact column names, types, nullable |
| **SLAs** | Data available by 6 AM UTC, fresher than 2 hours |
| **Volume** | Expected row count range per day |
| **Quality rules** | No nulls in user_id, amount > 0 |
| **Owner** | Producing team responsible for contract |
| **Consumer** | Teams that depend on this data |
| **Breaking change policy** | 30-day notice, expand-contract |

---

# Part 9: Batch Job Monitoring and Debugging

## Key Metrics

| Metric | What to Track | Alert Threshold |
|--------|--------------|-----------------|
| **Job duration** | Time from start to finish | > 2× historical average |
| **Data freshness** | Time since last successful load | > SLA threshold |
| **Row counts** | Input rows, output rows, filtered rows | ±30% from expected |
| **Error rate** | Failed records / total records | > 1% (configurable) |
| **Resource usage** | CPU, memory, disk, shuffle | > 80% capacity |
| **Stage duration** | Time per stage in Spark DAG | One stage > 50% of total time |
| **Retry count** | Number of task retries | > 3 retries per stage |

## Debugging Slow Batch Jobs

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   DEBUGGING DECISION TREE: WHY IS THE BATCH JOB SLOW?                       │
│                                                                             │
│   Is the job slow overall, or is one stage slow?                            │
│   │                                                                         │
│   ├── One stage slow (others fast)                                          │
│   │   │                                                                     │
│   │   ├── Shuffle stage?                                                    │
│   │   │   └── Too much data shuffled. Pre-aggregate before shuffle.        │
│   │   │       Broadcast small tables. Check for unnecessary repartition.   │
│   │   │                                                                     │
│   │   ├── One task much slower than siblings?                               │
│   │   │   └── DATA SKEW. Check key distribution. Salt skewed keys.         │
│   │   │       Enable AQE (spark.sql.adaptive.skewJoin.enabled).            │
│   │   │                                                                     │
│   │   └── All tasks equally slow?                                           │
│   │       └── Resource bottleneck. Check: CPU? Memory? Disk I/O?           │
│   │           Increase executor resources or partition count.              │
│   │                                                                         │
│   └── All stages slow                                                       │
│       │                                                                     │
│       ├── Input data grew significantly?                                    │
│       │   └── Scale cluster. Increase parallelism.                         │
│       │                                                                     │
│       ├── Reading many small files?                                         │
│       │   └── Compact input files. Use coalesce or file listing cache.     │
│       │                                                                     │
│       └── GC pauses?                                                        │
│           └── Increase memory. Reduce object creation. Use DataFrame       │
│               API (not RDD). Check for large broadcasts or collects.       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 10: Cost Optimization for Batch

## Compute Cost Strategies

| Strategy | Savings | Trade-off |
|----------|---------|-----------|
| **Spot/preemptible instances** | 60–80% | Jobs may be interrupted; need checkpointing |
| **Ephemeral clusters** | 40–60% | Spin up/tear down overhead (5-10 min) |
| **Right-sizing** | 20–40% | Requires monitoring; over-provisioning is common |
| **Auto-scaling** | 10–30% | Adds complexity; may not help short jobs |
| **Serverless (BigQuery, Athena)** | Variable | Pay-per-query; no cluster management |

## Storage Cost Strategies

| Strategy | Savings | When |
|----------|---------|------|
| **Columnar format (Parquet)** | 60–80% vs CSV | Always for analytics workloads |
| **Compression (Snappy, Zstd)** | 30–50% | Always; Snappy for speed, Zstd for ratio |
| **Partitioning** | Skip entire directories | Frequently filtered columns (date, region) |
| **Lifecycle policies** | Auto-delete old data | Tiered: hot (30d) → warm (90d) → cold (1yr) → delete |
| **Compaction** | Reduce file count | Periodic compaction of small files |

### Back-of-Envelope: Batch Job Cost

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   COST ESTIMATION: DAILY ETL JOB                                            │
│                                                                             │
│   Data: 1 TB input, daily                                                   │
│   Processing: 2 hours on 10-node Spark cluster                             │
│                                                                             │
│   COMPUTE:                                                                  │
│   10 nodes × r5.2xlarge ($0.504/hr) × 2 hrs = $10.08/day                  │
│   With spot instances (70% savings): $3.02/day                             │
│   Monthly: $91 (spot) vs $302 (on-demand)                                  │
│                                                                             │
│   STORAGE:                                                                  │
│   Input: 1 TB/day × 30 days × $0.023/GB/month = $690/month               │
│   Output: 200 GB/day × 30 days × $0.023/GB/month = $138/month            │
│   With lifecycle (delete after 90 days): same but bounded                  │
│                                                                             │
│   TOTAL: ~$920/month (spot + S3)                                           │
│                                                                             │
│   SERVERLESS ALTERNATIVE (BigQuery):                                        │
│   1 TB scanned × $5/TB = $5/day = $150/month                              │
│   Cheaper if job is simple SQL. More expensive if complex multi-pass.      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 11: Batch vs Stream Decision Framework

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   DECISION TREE: BATCH vs STREAM vs BOTH                                     │
│                                                                             │
│   Need result in < 1 minute?                                                │
│   │                                                                         │
│   ├── YES → STREAM (Flink, Kafka Streams)                                   │
│   │                                                                         │
│   └── NO → Is the input bounded (finite dataset)?                           │
│            │                                                                │
│            ├── YES → BATCH (Spark, SQL)                                     │
│            │                                                                │
│            └── NO → Need exact results from historical data?                │
│                     │                                                       │
│                     ├── YES → BATCH + STREAM (Lambda)                       │
│                     │         Batch for accuracy, stream for freshness      │
│                     │                                                       │
│                     └── NO → STREAM with replay (Kappa)                     │
│                              Reprocess by replaying Kafka                  │
│                                                                             │
│   ─────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│   ADDITIONAL SIGNALS FOR BATCH:                                             │
│   ✓ Full dataset aggregation (daily revenue across all regions)            │
│   ✓ Complex joins across multiple large datasets                           │
│   ✓ ML model training on historical data                                   │
│   ✓ Data warehouse loading (nightly refresh)                               │
│   ✓ Backfill after schema change or bug fix                                │
│                                                                             │
│   ADDITIONAL SIGNALS FOR STREAM:                                            │
│   ✓ Event-driven actions (fraud alert within seconds)                      │
│   ✓ Real-time dashboards (live metrics, monitoring)                        │
│   ✓ Incremental updates (user profile enrichment as events arrive)         │
│   ✓ Continuous data sync between systems                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 12: Production Incidents and Failure Modes

## Incident 1: Data Skew Causes 8-Hour Job

**Scenario**: Daily aggregation job groups by `merchant_id`. One merchant (Amazon) has 40% of all orders. One Spark task processes 40% of data while others finish in minutes.

**Impact**: Job SLA is 4 hours. Job runs for 8 hours. Downstream reports delayed. Executive dashboard stale.

**Root cause**: No skew handling. `GROUP BY merchant_id` puts all Amazon orders on one partition.

**Fix**: Salted aggregation. First pass: group by `(merchant_id, salt % 10)`. Second pass: group by `merchant_id` and sum partial results. Job time reduced to 90 minutes.

**Lesson**: Always check key distribution before GROUP BY at scale. The top 1% of keys often contain 50%+ of data.

## Incident 2: Pipeline Produces Duplicates After Retry

**Scenario**: ETL pipeline failed mid-write to warehouse. Operator re-ran the pipeline. Pipeline appended data instead of overwriting.

**Impact**: Revenue report showed 2× actual revenue. Discovered 6 hours later by finance team.

**Root cause**: Pipeline used `INSERT INTO` (append) instead of partition overwrite or upsert. Not idempotent.

**Fix**: Changed to partition overwrite: `INSERT OVERWRITE TABLE revenue PARTITION (date='2024-03-01')`. Re-run now replaces, not appends.

**Lesson**: Every batch job must be idempotent. If re-running produces different results, you will produce corrupt data.

## Incident 3: Airflow DAG Deadlock

**Scenario**: Two DAGs depend on each other's outputs. DAG A waits for DAG B's table. DAG B waits for DAG A's table. Both block forever.

**Impact**: Both pipelines stuck. Downstream consumers receive no fresh data for 12 hours until on-call investigates.

**Root cause**: Circular dependency introduced when a new data source was added.

**Fix**: Removed circular dependency by introducing a shared intermediate table. Added DAG dependency validation in CI (detect cycles before deployment).

**Lesson**: Orchestration DAGs must be truly acyclic. Add automated cycle detection.

## Incident 4: Small Files Problem

**Scenario**: Streaming ingestion writes to S3 every 30 seconds, creating thousands of tiny Parquet files per hour. Subsequent Spark batch job reads these files.

**Impact**: Batch job spends 90% of time listing and opening files, only 10% on actual processing. Job takes 4 hours instead of 30 minutes.

**Root cause**: No compaction. File listing on S3 is slow with millions of small files.

**Fix**: Added hourly compaction job that merges small files into ~128MB Parquet files. Batch job time reduced to 25 minutes.

**Lesson**: Object stores are optimized for large files. Compaction is a maintenance task that must be planned, not an afterthought.

## Incident 5: Clock Skew in Timestamp-Based CDC

**Scenario**: Incremental extraction uses `SELECT * FROM orders WHERE updated_at > ?` with last run time. Source database server clock drifted 5 minutes ahead, then was corrected by NTP.

**Impact**: Orders updated during the 5-minute drift window were never extracted. Warehouse missing ~2,000 orders.

**Root cause**: Timestamp-based CDC is vulnerable to clock skew. Correction made records "disappear" from the window.

**Fix**: Switched to WAL-based CDC (Debezium). WAL uses logical sequence numbers, not timestamps. Also added overlap window: query `updated_at > (last_run - 10 minutes)` with deduplication at load.

**Lesson**: Timestamp-based CDC has fundamental clock-skew vulnerabilities. Use WAL-based CDC for production.

---

# Part 13: Interview Essentials

## Quick-Fire Answers

**"Batch vs stream?"** — "Batch for high-throughput, bounded data, latency of hours OK—ETL, reports, ML training. Stream for low-latency, event-driven—dashboards, alerts, fraud detection. Batch: process 1TB in 2 hours. Stream: process 10K events/sec in real time. Many systems need both: batch for backfill and accuracy, stream for freshness."

**"How do you design a data pipeline?"** — "Extract from source (DB via CDC, files, APIs), transform (clean, validate, aggregate), load to destination (warehouse, lake). Orchestrate with Airflow or Dagster—DAG of tasks with dependencies and retries. Key requirements: idempotency (re-run produces same result via partition overwrite), data quality checks at each stage, SLAs for freshness and completeness."

**"When does a cron job need to become Spark?"** — "When: (1) data exceeds single-node memory (>50GB), (2) runtime exceeds SLA, (3) need parallelism for throughput. Single-node works surprisingly long if you process in chunks. Move to Spark when you need distributed shuffle (joins, group-by across large datasets). For SQL-only workloads, consider serverless (BigQuery, Athena) before Spark—simpler to operate."

**"What's data skew and how do you handle it?"** — "Data skew means one partition has disproportionately more data than others. In a GROUP BY, if one key has 50% of data, one executor processes 50% while others sit idle. Fix: salting—add random suffix to skewed key, aggregate in two passes. Spark 3.0+ has Adaptive Query Execution that handles skew automatically."

**"ETL vs ELT?"** — "ETL transforms before loading—smaller storage, less flexible. ELT loads raw data then transforms in the warehouse with SQL—more flexible, supports re-processing. Modern data stack (Fivetran + dbt + Snowflake) is ELT. ETL with Spark for complex transformations that exceed SQL capabilities."

**"Lambda vs Kappa?"** — "Lambda: separate batch and stream pipelines, merged in serving layer. Accurate batch + low-latency stream but two codebases. Kappa: single stream pipeline, replay for reprocessing. Simpler but requires sufficient Kafka retention. Start with Kappa; add batch layer only when reprocessing needs exceed stream replay."

## Staff-Level Interview Walkthrough: "Design a Data Pipeline for E-Commerce Analytics"

**Step 1 — Clarify requirements**: "What's the data volume? 10M orders/day. What's the freshness SLA? Reports by 6 AM for previous day. What downstream consumers? Executive dashboard, ML team, finance reconciliation."

**Step 2 — Source extraction**: "CDC from Postgres order database using Debezium → Kafka. WAL-based, no query load on production DB. Also extract from product catalog (full dump, small table) and user profiles (incremental by updated_at with dedup)."

**Step 3 — Processing**: "Daily Spark job triggered by Airflow at 1 AM UTC. Read from Kafka topic (yesterday's partition) + product catalog + users. Join, aggregate by region/category/day. Output: daily_revenue, user_cohorts, product_performance."

**Step 4 — Loading**: "Write to Snowflake via partition overwrite (idempotent). Date-partitioned: `daily_revenue/date=2024-03-01/`. Re-run replaces, doesn't duplicate."

**Step 5 — Data quality**: "Validation at each stage: row count within ±20% of expected, no null order_ids, amount > 0, all regions present. Quarantine bad records to dead-letter table. Alert if quarantine exceeds 1%."

**Step 6 — Monitoring**: "Job duration, data freshness (last successful load timestamp), row counts (input vs output), Spark stage durations. Alert if job not complete by 5 AM (1-hour buffer before 6 AM SLA)."

**Step 7 — Cost**: "Ephemeral Spark cluster on spot instances. 10 nodes × 2 hours/day. ~$3/day compute. Storage: ~1 TB/day in S3, lifecycle to Glacier after 90 days. Total: ~$300/month."

---

## Appendix: Spark Configuration Quick Reference

| Config | Purpose | Recommended |
|--------|---------|-------------|
| `spark.sql.adaptive.enabled` | Adaptive Query Execution | `true` (Spark 3.0+) |
| `spark.sql.adaptive.skewJoin.enabled` | Auto-handle data skew | `true` |
| `spark.sql.shuffle.partitions` | Number of shuffle partitions | 200 default; increase for large data |
| `spark.executor.memory` | Memory per executor | 4-8 GB typical; increase for large partitions |
| `spark.executor.cores` | Cores per executor | 4-5 (avoid too many GC threads) |
| `spark.sql.files.maxPartitionBytes` | Max partition size for file scan | 128 MB default |
| `spark.speculation` | Enable speculative execution | `true` for long jobs with potential stragglers |

## Appendix: Airflow Best Practices

| Practice | Why |
|----------|-----|
| **Idempotent tasks** | Re-run produces same result |
| **Atomic tasks** | Each task succeeds or fails fully; no partial state |
| **Date-parameterized** | Each run processes a specific execution_date |
| **SLA monitoring** | Alert if task exceeds expected duration |
| **Testing** | Test DAG parsing, task logic, and dependencies in CI |
| **Small tasks** | Avoid monolithic tasks; break into stages for debuggability |
| **Templated queries** | Use Jinja templates for dates, parameters |

## Appendix: Common Misconceptions

| Misconception | Reality |
|---------------|---------|
| "Batch is old, stream is modern" | Batch is the right tool when latency of hours is acceptable. Most analytics is batch. |
| "Spark replaces SQL" | For SQL-only workloads, serverless SQL (BigQuery, Athena) is simpler and often cheaper. |
| "More partitions = faster" | Too many partitions = scheduling overhead, small files. Balance partition size (~128MB). |
| "Kafka replaces batch" | Kafka enables stream processing. Batch remains essential for reprocessing, backfill, and complex aggregations over large datasets. |
| "Airflow is a data processing tool" | Airflow is an orchestrator. It schedules and monitors jobs but doesn't process data itself. |
| "Lambda architecture is always needed" | Start with one approach (usually batch or Kappa). Lambda adds operational complexity. Only use when both accuracy and real-time are non-negotiable. |
| "Data quality is the data team's problem" | Data quality is a shared responsibility. Producers must meet data contracts. Consumers must validate at ingestion. |

---

## Further Reading

| Topic | Resource |
|-------|----------|
| Batch processing foundations | *Designing Data-Intensive Applications* (Kleppmann) — Ch 10 |
| Stream processing | *Designing Data-Intensive Applications* (Kleppmann) — Ch 11 |
| Apache Spark | [Apache Spark docs](https://spark.apache.org/) |
| Apache Flink | [Apache Flink docs](https://flink.apache.org/) |
| Apache Airflow | [Airflow docs](https://airflow.apache.org/) |
| dbt | [dbt docs](https://docs.getdbt.com/) |
| Delta Lake | [Delta Lake docs](https://delta.io/) |
| Data engineering | *Fundamentals of Data Engineering* (Reis, Housley) |
| Great Expectations | [greatexpectations.io](https://greatexpectations.io/) |

---

*This supplement supports Chapter 24 (Queues, Logs, Streams), Chapter 33 (Event-Driven), and Chapter 50 (Background Job Queue). Read alongside Ch 28 Supplement (Data Encoding) for serialization in pipelines, Ch 33 Supplement (Kafka Internals) for stream source details, and Ch 69 (Log Aggregation) for batch ingestion of logs.*

---

# Exercises and Brainstorming

## Exercise 1: 10× Data Volume Overnight

Your nightly Spark batch job processes 100 GB of user event data in 2 hours, finishing at 6 AM before business hours. A viral product launch causes data volume to spike to 1 TB overnight.

1. What breaks first? Walk through: Spark executor memory, shuffle partitions, S3 I/O, Airflow task timeout.
2. The job is still running at 10 AM. Business stakeholders need the daily report. What do you do right now?
3. Design two fixes: one for immediate mitigation (today), one for long-term resilience. What's the cost difference between auto-scaling the Spark cluster and pre-provisioning headroom?
4. Your shuffle partition count is set to 200 (Spark default). At 1 TB, what should it be? How do you calculate the right number?
5. How would you instrument the job to detect "this run is tracking 3× over normal duration" within the first 20 minutes?

---

## Exercise 2: Cost Reduction — Redesign for 1/10 the Budget

Your current batch pipeline costs $30,000/month:
- Spark cluster on on-demand EC2: $18,000
- S3 storage (hot tier, all data): $8,000
- Data transfer (S3 → Redshift): $4,000

You've been asked to cut pipeline costs by 90% without changing business SLAs (daily reports by 7 AM).

1. Identify the highest-ROI optimization in each cost category.
2. On-demand → spot instances: what's the risk, and how do you make Spark checkpointing work with spot interruptions?
3. Hot S3 → tiered storage (S3 Intelligent-Tiering, Glacier for data > 90 days): which data can safely be archived? What's the query latency trade-off?
4. Replace Spark with serverless SQL (Athena on S3 Parquet): when does this make sense? What's the break-even point in query frequency?
5. Produce a revised cost estimate with your optimizations applied.

---

## Exercise 3: PII Deletion — GDPR Retrofit

A new compliance requirement: all PII must be purged within 72 hours of a user deletion request. Your batch pipeline has:
- Raw event data in S3 (partitioned by date, retained 2 years)
- Aggregated metrics in Redshift (anonymized, retained 5 years)
- User profile snapshots in S3 (daily, retained 1 year)
- Derived ML features in a feature store (retained indefinitely)

1. For each data store, describe the deletion mechanism and its complexity.
2. S3 partitioning by date makes row-level deletion expensive. What are your options? (Delete and rewrite partition vs. cryptographic erasure vs. pseudonymization)
3. Aggregated metrics contain user counts and click rates but not user IDs. Does GDPR require you to delete these? When is aggregated data no longer "personal data"?
4. The feature store has no deletion API. How do you handle this gap? What's the escalation path?
5. Design an end-to-end deletion pipeline: user deletes account → what triggers, what runs, what's the verification step, what's the audit trail?

---

## Exercise 4: Airflow DAG Deadlock

Your Airflow DAG has 50 tasks across 5 upstream data sources. Monday morning, the DAG stops making progress. No tasks are failing — they're all stuck in `queued` state. The Airflow UI shows 50 tasks waiting and 0 running.

1. What are the three most likely causes of this symptom?
2. How do you distinguish between: (a) worker capacity exhaustion, (b) a deadlock in task dependencies, (c) a database connection pool exhaustion in Airflow's metadata DB?
3. Your DAG has a critical dependency: Task A and Task B each wait for the other's output (circular dependency, introduced by a recent schema change). How do you detect this from the Airflow graph? How do you break the cycle?
4. You fix the immediate issue. What monitoring do you add to detect this class of problem earlier: (a) task queue depth alert, (b) slot utilization alert, (c) DAG run duration SLA?
5. Write a 5-line incident runbook for "DAG stuck in queued state."

---

## Exercise 5: Lambda Architecture Trade-off Decision

Your team currently runs a **batch-only architecture**: nightly Spark jobs producing daily reports. Product wants "near real-time" dashboards updating every 5 minutes. Engineering proposes three options:

- **Option A**: Keep batch, add micro-batch with Spark Streaming (5-minute windows)
- **Option B**: Full Lambda architecture (keep existing batch + add Flink stream layer, merge results at query time)
- **Option C**: Kappa architecture (replace batch with a single Flink streaming pipeline, reprocess from Kafka on schema change)

1. Compare operational complexity of each option. How many distinct systems does each team need to operate?
2. Lambda architecture risk: the batch and stream layers produce different numbers. How does this happen, and how do you reconcile?
3. Kappa architecture risk: you need to reprocess 2 years of historical data. Your Kafka retention is 7 days. How do you handle this?
4. For a team of 4 engineers, which option do you recommend? Justify with the constraint that the team also owns 3 other services.
5. "Near real-time" is ambiguous. Before choosing an architecture, what clarifying questions do you ask product?

---

## "What If X Changes?" Brainstorming

**Pipeline failures and recovery:**
- "Your nightly batch job fails at step 7 of 15 at 3 AM. It's idempotent. Do you restart from step 1 or step 7? How does Spark checkpointing factor into this decision?"
- "A data quality check catches that 30% of records in today's input have null user IDs. Do you fail the pipeline or proceed with the valid 70%? What's your escalation path?"
- "Your pipeline produces a daily aggregate that's 40% lower than yesterday. Is this a data quality issue, a pipeline bug, or a real business signal? Walk through your diagnosis."

**Schema evolution:**
- "Upstream service adds a new field to their event schema without notice. Your Spark job reads the schema from a registry. What breaks? How do you design for backward compatibility?"
- "You need to add a new column to a 5 TB Parquet dataset. You can't rewrite the whole dataset tonight. How do you handle reads from both old and new partitions that have different schemas?"

**Scale and cost:**
- "Your pipeline is the #2 cost line in your AWS bill. Your VP asks what you'd cut first to reduce costs by 30%. How do you answer? What data would you need first?"
- "A single Spark job is reading 500 GB, but only 10 GB is relevant (the rest is filtered out early). How do you restructure data layout to avoid reading the irrelevant 490 GB?"

**Compliance and correctness:**
- "You discover that a batch job has been silently dropping ~0.1% of records for 6 months due to a deserialization error. How do you scope the impact? How do you recover the data? How do you prevent this from happening again?"
- "Your ML training pipeline uses point-in-time correct features (no future leakage). A new engineer adds a feature that accidentally includes data from 'tomorrow.' How would you detect this in your pipeline testing?"

---

## Failure Injection Scenarios

**Scenario 1: Data Skew Cascade**
Your Spark job is joining user events (1 TB) with user profiles (10 GB). One user (a bot) has 200 million events — 20% of the entire dataset. When Spark shuffles for the join, all 200M rows route to a single partition on one executor.

- What symptoms do you see in the Spark UI? (executor metrics, task duration distribution)
- What is "data skew" and why does it cause this failure mode?
- Describe two mitigations: (a) salting the join key, (b) broadcast join. When is each appropriate?
- The bot user has no valid profile. Should their 200M events be included in your output? What's the business decision and how do you implement it efficiently?

**Scenario 2: Backfill Without Idempotency**
A bug in your pipeline caused incorrect aggregations for the past 14 days. You fix the bug and need to reprocess those 14 days. However, your pipeline was not designed to be idempotent — re-running it appends duplicate records to the output table.

- What's the risk of running the backfill as-is?
- Design a safe backfill strategy: what steps do you take before re-running? How do you make the reprocessed output correct?
- How would you design the pipeline from scratch to be idempotent, so this problem can't occur?
- The 14-day backfill will take 6 hours. Downstream dashboards are wrong during this window. How do you communicate to stakeholders?

**Scenario 3: Regulatory Audit**
A regulator asks your company to produce all data processed for user ID 12345 over the past 2 years, along with a record of every transformation applied to that data.

- Which of your data stores contain data about user 12345? (raw events, aggregates, snapshots, feature store, backups)
- Do you have a data lineage system? If not, how do you reconstruct what transformations were applied?
- How long would this audit response take with your current system? What's your target SLA for regulatory requests?
- Design a "right-to-access" (GDPR Article 15) pipeline that can answer this query in < 24 hours.
