# Write-Back and Write-Around Cache

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A journalist scribbles notes on a notepad during an interview. Fast. No waiting. Later, at the office, she types them into the system. But what if she loses the notepad before she gets there? The notes are gone. Forever. That risk. That speed. That's write-back. And what about writes you don't want in the cache at all? That's write-around.

---

## The Story

**Write-Back:** Meera is a journalist. She interviews people all day. She doesn't type into her laptop during the interview—too slow, too distracting, too rude. She scribbles on a notepad. Fast. No waiting. At the end of the day, she goes to the office and types everything into the system. The notepad is her cache. The system is her database. Write to cache first. Database later. Async. She gets speed during the interview. The system gets the data when she's ready. But if she loses the notepad on the bus? The notes are gone. Unrecoverable. Write-back equals speed plus risk. You trade durability for latency.

**Write-Around:** You buy new furniture. A new chair. A bookshelf. Where do you put it? Not on your desk. Your desk has limited space—your laptop, your coffee, the things you use daily. You put the new furniture in the storage room. When you need it—when you actually sit in that chair, when you put books on that shelf—you bring it to your "active" space. Write-around means writes go straight to the database. The cache is bypassed entirely. Cache fills only when someone reads. New data doesn't pollute the cache until it's requested. Your cache stays hot. Only what people actually use.

---

## Another Way to See It

**Write-back:** A waiter takes orders on a notepad. Quick. Doesn't run to the kitchen after every single order. At the end of the shift, he enters everything into the system. Fast service. Happy customers. But if the notepad gets wet, or lost, or someone throws it away? Orders vanish. No record.

**Write-around:** You receive a package. You put it in the closet. Not on your desk. Your desk is for the stuff you're actively using. When you need the package, you fetch it and put it on your desk. Your desk (cache) stays clean. Only holds what you actually use. No clutter.

---

## Connecting to Software

**Write-Back Flow:**
1. App writes to cache only.
2. Return success immediately. User gets fast response.
3. Cache asynchronously writes to the database in the background.
4. Batches possible. Multiple cache writes can become one DB write. Efficient.

**Risk:** Cache crashes before the async write completes? Data loss. Seconds or minutes of writes gone. Acceptable for metrics, logs, analytics. Unacceptable for financial transactions, user data.

**Write-Around Flow:**
1. App writes directly to the database.
2. Cache is not updated. Not touched.
3. Next read equals cache miss. Fetch from DB. Fill cache.
4. Writes never pollute the cache. Only reads do.

**When write-around:** Write-heavy, read-light. New data rarely read immediately. Audit logs. Event streams. Avoid filling cache with data that might never be accessed.

---

## Let's Walk Through the Diagram

```
    ALL FOUR CACHING WRITE PATTERNS
    
    ┌─────────────┬─────────────────────────────────────────────────┐
    │ Pattern     │ Behavior                                        │
    ├─────────────┼─────────────────────────────────────────────────┤
    │ Cache-aside │ Read fills cache. Writes → DB only.              │
    │             │ Cache invalidated on write. Lazy.                │
    ├─────────────┼─────────────────────────────────────────────────┤
    │ Write-      │ Write → Cache + DB (both). Always sync.         │
    │ through     │ Never stale. Slower writes.                      │
    ├─────────────┼─────────────────────────────────────────────────┤
    │ Write-back  │ Write → Cache only → return. Cache async        │
    │             │ writes to DB later. Fast. Risk: data loss.      │
    ├─────────────┼─────────────────────────────────────────────────┤
    │ Write-      │ Write → DB only. Cache untouched.               │
    │ around      │ Read fills cache on next access. No pollution.   │
    └─────────────┴─────────────────────────────────────────────────┘
```

```
    WRITE-BACK                    WRITE-AROUND
    -----------                   -------------
    
    App ──> Cache ──> Success     App ──> DB ──> Success
              │                         
              │ (async, later)           Next Read: Cache MISS
              ▼                         App ──> DB ──> Cache ──> Return
           Database
```

**When to use which:** Cache-aside for read-heavy, general purpose. Write-through when consistency is critical. Write-back for high write throughput, tolerable loss. Write-around for write-heavy, read-rare, cache pollution risk.

---

## Real-World Examples (2-3)

**Write-back — IoT sensors:** 100,000 temperature readings per second. Write to Redis first. Return. Background job batches and writes to the database. Fast. If Redis crashes? Lose a few seconds of readings. Acceptable for metrics. Nobody dies.

**Write-back — Analytics events:** Click events. Page views. Write to Kafka or in-memory buffer. Async flush to data warehouse. Speed matters. Some loss tolerable. Approximate counts are fine.

**Write-around — Audit logs:** Every action is logged. Write directly to DB. Rarely read. No need to cache. Cache stays hot for frequently-read data. User sessions. Product catalog. Not logs.

---

## Let's Think Together

IoT sensors send 100,000 readings per second. Which write pattern fits?

Write-back. Fast writes to cache. Async batch to DB. Throughput is huge. Some data loss if cache fails? For sensor metrics, usually acceptable. For payment data? Never. Context matters. Session updates? Write-through. Logs? Write-back. Product price? Cache-aside with invalidation.

---

## What Could Go Wrong? (Mini Disaster Story)

A company uses write-back for user session updates. "Session last active" timestamp. Writes go to Redis. Async job syncs to DB every 30 seconds. Works great. Fast. Scalable.

One day Redis crashes. Restart. 30 seconds of session data—gone. Users appear "inactive" even though they were online. Support chaos. "I was on the site! Why did I get logged out?" For session data, even 30 seconds of loss was unacceptable. They switched to write-through. Lesson: write-back is fast. But know what you're willing to lose.

---

## Surprising Truth / Fun Fact

Your CPU uses write-back internally. When you write to memory, the CPU often writes to the L1 cache first. Later, it syncs to RAM. Same pattern. Hardware has been doing this for decades. Software is catching up.

---

## Quick Recap (5 bullets)

- **Write-back** = write to cache first, DB updated later (async). Fastest writes. Data loss risk.
- **Write-around** = write to DB only. Cache bypassed. Fills on read. Avoids cache pollution.
- **Write-back use case** = high write throughput, some data loss acceptable (logs, metrics).
- **Write-around use case** = write-heavy, read-rare. New data unlikely to be read soon.
- **CPU caches** = use write-back. Same pattern at the hardware level.

---

## One-Liner to Remember

*Write-back: Fast writes, delayed DB. Risk of loss. Write-around: Skip cache on writes. Fill on reads.*

---

## Next Video

Next: Cache invalidation—why Phil Karlton called it one of the two hard things in computer science.
