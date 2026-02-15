# Search System: Index and Query Path

## Video Length: ~4-5 minutes | Level: Intermediate

---

## The Hook (20-30 seconds)

A library with 50 million books. Visitor: "Find all books mentioning 'machine learning' published after 2020." Without an index: scan all 50 million. Days. With an inverted index: look up "machine" → [doc1, doc5, doc99...]. Look up "learning" → [doc5, doc22, doc99...]. Intersection → [doc5, doc99...]. Filter by date. Return results. Milliseconds. That's search. Let's design it together.

---

## The Story

Search has two paths: the index path and the query path. Index path: documents arrive. We process them. Build a structure that lets us find them fast. Like a library catalog. Books arrive. Librarian catalogs. Index cards: "machine" appears in books 1, 5, 99. Query path: user asks a question. We use the index. Find matching documents. Rank them. Return. The index is the investment. The query is the payoff.

The inverted index: instead of document → words (forward), we store word → documents (inverted). "machine" → [doc1, doc5, doc99]. "learning" → [doc5, doc22, doc99]. Query "machine learning": intersect the lists. doc5, doc99. Both terms. Fast. Add ranking: which doc is more relevant? TF-IDF. Or learned ranking. Return top N.

---

## Another Way to See It

Think of a phone book. Forward: name → number. "John Smith" → 555-1234. Inverted: number → name. 555-1234 → "John Smith". Search is inverted. We don't have the query. We have words. We need: which documents have these words? Word → documents. Inverted. Like the index at the back of a textbook. "machine learning, page 45, 67, 89." Flip to index. Find pages. Fast.

---

## Connecting to Software

**Index path.** Document arrives (from DB, from crawl, from user upload). Tokenize: split into words. "Machine Learning in 2024" → ["machine", "learning", "2024"]. Lowercase. Remove stop words (optional). Stem (optional): "learning" → "learn". For each term, update inverted index: add doc_id to term's posting list. Batch or real-time. Batch: nightly job. Sync DB to search. Real-time: CDC (Change Data Capture). DB change → event → indexer. Near real-time. Store in search engine: Elasticsearch, Solr, OpenSearch. They handle the index structure.

**Query path.** Query arrives: "blue running shoes size 10". Parse: extract terms ["blue", "running", "shoes", "size", "10"]. Could be multi-field: "blue" in title, "running shoes" in category, "10" in size. Search each field. Combine. Boolean: AND (all terms) or OR (any term). Usually AND for relevance. Fetch posting lists. Intersect. Score. Rank. Return top 20. Cache frequent queries. "running shoes" searched 10K times/day. Cache the result. Sub-ms for cache hit.

**Components.** Indexer: processes documents, updates index. Index store: Elasticsearch cluster. Sharded by document or by term. Query parser: converts user query to internal representation. Ranker: scores documents. TF-IDF, BM25, or learned model. Cache: Redis or built-in. Hot queries.

**Sharding.** Index too large for one node. Shard by document ID: Shard 0 has docs 0-1M. Shard 1 has docs 1M-2M. Query: send to ALL shards. Each returns top N. Merge. Re-rank. Return global top N. Or shard by term: "a"-"m" on Shard 0, "n"-"z" on Shard 1. Query for "machine": only Shard 0. Fewer shards to query. But uneven. Document sharding is common. Equal distribution.

---

## Let's Walk Through the Diagram

```
SEARCH SYSTEM - INDEX AND QUERY
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   INDEX PATH:                                                    │
│                                                                  │
│   Document "Blue running shoes, size 10"                         │
│         │                                                        │
│         ▼                                                        │
│   Tokenize → ["blue", "running", "shoes", "size", "10"]         │
│         │                                                        │
│         ▼                                                        │
│   Update inverted index:                                         │
│   "blue"    → add doc_123                                        │
│   "running" → add doc_123                                         │
│   "shoes"   → add doc_123                                        │
│   ...                                                            │
│         │                                                        │
│         ▼                                                        │
│   Elasticsearch / Solr (index store)                             │
│                                                                  │
│   QUERY PATH:                                                    │
│                                                                  │
│   Query "blue running shoes size 10"                             │
│         │                                                        │
│         ▼                                                        │
│   Parse → ["blue", "running", "shoes", "size", "10"]            │
│         │                                                        │
│         ▼                                                        │
│   Fetch posting lists, intersect, score, rank                    │
│         │                                                        │
│         ▼                                                        │
│   Return top 20. Cache if hot query.                             │
│                                                                  │
│   SHARDING: Query → all shards → merge → top N                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Narrate it: Documents flow in. Tokenize. Update index. Terms point to documents. Query comes. Parse. Fetch lists. Intersect. Score. Return. Sharding: query hits all shards. Merge results. Search at scale. Cache hot queries. Millisecond response.

---

## Real-World Examples (2-3)

**Elasticsearch.** Powers search everywhere. E-commerce product search. Log search. Full-text. Inverted index. Sharded. Real-time indexing. Industry standard.

**Amazon product search.** "Blue running shoes size 10." Multi-field. Title, category, size, color. Each field indexed. Query combines. Faceted. "Filter by size 10." Facets from index. Fast. Billions of products.

**Slack search.** Messages. Channels. Files. One query. Multiple indices. Federated search. Merge results. Rank across types. Same principles. Different content.

---

## Let's Think Together

**"User types 'blue running shoes size 10.' How does the search system handle this multi-field query?"**

Parse into parts. "blue" → color field or title. "running shoes" → category or title. "size 10" → size field. Could be one query with field-specific clauses: title:blue AND category:running shoes AND size:10. Or treat as bag of words, search across all fields. Score higher if match in title (more important than body). Implementation: Elasticsearch multi_match. Specify fields. Boost title 2x. Combine scores. Filter: size must be 10. Boolean query: (blue AND running AND shoes) with filter size=10. Facets: show other sizes, colors. User refines. Iterative. Design: index each field. Query specifies field combination. Rank by relevance. Filter by exact match (size).

---

## What Could Go Wrong? (Mini Disaster Story)

A company adds search. One index. No sharding. Data grows. 100 million documents. Index size: 200GB. One node. Out of memory. Queries timeout. They add shards. But: reindex from scratch. 24 hours of downtime. "Search unavailable." Lesson: design for scale from start. Shard early. Reindex is painful. Plan growth. Test at 2x expected size.

---

## Surprising Truth / Fun Fact

Google's first index (1998) was 26 million pages. Fit on a few machines. Today: hundreds of billions of pages. The inverted index scaled. Same structure. Distributed. Partitioned. The 1998 idea still works. Good design lasts.

---

## Quick Recap (5 bullets)

- **Two paths:** Index (documents → tokenize → update index) and Query (parse → fetch → intersect → rank).
- **Inverted index:** Term → document list. Not document → terms.
- **Components:** Indexer, Elasticsearch/Solr, query parser, ranker, cache.
- **Sharding:** By document. Query all shards. Merge. Re-rank.
- **Multi-field:** Index each field. Query combines. Boosts. Filters.

---

## One-Liner to Remember

**Search: invert the index (word → docs), intersect the lists, rank the results.**

---

## Next Video

Next: we continue with more design problems. Rate limiting at scale. Multi-region. The journey continues.
