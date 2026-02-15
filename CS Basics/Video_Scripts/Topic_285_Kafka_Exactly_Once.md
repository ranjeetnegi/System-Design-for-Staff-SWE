# Kafka Exactly-Once: What It Means and Where It Stops

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

ATM machine. You withdraw Rs 10,000. The machine debits your account. Then it jams. Cash doesn't come out. You press the button again. Without exactly-once: your account gets debited TWICE. Rs 20,000 gone. Cash? Maybe once. Maybe zero. Chaos. With exactly-once: the system knows the first attempt already happened. The second press is a no-op. Rs 10,000 debited once. Cash dispensed once. Exactly-once in messaging means: each message is processed EXACTLY once. Not zero. Not twice. Once. Let's see how Kafka does it—and where it stops.

---

## The Story

Messaging has three delivery semantics. **At-most-once:** send the message, maybe process it, maybe lose it. Fast. Risky. **At-least-once:** guarantee delivery. Might retry. Might process twice. Duplicates possible. **Exactly-once:** process once. No loses. No duplicates. Perfect. Expensive.

Kafka supports exactly-once (EOS). How? **Producer idempotence:** each producer gets an ID. Each message gets a sequence number per partition. If the producer retries (network glitch, timeout), Kafka sees the same producer ID + sequence. It deduplicates. Only one copy lands. **Transactions:** produce to multiple partitions, or produce-and-consume atomically. Commit or abort. All or nothing.

But here's the limit: exactly-once works WITHIN Kafka. Producer → Kafka → consumer. If your consumer reads from Kafka and writes to MySQL, that's a different world. Kafka says "I delivered once." MySQL says "I got one write." But what if the consumer commits the Kafka offset after the MySQL write, and then crashes before the commit goes through? Restart: consumer reads the same message again. Writes to MySQL again. Duplicate. Kafka's exactly-once doesn't extend to your database. You need idempotent writes (e.g., upsert by ID) or distributed transactions. The boundary matters.

---

## Another Way to See It

A courier guarantees exactly-once delivery to your doorstep. The package arrives once. Perfect. But you take the package and put it in your filing cabinet. You get distracted. You forget whether you filed it. You check. You don't see it. You take the package again and file it. Now you have two copies. The courier did their job. Your filing didn't. Exactly-once at the doorstep doesn't mean exactly-once in the cabinet. Kafka is the doorstep. Your database is the cabinet. Bridge the gap yourself.

---

## Connecting to Software

**Kafka EOS features:** idempotent producer (no duplicates on retry), transactional producer (atomic multi-partition writes), read-process-write with consumer transaction (consume, process, produce, and commit offset atomically within Kafka). All good. All within Kafka.

**External systems:** consumer writes to MySQL, DynamoDB, external API. No Kafka transaction. You need: (1) idempotent consumers—same message processed twice = same effect (e.g., upsert by business key). (2) Or: two-phase commit / Saga—complex, rarely worth it. (3) Or: store offset and output in same DB transaction—consume, write to DB with offset, commit in one transaction. On restart, read offset from DB. Don't commit Kafka offset until DB commits. At-least-once delivery + idempent processing = effectively exactly-once.

---

## Let's Walk Through the Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│              KAFKA EXACTLY-ONCE: WHERE IT WORKS                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   WITHIN KAFKA (EOS works):                                              │
│   ┌─────────┐    idempotent     ┌─────────┐    transactional   ┌───────┐│
│   │Producer │ ────────────────► │ Kafka   │ ◄───────────────── │Consumer││
│   │         │    no duplicates  │         │   read-process-    │       ││
│   └─────────┘                   └─────────┘   write, atomic    └───┬───┘│
│                                                                     │    │
│   BOUNDARY (EOS stops):                                              │    │
│                                                                     ▼    │
│                                                              ┌─────────┐│
│                                                              │ MySQL   ││
│                                                              │ External││
│                                                              └─────────┘│
│   Kafka delivered once. But: if offset commit fails after MySQL write,  │
│   restart = reprocess = duplicate write. Need idempotent DB writes.     │
└─────────────────────────────────────────────────────────────────────────┘
```

The dashed line is where Kafka's guarantee ends. Your design must handle the rest.

---

## Real-World Examples

**Payment processing:** consume "payment initiated," write to DB, send to payment gateway. Use idempotency key (payment_id) on the external call. If duplicate consume, gateway sees same key, returns same result. No double charge. Idempotent by design.

**Event sourcing:** consume events, update materialized view. Use event_id as primary key for the view table. Same event twice → same upsert → same state. Idempotent. The view is the source of truth; replaying events always yields the same result.

**Sync to search:** consume record changes, update Elasticsearch. Use document ID. Same record twice → same document. Idempotent. Exactly-once semantics without Kafka transactions to the search engine. The document ID is your idempotency key.

---

## Let's Think Together

**"Consumer reads from Kafka, writes to MySQL, commits Kafka offset. If MySQL write succeeds but offset commit fails, what happens?"**

Answer: On restart, the consumer has no record of the offset commit. It will read from the last committed offset—which is before this message. So it reads the same message again. It writes to MySQL again. Duplicate. The fix: make the MySQL write idempotent. Use a unique key (e.g., event_id). Upsert. Second write = same effect. Or: use a transaction that includes both the MySQL write and storing the offset (e.g., in a Kafka consumer offsets table or in the same DB). Commit both atomically. Then committing to Kafka (or not) doesn't matter—you've recorded completion in your own store. Design for at-least-once delivery, idempotent processing.

---

## What Could Go Wrong? (Mini Disaster Story)

A billing system consumed "subscription renewed" events and charged the customer. No idempotency. Kafka had a rebalance. Same message processed twice. Customer charged twice. Refunds, apologies, churn. The fix: add a unique constraint on (customer_id, billing_cycle, event_id). Second insert fails. Or use upsert. Or check "already processed" before charging. Idempotency is not optional when the consumer talks to external systems.

---

## Surprising Truth / Fun Fact

Kafka's transactional producer has a small performance cost. Some high-throughput pipelines use idempotent producer (no duplicates) but skip full transactions. For single-partition produce, idempotence is often enough. For exactly-once consume-process-produce within Kafka (e.g., Kafka Streams), transactions are the way. Know the tradeoff: stronger semantics, slightly more latency.

---

## Quick Recap (5 bullets)

- **Exactly-once** = each message processed once; no loss, no duplicates.
- **Kafka EOS:** idempotent producer, transactions; works within Kafka (produce → Kafka → consume).
- **Limit:** Kafka's guarantee stops at the consumer; external DB/API needs your design.
- **External systems:** use idempotent writes (upsert by key, idempotency keys) or store offset+output in one transaction.
- **Practical:** design for at-least-once; make processing idempotent; achieve effectively exactly-once.

---

## One-Liner to Remember

*"Kafka guarantees exactly-once within Kafka. Beyond that, idempotency is your guarantee."*

---

## Next Video

Up next: **When Kafka Is Overkill**—sometimes you need a moving truck for a package that fits in your hand. We'll see when SQS, Redis, or a simple API call is enough.
