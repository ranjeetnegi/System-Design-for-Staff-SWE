# Leader-Follower Replication (Detailed)

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Breaking news. The main anchor reads it first. Live. In the studio. Three assistant anchors—in Mumbai, Delhi, Bangalore—watch the feed. They repeat the news to their local audiences. The main anchor controls the narrative. The assistants follow. Same story. Same moment. If the main anchor's studio catches fire? One assistant takes over. Becomes the new main anchor. But during the switch—those few seconds—there might be silence. Or repeated content. That's leader-follower replication. One leader. Many followers. Writes go to the leader. Followers replicate. Simple. Powerful. Let me walk you through the details.

---

## The Story

**Leader-follower** (also called primary-replica, master-slave): One node is the **leader**. All writes go there. The leader applies changes, writes to its write-ahead log (WAL), and sends the log to **followers**. Followers apply the same changes in the same order. Reads can go to the leader or followers. Leader reads = always fresh. Follower reads = might be slightly behind. Replication lag.

**How writes propagate:** Client writes to leader → Leader writes to WAL (durable) → Leader sends WAL entries to followers → Followers apply in order → Followers send ACK → Leader considers commit. **Synchronous followers:** Leader waits for ACK from N followers before responding. Safe. No data loss if those N fail. But slow. **Asynchronous followers:** Leader doesn't wait. Responds immediately. Fast. But if leader fails before replication, data loss. Trade-off.

**Failover:** Leader crashes. (1) Detect: heartbeat timeout, health checks. Might take 10-30 seconds. (2) Elect new leader: usually the most up-to-date follower. The one with the most recent WAL entries. (3) Reconfigure: point clients to new leader. DNS update, config change, or service discovery. (4) Old leader rejoins (if it recovers) as follower. During failover: unavailable window. Seconds to minutes. Plan for it. Applications should retry. Use exponential backoff. Treat failover as normal, not exceptional. It will happen. Design for it.

---

## Another Way to See It

Think of a head chef and line cooks. Head chef creates the recipe. Writes it down. Line cooks get copies. They execute. Same dish. Same order. If the head chef goes home sick, the most experienced line cook takes over. Same kitchen. New leader. The recipes (data) flow from one source. That's leader-follower. Centralized control. Simple to reason about.

---

## Connecting to Software

**Used by:** PostgreSQL (streaming replication), MySQL (replication), MongoDB (replica sets), Redis (replication), Kafka (leader per partition). Most relational databases. Industry standard for "one write location." If you're building a system that needs replication, leader-follower is where most teams start. It's well-understood. Tooling exists. Operationally proven. Only move to multi-leader or other patterns when you've hit the limits of single-leader.

**Sync vs async:** Sync = strong consistency, higher latency. Async = lower latency, replication lag, possible data loss on leader failure. Many systems offer both: sync for critical writes, async for the rest. Or: sync to one follower (semi-sync), async to others. Compromise.

---

## Let's Walk Through the Diagram

```
    LEADER-FOLLOWER REPLICATION

    WRITE PATH:
    Client ──► Leader ──► WAL (disk)
                │
                ├──► Follower A (apply, ACK)
                ├──► Follower B (apply, ACK)
                └──► Follower C (apply, ACK)
                │
                └──► "Done" (after sync) or immediate (async)

    READ PATH:
    Client ──► Leader (always fresh)
         ──► Follower (might be behind by seconds)

    FAILOVER:
    Leader ● ──X (crash)
    Follower A ○  Follower B ○  Follower C ○
         │            │              │
         └────────────┴──────────────┘
               Elect B as new Leader ●
```

The diagram shows: single write path. Multiple read paths. Failover = promote one follower. Simple topology. Easy to understand. Hard to scale writes (single leader bottleneck). But reads scale—add followers. For read-heavy workloads, leader-follower is perfect. One writer. Many readers. Add replicas until read capacity is enough. For write-heavy workloads, you'll hit the leader limit. That's when you consider sharding or multi-leader. But start with leader-follower. It solves 80% of replication needs.

---

## Real-World Examples (2-3)

**Example 1: PostgreSQL.** Primary + replicas. WAL streaming. Sync or async. Failover: Patroni, Stolon, or manual. Industry standard. **Example 2: MongoDB replica set.** One primary. Secondaries replicate. Automatic failover. Elect new primary from secondaries. Used by millions of apps.

**Example 3: Kafka.** Each partition has one leader. Replicas follow. Writes go to leader. Reads can go to leader or in-sync replicas. Leader dies? New leader elected. Per-partition. Scales horizontally by adding partitions. Kafka gets write scale not by multi-leader but by sharding: many partitions, each with its own leader. Same leader-follower pattern. Applied per partition. The principle scales. The implementation multiplies it.

---

## Let's Think Together

Leader crashes. Follower A is 2 seconds behind. Follower B is 10 seconds behind. Who becomes the new leader?

Follower A. Most up-to-date. Smallest gap. When you promote, you want to minimize data loss. Follower A has more of the leader's data. Follower B is further behind. Promote A. B will sync from A. Those 2 seconds of data on the old leader? If they weren't replicated to any follower—lost. Unless you had sync replication to at least one. That's the trade-off: async = fast but risk of loss. Sync = safe but slower. Choose based on durability needs.

---

## What Could Go Wrong? (Mini Disaster Story)

A company ran MySQL with async replication. Leader in DC1. Followers in DC2. Leader crashed. Promoted a follower. But the follower was 30 seconds behind. Last 30 seconds of writes? Gone. Orders. Payments. Users thought they had paid. System said they hadn't. Chaos. They switched to semi-sync: leader waits for at least one follower. Slower. But no silent data loss. Lesson: async is convenient. Until it isn't. Know your durability requirements.

---

## Surprising Truth / Fun Fact

The "master-slave" terminology is being phased out. "Leader-follower" and "primary-replica" are preferred. Same concept. Better language. PostgreSQL, Kubernetes, GitHub—many projects have switched. The technique is decades old. The names evolve. The idea stays: one writes, many follow.

---

## Quick Recap (5 bullets)

- **Leader-follower:** One leader for writes. Followers replicate. Reads from leader or follower (with lag).
- **Write path:** Leader → WAL → followers apply → ACK (sync) or fire-and-forget (async).
- **Sync** = safe, slow. **Async** = fast, risk of data loss on leader failure.
- **Failover:** Detect → elect most up-to-date follower → reconfigure clients.
- **Single write bottleneck.** Reads scale. Writes don't. For write scale, consider multi-leader or sharding.

---

## One-Liner to Remember

**Leader-follower: One anchor reads the news. The rest repeat it. Simple. When the main one falls, the most up-to-date assistant takes over.**

---

## Next Video

Next: **Multi-leader replication.** Two editors in different cities. Both publish. When they sync—conflicts. Which version wins? The power and the pain of multiple writers. See you there.
