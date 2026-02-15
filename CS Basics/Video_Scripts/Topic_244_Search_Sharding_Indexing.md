# Search System: Sharding and Indexing

## Video Length: ~4-5 minutes | Level: Staff

---

## The Hook (20-30 seconds)

A library. Not a small one. Massive. 10 buildings. Each building has its own card catalog—its own index. You search for "machine learning." Your query goes to ALL 10 buildings. Each searches its collection. Each returns its top 10 results. A coordinator MERGES them. Picks the best 10 across all buildings. Shows you. That's how large search engines work. The index is sharded across machines. Query goes to all shards. Results merged. Let's see how.

---

## The Story

Search at scale means billions of documents. One machine can't hold the index. You shard. Split the documents across multiple machines. Each shard has an inverted index: term → list of documents containing that term. "machine" → [doc1, doc5, doc99]. "learning" → [doc1, doc5, doc200]. Query "machine learning": intersect the lists. Documents in both. Rank them. Return top-K. Simple on one shard. But with 100 shards? Query goes to all 100. Each returns its top 100. Coordinator merges. 10,000 results. Re-rank. Return top 10. The scatter-gather pattern. Scatter the query. Gather the results. Merge. The coordinator is critical. And one slow shard slows everyone. Tail latency matters. A lot.

---

## Another Way to See It

Think of a treasure hunt. 10 rooms. Each room has clues. You send 10 people, one per room. "Find anything with 'gold' and 'chest'." Each person searches their room. Returns their findings. You combine. Pick the best. That's scatter-gather. The slowest person determines when you finish. If one person takes 5 minutes and others take 30 seconds, you wait 5 minutes. Same with search. One slow shard? Query latency = that shard's latency. Optimize for the tail. Replicate hot shards. Timeout slow shards. Don't let one slow shard ruin the experience.

---

## Connecting to Software

**Document-based sharding.** Documents split across shards. Shard 1: docs 1-100M. Shard 2: docs 100M-200M. Etc. Each shard has a complete inverted index for ITS documents. Query "machine learning": go to ALL shards. Each shard finds matching docs in its slice. Returns top-K. Coordinator merges. Advantage: simple. Documents don't overlap. Clean. Disadvantage: every query hits every shard. Fan-out = number of shards. 100 shards = 100 parallel queries. Coordination overhead. But it works. Elasticsearch does this. Lucene does this. Proven.

**Term-based sharding.** Each shard holds specific terms. Shard 1: terms A-M. Shard 2: terms N-Z. Query "machine learning": go to shard with "machine," shard with "learning." Less fan-out. But: documents can live on multiple shards. Complex. Rebalancing when term distribution changes. Harder to manage. Google reportedly used something like this in early days. Less common now. Document sharding won for simplicity.

**Scatter-gather.** Query to coordinator. Coordinator broadcasts to all shards. Shards search in parallel. Each returns top-K (K might be 100 or 1000). Coordinator merges. Re-ranks if needed. Returns final top-K to user. Latency = max(shard latencies) + merge time. Optimize: reduce shard count for simple queries. Or: don't wait for all. Return when you have "good enough" results. Trade completeness for speed. Depends on use case.

**Index updates.** New document arrives. Must be indexed. Which shard? Hash(doc_id) mod N. Route to that shard. Shard updates its index. Near-real-time: index in seconds. Batch: index hourly. Trade freshness for throughput. Search systems often have a lag. "Indexed 2 minutes ago." Acceptable for most use cases. Real-time search (chat, logs) needs faster. Different tradeoffs.

---

## Let's Walk Through the Diagram

```
SEARCH SHARDING - SCATTER-GATHER
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   QUERY: "machine learning"                                     │
│        │                                                         │
│        ▼                                                         │
│   COORDINATOR                                                    │
│        │                                                         │
│        ├─────────► Shard 1 (docs 1-100M)   ──► top 100           │
│        ├─────────► Shard 2 (docs 100-200M) ──► top 100           │
│        ├─────────► Shard 3 (docs 200-300M) ──► top 100           │
│        │             ...                                         │
│        └─────────► Shard N                    ──► top 100        │
│                        │                                         │
│                        ▼                                         │
│   MERGE + RE-RANK ──► Final top 10 to user                       │
│                                                                  │
│   LATENCY = max(shard latencies) + merge. One slow shard = slow. │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: User sends query. Coordinator scatters to all shards. Each shard searches its document slice. Returns top 100. Coordinator gathers. Merges. Re-ranks. Returns top 10. The scatter is parallel. The gather waits for the slowest. That's the bottleneck. In practice: timeout slow shards. Return partial results. Or replicate. More shard replicas. Better chance at least one is fast. The diagram shows the flow. Simple in concept. Complex in execution at scale.

---

## Real-World Examples (2-3)

**Elasticsearch.** Document-based sharding. Index split into shards. Query goes to all shards. Merges results. Standard pattern. Used by Wikipedia, GitHub, Netflix. Billions of documents. The open-source standard for full-text search. Proves the model.

**Amazon CloudSearch.** Managed. Same scatter-gather under the hood. You don't manage shards. AWS does. Simplicity for a cost. When you want search without the ops, managed services deliver.

**Wikipedia.** Full-text search. Elasticsearch. Every article indexed. Every search hits multiple shards. Millions of queries per day. The scale is real. The pattern holds.

---

## Let's Think Together

**"10-shard search cluster. Query goes to all 10. Shard 7 is slow—500ms. All others respond in 50ms. What's the user-visible latency?"**

500ms plus merge time. The coordinator waits for shard 7. User waits 500ms. Even though 9 shards responded in 50ms. Tail latency dominates. Mitigations: timeout. Don't wait for shard 7 past 200ms. Return results from 9 shards. Slightly incomplete. Usually acceptable. Or: replication. Shard 7 has 3 replicas. Query goes to replica 1. Maybe it's fast. Send to all 3 replicas. Use first response. Redundant requests. But better latency. Or: fix shard 7. Why is it slow? Hot shard? Bad document distribution? Rebalance. The symptom (slow query) points to the cause (one bad shard). Investigate. Fix. Tail latency is the user experience. Optimize for it.

---

## What Could Go Wrong? (Mini Disaster Story)

A search team. 50 shards. One shard has a bad disk. I/O slow. Every query that hits that shard: 2 seconds. P99 latency for search: 2 seconds. Users complain. "Search is slow." The team adds more shards. 100 shards. Problem persists. P99 still 2 seconds. Adding shards didn't help. The slow shard was the bottleneck. They finally found it. Monitoring. Per-shard latency. Shard 47: 2 seconds. Others: 50ms. Replace the disk. Problem gone. P99: 100ms. Lesson: when scatter-gather is slow, find the slow shard. Don't assume "more shards" fixes it. One bad apple ruins the batch. Monitor per-shard. Act on outliers.

---

## Surprising Truth / Fun Fact

Google's search index is estimated to be hundreds of billions of pages. The index is sharded. Heavily. Thousands of shards. Each query hits a subset—not all. Ranking is so sophisticated that they don't need to search everything. Sampling. Approximations. "Good enough" in milliseconds. The exact algorithms are secret. But the principle: at that scale, you can't scatter to everything. You optimize. Partial search. Proximity. Parallelism. The art is in the tradeoffs. We build smaller systems. The principles scale.

---

## Quick Recap (5 bullets)

- **Sharding:** Documents split across shards. Each shard has inverted index for its slice. Query hits all.
- **Scatter-gather:** Coordinator broadcasts query. Shards search in parallel. Return top-K. Merge.
- **Document sharding:** Simple. Common. Elasticsearch, Lucene. Every query fans out.
- **Tail latency:** One slow shard = slow query. Timeout. Replicate. Fix the slow shard.
- **Index updates:** Hash doc_id to shard. Near-real-time or batch. Trade freshness vs throughput.

---

## One-Liner to Remember

**Search at scale is a library with 10 buildings—your query visits all of them, and you wait for the slowest one to finish before you get your answer.**

---

## Next Video

Next: recommendation systems, candidate generation, and how Netflix knows what you want to watch.
