# Inbox / Idempotent Consumer: Avoiding Duplicates

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Ding-dong. "Package for you." You take it. Ding-dong. Same person. "Package for you." Again? You already got it. The system retried—no confirmation received. Without protection, you'd accept twice. Get charged twice. The inbox pattern: check "Did I already process this?" Yes → ignore. No → process and record. That's idempotent consumption.

---

## The Story

Your doorbell rings. Delivery person: "Package for you." You take it. Thank you. They leave. You go back to work. Five minutes later. Ding-dong. Same person. Back again. "Package for you." Wait—you already got it. What's happening? The delivery system didn't get your confirmation. Maybe the network dropped. Maybe the app crashed. So it retried. Standard practice. At-least-once delivery. Without protection, you'd accept again. Sign again. Two packages. Two charges. One order. Problem. The system did its job. It retried. You need to do yours. Check. "Did I already get this?" Yes. Decline. That's idempotent consumption. The inbox pattern makes it systematic.

The inbox pattern: before accepting, you check. "Have I already processed delivery ID 12345?" Look at your inbox—your record of processed IDs. Yes? "Already got it. Thanks." No? Accept. Record the ID. Next time: skip. Idempotent. Process once. Safe from retries. The key is the record. Without it, you have no memory. With it, you're protected. Duplicate delivery? Check. Skip. Same outcome. One package. One charge. One effect. The inbox is your defense against a chaotic world of retries and network failures.

---

## Another Way to See It

Think of a bouncer at a club. Every wrist gets a stamp. Same person tries to enter again? Bouncer checks the stamp. "Already in." Rejected. No double entry. The stamp is the inbox. The ID. Process once. Check before processing. Same idea in software. Message ID = stamp. Inbox = record of stamps. Idempotent entry.

---

## Connecting to Software

**Why duplicates happen:** Network retries. At-least-once delivery. Producer retries. Consumer crashes mid-processing—processes message, updates DB, dies before ACKing the queue. Queue re-delivers. Same message. Twice. Without protection: double charge, double order, double everything.

**Inbox table:** Store processed message IDs. Before processing: check if ID exists. Yes = skip. No = process + insert ID. In same transaction as your business logic. Atomic. Process and record together. If you process but fail to insert—transaction rolls back. Retry. Process again. Eventually both succeed. Next delivery of same ID: skip. Safe. The inbox can be a simple table. message_id primary key. Maybe a processed_at timestamp. Minimal. The pattern does the work. Implementation is straightforward. The thinking—"we need this"—is the hard part.

**Idempotent consumer:** Design the handler so processing the same message twice has the same effect as once. "Add Rs 100 to balance" is NOT idempotent. Twice = Rs 200. Wrong. "Set balance to Rs 500 for transaction T123" IS idempotent. Check T123. Already applied? Skip. Same result. The trick: make operations deterministic by transaction ID. Or use upsert. "Insert or update" based on key. Second run: no change. Idempotent. Another approach: store the result. Duplicate request? Return the stored result. No second side effect. Both work. Choose based on your domain. The goal: same message, many times; same effect, once.

---

## Let's Walk Through the Diagram

```
    INBOX PATTERN

    [Kafka] --- Message (id=abc123) ---> [Consumer]
                                              |
                                              | 1. Check inbox: abc123?
                                              |    No.
                                              | 2. Process message
                                              | 3. Insert abc123 into inbox
                                              | 4. Commit (DB + offset)
                                              |
    [Kafka] --- Same message (retry) ---> [Consumer]
                                              |
                                              | 1. Check inbox: abc123?
                                              |    Yes. Skip.
                                              | 2. ACK. Done.
```

First time: process. Record. Second time: skip. Same outcome. Idempotent.

---

## Real-World Examples (2-3)

**Example 1: Payment processing.** Message: "Charge customer X, Rs 500, id=pay_123." Without inbox: retry = double charge. With inbox: check pay_123. Processed? Return same result. Skip. Customer charged once. Safe.

**Example 2: Order creation.** Message: "Create order for user Y, id=ord_456." Without inbox: retry = duplicate order. With inbox: check ord_456. Exists? Return existing order. Skip insert. One order. Idempotent.

**Example 3: Email send.** Message: "Send welcome email to Z, id=mail_789." Without inbox: retry = two emails. User confused. "Why two welcome emails?" With inbox: check mail_789. Sent? Skip. One email. Happy user. Same pattern everywhere. Notification service. Webhook delivery. Cache invalidation. Any operation that shouldn't run twice. Inbox. Or idempotency keys. Same idea. Defensive design. Assume the message will arrive more than once. Be ready.

---

## Let's Think Together

**Consumer processes message, updates DB, but crashes before ACKing the message queue. Queue re-delivers. What happens without inbox pattern?**

Consumer gets same message again. Processes again. Double update. Double charge. Double order. Disaster. With inbox: first run—process, insert ID, crash before ACK. Second run: message re-delivered. Check inbox. ID exists. Skip processing. ACK. Done. Same logical effect as one process. Idempotent. Inbox saves you.

---

## What Could Go Wrong? (Mini Disaster Story)

A payments team trusted "we only deliver once." They didn't implement idempotency. One day: Kafka had a bug. Replayed a partition. Old messages. Consumer processed. Same payment IDs. Duplicate charges. Millions. Refunds. Lawsuits. Lesson: never trust "exactly once" delivery. Always design for at-least-once. Inbox. Idempotency. Assume duplicates. Protect yourself.

---

## Surprising Truth / Fun Fact

Kafka's "exactly-once semantics" doesn't mean the broker delivers once. It means: idempotent producer (no duplicate sends) + transactional consumer (commit offset with DB in one transaction). Under the hood: at-least-once delivery + idempotent processing. The name is marketing. The pattern is inbox + careful design.

---

## Quick Recap (5 bullets)

- **Duplicates happen:** Retries, at-least-once, consumer crashes. Assume it.
- **Inbox:** Store processed message IDs. Check before process. Skip if seen.
- **Idempotent design:** Same message twice = same effect. Use IDs. Check. Skip.
- **Atomic:** Process and insert inbox in same transaction. All or nothing.
- **Always:** Design for at-least-once. Inbox. Idempotency. Never assume once.

---

## One-Liner to Remember

**Inbox: Check before process. Seen it? Skip. New? Process and record. Idempotent. Duplicate-safe.**

---

## Next Video

We keep saying at-least-once. What about at-most-once? Or exactly-once? Delivery semantics. What they mean. When to use each. That's next. See you there.
