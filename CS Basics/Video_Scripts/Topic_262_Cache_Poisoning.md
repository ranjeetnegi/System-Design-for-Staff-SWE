# Cache Poisoning: How to Prevent

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A pharmacy. The pharmacist pre-fills 100 prescription bags for the day's most common medicines. Labels on each. "Aspirin." "Ibuprofen." A saboteur swaps the labels. The bag labeled "aspirin" now contains something else. Every customer who asks for aspirin gets the wrong drug. One act of tampering. Hundreds of victims. And it persists until someone notices.

That's cache poisoning. Someone puts wrong data in your cache. Every user who reads from cache gets corrupted data. It spreads. It persists. Until the cache expires or you manually clear it. Let's see how it happens—and how to stop it.

---

## The Story

Your cache stores API responses. User requests product 123. Cache misses. Backend fetches. Returns the product. Cache stores it under key `product:123`. Next user requests product 123. Cache hits. Served. Fast. Correct.

But what if the stored value is wrong? A bug stores an error response. "500 Internal Server Error" cached under `product:123`. Now every user asking for product 123 gets a 500. For minutes. Hours. Until TTL expires. That's poisoning. Unintentional, but same effect.

Or worse: an attacker. They craft a request that triggers a weird response. Malicious content. They manipulate the cache key so that key gets reused for normal users. Normal user hits the key. Gets the poisoned content. Attacker never touches that user directly. The cache does the damage.

---

## Another Way to See It

A water tank. Clean water for a building. Someone pours poison in. One pour. The tank distributes to every faucet. Everyone drinks poison. The tank—the cache—amplifies one bad input into many bad outputs. That's why poisoning is dangerous. One entry. Many victims.

---

## Connecting to Software

**How it happens:**

1. **Application bug:** Store wrong value under a key. Error response cached as success. Wrong mapping. Logic error.

2. **Race condition:** Request A and B both miss. Both fetch. A gets stale data. B gets fresh. B writes first. A overwrites with stale. Fresh data lost. Stale wins. Poisoned.

3. **Injection:** Attacker manipulates input. Cache key includes user-controlled input. Attacker sets key to overlap with another user's. Attacker poisons. Victim's request hits poisoned key. Attacker controls what victim sees.

4. **Error caching:** Upstream returns 500. Cache caches it. Key = `api:something`. Next 5 minutes, every request gets 500. Backend might be fine now. Cache serves the old error. Poisoned by good intentions—"cache everything." The fix: never cache 5xx. Only cache 2xx (and maybe 3xx). Validate status before storing. One line of code can prevent hours of outage.

5. **Cache stampede:** Popular key expires. Hundred requests miss. Hundred backend calls. Backend overloaded. All get errors or partial data. All cache the bad response. Poisoned. Solution: "request coalescing" or "lock" — only one request fetches; others wait. Or "probabilistic early expiration" — refresh before TTL for hot keys. Prevent the stampede.

---

## Let's Walk Through the Diagram

```
Normal flow:
  User -> Cache (miss) -> Backend -> Response -> Cache (store) -> User
  User -> Cache (hit) -> User  ✓

Poisoned flow:
  Attacker -> Cache (miss) -> Backend -> Malicious response
       -> Cache (store under key X)
  Victim -> Cache (hit, key X) -> Malicious response  ✗

One poison, many victims.
TTL = 5 min -> 5 min of damage
```

---

## Real-World Examples (2-3)

**CDN cache poisoning:** Attacker sends request with special headers. CDN caches response. Key includes header. Attacker tricks CDN into caching error page or malicious content. Legitimate users get it. Major CDNs have had such issues.

**API error caching:** Health check returns 500 during deploy. Cached. Load balancer keeps serving cached 500. "Service unhealthy." Backend is fine. Cache says no. Clearing cache fixes it. Don't cache errors.

**Web cache deception:** User requests `example.com/user/123/profile.css`. Server returns profile HTML (wrong content-type). Cache stores under that URL. Next user requests same URL (maybe via link). Gets profile HTML. User 123's private data leaked. Cache key + response mismatch = poisoning. The fix: never cache responses that vary by user (session, auth) under a key that doesn't include user identity. Or use Cache-Control: private for user-specific content. CDNs and caches must respect it.

**HTTP request smuggling + cache poisoning:** Attackers chain vulnerabilities. Malformed requests. Cache stores malicious response under a key that legitimate users will request. Complex. But real. Defense in depth: validate inputs, sanitize cache keys, avoid caching user-dependent responses under shared keys.

---

## Let's Think Together

**Question:** Your API returns a 500 error. The cache layer caches it for 5 minutes. What happens to all users for the next 5 minutes?

**Answer:** Every user who would have hit that cache key gets the 500. Even if the backend recovers in 10 seconds, the cache keeps serving the error for 5 minutes. Users think the service is down. Support gets flooded. Revenue lost. Social media lights up. Fix: never cache 5xx errors. Or use very short TTL (10 seconds max) if you must. Better: validate before caching. If response status is 4xx or 5xx, don't cache. Or set Cache-Control: no-store for error responses so caches won't store them. One check. Saves hours of pain.

---

## What Could Go Wrong? (Mini Disaster Story)

A retail site. Product API. Bug: sometimes returns another product's data—wrong ID in a join. Rare. One in 10,000. That wrong response gets cached. Product 456 cached under key for product 789. Every customer looking at product 789 sees product 456. Price wrong. Description wrong. Orders get wrong items. Chaos. The bug is in the app. But the cache amplifies it. One wrong response becomes thousands. The lesson: validate before caching. Sanity check. Don't cache responses that look wrong.

---

## Surprising Truth / Fun Fact

Cache poisoning has been used in real attacks. Security researchers have shown how to poison shared caches to steal credentials, inject malware, or deface sites. The fix: cache key sanitization. Never include unsanitized user input in cache keys. Whitelist. Validate. Treat the cache as part of your attack surface.

---

## Quick Recap (5 bullets)

- **Poisoning** = wrong data in cache; served to many users until TTL expires
- **Causes** = bugs, race conditions, key injection, caching errors
- **Prevention** = don't cache 5xx; validate before cache; sanitize keys
- **Impact** = one bad entry = many victims; cache amplifies
- **Recovery** = purge key or wait for TTL; fix root cause

---

## One-Liner to Remember

**Cache poisoning: one bad store, many bad reads—validate before caching, never cache errors, sanitize keys.**

---

## Next Video

Up next: Stale reads. When a few seconds of lag is fine—and when it's a catastrophe. The weather vs. banking test.
