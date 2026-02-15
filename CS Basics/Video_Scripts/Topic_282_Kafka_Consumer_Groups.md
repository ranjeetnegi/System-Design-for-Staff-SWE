# Kafka Consumer Groups: Sharing Work, Reading Independently

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A call center. One hundred incoming calls. Ten agents. Each agent picks up different calls—no two agents handle the SAME call. That's a consumer group. The work is SHARED. But here's the twist: the billing department also needs a record of every call. And the support department needs every call for training. So billing has its own group of 10 agents. Support has its own group of 10. Each department reads ALL the calls. Independently. Billing doesn't care what support does. Support doesn't care about billing. Same calls. Different groups. Different processing. That's Kafka consumer groups in a nutshell.

---

## The Story

In Kafka, a **consumer group** is a set of consumers that work together. They SHARE the partitions of a topic. Rule: each partition is assigned to exactly ONE consumer in the group. So if you have 6 partitions and 6 consumers, each consumer gets one partition. Load is balanced. No duplicate processing within the group—each message goes to one consumer.

But here's the magic: **multiple consumer groups** can read from the same topic. And each group gets ALL the messages. Independently. Group "analytics" reads every event. Group "email-sender" reads every event. Group "fraud-detection" reads every event. They don't share. They don't coordinate. Each group has its own offset tracking. Same topic. Same messages. Different consumers. Different purposes.

Think of it like a TV broadcast. The same show goes to millions of homes. Each home watches independently. Your pause doesn't affect your neighbor. In Kafka, the "show" is the topic. Each consumer group is like a different "household." They all receive the same stream. They process it separately.

---

## Another Way to See It

A restaurant. Orders come in on one ticket rail. The kitchen staff (one consumer group) divides the tickets among cooks—each cook takes different orders. No two cooks make the same order. Meanwhile, the manager (another consumer group) wants a copy of every order for inventory. They read the same tickets. Independently. The kitchen doesn't wait for the manager. The manager doesn't wait for the kitchen. Same data. Different consumers. Different groups.

---

## Connecting to Software

**Consumer group:** when you start a Kafka consumer, you assign it a `group.id`. All consumers with the same `group.id` form a group. Kafka assigns partitions to them. Rebalancing happens when consumers join or leave—partitions get reassigned. Brief pause possible during rebalance.

**Multiple groups:** create another application with a different `group.id`. It reads the same topic from the beginning (or from configured offset). No impact on the first group. Each group maintains its own offsets. Scales use cases: one topic, many consumers.

**Rebalancing:** consumer joins → partitions reassigned. Consumer dies → its partitions go to others. This takes a few seconds. During rebalance, some partitions might be unread. Plan for it. Avoid too-frequent rebalances (e.g., short-lived consumers that keep joining and leaving).

---

## Let's Walk Through the Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    CONSUMER GROUPS: SAME TOPIC, DIFFERENT GROUPS         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   TOPIC: order-events (6 partitions)                                     │
│   ┌─────┬─────┬─────┬─────┬─────┬─────┐                                  │
│   │ P0  │ P1  │ P2  │ P3  │ P4  │ P5  │                                  │
│   └──┬──┴──┬──┴──┬──┴──┬──┴──┬──┴──┬──┘                                  │
│      │     │     │     │     │     │                                     │
│      ▼     ▼     ▼     ▼     ▼     ▼                                     │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │  GROUP: order-processors (share partitions)                      │   │
│   │  C1←P0  C2←P1  C3←P2  C4←P3  C5←P4  C6←P5   (each gets 1)        │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│      │     │     │     │     │     │                                     │
│      └─────┴─────┴─────┴─────┴─────┘                                     │
│                          │                                               │
│                          ▼                                               │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │  GROUP: analytics (reads ALL partitions, own offsets)             │   │
│   │  C1 C2 C3 C4 C5 C6 each read from P0-P5 independently            │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│   Same topic. Group A shares. Group B shares. A and B don't affect each. │
└─────────────────────────────────────────────────────────────────────────┘
```

Two groups. Same 6 partitions. Each group divides internally. Between groups: independence.

---

## Real-World Examples

**E-commerce:** topic "order-events." Group "fulfillment" processes orders for shipping. Group "analytics" computes metrics. Group "recommendation" updates "users who bought X also bought Y." One topic. Three groups. Each does its job. No coordination needed.

**Netflix:** playback events. Group "real-time-monitoring" for alerts. Group "recommendation-engine" for personalization. Group "billing" for usage. Same events. Different consumers. Scale each independently.

**Ride-sharing:** trip events. Group "trip-completion" for receipts and driver pay. Group "fraud-detection" for anomaly detection. Group "ETA-service" for live maps. One topic. Many use cases.

---

## Let's Think Together

**"Topic: 6 partitions. Consumer group A: 3 consumers (2 partitions each). Consumer group B: 6 consumers (1 each). What if group A adds a 4th consumer?"**

Answer: Rebalancing. Group A's coordinator reassigns partitions. Before: C1 had P0+P1, C2 had P2+P3, C3 had P4+P5. After: maybe C1→P0, C2→P1, C3→P2, C4→P3+P4+P5? No. Typically it rebalances evenly: C1→P0+P1, C2→P2+P3, C3→P4, C4→P5. Or similar. Each consumer gets 1–2 partitions. Group B is unaffected—they have their own offset tracking. The rebalance causes a brief pause in group A. Consumers might need to reprocess some messages if offsets weren't committed. Plan for short stalls during scale-up.

---

## What Could Go Wrong? (Mini Disaster Story)

A team had one consumer group processing payments. They scaled to 20 consumers. But the topic had 4 partitions. Sixteen consumers sat idle. They didn't realize. They thought "more consumers = more throughput." It didn't. Then they tried to fix it by adding partitions. Partition count went from 4 to 20. Rebalance. But adding partitions can temporarily affect ordering guarantees for keys. And they had to plan the migration. Lesson: consumer count and partition count need to match your parallelism goals. More consumers than partitions = waste. Fewer = underutilized. Align them.

---

## Surprising Truth / Fun Fact

Kafka consumer groups use a "group coordinator" broker. When you start a consumer, it finds the coordinator, joins the group, gets partition assignments. The coordinator manages membership. If the coordinator broker dies, the group re-elects. There's a brief period of unavailability. For critical pipelines, some teams run multiple consumer groups as fallback—same logic, different group IDs—and only one "active" at a time. Failover by switching which group is active. Overkill for most. But the pattern exists.

---

## Quick Recap (5 bullets)

- **Consumer group:** set of consumers that SHARE partitions; each partition → one consumer in the group.
- **Multiple groups:** each group reads ALL messages independently; same topic, different purposes.
- **Rebalancing:** when consumers join/leave, partitions reassigned; brief pause possible.
- **Use case:** one topic serves many consumers—fulfillment, analytics, fraud—each with its own group.
- **Throughput:** max parallelism within a group = number of partitions; scale partitions to scale consumers.

---

## One-Liner to Remember

*"Within a group, work is shared. Between groups, everyone reads everything. Same topic, different kitchens."*

---

## Next Video

Up next: **Kafka Ordering and Partitioning Key**—why all events for user 123 go to the same partition, and what happens when "shipped" arrives before "paid." The post office sorting machine.
