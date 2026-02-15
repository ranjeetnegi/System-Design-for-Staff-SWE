# Distributed Cache at Scale: Multi-Region

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

A restaurant chain with locations in Mumbai, Delhi, and Bangalore. Each kitchen caches popular recipes locally. But the HEAD CHEF at Mumbai updates a recipe. Delhi and Bangalore are still using the old recipe. For 30 seconds, different restaurants serve different food. Multi-region cache—keeping caches consistent across geographically separated locations. It's harder than it looks.

---

## The Story

Your app runs in three regions: US-East, EU-West, Asia-Pacific. A user in San Francisco updates their profile photo. A user in London views that profile 100 milliseconds later. Which cache do they hit? EU cache. Does it have the new photo? Probably not. The update landed in US. EU hasn't heard yet. Cross-region latency: 50-200ms. Synchronizing cache across that distance adds delay to every write. Or you accept staleness. Freshness vs consistency. You can't have both at zero cost. Staff engineers navigate this trade-off daily.

The challenge: users expect instant updates. "I changed my name. Why does my friend in another country still see the old one?" The answer: caches. Multiple of them. Far apart. Updating one doesn't update the others. Not instantly. Physics wins. Your job: minimize the gap. Make it acceptable. Document the behavior. Set expectations.

---

## Another Way to See It

Think of a library with branches. Main branch gets a new bestseller. Branch A and Branch B don't have it yet. Customers at Branch A ask. "We'll get it in the next delivery." That's cache replication with delay. Or: Main branch calls each branch. "We have a new book. Invalidate your 'bestsellers' list." Branches update. Eventually consistent. The call takes time. Some branches might be slow to answer. Multi-region cache is that phone tree—at internet scale, with millions of "books."

---

## Connecting to Software

**The challenge.** Cross-region latency: 50-200ms. Synchronizing cache on every write = added latency. Users wait. Or you write async. But then there's a window where caches disagree. How long? Depends on your sync strategy.

**Approach 1: Invalidation-based.** Write happens in US. Invalidate cache keys in EU and Asia. Send invalidation messages. Simple. But: invalidation is not update. After invalidation, next read = cache miss. Fetch from origin DB. Extra latency for that read. And: what if invalidation fails? Retry? Give up? Stale data until TTL expires. Invalidation is simple but creates thundering herds if many regions miss at once.

**Approach 2: Replication-based.** Write happens. Replicate the new value to all regions. Pro: next read is a hit. No extra fetch. Con: more bandwidth. Every write = N copies across N regions. And: replication is async. There's still a window. Smaller than invalidation? Often. But not zero.

**Approach 3: Tiered cache.** Local L1 cache (very short TTL, e.g., 5 seconds). Regional L2 cache (longer TTL, e.g., 60 seconds). Origin DB. L1 is fast but stale quickly. L2 is shared in region. Origin is truth. Most reads hit L1. Stale for a few seconds. Acceptable for profile photos. Not acceptable for stock prices. Choose TTL by use case.

---

## Let's Walk Through the Diagram

```MULTI-REGION CACHE - CONSISTENCY
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
|   US-EAST           EU-WEST           ASIA-PACIFIC                |
│                                                                  │
|   [User writes]     [Cache]           [Cache]                    |
|        |                |                 |                       |
|        v                |                 |                       |
|   Origin DB <----------+-----------------+                       |
|        |                |         (50-200ms lag)                   |
|        +-- invalidate -->|                                             |
|        +-- replicate -->+--> [Cache updated]                        |
|        |                                                           |
|   Options: Invalidate (simple, miss on next read)                  |
|            Replicate (bandwidth, faster next read)                |
|            Tiered L1+L2 (TTL-based freshness)                     |
│                                                                  │
└─────────────────────────────────────────────────────────────────┘```

Narrate it: User in US updates. Origin DB writes. Now: invalidate EU and Asia caches? Or replicate new value? Invalidation: caches drop the key. Next read fetches from origin. Replication: send the new value. Next read hits cache. Both have latency. Both have windows of inconsistency. The diagram shows the flow. The real work is choosing the right strategy for your data type. Profile photo? Few seconds stale is fine. Payment balance? Not fine.

---

## Real-World Examples (2-3)

**Facebook's TAO.** Distributed graph store. Caches in every region. Writes propagate. Read-your-writes consistency in home region. Cross-region: eventual. They've published on it. Billions of users. The scale demands clever caching.

**Netflix.** Regional caches for video metadata. Catalog updates propagate. Viewing history: eventually consistent. Users rarely notice. The content itself is CDN-cached. Different problem. Same multi-region story.

**Stripe.** Payment data: strict consistency. No cache for balance. Profile, config: cached with TTL. They segment by consistency requirement. Not everything needs the same SLA.

---

## Let's Think Together

**"User in US updates profile. User in EU reads profile 100ms later. EU cache still has old data. How long until they see the update?"**

Depends on strategy. Invalidation: next read after invalidation arrives = fetch from origin. So: invalidation latency + read. 100-300ms total. Replication: replication latency. 50-200ms. So: 100-200ms. Tiered with 5s L1 TTL: up to 5 seconds in worst case. Best case: invalidation hits before their read. ~100ms. Set expectations. "Profile updates may take a few seconds to appear globally." Most users accept it. Power users might complain. Document it. Build for the common case. Optimize the critical path.

---

## What Could Go Wrong? (Mini Disaster Story)

A social app. Multi-region. User A in US blocks User B. A's request hits US servers. Block recorded. User B in EU tries to view A's profile. EU cache has old data. No block. B sees the profile. A thinks they're safe. B harasses. Trust broken. The fix: critical operations like block must bypass cache or use strict consistency. Not all data can be eventually consistent. Security and safety: synchronous. Profile photo: eventual. Know the difference. One bug. Real harm. Design for it.

---

## Surprising Truth / Fun Fact

Some companies run active-active multi-region with synchronous replication for critical data. Every write goes to two regions before returning. Latency: 100ms+. They accept it for financial transactions. For social features? Async. The same company, different consistency for different data. There's no one answer. There's a matrix. Data type x consistency need x latency budget. Staff engineers fill that matrix for their system.

---

## Quick Recap (5 bullets)

- **Multi-region cache = consistency across distance.** Physics limits speed of light. Latency is real.
- **Strategies:** Invalidate (simple, cache miss), Replicate (bandwidth, faster reads), Tiered (TTL-based).
- **Trade-off:** Freshness vs latency vs bandwidth. Pick two.
- **Segment by data type:** Critical (block, payment) = strict. Nice-to-have (profile photo) = eventual.
- **Document propagation delay.** Set user expectations. "Updates may take a few seconds globally."

---

## One-Liner to Remember

**Multi-region cache is a restaurant chain with one head chef—every kitchen has a copy of the recipe, but the newest version takes time to reach all locations.**

---

## Next Video

Next: news feed design. Fan-out. When one tweet reaches millions. Different kind of scale.
