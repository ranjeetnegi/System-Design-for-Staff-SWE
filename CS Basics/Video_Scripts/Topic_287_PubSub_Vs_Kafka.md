# Pub/Sub vs Kafka: When to Use Which?

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Two communication systems. System A: a radio broadcast. The station sends a signal. Anyone tuned in hears it. The moment the broadcast ends, the signal is gone. No replay. No "rewind to yesterday's show." System B: a newspaper archive. Every article ever published is stored. Readers can go back. Read last week's paper. Last year's. The archive is durable. Both deliver messages. But they're fundamentally different. Pub/Sub is the radio. Kafka is the newspaper archive. Let's see when you need which.

---

## The Story

**Pub/Sub** (Google Cloud Pub/Sub, AWS SNS, Azure Service Bus in pub/sub mode): message is delivered to subscribers. Then it's gone. No replay. No offset. No "start me from 3 hours ago." Simple. Managed. You publish. Subscribers receive. If a subscriber was down, it missed the message. Push-based or pull-based. But the message doesn't stick around.

**Kafka:** message is stored on disk. For days. Weeks. Configurable. Consumers read at their own pace. They can rewind. "Give me everything from offset 1000." Replay from any point. Consumer groups. Ordering within partitions. Stream processing. It's a durable log. The message sticks around.

The difference is persistence. Pub/Sub: fire and forget. Kafka: fire and store. Use Pub/Sub when you want simple delivery. Use Kafka when you want a log.

---

## Another Way to See It

A megaphone vs a library. Megaphone: you announce. People nearby hear. The sound fades. No recording. Pub/Sub. Library: every book is on the shelf. Readers come when they want. They can check out last month's bestseller. Kafka. Different models. Different use cases.

---

## Connecting to Software

**When Pub/Sub:** simple notification (user signed up → send email, send push), fanout pattern (one event, many subscribers), no replay needed, managed simplicity preferred. Google Pub/Sub, AWS SNS+SQS (SNS fans out, SQS buffers if needed). Great for event-driven, loosely coupled systems. Low ops. Auto-scales. Pay per message. No brokers to manage.

**When Kafka:** event sourcing (full history of events), replay needed (reprocess after bug fix, new consumer catching up), multiple consumers reading at different speeds, ordering critical (per user, per order), stream processing (Kafka Streams, Flink). Higher ops. Higher power.

**Hybrid:** some systems use both. Critical path: Kafka. Simple notifications: Pub/Sub. Right tool per use case.

**The nuances that matter:**

**Ordering:** Kafka guarantees ordering within a partition (using partition keys). Pub/Sub generally does NOT guarantee ordering (though Google Cloud Pub/Sub has an ordering key feature, it adds latency). If ordering matters — events for user #123 must arrive in sequence — Kafka is the safer bet.

**Consumer speed:** In Kafka, slow consumers don't affect fast ones. Each consumer group tracks its own offset. Consumer A can be 2 hours behind while Consumer B is real-time. In Pub/Sub, message acknowledgment and retry behavior is simpler but less flexible — a slow subscriber can cause message redelivery and backlog.

**Cost at scale:** Pub/Sub charges per message (plus storage for retained messages). At 1 million messages/day, Pub/Sub is cheap. At 1 billion messages/day, Kafka on dedicated brokers is often cheaper per message. The crossover point depends on your cloud provider and configuration, but it typically happens around 100M-500M messages/day.

**Operational burden:** Pub/Sub = zero ops. Google/AWS runs everything. Kafka = you run brokers (or pay for managed Kafka like Confluent Cloud / AWS MSK, which costs more but reduces ops). If your team has 3 engineers, the ops burden of self-managed Kafka is a real tax on productivity.

---

## Let's Walk Through the Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│              PUB/SUB vs KAFKA: PERSISTENCE                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   PUB/SUB:                        KAFKA:                                 │
│   ┌─────────┐                     ┌─────────┐                            │
│   │Publisher│                     │Producer │                            │
│   └────┬────┘                     └────┬────┘                            │
│        │                               │                                 │
│        ▼                               ▼                                 │
│   ┌─────────┐    Message delivered  ┌─────────┐   Message STORED          │
│   │ Pub/Sub │    then GONE         │ Kafka   │   then delivered           │
│   │ Broker  │    No replay         │ Broker  │   Replay from any offset   │
│   └────┬────┘                      └────┬────┘                            │
│        │                                │                                 │
│   ┌────┴────┐                      ┌────┴────┐                            │
│   │ Sub A   │ Sub B                │Group A  │ Group B                    │
│   │ (gets   │ (gets                │(reads   │ (reads                     │
│   │  copy)  │  copy)               │  log)   │   log)                     │
│   └─────────┘                      └─────────┘                            │
│   Each gets message. No history.   Each reads from durable log.          │
└─────────────────────────────────────────────────────────────────────────┘
```

Left: ephemeral. Right: durable. The choice changes your architecture.

---

## Real-World Examples

**Google Pub/Sub:** used for event distribution. Cloud events, GKE metrics. Simple. Managed. No retention. Process and forget.

**AWS:** SNS for fanout (topic → many SQS queues). SQS for buffering. No Kafka-style replay. Good for "notify N services." Simple.

**Uber, Netflix, LinkedIn:** Kafka. Event streams. Replay. Multiple consumers. Stream processing. The scale and use cases demand it.

---

## Let's Think Together

**"Requirement: 'Process each order event exactly once, with ability to replay from yesterday.' Pub/Sub or Kafka?"**

Answer: Kafka. "Exactly once" plus "replay from yesterday" means you need a durable log. Pub/Sub doesn't store messages. You can't replay. Kafka stores messages for days (retention). You can reset a consumer's offset to "yesterday" and replay. For exactly-once with external systems, you still need idempotent processing. But the replay requirement alone rules out Pub/Sub. Kafka.

---

## What Could Go Wrong? (Mini Disaster Story)

A team used Pub/Sub for an order processing pipeline. A bug in the consumer corrupted some data. They wanted to reprocess. "Replay last 24 hours." Pub/Sub: no can do. Messages are gone. They had to restore from database backups, replay from transaction logs. Painful. They migrated critical pipelines to Kafka. Now replay is a reset-offset away. Lesson: if you might need replay, plan for it from the start. Pub/Sub doesn't offer it.

---

## Surprising Truth / Fun Fact

Some managed Kafka services (Confluent Cloud, AWS MSK) blur the line: managed like Pub/Sub, but Kafka semantics. And some teams use Pub/Sub with "dead-letter" patterns and long retention on the DLQ—a form of durability. The spectrum isn't binary. But the core distinction holds: Pub/Sub = delivery, then gone. Kafka = store, then deliver (and redeliver). Match the model to the need.

---

## Quick Recap (5 bullets)

- **Pub/Sub:** message delivered, then gone; no replay; no offset; simple, managed (Google Pub/Sub, AWS SNS).
- **Kafka:** message stored on disk; replay from any offset; consumer groups; ordering; durable log.
- **When Pub/Sub:** simple notification, fanout, no replay, managed simplicity.
- **When Kafka:** event sourcing, replay, multi-consumer at different speeds, ordering, stream processing.
- **Replay requirement = Kafka.** Pub/Sub cannot replay. If you might need it, choose Kafka.

---

## One-Liner to Remember

*"Pub/Sub is the radio—hear it once, it's gone. Kafka is the archive—read it whenever you want."*

---

## Next Video

Up next: **Replication Lag: Monitoring and Handling**—when the sign language interpreter is 30 seconds behind the news anchor. We'll cover how to measure lag, when to worry, and how to handle stale reads.
