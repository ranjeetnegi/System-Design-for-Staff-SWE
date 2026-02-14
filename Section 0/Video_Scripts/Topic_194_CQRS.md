# CQRS: Command Query Responsibility Segregation

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

A restaurant with two counters. Counter 1, command: "I want to place an order." Writes. Counter 2, query: "What's on the menu? What's the status of my order?" Reads. Different counters. Different staff. Different optimization. CQRS = separate the write model (commands) from the read model (queries). Optimize each independently. Writes go to one store. Reads from another—possibly denormalized for speed. Powerful when read and write needs diverge.

---

## The Story

CQRS: Command Query Responsibility Segregation. Split your model. **Commands** change state. "Place order." "Update address." "Cancel subscription." They write. **Queries** return data. "What's my order status?" "List my subscriptions." They read. Simple CQRS: same database, but different code paths. Command handlers. Query handlers. Clean separation in code. No shared mutable model causing confusion.

Advanced CQRS: different stores. Write to a transactional store. Reads from a denormalized, optimized read store. Maybe a replica. Maybe a different schema altogether. "Orders" table for writes (normalized). "OrderListByCustomer" view for reads (denormalized, indexed for "my orders" query). Write model optimized for consistency. Read model optimized for query patterns. They can drift—eventually consistent. Sync via events: write happens, event published, read model updated.

When to use? When read and write patterns differ a lot. Millions of reads, few writes—cache aggressively, denormalize for reads. Complex writes, simple reads—keep write model clean, read model can be a dumb mirror. Or: different scaling. Writes need strong consistency. Reads can be eventually consistent, spread across replicas. CQRS lets you have both.

---

## Another Way to See It

Think of a library. Command: "Check out this book." Librarian updates the system. Query: "Where is this book?" Catalog, search index. Different systems. Checkout affects catalog eventually. But the catalog might be optimized for search—keywords, categories. The checkout system for transactions. Separated. Each does its job.

Or a hospital. Admissions (command): "Patient arrived, assign room." Admissions desk writes. Info desk (query): "Where is patient X? What's their room?" Different system. Maybe a display board. Optimized for "look up by name." Admissions optimizes for "process intake." CQRS.

---

## Connecting to Software

In practice: command side receives "PlaceOrder". Validates. Writes to order table. Publishes "OrderPlaced" event. Read side: subscribes to "OrderPlaced". Updates "OrdersByCustomer" table, or search index, or cache. Query "GetMyOrders(customerId)" reads from that. Fast. Denormalized. Maybe different DB. Eventual consistency: write succeeds, read model updates within seconds. For many use cases, fine.

Simple CQRS (same DB): just separate handlers. CommandHandler and QueryHandler. No events. Same database. Cleaner code. Less infrastructure. Start there. Add separate read store when needed.

**CQRS + Event Sourcing:** Common combo. Write = append event. Read = query projection built from events. Event store is source of truth. Projections are derived. Add new read model? Replay events, build it. No schema change on write side. Maximum flexibility. Used in high-scale, event-heavy domains. Complex but powerful.

**Sync lag:** Read model can lag behind writes. "I just placed an order. Where is it?" If read model hasn't updated yet, show "processing" or read from write store for that specific case. Design UX for eventual consistency. Most reads can be stale. Critical reads might need strong consistency. Know the difference.

---

## Let's Walk Through the Diagram

```
    CQRS: SEPARATE WRITE AND READ

    ┌─────────────┐                    ┌─────────────┐
    │  Command    │                    │   Query     │
    │ "Place Order"│                   │ "My Orders?"│
    └──────┬──────┘                    └──────┬──────┘
           │                                   │
           ▼                                   ▼
    ┌─────────────┐    Event     ┌─────────────────────┐
    │ Write Store │ ───────────► │ Read Store          │
    │ (transacts) │   OrderPlaced│ (denormalized,      │
    │             │              │  optimized for      │
    └─────────────┘              │  "list my orders")   │
                                 └─────────────────────┘

    Write: consistency, validation        Read: speed, scale, flexibility
```

---

## Real-World Examples (2-3)

**Example 1: E-commerce order history.** Write: place order, update status. Strong consistency. Read: "Show my past 50 orders with product names, prices, dates." Denormalized view. Orders + line items + product names in one table. Optimized for "customer view." Write model stays normalized. Read model is a projection. CQRS.

**Example 2: Social feed.** Write: post, like, follow. Simple. Read: "Feed for user X" = complex. Merge from 1000 followed users, rank, filter. Expensive. Read model: pre-computed feed per user. Updated async when someone posts. Write is quick. Read is a materialized view. CQRS in spirit.

**Example 3: Betting/gaming.** Place bet (command). High consistency. "What are the live odds?" (query). Read from cached, denormalized view. Updated by events. Millions of reads. Few writes. CQRS lets you scale reads independently.

---

## Let's Think Together

**Do you always need separate read and write stores?**

No. CQRS can be logical only. Same database. Separate command and query handlers. Cleaner code. Easier to reason about. Add separate read store when: read volume is huge, read schema differs from write schema, or you need to scale reads independently. Start simple. Evolve.

**What about consistency? User writes, immediately reads. Read model not updated yet?**

Eventual consistency. For "place order, show confirmation"—you might need immediate read from write store. Or: command returns the created data. Don't require read model for that. For "list my orders"—eventual is fine. A second later, it appears. Design the UX. Some actions need strong consistency. Others don't. CQRS gives you the choice.

---

## What Could Go Wrong? (Mini Disaster Story)

A company implements CQRS. Write to PostgreSQL. Read from Elasticsearch. Sync via events. Bug: event consumer crashes. Restart. Misses some events. Read model is stale. Users see old data. "I cancelled that. Why does it still show?" They add idempotency, checkpointing, replay. Fix the consumer. Rebuild read model from event log. Lesson: eventual consistency needs robust sync. Consumer must not lose events. Replay capability. Monitoring for lag.

---

## Surprising Truth / Fun Fact

CQRS was coined by Greg Young around 2010. It extends CQS (Command Query Separation) from Bertrand Meyer—every method is either a command (changes state, returns void) or a query (returns data, no side effects). CQRS takes it to the model level. Separate models. Different scalability. Different optimization. One idea, big impact for complex systems.

---

## Quick Recap (5 bullets)

- **CQRS** = separate write model (commands) from read model (queries). Optimize each for its purpose.
- Commands change state. Queries return data. Different code paths. Different stores (optional).
- Read store can be denormalized, cached, scaled independently. Eventually consistent with writes.
- Use when: read and write patterns diverge, high read volume, different scaling needs.
- Start with logical separation (same DB). Add separate read store when benefits justify complexity.

---

## One-Liner to Remember

CQRS = two counters. One for orders (writes). One for menu and status (reads). Optimize each. Don't mix.

---

## Next Video

That wraps up this set! You've covered data residency, failover, monoliths, microservices, event-driven architecture, serverless, API gateways, service mesh, WebSockets, polling strategies, SSE, pagination, event sourcing, and CQRS. Solid foundation for system design at scale.
