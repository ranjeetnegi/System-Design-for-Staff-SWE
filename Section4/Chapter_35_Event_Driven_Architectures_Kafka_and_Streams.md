# Chapter 33: Event-Driven Architectures — Kafka and Streams (Part A)

## The Architecture That Powers LinkedIn, Uber, and Netflix at Scale

---

## Before You Start: What This Chapter Is About

The previous chapter (Chapter 32) covered Redis and cache internals — how data gets stored in memory and served back fast. Caching is a read-side optimization. This chapter is about a different problem: **how data flows between services** when your system has many pieces that all need to react to the same things happening.

At an L6 interview you will not be asked "what is Kafka." You will be asked questions like these:

- "Your Order service calls Inventory, Fulfillment, Notifications, and Analytics synchronously. What happens when Notifications goes down?" — You need to know why tight coupling is dangerous and how event-driven architecture fixes it.
- "You have 6 partitions and 12 consumers in your consumer group. Why are half your consumers idle?" — You need to know the partition-to-consumer assignment rule cold.
- "Your fraud detection system has a consumer lag of 1 million messages. Walk me through what happened and how you fix it." — You need to know lag, backpressure, and scale-out strategy.
- "You need strict ordering of all events for user 123, but user 123 generates 40% of your traffic. What do you do?" — You need to know the hot-key problem and how to solve it.

This chapter answers all of those questions, built from the ground up so every concept is crystal clear before you need to apply it.

```
+-----------------------------+      +-----------------------------+      +-----------------------------+
|  1. WHY EVENT-DRIVEN?       |  ->  |  2. KAFKA CORE CONCEPTS     |  ->  |  3. ORDERING + LAG         |
|                             |      |                             |      |                             |
|  What problems does EDA     |      |  Topics, partitions,        |      |  What Kafka guarantees,     |
|  solve that REST cannot?    |      |  brokers, offsets, groups   |      |  when it breaks, and lag   |
+-----------------------------+      +-----------------------------+      +-----------------------------+
```

Part B of this chapter (Chapter 33 Part B) covers Kafka Streams, exactly-once semantics, Schema Registry, and the full L6 design patterns: outbox pattern, CQRS with Kafka, and event sourcing.

---

## Section 1: What Is Event-Driven Architecture?

### The Newspaper Analogy

Imagine you want to know what is in today's newspaper.

**Option A (Synchronous / REST style):** You pick up the phone and call the newspaper office. Someone answers, reads you the headlines, and hangs up. Simple. But now imagine a million people all call at the same moment. The newspaper office needs a million phone operators standing by. Every caller waits for an operator to pick up. If the newspaper office is overwhelmed, callers wait. If it crashes, nobody gets any news.

**Option B (Asynchronous / Event-Driven style):** The newspaper prints one edition. One million subscribers each get a copy delivered to their door. The newspaper office doesn't take a single phone call. It published once. Each subscriber reads at their own pace. A new subscriber who moves to the neighborhood can get the last seven days of back-issues without calling anyone. If one subscriber is on vacation and misses a delivery, the papers pile up at their door — they can read them all when they get back.

The newspaper (the **producer**) does not know who is reading. The subscriber (the **consumer**) does not know when the newspaper was written. They are **decoupled in time** and **decoupled in knowledge**.

That is the core insight of event-driven architecture.

```
SYNCHRONOUS (REST)
============================================================

  Order      calls ->   Inventory   (waits 50ms)
  Service    calls ->   Fulfillment (waits 80ms)
             calls ->   Notifications (waits 30ms)
             calls ->   Analytics   (waits 20ms)
                                           Total: 180ms
  If Notifications goes down -> Order Service call FAILS

ASYNCHRONOUS (Event-Driven / Kafka)
============================================================

  Order Service
      |
      | publishes 1 event "order.created"
      v
  +---+---+---+---+---+---+
  | Kafka Topic: "orders" |
  +---+---+---+---+---+---+
      |       |       |       |
      v       v       v       v
  Inventory  Fulfil  Notif  Analytics
  reads      reads   reads  reads
  when       when    when   when
  ready      ready   ready  ready

  If Notifications goes down -> It just falls behind.
  Order Service doesn't know. Doesn't care. Keeps running.
```

### Three Concrete Problems Event-Driven Architecture Solves

**Problem 1: Tight Coupling**

When Service A calls Service B directly (REST/RPC), A and B are coupled. B goes down — A breaks. B is slow — A is slow. B changes its API — A breaks. Every downstream service you add is another dependency that can take you down.

With events: Service A publishes a message to Kafka and returns. It has zero knowledge of B, C, or D. They subscribe to the event and process it independently. A cannot be broken by any downstream service going down, because A never talks to them directly.

Real example: **Uber**. When a ride is completed, dozens of downstream systems need to know: billing, driver rating, passenger rating, insurance logging, fraud analysis, promotions, trip history. Uber does not make Uber's trip-completion API wait for all twelve systems to respond. It publishes a `trip.completed` event to Kafka and lets each downstream system consume it independently.

**Problem 2: Fan-Out Inefficiency**

When one event needs to trigger multiple downstream actions, REST requires the publisher to make N API calls — one per downstream consumer. If you add a new downstream consumer later, you must change the publisher. The publisher needs to know about every consumer.

With Kafka: the publisher publishes once. Any number of consumers can subscribe. Adding a new consumer requires zero changes to the publisher. At **LinkedIn**, a single `pageview` event is consumed by over 30 different systems — analytics, recommendations, ad billing, A/B testing, security, and more — without the web server making 30 API calls per page view.

**Problem 3: Different Processing Speeds**

Your Order service creates 10,000 orders per second on Black Friday. Your Email service can only send 100 emails per second. With synchronous REST, the Order service calls the Email service for every order. The Email service is overwhelmed. Your order creation slows to 100/sec — throttled by the slowest downstream service.

With Kafka: the Order service publishes events at 10,000/second. The Email service reads from Kafka at 100/second. Kafka **buffers the difference**. Orders pile up in the Kafka topic — not in memory on the Order service, not crashing any system. The Email service drains the backlog at its own pace. Your Order service never slows down.

```
DIFFERENT SPEEDS: Kafka as a buffer

Producer (Order Service): 10,000 events/sec
Consumer (Email Service):    100 events/sec
                          ---------
Kafka topic backlog grows:  9,900 events/sec

But that's OK. Kafka holds them (up to configured retention: 7 days).
Email service drains the backlog overnight. Nothing is lost.

+-----------+   10,000/s   +-----------------------------+   100/s   +-----------+
|  Order    |  -------->   |  Kafka Topic "orders"       |  ------>  |  Email    |
|  Service  |              |  [msg][msg][msg]...[msg]    |           |  Service  |
+-----------+              |  Backlog grows: OK          |           +-----------+
                           +-----------------------------+
```

### When NOT to Use Event-Driven Architecture

L6 principle: **events are a tool, not a religion**. Knowing when NOT to use Kafka is just as important as knowing when to use it.

| Situation | Recommendation | Why |
|-----------|----------------|-----|
| User is waiting for a synchronous response | Use REST/RPC | Events are fire-and-forget. You cannot easily get a reply. |
| Simple operation, one consumer | Use a direct call | Kafka adds operational overhead with zero benefit. |
| Strong transactional guarantees across services | Use with caution | Distributed sagas are complex; two-phase commit doesn't work across Kafka. |
| Team has fewer than 5 engineers | Start without Kafka | Running a Kafka cluster requires real operational expertise. |
| You need sub-10ms latency | Use REST/gRPC | Kafka adds latency. It is optimized for throughput, not microsecond latency. |

Most systems should start synchronous. Add events when you hit real problems: cascading failures from coupling, fan-out becoming unmanageable, or speed mismatches causing bottlenecks. Do not add Kafka to a system with three services and one engineer because it "seems scalable."

---

## Section 2: Why Kafka Exists — The LinkedIn Origin Story

In 2010, LinkedIn's engineering team faced a crisis.

LinkedIn was operating data centers across the globe. Every user action — profile views, connection requests, job clicks, search queries — needed to flow from application servers to a central analytics system so LinkedIn could compute recommendations, detect spam, and measure product metrics. They were generating **millions of events per second**.

They tried existing message queue systems like **RabbitMQ**. These were designed for task queues — short-lived messages that get delivered and deleted. RabbitMQ could not handle LinkedIn's throughput. It also deleted messages after delivery, which meant if a consumer fell behind or crashed, those messages were gone. You could not replay them. You could not add a new analytics job and have it process last week's data.

They tried writing to a traditional database. The write throughput was too low for append-only stream ingestion at millions of events per second.

Three LinkedIn engineers — **Jay Kreps**, **Neha Narkhede**, and **Jun Rao** — built something new. They named it **Kafka**, after the author Franz Kafka, because "a system optimized for writing" seemed fitting for an author known for writing prolifically about bureaucratic systems.

The key insight that made Kafka different from everything before it:

> **A message queue deletes messages after delivery. What if messages were stored like a LOG — appended forever — and consumers tracked their own position in the log?**

This one change unlocked everything:

- Any consumer can re-read old messages (replay capability)
- A consumer that crashes can resume exactly where it left off (durability)
- A new consumer can start from message 1 and process the entire history (bootstrapping)
- Multiple consumer groups can each read independently at different positions (fan-out without duplication)

Today LinkedIn uses Kafka to process **7 trillion messages per day**. Kafka is used by more than 80% of Fortune 100 companies including **Netflix**, **Airbnb**, **Goldman Sachs**, **The New York Times**, and **Twitter (now X)**. It is maintained as an open-source project under the Apache Software Foundation.

---

## Section 3: Kafka Core Concepts — Built From First Principles

### The Append-Only Log: The Fundamental Data Structure

Before you learn about Kafka's features, you need to understand the data structure it is built on. Everything else follows from this.

Think about a bank ledger. When the bank records transactions, it never erases entries. Every deposit and withdrawal is written at the bottom of a list, in the order it happened. If you want to know your current balance, you sum up all the entries from the beginning. The ledger is **append-only** — entries are added to the end, never modified in the middle, never deleted.

Kafka is an **append-only, distributed log**.

Messages are written to the **end** of the log. Consumers read from **any position** in the log. Each message's position is identified by a number called an **offset** — a simple sequential integer starting at 0.

```
THE KAFKA LOG (one partition)

Offset:  0      1      2      3      4      5      6      7      8
       +------+------+------+------+------+------+------+------+------+
       | msg  | msg  | msg  | msg  | msg  | msg  | msg  | msg  | msg  |  <-- Producer writes here
       | "A"  | "B"  | "C"  | "D"  | "E"  | "F"  | "G"  | "H"  | "I" |     (always at the end)
       +------+------+------+------+------+------+------+------+------+
                                               ^
                                               |
                                   Consumer A is at offset 5
                                   (has processed 0-4, will read 5 next)

Rules:
  - Producer ALWAYS appends to the right end. Never modifies old messages.
  - Consumer tracks its own offset. Reads forward only.
  - Two different consumers can be at different offsets simultaneously.
  - An offset, once written, never changes its value. Offset 3 is always "D".
```

This is the single most important thing to understand about Kafka. Every other concept is built on top of this append-only log.

### Topics: Organizing the Log

In Kafka, a **topic** is a named category for messages. You create topics like `orders`, `user-events`, `inventory-updates`, `fraud-alerts`. Producers write messages to a topic. Consumers read messages from a topic.

Think of topics like different radio stations. Station "orders" broadcasts all order-related events. Station "user-events" broadcasts every user action on your website. Producers choose which station to broadcast on. Consumers choose which station to tune into.

A message stays in a topic for a configurable **retention period**. The default is 7 days. After that, old messages are deleted. You can also configure retention by size (e.g., delete oldest messages when the topic exceeds 50GB). For event sourcing use cases, you can configure **infinite retention** — messages are kept forever.

### Partitions: Making Throughput Scale

One append-only log has a limit: only one producer can write to the end at a time. At LinkedIn's scale (millions of events/second), one log would be a bottleneck. How do you parallelize writes?

A topic is split into **partitions**. Each partition is an independent append-only log. They run in parallel.

A topic called `orders` with 6 partitions can accept writes to 6 different logs simultaneously. This multiplies write throughput by roughly 6×.

```
TOPIC "orders" WITH 3 PARTITIONS

Partition 0:  [offset 0]["order-A"] [offset 1]["order-D"] [offset 2]["order-G"]
Partition 1:  [offset 0]["order-B"] [offset 1]["order-E"] [offset 2]["order-H"]
Partition 2:  [offset 0]["order-C"] [offset 1]["order-F"] [offset 2]["order-I"]

Each partition is its OWN independent log with its own offset sequence.
Partition 0 offset 2 ("order-G") is a DIFFERENT message than
Partition 1 offset 2 ("order-H").
```

**Critical point about ordering:** Messages within a single partition are strictly ordered by offset. Message at offset 5 in partition 0 was written before message at offset 6 in partition 0. BUT there is **no ordering guarantee across partitions**. Message at partition 0 offset 100 might have been written before OR after message at partition 1 offset 50. Kafka does not track cross-partition ordering.

### How a Message Lands on a Partition: The Assignment Rules

When a producer sends a message, Kafka decides which partition it goes to. There are two cases:

**With a message key:** The producer attaches a key to the message (e.g., a user ID, an order ID). Kafka computes `hash(key) % number_of_partitions` and routes the message to that partition. The same key **always** goes to the same partition.

Why does this matter? If you need all events for a specific entity to be in order, use that entity's ID as the message key. All events for user 123 go to partition 2 (by hash). A consumer reading partition 2 sees user 123's events in order: `account_created` at offset 10, `profile_updated` at offset 15, `order_placed` at offset 22.

Real example: **Uber** uses `ride_id` as the Kafka message key for ride events. All events for a given ride (`ride_requested`, `driver_assigned`, `ride_started`, `ride_completed`) are guaranteed to land on the same partition in the correct order. The consumer processing a ride can always reconstruct the full ride timeline.

**Without a message key:** Kafka distributes messages across partitions in round-robin order. Partition 0 gets message 1, partition 1 gets message 2, partition 2 gets message 3, partition 0 gets message 4, and so on. Use this when you do not care about ordering — for example, anonymous page view events where you only care about aggregate counts.

```
PARTITION ASSIGNMENT

WITH KEY ("user_id" = 123):
  hash(123) % 6 partitions = partition 2
  ALL events for user 123 -> always partition 2

  User 123: [login] -> P2, [click] -> P2, [purchase] -> P2, [logout] -> P2
            Consumer on P2 sees them IN ORDER

WITHOUT KEY (round-robin):
  msg1 -> P0
  msg2 -> P1
  msg3 -> P2
  msg4 -> P0  (wraps around)

  Spread evenly. No ordering guarantee.
```

### Consumer Groups: Reading in Parallel

A single consumer reading a topic with 6 partitions has to process everything by itself. At high throughput that consumer cannot keep up. You need to parallelize the reading the same way partitions parallelized the writing.

A **consumer group** is a set of consumers that cooperate to read a topic together. Kafka enforces one rule:

> **Each partition is assigned to exactly one consumer within a group at any given time.**

This ensures no two consumers in the same group process the same message. It also means the maximum useful parallelism equals the number of partitions.

```
CONSUMER GROUP "fulfillment-service"
Topic "orders": 4 partitions

  Partition 0 -------> Consumer Instance A
  Partition 1 -------> Consumer Instance A
  Partition 2 -------> Consumer Instance B
  Partition 3 -------> Consumer Instance B

  2 consumers, 4 partitions: each consumer handles 2 partitions.
  Throughput: 2x compared to 1 consumer.

If you add a 3rd consumer:
  Partition 0 -------> Consumer A
  Partition 1 -------> Consumer B
  Partition 2 -------> Consumer C
  Partition 3 -------> Consumer A  (A gets an extra one)

If you add a 5th consumer:
  Partition 0 -------> Consumer A
  Partition 1 -------> Consumer B
  Partition 2 -------> Consumer C
  Partition 3 -------> Consumer D
  Consumer E -------> (idle, no partition available)

  5th consumer is IDLE. Adding consumers beyond partition count is wasteful.
```

**Different consumer groups are completely independent.** One topic can be read by many consumer groups simultaneously. Group `fulfillment-service` is at offset 1,000. Group `analytics-pipeline` is at offset 500 (it's behind). Group `fraud-detection` is at offset 1,050 (it's ahead). Each group tracks its own offset. They do not interfere with each other.

```
MULTIPLE CONSUMER GROUPS reading "orders" topic

                    +-------------------------------+
                    |   KAFKA TOPIC "orders"        |
                    |   [0][1][2]...[999][1000]     |
                    +-------------------------------+
                          |           |          |
                          v           v          v
              fulfillment-service  analytics  fraud-detection
              offset: 1000         offset: 500  offset: 1050

  Each group reads independently. Adding analytics group does NOT
  affect fulfillment group's offset or performance.
```

This fan-out capability is what makes Kafka dramatically better than REST for multi-consumer scenarios. LinkedIn broadcasts one `pageview` event to a single Kafka topic. Thirty different consumer groups each independently process those events for their own purposes, at their own speeds, without any coordination between them.

### Offset Management: Tracking Where You Are

Each consumer group tracks **which offset it has processed** in each partition. This state is stored in a special Kafka topic called `__consumer_offsets` (internal, managed by Kafka).

When a consumer crashes and restarts, it reads its last recorded offset from `__consumer_offsets` and resumes from that position. No messages are lost — they are still in the partition, waiting.

There are two ways a consumer group commits its offset:

**Auto-commit (the simple way):** Kafka automatically commits the offset every 5 seconds (configurable). Simple to set up. But it introduces a subtle danger.

Danger scenario: Consumer pulls messages at offsets 50 through 60 at time T=0. At T=3 seconds (before the 5-second auto-commit fires), the consumer crashes while processing message 55. It restarts. It reads from the last committed offset — which was 50 (committed before the crash). Messages 50–54 are reprocessed. This is **at-least-once delivery**: messages may be processed more than once, but none are lost.

But there is a worse failure: if auto-commit fires at T=5 and commits offset 60, then the consumer crashes at T=6 before finishing processing. When it restarts, it reads from offset 61. Messages 55–60 were never fully processed but were marked as committed. This is **at-most-once delivery** with potential data loss.

**Manual commit (the controlled way):** The consumer explicitly calls `commitSync()` or `commitAsync()` only after it has successfully processed a message. This gives you precise control. The downside is that you must handle commit timing carefully in your application code.

```
OFFSET COMMIT TIMING

Auto-commit (every 5 seconds):
  T=0s:  Consumer reads offset 50, 51, 52...
  T=5s:  Auto-commit fires. Commits offset 55 (current position).
  T=6s:  CRASH during processing of offset 57.
  T=6s:  Restart. Reads last committed offset = 55.
  Result: offsets 55, 56 reprocessed. AT-LEAST-ONCE delivery.

Manual commit (after processing):
  T=0s:  Consumer reads and processes offset 50. Calls commitSync(50).
  T=1s:  Reads and processes offset 51. Calls commitSync(51).
  T=2s:  Reads offset 52. CRASH before processing completes.
  T=2s:  Restart. Last committed = 51. Reads from 52.
  Result: offset 52 reprocessed once. AT-LEAST-ONCE delivery.
          More precise control over what counts as "processed."
```

### Brokers and Clusters: The Infrastructure

A **broker** is a single Kafka server. It stores partitions on disk and handles producer and consumer requests. A production Kafka **cluster** typically has 3 to 10 brokers.

Each partition lives on one broker, called the **leader** for that partition. All reads and writes for a partition go to its leader broker.

But if that broker crashes, you lose all the data in those partitions. To prevent this, Kafka **replicates** each partition across multiple brokers. The replication factor (typically 3) means every partition has 3 copies: one leader and two **followers**.

```
KAFKA CLUSTER: 3 Brokers, Topic "orders" with 4 Partitions, Replication=3

                        BROKER 1        BROKER 2        BROKER 3
                      +-----------+   +-----------+   +-----------+
 Partition 0 Leader:  |   P0-L    |   |   P0-F    |   |   P0-F    |
 Partition 1 Leader:  |   P1-F    |   |   P1-L    |   |   P1-F    |
 Partition 2 Leader:  |   P2-F    |   |   P2-F    |   |   P2-L    |
 Partition 3 Leader:  |   P3-L    |   |   P3-F    |   |   P3-F    |
                      +-----------+   +-----------+   +-----------+

  L = Leader (handles reads/writes)
  F = Follower (replicates from leader, ready to take over)

  If Broker 2 crashes:
    - P1 has no leader. Kafka elects P1-F on Broker 1 or 3 as new leader.
    - Takes seconds. Producers and consumers see a brief hiccup, then continue.
    - No data loss because P1 was replicated to other brokers.
```

Leaders are spread across brokers by design to balance the load. No single broker should be the leader for all partitions.

### Zookeeper and KRaft: The Coordination Layer

Early Kafka (before version 2.8) used a separate system called **Zookeeper** to manage cluster metadata: which broker is the controller, which partitions have which leaders, what topics exist. This meant you had to run and maintain TWO separate distributed systems — Kafka AND Zookeeper — to have a working cluster.

**KRaft** (Kafka Raft, introduced in Kafka 2.8, production-ready in 3.3) eliminates Zookeeper entirely. Metadata is stored in a special Kafka topic managed internally by Kafka itself. A built-in Raft consensus protocol elects a controller from among the brokers.

| Feature | Zookeeper Mode | KRaft Mode |
|---------|---------------|------------|
| Dependency | Requires separate Zookeeper cluster | Self-contained |
| Failover time | 30+ seconds on controller failure | Under 1 second |
| Max partitions per cluster | ~200,000 | Millions |
| Operational complexity | High (two systems to monitor) | Low |
| Production recommendation | Legacy deployments | All new deployments |

If you are starting a new Kafka deployment in 2024 or later, use KRaft. If you are inheriting an older cluster with Zookeeper, plan a migration.

---

## Section 4: Ordering Guarantees — The Full Truth

### What Kafka Actually Guarantees

Kafka's ordering guarantees are precise and limited. Understanding exactly what is and is not guaranteed is the difference between a correct system and one with subtle, hard-to-reproduce bugs.

**Within a single partition: strict ordering.**

Messages are always delivered to a consumer in the order they were written. If the producer wrote message A at offset 5 and message B at offset 6, the consumer will always see A before B. This is guaranteed by the append-only log structure. The consumer reads offsets sequentially: 0, 1, 2, 3... It can never skip backward.

**Across partitions: no ordering guarantee.**

If message A was written to partition 0 and message B was written to partition 1 at nearly the same time, there is no guarantee which one a consumer sees first. Partitions are independent logs processed by different consumer threads. Timing across partitions is not coordinated.

```
ORDERING GUARANTEES ILLUSTRATED

Within Partition 0:                 Across Partitions:
  offset 5: event "A"               Partition 0 offset 5: event "A"
  offset 6: event "B"               Partition 1 offset 3: event "B"
  offset 7: event "C"
                                    "A" was written 1 millisecond before "B"
  Consumer ALWAYS sees:             but they are in different partitions.
  A -> B -> C                       Consumer might see: A, B (correct)
  GUARANTEED                            OR see: B, A (also valid)
                                    NOT GUARANTEED
```

### Ordering by Key: The Design Pattern

If you need all events for a specific entity to be in order, use that entity's ID as the message key. All events for user 123 hash to the same partition. One consumer handles that partition. That consumer sees user 123's events in strict order.

This is the standard pattern for **state machines** built on Kafka. A ride at Uber progresses through states: `requested` -> `driver_assigned` -> `in_progress` -> `completed`. All four events use `ride_id` as the key. They all land on the same partition. The consumer sees them in order and can build the correct state machine.

### The Hot Key Problem

Key-based ordering has a tradeoff. If one key generates a disproportionate share of traffic, the partition that key maps to becomes a **hot partition**.

Scenario: your e-commerce platform has a `seller_id` as the Kafka key for product listing updates. One seller (say, a major brand) updates 10,000 products per second. The remaining 1,000 sellers update a combined 1,000 products per second. The hot seller's partition receives 91% of all traffic. One consumer handles that partition. Your consumer group has 6 consumers but 5 of them are nearly idle. The 1 consumer on the hot partition cannot keep up.

```
HOT KEY PROBLEM

Seller "BigBrand" (key = seller_id_999):
  hash(999) % 6 = partition 3
  10,000 events/sec -> ALL go to partition 3

Other 1000 sellers:
  1,000 events/sec -> spread across P0, P1, P2, P4, P5

Consumer load:
  Consumer on P3: overwhelmed (10,000 events/sec)
  Consumers on P0,P1,P2,P4,P5: nearly idle (200 events/sec each)
  
  Adding more consumer instances DOES NOT HELP.
  P3 can only be assigned to ONE consumer.
```

Solutions for the hot key problem:

**Solution 1: Composite key.** Instead of using `seller_id` alone, use `seller_id + category_id` as the key. BigBrand's 10,000 updates are now spread across multiple partitions (one per category). The ordering guarantee is now per-seller-per-category, which may be sufficient.

**Solution 2: Key salting.** Append a random number to the key: `seller_999_0`, `seller_999_1`, ..., `seller_999_N`. This distributes the hot key across N partitions. The downstream consumer must **deduplicate** and **reorder** from N partitions to reconstruct the full order. More complex, but it handles extreme skew.

**Solution 3: Separate topic.** If one seller truly generates traffic equivalent to an entire topic, give that seller their own dedicated Kafka topic with higher partition count. Route that seller to the dedicated topic, all other sellers to the shared topic.

### When Ordering Breaks Even With Keys

The key assignment guarantees ordering during normal processing. But there is a common scenario that silently breaks ordering in production systems.

Scenario: Consumer reads messages at offsets 100, 101, 102 from partition 0. Processing message 101 fails (downstream service returns an error). You retry message 101. Meanwhile, message 102 was already processed successfully. Now when 101 eventually succeeds, it is processed AFTER 102.

```
ORDERING VIOLATION FROM RETRY

Normal flow:
  Offset 100: processed OK at T=0
  Offset 101: FAILS at T=1, sent to Dead Letter Queue (DLQ)
  Offset 102: processed OK at T=2
  Offset 103: processed OK at T=3
  ...
  DLQ retry: Offset 101 finally processed at T=60

  Order of processing: 100, 102, 103, ..., 101 (WRONG ORDER)
```

The production fix depends on your requirements:

- If strict ordering is business-critical (e.g., financial ledger): implement a **poison pill strategy** — when message 101 fails, stop consuming partition 0 entirely until 101 succeeds. Accept the lag. Never skip ahead.
- If processing is order-independent (e.g., incrementing a view counter): design your operations to be commutative and idempotent, so order does not matter.
- If ordering matters within a window but not globally: use event timestamps to reorder in the consumer before applying state changes.

---

## Section 5: Consumer Lag and Backpressure

### What Is Consumer Lag?

**Consumer lag** is the distance between where the producer is writing and where a consumer group has read up to.

```
Lag calculation:

  Latest offset in partition:       1,000,000
  Consumer group committed offset:    900,000
                                   ----------
  Lag:                                100,000 messages

  If consumer processes 1,000 messages/second:
  Time to catch up: 100,000 / 1,000 = 100 seconds
```

Lag = 0 means the consumer is fully caught up. Lag = 100,000 means the consumer is 100,000 messages behind. Whether that is a problem depends entirely on your use case.

```
LAG VISUALIZED

Producer write position:  offset 1,000,000
                          |
                          v
  [...][998000][999000][1000000]  <- new messages here
         ^
         |
  Consumer at offset 900,000
  Lag = 100,000

  Every second: producer writes 10,000 messages.
                consumer reads 9,000 messages.
                Lag GROWS by 1,000/second.
                Consumer is FALLING FURTHER BEHIND.
```

### Why Lag Matters — Real Business Impact

Lag translates directly to latency between an event happening in the world and your system reacting to it.

**Notifications:** If your notifications consumer has a lag of 100,000 messages and processes at 1,000 messages/second, users receive notifications 100 seconds after the triggering event. On a high-traffic day, lag can reach millions — users getting "your order was placed" notifications hours later.

**Fraud detection:** At **Netflix** and financial institutions, fraud detection consumers must process events in near real-time. A consumer lag of 1 million events with a throughput of 10,000/second means fraud is detected 100 seconds after it occurred. For credit card fraud, this delay means the fraudulent transaction is already complete.

**Analytics dashboards:** A lag of several minutes is often acceptable. Business analysts viewing a dashboard refreshed every 5 minutes are not harmed by a 2-minute event processing delay.

The L6 design principle: **set your SLA for consumer lag at design time, not in the postmortem**. Decide upfront what lag is acceptable for each consumer group and build monitoring alerts around those thresholds.

### Root Causes of High Consumer Lag

**Cause 1: Slow message processing.** The consumer reads messages but each message takes too long to process. If each message requires a synchronous database write at 20ms, and you process sequentially, you can handle 50 messages/second per consumer thread. If the producer generates 500/second per partition, you need 10 consumer threads per partition.

**Cause 2: Consumer crashing and restarting.** A consumer that crashes repeatedly does not make forward progress. Every restart means replaying messages from the last committed offset. If the consumer crashes because of a specific malformed message (a **poison pill message**), it will crash on the same message every restart, never advancing.

**Cause 3: Producer bursts.** Black Friday traffic spikes. A marketing email blast sends 10 million users to the site simultaneously. The producer writes events at 100× the normal rate for 30 minutes. Your consumer group, sized for normal traffic, falls behind rapidly. The backlog takes hours to drain.

**Cause 4: Downstream service slowdown.** The consumer writes processed results to a database. The database is slow due to an unrelated index rebuild. Consumer throughput drops from 10,000/second to 100/second. Lag grows by 9,900/second.

### Monitoring Consumer Lag

Kafka exposes consumer lag natively through its admin API. The standard command-line tool:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group my-consumer-group
```

Output shows per-partition lag:

```
GROUP              TOPIC    PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
my-consumer-group  orders   0          900,000         1,000,000       100,000
my-consumer-group  orders   1          995,000         1,000,000         5,000
my-consumer-group  orders   2          999,500         1,000,000           500
```

For production monitoring at scale, teams use:

- **Burrow**: LinkedIn's open-source Kafka consumer lag monitor. Evaluates whether a consumer is making progress (even with lag) vs. falling further behind or stalled.
- **Prometheus + kafka_exporter**: Exposes `kafka_consumer_group_lag` as a Prometheus metric. Alert when lag > 10,000 for more than 5 minutes.
- **AWS CloudWatch / Confluent Control Center**: Managed Kafka platforms provide lag dashboards out of the box.

A well-designed alerting rule:

```yaml
alert: KafkaConsumerLagHigh
condition: kafka_consumer_group_lag{group="fraud-detection"} > 50000
  for: 5m
severity: page
message: "Fraud detection consumer lag exceeds 50k messages for 5+ minutes.
          Real-time fraud detection SLA is at risk."
```

### Backpressure: When the Consumer Says "Slow Down"

In systems with direct connections (like a web server calling a database), the server can detect that the database is slow and back off. This is called **backpressure**. The fast component slows down to match the slow component.

Kafka does not have native backpressure in the traditional sense. The producer does not know how fast consumers are reading. The producer writes as fast as it wants (up to configured rate limits) and Kafka buffers the messages.

This is by design. Kafka's explicit choice is to **absorb speed mismatches** rather than slow down the producer. The tradeoff: if consumers fall behind indefinitely, the topic grows. When it exceeds the retention limit (7 days by default), old messages are deleted — even if the consumer has not read them yet.

```
WHAT HAPPENS WHEN RETENTION EXPIRES

  Day 0:  Producer writes offsets 0 - 1,000,000.
  Day 1:  Producer writes offsets 1,000,001 - 2,000,000.
  ...
  Day 7:  Producer writes offsets 7,000,001 - 8,000,000.
          Retention period (7 days) expires for Day 0 data.
          Offsets 0 - 1,000,000 are DELETED from Kafka.

  Consumer group stuck at offset 500,000 since Day 0:
          Tries to read offset 500,000.
          ERROR: "Offset out of range" - that data no longer exists.
          Consumer must reset to earliest available offset
          OR acknowledge that data is permanently lost.
```

This is the real danger of ignoring consumer lag. A consumer that is days behind risks losing data permanently when retention expires. Monitor lag. Fix the root cause. Scale out if needed.

**Application-level flow control:** Kafka consumers control their own read rate by controlling how often they call `poll()`. If processing is slow, simply call `poll()` less frequently. Kafka will not push messages to you — you always pull. This is an inherent form of backpressure: a slow consumer naturally slows its own read rate.

**Scale-out response:** The primary tool for reducing lag is adding more consumer instances to the consumer group — up to the number of partitions. If you have 6 partitions and 3 consumers, each handling 2 partitions, adding 3 more consumers (for a total of 6) cuts per-consumer load in half. Consumer lag should drop as the newly added instances catch up.

```
SCALE-OUT TO REDUCE LAG

Before scaling (lag growing):
  6 partitions, 3 consumers
  Each consumer: 2 partitions, 2,000 events/sec capacity
  Producer rate: 8,000 events/sec total
  Consumer capacity: 6,000 events/sec total
  Lag GROWS by: 2,000 events/sec

After scaling (lag shrinking):
  6 partitions, 6 consumers
  Each consumer: 1 partition, 2,000 events/sec capacity
  Consumer capacity: 12,000 events/sec total
  Producer rate: 8,000 events/sec total
  Lag SHRINKS by: 4,000 events/sec

  Time to drain 1,000,000 message backlog at -4,000/sec:
  1,000,000 / 4,000 = 250 seconds (~4 minutes)
```

If you are already at maximum consumers (one per partition) and still falling behind, you cannot scale the consumer group further without also increasing the partition count. Increasing partition count for an existing topic is possible but has operational considerations. Plan partition counts generously at topic creation time.

---

## Section 6: Producer Mechanics — How Messages Actually Get Into Kafka

Understanding what happens on the producer side is critical for two L6 concerns: throughput tuning and delivery guarantees.

### The Producer's Journey: From Application to Disk

When your application calls `producer.send(record)`, the message does not go to Kafka immediately. The Kafka producer client has a built-in buffer that accumulates messages before sending them in batches. This batching is the primary reason Kafka achieves high throughput — sending 1,000 messages in one network round trip is dramatically more efficient than 1,000 separate round trips.

```
PRODUCER INTERNALS

  Your Application Code:
    producer.send("order-placed", key="user-123", value="{...}")
    producer.send("order-placed", key="user-456", value="{...}")
    producer.send("order-placed", key="user-789", value="{...}")
          |
          v
  +---------------------------------------+
  |  PRODUCER BUFFER (RecordAccumulator)  |
  |                                       |
  |  Partition 0 batch: [msg1, msg3, ...] |
  |  Partition 1 batch: [msg2, msg4, ...] |
  |  Partition 2 batch: [msg5, msg7, ...] |
  +---------------------------------------+
          |
          | Trigger: batch.size reached (16KB default)
          |      OR  linger.ms elapsed (0ms default)
          v
  +------------------------+
  |  KAFKA BROKER (leader) |
  |  Writes to partition   |
  |  disk log segment      |
  +------------------------+
```

Two configuration parameters control when the buffer flushes to Kafka:

- **`batch.size`**: The maximum bytes to accumulate per partition batch before sending. Default is 16,384 bytes (16KB). Larger batches = better throughput, higher latency.
- **`linger.ms`**: How long to wait for the batch to fill before sending it anyway. Default is 0ms (send immediately). Setting to 5–10ms allows batches to accumulate, increasing throughput at the cost of a few milliseconds of extra latency.

For high-throughput use cases like **Airbnb's** event pipeline or **Twitter's** engagement tracking, teams set `linger.ms=5` and `batch.size=65536`. This alone can increase throughput by 10× compared to the default settings, because each network call carries many more messages.

### Acknowledgment Levels: The Durability vs. Latency Tradeoff

When the producer sends a batch, it can wait for different levels of acknowledgment from the broker. This is controlled by the **`acks`** configuration parameter and is one of the most important tuning decisions you make.

```
PRODUCER ACKS SETTINGS

acks=0 (Fire and forget):
  Producer -----> Broker
  Producer does NOT wait for any acknowledgment.
  Fastest possible throughput.
  Risk: if the broker crashes before writing, the message is LOST.
  Use case: metrics/telemetry where occasional loss is acceptable.

acks=1 (Leader acknowledged):
  Producer -----> Broker (Leader)
                  Broker writes to its local disk.
                  Broker sends ACK.
  Producer <----- ACK
  Risk: if the leader crashes before the followers replicate,
        the message is LOST (it was on the leader's disk, now gone).
  Use case: moderate durability, latency-sensitive applications.

acks=all (also acks=-1) (All replicas acknowledged):
  Producer -----> Broker (Leader)
                  Leader writes to disk.
                  Leader waits for all in-sync replicas to acknowledge.
                  ISR (in-sync replicas) write to their disks.
                  Leader sends ACK to producer.
  Producer <----- ACK
  Risk: lowest. Message is safe even if the leader crashes immediately
        after the ACK, because replicas have a copy.
  Use case: financial transactions, orders, anything critical.
  Cost: higher latency (one extra network round trip per batch).
```

The combination of `acks=all` and `min.insync.replicas=2` is the gold standard for production financial data. It means the producer's batch is confirmed only after at least 2 replicas have written it — surviving any single broker failure.

### Producer Retries and Idempotency

When a network error occurs between the producer and broker, the producer does not know if the message was written or not. If it retries, and the original message did arrive, the message appears twice in the partition log.

This is called **at-least-once** producer behavior: Kafka guarantees the message is delivered at least once, possibly more.

To eliminate duplicates at the producer level, enable **idempotent producer** mode:

```properties
enable.idempotence=true
```

With idempotent mode, each producer is assigned a **Producer ID (PID)** and each message gets a **sequence number**. If the broker receives the same PID + sequence number twice (a retry), it deduplicates — the second copy is silently dropped. Your topic receives exactly one copy of each message, even under network failures.

| Producer Mode | Configuration | What you get |
|---------------|---------------|--------------|
| Default | `acks=1` | At-most-once or at-least-once, duplicates possible |
| At-least-once | `acks=all` | No loss, possible duplicates |
| Exactly-once (producer side) | `enable.idempotence=true` + `acks=all` | No loss, no duplicates |
| Exactly-once (end-to-end) | Kafka Transactions (Part B) | Atomic read-process-write |

---

## Section 7: Consumer Group Rebalancing — The Hidden Disruption

Rebalancing is one of the most misunderstood and disruptive behaviors in Kafka deployments. Every Staff engineer working with Kafka needs to understand when it happens, why it is painful, and how to minimize it.

### What Is a Rebalance?

A **rebalance** is the process of redistributing partition assignments among the consumers in a group. Partitions are taken away from their current consumers and reassigned.

When does a rebalance happen?

- A new consumer instance joins the group (deploy of a new pod)
- An existing consumer leaves the group (pod is killed, scaling down)
- A consumer fails to send a heartbeat within `session.timeout.ms` (consumer appears dead)
- The topic's partition count changes

### Why Rebalances Are Painful

During a rebalance, **all consumption stops**. Every consumer in the group pauses reading from Kafka. Partitions are unassigned from their current consumers. The Kafka group coordinator reassigns partitions. Only after reassignment completes do consumers resume reading.

```
REBALANCE TIMELINE

T=0:   Consumer Group running normally.
       C1 reads P0, P1. C2 reads P2, P3. Lag = 0.

T=5s:  New consumer C3 joins the group.
       GROUP COORDINATOR TRIGGERS REBALANCE.

T=5s to T=8s:   ALL CONSUMPTION STOPS.
       C1 stops reading P0, P1.
       C2 stops reading P2, P3.
       Kafka reassigns partitions.

T=8s:  C1 reads P0. C2 reads P2. C3 reads P1, P3.
       Consumption resumes.

       During the 3-second stop: producer kept writing.
       Lag spiked by: 3 seconds * producer_rate messages.
       If producer_rate = 10,000/sec, lag grew by 30,000 messages.
```

For high-throughput systems, even a 3-second rebalance pause can cause significant lag. In the worst case, a misconfigured consumer triggers rebalances every few minutes (called a **rebalance storm**), and the consumer group never catches up.

### Common Causes of Accidental Rebalances

**Cause 1: Consumer taking too long to process a batch.**

Kafka's `max.poll.interval.ms` (default: 5 minutes) is the maximum time between two successive `poll()` calls. If your consumer takes more than 5 minutes to process a batch and does not call `poll()` again, Kafka assumes it is dead and triggers a rebalance.

Fix: reduce the batch size per poll (`max.poll.records`), or increase `max.poll.interval.ms` if processing genuinely takes a long time.

**Cause 2: JVM garbage collection pauses.**

Long GC pauses in Java/Scala consumers can cause the consumer to miss heartbeats for several seconds. Kafka's `session.timeout.ms` (default: 10–45 seconds depending on version) triggers a rebalance if heartbeats are missed.

Fix: tune GC settings, or use G1GC/ZGC for more predictable pause times.

**Cause 3: Slow deployment rollouts.**

Rolling deployment of a consumer group (replacing pods one at a time) causes one rebalance per pod replacement. For a group with 20 pods, this means 20 consecutive rebalances during a deploy.

Fix: use **static group membership** (`group.instance.id`). With static membership, when a consumer leaves and rejoins with the same instance ID (within `session.timeout.ms`), Kafka skips the rebalance and just reassigns the same partitions back to it. This is the single most impactful configuration change for reducing rebalance frequency in Kubernetes deployments.

```properties
group.instance.id=consumer-pod-7   # Set per-pod, unique and stable
session.timeout.ms=60000           # Give pods 60 seconds to restart
```

### Cooperative Rebalancing: The Modern Approach

Kafka 2.4+ introduced **cooperative incremental rebalancing** (via the `CooperativeStickyAssignor`). Instead of stopping all consumption and reassigning everything from scratch, the new algorithm reassigns only the partitions that need to move.

```
EAGER REBALANCING (old, default before Kafka 3.x):
  All partitions unassigned -> all consumers stop -> reassign all -> resume
  Stop time: proportional to number of partitions and consumers

COOPERATIVE REBALANCING (Kafka 2.4+):
  Only partitions that NEED to move are revoked -> rest keep consuming
  First round: consumers revoke only the "moving" partitions
  Second round: revoked partitions reassigned to new consumer
  Other partitions: never stop

  Consumer group of 10 consumers, 100 partitions:
  1 new consumer joins -> only ~10 partitions need to move
  90 partitions keep running uninterrupted
  Stop time: near zero for 90% of the group
```

To use cooperative rebalancing:

```properties
partition.assignment.strategy=org.apache.kafka.clients.consumer.CooperativeStickyAssignor
```

This is now the default in Kafka 3.1+. If you are on an older version, opt in explicitly. For large consumer groups at companies like **Shopify** and **Stripe**, enabling cooperative rebalancing reduced rebalance-related lag spikes by over 90%.

---

## Section 8: Delivery Semantics — At-Most-Once, At-Least-Once, Exactly-Once

Delivery semantics describe the guarantee your system makes about how many times a message is processed end-to-end, from producer writing to consumer finishing. This is one of the most common L6 interview topics around Kafka because the right answer always depends on business requirements and system design tradeoffs.

### At-Most-Once Delivery

The message is processed zero or one times. It might be lost. It is never processed more than once.

How you accidentally get this: auto-commit offsets BEFORE processing. The consumer fetches message, commits offset (marking it as done), then crashes before finishing processing. On restart, the consumer starts after that message. The message was never processed — it was processed zero times.

When this is acceptable: telemetry, metrics, analytics counters where losing 0.01% of events has no business impact. If you are counting page views on a dashboard, losing a few events is fine. LinkedIn's early click-tracking pipelines used at-most-once because dashboard approximations were acceptable.

### At-Least-Once Delivery

The message is processed one or more times. It is never lost, but may be processed multiple times (duplicates possible).

How you get this: `acks=all` on the producer, manual commit AFTER processing. The consumer fetches message, processes it, then crashes before committing the offset. On restart, the consumer re-reads the same message from the last committed offset and processes it again.

When this is acceptable (with idempotent consumers): most production systems use at-least-once delivery and design their consumers to be **idempotent** — processing the same message twice produces the same result as processing it once. Database upserts (INSERT OR UPDATE) are naturally idempotent. Incrementing a counter is not — you need deduplication.

### Exactly-Once Delivery

The message is processed exactly one time. No loss, no duplicates.

This is the hardest guarantee to achieve and requires coordination across the entire pipeline. Kafka supports exactly-once semantics (EOS) through **transactions** — an atomic read-process-write operation. Part B covers Kafka transactions in depth.

```
DELIVERY SEMANTICS COMPARISON

+------------------+---------+------------+--------+-----------------------------+
| Semantic         | Loss?   | Duplicates?| Cost   | Use Case                    |
+------------------+---------+------------+--------+-----------------------------+
| At-most-once     | Yes     | No         | Low    | Metrics, telemetry          |
| At-least-once    | No      | Yes        | Medium | Most applications           |
|   + idempotent   | No      | Handled    | Medium | Orders, events with upserts |
| Exactly-once     | No      | No         | High   | Financial, billing, payments|
+------------------+---------+------------+--------+-----------------------------+
```

The L6 principle: design for at-least-once delivery first. Make your consumers idempotent. Only reach for Kafka transactions (exactly-once) when the business truly requires it — the operational and performance cost is real. **Stripe** uses exactly-once semantics for payment event processing. Their analytics pipeline uses at-least-once. Different guarantees for different pipelines, chosen deliberately.

---

## What You Have Learned in Part A

This first half of Chapter 33 has built a complete foundation for event-driven architecture and Kafka internals. The key principles:

| Concept | The Principle |
|---------|---------------|
| Event-driven vs. REST | Decouple producers and consumers in time and knowledge |
| When to use EDA | Coupling, fan-out, or speed mismatch justify the complexity |
| Kafka's origin | An append-only log where consumers track their own position |
| Partitions | Enable parallel writes; max consumer parallelism = partition count |
| Message keys | Guarantee per-key ordering; beware hot keys |
| Consumer groups | Each group reads independently; partition assigned to 1 consumer |
| Offsets | Consumer's position in the log; committed to `__consumer_offsets` |
| Replication | Leader + followers per partition; survives broker failures |
| Consumer lag | Distance from producer to consumer; translate to latency impact |
| Backpressure | Kafka buffers differences; lag beyond retention = data loss |
| Producer acks | acks=all + min.insync.replicas=2 for durable writes |
| Rebalancing | Partition reassignment stops consumption; minimize with cooperative assignor |
| Delivery semantics | At-least-once + idempotent consumers covers most use cases |

### The Mental Model That Connects Everything

Here is the single mental model that ties all of Part A together. Print this in your head before any Kafka-related interview question.

```
KAFKA END-TO-END MENTAL MODEL

  PRODUCERS                  KAFKA CLUSTER                  CONSUMERS
  ---------                  -------------                  ---------

  Service A  --+             +------------------+     +--> Group "analytics"
  Service B  --+-> Topic --> |  P0 [0][1][2]... |-----+--> Group "fulfillment"
  Service C  --+  "orders"   |  P1 [0][1][2]... |     +--> Group "fraud-detect"
                  (6 partitions,  P2 [0][1][2]... |
                   RF=3)     |  P3 [0][1][2]... |
                             |  P4 [0][1][2]... |
                             |  P5 [0][1][2]... |
                             +------------------+

Key facts you must know cold:
  1. Producers write to partition by hash(key) or round-robin
  2. Each partition is an ordered, append-only log
  3. Each consumer GROUP has its own independent offset per partition
  4. Within a group: 1 partition -> 1 consumer (never split)
  5. Max parallelism per group = number of partitions
  6. Replication factor = copies of each partition across brokers
  7. Consumer lag = latest_offset - consumer_committed_offset
  8. When lag > retention window: messages DELETED before consumer reads them
```

Part B continues with: Kafka Streams processing, exactly-once delivery semantics, Schema Registry and Avro, the outbox pattern for transactional event publishing, CQRS architecture, and event sourcing — the full set of patterns you need to design production event-driven systems at the L6 level.

---

*End of Chapter 33 Part A*
# Chapter 33: Event-Driven Architectures — Kafka and Streams (Part B)
## Staff-Level System Design Interview Prep

---

## Section 1: Delivery Semantics — The Three Guarantees

### Why This Matters Before You Write a Single Line of Code

Imagine you send a birthday email to your friend. Three things could have happened:

1. The email bounced on the network and never arrived. Your friend never got it.
2. The email arrived. One time. Perfect.
3. You hit send three times because you were unsure. Your friend got three copies and thinks you are strange.

In distributed systems, every message you send over a network faces the same three fates. Networks fail. Servers crash mid-write. Disks fill up. The system cannot always tell whether a message was received before the crash happened, so it has to decide: do I risk losing it, or do I risk sending it twice?

That decision is called a **delivery semantic**, and there are exactly three choices. Every engineer working with Kafka, RabbitMQ, SQS, Pulsar, or any other messaging system must pick one for every topic and every consumer. Getting this wrong in a payment system means double-charging customers. Getting it wrong in an analytics pipeline is completely fine and probably saves you money.

The three semantics are:

| Semantic | Messages Lost? | Messages Duplicated? | Typical Use |
|---|---|---|---|
| At-most-once | Yes (possible) | No | Metrics, logs, page views |
| At-least-once | No | Yes (possible) | Most production systems |
| Exactly-once | No | No | Payments, financial ledgers |

---

### At-Most-Once: "Fire and Forget"

**At-most-once** is the simplest and fastest semantic. The producer sends a message and does not wait for confirmation. If the network drops the message, it is gone. The consumer will never see it.

There is a second way at-most-once happens on the consumer side: the consumer reads a message from Kafka and immediately advances its offset (marks the message as "done") BEFORE it processes the message. If the consumer crashes after advancing the offset but before finishing processing, the message is skipped forever.

Think of it like shouting an announcement in a crowded hallway. Maybe people heard you. Maybe they did not. You are not going to check.

```
+----------+        network drops        +-------+
| Producer |  ------>  X  (lost)         | Kafka |
+----------+                             +-------+
    acks=0 (no wait)                         |
                                             | (no message stored)
                                         +----------+
                                         | Consumer |
                                         +----------+
                                         (never receives it)
```

**Consumer-side at-most-once:**

```
+----------+          +------------+          +---------+
| Kafka    |  msg 42  | Consumer   |          |   DB    |
+----------+ -------> +------------+          +---------+
                      | 1. Advance |
                      |  offset    |  <-- done! (committed)
                      | 2. CRASH   |
                      +------------+
                          msg 42 is skipped forever.
                          Consumer restarts at offset 43.
```

**When to use at-most-once:**

- Collecting page-view events for a dashboard. Losing 0.1% of events does not change the graph meaningfully.
- Application logs sent to a central logging system. A missing log line is not worth the overhead of guaranteeing delivery.
- Real-time metrics (CPU usage, request rate). The next metric arrives in one second anyway.

**Kafka producer config for at-most-once:**

```properties
acks=0
retries=0
```

`acks=0` means the producer sends and does not wait for any acknowledgment from the broker. This is the fastest possible setting. It is also the most dangerous for anything that matters.

---

### At-Least-Once: "Best Effort, No Loss"

**At-least-once** is what most production systems use. The guarantee is: the message will arrive. It might arrive more than once, but it will not be lost.

Here is how it works on the producer side: the producer sends a message and waits for an acknowledgment from the Kafka broker. If the acknowledgment never comes (because the network was slow, or the broker was restarting), the producer retries. The problem is: maybe the broker DID receive and store the message, and only the ack was lost. Now the producer retries, the broker stores a second copy, and the consumer sees the message twice.

```
+----------+    send msg    +-------+    store OK    +---------+
| Producer | -------------> | Kafka | -------------> |  Disk   |
+----------+                +-------+                +---------+
     |                          |
     |     <--- ACK lost ------ |   (network hiccup on the way back)
     |
     | (producer sees: no ack)
     |    send msg AGAIN   +-------+    store OK    +---------+
     | ------------------> | Kafka | -------------> |  Disk   |
     +                     +-------+   (duplicate!) +---------+
                               |
                           +----------+
                           | Consumer |  <-- sees msg TWICE
                           +----------+
```

On the consumer side: the consumer reads a message, processes it (writes to a database, sends a notification), and THEN commits the offset. If it crashes after processing but before committing the offset, it will re-read and re-process the same message on restart.

**Kafka producer config for at-least-once:**

```properties
acks=all
retries=2147483647
enable.idempotence=false
```

`acks=all` means the producer waits for the leader AND all in-sync replicas to confirm they wrote the message. Retries are set very high so the producer keeps trying on failure.

**The deduplication requirement:**

Because duplicates will happen, consumers must be **idempotent**. An idempotent operation is one where running it twice produces the same result as running it once.

The classic example is a database upsert:

```sql
-- Idempotent: running this twice does nothing harmful
INSERT INTO orders (id, status, amount)
VALUES ('order-abc-123', 'placed', 99.99)
ON CONFLICT (id) DO NOTHING;
```

The opposite of idempotent:

```sql
-- NOT idempotent: running this twice gives wrong result
UPDATE account SET balance = balance - 99.99 WHERE user_id = 'u456';
-- Run twice: deducts $99.99 twice. Customer is angry.
```

The lesson: at-least-once delivery is safe as long as your consumers are idempotent. Most teams choose at-least-once and make their consumers idempotent rather than paying the cost of exactly-once.

---

### Exactly-Once: "The Gold Standard (With Caveats)"

**Exactly-once** is the guarantee that every message is processed exactly one time, even if producers retry and consumers crash. No lost messages, no duplicates. Sounds perfect. The reality is more nuanced.

Kafka introduced **Exactly-Once Semantics (EOS)** in version 0.11 in 2017. It has two components working together:

**Component 1: Producer Idempotence**

Each producer gets a unique **Producer ID (PID)** assigned by the broker. Every message also gets a **sequence number**. If the producer retries a message, it sends the same PID + sequence number. The broker checks: have I already seen this sequence number from this producer? If yes, it discards the duplicate without storing it.

```
+----------+  PID=7, seq=100, msg="pay $50"  +-------+
| Producer | --------------------------------> | Kafka |
+----------+                                  +-------+
     |                                             |
     | (network hiccup, no ack)                    | (stored)
     |  PID=7, seq=100, msg="pay $50"  (retry)     |
     | -------------------------------->            |
     |                                  Kafka sees: PID=7 seq=100
     |                                  already stored -> DISCARD
     +                                  Producer gets ack. One copy stored.
```

**Component 2: Transactions**

Producer idempotence handles duplicates within one partition. But what if your processing involves reading from one topic, computing something, and writing to another topic while also committing an offset? You need all three actions to succeed or fail together. That is what **Kafka transactions** provide.

How Kafka transactions work:

```
+------------------+
| Producer (app)   |
+------------------+
        |
        | 1. beginTransaction()
        |
        | 2. write to topic "payments-output" partition 2
        | 3. write to topic "notifications" partition 5
        | 4. commit consumer offset for "payments-input" partition 1
        |
        | 5. commitTransaction()
        |       --> All three actions land atomically, or none do.
        +
```

If the producer crashes between steps 2 and 5, Kafka rolls back all writes and the consumer offset is not advanced. The transaction never happened from the consumer's point of view.

**The critical caveat: Kafka transactions are Kafka-internal only.**

If step 2 above also writes a row to a PostgreSQL database, that PostgreSQL write is NOT inside the Kafka transaction. PostgreSQL does not know about Kafka transactions. If Kafka rolls back but the Postgres write already happened, your data is inconsistent.

```
+----------+   Kafka txn   +-------+
| Producer | ------------> | Kafka |  <-- Kafka rolls back
+----------+               +-------+
     |
     +---> Postgres write  +-----------+
                           | Postgres  |  <-- Postgres does NOT roll back
                           +-----------+
                           NOW: Kafka has nothing, Postgres has a row.
                           INCONSISTENT STATE.
```

**True end-to-end exactly-once requires:**

1. Kafka transactions for the Kafka side
2. Idempotent database writes using a unique key on the external store side

Both together. Neither alone is sufficient.

**The performance cost:**

Exactly-once with transactions adds roughly 20–30% throughput overhead compared to at-least-once. The broker must do extra coordination work (two-phase-commit-like protocol) for every transaction.

**When to use exactly-once:**

- Payment processing (each payment must debit exactly once)
- Inventory deduction (each item must be decremented exactly once)
- Financial ledger entries (each credit/debit must appear exactly once)

**When NOT to use exactly-once:**

- Analytics pipelines (near-duplicates in event counts are acceptable)
- Log aggregation (losing 0.01% of logs is fine)
- Any read-heavy workload where writes are rare

**Kafka producer config for exactly-once:**

```properties
acks=all
enable.idempotence=true
transactional.id=payment-processor-instance-1
max.in.flight.requests.per.connection=5
```

---

### Idempotent Consumer: The Practical Middle Ground

Most staff-level engineers in production choose **at-least-once delivery plus an idempotent consumer**. This gives you effectively-exactly-once behavior at a lower cost than Kafka's native transactions.

The pattern:

```
+-------+    duplicate    +--------------+    check dedup    +-------------+
| Kafka |  msg (order-42) | Consumer     | ----------------> | Dedup Table |
+-------+ ------------->  +--------------+                   +-------------+
                               |                                    |
                               |     "order-42 already processed"   |
                               | <---------------------------------- |
                               |
                               | SKIP. Do not process again.
                               +
```

The dedup table stores a unique event identifier. Before processing any consequential action, the consumer checks whether this event ID has been seen before. If yes: skip. If no: process and insert the ID into the dedup table atomically.

Example: notification service receiving "send email to user 123 for order 456"

```sql
-- Check first
SELECT id FROM emails_sent
WHERE user_id = 123 AND order_id = 456;

-- If row exists: skip. If not: insert and send email.
INSERT INTO emails_sent (user_id, order_id, sent_at)
VALUES (123, 456, NOW())
ON CONFLICT (user_id, order_id) DO NOTHING;

-- Only send email if INSERT affected 1 row (not a conflict)
```

User receives exactly one email. Even if the Kafka message arrives three times due to retries, the constraint on `(user_id, order_id)` ensures only one insert succeeds.

**Good deduplication keys:**

- A UUID embedded in the message payload at creation time
- A composite key: `(entity_id, event_type, event_timestamp)`
- An idempotency key provided by the caller (Stripe uses this pattern)

**Bad deduplication keys:**

- Kafka offset alone (offsets can shift after topic compaction or recreation)
- Consumer-generated timestamp (two consumers processing simultaneously may both think they are first)

---

## Section 2: Kafka Internals — How It Actually Works

### Log Segments: What Kafka Stores on Disk

When a student first hears "Kafka stores messages on disk," they think: "Won't that be slow?" The answer is: disk I/O is sequential, and sequential disk I/O on modern SSDs is extremely fast — often faster than random-access memory operations. Kafka is designed entirely around sequential disk writes, which is why it can sustain millions of writes per second.

Each **partition** in Kafka is a directory on the broker's filesystem. Inside that directory are **segment files**:

```
/kafka-data/my-topic-0/
    00000000000000000000.log    <-- messages with offsets 0 to 99
    00000000000000000000.index  <-- maps offset -> byte position
    00000000000000000000.timeindex
    00000000000000000100.log    <-- messages with offsets 100 to 199
    00000000000000000100.index
    00000000000000000200.log    <-- active segment (currently being written)
    00000000000000000200.index
```

Each `.log` file is up to 1 GB by default. When a segment fills up, a new one is created. Only the newest (active) segment is being written to. Old segments are read-only.

The `.index` file is the key to fast consumer seeking. It maps from offset number to byte position within the `.log` file.

```
+------------------+    "give me offset 150"    +-----------+
| Consumer Request | -------------------------> | Broker    |
+------------------+                            +-----------+
                                                     |
                              1. Which segment?      |
                              offset 150 is in       |
                              00000000000000000100.log|
                                                     |
                              2. Look up index:      |
                              offset 150 -> byte 38472
                                                     |
                              3. Seek to byte 38472  |
                              in that file.          |
                              Read message.          |
                              O(1) lookup. Done.     +
```

Without the index, finding offset 150 would require scanning every byte from offset 0 forward. The index makes it constant-time regardless of how many messages are in the partition.

**Log retention:** Kafka deletes old segments based on time (default: 7 days) or total size (default: none). When a segment's age exceeds the retention period, the whole segment file is deleted.

---

### Replication: How Data Stays Safe

Kafka's replication model is straightforward but there are important details at the L6 level.

Every partition has exactly one **leader** and zero or more **followers** (replicas). Producers ALWAYS write to the leader. Consumers ALWAYS read from the leader (with some newer versions supporting follower reads). Followers exist only for durability.

```
+----------+   write   +-------------------+
| Producer | --------> | Broker 1 (Leader) |
+----------+           +-------------------+
                               |  replicate
                    +----------+-----------+
                    |                      |
          +-----------------+   +-----------------+
          | Broker 2        |   | Broker 3        |
          | (Follower)      |   | (Follower)      |
          +-----------------+   +-----------------+

Replication factor = 3. Can survive 2 broker failures.
```

The **ISR (In-Sync Replicas)** list tracks which followers are caught up with the leader. A follower that falls behind by more than `replica.lag.time.max.ms` (default: 30 seconds) is removed from the ISR. If it catches up later, it is added back.

The combination of settings that gives strong durability:

```properties
# On the producer:
acks=all

# On the topic:
min.insync.replicas=2
replication.factor=3
```

With these settings: the broker only acknowledges a write after the leader AND at least one follower have stored it. If the leader fails immediately after, the follower has the data and can serve as the new leader. No data loss.

```
min.insync.replicas=2 with replication.factor=3:

  Scenario A: All 3 brokers up
  --> write needs ack from 2 --> succeeds normally

  Scenario B: 1 broker down (ISR = {leader, follower2})
  --> write needs ack from 2 --> still works

  Scenario C: 2 brokers down (ISR = {leader only})
  --> write needs ack from 2 --> BLOCKED (only 1 ISR)
  --> producer gets NotEnoughReplicasException
  --> this is intentional: better to reject writes than lose data
```

**Leader election on failure:**

Kafka's internal component called the **controller** (one broker elected among all brokers) watches for leader failures via ZooKeeper or KRaft (newer Kafka). When a leader dies, the controller picks the first replica in the ISR list as the new leader and broadcasts the change to all consumers and producers. This typically takes 5–30 seconds.

---

### Log Compaction: Topics as State Stores

Regular Kafka topics delete old messages after a time window. **Log compaction** is a different retention strategy: instead of deleting by time, Kafka keeps only the LATEST message for each KEY. Older messages with the same key are garbage collected.

Think of it like a contact book. If you update someone's phone number three times, you only need the most recent one. The first two entries are obsolete. Log compaction throws them away but keeps the latest.

```
BEFORE compaction (raw log):
  offset 0:  key=user:1  value={name:"Alice", email:"a@x.com"}
  offset 1:  key=user:2  value={name:"Bob",   email:"b@x.com"}
  offset 2:  key=user:1  value={name:"Alice", email:"alice@new.com"}  <-- updated
  offset 3:  key=user:3  value={name:"Carol", email:"c@x.com"}
  offset 4:  key=user:2  value=null   <-- tombstone (delete user:2)

AFTER compaction:
  offset 2:  key=user:1  value={name:"Alice", email:"alice@new.com"}
  offset 3:  key=user:3  value={name:"Carol", email:"c@x.com"}
  (user:2 deleted by tombstone, offset 0 superseded by offset 2)
```

**Tombstone messages:** Publishing a message with a non-null key and a null value signals to the compaction process: delete all records for this key. It is the equivalent of a DELETE in a database.

**Why this matters for system design:**

A compacted topic behaves like a key-value store that you can subscribe to. A new consumer starting from `offset=0` on a compacted topic will read every key exactly once (the latest value). After replaying the whole topic, the consumer has a complete, current view of all keys.

This is how **Kafka Streams** builds its local state stores. It is also how **ksqlDB** maintains materialized views. The compacted changelog topic IS the persistent store. If the local RocksDB state is lost (disk failure), the stream processor just replays the changelog topic to rebuild it.

**Topic config for log compaction:**

```properties
cleanup.policy=compact
min.cleanable.dirty.ratio=0.5
segment.ms=3600000
```

---

### Producer Batching and Compression

Producers do not send one message at a time. That would be like mailing one letter per envelope per sentence. Instead, Kafka producers accumulate messages in memory and send them as batches.

```
Time 0ms:  msg A arrives --> accumulate in buffer
Time 1ms:  msg B arrives --> accumulate in buffer
Time 3ms:  msg C arrives --> accumulate in buffer
Time 5ms:  linger.ms expires --> send batch {A, B, C} in one network call
                                  + compress the batch together
```

**Key producer configs:**

```properties
batch.size=16384        # 16 KB: max bytes per batch per partition
linger.ms=5            # wait up to 5ms for more messages before sending
compression.type=lz4   # compress the batch before sending
```

**Why batching improves compression:**

Similar messages (e.g., 100 JSON events from the same app) have a lot of repeated structure: field names, common values, schema. When compressed together, they achieve 3–5× better ratios than if compressed individually.

**Compression codec tradeoffs:**

| Codec | Speed | Compression Ratio | Best For |
|---|---|---|---|
| none | fastest | 1x | latency-critical, already binary |
| lz4 | very fast | 2-3x | high-throughput, latency-sensitive |
| snappy | fast | 2-3x | balanced (Google's choice) |
| gzip | slow | 3-5x | bandwidth-constrained, batch jobs |
| zstd | moderate | 3-4x | best balance of speed and ratio |

LinkedIn reported 3–5× bandwidth savings across their Kafka clusters by switching to gzip for their JSON event streams. At their scale (trillions of messages per day), this translates to significant infrastructure cost reduction.

---

### Consumer Polling: The Pull Model

Kafka uses a **pull model**: consumers ask Kafka for messages ("give me the next batch"). Kafka does NOT push messages to consumers.

Compare to a push model:

```
PUSH model (e.g., RabbitMQ with push consumers):
  +--------+  "here are 500 msgs"  +-----------+
  | Broker | --------------------> | Consumer  |
  +--------+                       +-----------+
  Problem: if consumer is slow, broker overwhelms it.
  Solution needed: backpressure (complex).

PULL model (Kafka):
  +-----------+  "give me up to 500 msgs"  +--------+
  | Consumer  | --------------------------> | Kafka  |
  +-----------+                             +--------+
  Consumer controls its own pace.
  If it is slow, it simply polls less often.
  No backpressure mechanism needed.
```

**Key consumer configs:**

```properties
max.poll.records=500              # max messages per poll call
max.poll.interval.ms=300000       # 5 minutes: max time between polls
fetch.min.bytes=1                 # return data as soon as 1 byte available
fetch.max.wait.ms=500             # max wait if less than fetch.min.bytes available
```

**The most common consumer misconfiguration:**

`max.poll.interval.ms` is the maximum time allowed between two consecutive `poll()` calls. If a consumer takes longer than this to process a batch (because processing is slow), Kafka assumes the consumer is dead and triggers a rebalance.

```
max.poll.records = 500
Processing time per message = 1 second
Total time to process one batch = 500 seconds

max.poll.interval.ms = 300000 (5 minutes = 300 seconds)

500 seconds > 300 seconds --> consumer kicked from group --> rebalance
New consumer takes over same partitions --> fetches same 500 messages
Same slow processing --> same timeout --> infinite rebalance loop
```

The fix: either reduce `max.poll.records` (process fewer messages per batch), increase `max.poll.interval.ms`, or make message processing faster.

---

### Partition Rebalancing

When a consumer **joins** or **leaves** a consumer group, Kafka must redistribute partitions among the remaining consumers. This is called a **rebalance**.

```
BEFORE rebalance (3 consumers, 6 partitions):
  Consumer 1: partition 0, partition 1
  Consumer 2: partition 2, partition 3
  Consumer 3: partition 4, partition 5

Consumer 3 crashes. Rebalance triggered.

AFTER rebalance (2 consumers, 6 partitions):
  Consumer 1: partition 0, partition 1, partition 4
  Consumer 2: partition 2, partition 3, partition 5
```

The problem: during the old (eager) rebalance protocol, ALL consumers stop reading for the duration of the rebalance. Even Consumer 1 and Consumer 2, which did not change their assignments, must pause.

For a large consumer group with 50 consumers, rebalances can take 30–60 seconds. During that time, no messages are being processed. This creates latency spikes visible in dashboards.

**Cooperative incremental rebalancing (Kafka 2.4+):**

Only partitions that are actually being moved pause. Consumers that keep their partitions keep reading.

```
COOPERATIVE rebalance when Consumer 3 crashes:
  Consumer 1: keeps partitions 0, 1 (CONTINUES READING)
  Consumer 2: keeps partitions 2, 3 (CONTINUES READING)
  Only partitions 4, 5 are temporarily unassigned while being moved.
```

**Sticky assignment:**

Kafka tries to assign the same partitions to the same consumers across rebalances. This minimizes the number of partitions that actually move, reducing disruption.

Enable cooperative rebalancing in your consumer:

```properties
partition.assignment.strategy=org.apache.kafka.clients.consumer.CooperativeStickyAssignor
```

---

## Section 3: Event-Driven Anti-Patterns

These are the patterns that look reasonable to a junior engineer and cause serious problems at scale. At L6 interviews, interviewers expect you to name anti-patterns proactively and explain why alternatives are better.

---

### Anti-Pattern 1: Over-Eventing — Events for Everything

A team decides to publish an event for every field change on every entity.

```
UserEmailChanged
UserNameChanged
UserPhoneChanged
UserAddressLine1Changed
UserAddressLine2Changed
UserBillingEmailChanged
UserMarketingOptInChanged
... (97 more event types)
```

This feels like good domain modeling. It is not.

**Problems:**

Consumers must subscribe to 100 event types and write handler code for each. The event schemas multiply: 100 schemas to maintain, version, and document. If a downstream service wants to rebuild a user's current state from scratch (e.g., after a disaster), it must replay 100 event types in order and apply each delta correctly. One missing handler and the state is wrong.

**Better approach:**

```
UserUpdated (contains full user snapshot, or a diff of changed fields)
```

One event. Consumers get everything they need. Schema is one document. State rebuild is replay of one event type.

The **L6 principle**: events should be designed for consumers, not for producers. The producer knows what changed. The consumer knows what it needs. Design the event to minimize consumer complexity.

A coarser-grained event with a full snapshot costs a few extra bytes. The reduction in consumer complexity and operational overhead is worth it almost always.

---

### Anti-Pattern 2: Tight Coupling via Events

A team adds fields to an event payload that only one specific consumer uses.

```json
{
  "event_type": "OrderPlaced",
  "order_id": "ord-123",
  "user_id": "usr-456",
  "items": [...],
  "marketing_campaign_id": "camp-789-summer-sale",
  "marketing_attribution_source": "email_drip_sequence_3"
}
```

The `marketing_campaign_id` field is only used by the Marketing Analytics service. No other consumer cares about it.

**Why this is a problem:**

The Order service is now coupled to Marketing service's internal data model. When Marketing changes how they track campaigns (they rename `marketing_campaign_id` to `campaign_tracking_code`), the Order service schema must change. Every consumer of the `OrderPlaced` event must update their deserializer to handle both old and new field names during the migration.

What was a Marketing-internal refactor is now a cross-team coordination event affecting the Order service, Fulfillment service, Analytics service, and every other consumer of `OrderPlaced`.

**Better approach:**

`OrderPlaced` contains only the natural order domain data. The Marketing service enriches it independently using a lookup against its own campaign attribution data.

```
OrderPlaced event:
{
  "order_id": "ord-123",
  "user_id": "usr-456",
  "items": [...],
  "placed_at": "2026-01-15T10:30:00Z"
}

Marketing consumer:
  1. Receives OrderPlaced
  2. Looks up: what campaign was user usr-456 attributed to at time of order?
  3. Processes attribution in Marketing's own system
  4. Marketing's internal schema can change freely without touching OrderPlaced
```

**The rule**: events should contain the natural data of the domain that produced them. Consumer-specific enrichment belongs in the consumer.

---

### Anti-Pattern 3: Events as RPC (Request-Reply over Kafka)

A team needs Service A to call Service B and get a result.

```
Service A publishes: "ProcessPaymentRequest" { request_id: "req-1", amount: 50 }
Service A waits...
Service B processes and publishes: "PaymentResponse" { request_id: "req-1", status: "approved" }
Service A correlates the response by request_id
```

This is using Kafka as a synchronous RPC mechanism. It has several problems:

```
+----------+  publish req  +-------+  consume req  +----------+
| Service A | -----------> | Kafka | ------------> | Service B|
+----------+               +-------+               +----------+
     |                                                  |
     | wait for response...                             | publish response
     |                        +-------+                 |
     | <----- response ------ | Kafka | <-------------- +
     +                        +-------+
     
Problems:
  - Latency: 2 Kafka round trips instead of 1 direct call
  - Complexity: Service A must correlate responses by request_id
  - Timeouts: how long does Service A wait? What if response never comes?
  - Ordering: responses may arrive out of order
```

Kafka is designed for **asynchronous, decoupled flows** where the producer does not wait for a result. If Service A needs a synchronous answer from Service B, use REST or gRPC. Direct, synchronous calls have lower latency and simpler semantics for request-reply patterns.

**When async reply IS acceptable:**

Some long-running operations (fraud analysis, video transcoding) legitimately take minutes. In these cases, event-driven reply is appropriate because the caller cannot block a thread for minutes anyway. The caller publishes a request, does other work, and handles the response whenever it arrives. This is different from the anti-pattern, which tries to use Kafka as a synchronous call.

---

### Anti-Pattern 4: Ignoring the Dead Letter Queue

A **poison message** is a message that always fails processing: malformed JSON, unexpected null, data that triggers an unhandled exception. Every system eventually encounters poison messages.

Without a **Dead Letter Queue (DLQ)**:

```
+-------+  partition 5  +-----------+
| Kafka | ------------> | Consumer  |
+-------+               +-----------+
  offset 1000               | process
  offset 1001               | process
  offset 1002 (POISON) ---> | EXCEPTION
                            | retry... EXCEPTION
                            | retry... EXCEPTION
                            | stuck forever
                            |
                    offset 1003, 1004, 1005...
                    NEVER PROCESSED.
                    Partition 5 is frozen.
```

With a Dead Letter Queue:

```
offset 1002 (POISON) --> retry 1 --> FAIL
                     --> retry 2 --> FAIL
                     --> retry 3 --> FAIL
                     --> write to dead-letter-topic: "my-topic-DLQ"
                     --> advance offset to 1003
                     --> CONTINUE PROCESSING 1003, 1004, 1005...
```

**DLQ must be monitored.** An unmonitored DLQ is a silent failure. Messages pile up. Nobody knows. Netflix discovered an unmonitored DLQ containing 10 million failed events over a three-month period. Those events were customer watch history records. They were never retried or investigated until an unrelated incident surfaced the issue. By then, the events were too stale to replay meaningfully.

**DLQ best practices:**

- Alert when DLQ message count exceeds a threshold
- Include the original error and stack trace in the DLQ message metadata
- Build a replay tool: ability to re-publish DLQ messages back to the original topic after fixing the processing bug
- Tag DLQ messages with original offset, partition, and timestamp for debugging

---

### Anti-Pattern 5: No Idempotency on Consumers

Already covered in the delivery semantics section, but worth repeating as an anti-pattern because it shows up constantly in production incidents.

At-least-once delivery is not a Kafka bug. It is an intentional design choice for durability. Duplicates WILL arrive. The system MUST handle them.

```
WRONG (non-idempotent consumer):

+-------+  "charge $50 for order-123"  +-----------+  debit $50  +------+
| Kafka | ---------------------------> | Consumer  | ----------> | Bank |
+-------+ ---------------------------> +-----------+             +------+
          (duplicate due to retry)
                                        debit $50 again          +------+
                                        -----------------------> | Bank |
                                                                 +------+
                                        User charged $100. User very angry.

CORRECT (idempotent consumer):

+-------+  "charge $50 for order-123"  +-----------+
| Kafka | ---------------------------> | Consumer  |
+-------+                              +-----------+
                                            |
                                   check: has order-123 been charged?
                                            |
                                       NO --> charge $50, record order-123
                                            |
+-------+  duplicate: order-123  +-----------+
| Kafka | ----------------------> | Consumer  |
+-------+                         +-----------+
                                       |
                                  check: has order-123 been charged?
                                       |
                                   YES --> skip. Done.
                                       |
                               User charged $50 exactly once.
```

---

### Anti-Pattern 6: Fan-out at the Consumer

A single consumer subscribes to a topic and then calls 10 downstream services for each message.

```
WRONG: fan-out inside consumer

+-------+  OrderPlaced  +--------------+
| Kafka | ------------> | Order        |
+-------+               | Consumer     |
                        +--------------+
                             |
                +------------+-------------+----------+
                |            |             |          |
          Inventory    Fulfillment     Analytics   Shipping
          Service      Service        Service     Service
          (REST call)  (REST call)    (REST call) (REST call)
                |
           call FAILS -->
           retry all 4? 
           track which succeeded?
           complex error handling in the consumer
```

The consumer becomes a coordination layer. Partial failures are hard to handle: if the Inventory call succeeded but Fulfillment failed, do you retry Fulfillment (and risk double-processing Inventory)?

**Better: fan-out in Kafka**

```
CORRECT: fan-out at the messaging layer

+-------+  OrderPlaced  +-------+  OrderPlaced  +-----------------+
| Order | ------------> | Kafka | ------------> | Inventory       |
| Service               +-------+               | Consumer (own)  |
+-------+                   |                   +-----------------+
                            |
                            +-------------->  +-----------------+
                            |                 | Fulfillment     |
                            |                 | Consumer (own)  |
                            |                 +-----------------+
                            |
                            +-------------->  +-----------------+
                                              | Analytics       |
                                              | Consumer (own)  |
                                              +-----------------+
```

Each downstream service has its own consumer group. Each handles its own failures independently. If Analytics is slow or failing, Inventory and Fulfillment are unaffected. This is the entire point of the event-driven architecture: independent failure domains.

---

## Section 4: Applied Examples

### Example 1: Uber's Real-Time Ride Matching

**The problem:** 1 million rides per day. Drivers send GPS updates every 5 seconds. When a rider requests a ride, the system must find and match a nearby available driver in under 1 second.

**The math:**
- 1M active drivers during peak hour
- 1 GPS update per driver per 5 seconds
- 1,000,000 / 5 = **200,000 GPS events per second**

A single REST endpoint cannot absorb 200K requests per second and remain available for rider requests at the same time. Kafka absorbs the GPS event flood, and the matching service consumes at its own pace.

**Event flow:**

```
+------------+  GPS update  +------------------+  partition key=driver_id
| Driver App | -----------> | "driver-locations"|
+------------+              | Kafka Topic       |
                            +------------------+
                                     |
                            +------------------+
                            | Matching Service |  (consumer group)
                            +------------------+
                                     |
                            builds in-memory index:
                            driver_id -> {lat, lng, status, last_seen}
                                     |
+----------+  ride request  +------------------+
| Rider App | ------------> | "ride-requests"  |
+----------+                | Kafka Topic      |
                            +------------------+
                                     |
                            +------------------+
                            | Matching Service |
                            +------------------+
                                     |
                   geospatial query: find available drivers within 0.5km
                                     |
                            +------------------+
                            | "ride-matched"   |
                            | Kafka Topic      |
                            +------------------+
                                     |
                      +-------------+-----------+
                      |                         |
               +-----------+           +----------+
               | Driver    |           | Rider    |
               | Notif.    |           | Notif.   |
               | Service   |           | Service  |
               +-----------+           +----------+
```

**Why Kafka instead of REST:**

Without Kafka, 200K GPS updates per second would arrive directly at the matching service. If the matching service is overloaded (during surge pricing events, bad weather), it drops requests. Kafka acts as a buffer: GPS events queue up in Kafka during traffic spikes, and the matching service processes them at maximum sustainable throughput. The service is never overwhelmed.

**Partition key design:**

GPS updates are keyed by `driver_id`. All updates for one driver land in the same partition, in order. The matching service always sees a coherent sequence of a driver's locations: it never processes location update #5 before update #4 for the same driver.

**Data retention value:**

Kafka retains driver location history for 7 days. When a passenger disputes their route ("the app says I went 10 miles but it only felt like 3"), Uber can replay the driver's GPS events for that ride from the Kafka topic to reconstruct the exact path.

---

### Example 2: LinkedIn's News Feed Fan-Out

**The problem:** 900 million users. Thousands of influencers with over 1 million followers. When an influencer posts an article, up to 1 million follower feeds must be updated.

**The naive approach:** When user A publishes a post, synchronously write to 1 million follower feeds before returning success. This takes too long. A user with 1M followers cannot wait 10 minutes for their post to publish.

**LinkedIn's Kafka-based approach:**

```
+--------+  PostCreated event   +-------------------+
| User A | -------------------> | "post-created"    |
+--------+                      | Kafka Topic       |
                                 +-------------------+
                                          |
                                 +-------------------+
                                 | Fan-out Service   |
                                 | (consumer group)  |
                                 +-------------------+
                                          |
                              lookup: followers of User A
                                          |
                              for each follower:
                              publish FeedUpdate event
                                          |
                                 +-------------------+
                                 | "feed-updates"    |
                                 | Kafka Topic       |
                                 | (many partitions) |
                                 +-------------------+
                                          |
                            partition key = follower_id
                                          |
                                 +-------------------+
                                 | Feed Storage      |
                                 | Consumers         |
                                 +-------------------+
                                          |
                            write to each follower's
                            materialized feed store
```

**The influencer problem:**

For normal users with 200 followers, fan-out on write is fine. For influencers with 1M followers, publishing 1M `FeedUpdate` events per post creates a massive spike in Kafka throughput. LinkedIn uses a hybrid strategy:

- Regular users (< 10K followers): fan-out on write via Kafka (pre-populate follower feeds)
- Celebrities (> 10K followers): fan-out on read (when follower opens their feed, the app fetches celebrity posts separately and merges them)

Kafka's role: decouple the post creation from the fan-out distribution. User A sees "post published" immediately. The million fan-out writes happen asynchronously in the background over the next few seconds. Users see the post propagate gradually, which is acceptable.

---

### Example 3: Stripe's Payment Event Stream

**The problem:** Process payments globally. Every payment event (initiated, authorized, settled, refunded) must be processed exactly once. A double charge is catastrophic. A missed charge is a revenue loss. Regulatory compliance requires a complete audit trail.

**Event flow with exactly-once semantics:**

```
+----------+  payment.initiated  +------------------+
| Client   | ------------------> | "payments-raw"   |
+----------+  (idempotency_key)  | Kafka Topic      |
                                  | RF=3, ISR=2      |
                                  +------------------+
                                           |
                                  +------------------+
                                  | Risk Assessment  |
                                  | Consumer         |
                                  +------------------+
                                           |
                              check fraud signals,
                              velocity, device fingerprint
                                           |
                                  +------------------+
                                  | "payments-risk"  |
                                  | Kafka Topic      |
                                  +------------------+
                                           |
                                  +------------------+
                                  | Authorization    |
                                  | Consumer         |
                                  +------------------+
                                           |
                              call card network (Visa, MC)
                                           |
                                  +------------------+
                                  | "payments-authed"|
                                  | Kafka Topic      |
                                  +------------------+
                                           |
                                  +------------------+
                                  | Settlement       |
                                  | Consumer         |
                                  +------------------+
                                           |
                              batch settlements at EOD
                              send to card networks
```

**Exactly-once implementation:**

Every message in the payment pipeline carries the original `idempotency_key` provided by the client. Every consumer that writes to an external database uses that key as a unique constraint:

```sql
INSERT INTO payment_events (idempotency_key, event_type, payload, processed_at)
VALUES ('idem-abc-123', 'authorized', '{"amount": 50, "currency": "USD"}', NOW())
ON CONFLICT (idempotency_key, event_type) DO NOTHING;
```

If the consumer processes the same Kafka message twice (due to retry after crash), the second INSERT hits the conflict and is silently skipped. The payment is never double-processed.

**Topic configuration for payments:**

```properties
# Topic level
replication.factor=3
min.insync.replicas=2
retention.ms=2592000000    # 30 days (regulatory audit trail)
cleanup.policy=delete      # retain by time, not compaction

# Producer level
acks=all
enable.idempotence=true
transactional.id=payment-processor-${instance-id}

# Consumer level
isolation.level=read_committed   # only read messages from committed transactions
enable.auto.commit=false
```

`isolation.level=read_committed` is critical: consumers will not see messages from aborted transactions. Without this, a consumer could read a message that the producer later rolled back, processing a payment that was never meant to be committed.

**30-day retention:** Stripe keeps payment events for 30 days in Kafka (and much longer in cold storage). This supports:
- Dispute resolution: replay the exact sequence of events for a disputed payment
- Regulatory compliance: financial regulators require audit trails
- Debugging: reproduce production bugs by replaying event sequences in a test environment

---

## Summary: The Decision Framework

At a staff-level interview, you will be asked to design a system that uses Kafka. The interviewer expects you to make specific choices and defend them. Here is the mental framework:

**Choosing delivery semantics:**

```
What is the consequence of processing a message twice?
    |
    +---> Trivial (analytics, logs, metrics)
    |         --> Use at-most-once for maximum throughput
    |
    +---> Manageable (emails, notifications, API calls)
    |         --> Use at-least-once + idempotent consumer
    |
    +---> Catastrophic (payments, inventory, ledger)
              --> Use at-least-once + idempotent consumer + unique DB constraints
              --> Or use Kafka exactly-once transactions (if all writes stay in Kafka)
```

**Designing topics:**

- One topic per event type, not one topic per service
- Partition key = entity that should have ordered processing (user_id, order_id, driver_id)
- Set `replication.factor=3`, `min.insync.replicas=2` for production data
- Use `cleanup.policy=compact` for topics that represent current state of entities
- Always define a DLQ topic and monitor it

**Consumer design:**

- Always make consequential consumers idempotent
- Set `max.poll.records` based on realistic processing time to avoid rebalance loops
- Use cooperative incremental rebalancing for large consumer groups
- Plan for poison messages: implement retry with backoff + DLQ after N failures

**Event schema design:**

- Design events for consumer needs, not producer convenience
- Keep domain data in events; push consumer-specific enrichment to consumers
- Avoid tight coupling by not including fields that only benefit one consumer
- Fan-out in Kafka, not in consumers

The engineers at Uber, LinkedIn, and Stripe who designed these systems were not smarter than you. They learned these patterns by building systems, watching them fail in production, and iterating. Understanding the failure modes and the patterns that prevent them is what separates staff-level thinking from junior-level thinking.
# Chapter 33: Event-Driven Architectures — Kafka and Streams
## Part C: Event Sourcing, Sagas, Stream Processing, CDC, and Failure Modes

---

## Before You Start: What This Chapter Is About

Parts A and B of Chapter 33 covered Kafka's internals, partitioning, consumer groups, and delivery guarantees. If you have not read those parts yet, read them first. This part builds on top of them.

This part answers a different set of questions. Parts A and B said: "here is how the Kafka plumbing works." Part C says: "here is how you build real systems on top of that plumbing."

At an L6 interview, the questions you will face are not "what is Kafka." They are:

- "You have a bug in a consumer that corrupted your database. How do you recover the correct state?" — You need to know event sourcing and event replay.
- "A user places an order that touches three microservices. What happens if the payment service goes down mid-transaction?" — You need to know the Saga pattern.
- "How do you build a real-time dashboard that shows orders-per-minute, updated every second?" — You need to know stream processing and windowing.
- "Your Elasticsearch search index is always slightly stale compared to your Postgres database. Fix it without changing your application code." — You need to know CDC and Debezium.
- "Your event-driven system is stuck. A single bad message is blocking a Kafka partition and nothing behind it is processing." — You need to know the poison message problem and DLQ design.

This chapter covers all five, in order. Each section starts with a plain analogy, builds to the mechanics, and ends with a real-world company example.

```
+------------------+   +------------------+   +------------------+   +------------------+   +------------------+
|  1. EVENT        |   |  2. SAGA         |   |  3. STREAM       |   |  4. CDC          |   |  5. FAILURE      |
|  SOURCING        |-->|  PATTERN         |-->|  PROCESSING      |-->|  DEBEZIUM        |-->|  MODES           |
|                  |   |                  |   |                  |   |                  |   |                  |
| Store history,   |   | Distributed      |   | Kafka Streams    |   | DB changes as    |   | Poison messages, |
| not current state|   | transactions via |   | and Apache Flink |   | Kafka events     |   | rebalancing, DLQ |
+------------------+   +------------------+   +------------------+   +------------------+   +------------------+
```

---

## Section 1: Event Sourcing — Storing History Instead of State

### The Accounting Ledger Analogy

Imagine you are a bank teller in 1920 — no computers, just paper ledgers.

You have two options for tracking a customer's account. Option A: keep a single card that shows only the current balance. Every time money moves, you erase the old number and write the new one. Balance right now: $500. That's all you know.

Option B: keep a running ledger page. Every transaction gets its own line entry:

```
Date        Description         Debit       Credit      Balance
---------------------------------------------------------------
Jan  1      Opening deposit                 $1,000      $1,000
Jan  3      Rent payment        $200                    $800
Jan  7      Grocery store       $50                     $750
Jan 12      Wire transfer out   $250                    $500
```

Option B is an accounting ledger. It stores every event that ever happened. The current balance ($500) is derived by summing all entries. But you can also answer questions like "what was the balance on January 5?" by summing entries through that date. You get a full audit trail, a time machine, and protection against fraud — all from the same ledger.

**Event sourcing** is Option B applied to software systems. Instead of storing the current state of an entity in a database row, you store every event that ever changed that entity. The current state is always derivable by replaying those events in order. Banks have done this for centuries. Kafka brings it to software at internet scale.

### Traditional State Storage vs. Event Sourcing

With a traditional database, updating a user's email looks like this:

```sql
UPDATE users SET email = 'new@email.com' WHERE id = 123;
```

After this runs, the database row shows the new email. The old email is gone. You have no record of when it changed, who changed it, what it was before, or why. If a bug caused this update to run incorrectly, you have no way to recover the old value. The mutation is permanent and silent.

With event sourcing, the same change looks like this:

```sql
INSERT INTO events (user_id, type, occurred_at, data)
VALUES (
  123,
  'email_changed',
  '2026-06-14 14:32:47',
  '{"old_email": "old@email.com", "new_email": "new@email.com", "changed_by": "user_self"}'
);
```

After this runs, the event is appended to the log. Nothing was overwritten. You now have a full audit trail: what changed, when, who triggered it, and what the previous value was. The current state is derived by reading all events for user 123 and applying them in order.

The visual difference is critical:

```
TRADITIONAL DATABASE (single-row, overwrites):
+------+-------------------+---------------------+
| id   | email             | updated_at          |
+------+-------------------+---------------------+
| 123  | new@email.com     | 2026-06-14 14:32:47 |  <-- old email gone forever
+------+-------------------+---------------------+

EVENT STORE (append-only log, full history):
+----+--------+---------------+---------------------+-------------------------------------+
| id | userId | type          | occurred_at         | data                                |
+----+--------+---------------+---------------------+-------------------------------------+
|  1 |    123 | user_created  | 2025-01-10 09:00:00 | {"email": "old@email.com"}          |
|  2 |    123 | plan_upgraded | 2025-03-22 11:14:00 | {"from": "free", "to": "pro"}       |
|  3 |    123 | email_changed | 2026-06-14 14:32:47 | {"old": "old@email.com",            |
|    |        |               |                     |  "new": "new@email.com"}            |
+----+--------+---------------+---------------------+-------------------------------------+
              ^                                ^
        first event                      latest event
        (beginning of user's history)    (current "head")

Current state = apply events 1, 2, 3 in order
State at 2025-04-01 = apply only events 1 and 2
```

### Five Benefits of Event Sourcing

**1. Complete audit trail.** Every change is recorded with timestamp, actor, and before/after state. For finance, healthcare, and compliance use cases, this is not a nice-to-have — it is legally required. PCI-DSS (payment card industry), HIPAA (healthcare), and GDPR (data privacy) all require audit trails that event sourcing provides naturally.

**2. Time travel.** You can reconstruct the exact state of any entity at any point in history. A support engineer can answer "what was user 123's account state at 14:32:47 on June 14?" by replaying events up to that timestamp. This is invaluable for debugging production incidents.

**3. Event replay.** If a consumer bug corrupts downstream data, you do not have to restore from backup and lose recent data. You fix the bug, then replay the event stream through the fixed consumer. The correct state is rebuilt from the authoritative event log.

```
REPLAY SCENARIO:
+---------------+    events     +------------------+    writes    +----------------+
| Kafka Topic   | ------------> | Consumer v1      | -----------> | Read Model DB  |
| (event store) |               | (BUG: counts     |              | (CORRUPTED)    |
|               |               |  items twice)    |              |                |
+---------------+               +------------------+              +----------------+
        |
        | same events, replayed from offset 0
        v
+------------------+    writes    +----------------+
| Consumer v2      | -----------> | Read Model DB  |
| (BUG FIXED)      |              | (CORRECT)      |
+------------------+              +----------------+
```

**4. Multiple projections from one source.** The same stream of "order" events can feed an order history view for customers, an analytics dashboard for the business team, a fulfillment queue for the warehouse, and a fraud detection model — all simultaneously. Each consumer builds its own read model optimized for its use case.

**5. Temporal queries.** "How many users signed up between January 1 and January 7?" is a simple count of events in a time range. No need for separate analytics pipelines.

### The Challenges of Event Sourcing

Event sourcing is not free. It comes with real operational costs.

**Query complexity.** "What is user 123's current email?" requires reading and replaying every event for user 123. With 10 events, that is trivial. With 10 million events per user (think of a trading account with daily transactions over 20 years), that is slow. The standard fix is to maintain a **materialized view** — a separate read-optimized store (Postgres, Redis, Elasticsearch) that a consumer keeps in sync with the event stream. Reads go to the materialized view. Only the event stream is the authoritative source of truth.

**Schema evolution.** Events are stored forever. An event written in 2021 must still be deserializable in 2031. This means you can never remove a required field from an event schema. You can add new optional fields. You cannot rename or remove existing ones. The industry standard solution is **Apache Avro** schemas stored in a **Schema Registry** — every event carries a schema ID, and the registry enforces backward compatibility before a new schema version is allowed.

**Snapshotting.** If an entity has accumulated 10 million events, replaying from the beginning every time you need its current state is impractical. The fix is **snapshotting**: periodically serialize the current derived state and store it as a snapshot. Future reads start from the latest snapshot and replay only events that occurred after it.

```
WITHOUT SNAPSHOTS (slow):
offset 0 ----[event 1]--[event 2]--...--[event 9,999,999]--[event 10,000,000]--> current state
             ^
             replay starts here (slow)

WITH SNAPSHOTS (fast):
offset 0 ----[event 1]--...--[snapshot at event 5M]--[event 5M+1]--...--[event 10M]--> current state
                              ^
                              replay starts here (fast: only 5M events to replay)
```

**Storage growth.** Events accumulate forever, by design. A system processing 100,000 events per second for five years will accumulate roughly 15 trillion events. Budget storage upfront, use tiered storage (hot SSD for recent events, cold object storage for old events), and use Kafka's tiered storage feature for long-term retention without growing broker disk indefinitely.

### Event Sourcing with Kafka

In practice, a Kafka topic serves as the event store. Each event is published to a topic and retained for years (or forever). Any consumer can start at offset 0 and rebuild state from scratch.

For "current state" use cases, Kafka offers **compacted topics**. In a compacted topic, only the latest message per key is retained on disk. Older messages with the same key are deleted during compaction. A consumer starting from offset 0 on a compacted topic will read the current state of every key, which is effectively a full bootstrap of the current world state.

The architectural pattern that pairs with event sourcing is **CQRS (Command Query Responsibility Segregation)**. The idea is simple: separate the write path from the read path. Writes go to the event log (Kafka, append-only). Reads go to a purpose-built query store (Postgres for relational queries, Elasticsearch for full-text search, Redis for low-latency key lookups). Multiple read models can coexist, each optimized for a different query pattern.

```
CQRS + EVENT SOURCING ARCHITECTURE:

   User Action
       |
       v
+-------------+     publishes      +------------------+
|  Command    | -----------------> |   Kafka Topic    |
|  Handler    |     (append-only)  |  (Event Store)   |
+-------------+                    +--------+---------+
                                            |
                              +-------------+-------------+
                              |             |             |
                              v             v             v
                    +---------+--+  +-------+---+  +-----+------+
                    | Consumer 1 |  | Consumer 2|  | Consumer 3 |
                    | (Postgres) |  | (Elastic) |  | (Redis)    |
                    +---------+--+  +-------+---+  +-----+------+
                              |             |             |
                              v             v             v
                    +----------+  +----------+  +----------+
                    | Order    |  | Search   |  | Session  |
                    | History  |  | Index    |  | Cache    |
                    | View     |  |          |  |          |
                    +----------+  +----------+  +----------+
                              ^             ^             ^
                              |             |             |
                              +------+------+------+------+
                                     |
                                  Reads
                                  (fast, query-optimized)
```

### Real Example: bol.com Order Management with Event Sourcing

bol.com is the largest e-commerce platform in the Netherlands and Belgium, serving roughly 50 million users. They migrated their order management system to event sourcing using the Axon Framework (a Java CQRS/event sourcing library).

The order aggregate — the representation of a single customer order — is built entirely from events:

```
Order lifecycle events:
[OrderCreated] -> [ItemAdded] -> [ItemAdded] -> [PaymentReceived] -> [OrderShipped] -> [OrderDelivered]

Current order state = apply all six events in sequence
Order state at any past moment = apply events up to that point in time
```

The business benefits were concrete: Dutch consumer protection law requires a complete audit trail for all commercial transactions. Event sourcing provided this for free — every change to an order was already captured. Customer support gained the ability to reconstruct exactly what a customer saw at the time they placed an order, which proved invaluable for resolving disputes.

The operational challenge they hit was projection rebuild time. When a bug in a read model required a full rebuild from the event log, it took four hours to replay all historical events. Their fix was snapshotting every 1,000 events per order aggregate, reducing rebuild time to under 20 minutes.

---

## Section 2: The Saga Pattern — Distributed Transactions via Events

### Why Distributed Transactions Are Hard

Picture a travel booking website. You book a flight, a hotel, and a rental car. All three must succeed together or not at all — you do not want to be charged for a hotel in Paris if the flight to Paris sold out. In a single database, this is trivial: wrap everything in one ACID transaction. If anything fails, the database rolls everything back automatically.

Now picture the same scenario in microservices. The flight booking lives in an Airline Service with its own database. The hotel booking lives in a Hotel Service with its own database. The car rental lives in a Car Service with its own database. There is no single database to wrap a transaction around. Each service only controls its own data.

The naive solution is **Two-Phase Commit (2PC)**. Phase 1: ask all participants to "prepare" (lock resources, check they can commit). Phase 2: if everyone said yes, tell everyone to commit. If anyone said no, tell everyone to rollback.

2PC sounds good in theory. In practice it has three problems that make it unusable at scale:

1. The coordinator (the service running 2PC) is a single point of failure. If it dies between Phase 1 and Phase 2, all participants are stuck holding locks forever.
2. It is a blocking protocol — all participants lock their resources and wait. Under high load, this causes cascading timeouts.
3. Databases that span geographic regions introduce seconds of latency per transaction, which is unacceptable.

The industry's practical answer is the **Saga pattern**.

### The Saga Approach: Local Transactions Plus Compensations

A **Saga** is a sequence of local transactions. Each local transaction updates one service's database and publishes an event (or sends a command) that triggers the next local transaction. If a step fails, the saga executes **compensating transactions** in reverse order to undo the effects of the steps that already completed.

A compensating transaction is the business-level undo operation for a step. "Charge credit card" has the compensation "issue refund." "Reserve inventory" has the compensation "release reservation." Every step in a saga must be designed alongside its compensation — you cannot add compensations as an afterthought.

There are two styles of saga coordination: **choreography** and **orchestration**.

### Choreography Saga: Services React to Events

In choreography, there is no central coordinator. Each service publishes events when it completes its step, and other services subscribe to those events and react.

Here is a complete order placement saga using choreography:

```
HAPPY PATH (everything succeeds):

OrderService           InventoryService         PaymentService          FulfillmentService
     |                        |                        |                        |
     | publishes               |                        |                        |
     | "OrderCreated"          |                        |                        |
     +------------------------>|                        |                        |
     |                        | reserves stock          |                        |
     |                        | publishes               |                        |
     |                        | "InventoryReserved"     |                        |
     |                        +------------------------>|                        |
     |                        |                        | charges card            |
     |                        |                        | publishes               |
     |                        |                        | "PaymentProcessed"      |
     |                        |                        +------------------------>|
     |                        |                        |                        | creates shipment
     |                        |                        |                        | publishes
     |                        |                        |                        | "ShipmentCreated"
     |<----------------------------------------------------------------------- |
     | updates order                                                             |
     | to CONFIRMED                                                              |

FAILURE PATH (payment fails, compensations run):

OrderService           InventoryService         PaymentService
     |                        |                        |
     | publishes               |                        |
     | "OrderCreated"          |                        |
     +------------------------>|                        |
     |                        | reserves stock          |
     |                        | publishes               |
     |                        | "InventoryReserved"     |
     |                        +------------------------>|
     |                        |                        | card declined
     |                        |                        | publishes
     |                        |                        | "PaymentFailed"
     |                        |<-----------------------+
     |                        | releases reservation    |
     |                        | publishes               |
     |                        | "InventoryReleased"     |
     |<-----------------------+                        |
     | updates order           |                        |
     | to CANCELLED            |
```

**Choreography pros:** simple to implement, no central coordinator, each service is autonomous and independently deployable. If the Inventory Service team wants to add a new reaction to "OrderCreated," they do it without touching any other service.

**Choreography cons:** the overall business flow is fragmented across N services. There is no single place to see the current state of a saga. Debugging a failure requires tracing events across multiple services and their individual logs. As the number of saga steps grows, the implicit dependencies between services become hard to understand and maintain.

### Orchestration Saga: A Central Coordinator

In orchestration, a dedicated **Order Orchestrator** service owns the business logic of the entire saga. It explicitly tells each service what to do, collects the results, and handles failures.

```
ORCHESTRATION SAGA — COORDINATOR IN CENTER:

                        +---------------------+
                        |  Order Orchestrator |
                        |                     |
                        | saga state:         |
                        |  step: PAYMENT      |
                        |  order_id: 456      |
                        |  status: IN_PROGRESS|
                        +----------+----------+
                                   |
            +----------------------+----------------------+
            |                      |                      |
            v                      v                      v
  +---------+--------+   +---------+--------+   +---------+--------+
  | Inventory Service|   | Payment Service  |   |Fulfillment Service|
  |                  |   |                  |   |                   |
  | receives command:|   | receives command:|   | receives command: |
  | "reserve 2x      |   | "charge $49.99   |   | "ship order 456  |
  |  SKU-XYZ-789"    |   |  to card ending  |   |  to 123 Main St" |
  |                  |   |  4242"           |   |                   |
  | sends event:     |   | sends event:     |   | sends event:      |
  | "reserved" or    |   | "processed" or   |   | "created" or      |
  | "out_of_stock"   |   | "declined"       |   | "address_invalid" |
  +------------------+   +------------------+   +-------------------+
            |                      |                      |
            +----------------------+----------------------+
                                   |
                                   v
                        +----------+----------+
                        |  Order Orchestrator |
                        | (receives events,   |
                        |  decides next step  |
                        |  or runs            |
                        |  compensations)     |
                        +---------------------+
```

The orchestrator persists its saga state to a database after each step. If the orchestrator crashes mid-saga, it restarts and picks up exactly where it left off by reading its persisted state. This makes the saga **durable** — a crash does not leave the system in an unrecoverable half-done state.

**Orchestration pros:** the complete business flow is readable in one place (the orchestrator's code). Saga state is explicit and queryable. Debugging is straightforward — check the orchestrator's state table for any saga. Adding a new step means modifying the orchestrator, not multiple independent services.

**Orchestration cons:** the orchestrator is a dependency that all services must interact with. It can become a bottleneck under high load. There is a philosophical tension: microservices are supposed to be autonomous, but an orchestrator implies a central authority that knows what every service is doing.

### When to Use Sagas

Use sagas when:
- A business operation spans multiple microservices, each with its own database
- The operation has rollback requirements (payments, inventory, reservations)
- The steps are long-lived (minutes or hours, not milliseconds)

Do not use sagas when:
- The entire operation fits in a single database transaction — just use ACID
- The operation is read-only — no transaction needed
- The operation has no meaningful rollback (sending an email cannot be "unsent" — design around this instead)

### Real Example: Amazon Order Processing

Amazon's order processing is a canonical example of orchestrated sagas at scale. A customer clicking "Place Order" triggers a multi-step distributed transaction:

```
Amazon Order Saga Steps (simplified):
Step 1: Reserve inventory in fulfillment center closest to customer
Step 2: Authorize payment method (credit card hold, not full charge)
Step 3: Confirm inventory can ship by promised date
Step 4: Complete payment capture
Step 5: Hand off to fulfillment system for picking and packing

Compensations:
- Step 4 fails: void the payment authorization (Step 2 compensation)
- Step 3 fails: release inventory reservation (Step 1 compensation)
- Step 5 fails after Step 4: issue refund (Step 4 compensation), release inventory (Step 1 compensation)
```

Amazon tracks each order through a state machine. The state machine is the orchestrator — it knows exactly which step the order is on, how long it has been in that state, and what to do if a timeout occurs. Engineers can query the state machine for any order ID and see its full progression, which is essential for customer support and fraud investigation.

---

## Section 3: Stream Processing — Kafka Streams and Apache Flink

### What Is Stream Processing?

Think about how you handle email. Approach A: ignore your inbox all week, then spend Saturday morning going through 300 emails. This is **batch processing** — accumulate data, process it in bulk on a schedule.

Approach B: read each email as it arrives throughout the day, responding or acting immediately. This is **stream processing** — process each piece of data the moment it appears.

**Batch processing** is appropriate for: daily reports, end-of-day reconciliation, large data transformation jobs that do not need to be real-time. ETL (Extract-Transform-Load) jobs that run at 2am are batch jobs.

**Stream processing** is appropriate for: fraud detection (you need to act before the transaction clears), live dashboards (you want orders-per-minute updated every second), real-time recommendations (you want to react to what the user just clicked), and alerting (you want to know within seconds when error rates spike).

### Kafka Streams: Stream Processing as a Library

**Kafka Streams** is a Java library that you include in your application like any other dependency. It is not a separate cluster or service you deploy. Your application reads from Kafka topics, processes events in the Kafka Streams library, and writes results back to Kafka topics. The processing happens inside your application's JVM process.

This simplicity is its biggest advantage. You do not need to provision or maintain a Flink cluster or a Spark cluster. You just add a library and write code.

Here is a complete real example: counting orders per product ID in real time.

```java
// Build the processing topology
StreamsBuilder builder = new StreamsBuilder();

// Read the "orders" Kafka topic
KStream<String, Order> orders = builder.stream("orders");

// Group by product ID, then count — this is stateful
KTable<String, Long> orderCountsPerProduct = orders
    .groupBy((key, order) -> order.getProductId())
    .count(Materialized.as("order-count-store")); // state stored in RocksDB locally

// Write results back to a Kafka topic
orderCountsPerProduct
    .toStream()
    .to("order-counts-by-product");

// Start the application
KafkaStreams streams = new KafkaStreams(builder.build(), config);
streams.start();
```

Every time a new order event arrives on the "orders" topic, this code updates the running count for that product ID and writes the new count to the "order-counts-by-product" topic. Any downstream consumer (a dashboard, an alerting system, a recommendation engine) reads from that output topic and always sees the latest count.

For stateful operations like counting and joining, Kafka Streams uses **RocksDB** — an embedded key-value database — stored on local disk. The state is also backed up to a Kafka **changelog topic**, which means if the application crashes, it can restore its state by replaying the changelog topic rather than reprocessing the entire input from the beginning.

### Windowing: Time-Bounded Aggregations

"Count all orders since the beginning of time" is rarely what you want. What you usually want is "count orders in the last 5 minutes" or "count orders per hour." These time-bounded aggregations are called **windows**.

There are three window types, and knowing when to use each is what Staff engineers are tested on.

**Tumbling windows** divide time into fixed, non-overlapping buckets. Every event falls into exactly one bucket. The buckets tile time without gaps or overlaps.

**Sliding windows** move forward continuously. For every new event that arrives, a sliding window looks back a fixed duration and aggregates all events in that lookback period. Events can fall into multiple windows.

**Session windows** group events based on inactivity gaps rather than fixed time. A new session starts when an event arrives after a period of silence. All events within an active session are grouped together.

```
WINDOW TYPES ILLUSTRATED (events marked with x on a timeline):

Events:  x    x  x      x        x   x    x
Time:    0----1--2------4--------7---8----10

TUMBLING WINDOWS (size = 5 minutes):
         +-----Window 1-----++----Window 2-----++----Window 3----+
         | 0:00 to 0:05     || 0:05 to 0:10    || 0:10 to 0:15  |
         | events: x, x, x  || events: x, x   || events: x, x   |
         +------------------++----------------++----------------+

SLIDING WINDOWS (size = 3 minutes, every event gets its own window):
         At time 2: look back 3min -> window [0:00-0:02], events: x, x, x
         At time 4: look back 3min -> window [0:01-0:04], events: x, x, x
         At time 8: look back 3min -> window [0:05-0:08], events: x, x, x

SESSION WINDOWS (inactivity gap = 2 minutes):
         +--Session 1--++-----gap------++--Session 2--++--Session 3-+
         | x  x  x     ||              || x           || x   x      |
         | 0:00-0:02   ||  0:02-0:04  || 0:04-0:04   || 0:07-0:10  |
         +-------------++-------------++-------------++------------+
```

**When to use each:**
- Tumbling windows: hourly/daily reporting periods, rate calculations for fixed intervals ("transactions per hour")
- Sliding windows: real-time dashboards ("orders in the last 5 minutes" displayed live)
- Session windows: user behavior analysis, clickstream grouping, anything where "a session" is defined by user activity with gaps

### Joining Streams

Kafka Streams (and Flink) support three types of joins, each solving a different problem.

**Stream-stream join** correlates events from two different topics that are related by time. You define a time window within which both events must arrive to be considered a match.

Example: join "ad-click" events with "purchase" events within a 30-minute window. If a user clicks an ad and makes a purchase within 30 minutes, those two events are joined into a "click-converted-to-purchase" record. This is how advertising attribution works at Google, Meta, and every ad-tech company.

**Stream-table join** enriches streaming events with reference data. The "table" side is a KTable — a compacted Kafka topic that represents the current state of some reference dataset. When a new event arrives on the stream side, it is joined with the current value of the matching key in the table.

Example: join an "orders" stream with a "product-catalog" KTable. Each order event contains a product ID. The join adds the product name, category, and price to the order event. The fulfillment service receives enriched order events without needing its own copy of the product catalog.

**Table-table join** joins two materialized state views. Both sides are KTables (compacted topics). When either side is updated, the join re-evaluates and produces a new output.

Example: join "user-profile" KTable with "user-preferences" KTable to produce a merged "user-full-context" KTable used by recommendation engines.

### Apache Flink: Industrial-Strength Stream Processing

Kafka Streams is excellent for application-embedded stream processing. Apache Flink is the choice when you need more power.

| Feature | Kafka Streams | Apache Flink |
|---|---|---|
| Deployment | Library inside your app | Separate cluster (JobManager + TaskManagers) |
| Languages | Java/Kotlin only | Java, Python, Scala, SQL |
| State size | Limited by local disk | Distributed state, terabytes supported |
| Late event handling | Limited | Full event-time processing with watermarks |
| Exactly-once | Yes (within Kafka) | Yes (end-to-end, including external sinks) |
| Operational complexity | Low | High |
| Best for | Simple transformations, small-medium state | Complex CEP, large state, multi-source joins |

Flink's defining technical advantage over Kafka Streams is **event-time processing**. Kafka Streams processes events based on when they arrive in Kafka (ingestion time). Flink can process events based on the timestamp embedded in the event itself — when they actually occurred in the real world.

This matters because real-world events are not always delivered in order. A mobile app event from 14:30 might arrive in Kafka at 14:35 because the user's phone had spotty network coverage. If you are computing a 5-minute window from 14:25 to 14:30, that event belongs inside the window even though it arrived late.

### Watermarks: Handling Late-Arriving Events

Flink uses **watermarks** to track event-time progress. A watermark is a signal that says: "I am confident that all events with timestamp earlier than T have now arrived." It is the system's best estimate of how far event time has advanced.

```
EVENT-TIME WATERMARKS:

Real world timeline:  14:25----14:26----14:27----14:28----14:29----14:30
Events arriving at Kafka (with 2-minute delay):
                      14:23----14:24----14:25----14:26----14:27----14:28
                      (event timestamps are 2 minutes behind arrival time)

Watermark strategy: "allow up to 2 minutes of lateness"
Current watermark at arrival time 14:28 = 14:28 - 2min = 14:26

Window [14:25 - 14:30]:
  - Still open until watermark reaches 14:30
  - Watermark reaches 14:30 when arrival time reaches 14:32
  - At 14:32, Flink closes the window and emits the result

Event arriving at 14:33 with timestamp 14:26 (7-minute delay, beyond tolerance):
  - Window [14:25-14:30] already closed
  - This event is LATE -> sent to side output for separate handling or dropped
```

When to use Flink over Kafka Streams:
- Complex Event Processing (CEP): detect patterns like "3 failed logins within 5 minutes followed by a password reset attempt"
- Large state: joining streams where the state table holds terabytes of data
- Multi-source: joining more than two streams simultaneously
- ML feature pipelines: real-time feature computation for model serving
- When you need exactly-once guarantees including external databases as sinks

**Real example:** Alibaba uses Apache Flink as the backbone of its real-time data infrastructure. During Singles' Day (November 11), Alibaba's peak sales event, Flink processes 4.72 trillion events over 24 hours — roughly 54 million events per second at peak. The fraud detection system that runs on top of Flink must decide whether a transaction is fraudulent in under 100 milliseconds. This is only possible with event-time stream processing and large distributed state.

---

## Section 4: CDC — Change Data Capture

### What Is CDC?

**CDC (Change Data Capture)** is the practice of capturing every change to a database as an event stream. Instead of writing to Kafka yourself from application code, you let the database's internal change log do the work.

Every production-grade relational database maintains a **write-ahead log (WAL)**. In PostgreSQL it is literally called the WAL. In MySQL it is called the binary log (binlog). The database writes every change to this log before applying it to the data files — that is how crash recovery works. If the database crashes mid-write, it replays the WAL on restart to get back to a consistent state.

CDC works by reading this log as a stream. A CDC tool like **Debezium** connects to the database's replication protocol, reads every INSERT, UPDATE, and DELETE as it is written to the WAL, and publishes each change as a message to a Kafka topic.

```
CDC ARCHITECTURE WITH DEBEZIUM:

+------------------+     WAL/binlog     +------------------+     Kafka      +---------------------+
|  PostgreSQL      | -----------------> |  Debezium        | ------------>  |  Kafka Topic        |
|  (source DB)     |   (replication     |  Connector       |  (publishes    | "postgres.public    |
|                  |    protocol)       |  (reads log)     |   messages)    |  .users"            |
|  INSERT user 123 |                    |                  |                |                     |
|  UPDATE email    |                    |                  |                | msg: {              |
|  DELETE user 99  |                    |                  |                |   op: "u",          |
+------------------+                    +------------------+                |   before: {email:  |
                                                                            |     "old@..."},    |
                                                                            |   after: {email:   |
                                                                            |     "new@..."}     |
                                                                            | }                   |
                                                                            +----------+----------+
                                                                                       |
                                        +----------------------+------------------------+----------+
                                        |                      |                        |          |
                                        v                      v                        v          v
                              +---------+------+    +----------+-----+    +-------------+--+  +---+------+
                              | Cache          |    | Search         |    | Data Warehouse |  | Analytics|
                              | Invalidation   |    | Index Sync     |    | Sync           |  | Pipeline |
                              | (Redis DEL)    |    | (Elasticsearch)|    | (BigQuery)     |  | (Flink)  |
                              +----------------+    +----------------+    +----------------+  +----------+
```

Each Kafka message from Debezium contains the operation type ("c" for create, "u" for update, "d" for delete), the full "before" state (for updates and deletes), and the full "after" state (for creates and updates). Consumers get everything they need to sync their own stores.

### Why CDC Instead of Dual-Write?

The naive approach to keeping Kafka in sync with your database is **dual-write**: when your application writes to the database, it also writes to Kafka in the same code path.

```
DUAL-WRITE PROBLEM:

Application code:
  Step 1: db.execute("INSERT INTO users ...")   <- succeeds
  Step 2: kafka.publish("user.created", ...)    <- FAILS (network hiccup)

Result:
  - Database has the new user
  - Kafka never got the event
  - Search index never updated, cache never invalidated, analytics never received the event
  - SILENT DATA INCONSISTENCY

Alternative failure mode:
  Step 1: kafka.publish("user.created", ...)    <- succeeds
  Step 2: db.execute("INSERT INTO users ...")   <- FAILS

Result:
  - Kafka has an event for a user that does not exist in the database
  - Downstream consumers are processing a ghost record
```

Dual-write creates a consistency gap that grows silently. There is no atomic two-phase operation that writes to both a database and a Kafka topic simultaneously. One will always succeed before the other, and if the second fails, you are inconsistent.

CDC solves this with a simple rule: **write only to the database.** The database write is the single source of truth. Debezium reads the WAL and publishes to Kafka only after the database transaction has committed. If Kafka is unavailable, Debezium buffers or pauses — but it never loses events, because the WAL is still there. When Kafka comes back, Debezium reads the WAL from where it left off and catches up.

```
CDC CONSISTENCY GUARANTEE:

Application code:
  Step 1: db.execute("INSERT INTO users ...")   <- commits to WAL

Kafka topic:
  (updated by Debezium reading WAL, asynchronously but reliably)

If Kafka is down:
  - DB write still succeeds
  - WAL retains the change
  - Debezium catches up when Kafka recovers
  - NO DATA LOSS, slight delay

If DB write fails:
  - WAL never receives the change
  - Debezium never sees it
  - Kafka never gets an event
  - CORRECTLY CONSISTENT (nothing happened, so nothing published)
```

### Five CDC Use Cases

**1. Cache invalidation.** Database row changes → Debezium → Kafka → cache invalidation consumer → Redis DEL or Redis SET with new value. The cache is always consistent with the database, without the application needing to remember to invalidate on every code path that writes to the database.

**2. Search index synchronization.** PostgreSQL product catalog → Debezium → Kafka → Elasticsearch consumer → search index updated. Search results reflect database changes within seconds. No application code changes needed — Debezium just watches the table.

**3. Data warehouse synchronization.** OLTP database → Debezium → Kafka → BigQuery or Snowflake consumer → analytics warehouse updated incrementally in near-real-time. Eliminates the nightly batch ETL job and its 12-hour data staleness.

**4. Event-driven microservices.** User Service writes to its own database. Debezium publishes every user creation, update, or deletion to a Kafka topic. The Email Service, the Recommendation Service, and the Analytics Service all react to those events without the User Service team needing to write any Kafka code.

**5. Compliance audit logging.** Capture every change to regulated data (PII, financial records, medical records) at the database level. The application cannot accidentally skip the audit trail because it bypasses Debezium — every WAL change is captured regardless of which application code path triggered it.

### The Transactional Outbox Pattern

CDC requires you to set up Debezium and give it access to your database's replication protocol. For some teams, this is operationally expensive. The **transactional outbox pattern** offers a simpler alternative when you do not need to capture all database changes — just specific business events.

The pattern uses the database's own ACID guarantees to atomically record both the business write and the intent to publish a Kafka event:

```
OUTBOX PATTERN FLOW:

Step 1: Business logic runs ONE database transaction:
  BEGIN TRANSACTION
    INSERT INTO orders (id, user_id, total) VALUES (456, 123, 49.99)
    INSERT INTO outbox  (event_type, payload, published) VALUES ('OrderCreated', '...', false)
  COMMIT

  (Both succeed or both fail. No inconsistency possible.)

Step 2: Outbox poller runs on a background thread (or Debezium watches the outbox table):
  SELECT * FROM outbox WHERE published = false ORDER BY created_at LIMIT 100
  -> Publishes each row to Kafka
  -> Marks as published = true

+----------+     transaction      +------------------+
|  Orders  | <------------------- | Application Code |
|  Table   |                      +------------------+
+----------+
                                  +------------------+
+----------+     transaction      | Application Code |
|  Outbox  | <------------------- +------------------+
|  Table   |
+----------+
    |
    | polled by outbox poller (separate thread or Debezium watching outbox table)
    v
+---------------+     publishes     +-------------------+
| Outbox Poller | ----------------> | Kafka Topic       |
+---------------+                   +-------------------+
```

The outbox pattern is simpler than full CDC when you only need to publish specific business events, not all database changes. Many teams start with the outbox pattern and graduate to CDC when they need to capture changes they did not explicitly instrument.

### Real Example: LinkedIn's Databus

Before Debezium existed, LinkedIn built their own CDC system called **Databus**. LinkedIn's core data lived in an Oracle database. Downstream systems — the member search index, the connection graph, the feed ranking system — all needed to stay in sync with that Oracle data.

The team built Databus to read Oracle's change log and stream changes to consuming services. The member search index could be rebuilt by consuming the full Databus stream from the beginning. Cache invalidations were triggered by Databus events rather than by application code, eliminating the inconsistency bugs that had plagued the dual-write approach.

Databus eventually influenced the design of open-source CDC tools, including Debezium, which is now the industry standard. LinkedIn itself migrated from Databus to Debezium-on-Kafka over time as Kafka's ecosystem matured.

---

## Section 5: Failure Modes in Event-Driven Systems

### Partial Failure: The "50% Done" Problem

A clean failure is a failure where nothing happened. The request failed, the database was not written, the user sees an error, they try again.

A **partial failure** is worse: something happened, but not everything. The system is in an inconsistent state that no code path was designed to handle. Partial failures are the hardest bugs in distributed systems.

In an event-driven saga, partial failure looks like this:

```
PARTIAL FAILURE SCENARIO:

Order Saga Steps:
  Step 1 (reserve inventory): SUCCESS  -> inventory reserved
  Step 2 (charge payment):    SUCCESS  -> $49.99 charged to card
  Step 3 (create shipment):   FAILURE  -> fulfillment service is down

Current system state:
  - Inventory: reserved (customer can't buy this item, but it's not going out either)
  - Payment: charged (customer was billed for something they won't receive)
  - Shipment: does not exist

This is WORSE than if all three steps had failed cleanly.
The customer is charged. The order will never ship. The inventory is stuck.
```

The only recovery path is executing compensation transactions in reverse order. Void the payment charge. Release the inventory reservation. Update the order to FAILED with a reason.

The critical lesson: **design every saga step together with its compensation before you write any code.** The compensation is not an afterthought. It is as important as the forward step. Teams that skip this design work during initial implementation discover the omission only when a production incident triggers a partial failure — the worst possible time to learn.

### Consumer Group Rebalancing During Deployment

**Rebalancing** is the process Kafka uses to reassign partition ownership when the consumer group membership changes. A consumer joins: rebalance. A consumer leaves: rebalance. A consumer crashes: rebalance.

During a rebalance, by default, all consumers in the group pause processing. Partitions are unassigned from their old consumers and reassigned to their new consumers. This is called **stop-the-world rebalancing**.

During a rolling deployment of 10 consumer instances, here is what happens:

```
ROLLING DEPLOYMENT REBALANCE IMPACT:

Instance restarts (10 total, deployed one at a time):
  t=0:00  Instance-01 restarts  ->  REBALANCE triggered, all 10 instances pause
  t=0:20  Rebalance complete    ->  all instances resume processing
  t=0:30  Instance-02 restarts  ->  REBALANCE triggered again, all 10 instances pause
  t=0:50  Rebalance complete    ->  all instances resume
  ...
  t=4:30  Instance-10 restarts  ->  final rebalance

Total time spent paused: 10 rebalances x 20 seconds = ~200 seconds of zero throughput
Consumer lag grows during every pause
If lag grows too large, SLAs are missed
```

The fix is **cooperative incremental rebalancing**, available since Kafka 2.4. With cooperative rebalancing, only the partitions that need to move are reassigned. The consumers that are not affected by the change continue processing during the rebalance. This reduces rebalance pause times from tens of seconds to milliseconds for large consumer groups.

Configure it with: `partition.assignment.strategy = CooperativeStickyAssignor`

### The Poison Message Loop

A **poison message** is a message that causes the consumer to crash or throw an unhandled exception every time it tries to process that message. Because Kafka does not advance the consumer offset until the message is successfully processed, the consumer retries the same message infinitely.

```
POISON MESSAGE BLOCKING A PARTITION:

Partition 7:
  offset 100: [normal message]  <- processed successfully
  offset 101: [normal message]  <- processed successfully
  offset 102: [POISON MESSAGE]  <- consumer crashes
                                    consumer restarts
                                    consumer crashes again
                                    consumer restarts
                                    (infinite retry loop)
  offset 103: [normal message]  <- STUCK (never processed, blocked by 102)
  offset 104: [normal message]  <- STUCK
  offset 105: [normal message]  <- STUCK
  ...

All messages behind offset 102 will never be processed
until offset 102 is handled or skipped.
Consumer lag for partition 7 grows without bound.
```

The fix is a **Dead Letter Queue (DLQ)** combined with a retry limit:

```
POISON MESSAGE HANDLING WITH DLQ:

Consumer processes message:
  Attempt 1: FAIL
  Attempt 2: FAIL
  Attempt 3: FAIL
  Retry limit (3) reached:
    -> Publish message to "orders-dlq" Kafka topic
    -> Commit offset for the poison message (advance past it)
    -> Continue processing offset 103, 104, 105...

"orders-dlq" topic:
  -> Alert fires: on-call engineer paged when DLQ grows
  -> Engineer inspects the poison message: was it a bug in consumer? malformed event?
  -> Fix: if consumer bug, replay DLQ through fixed consumer
  -> Fix: if malformed event, discard or manually correct
```

The DLQ does not solve the problem — it sidesteps it safely while alerting the right people. The partition continues making progress. The poison message is quarantined for inspection. The on-call engineer investigates and decides what to do with it.

### Schema Evolution Breaking Consumers

Event-driven systems often have producers and consumers deployed independently. A producer team ships a schema change. Some consumer instances are already running the new code. Some are still running the old code.

The most dangerous schema change is adding a **required field** without a default value:

```
SCHEMA BREAKING CHANGE SCENARIO:

OrderCreated event schema v1 (existing):
  { orderId: string, userId: string, total: float }

OrderCreated event schema v2 (NEW — producer team shipped today):
  { orderId: string, userId: string, total: float, currencyCode: string REQUIRED }

Consumer instances still running v1 code:
  - Receive new event with currencyCode field
  - Old consumer does not know about currencyCode
  - With strict deserialization: FAILS -> message goes to DLQ
  - DLQ fills up with every new order event
  - On-call paged, all consumer instances need emergency rollout

CORRECT approach:
  Schema v2 adds currencyCode as OPTIONAL with default "USD"
  Old consumers: ignore the unknown field (backward compatible)
  New consumers: read currencyCode field
  No consumers fail during rolling deployment
```

**Schema Registry** enforces this at publish time. When a producer tries to register a new schema version, the registry checks it against the previous version. If the change is not backward compatible (removing a field, changing a field's type, adding a required field), the registry rejects the schema registration. The producer cannot publish with the new schema until the compatibility issue is resolved.

The three compatibility modes in Schema Registry:

| Mode | What is allowed | When to use |
|---|---|---|
| BACKWARD | New schema can read old data | New consumers, old producers still running |
| FORWARD | Old schema can read new data | New producers, old consumers still running |
| FULL | Both directions | Most conservative, recommended default |

For Staff-level interviews, the full picture of event-driven system failure modes forms a pattern: each failure mode has a root cause, a detection mechanism, and a mitigation. Partial failures need compensation logic designed upfront. Rebalancing pauses need cooperative rebalancing configured. Poison messages need DLQs and retry limits. Schema breaks need Schema Registry enforcing compatibility. None of these mitigations are complex — but forgetting any one of them in a production system will eventually cause an incident.

---

## Summary

```
+---------------------+--------------------------------------+----------------------------+
| Concept             | Core Idea                            | Key Tool / Pattern         |
+---------------------+--------------------------------------+----------------------------+
| Event Sourcing      | Store every event, derive state      | Kafka + compacted topics   |
|                     | instead of overwriting it            | + CQRS read models         |
+---------------------+--------------------------------------+----------------------------+
| Saga Pattern        | Split distributed transactions into  | Choreography (events) or   |
|                     | local steps + compensations          | Orchestration (coordinator)|
+---------------------+--------------------------------------+----------------------------+
| Stream Processing   | Process events in real time using    | Kafka Streams (embedded)   |
|                     | windowed aggregations and joins       | or Apache Flink (cluster)  |
+---------------------+--------------------------------------+----------------------------+
| CDC                 | Capture DB changes as a Kafka stream | Debezium + WAL/binlog      |
|                     | without dual-write risk              | Outbox pattern for simpler |
+---------------------+--------------------------------------+----------------------------+
| Failure Modes       | Partial failure, poison messages,    | Compensations, DLQ,        |
|                     | rebalancing pauses, schema breaks    | cooperative rebalancing,   |
|                     |                                      | Schema Registry            |
+---------------------+--------------------------------------+----------------------------+
```

The thread connecting all five sections is **the event log as the source of truth**. Event sourcing stores history as a log. Sagas coordinate across services by publishing and consuming log events. Stream processing reads the log and derives real-time aggregations. CDC turns the database's internal log into a Kafka stream. Every failure mode in this chapter ultimately comes down to what happens when something in the log pipeline breaks and how you recover.

At an L6 interview, you are expected to know not just what these patterns are, but why they exist — what problem they solve that simpler approaches cannot, what tradeoffs they introduce, and how they fail. That is the level of understanding this chapter was designed to build.

---

## Quick Reference: Interview Decision Trees

### Choosing Between Event Sourcing and Traditional State Storage

```
Does the system need a complete audit trail of every change?
  YES -> lean toward event sourcing
  NO  -> consider whether it simplifies or complicates your design first

Does the system need to replay history to rebuild state after a bug?
  YES -> event sourcing is a strong fit
  NO  -> traditional state storage is simpler

Are there multiple consumers that need different views of the same data?
  YES -> event sourcing + CQRS (one event log, many read models)
  NO  -> a single well-modeled relational schema may be enough
```

### Choosing Between Choreography and Orchestration Sagas

```
Is the saga 2-3 steps with a small team owning all services?
  YES -> choreography is simpler, lower overhead

Is the saga 4+ steps, or owned by multiple independent teams?
  YES -> orchestration gives you observability and a single place to debug

Do you need to query "what is the current state of saga 456?"?
  YES -> orchestration (orchestrator persists saga state)
  NO  -> choreography is acceptable
```

### Choosing Between Kafka Streams and Apache Flink

```
Are you processing in Java/Kotlin with no separate cluster budget?
  YES -> Kafka Streams (library, no cluster needed)

Do you need event-time processing for late-arriving events?
  YES -> Flink (Kafka Streams has limited event-time support)

Is your state larger than a few hundred GB?
  YES -> Flink (distributed state backend, not bounded by local disk)

Do you need complex pattern matching across event sequences?
  YES -> Flink CEP library

Everything else with simple transformations, counting, filtering?
  -> Kafka Streams is sufficient and much simpler to operate
```

### Choosing Between CDC and the Outbox Pattern

```
Do you need to capture ALL changes to a table, not just specific events?
  YES -> CDC with Debezium (watches the full WAL)

Do you want to avoid giving Debezium database replication access?
  YES -> Outbox pattern (DB transaction + poller, no WAL access needed)

Is consistency between the DB write and the Kafka event critical?
  BOTH -> solve this equally well. CDC is atomically consistent via WAL.
          Outbox is atomically consistent via DB transaction.

Are you starting from scratch with a new service?
  -> Outbox pattern is simpler to start with. Migrate to CDC if you need full WAL coverage later.
```
# Chapter 33: Event-Driven Architectures — Kafka and Streams (Part D)

## Capacity, Multi-Region, Security, Testing, and Operating Kafka at Scale

---

## Before You Start: What This Section Is About

Parts A, B, and C of this chapter covered what Kafka is, how its internal pieces fit together, how ordering and lag work, Kafka Streams, exactly-once semantics, Schema Registry, the outbox pattern, CQRS, and event sourcing. If you have not read those parts, read them first. They define every term used here.

This is Part D — the operational half. It answers the questions an L6 engineer gets asked about running Kafka for real:

- "How many brokers do we need for 1 million messages per second?" — You need to know capacity planning math cold.
- "Our US-East Kafka cluster just died. How do we fail over?" — You need to know MirrorMaker 2, RTO, RPO, and offset translation.
- "A service was accidentally publishing user passwords to a Kafka topic for 48 hours. What do you do?" — You need to know crypto-shredding, GDPR event stream compliance, and ACLs.
- "How do we test that our consumer handles duplicate messages correctly?" — You need to know Testcontainers, idempotency testing, and chaos injection.
- "We are at 10 billion events per day. What does our Kafka infrastructure look like?" — You need to know the full evolution path and what LinkedIn, Uber, and Netflix actually run.

```
+----------------------+    +---------------------+    +--------------------+
|  1. CAPACITY         | -> |  2. MULTI-REGION    | -> |  3. SECURITY       |
|                      |    |                     |    |                    |
|  How many brokers,   |    |  MirrorMaker 2,     |    |  mTLS, ACLs,       |
|  partitions, TB?     |    |  active-active,     |    |  crypto-shredding, |
|  Worked examples.    |    |  failover.          |    |  GDPR compliance.  |
+----------------------+    +---------------------+    +--------------------+
         |
         v
+----------------------+    +---------------------+    +--------------------+
|  4. TESTING          | -> |  5. EVOLUTION PATH  | -> |  6. DEGRADATION    |
|                      |    |                     |    |                    |
|  Unit, integration,  |    |  Phase 1 through 4, |    |  Outbox fallback,  |
|  chaos, contracts.   |    |  cost at each tier. |    |  circuit breakers, |
|                      |    |                     |    |  monitoring.       |
+----------------------+    +---------------------+    +--------------------+
```

Read in order. Each section builds on the previous.

---

## Section 1: Kafka at Scale — Capacity Planning

### 1.1 The Concert Venue Analogy

Think of a Kafka cluster as a concert venue. The venue has a certain number of doors (brokers), each door can handle a certain number of people per minute (throughput), and people can only enter through specific sections (partitions). If you open too few doors, the line outside gets very long. If you add doors that lead nowhere, you waste money and slow down the fire-marshal check (leader election).

Capacity planning is the art of sizing the venue correctly before the concert sells out — not after the crowd is already backed up to the parking lot.

---

### 1.2 Message Throughput: The Core Formula

The first thing you calculate is raw throughput. How many bytes per second are flowing into the cluster?

```
+------------------------------------------------------------+
|  THROUGHPUT FORMULA                                        |
|                                                            |
|  throughput = (messages per second) x (avg message bytes) |
|                                                            |
|  Example:                                                  |
|  100,000 messages/sec x 2,048 bytes (2 KB) = 204,800,000 |
|  bytes/sec = ~200 MB/sec ingestion                        |
+------------------------------------------------------------+
```

But that is just the ingestion side. Kafka replicates every message to `replication_factor` brokers. If you have replication factor 3, every byte you write gets written 3 times — once on the leader partition and once on each of the two follower partitions.

```
+------------------------------------------------------------+
|  TOTAL WRITE LOAD WITH REPLICATION                         |
|                                                            |
|  total_disk_writes = throughput x replication_factor       |
|                                                            |
|  Example:                                                  |
|  200 MB/sec ingestion x 3 replicas = 600 MB/sec           |
|  total disk writes across the cluster                      |
|                                                            |
|  Typical Kafka broker on SSD: handles 200-300 MB/sec      |
|  So 600 MB/sec write load needs at least 3 brokers.       |
+------------------------------------------------------------+
```

**Key insight**: the replication factor multiplies your disk write load. Always plan for total writes, not just ingestion throughput.

---

### 1.3 Storage Sizing: How Much Disk Do You Need?

Kafka is not a database. It is a log with a retention window. You keep events for N days, and then they are deleted. That means disk usage grows proportionally to throughput and retention period.

```
+------------------------------------------------------------+
|  STORAGE FORMULA                                           |
|                                                            |
|  storage = throughput_MB_sec                              |
|           x retention_seconds                             |
|           x replication_factor                            |
|                                                            |
|  Example (uncompressed):                                   |
|  200 MB/sec x (7 days x 86,400 sec/day) x 3 replicas     |
|  = 200 x 604,800 x 3                                      |
|  = 362,880,000 MB = ~362 TB total cluster storage         |
+------------------------------------------------------------+
```

362 TB is a lot. The good news: Kafka supports compression (Snappy, LZ4, ZSTD). JSON events, log lines, and structured text compress at roughly 4:1. That takes 200 MB/sec uncompressed down to 50 MB/sec compressed.

```
+------------------------------------------------------------+
|  STORAGE WITH 4x COMPRESSION                               |
|                                                            |
|  50 MB/sec x 604,800 x 3 = ~90 TB total cluster storage   |
|                                                            |
|  From 362 TB to 90 TB — a 4x reduction.                   |
+------------------------------------------------------------+
```

**SSD vs HDD**: Kafka writes are almost entirely sequential — it appends to the end of log segment files. Sequential I/O is where spinning hard disks (HDD) excel. Random I/O is where they fall apart. So HDD is perfectly fine for Kafka in most cases, and significantly cheaper than SSD per terabyte.

Use SSD when:
- You need very low write latency, under 5 milliseconds (high-frequency trading events, for example)
- You are writing more than 500 MB/sec on a single broker (HDD tops out around 200 MB/sec sequential on modern hardware)

---

### 1.4 Partition Count Planning

Partitions are the unit of parallelism in Kafka. The maximum number of consumers that can read a topic in parallel equals the number of partitions. Fewer partitions means less parallelism. More partitions means more overhead.

```
+------------------------------------------------------------+
|  PARTITION RULES OF THUMB                                  |
|                                                            |
|  Too few partitions:                                       |
|  - Max consumer parallelism is capped                      |
|  - One partition = one consumer thread doing all the work  |
|                                                            |
|  Too many partitions:                                      |
|  - Each partition has a leader. Electing leaders costs     |
|    time. 10,000+ partitions on one broker -> slow failover |
|  - Kafka's recommendation:                                 |
|    <= 4,000 partitions per broker                          |
|    <= 200,000 partitions per cluster                       |
|                                                            |
|  Rule of thumb for sizing:                                 |
|  partitions = desired_topic_throughput_MB_sec / 10         |
|                                                            |
|  Example: 200 MB/sec topic -> 200 / 10 = 20 partitions    |
|  Result: 20 consumers can read this topic in parallel      |
+------------------------------------------------------------+
```

Why divide by 10? The assumption is that each partition can handle about 10 MB/sec of throughput on a healthy broker. If your per-partition throughput is much higher, use a smaller divisor.

---

### 1.5 Consumer Group Sizing: A Trap Most Engineers Miss

Knowing the right partition count is only half the story. You also need to know how many consumer threads to run. This is where engineers get surprised.

Imagine a topic with 20 partitions, getting 100,000 messages per second (5,000 messages/sec per partition). Each message takes 10 milliseconds to process (say, it writes to a database).

```
+------------------------------------------------------------+
|  CONSUMER SIZING EXAMPLE                                   |
|                                                            |
|  Messages per second per partition: 5,000                  |
|  Processing time per message: 10 ms                        |
|                                                            |
|  Work per second: 5,000 messages x 10 ms = 50 seconds     |
|  of processing needed every second                         |
|                                                            |
|  This means ONE thread on this partition is 50x too slow.  |
|  You need 50 threads per partition.                        |
+------------------------------------------------------------+
```

A naive consumer runs one thread per consumer instance, processes each message synchronously, and commits the offset after each message. This falls behind instantly at high throughput.

**The fix: async processing.** The consumer thread reads from Kafka fast, puts messages onto an in-memory work queue, and a thread pool of N workers processes them independently. The consumer thread never blocks waiting for processing to finish.

```
+-----------------------------------------------------------+
|  SYNC CONSUMER (slow, falls behind)                       |
|                                                            |
|  Kafka Partition  ->  Consumer Thread  ->  DB Write       |
|                       (reads, waits,       (10ms)         |
|                        reads, waits...)                    |
|                                                            |
|  Throughput: 1 message / 10ms = 100 msg/sec per thread    |
+-----------------------------------------------------------+

+-----------------------------------------------------------+
|  ASYNC CONSUMER (fast, keeps up)                          |
|                                                            |
|  Kafka Partition  ->  Consumer Thread  ->  Work Queue     |
|                       (reads fast)         |              |
|                                            v              |
|                                   Worker Pool (50 threads)|
|                                   -> DB Write (10ms each) |
|                                                            |
|  Throughput: 50 threads x 100 msg/sec = 5,000 msg/sec    |
+-----------------------------------------------------------+
```

---

### 1.6 Worked Cluster Sizing Example

Requirements from a real-world type scenario:

```
+------------------------------------------------------------+
|  INPUT REQUIREMENTS                                        |
|                                                            |
|  Messages per second:   1,000,000 (1 million)             |
|  Average message size:  1 KB                              |
|  Retention:             7 days                            |
|  Replication factor:    3                                 |
|  Compression:           LZ4, 4x ratio                    |
+------------------------------------------------------------+
```

Step through the math:

```
+------------------------------------------------------------+
|  STEP 1: RAW THROUGHPUT                                    |
|  1,000,000 msg/sec x 1 KB = 1 GB/sec uncompressed         |
|                                                            |
|  STEP 2: COMPRESSED THROUGHPUT                             |
|  1 GB/sec / 4 = 250 MB/sec after compression              |
|                                                            |
|  STEP 3: BROKER COUNT FOR THROUGHPUT                       |
|  Each broker handles 250 MB/sec (high-end SSD)            |
|  With replication: 250 MB/sec x 3 replicas = 750 MB/sec   |
|  total disk writes                                         |
|  750 MB/sec / 250 MB/sec per broker = 3 brokers minimum   |
|  (but never run minimum — plan for one broker failure)     |
|  Practical choice: 10 brokers for headroom                 |
|                                                            |
|  STEP 4: STORAGE                                           |
|  250 MB/sec x 86,400 sec/day x 7 days x 3 replicas        |
|  = 250 x 604,800 x 3 = 453,600,000 MB = ~453 TB           |
|  10 brokers x 45 TB SSD each = 450 TB. Close enough.      |
|                                                            |
|  STEP 5: PARTITIONS                                        |
|  250 MB/sec / 10 = 25 partitions per high-throughput topic |
|  25 partitions -> max 25 consumers reading in parallel     |
+------------------------------------------------------------+
```

Scale-tier summary table:

```
+--------------------+----------+-----------+-----------+------------+
| Scale Tier         | Msg/sec  | MB/sec    | Brokers   | Storage    |
|                    |          | (compr.)  | Needed    | (7-day)    |
+--------------------+----------+-----------+-----------+------------+
| Small startup      |   10,000 |    5 MB/s |     3     |    9 TB    |
| Mid-size product   |  100,000 |   50 MB/s |     3     |   90 TB    |
| Large platform     |  500,000 |  125 MB/s |     3-5   |  225 TB    |
| LinkedIn/Uber tier | 1M+      |  250 MB/s |    10+    |  450 TB+   |
+--------------------+----------+-----------+-----------+------------+
```

---

## Section 2: Multi-Region Kafka — Active-Passive and Active-Active

### 2.1 Why One Region Is Not Enough

Imagine your entire Kafka cluster is in AWS US-East-1. That data center catches fire (this has happened). Every producer in your system is trying to publish events. Every consumer is trying to read events. Nothing works. Your entire event-driven architecture is dead.

Three reasons you eventually need multi-region Kafka:

**1. Disaster recovery.** US-East fails — traffic needs to fail over to US-West automatically.

**2. Latency.** A European user's browser generates an event. That event has to travel to US-East (150 milliseconds extra round-trip) before it can be processed. If your European consumers are also in Europe, they are waiting on a US cluster they never needed.

**3. Data residency.** GDPR requires that certain EU user data stay inside the EU. You cannot send it to a US Kafka cluster, even temporarily.

---

### 2.2 Active-Passive Replication with MirrorMaker 2

The simpler setup. One cluster is the **primary** (all producers write here). One cluster is the **replica** (disaster recovery only — nobody reads from it under normal conditions).

**MirrorMaker 2** is Kafka's built-in replication tool. It is itself a Kafka consumer that reads from the primary cluster and a Kafka producer that writes to the replica cluster. It copies messages, consumer group offsets, and topic configurations.

```
+-------------------------------------------+
|  ACTIVE-PASSIVE WITH MIRRORMAKER 2         |
|                                            |
|  US-EAST (Primary)                         |
|  +----------------------------------+      |
|  | Kafka Cluster                    |      |
|  | Brokers: 10                      |      |
|  | Topics: payments, orders, users  |      |
|  +----------------------------------+      |
|       |                    ^               |
|       | Producers write    | Consumers read|
|       v                    |               |
|  [payment-service]    [fraud-detection]    |
|                                            |
|       |                                    |
|       | MirrorMaker 2                      |
|       | (reads primary, writes replica)    |
|       v                                    |
|  US-WEST (Replica - dormant)               |
|  +----------------------------------+      |
|  | Kafka Cluster                    |      |
|  | Topics: us-east.payments,        |      |
|  |         us-east.orders, ...      |      |
|  +----------------------------------+      |
+-------------------------------------------+
```

Notice the topic names in the replica have a prefix: `us-east.payments`. MirrorMaker 2 adds the source cluster name as a prefix to avoid confusion about which cluster originated the data.

**Offset translation problem**: an event at offset 1000 in the primary might end up at offset 1002 in the replica. Why? If MirrorMaker 2 filtered even one message (due to a config rule), offsets shift. During failover, you cannot just point consumers at the replica at offset 1000. MirrorMaker 2 maintains an offset mapping topic (`__consumer_offsets.us-east`) to translate consumer group positions.

```
+------------------------------------------------------------+
|  FAILOVER PROCEDURE (Active-Passive)                       |
|                                                            |
|  1. Primary (US-East) goes down                            |
|  2. Ops team verifies replica is up to date (lag = 0)      |
|  3. Update DNS: kafka.company.com -> US-West IP            |
|  4. Consumers restart, point to US-West                    |
|  5. MirrorMaker 2 offset translation maps their positions  |
|                                                            |
|  RTO (Recovery Time Objective): 15-30 minutes             |
|  RPO (Recovery Point Objective): near-zero                 |
|  (messages replicated as soon as committed in primary)     |
+------------------------------------------------------------+
```

**RTO** is how long it takes to restore service. **RPO** is how much data you can afford to lose. With MirrorMaker 2 in active-passive, your RPO is excellent (near zero) but your RTO is not great (15-30 minutes of manual or semi-automated steps).

---

### 2.3 Active-Active Replication (Both Clusters Accept Writes)

Now both US-East and US-West accept writes simultaneously. US users produce to US-East. EU users produce to US-West. MirrorMaker 2 replicates bidirectionally — US-East events appear in US-West and vice versa.

```
+-------------------------------------------------------+
|  ACTIVE-ACTIVE BIDIRECTIONAL REPLICATION               |
|                                                        |
|  US-EAST                         US-WEST              |
|  +------------------+            +------------------+ |
|  | Kafka Cluster    |  <-------> | Kafka Cluster    | |
|  | (US writers)     | MirrorMaker| (EU writers)     | |
|  |                  |     2      |                  | |
|  +------------------+            +------------------+ |
|          |                               |            |
|  [US payment-svc]               [EU payment-svc]     |
+-------------------------------------------------------+
```

This sounds great, but it creates one serious problem.

**The duplicate processing problem.** Imagine US-East writes event E at offset 500. MirrorMaker 2 replicates it to US-West. Now US-West has event E. US-West's MirrorMaker 2 replicates everything in US-West back to US-East — including event E, which originated in US-East. US-East now has event E twice.

**The fix: cycle detection via provenance headers.** MirrorMaker 2 adds a header to every replicated message: `__mm2.origin = us-east`. When US-West's MirrorMaker 2 considers replicating this message back to US-East, it checks the origin header. If the origin is already US-East, it skips it.

```
+------------------------------------------------------------+
|  CYCLE DETECTION IN ACTIVE-ACTIVE                          |
|                                                            |
|  Event E produced in US-East:                              |
|    Header: __mm2.origin = us-east                         |
|                                                            |
|  MirrorMaker 2 replicates E to US-West.                    |
|                                                            |
|  US-West's MM2 checks: should I replicate E back?          |
|    Origin = us-east. I am us-west. Destination = us-east.  |
|    Skip. Cycle detected.                                    |
+------------------------------------------------------------+
```

**Message ordering caveat**: In active-active, events produced in US-East and US-West interleave when replicated. You cannot guarantee that consumer A sees event X before event Y if X was produced in US-East and Y was produced in US-West. Cross-region ordering does not exist.

Use active-active only when:
- Operations are **commutative** (A then B gives same result as B then A) — e.g., "user viewed a product" events
- Ordering across regions is not required
- You accept that the same event may be processed in both regions

---

### 2.4 Confluent Multi-Region Clusters

Confluent (the commercial company built around Kafka) offers a product called Multi-Region Clusters. This is a single Kafka cluster whose brokers are physically located in multiple data centers. From your application's perspective, it is one cluster — no offset translation, no separate MirrorMaker 2 process.

Two consistency modes:

```
+------------------------------------------------------------+
|  CONFLUENT MULTI-REGION CLUSTER OPTIONS                    |
|                                                            |
|  Mode 1: SYNC (strong consistency)                         |
|  Produce ack requires replicas in BOTH regions to confirm. |
|  Latency: high (waits for cross-region network roundtrip)  |
|  RPO: zero. No data loss possible.                         |
|                                                            |
|  Mode 2: ASYNC (eventual consistency)                      |
|  Primary region acks. Secondary region replicates async.   |
|  Latency: low (same as single-region)                      |
|  RPO: non-zero. Recent messages may be lost if primary     |
|       region dies before replication completes.            |
+------------------------------------------------------------+
```

The tradeoff is classic: strong consistency costs latency, low latency costs durability guarantee.

---

## Section 3: Security in Event-Driven Systems

### 3.1 The Key-to-the-Filing-Cabinet Analogy

Think of a Kafka cluster as a building full of filing cabinets (topics). Security has three layers:

1. **Authentication**: Is this person allowed to enter the building at all? (Who are you?)
2. **Authorization**: Which specific filing cabinets can this person open? (What can you do?)
3. **Encryption**: Can someone read the papers if they steal a cabinet? (Is data unreadable at rest?)

---

### 3.2 Authentication: Who Can Produce or Consume?

Kafka supports three main authentication mechanisms:

```
+------------------------------------------------------------+
|  KAFKA AUTHENTICATION OPTIONS                              |
|                                                            |
|  SASL/PLAIN                                                |
|  - Username + password sent over the wire                  |
|  - Simple, but password visible if TLS not enabled         |
|  - OK for dev/test environments                            |
|                                                            |
|  SASL/SCRAM                                                |
|  - Username + password, but password is hashed            |
|  - Server never stores or sees plaintext password         |
|  - Better than PLAIN, reasonable for internal services     |
|                                                            |
|  mTLS (mutual TLS)                                         |
|  - Both client AND broker present certificates             |
|  - Each service gets its own certificate signed by your CA |
|  - "payment-service" has cert CN=payment-service           |
|  - Broker rejects any client without a valid cert          |
|  - Recommended for production                              |
+------------------------------------------------------------+
```

With mTLS, the certificate identity becomes the **principal** used for authorization. `payment-service` has a certificate with `CN=payment-service`. Kafka sees that principal and checks its ACLs.

---

### 3.3 Authorization: ACLs (Access Control Lists)

ACLs answer: which operations can this principal perform on which resources?

```bash
# Grant payment-service WRITE access to the payments topic
kafka-acls.sh --add \
  --allow-principal User:payment-service \
  --operation WRITE \
  --topic payments \
  --bootstrap-server kafka:9093

# Grant fraud-detection READ access to the payments topic
kafka-acls.sh --add \
  --allow-principal User:fraud-detection \
  --operation READ \
  --topic payments \
  --bootstrap-server kafka:9093
```

```
+------------------------------------------------------------+
|  ACL MATRIX EXAMPLE                                        |
|                                                            |
|  Service           | payments topic | orders topic         |
|  ------------------+----------------+--------------------  |
|  payment-service   | WRITE          | -                    |
|  fraud-detection   | READ           | READ                 |
|  order-service     | -              | WRITE                |
|  analytics-service | READ           | READ                 |
|  ------------------+----------------+--------------------  |
|                                                            |
|  WRONG: giving analytics-service wildcard (*) access.     |
|  Now analytics can read payment secrets, PII, everything. |
+------------------------------------------------------------+
```

**Principle of least privilege**: every service can access exactly the topics it needs, nothing more. This is not just best practice — at most companies, it is a compliance requirement for PCI-DSS (payment card security) and HIPAA (healthcare data).

---

### 3.4 Encryption in Transit and at Rest

**In transit**: enable TLS between every component — producers to brokers, brokers to brokers, brokers to consumers.

```
# Producer config (in application.properties or equivalent)
security.protocol=SSL
ssl.truststore.location=/etc/kafka/ssl/truststore.jks
ssl.truststore.password=changeit
ssl.keystore.location=/etc/kafka/ssl/keystore.jks
ssl.keystore.password=changeit
```

**At rest**: Kafka does NOT encrypt data stored in its log files by default. The files on disk are plaintext. To protect data at rest:
- AWS MSK: enable EBS encryption (all broker volumes are encrypted by AWS KMS)
- Self-hosted: use dm-crypt / LUKS on the broker disk volumes
- This protects against physical disk theft, but does not protect against an attacker who has OS-level access to the broker

---

### 3.5 PII in Event Streams: The GDPR Time Bomb

This is a scenario that bites companies over and over. Event streams and data privacy requirements are in direct tension.

The tension:

```
+------------------------------------------------------------+
|  THE GDPR / KAFKA PROBLEM                                  |
|                                                            |
|  Kafka retains events for 7 days (or more).               |
|                                                            |
|  User submits GDPR "right to be forgotten" request:        |
|  "Delete all my personal data."                            |
|                                                            |
|  Problem: You cannot delete individual messages from Kafka. |
|  Kafka is an append-only log. You can only delete entire   |
|  partitions or wait for retention to expire.               |
|                                                            |
|  Result: User data is still sitting in your event log      |
|  for up to 7 days (or however long your retention is),    |
|  being replicated and consumed.                            |
+------------------------------------------------------------+
```

There are three patterns to handle this:

**Solution 1: Crypto-shredding**

Encrypt the PII in each event with a per-user encryption key. Store those keys in a separate key store (AWS KMS, HashiCorp Vault).

When a user requests deletion: delete their encryption key. The events still exist in Kafka, but the PII inside them is now unreadable — it is just encrypted garbage. No key, no data.

```
+------------------------------------------------------------+
|  CRYPTO-SHREDDING                                          |
|                                                            |
|  At event write time:                                      |
|  1. Look up user_123's encryption key from Key Store       |
|  2. Encrypt PII fields: {email: AES(key_123, "a@b.com")}  |
|  3. Publish encrypted event to Kafka                       |
|                                                            |
|  At deletion time:                                         |
|  1. Delete key_123 from Key Store                          |
|  2. Events still in Kafka, but PII is now undecipherable   |
|                                                            |
|  [Key Store]  <-- delete key_123                           |
|       |                                                    |
|       | (no key anymore)                                   |
|       v                                                    |
|  [Kafka Event]: {email: 9fA2xP...} <- unreadable garbage  |
+------------------------------------------------------------+
```

**Solution 2: Tokenization**

Replace PII in events with a **token** (a random identifier). Store the token-to-PII mapping in a separate database. Events in Kafka contain tokens, not raw PII.

When a user requests deletion: delete their token mappings. Now nobody can resolve the tokens back to real PII.

**Solution 3: Minimize PII in events**

The simplest solution: do not put PII in events at all. Put only the `user_id`. Any service that needs the email or phone number does a real-time lookup from the User Service. The event itself contains no sensitive data.

This only works if consumers can afford the latency of a lookup, and if the lookup does not create a new scaling bottleneck.

---

### 3.6 Real Incident: Passwords Published to Kafka for 48 Hours

This type of incident has happened at multiple companies. Here is what the scenario looks like:

A team changes the User Registration event to include "full user context for debugging." Someone copies the raw HTTP request body into the event payload. That body contains the user's plaintext password from the registration form.

This event goes to the `user-registration` topic. Retention is 7 days. Six downstream consumer groups are reading this topic: analytics, fraud detection, CRM sync, email notifications, AB testing, and data warehouse export.

**What happens**:
- 6 consumer groups all see every password for 48 hours
- The data warehouse export sends events to an external analytics platform — passwords now leave your infrastructure
- Kafka has replicated these events to 3 brokers — the passwords are on 3 physical disks

**Response**:
1. **Immediately**: disable the consumer groups that read this topic and stop the data warehouse export
2. **Short-term**: force a consumer group offset reset to skip past the bad events
3. **Data destruction**: you cannot delete the messages. You wait for them to expire (7 days) OR reduce the retention on this topic to 0, wait for compaction to clear it, then restore retention
4. **User impact**: force-rotate all passwords for all users registered in that 48-hour window
5. **Audit**: review all consumer group logs to determine who actually read those messages
6. **Notification**: in most jurisdictions, a breach of password data requires notifying affected users within 72 hours

**The lesson**: put a linter in your CI/CD that scans event schemas for fields named `password`, `secret`, `token`, `ssn`, `cvv`, and blocks the deployment.

---

### 3.7 Audit Logging: Who Read What?

Producing events to Kafka and consuming them both leave a trail — but only if you set up audit logging explicitly. Out of the box, Kafka does not log who read what.

Options:

```
+------------------------------------------------------------+
|  AUDIT LOGGING OPTIONS                                     |
|                                                            |
|  Option 1: Confluent Audit Logs (commercial)               |
|  - Records all Kafka API calls: who connected, what        |
|    topic, what operation, when.                            |
|  - Outputs to a special Kafka topic or SIEM                |
|                                                            |
|  Option 2: Roll your own audit topic                       |
|  - Every service publishes an audit event after consuming  |
|  - Topic: __audit_log                                      |
|  - Event: {service: "fraud-detection",                     |
|             topic: "payments",                             |
|             consumer_group: "fraud-cg",                    |
|             partition: 3, offset: 10042, timestamp: ...}   |
|                                                            |
|  Option 3: Broker access logs (JMX metrics)                |
|  - Kafka exposes per-topic metrics via JMX                 |
|  - Tells you rate of reads/writes but not who specifically |
+------------------------------------------------------------+
```

---

## Section 4: Testing Event-Driven Systems

### 4.1 The Fire Drill Analogy

You do not wait for a real fire to find out whether your fire alarm works. You run drills. Testing event-driven systems is the same: you simulate broken producers, duplicate messages, and dead brokers before they happen in production — so you know your system handles them correctly.

There are four layers of testing: unit, integration, idempotency, and chaos.

---

### 4.2 Unit Testing Event Handlers

You do not need a real Kafka cluster to test whether your handler logic is correct. Mock the consumer and test the handler in isolation.

```python
def test_order_placed_handler():
    # Create a fake event (no Kafka needed)
    event = OrderPlacedEvent(
        order_id="123",
        user_id="456",
        amount=99.99
    )

    # Create handler with mocked dependencies
    mock_inventory = Mock()
    mock_notifications = Mock()
    handler = OrderPlacedHandler(mock_inventory, mock_notifications)

    # Call the handler directly
    handler.handle(event)

    # Assert the right side effects happened
    mock_inventory.reserve.assert_called_once_with("123")
    mock_notifications.notify.assert_called_once_with("456")
```

This test runs in milliseconds, has no external dependencies, and will catch regressions in your handler logic immediately. Write many of these.

---

### 4.3 Integration Testing with Testcontainers

Unit tests verify logic. Integration tests verify the full pipeline end-to-end — producer publishes, Kafka routes, consumer receives and processes correctly.

**Testcontainers** is a library (available in Python, Java, Go, and others) that starts a real Docker container (real Kafka broker, real Zookeeper) inside your test suite. The container is spun up for the test, used, and destroyed. No test environment to manage manually.

```python
import pytest
from testcontainers.kafka import KafkaContainer
from kafka import KafkaProducer, KafkaConsumer
import json

@pytest.fixture(scope="session")
def kafka_broker():
    # Starts a real Kafka broker in Docker for the test session
    with KafkaContainer("confluentinc/cp-kafka:7.4.0") as kafka:
        yield kafka.get_bootstrap_server()

def test_order_event_end_to_end(kafka_broker):
    # Produce an order event to the real (test) Kafka
    producer = KafkaProducer(bootstrap_servers=kafka_broker)
    producer.send(
        "orders",
        key=b"123",
        value=b'{"order_id": "123", "user_id": "456"}'
    )
    producer.flush()

    # Consume from the downstream results topic
    consumer = KafkaConsumer(
        "order-confirmations",
        bootstrap_servers=kafka_broker,
        auto_offset_reset="earliest",
        consumer_timeout_ms=5000
    )

    messages = [msg for msg in consumer]
    assert len(messages) == 1
    result = json.loads(messages[0].value)
    assert result["order_id"] == "123"
    assert result["status"] == "confirmed"
```

Integration tests run slower than unit tests (10-30 seconds for container startup) but catch a whole class of bugs that unit tests miss: serialization errors, wrong topic names, incorrect offset commit logic, consumer group rebalance handling.

---

### 4.4 Testing At-Least-Once and Idempotency

At-least-once delivery means your consumer may see the same message twice. This happens when: the consumer processes a message, then crashes before committing the offset. When it restarts, it re-reads and re-processes that message.

Your handler must be **idempotent** — processing the same message twice must produce the same result as processing it once.

Test this explicitly:

```python
def test_order_handler_is_idempotent(kafka_broker):
    event_bytes = b'{"order_id": "order-999", "user_id": "user-42"}'

    # Process the same event twice
    handler.handle(event_bytes)
    handler.handle(event_bytes)  # duplicate!

    # Verify the order was only confirmed ONCE in the database
    confirmed_orders = db.query(
        "SELECT COUNT(*) FROM order_confirmations WHERE order_id = 'order-999'"
    )
    assert confirmed_orders == 1  # not 2

    # Verify the user was only notified ONCE
    assert mock_notifications.notify.call_count == 1  # not 2
```

Also test the crash-and-restart scenario:

```
+------------------------------------------------------------+
|  CRASH AND RESTART TEST                                    |
|                                                            |
|  1. Consumer reads message M from Kafka (offset 100)       |
|  2. Consumer processes M (writes to DB)                    |
|  3. CRASH before offset commit                             |
|  4. Consumer restarts at offset 100 (last committed)       |
|  5. Consumer reads message M again                         |
|  6. Handler runs again                                     |
|                                                            |
|  Expected: DB has M's effect once. No duplicate side effects|
|  Test verifies: idempotency key check fires, duplicate     |
|  is silently skipped.                                      |
+------------------------------------------------------------+
```

---

### 4.5 Chaos Testing for Event Systems

Chaos testing deliberately breaks things to verify your system handles failures gracefully. Netflix built the concept of **Chaos Monkey** — a tool that randomly kills production services to verify resilience. Apply the same philosophy to Kafka.

**Chaos scenario 1: Kill a broker**
- Start 3 Kafka brokers in your test environment
- Kill broker 2
- Verify: producers automatically retry and eventually succeed (leader election completes in ~30 seconds)
- Verify: consumers on partitions led by broker 2 fail over to the new leader without message loss

**Chaos scenario 2: Simulate consumer lag**
- Add an artificial sleep in your consumer processing to simulate a slow downstream DB
- Let lag build to 100,000 messages
- Verify: your lag monitoring alerts fire within 5 minutes
- Verify: adding more consumers (scale out) reduces lag back to zero within N minutes

**Chaos scenario 3: Inject poison messages**
- Publish malformed events (empty body, wrong schema version, negative amounts, null keys) to your topic
- Verify: the consumer sends them to the Dead Letter Queue instead of crashing
- Verify: the main consumer continues processing valid messages (no stall)
- Verify: the DLQ alert fires so a human is notified

```
+------------------------------------------------------------+
|  POISON MESSAGE CHAOS TEST                                 |
|                                                            |
|  Normal messages:   [M1] [M2] [M3] [POISON] [M5] [M6]    |
|                                                            |
|  Expected behavior:                                        |
|  M1 -> processed ok                                        |
|  M2 -> processed ok                                        |
|  M3 -> processed ok                                        |
|  POISON -> caught by error handler -> sent to DLQ topic   |
|  M5 -> processed ok (consumer did NOT crash)               |
|  M6 -> processed ok                                        |
|                                                            |
|  Wrong behavior (do NOT want):                             |
|  POISON -> exception -> consumer crashes -> restarts ->    |
|            reads POISON again -> crashes again -> loop     |
+------------------------------------------------------------+
```

---

### 4.6 Contract Testing for Event Schemas

When teams own different services that communicate through Kafka, schema changes can silently break consumers. **Contract testing** makes the compatibility check explicit.

The producer owns a **contract** — a schema definition of what it promises to publish. Each consumer has a **contract** — a schema definition of what it expects to receive. Contract testing verifies these two are compatible.

Tools:
- **Pact**: producer publishes events, consumer specifies what fields it uses, Pact verifies compatibility
- **Schema Registry with compatibility checks**: every schema change is checked for backwards compatibility before deployment. BACKWARD compatibility means: new schema can read data written with old schema. FORWARD compatibility means: old schema can read data written with new schema.

```
+------------------------------------------------------------+
|  CI/CD CONTRACT CHECK FLOW                                 |
|                                                            |
|  Developer changes OrderPlacedEvent schema:                |
|  - Renames "amount" field to "total_amount"               |
|                                                            |
|  CI pipeline step: "schema compatibility check"           |
|                                                            |
|  Schema Registry: BACKWARD check FAILS.                    |
|  Old consumers still expect "amount". It is now missing.   |
|                                                            |
|  Build BLOCKED. Developer is notified.                     |
|  Fix: keep "amount" (deprecated) and ADD "total_amount".   |
|  Consumers migrate to "total_amount" over next 2 sprints.  |
|  Then remove "amount".                                     |
+------------------------------------------------------------+
```

This catches breaking schema changes before they reach production. Without this check, you discover the break when consumers start throwing `KeyError: 'amount'` at 2 AM.

---

## Section 5: Evolution Path — V1 Through 100x Scale

### 5.1 The City Growth Analogy

A city does not build a ten-lane highway on its first day. It starts with a dirt road, paves it when traffic increases, adds traffic lights when intersections become dangerous, builds a freeway when the town becomes a suburb, and builds a subway when the suburb becomes a metropolis.

Your event-driven infrastructure follows the same arc. The mistake is building the subway on day one when you have five users.

---

### 5.2 Phase 1: No Kafka (Under 10,000 Events Per Day)

At this scale, Kafka is almost certainly wrong. The operational overhead of running a Kafka cluster — ZooKeeper (or KRaft in newer versions), monitoring, schema registry, DLQ management — is not worth it when you could simply poll a database table every 30 seconds.

**What to use instead:**
- Direct database polling: `SELECT * FROM orders WHERE processed = false LIMIT 100`
- REST webhooks: Service A calls Service B's HTTP endpoint when something happens
- AWS SQS: managed queue, zero ops overhead, handles millions of messages per month cheaply

**When to graduate to Kafka:**
- You need fan-out to 3 or more independent consumers
- Async processing is required (caller cannot wait for all side effects)
- Burst handling: events arrive 10x faster than consumers can process them

Many startups add Kafka at 10,000 events/day because it sounds impressive in architecture diagrams. The result: two engineers spend 30% of their time on Kafka infrastructure while the actual business logic sits waiting. Do not do this.

---

### 5.3 Phase 2: Single Kafka Cluster (10,000 to 1 Million Events Per Day)

Now Kafka is justified. The cluster is small: three brokers (minimum for replication factor 3 to work properly), one Schema Registry instance, one topic per domain event type.

```
+------------------------------------------------------------+
|  PHASE 2 ARCHITECTURE                                      |
|                                                            |
|  [order-service]  --->  Kafka Cluster (3 brokers)          |
|  [user-service]   --->  |                                  |
|                         | topics:                          |
|                         |   order.placed                   |
|                         |   user.registered                |
|                         |   payment.completed              |
|                         |                                  |
|  Consumers:             |                                  |
|  [fraud-detection]  <---|                                  |
|  [notifications]    <---|                                  |
|  [analytics]        <---|                                  |
+------------------------------------------------------------+
```

**What breaks first at this phase**: usually a **poison message** from a new event type that nobody tested end-to-end. Or a **partition imbalance** — one partition is getting 80% of traffic because the partition key was poorly chosen (for example, using a status field that only has two values: "pending" and "completed").

Phase 2 checklist:
- Consumer lag alerting configured
- At least one DLQ per consumer group
- Broker disk usage alert at 70% capacity
- Producer error rate monitored

---

### 5.4 Phase 3: Multiple Topics, Multiple Teams (1 Million to 100 Million Events Per Day)

Now multiple teams own different parts of the Kafka cluster. Team A is changing the `order.placed` schema without telling Team B who consumes it. Teams are fighting over topic naming conventions. Someone keeps misconfiguring consumer group IDs and accidentally shares a consumer group with another team's service.

**Schema Registry becomes essential** at this phase. Every schema change goes through the registry and is checked for compatibility before deployment.

**Consumer lag SLAs** emerge: the Notifications team promises a P99 notification delivery within 30 seconds of an event. This requires that consumer lag on their consumer group stays below the equivalent of 30 seconds of backlog.

**Kafka Connect** standardizes the connectors: rather than every team writing their own producer to capture database changes, they use Debezium (a Kafka Connect source connector) to read MySQL or Postgres change logs and publish them to Kafka. Rather than every team writing their own Kafka consumer to write to a data warehouse, they use a Kafka Connect sink connector.

```
+------------------------------------------------------------+
|  PHASE 3 ARCHITECTURE                                      |
|                                                            |
|  [MySQL DB] -> Debezium (Kafka Connect Source)             |
|                    |                                       |
|                    v                                       |
|             Kafka Cluster                                  |
|             + Schema Registry                              |
|                    |                                       |
|          +---------+-----------+                           |
|          v                     v                           |
|  [fraud-service]         BigQuery (Kafka Connect Sink)     |
|  [notification-svc]      Elasticsearch (Kafka Connect Sink)|
+------------------------------------------------------------+
```

---

### 5.5 Phase 4: Multi-Cluster, Multi-Region (100 Million+ Events Per Day)

At this scale (LinkedIn reaches 2 trillion messages per day, Uber 4 trillion, Netflix over 1 trillion), the architecture changes fundamentally.

**Domain-separated clusters**: instead of one giant cluster, you run separate clusters per business domain. The payments cluster is isolated from the user-events cluster. A bug in user-events processing does not affect payment event throughput. A broker failure in payments does not trigger partition rebalancing in user-events.

```
+------------------------------------------------------------+
|  PHASE 4 MULTI-CLUSTER ARCHITECTURE                        |
|                                                            |
|  Payments Domain:                                          |
|  +------------------+    MirrorMaker 2    +-------------+ |
|  | Payments Cluster |  ----------------> | Payments DR | |
|  | US-East, 20 brk  |                    | US-West     | |
|  +------------------+                    +-------------+ |
|                                                           |
|  User Events Domain:                                       |
|  +------------------+    MirrorMaker 2    +-------------+ |
|  | User-Events Cltr |  ----------------> | User-Ev DR  | |
|  | US-East, 10 brk  |                    | US-West     | |
|  +------------------+                    +-------------+ |
|                                                           |
|  Analytics Domain:                                         |
|  +------------------+                                     |
|  | Analytics Cluster|  <-- firehose from both domains     |
|  | US-East, 30 brk  |                                     |
|  +------------------+                                     |
+------------------------------------------------------------+
```

At this scale you need a **dedicated Kafka platform team** — typically six or more engineers whose full-time job is Kafka infrastructure. They manage broker upgrades, partition rebalancing, MirrorMaker 2 configuration, Schema Registry governance, and capacity planning. Application teams never touch broker configuration directly.

---

### 5.6 Cost Analysis at Scale

The build-vs-buy question for Kafka comes down to operational cost versus infrastructure cost.

```
+------------------------------------------------------------+
|  COST COMPARISON AT 1 TB/DAY INGESTION                     |
|                                                            |
|  MANAGED (Confluent Cloud / AWS MSK):                      |
|  Storage: 1 TB x 7 days = 7 TB x $0.09/GB = $630/month   |
|  Network: 1 TB ingest + 3 TB consumer egress              |
|           = 4 TB x $0.08/GB = $320/month                  |
|  Confluent licensing: ~$500/month at this tier             |
|  Total: ~$1,450/month                                      |
|  Ops engineers needed: 0.25 FTE (monitoring + tuning)      |
|                                                            |
|  SELF-HOSTED (on-premises or EC2):                         |
|  Hardware: 5 x i3.4xlarge EC2 = $5,000/month              |
|  (includes 3.8 TB NVMe SSD per instance)                   |
|  Ops engineers: 1 FTE at $200K/year = $16,700/month fully  |
|                loaded                                      |
|  Total: ~$21,700/month                                     |
|                                                            |
|  CROSSOVER POINT:                                          |
|  Managed is cheaper until you reach ~50+ TB/day ingestion  |
|  At LinkedIn/Uber scale (petabytes/day), self-hosted wins  |
+------------------------------------------------------------+
```

The real cost of self-hosted Kafka is rarely the hardware — it is the engineering time. An on-call rotation for a Kafka cluster that pages at 3 AM costs more than Confluent's licensing fee until you are very large.

---

## Section 6: Graceful Degradation When Kafka Is Unavailable

### 6.1 The Power Outage Analogy

A good hospital has a generator. When the power grid fails, critical systems (operating rooms, ICU monitors, life support) keep running. Non-critical systems (the cafeteria coffee machine) can wait.

Your services need the same thinking. When Kafka goes down, which operations must succeed? Which can degrade gracefully? Which can safely pause?

---

### 6.2 What Happens to Producers When Kafka Is Down?

A producer calls `producer.send("payments", event)`. Kafka is down. The call fails. Now what?

```
+------------------------------------------------------------+
|  PRODUCER FALLBACK OPTIONS                                 |
|                                                            |
|  Option 1: FAIL THE REQUEST (simplest, worst UX)           |
|  "Sorry, payment service is temporarily unavailable."      |
|  User retries. You lose conversions.                       |
|                                                            |
|  Option 2: IN-MEMORY BUFFER (risky)                        |
|  Store the event in an in-memory queue. When Kafka comes   |
|  back, drain the queue and publish.                        |
|  Risk: if the service restarts while Kafka is down,        |
|  all buffered events are LOST. Not acceptable for payments.|
|                                                            |
|  Option 3: OUTBOX TABLE (most durable)                     |
|  Write the event to a `pending_events` table in your own   |
|  database, in the same transaction as the business action. |
|  A background job reads the table and publishes to Kafka.  |
|  If Kafka is down, events sit safely in the DB.            |
|  When Kafka comes back, the background job drains the table.|
|  Events are never lost.                                    |
+------------------------------------------------------------+
```

The outbox pattern is covered in depth in Part B of this chapter. Here, the key point is: for any event that represents money, user data, or a business commitment — always use the outbox table. In-memory buffers are only acceptable for non-critical metrics and telemetry events.

---

### 6.3 What Happens to Consumers When Kafka Is Down?

A consumer calls `consumer.poll(timeout=1000)`. Kafka is down. The poll returns an exception.

```
+------------------------------------------------------------+
|  CONSUMER FALLBACK OPTIONS                                 |
|                                                            |
|  Option 1: PAUSE AND RETRY (most common)                   |
|  Consumer catches the exception, logs it, sleeps 10s,      |
|  tries again. Processing halts until Kafka recovers.       |
|  Acceptable when: processing can be delayed.               |
|  Not acceptable when: consumer drives real-time features   |
|  (fraud detection, live inventory).                        |
|                                                            |
|  Option 2: FALL BACK TO DB POLLING                         |
|  Consumer bypasses Kafka and queries the source database   |
|  directly: SELECT * FROM orders WHERE processed = false.   |
|  Acceptable when: database is still available.             |
|  Risk: now two things (Kafka consumer + fallback poller)   |
|  can both process the same event -> need idempotency.      |
+------------------------------------------------------------+
```

---

### 6.4 Circuit Breaker for Kafka Producers

If Kafka is down, do not let every microservice hammer it with continuous retries. Each retry attempt consumes threads, sockets, and timeout budget. Instead, use a **circuit breaker**.

```
+------------------------------------------------------------+
|  CIRCUIT BREAKER STATE MACHINE                             |
|                                                            |
|  CLOSED (normal) -----> OPEN (Kafka down)                  |
|  N consecutive fails     Fast-fail for `duration`          |
|                          |                                 |
|                          v                                 |
|                    HALF-OPEN (testing recovery)            |
|                    Allow 1 request through                 |
|                    |           |                           |
|                    | success   | fail                      |
|                    v           v                           |
|                  CLOSED      OPEN                          |
|                  (Kafka is   (still down, wait more)       |
|                   back)                                    |
|                                                            |
|  During OPEN state:                                        |
|  - Do not attempt Kafka publish                            |
|  - Write event to outbox table immediately                 |
|  - Return success to caller (event is durably queued)      |
+------------------------------------------------------------+
```

Popular circuit breaker libraries: Resilience4j (Java), pybreaker (Python), go-resiliency (Go).

---

### 6.5 Monitoring Kafka Health: The Essential Dashboard

You cannot fix what you do not see. These are the six metrics every Kafka operator must watch continuously.

```
+------------------------------------------------------------+
|  KAFKA MONITORING DASHBOARD                                |
|                                                            |
|  Metric                  | Normal   | Alert Threshold     |
|  ------------------------+----------+-------------------   |
|  Messages In / sec       | > 0      | sudden drop to 0    |
|  (per topic)             |          | = producer outage   |
|  ------------------------+----------+-------------------   |
|  Consumer Group Lag      | < 1,000  | > 10,000 for 5 min  |
|  (per consumer group)    |          | = consumer too slow  |
|  ------------------------+----------+-------------------   |
|  Under-Replicated        | 0        | any value > 0       |
|  Partitions              |          | = data at risk      |
|  (must stay zero)        |          |                     |
|  ------------------------+----------+-------------------   |
|  Broker Disk Usage       | < 70%    | > 70%               |
|  (per broker)            |          | = near capacity     |
|  ------------------------+----------+-------------------   |
|  Active Controller Count | 1        | != 1                |
|  (whole cluster)         |          | = election problem  |
|  ------------------------+----------+-------------------   |
|  Request Handler Avg     | < 50%    | > 80% for 5 min     |
|  Idle Percentage         |          | = broker overloaded  |
+------------------------------------------------------------+
```

**Under-Replicated Partitions** is the single most important metric. When this is non-zero, it means some partitions do not have all their replicas in sync. If a broker fails right now, you would lose data. This metric should alert immediately — not after 5 minutes.

**JMX metric names for your monitoring system (Prometheus/Datadog/Grafana):**

```
# Under-replicated partitions (should always be 0)
kafka.server:type=ReplicaManager,name=UnderReplicatedPartitions

# Messages in per second per topic
kafka.server:type=BrokerTopicMetrics,name=MessagesInPerSec,topic=payments

# Consumer group lag
# (use kafka-consumer-groups.sh --describe or kafka_exporter)
kafka_consumergroup_lag{consumergroup="fraud-cg", topic="payments"}
```

---

### 6.6 Disk Alert: Why 70% Is the Warning Level

Kafka writes data in **segment files** — typically 1 GB each. When a segment is complete, Kafka closes it and starts a new one. When the retention window expires, it deletes old segments.

If your disk fills to 95%, Kafka tries to start a new segment and fails. The broker crashes. Data loss is possible.

You alert at 70% to give yourself time to:
1. Identify which topics are growing fastest
2. Reduce retention on low-priority topics
3. Add more disk capacity (attach a larger volume, add a broker)

The gap between 70% alert and 100% disk full should be enough time to fix the problem during business hours, not 3 AM.

---

## Summary and Interview Cheat Sheet

This is what you should be able to say out loud in an interview without looking anything up:

```
+------------------------------------------------------------+
|  CAPACITY PLANNING QUICK REFERENCE                         |
|                                                            |
|  Throughput: msg/sec x bytes = MB/sec ingestion            |
|  Total writes: MB/sec x replication_factor                 |
|  Storage: MB/sec x retention_sec x replication_factor      |
|  Compression: divide storage by 4 for typical JSON         |
|  Partitions: topic_MB_sec / 10                             |
|  Max consumers: = partition count                          |
+------------------------------------------------------------+

+------------------------------------------------------------+
|  MULTI-REGION QUICK REFERENCE                              |
|                                                            |
|  Active-Passive: primary writes only. MM2 replicates.      |
|  RTO: 15-30 min. RPO: near-zero.                           |
|                                                            |
|  Active-Active: both regions write. MM2 bidirectional.     |
|  Cycle detection via __mm2.origin header.                  |
|  No cross-region ordering guarantee.                       |
+------------------------------------------------------------+

+------------------------------------------------------------+
|  SECURITY QUICK REFERENCE                                  |
|                                                            |
|  Auth: mTLS for production (certificate per service)       |
|  Authz: ACLs, least privilege                              |
|  GDPR: crypto-shredding or tokenization                    |
|  Never put raw PII in event payloads without encryption    |
+------------------------------------------------------------+

+------------------------------------------------------------+
|  EVOLUTION PHASES                                          |
|                                                            |
|  Phase 1 (<10K/day):  no Kafka. SQS or DB polling.        |
|  Phase 2 (1M/day):    3-broker single cluster.             |
|  Phase 3 (100M/day):  Schema Registry, Connect, lag SLAs.  |
|  Phase 4 (100M+/day): multi-cluster, multi-region, 6+ FTE. |
+------------------------------------------------------------+

+------------------------------------------------------------+
|  DEGRADATION QUICK REFERENCE                               |
|                                                            |
|  Producers: outbox table (never in-memory buffer for PII)  |
|  Consumers: pause-and-retry or fallback DB poll            |
|  Circuit breaker: open after N failures, half-open probe   |
|  Alert: under-replicated partitions > 0 = IMMEDIATE        |
|  Alert: consumer lag > threshold for 5 min = PAGE          |
|  Alert: disk usage > 70% = WARNING                         |
+------------------------------------------------------------+
```

---

*End of Chapter 33, Part D.*
*Chapter 34 covers distributed consensus: Raft, Paxos, and how systems like etcd, ZooKeeper, and Spanner make decisions when nodes disagree.*
# Chapter 33 Supplement A: Kafka Deep Mechanics — Staff-Level Interview Prep

> This supplement covers **additional material** not in the base Chapter 33 parts. Do not
> read this as a replacement — read base parts first, then use this for the deeper
> mechanics that separate L5 answers from L6 answers.

---

## Section 1: Kafka Schema Evolution in Practice

### The Versioning Problem (The Time-Travel Headache)

Imagine you write a letter in 2020, seal it in an envelope, and someone opens it in 2025.
In those five years the language changed — words you used no longer mean the same thing.
Kafka is exactly like that. Events written today sit on disk for seven days (default retention),
but if you use **event sourcing** — replaying history to rebuild state — those events may sit
for years. Your system must be able to read a 2021 event today even though the schema has
changed four times since.

Here is the core tension:

```
  Producer updated to v2 schema         Consumer still on v1 schema
  ---------------------------------     -------------------------------
  Writes: { amount: 9999 (long) }  -->  Reads: expecting amount as double
                                         ERROR: type mismatch. Crash.
```

The producer team shipped on Tuesday. The consumer team ships on Thursday.
Those 48 hours of coexistence are when everything breaks.

At L6 you are expected to prevent this entirely through schema governance, not just survive it.

---

### Avro Schema Evolution Rules

**Apache Avro** is the standard serialization format used with Kafka's Schema Registry
(Confluent). Avro schemas are JSON documents describing field names and types.

**Version 1 — the original schema:**

```json
{
  "type": "record",
  "name": "Order",
  "namespace": "com.example",
  "fields": [
    { "name": "order_id", "type": "string" },
    { "name": "amount",   "type": "double" }
  ]
}
```

**Version 2 — backward compatible change (add optional field):**

```json
{
  "type": "record",
  "name": "Order",
  "namespace": "com.example",
  "fields": [
    { "name": "order_id", "type": "string" },
    { "name": "amount",   "type": "double" },
    { "name": "currency", "type": "string", "default": "USD" }
  ]
}
```

A v1 consumer reading a v2 message: no `currency` field in the old schema? Use the
default `"USD"`. No crash. This is **backward compatible**: the new schema can read
old messages, and old consumers can still read new messages because the new field has
a default.

**Version 3 — a BREAKING change (type change):**

```json
{
  "type": "record",
  "name": "Order",
  "namespace": "com.example",
  "fields": [
    { "name": "order_id", "type": "string" },
    { "name": "amount",   "type": "long" },
    { "name": "currency", "type": "string", "default": "USD" }
  ]
}
```

`amount` changed from `double` to `long`. A v1 consumer expecting `double` reads `long`
bytes → type mismatch → crash. This breaks production. The Schema Registry with the
right compatibility mode would have **rejected** this schema at registration time,
preventing the deploy from ever reaching production.

---

### Schema Registry Compatibility Modes

The **Confluent Schema Registry** sits alongside your Kafka cluster. Producers register
schemas before writing. Consumers fetch schemas by ID embedded in each message byte
envelope. Compatibility is enforced at registration time.

| Mode         | What it checks                                              | Rejects when                                             | Recommended usage                            |
|--------------|-------------------------------------------------------------|----------------------------------------------------------|----------------------------------------------|
| `BACKWARD`   | New schema can read old messages                            | New schema cannot deserialize old messages               | Default. Safe for rolling consumer deploys.  |
| `FORWARD`    | Old schema can read new messages                            | Old schema cannot deserialize new messages               | When producers deploy before consumers.      |
| `FULL`       | Both backward AND forward                                   | Either backward or forward check fails                   | Strictest. Only optional fields with defaults.|
| `NONE`       | No checks                                                   | Never rejects                                            | Dev/test only. Never in production.          |

**How CI/CD enforces this:**

In your `pom.xml` pipeline, before any merge to main, run:

```bash
mvn io.confluent:kafka-schema-registry-maven-plugin:test-compatibility \
  -Dregistry.url=https://schema-registry.internal:8081 \
  -Dschema.registry.url=https://schema-registry.internal:8081
```

This command fetches the currently registered schema for your subject, checks your
proposed schema against it, and fails the build if compatibility is violated. Zero
breaking changes reach the cluster. This is the L6 answer: "schema compatibility is
enforced in CI, not discovered at runtime."

---

### Expand-Contract for Breaking Changes

Sometimes a breaking change is genuinely necessary. A field is named `amt` by accident
and needs to be `amount`. You cannot rename in place — that breaks all consumers
simultaneously. Instead you use the **expand-contract** pattern, which spreads the
breaking change across three phases spanning weeks:

```
Phase 1: EXPAND
+------------------+        +---------------------+
| Producer (old)   |        | Consumer (updated)  |
|                  |        |                     |
| Writes:          |        | Reads BOTH:         |
|   amt: 99.0      +------> |   if amount != null |
|   amount: 99.0   |        |     use amount      |
|   (both fields)  |        |   else use amt      |
+------------------+        +---------------------+

Phase 2: MIGRATE
+------------------+        +---------------------+
| Producer (new)   |        | Consumer (stable)   |
|                  |        |                     |
| Writes:          +------> | Reads BOTH fields   |
|   amount: 99.0   |        | (still safe)        |
|   (only new)     |        |                     |
+------------------+        +---------------------+

Phase 3: CONTRACT
+------------------+        +---------------------+
| Producer (clean) |        | Consumer (clean)    |
|                  |        |                     |
| Writes:          +------> | Reads:              |
|   amount: 99.0   |        |   amount: 99.0      |
|   (only new)     |        |   (only new)        |
+------------------+        +---------------------+
```

Each phase requires time for all consumers across all teams to deploy. In a large
organization like Airbnb or LinkedIn — where a single Kafka topic has 40 consumers
from 15 teams — "phase 2 to phase 3" may take six weeks. The old field sits in every
event for six weeks, wasting bytes. That is the real cost of a poorly named field in
a high-throughput system.

---

## Section 2: Kafka and Microservices — Design Patterns Deep Dive

### Event Notification vs. Event-Carried State Transfer

Think of two ways your friend can invite you to a party. Method one: "I'm having a
party, check my Instagram for details." You have to go look it up. Method two: "I'm
having a party, here's the address, time, dress code, and menu." Everything is in the
message.

Kafka supports both. Choosing between them is an L6 design decision, not an L5 one.

**Event Notification (the Instagram approach):**

```json
{
  "type": "ORDER_PLACED",
  "order_id": "abc123",
  "occurred_at": "2025-06-14T10:30:00Z"
}
```

The consumer reads this and calls the Order Service REST API to fetch the full order:

```
+----------+     event      +----------+     GET /orders/abc123    +--------------+
| Producer +--------------> | Consumer +-------------------------> | Order Service|
|          |                |          | <------------------------ |              |
+----------+                +----------+    {full order details}   +--------------+
```

**Pros:** Small events, always fetches the latest data from the source of truth.

**Cons:** Consumer is coupled to Order Service. At 50,000 events/second, you have
50,000 HTTP calls per second against Order Service. One Order Service outage takes
down every downstream consumer.

**Event-Carried State Transfer (the complete invitation):**

```json
{
  "type": "ORDER_PLACED",
  "order_id": "abc123",
  "user_id": "456",
  "items": [
    { "sku": "SHOE-42", "quantity": 2, "unit_price": 49.99 }
  ],
  "total": 99.98,
  "shipping_address": {
    "street": "123 Main St",
    "city": "Denver",
    "zip": "80201"
  },
  "occurred_at": "2025-06-14T10:30:00Z"
}
```

```
+----------+     event (complete)      +----------+
| Producer +--------------------------> | Consumer |
|          |                           | processes|
+----------+                           | inline,  |
                                       | no calls |
                                       +----------+
```

**Pros:** Consumer is fully decoupled. No downstream HTTP calls. Consumer works even
if Order Service is down for an hour.

**Cons:** Events are large (network and storage cost). Data may be slightly stale —
the shipping address in the event was captured at order time; if the user changed it
two seconds later, the consumer has the old one. Also: **PII travels through Kafka
brokers**, which may violate your data governance policy.

**The L6 rule:** use event-carried state transfer when consumers are latency-sensitive
and need to process without blocking on external calls. Use event notification when
data freshness is critical and the downstream service SLA is acceptable.

---

### The Downstream Data Model Pattern

This is the most important architectural pattern for microservices using Kafka that
most L5 candidates do not know by name.

**The problem:**

The Inventory Service needs to route stock to the warehouse closest to the customer.
To do that, it needs the customer's shipping region. But shipping region lives in the
User Service. What does Inventory Service do?

**Option A (wrong at L6):** Inventory Service calls User Service API on every event.
Now Inventory Service is coupled to User Service. If User Service has a 50ms p99
latency spike, every inventory allocation is delayed. Classic synchronous coupling
hidden behind an async facade.

**Option B — The Downstream Data Model:**

```
"user-region-updated" topic
         |
         v
+------------------+
| Inventory Service|
|                  |   Maintains its OWN local table:
|  users_regions   |   user_id | region | updated_at
|  (read-only copy)|   456     | WEST   | 2025-06-13
|                  |   789     | EAST   | 2025-06-14
+------------------+
         ^
         |
When ORDER_PLACED event arrives:
  1. Look up user 456 in LOCAL table (microseconds, no network)
  2. Route stock to WEST warehouse
  3. Done. No User Service call.
```

The Inventory Service subscribes to `users.identity.profile.updated.v1` topic. Every
time a user changes their shipping region, the event flows to Inventory Service, which
updates its own internal table. The data is eventually consistent — there is a small
window where the local copy is stale. That is acceptable because the routing decision
is best-effort anyway.

**The L6 articulation:** "Each service owns the data it needs to fulfill its
responsibilities. For data that originates in another service's domain, we maintain a
local read model built from events. We accept eventual consistency in exchange for
zero runtime coupling to that service."

This is the **downstream data model** pattern — a read-only, service-specific
projection of another service's data, kept fresh via Kafka events.

---

### Consumer Idempotency Patterns (Extended)

Kafka guarantees at-least-once delivery by default. Your consumer will receive
duplicate messages during rebalances and crashes. Every consumer must be idempotent.
Here are the four concrete patterns with SQL:

**Pattern 1 — Natural Idempotency (prefer this when possible):**

SET operations are naturally idempotent. INCREMENT is not.

```sql
-- IDEMPOTENT: run 10 times, result is the same
UPDATE users SET email = 'new@example.com' WHERE user_id = '456';

-- NOT IDEMPOTENT: run 10 times, counter is 10x too high
UPDATE users SET order_count = order_count + 1 WHERE user_id = '456';
```

Design your events to carry the final desired state, not a delta.
`email.changed` event carries the new email value, not "+1 to email count."

**Pattern 2 — Deduplication Table:**

```sql
CREATE TABLE processed_events (
    event_id   UUID        PRIMARY KEY,
    processed_at TIMESTAMPTZ DEFAULT now()
);

-- In your consumer, wrap processing in a transaction:
BEGIN;
  INSERT INTO processed_events (event_id)
  VALUES ('evt-abc-123')
  ON CONFLICT (event_id) DO NOTHING;

  -- Check if insert actually happened:
  -- If 0 rows inserted: already processed, skip.
  -- If 1 row inserted: new event, process it.

  UPDATE orders SET status = 'CONFIRMED' WHERE order_id = 'abc';
COMMIT;
```

`ON CONFLICT DO NOTHING` makes the entire operation idempotent. A redelivered event
hits the PRIMARY KEY constraint and silently skips. Shopify uses this pattern at
scale for their order processing consumers.

**Pattern 3 — Conditional Update:**

```sql
-- Only update if the current state is what we expect
UPDATE orders
SET status = 'CONFIRMED'
WHERE order_id = 'abc'
  AND status = 'PENDING';
-- If already CONFIRMED: 0 rows affected. Idempotent.
-- If PENDING: 1 row affected. Processed.
```

No separate table needed. The business state itself acts as the idempotency guard.
Works when state transitions are strictly ordered.

**Pattern 4 — Version-Based Updates:**

Events carry an explicit version number. The database row stores the current version.

```sql
-- Event payload: { order_id: "abc", status: "CONFIRMED", version: 7 }
-- Database row:  order_id='abc', status='PENDING', version=6

UPDATE orders
SET status = 'CONFIRMED', version = 7
WHERE order_id = 'abc'
  AND version = 6;
-- Success: version 6 row updated to version 7.

-- Event redelivered (version 7 again):
UPDATE orders
SET status = 'CONFIRMED', version = 7
WHERE order_id = 'abc'
  AND version = 6;  -- <-- row is now version 7, condition fails
-- 0 rows affected. Idempotent.
```

Version-based updates are the most robust pattern. They handle out-of-order delivery
naturally — an older event (version 5) arriving after a newer event (version 7) cannot
overwrite the newer state because the `AND version = 6` condition would not match
version 7 either.

---

## Section 3: Kafka for Analytics — Lambda and Kappa Architectures

### Lambda Architecture (Two Systems, One Answer)

Nathan Marz coined **Lambda architecture** in 2011 while building Twitter's analytics
pipeline. The problem: streaming systems are fast but approximate. Batch systems are
accurate but slow. Can you have both?

Lambda says: run both simultaneously and merge the results.

```
Raw Events (Kafka)
        |
        +------------------+-------------------+
        |                                      |
        v                                      v
+---------------+                    +------------------+
| BATCH LAYER   |                    | SPEED LAYER      |
| Spark on HDFS |                    | Kafka Streams    |
| Runs: nightly |                    | Runs: real-time  |
| Produces:     |                    | Produces:        |
| accurate      |                    | approximate      |
| historical    |                    | current results  |
| results       |                    | (last few hours) |
+---------------+                    +------------------+
        |                                      |
        v                                      v
+-----------------------------------------------------+
| SERVING LAYER                                       |
| Merges: batch results (yesterday and older)         |
|       + speed layer delta (last few hours)          |
| Result: full historical view with current tail      |
+-----------------------------------------------------+
        |
        v
  Dashboard / API
```

**Why Lambda eventually became painful:**

Two codebases. Two data pipelines. Two sets of monitoring. The same business logic —
"count orders by region" — is implemented twice: once in Spark (Scala), once in
Kafka Streams (Java). When the logic changes (add a new filter for cancelled orders),
you update both. They drift. The batch result and stream result disagree. You spend
three days debugging which one is wrong.

LinkedIn built and eventually moved away from Lambda for exactly this reason.

---

### Kappa Architecture (One System, One Answer)

Jay Kreps (co-creator of Kafka, later co-founder of Confluent) published his critique
of Lambda in 2014. His insight: the only reason Lambda had a batch layer was that
stream processing was not powerful enough to reprocess historical data at scale. Kafka
changed that — you can replay a topic from offset 0.

**Kappa architecture:**

```
Raw Events (Kafka, long retention)
        |
        v
+---------------------------+
| STREAM PROCESSING LAYER   |
| Apache Flink or Kafka     |
| Streams                   |
|                           |
| ONE codebase              |
| ONE pipeline              |
+---------------------------+
        |
        v
  Results (real-time + historical replay)
```

**Reprocessing in Kappa (the "batch equivalent"):**

```
Step 1: Deploy new version of streaming job (v2)
Step 2: Start v2 from offset 0 on the raw events topic
Step 3: v2 writes to a NEW output topic (results-v2)
Step 4: Once v2 catches up to real-time, cut dashboards over to results-v2
Step 5: Decommission v1 job and results-v1
```

One codebase handles both real-time ingestion and historical reprocessing. The only
infrastructure is Kafka plus Flink. Uber, Lyft, and Cloudflare adopted Kappa for
their analytics pipelines.

**When Kappa does not work well:**

Machine learning training jobs require full dataset scans with random access patterns,
complex feature engineering, and joins across years of data. Streaming reprocessing
of 10 TB through a Flink job is slow and expensive compared to Spark reading from
columnar Parquet files on S3. For ML training, a hybrid — Kappa for operational
metrics, batch for feature engineering — is the pragmatic L6 answer.

---

### Real-Time Analytics at Uber: Pinot and Kafka

**Apache Pinot** is a real-time OLAP (Online Analytical Processing) database designed
by LinkedIn and heavily used at Uber. It ingests from Kafka and answers SQL queries
in under one second on datasets with billions of rows.

**The architecture at Uber:**

```
Driver/Rider App
      |
      v
Kafka Topic: "trip-events"
  - partition key: city_id
  - 1M+ events/second
      |
      v
+------------------+
| Pinot Real-Time  |
| Ingestion        |
| (aligned to      |
| Kafka partitions)|
+------------------+
      |
      v
Pinot Tables (columnar, indexed)
      |
      v
SQL queries from:
  - Surge pricing engine: "avg trip demand, last 5 min, by city"
  - Driver supply dashboard: "active drivers by city right now"
  - Operations: "p99 trip duration, by city, last hour"
```

**Why Pinot is not just ElasticSearch or PostgreSQL:**

- Pinot ingests directly from Kafka partitions in real-time with sub-second latency.
- Pinot tables are partitioned by the same key as the Kafka topic (`city_id`).
  This means each Pinot server handles the same partitions it ingests — no shuffle
  on join queries. A query for "city 42" goes directly to the server holding
  city 42's data.
- Pinot uses columnar storage with inverted indexes. A query scanning 100M rows for
  a single city returns in 200ms.

**Scale at Uber:** 100TB+ of data in Pinot. Sub-second query latency at p99.
Ingestion rate: over 1 million events per second. The surge pricing calculation that
determines whether you pay 2.1x or 1.8x for your ride is running on Pinot.

---

## Section 4: Exactly-Once Deep Dive — Transaction Mechanics

### How Kafka Transactions Actually Work

Kafka transactions were added in version 0.11. Most engineers know they exist.
L6 candidates know the mechanics.

The foundation is the **Transaction Coordinator** — a special broker partition
(the `__transaction_state` internal topic) that manages transaction state.

**Setup: the transactional producer registers itself:**

When a producer starts with `transactional.id = "payment-processor-1"`, the broker
assigns it a stable `producerId` and a `producerEpoch`. Even if the producer crashes
and restarts, its `transactional.id` maps back to the same `producerId`. This lets
the broker detect zombie producers (old epoch) and reject their writes.

**The full transaction flow:**

```java
producer.initTransactions();              // Register with Transaction Coordinator
                                          // Coordinator: "I know payment-processor-1"

producer.beginTransaction();              // Coordinator: mark transaction OPEN

producer.send("payments", paymentEvent); // Write to partition payments-3
producer.send("audit-log", auditEvent);  // Write to partition audit-log-1

producer.sendOffsetsToTransaction(       // Atomically include consumer offset commit
    Map.of(topicPartition, offsetMeta),  // in the transaction
    consumerGroupMetadata
);

producer.commitTransaction();            // Coordinator: mark transaction COMMITTED
                                         // Broadcasts COMMITTED marker to:
                                         //   payments-3, audit-log-1, consumer offsets
```

**What consumers see depends on isolation level:**

```
isolation.level = read_committed (set on your consumer):
  - Only reads messages that are part of COMMITTED transactions
  - Never sees messages from aborted or in-progress transactions
  - This is what "exactly-once" consumers use

isolation.level = read_uncommitted (default):
  - Reads all messages, including those from aborted transactions
  - Faster, but may see "ghost" writes that were later aborted
```

---

### ASCII Transaction Flow: Commit and Abort

**Commit path (happy path):**

```
Producer          Transaction Coordinator      Partition Leaders (P0, P1)
   |                       |                         |
   |--initTransactions()--> |                         |
   |<--producerEpoch=5------|                         |
   |                       |                         |
   |--beginTransaction()--> |                         |
   |                       | mark OPEN               |
   |                       |                         |
   |--send(P0, msg1)-------------------------------> | (write, uncommitted)
   |--send(P1, msg2)-------------------------------> | (write, uncommitted)
   |                       |                         |
   |--commitTransaction()-> |                         |
   |                       | write COMMITTED marker ->|
   |                       |                         | (now visible to read_committed)
   |<--success-------------|                         |
```

**Abort path (producer crashes before commit):**

```
Producer          Transaction Coordinator      Partition Leaders (P0, P1)
   |                       |                         |
   |--send(P0, msg1)-------------------------------> | (write, uncommitted)
   |   [CRASH]             |                         |
   |                       |                         |
   |  [new producer        |                         |
   |   epoch=6 starts]     |                         |
   |--initTransactions()--> |                         |
   |                       | detects OPEN txn from   |
   |                       | epoch=5. Writes ABORT ->|
   |                       |                         | (P0 msg1 marked ABORTED)
   |                       |                         |
   [read_committed consumer never sees P0 msg1]
```

The key insight: the Transaction Coordinator handles recovery. The new producer
instance asks the coordinator to catch up, and the coordinator finds the incomplete
old transaction and aborts it. No manual intervention. No dangling writes.

---

### The 2-Broker Failure Gotcha

This is an operational detail that separates engineers who have run Kafka in
production from those who have not.

**Setup:** cluster with 3 brokers, `replication.factor=3`, `min.insync.replicas=2`.

This means: a write is acknowledged only when at least 2 of the 3 replicas have
confirmed it. This prevents data loss — you can lose 1 broker and still have 2
copies of every message.

**What happens when 2 brokers fail simultaneously:**

```
+--------+  +--------+  +--------+
|Broker 1|  |Broker 2|  |Broker 3|
|  [UP]  |  | [DOWN] |  | [DOWN] |
+--------+  +--------+  +--------+
    |
    | Producer tries to write
    |
    v
NotEnoughReplicasException
(only 1 ISR, need 2)
Write rejected. Producer must retry or handle error.
```

**The Transaction Coordinator is also a partition leader.** If the broker hosting
the coordinator goes down mid-transaction, the transaction is in an ambiguous state
until a new coordinator leader is elected (15–30 seconds for controlled failover).
During that window, all transactional producers block.

**Production recommendation at L6:** Run 5 brokers. With 5 brokers and
`replication.factor=3`, you can lose 2 brokers without losing the transaction
coordinator or any partition. The coordinator failover is automatic, but 15–30 seconds
of producer blocking in a payment pipeline is unacceptable — design for it by either
using 5+ brokers or accepting that the transaction coordinator is a SPOF during
failover windows.

---

## Section 5: Kafka Connect — Standardizing Integration

### What Is Kafka Connect and Why It Matters

Writing a custom Kafka producer to pull data from PostgreSQL seems simple until you
hit: SSL certificate rotation, connection pool exhaustion at 3 AM, schema changes
breaking your hardcoded field list, restart logic after broker outages, and consumer
lag alerting. Every team writes this code. Every team writes it slightly differently.
Every team debugs it on their own.

**Kafka Connect** solves this. It is a framework — and an ecosystem of pre-built
**connectors** — that standardizes how data moves in and out of Kafka. You write a
JSON configuration file. Connect handles the rest.

```
+----------------+     Source Connector    +-------+    Sink Connector    +--------------+
| PostgreSQL DB  +-----------------------> | Kafka +-------------------> | BigQuery     |
| (Debezium CDC) |                         |       |                     | (GCS + BQ    |
+----------------+                         +-------+                     |  connector)  |
                                                                         +--------------+
                                                                         +--------------+
                                           +-------+    Sink Connector  -> | Elasticsearch|
                                           | Kafka +-------------------> | (search index|
                                           +-------+                     |  connector)  |
                                                                         +--------------+
```

- **Source connectors** pull data INTO Kafka: Debezium (PostgreSQL CDC), S3 files,
  REST API polling, JDBC bulk loads.
- **Sink connectors** push data FROM Kafka: Elasticsearch, BigQuery, S3 Parquet,
  JDBC, Snowflake, Redis.

---

### Kafka Connect Architecture

```
+-----------------------------------------------+
|            Kafka Connect Cluster               |
|                                               |
|  +----------+  +----------+  +----------+    |
|  | Worker 1 |  | Worker 2 |  | Worker 3 |    |
|  |          |  |          |  |          |    |
|  | Task 1   |  | Task 3   |  | Task 5   |    |
|  | Task 2   |  | Task 4   |  | Task 6   |    |
|  +----------+  +----------+  +----------+    |
|                                               |
|  Internal Kafka topics:                       |
|    connect-configs   (connector configs)      |
|    connect-offsets   (source read positions)  |
|    connect-status    (task health)            |
+-----------------------------------------------+
```

- **Workers** are JVM processes. They scale horizontally — add more workers to
  handle more connectors.
- **Tasks** are the unit of parallelism within a connector. A Debezium connector
  reading from a 10-partition table may spawn 10 tasks, one per partition.
- **State is stored in Kafka itself.** If a worker dies, another worker reads the
  state from `connect-offsets` and resumes from exactly where the dead worker left
  off. No data loss. No duplicate reads (at-least-once, or exactly-once with
  transactional sinks).

---

### Debezium PostgreSQL Source Connector Config

Debezium is the most widely used CDC (Change Data Capture) connector. It reads the
PostgreSQL **write-ahead log (WAL)** — the same log the database uses for replication
— and emits every INSERT, UPDATE, and DELETE as a Kafka event.

```json
{
  "name": "postgres-users-connector",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "database.hostname": "postgres-prod.internal",
    "database.port": "5432",
    "database.user": "debezium",
    "database.password": "${file:/secrets/debezium.properties:password}",
    "database.dbname": "app_db",
    "table.include.list": "public.users,public.orders",
    "topic.prefix": "cdc",
    "plugin.name": "pgoutput"
  }
}
```

- `table.include.list`: only capture changes from these tables. Others are ignored.
- `topic.prefix`: creates topics named `cdc.public.users` and `cdc.public.orders`.
- `plugin.name: pgoutput`: uses PostgreSQL's built-in logical replication output
  plugin. No extra PostgreSQL extensions required.
- `${file:/secrets/...}`: password is externalized. Never hardcode credentials in
  Connect configs, which are stored in the `connect-configs` Kafka topic (readable by
  anyone with cluster access).

**Result:** every row change in `public.users` appears in `cdc.public.users` within
milliseconds of the database commit. Zero custom producer code. Zero polling queries
against the production database.

---

### The Kafka Connect Reliability Model

**Dead Letter Queue (DLQ) for sink connectors:**

When a sink connector fails to write a record — malformed data, schema mismatch,
downstream timeout — it can be configured to route that record to a DLQ topic instead
of crashing the entire task.

```
Kafka Topic (source)
      |
      v
+------------------+
| Elasticsearch    |
| Sink Connector   |
|                  |
| Record fails:    |
|  "malformed JSON"|
+--------+---------+
         |
         v (instead of crashing)
+------------------+
| DLQ Topic:       |
| elasticsearch-   |
| sink-dlq         |
|                  |
| Contains:        |
| - original record|
| - error message  |
| - stack trace    |
+------------------+
         |
         v
  Separate consumer
  (alerts on-call,
   or retries after
   manual fix)
```

**Schema evolution with Debezium + Schema Registry:** When you add a column to the
PostgreSQL table, Debezium detects the schema change in the WAL, registers the new
Avro schema with Schema Registry (subject: `cdc.public.users-value`), and starts
emitting events with the new schema. If the new schema is not compatible with the
registered one, the connector pauses and alerts — no silent breakage.

---

## Section 6: Kafka in Multi-Tenant Environments

### The Isolation Problem

Imagine 50 engineering teams at a company like Stripe sharing a single Kafka cluster.
Team A (machine learning) writes a training data pipeline that accidentally sends
10 GB/second of feature vectors into their topic. The broker's network card is
saturated. Team B's payment confirmation consumer, sitting on the same broker, starts
falling behind. Payments lag. SLA is breached. This is the **noisy neighbor problem.**

Without quotas, Kafka has no built-in protection. One misconfigured producer can
degrade the entire cluster.

---

### Kafka Quotas

Kafka quotas are applied per `client.id` or per authenticated user (mTLS principal).

**Set a producer throughput quota:**

```bash
kafka-configs.sh \
  --bootstrap-server kafka:9092 \
  --alter \
  --add-config 'producer_byte_rate=1048576' \
  --entity-type clients \
  --entity-name analytics-producer
```

`producer_byte_rate=1048576` means 1 MB/second maximum produce throughput for
`analytics-producer`. If it tries to send faster, the broker throttles it by
delaying the response (it does NOT disconnect the client). The client sees higher
latency and backs off.

**Consumer quota:**

Controls how fast a consumer can read from brokers. Useful to prevent a bulk
backfill job from saturating broker disk I/O and starving real-time consumers.

```bash
kafka-configs.sh \
  --bootstrap-server kafka:9092 \
  --alter \
  --add-config 'consumer_byte_rate=5242880' \
  --entity-type clients \
  --entity-name backfill-consumer
```

5 MB/second read limit. The real-time consumer (no quota set) reads at full speed.
The backfill consumer is throttled.

**Request rate quota:**

```bash
--add-config 'request_percentage=25'
```

Limits a client to 25% of the broker's request handler thread time. Prevents
a client issuing thousands of metadata or admin API calls per second.

---

### Topic Naming Conventions for Multi-Tenant

In a multi-tenant cluster, ad hoc topic names like `orders`, `events`, `data` cause
conflicts and make it impossible to determine ownership. The L6 standard:

```
{domain}.{team}.{entity}.{event-type}.{version}
```

**Examples:**

| Topic Name                                       | Domain    | Team        | Entity   | Event Type  | Version |
|--------------------------------------------------|-----------|-------------|----------|-------------|---------|
| `payments.billing.invoice.created.v1`            | payments  | billing     | invoice  | created     | v1      |
| `users.identity.profile.updated.v2`              | users     | identity    | profile  | updated     | v2      |
| `logistics.fulfillment.shipment.dispatched.v1`   | logistics | fulfillment | shipment | dispatched  | v1      |

**Benefits:**
- Ownership is immediately clear from the topic name alone.
- Wildcard ACLs: `payments.*` grants the payments team access to all their topics.
- Schema versioning in the name means consumers can subscribe to `v1` and `v2`
  separately while a migration is in progress — no need to coordinate a cutover.
- Discoverability: searching for all `created` events across the company is a grep
  on topic names.

---

### Kafka ACL Enforcement in Multi-Tenant

Each team gets a service account authenticated via **mTLS (mutual TLS)**. The
certificate contains the team identity as the Common Name:

```
CN=payments-team, OU=engineering, O=example.com
```

ACLs are set at the topic pattern level:

```bash
# payments-team can PRODUCE to any payments.* topic
kafka-acls.sh --add \
  --allow-principal User:CN=payments-team \
  --operation Write \
  --topic 'payments.' \
  --resource-pattern-type prefixed

# payments-team can CONSUME from any payments.* topic
kafka-acls.sh --add \
  --allow-principal User:CN=payments-team \
  --operation Read \
  --topic 'payments.' \
  --resource-pattern-type prefixed

# payments-team explicitly granted READ access to user profile events
kafka-acls.sh --add \
  --allow-principal User:CN=payments-team \
  --operation Read \
  --topic 'users.identity.profile.updated.v2'
```

```
payments-team (CN=payments-team)
        |
        +---> WRITE: payments.billing.invoice.created.v1   [allowed]
        +---> READ:  payments.billing.invoice.created.v1   [allowed]
        +---> READ:  users.identity.profile.updated.v2     [explicitly granted]
        +---> WRITE: users.identity.profile.updated.v2     [DENIED]
        +---> READ:  logistics.fulfillment.shipment.*      [DENIED]
```

The payments team can read user profile events (a cross-team data dependency) but
cannot write to user topics. They cannot read logistics data. All access is explicit
and auditable. No team can access another team's data without an explicit ACL grant,
which requires a code review approval from the owning team.

---

## Section 7: Operational Runbooks

### Runbook: High Consumer Lag

Consumer lag is the number of messages in a topic that have been written but not yet
consumed. A lag of zero means the consumer is keeping up. A growing lag means the
consumer is falling behind. Left unchecked, lag means delayed processing, missed SLAs,
and cascading failures.

**Step 1 — Diagnose current lag across all partitions:**

```bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group my-consumer-group
```

Output:

```
GROUP           TOPIC     PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
my-group        orders    0          150000           150500          500
my-group        orders    1          149000           155000          6000   <-- high
my-group        orders    2          151000           151200          200
```

Partition 1 has 6,000 messages of lag. That is where to focus.

**Step 2 — Check consumer logs for errors:**

If the consumer is throwing exceptions (database connection lost, downstream timeout),
fix the root cause first. Adding more consumers does not help if they all crash on
the same bad message.

**Step 3 — Check downstream dependencies:**

If the consumer writes to PostgreSQL and PostgreSQL p99 write latency jumped from 2ms
to 200ms, the consumer's throughput dropped 100x. Fix the database problem first.

**Step 4 — If the consumer is healthy but slow, scale out:**

Consumer group scaling rule: you can have at most as many active consumer instances
as there are partitions. If the `orders` topic has 12 partitions and you have 4
consumer instances, each instance handles 3 partitions. Scale to 12 instances to
process all partitions in parallel.

```bash
kubectl scale deployment orders-consumer --replicas=12
```

**Step 5 — If already at max consumers (instances = partitions):**

The bottleneck is per-message processing time. Options:
- Profile the consumer code and optimize the hot path.
- Batch database writes (insert 100 rows at once instead of one row per message).
- Move slow processing to a separate async thread pool within the consumer.

**SLA:** if lag exceeds 50,000 messages for more than 10 minutes, escalate to the
on-call lead. At 50,000 messages with a typical processing rate of 1,000 messages/sec
per consumer, you are 50 seconds behind. For a real-time payment confirmation system,
that is a customer-visible failure.

---

### Runbook: Broker Failure

A Kafka broker going offline is a routine operational event, not an emergency —
if your cluster is configured correctly.

**Immediate automated response (no human action needed):**

The Kafka controller (a special broker role, auto-elected via ZooKeeper or KRaft)
detects a broker failure within 10 seconds via missed heartbeats. It immediately
promotes a follower from the ISR (In-Sync Replicas) to become the new leader for
each partition the dead broker led.

Producers and consumers reconnect to the new partition leaders automatically using
metadata refresh.

**Step 1 — Confirm recovery is in progress:**

```bash
kafka-topics.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --under-replicated-partitions
```

Under-replicated partitions: partitions that do not have their full replica count.
This is expected immediately after a broker failure. The number should decrease
as the replacement broker catches up.

**Step 2 — If under-replicated count is not decreasing:**

The dead broker may be needed as a replica. If it cannot be restarted, replace it
with a new broker on a new machine with the same `broker.id`. The cluster will
begin moving replicas automatically.

**Step 3 — Rebalance leader distribution:**

After recovery, partition leaders may all be on the original broker once it comes
back, leaving the replacement broker underutilized. Rebalance:

```bash
kafka-preferred-replica-election.sh \
  --bootstrap-server kafka:9092
```

Or with newer Kafka versions, enable automatic leader rebalance:
`auto.leader.rebalance.enable=true` (set in broker config).

**Step 4 — Confirm recovery:**

```bash
kafka-topics.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --under-replicated-partitions
# Should return 0 results within 30 minutes of recovery
```

**What failure is actually dangerous:** if two brokers fail simultaneously on a
cluster with `replication.factor=2`. You have zero replicas for some partitions.
Data is lost. This is why production clusters use `replication.factor=3` and run
at minimum 5 brokers.

---

### Runbook: Consumer Group Rebalancing Stuck

A **rebalance** is Kafka's process of reassigning partitions when a consumer joins
or leaves a group. Normal rebalances complete in seconds. A stuck rebalance —
staying in `PREPARING_REBALANCE` or `COMPLETING_REBALANCE` for more than five
minutes — means all consumers in the group are paused. No messages are processed
during a rebalance.

**Symptom:**

```bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group my-consumer-group

State: PREPARING_REBALANCE (for 7 minutes)
```

**Cause:** One consumer instance is connected to the group coordinator (sending
heartbeats) but is not calling `poll()` fast enough. It has not responded to the
rebalance join request within `max.poll.interval.ms` (default: 5 minutes).

Why would a consumer stop polling? Heavy processing of a single message, a deadlock
inside processing logic, a long-running synchronous database call, or a full garbage
collection pause (JVM stop-the-world GC lasting minutes on a heap with too little
tuning).

**Step 1 — Identify the offending consumer instance:**

Search consumer logs for:
```
Heartbeat session expired for member <instance-id>
```
or
```
poll() was not called within the configured max.poll.interval.ms
```

**Step 2 — Restart that specific instance:**

```bash
kubectl delete pod orders-consumer-7d4b8c9f6-xyz99
# Kubernetes immediately reschedules a replacement pod
```

Restarting the stuck consumer triggers the group coordinator to remove it from the
group. With the stuck member gone, the rebalance completes immediately.

**Step 3 — Prevent recurrence:**

```yaml
# Kafka consumer config (application.properties or similar)
max.poll.records=50            # Was 500. Fewer records = faster poll() loop.
max.poll.interval.ms=300000    # 5 minutes. Increase if processing legitimately slow.
```

Reducing `max.poll.records` means each poll call gets fewer records, so the consumer
processes them faster and calls poll() again sooner — well within the timeout.

For slow downstream dependencies (database writes taking 2–3 seconds per message),
move the processing to an async thread pool and have the main thread poll continuously
while background threads process. The Kafka thread never blocks; the poll() interval
is always respected.

---

## Summary: What L6 Answers Look Like

| Topic                    | L5 Answer                                  | L6 Answer                                                                 |
|--------------------------|--------------------------------------------|---------------------------------------------------------------------------|
| Schema changes           | "Use schema registry"                      | Compatibility modes, expand-contract, CI enforcement with maven plugin    |
| Event design             | "Put data in events"                       | Notification vs. state transfer trade-offs, PII implications, stale data  |
| Idempotency              | "Check if already processed"               | Deduplication table, conditional update, version-based update patterns    |
| Analytics architecture   | "Use Kafka Streams"                        | Lambda vs. Kappa, reprocessing mechanics, Pinot for sub-second OLAP       |
| Exactly-once             | "Set acks=all and enable idempotence"      | Transaction coordinator mechanics, isolation levels, zombie fencing       |
| Multi-tenancy            | "Use separate topics per team"             | Naming conventions, quota enforcement, ACL patterns, mTLS per team        |
| Operations               | "Monitor consumer lag"                     | Specific runbooks: lag → scale vs. fix, broker failure sequence, stuck rebalance |

The pattern: L5 knows what. L6 knows why, knows the failure modes, and has a runbook
ready before the incident happens.
# Chapter 33 — Supplement B: Kafka Applied System Design, Scale, and Cost

## What This Supplement Covers

The main Chapter 33 built your mental model of how Kafka works — topics, partitions, consumer groups, offsets, replication, and stream processing. This supplement is different. It throws you into the deep end of real system design problems:

- Build a real-time order tracking system like DoorDash, end-to-end
- Learn when Kafka is the wrong choice (and what to pick instead)
- See how LinkedIn, Airbnb, and Netflix actually run Kafka at massive scale
- Calculate the real dollar cost of a Kafka deployment
- Understand how ML pipelines use Kafka for live feature computation
- Run chaos engineering to find hidden failure modes before they hit production

Every topic here is new material, building on Chapter 33's fundamentals. Treat this like the Staff-level interview: you will be expected to say *why* you chose Kafka, *how* you'd size it, and *what it costs*.

---

## 1. End-to-End System Design: Real-Time Order Tracking

### The Problem

Imagine you are designing the backend for a food delivery company — call it FoodRush. Scale:

- 10 million orders per day, across US, Canada, and EU
- Customers see a live map and status string: "Restaurant is preparing your food"
- Status moves: **placed → accepted → preparing → picked_up → delivered**
- Courier GPS pings every 5 seconds (so you know exactly where the driver is)
- Restaurant app and courier app each need push notifications when status changes
- Analytics team needs average delivery time, restaurant acceptance rate, courier efficiency

This is not a toy problem. At 10 million orders per day that is ~116 orders per second on average, with spikes 5–10× that at lunch and dinner. Courier GPS at 5-second intervals across, say, 100,000 active couriers at peak means 20,000 GPS events per second. This is a streaming system whether you like it or not.

### Event Taxonomy

Before drawing any boxes, nail down your events. In Kafka, events are your API. Every field matters because changing a field later breaks consumers.

**Event 1: order.placed**
```
Key:  order_id   (e.g., "ord-28371623")
Data: {
  order_id:      string,
  customer_id:   string,
  restaurant_id: string,
  courier_id:    null,              // not assigned yet
  items:         [{item_id, qty, price}],
  delivery_addr: {lat, lng, street},
  placed_at:     ISO8601 timestamp,
  country:       "US" | "CA" | "EU"
}
```

**Event 2: order.restaurant_accepted**
```
Key:  order_id
Data: {
  order_id:            string,
  restaurant_id:       string,
  estimated_ready_at:  ISO8601,
  accepted_at:         ISO8601
}
```

**Event 3: order.courier_assigned**
```
Key:  order_id
Data: {
  order_id:   string,
  courier_id: string,
  eta_seconds: int,
  assigned_at: ISO8601
}
```

**Event 4: courier.location_updated**
```
Key:  courier_id   (NOT order_id — see why below)
Data: {
  courier_id: string,
  lat:        float,
  lng:        float,
  speed_kmh:  float,
  timestamp:  ISO8601
}
```

Why is the key `courier_id` and not `order_id`? Because a courier's GPS stream must be totally ordered by courier, not by order. If you key by order_id, two consecutive GPS pings from the same courier could land in different partitions, making ETA calculation impossible without a join.

**Event 5: order.picked_up**
```
Key:  order_id
Data: {
  order_id:    string,
  courier_id:  string,
  picked_up_at: ISO8601
}
```

**Event 6: order.delivered**
```
Key:  order_id
Data: {
  order_id:             string,
  delivered_at:         ISO8601,
  delivery_duration_sec: int    // placed_at to delivered_at
}
```

### Topic Design

You now have six event types. How many topics? Rule of thumb: group events that need the same retention, same consumer access pattern, and same partition count into one topic. Separate events that have fundamentally different characteristics.

**Topic 1: order-lifecycle**
- Contains: order.placed, order.restaurant_accepted, order.courier_assigned, order.picked_up, order.delivered
- Partition key: order_id (all events for one order stay in one partition → easy sequential reads)
- Partitions: 200
- Retention: 30 days
- Replication factor: 3
- Why 200 partitions? At peak 1,000 orders/sec, each partition handles 5 orders/sec — very comfortable.

**Topic 2: courier-locations**
- Contains: courier.location_updated
- Partition key: courier_id
- Partitions: 500 (at peak 100K active couriers, 200 couriers/partition — still manageable)
- Retention: 24 hours (you don't need old GPS pings — only current location matters)
- Log compaction: ON (Kafka keeps only the latest record per key, so you always have each courier's last known position without storing weeks of GPS history)
- Replication factor: 3

**Topic 3: notifications-critical**
- Contains: push notification payloads generated by the notification consumer
- Partitions: 20
- Retention: 1 hour (if a notification is not sent within 1 hour, it is stale)
- Replication factor: 3
- Priority consumer group: low lag SLA < 500ms

**Topic 4: analytics-events**
- Contains: mirror of order-lifecycle + aggregated GPS stats
- Partitions: 100
- Retention: 90 days (analytics needs historical data)
- Replication factor: 2 (analytics jobs can tolerate slightly lower durability to save cost)

### Consumer Architecture

Think of consumer groups as independent pipelines that share the same raw event stream but do completely different things with it.

**Consumer Group 1: tracking-state-updater**
- Reads from: order-lifecycle
- What it does: for each event, updates a Redis HASH with the current order state
- Redis key: `order:{order_id}` → value: `{status, eta, courier_lat, courier_lng, updated_at}`
- Customer-facing tracking API reads from Redis → sub-millisecond response
- At-least-once semantics are fine here: writing the same status update twice is idempotent

**Consumer Group 2: eta-calculator**
- Reads from: courier-locations AND order-lifecycle (stream-stream join)
- What it does: for each in-progress order, continuously updates ETA as the courier moves
- Join logic: "for courier_id X, what order are they currently carrying?" (from order-lifecycle state) → "where is X right now?" (from courier-locations) → compute drive time using maps API → update ETA in Redis
- Window: 30-minute window. If an order is not delivered within 30 minutes, flag it for investigation.
- State store: RocksDB (embedded in Kafka Streams, stores join state locally)

**Consumer Group 3: notification-dispatcher**
- Reads from: order-lifecycle
- What it does: detects status changes → writes push notification payloads to notifications-critical topic
- The push notification sender reads from notifications-critical → calls APNs (Apple) or FCM (Google Android)
- Why two stages? The push sender is an external call with variable latency. Separating it into its own topic means the notification-dispatcher can run at Kafka speed, and the push sender can apply rate limiting and retry logic independently.

**Consumer Group 4: analytics-bridge**
- Reads from: order-lifecycle
- What it does: writes all events into BigQuery for the analytics team
- Batch micro-writes every 10 seconds (not one event at a time — BigQuery streaming insert has per-row overhead)
- Also computes: orders_per_restaurant, avg_delivery_time_per_courier, cancellation_rate — written as pre-aggregated summary events

### Full System Diagram

```
PRODUCERS
+-----------------------+    +-----------------------+    +-----------------------+
|   Restaurant App      |    |   Courier App         |    |   Order Service       |
|  (accepts, ready)     |    |  (GPS pings,          |    |  (places orders,      |
|                       |    |   pickup, delivered)  |    |   assigns couriers)   |
+----------+------------+    +-----------+-----------+    +-----------+-----------+
           |                            |                            |
           |  order.restaurant_accepted |  courier.location_updated  |  order.placed
           |  (key=order_id)            |  (key=courier_id)          |  order.courier_assigned
           v                            v                            v
+----------+----------------------------+----------------------------+-----------+
|                          KAFKA CLUSTER (US-West)                              |
|                                                                               |
|  +---------------------------+   +---------------------------+                |
|  |   order-lifecycle         |   |   courier-locations       |                |
|  |   200 partitions          |   |   500 partitions          |                |
|  |   30-day retention        |   |   24h retention           |                |
|  |   key=order_id            |   |   key=courier_id          |                |
|  |                           |   |   log compaction ON       |                |
|  +---------------------------+   +---------------------------+                |
|                                                                               |
|  +---------------------------+   +---------------------------+                |
|  |   notifications-critical  |   |   analytics-events        |                |
|  |   20 partitions           |   |   100 partitions          |                |
|  |   1h retention            |   |   90-day retention        |                |
|  +---------------------------+   +---------------------------+                |
|                                                                               |
+-------------------------------------------------------------------------------+
           |              |              |                |
           v              v              v                v
+----------+--+  +--------+----+  +-----+--------+  +---+-----------+
| tracking-   |  | eta-        |  | notification |  | analytics-    |
| state-      |  | calculator  |  | dispatcher   |  | bridge        |
| updater     |  | (Streams    |  | (CG3)        |  | (CG4)        |
| (CG1)       |  |  join)      |  |              |  |              |
| (CG2 half)  |  | (CG2)       |  |              |  |              |
+------+------+  +------+------+  +------+-------+  +------+-------+
       |                |                |                  |
       v                v                v                  v
  +----+----+      +----+----+    +------+------+     +----+----+
  |  Redis  |      |  Redis  |    |  Push       |     | BigQuery|
  |  HASH   |      |  ETA    |    |  Sender     |     |         |
  | order:* |      | order:* |    |  (CG5)      |     |         |
  +---------+      +---------+    +------+------+     +---------+
       |                                 |
       v                                 v
  Customer          +--------------------+-------------------+
  Tracking API      |   APNs             |        FCM        |
  (REST/WebSocket)  | (iOS push)         |  (Android push)  |
                    +--------------------+-------------------+
                           |                       |
                           v                       v
                      Customer iOS          Customer Android
                      Restaurant iOS        Restaurant Android
                      Courier iOS           Courier Android
```

### Cross-Country Data Residency (GDPR)

The EU is strict: EU user data must stay in EU infrastructure. This means you cannot mirror EU Kafka data to your US cluster. Here is how you architect this:

```
EU CLUSTER (Frankfurt)                  US-WEST CLUSTER (Oregon)
+---------------------------+           +---------------------------+
|  order-lifecycle-eu       |           |  order-lifecycle-us-ca    |
|  courier-locations-eu     |           |  courier-locations-us-ca  |
|  analytics-events-eu      |           |  analytics-events-us-ca   |
+---------------------------+           +---------------------------+
          |                                         |
          | NO REPLICATION TO US (GDPR)             |
          |                                         | MirrorMaker 2
          v                                         v
   EU Analytics Team                       US-EAST CLUSTER (Virginia)
   EU Push Sender                          (active-passive DR replica)
   EU Redis                                +---------------------------+
                                           |  order-lifecycle-us-ca   |
                                           |  (replica for DR)         |
                                           +---------------------------+
```

The Order Service running in EU only produces to the EU cluster. MirrorMaker 2 runs between US-West and US-East for disaster recovery failover — if US-West goes down, the US-East replica can serve traffic. The EU cluster is completely isolated; no MirrorMaker connects it to any US cluster.

Practical implementation detail: the `country` field in every event lets a single Order Service codebase decide which cluster to publish to at runtime. EU orders go to the EU producer client; US and CA orders go to the US-West producer client.

---

## 2. Kafka vs. Alternatives: When NOT to Use Kafka

Staff-level interviewers love this question: "You said Kafka. Why not RabbitMQ? Why not SQS?" If you can't answer that clearly, you fail regardless of how good the rest of your design is.

### Kafka vs. RabbitMQ

| Dimension | Kafka | RabbitMQ |
|-----------|-------|----------|
| Message retention | Days to weeks (configurable, even forever) | Until consumed or TTL expires |
| Consumer model | Pull, offset-based | Push, ack-based |
| Throughput | 1M+ messages/sec per cluster | 50K–200K messages/sec |
| Replayability | Yes — seek to any offset, any time | No — consumed message is gone |
| Ordering guarantee | Per-partition | Per-queue (single consumer) |
| Routing | Topic-based only | Content-based, header-based, fanout exchanges |
| Primary use case | Event streaming, event sourcing, audit logs | Task queues, work distribution, RPC patterns |
| Ops complexity | High — you manage brokers, ZooKeeper/KRaft | Medium — straightforward single node or cluster |

**When to choose RabbitMQ over Kafka:**
- You need sophisticated routing: "send this message only to queues subscribed to category=sports AND region=EU" — RabbitMQ exchanges do this natively, Kafka cannot.
- Task queue semantics: one worker picks up a task, processes it, acks it, and it disappears. You explicitly do NOT want replay — double-processing a payment is a bug, not a feature.
- Smaller team, simpler ops: RabbitMQ is easier to operate at moderate scale.

**Example:** Stripe's internal job queue for retrying failed webhook deliveries uses task-queue semantics. If a webhook fails, one worker should retry it exactly once (or with backoff). RabbitMQ's ack + dead letter queue pattern fits naturally. Kafka's "all consumers get all messages" model would require extra logic to implement exclusive task assignment.

### Kafka vs. AWS SQS and SNS

| Dimension | Kafka | SQS | SNS |
|-----------|-------|-----|-----|
| Retention | Configurable (days to forever) | 14 days maximum | None — fire-and-forget push |
| Consumer groups | Unlimited | One consumer processes each message | Push to all subscribers simultaneously |
| Replayability | Yes | No | No |
| Throughput | Very high | High (3K/sec standard, unlimited FIFO with higher latency) | High |
| Ops overhead | High — you manage brokers | Zero — fully managed | Zero — fully managed |
| Cost model | Infrastructure cost | Per-message pricing ($0.40/million) | Per-notification pricing |

**When to choose SQS:**
- You are already deep in AWS and do not want another system to operate.
- You have a simple task queue: image resize jobs, email send jobs, report generation.
- You do not need replay — each job is processed once and discarded.
- Your throughput is under 50K messages/sec.

**Example:** Dropbox uses SQS to queue file-processing jobs (thumbnail generation, virus scanning). The job is placed in SQS when a file uploads, a worker picks it up, processes it, deletes it. No replay needed. No multiple consumer groups. SQS is perfect.

### Kafka vs. AWS Kinesis

| Dimension | Kafka | Kinesis |
|-----------|-------|---------|
| Partition / shard limit | No hard limit (grows with cluster) | 10,000 shards per AWS account |
| Retention | Configurable — forever possible | 7 days default, 365 days extended (extra cost) |
| Throughput per shard | 10+ MB/sec | 1 MB/sec write, 2 MB/sec read |
| Consumer model | Pull from broker | Pull (GetRecords) or push (Enhanced Fan-Out) |
| Managed | Self-managed, or Confluent/MSK | Fully managed by AWS |
| Cross-account sharing | Custom (MirrorMaker) | Native cross-account stream sharing |

**When to choose Kinesis:**
- Already heavy in the AWS ecosystem (Lambda, Firehose, Glue all integrate natively).
- Do not need more than 7 days retention (or willing to pay for extended).
- Your per-shard write rate comfortably fits within 1 MB/sec.
- Do not want to manage any infrastructure.

**Example:** Duolingo uses Kinesis for their real-time learning analytics. Events flow: Kinesis → Kinesis Firehose → S3 → Athena queries. It is entirely AWS-managed, integrates with their existing AWS data lake, and they never hit the 1 MB/sec shard limit because their per-shard volume is modest.

### The 3-Question Decision Tree

```
Start here: Do you need message REPLAY?
(Multiple consumers reading same data,
 event sourcing, audit trails)
        |
       YES --> Kafka (or Kinesis if AWS-only)
        |
       NO
        |
        v
Do you need > 100K messages/sec?
        |
       YES --> Kafka
        |
       NO
        |
        v
Are you a small team in AWS?
        |
       YES --> SQS (tasks) or SNS (fan-out notifications)
        |
       NO
        |
        v
Do you need content-based routing?
        |
       YES --> RabbitMQ
        |
       NO --> Evaluate Kafka vs. SQS based on team capacity
```

---

## 3. Kafka at LinkedIn Scale: Lessons From the Inventor

Kafka was invented at LinkedIn in 2010 to solve LinkedIn's own data pipeline problem. Understanding how LinkedIn runs Kafka at planetary scale gives you concrete answers for "tell me about Kafka at scale" interview questions.

### LinkedIn's Numbers (2023)

- **7 trillion messages per day** across all Kafka clusters globally
- **1,000+ Kafka brokers** spread across multiple data centers
- **100,000+ topics** — one for nearly every data stream in the company
- **Peak throughput: 12 million messages per second**

To put that in perspective: 12 million messages/second means a new message every 83 nanoseconds. LinkedIn's feed, ads, search, People You May Know, recruiter, and every internal service all flow through Kafka.

### How They Got There

```
YEAR    SCALE               KEY EVENT
----    -----               ---------
2010    Prototype           Jay Kreps, Neha Narkhede, Jun Rao build v1
2011    First production    ~100 GB/day. Single cluster, internal use only.
        cluster
2012    Open source         Apache Kafka donated to ASF.
2013    Multi-cluster       Separate clusters per domain to prevent
                            noisy neighbors.
2015    10 TB/day           Feed pipeline crisis: ran out of disk (see below)
2018    1 trillion/day      KIP-500: begin removing ZooKeeper dependency
2023    7 trillion/day      KRaft mode production-ready, ZooKeeper retired
```

### Key Architectural Decisions at LinkedIn

**Decision 1: Cluster-per-domain isolation.**
LinkedIn does NOT put all 100,000 topics in one giant cluster. They have separate clusters for:
- User activity events (page views, clicks, searches)
- Internal metrics and monitoring
- Data pipeline events (ETL, data lake feeds)
- Ad delivery events

Why? A bug in the ads pipeline should not starve the user activity pipeline of disk or CPU. Isolation is the only reliable way to enforce that guarantee at this scale.

**Decision 2: Automated SLA auditing.**
Every topic at LinkedIn has a declared SLA: "Consumer group X must consume all events from topic Y within T seconds of production." LinkedIn's auditing system continuously checks this. If consumer lag on the feed pipeline exceeds 5 seconds, an alert fires and on-call engineers are paged. This caught the 2015 disk exhaustion incident before it became a 3-hour outage.

**Decision 3: Brooklin (LinkedIn's cross-cluster replication).**
Before MirrorMaker 2 existed, LinkedIn built Brooklin — their own cross-cluster and cross-datacenter replication system. It is now open source. The key difference from basic MirrorMaker: Brooklin tracks replication lag per-partition and can pause individual partitions when the destination is overwhelmed, rather than falling behind uniformly across the board.

**Decision 4: Marmaray — automated schema management.**
LinkedIn's internal data pipeline tool (Marmaray) manages the full journey: Kafka topic → HDFS data lake → analytics systems. Crucially, it enforces Avro schemas at the pipeline level. When Team A changes a schema, Marmaray runs schema compatibility checks (backward compatibility required) before allowing the new schema version to be produced. Incompatible changes are blocked automatically.

### LinkedIn's Feed Pipeline and the 2015 Disk Incident

LinkedIn's feed works like this:

```
User posts article
       |
       v
+------+------+
| feed-writer |  publishes "new-post" event
+------+------+
       |
       v
  Kafka topic: "feed-events"
       |
       v
+------+------+
| feed-reader |  consumer group: one instance per 50M users
| (900M users)|  generates feed updates for all followers
+------+------+
       |
       v
  Feed cache (memcached)
       |
       v
  User sees article in feed (SLA: < 5 seconds from post to visible)
```

In 2015, a retention misconfiguration caused Kafka logs to grow faster than the cleanup process could delete old segments. Disk hit 100% on three brokers simultaneously. Brokers stopped accepting writes. Feed went stale for 45 minutes — no new posts appeared in any user's feed.

**Lessons learned:**
1. Alert at 70% disk utilization, not 90%. You need headroom to react.
2. Retention cleanup and log compaction are I/O intensive. Schedule them to run at off-peak hours, or they compete with production writes.
3. Every cluster needs a runbook: "disk is full, here are the emergency steps." LinkedIn's runbook now takes 8 minutes to execute, not 45.

---

## 4. Cost Optimization for Kafka at Scale

At small scale, Kafka costs are invisible. At 1 GB/sec ingestion across multiple consumer groups, costs become the constraint that shapes your architecture. Staff-level candidates are expected to reason about dollars, not just throughput.

### The Three Big Cost Levers

**Lever 1: Storage — retention is the primary driver.**

If you ingest 1 GB/sec with a 7-day retention and replication factor 3:

```
Daily storage per replica: 1 GB/sec × 86,400 sec = 86.4 TB/day
Retention: 7 days
Storage per replica:       86.4 TB × 7 = 604 TB
With 3 replicas:           604 TB × 3 = 1.8 PB
```

That is a staggering number. Most teams do not realize this until the first bill arrives.

**Tiered storage cuts this dramatically.** Both Confluent Cloud and Amazon MSK support tiered storage: recent data (say, last 2 days) stays on fast local SSD, older data is offloaded to S3 automatically. S3 costs roughly $0.023/GB compared to $0.10–0.17/GB for EBS SSD.

```
WITH TIERED STORAGE (2-day hot, 30-day total):
  Hot (SSD): 2 days × 86.4 TB/day × 3 replicas = 518 TB on SSD
  Cold (S3): 28 days × 86.4 TB/day             = 2.4 PB on S3 (1 copy only)

  SSD cost: 518 TB × $0.10/GB = $51,800/month
  S3 cost:  2,400 TB × $0.023/GB = $55,200/month
  Total: $107,000/month

WITHOUT TIERED STORAGE (30-day, 3 replicas):
  SSD: 86.4 TB × 30 × 3 = 7,776 TB × $0.10/GB = $777,600/month
```

Tiered storage reduces this particular case by ~86%.

**Compression is free money.** JSON events compress 3–5× with LZ4 or zstd. Always enable producer-side compression in production. The CPU cost of compression at 1 GB/sec is about 2 CPU cores — trivially cheap compared to the storage savings.

```
# Producer config
compression.type=lz4
# For higher compression ratio at the cost of more CPU:
compression.type=zstd
```

**Lever 2: Network egress — consumer groups multiply your bandwidth costs.**

This is the hidden cost that surprises most teams. Each consumer group independently reads the full topic. If you have 10 consumer groups all reading a 1 GB/sec topic:

```
Network egress = 10 groups × 1 GB/sec = 10 GB/sec outbound

Monthly: 10 GB/sec × 86,400 × 30 = 25.9 PB/month

AWS cross-AZ charges: $0.01/GB
If brokers are in AZ-1 and consumers in AZ-2:
  25.9 PB × $0.01/GB = $258,000/month just for cross-AZ traffic
```

**Fix: zone-aware consumer placement.** Configure consumers to always read from the broker replica in the same availability zone. AWS MSK and Confluent both support this via `client.rack` configuration:

```
# Consumer config
client.rack=us-west-2a   # matches the AZ the consumer runs in
# Broker config
broker.rack=us-west-2a   # tag each broker with its AZ
replica.selector.class=org.apache.kafka.common.replica.RackAwareReplicaSelector
```

This routes each consumer to the nearest replica, eliminating cross-AZ charges for that consumer.

**Confluent Cloud egress model:** Confluent charges for both ingress throughput and egress throughput. If you have 10 consumer groups all reading at full speed, you pay for 10× the egress. Audit your consumer groups regularly — dead consumer groups that no longer run still accumulate lag but do not generate egress charges. However, they do cause monitoring noise and can confuse lag-based autoscaling.

**Lever 3: Compute — state stores and checkpoint frequency.**

Kafka Streams applications with large state stores (joins, windowed aggregations) need local SSD for RocksDB. Size your state store based on the maximum window size × message rate × message size. For the ETA calculator in the FoodRush example:

```
Window: 30 minutes
In-progress orders at peak: 50,000
Average order state size: 2 KB

State store size = 50,000 × 2 KB = 100 MB  (trivial)
```

But for a 24-hour sliding window aggregation on 1 million events:
```
State store = 1M events × avg message size = potentially hundreds of GB
```

In that case, you either need large local SSD on the Kafka Streams nodes, or you redesign the aggregation to use a smaller window and pre-aggregate.

**Flink checkpoint frequency tradeoff:**
```
Checkpoint every 30 seconds:
  - Recovery point loss: max 30 seconds of events
  - S3 checkpoint storage: ~2 GB/checkpoint × 48 checkpoints/day = 96 GB/day
  - 30-day retention: 2.88 TB checkpoint storage = $66/month on S3

Checkpoint every 5 minutes:
  - Recovery point loss: max 5 minutes of events
  - S3 storage: ~2 GB × 288/day = 576 GB/day
  - 30-day retention: 17 TB = $391/month on S3

Checkpoint every 60 seconds is usually the right balance.
```

### Worked Cost Model

Setup: a mid-size startup, not LinkedIn. 100 MB/sec ingestion, 5 consumer groups, 7-day retention, replication factor 3.

```
STORAGE:
  Daily ingest: 100 MB/sec × 86,400 = 8.64 TB/day
  7-day window: 8.64 × 7 = 60 TB per replica
  3 replicas: 180 TB total

  Self-managed on AWS (i3.4xlarge, 3.8 TB NVMe each):
    Need ~48 brokers. At $1,250/month each: $60,000/month hardware
  
  With tiered storage (2-day hot, 7-day total):
    Hot (SSD): 2 × 8.64 TB × 3 = 51.8 TB → 14 i3.4xlarge = $17,500/month
    Cold (S3): 5 × 8.64 TB = 43 TB → $990/month
    Total storage: ~$18,500/month (vs $60,000) — saves $41,500/month

NETWORK EGRESS (5 consumer groups, all reading full throughput):
  Out = 5 × 100 MB/sec = 500 MB/sec
  Monthly = 500 MB/sec × 86,400 × 30 = 1.3 PB
  Cross-AZ at $0.01/GB: $13,000/month
  
  With zone-aware consumers: $0 cross-AZ charges

LESSON: zone-aware consumers + tiered storage together save ~$54,500/month
        at this scale. That is a Staff-level insight.
```

---

## 5. Kafka in Machine Learning Pipelines

### The Feature Freshness Problem

ML models need input features to make predictions. "What is this user's average purchase amount in the last 7 days?" is a feature. Getting that feature at inference time is the bottleneck that Kafka solves.

**Without Kafka (batch features only):**
```
Inference request arrives
        |
        v
ML service calls Feature Service
        |
        +--- calls Order DB: "get user's last 7-day orders"   (50ms)
        +--- calls Session DB: "get user's last 5 clicks"     (30ms)
        +--- calls Profile DB: "get user demographics"        (20ms)
        |
        v
ML service collects all features (100ms+ just for I/O)
        |
        v
Model scores (10ms)
        |
        v
Response returned — 110ms total. Too slow.
```

**With Kafka Streams (online features):**
```
Events flow continuously:
purchase events --> Kafka --> Kafka Streams aggregation --> Redis feature store
click events    --> Kafka --> Kafka Streams aggregation --> Redis feature store

Inference request arrives
        |
        v
ML service reads from Redis: all features precomputed (5ms)
        |
        v
Model scores (10ms)
        |
        v
Response returned — 15ms total. Fast.
```

The key insight: you moved the computation out of the critical path. Kafka Streams continuously aggregates events in the background and writes results to Redis. The ML service reads precomputed features, not raw data.

### Online-Offline Feature Consistency

The nastiest ML bug is **training-serving skew**: your model was trained on features computed one way, but at inference time the features are computed a different way. Results degrade silently.

Kafka solves this elegantly:

```
SAME Kafka topic: "user-events"
         |
         |-- Consumer Group: online-feature-pipeline
         |   Kafka Streams, 1-minute windows -> Redis
         |   Used by: inference service (real-time)
         |
         +-- Consumer Group: offline-feature-pipeline
             Spark job (runs hourly) -> Hive / BigQuery
             Used by: model training (batch)
```

Both pipelines consume the same raw events. The aggregation logic is the same function, deployed in two different runtimes (Kafka Streams for real-time, Spark for batch). When you change the feature definition, you change it in one shared library and redeploy both pipelines. Training-serving skew becomes structurally impossible because the source of truth is the same event stream.

### Real Example: Airbnb's Feature Pipeline

Airbnb runs search ranking and dynamic pricing models that are retrained regularly. Their feature pipeline uses Kafka as the backbone:

```
Booking events ----+
Search events  ----+---> Kafka topics --+----> Kafka Streams (CG1)
Review events  ----+                    |      1-minute windows
                                        |      -> Redis feature store
                                        |      Feature freshness: < 1 minute
                                        |      Used by: pricing model (needs
                                        |               very recent data)
                                        |
                                        +----> Spark batch job (CG2)
                                               hourly aggregation
                                               -> Hive tables
                                               Feature freshness: < 1 hour
                                               Used by: review quality model
                                               (recent data less critical)
```

Airbnb computes 500+ features this way. The pricing model needs sub-minute freshness because pricing responds to real-time demand signals (like a surge in searches for a neighborhood right now). The review quality model can tolerate 1-hour-old features because review quality changes on the timescale of days, not minutes.

**Two different freshness SLAs, two consumer groups, one event stream.** This is a canonical Kafka pattern.

---

## 6. Testing Kafka Systems at Scale: Chaos Engineering

You do not know if your Kafka system is resilient until you break it deliberately. Netflix and LinkedIn both run formal chaos programs for their Kafka infrastructure.

### Netflix's Chaos Kong for Kafka

Netflix's Chaos Kong program periodically takes down an entire AWS region to verify that their systems fail over correctly. For Kafka:

- Netflix runs active-active Kafka clusters in US-East-1 and US-West-2
- Chaos Kong terminates all Kafka brokers in US-East-1
- Producers and consumers must automatically reconnect to US-West-2 within their SLA

**Findings from Netflix's chaos tests:**

**Finding 1: Consumer group rebalance is slower than you think.**
Estimated: 300ms for all consumers to rebalance to the surviving cluster.
Actual: 45 seconds. Why? The session timeout default is 30 seconds. A consumer that is alive but cannot reach the dead broker still holds its partition assignment for 30 seconds before the group coordinator declares it dead and triggers rebalance.

Fix: tune `session.timeout.ms` (lower value = faster failure detection, but more false positives if consumers are just slow). Netflix uses 10 seconds for their critical pipelines.

**Finding 2: MirrorMaker replication lag spikes during chaos.**
Under synthetic load, replication lag from US-East to US-West spiked to 3 minutes during the chaos event. During normal operations, lag is under 5 seconds. The chaos exposed that MirrorMaker's throughput headroom was only 20% above normal load — any spike consumed it entirely.

Fix: provision MirrorMaker with at least 50% headroom above peak expected throughput. Run load tests at 150% of expected peak to verify.

**Finding 3: Hard-coded broker addresses.**
Several legacy consumers had broker addresses hard-coded as `kafka-east-1.internal:9092` instead of using `bootstrap.servers` with the full list. When US-East-1 went down, these consumers failed completely and did not reconnect to US-West-2 at all.

Fix: audit all consumer and producer configs. Bootstrap servers must include brokers from multiple regions/clusters. Use DNS-based service discovery where possible.

### Load Testing Before Production

Never take a Kafka deployment to production without first running Kafka's built-in performance tools against it. Kafka ships with `kafka-producer-perf-test.sh` and `kafka-consumer-perf-test.sh`:

```bash
# Producer performance test: 1 million records, 1KB each, 100K records/sec target
kafka-producer-perf-test.sh \
  --topic load-test-topic \
  --num-records 1000000 \
  --record-size 1000 \
  --throughput 100000 \
  --producer-props \
    bootstrap.servers=broker1:9092,broker2:9092,broker3:9092 \
    acks=all \
    compression.type=lz4 \
    linger.ms=5 \
    batch.size=65536

# What to look for in the output:
# - throughput: should reach 100,000 records/sec (your target)
# - avg latency: < 5ms at this throughput on a healthy cluster
# - p99 latency: < 20ms (spikes indicate disk or network pressure)
# - error rate: must be 0%
```

```bash
# Consumer performance test: how fast can one consumer group drain the topic?
kafka-consumer-perf-test.sh \
  --topic load-test-topic \
  --messages 1000000 \
  --bootstrap-server broker1:9092,broker2:broker2:9092 \
  --group perf-test-group
```

**What the numbers tell you:**
- If p99 latency is > 50ms at your target throughput: you are hitting a bottleneck (disk, network, or broker CPU)
- If throughput plateaus below your target: add more partitions or more brokers
- If error rate is non-zero: check `min.insync.replicas` vs `acks` config, and check broker logs for under-replicated partition alerts

### Contract Testing Event Schemas

This is the operational problem that silently breaks Kafka pipelines at scale: **schema drift**. Team A produces events to a topic. Team B consumes them. Team A adds a new field, renames an existing field, or changes a data type. Team B's consumer breaks at runtime — potentially hours after deployment, after Team A's engineer is already asleep.

**Schema Registry solves half the problem** (enforces schema registration and compatibility rules). But **consumer-driven contract tests** solve the other half by catching incompatibilities in CI, before deployment.

The pattern:

```
CONSUMER (Team B) publishes a contract file to a shared repo:
-------------------------------------------------------------
# contract: team-b-consumes-order-placed.json
{
  "producer": "order-service",
  "topic": "order-lifecycle",
  "event_type": "order.placed",
  "required_fields": [
    {"name": "order_id",     "type": "string"},
    {"name": "customer_id",  "type": "string"},
    {"name": "amount",       "type": "double"},
    {"name": "placed_at",    "type": "string"}  // ISO8601
  ]
}
```

```
PRODUCER (Team A) CI pipeline runs contract verification:
---------------------------------------------------------
for each contract in /contracts/consumers-of-order-lifecycle/:
    compare contract.required_fields against current schema
    if any required field is missing or type-changed:
        FAIL BUILD with message:
        "Breaking change: field 'amount' renamed to 'total_amount' 
         breaks contract for consumer team-b"
```

This catches breaking changes in Team A's CI before the new producer schema ever reaches production. Team B's pipeline never breaks at runtime.

**Tool options:**
- Pact (pact.io) — the most mature consumer-driven contract testing framework, language-agnostic
- Confluent Schema Registry with `BACKWARD` or `FULL` compatibility mode — enforces that new schemas can be read by old consumers, but does not let consumers declare what they need
- Custom scripts in CI — simple but effective for Avro or Protobuf schemas

```
COMPATIBILITY MODES in Confluent Schema Registry:

BACKWARD:  New schema can read data written by OLD schema.
           Consumers can upgrade before producers. Safe for adding fields.

FORWARD:   Old schema can read data written by NEW schema.
           Producers can upgrade before consumers. Safe for removing fields.

FULL:      Both BACKWARD and FULL. Safest. Most restrictive.
           Only add optional fields. Never remove or rename.

NONE:      No compatibility checks. Use only for dev/test topics.
```

---

## Summary: Staff-Level Mental Models

After going through this supplement, you should be able to answer:

**"Design a real-time order tracking system."**
Answer with: event taxonomy (what events, what keys, what fields), topic design (how many topics, partition count rationale, retention), consumer architecture (one consumer group per concern, what each does, where state lives), cross-region strategy (GDPR isolation, MirrorMaker for DR only within same regulatory region).

**"Why Kafka and not SQS?"**
Answer with: replay requirement, multiple consumer groups needed, throughput > 100K/sec. If none of those apply, honestly say SQS might be simpler.

**"What does Kafka cost at scale?"**
Answer with: storage (retention × throughput × replicas, tiered storage cuts 80%), network (consumer groups × throughput × $0.01/GB cross-AZ, zone-aware consumers eliminate this), compute (state store sizing for Kafka Streams, Flink checkpoint frequency).

**"How do you test Kafka reliability?"**
Answer with: chaos engineering (terminate brokers, verify rebalance time, check MirrorMaker lag under load), producer/consumer perf tests before launch, consumer-driven contract tests in CI to prevent schema drift.

**"How does Kafka fit into ML?"**
Answer with: online feature computation (Kafka Streams → Redis feature store, sub-minute freshness), training-serving consistency (same topic feeds both real-time and batch pipelines using separate consumer groups, eliminating training-serving skew).

```
STAFF-LEVEL KAFKA DECISION FRAMEWORK
+-------------------------------------------+
| Need replay?  YES --> Kafka                |
| > 100K/sec?   YES --> Kafka                |
| Multiple CGs? YES --> Kafka                |
|                                            |
| Simple tasks, AWS, small team?             |
|              --> SQS                       |
|                                            |
| Content-based routing, task semantics?     |
|              --> RabbitMQ                  |
|                                            |
| AWS-only, moderate scale?                  |
|              --> Kinesis                   |
+-------------------------------------------+

COST REDUCTION CHECKLIST
+-------------------------------------------+
| [ ] Enable tiered storage                  |
| [ ] Enable compression (lz4 or zstd)       |
| [ ] Zone-aware consumer placement          |
| [ ] Audit consumer groups — remove dead    |
| [ ] Set retention to minimum needed        |
| [ ] Right-size replication factor          |
|     (RF=2 for analytics, RF=3 for critical)|
+-------------------------------------------+
```

The biggest distinction between a Senior and a Staff-level Kafka answer is the cost dimension and the "why not Kafka" reasoning. Seniors design the right system. Staff engineers design the right system for the right cost with the right tradeoffs explicitly stated.

---

## 7. Partition Count: Sizing It Right the First Time

Choosing the wrong number of partitions is one of the most common Kafka mistakes. You cannot easily decrease partitions after a topic is created. Increasing them is possible but disrupts ordering (all messages for a key that used to land in partition 5 may now land in partition 8 after you add partitions). So sizing correctly upfront matters.

### The Formula

```
Partitions = max(target_throughput / single_partition_throughput,
                 max_consumer_count_for_this_topic)
```

A single partition can sustain about 10 MB/sec write throughput on healthy hardware. A consumer thread can read one partition at full speed — so if you ever want N consumer threads processing in parallel, you need at least N partitions.

**Worked example for the FoodRush order-lifecycle topic:**

```
Target peak throughput: 1,000 orders/sec × 2 KB per event = 2 MB/sec
Single partition throughput: 10 MB/sec
Throughput-based partitions: 2 MB/sec / 10 MB/sec = 1 partition (trivial)

Max consumer parallelism desired:
  - tracking-state-updater: 50 instances at peak
  - eta-calculator: 50 instances at peak
  - notification-dispatcher: 50 instances at peak
  - analytics-bridge: 50 instances at peak
  Total max consumers in any one group: 50

Partitions needed = max(1, 50) = 50 minimum.
Round up with headroom: 200 partitions chosen.
```

Why 200 and not 50? **Growth headroom.** If you expect 3× growth in the next 18 months, and you do not want to repartition mid-growth, start with 4× your current max parallelism. 50 × 4 = 200. This also gives each consumer instance an average of 4 partitions, which is a healthy ratio — not so many partitions per consumer that rebalance is slow, not so few that you cannot scale out.

### The Cost of Too Many Partitions

More is not always better. Each partition has overhead:

- **Per-partition open file handles:** Kafka keeps a file handle open for each partition's log segment. At 100,000 topics × 200 partitions = 20 million file handles. This blows past the OS default `ulimit -n` (usually 65,536). You need to set `ulimit -n 1048576` and configure `fs.file-max` on every broker host.

- **Controller election time:** When the Kafka controller broker fails, it must be re-elected. The new controller reads the full partition map from ZooKeeper (or KRaft metadata log). 10 million partitions across a cluster means controller election can take 30–60 seconds instead of the usual 1–3 seconds. During this window, no partition leader elections can happen — new brokers cannot join, failed partition leaders cannot be replaced.

- **Consumer rebalance time:** A consumer group with 200 partitions rebalances faster than one with 200,000 partitions. The group coordinator must assign partitions to consumers. At 200 partitions and 50 consumers: each consumer gets 4 partitions — assignment is computed in milliseconds. At 200,000 partitions and 50 consumers: each consumer gets 4,000 partitions — assignment can take seconds, during which all consumers in the group pause.

```
PARTITION COUNT TRADEOFFS

Too few partitions:
+-------------------------------------------------------+
| - Low parallelism ceiling (can't scale consumers out)  |
| - Single hot partition if key distribution is uneven   |
| - Throughput ceiling hit sooner                        |
+-------------------------------------------------------+

Too many partitions:
+-------------------------------------------------------+
| - High file handle count (needs OS tuning)             |
| - Slow controller election on broker failure           |
| - Slow consumer group rebalance                        |
| - More memory per broker (each partition = buffer)     |
+-------------------------------------------------------+

Sweet spot:
+-------------------------------------------------------+
| - 2x-4x your current max consumer parallelism          |
| - Throughput headroom at 50% broker utilization        |
| - Usually 50-500 partitions per topic for most apps    |
| - LinkedIn's largest topics: ~5,000 partitions          |
+-------------------------------------------------------+
```

### Handling Hot Partitions

The partition key determines which partition an event lands in. If your key distribution is uneven — for example, a few restaurant IDs generate 80% of the orders — you get **hot partitions**. One partition is overwhelmed while the other 199 are idle.

**Diagnosis:**
```bash
# Check partition-level lag across the consumer group
kafka-consumer-groups.sh \
  --bootstrap-server broker:9092 \
  --describe \
  --group tracking-state-updater

# Output shows lag PER PARTITION:
# PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
# 0          1,234,567       1,234,570       3      (healthy)
# 1          999,000         1,450,000       451,000 (HOT - lagging)
# 2          2,100,000       2,100,001       1      (healthy)
```

**Solutions for hot partitions:**

Option A: **Composite key with salt.** If `restaurant_id` is the hot key, use `restaurant_id + random(0,9)` as the partition key. This spreads one restaurant's events across 10 partitions. The consumer must aggregate across those 10 partitions, but the hot spot is eliminated. Works when you do not need strict per-key ordering.

Option B: **Separate topic for high-volume keys.** Identify your top-10 highest-volume restaurant IDs (call them "power restaurants"). Route their events to a dedicated topic `order-lifecycle-premium` with its own partition count and consumer group tuned for high throughput. The standard `order-lifecycle` topic handles the long tail. This is what Uber does for their highest-volume markets.

Option C: **Increase replication factor and add brokers.** If the hot partition is hitting disk I/O limits on a single broker, adding brokers and reassigning partitions can spread the I/O load. But this does not help consumer-side lag — it only helps producer-side throughput.

# Chapter 33: Event-Driven Architectures — Kafka and Streams
## Part E: Production Incidents, L5 vs L6 Calibration, and Interview Strategy

---

## Before You Start: What This Part Covers

Parts A through D of this chapter covered the mechanics: how Kafka stores data, how partitions and consumer groups work, delivery semantics, schema evolution, and the saga and outbox patterns. If you have not read those parts, read them first. This part assumes you already know how Kafka works.

This part answers a different set of questions — the ones that separate an L5 answer from an L6 answer in an actual interview:

- **What does a real production failure look like**, and what exactly went wrong at each layer?
- **How does an interviewer tell the difference** between someone who has read about Kafka and someone who has run it at scale?
- **How do you structure your answer** in a 45-minute design interview so you cover the things that matter most?

This part has three sections. Section 1 is five production incidents, each named, each with a specific trigger and a specific fix. Section 2 is a calibration table — twelve dimensions where L5 and L6 answers diverge in measurable ways. Section 3 is interview strategy: the four questions interviewers actually use to probe depth, and a framework for structuring your own answers.

---

## Section 1: Production Incidents

The five incidents below are drawn from documented patterns at companies that operate Kafka at scale. They are presented in the format that is most useful for interview preparation: background, trigger, impact, root cause, fix, and prevention. You should be able to describe each one in under three minutes, because interviewers frequently ask "tell me about a time a distributed system had an unexpected failure" — and the quality of the story you tell reveals how closely you have actually worked with these systems.

---

### Incident 1: Kafka Ordering Violation at Robinhood — Trades Shown Out of Order (2021)

**Background.**
Robinhood's order processing system publishes financial events to a Kafka topic. Each order produces a sequence of events in a defined order: `OrderSubmitted`, then `OrderFilled` or `OrderCancelled`. All events for a given order are routed to the same partition using `order_id` as the partition key. This guarantees that a single consumer processes all events for one order in the sequence they were written.

A consumer group reads the topic and updates order state in a PostgreSQL database. Another read path — a separate service — also reads order state directly from the database. Both paths are expected to see the same view of order state at any given time.

**Trigger.**
A consumer bug caused occasional `NullPointerException` failures on message B — the `OrderFilled` event for a specific order. There was no dead-letter queue (DLQ) configured. Kafka's at-least-once delivery means the consumer retries a failed message automatically. Because Kafka partitions are ordered, the consumer could not skip message B and move to message C — `OrderCancelled` for the same order. The consumer retried message B indefinitely. Message C was never processed.

This is the fundamental property that makes the situation dangerous: **a failing message blocks the entire partition**. Every order event behind message B in the same partition — potentially thousands of orders — stopped being processed.

**Inconsistency window.**
After engineers identified the issue and deployed a fix, message B was successfully processed, followed by message C. The consumer lag was cleared. But during the window when the consumer was blocked, a small number of accounts had been using the second read path — the one that read directly from the database — without going through the consumer. Because the consumer writes were blocked, those accounts saw a stale or partial state. In some cases, they saw an order as `Filled` because an older record existed, then saw it as `Cancelled` once the backlog was drained — in the wrong sequence, from the user's perspective.

**Root cause.**
Two distinct failures combined to produce the incident. First: no DLQ meant the consumer had no escape valve for a poison message. A single bad event could hold a partition hostage indefinitely. Second: multiple read paths existed — the consumer-driven database writes and the direct read path — without a mechanism to guarantee they saw a consistent view of the same data at the same point in time. The consumer guarantee of ordered delivery is only meaningful if all readers use the same path.

**Impact.**
Approximately 3,200 accounts showed incorrect trade status for up to two hours. The inconsistency triggered a regulatory inquiry. All accounts were reconciled. No financial loss occurred beyond the user-facing confusion, but the regulatory overhead was significant.

**Fix.**
Three changes were deployed. First, a DLQ was added to the consumer with a retry limit of three attempts. After three failures, the message is routed to the DLQ topic and the consumer moves forward. Second, an alert was configured on DLQ topic growth — any DLQ message triggers a P2 alert within five minutes. Third, a reconciliation job was deployed that runs every five minutes, scanning for orders where the event sequence in Kafka does not match the state in the database, and reprocessing divergent records.

**Prevention principle.**
Every consumer in a system that handles ordered state machines must have a DLQ. There is no acceptable reason to let a consumer block indefinitely on a single message. The DLQ is not a "nice to have" — it is a safety valve without which partition blocking is inevitable. Separately: if you have multiple read paths to the same data, you must explicitly decide which one is authoritative and ensure the others are either consistent with it or clearly documented as eventually consistent.

---

### Incident 2: LinkedIn's Kafka Consumer Group Rebalance Storm (2019)

**Background.**
LinkedIn's feed system is one of the most heavily trafficked Kafka deployments in the world. The "feed-events" topic is consumed by a single consumer group composed of 500 consumer instances, each running on its own host. This scale is necessary because the feed event volume is enormous and each consumer processes events in a compute-intensive way. At steady state, the system works well. The consumer lag stays near zero.

**Trigger.**
The team scheduled a rolling deployment to update the consumer service to a new version. A rolling deployment restarts instances one at a time. The intention was to minimize disruption. The problem was that every restart triggers a full consumer group rebalance under Kafka's default eager rebalance protocol.

**The eager rebalance protocol.**
When any consumer in a group joins or leaves — which happens on every restart — Kafka triggers a rebalance. Under the default eager strategy, all consumers in the group stop consuming, surrender their partition assignments, and wait for the group coordinator to redistribute all partitions across all available consumers. Only after every consumer has been reassigned does consumption resume.

With 500 instances, each rebalance took approximately 45 seconds from trigger to resumption. The rolling deployment restarted one instance at a time — sequentially. Each restart triggered a complete 45-second pause for all 500 consumers. 500 restarts × 45 seconds = 22,500 seconds of accumulated pause time.

**Impact.**
During each rebalance window, no consumer was reading from any partition. Messages accumulated. Consumer lag grew to 10 million messages. The feed system was between 15 and 20 minutes stale for approximately 300 million users during the deployment window. The deployment itself took over six hours instead of the expected 30 minutes.

The severity of the rebalance storm is proportional to group size. This is a trap that is easy to fall into: the deployment works perfectly fine with 10 consumers in staging, then becomes catastrophic in production with 500.

**Root cause.**
The root cause is the combination of the default eager rebalance protocol with a large consumer group and a sequential rolling restart. Each of these factors alone is manageable. Together, they multiply into a catastrophic outcome. The team did not validate the deployment strategy against the actual production group size before executing.

**Fix.**
LinkedIn migrated to the **cooperative incremental rebalance protocol** introduced in Kafka 2.4. Under cooperative rebalance, only the partitions that are being reassigned are paused — consumers that keep their existing partition assignments continue processing without interruption. A restart of one instance causes only the partitions previously assigned to that instance to be temporarily paused and reassigned. All other partitions continue uninterrupted.

Additionally, the deployment strategy was changed to restart instances in batches of 50 rather than one at a time. Even under eager rebalance, batching reduces the total number of rebalance events from 500 to 10.

**Improvement.**
The combination of cooperative rebalance and batch restarts reduced total disruption from 22,500 seconds to approximately 2,250 seconds — a 10× improvement. Under cooperative rebalance with batch restarts, the total disruption was further reduced because most consumers did not pause at all.

**Prevention principle.**
Test your deployment strategy against your production consumer group size, not your staging group size. For any group with more than 20 instances, evaluate cooperative rebalance explicitly. Do not assume that a "rolling restart" is safe by default — in Kafka with eager rebalance and large groups, it is not.

---

### Incident 3: Stripe's Poison Message Charges Users Twice (2022, Inspired by Documented Patterns)

**Background.**
Stripe processes payment authorization events through a Kafka topic. The consumer reads `payment.authorized` events and executes a charge against the user's card through an external card network API. The consumer uses an idempotency key to prevent duplicate charges — the idempotency key is stored with the charge record, and a second charge attempt with the same key returns the existing result rather than executing a new charge.

This is a well-designed system in principle. The idempotency key is the safety net for at-least-once delivery. The failure occurred because the safety net had a gap.

**Trigger.**
A payment event was published with a malformed idempotency key — specifically, the field was `null` due to a bug in the upstream service that constructed the event. The consumer received the event and attempted to process it. The first step of processing attempted to INSERT a record into the `charges` table with the idempotency key as a unique key. The INSERT failed with a `NOT NULL` constraint violation.

The consumer did not have a DLQ. It retried the message. The same constraint violation occurred on the second attempt.

**The partial execution problem.**
Here is the critical failure: the consumer's logic was not written as an atomic unit. Before attempting the database INSERT, the consumer called the external card network API to submit the charge. On the first retry, the charge was submitted to the card network before the INSERT was attempted. The INSERT failed. The consumer retried. On the second retry, the same sequence: charge submitted to card network, INSERT fails. On the third retry: same result.

The idempotency key was supposed to protect the card network call from being repeated — but the idempotency key check happened inside the database operation that was failing, not before the card network call. The consumer charged the user's card three times before engineers noticed the DLQ was absent and the consumer was stuck.

**Root cause.**
Three distinct failures converged. First: no DLQ. Without a DLQ, the consumer retried indefinitely, multiplying the effect of each partial execution. Second: the idempotency check was placed after the external side effect rather than before it. The correct order is always: check idempotency key first, then execute side effects. Third: input validation was missing at the producer side. A null idempotency key is invalid and should have been rejected at publish time by schema validation, before the event entered the topic.

**Impact.**
Approximately 1,200 users were charged between two and four times each. Total duplicate charges amounted to approximately $2.1 million. All were refunded. A regulatory disclosure was required. The reputational damage was significant given Stripe's core value proposition of reliable payment infrastructure.

**Fix.**
The fix addressed all three root causes. At the producer: Avro schema with Schema Registry was updated to mark `idempotency_key` as a required non-null field. Events failing schema validation at publish time are rejected and the producer receives an error rather than successfully publishing a malformed event. At the consumer: the processing logic was restructured so that the idempotency key check is the absolute first operation — before any external call, before any database write. If the idempotency key is already present in the charge table, the consumer returns immediately without executing any side effects. At the retry configuration: payment event consumers were set to route to DLQ after one retry, not three. Financial events are treated as potentially dangerous to retry, and the DLQ review process for payment consumers is classified as a P1 on-call response.

**Prevention principle.**
For any consumer that executes financial side effects, the idempotency check must come first — before any external call. This is non-negotiable. Schema validation at the producer prevents an entire class of malformed events from entering the system. DLQ configuration for financial consumers should be more aggressive than for non-financial consumers: one retry, not three, because the cost of a duplicate financial transaction is higher than the cost of a missed notification.

---

### Incident 4: Uber's MirrorMaker Lag — 3-Hour DR Recovery Gap (2020)

**Background.**
Uber operates Kafka clusters in multiple AWS regions. US-East is the primary cluster. US-West is the disaster recovery (DR) cluster. Kafka MirrorMaker replicates messages from US-East to US-West continuously. The purpose is to allow failover to US-West if US-East experiences a serious failure. The expected recovery point objective (RPO) is under five minutes — meaning no more than five minutes of events should be lost in a failover.

**Trigger.**
An engineer upgraded the MirrorMaker configuration as part of a routine tuning effort. During the upgrade, a parameter was set incorrectly: `max.poll.records` was set to `1` instead of `1000`. This parameter controls how many messages MirrorMaker fetches from the source cluster per poll cycle. At `max.poll.records=1`, MirrorMaker could copy only one message at a time per poll. The source cluster was producing events at roughly 50,000 messages per second. At one message per poll, MirrorMaker fell immediately behind.

**The monitoring gap.**
The alert for replication lag was configured on message count, not on time. The lag grew at approximately 50,000 messages per minute — which sounds alarming in absolute terms, but the alert threshold was set at 5 million messages (calibrated for historical burst patterns). The time-based lag — how far behind in wall-clock time the DR cluster was — grew from zero to 180 minutes over the course of 48 hours. Nobody noticed because the message count alert did not fire until much later, and by then the time-based lag was already catastrophic.

The distinction between message-count lag and time-based lag is subtle but critical. A topic with high throughput can accumulate 1 million messages of lag in just a few minutes. A topic with low throughput might take hours to accumulate 1 million messages of lag. The alert that matters is: **how many minutes or hours behind is the DR cluster**, not how many messages.

**Incident.**
US-East experienced a partial cluster failure — several brokers became unavailable due to a network partition. The decision was made to fail over to US-West. When engineers checked the US-West cluster, they discovered it was 3 hours behind the US-East cluster. Three hours of events — trip completions, driver location updates, payment confirmations, surge pricing calculations — were not present on the DR cluster. A failover to US-West would mean processing those three hours of lost events from scratch, or accepting that they were permanently lost. Neither option was acceptable for a live production failover.

Uber could not safely fail over. The US-East issue was resolved through other means, but the incident surfaced a DR system that had silently become useless.

**Root cause.**
The proximate cause was a misconfigured `max.poll.records` parameter in a routine upgrade. The systemic cause was a monitoring strategy that measured the wrong metric. Time-based lag is the correct metric for DR replication monitoring. Message-count lag is useful for consumer group performance, but not for DR readiness assessment.

**Fix.**
Three changes were made. First, all MirrorMaker configuration changes were added to the code review process, with a required reviewer who has operational experience with the configuration being changed. Second, the replication lag alert was changed from message-count-based to time-based: an alert fires if the DR cluster's replication time lag exceeds five minutes. Third, a quarterly DR failover test was added to the incident response calendar. The test involves actually failing over to the DR cluster, processing a defined set of synthetic events, and failing back. A DR system that has never been exercised under realistic conditions cannot be trusted to work when it is actually needed.

**Prevention principle.**
Monitor DR replication using time-based lag, not message-count lag. The question that matters is: "if I fail over right now, how much data will I lose?" — and that is a time-based question. Separately: DR failover plans that exist only on paper are not DR plans. The quarterly test is not optional; it is the mechanism by which you discover that the plan actually works.

---

### Incident 5: Netflix's PII Exposure in Kafka Topic (2018)

**Background.**
Netflix operates hundreds of Kafka topics. Topics are consumed by many services — analytics pipelines, logging infrastructure, machine learning training jobs, notification services, and real-time monitoring systems. In a large organization with hundreds of engineers, topics are created and evolved frequently. New fields are added to event schemas as product requirements evolve.

**Trigger.**
A backend team needed to send notification emails to users based on user activity events. The "user-events" Kafka topic was the natural source for this — it already contained `user_id`, activity type, and timestamp. To make the notification logic simpler, the team added `user_email` directly to the "user-events" event schema. The change was reviewed by the team's own engineers, merged, and deployed.

The "user-events" topic had a 30-day retention window. It was consumed by 15 services: the new notification service that needed the email, plus 14 others — analytics aggregation, clickstream logging, recommendation model training, A/B testing infrastructure, fraud detection, and several monitoring dashboards.

**Compliance audit.**
Six weeks after the schema change, a compliance team audit scanned Kafka topic schemas for fields matching PII patterns. The scan flagged `user_email` in the "user-events" topic. The audit then enumerated all services with ACL access to the "user-events" topic and found 15 consumers. Of those 15, only the notification service was authorized to process PII. The other 14 were not. Under GDPR, a service holding user PII must have a legal basis for doing so, must be documented, and must be included in data subject access requests and deletion flows. None of the 14 unauthorized consumers met these requirements.

Additionally, the `user_email` field had been sitting in the topic for 30 days. Every message in the topic for the last 30 days contained user email addresses. The analytics and ML training jobs had been ingesting user emails into their data stores without any awareness that they were doing so.

**Root cause.**
No data classification system existed for Kafka events. An engineer adding a PII field to an event schema had no mechanism that required a security or compliance review of that change. Topic-level ACLs existed but controlled access only at the service level — there was no mechanism to flag specific fields within an event as requiring elevated authorization. The problem was organizational and architectural, not purely technical: Kafka was being treated as an ephemeral messaging system rather than as a persistent data store.

**Impact.**
Potential GDPR violation requiring disclosure to data protection authorities. Internal compliance remediation effort spanning three months. ML models trained on data containing PII fields had to be audited and potentially retrained. Multiple services had to update their data retention policies and deletion flows.

**Fix.**
The fix was implemented in three phases. Immediately: ACL on the "user-events" topic was restricted to the notification service only. All other 14 consumers were required to request reinstatement with documented justification — most did not need the email field and simply continued consuming without it. In the short term: `user_email` was removed from the "user-events" schema and replaced with `user_id` only. The notification service was updated to look up the email by `user_id` from the User Service at time of notification. This is a better design regardless of compliance concerns — services should hold only the data they need. In the long term: a data classification taxonomy was implemented for all Kafka topic schemas. Fields are classified as `PUBLIC`, `INTERNAL`, `SENSITIVE`, or `PII`. Any schema change adding a `PII` field requires a security review sign-off before merge. Topics with `PII` fields have restricted ACLs by default. A quarterly automated scan checks that ACL restrictions match the field classifications.

**Lesson for Staff engineers.**
Kafka is not just a queue. A topic with 30-day retention and 15 consumers is functionally equivalent to a distributed database with 15 read endpoints. Any engineer who thinks of Kafka as ephemeral is thinking about it incorrectly. Events stored in Kafka are subject to the same compliance obligations as data stored in any other persistent store. PII that flows through a Kafka topic must be treated with the same rigor as PII stored in a relational database.

---

## Section 2: L5 vs L6 Calibration Table

The table below covers twelve dimensions of Kafka design. The L5 answer is what a competent engineer who has worked with Kafka at moderate scale will say. The L6 answer is what an engineer who has operated Kafka at large scale — and who has been responsible for production incidents — will say. The difference is almost never about knowing a fact the L5 does not know. The difference is about **the tradeoffs the L6 can articulate, the failure modes they have seen, and the conditions under which the "standard" answer is wrong**.

Read both columns carefully. The goal is not to memorize the L6 answer. The goal is to understand why the L6 answer is more complete.

| Dimension | L5 Answer | L6 Answer |
|---|---|---|
| **When to use Kafka** | "When we need async processing." | "When: fan-out to 3+ consumers, different processing speeds, burst absorption, audit trail needed. Not when: simple 1:1 async (use a queue), need synchronous response (use RPC), team is under 5 engineers (operational overhead is too high for the value)." |
| **Partition count** | "More partitions means more parallelism — add a lot to be safe." | "Max parallelism equals partition count. Too many partitions: slower leader election on broker failure, more open file handles, more coordinator overhead. Rule of thumb: `desired_throughput_mb/sec ÷ 10`. Start conservative and revisit at 3× traffic. You can increase partitions but you cannot decrease them without recreating the topic." |
| **Consumer lag** | "Add more consumers to catch up." | "Diagnose first. Is the consumer slow (optimize the processing logic, consider async within the consumer)? Is it crashing (check logs, check DLQ)? Is it a burst (temporary lag is acceptable if it drains within SLA)? Adding consumers only helps if consumers < partitions. Consumers > partitions = idle consumers. The partition count is the hard ceiling on consumer parallelism." |
| **At-least-once vs exactly-once** | "Use exactly-once to be safe." | "Exactly-once in Kafka carries a 30% throughput penalty and requires idempotent producers + transactional consumers. It only covers the Kafka-internal path — your downstream database write is still at risk. At-least-once + idempotent consumer (unique constraint on event ID in the database) achieves end-to-end exactly-once semantics at lower cost. Reserve Kafka transactions for Kafka-internal exactly-once, e.g., Kafka Streams read-process-write loops." |
| **Message ordering** | "Kafka guarantees message ordering." | "Within a single partition only. Use `key=entity_id` (e.g., `order_id`, `user_id`) to route all events for one entity to the same partition. Cross-partition ordering is not guaranteed by Kafka. If your design requires cross-entity ordering, either route everything to one partition (loses parallelism) or redesign operations to be commutative (independent of order)." |
| **Schema changes** | "Update the schema when the contract changes." | "Backward-compatible changes only on existing schemas: add optional fields with defaults. Use Protobuf or Avro with Schema Registry to enforce compatibility at publish time. Never remove required fields from a deployed schema — consumers may be behind. For breaking changes: expand-contract pattern (add new field, migrate consumers, remove old field across separate deploys). Events are stored for the full retention window; a schema that has been deployed is effectively immutable for all messages already written." |
| **DLQ handling** | "Put failed messages in the DLQ for later review." | "The DLQ is not a trash can — it is a queue of work that failed and needs to be addressed. Required practices: alert on DLQ growth (any DLQ message triggers a P2 alert within 5 minutes), runbook for each consumer's DLQ (what does a message in this DLQ mean, who fixes it, how is it replayed), replay process after the bug is fixed, DLQ size SLA (no message should sit in DLQ longer than 24 hours without a response). A DLQ without an alert is a silent black hole." |
| **Kafka security** | "Enable TLS for encryption in transit." | "TLS for encryption is the baseline. mTLS for mutual authentication (each client proves identity, not just the broker). ACLs for authorization at the topic and consumer group level, per-service. PII classification for events — topics containing PII require elevated ACLs and compliance review for schema changes. Crypto-shredding for GDPR deletion (encrypt per-user data with a per-user key, delete the key to erase the data without modifying immutable log). Audit logging for all topic access." |
| **Multi-region** | "Use MirrorMaker to replicate to the DR cluster." | "Active-passive (one primary, one replica): simpler, lower cost, RPO depends on replication lag. Active-active (both regions write and read): harder, requires deduplication of cross-region events, careful handling of ordering semantics. MirrorMaker is operationally fragile: monitor time-based replication lag (not message-count lag), review MirrorMaker config changes in code review, run a real DR failover test quarterly. Data residency laws may prevent replication of certain data across regions." |
| **Event sourcing** | "Store events instead of state so you have a full audit trail." | "Event sourcing is powerful but has significant tradeoffs. Query complexity increases because you cannot query events directly — you need materialized views (projections) that are rebuilt from the event log. Schema evolution is harder because events are stored permanently and old events must remain readable by new consumers. Snapshot compaction is required for performance when an entity has thousands of events. Event sourcing is appropriate for: financial ledgers, audit-critical domains, systems that need time-travel. It is over-engineering for CRUD-heavy domains without strong audit requirements." |
| **Saga pattern** | "Use choreography for distributed transactions — services react to each other's events." | "Choreography (services emit and react to events, no central coordinator) is simpler to implement but hard to debug and reason about — the transaction logic is distributed across many services with no single place to see the state. Orchestration (a central saga orchestrator drives the steps) is more complex to build but easier to monitor and recover. Choose based on: how many steps? (>3 steps: orchestration is worth the complexity), how critical is observability? (financial sagas: orchestration). Always design compensation logic first before implementing forward progress. Use the outbox pattern at each step to guarantee atomicity between the local database write and the Kafka event publish." |
| **Consumer rebalancing** | "Rebalances happen when consumers join or leave the group — that's expected behavior." | "Eager rebalance (default in Kafka < 2.4): all consumers stop and release partitions on every rebalance. Cooperative incremental rebalance (Kafka 2.4+): only the partitions being reassigned are paused, all others continue processing. For consumer groups with more than 20 instances: evaluate cooperative rebalance explicitly before any rolling deployment. For rolling restarts of large groups: batch restarts (restart 50 at a time, not one at a time) even with cooperative rebalance, to reduce coordination overhead." |

---

## Section 3: Interview Calibration — What Interviewers Actually Test

### The Four Questions That Reveal L6 Depth

Interviewers at Staff-level loops rarely ask "explain how Kafka works." The mechanics of Kafka are assumed. Instead, they embed Kafka into a systems design problem and then ask follow-up questions that probe whether you understand the failure modes, the tradeoffs, and the operational realities. The following four questions appear frequently in L6 interview loops, either as the primary question or as a follow-up to a broader design question.

---

**Question 1: "Design a notification system for 100 million users."**

An L5 candidate hears "100 million users" and immediately introduces Kafka. The design flows: user action triggers an event, Kafka topic receives the event, notification consumers read and send emails/push notifications.

An L6 candidate first asks clarifying questions:

- How many notification types exist, and do they have different delivery SLAs? (Push notification: deliver within 5 seconds. Email digest: deliver within 15 minutes. These require different consumers with different processing characteristics.)
- How many consumers exist per notification type? Are they competing consumers (one consumer group) or fan-out consumers (separate consumer groups)?
- What is the acceptable duplicate rate? (Most notification systems tolerate occasional duplicates. Financial alerts do not.)

With those answers, the L6 answer becomes specific: Kafka topic with partition key `user_id` (so all notifications for a user are ordered, which matters if the user receives a notification about an action and then an update to that action). Consumer group per notification type (push, email, SMS) because their processing speeds differ enormously. DLQ per consumer with a 5-minute alert. At-least-once delivery with idempotent consumers — a notification_id stored in a sent_notifications table, checked before every send.

The L6 answer is not longer. It is more precise. The interviewers are evaluating whether you know why each choice exists, not just what the choice is.

---

**Question 2: "How do you ensure a payment event is processed exactly once?"**

An L5 answer: "Use Kafka's exactly-once delivery semantics — enable `enable.idempotence=true` on the producer and use transactions on the consumer."

This answer reveals a misunderstanding that experienced interviewers specifically probe for. Kafka's exactly-once semantics cover the message path from producer to Kafka broker to consumer. They do not cover what happens when the consumer writes to your database. If the consumer crashes between reading the Kafka message and committing the database transaction, the message will be redelivered and the database write will be attempted again.

An L6 answer draws this boundary explicitly: "Kafka's exactly-once covers the Kafka-internal path. For end-to-end exactly-once semantics, I would use at-least-once delivery combined with an idempotent consumer. The consumer writes to the charges table with the payment_id as a unique key and uses `INSERT ... ON CONFLICT DO NOTHING`. If the message is redelivered, the second write silently no-ops. This achieves end-to-end exactly-once at the application level without the 30% throughput penalty of Kafka transactions."

The L6 answer then adds: "Kafka transactions are appropriate when the exactly-once guarantee needs to span multiple Kafka topics — for example, in a Kafka Streams application that reads from one topic, transforms, and writes to another. In that case, Kafka transactions ensure the read offset commit and the downstream write are atomic."

---

**Question 3: "Consumers are 3 hours behind producers. What do you do?"**

An L5 answer: "Add more consumers to catch up."

An L6 answer starts with diagnosis, because the right intervention depends on the root cause:

- **Step 1: Check partition count.** If consumers = partitions, adding more consumers does nothing — additional consumers will be idle. If consumers < partitions, adding consumers helps.
- **Step 2: Check consumer metrics.** Is the consumer processing slowly (high latency per message)? If yes, the bottleneck is compute, not consumer count. Optimize the processing logic — consider parallelizing work within the consumer using a thread pool for non-sequential operations.
- **Step 3: Check DLQ.** Is the DLQ filling up? If yes, the consumer is encountering errors and retrying repeatedly. Fix the bug first. Adding more consumers does not help if they are all failing on the same poison messages.
- **Step 4: Check producer rate.** Is the lag growing or shrinking? If the producer rate is temporarily elevated (a backfill job, a traffic spike), the lag may drain naturally once the burst ends. Scaling consumers for a burst that will end in 20 minutes is unnecessary operational churn.
- **Step 5: If diagnosis confirms consumer capacity is the bottleneck:** Scale consumers up to partition count. If partition count is already the ceiling and throughput is genuinely insufficient, you must increase partition count — but this requires careful planning because partitions cannot be decreased and key-based routing may become uneven.

The L6 answer does not answer the question by reflexively reaching for the most obvious lever. It treats the system as something to be diagnosed before it is modified.

---

**Question 4: "How do you handle user data deletion requests in a Kafka-based system?"**

This question tests whether you understand a fundamental property of Kafka that many engineers overlook until they face a GDPR audit.

An L5 answer: "Delete the messages from the topic."

This reveals a misconception. Kafka does not support deleting individual messages from a topic. The log is append-only. You can set a topic to compact mode, which retains only the latest message per key, but compaction is asynchronous and does not guarantee immediate deletion. You cannot surgically remove a single user's data from a Kafka partition.

An L6 answer presents the available options with their tradeoffs:

**Option 1: Crypto-shredding.** Encrypt any PII fields in the event using a per-user encryption key stored in a separate key management service. When a user requests deletion, delete their encryption key. The data remains in the Kafka log but is permanently unreadable — cryptographically equivalent to deletion under GDPR. Tradeoffs: adds encryption/decryption overhead to the consumer path, requires robust key management.

**Option 2: Tokenization.** Replace PII fields with a non-PII token at publish time. Store the mapping from token to PII in a separate, access-controlled data store. When a user requests deletion, delete the token-to-PII mapping. Events in Kafka contain only tokens. Tradeoffs: consumers that need the actual PII must call the lookup service, adding latency.

**Option 3: Minimize PII at source.** The cleanest solution is not to put PII in Kafka events at all. Use `user_id` as the event identifier. Consumers that need user details (email, name) look them up from the User Service at time of processing. When a user is deleted from the User Service, all future lookups return nothing. Historical events in Kafka contain no PII.

The L6 answer ends with an operational note: before designing a GDPR deletion mechanism, audit which Kafka topics contain PII and which consumers read them. This audit often surfaces more surprises than the deletion mechanism itself.

---

### How to Structure a Kafka Design Answer in an Interview

The following framework structures a Kafka-related design answer at L6. Use it in sequence. Each step corresponds to a class of decisions that interviewers expect to hear addressed.

**Step 1: Confirm event-driven architecture is appropriate.**
Do not introduce Kafka before justifying it. Say: "Before committing to Kafka, let me confirm the requirements that justify it. There are multiple consumers with different processing needs. Processing can be asynchronous. We need to absorb traffic bursts. We may need to replay events for new consumers. Given these, event-driven with Kafka makes sense." If any of these conditions do not hold, say so and choose a simpler solution.

**Step 2: Define the event schema explicitly.**
Name the fields: "The `OrderPlaced` event will contain `order_id` (UUID, non-null), `user_id` (UUID, non-null), `items` (array of item objects), `total_amount_cents` (integer, non-null), `created_at` (ISO 8601 timestamp). Schema managed with Avro and Schema Registry. `order_id` is required and non-null — validated at the producer before publish."

**Step 3: Choose the partition strategy and explain the reasoning.**
"Partition key is `user_id`. This guarantees that all order events for a single user are processed in order by the same consumer, which is necessary for the order state machine. Partition count is 24 — this supports 24 parallel consumers, which is sufficient for our estimated throughput of 240 MB/sec at 10 MB/sec per partition."

**Step 4: Address delivery semantics and idempotency explicitly.**
"At-least-once delivery. Consumers are idempotent: before processing, check whether `order_id` exists in the `processed_orders` table. If it does, skip processing and commit the offset. If it does not, process and insert in the same transaction. This achieves end-to-end exactly-once at the application level without the overhead of Kafka transactions."

**Step 5: Address failure modes.**
"DLQ after 3 retries. DLQ alert fires within 5 minutes of any message arriving in the DLQ. For order events, the DLQ runbook is: investigate the event, fix the bug in staging, replay the DLQ message after fix. Compensating transactions: if an OrderPlaced event triggers downstream reservation in the Inventory Service and the inventory reservation fails, the saga emits an `OrderCancelled` event and the consumer rolls back the order state."

**Step 6: Address scale and monitoring.**
"Consumer lag SLA: under 30 seconds at steady state. Alert at 10,000 messages of lag. At 30,000 messages, trigger auto-scaling to add consumers up to the partition count ceiling. Metrics to monitor: messages-in per second, consumer lag per partition, DLQ depth, consumer processing latency (p50, p99)."

This framework does not need to be delivered as a numbered list in the interview. It can be presented as a narrative. The important thing is that all six areas are covered — because an interviewer who does not hear you address failure modes will ask about them, and an interviewer who hears you address them proactively will score you higher.

---

### Common L5 Mistakes in Event-Driven Interview Answers

These are the five mistakes that most reliably reveal that a candidate is operating at L5 rather than L6 in a Kafka-related interview question. Being aware of them helps you avoid them, and helps you recognize the shape of the question when an interviewer is probing for one of them.

**Mistake 1: "Use Kafka for everything."**
The tell is that the candidate introduces Kafka before establishing that the requirements justify it. The interviewer probes: "This service just reads user profile data on demand — why Kafka?" A correct L6 answer is: "That is a synchronous read, not an asynchronous event flow — Kafka is not appropriate here. A simple cache or a synchronous API call is the right choice."

**Mistake 2: "Exactly-once means no duplicates end-to-end."**
The tell is the candidate conflates Kafka-internal exactly-once with application-level exactly-once. Kafka's exactly-once semantics (enabled via `enable.idempotence=true` and transactions) cover the path from producer to broker to consumer offset commit. They do not cover the downstream database write. End-to-end exactly-once requires idempotent database writes in addition to Kafka configuration.

**Mistake 3: "Add more partitions to fix any performance issue."**
Partitions are the ceiling on consumer parallelism. Adding partitions only helps if the bottleneck is consumer count. If the bottleneck is slow processing within a single consumer, more partitions and more consumers do not help — each consumer is still slow. Additionally, increasing partition count is irreversible and has costs: more file handles on brokers, slower leader election during failures. Partitions should be sized based on throughput analysis, not added reactively without diagnosis.

**Mistake 4: "Events are fire-and-forget — consumers don't need to care about ordering."**
This is true for some event types (user analytics, click events). It is false for any event type that represents a state machine: financial transactions, order status, inventory levels, account balance changes. These require per-entity ordering. A consumer that processes `OrderCancelled` before `OrderFilled` for the same order will produce an incorrect state, regardless of how robust the consumer logic is.

**Mistake 5: "Kafka can't lose messages — it's a distributed log."**
This conflates Kafka's durability model with its default configuration. Kafka can lose messages if: `acks=1` (default) and the leader broker fails before replicating, `min.insync.replicas=1` (replication factor is set but not enforced for writes), or the topic was created with `replication.factor=1`. Production Kafka for critical data requires `acks=all`, `min.insync.replicas=2`, and `replication.factor=3`. A candidate who says "Kafka can't lose messages" without mentioning these configuration requirements is revealing that they have not been responsible for the configuration of a production Kafka cluster.

---

## What to Carry Into Your Interview

The most important thing to carry into an L6 event-driven interview is not a list of facts about Kafka. It is a mental model of how things fail. Every incident in Section 1 of this chapter follows the same pattern: a system that worked correctly under normal conditions, a small change or a condition that had never been explicitly tested, and a failure mode that was obvious in retrospect but invisible beforehand.

The interviewer is trying to find out if you have built that mental model from experience — or if you have only read about Kafka at a conceptual level. The way they find out is by asking follow-up questions: "What happens if that consumer crashes between reading the message and committing the offset?" "What if the partition count is already maxed out?" "How do you handle a GDPR deletion request for events that were published two years ago?" 

Candidates who have operated these systems at scale answer those questions naturally, because they have seen what happens. Candidates who have only studied these systems answer them haltingly, because they are reasoning from principles rather than from experience.

The goal of this chapter is to give you enough of the experience — in compressed, narrative form — that you can answer like the former, even if your direct exposure has been at smaller scale.

---

*Part F covers design exercises and brainstorming prompts for self-assessment.*
# Chapter 33: Event-Driven Architectures — Kafka and Streams
## Part F: Brainstorming Questions, Exercises, and Quick Reference

This is the final section of Chapter 33. It contains everything you need to pressure-test your understanding: cross-topic design questions organized by theme, six graded homework exercises with L6 hints, and a quick reference card you can use during interviews.

Work through the brainstorming questions before looking at the exercises. The questions are deliberately open-ended — there is no single correct answer. The goal is to surface the tradeoffs you can articulate under pressure.

---

## Cross-Topic Brainstorming Questions

Twenty questions across four themes. Spend at least five minutes on each before moving on. If you can answer in under a minute, you are not going deep enough.

---

### Theme A: Kafka Architecture Design

**Question 1 — Real-Time Fraud Detection**

You need to build a real-time fraud detection system that processes 500K payment events per second with less than 100ms latency from event to decision. Design the Kafka architecture: topic structure, partition strategy, consumer architecture, and how you handle the 100ms SLA when your fraud model takes 80ms to run.

Start by budgeting your latency. If the model takes 80ms, you have 20ms left for: Kafka produce (network + broker ack) + Kafka fetch + consumer deserialization + response write. That is tight. You need to think about producer acks=1 vs acks=all (acks=all adds replication latency), fetch.min.bytes=1 (don't batch on the consumer side), and likely co-locating the consumer close to the broker. Ask yourself: should the fraud model run inside the consumer thread, or should the consumer delegate to an async model-serving tier? If async, you have a second hop and now your 20ms budget is gone. Think about how to use a **synchronous call within the consumer loop** combined with a timeout fallback (allow the transaction, flag for review) to protect the SLA. For partition strategy: partition by card number or user ID so that sequential transactions for the same card land on the same partition and your model can access recent transaction history without cross-partition lookups.

Key tensions to address: throughput (500K/sec) vs. latency (100ms) vs. correctness (don't miss fraud). Replication factor 3 with acks=all gives durability but costs ~5–10ms per produce. acks=1 cuts that cost but risks losing messages on broker failure. For a payment system, document your choice and the tradeoff explicitly.

---

**Question 2 — GPS Updates for Ride-Sharing**

A ride-sharing platform has 10 million active drivers sending GPS updates every 5 seconds. These updates need to be consumed by: a real-time matching service, an ETA prediction service, a driver monitoring dashboard, and a data lake. Design the Kafka topic structure and consumer group strategy. How do you handle a driver sending 100× normal GPS updates due to a bug?

The four consumers have wildly different latency and throughput requirements. The matching service needs the latest location within seconds. The data lake can tolerate minutes of lag and cares more about completeness. The dashboard probably fans out to websocket connections and does not need every update — just the most recent one. This suggests a **compacted topic** for current driver location (only the latest value per driver key matters) and a separate **non-compacted topic** for full GPS history (needed by data lake and ETA model that uses trajectories).

For the 100× flood: a single driver sending 100× means that one partition (keyed by driver ID) gets flooded if that driver happens to own a hot key. Your options are: (a) **rate limiting at the producer gateway** before events reach Kafka — this is the cleanest fix, (b) **consumer-side deduplication** using a timestamp check (if two events for the same driver arrive within 1 second, drop the second), or (c) Kafka Streams with a **suppress** operator to emit only the latest per driver per 5-second window. Option (a) is best because it prevents the flood from even consuming broker I/O.

---

**Question 3 — Social Media Post Created Event**

You are designing the event system for a social media platform. A "post created" event needs to reach: feed service (fan-out to followers), search indexing service, moderation service, analytics service, and CDN cache invalidation. The platform has influencers with 50M followers. Design the Kafka architecture for post events.

The core problem is fan-out at scale. When an influencer posts, the feed service needs to fan out to 50M followers. If feed-service is a Kafka consumer, it reads one event and does 50M writes. That is not a Kafka problem — Kafka has delivered the event fine. The fan-out is an application-level design challenge. At L6 you are expected to recognize this distinction.

For the Kafka layer: a single **post-created** topic with partitioning by user_id (or post_id). All five consumers use separate consumer groups. Each gets all events independently. The topic should have enough partitions for peak write throughput — if influencers generate 100K posts/min at peak, that is roughly 1,700 posts/sec, trivially handled by 20–50 partitions.

The interesting design question is: should the feed service receive the raw "post created" event and do its own fan-out, or should there be a **fan-out service** upstream of Kafka that publishes individual "add to feed" events per follower? The second approach explodes message count (50M events per influencer post) but makes downstream feed consumers simple. The first keeps Kafka clean but requires the feed service to handle fan-out internally. Most production systems (Twitter, Instagram) use a hybrid: pre-compute fan-out for non-celebrity accounts, and pull-on-read for celebrity accounts.

---

**Question 4 — Migration from REST to Event-Driven**

An e-commerce platform currently uses REST APIs between its 20 microservices. Response times are degrading because Service A waits for Service B, which waits for Service C. How do you migrate to event-driven without a big-bang rewrite? What is the migration sequence?

The anti-pattern to avoid is migrating all 20 services simultaneously. The big-bang approach means you are running distributed systems risk across the entire platform during the migration window.

The L6 approach is **strangler fig**: introduce Kafka incrementally, one integration at a time. Start with the integration that: (a) is genuinely async (the caller does not need an immediate response), (b) has a clear event boundary, and (c) is not in the critical path for the most common user flows. Good candidates: "order placed" → send confirmation email. Bad candidates: "check inventory" (synchronous, user waits for the answer).

Migration sequence for a single integration: (1) add a Kafka producer to Service A that publishes the event in addition to the existing REST call (dual-write temporarily), (2) build the consumer in Service B reading from Kafka, (3) run both paths in parallel and compare results, (4) cut over traffic to the Kafka path, (5) remove the REST call. Repeat for the next integration. At each step you have a rollback path: revert to REST if Kafka misbehaves.

The migration also requires organizational change: teams that owned REST contracts now own event schemas. Schema Registry and schema versioning become first-class concerns. Plan for this explicitly.

---

**Question 5 — Healthcare with Mixed Latency Requirements**

You are designing a Kafka cluster for a healthcare application. Patient monitoring data: 50K devices, each sending vitals every second (50K events/sec total). Some vitals are critical — abnormal heart rate must trigger alerts within 1 second. Others — temperature — can be processed in batch. How do you architect this with different latency requirements on the same platform?

The naive design puts all vitals in one topic. The problem: a slow consumer processing temperature readings shares resources with the alert consumer and can cause rebalances or lag that bleeds into alert latency.

The right design uses **separate topics by criticality**: a **vitals-critical** topic (heart rate, SpO2, blood pressure) and a **vitals-batch** topic (temperature, weight, activity). Critical topic gets: higher replication acknowledgment (acks=all), dedicated consumer group with zero shared consumers, alert service is the only consumer and it is sized to maintain zero lag permanently.

For the 1-second SLA: the full pipeline is produce → broker replicate → consumer fetch → alert publish. With acks=all and replication factor 3, produce latency is ~10–20ms. Consumer max.poll.interval.ms and fetch.max.wait.ms must be tuned to near-zero wait: fetch.max.wait.ms=10ms, fetch.min.bytes=1. Your consumer does a point lookup against device baseline (stored in local RocksDB or in-memory cache) and publishes an alert event. End-to-end this is achievable in under 200ms, well inside 1 second.

For the batch topic: relaxed consumer settings, larger batches, higher throughput, lower cost infra.

---

### Theme B: Delivery Semantics and Correctness

**Question 6 — Exactly-Once Payment Charging**

A subscription service charges users monthly. The "charge user" event is published to Kafka. If the consumer crashes after charging but before committing the offset, the charge runs again on restart. Design a solution that ensures users are charged exactly once even with consumer failures. Be specific about database schema, Kafka config, and consumer code flow.

This is the canonical exactly-once problem in event-driven systems. Kafka's transactional producer solves exactly-once for Kafka-to-Kafka flows, but the problem here crosses the Kafka boundary into a payment processor (Stripe, Braintree, etc.), which has its own state.

The solution is **idempotency at the consumer side**: before charging, check whether this event has already been processed. Schema: a table `charge_attempts(event_id VARCHAR PRIMARY KEY, user_id BIGINT, charged_at TIMESTAMP, result VARCHAR)`. Consumer code flow: (1) deserialize event, extract event_id, (2) `INSERT INTO charge_attempts(event_id, ...) ON CONFLICT(event_id) DO NOTHING` — if this returns 0 rows affected, the charge already happened, skip and commit offset, (3) if insert succeeds, call payment processor, (4) update charge_attempts with result, (5) commit Kafka offset. If the consumer crashes between step 3 and step 5, on restart it re-reads the event, tries the insert again, gets 0 rows affected, skips. The charge does not run twice.

One subtlety: the payment processor itself must support idempotency keys (Stripe does — pass event_id as idempotency_key). Without this, a crash between the charge API call returning and the DB insert could still double-charge if the API call succeeded but the DB write failed.

---

**Question 7 — Inventory Below Zero**

An inventory system needs to process "order placed" events and decrement stock. At 10K orders/second during Black Friday, stock for a popular item reaches 0. Events for that item continue arriving. How do you handle: (a) not decrementing below 0, (b) notifying producers of failure, (c) processing resuming when stock is replenished?

Part (a) is a database-level concern: `UPDATE inventory SET stock = stock - 1 WHERE item_id = ? AND stock > 0`. If this updates 0 rows, the order cannot be fulfilled. The consumer publishes an **order-rejected** event to an "order-outcomes" topic. Producers (or a downstream notification service) consume order-outcomes and notify the user.

Part (b) — notifying producers — highlights a core event-driven inversion: in REST, the caller gets a synchronous error response. In event-driven, the producer must subscribe to an outcome topic or use a request-reply pattern (producer includes a reply-to topic name in the event header and waits on that topic). For L6: design the **order-outcomes topic** as a single topic keyed by order_id, with all consumers (notification service, user-facing API waiting on a correlated response) reading from it.

Part (c) — resuming on replenishment — means the rejected orders sitting in the DLQ or a "pending-fulfillment" store need to be re-evaluated. When a "stock replenished" event arrives, trigger a reprocessing of pending orders for that item_id, in arrival order (FIFO). This is a mini-saga embedded inside the inventory domain.

---

**Question 8 — Cross-Service Ordering on a Shared Topic**

Two services (Order and Payment) both write to the same Kafka topic "account-ledger." Order service uses key=order_id, Payment service uses key=payment_id. A consumer needs to process all events for a given user in order — order events and payment events for user 123 must be ordered relative to each other. Is this possible with the current setup? How do you redesign?

With the current setup: no. Kafka ordering is guaranteed only within a partition. Events for user 123's orders go to partition hash(order_id) % N. Events for user 123's payments go to partition hash(payment_id) % N. These will almost certainly land on different partitions. There is no guarantee about relative ordering across partitions.

The redesign: both Order and Payment services must use **key=user_id** when writing to account-ledger. All events for user 123 now land on the same partition (hash(user_id) % N) regardless of which service produced them. Ordering is preserved.

But now you have a new problem: high-volume users create hot partitions. A user who generates 1,000 orders/minute (a merchant API, maybe) causes one partition to receive 1,000 events/minute while others receive 10. Solutions: (a) add a salt suffix to the key for high-volume users (user_id + shard_index) — breaks strict per-user ordering but distributes load, (b) separate topics per service and join them in a Kafka Streams co-partitioned join — this requires both topics to have the same number of partitions and the same key scheme.

The L6 insight: **global ordering across producers on a shared topic requires coordination on partition key**. This coordination is an organizational contract, not a Kafka feature. Enforce it via schema validation at the producer level.

---

**Question 9 — Event Sourcing Bootstrap at Scale**

You are using Kafka for an event sourcing system. The "account balance" is derived by replaying all "transaction" events from offset 0. The topic has 10 years of data (1TB). A new service needs to bootstrap and get the current balance for all accounts. How do you handle initial startup time? How do you handle schema evolution over 10 years of events?

Replaying 1TB from offset 0 on startup is impractical — it could take hours and blocks the service from being usable.

The solution is **periodic snapshotting**: every N events (or every 24 hours), persist the current state of all account balances to a durable store (PostgreSQL, S3). Store alongside each snapshot the Kafka offset of the last event included. On startup: load the latest snapshot (fast — it is a bulk read from the state store) and replay only the events published after the snapshot's offset. If snapshots are taken daily, startup requires replaying at most 24 hours of events instead of 10 years.

Schema evolution is harder. Over 10 years, the "transaction" event schema has changed multiple times. The new service must be able to deserialize events from 2014 with the old schema and events from 2024 with the new schema. The L6 solution is **Avro with Schema Registry**: every event is produced with a schema ID embedded in the binary payload. The consumer uses the schema ID to fetch the correct reader schema from Schema Registry and applies **schema resolution** (Avro's built-in backward/forward compatibility). Old fields that no longer exist are ignored. New fields that did not exist in old events get default values. This requires that all schema changes are backward-compatible (no removing required fields, no changing field types incompatibly).

---

**Question 10 — Late Arrivals in Stream Processing**

A service publishes "temperature reading" events from IoT sensors. Due to network issues, some readings arrive 5 minutes late (event time vs. ingestion time). The analytics system wants to compute "average temperature in 5-minute windows" accurately, including late arrivals. Design the stream processing architecture.

The standard approach: use **event time** (the timestamp embedded in the event) rather than processing time (when Kafka received it) for windowing. Kafka Streams and Apache Flink both support event-time processing with configurable **watermarks** — a heuristic that says "I will wait up to W minutes after the end of a window before finalizing the result, to accommodate late arrivals."

With a 5-minute allowed lateness: the window for 14:00–14:05 does not emit a final result until 14:10. Events arriving up to 5 minutes late are included. Events arriving more than 5 minutes late are dropped (or sent to a late-data sink for separate processing).

For L6: the tradeoff is accuracy vs. result latency. A 5-minute watermark means your dashboard shows results that are 5 minutes stale. If real-time latency matters more, use a 30-second watermark and accept that a small fraction of very-late events are dropped. Emit **preliminary results** as events arrive, and **corrected final results** after the watermark passes. The downstream dashboard must handle "this result may be updated."

Store windowed state in a local RocksDB state store (Kafka Streams default). The state store is changelog-backed to a Kafka topic, so it survives consumer failures.

---

### Theme C: Failure Modes and Operational

**Question 11 — Consumer Lag Growing at 3 AM**

Your Kafka consumer group for "payment-confirmations" topic suddenly shows lag growing at 5,000 messages/minute. The on-call page fires at 3 AM. Walk through your diagnosis checklist. What metrics do you look at first? What are the five most likely root causes? What is your first remediation action for each?

**First metrics**: consumer group lag per partition (which partitions are lagging — all of them or specific ones?), consumer instance count (are all instances running?), consumer throughput (messages processed/sec — has it dropped?), GC pause time (Java consumers), downstream dependency latency (database, external API — is the consumer blocked on a slow dependency?).

**Five most likely root causes and remediations**:

1. **Consumer instances crashed or were killed**: remediation — restart consumer instances, investigate why they crashed (OOM? unhandled exception?).
2. **A slow external dependency** (database, downstream API) is blocking consumer processing: remediation — circuit-break the dependency, allow consumers to process with degraded functionality (skip the slow call, emit to a retry topic).
3. **A poison message** is causing crash-loop on one or more partitions: remediation — identify the bad offset, skip it via offset manipulation, route to DLQ, deploy fix.
4. **A deployment introduced a regression** that slowed processing per message: remediation — rollback the deployment immediately, investigate during business hours.
5. **Traffic spike** — legitimate volume increase (Black Friday, viral event) exceeded consumer capacity: remediation — scale out consumer instances (add more instances up to the partition count limit), increase partition count if you have exhausted instances.

The single most important question to answer first: "Is lag growing on all partitions or specific partitions?" All partitions → systemic problem (deployment, dependency). Specific partitions → localized problem (poison message, hot partition, specific consumer instance failure).

---

**Question 12 — Broker Failure in a 3-Broker Cluster**

A Kafka broker fails in your 3-broker cluster. Which partitions are affected? What is the impact on producers and consumers? How long until the system is fully recovered? What if the failed broker was also the controller? Design your cluster configuration to minimize blast radius.

**Which partitions are affected**: only partitions for which the failed broker is the **leader**. Partitions where the failed broker is a follower are unaffected — they continue serving from the remaining leader. With replication factor 3 and 3 brokers, roughly one-third of partitions have their leader on any given broker.

**Impact timeline**: from the moment the broker fails, the Kafka controller (another broker) detects the failure via ZooKeeper or KRaft session expiration (~10–30 seconds depending on session.timeout.ms configuration). It then elects new leaders for the affected partitions from the in-sync replica (ISR) list. This takes 15–30 seconds in practice. During this window, producers with acks=all see errors and must retry. Consumers cannot fetch from affected partitions.

**If the failed broker was the controller**: there is an additional step — another broker must be elected as the new controller first, and then that new controller can elect partition leaders. This adds 5–15 seconds to the recovery time.

**Minimizing blast radius**: (a) set `min.insync.replicas=2` so writes require at least 2 replicas (prevents silent data loss), (b) distribute partition leaders evenly across brokers using `kafka-preferred-replica-election.sh` periodically, (c) use 5 or more brokers in production — with 3 brokers, losing one means 33% of your capacity is affected; with 6 brokers, it is 17%, (d) use KRaft mode (Kafka 3.x) to eliminate ZooKeeper — this reduces controller failover time significantly.

---

**Question 13 — Poison Message at Offset 10,000**

A malformed event that crashes your consumer is sitting in partition 3 at offset 10,000. There are 500,000 messages behind it waiting to be processed. Your DLQ has a 1-hour retry delay. Walk through the immediate remediation steps. How long will your backlog take to clear?

**Immediate remediation**:

Step 1: stop the consumer group to prevent further crash-looping (every loop wastes time and may cause excessive rebalances).

Step 2: use `kafka-consumer-groups.sh --reset-offsets --to-offset 10001 --topic my-topic --partition 3 --group my-consumer-group` to manually advance the consumer group's committed offset past the poison message. This effectively skips offset 10,000.

Step 3: separately, consume offset 10,000 manually (`kafka-console-consumer.sh --partition 3 --offset 10000 --max-messages 1`) to capture the bad message for investigation. Write it to your DLQ manually or via a one-off script.

Step 4: restart the consumer group. It now starts from offset 10,001 and processes the 500,000 backlog messages.

**Backlog clearance time**: depends on consumer throughput. If the consumer processes 5,000 messages/sec with 20 instances across 20 partitions, partition 3 is being processed by one instance. If that instance handles 250 messages/sec, the 500,000 backlog clears in 500,000 / 250 = 2,000 seconds (~33 minutes). The DLQ 1-hour retry delay is irrelevant here because you skipped the poison message directly — it does not go through the DLQ retry cycle.

**Prevention**: implement a **max retry count** per message at the consumer level. After N failures, route to DLQ immediately without retrying indefinitely.

---

**Question 14 — Schema Registry Goes Down**

Your Schema Registry goes down. Producers that need to register new schemas fail. Producers using cached schemas still work. Consumers using cached schemas still work. What is the blast radius? What is your runbook? How do you design Schema Registry for HA?

**Blast radius analysis**: existing producers with cached schemas continue publishing — they do not need to contact Schema Registry for every message, only when registering a new schema or fetching an uncached schema. Existing consumers with cached schemas continue consuming. New deployments of producers or consumers that have not yet cached schemas will fail on startup (they cannot fetch the schema). Any producer attempting to register a new schema version fails.

**Runbook**:

1. Confirm Schema Registry is down (health check endpoint).
2. Check if Schema Registry pods/instances can be restarted (OOM? disk full? dependency failure?).
3. If not immediately recoverable: freeze all deployments that involve new schema registrations. Existing deployments continue running.
4. If Schema Registry is backed by Kafka (it stores schemas in a Kafka topic `_schemas`), verify that Kafka itself is healthy. Schema Registry is stateless modulo its Kafka-backed store.
5. Restore Schema Registry from its Kafka-backed state (restart instances — they will reload schemas from the `_schemas` topic).

**HA design**: run Schema Registry as a horizontally scaled cluster (3+ instances) behind a load balancer. Each instance is stateless — state is in the `_schemas` Kafka topic. Use active-active mode. If one instance fails, traffic routes to others. Configure producers and consumers with `schema.registry.url` pointing to the load balancer, not individual instances. For multi-region: run Schema Registry in each region reading from a replicated Kafka cluster, with the primary region as the authoritative writer.

---

**Question 15 — Analytics Consumer 24 Hours Behind**

An analytics consumer is 24 hours behind on a topic with 7-day retention. At its current rate, it will never catch up before the oldest messages expire. What are your options? What if the events it will miss are required for regulatory reporting?

**Why it cannot catch up**: if the consumer processes messages at the same rate they are produced, the lag stays constant. To catch up, it must process faster than the production rate. If production is at 100% capacity and the consumer is at 100% capacity, it will never close the gap.

**Options**:

1. **Scale out the consumer**: add more instances (up to the partition count). If the topic has 20 partitions and you have 5 consumer instances, adding 15 more instances quintuples throughput. The consumer can now process 5× production rate and will close the gap.

2. **Temporarily increase partition count**: more partitions allow more parallel consumers. Note: this does not rebalance existing messages — old partitions keep their data.

3. **Optimize the consumer**: profile the consumer code. Is it doing unnecessary database calls per message? Can it batch writes? A 5× throughput improvement may be possible without adding hardware.

4. **Accept partial catch-up**: if retention is 7 days and the consumer is 24 hours behind with 6 days of retention remaining, the consumer just needs to catch up within 6 days. Scale-out to 2× production rate closes a 24-hour gap in 24 hours.

**For regulatory reporting**: if the messages that will expire are required for compliance, you must **archive them before they expire**. Options: (a) use `kafka-dump-segment.sh` to export the oldest segments to S3 before they are deleted — do this immediately as a firefighting action; (b) configure a separate S3 sink connector on the topic with no retention dependency — this should have been in place from the start for any topic with regulatory requirements; (c) restore from a Kafka backup if one exists. After recovery, implement a permanent rule: regulatory topics must have a durable archive consumer (S3 sink) with its own consumer group, separate from the analytics consumer, so that expiry risk is decoupled.

---

### Theme D: Advanced Design

**Question 16 — Distributed Payment Saga**

Design a distributed payment saga for this flow: debit user A's account, credit user B's account, send confirmation to both users. The accounts are in different databases. Design using both choreography and orchestration. Which do you recommend and why?

**Choreography**: each service listens for events and publishes its own outcome events. Flow: (1) Payment service publishes "debit-initiated" event, (2) Account-A service listens, debits, publishes "debit-completed" or "debit-failed," (3) Account-B service listens for "debit-completed," credits, publishes "credit-completed" or "credit-failed," (4) if "credit-failed," Account-A service listens and publishes a compensating "debit-reversed" event, (5) Notification service listens for final outcome events. No central coordinator — each service acts autonomously.

**Orchestration**: a Saga Orchestrator service manages the flow explicitly. It sends commands (not events) to each service: "debit-account-A," receives responses, then sends "credit-account-B," receives response, then sends "send-confirmation." On failure, the orchestrator sends compensating commands in reverse order. The orchestrator persists its state to a database after each step.

**Recommendation for payments**: orchestration. Payments require explicit state tracking, auditability, and the ability to answer "what step is saga XYZ currently on?" Choreography creates implicit state spread across multiple event streams — debugging a failed saga requires correlating events across multiple topics. With money movement, the ability to see the saga state in a single database row (status: DEBIT_COMPLETED, last_updated: 14:32:05) is operationally invaluable. The complexity cost of an orchestrator is worth it for financial workflows.

---

**Question 17 — Real-Time Analytics Dashboard**

A startup wants to build a real-time analytics dashboard showing: total revenue today, top 10 products by sales in the last hour, anomaly detection for fraud patterns. Data source: 50K orders/hour in Kafka. Design the stream processing pipeline. Include windowing strategy and state management.

Three different computation patterns requiring three different approaches:

**Total revenue today**: a **session window** or a **tumbling window** of 24 hours anchored to midnight. Since you need a running total (not a final result), use Kafka Streams with a **KTable** that accumulates revenue. On each order event, aggregate into a daily revenue accumulator stored in a local RocksDB state store. Emit an updated total on every new event. The dashboard reads from the output topic.

**Top 10 products in last hour**: a **sliding window** of 60 minutes. As new orders arrive, add them to the window. As the window slides, remove orders older than 60 minutes. Maintain a count per product_id within the window. Computing "top 10" requires a full sort of the product count map — do this every 30 seconds (scheduled, not per-event) to avoid O(N) sort on every order. Output: a small "top-10-products" topic that the dashboard polls.

**Anomaly detection**: this is stateful pattern matching. For example: more than 5 orders from the same user IP in 10 minutes, or an order amount 10× higher than that user's historical average. Use a **session window** keyed by user_id with a 10-minute inactivity gap. Store per-user historical average in the state store (updated incrementally using exponential moving average). On each order, compare against the stored baseline and emit an anomaly alert event if the threshold is exceeded.

State management: all three use RocksDB-backed state stores with Kafka changelog topics. On consumer restart, state is restored from the changelog. For the dashboard: a separate query service reads from the output topics and serves the UI over WebSocket or SSE.

---

**Question 18 — Monolith to Microservices Without Distributed Transactions**

You are migrating a monolithic e-commerce application to microservices. The monolith uses database transactions for: place order, reserve inventory, charge payment, send confirmation — all in one transaction. How do you implement this across 4 microservices without distributed transactions? What consistency guarantees can you offer users?

The distributed transaction equivalent in microservices is a **saga**. You cannot have ACID across 4 databases. What you can offer:

**Eventual consistency with compensation**: the saga succeeds in the happy path with strong guarantees (user is charged exactly once, inventory is decremented exactly once). On failure, compensating transactions undo completed steps. The system is eventually consistent — there is a window where an order exists but payment has not been confirmed.

**What users experience**: after clicking "Place Order," users see "Order being processed" rather than instant confirmation. The confirmation email arrives seconds later when the saga completes. This is already the user experience on Amazon and most e-commerce platforms.

**Specific guarantees you can offer**:
- You will never charge a user without decrementing inventory (the saga's compensation logic ensures this).
- You will never decrement inventory without charging the user (same logic).
- You may fail to send a confirmation email (the notification step), but this does not affect the financial transaction. Compensate by retrying the notification independently.
- Duplicate protection: all saga steps must be idempotent (idempotency keys on payment, upsert on inventory reservation).

The honest answer for an L6 interview: "We offer eventual consistency with bounded inconsistency window (typically under 5 seconds) and compensating transactions for failure cases. We do not offer serializability across services, and we design the user experience to accommodate asynchronous confirmation."

---

**Question 19 — Food Delivery Platform at Scale**

Design the event architecture for a food delivery platform at scale. Events: order placed, restaurant accepted, courier assigned, food picked up, delivered. 10M orders/day, 3 countries, different regulatory requirements per country. How do you structure topics, handle cross-country data residency, and provide real-time order tracking?

10M orders/day is ~115 orders/second average, with significant peaks at mealtimes (potentially 10–20× average, so 1,000–2,000 orders/second at peak). This is modest by Kafka standards.

**Topic structure**: one topic per event type (order-placed, restaurant-accepted, courier-assigned, food-picked-up, order-delivered), partitioned by order_id. This gives clean separation of concerns — each downstream service subscribes only to the event types it cares about. Country is encoded as metadata in the event, not in the topic name (you do not want 15 topics per country × 5 event types = 75 topics).

**Data residency**: EU GDPR and other regulations require that PII (customer name, address, payment info) not leave the country of the order. Approach: run **separate Kafka clusters per country** (EU cluster, US cluster, IN cluster). The topic structure is identical in each cluster. Services that aggregate cross-country analytics receive only non-PII fields (order count, category, timestamp) via a separate anonymized topic that can cross borders. Cross-country replication of non-PII data uses MirrorMaker 2.

**Real-time order tracking**: the tracking UI needs sub-second updates as courier location changes. This is not a Kafka consumer — Kafka latency is fine for backend state changes, but pushing updates to mobile apps requires WebSocket or Server-Sent Events from a stateful presence service. The presence service consumes "courier location" events from Kafka and fans out to connected mobile clients via WebSocket. The event pipeline feeds the presence service; the presence service feeds the user.

---

**Question 20 — GDPR Right to Be Forgotten in Kafka**

Your company needs to implement GDPR "right to be forgotten" for a system where user activity events are stored in Kafka topics with 2-year retention. You have 50M users. Walk through the technical implementation that allows deleting a specific user's personal data from the event stream without corrupting the event history for other users.

You cannot delete individual Kafka messages. Kafka is an append-only log. Even with compaction, compaction only removes earlier versions of the same key — it does not selectively delete messages based on content.

The solution is **crypto-shredding**:

1. When a user's PII (name, email, address) is embedded in an event, **encrypt it using a per-user AES-256 key** before publishing to Kafka. Non-PII fields (event type, product ID, timestamp) remain unencrypted.

2. Each user has a unique encryption key stored in a **Key Management Service** (AWS KMS, HashiCorp Vault). The Kafka event payload contains: `{ "user_id": 123, "encrypted_pii": "<ciphertext>", "event_type": "purchase", "product_id": 456 }`.

3. On a GDPR deletion request: **delete the user's key from KMS**. The ciphertext in Kafka now cannot be decrypted by anyone. The data is effectively deleted — even though the bytes remain on disk, they are permanently unreadable. From GDPR's perspective, unreadable data is considered deleted by most European data protection authorities (this interpretation is widely accepted but worth confirming with your legal team).

4. For downstream services that cached the decrypted PII: publish a **"user-deletion-requested"** event to a dedicated topic. Each downstream service must subscribe, find all records for user_id=123, and delete or anonymize them. Track completion per service — GDPR requires you to ensure all systems comply, not just Kafka.

5. SLA: GDPR requires deletion "without undue delay," typically interpreted as within 30 days. The key deletion from KMS is instant. Downstream service cleanup can be async within the 30-day window.

6. **Proving deletion to regulators**: maintain a `deletion_audit` table: `(user_id, deletion_requested_at, kms_key_deleted_at, downstream_services_notified_at, completion_confirmed_at)`. Each downstream service acknowledges completion via a "deletion-confirmed" event. The audit table provides the evidence trail for regulatory audit.

---

## Homework Exercises

Six exercises at increasing complexity. Do them in order. Timings are guidelines — at L6 you should be able to complete each within the suggested window under interview pressure.

---

### Exercise 1: Design Kafka for a Notification Platform (45 minutes)

**Scenario**: 100 million users, 15 notification types (email, push, SMS, in-app), three priority levels — critical (password reset, security alerts), high (order updates, delivery status), low (marketing, promotions). Peak load: 10 million notifications in 5 minutes after a major product event.

**What to design**:

1. **Topic structure**: how many topics? What naming convention? What partition keys?

2. **Consumer groups**: how many consumer groups? How are they organized?

3. **Priority handling**: critical notifications must not be delayed by a backlog of marketing messages. How do you ensure this?

4. **Deduplication**: a consumer crash after sending but before committing the offset means the user gets the same notification twice. How do you prevent this?

5. **DLQ strategy**: design different DLQ behavior for critical vs. low-priority notifications.

6. **Scale**: 10 million notifications in 5 minutes = 33,000 per second burst. How does your design handle this?

**L6 hint**: Use separate topics by priority level: `notifications-critical`, `notifications-high`, `notifications-low`. Critical topic gets a dedicated consumer group with 100 partitions and auto-scaling configured at lag > 1,000. Deduplication: include a `notification_id` (UUID) in each event. Before sending, insert `notification_id` into a `notification_log` table with `ON CONFLICT DO NOTHING`. If the insert fails (conflict), skip — already sent. DLQ for critical: retry every 30 seconds for 2 hours, then page on-call. DLQ for low-priority: retry once after 5 minutes, then drop (marketing notifications are not worth indefinite retry). For the 33K/second burst: with 100 partitions and 100 consumer instances each processing 500 notifications/second, total throughput is 50,000/sec — enough headroom.

---

### Exercise 2: Event Sourcing for a Bank Account (30 minutes)

**Scenario**: implement event sourcing for a bank account system. Events: AccountOpened, MoneyDeposited, MoneyWithdrawn, AccountClosed.

**What to design**:

1. **Event schema**: what fields does each event type contain?

2. **Balance computation**: how do you compute the current balance from the event stream?

3. **Point-in-time query**: how do you answer "what was the user's balance on March 15?"

4. **Slow startup**: the account has 10 years of events (500K events). How do you handle the startup time for a new service instance?

5. **Schema evolution**: you need to add a `fee_type` field to MoneyWithdrawn. How do you handle old events that do not have this field?

**L6 hint**: Add snapshotting every 1,000 events. Snapshot schema: `{ account_id, balance, last_event_offset, snapshot_taken_at }`. On new service startup: load the latest snapshot, then replay only events with offset > `last_event_offset`. For point-in-time queries: replay from offset 0 but stop at the first event with `event_time > target_date` — or, if you have daily snapshots, load the snapshot from the day before the target date and replay that one day's events only. For schema evolution: define events in Avro with default values. Old MoneyWithdrawn events without `fee_type` receive the default value `"NONE"` via Avro schema resolution. No migration needed.

---

### Exercise 3: Debug the Consumer Lag Incident (20 minutes)

**Scenario**: at 14:32, your PagerDuty alert fires: "order-processor consumer group lag exceeds 100,000 messages for 5 minutes." Historical context: lag was 0 at 14:20. A deployment happened at 14:25. The topic has 20 partitions. The consumer group has 20 instances.

**Work through these steps**:

1. What Kafka commands do you run first?

2. You see that 15 partitions have 0 lag. 5 partitions each have 20,000 messages of lag. What does this tell you?

3. You see in consumer logs: `CommitFailedException: Commit cannot be completed since the consumer is not part of an active group`. What happened?

4. You find 5 consumer instances are crash-looping with `NumberFormatException: For input string 'null'`. What likely changed in the deployment?

5. What is your immediate fix? What is your prevention strategy?

**L6 hint**:

Step 1: `kafka-consumer-groups.sh --describe --group order-processor` — shows lag per partition, current offset, end offset, and which consumer instance owns each partition.

Step 2: 5 partitions lagging with 15 at 0 means a subset of consumer instances have failed and their partitions have been reassigned. The reassigned partitions are being processed by the remaining healthy instances, but those instances cannot keep up — they now own more partitions than they were sized for.

Step 3: `CommitFailedException` occurs when `max.poll.interval.ms` is exceeded. The consumer was assigned partitions but took too long between poll() calls (because it was busy processing or crashing), so the coordinator removed it from the group and triggered a rebalance.

Step 4: the deployment changed a message schema — a new field that is null in messages produced before the deployment, but the new consumer code calls `Integer.parseInt()` on it without a null check. Old messages crash the consumer. The deployment introduced a backward-incompatible consumer change.

Step 5: immediate fix — rollback the deployment or hot-patch with a null check. The 5 crashed instances recover, rejoin the consumer group, their partitions are reassigned back to them, and the backlog clears. Prevention: require null checks for all new schema fields; use Avro with default values so null is impossible at the deserialization layer; run consumer tests against old message formats before deployment.

---

### Exercise 4: Design GDPR Deletion in Kafka (30 minutes)

**Scenario**: a user requests "delete all my data" under GDPR. Your system has a Kafka topic "user-events" with 2-year retention and 10 billion events for 50 million users. Fifteen downstream services consume this topic. Kafka is used for event sourcing — users can replay their own history.

**What to design**:

1. Why can you not delete specific Kafka messages directly?

2. Describe the crypto-shredding approach in detail. What is the key management strategy?

3. How do you handle the 15 downstream services that may have cached user data?

4. What is the SLA for deletion? How does crypto-shredding meet GDPR's "undue delay" requirement?

5. How do you prove to regulators that the data has been deleted?

**L6 hint**: Kafka is an immutable append-only log. Individual message deletion is not supported. Kafka compaction can remove old versions of the same key, but it cannot selectively delete messages based on content fields. Crypto-shredding: each user gets a unique AES-256 encryption key stored in AWS KMS or HashiCorp Vault. PII fields in events are encrypted before publishing. On deletion request: delete the key from KMS (takes milliseconds). All encrypted events for this user are now permanently unreadable. For downstream services: publish a `UserDeletionRequested` event to a dedicated `gdpr-deletion-requests` topic. Each service subscribes, deletes its local user data, and publishes a `UserDeletionConfirmed` event. Track completion in a `gdpr_audit` table. The KMS deletion is instant, so the SLA is met immediately even though downstream cleanup runs asynchronously within the 30-day window. Regulatory proof: the `gdpr_audit` table with timestamps of KMS key deletion and per-service confirmation events.

---

### Exercise 5: Saga for Hotel Booking (45 minutes)

**Scenario**: design a saga for booking a hotel room. Steps: (1) reserve room in Inventory Service, (2) charge credit card in Payment Service, (3) send confirmation email in Notification Service, (4) update loyalty points in Loyalty Service.

**Design both choreography and orchestration versions. For each**:

1. Draw the event or command flow for the happy path and the compensation path.

2. What happens if Step 2 (charge) fails?

3. What happens if the orchestrator crashes between Step 1 and Step 2?

4. How do you track saga state?

5. What is the user experience during compensation?

**L6 hint**:

Choreography compensation on payment failure: Payment Service publishes `PaymentFailed` event. Inventory Service listens for `PaymentFailed` and publishes `RoomReservationCancelled`. Notification Service listens and sends a "booking failed" email. Problem: what if Inventory Service is temporarily down when `PaymentFailed` fires? The compensation event might be missed. You need durable event delivery and retry logic in every compensation handler.

Orchestration on crash between Step 1 and Step 2: the orchestrator persists its state to a database after each step completes. State: `{ saga_id, current_step: "ROOM_RESERVED", room_reservation_id: "ABC123", payment_status: "PENDING" }`. On restart, the orchestrator reads its persisted state and continues from `current_step`. It sends the "charge credit card" command to Payment Service. Payment Service must be idempotent — if it already processed this saga_id, it returns the same result without double-charging.

Compensation for notifications: you cannot unsend an email. The compensation action is to send a different email — "Your booking has been cancelled." Design the Notification Service to accept both "booking confirmed" and "booking cancelled" commands, not a raw "unsend" command.

Loyalty points compensation: simple — publish a `DeductLoyaltyPoints` command that reverses the credit. Loyalty Service handles this idempotently via the saga_id.

---

### Exercise 6: Kafka Capacity Planning (20 minutes)

**Scenario**: design the Kafka infrastructure for a streaming analytics platform with these requirements: 500 data sources sending events at an average of 1 MB/second per source (500 MB/second total ingestion), 14-day event retention, 10 consumer groups each reading all data, replication factor 3, and available hardware of 32-core servers with 4 TB SSD each.

**Calculate**:

1. Total raw storage needed before and after compression.

2. Number of brokers needed based on storage.

3. Number of partitions needed (target: each partition handles 10 MB/second maximum).

4. Consumer instances needed if each instance processes 10 MB/second.

5. Network bandwidth required per broker.

**L6 hint — work through the math**:

Raw storage: 500 MB/sec × 14 days × 86,400 sec/day × 3 replicas = 500 × 14 × 86,400 × 3 = 1,814,400,000 MB = 1,814 PB. That cannot be right — check your units. 500 MB/sec × 86,400 = 43,200,000 MB/day = 43.2 TB/day. Times 14 days = 604.8 TB. Times 3 replicas = 1,814 TB = 1.81 PB. With 4× compression (JSON compresses well): 1.81 PB / 4 = 452 TB. With 4 TB SSD per broker: 452 TB / 4 TB = 113 brokers. That is still large — consider 32 TB NVMe per broker: 452 TB / 32 TB = 15 brokers for storage.

Throughput check: 500 MB/sec ingress + 500 MB/sec × 10 consumer groups = 5,500 MB/sec total I/O. Per broker with 15 brokers: 5,500 / 15 = 367 MB/sec per broker. A modern NVMe broker handles 500–1,000 MB/sec. 15 brokers is sufficient for throughput.

Partitions: 500 MB/sec / 10 MB/sec per partition = 50 partitions minimum. Use 60–100 for headroom.

Consumer instances: 10 consumer groups × (500 MB/sec / 10 MB/sec per instance) = 10 × 50 = 500 consumer instances total.

Network bandwidth per broker: (500 MB/sec ingress / 15 brokers) + (500 MB/sec × 10 groups / 15 brokers) + replication traffic (~2× ingress) = 33 + 333 + 67 = ~433 MB/sec ≈ 3.5 Gbps per broker. Use 25 GbE NICs with room for spikes.

The storage constraint dominates this design, not throughput. Key L6 insight: always check whether storage or throughput is the binding constraint — they lead to very different hardware choices.

---

## Quick Reference Card

### When to Use Kafka: Decision Checklist

Before adding Kafka to a design, confirm at least three of these are true:

| Condition | Details |
|-----------|---------|
| Multiple consumers need the same data | 3 or more independent services need to react to the same events |
| Processing can be asynchronous | The producer does not need an immediate response from downstream processors |
| Speed mismatch between producer and consumer | Producer bursts at 10× normal rate; consumer processes at steady rate |
| Burst absorption needed | Traffic spikes should be buffered, not dropped |
| Event history or replay is needed | Consumers may need to re-process past events |
| Audit trail required | Every state change must be logged durably |

If none of these apply, use a REST API or a simpler async queue (SQS, RabbitMQ). Kafka is not always the answer.

---

### Key Kafka Numbers

| Metric | Typical Value |
|--------|--------------|
| Broker throughput (NVMe) | 500 MB/sec–1 GB/sec per broker |
| Broker throughput (HDD, sequential) | 100–200 MB/sec per broker |
| Partition capacity | 10–50 MB/sec per partition |
| Consumer rebalance (eager protocol) | 10–60 seconds, all partitions stop |
| Consumer rebalance (cooperative/incremental) | 2–10 seconds, only reassigned partitions pause |
| Partition leader failover | 15–30 seconds |
| MirrorMaker 2 cross-region lag target | Less than 5 minutes |
| Typical compression ratio (JSON with gzip) | 3–5× |
| Default maximum message size | 1 MB (increase with `message.max.bytes`) |
| Minimum partitions for 1 GB/sec throughput | ~100 partitions |
| Retention default | 7 days (configurable per topic) |

---

### Delivery Semantics Cheat Sheet

| Guarantee | Kafka Config | Consumer Behavior | Use Case |
|-----------|-------------|-------------------|----------|
| At-most-once | `acks=0`, `enable.auto.commit=true` before processing | Commit offset before processing message | High-volume telemetry, logs where loss is acceptable |
| At-least-once | `acks=all`, `enable.auto.commit=false` | Commit offset only after successful processing | Most production systems: order events, user actions |
| Exactly-once (Kafka-to-Kafka) | `enable.idempotence=true`, `transactional.id` set | Use Kafka Streams or transactional producer-consumer | Event stream transformations, aggregations |
| Exactly-once (Kafka-to-DB) | `acks=all`, manual commit | Idempotency key in DB (`ON CONFLICT DO NOTHING`), commit after DB write succeeds | Payments, inventory, billing |

Note: Kafka's built-in exactly-once (`transactional.id`) only guarantees exactly-once within the Kafka ecosystem. For exactly-once across external systems (databases, APIs), you must implement idempotency at the application level.

---

### DLQ Runbook

Use this procedure every time a DLQ alert fires:

1. **Acknowledge** the alert and confirm DLQ lag is growing (not a stale alert).

2. **Inspect** the dead messages: `kafka-console-consumer.sh --topic <topic>-dlq --from-beginning --max-messages 5`. Look at the payload and the error metadata header.

3. **Classify the root cause**:
   - Bad data (malformed message, missing required field): fix at the producer or add a schema validation step upstream.
   - Consumer bug (null pointer, parsing error): deploy a fix, then replay the DLQ.
   - Downstream dependency down (database unavailable, external API timeout): restore the dependency first, then replay.
   - Transient infrastructure issue (broker restart, network blip): replay directly — messages should process now.

4. **Fix the root cause first.** Do not replay the DLQ until the root cause is resolved, or the messages will fail again and re-enqueue.

5. **Replay**: reset the DLQ consumer group offset to earliest and let it reprocess. Monitor lag returning to 0.

6. **Post-mortem**: document what caused the DLQ to fill, how long messages were stuck, and what change prevents recurrence.

---

### Saga Pattern Comparison

| Dimension | Choreography | Orchestration |
|-----------|-------------|---------------|
| State visibility | Implicit — must correlate events across topics | Explicit — saga state in a single database table |
| Coupling | Services coupled only via event contracts | Services coupled to the orchestrator's command interface |
| Debugging difficulty | High — requires distributed tracing to follow a saga | Low — one database row shows current step |
| Single point of failure | None — each service acts independently | Orchestrator is a SPOF (mitigate with HA deployment) |
| Best for | Simple 2–3 step flows with clear event semantics | Complex flows with many steps, compensation logic, or regulatory requirements |
| Compensation | Each service must know how to compensate based on incoming events | Orchestrator explicitly sends compensation commands |

---

### Schema Evolution Compatibility Rules

| Change Type | Backward Compatible | Forward Compatible | Safe in Production |
|-------------|--------------------|--------------------|-------------------|
| Add optional field with default | Yes | Yes | Yes — always safe |
| Add required field (no default) | No | Yes | No — old consumers break |
| Remove field | Yes | No | Depends — safe if all consumers are updated first |
| Rename field | No | No | Never — treat as add + remove |
| Change field type (e.g., int to long) | Depends | Depends | Only if Avro type promotion rules allow it |
| Change field type (e.g., int to string) | No | No | Never — full migration required |

The safe path for any schema change: (1) add the new field as optional with a default value, (2) deploy all consumers that understand the new field, (3) deploy producers that start populating the new field, (4) after all old messages have expired, you may deprecate (but not immediately remove) the old field.

---

### Common Interview Mistakes to Avoid

| Mistake | Why It Costs Points | Better Answer |
|---------|--------------------|--------------------|
| "Just use exactly-once semantics" | Kafka transactions only cover Kafka-to-Kafka; external systems need application-level idempotency | Explain the idempotency key pattern in the consuming database |
| "Add more partitions to fix lag" | Partitions cannot be easily reduced; more partitions increase rebalance time and coordinator load | First identify whether the bottleneck is partitions or consumer processing speed |
| "Kafka guarantees message ordering" | Ordering is only within a partition, not across partitions | Specify the partition key strategy that aligns with your ordering requirement |
| "Use a DLQ for everything" | DLQs without runbooks become black holes; messages rot unnoticed | Design DLQ monitoring, retry schedules, and escalation procedures |
| "Kafka solves the two-generals problem" | Nothing does — acknowledge this, then explain your consistency model | Describe the exactly-once guarantee boundary and what happens at failure boundaries |
| Ignoring consumer rebalance in SLA design | A 30-second rebalance during a 100ms SLA discussion is a fatal contradiction | Choose cooperative rebalancing and size consumer groups to avoid unnecessary rebalances |

---

This concludes Chapter 33: Event-Driven Architectures — Kafka and Streams.

The chapter has covered the full arc from Kafka fundamentals (Part A), delivery semantics and exactly-once (Part B), consumer group mechanics and rebalancing (Part C), stream processing with Kafka Streams and Flink (Part D), operational concerns including monitoring and GDPR (Part E), and this final section of design problems and exercises (Part F).

The core judgment that L6 interviews test is not whether you know Kafka's configuration parameters — it is whether you can reason about the failure modes, the tradeoff space, and the points at which Kafka's guarantees end and your application's responsibility begins. Every question in this section is designed to put you at exactly those boundaries.
# Supplemental Brainstorming: Chapters 33 and 34

Advanced questions for self-testing and interview prep. These assume you have already worked through
all twenty questions in each chapter. The focus here is on patterns that appear frequently in L6
system design interviews but were not covered in depth in the main text.

---

## Supplemental Brainstorming: Chapter 33 — Event-Driven Architecture

*Questions 25-42: Advanced patterns and cross-chapter integration.*

### Section A: Advanced Event-Driven Patterns (Q25-Q33)

---

**Question 25 — Saga Pattern: Order Across Four Services**

Your e-commerce system processes orders using four independent microservices — Order, Payment,
Inventory, and Shipping — each with its own database. A user submits an order. Payment charges
the card successfully. Inventory then attempts to reserve stock but fails because the item just
sold out. Design the saga pattern that handles this rollback. Include the event sequence, the
compensating transactions, and the failure handling for the case where the compensating
transaction itself fails.

A saga is a sequence of local transactions where each step publishes an event that triggers the
next step. A failed step triggers compensating events in reverse. The sequence here is:
Order.created -> Payment.charge_requested -> Payment.charged -> Inventory.reserve_requested ->
Inventory.reserve_failed -> Payment.refund_requested -> Payment.refunded -> Order.cancelled.

The hard part is compensation failure. If the Payment.refund_requested event is emitted but the
payment service crashes before processing it, the customer has been charged and the order is
cancelled. Solutions: (a) store saga state in a durable "saga log" table so a recovery process
can replay the compensating events after the service restarts, (b) use idempotency keys on all
compensating operations so retrying a refund is safe, (c) expose a manual reconciliation endpoint
that the on-call team can invoke if automated compensation exhausts its retry budget.

At L6 you must also discuss the visibility problem: from the customer's view, between the failed
inventory step and the completed refund, the order is in an ambiguous state. Design an
"order-status" read model that reflects the current saga state so the customer sees "Your payment
is being reversed" rather than a stale "Order confirmed" screen.

- Draw the full event sequence including the compensation path.
- Where does saga state live, and who owns it?
- Follow-up: how do you detect a saga that has been stuck in a partial state for more than 10 minutes
  and no event has arrived to advance or roll it back?

---

**Question 26 — Outbox Pattern: Atomic Event Publishing**

Your Order service writes to a PostgreSQL database and publishes a "order.created" event to Kafka.
These are two separate writes. If the database commit succeeds but the Kafka produce call fails
(network timeout, broker unavailable), the order exists in the database but no downstream service
knows about it. Design the outbox pattern. Explain how it solves the dual-write problem and what
infrastructure components are required.

The outbox pattern: instead of writing to Kafka directly, the Order service writes the event as a
row into an "outbox" table inside the same PostgreSQL transaction as the order. One atomic
transaction writes both the order row and the outbox row. A separate "relay" process reads
uncommitted outbox rows and publishes them to Kafka, then marks them as published. If the relay
crashes after publishing but before marking, it retries — Kafka consumers must handle the
resulting duplicate via idempotency.

The relay can be implemented two ways: (a) polling — a background thread queries
"SELECT * FROM outbox WHERE published = false ORDER BY created_at LIMIT 100" on a short interval,
or (b) Debezium / Change Data Capture — Debezium tails the PostgreSQL WAL (write-ahead log) and
emits an event to Kafka the moment the outbox row is committed. CDC is lower latency and
lower database load than polling but requires a running Debezium connector and the WAL configured
with logical replication enabled.

- What is the worst-case latency from order creation to Kafka event publish with (a) polling at
  100ms intervals and (b) CDC? When does each approach break down?
- Follow-up: the outbox table grows without bound if the relay falls behind. Design the cleanup
  strategy that does not lose events.

---

**Question 27 — Event Sourcing vs. CQRS: When They Are Not the Same Thing**

A team says "we are doing event sourcing and CQRS together." An interviewer asks: can you do
CQRS without event sourcing? Can you do event sourcing without CQRS? Give a concrete example of
each. Then describe what problems arise when you combine them and try to add a new query model
three years later when the event log has 2 billion events.

Event sourcing: the source of truth is the append-only event log, not a mutable state table. Current
state is derived by replaying events from the beginning (or from a snapshot). CQRS: reads and writes
use separate models. Write model accepts commands and validates business rules. Read model is
optimized for specific query patterns.

CQRS without event sourcing: the write model stores current state in a relational table. The read
model is a separately maintained materialized view (could be in Elasticsearch, Redis, a denormalized
table). No event log exists — just the two models synchronized via CDC or application-level dual
writes. Many systems do this. It is simpler than event sourcing.

Event sourcing without CQRS: a single service replays the event log to derive current state for
both command processing and query answering. Possible for small data volumes; becomes slow as the
log grows because every query requires state reconstruction.

The 2-billion-event problem: adding a new read model means replaying all 2 billion events from the
beginning. At 100K events/second replay speed, that is 20,000 seconds — about 5.5 hours. During
those 5.5 hours the new read model is stale. Solutions: (a) periodic snapshots that the new
consumer can start from, (b) compact the event log to the latest-per-entity state using Kafka
log compaction (but this destroys the ability to answer point-in-time queries), (c) store events
in an object store like S3 in Parquet format, enabling Spark batch replay in parallel across
many workers.

- Follow-up: what schema evolution strategy lets you add fields to events without breaking the
  replay of 2-billion-event history?

---

**Question 28 — Exactly-Once Semantics: What They Actually Mean**

An engineer says "we enabled exactly-once in Kafka so our pipeline is exactly-once end-to-end."
Identify the precise scope of Kafka's exactly-once guarantee. In a pipeline that reads from
Kafka, calls an external REST API, and writes results to a PostgreSQL table, does enabling Kafka's
transactional producer give you exactly-once end-to-end? Explain each component in the pipeline
and where duplicates can still occur.

Kafka's exactly-once guarantee applies to Kafka-to-Kafka pipelines. Specifically: a producer using
transactions and the transactional API guarantees that a batch of messages is either all committed
to the destination topic or none are, even if the producer crashes mid-batch. A consumer using
isolation.level=read_committed will not see uncommitted messages from an aborted transaction.

What exactly-once does NOT cover: (a) the call to an external REST API — if the consumer crashes
after the API call succeeds but before committing the Kafka offset, the API call runs again on
restart; most REST APIs are not idempotent unless you design them to be (via idempotency keys),
(b) the write to PostgreSQL — if the consumer crashes after the PostgreSQL write but before
committing the offset, the PostgreSQL write happens again unless the write itself is idempotent
(upsert or INSERT ON CONFLICT DO NOTHING using event_id as the key).

The end-to-end exactly-once guarantee requires: idempotent external API calls using a stable
idempotency key derived from the Kafka event, AND idempotent database writes. Kafka's
transactional producer alone provides exactly-once only for the Kafka-to-Kafka segment.

- Walk through a concrete crash scenario at each step of the pipeline and identify which step
  causes a duplicate, which causes a message loss, and which is covered by Kafka transactions.
- Follow-up: your pipeline calls Stripe to charge a user. Stripe returns HTTP 200 but the
  response never reaches your consumer (connection reset). What do you do?

---

**Question 29 — Dead Letter Queue: Design for Production**

Your payment event consumer fails on 0.1% of messages. The failures are a mix of: transient
network errors (payment processor temporarily unavailable), data quality errors (malformed event,
missing required field), and business logic errors (account frozen, insufficient balance). Design
a dead letter queue strategy that handles all three failure types correctly. Include retry
schedules, alerting thresholds, and the human review workflow for events stuck in the DLQ.

A single DLQ is the wrong answer. Different failure types require different handling:

Transient errors: retry with exponential backoff. The message stays in the main consumer loop
for up to 3 attempts (immediate, 1 second, 5 seconds), then if still failing, it moves to a
"retry" topic with a delay (implemented via a separate consumer that reads the retry topic but
only processes messages whose retry_after timestamp has passed). Retry schedule: 30 seconds,
5 minutes, 30 minutes, 2 hours. After 4 retries, move to the DLQ.

Data quality errors: retry will never succeed. Move immediately to the DLQ. Tag the DLQ message
with error_type=SCHEMA_ERROR. Alert the team that owns the producer schema. Do not retry.

Business logic errors (account frozen): not a bug — the system is working correctly. These should
be published to an "order-rejected" topic as a first-class outcome event, not treated as errors
at all. The upstream service subscribes to order-rejected to notify the user. Never put
intentional business rejections into a DLQ.

Alerting: DLQ depth > 0 for SCHEMA_ERROR type triggers a page within 5 minutes. DLQ depth > 100
for any type triggers a page. DLQ depth > 10 for payment events triggers an immediate incident.

Human review workflow: DLQ events are replayed through an admin console that shows: event payload,
error trace, number of retry attempts, and a "replay now" button that re-publishes the event to
the main topic with a force-process flag for operators to investigate.

- Follow-up: your DLQ has accumulated 500,000 messages over a weekend. How do you safely drain
  it on Monday without overwhelming the payment processor?

---

**Question 30 — Event Versioning in a Live System**

Your "payment.processed" event has been at version 1 for two years. Now you need to add a
currency_code field (required), rename user_id to customer_id, and remove the legacy_ref field
that no one uses. Three consumer services exist: consumer A was just deployed and can handle v2,
consumer B is a third-party system that cannot be updated for 60 days, consumer C is an internal
system being decommissioned in 90 days. Design the versioning strategy that allows the producer
to deploy without breaking any consumer.

First, separate the three changes by compatibility impact: adding a new field (currency_code) is
backward-compatible only if it has a default value. Renaming a field (user_id to customer_id) is
a breaking change — it is effectively removing one field and adding another. Removing a field
(legacy_ref) is backward-compatible if consumers ignore unknown fields.

Strategy: produce two versions simultaneously during the transition period. The producer writes
to both "payment.processed.v1" and "payment.processed.v2" topics (or embeds a version header and
writes to one topic, with consumers filtering on the version header). Consumer A reads v2. Consumers
B and C continue reading v1. The v1 topic is deprecated with a sunset date of 90 days. At day 60,
consumer B must be updated or given an adapter service that translates v1 to v2 internally. At day
90, the v1 topic is closed.

The cleanest production implementation: use Schema Registry with Avro. Register v1 and v2 schemas.
The producer includes the schema ID in each message. Consumer B reads v1 messages via the v1 schema.
Consumer A reads v2 messages. Field renaming is handled by aliasing: in the v2 Avro schema,
customer_id has an alias "user_id" so Avro's schema resolution can read v1 messages into a v2
reader schema by matching the alias.

- What is the minimum retention period for the v1 topic given that consumer C is being decommissioned
  in 90 days but may replay up to 7 days of events?
- Follow-up: a fourth consumer starts consuming after v1 is closed and needs events from 30 days
  ago. What options exist?

---

**Question 31 — Schema Evolution in a Live System Using Schema Registry**

Your Kafka cluster has 50 topics. Each topic uses JSON with no schema registry. You need to
migrate to Avro with Schema Registry to enable schema enforcement and backward-compatible
evolution. Design the migration strategy. What breaks during migration? How do you run JSON
and Avro producers on the same topic during the cutover period?

The core problem: Kafka topics are byte arrays. A JSON-producing service writes plain UTF-8 JSON.
An Avro-producing service writes a 5-byte magic prefix (magic byte + schema ID) followed by the
Avro-encoded binary payload. A consumer that expects JSON will fail to parse an Avro message and
vice versa. You cannot mix formats on the same topic without consumer-side detection logic.

Migration approach: for each topic, create a parallel new topic (e.g., "payments-v2-avro"). Migrate
one service at a time: (1) register the Avro schema in Schema Registry, (2) update the producer to
write to the new topic in Avro, (3) update each consumer to read from the new topic, (4) once all
consumers are migrated, drain and close the old JSON topic. Run both topics in parallel during the
transition — the old topic for consumers not yet migrated, the new topic for consumers already
migrated.

A single-topic migration is possible but fragile: add a version prefix byte to every message
(0x00 = JSON, 0x01 = Avro). Consumers check the prefix and dispatch to the appropriate
deserializer. This avoids creating new topics but permanently increases consumer complexity.

Schema Registry must be highly available before migration begins. If Schema Registry goes down,
Avro producers cannot fetch schema IDs and will fail to produce. Ensure Schema Registry is
deployed in a 3-node cluster with schema caching enabled on the producer side (cache the schema
ID locally so production continues for minutes even if Schema Registry is briefly unreachable).

- Follow-up: you migrate 48 of 50 topics. The two remaining topics use a complex nested JSON
  structure that is not expressible in Avro (contains arbitrary nested maps with non-string keys).
  What do you do?

---

**Question 32 — Fan-Out Patterns and Their Scaling Limits**

A "post.created" event triggers fan-out to 50 million followers. Three implementation approaches
exist: (A) the feed service reads the event and writes a feed entry to each follower's feed
table directly, (B) a fan-out service publishes one "add-to-feed" event per follower to Kafka
(50 million events), (C) followers pull their feed on request and the feed is computed at read
time from the events of accounts they follow. Analyze the throughput, latency, storage, and
failure characteristics of each. When does each break down?

Approach A (in-process fan-out): single consumer does 50M database writes per celebrity post.
At 10K writes/second per consumer instance, one post takes 5,000 seconds to fan out. This does
not work for celebrity accounts. For accounts with 1,000 followers it is fine.

Approach B (Kafka fan-out): 50M events published to Kafka. At 1M events/second producer throughput,
fan-out takes 50 seconds just to produce. Storage: 50M events x 200 bytes = 10 GB per celebrity post.
If 10 celebrities post per minute, that is 100 GB/minute of fan-out events. Downstream consumers
must process 50M events per post — at 100K events/second per consumer group, that is 500 seconds
behind before even starting on the next post. Kafka fan-out is only viable for accounts with
under ~100K followers.

Approach C (pull at read time): zero fan-out cost at write time. At read time, for a user following
1,000 accounts, the feed service queries the last 20 posts from each account (1,000 queries) and
merges them. This is 1,000 database reads per feed refresh. For 10M active users refreshing feeds
every 5 minutes, that is 2M feed loads/minute x 1,000 queries = 2 billion queries/minute. Database
does not survive this.

Production hybrid (Twitter/Meta approach): use approach A for non-celebrity accounts (< 10K
followers), approach C for celebrity accounts (> 1M followers), and a mix for accounts in between.
Define "celebrity" via a flag set by an async job that detects accounts exceeding the threshold.

- Follow-up: a celebrity account with 50M followers switches to private. All 50M pre-computed feed
  entries must be invalidated. Design the invalidation event and the downstream cleanup.

---

**Question 33 — Pull vs. Push Consumer Models**

Kafka uses a pull model: consumers poll the broker for new messages. SQS and RabbitMQ can push
messages to consumers. Compare the two models across: backpressure handling, latency, consumer
crash behavior, and the ability to serve consumers with heterogeneous processing speeds. In what
scenarios is push preferable to pull, and vice versa?

Pull model: the consumer controls the read rate. If the consumer is slow, it simply polls less
frequently or processes fewer messages per batch. The broker is never overwhelmed by slow consumers
because the broker does not push messages — it just stores them. This is why Kafka handles
heterogeneous consumers naturally: a fast consumer reads at 1M events/second, a slow analytics
consumer reads at 10K events/second, both read from the same topic at their own pace without
affecting each other or the broker. Downside: increased latency. The consumer must poll on a
schedule. With fetch.max.wait.ms=500ms, a message published immediately after a poll cycle waits
up to 500ms before the next poll reads it.

Push model: the broker delivers messages immediately when they arrive. Latency is lower — the
message reaches the consumer within milliseconds of being stored. Downside: the broker must
manage backpressure. If the consumer is slow, the broker must either queue messages (using memory),
drop them, or apply flow control. In RabbitMQ, this is handled via prefetch count — the broker
sends at most N unacknowledged messages to a consumer before pausing. If N is set too high, a
slow consumer is overwhelmed. If N is too low, throughput suffers.

Push preferable: when you need the lowest possible latency and all consumers process at roughly
the same rate (e.g., mobile push notifications via APNs/FCM). Pull preferable: when consumers
have heterogeneous processing speeds, when replay is needed, when the number of consumers is
large and variable, or when producer and consumer throughput are mismatched (the key Kafka use
case).

- Follow-up: you want sub-10ms latency from Kafka publish to consumer processing. What Kafka
  consumer configuration changes reduce latency at the cost of throughput?

---

### Section B: Cross-Chapter Integration (Q34-Q42)

---

**Question 34 — Ch33 + Ch28: Saga Pattern Across Microservice Databases**

You are migrating from a monolith with a single PostgreSQL database to microservices where each
service owns its own database. A user creates an order, which triggers payment, inventory, and
shipping services. Design the saga pattern for this flow. What happens if payment succeeds but
inventory fails? How do you ensure the customer is not charged for an item that cannot be
shipped?

The monolith version of this flow was a single database transaction: BEGIN; insert order; charge
payment; decrement inventory; create shipment; COMMIT. Atomicity was free. In microservices, you
cannot span a transaction across four databases. The saga pattern replaces the database transaction
with a sequence of events and compensating actions.

Forward path (choreography style): Order service publishes "order.created". Payment service
consumes it, charges the card, publishes "payment.charged". Inventory service consumes
"payment.charged", tries to reserve stock, and publishes either "inventory.reserved" or
"inventory.failed". If "inventory.reserved": Shipping service creates a shipment, publishes
"shipment.created". If "inventory.failed": Payment service must consume "inventory.failed" and
issue a refund, publishing "payment.refunded". Order service consumes "payment.refunded" and
publishes "order.cancelled".

The customer-is-charged-but-inventory-fails scenario: the compensating transaction is the refund.
The critical design requirement is that the refund compensating transaction is idempotent and
retried until it succeeds. Use an idempotency key (order_id) for the refund call. The payment
service must maintain a state machine: CHARGED -> REFUND_PENDING -> REFUNDED. If the payment
service crashes before processing "inventory.failed", the refund event is replayed by Kafka on
consumer restart — the idempotency check prevents double-refund.

The gap: between "payment.charged" and "payment.refunded", the customer's card shows a charge.
The order-status read model must show "Processing reversal" during this window, not "Order
confirmed."

- What is the maximum acceptable time between "inventory.failed" and "payment.refunded" from the
  customer's perspective, and what monitoring do you put in place to alert if that SLA is violated?
- Follow-up: the payment processor is down. The "payment.refund_requested" event has been retried
  50 times over 2 hours. What is the escalation path?

---

**Question 35 — Ch33 + Ch30: Zero-Downtime Schema Evolution with Avro**

Your Kafka topics use JSON. The schema changes: a new required field "currency_code" (string, no
default) is added. The producer deploys first. Consumers receive messages with the new field they
do not understand. Design the zero-downtime schema evolution strategy using Avro and Schema
Registry. Define the deployment order, the compatibility mode to configure in Schema Registry,
and how you handle the window between producer deploy and consumer deploy.

With JSON and no schema registry, you have no enforcement layer. The producer adds currency_code
and starts publishing. Old consumers deserialize the JSON and ignore the unknown field (if their
JSON library uses lenient parsing) or throw an exception (if strict mode). You have no way to know
which consumers are lenient and which are strict without checking each codebase.

Avro with Schema Registry solves this via compatibility modes. Configure BACKWARD compatibility on
the topic's schema: new schemas must be readable by consumers using the previous schema. With
BACKWARD compatibility, adding a new field is only allowed if it has a default value. A "required"
field with no default is not backward-compatible — Schema Registry will reject the schema
registration attempt.

Correct approach: add currency_code with a default value ("USD" or null, depending on business
rules). Register this schema in Schema Registry. It passes BACKWARD compatibility check. Deploy
the producer. Old consumers read new messages; Avro schema resolution fills currency_code with
the default value for old consumer schemas. Deploy new consumers. New consumers read the field
directly.

If the business requirement truly is that currency_code is required with no default, you need a
two-phase migration: (1) deploy consumers that can handle both the presence and absence of the
field (using FULL compatibility — both backward and forward compatible), (2) deploy the producer
that includes the field, (3) confirm all old consumers are drained, (4) make the field required
in a follow-up schema version.

- What Schema Registry compatibility mode would you use if you also need to allow old consumers to
  read new messages AND new consumers to read old messages simultaneously?
- Follow-up: Schema Registry is unavailable during the producer deployment window. The producer
  caches schema IDs locally. How long does production remain stable, and what happens when the
  cache expires?

---

**Question 36 — Ch33 + Ch35: Kafka for Real-Time and Batch Consumers Simultaneously**

Your streaming pipeline on Kafka feeds both a real-time dashboard (Flink, sub-1-second latency)
and a nightly batch analytics job (Spark, processes all events from the entire day). Design the
Kafka topic structure and retention policy to serve both consumers efficiently. What happens to
Spark's batch job if Kafka retention is set to 4 hours?

The tension: Flink needs data within milliseconds of it arriving. Spark needs all data from the
past 24 hours available at 2 AM when the batch job runs. If retention is 4 hours, the Spark job
starting at 2 AM can only read back to 10 PM — it misses 18 hours of data.

Retention must be set to at least 25 hours (24-hour lookback plus 1 hour of buffer for job
scheduling variability). In practice, use 48 hours to accommodate batch job retries and
incident recovery. Cost implication: at 1 TB/day ingestion with RF=3, 48-hour retention requires
6 TB of storage across the cluster versus 12 TB for the current 2-year retention. The batch job
is the retention driver here.

Topic structure: one primary topic with 48-hour retention serves both Flink and Spark. Flink reads
from the tail (latest offset, always near real-time). Spark reads from the beginning of the current
day's window. Separate consumer groups ensure Flink's committed offsets do not interfere with
Spark's committed offsets.

If the nightly Spark job fails and needs to reprocess three days of data for debugging, 48-hour
retention is insufficient. Solution: configure the topic with 48-hour retention for operational
use, and separately sink all events to S3 (via a Kafka Connect S3 Sink connector) for long-term
archival at low cost. Spark reruns read from S3 for historical data, not from Kafka. Kafka is for
operational freshness; S3 is for historical depth.

- Follow-up: Spark's batch job runs at 2 AM but takes 4 hours, finishing at 6 AM. A second
  Spark job needs to start at 5 AM using the output of the first job. How do you orchestrate
  this dependency without using Kafka?

---

**Question 37 — Ch33 + Ch36: Multi-Region Kafka with EU Data Residency**

You run Kafka across three regions: US-East, EU-West, AP-Southeast. EU regulations require that
EU user events containing PII stay within the EU region. Your analytics pipeline is in the US-East
region and needs to compute global user engagement metrics. An EU user generates an event. Design
the data flow: how does the EU event reach the US analytics pipeline without violating data
residency requirements?

The key insight: PII (name, email, IP address, user behavior linked to identity) must stay in EU.
Aggregate metrics (event count, session duration, feature usage rate) can leave EU because they
are not linked to individual identifiable users once aggregated.

Data flow: the EU Kafka cluster receives the raw event with PII. A Flink job running in EU reads
the raw event, anonymizes it (strips name, email, replaces user_id with a pseudonymous hashed ID
salted per-day so it cannot be reverse-engineered), and publishes the anonymized event to an
"eu-anonymized-events" topic. MirrorMaker 2 replicates "eu-anonymized-events" from EU-West to
US-East. The US analytics pipeline consumes from US-East only and never touches EU PII.

The raw EU topic with PII is never replicated outside EU. MirrorMaker 2 replication rules must
explicitly whitelist only the anonymized topic for cross-region replication. Audit log: each
event that is anonymized and replicated is logged with a correlation ID in an EU-resident audit
store for regulatory inspection.

Edge case: a specific EU event is needed for a fraud investigation. A US-based fraud analyst
needs the PII. This access must go through an EU-hosted data access service with explicit
legal authorization, not through the analytics Kafka topic.

- How do you ensure the MirrorMaker 2 replication rules are enforced and cannot be bypassed by
  a misconfigured producer that writes directly to the US topic?
- Follow-up: AP-Southeast has similar residency requirements for users in Singapore. Design the
  replication topology that serves the US analytics pipeline with anonymized global data while
  respecting two separate residency constraints.

---

**Question 38 — Ch33 + Ch38: Kafka Cost Analysis and Optimization**

Your Kafka cluster handles 500K messages/second at an average size of 2 KB per message.
Infrastructure: 3 broker instances of r5.2xlarge ($0.504/hour each), 1 TB of new data per day
stored with 7-day retention and replication factor 3. Cross-AZ replication traffic charges apply
at $0.01/GB. Identify the top two cost drivers. Design changes to reduce total monthly cost by
at least 40% without degrading the 500K messages/second throughput or reducing retention below
5 days.

First, calculate the full cost.

Broker compute: 3 x $0.504 x 24 x 30 = $1,089/month.

Storage: 1 TB/day x 7 days = 7 TB raw. With RF=3: 21 TB total. At $0.10/GB for EBS gp2:
21,000 GB x $0.10 = $2,100/month. With LZ4 compression at 3:1 ratio: 21 TB compresses to 7 TB,
costing $700/month. Cross-AZ replication: 500K events/sec x 2 KB x 2 replica writes crossing AZ
(assuming 3 AZs, each replica write may cross an AZ boundary) = ~2 GB/sec cross-AZ traffic.
2 GB/sec x 86,400 seconds x 30 days = 5,184 TB/month x $0.01/GB = $51,840/month.

Cross-AZ replication is the dominant cost by a large margin. The top two drivers are: (1) cross-AZ
replication traffic at ~$52K/month, and (2) storage at $2,100/month uncompressed.

Reductions: (a) enable LZ4 compression on producers — reduces both storage and cross-AZ traffic
proportionally. Storage drops from $2,100 to $700 (-$1,400). Cross-AZ traffic drops from $51,840
to $17,280 (-$34,560), assuming 3:1 compression. (b) Co-locate brokers and replicas in the same
AZ where possible by configuring rack-aware replica assignment to minimize cross-AZ traffic (some
cross-AZ traffic is unavoidable for durability, but the volume can be reduced). (c) Reduce
retention from 7 to 5 days: storage drops from 7 TB/day x 5 = 5 TB raw x 3 replicas with
compression = roughly $500/month. Total savings with compression + reduced retention = over
$36,000/month, exceeding the 40% target.

- Follow-up: a product manager asks you to increase retention to 30 days for compliance. Estimate
  the additional monthly cost, and propose a tiered storage approach using S3 to cap the Kafka
  cluster cost.

---

**Question 39 — Consumer Group Isolation for Critical vs. Non-Critical Consumers**

You have a Kafka topic "user-events" consumed by four consumer groups: (A) real-time
personalization (P99 latency < 100ms), (B) fraud detection (P99 latency < 500ms), (C) analytics
aggregation (batch, can tolerate 1-hour lag), (D) data lake sink (batch, can tolerate 4-hour lag).
A bug in consumer C causes it to crash and rebalance every 30 seconds. Explain the blast radius
of consumer C's rebalance on consumer groups A, B, and D.

Kafka consumer group rebalances are isolated per consumer group. Consumer group C rebalancing does
not trigger a rebalance in consumer groups A, B, or D. Each consumer group independently manages
its partition assignments. Consumer C's repeated crashes affect only its own group membership and
its committed offsets. Groups A, B, and D continue consuming normally.

However, there are indirect effects: if consumer C is producing significant load on the broker
during its crash loop (repeated JoinGroup requests, SyncGroup requests, offset commit attempts),
this increases the load on the Kafka broker's group coordinator. Under extreme conditions (hundreds
of crash-looping consumers), the group coordinator can become a bottleneck that increases latency
for all groups using that coordinator. In practice, a single crash-looping consumer group of
modest size does not noticeably impact other groups.

The real blast radius of consumer C's bug: consumer C's own lag grows unboundedly because it
crashes before processing messages. After enough time, consumer C's lag reaches the point where
it needs to read messages that have fallen outside Kafka's retention window. At that point,
consumer C receives an OffsetOutOfRange error and must reset its offset — either to the earliest
available offset (losing events that have expired) or to the latest offset (skipping all the
accumulated lag). This is the silent data loss risk: not in groups A, B, D, but in group C itself.

- How do you detect that consumer C has crossed the retention boundary and is about to lose data?
  What automated action should trigger?
- Follow-up: design a monitoring dashboard that shows, for each consumer group, the estimated time
  remaining before the consumer lag exceeds the topic's retention window.

---

**Question 40 — Event-Driven Idempotency in Payment Systems**

A payment processing consumer reads "charge.requested" events and calls an external payment
processor. The consumer crashes after the charge succeeds but before it commits the Kafka offset.
On restart, the consumer re-reads the same event and calls the payment processor again. The
customer is charged twice. Design a complete idempotency solution that prevents this without
using Kafka's exactly-once transactions (the payment processor is external and not transactional).

The solution requires idempotency at both the application layer and the external API layer.

Application layer: before calling the payment processor, insert a record into an idempotency table:
"INSERT INTO payment_attempts (event_id, user_id, amount, status) VALUES (?, ?, ?, 'PENDING')
ON CONFLICT (event_id) DO NOTHING." If this insert returns 0 rows affected, the event has already
been processed (successfully or in-progress). Read the existing row's status. If "COMPLETED," skip
and commit the Kafka offset. If "PENDING," a previous attempt started but the consumer crashed
before updating the status. Proceed with the charge, using the same idempotency key.

External API layer: pass event_id as the idempotency key to the payment processor's API. Stripe,
Braintree, and most modern payment processors support this. If the processor has already processed
a charge for this idempotency key, it returns the original response without charging again.

The gap: the payment processor charges the card (idempotency key was new, so the charge runs),
the processor returns HTTP 200, but the network connection resets before the consumer receives the
response. The consumer treats the call as failed (exception thrown) and retries. On retry, the
same idempotency key is sent to the processor. The processor returns the original successful
response. The consumer now knows the charge succeeded. This is the correct behavior — the
idempotency key on the external API is what makes the retry safe.

- What happens if event_id is not stable across consumer restarts (e.g., it is generated by the
  consumer, not embedded in the Kafka event)? Why must idempotency keys be derived from the
  event, not generated by the consumer?
- Follow-up: the idempotency table grows without bound. Design the cleanup strategy, and explain
  how long records must be retained relative to Kafka topic retention.

---

**Question 41 — Ordering Guarantees Across Multiple Topics**

A financial system publishes three event types to three separate topics: "account.created"
(topic A), "transaction.processed" (topic B), "account.closed" (topic C). A downstream audit
service must process these events in strict causal order per account: account.created must be
processed before any transaction.processed for that account, and account.closed must be processed
last. With separate topics, how do you enforce causal ordering? Design the architecture without
merging all events into one topic.

Kafka's ordering guarantee is: within a single partition of a single topic. Across topics, there
is no ordering guarantee. A consumer reading topic B may see transaction.processed events for
account 123 before the account.created event for that same account has been processed from topic A.

Solutions:

Option 1 — Event timestamps with retry: the audit service reads from all three topics. When it
encounters a transaction.processed for account 123 and has not yet seen account.created for
account 123, it parks the transaction event in a local buffer and retries processing it after a
short delay. Risk: if account.created is never received (producer failure), the buffered
transaction event waits forever.

Option 2 — Sequence numbers embedded in events: every event for account 123 includes a monotonic
sequence number assigned by the account service. account.created has sequence=1. The audit service
tracks the last processed sequence per account and buffers out-of-order events. This is reliable
but requires the account service to be the single source of sequence numbers, which re-centralizes
ordering control.

Option 3 — Single "account-lifecycle" topic: merge all three event types into one topic, keyed
by account_id. All events for account 123 land in one partition in arrival order. Ordering is
guaranteed by Kafka. The cost is a more complex schema (union type or envelope pattern) and the
inability to subscribe to only transaction events without also receiving account lifecycle events.
This is the correct L6 answer: partition-level ordering is the only reliable ordering Kafka
provides. Design event types that need ordering to share a partition.

- Follow-up: the three topics have different replication factors and different retention periods.
  When you merge them, what replication factor and retention period do you use?

---

**Question 42 — Event-Driven Architecture for a Global Leaderboard**

A mobile gaming platform runs a global leaderboard updated in real-time. Players from 180 countries
submit score events. The leaderboard must show the top 100 players globally, updated within 5
seconds of a new top score. 10 million active players submit scores at peak (roughly 50,000
scores/second). Design the event-driven architecture from score submission to leaderboard update
to mobile client display.

Score events flow from mobile clients through an API gateway to a Kafka topic "score.submitted"
partitioned by player_id. Each partition is processed by a Flink consumer group that maintains
a local sorted set of scores seen on that partition. A global aggregation stage merges the
per-partition top-100 lists into a global top-100 using a Flink global window with a 1-second
tumbling window.

The global aggregation is the bottleneck: all partitions must report to a single global aggregator,
which becomes a single-threaded computation. For 50,000 events/second this is manageable if the
aggregation is O(log N) per event (sorted structure). At 5-second update SLA: Flink emits a new
global top-100 every 2 seconds (with 3 seconds of buffer for downstream propagation).

The global leaderboard result (a 100-element JSON array) is published to a "leaderboard.updated"
topic. A WebSocket service consumes this topic and fans out the new leaderboard to all connected
mobile clients using a pub-sub broadcast. At 10M active players with 10% viewing the leaderboard
at any moment, that is 1M WebSocket connections receiving a 100-element update every 2 seconds.
This requires a horizontally scaled WebSocket tier (e.g., 100 servers at 10K connections each)
with a shared pub-sub layer (Redis Pub/Sub or the Kafka topic itself as the broadcast channel).

- What happens to the leaderboard display when the Flink aggregation job fails and restarts?
  Design the recovery behavior so clients see a degraded-but-not-broken experience.
- Follow-up: players in China cannot use Kafka topics hosted in the US due to latency and
  regulatory requirements. Design a regional leaderboard architecture that merges into the global
  leaderboard every 10 seconds.

---
---


---

### Cross-chapter: Kafka consumer idempotency with outbox pattern (from Ch23)

**Question 40 -- Kafka consumer idempotency with outbox pattern (Ch23 + Ch33)**

Your Kafka consumer processes "order.placed" events and does two things:
(1) inserts into the orders table, (2) publishes a "send_confirmation_email" task to Redis.
At-least-once delivery means the consumer may process the same message multiple times.

- The naive implementation fails: consumer reads message M (order_id=XYZ),
  inserts the order row, publishes the email task to Redis, then commits the offset.
  The consumer crashes between "publish email task" and "commit offset."
  On restart, it re-reads M, inserts again (blocked by unique constraint -- fine),
  and publishes a SECOND email task. The customer receives two emails.
  Which action failed to be idempotent, and why?
- Outbox pattern: instead of writing to Redis directly, the consumer writes an outbox row
  to the same PostgreSQL transaction as the order insert.
  Outbox row: (event_id, task_type="send_email", payload, processed=false).
  Walk through why this is idempotent on the second replay of message M.
- A separate outbox processor queries outbox rows with processed=false
  and publishes them to Redis. What is the deduplication key for the email task in Redis?
  If Redis does not support deduplication natively, how do you enforce at-most-once delivery
  at the outbox processor layer?
- Follow-up: Kafka Transactions (enable.idempotence=true, transactional.id) let a consumer
  atomically commit a Kafka offset AND produce to another Kafka topic.
  How does this differ from the outbox pattern?
  For writes to PostgreSQL (orders table), can Kafka Transactions help,
  or do you still need the outbox pattern?
  Explain the exact boundary of Kafka Transactions' guarantee.

---

---

### Cross-chapter from Ch20: Mapping Kafka Consistency to the Spectrum

**Question 42 — Ch20 + Ch33: Mapping Kafka's Consistency Model to the Spectrum**

Kafka provides producer-side durability via the acks configuration (acks=0, acks=1, acks=all) and consumer-side reads via offset-based consumption. Consumers can be ahead of or behind the partition head by any amount.

- Map each Kafka producer acks setting to a consistency model from Chapter 20's spectrum. acks=0 is fire-and-forget — what does the producer know about whether the write succeeded? acks=1 means the partition leader acknowledged — what does this provide and what does it not provide? acks=all means all in-sync replicas acknowledged — map this to the spectrum. Are these mappings clean, or do they cross multiple models?
- A Kafka consumer reads events from a partition. It is always reading from committed offsets — it cannot read uncommitted messages. But it can be arbitrarily far behind the current head of the partition. Is this "eventual consistency" in the same sense that a database replica's async replication is eventual consistency? State two specific differences and one meaningful similarity.
- A downstream service consumes from a Kafka topic, processes each event, and writes the result to a database. The service uses an exactly-once semantics (EOS) producer to write to the output topic. If the service restarts and re-reads from its last committed offset, it may re-process events whose results are already in the database. What consistency guarantee does the service need from its output database to prevent duplicate results? Is this a read-your-writes problem, a causal problem, or an idempotency problem? Which of these is the right framing, and what is the implementation?
- Follow-up: You want read-your-writes in Kafka. A producer writes a message to topic T and then wants to verify the message is available for consumers. Design this verification. What is the minimum overhead — in latency and in Kafka operations — of this verification? At what producer throughput does verifying every write become a bottleneck? What is the industry practice for handling this at high throughput?

> *Discussion notes:*
> - *acks=0: not on the consistency spectrum at all. The producer does not wait for any acknowledgment. Equivalent to "hope the write arrived."*
> - *acks=1: maps to read-your-writes for consumers reading from the same partition leader. But if the leader crashes before replicating, the write is lost. Durability guarantee is weak — not equivalent to a database write-to-disk acknowledgment.*
> - *acks=all: maps to sequential consistency for durability per partition. All in-sync replicas (ISR) have the message before the producer is told success. Any consumer reading from any ISR member will see it. But Kafka ordering is per-partition only — not global across partitions — so this is not linearizable.*
> - *Consumer lag vs. database replica lag key difference: in a database, the replica is expected to converge to the primary's state and serve reads in place of the primary. In Kafka, consumer offset is a client-side position — the partition head is always authoritative. Kafka "eventual consistency" is driven by consumer processing throughput, not server-side replication.*
> - *Read-your-writes in Kafka: producer sends a message and receives the offset in the response. Producer then asks a consumer to confirm it can see offset N. At low throughput: add 1-3ms. At high throughput (1M messages/second), this verification becomes a bottleneck — industry practice is to verify a sample (1 in 1000 messages) rather than every write.*

---


---

### Cross-chapter from Ch26: Kafka's CAP position

**Question 36 -- Ch26 + Ch33: Kafka's CAP position**

Kafka's CAP position is nuanced and commonly misunderstood. The producer side (with acks=all) is CP: it blocks until all in-sync replicas have acknowledged. But the consumer side is AP: consumers read from their current offset, which may be behind the latest committed offset. Kafka as a whole is a hybrid, with different CAP positions for different operations.

- With acks=all and min.insync.replicas=2 on a cluster with 3 replicas: if one replica fails, producers can still write (2 in-sync replicas remain). If two replicas fail, producers block (CP behavior -- availability is sacrificed for consistency). Trace this through.
- With min.insync.replicas=1 vs min.insync.replicas=2: how does the CAP position change for producers? Which is more available? Which is more consistent?
- Follow-up: A Kafka consumer reads a message and processes it. The Kafka broker crashes before the consumer commits its offset. On restart, the consumer re-reads the message (at-least-once delivery). Is this a CAP consistency violation? Is it an ACID consistency violation? Explain the difference, and how you design idempotent consumers to handle it.


### Cross-chapter from Ch27: Kafka transactions as 2PC

**Question 39 -- Ch27 + Ch33: Kafka's transaction mechanism as 2PC**

Kafka's exactly-once semantics (introduced in Kafka 0.11) implement a 2PC-like protocol internally. The producer writes to a transaction log (the transaction coordinator topic) and then commits. If the producer crashes after writing to the log but before committing, Kafka's transaction coordinator can recover the transaction state and complete or abort it. This is 2PC with Kafka acting as both the transaction coordinator and the participant.

- Walk through Kafka's exactly-once protocol: (a) producer begins transaction (registers with transaction coordinator), (b) producer writes messages to topic partitions, (c) producer sends commit to transaction coordinator, (d) coordinator writes commit marker to all partitions, (e) consumers only read committed messages. Which step is equivalent to 2PC Phase 1 (prepare)? Which is Phase 2 (commit)?
- What is the equivalent of the "coordinator" in Kafka's transaction protocol? (The transaction coordinator partition, which is itself Raft-replicated within the Kafka cluster.) If the transaction coordinator crashes, what happens to in-flight transactions?
- Follow-up: Kafka's exactly-once semantics require that the consumer's processing (business logic) AND the offset commit happen atomically. This is only achievable if the consumer writes its output back to Kafka (consume-transform-produce). If the consumer writes to an external database (e.g., PostgreSQL), you need external transaction coordination (2PC between Kafka and PostgreSQL). Describe this scenario and why it is usually avoided.

---

## Exercises

**Exercise 1 — Event vs. command vs. query design.** For each interaction in an e-commerce system, classify as event, command, or query — and choose the right delivery mechanism: (a) user places order, (b) check inventory level, (c) order was shipped, (d) trigger fraud check, (e) daily sales report generation. Justify each choice and the delivery guarantee required.

**Exercise 2 — Partition key design.** You're building a Kafka-backed order processing system. Messages must be processed in order per order ID. Design the partition key strategy. What happens if a popular seller generates 80% of all order events (hot partition)? How do you fix the hot partition without breaking ordering?

**Exercise 3 — Consumer group lag analysis.** Your Kafka consumer group is 30 seconds behind at 50K messages/second. Total lag: 1.5M messages. You have 8 consumer instances and 16 partitions. Calculate: messages per partition per second, lag per partition, time to catch up if you add 8 more consumers. What's the bottleneck?

**Exercise 4 — Exactly-once semantics design.** You're implementing a payment processing system using Kafka. Design the exactly-once flow: producer idempotency, consumer transaction, idempotency key in the downstream database. What's the failure mode if the consumer crashes after processing but before committing the offset?

**Exercise 5 — Event schema evolution.** You have a Kafka topic with 30 consumers. The event schema needs a new required field. Design the migration: how do you add the field without breaking existing consumers, what schema registry changes are needed, and how do you handle old events that don't have the field?

**Exercise 6 — Kafka vs. SQS selection.** You need to choose between Kafka and SQS for three scenarios: (a) audit log that must be replayed, (b) task queue for email sending, (c) real-time analytics pipeline with multiple downstream consumers. Justify each choice with the specific capability that drives it.

---

## Homework

**Assignment 1 — Consumer lag monitoring.** Set up consumer lag monitoring for a Kafka topic your team uses. Create an alert: if lag exceeds 60 seconds, page on-call. Write the runbook: what does lag mean, how do you diagnose the cause, what are the first three things to check?

**Assignment 2 — Design review: event-driven system.** Find any event-driven system your team operates. Write a one-page review: event schema design quality (does each event tell a complete story?), consumer group design, DLQ strategy, and monitoring. Identify one improvement.

**Assignment 3 — Interview practice: event-driven design.** Practice "design a real-time notification system using Kafka" in 30 minutes. Cover: topic design, partition key strategy, consumer groups, message schema, DLQ, and what happens when a consumer is slow.

**Assignment 4 — Read the LinkedIn engineering blog post on Kafka's origin ("Building a Distributed, Partitioned, and Replicated Log Service," Kreps et al.).** Write a one-paragraph summary: what problem was Kafka designed to solve that existing message queues couldn't, and what design choices followed from that?

