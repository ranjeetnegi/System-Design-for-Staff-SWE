# Event Sourcing: High-Level Idea

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

Traditional banking: your balance is Rs 50,000. That's it. One number. Event sourcing: "Deposited Rs 10,000 on Jan 1. Withdrew Rs 5,000 on Jan 5. Deposited Rs 45,000 on Jan 10." The history is the source of truth. Current balance is derived by replaying events. You can reconstruct ANY past state by replaying events up to that point. Like a bank ledger vs a balance sheet.

---

## The Story

Normal persistence: you store the current state. Balance = 50,000. Update it when something changes. Overwrite. The past is gone. Event sourcing: you store the events. Every change is an event. "Order Placed." "Payment Received." "Item Shipped." Append-only. Never delete. Current state = replay all events from the beginning. Or: maintain a "projection" (materialized view) for fast reads, but the event log is the source of truth.

Why? Audit trail. What happened, when, in what order. Perfect. Debugging: "why is the balance wrong?" Replay events. Find the bug. Time travel: what was the state at 3 PM yesterday? Replay events up to that timestamp. New read model: want a new view of the data? Replay events, build it. No schema migration on the event store. Events are immutable. Add consumers. Rebuild. Flexible.

Trade-offs: event store grows forever. Need compaction, snapshots, or retention policy. Replay can be slow for long histories—snapshots help. Event schema evolution: adding fields, handling old events. Versioning. Consistency: multiple writers? Ordering? Idempotency. Complex. But powerful for the right domains.

**Snapshots and compaction:** Event store grows forever. Replaying 10 years of events is slow. Solution: periodic snapshots. "State after event 1M = X." To rebuild, load snapshot, replay from 1M onward. 10x faster. Or: archive old events. Keep last 1 year hot. Rest in cold storage. Compaction policies. Event sourcing at scale requires this discipline.

**When not to use:** Simple CRUD. No audit need. No time travel. No multiple read models. Overkill. Event sourcing adds storage (every change stored), complexity (replay, versioning), and operational overhead. Use when the benefits—audit, flexibility, debugging—justify it. Finance, healthcare, compliance. Not a todo app.

**Idempotency:** Same event delivered twice? Consumer must handle it. Idempotency key in event. "I've already processed event ID 123. Skip." Or: event is deterministic. Processing twice yields same result. Design for at-least-once delivery. Duplicates will happen. Idempotent consumers are mandatory.

---

## Another Way to See It

Think of a video game save. Normal: save current state. Health, position, inventory. One file. Event sourcing: save the replay. Every move, every action. To "load," replay the tape. Same result. But now you can rewind. "What was my position 10 minutes ago?" Replay to that point. Or branch: replay to checkpoint, then different actions. Event sourcing is the "replay tape" of your domain.

Or a chess game. You don't store "current board state" after each move. You store the moves. e4, e5, Nf3. Replay to get any position. The move log is the source of truth. Event sourcing.

---

## Connecting to Software

Technically: event store is an append-only log. Kafka, EventStore, or a simple table with (id, aggregate_id, event_type, payload, timestamp, version). Append. Never update. Consumers read the stream. They maintain projections: "current balance" table built by replaying AccountDebited, AccountCredited events. Or they process in real time. CQRS often pairs with event sourcing: write = append event. Read = query projection.

Snapshots: periodically store "state after event 1,000,000." To rebuild, load snapshot, replay events after. Faster than full replay. Essential for long-lived aggregates.

---

## Let's Walk Through the Diagram

```
    TRADITIONAL (State)                    EVENT SOURCING (Events)

    ┌─────────────┐                        ┌─────────────────────────────┐
    │  Balance:   │                        │ Event Log (append-only)     │
    │  50,000     │                        │ 1. Deposited 10,000         │
    │             │                        │ 2. Withdrew 5,000            │
    │  (overwrite)│                        │ 3. Deposited 45,000          │
    └─────────────┘                        └──────────────┬──────────────┘
                                                          │
    Past state? Gone.                                     │ Replay
                                                          ▼
                                                 ┌─────────────────┐
                                                 │ Current balance │
                                                 │ = 50,000        │
                                                 └─────────────────┘
                                                 Past state? Replay to that point.
```

---

## Real-World Examples (2-3)

**Example 1: Banking, accounting.** Ledgers are event sourcing. Every transaction is a line. Balance = sum of lines. Audit: show the lines. Regulators love it. Banks have done this for centuries. Software event sourcing digitizes the same idea.

**Example 2: Kafka as event log.** Many companies use Kafka for event-sourced workflows. Order service appends "OrderPlaced." Inventory, payment, shipping consume. Each builds its view. The topic is the event store. Durable. Replayable. Source of truth.

**Example 3: Version control (Git).** Commits are events. The repo state = replay commits. Branch? Replay to a point, different subsequent commits. History is immutable. Checkout any point. Event sourcing in disguise.

---

## Let's Think Together

**When is event sourcing overkill?**

When you don't need history, audit, or multiple read models. CRUD app. Simple state. Overwriting is fine. Event sourcing adds complexity. Storage. Replay logic. Schema evolution. Use it when the benefits (audit, time travel, flexibility) justify the cost. Finance, healthcare, compliance-heavy domains. Not every app.

**How do you handle event schema changes?**

Version events. "AccountCredited v1" has fields A, B. "AccountCredited v2" adds C. Consumers handle both. Or upcast: when reading old events, transform to new schema. Event store stays append-only. Consumers evolve.

---

## What Could Go Wrong? (Mini Disaster Story)

A team adopts event sourcing for orders. Great. Then they need to "correct" a bad event. "We shipped to wrong address. Fix it." They're tempted to "edit" the event. Don't. Events are immutable. Fix: append a new event. "OrderCorrected: new address." Consumers handle it. Or: append "OrderCancelled" and "OrderPlaced" (corrected). The log stays append-only. Editing would break replay. New events fix things. Lesson: immutability is core. Correct by appending, never by mutating.

---

## Surprising Truth / Fun Fact

Event sourcing isn't new. Double-entry bookkeeping (14th century) is event sourcing. Every transaction is a record. Balance is derived. Accounting has used this for centuries. Software "discovered" it again with CQRS and event-driven systems. Old idea, new context. Proven.

---

## Quick Recap (5 bullets)

- **Event sourcing** = store events (what happened), not just current state. Append-only. Immutable.
- Current state = replay events. Or maintain projections (materialized views) from events.
- Benefits: full audit trail, time travel, new read models without schema change, debugging by replay.
- Trade-offs: storage growth, replay cost (mitigate with snapshots), schema evolution, complexity.
- Use when: audit, compliance, complex domains with rich history. Overkill for simple CRUD.

---

## One-Liner to Remember

Event sourcing: the ledger, not the balance sheet. History is truth. Current state is derived.

---

## Next Video

Next up: **CQRS**—two counters at a restaurant. One for orders (writes). One for menu and status (reads). Optimize each. Separate. Powerful.
