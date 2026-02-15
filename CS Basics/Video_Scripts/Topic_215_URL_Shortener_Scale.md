# URL Shortener: Scale and Bottlenecks

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Your URL shortener goes viral. From 1,000 URLs to 100 million. From 100 reads per second to 100,000. What breaks first? The database. The cache. The code generator. Storage. Every component has a limit. Let's walk through what fails, and how to fix it. Design this system for the moment everyone shares your link.

---

## The Story

Growth feels great until it doesn't. One day you're fine. The next, a celebrity tweets your short link. Traffic spikes 1000x. Redirects slow to a crawl. Database connections exhausted. Users see timeout errors. They think the link is dead. They go somewhere else. The window to fix it is minutes, not days.

Think of it like a highway. One lane handles 1,000 cars per hour. Suddenly you need 100,000. You need more lanes (replicas), better on-ramps (caching), and no single toll booth (bottleneck). Scale is about adding lanes before the traffic arrives. Capacity planning: assume your biggest link will get 10 million clicks in an hour. Design for that. Then add margin. The cost of over-provisioning cache is small. The cost of an outage is huge.

---

## Another Way to See It

A single cashier at a grocery store. One customer at a time. Fine for a small town. But Black Friday? You need 20 cashiers, a fast line for express items, and a back room full of inventory. Your shortener needs the same: multiple "cashiers" (read replicas), a "express line" (cache), and enough "inventory" (storage + pre-generated codes) so you never run out.

---

## Connecting to Software

**Read-heavy.** 100:1 read-to-write ratio. Most traffic is redirects. Solution: cache layer (Redis). Aim for 99%+ cache hit rate. Hot URLs—the viral ones—live in cache. Cold URLs hit the database, get cached for next time. Add read replicas to the database. Distribute load across them.

**Write scaling.** If you use counter-based generation, the counter is a bottleneck. One service can't generate IDs fast enough for 10K writes/sec. Use Snowflake-style distributed IDs or pre-generated code pools. Pools: generate millions of codes in advance, store in a queue. Servers grab batches. No single point of contention.

**Storage.** 100M URLs at ~500 bytes each (short code, long URL, metadata) = 50GB. Manageable. Single database can hold it. Partition by short code hash if you need to shard later.

**Analytics.** Click tracking. Don't slow down the redirect. Write click events asynchronously to an analytics DB or queue. Process in the background. Redirect must stay under 100ms.

---

## Let's Walk Through the Diagram

```
                    SCALED READ PATH
┌─────────┐                    ┌──────────────┐
│  User   │ ─────────────────►│  Load        │
└─────────┘  100K req/sec      │  Balancer    │
       │                       └──────┬───────┘
       │                              │
       │         ┌────────────────────┼────────────────────┐
       │         │                    │                    │
       │         ▼                    ▼                    ▼
       │    ┌─────────┐         ┌─────────┐          ┌─────────┐
       │    │ Redis   │         │ Redis   │          │ Redis   │
       │    │ Cache   │         │ Cache   │          │ Cache   │
       │    │ (99%    │         │ replica │          │ replica │
       │    │  hit)   │         │         │          │         │
       │    └────┬────┘         └────┬────┘          └────┬────┘
       │         │ miss              │ miss               │ miss
       │         └───────────────────┼────────────────────┘
       │                             │
       │                             ▼
       │                       ┌──────────┐
       │                       │ DB Read  │
       │                       │ Replicas │
       │                       └──────────┘
       │
       └── 301 Redirect (from cache or DB)
```

Traffic hits load balancer. Multiple cache nodes. Cache miss? Read from DB replicas. Writes go to primary; reads spread across replicas. No single choke point. The load balancer spreads traffic. Cache replicas spread reads. Database replicas spread read load. Writes go to the primary. If the primary becomes the bottleneck, consider sharding the write path: partition by short code hash. Each partition has its own primary. Writes spread. The system scales horizontally. Add more cache nodes. Add more DB replicas. Add more API servers. The architecture supports it. Pre-generate codes in batches. A background job fills a Redis list or Kafka topic with millions of short codes. API servers pop from the pool when creating URLs. No lock contention. No single counter. Horizontal scaling for writes. The read path was always scalable. Now the write path is too. Analytics: do not block the redirect. Write click events to a queue. Async consumers update the analytics database. Click counts, referrers, timestamps. The redirect stays fast. Analytics catches up. Decouple fast path from background processing. Scale each independently. Decouple the critical path from the nice-to-have.

---

## Real-World Examples

**Bitly** at scale: Redis clusters for caching, sharded databases, pre-generated ID pools. **t.co** handles every Twitter link click—billions per day—with aggressive caching and global distribution. **Rebrandly** scales analytics separately from redirects; click data flows async so redirects stay fast.

---

## Let's Think Together

**"A short URL goes viral. 10 million clicks in one hour. How does your system handle it?"**

That URL is hot. It lives in cache after the first click. Every subsequent click: cache hit, redirect, done. No database. Redis can serve hundreds of thousands of reads per second per node. 10M in an hour = ~2,800/sec. One Redis node handles it. The key: cache the mapping immediately on first access. Hot URLs never touch the database after warm-up.

---

## What Could Go Wrong? (Mini Disaster Story)

Viral link. Cache evicts it (LRU, memory pressure). Next 100K requests hit the database. Same row. Same partition. Database melts. Cascading failure. Lesson: hot-key protection. Pin viral URLs in cache. Or use a multi-tier cache—L1 in-process, L2 Redis. Viral keys stay warm. Never let a single key take down your database.

---

## Surprising Truth / Fun Fact

At 100K reads per second, your shortener serves more redirects per second than many countries have people. You're running a small slice of the internet's plumbing. And it's still just: lookup, redirect. The infrastructure does the heavy lifting.

---

## Quick Recap

- Read-heavy: cache is critical; 99%+ hit rate, read replicas for DB.
- Write scaling: distributed ID generation or pre-generated code pools.
- Storage: 50GB for 100M URLs; partition if needed.
- Analytics: async; never slow the redirect.
- Viral key: cache aggressively; protect DB from hot-key storms. Consider pinning the top 1000 hottest URLs in cache with a longer TTL. Or use a multi-tier cache: L1 in-process for the absolute hottest, L2 Redis for the rest. Never let a single key take down your database.

---

## One-Liner to Remember

*Scale a shortener by caching the read path and distributing the write path—hot keys in cache, cold keys in DB.*

---

## Next Video

We shift gears. Rate limiters: the valve that controls API traffic. Algorithms, placement, and single-region design. See you there.
