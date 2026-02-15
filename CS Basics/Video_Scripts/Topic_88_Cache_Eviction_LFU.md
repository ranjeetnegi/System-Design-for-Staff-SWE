# Cache Eviction: LFU and Other Policies

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Your bookshelf holds 10 books. LRU says: remove the one you touched longest ago. But that book might be your favorite. You read it every week—you just skipped this month. LRU would evict it! LFU says: remove the one you've read the fewest times. Your favorite? Read 50 times. The new book you glanced at once? Evict that. Count matters. Not recency.

---

## The Story

Kavya has a small bookshelf. Ten books. She needs space for a new one. LRU would say: remove the book you haven't touched in the longest time. But that's her favorite novel. She reads it every few weeks. She just didn't need it this month because of exams. LRU would kick it out. Wrong. She'd be furious.

LFU says: count how many times you've read each book. The favorite? 50 reads. The new thriller she skimmed once? 1 read. Evict the one with the lowest count. The 1-read book goes. The 50-read favorite stays. Frequency over recency. Different signal. Different outcome. Use history. Not just "when did I last use it?"

LFU = Least Frequently Used. When the cache is full, evict the item with the fewest total accesses. The logic: if something was accessed often in the past, it's probably important. If it was barely touched, it's probably not.

---

## Another Way to See It

A cafe's playlist. Some songs played 1000 times. Crowd favorites. LFU keeps those. A new song played once? LFU evicts it. "But it might become popular!" Maybe. LFU bets on the past. Songs that were popular will stay popular. Risky for trends. Good for steady favorites. LFU has a blind spot: the new hot thing.

---

## Connecting to Software

**LFU vs LRU:**
- LRU asks: "When was it last used?" Recent = keep. Old = evict.
- LFU asks: "How many times was it used?" Often = keep. Rarely = evict.

**LFU problem—frequency pollution:** An item was super popular last year. 10,000 accesses. This year? Nobody cares. But LFU keeps it forever. Count is high. New trending items can't get in. The cache fills with "zombie" popular items. Solution: aging or decay. Reduce counts over time. "Access count from last hour" instead of "all time." Or periodically halve all counts. Old popularity fades. New items get a chance. Keeps the cache responsive to change.

**All eviction policies compared:**

| Policy  | Evicts by              | Pros              | Cons                    |
|---------|-------------------------|-------------------|-------------------------|
| LRU     | Oldest access time      | Simple, temporal  | Scans pollute           |
| LFU     | Fewest total accesses   | Favors hot items  | Frequency pollution      |
| FIFO    | Oldest insertion        | Trivial           | Ignores access pattern   |
| Random  | Random key              | No state, fast     | Unpredictable            |
| TTL     | Expiration time         | Natural with TTL  | Not usage-based          |

**Which to use:** LRU is the default for 90% of cases. LFU when some items are consistently hot but accessed in bursts. Random when access patterns are unpredictable or adversarial. FIFO when you don't care. TTL when you have expiration anyway. Test. Profile. Your access pattern might surprise you. A/B test LRU vs LFU. Metrics matter. Hit rate. Eviction rate. Latency. Choose based on data. And remember: LFU without aging is dangerous. Old popular items become zombies. Block new content. Add decay. Always. Periodically halve counts. Or use a sliding window. Keep the cache responsive to changing trends.

---

## Let's Walk Through the Diagram

```
    LRU vs LFU (same access pattern: A B C A A B)
    
    LRU:  Evicts C (least recently used)
    LFU:  A=3, B=2, C=1 → Evict C (least frequently used)
    
    Different scenario: A B C D E ... (scan) ... A
    LRU:  A might be evicted (was accessed long ago in the scan)
    LFU:  A has count 2, scan items have count 1 → Evict scan items. A stays.
```

```
    LFU WITH AGING
    
    Without aging:  Old popular item (count=10000) blocks new item (count=1)
    With aging:     Periodically decay counts. Old counts shrink.
                   New item has a chance. Trending items can rise.
```

---

## Real-World Examples (2-3)

**Example 1 — Music streaming:** Some songs are all-time hits. High play count. LFU keeps them. New release? Low count. Might get evicted. But new releases can trend. LRU might be better for "discover" features. LFU for "your favorites" or "top charts."

**Example 2 — CDN for videos:** Evergreen content (old popular videos) stays. One-hit viral? Might flood cache with LFU initially, then fade. Depends on pattern.

**Example 3 — Redis 4.0:** Added `allkeys-lfu` and `volatile-lfu`. Companies can choose. Access pattern matters. Test both.

---

## Let's Think Together

Music streaming app. Some songs are all-time hits. Some are trending this week. LRU or LFU for caching song metadata?

All-time hits: LFU keeps them. High count. Good. Trending: new song, low count. LFU might evict before it gets popular. LRU would keep it if it was recently played. Mixed workload = hybrid. Or use LFU with strong aging so new items can rise quickly. Or segment: "trending" cache uses LRU, "library" cache uses LFU. No one policy fits all. Know your data.

---

## What Could Go Wrong? (Mini Disaster Story)

A news site used LFU without aging. A huge story from 6 months ago had millions of reads. Count: 10 million. Still in cache. New breaking news? Count: 1. Evicted immediately. Cache filled with old headlines. New content couldn't get in. Users saw stale news. "Why is the homepage showing last year's story?" LFU without decay. Zombie data. Lesson: if you use LFU, add aging. Or use LRU for time-sensitive data.

---

## Surprising Truth / Fun Fact

Redis 4.0 added LFU eviction as an option alongside LRU. Companies can now choose based on their access patterns. Before that, LRU was the only practical choice. Now it's a config. `maxmemory-policy allkeys-lfu`. One line. Different behavior.

---

## Quick Recap (5 bullets)

- **LFU** = Least Frequently Used. Evict the item with the fewest total accesses.
- **LFU vs LRU** = frequency vs recency. Different signals. Different use cases.
- **Frequency pollution** = old popular items block new items. Use aging/decay to fix.
- **Other policies** = FIFO, Random, TTL-based, Size-based. Each has a niche.
- **Redis 4.0** = offers LFU. Choose based on your access pattern.

---

## One-Liner to Remember

*LFU: Evict the one used least often. Count matters. But add aging—or the past blocks the future.*

---

## Next Video

Next: Cache stampede—when one expired key brings down the whole system.
