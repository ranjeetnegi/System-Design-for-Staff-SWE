# URL Shortener: High-Level Design and Flow

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Two flows. That's all a URL shortener really is. Write: user gives long URL, you generate a short code, store the mapping, return the short URL. Read: user clicks short URL, you look up the code, 301 redirect to the long URL. Simple! But the devil is in the details. How do you generate unique codes? What if two collide? Which database do you pick? Let's design this system together.

---

## The Story

The write path is your creation moment. A user pastes a monster link. Your system must produce a tiny, unique identifier. That identifier becomes the key in your lookup table. The read path is your performance moment. A user clicks. They expect to land on the destination in under 100 milliseconds. No one waits for a sluggish redirect. So: generation must be collision-free. Lookup must be blazing fast.

Think of it like a coat check. You hand over your coat (long URL). The attendant gives you a numbered tag (short code). You store the mapping: tag 42 → coat. Later, you return the tag. Attendant looks up 42, hands you the coat. The system only works if every tag is unique and lookups are instant. Same idea.

---

## Another Way to See It

Imagine a massive phone book. Names (long URLs) on one side. Numbers (short codes) on the other. When someone asks for "Smith," you flip to the index, find the number, dial. The index is everything. If two Smiths share a number, chaos. If the index is slow, everyone waits. Your shortener's database is that index—and it must be perfect.

---

## Connecting to Software

**Code generation—three approaches.** (1) Hash the URL: MD5 or SHA, take first 7 chars. Fast. But collision possible—two different URLs could hash to the same prefix. Add retry logic or append a random suffix. (2) Auto-incrementing counter plus base62 encode. No collision. But the counter becomes a bottleneck at scale—needs to be distributed (Snowflake, etc.). (3) Pre-generated pool. Generate millions of codes offline, store in a queue. Servers grab from the pool. No collision, no single-point bottleneck. Bitly uses something like this.

**Database choice.** Key-value store—DynamoDB, Redis—is ideal. Lookup by short code is your primary access pattern. O(1) by key. Relational works too—PostgreSQL with an index on short_code. But KV is simpler, faster for this use case.

**Caching.** Hot URLs—frequently clicked—get cached in Redis. Most redirects served from cache. Cache miss? Hit DB, populate cache, redirect. Aim for 99%+ hit rate on the read path. The cache stores short_code to long_url. TTL of 24 hours or more is common. Expired URLs? Rare. Cached forever until evicted. The write path is simpler: generate, store, return. No caching needed there.

---

## Let's Walk Through the Diagram

```
                    WRITE PATH
┌─────────┐   POST long URL   ┌──────────┐   Generate   ┌─────────────┐   Store   ┌──────────┐
│  User   │ ───────────────► │   API    │ ───────────► │   Code      │ ────────► │ Database │
└─────────┘                  │  Server  │   short_code │   Gen       │  mapping  │  (KV)     │
                             └──────────┘              └─────────────┘           └──────────┘
                                    │
                                    └── Returns: https://short.ly/abc123

                    READ PATH
┌─────────┐   GET /abc123    ┌──────────┐   Check      ┌──────────┐   Miss?    ┌──────────┐
│  User   │ ──────────────► │   API    │ ───────────► │  Redis   │ ─────────► │ Database │
└─────────┘                 │  Server  │   Cache      │  Cache   │   Lookup   └──────────┘
       ▲                    └──────────┘              └────┬─────┘
       │                           │                      │ Hit?
       │     301 Redirect          │                      └── Return long_url
       └──────────────────────────┘
```

User hits API. API checks cache first. Hit? Redirect immediately. Miss? Query DB, cache the result, redirect. Every redirect should feel instant. Sub-50ms from click to redirect is the goal. Cache hit: 1–2ms. Cache miss plus DB: 10–20ms. Still under 100ms. The 301 redirect tells browsers and caches to remember the mapping. Future clicks can be cached by the CDN or browser. A 302 would mean temporary—browsers might not cache as aggressively. Use 301 for permanent redirects. 302 if you need flexibility (e.g., A/B testing, geo-routing).

---

## Real-World Examples

**Bitly** uses a combination of hashing and custom logic for code generation, with a pre-warmed pool for high throughput. **TinyURL** started with sequential IDs—simple but doesn't scale to millions. **Rebrandly** focuses on custom branded links—same tech, different product twist. All rely on fast key-value lookups and aggressive caching for redirects.

---

## Let's Think Together

**"Two users submit the same long URL simultaneously. Should they get the same short code or different ones?"**

Both are valid. Same code: saves storage, deduplication. Implement with a unique constraint on the long URL in the database, or a check-then-insert with a unique index. Idempotent. Multiple requests for the same URL return the same short link. Analytics can still track clicks at the redirect layer by logging each request. Different codes: each user gets their own link, analytics stay separate. Most systems choose same code for the same URL—storage efficiency, and you can still track clicks at the redirect layer. Implement it with a "check if exists, else create" pattern. First writer wins; second gets the same short URL.

---

## What Could Go Wrong? (Mini Disaster Story)

You launch with hash-based generation. Two popular URLs collide—same 7-char prefix. One user's link redirects to the wrong site. Complaints flood in. You scramble to add collision detection, but the damage is done. Trust is lost. Lesson: choose your generation strategy carefully. Collisions in a shortener are unacceptable. Test with real-world URL distributions before you scale.

---

## Surprising Truth / Fun Fact

Goo.gl (Google's shortener, retired in 2019) used to serve over 20 billion redirects per month. The redirect endpoint was one of the most heavily trafficked services Google ever ran. And it was "just" a lookup and redirect. Simplicity at massive scale.

---

## Quick Recap

- Two flows: write (shorten + store) and read (lookup + redirect).
- Code generation: hash (collision risk), counter+base62 (distributed ID needed), or pre-generated pool.
- Database: key-value store ideal; index on short_code for relational.
- Caching: Redis for hot URLs; most redirects from cache.
- Same URL twice: same short code saves storage; deduplication wins. First writer wins. Idempotent API. Predictable behavior. The design choices—hash vs counter vs pool—affect scalability. Hash is simplest to implement. Counter needs distributed ID generation. Pool needs background job. Pick based on your expected write rate and operational complexity.

---

## One-Liner to Remember

*A URL shortener is write-once, read-many: generate unique, store fast, cache aggressively.*

---

## Next Video

Next, we tackle scale. What breaks when you hit 100M URLs and 100K reads per second? Cache, database, and the hidden bottlenecks. See you there. Design supports all three generation approaches; pick based on load and ops. Design supports all three generation approaches; pick based on load and ops.
