# Microservices: What and When to Split

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

From Swiss Army knife to professional tool belt. Each tool is separate. Hammer. Screwdriver. Measuring tape. Specialized. If the hammer breaks, you replace just the hammer. If the measuring tape is inadequate, you upgrade just that. In microservices, each service does one thing. Separate code. Separate deployment. Separate scaling. But you carry a heavy tool belt. More complexity. More coordination. When do you need it?

---

## The Story

Microservices = many small services. Each owns a bounded part of the domain. Auth service. Order service. Inventory service. Payment service. They talk over the network—HTTP, gRPC, or messages. Each has its own database, or at least its own schema. Deploy independently. Scale independently. Team A owns auth. Team B owns orders. They don't step on each other's toes.

The benefit: autonomy. Team B ships order changes without waiting for Team A. Scale orders to 100 instances while auth stays at 3. Replace the payment service without touching the rest. Technology choice: orders in Java, auth in Go. Polyglot. Each team optimizes for its domain.

The cost: complexity. Network calls instead of function calls. Latency. Failure modes. Service A is down—what does B do? Distributed tracing. Service discovery. API versioning. Deploying "one feature" might mean deploying 5 services. You need DevOps. You need observability. The tool belt is heavy.

When to split? When the monolith hurts. Multiple teams, constant merge conflicts. One part needs 100x the scale. Different release cycles—auth changes monthly, orders change daily. Different SLAs. Those are signals. Not "we want to look modern."

**Database per service:** Each service owns its data. Order service has order DB. Inventory has inventory DB. No shared database. Why? Loose coupling. Team A can't run a query that joins orders and users if they're in different services. Forces clean APIs. But: distributed transactions get hard. Saga pattern. Eventual consistency. Trade-offs. Design for them.

**Operational overhead:** Every service needs deployment, monitoring, logging, alerting. 50 services = 50 dashboards, 50 runbooks, 50 on-call rotations. Or shared platform. Kubernetes, service mesh, centralized logging. The platform team becomes critical. Microservices shift complexity from application code to operations. Invest in platform.

---

## Another Way to See It

Imagine an orchestra. Monolith = one person playing all instruments. Possible but hard. Microservices = each musician plays one instrument. Violin section, brass section, percussion. Specialized. They follow the conductor (orchestration) and listen to each other (events). Beautiful music. But coordination is complex. Tuning. Timing. One wrong note affects the whole. Microservices are like that—powerful when orchestrated well, chaotic when not.

---

## Connecting to Software

In practice, a microservice has a clear boundary. It owns its data. Other services don't touch its database directly. They call its API. Or they get events from it. Loose coupling. High cohesion within the service.

Service discovery: how does order service find auth service? Registry (Consul, etcd) or DNS. Load balancing across instances. Retries, timeouts, circuit breakers. All the distributed systems headaches. You need them. Or use a service mesh to handle it.

---

## Let's Walk Through the Diagram

```
    MONOLITH                          MICROSERVICES

    ┌──────────────────┐              ┌─────┐     ┌─────┐     ┌─────┐
    │                  │              │Auth │────►│Order│────►│Pay  │
    │  One Big App     │              └──┬──┘     └──┬──┘     └──┬──┘
    │  Auth+Order+Pay  │                 │           │           │
    │                  │              ┌──▼──┐     ┌──▼──┐     ┌──▼──┐
    │  One DB          │              │ DB  │     │ DB  │     │ DB  │
    └──────────────────┘              └─────┘     └─────┘     └─────┘

    Deploy all or nothing.            Deploy independently. Scale independently.
```

---

## Real-World Examples (2-3)

**Example 1: Netflix.** Hundreds of microservices. Recommendation, playback, billing, search. Each team owns services. They deploy thousands of times per day. Chaos engineering. They evolved from a monolith because scale and team size demanded it. Not every company is Netflix. But the pattern works at that scale.

**Example 2: Uber.** Trip service, driver service, payment service, map service. Different scaling. Map service gets hammered during rush hour. Trip service is more steady. They scale independently. Different teams. Different release cycles.

**Example 3: Amazon.** Two-pizza teams. Each team owns services. "You build it, you run it." Microservices enabled that. Team autonomy. Fast iteration. The famous "from monolith to microservices" story. They did it when the monolith became the bottleneck.

---

## Let's Think Together

**How small should a microservice be?**

Not "as small as possible." Small enough to be owned by one team. Small enough to deploy independently. Big enough to have a clear domain. "User service" might be one service. "User-first-name service" is too small—artificial split. "User + Auth + Profile" might be one or two. Bounded context from Domain-Driven Design helps. One service per bounded context is a good heuristic.

**Do you need a message queue for microservices?**

Not always. REST or gRPC is fine for request-response. But for async, fire-and-forget, or event-driven flows, a queue or event bus helps. Order placed → notify inventory, send email, update analytics. Publish event. Subscribers react. Loose coupling. So: sync for "I need an answer now," async for "do this eventually."

---

## What Could Go Wrong? (Mini Disaster Story)

A company splits into 50 microservices. "Orders" is 5 services: create-order, validate-order, fulfill-order, charge-order, ship-order. One checkout touches all 5. Latency adds up. One fails, whole flow fails. Debugging a bug: which service? Trace across 5. They realize they over-split. They merge create, validate, fulfill into one "order" service. Charge and ship stay separate (different domains). Lesson: split by domain, not by function. Don't make a single use case depend on 10 services.

---

## Surprising Truth / Fun Fact

Amazon's CTO Werner Vogels says: "Start with a monolith. Modularize it. Extract services when you have a clear boundary and a clear owner." Even Amazon didn't start microservices-first. They evolved. The best microservice architectures often come from a well-structured monolith that was split at the right seams.

---

## Quick Recap (5 bullets)

- **Microservices** = many small services, each owning a bounded domain, deployed and scaled independently.
- Benefits: team autonomy, independent scaling, technology flexibility. Costs: network complexity, observability, deployment coordination.
- Split when the monolith hurts: multiple teams, different scaling needs, different release cycles.
- Each service owns its data. Others interact via API or events. Loose coupling.
- Don't over-split. One service per bounded context. Avoid "nanoservices" that add more overhead than value.

---

## One-Liner to Remember

Microservices = professional tool belt. Each tool does one job, replaceable and scalable. But the belt is heavy. Wear it when you need it—not when a Swiss Army knife would do.

---

## Next Video

Next up: **Event-Driven Architecture**—when the bell rings and everyone reacts. No central coordinator. Just events and independent actions.
