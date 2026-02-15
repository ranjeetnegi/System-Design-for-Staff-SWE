# API Gateway: Backpressure and Failover

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

A highway on-ramp. Traffic light. When the highway is congested, the ramp light turns RED. Cars wait on the ramp instead of merging into a parking lot. When the highway clears, the light turns GREEN. Cars flow. The ramp light is backpressure. It stops new traffic when the system can't handle it. An API gateway does the same. Backend overwhelmed? Stop sending traffic. Don't make it worse. Let's see how.

---

## The Story

Your API gateway receives 100,000 requests per second. It forwards them to backend services. One service—the payment service—starts struggling. Database slow. CPU maxed. Latency climbs. 100ms → 500ms → 2 seconds. The gateway keeps forwarding. More and more requests pile up. Queues grow. The payment service drowns. Cascading failure. The gateway had no idea. It was "just doing its job." Backpressure changes that. When the backend signals "I'm overloaded," the gateway listens. Stops sending. Returns 503. Retry-After header. "Come back in 30 seconds." Protects the backend. Protects the system. One overwhelmed service doesn't take down everything.

---

## Another Way to See It

Imagine a water pipe. Water flows in. Flows out. If the exit is blocked, pressure builds. Eventually the pipe bursts. Backpressure: when the exit slows, the entrance closes. A valve. No burst. The gateway is the valve. It controls flow into the backend. When the backend says "I'm full," the gateway closes the valve. Requests get 503. Better than overflowing the backend. Better than timeouts. Controlled failure. Graceful degradation. The user gets a clear message. "Try again later." Not "connection reset" or "timeout after 30 seconds." Backpressure is the difference between chaos and controlled failure.

---

## Connecting to Software

**Backpressure signals.** How does the gateway know the backend is struggling? HTTP 503. Backend returns it when overloaded. Gateway sees it. "This backend is unhealthy." Increased latency. Requests taking 5 seconds when normal is 100ms. Circuit breaker tracks failure rate. Opens when too many failures. Queue depth. If the gateway queues requests to the backend, and the queue hits 10,000, that's a signal. Backpressure. Stop accepting. Health checks. Active probing. Backend returns 200? Healthy. 503? Unhealthy. Passive: observe real traffic. Active: send probes. Both matter.

**Gateway response.** When backpressure triggers: return 503 to the client. Include Retry-After header. "Retry in 30 seconds." Don't make the client guess. Circuit breaker: stop sending to this backend for 30 seconds. Let it recover. Fallback: serve cached response if available. "Last known good." Stale is better than nothing for some use cases. Load shedding: reject low-priority requests. Keep high-priority. Payment requests yes. Marketing analytics no. Prioritize. Or: route to a secondary region. Failover. If primary is down, try secondary. Backpressure + failover = resilience.

**Failover.** Primary backend in us-east. Secondary in us-west. Gateway health checks both. Primary returns 503? Switch to secondary. Automatic. Or manual. Depends on your ops style. But the key: don't keep hammering a dead backend. Fail fast. Fail over. User might get slightly higher latency (cross-region). Better than no response. Design the failover path. Test it. Chaos engineering. Kill primary. Verify traffic flows to secondary. Hope you never need it. Know it works when you do.

---

## Let's Walk Through the Diagram

```
API GATEWAY BACKPRESSURE
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   CLIENTS                    GATEWAY              BACKEND        │
│      │                          │                    │           │
│      │  request                 │                    │           │
│      │────────────────────────► │  forward           │           │
│      │                          │──────────────────► │           │
│      │                          │                    │           │
│      │                          │  ◄─── 503 (overload)           │
│      │                          │                    │           │
│      │  ◄─── 503 Retry-After    │  CIRCUIT BREAKER   │           │
│      │      (backpressure)      │  OPEN: stop forward            │
│      │                          │                    │           │
│      │                          │  After 30s: try    │           │
│      │                          │  again (half-open) │           │
│                                                                  │
│   FAILOVER: Primary 503? Route to secondary region.              │
│   FALLBACK: Cache? Serve stale. Shed load. Prioritize.           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: Client sends request. Gateway forwards to backend. Backend returns 503. Overloaded. Gateway's circuit breaker opens. Stops forwarding. Returns 503 to client with Retry-After. Protects the backend. After 30 seconds, circuit half-opens. One trial request. Success? Close circuit. Traffic flows again. Fail? Keep circuit open. The diagram shows the flow. Backpressure is the gateway protecting the backend. Not passive. Active. Listening. Responding. The gateway is the system's immune system. Backpressure is how it fights infection.

---

## Real-World Examples (2-3)

**Netflix Hystrix.** Circuit breaker library. Open source. (Now in maintenance.) Inspired a generation. When downstream fails, stop sending. Let it recover. The pattern: fail fast, protect upstream. Netflix ran this at massive scale. Proven.

**Envoy.** Proxy. Circuit breaking built in. Outlier detection. When upstream returns 503, mark unhealthy. Eject from load balancing. Retry with backoff. Production-grade. Used by Lyft, Stripe, countless others. Envoy does backpressure right.

**AWS API Gateway.** Integrates with Lambda, HTTP backends. Throttling. When backend is slow, gateway can queue or reject. Configurable. The cloud providers have learned. Backpressure is table stakes. Build it in.

---

## Let's Think Together

**"Backend returns 503 for 10 seconds. Should the gateway retry? Queue? Return error immediately?"**

Retry: maybe. If 503 is transient, retry with backoff. 1 retry. 2 retries. But if the backend is truly overloaded, retrying adds more load. Makes it worse. So: retry for transient errors. Don't retry for overload. How do you know? Some backends return 503 with Retry-After. "I'm overloaded. Come back in 30 seconds." Gateway: don't retry immediately. Honor Retry-After. Queue: dangerous. If you queue 10,000 requests and the backend is down, you're holding 10,000 requests in memory. When backend recovers, it gets a burst. Might overwhelm again. Queues can hide the problem. Or make it worse. Return immediately: safe. Client gets 503. Retry-After. Client retries later. Clear. Predictable. Recommendation: return immediately for sustained 503. Don't queue unbounded. Retry once or twice for transient 503. Use circuit breaker. When it opens, fail fast. Don't pile on.

---

## What Could Go Wrong? (Mini Disaster Story)

A gateway. No circuit breaker. Backend starts returning 503. Gateway keeps forwarding. "Maybe the next one will work." 1000 requests per second. All failing. Gateway holds connections. Waits for timeouts. 30 seconds each. Connection pool fills. Gateway runs out of connections. Can't handle new requests. Even for healthy backends. Cascading failure. Gateway is down. Not because of the backend. Because the gateway didn't protect itself. Didn't fail fast. Postmortem: "We need circuit breakers." Obvious in hindsight. In the moment, the gateway was "being helpful" by retrying. Helpful killed it. Lesson: fail fast. Protect the gateway. Protect the system. Retry has limits. Circuit breakers are non-negotiable.

---

## Surprising Truth / Fun Fact

The circuit breaker pattern comes from electrical engineering. A circuit breaker in your house: when current exceeds a threshold, it trips. Stops the flow. Prevents fire. Software circuit breakers do the same. When failure rate exceeds a threshold, "trip." Stop sending traffic. Prevent cascading failure. Michael Nygard wrote about it in "Release It!" in 2007. The book is a classic. Circuit breakers, bulkheads, timeouts. Patterns for resilience. Software borrowed from hardware. The best ideas cross domains.

---

## Quick Recap (5 bullets)

- **Backpressure:** When backend is overloaded, gateway stops sending. Protects the system.
- **Signals:** HTTP 503, high latency, circuit breaker, queue depth. Gateway detects. Acts.
- **Response:** Return 503 with Retry-After. Circuit breaker. Fallback. Load shedding.
- **Failover:** Primary down? Route to secondary region. Health checks. Automatic or manual.
- **Don't queue unbounded:** Queues hide overload. Can make it worse. Fail fast. Honor Retry-After.

---

## One-Liner to Remember

**Backpressure is the gateway's way of saying "the highway is full—wait on the ramp" instead of merging into a disaster.**

---

## Next Video

Next: search systems, sharding, and how to query across billions of documents.
