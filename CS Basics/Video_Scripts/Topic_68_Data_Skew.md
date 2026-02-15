# What is Data Skew and How to Avoid It?

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

A school. Four classrooms. 25 students each. Equal. Balanced. But Room 1 gets all the athletes. Hyperactive. Noisy. Constant questions. The teacher is drowning. Room 2 gets all the quiet readers. They sit. Read. Maybe one question per hour. The teacher is bored. Same number of students. Completely different workload. That's data skew. Count is even. LOAD is not. Your database can have shards with equal row counts. But one shard does 80% of the work. That shard dies. The others yawn. Let me show you how to see it. And fix it.

---

## The Story

You've sharded. Each shard has roughly the same number of rows. 1 million. 1 million. 1 million. Beautiful. You think you're done. But here's the crazy part — Row count ≠ workload. Shard 1: 1 million rows. Mostly old users. Inactive. A few reads per day. Shard 2: 1 million rows. Celebrity accounts. Viral content. Millions of reads per second. Same count. Shard 2 is melting. Shard 1 is idle. That's **data skew** — uneven distribution of data OR workload across shards.

**Types of skew:**
- **Size skew:** One shard has more data. More rows. More bytes. Disk full. Others half-empty.
- **Access skew:** One shard gets more queries. Reads. Writes. CPU maxed. Others at 5%.
- **Write skew:** One shard gets most writes. Time-series? Latest shard. All writes. Others idle.

**Causes:** Bad partition key. Natural patterns. Zipf's law — the most popular item gets ~2x traffic as 2nd, ~3x as 3rd. Top 1% of items can be 50%+ of traffic. Temporal patterns. Latest data always hotter. New users. Recent orders. All hit the same shard.

**Detecting:** Monitor shard sizes. Query rates per shard. CPU, memory per shard. One shard 5x the others? Skew. Alerts. Dashboards. Know before users complain. Set thresholds. Automate. Don't rely on manual checks.

**Preventing:** High-cardinality partition key. Composite keys. Salt hot keys. Re-shard when needed. Choose for distribution. Not just convenience. Monitor from day one. Don't assume even distribution. Measure. Act before users notice.

---

## Another Way to See It

A restaurant. Four waiters. 20 tables each. Equal. But Waiter 1's section has the party of 20. Constant orders. Running. Waiter 2's section: couples. One order per table. Same table count. Waiter 1 collapses. Waiter 2 relaxes. Skew. Count ≠ load.

---

## Connecting to Software

**Data skew** = uneven distribution of data or workload. Shards should be balanced. Size. Access. Writes. When one dominates, you have skew.

**Detecting skew:**
- Shard sizes: bytes, row count. One 10x others? Size skew.
- Query rate: QPS per shard. One 10x others? Access skew.
- Write rate: one shard gets all writes? Write skew.
- CPU, memory: one shard maxed? Others low? Skew.

**Preventing skew:**
- **Partition key:** High cardinality. user_id over country. Even distribution.
- **Composite keys:** (user_id, date). user_id distributes. date sorts.
- **Salt hot keys:** celebrity:123 → celebrity:123:0, 123:1, ... Spread.
- **Re-shard:** When skew detected. Split hot shard. Redistribute. Ongoing maintenance. It's not one-time. Data grows. Patterns shift. Rebalance regularly.

---

## Let's Walk Through the Diagram

```
DATA SKEW: DETECTION

Shard 1    Shard 2    Shard 3    Shard 4
   │          │          │          │
 1M rows   1M rows   1M rows   1M rows   ← Size: even
   │          │          │          │
 100 QPS   100 QPS  50,000 QPS  100 QPS   ← Access: SKEW!
   │          │          │          │
  5% CPU    5% CPU   100% CPU   5% CPU   ← Shard 3: hot

Same row count. Shard 3 has celebrity data. Access skew.
One shard = bottleneck. Fix: salt, cache, replicate.
```

Monitor both size AND access. Count is not enough. Workload matters.

---

## Real-World Examples (2-3)

**1. Social media by country:** Partition by country. India shard: 500 million users. Iceland shard: 300,000. Size skew. India shard massive. Queries slow. Iceland idle. Fix: don't partition by country alone. Or: split India into multiple shards. India-1, India-2. Composite. Balance.

**2. E-commerce by product:** Partition by product_id. One product goes viral. That partition hot. Access skew. Fix: cache. Salt product reads. Replicas. Prepare for Zipf.

**3. Time-series by date:** Partition by date. Today's partition. All writes. Size even (today = one day). Write skew. One partition does everything. Fix: partition by (sensor_id, date). Or (user_id, date). Spread writes.

---

## Let's Think Together

Social media app. Partition by country. India shard has 500 million users. Iceland shard has 300,000. Is this skew? How do you fix it?

*Think about that.*

Yes. Size skew. India shard is 1,600x bigger. Disk. Memory. Query load. All concentrated. Fixes: (1) Don't partition by country. Use user_id. Global distribution. (2) Or: split large countries. India → India-1, India-2, ... India-10. By user_id range within India. (3) Or: separate shards for "tier 1" countries. India gets 10 shards. Iceland shares with others. Tiered sharding. Complexity. But balance.

---

## What Could Go Wrong? (Mini Disaster Story)

Ignore skew. Metrics show Shard 5 at 90% CPU. Others at 10%. "We'll fix it next sprint." Sprint passes. No fix. Then Prime Day. Shard 5 hits 100%. Throttles. Timeouts. Users see errors. "Site down!" Other shards? 80% idle. Capacity exists. Wrong place. Cascading failures. Shard 5 melts. Replication lag. Reads fail. One shard. Whole system suffers. Lesson: skew is not "someone else's problem." It's a ticking bomb. Fix early. Monitor. Act.

---

## Surprising Truth / Fun Fact

Zipf's law. In many natural systems, the most popular item gets about 2x the traffic of the 2nd most popular, 3x the 3rd, and so on. The top 1% of items can account for 50%+ of all traffic. Not equal. Never equal. Design for it. Assume skew. Build for it. The best systems expect uneven distribution. And handle it gracefully.

---

## Quick Recap (5 bullets)

- **Data skew** = uneven data or workload across shards. Size, access, or write skew.
- **Causes:** Bad partition key, Zipf's law, temporal patterns. Natural. Expected.
- **Detect:** Monitor sizes, QPS, CPU per shard. One 5x others? Skew.
- **Prevent:** High-cardinality key, composite keys, salt hot keys, re-shard.
- Ignore skew → one shard overloaded → cascading failures. Fix early. Monitor always.

---

## One-Liner to Remember

> Same student count. One room has athletes. One has readers. Load unequal. That's skew. Design for it.

---

## Next Video

Sharding. Partitioning. Another trade-off: JOINs get expensive. Cross-shard JOINs are painful. So you duplicate data. Put author name IN the book row. No JOIN. Fast. But duplicate. Denormalization. When to do it. When to run. Next.
