# Metrics and Observability: Cardinality and Cost

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

You track a metric: "request_count" with tags: service, endpoint, status_code, user_id. Simple, right? 100 services. 1,000 endpoints. 10 status codes. 10 million users. How many unique metric series? 100 × 1,000 × 10 × 10,000,000. One TRILLION. You cannot store a trillion time series. Your monitoring bill would be millions per month. That's the cardinality explosion. High-cardinality tags blow up storage and cost. Let's understand why—and how to avoid it.

---

## The Story

Metrics are numbers over time. "How many requests? How fast?" You add tags to slice and dice. "Requests per service. Per endpoint. Per status code." Useful. But then someone says: "Let's add user_id. I want per-user latency." Sounds reasonable. You have 10 million users. Now every unique user gets their own time series. 10 million series for that one metric. Multiply by more metrics. More tags. Combinatorial explosion. Your time-series database screams. Storage explodes. Query speed tanks. Your Datadog or Grafana Cloud bill? 10x. 100x. Cardinality is the silent killer of observability budgets. It creeps up. By the time you notice, you're in trouble.

---

## Another Way to See It

Imagine a filing cabinet. Each folder is a unique combination of tag values. "Service A, endpoint /users, status 200, user 12345" = one folder. Low cardinality: 100 folders. You can find anything fast. High cardinality: 10 million folders. The cabinet is enormous. Finding one file takes forever. Adding a new metric is like adding another cabinet. Add user_id as a tag? You just multiplied your cabinets by 10 million. The filing system breaks. Same with metrics. Cardinality = number of folders. Keep it low. Or pay the price.

---

## Connecting to Software

**Cardinality defined.** Cardinality = number of unique combinations of tag values. Low cardinality: service (10 values), env (3 values), region (5 values). 10 × 3 × 5 = 150 series. Cheap. High cardinality: user_id (10M values), request_id (unbounded), session_id (unbounded). Each creates a new series. Unbounded. Explosive. The rule: NEVER use user_id, request_id, or session_id as metric tags. Ever. Use them in logs. Use them in traces. Not in metrics. Metrics are for aggregation. Percentiles. Sums. Counts. Not "this one user's request."

**Cost control.** Aggregate. Store p50, p99, p999 latencies—not per-request. Downsample old data. Keep raw for 7 days. 1-minute rollups for 30 days. 1-hour rollups for 1 year. Drop unused metrics. Audit. "Who added user_id to request_count?" Remove it. Use sampling if you must track high-cardinality data. 1% of requests. Still expensive. Better than 100%. Budget before you build. "This metric will create N series. Can we afford it?"

**Three pillars.** Metrics, logs, traces. Each has different cardinality. Metrics: low. Aggregated. Cheap to store. Logs: high. Every request can be a log line. Structured. Indexed. Expensive. Traces: per-request. Very high cardinality. Sampling is normal. 1% or 0.1% of traces. Each pillar has its place. Don't mix them. Don't put high-cardinality data in metrics. That's what logs and traces are for.

---

## Let's Walk Through the Diagram

```
CARDINALITY EXPLOSION - TAG COMBINATIONS
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   LOW CARDINALITY                    HIGH CARDINALITY            │
│                                                                  │
│   request_count{                      request_count{              │
│     service="api",      ──► 100       service="api",              │
│     endpoint="/users",     series     endpoint="/users",         │
│     status="200"          (cheap)     status="200",              │
│   }                                   user_id="12345" ──► 10M    │
│                                       }            series (!!)   │
│                                                                  │
│   RULE: Avoid user_id, request_id, session_id as metric tags.   │
│   USE: Logs and traces for per-request, per-user detail.         │
│                                                                  │
│   METRICS (low card) ←── AGGREGATE ──► LOGS (high) ──► TRACES   │
│   p99 latency, count                 full request detail         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: Same metric. Add one tag: user_id. Series count explodes. 100 → 10 million. Storage, cost, query time—all blow up. The diagram shows the before and after. The fix: keep user_id out of metrics. Use it in logs where you need to debug a specific user. Use it in traces where you follow a request. Metrics stay aggregated. That's the boundary. Cross it, and you pay. Heavily.

---

## Real-World Examples (2-3)

**Stripe.** Processes millions of payments. Metrics: aggregate latencies, error rates, throughput. No customer_id in metrics. Customer-level debugging? Logs and traces. They learned this the hard way. Early on, someone added high-cardinality tags. Bill spiked. They rolled it back. Lesson learned.

**Datadog pricing.** Billed by metric count. High cardinality = more metrics = higher bill. Their docs explicitly warn: avoid high-cardinality tags. Customer support sees it daily. "Why is my bill 10x?" "Check your cardinality." Same story. Every time.

**Prometheus.** In-memory. High cardinality fills memory. OOM. Crash. Prometheus has cardinality limits. Exceed them, and you're in trouble. The solution: design metrics correctly from the start. Don't discover cardinality when you're drowning in it.

---

## Let's Think Together

**"You want per-user latency metrics. 10 million users. Why is this problematic? What's the alternative?"**

Problematic: 10 million time series. Each storing latency data points. Storage explodes. Cost explodes. Query "p99 latency for user X" is one query. But storing 10M series? Impossible at scale. Alternative: aggregate. Store p50, p99, p999 latency per service, per endpoint. No user_id. For "user X had slow requests"—that's a log search. Or a trace. Query logs: "user_id=12345 AND latency>1s." Or trace: find that user's requests, see the span. Metrics answer: "How is the system doing overall?" Logs and traces answer: "What happened to this specific user?" Different tools. Different cardinality. Use each for its purpose.

---

## What Could Go Wrong? (Mini Disaster Story)

A team ships a new feature. They add a metric: "feature_usage" with tag "user_id." Sounds useful. "How many users tried the feature?" They could have used a counter. One series. Instead, 5 million series. Each user = one series. Grafana Cloud. Week one: bill is normal. Week two: 5x. Week three: 20x. Finance flags it. "What changed?" The team digs. Cardinality. They remove user_id. Add a single counter: feature_usage_total. Problem solved. But the bill? Already run up. Hundreds of thousands of dollars. One tag. One mistake. Metrics cardinality isn't just a technical concern. It's a financial one. Audit your tags. Every new tag = potential explosion. Treat it like adding a new database table. Think first.

---

## Surprising Truth / Fun Fact

Prometheus stores each unique label combination as a separate time series. Even if two series differ by one label value, they're separate. That's why "request_count{user_id='1'}" and "request_count{user_id='2'}" are two series. With 10M users, that's 10M series. For ONE metric. Add status_code (5 values)? 50M series. Multiplicative. The math is brutal. One engineer's "helpful" tag can cost a company six figures per year. Cardinality is a design decision. Make it consciously.

---

## Quick Recap (5 bullets)

- **Cardinality = unique tag combinations.** Low = cheap. High = expensive. Explosive.
- **Rule:** Never use user_id, request_id, or session_id as metric tags. Logs and traces only.
- **Cost control:** Aggregate metrics (p50, p99). Downsample old data. Drop unused metrics.
- **Three pillars:** Metrics (low cardinality), Logs (high), Traces (per-request). Each has its place.
- **Design before you tag:** "How many series will this create?" If the answer is huge, rethink.

---

## One-Liner to Remember

**Cardinality is the multiplier that turns "one helpful metric" into a seven-figure observability bill—keep tags bounded, aggregate aggressively.**

---

## Next Video

Next: retention policies, downsampling strategies, and when to use metrics vs logs vs traces in depth.
