# Write-Through Cache

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A teacher grades a paper. She writes the grade in two places at once—the official register and a quick-reference sheet on her desk. Both always match. When a student asks for their grade? She checks the desk. Instant. Always correct. That dual-write. That discipline. That's write-through.

---

## The Story

Mr. Sharma grades hundreds of exams every semester. Every time he grades a paper, he does something deliberate. He writes the grade in the official register—the permanent record, stored in the office, backed up. And he writes it on a sheet on his desk—the fast lookup, the one he glances at when students run up asking "What did I get?"

Both. Every time. No exceptions. He never updates one without the other. When a student runs up and asks, he doesn't flip through the heavy register. He looks at his desk. Instant. And it's always right—because he updated both together. The desk and the register are in perfect sync. Always. That's the promise.

That's write-through caching. Every write goes to the cache and the database at the same time. The cache is never stale. Read-after-write? Always consistent. The user updates their profile. You write to Redis and PostgreSQL. Both. Next read? Cache hit. Correct value. But here's the cost: every write is slower. You're writing to two places. And you might be caching data that no one ever reads.

---

## Another Way to See It

A whiteboard and a permanent notebook. Every time you write something on the whiteboard—a meeting note, a todo—you also write it in the notebook. The whiteboard is fast to read. Everyone can see it. The notebook is the source of truth. Durable. They're always in sync. That's write-through. Two writes. One truth. No drift.

---

## Connecting to Software

**The flow:**

1. Application receives a write request.
2. Write to the cache.
3. Write to the database.
4. Both succeed? Return success to the caller.

Cache and DB are updated together. Either in parallel (faster, but harder to rollback on failure) or sequentially (simpler—write DB first, then cache, so DB is source of truth). The key: both must succeed for consistency. If the DB fails, you typically roll back or invalidate the cache write too.

**Advantages:** Cache is always up-to-date. No stale data. Read-after-write is always consistent. Perfect for systems where correctness matters more than write speed. Session data. Configuration. User preferences.

**Disadvantages:** Every write hits two systems. Write latency increases. If cache write takes 2ms and DB write takes 20ms, your write latency is 22ms—or more. And you cache data that might never be read. New user signs up? You cache their empty profile. Maybe no one views it for a week. Cache space wasted. Write-through doesn't discriminate. It caches everything that gets written.

**Timing comparison:** Cache-aside writes to cache only on reads. Write-through writes on every write. For a write-heavy workload with low read-after-write, cache-aside might never cache some keys. Write-through caches them all. More cache traffic. More potential waste. Write latency: cache-aside read = 1–2ms (cache hit) or 20–50ms (DB). Write-through write = cache write + DB write. If sequential, add both. If parallel, limited by the slower. Either way, every write pays double. Compare: cache-aside write = DB only (cache invalidated separately). Write-through write = cache + DB. Twice the work. Twice the latency. You pay for consistency.

---

## Let's Walk Through the Diagram

```
    WRITE REQUEST
         │
         ▼
    ┌─────────────┐
    │  Application│
    └──────┬──────┘
           │
           ▼
    ┌──────┴──────┐
    │             │
    ▼             ▼
┌───────┐    ┌──────────┐
│ Cache │    │ Database │
│ Write │    │  Write   │
└───────┘    └──────────┘
    │             │
    └──────┬──────┘
           │
           ▼
      Success!
```

**Cache-aside vs write-through:** Cache-aside only caches on read. The application populates the cache when it misses. Write-through caches on write. The application updates the cache proactively. Different triggers. Different trade-offs. Cache-aside: lazy. Write-through: disciplined.

---

## Real-World Examples (2-3)

**Example 1 — Session data:** User logs in. Session created. Written to Redis and database. Every session read hits Redis. Always fresh. Write-through keeps them in sync. No "session not found" because cache was stale.

**Example 2 — Configuration:** Admin updates a setting. Written to cache and DB. All servers read from cache. Change is visible immediately. No invalidation needed. No TTL race. Just consistency.

**Example 3 — DynamoDB Accelerator (DAX):** AWS's DAX uses write-through. Writes go to both DAX cache and the DynamoDB table. Reads are fast—microseconds. Consistency is guaranteed. Writes pay the dual-write cost.

---

## Let's Think Together

You write 10,000 new user profiles per hour. How many are actually read within the first hour? Maybe 10%. The rest? Dormant. New signups. Profiles created. Never viewed.

With write-through, you're caching all 10,000. 9,000 of those cache entries might never get a single read. Is that wasting 90% of your cache writes? Yes. Cache space? Yes. Write-through excels when read-after-write is common. When most writes are followed quickly by reads. Session updates. Config changes. Know your access pattern. If writes far exceed reads, and reads are rare, write-through might be the wrong choice.

---

## What Could Go Wrong? (Mini Disaster Story)

A startup uses write-through. Cache is in the same region as the app. Database is across the ocean. Every write: 5ms to cache, 50ms to database. Total: 55ms. Fine at first.

Then they scale. Two data centers. Cache replicas in both. Now every write goes to a remote cache node—50ms. Plus 50ms to the database. 100ms per write. User experience tanks. "Why is saving so slow?" Write-through plus remote cache equals latency nightmare. Every keystroke. Every profile update. 100ms. Unacceptable. Lesson: keep write-through cache close. Or accept the cost. Or switch patterns.

---

## Surprising Truth / Fun Fact

DynamoDB Accelerator (DAX) uses write-through caching. When you write to a DAX-backed table, the write goes to both DAX and DynamoDB. Writes are a bit slower. But reads? Microseconds. AWS chose write-through for consistency. At scale, that trade-off matters. Millions of reads. Thousands of writes. The reads dominate. Write-through wins.

---

## Quick Recap (5 bullets)

- **Write-through** = every write goes to cache and database simultaneously.
- **Always consistent** = cache is never stale. Read-after-write works.
- **Slower writes** = two destinations per write. Latency adds up.
- **Cache pollution risk** = you cache data that might never be read.
- **Best when** = read-after-write is common. Consistency over write speed.

---

## One-Liner to Remember

*Write-through: Update cache and database together. Always in sync. But every write pays the price.*

---

## Next Video

Next: Write-back and write-around—when to write to cache first, or skip the cache entirely.
