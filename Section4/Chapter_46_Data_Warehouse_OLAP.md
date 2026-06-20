# Chapter 41c: Data Warehouse & OLAP — BigQuery / Redshift / Snowflake

> OLTP answers "did this transaction succeed?" in milliseconds.
> OLAP answers "what was our revenue by product category last quarter?" in seconds.
> They are completely different systems. Using your OLTP database for analytics
> is the most common data architecture mistake, and knowing why is an L6 signal.

---

## STATUS: STUB — Full chapter coming

---

## Why This Chapter Matters

Data warehouse design is increasingly expected at L6 for backend roles, not just
data engineers. Questions like "how do you design an analytics system for 1B events/day"
or "how does BigQuery run a query across 10PB" appear at Google, Meta, Amazon, Stripe,
and Airbnb. The columnar storage model and MPP query execution are the key ideas.

---

## Planned Content

### Part 1: OLTP vs. OLAP — The Fundamental Distinction
- OLTP: row-oriented, high write throughput, point queries, small result sets
- OLAP: column-oriented, read-heavy, full table scans, aggregations over billions of rows
- Why OLTP DBs fail for analytics: scanning 1B rows in a row-oriented DB = reading
  every column even if you only need 2 of 50
- The insight: analytics queries read few columns, many rows → columnar storage is 10-100x faster

### Part 2: Columnar Storage
- Row storage: [id, name, price, date, qty] stored together per row
- Column storage: all ids together, all prices together, all dates together
- Analytics query "SELECT SUM(price) WHERE date > 2024": reads only 2 column files,
  skips 48 others → 96% less I/O
- Compression: same-type data compresses far better (run-length encoding on sorted columns)
- Parquet: the standard open columnar format (used by BigQuery, Redshift Spectrum, Spark)
- ASCII diagram: row storage vs. columnar storage layout

### Part 3: Star Schema and Dimensional Modeling
- Fact table: the central table of measurable events (orders, clicks, transactions)
  - High row count (billions), append-only, immutable
- Dimension tables: descriptive context (users, products, dates, locations)
  - Lower row count (millions), slowly changing
- Star schema: fact table at center, dimension tables as satellites
- Snowflake schema: normalized dimension tables (trade-off: more joins, less storage)
- Why this matters: query planner can skip entire dimension tables via predicate pushdown

### Part 4: MPP Query Execution (Massively Parallel Processing)
- BigQuery/Redshift: distribute data across hundreds of worker nodes
- Query coordinator: parses SQL, creates query plan, distributes to workers
- Each worker: scans its partition of the data, applies filters, aggregates locally
- Shuffle: for GROUP BY and JOIN, redistribute data by the grouping/join key
- Final aggregation: coordinator merges partial results from all workers
- Dremel (BigQuery's engine): columnar + nested data + petabyte scale
- ASCII diagram: MPP query execution across worker fleet

### Part 5: Partitioning and Clustering
- Partitioning: divide table into physical partitions by a column (usually date)
  → query with WHERE date = '2024-01' only scans that partition (partition pruning)
- Clustering (sort order): within each partition, data sorted by a column
  → queries filtering by clustered column skip chunks via min/max metadata
- BigQuery: TABLE PARTITION BY DATE(created_at) CLUSTER BY user_id
- Partition pruning + clustering = the two biggest query performance levers

### Part 6: ETL / ELT Pipelines
- ETL: Extract → Transform → Load (transform before loading)
- ELT: Extract → Load → Transform (load raw, transform inside warehouse)
- Modern trend: ELT (storage is cheap; transform in warehouse using SQL)
- Tools: dbt (transform), Fivetran/Airbyte (extract + load), Airflow (orchestrate)
- Incremental vs. full refresh: for large tables, only process new/changed rows
- Real incident: Airbnb 2019 — full refresh of a 10TB fact table ran daily,
  consuming $50K/month in BigQuery compute; switched to incremental → $3K/month

### Part 7: BigQuery vs. Redshift vs. Snowflake
| Dimension | BigQuery | Redshift | Snowflake |
|-----------|----------|----------|-----------|
| Architecture | Serverless, auto-scale | Fixed cluster, manual scale | Virtual warehouses, auto-scale |
| Storage | Separated (GCS) | Coupled (local disk) | Separated (S3/Azure/GCS) |
| Pricing | Per query (TB scanned) | Per hour (cluster size) | Per credit (compute) |
| Best for | Sporadic large queries | Steady high-throughput | Flexible multi-cloud |
| Proprietary format | Yes (Capacitor) | Yes (internal) | Yes (micro-partitions) |

### Part 8: Real-Time Analytics
- Lambda architecture: batch layer (warehouse) + speed layer (streaming) + serving layer
- Kappa architecture: streaming only, replay for historical (Kafka as source of truth)
- HTAP (Hybrid Transactional/Analytical): same system for OLTP + OLAP
  - TiDB, AlloyDB, Spanner — emerging but trade-offs in both dimensions
- Materialized views: pre-compute common aggregations, refresh on schedule or on write

### Part 9: Interview Framework
- Key distinction to establish first: this is analytics (OLAP), not transactions (OLTP)
- Recommend columnar storage + MPP immediately, explain why
- Design choices: BigQuery for GCP, Redshift for AWS, Snowflake for multi-cloud
- Data model: fact + dimension tables (star schema)
- Pipeline: raw events → Kafka → stream processor → data warehouse (ELT pattern)
- L5 vs. L6: L5 says "use BigQuery"; L6 explains columnar storage, partition pruning,
  MPP execution, and why the ETL pipeline design matters as much as the warehouse choice

---

## The One-Sentence Summary

> "Data warehouse = columnar storage (read only the columns you need, 10-100x less I/O) + MPP execution (distribute query across hundreds of workers) + star schema (fact + dimension tables) + partition pruning (only scan relevant date partitions) — the question 'how do you analyze 1B events/day' is answered by this stack, not by running SQL on your OLTP database."

---

*Full chapter: ~2,500 lines. Pairs with Ch35 (Batch Processing) and Ch41a (ML System Design).*
