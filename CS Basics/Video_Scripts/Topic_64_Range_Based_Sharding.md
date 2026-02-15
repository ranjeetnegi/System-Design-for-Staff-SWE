# Range-Based Sharding Explained

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

An office filing cabinet. Four drawers. Drawer 1: customer names A through F. Drawer 2: G through L. Drawer 3: M through R. Drawer 4: S through Z. You need "Priya Sharma." Which drawer? Three. M through R. You open it. There she is. You need everyone from "Kumar" to "Patel." Drawers 2 and 3. Simple. Predictable. No magic. No hashing. Just ranges. That's range-based sharding. But here's the catch — what if 60% of your customers have names starting with S? Drawer 4 explodes. The others sit empty. Range = easy. Range = dangerous. Let me show you.

---

## The Story

A filing cabinet. Four drawers. You split by first letter of last name. A-F in drawer 1. G-L in drawer 2. M-R in drawer 3. S-Z in drawer 4. Simple. Logical. You want "Priya"? Drawer 3. You want "all customers from K to N"? Drawers 2 and 3. Range queries are EASY. You know exactly which drawers to open. No scanning everything. That's range-based sharding.

In databases: split data into ranges. IDs 1-1000 → Shard 1. 1001-2000 → Shard 2. 2001-3000 → Shard 3. Or timestamps. January → Shard 1. February → Shard 2. Or alphabetic. A-F, G-L, M-R, S-Z. The partition key has order. Ranges make sense.

**Great for range queries:** "Give me all orders from January to March." Go to the January-March shards. Don't touch the rest. "Users with names A through C." One shard. Efficient. Hash-based? "All orders Jan-Mar" — you'd have to scan EVERY shard. Hash destroys order. Range preserves it.

But here's where things go WRONG. Uneven distribution. Most users have names starting with S. Sharma. Singh. Smith. Patel. Drawer 4 has 60% of the data. It's massive. Slow. Overloaded. Drawers 1, 2, 3 are tiny. Wasted capacity. One hot shard. The rest idle. That's the trade-off. Range = range queries work. Range = distribution can be terrible.

---

## Another Way to See It

A library split by Dewey decimal. 000-199: General. 200-399: Religion. 400-599: Language. 600-699: Technology. Technology section? Packed. Everyone wants programming books. Religion? Quiet. Same number of "ranges." Completely different sizes. Range-based. Predictable routing. Unpredictable load.

---

## Connecting to Software

**Range-based sharding:** Data split into contiguous ranges. Partition key has order. 1-1000, 1001-2000. Or Jan, Feb, Mar. Or A-F, G-L.

**Pros:**
- **Range queries:** "Orders from Jan to Mar" → hit only those shards. Efficient.
- **Easy to understand:** No hash. Just "which range does this fall in?"
- **Predictable routing:** Lookup table or simple comparison. Fast.

**Cons:**
- **Uneven distribution:** Natural data skew. Names. Dates. One shard gets most.
- **Hot shard risk:** Time-series? Latest range gets ALL writes. Old ranges idle.

**Versus hash-based:** Hash = even distribution, but NO range queries. Range = range queries, but uneven. Trade-off. Know your data. Know your queries.

---

## Let's Walk Through the Diagram

```
RANGE-BASED SHARDING

Partition key: customer_name (last name)

  Shard 1        Shard 2        Shard 3        Shard 4
  A - F          G - L          M - R          S - Z
    │              │              │              │
    │              │              │              │
  1000 rows      800 rows      1200 rows      5000 rows  ← Hot!
    │              │              │              │
  "Ahuja"        "Gupta"        "Patel"        "Sharma"
  "Bhatia"       "Kapoor"       "Mehta"        "Singh"
  ...            ...            ...            ...

Query: "Customers G through P"  →  Shards 2 + 3 only. Efficient!
Distribution: Shard 4 overloaded. Skew. Problem.
```

Step 1: Define ranges. Step 2: Assign each row to range by partition key. Step 3: Range query? Identify which shards. Step 4: Query only those. Skip the rest. But watch the distribution.

---

## Real-World Examples (2-3)

**1. HBase / Bigtable:** Range-based partitioning. Rows have keys. Key ranges go to different region servers. They auto-split: when a region gets too big, split it. Dynamic. Range queries native. "Scan from key A to key B." Fast.

**2. MongoDB:** Sharding. Can use range or hash. Range for time-series: "logs from last hour" — one shard. But latest shard gets all writes. Hot. Common pitfall.

**3. MySQL:** Manual range sharding. user_id 1-1000000 → DB1. 1000001-2000000 → DB2. Simple. But user growth might be uneven. New users? Latest range. Monitor.

---

## Let's Think Together

Time-series data. IoT sensors. Millions of readings per day. Shard by time range. January in Shard 1. February in Shard 2. March in Shard 3. Good or bad?

*Pause. Think about it.*

BAD. Here's why. All NEW writes go to the current month's shard. February gets 100% of writes. January? Idle. December? Idle. One shard handles everything. Hot shard. Bottleneck. Time as partition key = always hot. Better: partition by sensor_id. Or (sensor_id, date). Spread writes. Use date as sort key within partition. Don't make date THE partition. Range on time is tempting. Dangerous for writes.

---

## What Could Go Wrong? (Mini Disaster Story)

Log storage system. Shard by date. Jan 1 → Shard 1. Jan 2 → Shard 2. Clean. Then a virus. Logs explode. Millions per second. All today's date. All hit ONE shard. That shard melts. Disk full. Writes fail. "Why is our logging broken?!" Because the hottest data — the most recent — always hits the same shard. Range on timestamp. Classic mistake. Fix: shard by (service_id, date) or hash the log ID. Spread the load. Don't put all "today" in one place.

---

## Surprising Truth / Fun Fact

HBase and Bigtable use range-based partitioning. They don't just set ranges once. They auto-split. When a region (shard) gets too big — say 10 GB — they split it in half. New ranges. Dynamic. The system adapts. Growth happens. Ranges split. Balance maintained. Elegant. Most systems do it manually. HBase does it automatically.

---

## Quick Recap (5 bullets)

- **Range-based:** Split by ranges. 1-1000, 1001-2000. Or A-F, G-L. Order preserved.
- **Pros:** Range queries efficient. "Jan to Mar" = few shards. Easy to understand.
- **Cons:** Uneven distribution. Skew. Hot shard risk. Time = latest shard gets all writes.
- **vs Hash:** Range = range queries, uneven. Hash = even, no range queries. Trade-off.
- HBase auto-splits ranges when they grow. Dynamic. Smart.

---

## One-Liner to Remember

> Drawers A-F, G-L, M-R, S-Z. Easy to find. Easy to range query. But if everyone's name starts with S? One drawer explodes.

---

## Next Video

Hash = reshuffle on add. Range = skew. Is there a way to add shards without moving everything? A ring. Servers on a circle. Add one — only nearby data moves. Consistent hashing. The game-changer. Next.
