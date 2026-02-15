# How to Prevent Cache Stampede: Locking, Jitter

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Remember the 500 students rushing the canteen door? The principal has three fixes. Fix 1: Put a prefect at the door. Only one student enters at a time. Others wait. The first gets food, fills the shared tray. Others take from the tray. Fix 2: Don't ring the bell at exactly 12:00. Ring it randomly between 11:55 and 12:05 for different classes. Students arrive staggered. No stampede. Fix 3: A staff member checks at 11:50 and pre-stocks food before the bell. Three solutions. Three strategies.

---

## The Story

The school principal saw the chaos. One bell. One door. Five hundred students. She tried three approaches.

**Solution 1 — Locking:** A prefect at the door. Only one student enters at a time. The first goes in, gets food, fills a shared tray. Others wait. When the first is done, they take from the tray. No rush. One person does the work. Many benefit. In caching: on cache miss, only one request fetches from the DB. Others wait for the result. The first populates the cache. Others get the cached value. Mutex. Singleflight. No stampede.

**Solution 2 — Jitter:** Don't ring the bell at 12:00 for everyone. Class A: 11:55. Class B: 11:58. Class C: 12:02. Class D: 12:05. Students arrive at different times. No 500-person spike. In caching: don't set TTL=60 for every key. Use TTL=55 to 65 (random). Keys expire at different times. Misses spread over 10 seconds. No spike.

**Solution 3 — Early refresh:** A staff member goes to the canteen at 11:50. Pre-stocks. Before the bell. When students arrive, food is ready. In caching: before TTL expires, a background process re-fetches and updates the cache. The cache never actually "expires" for users. Zero misses. Zero stampede.

---

## Another Way to See It

**Locking:** One person goes to the bank ATM. Others form a line. One transaction at a time. No crowd at the machine.

**Jitter:** Movie showtimes at 7:00, 7:15, 7:30, 7:45. Crowds spread. No single 7:00 rush.

**Early refresh:** Flight attendants prepare snacks before turbulence. Ready when needed. Proactive.

---

## Connecting to Software

**1. Locking (Mutex / Singleflight):**
- On cache miss, acquire a lock for that key.
- Only the first request fetches from DB.
- Others wait (or poll) for the result.
- First request populates cache. Releases lock.
- Others get cached value. No duplicate DB loads.
- Risk: every cache miss is serialized. Under heavy load, wait time grows. Use for hot keys. Not everything.

**2. Jitter (Randomized TTL):**
- Instead of TTL=60 for all, use TTL = 60 + random(-5, +5). So 55–65 seconds.
- Different keys expire at different times.
- Spreads misses over a window. No synchronized spike.
- Limitation: doesn't help for a single hot key. All requests hit the same key. It still expires once. Jitter helps when many keys expire around the same time (e.g. midnight refresh, batch load).

**3. Early refresh / Background refresh:**
- At TTL-10 seconds, trigger a background refresh.
- Fetch fresh data. Update cache. Extend TTL.
- Cache never expires from user perspective. Zero user-facing misses.
- Complicated: need to handle refresh failures. What if refresh fails? Serve stale. Retry.

**4. Stale-while-revalidate:**
- Serve stale cached value immediately—even if expired.
- In background, fetch fresh data. Update cache.
- User gets fast (possibly stale) response. Next user gets fresh.
- Best of both: no stampede, eventual freshness. No user ever triggers a DB load. The background job does it once.

---

## Let's Walk Through the Diagram

```
    WITHOUT PROTECTION (Stampede)
    
    t=60: Key expires. 10,000 requests.
    All 10,000 → DB. Crash.
```

```
    WITH LOCKING
    
    t=60: Key expires. 10,000 requests.
    Request 1: acquires lock, fetches from DB, fills cache, releases.
    Requests 2–10,000: wait. Get cached value. No DB load.
    DB: 1 query. Saved.
```

```
    WITH JITTER (TTL = 55–65 random)
    
    Key A expires at 55s. Key B at 62s. Key C at 58s.
    Misses spread. No single spike.
    (Helps for many keys. Single hot key: use locking.)
```

```
    STALE-WHILE-REVALIDATE
    
    t=60: Key expires. Request arrives.
    Serve stale from cache (fast!). Background: fetch fresh, update cache.
    Next request: gets fresh. No stampede. User never waited.
```

---

## Real-World Examples (2-3)

**Example 1 — Singleflight (Go):** The `golang.org/x/sync/singleflight` package. Groups duplicate concurrent calls by key. One executes. Others share the result. Classic stampede prevention. One line of code.

**Example 2 — Netflix:** Uses jitter plus stale-while-revalidate for home page API. Peak hours. Millions of users. Database never sees a stampede. Cache stays warm. Stale served while fresh loads.

**Example 3 — E-commerce product page:** Hot product. Cache miss. Lock per product ID. First request loads. Others wait. Cache fills. No 10,000 duplicate queries.

---

## Let's Think Together

Which technique works best for:
(a) One super hot key, 100K requests per second?
(b) One million keys expiring at midnight?
(c) High availability—must never show errors?

(a) Locking. Single key. Jitter doesn't help—same key expires once. Lock ensures one DB load. Others wait.  
(b) Jitter. Many keys. If all expire at midnight, huge spike. Randomize TTL. Keys expire over a window. Spread the load.  
(c) Stale-while-revalidate. Serve stale. Never block. Background refresh. User always gets something. No stampede. No errors. Eventually fresh.

---

## What Could Go Wrong? (Mini Disaster Story)

A team used locking everywhere. Aggressive. Every cache miss: lock. Under normal load, fine. Under peak, 1000 keys expired. 1000 locks. 1000 serialized DB fetches. Each took 50ms. Total: 50 seconds of serialized load. Users waited. Timeout city. "Site is broken." Lesson: locking prevents stampede but can serialize too much. Use for hot keys. Not for everything. Combine with jitter for bulk expiry.

---

## Surprising Truth / Fun Fact

Netflix uses a combination of jitter and stale-while-revalidate for their home page API. During peak hours—millions of users—the database never sees a stampede. The cache serves stale while refreshing in the background. Users get speed. The system gets stability. Production-proven. At scale.

---

## Quick Recap (5 bullets)

- **Locking** = one request fetches on miss. Others wait. Share result. No stampede.
- **Jitter** = randomize TTL. Spread expiry. Good for many keys. Not for single hot key.
- **Early refresh** = refresh before expiry. Cache never expires. Zero user-facing misses.
- **Stale-while-revalidate** = serve stale + refresh in background. Fast + eventually fresh.
- **Choose** = hot single key → locking. Bulk expiry → jitter. High availability → stale-while-revalidate.

---

## One-Liner to Remember

*Prevent stampede: Lock (one fetches, rest wait), jitter (spread expiry), or refresh early. Pick your weapon.*

---

## Next Video

Next: We'll dive deeper into distributed caching—consistency, replication, and what happens when cache nodes fail.
