# TTL: Time-to-Live — Simple Invalidation

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Your morning newspaper. Accurate today. Tomorrow? Outdated. It has a shelf life. You read it. Use it. Then throw it away and get a new one. That shelf life—that expiration—is TTL. In caching, you store data with a deadline. "Keep this for 5 minutes." After 5 minutes? Gone. Next request gets fresh data. Simple. Effective.

---

## The Story

Raj gets a newspaper every morning. Fresh. Accurate. He reads it over breakfast. The headlines. The sports section. By evening? Old news. He doesn't keep it. He throws it away. Tomorrow, a new paper arrives. The newspaper has a natural shelf life. One day. Use it. Discard it. Replace it. He doesn't need to "invalidate" the old paper manually. Time does the work.

That's TTL—Time-to-Live. When you cache something, you say: "Keep this for X seconds." Or minutes. Or hours. After that time, the cache automatically deletes the entry. The next request gets a cache miss. Fetches fresh data from the database. Caches it again with a new TTL. The cycle continues. No manual invalidation. No code to remember. Time does the work. Simple.

---

## Another Way to See It

Yogurt in the fridge. Expiration date on the lid. Seven days. You don't track when you bought it. The date tells you. After that? Don't eat it. Same idea. TTL is the expiration date for your cached data. Set it. Forget it. The system enforces it. Redis. Memcached. HTTP headers. All support it.

---

## Connecting to Software

**TTL = seconds (or minutes, hours) a cached value lives before expiring.**

Redis: `SET user:123 "data" EX 300` — cache for 300 seconds (5 minutes).  
Memcached: `set key 0 300 value` — same idea.  
HTTP: `Cache-Control: max-age=3600` — browser caches for 1 hour. The `max-age` is TTL in seconds.

**What TTL for what data:**

| Data Type      | TTL      | Why                                   |
|----------------|----------|---------------------------------------|
| User profile   | 5 min    | Changes occasionally. Stale okay.     |
| Stock price    | 0 (no cache) | Real-time. Stale = wrong.         |
| Static CSS/JS  | 1 day    | Rarely changes. Long TTL. CDN love.    |
| Homepage feed  | 30 sec   | Fresh. Balance load vs freshness.     |
| Product catalog| 10 min   | Updates infrequently.                 |

**Short TTL (e.g. 10 sec):** Very fresh data. More DB hits. Lower stale risk. Good for stock prices, live scores.

**Long TTL (e.g. 1 hour):** Fewer DB hits. Better performance. Higher stale risk. Good for user profiles, static content.

**Stale-while-revalidate:** Serve stale data immediately—even if expired. Don't block the user. In the background, fetch fresh data. Update cache. Next request gets fresh. User gets fast response. Eventually consistent. Best of both worlds. HTTP supports this with `stale-while-revalidate=60` in Cache-Control. The 60 means: you can serve stale for up to 60 seconds while revalidating. Gives the background fetch time to complete. No user waits. No stampede.

**Choosing TTL in practice:** Start with your maximum acceptable staleness. User profile? 5 minutes is usually fine. Stock price? Don't cache—or use 0. Static assets? 1 day or 1 week. Homepage? 30–60 seconds. Then tune. Too many DB hits? Increase TTL. Too stale? Decrease. Monitor. Adjust. It's an art. When in doubt, start conservative. Short TTL. Monitor. Increase if DB load is too high. Better to be a bit stale than to overload your database.

---

## Let's Walk Through the Diagram

```
    TTL LIFECYCLE
    
    t=0:    Request 1 → Cache MISS → DB → Cache (TTL=300s) → Return
    t=1:    Request 2 → Cache HIT → Return (fast!)
    t=2:    Request 3 → Cache HIT → Return
    ...
    t=299:  Request N → Cache HIT → Return
    t=300:  TTL expires. Cache entry deleted.
    t=301:  Request N+1 → Cache MISS → DB → Cache (TTL=300s) → Return
```

```
    TTL SPECTRUM
    
    Short (10s)     Medium (5m)      Long (1h)
    -----------     -------------    ----------
    Fresher         Balanced         Fewer hits
    More DB load    Sweet spot       Staler
    Live data       Most cases       Static data
```

**HTTP Cache-Control deep dive:** `Cache-Control: max-age=3600, stale-while-revalidate=60` means: cache for 1 hour. After expiry, serve stale for up to 60 more seconds while revalidating in background. Browsers and CDNs use this. You've seen it. Every website. Other useful directives: `no-cache` (must revalidate before use), `no-store` (don't cache at all), `private` (browser only, not shared), `public` (CDN can cache). TTL is everywhere. Learn it once. Use it forever.

---

## Real-World Examples (2-3)

**Example 1 — User profile:** TTL = 5 minutes. Profile changes might take 5 min to appear. Usually fine. Reduces DB load by 90% or more.

**Example 2 — News headline:** Breaking news. TTL = 10 seconds. Users see updates within 10 sec. DB gets hit every 10 sec. Acceptable for high-traffic headlines.

**Example 3 — Static assets:** CSS, JS, images. TTL = 1 day or more. Rarely change. Long TTL. Massive cache hit rate. CDNs love this.

---

## Let's Think Together

Breaking news headline on a news website. What TTL?

If 1 hour: users see yesterday's headline for a full hour. Bad. If 10 seconds: every 10 seconds, the cache expires. Millions of users. Millions of DB hits. Database might collapse. The sweet spot? Maybe 30–60 seconds. Or use stale-while-revalidate: serve stale, refresh in background. User gets speed. System gets relief. Trade-offs everywhere.

---

## What Could Go Wrong? (Mini Disaster Story)

A team set TTL = 24 hours for a "daily deals" section. Logic: it updates once a day. Sounds right. But one day they ran an emergency flash sale at 2 PM. Price dropped 80%. The cached "daily deals" still showed morning prices. For 24 hours. Users outraged. "The sale is a lie!" TTL too long. Cache became a trap. Lesson: match TTL to your actual update frequency. And have a manual invalidation escape hatch.

---

## Surprising Truth / Fun Fact

HTTP has `Cache-Control: max-age=3600`. Your browser uses TTL caching for every website you visit. Images, CSS, JavaScript—all cached with an expiration. You're using TTL right now. Every webpage. Without knowing it. It's the invisible foundation of the web.

---

## Quick Recap (5 bullets)

- **TTL** = how long cached data lives before expiring. Set in seconds/minutes/hours.
- **Short TTL** = fresher data, more DB hits. Long TTL = fewer hits, staler data.
- **Choosing TTL** = depends on how stale you can tolerate. Domain-specific.
- **Stale-while-revalidate** = serve stale + refresh in background. Fast + eventually fresh.
- **Browser caching** = every website uses TTL via Cache-Control headers.

---

## One-Liner to Remember

*TTL: Set an expiration. Let time do the invalidation. Simple. But choose wisely.*

---

## Next Video

Next: Invalidate on write—when you can't wait for TTL. Delete the cache the moment data changes.
