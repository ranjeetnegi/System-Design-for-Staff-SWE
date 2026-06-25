# Chapter 121 — Observability and Instrumentation

> *"You can't debug what you can't see. Observability is not about collecting more data — it's about being able to ask any question about your system's behavior and get an answer without deploying new code."*
> — Charity Majors, "Observability Engineering"

---

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                  AT-A-GLANCE: OBSERVABILITY AND INSTRUMENTATION                │
├─────────────────────────────────────────────────────────────────────────────────┤
│  THREE PILLARS    Metrics (what) + Logs (why) + Traces (where)                │
│                   Use all three; each answers different questions               │
│                                                                                 │
│  RED METHOD       Rate + Errors + Duration — for every service                │
│                   "How fast? How broken? How slow?"                            │
│                                                                                 │
│  USE METHOD       Utilization + Saturation + Errors — for every resource      │
│                   "How loaded? How queued? How failing?"                       │
│                                                                                 │
│  SLO ALERTING     Alert on error budget burn rate, not raw error counts       │
│                   Burn rate > 14.4× in 1hr → page (1% budget in 1 hour)      │
│                                                                                 │
│  CARDINALITY      High-cardinality labels (user_id, request_id) kill          │
│                   Prometheus. Use traces for high-cardinality queries.         │
│                                                                                 │
│  OPENTELEMETRY    The unified standard for metrics + logs + traces             │
│                   Instrument once, export to any backend (Prometheus,          │
│                   Jaeger, Grafana, Honeycomb, Datadog)                         │
│                                                                                 │
│  L5 SIGNAL        Adds RED metrics + structured logs + basic alerting         │
│  L6 SIGNAL        Designs the observability strategy for the org:             │
│                   cardinality budgets, SLO-based alerting, trace sampling,     │
│                   observability as a first-class requirement in design reviews │
│                                                                                 │
│  ALERT FATIGUE    The enemy of on-call health. Alerts that fire and are       │
│                   ignored are worse than no alerts. Every alert needs an       │
│                   owner and a runbook.                                          │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Part 1: Why Observability Matters

Imagine you're on-call at 3am. An alert fires: "payment service error rate elevated." You open your laptop. Now what?

Without observability:
- You look at logs. 10,000 log lines per second. Where's the error?
- You check the database. Looks normal.
- You restart the service. The alert clears. You don't know why.
- Two weeks later, the same thing happens.

With observability:
- You open the error rate dashboard. It spiked at 2:47am.
- You click the spike. It correlates with a deployment at 2:45am.
- You open a trace from the failure window. It shows: the new code path calls an external API that returns 429 (rate limited) but the code doesn't handle it — it propagates as a 500.
- Fix deployed at 3:15am. Postmortem written. Alert threshold tightened.

**The distinction between monitoring and observability:**

```
Monitoring:      Watching known failure modes.
                 "Alert if error rate > 1%"
                 Limited to questions you thought to ask in advance.

Observability:   The ability to understand any system state from its outputs.
                 "Why did this specific user's request fail at 2:47am?"
                 Answers questions you didn't know you'd need to ask.
```

Charity Majors' definition: "Observability is a measure of how well you can understand and explain any state your system has gotten itself into, no matter how novel or bizarre, solely from the outside."

**The cost of not investing in observability:**

```
Mean Time To Detect (MTTD):    How long before anyone knows there's a problem?
Mean Time To Resolve (MTTR):   How long to fix it?

Poor observability:  MTTD = 45+ minutes (customer reports it),
                     MTTR = 3-4 hours (guessing at root cause)

Good observability:  MTTD = 2-3 minutes (automated alert),
                     MTTR = 20-30 minutes (traces lead directly to root cause)

Business impact:     At $10M/day revenue, 2 hours of degraded service = ~$833K
                     (if 10% of transactions affected)
```

---

## Part 2: The Three Pillars of Observability

The three pillars are metrics, logs, and traces. They are complementary — not substitutes. Each answers different questions.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                    THE THREE PILLARS                                            │
├──────────────┬──────────────────────────────────────────────────────────────────┤
│ METRICS      │ Numeric measurements aggregated over time                       │
│              │ Question: "What is happening? How much? How fast?"              │
│              │ Example: "error rate = 2.3%, p99 latency = 450ms"              │
│              │ Tool: Prometheus, Datadog, CloudWatch                           │
│              │ Cost: low (aggregated numbers, not raw events)                  │
├──────────────┼──────────────────────────────────────────────────────────────────┤
│ LOGS         │ Timestamped event records                                        │
│              │ Question: "What happened for this specific event?"              │
│              │ Example: "2026-06-25 03:14:22 ERROR payment failed:             │
│              │           stripe returned 429 for user=xyz order=abc"           │
│              │ Tool: ELK Stack, Loki, CloudWatch Logs, Splunk                  │
│              │ Cost: high (full text, high volume)                             │
├──────────────┼──────────────────────────────────────────────────────────────────┤
│ TRACES       │ Distributed call graphs across services                         │
│              │ Question: "Where did this request spend its time?               │
│              │            Which service caused the latency?"                   │
│              │ Example: API gateway (5ms) → order service (12ms)              │
│              │           → payment service (430ms ← HERE) → DB (8ms)         │
│              │ Tool: Jaeger, Zipkin, Datadog APM, Honeycomb                   │
│              │ Cost: medium (sampled, not every request)                       │
└──────────────┴──────────────────────────────────────────────────────────────────┘
```

**How to use them together during an incident:**

```
Step 1: METRICS alert you.
        "Payment service error rate > 1% for 5 minutes."

Step 2: METRICS narrow the scope.
        Check dashboard: errors are on the /charge endpoint, started at 14:23.
        Error type: HTTP 500. Deployment at 14:20.

Step 3: LOGS explain a specific failure.
        Filter logs: service=payment, level=ERROR, time=14:23-14:30
        Find: "Stripe API returned 429, unhandled exception in PaymentProcessor.charge()"

Step 4: TRACES show the full picture.
        Find a trace from the failure window.
        See: the 429 from Stripe propagates through 3 services as a 500.
        Identify: missing error handling in payment-service AND missing retry in order-service.
```

---

## Part 3: Metrics Deep Dive

Metrics are the foundation of observability. Every service should emit metrics from day 1.

**The four metric types:**

```
COUNTER:   Monotonically increasing integer.
           Reset to 0 on restart.
           Use for: total requests, total errors, total bytes sent
           Example: http_requests_total{method="POST", status="200"} = 1,482,399
           Query: rate(http_requests_total[5m]) = requests per second

GAUGE:     Current value that can go up or down.
           Use for: active connections, memory usage, queue depth
           Example: active_connections{service="payment-api"} = 247
           Query: active_connections > 900 → alert

HISTOGRAM: Distribution of values bucketed by range.
           Use for: latency distribution, request size distribution
           Example: http_request_duration_seconds_bucket{le="0.1"} = 9,832
           Query: histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))
                  = p99 latency

SUMMARY:   Pre-computed quantiles (calculated on the client side).
           Use for: when you need accurate quantiles without Prometheus histogram_quantile
           Trade-off: cannot aggregate across instances; histogram is usually preferred
```

**Instrumenting a service — minimal viable metrics:**

```python
# Using prometheus_client (Python)
from prometheus_client import Counter, Histogram, Gauge, start_http_server
import time

# RED metrics: Rate, Errors, Duration
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code']
)

REQUEST_DURATION = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint'],
    buckets=[.005, .01, .025, .05, .1, .25, .5, 1, 2.5, 5, 10]
)

ACTIVE_REQUESTS = Gauge(
    'http_active_requests',
    'Currently active HTTP requests',
    ['endpoint']
)

# Usage in your handler
def handle_request(method: str, endpoint: str):
    start = time.time()
    ACTIVE_REQUESTS.labels(endpoint=endpoint).inc()
    
    try:
        result = process_request()
        REQUEST_COUNT.labels(method=method, endpoint=endpoint, status_code="200").inc()
        return result
    except Exception as e:
        REQUEST_COUNT.labels(method=method, endpoint=endpoint, status_code="500").inc()
        raise
    finally:
        duration = time.time() - start
        REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)
        ACTIVE_REQUESTS.labels(endpoint=endpoint).dec()
```

**Business metrics — beyond technical metrics:**

```python
# Don't just track HTTP — track business outcomes
PAYMENT_SUCCESS = Counter('payments_total', 'Total payments', ['status', 'provider'])
PAYMENT_AMOUNT = Histogram(
    'payment_amount_dollars',
    'Payment amounts in dollars',
    buckets=[1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000]
)
CHECKOUT_FUNNEL = Counter(
    'checkout_funnel_events_total',
    'Checkout funnel events',
    ['step']  # cart_viewed, checkout_started, payment_attempted, payment_succeeded
)
```

Business metrics let you answer: "Is the system healthy from the user's perspective?" Not just "Is the system healthy from the infrastructure perspective?"

---

## Part 4: The RED Method

The RED method (coined by Tom Wilkie at Weave Works) defines the three metrics every microservice should expose:

```
R — Rate:      How many requests per second is this service processing?
E — Errors:    What fraction of those requests are failing?
D — Duration:  How long does it take to process a request? (distribution, not average)
```

**Why these three specifically:**

These three metrics answer the most important question in incident response: "Is this service healthy from the user's perspective?"

- If Rate is much lower than expected → traffic is not reaching the service (upstream problem)
- If Errors are elevated → the service is failing requests
- If Duration is elevated → the service is slow (even if not erroring)

**The RED Prometheus queries:**

```promql
# Rate: requests per second (5-minute window)
rate(http_requests_total{service="payment-api"}[5m])

# Error rate: fraction of requests that failed
rate(http_requests_total{service="payment-api", status_code=~"5.."}[5m])
/
rate(http_requests_total{service="payment-api"}[5m])

# Error rate as percentage
100 * rate(http_requests_total{service="payment-api", status_code=~"5.."}[5m])
    / rate(http_requests_total{service="payment-api"}[5m])

# Duration: p99 latency
histogram_quantile(
    0.99,
    rate(http_request_duration_seconds_bucket{service="payment-api"}[5m])
)

# Duration: p50 and p99 together
histogram_quantile(0.50, rate(http_request_duration_seconds_bucket[5m]))
histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))
```

**Why p99, not average:**

```
10,000 requests:  9,900 take 10ms, 100 take 1,000ms
Average latency:  (9,900 × 10 + 100 × 1,000) / 10,000 = 19.9ms → looks fine
p99 latency:      1,000ms → 1 in 100 users waits 1 second → NOT fine

The average hides the worst user experiences.
p99 (99th percentile) is the latency 99% of users experience or better.
For services with SLA: use p99 or p99.9 as the SLO metric.
```

**The RED dashboard — one screen, all you need:**

```
┌──────────────────┬──────────────────┬────────────────────────────────┐
│  Rate (req/sec)  │  Error Rate (%)  │  p99 Latency (ms)             │
│  Time series     │  Time series     │  Time series                   │
│  Baseline: 1,200 │  Baseline: 0.05% │  Baseline: 120ms              │
├──────────────────┴──────────────────┴────────────────────────────────┤
│  Rate by endpoint (top 10)    │  Errors by status code              │
│  Bar chart                    │  Pie chart: 500 vs 503 vs 429       │
├──────────────────────────────┴──────────────────────────────────────┤
│  Latency heatmap (by endpoint × time)                                │
│  Highlights which endpoints are slow                                 │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Part 5: The USE Method

The USE method (Brendan Gregg) applies to infrastructure resources (CPU, memory, disk, network), not to services. Where RED asks "is the service healthy?" USE asks "is the infrastructure healthy?"

```
U — Utilization:  How busy is this resource? (% of time busy)
S — Saturation:   How much work is queued/waiting? (excess demand)
E — Errors:       Are there error events on this resource?
```

**USE for common resources:**

```
CPU:
  Utilization:  % CPU time used (target: < 70%)
  Saturation:   CPU run queue length (> 1 per core = saturated)
  Errors:       CPU throttling events (Kubernetes CPU limits)

Memory:
  Utilization:  % RAM used
  Saturation:   Swap usage, page faults, OOM events
  Errors:       OOM kills

Network:
  Utilization:  % of NIC bandwidth used
  Saturation:   Packet drops, retransmit rate
  Errors:       Network errors, dropped packets

Disk:
  Utilization:  % of time disk is busy
  Saturation:   I/O wait time, disk queue depth
  Errors:       Disk errors, I/O errors

Database connections:
  Utilization:  active_connections / max_connections
  Saturation:   Connections waiting in queue
  Errors:       Connection refused errors
```

**USE queries in Prometheus:**

```promql
# CPU utilization
100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)

# Memory utilization
(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) 
  / node_memory_MemTotal_bytes * 100

# Disk I/O utilization
rate(node_disk_io_time_seconds_total[5m]) * 100

# Network saturation (packet drops)
rate(node_network_receive_drop_total[5m])

# Database connection utilization
pg_stat_database_numbackends / pg_settings_max_connections * 100
```

**RED + USE = complete picture:**

During an incident, you need both. RED tells you "the service is slow." USE tells you "because the database is CPU-saturated." Without USE, you know there's a problem but not the root cause.

---

## Part 6: Logging Best Practices

Logs are the most common observability tool and the most commonly misused. Bad logs are worse than no logs — they hide the signal in noise.

**Structured logging — always:**

```python
# ❌ UNSTRUCTURED (hard to query, parse, or alert on)
logger.info(f"Payment processed for user {user_id}, amount {amount}, status success")
# Output: "2026-06-25 14:23:01 Payment processed for user usr_xyz, amount 99.99, status success"
# To find all payments > $100 for user group: grep + awk + pain

# ✅ STRUCTURED (JSON, queryable, correlatable)
import structlog
log = structlog.get_logger()

log.info(
    "payment_processed",
    user_id=user_id,
    order_id=order_id,
    amount_cents=amount_cents,
    currency="USD",
    provider="stripe",
    stripe_charge_id=charge_id,
    duration_ms=duration_ms,
    environment="production"
)
# Output: {"event": "payment_processed", "user_id": "usr_xyz", "order_id": "ord_abc",
#          "amount_cents": 9999, "provider": "stripe", "duration_ms": 142, ...}
# Query in Kibana: event:payment_processed AND amount_cents:[10000 TO *]
```

**Log levels — use them correctly:**

```
DEBUG:    Detailed information for debugging. NEVER in production by default.
          "Entering function calculate_tax with params: {order_id: ..., items: [...]}"
          
INFO:     Significant events in normal operation. Low volume.
          "Payment processed successfully. order_id=abc amount=99.99"
          "User registered. user_id=xyz email=..."
          
WARNING:  Something unexpected but recoverable.
          "Payment retry attempt 2 of 3. order_id=abc stripe_error=timeout"
          "Cache miss for frequently accessed key. key=user:1234:profile"
          
ERROR:    A request/operation failed. Needs attention.
          "Payment failed. order_id=abc error=insufficient_funds"
          "Database connection failed. retrying in 5s"
          
CRITICAL: System-level failure. Page someone now.
          "Database connection pool exhausted. all 100 connections in use"
          "Out of disk space. cannot write logs"
```

**What to always log:**

```python
# At service boundaries (incoming and outgoing requests):
log.info("request_received",
    method=request.method,
    path=request.path,
    user_id=auth.user_id,
    request_id=request.id,   # MUST: for correlating across logs
    ip_address=request.remote_addr
)

log.info("request_completed",
    request_id=request.id,
    status_code=response.status_code,
    duration_ms=duration_ms
)

# At external service calls:
log.info("external_call",
    service="stripe",
    endpoint="/v1/charges",
    request_id=request.id,
    stripe_request_id=stripe_response.request_id  # vendor's correlation ID
)

# On errors, always include:
log.error("payment_failed",
    order_id=order_id,
    error_type=type(e).__name__,
    error_message=str(e),
    request_id=request.id,
    stack_trace=traceback.format_exc()  # full stack in ERROR logs
)
```

**What NOT to log:**

```python
# ❌ Passwords, API keys, PII in plain text
log.info("user_login", password=request.password)  # NEVER
log.info("payment", card_number=card.number)        # NEVER — PCI violation

# ❌ Logs that fire on every function call
log.debug("entering process_item()")  # × 1M/second = 1M log entries/second

# ❌ Duplicate logging (same event logged in multiple places)
# If the HTTP handler logs the request, the service shouldn't log it again

# ❌ Logs without context (who? what request?)
log.error("Payment failed")  # which payment? which user? which request?
```

**The request_id pattern — critical for correlation:**

Every request should carry a unique request_id (UUID) that is:
1. Generated at the API gateway / load balancer (or by the client)
2. Passed via HTTP header (`X-Request-ID`) to every downstream service
3. Included in every log line for that request
4. Returned to the client in the response header

This allows you to find all logs across all services for a single user request:

```bash
# Find all logs for a failing request
grep "request_id=req_7f3a9b2c" /var/log/*/app.log
# Shows: gateway → auth-service → order-service → payment-service — full chain
```

---

## Part 7: Distributed Tracing

Distributed tracing solves the problem that logs cannot: "This request was slow — which service in the call chain caused the latency?"

**Core concepts:**

```
TRACE:   The full journey of a request through all services.
         A trace has a unique trace_id.
         
SPAN:    One unit of work within a trace (one service call, one DB query).
         A span has: span_id, parent_span_id, start_time, duration, service name,
                     operation name, status, tags/attributes.
         
CONTEXT  The trace_id and span_id passed between services
PROPAGATION: via HTTP headers (B3 format or W3C Trace Context).
```

**What a trace looks like:**

```
Trace ID: a3f8b2c9d1e4...

API Gateway                    [0ms  ──────────────── 450ms]
  └── Auth Service             [2ms  ── 15ms]
  └── Order Service            [18ms ─────────────── 430ms]
        └── DB: SELECT orders  [20ms ── 25ms]
        └── Payment Service    [28ms ──────────────── 425ms]  ← SLOW
              └── Stripe API   [30ms ─────────────── 420ms]  ← ROOT CAUSE
        └── Inventory Service  [426ms ─ 430ms]
```

Instantly: the slow request is caused by the Stripe API taking 390ms. Not the order service, not the DB. Stripe.

**Instrumenting traces with OpenTelemetry:**

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter

# Setup (once at startup)
provider = TracerProvider()
jaeger_exporter = JaegerExporter(
    agent_host_name="jaeger-agent",
    agent_port=6831,
)
provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))
trace.set_tracer_provider(provider)

tracer = trace.get_tracer(__name__)

# Instrument a function
def process_payment(order_id: str, amount: int):
    with tracer.start_as_current_span("process_payment") as span:
        span.set_attribute("order.id", order_id)
        span.set_attribute("payment.amount_cents", amount)
        
        try:
            result = stripe_client.charge(amount)
            span.set_attribute("stripe.charge_id", result.charge_id)
            span.set_status(trace.StatusCode.OK)
            return result
        except stripe.error.RateLimitError as e:
            span.set_status(trace.StatusCode.ERROR, str(e))
            span.record_exception(e)
            raise

# HTTP context propagation
from opentelemetry.propagate import inject, extract

# When making an outgoing HTTP call — inject trace context
headers = {}
inject(headers)
response = requests.post(
    "http://inventory-service/reserve",
    headers=headers,
    json={"order_id": order_id}
)

# When receiving an incoming HTTP call — extract trace context
from opentelemetry.instrumentation.flask import FlaskInstrumentor
FlaskInstrumentor().instrument_app(app)  # auto-instruments all Flask routes
```

**Trace sampling — the cardinality problem:**

At 10,000 req/sec, storing every trace would produce 10,000 traces/second. At 1KB per span and 10 spans per trace: 100MB/second = 8.6TB/day. Not sustainable.

```
Sampling strategies:

Head-based (probabilistic):   Sample N% of requests at the start.
                               Fast. Simple. Misses low-frequency bugs
                               (if you sample 1%, a bug affecting 0.5% is invisible).
                               
                               rate(1%)  → good for healthy-path analysis
                               rate(100%) on errors → always record failures
                               
Tail-based:                   Wait until request completes; decide whether to
                               keep the trace based on what happened.
                               Keep: all errors, all slow requests (p99+)
                               Discard: successful fast requests (most traffic)
                               
                               More expensive (buffer all spans until decision)
                               but dramatically better for finding bugs.
                               
                               OpenTelemetry Collector supports tail-based sampling.
```

---

## Part 8: OpenTelemetry — The Unified Standard

Before OpenTelemetry (OTel), you had to choose: Jaeger SDK or Zipkin SDK or Datadog SDK. Switching vendors required re-instrumenting every service.

OpenTelemetry solves this: instrument once, export to any backend.

**The OTel architecture:**

```
Application Code
    │ (OTel SDK — language-specific)
    │ emits: spans, metrics, logs
    ▼
OTel Collector (sidecar or standalone daemon)
    │ receives: OTLP protocol
    │ processes: batching, filtering, enriching
    │ exports to:
    ├── Jaeger (traces)
    ├── Prometheus (metrics)
    ├── Loki (logs)
    └── Datadog / Honeycomb / New Relic (SaaS backends)
```

**Auto-instrumentation — instrument without changing code:**

```bash
# Python: auto-instrument Flask, SQLAlchemy, Redis, requests, etc.
pip install opentelemetry-distro opentelemetry-exporter-otlp
opentelemetry-bootstrap -a install   # installs all auto-instrumentation packages

# Run your app with auto-instrumentation
opentelemetry-instrument \
  --traces_exporter otlp \
  --metrics_exporter otlp \
  --exporter_otlp_endpoint "http://otel-collector:4317" \
  python app.py
```

This automatically instruments:
- All HTTP requests (incoming and outgoing)
- All SQLAlchemy database queries
- All Redis operations
- All gRPC calls

Zero code changes. Every service gets distributed tracing.

**Go auto-instrumentation:**

```go
// Go: manual but standardized with OTel
import (
    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/trace"
)

func ProcessPayment(ctx context.Context, orderID string, amount int64) error {
    tracer := otel.Tracer("payment-service")
    ctx, span := tracer.Start(ctx, "ProcessPayment",
        trace.WithAttributes(
            attribute.String("order.id", orderID),
            attribute.Int64("payment.amount_cents", amount),
        ),
    )
    defer span.End()
    
    // Pass ctx to all downstream calls — this propagates the trace
    err := chargeStripe(ctx, amount)
    if err != nil {
        span.RecordError(err)
        span.SetStatus(codes.Error, err.Error())
        return err
    }
    return nil
}
```

---

## Part 9: SLOs, SLIs, and Error Budget Alerting

SLO-based alerting is the most important advancement in on-call practice in the last decade. Traditional threshold alerting ("alert if error rate > 1%") has two failure modes: too many alerts (alert fatigue) or too few (silent failures).

**The SLO framework:**

```
SLI (Service Level Indicator):
  The metric you're measuring.
  Example: "fraction of payment requests that succeed"
  
SLO (Service Level Objective):
  The target value for your SLI.
  Example: "99.9% of payment requests succeed over a 30-day window"
  
Error Budget:
  The allowable failures before the SLO is violated.
  At 99.9% over 30 days: 0.1% × 30 × 24 × 60 = 43.2 minutes of downtime allowed.
  
SLA (Service Level Agreement):
  The contract with customers. Usually weaker than internal SLO.
  If SLO = 99.9%, SLA = 99.5% (buffer so you don't pay penalties often)
```

**Error budget burn rate — the right way to alert:**

Alert not on the instantaneous error rate, but on how fast you're consuming your error budget.

```
30-day error budget at 99.9% SLO:
  Total requests in 30 days: assume 10M/day = 300M
  Allowed failures: 300M × 0.1% = 300,000 failures

Burn rate = actual failure rate / SLO failure rate
  SLO failure rate = 0.1%
  If current error rate = 1% → burn rate = 1% / 0.1% = 10×
  At 10× burn rate: budget exhausted in 30 / 10 = 3 days

Burn rate = 14.4× → exhausts 100% of budget in 2 hours
  → this is the "page now" threshold
```

**The Google SRE multi-window alerting approach:**

```promql
# Error budget burn rate over 1-hour window (fast burn)
(
  rate(http_requests_total{status=~"5..", job="payment-api"}[1h])
  /
  rate(http_requests_total{job="payment-api"}[1h])
) / 0.001 > 14.4

# Error budget burn rate over 6-hour window (slow burn)
(
  rate(http_requests_total{status=~"5..", job="payment-api"}[6h])
  /
  rate(http_requests_total{job="payment-api"}[6h])
) / 0.001 > 6

# Alert if EITHER window exceeds threshold
# 1-hour > 14.4× → page (1% of budget consumed in 1 hour)
# 6-hour > 6×    → ticket (6% of budget consumed in 6 hours)
```

**Why this is better than threshold alerting:**

```
Traditional: "Alert if error rate > 1%"
  Problem 1: At 0.9% for 30 days → no alert, but SLO violated
  Problem 2: At 1.1% for 5 minutes → alert fires, wakes on-call,
             but only 0.004% of budget consumed — not urgent

SLO burn rate: alerts only when budget consumption is meaningful
  Fast burn: "1% of monthly budget gone in 1 hour — page now"
  Slow burn: "6% of monthly budget gone in 6 hours — create ticket"
  No alert:  error rate elevated but budget consumption is manageable
```

**SLO error budget policy:**

```
If error budget > 50%:    Full speed ahead. Ship features.
If error budget 25-50%:   Normal pace but watch the dashboard.
If error budget 10-25%:   Slow down. Review high-risk deployments.
If error budget < 10%:    Feature freeze. Reliability work only.
If error budget exhausted: Incident in progress. Stop all launches.
```

This transforms the reliability conversation from "ops vs. dev" to "shared budget, shared risk."

---

## Part 10: Alert Design — Avoiding Alert Fatigue

Alert fatigue is when on-call engineers start ignoring alerts because they fire too often. It is the most dangerous reliability failure mode because it means real incidents go undetected.

**The symptoms of alert fatigue:**

```
1. On-call engineers acknowledge alerts without looking at them
2. "Expected" alerts — alerts that fire regularly and are always false positives
3. Runbooks that say "if this fires, wait and see if it clears"
4. On-call rotation considered a burden, not a responsibility
5. Post-incident reviews that say "the alert fired but we thought it was noise"
```

**The five alert design principles:**

```
1. EVERY ALERT MUST BE ACTIONABLE
   If you cannot write a runbook for an alert, delete the alert.
   "Service memory > 1GB" — what action do you take? If none, it's not an alert.

2. ALERTS SHOULD HAVE EXACTLY ONE OWNER
   If two teams both get paged, neither owns it. One team pages, others get Slack.

3. ALERT ON SYMPTOMS, NOT CAUSES
   Bad:  "MySQL replication lag > 60s"   (infrastructure cause)
   Good: "Payment success rate < 99.9%"  (user-facing symptom)
   Why:  Replication lag might be fine; what matters is whether users are impacted.

4. TUNE AGGRESSIVELY
   If an alert fires more than once per week as a false positive, tune it.
   Add minimum duration (only alert if condition persists for 5 minutes).
   Add minimum volume (only alert if > 100 requests/minute are affected).

5. REVIEW ALERTS QUARTERLY
   Each quarter: which alerts fired? How many were true positives?
   Delete or fix any alert with < 50% true positive rate.
```

**Alert severity levels:**

```
P1 (Critical — page now):
  Definition: User-facing SLO at risk of breach within 2 hours.
  Response: Page on-call immediately. All hands.
  Example: Payment error rate > 1% for 5 minutes (burn rate 10×+)

P2 (High — page during business hours):
  Definition: Degraded service but not immediately SLO-threatening.
  Response: Alert Slack. Fix within 4 hours.
  Example: p99 latency > 2× baseline for 30 minutes.

P3 (Medium — create ticket):
  Definition: Unusual pattern worth investigating.
  Response: Create ticket. Fix within 1 week.
  Example: Cache hit rate trending down over 24 hours.

P4 (Low — informational):
  Definition: Something you want to know but doesn't require action.
  Response: Log to Slack channel. Review weekly.
  Example: Deployment completed. New service version active.
```

**The runbook requirement:**

Every P1 and P2 alert must have a runbook. The runbook format:

```markdown
## Alert: PaymentServiceHighErrorRate

**Fires when:** Payment API error rate > 1% for 5 minutes (burn rate > 10×)

**Impact:** Users cannot complete payments. Revenue at risk: ~$1K/minute.

**Immediate steps:**
1. Check the payment service dashboard: [link to Grafana]
2. Identify if errors are on a specific endpoint (check by endpoint breakdown)
3. Check recent deployments: `kubectl rollout history deployment/payment-service`
4. Check Stripe API status: [status.stripe.com]

**Common causes and fixes:**
- New deployment introduced a bug → rollback: `kubectl rollout undo deployment/payment-service`
- Stripe API is degraded → enable fallback provider in config: [link]
- Database connection pool exhausted → check DB metrics, scale up pool size

**Escalation:**
- After 15 minutes without resolution: page #payments-team lead
- After 30 minutes: page VP Engineering

**Post-incident:** File incident report within 24 hours using template: [link]
```

**Alert anti-patterns to avoid:**

```
❌ The "canary" alert:  Fires every morning when traffic ramps up.
                        Engineers learn to ignore it. Delete or retune.

❌ The orphan alert:    Nobody knows who owns it. Nobody investigates it.
                        Every alert must have an owner in PagerDuty.

❌ The catch-all alert: "If anything is wrong, page me."
                        Too broad. Fires constantly. Useless.

❌ The vanity alert:    "Alert if CPU > 50%" (when 80% is normal for this service)
                        Trains engineers that alerts don't mean anything.

❌ The chatty dashboard alert: Fine for Slack notification, WRONG for pager.
                               Every pager alert should require a human to act.
```

---

## Part 11: Dashboard Design for Incidents

A great dashboard is one you can read in 30 seconds and understand what's wrong. Most dashboards are the opposite: 50 panels, no visual hierarchy, and you still can't tell if the service is healthy.

**Dashboard design principles:**

```
1. THE "SINGLE GLANCE" PRINCIPLE
   The top row of a dashboard should answer "is this service healthy?" 
   in 3-5 seconds. Use RED metrics: rate, errors, duration.
   
2. VISUAL HIERARCHY
   Most critical metrics: top, large
   Contributing details: middle, medium
   Deep-dive metrics: bottom, small
   Engineers scan top-to-bottom; put the most important thing first.
   
3. TIME CORRELATION
   All panels on the same time axis. Shift the time window together.
   During incidents, you need to compare: "did the DB spike before or after
   the error rate spiked?" Time-aligned panels make this possible.
   
4. ANNOTATIONS
   Show deployments as vertical lines on time series.
   Shows: "error rate went up exactly when deployment xyz happened."
   Automated with: Grafana annotations from your CD pipeline.
   
5. COLOR CONVENTION
   Red = bad, Green = good, Yellow = warning.
   Never use red for normal state (common mistake: red background for high traffic).
   Use consistent colors across all dashboards.
```

**The four-row incident dashboard template:**

```
Row 1: SERVICE HEALTH (always visible at top)
┌────────────────┬────────────────┬────────────────────────────────────┐
│  Error Rate    │  Request Rate  │  p99 Latency                       │
│  LARGE STAT    │  LARGE STAT    │  LARGE STAT                        │
│  Current: 2.1% │  Current: 1.2K │  Current: 480ms                   │
│  Normal: 0.05% │  Normal: 1.1K  │  Normal: 120ms                    │
└────────────────┴────────────────┴────────────────────────────────────┘

Row 2: BREAKDOWN (which endpoint / status code / region)
┌──────────────────────────────┬─────────────────────────────────────┐
│  Errors by endpoint          │  Errors by status code              │
│  Time series, multi-line     │  Time series, multi-line            │
└──────────────────────────────┴─────────────────────────────────────┘

Row 3: DEPENDENCIES (what the service depends on)
┌──────────────────────────────┬─────────────────────────────────────┐
│  Database query latency      │  Redis cache hit rate               │
│  External API (Stripe) rate  │  Downstream service error rate      │
└──────────────────────────────┴─────────────────────────────────────┘

Row 4: INFRASTRUCTURE (underlying resources)
┌──────────────────────────────┬─────────────────────────────────────┐
│  CPU utilization             │  Memory utilization                 │
│  Active DB connections       │  Disk I/O                           │
└──────────────────────────────┴─────────────────────────────────────┘
```

**Grafana tips:**

```json
// Grafana dashboard as code (JSON model excerpt)
{
  "panels": [
    {
      "title": "Error Rate",
      "type": "stat",
      "fieldConfig": {
        "defaults": {
          "thresholds": {
            "steps": [
              {"color": "green", "value": null},
              {"color": "yellow", "value": 0.1},
              {"color": "red", "value": 1.0}
            ]
          }
        }
      },
      "targets": [{
        "expr": "100 * rate(http_requests_total{status=~\"5..\"}[5m]) / rate(http_requests_total[5m])"
      }]
    }
  ]
}
```

**Dashboards for different audiences:**

```
Engineering (on-call) dashboard:
  Detailed metrics, technical, p99 latencies, query-level breakdowns
  Audience: engineers who need to debug

Management dashboard:
  Business metrics: payments/hour, MAU, checkout completion rate
  Trend lines over weeks/months, not seconds/minutes
  Audience: leadership who need business impact

Reliability dashboard:
  SLO health: % budget remaining, burn rate trend
  Incident frequency over 30/60/90 days
  MTTD and MTTR trends
  Audience: SRE team, reliability reviews
```

---

## Part 12: Cardinality — The Enemy of Metrics Systems

Cardinality is the number of unique label value combinations for a metric. High cardinality is the most common reason Prometheus runs out of memory.

**Why cardinality matters:**

```
Metric: http_requests_total
Labels: method, endpoint, status_code
Values:
  method:      GET, POST, PUT, DELETE = 4
  endpoint:    100 endpoints = 100
  status_code: 200, 201, 400, 401, 403, 404, 500, 503 = 8

Total time series: 4 × 100 × 8 = 3,200

Each time series in Prometheus uses ~3KB RAM
3,200 × 3KB = ~9.6MB — totally fine
```

The cardinality explosion problem:

```
Metric: http_requests_total
Labels: method, endpoint, status_code, user_id
Values:
  user_id: 10 million users = 10,000,000

Total time series: 4 × 100 × 8 × 10,000,000 = 32 BILLION time series
Memory required: 32B × 3KB = 96 PETABYTES — impossible

This is the cardinality explosion. Adding user_id as a Prometheus label
kills your metrics system.
```

**The cardinality rule:**

```
ALLOWED as Prometheus labels:
  service name, environment (prod/staging), region, endpoint (path template),
  HTTP method, status code, error type (enum)
  Rule: < 1,000 unique values per label

NOT ALLOWED as Prometheus labels:
  user_id, order_id, request_id, session_id, product_id, trace_id
  Rule: anything with unbounded cardinality
```

**High-cardinality questions → use traces:**

If you need to answer "what did user_id=xyz's requests look like?" — that's not a metrics question. That's a traces question.

```
Metrics:  "Error rate for endpoint /api/checkout is 2%" — low cardinality
Traces:   "Show me all failed traces for user_id=xyz" — high cardinality
Logs:     "Show me all logs where user_id=xyz AND status=ERROR" — full text search
```

**Cardinality budgets:**

```
Organization-level cardinality budget:
  Prometheus target: max 10M active time series
  Per-service budget: 100K time series
  Per-metric budget: 10K unique label combinations

Enforcement:
  Add cardinality checks in CI:
    - Static analysis on new metrics added to code
    - Alert if any metric exceeds 50K time series

Tools:
  mimirtool cardinality-check — scan for high-cardinality metrics
  prometheus: /api/v1/label/__name__/values — list all metric names
  tsdb analyze — show top metrics by time series count
```

**Practical cardinality control:**

```python
# ❌ HIGH CARDINALITY — kills Prometheus
REQUEST_COUNTER = Counter(
    'api_requests_total',
    'API requests',
    ['user_id', 'order_id', 'request_id']  # unbounded!
)

# ✅ LOW CARDINALITY — Prometheus-safe
REQUEST_COUNTER = Counter(
    'api_requests_total', 
    'API requests',
    ['endpoint', 'method', 'status_code', 'user_tier']
    # user_tier: free|paid|enterprise = 3 values max
)

# For high-cardinality context: use traces
# Attach user_id and order_id as SPAN ATTRIBUTES, not metric labels
span.set_attribute("user.id", user_id)
span.set_attribute("order.id", order_id)
```

---

## Part 13: Instrumentation Patterns by Service Type

Different service types have different instrumentation priorities.

**HTTP/REST API service:**

```python
# Mandatory: RED metrics + request_id correlation + trace propagation
# Additional: by-endpoint breakdown, by-user-tier breakdown

RECOMMENDED_METRICS = [
    "http_requests_total{method, endpoint, status_code}",
    "http_request_duration_seconds{method, endpoint}",
    "http_active_requests{endpoint}",
    "http_request_size_bytes{endpoint}",
    "http_response_size_bytes{endpoint}",
]

RECOMMENDED_LOGS = [
    "request_received: {method, path, user_id, request_id}",
    "request_completed: {request_id, status_code, duration_ms}",
    "auth_failed: {request_id, reason}",
    "rate_limit_applied: {user_id, endpoint, limit}",
]
```

**Worker / queue consumer service:**

```python
# Different metrics: throughput, lag, processing time, dead-letter queue

RECOMMENDED_METRICS = [
    "queue_messages_processed_total{queue, status}",      # rate
    "queue_message_processing_duration_seconds{queue}",   # duration
    "queue_depth{queue}",                                 # saturation
    "queue_consumer_lag_messages{queue, partition}",      # how far behind
    "queue_dead_letter_messages_total{queue, error_type}",# failed messages
]

# Critical: queue consumer lag
# If lag is growing, consumers can't keep up with producers.
# Alert: consumer_lag > 10,000 AND lag_growth_rate > 0 for 15 minutes
```

**Database-backed service:**

```python
# Focus on database performance metrics

RECOMMENDED_METRICS = [
    "db_query_duration_seconds{operation, table}",        # query latency
    "db_connections_active{pool}",                       # connection pool
    "db_connections_idle{pool}",                         # connection pool
    "db_queries_total{operation, table, status}",        # query rate
    "db_slow_queries_total{table, threshold_ms}",        # slow queries
    "db_deadlocks_total",                                # transaction health
]

# Critical log: slow query log
# Every query > 100ms should be logged with:
#   {query_hash, duration_ms, rows_examined, table, user_id, request_id}
```

**Scheduled job / cron service:**

```python
# Different pattern: jobs have start/end, not request/response

JOB_START_TIME = Gauge(
    'job_last_start_timestamp_seconds',
    'Unix timestamp when job last started',
    ['job_name']
)

JOB_DURATION = Histogram(
    'job_duration_seconds',
    'Job execution duration',
    ['job_name', 'status']
)

JOB_LAST_SUCCESS = Gauge(
    'job_last_success_timestamp_seconds',
    'Unix timestamp when job last succeeded',
    ['job_name']
)

# The "dead man's switch" alert:
# Alert if job_last_success is > 2 × expected_interval
# Example: daily job should succeed within 25 hours (1 day + buffer)
# Alert if: time() - job_last_success > 90000 (25 hours)
```

**Cache layer (Redis):**

```python
# Focus on hit rates and evictions

RECOMMENDED_METRICS = [
    "cache_requests_total{status}",         # hit, miss, error
    "cache_hit_rate",                       # hits / total (gauge)
    "cache_evictions_total",                # memory pressure
    "cache_memory_used_bytes",              # capacity planning
    "cache_connected_clients",             # connection pool
    "cache_commands_processed_total{command}", # by-command breakdown
]

# Alert: cache_hit_rate < 0.85 for 10 minutes (unexpected miss spike)
# Alert: cache_evictions_total rate increasing > 2× normal
```

---

## Part 14: Observability vs. Monitoring — The Critical Distinction

This distinction matters for L5→L6 growth and for staff-level discussions.

```
MONITORING (traditional):        OBSERVABILITY (modern):

Watches predefined conditions.   Answers arbitrary questions.
"Is X above threshold Y?"        "What happened for this user at 14:23?"

Fails when:                      Handles:
  New failure mode appears         Any novel failure mode
  (alert doesn't exist for it)     (you can slice and drill to find it)

Requires:                        Requires:
  Knowing what to watch           Rich instrumentation emitting context
  in advance

Tools:                           Tools:
  Nagios, basic Prometheus        Honeycomb, Datadog, OTel + Jaeger
  threshold alerts                high-cardinality event storage
  
Maturity: Good for stable,       Maturity: Necessary for complex,
          simple services        distributed, evolving systems
```

**The practical implication at L5:**

You don't need to rebuild your stack around Honeycomb. But you should:
1. Emit structured logs with enough context to answer "why did this specific request fail?"
2. Use distributed tracing so you can correlate across services
3. Build dashboards from a "debugging workflow" perspective, not a "metrics collection" perspective

**The honeycomb model — high-cardinality events:**

Honeycomb stores individual events (not aggregated metrics) and allows you to filter and group on any field, including high-cardinality fields like user_id or order_id.

```
Traditional (Prometheus):
  You can query: "what's the p99 latency for /checkout?"
  You cannot query: "what's the p99 latency for user_id=xyz?"
  (because user_id has unbounded cardinality)

Honeycomb:
  You can query: "what's the p99 latency for user_id=xyz?"
  "Filter: user_id = xyz. Group by: endpoint. Calculate: p99(duration_ms)"
  Answer: instant.

Trade-off: Honeycomb costs 3-5× more than Prometheus + Grafana.
Justification: For high-scale systems where incidents are expensive,
               the ability to ask "why is this specific user impacted?"
               pays for itself in MTTR reduction.
```

---

## Part 15: Exemplars — Bridging Metrics and Traces

Exemplars solve the "metrics show there's a problem, but how do I find the traces?" problem.

An exemplar is a sample trace_id attached to a specific metric observation. When Prometheus records a histogram observation, it can also record the trace_id for that specific request.

```python
# Prometheus Python client with exemplars
from prometheus_client import Histogram
from opentelemetry import trace

REQUEST_DURATION = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration',
    ['endpoint']
)

def handle_request(endpoint: str):
    start = time.time()
    try:
        result = process()
        return result
    finally:
        duration = time.time() - start
        # Get current trace ID from OTel context
        span = trace.get_current_span()
        trace_id = format(span.get_span_context().trace_id, '032x')
        
        # Record metric WITH exemplar (the trace ID)
        REQUEST_DURATION.labels(endpoint=endpoint).observe(
            duration,
            exemplar={'traceID': trace_id}  # exemplar!
        )
```

**How exemplars work in Grafana:**

When you see a spike on a latency histogram in Grafana, you click on the spike. Grafana shows you the exemplar — the trace_id from that exact time window. One click takes you from "the p99 spiked" to "here's the exact slow trace."

This is the workflow that turns a 2-hour investigation into a 10-minute one.

---

## Part 16: Observability for Kubernetes

Kubernetes introduces additional observability challenges: containers restart, pods move between nodes, and service endpoints change dynamically.

**Essential Kubernetes metrics:**

```promql
# Pod restart rate (containers crashing)
increase(kube_pod_container_status_restarts_total[1h]) > 5

# OOMKilled containers (memory limit issues)
kube_pod_container_status_last_terminated_reason{reason="OOMKilled"}

# Pending pods (scheduling issues)
kube_pod_status_phase{phase="Pending"} > 0

# HPA not at desired replicas (scaling issues)
kube_horizontalpodautoscaler_status_current_replicas
  != kube_horizontalpodautoscaler_status_desired_replicas

# CPU throttling (CPU limits too low)
rate(container_cpu_cfs_throttled_seconds_total[5m]) 
  / rate(container_cpu_cfs_periods_total[5m]) > 0.25
```

**kube-state-metrics + node-exporter:**

The Kubernetes observability stack:

```yaml
# Install Prometheus stack with Kubernetes monitoring
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace \
  --set grafana.adminPassword="changeme"

# This installs:
# - Prometheus (metrics collection)
# - Grafana (dashboards)
# - kube-state-metrics (cluster-level metrics: pod status, HPA, etc.)
# - node-exporter (node-level metrics: CPU, memory, disk, network)
# - AlertManager (alert routing and deduplication)
# - Pre-built dashboards for Kubernetes
```

**Log aggregation in Kubernetes — Loki:**

```yaml
# Promtail (log shipper) configuration
# Runs as DaemonSet, ships logs from all pods to Loki
config:
  clients:
    - url: http://loki:3100/loki/api/v1/push
  
  scrape_configs:
    - job_name: kubernetes-pods
      kubernetes_sd_configs:
        - role: pod
      
      pipeline_stages:
        - docker: {}              # parse Docker log format
        - json:                   # parse JSON logs
            expressions:
              level: level
              message: message
              request_id: request_id
        
        - labels:                 # add as queryable labels
            level:
            request_id:
```

**The benefit:** In Grafana, you can view metrics and logs side-by-side, correlated in time, without leaving the dashboard.

---

## Part 17: The On-Call Experience — Practical Observability

The real test of an observability system is: can a new engineer, on-call for the first time, effectively debug an incident at 3am?

**The incident debugging playbook:**

```
STEP 1: ORIENT (2-3 minutes)
  Open the service's RED dashboard.
  Answer: What's the error rate? Rate? Latency? When did it start?
  Correlate: Was there a deployment? A configuration change? A traffic spike?

STEP 2: NARROW (3-5 minutes)
  Which endpoint? Which status code? Which region?
  Use dashboard breakdowns to isolate the signal.
  "All errors are on /api/checkout. Status code 503. Only in us-east-1."

STEP 3: TRACE (5-10 minutes)
  Find a failed trace from the failure window.
  Walk the trace: which service returned the 503?
  The trace shows: order-service called inventory-service, which returned 503.
  
STEP 4: INVESTIGATE (10-15 minutes)
  Open the inventory-service dashboard.
  Check its RED metrics: error rate 100%. All requests failing.
  Check logs: "database connection refused" — DB is down.
  Check DB dashboard: yes, DB is restarting after OOMKill.
  
STEP 5: RESOLVE
  Identified root cause: inventory DB OOMKilled. Restarting.
  Short-term: increase memory limit. Apply immediately.
  Long-term: add circuit breaker in order-service so checkout can succeed
             even when inventory is down (best-effort reservation).
```

**Measuring the quality of your observability:**

```
MTTD (Mean Time To Detect):
  Target: < 5 minutes for P1 incidents
  Measure: time from incident start to first alert

MTTR (Mean Time To Resolve):
  Target: < 30 minutes for P1 incidents
  Measure: time from first alert to incident resolved

False positive rate:
  Target: < 20% (8 of 10 pages should be real incidents)
  Measure: in PagerDuty, tag each alert as true/false positive

Coverage:
  Target: 100% of user-facing endpoints have SLO alerts
  Measure: audit endpoints without SLO definitions quarterly
```

---

## Part 18: L5 vs. L6 Calibration

**What L5 engineers do well:**

```
✅ Adds RED metrics to new services from day 1
✅ Writes structured logs with request_id correlation
✅ Configures basic alerting on error rate and latency
✅ Creates service dashboard using team's standard template
✅ Writes runbooks for the alerts they create
✅ Uses traces to debug cross-service latency issues
✅ Knows the difference between monitoring and observability
✅ Understands SLOs and can set reasonable targets
✅ Recognizes cardinality issues before they cause problems
```

**What L5 engineers often miss:**

```
🟡 Treating alerts as a one-time setup, not maintained quarterly
🟡 Creating dashboards that look complete but don't help during incidents
🟡 Under-sampling traces (missing the rare but critical failures)
🟡 Logging too much (debug-level in production) or too little
🟡 Not measuring business outcomes — only technical metrics
🟡 Not using error budgets to have reliability conversations with PMs
```

**What L6 engineers add:**

```
⭐ Designs the observability strategy for the team or org
   Not "add prometheus" but "how do we instrument our 50 services consistently?"
   
⭐ Creates the team's instrumentation library
   Shared middleware that all services use, so every service gets
   RED metrics, trace propagation, and structured logging automatically.
   
⭐ Defines the organization's SLO framework
   Which services need 99.9% SLOs? Which need 99.99%?
   How do we compute error budgets? Who reviews them?
   
⭐ Builds the on-call experience
   Not just technical — who is on-call, how long are rotations,
   how are incidents reviewed, how are alerts tuned?
   
⭐ Makes observability a first-class design requirement
   In design reviews: "What are the SLIs for this feature?
   How will we know it's working from the user's perspective?
   What does a failure look like and how will we detect it?"
   
⭐ Measures the observability system itself
   MTTD trends over quarters, false positive rate per team,
   percentage of incidents detected by alerts vs. customer reports.
```

**The interview signal:**

```
L5 interview answer to "how would you instrument a new service?":
  "I'd add Prometheus metrics: request count, error count, latency histogram.
   I'd add structured logging with request_id. I'd set up alerts for
   error rate and p99 latency."

L6 interview answer to "how would you instrument a new service?":
  "Before adding metrics, I'd define the SLO: what does 'healthy' mean
   for this service from the user's perspective? Then work backward:
   what SLI measures that health? RED metrics for user-facing endpoints.
   But also business metrics — if this is the payment service, I want to
   know payments per minute, not just HTTP 200s.
   
   For the organization, I'd build a standard instrumentation library
   that makes doing the right thing the default — so engineers don't have
   to think about it. Every service that imports our HTTP middleware
   automatically gets RED metrics, distributed trace context propagation,
   structured logging with request_id, and our SLO dashboard template.
   
   And I'd define our on-call practices: who owns the alerts, how we tune
   them, how we measure our MTTD/MTTR over time. Observability is only
   valuable if it actually reduces MTTR."
```

---

## Part 19: War Stories

**War Story 1: The Invisible Degradation**

A payment service team got an alert: error rate 0.8% (below the 1% threshold). The on-call engineer checked the dashboard, saw the error rate below threshold, and went back to sleep.

Two hours later, a customer support ticket: "I've been trying to check out for 3 hours and keep getting errors." The error rate had been 0.8% — high enough to affect many users, but below the alerting threshold.

**The lesson:** Threshold alerts on error rate are brittle. The team switched to SLO burn rate alerting. A 0.8% error rate (when baseline is 0.05%) is a 16× burn rate — pages immediately.

**War Story 2: The Dashboard That Lied**

A team's dashboard showed "average latency: 45ms — healthy." During an incident, users complained the site was slow. The on-call engineer checked the dashboard: normal. Spent 90 minutes investigating nothing.

Finally checked the raw Prometheus: p99 was 3,200ms. The dashboard was showing average latency — which was fine, because 95% of requests were fast. But the 5% of slow requests were very slow (database index missing, affecting specific query patterns).

**The lesson:** Never display average latency. Only p50, p95, p99, and p99.9. The team rebuilt every dashboard with histograms. The next incident: identified in 8 minutes.

**War Story 3: The Alert That Cried Wolf**

An infrastructure team had a "disk usage > 70%" alert that fired every Monday morning when a batch job ran. The alert had fired every Monday for 6 months. On-call engineers had learned: "Monday morning disk alert = ignore, it'll clear."

One Monday, the disk was actually full. An engineer acknowledged the alert without looking at it. The service crashed 2 hours later when it couldn't write logs.

**The lesson:** An alert that regularly fires as a false positive is worse than no alert. The team scheduled disk cleanup to run Sunday night, eliminating the false positive. And added a new "disk usage > 90%" alert that had never fired as a false positive — and got respected.

**War Story 4: The Missing Trace**

A team was investigating latency: p99 latency was 800ms but they couldn't find the slow service. Their traces showed: API gateway → service A → service B → response. All spans looked fast. But they were sampling at 1% — the 99th percentile requests weren't in the sample.

**The lesson:** Always sample 100% of slow requests (p99+), regardless of your overall sampling rate. Add tail-based sampling: "keep any trace where total duration > 500ms." The team found the slow service within 10 minutes of enabling tail-based sampling.

**War Story 5: The $200K Logging Bill (see also Ch120)**

A startup deployed a new feature that added verbose debug logging (JSON objects with full request context) on every operation. The team was spending $45K/month on logging infrastructure. Nobody had the budget attribution wired up — logs were going to CloudWatch Logs but the team didn't see the bill until the quarterly cloud review.

The fix: added structured log with a single line per request (not one per operation), lowered log level in production from DEBUG to INFO. Monthly bill: $3K.

**The lesson:** Log volume directly maps to cost. Add logging budget as a metric: `log_bytes_written_total`. Alert if it grows > 2× from the weekly baseline.

---

## Part 20: Pre-Interview Drill — 12 Questions

These are the observability questions most commonly asked in L5/L6 interviews. Practice answering each out loud.

**Q1: How would you define SLOs for a new service?**

"Start with the user's perspective: what does 'working' mean for this service? For a payment service: '99.9% of checkout attempts succeed.' For a search service: 'p99 latency < 500ms and error rate < 0.1%.' Then work backward to the SLIs that measure those outcomes, and instrument accordingly."

**Q2: What's the difference between a metric, a log, and a trace? When do you use each?**

"Metrics answer 'what is happening and how much?' — aggregated numbers over time. Logs answer 'what happened for this specific event?' — detailed records of individual occurrences. Traces answer 'where did this request spend its time across services?' Use metrics for alerting and trends. Use logs to understand the details of a specific failure. Use traces when latency is the problem and you need to find which service is slow."

**Q3: What is the RED method? Apply it to a service you've worked on.**

"RED: Rate (requests per second), Errors (fraction that fail), Duration (latency distribution). For the payment service I worked on: Rate = charges per second, Errors = fraction of charges that return a non-200 status, Duration = time from request to response including Stripe API call. These three metrics on a single dashboard answered 80% of incident questions."

**Q4: What is alert fatigue, and how do you prevent it?**

"Alert fatigue is when engineers start ignoring alerts because they fire too often as false positives. Prevent it by: (1) only alerting on symptoms, not causes, (2) requiring every alert to have a runbook and an owner, (3) reviewing alerts quarterly and deleting any with < 50% true positive rate, (4) using SLO burn rate alerting instead of raw threshold alerting."

**Q5: What is cardinality in the context of Prometheus? Why does it matter?**

"Cardinality is the number of unique label value combinations for a metric. Each unique combination is a separate time series. Prometheus stores each time series in RAM. Add user_id as a label on a metric with 10M users = 10M time series just for that metric = potentially gigabytes of RAM. High cardinality kills Prometheus. Use traces (not metrics) for high-cardinality questions like 'what did user X experience?'"

**Q6: How do distributed traces work? What is context propagation?**

"A trace is the full journey of a request across all services, made up of spans — one per service call. Each span has a trace_id, span_id, and parent_span_id, forming a tree. Context propagation means passing the trace_id and span_id in HTTP headers (like W3C traceparent) when calling downstream services. The downstream service creates a new span with parent = the incoming span_id. This builds the full tree."

**Q7: What would you look at first when investigating a latency spike?**

"First: the service's RED dashboard — confirm latency is elevated and note when it started. Second: check for correlated deployment (annotations on the chart). Third: look at latency by endpoint to isolate which endpoint is slow. Fourth: find a trace from the failure window and walk the trace — which service's span is the longest? Fifth: check that service's dashboard and logs. This process takes 15-20 minutes with good observability."

**Q8: What is an error budget, and how is it used in practice?**

"Error budget is the allowable failures before an SLO is breached. If SLO = 99.9% over 30 days, the error budget is 0.1% × 30 × 24 × 60 = 43.2 minutes of total downtime. In practice: when > 50% of budget remains, ship features freely. When < 10% remains, freeze feature deployments and focus on reliability work. This makes reliability a shared responsibility between product and engineering — not just an operations concern."

**Q9: How do you design an on-call rotation that doesn't burn people out?**

"Follow-the-sun coverage when possible (hand off between time zones so nobody is paged at 3am regularly). Cap weekly on-call shifts at 1 per person. Aim for < 5 pages per week total — if consistently more, fix the alerts first. Require every P1 incident to have a 5-minute postmortem to prevent recurrence. Compensation: time-in-lieu or extra PTO for disruptive on-call weeks. And critically: fix the alerts. Alert fatigue is the biggest burnout driver."

**Q10: What is OpenTelemetry and why does it matter?**

"OpenTelemetry is the CNCF standard SDK for emitting metrics, logs, and traces. It matters because it decouples instrumentation from the backend. You instrument your code once with the OTel SDK, and can export to Jaeger, Datadog, Honeycomb, Prometheus, or any other backend by changing configuration — not code. This prevents vendor lock-in and allows you to change your observability stack as your needs evolve."

**Q11: How would you instrument a microservices system from scratch?**

"Start by defining SLOs for every user-facing service. Then: (1) add OTel SDK to every service with auto-instrumentation for HTTP, gRPC, and DB drivers, (2) deploy OTel Collector as a sidecar, exporting to Prometheus + Jaeger, (3) build a standard HTTP middleware that adds request_id, structured logging, RED metrics, and trace context propagation automatically, (4) create a standard service dashboard template in Grafana, (5) define SLO alerts using burn rate, not thresholds. The goal: a new service gets all of this by default, not by manual setup."

**Q12: What's the difference between availability and reliability?**

"Availability = uptime percentage (binary: service is up or down). Reliability = the broader user experience (service may be 'up' but slow, returning errors for edge cases, or degraded in specific regions). SLOs capture reliability better than uptime SLAs because they measure error rates and latency, not just whether the service responds. A service with 100% uptime but 5% error rate is unreliable despite perfect availability."

---

## Part 21: Behavioral Interview STAR Answer

**Question: "Tell me about a time you improved system reliability or reduced MTTR."**

**STAR:**

**Situation:** At [company], the payment service was experiencing intermittent failures that took 90+ minutes to diagnose. The on-call team would get paged, spend an hour looking at logs across 8 different services, and often only find the root cause after the issue had self-resolved.

**Task:** I was asked to lead an initiative to reduce our MTTR for payment-related incidents. We had a target of < 30 minutes MTTR for P1 incidents.

**Action:** I ran a 4-week initiative:
- Week 1: Analyzed the last 10 incidents. Found the pattern: we had no distributed tracing, so engineers were correlating logs across services manually using timestamps (not request IDs).
- Week 2: Deployed OpenTelemetry across all 8 services in the payment path. Added trace context propagation via our HTTP middleware layer. This was a one-time change: all services got tracing by updating the middleware library.
- Week 3: Built a payment-specific incident dashboard: trace explorer link directly from the error rate chart, plus exemplars connecting metric spikes to specific traces.
- Week 4: Rewrote the 3 most-used runbooks to include "Step 1: find a failing trace using [link to query]."

**Result:** MTTR for payment incidents dropped from 90 minutes to 23 minutes over the next quarter. False positive rate on alerts also dropped because we could now quickly confirm "this alert is real" vs. "this alert is noise" using a trace. The initiative was adopted as the standard for all services — we now require distributed tracing as part of the "done" criteria for new services.

---

## Part 22: Exercises

**Exercise 1: Instrument a service from scratch**

Take any service you've written. Add:
1. Prometheus RED metrics (rate, errors, duration as histogram)
2. Structured logging with request_id
3. OpenTelemetry tracing with span attributes (user_id, relevant business IDs)

Run Prometheus + Grafana locally (docker-compose), visualize your metrics, and write one alert for the error rate.

**Exercise 2: Design an SLO**

Pick a service or product you use daily. Define:
1. The SLI (what to measure)
2. The SLO target (99.9%? 99.5%?)
3. The error budget (how much allowed failure in 30 days?)
4. The alert thresholds (burn rate alerts)
5. The error budget policy (what happens at 50% / 10% / 0%?)

**Exercise 3: Debug a trace**

Set up a demo application with OpenTelemetry (the OpenTelemetry demo project at `github.com/open-telemetry/opentelemetry-demo` is excellent). Introduce a latency bug in one service (add a `time.sleep(2)` in a handler). Then: find the bug using only the tracing UI. Write down how long it took and what the investigation path looked like.

**Exercise 4: Alert audit**

If you have a production service: audit its alerts. For each alert:
- How many times did it fire in the last 90 days?
- What fraction were true positives?
- Does it have a runbook?
- Does it have an owner?

Propose changes: delete low-value alerts, tune thresholds, add runbooks.

---

## Part 23: Tools Reference Card

```
METRICS COLLECTION:
  Prometheus:         Open source; pull-based; excellent Kubernetes integration
  Datadog:            SaaS; best-in-class out-of-box integrations; expensive
  CloudWatch:         AWS-native; good for AWS services; expensive at scale
  InfluxDB:           Time-series DB; write custom queries; self-hosted

VISUALIZATION:
  Grafana:            Best-in-class open source dashboards; supports all backends
  Kibana:             Elastic's dashboard; best for log visualization
  Datadog Dashboard:  SaaS; easier setup than Grafana; less flexible

LOG AGGREGATION:
  ELK Stack:          Elasticsearch + Logstash + Kibana; powerful, complex
  Loki:               Prometheus for logs; cheap; integrates with Grafana
  Splunk:             Enterprise; very powerful; very expensive
  CloudWatch Logs:    AWS-native; easy setup; expensive at high volume

DISTRIBUTED TRACING:
  Jaeger:             CNCF; open source; excellent for OTel traces
  Zipkin:             Older standard; still widely used
  Datadog APM:        SaaS; best out-of-box experience; expensive
  Honeycomb:          High-cardinality event storage; best for complex systems
  Tempo (Grafana):    Open source; pairs with Grafana + Loki + Prometheus

UNIFIED (OTel):
  OpenTelemetry SDK:  Instrument once; export anywhere
  OTel Collector:     Receive → process → export; runs as sidecar or gateway

ON-CALL:
  PagerDuty:          Industry standard; excellent routing, escalation
  OpsGenie:           Good alternative to PagerDuty; Atlassian ecosystem
  VictorOps:          Now Splunk On-Call

SLO MANAGEMENT:
  Nobl9:              SLO platform; integrates with any metrics source
  Sloth:              Open source SLO generator for Prometheus
  Google Cloud SLOs:  Built into Cloud Monitoring for GCP users
```

---

## Part 24: Vocabulary Quick Reference

```
Alert fatigue:      When engineers start ignoring alerts because of too many false positives.

Cardinality:        Number of unique time series for a metric. High cardinality
                    (user_id, request_id as labels) causes Prometheus OOM.

Error budget:       The allowed failure budget before SLO breach.
                    = (1 - SLO) × window_duration

Exemplar:           A trace_id attached to a metric observation, linking metrics to traces.

MTTD:               Mean Time To Detect. How long before an alert fires after incident start.

MTTR:               Mean Time To Resolve. How long from first alert to incident resolved.

Observability:      The ability to understand any system state from its outputs without
                    deploying new code.

RED method:         Rate + Errors + Duration — for every microservice.

SLI:                Service Level Indicator. The metric you're measuring.
                    Example: fraction of requests that succeed.

SLO:                Service Level Objective. The target for the SLI.
                    Example: 99.9% of requests succeed over 30 days.

SLA:                Service Level Agreement. The customer-facing contract.
                    Usually weaker than internal SLO (buffer for SLO misses).

Span:               One unit of work in a distributed trace. Has trace_id, span_id,
                    parent_span_id, start_time, duration.

Structured logging: Logging as machine-parseable key-value pairs (JSON) rather than
                    plain text strings.

Tail-based sampling: Tracing strategy that decides whether to keep a trace after it
                    completes — keeps all errors and slow traces, discards healthy ones.

Trace:              The full journey of a request through all services, represented as
                    a tree of spans.

USE method:         Utilization + Saturation + Errors — for every infrastructure resource.
```

---

## Part 25: L5 Instrumentation Checklist

Use this checklist when adding a new service or reviewing an existing one:

```
METRICS:
□ Request rate (counter, per-endpoint)
□ Error rate (counter, per-endpoint, per-status-code)
□ Request duration (histogram, per-endpoint)
□ Active requests (gauge, per-endpoint)
□ Business metrics (payments/sec, checkouts/sec, etc.)
□ Dependency health (external API latency, DB query time)
□ No high-cardinality labels (user_id, request_id in metric labels)

LOGS:
□ Structured logging (JSON, not plain text)
□ request_id on every log line
□ user_id on authenticated requests
□ Correct log levels (INFO for business events, DEBUG not in production)
□ No PII/secrets in logs
□ Log at service entry and exit
□ Log at external service calls

TRACES:
□ OTel SDK installed and configured
□ HTTP middleware auto-instruments all inbound requests
□ Outgoing HTTP/gRPC calls propagate trace context
□ Key business IDs as span attributes (order_id, user_id, etc.)
□ Error spans have exception recorded
□ Sampling configured (100% errors + 1% healthy minimum)

ALERTS:
□ SLO defined for user-facing endpoints
□ Error budget burn rate alert (fast burn 1h, slow burn 6h)
□ p99 latency alert (>2× baseline)
□ Dependency health alerts (database, cache, external APIs)
□ Each alert has a runbook
□ Each alert has an owner
□ No alerts without runbooks
□ No alerts with known false positives

DASHBOARDS:
□ RED metrics dashboard (rate, errors, duration)
□ Deployments annotated
□ Dependencies visible
□ Link to runbooks in dashboard description
```

---

## Part 26: Companion Resources

**Primary:**
- *Observability Engineering* by Charity Majors, Liz Fong-Jones, George Miranda (Ch1-8) — the definitive modern observability book. Read Ch4 on "The Core Analysis Loop" especially.
- *Site Reliability Engineering* by Google (O'Reilly, free online) — Ch4 (SLOs), Ch5 (eliminating toil), Ch10 (practical alerting from time series data)

**Secondary:**
- *The Art of Monitoring* by James Turnbull — practical Prometheus and Grafana guide
- *Systems Performance* by Brendan Gregg — the USE method in depth; focused on Linux performance
- Honeycomb blog (honeycomb.io/blog) — excellent posts on high-cardinality observability

**Tools to explore hands-on:**
- `github.com/open-telemetry/opentelemetry-demo` — full microservices demo with OTel instrumentation; explore it in Jaeger and Prometheus
- `github.com/prometheus/prometheus` — read the TSDB internals to understand cardinality
- Grafana Play (play.grafana.org) — explore pre-built dashboards without installing anything

---

## Memorable Quotes

> *"The goal of observability is not to collect all the data. It's to be able to ask any question about system behavior without knowing in advance what question you'll need to ask."*
> — Charity Majors

> *"An alert that fires and is ignored is worse than no alert. It trains engineers that alerts don't mean anything."*
> — Rob Ewaschuk, Google SRE

> *"You are not Google. You are not Netflix. But you will have incidents. Observability is not a luxury — it is how you stay sane on-call."*
> — Kelsey Hightower

> *"Average latency is a lie. p99 is the truth. Always display percentiles."*
> — common wisdom, every distributed systems team

> *"The three pillars of observability are metrics, logs, and traces. The fourth pillar — the one people forget — is a culture that actually looks at them."*

---

## Final Checklist

Before you consider a service "observable":

```
□ I can tell if the service is healthy in < 30 seconds from its dashboard
□ When the service fails, an alert fires within 5 minutes
□ Every alert has an owner and a runbook
□ I can find all logs for a specific failing request using request_id
□ I can see which service caused a latency spike using distributed traces
□ I know the SLO for this service and how much error budget remains
□ My metrics don't use high-cardinality labels
□ My logs don't contain passwords, tokens, or PII
□ My on-call teammates can debug incidents in this service without asking me
```

The last item is the true test: observability is not about the tools you installed. It is about whether another engineer can understand your system's behavior from its outputs alone.

---

## Part 27: Observability Maturity Model

Use this to self-assess your team's current state and identify the next improvement.

```
LEVEL 0 — FLYING BLIND
  Symptoms: No dashboards. No alerts. Learn about incidents from users.
  Next step: Add RED metrics to the most critical user-facing service.

LEVEL 1 — BASIC MONITORING
  Symptoms: Some dashboards. Threshold-based alerts. High false positive rate.
            "I check the dashboard when I think there's a problem."
  Next step: Migrate top 3 alerts to SLO burn rate. Add request_id to logs.

LEVEL 2 — REACTIVE OBSERVABILITY
  Symptoms: RED metrics for all services. Structured logging. SLO alerts.
            Engineers can find root cause within 30 minutes for known failure modes.
  Next step: Add distributed tracing. Build runbooks for all P1 alerts.

LEVEL 3 — PROACTIVE OBSERVABILITY
  Symptoms: Distributed tracing across all services. Runbooks complete.
            MTTD < 5 minutes. MTTR < 30 minutes for known failure modes.
            Alert quarterly reviews in place.
  Next step: Add exemplars. Build standard instrumentation library.
             Define SLOs for all user-facing features.

LEVEL 4 — SYSTEMATIC OBSERVABILITY
  Symptoms: Shared instrumentation library. SLOs defined org-wide.
            Error budget policies enforced. Business metrics tracked.
            MTTR for novel failures < 60 minutes (traces + logs reach root cause).
            Observability is a design review requirement.
  Next step: High-cardinality event storage (Honeycomb). Continuous SLO review.

LEVEL 5 — OBSERVABILITY CULTURE
  Symptoms: Every engineer thinks about SLIs before writing code.
            Observability is part of "done" criteria for every feature.
            MTTD / MTTR measured and improving quarter-over-quarter.
            New engineers can debug production incidents solo within 30 days.
```

Most teams starting their observability journey are at Level 1-2. The jump from Level 2 to Level 3 (adding distributed tracing + runbooks) is the highest ROI investment in MTTR reduction.

---

## Part 28: Incident Postmortem and the Observability Feedback Loop

Observability improves only if you close the feedback loop: after every incident, ask "what should we instrument differently?"

**The 5-minute postmortem format (for P1/P2 incidents):**

```markdown
## Incident: [name] — [date]

**Duration:** 14:23 to 15:07 (44 minutes)

**Impact:** Payment checkout unavailable for ~12% of users in us-east-1

**Detection:** Alert fired at 14:25 (2 minutes after incident start) ✅
**Resolution:** 15:07 — rollback of deployment abc123

**Root cause:** New code path in order-service called inventory-service
synchronously. Inventory-service DB was undergoing maintenance (connection
refused). No circuit breaker — all checkout requests hung waiting for
inventory, exhausting connection pool in order-service.

**What went well:**
- Alert fired quickly (2 minutes MTTD)
- Dashboard showed which endpoint was affected within 3 minutes
- Trace showed the hanging span in order-service

**What could improve observability:**
- [ ] Add circuit breaker to inventory-service calls
- [ ] Add alert: inventory-service connection refused count > 10/minute
- [ ] Dashboard: add inventory-service health to checkout dashboard
- [ ] Add synthetic monitor: checkout golden path test every 60 seconds

**Owner:** [name] — due: [date + 1 week]
```

The "What could improve observability" section is the feedback loop. Every incident teaches you something you weren't measuring or alerting on. Over 6-12 months, this systematic improvement is how teams get from Level 2 to Level 4.

**The three questions to ask at every postmortem:**

1. **Detection**: How did we find out? Alert (good) or user report (bad). If user report: what metric or alert would have caught it earlier?
2. **Investigation**: What was the hardest part of finding root cause? Which trace, log query, or dashboard view would have made it faster?
3. **Prevention**: What should we add to catch this category of failure earlier next time?

Answering these three questions, and then actually implementing the follow-ups, is the highest-leverage observability activity a team can do. It costs almost nothing (30 minutes per incident) and compounds over time: after 20 incidents, you've systematically hardened your observability against your most common failure modes.

**Closing principle: observability is a product, not a project.**

Most teams approach observability as a one-time project: "we need to add Prometheus." They spend two weeks setting it up, declare it done, and never revisit it. Six months later, 40% of the alerts are firing as false positives, dashboards are stale, and the team is back to debugging by instinct.

The teams with excellent observability treat it as a product with an owner, a roadmap, and a quarterly review. Someone is responsible for: alert quality, dashboard relevance, SLO accuracy, and MTTD/MTTR metrics. It is maintained, iterated, and improved — not installed and forgotten.

At L5, your job is to build and maintain observability for your service.
At L6, your job is to build the system that makes every service observable by default.

**The one question that summarizes this chapter:**

> *If you were paged right now about a production incident in the service you're thinking of, how long would it take you to find the root cause?*

If the answer is "less than 30 minutes" — you have good observability.
If the answer is "depends what it is" — you have level 2 observability.
If the answer is "probably need to add some logging first" — start here.

---

*Pairs with [Chapter 117: Capacity Planning](Chapter_117_Capacity_Planning.md) (resource provisioning informed by metrics) and [Chapter 110: Code Review as a Discipline](Chapter_110_Code_Review_as_a_Discipline.md) (observability requirements in review checklists). Next: [Chapter 122: Performance Profiling](Chapter_122_Performance_Profiling.md).*

