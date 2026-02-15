# Kafka: Topic, Partition, Offset—The Newspaper Model

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Open a newspaper. It has sections: Sports, Politics, Entertainment. Each section has pages. Each page has articles, and every article has a page number. You want to read the Sports section? You go there. You want to start from page 5? You open page 5. You always read forward—page numbers only go up. That's Kafka. Topics are sections. Partitions are the pages. Offsets are the page numbers. And just like a newspaper, you can have multiple people reading different sections at the same time. Let's unpack this.

---

## The Story

Kafka organizes streams of events. Imagine billions of events flowing—user signups, orders, payment logs, sensor readings. Kafka doesn't dump them in one giant pile. It organizes them.

**Topic:** a named stream. Like "user-signups" or "order-events." Everything about user signups goes to the user-signups topic. Everything about orders goes to order-events. Topics are logical categories. You publish to a topic. You consume from a topic.

**Partition:** a topic is split into partitions. Each partition is an ordered, append-only log. Think of it like a queue that only grows. Messages land at the end. They never move. Partitions enable parallelism. One topic with 10 partitions means 10 logs. Ten consumers can read in parallel—one per partition. Throughput scales.

**Offset:** the position within a partition. Offset 0 is the first message. Offset 1 is the second. Offsets only increase. Consumers track their offset—"I've read up to offset 42." They can rewind—"Start me from offset 30." Or they can start from the end for new messages only. The offset is the consumer's bookmark.

---

## Another Way to See It

A library. The library has SECTIONS—fiction, nonfiction, kids. Those are topics. Each section has SHELVES—shelf 1, shelf 2, shelf 3. Those are partitions. Each book on a shelf has a POSITION—first book, second book. That's the offset. You can say "I want to read from the third book on shelf 2 of the fiction section." Kafka lets you do the same: topic = fiction, partition = 2, offset = 3. Precision.

---

## Connecting to Software

**Topic:** you create a topic when you need a new event stream. `kafka-topics.sh --create --topic order-events --partitions 6`. Six partitions for that topic.

**Partition:** each partition is a separate log file (simplified). Producers send messages to a topic; Kafka assigns each message to a partition (by key or round-robin). Messages within a partition are ordered. Across partitions? No guarantee.

**Offset:** consumers commit offsets. "I processed up to offset 100." If the consumer crashes and restarts, it resumes from 100. No reprocessing of 0–99. Offsets are the consumer's progress indicator.

**Why partitions matter:** more partitions = more parallelism. Ten partitions, ten consumers in a group = each consumer reads one partition. Throughput scales. But: too many partitions = more overhead, more connections, more coordination. Balance.

---

## Let's Walk Through the Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    KAFKA TOPIC = PARTITIONS = OFFSETS                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   TOPIC: order-events                                                    │
│                                                                          │
│   Partition 0        Partition 1        Partition 2                      │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                  │
│   │ offset 0    │    │ offset 0    │    │ offset 0    │                  │
│   │ offset 1    │    │ offset 1    │    │ offset 1    │                  │
│   │ offset 2    │    │ offset 2    │    │ offset 2    │                  │
│   │ offset 3    │    │ offset 3    │    │ offset 3    │                  │
│   │     ...     │    │     ...     │    │     ...     │                  │
│   │ offset N    │    │ offset N    │    │ offset N    │                  │
│   └─────────────┘    └─────────────┘    └─────────────┘                  │
│        ▲                  ▲                  ▲                           │
│        │                  │                  │                           │
│   Consumer A          Consumer B         Consumer C                     │
│   reads P0            reads P1           reads P2                       │
│   tracks offset       tracks offset       tracks offset                  │
│                                                                          │
│   Each partition = ordered log. Offset = position. Consumers = parallel.  │
└─────────────────────────────────────────────────────────────────────────┘
```

Three partitions, three consumers. Each has a dedicated log. Each tracks its own offset.

---

## Real-World Examples

**Netflix** uses Kafka for event streaming. Topic for "playback started," topic for "playback stopped." Partitions let them scale consumers. Hundreds of services consume at different rates. Partitions and consumer groups handle it.

**Uber** uses Kafka for ride events. High throughput. Topics like trip-lifecycle. Many partitions. Many consumers. Offsets let them replay—"reprocess last hour of trips for a bug fix."

**LinkedIn** (where Kafka was born) uses it for activity streams, metrics, logs. Billions of events per day. Topics, partitions, offsets—the foundation of it all.

---

## Let's Think Together

**"Topic with 3 partitions. 5 consumers in a group. What happens? (Hint: 2 consumers idle.)"**

Answer: In a consumer group, each partition is assigned to exactly one consumer. Three partitions, five consumers: three consumers get one partition each. Two consumers get nothing—they sit idle. They're "spare." If one of the active consumers dies, a spare takes over its partition. So: 5 consumers in the group, but only 3 do work. The other 2 are on standby. Useful for high availability. Not useful for more throughput—throughput is capped by the number of partitions. To scale consumers, you need more partitions.

---

## What Could Go Wrong? (Mini Disaster Story)

A team created a topic with one partition. Throughput grew. They added 10 consumers. All 10 joined the group. Nine sat idle. One consumer handled everything. Bottleneck. Lag grew. Alerts fired. They learned: partitions define max parallelism. You can't have more active consumers than partitions. They re-partitioned (with care—partition count changes can affect ordering). Now 10 partitions, 10 consumers. Problem solved. Plan partition count upfront based on target throughput.

---

## Surprising Truth / Fun Fact

Kafka offsets are sequential per partition but not globally unique. Partition 0 has offset 0, 1, 2... Partition 1 also has offset 0, 1, 2... Offsets are partition-local. When you say "offset 42," you must specify which partition. A full position in Kafka is: topic + partition + offset. Three coordinates. Like a library: section + shelf + position.

---

## Quick Recap (5 bullets)

- **Topic:** named stream of events (e.g., order-events, user-signups).
- **Partition:** topic split into ordered, append-only logs; enables parallelism.
- **Offset:** position within a partition; consumers track it to resume from where they left off.
- **Parallelism:** more partitions = more consumers can read in parallel; max consumers = partitions.
- **Ordering:** within a partition = ordered; across partitions = no guarantee.

---

## One-Liner to Remember

*"Topic is the section. Partition is the page. Offset is the page number. You always read forward."*

---

## Next Video

Up next: **Kafka Consumer Groups**—how multiple consumers share the work, and why two different departments can each read ALL the messages. The call center with billing and support.
