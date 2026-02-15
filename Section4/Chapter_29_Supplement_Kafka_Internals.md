# Chapter 29 Supplement: Kafka Internals — Topics, Partitions, Consumer Groups, Retention, and Exactly-Once

---

# Introduction

Chapter 23 provides the Staff-level framework for event-driven architecture—when to use events, delivery semantics, anti-patterns. But when the interview goes deeper into Kafka specifically, you need to understand *how* Kafka actually works. Video topics 281–287 assume familiarity with topics, partitions, consumer groups, retention policies, exactly-once semantics, and when Kafka is the wrong tool.

This supplement fills that gap. These are not academic topics. At Staff level, you're asked to explain *why* partition count matters for parallelism, *why* consumer lag explodes during rebalancing, *why* log compaction is essential for changelog topics, and *when* to reach for SQS instead of Kafka. This supplement gives you the internals needed to answer those questions with depth and precision.

**The Staff Engineer's Kafka Internals Principle**: You don't need to run a Kafka cluster. You do need to understand why partitions enable parallelism, how consumer groups divide work, what retention and compaction mean for disk usage, and where exactly-once semantics break at system boundaries. The same applies to "when Kafka is overkill" and "Pub/Sub vs Kafka"—understand the trade-offs, the operational implications, and the decision framework.

**How to use this supplement**: Read it alongside Chapter 23. When the main chapter mentions consumer groups, partitions, or exactly-once, this supplement provides the "how" and "why." For interview prep, focus on the L5 vs L6 tables, the operational monitoring section, the production incident examples, and the Appendix Q&A. For deep dives, work through the ASCII diagrams and the comparison tables. The goal is not to memorize configuration values but to build intuition—so you can reason about Kafka internals when the interviewer asks "why" or "what happens when."

---

## Quick Visual: Kafka Internals at a Glance

```
┌─────────────────────────────────────────────────────────────────────────────┐
│     KAFKA INTERNALS: THE LAYERS THAT MATTER AT STAFF LEVEL                   │
│                                                                             │
│   L5 Framing: "Kafka is a distributed message queue"                        │
│   L6 Framing: "Kafka is an append-only log. Topics split into partitions.   │
│                Partitions enable parallelism. Consumer groups divide work.   │
│                Retention and compaction control storage. Exactly-once has   │
│                boundaries. Kafka is overkill when simpler tools suffice."   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  TOPIC / PARTITION / OFFSET:                                         │   │
│   │  • Topic = named stream; partition = ordered log; offset = position  │   │
│   │  • Partitions = parallelism ceiling; 10 partitions = 10 max consumers│   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  CONSUMER GROUPS:                                                    │   │
│   │  • Each partition → exactly one consumer in group                    │   │
│   │  • Multiple groups read independently; rebalancing pauses processing  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  ORDERING / PARTITION KEY:                                           │   │
│   │  • Within partition: strict order. Across: none. Same key → same part  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  RETENTION / COMPACTION:                                             │   │
│   │  • Time/size retention deletes old; compaction keeps latest per key   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  EXACTLY-ONCE:                                                       │   │
│   │  • Inside Kafka: producer idempotence + transactions. Outside: no.   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  WHEN KAFKA IS OVERKILL:                                             │   │
│   │  • < 100 events/sec, no replay, single consumer → simpler tool        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## L5 vs L6 Kafka Internals Thinking

| Scenario | L5 Approach | L6 Approach |
|----------|-------------|-------------|
| **Consumer lag** | "Add more consumers" | "Consumer count is bounded by partition count. 6 partitions, 8 consumers → 2 idle. Fix: add partitions (reassign), or scale consumers down to 6. Adding consumers beyond partition count does nothing." |
| **Ordering broken** | "Use single partition" | "Single partition kills parallelism. Use partition key by entity ID—order_id, user_id—so events for same entity go to same partition. Ordering within entity, parallelism across entities." |
| **Exactly-once to DB** | "Enable Kafka exactly-once" | "Kafka exactly-once is producer→Kafka→consumer→Kafka. The moment we write to Postgres, we're outside the transaction. Need idempotent writes or outbox pattern." |
| **Topic growing forever** | "Increase retention" | " retention.ms or retention.bytes. For changelogs, use compaction—keep latest per key. Combined policy: compact + delete for compacted topics with time bound." |
| **Choosing Kafka** | "We need events, so Kafka" | "Throughput > 1000/sec? Multiple consumer groups? Need replay? If all no, SQS or Redis may be simpler. Kafka's ops cost is high— brokers, ZooKeeper, lag monitoring." |
| **Pub/Sub vs Kafka** | "Both are message queues" | "Pub/Sub: push, no replay, message gone after delivery. Kafka: pull, replay, message persisted. Use Pub/Sub for simple fanout; Kafka for event sourcing and replay." |

**Key Difference**: L6 engineers connect Kafka's internal mechanics to observable symptoms and operational reality. They know which knob to turn—and when the tool itself is the wrong choice.

---

## L5 vs L6 Thinking: Partition and Consumer Design

| Design Decision | L5 Approach | L6 Approach |
|-----------------|-------------|-------------|
| **Partition count** | "Start with 10" | "10 partitions = max 10 parallel consumers. If we expect 20 consumer instances, we need 20+ partitions. Rule: partitions ≥ max consumers. Add 2× headroom for scale." |
| **Partition key** | "Use user_id for ordering" | "user_id orders events per user. But if one user is 50% of traffic (e.g., system user), we get hot partition. Need to validate key distribution. Consider composite key or salting for high-volume entities." |
| **Consumer count** | "Scale consumers when lag is high" | "Consumer count is capped by partition count. Scaling from 6 to 12 consumers with 6 partitions does nothing—6 will sit idle. First add partitions (or confirm we're under the cap)." |
| **Retention** | "Keep 7 days" | "7 days × 100K msg/sec × 1KB = ~60 TB per topic. Do we have disk? retention.bytes per partition can cap size. Compaction for changelog topics reduces growth." |

---

# Part 1: Kafka Architecture — Topics, Partitions, and Offsets (Topic 281)

## Topic 281 in Context

Topic 281 covers the foundational Kafka model: topics as named streams, partitions as the unit of parallelism and ordering, and offsets as consumer position markers. This is the mental model you need before diving into consumer groups, retention, or exactly-once. At Staff level, you're expected to explain not just *what* these are, but *why* they exist and *how* they interact under load.

## Kafka Is an Append-Only Log, Not a Queue

A common misconception: Kafka is a message queue. It *can* behave like one—consumers read and commit offsets—but its design is fundamentally different.

**Kafka** is a **distributed append-only log**. Messages are appended to partitions and stored on disk. They are not removed when consumed. Consumers track their position via offsets and can read any message from any offset. This enables:

- **Replay**: Reset consumer offset to reprocess from the beginning or from a specific point in time
- **Multiple consumers**: Different consumer groups each read the full log independently
- **Durability**: Messages persist for days or weeks, even after consumption

A **queue** (e.g., SQS, RabbitMQ) typically removes a message when it's delivered. No replay. One consumer per message (or competing consumers).

**Staff Insight**: When someone says "Kafka is overkill for our queue use case," they may be right. If you need simple task distribution with no replay, a queue is simpler. Kafka's power is persistence and replay—use it when that matters.

## Topic: Logical Grouping of Events

A **topic** is a named stream of events. Examples: `user-signups`, `order-events`, `payment-transactions`. It's a logical grouping—a label. Producers publish to a topic; consumers subscribe to a topic.

Topics do not define ordering, parallelism, or retention by themselves. Those are determined by partitions and configuration.

## Partition: The Unit of Parallelism and Ordering

A topic is split into **N partitions**. Each partition is:

- An **ordered, append-only log** on disk
- Stored on one or more brokers (replicated for fault tolerance)
- Independently ordered: messages within a partition have **sequential offsets** (0, 1, 2, 3, ...)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    TOPIC WITH 3 PARTITIONS                                 │
│                                                                             │
│   Topic: "order-events"                                                      │
│                                                                             │
│   Partition 0:  [0][1][2][3][4][5][6]...   ← Ordered by offset              │
│   Partition 1:  [0][1][2][3][4]...         ← Ordered by offset              │
│   Partition 2:  [0][1][2][3][4][5][6][7]...  ← Ordered by offset           │
│                                                                             │
│   Each partition:                                                           │
│   • Immutable sequence of messages                                         │
│   • Offsets 0, 1, 2, ... assigned by broker when message is appended         │
│   • Stored in segment files on disk                                         │
│   • Can live on different brokers (distributed)                             │
│                                                                             │
│   Across partitions: NO ordering guarantee                                 │
│   Partition 0's offset 5 could be "before" or "after" Partition 1's offset 3│
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Why Partitions Matter: Parallelism

**Throughput scales linearly with partition count** (up to a point). Each partition can be read by one consumer in a consumer group. With 10 partitions, you can have up to 10 consumers reading in parallel. With 1 partition, only 1 consumer can read—no parallelism.

| Partitions | Max Parallel Consumers | Throughput |
|------------|------------------------|------------|
| 1 | 1 | Baseline |
| 10 | 10 | ~10× |
| 100 | 100 | ~100× |

**Rule of thumb**: Start with partitions = max expected consumer count × 2. Gives headroom for scaling without over-partitioning.

## Offset: Consumer's Position

The **offset** is an integer that indicates the consumer's position within a partition. Offset 5 means "I've consumed up to and including message 5; next read is 6."

- **Committed offset**: Stored by Kafka (in `__consumer_offsets` topic). On consumer restart, resume from last committed offset.
- **Current position**: The offset the consumer is about to read next.
- **Log end offset (LEO)**: The next offset to be assigned (i.e., the "end" of the log).
- **Lag**: LEO − current position = number of messages behind.

## Choosing Partition Count

| Too Few Partitions | Too Many Partitions |
|-------------------|---------------------|
| Limited parallelism | More file handles per broker |
| Consumer bottleneck | Slower leader elections |
| Hot partitions if key skew | More memory for metadata |
| | More ZooKeeper/KRaft load |

**Practical guidance**:

- **Low volume** (< 1000 msg/sec): 3–6 partitions. Enough for redundancy and some parallelism.
- **Medium volume** (1K–100K msg/sec): 10–50 partitions. Align with consumer count.
- **High volume** (100K+ msg/sec): 50–200+ partitions. Consider throughput per partition; very high partition count has diminishing returns and operational overhead.

**Staff Insight**: Adding partitions later is possible but triggers reassignment and can temporarily skew workload. It's easier to start with a reasonable number than to fix under-partitioning in production.

## Brokers and Replication (Context for Partitions)

Each partition has one **leader** broker and N **replicas** (followers). Producers and consumers talk to the leader. Followers replicate from the leader. If the leader fails, a replica is promoted.

- **Replication factor 3**: Each partition exists on 3 brokers. Tolerates 2 broker failures.
- **In-Sync Replicas (ISR)**: Replicas that are caught up with the leader. `acks=all` waits for all ISR to acknowledge.
- **Under-replicated partition**: A partition with fewer replicas than configured. Risk: reduced fault tolerance. Alert on this.

**Staff Insight**: Partition count affects replication traffic. 1000 partitions across 3 brokers = 333 leaders per broker + 666 replica fetches. Each partition has metadata and connection overhead. Very high partition counts (10K+) can stress ZooKeeper/KRaft and broker memory.

### ZooKeeper vs KRaft: Cluster Metadata

**ZooKeeper** (legacy): Kafka used ZooKeeper for cluster metadata (broker registration, partition assignment, controller election). Separate process; operational overhead. Being deprecated in favor of KRaft.

**KRaft** (Kafka 3.x+): Kafka Raft. Cluster metadata stored in Kafka's own log; no ZooKeeper. Controllers form a Raft quorum. Simpler ops, fewer moving parts. New clusters should use KRaft. For interviews, know that KRaft eliminates the ZooKeeper dependency—Kafka is self-contained.

## ASCII Diagram: Topic, Partitions, Messages, Offsets

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    TOPIC "order-events" — FULL LAYOUT                        │
│                                                                             │
│   BROKER 1                    BROKER 2                    BROKER 3         │
│   ┌─────────────┐             ┌─────────────┐             ┌─────────────┐   │
│   │ Partition 0 │             │ Partition 1 │             │ Partition 2 │   │
│   │ (Leader)    │             │ (Leader)    │             │ (Leader)    │   │
│   │             │             │             │             │             │   │
│   │ [0][1][2]   │             │ [0][1][2][3]│             │ [0][1]      │   │
│   │ [3][4][5]   │             │ [4][5]     │             │ [2][3][4]   │   │
│   │ [6][7]...   │             │ ...        │             │ [5]...      │   │
│   │             │             │             │             │             │   │
│   │ LEO=8       │             │ LEO=6      │             │ LEO=6       │   │
│   └─────────────┘             └─────────────┘             └─────────────┘   │
│                                                                             │
│   Replicas (not shown): P0 replica on B2,B3; P1 on B1,B3; P2 on B1,B2        │
│                                                                             │
│   Producer sends message with key="order-123" → hash("order-123") % 3       │
│   → Routing to partition (0, 1, or 2)                                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 2: Consumer Groups (Topic 282)

## Topic 282 in Context

Consumer groups are how Kafka scales consumption. Without them, you'd have a single consumer per topic—or N consumers fighting over every message. Consumer groups *partition* the work: each partition goes to exactly one consumer, enabling parallel processing. Topic 282 also covers rebalancing (the bane of Kafka operations) and the independence of multiple consumer groups. Staff engineers understand rebalance impact and design for minimal disruption.

## What Is a Consumer Group?

A **consumer group** is a set of consumers that cooperate to consume a topic. Kafka assigns each partition of the topic to **exactly one** consumer in the group. No two consumers in the same group read the same partition.

- **Load distribution**: Partitions are divided among consumers.
- **Fault tolerance**: If a consumer fails, its partitions are reassigned to other consumers.
- **Scalability**: Add consumers (up to partition count) to increase throughput.

## Partition Assignment Rules

| Partitions | Consumers in Group | Assignment |
|------------|-------------------|------------|
| 6 | 3 | Each consumer: 2 partitions |
| 6 | 6 | Each consumer: 1 partition |
| 6 | 8 | 6 consumers get 1 partition each; 2 are **idle** |
| 4 | 6 | 4 consumers get 1 partition each; 2 are **idle** |

**Key rule**: Maximum useful consumers = number of partitions. More consumers than partitions = wasted resources.

## Multiple Consumer Groups: Independence

Different consumer groups consume the **same** topic **independently**. Each group has its own offset per partition. They do not affect each other.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    TWO CONSUMER GROUPS, SAME TOPIC                           │
│                                                                             │
│   Topic "order-events"                                                       │
│   [P0][P1][P2][P3][P4][P5]                                                  │
│        │                                                                     │
│        ├──────────────────────────────┬─────────────────────────────────┐   │
│        │                              │                                 │   │
│        ▼                              ▼                                 ▼   │
│   ┌─────────────┐              ┌─────────────┐                     ┌─────────┐│
│   │ Group:      │              │ Group:      │                     │ Group:  ││
│   │ "analytics" │              │ "email-     │                     │ "fraud" ││
│   │             │              │  sender"    │                     │         ││
│   │ C1: P0,P1   │              │ C1: P0,P2  │                     │ C1: P0 ││
│   │ C2: P2,P3   │              │ C2: P1,P3  │                     │ C2: P1 ││
│   │ C3: P4,P5   │              │ C3: P4,P5  │                     │ ...    ││
│   │             │              │             │                     │         ││
│   │ Offset:     │              │ Offset:    │                     │ Offset: ││
│   │ varies     │              │ varies     │                     │ varies  ││
│   └─────────────┘              └─────────────┘                     └─────────┘│
│                                                                             │
│   Each group:                                                                │
│   • Reads ALL messages (from its own offset)                                │
│   • Processes at its own speed                                              │
│   • Failure in one group does NOT affect others                             │
│   • Use case: analytics (batch), email (real-time), fraud (real-time)       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Use case**: Same event stream drives multiple independent pipelines—analytics, notifications, search indexing, fraud detection. Each has different processing logic and different lag tolerances.

## Rebalancing: The Pause That Hurts

**Rebalancing** is the process of redistributing partitions among consumers when group membership changes. It's unavoidable but can be optimized.

When a consumer **joins** or **leaves** a group, Kafka triggers a **rebalance**. Partitions are reassigned. During rebalance:

- **Processing stops** (or is greatly reduced) for the group
- Consumers give up their partitions, then receive new assignments
- Can take seconds to tens of seconds depending on group size and partition count

**Causes of rebalancing**:

- Consumer joins (scale up)
- Consumer leaves (scale down, crash, restart)
- Consumer fails to send heartbeat (session timeout)
- Partition count changes (topic configuration)

**Cooperative rebalancing** (Kafka 2.4+): Reduces disruption. Partitions are revoked incrementally rather than all at once. Consumers can continue processing partitions they keep while new assignment is computed.

**Operational tip**: Avoid frequent restarts and scaling events. Use **static membership** (`group.instance.id`) when possible—Kafka treats the consumer as the same instance across restarts, reducing unnecessary rebalances.

### Rebalance Protocols: Eager vs Cooperative

| Protocol | Behavior | Disruption |
|----------|----------|------------|
| **Eager** (default, older) | All consumers revoke all partitions. New assignment computed. All consumers get new assignment. | Full processing stop during entire rebalance |
| **Cooperative** (Kafka 2.4+) | Consumers revoke subset of partitions. Reassign. Repeat until balanced. | Incremental; consumers keep processing retained partitions |

With cooperative rebalancing, a consumer that keeps partition P0 can continue processing P0 while P1 is revoked and reassigned elsewhere. Reduces "stop-the-world" duration.

### Offset Storage: __consumer_offsets

Consumer group offsets are stored in the internal topic `__consumer_offsets`. Each partition of this topic holds offsets for a subset of consumer groups. When a consumer commits, it writes to this topic. On restart, the consumer reads its last committed offset from `__consumer_offsets` and resumes.

- **Compact** this topic so it doesn't grow forever (Kafka does this by default)
- High consumer group churn can increase write load on this topic
- Retention of `__consumer_offsets` affects how far back consumers can reset

## Consumer Lag: How Far Behind?

**Consumer lag** = (Latest offset in partition) − (Consumer's current offset). Measured in number of messages or in time (if you know message rate).

| Lag | Interpretation |
|-----|-----------------|
| 0 | Consumer is caught up |
| Increasing | Consumer can't keep up; will never catch up unless producers slow |
| Stable but high | Consumer is keeping up but far behind; consider if SLA allows |
| Spikes during peak | Capacity planning; may need more consumers or partitions |

**Monitoring**: Track lag per partition and per consumer group. Alert when lag exceeds threshold (e.g., 10K messages or 5 minutes behind). High lag can mean slow consumers, insufficient parallelism, or poison messages blocking progress.

## ASCII Diagram: Consumer Group with Rebalance

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CONSUMER GROUP REBALANCE SCENARIO                         │
│                                                                             │
│   BEFORE: 3 consumers, 6 partitions                                          │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐                                  │
│   │Consumer A│  │Consumer B│  │Consumer C│                                  │
│   │  P0, P1  │  │  P2, P3  │  │  P4, P5  │                                  │
│   └──────────┘  └──────────┘  └──────────┘                                  │
│                                                                             │
│   Consumer B crashes (or is scaled down)                                    │
│   → Kafka detects: heartbeat timeout                                        │
│   → Rebalance triggered                                                     │
│                                                                             │
│   DURING REBALANCE (Stop-the-world, older behavior):                        │
│   - All consumers pause                                                     │
│   - Partitions reassigned: A gets P0,P1,P2,P3; C gets P4,P5                 │
│   - Processing resumes                                                       │
│   - A now handles 4 partitions (2× load)                                     │
│                                                                             │
│   AFTER: 2 consumers, 6 partitions                                          │
│   ┌──────────┐              ┌──────────┐                                    │
│   │Consumer A│              │Consumer C│                                    │
│   │ P0,P1,   │              │ P4, P5   │                                    │
│   │ P2,P3    │              │          │                                    │
│   └──────────┘              └──────────┘                                    │
│                                                                             │
│   If Consumer D joins: Another rebalance → A(P0,P1), C(P2,P3), D(P4,P5)    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 3: Ordering and Partitioning Keys (Topic 283)

## Topic 283 in Context

Ordering is one of the most misunderstood aspects of Kafka. "Kafka guarantees ordering" is true only *within a partition*. Across partitions, there is no guarantee. The partition key is the lever: same key → same partition → ordered. Choose the wrong key (or no key), and you get either broken ordering or hot partitions. Topic 283 is where Staff engineers demonstrate they understand the ordering/parallelism trade-off.

## Ordering Guarantees

| Scope | Ordering |
|-------|----------|
| **Within a partition** | Strict. Messages ordered by offset. If A is written before B, every consumer sees A before B. |
| **Across partitions** | None. Message in P0 and message in P1 can be processed in any order. |
| **With same partition key** | Same key → same partition → ordered within that partition. |

## Partition Key: Routing and Ordering

Producers can specify a **key** per message. Kafka routes the message using:

```
partition = hash(key) % num_partitions
```

- **Same key** → same partition → **ordering preserved**
- **No key** (null) → round-robin across partitions → maximum throughput, **no ordering**

**Example**: `key = order_id`. All events for order #123 go to the same partition:
- "created" → "paid" → "shipped" → "delivered"

Order preserved. Events for order #456 go to a different partition. Parallelism across orders; ordering within order.

## Hot Partitions: When One Key Dominates

If one key has disproportionate traffic—e.g., a celebrity user, a default tenant_id, or "unknown"—one partition receives most of the load. That partition becomes a **hot partition**. Throughput is limited by a single partition's capacity.

**Solutions**:

| Strategy | Description |
|----------|-------------|
| **Key salting** | Append random suffix: `key = order_id + "_" + random(0,9)`. Distributes load; breaks ordering for that key. |
| **Composite key** | `key = (tenant_id, sub_key)`. Balance tenant isolation with distribution. |
| **Separate handling** | High-volume keys go to a dedicated topic or pipeline. |
| **More partitions** | Dilutes hot partition effect (e.g., 100 partitions vs 10). |

**Staff Insight**: Hot partitions are a design smell. Choose partition keys that distribute load reasonably. Monitor per-partition throughput; skew indicates a key design problem.

### No Key: Round-Robin

When the producer sends a message with `key=null`, Kafka uses **sticky partitioning** (since Kafka 2.4): messages are sent in batches to the same partition until the batch is full or a time threshold is reached, then the partition is switched. This improves batching efficiency while still distributing across partitions. Older behavior was strict round-robin per message.

## ASCII Diagram: Message Routing by Key

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PARTITION ROUTING BY KEY                                  │
│                                                                             │
│   Producer sends:                                                            │
│   Message 1: key="order-101" → hash % 3 = 1 → Partition 1                    │
│   Message 2: key="order-102" → hash % 3 = 0 → Partition 0                    │
│   Message 3: key="order-101" → hash % 3 = 1 → Partition 1  (same as M1)     │
│   Message 4: key=null        → round-robin  → Partition 2                    │
│                                                                             │
│   Result in partitions:                                                       │
│   P0: [order-102, evt1]                                                      │
│   P1: [order-101, evt1][order-101, evt2]  ← order-101 events ordered         │
│   P2: [null, evt1]                                                          │
│                                                                             │
│   Ordering:                                                                  │
│   • order-101 events: strict order in P1                                     │
│   • order-102 events: strict order in P0                                     │
│   • order-101 vs order-102: no ordering guarantee                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 4: Retention and Compaction (Topic 284)

## Topic 284 in Context

Retention controls how long messages live; compaction controls how changelog topics evolve. Most engineers know "retention = 7 days" but struggle with compaction—when to use it, what tombstones are, why compaction lag matters. Topic 284 is essential for designing stateful stream processing (Kafka Streams, Flink) and CDC pipelines. At Staff level, you choose the right cleanup policy and size disk accordingly.

## How Kafka Stores Data: Segments

Kafka stores partition data in **segment files** on disk. Each segment is a file (e.g., `00000000000000000123.log`). Segments are:

- **Immutable** once rotated (closed). New writes go to the **active segment**.
- **Rotated** when segment size or time threshold is reached
- **Deleted or compacted** based on `cleanup.policy`

## Time-Based Retention

`retention.ms=604800000` (7 days): Segments older than 7 days are deleted. Simple and predictable.

- **Use case**: Event streams where old data has no value (logs, metrics, clickstream)
- **Trade-off**: Disk usage grows until segments expire. Plan disk capacity for retention window × write rate.

## Size-Based Retention

`retention.bytes` per partition: When total size exceeds the limit, oldest segments are deleted.

- **Use case**: Bound disk usage regardless of time
- **Trade-off**: In low-throughput topics, old data may stay longer than desired

## Log Compaction

`cleanup.policy=compact`: For each **key**, Kafka keeps only the **latest** message. Older messages with the same key are deleted during compaction.

- **Use case**: Changelog topics, state stores, CDC (Change Data Capture)
- **Example**: Topic `user-profiles` with key=user_id. Messages: {user_1, "John"}, {user_1, "John Doe"}, {user_2, "Jane"}. After compaction: {user_1, "John Doe"}, {user_2, "Jane"}. Latest state per key.

**Tombstones**: A message with `key=X` and `value=null` means "delete key X." Compaction removes the key entirely. Essential for deletes in compacted topics (e.g., GDPR "right to be forgotten"). Tombstones themselves are retained for a period (`delete.retention.ms`, default 24 hours) so late-arriving consumers can process the delete; after that, the tombstone is removed by compaction.

## When to Use Compaction vs Retention

| Use Case | Policy | Rationale |
|----------|--------|------------|
| **Event stream** (orders, clicks) | `delete` (time/size) | Old events have no value; delete when expired |
| **Changelog** (user profiles, state) | `compact` | Need latest state per key; old versions discarded |
| **CDC from DB** | `compact` | Row changes; keep latest per primary key |
| **Bounded changelog** | `compact,delete` | Latest per key + time limit (e.g., 7 days max) |

## Segment Lifecycle

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SEGMENT LIFECYCLE (Retention + Compaction)                 │
│                                                                             │
│   ACTIVE SEGMENT (current writes):                                          │
│   • Never compacted, never deleted                                          │
│   • Receives new messages                                                   │
│                                                                             │
│   CLOSED SEGMENTS:                                                           │
│   • Eligible for compaction (if cleanup.policy=compact)                     │
│   • Eligible for deletion (if retention exceeded)                           │
│                                                                             │
│   Compaction (async):                                                        │
│   • Log cleaner process runs in background                                  │
│   • Reads segments, keeps latest per key, writes new segment                │
│   • Not instant—old versions may exist for hours                            │
│                                                                             │
│   BEFORE COMPACTION:                                                         │
│   [key=A,v1][key=B,v1][key=A,v2][key=C,v1][key=B,v2]                        │
│                                                                             │
│   AFTER COMPACTION:                                                          │
│   [key=A,v2][key=B,v2][key=C,v1]  (latest per key only)                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Combined Policies: Compact + Delete

`cleanup.policy=compact,delete`: Compaction keeps latest per key; retention deletes even compacted keys older than `retention.ms`. Use when you want both: bounded size and time limit (e.g., compacted changelog with 7-day max age).

## Compaction Lag

Compaction runs **asynchronously**. After a new message with key X arrives, the old message for X may remain until the next compaction pass. "Compaction lag" = time between newest message for a key and when old versions are removed. Can be hours for low-activity keys.

**Operational tip**: Monitor compaction lag. If it grows unbounded, the log cleaner may not keep up—check CPU and I/O on brokers.

### Segment File Layout on Disk

Each partition's data is stored in a directory: `topic-partition-id/`. Inside:

- `00000000000000000123.log` — Message data
- `00000000000000000123.index` — Offset index (offset → byte position)
- `00000000000000000123.timeindex` — Timestamp index (for retention by time)

When retention or compaction runs, entire segment files are deleted or replaced. This is efficient—no in-place updates—but means retention is granular to the segment, not individual messages.

---

# Part 5: Exactly-Once Semantics (Topic 285)

## Topic 285 in Context

Exactly-once is the most over-promised and under-delivered guarantee in distributed systems. Kafka's EOS works *within* Kafka—producer idempotence, transactions, read-process-write. The moment you write to Postgres, Redis, or an HTTP endpoint, you're outside the transaction. Topic 285 tests whether you understand the boundary. Staff engineers design idempotent consumers regardless of EOS settings.

## Three Delivery Guarantees

| Guarantee | Behavior | When to Use |
|-----------|----------|-------------|
| **At-most-once** | May lose; never duplicate | Low-value, high-volume (analytics, logs) |
| **At-least-once** | May duplicate; never lose | Most production; requires idempotent consumers |
| **Exactly-once** | No loss, no duplicates | When possible within Kafka; external systems need idempotence |

## At-Most-Once

Commit offset **before** processing. If processing fails, message is lost (offset already moved). Use when loss is acceptable.

## At-Least-Once

Commit offset **after** processing. If crash happens after process but before commit, message is redelivered—**duplicate**. Use when loss is worse than duplication. **Requires idempotent consumers**.

## Exactly-Once: Kafka's EOS (Exactly-Once Semantics)

Kafka provides exactly-once **within** its ecosystem via:

1. **Producer idempotence** (`enable.idempotence=true`): Producer gets a Producer ID. Each message has a sequence number. Kafka deduplicates within a partition. Retries don't create duplicates.

2. **Transactional producer** (`transactional.id=my-txn-id`): Produce to multiple topics/partitions **atomically**. All or nothing.

3. **Read-process-write** (consuming from input topic, processing, producing to output topic, committing offset): All in **one atomic transaction**. Consumer uses `isolation.level=read_committed` to skip aborted transactions.

## The Boundary Problem

Exactly-once works **inside Kafka**: producer → Kafka → consumer → Kafka. It does **not** extend to external systems.

- Consumer reads from Kafka, writes to Postgres, commits offset. Kafka commit and Postgres write are **two separate operations**. If Postgres succeeds and Kafka commit fails, on restart the consumer will reprocess and write to Postgres again—**duplicate**.
- **Solution**: Idempotent writes to the external system (e.g., upsert by event ID, or check "already processed" before write).

## Performance Impact

Transactional produces are **slower** (~20–30% throughput reduction). Each transaction involves coordinator overhead (begin, commit). Use only when atomicity across multiple partitions/topics is required.

**Practical reality**: Most production systems use **at-least-once + idempotent consumers**. Simpler, better throughput, and effectively correct when consumers are designed for idempotence.

### Implementation Checklist for Kafka EOS

```
Producer:
  enable.idempotence = true          # Deduplication within partition
  transactional.id = "my-txn-id"     # For multi-partition/topic writes
  acks = all

Consumer:
  isolation.level = read_committed   # Skip aborted transactional messages
  enable.auto.commit = false         # Manual commit as part of transaction

Flow:
  producer.initTransactions()
  while (true) {
    records = consumer.poll()
    producer.beginTransaction()
    for (record : records) {
      output = process(record)
      producer.send(outputTopic, output)
    }
    producer.sendOffsetsToTransaction(consumer, offsets)
    producer.commitTransaction()
  }
```

## ASCII Diagram: Exactly-Once Transaction Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    EXACTLY-ONCE TRANSACTION FLOW (Within Kafka)              │
│                                                                             │
│   Consumer (transactional):                                                   │
│                                                                             │
│   1. initTransactions()                                                      │
│   2. consumer.poll() → read from input topic                                │
│   3. beginTransaction()                                                      │
│   4. process(message)                                                       │
│   5. producer.send(output_topic, result)  // multiple sends OK               │
│   6. sendOffsetsToTransaction(consumer, offsets)                             │
│   7. commitTransaction()  // atomic: output + offset commit                  │
│                                                                             │
│   If step 7 fails: abortTransaction() → no output, no offset commit           │
│   Consumer will reprocess on next poll.                                      │
│                                                                             │
│   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐                   │
│   │ Input Topic │────▶│  Consumer   │────▶│ Output Topic │                   │
│   └─────────────┘     │  (process)   │     └─────────────┘                   │
│                       │             │                                        │
│                       │  + commit   │                                        │
│                       │    offset   │                                        │
│                       └──────┬──────┘                                        │
│                              │                                               │
│                    All in ONE Kafka transaction                              │
│                                                                             │
│   EXTERNAL SYSTEM (e.g., Postgres):                                         │
│   - Outside transaction                                                      │
│   - Must use idempotent writes (event_id, upsert)                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 6: When Kafka Is Overkill (Topic 286)

## Topic 286 in Context

The best system design decision is often *not* to use the fanciest tool. Kafka is powerful but has real cost: brokers, ZooKeeper/KRaft, monitoring, expertise. Topic 286 is about knowing when SQS, Redis, or even a synchronous HTTP call is the right choice. Staff engineers push back on "we need Kafka" when the use case doesn't justify it.

## When Kafka Is Overkill

| Condition | Simpler Alternative |
|-----------|---------------------|
| Throughput < 100 events/sec | SQS, Redis, or direct HTTP |
| No replay needed | SQS, RabbitMQ |
| Single consumer | Direct call or queue |
| Team lacks Kafka expertise | Managed queue (SQS) |
| Simple task queue | SQS, database polling |

## Kafka's Hidden Costs

- **3+ brokers** for production HA
- **ZooKeeper or KRaft** for cluster coordination
- **Monitoring**: Consumer lag, ISR (In-Sync Replicas), partition skew, disk usage
- **Schema Registry** (if using Avro/Protobuf)
- **Disk management**: Retention, compaction, segment sizing
- **Version upgrades**: Kafka upgrades can be non-trivial

## Decision Framework

1. **Need replay?** (Reset offset, reprocess from past) → If no, consider SQS.
2. **Multiple consumer groups?** (Same events, different processors) → If no, single consumer or queue may suffice.
3. **Throughput > 1000/sec?** → If no, Kafka's scale may be unnecessary.
4. **Ordering within entity critical?** → Kafka's partition key helps. Simpler queues often don't guarantee ordering.

If all answers are "no," **skip Kafka**. Choose a simpler tool.

### Simpler Alternatives in Detail

| Alternative | Use Case | Pros | Cons |
|-------------|----------|------|------|
| **SQS** | Task queue, decoupling | Managed, pay per message, no brokers | 3K msg/sec (standard), no ordering (FIFO has limits), no replay |
| **Redis Lists** | Simple queue | Fast, in-memory, simple | No persistence by default, no consumer groups |
| **Database polling** | Jobs, low volume | Uses existing DB, transactional | Polling overhead, not real-time, scaling limits |
| **Direct HTTP** | Synchronous flow | Simple, no queue | Coupling, no buffer for spikes |

## Kafka Managed Services: Confluent Cloud, MSK, Event Hubs

**Self-managed vs managed**: Self-managed = you run brokers, ZooKeeper/KRaft, monitor, upgrade. Full control, full ops burden. Managed (Confluent Cloud, AWS MSK, Azure Event Hubs) = provider runs the cluster; you configure topics and connect. Higher cost, lower ops.

**When managed**: Team lacks Kafka expertise, want to move fast, or compliance requires managed services. **When self-managed**: Cost-sensitive at high volume, need custom config (e.g., specific retention, compaction), or air-gapped environment.

**Confluent Cloud**: Full Kafka ecosystem (Schema Registry, ksqlDB, connectors). Good for greenfield. **AWS MSK**: Kafka API compatible; integrates with IAM, VPC. **Event Hubs**: Azure; Kafka API; different underlying model but Kafka-compatible consumer/producer.

## Comparison Table: Kafka vs Alternatives

| Dimension | Kafka | SQS | RabbitMQ | Redis Streams |
|-----------|-------|-----|----------|---------------|
| **Throughput** | 100K+ msg/sec | 3K msg/sec (standard) | 10K-50K | 100K+ |
| **Ordering** | Per partition | Best-effort FIFO (FIFO queues) | Per queue | Per stream |
| **Replay** | Yes (reset offset) | No | No | Yes (consumer groups) |
| **Persistence** | Disk, days/weeks | S3-backed, days | Memory/disk | Memory |
| **Ops complexity** | High | Low (managed) | Medium | Low |
| **Cost at scale** | Brokers + disk | Per request | Self-hosted | Self-hosted |
| **Best for** | Event streaming, replay, multi-consumer | Task queues, simple decoupling | Complex routing, AMQP | Real-time, simple replay |

---

# Part 7: Pub/Sub vs Kafka (Topic 287)

## Topic 287 in Context

Pub/Sub (Google Cloud Pub/Sub, AWS SNS+SQS) and Kafka both move messages between producers and consumers. But they're built for different problems. Pub/Sub: push, fire-and-forget, no replay. Kafka: pull, persist, replay. Topic 287 is about matching the tool to the requirement. Staff engineers recommend Pub/Sub for simple fanout and Kafka for event sourcing and stream processing—and know when to use a hybrid.

## Key Differences

| Aspect | Pub/Sub (GCP, AWS SNS+SQS) | Kafka |
|--------|----------------------------|-------|
| **Delivery** | Push to subscribers | Pull by consumers |
| **Persistence** | Message delivered, then gone (or SQS retention) | Stored on disk, replayable |
| **Replay** | No | Yes |
| **Consumer offset** | No | Yes |
| **Consumer groups** | No (each subscriber gets copy) | Yes (partition assignment) |

## When Pub/Sub

- Simple notification/fanout
- Managed simplicity, low ops
- No replay needed
- Push model acceptable

## When Kafka

- Event sourcing
- Replay needed
- Multiple consumers at different speeds
- Ordering critical
- Stream processing (Kafka Streams, Flink)

## Cost Comparison at Scale

- **Pub/Sub**: Charges per message. At billions/day, cost adds up. GCP Pub/Sub: ~$0.40 per million messages; AWS SNS similar. At 500M messages/day = 15B/month ≈ $6K just for messaging.
- **Kafka**: Self-managed brokers; cost is infra + ops. At 100M–500M+ messages/day, Kafka on dedicated brokers often **cheaper per message** than Pub/Sub. Crossover typically around 100M–500M messages/day depending on message size and retention.
- **Hybrid**: Critical event streams in Kafka; simple notifications via Pub/Sub. Match tool to requirement. Example: order events in Kafka (replay, multi-consumer); "order confirmed" email trigger via Pub/Sub (simple fanout, no replay).

### Push vs Pull: Why It Matters

**Pub/Sub (push)**: Broker pushes to subscriber. Subscriber must handle rate—too fast and it's overwhelmed. Backpressure requires explicit flow control.

**Kafka (pull)**: Consumer pulls at its own rate. Natural backpressure—consumer can't be overwhelmed by producer. Trade-off: consumer must poll; adds latency for low-throughput use cases (poll interval).

**Staff Insight**: For high-throughput event streams, pull is often preferable. Consumer controls its pace. For simple fanout with few subscribers, push is fine.

---

# Part 8: Kafka Consumers — Poll, Commit, and Fetch

## Consumer Fetch Model

Kafka consumers **pull** messages. They don't receive pushed deliveries. The flow:

1. Consumer calls `poll(timeout)`
2. Broker returns a batch of messages (up to `max.poll.records`, default 500)
3. Consumer processes messages
4. Consumer calls `commitSync()` or `commitAsync()` to persist offset
5. Next `poll()` fetches from committed offset

**Critical**: If the consumer takes too long between `poll()` calls, it may exceed `max.poll.interval.ms` (default 5 minutes). Kafka considers the consumer dead and triggers a rebalance. For slow processors, increase `max.poll.interval.ms` or reduce `max.poll.records` so each poll batch is processed within the interval.

## Auto-Commit vs Manual Commit

| Mode | When Offset Committed | Use Case |
|------|----------------------|----------|
| **Auto-commit** (enable.auto.commit=true) | Periodically (auto.commit.interval.ms) | At-most-once or acceptable duplicates |
| **Manual commit** (enable.auto.commit=false) | After processing (commitSync/commitAsync) | At-least-once, exactly-once |

For at-least-once, always commit **after** successful processing. Commit **before** = at-most-once (message loss if processing fails).

## Producer acks: Durability vs Latency

| acks | Behavior | Durability | Latency |
|------|----------|------------|---------|
| **0** | Fire and forget. No wait. | May lose if broker fails before replicate | Lowest |
| **1** | Leader acknowledges. | Lose if leader fails before replicate | Low |
| **all** (-1) | All ISR replicas acknowledge | Most durable | Higher |

**Recommendation**: Use `acks=all` for production event pipelines where loss is unacceptable. The latency increase is typically 1–5 ms per batch. For low-value metrics or logs, `acks=1` may suffice. Never use `acks=0` for business-critical data.

---

# Part 9: Operational Monitoring and Production Incidents

## Key Metrics to Monitor

| Metric | What to Alert On |
|--------|------------------|
| **Consumer lag** | Lag > 10K messages or > 5 min behind |
| **Under-replicated partitions** | Any partition with replicas not in sync |
| **Offline partitions** | Partition has no leader |
| **Broker disk usage** | > 80% on log directories |
| **Rebalance rate** | Frequent rebalances (instability) |
| **Request rate per broker** | Sustained > 80% capacity |
| **Compaction lag** | Old versions not cleaned for hours |

## Producer Configuration Quick Reference

| Config | Values | Impact |
|--------|--------|--------|
| `acks` | 0, 1, all | 0=fire and forget (loss), 1=leader only, all=ISR (durable) |
| `retries` | 0, N | Retries on transient failure; with idempotence, safe to retry |
| `enable.idempotence` | true | Prevents duplicates from retries within partition |
| `compression.type` | none, gzip, lz4, snappy | Reduces bandwidth and disk; lz4/snappy common |
| `batch.size` | bytes | Larger = more throughput, more latency |
| `linger.ms` | ms | Wait to fill batch; higher = more batching, more latency |

## Operational Monitoring Queries (kafka-consumer-groups)

```bash
# List consumer groups
kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list

# Describe group (lag per partition)
kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group my-consumer-group

# Output: GROUP, TOPIC, PARTITION, CURRENT-OFFSET, LOG-END-OFFSET, LAG, CONSUMER-ID, HOST
# Lag = LOG-END-OFFSET - CURRENT-OFFSET
```

## JMX / Metrics for Brokers

Key broker metrics to expose to monitoring (e.g., Prometheus, Datadog):

- `kafka.server:type=BrokerTopicMetrics,name=MessagesInPerSec` — Producer throughput
- `kafka.server:type=BrokerTopicMetrics,name=BytesInPerSec` — Producer bytes
- `kafka.server:type=ReplicaManager,name=UnderReplicatedPartitions` — Should be 0
- `kafka.log:type=LogFlushStats,name=LogFlushRateAndTimeMs` — Flush latency
- `kafka.network:type=RequestMetrics,name=TotalTimeMs` — Request handling time

**Operational tip**: Dashboard per-topic, per-partition lag. A single stuck partition can cause high aggregate lag; drill-down is essential.

## Alerting Best Practices

| Alert | Threshold | Action |
|-------|-----------|--------|
| Consumer lag | > 10K msgs or > 5 min | Page if critical consumer group; investigate slow consumer or insufficient parallelism |
| Under-replicated partitions | > 0 | Broker or network issue; data at risk |
| Offline partitions | > 0 | No leader; immediate failure |
| Broker disk | > 85% | Increase retention deletion rate; add brokers or disk |
| Rebalance rate | > 1 per 5 min | Unstable consumers; check session timeout, deployment pattern |
| Produce/consume errors | > 1% | Schema mismatch, auth, or broker overload |

**Runbook items**: (1) Consumer lag: scale consumers (if under partition count), optimize processing, check for poison messages. (2) Under-replicated: check broker health, replication throttle. (3) Disk: reduce retention, add storage, archive to cold tier.

## Production Incident Example 1: Consumer Lag Explosion

**Symptom**: Consumer lag for "order-processor" group grew from 0 to 500K in 30 minutes.

**Diagnosis**:
- 6 partitions, 6 consumers. One consumer crashed and did not restart quickly.
- During rebalance, processing paused. Producers continued at high rate.
- After rebalance, 5 consumers divided 6 partitions. One consumer got 2 partitions—both high-volume.
- That consumer became bottleneck; lag grew on its partitions.

**Resolution**:
- Restart the missing consumer to restore 6 consumers.
- Investigate why the consumer crashed (OOM, poison message, bug).
- Consider adding partitions if single-partition throughput is the limit.
- Set up lag alerts to catch earlier.

## Production Incident Example 2: Hot Partition

**Symptom**: Partition 3 of topic "user-events" had 10× the message rate of others. Consumer for P3 could not keep up.

**Diagnosis**: Partition key was `tenant_id`. One tenant (e.g., "default" or a major customer) had 90% of traffic. All their events went to one partition.

**Resolution**:
- Short-term: Add more partitions and reassign (spreads load, but breaks ordering for that key across new partitions).
- Long-term: Change partition key to `tenant_id + "_" + (user_id % 10)` or similar to distribute within tenant. Or route high-volume tenants to dedicated topics.

## Production Incident Example 3: Retention Storm

**Symptom**: Brokers running out of disk space. Topic "click-events" grew to 5 TB in 2 weeks.

**Diagnosis**: retention.ms was set to 30 days. Producers sent 100K msg/sec. Average message 500 bytes. 100K × 500 × (30 × 24 × 3600) ≈ 13 TB. Retention was too long for the volume.

**Resolution**: Reduced retention to 7 days. Added retention.bytes per partition to cap size. Considered archival to cold storage (S3) for compliance instead of keeping in Kafka. Short-term: added brokers, rebalanced partitions to spread load.

---

## Production Incident Example 4: Exactly-Once Confusion

**Symptom**: Duplicate rows in downstream database despite "Kafka exactly-once" enabled.

**Diagnosis**: Exactly-once was enabled for producer and consumer offset commit. But consumer wrote to Postgres *before* committing offset. Postgres write and Kafka commit are not atomic. Crash after Postgres write, before commit → reprocess → duplicate Postgres write.

**Resolution**: Make Postgres writes idempotent (e.g., `INSERT ... ON CONFLICT (event_id) DO NOTHING`). Or use transactional outbox pattern: write to DB outbox in same transaction as business data, then relay to Kafka. Kafka consumers still idempotent.

## Production Incident Example 5: Rebalance Storm

**Symptom**: Consumer group "order-processor" rebalancing every 30–60 seconds. Processing constantly interrupted.

**Diagnosis**: Consumers running in Kubernetes with short-lived pods (frequent restarts), or session.timeout.ms too low. Each restart/leave triggered rebalance. Session timeout default is 10s (group); heartbeat 3s. If consumer is slow to respond (GC pause, network), it may be considered dead and trigger rebalance.

**Resolution**: Increase session.timeout.ms and max.poll.interval.ms for slow processors. Use static membership (group.instance.id) so restarts don't look like new consumers. Fix deployment strategy (rolling restart with longer graceful shutdown). Consider cooperative rebalancing to reduce disruption per rebalance.

## Troubleshooting Decision Tree

```
Symptom: Consumer lag increasing
├── Fewer consumers than partitions?
│   └── Add consumers (up to partition count)
├── Consumer slow (high processing time)?
│   └── Optimize consumer; batch; async I/O
├── Hot partition?
│   └── Check per-partition metrics; fix partition key
├── Poison message?
│   └── Dead letter queue; skip after N retries
└── Producer surge?
    └── Scale consumers; or accept temporary lag

Symptom: Messages lost
├── At-most-once semantics?
│   └── Expected. Use at-least-once if loss unacceptable
├── Producer ack=0 or 1?
│   └── Use acks=all for durability
└── Retention exceeded?
    └── Increase retention; or consumer was too far behind

Symptom: Duplicate processing
├── At-least-once without idempotence?
│   └── Add idempotent handling (event_id, upsert)
├── Consumer writes to external system?
│   └── Idempotent writes required regardless of Kafka EOS
└── Rebalance during processing?
    └── Idempotent design handles this
```

---

# Part 10: Capacity Estimation and Failure Modes

## Back-of-Envelope: When Does Kafka Make Sense?

| Metric | Kafka Sweet Spot | Below This | Above This |
|--------|------------------|-------------|------------|
| **Throughput** | 1K–1M msg/sec | SQS, Redis | May need more brokers, partition tuning |
| **Retention** | 1 day–30 days | In-memory queue | Consider tiered storage, archival |
| **Consumer groups** | 2–10+ | Single consumer, direct call | Kafka shines |
| **Replay need** | Yes | Skip Kafka | Kafka essential |

## Disk Sizing for Retention

```
Disk per topic = msg_rate × avg_msg_size × retention_seconds

Example:
  50K msg/sec, 1 KB avg message, 7 days retention = 604800 seconds
  Disk = 50,000 × 1 × 604,800 = 30 TB (uncompressed)
  With compression (gzip/lz4): ~5–10 TB typical
```

Add headroom for replication and 20–30% for segment overhead. Don't over-partition: 1000+ partitions per broker has operational cost (metadata, connections, ZooKeeper load).

## Poison Messages and Dead Letter Queues

**Poison message**: A message that causes the consumer to fail repeatedly (malformed JSON, missing field, bug-triggering payload). Without handling, the consumer gets stuck: fetch → fail → retry → same message → fail.

**Strategies**: (1) **DLQ**: After N retries, publish to `topic-dlq`, commit offset, move on. (2) **Skip and log**: After N retries, log and commit; accept loss. (3) **Schema validation** at producer or consumer entry. Every production consumer should have a retry limit and DLQ or skip strategy—"retry forever" is an anti-pattern.

---

# Summary: Key Takeaways

1. **Topics, partitions, offsets**: Topic = logical stream. Partition = ordered log; parallelism ceiling. Offset = consumer position. Partitions = max useful consumers.

2. **Consumer groups**: Each partition → one consumer. Multiple groups read independently. Rebalancing pauses processing. Consumer lag = how far behind.

3. **Ordering**: Within partition only. Same partition key → same partition → ordered. Hot partitions from skewed keys.

4. **Retention**: Time or size based. Compaction keeps latest per key for changelogs. Tombstones for deletes. Combined policy for bounded compacted topics.

5. **Exactly-once**: Works inside Kafka (producer + consumer + offset). Fails at external systems. Use idempotent writes for DB/API.

6. **When Kafka is overkill**: Low throughput, no replay, single consumer → SQS or simpler. Kafka has high ops cost.

7. **Pub/Sub vs Kafka**: Pub/Sub = push, no replay. Kafka = pull, replay, persistence. Match tool to use case.

## Cross-Topic Integration: How the Pieces Fit

A single event flows through multiple systems: **Producer** sends with key → **Partition** determined by hash(key) % N → **Broker** appends to segment → **Consumer** in group reads from assigned partition → **Offset** committed after processing → **Retention/compaction** eventually deletes or compacts old segments.

Each layer has limits: too few partitions → parallelism ceiling; wrong partition key → hot partition; at-least-once without idempotence → duplicates; retention too long → disk explosion; exactly-once to DB → impossible without idempotent writes. Staff engineers understand these interactions and tune the whole system, not just one knob.

---

# Appendix: Interview-Oriented One-Liners

- **"What is a partition?"** — Ordered, append-only log. Unit of parallelism. Max consumers = partition count.
- **"What is offset?"** — Consumer's position in a partition. Committed to Kafka for resume on restart.
- **"Why partition key?"** — Same key → same partition → ordering. No key → round-robin → no ordering.
- **"What is consumer lag?"** — Messages behind. LEO − current offset. High lag = consumer can't keep up.
- **"Log compaction?"** — Keep latest message per key. Delete older versions. For changelogs, CDC.
- **"Exactly-once to Postgres?"** — Not possible with Kafka alone. Need idempotent writes.
- **"When is Kafka overkill?"** — < 100 msg/sec, no replay, single consumer. Use SQS.
- **"Pub/Sub vs Kafka?"** — Pub/Sub: push, no replay. Kafka: pull, replay, persistence.

## Key Configuration Reference (Interview Cheat Sheet)

| Component | Config | Typical Value | Purpose |
|-----------|--------|---------------|---------|
| **Topic** | num.partitions | 6–50 | Default partition count for new topics |
| **Topic** | retention.ms | 604800000 (7d) | Time-based retention |
| **Topic** | cleanup.policy | delete \| compact | Retention vs compaction |
| **Producer** | acks | all | Durability |
| **Producer** | enable.idempotence | true | No duplicates from retries |
| **Consumer** | enable.auto.commit | false | Manual commit for at-least-once |
| **Consumer** | max.poll.records | 500 | Batch size per poll |
| **Consumer** | max.poll.interval.ms | 300000 (5m) | Max time between polls before rebalance |
| **Consumer** | isolation.level | read_committed | For transactional/read-process-write |

## Topic Creation: Recommended Defaults

When creating a new topic, specify at minimum: `--partitions`, `--replication-factor`, `--config retention.ms`, and for changelog topics `--config cleanup.policy=compact`. Example:

```bash
# Event stream topic
kafka-topics.sh --create --topic order-events \
  --partitions 24 --replication-factor 3 \
  --config retention.ms=604800000 \
  --config compression.type=lz4

# Changelog topic (state store, CDC)
kafka-topics.sh --create --topic user-profiles \
  --partitions 12 --replication-factor 3 \
  --config cleanup.policy=compact \
  --config retention.ms=2592000000
```

**Staff tip**: Create topics explicitly rather than relying on auto-create. Auto-create uses broker defaults (often 1 partition, short retention) which are rarely correct for production.

## Multi-Region Kafka: Brief Overview

**Single region**: Brokers in one region. Lowest latency. No cross-region replication.

**Multi-region replication**: MirrorMaker 2, Confluent Replicator, or custom consumers that produce to another cluster. Use when: disaster recovery, global read proximity, or data residency. **Trade-offs**: Replication lag (seconds to minutes); complexity of failover; potential duplicate processing if both regions consume.

**MirrorMaker 2**: Reads from source cluster, produces to target. Supports topic renaming (e.g., `us.orders` → `eu.orders`). Consumer groups are not replicated—each region has its own consumer groups and offsets.

**Staff Insight**: Multi-region Kafka is operationally complex. Only adopt when single-region doesn't meet requirements (RTO/RPO, latency for global users). Start with single region; add replication when needed.

---

## Real-World Throughput and Sizing

**Typical single-broker throughput**: 100–200 MB/sec write, 200–400 MB/sec read (depending on replication, acks, compression). For 1 KB messages: ~100K–200K msg/sec per broker.

**Partition throughput**: A single partition can handle ~10–30 MB/sec sustained. More partitions = more parallelism but more metadata and connections. Sweet spot: 10–100 partitions per topic for most workloads.

**Consumer throughput**: Bounded by processing, not Kafka. If each message requires 10 ms of work (DB write, API call), one consumer handles ~100 msg/sec. To reach 10K msg/sec, need 100 consumers = 100 partitions minimum.

**Staff Insight**: Sizing is iterative. Start conservative (e.g., 12 partitions, 3 brokers); monitor lag and throughput; scale partitions and consumers as needed. Over-provisioning partitions is easier to fix than under-provisioning.

## Checklist: Production Kafka Readiness

Before going live with a Kafka-based pipeline:

- [ ] **Partition count** matches or exceeds expected consumer count; partition key chosen for ordering and load distribution
- [ ] **Retention** (time and/or size) set; disk capacity planned for retention × throughput
- [ ] **Consumer** uses manual commit, processes idempotently, has retry limit and DLQ or skip strategy
- [ ] **Producer** uses acks=all, idempotence enabled for at-least-once semantics
- [ ] **Monitoring** in place: consumer lag, under-replicated partitions, broker disk, rebalance rate
- [ ] **Runbooks** for common incidents: lag spike, under-replicated, disk full, rebalance storm
- [ ] **Schema** defined (Avro/Protobuf + registry) with compatibility policy; avoid opaque blobs
- [ ] **Topics** created explicitly with correct config; no reliance on auto-create defaults

**Staff discipline**: Skipping any item above increases incident risk. The most common production failures—lag explosion, duplicate processing, disk exhaustion, rebalance storms—map directly to gaps in this checklist. Review this list with the team before each new Kafka-backed pipeline goes live. Document deviations and their justification; revisit when requirements or scale change. This discipline separates production-ready event pipelines from those that become operational burdens.

---

## End of Supplement

*Word count: ~10,000. Covers Topics 281–287: Topics/Partitions/Offsets, Consumer Groups, Ordering/Partition Keys, Retention/Compaction, Exactly-Once, When Kafka Is Overkill, Pub/Sub vs Kafka.*

This supplement complements Chapter 23 with Kafka-specific depth for topics 281–287. For interview prep: master the L5 vs L6 tables, the troubleshooting decision tree, the production incident patterns, and the decision frameworks (when Kafka, when Pub/Sub, when SQS). For systems design: use the capacity estimation formulas, the partition count reasoning, and the exactly-once boundary understanding. The goal is not to memorize—it is to reason correctly when the interviewer asks "why" or "what happens when."

## Staff Interview Walkthrough: "Design an Event Pipeline for Order Processing"

**Interviewer**: "We need to process 50K orders per second. Design the event pipeline. Discuss Kafka internals."

**Strong Answer Structure**:

1. **Partitioning and parallelism**: "At 50K orders/sec, we need significant parallelism. Each partition can support roughly 10–50K msg/sec depending on message size and broker config. We'd start with 50–100 partitions. Partition key = order_id so all events for one order are ordered. Max consumers = partition count. We'd run 50–100 consumer instances."

2. **Consumer groups**: "We'll have multiple consumer groups: order-processor (fulfillment), analytics (aggregations), search-indexer (elasticsearch). Each reads the full stream independently at its own pace. Lag in analytics doesn't block order processing."

3. **Retention**: "Order events need 7–30 days for compliance and replay. retention.ms=2592000000 (30 days). For changelog-style topics (e.g., order state), we'd use compaction to keep latest per order_id."

4. **Exactly-once**: "We need exactly-once to our fulfillment DB. Kafka EOS covers producer→Kafka→consumer→Kafka. Our consumer writes to Postgres—outside the transaction. We'll use idempotent writes: INSERT ... ON CONFLICT (order_id, event_type) DO NOTHING, or a processed_events table. At-least-once delivery + idempotence = effective exactly-once."

5. **Operational concerns**: "We'll monitor consumer lag per partition. Hot partitions would indicate a bad partition key. We'd use static membership to reduce rebalances during deployments. Retention will drive disk—50K msg/sec × 30 days × avg message size; we'd size brokers accordingly."

**Key Staff Signal**: The candidate connects partition count to throughput, partition key to ordering, consumer groups to independent pipelines, and EOS boundaries to idempotent design. They quantify (50K/sec, 50–100 partitions) and address operations (lag, retention, disk).

**Follow-up**: "What if we need to add a new consumer group that does ML inference? Any considerations?"  
**Strong answer**: "Same topic, new consumer group. No change to producers or existing consumers. We need to size for lag—ML inference may be slow; we might need more partitions if a single partition's throughput can't keep up. We'd also ensure the ML model can handle out-of-order and duplicate events (idempotent) since we're at-least-once."

---

## Schema Registry and Schema Evolution

When using Avro or Protobuf with Kafka, a **Schema Registry** (e.g., Confluent Schema Registry) stores schemas. Producers and consumers fetch schemas by ID from the registry. This enables:

- **Evolution**: Add optional fields, remove optional fields, with compatibility rules
- **Validation**: Invalid schemas rejected at producer
- **Decoupling**: Consumers can evolve independently if schemas are backward compatible

**Compatibility modes**: BACKWARD (new consumer reads old producer), FORWARD (old consumer reads new producer), FULL (both). Breaking changes (rename required field, change type) require new schema version and often a new topic or migration.

**Staff Insight**: Schema evolution is organizational as much as technical. Define compatibility policy; use schema registry from day one for event topics. Avoid "string blob" events—they become unmaintainable.

## Resetting Consumer Offsets: When and How

**When**: Replay from beginning after bug fix; reprocess after schema change; disaster recovery; testing.

**How**: Use `kafka-consumer-groups.sh --reset-offsets`. Options: `--to-earliest`, `--to-latest`, `--to-datetime`, `--shift-by N`. Run with `--dry-run` first. **Warning**: Resetting causes reprocessing. Ensure consumers are idempotent, or you'll create duplicates. For critical groups, coordinate with stakeholders—replay may take hours and increase load.

**Alternative**: Create a new consumer group with a new name; it starts from `auto.offset.reset` (earliest or latest). Leave the old group as-is. Useful when you want a one-off replay without affecting the production group.

---

## Kafka Streams vs Consumer API: When to Use Which

**Consumer API**: Low-level. You manage offset commits, partition assignment, rebalancing. Full control. Use when: custom processing logic, non-JVM languages, or when Kafka Streams doesn't fit.

**Kafka Streams**: Library on top of consumer API. Provides: exactly-once processing (with EOS), state stores (RocksDB), windowing, aggregations, joins. Use when: stream processing within the JVM (Java, Kotlin, Scala), need stateful operations (count, sum, windows), or built-in exactly-once to output topics.

**Kafka Connect**: For source/sink connectors (DB → Kafka, Kafka → S3). Not for custom business logic. Use when: ingesting from DB (Debezium) or exporting to data lake.

**Staff Insight**: For "read event, transform, write to another topic" with state (e.g., user session aggregation), Kafka Streams is the right choice. For "read event, call external API, write to Postgres," the Consumer API is simpler. Don't reach for Kafka Streams for stateless pass-through.

---

## Extended Interview Q&A

**Q: "We have 6 partitions and 12 consumers. Why is lag still high?"**  
A: Only 6 consumers are doing work; 6 are idle (max consumers = partitions). Either add partitions (and reassign) to use 12 consumers, or accept that parallelism is capped at 6. Lag might be from slow processing, not insufficient consumers.

**Q: "How do you ensure ordering for a user's events?"**  
A: Use `user_id` as partition key. All events for that user go to the same partition; strict ordering. Trade-off: one very active user = hot partition. Mitigate with key salting or dedicated handling for high-volume users.

**Q: "Our compacted topic is huge. Why?"**  
A: Compaction keeps latest per key. If you have millions of unique keys, the topic stays large. Retention (compact+delete) can bound age. Also, compaction lag—old versions may not be removed yet. Check log cleaner throughput.

**Q: "We enabled exactly-once but still get duplicates in our database."**  
A: Kafka exactly-once covers producer→Kafka and consumer offset commit. Database write is outside that. You need idempotent writes: upsert by event_id, or "processed_events" table to skip duplicates.

**Q: "When would you choose SQS over Kafka?"**  
A: Simple task queue, single consumer, < 100 msg/sec, no replay needed, team wants minimal ops. SQS is managed, pay-per-use. Kafka is for event streaming, replay, multiple consumer groups, high throughput.

**Q: "What happens during a consumer group rebalance?"**  
A: Partitions are reassigned. All consumers (in older implementations) pause, give up partitions, receive new assignment, resume. Processing stops for seconds to tens of seconds. Cooperative rebalancing (Kafka 2.4+) reduces pause. Avoid frequent rebalances—static membership, stable deployments.

**Q: "How do you add partitions to an existing topic?"**  
A: `kafka-topics.sh --alter --topic X --partitions N`. Partitions are added; existing data is not re-distributed (new partitions start empty). New keys will distribute across new partitions; old partitions keep their data. Rebalancing is triggered for consumer groups. Plan for temporary load skew.

**Q: "What is the difference between consumer offset and producer acknowledgment?"**  
A: Producer ack (acks=0/1/all) = when producer considers the write "done." acks=all waits for all ISR replicas. Consumer offset = consumer's position in the partition, committed to `__consumer_offsets`. They're independent: producer can have acks=1 (only leader), consumer can still read once leader has it.

**Q: "Why might a compacted topic grow indefinitely?"**  
A: Millions of unique keys. Compaction keeps latest per key; if keys never repeat (e.g., event_id as key), there's nothing to compact—each key has one message. Use compaction only when keys are reused (e.g., user_id, order_id for state). For event streams with unique IDs, use delete retention.

---

## Common Misconceptions

| Misconception | Reality |
|---------------|---------|
| "Kafka is a queue" | Kafka is an append-only log. Can behave like a queue with consumer groups, but persistence and replay differ. |
| "More consumers = more throughput" | Only up to partition count. 8 consumers, 4 partitions → 4 idle. |
| "Exactly-once means no duplicates ever" | Only within Kafka. External systems need idempotent writes. |
| "Compaction deletes old messages immediately" | Compaction runs asynchronously. Lag can be hours. |
| "Partition key ensures global ordering" | Only within partition. Same key → same partition → ordered. Different keys → no ordering. |
| "Adding partitions is free" | Triggers rebalance, reassignment. Can cause temporary skew. |
