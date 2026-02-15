# Delivery Semantics: At-Most-Once, At-Least-Once

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Sending wedding invitations. You mail it. If it's lost—oh well. Guest never gets it. You don't re-send. Or: you mail it. No confirmation? Send again. And again. Guest might get three copies. But they definitely get at least one. Two strategies. Two trade-offs. That's delivery semantics. And it shapes everything we build.

---

## The Story

Imagine sending wedding invitations. **At-most-once:** You put the letter in the mailbox. You walk away. If it's lost in the mail, too bad. The guest never gets it. You don't re-send. Fast. Simple. But data loss is possible. **At-least-once:** You send it. No confirmation? Send again. Still nothing? Send again. The guest might get three copies. Annoying. But they definitely get at least one. You don't stop until you know it arrived. **Exactly-once:** The guest gets exactly one. No more. No less. The holy grail. Sounds simple. In practice? Nearly impossible. But in distributed systems—with networks that fail, retries that happen, consumers that crash—exactly-once delivery as a primitive doesn't exist. We can't make the network guarantee it. But we can build exactly-once processing. With idempotency. With deduplication. We'll get there in the next video. First, understand the two we have. At-most-once. At-least-once. Choose wisely. Your system's reliability depends on it.

---

## Another Way to See It

Think of a courier. At-most-once: courier takes the package. Drops it once. No tracking. Lost? Your problem. At-least-once: courier tries. Fails? Tries again. You might get two packages. But you'll get one. Exactly-once: courier delivers exactly one. Magic. In reality, they use at-least-once plus "please return duplicate if you get two." That's idempotency. We'll get there.

---

## Connecting to Software

**At-most-once:** Fire and forget. Send the message. Don't wait for ACK. Don't retry. Fast. Simple. Low latency. But: if the network drops it, it's gone. Forever. Use for: metrics, logs, non-critical events. Where loss is acceptable. "Page view counter missed one? Fine. We have millions." "Temperature sensor missed a reading? Next one in a second." At-most-once is the cheapest. The fastest. And the least reliable. Choose consciously.

**At-least-once:** Retry on failure. Producer sends. No ACK? Send again. And again. Until confirmed. Consumer might get it twice. Or more. Use for: payments, orders, critical data. Where duplicates are bad but loss is worse. Handle duplicates with idempotency. Inbox. Deduplication. "Charge twice? No. Check transaction ID. Skip." At-least-once is the default for most production systems. Because loss is worse than duplicate. And duplicate we can fix. Loss we cannot.

**Exactly-once:** We'll cover this next. Spoiler: it's really "at-least-once plus idempotent processing." True exactly-once delivery—the network guarantees it—doesn't exist. We can't control the network. We can't make it deliver exactly once as a primitive. We simulate it. With care. With idempotency. With deduplication. So when someone says "exactly once," ask: do you mean delivery or processing? Delivery: nearly impossible. Processing: achievable. Big difference. We'll unpack it next.

---

## Let's Walk Through the Diagram

```
    DELIVERY SEMANTICS

    AT-MOST-ONCE          AT-LEAST-ONCE
    [Producer]            [Producer]
        |                      |
        |--- send ---->        |--- send ---->
        |   (no retry)         |   (retry until ACK)
        |                      |
        v                      v
    [Broker]              [Broker]
        |                      |
        |   (may lose)         |   (may deliver 2x)
        v                      v
    [Consumer]             [Consumer]
    Loss OK.               Duplicates OK with dedup.
```

At-most-once: one shot. At-least-once: keep trying. Different guarantees. Different use cases.

---

## Real-World Examples (2-3)

**Example 1: Metrics.** CPU usage. Memory. Temperature. At-most-once. One sample lost? Next one in a second. No big deal. Fire and forget. Simple. Fast.

**Example 2: Orders.** Customer places order. Event: OrderCreated. At-least-once. We cannot lose this. Retry. Consumer might get twice. Idempotent: check order ID. Exists? Skip. Safe.

**Example 3: Payments.** Charge request. At-least-once. Never lose. Duplicate? Idempotency. Transaction ID. Process once. The alternative—losing a payment—is unacceptable. Banks. Stripe. PayPal. All use at-least-once for critical paths. With strong idempotency on the receiving end. They assume messages can be duplicated. They design for it. You should too. Choose semantics first. Then build the guards. At-least-once without idempotency is a recipe for duplicate charges. At-least-once with idempotency is production-ready.

---

## Let's Think Together

**Push notification to a user's phone. Which semantics? User getting the notification twice = annoying. Not getting it = they miss an important alert.**

Tricky. Losing it is bad. Duplicate is annoying. Often: at-least-once. Because missing an alert can be critical (security, OTP). Duplicate? Slightly annoying. User can ignore. Deduplication on device: same notification ID = show once. So: at-least-once delivery + client-side dedup. Best of both. Don't use at-most-once for critical notifications. Loss is worse than duplicate.

---

## What Could Go Wrong? (Mini Disaster Story)

A team used at-most-once for "password reset" emails. "Simple. Fast." One day: email service had a hiccup. 10% of emails dropped. Users never got reset links. Support flooded. "I didn't get the email." Lesson: at-most-once only when loss is acceptable. Password reset? At-least-once. Retry. Ensure delivery. Choose semantics by criticality.

---

## Surprising Truth / Fun Fact

Kafka default: at-least-once. Producer sends. Waits for ACK. No ACK? Retry. Broker stores. Consumer reads. Commits offset. Crash before commit? Re-read. At-least-once. RabbitMQ. SQS. Redis Streams. Most message systems default to this. Because loss is usually worse than duplicate. Duplicate you can handle. Idempotency. Inbox. Dedup. Lose a message? It's gone. No retry. No recovery. Design for at-least-once. Add idempotency. You'll sleep better.

---

## Quick Recap (5 bullets)

- **At-most-once:** Send once. No retry. Loss possible. Use for non-critical (metrics, logs).
- **At-least-once:** Retry until ACK. Duplicates possible. Use for critical (orders, payments).
- **Exactly-once:** Next video. Hint: at-least-once + idempotency.
- **Choose** by criticality: can you afford to lose? At-most-once. Can't afford? At-least-once.
- **Most systems** default to at-least-once. Plan for duplicates.

---

## One-Liner to Remember

**At-most-once: might lose. At-least-once: might duplicate. Choose by what you can afford to lose.**

---

## Next Video

Exactly-once. The holy grail. How do we get it? The surprising truth: we don't get "true" exactly-once delivery. We get exactly-once processing. With idempotency. At-least-once under the hood. That's next. See you there.
