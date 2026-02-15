# Event Sourcing vs Event-Driven (The Difference)
## Video Length: ~4-5 minutes | Level: Staff
---
## The Hook (20-30 seconds)

Two restaurants. Restaurant A (event-driven): when a customer orders, a BELL rings in the kitchen. The kitchen hears the bell and starts cooking. The bell is a SIGNAL — "something happened, react to it." Restaurant B (event sourcing): the customer's order is written on a RECEIPT. Every receipt is STORED forever. To know the restaurant's history: read ALL receipts. To rebuild current menu popularity: replay all receipts. The receipt is the SOURCE OF TRUTH. Same word — "event." Different meanings. One is a signal. One is a record. Let's unpack it.

---

## The Story

You hear "event-driven architecture" and "event sourcing." They sound similar. Both use events. Both are trendy. But they solve different problems. Event-driven: something happens, you react. Publish an event. A service subscribes. Sends a welcome email. Updates a cache. The event is a NOTIFICATION. It might be stored. It might not. The current state lives in the database. Event sourcing: the event IS the database. You never store "current balance = 1250." You store "Account created. +500. -200. +1000. -50." To get current balance: replay. Sum it up. Events are the source of truth. State is derived. Big difference.

---

## Another Way to See It

Think of a diary vs. a doorbell. Doorbell: someone rings. You react. Open the door. The ring isn't recorded. It was a signal. Event-driven. Diary: you write everything down. "Woke up. Had coffee. Went to work." The diary is the record. To know what you did: read the diary. Event sourcing. Same "thing happened" — but one triggers action, the other IS the record.

---

## Connecting to Software

**Event-driven.** Events are SIGNALS. "User signed up" → trigger welcome email. "Order placed" → notify warehouse. Services REACT. The event says "something happened." It may or may not be stored. The current state is in the database. Events are notifications. Fire and forget (or persist for retry). Loose coupling. Services don't call each other directly. They listen.

**Event sourcing.** Events are the SOURCE OF TRUTH. State is DERIVED by replaying events. "Account created" → "Deposited 500" → "Withdrew 200" → "Deposited 1000." Current balance = 1300. You don't store 1300. You store the events. Replay to get state. Events are NEVER deleted (usually). You can rebuild any state at any point in time. Full history. Audit trail. Time travel.

**Key difference.** Event-driven = react to events. Event sourcing = store ALL events as the primary data model. One is about communication. One is about storage.

**When event sourcing:** Audit trail (financial, legal), temporal queries ("what was the state at 3 PM?"), debugging (replay to reproduce bugs), CQRS (command and query separation). When you need history. When you need to replay.

**When event-driven (not sourcing):** Simple notification patterns. Loose coupling. React to changes. Don't need full history. Microservices talking. Async workflows. "User signed up — send email." You don't need to store every signup event forever. The user record in the database is the source of truth. The event is just a signal. Use the right tool for the job. Not every system needs event sourcing. Most don't. But when you need audit, compliance, or time travel — event sourcing shines.

---

## Let's Walk Through the Diagram

```
    EVENT-DRIVEN
    ───────────
    Service A: "User signed up"
              │
              │  publish event
              ▼
    ┌─────────────────┐
    │  Message Queue  │  (event may or may not be stored long-term)
    └────────┬────────┘
              │
     ┌───────┼───────┐
     ▼       ▼       ▼
   Email   Cache   Analytics  (react, update their own state)
   
   State lives in: Email DB, Cache, Analytics DB. Event = signal.
   
    EVENT SOURCING
    ─────────────
    "Deposit +500" ──┐
    "Withdraw -200" ─┼──▶  Event Store (immutable, append-only)
    "Deposit +1000" ─┘              │
                                    ▼
                            Replay events
                                    │
                                    ▼
                            Current balance = 1300 (derived)
   
   State = replay of events. Event store = source of truth.
```

The diagram shows: event-driven spreads signals. Event sourcing accumulates records.

---

## Real-World Examples (2-3)

**Kafka as event-driven:** Order service publishes "OrderPlaced." Notification service consumes. Sends email. The event is a message. Notification service has its own DB. Event not the source of truth.

**Bank accounts as event sourcing:** "AccountCreated. +500. -200. +1000." Every transaction is an event. Balance = sum. Audit trail built-in. Regulators love it. Replay to any point in time.

**Uber (hybrid):** Trip events are sourced. Full history. Event-driven for real-time: "Driver arrived" → notify rider. Both patterns in one system.

---

## Let's Think Together

Bank account. Should you use event sourcing or event-driven? Hint: "Account created, +500, -200, +1000, -50" → current balance = replay.

**Answer:** Event sourcing is ideal. You need: audit trail (every transaction), correctness (balance = sum of events), regulatory compliance (prove what happened). Event-driven could NOTIFY other systems ("large withdrawal — send alert"). But the ledger itself? Event sourcing. Events are the source of truth. Replay to get balance. Never lose a transaction.

---

## What Could Go Wrong? (Mini Disaster Story)

A company built "event-driven" without event sourcing. Order service published "OrderPlaced." Payment service consumed. Updated its DB. A bug corrupted the payment DB. They had no event log. Couldn't replay. Couldn't rebuild. Data loss. They had to manually reconcile from the order service DB. Painful. If they'd used event sourcing for the payment ledger, they could have replayed. Lesson: For critical state (money, inventory), consider event sourcing. Events as source of truth = recovery is possible.

---

## Surprising Truth / Fun Fact

Event sourcing is older than you think. Double-entry bookkeeping (debits and credits) is essentially event sourcing. You don't store "balance = X." You store every transaction. Balance = sum. Accounting has done this for centuries. Software rediscovered it.

---

## Quick Recap (5 bullets)

- Event-driven: events are signals. React. Loose coupling. State in databases.
- Event sourcing: events ARE the source of truth. State = replay. Full history.
- Event-driven = communication pattern. Event sourcing = storage pattern.
- Use event sourcing for: audit, compliance, temporal queries, debugging.
- Use event-driven for: async workflows, microservices, simple reactions.

---

## One-Liner to Remember

**Event-driven: "Something happened — react." Event sourcing: "Something happened — store it forever. State is replay."**

---

## Next Video

**Congratulations.** You've made it. Three hundred twenty videos. From APIs to CRDTs. From rate limiters to event sourcing. You've walked through requirements gathering, system design, scaling, consistency, resilience, and so much more.

This isn't the end — it's the beginning. You now have a map. A vocabulary. A way of thinking. Go build. Build systems that scale. Build systems that don't break when things go wrong. Build systems that serve real people. You're ready.

Thank you for watching. Thank you for sticking with this journey. Go make something amazing.
