# Metrics Pipeline: Ingestion and Storage

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A hospital with 1000 patients. Each has a heart monitor beeping every second. 1000 readings per second. You need to collect ALL of them, store them for weeks, alert if any go abnormal, and show dashboards to doctors. That's a metrics pipeline—not optional, not nice-to-have. Critical. Let's build one.

---

## The Story

Imagine that hospital. Monitors everywhere. Beep. Beep. Beep. Data flows in constantly. Miss one reading? A patient's heart could spike. Nobody notices in time. The job: capture every data point. Store it. Make it queryable. Alert on anomalies. Show trends.

That's exactly what a metrics pipeline does for your software systems. CPU usage. Memory. Request count. Latency. Hundreds of metrics. Thousands of servers. Millions of data points per minute.

The challenge isn't collecting one number. It's collecting them ALL—at scale, reliably, without losing anything. When your p99 latency climbs to 5 seconds, you need to know. When disk fills up, you need to know before users complain. Metrics are the nervous system of your infrastructure. Without them, you're flying blind. One missed alert can mean hours of outage. One gap in data can hide the root cause. This is life or death for production systems.

---

## Another Way to See It

Think of a weather station network. Hundreds of sensors across a city. Temperature. Humidity. Wind speed. Every 10 seconds, each sensor sends a reading. A central system collects them all, stores them, and produces forecasts. Miss data? The forecast degrades. Delay data? The forecast is stale. Nobody trusts it.

A metrics pipeline is your software's weather network. Servers are the sensors. Your dashboards are the forecast. The analogy holds: both need completeness, timeliness, and storage at scale. Both need to answer: "What happened? What's happening now? What will happen next?"

---

## Connecting to Software

**Ingestion.** Agents run on every server—Collectd, Telegraf, Node Exporter. They scrape or receive metrics: CPU at 45%, memory at 2.3GB, 150 requests in the last 10 seconds. Two modes: push or pull. Push: agent sends to a collector. Pull: collector scrapes agents. Pull is common for Prometheus. Agents expose an HTTP endpoint. Collector hits it every 10–15 seconds.

Metrics flow to a buffer—often Kafka. Why? Decouple collection from storage. Burst of traffic? Queue absorbs it. Storage is slow? Queue holds the data. Never drop a metric. The buffer is your safety net.

**Storage.** Time-series databases. Prometheus, InfluxDB, TimescaleDB. These aren't general-purpose DBs. They're optimized for write-heavy, time-ordered data. Append-only writes. Compress aggressively. Gorilla encoding: delta-of-delta compression. 16 bytes per point becomes 1.5 bytes. Efficiency matters when you store billions of points. Retention policies: keep raw data for 15 days, aggregates for 1 year. Downsample over time. Raw for debugging. Aggregates for trends.

**Querying.** Dashboards like Grafana. Alerts via Alertmanager. "Alert if p99 latency > 500ms for 5 minutes." "Alert if error rate > 1%." Queries are time-range: "Give me CPU for the last hour." Aggregations: avg, sum, p99. The pipeline exists so you can ask questions and get answers—fast. The moment a metric crosses a threshold, you know.

---

## Let's Walk Through the Diagram

```
METRICS PIPELINE - INGESTION AND STORAGE
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   SERVERS (1000s)              COLLECTOR           STORAGE       │
│                                                                  │
│   [Server 1]──┐                ┌──────────┐      ┌─────────────┐ │
│   [Server 2]──┼──► SCRAPE ──► │  Kafka   │ ──►  │ Time-series │ │
│   [Server 3]──┤    or PUSH    │  Queue   │      │     DB      │ │
│   [Server N]──┘                └──────────┘      └──────┬──────┘ │
│                                                       │         │
│   Agents: Telegraf, Node Exporter, Collectd           │         │
│   Storage: Prometheus, InfluxDB, TimescaleDB          ▼         │
│                                               ┌─────────────┐   │
│                                               │  Grafana    │   │
│                                               │ Alertmanager│   │
│                                               └─────────────┘   │
│                                                                  │
│   FLOW: Scrape → Buffer → Write → Query/Alert                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: Agents on servers emit metrics. Collector scrapes or receives them. Kafka buffers. Absorbs bursts. Writers consume from Kafka and write to the time-series DB. Grafana queries. Alertmanager fires when thresholds break. The queue is the safety valve. Without it, a storage hiccup means lost data. The pipeline is only as good as its weakest link—and the buffer makes the chain strong. Every component has a job. Together, they turn chaos into insight.

---

## Real-World Examples (2-3)

**Prometheus + Grafana.** The classic stack. Prometheus scrapes targets every 15 seconds. Stores locally. Grafana visualizes. Alertmanager handles alerts. Used by Kubernetes, countless startups. Simple. Battle-tested. The open-source standard for metrics. If you're starting, start here.

**Datadog.** SaaS metrics. Agents on your servers push to Datadog cloud. No infrastructure to run. Dashboards, alerts, APM in one place. Pay per host, per metric. Scale without ops. Trade money for simplicity. When you don't want to run Prometheus yourself, this is the path.

**Uber's M3.** Open-source metrics platform. Billions of data points per second. Built for their scale. In-house time-series DB. Proves metrics pipelines scale when you invest. When you outgrow Prometheus, you build like Uber. The ceiling is high. The journey is long.

---

## Let's Think Together

**"1000 servers, 100 metrics each, collected every 10 seconds. How many data points per day?"**

Let's math. 1000 × 100 × (86400 / 10) = 1000 × 100 × 8640 = 864 million points per day. Per metric type, you're storing time, value, maybe tags. With compression, ~2 bytes per point. That's ~1.7 GB per day for raw data. Retention: 30 days? 51 GB. Manageable. But 10,000 servers? 10× that. 100,000? You need partitioning, downsampling, aggregation. The math tells you when to optimize. Run the numbers before you hit the wall. Your future self will thank you.

---

## What Could Go Wrong? (Mini Disaster Story)

A company runs Prometheus. No Kafka. Direct scrape to storage. One day, the time-series DB has a bad deploy. Writes slow to a crawl. Prometheus keeps scraping. In-memory buffers fill. Prometheus OOMs. Crashes. No metrics for 2 hours.

During those 2 hours, a bug triggers a 10× traffic spike. Nobody sees it. Latency goes to 5 seconds. Users rage. Support drowns. Postmortem: "We had no visibility." If they'd had Kafka in the middle, the scrape would have continued. Data would queue. When the DB recovered, they'd backfill. No blind spot. Buffer = resilience. The cost of skipping the queue? Two hours of darkness when you needed light most. Never skip the buffer at scale.

---

## Surprising Truth / Fun Fact

Gorilla encoding—used by Facebook for their time-series storage—reduces 16-byte floats to roughly 1.5 bytes by exploiting a simple insight: adjacent metrics are usually close in value. Store the delta. Delta of deltas is even smaller. Compression ratios of 10× are common. Your "billions of points" problem becomes "hundreds of millions of bytes." Math saves you. The same idea powers video compression: what changed, not what is. Elegant. Powerful.

---

## Quick Recap (5 bullets)

- **Metrics pipeline = collect, store, query.** Agents on servers → buffer (Kafka) → time-series DB → dashboards and alerts.
- **Ingestion:** Push or pull. Scrape every 10–15 seconds. Buffer decouples collection from storage.
- **Storage:** Time-series DB (Prometheus, InfluxDB). Append-only. Gorilla compression. Write-optimized.
- **Querying:** Grafana for dashboards. Alertmanager for "if X then alert."
- **Scale:** 1000 servers × 100 metrics × 8640 intervals/day = 864M points/day. Plan retention and downsampling.

---

## One-Liner to Remember

**A metrics pipeline is a hospital's heart monitors for your servers—capture every heartbeat, store it, alert when something's wrong.**

---

## Next Video

Next: querying at scale, retention policies, and when to use push vs pull. Deeper into the pipeline.
