# Bulkheads: Isolating Failure

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

A ship. The hull is divided into compartments by steel walls. Bulkheads. If one compartment floods, the water stays there. Other compartments stay dry. The ship doesn't sink. Without bulkheads? One hole, water everywhere, ship goes down. The Titanic had bulkheads. They bought time. In software, bulkheads do the same thing: isolate failure so one bad component doesn't take down the whole system.

## The Story

The problem: **shared resources**. All your microservices share one thread pool. One connection pool. One piece of the system. Service A calls a slow external API. It holds 100 threads waiting. Service B needs threads to handle user requests. But there are none left. Service A exhausted them. Service B is blocked. Your whole API is down. One slow dependency killed everything.

**Bulkhead pattern**: give each service—or each dependency—its **own** resources. Service A gets 50 threads. Service B gets 50 threads. Service C gets 50 threads. If Service A is slow and uses all 50, Service B and C still have their 50. They're unaffected. The failure is contained. Isolated.

The name comes from ships. Bulkheads = walls between sections. In software, the "walls" are resource limits. Thread pools. Connection pools. Process boundaries.

## Another Way to See It

Like an apartment building. One pipe bursts in 3A. Without bulkheads, water floods the whole building. With bulkheads—fire doors, separate plumbing per unit—only 3A is affected. The rest of the building stays dry. Isolation saves the majority. In software, the "water" is resource exhaustion. Threads, connections, memory. One leaking service floods the shared pool. Bulkheads contain the leak. The rest of the system keeps running. You get partial failure, not total outage.

## Connecting to Software

Types of bulkheads:

- **Thread pool isolation**: Each downstream dependency gets its own thread pool. Call to Payment service? Pool A. Call to Inventory? Pool B. One blocks, the other doesn't.
- **Connection pool isolation**: Separate DB connection pools per service or per tenant. One tenant's query storm doesn't exhaust connections for others.
- **Process isolation**: Separate containers or processes. Service A runs in its own pod. It crashes? Other pods keep running.
- **Regional isolation**: US-East has an outage. EU-West is separate. Different failure domains. Bulkhead at the region level.

You see this in Netflix Hystrix (older, now in maintenance mode) and Resilience4j: bulkhead = bounded thread pool per dependency. Same idea everywhere. Even connection pool limits are a form of bulkhead: "This service can use at most 20 DB connections." If it tries to use 21, it blocks or fails. That protects the database from one runaway service exhausting all connections. Bulkheads are about quotas. Hard limits. "You get this much. No more."

## Let's Walk Through the Diagram

```
  WITHOUT BULKHEADS:
    API Gateway
         |
    [Shared Thread Pool: 100 threads]
         |
    +-----+-----+-----+-----+-----+
    |  A  |  B  |  C  |  D  |  E  |  (5 services)
    +-----+-----+-----+-----+-----+
    Service A slow → uses all 100 threads
    B, C, D, E starve. Everything blocks.

  WITH BULKHEADS:
    API Gateway
         |
    +-----+-----+-----+-----+-----+
    | 20 | 20 | 20 | 20 | 20 |  (20 threads each)
    +-----+-----+-----+-----+-----+
    Service A slow → uses only its 20
    B, C, D, E still have their 20. Isolated.
```

## Real-World Examples (2-3)

- **Netflix**: Each microservice call (e.g., to Recommendations) gets a bounded thread pool. One slow service doesn't block the whole UI.
- **Kubernetes**: Each pod is a process bulkhead. Pod A OOMs? Pods B and C run.
- **Multi-tenant SaaS**: Tenant A gets a connection pool. Tenant B gets another. Tenant A's bad query doesn't exhaust Tenant B's connections.
- **API Gateway**: 5 backend services. Each has a connection limit. One backend is down/slow? Others still get requests. Without bulkheads, one bad backend could exhaust the gateway's entire connection pool. With bulkheads, the bad backend hits its limit, gateway returns 503 for that service only. Other routes keep working. Graceful degradation.
- **Database connection pools**: Tenant A gets 10 connections. Tenant B gets 10. Tenant A's runaway query holds all 10. Tenant B is unaffected. Multi-tenant isolation through bulkheads. Same DB, separate pools. One bad tenant doesn't kill the rest.

## Let's Think Together

**Your API gateway talks to 5 backend services. One service is slow. Without bulkheads, what happens? With bulkheads?**

Without: All requests share the same connection pool or thread pool. Slow service holds connections/threads. Others wait. Eventually the gateway runs out. Timeouts. Cascade failure. User-facing APIs that don't even call the slow service start failing—they're blocked waiting for a thread. With bulkheads: Each service has a limited slice. Slow service uses its slice. Others have theirs. Gateway can still serve requests that don't need the slow service. You get graceful degradation. Users of the healthy services keep working. Users of the slow service see delays or errors. Partial failure, not total outage. That's the goal.

## What Could Go Wrong? (Mini Disaster Story)

You add bulkheads. Each service gets 10 threads. Great. But your traffic spikes. Each service needs 50 threads at peak. With 10, you get queuing. Requests wait. Latency spikes. You've isolated failure but also capped capacity. Bulkheads protect you from one bad actor. They can also limit good actors if sized wrong. Size your pools to actual need. Monitor. Adjust. Bulkheads are a tuning knob, not a set-and-forget.

## Surprising Truth / Fun Fact

The Titanic's bulkheads didn't go high enough. Water overflowed from one compartment into the next. The bulkheads were there, but the design was flawed. Same in software: your bulkheads must be complete. If Service A can still exhaust a shared resource you forgot about—like file descriptors, memory, or a global cache—the bulkhead is incomplete. One leak and the whole ship goes down. Think holistically. Isolate everything that can be exhausted. Monitor. Alert when a pool is near capacity. That's when you're one slow dependency away from outage.

---

## Quick Recap (5 bullets)

- Bulkheads = resource isolation so one failing component doesn't kill the whole system; compartments on a ship
- Shared resources (thread pools, connection pools) let one slow service block everyone
- Solution: separate pools per service/dependency—bounded, isolated
- Types: thread pool, connection pool, process, regional
- Size correctly—too small and you throttle good traffic; monitor pool usage, alert before exhaustion

## One-Liner to Remember

*One bad neighbor shouldn't ruin the building. Bulkheads keep them apart.*

Isolate resource pools per service, per tenant, or per dependency. When one exhausts its pool, others keep running. Graceful degradation over cascade failure.

---

## Next Video

Up next: Chaos engineering—why you break things on purpose. See you there.
