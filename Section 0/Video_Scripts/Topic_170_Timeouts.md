# Timeouts: Why Set Them and What Value?

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You call a pizza shop. Ring. Ring. Ring. Five minutes of ringing. Nobody picks up. You wasted five minutes. If you'd hung up after 30 seconds and called another shop, you'd have pizza by now. A timeout is simple: "I'll wait THIS long. If no response, I move on." Without timeouts, your system waits forever for responses from dead services. Forever. Until everything is stuck.

---

## The Story

Your service calls a downstream API. The downstream is slow. Or dead. Or the network is broken. Without a timeout, your request waits. And waits. Thread blocked. Connection held. Resource consumed. One request. Ten. A hundred. Thread pool exhausts. No threads for new requests. Your service is down. Not because of the downstream. Because you had no timeout. You waited forever. For nothing.

Set a timeout. 500 milliseconds. 2 seconds. 5 seconds. Something. After that—fail. Free the thread. Return error. Move on. The user gets "service unavailable" in 2 seconds instead of your entire system dying in 10 minutes.

But get the value wrong. Too short: legitimate slow responses get cut off. False failures. Unnecessary retries. User sees errors when a retry would have succeeded. Too long: slow failures block resources. Cascade starts. Threads pile up. Same death. Slower. The art is in the number.

---

## Another Way to See It

Think of waiting for a friend at a coffee shop. No deadline: you wait forever. Friend never comes. You're stuck. Timeout: "I'll wait 15 minutes." After 15, you leave. You get on with your day. Timeout gives you your life back.

Or a restaurant. Kitchen is slow. No timeout: you sit for 3 hours. Timeout: "If food doesn't arrive in 45 minutes, we leave." You might miss a late meal. But you don't waste the whole evening. Trade-off. Timeouts are always trade-offs.

---

## Connecting to Software

**Rules of thumb:** Base timeout on p99 latency of the downstream service, plus buffer. If p99 is 200ms, timeout might be 500ms to 1 second. For database calls: 1–5 seconds. For external APIs: 5–30 seconds. Depends on the service. Measure. Tune.

**Connect timeout vs. read timeout:** Two different timeouts. Connect: how long to establish the TCP connection. If the server is unreachable, fail fast. 1–5 seconds. Read: how long to wait for the response *after* connected. Server slow? Read timeout. Set both. Missing read timeout = infinite wait after connect. Common bug.

**Without timeout:** Thread blocked forever. Resources exhausted. System crashes. **Too short:** Legitimate slow responses fail. False failures. **Too long:** Slow failures block resources. Cascade. Choose based on your p99. And monitor. Adjust.

**Per-call vs. global.** You might have a global default: 5 seconds for all HTTP calls. But one dependency is legitimately slow—ML inference, report generation. Override per client. Or per endpoint. Don't let one slow path force short timeouts everywhere. Granularity matters. Match timeout to the operation.

---

## Let's Walk Through the Diagram

```
    NO TIMEOUT                          WITH TIMEOUT (2s)

    [Client] ──► [Server] (dead)        [Client] ──► [Server] (dead)
         │            ✗                      │            ✗
         │  waits...                           │  waits 2s
         │  waits...                           │  fails
         │  waits...                           │  returns error
         │  forever                            │  thread FREE
         │                                     │
         ▼                                     ▼
    Thread stuck. Pool exhausts.         User gets error. System survives.
         💥                                  ✓
```

Left: infinite wait. Death. Right: bounded wait. Failure contained. Resources freed.

---

## Real-World Examples (2-3)

**Example 1: Stripe.** Payment APIs have strict SLAs. They document expected latency. Their clients set timeouts accordingly. Too short: legitimate payments fail. Too long: checkout hangs when Stripe has issues. Stripe publishes p99. Clients tune. Timeouts are part of the contract.

**Example 2: Databases.** Connection timeout: 5 seconds. Query timeout: 30 seconds. Why different? Connecting is fast or fail. Queries can be slow—complex joins, large scans. But 30 seconds is enough. Beyond that, something is wrong. Don't wait. Kill the query. Free the connection.

**Example 3: Kubernetes.** Probes have timeouts. Liveness: 10 seconds. Readiness: 5 seconds. If the app doesn't respond in time, Kubernetes assumes failure. Restarts. Removes from load balancer. Timeouts drive critical decisions.

---

## Let's Think Together

**Your API calls a slow ML service for recommendations. Normal: 500ms. Sometimes: 5 seconds. Timeout?**

Options: (1) 1 second—covers most requests. Some fail. Retry? (2) 5 seconds—covers all normal. But 5 seconds holds a thread. Under load, threads exhaust. (3) Async—don't block. Send request. Return quickly. Callback or polling for result. Best: match your user expectation. Can the user wait 5 seconds? If not, shorter timeout + fallback (cached recommendations). Or async. Don't default to "as long as it takes." That's a cascade waiting to happen.

---

## What Could Go Wrong? (Mini Disaster Story)

A team set a 30-second timeout on all external API calls. Seemed safe. One day, an external provider had issues. Every call took 29 seconds. Then failed. 29 seconds per request. 100 concurrent requests. 100 threads. All blocked 29 seconds. New requests queued. System slowed. More retries. More 29-second blocks. Cascade. Lesson: 30 seconds is a long time to hold a thread. Under load, "long" timeouts multiply. Consider: not just "what's the longest acceptable wait?" but "how many threads can we afford to block for that long?" Sometimes shorter timeout + faster failure is better. Fail fast. Retry. Don't slow-death.

---

## Surprising Truth / Fun Fact

Many production outages have been traced to missing timeouts. A 2012 GitHub outage: no timeout on a database call. Threads blocked. Cascade. Redis connection pool exhaustion at Stripe: similar. Timeouts seem trivial. A single number. But they're one of the most impactful settings in distributed systems. One line of config. Prevents cascades. Saves systems. Never leave them at default "infinite."

---

## Quick Recap (5 bullets)

- **Timeout** = maximum wait time. After that, fail. Free resources.
- **Without timeout** = thread blocked forever. Resources exhausted. Cascade.
- **Too short** = false failures. Too long = slow death. Tune to p99 + buffer.
- **Connect timeout** = time to establish connection. **Read timeout** = time to get response. Set both.
- **Rules of thumb:** DB 1–5s. External API 5–30s. Internal service: p99 + buffer.

---

## One-Liner to Remember

**Set a timeout on every call. Or your threads will wait forever. And take your system with them.**

---

## Next Video

Next: **Health Checks**—liveness vs readiness. Two monitors. Two different questions. Stay tuned.
