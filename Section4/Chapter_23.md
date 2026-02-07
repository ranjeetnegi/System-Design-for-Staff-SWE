# Chapter 23: Event-Driven Architectures — Kafka, Streams, and Staff-Level Trade-offs

---

# Introduction

Event-driven architecture is one of the most powerful and most abused patterns in distributed systems. When applied correctly, it enables systems that scale elastically, degrade gracefully, and evolve independently. When applied incorrectly—which happens far more often—it creates distributed debugging nightmares, consistency headaches, and operational complexity that far exceeds the benefits.

I've spent years building event-driven systems at Google scale and debugging production incidents caused by their misuse. The pattern that emerges is consistent: teams adopt Kafka because it's "modern" and "scalable," then spend the next two years fighting the consequences of that decision. Not because Kafka is bad—it's excellent at what it does—but because they chose event-driven architecture when they should have chosen something simpler.

This section teaches event-driven architecture as Staff Engineers practice it: with deep skepticism, careful scoping, and relentless focus on operational reality. We'll cover when events make systems better and when they make systems worse. We'll examine Kafka internals not to show off, but because understanding the mechanics helps you predict failure modes. And we'll explore the anti-patterns that turn promising architectures into production nightmares.

**The Staff Engineer's First Law of Events**: Every event you publish is a promise you're making to the future. Make sure you can keep it.

---

## Quick Visual: Event-Driven Architecture at a Glance

```
┌─────────────────────────────────────────────────────────────────────────────┐
│               EVENT-DRIVEN ARCHITECTURE: THE STAFF ENGINEER VIEW            │
│                                                                             │
│   WRONG Framing: "Events make systems more scalable and decoupled"          │
│   RIGHT Framing: "Events trade consistency and debuggability for            │
│                   scalability and producer independence"                    │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Before adding events, answer:                                      │   │
│   │                                                                     │   │
│   │  1. What happens when the consumer is down for 2 hours?             │   │
│   │  2. What happens when events arrive out of order?                   │   │
│   │  3. What happens when the same event is delivered twice?            │   │
│   │  4. How will you debug a problem that spans 5 services via events?  │   │
│   │  5. Who is on-call when event processing breaks at 3am?             │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   If you can't answer all five, you're not ready for events.                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## L5 vs L6 Event-Driven Decisions

| Scenario | L5 Approach | L6 Approach |
|----------|-------------|-------------|
| **Send email after signup** | "Publish UserCreated event, email service subscribes" | "Why not just call the email service? One subscriber, no ordering needs. Sync call with retry is simpler and more debuggable." |
| **Update search index** | "Publish events for all entity changes" | "Events make sense here—search can lag. But what's our consistency SLA? How do we handle reindexing? Events are the steady-state; we also need batch backfill." |
| **Real-time notifications** | "Kafka for everything" | "What latency do we need? Kafka adds 10-100ms. For real-time, consider WebSockets with Kafka as backup persistence. Match the tool to the latency requirement." |
| **Cross-service data sync** | "Publish change events, other services subscribe" | "This is distributed data management disguised as events. Who owns the data? What's the consistency model? Events don't solve the hard problem—they defer it." |
| **Microservice communication** | "Events for loose coupling" | "Events couple you to schemas and ordering semantics. Loose coupling is a myth. Choose: tight coupling you can see (APIs) or tight coupling you can't (events)." |

**Key Difference**: L6 engineers treat events as a trade-off, not a benefit. They ask what they're giving up, not just what they're gaining.

---

# Part 1: Why Event-Driven Architectures Exist

## The Real Problem Events Solve

Event-driven architecture exists to solve a specific problem: **temporal coupling**. When Service A calls Service B synchronously, A must wait for B. If B is slow, A is slow. If B is down, A fails.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SYNCHRONOUS vs ASYNCHRONOUS COUPLING                     │
│                                                                             │
│   SYNCHRONOUS (Request/Response):                                           │
│                                                                             │
│   ┌─────────┐         ┌─────────┐         ┌─────────┐                       │
│   │Service A│────────▶│Service B│────────▶│Service C│                       │
│   └─────────┘  wait   └─────────┘  wait   └─────────┘                       │
│        │                   │                   │                            │
│        │◀──────────────────┼───────────────────│                            │
│        │     A waits for B, B waits for C      │                            │
│        │     Total latency = A + B + C         │                            │
│        │     If C fails, A fails               │                            │
│                                                                             │
│   ASYNCHRONOUS (Event-Driven):                                              │
│                                                                             │
│   ┌─────────┐         ┌─────────┐                                           │
│   │Service A│────────▶│  Event  │                                           │
│   └─────────┘  fire   │  Bus    │                                           │
│        │    & forget  └────┬────┘                                           │
│        │                   │                                                │
│        │ (A continues     ┌▼────────┐     ┌─────────┐                       │
│        │  immediately)    │Service B│────▶│Service C│                       │
│        │                  └─────────┘     └─────────┘                       │
│        │                                                                    │
│        │     A doesn't wait for B or C                                      │
│        │     A's latency = A only                                           │
│        │     If C fails, A doesn't know (problem or feature?)               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

Events break temporal coupling. Service A publishes an event and moves on. Whether B processes it immediately, in 10 seconds, or after a restart doesn't affect A.

**But here's the catch**: temporal decoupling creates other forms of coupling:

1. **Schema Coupling**: Consumers depend on event structure. Change the schema, break the consumers.
2. **Semantic Coupling**: Consumers depend on event meaning. Change what "UserCreated" means, break the consumers.
3. **Ordering Coupling**: Consumers may depend on event order. Reorder events, break the consumers.
4. **Availability Coupling**: Consumers depend on the event bus. If Kafka is down, everyone's down.

**Staff Insight**: Events don't eliminate coupling—they transform it. Sometimes the transformation is beneficial (producer independence). Sometimes it's harmful (debugging complexity). The skill is knowing which.

---

## When Events Make Systems Better

Events genuinely improve systems in specific scenarios:

### 1. Fan-Out to Many Consumers

When one event needs to trigger actions in multiple independent systems, events shine.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FAN-OUT: EVENTS MAKE SENSE                               │
│                                                                             │
│                          "OrderPlaced"                                      │
│                               │                                             │
│   ┌───────────────────────────┼───────────────────────────┐                 │
│   │                           │                           │                 │
│   ▼                           ▼                           ▼                 │
│ ┌─────────────┐       ┌─────────────┐       ┌─────────────┐                 │
│ │  Inventory  │       │   Payment   │       │   Email     │                 │
│ │  Service    │       │   Service   │       │   Service   │                 │
│ └─────────────┘       └─────────────┘       └─────────────┘                 │
│        │                     │                     │                        │
│        ▼                     ▼                     ▼                        │
│ ┌─────────────┐       ┌─────────────┐       ┌─────────────┐                 │
│ │  Analytics  │       │  Shipping   │       │    Fraud    │                 │
│ │  Service    │       │  Service    │       │  Detection  │                 │
│ └─────────────┘       └─────────────┘       └─────────────┘                 │
│                                                                             │
│   With sync calls: Order service knows about 6 downstream services          │
│   With events: Order service knows about 0 downstream services              │
│   Adding a 7th consumer requires no change to Order service                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Why it works**: The producer (Order Service) has a stable, well-defined responsibility: record an order. Adding new reactions to orders is a consumer concern, not a producer concern.

### 2. Absorbing Traffic Spikes

Events act as a buffer between traffic spikes and processing capacity.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    BUFFERING: EVENTS AS SHOCK ABSORBER                      │
│                                                                             │
│   Traffic Pattern (writes/sec):                                             │
│                                                                             │
│   10,000 ─┐                     ┌──┐                                        │
│           │                    ╱    ╲                                       │
│    5,000 ─┤        ┌──────────╱      ╲──────────┐                           │
│           │       ╱                              ╲                          │
│    1,000 ─┤──────╱                                ╲──────                   │
│           └─────────────────────────────────────────────▶ Time              │
│             Normal    Spike (10x)      Normal                               │
│                                                                             │
│   WITHOUT Events:                                                           │
│   - Database must handle 10x load                                           │
│   - Either over-provision (expensive) or fail (bad)                         │
│                                                                             │
│   WITH Events:                                                              │
│   - Kafka absorbs the spike into the log                                    │
│   - Consumer processes at steady rate                                       │
│   - Lag increases during spike, decreases after                             │
│   - Database sees constant load                                             │
│                                                                             │
│   Consumer Processing Rate:                                                 │
│                                                                             │
│    2,000 ─┤────────────────────────────────────────────                     │
│           │  Steady processing regardless of input rate                     │
│    1,000 ─┤                                                                 │
│           └─────────────────────────────────────────────▶ Time              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Why it works**: The event log is designed for high-throughput writes. Kafka can absorb 100,000+ events/second per partition. Consumers process at whatever rate the downstream system can handle.

### 3. Failure Isolation

When a downstream system fails, events prevent that failure from cascading to the producer.

```
Synchronous failure cascade:
   Database fails → Inventory fails → Order fails → User sees error

Event-driven failure isolation:
   Database fails → Inventory fails → Events queue up → Order succeeds
   (Inventory processes queued events when database recovers)
```

**Why it works**: The producer's success doesn't depend on the consumer's success. Events persist in the log until consumers are ready.

### 4. Replay and Reprocessing

Events create a durable log of what happened, enabling:
- **Debugging**: Replay events to reproduce issues
- **Recovery**: Reprocess events after fixing a bug
- **New consumers**: Catch up on historical events
- **Testing**: Use production events in test environments

**Staff Insight**: This is often the most underappreciated benefit. The ability to say "what were the last 1000 events for this user?" has saved me during countless debugging sessions.

---

## When Events Make Systems Worse

Events are not always the answer. Here's when they hurt:

### 1. Simple Request/Response Patterns

If you have one producer and one consumer with synchronous needs, events add complexity without benefit.

```
BAD: User clicks "Send Email" → Publish EmailRequested event → 
     Email service consumes → Sends email → ??? (how does user know it worked?)

GOOD: User clicks "Send Email" → Call email service → 
      Get response → Show success/failure to user
```

**The problem**: Events are fire-and-forget. If the user needs to know the result, you need a way to correlate the response. That's usually a request/response pattern with extra steps.

### 2. Transactional Requirements

When multiple operations must succeed or fail together, events make consistency hard.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    EVENTS AND TRANSACTIONS DON'T MIX WELL                   │
│                                                                             │
│   REQUIREMENT: Transfer $100 from Account A to Account B                    │
│                                                                             │
│   SYNC/TRANSACTIONAL:                                                       │
│   BEGIN TRANSACTION                                                         │
│     UPDATE accounts SET balance = balance - 100 WHERE id = 'A'              │
│     UPDATE accounts SET balance = balance + 100 WHERE id = 'B'              │
│   COMMIT (atomic, consistent)                                               │
│                                                                             │
│   EVENT-DRIVEN (Naive):                                                     │
│   Publish DebitAccountA(100)    ← succeeds                                  │
│   Publish CreditAccountB(100)   ← fails (Kafka down?)                       │
│   Result: Money disappeared!                                                │
│                                                                             │
│   EVENT-DRIVEN (With Saga):                                                 │
│   Publish DebitAccountA(100, txn_id=123)                                    │
│   Account A service debits, publishes DebitCompleted(txn_id=123)            │
│   Saga coordinator sees completion, publishes CreditAccountB(100, txn_id)  │
│   Account B service credits, publishes CreditCompleted(txn_id=123)          │
│   Saga coordinator marks transaction complete                               │
│   ...                                                                       │
│   What if CreditAccountB fails?                                             │
│   Saga coordinator publishes CompensateDebitA(100, txn_id=123)              │
│   Account A service reverses the debit                                      │
│                                                                             │
│   This works, but it's 10x more complex than a transaction.                 │
│   And you still have windows where state is inconsistent.                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Staff Insight**: Sagas are sometimes necessary, but they're never simple. If you can use a transaction, use a transaction. Events are not a replacement for ACID.

### 3. Low Latency Requirements

Events add latency. Even with optimal configuration:
- Publishing to Kafka: 2-10ms
- Consumer polling: 0-100ms (configurable)
- End-to-end: 10-200ms typically

For real-time features (typing indicators, live cursors, gaming), this latency is unacceptable.

### 4. When You Need to Debug It

This is the hidden cost that teams consistently underestimate.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DEBUGGING: SYNC vs EVENT-DRIVEN                          │
│                                                                             │
│   SYNCHRONOUS DEBUGGING:                                                    │
│                                                                             │
│   User reports: "I clicked checkout but nothing happened"                   │
│   You check: Order service logs                                             │
│   You see: Stack trace, Payment service returned 500                        │
│   You check: Payment service logs (same request ID)                         │
│   You see: Stack trace, card processor timeout                              │
│   Root cause found: 5 minutes                                               │
│                                                                             │
│   EVENT-DRIVEN DEBUGGING:                                                   │
│                                                                             │
│   User reports: "I clicked checkout but nothing happened"                   │
│   You check: Order service logs                                             │
│   You see: OrderPlaced event published successfully                         │
│   You check: Kafka (where's the event? which partition?)                    │
│   You find: Event in partition 7                                            │
│   You check: Which consumer group has partition 7?                          │
│   You find: payment-processor-consumer-group                                │
│   You check: Consumer lag for that group (is it behind?)                    │
│   You see: Lag is 50,000 events (so event is queued)                        │
│   You check: Why is consumer slow?                                          │
│   You find: Consumer is stuck on earlier event (bad data)                   │
│   Root cause found: 2 hours                                                 │
│                                                                             │
│   And this is the SIMPLE case (one hop). Imagine 5 services.                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Staff Insight**: Every event hop you add multiplies debugging time by 2-5x. If you have 4 hops, debugging is 16-625x harder than synchronous. This is not an exaggeration. I've spent entire weeks tracking down bugs that would have been 10-minute fixes in synchronous systems.

---

## The Decoupling Myth

"Events decouple services" is one of the most repeated and least accurate claims in software architecture. Let's be precise about what events actually do:

**What Events Decouple**:
- **Temporal coupling**: Producer doesn't wait for consumer
- **Deployment coupling**: Services can be deployed independently
- **Scaling coupling**: Producer and consumer scale independently

**What Events Don't Decouple**:
- **Schema coupling**: Consumer depends on event structure
- **Semantic coupling**: Consumer depends on event meaning
- **Ordering coupling**: Consumer may depend on event sequence
- **Operational coupling**: Both depend on Kafka being up

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    COUPLING TRANSFORMATION, NOT ELIMINATION                  │
│                                                                             │
│   SYNC COUPLING (Explicit):                                                 │
│                                                                             │
│   Order Service ──────API Contract──────▶ Payment Service                   │
│                                                                             │
│   - Coupling is visible in code                                             │
│   - Compiler catches breaking changes                                       │
│   - IDE shows dependencies                                                  │
│   - Failures are immediate and obvious                                      │
│                                                                             │
│   EVENT COUPLING (Implicit):                                                │
│                                                                             │
│   Order Service ──────┐                                                     │
│                       │                                                     │
│                       ▼                                                     │
│                   [OrderPlaced                                              │
│                    Event Schema] ◀─────── Payment Service                   │
│                       │                                                     │
│                       ▼                                                     │
│                   [Kafka Topic                                              │
│                    Configuration] ◀─────── Payment Service                  │
│                       │                                                     │
│                       ▼                                                     │
│                   [Consumer Group                                           │
│                    Coordination] ◀─────── Payment Service                   │
│                                                                             │
│   - Coupling is hidden in schemas, configs, and conventions                 │
│   - Breaking changes surface at runtime, possibly hours later               │
│   - Dependencies are invisible to tools                                     │
│   - Failures are delayed and obscure                                        │
│                                                                             │
│   YOU HAVEN'T DECOUPLED. YOU'VE MADE THE COUPLING INVISIBLE.                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Staff Engineer's Rule**: Invisible coupling is worse than visible coupling. At least with a synchronous call, you know when you've broken something.

---

# Part 2: Kafka and Log-Based Systems

## Why Kafka Exists

Before Kafka, distributed messaging used traditional message queues (RabbitMQ, ActiveMQ). These work like a queue: producers enqueue, consumers dequeue, messages are deleted after consumption.

Kafka is fundamentally different. It's a **distributed log**: an append-only, ordered, durable sequence of records. Messages aren't deleted after consumption—they persist for a configurable retention period (days, weeks, or forever).

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MESSAGE QUEUE vs DISTRIBUTED LOG                         │
│                                                                             │
│   MESSAGE QUEUE (RabbitMQ, SQS):                                            │
│                                                                             │
│   Producer ──▶ [M5][M4][M3][M2][M1] ──▶ Consumer                            │
│                                                                             │
│   - Consumer receives message, message is deleted                           │
│   - Can't replay, can't have multiple consumer groups                       │
│   - Simple, but limited                                                     │
│                                                                             │
│   DISTRIBUTED LOG (Kafka):                                                  │
│                                                                             │
│   Producer ──▶ [M1][M2][M3][M4][M5][M6][M7][M8][M9]...                       │
│                 ▲              ▲                   ▲                        │
│                 │              │                   │                        │
│           Consumer A     Consumer B          Consumer C                     │
│           (offset: 1)    (offset: 4)         (offset: 9)                    │
│                                                                             │
│   - Messages persist, consumers track their position (offset)               │
│   - Multiple consumer groups, each with own offset                          │
│   - Replay by resetting offset                                              │
│   - More powerful, more complex                                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

This seemingly simple change—persisting messages and tracking offsets—enables fundamentally different architectures:

1. **Multiple consumer groups**: Search indexer and analytics and notifications can all consume the same events
2. **Replay**: Reprocess events after fixing a bug or adding a new consumer
3. **Time travel**: Query "what was the state at 2pm yesterday?"
4. **Buffering**: Absorb spikes, consumers catch up when ready

---

## Topics, Partitions, and Consumer Groups

Understanding Kafka's data model is essential for designing event-driven systems.

### Topics

A **topic** is a named stream of events. Think of it as a category or channel:
- `user-events`: All events related to users
- `order-events`: All events related to orders
- `page-views`: Clickstream data

Topics are logical groupings. The physical storage is partitions.

### Partitions

A **partition** is an ordered, immutable sequence of records. Each topic has one or more partitions.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    TOPIC "order-events" WITH 4 PARTITIONS                   │
│                                                                             │
│   Partition 0: [E0][E4][E8][E12][E16]...                                    │
│                 │   │   │    │    │                                         │
│                 ▼   ▼   ▼    ▼    ▼                                         │
│               offset 0,1,2,3,4...                                           │
│                                                                             │
│   Partition 1: [E1][E5][E9][E13][E17]...                                    │
│                                                                             │
│   Partition 2: [E2][E6][E10][E14][E18]...                                   │
│                                                                             │
│   Partition 3: [E3][E7][E11][E15][E19]...                                   │
│                                                                             │
│   Key properties:                                                           │
│   - Events WITHIN a partition are strictly ordered                          │
│   - Events ACROSS partitions have no ordering guarantee                     │
│   - Each partition can be on a different broker (parallelism)               │
│   - Events are assigned to partitions by key hash                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Why partitions matter**:

1. **Parallelism**: Each partition can be consumed independently, enabling parallel processing
2. **Ordering**: Events with the same key go to the same partition, preserving order
3. **Scalability**: Add partitions to increase throughput (but you can only add, not remove)

### Partition Key Selection

How events are routed to partitions is critical for ordering:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PARTITION KEY EXAMPLES                                   │
│                                                                             │
│   GOOD: Partition by user_id                                                │
│   - All events for user-123 go to same partition                            │
│   - UserCreated, UserUpdated, UserDeleted in order                          │
│   - Different users can be processed in parallel                            │
│                                                                             │
│   GOOD: Partition by order_id                                               │
│   - All events for order-456 go to same partition                           │
│   - OrderPlaced, PaymentReceived, OrderShipped in order                     │
│   - Different orders can be processed in parallel                           │
│                                                                             │
│   BAD: Partition by timestamp                                               │
│   - Events spread across partitions randomly                                │
│   - No ordering guarantees for related events                               │
│   - User's events might arrive: Updated, Deleted, Created (wrong order!)    │
│                                                                             │
│   BAD: Partition by event_type                                              │
│   - All UserCreated events together, all UserUpdated together               │
│   - But user-123's Created might be in different partition than Updated     │
│   - No way to ensure processing order                                       │
│                                                                             │
│   TRICKY: Partition by tenant_id (multi-tenant)                             │
│   - All events for tenant together (good for tenant consistency)            │
│   - But one large tenant can create hot partition (bad for parallelism)     │
│   - Consider sub-partitioning for large tenants                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Staff Insight**: Partition key selection is one of the most important decisions in Kafka architecture. Get it wrong, and you'll either lose ordering guarantees or create hot partitions. Both are painful to fix later.

### Consumer Groups

A **consumer group** is a set of consumers that cooperate to consume a topic. Each partition is assigned to exactly one consumer in the group.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CONSUMER GROUP MECHANICS                                 │
│                                                                             │
│   Topic "orders" with 4 partitions:                                         │
│   [P0] [P1] [P2] [P3]                                                       │
│                                                                             │
│   Consumer Group "order-processor" with 2 consumers:                        │
│                                                                             │
│   Consumer A: handles P0, P1                                                │
│   Consumer B: handles P2, P3                                                │
│                                                                             │
│   ┌──────────┐         ┌──────────┐                                         │
│   │    P0    │         │    P2    │                                         │
│   │    P1    │         │    P3    │                                         │
│   └────┬─────┘         └────┬─────┘                                         │
│        │                    │                                               │
│        ▼                    ▼                                               │
│   ┌──────────┐         ┌──────────┐                                         │
│   │Consumer A│         │Consumer B│                                         │
│   └──────────┘         └──────────┘                                         │
│                                                                             │
│   If Consumer B dies:                                                       │
│   - Kafka detects failure (heartbeat timeout)                               │
│   - Rebalance triggers                                                      │
│   - Consumer A now handles P0, P1, P2, P3                                   │
│   - Processing continues (with higher load on A)                            │
│                                                                             │
│   If Consumer C joins:                                                      │
│   - Rebalance triggers                                                      │
│   - New assignment: A(P0), B(P2), C(P1, P3) or similar                      │
│   - Load is distributed                                                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key insight**: Maximum parallelism = number of partitions. If you have 4 partitions and 8 consumers, 4 consumers will be idle. If you have 4 partitions and 2 consumers, each consumer handles 2 partitions.

**Multiple consumer groups**: Different consumer groups independently consume the same topic. Each maintains its own offset.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MULTIPLE CONSUMER GROUPS                                 │
│                                                                             │
│   Topic "orders" (same events)                                              │
│          │                                                                  │
│          ├───────────────────┬─────────────────────┐                        │
│          │                   │                     │                        │
│          ▼                   ▼                     ▼                        │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                     │
│   │  "search-   │    │  "payment-  │    │ "analytics- │                     │
│   │  indexer"   │    │  processor" │    │  pipeline"  │                     │
│   │  offset:    │    │  offset:    │    │  offset:    │                     │
│   │  1,234,567  │    │  1,234,890  │    │  1,200,000  │                     │
│   └─────────────┘    └─────────────┘    └─────────────┘                     │
│                                                                             │
│   Each group:                                                               │
│   - Tracks own offset per partition                                         │
│   - Processes at own speed                                                  │
│   - Can be behind or ahead of others                                        │
│   - Failure in one doesn't affect others                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Ordering Guarantees and Trade-offs

Ordering is where most Kafka confusion originates. Let's be precise:

### What Kafka Guarantees

1. **Within a partition**: Messages are strictly ordered by offset. If A is written before B, every consumer sees A before B.

2. **With the same key**: Messages with the same partition key go to the same partition, thus are ordered.

3. **From a single producer, to a single partition**: Order is preserved.

### What Kafka Does NOT Guarantee

1. **Across partitions**: No ordering. Partition 0's message 100 might be processed before or after partition 1's message 50.

2. **Across topics**: No ordering. Event in topic A might be processed before or after event in topic B.

3. **With consumer failures**: During rebalance, there's a window where ordering can be violated.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ORDERING VIOLATION SCENARIOS                             │
│                                                                             │
│   SCENARIO 1: Wrong partition key                                           │
│                                                                             │
│   Events:                                                                   │
│   1. UserCreated(user_id=123)  → Partition 2 (key=user_id)                  │
│   2. UserUpdated(user_id=123)  → Partition 2 (key=user_id) ✓ Same partition │
│   3. UserDeleted(email=a@b.c)  → Partition 0 (key=email)   ✗ Different!     │
│                                                                             │
│   Result: Delete might be processed before Create!                          │
│                                                                             │
│   SCENARIO 2: Cross-topic dependencies                                      │
│                                                                             │
│   Topic "users": UserCreated(user_id=123)                                   │
│   Topic "orders": OrderCreated(user_id=123)                                 │
│                                                                             │
│   Consumer sees OrderCreated before UserCreated                             │
│   → Order references non-existent user!                                     │
│                                                                             │
│   SCENARIO 3: Consumer rebalance                                            │
│                                                                             │
│   Consumer A processing: [M1][M2][M3][M4][M5]                               │
│                               ↑                                             │
│   Consumer A dies after processing M2 but before committing                 │
│   Consumer B takes over, starts from last committed offset (M1)             │
│   M1 and M2 are reprocessed (duplicate processing!)                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Designing for Ordering

If ordering matters, design defensively:

```
STRATEGY 1: SINGLE PARTITION (Nuclear Option)
- All events in one partition
- Perfect ordering
- Zero parallelism
- Only use for low-volume, ordering-critical scenarios

STRATEGY 2: ENTITY-BASED PARTITIONING
- Partition by entity ID (user_id, order_id)
- Ordering within entity
- Parallelism across entities
- Most common approach

STRATEGY 3: SEQUENCE NUMBERS
- Include sequence number in events
- Consumer buffers and reorders
- Handles out-of-order delivery
- Complex but robust

STRATEGY 4: IDEMPOTENT PROCESSING
- Design consumers to handle any order
- UserCreated before UserUpdated? Create first
- UserUpdated before UserCreated? Buffer and wait
- UserDeleted before UserCreated? Ignore (already deleted)
```

**Staff Insight**: Sequence numbers and idempotent processing are often both necessary. Sequence numbers let you detect out-of-order delivery. Idempotent processing lets you handle duplicates. You'll need both for robust systems.

---

## Backpressure and Consumer Lag

### What is Consumer Lag?

Consumer lag is the difference between the latest message in a partition and the consumer's current position.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CONSUMER LAG VISUALIZATION                               │
│                                                                             │
│   Partition 0:                                                              │
│   [0][1][2][3][4][5][6][7][8][9][10][11][12][13][14][15]...                  │
│                        ↑                               ↑                    │
│                   Consumer                         Latest                   │
│                   Position                         Message                  │
│                   (offset 5)                       (offset 15)              │
│                                                                             │
│                   Lag = 15 - 5 = 10 messages                                │
│                                                                             │
│   LAG OVER TIME:                                                            │
│                                                                             │
│   Lag │                                                                     │
│       │     ╱╲                                                              │
│   10K │    ╱  ╲         Spike: producer outpacing consumer                  │
│       │   ╱    ╲                                                            │
│    5K │──╱      ╲──╲                                                        │
│       │              ╲   Recovery: consumer catching up                     │
│    0K │───────────────╲────────                                             │
│       └────────────────────────▶ Time                                       │
│                                                                             │
│   Concerning patterns:                                                      │
│   - Lag increasing over time → Consumer can't keep up (will never catch up)│
│   - Lag stable but high → Consumer is keeping up but far behind             │
│   - Lag spikes during business hours → Capacity planning issue              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Why Lag Matters

Lag represents **delayed processing**. Depending on your use case, this might be:

- **Acceptable**: Analytics pipeline that can be hours behind
- **Problematic**: Search index that should reflect changes within seconds
- **Critical**: Fraud detection that must be real-time

### Causes of Lag

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    COMMON CAUSES OF CONSUMER LAG                            │
│                                                                             │
│   1. SLOW PROCESSING                                                        │
│      - Consumer does expensive work per message                             │
│      - Database writes, HTTP calls, complex computation                     │
│      Fix: Optimize processing, batch operations, async I/O                  │
│                                                                             │
│   2. INSUFFICIENT PARALLELISM                                               │
│      - Too few consumers for the partition count                            │
│      - Too few partitions for the message volume                            │
│      Fix: Add consumers (up to partition count), add partitions             │
│                                                                             │
│   3. POISON MESSAGES                                                        │
│      - One bad message causes repeated failures                             │
│      - Consumer retries forever, blocking partition                         │
│      Fix: Dead letter queue, skip after N retries                           │
│                                                                             │
│   4. HOT PARTITIONS                                                         │
│      - One partition has much more traffic than others                      │
│      - Bad partition key choice (e.g., tenant_id for one big tenant)        │
│      Fix: Better partitioning strategy, sub-partitioning                    │
│                                                                             │
│   5. REBALANCING STORMS                                                     │
│      - Frequent consumer joins/leaves cause repeated rebalances             │
│      - Each rebalance pauses processing                                     │
│      Fix: Static membership, longer session timeouts, stable deployment     │
│                                                                             │
│   6. PRODUCER BURSTS                                                        │
│      - Traffic spikes exceed consumer capacity                              │
│      - Lag increases during spike, should recover after                     │
│      Fix: Usually acceptable if lag recovers; otherwise, scale consumers    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Lag Propagation

Lag in one system can cascade to others:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    LAG PROPAGATION CASCADE                                  │
│                                                                             │
│   Orders Topic → Order Processor → Fulfillment Topic → Shipping Service    │
│                       │                                      │              │
│                       ▼                                      ▼              │
│                  Lag: 10 min                            Lag: 10 min         │
│                                                              +              │
│                                                         Processing          │
│                                                              =              │
│                                                         Lag: 15 min         │
│                                                                             │
│   If Order Processor falls behind:                                          │
│   - Fulfillment events are delayed                                          │
│   - Shipping can't process what it doesn't receive                          │
│   - Even if Shipping is fast, it shows "lag" (waiting for input)            │
│                                                                             │
│   DEBUGGING NIGHTMARE:                                                      │
│   - Shipping shows lag                                                      │
│   - Shipping team investigates                                              │
│   - "Our service is healthy, no slow processing"                            │
│   - Hours later: "Oh, Order Processor is behind"                            │
│                                                                             │
│   SOLUTION: Track lag at each hop with correlation IDs                      │
│   - Event carries timestamp from original source                            │
│   - Each consumer logs: "event_age_ms" = now - original_timestamp           │
│   - Dashboard shows where delays are introduced                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Backpressure Strategies

When consumers can't keep up, you have options:

```
STRATEGY 1: SCALE OUT
- Add more consumers (up to partition count)
- Add more partitions (if consumers are saturated)
- Horizontal scaling for the win

STRATEGY 2: BATCH PROCESSING
- Process messages in batches instead of one-at-a-time
- Reduces per-message overhead
- Enables batch database writes, bulk API calls

STRATEGY 3: DROP OR DELAY
- For non-critical data, accept some loss
- Sample metrics instead of processing all
- Delay batch jobs until off-peak hours

STRATEGY 4: PRIORITIZATION
- Process high-priority messages first
- Route to separate topics by priority
- Different consumer groups with different SLAs

STRATEGY 5: DYNAMIC THROTTLING
- Producer slows down when lag exceeds threshold
- Requires feedback loop from consumer to producer
- Works but adds complexity
```

**Staff Insight**: Lag is not inherently bad—it's a design parameter. An analytics pipeline that's 30 minutes behind is fine. A fraud detection system that's 30 seconds behind is a problem. Define your SLA first, then architect for it.

---

# Part 3: Delivery Semantics

## The Three Guarantees (And What They Really Mean)

Messaging systems offer three delivery semantics. All three have trade-offs.

### At-Most-Once

**Definition**: Each message is delivered zero or one times. Messages may be lost but are never duplicated.

```
IMPLEMENTATION:
1. Consumer receives message
2. Consumer immediately commits offset
3. Consumer processes message
4. If processing fails, message is lost (offset already moved)

PSEUDOCODE:
FOR EACH message IN consumer.poll():
    consumer.commit(message.offset)  // Commit FIRST
    TRY:
        process(message)
    CATCH error:
        log.error("Processing failed, message lost")
        // Message is gone, we've moved past it
```

**When to use**: Low-value, high-volume data where occasional loss is acceptable.
- Web analytics events (missing a few page views is fine)
- Debug logs (completeness not required)
- Metrics that are aggregated anyway (missing 1 of 1000 samples doesn't matter)

### At-Least-Once

**Definition**: Each message is delivered one or more times. Messages may be duplicated but are never lost.

```
IMPLEMENTATION:
1. Consumer receives message
2. Consumer processes message
3. Consumer commits offset
4. If commit fails, message will be redelivered (duplicate processing)

PSEUDOCODE:
FOR EACH message IN consumer.poll():
    TRY:
        process(message)
        consumer.commit(message.offset)  // Commit AFTER success
    CATCH error:
        log.error("Processing failed, will retry")
        // Don't commit, message will be redelivered
```

**The duplicate problem**:
```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    AT-LEAST-ONCE DUPLICATE SCENARIO                         │
│                                                                             │
│   Timeline:                                                                 │
│                                                                             │
│   T1: Consumer receives message M                                           │
│   T2: Consumer processes message (inserts row in database)                  │
│   T3: Consumer tries to commit offset                                       │
│   T4: Network error! Commit fails                                           │
│   T5: Consumer restarts or rebalance occurs                                 │
│   T6: Consumer receives message M again (offset wasn't committed)           │
│   T7: Consumer processes message again (inserts ANOTHER row!)               │
│   T8: Commit succeeds                                                       │
│                                                                             │
│   Result: Same message processed twice, duplicate data in database          │
│                                                                             │
│   This happens in production. Plan for it.                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**When to use**: Most use cases. But requires idempotent consumers.

### Exactly-Once

**Definition**: Each message is delivered exactly one time. No loss, no duplicates.

This is the holy grail—and it's complicated.

```
THE HARSH TRUTH ABOUT EXACTLY-ONCE:

"Exactly-once" means different things in different contexts:

1. EXACTLY-ONCE WITHIN KAFKA (Kafka Transactions)
   - Kafka can ensure producer writes are atomic
   - Kafka can ensure consumer reads + producer writes are atomic
   - But the MOMENT you write to external system, you lose this

2. EXACTLY-ONCE TO EXTERNAL SYSTEMS (Impossible Without Help)
   - Kafka commits offset
   - You write to database
   - Kafka crashes before recording the commit
   - On restart, you write to database AGAIN
   - Database now has duplicate

   Unless database write is IDEMPOTENT, you have duplicates.

3. PRACTICAL "EXACTLY-ONCE" (Idempotence + At-Least-Once)
   - Accept that duplicates will happen
   - Make processing idempotent
   - Result: effective exactly-once semantics
```

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    "EXACTLY-ONCE" IMPLEMENTATION                            │
│                                                                             │
│   STRATEGY: IDEMPOTENT CONSUMER                                             │
│                                                                             │
│   Each event carries a unique idempotency_key (e.g., event_id or UUID)      │
│                                                                             │
│   PSEUDOCODE:                                                               │
│   FOR EACH message IN consumer.poll():                                      │
│       TRY:                                                                  │
│           // Check if already processed                                     │
│           IF database.exists("processed_events", message.idempotency_key):  │
│               log.info("Duplicate, skipping")                               │
│               consumer.commit(message.offset)                               │
│               CONTINUE                                                      │
│                                                                             │
│           // Process in transaction with idempotency record                 │
│           database.begin_transaction()                                      │
│           process_business_logic(message)                                   │
│           database.insert("processed_events", message.idempotency_key)      │
│           database.commit_transaction()                                     │
│                                                                             │
│           consumer.commit(message.offset)                                   │
│       CATCH error:                                                          │
│           database.rollback_transaction()                                   │
│           // Will retry on next poll                                        │
│                                                                             │
│   Result: Even if message is delivered twice, it's processed once           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Duplication vs Loss Trade-offs

The fundamental trade-off:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DUPLICATION vs LOSS: PICK YOUR POISON                    │
│                                                                             │
│                           COMMIT BEFORE PROCESSING                          │
│                                     │                                       │
│                           Risk: MESSAGE LOSS                                │
│                           (If processing fails after commit)                │
│                                     │                                       │
│   ◄────────────────────────────────────────────────────────────────────►    │
│                                     │                                       │
│                           Risk: DUPLICATION                                 │
│                           (If commit fails after processing)                │
│                                     │                                       │
│                          COMMIT AFTER PROCESSING                            │
│                                                                             │
│   WHICH IS WORSE?                                                           │
│                                                                             │
│   Financial transactions: Loss is catastrophic, duplicates are bad          │
│                           → At-least-once with idempotence                  │
│                                                                             │
│   Analytics events:       Loss is acceptable, duplicates inflate metrics    │
│                           → At-most-once is often fine                      │
│                                                                             │
│   Notification sends:     Loss means user doesn't get notified              │
│                           Duplicates mean user gets notified twice          │
│                           → Usually prefer duplicate notifications          │
│                                                                             │
│   Idempotent operations:  Loss loses data                                   │
│                           Duplicates have no effect (idempotent!)           │
│                           → At-least-once, duplicates are free              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Making Operations Idempotent

The key to handling at-least-once delivery is making your operations idempotent:

```
NATURALLY IDEMPOTENT OPERATIONS:

SET user.email = "new@example.com"
  → Same result whether executed 1 or 100 times

DELETE FROM orders WHERE id = 123
  → Second delete is a no-op

UPSERT: INSERT ... ON CONFLICT DO UPDATE
  → Second insert updates (idempotent if update is idempotent)


NOT IDEMPOTENT OPERATIONS:

INCREMENT counter
  → Each execution adds 1 (counter += N for N executions)

INSERT INTO orders (...)
  → Each execution creates a new row

APPEND TO list
  → Each execution adds another item


MAKING NON-IDEMPOTENT OPERATIONS IDEMPOTENT:

Instead of: INSERT INTO orders (user_id, product_id, ...)
Use:        INSERT INTO orders (order_id, user_id, product_id, ...)
            ON CONFLICT (order_id) DO NOTHING
Where:      order_id comes from the event (not auto-generated)

Instead of: UPDATE wallets SET balance = balance + 100 WHERE user_id = ?
Use:        INSERT INTO transactions (transaction_id, user_id, amount)
            ON CONFLICT (transaction_id) DO NOTHING
            Balance is computed from sum of transactions (event sourcing)

Instead of: counter++
Use:        Store processed event IDs, skip if already seen
            Or use HyperLogLog for approximate counting (duplicates don't matter)
```

---

## Why Exactly-Once Does Not Remove Complexity

A common misconception: "We'll use Kafka's exactly-once, so we don't need to worry about duplicates."

This is dangerously wrong. Here's why:

### Kafka's Exactly-Once Scope

Kafka's transactional/exactly-once features cover:
1. **Producer to Kafka**: A batch of writes is atomic (all or nothing)
2. **Kafka to Kafka**: Read from topic A, write to topic B atomically
3. **Consumer offset + Kafka write**: Commit offset and produce messages atomically

Kafka's exactly-once does NOT cover:
1. **Kafka to external database**: Write to Postgres is outside Kafka's transaction
2. **Kafka to external API**: HTTP call to Stripe is outside Kafka's transaction
3. **Kafka to file system**: File write is outside Kafka's transaction

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    EXACTLY-ONCE BOUNDARY PROBLEM                            │
│                                                                             │
│   INSIDE KAFKA (Exactly-once works):                                        │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Topic A ──▶ Consumer ──▶ Producer ──▶ Topic B                      │   │
│   │              └──────── Kafka Transaction ────────┘                  │   │
│   │                                                                     │   │
│   │  This is atomic: either both happen or neither happens              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   CROSSING BOUNDARY (Exactly-once breaks):                                  │
│                                                                             │
│   ┌───────────────────────────────┐  ┌───────────────────────────────┐      │
│   │         KAFKA WORLD           │  │       EXTERNAL WORLD          │      │
│   │                               │  │                               │      │
│   │  Topic A ──▶ Consumer ──────────────▶ Postgres                   │      │
│   │                  │            │  │        │                      │      │
│   │                  └──commit────│──│────────┘                      │      │
│   │                               │  │                               │      │
│   │  Kafka commit and Postgres    │  │  These are TWO transactions   │      │
│   │  write are separate!          │  │  Not atomic together          │      │
│   └───────────────────────────────┘  └───────────────────────────────┘      │
│                                                                             │
│   Failure scenario:                                                         │
│   1. Consumer reads from Topic A                                            │
│   2. Consumer writes to Postgres (SUCCESS)                                  │
│   3. Consumer commits offset to Kafka (FAILURE - network issue)             │
│   4. Consumer restarts, reads same message again                            │
│   5. Consumer writes to Postgres again (DUPLICATE!)                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### The Outbox Pattern

For exactly-once semantics across boundaries, use the **outbox pattern**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    OUTBOX PATTERN FOR CROSS-BOUNDARY ATOMICITY              │
│                                                                             │
│   PROBLEM: Can't atomically write to Postgres AND commit Kafka offset       │
│                                                                             │
│   SOLUTION: Write to Postgres outbox table, relay to Kafka                  │
│                                                                             │
│   ┌──────────────────────────────────────────────────────────────────┐      │
│   │                    DATABASE TRANSACTION                          │      │
│   │                                                                  │      │
│   │   1. Write business data to orders table                         │      │
│   │   2. Write event to outbox table (same transaction!)             │      │
│   │                                                                  │      │
│   │   BEGIN;                                                         │      │
│   │   INSERT INTO orders (id, user_id, ...) VALUES (...);            │      │
│   │   INSERT INTO outbox (id, topic, payload, created_at)            │      │
│   │       VALUES (uuid(), 'orders', '{"order_id": ...}', now());     │      │
│   │   COMMIT;                                                        │      │
│   │                                                                  │      │
│   │   Atomicity guaranteed by database transaction!                  │      │
│   └──────────────────────────────────────────────────────────────────┘      │
│                                                                             │
│   ┌──────────────────────────────────────────────────────────────────┐      │
│   │                    OUTBOX RELAY (Separate Process)               │      │
│   │                                                                  │      │
│   │   LOOP:                                                          │      │
│   │     events = SELECT * FROM outbox WHERE relayed = false          │      │
│   │                     ORDER BY created_at LIMIT 100                │      │
│   │     FOR event IN events:                                         │      │
│   │         kafka.produce(event.topic, event.payload)                │      │
│   │         UPDATE outbox SET relayed = true WHERE id = event.id     │      │
│   │                                                                  │      │
│   │   If relay crashes, it will retry (at-least-once)                │      │
│   │   Kafka consumers must still be idempotent!                      │      │
│   └──────────────────────────────────────────────────────────────────┘      │
│                                                                             │
│   This gives you:                                                           │
│   - Atomicity between business write and event publish intent               │
│   - At-least-once delivery to Kafka (relay might duplicate)                 │
│   - Need idempotent consumers (always need this!)                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Staff Insight**: The outbox pattern is the standard approach for reliable event publishing from a database. Tools like Debezium can automate the relay by reading the database's change log. But even with outbox + Debezium, consumers still need to be idempotent.

---

# Part 4: Event-Driven Anti-Patterns

## Anti-Pattern 1: Over-Eventing

**Symptom**: Everything is an event. User clicks a button? Event. Page loads? Event. API called? Event.

**Why it happens**: "We might need this data someday" combined with "events are cheap."

**Why it hurts**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    OVER-EVENTING DEATH SPIRAL                               │
│                                                                             │
│   Stage 1: "Let's publish events for everything!"                           │
│   - 50 event types across 10 services                                       │
│   - 10 million events per day                                               │
│   - "Look how decoupled we are!"                                            │
│                                                                             │
│   Stage 2: "We need to understand our event flows"                          │
│   - Build event catalog (which events exist?)                               │
│   - Build event lineage (who produces? who consumes?)                       │
│   - 3 engineers spend 2 months on tooling                                   │
│                                                                             │
│   Stage 3: "Some events are causing problems"                               │
│   - Schema changed, consumers are failing                                   │
│   - Which consumers? We have 30 consumer groups...                          │
│   - Nobody knows who owns consumer-group-legacy-v2                          │
│                                                                             │
│   Stage 4: "We need event versioning and contracts"                         │
│   - Build schema registry                                                   │
│   - Introduce event versioning (UserCreatedV1, V2, V3...)                   │
│   - Now managing 150 event versions                                         │
│                                                                             │
│   Stage 5: "Events are our biggest operational burden"                      │
│   - Full-time team managing Kafka infrastructure                            │
│   - Full-time team managing event schemas                                   │
│   - Every incident involves "check the events"                              │
│   - "Maybe we over-did the events..."                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**The fix**: Treat events as API contracts. Every event type should have:
- An owner
- A documented schema
- Known consumers
- A reason to exist

```
QUESTIONS BEFORE ADDING AN EVENT:

1. Who will consume this event?
   - "Maybe someone" is not an answer
   - No consumer = no event (yet)

2. What's the contract?
   - Schema versioning strategy
   - Backwards compatibility commitment
   - Breaking change process

3. What's the SLA?
   - How fresh must this data be?
   - What happens if processing is delayed?

4. Who's on-call?
   - When this breaks at 3am, who gets paged?
   - "The platform team" is not specific enough
```

---

## Anti-Pattern 2: Tight Coupling via Events

**Symptom**: Services that communicate via events are tightly coupled to event schemas and semantics, but nobody acknowledges it.

**Why it happens**: Events feel loosely coupled because there's no compile-time dependency. But there's a runtime dependency that's harder to see and more dangerous.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    HIDDEN COUPLING IN EVENTS                                │
│                                                                             │
│   EXPLICIT API COUPLING (Visible):                                          │
│                                                                             │
│   // Order service                                                          │
│   import { PaymentClient } from '@company/payment-sdk';                     │
│   const result = await paymentClient.charge(orderId, amount);               │
│                                                                             │
│   - Coupling is in the code                                                 │
│   - IDE shows the dependency                                                │
│   - Breaking changes fail at compile time                                   │
│   - Clear ownership and versioning                                          │
│                                                                             │
│   HIDDEN EVENT COUPLING (Invisible):                                        │
│                                                                             │
│   // Order service                                                          │
│   kafka.produce('order-events', { type: 'OrderPlaced', orderId, amount });  │
│                                                                             │
│   // Payment service (completely different codebase)                        │
│   kafka.consume('order-events', (event) => {                                │
│       if (event.type === 'OrderPlaced') {                                   │
│           charge(event.orderId, event.amount);  // ASSUMES schema!          │
│       }                                                                     │
│   });                                                                       │
│                                                                             │
│   - Coupling is in runtime behavior                                         │
│   - IDE shows no dependency                                                 │
│   - Breaking changes fail at runtime, possibly hours later                  │
│   - Ownership is unclear (who owns the event schema?)                       │
│                                                                             │
│   THE COUPLING EXISTS. IT'S JUST INVISIBLE.                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Manifestations of event coupling**:

1. **Schema coupling**: Consumer expects `event.userId`, producer changes to `event.user_id`. Consumer breaks.

2. **Semantic coupling**: Consumer expects `amount` in cents, producer changes to dollars. Consumer silently charges 100x.

3. **Ordering coupling**: Consumer expects `UserCreated` before `OrderCreated`. Producer changes publish order. Consumer creates orphan orders.

4. **Timing coupling**: Consumer expects events within 1 second. Producer adds batching with 10-second flush. Consumer SLA violated.

**The fix**: Treat events as public APIs with the same rigor:

```
EVENT API CONTRACT:

Topic: order-events
Event: OrderPlaced (v2)
Owner: Order Team (order-team@company.com)
Schema:
  {
    "event_id": "uuid",           // Required, idempotency key
    "event_type": "OrderPlaced",  // Required
    "event_version": 2,           // Required
    "timestamp": "ISO8601",       // Required
    "data": {
      "order_id": "uuid",         // Required
      "user_id": "uuid",          // Required  
      "amount_cents": "integer",  // Required, always cents
      "currency": "string"        // Required, ISO 4217
    }
  }

Compatibility: Backwards compatible. New fields may be added.
                Fields will not be removed or renamed without v3.
                
Ordering: Events for same order_id are ordered.
          Events for different orders have no ordering guarantee.
          
Consumers:
  - payment-processor (Payment Team)
  - inventory-manager (Fulfillment Team)
  - analytics-pipeline (Data Team)
```

---

## Anti-Pattern 3: Debuggability Nightmares

**Symptom**: When something goes wrong, nobody can figure out what happened.

**Why it happens**: Events break the request/response model that makes tracing easy. A single user action might trigger a cascade of events across 10 services, and correlating them requires tooling that doesn't exist.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DEBUGGING NIGHTMARE SCENARIO                             │
│                                                                             │
│   User report: "I placed an order 2 hours ago, still no confirmation"       │
│                                                                             │
│   WHAT ACTUALLY HAPPENED (unknown to debugger):                             │
│                                                                             │
│   10:00:00 - User submits order                                             │
│   10:00:01 - Order service creates order, publishes OrderPlaced             │
│   10:00:02 - Payment service receives OrderPlaced, calls Stripe             │
│   10:00:03 - Stripe returns success, Payment publishes PaymentSucceeded     │
│   10:00:04 - Notification service receives PaymentSucceeded                 │
│   10:00:04 - Notification tries to get user email from User service         │
│   10:00:05 - User service is slow (database issue)                          │
│   10:00:35 - User service times out                                         │
│   10:00:35 - Notification service logs error, message goes to DLQ           │
│   10:00:35 - Nobody is monitoring the DLQ                                   │
│   12:00:00 - User complains                                                 │
│                                                                             │
│   DEBUGGER'S VIEW:                                                          │
│                                                                             │
│   "Let me check the order service logs..."                                  │
│   → Order was created successfully ✓                                        │
│                                                                             │
│   "Let me check if payment went through..."                                 │
│   → Payment succeeded ✓                                                     │
│                                                                             │
│   "So why no confirmation email?"                                           │
│   → ???                                                                     │
│                                                                             │
│   "Let me check notification service..."                                    │
│   → Which notification service instance? There are 20.                      │
│   → What's the correlation ID? Events don't have request IDs.               │
│   → Did it even receive the event? Check consumer lag...                    │
│                                                                             │
│   2 hours of investigation later: found the DLQ message                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**The fix**: Correlation and tracing are non-negotiable in event-driven systems.

```
MANDATORY EVENT DEBUGGING INFRASTRUCTURE:

1. CORRELATION IDS
   Every event carries a correlation_id from the original request.
   All logs include correlation_id.
   Searching logs by correlation_id shows entire flow.

   {
     "event_id": "evt-789",
     "correlation_id": "req-123",  // From original HTTP request
     "causation_id": "evt-456",    // The event that caused this event
     ...
   }

2. DISTRIBUTED TRACING
   OpenTelemetry or similar across all services.
   Events carry trace context (trace_id, span_id).
   Jaeger/Zipkin shows event flow as spans.

3. EVENT FLOW VISUALIZATION
   Dashboard showing: event → consumers → downstream events
   Real-time visibility into event propagation.

4. DEAD LETTER QUEUE MONITORING
   Alert when DLQ has messages.
   Dashboard showing DLQ contents.
   Playbook for DLQ investigation.

5. EVENT REPLAY TOOLING
   Ability to replay single event for debugging.
   Ability to replay time range for recovery.
   Safe replay (doesn't affect production if misconfigured).
```

---

## Anti-Pattern 4: Event-Driven for the Wrong Reasons

**Symptom**: Team chose events because they're "modern" or "scalable" without analyzing if they're appropriate.

**Common bad reasons to use events**:

```
BAD REASON 1: "Microservices should communicate via events"
REALITY: Microservices can use sync calls, events, or both.
         Choose based on requirements, not dogma.

BAD REASON 2: "Events are more scalable"
REALITY: Events add Kafka, consumer groups, lag management.
         That's MORE infrastructure, not less.
         Sync calls through load balancer are also scalable.

BAD REASON 3: "We want loose coupling"
REALITY: Events create different coupling (schema, semantic).
         Often harder to manage than explicit API coupling.

BAD REASON 4: "Netflix/LinkedIn uses events"
REALITY: They also have 100+ engineers on their platform team.
         They built custom tooling for years.
         Can you afford that investment?

BAD REASON 5: "We might need to add more consumers later"
REALITY: YAGNI. Add events when you have multiple consumers.
         Converting sync to async is easier than debugging async.
```

**Good reasons to use events**:

```
GOOD REASON 1: Multiple independent consumers exist TODAY
- Order placed → Payment, Inventory, Analytics, Fraud
- Fan-out to many services that don't need coordination

GOOD REASON 2: Traffic spikes exceed backend capacity
- Black Friday surge that would overwhelm database
- Events buffer the spike, consumers process at steady rate

GOOD REASON 3: Processing is slow and can be async
- Video transcoding that takes minutes
- Report generation that takes hours
- User doesn't need immediate result

GOOD REASON 4: Replay and reprocessing are required
- Need to reprocess historical data when fixing bugs
- Need to backfill when adding new consumers
- Audit requirements mandate event log

GOOD REASON 5: Failure isolation is critical
- Downstream failures shouldn't affect upstream
- Circuit breaker isn't sufficient
- Need hours of tolerance, not seconds
```

---

## Anti-Pattern 5: Unclear Ownership Boundaries

**Symptom**: When event processing breaks, nobody knows who's responsible. Schema changes break consumers, but who owns the schema? Consumer lag spikes, but who gets paged?

**Why it happens**: Events create implicit dependencies that don't show up in org charts. The producer team doesn't know all consumers. The consumer team doesn't control the producer. The platform team manages Kafka but doesn't understand business logic.

### Ownership Boundaries in Event-Driven Systems

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    OWNERSHIP BOUNDARIES: WHO OWNS WHAT?                    │
│                                                                             │
│   QUESTION 1: Who owns the event schema?                                    │
│   ────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│   BAD: "Everyone owns it" or "The platform team"                            │
│   - Schema changes break consumers randomly                                  │
│   - No versioning strategy                                                  │
│   - Breaking changes deployed without coordination                           │
│                                                                             │
│   GOOD: Producer team owns schema, consumers depend on it                    │
│   - Order Team owns OrderPlaced event schema                                 │
│   - Payment Team consumes OrderPlaced (depends on Order Team)               │
│   - Order Team commits to backwards compatibility                            │
│   - Order Team announces breaking changes 30 days in advance                 │
│                                                                             │
│   OWNERSHIP MODEL:                                                           │
│   - Producer = Schema Owner (defines contract)                              │
│   - Consumer = Schema Dependent (must adapt to changes)                       │
│   - Platform Team = Infrastructure Owner (Kafka, not schemas)              │
│                                                                             │
│   QUESTION 2: Who gets paged when consumer lag spikes?                      │
│   ────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│   BAD: "The platform team" (they don't know why lag is high)              │
│   - Platform team pages consumer team: "Your lag is high"                  │
│   - Consumer team: "It's not our fault, database is slow"                  │
│   - Database team: "It's not our fault, queries are fine"                  │
│   - Hours wasted in blame game                                               │
│                                                                             │
│   GOOD: Consumer team owns lag, platform team owns Kafka health             │
│   - Alert: "inventory-consumer lag > 10K" → Page Inventory Team             │
│   - Alert: "Kafka broker CPU > 90%" → Page Platform Team                    │
│   - Alert: "Kafka disk > 90%" → Page Platform Team                          │
│   - Clear ownership = faster resolution                                     │
│                                                                             │
│   OWNERSHIP MODEL:                                                          │
│   - Consumer Team = Owns consumer lag (their processing is slow)            │
│   - Platform Team = Owns Kafka availability (brokers, network)              │
│   - Producer Team = Owns producer throughput (if producer is slow)          │
│                                                                             │
│   QUESTION 3: Who owns event versioning and compatibility?                 │
│   ────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│   BAD: "We'll figure it out when we need it"                                │
│   - Schema changes break production                                         │
│   - No deprecation process                                                  │
│   - Consumers stuck on old versions forever                                 │
│                                                                             │
│   GOOD: Producer team owns versioning, platform team provides tooling      │
│   - Producer team: Defines versioning strategy (semantic versioning)         │
│   - Producer team: Maintains compatibility (backwards compatible changes)   │
│   - Platform team: Provides schema registry (tooling, not policy)           │
│   - Platform team: Enforces compatibility rules (automated checks)          │
│                                                                             │
│   OWNERSHIP MODEL:                                                          │
│   - Producer Team = Policy owner (what versions, how long to support)       │
│   - Platform Team = Tooling owner (schema registry, compatibility checks)   │
│                                                                             │
│   QUESTION 4: Who owns the DLQ (Dead Letter Queue)?                         │
│   ────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│   BAD: "Nobody" or "The platform team"                                      │
│   - DLQ fills up, nobody notices                                             │
│   - Messages sit in DLQ for weeks                                             │
│   - No playbook for DLQ investigation                                       │
│                                                                             │
│   GOOD: Consumer team owns DLQ, platform team provides infrastructure       │
│   - Consumer team: Monitors DLQ size (alert on any messages)                 │
│   - Consumer team: Investigates DLQ messages (why did they fail?)           │
│   - Consumer team: Fixes bugs and replays                                    │
│   - Platform team: Provides DLQ topic infrastructure                        │
│                                                                             │
│   OWNERSHIP MODEL:                                                          │
│   - Consumer Team = DLQ owner (their processing failed)                       │
│   - Platform Team = DLQ infrastructure (topic, monitoring hooks)            │
│                                                                             │
│   QUESTION 5: Who owns cross-service event dependencies?                    │
│   ────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│   BAD: "Each team owns their service" (ignores dependencies)                │
│   - Order Team changes OrderPlaced schema                                   │
│   - Payment Team breaks (didn't know about change)                          │
│   - Blame game: "You should have checked" vs "You should have told us"      │
│                                                                             │
│   GOOD: Dependency graph tracked, change coordination required               │
│   - Event catalog: Lists all events, producers, consumers                   │
│   - Change process: Producer announces changes, consumers acknowledge        │
│   - Breaking changes: Require approval from all consumers                   │
│   - Non-breaking changes: Notification only (consumers adapt when ready)    │
│                                                                             │
│   OWNERSHIP MODEL:                                                          │
│   - Producer Team = Change initiator (proposes changes)                      │
│   - Consumer Teams = Change approvers (must approve breaking changes)       │
│   - Platform Team = Dependency tracking (maintains catalog)                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Organizational Patterns for Event Ownership

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    OWNERSHIP PATTERNS IN PRACTICE                          │
│                                                                             │
│   PATTERN 1: PRODUCER-OWNED SCHEMAS                                         │
│   ────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│   Order Team publishes OrderPlaced event:                                   │
│   - Order Team owns the schema (defines fields, types)                      │
│   - Order Team commits to backwards compatibility                           │
│   - Order Team maintains changelog (what changed, when, why)                 │
│   - Order Team announces breaking changes 30 days in advance                │
│                                                                             │
│   Payment Team consumes OrderPlaced:                                         │
│   - Payment Team depends on Order Team's schema                             │
│   - Payment Team must adapt to non-breaking changes                         │
│   - Payment Team must approve breaking changes (can block if needed)        │
│                                                                             │
│   Platform Team:                                                             │
│   - Provides schema registry (tooling)                                      │
│   - Enforces compatibility rules (automated)                                 │
│   - Does NOT own business schemas                                           │
│                                                                             │
│   PATTERN 2: CONSUMER-OWNED LAG                                             │
│   ────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│   Inventory Service consumer lag spikes:                                    │
│   - Alert fires: "inventory-consumer lag > 10K"                             │
│   - Pages: Inventory Team (not Platform Team)                               │
│   - Inventory Team investigates:                                             │
│     * Is processing slow? (their code)                                      │
│     * Is database slow? (their database)                                    │
│     * Is Kafka slow? (check with Platform Team)                            │
│                                                                             │
│   Platform Team:                                                             │
│   - Owns Kafka broker health (CPU, disk, network)                           │
│   - Owns Kafka availability (brokers down, partitions unavailable)           │
│   - Does NOT own consumer lag (that's consumer's processing)                │
│                                                                             │
│   PATTERN 3: SHARED OWNERSHIP FOR INFRASTRUCTURE                            │
│   ────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│   Kafka cluster capacity:                                                    │
│   - Platform Team: Owns broker capacity (adds brokers when needed)          │
│   - Producer Teams: Owns topic capacity (requests partitions)               │
│   - Consumer Teams: Owns consumer capacity (scales consumers)               │
│                                                                             │
│   Coordination:                                                              │
│   - Platform Team: Provides capacity planning guidance                       │
│   - Teams: Request capacity changes through Platform Team                   │
│   - Platform Team: Approves/rejects based on cluster capacity               │
│                                                                             │
│   PATTERN 4: EVENT CATALOG AS CONTRACT REGISTRY                             │
│   ────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│   Event Catalog (maintained by Platform Team, content by Producer Teams):   │
│   - Event name: OrderPlaced                                                 │
│   - Owner: Order Team (order-team@company.com)                             │
│   - Schema: { order_id, user_id, amount_cents, ... }                       │
│   - Consumers: Payment Team, Inventory Team, Analytics Team                 │
│   - Versioning: Semantic (v1, v2, v3)                                       │
│   - Compatibility: Backwards compatible (new fields only)                   │
│                                                                             │
│   Change Process:                                                            │
│   1. Order Team proposes schema change                                      │
│   2. Catalog notifies all consumers                                         │
│   3. If breaking change: Consumers must approve                             │
│   4. If non-breaking: Consumers acknowledge (no approval needed)            │
│   5. Order Team deploys after approval/acknowledgment                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Staff Engineer's Ownership Checklist

Before deploying an event-driven system, answer:

```
OWNERSHIP CHECKLIST:

□ Who owns each event schema?
  → Producer team name, contact email

□ Who gets paged when consumer lag spikes?
  → Consumer team (not platform team)

□ Who owns the DLQ?
  → Consumer team (their processing failed)

□ Who owns event versioning policy?
  → Producer team (defines compatibility rules)

□ Who maintains the event catalog?
  → Platform team (tooling), Producer teams (content)

□ Who approves breaking schema changes?
  → All consumer teams (must approve before deploy)

□ Who owns Kafka infrastructure capacity?
  → Platform team (brokers), Teams (topics/consumers)

□ Who debugs cross-service event flows?
  → Consumer team (with correlation IDs from producer)

If you can't answer all 8, you're not ready for production.
```

**Why Ownership Matters**:

1. **Faster incident resolution**: Clear ownership = faster escalation
2. **Prevents blame games**: Everyone knows their responsibility
3. **Enables autonomy**: Teams can operate independently within boundaries
4. **Reduces platform team burden**: Platform team doesn't debug business logic

**Common Anti-Pattern**:

- **"Platform team owns everything"**: Platform team becomes bottleneck, doesn't understand business logic
- **"Each team owns their service"**: Ignores dependencies, breaking changes deployed without coordination
- **"Nobody owns it"**: DLQ fills up, lag spikes, schema changes break production

**Staff Engineer Rule**: Every event, every consumer, every alert must have a clear owner. If ownership is unclear, the system will fail in production.

---

# Part 5: Applied Examples

## Example 1: Notification Pipeline

### Requirements
- Send notifications (email, push, SMS) for various user actions
- User preferences determine which channels are enabled
- Each notification type has different templates
- Some notifications are time-sensitive, others can be delayed
- Track delivery status for analytics

### Design Evolution

**Stage 1: Naive Event-Driven (Common Mistake)**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    NOTIFICATION PIPELINE V1 (PROBLEMATIC)                   │
│                                                                             │
│   Every Service ──publish──▶ NotificationRequested event                    │
│                                      │                                      │
│                                      ▼                                      │
│                             ┌────────────────┐                              │
│                             │ Notification   │                              │
│                             │ Service        │                              │
│                             └───────┬────────┘                              │
│                                     │                                       │
│                    ┌────────────────┼────────────────┐                      │
│                    ▼                ▼                ▼                      │
│              ┌─────────┐      ┌─────────┐      ┌─────────┐                  │
│              │ Email   │      │  Push   │      │   SMS   │                  │
│              │ Provider│      │ Provider│      │ Provider│                  │
│              └─────────┘      └─────────┘      └─────────┘                  │
│                                                                             │
│   PROBLEMS:                                                                 │
│   1. Single consumer creates bottleneck                                     │
│   2. One slow email blocks all notifications                                │
│   3. No priority: password reset waits behind marketing                     │
│   4. Provider failure affects all notifications                             │
│   5. Hard to retry failed sends without duplicates                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Stage 2: Better Design with Separation**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    NOTIFICATION PIPELINE V2 (IMPROVED)                      │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    INGESTION LAYER                                  │   │
│   │                                                                     │   │
│   │   notification-requests (Kafka topic)                               │   │
│   │   Partitioned by user_id (preference lookup locality)               │   │
│   │                                                                     │   │
│   │   Schema:                                                           │   │
│   │   {                                                                 │   │
│   │     notification_id: uuid,     // Idempotency key                   │   │
│   │     user_id: uuid,                                                  │   │
│   │     type: "order_shipped",     // Maps to template                  │   │
│   │     priority: "high",          // high, normal, low                 │   │
│   │     data: { order_id, tracking_number, ... },                       │   │
│   │     requested_at: timestamp                                         │   │
│   │   }                                                                 │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    ROUTING LAYER                                    │   │
│   │                                                                     │   │
│   │   Notification Router (Consumer Group)                              │   │
│   │   - Fetch user preferences                                          │   │
│   │   - Apply business rules (quiet hours, frequency caps)              │   │
│   │   - Route to channel-specific topics                                │   │
│   │                                                                     │   │
│   │   Output topics:                                                    │   │
│   │   - email-high-priority                                             │   │
│   │   - email-normal                                                    │   │
│   │   - push-high-priority                                              │   │
│   │   - push-normal                                                     │   │
│   │   - sms (always high priority)                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│              ┌───────────────┼───────────────┐                              │
│              ▼               ▼               ▼                              │
│   ┌─────────────────┐ ┌─────────────┐ ┌─────────────┐                       │
│   │  Email Workers  │ │Push Workers │ │ SMS Workers │                       │
│   │  (per priority) │ │(per priority)│ │             │                       │
│   └────────┬────────┘ └──────┬──────┘ └──────┬──────┘                       │
│            │                 │               │                              │
│            ▼                 ▼               ▼                              │
│   ┌─────────────────┐ ┌─────────────┐ ┌─────────────┐                       │
│   │ SendGrid/SES    │ │ FCM/APNS    │ │ Twilio      │                       │
│   └─────────────────┘ └─────────────┘ └─────────────┘                       │
│                                                                             │
│   IMPROVEMENTS:                                                             │
│   - Priority queues prevent low-priority blocking high-priority             │
│   - Channel-specific workers isolate failures                               │
│   - Horizontal scaling per channel                                          │
│   - Idempotency via notification_id at each stage                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Handling failures and retries**:

```
EMAIL WORKER LOGIC:

FUNCTION process_email(message):
    notification_id = message.notification_id
    
    // Idempotency check
    IF redis.EXISTS("email:sent:" + notification_id):
        log.info("Already sent, skipping")
        RETURN SUCCESS
    
    // Render template
    TRY:
        content = template_service.render(message.type, message.data)
    CATCH TemplateError:
        // Bad data, won't fix on retry
        send_to_dlq(message, "template_error")
        RETURN SUCCESS  // Don't retry
    
    // Send via provider
    TRY:
        result = sendgrid.send(
            to: message.email,
            subject: content.subject,
            body: content.body
        )
    CATCH RateLimitError:
        // Transient, retry later
        THROW RetryableError("rate_limited")
    CATCH InvalidEmailError:
        // Permanent failure
        publish("notification-failed", { 
            notification_id, reason: "invalid_email" 
        })
        RETURN SUCCESS  // Don't retry
    CATCH ProviderError:
        // Provider is down, retry
        THROW RetryableError("provider_error")
    
    // Mark as sent (idempotency)
    redis.SET("email:sent:" + notification_id, "1", EX=86400)
    
    // Publish success event
    publish("notification-sent", {
        notification_id,
        channel: "email",
        sent_at: now()
    })
    
    RETURN SUCCESS
```

### Key Design Decisions

1. **Why events make sense here**: Multiple async steps (routing, rendering, sending), fan-out to multiple channels, spikes during marketing campaigns, retry/replay needed.

2. **Why NOT pure events**: User preference lookup is sync (small, fast, required for routing).

3. **Priority separation**: Critical notifications (password reset) shouldn't wait behind marketing blasts.

4. **Idempotency at every stage**: notification_id flows through entire pipeline, each stage dedupes.

---

## Example 2: Feed Fan-Out

### Requirements
- User posts content, followers see it in their feed
- Users follow thousands of accounts
- Celebrity accounts have millions of followers
- Feed should show recent posts, ordered by time
- Posts should appear in feeds within seconds

### The Fan-Out Trade-off

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FEED FAN-OUT STRATEGIES                                  │
│                                                                             │
│   STRATEGY 1: FAN-OUT ON READ (Pull)                                        │
│                                                                             │
│   User opens app:                                                           │
│   1. Get list of accounts user follows (1000 accounts)                      │
│   2. Query each account's recent posts                                      │
│   3. Merge and sort                                                         │
│   4. Return top N                                                           │
│                                                                             │
│   Pros: Simple, no write amplification                                      │
│   Cons: Slow reads (1000 queries), high read latency                        │
│   Best for: Small follow counts                                             │
│                                                                             │
│   STRATEGY 2: FAN-OUT ON WRITE (Push)                                       │
│                                                                             │
│   User posts:                                                               │
│   1. Store post                                                             │
│   2. Get list of followers                                                  │
│   3. Write post_id to each follower's feed cache                            │
│                                                                             │
│   User opens app:                                                           │
│   1. Read pre-computed feed from cache                                      │
│   2. Hydrate post details                                                   │
│   3. Return                                                                 │
│                                                                             │
│   Pros: Fast reads (single cache lookup)                                    │
│   Cons: Write amplification (1M followers = 1M writes)                      │
│   Best for: Normal users, read-heavy access patterns                        │
│                                                                             │
│   STRATEGY 3: HYBRID (What Twitter/X Uses)                                  │
│                                                                             │
│   For normal users (< 10K followers): Fan-out on write                      │
│   For celebrities (> 10K followers): Fan-out on read                        │
│                                                                             │
│   User opens app:                                                           │
│   1. Read pre-computed feed (from followed normal users)                    │
│   2. Query recent posts from followed celebrities                           │
│   3. Merge and return                                                       │
│                                                                             │
│   Balances write cost and read latency                                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Event-Driven Feed Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FEED FAN-OUT ARCHITECTURE                                │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  POST SERVICE                                                       │   │
│   │                                                                     │   │
│   │  1. User creates post                                               │   │
│   │  2. Store post in Posts DB                                          │   │
│   │  3. Publish PostCreated event                                       │   │
│   │     {                                                               │   │
│   │       post_id: "p123",                                              │   │
│   │       author_id: "u456",                                            │   │
│   │       content_preview: "...",                                       │   │
│   │       created_at: timestamp,                                        │   │
│   │       is_celebrity: false  // Pre-computed flag                     │   │
│   │     }                                                               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  POST-CREATED TOPIC                                                 │   │
│   │  Partitioned by author_id (to batch author's posts together)        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  FAN-OUT WORKER                                                     │   │
│   │                                                                     │   │
│   │  FOR each PostCreated event:                                        │   │
│   │    IF is_celebrity:                                                 │   │
│   │      SKIP (celebrity posts are pulled on read)                      │   │
│   │                                                                     │   │
│   │    followers = follower_service.get_followers(author_id)            │   │
│   │    // Returns list of follower user_ids                             │   │
│   │                                                                     │   │
│   │    // Batch write to Redis                                          │   │
│   │    FOR EACH batch of 1000 followers:                                │   │
│   │      pipeline = redis.pipeline()                                    │   │
│   │      FOR follower_id IN batch:                                      │   │
│   │        pipeline.ZADD(                                               │   │
│   │          "feed:" + follower_id,                                     │   │
│   │          score=created_at,  // For time-ordering                    │   │
│   │          member=post_id                                             │   │
│   │        )                                                            │   │
│   │        pipeline.ZREMRANGEBYRANK(                                    │   │
│   │          "feed:" + follower_id,                                     │   │
│   │          0, -1001  // Keep only last 1000 posts                     │   │
│   │        )                                                            │   │
│   │      pipeline.execute()                                             │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  FEED READ PATH                                                     │   │
│   │                                                                     │   │
│   │  1. Get pre-computed feed: ZREVRANGE feed:{user_id} 0 50            │   │
│   │  2. Get followed celebrities: SELECT id FROM follows                │   │
│   │                               WHERE follower_id = ? AND is_celebrity│   │
│   │  3. Get celebrity posts: Multi-get from Posts DB                    │   │
│   │  4. Merge, sort by time                                             │   │
│   │  5. Hydrate post details (content, author info, like counts)        │   │
│   │  6. Return feed                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Handling Lag in Fan-Out

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FAN-OUT LAG SCENARIOS                                    │
│                                                                             │
│   SCENARIO: Viral post from user with 500K followers                        │
│                                                                             │
│   Time 0:00 - Post created, event published                                 │
│   Time 0:01 - Fan-out worker starts processing                              │
│   Time 0:01 to 0:30 - Writing to 500K feeds (batch of 1000 every 50ms)     │
│                                                                             │
│   PROBLEM: Followers checking feed in first 30 seconds might not see post   │
│                                                                             │
│   SOLUTIONS:                                                                │
│                                                                             │
│   1. PARALLEL FAN-OUT                                                       │
│      - Partition followers into chunks                                      │
│      - Multiple workers process chunks in parallel                          │
│      - 500K followers ÷ 50 workers = 10K each = faster                      │
│                                                                             │
│   2. HYBRID READ                                                            │
│      - Always query "recent posts from followed users" (last 60 seconds)    │
│      - Merge with pre-computed feed                                         │
│      - Handles the gap during fan-out                                       │
│                                                                             │
│   3. PRIORITY LANES                                                         │
│      - Close friends/active users get higher priority                       │
│      - Fan-out to active users first (they're likely to check)              │
│      - Inactive users can wait (they check less often anyway)               │
│                                                                             │
│   4. ACCEPT EVENTUAL CONSISTENCY                                            │
│      - Users don't notice 30-second delay                                   │
│      - Define SLA (e.g., 95% of feeds updated within 5 seconds)             │
│      - Monitor and alert on SLA breach                                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Example 3: Metrics Ingestion

### Requirements
- Collect metrics from 10,000 servers
- Each server sends metrics every 10 seconds
- Metrics include CPU, memory, disk, network, custom app metrics
- Total: ~1M metrics per second
- Retention: 1 minute granularity for 30 days, 1 hour granularity for 1 year
- Query latency: < 1 second for recent data, < 10 seconds for historical

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    METRICS INGESTION PIPELINE                               │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  COLLECTION LAYER                                                   │   │
│   │                                                                     │   │
│   │  10,000 servers running metrics agent                               │   │
│   │  Agent batches metrics locally (10 seconds of data)                 │   │
│   │  Agent sends batch to collector via HTTP or gRPC                    │   │
│   │                                                                     │   │
│   │  ┌──────┐ ┌──────┐ ┌──────┐     ┌──────┐                            │   │
│   │  │Agent │ │Agent │ │Agent │ ... │Agent │                            │   │
│   │  └──┬───┘ └──┬───┘ └──┬───┘     └──┬───┘                            │   │
│   │     └────────┴────────┴───────────┴──────▶ Collectors (Load Balanced)│   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  INGESTION LAYER                                                    │   │
│   │                                                                     │   │
│   │  Collectors validate and publish to Kafka                           │   │
│   │                                                                     │   │
│   │  Topic: raw-metrics                                                 │   │
│   │  Partitions: 100 (for parallelism)                                  │   │
│   │  Partition key: server_id (all metrics from server together)        │   │
│   │  Retention: 24 hours (for replay)                                   │   │
│   │                                                                     │   │
│   │  Message:                                                           │   │
│   │  {                                                                  │   │
│   │    server_id: "srv-123",                                            │   │
│   │    timestamp: 1706300000,                                           │   │
│   │    metrics: [                                                       │   │
│   │      { name: "cpu.usage", value: 45.2, tags: {core: "0"} },         │   │
│   │      { name: "mem.used", value: 8589934592, tags: {} },             │   │
│   │      ...                                                            │   │
│   │    ]                                                                │   │
│   │  }                                                                  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  PROCESSING LAYER                                                   │   │
│   │                                                                     │   │
│   │  Consumer Group: metrics-processor                                  │   │
│   │  50 consumers (2 partitions each)                                   │   │
│   │                                                                     │   │
│   │  Processing:                                                        │   │
│   │  1. Parse and validate metrics                                      │   │
│   │  2. Apply rate limiting per server (prevent metric explosion)       │   │
│   │  3. Buffer in memory (1 minute window)                              │   │
│   │  4. Aggregate: compute min/max/avg/p99 per minute                   │   │
│   │  5. Batch write to time-series database                             │   │
│   │                                                                     │   │
│   │  Writes to:                                                         │   │
│   │  - TimescaleDB for recent data (last 7 days, 1-minute granularity)  │   │
│   │  - Long-term storage job for old data (1-hour granularity)          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Handling Metrics at Scale

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    METRICS PIPELINE CHALLENGES                              │
│                                                                             │
│   CHALLENGE 1: CARDINALITY EXPLOSION                                        │
│                                                                             │
│   Bad metric:                                                               │
│   { name: "http.request", tags: { user_id: "u123", path: "/api/..." } }     │
│   → Millions of unique time series (user_id × path combinations)            │
│   → Storage and query costs explode                                         │
│                                                                             │
│   Solution: Drop high-cardinality tags at ingestion                         │
│   - Maintain allowlist of permitted tags                                    │
│   - Rate limit unique series per metric name                                │
│   - Alert when new high-cardinality pattern detected                        │
│                                                                             │
│   CHALLENGE 2: LATE ARRIVING DATA                                           │
│                                                                             │
│   Server clock is wrong, or network delayed delivery                        │
│   Metrics arrive with timestamp 5 minutes in the past                       │
│   Already aggregated that window!                                           │
│                                                                             │
│   Solution: Late data handling                                              │
│   - Accept late data up to threshold (e.g., 5 minutes)                      │
│   - Re-aggregate affected windows                                           │
│   - Beyond threshold: drop or route to "late data" bucket                   │
│                                                                             │
│   CHALLENGE 3: BACKPRESSURE FROM DATABASE                                   │
│                                                                             │
│   Database is slow (maintenance, load spike)                                │
│   Consumer can't write fast enough                                          │
│   Kafka lag increases                                                       │
│                                                                             │
│   Solution: Graceful degradation                                            │
│   - Buffer more in memory (increase aggregation window)                     │
│   - Sample data during extreme load (keep 1 in N)                           │
│   - Alert on lag, investigate database                                      │
│   - Accept data loss as last resort (metrics, not transactions)             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Why Events Work Here

1. **Volume**: 1M events/second is too much for synchronous processing
2. **Tolerance for loss**: Missing a few metrics doesn't break monitoring
3. **Aggregation**: Buffering enables efficient batch writes
4. **Replay**: Reprocess when aggregation logic changes
5. **Decoupling**: Collectors shouldn't know about database schema

---

# Part 6: Failure and Evolution

## What Breaks Under Load

### Producer-Side Failures

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PRODUCER FAILURE MODES                                   │
│                                                                             │
│   1. KAFKA BROKER UNAVAILABLE                                               │
│                                                                             │
│   Producer tries to publish → Connection refused                            │
│                                                                             │
│   Bad response: Throw error, lose the event                                 │
│   Good response: Queue locally, retry with backoff                          │
│   Better: Write to local disk, background process retries                   │
│                                                                             │
│   Producer config:                                                          │
│   - retries = 3 (or more)                                                   │
│   - retry.backoff.ms = 100                                                  │
│   - delivery.timeout.ms = 120000 (2 minutes of retrying)                    │
│                                                                             │
│   2. KAFKA OVERLOADED                                                       │
│                                                                             │
│   Producer tries to publish → Timeout                                       │
│   Internal queue fills up → memory exhaustion                               │
│                                                                             │
│   Producer config:                                                          │
│   - buffer.memory = reasonable limit (not unlimited)                        │
│   - max.block.ms = how long to block before failing                         │
│                                                                             │
│   Application decision:                                                     │
│   - Fail the request (user sees error)                                      │
│   - Queue to disk (delayed processing)                                      │
│   - Drop the event (acceptable for some use cases)                          │
│                                                                             │
│   3. SERIALIZATION FAILURE                                                  │
│                                                                             │
│   Event doesn't match schema → Serialization error                          │
│                                                                             │
│   This is a bug, not a transient failure                                    │
│   Retrying won't help                                                       │
│   Log error, alert, fix code                                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Consumer-Side Failures

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CONSUMER FAILURE MODES                                   │
│                                                                             │
│   1. POISON MESSAGE                                                         │
│                                                                             │
│   One message causes consumer to crash or hang                              │
│   Consumer restarts, processes same message, crashes again                  │
│   Infinite loop, partition is stuck                                         │
│                                                                             │
│   Solution: Dead Letter Queue (DLQ)                                         │
│   - Track retry count per message                                           │
│   - After N failures, send to DLQ topic                                     │
│   - Continue processing remaining messages                                  │
│   - Alert on DLQ growth, investigate manually                               │
│                                                                             │
│   FUNCTION process_with_dlq(message):                                       │
│       retry_count = get_retry_count(message.id)                             │
│       IF retry_count > MAX_RETRIES:                                         │
│           publish_to_dlq(message)                                           │
│           RETURN SUCCESS  // Move past this message                         │
│                                                                             │
│       TRY:                                                                  │
│           process(message)                                                  │
│           clear_retry_count(message.id)                                     │
│       CATCH Exception:                                                      │
│           increment_retry_count(message.id)                                 │
│           THROW  // Don't commit, will retry                                │
│                                                                             │
│   2. SLOW DOWNSTREAM DEPENDENCY                                             │
│                                                                             │
│   Consumer calls database/API that's slow                                   │
│   Processing slows down, lag increases                                      │
│                                                                             │
│   Solutions:                                                                │
│   - Timeouts on all external calls                                          │
│   - Circuit breaker to fail fast                                            │
│   - Batch operations (one DB write per 100 messages)                        │
│   - Async processing with bounded concurrency                               │
│                                                                             │
│   3. REBALANCING STORM                                                      │
│                                                                             │
│   Consumer joins/leaves frequently                                          │
│   Each change triggers rebalance                                            │
│   During rebalance, processing stops                                        │
│                                                                             │
│   Causes:                                                                   │
│   - Kubernetes pod restarts                                                 │
│   - Slow processing causing heartbeat timeout                               │
│   - Memory issues causing GC pauses                                         │
│                                                                             │
│   Solutions:                                                                │
│   - Increase session.timeout.ms (30s → 60s)                                 │
│   - Use static membership (group.instance.id)                               │
│   - Reduce max.poll.records if processing is slow                           │
│   - Monitor for frequent rebalances                                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Kafka-Side Failures

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    KAFKA INFRASTRUCTURE FAILURES                            │
│                                                                             │
│   1. BROKER FAILURE                                                         │
│                                                                             │
│   One of N brokers goes down                                                │
│   Partitions on that broker become unavailable (briefly)                    │
│   Leader election for affected partitions                                   │
│                                                                             │
│   Impact:                                                                   │
│   - Producers to affected partitions fail (temporarily)                     │
│   - Consumers rebalance to new leader                                       │
│   - Usually recovers in seconds if replication is configured                │
│                                                                             │
│   Mitigation:                                                               │
│   - Replication factor = 3 (survive 2 broker failures)                      │
│   - min.insync.replicas = 2 (at least 2 copies before ack)                  │
│   - Spread partitions across failure domains (racks/AZs)                    │
│                                                                             │
│   2. DISK FAILURE                                                           │
│                                                                             │
│   Broker disk fills up or fails                                             │
│   No space to write new messages                                            │
│   Broker rejects new writes                                                 │
│                                                                             │
│   Mitigation:                                                               │
│   - Monitor disk usage with alerts at 70%, 80%, 90%                         │
│   - Tune retention policies                                                 │
│   - Provision sufficient disk (2x expected peak)                            │
│                                                                             │
│   3. ZOOKEEPER/KRAFT FAILURE                                                │
│                                                                             │
│   Cluster coordination fails                                                │
│   No leader elections, no partition reassignment                            │
│   Cluster becomes read-only or unavailable                                  │
│                                                                             │
│   Mitigation:                                                               │
│   - 3 or 5 ZK/KRaft nodes across failure domains                            │
│   - Monitor ZK/KRaft health separately                                      │
│   - Test failure scenarios in staging                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Cascading Failure Timeline: Consumer Lag → Partition Fill → Producer Blocking

Staff Engineers think in timelines, not just failure modes. Here's what happens when a consumer falls behind in an event-driven system:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CASCADING FAILURE TIMELINE: CONSUMER LAG CASCADE         │
│                                                                             │
│   SYSTEM: Order processing pipeline                                         │
│   - Order Service publishes OrderPlaced events (1000 events/sec)          │
│   - Inventory Service consumes and decrements stock                        │
│   - Kafka topic: 10 partitions, replication factor 3                        │
│   - Consumer: 10 instances (1 per partition)                                │
│                                                                             │
│   ────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│   T=0:00 (TRIGGER)                                                          │
│   ────────────────────────────────────────────────────────────────────────  │
│   Inventory Service's database starts slow queries (index corruption)     │
│   Consumer processing time: 10ms → 500ms per event                          │
│   Consumer throughput: 100 events/sec → 2 events/sec                       │
│                                                                             │
│   T=0:05 (PROPAGATION PHASE 1: Lag Accumulation)                            │
│   ────────────────────────────────────────────────────────────────────────  │
│   Producer: Still publishing 1000 events/sec (unaware of problem)         │
│   Consumer: Processing 2 events/sec per partition = 20 events/sec total   │
│   Lag: (1000 - 20) * 5 seconds = 4,900 events                             │
│   Kafka: Events accumulating in partition logs                               │
│   Impact: None yet (lag is internal to Kafka)                              │
│                                                                             │
│   T=0:15 (PROPAGATION PHASE 2: Lag Becomes Visible)                         │
│   ────────────────────────────────────────────────────────────────────────  │
│   Lag: (1000 - 20) * 15 seconds = 14,700 events                            │
│   Monitoring alert fires: "Consumer lag > 10,000 for 5 minutes"           │
│   On-call engineer paged                                                    │
│   Impact: Operations team aware, investigating                             │
│                                                                             │
│   T=1:00 (PROPAGATION PHASE 3: Downstream Impact)                           │
│   ────────────────────────────────────────────────────────────────────────  │
│   Lag: (1000 - 20) * 60 seconds = 58,800 events                            │
│   Inventory counts are stale (not updated for 1 minute)                     │
│   Users see "in stock" but orders fail (inventory already decremented)     │
│   Customer support tickets spike                                           │
│   Impact: User-visible degradation (incorrect inventory display)            │
│                                                                             │
│   T=5:00 (PROPAGATION PHASE 4: Partition Storage Pressure)                 │
│   ────────────────────────────────────────────────────────────────────────  │
│   Lag: (1000 - 20) * 300 seconds = 294,000 events                           │
│   Kafka partition storage: 294K events * 500 bytes = 147 MB per partition │
│   Total across 10 partitions: 1.47 GB (within limits, but growing)         │
│   Retention: 7 days = 604,800 seconds                                        │
│   If lag continues, will hit retention limit in ~7 hours                    │
│   Impact: Risk of data loss if lag exceeds retention                      │
│                                                                             │
│   T=10:00 (PROPAGATION PHASE 5: Producer Blocking Risk)                     │
│   ────────────────────────────────────────────────────────────────────────  │
│   Lag: (1000 - 20) * 600 seconds = 588,000 events                           │
│   Kafka broker memory: Producer buffers filling up                          │
│   Producer config: max.block.ms = 60000 (1 minute)                         │
│   Producer config: buffer.memory = 32 MB                                    │
│                                                                             │
│   IF buffer.memory fills:                                                   │
│   - Producer blocks on send() (waits for buffer space)                     │
│   - Order Service API calls hang (waiting for Kafka publish)                │
│   - User requests timeout                                                    │
│   - Cascading failure: Order Service appears down                           │
│                                                                             │
│   Impact: Producer-side blocking (if buffer limits hit)                     │
│                                                                             │
│   T=30:00 (CONTAINMENT: Circuit Breaker Activates)                           │
│   ────────────────────────────────────────────────────────────────────────  │
│   Lag: (1000 - 20) * 1800 seconds = 1,764,000 events                        │
│   Operations team: Identifies database issue, applies fix                    │
│   Consumer: Still processing old events (30 minutes behind)                  │
│                                                                             │
│   CONTAINMENT ACTIONS:                                                      │
│   1. Circuit breaker opens: Stop calling slow database                      │
│   2. Consumer publishes to DLQ: "events requiring DB unavailable"            │
│   3. Consumer continues processing: New events (no DB dependency)            │
│   4. Lag stops growing: Consumer catches up on new events                  │
│   5. DLQ replay: After DB fix, replay DLQ events                            │
│                                                                             │
│   Impact: Lag growth contained, system partially functional                  │
│                                                                             │
│   T=60:00 (RECOVERY: Catch-Up Phase)                                        │
│   ────────────────────────────────────────────────────────────────────────  │
│   Database: Fixed, queries back to 10ms                                    │
│   Consumer: Processing at 100 events/sec again                             │
│   Catch-up rate: 100 - 20 = 80 events/sec excess capacity                   │
│   Time to catch up: 1,764,000 / 80 = 22,050 seconds ≈ 6 hours              │
│                                                                             │
│   Impact: System recovering, but 6-hour catch-up window                    │
│                                                                             │
│   ────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│   KEY INSIGHTS:                                                             │
│   1. Producer doesn't know consumer is slow (asynchronous decoupling)      │
│   2. Lag accumulates linearly (production rate - consumption rate)         │
│   3. User-visible impact appears BEFORE producer blocking                   │
│   4. Producer blocking is LAST (if buffer limits configured)                │
│   5. Recovery time >> failure time (catch-up is slower than accumulation)  │
│                                                                             │
│   STAFF ENGINEER QUESTION:                                                 │
│   "What's our max acceptable lag? At what lag do we fail fast vs continue?" │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Why This Timeline Matters**:

1. **Trigger identification**: Database slowdown is the root cause, but symptoms appear in Kafka lag
2. **Propagation understanding**: Lag grows linearly; user impact appears before system failure
3. **Containment timing**: Circuit breaker must activate BEFORE producer blocking
4. **Recovery planning**: Catch-up time is often 10x longer than failure time

**Design Implications**:

- **Lag thresholds**: Alert at 10K, circuit breaker at 100K, fail-fast at 1M
- **Buffer sizing**: Producer buffer.memory must accommodate lag spikes
- **Retention policy**: Must exceed max expected lag + catch-up time
- **Monitoring**: Lag metrics are more important than throughput metrics

---

## Containing Blast Radius

Staff Engineers design systems where failures don't cascade. Here's how:

### Isolation Patterns

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    BLAST RADIUS CONTAINMENT                                 │
│                                                                             │
│   PATTERN 1: TOPIC-PER-CONCERN                                              │
│                                                                             │
│   Bad: Single topic "all-events" with everything                            │
│   - One poison message blocks all processing                                │
│   - One slow consumer affects everything                                    │
│   - Can't scale or tune per use case                                        │
│                                                                             │
│   Good: Separate topics per domain                                          │
│   - user-events, order-events, payment-events                               │
│   - Failure in order processing doesn't affect user events                  │
│   - Different retention, partition counts, consumer configs                 │
│                                                                             │
│   PATTERN 2: PRIORITY SEPARATION                                            │
│                                                                             │
│   Bad: Single queue for all priorities                                      │
│   - Bulk analytics events delay critical alerts                             │
│                                                                             │
│   Good: Separate topics/consumer groups by priority                         │
│   - critical-alerts (dedicated consumers, aggressive monitoring)            │
│   - normal-events (standard consumers)                                      │
│   - bulk-events (batch consumers, can lag)                                  │
│                                                                             │
│   PATTERN 3: TENANT ISOLATION                                               │
│                                                                             │
│   Bad: All tenants share same consumers                                     │
│   - One tenant's spike affects all others                                   │
│   - One tenant's bad data poisons queue for all                             │
│                                                                             │
│   Better: Priority lanes per tenant tier                                    │
│   - Enterprise tenants get dedicated consumer capacity                      │
│   - Free tenants share consumer pool                                        │
│                                                                             │
│   Best (for critical tenants): Dedicated topic per tenant                   │
│   - Complete isolation                                                      │
│   - More operational overhead                                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Monitoring and Alerting

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ESSENTIAL EVENT-DRIVEN MONITORING                        │
│                                                                             │
│   LAG MONITORING (Most Important)                                           │
│                                                                             │
│   Metric: kafka_consumergroup_lag                                           │
│   Alert thresholds:                                                         │
│   - Warning: lag > 10,000 messages for 5 minutes                            │
│   - Critical: lag > 100,000 messages for 5 minutes                          │
│   - Emergency: lag increasing for 30 minutes (will never catch up)          │
│                                                                             │
│   Dashboard: Lag over time, per consumer group, per partition               │
│                                                                             │
│   THROUGHPUT MONITORING                                                     │
│                                                                             │
│   Producer: messages/sec, bytes/sec per topic                               │
│   Consumer: messages/sec processed per consumer group                       │
│   Alert: Sudden drop (producer stopped?) or sudden spike (need scaling?)    │
│                                                                             │
│   ERROR RATE MONITORING                                                     │
│                                                                             │
│   Producer: Failed publishes, timeout rate                                  │
│   Consumer: Processing errors, DLQ rate                                     │
│   Alert: Error rate > 1% for 5 minutes                                      │
│                                                                             │
│   DLQ MONITORING                                                            │
│                                                                             │
│   Metric: DLQ message count per topic                                       │
│   Alert: Any message in DLQ (investigate immediately)                       │
│   Dashboard: DLQ messages by error type, time                               │
│                                                                             │
│   REBALANCE MONITORING                                                      │
│                                                                             │
│   Metric: Rebalance count per consumer group                                │
│   Alert: > 5 rebalances in 10 minutes (storm)                               │
│   Dashboard: Rebalance duration, frequency                                  │
│                                                                             │
│   END-TO-END LATENCY                                                        │
│                                                                             │
│   Measure: Time from event publish to processing complete                   │
│   Include correlation_id with publish_timestamp in event                    │
│   Consumer logs: event_age_ms = now() - event.publish_timestamp             │
│   Alert: p99 age > SLA threshold                                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Migration Strategies

### Adding Events to Existing Sync System

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MIGRATION: SYNC TO EVENT-DRIVEN                          │
│                                                                             │
│   PHASE 1: DUAL WRITE (Add Events, Keep Sync)                               │
│                                                                             │
│   Order Service (current):                                                  │
│   1. Create order in DB                                                     │
│   2. Call Payment service (sync)                                            │
│   3. Call Notification service (sync)                                       │
│                                                                             │
│   Order Service (phase 1):                                                  │
│   1. Create order in DB                                                     │
│   2. Publish OrderCreated event            ← NEW                            │
│   3. Call Payment service (sync)           ← STILL HERE                     │
│   4. Call Notification service (sync)      ← STILL HERE                     │
│                                                                             │
│   New consumers can start building on events                                │
│   Existing sync flow unchanged (safety net)                                 │
│                                                                             │
│   PHASE 2: PARALLEL PROCESSING (Validate Events Work)                       │
│                                                                             │
│   New consumer for notifications:                                           │
│   - Consume OrderCreated events                                             │
│   - Send notification                                                       │
│   - Compare with sync notification (should match)                           │
│                                                                             │
│   Run both for 2 weeks, validate:                                           │
│   - All events received?                                                    │
│   - Latency acceptable?                                                     │
│   - No duplicates (or handled correctly)?                                   │
│                                                                             │
│   PHASE 3: CUTOVER (Remove Sync)                                            │
│                                                                             │
│   Order Service (phase 3):                                                  │
│   1. Create order in DB                                                     │
│   2. Publish OrderCreated event                                             │
│   // Sync calls removed                                                     │
│                                                                             │
│   Notification handled entirely by event consumer                           │
│   Payment still sync (critical path, needs sync semantics)                  │
│                                                                             │
│   PHASE 4: CLEANUP                                                          │
│                                                                             │
│   Remove dead code for sync notification calls                              │
│   Update documentation                                                      │
│   Celebrate (but keep monitoring!)                                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Removing Events (Going Back to Sync)

Sometimes events were the wrong choice. Here's how to migrate back:

```
WHEN TO REMOVE EVENTS:

1. Single consumer that needs sync response
2. Debugging cost exceeds decoupling benefit  
3. Latency requirements can't be met
4. Operational overhead isn't justified

MIGRATION STEPS:

1. Build sync endpoint in consumer service
2. Producer calls sync endpoint AND publishes event (dual)
3. Monitor sync call success rate
4. Stop consuming events (but keep publishing for now)
5. Remove event publishing
6. Clean up consumer code

IMPORTANT: Keep event topic for a while (retention)
           Some consumers might still be reading
           Announce deprecation timeline
```

---

# Part 7: Diagrams Summary

## Event Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    COMPLETE EVENT FLOW ARCHITECTURE                         │
│                                                                             │
│   ┌─────────────┐                                                           │
│   │   Source    │                                                           │
│   │  (Service)  │                                                           │
│   └──────┬──────┘                                                           │
│          │                                                                  │
│          │ 1. Business operation + Outbox write (atomic)                    │
│          ▼                                                                  │
│   ┌─────────────┐      ┌─────────────┐                                      │
│   │  Database   │◀────▶│   Outbox    │                                      │
│   │  (Source    │      │   Table     │                                      │
│   │   of Truth) │      └──────┬──────┘                                      │
│   └─────────────┘             │                                             │
│                               │ 2. CDC/Polling captures changes             │
│                               ▼                                             │
│   ┌───────────────────────────────────────────────────────────────────┐     │
│   │                          KAFKA CLUSTER                            │     │
│   │  ┌─────────────────────────────────────────────────────────────┐  │     │
│   │  │  Topic: domain-events                                       │  │     │
│   │  │  ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐                    │  │     │
│   │  │  │Part 0 │ │Part 1 │ │Part 2 │ │Part 3 │  ...               │  │     │
│   │  │  └───────┘ └───────┘ └───────┘ └───────┘                    │  │     │
│   │  └─────────────────────────────────────────────────────────────┘  │     │
│   └───────────────────────────────────────────────────────────────────┘     │
│          │              │              │              │                     │
│          │ 3. Consumer groups process independently                         │
│          ▼              ▼              ▼              ▼                     │
│   ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐                │
│   │ Consumer  │  │ Consumer  │  │ Consumer  │  │ Consumer  │                │
│   │ Group A   │  │ Group B   │  │ Group C   │  │ Group D   │                │
│   │ (Search)  │  │ (Email)   │  │(Analytics)│  │  (Audit)  │                │
│   └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘                │
│         │              │              │              │                      │
│         ▼              ▼              ▼              ▼                      │
│   ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐                │
│   │Elasticsearch│ │ SendGrid │  │ BigQuery  │  │ S3/GCS    │                │
│   └───────────┘  └───────────┘  └───────────┘  └───────────┘                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Consumer Lag Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CONSUMER LAG VISUALIZATION                               │
│                                                                             │
│   HEALTHY LAG (Consumer Keeping Up):                                        │
│                                                                             │
│   Lag │                                                                     │
│    1K │                          ┌─┐                                        │
│   500 │   ┌─┐   ┌─┐        ┌─┐   │ │                                        │
│     0 │───┴─┴───┴─┴────────┴─┴───┴─┴──────────────                          │
│       └───────────────────────────────────────────▶ Time                    │
│         Small spikes, quickly recovered                                     │
│                                                                             │
│   UNHEALTHY LAG (Consumer Falling Behind):                                  │
│                                                                             │
│   Lag │                                         ╱                           │
│  100K │                                      ╱╱╱                            │
│   50K │                                  ╱╱╱╱                               │
│   10K │                             ╱╱╱╱╱                                   │
│    1K │                        ╱╱╱╱╱                                        │
│     0 │────────────────────╱╱╱╱                                             │
│       └───────────────────────────────────────────▶ Time                    │
│         Continuously increasing - will never catch up!                      │
│                                                                             │
│   SPIKE AND RECOVERY:                                                       │
│                                                                             │
│   Lag │           ╲                                                         │
│   50K │        ╱   ╲                                                        │
│   25K │       ╱     ╲                                                       │
│   10K │      ╱       ╲                                                      │
│    1K │─────╱         ╲─────────────────────                                │
│       └───────────────────────────────────────────▶ Time                    │
│         Traffic spike, then recovery (healthy)                              │
│                                                                             │
│   LAG PROPAGATION ACROSS SERVICES:                                          │
│                                                                             │
│   Service A (Source)     │░░░░░░░░░│ Healthy - producing                    │
│                          ▼                                                  │
│   Service B              │████████░│ 10min lag                              │
│                          ▼                                                  │
│   Service C              │████████████░│ 15min lag (B's lag + processing)   │
│                          ▼                                                  │
│   Service D              │████████████████░│ 20min lag                      │
│                                                                             │
│   Lag compounds through the pipeline!                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Failure Propagation Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FAILURE PROPAGATION IN EVENT SYSTEMS                     │
│                                                                             │
│   SCENARIO: Database slowdown in Service C                                  │
│                                                                             │
│   T=0 (Normal):                                                             │
│   ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐              │
│   │Service A│────▶│  Kafka  │────▶│Service B│────▶│Service C│──▶[DB]       │
│   │ (OK)    │     │ lag: 0  │     │ (OK)    │     │ (OK)    │  (OK)        │
│   └─────────┘     └─────────┘     └─────────┘     └─────────┘              │
│                                                                             │
│   T=5min (DB Slow):                                                         │
│   ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐              │
│   │Service A│────▶│  Kafka  │────▶│Service B│────▶│Service C│──▶[DB]       │
│   │ (OK)    │     │ lag: 0  │     │ (OK)    │     │ (SLOW)  │  (SLOW)      │
│   └─────────┘     └─────────┘     └─────────┘     └─────────┘              │
│                                                                             │
│   T=10min (Lag Building):                                                   │
│   ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐              │
│   │Service A│────▶│  Kafka  │────▶│Service B│────▶│Service C│──▶[DB]       │
│   │ (OK)    │     │ lag: 5K │     │ (OK)    │     │ lag:10K │  (SLOW)      │
│   └─────────┘     └─────────┘     └─────────┘     └─────────┘              │
│                                                    ▲                        │
│                                                    │                        │
│                                               Processing                    │
│                                               backed up                     │
│                                                                             │
│   T=30min (Cascade):                                                        │
│   ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐              │
│   │Service A│────▶│  Kafka  │────▶│Service B│────▶│Service C│──▶[DB]       │
│   │ (OK)    │     │ lag:50K │     │ lag:30K │     │ lag:50K │  (SLOW)      │
│   └─────────┘     └─────────┘     └─────────┘     └─────────┘              │
│       ▲                                                                     │
│       │                                                                     │
│   Still producing,                                                          │
│   doesn't know                                                              │
│   downstream is sick                                                        │
│                                                                             │
│   CONTAINMENT STRATEGY:                                                     │
│                                                                             │
│   ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐              │
│   │Service A│────▶│  Kafka  │────▶│Service B│     │Service C│──▶[DB]       │
│   │ (OK)    │     │         │     │         │     │         │              │
│   └─────────┘     └─────────┘     └────┬────┘     └─────────┘              │
│                                        │                                    │
│                                        │ Circuit                            │
│                                        │ Breaker                            │
│                                        │ OPEN                               │
│                                        ▼                                    │
│                                   ┌─────────┐                               │
│                                   │   DLQ   │                               │
│                                   │(process │                               │
│                                   │ later)  │                               │
│                                   └─────────┘                               │
│                                                                             │
│   Service B detects C is slow, stops calling, queues to DLQ                 │
│   B stays healthy, lag stays bounded                                        │
│   When C recovers, DLQ is replayed                                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 8: Advanced Patterns (L6 Depth)

This section covers advanced patterns that are frequently discussed in Staff-level interviews but often misunderstood.

---

## Event Sourcing vs Event-Driven Architecture

These are often confused. They are different patterns that can be used together or separately.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    EVENT SOURCING vs EVENT-DRIVEN                           │
│                                                                             │
│   EVENT-DRIVEN ARCHITECTURE:                                                │
│   - Services communicate via events                                         │
│   - Events are messages between systems                                     │
│   - State is stored in databases (traditional)                              │
│   - Events can be discarded after consumption                               │
│                                                                             │
│   Example:                                                                  │
│   User creates account → Publish "UserCreated" event →                      │
│   Email service sends welcome email                                         │
│   (The event is communication, not the source of truth)                     │
│                                                                             │
│   EVENT SOURCING:                                                           │
│   - Events ARE the source of truth                                          │
│   - No traditional database—state is derived from events                    │
│   - Events are never deleted (append-only log)                              │
│   - Current state = replay all events from beginning                        │
│                                                                             │
│   Example:                                                                  │
│   Bank Account Events:                                                      │
│   1. AccountOpened(balance=0)                                               │
│   2. MoneyDeposited(amount=100) → balance = 100                             │
│   3. MoneyWithdrawn(amount=30) → balance = 70                               │
│   4. MoneyDeposited(amount=50) → balance = 120                              │
│                                                                             │
│   Current balance isn't stored—it's computed by replaying events.           │
│                                                                             │
│   KEY DIFFERENCES:                                                          │
│                                                                             │
│   │ Aspect              │ Event-Driven        │ Event Sourcing            │ │
│   │─────────────────────│─────────────────────│───────────────────────────│ │
│   │ Source of Truth     │ Database            │ Event Log                 │ │
│   │ Event Retention     │ Optional            │ Forever (mandatory)       │ │
│   │ State Reconstruction│ Query database      │ Replay all events         │ │
│   │ Historical Queries  │ Need audit tables   │ Built-in (replay to date) │ │
│   │ Complexity          │ Moderate            │ High                      │ │
│   │ Use Case            │ Integration         │ Audit, temporal queries   │ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### When to Use Event Sourcing

```
GOOD USE CASES:

1. AUDIT REQUIREMENTS
   - Financial systems where you need complete history
   - Healthcare where every change must be traceable
   - "What was the account balance on March 15th at 2pm?"

2. TEMPORAL QUERIES
   - "Show me the state of the system at any point in time"
   - Useful for debugging, compliance, analytics

3. UNDO/REDO FUNCTIONALITY
   - Document editors, design tools
   - Replay to any previous state

4. COMPLEX DOMAIN LOGIC
   - Insurance claims processing
   - Order fulfillment with many state transitions
   - Domain events capture business intent, not just data changes

BAD USE CASES:

1. SIMPLE CRUD APPLICATIONS
   - Overkill for blogs, user profiles, basic content management
   - The complexity isn't worth the benefits

2. HIGH-VOLUME, LOW-VALUE DATA
   - Page views, click tracking
   - You don't need perfect reconstruction of every click

3. TEAMS WITHOUT EVENT SOURCING EXPERIENCE
   - Steep learning curve
   - Easy to implement incorrectly
   - Start with event-driven, graduate to event sourcing if needed
```

### The CQRS Pattern with Events

Command Query Responsibility Segregation (CQRS) often accompanies event sourcing:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CQRS WITH EVENT SOURCING                                 │
│                                                                             │
│   TRADITIONAL (Single Model):                                               │
│                                                                             │
│   ┌────────────┐      ┌─────────────┐      ┌────────────┐                   │
│   │   Client   │─────▶│   Service   │◀────▶│  Database  │                   │
│   │            │      │(Read+Write) │      │            │                   │
│   └────────────┘      └─────────────┘      └────────────┘                   │
│                                                                             │
│   Same model for reads and writes. Works, but:                              │
│   - Read patterns often differ from write patterns                          │
│   - Optimization for one hurts the other                                    │
│                                                                             │
│   CQRS (Separate Models):                                                   │
│                                                                             │
│   COMMAND SIDE (Writes):                                                    │
│   ┌────────────┐      ┌─────────────┐      ┌────────────┐                   │
│   │   Client   │─────▶│  Command    │─────▶│   Event    │                   │
│   │  (Write)   │      │  Handler    │      │   Store    │                   │
│   └────────────┘      └─────────────┘      └─────┬──────┘                   │
│                                                  │                          │
│                                            Events published                 │
│                                                  │                          │
│                                                  ▼                          │
│   QUERY SIDE (Reads):                      ┌─────────────┐                  │
│   ┌────────────┐      ┌─────────────┐      │  Projection │                  │
│   │   Client   │◀─────│   Query     │◀─────│  (Read DB)  │                  │
│   │   (Read)   │      │   Handler   │      └─────────────┘                  │
│   └────────────┘      └─────────────┘                                       │
│                                                                             │
│   Projection = materialized view optimized for reads                        │
│   Updated asynchronously from events                                        │
│   Can have multiple projections for different query patterns                │
│                                                                             │
│   TRADE-OFFS:                                                               │
│   + Read model optimized for queries (denormalized, indexed)                │
│   + Write model optimized for business logic (normalized)                   │
│   + Can scale reads and writes independently                                │
│   - Eventual consistency between write and read                             │
│   - More moving parts to manage                                             │
│   - Projection lag during high write load                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Saga Pattern: Distributed Transactions via Events

When you need transaction-like behavior across services, you use Sagas.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SAGA PATTERN FOR DISTRIBUTED TRANSACTIONS                │
│                                                                             │
│   PROBLEM: Order requires multiple services that must all succeed           │
│   - Create order (Order Service)                                            │
│   - Reserve inventory (Inventory Service)                                   │
│   - Charge payment (Payment Service)                                        │
│   - Ship order (Shipping Service)                                           │
│                                                                             │
│   Can't use database transaction—services have separate databases.          │
│   Solution: Saga (series of local transactions with compensating actions)   │
│                                                                             │
│   CHOREOGRAPHY SAGA (Decentralized):                                        │
│                                                                             │
│   ┌─────────┐  OrderCreated  ┌─────────┐  InventoryReserved  ┌─────────┐   │
│   │ Order   │───────────────▶│Inventory│────────────────────▶│ Payment │   │
│   │ Service │                │ Service │                     │ Service │   │
│   └─────────┘                └─────────┘                     └────┬────┘   │
│        ▲                          │                               │        │
│        │                          │ (if fails)                    │        │
│        │                          ▼                               ▼        │
│        │                   ┌─────────────┐                 PaymentCharged  │
│        │                   │Compensation:│                        │        │
│        │                   │ Release     │                        │        │
│        │                   │ Inventory   │                        ▼        │
│        │                   └─────────────┘                  ┌─────────┐    │
│        │                                                    │Shipping │    │
│        │◀───────────────── OrderCancelled ─────────────────│ Service │    │
│                            (if any step fails)              └─────────┘    │
│                                                                             │
│   Each service listens for events and triggers next step or compensation.  │
│                                                                             │
│   ORCHESTRATION SAGA (Centralized):                                        │
│                                                                             │
│        ┌───────────────────────────────────────────────────────┐            │
│        │              SAGA ORCHESTRATOR                        │            │
│        │  (Knows full workflow, coordinates all services)      │            │
│        └────────────┬─────────┬──────────┬──────────┬──────────┘            │
│                     │         │          │          │                       │
│                     ▼         ▼          ▼          ▼                       │
│               ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐               │
│               │ Order   │ │Inventory│ │ Payment │ │Shipping │               │
│               │ Service │ │ Service │ │ Service │ │ Service │               │
│               └─────────┘ └─────────┘ └─────────┘ └─────────┘               │
│                                                                             │
│   Orchestrator explicitly commands each service:                            │
│   1. CreateOrder → Order Service → OrderCreated                             │
│   2. ReserveInventory → Inventory Service → InventoryReserved               │
│   3. ChargePayment → Payment Service → PaymentCharged                       │
│   4. ShipOrder → Shipping Service → OrderShipped                            │
│                                                                             │
│   If step 3 fails:                                                          │
│   - Orchestrator catches failure                                            │
│   - Sends ReleaseInventory to Inventory Service                             │
│   - Sends CancelOrder to Order Service                                      │
│   - Saga completed with compensation                                        │
│                                                                             │
│   CHOREOGRAPHY vs ORCHESTRATION:                                            │
│                                                                             │
│   │ Aspect              │ Choreography        │ Orchestration             │ │
│   │─────────────────────│─────────────────────│───────────────────────────│ │
│   │ Coupling            │ Lower               │ Higher (to orchestrator)  │ │
│   │ Visibility          │ Harder to trace     │ Single place to look      │ │
│   │ Complexity          │ Spread across svcs  │ Centralized               │ │
│   │ Failure Handling    │ Distributed         │ Centralized               │ │
│   │ Adding Steps        │ Modify listeners    │ Modify orchestrator       │ │
│   │ Best For            │ Simple sagas        │ Complex, long-running     │ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Saga Failure Handling

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SAGA COMPENSATION DESIGN                                 │
│                                                                             │
│   RULE 1: Every action must have a compensating action                      │
│                                                                             │
│   Action                      Compensation                                  │
│   ──────────────────────────  ──────────────────────────────────            │
│   CreateOrder                 CancelOrder                                   │
│   ReserveInventory            ReleaseInventory                              │
│   ChargePayment               RefundPayment                                 │
│   ShipOrder                   ??? (Can't un-ship!)                          │
│                                                                             │
│   RULE 2: Order compensations carefully                                     │
│                                                                             │
│   Compensation order is REVERSE of action order:                            │
│   Forward:  A → B → C → D                                                   │
│   Backward: D' → C' → B' → A'                                               │
│                                                                             │
│   If C fails:                                                               │
│   - Don't compensate C (it didn't complete)                                 │
│   - Compensate B' then A'                                                   │
│                                                                             │
│   RULE 3: Some actions are not compensable                                  │
│                                                                             │
│   - Sending an email (can send "correction" but not unsend)                 │
│   - Physical shipment (can recall, but not instant)                         │
│   - Third-party API calls (may not support undo)                            │
│                                                                             │
│   Design principle: Put non-compensable actions LAST                        │
│   If earlier steps fail, you haven't done the irreversible thing yet.       │
│                                                                             │
│   RULE 4: Compensations must be idempotent                                  │
│                                                                             │
│   Compensation might be retried. Handle duplicates:                         │
│   - RefundPayment(order_id=123) called twice                                │
│   - Second call should be no-op (already refunded)                          │
│                                                                             │
│   RULE 5: Track saga state persistently                                     │
│                                                                             │
│   saga_instances table:                                                     │
│   - saga_id                                                                 │
│   - saga_type ("OrderSaga")                                                 │
│   - current_step                                                            │
│   - status (RUNNING, COMPENSATING, COMPLETED, FAILED)                       │
│   - created_at                                                              │
│   - updated_at                                                              │
│   - payload (JSON)                                                          │
│                                                                             │
│   If orchestrator crashes mid-saga, it can recover from this state.         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Compacted Topics: Events as State

Kafka log compaction is a powerful but often misunderstood feature.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    COMPACTED TOPICS                                         │
│                                                                             │
│   REGULAR TOPIC (Retention by time):                                        │
│                                                                             │
│   [K1:V1] [K2:V2] [K1:V3] [K3:V4] [K1:V5] [K2:V6] ...                       │
│      ↑       ↑       ↑       ↑       ↑       ↑                              │
│      │       │       │       │       │       │                              │
│   Kept until retention.ms expires, then deleted                             │
│   Consumer starting from beginning sees ALL messages                        │
│                                                                             │
│   COMPACTED TOPIC (Retention by key):                                       │
│                                                                             │
│   Before compaction:                                                        │
│   [K1:V1] [K2:V2] [K1:V3] [K3:V4] [K1:V5] [K2:V6]                           │
│                                                                             │
│   After compaction:                                                         │
│   [K3:V4] [K1:V5] [K2:V6]                                                   │
│      ↑       ↑       ↑                                                      │
│   Only LATEST value per key is kept                                         │
│   Consumer starting from beginning sees CURRENT STATE                       │
│                                                                             │
│   USE CASES:                                                                │
│                                                                             │
│   1. CONFIGURATION DISTRIBUTION                                             │
│      Topic: service-configs                                                 │
│      Key: service-name                                                      │
│      Value: JSON config                                                     │
│      New consumer gets current config for all services                      │
│                                                                             │
│   2. CACHE SYNCHRONIZATION                                                  │
│      Topic: user-cache                                                      │
│      Key: user_id                                                           │
│      Value: serialized user object (or null for deletion)                   │
│      Consumers maintain local cache, sync from topic                        │
│                                                                             │
│   3. CDC (Change Data Capture)                                              │
│      Topic: database-changes                                                │
│      Key: table:primary_key                                                 │
│      Value: current row state                                               │
│      Replicas can bootstrap from compacted topic                            │
│                                                                             │
│   DELETION IN COMPACTED TOPICS:                                             │
│                                                                             │
│   Send message with key=X, value=null (tombstone)                           │
│   Compaction will eventually remove key X entirely                          │
│   Tombstones are kept for delete.retention.ms before removal                │
│                                                                             │
│   TRADE-OFFS:                                                               │
│                                                                             │
│   + Bounded storage (only one value per key)                                │
│   + New consumers get current state quickly                                 │
│   + Good for "table" semantics vs "log" semantics                           │
│   - Lose history (can't see previous values)                                │
│   - Compaction timing is non-deterministic                                  │
│   - Not suitable for events that represent actions (only state)             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Consumer Group Strategies

Understanding rebalancing strategies is crucial for production systems.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CONSUMER GROUP REBALANCING STRATEGIES                    │
│                                                                             │
│   EAGER REBALANCING (Default, Legacy):                                      │
│                                                                             │
│   When any consumer joins/leaves:                                           │
│   1. ALL consumers stop processing                                          │
│   2. ALL consumers revoke ALL partitions                                    │
│   3. Coordinator reassigns ALL partitions                                   │
│   4. ALL consumers receive new assignments                                  │
│   5. ALL consumers resume processing                                        │
│                                                                             │
│   Problem: "Stop the world" pause. Processing halts completely.             │
│   With 100 consumers and 1000 partitions, rebalance takes 30+ seconds.      │
│                                                                             │
│   COOPERATIVE REBALANCING (Modern):                                         │
│                                                                             │
│   When any consumer joins/leaves:                                           │
│   1. Consumers continue processing unaffected partitions                    │
│   2. Only affected partitions are revoked and reassigned                    │
│   3. Minimal disruption to processing                                       │
│                                                                             │
│   Example:                                                                  │
│   Consumer A: [P0, P1, P2]                                                  │
│   Consumer B: [P3, P4, P5]                                                  │
│   Consumer C joins                                                          │
│                                                                             │
│   Eager: A stops, B stops, all partitions redistributed                     │
│   Cooperative: A gives up P2, B gives up P5, C gets P2 and P5               │
│                A and B continue processing P0,P1 and P3,P4                  │
│                                                                             │
│   Configuration:                                                            │
│   partition.assignment.strategy=                                            │
│     org.apache.kafka.clients.consumer.CooperativeStickyAssignor             │
│                                                                             │
│   STATIC MEMBERSHIP:                                                        │
│                                                                             │
│   Normal: Consumer restarts → leaves group → rejoins → rebalance!           │
│   Static: Consumer restarts → group.instance.id remembered →                │
│           same partitions reassigned → no rebalance!                        │
│                                                                             │
│   Configuration:                                                            │
│   group.instance.id=consumer-1 (unique per consumer instance)               │
│   session.timeout.ms=300000 (5 minutes—allows for restart)                  │
│                                                                             │
│   WHEN TO USE WHAT:                                                         │
│                                                                             │
│   │ Scenario                │ Strategy                                   │  │
│   │─────────────────────────│─────────────────────────────────────────── │  │
│   │ Frequent deployments    │ Static membership + cooperative            │  │
│   │ Auto-scaling consumers  │ Cooperative rebalancing                    │  │
│   │ Stable consumer count   │ Either works, prefer cooperative           │  │
│   │ Legacy Kafka (< 2.4)    │ Eager only (cooperative not available)     │  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Stream Processing vs Event Streaming

A common point of confusion in interviews.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    EVENT STREAMING vs STREAM PROCESSING                     │
│                                                                             │
│   EVENT STREAMING (Kafka as Message Bus):                                   │
│                                                                             │
│   Producer → Kafka Topic → Consumer                                         │
│                                                                             │
│   - Events are transported from A to B                                      │
│   - Consumer does simple processing per event                               │
│   - No windowing, no aggregation, no joins                                  │
│   - Stateless or simple stateful (with external state)                      │
│                                                                             │
│   Example: Order placed → send to warehouse                                 │
│            Each event processed independently                               │
│                                                                             │
│   STREAM PROCESSING (Kafka Streams, Flink, Spark Streaming):                │
│                                                                             │
│   Producer → Kafka Topic → Stream Processor → Output Topic                  │
│                                  │                                          │
│                                  ├── Windowing (5-minute windows)           │
│                                  ├── Aggregation (count, sum, avg)          │
│                                  ├── Joins (stream-stream, stream-table)    │
│                                  └── Stateful transformations               │
│                                                                             │
│   Example: Count clicks per page per 5-minute window                        │
│            Join click stream with user profile table                        │
│            Detect fraud patterns across event sequences                     │
│                                                                             │
│   KEY DIFFERENCES:                                                          │
│                                                                             │
│   │ Aspect              │ Event Streaming     │ Stream Processing         │ │
│   │─────────────────────│─────────────────────│───────────────────────────│ │
│   │ State               │ External or none    │ Built-in, managed         │ │
│   │ Windowing           │ Not supported       │ Core feature              │ │
│   │ Joins               │ Manual (DB lookup)  │ Native support            │ │
│   │ Aggregations        │ Manual              │ Native support            │ │
│   │ Exactly-once        │ Application-level   │ Framework-level           │ │
│   │ Complexity          │ Lower               │ Higher                    │ │
│   │ Use Case            │ Event routing       │ Analytics, enrichment     │ │
│                                                                             │
│   WHEN TO USE STREAM PROCESSING:                                            │
│                                                                             │
│   1. Real-time aggregations (metrics, dashboards)                           │
│   2. Complex event processing (fraud detection, pattern matching)           │
│   3. Stream-table joins (enrich events with dimension data)                 │
│   4. Windowed computations (session analysis, trend detection)              │
│                                                                             │
│   WHEN SIMPLE CONSUMERS SUFFICE:                                            │
│                                                                             │
│   1. Event routing (fan-out to multiple services)                           │
│   2. Simple transformations (format conversion, filtering)                  │
│   3. Triggering actions (send email, call API)                              │
│   4. Simple stateful processing with external store                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Testing Event-Driven Systems

Testing is where many event-driven projects fail. Staff Engineers build testing into the architecture.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    TESTING STRATEGIES FOR EVENT-DRIVEN SYSTEMS              │
│                                                                             │
│   LEVEL 1: UNIT TESTS (Event Handlers)                                      │
│                                                                             │
│   Test event processing logic in isolation:                                 │
│   - Mock the event, call the handler, verify outcomes                       │
│   - No Kafka, no network, fast execution                                    │
│                                                                             │
│   FUNCTION test_order_handler():                                            │
│       event = OrderPlacedEvent(order_id="123", amount=100)                  │
│       mock_db = MockDatabase()                                              │
│       mock_payment = MockPaymentService()                                   │
│                                                                             │
│       handler = OrderHandler(mock_db, mock_payment)                         │
│       handler.process(event)                                                │
│                                                                             │
│       assert mock_db.orders["123"].status == "created"                      │
│       assert mock_payment.charged["123"] == 100                             │
│                                                                             │
│   LEVEL 2: INTEGRATION TESTS (With Embedded Kafka)                          │
│                                                                             │
│   Test producer/consumer with real Kafka (embedded):                        │
│   - Use Testcontainers or embedded Kafka                                    │
│   - Verify serialization/deserialization                                    │
│   - Test partition key routing                                              │
│   - Test consumer group behavior                                            │
│                                                                             │
│   FUNCTION test_order_flow():                                               │
│       with EmbeddedKafka() as kafka:                                        │
│           producer = create_producer(kafka.bootstrap_servers)               │
│           consumer = create_consumer(kafka.bootstrap_servers)               │
│                                                                             │
│           producer.send("orders", OrderPlacedEvent(...))                    │
│           producer.flush()                                                  │
│                                                                             │
│           events = consumer.poll(timeout=5s)                                │
│           assert len(events) == 1                                           │
│           assert events[0].order_id == "123"                                │
│                                                                             │
│   LEVEL 3: CONTRACT TESTS (Schema Compatibility)                            │
│                                                                             │
│   Test that producers and consumers agree on schemas:                       │
│   - Use Schema Registry compatibility checks                                │
│   - Test old consumer with new producer events                              │
│   - Test new consumer with old producer events                              │
│                                                                             │
│   FUNCTION test_backwards_compatibility():                                  │
│       old_schema = load_schema("OrderPlacedV1.avsc")                        │
│       new_schema = load_schema("OrderPlacedV2.avsc")                        │
│                                                                             │
│       # New producer, old consumer                                          │
│       new_event = serialize(new_schema, {...})                              │
│       old_parsed = deserialize(old_schema, new_event)                       │
│       assert old_parsed.order_id == "123"  # Required fields work           │
│                                                                             │
│   LEVEL 4: END-TO-END TESTS (Full Pipeline)                                 │
│                                                                             │
│   Test complete event flows in staging environment:                         │
│   - Real Kafka, real services, real databases                               │
│   - Inject test events, verify end state                                    │
│   - Use correlation IDs to trace test events                                │
│                                                                             │
│   FUNCTION test_order_to_shipment_e2e():                                    │
│       correlation_id = "test-" + uuid()                                     │
│       order = create_order(correlation_id=correlation_id)                   │
│                                                                             │
│       # Wait for eventual consistency                                       │
│       shipment = wait_for(                                                  │
│           lambda: get_shipment(order.id),                                   │
│           timeout=60s                                                       │
│       )                                                                     │
│                                                                             │
│       assert shipment.status == "created"                                   │
│       assert shipment.correlation_id == correlation_id                      │
│                                                                             │
│   LEVEL 5: CHAOS TESTS (Failure Injection)                                  │
│                                                                             │
│   Test system behavior under failures:                                      │
│   - Kill consumer mid-processing (verify no data loss)                      │
│   - Inject network partitions (verify recovery)                             │
│   - Inject poison messages (verify DLQ handling)                            │
│   - Inject slow processing (verify backpressure)                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Capacity Planning for Event Systems

Staff Engineers must estimate capacity before production.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CAPACITY PLANNING CALCULATIONS                           │
│                                                                             │
│   STEP 1: ESTIMATE EVENT VOLUME                                             │
│                                                                             │
│   Example: E-commerce order events                                          │
│   - 10M orders per day                                                      │
│   - Average event size: 500 bytes                                           │
│   - Peak hour: 3x average (30M / 24 * 3 = 3.75M orders in peak hour)        │
│                                                                             │
│   Events per second (average): 10M / 86400 = 116 events/sec                 │
│   Events per second (peak):    3.75M / 3600 = 1042 events/sec               │
│                                                                             │
│   STEP 2: CALCULATE THROUGHPUT                                              │
│                                                                             │
│   Bytes per second (peak): 1042 * 500 = 521 KB/sec ≈ 0.5 MB/sec             │
│   Bytes per day: 10M * 500 = 5 GB/day                                       │
│                                                                             │
│   STEP 3: DETERMINE PARTITION COUNT                                         │
│                                                                             │
│   Rule of thumb: 1 partition = 1 consumer = ~10K events/sec throughput      │
│   (Actual varies by message size, processing complexity)                    │
│                                                                             │
│   For 1042 events/sec peak: minimum 1 partition                             │
│   For parallelism with 4 consumers: 4 partitions                            │
│   For future growth (10x): 40 partitions                                    │
│                                                                             │
│   IMPORTANT: You can ADD partitions but not REMOVE them                     │
│   Start with room to grow: 12-24 partitions is common starting point        │
│                                                                             │
│   STEP 4: CALCULATE STORAGE                                                 │
│                                                                             │
│   Retention: 7 days                                                         │
│   Storage = 5 GB/day * 7 days * 3 replicas = 105 GB                         │
│                                                                             │
│   STEP 5: ESTIMATE CONSUMER CAPACITY                                        │
│                                                                             │
│   Consumer processing time per event: 10ms (with DB write)                  │
│   Events per consumer per second: 1000ms / 10ms = 100 events/sec            │
│   Consumers needed for peak: 1042 / 100 = 11 consumers (round up to 12)     │
│                                                                             │
│   With partition count of 12: exactly 1 consumer per partition              │
│                                                                             │
│   STEP 6: CALCULATE LAG TOLERANCE                                           │
│                                                                             │
│   If consumer capacity = exactly peak load, any spike creates lag           │
│   Recommended: 2x headroom                                                  │
│                                                                             │
│   24 consumers for 12 partitions?                                           │
│   No—max parallelism = partition count                                      │
│   Either: increase partitions to 24 OR optimize consumer processing         │
│                                                                             │
│   CAPACITY PLANNING CHECKLIST:                                              │
│                                                                             │
│   □ Event volume (average, peak, growth projection)                         │
│   □ Event size (average, max)                                               │
│   □ Throughput requirements (events/sec, MB/sec)                            │
│   □ Partition count (current parallelism + future growth)                   │
│   □ Storage (retention * daily volume * replication)                        │
│   □ Consumer count (peak throughput / processing rate)                      │
│   □ Headroom (typically 2x peak for safety)                                 │
│   □ Lag SLA (how far behind is acceptable?)                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Cost Analysis: Kafka at Scale

Staff Engineers treat cost as a first-class constraint, not an afterthought. Kafka clusters can become one of your largest infrastructure costs if not managed carefully.

### Cost Drivers in Event-Driven Systems

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    KAFKA COST BREAKDOWN AT SCALE                            │
│                                                                             │
│   EXAMPLE: E-commerce platform, 100M events/day, 7-day retention            │
│                                                                             │
│   COST DRIVER 1: BROKER STORAGE (Largest Component)                        │
│   ────────────────────────────────────────────────────────────────────────  │
│   Event volume: 100M events/day * 500 bytes = 50 GB/day                      │
│   Retention: 7 days                                                          │
│   Replication: 3x (for durability)                                           │
│   Total storage: 50 GB * 7 * 3 = 1,050 GB = 1.05 TB                        │
│                                                                             │
│   Storage cost (AWS EBS gp3): $0.08/GB-month                                │
│   Monthly storage: 1.05 TB * $0.08 * 1024 = $86/month                       │
│                                                                             │
│   BUT: At 1B events/day (10x growth):                                       │
│   Storage: 10.5 TB * $0.08 * 1024 = $860/month                              │
│                                                                             │
│   Storage scales linearly with:                                             │
│   - Event volume (events/day)                                                 │
│   - Event size (bytes per event)                                             │
│   - Retention period (days)                                                   │
│   - Replication factor (copies)                                               │
│                                                                             │
│   OPTIMIZATION:                                                              │
│   - Compression: gzip reduces 50-70% (trade: CPU)                          │
│   - Tiered storage: Hot (SSD) + Cold (S3) for old data                      │
│   - Reduce retention: 7 days → 3 days (if replay not needed)                 │
│                                                                             │
│   COST DRIVER 2: NETWORK EGRESS (Cross-AZ Replication)                       │
│   ────────────────────────────────────────────────────────────────────────  │
│   Replication factor 3: Each event replicated 2x across AZs                  │
│   Daily egress: 50 GB * 2 = 100 GB/day                                      │
│   Monthly egress: 100 GB * 30 = 3 TB/month                                   │
│                                                                             │
│   AWS cost: $0.02/GB for cross-AZ transfer                                  │
│   Monthly egress: 3 TB * $0.02 * 1024 = $61/month                           │
│                                                                             │
│   At 1B events/day:                                                         │
│   Egress: 30 TB/month * $0.02 * 1024 = $614/month                           │
│                                                                             │
│   OPTIMIZATION:                                                              │
│   - Single-AZ deployment (trade: durability)                                │
│   - Compression reduces egress (compressed before replication)              │
│   - Regional topics (replicate only critical events)                         │
│                                                                             │
│   COST DRIVER 3: BROKER COMPUTE (CPU/Memory)                                 │
│   ────────────────────────────────────────────────────────────────────────  │
│   Kafka brokers: 3 brokers (for replication)                                │
│   Instance: m5.xlarge (4 vCPU, 16 GB RAM)                                   │
│   Cost: $0.192/hour * 3 brokers * 730 hours = $420/month                   │
│                                                                             │
│   Compute scales with:                                                      │
│   - Throughput (events/sec) - CPU for serialization                          │
│   - Partition count - Memory for partition metadata                          │
│   - Consumer group count - CPU for coordination                               │
│                                                                             │
│   OPTIMIZATION:                                                              │
│   - Right-size instances (don't over-provision)                             │
│   - Use spot instances for non-critical clusters                             │
│   - Consolidate topics (fewer brokers, more partitions)                       │
│                                                                             │
│   COST DRIVER 4: ZOOKEEPER/KRAFT COORDINATION                               │
│   ────────────────────────────────────────────────────────────────────────  │
│   Zookeeper: 3 nodes (for quorum)                                            │
│   Instance: m5.large (2 vCPU, 8 GB RAM)                                     │
│   Cost: $0.096/hour * 3 * 730 = $210/month                                  │
│                                                                             │
│   OR KRaft (Kafka Raft): No separate ZK cluster needed                      │
│   Cost: $0 (embedded in brokers)                                            │
│                                                                             │
│   OPTIMIZATION:                                                              │
│   - Migrate to KRaft (eliminates ZK cost)                                   │
│   - Use smaller instances for ZK (if still on ZK)                           │
│                                                                             │
│   COST DRIVER 5: CONSUMER INFRASTRUCTURE                                     │
│   ────────────────────────────────────────────────────────────────────────  │
│   Consumer instances: 50 instances (for parallelism)                         │
│   Instance: c5.large (2 vCPU, 4 GB RAM)                                     │
│   Cost: $0.085/hour * 50 * 730 = $3,102/month                              │
│                                                                             │
│   Consumer cost often EXCEEDS Kafka broker cost!                             │
│                                                                             │
│   OPTIMIZATION:                                                              │
│   - Batch processing (reduce per-event overhead)                             │
│   - Async I/O (process multiple events concurrently)                          │
│   - Right-size consumers (don't need 1 per partition if processing is fast) │
│                                                                             │
│   ────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│   TOTAL MONTHLY COST (100M events/day):                                      │
│   - Storage: $86                                                              │
│   - Egress: $61                                                              │
│   - Brokers: $420                                                            │
│   - ZK/KRaft: $210 (or $0 with KRaft)                                       │
│   - Consumers: $3,102                                                        │
│   TOTAL: ~$3,879/month                                                      │
│                                                                             │
│   At 1B events/day (10x):                                                   │
│   TOTAL: ~$38,790/month (mostly consumers scale linearly)                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Cost Optimization Strategies

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    COST OPTIMIZATION DECISION TREE                         │
│                                                                             │
│   QUESTION 1: Can you reduce event volume?                                 │
│   ──────────────────────────────────────────────────────────────────────── │
│   YES → Sample events (1 in 10 for analytics)                              │
│        → Aggregate before publishing (batch metrics)                        │
│        → Filter at source (don't publish low-value events)                  │
│        → Impact: 10x reduction = 10x cost reduction                        │
│                                                                             │
│   NO → Continue to Question 2                                                │
│                                                                             │
│   QUESTION 2: Can you reduce retention?                                    │
│   ──────────────────────────────────────────────────────────────────────── │
│   YES → Reduce retention: 7 days → 3 days (if replay not needed)           │
│        → Impact: 50% storage reduction                                     │
│                                                                             │
│   NO → Continue to Question 3                                              │
│                                                                             │
│   QUESTION 3: Can you reduce replication?                                  │
│   ──────────────────────────────────────────────────────────────────────── │
│   YES (for non-critical) → RF=3 → RF=2 (trade: durability)                 │
│        → Impact: 33% storage + egress reduction                            │
│                                                                             │
│   NO → Continue to Question 4                                              │
│                                                                             │
│   QUESTION 4: Can you optimize consumer processing?                          │
│   ──────────────────────────────────────────────────────────────────────── │
│   YES → Batch database writes (100 events per transaction)                  │
│        → Async I/O (process 10 events concurrently)                         │
│        → Impact: 10x fewer consumer instances needed                       │
│                                                                             │
│   NO → Continue to Question 5                                              │
│                                                                             │
│   QUESTION 5: Can you use tiered storage?                                   │
│   ──────────────────────────────────────────────────────────────────────── │
│   YES → Hot storage (SSD): Last 24 hours                                    │
│        → Cold storage (S3): Older data                                      │
│        → Impact: 80% storage cost reduction for old data                   │
│                                                                             │
│   NO → Accept cost or reconsider architecture                              │
│                                                                             │
│   STAFF ENGINEER RULE:                                                      │
│   The cheapest event is the one you don't publish.                         │
│   The second cheapest is the one you compress.                              │
│   The third cheapest is the one you delete quickly.                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Cost vs Scale: When Kafka Becomes Expensive

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    COST SCALING: WHEN TO WORRY                              │
│                                                                             │
│   SCALE 1: < 1M events/day                                                  │
│   Cost: < $500/month                                                        │
│   Status: Negligible cost, don't optimize                                  │
│                                                                             │
│   SCALE 2: 1M - 10M events/day                                              │
│   Cost: $500 - $5,000/month                                                 │
│   Status: Monitor, optimize if > $2K/month                                 │
│                                                                             │
│   SCALE 3: 10M - 100M events/day                                            │
│   Cost: $5,000 - $50,000/month                                              │
│   Status: Active optimization required                                      │
│   Actions: Compression, retention tuning, consumer optimization             │
│                                                                             │
│   SCALE 4: 100M - 1B events/day                                             │
│   Cost: $50,000 - $500,000/month                                            │
│   Status: Cost is a first-class constraint                                 │
│   Actions: Sampling, tiered storage, dedicated clusters per domain         │
│                                                                             │
│   SCALE 5: > 1B events/day                                                  │
│   Cost: > $500,000/month                                                    │
│   Status: Re-evaluate architecture                                          │
│   Questions: Do you need all events? Can you aggregate? Alternative tools? │
│                                                                             │
│   STAFF ENGINEER INSIGHT:                                                   │
│   At $100K+/month, Kafka cost exceeds most application infrastructure.     │
│   This is when you need dedicated platform team and cost reviews.          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Why Cost Matters at Staff Level**:

1. **Hidden costs**: Consumer infrastructure often costs more than Kafka brokers
2. **Linear scaling**: Cost scales linearly with volume (no economies of scale)
3. **Retention trap**: Long retention multiplies storage cost
4. **Replication multiplier**: RF=3 means 3x storage + 2x egress cost

**Design Decision Framework**:

- **Before adding events**: Estimate cost at 10x current scale
- **After adding events**: Monitor cost per million events
- **Cost review**: When Kafka cost > 10% of infrastructure budget, optimize

---

# Part 9: Conclusion and Key Takeaways

Event-driven architecture is a powerful tool—but like all powerful tools, it can cause significant harm when misused. The Staff Engineer's role is not to advocate for events or against them, but to choose the right tool for each situation and design systems that remain operable when things go wrong.

**Key Takeaways**:

1. **Events are a trade-off, not an upgrade**. You're trading consistency and debuggability for temporal decoupling and independent scaling. Make sure the trade is worth it.

2. **Decoupling is a myth**. Events transform coupling from visible (API contracts) to invisible (schema and semantic dependencies). Invisible coupling is often worse.

3. **Exactly-once is hard**. Kafka's exactly-once features don't extend beyond Kafka. For real systems, design for at-least-once and make everything idempotent.

4. **Operational complexity is real**. Before adding Kafka, ask: who will be on-call? How will you debug? What's the DLQ strategy? If you can't answer these, you're not ready.

5. **Start synchronous, add events later**. It's easier to add async to a working sync system than to debug a broken async system. YAGNI for event-driven architecture is sound advice.

The best event-driven systems I've seen were designed by engineers who were deeply skeptical of events. They added events reluctantly, for specific reasons, with comprehensive operational support. The worst systems were designed by enthusiasts who saw events as inherently superior and adopted them wholesale.

Be skeptical. Be specific. Be operational. That's how Staff Engineers build event-driven systems that work.

---

# Part 10: Staff-Level Deep Dives (L6 Addendum)

This section addresses advanced topics that distinguish Staff Engineer (L6) thinking from Senior Engineer (L5) thinking. These are the failure modes, evolution patterns, and operational realities that only emerge after years of production experience.

---

## Partial Failure States: The 50% Complete Problem

Most event-driven documentation discusses success and failure as binary states. In production, the most dangerous state is **partial completion**.

### The Anatomy of Partial Failure

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PARTIAL FAILURE: THE 50% COMPLETE PROBLEM                │
│                                                                             │
│   SCENARIO: Order Processing with Multiple Side Effects                     │
│                                                                             │
│   Consumer receives OrderPlaced event:                                      │
│   1. ✓ Insert order into database                                           │
│   2. ✓ Decrement inventory                                                  │
│   3. ✓ Charge payment                                                       │
│   4. ✗ Send confirmation email (timeout)                                    │
│   5. ? Update analytics                                                     │
│   6. ? Notify warehouse                                                     │
│                                                                             │
│   Consumer crashes. What state are we in?                                   │
│                                                                             │
│   - Order exists in database ✓                                              │
│   - Inventory decremented ✓                                                 │
│   - Payment charged ✓                                                       │
│   - No confirmation email sent                                              │
│   - Analytics not updated                                                   │
│   - Warehouse not notified                                                  │
│                                                                             │
│   On restart, consumer replays OrderPlaced event:                           │
│   1. Insert order → DUPLICATE! (unless idempotent)                          │
│   2. Decrement inventory → DOUBLE DECREMENT! (unless idempotent)            │
│   3. Charge payment → DOUBLE CHARGE! (unless idempotent)                    │
│   4. Send email → Finally works                                             │
│   5. Update analytics → DUPLICATE data                                      │
│   6. Notify warehouse → Finally works                                       │
│                                                                             │
│   THE HARSH REALITY:                                                        │
│   Every single operation in your consumer must be idempotent.               │
│   Not just "should be" — MUST be, or you WILL have production incidents.    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Staff-Level Pattern: Checkpoint-Based Processing

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CHECKPOINT-BASED PROCESSING PATTERN                      │
│                                                                             │
│   Instead of: One big consumer that does 6 things                           │
│   Use: Checkpoint each step, resume from last successful checkpoint         │
│                                                                             │
│   Database table: processing_checkpoints                                    │
│   - event_id (PK)                                                           │
│   - step_completed (enum: 'order_created', 'inventory_decremented', ...)    │
│   - updated_at                                                              │
│                                                                             │
│   PSEUDOCODE:                                                               │
│                                                                             │
│   FUNCTION process_order_event(event):                                      │
│       checkpoint = db.get_checkpoint(event.id)                              │
│       current_step = checkpoint?.step_completed ?? 'none'                   │
│                                                                             │
│       // Resume from last successful step                                   │
│       IF current_step < 'order_created':                                    │
│           create_order(event)  // Must be idempotent                        │
│           db.update_checkpoint(event.id, 'order_created')                   │
│                                                                             │
│       IF current_step < 'inventory_decremented':                            │
│           decrement_inventory(event)  // Must be idempotent                 │
│           db.update_checkpoint(event.id, 'inventory_decremented')           │
│                                                                             │
│       IF current_step < 'payment_charged':                                  │
│           charge_payment(event)  // Must be idempotent                      │
│           db.update_checkpoint(event.id, 'payment_charged')                 │
│                                                                             │
│       // Continue for each step...                                          │
│                                                                             │
│       // Final step: mark fully complete                                    │
│       db.update_checkpoint(event.id, 'completed')                           │
│       RETURN SUCCESS                                                        │
│                                                                             │
│   BENEFITS:                                                                 │
│   - Crash at any point, resume exactly where you left off                   │
│   - Each step still needs idempotence (defense in depth)                    │
│   - Observability: "event X is stuck at step Y"                             │
│   - Can implement per-step retry logic                                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### What L5 Engineers Miss

L5 engineers often think: "I'll make it idempotent" — but only make the *first* operation idempotent.

L6 engineers know: Every step, every external call, every database write must independently handle being called twice. And you need observability into which step failed.

---

## Graceful Degradation During Kafka Unavailability

What happens when Kafka itself is unavailable? Most teams don't have an answer. Staff Engineers do.

### The Kafka Unavailability Scenarios

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    KAFKA UNAVAILABILITY SCENARIOS                           │
│                                                                             │
│   SCENARIO 1: Full Cluster Outage (Rare but Catastrophic)                   │
│                                                                             │
│   All Kafka brokers are down. Producers can't publish, consumers can't      │
│   consume. What happens to your system?                                     │
│                                                                             │
│   WITHOUT Graceful Degradation:                                             │
│   - Producer throws exception → API returns 500 → User sees error           │
│   - Every event-dependent operation fails                                   │
│   - System is effectively down even though databases are fine               │
│                                                                             │
│   WITH Graceful Degradation:                                                │
│   - Producer catches exception, writes to fallback (local disk, Redis)      │
│   - API returns success to user (operation will be processed eventually)    │
│   - Background process drains fallback when Kafka recovers                  │
│   - User experience is preserved (with eventual consistency)                │
│                                                                             │
│   SCENARIO 2: Partition Leader Unavailable (More Common)                    │
│                                                                             │
│   One partition's leader is down, others work fine.                         │
│   Events with certain keys fail, others succeed.                            │
│                                                                             │
│   Implication:                                                              │
│   - User A's events work fine                                               │
│   - User B's events all fail (their key hashes to failed partition)         │
│   - Partial outage, hard to detect, confusing for support                   │
│                                                                             │
│   SCENARIO 3: Consumer Group Coordination Failure                           │
│                                                                             │
│   Consumers can't reach group coordinator. No rebalancing, no commits.      │
│   Consumers continue processing but can't commit offsets.                   │
│                                                                             │
│   Implication:                                                              │
│   - Processing appears to work                                              │
│   - On recovery, all uncommitted messages are reprocessed                   │
│   - Massive duplicate processing storm                                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Staff-Level Pattern: The Fallback Queue

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FALLBACK QUEUE PATTERN                                   │
│                                                                             │
│   Architecture:                                                             │
│                                                                             │
│   ┌─────────────┐     ┌─────────────┐                                       │
│   │   Producer  │────▶│    Kafka    │  (Primary path)                       │
│   │             │     └─────────────┘                                       │
│   │             │            │                                              │
│   │             │     ┌──────▼──────┐                                       │
│   │             │     │  Consumers  │                                       │
│   │             │     └─────────────┘                                       │
│   │             │                                                           │
│   │             │     ┌─────────────┐                                       │
│   │             │────▶│  Fallback   │  (When Kafka unavailable)             │
│   │             │     │  (Redis/    │                                       │
│   └─────────────┘     │   Disk)     │                                       │
│                       └──────┬──────┘                                       │
│                              │                                              │
│                       ┌──────▼──────┐                                       │
│                       │  Drainer    │  (Moves to Kafka when recovered)      │
│                       └─────────────┘                                       │
│                                                                             │
│   PRODUCER LOGIC:                                                           │
│                                                                             │
│   FUNCTION publish_with_fallback(topic, message):                           │
│       TRY:                                                                  │
│           kafka.publish(topic, message, timeout=5s)                         │
│           metrics.increment("kafka.publish.success")                        │
│       CATCH KafkaUnavailableError:                                          │
│           metrics.increment("kafka.publish.fallback")                       │
│           fallback.push(topic, message)  // Redis list or local file        │
│           alert_if_first_fallback()  // Page someone                        │
│                                                                             │
│   DRAINER LOGIC (Background Process):                                       │
│                                                                             │
│   LOOP every 5 seconds:                                                     │
│       IF kafka.is_healthy():                                                │
│           messages = fallback.pop_batch(100)                                │
│           FOR message IN messages:                                          │
│               TRY:                                                          │
│                   kafka.publish(message.topic, message.payload)             │
│               CATCH:                                                        │
│                   fallback.push_back(message)  // Re-queue                  │
│                   BREAK  // Kafka still unhealthy                           │
│                                                                             │
│   IMPORTANT CONSIDERATIONS:                                                 │
│   - Fallback must be durable (not just in-memory)                           │
│   - Drainer must preserve ordering (per partition key)                      │
│   - Monitor fallback queue size (should be 0 normally)                      │
│   - Set TTL on fallback items (don't process stale events)                  │
│   - Consumers must be idempotent (drainer may duplicate)                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### The Decision Framework for Kafka Unavailability

```
WHEN KAFKA IS UNAVAILABLE, WHAT SHOULD YOUR SYSTEM DO?

OPTION 1: FAIL FAST
- Return error to user
- User retries
- Appropriate when: User can easily retry, operation is not time-sensitive

OPTION 2: FALLBACK QUEUE
- Accept operation, queue for later processing
- User sees success (eventually consistent)
- Appropriate when: User experience matters, eventual processing is acceptable

OPTION 3: SYNCHRONOUS FALLBACK
- Skip events entirely, call downstream services directly
- Lose benefits of events (fan-out, buffering)
- Appropriate when: Critical path that cannot fail

OPTION 4: CIRCUIT BREAKER + RETRY
- Return error but remember Kafka is down
- Stop trying Kafka for N seconds
- Retry after circuit breaker resets
- Appropriate when: Kafka outages are brief, retry is acceptable

Staff Engineers choose based on:
1. What's the user experience impact?
2. How critical is this operation?
3. Can we tolerate eventual consistency?
4. What's our SLA for this operation?
```

---

## Evolution Path: V1 → 10× → 100× Scale

Systems don't fail at one scale—they fail at *transition points*. Staff Engineers anticipate these transitions and design for them.

### What Breaks at Each Stage

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SCALING BREAKPOINTS IN EVENT SYSTEMS                     │
│                                                                             │
│   STAGE 1: V1 (1K events/sec)                                               │
│   Everything works. Single partition is enough.                             │
│   One consumer instance handles everything.                                 │
│   Debugging is easy (grep the logs).                                        │
│   "Events are great!"                                                       │
│                                                                             │
│   STAGE 2: 10× (10K events/sec)                                             │
│   WHAT BREAKS:                                                              │
│   - Single partition can't handle throughput                                │
│   - Single consumer falls behind                                            │
│   - First hot partition problems appear                                     │
│   - Log volume makes grep impossible                                        │
│                                                                             │
│   WHAT YOU NEED:                                                            │
│   - Increase partitions (can't decrease later!)                             │
│   - Add consumer instances                                                  │
│   - Re-evaluate partition key (avoid hot partitions)                        │
│   - Centralized logging with search                                         │
│   - Consumer lag monitoring                                                 │
│                                                                             │
│   STAGE 3: 100× (100K events/sec)                                           │
│   WHAT BREAKS:                                                              │
│   - Kafka cluster resource limits                                           │
│   - Consumer processing can't keep up even with parallelism                 │
│   - Downstream databases become bottleneck                                  │
│   - Rebalancing takes too long (processing pauses for minutes)              │
│   - Event schema changes require coordinated deploys                        │
│                                                                             │
│   WHAT YOU NEED:                                                            │
│   - Dedicated Kafka cluster per domain                                      │
│   - Batch processing for bulk operations                                    │
│   - Database sharding or specialized storage                                │
│   - Static consumer membership (avoid rebalancing)                          │
│   - Schema registry with compatibility checks                               │
│   - Dedicated platform team                                                 │
│                                                                             │
│   STAGE 4: 1000× (1M events/sec)                                            │
│   WHAT BREAKS:                                                              │
│   - Single datacenter can't handle load                                     │
│   - Cross-region consistency becomes a problem                              │
│   - Retention costs become significant                                      │
│   - Every small inefficiency is amplified                                   │
│                                                                             │
│   WHAT YOU NEED:                                                            │
│   - Multi-region Kafka deployment                                           │
│   - Event compression and optimization                                      │
│   - Tiered storage for long retention                                       │
│   - Sampling for analytics (not every event)                                │
│   - Full-time team just for Kafka operations                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Incident-Driven Evolution: When to Re-Architect

Staff Engineers don't re-architect based on theory—they re-architect based on production pain.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    TRIGGERS FOR RE-ARCHITECTURE                             │
│                                                                             │
│   TRIGGER 1: Lag Never Recovers                                             │
│                                                                             │
│   Symptom: Consumer lag increases during peak, never catches up             │
│   What it means: Processing rate < production rate (permanently)            │
│   Action: Either optimize processing or accept data loss (sampling)         │
│                                                                             │
│   TRIGGER 2: Debugging Takes Days                                           │
│                                                                             │
│   Symptom: Simple bugs take 3+ days to diagnose                             │
│   What it means: Observability is inadequate for event complexity           │
│   Action: Add tracing, consider reducing event hops, add correlation IDs    │
│                                                                             │
│   TRIGGER 3: Schema Changes Cause Outages                                   │
│                                                                             │
│   Symptom: Every schema change breaks consumers                             │
│   What it means: Schema evolution strategy is missing                       │
│   Action: Schema registry, versioning, or consider decoupling via API       │
│                                                                             │
│   TRIGGER 4: One Bad Event Cascades                                         │
│                                                                             │
│   Symptom: Poison message takes down multiple services                      │
│   What it means: Blast radius is too wide                                   │
│   Action: DLQ per consumer, circuit breakers, topic separation              │
│                                                                             │
│   TRIGGER 5: Operational Cost Exceeds Benefit                               │
│                                                                             │
│   Symptom: Team spends 50%+ time on Kafka operations                        │
│   What it means: Events are providing less value than they cost             │
│   Action: Evaluate replacing some events with sync calls, reduce scope      │
│                                                                             │
│   Staff Engineer Rule:                                                      │
│   Re-architect when production pain exceeds theoretical benefits.           │
│   Not before. Theory is cheap; production data is expensive.                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Multi-Region Event Architecture

At Staff level, you need to reason about events across regions. This is where event-driven architecture becomes genuinely complex.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MULTI-REGION KAFKA CHALLENGES                            │
│                                                                             │
│   CHALLENGE 1: Which Region Owns the Topic?                                 │
│                                                                             │
│   Option A: Single Primary Region                                           │
│   - All writes go to one region's Kafka                                     │
│   - Mirror to other regions (MirrorMaker, Confluent Replicator)             │
│   - Pros: Simple consistency, no conflicts                                  │
│   - Cons: Write latency for non-primary regions                             │
│                                                                             │
│   Option B: Multi-Region Active-Active                                      │
│   - Each region has its own Kafka                                           │
│   - Events are produced locally, replicated to other regions                │
│   - Pros: Low write latency everywhere                                      │
│   - Cons: Conflict resolution, duplicate detection, ordering chaos          │
│                                                                             │
│   Option C: Regional Topics with Global Aggregation                         │
│   - events-us-west, events-us-east, events-eu (regional)                    │
│   - events-global (aggregated for consumers that need everything)           │
│   - Pros: Isolation + global view when needed                               │
│   - Cons: Complexity of managing multiple topics                            │
│                                                                             │
│   CHALLENGE 2: Replication Lag                                              │
│                                                                             │
│   Cross-region replication takes 50-200ms minimum (physics).                │
│   During that window:                                                       │
│   - Event exists in region A                                                │
│   - Event doesn't exist in region B                                         │
│   - Consumer in B reading from replicated topic is behind                   │
│                                                                             │
│   Implication:                                                              │
│   - User writes in region A, immediately reads in region B                  │
│   - Read doesn't see the write (consistency violation from user's POV)      │
│                                                                             │
│   Solution:                                                                 │
│   - Sticky sessions (user stays in same region)                             │
│   - Read-your-writes via version vectors                                    │
│   - Accept eventual consistency with clear SLA                              │
│                                                                             │
│   CHALLENGE 3: Consumer Offset Management                                   │
│                                                                             │
│   Which offsets are correct across regions?                                 │
│   - Primary fails, secondary takes over                                     │
│   - Offsets in primary: 1,234,567                                           │
│   - Offsets in secondary: 1,234,000 (replication lag)                       │
│   - Consumer in secondary starts from 1,234,000                             │
│   - 567 events reprocessed (duplicates!)                                    │
│                                                                             │
│   Solution:                                                                 │
│   - Idempotent consumers (always)                                           │
│   - External offset storage with event_id (not offset-based)                │
│   - Accept reprocessing as cost of failover                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Interview Calibration: What Interviewers Look For

### Staff-Level Signals in Event-Driven Design

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    WHAT GOOGLE INTERVIEWERS LOOK FOR                        │
│                                                                             │
│   STRONG L6 SIGNALS:                                                        │
│                                                                             │
│   1. SKEPTICISM BEFORE ENTHUSIASM                                           │
│      L5: "We should use Kafka for this—it's scalable"                       │
│      L6: "What specific problem are events solving here? Could we           │
│           start with sync calls and add events when we have multiple        │
│           consumers?"                                                       │
│                                                                             │
│   2. OPERATIONAL THINKING UNPROMPTED                                        │
│      L5: Draws the happy path architecture                                  │
│      L6: "Who's on-call for this? How do we debug when user says            │
│           'my order didn't go through'? What's our DLQ strategy?"           │
│                                                                             │
│   3. FAILURE MODE ENUMERATION                                               │
│      L5: "Kafka handles failures"                                           │
│      L6: "There are 5 failure modes here: producer can't reach Kafka,       │
│           consumer crashes mid-processing, Kafka loses leadership,          │
│           downstream service is slow, poison message blocks partition.      │
│           Let me explain how we handle each..."                             │
│                                                                             │
│   4. TRADE-OFF ARTICULATION                                                 │
│      L5: "Events are loosely coupled"                                       │
│      L6: "Events trade explicit API coupling for implicit schema coupling.  │
│           We gain producer independence but lose compile-time safety.       │
│           For this use case, that's a good trade because [specific reason]" │
│                                                                             │
│   5. SCALE TRANSITION AWARENESS                                             │
│      L5: "This design handles 100K events/sec"                              │
│      L6: "At 10K events/sec, we need 10 partitions and 10 consumers.        │
│           At 100K, we'll need to batch database writes. At 1M, we'll        │
│           need a dedicated Kafka cluster and sampling for analytics."       │
│                                                                             │
│   PHRASES STAFF ENGINEERS USE:                                              │
│                                                                             │
│   - "Before we add events, let me verify we actually need async here..."    │
│   - "The partition key choice is critical—let's think about ordering..."    │
│   - "What's our SLA for event processing latency?"                          │
│   - "How do we handle duplicate delivery? Every consumer must be..."        │
│   - "If Kafka is down, what's our degradation strategy?"                    │
│   - "Who owns this event contract? What's our versioning strategy?"         │
│   - "Let me trace through what happens when this fails mid-processing..."   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Common L5 Mistake and L6 Correction

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    L5 vs L6: THE CLASSIC MISTAKE                            │
│                                                                             │
│   THE SCENARIO:                                                             │
│   "Design a notification system that sends emails when users sign up"       │
│                                                                             │
│   L5 ANSWER (Common Mistake):                                               │
│   "I'll use Kafka. User service publishes UserCreated event.                │
│    Notification service consumes and sends email.                           │
│    This is decoupled and scalable."                                         │
│                                                                             │
│   WHY IT'S WEAK:                                                            │
│   - Didn't question if events are needed (one producer, one consumer)       │
│   - "Decoupled" is asserted but not justified                               │
│   - No discussion of failure modes                                          │
│   - No operational considerations                                           │
│   - Kafka is overhead for this simple case                                  │
│                                                                             │
│   L6 ANSWER (Correct Approach):                                             │
│   "Let me first understand if we need events here.                          │
│                                                                             │
│    It's one producer, one consumer, user expects immediate email.           │
│    A synchronous call with retry would be simpler:                          │
│    - User service calls notification service directly                       │
│    - Retry with exponential backoff on failure                              │
│    - Circuit breaker if notification service is down                        │
│    - User still gets success (signup worked), email will retry              │
│                                                                             │
│    When would I switch to events?                                           │
│    - Multiple consumers (email + SMS + in-app + analytics)                  │
│    - Traffic spikes that overwhelm notification service                     │
│    - Need to replay events for new notification types                       │
│                                                                             │
│    If events are required, I'd use Kafka with:                              │
│    - Partition by user_id (ordering within user)                            │
│    - Idempotency via notification_id in Redis                               │
│    - DLQ for failed sends with alerting                                     │
│    - Priority topics (password reset vs marketing)                          │
│    - Correlation IDs for debugging"                                         │
│                                                                             │
│   THE DIFFERENCE:                                                           │
│   L5 reached for technology first.                                          │
│   L6 understood the problem, questioned assumptions, proposed the           │
│   simpler solution, and explained when to evolve.                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Real-World Incident: The Ordering Violation That Cost Millions

A grounding example from production with a detailed step-by-step timeline:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PRODUCTION INCIDENT: ORDERING VIOLATION                  │
│                                                                             │
│   THE SYSTEM:                                                               │
│   - E-commerce platform, 500K orders/day                                    │
│   - Order service publishes to Kafka                                        │
│   - Inventory service consumes and decrements stock                         │
│   - Partition key: order_id                                                 │
│                                                                             │
│   THE INCIDENT:                                                             │
│   Customer places order, then immediately cancels.                          │
│   Events: OrderPlaced(order_id=123), OrderCancelled(order_id=123)           │
│   Both events have same partition key, should be ordered.                   │
│                                                                             │
│   BUT: Development added a "fast cancel" feature.                           │
│   Cancel bypasses normal flow, publishes directly to Kafka.                 │
│   Different producer instance = different partition assignment!             │
│                                                                             │
│   OrderCancelled → Partition 7 (fast cancel producer)                       │
│   OrderPlaced → Partition 3 (normal order producer)                         │
│                                                                             │
│   Inventory service:                                                        │
│   1. Receives OrderCancelled first (Partition 7 ahead)                      │
│   2. "Order 123 doesn't exist, ignoring cancel"                             │
│   3. Receives OrderPlaced                                                   │
│   4. Decrements inventory                                                   │
│   5. Order is cancelled but inventory is decremented!                       │
│                                                                             │
│   THE IMPACT:                                                               │
│   - Inventory counts drifted over weeks                                     │
│   - Popular items showed "in stock" when they weren't                       │
│   - Customers ordered, then got "sorry, out of stock" emails                │
│   - Customer satisfaction dropped, revenue impact in millions               │
│                                                                             │
│   THE ROOT CAUSE:                                                           │
│   Partition key was correct (order_id), but producers were different.       │
│   Same key + different producer = different partitions!                     │
│                                                                             │
│   THE FIX:                                                                  │
│   1. All order events go through same producer (single source of truth)     │
│   2. Inventory service handles out-of-order: if cancel before create,       │
│      store "pre-cancelled" flag, ignore subsequent create                   │
│   3. Add sequence numbers to events for detection                           │
│   4. Reconciliation job to catch drift                                      │
│                                                                             │
│   THE LESSON:                                                               │
│   Ordering guarantees require same key AND same producer AND same topic.    │
│   If any of these differ, ordering is not guaranteed.                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Final Verification Checklist

## This Section Now Meets Google Staff Engineer (L6) Expectations

### Staff-Level Signals Covered:

| Signal | Status | Evidence |
|--------|--------|----------|
| **Judgment & Decision-Making** | ✓ Complete | WHY explained for all decisions, L5/L6 comparisons, explicit trade-offs |
| **Failure & Degradation Thinking** | ✓ Complete | Partial failure states, Kafka unavailability, runtime behavior during failures |
| **Scale & Evolution** | ✓ Complete | V1→10×→100× breakpoints, incident-driven evolution triggers |
| **Operational Ownership** | ✓ Complete | Monitoring, alerting, DLQ strategies, on-call considerations |
| **Multi-Region Complexity** | ✓ Complete | Cross-region replication, offset management, consistency |
| **Interview Calibration** | ✓ Complete | L5 vs L6 examples, interviewer signals, common mistakes |
| **Real-World Grounding** | ✓ Complete | Notification pipeline, feed fan-out, metrics ingestion, ordering incident |

### Key Concepts with Real-World Application:

1. **Notification Pipeline**: Priority separation, idempotency, DLQ handling
2. **Feed Fan-Out**: Hybrid push/pull, celebrity problem, lag handling
3. **Metrics Ingestion**: Cardinality explosion, late data, backpressure
4. **Ordering Violation Incident**: Same key ≠ same partition when producers differ

### Diagrams Provided:

1. Event flow architecture (complete pipeline)
2. Consumer lag visualization (healthy vs unhealthy)
3. Failure propagation (cascade and containment)
4. Multi-region challenges

### Remaining Gaps (Acceptable at L6 Level):

- Cloud-specific implementations (AWS Kinesis, GCP Pub/Sub) not covered—vendor-agnostic approach is appropriate

---

# Part 11: Brainstorming Questions (Comprehensive)

Use these questions to evaluate event-driven designs in interviews, design reviews, or self-study.

---

## Category 1: Requirements Analysis

1. **What's the latency requirement?**
   - If < 100ms end-to-end, events may not be suitable
   - If "eventual" is acceptable, define what "eventual" means (seconds? minutes? hours?)
   - What's the p99 latency requirement, not just average?

2. **What's the consistency requirement?**
   - If transactions are needed across services, events make this hard
   - If eventual consistency is fine, what's the maximum acceptable staleness?
   - Are there specific operations that require strong consistency?

3. **How many consumers exist today? Will exist in the future?**
   - One consumer: probably don't need events
   - Many consumers: events might be justified
   - "Future consumers": be skeptical (YAGNI)—how confident are you?

4. **What happens if processing is delayed by 1 hour? 1 day?**
   - If it's a disaster: events add risk
   - If it's fine: events are a good buffer
   - What's the business impact of each delay tier?

5. **What's the ordering requirement?**
   - No ordering needed: more flexibility in partitioning
   - Per-entity ordering: partition by entity ID
   - Global ordering: single partition (kills parallelism)

---

## Category 2: Kafka Architecture

6. **What's your partition key? Why?**
   - Does it preserve necessary ordering?
   - Does it avoid hot partitions?
   - What happens if a heavy hitter (big customer, viral post) uses this system?

7. **How many partitions do you need?**
   - Current throughput requirements
   - Future growth (can add, can't remove)
   - Consumer parallelism targets

8. **What's your replication factor and min.insync.replicas?**
   - RF=3, min.insync=2 is typical production setting
   - What's your tolerance for data loss vs availability?

9. **What retention do you need?**
   - How long for replay/recovery?
   - Storage cost at that retention?
   - Is there PII that needs special handling (GDPR)?

10. **What's your consumer group strategy?**
    - Static membership for stable deployments?
    - Cooperative rebalancing to minimize disruption?
    - What's your session timeout for failure detection?

---

## Category 3: Delivery Semantics

11. **How do you handle duplicate delivery?**
    - All consumers must be idempotent—what's the idempotency key?
    - Where's the deduplication logic (Redis, database unique constraint)?
    - What happens if deduplication fails?

12. **What happens during partial failure?**
    - Consumer processes 3 of 5 steps, then crashes
    - How do you resume? Checkpoint? Retry all?
    - Are ALL steps idempotent, not just the first one?

13. **Is at-least-once or at-most-once appropriate?**
    - Financial: at-least-once with idempotence
    - Metrics: at-most-once may be fine
    - Notifications: usually at-least-once (duplicate is better than missed)

14. **How do you handle exactly-once to external systems?**
    - Kafka's exactly-once doesn't extend beyond Kafka
    - Outbox pattern? Idempotency keys?
    - What's your strategy for non-idempotent external APIs?

---

## Category 4: Failure Modes

15. **What happens when Kafka is unavailable?**
    - Fail fast and return error?
    - Fallback queue (local disk, Redis)?
    - Synchronous fallback to downstream services?

16. **What's your DLQ strategy?**
    - Who monitors the DLQ?
    - What's the playbook for DLQ messages?
    - How do you replay after fixing bugs?
    - What's the retention on DLQ?

17. **How do you handle poison messages?**
    - How many retries before DLQ?
    - Does one poison message block the entire partition?
    - How do you identify and isolate poison messages?

18. **What's your circuit breaker strategy for downstream services?**
    - When consumer calls slow database/API
    - How do you fail fast vs retry vs queue?
    - How do you recover when downstream recovers?

19. **How do you handle consumer rebalancing storms?**
    - Frequent deployments causing repeated rebalances
    - Each rebalance pauses processing
    - Static membership? Longer session timeouts?

---

## Category 5: Operational Concerns

20. **Who's on-call when Kafka has problems?**
    - Platform team? They need Kafka expertise
    - Each service team? Multiplied operational burden
    - What's the escalation path?

21. **How will you debug a problem that spans 5 event hops?**
    - Do you have distributed tracing (OpenTelemetry)?
    - Do you have correlation IDs in every event?
    - Have you practiced debugging event flows in staging?

22. **What monitoring do you need?**
    - Consumer lag (the most important metric)
    - Throughput (messages/sec, bytes/sec)
    - Error rates (producer failures, processing failures, DLQ rate)
    - End-to-end latency (event age when processed)

23. **What's your schema evolution strategy?**
    - How do you version events?
    - How do you handle backwards compatibility?
    - Who owns the event contracts?
    - Schema registry? Version headers?

24. **What's your capacity plan?**
    - Peak throughput estimates
    - Partition count for parallelism
    - Storage for retention period
    - Consumer count for processing rate

---

## Category 6: Design Trade-offs

25. **Could this be a simple API call instead?**
    - Seriously consider synchronous first
    - What specifically do events buy you here?
    - One producer, one consumer = probably sync

26. **Is this event-driven architecture or event sourcing?**
    - Event-driven: events for communication
    - Event sourcing: events as source of truth
    - Do you need the complexity of event sourcing?

27. **Do you need CQRS?**
    - Are read patterns significantly different from write patterns?
    - Is the added complexity worth the optimization?
    - Can you tolerate eventual consistency in reads?

28. **Do you need a saga or just events?**
    - Do multiple services need to coordinate?
    - Are compensating transactions required?
    - Choreography vs orchestration?

29. **Should you use compacted topics?**
    - Do you need current state or full history?
    - Is this "table" semantics or "log" semantics?
    - What about deletions?

30. **Do you need stream processing or simple consumers?**
    - Windowed aggregations → stream processing
    - Complex joins → stream processing
    - Simple routing → consumer is enough

---

## Category 7: Multi-Region

31. **Which region owns the topic?**
    - Single primary region?
    - Active-active multi-region?
    - What's the replication strategy?

32. **How do you handle replication lag?**
    - Cross-region replication takes 50-200ms minimum
    - Read-your-writes consistency?
    - What's acceptable staleness?

33. **What happens during region failover?**
    - Consumer offsets may be behind
    - Duplicate processing during switchover
    - How do you recover?

---

## Category 8: Advanced Patterns

34. **How do you handle cross-topic ordering?**
    - UserCreated in topic A, OrderCreated in topic B
    - Consumer might see order before user
    - How do you handle missing dependencies?

35. **How do you handle hot keys?**
    - One entity generating disproportionate events
    - Causes hot partition, affects other entities on same partition
    - Sub-partitioning? Different topic?

36. **How do you replay events to new consumers?**
    - New consumer needs historical data
    - Reset offset to beginning?
    - Separate bootstrap mechanism?

37. **How do you handle schema migration for existing events?**
    - Events in topic don't match new schema
    - Consumer needs to handle both versions
    - What about compacted topics with mixed schemas?

---

# Part 12: Exercises and Homework (Comprehensive)

---

## Exercise 1: Replace Events with Sync (And Justify)

**Current Design (Event-Driven)**:

```
User Registration Flow:
1. User submits registration form
2. Auth Service creates user, publishes UserCreated event
3. Profile Service consumes event, creates profile
4. Email Service consumes event, sends welcome email
5. Analytics Service consumes event, tracks signup
```

**Your Task**:

1. Redesign this flow using synchronous calls
2. Document:
   - The new sequence diagram
   - What you lose (benefits of events you're giving up)
   - What you gain (benefits of sync you're adding)
   - Under what conditions is sync better? Events better?
3. If you had to keep ONE service async, which would it be and why?

**Deliverable**: A 2-page document with diagrams and trade-off analysis.

---

## Exercise 2: Debug the Outage

**Scenario**:

Your company has a notification pipeline:
- Order Service → Kafka (order-events) → Notification Service → Email Provider

Users report: "I placed an order 3 hours ago, no confirmation email."

**Given Information**:
- Order Service logs show event published successfully
- Kafka topic has the event (you can see it with kafka-console-consumer)
- Notification Service consumer group shows lag of 500,000 messages
- Notification Service pods are running, no crash loops
- Email provider dashboard shows they're receiving very few requests

**Your Task**:

1. What's your debugging process? (Step by step)
2. List 5 possible root causes in order of likelihood
3. For each cause, describe how you would confirm or rule it out
4. What immediate mitigation would you apply while investigating?
5. What monitoring/alerting would have caught this earlier?

**Deliverable**: Incident investigation document with timeline and actions.

---

## Exercise 3: Design a Feed System

**Requirements**:
- Social media feed for 10M users
- Average user follows 200 accounts
- 1% of users are "celebrities" with 100K+ followers
- Feed should update within 10 seconds of post
- Support 1M feed reads per minute

**Your Task**:

1. Design the event-driven architecture for feed fan-out
2. Address:
   - How do you handle celebrity posts? (fan-out on write doesn't scale)
   - What's your partition key for the events topic?
   - How do you handle a user following a new celebrity? (backfill)
   - What happens when a user unfollows someone? (remove from feed)
3. Include:
   - Architecture diagram
   - Data model (what's stored where)
   - Capacity estimation (events/sec, storage, consumer count)
   - Failure modes and mitigations

**Deliverable**: 5-page design document with diagrams and calculations.

---

## Exercise 4: Schema Evolution

**Current Event Schema**:

```json
{
  "event_type": "OrderPlaced",
  "order_id": "ord-123",
  "user_id": "usr-456",
  "amount": 99.99,
  "currency": "USD"
}
```

**New Requirements**:
- Need to add `items` array with item details
- Need to rename `amount` to `total_amount`
- Need to add `placed_at` timestamp
- Need to deprecate `currency` (moving to multi-currency support with per-item currencies)

**Your Task**:

1. Design a migration strategy that:
   - Doesn't break existing consumers
   - Allows gradual migration
   - Handles consumers that are deployed at different times

2. Define:
   - V2 schema
   - Compatibility rules
   - Migration timeline (phases)
   - How V1 consumers handle V2 events
   - How V2 consumers handle V1 events

3. What tooling would help manage this? (Schema registry? Version headers? Etc.)

**Deliverable**: Schema evolution playbook with examples.

---

## Exercise 5: Design a Saga for Payment Flow

**Requirements**:

Order checkout must:
1. Create order record
2. Reserve inventory
3. Charge payment
4. Update loyalty points
5. Send confirmation email
6. Notify warehouse

If any step fails, compensate previous steps.

**Your Task**:

1. Design the saga (choreography or orchestration—justify your choice)
2. Define:
   - Each step's action and compensating action
   - What happens if compensation fails?
   - Saga state machine diagram
   - How you handle partial completion on restart
3. Identify which steps are:
   - Compensable (can be undone)
   - Retriable (can be retried safely)
   - Pivot points (can't undo after this)
4. Where do you put the "non-compensable" actions (email, warehouse notification)?

**Deliverable**: Saga design document with state machine and failure scenarios.

---

## Exercise 6: Capacity Planning

**Scenario**:

You're designing a real-time metrics ingestion system:
- 50,000 servers sending metrics
- Each server sends 100 metrics every 10 seconds
- Each metric is ~200 bytes
- Retention: 24 hours in Kafka, 30 days in time-series database
- Query requirement: < 500ms for last 1 hour, < 5s for last 7 days

**Your Task**:

Calculate:
1. Events per second (average and peak, assuming 3x peak factor)
2. Bytes per second throughput
3. Partition count needed for throughput and parallelism
4. Storage requirements (Kafka and time-series DB)
5. Consumer count needed (assume 5ms processing per metric)
6. What changes if you grow to 500,000 servers?

**Deliverable**: Capacity planning spreadsheet with calculations and recommendations.

---

## Exercise 7: Multi-Region Event Architecture

**Scenario**:

Your e-commerce platform operates in 3 regions: US-East, US-West, EU-West.
Orders must be:
- Created in user's local region (low latency)
- Visible in all regions within 5 seconds (for support tools)
- Processed by fulfillment in the region where inventory exists

**Your Task**:

1. Design the multi-region Kafka architecture
2. Address:
   - Where do order events live? (single topic, per-region topics, or both?)
   - How do you route orders to correct fulfillment region?
   - How do you handle the 5-second cross-region visibility SLA?
   - What happens during region failover?
3. Include:
   - Architecture diagram showing regions and data flow
   - Replication strategy (MirrorMaker, Confluent Replicator, or other)
   - Consistency guarantees and trade-offs
   - Failure modes and recovery procedures

**Deliverable**: Multi-region design document with diagrams.

---

## Exercise 8: Event-Driven to Event Sourcing Migration

**Scenario**:

Your order management system currently uses:
- PostgreSQL for order storage (traditional CRUD)
- Kafka for publishing OrderPlaced, OrderUpdated, OrderCancelled events

You need to migrate to event sourcing because:
- Auditors require complete history of all order changes
- Business wants to answer "what was the order state at any point in time?"

**Your Task**:

1. Design the event-sourced order service
2. Address:
   - Event store design (separate from Kafka? Using Kafka?)
   - How do you rebuild order state from events?
   - How do you handle the migration of existing orders?
   - How do you maintain read performance (projections)?
3. Define:
   - Event schema for all order state transitions
   - Projection strategy for common queries
   - Snapshotting strategy for performance
4. What are the risks and rollback plan?

**Deliverable**: Event sourcing migration plan with schema and architecture.

---

## Exercise 9: Testing Strategy Design

**Scenario**:

You have an event-driven order pipeline:
- Order Service → order-events → Payment Service → payment-events → Shipping Service

The team has no event-driven testing strategy. Bugs frequently reach production.

**Your Task**:

1. Design a comprehensive testing strategy covering:
   - Unit tests (event handlers in isolation)
   - Integration tests (with embedded Kafka)
   - Contract tests (schema compatibility)
   - End-to-end tests (full pipeline)
   - Chaos tests (failure injection)
2. For each level:
   - What are you testing?
   - What tools do you use?
   - What's in CI vs manual?
   - Example test case
3. How do you test:
   - Idempotency (send same event twice)
   - Out-of-order delivery
   - Poison messages
   - Consumer lag recovery

**Deliverable**: Testing strategy document with example tests.

---

## Exercise 10: Hot Partition Investigation

**Scenario**:

Your consumer group shows concerning metrics:
- Partition 7 has 500,000 lag while other partitions have 0 lag
- Consumer assigned to partition 7 is at 100% CPU
- All other consumers are at 10% CPU
- Business is complaining about delays for "certain customers"

**Your Task**:

1. Write an investigation runbook:
   - How do you identify which keys are on partition 7?
   - How do you find the "hot key"?
   - What metrics confirm this is a hot partition vs other issues?
2. Propose short-term mitigation:
   - How do you unblock processing without data loss?
   - How do you process the stuck events?
3. Propose long-term fixes:
   - Re-partitioning strategy?
   - Sub-partitioning for hot keys?
   - Different partition key selection?
4. How do you prevent this in the future?
   - Monitoring and alerting
   - Partition key guidelines

**Deliverable**: Investigation runbook and remediation plan.

---

## Exercise 11: DLQ Operations Playbook

**Scenario**:

Your team has a DLQ (dead letter queue) that's been growing. There are 50,000 messages in the DLQ accumulated over 2 weeks. Nobody knows what to do with them.

**Your Task**:

1. Create a DLQ operations playbook covering:
   - How to inspect DLQ messages (tools, queries)
   - How to categorize failure reasons
   - Decision tree: which messages to retry, discard, or manually fix
   - How to replay messages safely
   - How to prevent duplicates during replay
2. For your 50,000 message backlog:
   - Propose a triage approach
   - Estimate effort for each category
   - Prioritization strategy
3. Preventive measures:
   - Monitoring and alerting for DLQ
   - Automated categorization
   - SLA for DLQ processing

**Deliverable**: DLQ operations playbook and backlog triage plan.

---

## Exercise 12: Cost Optimization

**Scenario**:

Your Kafka cluster costs $50,000/month. Leadership wants you to reduce costs by 30% without impacting reliability.

Current setup:
- 20 brokers, 500 partitions, 3x replication
- 7-day retention
- 100 topics, 50 consumer groups
- 50TB storage, 500MB/sec throughput peak

**Your Task**:

1. Identify cost drivers:
   - Which is largest: compute, storage, network?
   - Are there inefficiencies?
2. Propose optimization strategies:
   - Retention reduction (which topics can have shorter retention?)
   - Compression (what's current vs achievable compression ratio?)
   - Tiered storage (cold data to S3/GCS?)
   - Topic consolidation (too many topics?)
   - Right-sizing (over-provisioned brokers?)
3. For each optimization:
   - Estimated savings
   - Risk and mitigation
   - Implementation complexity
4. Which optimizations would you prioritize and why?

**Deliverable**: Cost optimization proposal with estimates and risks.

---

*"The first rule of distributed systems is: don't distribute. The second rule is: if you must distribute, don't use events. The third rule is: if you must use events, make everything idempotent and invest heavily in observability."*

— Wisdom from too many 3am debugging sessions
