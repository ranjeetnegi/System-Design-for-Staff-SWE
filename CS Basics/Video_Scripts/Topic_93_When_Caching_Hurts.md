# When Caching Hurts: Stale Data and Complexity

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

You check the weather app before leaving home. "Sunny, 30°C." You wear shorts. Step outside. It's raining. The app showed cached weather from two hours ago. The cache lied. You got soaked. Caching saved the app server from load—but it gave you wrong information. Sometimes, cache helps. Sometimes, it hurts. Let's see when.

---

## The Story

Morning. You open the weather app. "Sunny. 30°C." Perfect. You wear shorts and a t-shirt. Grab your bag. Leave.

You step outside. Rain. Cold. You're soaked in 30 seconds.

What happened? The app showed cached data. The weather had changed two hours ago. Your app never refreshed. It served you a lie. The cache *saved* the server from extra API calls. But it *hurt* you. Wrong information. Wrong decision.

Cache is a trade-off. Speed vs. freshness. Most of the time it helps. But when it goes wrong, it goes very wrong. And the damage isn't always obvious. A slightly stale product description? Maybe fine. Stale medical dosage? Danger. Stale stock price before a trade? Money lost. Context matters. Not everything should be cached. And not everything should be cached for the same duration.

---

## Another Way to See It

A newspaper stand. Yesterday's paper. Cheap. Fast to grab. But if you need today's stock prices, yesterday's paper is worse than useless. It's misleading. You might buy or sell based on stale numbers. Lose money. Cache can do the same. Stale prices. Stale inventory. Stale anything that changes frequently. Dangerous.

---

## Connecting to Software

**When caching hurts:**

**1. Stale data shown to users**  
Wrong prices. Outdated stock levels. Old news. User makes a decision based on cached data. Reality is different. Trust lost. Or money lost.

**2. Complexity of invalidation**  
Multiple cache layers. Local cache. Redis. CDN. User updates their profile. Where do you invalidate? Miss one layer. Stale data persists. Debugging becomes a nightmare. "We cleared Redis. Why is it still old?" Local cache. Oops.

**3. Cold start problem**  
Server restarts. Cache is empty. Traffic hits. Every request is a miss. All go to the database. Stampede. Database overloaded. Site down. Cache was supposed to protect the DB. Empty cache does the opposite.

**4. Memory cost**  
Cache isn't free. Redis costs money. Every byte you cache is a byte you don't use for something else. Cache the wrong things, and you're wasting resources.

**5. False sense of security**  
System depends on cache. Cache goes down. All traffic hits the database. Database was never sized for that. Collapse. The rule: your system must work without cache. Slower, but it must work. Cache is an optimization. Not a requirement. Design for cache failure. Load test without cache. Know your database's limits when cache is cold. Hope for the best, plan for the worst.

---

## Let's Walk Through the Diagram

```
The invalidation nightmare:

  User updates profile in DB
           │
           ▼
  ┌─────────────────────────────────────────┐
  │  Invalidate WHERE?                       │
  │  ✓ Redis? ✓ Local cache? ✓ CDN?         │
  │  Miss one = stale data somewhere         │
  └─────────────────────────────────────────┘

  Cold start disaster:

  [Server Restart] → Cache empty
        │
  Traffic arrives → All MISSES → All hit DB
        │
  DB overloaded → Timeouts → Site down
```

---

## Real-World Examples

**1. E-commerce price display**  
Product cached at Rs 500. Price changed to Rs 450. Sale. Cache not invalidated. User sees Rs 500. Adds to cart. Checkout. Charged Rs 450 (correct in DB). User confused. Or worse: charged Rs 500 (bug). User angry. Refund. Lost trust.

**2. Stock trading app**  
Cache stock prices for 1 minute. Trader sees cached price. Clicks buy. Real price moved. Filled at different price. Trader loses money. Lawsuit. Never cache real-time financial data without extreme care.

**3. Social feed**  
User deletes a post. Cache still shows it. User refreshes. Post still there. "I deleted it. Why is it showing?" Cache invalidation missed. User thinks the app is broken.

---

## Let's Think Together

Stock trading app. Should you cache stock prices? What if the cache shows Rs 500 but the real price is Rs 450? User buys at the wrong price.

Pause. Think.

For real-time trading: no cache. Or cache with very short TTL (seconds). Or cache only for display, never for execution. Execution always hits live prices. Display can be slightly stale—with a disclaimer. The rule: if freshness affects money or safety, cache carefully or not at all.

---

## What Could Go Wrong? (Mini Disaster Story)

A bank. Account balance cached for 5 minutes. User withdraws Rs 10,000. Balance updated in DB. Cache not invalidated. User checks balance on another device. Sees old balance. Thinks withdrawal failed. Tries again. Double withdrawal? No—transaction logic prevented it. But user panicked. Called support. Hundreds of such calls. Support overwhelmed. Bad day. Root cause: caching balance without proper invalidation. Fix: don't cache balance. Or invalidate on every write. Or use very short TTL with write-through.

---

## Surprising Truth / Fun Fact

Phil Karlton said: "There are only two hard things in computer science: cache invalidation and naming things." Martin Fowler added: "and off-by-one errors." Cache invalidation has been a famous hard problem for decades. When you struggle with it, you're in good company.

---

## Quick Recap (5 bullets)

- Caching hurts when: stale data, invalidation complexity, cold start stampedes, memory cost, over-reliance on cache.
- Your system must work without cache—slower, but functional. Cache is optimization, not truth.
- Don't cache data where freshness = money or safety (e.g., stock prices, account balances) without extreme care.
- Cold start: warm the cache gradually or use probabilistic early expiration to avoid stampedes.
- When in doubt: shorter TTL, fewer layers, simpler invalidation. And always ask: "If this cache showed wrong data for 5 minutes, what would happen?" If the answer is "users lose money" or "safety risk," don't cache it. Or cache it with extreme care and very short TTL. The goal is speed. But correctness comes first. Speed with wrong data is worse than slowness with right data. Users can wait a few hundred milliseconds. They cannot make decisions on lies. When you cache, always ask: what's the cost of serving stale data? If it's high, cache less—or don't cache at all.

---

## One-Liner to Remember

*Cache is a performance optimization, not a data source—your system must work without it, and stale cache can hurt more than no cache.*

---

## Next Video

Next: Distributed cache. Redis Cluster, sharding, and how multiple nodes work together. Topic 94: Distributed Cache with Redis.
