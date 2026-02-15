# How to Measure Cache: Hit Rate and Miss Rate

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A student has an exam tomorrow. She keeps notes on her desk—her cache. Ten questions on the exam. She finds answers for eight without opening a textbook. Two she has to look up. Her "hit rate" is 80%. If it were 20%, her cache would be useless. She'd always be reaching for the textbook. Your cache works the same way. Let's measure it.

---

## The Story

Imagine a student studying for finals. Her desk is her cache. Textbooks are her database. On exam day, ten questions appear.

For eight questions, she glances at her desk. Notes are right there. She writes the answer. No textbook needed. Fast.

For two questions, her desk has nothing. She opens the textbook. Slower. But she gets the answer.

Eight out of ten from the desk. That's an 80% hit rate. Her cache—the desk—is doing its job. She spent less time opening textbooks. More time writing answers. Efficiency. That's what cache gives you.

If her hit rate were 20%? She'd be opening the textbook for almost everything. The "cache" wouldn't help. She might as well not have notes at all.

---

## Another Way to See It

A librarian. Popular books are on a display rack near the entrance—the cache. A patron asks for a book. If it's on the display rack, the librarian grabs it in seconds. That's a hit. If it's not, she walks to the stacks. That's a miss.

At the end of the day: 95 books from the display rack, 5 from the stacks. Hit rate = 95%. The display rack is earning its place.

If 80 books came from the stacks? Hit rate = 20%. The display rack is useless. Wrong books. Wrong strategy.

---

## Connecting to Software

**Hit rate** = Hits / (Hits + Misses).  
**Miss rate** = 1 - Hit rate = Misses / (Hits + Misses).

Example: 9,500 cache hits, 500 misses. Hit rate = 9,500 / 10,000 = 95%. Miss rate = 5%.

**What's good?**  
- Above 90%: cache is helping. Most reads avoid the database.  
- Above 95%: excellent. You're in the sweet spot. Cache is doing heavy lifting.  
- Below 50%: cache is probably not worth the complexity. You're hitting the database too often anyway. Either fix the cache strategy or accept that this workload doesn't cache well.

**What affects hit rate?**

1. **TTL too short** — Data expires before it's reused. Users request it again. Miss.  
2. **Cache too small** — Evictions. Popular data gets kicked out to make room.  
3. **Poor key design** — Keys too specific. Same data cached under different keys. Duplication and wasted space.  
4. **Access pattern** — Random accesses. No reuse. Every request is different. Low hit rate by nature. Think of a search engine: users search for different things. Hard to cache. Compare to a homepage: same content for millions. Easy to cache. Your access pattern determines your ceiling. Optimize key design and TTL for the pattern you actually have.

---

## Let's Walk Through the Diagram

```
Request flow with hit/miss tracking:

  Request ──► Check Cache
                  │
        ┌────────┴────────┐
        │                 │
      HIT              MISS
        │                 │
   Return data      Fetch from DB
   (fast!)               │
                     Store in cache
                        │
                     Return data
                     (slower)

  Metrics:
  hits = 9,500
  misses = 500
  hit_rate = 9,500 / 10,000 = 95%
```

---

## Real-World Examples

**1. Redis INFO stats**  
Redis exposes `keyspace_hits` and `keyspace_misses`. Hit rate = hits / (hits + misses). Monitor this in your dashboard. Alert when it drops below 90%.

**2. Application-level metrics**  
Instrument your code. Increment a counter on cache hit. Increment another on miss. Export to Prometheus, Grafana, or your APM. Graph hit rate over time. Watch for sudden drops.

**3. E-commerce product pages**  
Popular products get high hit rates. Long-tail products get more misses. Segment metrics: hit rate for top 1,000 products vs. the rest. Optimize each segment differently.

---

## Let's Think Together

Your cache hit rate drops from 95% to 60% overnight. What could have happened?

Think. Pause.

Possibilities: (1) Someone deployed a change that broke cache keys. (2) TTL was reduced. (3) Traffic pattern shifted—new viral content, old cache entries evicted. (4) Cache cluster was resized. Fewer nodes, more evictions. (5) A bug: cache writes failing silently. Cache slowly emptied. (6) Database migration or new feature. New query patterns. Cache never warmed up for them.

Investigate. Check deploy logs. Compare TTL config. Look at eviction metrics. Trace a few misses to see the key pattern. The hit rate is your cache's report card. When it drops, something changed. Your job is to find out what. Build dashboards. Set up alerts. Review hit rate in your weekly metrics. It's one number that tells you if your caching strategy is working or wasting resources.

---

## What Could Go Wrong? (Mini Disaster Story)

A startup. Cache hit rate was 98%. Great. They grew. Traffic tripled. Nobody resized the cache. Memory pressure increased. Eviction policy kicked in. LRU evicted popular keys. Hit rate crashed to 40%. Database got hammered. Latency spiked from 10ms to 2 seconds. Customers complained. Site felt broken.

The fix: monitor hit rate. Set an alert. When it drops, investigate. Auto-scale cache memory or add nodes. Size the cache for peak load, not average.

---

## Surprising Truth / Fun Fact

Facebook's Memcache hit rate is above 99%. That means only 1 in 100 requests actually reaches the database. The cache *is* the system. The database is the backup. When your cache is that good, you've built a read-through cache that effectively is your primary data source for reads. That's the power of a well-tuned cache.

---

## Quick Recap (5 bullets)

- Hit rate = hits / (hits + misses). Miss rate = 1 - hit rate.
- Good hit rate: >90%. Great: >95%. Below 50%: cache probably not helping.
- What hurts hit rate: TTL too short, cache too small, poor key design, random access patterns.
- Monitor via Redis INFO, application metrics, dashboard alerts.
- Alert when hit rate drops. Investigate TTL, evictions, traffic shifts, and code changes. Treat hit rate like latency or error rate—a first-class metric. When someone asks "is our cache working?" hit rate is the answer. No guesswork. One number. Clear signal.

---

## One-Liner to Remember

*Hit rate tells you if your cache is earning its keep—above 95% you're winning; below 50% you're wasting memory.*

---

## Next Video

Next: When caching backfires. Stale data, complexity, and the day the weather app lied. Topic 93: When Caching Hurts.
