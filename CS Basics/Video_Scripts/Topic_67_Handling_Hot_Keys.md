# How to Handle Hot Keys: Caching, Splitting, Salting

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

Counter 7. Always packed. The supermarket manager has had enough. She tries three things. First: a big screen near the entrance. "Milk? Rs 55. Eggs? Rs 80. Bread? Rs 40." Common questions. Answered before people reach the counter. Half the crowd leaves. Second: she opens three more counters RIGHT next to 7. Spread the line. Same capacity. Better distribution. Third: she randomly sends people to other counters. "You — Counter 3. You — Counter 9." Distribute. All three work. Different strategies. Caching. Splitting. Salting. Let me show you how they translate to databases.

---

## The Story

A hot key. One partition. 10,000 reads per second. Melting. You need solutions.

**Solution 1: Caching.** Put the hot key's data in Redis. Or Memcached. Or local cache. When a request comes for that key, check cache first. Hit? Return. Done. No database. Miss? Fetch from DB. Store in cache. Next request? Cache hit. 90% of reads never touch the database. The hot shard gets 1,000 requests instead of 10,000. Survives. Simple. Effective. Trade-off: staleness. Cache has old data. Product price changed? Cache shows old price. TTL. Invalidation. Manage it.

**Solution 2: Splitting / Replication.** The hot partition is one. Split the load. Read replicas for that shard. Route reads to any replica. Writes go to primary. Reads spread across 5 replicas. 10,000 reads? 2,000 per replica. Manageable. Or: replicate the hot key data to multiple partitions. Write once. Read from any. More infrastructure. More complexity. But it works.

**Solution 3: Salting / Scattering.** One key. Too hot. Split the key. "celebrity:123" becomes "celebrity:123:0", "celebrity:123:1", ... "celebrity:123:9". Ten partitions. Write? Pick one randomly. Or round-robin. Read? Query all 10. Merge. Fan-out. The load spreads. 10,000 reads? 1,000 per partition. Trade-off: reads get expensive. One logical key. Ten physical keys. Ten queries. Merge. Complexity. But hot partition? Gone.

Choose based on your case. Cache for read-heavy. Split for moderate. Salt for extreme. Or combine.

---

## Another Way to See It

A popular food stall. One counter. Huge line. Option 1: Menu board. "Price: Rs 50." Many people see it and leave. Don't need to order. Cache. Option 2: Open more windows. Same stall. More counters. Split. Option 3: Random assignment. "You go to window A. You to B." Spread. Salting. Same problem. Three solutions. Different costs.

---

## Connecting to Software

**Caching:** Redis, Memcached, local cache. Key → value. TTL. Invalidate on write. Simple. Fast. Stale risk. Best for: read-heavy, acceptable staleness. Product catalog. User profiles. Session data.

**Splitting/Replication:** Read replicas for hot shard. Or materialize hot key to multiple partitions. Write to one. Read from many. Best for: moderate hot, need consistency. More infra. More cost.

**Salting:** Append random suffix. Key → key:0, key:1, ... key:N. Writes: pick one. Reads: query all N. Merge. Best for: extreme hot. Viral. Willing to pay read cost. Used by: high-scale systems. Instagram. Facebook.

**Trade-offs:** Caching = fast, stale. Splitting = more machines, consistent. Salting = complex reads, even distribution. Balance.

---

## Let's Walk Through the Diagram

```
HANDLING HOT KEYS: THREE STRATEGIES

1. CACHING
   Request → [Cache] → Hit? Return. Miss? → [DB] → Store in cache
   90% cache hit = 10% DB load. Hot key survives.

2. SPLITTING
   Hot Shard → Replicas R1, R2, R3, R4, R5
   Reads: any replica. Writes: primary.
   10,000 reads → 2,000 per replica. Spread.

3. SALTING
   Key "celebrity:123" → "celebrity:123:0" ... "celebrity:123:9"
   Write: pick one (e.g. random). Read: query all 10, merge.
   Load divided by 10. Reads 10x more expensive.
```

Each strategy reduces load on the hot partition. Different mechanisms. Different costs.

---

## Real-World Examples (2-3)

**1. Instagram viral posts:** Caching. Redis. Hot post data cached. Millions of reads. Cache absorbs. DB survives. Plus: they detect hot keys in real-time. Monitor access patterns. Proactively cache before meltdown. Smart.

**2. Amazon product pages:** Caching. CDN. Product data cached at edge. Hot product? Served from cache. DB sees fraction of traffic. Plus: they use read replicas. Multiple layers. Defense in depth.

**3. Twitter celebrity tweets:** All three. Cache for reads. Read replicas. And salting for write-heavy cases. Tweet ID might be fanned out. Likes. Retweets. Counters. Salted. "tweet:123:likes:0" through "tweet:123:likes:99". Merge for count. Write load spread. Complex. Necessary at scale.

---

## Let's Think Together

Viral product on Amazon. 10,000 reads per second on ONE product page. Which technique would you use first — and why?

*Pause. Think about it.*

**Caching.** First. Always. Product data changes rarely. Price. Description. Images. Cache for 5 minutes. 10 seconds. Whatever acceptable. 90%+ cache hit rate. 10,000 reads → 1,000 DB reads. Or less. Simple. Cheap. Deploy Redis. Done. If still hot? Add read replicas. Splitting. Last resort: salting. Complex. Only if cache + replicas aren't enough. Start simple. Scale complexity when needed.

---

## What Could Go Wrong? (Mini Disaster Story)

Over-salting. Hot key. Solution: salt into 100 partitions. Spread. Good. But reads? Now you query 100 partitions for ONE logical key. Merge. 100x read cost. Latency explodes. 100 round-trips. Or parallel. Still expensive. The hot partition is gone. But now every read is 100x slower. Under-salting? 10 partitions. Still hot. 1,000 reads each. Melts. Balance. 10-20 partitions often enough. Don't over-salt. Don't under-salt. Profile. Measure. Tune.

---

## Surprising Truth / Fun Fact

Instagram uses both caching and replicated hot-key detection. They don't wait for meltdown. They monitor key access patterns in real-time. See a key heating up? Proactively cache. Route to more replicas. Detect before throttle. Prevention over cure. The systems learn. Adapt. Hot keys are inevitable at scale. The response is what separates the best from the rest.

---

## Quick Recap (5 bullets)

- **Caching:** Redis, Memcached. Hot key in cache. Most reads never hit DB. Simple. Stale risk.
- **Splitting:** Read replicas. Or replicate data. Spread reads. More infra. Consistent.
- **Salting:** Key → key:0, key:1, ... key:N. Writes pick one. Reads query all. Merge. Complex. Effective.
- **Trade-offs:** Cache = fast, stale. Split = infra, consistent. Salt = complex reads, even load.
- Balance. Don't over-salt. Start with cache. Scale when needed.

---

## One-Liner to Remember

> Screen for common answers. Open more counters. Randomly redirect. Cache. Split. Salt. Three ways to tame the hot key.

---

## Next Video

Hot keys are one symptom. Underneath: uneven distribution. Data skew. Size skew. Access skew. What causes it? How to detect it? How to prevent it? The classroom analogy. Next.
