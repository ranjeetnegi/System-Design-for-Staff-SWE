# Chapter 40: Search System (Single Cluster)

---

# Introduction

Search is the single feature users reach for when they can't find what they need through navigation. When a user types a query into a search box, they expect results in under 200 milliseconds—relevant, ranked, and ready. Behind that instant response is an inverted index, a query parser, a ranking pipeline, and a serving layer that together handle thousands of queries per second while indexing millions of documents.

I've built search systems that served 10K queries/second across billions of documents, debugged ranking bugs where a single misconfigured boost made irrelevant results appear first, and handled incidents where a bad indexing job corrupted the entire search index and we had to rebuild from scratch during peak traffic. The difference between a search system that users trust and one they abandon is relevance—and relevance is not a single algorithm, it's an end-to-end engineering discipline.

This chapter covers search as a Senior Engineer owns it: indexing, query processing, ranking, and the operational reality of keeping results fast and relevant at scale.

**The Senior Engineer's First Law of Search**: A search system that returns results fast but irrelevant is worse than one that's slow. Users tolerate 500ms; they don't tolerate garbage.

**Staff one-liner**: Relevance is not an algorithm—it's an operational concern. You measure it (CTR, zero-result rate), you regress-test it before config changes, and you own it when it breaks.

---

# Part 1: Problem Definition & Motivation

## What Is a Search System?

A search system ingests documents (products, articles, users, messages), builds an index optimized for text matching, accepts user queries, and returns a ranked list of relevant results. It bridges the gap between what the user is looking for and the content that exists.

### Simple Example

```
SEARCH SYSTEM OPERATIONS:

    INDEX:
        New product added to catalog
        → Extract searchable fields (title, description, category)
        → Tokenize and normalize text ("Running Shoes" → ["running", "shoe"])
        → Update inverted index (shoe → [doc_42, doc_87, doc_193])

    QUERY:
        User types "red running shoes"
        → Parse query → tokenize → ["red", "running", "shoe"]
        → Look up each token in inverted index
        → Intersect/union posting lists
        → Score and rank results
        → Return top 10 results in < 200ms

    UPDATE:
        Product price changes
        → Update document in index
        → Ranking may change (price affects score)
```

## Why Search Systems Exist

Search exists because browsing doesn't scale. When a catalog has 10 items, users browse. When it has 10 million items, users search.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    WHY BUILD A SEARCH SYSTEM?                               │
│                                                                             │
│   WITHOUT SEARCH:                                                           │
│   ├── Users browse categories (works for small catalogs)                    │
│   ├── SQL LIKE '%query%' (full table scan, no ranking, no relevance)        │
│   ├── No typo tolerance ("runnning shoes" → 0 results)                      │
│   ├── No synonym handling ("sneakers" ≠ "running shoes")                    │
│   └── Latency: seconds to minutes on large datasets                         │
│                                                                             │
│   WITH SEARCH:                                                              │
│   ├── Sub-200ms response on millions of documents                           │
│   ├── Relevance ranking (best results first)                                │
│   ├── Typo tolerance ("runnning" → "running")                               │
│   ├── Synonym expansion ("sneakers" → also matches "running shoes")         │
│   ├── Faceted filtering (category, price range, brand)                      │
│   └── Autocomplete and suggestions                                          │
│                                                                             │
│   KEY INSIGHT:                                                              │
│   Search is NOT a database query. It's an information retrieval system      │
│   with fundamentally different data structures (inverted index, not B-tree) │
│   and different optimization goals (relevance, not ACID).                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Problem 1: The Scale of Text Matching

```
CHALLENGE:

10 million products in catalog
    - Average 500 words per document (title + description)
    - 5 billion word-document pairs
    - User expects results in < 200ms

SQL approach: SELECT * FROM products WHERE description LIKE '%running shoes%'
    - Full table scan: O(N × L) where N = rows, L = text length
    - No ranking
    - No typo handling
    - Latency: 5-30 seconds on 10M rows

Search approach: Inverted index lookup
    - "running" → posting list of 50,000 document IDs
    - "shoes" → posting list of 80,000 document IDs
    - Intersection: 12,000 documents match both
    - Rank top 10: < 50ms
    - Total: < 200ms

WHY: Inverted index pre-computes "which documents contain this word"
    Query time is proportional to result set, not corpus size.
```

### Problem 2: Relevance Is Hard

```
RELEVANCE CHALLENGES:

Query: "apple"
    Does the user want:
    - Apple the fruit?
    - Apple the company?
    - Apple pie recipes?

Query: "cheap hotel NYC"
    Ranking factors:
    - Text match: Does the listing mention "cheap"?
    - Price: Is it actually cheap?
    - Location: Is it in NYC?
    - Recency: Is the listing current?
    - Popularity: Do other users book it?

RELEVANCE IS NOT JUST TEXT MATCHING:
    - TF-IDF: How important is this word in this document?
    - BM25: Improved TF-IDF with document length normalization
    - Boost factors: Price, popularity, recency
    - Personalization: User's past behavior
    - Freshness: Recently updated content ranks higher

A SEARCH SYSTEM MUST COMBINE:
    1. Text relevance (does it match the query?)
    2. Quality signals (is this a good result regardless of query?)
    3. Business rules (promoted results, in-stock items first)
```

### Problem 3: Freshness vs Throughput

```
INDEXING TRADE-OFF:

BATCH INDEXING (rebuild entire index):
    + Simple
    + Consistent
    - Stale: New products not searchable for hours
    - Expensive: Full rebuild on every change

REAL-TIME INDEXING (update index on every change):
    + Fresh: New products searchable in seconds
    - Complex: Concurrent reads and writes on index
    - Risk: Bad document can corrupt live index

NEAR-REAL-TIME (NRT) INDEXING (chosen):
    + Fresh enough: Documents searchable within 1-5 seconds
    + Safe: Buffered writes, periodic commit
    - Small staleness window
    
    This is the standard for production search systems.
```

## What Happens Without a Proper Search System

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SYSTEMS WITHOUT PROPER SEARCH                            │
│                                                                             │
│   FAILURE MODE 1: SQL LIKE QUERIES                                          │
│   Full table scan on every query                                            │
│   5+ second latency on large tables                                         │
│   No relevance ranking → users see random matching rows                     │
│                                                                             │
│   FAILURE MODE 2: NO TYPO TOLERANCE                                         │
│   "runnning shoes" → 0 results                                              │
│   User thinks the product doesn't exist                                     │
│   Lost sale / lost engagement                                               │
│                                                                             │
│   FAILURE MODE 3: STALE INDEX                                               │
│   New product added but not searchable for hours                            │
│   Customer support: "I added it but can't find it"                          │
│   Manual workarounds: Direct links instead of search                        │
│                                                                             │
│   FAILURE MODE 4: NO RANKING                                                │
│   Results in arbitrary order (insertion time, alphabetical)                 │
│   Best result buried on page 3                                              │
│   Users give up after first page                                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Mental Model

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              SEARCH SYSTEM: THE LIBRARY CARD CATALOG ANALOGY                │
│                                                                             │
│   CATALOGING (Indexing):                                                    │
│   - Librarian reads each book                                               │
│   - Creates index cards: one per keyword                                    │
│   - Card says: "Running" → Shelf 3, Book 42; Shelf 7, Book 87               │
│   - This is the INVERTED INDEX                                              │
│                                                                             │
│   SEARCHING (Query):                                                        │
│   - Patron asks: "Books about running shoes"                                │
│   - Librarian pulls "running" card → Books 42, 87, 193                      │
│   - Librarian pulls "shoes" card → Books 42, 150, 193                       │
│   - Intersection: Books 42 and 193 (match BOTH)                             │
│   - Rank: Book 42 has "running shoes" in the title → rank #1                │
│                                                                             │
│   KEY INSIGHTS:                                                             │
│   1. Index is built ONCE (or incrementally), queried MANY times             │
│   2. Query time depends on RESULT SET SIZE, not total books                 │
│   3. Ranking decides which results the patron sees first                    │
│   4. Typo tolerance = "runnning" → "Did you mean: running?"                 │
│   5. Synonyms = "sneakers" card points to "shoes" card                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 2: Users & Use Cases

## Primary Users

### 1. End Users (Searchers)
- Type queries into search box
- Expect fast, relevant results
- Use filters (price, category, date)
- Expect typo tolerance and autocomplete

### 2. Content Producers / Admin
- Add, update, delete documents in the catalog
- Expect changes reflected in search quickly
- Configure boost rules (promote certain results)
- Manage synonyms, stop words

### 3. Platform Engineering Team
- Monitor search latency and relevance
- Manage search infrastructure (index, shards, replicas)
- Respond to search quality issues

## Core Use Cases

### Use Case 1: Full-Text Search

```
PATTERN: User searches for products/content

Flow:
1. User types "wireless bluetooth headphones"
2. Query hits search API
3. Tokenize: ["wireless", "bluetooth", "headphone"]
4. Look up inverted index for each token
5. Intersect posting lists
6. Score with BM25 + boost factors
7. Apply filters (price < $100, in stock)
8. Return top 10 with snippets

// Pseudocode: Search query
FUNCTION search(query_string, filters, page=0, size=10):
    // Parse and tokenize
    tokens = tokenize(query_string)
    tokens = apply_synonyms(tokens)         // "headphones" → ["headphone", "earphone"]
    tokens = apply_stemming(tokens)         // "running" → "run"
    
    // Retrieve candidates from inverted index
    posting_lists = []
    FOR token IN tokens:
        posting_lists.append(inverted_index.get(token))
    
    // Intersect (AND semantics by default)
    candidate_docs = intersect(posting_lists)
    
    // Apply filters
    IF filters:
        candidate_docs = apply_filters(candidate_docs, filters)
    
    // Score and rank
    scored = []
    FOR doc_id IN candidate_docs:
        score = bm25_score(tokens, doc_id)
        score += boost_score(doc_id)        // Popularity, recency, etc.
        scored.append((doc_id, score))
    
    // Sort by score descending
    scored.sort(by=score, descending=true)
    
    // Paginate
    results = scored[page * size : (page + 1) * size]
    
    // Fetch full documents
    documents = document_store.get_batch([r.doc_id FOR r IN results])
    
    RETURN {
        hits: documents,
        total: len(candidate_docs),
        took_ms: elapsed()
    }
```

### Use Case 2: Autocomplete / Typeahead

```
PATTERN: Suggestions as user types

Flow:
1. User types "blue" → suggest ["bluetooth headphones", "blue jeans", "blueberry"]
2. Prefix lookup on suggestion index
3. Return top 5 suggestions ranked by popularity

// Pseudocode: Autocomplete
FUNCTION autocomplete(prefix, limit=5):
    // Prefix lookup on a trie or prefix index
    candidates = suggestion_index.prefix_search(prefix.lower())
    
    // Rank by popularity (query frequency)
    candidates.sort(by=popularity, descending=true)
    
    RETURN candidates[:limit]

INDEX STRUCTURE:
    Separate from main search index
    Optimized for prefix matching (trie or edge-ngram)
    Updated with popular query terms
```

### Use Case 3: Faceted Search (Filtering + Counts)

```
PATTERN: User filters results by category, price, brand

Flow:
1. User searches "laptop"
2. Results include facet counts:
   - Brand: Dell (42), HP (38), Apple (35)
   - Price: $0-500 (30), $500-1000 (55), $1000+ (30)
   - Category: Electronics (115)
3. User clicks "Apple" → results filtered to Apple laptops

// Pseudocode: Faceted search
FUNCTION search_with_facets(query, filters, facet_fields):
    // Get search results (same as above)
    candidate_docs = search_candidates(query, filters)
    
    // Compute facet counts
    facets = {}
    FOR field IN facet_fields:
        facets[field] = compute_facet_counts(candidate_docs, field)
    
    // Score and paginate
    results = score_and_paginate(candidate_docs)
    
    RETURN {
        hits: results,
        facets: facets
    }

FACET IMPLEMENTATION:
    Doc values / column store: Pre-computed per-field values
    Efficient aggregation without loading full documents
```

### Use Case 4: Document Indexing

```
PATTERN: New or updated document added to index

Flow:
1. Product service creates/updates product
2. Indexing pipeline receives event
3. Extract searchable fields
4. Tokenize and normalize
5. Update inverted index
6. Document searchable within 1-5 seconds

// Pseudocode: Indexing
FUNCTION index_document(document):
    doc_id = document.id
    
    // Extract searchable fields
    text_fields = {
        "title": document.title,
        "description": document.description,
        "brand": document.brand,
        "category": document.category
    }
    
    // Tokenize each field
    FOR field, text IN text_fields:
        tokens = tokenize(text)
        FOR token IN tokens:
            inverted_index.add(token, doc_id, field, position)
    
    // Store document for retrieval
    document_store.put(doc_id, document)
    
    // Update filter/facet data
    facet_store.put(doc_id, {
        price: document.price,
        category: document.category,
        brand: document.brand,
        in_stock: document.in_stock
    })
    
    // Commit (NRT: buffered, committed periodically)
    // Document searchable after next refresh (1-5 seconds)

DELETION:
    FUNCTION delete_document(doc_id):
        inverted_index.mark_deleted(doc_id)
        document_store.delete(doc_id)
        // Actual removal during segment merge (background)
```

## Non-Goals (Out of Scope for V1)

| Non-Goal | Reason |
|----------|--------|
| ML-based ranking | V2; BM25 + boosts sufficient for V1 |
| Personalized search | Requires user behavior data; V2 |
| Image search | Different indexing pipeline; separate system |
| Cross-language search | Single-language V1; add analyzers in V2 |
| Distributed (multi-cluster) | Single cluster scope |
| Spell correction (advanced) | Basic fuzzy matching only for V1 |

## Why Scope Is Limited

```
SCOPE LIMITATION RATIONALE:

1. BM25 RANKING ONLY (no ML)
   Problem: ML ranking requires training data, feature engineering, model serving
   Decision: BM25 + configurable boosts
   Acceptable because: BM25 is industry-proven for text relevance; ML is additive

2. SINGLE CLUSTER
   Problem: Multi-cluster requires cross-cluster query fan-out
   Decision: Single cluster with sharding
   Acceptable because: Scales to billions of documents within one cluster

3. NEAR-REAL-TIME (not real-time)
   Problem: True real-time requires transactional index updates
   Decision: 1-5 second indexing delay
   Acceptable because: Users don't notice 5-second delay for new content

4. NO PERSONALIZATION
   Problem: Personalization requires user model, click data pipeline
   Decision: Same results for same query (deterministic)
   Acceptable because: Reduces complexity; add personalization when you have data
```

---

# Part 3: Functional Requirements

## Core Operations

### SEARCH: Execute a Query

```
OPERATION: SEARCH
INPUT: query_string, filters{}, sort_by, page, page_size
OUTPUT: hits[], total_count, facets{}, took_ms

BEHAVIOR:
1. Parse query string (tokenize, stem, expand synonyms)
2. Look up tokens in inverted index
3. Combine posting lists (AND/OR)
4. Apply filters (range, term, boolean)
5. Score candidates (BM25 + boosts)
6. Sort by score (or custom sort)
7. Paginate
8. Fetch document bodies
9. Generate snippets (highlighted matches)
10. Return results

ERROR CASES:
- Empty query → Return popular/trending items (or error)
- Query too long (> 256 chars) → Truncate and warn
- Invalid filter field → 400 error
- Timeout (> 5s) → Return partial results or 504
```

### INDEX: Add or Update a Document

```
OPERATION: INDEX
INPUT: document_id, document_body
OUTPUT: success/failure, indexing_lag_ms

BEHAVIOR:
1. Validate document schema
2. Extract searchable fields
3. Analyze text (tokenize, stem, normalize)
4. Write to in-memory buffer (segment)
5. Periodically flush to disk (every 1 second)
6. Refresh reader (make searchable, every 1-5 seconds)

UPSERT SEMANTICS:
    Same document_id → Replaces previous version
    Old version marked as deleted; new version indexed
    Actual cleanup during segment merge (background)
```

### DELETE: Remove a Document

```
OPERATION: DELETE
INPUT: document_id
OUTPUT: success/failure

BEHAVIOR:
1. Mark document as deleted in current segment
2. Document excluded from search results immediately
3. Physical removal during next segment merge
```

### SUGGEST: Autocomplete

```
OPERATION: SUGGEST
INPUT: prefix (partial query)
OUTPUT: suggestions[] with popularity scores

BEHAVIOR:
1. Lowercase and normalize prefix
2. Prefix lookup on suggestion index
3. Rank by popularity / frequency
4. Return top 5-10 suggestions
```

---

## Expected Behavior Under Partial Failure

| Scenario | System Behavior | User Impact |
|----------|-----------------|-------------|
| **One shard slow** | Timeout after 500ms, return results from other shards | Partial results; may miss some matches |
| **Indexing pipeline down** | New documents not indexed; search still serves | Results become stale over time |
| **Replica unavailable** | Route queries to other replicas | Slightly higher load on remaining replicas |
| **Document store slow** | Return results without full body (IDs + scores only) | Degraded results display |
| **Full index corruption** | Fail over to replica; rebuild from source | Brief degraded availability |

---

# Part 4: Non-Functional Requirements (Senior Bar)

## Latency Targets

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LATENCY REQUIREMENTS                                │
│                                                                             │
│   SEARCH QUERY:                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  P50: < 50ms    (simple queries, warm cache)                        │   │
│   │  P95: < 200ms   (complex queries with filters)                      │   │
│   │  P99: < 500ms   (faceted search with large result set)              │   │
│   │  Timeout: 5s    (return partial or error)                           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   AUTOCOMPLETE:                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  P50: < 10ms    (prefix trie lookup)                                │   │
│   │  P95: < 30ms                                                        │   │
│   │  P99: < 50ms                                                        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   INDEXING (time to searchable):                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  P50: < 2s      (NRT refresh interval)                              │   │
│   │  P95: < 5s                                                          │   │
│   │  P99: < 10s     (under heavy indexing load)                         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   WHY THESE TARGETS:                                                        │
│   - Search < 200ms: Users perceive as instant                               │
│   - Autocomplete < 30ms: Must keep up with typing speed                     │
│   - Indexing < 5s: "Near real-time" contract                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Availability Target

| Operation | Target | Justification |
|-----------|--------|---------------|
| Search API | 99.9% | Core user-facing feature |
| Indexing pipeline | 99.5% | Temporary staleness acceptable |
| Autocomplete | 99.9% | Part of search experience |

## Consistency Model

```
CONSISTENCY MODEL: Eventual consistency (NRT)

WHAT THIS MEANS:
    After indexing a document:
    → It becomes searchable within 1-5 seconds
    → Not immediately visible in search results
    → Refresh interval controls visibility lag

WHY EVENTUAL IS ACCEPTABLE:
    - Users don't expect instant searchability
    - Strong consistency would require synchronous index writes
    - Synchronous writes = 10× latency on indexing
    - NRT is the industry standard (Elasticsearch, Solr)

NOT ACCEPTABLE:
    - Deletes must take effect within same refresh cycle
    - A deleted product must not appear in results after refresh
    - Compliance: Deleted content must be unsearchable quickly
```

## Durability

```
DURABILITY:

INDEX DATA:
    - Index can be rebuilt from source of truth (primary database)
    - Index is a DERIVED data store, not the source
    - Loss = rebuild time (minutes to hours), not data loss
    
SOURCE DOCUMENTS:
    - Stored in primary database (not our responsibility)
    - Search system indexes from the database via change events

TRANSACTION LOG:
    - Index writes buffered in write-ahead log (translog)
    - Survives process crash
    - Replayed on restart
```

---

# Part 5: Scale & Capacity Planning

## Assumptions

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SCALE ASSUMPTIONS                                   │
│                                                                             │
│   CORPUS:                                                                   │
│   • Total documents: 50 million                                             │
│   • Average document size: 2 KB (searchable fields)                         │
│   • Total index size: ~100 GB (with inverted index overhead)                │
│   • Document updates: 100K/day (new + modified)                             │
│                                                                             │
│   QUERY VOLUME:                                                             │
│   • Average QPS: 2,000 search queries/sec                                   │
│   • Peak QPS: 10,000/sec (10× burst, e.g., sale event)                      │
│   • Autocomplete QPS: 5,000/sec (multiple per keystroke)                    │
│   • Read:Write ratio: 100:1 (read-heavy)                                    │
│                                                                             │
│   INDEX:                                                                    │
│   • Shards: Horizontal partitioning of index                                │
│   • Replicas: Copies of each shard for read throughput                      │
│   • Shard size target: 10-30 GB per shard                                   │
│   • Shards needed: 100 GB / 20 GB = 5 primary shards                        │
│   • Replicas: 2 per shard (for availability + read throughput)              │
│   • Total shard instances: 5 × 3 = 15                                       │
│                                                                             │
│   HARDWARE:                                                                 │
│   • Each shard hosted on node with 32 GB RAM, 8 cores                       │
│   • Index should fit in OS page cache for fast queries                      │
│   • Nodes needed: 5-8 (multiple shards per node)                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## What Breaks First at 10× Scale

```
CURRENT: 50M docs, 2K QPS
10× SCALE: 500M docs, 20K QPS

COMPONENT ANALYSIS:

1. INDEX SIZE (Primary concern)
   Current: 100 GB
   10×: 1 TB
   
   Problem: Single shard can't be 1 TB (query latency degrades)
   Breaking point: Shards > 50 GB become slow
   
   → AT 10×: 50 shards (1 TB / 20 GB)
   → More nodes, more cross-shard coordination

2. QUERY THROUGHPUT (Secondary concern)
   Current: 2K QPS across 15 shard instances
   10×: 20K QPS
   
   Problem: Each shard handles ~130 QPS → needs ~1,300 QPS
   Breaking point: Single shard saturates at ~500 QPS
   
   → AT 10×: More replicas (3-4 per shard)
   → 50 × 4 = 200 shard instances

3. SCATTER-GATHER OVERHEAD (Tertiary concern)
   Current: Query fans out to 5 shards
   10×: Query fans out to 50 shards
   
   Problem: More fan-out = higher tail latency
   Breaking point: P99 > 500ms when > 20 shards
   
   → AT 10×: Two-phase query (routing shard → data shards)
   → Limit fan-out by routing on partition key

4. INDEXING THROUGHPUT
   Current: 100K documents/day = ~1.2/sec
   10×: 1M documents/day = ~12/sec
   
   This is not a bottleneck. Even 1000/sec is manageable.

MOST FRAGILE ASSUMPTION:
    "Queries touch all shards"
    
    If every query fans out to all 50 shards at 10× scale:
    - Tail latency dominated by slowest shard
    - Network overhead of scatter-gather
    - Coordinator becomes bottleneck
    
    Mitigation: Route queries to subset of shards when possible
    (e.g., partition by category → "electronics" queries only hit electronics shards)
```

## Back-of-Envelope: Node Sizing

```
SIZING CALCULATION:

Step 1: Shard count
    Index size: 100 GB
    Target shard size: 20 GB
    Primary shards: 5
    Replicas: 2 per shard
    Total shard instances: 5 × 3 = 15

Step 2: Node capacity
    RAM per node: 32 GB
    OS page cache for index: ~20 GB (index should fit in memory)
    JVM heap (if JVM-based): ~8 GB
    Shards per node: 2-3
    Nodes needed: 15 / 3 = 5 nodes

Step 3: QPS per node
    Total QPS: 2,000 search + 5,000 autocomplete = 7,000
    Per node: 7,000 / 5 = 1,400 QPS
    
    Each search: ~10ms CPU time
    Per core: 100 QPS
    Cores per node: 8
    Capacity: 800 QPS per node
    
    Need: 7,000 / 800 = 9 nodes (QPS-limited, not storage-limited)
    
Step 4: Final sizing
    Nodes: 9 (round up to 10 for headroom)
    Each: 8 cores, 32 GB RAM, 500 GB SSD
    
COST ESTIMATE:
    10 nodes × $500/month = $5,000/month
    Total with networking/management: ~$7,000/month
```

---

# Part 6: High-Level Architecture

## Core Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SEARCH SYSTEM ARCHITECTURE                               │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        DATA SOURCES                                 │   │
│   │  ┌──────────┐  ┌──────────┐    ┌──────────┐                         │   │
│   │  │ Product  │  │  CMS     │    │  User    │                         │   │
│   │  │   DB     │  │  DB      │    │  DB      │                         │   │
│   │  └────┬─────┘  └────┬─────┘    └────┬─────┘                         │   │
│   └───────┼──────────────┼──────────────┼───────────────────────────────┘   │
│           │              │              │                                   │
│           └──────────────┼──────────────┘                                   │
│                          │ (CDC / Change Events)                            │
│                          ▼                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    INDEXING PIPELINE                                │   │
│   │  ┌──────────┐  ┌──────────┐  ┌──────────┐                           │   │
│   │  │  Event   │  │  Doc     │  │  Index   │                           │   │
│   │  │  Queue   │→ │Transform │→ │  Writer  │                           │   │
│   │  │ (Kafka)  │  │          │  │          │                           │   │
│   │  └──────────┘  └──────────┘  └──────────┘                           │   │
│   └────────────────────────────────┬────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    SEARCH CLUSTER                                   │   │
│   │                                                                     │   │
│   │  ┌──────────────────────────────────────────────────────────────┐   │   │
│   │  │              COORDINATOR NODE                                │   │   │
│   │  │  (Query parsing, scatter-gather, merge results)              │   │   │
│   │  └──────────────────────┬───────────────────────────────────────┘   │   │
│   │                         │                                           │   │
│   │         ┌───────────────┼───────────────┐                           │   │
│   │         ▼               ▼               ▼                           │   │
│   │  ┌────────────┐ ┌────────────┐ ┌────────────┐                       │   │
│   │  │  Shard 0   │ │  Shard 1   │ │  Shard 2   │  ...                  │   │
│   │  │ (Primary)  │ │ (Primary)  │ │ (Primary)  │                       │   │
│   │  │ + Replica  │ │ + Replica  │ │ + Replica  │                       │   │
│   │  │ + Replica  │ │ + Replica  │ │ + Replica  │                       │   │
│   │  └────────────┘ └────────────┘ └────────────┘                       │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    SEARCH API                                       │   │
│   │  (Rate limiting, authentication, query routing)                     │   │
│   │  ┌──────────┐  ┌──────────┐  ┌──────────┐                           │   │
│   │  │  API     │  │  API     │  │  API     │                           │   │
│   │  │  Node 1  │  │  Node 2  │  │  Node N  │                           │   │
│   │  └──────────┘  └──────────┘  └──────────┘                           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                          ▲                                                  │
│                          │                                                  │
│   ┌──────────────────────┴──────────────────────────────────────────────┐   │
│   │                    CLIENTS                                          │   │
│   │  ┌──────────┐  ┌──────────┐  ┌──────────┐                           │   │
│   │  │  Web     │  │ Mobile   │  │  API     │                           │   │
│   │  └──────────┘  └──────────┘  └──────────┘                           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | Stateful? |
|-----------|---------------|-----------|
| Search API | Request handling, rate limiting, query routing | No |
| Coordinator Node | Query parsing, scatter to shards, merge results | No |
| Shard (Primary) | Holds a partition of the index; handles indexing + search | Yes |
| Shard (Replica) | Read-only copy; serves search queries | Yes |
| Indexing Pipeline | Transform source data, write to index | No |
| Event Queue (Kafka) | Buffer change events between source and index | Yes |

## Data Flow: Search Query

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        SEARCH QUERY FLOW                                    │
│                                                                             │
│  Client        API         Coordinator      Shard 0      Shard 1    Shard 2 │
│    │            │              │               │            │           │   │
│    │ GET /search│              │               │            │           │   │
│    │───────────▶│              │               │            │           │   │
│    │            │ 1. Parse     │               │            │           │   │
│    │            │ 2. Route     │               │            │           │   │
│    │            │─────────────▶│               │            │           │   │
│    │            │              │               │            │           │   │
│    │            │              │ 3. Scatter    │            │           │   │
│    │            │              │──────────────▶│            │           │   │
│    │            │              │────────────────────-──────▶│           │   │
│    │            │              │─────────────────────────────-─────────▶│   │
│    │            │              │               │            │           │   │
│    │            │              │  4. Each shard: search local index     │   │
│    │            │              │     - Lookup inverted index            │   │
│    │            │              │     - Score with BM25                  │   │
│    │            │              │     - Return top K results             │   │
│    │            │              │               │            │           │   │
│    │            │              │ 5. Gather     │            │           │   │
│    │            │              │◀──────────────│            │           │   │
│    │            │              │◀──────────────────────────│            │   │
│    │            │              │◀────────────────────────────────────-──│   │
│    │            │              │               │            │           │   │
│    │            │              │ 6. Merge + re-rank                     │   │
│    │            │              │ 7. Top N global                        │   │
│    │            │◀─────────────│               │            │           │   │
│    │◀───────────│              │               │            │           │   │
│    │ results    │              │               │            │           │   │
│                                                                             │
│   TIMING:                                                                   │
│     Steps 1-2: ~1ms (parse + route)                                         │
│     Step 3: ~1ms (fan-out)                                                  │
│     Step 4: ~30-100ms (per-shard search, parallel)                          │
│     Steps 5-7: ~5ms (merge)                                                 │
│     TOTAL: ~40-110ms                                                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 7: Component-Level Design

## Inverted Index

The core data structure of search.

```
INVERTED INDEX:

What it is:
    Mapping from TERM → list of DOCUMENT IDs (posting list)

Example:
    "running"   → [doc_3, doc_42, doc_87, doc_193]
    "shoes"     → [doc_3, doc_42, doc_150, doc_193]
    "red"       → [doc_3, doc_55, doc_193]

Query "red running shoes":
    Posting lists:
        "red"     → [3, 55, 193]
        "running" → [3, 42, 87, 193]
        "shoes"   → [3, 42, 150, 193]
    
    Intersection: [3, 193] (appear in ALL lists)

POSTING LIST FORMAT:
    Each entry stores:
    - document_id
    - term_frequency (how many times in this doc)
    - field (title vs description)
    - positions (for phrase matching)

    Compressed with variable-byte encoding or PForDelta
    Sorted by doc_id for efficient intersection (merge join)

// Pseudocode: Posting list intersection
FUNCTION intersect(list_a, list_b):
    result = []
    i = 0
    j = 0
    WHILE i < len(list_a) AND j < len(list_b):
        IF list_a[i].doc_id == list_b[j].doc_id:
            result.append(list_a[i])
            i += 1
            j += 1
        ELSE IF list_a[i].doc_id < list_b[j].doc_id:
            i += 1
        ELSE:
            j += 1
    RETURN result

COMPLEXITY: O(min(|A|, |B|)) for sorted lists — fast!
```

## Text Analysis Pipeline

```
TEXT ANALYSIS: Converting raw text to searchable tokens

PIPELINE:
    "Running in Red Shoes!! (Size 10)"
    
    Step 1: CHARACTER FILTER
        Remove HTML, special chars
        → "Running in Red Shoes Size 10"
    
    Step 2: TOKENIZER
        Split on whitespace/punctuation
        → ["Running", "in", "Red", "Shoes", "Size", "10"]
    
    Step 3: TOKEN FILTERS
        a) Lowercase: ["running", "in", "red", "shoes", "size", "10"]
        b) Stop words (remove common words): ["running", "red", "shoes", "size", "10"]
        c) Stemming ("running" → "run"): ["run", "red", "shoe", "size", "10"]
    
    Final tokens: ["run", "red", "shoe", "size", "10"]

// Pseudocode: Text analysis
FUNCTION analyze(text, analyzer_config):
    // Character filters
    FOR filter IN analyzer_config.char_filters:
        text = filter.apply(text)
    
    // Tokenize
    tokens = analyzer_config.tokenizer.tokenize(text)
    
    // Token filters
    FOR filter IN analyzer_config.token_filters:
        tokens = filter.apply(tokens)
    
    RETURN tokens

ANALYZER CONFIGURATION:
    "product_analyzer": {
        char_filters: [html_strip],
        tokenizer: standard_tokenizer,
        token_filters: [lowercase, stop_words, stemmer]
    }
```

## BM25 Scoring

```
BM25: Best Match 25 — Standard relevance scoring algorithm

FORMULA:
    score(q, d) = Σ IDF(t) × (tf(t,d) × (k1 + 1)) / (tf(t,d) + k1 × (1 - b + b × |d| / avgdl))

WHERE:
    q = query terms
    d = document
    t = individual term
    tf(t,d) = frequency of term t in document d
    IDF(t) = inverse document frequency (rare words score higher)
    |d| = document length (in words)
    avgdl = average document length in corpus
    k1 = term frequency saturation (default 1.2)
    b = length normalization (default 0.75)

INTUITION:
    - IDF: "bluetooth" is more informative than "the" → higher score
    - TF: A document mentioning "bluetooth" 5 times is more relevant than 1 time
    - TF saturation: But 50 times isn't 50× better than 1 time (diminishing returns)
    - Length norm: Short document with match is more relevant than long document with match

// Pseudocode: BM25 scoring
FUNCTION bm25_score(query_tokens, doc_id):
    score = 0.0
    doc_length = get_doc_length(doc_id)
    
    FOR token IN query_tokens:
        tf = get_term_frequency(token, doc_id)
        df = get_document_frequency(token)
        idf = log((N - df + 0.5) / (df + 0.5) + 1)
        
        tf_component = (tf * (K1 + 1)) / (tf + K1 * (1 - B + B * doc_length / AVG_DOC_LENGTH))
        
        score += idf * tf_component
    
    RETURN score

BOOST FACTORS (applied on top of BM25):
    final_score = bm25_score
                + popularity_boost      // Click-through rate, sales
                + freshness_boost       // Recently updated
                + field_weight_boost    // Title match > description match
                - penalty(out_of_stock) // Demote unavailable items
```

## Coordinator (Scatter-Gather)

```
// Pseudocode: Coordinator query handling
CLASS Coordinator:
    
    FUNCTION execute_search(query):
        // Parse query
        parsed = parse_query(query.query_string)
        
        // Determine target shards
        target_shards = get_shards_for_query(parsed)  // Usually all shards
        
        // Scatter: Send query to each shard in parallel
        shard_futures = []
        FOR shard IN target_shards:
            future = async_send(shard, parsed, query.filters, query.size)
            shard_futures.append(future)
        
        // Gather: Wait for results (with timeout)
        shard_results = wait_all(shard_futures, timeout=500ms)
        
        // Handle partial failures
        failed_shards = [r FOR r IN shard_results IF r.is_error]
        IF len(failed_shards) > 0:
            log.warn("Query degraded: " + len(failed_shards) + " shards failed")
            metrics.increment("search.partial_failure")
        
        successful_results = [r FOR r IN shard_results IF r.is_success]
        
        // Merge: Combine results from all shards
        merged = merge_results(successful_results)
        
        // Re-rank top N globally
        top_n = merged[:query.size]
        
        // Fetch full documents (if not embedded in shard response)
        IF NOT embedded_docs:
            documents = document_store.get_batch([r.doc_id FOR r IN top_n])
            enrich(top_n, documents)
        
        RETURN SearchResponse(
            hits=top_n,
            total=sum(r.total FOR r IN successful_results),
            took_ms=elapsed(),
            shards_successful=len(successful_results),
            shards_failed=len(failed_shards)
        )
```

---

# Part 8: Data Model & Storage

## Index Schema

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SEARCH INDEX SCHEMA                                 │
│                                                                             │
│   DOCUMENT SCHEMA (product index):                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  id              STRING         (primary identifier)                │   │
│   │  title           TEXT           (analyzed, searchable, boosted 2×)  │   │
│   │  description     TEXT           (analyzed, searchable)              │   │
│   │  brand           KEYWORD        (exact match, facetable)            │   │
│   │  category        KEYWORD        (exact match, facetable, filterable)│   │
│   │  price           FLOAT          (filterable, sortable)              │   │
│   │  in_stock        BOOLEAN        (filterable)                        │   │
│   │  rating          FLOAT          (sortable, boost factor)            │   │
│   │  popularity      INTEGER        (boost factor)                      │   │
│   │  created_at      TIMESTAMP      (sortable, freshness boost)         │   │
│   │  updated_at      TIMESTAMP      (sortable)                          │   │
│   │  image_url       KEYWORD        (stored, not indexed)               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   FIELD TYPES:                                                              │
│   TEXT:    Analyzed (tokenized, stemmed) → inverted index                   │
│   KEYWORD: Not analyzed → exact match, aggregation, filtering               │
│   FLOAT/INT: Numeric → range queries, sorting                               │
│   BOOLEAN: Binary filter                                                    │
│   TIMESTAMP: Date → range queries, sorting                                  │
│                                                                             │
│   INVERTED INDEX STRUCTURE (per shard):                                     │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Term Dictionary:  "run" → segment_offset                           │   │
│   │  Posting List:     [doc_3(tf=2,pos=[1,5]), doc_42(tf=1,pos=[3])]    │   │
│   │  Doc Values:       doc_3 → {price: 99.99, brand: "Nike"}            │   │
│   │  Stored Fields:    doc_3 → {title: "Running Shoes", image: "..."}   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   SEGMENTS:                                                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Index is composed of immutable SEGMENTS                            │   │
│   │  New documents → new segment                                        │   │
│   │  Deletes → mark in deletion bitmap                                  │   │
│   │  Segment merge: Background process compacts segments                │   │
│   │  Benefit: No locking during reads (segments are immutable)          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Storage Calculations

```
STORAGE ESTIMATES:

INVERTED INDEX:
    50M documents × 500 tokens avg = 25 billion term-doc pairs
    Compressed posting lists: ~60 GB
    Term dictionary: ~5 GB
    Total inverted index: ~65 GB

DOC VALUES (for filtering/sorting):
    50M × 100 bytes (numeric fields) = 5 GB

STORED FIELDS (for result display):
    50M × 500 bytes (title, image, price) = 25 GB

TOTAL INDEX SIZE: ~95 GB (~100 GB with overhead)

WITH REPLICAS:
    100 GB × 3 (1 primary + 2 replicas) = 300 GB total disk
```

## Sharding Strategy

```
SHARDING APPROACH: Hash-based (document ID)

HOW:
    shard_id = hash(document_id) % num_shards
    
    Document goes to deterministic shard.
    Queries fan out to ALL shards (since any shard may have relevant docs).

WHY HASH-BASED (not category-based):
    + Even distribution (no hot shards)
    + Simple document routing
    - Every query hits every shard (full scatter)
    
    Category-based alternative:
    + Query "electronics" hits only electronics shard
    - Uneven distribution (electronics >> pet supplies)
    - Cross-category queries need all shards anyway
    
DECISION: Hash-based for V1.
    Uniform shard sizes; simpler ops.
    Optimize scatter with caching if needed.
```

---

# Part 9: Consistency, Concurrency & Idempotency

## Consistency Model

```
CONSISTENCY GUARANTEES:

1. INDEXING (eventual consistency)
   Document indexed → searchable within 1-5 seconds
   Refresh interval controls visibility
   
2. DELETE (eventual consistency)
   Document deleted → removed from results within 1-5 seconds
   Physical removal during next segment merge

3. UPDATE (eventual consistency)
   Document updated → old version immediately invisible (after refresh)
   New version indexed and visible after refresh
   
   Implementation: Delete old + index new (same doc_id)

4. REPLICA SYNC (eventual consistency)
   Primary shard indexes document
   Replica syncs via replication log
   Small window where primary and replica return different results
   Acceptable: User refreshing page may see slightly different results
```

## Concurrency

```
CONCURRENCY: Readers never block writers

WHY: Segments are immutable
    - Search reads from existing segments (no locks)
    - Indexing writes to new segments (no conflict)
    - Segment merge is background (doesn't block search)
    
CONCURRENT INDEXING:
    Multiple documents can be indexed simultaneously.
    Each goes to its segment buffer.
    No cross-document locking.

CONCURRENT SEARCH:
    Multiple queries served simultaneously.
    Each reads from the current snapshot of segments.
    No locking on read path.
    
    This is the key architectural advantage of segment-based indices.
```

## Idempotency

```
INDEXING IDEMPOTENCY:

Same document_id indexed twice → replaces previous version
    No duplicate documents.
    
    Implementation:
    - New version indexed with same doc_id
    - Old version marked as deleted
    - Only latest version returned in search
    
    Safe for retries: If indexing event is replayed, same result.

SEARCH IDEMPOTENCY:
    Search queries are naturally idempotent (read-only).
    Same query returns same results (given same index state).
```

---

# Part 10: Failure Handling & Reliability

## Partial Failure Behavior

```
PARTIAL FAILURE: One shard slow or unavailable

SITUATION: Shard 2 responding at 500ms instead of 50ms, or timing out

BEHAVIOR:
- Coordinator waits up to 500ms timeout per shard
- Returns results from healthy shards
- Response includes: shards_successful: 4, shards_failed: 1
- Results are partial (missing ~20% of matches from shard 2)

USER IMPACT:
- Results may be incomplete
- Top results likely unaffected (distributed across shards)
- User unlikely to notice unless looking for specific document on shard 2

DETECTION:
- Per-shard latency metrics
- search.partial_failure counter increasing
- Alert: "Shard 2 P99 > 300ms"

MITIGATION:
- Route queries to shard 2's replicas instead of primary
- Investigate primary (GC? disk? segment merge?)

---

PARTIAL FAILURE: One dependency slow (document store)

SITUATION: Document store returns 200ms instead of 20ms

BEHAVIOR:
- Search still works (inverted index is local to shard)
- Document enrichment (fetching full body) is slower
- Option: Return results without full body (IDs + title + score)

USER IMPACT:
- Results appear but some fields may be missing
- Or overall latency increases by 200ms

MITIGATION:
- Embed commonly displayed fields in shard (stored fields)
- Only call document store for full-body display
- This way, doc store is not on hot search path
```

## Dependency Failures

### Index Corruption

```
SCENARIO: Bad indexing job writes malformed documents

DETECTION:
- Search errors on affected shard
- "IndexCorruptionException" in logs
- Query results suddenly empty for some queries

IMPACT:
- Queries to affected shard fail or return wrong results
- Other shards unaffected

RECOVERY:
1. Identify corrupted shard
2. Promote replica to primary (replica may be clean)
3. If replica also corrupted: rebuild shard from source
4. Rebuild time: ~30 minutes for 20 GB shard

// Pseudocode: Corruption detection
FUNCTION health_check_shard(shard_id):
    TRY:
        // Run a known query that should return results
        result = shard.search("*", size=1)
        IF result.total == 0 AND expected_docs > 0:
            alert("Shard " + shard_id + " may be corrupted: 0 results for match-all")
        RETURN healthy
    CATCH IndexError:
        alert("Shard " + shard_id + " corruption detected")
        RETURN corrupted
```

### Indexing Pipeline Failure

```
SCENARIO: Kafka consumer or indexing worker crashes

DETECTION:
- Consumer lag increasing on Kafka topic
- No new documents indexed (index freshness stale)
- Alert: "Indexing lag > 10 minutes"

IMPACT:
- Search still works (serves existing index)
- New or updated documents not searchable
- Results become stale

RECOVERY:
1. Restart consumer/worker
2. Consumer resumes from last committed offset
3. Backlog of events processed (catch-up)
4. No data loss (Kafka retains events)

MITIGATION:
    Kafka retention: 7 days (enough to survive extended outage)
    Consumer offset committed after successful index write
    Idempotent indexing: replay is safe
```

## Realistic Production Failure Scenario

```
┌─────────────────────────────────────────────────────────────────────────────┐
│   FAILURE SCENARIO: BAD SYNONYM CONFIG TANKS SEARCH RELEVANCE               │
│                                                                             │
│   TRIGGER:                                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Engineer deploys updated synonym file for product search.          │   │
│   │  Synonym: "phone" → "case" (intended: "phone" → "mobile")           │   │
│   │  Typo in synonym mapping.                                           │   │
│   │  All queries containing "phone" now match "case" documents.         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   WHAT BREAKS:                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  T+0:    Synonym config deployed                                    │   │
│   │  T+1min: New index segments use bad synonyms                        │   │
│   │  T+5min: Users searching "iPhone" see phone cases ranked first      │   │
│   │  T+10min: Product team notices: "Why are phone search results bad?" │   │
│   │  T+15min: Alert fires: Click-through rate on "phone" queries -40%   │   │
│   │                                                                     │   │
│   │  SECONDARY EFFECTS:                                                 │   │
│   │  - Conversion rate drops                                            │   │
│   │  - "phone" is one of top 10 queries by volume                       │   │
│   │  - Customer complaints: "search is broken"                          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   DETECTION:                                                                │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  - Alert: CTR drop > 20% on high-volume queries                     │   │
│   │  - Dashboard: Top query "phone" relevance score degraded            │   │
│   │  - Qualitative: Manual spot check of top 10 queries                 │   │
│   │  - Correlation: Recent config deployment                            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   SENIOR ENGINEER RESPONSE:                                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  IMMEDIATE (0-5 min):                                               │   │
│   │  1. Identify recent config changes (synonym file updated)           │   │
│   │  2. Revert synonym config to previous version                       │   │
│   │  3. Trigger index refresh to pick up reverted config                │   │
│   │                                                                     │   │
│   │  MITIGATION (5-15 min):                                             │   │
│   │  4. Verify: "phone" queries returning relevant results              │   │
│   │  5. Monitor CTR recovering                                          │   │
│   │                                                                     │   │
│   │  POST-INCIDENT:                                                     │   │
│   │  1. Add synonym validation (integration test with known queries)    │   │
│   │  2. Deploy synonyms via canary (test on 1% traffic first)           │   │
│   │  3. Automated relevance regression test before deploy               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Timeout and Retry Configuration

```
TIMEOUT CONFIGURATION:

Search API:
    Overall request timeout: 5 seconds
    Per-shard timeout: 500ms (don't wait for slow shards)
    Document fetch timeout: 200ms

Indexing Pipeline:
    Kafka consume timeout: 30 seconds (long poll)
    Index write timeout: 5 seconds
    Retry on failure: 3 attempts, exponential backoff (1s, 5s, 30s)

RETRY CONFIGURATION:

Search (client-side):
    Retries: 1 (idempotent, safe to retry)
    On partial result: Return what we have (don't retry)
    On full failure: Retry once after 100ms

Indexing (server-side):
    Retries: 3
    Backoff: 1s, 5s, 30s
    After max retries: Send to dead-letter queue
    DLQ: Processed manually or after fix deployed
```

---

# Part 11: Performance & Optimization

## Hot Path Analysis

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SEARCH QUERY HOT PATH                               │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. Parse query + analyze tokens       ~1ms                         │   │
│   │  2. Fan out to shards (network)        ~1ms                         │   │
│   │  3. Per-shard: inverted index lookup   ~5ms                         │   │
│   │  4. Per-shard: posting list intersect  ~10-30ms                     │   │
│   │  5. Per-shard: BM25 scoring            ~5-20ms                      │   │
│   │  6. Per-shard: filter application      ~2-5ms                       │   │
│   │  7. Gather + merge results             ~3ms                         │   │
│   │  8. Fetch stored fields                ~2ms (from shard)            │   │
│   │  ─────────────────────────────────────────────                      │   │
│   │  TOTAL: ~30-60ms (warm cache), ~100-200ms (cold)                    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   BIGGEST FACTORS:                                                          │
│   - Posting list intersection (depends on query cardinality)                │
│   - BM25 scoring (proportional to candidate set size)                       │
│   - OS page cache: Index in memory = 30ms; on disk = 200ms                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Optimizations Applied

### 1. OS Page Cache (Most Critical)

```
PROBLEM: Reading index from disk = 200ms+ per query

SOLUTION: Keep index in OS page cache (RAM)

HOW:
    Index size: 100 GB
    Node RAM: 32 GB
    Hot portion of index: ~20 GB (frequently accessed posting lists)
    
    OS automatically caches frequently accessed file regions.
    After warm-up: 90%+ of reads from memory.

BENEFIT: 5-10× query speedup

RISK: New node restarts = cold cache = slow queries for minutes
MITIGATION: Warm cache before routing traffic to new node
```

### 2. Query Result Cache

```
PROBLEM: Popular queries recomputed on every request

SOLUTION: Cache results for identical queries (short TTL)

// Pseudocode: Query result cache
FUNCTION search_with_cache(query):
    cache_key = hash(query.query_string + query.filters + query.sort)
    
    cached = result_cache.get(cache_key)
    IF cached AND cached.age < 60 seconds:
        metrics.increment("search.cache.hit")
        RETURN cached.result
    
    result = execute_search(query)
    result_cache.set(cache_key, result, ttl=60s)
    
    RETURN result

BENEFIT:
    - Top 100 queries cover 30% of traffic
    - 30% of queries served from cache (< 1ms)
    - Reduce shard load by 30%

TRADE-OFF:
    - 60-second staleness for cached queries
    - Acceptable: Search results change slowly
```

### 3. Early Termination

```
PROBLEM: Scoring all 50,000 candidates when user only sees top 10

SOLUTION: Score top K per shard, not all candidates

// Pseudocode: Early termination
FUNCTION search_shard(query, size):
    candidates = get_matching_docs(query)
    
    // Don't score all candidates
    // Use index-order (roughly BM25-ordered) and score top N
    top_candidates = candidates[:size * 10]  // Over-fetch for accuracy
    
    scored = []
    FOR doc IN top_candidates:
        score = bm25_score(query, doc)
        scored.append((doc, score))
    
    scored.sort(by=score, descending=true)
    RETURN scored[:size]

BENEFIT:
    - 10× fewer BM25 computations
    - Minimal impact on result quality (top results are usually in first 10× candidates)

TRADE-OFF:
    - May miss a high-scoring document ranked > 10×size in posting list
    - Acceptable for 99% of queries
```

## Optimizations NOT Done

```
DEFERRED OPTIMIZATIONS:

1. QUERY REWRITING (ML)
   Could expand/rewrite queries for better recall
   NOT DONE: BM25 + synonyms sufficient for V1
   DEFER UNTIL: Relevance metrics show missed results

2. LEARNING-TO-RANK
   Could use ML model instead of BM25 for scoring
   NOT DONE: Requires click data, training pipeline, model serving
   DEFER UNTIL: Product matures and click data is available

3. DOCUMENT-LEVEL CACHING
   Could cache individual document scores
   NOT DONE: Query-level cache is sufficient; doc-level adds complexity
   DEFER UNTIL: Cache hit rate drops below 20%

4. INDEX TIERING (hot/warm/cold)
   Could move old documents to slower storage
   NOT DONE: All 100 GB fits on fast storage
   DEFER UNTIL: Index exceeds available memory
```

---

# Part 12: Cost & Operational Considerations

## Major Cost Drivers

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     SEARCH SYSTEM COST BREAKDOWN                            │
│                                                                             │
│   For 50M docs, 2K QPS:                                                     │
│                                                                             │
│   1. COMPUTE (55% of cost)                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Search nodes (10): $500/month each = $5,000/month                  │   │
│   │  Indexing workers (2): $200/month each = $400/month                 │   │
│   │  API servers (3): $200/month each = $600/month                      │   │
│   │  Total compute: ~$6,000/month                                       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   2. STORAGE (20% of cost)                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  SSD: 300 GB (index + replicas) × $0.10/GB = $30/month              │   │
│   │  Kafka: 100 GB × $0.10/GB = $10/month                               │   │
│   │  Total storage: ~$40/month                                          │   │
│   │  (Storage is cheap; compute dominates)                              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   3. INFRASTRUCTURE (25% of cost)                                           │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Kafka cluster: $500/month                                          │   │
│   │  Monitoring/Logging: $200/month                                     │   │
│   │  Total infra: ~$700/month                                           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   TOTAL MONTHLY COST: ~$7,000                                               │
│   COST PER 1M QUERIES: ~$1.30                                               │
│                                                                             │
│   KEY INSIGHT: Search is compute-bound (CPU + RAM for index).               │
│   The most expensive resource is RAM for keeping index in cache.            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Cost Analysis Table (L5 Checklist)

| Cost Driver | Current | At Scale (10×) | Optimization |
|-------------|---------|----------------|--------------|
| Compute (search nodes + API + indexers) | ~$6,000/mo | ~$60,000/mo | Right-size instances; spot for replicas; query result cache to reduce QPS per node |
| Storage (SSD + Kafka) | ~$40/mo | ~$400/mo | Tiered storage for old segments; Kafka retention tuned to recovery needs |
| Infrastructure (Kafka cluster, monitoring) | ~$700/mo | ~$4,000/mo | Shared Kafka cluster; sampling for logs |

**Senior cost discipline:** Intentionally not building ML ranking, personalization, or cross-datacenter search in V1. Premature optimization (e.g. custom compression) wastes time; cost-cutting is safe on replicas (spot) and indexing pipeline (smaller instances), dangerous on primaries or cache size.

**Staff consideration (L6):** At platform scale, cost allocation matters. Charge back by index size and QPS so consuming teams see their search cost. Trade-off: granular allocation adds instrumentation overhead; coarse allocation leads to "free rider" behavior. Document blast radius of cost cuts (e.g., "removing one replica = 33% less headroom during failover") so finance understands risk.

| Decision | Cost Impact | Operability Impact | On-Call Impact |
|----------|-------------|---------------------|----------------|
| More replicas | +$X | Better availability | Fewer partial-failure pages |
| Query result cache | -$Y | Fewer nodes for same QPS | Fewer latency spikes |
| Spot instances for replicas only | -$1.5K/mo | Replica can be preempted | Acceptable; promote another replica |

## On-Call Burden Analysis

```
ON-CALL REALITY:

EXPECTED PAGES (monthly):
    - Search latency spike: 1-2 (query pattern change, cold cache)
    - Indexing lag: 1-2 (consumer crash, schema issue)
    - Shard failure: 0-1 (disk, node crash)
    - Relevance complaint: 1-2 (manual investigation)
    
    Total: 3-7 pages/month

HIGH-BURDEN:
    1. Full index corruption
       - Requires rebuild from source (30+ minutes)
       - Serve from replicas during rebuild
    
    2. Relevance regression
       - Hard to detect (no automated metric)
       - Requires manual investigation
       - Duration: Hours to find root cause

LOW-BURDEN (AUTOMATED):
    - Single node crash → Shard replicas serve traffic
    - Minor indexing lag → Self-resolving after restart
```

## Misleading Signals & Debugging Reality

```
MISLEADING SIGNALS:

| Metric | Looks Healthy | Actually Broken |
|--------|---------------|-----------------|
| QPS normal | Queries flowing | Results are irrelevant |
| Latency P50 good | Fast median | P99 = 2 seconds (slow shard) |
| Index size growing | Docs being indexed | Duplicates in index |
| 0 errors | No exceptions | Missing results (not an error) |

REAL SIGNALS:
    - Click-through rate (CTR) on first page results
    - Zero-result rate (queries with 0 hits)
    - Latency by percentile (P50, P95, P99)
    - Indexing lag (seconds behind real-time)
    - Shard-level metrics (per-shard latency, size)

DEBUGGING: "Search results are bad"

1. Is it a ranking issue? (Results exist but wrong order)
   → Check boost config, synonym config, recent changes
2. Is it a recall issue? (Results missing entirely)
   → Check if document is indexed (GET /index/{doc_id})
   → Check analyzer: what tokens were generated?
3. Is it a freshness issue? (Old version of document)
   → Check indexing lag, consumer health
4. Is it a shard issue? (One shard returning wrong results)
   → Query each shard individually, compare results

Common causes:
    - Bad synonym/analyzer config (40%)
    - Indexing lag / stale index (25%)
    - Boost factor misconfigured (20%)
    - Actual bug in scoring (10%)
    - Infrastructure issue (5%)
```

---

# Part 12b: Rollout, Rollback & Operational Safety

## Deployment Strategy

```
SEARCH SYSTEM DEPLOYMENT:

COMPONENT TYPES AND STRATEGY:

1. Search API (stateless)
   Strategy: Rolling deployment
   Bake time: 15 minutes per stage
   
2. Search cluster nodes
   Strategy: Rolling restart (one node at a time)
   - Drain queries from node
   - Restart with new version
   - Wait for shard recovery (replica sync)
   - Verify healthy before proceeding
   Bake time: 30 minutes per node

3. Indexing pipeline
   Strategy: Rolling deployment
   - Stop consumers gracefully
   - Deploy new version
   - Resume consuming from last offset
   
4. Config changes (synonyms, boosts, analyzers)
   Strategy: Canary with relevance testing
   - Deploy to 1 shard only
   - Run relevance test queries
   - Verify CTR / quality metrics
   - Roll out to remaining shards

CANARY CRITERIA:
    - Search latency P99 delta < 20%
    - Zero-result rate delta < 1%
    - Error rate unchanged
    - CTR on top queries stable

ROLLOUT STAGES (config changes):
    1 shard → all shards (after validation)
```

## Rollback Safety

```
ROLLBACK TRIGGERS:
    - Latency P99 > 2× baseline
    - Zero-result rate > 5% increase
    - Error rate > 1%
    - CTR drop > 10% on top queries
    - On-call judgment

ROLLBACK MECHANISM:
    - API/Pipeline: Redeploy previous version
    - Config: Revert synonym/boost/analyzer config
    - Index: If corrupted, promote replica or rebuild from source

ROLLBACK TIME:
    - API: 5 minutes
    - Config: 2 minutes (apply + refresh)
    - Full index rebuild: 30-60 minutes (last resort)
```

## Concrete Scenario: Bad Analyzer Deployment

```
SCENARIO: New analyzer strips numeric tokens (breaking model number search)

1. CHANGE DEPLOYED
   - New text analyzer added to remove "noise" tokens
   - Analyzer incorrectly treats model numbers as noise
   - "iPhone 15" tokenized as ["iphone"] (missing "15")

2. BREAKAGE TYPE
   - Subtle: Search still works, but model-specific queries degrade
   - "iPhone 15 Pro" returns all iPhones (no model distinction)

3. DETECTION SIGNALS
   - Zero-result rate unchanged (results still returned)
   - CTR drops on model-specific queries
   - Customer report: "Can't find exact product model"

4. ROLLBACK STEPS
   a. Revert analyzer config to previous version
   b. Re-index affected documents (analyzer is applied at index time)
   c. Full re-index may be needed if analyzer change is at index level
   d. Verify: "iPhone 15" returns only iPhone 15 models

5. GUARDRAILS ADDED
   - Relevance test suite: Known query → expected results
   - Run before every analyzer/synonym change
   - Automated: If test fails, block deployment
```

## Rushed Decision Scenario

```
RUSHED DECISION SCENARIO

CONTEXT:
- Peak launch: New product line goes live in 6 hours. Search must support new
  "model number" field for filtering. Ideal: New analyzer, synonym list for
  model aliases, regression tests, canary rollout.

DECISION MADE:
- Ship with stored field + filter only: no new analyzer, no tokenization of
  model numbers. Exact match filter (e.g. model: "iPhone 15 Pro") works;
  free-text search "iPhone 15" still uses existing title/description only.
- Why acceptable: Unblocks launch; filter covers primary use case; no index
  schema change = no full reindex, no rollout risk.

TECHNICAL DEBT INTRODUCED:
- Queries like "15 Pro" don't match model field; users must use filter.
- When we add proper model tokenization later: reindex required, analyzer
  change, relevance tests. Cost: ~1 sprint to do right + 83 min full reindex.
- Carrying debt: Support tickets ("search doesn't find by model"); documented
  as known limitation; fix scheduled for next quarter.
```

---

# Part 13: Security Basics & Abuse Prevention

## Authentication & Authorization

```
AUTHENTICATION:
    - Search API behind API gateway with auth
    - Public search: Rate-limited by IP
    - Authenticated search: Rate-limited by user/API key

AUTHORIZATION:
    - Some documents may have access restrictions
    - Implementation: Filter at query time
    
    // Pseudocode: Access-controlled search
    FUNCTION search_with_access_control(query, user):
        // Add access filter
        query.filters.add("visibility IN user.accessible_visibilities")
        RETURN execute_search(query)
    
    V1: All documents are public. Access control is V2.
```

## Abuse Prevention

```
ABUSE VECTORS:

1. QUERY FLOODING (DoS)
   Attack: Millions of complex queries to saturate search cluster
   Defense: Rate limiting (100 queries/min per IP, 1000/min per API key)
   
2. EXPENSIVE QUERIES
   Attack: Wildcard queries ("*"), very broad queries
   Defense: Query complexity limits (max terms, max wildcard expansion)
   
   // Pseudocode: Query validation
   FUNCTION validate_query(query):
       IF len(query.tokens) > 20:
           RETURN Error("Too many terms")
       IF query.contains_leading_wildcard:
           RETURN Error("Leading wildcards not allowed")
       IF query.estimated_cost > MAX_QUERY_COST:
           RETURN Error("Query too expensive")

3. INDEX POISONING
   Attack: Inject spam documents with popular keywords
   Defense: Document quality scoring, abuse detection on indexing pipeline
   
4. SCRAPING
   Attack: Systematic querying to extract entire catalog
   Defense: Rate limiting, pagination limits, fingerprinting
```

---

# Part 14: System Evolution

## V1: Minimal Search System

```
V1 DESIGN (Launch):

Features:
- Full-text search with BM25
- Basic filters (category, price)
- Single index, 3 shards, 1 replica
- Kafka-based indexing pipeline

Scale:
- 1M documents
- 100 QPS
- < 200ms P95

Limitations:
- No autocomplete
- No synonyms
- No faceted counts
- Manual relevance tuning only
```

## First Issues and Fixes

```
ISSUE 1: "No results" for common queries (Week 2)

Problem: Users typing "sneakers" get 0 results (only "shoes" indexed)
Detection: Zero-result rate monitoring
Root cause: No synonym handling

Solution: Add synonym file ("sneakers" → "shoes", "laptop" → "notebook")
Effort: 2 days

ISSUE 2: Stale results (Month 1)

Problem: Products updated but search shows old prices
Detection: Customer complaints
Root cause: Indexing pipeline lag; consumer crash went unnoticed

Solution:
- Add indexing lag alert (> 5 min)
- Add consumer health monitoring
- Auto-restart on crash
Effort: 1 week

ISSUE 3: Slow queries during peak (Month 2)

Problem: Sale event causes 10× QPS; P99 > 2 seconds
Detection: Latency alert
Root cause: Not enough replicas; OS page cache thrashing

Solution:
- Add 1 more replica per shard
- Increase node RAM (more page cache)
- Add query result cache
Effort: 1 week
```

## V2 Improvements

```
V2: PRODUCTION-HARDENED SEARCH

Added:
- Autocomplete with popularity ranking
- Synonym and stemming support
- Faceted search with counts
- Query result cache
- Configurable boost factors
- Relevance monitoring (CTR tracking)

Improved:
- 50M documents, 2K QPS
- P95 < 200ms
- 2 replicas per shard
- Automated relevance regression testing
```

---

# Part 15: Alternatives & Trade-offs

## Alternative 1: Database Full-Text Search (PostgreSQL tsvector)

```
CONSIDERED: Use PostgreSQL's built-in full-text search

WHAT IT IS:
    PostgreSQL tsvector/tsquery with GIN index.
    No separate search service needed.

PROS:
- No additional infrastructure
- ACID consistency (instant visibility)
- Simpler architecture (one fewer service)

CONS:
- Limited ranking capabilities (no BM25 tuning)
- No faceted search
- Scaling: Tied to database scaling
- Performance: Degrades at 10M+ documents
- No autocomplete, synonyms, or fuzzy matching

DECISION: Dedicated search system

REASONING:
- Need BM25 ranking, facets, synonyms, autocomplete
- Need 10M+ documents with < 200ms latency
- Database search works for < 1M docs; we're past that
- Separate search = independent scaling
```

## Alternative 2: Exact-Match Only (No Full-Text)

```
CONSIDERED: Only support exact matches (category + keyword filters)

WHAT IT IS:
    Database queries with indexed columns.
    No text analysis, no relevance scoring.

PROS:
- Very simple
- Strong consistency
- No search infrastructure

CONS:
- "Running shoes" doesn't match "shoe for running"
- No typo tolerance
- No relevance ranking
- Users must know exact terms

DECISION: Full-text search with inverted index

REASONING:
- Users don't know exact terms
- Typo tolerance is essential for conversion
- Relevance ranking is the core value of search
```

## Alternative 3: Pre-Computed Search (Materialized Views)

```
CONSIDERED: Pre-compute results for common queries

WHAT IT IS:
    For top 1000 queries, pre-compute and cache results.
    Fall back to real-time search for long-tail queries.

PROS:
- Ultra-fast for popular queries (< 5ms)
- Reduces search cluster load by 30%+

CONS:
- Stale: Results only as fresh as last refresh
- Doesn't help long-tail queries (70% of traffic)
- Maintenance complexity

DECISION: Use as optimization layer on top of real-time search

REASONING:
- Query result cache achieves similar benefit with less complexity
- Cache with 60s TTL = nearly as fast as pre-computed
- Real-time search is the foundation; cache is an optimization
```

---

# Part 16: Interview Calibration (L5 + L6)

## Common Senior Mistake vs Staff Mistake

| Level | Mistake | Fix |
|-------|---------|-----|
| **Senior** | Optimize for perfect relevance (ML ranking from day one). | BM25 + boosts for V1; collect click data; add ML when signal exists. |
| **Senior** | Design search without failure-mode discussion. | Proactively discuss slow shard, partial results, rollback, relevance regression. |
| **Staff** | Build search in isolation without platform reuse. | Check if shared search platform exists; contribute requirements rather than maintain separate stack. |
| **Staff** | Solve relevance without cross-team SLO. | Define SLO with product (CTR, zero-result rate); agree on relevance regression criteria and escalation. |

## What Interviewers Evaluate

| Signal | How It's Assessed |
|--------|-------------------|
| Scope management | Do they clarify corpus size, query patterns, freshness needs? |
| Trade-off reasoning | Do they justify inverted index vs database, BM25 vs ML, NRT vs real-time? |
| Failure thinking | What happens if a shard is slow? If index is corrupted? |
| Scale awareness | Sharding strategy, scatter-gather overhead, page cache importance? |
| Relevance understanding | Do they discuss ranking, not just matching? |

## Example Strong L5 Phrases

- "First, let me clarify: how many documents, what QPS, and how fresh does search need to be?"
- "I'll use an inverted index—not a database—because query time must be proportional to results, not corpus size."
- "BM25 is sufficient for V1. ML ranking requires click data we don't have yet."
- "The scatter-gather across shards means P99 is dominated by the slowest shard."
- "Index corruption is recoverable because the index is derived from the primary database."

## How Google Interviews Probe Search Systems

```
COMMON INTERVIEWER QUESTIONS:

1. "How does search scale to billions of documents?"
   
   L4: "We shard the data."
   
   L5: "Shard the inverted index by document hash. Each shard holds
   a partition. Queries fan out to all shards (scatter), each shard
   returns top K results, coordinator merges (gather).
   
   At 10× scale, the bottleneck is scatter-gather tail latency—
   P99 is the slowest shard. Mitigation: replicas, per-shard
   timeouts, and potentially routing queries to shard subsets
   when the query implies a partition (e.g., category)."

2. "How do you ensure search results are relevant?"
   
   L4: "We use TF-IDF or keyword matching."
   
   L5: "BM25 for text relevance, plus configurable boost factors
   for quality signals: popularity, freshness, field weights (title
   match scores higher than description match).
   
   But relevance isn't just an algorithm—it's an operational concern.
   We need to measure it: CTR on top results, zero-result rate,
   and relevance regression tests that run before any config change."

3. "What if a shard goes down?"
   
   L4: "We have replicas."
   
   L5: "Each shard has 2 replicas. If the primary fails, a replica
   is promoted. Queries continue against the remaining replica.
   
   But the subtle case is a SLOW shard (not down). Coordinator
   sets a 500ms per-shard timeout. If shard 2 is slow, we return
   results from shards 0, 1, 3, 4 and note 'partial results.'
   Users rarely notice because results are distributed across shards."
```

## Common L4 Mistakes

```
L4 MISTAKE: "Use SQL LIKE for search"

WHY IT'S L4: Doesn't understand inverted index or why it exists.
Problem: Full table scan, O(N × L); no ranking, no typo tolerance.

L5 APPROACH: Inverted index + BM25. Query time O(result set), not O(corpus).


L4 MISTAKE: "Shard by category for better locality"

WHY IT'S L4: Optimizes for one query pattern, breaks for cross-category.
Problem: "laptop bags" touches both "electronics" and "accessories" shards; hot shard for popular categories.

L5 APPROACH: Hash-based sharding for uniform distribution. Accept full scatter-gather; optimize with caching and replicas.


BORDERLINE L5 MISTAKE: "Use ML ranking from day one"

WHY IT'S BORDERLINE: Shows ambition but not pragmatism.
Problem: ML ranking requires training data, feature engineering, model serving; premature for V1.

L5 FIX: BM25 + boost factors for V1. Collect click data. Add ML ranking when you have enough signal.


BORDERLINE L5 MISTAKE: Good design (sharding, BM25, NRT) but no failure mode discussion

WHY IT'S BORDERLINE: Shows skill but not ownership mentality.
Problem: Interviewer infers candidate wouldn't think about partial failures, rollback, or on-call.

L5 FIX: Proactively discuss "what happens when one shard is slow," "how we roll back a bad config," and "how we detect relevance regression."
```

## L6 / Staff Interview Calibration

### Staff-Level Probes

| Probe | What It Surfaces | Staff Signal |
|-------|------------------|--------------|
| "Ten teams need search. How do you approach it?" | Platform vs per-team design. | "Shared search platform. Each team has own index and config. Platform owns cluster, indexing pipeline, SLO." |
| "Finance wants 30% cost cut on search. What do you do?" | Cost vs reliability trade-off. | "Quantify risk per option. Spot for replicas first. Document blast radius of removing replica. Never cut primaries or cache." |
| "How do you explain search relevance to a non-engineer executive?" | Leadership communication. | "Relevance is: does the user find what they need in the first page? We measure it with click-through rate and zero-result rate." |
| "How would you teach this to a new L5?" | Teaching and leveling. | "Start with inverted index and why it's not a database. Then failure modes and partial results. Then relevance as an operational concern. Exercises on misleading metrics." |

### Staff Signals (What to Listen For)

- **Cross-team ownership**: "Platform owns the cluster; product teams own their index schema and relevance config. We have an SLO handoff."
- **Blast radius**: "Single shard corruption affects 20% of results. Full rebuild takes 30–40 minutes; we serve from replicas during rebuild."
- **Cost allocation**: "We charge back by index size and QPS. Teams see their search cost."
- **Technical debt awareness**: "Synonym file is manual; we have a ticket for ML-based query expansion when we have click data."

### Common Senior Mistake at Staff Bar

**Mistake:** Designing the perfect search system for one product without considering platform reuse or multi-tenant cost allocation.

**Staff phrasing:** "Before building, I'd check if platform already has search. We'd contribute requirements—index schema, relevance SLO—rather than maintain a separate cluster."

### How to Teach This Chapter

1. **First pass:** Read Problem Definition, Mental Model, and Inverted Index. Understand why search is not a database.
2. **Second pass:** Read Failure Handling, Real Incident table, and Misleading Signals. Practice 3 AM debugging flow.
3. **Third pass:** Read Staff vs Senior contrast and Cost. Practice explaining relevance to a non-engineer.
4. **Exercises:** Complete Part 18. Focus on Scale (A1, A2), Failure (B1–B6), and Cost (C1).

---

# Part 17: Diagrams

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        SEARCH SYSTEM ARCHITECTURE                           │
│                                                                             │
│   DATA SOURCES                                                              │
│   ┌──────────┐   ┌──────────┐     ┌──────────┐                              │
│   │ Product  │   │  CMS     │     │  User    │                              │
│   │   DB     │   │  DB      │     │  DB      │                              │
│   └────┬─────┘   └────┬─────┘     └────┬─────┘                              │
│        └───────────────┼───────────────┘                                    │
│                        │ CDC events                                         │
│                        ▼                                                    │
│   ┌─────────────────────────────────────────┐                               │
│   │          KAFKA (Change Events)          │                               │
│   └────────────────────┬────────────────────┘                               │
│                        │                                                    │
│                        ▼                                                    │
│   ┌─────────────────────────────────────────┐                               │
│   │     INDEXING PIPELINE (Transform + Write)│                              │
│   └────────────────────┬────────────────────┘                               │
│                        │                                                    │
│                        ▼                                                    │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    SEARCH CLUSTER                                   │   │
│   │                                                                     │   │
│   │   ┌──────────────────────────────────────────────────────────────┐  │   │
│   │   │  COORDINATOR (scatter-gather, merge, result cache)           │  │   │
│   │   └──────────────────────────┬───────────────────────────────────┘  │   │
│   │                              │                                      │   │
│   │          ┌───────────────────┼───────────────────┐                  │   │
│   │          ▼                   ▼                   ▼                  │   │
│   │   ┌────────────┐     ┌────────────┐     ┌────────────┐              │   │
│   │   │  Shard 0   │     │  Shard 1   │     │  Shard 2   │  ...         │   │
│   │   │ P + 2R     │     │ P + 2R     │     │ P + 2R     │              │   │
│   │   └────────────┘     └────────────┘     └────────────┘              │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                        ▲                                                    │
│                        │                                                    │
│   ┌─────────────────────────────────────────┐                               │
│   │          SEARCH API (stateless)         │                               │
│   └────────────────────┬────────────────────┘                               │
│                        ▲                                                    │
│              ┌─────────┼─────────┐                                          │
│              │         │         │                                          │
│           ┌──┴──┐   ┌──┴──┐   ┌──┴──┐                                       │
│           │ Web │   │Mobil│   │ API │                                       │
│           └─────┘   └─────┘   └─────┘                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Index Write + Query Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              INDEX WRITE → NRT REFRESH → QUERY FLOW                         │
│                                                                             │
│  Source DB      Kafka       Indexer       Shard        Coordinator   Client │
│    │              │           │            │              │            │    │
│    │ CDC event    │           │            │              │            │    │
│    │─────────────▶│           │            │              │            │    │
│    │              │ consume   │            │              │            │    │
│    │              │──────────▶│            │              │            │    │
│    │              │           │ transform  │              │            │    │
│    │              │           │ + index    │              │            │    │
│    │              │           │───────────▶│              │            │    │
│    │              │           │            │ write to     │            │    │
│    │              │           │            │ in-memory    │            │    │
│    │              │           │            │ buffer       │            │    │
│    │              │           │            │              │            │    │
│    │              │           │            │ [1-5s later: │            │    │
│    │              │           │            │  NRT refresh]│            │    │
│    │              │           │            │ doc becomes  │            │    │
│    │              │           │            │ searchable   │            │    │
│    │              │           │            │              │            │    │
│    │              │           │            │              │ GET /search│    │
│    │              │           │            │              │◀───────────│    │
│    │              │           │            │◀─────────────│ scatter    │    │
│    │              │           │            │ search local │            │    │
│    │              │           │            │─────────────▶│ gather     │    │
│    │              │           │            │              │───────────▶│    │
│    │              │           │            │              │  results   │    │
│                                                                             │
│   INDEX TIMING: Source change → searchable in 1-5 seconds                   │
│   QUERY TIMING: Request → results in 30-200ms                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 18: Brainstorming & Senior-Level Exercises (MANDATORY)

---

## A. Scale & Load Thought Experiments

### Experiment A1: Traffic Growth

| Scale | Documents | QPS | Shards | What Changes | What Breaks First |
|-------|-----------|-----|--------|--------------|-------------------|
| Current | 50M | 2K | 5 | Baseline | Nothing |
| 2× | 100M | 4K | 10 | More shards + replicas | Scatter-gather latency |
| 5× | 250M | 10K | 25 | Many more replicas | Coordinator fan-out |
| 10× | 500M | 20K | 50 | Architecture change needed | P99 tail latency |

#### Scale Estimates Table (L5 Checklist)

| Metric | Current | 10× Scale | Breaking Point |
|--------|---------|-----------|----------------|
| Documents | 50M | 500M | When index exceeds page cache per node |
| QPS | 2K | 20K | When coordinator fan-out or single-node CPU saturates |
| Search nodes | 10 | 100 | When operational burden (shards, rebalancing) becomes unsustainable |
| Index size | 100 GB | 1 TB | When single node can't hold shard in RAM/cache |
| Shards | 5 | 50 | When scatter-gather P99 dominates (slowest shard wins) |

**Scale analysis:** The most fragile assumption is *index fits in OS page cache*. At 10×, the first thing that breaks is P99 latency (tail shard + coordinator merge). Back-of-envelope: 50 shards × 50ms P99 per shard → coordinator waits on slowest; one 500ms shard makes whole query 500ms+.

```
AT 2× (100M docs, 4K QPS):
    Changes: Double shards (10); add replicas for QPS
    First stress: More shards per query = higher tail latency
    Action: Add query result cache; increase replicas

AT 10× (500M docs, 20K QPS):
    Changes: 50 shards; consider two-tier query routing
    First stress: Fan-out to 50 shards; coordinator bottleneck
    Action:
    - Two-phase query: estimate shard relevance, only query top-N shards
    - Or: Partition by category (accept uneven shard sizes)
    - Or: Multiple coordinators with load balancing
```

### Experiment A2: Most Fragile Assumption

```
FRAGILE ASSUMPTION: "Index fits in OS page cache"

Why it's fragile:
- Index grows with corpus; RAM is fixed
- Once index > page cache, queries hit disk
- Disk reads: 5ms each vs 0.05ms from memory = 100× slower

What breaks:
    If index outgrows cache:
    - P50 latency: 50ms → 500ms
    - P99 latency: 200ms → 2000ms
    - User experience degrades catastrophically
    
Detection: Page cache hit rate dropping; disk IOPS increasing

Mitigation:
    - Add more nodes (distribute index across more RAM)
    - SSD (fast disk) limits impact to 5× not 100×
    - Index tiering: Keep hot data in memory, cold on disk
```

---

## B. Failure Injection Scenarios

### Scenario B1: Slow Shard (10× Latency)

```
SITUATION: Shard 2 responding at 500ms instead of 50ms

IMMEDIATE BEHAVIOR:
- Coordinator waits 500ms for shard 2, or times out
- Overall query latency increases
- If timeout: Partial results (missing shard 2 data)

USER SYMPTOMS:
- Search feels slower
- Or: Some results missing

DETECTION:
- Per-shard latency metrics
- P99 search latency spike
- Partial failure counter increasing

MITIGATION:
1. Route queries to shard 2 replicas (skip slow primary)
2. Investigate: Segment merge? GC pause? Disk issue?
3. If persistent: Restart node, wait for cache warm-up

PERMANENT FIX: Investigate root cause; add monitoring for segment merge impact
```

### Scenario B2: Full Index Rebuild Required

```
SITUATION: Index corrupted after bad migration; need full rebuild

IMMEDIATE BEHAVIOR:
- Serve from replicas (if healthy)
- Start rebuild from source database

USER SYMPTOMS:
- Search works (from replicas)
- Possibly stale results if replicas also affected

TIMELINE:
- 50M documents at 10K docs/sec indexing rate
- Full rebuild: ~5,000 seconds = ~83 minutes
- During rebuild: Read from replicas; no new indexing

MITIGATION:
1. Never modify index in place; always build new index alongside
2. Alias swap: Build new index, swap alias when ready
3. Zero-downtime rebuild pattern
```

### Scenario B3: Kafka Down (Indexing Pipeline)

```
SITUATION: Kafka broker unavailable for 1 hour

IMMEDIATE BEHAVIOR:
- No new documents indexed
- Search continues serving existing index
- Index becomes increasingly stale

USER SYMPTOMS:
- New products not findable via search
- Updated prices/stock not reflected

DETECTION:
- Kafka health alert
- Indexing lag metric increasing
- Consumer offset stalled

MITIGATION:
1. Kafka cluster has 3 brokers; tolerates 1 failure
2. If all brokers down: Search still works (degraded freshness)
3. On recovery: Consumer catches up from last offset
4. Kafka retention: 7 days (no data loss)

PERMANENT FIX: Multi-broker Kafka; monitor broker health proactively
```

### Scenario B4: Cache Stampede (Cold Start)

```
SITUATION: Node restart or cache flush; all queries hit disk

IMMEDIATE BEHAVIOR:
- Every query reads from SSD instead of memory
- Latency: 50ms → 500ms (10× slower)
- Throughput: 800 QPS → 80 QPS per node

USER SYMPTOMS:
- Search very slow for 5-10 minutes after restart
- Timeouts during cache warming

DETECTION:
- Node restart alert
- Latency spike after restart
- Disk I/O spike

MITIGATION:
1. Don't route traffic until cache is warm
2. Warm cache by replaying recent popular queries
3. Rolling restarts: One node at a time, wait for warm

PERMANENT FIX: Pre-warm script; health check includes cache readiness
```

### Scenario B5: Database Failover (Document Store / Source DB)

```
SITUATION: Primary DB (source of truth for documents) fails; failover to secondary.

IMMEDIATE BEHAVIOR:
- CDC/Kafka may have brief gap or duplicate events during failover
- Indexing pipeline: Consumer may see out-of-order or repeated events
- Search cluster: Unaffected (serves from existing index)
- Document enrichment (fetch full body from doc store): If doc store is same DB, reads go to new primary after failover

USER SYMPTOMS:
- Short window (seconds to 1–2 min): Possible stale or missing docs if indexing lagged
- Once consumer catches up: Search and doc store both consistent with new primary

DETECTION:
- DB failover alerts; Kafka consumer lag spike; brief indexing lag

MITIGATION:
1. Idempotent indexing: Replayed events overwrite same doc; no duplicates in index
2. Document store: Read from secondary if available during failover to avoid overloading new primary
3. After failover: Let consumer drain lag; verify index freshness metric

PERMANENT FIX: Document store read replica for enrichment; indexing pipeline tolerates brief event gap (at-least-once + idempotent write).
```

### Scenario B6: Retry Storm (Client Retries on Timeout)

```
SITUATION: One shard slow → search P99 rises → clients timeout and retry → effective QPS 2×–3× → coordinator and shards overload.

IMMEDIATE BEHAVIOR:
- Latency spike causes more timeouts → more retries → more load → more latency
- Cascade: Healthy shards start missing SLA; partial results increase

USER SYMPTOMS:
- Search intermittently very slow or "no results"
- Errors or timeouts in UI/API

DETECTION:
- QPS spike (retries) with error rate or timeout rate increasing
- Per-shard latency: One shard slow first, then others degrade

MITIGATION:
1. Client: Strict retry policy (e.g. 1 retry, backoff 100ms); no retry on timeout for search (return partial results instead)
2. Server: Per-shard timeout (500ms) so coordinator doesn't wait forever; return partial results + shards_failed
3. Circuit breaker: If error rate > threshold, fail fast to avoid cascading load

PERMANENT FIX: Limit retries; prefer partial results over retry storm; alert on retry rate and per-shard P99.
```

### Staff Consideration: Cross-Team Blast Radius

When multiple product teams share one search cluster, a config change (synonym, boost, analyzer) can affect all teams. **Blast radius**: One bad synonym deploy degrades relevance for every team using that index. **Mitigation**: Per-team indexes when blast radius must be isolated; shared index with canary deploy when cost matters. **Trade-off**: Per-team indexes multiply cost; shared index requires coordination and regression tests across teams.

---

## C. Cost & Trade-off Exercises

### Exercise C1: 30% Cost Reduction

```
CURRENT COST: $7,000/month

OPTIONS:

Option A: Reduce replicas (2 → 1 per shard) (-$1,500)
    Risk: Single replica = one node failure away from partial outage
    Recommendation: NO for production

Option B: Smaller nodes (-$1,000)
    Risk: Less RAM = less page cache = slower queries
    Recommendation: CAREFUL - test latency impact first

Option C: Reduce indexing pipeline resources (-$200)
    Risk: Slower indexing; more stale results
    Recommendation: YES if freshness tolerance is > 30 seconds

Option D: Use spot/preemptible instances for replicas (-$1,500)
    Risk: Instances can be terminated with 30s notice
    Recommendation: YES for replicas only (primaries on regular instances)

SENIOR RECOMMENDATION:
    Options C + D = ~$1,700 savings (24%)
    Keep primaries and at least 1 replica on stable instances
```

---

## D. Ownership Under Pressure

```
SCENARIO: 30-minute mitigation window

2 AM alert: "Search P99 latency > 2 seconds" (baseline: 200ms)

1. What do you check first?
   - Per-shard latency: Is one shard slow or all?
   - Node health: CPU, memory, disk I/O
   - Recent deploys or config changes
   - Segment merge in progress? (heavy background I/O)
   
2. What do you AVOID touching?
   - Index settings (shard count, analyzer)
   - Synonym/boost config
   - Shard rebalancing (makes things worse short-term)
   
3. Escalation criteria?
   - If all shards slow: Likely node-level issue → engage infra
   - If one shard slow: Try routing to replica first
   - If index corruption suspected: Engage team lead
   
4. Communication?
   "Search latency elevated. Investigating per-shard metrics. 
   No data loss. Will update in 10 minutes."
```

---

## E. Correctness & Data Integrity

### Exercise E1: Ensuring Deleted Documents Are Unsearchable

```
QUESTION: Product recalled. Must not appear in search. How fast?

REQUIREMENT: Deleted within one NRT refresh cycle (1-5 seconds)

IMPLEMENTATION:
1. Delete event sent to Kafka
2. Indexer consumes and marks document as deleted
3. Next NRT refresh (1-5s): Document excluded from search
4. Physical removal: Next segment merge (background)

VERIFICATION:
- After delete: Query by exact doc_id → should return 0 results
- Monitor: "Deleted but still searchable" metric

COMPLIANCE: For GDPR right-to-erasure, 1-5 seconds is well within requirements.
```

---

## F. Incremental Evolution & Ownership

### Exercise F1: Adding Autocomplete (2 weeks)

```
REQUIRED CHANGES:
- New suggestion index (separate from main index)
- Prefix-based lookup (edge-ngram or trie)
- Popularity ranking (from query logs)
- New API endpoint: GET /suggest?q=prefix

RISKS:
- Suggestion quality depends on query log data
- Prefix index adds storage and memory
- Must be very fast (< 30ms)

DE-RISKING:
- Start with static popular queries (no ML)
- Separate index: doesn't affect main search
- Feature flag for gradual rollout
```

### Exercise F2: Safe Index Migration (Zero Downtime)

```
SCENARIO: Need to change analyzer (breaking change)

SAFE PROCEDURE:

Phase 1: Create new index with new analyzer
    - New index: "products_v2"
    - Old index: "products_v1" (still serving)
    - Both exist simultaneously

Phase 2: Full re-index into new index
    - Index all 50M documents into products_v2
    - Duration: ~83 minutes

Phase 3: Alias swap
    - Search alias "products" points to products_v1
    - Atomically swap: "products" → products_v2
    - Zero downtime: One request uses v1, next uses v2

Phase 4: Cleanup
    - Delete products_v1 after verification
    - Monitor: Relevance, latency, zero-result rate

ROLLBACK:
    Swap alias back to products_v1 (instant, < 1 second)
```

---

## G. Interview-Oriented Thought Prompts

### Prompt G1: Clarifying Questions to Ask First

```
1. "How many documents and what's the average size?"
   → Determines: Shard count, index size, RAM needs

2. "What QPS and latency requirement?"
   → Determines: Replica count, caching strategy

3. "How fresh must search be?"
   → Determines: NRT refresh interval, indexing pipeline design

4. "What types of queries? Full-text, filtered, faceted?"
   → Determines: Index schema, field types

5. "Is relevance critical (e-commerce) or good-enough (internal tool)?"
   → Determines: Ranking investment, BM25 vs ML
```

### Prompt G2: What You Explicitly Don't Build

```
1. ML RANKING (V1)
   "BM25 + boosts for V1. ML needs click data we don't have yet."

2. PERSONALIZATION
   "Same results for same query. Add user signals when we have them."

3. CROSS-LANGUAGE SEARCH
   "Single language V1. Add language-specific analyzers in V2."

4. IMAGE SEARCH
   "Text search only. Image search requires separate embedding pipeline."

5. REAL-TIME INDEXING
   "Near-real-time (1-5s delay). True real-time requires transactional index."
```

---

# Final Verification

```
✓ This chapter MEETS Google Senior Software Engineer (L5) expectations.

SENIOR-LEVEL SIGNALS COVERED:

A. Design Correctness & Clarity:
✓ End-to-end: Index → Query → Scatter-Gather → Rank → Return
✓ Component responsibilities clear (coordinator, shards, indexer)
✓ Inverted index vs database justified

B. Trade-offs & Technical Judgment:
✓ BM25 vs ML ranking, hash vs category sharding, NRT vs real-time
✓ Fail-open on partial shard failure
✓ Explicit non-goals and deferred optimizations

C. Failure Handling & Reliability:
✓ Partial failure (slow shard, partial results)
✓ Index corruption recovery
✓ Realistic production scenario (bad synonym config)
✓ Timeout and retry configuration

D. Scale & Performance:
✓ Concrete numbers (50M docs, 2K QPS, 100 GB index)
✓ Scale Estimates Table (Current / 10× / Breaking Point)
✓ 10× scale analysis (scatter-gather bottleneck)
✓ Page cache as most fragile assumption

E. Cost & Operability:
✓ $7K/month breakdown
✓ Cost Analysis Table (Current / At Scale / Optimization)
✓ Misleading signals section (QPS normal but results irrelevant)
✓ On-call burden analysis

F. Ownership & On-Call Reality:
✓ Debugging "search results are bad"
✓ 30-minute mitigation scenario
✓ Relevance as operational concern

G. Rollout & Operational Safety:
✓ Deployment strategy (rolling, canary for config)
✓ Zero-downtime index migration (alias swap)
✓ Bad analyzer deployment scenario
✓ Rushed Decision scenario (shipping filter-only for model field)

H. Interview Calibration:
✓ L4 vs L5 mistakes with WHY IT'S L4 / L5 FIX
✓ Borderline L5 mistake (no failure discussion) with L5 FIX
✓ Strong L5 signals and phrases
✓ Clarifying questions and non-goals

Brainstorming (Part 18):
✓ Failure scenarios: Slow shard, full rebuild, Kafka down, cache stampede, database failover (B5), retry storm (B6)
✓ Ownership Under Pressure: 30-minute mitigation scenario
```
