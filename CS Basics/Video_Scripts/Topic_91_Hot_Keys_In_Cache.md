# Hot Keys in Cache: Replication vs Local Cache

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

Imagine a food court with 20 stalls. One stall sells the BEST biryani in town. Five hundred people are lined up. The other nineteen stalls? Empty. The biryani stall is on fire. The chef is drowning in orders. What do you do? Two solutions: open more biryani counters, or put biryani on every table. In caching, this exact problem is called a hot key. Let's crack it.

---

## The Story

Picture a busy food court. Fifteen stalls sell different food. But one stall—the biryani stall—has gone viral. Everyone wants THAT biryani.

Five hundred people. One counter. One chef. Chaos.

**Solution 1: Replication.** You open five more biryani counters across the food court. Same recipe. Same biryani. Now the line splits across six counters. Each counter serves 80 people instead of 500. Problem solved.

**Solution 2: Local cache.** Every table gets a small tray of biryani pre-served. Customers don't wait in line at all. They grab from their table. Zero queuing.

Both work. But they feel very different. Replication spreads the load. Local cache removes the need to queue entirely.

---

## Another Way to See It

Think of a viral tweet. One post gets 10 million views in an hour. When someone loads that tweet, your system fetches it. If the tweet data is cached under ONE key—like `tweet:12345`—that single key gets hit 100,000 times per second.

One Redis node can handle maybe 80,000 to 100,000 operations per second. One key. One node. All traffic hitting it. That node becomes a bottleneck. CPU maxed. Network saturated. Latency spikes. Users see timeouts.

That key is HOT. Too hot for one node.

---

## Connecting to Software

In caching, a hot key is one key accessed far more often than others. Viral content. Homepage banners. Trending products. Login tokens for a celebrity account.

Your cache is sharded. Keys are distributed across nodes by hash. But if ONE key gets 100K reads per second, that ONE node holds that key. It cannot spread the load by design. Hash says: this key lives here. All traffic goes there.

**Solution 1: Replicate the key across multiple cache nodes.**

Add a random suffix to the key: `homepage:banner` → `homepage:banner:0`, `homepage:banner:1`, ... `homepage:banner:4`. Store the same value in five keys across five nodes. When reading, pick a random suffix. Traffic spreads. No single node drowns.

**Solution 2: Local in-process cache.**

Use a HashMap, Guava cache, or Caffeine on each application server. Store the hot key in memory locally. Most reads never leave the server. No network. No Redis. Sub-millisecond latency.

**Solution 3: Tiered caching.**

L1 = local cache on each app server (fast, small). L2 = Redis (shared, larger). Check L1 first. Miss? Check L2. Miss? Hit the database. Hot keys live in L1. Cold keys stay in L2.

---

## Let's Walk Through the Diagram

```
WITHOUT hot key handling:
                    ┌─────────────────┐
  100K req/sec  ──► │  Redis Node A   │  ◄── ONE node, ONE key
                    │  (key: banner)  │      Overwhelmed!
                    └─────────────────┘

WITH replication (random suffix):
  20K ──► Redis Node A (banner:0)
  20K ──► Redis Node B (banner:1)
  20K ──► Redis Node C (banner:2)
  20K ──► Redis Node D (banner:3)
  20K ──► Redis Node E (banner:4)
  Load spread across 5 nodes!

WITH local cache:
  App Server 1: HashMap has "banner" → serves from memory
  App Server 2: HashMap has "banner" → serves from memory
  ...
  Redis rarely hit for this key.
```

---

## Real-World Examples

**1. Twitter Trending Topics**  
Trending topics are accessed millions of times per minute. One key per region. Too hot for a single Redis node. Twitter uses local cache on every application server. Redis is the fallback. The local cache absorbs the storm.

**2. E-commerce Homepage**  
A big sale banner. Same image, same JSON for everyone. One key. Millions of hits. Replicate with suffix: `banner:0` through `banner:N`. Or cache it locally on each web server. Both patterns are used.

**3. Celebrity Profile**  
One celebrity logs in. Their profile and feed get cached. Millions of followers view it. That profile key is scorching hot. Local cache + replication. Standard approach.

---

## Let's Think Together

You have a homepage banner cached in Redis. One key. Traffic spikes to 500,000 reads per second. One Redis node maxes at 100K ops/sec. What do you do?

Pause. Think. 

Replication with random suffix: create `banner:0` to `banner:4`, store the same value in each. Round-robin or random selection. Five nodes share the load. Each handles 100K. Done.

Or: add a local cache. Each of your 50 app servers holds the banner in memory. Most reads never touch Redis. Redis only fills the cache on cold start or invalidation.

---

## What Could Go Wrong? (Mini Disaster Story)

A news site. Breaking story. One article key explodes to 200K reads/sec. Redis node holding that key dies. Too much load. OOM. Replica promotes. But the replica gets the same storm. It dies too. Cascade failure.

Worse: someone invalidates the cache. All app servers lose their local copy. They all rush to Redis at once. Cache stampede. Database gets hammered. Site goes down.

The fix: hot key detection. Monitor key access frequency. When a key exceeds threshold, proactively replicate or promote to local cache. And when invalidating, use staggered TTL or probabilistic early expiration to avoid stampedes.

---

## Surprising Truth / Fun Fact

Twitter's trending topics are so hot they use local cache on every app server. Redis is only the fallback. When you open Twitter and see "What's happening," that data is often served from memory on the server handling your request. No network hop. No Redis. That's how they survive viral moments.

---

## Quick Recap (5 bullets)

- A hot key is one key accessed far more than others (e.g., 100K+ reads/sec).
- One cache node cannot handle that load; it becomes a bottleneck.
- **Replication:** Store the same value under multiple keys (random suffix), spread traffic across nodes.
- **Local cache:** Keep hot keys in-process (HashMap/Guava) on each app server.
- **Trade-offs:** Local cache can go stale faster and is harder to invalidate—you must propagate invalidation to every app server. Replication uses more memory: the same value stored N times across N nodes. But both strategies save you when one key would otherwise melt a single node. Choose based on your invalidation needs and memory budget.

---

## One-Liner to Remember

*When one key burns hotter than the rest, replicate it across nodes or serve it from local memory—don't let one key take down your cache.*

---

## Next Video

Next up: How to measure if your cache is actually helping. Hit rate, miss rate, and why Facebook's cache hits 99% of requests. Topic 92: Cache Hit Rate.
