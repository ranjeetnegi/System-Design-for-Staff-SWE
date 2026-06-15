# Chapter 35: Batch Processing and Data Pipelines — Part A

## Staff-Level System Design Interview Prep
### Audience: Intern-to-Staff Accelerated Track

---

## 1. Chapter Opening: Batch vs Stream — the Right Tool for the Job

### The Misconception That Kills Interviews

Here is something that trips up mid-level engineers constantly in L6 interviews: they assume that streaming is the modern, correct approach and that batch processing is old and should be replaced. Interviewers hear this and immediately know the candidate does not understand the tradeoffs.

The truth: **batch processing** handles roughly 80% of analytics workloads at the largest tech companies in the world. Google runs nightly ETL jobs that process petabytes of search logs. Netflix trains its recommendation models on week-long rolling windows of watch history using batch Spark jobs. Uber generates its city-level surge pricing reports from daily batch aggregations. LinkedIn's "People You May Know" system retrains from scratch every night using a batch pipeline over the full social graph.

Streaming is essential when results are needed in seconds. Batch is essential when results need to be accurate over terabytes. The L6 principle is: **do not choose between batch and stream. Design systems that use both, each where it fits.**

---

### The Core Difference: Bounded vs Unbounded Data

The single most important concept to internalize before anything else:

**Bounded data** has a defined beginning and end. "Give me all orders placed on June 13, 2026." The dataset has a fixed size. You can read it all, process it all, and the job completes. This is batch.

**Unbounded data** never ends. "Give me all orders as they are placed." New orders keep arriving. The job must run forever or restart periodically to process what has accumulated. This is streaming.

Think of it like washing dishes. Batch processing is like waiting until after dinner and washing all the dishes at once. You know exactly how many plates there are. You work through them all and finish. Stream processing is like washing each dish immediately after someone uses it, even while other people are still eating. The job never truly "ends" — as long as people keep using dishes, you keep washing.

Both approaches solve real problems. Neither replaces the other.

```
BATCH (Bounded Input)
+------------------+        +------------------+        +------------------+
|  All of         |        |                  |        |                  |
|  Yesterday's    | -----> |   Spark Job      | -----> |  Output File     |
|  Orders         |        |   (runs once,    |        |  (complete,      |
|  (fixed size)   |        |    completes)    |        |   ready to use)  |
+------------------+        +------------------+        +------------------+
   Bounded input             Finite execution            Job is DONE


STREAM (Unbounded Input)
+------------------+        +------------------+        +------------------+
|  Orders         |        |                  |        |  Continuous      |
|  arriving now   | -----> |   Flink Job      | -----> |  output stream   |
|  ...and now     |        |   (runs forever) |        |  (never stops)   |
|  ...and now     |        |                  |        |                  |
+------------------+        +------------------+        +------------------+
  Unbounded input            Continuous execution        Output is ongoing
```

---

### When to Use Batch: The Decision Criteria

Use batch when any of these apply:

| Criterion | Batch Signal | Example |
|-----------|-------------|---------|
| Latency tolerance | Minutes to hours is fine | Daily sales report |
| Full-dataset access | You need ALL records | Join every user with every order |
| Historical analysis | Looking backward in time | Last year's revenue by region |
| ML model training | Needs all historical data at once | Netflix recommendation model |
| Compliance reporting | Audit of all transactions in a period | Monthly billing statement |
| Data correctness priority | Accuracy matters more than speed | Financial reconciliation |

Use stream when any of these apply:

| Criterion | Stream Signal | Example |
|-----------|--------------|---------|
| Low latency required | User needs result in < 1 minute | Fraud alert on purchase |
| Event-driven reaction | Do X immediately when Y happens | Push notification on order shipped |
| Incremental updates | Update a counter as events arrive | Live view count on YouTube |
| Real-time feature engineering | Features for live ML inference | Ride request scoring at Uber |

---

### The Architectural Reality at Scale

At Airbnb, the data platform team maintains two separate processing paths running in parallel. The batch path runs hourly and daily Spark jobs on HDFS for full-dataset analytics. The streaming path runs Flink jobs on Kafka for operational dashboards and anomaly detection. They are not competing — they serve different consumers with different latency requirements.

At Facebook (Meta), the famous **Lambda Architecture** was adopted precisely because neither batch nor streaming alone was sufficient. Batch gives accurate answers over historical data. Streaming gives fast (approximate) answers over recent data. The serving layer merges both. (We will revisit Lambda vs Kappa in a later section of this chapter.)

The interview signal: when a candidate says "I would use streaming" without first asking about latency requirements and data volume, that is a red flag. When a candidate says "This looks like a batch job because the latency tolerance is 1 hour and we need full historical joins," that is an L6 signal.

---

## 2. MapReduce: The Foundation of Distributed Batch

### Why Learn MapReduce in 2026?

You will almost certainly never write a MapReduce job at your next job. Hadoop MapReduce as a hands-on technology is largely obsolete. So why is it in this chapter?

Because **MapReduce is the conceptual DNA of every modern distributed batch system**. Spark, BigQuery, Presto, Hive, Flink in batch mode — all of them implement variants of the same fundamental idea that MapReduce formalized in Google's 2004 paper. When you understand why MapReduce shuffles are expensive, you understand why Spark stage boundaries matter. When you understand why MapReduce is slow for iterative algorithms, you understand why Spark in-memory caching was a breakthrough.

Learning MapReduce is like learning how a car engine works before you drive. You do not need to know it to drive, but if the car breaks down, you will know why, and you will know how to fix it.

---

### The Three Phases: An Intuitive Walkthrough

**The problem:** You have 10 books. You want to count how many times every word appears across all 10 books. There are one billion words total. One person reading all 10 books would take weeks.

**The parallel solution:** Hire 10 workers, one per book. Here is the three-phase approach:

**Phase 1 — MAP (parallel reading):**
Each worker reads their one book. For every word they see, they write a slip of paper: `(word, 1)`. Worker 1 might produce: `("apple", 1)`, `("banana", 1)`, `("apple", 1)`, `("cherry", 1)`. Worker 2 might produce: `("apple", 1)`, `("apple", 1)`, `("date", 1)`. Every worker works in parallel. No coordination needed.

**Phase 2 — SHUFFLE (sorting the slips):**
All slips of paper are sorted and grouped by word. All "apple" slips go into one pile. All "banana" slips go into another pile. All "cherry" slips go into another. This is the phase that requires moving data — slips from Worker 2 travel to join slips from Worker 1 if they have the same word.

**Phase 3 — REDUCE (counting each pile):**
Assign one counter per word. The "apple" counter reads all apple slips, counts them, and outputs: `("apple", 42)`. The "banana" counter outputs `("banana", 17)`. Each counter works in parallel.

The magic of this design: Map workers are fully parallel (no coordination). Reduce workers are fully parallel (no coordination). Only the Shuffle phase requires cross-machine data movement. And this design scales to any number of workers.

```
INPUT: 3 files, too large for one machine

  File 1        File 2        File 3
  (300 GB)      (300 GB)      (400 GB)
     |              |              |
     v              v              v
+----------+   +----------+   +----------+
|  MAP 1   |   |  MAP 2   |   |  MAP 3   |
| (apple,1)|   | (apple,1)|   | (date,1) |
| (bat,1)  |   | (bat,1)  |   | (apple,1)|
| (apple,1)|   | (date,1) |   | (bat,1)  |
+----------+   +----------+   +----------+
     |              |              |
     +------+--------+------+------+
            |                |
     SHUFFLE: sort and group by key
     (network transfer: all machines send data to appropriate reducers)
            |                |
            v                v
     +----------+      +----------+
     | REDUCE 1 |      | REDUCE 2 |
     | key=apple|      | key=bat  |
     | count 4  |      | count 3  |  ... (one reducer per key group)
     +----------+      +----------+
            |                |
            v                v
       (apple, 4)        (bat, 3)        (date, 2)
```

In real MapReduce (Hadoop), Map workers write their output to local disk. The Shuffle reads from those disks across the network. Reduce workers write final output to HDFS (distributed disk). Every single intermediate step touches disk. This is the critical weakness.

---

### Why the Shuffle Is So Expensive

The Shuffle is where distributed batch processing hurts most. Here is exactly why:

Every Map task produces output sorted by key. There are N Map tasks and M Reduce tasks. Every Map task must send its output for key K to the specific Reduce task that handles key K. This means:

1. **Sorting**: each Map task must sort its output by key before sending
2. **Partitioning**: each Map task splits its output into M buckets (one per Reduce task)
3. **Network transfer**: every Map task sends data to potentially every Reduce task
4. **Merging**: each Reduce task receives N sorted files and must merge them

At real scale — say 1 TB of input data — the Map tasks might produce 800 GB of intermediate output. All 800 GB crosses the network during Shuffle. At a 10 GB/sec bisectional bandwidth on a typical cluster, that is 80 seconds of pure network transfer, plus the CPU overhead for sorting and merging.

**The golden rule**: minimize shuffles. Before a shuffle:
- Filter out records you do not need
- Pre-aggregate where possible (combine phase in MapReduce — a mini-reduce on each mapper before the shuffle)
- Use partitioned data so you can skip entire files

---

### MapReduce Limitations That Created Spark

MapReduce has three fundamental architectural problems:

**Problem 1 — Disk writes at every stage:**
Every Map output goes to local disk. Every Reduce input is read from disk. Every Reduce output goes to HDFS. If your pipeline has 5 MapReduce jobs chained together, you get 5 complete write cycles and 5 complete read cycles. For a 1 TB dataset, that is 10 TB of disk I/O.

**Problem 2 — Catastrophic for iterative algorithms:**
Machine learning algorithms (gradient descent, expectation-maximization) need to pass over the same dataset many times. Each pass in MapReduce is one full job: read from disk, compute, write to disk. 100 training iterations = 100 MapReduce jobs = 200 disk operations on the full dataset. This is why training even a simple logistic regression on Hadoop used to take hours.

**Problem 3 — Fixed two-phase model:**
Complex pipelines — like "filter, then join, then aggregate, then join again, then sort" — require chaining many separate MapReduce jobs. Each job boundary forces a complete disk write and read. The code is difficult to write and debug. There is no concept of expressing the whole pipeline as one logical unit.

These three problems are exactly what Spark was designed to solve.

---

## 3. Apache Spark: The Modern Distributed Batch Engine

### What Spark Fixes (and Why It Matters)

**Apache Spark** launched from the AMPLab at UC Berkeley in 2009 with one core insight: keep intermediate data in RAM instead of always writing to disk.

The three fixes:
- **In-memory caching**: intermediate results can stay in RAM across stages. Disk writes only happen when explicitly requested or when memory runs out (spill to disk).
- **DAG execution model**: instead of the fixed Map → Shuffle → Reduce shape, Spark represents an entire pipeline as a Directed Acyclic Graph (DAG). Any sequence of operations can be expressed as one job. Spark plans the entire pipeline before running anything and can optimize across all stages.
- **Lazy evaluation**: no computation starts until you ask for a result. Spark collects all the transformations you want to apply, optimizes the plan, then executes everything in one efficient pass.

The performance result: Spark is 10-100x faster than MapReduce for iterative algorithms (where in-memory caching eliminates repeated disk reads) and 2-10x faster for standard ETL workloads (where DAG optimization eliminates redundant passes over data).

**Who uses it:**
- **Facebook/Meta**: petabyte-scale analytics on ad data, running thousands of Spark jobs daily
- **Netflix**: recommendation model training on 200+ million member viewing histories
- **Airbnb**: the entire data science platform runs on Spark for feature engineering and A/B test analysis
- **LinkedIn**: log analytics, feed ranking model training, "People You May Know" computation

---

### Spark Architecture: Driver and Executors

Every Spark application has exactly two types of processes:

**The Driver** is the brain. There is exactly one Driver per Spark application. It:
1. Receives your Spark code
2. Builds the execution plan (the DAG)
3. Negotiates with the cluster manager (YARN, Kubernetes, Mesos) for resources
4. Divides the DAG into tasks
5. Schedules tasks on executors
6. Tracks which tasks are complete, which failed
7. Handles retries for failed tasks
8. Collects results

The Driver is a single point of failure for the application. If it dies, the job fails. This is why you never run `collect()` on a massive dataset — it sends all the data back to the Driver, which can OOM.

**Executors** are the workers. There are many executors per application (tens to hundreds). Each executor:
1. Runs on one worker machine
2. Has a fixed amount of RAM (e.g., 16 GB) and CPU cores (e.g., 4 cores)
3. Runs tasks assigned by the Driver
4. Stores cached RDD/DataFrame partitions in RAM
5. Reports task completion and metrics back to the Driver

**Tasks** are the smallest unit of work. Each task:
1. Processes exactly one partition of data
2. Runs on exactly one executor core
3. Runs entirely within one stage (no cross-task communication within a stage)

```
SPARK CLUSTER ARCHITECTURE

+--------------------------------------------------+
|                   DRIVER                         |
|   - Builds DAG                                   |
|   - Schedules tasks                              |
|   - Tracks progress                              |
+--------------------------------------------------+
         |              |              |
         | tasks        | tasks        | tasks
         v              v              v
+------------+   +------------+   +------------+
| EXECUTOR 1 |   | EXECUTOR 2 |   | EXECUTOR 3 |
| RAM: 16 GB |   | RAM: 16 GB |   | RAM: 16 GB |
| Cores: 4   |   | Cores: 4   |   | Cores: 4   |
|            |   |            |   |            |
| [Task 1]   |   | [Task 5]   |   | [Task 9]   |
| [Task 2]   |   | [Task 6]   |   | [Task 10]  |
| [Task 3]   |   | [Task 7]   |   | [Task 11]  |
| [Task 4]   |   | [Task 8]   |   | [Task 12]  |
|            |   |            |   |            |
| [Cache]    |   | [Cache]    |   | [Cache]    |
+------------+   +------------+   +------------+
```

The cluster manager (YARN on Hadoop, Kubernetes in cloud environments) allocates machines and resources. Spark does not manage machines directly — it asks the cluster manager for containers and runs executors inside them.

---

### DAG, Stages, and Shuffle Boundaries

When you write Spark code, you are not immediately running computation. You are defining a **DAG** (Directed Acyclic Graph) of transformations. Spark then analyzes this DAG to find the most efficient execution order.

The DAG is divided into **stages**. A new stage begins every time a **shuffle** is required. Within a single stage, all tasks run in parallel and no data crosses the network between executors. Between stages, a shuffle occurs — data is redistributed across executors by key.

Example pipeline: `read orders → filter by date → group by merchant → count → write`

```
STAGE 1: read + filter + partial aggregate (all local, fully parallel)
+----------+   +----------+   +----------+
| Task 1   |   | Task 2   |   | Task 3   |
| Partition|   | Partition|   | Partition|
| 1 data   |   | 2 data   |   | 3 data   |
|          |   |          |   |          |
| filter   |   | filter   |   | filter   |
| partial  |   | partial  |   | partial  |
| agg      |   | agg      |   | agg      |
+----------+   +----------+   +----------+
      |               |               |
      +-------+--------+-------+-------+
              |
      SHUFFLE BOUNDARY
      (data crosses network, grouped by merchant_id key)
              |
      +-------+--------+-------+-------+
      |               |               |
STAGE 2: final aggregate + write (all local, fully parallel)
+----------+   +----------+   +----------+
| Task 4   |   | Task 5   |   | Task 6   |
| merchant |   | merchant |   | merchant |
| A, B, C  |   | D, E, F  |   | G, H, I  |
|          |   |          |   |          |
| final    |   | final    |   | final    |
| count    |   | count    |   | count    |
| write    |   | write    |   | write    |
+----------+   +----------+   +----------+
```

This is why the Spark UI shows "stages" — each stage is a batch of tasks that run in parallel without needing to talk to each other. The stage boundaries are where the expensive shuffles happen.

The key insight for interviews: **the number of shuffles is the primary driver of Spark job performance.** Every `groupBy`, `join`, `distinct`, and `repartition` creates a shuffle boundary (a new stage). Minimize these.

---

### Partitions: The Unit of Parallelism

A **partition** is a chunk of your input data. It is the fundamental unit of parallelism in Spark. One task processes one partition. One core runs one task at a time. So:

```
Parallelism = min(number of partitions, total executor cores)
```

**Too few partitions:** If you have 400 executor cores but only 10 partitions, only 10 cores are working. 390 cores sit idle. Job runs at 2.5% efficiency. This happens when you read a single small file or when the source data is not partitioned.

**Too many partitions:** If you have 400 executor cores and 100,000 partitions, most partitions are tiny (say 1 KB each). The scheduling overhead of 100,000 tasks dominates actual compute time. You also write 100,000 output files, which overwhelms downstream file systems.

**The rules of thumb:**
- Target 128 MB per partition (same as HDFS block size — not a coincidence)
- Use 2-3 partitions per executor core as a starting point
- For a 1 TB dataset with 128 MB partition size: 1,000,000 MB / 128 MB = ~8,000 partitions

```python
# Check current partition count
df.rdd.getNumPartitions()  # e.g., returns 200

# Adjust partition count
df.repartition(500)     # increase partitions (causes shuffle)
df.coalesce(50)         # decrease partitions (NO shuffle, just merges local partitions)

# Tune shuffle partitions (default is 200, often too low for large datasets)
spark.conf.set("spark.sql.shuffle.partitions", "2000")
```

The `spark.sql.shuffle.partitions` setting controls how many partitions are created after a shuffle. The default of 200 is appropriate for small datasets (a few GB) but far too low for 1 TB+ datasets. Increasing this is one of the first tuning steps in production.

---

### Lazy Evaluation: Why Spark Waits to Run

Spark operations split into two categories:

**Transformations** (lazy — nothing runs):
`filter()`, `select()`, `groupBy()`, `join()`, `map()`, `flatMap()`, `withColumn()`, `drop()`

**Actions** (trigger execution — job actually runs):
`write()`, `count()`, `show()`, `collect()`, `take()`, `first()`

When you call transformations, Spark builds up a plan. When you call an action, Spark executes the entire plan at once.

```python
# This code defines a plan but runs NOTHING:
df = spark.read.parquet("s3://data/orders/")
filtered = df.filter(df["date"] == "2026-06-13")
grouped = filtered.groupBy("merchant_id").count()

# This line triggers execution of ALL steps above:
grouped.write.parquet("s3://output/daily_counts/")
```

The analogy: a restaurant does not start cooking when you browse the menu. It does not start cooking when you say "I'm thinking about the pasta." It starts cooking when you place your order. The menu (transformations) exists as a plan. The order (action) starts the kitchen.

Why does laziness help? Because Spark sees the **entire plan** before running anything. It can optimize across all steps:
- It notices you only use two columns out of twenty → it reads only those two from Parquet
- It notices a filter comes before a join → it applies the filter first to reduce join input size
- It notices two consecutive `filter()` calls → it combines them into one pass over the data

---

### The Catalyst Optimizer: Spark's Automatic Speedup

The **Catalyst optimizer** is Spark's query planning engine. It takes your logical plan (what you asked for) and rewrites it into a more efficient physical plan (how to actually execute it) before running anything.

Catalyst applies several optimization rules automatically:

**Predicate pushdown**: Move filter conditions as close to the data source as possible.

```python
# You write:
df.filter(df["date"] == "2026-06-13").groupBy("city").count()

# Catalyst rewrites the execution to:
# 1. Read ONLY Parquet files for date=2026-06-13 (partition pruning)
# 2. Read ONLY the "date" and "city" columns (column pruning)
# 3. THEN groupBy and count
# Result: reads 1/365th of the data instead of the whole table
```

**Column pruning**: Only read the columns that are actually used downstream.

```python
# You write:
df.select("user_id", "amount").filter(df["amount"] > 100)

# Even though the Parquet file has 20 columns, Catalyst tells the reader:
# "Only load user_id and amount from disk." 18 columns never touch RAM.
```

**Join reordering**: Filter large tables before joining them. If you have a 1 TB orders table and a 100 GB users table, and your query filters orders to 10 GB, Catalyst will apply that filter before the join (reducing the join from 1 TB x 100 GB to 10 GB x 100 GB).

**Constant folding**: Compute constant expressions once at planning time.

```python
# You write:
df.filter(df["amount"] > 50 * 2)

# Catalyst computes 50*2=100 at planning time. At runtime: df["amount"] > 100.
# No multiplication per row.
```

Catalyst is why Spark SQL is often as fast (or faster) than hand-tuned code — the optimizer knows more about the data and the execution environment than most engineers writing transformations manually.

---

### Spark Optimization Techniques Reference

| Technique | What It Does | When to Use | Impact |
|-----------|-------------|-------------|--------|
| **Broadcast join** | Sends small table to all executors; eliminates shuffle | One table < 10 MB (default threshold) | 5-50x faster joins |
| **Partition pruning** | Reads only partitions matching filter predicates | Data partitioned by date/region/key in storage | 10-100x less data read |
| **Bucketing** | Pre-sort and pre-partition data on disk by join key | Repeated joins on same key across jobs | Eliminates shuffle on future joins |
| **Caching** | Keeps a DataFrame in executor RAM | DataFrame used multiple times in same job | Eliminates redundant recomputation |
| **Coalesce** | Reduces partition count without shuffle | After heavy filtering reduces data volume | Avoids small file problem |
| **AQE (Spark 3+)** | Runtime adaptive optimization based on actual data stats | Always — enable by default | 10-50% job time reduction |

```python
# Enable AQE (Adaptive Query Execution) — always do this in production
spark.conf.set("spark.sql.adaptive.enabled", "true")
spark.conf.set("spark.sql.adaptive.coalescePartitions.enabled", "true")
spark.conf.set("spark.sql.adaptive.skewJoin.enabled", "true")
```

---

## 4. Data Skew: The Batch Processing Enemy

### What Data Skew Looks Like

Imagine you manage 10 workers at a furniture assembly warehouse. You divide the day's work equally: each worker gets 20 chair boxes to assemble. At the end of 8 hours, 9 workers are done and waiting. The 10th worker is still at hour 2 of their pile — because their boxes actually contain 200 chairs, not 20. Your warehouse ships when the last worker is done. Your entire operation is blocked by that one worker.

This is **data skew** in a distributed system: one partition (one task) has dramatically more data than all others. The entire job finishes when the last task finishes. If one task has 100x more data, the entire job takes 100x longer than it should.

Skew happens because real data is not uniformly distributed:
- In an e-commerce system: Amazon, Walmart, and Target account for 30% of all orders. Any `GROUP BY merchant_id` creates skew on those three keys.
- In social networks: celebrity accounts have 100 million followers. Any `JOIN` on `user_id` creates skew for those accounts.
- In ride-sharing: downtown Manhattan generates 40% of Uber's NYC rides. Any `GROUP BY pickup_zone` creates skew on Manhattan.

At LinkedIn, a `GROUP BY company_id` job on professional interaction data routinely skewed on Microsoft (which owned LinkedIn) and Google. The job's SLA was 4 hours. The skewed task ran for 11 hours. The entire daily pipeline was delayed.

---

### How to Detect Data Skew

**Method 1 — Spark UI inspection:**
Open Spark UI → click on a Stage → look at the task duration distribution. If the median task duration is 2 minutes and the maximum task duration is 2 hours, you have severe skew. The p99 vs p50 ratio is your skew signal. A ratio above 5x warrants investigation.

**Method 2 — Data distribution query:**
Before running a large job, run a quick COUNT to see how data distributes by key:

```sql
SELECT merchant_id, COUNT(*) as cnt
FROM orders
GROUP BY merchant_id
ORDER BY cnt DESC
LIMIT 20;
```

If the top key has more than 5% of total rows, expect skew when grouping or joining on that key.

**Method 3 — Check partition sizes at runtime:**
```python
# Check how many records are in each partition
df.rdd.mapPartitions(lambda x: [sum(1 for _ in x)]).collect()
# If output looks like: [10000, 11000, 9500, 850000, 10200, ...]
# the 850000-record partition is your skewed partition
```

---

### Salting: The Manual Fix for Data Skew

**Salting** is the standard technique for handling skew on grouped aggregations. The idea: instead of putting all "amazon" records into one partition, artificially spread them across multiple partitions by appending a random number (the "salt") to the key.

**Three steps:**

**Step 1 — Add salt to the key:**
```python
import pyspark.sql.functions as F

NUM_SALT_BUCKETS = 10

# Add a random salt 0-9 to each row
df_salted = df.withColumn(
    "salt",
    (F.rand() * NUM_SALT_BUCKETS).cast("int")
).withColumn(
    "merchant_id_salted",
    F.concat(F.col("merchant_id"), F.lit("_"), F.col("salt").cast("string"))
)
```

**Step 2 — Aggregate on the salted key:**
```python
# First aggregation: group by (merchant_id, salt)
# "amazon_0", "amazon_1", ..., "amazon_9" are now 10 separate groups
partial_agg = df_salted.groupBy("merchant_id_salted", "merchant_id") \
    .agg(F.sum("amount").alias("partial_sum"))
```

**Step 3 — Re-aggregate on the real key:**
```python
# Second aggregation: combine the 10 partial sums for "amazon"
final_agg = partial_agg.groupBy("merchant_id") \
    .agg(F.sum("partial_sum").alias("total_amount"))
```

The cost: two aggregations instead of one (extra CPU). The benefit: no single partition is overloaded.

```
BEFORE SALTING: severe skew

  Partition 1: amazon (80 million rows)  <-- task runs for 4 hours
  Partition 2: walmart (5 million rows)  <-- done in 15 minutes
  Partition 3: target (4 million rows)   <-- done in 12 minutes
  Partition 4: others (11 million rows)  <-- done in 30 minutes

  Job duration: 4 hours (blocked on Partition 1)

AFTER SALTING: balanced

  amazon_0 (8M)  amazon_1 (8M)  amazon_2 (8M)  ... amazon_9 (8M)
  walmart (5M)   target (4M)    others (11M)
  All partitions: roughly 5-11 million rows each

  Job duration: ~35 minutes (all tasks finish around the same time)
```

---

### Salting for Joins: The Skewed Join Problem

Salting for aggregations is straightforward. Salting for joins is trickier because you need both sides of the join to use the same salt values consistently.

**Problem setup:** You are joining a 1 TB orders table with a 500 GB customer_profiles table on `customer_id`. A few celebrity customers (Beyonce's account, an influencer with millions of purchases) have millions of order records. The join on `customer_id` causes massive skew on those few keys.

**Solution — replicate the small side, salt the large side:**

```python
NUM_SALT = 10

# Step 1: Add random salt to the LARGE table (orders)
orders_salted = orders.withColumn(
    "salt", (F.rand() * NUM_SALT).cast("int")
).withColumn(
    "customer_id_salted",
    F.concat(F.col("customer_id"), F.lit("_"), F.col("salt").cast("string"))
)

# Step 2: Explode the SMALL table (profiles) for all salt values
# Each profile row gets duplicated 10 times (one per salt value)
salt_values = spark.range(NUM_SALT).select(F.col("id").alias("salt"))
profiles_exploded = customer_profiles.crossJoin(salt_values).withColumn(
    "customer_id_salted",
    F.concat(F.col("customer_id"), F.lit("_"), F.col("salt").cast("string"))
)

# Step 3: Join on the salted key — now balanced across 10x more partitions
result = orders_salted.join(profiles_exploded, on="customer_id_salted")
    .drop("salt", "customer_id_salted")
```

The tradeoff: the smaller join side (customer_profiles) gets 10x larger due to replication. If profiles is 50 GB, the exploded version is 500 GB. This works when the small side is manageable. If both sides are truly huge and skewed, you need AQE or a different data model.

---

### AQE: Spark 3.0 Automatic Skew Handling

**Adaptive Query Execution (AQE)** is Spark 3.0's answer to making skew handling automatic. Before AQE, the execution plan was fixed at job submission time — Spark had no idea which partitions would be large until the job was actually running. After AQE, Spark monitors partition sizes at runtime and adapts:

When AQE detects a skewed partition (one that is much larger than the median), it automatically:
1. Splits the large partition into multiple sub-partitions
2. Duplicates the corresponding join side data to match
3. Runs the operation on the sub-partitions in parallel

```python
# Enable AQE skew handling (Spark 3.0+):
spark.conf.set("spark.sql.adaptive.enabled", "true")
spark.conf.set("spark.sql.adaptive.skewJoin.enabled", "true")

# Tune the detection threshold (partition is skewed if it's > 5x median AND > 256MB):
spark.conf.set("spark.sql.adaptive.skewJoin.skewedPartitionFactor", "5")
spark.conf.set("spark.sql.adaptive.skewJoin.skewedPartitionThresholdInBytes", "268435456")
```

No code changes to your pipeline logic. Just configuration. Databricks internal benchmarks showed AQE reduced median job runtime by 19% and p95 job runtime by 48% across production workloads. Enable it by default for all production Spark jobs on version 3.0+.

---

### Common Spark Failure Modes Reference

| Failure | Symptom | Root Cause | Fix |
|---------|---------|-----------|-----|
| **OOM on Driver** | Job fails with `java.lang.OutOfMemoryError` on driver | `collect()` or `show()` on large dataset pulls all data to driver | Never `collect()` large results; use `write()` instead |
| **OOM on Executor** | Task fails repeatedly; `SparkOutOfMemoryError` | Skewed partition too large for executor RAM | Salting, AQE, increase executor memory |
| **Shuffle spill** | Job slow; Spark UI shows "shuffle spill" metric high | Executor memory too small to hold shuffle buffers | Increase `spark.executor.memory`, reduce shuffle partitions |
| **Small files explosion** | S3/HDFS has 100,000 files for one output table | Too many output partitions (default 200 per stage) | `coalesce()` before write; tune `spark.sql.shuffle.partitions` |
| **Long tail tasks** | Most tasks done but a few run 10x longer | GC pauses, skew, slow disk on one executor | Enable AQE, check GC logs, consider salting |
| **Stage retry loop** | Stage retries 4 times then job fails | Corrupt or unavailable input data partition | Check data source, enable speculation (`spark.speculation=true`) |

---

## 5. Broadcast Join: The Optimization That 10xs Join Speed

### The Default: Shuffle Join (Expensive)

When you join two large tables in Spark, the default behavior is a **shuffle join** (also called sort-merge join). Here is what happens:

1. Both tables are shuffled across the network by the join key
2. Records with the same key land on the same executor
3. The join is performed locally on each executor

```
SHUFFLE JOIN: Large Table A (1 TB) JOIN Large Table B (500 GB)

Table A (1 TB)                 Table B (500 GB)
distributed across             distributed across
Executors 1,2,3,...           Executors 1,2,3,...

          SHUFFLE: both tables redistributed by join key
          -----------------------------------------------
          1.5 TB of data moves across the network
          At 10 GB/sec: 150 seconds of pure network I/O

          THEN: join happens locally on each executor
```

The cost is the network transfer. At 10 GB/sec bisectional bandwidth (typical cluster), shuffling 1.5 TB takes roughly 150 seconds of pure network time, before any actual computation. For complex joins that run many times in a pipeline, this cost multiplies.

---

### The Broadcast Join (When One Table Is Small)

The insight: if one table is small enough to fit in memory, why shuffle it? Instead, **broadcast** a complete copy of the small table to every single executor. Now each executor can do the join entirely in local memory without any network transfer for the large table.

```
BROADCAST JOIN: Large Table A (1 TB) JOIN Small Table B (10 MB)

                Small Table B (10 MB)
                sent to ALL executors
                     |
         +-----------+-----------+
         |           |           |
         v           v           v
    Executor 1  Executor 2  Executor 3
    [Table B    [Table B    [Table B
     in RAM]     in RAM]     in RAM]
         |           |           |
    [Table A    [Table A    [Table A
     partition1] partition2] partition3]
         |           |           |
      JOIN         JOIN         JOIN
    (local,      (local,      (local,
     no network)  no network)  no network)

Network transfer: only 10 MB * 3 executors = 30 MB total
vs. 1.5 TB in shuffle join
```

Spark automatically uses broadcast join when one table is below the threshold:

```python
# Default threshold: 10 MB. Tables smaller than this are auto-broadcast.
spark.conf.set("spark.sql.autoBroadcastJoinThreshold", "10485760")  # 10 MB in bytes

# Increase threshold if you have enough executor RAM and medium-sized dimension tables:
spark.conf.set("spark.sql.autoBroadcastJoinThreshold", "104857600")  # 100 MB

# Force a broadcast join explicitly (overrides threshold):
from pyspark.sql.functions import broadcast
result = large_table.join(broadcast(small_table), on="user_id")

# Disable broadcast join (sometimes needed to avoid executor OOM):
spark.conf.set("spark.sql.autoBroadcastJoinThreshold", "-1")
```

**Real-world impact at Airbnb:** A critical daily ETL job joined booking data (800 GB) with a listing metadata table (8 MB). The join was using a shuffle join and taking 45 minutes. After explicitly setting the broadcast threshold to include the 8 MB table, the same join took 4 minutes. No code changes to business logic. One configuration line.

---

### Bucket Join: The Zero-Shuffle Join for Repeated Pipelines

There is a third join strategy that eliminates shuffles entirely for pipelines that join the same tables repeatedly: **bucketing**.

The idea: at write time, you sort and partition data by the join key and write it into a fixed number of "buckets" (files). If both tables are bucketed on the same key with the same number of buckets, a join between them requires no shuffle at all — matching buckets are guaranteed to contain matching keys.

```python
# Write orders bucketed by user_id into 200 buckets
orders.write \
    .bucketBy(200, "user_id") \
    .sortBy("user_id") \
    .saveAsTable("orders_bucketed")

# Write user_profiles bucketed by user_id into 200 buckets
user_profiles.write \
    .bucketBy(200, "user_id") \
    .sortBy("user_id") \
    .saveAsTable("user_profiles_bucketed")

# JOIN: no shuffle! Bucket 1 of orders joins with Bucket 1 of user_profiles
# on the same executor. No data crosses the network.
result = spark.table("orders_bucketed") \
    .join(spark.table("user_profiles_bucketed"), on="user_id")
```

```
BUCKET JOIN: zero network transfer at join time

  orders_bucketed              user_profiles_bucketed
  on disk, sorted by user_id   on disk, sorted by user_id

  Bucket 1 (users A-F)  -----> Executor 1 -----> JOIN (local)
  Bucket 2 (users G-M)  -----> Executor 2 -----> JOIN (local)
  Bucket 3 (users N-S)  -----> Executor 3 -----> JOIN (local)
  Bucket 4 (users T-Z)  -----> Executor 4 -----> JOIN (local)

  Network transfer: 0 bytes (data read directly from local disk)
```

The cost: the bucketing write is expensive (requires a shuffle to write). The benefit: every future job that joins these two tables skips the shuffle entirely. If you join orders with user_profiles in 50 different daily jobs, you pay the bucketing cost once and save the shuffle cost 50 times. At Uber, the trips table and driver_profiles table are both bucketed by driver_id. Every daily analytics job on driver behavior avoids a multi-hundred-GB shuffle.

When to use bucketing:
- The same join runs repeatedly (daily ETL, multiple pipelines joining the same tables)
- Both tables are large (if one is small, broadcast join is simpler)
- The join key is stable (bucketing is invalidated if the key distribution changes dramatically)
- You control the write path (cannot bucket external tables you do not own)

---

### When Broadcast Join Breaks Down

Broadcast join has one critical failure mode: the "small" table is not actually small. If you set `autoBroadcastJoinThreshold` to 500 MB and that 500 MB table is broadcast to 200 executors, you now have 200 x 500 MB = 100 GB of RAM consumed just for this one table's copies. Executors OOM. Job fails with confusing errors.

Rules for broadcast join:
- Only broadcast tables that comfortably fit in executor memory with room to spare
- Consider total memory: broadcast size x number of executors must be << total cluster RAM
- When in doubt: let AQE decide. AQE's `spark.sql.adaptive.autoBroadcastJoinThreshold` dynamically decides based on runtime statistics whether to use broadcast or shuffle join.

```python
# Let AQE decide at runtime based on actual partition stats:
spark.conf.set("spark.sql.adaptive.enabled", "true")
# AQE will automatically switch from shuffle join to broadcast join
# if it discovers (at runtime) that the smaller side is actually small
```

| Join Type | Best For | Network Cost | Memory Cost | Risk |
|-----------|---------|-------------|-------------|------|
| **Shuffle join** | Both tables large (GB+) | Very high (both sides shuffle) | Low per executor | Slow; skew-sensitive |
| **Broadcast join** | One table small (< 100 MB) | Very low (small table only) | High (copies on every executor) | Executor OOM if table too large |
| **Bucket join** | Repeated joins on same key | Zero (pre-shuffled on disk) | Zero extra | Requires upfront bucketing at write time |

---

## 6. File Formats: Why Parquet and ORC Dominate Batch Processing

### The Problem with CSV and JSON at Scale

When you are learning data engineering, you start with CSV and JSON files. They are human-readable, easy to inspect, and work everywhere. At small scale, they are fine. At large scale, they are catastrophically inefficient.

**The core issue: row-oriented vs column-oriented storage.**

A CSV file stores data row by row:

```
Row 1: user_id=1, name="Alice", age=28, country="US", amount=150.00
Row 2: user_id=2, name="Bob",   age=35, country="UK", amount=89.50
Row 3: user_id=3, name="Carol", age=22, country="US", amount=200.00
...
```

If you want to compute the average `amount` for US users, you must read every row, including `name` and `age`, even though you only need `country` and `amount`. For a 1 TB file with 20 columns and you only need 2 of them, you read 1 TB but only use 100 GB of it. 900 GB of disk I/O wasted.

**Parquet** (Apache Parquet) stores data column by column:

```
Column "user_id":  [1, 2, 3, ...]
Column "name":     ["Alice", "Bob", "Carol", ...]
Column "age":      [28, 35, 22, ...]
Column "country":  ["US", "UK", "US", ...]
Column "amount":   [150.00, 89.50, 200.00, ...]
```

To compute average `amount` for US users, you read only the `country` column and the `amount` column. If those two columns are 200 GB of your 1 TB file, you read 200 GB instead of 1 TB. 5x less disk I/O automatically.

```
ROW FORMAT (CSV/JSON):                COLUMN FORMAT (Parquet/ORC):

+----+-------+---+---+--------+      +---------+--------+
| id | name  |age|cty|amount  |      | user_id | amount |
+----+-------+---+---+--------+      +---------+--------+
| 1  | Alice | 28| US| 150.00 |      |    1    | 150.00 |
| 2  | Bob   | 35| UK|  89.50 |      |    2    |  89.50 |
| 3  | Carol | 22| US| 200.00 |      |    3    | 200.00 |
+----+-------+---+---+--------+      +---------+--------+
                                      Only 2 columns read from disk
Query: avg(amount) WHERE country=US   when query needs 2 of 20 columns.
Reads: ALL columns (wasteful)         Reads: only relevant columns.
```

---

### Parquet: The Standard for Batch Analytics

**Apache Parquet** is the default file format for all major batch analytics systems. Spark, Presto, BigQuery (via its Parquet export), Hive, Athena — all use Parquet as their preferred format.

Key properties:

**Columnar storage**: as described above, read only the columns you query. This is the biggest performance win for analytics workloads (which typically query 2-5 columns out of 50+).

**Row groups**: Parquet files are divided into row groups (default 128 MB). Each row group contains column chunks for all columns. Within a row group, each column chunk stores statistics: min value, max value, null count. Spark uses these statistics to skip entire row groups that cannot match your filter.

```
Parquet File (1 GB total)
+------------------------------------------+
| Row Group 1 (128 MB):                    |
|   Column "date": [2026-01-01..2026-01-31]|  <-- stats: min, max
|   Column "amount": [0.01..50000.00]      |
|   Column "country": ["AU".."ZW"]         |
+------------------------------------------+
| Row Group 2 (128 MB):                    |
|   Column "date": [2026-02-01..2026-02-28]|  <-- if you query date=2026-06-13,
|   Column "amount": [0.01..45000.00]      |      Spark skips Row Group 2 entirely
|   Column "country": ["AU".."ZA"]         |      without reading it
+------------------------------------------+
| Row Group 3 (128 MB): ...                |
+------------------------------------------+
```

**Compression**: Parquet applies per-column compression (Snappy, GZIP, ZSTD). Because values within a column are the same type and often similar, compression ratios are excellent. A 100 GB CSV file often becomes a 15-25 GB Parquet file. Less storage cost, faster reads (less data to decompress than to read uncompressed from disk).

**Schema evolution**: Parquet supports adding new columns to a table without rewriting existing data. Old files simply return `null` for new columns. This is critical for production pipelines that evolve over months.

```python
# Writing Parquet in Spark
df.write \
    .mode("overwrite") \
    .partitionBy("date", "country") \  # creates directory structure: date=2026-06-13/country=US/
    .parquet("s3://data-lake/orders/")

# Reading Parquet — Spark automatically applies column pruning and predicate pushdown
orders = spark.read.parquet("s3://data-lake/orders/") \
    .filter(F.col("date") == "2026-06-13") \    # Spark reads only date=2026-06-13/ directory
    .select("user_id", "amount")                 # Spark reads only these 2 columns
```

---

### Partitioning in Storage: Directory-Level Pruning

When you write Parquet files partitioned by a column, Spark creates a directory hierarchy:

```
s3://data-lake/orders/
  date=2026-06-11/
    country=US/
      part-00000.parquet
      part-00001.parquet
    country=UK/
      part-00000.parquet
  date=2026-06-12/
    country=US/
      ...
  date=2026-06-13/
    country=US/
      part-00000.parquet   <-- ONLY THIS is read for date=2026-06-13, country=US query
```

When your query has `WHERE date = '2026-06-13' AND country = 'US'`, Spark lists only the matching directory and reads only those files. The rest of the data on S3 is never touched. For a table with 3 years of data (1,095 daily partitions), a single-day query reads 1/1,095th of the total data.

**Partition column selection is a critical design decision.** Rules:
- Partition by the most common filter in your queries (usually `date`)
- Do not partition by high-cardinality columns (never partition by `user_id` — you would have millions of directories, each with one tiny file)
- A good partition contains between 100 MB and 10 GB of data
- Add a second partition level only if you frequently filter on both dimensions simultaneously

At Facebook, the main events table is partitioned by `ds` (datestamp) and `country`. Almost every query either specifies a date range or a specific country, so partition pruning eliminates the vast majority of data before any compute happens.

---

### ORC vs Parquet: When to Use Which

**ORC (Optimized Row Columnar)** is Parquet's main competitor. Both are columnar. The differences are subtle:

| Property | Parquet | ORC |
|----------|---------|-----|
| Ecosystem | Spark, Presto, Flink (default) | Hive (default), some Spark shops |
| Bloom filters | Yes | Yes (better implementation) |
| Predicate pushdown | Excellent | Excellent |
| Compression | Snappy (default), GZIP, ZSTD | ZLIB (default), Snappy, ZSTD |
| Complex types | Native (nested structs, arrays, maps) | Good support |
| Industry default | Majority of modern systems | Older Hadoop ecosystems |

In 2026, if you are starting a new project on Spark, Presto, or Athena: use Parquet. If you are integrating with a legacy Hive warehouse: ORC may be required for compatibility. The performance difference between ORC and Parquet for typical workloads is negligible — both are dramatically better than CSV or JSON.

---

### The Small File Problem: A Silent Performance Killer

One of the most common production issues in batch pipelines is the **small file problem**. It sounds minor but causes real pain at scale.

When Spark writes output, it writes one file per output partition. If you have `spark.sql.shuffle.partitions = 200` (the default) and your output data is only 2 GB, you get 200 files of roughly 10 MB each. Run this job daily for a year: 200 x 365 = 73,000 files in one table directory. After three years: 219,000 files.

**Why small files hurt:**
- Every file is a separate S3 or HDFS object. Listing a directory with 200,000 files takes 20-40 seconds because object stores list objects in pages of 1,000.
- The next Spark job that reads this table opens 200,000 file handles. File open overhead per file is small but multiplied by 200,000 it becomes significant.
- Parquet's statistics (min/max per row group) are less useful in tiny files because each file has few rows — Spark cannot skip much.
- HDFS NameNode stores metadata for every file in RAM. 200,000 tiny files consumes NameNode RAM that should go toward managing real data.

**The fix — coalesce before writing:**

```python
# After a heavy computation that produces small output, coalesce before write
result_df \
    .coalesce(20) \          # reduce from 200 partitions to 20 (no shuffle)
    .write \
    .parquet("s3://output/daily_report/")

# For larger outputs, repartition (with shuffle, but guarantees even distribution):
result_df \
    .repartition(50) \
    .write \
    .parquet("s3://output/daily_report/")
```

Target file size: 128 MB to 512 MB per Parquet file. This matches HDFS block size and S3 optimal read size. A 10 GB daily output should be written as 20-80 files, not 200.

At Netflix, the pipeline team enforces a post-write compaction step in all ETL jobs that output less than 5 GB per partition date. A final `coalesce()` step brings file count to a consistent 5-10 files per daily partition, keeping the S3 listing latency under 100ms for any downstream reader.

---

## Chapter 35 Part A — Concept Checkpoint

Before moving to Part B (data pipeline architecture, Lambda vs Kappa, orchestration), confirm you can answer these without notes:

**On Batch vs Stream:**
- Why does Netflix use batch for recommendation model training instead of streaming?
- A product manager says "we want real-time reports." What clarifying question do you ask first?

**On MapReduce:**
- Why does the Shuffle phase require network transfer but the Map phase does not?
- What is the fundamental reason MapReduce is slow for machine learning training?

**On Spark:**
- A Spark job has 8 stages. How many shuffle boundaries does it have?
- You have 200 executor cores. Your input data has 20 partitions. What is the utilization percentage?
- What does `collect()` do and why is it dangerous on large datasets?

**On Data Skew:**
- Your Spark UI shows median task time = 3 minutes, max task time = 4 hours. What do you do?
- Describe the three steps of salting in plain English (no code).

**On Broadcast Join:**
- You are joining a 500 GB orders table with a 5 MB country codes lookup table. What join type do you use and why?
- What happens if you broadcast a 2 GB table to 500 executors with 8 GB RAM each?

These questions appear verbatim in L6 system design interviews. Not as trivia — interviewers use them to confirm that when you design a data pipeline and say "we'll use Spark," you actually know what that means under the hood.

---

*Chapter 35 continues in Part B: Data Pipeline Architecture, Lambda vs Kappa, Orchestration with Airflow, and Building Production-Grade Pipelines.*
# Chapter 35: Batch Processing and Data Pipelines
## Part B — Pipelines, CDC, Storage, and Orchestration

---

## 1. Data Pipelines: Moving Data at Scale

### What Is a Data Pipeline?

Before we touch any code or architecture, think about a **water treatment plant**.

A city pulls raw water from a river. That water is dirty: it has sediment, bacteria, and chemicals. The plant runs the water through a series of stages — filtering, adding chlorine, testing pH — and at the end, clean water flows to your tap. Each stage of the plant has one specific job. If the chlorine stage fails, the plant doesn't just dump untreated water into your house. It stops, raises an alarm, and the operator fixes the problem before the water moves forward.

A **data pipeline** works the same way. Raw data flows from where it is **produced** (databases, APIs, user events, payment systems) through a series of processing stages, and ends up where it is **used** (analytics dashboards, ML models, executive reports, recommendation engines). Each stage has a specific job. And just like the water plant, if one stage fails, the pipeline needs to stop, alert, and recover — not silently corrupt your data.

The three core stages every pipeline has, in some form:

```
+----------------+     +-------------------+     +------------------+
|                |     |                   |     |                  |
|   EXTRACT      | --> |    TRANSFORM      | --> |      LOAD        |
|                |     |                   |     |                  |
| Pull data from |     | Clean, reshape,   |     | Write to final   |
| source systems |     | join, aggregate   |     | destination      |
| (DBs, APIs,    |     | (Spark, SQL, dbt) |     | (warehouse,      |
|  files, Kafka) |     |                   |     |  data lake, DB)  |
+----------------+     +-------------------+     +------------------+
```

**Extract**: get the data out of wherever it lives. This sounds easy. It is not. Production databases are running live traffic. APIs have rate limits. Files arrive late or malformed. Schemas change without warning.

**Transform**: clean and reshape the raw data so it is useful. Remove nulls. Join with reference tables. Convert timestamps to UTC. Aggregate millions of events into daily summaries. This is where most of the business logic lives.

**Load**: write the transformed data to the destination. This destination might be a data warehouse for SQL analytics, an object store for ML training, a search index, or a cache.

#### Why Pipelines Fail

Pipelines fail constantly. This is not a defect in your design — it is a fact of distributed systems. Networks drop packets. Disks fill up. The upstream team changes a column from `INTEGER` to `VARCHAR` without telling anyone. The API starts returning a new field your parser does not understand. A cloud region goes down at 3 AM.

The entire job of pipeline engineering is making these failures **recoverable**: when a stage fails, you can re-run it safely without corrupting or duplicating data. This is the property called **idempotency**, and we will cover it in depth. But first, a foundational choice every team makes when designing a pipeline.

---

### ETL vs ELT: A Real Distinction at L6

There are two schools of thought on pipeline architecture. The difference is about **where transformation happens**.

#### ETL: Extract, Transform, Load

In the ETL model, you transform data **before** it touches the warehouse.

```
Source DB
    |
    v
+------------------+
| Extract raw data |
+------------------+
    |
    v
+------------------+
| Transform in     |  <-- Spark cluster, Python, custom code
| compute layer    |      Heavy joins, ML feature engineering
+------------------+
    |
    v
+------------------+
| Load ONLY clean  |  <-- Only transformed data written
| data to warehouse|      Raw data never stored here
+------------------+
    |
    v
Warehouse / Dashboard
```

The warehouse sees only clean, transformed data. Raw data is processed and discarded (or archived cheaply in object storage).

**When to use ETL:**
- Transformations are too complex for SQL. Custom ML feature engineering, binary file parsing, natural language processing — things that need real code, not declarative SQL.
- Your warehouse compute budget is tight. If you are paying $3 per credit-hour on Snowflake, you do not want it running expensive transformations when a Spark cluster can do it cheaper.
- You have compliance requirements where raw data (with PII) must never land in the analytics warehouse.

#### ELT: Extract, Load, Transform

In the ELT model, you load raw data **first**, then transform it **inside** the warehouse using SQL.

```
Source DB
    |
    v
+------------------+
| Extract raw data |
+------------------+
    |
    v
+------------------+
| Load RAW data to |  <-- Raw data lands in warehouse first
| warehouse        |      (raw schema / raw layer)
+------------------+
    |
    v
+---------------------------+
| Transform INSIDE warehouse|  <-- dbt SQL runs here
| using SQL (dbt)           |      MERGE, JOIN, GROUP BY
+---------------------------+
    |
    v
+------------------+
| Analytics layer  |  <-- Cleaned tables, dashboard-ready
| in same warehouse|
+------------------+
    |
    v
BI Tool / Dashboard
```

**When to use ELT:**
- You are on a modern data stack: Snowflake, BigQuery, or Redshift. These warehouses have enormous compute power and can run SQL transforms cheaply.
- Your team is SQL-first. Analysts can write and maintain dbt models themselves, without needing a Spark engineer.
- You want to preserve raw data forever and re-transform it as your business logic changes. You keep the raw data as the source of truth, and the transformed tables are just views of it.

#### The Shift in the Industry

Most new teams starting in 2020 or later choose ELT. Here is why:

Cloud warehouses got dramatically cheaper and more powerful. Snowflake and BigQuery can run a complex SQL transform on 10 billion rows in minutes. Keeping raw data around gives you a **replay** capability: if your transformation logic had a bug last month, you can fix the SQL and re-run the transform against the same raw data, without re-extracting from the source.

| Property | ETL | ELT |
|---|---|---|
| Where raw data lands | Compute layer (temp), discarded | Warehouse (raw schema), preserved |
| Transform language | Python, Scala, Spark | SQL (usually dbt) |
| Warehouse compute used | Low (transforms done before load) | Higher (transforms run in warehouse) |
| Flexibility on schema changes | Low (pipeline code must be updated) | High (re-run dbt models) |
| Replay / re-transform | Hard (raw data gone) | Easy (raw data always there) |
| Storage cost | Lower (only transformed data) | Higher (raw + transformed both stored) |
| Best tools | Spark, Airflow, AWS Glue | Fivetran, dbt, Snowflake, BigQuery |
| Best team fit | Engineering-heavy teams | Analytics + engineering hybrid teams |

---

### The Modern Data Stack (ELT in Practice)

Most companies building new data infrastructure in the last few years use roughly this architecture:

```
+------------+  +------------+  +------------+  +----------+  +----------+
| Salesforce |  | PostgreSQL |  |  Stripe    |  |  GitHub  |  | AppFlows |
+------------+  +------------+  +------------+  +----------+  +----------+
      |               |               |               |             |
      +---------------+---------------+---------------+-------------+
                                    |
                                    v
                          +-------------------+
                          |  Fivetran/Airbyte  |  <-- Managed connectors
                          |  (Extract + Load)  |      200+ source types
                          +-------------------+
                                    |
                                    v
                    +------------------------------+
                    |  BigQuery / Snowflake          |
                    |  RAW SCHEMA                   |  <-- Raw, unmodified data
                    |  (salesforce_raw, stripe_raw) |
                    +------------------------------+
                                    |
                                    v
                          +-------------------+
                          |   dbt             |  <-- SQL transforms
                          |   (Transform)     |      version-controlled, tested
                          +-------------------+
                                    |
                                    v
                    +------------------------------+
                    |  BigQuery / Snowflake          |
                    |  ANALYTICS SCHEMA             |  <-- Clean, joined tables
                    |  (dim_users, fct_orders)      |
                    +------------------------------+
                                    |
                                    v
                    +------------------------------+
                    |  Looker / Tableau / Metabase  |  <-- Dashboards, reports
                    +------------------------------+
```

**Fivetran** handles extraction and loading. It ships 200+ pre-built connectors to sources like Salesforce, PostgreSQL, Stripe, and Google Analytics. You configure it in a UI, give it credentials, tell it how often to sync, and it handles everything: schema detection, incremental updates, retries, backfill. Zero pipeline code to write for the extract step.

**BigQuery** (or Snowflake/Redshift) is the warehouse. It stores both the raw schema (what Fivetran loaded) and the analytics schema (what dbt built). BigQuery charges per query scanned — roughly $5 per terabyte — so it is very cheap for low-volume analytics.

**dbt** (data build tool) is a SQL-based transformation framework. You write SQL `SELECT` statements, dbt wraps them in `CREATE TABLE AS SELECT` or `INSERT OVERWRITE` logic, runs them in the right order based on dependencies, and tests the outputs. It is version-controlled in Git like application code. A junior analyst can write and ship a dbt model; an engineer reviews it in a pull request.

**Looker or Tableau** connects to the analytics schema and builds dashboards.

---

### Idempotency: The Most Important Property of Any Pipeline

Let's talk about an ATM.

You walk up, request $200. The ATM sends the debit instruction to your bank. The bank deducts $200. Then the network drops before the ATM gets a confirmation. The ATM does not know if the transaction succeeded. Should it retry? If it retries, does your bank deduct $200 again?

A well-designed banking system handles this with **idempotency keys**. The ATM sends a unique transaction ID with the request. If the bank already processed a request with that ID, it returns the same result without charging you again. You can retry a thousand times — same result.

An **idempotent pipeline** produces the **same output** when run multiple times with the same input. If your pipeline runs at 2 AM and fails halfway through, you need to be able to re-run it at 3 AM and get the correct result — not double the data.

This matters more than almost anything else in pipeline design. Pipelines WILL fail. Every engineer who has run a production pipeline has a story about a re-run that doubled revenue numbers in a dashboard and caused an executive to call them at 7 AM.

#### Non-Idempotent (Dangerous) Example

```sql
-- DO NOT DO THIS:
INSERT INTO daily_sales
SELECT date, SUM(amount) as revenue
FROM orders
WHERE date = '2024-03-01'
GROUP BY date;
```

Run this once: you have one row for 2024-03-01 with correct revenue.

Run this twice (because the job failed and you re-ran it): you have TWO rows for 2024-03-01. Your revenue dashboard now shows 2x actual revenue. Your CEO is very excited for 30 minutes.

#### Idempotency Strategy 1: Partition Overwrite

Instead of appending, **overwrite the partition** for the date you are processing.

```sql
-- In Spark (Python):
df.write \
  .mode("overwrite") \
  .partitionBy("date") \
  .parquet("s3://bucket/daily_sales/")

-- In BigQuery:
INSERT OVERWRITE daily_sales
PARTITION (date = '2024-03-01')
SELECT date, SUM(amount) as revenue
FROM orders
WHERE date = '2024-03-01'
GROUP BY date;
```

First run: writes `date=2024-03-01/part-0001.parquet`.
Second run: **deletes** `date=2024-03-01/part-0001.parquet`, writes a fresh copy.
Same input, same output, always. Safe.

#### Idempotency Strategy 2: Delete Then Insert

When working with a relational database that does not support partition overwrite:

```sql
-- Step 1: delete existing data for this date
DELETE FROM daily_sales WHERE date = '2024-03-01';

-- Step 2: insert fresh data
INSERT INTO daily_sales
SELECT date, SUM(amount) as revenue
FROM orders
WHERE date = '2024-03-01'
GROUP BY date;
```

Wrap both steps in a transaction if possible. If the job fails between steps, the transaction rolls back and you start clean on the next run.

#### Idempotency Strategy 3: Upsert (MERGE INTO)

When output rows have a primary key (like `order_id`), use a MERGE statement that handles both new records and updates:

```sql
MERGE INTO orders_summary AS target
USING (
    SELECT order_id, SUM(amount) as total
    FROM order_items
    WHERE date = '2024-03-01'
    GROUP BY order_id
) AS source
ON target.order_id = source.order_id
WHEN MATCHED THEN
    UPDATE SET target.total = source.total
WHEN NOT MATCHED THEN
    INSERT (order_id, total) VALUES (source.order_id, source.total);
```

Running this twice with the same source data: the second run hits the `WHEN MATCHED` branch and updates to the same value. Net result is identical. Safe.

#### Idempotency Strategy 4: Atomic File Swap

When writing large files to a distributed file system, writes are not instantaneous. If a reader reads during a write, it sees partial data — some new files, some old files, some nothing.

The solution is a **two-phase atomic swap**:

```
Phase 1: Write to TEMP location (invisible to readers)
+-----------------------------------+
| s3://bucket/tmp/2024-03-01/       |
|   part-0001.parquet  (writing...) |
|   part-0002.parquet  (writing...) |
+-----------------------------------+

Phase 2: Atomic rename to FINAL location (instant from readers' perspective)
s3://bucket/daily_sales/date=2024-03-01/
  part-0001.parquet
  part-0002.parquet
```

The `rename` operation is atomic on HDFS and most distributed file systems. Readers see either the old complete data or the new complete data. Never partial. Spark's `write.mode("overwrite")` does this internally.

---

## 2. Change Data Capture (CDC): Incremental Extraction

### The Problem With Full Extracts

The naive approach to getting data out of a production database is a full extract:

```sql
SELECT * FROM orders;
```

Run this every night, dump the result to S3, process it. Simple.

This works when your `orders` table has 10,000 rows. It stops working when it has 100 million rows.

At 100 million rows, 1 KB per row on average: that is **100 GB** of data transferred every night. At a typical throughput of 10 GB/hour for a database scan plus network transfer, that is a 10-hour window for your nightly job. The query itself puts a massive read load on your production database — the same one handling live user traffic at 2 AM.

At 10x growth (1 billion rows): 1 TB transferred, 100 hours. Impossible. Your nightly job takes longer than the day.

There is another problem: **deletes**. If order 456 was deleted from the orders table (customer cancellation, GDPR deletion request), your full extract does not tell you that. You get a snapshot of what exists now, with no record of what was removed.

### CDC: Capture Only What Changed

**Change Data Capture (CDC)** captures only the rows that changed since the last extraction: inserts, updates, and deletes. Instead of copying 100 GB every night, you copy the 50,000 rows that changed in the last hour. That is 50 MB instead of 100 GB — 2,000x less data.

```
Without CDC (full extract):
+---------------+       100 GB every night       +------------------+
| Production DB | ----------------------------> | Data Warehouse   |
| 100M rows     |   slows prod DB, 10 hours      |                  |
+---------------+                               +------------------+

With CDC (incremental):
+---------------+      50 MB (only changes)      +------------------+
| Production DB | ----------------------------> | Data Warehouse   |
| 100M rows     |   no prod DB load, 5 minutes   |                  |
+---------------+                               +------------------+
```

#### CDC Method 1: WAL-Based (Best)

Every modern relational database maintains a **Write-Ahead Log (WAL)**. This is a sequential record of every change made to the database, written before the change is applied to the actual data pages. The WAL is how the database recovers from crashes: if the server crashes, it replays the WAL.

In PostgreSQL, this is the WAL (`pg_wal/`). In MySQL, it is the binlog. In MongoDB, it is the oplog.

WAL-based CDC reads this log instead of querying the tables directly.

Advantages:
- Zero additional load on the production database. You are reading a log file, not running a SELECT query.
- Captures all operations: INSERT, UPDATE, and DELETE.
- Near-real-time: changes appear in the WAL within milliseconds.

The primary tool for WAL-based CDC is **Debezium**.

#### CDC Method 2: Timestamp-Based

The simpler but weaker approach: add an `updated_at` column to every table, index it, and query only rows updated since last run.

```sql
SELECT * FROM orders
WHERE updated_at > '2024-03-01 02:00:00'
  AND updated_at <= '2024-03-01 03:00:00';
```

**Problems:**
- Does not capture deletes. A deleted row disappears from the table — no `updated_at` to query.
- Clock skew: if the application server's clock and the database server's clock differ by even a few seconds, you can miss rows written near the boundary window.
- Requires `updated_at` on every table. If a team forgets to add it to a table, CDC breaks for that table silently.
- Polling adds some query load (minor compared to full extract, but not zero).

Use timestamp-based CDC only when WAL access is impossible (e.g., a hosted SaaS database that does not expose the WAL).

#### CDC Method 3: Trigger-Based

Database triggers fire on INSERT, UPDATE, DELETE and write a record to a changelog table:

```sql
CREATE TRIGGER orders_cdc
AFTER INSERT OR UPDATE OR DELETE ON orders
FOR EACH ROW EXECUTE FUNCTION log_change();
```

The trigger function writes the changed row to an `orders_changelog` table. A separate process reads and processes that changelog.

**Problems:**
- Triggers add 5–10% write latency to every INSERT/UPDATE/DELETE on the source table. On a high-traffic orders table, this is significant.
- The changelog table grows unboundedly — you need to prune it, which is another maintenance job.
- Harder to capture bulk operations (some bulk inserts skip triggers).

Trigger-based CDC is mostly a legacy approach. Prefer WAL-based.

### Debezium: The Production CDC Tool

**Debezium** is an open-source CDC platform built on Kafka Connect. It reads the database WAL and publishes every change as a Kafka message.

For PostgreSQL, Debezium uses the `pgoutput` logical replication plugin (built into Postgres 10+). For MySQL, it reads the binlog. For MongoDB, the oplog.

Each Kafka message contains the full before and after state of the changed row, plus metadata about the operation:

```json
{
  "before": {
    "id": 456,
    "user_id": 789,
    "amount": 99.99,
    "status": "pending"
  },
  "after": {
    "id": 456,
    "user_id": 789,
    "amount": 99.99,
    "status": "shipped"
  },
  "op": "u",
  "ts_ms": 1709251200000,
  "source": {
    "table": "orders",
    "db": "production"
  }
}
```

`op` values: `"c"` (create/insert), `"u"` (update), `"d"` (delete), `"r"` (snapshot/read).

The architecture:

```
+--------------------+
| PostgreSQL         |
|  WAL (pg_wal/)     |
|  (sequential log   |
|   of all changes)  |
+--------------------+
         |
         | pgoutput logical replication
         v
+-------------------------+
| Debezium Connector      |  <-- Runs inside Kafka Connect
| (Postgres Source        |      worker cluster
|  Connector)             |
+-------------------------+
         |
         | Kafka messages (one per row change)
         v
+--------------------------------------------+
| Kafka Topic: cdc.public.orders             |
+--------------------------------------------+
         |
    +----+----+------+
    |         |      |
    v         v      v
+--------+ +------+ +------------------+
| Data   | |Search| | Cache            |
| Ware-  | |Index | | Invalidation     |
| house  | |(ES)  | | (Redis DEL key)  |
| Loader |
+--------+
```

Multiple consumers can read the same Kafka topic independently: a warehouse loader that writes changes to Snowflake, an Elasticsearch indexer that keeps search in sync, a cache invalidation service that deletes Redis keys when the underlying row changes. Each consumer tracks its own offset — they do not interfere with each other.

### The Outbox Pattern vs CDC

A common problem in microservices: a service needs to write to its database AND publish an event to Kafka, atomically. If the DB write succeeds but the Kafka publish fails, you have inconsistent state.

Two-phase commit (2PC) across DB and Kafka is complex and adds latency. The better solution is the **outbox pattern**:

```
In the SAME database transaction:
+-------------------------------------------+
| BEGIN TRANSACTION                          |
|   INSERT INTO orders (id, amount, status) |
|     VALUES (456, 99.99, 'pending');        |
|                                            |
|   INSERT INTO outbox (event_type, payload)|
|     VALUES ('order_created', '{"id":456}')|
| COMMIT TRANSACTION                         |
+-------------------------------------------+
         |
         | (transaction is atomic: both succeed or both fail)
         v
+-------------------------------+
| outbox table in same database |
| [event_type | payload | sent] |
+-------------------------------+
         |
         | Debezium reads outbox table via WAL
         | (or a poller reads and marks sent)
         v
+--------+
| Kafka  |
+--------+
```

The business write and the outbox write happen in one transaction. Debezium watches the outbox table and publishes each row to Kafka. Once published, the row is marked as sent (or deleted).

**CDC vs outbox distinction**: Debezium reading the WAL captures ALL changes to a table — including direct SQL operations, schema migrations, and bulk loads. The outbox pattern captures only explicit application-level events. If you need guaranteed-correct business event semantics (not raw row changes), use the outbox. If you need to replicate everything that happens to a table (including ops team changes), use direct CDC.

---

## 3. Data Storage: Lake, Warehouse, Lakehouse

### Data Lake: Cheap, Flexible, Messy

A **data lake** is object storage (Amazon S3, Google Cloud Storage) used to store data in any format: CSV, JSON, Parquet, Avro, images, ML model artifacts, log files.

Cost: S3 Standard charges roughly $0.023 per GB per month. At that price, storing 100 TB of raw data costs $2,300/month — affordable for most companies.

**Schema-on-read**: you define the schema when you query, not when you write. You can dump raw JSON from your application into S3 without thinking about column names or types. When you later query it with Athena or Spark, you define what the schema looks like at query time.

This sounds great. The problem is: there are no transactions, no ACID guarantees, no support for row-level updates or deletes. Object storage is designed for PUT and GET, not UPDATE or DELETE.

```
Problem: concurrent writes to a data lake

Writer A: uploads part-0001.parquet, part-0002.parquet (still uploading...)
Reader B: starts reading the directory, sees part-0001.parquet only
Result:   Reader B gets incomplete data -- sees only half the results
```

No two-phase commit. No locks. If a writer is mid-upload when a reader queries, the reader sees partial data. This is acceptable for some use cases (archiving, ML training data) and disqualifying for others (reporting, dashboards).

### Data Warehouse: Fast, Structured, Expensive

A **data warehouse** is a managed database built specifically for analytics SQL queries. It uses columnar storage, massively parallel query execution, and sophisticated compression.

Examples: **Snowflake**, **Google BigQuery**, **Amazon Redshift**.

**Schema-on-write**: you define the schema before writing. Strong types. ACID transactions. MERGE INTO is supported. Concurrent writers do not corrupt data.

Warehouses are expensive relative to object storage. Snowflake charges $2–4 per credit-hour for compute, plus storage costs. BigQuery charges $5 per terabyte scanned by queries. A team running heavy analytics workloads can easily spend $50,000–$500,000/year.

Best for: BI dashboards, executive reporting, ad-hoc SQL analytics where business analysts write queries, revenue reporting, A/B test analysis.

### Lakehouse: Best of Both Worlds

The **lakehouse** architecture combines the cheap storage of a data lake with the transactional guarantees of a data warehouse. The core idea: add a **metadata and transaction layer** on top of object storage (S3/GCS). This layer handles ACID transactions, schema enforcement, and MERGE operations — all while data stays in Parquet files in cheap object storage.

Three major open formats implement this:

```
+-----------------------------------------------------------+
|                     LAKEHOUSE FORMATS                     |
+-----------------------------------------------------------+
| Delta Lake    | Databricks. Most mature. Best Spark        |
|               | integration. Transaction log alongside    |
|               | Parquet in S3. Widely adopted.            |
+---------------+-------------------------------------------+
| Apache Iceberg| Netflix / Apple origin. Engine-agnostic:  |
|               | works with Spark, Flink, Presto, Trino,   |
|               | Snowflake. Hidden partitioning. Growing   |
|               | fastest in open-source community.         |
+---------------+-------------------------------------------+
| Apache Hudi   | Uber origin. Optimized for CDC-style      |
|               | upserts. Best for high-frequency          |
|               | incremental writes. Good Spark + Flink    |
|               | integration.                              |
+-----------------------------------------------------------+
```

### How Delta Lake Transactions Work

Delta Lake stores data as **Parquet files** in S3 (the same files a plain data lake would use). The magic is in a separate folder: `_delta_log/`.

```
s3://bucket/orders/
+-- _delta_log/
|   +-- 00000000000000000000.json   (initial snapshot)
|   +-- 00000000000000000001.json   (transaction 1: added 5 files)
|   +-- 00000000000000000002.json   (transaction 2: removed 2 files, added 3)
|   +-- 00000000000000000003.json   (transaction 3: MERGE INTO operation)
|
+-- part-00001-abc123.parquet
+-- part-00002-def456.parquet
+-- part-00003-ghi789.parquet
+-- part-00004-jkl012.parquet  (added in transaction 2)
+-- part-00005-mno345.parquet  (added in transaction 3)
```

Each entry in the `_delta_log/` folder is a JSON file describing one transaction:

```json
{
  "add": {"path": "part-00004-jkl012.parquet", "size": 104857600},
  "remove": {"path": "part-00001-abc123.parquet"}
}
```

When a reader wants to query the table:
1. Read the `_delta_log/` entries in order from the beginning (or from the latest checkpoint).
2. Build a list of which Parquet files are "current" (added but not yet removed).
3. Read only those Parquet files.

This gives you:

**Atomicity**: if a write fails halfway through, no log entry is added. Readers never see partial writes. The orphaned Parquet files are invisible to readers.

**Time travel**: read the log up to transaction N to see the state of the table at that point in history. The old Parquet files (marked as removed but not deleted from S3) are still there, still readable.

**MERGE INTO**: a MERGE operation writes new Parquet files (the merged result) and removes old ones, atomically in one log entry.

```
How a MERGE INTO executes in Delta Lake:

Step 1: Read current table files (follow the log)
+-- part-00001.parquet (current)
+-- part-00002.parquet (current)

Step 2: Find rows that match the MERGE condition
+-- rows from part-00001.parquet that match: update them -> part-00004.parquet
+-- rows that don't match: pass through -> part-00003.parquet (new copy)

Step 3: Write one log entry atomically:
{
  "add": ["part-00003.parquet", "part-00004.parquet"],
  "remove": ["part-00001.parquet"]
}

Result: readers now see part-00002 + part-00003 + part-00004
        part-00001 is logically deleted (still in S3 for time travel)
```

### Time Travel: Querying Historical Data

Both Delta Lake and Apache Iceberg support querying a table **as it existed at a specific point in the past**.

```sql
-- Delta Lake: query as of a specific version
SELECT * FROM orders VERSION AS OF 10;

-- Delta Lake: query as of a specific timestamp
SELECT * FROM orders TIMESTAMP AS OF '2024-03-01 00:00:00';

-- Apache Iceberg (Spark):
SELECT * FROM catalog.orders FOR SYSTEM_TIME AS OF '2024-03-01 00:00:00';
```

**Use cases at scale:**

Audit queries: "What did the `users` table look like before the GDPR deletion job ran?" You query the table as of before the deletion. No backups needed.

Debugging: "The pipeline wrote bad data at 3 AM. What did the table look like before that run?" Read the table at 2:59 AM. Compare with 3:01 AM. Find the discrepancy.

ML reproducibility: Netflix uses Iceberg time travel to ensure ML experiments are reproducible. When they re-train a model six months later, they query the exact same snapshot of training data that existed when the original experiment ran. Without time travel, you can not reproduce the exact training set — data has changed, rows were added and deleted. With Iceberg, you query `FOR SYSTEM_TIME AS OF '2024-09-15'` and get exactly what the model was trained on.

### Parquet: The File Format of Choice

**Parquet** is a columnar file format. This sounds like a minor implementation detail. It is actually one of the biggest performance levers in data engineering.

Think about how data is stored in a regular row-oriented file (like CSV):

```
Row-oriented (CSV):
Row 1: [order_id=1, user_id=101, amount=99.99, status=shipped, created_at=...]
Row 2: [order_id=2, user_id=102, amount=49.99, status=pending, created_at=...]
Row 3: [order_id=3, user_id=101, amount=199.99, status=shipped, created_at=...]
...
```

Every row is contiguous on disk. To read `order_id` and `amount` for all rows, you must read all bytes of every row (including `user_id`, `status`, `created_at`, everything else) and then discard the columns you do not need.

Columnar storage (Parquet) stores each column contiguously:

```
Columnar (Parquet):
order_id column:  [1, 2, 3, 4, 5, ...]
user_id column:   [101, 102, 101, 103, ...]
amount column:    [99.99, 49.99, 199.99, 29.99, ...]
status column:    [shipped, pending, shipped, pending, ...]
created_at column:[..., ..., ..., ..., ...]
```

An analytics query like `SELECT SUM(amount) FROM orders WHERE date = '2024-03-01'` needs only two columns: `amount` and `date`. Parquet reads only those two columns off disk. If `amount` is 8 bytes per row and you have 100 columns, Parquet reads 1/50th of the data that a row-format file would require. That is a 50x reduction in I/O, and I/O is almost always the bottleneck in large-scale analytics.

**Compression**: because all values in a column are the same type, they compress extremely well. The `user_id` column contains 64-bit integers. Delta encoding (store the difference between consecutive values instead of the absolute value) compresses a sorted user_id column by 10–20x. Run-length encoding compresses repeated values in `status` ("shipped", "shipped", "shipped", "pending"...) dramatically.

Real-world impact: when Uber migrated their data pipelines from CSV to Parquet, they reduced storage costs by 85% and query execution times by 90%. Those are not unusual numbers — Parquet routinely delivers 5–10x query speedups and 5–10x storage reduction over CSV or JSON for analytics workloads.

---

## 4. Pipeline Orchestration: Airflow and Friends

### Why Orchestration Exists

A real production pipeline is not one job. It is a graph of 10 to 100 jobs with dependencies.

"Run the revenue report ONLY AFTER the orders ETL AND the users ETL AND the product catalog ETL all complete successfully."

"If the orders ETL fails on its first attempt, retry it up to 3 times with a 5-minute gap between retries. If all retries fail, page the on-call engineer and halt all downstream jobs."

"The pipeline had a bug for the last 30 days. Fix the bug, then re-run all 30 days of data in parallel, but do not overwhelm the source database — throttle to 5 days at a time."

An **orchestrator** manages scheduling, dependencies, retries, backfill, and monitoring. Without it, you have a mess of cron jobs and bash scripts that fail silently and have hidden dependencies no one has documented.

### Apache Airflow: The Standard

**Apache Airflow** represents a pipeline as a **DAG** (Directed Acyclic Graph) of tasks. Each task is one unit of work (a Spark job, a SQL query, a Python function, a shell command). Edges between tasks define dependencies.

```
Example: Daily Revenue Pipeline DAG

+------------------+
| extract_orders   |  task 1: pull orders from Postgres via CDC
+------------------+
         |
+------------------+   +------------------+
| transform_orders |   | extract_users    |  tasks run in parallel
+------------------+   +------------------+
         |                    |
         +--------+-----------+
                  |
         +------------------+
         | join_and_enrich  |  waits for both upstream tasks
         +------------------+
                  |
       +----------+----------+
       |                     |
+------------+    +------------------+
| revenue_   |    | user_cohort_     |
| report     |    | report           |
+------------+    +------------------+
```

The Python definition:

```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime

with DAG(
    dag_id='daily_revenue_pipeline',
    schedule_interval='0 2 * * *',   # 2 AM every day
    start_date=datetime(2024, 1, 1),
    catchup=True                      # backfill past missed runs
) as dag:

    extract_orders = PythonOperator(
        task_id='extract_orders',
        python_callable=run_orders_cdc,
        op_kwargs={'execution_date': '{{ ds }}'}
    )

    extract_users = PythonOperator(
        task_id='extract_users',
        python_callable=run_users_extract,
        op_kwargs={'execution_date': '{{ ds }}'}
    )

    transform = PythonOperator(
        task_id='transform_and_join',
        python_callable=run_spark_transform
    )

    report = PythonOperator(
        task_id='revenue_report',
        python_callable=write_revenue_report
    )

    [extract_orders, extract_users] >> transform >> report
```

The `>>` operator defines dependencies. `[A, B] >> C` means C waits for both A and B. This is a DAG: no cycles allowed (hence "Acyclic").

**Components of Airflow:**

```
+------------------+        +-------------------+
| Scheduler        |        | Web UI            |
| - watches clock  |        | - view DAG graph  |
| - checks deps    |        | - trigger runs    |
| - queues tasks   |        | - see task logs   |
+------------------+        +-------------------+
         |
         | puts tasks onto queue
         v
+------------------+
| Message Queue    |  (Redis or RabbitMQ)
+------------------+
         |
         | workers pull tasks from queue
         v
+------------------+
| Workers (pool)   |  execute tasks: Spark, SQL, Python, shell
+------------------+
         |
         | write state: success / failed / retrying
         v
+------------------+
| Metadata DB      |  (PostgreSQL): stores DAG run history,
| (PostgreSQL)     |  task states, task logs, SLAs
+------------------+
```

### Airflow Critical Concepts at L6

#### Execution Date vs Run Date

This is a subtle distinction that trips up junior engineers and causes production incidents.

**Execution date**: the logical date the DAG is processing. This is "the date of the data," not "the date the job ran." If your daily pipeline processes yesterday's data, the execution date for the job that runs on March 2nd is March 1st.

**Run date**: the actual wall-clock time when Airflow triggered and executed the DAG.

Why does this matter? Imagine the Airflow scheduler goes down for 3 days due to an infrastructure failure. When it recovers, `catchup=True` means Airflow will backfill all 3 missed runs. Each backfill run has its own `execution_date` (day 1, day 2, day 3 of the outage). The run_date for all three is "today" (recovery day), but the execution dates span those 3 missed days.

If your pipeline uses the run date to parameterize queries instead of the execution date, all 3 backfill runs process today's data — you get 3x today's data and 0x data for the missed days.

Always parameterize your queries with `execution_date` (the Jinja template `{{ ds }}` in Airflow gives you the execution date as a string):

```sql
-- CORRECT: use execution date
SELECT * FROM events
WHERE event_date = '{{ ds }}';

-- WRONG: uses current time, breaks on backfill
SELECT * FROM events
WHERE event_date = CURRENT_DATE;
```

#### Idempotency in Airflow DAGs

Every task in an Airflow DAG must be idempotent. The scheduler can retry tasks. Engineers can manually re-trigger DAG runs. If your tasks append instead of overwrite, every retry or re-trigger doubles your data.

The pattern: use `{{ ds }}` (the execution date) both as the filter for input data and as the partition key for output data.

```python
def load_daily_orders(execution_date, **kwargs):
    date_str = execution_date.strftime('%Y-%m-%d')

    # Read only this day's data
    df = spark.sql(f"""
        SELECT * FROM raw_orders
        WHERE order_date = '{date_str}'
    """)

    # Write to this day's partition (overwrite if exists)
    df.write \
      .mode("overwrite") \
      .partitionBy("order_date") \
      .parquet(f"s3://bucket/processed_orders/")
```

Running this task twice for `execution_date = 2024-03-01`: both times it reads the same rows, both times it overwrites the same partition. Safe.

#### Sensors: Waiting for External Conditions

**Sensors** are special Airflow tasks that poll for an external condition before allowing the pipeline to proceed.

```python
from airflow.sensors.s3_key_sensor import S3KeySensor

wait_for_partner_file = S3KeySensor(
    task_id='wait_for_partner_data',
    bucket_name='partner-data-drops',
    bucket_key='daily/{{ ds }}/orders.csv',
    timeout=60 * 60 * 4,   # fail after 4 hours of waiting
    poke_interval=60 * 5,  # check every 5 minutes
    mode='reschedule'       # release worker slot between checks
)

# Only proceed after file arrives
wait_for_partner_file >> process_partner_data
```

**`FileSensor` / `S3KeySensor`**: wait for a specific file or S3 key to appear.

**`ExternalTaskSensor`**: wait for a task in a different DAG to complete. Useful when DAG A must finish before DAG B can start.

**`HttpSensor`**: poll an HTTP endpoint until it returns a success status code. Useful for waiting for an upstream API to confirm data is ready.

The `mode='reschedule'` parameter is critical for long-running sensors: instead of holding a worker slot while polling (which wastes workers), it releases the slot between checks and re-queues itself. Without this, a sensor waiting 4 hours ties up a worker slot for 4 hours.

### Airflow Alternatives

Airflow has been the industry standard since Airbnb open-sourced it in 2014. But it has real weaknesses: the scheduler is complex, dynamic DAGs are painful to build, and the developer experience is rough. Several strong alternatives exist.

| Property | Apache Airflow | Prefect | Dagster |
|---|---|---|---|
| Core model | Task graph (DAG) | Flow + Task (Python) | Software-defined assets |
| Dynamic DAGs | Painful (requires complex patterns) | Native Python | Native |
| Developer experience | Medium (YAML + Python mix) | High (pure Python) | High (type-safe) |
| Observability | Basic (metadata DB) | Built-in (Prefect Cloud) | Built-in (asset catalog) |
| Testing | Weak | Good | Excellent (unit testable) |
| Community size | Largest | Growing | Growing |
| Best team size | Any (due to ecosystem) | Small to medium | Medium to large |
| Hosted option | Astronomer (paid) | Prefect Cloud | Dagster Cloud |

**Prefect**: more Python-native than Airflow. You decorate regular Python functions with `@flow` and `@task`. Dynamic task generation is trivial — just write a Python loop. Prefect Cloud provides hosted observability. The community is smaller than Airflow's, so fewer pre-built integrations.

**Dagster**: the most sophisticated of the three. Dagster thinks in terms of **data assets** rather than tasks. Instead of "run this task," you define "here is what the `orders_daily_summary` asset looks like, and here is how to produce it." Dagster understands data lineage at the column level, makes testing straightforward, and has an excellent UI for exploring data assets. Best for engineering teams building a formal data platform, not just running ad-hoc ETL.

**dbt**: not a general orchestrator — it only handles SQL transforms. But it pairs naturally with Airflow or Dagster for the transformation step of ELT pipelines. Many teams run: Fivetran → S3 → Airflow triggers dbt → dbt transforms in Snowflake → Tableau.

### Common Airflow Failure Patterns

Understanding failure modes is a Level 6 skill. Junior engineers know how Airflow works when it works. Staff engineers know what happens when it breaks.

**Failure Pattern 1: DAG Deadlock**

A DAG has an undetected circular dependency: Task A waits for Task B, and Task B waits for Task A. Both tasks are in "queued" state indefinitely. No error — just silence. Everything is stuck.

```
Circular dependency (detected at parse time if DAG validation runs):

A --> B --> C
^           |
|           v
+-----------D
```

Prevention: Airflow validates that DAGs are acyclic at parse time and raises a `DagCycleException`. Add a CI check that imports all DAG files and confirms they parse without errors before merging.

**Failure Pattern 2: Worker Exhaustion**

Your Airflow cluster has 20 worker slots. A backfill job fires off 200 tasks simultaneously. All 200 tasks are now in "queued" state. Nothing is running. The workers are all occupied with the first 20 tasks, and 180 are sitting in queue. Eventually tasks time out, which fires retries, which adds more tasks to the queue. The cluster spirals.

Fix: set `max_active_tasks_per_dag` and `max_active_runs` limits in Airflow config. For backfills, use the `--max-active-runs` flag to throttle how many parallel DAG runs execute.

**Failure Pattern 3: Backfill Explosion**

Your pipeline had a bug for 30 days. You fix the bug and trigger a backfill: 30 days × 20 tasks per day = 600 tasks queued simultaneously. This overwhelms your workers, hammers your source database with 30 concurrent CDC extracts, and floods your destination warehouse with 30 simultaneous MERGE operations.

Fix: backfill in batches. Trigger backfill for 5 days, wait for it to complete, trigger the next 5 days. Or use Airflow's `--rerun-failed-tasks` flag with limited parallelism.

---

## 5. Idempotency Patterns for Batch

This section consolidates the idempotency strategies mentioned throughout the chapter into a single reference. At L6, you must be able to choose the right strategy for any pipeline output type — files, database tables, or streaming sinks.

### Partition Overwrite (Most Common)

When your output is partitioned files (the most common case in modern data stacks), use partition overwrite.

```python
# Spark: write date-partitioned Parquet, overwrite the partition on re-run
df.write \
  .mode("overwrite") \
  .partitionBy("date") \
  .parquet("s3://data-lake/processed_orders/")
```

On disk: `date=2024-03-01/part-00001.parquet`. Re-running overwrites only the `date=2024-03-01/` directory; other partitions are untouched.

One gotcha: Spark's `mode("overwrite")` without `partitionBy` overwrites the **entire** table. Always combine both, or set `spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")` to enable partition-scoped overwrite automatically.

### Upsert With Primary Key

When output is a relational database table (not files), use MERGE INTO (upsert). Snowflake and BigQuery syntax:

```sql
MERGE INTO daily_order_summary AS target
USING (
    SELECT order_date, COUNT(*) AS order_count, SUM(amount) AS revenue
    FROM orders WHERE order_date = '2024-03-01'
    GROUP BY order_date
) AS source
ON target.date = source.order_date
WHEN MATCHED THEN UPDATE SET
    target.order_count = source.order_count,
    target.revenue = source.revenue
WHEN NOT MATCHED THEN INSERT
    (date, order_count, revenue)
    VALUES (source.order_date, source.order_count, source.revenue);
```

First run: inserts a new row for March 1st. Second run: finds the existing row, updates it to the same values. Result is identical. Safe. PostgreSQL uses `INSERT ... ON CONFLICT (date) DO UPDATE SET` for the same semantics.

### Atomic Swap (Two-Phase Write)

When writing large files to a distributed file system, protect against readers seeing partial data during the write.

```
Phase 1: Write to temp path
+----------------------------------------------+
| s3://bucket/tmp/run-20240301-0300/            |
|   part-00001.parquet  (still writing...)      |
|   part-00002.parquet  (still writing...)      |
|   part-00003.parquet  (still writing...)      |
+----------------------------------------------+
      [readers query s3://bucket/final/ -- still sees old data]

Phase 2: Atomic rename to final path (instantaneous)
+----------------------------------------------+
| s3://bucket/final/date=2024-03-01/            |
|   part-00001.parquet  (complete)              |
|   part-00002.parquet  (complete)              |
|   part-00003.parquet  (complete)              |
+----------------------------------------------+
      [readers now query and see complete new data]
```

Note: S3 does not natively support atomic rename across prefixes — it is a copy + delete at the SDK level. Delta Lake and Apache Iceberg implement atomic swap through their transaction log: the commit to the `_delta_log/` folder is the atomic step, not the Parquet file move. This is why writing directly to a Delta table is safer than writing raw Parquet and manually renaming: the lakehouse format handles atomicity for you.

---

## Summary: The Mental Model

If someone asks you to design a data pipeline in an L6 interview, this is the mental framework:

```
+------------------------------------------------------------------+
|                     DATA PIPELINE DECISIONS                       |
+------------------------------------------------------------------+
|                                                                   |
|  1. EXTRACTION:                                                   |
|     Full extract vs CDC?                                          |
|     - Volume > 10M rows/day: use CDC (Debezium)                  |
|     - Need deletes: must use CDC                                  |
|     - Simple setup: timestamp-based (with known limitations)      |
|                                                                   |
|  2. PATTERN:                                                      |
|     ETL vs ELT?                                                   |
|     - Modern stack + SQL-first team: ELT (dbt + Snowflake)       |
|     - Complex non-SQL transforms: ETL (Spark)                     |
|                                                                   |
|  3. STORAGE:                                                      |
|     Lake vs Warehouse vs Lakehouse?                               |
|     - Analytics + ACID + structured: Warehouse (Snowflake)        |
|     - Cheap + flexible + ML: Lake (S3 + Parquet)                  |
|     - ACID on object storage + time travel: Lakehouse (Delta)     |
|                                                                   |
|  4. ORCHESTRATION:                                                |
|     - Industry default: Airflow                                   |
|     - Better DX: Prefect                                          |
|     - Asset-based + testable: Dagster                             |
|                                                                   |
|  5. IDEMPOTENCY (always required):                                |
|     - File output: partition overwrite                            |
|     - DB table: MERGE INTO / upsert                               |
|     - Concurrent write safety: atomic swap via lakehouse format   |
|                                                                   |
+------------------------------------------------------------------+
```

Every staff-level pipeline design question requires you to address all five of these axes. Idempotency is not optional — it is the baseline correctness requirement for any pipeline that will run in production.

---
# Chapter 35: Batch Processing and Data Pipelines
## Part C: Lambda vs Kappa, Data Quality, Monitoring, Cost, and Production Incidents

---

## 0. Chapter Opening: What This Part Is About

Parts A and B of this chapter covered the mechanical foundations: how Spark actually executes jobs (DAGs, stages, tasks, shuffles), how partitioning works, what makes a batch job slow, and the core patterns of data pipeline design (Extract-Transform-Load, incremental loading, CDC, orchestration with Airflow).

This part covers the higher-level architectural and operational concerns that separate L5 from L6 thinking. An L5 engineer can build a batch pipeline that works. An L6 engineer can defend the architectural decisions behind it, ensure it stays correct at scale, monitor it properly, debug it systematically, and optimize its cost without sacrificing reliability.

Here is the specific difference in an interview. An interviewer asks: "You need to build a real-time recommendation system. How would you approach this?"

**L5 answer:** "I would use Kafka for streaming and Spark for batch. The batch job would run nightly and the stream would handle real-time updates."

**L6 answer:** "That describes Lambda architecture. Let me explain why Lambda might be the right choice here versus Kappa, which uses streaming only. Lambda gives you accuracy over all historical data combined with low latency for recent events, but at the cost of two codebases and potential divergence between batch and stream outputs for the same time window. Kappa solves the dual-codebase problem by using a single Flink job for both real-time processing and historical reprocessing via Kafka replay, but requires sufficient Kafka retention. Given this use case — a recommendation engine that needs five years of watch history for accuracy AND sub-second response to the last thing a user just watched — Lambda is likely the right choice, because five years of event history almost certainly exceeds practical Kafka retention limits. I would run a nightly Spark job over the historical data in S3 for the long-term signal, a Flink streaming job for the recency signal, and merge them at serve time using Cassandra for the batch views and Redis for the speed layer delta."

That answer demonstrates: architectural literacy, knowledge of tradeoffs, and the ability to connect the architectural choice to the actual business requirement. That is what this part prepares you to give.

**What you will understand after reading this part:**

- Why Lambda and Kappa exist, what problem each solves, and the specific conditions under which each is the right choice
- How to build data quality validation into every pipeline you write, at four layers, using real tools
- The six metrics every production batch job must emit, and how to debug a slow or failing job systematically
- How to cut batch infrastructure costs by 60-80% using techniques that major companies have validated at scale
- Five named production incidents with root causes, impact, fixes, and prevention patterns you can apply immediately

---

## 1. Lambda Architecture: Batch + Stream Together

### Why Lambda exists

Imagine you are the recommendation engine at Netflix. Your job is to tell every user, at every moment, which movie they should watch next. To do this well, you need two things at the same time, and they contradict each other.

**Thing 1: Accuracy.** You need to know everything that user has ever watched, rated, skipped, and re-watched over the past five years. A model built on five years of history is much better than one built on the last two hours. But computing a recommendation over five years of data takes time — maybe hours of batch processing.

**Thing 2: Speed.** The user just finished watching a thriller ten minutes ago. They are back on the app right now. If your recommendation system still thinks their most recent watch was a comedy from yesterday morning, your recommendations are stale. You need to incorporate that thriller — right now — into the suggestion list. Waiting until the batch job runs tonight is unacceptable.

These two requirements pull in opposite directions. A batch job is accurate because it sees all the data, but it is slow — it might run once a day. A stream processor is fast because it reacts in milliseconds, but it only sees the last few hours of events. You cannot get both from a single system built to do just one thing.

**Lambda architecture** is the engineering answer to this contradiction: run both systems at once, then combine their outputs at query time. It was formalized by Nathan Marz around 2011, and it became the dominant pattern for data pipelines at companies like Twitter, LinkedIn, and Yahoo in the early and mid 2010s.

---

### Lambda Architecture Components

Lambda has three distinct layers. Think of it like a restaurant with two kitchens and one counter.

**The batch layer** is the slow kitchen. It processes ALL historical data from the very beginning of time — every event ever recorded — on a regular schedule, typically once per hour or once per day. Because it sees everything, its output is authoritative and complete. No record is missing. No approximation. The downside is time: a batch job over five years of data might take four to six hours to finish. Tools: Apache Spark in batch mode, Hadoop MapReduce (older), or Flink in batch mode.

**The speed layer** is the fast kitchen. It only processes the RECENT data — events from the last few hours, or since the last batch job finished. Because it covers a small window, it runs in real-time or near-real-time. Its output is approximate and covers only the gap that the batch layer has not yet processed. Tools: Apache Flink, Kafka Streams, Apache Storm.

**The serving layer** is the counter that the customer (the query) actually talks to. When a query comes in, the serving layer fetches the answer from the batch layer (complete and accurate, but only up to a few hours ago) and the answer from the speed layer (covers the recent gap, potentially approximate). It merges these two partial answers into one response and hands it back.

```
+----------------------------------------------------------+
|                  LAMBDA ARCHITECTURE                     |
+----------------------------------------------------------+
|                                                          |
|   Raw Events (Kafka)                                     |
|         |                                                |
|         +-------------------+                            |
|         |                   |                            |
|         v                   v                            |
|   +----------+       +----------+                        |
|   |  BATCH   |       |  SPEED   |                        |
|   |  LAYER   |       |  LAYER   |                        |
|   | (Spark)  |       | (Flink)  |                        |
|   | All data |       | Recent   |                        |
|   | Runs Q4H |       | data only|                        |
|   | Slow/    |       | Fast/    |                        |
|   | Complete |       | Approx.  |                        |
|   +----+-----+       +----+-----+                        |
|        |                  |                              |
|        v                  v                              |
|   +----------+       +----------+                        |
|   | Batch    |       | Speed    |                        |
|   | Views    |       | Views    |                        |
|   | (S3/     |       | (Redis/  |                        |
|   |  HDFS)   |       |  Druid)  |                        |
|   +----+-----+       +----+-----+                        |
|        |                  |                              |
|        +--------+---------+                              |
|                 |                                        |
|                 v                                        |
|          +-----------+                                   |
|          |  SERVING  |                                   |
|          |  LAYER    |                                   |
|          | Merges    |                                   |
|          | batch +   |                                   |
|          | speed     |                                   |
|          | results   |                                   |
|          +-----+-----+                                   |
|                |                                         |
|                v                                         |
|           User Query                                     |
+----------------------------------------------------------+
```

Here is what a real query looks like in this system. A user opens Netflix at 9:47 PM. The recommendation service calls the serving layer. The serving layer fetches: (1) the batch view computed at 6 AM, which has five years of watch history, and (2) the speed view from the Flink job, which has the last 15 hours of events — including the thriller the user just watched. The serving layer merges them: take the long-term preferences from the batch view, then overlay the recency signal from the speed view. The user sees a recommendation list that is both historically informed and immediately current.

---

### The Cost of Lambda

Lambda solves the accuracy-vs-speed problem, but it introduces three serious costs. At the L6 level, you must be able to name these costs before an interviewer asks about them, because every architecture choice has tradeoffs and your job is to demonstrate that you understand what you are giving up.

**Cost 1: Two codebases doing the same thing.** Every piece of business logic — every aggregation formula, every filter rule, every join condition — must be implemented TWICE. Once in Spark (batch) and once in Flink (stream). When a product manager says "change the revenue calculation to exclude refunds issued within 24 hours," an engineer must update the Spark job and the Flink job. Any bug in the logic must be found and fixed in both places. Teams that are not disciplined about keeping the two codebases synchronized end up with the batch layer and speed layer computing different numbers for the same time window. Now you have a correctness problem on top of your complexity problem.

**Cost 2: Two infrastructure stacks.** You need a Spark cluster AND a Flink cluster AND a serving layer with its own data store (often Cassandra, Druid, or Redis). Each cluster has its own operations burden: capacity planning, upgrades, on-call rotations, monitoring dashboards. This is roughly two and a half times the infrastructure cost and operational complexity of a single-system solution.

**Cost 3: Merge inconsistency at query time.** The serving layer's job sounds simple — add the batch answer and the speed answer together — but in practice it is subtle. The batch layer and speed layer often have different semantics for the same window. The batch layer might use event time (when the event actually happened); the speed layer might use processing time (when the system processed it). Late-arriving data is handled differently. Deduplication logic might differ. The result: for the same five-hour window, the batch view and speed view can produce different row counts, different totals, different user counts. Which one is correct? There is no clean answer. You built two systems and now you have to decide which one to trust.

---

### When Lambda Is Justified

Lambda is not wrong. It is correct for specific situations. At L6 you need to know when the tradeoffs are worth paying.

Lambda is the right choice when: (1) you genuinely need both accurate historical aggregates AND real-time current state, (2) the two requirements have different consumers that tolerate different latencies, and (3) your team is large enough to maintain two separate pipelines without degrading either.

**Real example: Uber surge pricing.** Uber needs to compute a surge multiplier for every geographic cell in every city in real-time. That multiplier has two inputs. First: a baseline model trained on historical trip patterns — what is normal supply/demand for this neighborhood at this time of day on this day of the week? This model is built by a nightly batch job that processes months of historical trip data using Spark. It is accurate because it sees everything. It changes slowly; retraining once per day is fine. Second: the real-time supply/demand ratio right now — how many drivers are available in this cell versus how many riders have requested in the last 60 seconds? This comes from a Flink streaming job processing live GPS pings and ride requests. It changes every few seconds. The surge multiplier combines both signals. You cannot get both from a single system. Lambda is the right choice here.

**Second real example: LinkedIn's "People You May Know."** LinkedIn's friend recommendation feature uses Lambda to serve two signals simultaneously. The batch layer runs a graph algorithm (approximate personalized PageRank) over the full LinkedIn social graph — hundreds of millions of nodes and billions of edges — every 24 hours. This produces a stable, high-quality "who you should know based on your full network" ranking. The speed layer tracks events from the past few hours: did you just connect with someone? Did you just search for a name? Did you visit a profile? These recency signals are injected by the Flink streaming job and boost certain candidates in the recommendation list immediately. Without the batch layer, new users with sparse connections get poor recommendations. Without the speed layer, a user who just attended a conference and connected with 20 people sees no change in their recommendations until the next day's batch run. Lambda handles both.

The key signal that Lambda is the right choice: your analytics or product requirements include the phrase "historically informed AND immediately responsive." If a business stakeholder says "show me the all-time best sellers AND update it when a new sale happens in the last 60 seconds" — that is Lambda territory. If they say "show me what sold in the last 24 hours, updated hourly" — that is just a batch job.

---

## 2. Kappa Architecture: Stream Only

### The Insight Behind Kappa

In 2014, Jay Kreps — one of the creators of Kafka, working at LinkedIn at the time — wrote a blog post with a pointed question: "Why are we maintaining two completely separate systems when the stream processor can do everything the batch processor does, if we just replay all the historical data through it?"

The analogy Kreps used was a video recording. Imagine you recorded a live game. A "batch processor" would be someone who sits down the next morning and watches the entire recording from the beginning to compile statistics. A "stream processor" would be someone who tracks statistics in real-time as the game happens. Kreps asked: why not just use the same person doing the live tracking, but hand them the recording to re-watch when you need to recompute? Same person, same process, same code — just different input data (recording vs live feed).

This is the **Kappa architecture**. Instead of running a batch layer AND a speed layer, you run only a streaming layer. For real-time processing: the stream processor consumes live events from Kafka. For historical reprocessing (the thing that used to require the batch layer): you replay the Kafka topic from offset 0 — from the very beginning — through the same streaming job. One codebase. One cluster. One system.

```
+----------------------------------------------------------+
|                  KAPPA ARCHITECTURE                      |
+----------------------------------------------------------+
|                                                          |
|   Raw Events (Kafka - long retention or tiered storage)  |
|         |                                                |
|         |   +---- Replay from offset 0 for              |
|         |   |     historical reprocessing               |
|         |   |                                            |
|         v   v                                            |
|   +----------+                                           |
|   |  STREAM  |                                           |
|   |  LAYER   |    <- ONE codebase handles both           |
|   | (Flink / |       real-time AND reprocessing          |
|   |  Kafka   |                                           |
|   |  Streams)|                                           |
|   +----+-----+                                           |
|        |                                                 |
|        v                                                 |
|   +----------+                                           |
|   | Serving  |                                           |
|   | Layer    |                                           |
|   | (One     |                                           |
|   |  output) |                                           |
|   +----+-----+                                           |
|        |                                                 |
|        v                                                 |
|   User Query                                             |
+----------------------------------------------------------+
```

The reprocessing workflow looks like this. You have a bug in your revenue calculation and need to fix it for the last 90 days. In Lambda: you fix both the Spark job and the Flink job, then rerun the Spark batch job over 90 days of data. In Kappa: you deploy the fixed Flink job as a new version (version 2), then start it from the Kafka offset corresponding to 90 days ago. It processes 90 days of events at high speed (consuming from Kafka is much faster than real-time, since there is no waiting — all events are already there). When version 2 catches up to the live tail, you switch the serving layer to read from version 2's output and shut down version 1. Done. One codebase, one cluster, one fix.

The zero-downtime version switchover looks like this in practice:

```
+----------------------------------------------------------+
|         KAPPA REPROCESSING: ZERO-DOWNTIME CUTOVER        |
+----------------------------------------------------------+
|                                                          |
| Phase 1: Both versions running                           |
|                                                          |
|  Kafka topic (90 days of events)                         |
|    |                                                     |
|    +----------+----------+                               |
|    |                     |                               |
|    v                     v                               |
|  [Flink v1]           [Flink v2]                        |
|  (buggy code,         (fixed code,                      |
|   consuming           consuming from                     |
|   live tail)          90-day offset)                     |
|    |                     |                               |
|    v                     v                               |
| output_v1             output_v2                          |
|    ^                     |                               |
|    |                     | (catching up...)              |
| [Serving layer reads v1] |                               |
|                                                          |
| Phase 2: v2 catches up to live tail                      |
|                                                          |
|  [Serving layer switches -> reads output_v2]             |
|  [Flink v1 shut down]                                    |
|  [output_v1 archived or deleted]                         |
+----------------------------------------------------------+
```

During Phase 1, users continue to get answers from v1 (slightly wrong, but available). During Phase 2, the cutover is atomic from the serving layer's perspective — one config change flips it from v1 to v2. No downtime. No users see a missing answer. The only requirement is that Kafka has retained the last 90 days of events and that Flink v2 can process them faster than real-time (which it will, because the cluster is not rate-limited by real-world event arrival speed when processing historical data).

---

### When Kappa Works

Kappa works beautifully when three conditions hold:

**Kafka retention is long enough.** If you need to reprocess 90 days of data, Kafka needs to have retained 90 days of events. Modern Kafka with tiered storage (Confluent Tiered Storage, or Apache Kafka's own tiered storage feature released in 3.6) can retain data cheaply in S3 for years. Without tiered storage, typical Kafka retention is 7-30 days, which limits your reprocessing window.

**Your processing logic is expressible as a stream operation.** Flink and Kafka Streams can do windowed aggregations, joins, deduplication, and stateful computations. Most analytics workloads fit. The question is whether your business logic requires something that streaming semantics cannot express naturally.

**Your state volume is manageable.** Flink stores state in RocksDB on executor machines. If you need to maintain state for billions of unique user IDs over five years, that state might not fit in your Flink cluster's RocksDB storage without significant infrastructure overhead.

---

### When Kappa Does Not Work

**Historical data exceeds Kafka retention.** If your company has been collecting data for eight years and Kafka only has 30 days of retention (and no tiered storage), you cannot replay eight years of data through Kappa. You need a batch job to handle the historical backfill — which means you are running Lambda in practice, even if you call it Kappa.

**Complex batch-only operations.** Some computations genuinely require the full dataset before they can produce any output — for example, training an ML model on billions of rows, or computing a global percentile ranking where you must sort the entire dataset. These are multi-pass algorithms. A streaming system processes records one at a time in order; it cannot sort the whole dataset first. For these, you need a true batch system like Spark.

**In practice**, most companies end up with Kappa + an occasional batch job for historical backfill. They call it Kappa because the day-to-day pipeline is a single streaming system, but they have a Spark job sitting in a corner for the once-a-year "we need to reprocess all of 2019" situation.

---

### Lambda vs Kappa Decision Table

| Dimension | Lambda | Kappa |
|---|---|---|
| Codebases | Two (Spark + Flink) | One (Flink only) |
| Ops burden | High (two clusters) | Medium (one cluster) |
| Reprocessing | Run batch job over all history | Replay Kafka from offset 0 |
| Historical data limit | Can use S3/HDFS; no limit | Limited by Kafka retention |
| Complex batch ops | Supported natively in Spark | Difficult or impossible in Flink |
| Team size needed | Larger (maintain two systems) | Smaller (maintain one system) |
| Result consistency | Risk of batch/stream divergence | Single system = consistent results |
| Choose when | You need both accurate history AND real-time, have large team | You want simplicity, Kafka retention is sufficient, logic is streamable |

---

## 3. Data Quality: Trust But Verify

### Why Data Quality Is a Staff-Level Concern

Most interns and junior engineers treat data quality as someone else's problem. "The data team checks the data." This attitude is one of the most expensive beliefs in software engineering.

Here is a concrete example of what bad data costs. A startup's engineering team built a data pipeline that aggregated daily revenue. A bug in the pipeline caused every row to be inserted twice — the pipeline was not idempotent, and a restart after a failure duplicated all records. The finance team received a revenue report showing twice the actual revenue. They spent three days making hiring decisions, budget allocations, and investor communication decisions based on that number. When the bug was found, the company had to unwind those decisions, issue corrections, and investigate why their controls had not caught the error.

At Netflix, a ML training pipeline processed incorrectly labeled data because an upstream join produced wrong training labels for about 15% of the dataset. The model trained on this corrupted dataset was deployed to production and affected recommendation quality for two weeks before the error was traced back to the pipeline. The fix required retraining the model, re-deploying, and a post-mortem investigation across three teams.

The L6 principle is: **data quality is an engineering responsibility, not a data team responsibility.** Every pipeline you build must validate its own output. If you write code that produces data, you own the quality of that data.

---

### The Four Layers of Data Quality Validation

Think of data quality like airport security. Every checkpoint catches a different type of problem. You do not rely on one checkpoint to catch everything — you layer them so each one compensates for what the others miss.

#### Layer 1: Schema Validation (at Ingestion)

This is the first checkpoint — the moment data enters your system. You verify that the structure of the incoming data matches what you expect.

Questions schema validation answers: Are all required columns present? Is `user_id` an integer or did someone change it to a string? Did the upstream team add a new column you did not know about (called **schema drift**)? Is the JSON properly formed?

```
+----------------------------------------------------------+
|  RAW DATA IN -> [SCHEMA VALIDATOR] -> PASS or QUARANTINE |
|                                                          |
|  Checks:                                                 |
|    + All expected columns present?                       |
|    + Column types match contract?                        |
|    + No unexpected new columns?                          |
|    + JSON/Avro/Protobuf parses correctly?                |
+----------------------------------------------------------+
```

Tools: **Great Expectations** (Python library with hundreds of built-in validation rules), **dbt schema tests** (define expected types and constraints in YAML, run automatically after every transform), **Avro/Protobuf schema enforcement** (compile-time schema checking for event streams).

Here is what a dbt schema test file looks like in practice:

```yaml
# models/schema.yml
models:
  - name: orders
    columns:
      - name: order_id
        tests:
          - not_null
          - unique
      - name: user_id
        tests:
          - not_null
          - relationships:
              to: ref('users')
              field: user_id
      - name: amount
        tests:
          - not_null
          - dbt_utils.accepted_range:
              min_value: 0
              max_value: 1000000
```

When `dbt test` runs, it executes each of these as a SQL query against the output table. If any test fails, dbt marks the model as failed and does not allow downstream models to use it. You get a broken build before any bad data reaches a dashboard.

#### Layer 2: Value Validation (at Transform)

Schema validation tells you the structure is correct. Value validation tells you the actual values make sense for your business.

- **Null checks:** `user_id IS NOT NULL` — if user_id is null, this row is useless for any join and likely represents a bug upstream.
- **Range checks:** `amount > 0 AND amount < 1000000` — if a payment amount is negative or larger than one million dollars, it probably represents a processing error, not a real transaction.
- **Referential integrity:** Every `order.user_id` must exist in the `users` table. Orphaned orders represent data corruption.
- **Uniqueness:** No duplicate primary keys in the output table. Duplicates silently inflate every count and sum that touches that table.

In Spark, value validation runs as a transform step before writing output:

```python
from pyspark.sql import functions as F

def validate_orders(df):
    # Null check
    null_count = df.filter(F.col("user_id").isNull()).count()
    if null_count > 0:
        raise ValueError(f"Found {null_count} rows with null user_id")
    
    # Range check
    bad_amounts = df.filter(
        (F.col("amount") <= 0) | (F.col("amount") > 1000000)
    ).count()
    if bad_amounts > 0:
        quarantine_df = df.filter(
            (F.col("amount") <= 0) | (F.col("amount") > 1000000)
        )
        quarantine_df.write.mode("append").parquet("s3://quarantine/orders/")
        df = df.filter(
            (F.col("amount") > 0) & (F.col("amount") <= 1000000)
        )
    
    return df
```

Notice: instead of failing the job on bad amount values, the code routes bad records to quarantine and continues with the valid ones. This is the quarantine pattern applied at the transform stage.

#### Layer 3: Statistical Validation (at Load)

Individual row validation catches bad records. Statistical validation catches bad batches — situations where individual records look fine but the aggregate is wrong.

- **Row count check:** If yesterday's job produced 1,000,000 rows and today's job produced 50,000, something is wrong. A 95% drop in volume is not a business event; it is a pipeline failure. Set a threshold: alert if today's row count is outside ±30% of the 7-day rolling average.
- **Distribution checks:** If the NULL rate for `email` column jumps from 0.1% to 30% overnight, upstream changed something. A sudden distribution shift is a signal, even if every individual row passes its own checks.
- **Freshness check:** The data should have arrived by 6 AM. If at 7 AM the most recent record in the table has a timestamp of 9 PM yesterday, the pipeline did not run — or ran but failed to write output.

#### Layer 4: Cross-Pipeline Validation (Post-Load)

The final layer catches inconsistencies that exist across multiple pipelines or tables.

- **Sum of parts equals whole:** If your pipeline produces regional revenue tables (US, EU, APAC), the sum of regional totals must equal the global total. If it does not: one region is duplicating data, or one is missing data.
- **Source-to-target reconciliation:** Count rows in the source database: `SELECT COUNT(*) FROM payments WHERE date = '2024-01-15'`. Count rows in the warehouse: `SELECT COUNT(*) FROM dw.payments WHERE date = '2024-01-15'`. They should match. If they differ by more than a rounding error, records were dropped or duplicated in transit.
- **Cross-pipeline consistency:** If you have both an `orders` pipeline and a `payments` pipeline, `orders.total_revenue` and `payments.total_collected` should agree on the total for the same time period. Divergence means one pipeline has a bug.

---

### Data Contracts: The Organizational Solution

Technical validation catches bugs. **Data contracts** prevent bugs from happening in the first place by making the expectations explicit before any code is written.

A data contract is a formal agreement between the team that PRODUCES a dataset and every team that CONSUMES it. It is a document (ideally machine-readable) that specifies:

- **Schema:** exact column names, types, and nullability
- **SLA:** data will be available by 6:00 AM UTC every day
- **Volume expectations:** 500,000 to 2,000,000 rows per day. Alert if outside this range.
- **Quality rules:** `order_id` is never null, `amount` is always positive, `user_id` always exists in the users table
- **Breaking change policy:** the producing team will give 30 days notice before removing or renaming any column

Without contracts, this happens constantly: the team that owns the `events` table renames `user_id` to `uid` because it is cleaner. They update their own code. They do not realize that eleven downstream pipelines consume this table. All eleven pipelines break simultaneously at midnight when the rename deploys to production. Five teams are paged at 2 AM.

With a data contract, that rename requires a 30-day notice, a migration period where both `user_id` and `uid` exist, and a coordinated cutover. Still annoying, but not a 2 AM incident.

Tools: **OpenDataContract** (open standard for contract format), **dbt contracts** (enforces schema contracts as part of dbt build), **AsyncAPI** for documenting event stream schemas in Kafka topics.

What a data contract looks like in practice (simplified YAML format):

```yaml
# data-contract-orders.yaml
dataContractSpecification: 0.9.0
id: orders-daily
info:
  title: Orders Daily Aggregate
  owner: data-platform-team
  contact: data-platform@company.com

servers:
  production:
    type: bigquery
    project: analytics-prod
    dataset: core
    table: orders_daily

terms:
  noticePeriod: P30D    # 30 days notice before breaking changes
  availableBy: "06:00 UTC"

models:
  orders_daily:
    fields:
      order_id:
        type: string
        required: true
        unique: true
      user_id:
        type: string
        required: true
      amount:
        type: number
        minimum: 0
        maximum: 1000000
      date:
        type: date
        required: true

quality:
  volumeExpectations:
    minRows: 500000
    maxRows: 2000000
  freshnessExpectations:
    availableBy: "06:00"
    timezone: UTC
```

When a producing team wants to rename `user_id` to `uid`, they must update this contract file, submit a pull request, and notify all subscribed consumer teams. Consumers have 30 days to migrate before the old column disappears. The contract file is the source of truth, and tools like `soda` or `great_expectations` can read it to automatically generate and run validation checks.

---

### Quarantine Pattern: Do Not Fail the Whole Pipeline for 0.01% Bad Records

Here is a decision that trips up junior engineers: your pipeline is processing one million records and encounters ten malformed records. What do you do?

**Option A: Fail the entire job.** Safe from a correctness standpoint — you do not load any data until all data is valid. But now 999,990 perfectly good records are also blocked. Your SLA is missed. Downstream teams have no data. All because of ten bad records that represent 0.001% of the volume.

**Option B: Skip bad records silently.** The job completes. But you have no visibility into what was dropped. The quarantine rate could be 50% and you would never know.

The right answer is the **quarantine pattern**, which is Option C: route bad records to a separate dead-letter destination (a dedicated S3 path or database table), continue processing all good records normally, and trigger an alert if the quarantine rate exceeds a threshold.

```
+----------------------------------------------------------+
|                  QUARANTINE PATTERN                      |
+----------------------------------------------------------+
|                                                          |
|   Incoming Records                                       |
|         |                                                |
|         v                                                |
|   [VALIDATOR]                                            |
|         |                                                |
|    +----+----+                                           |
|    |         |                                           |
|    v         v                                           |
| VALID      INVALID                                       |
| Records    Records                                       |
|    |           |                                         |
|    v           v                                         |
| [Output    [Dead Letter     [Alert if                    |
|  Table]     Table /         quarantine                   |
|             S3 Path]        rate > 1%]                   |
|                                                          |
|  Good data flows.    Bad data isolated.    Team notified.|
+----------------------------------------------------------+
```

This gives you: (1) 99.99% of good data still flows on time, (2) bad data is preserved for investigation rather than silently dropped, (3) an alert fires if the quarantine rate is high enough to indicate a real upstream problem. When the quarantine rate for a normal pipeline spikes from 0.01% to 15%, that is a signal that something significant changed upstream — a bad deploy, a schema change, a data source problem. You find out immediately rather than at the end of your next audit.

---

## 4. Batch Job Monitoring and Debugging

### The 6 Metrics That Matter

When a batch job is running in production, these are the six numbers you watch. Any one of them going outside its expected range is a signal worth investigating.

**1. Job duration.** How long did the job take to complete? Track a rolling 7-day average and alert if today's run exceeds 2× that average. Gradually increasing duration over weeks usually means your data volume is growing and you need to scale the cluster. Sudden doubling usually means a regression: a new join that causes a shuffle, a schema change that turned a partition prune into a full scan, or data skew in a new key.

**2. Data freshness.** When was the last SUCCESSFUL completion of this job? "The job is running" is different from "the job completed successfully and loaded data." Track the timestamp of the most recent successful load. Alert if it is stale beyond your SLA window.

**3. Row counts.** How many rows were written to the output table? Compare against the 7-day rolling average for the same day of week (Tuesday traffic differs from Sunday traffic). Alert if outside ±30% of that baseline.

**4. Error and quarantine rate.** Bad records / total records as a percentage. A healthy pipeline is below 0.1%. Alert at 1%. Page on-call at 5%. If this metric is 40%, stop and investigate before loading anything.

**5. Resource utilization.** Executor CPU and memory. If executors are using 10% CPU but the job is slow, the job is I/O bound (reading from S3 slowly) or serialization bound, not compute bound. Adding more CPU does not help. If executors are spilling memory to disk (visible in the Spark UI as "spill" bytes), add memory or reduce partition size.

**6. Stage duration breakdown.** Which Spark stage takes the longest? Usually it is the shuffle stage after a groupBy or join. Knowing which stage is the bottleneck tells you where to focus optimization effort.

Here is a practical SQL query that a monitoring system can run after every pipeline completion to check all six metrics at once against the `pipeline_run_log` tracking table:

```sql
-- Pipeline health check query — run after each pipeline completion
WITH recent_runs AS (
  SELECT
    pipeline_name,
    run_date,
    duration_minutes,
    rows_written,
    quarantine_rows,
    completed_at,
    status
  FROM pipeline_run_log
  WHERE pipeline_name = 'orders_daily'
    AND run_date >= CURRENT_DATE - INTERVAL '8 days'
),
baseline AS (
  SELECT
    DAYOFWEEK(run_date)              AS day_of_week,
    AVG(duration_minutes)            AS avg_duration,
    AVG(rows_written)                AS avg_rows,
    AVG(quarantine_rows * 1.0 / rows_written) AS avg_quarantine_rate
  FROM recent_runs
  WHERE run_date < CURRENT_DATE   -- exclude today from baseline
  GROUP BY DAYOFWEEK(run_date)
),
today AS (
  SELECT * FROM recent_runs WHERE run_date = CURRENT_DATE
)
SELECT
  today.pipeline_name,
  today.run_date,
  -- Metric 1: Duration
  today.duration_minutes,
  baseline.avg_duration,
  CASE WHEN today.duration_minutes > baseline.avg_duration * 2
       THEN 'ALERT: duration > 2x average' ELSE 'OK' END AS duration_check,
  -- Metric 3: Row counts
  today.rows_written,
  baseline.avg_rows,
  CASE WHEN today.rows_written < baseline.avg_rows * 0.7
        OR today.rows_written > baseline.avg_rows * 1.3
       THEN 'ALERT: row count outside 30% of baseline' ELSE 'OK' END AS rowcount_check,
  -- Metric 4: Quarantine rate
  today.quarantine_rows * 1.0 / today.rows_written AS quarantine_rate,
  CASE WHEN today.quarantine_rows * 1.0 / today.rows_written > 0.01
       THEN 'ALERT: quarantine rate > 1%' ELSE 'OK' END AS quarantine_check,
  -- Metric 2: Freshness
  today.completed_at,
  CASE WHEN today.completed_at > CURRENT_DATE + INTERVAL '6 hours'
       THEN 'ALERT: completed after SLA window' ELSE 'OK' END AS freshness_check
FROM today
JOIN baseline ON DAYOFWEEK(today.run_date) = baseline.day_of_week;
```

This query is the kind of thing you put in a scheduled check that runs 15 minutes after each pipeline is expected to complete. If any `_check` column returns 'ALERT', the monitoring system pages on-call. The SQL computes all checks relative to the same day-of-week baseline — important because Monday traffic at a consumer app is genuinely different from Saturday traffic, and alerting against a flat average would produce noise.

---

### Debugging a Slow Spark Job: Step-by-Step

You get paged at 6 AM. The daily pipeline is supposed to finish by 5 AM. The Spark job is still running. Here is how you diagnose it methodically.

```
+----------------------------------------------------------+
|           SPARK JOB DEBUGGING DECISION TREE              |
+----------------------------------------------------------+
|                                                          |
|   JOB IS SLOW OR STUCK                                   |
|         |                                                |
|         v                                                |
|   Open Spark UI -> Stages tab                            |
|         |                                                |
|         v                                                |
|   Which stage is slow?                                   |
|         |                                                |
|    +----+----+                                           |
|    |         |                                           |
|    v         v                                           |
| ONE STAGE  ALL STAGES                                    |
| IS SLOW    ARE SLOW                                      |
|    |           |                                         |
|    v           v                                         |
| Check task  -> Data volume grew?                         |
| distribution   -> Small files?                           |
|    |           -> GC pauses?                             |
|    |           -> Under-provisioned cluster?             |
|    |                                                     |
| +--+--+                                                  |
| |     |                                                  |
| v     v                                                  |
|ONE   ALL TASKS                                           |
|TASK  SIMILAR                                             |
|SLOW  DURATION                                            |
| |       |                                                |
| v       v                                                |
|DATA   SHUFFLE   JOB OOM?                                 |
|SKEW   SIZE OR     |                                      |
|       RESOURCE  +--+--+                                  |
| |     BOTTLENECK |     |                                 |
| v               v     v                                  |
|SALT           DRIVER  EXECUTOR                           |
|THE KEY        OOM     OOM                                |
|               (don't  (skew or                           |
|               use     increase                           |
|               collect)|memory)                           |
+----------------------------------------------------------+
```

**Step 1: Open the Spark UI and go to the Stages tab.** This tab shows every stage of your job and its duration. A stage corresponds to one set of tasks that can run in parallel without shuffling data. Look for the stage with the longest wall-clock duration — that is your bottleneck.

**Step 2: Click into the bottleneck stage and look at the task duration distribution.** The Spark UI shows a histogram of task durations for that stage.

- If all tasks have similar durations (say, 20-25 minutes each): the problem is not skew. Every task is just slow. Look at shuffle read/write size, executor CPU, and whether tasks are spilling to disk.
- If one task has a duration that is 10× or 100× longer than all the others: you have **data skew**. One partition contains a disproportionate fraction of the data. One executor gets stuck processing it while all others finish and sit idle.

**Step 3: If you have data skew, find the skewed key.**

```sql
-- Find which key value dominates the data
SELECT group_key, COUNT(*) as record_count
FROM your_table
GROUP BY group_key
ORDER BY record_count DESC
LIMIT 20;
```

If the top key has 35% of all rows and the next has 0.5%, that is your skewed key. Apply salted aggregation: append a random suffix (0-9) to the key before the first groupBy, aggregate at the salted level, then aggregate again after removing the salt. This distributes the 35% across 10 partitions instead of one.

**Step 4: Check shuffle size.** Large shuffles are expensive. If your groupBy or join is shuffling 500 GB of data, consider:
- Pre-aggregate before the shuffle: if you are doing `SELECT user_id, SUM(amount) FROM events GROUP BY user_id`, and events is huge, push a partial sum down before the shuffle.
- Broadcast small tables: if you are joining a 10 TB fact table against a 50 MB dimension table, broadcast the dimension table. No shuffle needed. `spark.conf.set("spark.sql.autoBroadcastJoinThreshold", "100m")`.

**Step 5: Check for memory spills.** In the Spark UI, look for "Spill (Memory)" and "Spill (Disk)" in the stage metrics. Any spill means executors are running out of memory and writing intermediate data to disk, which is 10-100× slower. Fixes: increase executor memory (`spark.executor.memory=8g`), increase the number of partitions so each partition is smaller (`spark.sql.shuffle.partitions=400`), or apply salted aggregation to reduce per-partition data volume.

**Step 6: Check for GC pauses.** In the Spark UI, each executor has a "GC Time" column. If GC time is more than 10% of task duration, the JVM is spending significant time garbage collecting. This usually means heap size is too small relative to the data being processed, or too many small objects are being created. Fix: increase `spark.executor.memory`, switch to Kryo serialization (`spark.serializer=org.apache.spark.serializer.KryoSerializer`), or reduce partition size so each task handles less data.

A solid Spark configuration for a production batch job on moderate data volumes:

```bash
spark-submit \
  --conf spark.executor.memory=8g \
  --conf spark.executor.cores=4 \
  --conf spark.driver.memory=4g \
  --conf spark.sql.shuffle.partitions=400 \
  --conf spark.sql.adaptive.enabled=true \
  --conf spark.sql.adaptive.coalescePartitions.enabled=true \
  --conf spark.sql.adaptive.skewJoin.enabled=true \
  --conf spark.serializer=org.apache.spark.serializer.KryoSerializer \
  --conf spark.checkpoint.dir=s3://your-bucket/spark-checkpoints/ \
  your_job.py
```

The three `spark.sql.adaptive.*` flags are Spark 3.0+ Adaptive Query Execution (AQE). They let Spark automatically adjust shuffle partition count at runtime based on actual data sizes — if a shuffle stage produces only 2 GB of data but `shuffle.partitions` is set to 400, AQE coalesces those 400 partitions down to ~16, eliminating the overhead of launching 384 nearly-empty tasks. AQE also automatically detects skewed join partitions and splits them without any manual salting. For any job on Spark 3.x, enabling these flags costs nothing and commonly delivers 20-40% speedup on real-world workloads.

---

## 5. Cost Optimization for Batch

### The Biggest Cost Levers

Batch jobs can be expensive. A Spark cluster running for eight hours a day on 50 large EC2 instances costs real money. At scale, data infrastructure costs can easily reach hundreds of thousands of dollars per month. L6 engineers are expected to understand these costs and know how to reduce them without sacrificing reliability or correctness.

#### Compute: Spot and Preemptible Instances

**EC2 Spot instances** (AWS) and **preemptible VMs** (GCP) are spare compute capacity that the cloud provider sells at 60-80% discount compared to on-demand pricing. The catch: the cloud provider can reclaim them at any time with a 2-minute warning when they need the capacity back.

For always-on services (your API server, your database), spot instances are too risky. An interruption kills the instance and your service goes down.

For batch jobs, spot instances are often the right answer. The key mitigation is **Spark checkpointing**: Spark periodically writes its current computation state (shuffle data, RDD lineage checkpoints) to durable storage (S3 or HDFS). If a spot instance is interrupted, Spark does not restart the entire job — it restarts from the last checkpoint, losing only the work done since the last checkpoint. For a job with checkpoints every 15 minutes, an interruption costs you at most 15 minutes of re-work.

Rule of thumb: enable checkpointing for any batch job that runs longer than 30 minutes on spot instances. Accept the 5-10 minute restart overhead in exchange for 65-75% cost reduction.

Real impact: Airbnb reported migrating their batch compute fleet from 100% on-demand instances to 90% spot instances, cutting their monthly batch compute bill from approximately $800,000 to approximately $150,000. Same jobs, same output, 81% cheaper.

#### Storage: Columnar Format and Compression

Storage is not free, and the format you choose has a massive impact on both storage cost and query performance.

**CSV to Parquet**: Parquet is a columnar storage format. CSV is row-based. When you have a table with 100 columns and a query that only touches 3 of them, a row-based format (CSV) must read all 100 columns for every row. A columnar format (Parquet) reads only the 3 columns you actually need. Uber reported an 85% storage reduction when migrating analytical tables from CSV to Parquet. Query speed improved by approximately 90% for typical analytical queries.

**Compression**: Parquet supports multiple compression codecs. Snappy is the default — fast compression and decompression, moderate compression ratio. Zstd (Zstandard) achieves 40-60% better compression ratio than Snappy with acceptable decompression speed. For cold data that is read infrequently, Zstd is often worth the tradeoff.

**S3 lifecycle policies**: Data that was critical last month may be rarely accessed six months from now. S3 Intelligent-Tiering automatically moves objects between storage tiers based on access patterns. Objects not accessed for 30 days move to a cheaper tier. Objects not accessed for 90 days move to an even cheaper archival tier. Facebook reported a 70% reduction in storage costs for analytical data by implementing 30-day transitions from hot to cold storage for event log data.

#### Query: Pay-Per-Query vs Always-On Cluster

There are two cost models for running analytical queries.

**Serverless SQL** (BigQuery on GCP, Athena on AWS): you pay per byte scanned, not per hour of cluster time. No cluster to provision, manage, or keep running. BigQuery charges approximately $5 per terabyte scanned. An ad-hoc query that scans 1 TB costs $5. If your analysts run 20 queries per day, each scanning 500 GB on average, that is 10 TB per day × $5 = $50 per day = $1,500 per month.

**Self-managed Spark cluster**: fixed cost per hour regardless of query volume. Ten large instances at $0.50/hour each = $5/hour = $120/day = $3,600/month. If you run more than 24 TB of queries per day on BigQuery, you pay more than $120 (24 TB × $5 = $120). Below 24 TB/day, BigQuery is cheaper. Above 24 TB/day, self-managed Spark is cheaper.

| Cost Strategy | What It Does | Real Savings |
|---|---|---|
| Spot/preemptible instances | Run batch jobs on 60-80% cheaper interruptible compute | Airbnb: $800K -> $150K/month |
| Ephemeral clusters | Spin up cluster for job, terminate after | Eliminate idle cluster cost (hours of waste/day) |
| CSV -> Parquet | Columnar format, read only needed columns | Uber: 85% storage reduction, 90% faster queries |
| Snappy -> Zstd compression | Better compression ratio | 40-60% additional storage reduction |
| S3 lifecycle policies | Move cold data to cheaper tiers automatically | Facebook: 70% storage cost reduction |
| Partition pruning | Ensure queries use partition columns in WHERE | 10-100× less data scanned per query |
| Serverless SQL (BigQuery/Athena) | Pay per query, not per cluster-hour | Wins when < 24 TB scanned/day |
| Broadcast joins | Avoid large shuffles for small dimension tables | Eliminate entire shuffle stage in Spark jobs |

---

## 6. Production Incidents

### Incident 1: Facebook's Data Skew — 8-Hour Daily Report (2017)

**What happened:**

Facebook runs a daily job that aggregates advertising revenue by advertiser. The query is conceptually simple: `SELECT advertiser_id, SUM(impressions), SUM(revenue) FROM daily_impressions GROUP BY advertiser_id`. When Spark executes this groupBy, it partitions the data by `advertiser_id`. Every row with the same advertiser_id goes to the same partition — and thus the same Spark task.

Procter and Gamble at the time represented approximately 35% of Facebook's global ad impression volume. This means 35% of all data went to one Spark partition, processed by one task running on one executor. The other tasks finished in about 20 minutes. The P&G task took 6 hours. Because Spark stages cannot complete until every task in the stage finishes, the entire job was blocked for 6 hours waiting for that one task.

**Impact:** The daily advertising revenue report — which is used in earnings call preparation and financial reconciliation — was delayed by 4 hours. Finance teams had to postpone meetings. The incident escalated to engineering leadership.

**Root cause:** No skew detection or monitoring. Default Spark hash partitioning distributed data perfectly by hash value, which meant a single high-volume advertiser dominated a single partition.

**Fix:**

First, the team identified the top 50 advertisers by impression count. For any advertiser representing more than 5% of total daily volume, the job applies two-pass salted aggregation: append a random integer suffix 0-9 to the advertiser_id, perform the first groupBy at the salted level to get 10× more parallelism, then aggregate again after removing the salt. The P&G data now spreads across 10 partitions instead of one.

Second, after upgrading to Spark 3.0, the team enabled **Adaptive Query Execution (AQE)**: `spark.sql.adaptive.enabled=true`. AQE detects skew at runtime and automatically splits skewed partitions without any manual salting code.

Result: job time dropped from 8 hours to 45 minutes.

**Prevention:** An automated skew detection step runs in CI before every pipeline deployment:

```sql
SELECT advertiser_id, COUNT(*) as cnt,
       COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () as pct_of_total
FROM daily_impressions_sample
GROUP BY advertiser_id
ORDER BY cnt DESC
LIMIT 10;
```

If any single advertiser exceeds 10% of total volume, the pipeline is automatically routed through the salted aggregation code path instead of the simple groupBy.

---

### Incident 2: Netflix's Non-Idempotent Pipeline Doubles Revenue (2019)

**What happened:**

Netflix has a pipeline that calculates "content cost per stream" daily. This figure is used by the content licensing team to negotiate content deals. The pipeline reads from several source systems, performs complex joins and calculations, and writes results to a data warehouse table.

On the day of the incident, the pipeline failed midway through writing its output to the warehouse. The on-call engineer identified the failure, determined it was a transient network error, and restarted the job. The restarted job successfully wrote its output.

The problem: the pipeline used `INSERT INTO` (append semantics), not `INSERT OVERWRITE` (replace semantics). The partial write from the first failed run was already in the table. The second successful run appended a complete set of results on top. The output table now had 2× the correct number of rows — a complete set from the failed partial run plus a complete set from the successful run.

The content licensing team, unaware of the issue, used this data for three days. Contracts were negotiated based on a cost model showing twice the actual per-stream cost. Several content deals were structured based on inaccurate financial projections.

**Impact:** Approximately $5 million in content deals were mispriced based on the doubled data. The error was discovered during a routine audit three days later. Correction required renegotiation, internal write-offs, and a full post-mortem.

**Root cause:** `INSERT INTO` (non-idempotent) instead of `INSERT OVERWRITE` (idempotent). No post-run validation of row counts.

**Fix:**

All pipeline outputs were migrated to date-partitioned `INSERT OVERWRITE`:

```sql
INSERT OVERWRITE TABLE content_cost_per_stream
PARTITION (date = '{{ execution_date }}')
SELECT ...
FROM source_data
WHERE date = '{{ execution_date }}';
```

With `INSERT OVERWRITE`, running the job twice on the same date produces the same result — the second run replaces the first. Idempotency is guaranteed.

A post-run validation step was added that runs automatically after every successful pipeline completion:

```sql
SELECT COUNT(*) as row_count
FROM content_cost_per_stream
WHERE date = '{{ execution_date }}';
-- Compare against historical average for this day of week
-- Alert if outside [avg * 0.7, avg * 1.3]
```

If the row count is outside the expected range, the pipeline is marked as failed even though the Spark job itself succeeded. Downstream consumers are blocked until the validation passes.

**Prevention:** All new pipelines must pass an idempotency test in code review — run the pipeline twice on the same date in a staging environment and verify the output row count is identical both times. This is now a required checklist item before any data pipeline ships to production.

---

### Incident 3: Airbnb's DAG Deadlock — 12-Hour Pipeline Stall (2020)

**What happened:**

Airbnb's nightly data pipeline in Airflow had the following structure: three data sources extract in parallel, their outputs join into an intermediate table, and then five report jobs run in parallel to generate business dashboards. The whole pipeline ran nightly and completed by 4 AM.

A new engineer added a feature that required Report A to use a summary computed by Report B, and separately, Report B to use a dimension table that Report A computed. Both dependencies seemed reasonable in isolation. Together, they formed a cycle: A depends on B, B depends on A. Neither can start until the other completes.

In Airflow, when a task's upstream dependencies have not completed, the task sits in "queued" state. It does not fail — it just waits. Both Report A and Report B entered "queued" state and waited for each other. All tasks downstream of both reports also entered "queued" state and waited. The entire second half of the pipeline was frozen.

The monitoring system was configured to alert on "failed" tasks, not on "queued for too long" tasks. No alert fired. The on-call engineer did not notice until 8 AM, when business users reported that dashboards were showing yesterday's data.

**Impact:** 12 hours of stale data across every business dashboard that depended on the nightly pipeline. Multiple business meetings were conducted with outdated metrics. Detection was delayed by 4 hours because the monitoring system did not alert on stuck queued tasks.

**Root cause:** Circular dependency introduced by a new engineer who did not run cycle detection. Monitoring gap: no alert for tasks stuck in queued state.

**Fix:**

The circular dependency was broken by identifying the subset of data that both tasks actually needed and extracting it into a new upstream shared intermediate table. Both Report A and Report B now depend on this shared table, and neither depends on the other.

A DAG validation step was added to the CI pipeline:

```python
# Pseudo-code: topological sort to detect cycles
def validate_dag(dag):
    visited = set()
    in_stack = set()
    
    def dfs(node):
        visited.add(node)
        in_stack.add(node)
        for downstream in dag.get_downstream(node):
            if downstream not in visited:
                if dfs(downstream):
                    return True  # cycle found
            elif downstream in in_stack:
                return True  # cycle found
        in_stack.remove(node)
        return False
    
    for task in dag.tasks:
        if task not in visited:
            if dfs(task):
                raise ValueError(f"Cycle detected in DAG {dag.dag_id}")
```

This validation runs on every pull request. A PR that introduces a cycle fails CI and cannot be merged.

A new alert was added: any Airflow task that has been in "queued" state for more than 60 minutes without any upstream task completing triggers a page to on-call. This catches both deadlocks and silent upstream failures.

---

### Incident 4: Uber's Small Files Problem — 25-Minute Job Takes 4 Hours (2018)

**What happened:**

Uber's real-time ride data pipeline writes events to S3 using Kafka Streams in microbatch mode: every 60 seconds, all events accumulated in the last minute are flushed to S3 as a small Parquet file. This is a common pattern — small, frequent writes keep latency low for real-time consumers.

The problem appears when a daily batch job tries to read this data. For a single day of data in a single partition, the 60-second microbatch produces 60 files per hour × 24 hours = 1,440 files. With multiple geographic regions each having their own partition, the total file count for a single day was approximately 34,560 small Parquet files, each averaging 2-5 MB.

When the daily Spark job reads these 34,560 files from S3, the overhead is enormous. S3 LIST operations to discover all files: 5+ minutes. Opening 34,560 individual file handles: significant overhead. Each file triggers its own task in Spark, so the job had 34,560 small tasks instead of a reasonable number of large tasks. The overhead of scheduling, launching, and tracking 34,560 tasks dominated the actual computation time. The job that took 25 minutes when file sizes were normal took 4 hours with the small file pattern.

**Impact:** Daily driver earnings reports (which drivers use to track their income and Uber uses for financial reconciliation) consistently missed their SLA. The job was supposed to complete by 4 AM. It completed between 8 AM and 9 AM.

**Root cause:** Streaming microbatch creates many small files. No compaction step to merge them before batch processing.

**Fix:** A compaction job was added that runs at 55 minutes past every hour:

```python
# Pseudo-code for hourly compaction
def compact_hour(partition_date, partition_hour):
    small_files = list_files(
        path=f"s3://uber-rides/{partition_date}/hour={partition_hour}/",
        max_size_mb=10  # files smaller than 10MB are "small"
    )
    if len(small_files) > 1:
        df = spark.read.parquet(*small_files)
        # Write as single 128MB file
        df.coalesce(1).write.mode("overwrite").parquet(
            f"s3://uber-rides-compacted/{partition_date}/hour={partition_hour}/"
        )
```

The daily batch job now reads from the compacted path, which has 24 files (one per hour) instead of 34,560. Job time dropped from 4 hours to 22 minutes.

**Prevention:** A monitoring rule was added: if the average file size in any output partition drops below 10 MB AND the file count exceeds 1,000, trigger an alert. This catches any new pipeline that starts generating small files before the problem grows large enough to affect SLAs.

---

### Incident 5: Stripe's Timestamp CDC Clock Skew (2021)

**What happened:**

Stripe's data warehouse pipeline uses incremental extraction from the production PostgreSQL database. The extraction query uses a timestamp-based approach:

```sql
SELECT *
FROM payments
WHERE updated_at > :last_extraction_timestamp
ORDER BY updated_at ASC;
```

This is a standard pattern. After each successful extraction, the pipeline stores `MAX(updated_at)` as the watermark for the next run. Any payment updated after the watermark gets picked up in the next run.

One day, the clock on the source PostgreSQL server drifted 8 minutes ahead of true time due to an NTP synchronization failure. Payments processed during this drift period were written to the database with timestamps 8 minutes in the future.

When the NTP daemon corrected the clock — jumping the server's clock backward by 8 minutes — the watermark from the previous run was now AHEAD of the server's current clock. The extraction window `updated_at > last_watermark` now excluded the records with the "future" timestamps, because those timestamps were still greater than the corrected clock's current time but were no longer being returned in the ordered query in the expected way.

More precisely: the watermark had advanced to the end of the drift window. After the clock correction, records in the 8-minute drift window were effectively "behind" the watermark. The next extraction's `WHERE updated_at > watermark` skipped them entirely because the watermark was set after those records' timestamps.

Those 3,200 payment records were never extracted.

**Impact:** 3,200 payment records were missing from the data warehouse for 36 hours. Risk and compliance dashboards showed incorrect payment volumes. Automated fraud detection models that relied on the warehouse data produced incorrect risk scores during this period.

**Root cause:** Timestamp-based CDC assumes that `updated_at` values are monotonically increasing. Clock skew violates this assumption: records written during the drift have timestamps that are "in the past" relative to the corrected watermark, so they fall behind the extraction window and are never picked up.

**Fix:**

The pipeline was migrated from timestamp-based extraction to **WAL-based CDC** using Debezium, a change data capture tool. Debezium reads the PostgreSQL Write-Ahead Log (WAL) directly. The WAL uses **Log Sequence Numbers (LSNs)** — monotonically increasing integers that identify positions in the log. LSNs are assigned by the database engine, not by the system clock. Clock drift has no effect on LSNs. Every committed transaction gets an LSN greater than all previous transactions, without exception.

```
+----------------------------------------------------------+
|  TIMESTAMP CDC vs WAL-BASED CDC                          |
+----------------------------------------------------------+
|                                                          |
|  TIMESTAMP CDC:                                          |
|    Source DB -> filter by updated_at > watermark         |
|    Problem: clock skew can cause records to fall         |
|             "behind" the watermark                       |
|                                                          |
|  WAL-BASED CDC (Debezium):                               |
|    Source DB WAL -> Debezium -> Kafka -> Warehouse       |
|    Watermark: LSN (integer), not timestamp               |
|    LSN always increases, regardless of clock             |
|    Clock skew = irrelevant                               |
+----------------------------------------------------------+
```

In addition to migrating to WAL-based CDC, the team added an overlap window as defense-in-depth: even with WAL-based extraction, the pipeline extracts from `(last_lsn - 10000)` rather than exactly from `last_lsn`. The overlap introduces duplicate records, which are deduplicated at load time using `INSERT INTO ... ON CONFLICT DO NOTHING`. This ensures that even if there is some edge case in LSN tracking, no records are permanently missed — they might be re-processed, but deduplication handles that cleanly.

**Prevention:** The engineering team documented a new standard: timestamp-based CDC is prohibited for any pipeline that carries financial, compliance, or risk data. WAL-based CDC is required. This is documented in the team's architecture decision records (ADR) and enforced in code review. Any pipeline touching the `payments`, `refunds`, or `disputes` tables must use Debezium, full stop.

---

## Summary

The table below ties together the key architectural decisions in this chapter. At the L6 level, every answer you give in an interview should include the tradeoff — what you get, what you give up, and under what conditions the tradeoff is worth it.

| Concept | What You Get | What You Give Up | Choose When |
|---|---|---|---|
| Lambda Architecture | Accurate history AND real-time current | Two codebases, two clusters, merge complexity | Need both historical accuracy and real-time, have large team |
| Kappa Architecture | One codebase, simpler ops, consistent results | Need long Kafka retention, complex batch ops unsupported | Kafka retention is sufficient, logic is streamable |
| Schema validation | Catch structural bugs at ingestion | Compute overhead per record | Always — cheap and catches real bugs |
| Value validation | Catch business-logic violations per row | Requires knowledge of valid value ranges | Any pipeline touching financial or compliance data |
| Statistical validation | Catch bad batches even when individual rows look fine | Requires baseline history to compare against | Any pipeline with SLA-bound consumers |
| Data contracts | Prevent breaking changes from propagating | Coordination overhead between teams | Any dataset with multiple downstream consumers |
| Quarantine pattern | Good data flows despite some bad records | Bad data is delayed, not dropped | When 0.01% bad records should not block 99.99% good data |
| AQE (Spark 3.x) | Automatic skew detection and partition coalescing | Spark 3.0+ required | Always enable; it is free and improves most jobs |
| Spot instances | 60-80% compute cost reduction | Jobs can be interrupted, need checkpointing | Batch jobs > 30 minutes that are not latency-sensitive |
| Parquet + Zstd | 85-90% storage reduction, faster queries | Slightly slower decompression vs Snappy | Always for analytical data; avoid for write-heavy operational data |
| Hourly compaction | Eliminates small-files overhead for daily batch | Adds one hourly job to maintain | Any pipeline that writes microbatch output to S3 |
| WAL-based CDC | Immune to clock skew, complete capture | Requires Debezium or similar, more setup | Financial data, compliance data, any data where missing records is unacceptable |

The five incidents in this chapter each violated one of these principles. Facebook skipped AQE and skew detection. Netflix skipped idempotency (INSERT OVERWRITE). Airbnb skipped DAG cycle detection and "stuck-queued" alerting. Uber skipped compaction. Stripe used timestamp-based CDC for financial data instead of WAL-based CDC. In every case, the fix was simple in hindsight. The hard part is building the discipline to apply these patterns before the incident — which is exactly what L6 engineers are hired to do.
# Chapter 35: Batch Processing and Data Pipelines — Part D

## Staff-Level System Design Interview Prep
### Final Section: Calibration, Brainstorming Questions, Exercises, and Quick Reference

---

## 1. L5 vs L6 Calibration Table

This table shows the exact gap between a strong mid-level answer
and a Staff-level answer for the most common interview sub-questions
in batch processing and data pipeline design.

Study these patterns. The L6 column is not about knowing more facts.
It is about knowing the failure modes, the tradeoffs, and the limits
of each solution.

---

| Dimension | L5 Answer | L6 Answer |
|---|---|---|
| **Batch vs stream choice** | "Use Kafka for everything" or "just use a cron job" | "Batch when: latency of hours is acceptable, need full dataset scan, high throughput. Stream when: latency of seconds matters, event-driven action required. Most production systems need both. Never add streaming complexity when a nightly job solves the problem." |
| **Spark at scale** | "Just run a bigger Spark job" | "Diagnose first: is the job slow due to data skew, shuffle size, small files, or resource bottleneck? Each has a different fix. Adding nodes does not fix skew or small files — it only helps resource bottlenecks." |
| **Data skew** | "Add more Spark partitions" | "Identify the hot key. Apply salting with 2-pass aggregation. Enable AQE. More partitions dilute but do not fix fundamental skew. One key with 30% of rows will always slow one task." |
| **Pipeline idempotency** | "We can just rerun it" | "Rerun must produce identical output. Use partition overwrite, not INSERT INTO. Test idempotency explicitly in CI: run twice, verify row count is identical both times." |
| **ETL vs ELT** | "We transform with Spark before loading" | "ELT for modern stacks (dbt + Snowflake). ETL only when: transformation is too complex for SQL, or raw PII must not enter the warehouse. ELT preserves raw data for re-processing when logic changes." |
| **CDC method** | "Use timestamp-based extraction" | "WAL-based CDC (Debezium) for production: captures deletes, no query load on source DB, no clock skew risk. Timestamp-based: misses deletes, vulnerable to NTP drift. Never use timestamp-based for financial data." |
| **Data lake vs warehouse** | "Use S3 for storage" | "Lake for cheap raw storage and ML training. Warehouse for governed SQL analytics. Lakehouse (Delta/Iceberg) for ACID transactions plus time travel on object storage. Choose based on access patterns, not cost alone." |
| **Lambda vs Kappa** | "Lambda is more robust" | "Lambda means two codebases and double the ops burden. Start with Kappa if Kafka retention covers your reprocessing window. Add a batch layer only when reprocessing needs exceed stream replay. Most teams over-engineer Lambda." |
| **Data quality** | "We'll fix bad data after it's reported" | "Validate at 4 layers: schema, values, statistics, cross-pipeline reconciliation. Data quality is an engineering problem, not a data team problem. Quarantine bad records; do not fail the entire pipeline on partial bad data." |
| **Cost optimization** | "We need the cluster always on" | "Spot instances for 60-80% savings. Ephemeral clusters that terminate after the job. CSV to Parquet for 85% storage reduction. Serverless SQL for ad-hoc queries. Lifecycle policies for cold data. Every pipeline has a cost owner." |
| **Small files problem** | "That's just how Spark writes data" | "Compaction is a first-class pipeline step, not an afterthought. Alert when avg file size < 10 MB and file count > 1,000. Compaction frequency should match read frequency. Missing compaction causes 10-100x slower reads." |
| **Pipeline failure alerting** | "Page on-call when the job fails" | "Alert on: job duration > 2x historical average (before it fails). Data freshness SLA breach. Row count anomaly of plus or minus 30%. Error rate above 1%. Detect degradation early — not only on complete failure." |

---

## 2. Brainstorming Questions

There are 20 questions across 4 themes.

These are not trivia questions.
They are open-ended design problems that mirror real L6 interview prompts.
For each one: talk through your reasoning, not just your answer.
The interviewer is evaluating your thinking process.

---

### Theme A: Spark and Batch Architecture

---

**Question 1: Partition Strategy at Scale**

You have a daily Spark job that aggregates 500 GB of user events.

Aggregation dimensions:
- country
- device_type
- user_id

Current runtime: 45 minutes.

Data is growing at 20% per month.

At 6 months, the dataset will be 2.5 TB.

Tasks:
- Design the partition strategy for the output table
- What Spark optimization settings do you configure?
- Estimate the expected runtime at 2.5 TB with the same cluster
- What is the breaking point where you need to redesign the job or the cluster?
- What metric do you monitor to detect that the job is approaching that breaking point?

Think about:
- How the number of shuffle partitions should scale with data size
- Whether AQE handles the growth automatically or needs manual tuning
- What "breaking point" means: SLA breach, not just slow job

---

**Question 2: Join Strategy for Multi-Table Pipeline**

An e-commerce company runs a monthly billing job.

Tables:
- orders: 2 TB
- products: 5 GB
- users: 50 GB

The join on user_id is extremely slow.

Stage 2 in the Spark UI shows a 6-hour shuffle.

Tasks:
- Diagnose the likely cause of the slow join
- Design the join strategy for each table pair
  - orders JOIN products
  - orders JOIN users
  - Which uses broadcast join? Which uses sort-merge join?
- At what table size does broadcast join become unsafe?
- How does the join strategy change when data volume grows 10x?
- What Spark configs control broadcast join threshold?

Think about:
- Broadcast join is only safe when the smaller table fits in executor memory
- Sort-merge join is safer but causes a full shuffle
- Data skew on user_id will show up even with the right join type

---

**Question 3: Small Files Compaction Strategy**

Your Spark job processes log files.

Upstream writes 500 files per hour, each approximately 5 MB.

After 24 hours: 12,000 files.
After 30 days: 360,000 files.

The daily batch job reads 30 days of logs.
File listing overhead alone takes 45 minutes before any computation starts.

Tasks:
- Design the compaction strategy
  - When do you compact? (hourly? daily? triggered?)
  - What target file size do you compact to?
  - How do you determine the right target size?
- How do you handle concurrent reads during compaction?
  - If a reader is scanning a partition while compaction runs, what breaks?
- Design the alerting: what metric triggers a compaction warning?
- In Delta Lake or Iceberg, how does the built-in compaction (OPTIMIZE) differ
  from a manual Spark job?

Think about:
- Optimal Parquet file size for Spark reads: 128 MB to 1 GB
- Compaction using Delta Lake OPTIMIZE + Z-ORDER
- Atomic file replacement vs in-place modification

---

**Question 4: ML Feature Engineering at Scale**

A fraud detection team wants to add a new feature to ML model training.

Feature: number of distinct merchants visited per user in the last 7 days.

This requires a GROUP BY over 7 days of transaction data: 3 TB.

Current training job:
- Fixed 4-node cluster
- Runs in 2 hours
- Outputs one feature matrix per user

Tasks:
- Estimate how much additional compute is needed for this feature
- What Spark settings change for a 7-day rolling window aggregation?
- Should this feature be computed in a batch job (nightly) or a stream job
  (updated continuously)?
- If the feature is updated in a stream, what happens to model consistency?
  (The model was trained on daily batch data, not real-time features)
- Design the feature store integration: how is the computed feature served
  to the inference pipeline?

Think about:
- Training-serving skew: features at training time must match features at serving time
- Rolling window aggregation requires a full re-scan of 7 days of data each day
- Stream-computed features introduce staleness and replayability challenges

---

**Question 5: Schema Migration with 50 Consumers**

Your Spark job reads from a Delta Lake table.

A colleague ran a schema migration:
- Added 3 new columns
- Removed 1 old column (`legacy_discount_code`)
- Forgot to update your Spark job

Tasks:
- What happens when the Spark job runs after this migration?
  - Does the failure happen at the read step or the write step?
  - What error message do you expect?
- How does Parquet schema evolution handle:
  - Added columns (columns present in file but not in schema)
  - Removed columns (columns present in schema but not in file)
- Design the safest migration strategy for a table with 50 concurrent consumers:
  - How do you communicate the migration in advance?
  - What is the rollback plan if 10 consumers break after the change?
  - What is the minimum deprecation window for a removed column?
- In Delta Lake: what does `mergeSchema = true` do? When is it safe to use?

Think about:
- Schema-on-read vs schema-on-write semantics
- Added columns: safe (old readers return null for new columns)
- Removed columns: unsafe (old readers expect the column and get StructField errors)

---

### Theme B: Pipeline Design and CDC

---

**Question 6: Debezium CDC Pipeline Design**

You are building a pipeline to ingest from a PostgreSQL database
with 50 million rows in the `orders` table.

Current approach: full table scan nightly (`SELECT * FROM orders`)
Duration: 3 hours. Growing monthly.

New requirements:
- Data freshness: < 15 minutes
- No significant query load on the production database

Tasks:
- Design the Debezium-based CDC pipeline end to end
  - Source connector configuration
  - Kafka topic design (name, partitions, retention)
  - Consumer (Spark Structured Streaming or Flink) design
- What happens if Debezium falls 2 hours behind?
  - How do you detect this? (lag monitoring)
  - How do you recover without losing events?
- What happens if the PostgreSQL WAL segment is rotated before Debezium reads it?
  - What error does Debezium produce?
  - What is the recovery procedure?
- How do you handle the initial snapshot (before Debezium is running)?

Think about:
- WAL retention: PostgreSQL default is 24 hours. Debezium needs WAL slot.
- `max_wal_size` and `wal_keep_size` settings
- Initial snapshot uses PostgreSQL snapshot isolation (consistent read)

---

**Question 7: Fan-Out Pipeline to Multiple Destinations**

You have a pipeline that processes user events and must write to two destinations:

Destination 1: BigQuery (batch, nightly aggregates, freshness: daily)
Destination 2: Elasticsearch (near-real-time, freshness: < 5 minutes)

Both destinations must be fed from a single source of truth.

Tasks:
- Design the pipeline architecture that serves both destinations
  from one data source (Kafka)
- What happens if the BigQuery write succeeds but Elasticsearch fails?
  - How do you detect this?
  - How do you replay only the failed Elasticsearch writes?
- What happens if Elasticsearch succeeds but BigQuery fails?
  - Is this more or less severe? Why?
- Design the consistency guarantee:
  - Can the two destinations ever be out of sync? For how long?
  - Is eventual consistency acceptable here?
- How do you test that both destinations stay consistent under partial failure?

Think about:
- Two separate consumers on the Kafka topic (consumer groups)
- Offset management per consumer group
- Dead-letter queues for failed Elasticsearch writes
- BigQuery failure is less severe (nightly, aggregated — can re-run)

---

**Question 8: Flaky Upstream Task Strategy**

An Airflow DAG has 4 tasks:

- extract_orders (success rate: 99%)
- extract_users (success rate: 80% — flaky)
- extract_products (success rate: 99%)
- join_all (depends on all 3 extract tasks)

The join_all task cannot run until all 3 extracts succeed.

Tasks:
- Design a retry strategy for extract_users
  - How many retries? What backoff?
  - When does a retry become a DAG failure vs a warning?
- Design an SLA for the overall pipeline given a 20% failure rate on one task
  - What is the expected success rate of the full DAG?
  - What p50 and p95 completion time do you commit to?
- Design a fallback behavior:
  - If extract_users fails after 3 retries, can join_all use yesterday's user data?
  - Is stale user data acceptable? For which downstream consumers?
- At what point does a flaky upstream task become a redesign problem?
  - 20% failure rate: retry
  - 50% failure rate: ?
  - 80% failure rate: ?

Think about:
- P(full DAG success) = P(orders) x P(users) x P(products) = 0.99 x 0.8 x 0.99 ≈ 0.78
- 78% success rate on a daily job means the pipeline fails 1 in 5 days
- At 20% failure rate, the upstream system is broken — not the pipeline

---

**Question 9: Daily to Hourly Pipeline Migration**

Your pipeline currently runs once per day at 2 AM.

Current profile:
- Input data: 100 GB per day
- Runtime: 30 minutes
- Output: 1 partition per day in the warehouse

Business asks for hourly dashboard refreshes.

Tasks:
- Design the migration from daily to hourly processing
  - What changes in the Spark job?
  - What changes in the output partitioning schema?
  - What changes in the Airflow/orchestration schedule?
- What is the compute cost multiplier when moving from daily to hourly?
  - Naive calculation: 24x. Is this accurate? Why or why not?
  - What is the actual multiplier if each hourly job has fixed overhead (startup, small files)?
- What changes in the output schema?
  - If the daily table is partitioned by `date`, the hourly table is partitioned by... what?
  - How do downstream consumers need to change their queries?
- Design a backfill plan:
  - You switch to hourly starting June 14. How do you backfill June 1-13 in hourly partitions?

Think about:
- Startup overhead per job: if daily job is 30 min and startup is 5 min, hourly jobs cost
  24 x 30 min = 720 min vs 24 x 5 min extra startup = 120 min overhead added
- Output schema: partition by `date` AND `hour`
- Downstream consumers: must change `WHERE date = '2026-06-14'` to include hour

---

**Question 10: 2-Year Historical Backfill**

You found a bug in your pipeline that has been running for 2 years.

The bug: a filter was incorrectly excluding orders with `status = 'pending'`.
All pending orders for the last 2 years are missing from the warehouse.

Data profile:
- Each day of data: 50 GB
- Processing time per day: 20 minutes
- Total: 730 days x 20 minutes = 243 hours of compute (sequential)

Available: a 10-node cluster that is normally idle overnight.

Tasks:
- Design the backfill plan
  - What is the parallelism strategy? (how many days in parallel?)
  - What is the ordering? (oldest first, or newest first, or random?)
  - How do you prevent the backfill from impacting existing production jobs?
- Estimate the wall-clock time to complete the backfill
  - With 10-node cluster, naive: 243 hours / 10 = 24.3 hours
  - Is this accurate? What are the real constraints?
- How do you validate the backfill is correct?
  - What checks do you run after each day is reprocessed?
  - How do you verify the total count is correct at the end?
- What happens if the backfill job is interrupted on day 400 of 730?
  - How do you resume without re-processing completed days?
  - Why is idempotency critical here?

Think about:
- Ordering: newest first means the most-used recent data is fixed fastest
- Parallelism limit: cluster has 10 nodes, but job startup overhead limits true parallelism
- Idempotency: partition overwrite means re-running day 400 is safe

---

### Theme C: Data Quality and Governance

---

**Question 11: Revenue Discrepancy Investigation**

Your revenue pipeline has been running for 6 months.

A data analyst reports:
- Revenue numbers for Q2 (3 months ago) do not match the finance system
- Discrepancy: 2.3% ($4.7M out of $200M)

Tasks:
- Walk through your investigation in order:
  - Where do you look first?
  - What tools and queries do you run?
  - Who do you contact?
- How do you determine if this is an ongoing bug vs a one-time incident?
  - What distinguishes a systematic issue from a timing anomaly?
- Design the data reconciliation process:
  - How do you compare your pipeline's output to the finance system?
  - What is the acceptable reconciliation threshold for revenue? (0.1%? 1%? 0.01%?)
- How do you communicate a $4.7M discrepancy to business stakeholders?
  - What information do they need?
  - What is the resolution SLA?

Think about:
- First check: compare raw source counts to warehouse counts by day
- Second check: look for missing transaction types (refunds, adjustments, currency)
- Third check: time zone handling (orders placed at 11:59 PM UTC vs local time)
- A 2.3% discrepancy on financial data is a severity-1 incident

---

**Question 12: Data Quality Framework Design**

You own a pipeline with:
- 5 upstream data sources (3 PostgreSQL, 1 Kafka, 1 Salesforce API)
- 3 downstream consumers (BI dashboards, ML training, financial reporting)

Last quarter: two incidents
- Null user_ids in 15% of rows (undetected for 3 days)
- Row count dropped 40% due to a filter bug (undetected for 1 week)

Tasks:
- Design 3 data quality checks at ingestion (before transformation)
- Design 3 data quality checks at transformation output
- Design 2 cross-pipeline reconciliation checks
- Design the alerting thresholds:
  - At what bad-record percentage: warn and continue?
  - At what percentage: quarantine bad records, continue with clean data?
  - At what percentage: fail the entire pipeline?
- How do you establish and communicate data quality SLAs to:
  - The 5 upstream teams (who produce the data)
  - The 3 downstream teams (who consume the data)

Think about:
- Ingestion checks: schema match, null rate on primary keys, row count vs yesterday
- Transform checks: uniqueness on output key, referential integrity, value range validation
- Quarantine: isolate bad records to a separate table, process clean records normally
- Fail pipeline: null rate > 5% on primary key, or row count drop > 50%

---

**Question 13: Schema Migration with Downstream Impact**

Your team owns a `user_features` table used by 8 ML teams.

Requested changes:
- Rename column: `user_signup_date` → `registration_date`
- Type change: `purchase_count` from INT to BIGINT

Tasks:
- Design the migration strategy that minimizes disruption to all 8 consumers
  - What is the minimum deprecation notice period?
  - Can you run old and new column names in parallel during transition?
  - What is the exact sequence of steps?
- What is the rollback plan if a consumer breaks after migration?
  - How long does rollback take?
  - Is rollback possible if consumers have already written data using the new schema?
- How do you verify all 8 teams are aware of and ready for the change?
  - What is the communication process?
  - What constitutes "ready"? (tested in staging? confirmed in writing?)
- For the type change (INT → BIGINT):
  - Is this backwards compatible? Which consumers break?
  - Which SQL engines handle implicit INT to BIGINT casting? Which do not?

Think about:
- Parallel column approach: add `registration_date` while keeping `user_signup_date`
  (populated with same value). Deprecate old column after all 8 teams migrate.
- Minimum deprecation window: 2 sprints (4 weeks) for internal teams
- BIGINT is backwards-compatible in most SQL engines but breaks strict type checking in Spark

---

**Question 14: GDPR Right-to-Deletion Across Storage Systems**

A GDPR deletion request arrives for user_id 12345.

Your data infrastructure contains:
- Raw event data in S3, partitioned by date (2 years of data, 730 partitions)
- Daily aggregates in BigQuery (user-level dimensions, but no direct PII)
- ML feature store (Feast) with computed features keyed by user_id
- Daily snapshots in Redshift (user profile table, updated nightly)

Tasks:
- For each storage system, describe:
  - The deletion mechanism (what command or API)
  - The complexity (hours? days? engineer time required?)
  - The risk (what could break if this user's data is deleted mid-pipeline?)
- GDPR requires deletion "without undue delay" — typically 30 days
  - Design the SLA and workflow for processing deletion requests
  - What is the handoff between legal, engineering, and data teams?
- For S3 with 730 date partitions:
  - You cannot delete a single row from a Parquet file without rewriting the file
  - How do you handle this at scale with 1,000 deletion requests per day?
- For BigQuery aggregates:
  - If the aggregates are anonymized (no user_id column), is deletion required?
  - When does aggregated data become "personal data" under GDPR?

Think about:
- S3 deletion at scale: crypto-shredding (encrypt user data with a per-user key, delete the key)
- Feature store deletion: Feast supports point-in-time deletion by entity key
- Redshift: DELETE WHERE user_id = 12345 (simple, but must be replayed to snapshots)
- BigQuery aggregates: if k-anonymity is maintained (> 5 users per aggregate), no deletion needed

---

**Question 15: Cross-Pipeline Reconciliation Failure**

Your pipeline reads from 3 source databases:
- orders_db (PostgreSQL)
- payments_db (PostgreSQL)
- inventory_db (MySQL)

After nightly load to the warehouse, you run:
`SELECT SUM(orders.total) = SUM(payments.total)`

The check fails. There is a $50,000 discrepancy.

Tasks:
- Diagnose: is this a pipeline bug, a source data bug, or expected?
  - List 5 possible causes of a reconciliation discrepancy
  - Which causes are "expected" (not a bug)?
  - Which require immediate action?
- What queries do you run to narrow down the cause?
  - How do you find which specific orders are in payments_db but not in orders_db?
  - How do you determine if the discrepancy is growing or stable?
- Design the escalation decision tree:
  - Discrepancy < 0.1%: acceptable for timing differences?
  - Discrepancy > 1%: page on-call?
  - Discrepancy in financial data > $10K: escalate to finance?
- When is a reconciliation discrepancy acceptable vs requiring immediate action?

Think about:
- Timing: orders placed at 11:59 PM may be captured in orders_db before payment clears
- Refunds: payment reversals may lag order updates
- Currency: if orders and payments use different currency fields, FX conversion timing differs
- Pipeline lag: orders pipeline ran at 2 AM, payments pipeline ran at 3 AM — different snapshots

---

### Theme D: Scale, Cost, and Architecture

---

**Question 16: Cost Optimization Under Budget Pressure**

Your daily batch job profile:
- Data processed: 1 TB
- Runtime: 2 hours
- Cluster: 20 nodes, on-demand EC2
- Monthly compute cost: $3,000

Target: reduce to under $1,000/month (67% reduction).

Tasks:
- Design the optimized infrastructure
  - Which optimizations give the highest ROI?
  - What is the estimated cost after each optimization?
- For spot instances:
  - What are the risks? (interruption, partial job completion)
  - What Spark setting enables checkpointing for spot interruption resilience?
  - What is the maximum acceptable interruption rate before spot is not viable?
- For Parquet vs CSV:
  - If current storage is CSV, what is the storage cost reduction from converting to Parquet?
  - Does Parquet compression also reduce compute cost? How?
- At what point is it worth investing 2 weeks of engineer time in optimization
  vs just paying the bill?
  - Calculate the break-even: 2 weeks of L6 engineer time vs $2,000/month savings

Think about:
- Spot instances: 60-80% savings. Use with checkpointing and Spot Fleet diversification
- Parquet: 85% storage reduction from columnar compression + column pruning at read time
- Break-even: $2,000/month savings x 12 months = $24,000/year. 2 weeks of L6 eng ≈ $15K loaded cost. Worth it.

---

**Question 17: Lambda vs Kappa Architecture Decision**

Current architecture:
- events → Kafka → Flink → Redis (real-time fraud decisions, < 100ms latency)

New requirement from the risk team:
- Daily fraud summary reports, available by 6 AM
- Data needed: all fraud decisions from the past 90 days
- Historical reprocessing: if fraud logic changes, must be able to reprocess 90 days

Tasks:
- Design Option A (Lambda):
  - Keep Flink for real-time
  - Add a Spark batch job for daily reports
  - List all components needed
  - What is the ops overhead?
  - Where is the code duplication?
- Design Option B (Kappa):
  - Use Flink for both real-time decisions and daily reports
  - How do you generate daily reports from a streaming job?
  - What Kafka retention do you need? (Current: 7 days)
  - How do you handle the 90-day historical requirement?
- Compare on 4 dimensions:
  - Ops complexity
  - Code duplication
  - Historical reprocessing capability
  - Team skill requirement
- Recommend one option for a team of 6 engineers. Justify.

Think about:
- Lambda: two codebases = two sets of bugs, two deploy pipelines, inconsistency risk
- Kappa: needs Kafka retention > 90 days, or S3 archive with Flink replay
- For 2-year history: Lambda wins (Spark reads S3 data lake); Kappa struggles
- For 6 engineers: Lambda if team has Spark expertise. Kappa if team is Flink-native.

---

**Question 18: BigQuery Cost Reduction**

Current BigQuery spend: $15,000/month.

Primary cost driver: one analytics dashboard
- 500 queries per day
- Each query scans 1 TB
- Cost: $5/TB x 1 TB x 500 queries/day x 30 days = $75,000/month
  (Note: the $15K is after some existing optimizations — use this as your baseline)

Your task: design a plan to reduce this cost by 80% (to $3,000/month or less).

Tasks:
- Materialized views:
  - What queries does this help? What are the limits (freshness, query shapes)?
  - What is the cost reduction?
- Partitioning and clustering:
  - If the dashboard always filters by `date` and `country`, what does this change?
  - What is the cost reduction from partition pruning?
- Query result caching:
  - When does BigQuery cache query results?
  - What invalidates the cache?
  - For a dashboard refreshed every hour, is caching useful?
- Pre-computation:
  - If you pre-compute all common aggregates nightly into a summary table,
    what is the query cost against the summary table (assume 1 GB per day of aggregates)?
- Design the combined approach and produce a revised monthly cost estimate.

Think about:
- Partitioning: scan drops from 1 TB to 1/365 TB if filtered by single day = $0.014 per query
- Pre-computation: 500 queries x 1 GB x $5/TB = $2.50/day = $75/month (from $75K/month)
- Combined savings: partitioning + pre-computation can reduce to < $500/month

---

**Question 19: Healthcare Data Pipeline with Compliance Constraints**

Design a data pipeline for a healthcare company.

Source: 200 hospital databases (PostgreSQL), each with patient records.

Destination: central data warehouse for population health analytics.

Constraints:
- HIPAA compliance required
- No PII in the analytics warehouse
- Data must be available within 4 hours of creation at the source
- Volume: 5 million new records per day across 200 hospitals

Tasks:
- Design the full pipeline architecture:
  - How do you ingest from 200 separate databases?
  - Where and how do you de-identify the data? (before or after transfer?)
  - What encryption is required in transit and at rest?
- HIPAA Safe Harbor de-identification:
  - What 18 identifiers must be removed?
  - How do you handle dates? (HIPAA requires dates to be shifted or removed)
  - What is a "Limited Data Set" and when is it allowed?
- Design the access control model for the analytics warehouse:
  - Who can query the warehouse?
  - What is the audit log requirement?
  - How do you implement column-level security for quasi-identifiers?
- For the 4-hour freshness SLA:
  - Is CDC or batch extraction the right choice?
  - What is your alerting strategy if a hospital's pipeline falls behind?

Think about:
- De-identification must happen before data leaves the hospital network or at a secure ETL layer
- Crypto-shredding: encrypt PII with a hospital-specific key before transfer; key stays at hospital
- Audit logs: HIPAA requires logging of all access to PHI (patient health information)
- 200 hospitals x Debezium = 200 Kafka connectors — use a managed CDC service

---

**Question 20: Greenfield Data Infrastructure Design**

You are designing the data infrastructure for a new analytics product from scratch.

Requirements:
- 50 microservices producing events (click events, transactions, inventory updates)
- 10 consumer teams (analytics, ML, finance, marketing, operations, 5 more)
- Real-time dashboards (latency < 1 minute)
- Daily reports (available by 7 AM)
- ML model training (weekly, full historical data, 3-year retention)
- Budget: $50,000/month

Tasks:
- Design the full stack:
  - Event ingestion layer
  - Stream processing layer
  - Storage layer (data lake, warehouse, feature store)
  - Batch processing layer
  - Orchestration
  - Data catalog and governance
- For each component: what technology do you choose and why?
- Estimate the monthly cost breakdown across components
- How do you onboard the 10 consumer teams without creating a bottleneck?
  - Self-service vs gated access
  - What does the data contract look like?
- How does the architecture change when budget doubles to $100,000/month?
  - What capabilities does the additional $50K unlock?
  - What problems does money not solve?

Think about:
- $50K/month is significant. You can afford: managed Kafka ($5K), Snowflake ($15K),
  Databricks ($20K), Airflow ($2K), misc ($8K). That is a full modern data stack.
- The hard problem is not cost — it is governance: 10 teams, 50 producers, no central ownership
- Data contracts: producers define schemas and SLAs; consumers subscribe; violations are automated alerts

---

## 3. Homework Exercises

There are 6 exercises.

Each exercise has a setup, specific tasks, and an L6 hint.

Work through each exercise before reading the hint.
The hint reveals the answer an interviewer is looking for.

---

### Exercise 1: Diagnose a Slow Spark Job

Time estimate: 20 minutes.

**Setup**

A Spark job joins two tables:
- orders: 500 GB
- users: 10 GB
- Join key: user_id

Spark UI results:
- Stage 1 (read + project): 3 minutes
- Stage 2 (shuffle join): 4.5 hours
- Task duration in Stage 2:
  - p50: 2 minutes
  - p90: 8 minutes
  - p99: 4.5 hours
- One executor has been running the same task for 4.5 hours

**Tasks**

1. What is the root cause?
   - Diagnose from the symptoms above
   - Do not guess — derive the answer from the Spark UI data

2. Why is one task 135x slower than the median?
   - What data is that task processing?
   - Why does the join key cause this?

3. Write the Spark configuration changes to fix this
   - Do not change the query logic
   - Use config names and values

4. Rewrite the join as a broadcast join
   - When is this safe to do?
   - What is the threshold for the broadcasted table?
   - What config controls this?

5. The fix works today
   - Data grows 3x next quarter
   - How do you ensure the fix still holds?
   - What monitoring do you add?

**L6 Hint**

Root cause: data skew on user_id.
One user_id (likely a business account or test account) has millions of orders.
All rows for that user_id land in one Spark partition → one task.
That task processes 30% of the data while 199 tasks process 70%.

Fix with Spark configs:

```
spark.sql.adaptive.enabled = true
spark.sql.adaptive.skewJoin.enabled = true
spark.sql.adaptive.skewJoin.skewedPartitionThresholdInBytes = 256MB
```

Broadcast join fix:

```
spark.sql.autoBroadcastJoinThreshold = 11000000000
```

(11 GB — above the 10 GB users table size)

3x growth risk:
- users table grows from 10 GB to 30 GB
- 30 GB exceeds executor memory → broadcast join fails with OOM
- Monitor: alert when users table exceeds 8 GB → fallback to sort-merge join with AQE

---

### Exercise 2: Design an Idempotent ETL Pipeline

Time estimate: 25 minutes.

**Setup**

Daily Spark job:
- Reads `orders` table from PostgreSQL
- Aggregates by product and region
- Writes to BigQuery table `daily_revenue`

Current write code:

```python
df.write.mode("append").save("bigquery://daily_revenue")
```

Incident: pipeline failed mid-run yesterday.
On-call restarted it.
Revenue report now shows 2x actual revenue for yesterday.

**Tasks**

1. Why did the data double?
   - Trace the exact failure sequence step by step
   - At what step did the data corruption occur?

2. Rewrite the write operation to be idempotent
   - Use partition overwrite
   - Write the corrected code

3. Add a post-run validation check
   - What does it verify?
   - What threshold triggers an alert vs a pipeline failure?

4. Design a test for idempotency in CI
   - How do you verify in automated tests that the pipeline is idempotent?
   - What is the test input, what do you run, what do you assert?

5. Fix the doubled data for yesterday
   - How do you remove the duplicate rows for that specific date?
   - How do you verify the fix is correct without affecting other dates?

**L6 Hint**

Why data doubled:
- Run 1: partial success, some rows written to `daily_revenue` for June 13
- On-call restarts the job (does not delete the partial write)
- Run 2: completes successfully, appends all rows for June 13 again
- Result: June 13 has 2x rows

Fix — idempotent write:

```python
df.write \
  .mode("overwrite") \
  .partitionBy("date") \
  .option("partitionOverwriteMode", "dynamic") \
  .save("bigquery://daily_revenue")
```

Post-run validation:

```sql
SELECT COUNT(*) FROM daily_revenue WHERE date = execution_date
```

Compare to: 7-day rolling average COUNT ± 30%.
Alert if outside range. Fail if outside 50%.

CI idempotency test:
- Run the pipeline once → record row count
- Run again without deleting output → record row count again
- Assert: both counts are identical

Fix yesterday's data:

```sql
DELETE FROM daily_revenue WHERE date = '2026-06-13';
```

Then re-run the pipeline for June 13 only.
Verify: `SELECT SUM(revenue) WHERE date = '2026-06-13'` matches source.

---

### Exercise 3: CDC Migration from Full Extract

Time estimate: 30 minutes.

**Setup**

Current pipeline:
- Full table extract nightly: `SELECT * FROM payments`
- 50 million rows, growing 1% per day
- Extract → CSV → S3 → load to Redshift
- Current problems:
  - 3-hour extract window blocks OLTP performance
  - Misses DELETE operations
  - Clock skew incidents (NTP drift causes some rows to be missed)

**Tasks**

1. Design the Debezium CDC replacement end to end
   - Source connector configuration (key settings)
   - Kafka topic design
   - Consumer design for Redshift loading

2. What Kafka topic structure do you use?
   - Topic name
   - Partition key
   - Retention period
   - Number of partitions

3. How do you handle the initial snapshot?
   - You are replacing a full-extract system
   - Debezium has never run before
   - How does Debezium take the first snapshot without locking the table?

4. A payment record is updated 3 times in 1 second
   - How many Kafka messages does Debezium produce?
   - How does the Redshift consumer handle multiple messages for the same payment?
   - What SQL operation does the consumer use?

5. WAL retention is configured to 24 hours
   - Debezium falls behind by 30 hours due to an outage
   - What happens?
   - What is the recovery procedure?
   - How do you prevent this in the future?

**L6 Hint**

Topic design:
- Name: `cdc.payments.v1`
- Partition key: `payment_id` (ensures ordering per payment)
- Retention: 7 days (enough for weekend outages)
- Partitions: 16 (scale with downstream consumers)

Initial snapshot:
- Debezium uses PostgreSQL snapshot isolation
- `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ` → reads a consistent point in time
- No table lock required
- After snapshot, switches to WAL streaming from the snapshot LSN

3 updates → 3 Kafka messages:
- Each UPDATE in PostgreSQL produces one WAL record → one Kafka message
- Consumer uses MERGE INTO (upsert):

```sql
MERGE INTO payments AS target
USING staging AS source ON target.payment_id = source.payment_id
WHEN MATCHED THEN UPDATE SET ...
WHEN NOT MATCHED THEN INSERT ...
```

- Keep the latest by Kafka offset or `updated_at` timestamp

WAL expiry recovery:
- Debezium cannot resume from WAL (it is gone)
- Must take a new full snapshot of the payments table
- All downstream consumers must handle the snapshot (full table re-load, not incremental)
- Prevention: increase WAL retention to 7 days. Alert when Debezium lag > 12 hours.

---

### Exercise 4: Data Quality Framework Design

Time estimate: 25 minutes.

**Setup**

Your pipeline:
- 3 source databases → Spark transformation → Snowflake

Downstream consumers:
- 5 teams: BI dashboards, ML training, financial reporting, ops, marketing

Recent incidents:
- Incident 1: null user_ids in 15% of rows — undetected for 3 days
- Incident 2: row count dropped 40% — undetected for 1 week

Current state: no automated data quality checks.

**Tasks**

1. Design 3 data quality checks at ingestion
   - Before any transformation runs
   - Name each check, describe what it measures, and the alert threshold

2. Design 3 data quality checks at transformation output
   - After Spark writes to the staging table
   - Name each check, describe what it measures, and the alert threshold

3. Design 2 cross-pipeline reconciliation checks
   - Checks that span multiple datasets
   - What do they verify? What is the failure threshold?

4. Design the severity thresholds:
   - At what bad-record rate: warn and continue (no action)?
   - At what bad-record rate: quarantine bad records, continue with clean data?
   - At what bad-record rate: fail the entire pipeline?

5. How do you establish data quality SLAs with upstream teams?
   - What is in the SLA?
   - What happens when an upstream team violates the SLA?

**L6 Hint**

Ingestion checks:
1. Schema match: incoming schema matches expected schema. Fail pipeline if columns are missing.
2. Null rate on primary keys: null_count / total_count on user_id, order_id. Alert if > 0.1%, fail if > 5%.
3. Row count vs yesterday: abs(today - yesterday) / yesterday > 30% → alert. > 50% → fail.

Transformation output checks:
1. Uniqueness: `SELECT COUNT(*) - COUNT(DISTINCT output_key)` = 0. Fail if duplicates found.
2. Referential integrity: all user_ids in output exist in the users dimension table. Alert if > 0.01% orphans.
3. Value range: all revenue values > 0. All quantities > 0. Alert on any negative values.

Cross-pipeline reconciliation:
1. Row count reconciliation: source row count = destination row count ± 0.01%. Alert on deviation.
2. Sum reconciliation: SUM(orders.total) = SUM(payments.total). Alert on any discrepancy > 0.1%.

Severity thresholds:
- Bad record rate < 0.1%: log warning, continue
- Bad record rate 0.1% to 5%: quarantine bad records to a separate table, process clean records, alert on-call
- Bad record rate > 5% on primary keys: fail the pipeline, page on-call, block downstream consumers

Upstream SLA:
- Document: expected schema, null rate < 0.1% on keys, row count within 30% of daily average
- Violation response: automated alert to the upstream team's on-call channel
- Repeated violations: escalation to their engineering manager

---

### Exercise 5: Lambda vs Kappa Decision

Time estimate: 20 minutes.

**Setup**

Current architecture:
- Flink processes payment events in real time
- Output: fraud decisions to Redis, latency < 100ms

New requirement:
- Daily fraud summary reports for the risk team (90 days of history needed)
- Kafka retention: 7 days

**Option A — Lambda:**

Keep Flink for real-time + add a Spark batch job for daily reports.

**Option B — Kappa:**

Use Flink for both real-time decisions and daily aggregate reports.

**Tasks**

1. For each option:
   - List all components required
   - Estimate ops overhead (pipelines to maintain, deploy, monitor)
   - Identify where code is duplicated between real-time and batch logic

2. Kafka retention is 7 days
   - In Option B (Kappa), how do you generate reports that need 90 days of data?
   - Design the solution

3. A bug is found in the fraud detection logic
   - How do you reprocess 90 days of data in Option A (Lambda)?
   - How do you reprocess 90 days of data in Option B (Kappa)?

4. The risk team later asks for reports using data from 2 years ago
   - How does each option handle this?
   - Which option handles it more easily?

5. Recommend one option for a team of 6 engineers
   - State your recommendation and the 3 most important reasons

**L6 Hint**

Option A (Lambda) components:
- Flink job (real-time)
- Spark batch job (daily reports)
- S3 data lake (historical storage)
- Airflow (batch orchestration)
- Duplicate logic: fraud feature computation exists in Flink AND in Spark SQL

Option B (Kappa) components:
- Flink job (real-time + batch reports via session windows or periodic triggers)
- Kafka with extended retention (90 days) OR S3 archive with Flink source connector

90-day history in Kappa:
- Option 1: increase Kafka retention to 90 days (cost: depends on event volume)
- Option 2: stream events to S3 as they arrive, use Flink's FileSystem source to replay

2-year history:
- Lambda: Spark reads from S3. Straightforward.
- Kappa: Kafka cannot hold 2 years. Must replay from S3 through Flink. Complex.
- Lambda wins for long historical lookback.

Recommendation for 6 engineers:
- Choose Lambda if the team has Spark knowledge (likely)
- Two codebases is manageable at 6 engineers
- Kappa makes sense only if the team is Flink-native and ops overhead of two pipelines is the primary concern

---

### Exercise 6: Cost Optimization Audit

Time estimate: 25 minutes.

**Setup**

Monthly AWS data infrastructure bill: $45,000.

Breakdown:
- EC2 on-demand (Spark clusters): $22,000/month
- S3 storage (all hot tier): $14,000/month
- Data transfer (S3 to Redshift): $9,000/month

Target: reduce to $15,000/month (67% reduction).

**Tasks**

1. Identify the highest-ROI optimization in each cost category
   - EC2: what is the single change with highest impact?
   - S3: what is the single change with highest impact?
   - Data transfer: what is the single change with highest impact?

2. On-demand to spot instances
   - Estimate the savings
   - List the top 3 risks
   - What Spark setting enables checkpointing for spot interruption resilience?
   - What is the checkpointing configuration?

3. S3 lifecycle policy design
   - Which data can safely move to cheaper tiers?
   - Design the lifecycle rules (3 tiers with transition thresholds)
   - What is the risk of moving active pipeline data to Intelligent-Tiering?

4. CSV to Parquet conversion
   - If current data is 100% CSV, estimate storage reduction from converting to Parquet with Snappy
   - Does this also reduce data transfer costs? How?
   - What is the one-time cost of the conversion job?

5. Produce a revised monthly estimate
   - Apply all optimizations from tasks 1-4
   - Show the calculation for each line item
   - Total the revised monthly cost

**L6 Hint**

EC2 optimization:
- On-demand to spot: 70% savings
- $22,000 x 30% = $6,600/month (down from $22,000)
- Risk 1: spot interruption mid-job → use checkpointing
- Risk 2: spot capacity unavailable in one AZ → use Spot Fleet across 3 AZs
- Risk 3: long-running jobs harder to checkpoint → ephemeral clusters for each job

Checkpointing config:

```
spark.checkpoint.dir = s3://your-bucket/spark-checkpoints/
spark.sql.streaming.checkpointLocation = s3://your-bucket/streaming-checkpoints/
```

S3 lifecycle rules:
- 0-30 days: S3 Standard ($0.023/GB) — active pipeline data
- 30-90 days: S3 Intelligent-Tiering ($0.023/GB active, $0.0125/GB inactive)
- 90-365 days: S3 Standard-IA ($0.0125/GB)
- 365+ days: S3 Glacier Instant Retrieval ($0.004/GB)
- Estimated saving on $14,000: most data is cold → move to IA and Glacier
- Conservative estimate: $14,000 x 40% remaining = $5,600/month

CSV to Parquet:
- Storage reduction: 85% (from columnar compression + encoding)
- $14,000 storage x 15% = $2,100/month after conversion
- But above lifecycle policy applies to the compressed Parquet: $2,100 x 40% = $840/month
- Data transfer reduction: Parquet with predicate pushdown scans fewer bytes → less transferred
- Transfer: $9,000 x 50% reduction estimate = $4,500/month

Revised monthly estimate:

| Category | Before | After | Savings |
|---|---|---|---|
| EC2 compute | $22,000 | $6,600 | $15,400 |
| S3 storage | $14,000 | $840 | $13,160 |
| Data transfer | $9,000 | $4,500 | $4,500 |
| **Total** | **$45,000** | **$11,940** | **$33,060** |

Result: $11,940/month — under the $15,000 target.

---

## 4. Quick Reference Card

This section is for active use during interviews.
Refer to these tables when you need to give a precise number,
make a technology recommendation, or explain a tradeoff.

---

### Batch vs Stream Decision Tree

| Question | If YES, then... |
|---|---|
| Is result needed in < 1 minute? | Stream |
| Is input data bounded (finite dataset)? | Batch |
| Do you need to process full historical data? | Batch |
| Is an event-driven action required immediately? | Stream |
| Do you need both accuracy over history and real-time? | Lambda or Kappa |
| Is streaming complexity justified by the latency requirement? | Only if SLA < 5 minutes |
| Can a nightly cron job solve this? | Yes → use batch |

---

### Spark Configuration Reference

| Config | Default | When to Change |
|---|---|---|
| `spark.sql.shuffle.partitions` | 200 | Increase for datasets > 1 TB. Rule of thumb: 1 partition per 128 MB of shuffled data |
| `spark.sql.adaptive.enabled` | true (Spark 3+) | Always keep enabled |
| `spark.sql.adaptive.skewJoin.enabled` | true (Spark 3+) | Always keep enabled |
| `spark.sql.adaptive.coalescePartitions.enabled` | true (Spark 3+) | Always keep enabled |
| `spark.sql.autoBroadcastJoinThreshold` | 10 MB | Increase for larger dimension tables (up to ~1/10 of executor memory) |
| `spark.executor.memory` | 1g | 4-8g for typical workloads |
| `spark.executor.cores` | 1 | 4-5 for typical workloads |
| `spark.executor.memoryOverhead` | 10% of executor memory | Increase to 20-25% for jobs with heavy UDFs or Python |
| `spark.checkpoint.dir` | not set | Set to S3 path when using spot instances |

---

### Key Numbers for Interviews

| Fact | Value | Source |
|---|---|---|
| CSV to Parquet storage reduction | ~85% | Uber engineering report |
| BigQuery cost | $5 per TB scanned | GCP pricing |
| Spot instance savings vs on-demand | 60-80% | AWS Spot pricing |
| Broadcast join default threshold | 10 MB | Spark default |
| Optimal Spark partition size | 128 MB to 1 GB | Spark tuning guide |
| Data skew alert threshold | Any key > 5% of partition data | Rule of thumb |
| Compaction trigger threshold | avg file size < 10 MB AND file count > 1,000 | Databricks best practices |
| GDPR deletion SLA | 30 days ("without undue delay") | GDPR Article 17 |
| PostgreSQL WAL default retention | 24 hours | PostgreSQL default |
| Kafka default log retention | 7 days | Kafka default |

---

### CDC Method Comparison

| Method | Captures DELETEs? | Load on Source DB | Clock Skew Risk | Recommended for Production? |
|---|---|---|---|---|
| WAL-based (Debezium) | Yes | None (reads WAL) | No | Yes — preferred |
| Timestamp-based | No | Yes (query at extraction) | Yes | No — avoid for critical data |
| Trigger-based | Yes | High (triggers on every write) | No | No — avoid |
| Full extract | Yes (by snapshot comparison) | Very high | No | Only for small tables < 1M rows |

---

### Data Quality Severity Thresholds

| Metric | Threshold | Action |
|---|---|---|
| Null rate on primary key | < 0.1% | Log warning |
| Null rate on primary key | 0.1% to 5% | Quarantine bad records, alert |
| Null rate on primary key | > 5% | Fail pipeline, page on-call |
| Row count vs yesterday | > 30% deviation | Alert |
| Row count vs yesterday | > 50% deviation | Fail pipeline |
| Revenue reconciliation discrepancy | > 0.1% | Escalate to finance |
| Duplicate rows in output | Any | Fail pipeline |
| Schema mismatch | Any column missing | Fail pipeline |

---

### Lambda vs Kappa Comparison

| Dimension | Lambda | Kappa |
|---|---|---|
| Number of codebases | 2 (stream + batch) | 1 (stream only) |
| Historical reprocessing | Easy (replay from data lake) | Hard (limited by Kafka retention) |
| 2-year historical lookback | Easy | Requires S3 archive + replay |
| Ops overhead | Higher | Lower |
| Code duplication | High | Low |
| When to choose | Long history needed, Spark expertise | Short history, Flink-native team |
| Common mistake | Over-engineering Lambda from day 1 | Underestimating Kafka retention cost |

---

### Cost Optimization Priority Order

Rank these in order of ROI before doing anything else.

1. On-demand to spot instances (EC2): 60-80% compute savings
2. CSV to Parquet conversion: 85% storage savings, faster reads
3. S3 lifecycle policies: 70-90% savings on cold data
4. Partition pruning and clustering (warehouse): reduces scanned bytes
5. Ephemeral clusters (terminate after job): eliminates idle cost
6. Materialized views (warehouse): reduces repeated full scans
7. Query result caching: reduces redundant scans for dashboards
8. Compaction (small files): reduces read cost, not directly storage

---

### Pipeline Monitoring — Metrics to Alert On

| Metric | Alert Threshold | Severity |
|---|---|---|
| Job duration | > 2x historical average | Warning |
| Job duration | > 3x historical average | Page on-call |
| Data freshness | SLA window exceeded | Page on-call |
| Row count | > 30% deviation from 7-day average | Warning |
| Row count | > 50% deviation | Page on-call |
| Error rate | > 1% | Warning |
| Debezium consumer lag | > 30 minutes | Warning |
| Debezium consumer lag | > 12 hours | Page on-call |
| Kafka topic partition lag | > 100,000 messages | Warning |
| Avg Parquet file size | < 10 MB AND file count > 1,000 | Trigger compaction |

---

### Interview Red Flags to Avoid

These are the answers that immediately signal L4 thinking in an L6 interview.

Do not say these things:

- "We'll just use Kafka for everything."
  Replace with: "Kafka for event-driven workloads where latency matters. Batch for
  analytical workloads where latency of hours is acceptable."

- "We'll fix the data quality issues later."
  Replace with: "Data quality is validated at ingestion, at transformation, and
  at load. Bad records are quarantined. Downstream consumers are protected by SLAs."

- "Just add more Spark nodes."
  Replace with: "First diagnose the bottleneck. Data skew, small files, and memory
  pressure each have different fixes. Adding nodes only helps resource bottlenecks."

- "We can rerun the pipeline if something goes wrong."
  Replace with: "The pipeline is idempotent by design. Rerunning always produces
  the same result. Partition overwrite, not append."

- "Lambda architecture is the most robust."
  Replace with: "Lambda has two codebases and double the operational overhead. Start
  with Kappa if the reprocessing window fits Kafka retention. Add batch only when needed."

- "Use timestamp-based CDC to reduce load on the source DB."
  Replace with: "WAL-based CDC (Debezium) has zero query load on the source.
  Timestamp-based CDC misses deletes and has clock skew risk. Do not use timestamps
  for financial or compliance-sensitive data."

---

*End of Chapter 35: Batch Processing and Data Pipelines.*

*This is the final section. All brainstorming questions and exercises are in Part D.*
# Supplemental Brainstorming: Chapters 35, 36, 37

---

## Supplemental Brainstorming: Chapter 35 -- Batch Processing

*Questions 21-40: Advanced topics and cross-chapter integration.*

---

### Section A: Advanced Batch Patterns (Q21-Q30)

---

**Question 21 -- Spark executor memory sizing**

Your Spark job is crashing with OutOfMemoryError on executors. The job reads 200GB of Parquet files, does a join between a 190GB fact table and a 10GB dimension table, and writes the result to S3. Your cluster has 20 executors, each with 16GB RAM allocated. Explain the breakdown of executor memory in Spark (heap vs off-heap, execution vs storage pools) and redesign the memory configuration to fix the crash.

- Spark splits executor memory into reserved memory (300MB fixed), user memory, Spark memory (execution + storage). The default Spark memory fraction is 60% of the remaining heap. Execution memory is used for joins, shuffles, aggregations. Storage memory is used for cached RDDs/DataFrames. They share a unified pool and evict each other.
- The 10GB dimension table is a candidate for broadcast join. Broadcasting avoids a shuffle entirely. With 20 executors and 200GB input, each executor reads ~10GB of Parquet. Partition count matters: if partitions are too large, execution memory overflows to disk (spill), then OOM.
- Increase executor memory to 24GB, set spark.executor.memoryFraction to 0.7, enable broadcast join for the 10GB dimension (spark.sql.autoBroadcastJoinThreshold = 12GB), and increase the number of partitions (spark.sql.shuffle.partitions = 400 instead of default 200).
- Follow-up: When would you move to off-heap memory (spark.memory.offHeap.enabled = true)? What workloads benefit, and what are the GC implications?

---

**Question 22 -- On-heap vs off-heap memory trade-offs**

You're running a Spark job that processes 500GB of user event data. The job runs on JVM-based executors and you're seeing frequent GC pauses (5-10 seconds every few minutes), causing task failures and speculative task re-executions. Explain the trade-off between on-heap and off-heap memory in Spark and decide whether off-heap is the right fix here.

- On-heap memory is managed by the JVM garbage collector. Large heaps (> 8GB) lead to long GC pauses because the GC must scan all live objects. Spark's Tungsten engine uses unsafe memory operations and compact binary encoding to reduce GC pressure even within the heap -- but the GC still applies.
- Off-heap memory (native memory outside JVM heap) bypasses GC entirely. Spark manages it manually via sun.misc.Unsafe. You enable it with spark.memory.offHeap.enabled = true and spark.memory.offHeap.size. This is useful for memory-intensive operations (sorts, aggregations) where GC becomes the bottleneck.
- The trade-off: off-heap reduces GC pauses but complicates memory management. Memory leaks can crash the JVM process permanently, not just pause it. You lose JVM crash dumps. Off-heap is best for stable, well-tested pipelines with predictable memory patterns.
- Follow-up: If GC is the bottleneck, what is the alternative to off-heap? (Smaller executor heaps with more executors, using G1GC with tuned region sizes, or switching to non-JVM runtimes like Arrow-based processing.)

---

**Question 23 -- Checkpointing in Spark Streaming vs Structured Streaming**

Your team has a Spark Streaming job (DStream API) that has been running for 6 months. It checkpoints state to HDFS every 30 seconds. A new team member says "just migrate it to Structured Streaming and use stateful operations." The manager says "the checkpoint formats are incompatible." Explain the checkpoint differences and the migration path.

- Spark Streaming (DStream) checkpoints serialize the entire DAG, including the DStream graph structure, RDD lineage, and operator state. The checkpoint is tightly coupled to the Spark version and the code structure. If you change the code (add a new transformation), the old checkpoint is invalid and the job must restart from scratch, losing state.
- Structured Streaming uses a different checkpoint format: a Write-Ahead Log of offsets plus state stored as versioned Parquet files (using RocksDB or in-memory state store). The checkpoint is decoupled from the query plan to some extent. Schema changes to state require explicit state schema migration.
- Migration path: you cannot reuse DStream checkpoints in Structured Streaming. Options: (1) drain the DStream job, let it finish processing all in-flight data, then start the Structured Streaming job from the current Kafka offset. Accept a small state loss or re-derive state from the batch layer. (2) Run both in parallel during a transition window.
- Follow-up: In Structured Streaming, what happens to state when you do a rolling deployment that changes the schema of your stateful operator? How does Spark handle backward compatibility of the state store?

---

**Question 24 -- Delta Lake ACID transactions on a data lake**

Your team writes to S3-based data lake from multiple Spark jobs running concurrently: a nightly batch job that writes daily summaries, an hourly incremental job that appends new rows, and an ad-hoc job that fixes bad rows. Without a transactional layer, you are seeing corrupted reads mid-write. Design a solution using Delta Lake.

- S3 is not a transactional store. Concurrent writers can produce partial writes visible to readers. The "S3 eventual consistency" issue (now largely resolved with strong consistency) was historically a problem, but concurrent multi-writer issues remain because there is no locking mechanism native to S3.
- Delta Lake adds a transaction log (_delta_log directory) that records every operation as a JSON commit file. Writers use optimistic concurrency: they read the current log version, write their data files, then attempt to commit by writing a new log entry. If two writers try to commit the same version, the loser retries or fails with a conflict error.
- Concurrent readers always see a consistent snapshot because they read from a committed log version. Time travel queries read older log versions. The nightly batch, hourly append, and ad-hoc fix job each get serialized through the log, preventing partial-write visibility.
- Follow-up: Apache Iceberg also provides ACID transactions on object stores. Compare Delta Lake vs Iceberg for: (a) engine compatibility (Spark, Flink, Trino), (b) schema evolution support, (c) partition evolution support. Which would you pick for a multi-engine data lake?

---

**Question 25 -- Data quality validation at pipeline ingestion**

Your batch pipeline ingests 10 million user event rows nightly from an upstream team's S3 bucket. Last month, an upstream schema change caused 3 days of bad data to be loaded into your warehouse before anyone noticed (a nullable field was made non-nullable upstream, silently corrupting joins). Design a data quality gate at ingestion.

- The first layer is schema validation: compare the incoming Parquet schema against the expected schema contract (field names, types, nullability). Any schema mismatch should halt the pipeline before any data is written to the downstream warehouse. Tools: Great Expectations, Deequ (AWS), or custom schema registry checks.
- The second layer is statistical validation: check row counts (is today's file within +/- 20% of the 30-day rolling average?), null rates per column, value range checks (no negative user IDs, no timestamps in the future), and referential integrity checks (all user_id values exist in the user dimension table).
- The third layer is anomaly detection on derived metrics: if the pipeline produces aggregates (daily active users, revenue), compare the new values against historical trends using z-score or median absolute deviation. A sudden 40% drop in DAU signals a data quality problem, not a product change.
- Follow-up: Where do you store validation results? How do you notify on-call automatically? How do you handle a "quarantine and continue" strategy where bad rows are isolated but the pipeline continues with good rows?

---

**Question 26 -- Pipeline observability in Airflow/Prefect**

Your Airflow DAG runs 47 tasks across a 6-hour nightly pipeline. Last week it failed silently: tasks appeared green, but S3 outputs were empty because the Spark job succeeded with zero rows processed (a filter bug). Design the observability layer for this pipeline.

- Task-level success/failure is not sufficient observability. You need output validation as a distinct task step: after each Spark job writes to S3, a lightweight validation task checks that the output path exists, the file count is non-zero, and the row count is within expected range. This validation task blocks downstream tasks from running if it fails.
- SLA monitoring: track expected completion time per task and per DAG run. Airflow has built-in SLA miss alerts. Set the SLA for the full DAG to 5.5 hours; if it is not done by 5:30 AM, send an alert so the on-call can investigate before business hours start.
- Lineage and audit: emit structured logs from each task (task name, start time, end time, rows read, rows written, input paths, output paths). Push these to a central observability store (BigQuery table or OpenTelemetry-compatible backend). This lets you trace which task processed which data, and replay any task with the exact same inputs.
- Follow-up: How do you monitor the cost of each DAG run over time? If a Spark task that used to cost $12 now costs $80, you want to know immediately. What metric do you capture, and where?

---

**Question 27 -- Cost of Spark jobs: spot instances and shuffle cost**

Your team runs a daily Spark batch job on AWS EMR using 50 on-demand r5.4xlarge instances for 4 hours. The monthly cost is around $14,000. Your manager asks you to cut this by 60%. Design a cost optimization strategy covering spot instances, shuffle optimization, and right-sizing.

- Spot instances cost 60-90% less than on-demand but can be interrupted with 2-minute warning. EMR supports mixed fleets: use on-demand for the master node and task-critical core nodes, and spot for task nodes (which can be interrupted without data loss since they do not store HDFS data). A 70% spot / 30% on-demand mix gives 50-60% savings with low interruption risk for most jobs.
- Shuffle is the most expensive Spark operation. Each shuffle stage writes all intermediate data to disk and then re-reads it across the network. Minimize shuffles by: using broadcast joins for small tables, pre-partitioning input data to match the join key (partition pruning), and using sort-merge join with pre-bucketed tables. Shuffle cost is both time cost and I/O cost on spot instances (interrupted mid-shuffle = wasted work).
- Right-sizing: profile the job to find the actual CPU and memory utilization. If executors use 8GB of their 16GB allocation, halve the executor memory and double the number of executors on smaller instances. Compute-optimized instances (c5) may be cheaper than memory-optimized (r5) if the job is not memory-bound.
- Follow-up: Calculate the exact cost. 50 x r5.4xlarge on-demand = $1.008/hr each = $50.40/hr x 4 hours = $201.60/day = $6,048/month. (The $14K figure implies the job runs twice daily or the instance count is higher -- work through the math.) With 70% spot at $0.22/hr per instance, what is the new monthly cost?

---

**Question 28 -- Incremental processing vs full reprocessing**

Your nightly Spark batch job does a full table scan of 2TB of S3 data to compute daily aggregates. The data grows by 20GB per day. In 6 months, the full scan will take 8 hours, exceeding your overnight batch window. Design the transition to incremental processing and explain when full reprocessing is still necessary.

- Incremental processing reads only the new data since the last successful run. This requires: (1) a reliable watermark or cursor (last processed partition date, last Kafka offset, last modified timestamp), (2) the ability to merge incremental results into the existing aggregate table (upsert, not just append), and (3) idempotent writes so a retry does not double-count.
- Delta Lake or Iceberg makes incremental writes safe: use MERGE INTO to upsert new aggregates into the existing table. Partition the S3 data by date so Spark only reads the new date partitions (partition pruning eliminates the full table scan). Processing 20GB per day instead of 2TB is a 100x reduction in scan cost.
- Full reprocessing is still necessary in these cases: (a) a bug is found in the aggregation logic that affected historical data, (b) a new dimension is added that requires recomputing all historical records, (c) late-arriving data older than the incremental window must be incorporated. Design a backfill mechanism that can reprocess date ranges in parallel: partition the historical range into chunks, run each chunk as a separate Spark job, and merge results.
- Follow-up: How do you handle late-arriving events in incremental processing? If an event from 3 days ago arrives today, which partition does it land in, and how do you recompute the 3-day-old aggregate without reprocessing everything?

---

**Question 29 -- Data lineage tracking in batch pipelines**

Your organization has 200 Spark batch jobs running across 15 pipelines. A data engineer changed a transformation in pipeline #4 two weeks ago. Now a finance report is showing wrong numbers. No one knows which pipeline feeds which report. Design a data lineage system for the organization.

- Column-level lineage: for each Spark job, capture which input columns are read and which output columns are derived from them. Spark's query execution plan (the DAG of transformations) encodes this information. Tools like Apache Atlas, DataHub, or OpenLineage can instrument Spark to emit lineage events automatically with each job run.
- Dataset-level lineage: emit an event for each job run that records: job ID, run timestamp, input datasets (S3 paths or table names + snapshot versions), output datasets, and row counts in/out. Store these events in a graph database or lineage store. This lets you traverse: "which jobs read from table X?" and "which reports depend on job Y's output?"
- Impact analysis: when a schema change or transformation change happens, the lineage graph lets you answer "what is downstream of this dataset?" before making the change. This is the key use case: the finance report is a node in the graph, and you can trace back through the lineage to find which upstream job introduced the bad transformation.
- Follow-up: OpenLineage is an open standard for lineage events. How would you integrate it with Airflow (which has a built-in OpenLineage plugin) and with Spark (using the openlineage-spark listener jar)? What does a lineage event look like in JSON?

---

**Question 30 -- Schema drift handling in batch pipelines**

Your batch pipeline ingests JSON files from 12 upstream microservices into a Spark job that writes to a Parquet-based data warehouse. Three times in the past year, an upstream service added new fields or changed field types, breaking the Spark job. Design a schema drift handling strategy.

- Schema drift happens when the actual data structure diverges from the expected schema. In Spark, if you specify an explicit schema (StructType) and the incoming JSON has extra fields, those fields are dropped silently. If a field changes type (string to integer), Spark throws a runtime error. Both outcomes are bad: silent data loss and crashes.
- The correct approach has three layers: (1) Schema detection -- infer the schema of each incoming batch and compare it against the registered schema in a schema registry (or a stored StructType in your metastore). Alert on drift before processing begins. (2) Evolution rules -- allow additive changes (new nullable fields) automatically, require manual approval for breaking changes (field removals, type changes). (3) Schema versioning -- store the schema version alongside each Parquet partition so downstream consumers know which version to expect.
- For additive drift specifically: use Spark's mergeSchema option when reading Parquet (spark.read.option("mergeSchema", "true")). This allows new columns to be added without breaking the job. New columns appear as nulls in partitions that do not have them. This is safe for additive-only drift.
- Follow-up: How do you handle a non-additive change (a field renamed from user_id to userId)? You cannot use mergeSchema. You need a transformation layer that normalizes field names before writing to the warehouse. How do you make this transformation layer configurable rather than hardcoded?

---

### Section B: Cross-Chapter Integration (Q31-Q40)

---

**Question 31 -- Ch35 + Ch28: Separating batch reads from the production DB**

Your nightly Spark batch job reads 500 million rows from a PostgreSQL production database using JDBC and writes the results to S3. The read alone takes 3 hours and causes CPU and I/O spikes on the production DB, degrading response times for live users between 2 AM and 5 AM. Design the architecture to separate batch reads from operational queries.

- The root problem is that the batch job competes with the operational workload for the same DB resources. The cleanest fix is read replicas: PostgreSQL supports streaming replication to one or more standby replicas. Point the Spark JDBC connection at a dedicated read replica. This offloads all batch I/O from the primary.
- Even on a read replica, a 500M-row JDBC read without partitioning is a single sequential scan. Spark's JDBC source can parallelize reads using partitionColumn, lowerBound, upperBound, and numPartitions. Partition by a monotonically increasing ID column and set numPartitions = 50. Each Spark executor reads a range of IDs in parallel, reducing wall clock time.
- A better long-term architecture is CDC (Change Data Capture) using Debezium. Debezium streams every row change from PostgreSQL binlog to Kafka. The batch job reads from Kafka or from an S3 sink (Kafka Connect S3 sink). The production DB is never touched by batch jobs. The batch job always reads from the event stream, which is decoupled from DB load.
- Follow-up: The read replica has a replication lag of 45 seconds. Does this matter for your nightly batch? At what point does replication lag become a problem for batch jobs, and how do you detect it?

---

**Question 32 -- Ch35 + Ch30: Schema evolution in Avro files from Kafka S3 sink**

Your Spark batch pipeline reads Avro files from a Kafka S3 sink connector. The upstream service changed its schema: the field user_country was renamed to user_region and the type changed from a two-letter ISO code (string) to an enum. Avro schema resolution rules apply. Design how Spark handles this without a full pipeline rewrite.

- Avro schema resolution compares the writer schema (the schema used when the file was written) against the reader schema (the schema the consumer expects). Renaming a field is not backward compatible by default, but Avro supports aliases: if you add user_country as an alias for user_region in the new schema, the Avro reader can map the old field name to the new one during deserialization.
- The schema registry is critical here. Confluent Schema Registry (or AWS Glue Schema Registry) stores every version of the schema. Each Avro file written by the Kafka S3 sink includes the schema ID in its header. When Spark reads the file, it fetches the writer schema by ID from the registry and applies schema resolution rules against the current reader schema.
- The type change from string to enum is a separate problem. Avro allows promotion (int to long, float to double) but string-to-enum is not a standard promotion. You need a transformation step: read the raw string value, map it to the new enum values, and write the result. This transformation layer is isolated in a Spark UDF or a map transformation that is versioned alongside the schema change.
- Follow-up: What is the difference between backward compatibility (new reader can read old data) and forward compatibility (old reader can read new data) in Avro? Which one does a Kafka consumer need, and why?

---

**Question 33 -- Ch35 + Ch33: Reprocessing after a streaming bug corrupted 3 days of data**

You have a Lambda architecture: Kafka + Flink for near-real-time aggregations, and Spark for nightly full reprocessing. A bug in the Flink stream layer caused incorrect aggregations for the past 3 days. The Flink output tables are wrong. Spark's batch job runs nightly and overwrites the same output tables. Design the reprocessing strategy and explain how users see accurate data while reprocessing is in progress.

- The Spark batch job is the source of truth in Lambda architecture. The fix is to trigger an out-of-schedule Spark reprocess job that covers the 3 affected days. Spark reads the raw events from Kafka (which retains events for 7 days by default) or from the S3 raw event archive, recomputes the correct aggregations, and overwrites the output tables.
- During reprocessing (which may take 4-6 hours), users querying the output tables see stale or incorrect data. To avoid this, use a blue/green table approach: the Spark reprocess job writes to a shadow table (_reprocess suffix). Once validation passes, atomically swap the shadow table to become the live table (rename in the metastore). Users see either the old (incorrect) data or the new (correct) data, never a mix.
- The Flink bug must be fixed before reprocessing begins, otherwise Flink will overwrite the corrected batch output with fresh incorrect streaming aggregations. Options: (a) pause Flink during reprocessing and restart from the latest Kafka offset after Spark finishes, (b) switch to serving only from the batch layer (batch-only mode) while the fix is validated, then re-enable Flink.
- Follow-up: Kafka retains data for 7 days. The bug was introduced 3 days ago, so you have the raw events. What if the bug had been running for 10 days and Kafka retention had expired? How do you recover?

---

**Question 34 -- Ch35 + Ch36: Regional Spark processing with global report merging**

Your Spark batch job processes global user events stored in S3 in us-east-1. EU regulations require that EU user events be processed only within EU infrastructure. Redesign the pipeline with regional processing. Explain how you merge EU and US results for global reports without EU data crossing the Atlantic.

- Deploy two independent Spark clusters: one in AWS eu-west-1 and one in aws us-east-1. Each cluster has its own S3 bucket in its region. EU user events are written to the eu-west-1 S3 bucket and processed by the EU Spark cluster. US (and other non-EU) user events are written to the us-east-1 bucket and processed by the US cluster. No EU raw event data ever leaves the EU region.
- Each regional cluster produces aggregated outputs. Aggregates (daily active users by country, revenue by SKU, conversion rates) are not personally identifiable information if constructed correctly. These aggregate outputs can cross regions without violating GDPR. The EU cluster writes its aggregate results to a cross-region S3 bucket accessible from us-east-1.
- A global merge job (runs in us-east-1 or in a neutral region) reads the US aggregates and the EU aggregates, combines them using union or join depending on the report structure, and writes the final global report. The global report contains no EU PII -- only aggregate numbers.
- Follow-up: Some global reports require user-level joins (e.g., find users who were active in both EU and US). You cannot send EU user_ids to the US for the join. What privacy-preserving technique allows cross-region user matching without transferring raw IDs? (Hash-based matching, PPRL -- Privacy Preserving Record Linkage.)

---

**Question 35 -- Ch35 + Ch37: Federated learning for recommendation model training under GDPR**

Your batch ML pipeline trains a recommendation model nightly on global user behavioral data stored in S3. A GDPR audit concludes that EU user behavioral data cannot be sent to the US for model training. Your current architecture centralizes all data in us-east-1 before training. Design a federated learning approach where training happens locally in each region and only gradient updates cross borders.

- Federated learning: instead of sending raw data to a central trainer, each regional node trains on its local data and sends only model gradient updates (not raw data) to a central aggregator. The central aggregator combines gradients using Federated Averaging (FedAvg) and distributes the updated global model back to each regional node.
- The EU Spark cluster trains on EU behavioral data locally in eu-west-1. It computes gradients and sends them to the US aggregator. The gradients are vectors of floating-point numbers (model weight updates) -- they contain no raw user data. The GDPR question is whether gradients are "personal data." Legal consensus: model gradients in aggregate are not personal data, but gradients from a single user's data could theoretically allow reconstruction of that user's data (gradient inversion attacks). Mitigate with differential privacy: add calibrated noise to gradients before sending them.
- Engineering: implement federated training using PySpark + custom gradient computation, or use a dedicated federated learning framework (TensorFlow Federated, PySpark with MLlib for gradient computation). The aggregator runs in us-east-1 or in a neutral region. Training rounds: each region does one epoch locally, sends gradients, receives updated weights, repeats.
- Follow-up: Federated learning typically produces a model with 2-5% lower accuracy than centralized training (non-IID data problem -- each region's data distribution is different). Is this acceptable for recommendation? What if EU users make up 40% of your training data -- how much accuracy loss do you expect?

---

**Question 36 -- Ch35 + Ch38: Spot instance checkpoint strategy for Spark on EMR**

Your weekly Spark batch job runs 200 spot instances (r5.2xlarge) for 6 hours. The spot interruption rate for r5.2xlarge in us-east-1 is approximately 10% per instance per hour. Calculate the expected cost, expected completion time with retries, and the expected number of interruptions. Then design the checkpoint strategy to minimize wasted work on interruption.

- Cost calculation: r5.2xlarge spot price ~$0.14/hr. 200 instances x $0.14/hr x 6 hours = $168. On-demand price: $0.504/hr. 200 x $0.504 x 6 = $604.80. Spot savings: ~72%. Expected interruptions: 10% per instance per hour x 200 instances x 6 hours = 120 expected interruption events across the job. Not all interruptions kill the job -- EMR task nodes can be replaced. Core nodes hold HDFS data and should use on-demand.
- Checkpointing strategy: Spark checkpoints RDD/DataFrame lineage and state to HDFS or S3. Set checkpoint interval to every 30 minutes of processing. On interruption, the job resumes from the last checkpoint, losing at most 30 minutes of work. Without checkpointing, the entire job restarts from scratch on any failure, wasting potentially 5 hours of work.
- Checkpoint location should be S3 (not HDFS on instance storage) because S3 survives instance terminations. Use S3 with server-side encryption. Set spark.checkpoint.dir to an S3 path. For structured streaming, checkpointing is built-in. For batch jobs, use RDD.checkpoint() at stage boundaries, or design jobs as sequential stages where each stage writes its output to S3 before the next stage reads it (natural checkpointing via stage outputs).
- Follow-up: EMR Graceful Decommission allows spot nodes to finish their current task before being terminated (Spark tasks drain before the instance is removed). How does this interact with the 2-minute spot interruption warning? Is 2 minutes enough to finish a typical Spark task?

---

**Question 37 -- Ch35 design synthesis: building a fault-tolerant global batch platform**

You are the lead architect for a company processing 50TB of event data daily. You have batch jobs for ML training, business intelligence aggregates, and data quality checks. Jobs run on AWS EMR in us-east-1, eu-west-1, and ap-southeast-1. Design the full batch platform: orchestration, compute, storage, data quality, lineage, and cost controls.

- Orchestration: Airflow deployed on managed MWAA (AWS Managed Workflows for Apache Airflow) in each region with a cross-region DAG hierarchy. Global DAGs coordinate regional DAGs. Each regional Airflow instance manages jobs in its region. Cross-region dependencies are handled via S3 sentinel files: a job in eu-west-1 polls for a success marker from us-east-1 before starting.
- Compute: EMR with mixed fleets (spot task nodes, on-demand core nodes). Auto-scaling based on job queue depth. Instance fleet with multiple instance types (r5.2xlarge, r5.4xlarge, m5.4xlarge) to maximize spot availability. Use EMR Serverless for ad-hoc jobs to eliminate cluster management overhead.
- Storage: S3 as the primary store, partitioned by region, date, and event type. Delta Lake for transactional write semantics. Cross-region replication of aggregates only (not raw events) to a global reporting bucket.
- Follow-up: How do you set a hard cost cap per job? If a job is projected to exceed $500 in EMR compute, it should alert and optionally stop. What Airflow mechanism or AWS service enables this?

---

**Question 38 -- Ch35 data quality synthesis: the end-to-end bad data scenario**

A downstream data science team builds a churn prediction model on data produced by your batch pipeline. After deploying the model, churn predictions are garbage. Investigation reveals that 40 days ago, your pipeline silently ingested a file where the event_type field values were corrupted (all values became "unknown"). This lasted for 3 days. The model trained on this corrupted data. Design the detection, correction, and prevention system.

- Detection failure analysis: the pipeline had no statistical validation on the event_type column. A correct validation would have checked: (a) the distribution of event_type values -- "unknown" appearing at 100% instead of the normal 0.1% is a 1000-sigma anomaly, (b) the cardinality of event_type -- normally 12 distinct values, now 1. Either check would have caught this on day 1.
- Correction: use Delta Lake time travel to restore the 3 affected partitions to their state before the bad data was ingested. If the raw source files still exist, re-ingest them. Retrain the model on the corrected data. Mark the model trained on corrupted data as deprecated in the ML model registry and roll back to the last clean version.
- Prevention: add a mandatory data quality gate task to the Airflow DAG. This task runs Great Expectations checks: event_type must appear in a fixed allowed list, the null rate for event_type must be less than 1%, the "unknown" rate must be less than 0.5%. If the gate fails, the job stops and alerts. No downstream tasks run. The gate is not optional.
- Follow-up: The 3-day corruption window was 40 days ago. Your ML model was trained 2 weeks ago using the already-corrupted data. How do you audit every model trained in the past 60 days for data quality issues? What does your model training lineage system need to support this?

---

**Question 39 -- Ch35 + Ch33 synthesis: unified Lambda architecture with quality guarantees**

You are serving a real-time dashboard (Flink aggregates) and a historical analytics page (Spark batch aggregates) from the same data. The Lambda architecture means users sometimes see different numbers on the real-time vs historical views for the same time window. Design the reconciliation mechanism and the user experience for the "eventual consistency" of these two views.

- The discrepancy comes from two sources: (1) late-arriving events that Flink has not yet processed but Spark's nightly reprocess has incorporated, (2) different aggregation logic between the Flink job and the Spark job (a bug or intentional difference). Reconciliation requires: identical aggregation logic enforced by a shared library (the same UDF code runs in both Flink and Spark), and a serving layer that knows which view to serve for which time window.
- Serving strategy: for time windows within the last 2 hours, serve Flink aggregates (most current). For time windows older than 24 hours, serve Spark batch aggregates (reconciled, includes late arrivals). For the 2-24 hour window, serve Flink aggregates with a visual indicator ("approximate, updating") so users know the numbers may shift.
- Kappa architecture alternative: eliminate the batch layer entirely. Run Flink over the full historical Kafka log to recompute any time window. This removes the dual-system complexity. The trade-off is that historical reprocessing in Flink is slower than Spark and requires Kafka to retain data indefinitely (which is expensive -- use tiered storage).
- Follow-up: A user sees a revenue number of $1,247,382 on the real-time dashboard at 3 PM. At 9 AM the next day, the historical view shows $1,251,103 for the same day. The $3,721 difference represents late-arriving transactions. How do you explain this to a non-technical business stakeholder in a way that builds trust rather than confusion?

---

**Question 40 -- Ch35 synthesis: the 3 AM pipeline failure**

Your nightly batch pipeline is supposed to finish by 4 AM so reports are ready for business users at 8 AM. At 3:15 AM, PagerDuty wakes you up: the pipeline has been running for 6 hours (started at 9 PM) and is stuck at 67% completion. The Airflow dashboard shows one task in "running" state for 4 hours with no progress. Walk through the diagnosis and the incident response.

- Diagnosis step 1: check the Spark driver logs for the stuck task. Look for: executor heartbeat timeouts (indicates lost executors), shuffle fetch failures (network partition or spot interruption killed executor holding shuffle data), OOM errors in executor logs, and whether the task is actually running (producing output bytes) or blocked (zero output for 4 hours).
- Diagnosis step 2: check the EMR cluster health. Are all executors alive? Did any spot instances get reclaimed? Check the Spark UI (available on port 18080 of the master node) for the stage/task breakdown. A single skewed partition (one partition with 10x more data than others) can cause one task to run for hours while all others finish in minutes. This is the most common "stuck at 67%" cause.
- Response: if it is data skew, kill the job and restart with increased parallelism on the skewed stage (spark.sql.shuffle.partitions from 200 to 800, or use salting on the skew key). If it is a lost executor, the job should self-recover via Spark's task retry mechanism -- but if it does not, kill and restart from the last S3 stage checkpoint. Communicate an updated ETA to stakeholders.
- Follow-up: The reports are not ready by 8 AM. Business users are waiting. What is the degraded-mode service you can provide? Can you serve yesterday's report with a "data as of yesterday" label? How do you automate this fallback?

---

