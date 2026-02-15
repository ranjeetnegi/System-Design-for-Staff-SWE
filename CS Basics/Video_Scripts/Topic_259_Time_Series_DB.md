# Time-Series DB: Why Different (Gorilla Compression)

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A weather station. Records temperature every 10 seconds. Twenty-four hours: 8,640 readings. Three hundred sixty-five days: 3.15 million readings. Per station. Ten thousand stations: 31.5 billion readings per year. Each reading: timestamp plus value. Always appending. Almost never updating. Queries: "What was the average temperature last week?" Time-series data is different. It needs a different kind of database. And a different kind of compression. Let's see why.

---

## The Story

Regular data: users, orders, products. You insert. You update. You delete. Random access. Queries: "Find user 123." "Update order 456." Indexes. Joins. Normal database stuff.

Time-series data: sensors, metrics, logs. You append. Timestamp, value. That's it. Updates? Rare. Deletes? Rare. Queries: "Give me all readings between 2 PM and 4 PM." "Average temperature last hour." "Max CPU usage per minute." Time-ordered. Range-based. Append-heavy. Different access pattern. Different optimizations.

A regular database—PostgreSQL with 31 billion rows—struggles. Indexes explode. Queries slow. No built-in downsampling. No time-bucketing. You're fighting the wrong tool. Time-series databases are built for this. InfluxDB, TimescaleDB, Prometheus. Optimized for append. For range queries. For compression. And the compression is where it gets wild.

---

## Another Way to See It

Think of a diary. Regular database: random entries. "July 15: met John." "January 3: bought a car." Jump around. Time-series: one entry per day, in order. "Jan 1, Jan 2, Jan 3..." Never out of order. Never go back to edit. Just append. The structure is different. The diary is a stream. Time-series DBs optimize for that stream.

---

## Connecting to Software

**Characteristics:** Write-heavy. Append-only. Time-ordered. Rarely updated. Queries: range-based (last hour, last week), aggregation (avg, sum, max).

**Why not PostgreSQL?** 31 billion rows = painful. B-tree indexes on timestamp = huge. Query "last hour" = scan massive index. No native compression for sequential values. It works, but it fights you.

**Time-series DBs:** InfluxDB, TimescaleDB, Prometheus. Storage optimized for time order. Compression built-in. Downsampling. Retention policies. TTL. Built for the workload.

**Gorilla compression (Facebook):** Two tricks. Timestamps are sequential—store deltas (difference from previous). 1500000000, 1500000010, 1500000020 → 0, 10, 10. Small numbers. Fewer bits. Values change slowly—store XOR of consecutive values. 20.1, 20.1, 20.2, 20.1 → XOR gives small deltas. Compress those. Result: 10x compression. 31 billion rows stored like 3 billion. Same data. Fraction of the space. The paper: "Gorilla: A Fast, Scalable, In-Memory Time Series Database." Facebook used it for internal monitoring. Now the ideas are everywhere—Prometheus, VictoriaMetrics, others.

**Downsampling:** Raw data: one point per second. Keep for 7 days. After that, aggregate: 1 minute averages. After 30 days: 1 hour averages. Storage stays bounded. Queries for "last year" hit downsampled data—fast, approximate. Queries for "last hour" hit raw—precise. Retention and aggregation are first-class in time-series DBs.

---

## Let's Walk Through the Diagram

```
Regular DB row:
  timestamp (8 bytes) + value (8 bytes) = 16 bytes/reading
  31B readings = 496 GB raw

Gorilla compression:
  Timestamps: store delta from previous
    1500000000, 1500000010, 1500000020
    -> 0, 10, 10 (variable-bit encoding)
  Values: XOR with previous (similar values = small XOR)
    20.1, 20.1, 20.2, 20.1
    -> XOR: small numbers, compress
  Result: ~1.6 bytes/reading (Facebook's numbers)
  31B readings = ~50 GB
  10x compression
```

---

## Real-World Examples (2-3)

**Prometheus:** Metrics. CPU, memory, request rate. Time-series native. Gorilla-like compression. Used by Kubernetes, thousands of companies. Pull model. Scrape and store.

**InfluxDB:** IoT, monitoring, sensors. High write throughput. Columnar storage. Compression. Downsampling. Continuous queries. Built for streams.

**TimescaleDB:** PostgreSQL extension. Hypertables. Automatic partitioning by time. SQL interface. Best of both: PostgreSQL familiarity, time-series optimization. Chunks are created automatically. Continuous aggregates for downsampling. You get PostgreSQL + time-series superpowers. Migration from vanilla PostgreSQL is straightforward—add extension, convert table to hypertable.

**VictoriaMetrics:** Prometheus-compatible. Faster. More efficient storage. Used by companies that outgrow Prometheus. Same query language (PromQL). Drop-in replacement in many cases. Gorilla-like compression. The time-series ecosystem is rich—pick by scale, query language, and operational fit.

---

## Let's Think Together

**Question:** Temperature readings: 20.1, 20.1, 20.2, 20.1, 20.3. How would delta and XOR compression shrink this?

**Answer:** Values: XOR each with previous. 20.1 XOR 20.1 = 0. 20.1 XOR 20.2 = small. 20.2 XOR 20.1 = small. 20.1 XOR 20.3 = small. Consecutive similar values produce small XOR results. Small numbers compress well—few bits. Instead of 5 × 8 bytes = 40 bytes, you might get 5 × 2 bits for the XOR deltas. Plus one full value as anchor. Massive savings. Gorilla does this automatically.

---

## What Could Go Wrong? (Mini Disaster Story)

A team stores metrics in PostgreSQL. One row per metric per second. Millions of metrics. Table grows. 100 GB. 500 GB. Queries for "last hour" take 30 seconds. Dashboards time out. Grafana shows errors. On-call gets paged. They switch to Prometheus. Rewrite ingestion. Migration pain—weeks of work. But after: queries 100 ms. Storage 50 GB. Dashboards load instantly. The lesson: use the right tool. Time-series workload = time-series database. Don't force a square peg. The migration is painful but worth it when you're in the wrong tool.

---

## Surprising Truth / Fun Fact

Gorilla compression was published by Facebook in 2015. Used in their internal metrics system. The name? No relation to the animal. Just a code name. The paper is a gem—simple ideas, huge impact. Open-sourced. Prometheus adapted it. Now it's everywhere in the metrics world. The insight: time-series data has structure. Timestamps march forward. Values often change slowly. Exploit that structure, compress aggressively. Generic compression (gzip, etc.) helps too, but Gorilla's domain-specific approach does better. When you know the shape of your data, optimize for it. Time-series data has a shape—append, time-ordered, high volume. Time-series DBs and Gorilla compression are built for that shape. Use them. The next time you're storing metrics or sensor data, ask: is this time-series? If yes, reach for a time-series database first. You'll thank yourself later when queries are fast and storage is manageable.

---

## Quick Recap (5 bullets)

- **Time-series** = append-only, time-ordered, range queries; sensors, metrics, logs
- **Why different DB** = regular DB fights the workload; time-series DB built for it
- **Gorilla compression** = delta timestamps + XOR values = 10x compression
- **Examples** = InfluxDB, TimescaleDB, Prometheus
- **Use when** = high-volume sequential writes, time-range queries, aggregation

---

## One-Liner to Remember

**Time-series data flows in one direction; time-series DBs and Gorilla compression are built to ride that stream—append, compress, query by time.**

---

## Next Video

Up next: Inverted index. The simple idea behind Google. One word, millions of documents, instantly.
