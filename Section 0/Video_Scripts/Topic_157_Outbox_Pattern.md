# Outbox Pattern: Reliable Event Publishing

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You write a letter. And you put a note on the community board. Two actions. What if you write the letter and forget the board? Or update the board but never mail the letter? They must happen together. In software: you save to the database and publish to Kafka. DB save succeeds. Kafka publish fails. Data saved. Event lost. Systems diverge. There's a pattern that fixes this.

---

## The Story

You write a letter. At the same time, you're supposed to put a note on the community board: "Letter sent to X." Two actions. Independent. What if you write the letter and forget to update the board? The board is wrong. People think you didn't send it. What if you update the board but forget to mail the letter? The board says "sent." It wasn't. Someone might act on bad info. They must happen together. Atomically. But you can't make the board and the post office one system. In software: you save an order to the database. And you publish an event to Kafka: "OrderCreated." Two systems. Database. Message broker. No atomic guarantee across them. DB save succeeds. Kafka publish fails. Your database has the order. Kafka doesn't. Downstream services never hear. Data inconsistency. Orders without events. Events without orders. Chaos. The outbox pattern solves this: write BOTH the data AND the event to the SAME database. One transaction. Atomic. The database is the single source of truth. Then a separate process reads the outbox and publishes to Kafka. Guaranteed. Eventually consistent with the broker. But the source of truth is solid.

---

## Another Way to See It

Think of a mailbox. You don't hand the letter to the postman directly. You put it in YOUR mailbox. One place. You control it. The mail carrier comes later. Picks it up. Delivers. Your mailbox is the outbox. The letter is safe until it's picked up. If the carrier fails today, the letter is still there. Tomorrow. Same idea. Write to your outbox. Poll later. Publish when you can. No dual-write. No lost events.

---

## Connecting to Software

**The problem: Dual write.** App writes to DB. App publishes to Kafka. Two operations. Not atomic. DB succeeds, Kafka fails? Event lost. Kafka succeeds, DB fails? Orphan event. Downstream acts on data that doesn't exist. Mess.

**The solution: Outbox table.** Same database as your business data. One transaction: (1) Insert/update your business row. (2) Insert a row into the `outbox` table with the event payload. Both in one transaction. ACID. If the transaction commits, both are there. If it fails, neither is. Atomic. Then: a separate "relay" process (polling or CDC) reads from the outbox. Publishes to Kafka. Marks the row as "published" or deletes it. At least once to Kafka. Idempotent consumers handle duplicates. Event is guaranteed to be published. Eventually. The magic: one write. Two logical outputs. The database is the single source of truth. The outbox is part of that truth. No dual-write. No race. No lost events. Just a relay that might be slow. But reliable. Very reliable. This pattern is used by Uber, Netflix, many others. It's battle-tested. When you need reliable event publishing from a database, outbox is the answer.

---

## Let's Walk Through the Diagram

```
    OUTBOX PATTERN

    [App] -------- 1. Write order + outbox event -------> [DB]
      |                    (single transaction)              |
      |                                                      |
      |                                                      | 2. Poll / CDC
      |                                                      v
      |                                              [Outbox Relay]
      |                                                      |
      |                                                      | 3. Publish
      |                                                      v
      |                                                 [Kafka]
      |                                                      |
      |                                                      | 4. Mark published
      |                                                      |
                                                         Done.
```

One write. Two logical outputs. Atomic. Relay handles the rest. Kafka gets the event. Guaranteed.

---

## Real-World Examples (2-3)

**Example 1: Order service.** Create order. Publish OrderCreated. Without outbox: DB commit, Kafka fail. Order exists. No event. Payment service never knows. With outbox: order + event in one transaction. Relay publishes. Payment service gets event. Eventually consistent. Reliable.

**Example 2: User registration.** Save user. Send "UserRegistered" event. Notification service listens. Without outbox: user saved, event lost. No welcome email. With outbox: user + event in DB. Relay publishes. Welcome email sent. Guaranteed.

**Example 3: Inventory update.** Decrement stock. Publish "InventoryUpdated." Search index must update. Without outbox: stock updated, event lost. Search index stale. With outbox: both in DB. Relay publishes. Search index updates. Consistent.

---

## Let's Think Together

**The relay crashes after reading from outbox but before publishing to Kafka. What happens when it restarts?**

The outbox row is still there. Unpublished. Or maybe "in progress." On restart, the relay polls again. Reads the row. Publishes. Marks done. No loss. The key: don't delete the row until Kafka confirms. Or use "published" flag. If relay dies mid-publish, the row stays. Restart. Retry. Idempotent consumers handle duplicate delivery. Safe.

---

## What Could Go Wrong? (Mini Disaster Story)

A team implemented outbox. But the relay deleted rows immediately after reading—before Kafka confirmed. Relay crashed. Row gone. Event never published. Downstream never got it. Data permanently inconsistent. Lesson: mark published only after Kafka ACK. Or use transactional outbox with CDC (Debezium). Don't delete too early. Reliability over neatness.

---

## Surprising Truth / Fun Fact

Debezium can read from your database's transaction log (WAL/binlog) and emit changes. No polling. Real-time. Use your outbox table. Debezium streams inserts to Kafka. Outbox + CDC = no relay process. Simpler. Kafka Connect has Debezium connector. Battle-tested. Netflix, Uber use similar patterns.

---

## Quick Recap (5 bullets)

- **Problem:** Dual write to DB + Kafka. Not atomic. One can fail. Data and events diverge.
- **Solution:** Write data + event to same DB in one transaction. Outbox table.
- **Relay:** Separate process reads outbox, publishes to Kafka, marks done.
- **Guarantee:** At least once delivery. Idempotent consumers handle duplicates.
- **CDC option:** Debezium reads outbox from WAL. No polling. Real-time.

---

## One-Liner to Remember

**Outbox: One transaction. Data + event in same DB. Relay publishes. No dual-write. No lost events.**

---

## Next Video

Events are published. But what if the consumer gets the same event twice? Retries. At-least-once delivery. Duplicates. The inbox pattern. Idempotent consumers. Avoiding double processing. That's next. See you there.
