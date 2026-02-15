# Cascading Failure: How One Failure Spreads

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Dominoes. One falls. Hits the next. Hits the next. One small push. Entire chain collapses. In software: the database slows down. The API server waits. Thread pool fills up. Other requests queue. Timeouts. Retries flood the database even more. Database crashes. API crashes. Load balancer marks servers dead. Entire system down. One slow component. Took everything with it. That's cascading failure.

---

## The Story

Service A depends on Service B. Service B depends on the database. Normal day: requests flow. Fast. Then the database gets slow. Disk I/O issue. Queries take 10 seconds instead of 10 milliseconds. Service B's threads are all blocked. Waiting on the database. No threads left for new requests. Service B starts timing out. Service A calls Service B. Service A's threads block. Waiting on B. Service A's thread pool fills. Now *everything* that touches A—including requests that don't need B—gets stuck. Because A has no free threads. The cascade spreads. Up the chain. Outward. One slow database. Dozens of services. Total outage.

Why does it spread? No timeouts—threads wait forever. Unlimited retries—more load on the failing component. No circuit breakers—keep sending to a dead service. No bulkheads—one slow dependency exhausts all threads. Tight coupling—everyone waits on everyone. The cascade feeds itself. Gets worse. Until everything is down.

---

## Another Way to See It

Think of a highway. One car breaks down. Stops. Cars behind stop. More cars. Traffic jam spreads. Miles. One failure. Thousands stuck. No one moving. Cascading gridlock.

Or a power grid. One transformer overloads. Fails. Load shifts to neighbors. They overload. Fail. Blackout spreads. City by city. One component. Regional outage. Cascading power failure. Same pattern. Same physics.

---

## Connecting to Software

**Prevention:**

**Timeouts.** Don't wait forever. If the database doesn't respond in 2 seconds, fail. Free the thread. Move on. Timeouts stop the block.

**Circuit breakers.** Too many failures? Stop calling. Open the circuit. Fail fast. No more hammering the struggling service. It gets a chance to recover.

**Bulkheads.** Isolate resources. Limit threads per dependency. If DB is slow, only 10 threads block. The other 90 handle other requests. Isolation contains the blast.

**Load shedding.** When overloaded, drop excess requests. 503. "Try later." Better than slow death for everyone.

**Retries with backoff.** Don't retry immediately. Don't flood. Exponential backoff. Jitter. Give the failing service room to breathe.

---

## Let's Walk Through the Diagram

```
    THE CASCADE

    [DB] slow (disk I/O)
         │
         │  Queries block. 10s each.
         ▼
    [Service B] threads exhausted (all waiting on DB)
         │
         │  B times out. A waits on B.
         ▼
    [Service A] threads exhausted (all waiting on B)
         │
         │  A times out. API waits on A.
         ▼
    [API] threads exhausted
         │
         ▼
    [Load Balancer] marks API dead
         │
         ▼
    TOTAL OUTAGE 💥

    One slow DB → entire system down
```

Each layer blocks. Each layer exhausts. The failure climbs. Prevention at each layer stops it.

---

## Real-World Examples (2-3)

**Example 1: AWS S3 outage 2017.** S3 had issues in one partition. Services that depended on S3 started failing. Those failures caused more load. Retries. Cascading. Many AWS services went down—not because they were broken, but because S3 was. One dependency. Wide outage.

**Example 2: GitHub 2022.** Database primary had issues. Replicas lagged. Services that depended on the database started failing. Cascading. Multiple systems affected. Took hours to recover. One component. Chain reaction.

**Example 3: Netflix Chaos Engineering.** They *simulate* cascading failures. Kill a service. Watch what happens. Find the propagation paths. Add circuit breakers. Timeouts. Bulkheads. Before real failure finds them. They learned: cascades are predictable. And preventable.

---

## Let's Think Together

**One microservice out of 20 is slow. How can it bring down all 19 others?**

If every service calls that one. Or calls something that calls it. And none have timeouts. All block. Thread pools fill. The slow service becomes a sink. All threads drain into it. No threads left for anything else. The "slow" spreads through shared resources—threads, connections. Solution: isolate. Timeout. Circuit break. Bulkhead. Don't let one slow dependency monopolize shared resources.

---

## What Could Go Wrong? (Mini Disaster Story)

A startup had 50 microservices. All shared one thread pool for outgoing HTTP calls. One external API—used by 5 services—went slow. 30-second responses. Those 5 services held all threads. The other 45 services needed threads for their own calls. None left. Entire platform stalled. One external API. 50 services down. Lesson: shared resource pools are cascade amplifiers. Isolate. Per-dependency limits. Bulkheads. Or one slow dependency kills everything.

---

## Surprising Truth / Fun Fact

The term "cascading failure" comes from power systems. The 2003 Northeast blackout—50 million people without power—started with a single power line hitting a tree in Ohio. One line. Cascading failures across the grid. Software is not unique. Complex interconnected systems fail this way. The fix: isolation, circuit breakers, and design that limits blast radius. Same principles. Different domains.

---

## Quick Recap (5 bullets)

- **Cascading failure** = one failure triggers others. Chain reaction. Total outage.
- **Cause:** tight coupling, no timeouts, unlimited retries, no circuit breakers, no bulkheads.
- **Prevention:** timeouts, circuit breakers, bulkheads, load shedding, retries with backoff.
- **Bulkheads** = isolate resources. One slow dependency can't exhaust all threads.
- **Design** = assume any component can fail. Limit blast radius.

---

## One-Liner to Remember

**One slow service can take down everything—if you let it. Timeouts, circuit breakers, and bulkheads stop the cascade.**

---

## Next Video

Next: **Timeouts**—why set them, and what value? The simple setting that prevents most cascades. Stay tuned.
