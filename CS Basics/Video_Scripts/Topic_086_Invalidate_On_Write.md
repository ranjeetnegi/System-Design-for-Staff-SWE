# Invalidate on Write: When and How

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A scoreboard at a cricket match. It shows 245. Batsman hits a six. 251. The scorekeeper updates the display immediately. Not after 5 minutes. Not "whenever." Right now. Because the data changed. That instant update? That's invalidate-on-write.

---

## The Story

The stadium is packed. Forty thousand fans. Scoreboard: 245. The batsman swings. Crack. Six! The ball sails over the boundary. The scorekeeper doesn't wait. He doesn't say "I'll update it at the next over." He updates the display instantly. 251. Everyone sees it. Real-time. The moment the data changed, the "cache"—the scoreboard—was updated. No TTL. No "it'll refresh in a minute." Now. Because the score changed. The cache must reflect reality.

That's invalidate-on-write. Whenever data changes in the database, you delete—or update—the corresponding cache entry immediately. The next read gets a cache miss (if you deleted) or the new value (if you updated). Either way, users see fresh data. No stale window. If you do it right.

---

## Another Way to See It

A shared family calendar. Someone adds an event. They don't just write it in the main calendar and hope everyone notices. They erase the old "upcoming events" list on the fridge and write the new one. Or they update it. The fridge display (cache) stays in sync with the source (main calendar). Invalidate or update on every change. Everyone sees the truth.

---

## Connecting to Software

**Two flavors:**

1. **Delete the cache key on write.** Next read = cache miss. Fetch from DB. Refill cache. Safer. Avoids race conditions. Slightly slower next read (one extra DB hit). Preferred by most systems.

2. **Update the cache key on write.** Write new value to both DB and cache. Next read = cache hit. Faster. But risk of race conditions. If Thread A reads old, Thread B writes new, Thread A overwrites cache with old—stale. Order matters. Most systems prefer delete.

**Implementation:**
1. Application writes to database.
2. Application deletes the cache key. (Or updates it.)
3. Done. Next read will miss and refill. Or hit the new value.

**Race condition:** Thread A reads (miss). Thread A fetches from DB (old value). Thread B writes to DB and invalidates cache. Thread A—still holding old data—writes it to cache. Stale! Solution: short TTL as safety net. Or distributed locks. Or "double delete"—delete cache before write, write to DB, delete cache again. The second delete catches any stale write that snuck in.

**Update vs delete in detail:** Update = write-through style. Simpler logic. But races. Delete = cache-aside style. Cleaner. Next reader pays one DB hit. Usually worth it.

**Double delete in depth:** Why twice? Thread A deletes (clear stale). Thread B reads (miss), fetches old, about to write. Thread A writes new to DB. Thread A deletes again. Thread B writes old to cache. Now we have stale. Thread A's second delete runs after B's write. Catches it. Cache clean. The second delete is the safety net. Small window. But it works. Use with a short delay between deletes if needed. Or run the second delete asynchronously after a few milliseconds.

---

## Let's Walk Through the Diagram

```
    INVALIDATE ON WRITE (DELETE FLAVOR)
    
    Write request
         │
         ▼
    ┌──────────┐     ┌─────────────┐
    │ Write to │     │ Delete      │
    │ Database │     │ Cache Key   │
    └──────────┘     └─────────────┘
         │                   │
         └─────────┬────────┘
                   │
                   ▼
              Success!
    
    Next Read: Cache MISS → DB → Refill cache → Return
```

```
    RACE CONDITION (THE BUG)
    
    Thread A: read (miss) → fetch from DB (old value)
    Thread B: write to DB → invalidate cache
    Thread A: write OLD value to cache  ← STALE!
    
    Solution: TTL as safety net. Or lock. Or double-delete.
```

```
    DOUBLE DELETE (SAFETY TECHNIQUE)
    
    1. Delete cache key (clear any stale)
    2. Write to database
    3. Delete cache key again (catch race from step 1)
    
    Next read: miss. Fresh from DB. Clean.
```

---

## Real-World Examples (2-3)

**Example 1 — User profile update:** User changes their name. Write to DB. Delete cache key `user:123`. Next profile read misses, fetches fresh, caches. Clean.

**Example 2 — Product price update:** Admin changes price. DB updated. Delete `product:456` from cache. Next product view gets correct price. No TTL wait.

**Example 3 — Wikipedia:** Edit a page. Their system purges cached versions across the entire CDN within seconds. Thousands of edge servers. Hundreds of languages. Almost instant. Invalidate-on-write at massive scale. When you edit Wikipedia, your change propagates globally in seconds. Engineering excellence. They use a purge API. Edit triggers purge. CDN invalidates. Next read fetches fresh. Millions of pages. One pattern. The key lesson: every write path must trigger invalidation. No exceptions. Add it to your code review checklist. Automate it. Tests that verify invalidation on every write. One forgotten path. Stale forever.

---

## Let's Think Together

User updates their profile. You delete the cache. Good. But 100 concurrent readers just missed the cache. They all hit the database simultaneously. 100 parallel queries for the same key. What happens?

Cache stampede. Thundering herd. The database gets hammered. All because one key was invalidated. We'll cover how to prevent this in a later video. For now: invalidation can trigger a stampede. Design for it. Locking. Jitter. Stale-while-revalidate.

---

## What Could Go Wrong? (Mini Disaster Story)

A developer adds a new API: "Update user preferences." Writes to the database. Works. But they forget to add cache invalidation. The preferences are cached under `user:123:prefs`. The cache still has the old preferences. Forever. Until TTL. TTL is 24 hours. Users change settings. Nothing happens. "The app is broken!" One forgotten line. One invalidate call. Silent bug. Lesson: every write path must invalidate. Code review. Checklist. Automation. Don't trust memory.

---

## Surprising Truth / Fun Fact

Every time you edit a Wikipedia page, their cache invalidation system purges cached versions across their entire CDN within seconds. Thousands of edge servers. Millions of pages. Updated almost instantly. Invalidate-on-write at planetary scale.

---

## Quick Recap (5 bullets)

- **Invalidate on write** = when data changes, delete or update the cache entry immediately.
- **Delete vs update** = delete is safer (avoids races). Update is faster (avoids next miss). Prefer delete.
- **Race condition** = old read can overwrite cache after invalidation. Use TTL or locks as safety.
- **Cache stampede** = many readers hit DB after invalidation. A problem to solve separately.
- **Critical** = every write path must invalidate. Forget one? Stale forever.

---

## One-Liner to Remember

*Invalidate on write: The moment data changes, kill the cache. Next read gets fresh. If you remember to do it.*

---

## Next Video

Next: Cache eviction—when the cache is full, who gets kicked out? LRU explained.
