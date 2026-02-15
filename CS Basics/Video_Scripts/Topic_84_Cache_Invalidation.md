# Cache Invalidation: Why It's Hard

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A post-it on the fridge: "Milk expires Jan 15." It's January 20. You drink the milk. It's spoiled. The post-it lied. Wait—the milk was replaced days ago. New carton, Feb 1. But the post-it still says Jan 15. You served yourself stale data. That moment of betrayal? That's cache invalidation.

---

## The Story

Ananya has a system. Post-its everywhere. Reminders. Notes. Grocery lists. One says "Milk expires Jan 15." She trusts it. January 20. She pours a glass. Sour. She spits it out. The post-it was wrong. Her roommate had replaced the milk. New carton. Expires Feb 1. But no one updated the post-it. The real data changed. The cached copy—the note—didn't. Stale. Dangerous. She could have gotten sick. All because two systems—fridge and post-it—were out of sync.

That's cache invalidation. Phil Karlton said it: "There are only two hard things in computer science: cache invalidation and naming things." When the real data changes, how do you make sure the cached copy is updated or removed? There's no magical link. Cache and database are separate systems. When one changes, the other doesn't know. You have to build the bridge. Manually. And it's easy to forget.

---

## Another Way to See It

A phone book. Your friend changes their number. Your old phone book still has the old number. How do you find out? Option 1: They tell you. You cross out the old number, write the new one. Direct invalidation. Option 2: You assume the book is wrong after a year. Throw it away. Get a new one. TTL. Time-based invalidation. Option 3: You don't trust the book. Every time you need to call, you ask them directly. No cache. Each approach has trade-offs. Accuracy. Convenience. Cost.

---

## Connecting to Software

**Why it's hard:** The cache and the database don't talk. When the DB changes, the cache has no idea. You have to build the bridge. Manually. Every write path. Every update. Every delete. It's easy to forget one. A new API. A new admin panel. A new batch job. Each is a place where data can change. Each needs invalidation. Miss one? Stale forever.

**Three approaches:**

1. **TTL (Time-to-Live):** Let the cache expire after a fixed time. Simple. No code paths to update. But you get a stale window. Data might be wrong for minutes or hours. User updates their name? Might take 5 minutes to appear. Or an hour.

2. **Invalidate on write:** When you write to the DB, delete (or update) the cache entry. Real-time. Fresh. But requires coordination. Every write path must trigger invalidation. Miss one? Stale forever. And there's a race: delete-then-write vs write-then-delete. Thread A deletes cache. Thread B reads (miss), fetches old data. Thread A writes new data to DB. Thread B writes old data to cache. Stale. Order matters.

3. **Event-driven:** DB change publishes an event. A consumer listens and invalidates the cache. Decoupled. Scales. Complex. But real-time and flexible. Facebook's Memcache invalidation pipeline does this at massive scale.

---

## Let's Walk Through the Diagram

```
    THE PROBLEM
    
    Database:  price = 500 (updated)
    Cache:     price = 1000 (old!)
    
    User request → Cache HIT → Returns 1000 (WRONG!)
    
    
    THREE SOLUTIONS
    
    1. TTL:           Cache expires after 5 min. Next request = miss = fresh from DB.
                      Simple. Stale window = up to 5 min.
    
    2. Invalidate:    On DB write → DELETE cache key. Next read = miss = fresh.
                      Precise. Must remember to invalidate everywhere.
    
    3. Event-driven:  DB write → publish event → consumer deletes cache.
                      Decoupled. More moving parts.
```

**Delete-then-write vs write-then-delete:** If you write to DB first, then delete cache, there's a small window where cache has old data and DB has new. A reader could get old from cache. If you delete cache first, then write to DB, a reader could miss, fetch from DB mid-write, get inconsistent data. Solutions: double-delete (delete before and after write). Or use a short TTL as safety net. No perfect order. The race is subtle. Thread A deletes. Thread B reads (miss), fetches. Thread A writes. Thread B writes old to cache. Stale. The double-delete catches Thread B's stale write when the second delete runs.

---

## Real-World Examples (2-3)

**Example 1 — Product price:** Flash sale. Price drops from Rs 1000 to Rs 500. DB updated. Cache still has 1000. Thousands of users see wrong price. Cart confusion. Support overloaded. Invalidation was forgotten.

**Example 2 — User profile:** User updates their bio. DB has new bio. Cache has old bio. Followers see outdated information. Until TTL expires or someone invalidates. Annoying. Brand damage.

**Example 3 — Deleted content:** User deletes a post. DB: post gone. Cache: post still there. Users see deleted content. Creepy. Privacy violation. Invalidation is critical.

---

## Let's Think Together

Product price changes from Rs 1000 to Rs 500. Cache still has Rs 1000. 10,000 users see the wrong price. How long is acceptable?

Zero? For prices, maybe. But that means no caching—or perfect invalidation. Ten seconds? TTL of 10 seconds. Some users see wrong price. Usually acceptable for non-critical data. One hour? For a flash sale? Disaster. The answer depends on your domain. Money? Stricter. Social posts? Looser.

---

## What Could Go Wrong? (Mini Disaster Story)

A social app had no invalidation strategy. Just TTL. One hour. User updates their profile photo. Friends still see the old photo for an hour. Annoying but livable. Then: user deletes their account. For one hour, their profile still appeared. Cached. "User not found" only after cache expired. Privacy violation. Legal risk. Lesson: invalidation isn't optional for sensitive data. TTL alone is not enough.

---

## Surprising Truth / Fun Fact

Facebook built a system called the Memcache invalidation pipeline. It processes millions of cache invalidations per second. At their scale, invalidation isn't a feature—it's an entire engineering discipline. Dedicated teams. Custom tooling. When you have billions of users, "just invalidate" becomes a massive distributed system.

---

## Quick Recap (5 bullets)

- **Cache invalidation** = when real data changes, how do you update or remove the cached copy?
- **Phil Karlton** = "Two hard things: cache invalidation and naming things."
- **TTL** = expire after time. Simple. Stale window.
- **Invalidate on write** = delete cache when DB changes. Precise. Easy to forget.
- **Event-driven** = DB change triggers invalidation. Decoupled. Complex.

---

## One-Liner to Remember

*Cache invalidation: The bridge between two systems that don't talk. Build it. Or pay the price.*

---

## Next Video

Next: TTL—the simplest invalidation strategy. Time as your safety net.
