# Cache Eviction: LRU Explained

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

Your desk holds 5 books. You need a 6th. Which one do you remove? The one you used most recently? No—keep that! The one you haven't touched in weeks? Yes. Remove the Least Recently Used. That simple logic. That's LRU.

---

## The Story

Vikram's desk is small. Space for 5 books. He's writing an essay. He needs a 6th book—a reference he hasn't used in a month. Which one leaves? Not the one he just opened. Not the one from yesterday. That one in the corner—dusty, untouched for weeks. The one he borrowed for a project he abandoned. That's the Least Recently Used. If he hasn't touched it in a long time, he probably won't need it soon. Out it goes. Make room for what he actually needs now.

That's LRU—Least Recently Used. When the cache is full and a new item needs space, LRU evicts the item that hasn't been accessed for the longest time. Simple. Intuitive. The logic: recent access suggests future access. Temporal locality. Things you used yesterday, you might use today. Things you used last month? Probably not. It works for most real-world patterns.

---

## Another Way to See It

Kitchen counter. Limited space. You use the salt daily. The paprika—once a year, for that one holiday dish. When you buy a new spice jar and need room, you don't toss the salt. You move the paprika to the pantry. Least recently used. Out. Same idea. Space is limited. Evict what you use least. Keep what's hot.

---

## Connecting to Software

**LRU = evict the item with the oldest access time when the cache is full.**

**How it works:** Maintain a list ordered by access time. Every time you access an item, move it to the "most recently used" end. When evicting, remove from the "least recently used" end. The back of the list is always the victim. Simple.

**Implementation—doubly linked list plus hash map:** The list gives you order. Head = most recent. Tail = least recent. The map gives you O(1) lookup: key to node. Get: find node, move to head. O(1). Put: if exists, update and move to head. If full, evict tail, add new at head. O(1). Classic interview question. Elegant.

**Why LRU is popular:** Simple. Intuitive. Works well for temporal locality. Most access patterns have this. Page views. Session data. Good default.

**When LRU fails—cache pollution:** One-time scans. A batch job reads 2000 old records. None will be read again. But they flood the cache. Each access "recent" at the moment. All the "hot" items—recently used by real users—get pushed to the tail. Evicted. Cache polluted. Hit rate crashes. LRU assumes "recently used = will use again." Scans break that assumption. One full table scan can destroy your cache.

---

## Let's Walk Through the Diagram

```
    LRU ORDER (most recent → least recent)
    
    [A] [B] [C] [D] [E]   ← E is LRU (will be evicted first)
    
    Access C:
    [C] [A] [B] [D] [E]   ← C moves to front
    
    Add F (cache full, evict E):
    [F] [C] [A] [B] [D]   ← E gone, F at front
```

```
    DATA STRUCTURE (O(1) Get and Put)
    
    HashMap: key → Node (for O(1) lookup)
    Doubly Linked List: order by access time
    Head = most recent, Tail = least recent (eviction target)
    
    Get(key): find node, move to head. O(1).
    Put(key, value): if exists, update + move to head.
                     if full, evict tail. Add new at head. O(1).
```

**Step by step:** User requests key C. We find C in the map. Move its node to the head. Now C is most recent. User adds key F. Cache full. We evict the tail—E. Add F at head. The list shrinks and grows. Order is always maintained. Access updates order. Eviction is deterministic: always the tail. The doubly linked list lets us move nodes in O(1)—just update pointers. No traversal. That's why it's fast.

---

## Real-World Examples (2-3)

**Example 1 — User sessions:** Recently active users stay in cache. Inactive users get evicted. LRU naturally keeps "hot" users. Perfect fit.

**Example 2 — Page cache (OS):** Operating systems use LRU for memory pages. Recently used pages stay. Old pages get swapped out. Decades of use. Proven.

**Example 3 — Redis:** Redis offers `allkeys-lru` and `volatile-lru`. Approximated LRU—samples 5 random keys, evicts the least recently used among them. True LRU requires tracking every key. Too expensive at scale. Approximation works.

---

## Let's Think Together

Cache has 1000 slots. A batch job reads 2000 old records. One by one. What happens?

Each read inserts into the cache. After 1000, the cache is full. The next 1000 reads evict the previous 1000. But here's the problem: the batch job's 2000 records are all "one-time" access. They won't be read again. Meanwhile, they evicted the 1000 "hot" records that real users need. Cache hit rate drops from 95% to 10%. Database overwhelmed. The batch job poisoned the cache. LRU couldn't tell "one-time scan" from "real traffic." Design for this: separate cache for batch jobs. Or cache only hot keys. Or use a different eviction policy for scan-heavy workloads.

---

## What Could Go Wrong? (Mini Disaster Story)

A reporting team ran a nightly report. Full table scan. 50,000 rows. Each row was cached (cache-aside). The cache had 10,000 slots. By the end of the scan, the cache was full of report data. User sessions, trending products, popular profiles—all evicted. Morning traffic hit a cold cache. 90% miss rate. Site slowed to a crawl. "What happened overnight?" The report. One batch job. LRU didn't discriminate. Lesson: isolate batch workloads. Or exclude them from the cache. Protect your hot data.

---

## Surprising Truth / Fun Fact

Redis uses approximated LRU. Why? True LRU requires tracking every key's access time. Memory cost is huge. Redis samples 5 random keys and evicts the least recently used among them. Good enough. At scale, "good enough" wins. Perfect is the enemy of shipped.

---

## Quick Recap (5 bullets)

- **LRU** = Least Recently Used. Evict the oldest-accessed item when full.
- **Logic** = recent use suggests future use. Temporal locality. Works for most patterns.
- **Implementation** = doubly linked list + hash map. O(1) get and put.
- **Fails when** = one-time scans pollute cache. Batch jobs evict hot data.
- **Redis** = uses approximated LRU. Samples keys. Good enough at scale.

---

## One-Liner to Remember

*LRU: When full, kick out whoever hasn't been touched the longest. Simple. Usually right.*

---

## Next Video

Next: LFU and other eviction policies—when frequency matters more than recency.
