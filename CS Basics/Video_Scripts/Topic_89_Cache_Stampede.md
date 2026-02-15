# What Is Cache Stampede? (Thundering Herd)

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

School lunch bell. 12:00. 500 students. One door. They all rush at the same time. Pushing. Shoving. The door breaks. Someone trips. The canteen is overwhelmed. Chaos. This is a thundering herd. In software: one cache key expires. 10,000 requests. All miss. All hit the database at once. The database collapses. All because of one key.

---

## The Story

The lunch bell rings. Exactly 12:00. Five hundred students. One canteen door. They all run at the same time. One moment—silence. Next moment—chaos. The door can't handle 500 people. It jams. Students trip. The food counter is overwhelmed. One person can't serve 500. The line doesn't move. Fights break out. The principal has to intervene. One bell. One moment. One stampede.

Replace "students" with "requests" and "canteen" with "database." A popular cache key expires. TTL hits zero. Ten thousand users are waiting for that key. Homepage. Trending list. Celebrity profile. All 10,000 requests see: cache miss. All 10,000 go to the database. At the same time. The database was fine when 9,999 were served from cache. Now it gets 10,000 queries in one second. From 100 QPS to 10,000 QPS in an instant. It can't handle it. Queries queue. Timeout. Errors. Cascade. Site down. All because one key expired.

That's a cache stampede. Also called thundering herd. Many concurrent requests for the same key. All miss. All hit the backend. At once. A system that works at 10,000 QPS with cache can die at 10,000 QPS without it. For just one second.

---

## Another Way to See It

Concert gates open. Thousands of fans rush in. One entrance. All at once. Stampede. Same idea. A bottleneck. A moment of synchronization. Everyone wants the same thing at the same time. The system wasn't designed for that spike. The gates were built for a steady flow. Not 10,000 people in 5 seconds.

---

## Connecting to Software

**Cache stampede = many concurrent requests for the same key all experience a cache miss simultaneously.**

**When it happens:**
1. **Popular key expires (TTL).** Every 60 seconds, the key dies. All requests in that second miss. Predictable. Repeating.
2. **Cache server restarts.** Cold cache. All keys gone. All requests miss. Massive stampede. Worse than TTL because everything fails at once.
3. **Invalidation of a hot key.** Someone updates data. Cache deleted. All readers miss at once. One write. Thousands of reads. All hitting DB.

**The chain reaction:**
1. Cache miss. All requests go to DB. 10,000 queries. In one second.
2. DB overwhelmed. Slow. Timeouts. 500ms. 2 seconds. 5 seconds.
3. Clients retry. More requests. Worse. 20,000 queries now.
4. DB connection pool exhausted. No more connections. Cascading failures.
5. Site down. "Service unavailable." Revenue zero.

**Why it's dangerous:** Your system handles 10,000 QPS because 99% are cache hits. One key expires. For one second, 100% of traffic for that key hits the DB. 10,000 queries. DB capacity might be 1,000. Instant overload. The cache was hiding your true dependency. When it fails, reality hits. Hard.

---

## Let's Walk Through the Diagram

```
    NORMAL (cache warm)
    
    10,000 requests for key X
         │
         ▼
    Cache: 9,999 HIT ──> Return (fast!)
    DB:    1 miss ──> Refill cache, return
    
    DB load: 1 query. Happy.
```

```
    STAMPEDE (cache expired)
    
    10,000 requests for key X (key just expired!)
         │
         ▼
    Cache: 10,000 MISS
         │
         ▼
    DB: 10,000 queries AT ONCE
         │
         ▼
    DB overload. Timeouts. Crash.
```

**The numbers:** Normal: 100 QPS on DB. Cache warm. Fine. Stampede: 10,000 QPS in 1 second. DB capacity: 1,000. Collapse. The spike is 100x. One key. One moment. And it gets worse. Clients retry. 10,000 becomes 20,000. Connection pool exhausts. Cascading failures. One expired key. Five minutes of outage. Design for it. Always. The fix is simple in concept: never let all requests hit the DB at once. One fetches. Others wait. Or spread the expiry. Or refresh before expiry. We cover the solutions in the next video. But first: recognize the problem. One key. One moment. System down.

---

## Real-World Examples (2-3)

**Example 1 — Homepage banner:** Cached. TTL = 60 seconds. 50,000 users per minute visit the homepage. Every 60 seconds, the key expires. 50,000 requests in that second. All miss. All hit the DB. Every minute: a spike. A mini stampede. DB groans.

**Example 2 — Celebrity profile:** Millions of followers. Profile cached. One edit. Cache invalidated. Millions of requests. All miss. All hit DB. Stampede. Profile service down. "Celebrity X's profile not loading." Headlines.

**Example 3 — Black Friday:** Top 100 products. Cached. TTL = 5 minutes. 9:00 AM. Doorbusters go live. Key expires. 100,000 users. All miss. DB gets 100,000 queries. Crashes. Sales = zero for 5 minutes. Black Friday disaster. Competitors win.

---

## Let's Think Together

Your homepage banner is cached with 60-second TTL. 50,000 users per minute visit the homepage. What happens every 60 seconds?

The key expires. In the next second, some fraction of those 50,000 users will load the page. Say 1,000. All 1,000 miss. All 1,000 hit the DB. A spike every minute. Maybe the DB handles it. Maybe not. If 10,000 hit in one second? Probably not. The periodicity is the problem. Predictable. Exploitable. Fixable—with jitter, locking, or early refresh. Next video.

---

## What Could Go Wrong? (Mini Disaster Story)

Black Friday. 9 AM. Doorbusters go live. Homepage shows "Top 100 Deals." Cached. TTL = 5 minutes. 9:00. Key expires. 100,000 users refresh. All miss. 100,000 simultaneous DB queries. Database collapses. "Service unavailable." For 5 minutes. Competitors get the sales. Revenue: zero. Lesson: cache stampede isn't theory. It's production. Design for it. Before it designs for you.

---

## Surprising Truth / Fun Fact

The term "thundering herd" comes from operating systems. When multiple processes are waiting on a lock, and the lock is released, they all wake up at once. They fight for the resource. Stampede. Same pattern. Different layer. CS concepts repeat. The name stuck.

---

## Quick Recap (5 bullets)

- **Cache stampede** = many requests for same key miss simultaneously. All hit DB at once.
- **Triggers** = TTL expiry, cache restart, hot key invalidation.
- **Danger** = system works with cache. Without it for one second? Overload.
- **Chain reaction** = DB slow → timeouts → retries → worse. Cascading failure.
- **Thundering herd** = term from OS. Same idea. Multiple waiters, one resource.

---

## One-Liner to Remember

*Cache stampede: One key dies. Thousands rush the database. All at once. Chaos.*

---

## Next Video

Next: How to prevent cache stampede—locking, jitter, early refresh. The principal's three solutions.
