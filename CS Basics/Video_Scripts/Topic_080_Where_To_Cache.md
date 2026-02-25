# Where to Cache: Client, Edge, Server, DB Layer

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You order food. Where is it cached—pre-made? Your fridge at home. The stall outside your apartment. The restaurant's kitchen. The prep table with pre-chopped vegetables. Four levels. Each closer to you = faster. Each further = more shared, more centralized.

That's the cache hierarchy. And every big system uses it.

---

## The Story

Nina is hungry. She could cook at home—fridge has leftovers. Fastest. Most personal. Or walk to the stall outside her building—serves the whole neighborhood. Close. Shared. Or go to the restaurant—shared by the whole city. Or the restaurant's prep table—pre-chopped veggies. Saves the cooks time. Not for her directly, but it speeds everything up.

Four levels. Home = client cache. Stall = edge cache. Kitchen = server cache. Prep table = database cache. Each step closer to the user means faster. Each step further means more users benefit from the same cached data. But more shared = harder to invalidate. When the recipe changes, you have to update the prep table. And the kitchen. And the stall. And hope the user's fridge gets refreshed.

The insight: you don't pick one level. You use the whole stack. Browser cache for static assets. CDN for public content. Redis for API responses. Database buffer pool for hot rows. Layers compound. Each one reduces load on the next.

---

## Another Way to See It

Water supply. Your water bottle (client)—fastest, just for you. Building water cooler (edge)—shared by the floor. City reservoir (server)—shared by the region. The main plant (database)—the source. Caching at each level. Closer = less distance, faster. Further = more people served per cache.

---

## Connecting to Software

**Level 1 — Client cache:** Browser cache. Mobile app cache. Stores images, CSS, JS, API responses locally. Zero network latency. But only helps that one user. And you can't control when they refresh.

**Level 2 — Edge cache / CDN:** Cloudflare, CloudFront, Fastly. Sits between user and origin. Serves static content from servers near the user. Helps everyone in that region. Same image cached in Tokyo and New York. Users get it from the nearest edge. Fast. Shared.

**Level 3 — Server cache:** In-memory cache in your app (HashMap, Guava). Or distributed cache (Redis, Memcached). Caches API responses, computed results. Shared by all users hitting that server or cluster. One Redis, many app servers.

**Level 4 — Database cache:** Query cache (MySQL), buffer pool (PostgreSQL, InnoDB). Caches frequently-accessed rows and pages in memory. Reduces disk reads. Helps every query. Invisible to your app. The database does it.

**The hierarchy:** User → Browser → CDN → App Server → Redis → Database → Disk. A request might be satisfied at any level. The further it goes, the slower—but the more "authoritative."

The tricky part: invalidation. User changes their name. You update the database. Now you need to invalidate browser cache, CDN cache, Redis. Miss one layer and the user sees stale data for hours. Design your invalidation strategy before you cache everywhere. Options: versioned URLs (photo_v2.jpg), short TTLs (60 seconds for dynamic data), or event-driven invalidation (publish "user 123 updated" and every layer purges). Each has trade-offs.

---

## Let's Walk Through the Diagram

```
    USER REQUEST
         │
         ▼
    ┌─────────────┐  miss   ┌─────────────┐  miss   ┌─────────────┐
    │   Browser   │ ──────> │  CDN/Edge   │ ──────> │ Server/Redis │
    │   Cache     │         │   Cache     │         │   Cache      │
    └─────────────┘         └─────────────┘         └─────────────┘
         ▲ hit                    ▲ hit                    │ miss
         │                        │                        ▼
         │                        │                 ┌─────────────┐
         │                        │                 │  Database   │
         └────────────────────────┴─────────────────│   Cache    │
              Fastest (0ms)        Fast (10ms)       │  + Disk    │
                                                    └─────────────┘
                                                    Slowest (50ms+)
```

Each layer can satisfy the request. First hit wins. No hit = next layer. Eventually the database.

---

## Real-World Examples (2-3)

**Example 1 — Static website:** HTML, CSS, JS. Cached in browser. Cached at CDN. Cached at server. Three layers. Origin server rarely hit.

**Example 2 — User profile:** Personal data. Browser might cache the API response (Cache-Control). Server caches in Redis by user_id. Database has the source. First visit: DB → Redis → browser. Next visit: browser might have it. Or Redis. Fast either way.

**Example 3 — Celebrity profile:** Same for everyone. CDN can cache it—same response for millions. Edge serves it. Origin might get 1 request per minute. Rest from edge.

The hierarchy in practice: a static asset might hit browser cache first (0ms). Miss? CDN (10ms). Miss? Origin server (50ms). Miss? Database (100ms). Each layer reduces load on the next. Design for hits at the closest layer.

---

## Let's Think Together

A user views their own profile. Which cache level helps? What about viewing a public celebrity profile?

Pause and think.

**Own profile:** Browser cache (personal), Redis (server cache by user_id). Both help. CDN less—profile is user-specific, varies by auth.

**Celebrity profile:** Same for everyone. CDN can cache it aggressively. Edge servers worldwide. Millions of fans, one cached copy per region. CDN is huge here. Plus Redis. Plus browser. All layers help.

The insight: cache what's shared. Personal data = server cache. Public data = edge cache. Know the difference.

---

## What Could Go Wrong? (Mini Disaster Story)

A team cached at every level. Browser. CDN. Redis. No coordination. A user changed their display name. Server updated the database. Redis invalidated. But the CDN had a 1-hour TTL. And the browser had a 24-hour TTL. User saw the new name in one tab. Old name in another. Old name on mobile. Complaints. "I changed it hours ago!" Caching at every level without invalidation strategy = stale data everywhere. Design your invalidation. Know your TTLs.

---

## Surprising Truth / Fun Fact

Modern web requests can be served from up to 5 different cache layers before ever reaching the origin server. Browser, CDN, load balancer cache, app server cache, database cache. Five. Most requests never hit the source. Your origin server might handle 1% of requests. The rest are satisfied by caches. That's how the web scales.

---

## Quick Recap (5 bullets)

- **Client cache:** Browser, app. Fastest. Per user. Hard to invalidate.
- **Edge cache / CDN:** Cloudflare, CloudFront. Serves region. Great for static, same-for-everyone content.
- **Server cache:** Redis, Memcached. Shared. API responses, computed data.
- **Database cache:** Buffer pool, query cache. Reduces disk I/O.
- **Hierarchy:** More layers = more complexity. Invalidation gets hard. Plan it.

---

## One-Liner to Remember

Four levels: your fridge, the stall, the kitchen, the prep table. Closer = faster. Further = more shared.

---

## Next Video

You've seen caching. Next we'll dive into more system design patterns. Stay tuned.
