# Cache Key Design: What to Include

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A filing cabinet. Each drawer has a label. Too vague—"documents"—and you'll mix everything up. Wrong things in wrong drawers. Too specific—"John-Smith-tax-return-2024-page-3"—and finding anything takes forever. You'll never reuse that slot.

Cache keys are labels for your cached data. Too generic, you serve wrong data. Too specific, you never get a cache hit. The key design decides whether your cache helps or hurts. Let's get it right.

---

## The Story

You're caching API responses. User profile. Product details. Search results. Each response needs a key. Something unique. So when the same request comes again, you find the cached response. No recompute. Fast. A well-designed cache can turn 1000 database queries per second into 10—the rest served from memory. But only if the keys are right.

What makes a good key? It must capture everything that affects the response. If the response depends on user ID, include it. On language? Include it. On role? Include it. If you forget one, you'll serve the wrong response. User A gets User B's data. Disaster. If you include too much—request ID, timestamp, random token—every request is "unique." No hits. Cache is useless.

The balance: include what varies and matters. Omit what doesn't.

---

## Another Way to See It

A lock and key. The key must match the lock. Too many teeth—too specific—and almost no key fits. Too few teeth—too generic—and the wrong key opens the door. Cache key is the same. Must be specific enough to be correct. Generic enough to be reusable. The right number of "teeth."

---

## Connecting to Software

**What to include:** Resource type + identifier + relevant parameters. `user:123:profile`. `product:456:details:en-US`. `order:789:summary`. If the response changes when a parameter changes, that parameter is in the key.

**Include what varies:** Language (en-US vs. hi-IN). User role (admin vs. user). API version (v1 vs. v2). Pagination might be in the key—page 1 and page 2 are different responses. Category filter. Sort order. All of these affect the response. All belong in the key.

**Don't include what doesn't matter:** Timestamp (changes every request = never cached). Request ID (unique = never cached). Random nonces. Session IDs if the response is the same for all sessions. These destroy hit rate.

**Namespacing:** Prefix keys. `order-service:order:789`. `user-service:user:123`. Prevents collisions. Different services, different key spaces. Clear. Safe. When debugging, you can list all keys for a service: `order-service:*`. Or invalidate a whole namespace: delete `order-service:*` (careful in production!). Namespacing is also useful for multi-tenancy: `tenant:acme:user:123`. Isolate tenant data. No accidental cross-tenant cache hits.

**Key length and character set:** Some caches (e.g., Memcached) have key length limits (250 bytes). Long keys = problems. Keep keys readable but not excessive. Use alphanumeric, colons, hyphens. Avoid spaces, special characters that might need encoding. Consistency helps—pick a convention and stick to it across the team.

---

## Let's Walk Through the Diagram

```
BAD keys:
  "profile"              -> Too generic. Whose profile? Wrong data.
  "req-7f3a-9b2c-..."    -> Request ID. Unique. Never hits.
  "data:1699123456"      -> Timestamp. Changes every second. No hits.

GOOD keys:
  user:123:profile
  product:456:en-US:details
  orders:user:123:page:1:sort:date

Structure: [namespace]:[resource]:[id]:[params...]
Include: what changes the response
Exclude: what doesn't
```

---

## Real-World Examples (2-3)

**E-commerce product page:** `product:{id}:{lang}:{currency}`. Same product, different language or currency = different response. Both in key. Hit rate: high for popular products.

**User feed:** `feed:user:{id}:page:{n}:filter:{filter}`. User, page, filter. All affect the feed. Cached. Next user with same params gets the cache. Often not—feeds are personalized. But shared content (trending) might use `feed:trending:region:{region}`. Reuse.

**API gateway:** `api:GET:/products:v1:category=electronics:page=1`. Method, path, version, query params. Full request signature. Correct. Reusable for identical requests. The gateway might cache responses for a short TTL. Same key = same cached response. Different user? If the response is user-agnostic (public product list), one cache entry serves all. If user-specific, include user ID in the key.

**Search results:** `search:query:{hash}:filters:{hash}:page:{n}`. The query might be long—hash it. Same query + same filters + same page = same key. Searches are expensive. Caching helps. But search results can change (new products added). Short TTL or invalidation on product creation. Key design plus invalidation strategy = complete picture.

---

## Let's Think Together

**Question:** API returns product list filtered by category, sorted by price, paginated. What's a good cache key?

**Answer:** `products:category:{category}:sort:price:page:{n}`. Category affects results. Sort affects order. Page affects which slice. All in the key. Maybe add `region` or `lang` if the catalog differs. Maybe exclude `page` if you cache the full result set and paginate in memory—depends on size. The principle: every parameter that changes the response belongs in the key. Nothing more. Order of parameters in the key can matter for cache efficiency—put the most discriminative parts first (e.g., user ID before page number) so that similar keys are grouped. Helps with cache locality if your cache supports prefix scanning.

---

## What Could Go Wrong? (Mini Disaster Story)

A team caches product pages with key `product:{id}`. Product has price. Price changes. Cache still has old price. User sees $99. Actual price $79. Sale missed. Or worse: user sees $79. Actual $99. Checkout fails. The lesson: if data changes, either short TTL or include version/timestamp. Or invalidate on update. Key design isn't just structure—it's knowing when cached data goes stale.

---

## Surprising Truth / Fun Fact

Some systems use content-based keys. Hash the request. Same request = same hash = same key. No need to manually design. But collision risk—different requests, same hash (rare but possible). And debugging is hard—"what does key a7f3b2 mean?" Explicit keys are clearer. Hybrid: `products:hash(a7f3b2)`—namespace + hash. Best of both. For complex APIs with many parameters, hashing avoids key length explosion. For simple cases, explicit keys win. Choose based on complexity and debuggability needs. When in doubt, start explicit. Add hashing only when keys get unwieldy. Iterate. Good key design is often discovered, not designed upfront. Monitor hit rates. Adjust. The cache will tell you if your keys are working. Pay attention to it.

---

## Quick Recap (5 bullets)

- **Include** = resource type, identifier, all parameters that change the response
- **Exclude** = timestamp, request ID, anything that makes every request unique
- **Namespacing** = prefix with service/resource; avoid collisions
- **Structure** = `service:resource:id:param1:param2`—consistent, readable
- **Validate** = would two different requests produce the same response? Then same key.

---

## One-Liner to Remember

**Cache key: include what varies and matters; exclude what makes every request unique—so you get correct, reusable hits.**

---

## Next Video

Up next: Cache poisoning. When wrong data gets into your cache—and stays. How to prevent it.
