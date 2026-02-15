# Circuit Breaker: Stop Cascading Failures

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Your house has an electrical circuit breaker. Too much current flows—short circuit, overload. Instead of letting the wires melt and the house burn down, the breaker *trips*. Power cuts to that circuit. The house is protected. You fix the problem. Reset the breaker. In software, a service is failing. Thousands of requests flood in. Each one waits. Times out. Retries. The failing service drowns. The callers drown. Everything cascades. The circuit breaker? It trips. Stops the flow. Fails fast. Saves the system.

---

## The Story

A payment service goes down. Your checkout flow calls it. User clicks "Pay." Your app sends the request. Waits. And waits. 30 seconds. Timeout. User retries. Another 30 seconds. Your app retries with backoff. More requests. More threads blocked. Your thread pool fills. Now *all* requests—not just checkout—are stuck. Product pages. Search. Everything waits on threads. Your app is down. Not because of the payment service. Because you couldn't *stop* calling it.

The circuit breaker fixes this. It watches. Normal operation: requests flow. Success. Success. Success. Then—failure. Failure. Failure. Too many. Threshold reached. The circuit **opens**. No more requests. Callers get an immediate error. "Payment service unavailable." No waiting. No blocking. Threads freed. Your app stays responsive. The payment service gets zero traffic. Time to recover. After a cooldown, the circuit goes **half-open**. Try a few test requests. Success? Close the circuit. Back to normal. Failure? Open again. Wait longer.

---

## Another Way to See It

Think of a crowded nightclub. Fire marshal limit: 200 people. 500 trying to get in. Bouncer sees chaos inside. Fights. Overload. Instead of letting more in, he closes the door. "No entry." Protects those inside. Lets the crowd disperse. When things calm, he lets a few in to test. OK? Resume. Still chaos? Stay closed. The bouncer is the circuit breaker.

Or a doctor's office. Flu outbreak. Too many patients. Overwhelmed. Receptionist stops taking appointments. "Come back next week." Protects staff. Protects patients already waiting. Doesn't add to the disaster. Fail fast at the door.

---

## Connecting to Software

**Three states:**

**CLOSED:** Normal. Requests flow through. Failures counted. Success resets the counter.

**OPEN:** Too many failures (e.g., 5 failures in 10 seconds, or 50% error rate). Circuit trips. All requests immediately fail. No calls to the downstream service. Fast-fail. Protects both caller and callee.

**HALF-OPEN:** After a timeout (e.g., 30 seconds), circuit allows a few test requests. If they succeed, close the circuit. If any fail, open again. Gives the service a chance to prove it recovered.

**Flow:** CLOSED → failures exceed threshold → OPEN → wait timeout → HALF-OPEN → test requests → success? → CLOSED. Failure? → OPEN again.

**Fallbacks:** When circuit is open, return something. Cached data. Default value. "Service temporarily unavailable." Don't just fail. Give the caller something to work with. Graceful degradation.

---

## Let's Walk Through the Diagram

```
    WITHOUT CIRCUIT BREAKER              WITH CIRCUIT BREAKER

    [App] ──► [Payment] (failing)        [App] ──► [Circuit Breaker]
    [App] ──► [Payment] (failing)                 |
    [App] ──► [Payment] (failing)                 |  CLOSED: flow through
    [App] ──► [Payment] (failing)                 |  OPEN: fail fast, no calls
    ...                                           v
    Threads blocked. Cascade.            [Payment] gets ZERO traffic when OPEN
         💥                                  App stays responsive ✓
```

Left: endless calls to failing service. Threads exhaust. App dies. Right: circuit opens. Fail fast. App survives. Payment recovers.

---

## Real-World Examples (2-3)

**Example 1: Netflix Hystrix.** Netflix built Hystrix for exactly this. Their API calls dozens of microservices. One slow or failing service was taking down the whole app. Hystrix added circuit breakers. Service down? Circuit opens. Show cached content. Show fallback. "Recommendations temporarily unavailable." The rest of Netflix works.

**Example 2: Stripe.** Payment processing. When a bank or card network has issues, Stripe doesn't hammer it. Circuit breaker opens. Returns "payment provider temporarily unavailable." Merchants get fast failure. Can show "try later." Users don't wait 30 seconds per attempt.

**Example 3: Kubernetes.** Services communicate. One pod is unhealthy. Kube-proxy and service mesh can implement circuit-breaking behavior. Unhealthy pod gets no traffic. Others take the load. System stabilizes.

---

## Let's Think Together

**Payment service is down. Circuit breaker opens. User clicks "Pay." What do you show them?**

Options: (1) "Payment temporarily unavailable. Please try again in a few minutes." Clear. Honest. (2) Cached "Pay later" option—save cart, email when payment is back. (3) Alternative payment methods if you have multiple providers—circuit breaker per provider. (4) Queue the payment—"we'll process when ready"—and notify. Best: fast, clear error + retry option. Don't pretend. Don't block. Fail gracefully.

---

## What Could Go Wrong? (Mini Disaster Story)

A team added circuit breakers. Configured threshold: 3 failures in 10 seconds. But their payment service had a quirk: first request after cold start always timed out. Every deployment. Circuit opened immediately. Every user got "payment unavailable" for 30 seconds after every deploy. They thought payment was broken. It wasn't. Lesson: tune your thresholds. Consider cold start. Consider partial failures. Test circuit breakers in staging. A circuit breaker misconfigured can cause more outages than it prevents.

---

## Surprising Truth / Fun Fact

Michael Nygard popularized the circuit breaker pattern in his book "Release It!" in 2007. He was building systems at a time when cascading failures were common. The pattern comes from electrical engineering—where it's been saving buildings since the 1800s. Software just caught up. Sometimes the best ideas are 200 years old.

---

## Quick Recap (5 bullets)

- **Circuit breaker** = stop calling a failing service. Fail fast instead of waiting.
- **Three states:** CLOSED (normal), OPEN (block all calls), HALF-OPEN (test recovery).
- **Prevents cascading failure** = one failing service doesn't exhaust your threads.
- **Protects the failing service** = no more hammering. Time to recover.
- **Provide fallbacks** = cached data, "try later," alternative providers.

---

## One-Liner to Remember

**When a service keeps failing, stop calling it. The circuit breaker trips. You fail fast. The system survives.**

---

## Next Video

Next: **Availability vs Reliability vs Durability**—three words that sound the same but mean completely different things. Stay tuned.
