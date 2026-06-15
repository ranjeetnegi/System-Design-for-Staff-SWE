# Chapter 34: Kafka Internals — Topics, Partitions, Consumer Groups, Retention, and Exactly-Once
## Part A: The Log, Brokers, Replication, and Consumer Groups

---

## 1. Chapter Opening: What This Chapter Is About

### Why go deeper on Kafka internals?

Chapter 33 taught you the *what* and *when* of Kafka. You learned delivery semantics — at-most-once, at-least-once, exactly-once. You learned Event-Driven Architecture patterns, the Saga pattern, Change Data Capture. You learned when to reach for Kafka versus SQS versus RabbitMQ. That chapter gave you the architect's-eye view.

This chapter teaches the *how*. What happens inside the machine when a message is published? Where does data actually live on disk? Why does adding a sixth consumer to a five-partition topic do literally nothing? Why did your Kafka lag spike during a rolling deployment? Why is your compacted topic still growing after you configured it to compact old data?

These are not trivia questions. They are the follow-up questions that separate an L5 answer from an L6 answer in a system design interview. Here is what that difference looks like in practice:

**L5 answer:** "I would use Kafka here because it handles high throughput and allows replay."

**Interviewer follow-up:** "How many partitions would you use?"

**L5 answer:** "Maybe 10 or 20, based on expected throughput."

**L6 answer:** "I would start by measuring peak consumer processing throughput per instance, then set partition count = peak_producer_throughput / per_consumer_throughput. For 10 MB/sec producer throughput and 2 MB/sec per consumer, I need at least 5 partitions. I would round up to 8 to leave headroom and keep it a power of two so key-based routing stays stable when I horizontally scale consumers. I would not go above 30 partitions for this use case because each partition adds replication overhead and Zookeeper watches, and we don't need that much consumer parallelism."

That answer requires knowing what a partition is at the mechanical level — not just as a concept but as a concrete data structure with real performance implications. That is what this chapter delivers.

The other important distinction at L6: you must be able to reason about *failure modes*, not just happy-path behavior. What happens to your in-flight messages if the leader broker dies mid-write? (Answer: depends on acks configuration and ISR state at that moment.) What happens to your consumer group if it can't connect to the group coordinator? (Answer: consumers continue processing existing partition assignments but cannot rebalance or commit offsets; after session.timeout.ms, they stop.) These failure-mode answers come naturally once you understand the mechanics below.

**What you will understand after reading this chapter:**

- Why Kafka stores data the way it does (the append-only log and why it is fast)
- What topics and partitions are at the file-system level
- How brokers, leaders, followers, and ISR work — and what happens during a broker failure
- How consumer groups divide work and why there is a hard ceiling on parallelism
- Why rebalancing hurts and what the newer strategies do differently
- How Kafka manages retention — time-based, size-based, and log compaction
- What exactly-once delivery actually means mechanically (idempotent producers and transactions)

---

## 2. The Append-Only Log: Kafka's Core Data Structure

### Why Kafka is not a message queue

Before anything else, you need to understand what Kafka *is* at the structural level, because it is fundamentally different from what most people call a "message queue."

Think about a traditional message queue — SQS, RabbitMQ — like a physical mailbox at your house. The mail carrier (producer) puts letters (messages) into the mailbox. You (the consumer) collect your mail. Once you take a letter out, it is gone. The mailbox is empty again. No one else can read that letter after you collect it. You cannot go back and re-read yesterday's mail once you've taken it. The system is designed around a single reader consuming and removing messages.

**Kafka is completely different.** Think of Kafka like a newspaper publishing company — the New York Times, for example. The printing press (producer) runs every morning and prints one master copy of the newspaper. Thousands of subscribers (consumer groups) each get a copy. Subscriber A reads the sports section at 8am. Subscriber B reads the same paper's sports section at noon. Subscriber C, who forgot to read for three weeks, goes to the archive and gets back issues. The printing press doesn't care how many people read the paper or when. The archive holds papers for a fixed retention period — 7 days, 30 days — and then disposes of old issues.

This distinction — **log versus queue** — is Kafka's entire design philosophy. The log is persistent. Multiple readers can read it independently. Readers can replay from any point. Adding a new reader does not affect existing readers. The data exists on disk regardless of whether anyone has consumed it, until retention expires.

This is why LinkedIn built Kafka in 2011. They needed multiple internal systems to each independently consume the same stream of user activity events. A message queue would require them to duplicate data to each consumer. A log lets every consumer read independently from one canonical source.

### The log data structure

A **log** — in the computer science sense, not the debugging sense — is an append-only, ordered sequence of records. The word "append-only" is critical. You can only add records to the end of the log. You cannot go back and modify record number 47. You cannot delete record number 12 (outside of retention expiry). You cannot insert a record between records 100 and 101. The log only grows forward.

Why does append-only matter? Performance. The most expensive operation on a spinning hard disk is the *seek* — physically moving the read/write head to a new position on the disk surface. Random writes scatter data all over the disk, requiring constant seeks. A spinning disk can do roughly 0.5 MB/second of random writes because it spends most of its time seeking.

Sequential writes go to one place: the end of the file. No seeking. A spinning disk can do 200 MB/second of sequential writes — that is 400 times faster. Even SSDs, which have no moving parts, show a similar ratio because sequential writes allow larger batched I/O operations that fill memory pages more efficiently.

Append-only also means Kafka can use the operating system's **page cache** aggressively. When you write to the end of a file, the OS keeps the most recent pages in RAM. Consumer reads almost always want recent messages. Those recent messages are already in RAM from the write. So a Kafka broker serving a real-time consumer pipeline is often doing zero disk I/O for reads — everything is served from the OS page cache in memory.

Every record in a Kafka log has an **offset**: a sequential integer starting at 0 for the first record. Offset 0 is the oldest record (or the oldest within the retention window). Offset 999 is the 1000th record. Offset is how both Kafka and consumers track position.

```
Kafka Partition Log — Append Only
====================================

     oldest                                          newest
       |                                               |
       v                                               v
  +----+----+----+----+----+----+----+----+----+----> (end, LEO)
  | 0  | 1  | 2  | 3  | 4  | 5  | 6  | 7  | 8  |
  +----+----+----+----+----+----+----+----+----+---->
       ^                              ^
       |                              |
   consumer                     new writes
   reading                     appended here
   at offset 0                 (sequential, fast)

  Offset = position in log (0-indexed, never changes)
  You can ONLY append at the right end.
  You can READ from any offset.
```

This is the entire foundation of Kafka. Everything else — topics, partitions, consumer groups, replication — is built on top of this one simple data structure.

### Partitions on disk: what the file system actually looks like

When Kafka stores a partition on a broker's disk, it does not write one giant file. It writes **segments** — a series of fixed-size files, each capped at `log.segment.bytes` (default: 1 GB).

Think of it like a long book being split into volumes. Volume 1 holds chapters 1-100, volume 2 holds chapters 101-200, and so on. When you want chapter 150, you know it is in volume 2 without scanning volume 1 at all.

Each segment is identified by the offset of the first message it contains. So a partition directory on a broker looks like this:

```
Partition Data on Disk — Broker File System
=============================================

/kafka/data/order-events-0/        <- topic "order-events", partition 0
  00000000000000000000.log          <- segment starting at offset 0
  00000000000000000000.index        <- offset index for this segment
  00000000000000000000.timeindex    <- timestamp index for this segment
  00000000001073741824.log          <- segment starting at offset 1,073,741,824
  00000000001073741824.index
  00000000001073741824.timeindex
  00000000002147483648.log          <- latest (active) segment
  00000000002147483648.index
  00000000002147483648.timeindex
  leader-epoch-checkpoint

  .log   = the actual message data (append-only)
  .index = sparse offset-to-byte-position index (find offset fast)
  .timeindex = sparse timestamp-to-offset index (find by time)
```

The `.index` file is how Kafka finds a specific offset efficiently. It is a sparse index: instead of indexing every offset (which would be huge), it stores an entry every `log.index.interval.bytes` (default 4 KB). To find offset 5000:
1. Binary search the `.index` file to find the largest indexed offset <= 5000, get its byte position.
2. Scan the `.log` file linearly from that byte position until you find offset 5000.

This means Kafka can find any message by offset in O(log N) + small linear scan time. For a 1 GB segment with messages averaging 1 KB each: roughly 1 million messages, index has ~250,000 entries, binary search finds the right 4 KB block, linear scan through at most a few hundred entries. Fast.

The **active segment** is the most recent segment — the one being appended to right now. All other segments are **closed** (sealed). Retention and compaction operate on closed segments. The active segment is never touched by retention or compaction while it is still receiving writes.

### Topics: naming the log

A **topic** is a named log. That is all it is. The name "order-events" is a label that says "this log holds order events." The name "user-signups" labels another log. Producers publish records to a topic name. Consumers subscribe to a topic name.

The topic itself is an organizational concept — like naming a folder on your computer. The actual data storage and behavior come from what is inside the topic: partitions.

Topics can hold any byte payload. Kafka does not care what format your data is in — raw bytes, JSON, Avro, Protobuf. Format is the producer's and consumer's problem. Kafka just stores and delivers bytes.

Common topics you'd see at real companies:

- Netflix: `playback-events`, `recommendation-signals`, `encoder-jobs`
- Uber: `ride-state-changes`, `driver-location-updates`, `fare-calculation-requests`
- LinkedIn: `user-activity-events`, `connection-graph-updates`, `ad-click-events`

### Partitions: splitting the log for parallelism

One log on one machine has a throughput ceiling. One machine can write maybe 500 MB/sec to disk. At high volume — say, Uber ingesting 1 million location updates per second — a single log is a bottleneck.

The solution is **partitioning**: split one topic into N independent sub-logs, each called a **partition**. Each partition is a completely independent append-only log, typically stored on a different broker (machine).

Topic "order-events" with 4 partitions means 4 independent logs. 4 producers can write to 4 different partitions simultaneously. 4 consumers can read from 4 different partitions simultaneously. Throughput scales roughly linearly with partition count (up to hardware limits).

The trade-off: **ordering is guaranteed WITHIN a partition, but NOT across partitions.**

Analogy: imagine a supermarket with 4 checkout lanes. Each lane is strictly ordered — customers are served first-come-first-served within that lane. But a customer who arrived at lane 3 after a customer in lane 1 might finish checking out first if lane 3's line moved faster. There is no global ordering across lanes. Similarly, messages within Kafka partition 2 are strictly ordered by offset. But message at partition 2 offset 50 might have arrived *after* message at partition 3 offset 200 in wall-clock time.

**Key insight for L6 interviews:** if your use case requires strict global ordering across all events (rare), you must use 1 partition (losing parallelism) or encode ordering information in the messages themselves. For most use cases, per-entity ordering is sufficient: all events for Order #12345 go to the same partition, guaranteeing they are processed in order, even if Order #12346's events go to a different partition.

```
Topic: "order-events" — 4 Partitions
===========================================

Partition 0:  +--+--+--+--+--+--+---->
              | 0| 1| 2| 3| 4| 5|
              +--+--+--+--+--+--+---->

Partition 1:  +--+--+--+--+--+--+---->
              | 0| 1| 2| 3| 4| 5|
              +--+--+--+--+--+--+---->

Partition 2:  +--+--+--+--+--+--+---->
              | 0| 1| 2| 3| 4| 5|
              +--+--+--+--+--+--+---->

Partition 3:  +--+--+--+--+--+--+---->
              | 0| 1| 2| 3| 4| 5|
              +--+--+--+--+--+--+---->

  Each partition is an independent log.
  Ordering guaranteed WITHIN each partition.
  No ordering guarantee ACROSS partitions.

  Producer A --->  Partition 0
  Producer B --->  Partition 1
  Producer C --->  Partition 2
  Producer D --->  Partition 3

  Consumer 1 reads from Partition 0
  Consumer 2 reads from Partition 1
  Consumer 3 reads from Partition 2
  Consumer 4 reads from Partition 3
```

### Partition key: controlling which partition a message goes to

When a producer sends a message, it can include a **partition key** — a string like an order ID, a user ID, or a device ID.

Kafka computes: `partition = hash(key) % num_partitions`

Messages with the same key always go to the same partition. All events for Order #12345 (key="12345") always go to the same partition, guaranteeing they are ordered relative to each other. Events for Order #99999 (different hash) go to a different partition.

If no key is provided: Kafka uses **round-robin** by default — message 1 to partition 0, message 2 to partition 1, message 3 to partition 2, etc. This maximizes distribution but gives no ordering guarantee across messages from the same producer.

**L6 interview trap:** "What happens if you increase partition count after launch?" The hash function changes. `hash("12345") % 4` might map to partition 2, but `hash("12345") % 8` maps to partition 6. Messages for the same key that were in partition 2 are now being routed to partition 6. Consumers reading partition 2 will see old messages; consumers reading partition 6 will see new messages. Order ID 12345's event history is now split across two partitions. This is why you should plan partition count carefully before launch — changing it is painful.

### Offsets: tracking position in the log

Every message in every partition gets a **offset**: a sequential integer, unique within that partition, starting at 0.

Partition-local means: Partition 0, Offset 50 and Partition 1, Offset 50 are two completely different messages. The offset number 50 only means something in the context of a specific partition.

Two critical offset concepts for operations:

**Log End Offset (LEO):** the offset of the next message to be written. If 1,000 messages have been written to a partition (offsets 0–999), the LEO is 1,000. This is the "front" of the log.

**Consumer Committed Offset:** the offset the consumer has explicitly acknowledged processing up to. If the consumer committed offset 950, it means "I have successfully processed messages 0 through 950."

**Consumer Lag** = LEO - Consumer Committed Offset

Lag is the most important operational metric for Kafka consumers. Lag=0 means the consumer is keeping up. Lag growing over time means the consumer is falling behind the producer. Lag=50,000 and growing means you need more consumers or faster processing logic.

```
Partition 0: Consumer Lag Example
==========================================

  Log:
  +--+--+--+--+--+     +--+--+--+
  | 0| 1|...|950| ... |998|999|   <-- LEO = 1000
  +--+--+--+--+--+     +--+--+--+
                ^                       ^
                |                       |
          Consumer                    LEO
          committed                  = 1000
          offset=950

  LAG = LEO - consumer offset
      = 1000 - 950
      = 50 messages behind

  If LAG is 0: consumer is caught up (real-time processing)
  If LAG is growing: consumer is slower than producer (danger)
  If LAG is shrinking: consumer is catching up (recovery)
```

Lag monitoring is how on-call engineers detect that a consumer is sick. Kafka's built-in consumer lag metric, plus tools like Burrow (open-sourced by LinkedIn) or Datadog's Kafka integration, alert when lag exceeds a threshold.

---

## 3. Brokers, Leaders, and Replication

### What is a broker?

A **broker** is a Kafka server process running on a physical or virtual machine. It receives messages from producers, stores them on disk, and serves them to consumers. A Kafka cluster is a group of brokers working together.

Typical cluster sizes by company scale:

- Small startup: 3 brokers (minimum for fault tolerance)
- Medium scale (Stripe, Airbnb): 10–30 brokers
- Large scale (LinkedIn, Netflix): 100+ brokers across multiple data centers

No single broker stores all the data. Data is distributed across brokers. Each broker stores some partitions, not all. This distribution is what allows Kafka to scale beyond the disk capacity and throughput of any one machine.

Analogy: a broker is like a branch of a bank. The bank (Kafka cluster) has many branches (brokers). Each branch holds some customer accounts (partitions). If one branch closes for repairs (broker failure), other branches handle the work. No single branch closure takes down the entire bank.

### Leaders and followers

Here is the critical question: if topic "order-events" has 4 partitions and 3 brokers, which broker stores which partition?

Kafka's answer is replication with a **leader/follower** model.

For each partition, Kafka assigns:
- One **leader** broker: handles all reads AND writes for that partition
- One or more **follower** (replica) brokers: copy the data from the leader but do not serve clients directly

**Replication factor** determines how many total copies exist (1 leader + N followers).

- Replication factor 1: 1 copy total. No redundancy. Broker dies = data lost. Use only for non-critical, disposable data.
- Replication factor 2: 1 leader + 1 follower. Can lose 1 broker. Used for dev/staging environments.
- Replication factor 3: 1 leader + 2 followers. Can lose 2 brokers. Standard production setting.

```
Partition P0 — Replication Factor 3
=========================================

  +----------+     +----------+     +----------+
  | Broker 1 |     | Broker 2 |     | Broker 3 |
  |          |     |          |     |          |
  | P0 LEADER|     | P0 FOLLOW|     | P0 FOLLOW|
  | [0,1,...] |     | [0,1,...] |     | [0,1,...] |
  +----------+     +----------+     +----------+
       ^                |                |
       |    replicates <-+                |
       |    replicates <------------------+
       |
  Producer writes to Leader only.
  Consumers read from Leader only (by default).
  Followers are hot standbys.

  If Broker 1 dies:
  - Controller elects Broker 2 or 3 as new Leader for P0
  - Producer and consumers redirect to new Leader
  - Recovery time: typically < 1 second (KRaft mode)
```

Kafka's assignment tries to distribute leaders evenly across brokers. If you have 12 partitions and 3 brokers, each broker should be the leader for roughly 4 partitions. This is called **partition leadership balance**. If a broker fails and comes back, Kafka can **preferred leader election** to rebalance leadership back.

### In-Sync Replicas (ISR)

The **ISR (In-Sync Replica set)** is the set of replicas (including the leader) that are currently caught up with the leader's log.

"Caught up" is defined by `replica.lag.time.max.ms` (default: 30 seconds in modern Kafka). A follower is in-sync if it has fetched all messages from the leader within the last 30 seconds. If a follower falls behind by more than this window — due to network issues, GC pauses, slow disk — it is **removed from the ISR**.

Why does ISR matter? It controls durability.

When a producer sends with `acks=all`, the leader waits for all replicas in the ISR to confirm they have written the message before sending an ACK to the producer. If ISR = {Leader, Follower1, Follower2}, all three must confirm. If ISR = {Leader} (only the leader is in-sync), only the leader needs to confirm — but now the data only exists on one machine.

```
ISR Example — P0 with 3 replicas
==========================================

  Normal state (all caught up):
  Leader  LEO=500 -----> ISR
  Follow1 LEO=500 -----> ISR   (in-sync, replicating normally)
  Follow2 LEO=500 -----> ISR

  acks=all: all 3 must confirm write. Safe.

  ---

  Follower2 has network issues:
  Leader  LEO=800 -----> ISR
  Follow1 LEO=800 -----> ISR
  Follow2 LEO=503 -----> NOT ISR (fell behind, removed)

  ISR = {Leader, Follow1} only.

  acks=all: only Leader + Follow1 must confirm.
  If Leader dies now, Follow1 has all data. Safe.
  But if BOTH Leader and Follow1 die: Follow2 has stale data.
  Under-replicated partition = danger alert!

  ---

  "Under-replicated partition" = ISR size < replication factor
  Monitor this metric in production. It is a red alert.
```

**Under-replicated partitions** are one of the most important Kafka operational metrics. If `kafka.server:type=ReplicaManager,name=UnderReplicatedPartitions` goes above 0, you have partitions where data safety is degraded. Alert on this immediately.

The `min.insync.replicas` (ISR) configuration sets the minimum number of in-sync replicas a leader must have before it will accept writes with `acks=all`. Setting `min.insync.replicas=2` with replication factor 3 means: if two replicas fall out of ISR and only the leader remains, the leader will **refuse writes** rather than accept data that could be lost. This is a safety valve: better to error loudly than to silently lose data.

```
min.insync.replicas in action
==========================================

  Config: replication.factor=3, min.insync.replicas=2

  ISR = {Leader, F1, F2}: accepts writes (ISR size=3 >= 2)
  ISR = {Leader, F1}:     accepts writes (ISR size=2 >= 2)
  ISR = {Leader}:         REJECTS writes with NotEnoughReplicas
                          (ISR size=1 < 2)

  Producer gets an exception. This is intentional.
  Data durability > availability in this configuration.
  Appropriate for financial transactions, not for logs.
```

### Controller: the cluster manager

One broker in the cluster is elected the **Controller**. The Controller is responsible for:

1. Monitoring broker health (via Zookeeper watches or KRaft heartbeats)
2. Detecting when a broker fails
3. Electing new partition leaders when a broker fails
4. Propagating cluster metadata changes to all brokers

The Controller is just a regular broker that also happens to have the Controller role. It is elected by competing to write to a Zookeeper path (in older Kafka) or by Raft consensus (KRaft, Kafka 2.8+).

**KRaft mode** (Kafka 3.x, the default from Kafka 3.3+) replaced Zookeeper with an internal Raft-based metadata log. Before KRaft, Kafka required a separate Zookeeper cluster — additional infrastructure to operate and a source of failure. KRaft embedded the consensus protocol directly into Kafka brokers (or dedicated controller nodes).

Why KRaft matters operationally: Zookeeper-based leader election after a broker failure took 30–60 seconds because each partition leader election was a separate Zookeeper write. With KRaft, the Controller can elect leaders for thousands of partitions in under a second via a single Raft log entry. LinkedIn's Kafka team documented recovering a 500-partition topic from broker failure in under 200ms with KRaft versus 45 seconds with Zookeeper.

### Producing a message: the full step-by-step flow

Let's walk through exactly what happens when a producer at Uber sends one message to the "ride-state-changes" topic.

```
Producer -> Kafka: Full Write Path
==========================================

Step 1: Get cluster metadata
  Producer --> any Broker (bootstrap)
              "Give me the broker list and leader map"
  Broker  --> Producer
              "Broker1=10.0.0.1, Broker2=10.0.0.2, Broker3=10.0.0.3
               P0 leader=Broker1, P1 leader=Broker2, P2 leader=Broker3"

Step 2: Choose partition
  key = "ride-12345"
  partition = hash("ride-12345") % 3 = 1
  Leader for P1 = Broker2

Step 3: Send message to leader
  Producer --> Broker2 (P1 Leader)
               batch of messages for P1

Step 4: Leader appends and replicates
  Broker2 appends to P1 log at offset 500
  Broker1 and Broker3 (followers) pull from Broker2
  Broker1 LEO for P1 becomes 501
  Broker3 LEO for P1 becomes 501

Step 5: Acknowledge
  If acks=0:  Producer doesn't wait. No ACK needed.
  If acks=1:  Broker2 sends ACK after its own write.
  If acks=all: Broker2 waits for Broker1+Broker3 to confirm,
               THEN sends ACK to producer.

  Producer --> done, send next batch.
```

The **producer batch** is an important performance detail. Producers do not send messages one-at-a-time by default. They accumulate messages in a buffer and send batches. Two configs control this:

- `linger.ms` (default 0): how long to wait for the buffer to fill before sending. Setting `linger.ms=5` means wait up to 5ms for more messages to arrive before sending a batch. This increases latency slightly but dramatically increases throughput.
- `batch.size` (default 16,384 bytes = 16 KB): maximum batch size. When the batch reaches this size, it is sent immediately regardless of `linger.ms`.

Netflix uses `linger.ms=20` and `batch.size=512KB` for their high-throughput event pipelines, trading 20ms of extra latency for 10x throughput improvement.

### The acks configuration: durability vs speed

The `acks` configuration is the single most important producer setting for reliability.

| acks value | Who must confirm | Latency | Durability | When to use |
|------------|-----------------|---------|------------|-------------|
| 0 | Nobody | Lowest | None — fire and forget | Metrics, non-critical logs |
| 1 | Leader only | Low | Leader write — loses data if leader dies before replication | Medium-criticality events |
| all (or -1) | All ISR replicas | Higher | Survives broker failures as long as 1 ISR replica lives | Financial events, orders, critical state |

Real numbers from LinkedIn's Kafka team: `acks=all` with 3 replicas adds roughly 3–7ms of additional latency compared to `acks=1`, because the producer must wait for two additional network round-trips (leader to follower, follower ACK back to leader, leader ACK to producer). For a payment system processing $10M transactions per day, that 3ms is worth paying for guaranteed durability. For an analytics beacon tracking page views, `acks=1` or even `acks=0` is fine — losing some events is acceptable.

---

## 4. Consumer Groups: Scaling Reads

### The problem: one consumer can't keep up

Imagine Uber's "driver-location-updates" topic receives 2,000,000 messages per second during peak hours — every driver app sends a GPS coordinate update every second, and Uber has 2 million drivers active globally. A single consumer instance processing 200,000 messages per second would fall behind at 10× the rate. Lag would grow at 1.8M messages per second. Within an hour: 6.48 billion messages of lag. That consumer will never catch up.

The solution is **consumer groups**: multiple consumer instances sharing the work of reading a topic.

### How consumer groups work

A **consumer group** is a named collection of consumer instances that cooperate to read all partitions of one or more topics. Within a group, each partition is assigned to exactly one consumer. The partition's messages flow to only that one consumer in the group.

The rules:

```
Consumer Group Assignment Rules
==========================================

Topic: "driver-location-updates" — 6 Partitions (P0 through P5)

  Case 1: 2 consumers in group "location-processor"
  +------------+   +------------+
  | Consumer 1 |   | Consumer 2 |
  | reads P0   |   | reads P3   |
  | reads P1   |   | reads P4   |
  | reads P2   |   | reads P5   |
  +------------+   +------------+
  Each consumer reads 3 partitions.

  Case 2: 6 consumers in group "location-processor"
  +----+ +----+ +----+ +----+ +----+ +----+
  | C1 | | C2 | | C3 | | C4 | | C5 | | C6 |
  | P0 | | P1 | | P2 | | P3 | | P4 | | P5 |
  +----+ +----+ +----+ +----+ +----+ +----+
  Maximum parallelism. Each consumer reads 1 partition.

  Case 3: 8 consumers in group "location-processor"
  +----+ +----+ +----+ +----+ +----+ +----+ +----+ +----+
  | C1 | | C2 | | C3 | | C4 | | C5 | | C6 | | C7 | | C8 |
  | P0 | | P1 | | P2 | | P3 | | P4 | | P5 | idle| idle|
  +----+ +----+ +----+ +----+ +----+ +----+ +----+ +----+
  C7 and C8 are IDLE. They have no partitions. Wasted resources.
  You cannot have more active consumers than partitions.
```

The reason for the "one partition, one consumer" rule is ordering. If two consumers could read the same partition simultaneously, each would see some subset of messages. Consumer A processes offset 50 while Consumer B processes offset 51. Consumer B finishes first and commits offset 51. Now offset 50's processing is in-flight in Consumer A, but the committed offset says "51 done." If Consumer A crashes, offset 50 is lost. The only way to maintain ordered processing per partition is to assign each partition to exactly one consumer.

**The hard ceiling on parallelism: you can never have more active consumers in a group than you have partitions.** This is why partition count is a critical upfront design decision. If you start with 10 partitions and later need to scale to 20 consumer instances, you are stuck at 10 active consumers. You would need to increase partition count (painful) or rethink your design.

### Multiple consumer groups: full independence

Here is where Kafka's log model shines versus a queue model. Multiple consumer groups read the ENTIRE topic independently. Group A's reads do not affect Group B's reads. Each group maintains its own committed offsets.

```
One Topic — Multiple Independent Consumer Groups
================================================

  Topic: "ride-events" (Uber)
  +------+------+------+------+
  | P0   | P1   | P2   | P3   |
  | 0..N | 0..N | 0..N | 0..N |
  +------+------+------+------+
       |          |
       |          +-------------------------------+
       |                                          |
       v                                          v
  Group: "fare-calculation"          Group: "safety-monitoring"
  offset: P0@5000, P1@4900,          offset: P0@4000, P1@3800,
          P2@5100, P3@5050                   P2@4200, P3@3900
  (nearly real-time, low lag)        (slightly behind, higher lag)
       |
       v
  Group: "data-lake-ingestion"
  offset: P0@1000, P1@900,
          P2@1100, P3@950
  (hours behind, bulk loading)

  All three groups read the same events.
  None of them affects the others.
  Adding "fraud-detection" as Group 4: zero impact on others.
```

This is exactly how Uber's data platform works. A single "ride-events" topic feeds: fare-calculation (low-latency, near-real-time), driver analytics (moderate latency, batch), safety monitoring (real-time), data lake (high-latency, bulk). Each is its own consumer group. The teams owning each group deploy and scale independently.

### Offset management: where did I leave off?

Every consumer group tracks its progress — its committed offset per partition — in Kafka's internal **`__consumer_offsets`** topic. This is a normal Kafka topic with 50 partitions by default, used internally by Kafka to store `{group_id, topic, partition} -> committed_offset` mappings.

When a consumer commits an offset, it is writing to `__consumer_offsets`. When a consumer restarts (after a crash or deployment), it reads from `__consumer_offsets` to find out where it left off, then resumes from there.

Two commit modes:

**Auto-commit** (default, `enable.auto.commit=true`): Kafka automatically commits the last polled offset every `auto.commit.interval.ms` (default 5000ms = 5 seconds). Simple to use, but creates a risk window:

```
Auto-commit risk window:
  t=0:    consumer polls, gets offsets 100-200
  t=0.1:  consumer starts processing offset 100
  t=2.5:  auto-commit fires, commits offset 200 (last polled)
  t=3.0:  consumer crashes while processing offset 150
  t=3.1:  consumer restarts, reads committed offset = 200
           -> Offsets 150-200 are SKIPPED (data loss!)
```

**Manual commit** (`enable.auto.commit=false`): Consumer calls `consumer.commitSync()` or `consumer.commitAsync()` explicitly after processing. You commit only after your business logic has successfully processed the messages.

```python
# Manual commit pattern — at-least-once delivery
while True:
    records = consumer.poll(timeout_ms=1000)
    for record in records:
        process(record)          # your business logic
    consumer.commitSync()        # commit only after processing all records
```

With manual commit: if the consumer crashes after processing but before committing, those messages are reprocessed on restart. This is **at-least-once delivery** — you might process a message more than once, but you never lose one.

`auto.offset.reset` controls behavior when a consumer group has no committed offset at all (first time running, or offsets expired):

- `earliest`: start from the oldest available message in the topic. Used for initial backfill or data migration.
- `latest` (default): start from now — skip all historical messages, only process new ones. Used for real-time consumers that only care about current state.
- `none`: throw an exception. Used when you want to ensure explicitly configured starting points.

---

## 5. Partition Rebalancing: The Pause That Hurts

### What is a rebalance and why does it happen?

A **rebalance** is the process by which Kafka redistributes partition assignments across the consumers in a group. It happens when the group's membership changes.

Triggers:

1. A new consumer instance joins the group (scale-out event, new pod starts)
2. A consumer leaves the group (scale-in, graceful shutdown via `consumer.close()`)
3. A consumer crashes or stops sending heartbeats within `session.timeout.ms`
4. A consumer fails to call `poll()` within `max.poll.interval.ms` (processing took too long)
5. The number of partitions in the topic changes
6. The group coordinator broker changes (rare, due to broker failure)

The **group coordinator** is a specific broker responsible for managing a consumer group's membership and offset commits. Every consumer group is assigned a coordinator (based on hash of group ID). The coordinator tracks which consumers are alive (via heartbeats) and orchestrates rebalances.

### Eager rebalancing: the stop-the-world pause

**Eager rebalancing** (default in older Kafka versions, still common) works like this:

1. Rebalance is triggered (e.g., new consumer joins)
2. Group coordinator sends `REBALANCE_IN_PROGRESS` to all consumers
3. ALL consumers immediately stop processing and revoke ALL their partition assignments
4. ALL consumers send a `JoinGroup` request to the coordinator
5. Coordinator computes new assignments (using the partition assignment strategy)
6. Coordinator sends new assignments to all consumers
7. ALL consumers receive their new assignments and resume processing

The critical problem: step 3. ALL consumers stop processing ALL partitions simultaneously. Zero messages are processed across the entire consumer group for the duration of the rebalance — typically 10–60 seconds depending on cluster size and coordinator load.

```
Eager Rebalance Timeline — Stop-the-World
==========================================

                    Rebalance triggered
                         |
                         v
  Consumer A: [processing]---X----[idle]--[idle]--[new assign]---[processing]
  Consumer B: [processing]---X----[idle]--[idle]--[new assign]---[processing]
  Consumer C: [processing]---X----[idle]--[idle]--[new assign]---[processing]
                              ^                                ^
                              |                                |
                          STOP ALL                         RESUME ALL
                         (revoking)                      (new assignments)

  Gap = "stop-the-world" duration
  During gap: ZERO messages processed by any consumer
  Lag grows during this window
```

The scale problem: imagine a microservice with 100 consumer instances (common at Netflix scale). Rolling deployments restart pods one at a time. Each restart: pod shuts down → rebalance → 30-second pause → new pod starts → rebalance again → another 30-second pause. 100 pods × 2 rebalances × 30 seconds = 100 minutes of cumulative pause. Your consumer group is essentially non-functional during a rolling deployment.

### Cooperative (incremental) rebalancing: Kafka 2.4+

**Cooperative rebalancing** (also called incremental rebalancing) fixes this by only revoking and reassigning the partitions that actually need to move. Consumers that keep the same partitions across the rebalance never stop processing.

How it works in two phases:

**Phase 1:** Coordinator tells each consumer which partitions are being revoked (because they need to be assigned elsewhere). Consumers revoke ONLY those partitions and send a new `JoinGroup`. Consumers that keep all their partitions continue processing without interruption.

**Phase 2:** Coordinator assigns the revoked partitions to the appropriate consumers. Only the consumers receiving new partitions must briefly pause to start consuming from the new partition.

```
Cooperative Rebalance — Only Affected Partitions Pause
=======================================================

  Before: C1 has P0,P1,P2. C2 has P3,P4,P5.
  Event:  C3 joins. Needs partitions P2 and P5.

  Phase 1: Revoke P2 from C1, revoke P5 from C2
  Consumer A: [P0,P1,P2 processing]--[P0,P1 only]--[P0,P1 processing]
  Consumer B: [P3,P4,P5 processing]--[P3,P4 only]--[P3,P4 processing]
  Consumer C: [idle]-----------------------------[joining]

  Phase 2: Assign P2 and P5 to C3
  Consumer C: [joining]--[P2,P5 processing]

  C1 and C2 never fully stop. Only P2 and P5 experience a brief pause.
  The rest of the group keeps processing throughout.
```

Enable cooperative rebalancing in your consumer configuration:

```properties
partition.assignment.strategy=org.apache.kafka.clients.consumer.CooperativeStickyAssignor
```

The **StickyAssignor** (an older variant) tries to minimize partition movement during rebalances — it keeps existing assignments where possible and only moves the minimum set. The **CooperativeStickyAssignor** adds incremental behavior on top.

Spotify adopted cooperative rebalancing in 2021 and reported rebalance-related processing gaps dropping from 45 seconds to under 3 seconds during rolling deployments of their recommendation pipeline consumers.

### Static group membership: surviving pod restarts without rebalance

Kubernetes restarts pods frequently — out-of-memory kills, liveness probe failures, rolling deployments. By default, each restart creates a new consumer identity (Kafka sees a brand-new consumer joining and the old one leaving). That triggers two rebalances.

**Static group membership** (`group.instance.id`) gives a consumer a stable identity that persists across restarts.

```properties
group.instance.id=recommendation-consumer-pod-7
```

When a consumer with a static instance ID disconnects and reconnects within `session.timeout.ms` (default 10 seconds), Kafka treats it as the same consumer returning — no rebalance triggered. The partition assignments are immediately restored to that consumer.

If the consumer does not reconnect within `session.timeout.ms`, Kafka treats it as truly dead and triggers a rebalance.

Use case: stateful consumers that maintain local state (like Kafka Streams with RocksDB local state stores). A rebalance would force a state migration or rebuild. Static membership avoids this on ordinary pod restarts.

### The session timeout and heartbeat triangle

Three configs control how Kafka detects dead consumers:

```
Consumer Liveness Config Triangle
==========================================

session.timeout.ms (default: 10,000ms = 10 seconds)
  -> If group coordinator receives no heartbeat from consumer
     within this window: consumer is declared dead, rebalance triggered.

heartbeat.interval.ms (default: 3,000ms = 3 seconds)
  -> How often consumer sends heartbeat to group coordinator.
  -> Rule of thumb: heartbeat.interval.ms = session.timeout.ms / 3

max.poll.interval.ms (default: 300,000ms = 5 minutes)
  -> Maximum time between poll() calls.
  -> If consumer does not call poll() within this window,
     Kafka assumes it is stuck (processing too slow) and kicks it out.
  -> Different from session.timeout.ms: session timeout = heartbeat missing.
     max.poll.interval.ms = poll() missing (consumer might be alive but stuck).
```

The **deadly trap** that kills production Kafka consumers at least once per engineering team's lifetime:

```
The max.poll.interval.ms Trap
==========================================

  Consumer polls, gets 500 records.
  Each record triggers a slow database lookup: 2 seconds each.
  500 records x 2 seconds = 1000 seconds of processing.

  max.poll.interval.ms default = 300 seconds (5 minutes).
  After 300 seconds without a poll(): consumer is kicked out.
  Rebalance triggered.
  Same 500 records assigned to another consumer.
  That consumer also takes 1000 seconds.
  Infinite rebalance loop. No progress ever made.

  Fix Option 1: Reduce max.poll.records
    max.poll.records=10  -> only 10 records per poll()
    10 x 2 seconds = 20 seconds, well within 5 minutes

  Fix Option 2: Increase max.poll.interval.ms
    max.poll.interval.ms=1800000  -> 30 minutes
    1000 seconds < 30 minutes, consumer survives
    Risk: genuinely stuck consumers take 30 minutes to detect.

  Fix Option 3: Async processing
    Poll records, immediately hand off to a thread pool.
    Thread pool processes slowly; main thread polls again immediately.
    Requires careful offset management (only commit when fully processed).
```

### Follower reads: an emerging pattern (Kafka 2.4+ rack-aware replicas)

By default, consumers always read from the leader replica. This simplifies consistency — the leader always has the latest data, so consumers always see the freshest view. But it concentrates all read traffic on the leader broker, even though followers have copies of the same data sitting idle on nearby machines.

Kafka 2.4 introduced **follower reads** (also called rack-aware consumers or replica fetching from preferred replicas). If a consumer is co-located in the same availability zone (AZ) as a follower replica, it can be configured to read from that follower instead of the leader, which may be in a different AZ.

Why does this matter?

At large scale (Netflix, Confluent Cloud deployments), cross-AZ data transfer has a real cost — AWS charges $0.01/GB for cross-AZ egress. A topic with 100 MB/sec of consumer reads, with consumers in us-east-1a reading from a leader in us-east-1b, generates 8.64 TB/day of cross-AZ traffic. At $0.01/GB, that is $86/day from one topic. Multiply by 500 topics and it becomes material.

With follower reads and rack-aware assignment, the consumer in us-east-1a reads from the follower in us-east-1a. Same data, zero cross-AZ network cost.

The trade-off: followers can be slightly behind the leader (within `replica.lag.time.max.ms`). Consumer reads from a follower may be up to 30 seconds stale by default. For most use cases (analytics, monitoring, data lake ingestion), this is acceptable. For use cases requiring the very latest data (real-time fraud signals, live inventory), stick with leader reads.

Enable with:
```properties
# On the consumer
client.rack=us-east-1a

# On the broker
replica.selector.class=org.apache.kafka.common.replica.RackAwareReplicaSelector
```

### Choosing the right number of partitions: the L6 decision framework

One of the most common L6 interview questions is: "How many partitions would you use for this topic?" There is no single correct answer, but there is a principled reasoning process. Here is how to think through it.

**Step 1: Calculate the minimum partitions needed for producer throughput.**

If your producers collectively write 500 MB/sec to a topic, and each broker can handle roughly 100 MB/sec of writes to a single partition (disk I/O + replication), you need at least 5 partitions spread across 5+ brokers.

In practice: `min_partitions_for_producers = total_producer_MB_per_sec / MB_per_sec_per_partition`

**Step 2: Calculate the minimum partitions needed for consumer throughput.**

If your consumer group needs to process 500 MB/sec and each consumer instance can process 50 MB/sec, you need at least 10 consumers active, which means at least 10 partitions.

`min_partitions_for_consumers = total_throughput / per_consumer_throughput`

**Step 3: Take the maximum of steps 1 and 2.**

`min_partitions = max(producer_partitions, consumer_partitions)`

**Step 4: Add headroom and practical considerations.**

- Add 20-50% headroom for traffic spikes
- Round up to a "nice" number for even distribution across brokers (multiples of broker count work well: 3 brokers × 4 partitions each = 12 total)
- Consider that more partitions increase end-to-end latency slightly (more buffering), increase memory usage (each partition uses ~few KB per broker per consumer), and slow down leader election (more partitions to reassign per broker failure)
- The practical upper bound without careful tuning: 200 partitions per broker, 4,000 partitions per cluster (for smooth Zookeeper-based operations). KRaft raises these limits significantly.

**Step 5: Decide if you need key-based ordering, and if so, how many distinct keys you have.**

If you have 1,000 distinct order IDs and you set partition count to 100, each partition handles ~10 orders. That is fine. If you have 5 distinct user tiers (bronze/silver/gold/platinum/enterprise) and set 100 partitions, you have a skew problem — all "gold" tier orders hash to the same 1-2 partitions, creating a hot spot.

```
Partition Count Decision — Example
=============================================

  Scenario: Stripe payment event pipeline
  - Producer throughput: 200 MB/sec peak
  - Each broker handles 80 MB/sec write per partition (with replication)
  - Minimum partitions for producers: 200/80 = 2.5 -> 3 partitions

  - Consumer throughput needed: 200 MB/sec
  - Each consumer processes 20 MB/sec
  - Minimum partitions for consumers: 200/20 = 10 partitions

  - Take max: max(3, 10) = 10 partitions
  - Add 50% headroom: 15 partitions
  - Round to multiple of 3 brokers: 15 (already a multiple of 3)
  - Final choice: 15 partitions

  Key concern: payment_id keys -> ~1M distinct IDs
  1M distinct keys across 15 partitions -> ~66,000 per partition (fine, no skew)

  Answer at interview:
  "15 partitions, driven by consumer throughput needing 10 active consumers,
   with headroom. Key = payment_id for per-payment ordering."
```

**The cost of getting it wrong:** partitions are hard to change after launch. Increasing partition count requires moving data and breaks key-based routing (your old messages for a key live in partition X; new messages go to partition Y after the repartition). Most teams choose a partition count 2-3× their current need to buy time. Uber, for example, started their ride-events topic at 32 partitions when they needed 8, knowing they would grow into it within a year.

### The poll loop: how a consumer actually works

Understanding the poll loop is essential for writing correct Kafka consumers. The poll loop is not just how you fetch messages — `poll()` does double duty.

`consumer.poll(timeout_ms)` does two things simultaneously:
1. Fetches messages from the broker for all assigned partitions
2. Sends a heartbeat to the group coordinator, proving the consumer is alive

If you are not calling `poll()`, you are not sending heartbeats. After `session.timeout.ms` without a heartbeat, the group coordinator declares you dead.

```python
# Correct Kafka consumer poll loop pattern
consumer = KafkaConsumer(
    'order-events',
    group_id='order-processor',
    bootstrap_servers=['kafka1:9092'],
    enable_auto_commit=False,       # manual commit for at-least-once
    max_poll_records=50,            # small batch to stay within max.poll.interval
    max_poll_interval_ms=300000     # 5 minutes
)

while True:
    # poll() fetches messages AND sends heartbeat
    records = consumer.poll(timeout_ms=1000)

    if not records:
        continue   # no messages, loop again (heartbeat still sent)

    for partition, messages in records.items():
        for message in messages:
            process(message)   # your business logic here

    # Commit after ALL records in this batch are processed
    # At-least-once: if crash before commit, records reprocessed on restart
    consumer.commit_sync()
```

The most common production mistake: putting slow work inside the poll loop without keeping the loop itself fast.

```python
# WRONG: long blocking work inside poll loop
while True:
    records = consumer.poll(timeout_ms=1000)
    for record in records:
        result = slow_http_call(record)   # 30 seconds per call
        write_to_database(result)         # 5 seconds per call
    consumer.commit_sync()
    # After 10 records: 350 seconds have passed.
    # max.poll.interval.ms=300000 = 300 seconds.
    # Consumer is kicked out after record 9. Infinite rebalance loop.

# RIGHT: hand off slow work to a thread pool
executor = ThreadPoolExecutor(max_workers=20)
futures = []

while True:
    records = consumer.poll(timeout_ms=1000)   # fast, keeps heartbeat alive
    for record in records:
        future = executor.submit(process_record, record)
        futures.append((record.offset(), future))

    # Drain completed futures and commit
    completed = [(off, f) for off, f in futures if f.done()]
    if completed:
        max_committed_offset = max(off for off, _ in completed)
        consumer.commit(offsets={...max_committed_offset...})
        futures = [(off, f) for off, f in futures if not f.done()]
```

The poll loop seems simple — it is a `while True` with a `poll()` call. But getting it right (managing heartbeats, commits, and slow processing simultaneously) is one of the hardest parts of building a production Kafka consumer.

One more nuance: `commitSync()` blocks until the broker confirms the offset commit. `commitAsync()` does not block — it sends the commit and immediately returns. `commitAsync` is faster but if the commit fails, it is silently dropped (Kafka retries internally, but not always successfully before the next commit supersedes it). For most production workloads: use `commitAsync` during normal processing for speed, and `commitSync` in the shutdown hook to guarantee a final clean commit before the process exits. This combination gives you throughput in the common case and safety on the boundary case.

---

## Summary: What You Now Know

At this point in Chapter 34, you have covered the mechanical foundation of Kafka:

**The Append-Only Log:**
- Kafka stores data as append-only, ordered logs — not as removable queues
- Sequential writes make Kafka fast (400× faster than random writes on spinning disks)
- Offsets give each message a stable, addressable position in the log forever (within retention)
- Topics name logs; partitions parallelize them

**Disk Layout:**
- Partitions are stored as numbered segment files (`.log`, `.index`, `.timeindex`) in a directory per partition
- The active segment receives all new writes; closed segments are eligible for retention and compaction
- The `.index` file is a sparse offset-to-byte index enabling O(log N) message lookup by offset

**Brokers, Leaders, ISR:**
- Brokers are servers; each holds some partitions
- Every partition has one leader (handles reads/writes) and followers (replicate data)
- ISR is the set of caught-up replicas; `acks=all` requires all ISR to confirm writes
- `min.insync.replicas` prevents writes when too few replicas are healthy
- KRaft replaced Zookeeper, reducing leader election time from 30+ seconds to under 1 second

**Consumer Groups:**
- Groups share partition work: N partitions, at most N active consumers per group
- Multiple groups read the same topic fully independently
- Offsets are committed to `__consumer_offsets`; manual commit gives at-least-once delivery
- `auto.offset.reset` controls first-run behavior (earliest vs latest)

**Partition Count:**
- Minimum partitions = max(producer throughput / partition throughput, consumer throughput / per-consumer throughput)
- Add 2-3× headroom; round to a multiple of broker count for balanced leader distribution
- Changing partition count post-launch breaks key-based routing — plan carefully upfront

**Rebalancing:**
- Eager rebalancing stops all consumers — dangerous at scale
- Cooperative rebalancing (Kafka 2.4+) pauses only affected partitions
- Static group membership (`group.instance.id`) eliminates rebalances on pod restarts
- The `max.poll.interval.ms` trap is the most common production consumer failure mode

### Quick reference: key Kafka configuration parameters covered in Part A

| Config | Default | What it controls | When to tune |
|--------|---------|------------------|--------------|
| `acks` | 1 | How many replicas must confirm a write | Set to `all` for critical data |
| `replication.factor` | 1 | Number of partition copies | Use 3 for production |
| `min.insync.replicas` | 1 | Min ISR for writes to succeed | Set to 2 with RF=3 for safety |
| `replica.lag.time.max.ms` | 30000 | Lag before follower removed from ISR | Lower if faster failover needed |
| `linger.ms` | 0 | Wait time to accumulate batches | Set 5-20ms for throughput |
| `batch.size` | 16384 | Max producer batch size in bytes | Increase for throughput |
| `enable.auto.commit` | true | Whether consumer commits automatically | Set false for at-least-once |
| `auto.commit.interval.ms` | 5000 | Auto-commit frequency | Reduce to limit re-delivery window |
| `auto.offset.reset` | latest | What to do with no committed offset | Set `earliest` for replay/backfill |
| `max.poll.records` | 500 | Max messages per poll() call | Reduce if processing is slow |
| `max.poll.interval.ms` | 300000 | Max gap between poll() calls | Increase for slow processors |
| `session.timeout.ms` | 10000 | Heartbeat deadline before consumer declared dead | Increase for GC-heavy consumers |
| `heartbeat.interval.ms` | 3000 | Heartbeat frequency | Keep at ~1/3 of session.timeout |
| `group.instance.id` | none | Static consumer identity | Set for stable-infra consumers |
| `partition.assignment.strategy` | RangeAssignor | How partitions are distributed | Set to CooperativeStickyAssignor |

**Part B of this chapter** will cover retention (time-based, size-based, log compaction) and exactly-once delivery (idempotent producers, transactions, and what EOS actually means mechanically).

---

**Coming up in Part B:** how Kafka decides what old data to throw away (retention policies), how log compaction keeps only the latest value per key, and the full mechanical story of exactly-once semantics — what idempotent producers actually prevent at the broker level, what transactions add on top, and why EOS is harder than it sounds when you cross the consumer-to-producer boundary.

---

*Part A complete — continues in Ch34_PartB.md*
# Chapter 34: Kafka Internals — Ordering, Partitions, Storage, and Producers
## Part B: The Mechanics That Drive L6 Answers

---

## Section 1: Ordering — The Full, Honest Truth

### The Analogy First: A Library With Many Shelves

Imagine a library where every book gets a number stamped on its spine when it arrives. Shelf A has books numbered 1 through 500 in order. Shelf B has books numbered 1 through 300 in order. But there is absolutely no rule about which shelf got its books first. Book #1 on Shelf A might have arrived at the library before or after Book #1 on Shelf B. Nobody tracked that cross-shelf order.

Kafka is that library. Each partition is a shelf. Each message gets an **offset** — a number stamped on it in the order it arrived on that partition. Within one partition, order is guaranteed. Across partitions, there is no ordering guarantee at all.

This is the most common mistake candidates make in system design interviews. They say "Kafka guarantees ordering" and the interviewer nods slowly, then asks a follow-up that exposes the misunderstanding. The precise, L6 answer is: **Kafka guarantees strict ordering within a partition. Across partitions, there is no ordering guarantee.**

---

### The Exact Guarantee: Within a Partition

When a producer writes message A, then message B, to the same partition, the broker assigns:

```
Message A --> offset 100
Message B --> offset 101
```

A consumer reading that partition will always read offset 100 before offset 101. No exceptions. The broker will never serve them out of order. This is enforced by the append-only log structure of the partition.

```
Partition 0 (order-events topic):

+--------+--------+--------+--------+--------+
| off:97 | off:98 | off:99 |off:100 |off:101 |
|  msg A |  msg B |  msg C |  msg D |  msg E |
+--------+--------+--------+--------+--------+
  <--- older                           newer --->

Consumer reads left to right. Always.
```

This is strict. The consumer cannot jump ahead. The consumer cannot get offset 101 before 100. The only way to get out-of-order messages from a single partition is if YOUR application reorders them after reading — which is your bug, not Kafka's.

---

### The Cross-Partition Reality

Now look at two partitions side by side:

```
Partition 0:                       Partition 1:

+--------+--------+--------+       +--------+--------+--------+
| off:0  | off:1  | off:2  |       | off:0  | off:1  | off:2  |
| user:A | user:C | user:A |       | user:B | user:B | user:D |
+--------+--------+--------+       +--------+--------+--------+

Written at: 9:00am  9:01am  9:03am  Written at: 9:00:30am 9:02am 9:04am
```

Partition 0 offset 2 (user:A, 9:03am) was written AFTER Partition 1 offset 1 (user:B, 9:02am). But Kafka has no mechanism to tell you that. From Kafka's perspective, both partitions are independent logs. If Consumer Group X reads both, one consumer thread gets Partition 0 and another gets Partition 1. They race. You might process Partition 1 offset 2 before Partition 0 offset 1. There is no coordination.

**This is not a bug. It is a deliberate design choice that enables horizontal scalability.**

---

### Why Total Ordering Is Impossible at Scale

Think about a single-file grocery checkout line. Everyone goes in exactly the order they arrived. But at a busy supermarket with 500 customers per hour, a single line is a disaster. So stores open 10 lanes. Now 10 customers are being processed simultaneously. But the order across lanes is undefined — lane 3 might finish before lane 1 even if lane 1's customer arrived first.

Kafka makes the same tradeoff:

```
OPTION A: 1 partition, strict global order

Producer --> [Partition 0] --> 1 Consumer
             offset 1,2,3,4
             
Throughput: limited to what ONE consumer can handle.
At 1 million messages/sec: consumer falls behind, lag grows, system fails.

OPTION B: 12 partitions, order within partition only

Producer --> [Partition 0]  --> Consumer A
         --> [Partition 1]  --> Consumer B
         --> [Partition 2]  --> Consumer C
         --> ...
         --> [Partition 11] --> Consumer L

Throughput: 12x parallelism. 12 consumers run simultaneously.
Trade-off: no ordering guarantee ACROSS partitions.
```

The L6 answer when an interviewer asks "how do you handle ordering in Kafka?" is not "use one partition." The L6 answer is: **"What entities need to be ordered relative to each other?"**

Orders for User 123 need to be ordered. The sequence (order created → payment processed → order shipped → delivered) must be in order for User 123. But User 123's order events and User 456's order events do not need to be ordered relative to each other. They are completely independent.

The solution: **partition key = user_id.** All events for User 123 always hash to the same partition. Within that partition they are ordered. User 456 hashes to a different partition and runs in parallel.

```
key="user:123" --> hash --> Partition 4
                            [created][paid][shipped][delivered]  <-- in order

key="user:456" --> hash --> Partition 7
                            [created][paid][shipped]             <-- in order

Partition 4 and Partition 7 run independently. Total system throughput = 12x.
```

---

## Section 2: Partition Keys — The Design Decision That Matters Most

### How Kafka Assigns Messages to Partitions

When a producer sends a message, Kafka needs to decide which partition gets it. The rule is simple:

**With a key:**
```
partition = MurmurHash2(key) % num_partitions
```

MurmurHash2 is a fast, non-cryptographic hash function. Given the same key, it always produces the same hash. So the same key always maps to the same partition. Deterministic. Stable. Predictable.

**Without a key (null):**

In Kafka 2.4 and later, **sticky partitioning** is used. Messages accumulate in a single partition's batch until the batch is full or a time limit is reached, then Kafka switches to the next partition. This distributes messages evenly over time without the overhead of hashing.

**With a custom partitioner:**

You implement the `Partitioner` interface and write your own routing logic. Useful for unusual cases like "all messages with priority=HIGH go to partitions 0-3, all others go to 4-11."

---

### Choosing the Right Partition Key: The Mental Model

The key should answer one question: **which entity's events must be ordered relative to each other?**

| Service | Good Key | Why |
|---|---|---|
| Order service | `order_id` | All events for one order (created, paid, shipped) must be in order |
| User profile | `user_id` | All profile changes for one user must be in order |
| IoT sensors | `device_id` | Readings from device 42 must be ordered |
| Payment processing | `payment_id` | Payment state machine events must be sequential |
| Ad click stream | `ad_campaign_id` | Clicks for same campaign analyzed together |

---

### What NOT to Use as a Partition Key

**Constant value (e.g., "US", "global", "default"):**
```
key = "US"
MurmurHash2("US") % 12 = 3  (always)

Result: ALL messages go to Partition 3.
Partitions 0,1,2,4,5,...,11: empty, idle.
Partition 3: overwhelmed.
You have paid for 12 partitions. You are using 1.
```

**Null (when ordering matters):**
```
Messages without a key go to different partitions via sticky partitioning.
Event A for order:789 --> Partition 2
Event B for order:789 --> Partition 7  (after batch switch)

Order:789's events are now in different partitions.
No ordering for any single entity.
```

**Timestamp:**
```
key = System.currentTimeMillis()  // new value every millisecond

Every message gets a unique key --> different partition.
No entity's events ever land on the same partition.
Ordering for any entity: zero guarantee.
Also: your partition assignment changes every millisecond --> chaos.
```

---

### Hot Partitions: The Painful Production Problem

**The Analogy:** Imagine 4 checkout lanes at a grocery store. A celebrity walks in. Every fan in the store immediately lines up behind the celebrity. Lane 2 has 200 people. Lanes 1, 3, 4 have 2 people each. The store is serving people as slowly as it would with 1 lane.

In Kafka: if one key generates a disproportionate amount of traffic, the partition that key hashes to becomes a **hot partition**.

```
NORMAL TRAFFIC:

Partition 0: [====]         ~25% of traffic
Partition 1: [====]         ~25% of traffic
Partition 2: [====]         ~25% of traffic
Partition 3: [====]         ~25% of traffic

HOT PARTITION (key=user_id=123 generates 50% of writes):

Partition 0: [====================]  50% of traffic  <-- HOT
Partition 1: [=====]                 17% of traffic
Partition 2: [=====]                 17% of traffic
Partition 3: [=====]                 16% of traffic

Consumer for Partition 0: overwhelmed, falling behind.
Consumers for Partitions 1-3: mostly idle.
```

**Real company example:** Stripe encountered this during internal load testing. Their test account — used by hundreds of internal engineers simultaneously — generated roughly 70% of all API call events during peak testing periods. Every event from the test account had the same `account_id` key. That account's partition absorbed 70% of writes. The consumer for that partition couldn't keep up and built lag while other consumers sat nearly idle.

**How to diagnose:** Check per-partition message rates using `kafka-consumer-groups.sh` or your monitoring tool (Datadog, Grafana). If one partition's message rate is 10x the others, you have a hot partition.

---

### Solutions for Hot Partitions

**Solution 1: Key Salting**

Add a random suffix to the key to spread it across multiple partitions:

```python
# Instead of:
key = f"user:{user_id}"

# Use:
suffix = random.choice(["a", "b", "c", "d"])
key = f"user:{user_id}:{suffix}"
```

```
user:123:a --> Partition 2
user:123:b --> Partition 5
user:123:c --> Partition 9
user:123:d --> Partition 1

Traffic for user:123 now spread across 4 partitions.
```

**Trade-off:** Per-user ordering is broken. Events for user:123 may now be in 4 different partitions in different orders. Fix: consumer collects all events for user:123 within a time window (say, 30 seconds), sorts them by timestamp, then processes them. More complex consumer code but solves the hot partition.

**Solution 2: Composite Key**

Spread by a secondary dimension:

```python
key = f"user:{user_id}:event_type:{event_type}"
# e.g., "user:123:event_type:login"
#        "user:123:event_type:purchase"
#        "user:123:event_type:logout"
```

All "login" events for user 123 are ordered. All "purchase" events for user 123 are ordered. But login and purchase events for user 123 may interleave. Partial ordering. Often enough.

**Solution 3: Dedicated Topic for Hot Entities**

```
Regular users  --> topic: user-events (12 partitions)
VIP / hot users --> topic: vip-user-events (dedicated, more consumers)
```

Netflix does a version of this for high-profile content launches. The streaming events for a major new release drop go to a dedicated high-throughput pipeline rather than the general content events topic.

**Solution 4: More Partitions**

If the hot partition has 50% of traffic in a 12-partition topic, increasing to 120 partitions means the hot partition still gets 50% — but 50% of a much smaller share. The remaining 119 partitions absorb the rest. Less pressure per partition, though the root cause is unaddressed.

---

### Sticky Partitioning Deep Dive (No Key)

Before Kafka 2.4, messages without a key used round-robin assignment: message 1 → partition 0, message 2 → partition 1, message 3 → partition 2, etc.

**The problem with round-robin:**
```
1000 messages/sec, 10 partitions, each message sent immediately:
--> 100 batches/sec per partition
--> Each batch contains ~1 message
--> Tiny batches = poor compression ratio
--> High network overhead
```

**Sticky partitioning (Kafka 2.4+):**
```
Producer accumulates messages until batch is full (16KB by default)
OR until linger.ms expires (5ms by default).

Then switches to next partition.

Result: fewer, larger batches.
--> Better compression (similar messages compress together)
--> Fewer network round trips
--> Higher throughput
```

**The config that controls this:**
```properties
# How long to wait for batch to fill before sending
linger.ms=5

# Maximum batch size before sending immediately
batch.size=16384
```

If latency matters more than throughput: `linger.ms=0`. Send immediately. Batch size may be 1 message. High overhead but lowest latency.

If throughput matters more: `linger.ms=50`. Wait up to 50ms. Batches of hundreds of messages. Much better compression. Higher latency.

---

## Section 3: On-Disk Storage — Segment Files

### The Analogy: A Ledger Cut Into Chapters

Imagine a massive ledger book recording every transaction at a bank. The ledger is too big to store in one physical book, so it's cut into chapters of 1,000 pages each. Each chapter is labeled with the page number it starts on: "Chapter starting at page 1," "Chapter starting at page 1001," "Chapter starting at page 2001," and so on.

When the bank needs to find transaction #1,847, they look at the chapter labels, find "Chapter starting at 1001" (since 1847 > 1001 but 1847 < 2001), and open that chapter. Then they flip to page 1847 directly. Fast lookup without scanning every page.

Kafka's **segment files** are exactly that system.

---

### How Kafka Stores Data on Disk

Each partition gets its own directory:

```
/kafka/data/
    order-events-0/      <-- Partition 0 of topic "order-events"
    order-events-1/      <-- Partition 1 of topic "order-events"
    order-events-2/      <-- Partition 2 of topic "order-events"
    user-activity-0/     <-- Partition 0 of topic "user-activity"
    ...
```

Inside each partition directory, data is stored in **segment files**. A segment is a fixed-size chunk of the partition log. Each segment has three associated files:

```
/kafka/data/order-events-0/
    |
    +-- 00000000000000000000.log        <-- messages at offsets 0-99
    +-- 00000000000000000000.index      <-- offset index for fast seek
    +-- 00000000000000000000.timeindex  <-- timestamp index
    |
    +-- 00000000000000000100.log        <-- messages at offsets 100-199
    +-- 00000000000000000100.index
    +-- 00000000000000000100.timeindex
    |
    +-- 00000000000000000200.log        <-- messages at offsets 200-? (ACTIVE)
    +-- 00000000000000000200.index
    +-- 00000000000000000200.timeindex
    
    ^-- File name = first offset in that segment.
    ^-- The .log with the HIGHEST number is the ACTIVE segment (receiving writes).
```

**The `.log` file:** raw message data, stored as a sequence of binary records. Append-only. Messages are written to the end and never moved.

**The `.index` file:** a **sparse offset index**. Not every offset is in here — just one entry every N bytes. Each entry maps: `(offset) --> (byte position in .log file)`. This enables fast lookup without scanning the entire .log file.

**The `.timeindex` file:** a **sparse timestamp index**. Maps `(timestamp) --> (offset)`. Used when consumers say "give me messages from the last hour." Kafka looks up the timestamp, finds the closest offset, and starts reading from there.

---

### How a Lookup Works: Step by Step

A consumer asks: "give me messages starting at offset 150."

```
Step 1: Which segment file contains offset 150?

Segment files: 00000.log (offsets 0-99)
               00100.log (offsets 100-199)   <-- 150 is here
               00200.log (offsets 200+)

Binary search over segment file names: found 00100.log.

Step 2: Open 00100.index. Binary search for offset 150.
        Find entry: offset 150 --> byte 4,832 in 00100.log

Step 3: Seek to byte 4,832 in 00100.log. Start reading messages.

Total cost: O(log N) binary search + O(1) disk seek. No full scan.
```

This is why Kafka can handle billions of messages with sub-millisecond read latency. It never scans. It always seeks.

---

### Segment Rotation

The **active segment** is the one currently receiving writes. All others are closed (immutable).

When does a segment rotate (close and become immutable, new active segment opens)?

```
Trigger 1: Segment exceeds size limit
  Config: segment.bytes=1073741824  (1 GB, the default)
  When .log file reaches 1 GB: rotate.

Trigger 2: Segment exceeds age limit
  Config: segment.ms=604800000  (7 days, the default)
  When segment has been open for 7 days: rotate, even if not full.
```

```
Timeline of segment rotation:

Day 1, 9am: Segment 00000.log opens (offset 0). Active.
Day 8, 9am: 7 days old. Rotate.
             00000.log: CLOSED, immutable.
             00012847.log: opens (offset 12,847). Active.

OR:

Day 1, 9am:  Segment 00000.log opens. Active.
Day 1, 1pm:  Segment reaches 1 GB.
              00000.log: CLOSED.
              00087234.log: opens. Active.
```

Only closed segments are eligible for deletion (time/size-based retention) or compaction. The active segment is never touched by retention or compaction while it is active.

---

### Sequential Writes: Why Kafka Is So Fast

Kafka's secret to extreme write throughput is that it only writes to the END of the active segment. This is called a **sequential write** — the disk head moves in one direction only, always appending.

```
SEQUENTIAL WRITE (Kafka's pattern):
Disk head at position 1,000.
Write message --> position 1,000 to 1,080. Done.
Write message --> position 1,080 to 1,160. Done.
Write message --> position 1,160 to 1,240. Done.

Disk head never backtracks. Each write is adjacent to the last.
Speed on spinning HDD: ~200 MB/sec


RANDOM WRITE (database's pattern):
Write to position 1,000 (Row 5, updated).
Seek to position 847,293 (Row 11, new index entry).
Seek to position 2,104,847 (Row 5 in secondary index).
Seek to position 500 (Row 5, write-ahead log).

Disk head moves all over the platter.
Speed on spinning HDD: ~0.5 MB/sec

Kafka is 400x faster on spinning disk than random-write databases.
```

This is why at LinkedIn (where Kafka was created), brokers use 12-drive RAID-0 HDD configurations. 12 drives × 200 MB/sec sequential write = 2.4 GB/sec per broker. Kafka can fully saturate every drive simultaneously because all writes are sequential.

**SSD vs HDD for Kafka:**
- Writes: HDD is sufficient (sequential write speed is already fast)
- Reads: SSD helps when consumers are far behind (catching up requires reading old segments that are not in page cache)
- Most production deployments use HDDs with very large page caches (64-128 GB RAM). Hot data stays in memory. Disk is the backstop.

---

## Section 4: Retention Policies — How Long Data Lives

### Time-Based Retention: The Default

**The Analogy:** Imagine a newspaper archive room. Papers older than 7 days get thrown out. But here's the catch — they throw out entire boxes of papers at once, not individual papers. If a box has papers from 6 days ago AND 8 days ago mixed together, the whole box goes in the trash. A few 6-day-old papers get thrown out a little early.

Kafka retention works exactly this way — **deletion is per segment, not per message.**

```properties
# Keep messages for 7 days (default)
retention.ms=604800000
```

```
Segment A: messages from Day 1 to Day 6 (written to as it filled up)
Segment B: messages from Day 6 to Day 8 (crossed the 7-day boundary)

At Day 8:
  Segment A: all messages older than 7 days. DELETE entire segment.
  Segment B: some messages < 7 days old. KEEP (even the older ones).

Result: some messages in Segment B are 7+ days old but survive.
Retention is APPROXIMATE, not exact.
```

**Disk space planning formula:**
```
disk_needed = write_rate_MB_per_sec x retention_seconds x replication_factor

Example: Uber's trip events
  Write rate: 50 MB/sec
  Retention: 7 days = 604,800 seconds
  Replication factor: 3

  50 x 604,800 x 3 = 90,720,000 MB = ~90 TB cluster storage
```

This is how you size Kafka clusters in interviews. Write rate, retention, replication factor. Three numbers, one formula.

---

### Size-Based Retention

```properties
# Delete oldest segments when partition exceeds 100 GB
retention.bytes=107374182400
```

Useful when write rate varies unpredictably. With time-based retention, a spike in write rate can cause disk to fill up before the retention window expires. Size-based retention caps the disk usage.

**Combining both policies:**
```properties
retention.ms=604800000      # 7 days
retention.bytes=107374182400 # 100 GB per partition
```

Whichever limit triggers first causes deletion. This is the safe production pattern: cap both time and size.

---

### Compaction: Keeping Only the Latest Value Per Key

**The Analogy:** Imagine a whiteboard where you keep track of everyone's current score in a game. You erase the old score and write the new one each time someone's score changes. At the end, the whiteboard has only each person's CURRENT score. You don't keep a history of every intermediate score.

Time-based retention is like erasing the whole whiteboard every week. **Log compaction** is like erasing only old scores for each person, keeping only the most recent one — forever.

```properties
cleanup.policy=compact
```

**Use cases:**
- User profile service: keep the current profile, not every edit
- Database CDC (Change Data Capture): keep the current state of each database row
- Kafka Streams state stores: key-value state that must survive broker restarts

---

### How Compaction Works Mechanically

The **log cleaner** is a background thread pool on the broker. It periodically scans closed segments looking for duplicate keys.

```
BEFORE compaction:

Segment 1 (closed):
  +------------------+------------------+------------------+
  | key:user:1       | key:user:2       | key:user:1       |
  | val:"Alice"      | val:"Bob"        | val:"Alice Smith" |
  | offset:0         | offset:1         | offset:2          |
  +------------------+------------------+------------------+

Segment 2 (closed):
  +------------------+------------------+
  | key:user:3       | key:user:1       |
  | val:"Charlie"    | val:"A. Smith"   |
  | offset:3         | offset:4         |
  +------------------+------------------+

Segment 3 (ACTIVE - not touched):
  +------------------+
  | key:user:2       |
  | val:"Robert"     |
  | offset:5         |
  +------------------+

AFTER compaction (Segments 1 and 2 cleaned):

Cleaned segment:
  +------------------+------------------+------------------+
  | key:user:2       | key:user:3       | key:user:1       |
  | val:"Bob"        | val:"Charlie"    | val:"A. Smith"   |
  | offset:1         | offset:3         | offset:4          |
  +------------------+------------------+------------------+

Older entries for user:1 (offsets 0 and 2) are GONE.
Latest value for each key is preserved.
Offsets are maintained (gaps are allowed in compacted topics).
```

**Important:** Compaction is not instant. The log cleaner runs in the background on a schedule. Between the time a new value arrives and the time the cleaner runs, old values for the same key may persist for hours. This is **compaction lag**.

---

### Tombstone Messages: Deleting Keys From Compacted Topics

What if you want a key to completely disappear from the topic? In a compacted topic, publishing a new value just replaces the old value — the key stays. To DELETE a key, you publish a **tombstone message**: a message with the key but `value=null`.

```python
# Publish a tombstone for user:123
producer.send("user-profiles", key="user:123", value=None)
```

```
Timeline:

t=0:  user:123 --> "Alice Smith"  (latest value, key exists in topic)

t=1:  Tombstone: user:123 --> null  (DELETION signal)

      Log cleaner sees tombstone.
      Marks user:123 for deletion.
      Tombstone retained for delete.retention.ms (default: 24 hours).
      This gives lagging consumers time to see the delete.

t=25h: delete.retention.ms elapsed.
       Tombstone removed.
       user:123 is GONE from the compacted topic entirely.
```

**Real-world use case:** GDPR "right to be forgotten." A user requests data deletion. You publish a tombstone for their `user_id` key in your compacted user-profiles topic. After the tombstone retention period, their data is gone from Kafka. All downstream consumers that received the tombstone can also delete their local copy.

---

### Combined Policy: Compact + Delete

```properties
cleanup.policy=compact,delete
```

Both policies apply:
- Compaction removes old versions of each key (keeps latest)
- Time/size retention removes even the latest version if it's old enough

Use case: a changelog topic where you need the current state of each entity, but you also don't want to store data indefinitely. Example: real-time inventory. Keep the current stock count per SKU (compaction). But if a SKU hasn't had any updates in 90 days, delete it entirely (retention).

---

### Compaction Lag: The Operational Reality

After you write a new message for key X, the old message for key X does not disappear immediately. The log cleaner runs in the background on a schedule. Old messages may persist for hours.

**Monitoring compaction health:**
```
Metric: kafka.log:type=LogCleanerManager,name=max-dirty-percent

"Dirty" = ratio of log that has not yet been cleaned.
If max-dirty-percent is consistently high (>50%), the log cleaner is falling behind.
```

**Fixing compaction lag:**
```properties
# Default: 1 log cleaner thread per broker
log.cleaner.threads=4   # Increase to 4

# Lower the threshold at which cleaning starts
log.cleaner.min.dirty.ratio=0.3  # Clean sooner (default: 0.5)
```

---

### Segment File Lifecycle

```
                     ROTATION
                   (size or age)
                        |
                        v
 +----------+      +----------+      +------------------+      +---------+
 |  ACTIVE  | ---> |  CLOSED  | ---> | CLEANED/COMPACTED| ---> | DELETED |
 | segment  |      | segment  |      | segment          |      |         |
 +----------+      +----------+      +------------------+      +---------+
                        |                                            ^
                        |                   retention.ms            |
                        +--------------------------------------------+
                                   (if cleanup.policy=delete)
                             OR
                        compaction + then eventually retention
                                   (if cleanup.policy=compact,delete)
```

The active segment never goes directly to deletion. It must first rotate to closed, then be subject to the configured policy.

---

## Section 5: Partition Count — The Math That Matters

### Why Partition Count Is a Real Design Decision

The default partition count in many Kafka setups is 1. This is almost always wrong for production workloads.

**Partition count sets the ceiling on parallelism.** You cannot have more consumers actively working in a consumer group than there are partitions. Extra consumers sit idle.

```
6 partitions, 6 consumers in the group:

Partition 0 --> Consumer A  (working)
Partition 1 --> Consumer B  (working)
Partition 2 --> Consumer C  (working)
Partition 3 --> Consumer D  (working)
Partition 4 --> Consumer E  (working)
Partition 5 --> Consumer F  (working)

All consumers busy. Maximum throughput.

6 partitions, 10 consumers in the group:

Partition 0 --> Consumer A  (working)
Partition 1 --> Consumer B  (working)
Partition 2 --> Consumer C  (working)
Partition 3 --> Consumer D  (working)
Partition 4 --> Consumer E  (working)
Partition 5 --> Consumer F  (working)
              Consumer G  (IDLE - no partition)
              Consumer H  (IDLE - no partition)
              Consumer I  (IDLE - no partition)
              Consumer J  (IDLE - no partition)

You are paying for 10 consumers. 4 are doing nothing.
Partition count is the bottleneck, not your consumer fleet.
```

---

### How to Calculate Partition Count

**Method 1: Consumer-driven calculation**

```
Variables:
  T_total  = total topic write rate (MB/sec)
  T_consumer = throughput one consumer instance can process (MB/sec)

Partitions = ceil(T_total / T_consumer)

Example: Shopify order events
  T_total = 500 MB/sec (peak Black Friday)
  T_consumer = 50 MB/sec per consumer instance
               (includes deserialization, enrichment, database write)

  Partitions = 500 / 50 = 10 minimum

  Add 50% headroom: 15 partitions
  Round to clean number: 16 partitions
```

**Method 2: Headroom-driven calculation**

```
Variables:
  Max_consumers = maximum number of consumer instances you'll ever run

Partitions = Max_consumers x 2   (2x headroom for future growth)

Example: you plan to run at most 20 consumer instances
  Partitions = 20 x 2 = 40 partitions
```

In practice, use both methods and take the larger result.

---

### The Cost of Too Many Partitions

More partitions are not free. Every partition has overhead:

**Memory on the broker:**
Each partition requires the broker to track: current offset, ISR (in-sync replicas), leader epoch, replication state. 10,000 partitions = 10,000 × that overhead. Can exhaust broker heap.

**Leader election time:**
When a broker fails, the Kafka controller must elect a new leader for every partition that broker was leading. If one broker had 1,000 partitions as leader, 1,000 elections must happen. Each takes ~5ms. Total: ~5 seconds of unavailability for those partitions.

```
Broker failure recovery time:
  100 partitions per broker:   100 x 5ms = 0.5 seconds downtime
  1,000 partitions per broker: 1,000 x 5ms = 5 seconds downtime
  10,000 partitions per broker: 10,000 x 5ms = 50 seconds downtime
```

**File handles:**
Each partition has at least 3 open files (.log, .index, .timeindex for the active segment). Operating systems have a file handle limit (`ulimit -n`).

```
10,000 partitions x 3 files = 30,000 open file handles
Default Linux ulimit: 1,024  <-- crash
Need to configure: ulimit -n 100000
```

**Rebalance duration:**
More partitions = more assignments = longer rebalances when consumers join/leave. For topics with 10,000 partitions and 50 consumers, a rebalance can take 30+ seconds during which no consumer is processing.

**LinkedIn's production guidelines:**
- No more than 4,000 partitions per broker
- No more than 200,000 partitions per cluster

---

### Adding Partitions: The Painful Truth

```bash
# Increasing from 10 to 20 partitions
kafka-topics.sh --alter --topic order-events --partitions 20
```

This works. But it has a critical gotcha:

**Existing data is NOT redistributed.** The 10 original partitions still have their data. The 10 new partitions start empty. Data distribution is now uneven until new writes fill the new partitions.

More dangerously: **key routing changes.**

```
Before (10 partitions):
  key="user:456" --> MurmurHash2("user:456") % 10 = 3

After (20 partitions):
  key="user:456" --> MurmurHash2("user:456") % 20 = 13

Messages for user:456 written BEFORE the change: in Partition 3.
Messages for user:456 written AFTER the change: in Partition 13.

User:456's events are now split across two partitions.
Within each partition they are in order.
But Partition 3 messages and Partition 13 messages are independent.
You have broken the ordering guarantee for user:456.
```

**Best practice:** Set partition count generously at topic creation. If you expect to need 20 partitions, start with 30. Increasing partitions later is disruptive, cannot be undone without migrating data, and breaks ordering guarantees.

---

## Section 6: Producer Batching and Compression

### Why Producers Batch Messages

**The Analogy:** Imagine a mail carrier who delivers one letter at a time, driving across town for each one. 1,000 letters = 1,000 car trips. Now imagine sorting the letters by neighborhood and delivering a full bag to each neighborhood in one trip. 1,000 letters = 10 car trips. Same letters, 100× fewer trips.

Kafka producers batch messages for exactly this reason.

```
WITHOUT batching:

1,000 messages/sec
= 1,000 network round trips/sec
= 1,000 x 2ms round trip = 2,000ms of network time per second
= Network is the bottleneck.

WITH batching (batch.size=16KB, linger.ms=5):

1,000 messages/sec --> accumulate into batches --> ~10 batches/sec
= 10 network round trips/sec
= 10 x 2ms = 20ms of network time per second
= 100x improvement. Throughput constrained by disk, not network.
```

**The two knobs that control batching:**

```properties
# Accumulate up to 16 KB before sending
batch.size=16384

# Wait up to 5ms even if batch isn't full
linger.ms=5
```

The producer sends when EITHER condition is met: batch is full OR `linger.ms` expires.

```
Timeline with linger.ms=5:

t=0ms:    Message 1 arrives. Batch starts.
t=1ms:    Message 2 arrives. Added to batch.
t=2ms:    Message 3 arrives. Added to batch.
t=5ms:    linger.ms expires. Send batch of 3 messages.
          OR
t=0ms:    Message 1 arrives. Batch starts.
t=0.1ms:  Message 2 arrives.
...
t=0.8ms:  Message 200 arrives. Batch reaches 16KB.
          Send batch immediately. Don't wait for linger.ms.
```

**Latency vs throughput tradeoff:**

| `linger.ms` | Latency | Throughput | Use case |
|---|---|---|---|
| 0 | Lowest | Low (many small batches) | Real-time alerting |
| 5 | Low | Good | General purpose |
| 50 | Medium | High | High-volume analytics |
| 100+ | High | Maximum | Bulk data pipeline |

---

### Compression: Making Batches Smaller

**Why batching and compression go together:**

Messages in a batch are often structurally similar — same JSON keys, same field names, similar values. Compression exploits this repetition. The bigger the batch, the more repetition, the better the compression ratio.

```
Batch of 1 JSON message:
{"user_id": 123, "event": "purchase", "amount": 49.99, "ts": 1718323200}
Size: 72 bytes. After gzip: 68 bytes. Ratio: 1.06x (almost no savings).

Batch of 1,000 similar JSON messages:
All have same keys. Many share values. Patterns repeat.
Size: 72,000 bytes. After gzip: ~14,400 bytes. Ratio: 5x savings.
```

**Compression codecs compared:**

| Codec | CPU cost | Compression ratio | Decompression speed | Best for |
|---|---|---|---|---|
| none | Zero | 1.0x | N/A | Already compressed data |
| Snappy | Low | 2-3x | Very fast | Low-latency, CPU-sensitive |
| LZ4 | Very low | 2-3x | Fastest | Default good choice |
| gzip | High | 4-6x | Moderate | Storage-sensitive pipelines |
| zstd | Medium | 4-5x | Fast | Best overall balance |

**Real numbers from LinkedIn:**

LinkedIn reported 4-5× compression ratio for JSON events using gzip. Their Kafka cluster at the time handled 1 TB of data per day in raw form. After compression: 200-250 GB per day. That compression saves ~250 TB of storage per year across the cluster.

**Producer config:**
```properties
compression.type=lz4
```

Compression is applied per batch by the producer. The compressed batch travels over the network. The broker stores the compressed batch as-is on disk (no decompress-then-recompress). The consumer receives the compressed batch and decompresses it. This means compression savings apply at all three points: network, disk, and memory.

---

### Zero-Copy: The Silent Throughput Multiplier

When a consumer asks for messages that are already in the broker's page cache (the OS's memory-mapped buffer of recently-read disk files), Kafka can use a Unix system call called `sendfile()` to send those bytes directly from the kernel buffer to the network socket.

**Without zero-copy (normal path):**
```
Disk --> kernel page cache --> user space (Kafka broker process) -->
kernel socket buffer --> network

Data is COPIED 4 times. CPU is involved at each copy.
```

**With zero-copy (`sendfile()`):**
```
Disk --> kernel page cache --> network

Data is COPIED 2 times. CPU barely involved.
Kafka broker code is NOT in the data path.
```

This is why Kafka can serve consumer reads at near-disk-bandwidth speeds without significant CPU usage. The broker acts as a pass-through. For a broker receiving 1 GB/sec of writes and serving 5 GB/sec of reads (5 consumer groups reading the same data), the broker's CPU usage stays low because consumer reads use zero-copy.

**The prerequisite:** Kafka's on-disk format and network format are identical. The broker does not need to transform data before sending it to consumers. If they were different formats, zero-copy would be impossible — you'd need to deserialize and re-serialize, which requires a CPU-involved copy.

---

### How Message Format Ties It All Together

Each message stored on disk contains:

```
+----------+--------+-----------+-----------+-------+-------+
| offset   | size   | timestamp | leader    | CRC32 | key   |
| (int64)  | (int32)| (int64)   | epoch     | check | value |
|          |        |           | (int32)   | sum   | bytes |
+----------+--------+-----------+-----------+-------+-------+
```

Messages are stored in BATCH format on disk — the same binary format as the network protocol batch. This is the key design choice that makes zero-copy possible: the bytes on disk are exactly the bytes that go over the wire.

```
Producer creates batch:
  [header][msg1][msg2][msg3] (compressed if configured)
  
Broker receives batch, writes it to .log file as-is.

Consumer requests messages:
  Broker reads batch bytes from page cache.
  Sends bytes directly to consumer via sendfile().
  Consumer receives exact bytes, decompresses, processes.

Zero transformation at the broker. Zero extra CPU copies.
```

---

## Quick Reference: The Numbers You Need in an Interview

| Parameter | Default | What it controls | When to change |
|---|---|---|---|
| `num.partitions` | 1 | Default partition count for new topics | Set to match target parallelism |
| `retention.ms` | 604800000 (7d) | How long messages survive | Increase for replay capability |
| `retention.bytes` | -1 (unlimited) | Max partition size | Set to cap disk usage |
| `segment.bytes` | 1073741824 (1GB) | When to rotate segments | Rarely changed |
| `linger.ms` | 0 | Batch wait time | Set 5-50ms for throughput |
| `batch.size` | 16384 (16KB) | Max batch size | Increase for high-throughput |
| `compression.type` | none | Compression codec | Use lz4 or zstd |
| `log.cleaner.threads` | 1 | Compaction threads | Increase if compaction lags |
| `delete.retention.ms` | 86400000 (24h) | Tombstone lifetime | Keep at default |

---

## The L6 Mental Model: Putting It All Together

When designing a Kafka-backed system, these are the questions you answer in order:

```
1. What is the partition key?
   --> What entity needs ordering? (user_id, order_id, device_id)
   --> Is that key distributed enough? (avoid hot partitions)

2. How many partitions?
   --> Write rate / consumer throughput = minimum partitions
   --> Add 50-100% headroom
   --> Set at topic creation; adding later is painful

3. What is the retention policy?
   --> How long do consumers need to replay? (outage recovery window)
   --> How much disk do you have?
   --> Is it a changelog topic? (use compaction)

4. How do producers send data?
   --> linger.ms and batch.size tradeoff: latency vs throughput
   --> Use lz4 or zstd compression
   --> acks=all for durability (more on this in Part C)

5. What ordering does your consumer logic assume?
   --> Within-partition order: guaranteed. Design around it.
   --> Cross-partition order: undefined. Either don't need it
       (partition by entity) or handle it in the consumer
       (sort within time window).
```

This is the mental model that separates an L4 answer ("Kafka guarantees ordering") from an L6 answer ("Kafka guarantees ordering within a partition; I'm partitioning by order_id to ensure all events for a given order are sequentially processed by one consumer, while enabling full parallelism across orders").

---

*Next: Part C covers Replication, ISR, Acknowledgment Levels, and Exactly-Once Semantics — the durability and consistency mechanics.*
# Chapter 34, Part C: Kafka Internals — Exactly-Once Semantics, Alternatives, Consumer Deep Dive, and Operations

---

## Section 1: Exactly-Once Semantics — What It Actually Means

### The Three Delivery Guarantees: A Quick But Deep Recap

Before you can understand exactly-once, you need to feel the pain of the two
simpler alternatives. Most engineers know the names. Staff-level engineers know
exactly which line of code causes the problem in each case.

**At-most-once delivery** means: commit the offset before processing the
message. Think of it like reading a letter and then immediately feeding it into a
shredder — before you have even decided what to do about it. If your application
crashes during processing, the message is gone. The broker thinks you consumed
it (you committed the offset), but your application never finished the work. You
never lose a message twice. You can lose a message exactly once. Hence the name:
at most one delivery, never more, sometimes zero.

Code flow that causes at-most-once:

```
1. Consumer polls offset 42 from broker.
2. Consumer commits offset 43 to broker ("I have read offset 42").
3. Consumer crashes.
4. Consumer restarts at offset 43.
5. The work for offset 42 was NEVER done. Gone forever.
```

**At-least-once delivery** flips the order. Commit the offset AFTER processing.
If your application crashes after finishing the work but before it gets to commit
the offset, the broker still shows the old offset. On restart, the consumer reads
the same message again and processes it a second time. You never lose a message.
You might process it twice. At least one delivery, sometimes two.

Code flow that causes at-least-once duplication:

```
1. Consumer polls offset 42 from broker.
2. Consumer processes offset 42 (writes result to database).
3. Consumer crashes BEFORE committing offset 43.
4. Consumer restarts at offset 42 (old offset still in broker).
5. Consumer processes offset 42 AGAIN. Database write happens twice.
```

**Exactly-once delivery** is the guarantee that every message is processed
exactly one time — no loss, no duplicates. This is the hardest guarantee to
provide. Kafka achieves it within its own system through two mechanisms:
**idempotent producers** and **transactional producers**. Understanding both is
a staff-level requirement.

---

### Idempotent Producer: Deduplication at the Partition Level

Here is the problem that idempotent producers solve.

A producer at Netflix sends a "video-watch-event" to Kafka. The message travels
over the network, reaches the broker, gets written to the partition log. The
broker is about to send an acknowledgment (ACK) back to the producer. At that
exact moment, a tiny network hiccup drops the ACK packet. The producer never
receives the ACK. From the producer's perspective, the message might not have
made it. The producer's retry logic kicks in and sends the same message again.
Now the broker has the message TWICE.

Without idempotence, the partition log has a duplicate. Every downstream consumer
reading that partition will see the same watch event twice, inflating your metrics,
possibly charging the user twice, breaking your analytics pipelines.

With `enable.idempotence=true`, this is the mechanism that prevents it:

**Step 1**: When the producer first connects to a broker, the broker assigns it a
unique identifier called the **ProducerID (PID)**. This PID is stable for the
lifetime of that producer session.

**Step 2**: Every message the producer sends carries a **sequence number**. The
sequence number starts at 0 for each partition and increments by 1 for every
message sent to that partition.

**Step 3**: The broker tracks the last successfully written sequence number for
every (PID, partition) pair. When a message arrives, the broker checks: "Is this
sequence number exactly one more than the last sequence I recorded for this PID
and partition?" If yes, write it and advance the sequence. If the sequence number
is equal to or less than what is already recorded, this is a duplicate — discard
it and send an ACK back to the producer as if it succeeded.

Here is what that looks like:

```
+------------------+          message (PID=5, Seq=42)          +--------------+
|                  | ----------------------------------------> |              |
|  Producer        |                                           |  Broker      |
|  (PID=5)         |          ACK drops on network             |  (writes it) |
|                  | <----- x x x x x x x x x x x x x x ---- |              |
|  "No ACK,        |                                           |  Seq tracker:|
|   retrying..."   |                                           |  PID=5, P0=42|
|                  |                                           |              |
|                  |   retry: message (PID=5, Seq=42)          |              |
|                  | ----------------------------------------> |              |
|                  |                                           | "Seq 42 from |
|                  |          ACK (success)                    |  PID 5 already|
|                  | <---------------------------------------- |  exists. Drop.|
+------------------+                                           | Send ACK."   |
                                                               +--------------+
```

The producer does not need to change its retry logic. It just retries normally.
The broker silently deduplicates. The partition log stays clean.

One important constraint: idempotent producer guarantees exactly-once delivery
**within a single partition** and **within the lifetime of a single producer
session**. If the producer restarts and gets a new PID, the sequence counter
resets. The duplicate protection only covers retries within the same session.
For cross-session and cross-partition guarantees, you need transactions.

---

### Transactional Producer: Atomic Multi-Partition Writes

Idempotent producers solve the retry duplicate problem for a single partition.
But real systems need something bigger. Consider this real-world scenario at a
company like Stripe.

A payment processor reads from the "payment-requests" Kafka topic. For each
request it processes, it needs to write two things: a result record to the
"payment-results" topic and an audit record to the "audit-log" topic. If the
processor crashes after writing to "payment-results" but before writing to
"audit-log", you have an inconsistent state. The payment was recorded but the
audit trail is incomplete. Your compliance team is not happy. Your regulators
are less happy.

Kafka **transactions** solve this. They allow a producer to write to multiple
partitions and multiple topics atomically. Either ALL writes succeed as a visible,
committed batch, or ALL writes are rolled back and consumers never see them.

Configuration: set `transactional.id` to a stable, unique string that identifies
this logical producer. This is the key that ties together all the atomic writes.

```python
producer = KafkaProducer(
    bootstrap_servers='kafka:9092',
    transactional_id='payment-processor-1',  # unique per logical instance
    enable_idempotence=True                   # transactions require idempotence
)

producer.init_transactions()

while True:
    records = consumer.poll(timeout_ms=1000)

    producer.begin_transaction()

    try:
        for record in records:
            result = process_payment(record)
            producer.send('payment-results', value=result)
            producer.send('audit-log', value=audit_entry(record, result))

        # Atomic: commit the consumer offset AS PART OF the transaction.
        # The offset commit and the produces all commit together.
        producer.send_offsets_to_transaction(
            consumer_offsets,
            consumer_group_id='payment-processor-group'
        )

        producer.commit_transaction()   # all writes visible atomically

    except Exception as e:
        producer.abort_transaction()    # all writes disappear
```

The key player is the **Transaction Coordinator**, a special role played by one
of the Kafka brokers. Every producer with a `transactional.id` has a designated
coordinator (chosen by hashing the `transactional.id` to a partition of the
internal `__transaction_state` topic).

```
                        +-------------------------+
                        |  Transaction Coordinator |
                        |  (broker that owns       |
                        |   __transaction_state    |
                        |   partition for this ID) |
                        +----------+--------------+
                                   |
           +----------------------+|+-----------------------+
           |                      ||                        |
           v                      v|                        v
  +----------------+   COMMIT marker written    +------------------+
  |  Partition:    |   to EACH partition        |  Partition:      |
  |  payment-      | <------------------------  |  audit-log-0     |
  |  results-0     |                            |                  |
  +----------------+                            +------------------+
           |                                             |
           v                                             v
  +-----------------------------------------------------------+
  |  Consumer with isolation.level=read_committed             |
  |  Waits for COMMIT marker before making records visible.   |
  |  Aborted transactions? Never seen. Invisible.             |
  +-----------------------------------------------------------+
```

**Consumers and isolation level** — this is where the consumer side of
transactions matters. A consumer can be configured with
`isolation.level=read_committed`. This setting makes the consumer ONLY read
messages that belong to committed transactions. If a producer started a
transaction, wrote some messages, and then aborted the transaction — a
`read_committed` consumer will never see those messages. They are invisible.

Without `isolation.level=read_committed` (the default is `read_uncommitted`),
consumers see all messages including ones from aborted transactions. For payment
systems, you almost always want `read_committed`.

The happy path and failure path:

```
HAPPY PATH:
Producer                   Coordinator                    Consumers
   |                           |                              |
   |-- beginTransaction() ---> |                              |
   |                           |                              |
   |-- send(payment-results) --|-- writes data records        |
   |-- send(audit-log) --------|-- to partitions              |
   |                           |   (not yet visible)          |
   |                           |                              |
   |-- commitTransaction() --> |                              |
   |                           |-- writes COMMIT markers -->  |
   |                           |   to all partitions          |
   |                           |                          records now visible
   |<-- success -------------- |                              |

FAILURE PATH:
Producer                   Coordinator                    Consumers
   |                           |                              |
   |-- beginTransaction() ---> |                              |
   |-- send(payment-results) --|-- writes data records        |
   |   CRASH before committing |                              |
   |                           |                              |
   |   (coordinator times out) |                              |
   |                           |-- writes ABORT markers -->   |
   |                           |   to all partitions          |
   |                           |                         records never visible
```

---

### The Boundary Problem: Exactly-Once Stops at Kafka's Edge

Here is the most important thing to understand for an L6 interview: **Kafka
transactions only guarantee exactly-once within Kafka's own system**. The moment
you step outside Kafka, you are on your own.

The scope of a Kafka transaction covers:
- Producer writing to Kafka partitions
- The Kafka broker storing the records
- The consumer offset commit (via `sendOffsetsToTransaction`)

The scope does NOT cover:
- Writing to PostgreSQL
- Calling an external REST API
- Writing to Redis
- Sending an email
- Updating a MySQL table

Here is the failure case that trips up engineers at every level below staff:

```
1. Consumer reads message from Kafka (inside transaction scope).
2. Consumer writes result to PostgreSQL (OUTSIDE transaction scope).
3. PostgreSQL write succeeds.
4. Consumer tries to commit Kafka offset.
5. Kafka offset commit FAILS (network blip, broker restart, whatever).
6. Consumer retries from the same Kafka offset.
7. Consumer reads the same message again.
8. Consumer writes to PostgreSQL AGAIN.
9. PostgreSQL now has a duplicate row.
```

There is no technical mechanism to atomically commit a Kafka offset and a
PostgreSQL write in the same transaction. They are different systems with
different transaction protocols. The two-generals problem lives here.

**The correct L6 answer**: use **at-least-once delivery with an idempotent
consumer**.

Design the PostgreSQL write so it is safe to execute twice:

```sql
-- Create a unique constraint on your event identifier
CREATE TABLE payment_results (
    event_id  UUID PRIMARY KEY,  -- comes from the Kafka message
    user_id   BIGINT NOT NULL,
    amount    DECIMAL(10, 2) NOT NULL,
    processed_at TIMESTAMP NOT NULL
);

-- In your consumer, do an upsert that ignores duplicates:
INSERT INTO payment_results (event_id, user_id, amount, processed_at)
VALUES ($1, $2, $3, NOW())
ON CONFLICT (event_id) DO NOTHING;  -- second execution is silently ignored
```

Now even if the same Kafka message is delivered twice, the second database write
does nothing. The result is effectively exactly-once from the user's perspective,
even though the delivery mechanism is at-least-once.

The interviewer who asks "how do you achieve exactly-once semantics?" is looking
for exactly this nuance. The naive answer is "enable Kafka transactions." The
staff-level answer is: "Kafka transactions give us exactly-once within Kafka's
boundaries. For external systems, we design idempotent writes using natural
deduplication keys, so at-least-once delivery from Kafka results in effectively
exactly-once outcomes at the database."

---

### Zombie Fencing: Preventing Old Producers from Corrupting New Transactions

There is a dangerous edge case in distributed systems called the **zombie
producer** problem. Kafka's transactions address it through epoch-based fencing.

Scenario: your payment processor `payment-processor-1` is running and producing
to Kafka. A network partition isolates it from the Kafka brokers for longer than
the session timeout. The coordinator declares it dead and allows a new instance
to start.

Now the new instance (call it instance B) registers with `transactional.id=payment-processor-1` and starts processing. Five seconds later, the
network partition heals. The old instance (instance A) is still running. It was
never actually dead — just temporarily disconnected. Now both A and B are running
and both believe they are the legitimate `payment-processor-1`. If both start
producing transactions to the same topics, you have a split-brain corruption
scenario.

**Fencing** works like this: every time a producer registers a `transactional.id`
with the coordinator, the coordinator increments an **epoch** counter for that
ID. When instance B registers, the coordinator bumps the epoch from 0 to 1 and
gives instance B epoch=1. If instance A (which holds epoch=0) tries to send
any transactional message, the coordinator checks: "Is this producer's epoch the
current epoch for this transactional.id?" The answer is no (0 is not equal to 1),
so the coordinator **rejects** the request with a FencedInstanceIdException.
Instance A (the zombie) is permanently fenced out.

```
+------------------------------------------+
|  Transaction Coordinator                  |
|  State:                                   |
|    transactional.id: payment-processor-1  |
|    current epoch:    1  (given to B)       |
+------------------------------------------+
         ^                     ^
         |                     |
   REJECTED                  ACCEPTED
   (epoch=0, stale)          (epoch=1, current)
         |                     |
  +-----------+          +-----------+
  | Instance A |         | Instance B |
  | (zombie)   |         | (active)   |
  | epoch=0    |         | epoch=1    |
  +-----------+          +-----------+
```

The requirement this places on your architecture: `transactional.id` must be
stable per logical producer role (e.g., one ID per partition of work, or one per
shard), and you must ensure only one instance per ID is running at a time (or
accept that the old one will be fenced out automatically).

---

### Performance Impact of Exactly-Once

Exactly-once is not free. Before committing to it, understand the costs:

**Idempotent producer** (`enable.idempotence=true`):
- Overhead: roughly 1% throughput reduction
- Reason: broker must check sequence numbers per (PID, partition) on every write
- Verdict: always enable this. The cost is negligible and the benefit is real.

**Transactional producer** (`transactional.id` set):
- Overhead: 10-30% throughput reduction depending on transaction size and commit
  frequency
- Reason: each transaction requires coordinator round trips (begin, commit),
  writing transaction metadata, and flushing commit markers to each affected
  partition
- Smaller transactions (committing every 1 message) are slower than larger
  transactions (committing every 1,000 messages). Batch your transactions.

**`isolation.level=read_committed` consumer**:
- Overhead: additional read latency equal to the transaction commit time
- Reason: the consumer cannot return records from a partition until it sees the
  COMMIT or ABORT marker for the transaction that produced those records. If the
  transaction coordinator is slow or the producer is slow to commit, consumers
  wait.
- On high-throughput topics with fast commits (~50ms transactions), this latency
  is usually acceptable. On topics where individual transactions take seconds,
  `read_committed` consumers see significant latency spikes.

**Rule of thumb**:
- Financial events (payments, inventory deductions, accounting ledger writes):
  use transactions and `read_committed`. The correctness requirement justifies
  the cost.
- Analytics events, logging, monitoring: use at-least-once. The duplicates are
  acceptable or deduped at query time (e.g., `SELECT DISTINCT` or
  `COUNT(DISTINCT event_id)`).

---

## Section 2: Kafka vs Alternatives — When NOT to Use Kafka

### The Real Ops Cost of Kafka

Running production Kafka yourself requires at minimum:

- **3 Kafka broker nodes** — for replication factor 3 and leader election.
- **ZooKeeper (legacy) or KRaft quorum** — ZooKeeper needs its own 3 nodes (6
  servers total). KRaft (Kafka 3.3+) eliminates ZooKeeper but still needs a 3-node
  quorum.
- **Schema Registry** — separate service with its own HA requirements if using
  Avro or Protobuf.
- **Monitoring infrastructure** — JMX metrics to Prometheus, Grafana dashboards,
  alerts for consumer lag, under-replicated partitions, broker disk, and rebalances.
- **Capacity planning** — disk = write rate x replication factor x retention.
  100 MB/sec with 3x replication and 7-day retention = ~172 TB across the cluster.
- **Kafka upgrades** — rolling procedures, protocol version management, rebalance
  storms. Not a weekend project.

Total: 6-10 servers minimum plus monitoring. A team of 5 engineers building a new
service should seriously evaluate simpler alternatives first. The operational burden
is a real cost that must be weighed against Kafka's benefits.

---

### The Decision Framework: Four Questions

Before recommending Kafka in a system design interview, ask these four questions.
If all answers are no, use something simpler.

**Question 1: Do you need replay?** Can a consumer restart from an older offset?
Is there an audit trail to reprocess? If yes, Kafka's durable log is the answer —
no other major queue system offers this.

**Question 2: Do you have multiple independent consumer groups?** Does the same
event need to trigger billing, notifications, and analytics independently? Kafka
lets each group track its own offset. SQS marks a message consumed — once one
worker takes it, it's gone.

**Question 3: Do you have high throughput?** Over 1,000 messages per second,
sustained? Kafka's sequential disk writes and batch compression handle this
natively. Below that threshold, the ops overhead often outweighs the benefits.

**Question 4: Do you need per-entity ordering?** All events for a user or order
in sequence? Kafka's partition key routes all messages with the same key to the
same partition, consumed in order by a single consumer.

If all four answers are no, a simpler tool is probably better.

---

### Kafka vs AWS SQS

| Dimension            | Kafka                      | SQS Standard          | SQS FIFO                      |
|----------------------|----------------------------|-----------------------|-------------------------------|
| Throughput           | 1M+ msg/sec per cluster    | 3,000 msg/sec         | 300 msg/sec per message group |
| Ordering             | Per partition              | Best-effort           | Per message group (strict)    |
| Replay               | Yes (reset offset)         | No                    | No                            |
| Retention            | Configurable (forever)     | Up to 14 days         | Up to 14 days                 |
| Multiple consumers   | Yes (consumer groups)      | Competing consumers   | Competing consumers           |
| Ops overhead         | High                       | Zero (fully managed)  | Zero (fully managed)          |

When to choose SQS over Kafka:
- Task queue pattern (one worker per job, no replay needed, AWS shop, small team,
  under 10,000 msg/sec). Zero ops overhead is a real advantage.

Real example: Airbnb uses SQS for internal job queues (image resizing,
notification delivery) and Kafka for event streams (booking events, search
events, pricing inputs). Fan-out across analytics, fraud detection, and
recommendations is where Kafka shines; task queues with a single worker type
are where SQS is appropriate.

---

### Kafka vs RabbitMQ

| Dimension       | Kafka                   | RabbitMQ                           |
|-----------------|-------------------------|------------------------------------|
| Model           | Log (pull-based)        | Queue (push-based)                 |
| Throughput      | 100K-1M+ msg/sec        | 20K-100K msg/sec                   |
| Ordering        | Per partition           | Per queue (single consumer)        |
| Replay          | Yes                     | No (consumed = deleted)            |
| Routing         | By partition key        | Complex routing via exchanges      |
| Ops overhead    | High                    | Medium                             |

When to choose RabbitMQ:
- Complex routing via fanout, direct, or topic exchanges — Kafka has no equivalent;
  you would build the routing logic yourself in consumer code.
- Task distribution (RabbitMQ pushes work to idle workers automatically).
- Team already has RabbitMQ expertise; no need for replay.

Real example: Pinterest uses RabbitMQ for internal service-to-service messaging
with complex routing rules, and Kafka for the analytics pipeline and data platform
where throughput and replay are required.

---

### Kafka vs Redis Streams

| Dimension          | Kafka                    | Redis Streams                           |
|--------------------|--------------------------|-----------------------------------------|
| Throughput         | Very high (disk-backed)  | Very high (in-memory)                   |
| Ordering           | Per partition            | Per stream                              |
| Replay             | Yes                      | Yes (consumer groups with offsets)      |
| Persistence        | Disk (durable)           | Memory + AOF (can lose data on restart) |
| Consumer groups    | Yes, scales to hundreds  | Yes, but limited in practice            |
| Ops overhead       | High                     | Low (if already running Redis)          |

When to choose Redis Streams:
- Already running Redis (zero additional ops cost). Sub-millisecond latency needed.
  Small-to-medium volume where short retention is acceptable.

When Kafka beats Redis Streams:
- 10M+ messages/sec sustained (Redis is memory-limited; Kafka scales to disk).
- Long retention (weeks or more) — keeping 30 days in memory is expensive.
- Hundreds of independent consumer groups at scale.

---

### Kafka vs Google Cloud Pub/Sub

| Dimension       | Kafka                          | Google Cloud Pub/Sub             |
|-----------------|--------------------------------|----------------------------------|
| Delivery        | Pull (consumer-driven)         | Push or pull                     |
| Replay          | Yes (by offset, indefinite)    | Limited (7-day "seek" window)    |
| Ordering        | Per partition                  | Per ordering key (opt-in)        |
| Ops overhead    | High (self-managed or Confluent)| Zero (fully managed)            |
| Cost at scale   | Fixed infrastructure cost      | Pay per message (variable)       |

Cost crossover: at ~100M messages/day, self-managed Kafka on cloud VMs often
costs less per message than Pub/Sub. Below that, Pub/Sub's zero ops cost is
usually worth the higher per-message price. GCP shop under 100M/day: start with
Pub/Sub and migrate to Kafka if economics shift.

---

## Section 3: Kafka Consumer Deep Dive — Poll, Commit, Fetch

### The Fetch Request: What Actually Happens Under the Hood

When your consumer calls `consumer.poll()`, it sends a **FetchRequest** to the
leader broker for each assigned partition. Understanding the parameters in that
request explains why consumers sometimes return empty results, block, or return
different batch sizes.

**`fetch.min.bytes`** (default: 1): broker waits until at least this many bytes
are available. Increase to 1 MB on high-throughput topics to reduce round trips.

**`fetch.max.wait.ms`** (default: 500ms): if `fetch.min.bytes` is not reached,
the broker holds the request open this long before returning what it has. Creates
natural batching — consumers collect up to 500ms of data per round trip.

**`max.partition.fetch.bytes`** (default: 1 MB): max data per partition per fetch.
A partition with 10 MB of new messages is returned 1 MB at a time.

**`max.poll.records`** (default: 500): even with 2,000 messages available, `poll()`
returns at most 500. Controls per-cycle processing volume.

The broker-side fetch process:

```
Consumer                          Broker (Partition Leader)
   |                                       |
   |-- FetchRequest(offset=1050,           |
   |       min_bytes=1,                    |
   |       max_wait=500ms,                 |
   |       max_bytes=1MB) --------------> |
   |                                       |
   |                                       |-- Check: any data at offset 1050?
   |                                       |-- Yes: 450KB of messages (offsets
   |                                       |         1050 through 1349)
   |                                       |-- Read segment file: page cache hit
   |                                       |   (zero-copy sendfile to network)
   |                                       |
   |<-- FetchResponse(records[1050..1349], |
   |        high_watermark=1500) --------- |
   |                                       |
```

Note the **high watermark** — the highest offset replicated to all ISR brokers.
Consumers never receive messages beyond this, even if they exist on the leader.
This ensures consumers only read data that will survive a leader failure.

---

### Auto-Commit: The Easy But Dangerous Default

By default: `enable.auto.commit=true`, `auto.commit.interval.ms=5000`. Every 5
seconds Kafka commits the current position regardless of whether processing
finished. The commit is time-based, not completion-based.

The exact failure scenario:

```
Time 0:   Consumer polls offsets 0-499.
Time 0-4: Consumer processes messages 0-249.
Time 5:   AUTO-COMMIT fires. Kafka records offset 500.
Time 5.1: Consumer crashes on message 250.
Time 5.2: Consumer restarts at offset 500.
          Messages 250-499 are SKIPPED PERMANENTLY.
```

Auto-commit with crashes = **at-most-once semantics**. Disable it for anything
where losing data is not acceptable.

---

### Manual Commit Strategies

With `enable.auto.commit=false` you control exactly when offsets are committed.
Two methods:

**`commitSync()`**: blocks until the broker confirms. Safe (no silent failures),
but slower (one round trip per commit).

**`commitAsync()`**: non-blocking, result via callback. Fast, but failures require
careful callback implementation.

Recommended pattern — combine both:

```java
try {
    while (running) {
        ConsumerRecords<String, String> records =
            consumer.poll(Duration.ofMillis(100));

        // Process the records
        for (ConsumerRecord<String, String> record : records) {
            processRecord(record);
        }

        // Fast non-blocking commit in the normal path.
        // If it fails, we'll retry on the next poll cycle because
        // the offset hasn't advanced yet from Kafka's perspective.
        consumer.commitAsync((offsets, exception) -> {
            if (exception != null) {
                log.error("Async commit failed for offsets {}", offsets, exception);
            }
        });
    }
} catch (Exception e) {
    log.error("Consumer error", e);
} finally {
    try {
        // On clean shutdown, make sure the final batch is committed.
        // commitSync blocks here to ensure we don't close before committing.
        consumer.commitSync();
    } finally {
        consumer.close();
    }
}
```

The reasoning: `commitAsync()` is fast in the happy path and does not block your
processing loop. `commitSync()` in the `finally` block ensures that on a clean
shutdown, the last batch is committed before the consumer exits. This minimizes
duplicate processing on restart.

---

### Seeking: Reading from Any Position

One of Kafka's most powerful operational features is the ability to seek to any
offset in any partition at runtime:

```java
consumer.seekToBeginning(consumer.assignment()); // replay from start
consumer.seekToEnd(consumer.assignment());        // skip to latest
consumer.seek(new TopicPartition("payment-events", 3), 100_000L); // specific offset

// Find offset for a timestamp, then seek (time-based replay)
Map<TopicPartition, Long> timestamps = new HashMap<>();
consumer.assignment().forEach(tp -> timestamps.put(tp, targetTimestampMs));
consumer.offsetsForTimes(timestamps)
    .forEach((tp, oat) -> consumer.seek(tp, oat.offset()));
```

Real operational scenarios:

**Incident recovery**: consumer had a bug from 14:00 to 15:00. Fix deployed.
Use `offsetsForTimes` to find 14:00, seek all partitions there, process until
15:00, then resume normally.

**New consumer group startup**: `auto.offset.reset` controls behavior when no
committed offset exists. `earliest` = replay all history. `latest` = skip
history, start from now. Choose based on whether historical events matter to
your service's initialization.

**Spot checking**: seek to a specific offset in a debug session without affecting
the consumer group's committed position.

---

## Section 4: Operational Monitoring — What to Watch

### The Six Metrics Every Kafka Engineer Monitors

**1. Consumer lag per group per partition** (`kafka.consumer_group.lag`):
Difference between log end offset and committed offset. Alert thresholds are
per-group: payment processor at lag > 1,000; analytics pipeline at lag > 100,000.
Alert on lag that is **growing**, not just high — growing lag means the consumer
will never catch up.

**2. Under-replicated partitions** (`kafka.server.replica_manager.under_replicated_partitions`):
Must always be 0. Non-zero means partitions lack the configured ISR count. One
more broker failure could cause permanent data loss. Page immediately. P0 alert.

**3. Offline partitions** (`kafka.server.kafka_controller.offline_partitions_count`):
Must always be 0. An offline partition has no leader — producers and consumers
for that partition fail. Service outage for affected topics. P0 alert.

**4. Broker disk usage**:
Alert at 70% (60% if conservative). Kafka needs headroom for segment writes,
compaction working space, and burst absorption. If disk fills, the broker stops
accepting writes. Alert early enough to expand storage or reduce retention.

**5. Rebalance rate**:
Rebalances are normal on startup. Continuous rebalancing (> 5/minute for a
stable group) means consumers are being evicted — likely exceeding
`max.poll.interval.ms` or hitting `session.timeout.ms`. Alert and investigate.

**6. Producer error rate**:
Spikes in producer errors (timeouts, leader not available) mean messages may
be lost or delayed. Usually signals a broker problem (leader election, disk
issue) or network congestion.

---

### Consumer Lag Monitoring Tools

**Built-in CLI** — quick spot checks:

```bash
kafka-consumer-groups.sh --bootstrap-server kafka:9092 \
  --describe --group payment-processor-group
# GROUP                   TOPIC          PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
# payment-processor-group payment-events 0          1,000,000       1,000,500       500
# payment-processor-group payment-events 1          999,800         1,000,100       300
# payment-processor-group payment-events 2          1,000,200       1,000,200       0
```

**Burrow** (LinkedIn open-source): tracks lag over time and alerts based on
trend (growing vs stable) rather than absolute value — avoids false positives
when a consumer is recovering from a burst.

**Prometheus + JMX Exporter**: exports Kafka JMX metrics to Prometheus. Grafana
dashboards visualize lag, throughput, and broker health. Standard production stack.

**Confluent Control Center** (commercial): web GUI for topics, consumer groups,
schema registry, and alerts. Useful for teams preferring GUI over CLI.

---

### Troubleshooting High Consumer Lag: A Decision Tree

When you see consumer lag alerts firing, follow this diagnostic sequence:

```
+------------------------------------------------------------+
|  Consumer lag alert fired for "payment-processor-group"   |
+------------------------------------------------------------+
                          |
                          v
        +----------------------------------+
        |  Is the lag GROWING or STABLE?   |
        +----------------------------------+
              |                  |
           GROWING             STABLE
              |                  |
              v                  v
   Consumer is slower     Group may be catching up
   than producer.         from an earlier backlog.
   This is a problem.     Monitor for 15 minutes.
              |
              v
   +--------------------------------------------+
   |  Compare consumer count vs partition count  |
   +--------------------------------------------+
          |                |              |
  consumers < partitions  equal      consumers > partitions
          |                |              |
          v                v              v
   Add consumer     Look at per-    Some consumers idle.
   instances.       partition lag.  Reduce consumers OR
   Immediate fix.   (see below)     increase partitions.
                        |
                        v
   +------------------------------------------------+
   |  Is the high lag concentrated in one partition? |
   +------------------------------------------------+
          |                         |
        YES                        NO
          |                         |
          v                         v
   HOT PARTITION              ALL partitions evenly lagging.
   Check partition key.        Consumer processing is too slow.
   Maybe 80% of your          Profile the processing code.
   traffic hashes to P3.       Look for blocking I/O, slow
   Rethink the key.            DB calls, CPU-bound operations.
          |
          v
   +--------------------------------+
   |  Check for poison messages in  |
   |  Dead Letter Queue (DLQ)       |
   +--------------------------------+
          |                 |
    DLQ has entries     DLQ empty
          |
          v
   A bad message is blocking
   one partition. Fix the
   message, remove from DLQ,
   replay through fixed consumer.
```

---

### Key Configuration Reference

**Producer Configuration**:

| Config                    | Default        | Purpose                                                     |
|---------------------------|----------------|-------------------------------------------------------------|
| `acks`                    | `1`            | Durability level. `all` (-1) for strongest guarantee.       |
| `retries`                 | `INT_MAX`      | Retry on transient failures. Default is effectively infinite.|
| `enable.idempotence`      | `true` (3.0+)  | Deduplicate retries. Always enable.                         |
| `compression.type`        | `none`         | `lz4` or `snappy` recommended for throughput.               |
| `batch.size`              | `16384` (16KB) | Max bytes batched before sending. Increase for throughput.   |
| `linger.ms`               | `0`            | Wait this long to fill a batch. 5-20ms for throughput.      |

**Consumer Configuration**:

| Config                    | Default        | Purpose                                                     |
|---------------------------|----------------|-------------------------------------------------------------|
| `enable.auto.commit`      | `true`         | Disable for at-least-once semantics.                        |
| `max.poll.records`        | `500`          | Max records per poll call.                                  |
| `max.poll.interval.ms`    | `300000` (5m)  | Max time between polls before consumer is evicted.          |
| `session.timeout.ms`      | `45000` (45s)  | Heartbeat timeout before consumer is declared dead.         |
| `isolation.level`         | `read_uncommitted`| Set to `read_committed` for transactional topics.        |
| `auto.offset.reset`       | `latest`       | `earliest` to replay all, `latest` to skip history.        |

**Topic Configuration**:

| Config                    | Default        | Purpose                                                     |
|---------------------------|----------------|-------------------------------------------------------------|
| `num.partitions`          | `1`            | Parallelism ceiling. Set based on expected consumer count.  |
| `replication.factor`      | `1`            | Set to 3 for production durability.                         |
| `retention.ms`            | `604800000` (7d)| How long to keep messages.                                 |
| `retention.bytes`         | `-1` (unlimited)| Max bytes per partition before oldest segments deleted.    |
| `cleanup.policy`          | `delete`       | `compact` for changelog topics (keep only latest per key). |
| `compression.type`        | `producer`     | `producer` uses whatever the producer sent.                 |
| `segment.bytes`           | `1073741824` (1GB)| Size of each log segment file.                          |

---

## Section 5: Kafka Streams vs Consumer API vs Connect — When to Use Each

### Consumer API: Raw Access, Full Control

The Kafka Consumer API is the lowest-level option. You write your own poll loop,
manage offsets, and handle partition reassignment. Works in any language with a
Kafka client (Java, Python, Go, Ruby, Rust).

```python
consumer = Consumer({'bootstrap.servers': 'kafka:9092',
                     'group.id': 'my-consumer-group',
                     'enable.auto.commit': False,
                     'auto.offset.reset': 'earliest'})
consumer.subscribe(['payment-events'])
try:
    while True:
        msg = consumer.poll(timeout=1.0)
        if msg is None or msg.error():
            continue
        process(msg)
        consumer.commit(asynchronous=False)
finally:
    consumer.close()
```

Use the Consumer API when: non-JVM language required, simple processing with no
aggregations or stateful joins, full control needed, Kafka Streams overhead
unjustified.

Do not use it when: you need windowed aggregations, stateful joins, or
fault-tolerant local state that survives restarts — use Kafka Streams for those.

---

### Kafka Streams: Stateful Stream Processing in Java

**Kafka Streams** is a Java library (not a separate cluster) running inside your
application. Built on the Consumer API, it adds:

- **State stores**: local RocksDB databases for aggregation results and joins,
  backed to internal changelog topics — survives application restarts.
- **Exactly-once processing**: transactions handled for you by the library.
- **Windowed computations**: tumbling, hopping, and sliding windows.
- **Stream-table joins**: enrich events with data from compacted Kafka topics.

```java
StreamsBuilder builder = new StreamsBuilder();
KStream<String, Purchase> purchases = builder.stream("purchase-events");

purchases
    .groupByKey()
    .windowedBy(TimeWindows.ofSizeWithNoGrace(Duration.ofMinutes(5)))
    .count(Materialized.as("purchase-counts"))
    .toStream()
    .to("purchase-count-output");

new KafkaStreams(builder.build(), config).start();
```

Use Kafka Streams when: aggregations, joins, or windowed computations in Java/Kotlin,
state fits in local RocksDB, library-based approach without a separate cluster.

Do NOT use Kafka Streams when: non-JVM language needed, state too large for local
disk (use Flink), cross-cluster joins required, zero JVM experience on the team.

---

### Kafka Connect: Pre-Built Connectors for Data Movement

**Kafka Connect** is a framework for moving data between Kafka and external systems
without writing any custom code. You configure connectors using JSON, and the
Connect framework handles the rest.

Two types of connectors:

**Source connectors** read from an external system and write to Kafka:
- Debezium PostgreSQL: captures every INSERT/UPDATE/DELETE via logical replication.
  Standard CDC pattern at Coinbase, Shopify, and Segment.
- S3 source: reads S3 files and writes to Kafka.
- REST API source: polls an HTTP endpoint and forwards responses.

**Sink connectors** read from Kafka and write out:
- Elasticsearch sink: indexes events for search and analytics.
- BigQuery sink: streams events into BigQuery tables.
- S3 sink: writes Parquet/JSON/Avro files for a data lake.
- JDBC sink: writes to any JDBC-compatible database.

```json
{
  "name": "postgres-source",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "database.hostname": "postgres",
    "database.port": "5432",
    "database.user": "debezium",
    "database.password": "secret",
    "database.dbname": "production",
    "table.include.list": "public.orders,public.payments",
    "plugin.name": "pgoutput"
  }
}
```

Use Kafka Connect when:
- Building standard integrations (DB to Kafka, Kafka to S3, Kafka to Elasticsearch)
  where a pre-built connector exists. Avoids boilerplate consumer/producer code.
  Essential for CDC (change data capture) from databases.

Do NOT use Kafka Connect when:
- You need complex custom business logic beyond what **Single Message Transforms
  (SMTs)** provide. SMTs handle simple field-level operations (rename, filter,
  cast). They cannot join topics or call external APIs. Use Kafka Streams or the
  Consumer API instead.

---

### ksqlDB: SQL on Kafka Streams

**ksqlDB** provides a SQL interface for stream processing. Instead of Java, you
write queries:

```sql
CREATE STREAM orders (order_id VARCHAR KEY, user_id VARCHAR, amount DOUBLE)
    WITH (kafka_topic='order-events', value_format='JSON');

CREATE TABLE order_counts AS
    SELECT user_id, COUNT(*) AS total_orders
    FROM orders GROUP BY user_id EMIT CHANGES;
```

ksqlDB runs as a separate service, backed by Kafka Streams internally.

Use ksqlDB when: team prefers SQL over Java, simple real-time aggregations for
dashboards or alerting, query logic fits in SQL.

Do NOT use ksqlDB for: complex business logic (conditional branching, external API
calls, multi-step pipelines), or production-critical payment/inventory pipelines
where the Consumer API or Kafka Streams provides more control and a longer track
record.

---

### Side-by-Side: Which Tool for Which Job

```
+--------------------+------------------+-------------+------------------+----------+
|  Task              | Consumer API     | Kafka Streams| Kafka Connect   | ksqlDB   |
+--------------------+------------------+-------------+------------------+----------+
| Simple consumption | Best choice      | Overkill     | Not applicable   | Possible |
| Stateful agg.      | You build it     | Best choice  | Not applicable   | Good     |
| Windowed counts    | You build it     | Best choice  | Not applicable   | Good     |
| DB to Kafka (CDC)  | Not applicable   | Not applicable| Best choice     | No       |
| Kafka to S3        | Possible         | Possible     | Best choice      | No       |
| Non-JVM language   | Best choice      | Not available| Possible (REST)  | No       |
| Quick SQL analytics| Awkward          | Possible     | Not applicable   | Best     |
+--------------------+------------------+-------------+------------------+----------+
```

The mental model: **Connect** for data movement with no custom logic. **Kafka
Streams** for stateful processing in Java. **Consumer API** for everything else,
especially non-Java languages or simple pipelines. **ksqlDB** for quick SQL
analytics when exactness is less critical.

---

## Summary: The Staff-Level Kafka Checklist

When Kafka comes up in an interview, speak to all of these without prompting:

- **Delivery guarantees**: exact code paths for at-most-once vs at-least-once,
  and why exactly-once stops at Kafka's boundary.
- **Idempotent producer**: PID + sequence number + broker deduplication.
  Retries are automatically safe.
- **Transactions**: multi-partition atomic writes, coordinator role, epoch-based
  fencing for zombie producers, `read_committed` consumer isolation.
- **External idempotency**: "at-least-once delivery + ON CONFLICT DO NOTHING" is
  the correct answer for achieving effectively-exactly-once with external DBs.
- **Alternatives**: SQS (task queues, zero ops), RabbitMQ (complex routing),
  Redis Streams (low latency, already on Redis), Pub/Sub (GCP managed service) —
  and under what conditions each beats Kafka.
- **Consumer internals**: fetch parameters, auto-commit danger, manual commit
  strategies, seek and replay.
- **Monitoring**: the six key metrics, lag diagnosis decision tree, and tooling.
- **Processing APIs**: Consumer API vs Kafka Streams vs Connect vs ksqlDB.

Production Kafka systems do not fail because the engineer mistyped
`bootstrap.servers`. They fail because the team did not understand the delivery
guarantee they actually configured, did not plan for consumer lag accumulation,
and did not monitor under-replicated partitions. Operational understanding is what
separates staff-level from senior on Kafka topics.
# Chapter 34: Kafka Internals — Part D
## Production Incidents, L6 Calibration, Brainstorming, Exercises, Quick Reference

---

# 1. Production Incidents

Five real incidents. Short format. What happened, why, how it was fixed.

---

## Incident 1: LinkedIn Hot Partition (2018)

### What Happened

- Topic: "member-events", 48 partitions, partitioned by member_id
- Internal automation system: uses member_id = 0 for all system-generated events
- Partition assignment: hash(0) % 48 = 0
- Partition 0 receives 40% of all traffic
- Consumer assigned to partition 0: CPU-saturated, falling behind
- Partition 0 lag: 2 million messages
- All other 47 partitions: lag = 0
- Time to diagnose: 3 hours
- Root cause of slow diagnosis: team monitored aggregate lag only, not per-partition

### Why It Took 3 Hours

- Aggregate consumer lag = 2M / 47 partitions spread — average looked "medium"
- No per-partition lag dashboard existed
- On-call assumed network or broker issue
- Root cause found only when someone checked kafka-consumer-groups.sh output directly

### Fix

- System events now keyed with: "SYSTEM_" + str(random.choice(range(48)))
- This distributes system traffic uniformly across all 48 partitions
- No consumer code change required — producers changed their key generation

### Prevention

- Alert: any single partition receiving > 3x the average partition throughput
- Dashboard: per-partition message rate, not just aggregate
- Rule: partition keys that are constants, enums, or small integer IDs always need audit

---

## Incident 2: Netflix Retention Misconfiguration (2019)

### What Happened

- Topic: "user-watch-events", configured with retention.ms = 7 days
- Platform engineering team changed retention to 1 day for "cost optimization"
- Change made via Kafka admin API, no change management ticket, no downstream notification
- Analytics team runs weekly batch jobs every Sunday
- Sunday job ran, found only 24 hours of data instead of 7 days
- Job did not fail — it silently processed whatever data was present
- Content licensing decisions made on 85% less data than expected

### Impact

- $3M in content licensing decisions placed on hold pending reanalysis
- Recommendation models retrained on incomplete data
- Incorrect recommendations served to users for approximately 2 weeks
- Data was unrecoverable — not stored anywhere else

### Fix

- Topic configuration changes now require a change management ticket
- Each topic has a documented retention SLA: "analytics-required-minimum"
- CI check added: if new retention.ms < topic_sla_retention_ms, pipeline fails
- Slack notification sent to all consumer team channels on any retention change

### What to Remember

- Kafka does not warn you when data is missing — consumers just process less
- Silent data loss is the worst kind because downstream jobs appear to succeed
- Retention is a contract between producers and consumers, not just a cost knob

---

## Incident 3: Robinhood Rebalance Storm (2020)

### What Happened

- Consumer group: "trade-event-processor"
- 200 consumer instances running on 200 Kubernetes pods
- Topic: 200 partitions (1 consumer per partition, perfectly balanced)
- Kubernetes cluster autoscaler: scaled down to 50 pods at 3 AM (low traffic window)
- 150 pods terminated within 4 minutes
- Each termination triggered a group rebalance
- During each rebalance: all remaining consumers paused for up to 30 seconds
- 150 terminations x 30 second pauses = serial rebalance storm
- Consumer lag: 0 at 2:55 AM, 4 million messages by 9:00 AM
- Markets opened at 9:30 AM: trade confirmation latency = 20 minutes

### Why Rebalances Were So Expensive

- Default EagerRebalance (stop-the-world): all consumers release ALL partitions
- All 50 remaining consumers waited idle while coordinator reassigned everything
- With 200 partitions and 50 consumers, each rebalance took ~25-30 seconds
- 150 serial rebalances = ~4,000 seconds of consumer pause time total

### Fix

- Autoscaler disabled for this consumer group: min replicas = max replicas = 200
- Cooperative rebalancing enabled: only affected partitions reassigned, others keep running
- Static group membership: each pod assigned group.instance.id = pod_name
- Result: pod loss triggers targeted reassignment of only that pod's partitions

### Prevention

- Consumer groups with strict SLAs: disable autoscaling or set tight min/max bounds
- CooperativeStickyAssignor: default for all new consumer groups
- Alert: rebalances > 1 per minute for a sustained 5-minute window

---

## Incident 4: Stripe Tombstone Gap (2021)

### What Happened

- Topic: "payment-methods", cleanup.policy = compact
- Key = payment_method_id
- Customer removes payment method — producer publishes tombstone (null value)
- Compaction runs — tombstone is retained for delete.retention.ms (default 24 hours)
- After 24 hours: tombstone deleted from topic, key no longer present anywhere
- New service "fraud-scoring-v2" deployed 36 hours after tombstone was published
- Fraud service reads from offset 0 (cold start to build its state)
- Tombstone already deleted — fraud service never sees the deletion event
- Fraud service builds a state map with the removed payment method still present
- Result: fraud service treats deleted payment method as valid and active

### Impact

- 800 transactions flagged for manual review
- None were fraud — they were using payment methods that should have been deleted
- Manual review took 4 days

### Root Cause

- delete.retention.ms guarantees tombstones are visible only for a window after compaction
- Any consumer starting after that window has no way to learn about the deletion
- Compacted topics have this fundamental limitation for late-starting consumers

### Fix

- Consumers building state from compacted topics must start within delete.retention.ms of the tombstone
- OR: maintain a separate "deleted-payment-methods" topic with time-based retention (30 days)
- New consumers check the deletion topic during initial state construction
- Monitoring: alert if any consumer group on a compacted topic starts from offset 0 after a long gap

### What to Remember

- Compaction does not mean "perfect audit log of all changes"
- Late-starting consumers on compacted topics may miss deletions
- This is a known limitation, not a bug — design your consumers to account for it

---

## Incident 5: Uber Exactly-Once Confusion (2019)

### What Happened

- Service: surge pricing calculator
- Input: reads "trip-events" Kafka topic
- Output 1: writes surge multiplier to Redis (per city key)
- Output 2: publishes result to "surge-results" Kafka topic
- Engineers enabled Kafka transactions: idempotent producer + transactional writes
- Engineers believed: "exactly-once = no duplicate surge calculations anywhere"
- Broker failover occurred during a transaction
- Kafka transaction: aborted, retried, committed correctly — Kafka side was fine
- Redis write: happened BEFORE the Kafka transaction committed
- On retry, the Redis write executed a second time
- Combined with an application-level accumulation bug triggered by the double-write, surge multiplier doubled in Redis

### Impact

- 3,400 drivers in Chicago showed 2x surge pricing for 8 minutes
- Passenger complaints: approximately 1,200

### Fix

- Redis write made explicitly idempotent:
  - Use SET surge_{city} {value} with NX flag and expiry window
  - NX = only set if key not already set within the dedup window
- Preferred redesign: remove Redis write from producer entirely
  - Downstream "surge-results-to-redis" consumer reads the Kafka topic and writes to Redis
  - Kafka exactly-once protects the Kafka-to-Kafka pipeline
  - Redis write consumer independently handles idempotency

### The Core Lesson

- Kafka exactly-once protects: producer to broker, and broker to consumer with Kafka output
- Kafka exactly-once does NOT protect: any external system write (Redis, Postgres, HTTP API, S3)
- Every external write must be independently idempotent
- Transactions do not create atomicity across Kafka and external systems

---

# 2. L5 vs L6 Calibration Table

The difference between L5 and L6 is not knowing more facts.
It is diagnosing before prescribing, naming tradeoffs explicitly, and knowing when the simple answer is wrong.

---

| Dimension | L5 Answer | L6 Answer |
|-----------|-----------|-----------|
| High consumer lag | "Add more consumers" | "Diagnose first: consumers < partitions? Per-partition skew? DLQ blocked? Hot partition? Slow processing? Add consumers only after ruling out these causes." |
| Partition count | "Start with 10" | "target_throughput / throughput_per_consumer. Add 2x headroom for growth. Never exceed 4,000 per broker. Too many = slow failover + file handle exhaustion." |
| Ordering guarantee | "Kafka guarantees ordering" | "Within a partition only. Use entity_id as key for per-entity ordering. Cross-partition ordering: no guarantee. Design the consumer to not require it." |
| Exactly-once to database | "Enable Kafka exactly-once" | "Kafka EOS is Kafka-to-Kafka only. DB writes: INSERT ON CONFLICT DO NOTHING with event_id. At-least-once + idempotent consumer = effectively exactly-once." |
| Retention policy | "7 days is the default" | "Retention = write_rate x time x RF in bytes. Compaction for unbounded state. compact+delete for bounded changelogs. Retention is a contract, not just a cost dial." |
| Rebalancing during deploy | "Rolling restarts cause rebalances" | "Mitigate with CooperativeStickyAssignor (only affected partitions pause) and static group.instance.id per pod. Deploy in small batches to limit rebalance scope." |
| Compacted topic too large | "Add more disk" | "Compaction keeps latest value per key. 100M unique keys = large topic even after compaction. Verify key cardinality. Add retention.ms alongside compact for bounded size." |
| Kafka vs SQS | "Use Kafka for async work" | "SQS: task queue, no replay, single consumer, < 10K msg/sec, zero ops. Kafka: replay needed, multiple consumer groups, high throughput, ordering. Kafka costs 6-10 servers + ops overhead." |
| Hot partition | "Add more partitions" | "Diagnose the key first. Adding partitions dilutes average load but does not fix the specific hot key. Use composite key or salting. Separate topic for ultra-high-volume entities." |
| Broker failure | "Kafka is fault tolerant" | "RF=3 tolerates up to 2 simultaneous failures. Only with acks=all AND min.insync.replicas=2. Controller failover: 15-30 seconds. Configure producer retries to cover this window." |
| Schema change | "Update the schema" | "Backward compatible only. Schema Registry enforces compatibility. Expand-contract for breaking changes: add new field, migrate consumers, remove old field. Never remove required fields from live topics." |
| Offset reset strategy | "Reset to earliest" | "Choose by use case: earliest (full replay), latest (skip history), to-datetime (replay from specific time), shift-by-N (skip N messages). Always --dry-run first. Ensure idempotent consumers before any replay." |
| Consumer group isolation | "Each app gets a group" | "Groups are fully isolated — one group's lag never affects another. However: shared topic partition changes affect all groups simultaneously. Coordinate partition count changes across all consumers." |
| Producer acks setting | "Use acks=1 for speed" | "acks=1: leader confirmed, replicas not yet. Leader fails before replication = message lost. Production: acks=all. Accept the ~10ms latency cost. Use async sending to absorb it." |

---

# 3. Brainstorming Questions

Twenty questions across four themes.
These are the kind of design and diagnosis questions asked at L6 system design interviews.
Work through each before reading the hint.

---

## Theme A: Partition and Consumer Design

---

### Question 1: Priority SLAs on a Single Topic

**Setup:**

- Topic: "payment-events", 20 partitions
- 20 consumer instances
- New requirement: enterprise customers (5% of traffic volume) need < 50ms end-to-end processing
- Standard customers: 5 seconds is acceptable

**Question:**

- Can one topic + one consumer group satisfy both SLAs simultaneously?
- If not, why not?
- How do you redesign?

**What to think through:**

- Kafka assigns whole partitions to consumers, not individual messages
- If an enterprise event lands on the same partition as a backlog of standard events, it waits in line
- No concept of message priority within a partition — FIFO only
- One consumer group = one processing pipeline = one effective SLA

**Design direction:**

- Two topics: "payment-events-enterprise" and "payment-events-standard"
- Two consumer groups with different instance counts and SLA targets
- Producer routes based on customer tier at write time
- Tradeoff: producer must know the tier at publish time, leads to topic proliferation

---

### Question 2: Hot Partitions with Ordering Constraint

**Setup:**

- Topic: "product-events", 100 partitions, key = product_id
- 10 products generate 50% of all events
- Those 10 products map to 10 specific partitions
- Consumer instances for those 10 partitions: CPU-saturated
- Other 90 partitions: idle

**Constraint:**

- Per-product ordering must be preserved

**Question:**

- Design a solution that eliminates the hot partitions without losing per-product ordering

**What to think through:**

- Adding more partitions: does not help — those 10 product_ids still hash to the same specific partitions
- Composite key (product_id + sequence % N): distributes a single product across N partitions, but breaks total ordering
- Separate topic per hot product: product_id_12345 gets its own topic with dedicated consumers
- Consumer-side sorting: use composite key for distribution, re-sequence using event sequence number in payload

**Design direction:**

- Identify the 10 hot product_ids (can be static list or dynamic threshold)
- Route them to dedicated "hot-product-events" topic, keyed by product_id + shard
- Consumer for hot topic: parallel readers per shard, sequence number in event payload for re-ordering
- Standard products: remain on original topic, unchanged

---

### Question 3: Banking Traffic Distribution

**Setup:**

- 50 million accounts
- Traffic distribution: top 0.1% of accounts = 30% of all events
- Target: 500,000 events/second
- Consumer latency requirement: < 100ms

**Questions:**

- How many partitions do you need?
- What partition key strategy handles the top 0.1% without hot partitions?
- How do you handle a single account generating 1,000x average traffic?

**What to think through:**

- 500K events/sec, typical consumer processes 10K/sec: 50 partitions minimum
- With headroom and growth: 100 partitions
- Top 0.1% of 50M = 50,000 potentially hot accounts
- Salted key for known hot accounts: account_id + "_" + (timestamp_ms % 5) creates 5 sub-partitions per account
- Trade-off: breaks strict per-account ordering across shards

**Decision point:**

- Is strict per-account ordering required for every account, or just eventual consistency?
- If strict: hot accounts need dedicated partitions or a separate high-throughput topic
- If eventual: salting works, consumers can re-sort by account_id + event_time within a short window

---

### Question 4: IoT Burst Traffic

**Setup:**

- 1 million sensors, 1 event per minute each = approximately 16,700 events/second
- Partition key: sensor_id (for per-sensor ordering)
- Total partitions: 50 (reasonable for this throughput)
- Sensor S-001 starts sending bursts: 1,000 events in 1 second

**Questions:**

- What happens to the consumer processing the partition assigned to S-001?
- Does this affect consumers on other partitions?
- How do you handle the burst without redesigning all partition keys?

**What to think through:**

- S-001 maps to one partition — that partition's consumer falls behind
- Other partitions: completely unaffected (Kafka partitions are independent)
- Consumer for S-001's partition: sees burst, lag grows temporarily
- Options: consumer-level rate limiting per sensor, separate "high-frequency-sensors" topic, sensor-side buffering before publish

**Design direction:**

- Flag sensors exceeding 100x average rate dynamically
- Route flagged sensors to "iot-events-burst" topic with dedicated consumers
- Main topic consumers: never see extreme bursts
- Burst topic: different retention, different consumer SLA

---

### Question 5: Recurring Weekly Lag Spike

**Setup:**

- Consumer group: "notification-sender"
- Consumer lag: spikes every Tuesday at 2 PM, recovers in 30 minutes
- No deploys on Tuesdays
- Pattern has repeated for 6 consecutive weeks

**Questions:**

- What are the likely root causes?
- How do you diagnose without adding consumer instances?
- What is your remediation?

**What to think through:**

- Recurring time-based pattern means something happens every Tuesday at 2 PM
- Check: scheduled jobs that run Tuesday 2 PM (batch data import, weekly report, cron task)
- Check: producer traffic spike at 2 PM Tuesdays (business event, marketing campaign, weekly push notifications)
- Check: external dependency slowdown at 2 PM (downstream API, database, 3rd party service)
- 30-minute recovery suggests a producer burst, not a sustained consumer slowdown

**Diagnosis steps:**

1. Plot producer throughput by minute for the past 6 Tuesdays
2. Check for scheduled jobs or cron tasks firing at 2 PM Tuesday
3. Check consumer processing time per message at 2 PM vs. 1 PM
4. Check external dependency latency at 2 PM

**Fix without adding instances:**

- If producer burst: rate limiting on the batch job that runs at 2 PM
- If external slowdown: circuit breaker with backoff, consumer continues processing without the slow dependency
- If not fixable without more consumers: pre-scale Tuesday at 1:50 PM, scale down at 2:30 PM

---

## Theme B: Retention and Compaction

---

### Question 6: Compacted User Settings Topic

**Setup:**

- Topic: "user-settings"
- cleanup.policy = compact
- Key = user_id
- Value = full settings JSON (approximately 2 KB)
- 100 million users
- Update frequency: most users update monthly, some update hourly

**Questions:**

- How much disk does this topic need at steady state?
- What happens when a user deletes their account?
- How do you handle GDPR deletion requests?

**What to think through:**

- Compaction keeps only latest value per key
- Steady state: 100M keys x 2 KB = 200 GB per replica
- RF=3: 600 GB total
- Account deletion: publish tombstone (null value) for that user_id
- Tombstone retained for delete.retention.ms (default 24h), then removed by compaction

**GDPR complication:**

- Old values for the key existed in log segments before compaction ran
- Compaction is not immediate — old segments may still contain the data temporarily
- True GDPR compliance: crypto-shredding
  - Encrypt value with a user-specific key stored in KMS
  - On deletion request: delete the KMS key
  - Even if old segments not yet compacted, data is unreadable

---

### Question 7: Retention Cost vs. Consumer Requirements

**Setup:**

- Topic: "click-events"
- Current retention: 7 days
- Consumer A: real-time analytics, needs last 24 hours
- Consumer B: batch analytics, needs last 7 days
- Cost team proposes: change retention to 25 hours to save storage

**Questions:**

- What are the consequences of this change?
- Is there a solution satisfying both consumers at lower cost?

**What to think through:**

- Changing to 25 hours: Consumer B's weekly batch job breaks permanently
- Consumer B runs Sunday, needs 7 days of data — only 25 hours available
- Kafka will not warn Consumer B — the job will process whatever data is present and appear to succeed

**Solution:**

- Kafka: 25-hour retention (satisfies Consumer A)
- S3 sink connector: real-time copy of click-events to S3 as events arrive
- Consumer B: reads 7 days from S3 instead of Kafka
- Cost: S3 storage is roughly 10x cheaper per GB than Kafka broker storage
- Latency for Consumer B: batch job anyway, S3 access latency acceptable

---

### Question 8: Compacted Topic and Late-Starting Consumer

**Setup:**

- Compacted topic: "user-profiles"
- User ID 99999: deleted account 2 weeks ago
- Tombstone was published 2 weeks ago
- Compaction ran, tombstone retained for 24 hours, then deleted
- Today: new "Profile Replica Service" starts, reads from offset 0

**Question:**

- Will the Profile Replica Service correctly handle user 99999's deletion?
- What is the root cause?

**Answer:**

- No. The Profile Replica Service will never see the tombstone.
- It will see user 99999's last profile value from before the deletion.
- It will treat user 99999 as an active user with a valid profile.

**Root cause:**

- Tombstones are not permanent in compacted topics
- delete.retention.ms controls how long tombstones survive after compaction
- Late-starting consumers that start after tombstone expiry cannot learn about deletions
- This is a fundamental property of compacted topics, not a configuration error

**Mitigation:**

- Separate "account-deletions" topic with 30-day time-based retention
- New services onboarding: must consume the deletions topic during initial state bootstrap
- Document this requirement explicitly for all consumers of the compacted topic

---

### Question 9: Bounding Compacted Topic Size

**Setup:**

- Topic: "order-state"
- cleanup.policy = compact
- Current size: 2 TB
- Active orders: 500,000
- Total unique order_ids in log: 50 million (old, closed orders still present)
- Orders older than 30 days: never needed again

**Question:**

- How do you bound disk usage while preserving state for active orders?

**What to think through:**

- Compaction alone: keeps latest value for all 50M order_ids — never shrinks regardless
- Need to remove old keys: either publish tombstones for closed orders after 30 days
- OR: use compact+delete with retention.ms = 30 days

**Design:**

- cleanup.policy = compact,delete
- retention.ms = 2592000000 (30 days in milliseconds)
- Old order keys: compacted to latest value within the 30-day window, then deleted with their segment
- Active orders: always updated within 30 days, remain in topic
- Expected size after steady state: 500K x avg_order_state_size (much less than 2 TB)

**What to warn:**

- compact+delete: a key disappearing does not mean it was explicitly deleted — it may just be aged out
- If you need to distinguish "aged out" vs. "explicitly deleted": publish tombstones before relying on age-based deletion

---

### Question 10: Compaction Timing Walkthrough

**Setup:**

- cleanup.policy = compact,delete
- retention.ms = 86400000 (24 hours)
- delete.retention.ms = 3600000 (1 hour)

**Timeline:**

- 10:00 AM: message for key X published (value = "first")
- 10:30 AM: update for key X published (value = "updated")
- 11:00 AM: tombstone for key X published (value = null)

**Questions:**

1. When is the tombstone eligible for deletion?
2. When is key X fully gone from the topic?
3. A consumer starts at 11:45 AM reading from latest offset. Does it see key X?

**Answers:**

1. Tombstone eligible for deletion: 11:00 AM + 1 hour (delete.retention.ms) = 12:00 PM
2. Key X fully gone: after compaction runs post-12:00 PM and cleans the tombstone. Compaction is asynchronous — could be 12:05 PM or later.
3. Consumer starting at 11:45 AM from latest: will NOT see key X. It only sees messages published after 11:45 AM. Key X had its last message at 11:00 AM.

**Bonus:**

- Consumer starts at 11:45 AM from offset 0: may see the tombstone if compaction has not yet run. After compaction cleans the tombstone post-12:00 PM, the tombstone is gone. Timing is non-deterministic.

---

## Theme C: Exactly-Once and Delivery

---

### Question 11: Flash Sale Inventory

**Setup:**

- Flash sale: 100,000 users attempt to purchase the last 50 units simultaneously
- Consumer reads "purchase-attempts" topic
- Consumer deducts inventory in a database
- Consumer publishes result to "purchase-results" topic
- Consumer restarts in the middle of the sale

**Design questions:**

- What is your idempotency key strategy?
- What delivery semantics do you need?
- What happens on consumer restart?
- How do you prevent oversell?
- How do you prevent lost purchases?

**What to think through:**

- Oversell cause: consumer deducts inventory, Kafka commit fails, consumer retries and deducts again
- Fix: idempotency key = purchase_attempt_id (UUID present in the message payload)
- DB write: INSERT INTO deductions (attempt_id, units, ts) ON CONFLICT (attempt_id) DO NOTHING
- If rows_affected = 0: duplicate, skip silently
- If rows_affected = 1: first time seen, proceed with inventory check

**Restart behavior:**

- Consumer restarts from last committed offset
- Messages since last commit: reprocessed
- With idempotent DB writes: safe — duplicates silently ignored

**Delivery semantics needed:**

- Kafka EOS not required here
- At-least-once delivery + idempotent DB write = effectively exactly-once for inventory

---

### Question 12: Financial Reconciliation Atomic Write

**Setup:**

- Consumer reads "bank-transactions" topic
- Must atomically write to:
  1. Balance database table
  2. Audit log database table
  3. "balance-updated" Kafka topic

**Questions:**

- Is true atomicity achievable across all three?
- What is the exact scope of Kafka's exactly-once guarantee?
- How do you achieve effectively-exactly-once semantics?

**Kafka EOS scope:**

- Kafka transactions guarantee: read from topic A and write to topic B atomically
- Both writes succeed or both roll back as seen by read_committed consumers
- This protects: Kafka-to-Kafka pipeline only

**Database writes:**

- NOT included in Kafka transactions
- A Kafka transaction aborting does not roll back a DB write that already occurred

**Design for effectively-exactly-once:**

- Write to balance DB and audit log in one ACID DB transaction, using transaction_id as idempotency key
- If DB transaction succeeds: commit Kafka offset and publish to "balance-updated"
- If DB transaction fails: do not commit Kafka offset, retry
- Outcome: DB is updated at most once per transaction_id; Kafka offset commits only after DB success

**What you accept:**

- True atomicity between DB and Kafka is impossible without distributed transactions (2PC)
- "balance-updated" topic may have occasional duplicates on consumer restart
- Downstream consumers of "balance-updated" must also be idempotent

---

### Question 13: Kafka Transactions with External API

**Setup:**

- Payment consumer using Kafka transactions (isolation.level = read_committed)
- Processing pipeline: read message → call fraud API (200ms latency) → write to Kafka output topic

**Questions:**

- How does the 200ms API call affect the transaction?
- What if the fraud API returns success but the Kafka transaction then aborts?
- How do you handle this idempotently?

**What to think through:**

- Kafka transaction is open for the entire 200ms API call duration
- Long-open transactions hold back consumer position on output topic for read_committed consumers
- Other consumers on the output topic see no progress for 200ms per message
- At 1,000 events/sec: severe downstream lag accumulates

**Abort scenario:**

- Fraud API returns PASS
- Kafka transaction aborts (broker failover during commit)
- Producer retries: calls fraud API again with a new attempt
- Fraud API called twice for the same payment
- If fraud API is not idempotent: potential double-evaluation, double-block, or double-allow

**Fix:**

- Assign request_id = Kafka message offset + partition_id as idempotency key for fraud API
- Fraud API: cache result by request_id for 60 seconds
- Second call with same request_id: returns cached result, does not re-evaluate
- Kafka transaction: retried correctly with correct fraud result

**Architecture recommendation:**

- Move fraud API call outside of Kafka transaction
- Evaluate fraud first, write result to event payload, then start transaction to commit the result

---

### Question 14: Commit Offset Migration

**Setup:**

- Current notification service flow:
  1. Read message from Kafka
  2. Commit offset
  3. Send push notification

**Proposed new flow:**

  1. Read message from Kafka
  2. Send push notification
  3. Commit offset

**Questions:**

- What is the blast radius of this change?
- What behavior will users experience if the service crashes between step 2 and step 3?
- How do you make this safe?

**Current behavior (commit before send):**

- Service crashes after commit, before send: message is permanently lost
- Users: sometimes do not receive notifications (silent loss)
- Delivery semantics: at-most-once

**New behavior (commit after send):**

- Service crashes after send, before commit: message reprocessed on restart
- Users: sometimes receive the same notification twice
- Delivery semantics: at-least-once
- Blast radius: every user with a pending notification at crash time gets a duplicate

**For most notification use cases:**

- Duplicates are more acceptable than missed messages
- This is the right direction to move

**Making it safe:**

- Notification provider API: pass idempotency_key = message_id or event_id in every request
- FCM and APNs both support deduplication keys natively
- Same notification sent twice with same key: provider delivers it once
- Result: effectively-exactly-once notification delivery

---

### Question 15: Duplicate Account Cleanup

**Setup:**

- Consumer has run at-least-once for 6 months
- Discovery: 5,000 duplicate accounts created from a rebalance incident 3 months ago
- The consumer had no idempotency protection at that time
- Incident: fixed 3 months ago, idempotency now in place for new messages

**Questions:**

- How do you find the 5,000 duplicates?
- How do you prevent future duplicates?
- How do you verify the fix works?

**Finding duplicates:**

- Query: SELECT event_id, COUNT(*) FROM accounts GROUP BY event_id HAVING COUNT(*) > 1
- This identifies accounts created from the same Kafka event_id (created twice)
- JOIN back to original events to identify affected users

**Cleanup strategy:**

- Identify canonical account: earliest created_at timestamp for a given event_id
- Soft-delete or merge the duplicate: set is_duplicate = true or merge activity into canonical
- Notify affected users if any activity was merged

**Verification:**

- Deploy idempotent consumer (already done)
- Run load test in staging: publish 1,000 test events, trigger a rebalance mid-run, verify 0 duplicate accounts created
- Monitor production: count of duplicate event_ids over 30 days should equal 0
- Add assertion: every staging deploy triggers a rebalance test as part of CI

---

## Theme D: Operational and Scale

---

### Question 16: Payment Processor Lag Alert

**Setup:**

- Alert fires: "payment-processor lag > 100,000 messages for 15 minutes"
- Normal consumer throughput: 1,000 events/second
- Topic: 20 partitions, 20 consumer instances
- Time: 2:15 PM on a Wednesday

**Question:**

- Walk through your complete diagnosis and remediation process
- What do you check first?
- What are the top 5 root causes at this lag level?

**Diagnosis order:**

1. Check per-partition lag: is lag spread evenly, or concentrated in one or two partitions?
2. Check consumer instance health: are all 20 instances running and joined to the group?
3. Check consumer processing rate now vs. 30 minutes ago: did throughput drop?
4. Check producer throughput: did event rate spike above normal 1,000/sec?
5. Check downstream dependencies: database slow? External API timing out?

**Top 5 root causes:**

1. Hot partition — one partition holds all the lag, others are fine
2. Consumer instance crashed — 20 partitions now on 19 consumers, plus rebalance overhead
3. Downstream database slow — consumers processing but writes taking longer, builds up
4. External API timeout — consumer waiting 30 seconds per message for a 3rd party call
5. Producer traffic spike — marketing campaign triggered 10x normal event rate

**Remediation by cause:**

- Hot partition: fix partition key long-term; short-term cannot be fixed without topic repartitioning
- Consumer crash: Kubernetes restarts automatically, monitor recovery within 60 seconds
- DB slow: identify slow query, add circuit breaker, temporarily route to DLQ to unblock
- External API timeout: reduce timeout, add fallback behavior, skip slow call temporarily
- Traffic spike: add consumer instances up to partition count maximum

---

### Question 17: New Consumer Group Onboarding

**Setup:**

- Existing topic: "order-events", 20 partitions, 100,000 events/second
- Existing consumer groups: 3 groups, each with 20 consumer instances
- New team request: 100 consumer instances for "maximum parallelism"

**Questions:**

- What do you tell the new team about their 100-instance request?
- What topic changes might you suggest?
- What consumer group configuration should they use?

**What to tell them:**

- 20 partitions is the hard ceiling for parallelism in a single consumer group
- The 21st consumer instance receives 0 partitions — it is completely idle
- 100 instances on a 20-partition topic: 80 instances are idle, burning memory and contributing to rebalance overhead

**If they genuinely need 100-way parallelism:**

- Increase topic to 100 partitions — requires coordination with all existing consumer groups
- All existing groups will also rebalance and must update their consumer counts
- This is a cluster-wide change, not just the new team's change

**Configuration recommendations:**

- Start with 20 consumer instances to match partition count
- Use CooperativeStickyAssignor for all groups
- Set group.instance.id: static membership, faster rejoins after pod restarts
- If throughput insufficient with 20 consumers: tune max.poll.records per consumer instead of adding more instances

---

### Question 18: Partition Count Migration

**Setup:**

- Topic: "order-events", 20 partitions today
- Upcoming traffic: 4x increase requires 80 partitions
- 10 consumer groups currently reading this topic
- Each consumer group has exactly 20 consumer instances

**Question:**

- Walk through the migration plan step by step
- How does partition key routing change?
- How do you verify the migration succeeded?

**Migration plan:**

1. Announce migration date to all 10 consumer group teams: 2-week advance notice
2. Coordinate: all teams commit to scaling to 80 consumer instances before migration day
3. Day of migration: increase topic partitions: kafka-topics.sh --alter --partitions 80
4. Immediately after: all 10 consumer groups trigger rebalance automatically
5. Each group must have 80 consumers available or some consumers handle 4 partitions each

**Key routing change:**

- Before: hash(order_id) % 20 determines partition
- After: hash(order_id) % 80 determines partition
- An order that was on partition 5 before may be on partition 37 after
- Ordering: preserved per key going forward
- Historical messages: still accessible on old partition numbers (partitions 0-19)
- New messages: routed to 0-79

**Verification:**

- Check: all 80 partitions have at least 1 leader (no offline partitions)
- Check: per-partition message rates are roughly balanced (no single partition at 100x average)
- Check: each consumer group now shows 80 partition assignments total
- Check: no under-replicated partitions post-migration
- Monitor lag across all 10 groups for 30 minutes post-migration

---

### Question 19: Kafka Streams vs. Apache Flink

**Use case:**

- Compute fraud risk score from each user's purchases in a 30-day sliding window
- 50 million users, approximately 5 purchases each = 250 million state entries
- Latency target: sub-second on each new event
- State must survive service restarts

---

| Dimension | Kafka Streams | Apache Flink |
|-----------|--------------|-------------|
| Deployment model | Library inside your JVM app | Separate cluster to operate |
| State backend | RocksDB per partition, local disk | RocksDB + remote checkpoint (S3/HDFS) |
| 250M state entries | Viable with adequate local disk | Viable, better at very large state with incremental checkpointing |
| 30-day sliding window | Supported natively | Supported natively, more window types available |
| Operational overhead | Low — no external cluster | High — Flink cluster management, job manager, task managers |
| Exactly-once semantics | Yes, via Kafka transactions | Yes, via checkpointing |
| State recovery on restart | Replay from Kafka changelog topic | Restore from S3 checkpoint |
| Sub-second latency | Yes | Yes |
| Team expertise required | Java/Kotlin + Kafka knowledge | Flink API + cluster operations |
| Complex event patterns | Limited | CEP library available |

**Recommendation:**

- If your team already operates Kafka and has no Flink expertise: use Kafka Streams
- If state exceeds available local disk: Flink with S3 backend scales more cleanly
- If you need complex event patterns beyond windowing: Flink's CEP library is more powerful
- For 250M entries at ~1 KB each: 250 GB per replica — plan disk accordingly for Kafka Streams

---

### Question 20: Full Cluster Capacity Planning

**Requirements:**

- 50 services, each producing to 3 topics = 150 topics total
- Total write rate: 500,000 events/second
- Average event size: 2 KB
- Replication factor: 3
- Retention: 14 days
- Consumer groups per topic: 5

**Calculate each step:**

---

**Step 1: Write bandwidth**

- Ingestion rate: 500K events/sec x 2 KB = 1 GB/sec raw
- With replication: 1 GB/sec x 3 replicas = 3 GB/sec total broker write bandwidth

**Step 2: Read bandwidth**

- 5 consumer groups each reading full ingestion rate
- Read bandwidth: 1 GB/sec x 5 groups = 5 GB/sec total broker read bandwidth

**Step 3: Total bandwidth**

- Write + Read = 3 + 5 = 8 GB/sec = 8,000 MB/sec
- At 300 MB/sec usable per broker: 8,000 / 300 = 26.7 — minimum 27 brokers for throughput

**Step 4: Storage**

- Raw ingestion per day: 1 GB/sec x 86,400 = 86.4 TB
- 14 days: 86.4 x 14 = 1,209.6 TB per replica
- With RF=3: 1,209.6 x 3 = 3,628 TB total
- After LZ4 compression at 3:1 ratio: 3,628 / 3 = approximately 1,210 TB compressed total

**Step 5: Brokers for storage**

- At 30 TB usable per broker: 1,210 / 30 = 40 brokers
- With 30% headroom reserved: 40 / 0.7 = 57 brokers
- Storage is the binding constraint: use 57 brokers (covers bandwidth requirement too)

**Step 6: Partitions per topic**

- 500K events/sec across 150 topics = 3,333 events/sec per topic average
- At 10,000 events/sec per partition: 1 partition is technically sufficient
- Recommended with 2x headroom and future growth: 10 partitions per topic
- Total partitions: 150 topics x 10 = 1,500 partitions
- Per broker: 1,500 / 57 = 26 partitions per broker — well under the 4,000 limit

**Step 7: Consumer instances per group**

- 5 consumer groups x 10 partitions per topic = 10 instances per group per topic
- Maximum useful instances per group per topic: 10 (matches partition count)
- Total consumer instances across all groups and topics: 150 topics x 5 groups x 10 instances = 7,500

---

# 4. Homework Exercises

Six exercises with setup, specific tasks, and L6-level hints.
Work the problem before reading the hint.

---

## Exercise 1: Debug Hot Partition

**Time estimate:** 20 minutes

**Setup:**

- Topic: "user-activity", 10 partitions
- Partition 3 throughput: 450,000 messages/second
- Partitions 0, 1, 2, 4, 5, 6, 7, 8, 9 throughput: approximately 5,000 messages/second each
- Partition key: user_id
- Consumer for partition 3: CPU at 100%, falling 45 minutes behind

**Tasks:**

1. Why is partition 3 getting approximately 90x more traffic than other partitions?

2. Write the SQL query to find the top 10 user_ids generating the most traffic.

3. Design a new partition key that eliminates the hot partition while preserving per-user event ordering.

4. Write the producer configuration change for your new strategy.

5. How do you migrate from the old key to the new key without losing messages or breaking consumers?

**L6 Hint:**

- Partition 3 = one specific user_id whose hash(user_id) % 10 = 3. Likely a bot, test account, or internal automation using a constant ID.
- SQL: SELECT user_id, COUNT(*) AS event_count FROM user_activity_log WHERE ts > NOW() - INTERVAL '1 hour' GROUP BY user_id ORDER BY event_count DESC LIMIT 10;
- New key strategy: user_id + "_" + (event_type_hash % 5) distributes events for one user across up to 5 partitions. Trade-off: loses strict total ordering across event types for one user.
- If strict total ordering is required: separate "high-volume-users" topic with dedicated consumers for flagged user_ids.
- Migration: dual-publish for 30-60 minutes. Producers write to both old key scheme and new key scheme simultaneously. Consumers use offset tracking to drain old topic before fully switching. Monitor lag on both schemes before cutover.

---

## Exercise 2: Retention Design for Compliance

**Time estimate:** 30 minutes

**Setup:**

- Topic: "trade-events"
- Volume: 500,000 events/day, 500 bytes each
- Four stakeholder requirements:
  - Real-time risk engine: must access last 24 hours
  - Compliance audit team: must access last 7 years
  - Analytics team: must access last 30 days
  - GDPR compliance officer: must delete a specific trader's data within 30 days of request

**Tasks:**

1. Can one Kafka topic with time-based retention serve all four requirements? What is the storage cost at 7-year retention?

2. Design a tiered storage architecture: hot (Kafka), warm (S3), cold (archive). What moves where and when?

3. How do you handle GDPR deletion across all three storage tiers?

4. What is the minimum Kafka retention period that satisfies all real-time consumers?

5. Calculate the total storage cost for the full 7-year compliance window using a 3:1 compression ratio.

**L6 Hint:**

- 7-year Kafka retention: 500K events/day x 500 bytes x 365 x 7 years = approximately 638 GB uncompressed. At 3:1 compression: ~213 GB. With RF=3: ~640 GB total. Technically feasible but expensive on broker disk.
- Better design: Kafka for 30 days (covers risk + analytics), S3/Parquet for 7 years (compliance queries via Athena), Glacier for archives.
- GDPR in Kafka: crypto-shredding — encrypt per-trader with a key stored in KMS, delete the KMS key on deletion request. Data becomes unreadable without key.
- GDPR in S3: partition files by trader_id in the S3 path. On deletion request: delete all objects at that path prefix.
- Minimum Kafka retention: 30 days (analytics is the longest-lived real-time consumer).

---

## Exercise 3: Idempotent Consumer Implementation

**Time estimate:** 25 minutes

**Setup:**

- Consumer processes topic: "email-send-requests"
- Event schema: { request_id: UUID, recipient: string, subject: string, body: string }
- Current delivery semantics: at-least-once
- Problem: on consumer restarts, emails are sometimes sent twice

**Tasks:**

1. Write the database schema for a deduplication table (table name, columns, indexes, constraints).

2. Write the consumer processing logic pseudocode, including the duplicate check.

3. What is your strategy if the deduplication database is unavailable? Fail open or fail closed, and why?

4. A duplicate arrives 30 days later, outside your dedup table's retention window. How do you handle it?

5. Design the dedup table cleanup process: what retention period, how do you purge old entries safely?

**L6 Hint:**

- Schema:
  ```sql
  CREATE TABLE email_dedup (
    request_id UUID PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
  );
  CREATE INDEX idx_email_dedup_processed_at ON email_dedup(processed_at);
  ```
- Consumer logic: INSERT INTO email_dedup (request_id) VALUES ($1) ON CONFLICT DO NOTHING. Check rows_affected: if 0, skip (duplicate). If 1, send email.
- Database unavailable: fail closed. Do not send the email. Do not commit Kafka offset. Let the message sit in Kafka. Sending without dedup check risks duplicates. Retry when DB recovers.
- 30-day duplicate outside retention window: also make the email provider idempotent. Pass request_id as idempotency_key to the email API (SendGrid and Mailgun both support this natively).
- Cleanup: DELETE FROM email_dedup WHERE processed_at < NOW() - INTERVAL '7 days'. Run nightly, delete in batches of 10,000 rows to avoid table lock.

---

## Exercise 4: Consumer Group Impact Analysis

**Time estimate:** 20 minutes

**Setup:**

- Topic: "order-events", 12 partitions
- Three existing consumer groups:
  - "fulfillment": 12 consumer instances, SLA: lag must stay below 1,000
  - "analytics": 3 consumer instances, lag tolerance: up to 1,000,000
  - "search-indexer": 6 consumer instances, SLA: lag must stay below 10,000
- New request: add "ml-feature-pipeline" consumer group with 50 instances, processing time = 100ms per message

**Tasks:**

1. Does adding the new consumer group affect any existing consumer group's throughput or lag? Explain why or why not.

2. What is the maximum throughput of "ml-feature-pipeline" given 12 partitions and 100ms per message processing time?

3. How long will it take "ml-feature-pipeline" to replay 30 days of history (approximately 100 million events)?

4. What topic change would allow all 50 consumer instances to be genuinely useful in parallel?

5. Design the deployment plan for adding the new consumer group with minimum disruption to existing groups.

**L6 Hint:**

- Impact on existing groups: zero. Kafka consumer groups are fully independent. Each group maintains its own offsets. Adding a new group does not change partition assignment for any other group.
- Max throughput: 12 partitions x (1 message / 0.1 sec) = 120 messages/second. The other 38 instances are idle.
- Replay time: 100,000,000 messages / 120 messages per second = 833,333 seconds = approximately 9.6 days.
- Topic change needed for 50 consumers: increase partitions to at least 50. This triggers rebalance for ALL existing consumer groups simultaneously. Coordinate with all teams before doing this.
- Deployment plan: (a) create the new consumer group with 12 instances initially, (b) verify it reads and processes correctly, (c) if higher throughput required, coordinate a partition count increase with all 3 existing teams, (d) after partition increase, scale new group to 50 instances.

---

## Exercise 5: Schema Evolution Migration

**Time estimate:** 30 minutes

**Existing v1 Avro schema:**

```json
{
  "name": "UserCreated",
  "type": "record",
  "fields": [
    {"name": "user_id", "type": "string"},
    {"name": "email", "type": "string"},
    {"name": "created_at", "type": "long"}
  ]
}
```

**New requirements:**

- Add field: country_code (string, required for all new users going forward)
- Add field: referral_source (string, optional, can be null)
- Rename field: email to email_address (breaking change requested by the API team)

**Tasks:**

1. Which of these three changes are backward compatible? Which are breaking?

2. Design the full expand-contract migration strategy for the email to email_address rename.

3. Write the v2 Avro schema (backward compatible intermediate state).

4. Write the v3 Avro schema (final target state after migration is complete).

5. How should consumers handle a mix of v1 messages (30-day history in the topic) and v2 messages arriving now?

**L6 Hint:**

- Backward compatibility analysis:
  - country_code as a required field with no default = BREAKING. Old consumers cannot deserialize new messages. Fix: add it as optional with default value "UNKNOWN".
  - referral_source as a nullable union with null default = backward compatible.
  - Rename email to email_address = BREAKING. Old consumers expect the field named "email".
- Expand phase (v2 schema): add "email_address" as a new field alongside the original "email" field. Both present in the same record. Producers write both. Consumers read either field name.
- Contract phase (v3 schema): after all consumers have migrated to read "email_address", remove the old "email" field.
- Consumer handling v1 + v2 in same topic: v2 reader schema must declare "email" as optional with a default. Avro schema resolution maps v1 records (which have "email" but not "email_address") using the default declared in v2.
- Schema Registry: register v2 with BACKWARD compatibility mode. Registry will reject any schema that breaks backward compatibility.

---

## Exercise 6: Cluster Capacity Planning

**Time estimate:** 25 minutes

**Requirements:**

- 5 producer services
- Each service: 10,000 events/second at 1.5 KB average event size
- Total ingestion: 75 MB/second
- Consumer groups: 8, each consuming all events from all topics
- Replication factor: 3
- Retention: 7 days
- SLA: p99 producer latency < 10ms, p99 consumer latency < 50ms

**Calculate each step. Show your work.**

1. Total broker write bandwidth (ingestion plus replication)

2. Total broker read bandwidth (all consumer groups reading)

3. Total broker bandwidth combined (write plus read)

4. Minimum brokers needed for throughput (assume 300 MB/sec usable bandwidth per broker)

5. Total raw storage for 7 days with replication included

6. Compressed storage after LZ4 at 3:1 compression ratio

7. Minimum brokers needed for storage (assume 10 TB usable per broker, reserve 30% headroom)

8. Recommended partition count per topic (assume 5 topics, one per service)

**Worked Solution:**

- Step 1 write bandwidth: 75 MB/sec x 3 replicas = 225 MB/sec
- Step 2 read bandwidth: 75 MB/sec x 8 consumer groups = 600 MB/sec
- Step 3 total bandwidth: 225 + 600 = 825 MB/sec
- Step 4 brokers for throughput: 825 / 300 = 2.75 — round up to 3 brokers
- Step 5 raw storage: 75 MB/sec x 86,400 sec/day x 7 days x 3 replicas = 136,080,000 MB = approximately 136 TB
- Step 6 compressed storage: 136 TB / 3 = approximately 45 TB
- Step 7 brokers for storage: 45 TB / (10 TB x 0.7 headroom) = 45 / 7 = 6.4 — round up to 7 brokers
- Storage is the binding constraint: use 7 brokers
- Step 8 partitions per topic: 75 MB/sec total across 5 topics = 15 MB/sec per topic. At 10 MB/sec per partition: 2 partitions minimum. Recommended with 2x growth headroom: 20 partitions per topic.

**Final cluster spec:**

- 7 brokers, 10 TB disk each
- 5 topics x 20 partitions = 100 total partitions
- Per broker: 100 / 7 = 14 partitions per broker — well under the 4,000 limit
- 3 ZooKeeper nodes (or 3 KRaft controller nodes)

---

# 5. Quick Reference Card

For interview prep. These numbers should feel instinctive, not looked up.

---

## Key Numbers

| Fact | Value |
|------|-------|
| Max partitions per broker (recommended) | 4,000 |
| Max partitions per Kafka cluster | 200,000 |
| Broker sequential write throughput (SSD) | 100-300 MB/sec |
| Exactly-once overhead vs. at-least-once | ~20-30% throughput reduction |
| Default max.poll.interval.ms | 5 minutes (300,000 ms) |
| Default session.timeout.ms | 10 seconds (10,000 ms) |
| Default retention.ms | 7 days (604,800,000 ms) |
| Default segment.bytes | 1 GB |
| Default delete.retention.ms (tombstone window) | 24 hours (86,400,000 ms) |
| ISR lag threshold (replica.lag.time.max.ms) | 10 seconds |
| Controller failover time | 15-30 seconds |
| Recommended replication factor (production) | 3 |
| min.insync.replicas for durability with RF=3 | 2 |
| Typical broker RAM recommendation | 32-64 GB |

---

## Alert Thresholds

| Metric | Alert Threshold | Recommended Action |
|--------|----------------|-------------------|
| Consumer lag (per group) | > 10,000 for > 5 minutes | Diagnose root cause: hot partition, slow consumer, downstream dep |
| Under-replicated partitions | > 0 | Check broker health immediately — data durability at risk |
| Offline partitions | > 0 | Leader election failed — hard failure, immediate response |
| Broker disk utilization | > 70% | Reduce retention or add brokers before hitting 85% |
| Rebalance rate | > 1 per 5 minutes sustained | Consumer instability — check health, timeouts, deploy activity |
| Per-partition throughput skew | Any partition > 3x average rate | Hot partition — investigate partition key distribution |
| ISR shrink events | > 2 per hour | Replication falling behind — check broker load and disk |
| Consumer processing time p99 | > 50% of max.poll.interval.ms | Risk of session timeout — reduce max.poll.records or increase timeout |

---

## Delivery Semantics Comparison

| Guarantee | When Offset Committed | Message Loss Risk | Duplicate Risk | Typical Use Case |
|-----------|----------------------|------------------|----------------|-----------------|
| At-most-once | Before processing | Yes — crash after commit loses message | No | Metrics, logs, fire-and-forget |
| At-least-once | After processing succeeds | No | Yes — reprocessed on crash | Most production workloads |
| Exactly-once (Kafka EOS) | Atomically with Kafka output | No | No — within Kafka pipeline | Kafka-to-Kafka stream processing only |
| Effectively exactly-once | After idempotent write to external system | No | Functionally no — duplicates silently ignored | At-least-once + idempotent writes |

---

## Partition Key Selection Guide

| Scenario | Key Strategy | Ordering Preserved | Risk |
|----------|-------------|-------------------|------|
| Per-user event ordering | user_id | Yes, per user | Hot partition if power users exist |
| Per-order state | order_id | Yes, per order | Generally safe with large order counts |
| System-generated events | Random UUID or round-robin | None by design | Uniform distribution, no risk |
| IoT sensor data | sensor_id | Yes, per sensor | Hot partition if sensors burst |
| Power user or hot entity | entity_id + shard_number | Yes, per shard | Ordering within entity lost |
| Multi-tenant with skewed tenants | tenant_id + record_id | Yes, per record | Hot partition if one tenant dominates |
| Audit or append-only log | null (round-robin) | None by design | None |

---

## Compaction Policy Decision Tree

| Need | Cleanup Policy | Notes |
|------|---------------|-------|
| Latest state per key, unlimited retention | compact | Disk grows with key cardinality — never shrinks |
| Latest state per key, bounded disk | compact,delete | Aged-out keys silently disappear — document this for consumers |
| Time-bounded event log, no deduplication | delete | Simple, predictable disk usage |
| Account deletions with audit window | compact + tombstone | delete.retention.ms controls tombstone visibility window |
| Regulatory compliance: specific duration then purge | delete with exact retention.ms | Set precisely to SLA requirement, document as a contract |

---

## Common Misconceptions

| Misconception | Correct Understanding |
|--------------|----------------------|
| "Kafka guarantees ordering" | Within a single partition only. Cross-partition ordering: no guarantee. |
| "Exactly-once means no duplicates anywhere" | Kafka EOS is Kafka-to-Kafka only. Every external write (DB, Redis, API) must be independently idempotent. |
| "More consumers = more throughput" | Only up to partition count. Beyond that, extra consumers are idle. |
| "Compacted topics have no data loss" | Late-starting consumers miss tombstones after delete.retention.ms expires. Deleted keys may appear active to them. |
| "Consumer groups affect each other" | Groups are fully independent. One group's lag does not affect another group. |
| "Kafka is always better than SQS" | SQS is simpler, cheaper, zero-ops for task queues with single consumers. Kafka is correct for replay, multi-consumer, ordering, and high throughput. |
| "Retention is just a cost setting" | Retention is a contract. Consumers silently process partial data if retention is reduced without notifying them. |
| "Hot partitions are fixed by adding partitions" | Adding partitions dilutes average load but does not fix the specific hot key. Fix the key distribution first. |

---

## Kafka Transactions Scope Reference

| Operation | Protected by Kafka Transactions? |
|-----------|----------------------------------|
| Producer writes to a Kafka topic | Yes |
| Consume from topic A, write to topic B atomically | Yes — read_committed consumers see both or neither |
| Write to Postgres | No |
| Write to Redis | No |
| Call an external HTTP API | No |
| Write to S3 | No |
| Kafka offset commit + write to output topic atomically | Yes |
| Write to two different Kafka clusters atomically | No |

---

## Chapter 34 Summary

Kafka internals at L6 requires depth across four dimensions.

**Storage model:**
Partitions are append-only logs on disk.
Segments are the unit of retention and compaction.
Compaction preserves the latest value per key within a segment.
Tombstones expire after delete.retention.ms.
Late-starting consumers on compacted topics can miss deletions.

**Consumer model:**
Consumer groups provide parallel consumption up to the partition count.
Rebalancing pauses consumption — CooperativeStickyAssignor minimizes the pause scope.
Static membership (group.instance.id) reduces rebalance frequency.
Consumer lag is a symptom, not a cause — diagnose the root before prescribing.

**Delivery semantics:**
At-least-once is the production default.
Idempotent writes make at-least-once effectively exactly-once for external systems.
Kafka EOS covers Kafka-to-Kafka pipelines only.
Every external write needs its own independent idempotency strategy.

**Operations:**
Partition count can only increase after topic creation, never decrease.
Hot partitions require key redesign, not just more partitions.
Schema changes require backward-compatible expand-contract strategy.
Retention changes affect downstream consumers silently — they are contracts, not just knobs.

**The L6 signal:**
Not knowing these facts.
Diagnosing before prescribing.
Naming the tradeoff before recommending.
Designing for failure before designing for the happy path.
## Supplemental Brainstorming: Chapter 34 — Kafka Internals

*Questions 25-42: Advanced internals and cross-chapter integration.*

### Section A: Advanced Kafka Mechanics (Q25-Q33)

---

**Question 25 — Partition Reassignment and Its Impact**

Your Kafka cluster has 5 brokers and a topic with 20 partitions replicated at RF=3. Broker 2 is
being decommissioned. You initiate a partition reassignment to move its 4 partition replicas to
broker 5. Describe what happens mechanically during the reassignment. What is the impact on
producer and consumer throughput during reassignment, and how do you minimize it?

During partition reassignment: Kafka begins replicating the partition data from the current leader
to the new replica on broker 5. Broker 5 starts fetching log segments from the leader sequentially
from the beginning of the retention window. Until broker 5 has caught up to the leader's end offset,
it is not in the ISR (In-Sync Replicas). During this catch-up phase, the partition has a reduced
ISR. If the leader fails during catch-up, Kafka can only elect a new leader from the existing ISR,
which may not include the fully caught-up broker 5.

Throughput impact: the reassignment adds replication network traffic between the leader broker and
broker 5. For a partition with 1 TB of data and 7-day retention, catch-up requires transferring
1 TB of log data. At 100 MB/second replication throughput, that takes over 2.5 hours. During those
2.5 hours, the leader broker's network is saturated with both normal consumer reads and the
replication catch-up traffic for broker 5.

Mitigation: use throttling. Kafka's kafka-reassign-partitions.sh tool accepts
--throttle <bytes_per_second>. Set the throttle to 50 MB/second so reassignment uses half the
broker's available network bandwidth. The reassignment takes longer (5+ hours instead of 2.5) but
does not saturate the broker. Schedule reassignments during off-peak hours. Monitor ISR shrinkage
on the affected partitions — if ISR drops below 2 during reassignment, temporarily pause the
reassignment.

- Calculate: at 50 MB/second throttle, how long does it take to reassign 4 partitions each with
  250 GB of data? What is the total extra network traffic the leader broker handles?
- Follow-up: the reassignment completes but broker 5 does not become the preferred leader. Kafka
  still routes all reads and writes for those partitions through the old leader on broker 3.
  What command fixes this, and what is "preferred leader election"?

---

**Question 26 — Log Compaction vs. Time-Based Retention: Choosing and Combining**

You have two Kafka topics: (A) "user-preferences" where each user's latest settings matter but
history does not, and (B) "user-transactions" where the full history must be retained for audit
purposes. You consider: log compaction for topic A, time-based retention for topic B, and a
hybrid cleanup.policy=compact,delete for a third topic C. Explain what each policy does
mechanically, how the compaction thread works, and what the worst-case behavior of compaction
is when the topic is heavily written.

Log compaction (cleanup.policy=compact): Kafka periodically runs a compaction thread in the
background. The compaction thread scans the "dirty" segment (all segments written since the last
compaction) and builds an in-memory map of key -> latest_offset. It then rewrites log segments,
keeping only the message with the highest offset for each key and discarding earlier versions. The
result: only the latest value per key is retained, regardless of how old the partition is. A
"tombstone" record (value=null for a key) causes the key to be deleted from the log entirely after
a compaction cycle.

Compaction does NOT run continuously. It runs when the ratio of "dirty" bytes to total bytes exceeds
min.cleanable.dirty.ratio (default 0.5). If a topic is written heavily (1M events/second for a
single key), the compaction thread may fall behind and the topic can grow significantly before the
next compaction cycle runs. Worst-case: with min.cleanable.dirty.ratio=0.5 and a 100 GB partition,
the dirty section can grow to 50 GB before compaction starts. During compaction, the dirty section
can be temporarily expanded further before shrinking.

Hybrid cleanup.policy=compact,delete: Kafka applies both policies. Older messages are deleted
based on retention.ms (time-based). Among retained messages, compaction ensures only the latest
value per key is kept. This is useful for topic C where you need both "don't retain data older
than 30 days" AND "for recent data, only keep the latest value per key."

For topic A (user-preferences): log compaction is correct. Users update settings infrequently but
the latest value must always be available for new consumers (e.g., a new recommendation service
that starts consuming from the beginning must get the current settings for all users, not replay
every historical change).

For topic B (user-transactions): time-based retention with a long window (2 years) and no
compaction. Every transaction event must be preserved; compaction would discard earlier
transactions for the same user.

- Follow-up: a consumer starts from offset 0 on the compacted user-preferences topic. It reads
  user 123's settings record and processes it. Five minutes later, another message arrives for
  user 123 (a settings update). The compaction runs that night and removes the earlier record.
  The consumer has already committed the offset past the old record. Is there any issue? What
  if the consumer needs to restart from offset 0 again after the compaction?

---

**Question 27 — Kafka Connect: Source and Sink Connectors**

You need to stream all new rows from a PostgreSQL "orders" table into a Kafka topic, and then
stream processed events from that topic into an Elasticsearch index for search. Design the
Kafka Connect pipeline using a source connector and a sink connector. Explain how the source
connector detects new rows, what happens if the source connector restarts after a crash, and
how you handle schema changes in the PostgreSQL table.

Kafka Connect is a framework for running data ingestion pipelines without writing producer/consumer
code. Connectors run inside Kafka Connect workers (JVM processes that Kafka manages). A source
connector reads from an external system and publishes to Kafka. A sink connector reads from Kafka
and writes to an external system.

Source connector for PostgreSQL: use the Debezium PostgreSQL connector. Debezium reads the
PostgreSQL WAL (Write-Ahead Log) using logical replication. Every INSERT, UPDATE, and DELETE to the
orders table generates a change event published to a Kafka topic (e.g., "postgres.public.orders").
Debezium stores its current WAL position (LSN — Log Sequence Number) in a Kafka topic called
"connect-offsets." On restart, Debezium reads the last committed LSN from "connect-offsets" and
resumes from that WAL position. No rows are missed (Kafka Connect provides at-least-once delivery;
you must handle deduplication downstream if needed).

Schema changes: if a column is added to the PostgreSQL orders table, Debezium detects the schema
change from the WAL and publishes a schema change event. If Schema Registry is configured,
Debezium registers the new schema version and subsequent events use the new schema. Old consumers
that registered with BACKWARD compatibility can continue reading — the new column appears with a
default value. Dropping a column from PostgreSQL is a breaking change; Debezium will publish events
missing that field, which may break consumers expecting it.

Sink connector for Elasticsearch: use the Confluent Elasticsearch Sink connector. It reads from
the Kafka topic, maps Kafka message keys to Elasticsearch document IDs (enabling idempotent
upserts), and indexes documents into Elasticsearch. If Elasticsearch is unavailable, the connector
pauses (does not crash) and retries with backoff. Consumer lag accumulates in Kafka while
Elasticsearch is down. When Elasticsearch recovers, the connector drains the lag.

- Follow-up: you want zero-downtime migration of the Elasticsearch index (e.g., adding a new
  field that requires an index mapping change). How do you use Kafka Connect's offset management
  to replay the Kafka topic into a new Elasticsearch index, run both indexes in parallel, and
  then switch traffic?

---

**Question 28 — Kafka Streams vs. Flink for Stream Processing**

Your team must choose between Kafka Streams and Apache Flink for a stream processing job that
computes 5-minute windowed aggregations of payment events, joins them with a slowly updating
"merchant" reference table, and outputs results to another Kafka topic. Compare the two on:
deployment complexity, state management, exactly-once semantics, late arrival handling, and the
join semantics for the slowly-changing reference table.

Kafka Streams: a Java library, not a separate cluster. Stream processing logic runs inside your
application JVM alongside your normal application code. No separate cluster to operate. State is
stored in local RocksDB instances on each application instance. State is backed up to Kafka
changelog topics so it survives instance restarts. Deployment: add the library as a dependency,
write the topology, package as a JAR, deploy like any microservice.

Flink: a separate cluster (Flink Job Manager + Task Managers). Your job is submitted as a JAR to
the Flink cluster. State is stored in Flink's managed state (in-memory or RocksDB). Checkpoints
are taken periodically to durable storage (S3, HDFS). Flink offers more expressive windowing
(event-time, session windows, sliding windows), better late-arrival handling via watermarks, and
a richer operator library. Flink supports exactly-once via the two-phase commit sink.

For this specific job:

5-minute windowed aggregations: both support this. Flink's event-time watermark support is more
precise for late arrivals. Kafka Streams supports windowed aggregations but late arrival handling
requires manual configuration of grace periods and is less expressive than Flink's watermark API.

Join with slowly-changing merchant table: in Kafka Streams, use a GlobalKTable for the merchant
reference data. A GlobalKTable is replicated to every application instance, so every instance can
do a local lookup without a network hop. Flink achieves the same with a broadcast join — the
slowly-changing table is broadcast to all task managers. Both work. Kafka Streams is simpler to
implement.

Exactly-once: Kafka Streams supports exactly-once for Kafka-to-Kafka flows using Kafka's
transactional API. Flink supports exactly-once for any sink that supports two-phase commit.

Recommendation for this job: if the team already manages Kubernetes and is comfortable running
distributed systems, Flink. If the team wants minimal operational overhead and the job does not
require advanced windowing, Kafka Streams.

- Follow-up: the payment aggregation job needs to join payment events with a "fraud-score" table
  that updates every 5 seconds. The fraud-score table has 10 million rows. Can it be loaded
  into a GlobalKTable or broadcast table? What is the memory implication?

---

**Question 29 — MirrorMaker 2: Cross-Cluster Replication**

You use MirrorMaker 2 (MM2) to replicate Kafka topics from a US-East primary cluster to an
EU-West disaster-recovery cluster. Your replication lag is normally under 5 seconds. A network
partition between US-East and EU-West lasts 30 minutes. After the partition heals, describe what
happens: (a) how MM2 recovers, (b) how much data was not replicated, and (c) how consumers on
the EU cluster that were reading the replicated topics are affected.

MirrorMaker 2 is a Kafka Connect cluster running in the target (EU-West) cluster. Its source
connectors poll the US-East cluster for new messages. MM2 tracks its replication progress using
consumer group offsets on the source cluster. When the network partition occurs: MM2's source
connectors cannot connect to US-East. They pause and retry with backoff. No new data is replicated
during the 30 minutes.

After healing: MM2 source connectors reconnect to US-East. They resume from the last committed
offset stored in the US-East "mm2-offsets" topic (MM2 stores its source cluster offsets in a
topic on the source cluster). MM2 replays the 30 minutes of data that was not replicated. At
normal replication throughput, if the backlog is 30 minutes of data and MM2 can process it faster
than real-time, it catches up. If US-East ingestion is 1 GB/second and MM2 replication throughput
is 1.2 GB/second, catch-up takes 30 minutes / 0.2 GB/sec advantage = 150 minutes to catch up
while also keeping up with real-time data.

Consumers on EU cluster: if EU-West consumers were reading the replicated topics during the 30-
minute partition, they read up to the last replicated offset and then encountered no new data (the
topic's high watermark in EU stopped advancing). Depending on consumer configuration, they either
blocked (waiting for new messages) or returned empty poll results. No data loss for EU consumers
— they just experienced 30 minutes without new data. After MM2 catches up, consumers resume.

- Design the MM2 topic replication configuration that excludes internal topics (__consumer_offsets,
  connect-configs) from replication while including all application topics.
- Follow-up: a consumer group in EU-West committed offsets to the EU replicated topic during the
  30-minute blackout. After the blackout, MM2 catches up and the EU topic now has 30 minutes of
  new events. Will the EU consumer group automatically process the new events, or will there be
  a consumer group offset issue?

---

**Question 30 — Consumer Group Rebalance: Impact and Mitigation**

You have a consumer group with 20 instances consuming a topic with 20 partitions. A rolling
deployment of your consumer service takes 10 minutes (one instance replaced at a time, 30 seconds
per instance). Every time an instance is stopped and a new one starts, a rebalance occurs. Walk
through the timeline: how many rebalances happen during the 10-minute deployment? What is the
impact of each rebalance on consumer throughput? How do static group membership (group.instance.id)
reduce this impact?

With eager (stop-the-world) rebalancing: when instance 1 is stopped, it leaves the consumer group.
The group coordinator detects this after session.timeout.ms (default 10 seconds). A rebalance
begins. All 19 remaining instances stop processing, submit their partition assignments, wait for
the group coordinator to send new assignments. Rebalance takes 5-30 seconds. Then instance 1's
replacement joins: another rebalance. Total rebalances: 2 per replaced instance x 20 instances =
40 rebalances. At 30 seconds of stop-the-world per rebalance: 40 x 30 seconds = 1,200 seconds of
cumulative consumer downtime across the group, spread over 10 minutes. During each rebalance
window, all 20 partitions are unassigned. Messages continue arriving in Kafka; consumer lag spikes.

Static group membership (group.instance.id): assign each consumer instance a stable ID (e.g.,
"consumer-1" through "consumer-20"). When an instance with a static ID leaves the group, the
group coordinator does NOT immediately trigger a rebalance. It waits for session.timeout.ms. If a
new instance joins with the same static ID within that window, the group coordinator reassigns the
same partitions to the new instance without a full group rebalance. During a rolling deployment:
stop instance 1, new instance 1 joins within session.timeout.ms (set to 60 seconds to give the
new instance time to start), the coordinator reassigns only the 1 partition that was owned by
instance 1. Throughput impact: 19 instances continue uninterrupted. Only the 1 partition being
transferred experiences a brief processing gap. Total rebalances: 0 full-group rebalances, 20
single-partition reassignments.

Cooperative incremental rebalancing (partition.assignment.strategy=CooperativeStickyAssignor):
further reduces impact by only revoking and reassigning partitions that actually need to move,
rather than revoking all partitions and reassigning from scratch.

- What is the correct value for session.timeout.ms if your rolling deployment guarantees each new
  instance starts and joins the group within 45 seconds?
- Follow-up: a consumer instance with static ID "consumer-7" crashes and is not restarted (the
  deployment pipeline fails for that instance). Its static ID never rejoins. How does Kafka handle
  this, and when does its partition get reassigned?

---

**Question 31 — Producer Idempotency: How It Actually Works**

Explain the mechanical implementation of Kafka's idempotent producer (enable.idempotence=true).
What is the producer ID (PID), what is the sequence number, and how does the broker use these
to detect and deduplicate duplicates? What failure scenario does idempotency cover that acks=all
alone does not cover?

Without idempotency: a producer sends a batch with acks=all. The batch is replicated to all ISR
replicas. The leader sends the ack. The ack is lost in the network before reaching the producer.
The producer does not receive the ack and times out. It retries the same batch. The broker receives
the batch again and writes it again — resulting in a duplicate record in the log.

With idempotency (enable.idempotence=true): the producer is assigned a unique Producer ID (PID)
by the broker when it connects. For each partition, the producer assigns a monotonically increasing
sequence number to each batch, starting from 0. The sequence number is included in the batch header.
The broker tracks, per (PID, partition), the last sequence number it successfully wrote. When a
batch arrives, the broker checks: is this sequence number exactly (last_sequence + 1)? If yes,
accept and write. If the sequence number equals last_sequence (duplicate retry): silently discard,
return success to the producer. If the sequence number is lower than expected (out-of-order batch
due to a bug): return an error. If the sequence number is higher than expected (gap in sequence):
return an error indicating missed batches.

This covers the ack-lost scenario: the broker wrote the batch, sent the ack, the ack was lost.
Producer retries. Broker sees the same sequence number, recognizes it as a duplicate, discards it,
returns success. No duplicate in the log.

What idempotency does NOT cover: duplicates across producer restarts. The PID is assigned fresh on
each producer startup. If a producer crashes and restarts, it gets a new PID. The broker does not
know that the new producer is logically the same as the crashed producer. Any in-flight batches
from the old producer that the broker already wrote will not be detected as duplicates by the new
producer's sequence numbers.

- How do Kafka transactions (initTransactions, beginTransaction, commitTransaction) extend
  idempotency to cover the cross-restart duplicate case?
- Follow-up: your producer is producing to 50 partitions. Each partition has an independent
  sequence number tracked by the broker. If the producer crashes and restarts with a new PID,
  how many independent duplicate scenarios are possible?

---

**Question 32 — Exactly-Once Transactions in Kafka: initTransactions, beginTransaction, commitTransaction**

Walk through the complete lifecycle of a Kafka transaction for a Kafka Streams job that reads
from topic A, transforms each message, and writes the result to topic B. Include: what happens
at initTransactions, beginTransaction, the write of transformed messages, commitTransaction, and
what happens if the Streams instance crashes between beginTransaction and commitTransaction. How
does a consumer with isolation.level=read_committed handle the uncommitted messages?

initTransactions: called once at application startup. The producer contacts the transaction
coordinator broker (determined by hash(transactional.id) % num_partitions of the __transaction_state
topic). The coordinator registers the transactional.id, assigns a Producer ID (PID) and epoch,
and fences any previous producer with the same transactional.id and a lower epoch. "Fencing"
means the coordinator will reject any future produce requests from the old PID/epoch combination.
This is the mechanism that prevents the old (crashed) instance from completing a transaction
that the new instance is taking over.

beginTransaction: a local call. No network request. The producer marks itself as being inside a
transaction. Subsequent produce calls are marked as part of this transaction in the batch header.

Write to topic B: the producer sends batches to topic B's leader broker. The broker writes the
batches to the log but marks them as "transactional — not yet committed." Consumers with
isolation.level=read_committed cannot read these messages yet.

Commit to topic A offsets: the producer sends an "add offsets to transaction" request, associating
the consumed offsets from topic A with this transaction. The offsets will only be committed if the
transaction commits.

commitTransaction: the producer sends a commit request to the transaction coordinator. The
coordinator writes "PREPARE_COMMIT" to the __transaction_state log, then sends "commit markers"
to all topic partitions involved in the transaction (including topic B and the consumer group's
offset topic). Brokers receiving commit markers mark the transactional batches as committed.

Crash between beginTransaction and commitTransaction: the new producer instance starts,
calls initTransactions with the same transactional.id. The coordinator sees a new epoch and
fences the old PID. The coordinator checks the state of the in-progress transaction in
__transaction_state and sees it was in ONGOING state. The coordinator issues an ABORT for that
transaction — it sends abort markers to all involved partitions. The uncommitted batches in topic
B are marked as aborted. Consumers with isolation.level=read_committed skip aborted batches.
The messages are effectively invisible.

- What is the transactional.id used for in practice, and why must it be unique per application
  instance but stable across restarts of the same logical instance?
- Follow-up: a consumer with isolation.level=read_uncommitted reads a transactional batch that
  is later aborted. What does the consumer see?

---

**Question 33 — Monitoring Kafka: Consumer Lag, Under-Replicated Partitions, Request Rate**

You are on-call for a Kafka cluster processing 200K messages/second. At 3 AM, an alert fires.
Design the monitoring dashboard and the runbook for three scenarios: (A) consumer lag on the
payment-processor group spikes to 500,000, (B) under-replicated partitions count goes from 0 to
12, (C) broker request rate drops from 200K/sec to 0 for broker 3. For each: what is the likely
cause, what commands do you run, and what is the remediation?

**Scenario A — Consumer lag spike:**

Likely causes: consumer crash-loop, slow message processing (CPU-bound model, slow external API),
message producing rate spiked beyond consumer processing capacity, consumer rebalance storm.

Commands: kafka-consumer-groups.sh --describe --group payment-processor shows per-partition lag,
current offset, log end offset, and which consumer instance owns each partition. Check consumer
logs for exceptions. Check broker CPU and network metrics for sudden throughput spikes.

Remediation: if crash-loop, fix the bug and redeploy. If slow processing, scale out the consumer
group (add instances up to the partition count). If message rate spiked, check the producer side
for an upstream event that generated a burst (e.g., a batch import, a traffic spike). If
rebalance storm, enable static group membership.

**Scenario B — Under-replicated partitions:**

Likely causes: one or more follower brokers are lagging behind the leader. Causes include: a broker
that is overloaded (high disk I/O from compaction or reassignment), a broker that restarted and is
catching up, network degradation between brokers, or a broker crash.

Commands: kafka-topics.sh --describe --under-replicated-partitions shows which partitions are
under-replicated and which replicas are out of sync. Check broker logs on the lagging replica for
I/O errors, OutOfMemoryError, or network exceptions. Check broker JVM GC logs.

Remediation: if a broker is catching up after a restart, wait — it will rejoin ISR when it catches
up to the high watermark. If a broker is overloaded, reduce compaction throttle or move some
partitions off that broker. If a broker has crashed, restart it or replace it and initiate
partition reassignment.

**Scenario C — Request rate drops to 0 for broker 3:**

Likely causes: broker process crashed, OOM kill, disk full (Kafka writes stop when disk is 95%
full), network interface failure, or ZooKeeper/KRaft connectivity loss.

Commands: SSH to broker 3, check process status (systemctl status kafka), check disk space
(df -h), check recent Kafka logs (/var/log/kafka/server.log). On the cluster: kafka-broker-api-
versions.sh --bootstrap-server broker3:9092 — if this times out, the broker is unreachable.

Remediation: if disk full, delete old log segments manually or increase disk. If OOM, check heap
settings (-Xmx). If crashed, restart the broker. Leaders on broker 3's partitions will have
already failed over to other ISR replicas (within the unclean.leader.election.enable window).
After broker 3 restarts, preferred leader election restores leadership to broker 3.

- Follow-up: consumer lag is 500,000 messages and growing. You scale the consumer group from 10
  to 20 instances. The topic has 10 partitions. Does the lag stop growing? Why or why not?

---

### Section B: Cross-Chapter Integration (Q34-Q42)

---

**Question 34 — Ch34 + Ch29: Kafka Log Compaction vs. LSM-Tree Compaction**

Kafka log compaction and LSM-Tree compaction in databases like RocksDB or Cassandra share a
similar name and a vaguely similar concept. Compare the two rigorously: what problem does each
solve, what is the mechanical process of each, and what are the performance costs of each?
A teammate claims "Kafka compaction is just like RocksDB compaction." Is that accurate?

LSM-Tree compaction: in a log-structured merge tree, all writes go to an in-memory memtable, which
is flushed to immutable SSTable files on disk (level 0). As SSTables accumulate, they are compacted:
multiple SSTables at level N are merged and sorted, producing fewer, larger SSTables at level N+1.
The purpose is to improve read performance (fewer SSTables to scan) and reclaim space from deleted
or overwritten keys. Compaction is CPU and I/O intensive — it involves reading multiple SSTables,
merging/sorting the key-value pairs, and writing the result as a new SSTable. The cost is a
background I/O amplification factor of 10-30x: for every byte written once, the compaction process
reads and rewrites it 10-30 times over its lifetime.

Kafka log compaction: the purpose is different — not to improve read performance (Kafka reads are
sequential, always fast), but to reclaim storage by removing earlier versions of the same key.
Kafka does not sort by key. It does not create a data structure that improves lookup speed. After
compaction, a consumer reading offset 0 still reads sequentially — it just encounters fewer records
because duplicate keys have been removed. Kafka compaction does not enable key-based random access.

The claim is inaccurate: they solve different problems. LSM compaction merges sorted levels to
improve read performance. Kafka compaction removes superseded key versions to reduce storage.
LSM compaction produces a searchable B-tree-like structure per level. Kafka compaction produces
a smaller sequential log. LSM compaction is triggered by SSTable count per level. Kafka compaction
is triggered by the dirty-to-total bytes ratio.

One meaningful similarity: both involve reading old data and writing a new, smaller representation
of it. Both are background processes that compete with foreground read/write operations for I/O.

- For a use case where you need both fast random key-value lookup AND event streaming, would you
  use Kafka with log compaction alone? What would you add?
- Follow-up: a compacted Kafka topic and a RocksDB instance are both used to store "latest user
  preferences." What can RocksDB do that the compacted Kafka topic cannot?

---

**Question 35 — Ch34 + Ch33: Scaling Consumer Groups Beyond Partition Count**

Your Kafka consumer group has 10 consumers for a topic with 10 partitions. You need to handle
10x the current message rate. A teammate proposes adding 90 more consumers to the group (100
total). Explain exactly what happens when you add the 91st consumer. Then design the correct
approach to handle 10x message rate while working within Kafka's partition-consumer constraints.

When you add the 91st consumer to a consumer group consuming a topic with 10 partitions: the
91st consumer through 100th consumer receive no partition assignment. Kafka's partition assignment
rule is hard: one partition can be assigned to at most one consumer within a consumer group at
any time. 10 partitions means 10 consumers can be active at most. Consumers 11 through 100 sit
idle, receiving empty poll results. They still maintain heartbeats and participate in rebalances,
adding overhead to the group coordinator, but they do zero useful work.

The correct approach to handle 10x message rate:

Option 1 — Increase partition count: increase the topic from 10 to 100 partitions and add 90
consumers. This is the primary Kafka scaling mechanism. Downside: partition count increase in a
live topic requires careful planning (it does not reshuffle existing messages, so key-based
routing changes meaning — messages that previously went to partition 3 for a given key may now
go to partition 37 after the repartition, breaking ordering guarantees). For topics with key-based
routing, increasing partitions while maintaining ordering is complex.

Option 2 — Scale consumer processing: instead of adding more Kafka consumers, make each consumer
process faster. Use a thread pool inside each consumer: the consumer thread polls Kafka and
dispatches messages to a local thread pool of 10 worker threads. 10 consumers x 10 internal
threads = effective parallelism of 100. Risk: offset management is harder (you must not commit an
offset until all earlier offsets in that partition have been processed by the thread pool).

Option 3 — Scale consumer infrastructure: if each consumer is CPU-bound and runs on a single-core
VM, vertically scale the VM. 10 consumers on 16-core VMs may process 10x as fast as 10 consumers
on single-core VMs.

- If you increase partitions from 10 to 100 in a live system with key=user_id partitioning, what
  happens to in-flight messages and ordering guarantees during the transition?
- Follow-up: is there a way to serve multiple consumer groups from the same 10-partition topic
  while each group gets the full throughput guarantee? Why or why not?

---

**Question 36 — Ch34 + Ch35: Lambda Architecture with Kafka**

Design a Lambda architecture using Kafka. The stream layer (Flink) processes events in real-time
and produces approximate results with low latency. The batch layer (Spark) reprocesses all events
every 24 hours and produces accurate results. How do you manage Kafka retention to support both
layers? What happens when Spark's accurate results differ from Flink's approximate results, and
how do you reconcile them in the serving layer?

Lambda architecture: two separate processing paths operating on the same source data. Stream layer:
Flink reads from Kafka continuously, computes approximate results (windowed aggregations, session
stats), writes to a "stream-results" store (e.g., Redis or a real-time database). Batch layer:
Spark reads the entire event history from Kafka every 24 hours, recomputes accurate results
(correct for late arrivals, deduplication, and any approximation errors), writes to a
"batch-results" store (e.g., a data warehouse). Serving layer: queries merge stream results and
batch results. For time windows that the batch layer has processed, serve batch results (accurate).
For recent time windows (past 24 hours), serve stream results (approximate).

Kafka retention for this design: Spark needs to read all events from the past 24 hours at
minimum. If Spark's job is slow and takes 6 hours to complete, the oldest events it reads were
30 hours old at job start. Set retention to 48 hours minimum. For resilience (Spark job failure
+ 24-hour retry), set retention to 72 hours. Cost: at 1 TB/day ingestion x RF=3 x 72 hours =
9 TB of storage across the cluster.

For historical reprocessing (Spark needs to recompute the past 6 months of data): Kafka retention
cannot hold 6 months. Archive all Kafka events to S3 in Parquet format using a Kafka Connect S3
sink. Spark reads historical data from S3, not Kafka.

Reconciliation in the serving layer: when Spark produces accurate results for a time window, the
serving layer must "upgrade" that window from stream (approximate) to batch (accurate). This is
typically done via a version timestamp: Spark writes results with batch_run_timestamp. The serving
layer queries: "for window W, if batch_run_timestamp exists and is recent, use batch result; else
use stream result." Care must be taken to ensure there is no visible "flicker" as the serving
layer transitions between the two sources.

- Follow-up: the Lambda architecture's main criticism is that you maintain two codebases — one
  Flink job and one Spark job — that must produce compatible results from the same input. The
  Kappa architecture proposes eliminating the batch layer and using only the stream layer with
  long-retention Kafka for reprocessing. What are the practical limits of the Kappa approach?

---

**Question 37 — Ch34 + Ch36: MirrorMaker 2 Failover and Offset Translation**

MirrorMaker 2 replicates Kafka topics from US-East (primary) to EU-West (DR). The US-East cluster
becomes unavailable. Consumers must failover and start reading from the EU-West cluster. Design
the offset translation and consumer group failover. What is the worst-case duplicate processing
window, and how do you bound it?

Offset translation problem: a message at offset 1000 in US-East may be at offset 997 in EU-West,
because MM2 replication is not guaranteed to preserve offsets. MM2 may batch messages differently.
EU-West is a fresh cluster that received the replicated data. Consumer group "order-processor" has
committed offset 1000 in US-East. After failover to EU-West, what offset should it start from?

MM2 solves this with an offset translation topic: "mm2-offset-syncs." MM2 records the mapping
between source cluster offsets and target cluster offsets. The mapping is approximate — MM2 records
a sync point for every 4096 messages (configurable). MirrorMaker 2 provides the
RemoteClusterUtils.translateOffsets() API that looks up the source offset and returns the
corresponding target offset by finding the nearest sync point at or before the committed offset.

Worst-case duplicate window: if the nearest sync point before US-East offset 1000 is at offset
900 (MM2 recorded a sync at every 100 messages), the consumer starts from EU-West's equivalent
of offset 900. Messages 900 to 999 that the consumer already processed in US-East are reprocessed.
Worst-case duplicates: 100 messages (1 sync interval). To reduce this, decrease the offset sync
interval in MM2 configuration (sync every 100 messages instead of 4096). This increases the
frequency of sync writes to the offset-syncs topic but reduces the worst-case duplicate window.

Consumer group failover procedure: (1) detect US-East unavailability via monitoring, (2) use
RemoteClusterUtils.translateOffsets() to compute target offsets for each partition, (3) use
kafka-consumer-groups.sh --reset-offsets --to-offset <translated_offset> on the EU-West cluster
to set the consumer group's starting position, (4) restart consumers pointing to EU-West.

- What is the worst-case message loss (as opposed to duplicates) that can occur during failover?
  Under what conditions is message loss possible even with MM2?
- Follow-up: after the US-East cluster recovers, you want to fail back. What is the failback
  procedure, and how do you handle messages that were produced to EU-West during the failover
  period (messages that do not exist in US-East)?

---

**Question 38 — Ch34 + Ch37: GDPR Deletion from an Immutable Kafka Log**

EU user events are stored in a Kafka topic with 7-day retention. A GDPR deletion request arrives
for user 123. The user's PII is embedded in 200 Kafka messages spread across 3 partitions over
the past 7 days. Kafka is immutable — you cannot delete or modify individual messages. Design
the compliant approach. Be specific about the technical mechanism, the audit trail, and what
happens to the messages after the user's key is deleted.

Approach 1 — Wait for retention expiry: do nothing. Messages expire in at most 7 days. GDPR's
"right to erasure" requires deletion "without undue delay," typically interpreted as within 30
days. 7-day retention satisfies this if the request is processed before the 7 days expire and
no other system has consumed and stored the data. This approach is fragile: messages produced
late in the 7-day window (e.g., day 6) persist for 1 day after the request; downstream consumers
may have already read and stored the PII elsewhere.

Approach 2 — Crypto-shredding (recommended): before writing to Kafka, encrypt all PII fields
using a per-user AES-256 key stored in a Key Management Service (KMS). Kafka messages contain
ciphertext, not plaintext PII. On GDPR deletion: delete the user's encryption key from KMS.
All 200 messages now contain undecryptable ciphertext. The bytes remain in Kafka but are
effectively meaningless without the key. Regulators widely accept that undecryptable ciphertext
does not constitute personal data.

Audit trail: log the deletion request: (user_id=123, deletion_requested_at=2026-06-15T10:00Z,
kms_key_deleted_at=2026-06-15T10:00:03Z, kafka_topic_has_ciphertext_only=true). Store the
audit record in an EU-resident durable store (not in Kafka, since Kafka's own retention would
eventually expire it).

Downstream handling: the user's PII was likely consumed from Kafka by downstream services and
stored in their own databases. Publish a "user.deletion.requested" event to a dedicated compliance
topic. Each downstream service subscribes, deletes or anonymizes its copy of the user's data,
and publishes a "user.deletion.confirmed" event with its service name. A compliance coordinator
service tracks confirmation from all known downstream services. Only when all have confirmed is
the deletion considered complete for regulatory purposes.

- What is the risk of approach 1 (wait for retention expiry) if the Kafka topic has a 30-day
  retention? Does it still comply with GDPR's "without undue delay" standard?
- Follow-up: a log compaction topic stores "latest user preferences" per user. The user's
  preferences record is the most recent record for key=user_123. Crypto-shredding makes the
  ciphertext unreadable. But the key "user_123" is itself visible in the Kafka log (keys are
  not encrypted by default). Is the visible key a GDPR compliance risk?

---

**Question 39 — Broker Failure During a High-Throughput Write**

Your Kafka cluster has 3 brokers. A topic has RF=3 and min.insync.replicas=2. Broker 1 is the
leader for partition 0. At 14:00, while processing 500K messages/second, broker 1's disk fills
up and the broker process stops accepting writes. Walk through the failure detection sequence,
the leader election, the ISR impact, and the producer behavior during the election window.
Specifically: what happens to producers using acks=all versus acks=1 during the ~10-second
election window?

Failure detection: Kafka brokers send heartbeats to the controller (the KRaft controller in modern
Kafka, or the ZooKeeper-elected controller in older versions). The heartbeat timeout is
controlled by zookeeper.session.timeout.ms (ZooKeeper) or broker.session.timeout.ms (KRaft),
typically 6-18 seconds. When broker 1 stops sending heartbeats, the controller detects the failure
after the timeout expires. During the detection window (up to 18 seconds), producers and consumers
attempting to connect to broker 1 receive connection errors.

ISR impact: broker 1 was in the ISR as leader. When it fails, the ISR shrinks from {1, 2, 3}
to {2, 3}. min.insync.replicas=2, so {2, 3} satisfies the minimum. The controller elects a new
leader from {2, 3} (first broker in ISR that is alive). Partition 0 now has a new leader on
broker 2.

Producer behavior with acks=all: the producer sends a batch to broker 1 (the leader). Broker 1 is
down. The producer's connection to broker 1 fails after connection.timeout.ms. The producer
refreshes metadata from another broker, discovers broker 2 is the new leader for partition 0, and
retries the batch to broker 2. During the metadata refresh and leader election window (10-30
seconds), the producer receives NotLeaderForPartition or LeaderNotAvailable errors. With retries
enabled (retries=MAX_INT, default in modern Kafka), the producer retries automatically. With
idempotence enabled, the retry is safe (duplicate detection via sequence numbers). With
enable.idempotence=false and retries > 0, duplicates are possible if the batch reached broker 1
before it crashed and was replicated to followers.

Producer behavior with acks=1: the producer sends a batch to broker 1. If broker 1 acknowledged
the batch (acks=1 means the leader acks before replicating), but then crashed before replicating,
the data is lost — it is not on brokers 2 or 3. This is the data loss scenario that acks=1 allows.
After election, the new leader broker 2 does not have that batch, and it is gone.

- Calculate: at 500K messages/second and a 15-second election window, how many messages are
  affected (in-flight or unacknowledged) during the leader election with acks=all versus acks=1?
- Follow-up: min.insync.replicas=2 and only 2 brokers are alive. A producer with acks=all sends
  a batch. The batch is written to both surviving brokers. Broker 2 then fails before acking.
  Now only 1 broker is alive. What happens to the producer?

---

**Question 40 — Kafka Topic Naming, Access Control, and Multi-Tenant Operations**

Your organization has 30 engineering teams each producing and consuming Kafka topics on a shared
cluster. No naming conventions exist. Topics include: "test", "data", "events", "orders", "orders2",
"orders-new", "orders-final", "orders-final-v2". Access control does not exist. A team's buggy
consumer joins the wrong consumer group and resets offsets on a production topic. Design the topic
naming convention, ACL strategy, and operational controls to prevent this class of incident in a
multi-tenant shared cluster.

Topic naming convention: enforce via a Kafka AdminClient interceptor that rejects topic creation
if the name does not match the pattern: {team}.{environment}.{domain}.{version}, e.g.,
payments.prod.orders.v1. This encodes team ownership (for ACL assignment), environment
(prevents dev consumers from accidentally reading prod), domain (business context), and version
(explicit versioning). Create a naming validation service called by the topic provisioning API
— teams do not create topics directly via kafka-topics.sh, they request creation via an internal
portal that enforces naming rules.

ACL strategy: use Kafka ACLs (Access Control Lists) backed by each team's service account.
Principle of least privilege: the payments team service account has WRITE access to
payments.prod.*.* topics and READ access only to topics it explicitly depends on. No team has
WRITE access to another team's topics. No team has the ability to delete topics or reset offsets
for topics they do not own. Consumer group naming follows the same convention:
{team}.{environment}.{domain}.{purpose}, e.g., payments.prod.orders.charge-processor. ACLs on
consumer group names: teams can only use consumer groups prefixed with their team name.

Operational controls: disable direct kafka-consumer-groups.sh --reset-offsets access in production.
All offset resets must go through a change management portal that requires: team ownership
verification, reason for reset, approval from a second team member, and an audit log entry.
The portal calls Kafka Admin API on behalf of the requesting team after verification.

- What monitoring do you put in place to detect when a new consumer group joins a production
  topic that does not match any known consumer group for that topic?
- Follow-up: a team needs to temporarily read another team's production topic to debug an
  integration issue. Design a time-bound access grant mechanism that automatically expires the
  ACL after 24 hours.

---

**Question 41 — Kafka in a Service Mesh: mTLS, Encryption, and Latency**

Your organization runs Kafka inside a service mesh (Istio). All service-to-service communication
is mTLS. The Kafka brokers are not part of the mesh — they use their own SASL_SSL authentication.
Producers and consumers are mesh-enrolled pods that must communicate with Kafka. Explain the
encryption and authentication path for a producer writing to Kafka. Then measure: at 500K
messages/second, what is the additional latency from mTLS handshakes, and how do session
resumption and connection pooling affect this?

Authentication path: the producer pod is in the Istio mesh. Outbound traffic from the pod first
hits the Envoy sidecar proxy. Since Kafka brokers are external to the mesh (not enrolled in Istio's
mTLS), Envoy cannot perform mTLS on the Kafka port — it passes the traffic through as TCP passthrough
for the Kafka port. The Kafka client itself then performs SASL_SSL authentication directly with the
Kafka broker. This means: Istio mTLS applies to service-to-service traffic within the mesh (e.g.,
producer service to a gateway service), but the Kafka connection uses Kafka-native SASL_SSL.

The distinction matters: traffic from the producer pod to the Kafka broker is encrypted and
authenticated via SASL_SSL, but it is NOT controlled by the Istio mesh. Istio cannot enforce
network policies, observe, or rate-limit the Kafka connection.

mTLS handshake latency: the TLS 1.3 handshake takes 1 RTT (round-trip time). At 1ms RTT
between producer and broker, the handshake adds 1ms. At 500K messages/second from a single
producer, connections are long-lived — the handshake occurs once per connection, not per message.
With connection pooling (Kafka producers use persistent TCP connections), the per-message overhead
is zero. The handshake cost is amortized over millions of messages per connection lifetime.

Session resumption (TLS session tickets or TLS 1.3 0-RTT): allows reconnections to skip the
full handshake by resuming a prior session. If a producer's connection to a broker drops and
reconnects, 0-RTT session resumption adds no round trips. However, 0-RTT has security tradeoffs
(replay attacks are possible) — most Kafka deployments disable 0-RTT and accept the 1 RTT
reconnection cost.

- What is the operational risk of running Kafka outside the service mesh when all other
  services are inside the mesh? How does this affect observability of Kafka traffic?
- Follow-up: a security audit requires end-to-end encryption of all Kafka messages including at
  the broker storage layer (encryption at rest). What Kafka configuration enables this, and
  what is the performance overhead?

---

**Question 42 — Kafka Capacity Planning for a New Product Launch**

You are planning Kafka capacity for a new product launch in 3 months. Expected traffic: 50K
users in the first hour, growing to 500K users by day 7. Each user generates 10 events/minute.
Events average 1 KB each. You need 7-day retention, RF=3, 5 consumer groups, and a starting
partition count that supports scale-out without repartitioning for at least 6 months. Design
the initial cluster and the scale-out plan.

Day 1, hour 1: 50K users x 10 events/minute / 60 = 8,333 events/second at 1 KB = 8.3 MB/sec
ingestion. Day 7: 500K users x 10 events/minute / 60 = 83,333 events/second at 1 KB =
83.3 MB/sec ingestion. 6-month projection (assuming 10x growth over 6 months from day 7 peak):
833,333 events/second = 833 MB/sec. This is the capacity target.

Partition count: design for 6-month peak. At 10 MB/sec per partition (conservative), 833 MB/sec
requires at least 84 partitions. Round up to 100 partitions for headroom. Start with 100 partitions
on day 1. This is excess capacity on day 1 (only 8.3 MB/sec total, trivially served by 100
partitions with 1 consumer each). Consumer group scaling: at day 1, 5 consumer groups need
at most 5 consumers each. At 6-month peak, 5 consumer groups need up to 100 consumers each.
Scale consumer count from 5 to 100 over time without ever touching partition count.

Broker sizing: at 6-month peak, write bandwidth 833 MB/sec + replication 2x = 2.5 GB/sec.
Read bandwidth: 5 consumer groups x 833 MB/sec = 4.2 GB/sec. Total: 6.7 GB/sec.
At 300 MB/sec usable per broker: 6.7 GB/sec / 300 MB/sec = 23 brokers needed. Start with
6 brokers (handles day 7 traffic at 83 MB/sec x 3 RF = 250 MB/sec across 6 brokers = 42 MB/sec
per broker — well within limits). Add brokers monthly as traffic grows. Kafka supports live broker
addition without downtime.

Storage: 833 MB/sec x 86,400 seconds/day x 7 days x 3 RF = 1,509 TB at 6-month peak. With 3:1
compression: 503 TB. At 30 TB per broker: 17 brokers needed for storage alone at 6-month peak.
Storage is the binding constraint at peak; broker count must reach at least 17 for storage even
if bandwidth would be satisfied with fewer.

Scale-out plan: month 1, 6 brokers, 100 partitions, 5 consumer instances per group.
Month 3, 10 brokers, no repartitioning, scale consumers to 30 per group. Month 6, 23 brokers,
same 100 partitions, consumers scaled to 100 per group. At month 6 if traffic exceeds 6-month
projection, evaluate partition increase and plan the repartitioning carefully.

- Follow-up: the product team tells you the launch will have a marketing push that may spike
  to 10x expected traffic for 2 hours on day 1. Design the burst handling strategy that does
  not require pre-provisioning 10x capacity permanently.
