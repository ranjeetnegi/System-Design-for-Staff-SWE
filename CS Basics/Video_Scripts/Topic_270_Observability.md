# Observability: Logs, Metrics, Traces

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A patient in a hospital. Three monitoring systems. (1) The medical chart—detailed notes about every event. "Patient coughed at 3 PM. Took medicine at 4 PM. Complained of headache at 5 PM." That's LOGS. (2) The heart monitor—continuous vital numbers. Pulse 72. Blood pressure 120 over 80. Temperature 98.6. That's METRICS. (3) The patient's journey map—from admission to ER to X-ray to ward to discharge. One path through the system. That's TRACES. All three together—full observability. You know what happened, what the numbers look like, and where the patient spent time. Your software needs the same.

---

## The Story

Something is wrong. The API is slow. Users complain. How do you find the problem? You need visibility. Observability is the ability to understand the internal state of a system from its outputs. You don't instrument everything you can think of—you instrument so that when something goes wrong, you can ask questions and get answers. Logs, metrics, and traces are the three pillars. Each answers a different question. Together, they give you the full picture.

Logs tell you WHAT happened. "Error at line 45: null pointer." "User 123 logged in." "Payment failed: insufficient funds." Detailed. Text. High volume. Good for debugging a specific issue. Bad for "what's the trend over the last hour?" You don't want to grep through millions of log lines for that.

Metrics tell you HOW MUCH. Request count per second. p99 latency. Error rate. CPU usage. Aggregated numbers over time. Good for dashboards. Alerts. "When did latency spike?" Metrics answer that in one graph. Fast. But they don't tell you WHY. You see the spike. You don't see the individual slow request.

Traces tell you WHERE the time went. One request. Through API Gateway. Then Auth Service. Then Order Service. Then Database. Each hop has a duration. You see: Database took 200ms. Everything else was fast. The bottleneck is clear. Traces follow a single request through many services. They connect the dots. Without traces, you know "something is slow." With traces, you know "the database call in Order Service is slow."

---

## Another Way to See It

Imagine investigating a car accident. Logs are the witness statements—"I saw the car swerve at 3:42 PM." Metrics are the traffic statistics—"this intersection has 3 accidents per month on average." Traces are the skid marks—you follow the path from where the car started braking to where it stopped. All three help. Witnesses give detail. Statistics give context. Skid marks show the exact path. You need all three to understand what happened.

---

## Connecting to Software

**Logs:** Structured or unstructured. JSON is common: `{"level":"error","msg":"null pointer","user":123,"timestamp":"..."}`. Tools: ELK (Elasticsearch, Logstash, Kibana), Splunk, Loki, CloudWatch. Use for: debugging, auditing, security. Cost: high volume = expensive storage. Sample or aggregate for high-throughput systems. Keep logs for critical paths. Don't log every request—metrics do that better.

**Metrics:** Time-series data. Counter (requests total). Gauge (active connections). Histogram (latency distribution). Tools: Prometheus, Grafana, Datadog, CloudWatch. Use for: dashboards, alerting, SLOs. "p99 latency over 200ms" → alert. Fast queries. Low storage. But no request-level detail. You see the aggregate. You need traces or logs for the "why."

**Traces:** Distributed tracing. Each request gets a trace ID. Propagated through services. Each service creates a span—"I'm handling this request, it took 50ms." Parent-child relationship. Tools: Jaeger, Zipkin, OpenTelemetry, X-Ray. Use for: finding bottlenecks across services. "Request took 500ms total. 450ms was in the database call." Obvious. Without traces, you're guessing which of 20 microservices is slow.

---

## Let's Walk Through the Diagram

```
ONE REQUEST - TRACE VIEW:

Trace ID: abc123
|------------------------------------------------------------------------|
| API Gateway (5ms)                                                       |
|   |-- Auth Service (10ms)                                              |
|   |                                                                     |
|   |-- Order Service (50ms)                                              |
|         |-- Cache lookup (2ms) - HIT                                    |
|         |-- Database query (200ms)  ◄── BOTTLENECK!                     |
|         |-- Send to queue (3ms)                                         |
|         |                                                                |
|   |-- Notification Service (20ms) - async                              |
|------------------------------------------------------------------------|
Total: ~290ms. DB is 200ms. Fix the DB query.
```

Metrics would show "p99 latency 300ms" but not why. The trace shows: database. Fix the query. Add an index. Optimize the join. Traces turn "something is slow" into "this specific call is slow."

---

## Real-World Examples (2-3)

**Uber** built their own tracing system (Jaeger originated there). With hundreds of microservices, a single ride involves dozens of services. Without traces, debugging a slow booking flow would be guesswork. Traces show the path. They open-source Jaeger—now widely used.

**Stripe** runs on observability. Payments are critical. They need to know exactly where a failed payment got stuck. Logs for the error. Metrics for volume and success rate. Traces for the path. All correlated. Trace ID in logs. Same ID in metrics. Click through from dashboard to trace to log line. Full story.

**Amazon** pioneered many of these ideas. Their internal monitoring and distributed tracing systems evolved into what became CloudWatch and X-Ray. Observability at scale is a first-class concern. They've written about it in their builder's library.

---

## Let's Think Together

**"API is slow. Metrics show p99 latency spiked. How do you use traces and logs to find the root cause?"**

Start with the trace. Filter for slow requests (p99). Pick one. Follow the trace. Which service? Which call? Say it's the database. The trace shows "DB query 400ms." Now use logs. Filter logs by trace ID. You get the full context for that request. What was the query? What were the parameters? Maybe you see "SELECT * FROM orders WHERE user_id=123" — no index. The trace told you WHERE. The log told you WHAT. Together: add an index on user_id. Fixed. The workflow: metrics (detect) → traces (locate) → logs (detail). That's the power of the three pillars together.

---

## What Could Go Wrong? (Mini Disaster Story)

A team had great metrics. Dashboard. Alerts. But no traces. Latency spiked. They knew "Order Service is slow." Order Service called 5 other services. Which one? They added logging. Redeployed. Waited for the next spike. It came. Logs showed... nothing useful. The log level was wrong. They spent 4 hours adding more logs, redeploying, waiting. Finally found it: a third-party API was slow. With traces, they would have seen it in 5 minutes. The trace would show "External API call: 3 seconds." Lesson: invest in traces early. They're the fastest path from "something is slow" to "this exact call is slow." Logs and metrics aren't enough alone. You need all three.

---

## Surprising Truth / Fun Fact

The "three pillars" (logs, metrics, traces) were popularized by the observability movement around 2017-2018. But the idea is older. Google's Dapper paper (2010) described distributed tracing. Statsd and Graphite brought metrics to the mainstream. Logs have been around since the first programs. The innovation was connecting them—correlation IDs, trace IDs that flow through logs and metrics. One request. One ID. Click through. That connection is what makes modern observability powerful. Not three separate tools. One story.

---

## Quick Recap (5 bullets)

- **Logs** = what happened; detailed; good for debugging; high volume.
- **Metrics** = how much; aggregated; good for dashboards and alerts; fast.
- **Traces** = where time went; follow one request through services; find bottlenecks.
- **Workflow** = metrics detect → traces locate → logs give detail.
- **Correlation** = trace ID in logs and metrics; click from dashboard to trace to log.

---

## One-Liner to Remember

*Logs tell you what happened. Metrics tell you how much. Traces tell you where. All three together—you can answer any "why" question.*

---

## Next Video

Next: SLO, SLI, and error budget. The bus company promises 99% on-time arrival. How do they measure it? What happens when they miss? See you there.
