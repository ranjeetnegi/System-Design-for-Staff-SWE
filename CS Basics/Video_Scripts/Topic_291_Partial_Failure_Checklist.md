# Designing for Partial Failure (Checklist)

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

A chain of 10 dominoes. One falls, all fall. In distributed systems: Service A calls B, B calls C, C calls D. D is slow. C waits. B waits. A waits. Everything is stuck because ONE service is slow. The whole system grinds to a halt. Designing for partial failure means: when D is slow, A, B, and C continue working. Maybe with degraded functionality. Maybe with cached data. But they DON'T all fall down. One failure shouldn't cascade. Here's your checklist to make sure it doesn't.

---

## The Story

Imagine a restaurant. Kitchen, waitstaff, dishwasher, manager. The dishwasher breaks. Water everywhere. In a badly designed restaurant: the whole place closes. No dishes, no service, no nothing. In a well-designed restaurant: they use paper plates. Or they call a backup dishwasher. Or they delay dessert. The core service—feeding customers—continues. The dishwasher failure is isolated. That's partial failure design. One component fails. The system adapts. Degrades gracefully. Doesn't die.

In software, your order service calls the user service. User service calls the recommendation service. Recommendation service calls a third-party API that's timing out. Without protection, your order service waits. Then times out. Then the user gets an error. For an order. Because recommendations were slow. That's cascading failure. The recommendation service is non-critical for checkout. But you made it critical by not handling its failure. Staff engineers design so that when the non-critical path fails, the critical path still works.

---

## Another Way to See It

Think of a power grid. One neighborhood has an outage. Well-designed grid: the rest of the city stays on. Isolated failure. Badly designed grid: one failure triggers a cascade. Blackout. Same principle. You want isolation. Bulkheads. When one compartment floods, the ship doesn't sink. When one service fails, the system doesn't collapse.

---

## Connecting to Software

**The philosophy.** Assume EVERY dependency WILL fail. Not might. Will. Design as if failure is normal. Because it is. Networks fail. Databases fail. Third-party APIs fail. Disks fail. The question is: when they fail, does your system fail? Or does it degrade gracefully?

**The checklist.** Eight things every service needs:

**(1) Timeouts on every external call.** Never wait forever. 30 seconds for a database? Maybe. 30 seconds for an API? No. Set timeouts. 5 seconds. 10 seconds. If the dependency doesn't respond, fail fast. Return an error. Don't block.

**(2) Circuit breakers.** If a dependency fails 5 times in a row, stop calling it. Open the circuit. Fail immediately. Don't keep hammering a dead service. Give it time to recover. After 30 seconds, try again. If it works, close the circuit. Circuit breakers prevent cascade. You stop sending traffic to a failing dependency.

**(3) Fallback responses.** When a dependency fails, what do you return? Cached data. Default value. Degraded response. "Recommendations temporarily unavailable." Not "Internal Server Error." The user gets something. Maybe not ideal. But something.

**(4) Bulkheads.** Isolate failures. Don't let one slow dependency consume all your threads. If the payment service is slow, limit how many threads can wait on it. Other requests continue. Order service can still serve "view order" even if "process payment" is stuck.

**(5) Retry with backoff and jitter.** Transient failures happen. Retry. But: exponential backoff. Don't retry immediately 100 times. Wait 1s, 2s, 4s. Add jitter so you don't thundering herd. Retry on idempotent operations. Never retry on non-idempotent without careful design.

**(6) Health checks and load shedding.** Know when you're overloaded. Reject new requests before you collapse. Return 503. "Try again later." Better than accepting everything and crashing. Load shedding is saying no to protect the core.

**(7) Graceful degradation over total failure.** If the recommendation service is down, show "Popular items" instead of "Recommended for you." If search is down, show the category list. Degrade. Don't die.

**(8) Async where possible.** Queue instead of synchronous call. User submits order. You queue it. Return "Order received." Process in background. If payment service is slow, the queue waits. The user isn't waiting. Decouple with queues. Sync creates fragile chains.

---

## Let's Walk Through the Diagram

```
PARTIAL FAILURE DEFENSE LAYERS
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   [User Request]                                                 │
│        │                                                         │
│        ▼                                                         │
│   [Service A] ──┬── Timeout: 5s                                  │
│        │        ├── Circuit Breaker: open after 5 failures       │
│        │        └── Fallback: cached / default if B fails        │
│        │                                                         │
│        ▼                                                         │
│   [Service B] ──┬── Bulkhead: max 10 threads waiting on C        │
│        │        ├── Retry: 3x with backoff + jitter              │
│        │        └── Async: queue to C instead of sync?           │
│        │                                                         │
│        ▼                                                         │
│   [Service C] ──► Health check: if unhealthy, don't call         │
│        │         Load shed: reject if overloaded                │
│        │                                                         │
│   RESULT: C fails → B gets timeout → A gets fallback             │
│   User sees degraded response. System survives.                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: Each layer is a defense. Timeout stops infinite wait. Circuit breaker stops hammering. Fallback gives the user something. Bulkhead isolates. Retry handles transient. Health check avoids known-bad. The diagram shows the armor. One failure doesn't punch through. Staff engineers layer these. They don't rely on one.

---

## Real-World Examples (2-3)

**Netflix.** Their whole architecture assumes dependencies fail. When a recommendation service is down, they show trending. When a CDN is slow, they degrade quality. Circuit breakers everywhere. They have a library—Hystrix—built for this. They don't expect anything to be up. They design for everything to be down. That's resilience.

**Uber.** Checkout depends on: user service, inventory (driver availability), payment, pricing. If payment is down, they don't fail the whole flow. They show "Payment temporarily unavailable. Try again in a few minutes." The ride request might be queued. They degrade. They don't cascade.

**Stripe.** Payment processing. Critical path. But they still use timeouts, circuit breakers, fallbacks. If a fraud check service is slow, they might proceed with a default. Or queue for async processing. They never let one dependency block the entire payment flow. Partial failure handling is table stakes at scale.

---

## Let's Think Together

**"Checkout page calls: User Service, Inventory Service, Payment Service, Shipping Service. Payment is down. What do you show the user?"**

Don't fail the whole page. Show: "Your cart is saved. Payment is temporarily unavailable. We'll notify you when it's back." Let them see their cart. Let them see shipping options. Gray out or hide the "Pay" button. Or: show a "Retry" option. Queue the order for later processing. The key: the user knows what happened. They're not stuck on a blank error page. They can come back. You've degraded gracefully. Staff engineers think: "What's the minimum viable experience when X fails?" Design for that. Not for the happy path only.

---

## What Could Go Wrong? (Mini Disaster Story)

An e-commerce site. Black Friday. Huge traffic. Their recommendation service—a third-party API—starts slowing down. 10 second response times. No timeout. Every request to the homepage waits for recommendations. Thread pool fills. Server runs out of threads. Can't serve any request. Not even "Add to cart." Not even "View product." The whole site goes down. Because of recommendations. A non-critical feature took down the critical path. No circuit breaker. No fallback. No bulkhead. One slow dependency. Total failure. The fix: add timeouts (5 seconds), circuit breaker (open after 3 failures), fallback (show "Popular" instead of "Recommended"). Next Black Friday: recommendation service slow again. Homepage still loads. Shows popular items. Degraded but alive. That's the difference between designing for partial failure and hoping nothing breaks.

---

## Surprising Truth / Fun Fact

Amazon's internal services are designed with a principle: "Assume the network is hostile." They don't trust that a response will arrive. They don't trust that a dependency is up. Every call has a timeout. Every dependency has a fallback. When you design like the network will betray you, you're ready when it does. The best partial failure design comes from paranoia. Assume failure. Design for it. When it happens, you're not surprised.

---

## Quick Recap (5 bullets)

- **Assume every dependency WILL fail.** Design for it. Failure is normal.
- **Checklist:** Timeouts, circuit breakers, fallbacks, bulkheads, retry with backoff, health checks, load shedding, async.
- **Graceful degradation:** Show cached, default, or simplified response. Don't fail completely.
- **One failure shouldn't cascade.** Isolate. Bulkheads. Circuit breakers.
- **Queue instead of sync** where possible. Decouples. User doesn't wait for slow dependencies.

---

## One-Liner to Remember

**Partial failure design: assume every dependency will fail; add timeouts, circuit breakers, fallbacks—so one slow service doesn't take down everything.**

---

## Next Video

Next: organizational scaling. When 5 people become 500. APIs as contracts. Conway's Law. How teams and systems grow together.
