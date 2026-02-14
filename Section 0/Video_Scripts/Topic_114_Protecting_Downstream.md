# Protecting Downstream Services from Spikes

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Picture a river. Heavy rains upstream. Water rushes toward a village below. Without a dam? The village floods. Houses drown. Lives lost. With a dam? The water is controlled. Gates open. Gates close. Only what the village can handle flows through. The dam protects downstream. Your API gateway is that dam. A traffic spike—flash sale, viral tweet, Black Friday—is the heavy rain. Without protection, your downstream databases and services drown. Let me show you how to build the dam.

---

## The Story

Imagine the cascade. Frontend sends requests. Hits your API. The API calls service A. Service A calls service B. Service B hits the database. Each layer depends on the next. One chain. One flow.

Now picture this. Your database can handle 1,000 queries per second. That's its limit. No more. But your API gets 10,000 requests per second. A celebrity tweets your product. Or it's Black Friday. Traffic explodes.

What happens? The API forwards all 10,000. Service A forwards them. Service B forwards them. The database gets 10,000. It tries. Connection pool exhausted. CPU maxed. Timeouts. Crashes. And here's the cruel part: when the database dies, service B fails. When service B fails, service A fails. When service A fails, the API fails. Everything upstream collapses because one downstream component drowned. One weak link. Total failure.

The fix? Protect downstream. Let through only what each layer can handle. Rate limiting at the API. Circuit breakers when a service is overloaded. Queues to buffer spikes. Backpressure to signal "slow down." The dam at each layer. Control the flow. Or everything drowns.

---

## Another Way to See It

Think of a highway exit. Without a traffic light, thousands of cars pour onto a small street. Gridlock. Accidents. The street can't handle it. A traffic light—metering—lets only a few cars through at a time. The highway waits. The street stays functional.

Or a restaurant kitchen. One chef can cook 20 orders per hour. Unlimited orders at the door? Chaos. Burned food. Angry customers. Collapse. The fix? A host at the door. "We're at capacity. Please wait." Or a waitlist. Orders flow in at a pace the kitchen can handle. Controlled admission. The chef stays effective. The system survives.

---

## Connecting to Software

**Rate limiting.** Cap requests at the entry point. Your API gateway says: "Max 1,000 requests per second." Excess gets 429 Too Many Requests. Downstream never sees the spike. First line of defense. Simple. Critical.

**Circuit breakers.** When downstream fails or slows down, stop sending. Open the circuit. Fail fast. Retry later. Prevents hammering a struggling service. Like calling a friend who doesn't answer. You stop after a few tries. You don't dial 100 times.

**Load shedding.** When overloaded, drop non-critical requests. Keep payment processing. Drop "trending" recommendations. Prioritize. Survive. Triage in the ER. Who gets care first?

**Queue-based buffering.** Spike arrives? Put requests in a queue. Workers process at a steady rate. Downstream sees smooth load. No sudden burst. The queue absorbs. Downstream breathes.

**Backpressure.** Downstream signals upstream: "I'm full. Stop." Producer slows. No overflow. No crash. The valve closes. Flow matches capacity.

---

## Let's Walk Through the Diagram

```
    TRAFFIC SPIKE (10K QPS)                    PROTECTED FLOW

    ┌─────────────┐                             ┌─────────────┐
    │  Traffic    │ 10K/sec                     │  Traffic    │ 10K/sec
    │  Spike      │                             │  Spike      │
    └──────┬──────┘                             └──────┬──────┘
           │                                          │
           │  ALL forwarded                            │  RATE LIMITER
           ▼                                          │  (The Dam)
    ┌─────────────┐                             ┌──────▼──────┐
    │  API       │                             │  Max 1K/sec │
    └──────┬──────┘                             └──────┬──────┘
           │                                          │
           │  10K → Service A                          │  1K → Service A
           ▼                                          ▼
    ┌─────────────┐                             ┌─────────────┐
    │  Service A  │                             │  Service A  │
    └──────┬──────┘                             └──────┬──────┘
           │                                          │
           │  10K → Service B                          │  1K → Service B
           ▼                                          ▼
    ┌─────────────┐                             ┌─────────────┐
    │  DB (1K cap)│  💥 CRASH                   │  DB (1K cap)│  ✓ OK
    └─────────────┘                             └─────────────┘
```

Left side: No dam. 10K flows to a 1K-capacity database. Crash. Right side: Rate limiter acts as the dam. Only 1K passes through. Downstream stays within capacity. The dam saves the village. The rate limiter saves the system.

---

## Real-World Examples (2-3)

**Example 1: Stripe.** Payment processing. Black Friday traffic spikes. Millions of transactions. Their API rate limits per key. Downstream payment services never see more than they can handle. Orders might queue. Users might wait. But payments don't fail. Reliability first.

**Example 2: Netflix.** New show drops. Millions hit play at once. Without protection, encoding pipelines and CDN layers would collapse. They use queues, aggressive caching, and progressive loading. Downstream stays stable. You hit play. It works.

**Example 3: Amazon Prime Day.** 50x normal traffic. API gateways throttle. Some requests get "try again later." Product catalog and inventory services stay up. Checkout flows. Sacrifice some latency. Save the system. Slow and up beats fast and down.

---

## Let's Think Together

Black Friday. 50x normal traffic hits your API. Your API handles it—you scaled it. But your payment service can handle only 2x. What do you do?

Consider your options. (1) Rate limit at API—cap requests so payment service gets max 2x. Some users wait. Some see "try again." (2) Queue checkout—acknowledge order immediately, process payment async, notify when done. User gets confirmation. Payment happens in background. (3) Circuit breaker—if payment service fails, stop sending, show "Pay later" option. Don't hammer a dead service. (4) Load shed—disable non-critical features. Recommendations? Wishlist? Drop them. Free capacity for checkout.

No single right answer. Trade-offs: user experience vs. system survival. The key: **protect the bottleneck first.** Know where your limits are. Build the dam there.

---

## What Could Go Wrong? (Mini Disaster Story)

A retail app launches a flash sale. 9 AM sharp. "First 1,000 customers get 90% off." The marketing team did their job. Social media exploded. They scaled their API. They scaled their app servers. They forgot the inventory service.

The inventory service talks to a legacy database. Max 500 queries per second. No one checked. At 9:01 AM, 50,000 users hit "Add to Cart" at once. The inventory service gets hammered. It times out. The app retries. More requests. More retries. Cascade. Inventory service dies. Cart service dies. Checkout dies. Everything dies. Sale cancelled. Refunds. Angry customers. Lost revenue. One downstream service. One missing dam. One oversight. Total disaster.

The fix? Rate limit or queue at the API. Let through 500 to inventory. Queue the rest. Or degrade gracefully: "Limited stock. Try again in 5 minutes." Protect downstream. Always. Audit your chain. Find the weakest link. Build the dam there.

---

## Surprising Truth / Fun Fact

Amazon Prime Day taught the industry a hard lesson. Early years had outages. Traffic spikes crushed systems. Now? They pre-throttle. They know their bottlenecks. They intentionally slow traffic at the gate so every downstream service stays within capacity. Sometimes "slow" is the feature. Slow and up beats fast and down. Every time.

---

## Quick Recap (5 bullets)

- **Downstream protection** = don't overwhelm services that can't handle the load.
- **Techniques**: rate limiting, circuit breakers, load shedding, queues, backpressure.
- **Cascade failure**: one overloaded component takes everything upstream with it.
- **The dam analogy**: control flow at each layer; let through only what downstream can handle.
- **Protect the bottleneck first**—often the database or a legacy service.

---

## One-Liner to Remember

**Your downstream services are the village. Your API gateway is the dam. Control the flow, or everything drowns.**

---

## Next Video

Next: **What is system design?** The blueprint before the bricks. Interview vs. real world. Stay tuned.
