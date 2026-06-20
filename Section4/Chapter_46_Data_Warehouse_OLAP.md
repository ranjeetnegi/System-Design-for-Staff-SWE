# Chapter 46: Data Warehouse / OLAP — BigQuery, Redshift, Snowflake

> OLTP answers "did this transaction succeed?" in milliseconds.
> OLAP answers "what was our revenue by product category last quarter?" in seconds.
> They are completely different systems. Using your OLTP database for analytics
> is the most common data architecture mistake, and knowing *why* they are different
> is an L6 signal that separates candidates who have just used a warehouse from
> candidates who understand how one works.

---

## Why This Chapter Matters

Every company above a certain size — say, a few million dollars in revenue or a few
million users — eventually runs into the same wall: their Postgres or MySQL database
starts choking when the data science team runs reports. The fix is not "buy a bigger
Postgres instance." The fix is understanding why row-oriented transactional databases
are structurally wrong for analytical queries, and building a system that is right.

Data warehouse design appears in L6 interviews at Google, Meta, Amazon, Stripe, Airbnb,
DoorDash, and Uber in multiple forms: "design an analytics platform for 1 billion events
per day," "how does BigQuery scan 10 petabytes in seconds," "how do you model your data
for a business intelligence tool," or "what is the difference between a data lake and a
data warehouse." This chapter gives you the full mental model.

---

## The Mental Model Before We Start

Imagine a library. In a transactional library (OLTP), librarians constantly check books
in and out — thousands of small operations per minute. Each operation touches one book
record at a time. Speed = fast lookups of individual items.

In an analytical library (OLAP), a researcher walks in and asks: "Across all 10 million
books checked out last year, what was the average checkout duration, broken down by
genre and month?" This question touches millions of records, reads only a few pieces of
information from each (checkout date, return date, genre), and aggregates the results.
These are completely different workloads. Building one system to do both well is like
designing a Formula 1 car that also hauls cargo — you get a mediocre version of both.

---

## Part 1: OLTP vs. OLAP — The Fundamental Distinction

### 1.1 What OLTP Actually Does

OLTP stands for Online Transaction Processing. This is your everyday database: Postgres,
MySQL, Oracle, SQL Server. When a user places an order on Amazon, that order gets written
to a database. When they check their order status, the database returns that specific row.
When the warehouse confirms shipment, another update touches that row.

The key characteristics of OLTP workloads:

- **Many small operations**: thousands to millions per second at scale
- **Short transactions**: read or write a few rows, commit, done
- **Random access**: queries use index lookups to find specific rows by primary key
- **Mix of reads and writes**: roughly equal, or write-heavy
- **Latency-sensitive**: users are waiting — responses need to come back in under 100ms
- **Correctness-critical**: ACID properties (Atomicity, Consistency, Isolation, Durability)
  are non-negotiable

The data model is normalized: users table, orders table, products table, with foreign keys
between them. Normalization reduces redundancy so that when a product's name changes, you
update it in one place.

### 1.2 What OLAP Actually Does

OLAP stands for Online Analytical Processing. This is your data warehouse: BigQuery,
Redshift, Snowflake. When a data analyst asks "what was our revenue by product category
for each month of last year, broken down by country, for customers who signed up before
2022," that query might touch 500 million rows in the orders table.

The key characteristics of OLAP workloads:

- **Few large queries**: tens to thousands per day, not millions per second
- **Long scans**: a single query might scan billions of rows
- **Aggregations**: SUM, COUNT, AVG, GROUP BY over entire datasets
- **Read-heavy**: rarely write, and when you do it's bulk inserts not random updates
- **Latency-tolerant**: analysts wait seconds or minutes, not milliseconds
- **Correctness still matters** but eventual-consistency is often acceptable

The data model is denormalized (or uses a star schema, explained later): redundancy is
okay because reads dominate and storage is cheap.

### 1.3 The 1-Billion-Row Problem

Let's make this concrete. You have a table called `orders` with 1 billion rows and
50 columns: order_id, user_id, product_id, category, created_at, shipped_at,
delivered_at, status, price, quantity, discount, tax, shipping_cost, country, city,
device_type, referral_source, payment_method, ... and 31 more columns.

An analyst wants to run this query:

```sql
SELECT
    category,
    DATE_TRUNC('month', created_at) AS month,
    SUM(price * quantity) AS revenue
FROM orders
WHERE created_at >= '2024-01-01'
    AND country = 'US'
GROUP BY category, month
ORDER BY month, revenue DESC;
```

This query only cares about 4 columns out of 50: `category`, `created_at`, `price`,
`quantity`, and the filter column `country`.

**In a row-oriented OLTP database (Postgres):**

Each row is stored as a contiguous block of bytes on disk. To read `price` for a
row, you must read the entire row: all 50 columns of data. Even if each row is only
500 bytes, 1 billion rows = 500 GB of data you must scan off disk. You're reading 92%
of that data (the 46 columns you don't need) just to throw it away.

Even with an index on `created_at`, the query returns millions of rows (all orders in
the US in 2024). Index scans are efficient for lookups returning a tiny fraction of
rows. When you're returning millions of rows, a full table scan is often faster than
jumping around on disk following index pointers. Postgres will choose the sequential
scan.

**In a column-oriented analytical database (BigQuery):**

Each column is stored separately. The `price` column for all 1 billion rows is one
file. The `quantity` column is another file. The database reads only the 4 files
(columns) needed for this query. With compression (explained in Part 2), those 4
columns might be only 8 GB total, versus 500 GB for the full row-oriented table.

That is a 62x reduction in data read. Less data read = faster query = lower cost.

```
Row-oriented storage — reading one column requires reading all columns:
┌─────────────────────────────────────────────────────────────────────────┐
│ Row 1: [order_id|user_id|product_id|category|created_at|price|qty|...] │
│ Row 2: [order_id|user_id|product_id|category|created_at|price|qty|...] │
│ Row 3: [order_id|user_id|product_id|category|created_at|price|qty|...] │
│                  ↑                            ↑          ↑    ↑         │
│              needed                         needed    needed needed     │
│   ←────────────────── All of this must be read ──────────────────→     │
└─────────────────────────────────────────────────────────────────────────┘

Column-oriented storage — only read the columns you need:
┌────────────┐  ┌──────────────────┐  ┌────────────┐  ┌─────────┐
│ category   │  │  created_at      │  │  price     │  │  qty    │
│ col file   │  │  col file        │  │  col file  │  │ col file│
│ Electronics│  │  2024-01-05      │  │  99.99     │  │  1      │
│ Clothing   │  │  2024-01-07      │  │  29.99     │  │  2      │
│ Electronics│  │  2024-01-09      │  │  149.99    │  │  1      │
│    ...     │  │    ...           │  │    ...     │  │   ...   │
└────────────┘  └──────────────────┘  └────────────┘  └─────────┘
       ↑                ↑                   ↑               ↑
  Read this        Read this           Read this        Read this
                  46 other column files are SKIPPED
```

### 1.4 Why OLTP Cannot Serve Both Workloads Well

Some people ask: "Can't we just run analytics queries on Postgres with the right indexes?"
The answer is: at small scale, yes. At scale, no, for several reasons.

First, analytics queries compete with user-facing OLTP queries for I/O bandwidth and CPU.
A single analyst running a slow report can cause Postgres to slow down for all users. This
is not a configuration problem — it's a fundamental resource contention problem.

Second, row-oriented storage is structurally wrong for analytics. You cannot add a column
index for every possible analytics query pattern. The space would be prohibitive.

Third, OLTP databases are optimized for update-in-place workloads. Analytical tables are
often append-only (new events added, old events never changed). This difference changes
the optimal storage format, compression strategy, and query planner entirely.

The industry solution is to have two separate systems: OLTP for transactions, OLAP for
analytics, with a pipeline moving data from one to the other.

---

### Brainstorming Q&A for Part 1

**Q: If OLAP is just for reads, why not create a read replica of Postgres for analytics?**

A read replica of Postgres is a common intermediate step, and it does solve the resource
contention problem — analytics queries run on the replica, leaving the primary free for
OLTP. However, it does not solve the structural problem: the replica is still row-oriented
Postgres, which means analytics queries still scan all 50 columns when they only need 4.
At hundreds of millions of rows, this becomes prohibitively slow and expensive.

Read replicas also have replication lag, typically a few seconds to a few minutes. For
real-time dashboards this is fine. For quarterly financial reports this is fine. But a
Postgres read replica is not designed for petabyte-scale analytics. Practically speaking,
companies use read replicas to buy time while they build a proper warehouse.

**Q: How does a data warehouse handle concurrent users — what if 100 analysts run queries at the same time?**

This is where the architecture of different warehouses diverges significantly. In
Redshift, adding users means sizing your cluster for peak concurrent load — 100 users
running simultaneously requires a bigger cluster. Snowflake introduced the concept of
"virtual warehouses": separate compute clusters for separate workloads. The BI tool gets
its own compute cluster, data scientists get another, ETL jobs get a third. They all share
the same underlying storage (S3) but can scale compute independently. BigQuery is
serverless — it automatically allocates slots (units of computation) for each query from a
shared pool, with options to purchase dedicated slot reservations for predictable
workloads.

The practical answer is: MPP systems (covered in Part 5) handle concurrency by giving
each query its own set of worker nodes. The more simultaneous queries, the more resources
needed. The difference is in *how* you pay for that resource expansion.

**Q: What is HTAP and why didn't it become the universal solution?**

HTAP stands for Hybrid Transactional/Analytical Processing — the dream of one database
that handles both workloads well. Systems like TiDB, AlloyDB (Google), Aurora, and newer
Postgres extensions claim HTAP capabilities. The reality is nuanced: these systems
typically use row storage for OLTP and maintain a separate columnar replica internally
for analytics. They hide the complexity from the user but don't violate the fundamental
physics.

The trade-offs are real: HTAP systems perform better than pure OLTP for analytics but
worse than a dedicated warehouse for very large analytical queries. They perform well for
OLTP but have higher write latency than pure OLTP systems because writes must also
update the columnar replica. For many companies (especially startups), HTAP is excellent
because you reduce operational complexity. For companies with truly large analytical
workloads (petabytes), a dedicated warehouse is still necessary.

---

## Part 2: Columnar Storage — How It Actually Works

### 2.1 The Basic Idea

Let's build intuition from a simple example. Imagine a spreadsheet with 5 columns and
10 million rows. In row-oriented storage, each row's data is stored together:

```
Disk layout (row-oriented):
Block 1: [row1_col1, row1_col2, row1_col3, row1_col4, row1_col5]
Block 2: [row2_col1, row2_col2, row2_col3, row2_col4, row2_col5]
Block 3: [row3_col1, row3_col2, row3_col3, row3_col4, row3_col5]
...
```

In column-oriented storage, all values for the same column are stored together:

```
Disk layout (column-oriented):
col1_file: [row1_col1, row2_col1, row3_col1, row4_col1, ... row10M_col1]
col2_file: [row1_col2, row2_col2, row3_col2, row4_col2, ... row10M_col2]
col3_file: [row1_col3, row2_col3, row3_col3, row4_col3, ... row10M_col3]
col4_file: [row1_col4, row2_col4, row3_col4, row4_col4, ... row10M_col4]
col5_file: [row1_col5, row2_col5, row3_col5, row4_col5, ... row10M_col5]
```

A query that only needs col2 and col4 reads only those two files. The other three files
are never touched. If you have 50 columns and your query needs 4, you read 8% of the
data instead of 100%.

### 2.2 Compression — Why Columnar Data Compresses So Well

Here is the key insight that makes columnar storage even more powerful than the "read
fewer columns" benefit: values in the same column are of the same type and often similar
in value, which means they compress extremely well.

Consider a column called `country` with 1 billion rows. The values might be:
"US", "US", "US", "US", "UK", "US", "US", "CA", "US", "US", "US", "DE", ...

With row-oriented storage, these country strings are scattered throughout the disk,
interleaved with all the other columns. There is no good way to compress them.

With column-oriented storage, all 1 billion country strings are together. Now we can
apply powerful compression algorithms:

**Dictionary Encoding:**
Instead of storing "United States" (13 bytes) 800 million times, build a dictionary:
{0 = "US", 1 = "UK", 2 = "CA", 3 = "DE", ...} and store just integer codes (1-4 bytes).
For a column with 200 distinct country values, this can compress 10x or more.

```
Dictionary:
  0 → "US"
  1 → "UK"
  2 → "CA"
  3 → "DE"

Column data (instead of full strings): 0,0,0,0,1,0,0,2,0,0,0,3,...
From 13 bytes per row → 1 byte per row = 13x compression
```

**Run-Length Encoding (RLE):**
If the data is sorted (which you can choose to do), consecutive identical values can be
compressed to "value + count":

```
Sorted country column: US x 800,000,000 | UK x 80,000,000 | CA x 70,000,000 | ...

Run-length encoded:
  (US, 800000000)
  (UK, 80000000)
  (CA, 70000000)
  ...

From 800 million entries → a few dozen entries = thousands of times compressed
```

**Bit packing:**
If a column has values 0-15, each value fits in 4 bits, not 64 bits (8 bytes). Packing
multiple values into one integer word gives 16x compression for these "low cardinality"
integer columns.

The combined effect of dictionary encoding + RLE + bit packing on real analytics data
typically achieves 5x to 20x compression compared to uncompressed row storage. That
means not only do you read fewer columns, but each column takes up far less space.

### 2.3 Parquet — The Standard Open Columnar Format

Apache Parquet is the open-source columnar file format that has become the standard for
analytical data storage. BigQuery, Redshift Spectrum, Spark, Hive, Presto, Athena, and
virtually every analytics tool can read and write Parquet files.

Key design decisions in Parquet:

**Row groups**: The file is divided into row groups, typically 128 MB each. Within each
row group, data is stored column-by-column. This gives you the benefit of columnar
storage while keeping related column data co-located for a range of rows.

**Column chunks**: Within each row group, each column's data is a "column chunk" that
can be read independently.

**Page-level statistics**: Each page within a column chunk stores min/max values. This
enables "predicate pushdown" — the query engine can look at the min/max for each page
and skip entire pages that cannot contain rows matching a WHERE clause.

```
Parquet file structure:
┌─────────────────────────────────────────────────┐
│  File Header                                    │
├─────────────────────────────────────────────────┤
│  Row Group 1 (rows 1 - 1,000,000):             │
│  ┌──────────────┬──────────────┬──────────────┐ │
│  │ col_1 chunk  │ col_2 chunk  │ col_3 chunk  │ │
│  │ [page stats] │ [page stats] │ [page stats] │ │
│  │ [encoded     │ [encoded     │ [encoded     │ │
│  │  data]       │  data]       │  data]       │ │
│  └──────────────┴──────────────┴──────────────┘ │
├─────────────────────────────────────────────────┤
│  Row Group 2 (rows 1,000,001 - 2,000,000):     │
│  ┌──────────────┬──────────────┬──────────────┐ │
│  │ col_1 chunk  │ col_2 chunk  │ col_3 chunk  │ │
│  └──────────────┴──────────────┴──────────────┘ │
├─────────────────────────────────────────────────┤
│  ...more row groups...                          │
├─────────────────────────────────────────────────┤
│  Footer: schema + row group metadata + offsets  │
└─────────────────────────────────────────────────┘
```

### 2.4 Sort Order in Columnar Storage

One more dimension: the physical sort order of rows matters even in columnar storage,
because it interacts with compression and predicate pushdown.

If your data is sorted by `created_at` (date) and an analyst queries
`WHERE created_at BETWEEN '2024-01-01' AND '2024-01-31'`, the query engine can:
1. Look at row group metadata (min/max for `created_at`)
2. Skip all row groups where `max(created_at) < '2024-01-01'` or `min(created_at) > '2024-01-31'`
3. Only decompress and scan the row groups that fall in January 2024

Combined with RLE compression (sorted dates are highly repetitive), sort order is a
free performance multiplier. In BigQuery this is called "clustering." In Redshift it's
called "sort keys." In Snowflake it's called "cluster keys." Same idea, different names.

---

### Brainstorming Q&A for Part 2

**Q: If columnar storage is so much better for analytics, why do OLTP databases use row storage at all?**

Row storage is better for OLTP because transactional workloads frequently need all
columns for a given row. When a user logs in, you look up their user record by ID and
need their name, email, hashed password, settings, and preferences all at once — all
columns. In columnar storage, reconstructing a single row requires reading from dozens
of separate column files, which is much slower than reading one contiguous row from
row-oriented storage.

More importantly, OLTP databases do many random updates. Changing a user's email address
in row-oriented storage is simple: find the row, update one field, write back. In
columnar storage, updating one field means modifying one column's file for that row
position — which is fine. But inserting a new row means appending to every column file.
And updating rows that change many columns means touching many files. Columnar databases
handle this by writing updates to small "delta" structures that are periodically merged
into the main columnar storage, adding complexity that is unnecessary in an OLTP system.

**Q: How does the query engine know which columns to read if the data is stored separately?**

The schema is stored separately from the data — usually in a catalog service (BigQuery's
catalog, Redshift's metadata layer, Hive Metastore, AWS Glue Data Catalog). When a query
arrives, the query planner consults the catalog to understand the table's schema: how many
columns, their types, which column chunks are in which files, and where those files are
stored. The planner then identifies which columns are referenced in the SELECT clause and
WHERE clause. Only those column files are opened and read. The catalog also stores
statistics: total row count, min/max values per column, cardinality estimates. These
statistics are critical for the query optimizer to generate a good query plan.

**Q: What happens when you need to update a row — say, an order status changes from "shipped" to "delivered"?**

This is a real challenge for columnar systems. Most data warehouses handle updates
inefficiently: they append a new version of the row and mark the old version as deleted.
Periodically, a background process "compacts" the data by rewriting column files with the
deleted rows removed. This is why data warehouses are best for immutable, append-only
data.

Snowflake handles updates by writing changed data to new "micro-partitions" and marking
old partitions as deleted. BigQuery DML (UPDATE/DELETE/MERGE) operations work but are
expensive — they rewrite entire partitions. Tools like Delta Lake and Apache Iceberg add
a transaction log on top of columnar files (Parquet) to support ACID updates efficiently,
tracking which files are "current" versus "deleted." The overhead is acceptable for
analytical workloads that update a small fraction of rows.

---

## Part 3: The Data Warehouse Architecture

### 3.1 The Full Pipeline Overview

A data warehouse does not exist in isolation. It's the end point of a pipeline that
starts at your operational systems and ends at your BI tools and analysts. Understanding
the full architecture is important because failure at any layer cascades downstream.

```
Full Data Warehouse Architecture:

Source Systems          Pipeline            Warehouse                Consumers
┌─────────────┐        ┌──────────┐        ┌──────────────────────┐  ┌──────────────┐
│ PostgreSQL  │───────►│          │        │ Staging Layer        │  │ Tableau      │
│ (OLTP)      │        │ ETL/ELT  │───────►│ (raw, untransformed) │  │ Looker       │
├─────────────┤        │ Pipeline │        ├──────────────────────┤  │ Power BI     │
│ MySQL       │───────►│          │        │ Core/Warehouse Layer  │  └──────────────┘
│ (OLTP)      │        │ Fivetran │        │ (cleaned, modeled,   │       │
├─────────────┤        │ Airbyte  │        │  star schema)        │       │
│ Kafka       │───────►│ dbt      │        ├──────────────────────┤  ┌──────────────┐
│ (events)    │        │ Airflow  │        │ Data Marts           │◄─┤ Data         │
├─────────────┤        └──────────┘        │ (dept-specific       │  │ Scientists   │
│ Salesforce  │                            │  subsets)            │  └──────────────┘
│ (SaaS)      │───────►                    └──────────────────────┘
├─────────────┤                                      ▲
│ Log files   │───────►                              │
│ (S3)        │                              Data Catalog / Governance
└─────────────┘
```

### 3.2 Source Systems

Source systems are wherever your data originates. This typically includes:

- **OLTP databases**: Postgres, MySQL — your application's primary data stores
- **Event streams**: Kafka topics containing clickstream, user activity, server logs
- **Third-party SaaS**: Salesforce (CRM), Stripe (payments), Hubspot (marketing)
- **Log files**: Application logs stored in S3 or GCS
- **APIs**: REST APIs from external data providers

The challenge with source systems is that they are owned by different teams, change their
schemas without warning, have inconsistent data quality, and may not be designed with
analytics in mind. A product engineer changes a column name in Postgres, and suddenly the
ETL pipeline breaks.

### 3.3 The ETL/ELT Pipeline Layer

This is the plumbing. It extracts data from source systems, transforms it into the right
shape, and loads it into the warehouse. Tools in this layer:

- **Fivetran / Airbyte**: managed connectors that replicate data from hundreds of sources
  into your warehouse without you writing code. They handle schema changes, incremental
  loads, and de-duplication.
- **Apache Airflow**: workflow orchestrator — defines the order in which pipeline steps
  run, handles retries and alerting, tracks which runs succeeded or failed.
- **dbt (data build tool)**: SQL-based transformation framework. You write SQL models,
  dbt compiles them into the right SQL dialect and runs them in your warehouse. This is
  the "T" in ELT — transformations happen inside the warehouse using SQL.
- **Apache Spark**: for transformations that are too heavy for SQL or require custom Python
  logic. Often used for ML feature engineering pipelines.

### 3.4 Staging Layer

The staging layer is the first landing zone inside the warehouse. It contains raw,
untransformed data, as close to the source as possible. Why keep raw data?

- **Auditability**: If a transformation had a bug, you can re-run it against the raw data
  without having to re-extract from the source system.
- **Schema flexibility**: Source systems change. Raw data captures whatever the source
  sent. Transformations can handle the schema change logic.
- **Debugging**: When an analyst finds a number that doesn't match what they expect, you
  trace back through the transformation chain to the raw data.

Staging tables are typically prefixed with `stg_` by convention. They are not joined,
not aggregated, not cleaned. They are just raw copies.

### 3.5 Core Warehouse / Dimensional Model Layer

This is where the real work happens. Raw data from staging is cleaned, joined, and
modeled into a star schema (covered in Part 4). This layer is what analysts and BI tools
actually query. Tables here have clear business meaning: `fct_orders`, `dim_users`,
`dim_products`, `dim_date`.

This layer enforces data quality rules: null checks, referential integrity, deduplication.
A row in `fct_orders` represents exactly one order. A row in `dim_users` represents
exactly one user. Joining them gives you the full picture.

### 3.6 Data Marts

Data marts are department-specific subsets of the warehouse. The finance team's mart
contains revenue tables, cost tables, and financial metrics calculated their way. The
marketing team's mart contains campaign performance tables. The product team's mart
contains user funnel metrics.

Why separate marts instead of having everyone query the core warehouse?

- **Performance**: small, pre-aggregated tables query faster
- **Governance**: the finance team controls the definition of "revenue" in their mart
- **Simplicity**: analysts don't need to know the full star schema, just their mart

Data marts are often materialized views or summary tables built from the core warehouse.

### 3.7 BI Tools and Consumers

At the top of the stack are the consumers: Tableau, Looker, Power BI, Metabase for
visualization; Jupyter notebooks for data science; dbt's semantic layer for defining
metrics that are consistent across tools. The warehouse serves SQL queries from all
these tools simultaneously.

---

### Brainstorming Q&A for Part 3

**Q: Why does the staging layer exist? Can't you transform data as it lands?**

You can, and some pipelines do. The problem is that when your transformation has a bug —
and it will — you need to be able to re-run the transformation without re-extracting all
the data from the source system. Source systems are not designed to replay historical data.
If your Postgres database only keeps 30 days of change logs (binlog), and your
transformation had a bug that corrupted 6 months of data, you have a serious problem if
you didn't keep the raw data somewhere.

The staging layer is essentially a cheap insurance policy. Storage in S3 or GCS (where
you might store raw data) costs pennies per GB per month. The cost of re-extracting and
reprocessing months of data from a production OLTP database — in engineering time, in
load on the source system, in missed deadlines — is orders of magnitude higher. The
industry standard is to always keep raw data, even if you don't expect to need it.

**Q: How do you handle data quality issues in the pipeline — what if source data has nulls where it shouldn't?**

Data quality is one of the hardest problems in data engineering. The approach most mature
teams use has multiple layers. First, at extraction: tools like Great Expectations or dbt
tests run assertions on the raw data as it lands (e.g., "order_id must never be null,"
"price must be positive"). If assertions fail, the pipeline pauses and alerts the team
rather than propagating bad data downstream.

Second, at transformation: dbt models can include relationship tests (every order's
user_id must exist in the users table) and uniqueness tests (no duplicate order IDs in
the fact table). Third, at consumption: data observability tools like Monte Carlo or
Bigeye monitor metrics over time and alert when values drift unexpectedly — if yesterday's
order count was 500,000 and today it's 5,000, something is probably wrong with the
pipeline before an analyst finds it and reports it.

**Q: What is a semantic layer and why is it gaining popularity?**

A semantic layer sits between the data warehouse and BI tools and provides a
business-logic abstraction. Instead of every analyst writing their own SQL to calculate
"monthly active users," the semantic layer defines MAU once (as a reusable metric) and
every tool (Tableau, Looker, Python notebooks) calls that definition. This solves the
"different teams calculating the same metric differently and getting different answers"
problem, which is a major source of trust issues in analytics organizations.

dbt's semantic layer (now called MetricFlow) and tools like Cube.js are the main players.
The idea is old (Looker's LookML has done this for years), but it's gaining adoption
because organizations have learned the hard way that inconsistent metric definitions
destroy confidence in data. An L6 candidate mentioning the semantic layer in an analytics
system design demonstrates awareness of the organizational dimension of data platform
design, not just the technical dimension.

---

## Part 4: Star Schema and Dimensional Modeling

### 4.1 The Two Types of Tables

Dimensional modeling, developed by Ralph Kimball in the 1990s, is the dominant approach
to modeling data in a warehouse. It defines two types of tables:

**Fact tables** contain measurements — things that happened, usually with numeric values.
Examples: orders, page views, payments, clicks, logins, shipments. Fact tables:
- Have very high row counts (billions)
- Are mostly append-only (events happen, they don't change)
- Contain foreign keys to dimension tables
- Contain the numeric measures (price, quantity, duration, count)

**Dimension tables** contain context — the "who, what, where, when" that gives meaning
to facts. Examples: users, products, geographic regions, marketing campaigns, time.
Dimension tables:
- Have lower row counts (millions at most)
- Change slowly (a user's email might change, a product's name might change)
- Contain descriptive attributes (name, category, country, tier)

### 4.2 The Star Schema

The star schema gets its name from the shape of the entity-relationship diagram: the fact
table sits in the center like a star, with dimension tables radiating outward like points.

```
Star Schema — Orders Data Warehouse:

                    ┌─────────────────┐
                    │  dim_date       │
                    │─────────────────│
                    │ date_key (PK)   │
                    │ date            │
                    │ year            │
                    │ quarter         │
                    │ month           │
                    │ day_of_week     │
                    │ is_holiday      │
                    └────────┬────────┘
                             │
                             │ date_key (FK)
                             │
┌─────────────────┐          │         ┌─────────────────┐
│  dim_user       │          │         │  dim_product    │
│─────────────────│          ▼         │─────────────────│
│ user_key (PK)   │   ┌─────────────┐  │ product_key (PK)│
│ user_id         │   │  fct_orders │  │ product_id      │
│ email           │   │─────────────│  │ name            │
│ country         │◄──┤ order_key   ├──►│ category        │
│ signup_date     │   │ user_key(FK)│  │ subcategory     │
│ tier            │   │ prod_key(FK)│  │ brand           │
│ age_group       │   │ date_key(FK)│  │ unit_cost       │
└─────────────────┘   │ loc_key (FK)│  └─────────────────┘
                      │ price       │
                      │ quantity    │          ┌─────────────────┐
                      │ discount    │          │  dim_location   │
                      │ tax         │          │─────────────────│
                      │ shipping    │          │ location_key(PK)│
                      └──────┬──────┘          │ city            │
                             │                 │ state           │
                             └────────────────►│ country         │
                               location_key FK │ region          │
                                               └─────────────────┘
```

### 4.3 Benefits of Star Schema for Query Performance

The star schema design is not just organizational — it has direct query performance
implications.

**Filter pushdown**: When a query filters on a dimension attribute (`WHERE category =
'Electronics'`), the query engine can first filter the dimension table (a small scan) to
find the matching dimension keys, then use those keys to filter the fact table. This
reduces the rows scanned in the huge fact table.

**Aggregation efficiency**: Because the fact table contains only foreign keys and numeric
measures, GROUP BY queries over the fact table are efficient — the engine aggregates
numbers without dealing with large string values.

**Pre-computed hierarchies**: The `dim_date` table is a classic example. Instead of
computing `EXTRACT(YEAR FROM created_at)` in every query, you pre-compute year, quarter,
month, week, day_of_week, is_holiday for every date. Queries like "GROUP BY quarter"
become simple joins and GROUP BY on a pre-computed column.

### 4.4 Slowly Changing Dimensions (SCD)

A dimension table's attributes change over time. A user changes their country. A product
changes its category. A store changes its region. How do you handle this in a dimension
table?

**SCD Type 1 — Overwrite**: Just update the dimension record with the new value. No
history kept. Simple, but queries on historical data will use the *current* value, not the
value at the time of the order. Example: if a user moves from US to UK, all their past
orders will now look like they came from UK. Bad for historical analysis.

**SCD Type 2 — Add new row**: Instead of overwriting, add a new row with the new
attribute values. Add `valid_from` and `valid_to` columns to track which version was
active when. The fact table foreign key points to the specific version of the dimension
record that was active at the time of the event.

```
SCD Type 2 — dim_user example:
┌──────────┬─────────┬─────────┬──────────┬────────────┬────────────┐
│ user_key │ user_id │ country │ tier     │ valid_from │ valid_to   │
├──────────┼─────────┼─────────┼──────────┼────────────┼────────────┤
│ 1001     │ u_42    │ US      │ free     │ 2022-01-01 │ 2023-06-14 │
│ 1002     │ u_42    │ UK      │ free     │ 2023-06-15 │ 2024-03-20 │
│ 1003     │ u_42    │ UK      │ premium  │ 2024-03-21 │ 9999-12-31 │
└──────────┴─────────┴─────────┴──────────┴────────────┴────────────┘
                                                           ↑
                                               9999-12-31 = "current"
```

**SCD Type 3 — Add column**: Add `previous_country` and `current_country` columns. Keeps
one level of history but not unlimited. Simple but limited.

Type 2 is the most common in practice because it preserves full history without losing
the ability to do "what did the world look like when this order was placed" queries. The
trade-off: the dimension table grows larger over time, and queries need to filter by
`valid_to = '9999-12-31'` or use `BETWEEN` logic to find the right version.

### 4.5 The Snowflake Schema (vs. Star Schema)

A "snowflake schema" (confusingly, not just the Snowflake product) is a star schema with
normalized dimension tables. Instead of one flat `dim_product` table, you have
`dim_product` → `dim_category` → `dim_department`. This reduces storage (category name
stored once, not once per product) but requires more joins in queries.

Most modern warehouses favor the star schema's denormalized approach because:
- Storage is cheap
- Joins on large tables are expensive
- Simpler schema means faster query authoring and less room for mistakes

The Snowflake product supports both, but the star schema is generally recommended for
the core analytical layer.

---

### Brainstorming Q&A for Part 4

**Q: How do you decide what goes in a fact table vs. a dimension table?**

The heuristic is: facts are measurements, dimensions are context. Ask yourself: "Is this
value something I would SUM or COUNT?" If yes, it's probably a fact (price, quantity,
duration, count). "Is this a description or a label?" If yes, it's probably a dimension
(category, country, tier, name).

A trickier question is what to do with attributes that could be either. User age at the
time of purchase — is that a fact (numeric, measurable) or a dimension (used for
filtering, grouping)? The answer is context-dependent. If analysts frequently filter
"orders by users aged 25-34," treating it as a dimension attribute makes sense. If
analysts want "average age of purchasers by product category," it behaves as a fact
measure. In practice, you often include it in both places: as a column on the fact table
for use as a measure, and as a pre-bucketed `age_group` attribute on the user dimension
for use as a filter.

**Q: What is a degenerate dimension and when do you use one?**

A degenerate dimension is a dimension attribute stored directly on the fact table, not
in a separate dimension table. The classic example is `order_number` — it's an identifier
used for filtering and grouping, but there's no other information about it (no attributes
beyond the order ID itself). Creating a separate `dim_order` table with just an ID column
would be wasteful. So `order_number` lives as a column on `fct_orders` directly.

Other examples: transaction IDs, receipt numbers, invoice numbers, ticket numbers. Any
identifier that is used for grouping or filtering but has no associated descriptive
attributes. Degenerate dimensions are a practical compromise between strict dimensional
modeling theory and the reality that some "things" have no properties beyond their ID.

**Q: How does a data warehouse handle slowly changing dimensions in practice — isn't SCD Type 2 very complex?**

SCD Type 2 is conceptually clean but operationally messy. In practice, tools like dbt
have built-in snapshot functionality that handles the `valid_from` and `valid_to` column
management automatically. You define a snapshot configuration (source table, unique key,
strategy = "timestamp" or "check"), and dbt runs it on a schedule. Each run detects
changed rows, closes the old record by setting `valid_to` to the current timestamp, and
inserts a new record with `valid_from` set to now.

The query-time complexity is also real: joining a fact table to an SCD Type 2 dimension
table requires the user to either filter to current records (`WHERE valid_to = '9999-12-31'`)
or write a range join (`ON fact.event_date BETWEEN dim.valid_from AND dim.valid_to`).
Range joins are expensive and not always optimized well by query planners. Many teams
pragmatically use SCD Type 1 for attributes where historical accuracy doesn't matter
(user's name, user's tier for non-financial analysis) and SCD Type 2 only for attributes
where it does (user's country for revenue attribution, product category for inventory
accounting). The decision is business-driven, not just technical.

---

## Part 5: MPP Query Execution — Massively Parallel Processing

### 5.1 Why a Single Machine Is Not Enough

A table with 1 trillion rows and 10 petabytes of data cannot be scanned by a single
machine. A modern server with an NVMe SSD has a disk read speed of perhaps 7 GB/s.
Reading 10 TB would take about 24 minutes, ignoring CPU time for decompression and
computation. That is unacceptably slow for interactive analytics.

The solution is to split the data across hundreds or thousands of machines and have them
all scan in parallel. A query that would take 24 minutes on one machine takes under 1
minute on 1,500 machines. This is Massively Parallel Processing (MPP).

### 5.2 The Architecture: Coordinator + Workers

All MPP systems follow a similar architecture:

```
MPP Query Execution Architecture:

                    User submits SQL query
                           │
                           ▼
                  ┌─────────────────┐
                  │  Coordinator /  │
                  │  Query Planner  │
                  │  (1 node)       │
                  └────────┬────────┘
                           │
              Parse SQL → Create query plan
              Identify partitions → Dispatch subtasks
                           │
           ┌───────────────┼───────────────┐
           │               │               │
           ▼               ▼               ▼
    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
    │ Worker Node  │ │ Worker Node  │ │ Worker Node  │
    │     1        │ │     2        │ │     3        │
    │──────────────│ │──────────────│ │──────────────│
    │ Scan shard 1 │ │ Scan shard 2 │ │ Scan shard 3 │
    │ Apply filter │ │ Apply filter │ │ Apply filter │
    │ Local agg.   │ │ Local agg.   │ │ Local agg.   │
    └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
           │                │                │
           └────────────────┼────────────────┘
                            │
                   Shuffle (redistribute
                   data by grouping key)
                            │
           ┌────────────────┼────────────────┐
           │                │                │
           ▼                ▼                ▼
    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
    │ Worker Node  │ │ Worker Node  │ │ Worker Node  │
    │     1        │ │     2        │ │     3        │
    │──────────────│ │──────────────│ │──────────────│
    │ Final agg.   │ │ Final agg.   │ │ Final agg.   │
    │ (for keys    │ │ (for keys    │ │ (for keys    │
    │  assigned    │ │  assigned    │ │  assigned    │
    │  to me)      │ │  to me)      │ │  to me)      │
    └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
           │                │                │
           └────────────────┼────────────────┘
                            │
                            ▼
                  ┌─────────────────┐
                  │  Coordinator    │
                  │  Merge results  │
                  │  Return to user │
                  └─────────────────┘
```

### 5.3 How a Query Gets Parallelized — Step by Step

Let's trace a specific query through the MPP system:

```sql
SELECT category, SUM(revenue) as total_revenue
FROM orders
WHERE order_date >= '2024-01-01'
GROUP BY category;
```

**Step 1: Parse and Plan (Coordinator)**
The coordinator parses the SQL and creates an execution plan. It identifies:
- Table: `orders` — distributed across 1,000 worker nodes (shards/partitions)
- Filter: `order_date >= '2024-01-01'` — can be applied at scan time
- Aggregation: `SUM(revenue)` grouped by `category` — requires data redistribution

**Step 2: Scan (Worker Nodes — All 1,000 in Parallel)**
Each worker scans its local shard of the `orders` table. Because it knows the filter
(`order_date >= '2024-01-01'`), each worker only reads rows matching this condition.
It reads only the `order_date`, `category`, and `revenue` columns (the others are skipped
by columnar storage). Each worker computes a local partial aggregation:

```
Worker 1 local result:
  category=Electronics → local_sum=45,000
  category=Clothing    → local_sum=12,000

Worker 2 local result:
  category=Electronics → local_sum=38,000
  category=Books       → local_sum=7,500
...
```

**Step 3: Shuffle (Network Redistribution)**
To compute the global SUM per category, all rows with the same category must be on the
same worker. The workers redistribute their partial results by `category` key. This step
involves sending data over the network — it is the most expensive step because:
- Network bandwidth is slower than CPU computation or local memory
- Large shuffle operations can move many gigabytes or terabytes across the network
- If the data is skewed (one category has 90% of all orders), one worker gets overloaded

After shuffling, worker 1 might get all Electronics rows from all 1,000 workers, worker 2
might get all Clothing rows, and so on.

**Step 4: Final Aggregation (Worker Nodes)**
Each worker now has all partial sums for its assigned categories. It computes the final
SUM by adding up the partial results. This is simple local computation.

**Step 5: Merge and Return (Coordinator)**
The coordinator collects the final aggregated results from all workers, orders them
as specified (`ORDER BY total_revenue DESC`), and returns the result set to the user.

### 5.4 Joins in MPP Systems

Joins are the most complex operation in MPP because the data that needs to be joined may
live on different workers. Two common strategies:

**Broadcast join**: If one table is small enough (a dimension table), send a full copy
to every worker. Then each worker can join locally without any shuffling. This is
efficient when one table is small (< few hundred MB).

**Sort-merge join / hash join**: If both tables are large, hash each table's join key and
distribute rows to workers based on that hash. All rows with the same join key value end
up on the same worker, which can then join locally. The downside: requires shuffling
potentially both tables across the network.

Understanding these join strategies is why choosing your distribution key in Redshift,
or your cluster key in BigQuery, matters so much — if your fact table and its most-used
dimension tables are co-located on the same workers (co-located joins), you avoid the
expensive shuffle.

### 5.5 Stages and Pipelining

Modern MPP systems like BigQuery (Dremel/Capacitor) and Redshift break queries into
multiple "stages" that are pipelined: as soon as stage 1 produces output rows, stage 2
starts consuming them. This avoids materializing large intermediate results to disk,
which was a major bottleneck in early MapReduce-based systems.

BigQuery's Dremel takes this further with a tree-of-servers architecture: the coordinator
sends the query to intermediate "mixers" which further distribute to leaf workers. The
tree structure enables aggregation to happen progressively up the tree, avoiding a single
bottleneck at the coordinator for queries returning large aggregated results.

---

### Brainstorming Q&A for Part 5

**Q: What happens in an MPP system if one worker node is slow — does the whole query wait?**

Yes, the "straggler problem" is real. In an MPP system, the slowest worker determines
the total query latency. If 999 out of 1,000 workers finish in 10 seconds but one worker
takes 60 seconds (maybe it hit a disk I/O issue, or it was assigned a skewed partition),
the entire query takes 60 seconds.

Modern MPP systems address this with "speculative execution" — if a worker is identified
as slow (its assigned work is taking significantly longer than other workers doing similar
work), the coordinator starts running the same task on a different worker. Whichever
finishes first has its result used; the other is killed. This adds some redundant compute
cost but prevents outlier workers from wrecking query latency. BigQuery and Spark both
use speculative execution. An alternative approach is to preemptively load-balance by
dividing data into more partitions than there are workers, so fast workers automatically
pick up more work when they finish their first partition.

**Q: How does BigQuery achieve serverless MPP — where are the workers coming from if there's no cluster to provision?**

BigQuery is built on Google's Borg cluster management infrastructure and runs on shared
server fleets across Google's data centers. When a query arrives, BigQuery's resource
manager allocates "slots" (each slot is one vCPU of compute) from the shared pool to
the query. The default allocation is 2,000 slots per on-demand query. Workers are spun
up from this shared pool in milliseconds because the machines are already running — they
are repurposed from other Google workloads or idle capacity. The columnar data (stored in
Capacitor format on Colossus, Google's distributed file system) is accessible from any
machine in the data center, so data locality is not a constraint.

This is fundamentally different from Redshift, where you rent specific machines that have
specific data on them. BigQuery separates storage (Colossus) from compute (Borg) so
completely that any compute machine can access any data, enabling true on-demand scaling.
The trade-off: for sustained, predictable workloads, pre-reserved slots are cheaper than
on-demand pricing; and cold queries (where all workers must read from remote storage) can
have higher latency than Redshift queries where data is on local SSDs.

**Q: What is data skew and how do you fix it in a distributed query?**

Data skew is when the data is not uniformly distributed across partitions. If one
category (say "Electronics") has 60% of all orders and the rest of the categories share
the remaining 40%, the worker handling Electronics data will take 3x longer than average
and will block all other workers from completing.

The solutions depend on the type of skew. For grouping skew: some aggregation frameworks
support "salting" — adding a random prefix to the grouping key so that the skewed key is
spread across multiple workers, then doing a second-level aggregation to combine the
partial results. For join skew: if a join key appears disproportionately often in one
table (a common user ID in a clickstream), the join partner is broadcast to all workers
rather than shuffled. For partition skew: if one date partition has 100x more data than
others (because the product launched on that date), you might need to sub-partition by
hour or by hash of another column to break up the large partition into smaller pieces.

---

## Part 6: Partition Pruning and Query Optimization

### 6.1 Partitioning — The Single Biggest Performance Lever

Partitioning divides a large table into smaller physical pieces based on the value of
a column. The most common partition column in a data warehouse is date or timestamp.

When you create a table partitioned by date, the warehouse stores each day's (or each
month's) data in a separate physical location. A query filtering by date can then skip
all other date partitions entirely — this is called "partition pruning."

```
Partitioned Orders Table:

┌────────────────────────────────────────────────────────────┐
│ orders table (total: 10 TB, 1 year of data)               │
├────────────────┬──────────────┬──────────────┬────────────┤
│ Partition      │ Partition    │ Partition    │ ...        │
│ 2024-01-01     │ 2024-01-02   │ 2024-01-03   │            │
│ 27 GB          │ 29 GB        │ 26 GB        │            │
├────────────────┼──────────────┼──────────────┼────────────┤
│ Partition      │ Partition    │ Partition    │ ...        │
│ 2024-02-01     │ 2024-02-02   │ 2024-02-03   │            │
│ 31 GB          │ 30 GB        │ 28 GB        │            │
└────────────────┴──────────────┴──────────────┴────────────┘

Query: SELECT SUM(revenue) FROM orders WHERE order_date = '2024-01-15'
Result: Read ONLY the 2024-01-15 partition (28 GB) instead of 10 TB
        → 99.7% of data skipped
```

### 6.2 Partition Key Selection

The choice of partition key is crucial. Date is almost always the right choice for time-
series analytical data because:
- Analytics queries almost always filter by date range
- Data ingestion is date-aligned (today's data goes in today's partition)
- Partition management (retention, archiving) is natural with date partitions

Bad partition choices:
- **High cardinality columns** (user_id): too many tiny partitions, overhead exceeds benefit
- **Low cardinality columns** (status with 3 values): too few large partitions, each still
  huge, pruning doesn't help much
- **Columns not used in WHERE clauses**: pruning never triggers

### 6.3 Predicate Pushdown

Predicate pushdown is the technique of applying filters as early as possible in the query
execution pipeline — "pushing" them "down" to the storage layer rather than filtering
after reading all the data.

With Parquet files and modern query engines (Trino/Presto, Spark, BigQuery):

1. The query engine reads the Parquet file footer, which contains min/max statistics for
   each column in each row group.
2. If a filter condition (predicate) like `WHERE price > 1000` can be checked against
   these statistics, and if `max(price) <= 1000` for an entire row group, that row group
   is skipped entirely without decompressing or reading its data.
3. For columns like dictionary-encoded `category`, the engine can check the dictionary
   without reading the data pages: if 'Electronics' is not in the dictionary for this row
   group, the entire row group is skipped.

This can skip 80-99% of data at the row group level, in addition to partition pruning
at the partition level. Two levels of filtering before reading a single data byte.

### 6.4 Clustering / Sort Keys

Within a partition, data can be physically sorted by one or more columns. BigQuery calls
this "clustering," Redshift calls it "sort keys," Snowflake calls it "cluster keys."

When data is clustered by `user_id`, all rows for a given user are stored together. A
query filtering `WHERE user_id = 12345` can use block-level min/max metadata to skip to
the right part of the partition quickly, rather than scanning the entire partition.

The combination of partition pruning (skip wrong partitions) + clustering (skip wrong
blocks within a partition) creates a two-level lookup that can reduce data read by 99%+.

### 6.5 Approximate Query Processing

For exploratory analytics, exact answers are sometimes less important than fast answers.
Approximate query processing algorithms trade accuracy for speed:

**HyperLogLog (HLL)**: Estimates COUNT(DISTINCT x) with ~1% error using only a few
kilobytes of memory, versus the exact count which might require tracking millions of
distinct values. Used in BigQuery (`APPROX_COUNT_DISTINCT`) and most warehouses.

**Theta sketches**: More general than HLL, support set operations (union, intersection)
on approximate distinct counts.

**Sample queries**: Some systems automatically sample data for exploratory queries
("give me the result for 1% of the data 100x faster").

**Materialized views**: Pre-computed aggregations stored as tables. A query for "total
revenue by month" can be answered from a pre-computed materialized view in milliseconds
instead of scanning the entire orders table. The trade-off: materialized views must be
refreshed (either on a schedule or when base data changes), and they only help for query
patterns you anticipated.

### 6.6 Real Incident: The Quarter-End Warehouse Meltdown

A mid-size e-commerce company had a 3 TB Redshift cluster that served their analytics
fine for 11 months of the year. But at the end of Q4 (December 31), the finance team
needed to run every quarterly, semi-annual, and annual report simultaneously. The data
science team was also running year-end model refreshes. The BI tool's scheduled refreshes
all kicked off at midnight.

The result: the Redshift cluster was completely overwhelmed. Query queue depth hit 500+
queries. Some queries timed out after 30 minutes. Finance couldn't close the books on
time. The CTO was paged at 2 AM.

The root cause was a combination of: (1) no partition pruning on the main fact table
(full table scans for every report), (2) no concurrency scaling enabled in Redshift, and
(3) all dashboards refreshing at midnight by default.

The fix: (1) restructured fact table with date partitioning and sort keys, reducing scan
costs by 80%, (2) enabled Redshift's concurrency scaling to automatically add burst
compute capacity, (3) staggered dashboard refresh schedules throughout the day.

The lesson: performance works fine at normal load, but peak load — which often happens
on exactly the highest-stakes days — requires explicit design for concurrency and
partition efficiency.

---

### Brainstorming Q&A for Part 6

**Q: What is the difference between partitioning in BigQuery and partitioning in Redshift?**

BigQuery's partitioning is managed automatically: you declare the partition column, and
BigQuery handles the physical storage layout, statistics, and pruning. Queries that filter
on the partition column automatically get pruning without any special syntax. BigQuery also
supports "ingestion-time partitioning" where data is partitioned by the time it was loaded,
which is useful when the data itself doesn't have a reliable timestamp.

Redshift's partitioning works through its distribution style and sort key approach. Redshift
physically distributes data across nodes (the distribution style: ALL, EVEN, KEY, or AUTO)
and sorts it within each node by the sort key. For date-range filtering, you want the date
column as the sort key — Redshift maintains zone maps (min/max per 1 MB block) and skips
blocks where the date range doesn't match. Redshift also supports late-binding partition
elimination through its newer Automatic Table Optimization feature, but the control is
less explicit than Snowflake or BigQuery. Snowflake takes yet another approach: automatic
micro-partitioning based on data arrival order, with automatic clustering that can be
explicitly tuned via cluster keys.

**Q: How do you know if partition pruning is actually happening — how do you debug a slow query?**

Every major warehouse has a query explanation tool. In BigQuery, `EXPLAIN` or the query
plan tab in the console shows bytes billed — if partition pruning is working, you'll see
"partitions scanned: 3 of 365" for a query filtering to 3 days. In Redshift, `EXPLAIN`
shows the query plan and you can look for "RowGScan" steps that indicate zone map
pruning. Snowflake's query profile shows "Partitions scanned" vs "Partitions total" and
visually highlights the pruning efficiency.

If you're not seeing pruning, the most common causes are: (1) the WHERE clause
filter uses a function on the partition column (`WHERE YEAR(order_date) = 2024` instead
of `WHERE order_date BETWEEN '2024-01-01' AND '2024-12-31'` — the function prevents
the optimizer from using partition metadata), (2) implicit type casting in the WHERE
clause causing the optimizer to give up on pruning, (3) the filter column is not the
partition key. Training analysts to write partition-friendly SQL is as important as
technical configuration.

---

## Part 7: ETL vs. ELT — The Pipeline Paradigm Shift

### 7.1 The Old Way: ETL

Extract-Transform-Load (ETL) is the traditional approach to moving data from source
systems to a warehouse. The sequence:

1. **Extract**: Pull raw data from source systems (Postgres, APIs, log files)
2. **Transform**: Process and clean the data using a separate compute system (a Spark
   cluster, a Python script, a dedicated ETL server)
3. **Load**: Load the clean, transformed data into the data warehouse

The transformation happens *outside* the warehouse, before loading. This made sense
historically because warehouses were expensive and slow to run arbitrary compute on.
You didn't want to use precious warehouse capacity for data cleaning. Data warehouses
before cloud (Teradata, IBM Netezza) charged by the hour for the appliance, making
compute precious.

```
ETL Architecture:

Source DB → Extract → [Spark/Python Transform] → Load → Warehouse (only clean data)
                              ↑
                   Transformation happens HERE
                   (outside the warehouse)
```

Problems with ETL:
- **Transformation logic lives in code** (Python/Spark), making it hard for data analysts
  (who know SQL) to understand or modify
- **Complex orchestration**: Spark jobs need clusters, Docker containers, dependencies
- **Debugging is hard**: When a transformation fails, you might have to re-extract
- **Schema evolution is painful**: If the source schema changes, the transformation code
  breaks in non-obvious ways

### 7.2 The Modern Way: ELT

Extract-Load-Transform (ELT) reverses the middle two steps. Raw data goes into the
warehouse *first*, then transformations are written in SQL and run *inside* the warehouse.

1. **Extract**: Pull raw data from source systems
2. **Load**: Load raw, unmodified data into a staging area in the warehouse
3. **Transform**: Write SQL transformations that build clean tables from the raw staging
   tables, running inside the warehouse's MPP compute

```
ELT Architecture:

Source DB → Extract → Load → Staging Layer → [SQL/dbt Transform] → Clean Tables
                              (raw, dirty)         ↑
                                       Transformation happens HERE
                                       (INSIDE the warehouse, using SQL)
```

### 7.3 Why ELT Won

Three things happened in the 2015-2020 period that made ELT viable and ETL obsolete:

**Cheap cloud storage**: S3 and GCS cost $0.023 per GB per month. Storing raw, dirty data
is essentially free. The old concern about wasting expensive warehouse storage on dirty
data disappeared.

**Cheap cloud compute**: BigQuery, Redshift, and Snowflake can throw hundreds of compute
nodes at a SQL transformation and finish in minutes what would have taken hours. Doing
transformations "in the warehouse" is no longer slow or expensive.

**dbt (data build tool)**: dbt productionized SQL-based transformations with software
engineering best practices: version control, testing, documentation, modular
dependencies, incremental processing. With dbt, a data analyst can write SQL
transformations that are automatically tested, documented, and deployed.

The practical result: Fivetran loads raw data from 300+ sources into your warehouse in
minutes. dbt runs SQL to clean and model that data inside the warehouse. Airflow
schedules the pipeline. The engineering team's involvement in the data pipeline dropped
dramatically.

### 7.4 Incremental vs. Full Refresh

For small tables, transformations can re-process the entire table every time (full
refresh). For large fact tables (billions of rows), this is prohibitively expensive.

Incremental processing: each run only processes rows that arrived since the last run.

```
Incremental Logic (in dbt):

-- Only process rows created after the last run
{% if is_incremental() %}
WHERE created_at > (SELECT MAX(created_at) FROM {{ this }})
{% endif %}
```

The challenge: incremental models require careful handling of late-arriving data
(events that arrive in the pipeline hours or days after they occurred), deduplication
(the same event might arrive twice due to at-least-once delivery), and schema changes
(adding a new column requires a full refresh or backfill).

### 7.5 Real Incident: The $50K/Month BigQuery Bill

Airbnb's data team (per public talks) ran a full refresh of their main events fact table
every night in BigQuery. The table had 10+ trillion rows (years of event data). Each full
refresh scanned the entire table, at BigQuery's then-pricing of $5 per TB, resulting in
a monthly bill that rivaled a small engineering team's salary.

The fix was incremental processing: each night's run only processes that day's new events,
then appends to the fact table. The table itself accumulates data, but the nightly job
only touches 1/365th of the data. The monthly BigQuery cost dropped by 99%.

The lesson: always design pipelines with incremental processing in mind from day one.
It's much harder to retrofit incrementality into a pipeline designed for full refresh.

---

### Brainstorming Q&A for Part 7

**Q: What are the risks of ELT — is there anything ETL does better?**

ELT has real weaknesses that are often understated. The first is governance: when raw,
uncleaned data is loaded directly into the warehouse, it may contain PII (personally
identifiable information) that should not be accessible to all analysts. An ETL pipeline
can strip or anonymize sensitive fields *before* they enter any system that analysts
access. With ELT, you need to implement column-level access controls inside the warehouse
to prevent analysts from seeing raw PII in staging tables.

The second weakness is transformation complexity. SQL is powerful for many transformations,
but not for all. Complex ML feature engineering, natural language processing of text
fields, or graph computations on relational data are awkward or impossible in SQL. These
transformations still benefit from Spark or Python, leading to a hybrid: ELT for
standard data cleaning and modeling, ETL for complex feature engineering.

Third, debugging ELT pipelines can be harder when something goes wrong. A raw staging
table with bad data causes multiple downstream dbt models to fail in confusing ways.
Mature data teams address this with schema tests and data quality checks in dbt that run
as the first step before any transformations.

**Q: What is Change Data Capture (CDC) and how does it fit with ELT?**

Change Data Capture is a technique for extracting not just the current state of a database
table, but the stream of changes (inserts, updates, deletes) that have occurred. This is
done by reading the database's transaction log (Postgres's WAL, MySQL's binlog) rather
than querying the table directly.

CDC is the key technology for near-real-time ELT. Instead of polling the source database
every hour and scanning for rows where `updated_at > last_run_time`, CDC streams every
individual change as it happens, with subsecond latency. Tools like Debezium read the
transaction log and publish changes to Kafka topics, which are then consumed by the
warehouse loader.

The benefit: your warehouse is minutes (or seconds) behind the source, not hours. The
challenge: deletes in the source must be tracked as explicit events (since the row is
gone, you can't detect a deletion by scanning the table), and the consumer must handle
the out-of-order events that CDC occasionally produces. For data warehouses that need
"fresh" data for operational dashboards, CDC is increasingly the standard approach.

---

## Part 8: BigQuery vs. Redshift vs. Snowflake — Choosing Your Warehouse

### 8.1 The Three Major Players

The cloud data warehouse market is dominated by three platforms, each with a distinct
architecture and philosophy. Understanding the differences is essential for an L6
interview, where "which warehouse do you recommend?" is a common question.

```
Architecture Comparison:

BigQuery (Google):
  ┌───────────────────────────────────────────────────────┐
  │  Serverless: No cluster to manage                     │
  │  Storage: Google Colossus (GCS-like, columnar)        │
  │  Compute: Dremel workers from shared pool (slots)     │
  │  Pricing: $5/TB scanned (on-demand) or slot reservations│
  │  Strong at: Ad-hoc large queries, serverless simplicity│
  └───────────────────────────────────────────────────────┘

Redshift (Amazon):
  ┌───────────────────────────────────────────────────────┐
  │  Provisioned: You choose node type and count          │
  │  Storage: Local NVMe SSDs on nodes (or RA3 = S3)     │
  │  Compute: Fixed cluster (burst with concurrency scaling)│
  │  Pricing: Per node per hour ($0.25 - $13/node/hr)    │
  │  Strong at: Predictable workloads, AWS ecosystem     │
  └───────────────────────────────────────────────────────┘

Snowflake (Cloud-agnostic):
  ┌───────────────────────────────────────────────────────┐
  │  Virtual Warehouses: Separate compute clusters       │
  │  Storage: S3 / Azure Blob / GCS (micro-partitions)  │
  │  Compute: Auto-suspend/resume virtual warehouses     │
  │  Pricing: Per credit (compute) + storage separately  │
  │  Strong at: Multi-workload, multi-cloud, data sharing│
  └───────────────────────────────────────────────────────┘
```

### 8.2 BigQuery — Serverless, Pay Per Query

BigQuery is Google's serverless warehouse. "Serverless" means you do not provision or
manage any cluster. You create a dataset, load data, and run SQL. BigQuery automatically
scales to thousands of workers for large queries and scales to zero when no queries are
running.

**Pricing model**: On-demand pricing charges $5 per TB of data scanned. A query scanning
100 GB costs $0.50. A query scanning 10 TB costs $50. This pricing aligns cost directly
with query efficiency: well-partitioned, clustered tables that use predicate pushdown
cost far less to query than unoptimized tables.

**Strengths**:
- No infrastructure management — no clusters to size, manage, or upgrade
- Extreme scale: BigQuery regularly handles petabyte-scale queries
- Integration with Google's ML stack (BigQuery ML for in-database ML)
- Automatic optimization (the optimizer often finds query plans humans wouldn't think of)

**Weaknesses**:
- Cost unpredictability: a poorly written query (full table scan on a petabyte table)
  results in a surprise bill
- Latency: slot allocation from a shared pool takes milliseconds to seconds, which can
  be noticeable for interactive dashboards (though slot reservations mitigate this)
- Proprietary format: data is stored in Colossus in Capacitor format, not open Parquet
  (you can export to Parquet, but the native format is not open)

**Best for**: Companies on GCP, sporadic large ad-hoc queries, teams that don't want
to manage infrastructure, ML-heavy analytics workloads.

### 8.3 Redshift — Provisioned, AWS-Native

Amazon Redshift is the AWS-native data warehouse. You provision a cluster of nodes
(choosing node type: ra3.xlplus, ra3.4xlarge, etc.) and pay per hour for running nodes.
Modern Redshift (RA3 nodes) separates compute from storage by storing data in S3 and
caching hot data on local NVMe SSDs — giving you local disk speed for frequently
accessed data while unbounded S3 storage.

**Pricing model**: Fixed hourly cost per node. A 2-node ra3.4xlarge cluster costs roughly
$2/hour = $1,440/month. Costs are predictable but don't scale to zero (you pay when the
cluster is idle unless you pause it).

**Strengths**:
- Predictable costs for steady, high-throughput workloads
- Local disk caching (RA3) = very low latency for hot data
- Deep AWS ecosystem integration (S3, Lambda, Glue, QuickSight)
- AQUA (Advanced Query Accelerator): hardware-accelerated compression/filtering on
  storage nodes, offloading work from compute

**Weaknesses**:
- Cluster sizing is manual (though auto-scaling exists, it's limited)
- Managing cluster health, vacuum operations, and sort key maintenance requires DBA work
- Concurrency at scale requires careful configuration (WLM queues)
- Less flexible for multi-cloud scenarios

**Best for**: Companies on AWS with predictable, high-throughput analytics workloads
(e.g., a product analytics team running thousands of scheduled reports daily).

### 8.4 Snowflake — Flexible, Multi-Cloud

Snowflake is cloud-agnostic (runs on AWS, Azure, or GCP with the same interface) and
pioneered the concept of "virtual warehouses" — separate compute clusters for separate
workloads, all sharing the same underlying storage.

**Architecture**: Data is stored in S3/Azure/GCS as micro-partitions (Snowflake's internal
columnar format, similar to Parquet but with automatic clustering metadata). Virtual
warehouses (XS to 6XL, each doubling the compute) run SQL queries by reading from this
shared storage. You can have 10 virtual warehouses — one for BI, one for data science,
one for ETL — all hitting the same data without contention.

**Pricing model**: Per-credit pricing (compute) + per-TB storage. Virtual warehouses
auto-suspend when idle (configurable: suspend after 1 minute of no queries), so you only
pay when queries are running.

**Strengths**:
- Multi-cloud: run on GCP today, migrate to AWS tomorrow without data migration
- Workload isolation: each team gets their own compute without infrastructure ownership
- Data sharing: share data with partners or other Snowflake accounts without copying data
- Time travel: query historical versions of data for up to 90 days
- Zero-copy cloning: clone entire databases for dev/test without duplicating storage

**Weaknesses**:
- Per-credit pricing can be expensive for sustained, predictable workloads (vs. Redshift's
  fixed hourly cost)
- Storage format is proprietary (not Parquet natively, though external tables can read Parquet)
- Cold starts: a suspended virtual warehouse takes a few seconds to resume

**Best for**: Multi-cloud companies, organizations with multiple teams having different
compute needs, companies that want to share data externally with partners.

### 8.5 Real Story: The Snowflake to Redshift Migration

A payments company (similar to stories from public Redshift case studies) ran Snowflake
for 3 years. It worked well initially, but as their query volume grew to 200,000 queries
per day with a consistent pattern (mostly scheduled reports), Snowflake's per-credit
pricing became expensive. The predictable workload meant they were paying for on-demand
pricing when reserved pricing would have been much cheaper.

They migrated to Redshift RA3 nodes, pre-purchasing reserved instances for 3 years at
a 70% discount from on-demand pricing. Annual savings: ~$800,000. The migration took
6 months and required translating Snowflake SQL to Redshift SQL (small syntax
differences), rebuilding their dbt configuration, and reprocessing historical data.

The lesson: the "right" warehouse depends on workload pattern. Sporadic = serverless
(BigQuery or Snowflake auto-suspend). Predictable/high-volume = provisioned (Redshift
reserved). Mixed = Snowflake's middle ground is often good but not always cheapest.

### 8.6 Feature Comparison Table

```
┌───────────────────────┬──────────────────┬──────────────────┬──────────────────┐
│ Dimension             │ BigQuery         │ Redshift         │ Snowflake        │
├───────────────────────┼──────────────────┼──────────────────┼──────────────────┤
│ Architecture          │ Serverless       │ Provisioned      │ Virtual WH       │
│ Storage format        │ Capacitor (prop) │ RA3 = S3 + cache │ Micro-partitions │
│ Compute scaling       │ Auto (slots)     │ Manual + burst   │ Auto-suspend     │
│ Pricing model         │ Per TB scanned   │ Per node/hour    │ Per credit       │
│ Scale to zero         │ Yes (automatic)  │ No (pause only)  │ Yes (auto-suspend│
│ Multi-cloud           │ No (GCP only)    │ No (AWS only)    │ Yes              │
│ Concurrency model     │ Slot pooling     │ WLM queues       │ Multi-VWH        │
│ Data sharing          │ Analytics Hub    │ Data Sharing     │ Best-in-class    │
│ Time travel           │ 7 days           │ No native        │ Up to 90 days    │
│ Zero-copy clone       │ No               │ No               │ Yes              │
│ Built-in ML           │ BigQuery ML      │ Redshift ML      │ Snowpark ML      │
│ Best ecosystem        │ GCP/Google       │ AWS              │ Multi-cloud      │
│ Ideal workload        │ Sporadic large   │ Sustained heavy  │ Variable, multi  │
└───────────────────────┴──────────────────┴──────────────────┴──────────────────┘
```

---

### Brainstorming Q&A for Part 8

**Q: When should you choose BigQuery over Snowflake if both support sporadic workloads?**

The primary differentiator is cloud ecosystem. If your company is already on GCP (using
GKE, Cloud Run, Pub/Sub, Vertex AI), BigQuery is the natural choice because of
deep integration: Pub/Sub events can stream directly to BigQuery with no code, Vertex AI
training jobs can read from and write to BigQuery natively, Cloud Composer (Airflow) has
native BigQuery operators. The cost of operating across cloud boundaries (data egress
fees, authentication complexity) often exceeds the price difference between warehouses.

If you're multi-cloud or on AWS/Azure, Snowflake's cloud-agnostic position is valuable.
Snowflake also has a more mature data sharing ecosystem and better zero-copy clone
functionality for development workflows. For teams that need to share data externally
(providing a data product to enterprise customers), Snowflake's data sharing is
best-in-class. BigQuery's Analytics Hub is catching up but isn't quite at parity.
Ultimately, an L6 decision would start with "what cloud are you on and what ecosystem
integrations matter most" before comparing warehouse-specific features.

**Q: Is it ever the right answer to run your own data warehouse on-premise instead of using a cloud managed service?**

Yes, for specific industries and requirements. Financial services companies (large banks,
hedge funds), healthcare organizations handling sensitive patient data, and government
agencies often have regulatory requirements (FedRAMP, ITAR, data residency laws) that
make cloud hosting complex or prohibited for certain data categories. For these
organizations, running their own data warehouse (often Apache Hive on HDFS, or Teradata,
or ClickHouse) on-premise or in a private cloud is the only viable option.

For most companies without those constraints, the operational burden of managing
on-premise data warehouse infrastructure outweighs the cost savings. Cloud managed
services handle hardware failures, software upgrades, security patches, scaling, and
backup automatically. The engineering time saved (easily 2-5 senior engineers) costs
more than the delta between cloud and on-premise. A startup that tries to run its own
data warehouse to save money usually finds it spent far more engineering time on
infrastructure than on building analytics capabilities.

---

## Part 9: Real-Time Analytics and Lambda/Kappa Architecture

### 9.1 The Real-Time Analytics Problem

Traditional batch ETL pipelines update the warehouse once a day (nightly runs) or at
best hourly. For most analytics use cases — quarterly reports, weekly metrics, data
science model training — this is fine. But some use cases require fresher data:

- **Operational dashboards**: A delivery company's ops team needs to see how many deliveries
  are currently "out for delivery" vs "delayed" — data that is minutes old is useless
- **Fraud detection**: A payment system needs to flag suspicious patterns within seconds
- **Live event analytics**: A streaming service needs to see concurrent viewers during a
  major live event in real time
- **A/B test monitoring**: A product team running an experiment wants to see results within
  hours, not wait until the next morning's pipeline run

These use cases require a different architecture than batch warehousing.

### 9.2 The Lambda Architecture

The Lambda Architecture (coined by Nathan Marz, circa 2012) addresses this by running
two parallel pipelines:

```
Lambda Architecture:

Source Events
      │
      ├──────────────────────────────────────────────────────────┐
      │                                                          │
      ▼                                                          ▼
 Speed Layer                                             Batch Layer
 (Kafka + Flink/Spark Streaming)                        (Spark Batch or
 Near-real-time processing                               warehouse ETL)
 Low latency (seconds)                                  High latency (hours)
 Approximate or incomplete                               Accurate and complete
      │                                                          │
      ▼                                                          ▼
 Real-time views                                         Batch views
 (in Redis, Druid, Pinot)                               (in data warehouse)
      │                                                          │
      └─────────────────────┬────────────────────────────────────┘
                            │
                            ▼
                      Serving Layer
                   (merges real-time + batch views)
                            │
                            ▼
                     Dashboard / API
```

The speed layer processes recent events and provides low-latency approximate results.
The batch layer processes all historical events and provides accurate, complete results.
The serving layer merges them: "show me real-time data for the last 2 hours, batch data
for everything older."

**Problems with Lambda**: You maintain two completely separate codebases (streaming logic
and batch logic) that are supposed to produce the same results. In practice they diverge.
Debugging discrepancies between the speed layer and batch layer is a nightmare. Engineers
hate it.

### 9.3 The Kappa Architecture

The Kappa Architecture (proposed by Jay Kreps of Confluent, 2014) simplifies Lambda by
eliminating the batch layer entirely. Everything goes through the streaming pipeline.
Historical reprocessing is done by replaying the stream from Kafka (which retains
messages for a configurable duration, potentially forever on S3-backed log storage).

```
Kappa Architecture:

Source Events → Kafka (source of truth, retained indefinitely)
                     │
                     ├──── Real-time consumers (Flink, Spark Streaming)
                     │         → Write results to serving store
                     │
                     └──── Historical reprocessing (replay Kafka from beginning)
                               → Same code as real-time consumers
                               → Produces accurate historical views
```

The key insight: if Kafka retains all events permanently (feasible with cheap S3-backed
Kafka, such as Amazon MSK with tiered storage), you can always replay history through
the same streaming logic that processes real-time events. One codebase, not two.

**Problems with Kappa**: Replaying years of events for a full historical reprocess takes
time (hours or days). The streaming processing model (Flink, Spark Streaming) is harder
to reason about than batch SQL. State management in streaming systems is complex.

### 9.4 OLAP Databases Designed for Real-Time: Druid, ClickHouse, Pinot

Traditional warehouses (BigQuery, Redshift, Snowflake) are optimized for batch-loaded
data. A new category of real-time OLAP databases has emerged that can ingest streaming
data at millions of rows per second while simultaneously serving sub-second analytical
queries:

**Apache Druid**: Originally built at Metamarkets (now part of Imply), adopted by
Airbnb, Netflix, Twitter. Real-time ingestion from Kafka, sub-second queries on time-
series data. Optimized for event analytics and time-series aggregations.

**ClickHouse**: Open-source, developed by Yandex. Extremely fast columnar OLAP with
real-time ingestion. Commonly used for product analytics (Segment, PostHog are built on
it), observability, and log analytics. Often cited as the fastest OLAP engine for
analytical queries on a single table.

**Apache Pinot**: Developed at LinkedIn, now open source at Apache. Real-time OLAP with
upsert support (can update existing records). Used by LinkedIn, Uber, and Stripe for
user-facing analytics (e.g., "show me my profile views in real time").

```
Real-Time OLAP vs. Traditional Warehouse:

┌────────────────────┬──────────────────────┬────────────────────────┐
│ Dimension          │ Data Warehouse       │ Real-Time OLAP         │
│                    │ (BigQuery/Redshift)  │ (Druid/ClickHouse/Pinot│
├────────────────────┼──────────────────────┼────────────────────────┤
│ Data freshness     │ Hours to days        │ Seconds to minutes     │
│ Query latency      │ Seconds to minutes   │ Milliseconds           │
│ Data model         │ Star schema, SQL     │ Time-series, flat      │
│ Ingestion          │ Batch (S3, Kafka)    │ Streaming (Kafka)      │
│ User-facing?       │ Internal analysts    │ Yes (API-serving)      │
│ Complexity         │ Lower               │ Higher                  │
│ SQL support        │ Full ANSI SQL        │ Limited (varies)       │
│ Join support       │ Full                 │ Limited (denormalized) │
│ Cost               │ Pay per query        │ Provisioned cluster    │
└────────────────────┴──────────────────────┴────────────────────────┘
```

### 9.5 Real Incident: Netflix Switching from Hive to Presto (Trino)

Netflix's data platform (publicly documented in engineering blog posts) ran on Apache
Hive for years. Hive translates SQL queries into MapReduce jobs, which are reliable and
scalable but notoriously slow: even simple queries take 10-15 minutes because MapReduce
starts YARN containers, reads from HDFS, and writes intermediate results to disk at every
stage.

Netflix data scientists were frustrated: exploring a dataset required waiting 15 minutes
per query iteration. Exploratory analysis that should take an afternoon took days.

In 2013, Netflix evaluated Facebook's Presto (now Trino), a distributed SQL engine
designed for interactive analytics on data in S3/HDFS. Presto processes queries entirely
in memory (no MapReduce, no disk writes for intermediates), executes pipelines stages in
parallel, and returns results in seconds to minutes instead of minutes to tens of minutes.

Netflix adopted Presto for ad-hoc analytics (analysts' queries) while keeping Hive for
batch ETL jobs (where Hive's reliability and integration with the Hadoop ecosystem still
had advantages). The result: analyst query latency dropped from 15+ minutes average to
under 2 minutes average. Data scientist productivity increased measurably.

The lesson: different query patterns need different engines. Interactive exploration
needs fast, in-memory execution. Large scheduled batch jobs can tolerate slower,
disk-spilling execution in exchange for greater fault tolerance.

---

### Brainstorming Q&A for Part 9

**Q: When should you use a real-time OLAP system (ClickHouse/Druid/Pinot) vs. a traditional data warehouse?**

The key questions are: (1) How fresh does the data need to be? and (2) Who is the
consumer? If data science analysts can wait until tomorrow's pipeline run, a traditional
warehouse is simpler and cheaper. If operational teams need data that is minutes old, or
if the analytics are user-facing (shown in a product UI to end users), you need real-time
OLAP.

The second question (who is the consumer) is critical. Traditional warehouses are
designed for internal analytics where query latency of seconds to minutes is acceptable.
Real-time OLAP databases are designed for sub-second query responses, making them
suitable for user-facing product features: "show me my spending analysis for this month"
(Stripe), "show me who viewed my post" (LinkedIn/Pinot), "show me how many users are
in each A/B test variant right now" (Optimizely/Druid). If your query serves an API that
a user is waiting for, use a real-time OLAP system. If your query runs in a data analyst's
notebook, use a traditional warehouse.

**Q: What is materialized view and how is it different from a regular view?**

A regular view is a saved SQL query. Every time you query the view, the SQL is executed
against the underlying tables. No data is stored separately for the view itself. Views
are convenient (you write the query once) but don't improve performance because the
underlying tables are still scanned every time.

A materialized view is a pre-computed and stored snapshot of the view's query results.
The warehouse runs the SQL periodically and stores the results as an actual table.
Queries against the materialized view read the pre-computed results directly, which is
much faster for expensive aggregations. The trade-off: the data is only as fresh as the
last refresh (which might be hours ago), and storage is needed for the pre-computed
results. Modern systems like BigQuery support "continuous" materialized views that
update automatically as the underlying data changes (within seconds to minutes), blurring
the line between batch materialized views and real-time OLAP.

---

## Part 10: Data Lake vs. Data Warehouse vs. Lakehouse

### 10.1 Definitions and the Evolution of Thinking

The database world has accumulated three related but distinct concepts over the past
decade. Understanding the distinction — and why the industry is converging toward one
approach — is important for any senior engineering role.

**Data Warehouse**: Structured, schema-on-write, optimized for SQL analytics. Raw data is
cleaned and modeled before landing in the warehouse. Tight schema enforcement means
queries are fast and reliable, but the schema must be defined upfront, and changing it
requires migration work.

**Data Lake**: Unstructured, schema-on-read, stores raw data in open formats (Parquet,
JSON, CSV, Avro) on cheap object storage (S3, GCS). Anything can land: structured tables,
semi-structured JSON, images, audio files. Schema is applied at query time. Extremely
flexible and cheap to store, but querying is slower (no optimization metadata) and data
quality is "garbage in, garbage out."

**Data Lakehouse**: A newer architectural pattern that combines the best of both: raw
data stored in open formats on object storage (like a data lake), but with table metadata,
ACID transactions, schema enforcement, and query optimization (like a warehouse).

```
Data Architecture Evolution:

Phase 1 — Data Warehouse only:
  Source → ETL → Structured Warehouse → BI
  ✓ Fast queries, clean data
  ✗ Expensive storage, rigid schema, raw data lost

Phase 2 — Data Lake + Warehouse:
  Source → Data Lake (raw) → ETL → Warehouse → BI
            ↓
          Data Science (Python, Spark on S3)
  ✓ Raw data retained, flexible for DS
  ✗ Two systems to manage, data swamp problem

Phase 3 — Lakehouse:
  Source → Lakehouse (raw Parquet + Delta/Iceberg metadata)
            → SQL (warehouse-quality queries directly on Parquet)
            → BI Tools
            → Data Science (Python, Spark on same data)
  ✓ One system, open formats, warehouse performance
  ✗ Still newer, operational complexity
```

### 10.2 The Data Lake Problem — The Data Swamp

Data lakes promised to solve the inflexibility of warehouses by storing everything.
In practice, many data lakes became "data swamps": enormous S3 buckets full of Parquet
files with no documentation, no consistent naming, no schema enforcement, no data
quality. Files were written with different schemas by different teams. Partitioning was
inconsistent. Deletes were impossible (old files just accumulated). Finding the right
data required tribal knowledge.

The fundamental problem: a file system (S3) is not a database. It has no transactions,
no schema registry, no indexing, no way to update a row without reading and rewriting
the entire file. Treating S3 as a database requires adding a layer on top.

### 10.3 Delta Lake and Apache Iceberg — The Lakehouse Foundation

Two open-source projects emerged to add database functionality on top of object storage:

**Delta Lake** (Databricks, 2019): A transaction log stored alongside Parquet files in
S3. The transaction log records every write operation, making the entire state of the
table recoverable at any point in time. This enables:
- ACID transactions (multiple files written atomically)
- Time travel (query the table as it was 30 days ago)
- Schema enforcement (writes with wrong schema are rejected)
- Efficient upserts and deletes (using merge logic that rewrites only affected files)
- Optimized reading (the transaction log tells the query engine which files to read)

**Apache Iceberg** (Netflix, 2018, now Apache top-level project): Similar goals to Delta
Lake but with a different metadata architecture designed for even better query planning
and partition evolution. Iceberg supports partition spec changes without rewriting data
(you can change from monthly to daily partitioning without migrating existing files),
hidden partitioning (the user doesn't need to write `WHERE year=2024 AND month=01`,
Iceberg figures out the partitions from `WHERE created_at BETWEEN '2024-01-01' ...`),
and snapshot isolation.

**Apache Hudi** (Uber, 2019): Focuses on efficient record-level upserts on large tables,
designed for the use case of "change data capture from OLTP systems into a data lake."

### 10.4 The Modern Lakehouse Stack

The industry is converging on a "lakehouse" pattern:

```
Modern Lakehouse Architecture:

Ingestion Layer:
  Kafka → Flink/Spark Streaming → write to Parquet + Delta/Iceberg metadata in S3

Storage Layer:
  S3/GCS/ADLS
  Parquet files + Delta Lake / Iceberg transaction log
  Open format: any tool can read

Compute Layer (multiple engines, same data):
  ┌─────────────┬──────────────┬──────────────────┐
  │  Spark      │  Trino/Presto│  dbt + BigQuery  │
  │  (batch ML) │  (ad-hoc SQL)│  (scheduled SQL) │
  └─────────────┴──────────────┴──────────────────┘
  All reading the same Parquet files via same Delta/Iceberg metadata

Governance Layer:
  Unity Catalog (Databricks) / Hive Metastore / AWS Glue
  Schema registry, access control, lineage

Serving Layer:
  BI tools / APIs / ML models
```

The key benefit: different compute engines (Spark for ML, Trino for ad-hoc queries, dbt
for SQL modeling) all read the same data in the same format. No more "the ML team's data
and the analytics team's data are different."

### 10.5 When to Choose Each Architecture

```
Decision Framework:

Question 1: Do you have structured data only, or mixed (JSON, logs, images, etc.)?
  → Structured only: consider warehouse
  → Mixed: consider lakehouse or data lake + warehouse

Question 2: Do you need ML training on raw events, or just SQL analytics?
  → SQL analytics only: warehouse is simpler
  → ML training on raw events: lakehouse gives Spark/Python access to raw data

Question 3: How mature is your data team?
  → Small/early: managed warehouse (BigQuery/Snowflake) is simplest
  → Mature, large: lakehouse offers more flexibility and potentially lower cost

Question 4: What is your cloud budget constraint?
  → Unlimited: Snowflake/BigQuery managed convenience
  → Cost-sensitive: Trino/Presto on Iceberg on S3 is much cheaper but requires
    more operational work

Question 5: Do you need to share data externally?
  → Internal only: any choice works
  → External partners: Snowflake Data Sharing or Delta Sharing is easiest
```

---

### Brainstorming Q&A for Part 10

**Q: Is the data lakehouse architecture actually simpler than running a separate data lake and data warehouse?**

This is a nuanced question. At mature engineering organizations with experienced data
engineers, the lakehouse reduces the number of systems (no ETL pipeline between lake and
warehouse, no data duplication) and maintains open formats (avoiding vendor lock-in). The
operational complexity shifts from "maintaining two separate systems" to "maintaining
complex Delta/Iceberg metadata and a catalog service."

For smaller teams or teams without data engineering expertise, the managed warehouse
(BigQuery, Snowflake) is almost always simpler because the vendor handles all the
metadata management, optimization, and operational complexity. A Databricks Lakehouse
is a powerful platform but requires understanding of Spark, Delta Lake internals, cluster
management, and more. A startup with 3 engineers choosing between BigQuery and building
a Databricks lakehouse should almost always choose BigQuery.

The lakehouse becomes the right answer when you have both large-scale analytics needs
*and* large-scale ML needs on the same data, and you want to avoid paying twice for
storage and avoid copying data between systems. At Uber, Airbnb, and similar companies
with mature data platforms, the economics favor the lakehouse. For most companies, the
managed warehouse is the right starting point.

**Q: What is "schema on read" vs "schema on write" and why does it matter for data quality?**

Schema on write (data warehouse): when you load data into the warehouse, it must conform
to a pre-defined schema. If a source sends a null in a non-nullable column, or sends a
string where an integer is expected, the write fails. This enforces data quality at
ingestion time and means that any data you successfully read from the warehouse is
guaranteed to conform to the schema. The downside: you must define the schema before you
have the data, which is hard for new data sources or rapidly evolving schemas.

Schema on read (data lake): data is stored as-is (raw Parquet, JSON, CSV). The schema is
only applied when you try to read the data. This means you can ingest data from any
source without upfront schema definition. The downside: "garbage in, garbage out." If
source data has quality issues, you won't know until you try to query it, potentially
weeks or months later, and the pipeline has already ingested months of bad data.

The lakehouse approach tries to get the best of both: data is stored in open formats
(schema on read flexibility) but schema enforcement is applied via the Delta/Iceberg
layer (schema on write reliability). You can define a schema for Delta tables that
rejects writes with wrong schemas while still keeping the data in open Parquet format.

---

## Part 11: Interview Application — L6 Data Warehouse Questions

### 11.1 How Data Warehouse Questions Appear in L6 Interviews

Data warehouse topics appear in three forms at L6 system design interviews:

**Form 1: Direct analytics system design**
"Design an analytics platform for 1 billion user events per day that allows the data
science team to query event data and build ML models."

**Form 2: Embedded in product system design**
"Design a ride-sharing platform" — and the interviewer probes "how do you track driver
earnings over time and generate weekly statements?" or "how do your data scientists
analyze rider behavior patterns?"

**Form 3: Trade-off discussion**
"We're running analytics on Postgres and it's getting slow. What would you recommend?"
Or: "Should we use a data lake or a data warehouse for this use case?"

### 11.2 The L5 vs. L6 Calibration

This is the critical distinction. L5 and L6 candidates both know that BigQuery, Redshift,
and Snowflake exist. The differentiation happens in depth.

**L5 answer pattern**: "I'd use BigQuery for analytics. It scales well and is managed.
We'd run ETL to move data from Postgres to BigQuery using Fivetran. Then analysts can
query it with SQL."

This is correct but shallow. It does not demonstrate understanding of *why* BigQuery
works well for analytics, *how* it executes queries efficiently, or *what design decisions*
in the data model and pipeline determine whether the system performs well.

**L6 answer pattern**: "For analytics at this scale, we need columnar storage because
analytics queries read a few columns across many rows — columnar avoids reading the
90% of data that isn't needed. I'd design a star schema with a fact table for events
and dimension tables for users, products, and dates — this lets the query engine use
predicate pushdown against small dimension tables before hitting the large fact table.

"For the pipeline, I'd use Fivetran or CDC (via Debezium into Kafka) for ingestion and
dbt for SQL-based transformations inside the warehouse — ELT pattern, raw data lands
first, transformations are versioned SQL. For the fact table, I'd partition by event_date
and cluster by user_id, because most analytics queries filter by date range and user
cohort. This reduces scanned data by 95%+ compared to a flat unpartitioned table.

"For data freshness, I'd ask the team: does data science need today's data for model
training, or is yesterday's data acceptable? If today's data is needed, we add a
streaming path: Kafka → Flink → BigQuery Storage Write API for near-real-time ingestion.

"The biggest risk is pipeline reliability — ETL pipelines fail silently, so I'd add dbt
data quality tests (null checks, uniqueness, referential integrity) that run after each
pipeline execution and alert on failures before analysts encounter bad data."

That's an L6 answer. It covers: why columnar, data model design (star schema), partition
key reasoning, pipeline pattern (ELT), incremental processing implication, data freshness
trade-off, and data quality. Each of these was a deliberate design decision with
justification, not a name-drop.

### 11.3 Common Interview Mistakes

**Mistake 1: Recommending Postgres with read replicas as the final answer**
Postgres read replicas are a reasonable interim solution for companies with hundreds of
millions of rows and a few analysts. At billions of rows or dozens of analysts, it is
clearly the wrong answer. An L6 candidate should recognize the limit and know when to
cross the threshold to a proper warehouse.

**Mistake 2: Naming the warehouse without explaining why**
Saying "I'd use BigQuery" without explaining columnar storage, MPP, or partition pruning
is like saying "I'd use Postgres" for a social network without explaining the indexing
strategy or connection pooling. The name means nothing if you can't explain the mechanics.

**Mistake 3: Ignoring the data pipeline**
Many candidates design the warehouse data model beautifully but completely ignore how
data gets from the source systems to the warehouse. The warehouse is the destination; the
pipeline is equally important. Ignoring it is like designing a beautiful restaurant without
thinking about the supply chain. Address ETL/ELT patterns, CDC, incremental processing,
and data quality explicitly.

**Mistake 4: Designing a normalized schema for a warehouse**
A warehouse is not a transactional database. Normalized schemas (1NF, 2NF, 3NF) with many
foreign keys are correct for OLTP. For analytics, a denormalized star schema with
pre-joined dimension tables dramatically reduces query complexity and improves performance.
Recommending a normalized schema for a warehouse signals a fundamental misunderstanding
of the different design requirements.

**Mistake 5: Ignoring data freshness requirements**
Different teams have different freshness needs. Finance needs last month's numbers by the
5th of next month — daily pipeline is fine. Operations needs to see current delivery
status — hourly or real-time. ML feature engineering usually works fine with yesterday's
data. Failing to ask about freshness requirements before designing the pipeline is a
scoping mistake that leads to over-engineered (always building a streaming pipeline when
daily batch is sufficient) or under-engineered (building batch when real-time is needed)
solutions.

**Mistake 6: Conflating data lake with data warehouse**
These are different tools for different jobs. A data lake (raw files in S3) is great for
flexible storage and ML training on raw events. A data warehouse (BigQuery, Redshift) is
great for SQL analytics with fast query performance. Treating them as interchangeable, or
claiming that "we'll just put everything in S3 and query it with Athena" without
acknowledging the performance and governance trade-offs, misses the nuance.

### 11.4 The 5-Level Progression for Data Warehouse Concepts

**Intern level** — Knows that BigQuery and Redshift exist. Can write SQL. Knows what a
table is. Has run queries on a warehouse but doesn't know what happens underneath.

**Junior (L3) level** — Understands that warehouses are different from OLTP databases.
Has used partitioning and knows it makes queries faster. Has built a basic ETL pipeline
using a managed connector. Knows what a star schema looks like from a diagram.

**Mid (L4) level** — Can design a star schema for a given business domain. Understands
ETL vs ELT trade-offs and can justify the choice. Can explain partition pruning and choose
an appropriate partition key. Knows when to use BigQuery vs Redshift at a high level.

**Senior (L5) level** — Can design a complete data pipeline from source systems through
the warehouse to BI tools. Understands incremental processing and CDC. Can diagnose
warehouse performance issues (missing partitioning, missing clustering, inefficient joins).
Can evaluate and recommend between warehouse options based on workload patterns and
organizational constraints.

**Staff (L6) level** — Can design the full architecture including data freshness trade-
offs (streaming vs batch), data governance and quality controls, schema evolution
strategy, and data model that balances query performance with flexibility. Can reason about
the organizational impact of architectural choices (who owns the transformation logic,
how schemas are communicated to downstream consumers, how pipelines are monitored).
Understands the business context: what decisions will stakeholders make with this data,
and does the architecture enable those decisions efficiently?

### 11.5 The Key Trade-Offs to Articulate at L6

Every L6 answer needs trade-offs. In data warehouse design, the major ones are:

**Freshness vs. Cost**: Real-time ingestion (streaming pipeline) costs more than daily
batch. Ask whether daily freshness is acceptable before building a streaming pipeline.

**Query performance vs. Schema flexibility**: More denormalization and more partitions
improve query performance but make schema changes harder and increase storage. The right
balance depends on query patterns.

**ETL vs. ELT vs. hybrid**: ELT is simpler for SQL-friendly transformations but less
suitable for complex ML feature engineering. Many real systems use both.

**Managed warehouse vs. open lakehouse**: Managed is simpler to operate; open lakehouse
avoids vendor lock-in and can be cheaper at scale but requires more engineering.

**Batch vs. streaming ingestion**: Batch is simpler, cheaper, and more reliable. Streaming
is complex but necessary for real-time use cases. Most companies need both for different
data types.

---

### Brainstorming Q&A for Part 11

**Q: How do you handle schema evolution in a data warehouse — what happens when a source table adds a new column?**

Schema evolution is one of the most underestimated operational challenges in data
warehousing. When a source table adds a column, the downstream consequence depends on
the pipeline design. In a well-designed ELT pipeline with modern tools: (1) Fivetran
detects the new column in the source, automatically adds it to the staging table in the
warehouse, and starts loading values. (2) dbt models that don't reference the new column
are unaffected. (3) dbt models or downstream tables that need to use the new column
require a code change to add it.

The harder cases are column renames and column type changes. If a source renames `user_id`
to `customer_id`, the pipeline breaks unless it handles this explicitly. Fivetran and
Airbyte handle renames gracefully if they can detect them (via unique key matching).
Type changes (int to string) can cause type mismatch errors in downstream transformation
SQL. The best practice is to maintain a contract between source teams and the data
pipeline team: source schema changes are communicated in advance, not discovered when the
pipeline breaks at midnight.

For the warehouse schema itself (changes to the data model), dbt supports `schema.yml`
files that document expected column names and types. Running `dbt test` after a schema
change catches mismatches before they reach analysts.

**Q: What is data lineage and why is it important at scale?**

Data lineage tracks the origin and transformation history of every piece of data: which
source system did this column come from, which transformation modified it, which tables
depend on this table. At small scale, one person knows all of this in their head. At
large scale (thousands of tables, dozens of engineers), no one has the full picture.

Lineage becomes critical when: (1) a source system changes its data and you need to know
all downstream tables affected, (2) an analyst finds a suspicious number and needs to
trace it back to find where the error was introduced, (3) a legal or compliance team
asks "where does this customer's data live in our systems?" for a GDPR deletion request.

Tools like dbt generate lineage automatically (it knows which tables each model depends
on), Atlan and Alation provide catalog and lineage UI, and OpenLineage is an open standard
for emitting lineage events from Spark and Airflow. An L6 design should mention lineage
as part of the governance layer — not as an afterthought, but as a first-class
requirement that the architecture should support from day one.

**Q: How do you approach cost governance in a data warehouse — how do you prevent runaway query costs?**

Cost governance is a real operational concern, especially in BigQuery (where a single
poorly written query can scan petabytes) and Snowflake (where multiple large virtual
warehouses running simultaneously multiply costs). The approach has multiple layers.

At the warehouse level: set up spending alerts (BigQuery's budget alerts, Snowflake's
resource monitors) that notify when costs exceed thresholds. In BigQuery, use custom
quotas to limit the maximum TB a single user or project can scan per day. In Snowflake,
resource monitors can automatically suspend virtual warehouses when credit usage exceeds
a threshold.

At the SQL level: enforce query best practices through linting (dbt-utils has macros that
warn when a query lacks a partition filter on a large table). Some teams use a query
gateway that inspects SQL before submitting to BigQuery and rejects queries that will scan
more than X TB without a partition filter.

At the data model level: well-partitioned and clustered tables reduce costs for all users
automatically. A data platform team's highest-leverage investment is optimizing the most
expensive tables: adding partitioning and clustering to the top 10 most-scanned tables
often reduces overall warehouse costs by 50-80%.

---

## Common Interview Mistakes — Full Summary

To reinforce the list from Part 11 with additional context:

**Mistake 1: Postgres read replica as the analytics solution at scale**
This works up to a few hundred million rows with a handful of analysts. Beyond that,
it's the wrong tool. Know the threshold and cross it confidently.

**Mistake 2: Naming a warehouse without explaining the mechanism**
"Use BigQuery" is not an answer. "BigQuery uses columnar storage to avoid reading unused
columns, MPP to parallelize across thousands of workers, and partition pruning to skip
non-matching date partitions — together these allow scanning petabytes in seconds" is
an answer.

**Mistake 3: Ignoring the data pipeline (ETL/ELT)**
The warehouse is 30% of the design. The pipeline (extraction, transformation, loading,
incremental processing, data quality) is 70%. Don't spend all your time on the warehouse
and wave your hand at "ETL will move the data over."

**Mistake 4: Normalized schema in the warehouse**
Third normal form belongs in your OLTP database. Denormalized star schema belongs in your
warehouse. Designing a warehouse with 40 tables and extensive joins signals misunderstanding
of the analytical query pattern and the read-optimized nature of warehouses.

**Mistake 5: Missing data freshness requirements**
Always ask "how fresh does the data need to be?" before choosing streaming vs. batch.
Daily batch is far simpler and cheaper. Building a streaming pipeline when daily batch
would suffice is over-engineering.

**Mistake 6: Treating data lake and data warehouse as synonymous**
A data lake (S3 + Parquet) is for storing raw, varied data cheaply. A data warehouse is
for high-performance SQL analytics on structured data. Know the distinction and when each
is appropriate.

---

## Exercises

1. **Query cost estimation**: A BigQuery table has 1 TB of data across 20 columns.
   An analyst writes `SELECT SUM(price) FROM orders WHERE date = '2024-01-01'`. The
   table is not partitioned and not clustered. How many bytes will BigQuery scan? Now
   the table is partitioned by date (365 days of data, roughly equal) and clustered by
   category (10 distinct values). How many bytes will BigQuery scan for the same query?
   What is the ratio? (Hint: calculate for each of the three cases.)

2. **Star schema design**: Design a star schema for a hotel booking system. The business
   questions are: "What is our revenue by hotel, by room type, by month, by country of
   guest?", "What is our average booking lead time by country?", "Which hotels have the
   highest cancellation rates by booking channel?" Identify the fact table (what is the
   grain?), all dimension tables, and their attributes.

3. **SCD Type 2 implementation**: You have a `dim_users` table with SCD Type 2. A user
   (user_id=42) signs up in the US tier="free" on 2022-01-01. They upgrade to "premium"
   on 2023-06-15. They move to UK on 2024-02-10. Write the full contents of the
   `dim_users` table after all these changes, showing all four columns: `user_key`,
   `user_id`, `tier`, `country`, `valid_from`, `valid_to`.

4. **Partition key selection**: You have an `events` table in BigQuery with 5 TB of data.
   The columns are: `event_id`, `user_id`, `event_type`, `country`, `created_at`,
   `value`. Analysts most commonly filter by `created_at` range (90% of queries), by
   `country` (50% of queries), and by `event_type` (30% of queries). You can choose one
   partition key and up to two cluster keys. What do you choose and why? What is the
   impact on a query that filters by `country` but not `created_at`?

5. **ETL vs ELT decision**: Your team is extracting data from 5 sources: (a) Postgres
   OLTP database (500M rows), (b) Salesforce CRM, (c) Stripe payment events via Kafka,
   (d) third-party market data API, (e) server access logs in S3. For each source, would
   you use ETL or ELT? For sources using ELT, would you use full refresh or incremental
   processing? Justify your answers.

6. **MPP join strategy**: You have a fact table `fct_orders` (500 GB, 1B rows) and a
   dimension table `dim_users` (50 MB, 5M rows). You need to join them on `user_id`.
   What join strategy will the MPP engine use (broadcast join or shuffle join)? Now
   imagine `dim_users` is 50 GB (500M users). Which strategy would the engine use now?
   What are the performance implications of each?

7. **Data freshness design**: An operations team needs a dashboard showing current driver
   locations, active trips, and real-time surge pricing areas. They also need a daily
   report on trip revenue by city. Design the data architecture that serves both use
   cases efficiently. What systems would you use, and why are they different?

8. **Warehouse selection**: Your startup processes 10M orders per year, has a 5-person
   data team (2 analysts, 2 data scientists, 1 data engineer), runs on AWS, and has a
   data budget of $5,000/month. You're evaluating BigQuery, Redshift (ra3.xlplus nodes),
   and Snowflake. Your workload is primarily scheduled reports (8 hours/day of query
   activity) plus ad-hoc exploration by data scientists (2-4 hours/day). Which do you
   choose, why, and what configuration?

---

## Homework

1. **Hands-on — BigQuery free tier**: Create a GCP account (free tier). Load the public
   BigQuery dataset `bigquery-public-data.chicago_taxi_trips.taxi_trips` (75M rows, 15
   columns). Run three queries: (a) `SELECT SUM(fare) FROM taxi_trips` with no filter,
   (b) the same query with `WHERE trip_start_timestamp >= '2023-01-01'`, (c) the same
   with a table that you create as a copy partitioned by trip_start_timestamp. Note the
   bytes billed for each query. Write a paragraph explaining the difference.

2. **Schema design exercise**: Pick a real product you use (Spotify, Airbnb, DoorDash,
   your bank). Design a complete star schema for their core analytics use case. Include:
   1 fact table (with grain definition), at least 3 dimension tables, and 3 example
   business questions that can be answered with the schema. For one dimension table,
   design the SCD Type 2 history tracking.

3. **Read and summarize**: Read two Databricks blog posts on Delta Lake time travel and
   Apache Iceberg's hidden partitioning feature. Write a one-page comparison of how they
   handle partition evolution (changing the partition scheme on existing data) — this is
   one of the most practically important features when a table grows and the original
   partitioning choice turns out to be wrong.

4. **Cost calculator**: Using BigQuery's public pricing ($5/TB scanned on-demand) and
   Snowflake's pricing (Standard edition, XS warehouse = 1 credit/hour = $2.50/credit
   on AWS), calculate the monthly cost for the following workload: 500 queries/day
   averaging 100 GB scanned per query, and 8 hours of active query time per day (assume
   queries are not overlapping and BigQuery is idle during off-hours). Which is cheaper?
   At what query volume does the crossover happen?

5. **Architecture comparison**: Research how one of the following companies built their
   data platform (all have public engineering blog posts): (a) Airbnb's data platform
   evolution, (b) Uber's data platform (from Hadoop/Hive to Spark on S3), (c) Stripe's
   analytics infrastructure, (d) DoorDash's data platform. Write a half-page summary of
   their architectural choices and what lessons apply to the concepts in this chapter.

---

## KEY TAKEAWAYS

```
╔══════════════════════════════════════════════════════════════════════════════════╗
║                     CHAPTER 46 — KEY TAKEAWAYS                                  ║
╠══════════════════════════════════════════════════════════════════════════════════╣
║                                                                                  ║
║  1. OLTP vs OLAP is not a preference — it is physics.                           ║
║     Row storage reads 100% of columns for a query touching 4% of columns.       ║
║     Columnar storage reads 4% of columns for a query touching 4% of columns.    ║
║     For 1B row analytics queries, this is a 25x difference in I/O.             ║
║                                                                                  ║
║  2. Columnar storage = fewer columns read + better compression.                 ║
║     Dictionary encoding + RLE compress same-type data 5x-20x.                  ║
║     Parquet is the open standard. All warehouses and engines speak it.          ║
║                                                                                  ║
║  3. Star schema: fact table (events, immutable, billions of rows) + dimension   ║
║     tables (context, millions of rows, slowly changing). Design for the         ║
║     analytics workload, not the OLTP workload. Denormalize.                     ║
║                                                                                  ║
║  4. MPP = coordinator (plan + dispatch) + workers (scan + local aggregate) +   ║
║     shuffle (redistribute by grouping/join key) + merge. The shuffle step is   ║
║     the bottleneck. Data skew kills shuffle performance.                        ║
║                                                                                  ║
║  5. Partition pruning is the single biggest performance lever. Partition by     ║
║     date. Cluster by the next-most-filtered column. Two-level pruning can       ║
║     skip 99%+ of data before reading a single byte.                             ║
║                                                                                  ║
║  6. ELT won because storage is cheap and warehouse compute is fast. Load raw    ║
║     data first, transform with SQL (dbt) inside the warehouse. Keep raw data    ║
║     forever for auditability. Use incremental processing for large tables.      ║
║                                                                                  ║
║  7. BigQuery = serverless (no cluster, pay per TB scanned, scales instantly).   ║
║     Redshift = provisioned (fixed cluster, predictable cost, local disk cache). ║
║     Snowflake = virtual warehouses (multi-workload isolation, multi-cloud,      ║
║     auto-suspend). Choose based on workload pattern and cloud ecosystem.        ║
║                                                                                  ║
║  8. Lambda architecture (batch + speed layers) is complex but separates SLAs.  ║
║     Kappa architecture (streaming only, Kafka as log) is simpler with one      ║
║     codebase. Real-time OLAP (Druid/ClickHouse/Pinot) = sub-second queries     ║
║     on streaming-ingested data, needed for user-facing analytics.               ║
║                                                                                  ║
║  9. Data Lake = raw, flexible, schema-on-read, data swamp risk.                ║
║     Data Warehouse = structured, fast SQL, schema-on-write rigidity.           ║
║     Lakehouse (Delta/Iceberg) = open Parquet + ACID transactions + catalog =   ║
║     best of both. Industry is converging here.                                  ║
║                                                                                  ║
║ 10. L6 signal in interviews: don't name the warehouse — explain WHY it works.  ║
║     Mention columnar storage mechanics, partition key reasoning, star schema    ║
║     design, ELT pipeline pattern, data quality controls, and freshness trade-  ║
║     offs. The pipeline design is as important as the warehouse choice.          ║
║                                                                                  ║
╚══════════════════════════════════════════════════════════════════════════════════╝
```

---

## Part 12: 5-Level Intern → Staff Progression Tables for Every Major Concept

This section provides the detailed intern-to-staff depth ladder for each core concept,
giving you a precise calibration of where you currently sit and what the next level
requires.

### 12.1 Columnar Storage — 5 Levels

```
INTERN:
  "I know BigQuery is faster for analytics than Postgres."
  No understanding of why. Cannot explain storage format.

JUNIOR (L3):
  "BigQuery uses columnar storage. Instead of storing rows together,
   it stores columns together. Analytics only needs a few columns,
   so it reads less data."
  Correct concept, thin on mechanism. Cannot explain compression or
  the specific I/O math.

MID (L4):
  "Columnar storage reads only the columns referenced in SELECT and WHERE.
   For a 50-column table where a query uses 4 columns, the engine skips
   92% of data. Same-type column values compress well: dictionary encoding
   for low-cardinality strings, run-length encoding for sorted columns.
   Parquet is the open columnar format — row groups + column chunks."
  Good explanation. Missing: the sort order interaction with RLE, the
  page-level statistics and predicate pushdown implications.

SENIOR (L5):
  Adds: "Sort order multiplies the compression benefit — if you sort by
  date, the date column becomes nearly perfectly RLE-compressible.
  Parquet page-level min/max statistics enable predicate pushdown:
  for a range filter, entire pages are skipped without decompression.
  Dictionary encoding can also enable predicate pushdown at the dictionary
  level: if the filter value is not in the dictionary, skip the page.
  For nested data (JSON-like structures), Dremel encoding (used in
  BigQuery's Capacitor format) stores repetition and definition levels
  alongside values to reconstruct nesting structure column-by-column."
  Can diagnose: query scanning unexpectedly much data despite good
  partitioning → missing clustering, or large row groups preventing
  fine-grained predicate pushdown.

STAFF (L6):
  Adds organizational and cross-system perspective: "The choice of
  columnar format (Parquet vs ORC vs Avro vs Arrow) matters for the
  ecosystem: Parquet is the consensus format for interchange.
  Arrow is the in-memory columnar format, enabling zero-copy data
  transfer between systems (e.g., Spark → Python without serialization).
  For warehouses where storage is separated from compute (BigQuery's
  Colossus, Snowflake's S3 micro-partitions), the columnar format on
  storage must be efficiently read over network — this is why BigQuery's
  remote read throughput is a key infrastructure investment.
  At system design level: advise on encoding choices per column type
  (timestamp columns: delta encoding; floating point: XOR encoding;
  high-cardinality strings: ZSTD byte-stream compression rather than
  dictionary encoding). Understand the storage-query latency trade-off:
  higher compression = smaller files = less I/O but more CPU for
  decompression — the right balance depends on I/O vs CPU bottleneck."
```

### 12.2 Star Schema — 5 Levels

```
INTERN:
  "I've heard of a star schema. I think it's a way to organize tables."
  Cannot distinguish fact from dimension. Cannot draw the diagram.

JUNIOR (L3):
  "A star schema has a fact table in the center with dimension tables
   around it. The fact table has the events (like orders) and the
   dimension tables have descriptive information (like users, products).
   They're connected by foreign keys."
  Correct structure. Cannot explain why it exists or what it enables.

MID (L4):
  "Fact tables are high-row-count, immutable events with numeric
   measures. Dimension tables are lower-row-count, slowly-changing
   context. The design enables predicate pushdown: filter the small
   dimension table (finding matching user_keys for country='US') then
   use those keys to filter the large fact table. This avoids full
   scans when the selectivity of the dimension filter is high.
   Grain is critical: the fact table grain is what one row represents
   (one order line item, one pageview, one session)."
  Missing: SCD handling, the business implication of grain choice,
  degenerate dimensions, junk dimensions.

SENIOR (L5):
  Adds: "SCD Type 2 (add new row with valid_from/valid_to) preserves
   history for user attribute changes. The grain decision has cost
   implications: order-line-item grain (one row per item per order)
   gives flexibility but 10x more rows than order-level grain. Degenerate
   dimensions (order_number on the fact table directly) avoid tiny
   dimension tables. Conformed dimensions (shared dim_date table used
   across multiple fact tables) enable cross-fact-table analysis.
   Aggregate fact tables (pre-summed to month-level) serve BI dashboards
   without hitting the raw fact table."
  Can design a warehouse schema for any business domain from a set of
  business questions.

STAFF (L6):
  Adds: "The grain decision is the highest-stakes design choice — getting
   it wrong requires full reprocessing of the fact table. The correct
   approach: enumerate the key business questions before designing the
   schema, derive the grain from the finest level of detail any question
   requires. At organizational scale, conformed dimensions require
   governance: a company-wide definition of 'active user' must be
   maintained in a shared dim_users table, not independently defined
   by each team. Dimensional model evolution strategy: adding new
   columns to fact tables requires backfilling historical data
   (expensive) or accepting nulls for history (often acceptable).
   Trade-off articulation: snowflake schema saves storage but adds
   join complexity; star schema wastes storage but eliminates joins.
   For sub-10TB warehouses on managed cloud, storage cost difference
   is negligible — always favor star schema's query simplicity."
```

### 12.3 MPP Query Execution — 5 Levels

```
INTERN:
  "BigQuery is fast because it uses lots of computers in parallel."
  No understanding of how parallelism is achieved, what the coordinator
  does, or what the bottleneck is.

JUNIOR (L3):
  "The query is split up and run on many machines at the same time.
   Each machine processes part of the data. The results are combined
   at the end."
  Correct at a cartoon level. Cannot explain the shuffle step, why
  joins are expensive, or how GROUP BY is distributed.

MID (L4):
  "The coordinator parses SQL and creates a query plan. It distributes
   scan tasks to worker nodes. Workers apply filters and compute local
   aggregations. For GROUP BY, data must be shuffled (redistributed)
   by the grouping key so all rows with the same key are on the same
   worker. The worker then computes the final aggregation. Shuffle is
   the expensive step because it moves data over the network."
  Can explain basic query execution. Missing: broadcast vs. shuffle join
  strategies, speculative execution for stragglers, pipeline stages.

SENIOR (L5):
  Adds: "Broadcast join: if one table is small (< a few hundred MB),
   copy it to all workers — each worker joins locally without any
   network shuffle. This is the typical path for fact-dimension joins
   where the dimension is small. Sort-merge join: if both tables are
   large, hash both tables' join keys and route rows to workers by
   hash — all rows with the same join key land on the same worker.
   Distribution key in Redshift: if the fact table and its most-used
   dimension are distributed by the same key, joins are co-located
   (no network movement). Straggler mitigation: speculative execution
   runs duplicate tasks on other workers if one worker falls behind.
   Pipeline execution: stage N starts consuming output from stage N-1
   without waiting for N-1 to complete — this avoids materializing
   large intermediate results to disk."

STAFF (L6):
  Adds: "At system design level: the MPP architecture determines how
   you choose cluster sizing and node count. For Redshift, adding nodes
   increases parallelism proportionally until you hit I/O saturation
   on each node's local storage, then you get diminishing returns.
   For BigQuery, the slot count (default 2,000 per query) is tunable
   via reservations — important for consistent latency SLAs on critical
   dashboards. Data skew is the most common reason MPP performance
   degrades unpredictably: a join on a high-cardinality but skewed
   key (e.g., 'product_id=1 appears in 50% of all orders') routes
   50% of the shuffle traffic to one worker, making it 50x slower than
   the others. Detection: query plan shows highly uneven partition sizes.
   Fix: add a salt key to distribute the hot key, then aggregate by
   the original key after. Know the failure modes: OOM on workers
   during shuffle (insufficient memory for the intermediate hash table),
   mitigated by spill-to-disk at the cost of disk I/O latency."
```

### 12.4 Partition Pruning — 5 Levels

```
INTERN:
  "Partitioning makes queries faster." Cannot explain the mechanism.

JUNIOR (L3):
  "If you partition a table by date, queries that filter by date only
   read that day's data instead of the whole table."
  Correct. Cannot explain metadata, predicate pushdown, or clustering
  as a second level.

MID (L4):
  "Partition metadata (min/max per partition) is stored separately.
   The query engine checks the WHERE clause against partition metadata
   before reading any data — partitions that cannot match the filter
   are skipped entirely. This is 'partition pruning.' The partition key
   should match the most common filter column (usually date). Partition
   pruning at the partition level + page-level statistics in Parquet
   give two layers of skipping. Clustering (sort key) is the second
   layer: within a partition, blocks are sorted by the cluster key,
   enabling min/max-based block skipping for cluster key filters."

SENIOR (L5):
  Adds: "Avoid function application on the partition key in WHERE clauses:
   WHERE YEAR(created_at) = 2024 prevents pruning because the optimizer
   cannot evaluate the function against partition metadata without
   reading data. Rewrite as WHERE created_at BETWEEN '2024-01-01' AND
   '2024-12-31'. Partition granularity trade-off: daily partitions for
   a table with 5 years of data = 1,825 partitions. Too-fine granularity
   increases metadata overhead and slows down queries that span many
   partitions (e.g., a 1-year date range scan now opens 365 partition
   files instead of 1). Monthly partitions may be better for older
   data, with daily partitions for recent data (partition by TRUNC(date,
   month) for data older than 90 days)."

STAFF (L6):
  Adds: "At design level: partition strategy is a long-term commitment.
   Repartitioning an existing table requires rewriting all data — plan
   carefully. Apache Iceberg's hidden partitioning allows the partition
   scheme to evolve without rewriting data (new data uses new scheme,
   old data uses old scheme, query engine handles both). For multi-tenant
   tables (one table serving many customers), consider composite
   partitioning: partition by date + tenant_id range. The interview
   signal: proactively ask 'what is the primary access pattern?' before
   choosing a partition key. If the answer is 'we mostly filter by user
   cohort, not by date,' the partition key should be a hash bucket of
   user_id, not date — even though date partitioning is the common
   default."
```

### 12.5 ETL/ELT Pipeline — 5 Levels

```
INTERN:
  "Data gets moved from one database to another somehow."
  No understanding of the mechanism, tools, or design decisions.

JUNIOR (L3):
  "ETL means you extract data from a source, transform it (clean it,
   join it), then load it into the warehouse. ELT is newer — you load
   it first, then transform inside the warehouse using SQL."
  Correct definition. Cannot explain when to use which, or what
  tools implement each.

MID (L4):
  "ELT is preferred when the warehouse has cheap compute (BigQuery,
   Snowflake) because transforming inside the warehouse uses the MPP
   compute you're already paying for. dbt implements the T in ELT:
   you write SQL models, dbt compiles and runs them in the warehouse.
   Fivetran/Airbyte implement the E and L. Airflow orchestrates the
   sequence. Incremental processing is essential for large tables:
   each run only processes new rows (identified by a watermark
   column like 'created_at'), appending to the target table rather
   than reprocessing everything."
  Missing: CDC, late-arriving data handling, at-least-once delivery
  and deduplication, schema evolution.

SENIOR (L5):
  Adds: "CDC (Change Data Capture via Debezium on Postgres WAL or
   MySQL binlog) enables near-real-time ELT by streaming row-level
   changes to Kafka. The warehouse loader (Flink or a custom Kafka
   consumer) applies these changes to the warehouse in minutes.
   Late-arriving data: events with timestamps in the past (users with
   mobile apps that were offline for days) may arrive after the nightly
   pipeline has already processed their date partition. Handle this
   with a lookback window: the pipeline always reprocesses the last
   3-7 days even if those partitions were previously processed, then
   deduplicates using INSERT OVERWRITE or MERGE. At-least-once
   delivery from Kafka means duplicates are possible — always
   deduplicate in the warehouse using ROW_NUMBER() OVER (PARTITION BY
   event_id ORDER BY loaded_at) and filter to rn=1."

STAFF (L6):
  Adds: "Pipeline design is the organizational contract between
   the data platform team and data consumers. SLA definition: 'data
   for day D is available by 8 AM on day D+1' must be communicated
   and monitored with alerting. Pipeline observability: each pipeline
   run should emit metadata (rows processed, rows failed, run duration,
   bytes read/written) to a monitoring table that feeds a pipeline
   health dashboard. Backfill strategy: when a transformation bug
   corrupts 6 months of data, the backfill must be done without
   affecting the live pipeline and without causing data gaps for
   downstream consumers. The architecture should support parallel
   backfill runs in a separate dbt target environment. At design scale:
   the DAG structure of dbt models (model A depends on model B depends
   on model C) creates a dependency chain; a failure in a foundational
   model fails everything downstream. Identify the critical-path models
   and apply extra monitoring and alerting to them specifically."
```

### 12.6 Choosing BigQuery vs. Redshift vs. Snowflake — 5 Levels

```
INTERN:
  "I've heard of BigQuery. I think it's Google's database."
  No understanding of differences.

JUNIOR (L3):
  "BigQuery is Google's warehouse, Redshift is Amazon's, Snowflake
   works on multiple clouds. They all do SQL analytics."
  Correct at a product name level. Cannot advise on choice.

MID (L4):
  "BigQuery is serverless — no cluster to manage, pay per query.
   Redshift is a provisioned cluster on AWS — fixed cost per hour.
   Snowflake has virtual warehouses that auto-suspend — pay when
   running. For sporadic queries: BigQuery. For sustained predictable
   load: Redshift reserved instances. For multiple workloads needing
   isolation: Snowflake."
  Good practical heuristic. Missing: storage-compute separation
  implications, feature comparison (time travel, data sharing),
  ecosystem integration depth.

SENIOR (L5):
  Adds: "Redshift RA3 nodes separate compute from storage (data on S3,
   hot data cached on local NVMe). This enables cluster resizing without
   data movement, and Redshift Serverless for variable workloads.
   Snowflake's data sharing (sharing live data with other Snowflake
   accounts without copying) is the best-in-class for data product
   use cases. BigQuery's ML capabilities (BigQuery ML: train and
   serve models directly in SQL) reduce the need for separate ML
   infrastructure for standard models (logistic regression, k-means).
   Migration cost: switching warehouses requires SQL dialect translation
   (Snowflake SQL, BigQuery SQL, Redshift SQL all differ in window
   functions, date functions, approximate distinct count syntax),
   pipeline reconfiguration, and data reprocessing. This is 3-6 months
   of engineering work — choose carefully."

STAFF (L6):
  Adds: "The warehouse decision is 5-year infrastructure. Total cost
   of ownership includes: compute cost + storage cost + egress cost
   (BigQuery has no egress if within GCP, Redshift has no egress if
   within AWS, Snowflake has egress costs when reading from S3 cross-
   region) + engineering time for migration + opportunity cost of
   vendor lock-in. For a multi-cloud company with data sharing needs:
   Snowflake. For a GCP-native company: BigQuery (Colossus storage,
   Vertex AI integration, no cold-start). For an AWS-native company
   with consistent, high-volume workloads: Redshift RA3 + reserved
   instances. The organizational dimension: which warehouse does your
   team have expertise in? Switching warehouses resets team expertise
   and imposes a 6-12 month productivity tax while engineers learn
   the new system's quirks. This cost is often larger than the
   infrastructure cost difference."
```

---

## Part 13: Supplementary Concepts and Production Notes

### 13.1 Data Quality and Observability

Data quality is the most common reason analytics organizations lose trust in their data
platform. Once an analyst finds a number that doesn't match reality, every number is
suspect. Rebuilding trust takes months. The engineering investment in data quality is
almost always worth it.

**Three layers of data quality control**:

Layer 1 — Source validation: Assertions on raw data as it lands in staging. dbt tests
include `not_null`, `unique`, `accepted_values`, `relationships` (referential integrity).
These run after each pipeline load and fail the pipeline before transformations begin.

Layer 2 — Transformation testing: Each dbt model has tests on its output. The final
fact table is tested for: uniqueness on the primary key, no nulls in required columns,
expected row count range (if today's orders are 100,000 and suddenly there are 10
orders, something is wrong), referential integrity to dimension tables.

Layer 3 — Data observability: Tools like Monte Carlo, Bigeye, or Anomalo monitor data
freshness (the table hasn't been updated in more than 24 hours) and data distribution
(average order value has been $85 for 6 months and suddenly it's $8,500 — is this correct
or a pipeline bug?). These monitor continuously rather than just at pipeline execution time.

### 13.2 Data Governance and Access Control

At larger organizations, data access control is as important as data quality. Not every
analyst should see every column. PII (names, emails, phone numbers, addresses) should
be accessible only to teams with a legitimate business need and the appropriate data
handling agreements in place.

Row-level security: BigQuery, Redshift, and Snowflake all support row-level access
policies. A support analyst should see only tickets for their assigned region. A country
manager should see only data for their country.

Column-level security: Sensitive columns (social_security_number, credit_card_number,
exact_birthdate) can be masked or tokenized for most users. Only specific roles see the
full value.

Dynamic data masking: Snowflake and BigQuery support defining masking policies that
return a masked value (e.g., 'XXXXX' or a hash) for users without the unmasking privilege,
while returning the full value for privileged users — all transparently within the same
query.

### 13.3 The Data Catalog

At scale, the warehouse might have thousands of tables. Without a catalog, finding the
right table is impossible. Data catalogs serve three functions:

**Discovery**: "I need a table with order revenue by product." A catalog with search and
tagging makes this findable without asking a colleague.

**Documentation**: What does the `revenue` column in `fct_orders` mean? Is it gross
revenue or net revenue? Does it include taxes? The catalog stores this documentation
alongside column descriptions.

**Lineage**: Which tables does `mart_finance.monthly_revenue` depend on? If `stg_orders`
has a bug, which downstream tables are affected?

Tools: dbt's built-in documentation (auto-generated from `schema.yml` files), Datahub
(open-source, LinkedIn), Atlan, Alation, Google Data Catalog (for BigQuery).

### 13.4 The Semantic Layer — One Definition of "Revenue"

The most politically contentious issue in analytics organizations is often "whose revenue
number is correct?" Marketing's dashboard shows one number, Finance's shows another,
the CEO's dashboard shows a third. All are calculating "revenue" differently:
gross vs. net, including refunds vs. excluding, with currency conversion or without.

The semantic layer solves this by defining metrics once, centrally, in a version-controlled
code repository. Every BI tool, every dashboard, every analyst query goes through the
semantic layer and gets the same metric definition.

Tools: dbt's MetricFlow (open source), Cube.js (open source), Looker's LookML
(proprietary). The pattern is: write the metric definition once in a YAML or SQL file,
all consumers call that definition rather than writing their own SQL.

This is an organizational solution as much as a technical one. The semantic layer is only
as good as the governance process that maintains it: who has the authority to define
"revenue," how are changes reviewed, how are downstream consumers notified of changes
to metric definitions.

---

### Brainstorming Q&A for Part 13

**Q: How do you handle GDPR and data deletion requirements in a data warehouse?**

GDPR's "right to be forgotten" requires deleting a user's personal data within 30 days
of their request. In an OLTP database, this is straightforward: DELETE WHERE user_id =
X. In a data warehouse, it is much harder because data is stored in immutable columnar
files partitioned by date — there is no easy "delete one row from a file" operation.

The standard approach for warehouses is one of two strategies. The first is "crypto
shredding": encrypt all PII for a user with a user-specific encryption key. When the user
requests deletion, delete the encryption key. All their PII becomes unreadable
(effectively deleted) without physically removing any rows from the warehouse. This is
simpler to implement and works well for data that is heavily interleaved across many tables.

The second is table-based masking: maintain a "deleted_users" table. Any query that
joins user data must also exclude users in deleted_users. dbt models enforce this by
always filtering `WHERE user_id NOT IN (SELECT user_id FROM deleted_users)`. For tables
that store PII directly (not as foreign keys), a periodic reprocessing job overwrites
the user's data with nulls or placeholder values. Delta Lake and Iceberg make this more
tractable with MERGE operations that can update or delete specific rows without rewriting
entire partitions.

**Q: What is the difference between a data mesh and a traditional centralized data warehouse?**

A data mesh (coined by Zhamak Dehghani) is an organizational and architectural philosophy
where data ownership is decentralized: each domain team (checkout, payments, users,
catalog) owns their own data products, publishes them using standard interfaces (a
warehouse table, an API, or a streaming topic), and is responsible for data quality and
documentation. There is no central "data engineering team" responsible for all pipelines.

A centralized data warehouse has a central platform team that owns the warehouse, all
pipelines, and all data models. This creates a bottleneck: every new data need goes
through the central team, which becomes overloaded as the organization grows.

The data mesh trades central team bottleneck for the complexity of coordination across
domain teams. If 20 teams each publish their own data products with their own schemas
and quality standards, cross-domain analysis (joining checkout events with payment
events with user profile data) requires coordination across three teams' definitions.
The semantic layer and catalog are the technical solutions, but organizational alignment
is required.

For most companies under 500 engineers, a centralized data platform with domain liaisons
is more practical. Data mesh is appropriate at very large organizations (1,000+ engineers,
dozens of domains) where the central team bottleneck has become the primary constraint
on analytics velocity.

---

## Part 14: Production Debugging Scenarios

### 14.1 "Why Is My Query Suddenly 10x Slower?"

Scenario: A query that ran in 30 seconds last week now takes 5 minutes. The query and
the table schema haven't changed.

**Diagnosis checklist**:

Step 1: Check if the table's data volume grew significantly. If the table grew from
100M rows to 1B rows in the last week (e.g., a backfill ran), the query now scans 10x
more data. Check with `SELECT COUNT(*) FROM table` or the table metadata.

Step 2: Check if partition pruning is still working. Look at the bytes scanned in the
query profile. If it's scanning the full table instead of one partition, the WHERE clause
may have changed in a way that prevents pruning (e.g., adding a function around the
partition key column).

Step 3: Check if clustering statistics are stale. In Snowflake, micro-partition
clustering degrades as new data arrives unsorted. Running `SYSTEM$CLUSTERING_INFORMATION`
shows clustering depth — if it's high, run `ALTER TABLE ... CLUSTER BY` to recluster.

Step 4: Check for a statistics refresh issue. Query planners make decisions based on
table statistics (row count, cardinality estimates). If statistics are stale (the table
grew significantly since the last `ANALYZE` in Redshift or automatic stats refresh in
Snowflake/BigQuery), the planner may choose a suboptimal join strategy.

Step 5: Check for lock contention or resource contention. In Redshift, running queries
during a heavy ETL load can cause WLM queue delays. In Snowflake, a long-running data
loading job on the same virtual warehouse can starve interactive queries.

### 14.2 "The Pipeline Is Late — Data Isn't in the Warehouse"

Scenario: The daily pipeline should complete by 6 AM. It's 9 AM and analysts are
complaining that yesterday's data isn't there.

**Diagnosis checklist**:

Step 1: Check the pipeline orchestration tool (Airflow, Prefect). Which task failed?
Look at the error message. Common causes: source system was down or slow (extraction
failed), the warehouse was throttling writes (loading failed), a dbt model test failed
(transformation failed), disk or quota limits (loading failed).

Step 2: If extraction failed: was the source system available? Did the API rate limit
get hit? Was the network connection to the source flaky? Most extraction failures are
transient — retry the task.

Step 3: If transformation failed: was it a dbt data quality test failure (a source
column had unexpected nulls) or a SQL compilation error (schema changed in a source
table, new column added to a dbt model's source that the model didn't expect)?

Step 4: Was the pipeline manually paused or marked as failed by someone else? Check
the Airflow logs for manual interventions.

Step 5: After resolution: add monitoring for pipeline SLA — alert if the pipeline has
not completed by 6 AM, so the team knows before analysts arrive. Don't rely on analysts
to discover pipeline failures.

### 14.3 "Data Science Team Says Our Numbers Don't Match"

Scenario: The data science team is computing revenue in Python using data from the
warehouse and getting a different number than the Finance dashboard.

**Diagnosis checklist**:

Step 1: Establish the exact definition of the metric for each team. "Revenue" in Finance
might be net revenue (after refunds, after discounts), while the data science team might
be computing gross revenue (before refunds). Get both SQL definitions side by side.

Step 2: Check the time boundary. Is Finance computing revenue by payment date, and the
data science team by order date? For orders placed in December but paid in January, this
makes a significant difference at month-end.

Step 3: Check the currency conversion. Finance uses end-of-month exchange rates.
Data science might be using spot exchange rates at order time. For international companies,
this can be a 5-10% difference.

Step 4: Check for double-counting. Are any orders appearing multiple times due to a
deduplication bug in the pipeline?

Step 5: The fix: define the metric formally in the semantic layer (dbt MetricFlow or
Looker LookML). Both Finance and data science use the same metric definition. All
discrepancies are eliminated by construction.

---

## Final Note: What Makes Data Warehouse Design Hard

The technical concepts in this chapter — columnar storage, MPP, star schema, partition
pruning — are well-understood and well-documented. The hard part of data warehouse design
is not the technology. It is the organizational and social dimensions:

**Defining shared metrics**: Getting the Finance team and the Revenue Operations team to
agree on one definition of "ARR" requires negotiation, not just engineering.

**Schema governance**: Deciding who has the authority to change a dimension table's
attributes, and what process is required, is a process design problem.

**Pipeline reliability expectations**: Analysts expect data to be there at 6 AM. Engineers
know pipelines fail. Negotiating the SLA and building the alerting and recovery processes
are as important as building the pipeline itself.

**Balancing flexibility and performance**: The data model that makes any query imaginable
possible (very normalized) and the data model that makes the top 20 queries very fast
(very denormalized, pre-aggregated) are in tension. Choosing where to land on this
spectrum requires understanding what questions matter and how often.

**Cost governance**: Without explicit controls, one team's poorly-written queries can
spend the entire monthly BigQuery budget. Governance processes (budget alerts, query
cost reviews, training on partition-friendly SQL) are as important as the infrastructure.

These are the dimensions an L6 engineer is expected to navigate, not just the technical
ones. The warehouse architecture exists within an organization, and the architecture
succeeds or fails based on how well it fits the organization's needs, processes, and
culture — not just whether the columns are stored correctly on disk.

---

## The One-Sentence Summary

> "A data warehouse is the combination of columnar storage (read only the columns you
> need, compress same-type data 5-20x), MPP query execution (parallelized across hundreds
> of workers, with coordinator-worker-shuffle architecture), star schema dimensional
> modeling (fact tables for events, dimension tables for context, predicate pushdown at
> join time), partition pruning (skip non-matching partitions, two levels of metadata
> filtering), and ELT pipeline design (load raw, transform in SQL, incremental processing
> for cost efficiency) — together enabling analytics over billions of rows in seconds on
> a system architecturally incompatible with your OLTP database."

---

*Pairs with: Ch35 (Batch Processing and Data Pipelines), Ch33 (Event-Driven Architectures
and Kafka), Ch29 (Database Internals), Ch31 (Caching at Scale). Chapter 46 completes
the analytics tier of the data engineering stack.*
