# Chapter 49. Search / Indexing System (Read-Heavy, Latency-Sensitive)

---

# Introduction

Search is the system that turns unstructured human intent into structured results in under 200 milliseconds across billions of documents, multiple languages, dozens of regions, and thousands of queries per second. I've spent years building and operating search infrastructure at Google-scale, and I'll be direct: the hard part isn't building an inverted index—any engineer can stand up Elasticsearch in an afternoon. The hard part is serving 100K queries per second with P99 under 100ms while indexing 50K document mutations per second, keeping relevance tuned across hundreds of ranking signals, surviving the loss of an entire datacenter without users noticing, and evolving the system from a single-cluster prototype into a globally distributed, multi-tenant platform that dozens of product teams depend on as their primary read path.

This chapter covers the design of a search and indexing system at Staff Engineer depth: with deep understanding of the inverted index mechanics that drive latency, awareness of the failure modes that degrade relevance and freshness silently, judgment about where to shard, how to replicate, and when to sacrifice consistency for availability—and the organizational reality of owning a shared search platform that multiple teams build products on top of.

**The Staff Engineer's First Law of Search**: Search is not a feature—it's an infrastructure service. When search is slow, every product that uses it is slow. When search returns stale results, every product shows stale data. When search is down, navigation-dependent products survive but query-dependent products are dead. Treat search with the same criticality as your database tier.

---

## Quick Visual: Search / Indexing System at a Glance

```
┌─────────────────────────────────────────────────────────────────────────────┐
│     SEARCH / INDEXING SYSTEM: THE STAFF ENGINEER VIEW                       │
│                                                                             │
│   WRONG Framing: "An Elasticsearch cluster that indexes documents"          │
│   RIGHT Framing: "A globally distributed information retrieval platform     │
│                   that ingests billions of documents, serves sub-100ms      │
│                   ranked results at 100K+ QPS, supports near-real-time      │
│                   freshness, multi-tenancy, and cross-region failover—      │
│                   owned by a platform team, consumed by dozens of           │
│                   product teams"                                            │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Before designing, understand:                                      │   │
│   │                                                                     │   │
│   │  1. What is the corpus? (Products? Documents? Messages? Mixed?)     │   │
│   │  2. What is the read:write ratio? (1000:1? 100:1? 10:1?)            │   │
│   │  3. What freshness does the business need? (Seconds? Minutes?)      │   │
│   │  4. How many distinct tenants / product teams use search?           │   │
│   │  5. Is relevance a differentiator? (Search IS the product? Or       │   │
│   │     search assists navigation?)                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   THE UNCOMFORTABLE TRUTH:                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Search looks like a read-heavy system, and it is. But the real     │   │
│   │  complexity is in the WRITE PATH: ingesting documents, analyzing    │   │
│   │  text, building index segments, merging them, replicating them      │   │
│   │  across regions—all while serving live queries without degrading    │   │
│   │  latency. The write path is where Staff Engineers spend 70% of      │   │
│   │  their design time.                                                 │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## L5 vs L6 Search System Decisions

| Scenario | L5 Approach | L6 Approach |
|----------|-------------|-------------|
| **Index design** | "Use an inverted index, shard by document ID" | "Shard by document ID for writes but consider query-aware partitioning for hot terms. Use tiered storage: hot segments in memory-mapped files, warm on SSD, cold on object storage. Index schema is versioned and evolved without full rebuild through dual-write and shadow indexing." |
| **Query processing** | "Parse query, fan out to all shards, merge results" | "Parse query, rewrite with synonyms and spelling correction, route to the minimum set of shards needed (partition pruning via metadata index), enforce per-tenant timeout budgets, scatter-gather with speculative retries on slow shards, merge with position-aware scoring, apply business rules post-merge." |
| **Relevance** | "BM25 scoring with some boost factors" | "Multi-phase ranking pipeline: Phase 1 (retrieval) uses BM25 on inverted index to get top-N candidates. Phase 2 (ranking) applies ML-based scoring with features: text relevance, freshness, popularity, personalization, quality signals. Phase 3 (business rules) applies pinned results, filtering, diversity. Each phase has its own latency budget." |
| **Freshness** | "Near-real-time indexing with periodic refresh" | "Tiered freshness: transaction log provides search-on-write for critical updates (seconds), NRT segments serve most updates (1–5 seconds), background segment merge provides optimized serving. Freshness SLO per tenant—some need sub-second, some tolerate minutes. Measure indexing lag as a first-class metric." |
| **Failure handling** | "Replicas serve reads if primary fails" | "Per-shard circuit breakers. If one shard is slow, return partial results with a 'results may be incomplete' signal rather than timing out the whole query. If a region fails, traffic shifts to the surviving region serving stale replicas. Relevance degradation under failure is measured and acceptable—total failure is not." |
| **Multi-tenancy** | "Separate index per tenant" | "Shared index cluster with logical isolation: per-tenant query quotas, per-tenant indexing throughput limits, per-tenant relevance configuration, tenant-aware shard routing to prevent noisy-neighbor. Separate indexes only for tenants with fundamentally different schemas or SLAs." |

**Key Difference**: L6 engineers recognize that a search system is a platform with multiple consumers, not a feature with one owner. The design must account for multi-tenancy, independent relevance tuning per use case, graceful degradation under partial failure, and evolution without downtime—while maintaining sub-100ms P99 at scale.

---

# Part 1: Foundations — What a Search System Is and Why It Exists

## What Is a Search System?

A search system is an information retrieval platform that ingests documents (structured, semi-structured, or unstructured), builds specialized data structures (inverted indexes, column stores, vector indexes) optimized for fast lookup by content, and serves ranked results in response to user queries. It sits between the source-of-truth data stores and the user-facing applications, providing a read-optimized view of data that would be prohibitively slow to query directly.

### The Simplest Mental Model

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    THE SIMPLEST MENTAL MODEL                                │
│                                                                             │
│   A search system is a LIBRARY CATALOG:                                     │
│                                                                             │
│   WRITE PATH (Librarian cataloging books):                                  │
│   New book arrives → Extract metadata (title, author, subject, keywords)    │
│   → Create index cards → File in catalog drawers by subject, author, title  │
│                                                                             │
│   READ PATH (Patron searching):                                             │
│   "Books about distributed systems by Kleppmann"                            │
│   → Check subject drawer → Check author drawer → Intersect results          │
│   → Sort by relevance (newer editions first, highly cited first)            │
│   → Return top results                                                      │
│                                                                             │
│   WHY NOT JUST SCAN ALL BOOKS?                                              │
│   1 million books × 1ms per book = 1000 seconds to scan                     │
│   Index lookup: 5ms regardless of collection size                           │
│                                                                             │
│   A SEARCH SYSTEM IS THIS LIBRARY CATALOG, AT:                              │
│   → Billions of documents instead of millions of books                      │
│   → 100K lookups per second instead of 10 patrons per hour                  │
│   → Sub-100ms response instead of "come back tomorrow"                      │
│   → Updated continuously instead of monthly                                 │
│   → Replicated across continents instead of one building                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### What the System Does on Every Query

```
FOR each incoming search query:

  1. QUERY PARSING & UNDERSTANDING
     Raw query: "red runnning shoes under $50"
     → Tokenize: ["red", "runnning", "shoes", "under", "$50"]
     → Spell correct: "runnning" → "running"
     → Synonym expand: "shoes" → ["shoes", "sneakers", "footwear"]
     → Extract filters: price < $50
     → Final query: (red AND running AND (shoes OR sneakers OR footwear))
                     FILTER price < 50
     Cost: ~5ms

  2. SHARD ROUTING
     Determine which shards hold potentially relevant documents
     For term queries: all shards (documents are hash-partitioned)
     For tenant-specific queries: subset of shards (tenant-aware routing)
     Cost: ~0.1ms

  3. SCATTER (parallel fan-out to shards)
     Send parsed query to N shard replicas simultaneously
     Each shard: look up posting lists, intersect, score, return top-K
     Cost: ~10-50ms per shard (in parallel)

  4. GATHER (merge results from all shards)
     Merge N sorted result lists into one globally sorted list
     Re-rank top results with cross-shard scoring adjustments
     Cost: ~2ms

  5. POST-PROCESSING
     Apply business rules (pinned results, boosted items, content policy)
     Compute facet counts (category: shoes(1200), sneakers(800))
     Truncate to requested page size
     Cost: ~1ms

  6. RESPONSE
     Return ranked results with highlights, facets, metadata
     Include: query_id, latency_ms, total_hits, shard_stats
     Cost: ~0.5ms

  TOTAL: ~20-60ms (P50), ~80-120ms (P95), ~150-250ms (P99)
  BUDGET: The entire query must complete within 200ms.
  Each component competes for this shared budget.
```

## Why a Search System Exists

### 1. Databases Are Wrong for Text Retrieval

```
PROBLEM: Relational databases optimize for exact-match and range queries,
         not for relevance-ranked text retrieval.

SQL approach to "red running shoes":
  SELECT * FROM products 
  WHERE description LIKE '%red%' 
    AND description LIKE '%running%' 
    AND description LIKE '%shoes%'
  ORDER BY ??? -- No relevance scoring
  LIMIT 10;

  PROBLEMS:
  → Full table scan: O(N × L) per query — 10M rows × 500 chars = 5B comparisons
  → No relevance ranking: Results ordered arbitrarily
  → No typo tolerance: "runnning" → 0 results
  → No synonym handling: "sneakers" won't match "shoes"
  → Latency: 5-30 seconds on 10M rows vs 50ms with inverted index

Search approach:
  Inverted index: pre-computed mapping of words → document IDs
  "running" → [doc_42, doc_87, doc_193, doc_455, ...]  (50K docs)
  "shoes"   → [doc_42, doc_100, doc_193, doc_300, ...]  (80K docs)
  "red"     → [doc_42, doc_193, doc_500, ...]           (30K docs)
  
  Intersection: [doc_42, doc_193, ...] (12K docs match all three)
  Score and rank top 10: < 50ms total

  WHY FASTER: Index is pre-built. Query time is proportional to 
  posting list length (result set), NOT corpus size.
```

### 2. Search Enables Product Experiences That Browsing Cannot

```
AT SCALE, BROWSING FAILS:

10 items         → Users browse. Menu works fine.
1,000 items      → Categories help. Browsing is slow but possible.
100,000 items    → Category trees get deep. Users get lost.
10,000,000 items → Browsing is impossible. Search is the primary interface.

SEARCH-DEPENDENT PRODUCTS:
→ E-commerce: Product search IS the product (Amazon, eBay)
→ Knowledge bases: Document search drives support workflows
→ Communication: Message search enables re-finding conversations
→ Content platforms: Content discovery drives engagement
→ Internal tools: Code search, log search, config search

STAFF INSIGHT: When search is the primary interface, search latency
IS product latency. A 50ms regression in search is a 50ms regression
in the product. This is why search is infrastructure, not a feature.
```

### 3. The Freshness Imperative

```
WHY FRESHNESS MATTERS:

E-commerce:
  Product listed at 10:00:01 → User searches at 10:00:05
  If indexing lag is 10 minutes → Product not found → Lost sale
  
  Product goes out of stock at 10:00:01 → User finds it at 10:00:05
  If indexing lag is 10 minutes → User sees stale inventory → Bad UX

Marketplace:
  Listing posted → Must be searchable within seconds
  Listing sold → Must be removed from search within seconds
  Stale listings erode trust

Communication:
  Message sent → Must be searchable by recipient immediately
  Lag of minutes is unacceptable for "I just sent it, let me find it"

FRESHNESS IS NOT FREE:
  → Real-time indexing competes with query serving for resources
  → Faster indexing = more segment merges = more I/O = query latency risk
  → The Staff Engineer's job is defining the freshness SLO per use case
    and engineering the system to meet it without violating latency SLOs
```

## What Happens If the Search System Does NOT Exist (or Fails)

```
SCENARIO 1: No search system — application queries the database directly

  Impact:
  → Every text search is a full table scan
  → P99 query latency: 5-30 seconds (vs 100ms with search)
  → No relevance ranking — results are arbitrary
  → No typo tolerance — misspellings return nothing
  → Database CPU saturated by text matching → transactional writes slow down
  → As corpus grows, search gets slower (O(N) instead of O(log N))

  At Google scale (billions of documents):
  → Database approach is physically impossible
  → A single query would take minutes to hours

SCENARIO 2: Search system exists but goes down

  Impact:
  → All search-dependent products return empty results or errors
  → E-commerce: Users can browse categories but can't search → 40-70% drop in purchases
  → Support tools: Agents can't find knowledge base articles → resolution time doubles
  → Communication: Users can't find old messages → productivity collapses
  → Revenue impact: Proportional to how much the product relies on search

  Staff insight: The blast radius of search failure depends on whether
  products have fallback paths. Products that ONLY offer search (no browsing)
  have 100% failure on search outage. Products with browsing alternatives
  degrade but survive. Design the system for partial degradation, not
  all-or-nothing.

SCENARIO 3: Search system returns stale results

  Impact (silent failure — the worst kind):
  → Users see products that are out of stock → frustration, lost trust
  → Users don't see newly listed items → sellers leave platform
  → Users find deleted content → policy violations, legal risk
  → No error message — system looks healthy but results are wrong
  → Staleness is hard to detect without explicit freshness monitoring

  Staff insight: Staleness failures are MORE dangerous than downtime
  because they're invisible. You must monitor indexing lag as a
  first-class SLO, not just query latency and availability.
```

## One Intuitive Mental Model

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MENTAL MODEL: SEARCH AS A MIRROR                         │
│                                                                             │
│   SOURCE OF TRUTH              SEARCH INDEX                                 │
│   (Databases, services)        (Read-optimized mirror)                      │
│                                                                             │
│   ┌─────────────────┐          ┌─────────────────┐                          │
│   │ Products DB     │ ──────→  │ Product Index   │                          │
│   │ Messages DB     │ ──────→  │ Messages Index  │                          │
│   │ Users DB        │ ──────→  │ Users Index     │                          │
│   │ Documents Store │ ──────→  │ Documents Index │                          │
│   └─────────────────┘          └─────────────────┘                          │
│                                                                             │
│   The search index is NEVER the source of truth.                            │
│   It is a derived, denormalized, read-optimized PROJECTION                  │
│   of the authoritative data.                                                │
│                                                                             │
│   This has consequences:                                                    │
│   1. Index can be rebuilt from source — recovery path exists                │
│   2. Index can be stale — freshness lag is inherent                         │
│   3. Index can have different schema — optimized for queries, not writes    │
│   4. Index can be replicated independently — scale reads without            │
│      touching the source                                                    │
│   5. Index can be wrong — and that's fixable by reindexing                  │
│                                                                             │
│   The Staff Engineer's key insight: Because the index is derived,           │
│   you can make aggressive trade-offs (eventual consistency, approximate     │
│   results, stale data) that you would NEVER make on the source of truth.    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 2: Functional Requirements (Deep Enumeration)

## Core Use Cases

### 1. Full-Text Search

```
FUNCTION search(query, filters, sort, page, page_size, tenant_id):
  
  INPUT:
    query: "red running shoes"
    filters: {category: "footwear", price_max: 50, in_stock: true}
    sort: "relevance" | "price_asc" | "price_desc" | "newest"
    page: 1
    page_size: 20
    tenant_id: "ecommerce_team"
  
  OUTPUT:
    {
      results: [
        {id: "prod_42", title: "Red Trail Runners", score: 0.94,
         highlights: {"title": "<em>Red</em> Trail <em>Runners</em>"},
         price: 45.99, in_stock: true},
        ...
      ],
      total_hits: 12847,
      facets: {
        category: [{value: "running_shoes", count: 3200}, ...],
        brand: [{value: "Nike", count: 1100}, ...],
        price_range: [{value: "0-50", count: 4500}, ...]
      },
      query_metadata: {
        query_id: "q_abc123",
        latency_ms: 47,
        shards_queried: 12,
        shards_succeeded: 12,
        spell_corrected: false,
        synonyms_applied: ["shoes→sneakers"]
      }
    }

  BEHAVIOR:
  → Empty query with filters → returns filtered browse results
  → Query with no matches → returns empty results (NOT an error)
  → Query with partial shard failure → returns partial results with warning
  → Query exceeding timeout → returns best-effort results collected so far
```

### 2. Autocomplete / Typeahead

```
FUNCTION suggest(prefix, tenant_id, context):

  INPUT:
    prefix: "run"
    tenant_id: "ecommerce_team"
    context: {category: "footwear"}  // optional context for filtering

  OUTPUT:
    {
      suggestions: [
        {text: "running shoes", score: 0.95, result_count: 32000},
        {text: "running shorts", score: 0.82, result_count: 15000},
        {text: "running watch", score: 0.71, result_count: 8000}
      ],
      latency_ms: 8
    }

  LATENCY REQUIREMENT: < 30ms (P99)
  Users type faster than they read — suggestion must appear before next keystroke.
  
  STAFF CONSIDERATION:
  Autocomplete is a DIFFERENT index optimized for prefix matching (edge n-grams
  or prefix trie), NOT a regular search query. Treating autocomplete as a 
  full search query wastes resources and is too slow.
```

### 3. Document Indexing (Single Document)

```
FUNCTION index_document(document, tenant_id, index_name):

  INPUT:
    document: {
      id: "prod_42",
      title: "Red Trail Running Shoes",
      description: "Lightweight trail runners with...",
      category: "footwear",
      price: 45.99,
      in_stock: true,
      brand: "TrailMaster",
      created_at: "2025-01-15T10:00:00Z",
      updated_at: "2025-06-20T14:30:00Z"
    }
    tenant_id: "ecommerce_team"
    index_name: "products"

  OUTPUT:
    {status: "accepted", version: 7, indexing_lag_estimate_ms: 1500}

  BEHAVIOR:
  → New document: Creates entry in the index
  → Existing document (same ID): Updates in place (upsert semantics)
  → Indexing is ASYNCHRONOUS: Returns "accepted" immediately,
    document becomes searchable after indexing_lag
  → idempotent: Re-indexing the same document at the same version is a no-op
```

### 4. Bulk Indexing

```
FUNCTION bulk_index(documents[], tenant_id, index_name):

  INPUT:
    documents: [{id, fields}...] — up to 10,000 per batch
    tenant_id: "ecommerce_team"
    index_name: "products"

  OUTPUT:
    {
      accepted: 9980,
      rejected: 20,
      errors: [{id: "prod_999", reason: "schema_violation: price must be numeric"}]
    }

  BEHAVIOR:
  → Partial success: Accept valid documents, reject invalid ones
  → Batch is NOT transactional: No all-or-nothing guarantee
  → Ordering within batch is preserved per-document-ID (last write wins)
  → Used for: Initial data load, periodic full reindex, migration
  
  STAFF CONSIDERATION:
  Bulk indexing can consume significant cluster resources.
  Must be rate-limited per tenant to prevent impact on query serving.
  Separate ingestion pipeline from serving pipeline where possible.
```

### 5. Document Deletion

```
FUNCTION delete_document(document_id, tenant_id, index_name):

  OUTPUT:
    {status: "accepted", effective_after_ms: 1500}

  BEHAVIOR:
  → Soft-delete initially: Document marked as deleted in a deletion bitmap
  → Physically removed during segment merge (background process)
  → Query results exclude deleted documents immediately (deletion bitmap check)
  → Deleting non-existent document: Succeeds silently (idempotent)
```

### 6. Index Management

```
CONTROL OPERATIONS:

  CREATE INDEX:
    create_index(name, schema, settings, tenant_id)
    → Schema: field names, types, analyzers, index options
    → Settings: shard count, replica count, refresh interval
    → Tenant isolation: logical namespace within shared cluster

  UPDATE SCHEMA:
    update_schema(index_name, schema_changes, tenant_id)
    → Additive changes (new fields): Applied immediately
    → Destructive changes (remove field, change type): Require reindex
    → Schema versioning: Old and new schema coexist during migration

  REINDEX:
    reindex(source_index, target_index, transform_function)
    → Copies documents from source to target with optional transformation
    → Used for: Schema migration, analyzer changes, shard count changes
    → Must run WITHOUT impacting live query serving

  ALIAS:
    create_alias(alias_name, target_index)
    → Provides indirection: Queries use alias, alias points to index
    → Enables zero-downtime reindexing: Build new index, swap alias
```

## Read Paths

```
READ PATH 1: Full-text search query
  Client → Query API → Query Parser → Shard Router → Scatter to shards
  → Per-shard retrieval & scoring → Gather & merge → Post-process → Response

READ PATH 2: Autocomplete / Typeahead
  Client → Suggest API → Prefix Index Lookup → Return top suggestions
  (Separate, lighter-weight path — does NOT go through full query pipeline)

READ PATH 3: Get document by ID
  Client → Document API → Shard Router → Single shard lookup → Response
  (Direct hash lookup — no inverted index involved)

READ PATH 4: Scroll / Deep pagination
  Client → Scroll API → Stateful cursor → Fetch next page from shards
  (Uses search_after or scroll context — NOT offset-based pagination for deep pages)

READ PATH 5: Aggregation / Analytics queries
  Client → Query API → Scatter to shards → Per-shard aggregation
  → Gather & merge aggregations → Response
  (Facet counts, histograms, statistical aggregations)
```

## Write Paths

```
WRITE PATH 1: Single document index/update
  Source system → Indexing API → Validate → Write to transaction log
  → Acknowledge client → Background: Analyze text → Add to in-memory buffer
  → Periodic flush to disk segment → Background segment merge

WRITE PATH 2: Bulk index
  Source system → Bulk API → Validate batch → Write to transaction log
  → Acknowledge client → Background: Process batch through analysis pipeline
  → Flush to disk segments

WRITE PATH 3: Delete
  Source system → Delete API → Write tombstone to transaction log
  → Update deletion bitmap → Acknowledge client
  → Background: Physical removal during segment merge

WRITE PATH 4: Schema update
  Admin → Schema API → Validate compatibility → Update cluster metadata
  → Propagate to all shards → New documents use updated schema
  → Existing documents: Unchanged until reindex
```

## Control / Admin Paths

```
ADMIN PATH 1: Cluster health monitoring
  Admin → Cluster API → Shard allocation status, node health, index stats

ADMIN PATH 2: Tenant quota management
  Admin → Quota API → Set/update per-tenant QPS limits, indexing rate limits,
  storage quotas

ADMIN PATH 3: Relevance tuning
  Tenant admin → Relevance API → Update boost factors, custom scoring functions,
  synonym dictionaries, stop word lists — per tenant, per index

ADMIN PATH 4: Index lifecycle management
  Admin → Lifecycle API → Define policies: hot → warm → cold → delete
  Based on: index age, document freshness, access frequency

ADMIN PATH 5: Query analysis / explain
  Admin → Explain API → For a given query+document, show full scoring breakdown:
  which terms matched, BM25 scores, boost factors, final score
  Used for relevance debugging
```

## Edge Cases

```
EDGE CASE 1: Empty query with filters only
  → Treated as a filtered browse — return all matching documents sorted by default
  → This is a valid and common use case (category browsing)

EDGE CASE 2: Query matches millions of documents
  → Only score and return top-K (e.g., top 10,000)
  → total_hits is approximate for large result sets (saves counting time)
  → Exact counts available on request but cost more

EDGE CASE 3: Document updated multiple times during indexing
  → Last-write-wins based on document version
  → Out-of-order updates handled via version comparison at index time
  → Stale update (lower version) is discarded

EDGE CASE 4: Query contains only stop words ("the", "a", "is")
  → Return results but with reduced relevance discrimination
  → May fall back to popularity-based ranking

EDGE CASE 5: Unicode, emoji, CJK (Chinese/Japanese/Korean) text
  → Requires language-specific tokenizers (not whitespace splitting)
  → CJK: Character n-gram tokenization (no word boundaries)
  → Emoji: Treated as searchable tokens or stripped depending on use case

EDGE CASE 6: Tenant's index is being reindexed
  → Old index serves queries until new index is ready
  → Alias swap is atomic — no query sees a partial new index
  → During reindex, writes go to BOTH old and new index (dual-write)

EDGE CASE 7: Query timeout
  → Return best-effort results collected from shards that responded
  → Include metadata: "partial_results: true, shards_timed_out: 3"
  → Better to return 80% of results than an error
```

## What Is Intentionally OUT of Scope

```
OUT OF SCOPE:
1. Vector / semantic / embedding-based search (ANN)
   → This is a separate system (vector database) with different data structures
   → Can be combined with lexical search in a hybrid retrieval pipeline
   → Excluded to keep focus on inverted-index-based lexical search

2. Real-time streaming analytics on search logs
   → Search provides query logs; analytics is a separate pipeline

3. Crawler / content acquisition
   → The search system indexes documents it RECEIVES
   → How documents are acquired (crawled, published, imported) is upstream

4. ML model training for ranking
   → The search system SERVES trained models
   → Training infrastructure is a separate ML platform concern

5. Natural language understanding / conversational search
   → Query understanding (spelling, synonyms) is in scope
   → Full NLU / question answering is a different system

WHY SCOPE IS LIMITED:
Each excluded item is a Staff-level system in its own right.
Combining them into one design would sacrifice depth for breadth.
A Staff Engineer scopes aggressively and builds well.
```

---

# Part 3: Non-Functional Requirements (Reality-Based)

## Latency Expectations

```
SEARCH QUERY LATENCY:
  P50:  < 50ms    (most queries are fast — simple terms, small result sets)
  P95:  < 150ms   (complex queries, large intersections, heavy faceting)
  P99:  < 300ms   (worst case: wildcard queries, high fan-out, slow shards)
  
  WHY THESE NUMBERS:
  → Users perceive delays above 200ms as "slow"
  → Above 500ms, users abandon the search and try navigation
  → Above 1 second, users leave the product entirely
  → For autocomplete: P99 < 30ms (must respond before next keystroke)

INDEXING LATENCY (document mutation to searchable):
  Target:  < 5 seconds for 95% of documents
  Maximum: < 30 seconds for 99.9% of documents
  
  WHY:
  → Users expect to find content they just published
  → Marketplace listings must be discoverable quickly
  → Stale inventory (sold items still appearing) erodes trust

STAFF INSIGHT ON LATENCY:
  Search latency is a DISTRIBUTION, not a single number.
  A system with P50=20ms but P99=2000ms is WORSE than one with P50=50ms
  and P99=200ms. The long tail kills user experience because:
  → Users don't average their experience — they remember the worst ones
  → P99 at 100K QPS = 1,000 slow requests per second = constant user pain
  → Tail latency often indicates resource contention or garbage collection,
    which will get worse under load
```

## Availability Expectations

```
TARGET: 99.95% availability (< 4.4 hours downtime/year)

WHY NOT 99.99%:
  → Search is derived data — temporary unavailability means users
    can't search, but source data is intact
  → Recovery path: Rebuild index from source of truth
  → Products should have fallback (browse, category navigation)
    for when search is unavailable
  → 99.99% for a globally distributed search system requires
    active-active multi-region with automated failover — achievable
    but expensive; justified only if search IS the product

AVAILABILITY DEFINITION:
  Available = query returns results within timeout budget
  Degraded = query returns partial results (some shards failed)
  Unavailable = query returns error or zero results when results should exist

STAFF INSIGHT:
  Partial availability is more realistic and more useful than binary up/down.
  A system that returns results from 11 of 12 shards is 91.7% available
  from a data coverage perspective but 100% available from a user perspective
  (they still get results). Design for graceful degradation, not perfection.
```

## Consistency Needs

```
CONSISTENCY MODEL: EVENTUAL CONSISTENCY (by design)

  The search index is a DERIVED VIEW of the source of truth.
  It is ALWAYS eventually consistent with the source.

  IMPLICATIONS:
  → A document indexed 1 second ago MIGHT not be searchable yet
  → A document deleted 1 second ago MIGHT still appear in results
  → Two queries issued simultaneously MIGHT return different results
    (different replicas, different refresh states)

  WHY EVENTUAL CONSISTENCY IS ACCEPTABLE:
  → Users don't notice sub-second staleness for most use cases
  → Strong consistency would require distributed transactions between
    source database and search index → massive latency penalty
  → The source of truth (database) IS strongly consistent
  → If a user finds a stale result and clicks it, the application
    checks the source of truth and handles the mismatch

  WHERE STRONGER GUARANTEES ARE NEEDED:
  → Read-your-own-writes: After indexing document X, the indexer's
    subsequent search should find X. Solved by version-aware routing
    or synchronous refresh for the submitter's session.
  → Deletion: Deleted content MUST disappear within bounded time
    (regulatory, legal). Solved by fast deletion propagation and
    freshness SLO monitoring.

  STAFF INSIGHT:
  The real consistency challenge is not between queries and mutations.
  It's between the search index and the source of truth. If the source
  changes and the index doesn't update, you have silent data divergence.
  This is why indexing pipeline health monitoring is more important than
  query serving monitoring.
```

## Durability

```
DURABILITY: THE INDEX IS REBUILDABLE, NOT PRECIOUS

  The search index is derived from the source of truth.
  Therefore, index durability requirements are LOWER than database durability.

  WHAT MUST BE DURABLE:
  → Source of truth (databases) — not our responsibility
  → Transaction log (write-ahead log for recent mutations) — replicated, durable
  → Index configuration and schema — version-controlled, stored externally

  WHAT IS EPHEMERAL:
  → Index segments — can be rebuilt from source + transaction log
  → In-memory buffers — can be recovered from transaction log replay
  → Caches (query cache, filter cache) — warm up automatically

  DURABILITY STRATEGY:
  → Transaction log: Replicated across 3 nodes, fsync on commit
  → Index segments: Replicated across 2-3 replicas per shard
  → Full index: Periodic snapshots to object storage (disaster recovery)
  → If all replicas of a shard are lost: Rebuild from source of truth

  STAFF INSIGHT:
  Engineers who come from database backgrounds over-invest in index
  durability. A search index that takes 4 hours to rebuild from source
  is FINE — the availability impact is handled by replicas and
  cross-region failover, not by making individual shards indestructible.
```

## Correctness vs User Experience Trade-offs

```
TRADE-OFF 1: Approximate hit counts vs exact counts
  EXACT: Count every matching document across all shards
  → Cost: Must visit every posting list entry — expensive for broad queries
  APPROXIMATE: Count up to 10,000, then estimate
  → Cost: Bounded computation, fast response
  → User impact: "About 12,800 results" vs "12,847 results" — nobody notices
  CHOICE: Approximate by default, exact on request

TRADE-OFF 2: Result consistency across pages vs freshness
  PROBLEM: User is on page 3, index refreshes, results shift
  → Results on page 4 might duplicate or skip documents
  OPTION A: Point-in-time snapshot (scroll context) — consistent but stale
  OPTION B: Live results — fresh but may have duplicates across pages
  CHOICE: Use search_after with sort tiebreaker for consistency without state

TRADE-OFF 3: Partial results vs timeout error
  PROBLEM: 2 of 12 shards are slow
  OPTION A: Wait for all shards → risk timeout → return error
  OPTION B: Return results from 10 fast shards → results may be incomplete
  CHOICE: Return partial results with metadata indicating incompleteness
  → Users get 83% of results immediately vs 0% after a timeout

TRADE-OFF 4: Relevance accuracy vs latency
  PROBLEM: ML re-ranking on 10,000 candidates takes 50ms
  OPTION A: Re-rank all candidates → better relevance, higher latency
  OPTION B: Re-rank top 100 → good enough relevance, lower latency
  CHOICE: Two-phase ranking with configurable candidate set size per tenant
```

## Security Implications

```
DATA ISOLATION:
  → Multi-tenant search must enforce strict tenant isolation
  → Tenant A must NEVER see Tenant B's documents in results
  → Tenant ID is a mandatory filter on EVERY query (enforced at platform level)
  → Indexing pipeline validates tenant ownership before accepting documents

ACCESS CONTROL:
  → Query API authenticates callers and maps to tenant
  → Admin API (schema changes, reindex) requires elevated permissions
  → Document-level ACLs: Some documents visible only to specific users
    → Implemented as security filters applied at query time
    → NOT cached globally (cache would leak across users)

SEARCH AS AN INFORMATION LEAK:
  → Autocomplete can reveal existence of documents ("did you mean: secret project X")
  → Facet counts can reveal data distribution ("0 results in category: classified")
  → Query logs contain sensitive user intent
  → Staff insight: Search is a powerful information extraction tool.
    Every search feature is also a potential data leak vector.
```

## SLO/SLI Framework

```
SLOs ARE NOT JUST NUMBERS — THEY ARE CONTRACTS WITH TENANTS.
A Staff Engineer defines SLOs, measures SLIs, and manages error budgets.

SLI (Service Level Indicator) — what we MEASURE:

  SLI 1: Query Latency
    Measurement: P99 of search query latency, measured at the gateway
    (includes all internal processing, NOT including client-side network)
    Granularity: Per tenant, per 5-minute window

  SLI 2: Query Availability
    Measurement: % of queries that return a non-error response within timeout
    Partial results count as AVAILABLE (not an error)
    Error = 5xx or timeout with zero results returned

  SLI 3: Indexing Freshness
    Measurement: P95 time from document mutation to searchability
    Measured by: Canary documents indexed every 30 seconds with known content,
    then searched. Freshness = time between index and first successful search.

  SLI 4: Index Completeness
    Measurement: % of source-of-truth documents that exist in the index
    Measured by: Periodic sampling — pick 1000 random source documents,
    verify they exist in the index via get-by-ID.

SLO (Service Level Objective) — what we PROMISE:

  SLO 1: Query P99 latency < 300ms (per tenant, per 5-min window)
  SLO 2: Query availability > 99.95% (per month)
  SLO 3: Indexing freshness P95 < 5 seconds (per tenant)
  SLO 4: Index completeness > 99.99% (per daily check)

ERROR BUDGET — how much failure is ACCEPTABLE:

  SLO 2 at 99.95% = 21.6 minutes of downtime per month
  → If error budget is not exhausted: Ship features, experiment, take risks
  → If error budget is 50% consumed: Slow down risky changes
  → If error budget is exhausted: Freeze all non-reliability work

  STAFF INSIGHT:
  Error budgets are the mechanism that balances velocity and reliability.
  Without error budgets, platform teams either move too fast (break things)
  or too slow (never ship). The SLO framework makes this explicit:
  "We have 15 minutes of budget left this month — that reindex can wait."

PER-TENANT SLO TIERS:

  TIER 1 (Premium):
    → P99 < 200ms, 99.99% availability, freshness < 2 seconds
    → Dedicated shard allocation, 3 replicas, dedicated coordinator pool
    → Cost: 3× standard pricing

  TIER 2 (Standard):
    → P99 < 300ms, 99.95% availability, freshness < 5 seconds
    → Shared infrastructure with quotas, 2 replicas
    → Cost: Standard pricing

  TIER 3 (Best-effort):
    → P99 < 500ms, 99.9% availability, freshness < 30 seconds
    → Shared infrastructure, 1 replica, first to be shed under load
    → Cost: 0.5× standard pricing

  WHY TIERS:
  → Not all tenants need the same guarantees
  → Tiered SLOs enable cost-efficient resource allocation
  → Shedding Tier 3 traffic protects Tier 1 during incidents
  → Tenants self-select based on business criticality
```

---

# Part 4: Scale & Load Modeling (Concrete Numbers)

## Users and Traffic

```
SCALE ASSUMPTIONS (large platform):

  Total documents in corpus:     2 billion
  Average document size:         2 KB (indexed fields)
  Total index size:              ~4 TB (inverted index + stored fields)
  Daily active users:            50 million
  Queries per day:               500 million
  Average queries per user:      10 / day

QPS (QUERIES PER SECOND):
  Average: 500M / 86,400 = ~5,800 QPS
  Peak (2× average):            ~12,000 QPS
  Spike (10× during events):    ~60,000 QPS
  
  AUTOCOMPLETE QPS (3× search QPS — multiple calls per search):
  Average: ~18,000 QPS
  Peak: ~36,000 QPS

DOCUMENT MUTATIONS PER SECOND:
  New documents / day:           5 million
  Updated documents / day:       20 million
  Deleted documents / day:       2 million
  Total mutations / day:         27 million
  Mutations per second (avg):    ~310 mutations/sec
  Mutations per second (peak):   ~3,000 mutations/sec

READ:WRITE RATIO:
  Queries : Mutations = 5,800 : 310 ≈ 19:1
  Including autocomplete: (5,800 + 18,000) : 310 ≈ 77:1
  
  This is heavily read-dominated, but the write path is NOT negligible.
  310 mutations/sec × 2KB = 620 KB/sec of raw data to index,
  but each mutation triggers: text analysis, inverted index update,
  segment buffer flush, replication to N replicas, and eventually
  segment merge. The effective I/O amplification is 10-50×.
```

## Capacity Planning

```
INDEX SIZING:

  2 billion documents × 2 KB avg = 4 TB raw stored fields
  Inverted index overhead: ~1.5× raw data = 6 TB inverted index
  Total per replica: ~10 TB
  Replicas: 3 (1 primary + 2 replicas)
  Total storage: 30 TB

SHARD SIZING:
  Target shard size: 30-50 GB (sweet spot for search performance)
  Number of shards: 10 TB / 40 GB = 250 shards
  With 3 replicas: 750 shard instances

NODE SIZING:
  Each node: 64 GB RAM, 1 TB NVMe SSD, 16 cores
  Shards per node: 5-10 (depending on query load)
  Working set in memory: Inverted index + filter caches
  → Need ~60% of index in OS page cache for fast queries
  → 40 GB index per node × 60% = 24 GB in page cache

  Total nodes needed:
  → Storage: 750 shard instances / 7 shards per node = ~107 nodes
  → CPU: 12,000 peak QPS / 200 QPS per node = ~60 nodes  
  → Memory: Dominated by storage calculation
  → TOTAL: ~110 data nodes (storage is the binding constraint)

QUERY COORDINATOR NODES:
  → Stateless, CPU-bound (scatter-gather, merge, re-rank)
  → 12,000 peak QPS / 2,000 QPS per coordinator = 6 coordinators
  → Over-provision to 10 for headroom and failure tolerance
```

## Growth Assumptions

```
GROWTH MODEL:
  Year 1: 2B documents, 12K peak QPS
  Year 2: 5B documents, 25K peak QPS (new product teams onboard)
  Year 3: 10B documents, 50K peak QPS (international expansion)

WHAT THIS MEANS FOR ARCHITECTURE:
  → Shard count must be adjustable without full reindex
    (use routing-based sharding with virtual shard IDs)
  → Storage tier must support hot/warm/cold
    (old, rarely-accessed documents move to cheaper storage)
  → Query routing must support per-tenant isolation
    (new tenants shouldn't degrade existing tenants)
  → Cross-region replication becomes essential at Year 2
    (latency for international users, regional failure tolerance)
```

## Burst Behavior

```
BURST SCENARIOS:

SCENARIO 1: Flash sale / product launch
  → 10× normal QPS for specific product categories
  → Mostly READ burst — queries for specific terms spike
  → Impact: Specific shards may hot-spot if documents cluster by category
  → Mitigation: Ensure sharding is content-agnostic (hash-based),
    query result caching for popular queries

SCENARIO 2: Bulk data import (new tenant onboarding)
  → 100× normal write rate for hours
  → Impact: Segment merge storm, increased I/O, query latency degradation
  → Mitigation: Dedicated ingestion pipeline with rate limiting,
    separate bulk indexing from real-time indexing, throttle merges

SCENARIO 3: "Thundering herd" — cache invalidation
  → Query cache expires → all replicas simultaneously hit index
  → Impact: CPU spike across all nodes
  → Mitigation: Jittered cache expiry, request coalescing
    (only one query fetches, others wait for cached result)

SCENARIO 4: Reindex in progress
  → Full reindex of 2B documents while serving live queries
  → Impact: Doubles write load, increases I/O contention
  → Mitigation: Reindex at reduced throughput during off-peak,
    reindex to a new index (not in-place), alias swap when done

WHAT BREAKS FIRST AT SCALE:
  1. Segment merge I/O competes with query serving → P99 latency spikes
  2. Per-shard posting list intersection on popular terms → CPU bottleneck
  3. Scatter-gather to 250 shards → tail latency from slowest shard dominates
  4. Memory pressure: Inverted index too large for page cache → disk reads
  5. Network bandwidth: Large fan-out × large responses saturate NIC
```

## Which Assumptions Are Most Dangerous

```
DANGEROUS ASSUMPTION 1: "Queries are uniformly distributed across shards"
  REALITY: Zipf distribution — a few terms appear in many documents.
  Query for "shoes" hits every shard heavily; query for "xyz123" hits few.
  HOT TERMS create hot shards regardless of document distribution.

DANGEROUS ASSUMPTION 2: "Indexing lag doesn't matter because we refresh every second"
  REALITY: Under load, refresh can be delayed. Segment merges compete with refresh.
  A 1-second refresh interval can become 30 seconds during a merge storm.
  You MUST monitor actual indexing lag, not configured refresh interval.

DANGEROUS ASSUMPTION 3: "Adding replicas linearly improves query throughput"
  REALITY: Replicas help until you're bottlenecked on coordinator CPU (merge step),
  network bandwidth, or per-shard hot-spotting. Replicas also increase
  indexing cost (every mutation replicated N times).

DANGEROUS ASSUMPTION 4: "The query parser handles all queries well"
  REALITY: Adversarial queries exist: "* OR * OR * OR * ..." can create
  enormous posting list unions. "field:*" on a high-cardinality field
  creates O(vocabulary_size) work. Query validation and cost estimation
  BEFORE execution is essential.
```

---

# Part 5: High-Level Architecture (First Working Design)

## Core Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SEARCH SYSTEM ARCHITECTURE                               │
│                                                                             │
│   ┌─────────────┐                                                           │
│   │   Clients   │  (Product services, mobile apps, web frontend)            │
│   └──────┬──────┘                                                           │
│          │                                                                  │
│          ▼                                                                  │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │                    QUERY GATEWAY / LOAD BALANCER                   │    │
│   │  (Authentication, tenant identification, rate limiting, routing)   │    │
│   └─────────┬──────────────────────────────────┬───────────────────────┘    │
│             │                                  │                            │
│      ┌──────▼──────┐                    ┌──────▼──────┐                     │
│      │  QUERY PATH │                    │ WRITE PATH  │                     │
│      └──────┬──────┘                    └──────┬──────┘                     │
│             │                                  │                            │
│      ┌──────▼─────────────-─┐           ┌──────▼──────────────┐             │
│      │ QUERY COORDINATOR    │           │ INDEXING PIPELINE   │             │
│      │ (Parse, plan, scatter│           │ (Validate, analyze, │             │
│      │  gather, merge, rank)│           │  route to shards)   │             │
│      └──────┬──────────────-┘           └──────┬──────────────┘             │
│             │                                  │                            │
│             │    ┌────────────────────────────┐│                            │
│             │    │     SHARD LAYER            ││                            │
│             │    │                            ││                            │
│             ▼    ▼                            ▼│                            │
│      ┌────────────────────────────────────────────┐                         │
│      │  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐    │                         │
│      │  │Shard │  │Shard │  │Shard │  │Shard │    │                         │
│      │  │  0   │  │  1   │  │  2   │  │ ...  │    │                         │
│      │  │      │  │      │  │      │  │      │    │                         │
│      │  │ P R R│  │ P R R│  │ P R R│  │ P R R│    │  P=Primary R=Replica    │
│      │  └──────┘  └──────┘  └──────┘  └──────┘    │                         │
│      └────────────────────────────────────────────┘                         │
│                                                                             │
│      ┌────────────────────────────────────────────┐                         │
│      │          CLUSTER MANAGEMENT                │                         │
│      │  (Shard allocation, rebalancing, health)   │                         │
│      └────────────────────────────────────────────┘                         │
│                                                                             │
│      ┌──────────────────┐  ┌──────────────────┐                             │
│      │  CONFIG STORE    │  │  METADATA STORE  │                             │
│      │ (Schema, aliases,│  │  (Cluster state, │                             │
│      │   tenant config) │  │   shard map)     │                             │
│      └──────────────────┘  └──────────────────┘                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

```
QUERY GATEWAY / LOAD BALANCER:
  → Authenticate client, identify tenant
  → Rate limit per-tenant
  → Route to appropriate query coordinator
  → TLS termination
  → NOT involved in query execution logic

QUERY COORDINATOR (stateless):
  → Receive parsed query from gateway
  → Query planning: Determine which shards to query
  → Scatter: Fan out query to shard replicas in parallel
  → Gather: Collect per-shard results, merge into global ranking
  → Post-processing: Apply business rules, compute facets, format response
  → Timeout management: Return partial results if some shards are slow

INDEXING PIPELINE (stateless processing, stateful queue):
  → Receive document mutations (index, update, delete)
  → Validate schema compliance
  → Text analysis: Tokenize, normalize, stem, apply analyzers
  → Route to correct shard (hash of document ID)
  → Write to shard's transaction log
  → Manage backpressure: Queue depth monitoring, producer throttling

SHARD (stateful):
  → Stores a partition of the inverted index + stored fields
  → Handles local query execution: posting list lookup, scoring, top-K
  → Handles local indexing: Buffer mutations, flush to segments, merge segments
  → Replication: Primary accepts writes, replicates to replica shards
  → Each shard has: inverted index, stored fields, doc values (for sorting/facets),
    deletion bitmap, transaction log

CLUSTER MANAGEMENT (control plane):
  → Shard allocation: Assign shards to nodes, balance load
  → Node health monitoring: Detect failed nodes, reallocate shards
  → Shard rebalancing: Move shards when nodes are added/removed
  → Split/merge shards: Adjust shard count as data grows
  → Consensus-based: Uses leader election for cluster state decisions

CONFIG STORE:
  → Index schemas, aliases, analyzer definitions
  → Per-tenant configuration (quotas, relevance settings)
  → Version-controlled, auditable

METADATA STORE:
  → Cluster topology: Which shards are on which nodes
  → Shard state: Primary, replica, initializing, relocating
  → Stored in consensus system (ZooKeeper, etcd equivalent)
```

## Stateless vs Stateful Decisions

```
STATELESS:
  → Query coordinators: Any coordinator can handle any query
    → Enables horizontal scaling, trivial load balancing, instant failover
  → Indexing pipeline workers: Any worker can process any mutation
    → Enables elastic scaling during bulk imports
  → Query gateway: Routes based on tenant, not session
    → No sticky sessions needed

STATEFUL:
  → Shard nodes: Hold inverted index data on disk + in-memory buffers
    → State IS the purpose — can't be stateless
    → Replicated for durability and read scaling
  → Cluster manager: Holds authoritative cluster state
    → Leader-elected, consensus-based
  → Transaction logs: Per-shard, replicated
    → Must survive node failure for recovery

STAFF INSIGHT:
  The most important architectural decision is keeping the query path
  as stateless as possible. Stateless coordinators mean any coordinator
  can serve any query, which enables:
  → Simple horizontal scaling
  → Instant failover (no session draining)
  → Independent deployment (update coordinators without draining queries)
  → Per-query load balancing (not per-session)

  The ONLY stateful components should be the shard nodes (where data
  lives) and the cluster manager (where metadata lives). Everything
  else is stateless.
```

## Data Flow: Search Query (Detailed)

```
CLIENT → QUERY GATEWAY → COORDINATOR → SHARDS → COORDINATOR → CLIENT

STEP-BY-STEP:

  1. Client sends: POST /search
     {"query": "red running shoes", "filters": {"price_max": 50}, "size": 20}
     Headers: Authorization: Bearer <token>, X-Tenant: ecommerce

  2. Gateway:
     → Verify token → Extract tenant_id = "ecommerce"
     → Check rate limit for tenant: OK (450/500 requests this second)
     → Forward to query coordinator (round-robin selection)

  3. Coordinator (PLAN):
     → Parse query: ["red", "running", "shoes"] with AND semantics
     → Apply synonyms: "shoes" → ["shoes", "sneakers"]
     → Spell check: No corrections needed
     → Determine shard set: All 250 shards (no partition pruning possible)
     → Set per-shard timeout: 100ms (leaves 100ms for merge + post-process)

  4. Coordinator (SCATTER):
     → Fan out query to one replica of each shard (250 parallel requests)
     → Select replica using adaptive routing (prefer replicas with lower latency)

  5. Each Shard (LOCAL EXECUTION):
     → Look up posting lists:
       "red" → [doc_1, doc_42, doc_99, ...] (5K docs in this shard)
       "running" → [doc_42, doc_55, ...] (3K docs in this shard)
       "shoes" → [doc_42, doc_100, ...] (4K docs in this shard)
       "sneakers" → [doc_200, ...] (1K docs in this shard)
     → Intersect: "red" AND "running" AND ("shoes" OR "sneakers")
       → [doc_42, ...] (200 docs match in this shard)
     → Apply filter: price < 50
       → 150 docs remain
     → Score using BM25 + boost factors
     → Return top-20 with scores to coordinator
     → Time: 15-40ms

  6. Coordinator (GATHER):
     → Receive 250 top-20 lists (5000 candidates total)
     → Merge into global top-20 using priority queue
     → Apply ML re-ranking on top-100 candidates (optional)
     → Compute global facet counts by merging per-shard facets
     → Time: 5-10ms

  7. Coordinator (RESPOND):
     → Format response with highlights, facets, metadata
     → Return to client
     → Total latency: 40-80ms (P50)
```

## Data Flow: Document Indexing (Detailed)

```
SOURCE → INDEXING PIPELINE → SHARD PRIMARY → REPLICAS

STEP-BY-STEP:

  1. Source system sends: POST /index
     {"id": "prod_42", "title": "Red Trail Running Shoes", ...}
     Headers: X-Tenant: ecommerce

  2. Indexing Pipeline:
     → Validate schema: All required fields present, types correct
     → Determine target shard: hash(doc_id) % num_shards = shard_17
     → Write to transaction log (durable, replicated)
     → Acknowledge to client: {status: "accepted"}

  3. Text Analysis (async, in pipeline or on shard):
     → Tokenize: "Red Trail Running Shoes" → ["red", "trail", "running", "shoes"]
     → Lowercase: Already done
     → Stem: "running" → "run", "shoes" → "shoe" (language-dependent)
     → Remove stop words: None in this case
     → Generate: Inverted index entries for each token

  4. Shard Primary (shard_17):
     → Add analyzed document to in-memory buffer (indexing buffer)
     → When buffer is full OR refresh interval (1s) elapses:
       → Flush buffer to a new immutable segment on disk
       → New segment is immediately searchable
     → Replicate transaction log entry to replica shards

  5. Replica Shards:
     → Receive transaction log entry
     → Apply same analysis and buffering
     → Segment becomes searchable after local refresh

  6. Background: Segment Merge
     → Over time, many small segments accumulate
     → Merge process combines small segments into larger ones
     → Applies deletion bitmaps (physically removes deleted docs)
     → Reclaims space, improves query performance (fewer segments to search)
```

---

# Part 6: Deep Component Design (NO SKIPPING)

## Component 1: Inverted Index

### Internal Data Structures

```
THE INVERTED INDEX IS THE CORE DATA STRUCTURE OF SEARCH.

STRUCTURE:
  Term Dictionary:
    Maps each unique term to its posting list location.
    Stored as a sorted term list with binary search, or as an FST
    (Finite State Transducer) for memory-efficient prefix lookups.

    Example:
    "apple"    → offset 0x1000, doc_freq: 50000
    "banana"   → offset 0x2000, doc_freq: 12000
    "cherry"   → offset 0x3000, doc_freq: 8000
    ...
    Total terms: ~10 million unique terms per shard

  Posting List (per term):
    Sorted list of document IDs that contain this term.
    Each entry includes:
    → Document ID (delta-encoded for compression)
    → Term frequency (how many times this term appears in this document)
    → Position offsets (for phrase queries and highlighting)

    Example for "running":
    [doc_1 (tf:3, positions:[5,12,45]),
     doc_42 (tf:1, positions:[8]),
     doc_99 (tf:7, positions:[1,3,15,22,30,41,55]),
     ...]

  COMPRESSION:
    → Delta encoding: Store differences between consecutive doc IDs
      [1, 42, 99] → [1, 41, 57] (smaller numbers = fewer bits)
    → Variable-byte encoding: Use fewer bytes for small numbers
    → Block compression: Compress blocks of 128 doc IDs together
    → Result: ~2 bytes per posting on average (vs 4-8 uncompressed)

  Doc Values (Column Store):
    Per-field column-oriented storage for sorting, faceting, aggregation.
    → price: [45.99, 29.99, 89.99, ...]  (one value per document)
    → category: [1, 3, 1, 2, ...]         (encoded as ordinals)
    → Used when we need field values for ALL matching documents
      (not per-term, but per-document)

  Stored Fields:
    Original document content, stored per document.
    → Retrieved only for the final top-K results (not during scoring)
    → Compressed per-document for space efficiency

  Deletion Bitmap:
    Bit vector with one bit per document.
    → Bit set = document is deleted
    → Checked during every query to exclude deleted documents
    → Physically removed during segment merge
```

### Segment Architecture

```
THE INDEX IS NOT ONE BIG FILE — IT'S A COLLECTION OF SEGMENTS.

SEGMENT:
  An immutable, self-contained mini-index.
  Contains: term dictionary, posting lists, doc values, stored fields, deletion bitmap
  Once written, a segment is NEVER modified.

  WHY IMMUTABLE SEGMENTS:
  → No locking needed for concurrent reads (immutable = thread-safe)
  → Caching is trivial (content never changes)
  → Crash recovery is simple (segments are either complete or not)
  → Concurrent reads and writes without interference

SEGMENT LIFECYCLE:
  1. IN-MEMORY BUFFER
     New documents accumulate in a RAM buffer.
     Not yet searchable.

  2. FLUSH → NEW SEGMENT
     Buffer contents written to disk as a new segment.
     Triggered by: buffer full, refresh interval, explicit flush.
     Now searchable.

  3. MERGE
     Background process combines multiple small segments into one larger segment.
     Applies deletions (physically removes deleted documents).
     Merge strategies:
     → Tiered: Segments of similar size merge together
     → Log-structured: Always merge the smallest segments first
     → Force merge: Manually trigger merge to optimize (reduce segment count)

  WHY MERGE MATTERS:
  → Too many segments = slower queries (must search each segment)
  → Too few merges = wasted space (deleted documents not reclaimed)
  → Too aggressive merging = I/O contention with queries
  → The merge policy is one of the most important tuning knobs

SEGMENT EXAMPLE:
  After 1 hour of indexing at 300 docs/sec:
  → ~300 × 3600 = 1.08M documents
  → ~3,600 small segments created (one per second refresh)
  → Merge reduces to: ~10-20 segments of varying sizes
  → Query searches all 10-20 segments and merges results
```

### Failure Behavior

```
FAILURE: Segment corruption
  → Detected by: Checksum validation on segment open
  → Impact: Shard cannot serve queries for that segment
  → Recovery: Re-replicate segment from replica, or rebuild from transaction log
  → User impact: If replicas are healthy, no impact (failover to replica)

FAILURE: In-memory buffer lost (node crash before flush)
  → Impact: Recent mutations (since last flush) are lost from this node
  → Recovery: Replay transaction log from last flush checkpoint
  → User impact: Brief period where very recent documents are not searchable
    (transaction log replayed within seconds)

FAILURE: Merge fails mid-way
  → Impact: None — source segments are not deleted until merge completes
  → Old segments continue serving queries
  → Merge is retried automatically
  → This is WHY segments are immutable: merge is always safe to retry

FAILURE: Disk full
  → Impact: Cannot create new segments, cannot merge
  → Indexing backs up (buffer stays in memory, eventually rejected)
  → Queries continue from existing segments (read path unaffected short-term)
  → Alert: Disk usage > 85% triggers immediate investigation
```

## Component 2: Query Coordinator

### Internal Design

```
THE COORDINATOR IS THE BRAIN OF THE QUERY PATH.
It is STATELESS — holds no data, only logic.

RESPONSIBILITIES:
  1. Query parsing and understanding
  2. Query planning (which shards, which replicas)
  3. Scatter (fan-out to shards)
  4. Gather (merge results)
  5. Post-processing (re-ranking, facet aggregation)
  6. Timeout and partial failure management

QUERY PARSING PIPELINE:
  Raw query → Tokenizer → Spell Corrector → Synonym Expander
  → Query Builder → Optimized Query Plan

  TOKENIZER:
    "red running shoes under $50"
    → ["red", "running", "shoes", "under", "$50"]
    Language-aware: CJK uses character n-grams, Thai uses dictionary segmentation

  SPELL CORRECTOR:
    "runnning" → "running" (edit distance 1)
    Uses: Pre-built dictionary + corpus term frequencies
    Only corrects if corrected term has significantly higher document frequency
    Does NOT correct if original term has matches (assume user knows what they want)

  SYNONYM EXPANDER:
    "shoes" → "shoes OR sneakers OR footwear"
    Per-tenant synonym dictionaries (configurable)
    Expansion is ADDITIVE (never removes original term)

  QUERY BUILDER:
    Converts parsed tokens + filters into an executable query tree:
    AND(
      term("red"),
      term("running"),
      OR(term("shoes"), term("sneakers"), term("footwear")),
      range("price", 0, 50),
      term("in_stock", true)
    )

SHARD SELECTION:
  Default: Query all shards (hash-partitioned, any shard may have relevant docs)
  Optimization: Routing key — if query includes tenant or partition key,
  route to subset of shards
  
  Example: Tenant "ecommerce" uses shards 0-49 (not all 250)
  → Query fans out to 50 shards instead of 250
  → 5× reduction in fan-out → better tail latency

SCATTER-GATHER:
  FUNCTION scatter_gather(query, shards, timeout):
    results = []
    pending = shards.copy()
    deadline = now() + timeout
    
    // Send to all shards in parallel
    FOR shard IN shards:
      replica = select_replica(shard)  // Adaptive: prefer fast replicas
      send_async(query, replica)
    
    // Collect results with timeout
    WHILE pending.not_empty() AND now() < deadline:
      response = wait_for_next_response()
      results.append(response)
      pending.remove(response.shard)
    
    // Handle timeouts
    IF pending.not_empty():
      log_warning("Shards timed out: " + pending)
      mark_response_as_partial()
    
    RETURN merge(results)

ADAPTIVE REPLICA SELECTION:
  Track per-replica latency using exponentially weighted moving average.
  Prefer replicas with lower recent latency.
  Avoid replicas that are currently merging (higher I/O → higher latency).
  This is critical for tail latency: one slow replica can dominate P99.

RESULT MERGING:
  Each shard returns top-K results sorted by score.
  Coordinator maintains a priority queue of size K.
  Merge N sorted lists into one in O(K × log(N)) time.
  For K=20 and N=250: 20 × 8 = 160 comparisons (trivial).
```

### Why Simpler Alternatives Fail

```
ALTERNATIVE: Single coordinator, single thread
  PROBLEM: At 12K QPS, coordinator must handle 12K scatter-gather ops/sec.
  Each scatter-gather involves 250 parallel shard calls.
  Single-threaded: 1 query at a time × 50ms each = 20 QPS max.
  NEED: Event-driven, async I/O coordinator handling 1000s of concurrent queries.

ALTERNATIVE: Client fans out to shards directly (no coordinator)
  PROBLEM: Every client must know shard topology, handle partial failures,
  merge results, apply re-ranking. This pushes platform complexity to every consumer.
  → 10 product teams × complex client = 10 buggy clients.
  → Shard topology changes require coordinated client updates.
  → The coordinator is the abstraction that hides cluster complexity.

ALTERNATIVE: Random shard selection (query one shard only)
  PROBLEM: With hash-partitioned documents, relevant results may be on any shard.
  Querying one shard returns ~1/250th of the results — incomplete and poorly ranked.
  Only works if data is partitioned by query key (which is usually impossible
  because queries are free-form text, not structured keys).
```

## Component 3: Indexing Pipeline

### Internal Design

```
THE INDEXING PIPELINE TRANSFORMS RAW DOCUMENTS INTO INDEX UPDATES.

ARCHITECTURE:
  Source → Message Queue → Pipeline Workers → Shard Primaries

  WHY A QUEUE:
  → Decouples producers (source systems) from consumers (shards)
  → Absorbs burst writes (flash sale inventory updates)
  → Provides replay capability (re-process failed mutations)
  → Enables backpressure (slow shards don't block producers)

PIPELINE WORKER RESPONSIBILITIES:
  1. Deserialize document from queue
  2. Validate against tenant's schema
  3. Text analysis: tokenization, stemming, synonym injection (index-time)
  4. Extract structured fields for doc values
  5. Determine target shard: hash(tenant_id + doc_id) % num_shards
  6. Forward analyzed document to shard primary

TEXT ANALYSIS PIPELINE:
  Raw text: "The Quick Brown Fox Jumped Over the Lazy Dogs!!"
  
  Step 1 — Character filtering:
    Strip HTML, normalize Unicode, handle diacritics
    → "The Quick Brown Fox Jumped Over the Lazy Dogs"
  
  Step 2 — Tokenization:
    Split on whitespace and punctuation
    → ["The", "Quick", "Brown", "Fox", "Jumped", "Over", "the", "Lazy", "Dogs"]
  
  Step 3 — Lowercasing:
    → ["the", "quick", "brown", "fox", "jumped", "over", "the", "lazy", "dogs"]
  
  Step 4 — Stop word removal:
    Remove: "the", "over"
    → ["quick", "brown", "fox", "jumped", "lazy", "dogs"]
  
  Step 5 — Stemming:
    "jumped" → "jump", "dogs" → "dog"
    → ["quick", "brown", "fox", "jump", "lazy", "dog"]
  
  Step 6 — Synonym injection (index-time, optional):
    "fox" → also index "vixen" (if configured)
    → ["quick", "brown", "fox", "vixen", "jump", "lazy", "dog"]
  
  Output: Tokens to be added to the inverted index with positions.

DUAL-WRITE FOR SCHEMA MIGRATION:
  During schema changes, pipeline writes to BOTH old and new index.
  → Old index continues serving queries
  → New index builds up with new schema
  → When new index is complete, swap alias
  → Stop writing to old index, delete after cooldown
```

### Backpressure Mechanisms

```
BACKPRESSURE LAYERS:

LAYER 1: Queue depth monitoring
  IF queue_depth > threshold:
    → Alert: Indexing is falling behind
    → Scale up pipeline workers
  IF queue_depth > critical_threshold:
    → Reject new mutations with backpressure signal (429)
    → Source systems retry with exponential backoff

LAYER 2: Per-tenant rate limiting
  Each tenant has an indexing throughput quota (e.g., 1000 docs/sec).
  Prevents one tenant's bulk import from starving others.
  Enforced at the pipeline level BEFORE analysis.

LAYER 3: Shard-level backpressure
  IF shard's indexing buffer is > 90% full:
    → Pipeline worker slows down writes to that shard
    → Does NOT block other shards
  IF shard is in a large merge:
    → Reduce indexing throughput to avoid I/O contention with merge
    → Resume normal throughput after merge completes

STAFF INSIGHT:
  The indexing pipeline is where most search system incidents originate.
  Unbounded writes → merge storms → I/O contention → query latency spike.
  The pipeline MUST be the enforcement point for write rate control.
```

## Component 4: Shard Manager / Cluster Management

### Internal Design

```
THE CLUSTER MANAGER IS THE CONTROL PLANE.
It does NOT handle data traffic — only metadata and orchestration.

RESPONSIBILITIES:
  1. Shard allocation: Decide which shards go on which nodes
  2. Rebalancing: Move shards when nodes are added/removed
  3. Failure detection: Detect node failures, trigger re-replication
  4. Primary election: When a primary shard fails, promote a replica
  5. Metadata management: Maintain authoritative shard → node mapping

SHARD ALLOCATION ALGORITHM:
  GOALS (in priority order):
  1. No two copies of the same shard on the same node (fault tolerance)
  2. No two copies of the same shard in the same failure domain (rack/AZ)
  3. Balance shard count across nodes (even load distribution)
  4. Balance disk usage across nodes (avoid hot spots)
  5. Minimize shard movements during rebalancing (stability)

  CONSTRAINTS:
  → Each shard has 1 primary + N replicas (typically N=2)
  → Primary and replicas MUST be on different nodes
  → Prefer different racks/AZs for replicas
  → Don't move shards during peak query hours if possible

PRIMARY ELECTION:
  When primary shard's node fails:
  1. Cluster manager detects failure (heartbeat timeout: 30 seconds)
  2. Selects most up-to-date replica as new primary
     (determined by transaction log position)
  3. Promotes replica to primary
  4. Updates cluster metadata
  5. Other replicas sync from new primary
  
  Total failover time: 30-60 seconds
  During failover: Reads served by remaining replicas, writes queued

NODE FAILURE HANDLING:
  Node fails → 
  1. All primaries on that node → promote replicas elsewhere
  2. All replicas on that node → cluster is still functional but under-replicated
  3. Schedule re-replication to restore replica count
  4. Re-replication throttled to avoid overwhelming surviving nodes
```

### State Management

```
CLUSTER STATE:
  Stored in consensus system (ZooKeeper, etcd equivalent).
  
  Content:
  → Index definitions (name, schema, settings)
  → Shard allocation table (shard → node mapping)
  → Node registry (alive/dead status, resource capacity)
  → Alias definitions (alias → index mapping)
  → Tenant configurations

  State updates:
  → Through cluster manager leader ONLY
  → Applied via compare-and-swap for consistency
  → Propagated to all nodes via watch/notification

  SIZE:
  → For 250 shards × 3 replicas on 110 nodes: ~10KB of state
  → Updates: ~1-10 per minute (rare unless failures or scaling events)
  → This is a SMALL, CRITICAL, LOW-FREQUENCY state store.
    Perfect use case for consensus-based systems.
```

## Component 5: Relevance Engine

### Multi-Phase Ranking

```
WHY MULTI-PHASE RANKING:

  Corpus: 2 billion documents
  Matching documents for query "running shoes": 50 million
  User wants: Top 20 results
  
  PROBLEM: Applying a complex ML model to 50M documents = 50 seconds
  SOLUTION: Progressive filtering — cheap filters first, expensive scoring last

PHASE 1: RETRIEVAL (inverted index)
  → Input: All 50M matching documents
  → Method: BM25 scoring on inverted index
  → Output: Top 1,000 candidates per shard
  → Cost: ~10ms per shard (parallel across shards)
  → This is the HARD FILTER — eliminate 99.998% of documents cheaply

PHASE 2: RANKING (feature-based scoring)
  → Input: Top 1,000 candidates (from coordinator merge)
  → Method: Lightweight ML model with features:
    - BM25 score (from Phase 1)
    - Document freshness (hours since last update)
    - Popularity (click-through rate, conversion rate)
    - Quality score (editorial rating, user reviews)
    - Personalization signals (user's category affinity)
  → Output: Top 100 re-ranked candidates
  → Cost: ~5ms (simple linear model or small gradient-boosted tree)

PHASE 3: BUSINESS RULES (post-processing)
  → Input: Top 100 candidates
  → Apply:
    - Pinned results (sponsored/promoted items at specific positions)
    - Diversity: No more than 3 results from same brand
    - Content policy: Filter blocked/flagged items
    - Freshness boost: Newly listed items get temporary boost
  → Output: Final top 20 results
  → Cost: ~1ms

STAFF INSIGHT:
  Phase 1 determines the CEILING of relevance. If a relevant document
  doesn't make it past Phase 1 (not in top 1,000 by BM25), no amount
  of ML re-ranking will save it. This is why inverted index quality
  (analyzers, synonyms, tokenization) matters more than ranking model
  sophistication for most search systems.
```

### BM25 Scoring (Detailed)

```
BM25 IS THE INDUSTRY STANDARD FOR LEXICAL RELEVANCE SCORING.

FORMULA:
  score(q, d) = Σ IDF(t) × (tf(t,d) × (k1 + 1)) / (tf(t,d) + k1 × (1 - b + b × |d|/avgdl))

  WHERE:
  → q = query, d = document, t = term
  → IDF(t) = log((N - df(t) + 0.5) / (df(t) + 0.5))
    (Inverse document frequency — rare terms are more informative)
  → tf(t,d) = term frequency in document d
  → k1 = 1.2 (term frequency saturation — diminishing returns for repeated terms)
  → b = 0.75 (length normalization — penalize long documents slightly)
  → |d| = document length, avgdl = average document length

INTUITION:
  → A term that appears in 10 of 1,000,000 documents is very discriminative (high IDF)
  → A term that appears in 500,000 of 1,000,000 documents is barely useful (low IDF)
  → Term frequency matters but saturates (5 mentions ≈ as good as 50)
  → Long documents are slightly penalized (more opportunities for random matches)

EXAMPLE:
  Query: "distributed systems"
  Document A: "Distributed Systems: Theory and Practice" (4 words)
  Document B: "A comprehensive guide covering many topics including distributed systems" (10 words)
  
  Both mention both terms once.
  Document A scores HIGHER because:
  → Same term frequency but shorter document → higher density
  → Length normalization gives advantage to focused content
```

### Relevance Evaluation & Safe Rollout Framework

```
HOW DO YOU KNOW IF RELEVANCE IMPROVED? YOU MEASURE IT.
A Staff Engineer never deploys a relevance change without measurement.

OFFLINE EVALUATION (before deployment):

  JUDGMENT SETS:
    → Curated set of (query, document, relevance_label) triples
    → Labels: Perfect (4), Excellent (3), Good (2), Fair (1), Bad (0)
    → Size: 5,000-10,000 labeled queries
    → Source: Human raters, click logs, editorial teams
    → Updated quarterly (queries change, corpus changes)

  METRICS:
    → NDCG@10: Normalized Discounted Cumulative Gain at position 10
      Measures: Are the best results at the top? Penalizes good results at low positions.
    → Precision@5: % of top 5 results that are relevant
    → Zero-result rate: % of queries returning 0 results (should be < 2%)
    → Regression detection: Compare new model vs current model on judgment sets

  GATE:
    → NDCG@10 must not decrease by > 1% vs production model
    → Zero-result rate must not increase by > 0.5%
    → IF either gate fails: Block deployment, investigate

ONLINE EVALUATION (during and after deployment):

  A/B TESTING FOR RELEVANCE:
    → Deploy new model to 5% of traffic (canary)
    → Control: Current production model (95% of traffic)
    → Treatment: New model (5% of traffic)
    → Duration: 7 days minimum (capture weekly patterns)
    → Metrics compared:
      - Click-through rate (CTR) on search results
      - Mean Reciprocal Rank (MRR) of first click
      - Reformulation rate (user searches again immediately)
      - Add-to-cart / conversion rate (if e-commerce)
      - Session search success rate (user found what they needed)

  STATISTICAL SIGNIFICANCE:
    → Require p < 0.05 for declaring a winner
    → At 5% traffic × 12K QPS = 600 QPS in treatment
    → Sufficient sample size within 24-48 hours for CTR
    → 7 days for conversion metrics (lower signal, needs more data)

  ROLLOUT SEQUENCE:
    1. Offline eval on judgment sets → GATE
    2. Shadow mode: Run new model on production traffic, log results,
       DON'T serve them. Compare with production results offline.
    3. Canary: 5% of traffic for 7 days → A/B metrics
    4. Ramp: 5% → 25% → 50% → 100% over 2 weeks
    5. At any stage: If metrics degrade → rollback within minutes

  ROLLBACK:
    → Relevance model is a versioned artifact (not code)
    → Rollback = update model config to point to previous version
    → Takes effect within seconds (config push, not deployment)
    → Zero code deployment required for rollback

STAFF INSIGHT:
  Relevance is the HARDEST thing to get right in search because
  "better" is subjective and query-dependent. A change that improves
  head queries ("shoes") can degrade tail queries ("blue suede shoes size 11").
  
  The safe rollout framework exists because a bad relevance change is WORSE
  than a latency regression — users notice bad results more than slow results.
  And unlike latency, relevance degradation has no clear error signal.
  Users don't report "results are slightly less relevant" — they just
  leave the platform.
```

---

# Part 7: Data Model & Storage Decisions

## What Data Is Stored

```
DATA CATEGORY 1: Inverted Index (primary search structure)
  → Term dictionary: All unique terms across all documents
  → Posting lists: Document IDs + term frequency + positions per term
  → Size: ~1.5× raw document size
  → Access pattern: Random read (look up specific terms during query)

DATA CATEGORY 2: Stored Fields (original document content)
  → Full document as submitted (or selected fields)
  → Used for: Returning results to client, highlighting
  → Size: ~1× raw document size
  → Access pattern: Sequential read for top-K results only

DATA CATEGORY 3: Doc Values (columnar storage)
  → Per-field column-oriented storage
  → Used for: Sorting, faceting, aggregation
  → Size: ~0.3× raw document size
  → Access pattern: Scan column for matching documents (e.g., all prices for facet)

DATA CATEGORY 4: Transaction Log
  → Append-only log of all mutations (index, update, delete)
  → Used for: Crash recovery, replication
  → Size: Bounded by retention period (e.g., 7 days)
  → Access pattern: Append (writes), sequential scan (recovery)

DATA CATEGORY 5: Metadata
  → Schemas, aliases, cluster state, tenant configuration
  → Size: Kilobytes (tiny)
  → Stored in: External consensus store (ZooKeeper/etcd)
```

## How Data Is Keyed

```
DOCUMENT KEY: (tenant_id, index_name, document_id)
  → Globally unique within the search platform
  → tenant_id prevents cross-tenant collisions
  → index_name allows multiple indexes per tenant
  → document_id is tenant-provided, assumed unique within tenant+index

SHARD KEY: hash(tenant_id + document_id) % num_shards
  → Deterministic: Same document always goes to same shard
  → Uniform: Hash distributes documents evenly across shards
  → Tenant-agnostic: Documents from different tenants share shards
    (unless tenant requests dedicated shards)

TERM KEY: (shard_id, field_name, term)
  → Each shard maintains its own term dictionary
  → Field-level isolation: "title:running" and "description:running"
    are separate posting lists (can have different boosts)

WHY NOT SHARD BY TERM:
  → Sharding by term means a single document's terms scatter across shards
  → Indexing one document requires writing to MANY shards
  → Deleting one document requires writing to MANY shards
  → Document-based sharding keeps all of a document's data on one shard
  → Trade-off: Queries must fan out to all shards, but fan-out is cheap
    with parallel network calls
```

## How Data Is Partitioned

```
PARTITIONING STRATEGY: HASH-BASED DOCUMENT PARTITIONING

  shard_id = hash(tenant_id + doc_id) % num_shards

  PROPERTIES:
  → Uniform distribution: Each shard has ~same number of documents
  → Content-agnostic: Shards don't correspond to categories or topics
  → Query fan-out: ALL shards must be queried (no partition pruning for text queries)

OPTIMIZATION: TENANT-AWARE ROUTING
  For multi-tenant deployments, add tenant routing:
  → Tenant A's documents: shards 0-49
  → Tenant B's documents: shards 50-149
  → Queries for Tenant A only fan out to 50 shards (not all 250)
  
  Implementation: Routing table mapping tenant → shard range
  Benefit: 5× reduction in query fan-out for single-tenant queries

REPLICATION:
  Each shard: 1 primary + 2 replicas = 3 copies
  → Primary: Accepts writes, serves reads
  → Replicas: Serve reads, standby for promotion
  → Replicas lag primary by < 1 second (transaction log replication)
  → Reads can go to any copy (coordinator chooses based on load/latency)
```

## Retention Policies

```
TIERED STORAGE:

HOT TIER (0-30 days):
  → Storage: NVMe SSD
  → Content: Recently indexed/updated documents
  → Performance: Full query speed, in-page-cache
  → Cost: $$$$

WARM TIER (30-180 days):
  → Storage: Standard SSD
  → Content: Older documents, less frequently accessed
  → Performance: Slightly slower (may require disk reads)
  → Cost: $$

COLD TIER (180+ days):
  → Storage: Object storage (cheaper)
  → Content: Rarely accessed documents, compliance retention
  → Performance: Much slower (remote storage, on-demand loading)
  → Cost: $

DELETION POLICY:
  → Configurable per tenant, per index
  → Default: Retain forever (tenant manages their own deletions)
  → Option: Auto-delete documents older than X days
  → Legal/compliance: Some documents must be retained for N years

TRANSACTION LOG RETENTION:
  → 7 days (sufficient for crash recovery and replication catch-up)
  → After 7 days, log entries are purged
  → Full index can always be rebuilt from source of truth if log is insufficient
```

## Schema Evolution

```
ADDITIVE CHANGES (safe, no reindex needed):
  → Add new field: Documents without it → field is null/missing
  → Add new analyzer: Only applies to newly indexed documents
  → Existing documents searched with old analysis until reindexed

BREAKING CHANGES (require reindex):
  → Change field type (string → integer)
  → Change analyzer (standard → language-specific)
  → Remove field
  → Change shard count

ZERO-DOWNTIME SCHEMA MIGRATION:
  1. Create new index (v2) with new schema
  2. Start dual-writing: New mutations go to BOTH v1 and v2
  3. Backfill v2: Copy existing documents from source of truth
  4. Validate v2: Compare result quality against v1
  5. Swap alias: search_alias → v2 (atomic, zero-downtime)
  6. Stop writing to v1
  7. Delete v1 after cooldown period (1 week)

STAFF INSIGHT:
  Schema migration is the most operationally dangerous activity
  in a search system. It involves writing to two indexes simultaneously,
  potentially doubling write load. The migration MUST be reversible:
  if v2 has worse relevance, swap alias back to v1 immediately.
  Always run v1 and v2 in parallel for at least 24 hours before
  committing to v2.
```

## Why Other Data Models Were Rejected

```
REJECTED: Graph database for search
  → WHY ATTRACTIVE: Can model relationships between documents
  → WHY REJECTED: Graph traversal is fundamentally different from text retrieval.
    A graph answers "what is connected to X?" not "what documents match this text?"
    Traversal time grows with graph depth, not bounded by posting list size.
    Use graph for recommendation/relationship queries, not text search.

REJECTED: Key-value store for search
  → WHY ATTRACTIVE: O(1) lookups, simple
  → WHY REJECTED: Search requires INVERTED lookups (content → documents),
    not forward lookups (key → value). Building an inverted index on top
    of a KV store re-implements a search engine, poorly.

REJECTED: Relational database with full-text extensions (PostgreSQL FTS)
  → WHY ATTRACTIVE: Single system for transactional data + search
  → WHY REJECTED: At scale, search load competes with transactional load.
    FTS indices in RDBMS lack: configurable analyzers, distributed sharding,
    replica-based read scaling, tiered storage, faceting, and the query
    optimization depth of a dedicated search engine. Acceptable for < 1M docs.

REJECTED: Column store (ClickHouse, BigQuery) for search
  → WHY ATTRACTIVE: Fast aggregations, analytical queries
  → WHY REJECTED: Optimized for scan-heavy analytics, not for text matching.
    No inverted index. Text search requires scanning all rows.
    Good for log analytics (structured fields), bad for full-text search.
```

---

# Part 8: Consistency, Concurrency & Ordering

## Strong vs Eventual Consistency

```
THE SEARCH INDEX IS EVENTUALLY CONSISTENT WITH THE SOURCE OF TRUTH.
This is a DESIGN CHOICE, not a limitation.

WHAT EVENTUAL CONSISTENCY MEANS IN PRACTICE:

  Time T: User creates product in database (source of truth)
  Time T+0: Database confirms write to user
  Time T+100ms: Mutation enters indexing pipeline queue
  Time T+500ms: Pipeline worker processes mutation
  Time T+1000ms: Shard primary buffers mutation in memory
  Time T+1500ms: Shard primary refreshes → document is searchable
  Time T+2000ms: Replica shards refresh → document searchable on replicas

  GAP: Between T and T+1500ms, document is in database but NOT in search.
  User creates product, immediately searches → might not find it.

MITIGATIONS:

  1. READ-YOUR-OWN-WRITES (per session):
     After indexing, return a "freshness token" (transaction log position).
     On subsequent search from same user, route to a replica that has
     reached at least that position.
     → User sees their own writes immediately
     → Other users see it after normal refresh

  2. SYNCHRONOUS REFRESH (for critical operations):
     After indexing, explicitly trigger refresh on the shard.
     → Document searchable within ~50ms
     → Cost: Higher I/O, more frequent segment creation
     → Reserved for critical paths (e.g., safety-critical content deletion)

  3. ACCEPTANCE OF STALENESS (for most operations):
     Most users don't notice 1-2 second staleness.
     → New products appearing a second late is fine
     → Price updates reflecting a second late is fine
     → Only a problem when users can observe the gap
       (e.g., "I just posted this, why can't I find it?")
```

## Race Conditions

```
RACE CONDITION 1: Concurrent updates to same document
  Thread A: Index doc_42 with price = $50 (version 3)
  Thread B: Index doc_42 with price = $45 (version 4)
  
  If Thread A's write arrives after Thread B's write (out of order):
  → Without versioning: doc_42 shows price = $50 (WRONG — stale version wins)
  → With versioning: Shard compares versions, rejects version 3 if version 4
    is already indexed. doc_42 shows price = $45 (CORRECT).

  SOLUTION: Optimistic concurrency with version numbers.
  Every document has a monotonically increasing version.
  Shard only accepts a write if version > current_version.
  Out-of-order writes are silently discarded.

RACE CONDITION 2: Delete arrives before index
  Thread A: Delete doc_42 (version 5)
  Thread B: Index doc_42 (version 4) — arrives after the delete

  Without handling: doc_42 is re-created (WRONG — delete should win)
  SOLUTION: Tombstone with version. Delete records version 5.
  Subsequent index with version 4 is rejected (version < tombstone version).
  Tombstone retained for a configurable period (e.g., 1 hour).

RACE CONDITION 3: Alias swap during query execution
  Query starts at T=0, uses index v1 via alias "products"
  Alias swaps to index v2 at T=50ms
  Shards 1-100 serve from v1, shards 101-250 serve from v2

  SOLUTION: Coordinator resolves alias to concrete index at query start.
  All shard requests use the resolved index name, not the alias.
  → Query sees a consistent view of one index version.
```

## Idempotency

```
INDEXING IS IDEMPOTENT BY DESIGN:

  Index(doc_42, version=3) called once → doc_42 at version 3
  Index(doc_42, version=3) called again → no-op (same version, same content)
  Index(doc_42, version=3) called a third time → no-op

  WHY THIS MATTERS:
  → Indexing pipeline may retry on failure → no duplicate documents
  → Source systems may send duplicate events → no corruption
  → Reindex operations may overlap with live indexing → no conflicts

DELETION IS IDEMPOTENT:
  Delete(doc_42) called once → doc_42 marked deleted
  Delete(doc_42) called again → no-op (already deleted)

QUERIES ARE NATURALLY IDEMPOTENT:
  Same query, same time → same results (within eventual consistency window)
  Queries have no side effects on the index.
```

## Ordering Guarantees

```
PER-DOCUMENT ORDERING:
  Mutations to the same document ID are applied in version order.
  Out-of-order mutations are rejected (version check).
  → Users see a consistent, monotonically advancing view of each document.

CROSS-DOCUMENT ORDERING:
  NO ordering guarantee between different documents.
  Doc A indexed before Doc B in the pipeline does NOT guarantee
  Doc A is searchable before Doc B.
  
  WHY: Documents may go to different shards, different pipeline workers.
  Enforcing cross-document ordering would require global coordination → too expensive.

QUERY RESULT ORDERING:
  Results are ordered by score (relevance) within a query.
  Across queries: No ordering guarantee (different replicas may refresh at different times).
  Same query at T=0 and T=1: May return different results (index refreshed between).

STAFF INSIGHT:
  The ordering guarantees that MATTER for search are:
  1. Per-document version ordering (prevents stale updates) — ENFORCED
  2. Deletion ordering (deletes must not be undone) — ENFORCED via tombstones
  3. Cross-document ordering — NOT enforced, NOT needed
  4. Query-time ordering — NOT enforced across queries, acceptable
```

## Clock Assumptions

```
CLOCKS IN SEARCH SYSTEMS:

  Document timestamps: Provided by source systems.
  → Used for: Freshness scoring, time-based filtering
  → Assumption: Source system clocks are reasonably accurate (±1 second)
  → Impact if wrong: Freshness sorting may be slightly off, but not catastrophic

  Version numbers: Monotonically increasing integers (NOT timestamps).
  → Used for: Conflict resolution (last-writer-wins by version)
  → No clock dependency — version generated by source system or pipeline
  → Safer than timestamp-based conflict resolution

  Transaction log sequence numbers: Local to each shard.
  → Used for: Replication position, crash recovery checkpoint
  → Monotonic within a shard, no cross-shard coordination needed

  STAFF INSIGHT:
  Search systems should avoid depending on synchronized clocks.
  Version numbers and sequence numbers provide the ordering guarantees
  we need without clock assumptions. Timestamps are used only for
  user-facing features (sorting by date) where ±1 second accuracy is fine.
```

## Index-Source Reconciliation

```
THE INDEX WILL DIVERGE FROM THE SOURCE OF TRUTH. NOT "IF" — "WHEN."

Divergence causes:
  → Indexing pipeline bug drops mutations silently
  → Consumer offset gets stuck (queue backlog not processed)
  → Partial reindex completes but misses some documents
  → Source system sends delete but pipeline is down
  → Network partition between source and pipeline

RECONCILIATION IS A MANDATORY BACKGROUND PROCESS, NOT AN EMERGENCY PROCEDURE.

RECONCILIATION PROCESS:

  STEP 1: SAMPLE VERIFICATION (continuous, every 5 minutes)
    → Pick 1,000 random document IDs from source of truth
    → For each: GET document from search index by ID
    → Compare: Does document exist? Is version current? Are fields correct?
    → Metric: Divergence rate = (mismatched + missing) / sampled
    → Alert: Divergence rate > 0.01% → WARN
    → Alert: Divergence rate > 0.1% → PAGE

  STEP 2: FULL RECONCILIATION (scheduled, weekly or on-demand)
    → Stream ALL document IDs + versions from source of truth
    → Stream ALL document IDs + versions from search index
    → Diff: Identify missing, extra, and version-mismatched documents
    → Queue missing/mismatched documents for re-indexing
    → Queue extra documents (in index but not in source) for deletion
    → Throttle reconciliation writes to avoid impacting live serving

  STEP 3: FRESHNESS CANARY (continuous, every 30 seconds)
    → Index a synthetic "canary document" with known content + timestamp
    → Search for canary document
    → Freshness = current_time - canary_timestamp
    → If freshness > SLO: Pipeline is unhealthy
    → This catches stuck pipelines that sample verification might miss
      (if the pipeline is stuck, all new documents are missing, but
       existing documents look fine in the sample)

  PSEUDO-CODE:
  FUNCTION reconcile(tenant_id, index_name):
    source_cursor = source_of_truth.scan(tenant_id)
    index_cursor = search_index.scan(tenant_id, index_name)
    
    missing = []
    stale = []
    extra = []
    
    // Merge-join on document ID (both cursors sorted)
    WHILE source_cursor.has_next() OR index_cursor.has_next():
      IF source_doc.id < index_doc.id:
        missing.append(source_doc.id)      // In source, not in index
        source_cursor.advance()
      ELSE IF source_doc.id > index_doc.id:
        extra.append(index_doc.id)          // In index, not in source
        index_cursor.advance()
      ELSE:
        IF source_doc.version > index_doc.version:
          stale.append(source_doc.id)       // Index has old version
        source_cursor.advance()
        index_cursor.advance()
    
    // Repair
    FOR doc_id IN missing + stale:
      queue_for_reindex(doc_id)             // Throttled
    FOR doc_id IN extra:
      queue_for_deletion(doc_id)            // Throttled
    
    RETURN {missing: len(missing), stale: len(stale), extra: len(extra)}

STAFF INSIGHT:
  Reconciliation is boring but critical infrastructure. Without it,
  the search index silently drifts from reality over weeks and months.
  The "ghost results" incident (Part 14) happened because there was
  no reconciliation process to catch the stuck pipeline. Every search
  system at Staff level MUST have automated reconciliation with alerting.
  
  An analogy: Reconciliation is to search what checksums are to storage.
  You don't notice their absence until corruption has already spread.
```

---

# Part 9: Failure Modes & Degradation (MANDATORY)

## Partial Failures

```
FAILURE 1: Single shard unresponsive
  CAUSE: Node crash, GC pause, disk I/O stall
  SYMPTOMS: Coordinator timeout waiting for one shard
  USER IMPACT: 
    → If replicas available: Transparent failover, no impact
    → If all replicas down: Partial results (1/250 = 0.4% of data missing)
  DEGRADATION:
    → Return results from 249/250 shards
    → Include in response: "partial_results: true, missing_shards: [shard_42]"
    → Log and alert for investigation
  
  STAFF DECISION: Return partial results, don't fail the whole query.
  Users tolerate 0.4% missing data. They don't tolerate timeouts.

FAILURE 2: Multiple shards on same node fail
  CAUSE: Node hardware failure, kernel panic
  SYMPTOMS: 5-10 shards simultaneously unresponsive
  USER IMPACT: 2-4% of results missing (if replicas on other nodes)
  DEGRADATION:
    → Same as single shard: Return partial results
    → Cluster manager promotes replicas on surviving nodes
    → Schedule re-replication to restore redundancy
  RECOVERY TIME: 30-60 seconds for promotion, hours for re-replication

FAILURE 3: Entire AZ (Availability Zone) failure
  CAUSE: Network partition, power failure, cloud AZ outage
  SYMPTOMS: 33% of nodes unreachable (if 3 AZs)
  USER IMPACT:
    → If replicas distributed across AZs: No data loss, increased latency
      (remaining nodes handle 50% more load)
    → If not: Significant data gaps
  DEGRADATION:
    → Increase query timeout (remaining shards are overloaded)
    → Reduce replica count temporarily (accept lower redundancy)
    → Shed non-critical traffic (analytics queries, bulk exports)
```

## Slow Dependencies

```
SLOW DEPENDENCY 1: Indexing pipeline queue backup
  CAUSE: Downstream shard overload, burst writes, slow merge
  SYMPTOMS: Growing queue depth, increasing indexing lag
  USER IMPACT: Freshness SLO violated — new/updated content not searchable
  DEGRADATION:
    → Query serving unaffected (reads from existing segments)
    → Freshness degrades silently — MUST be monitored
    → Alert on: indexing_lag > 30 seconds
  MITIGATION:
    → Scale up pipeline workers
    → Throttle low-priority tenants
    → Pause background merges to free I/O for indexing

SLOW DEPENDENCY 2: External ranking model service
  CAUSE: ML model serving infrastructure degraded
  SYMPTOMS: Phase 2 ranking takes 200ms instead of 5ms
  USER IMPACT: Total query latency exceeds SLO
  DEGRADATION:
    → Skip Phase 2 ranking, return BM25-only results
    → Results are less relevant but still functional
    → Log: "ranking_fallback: true" for analysis
  STAFF DECISION:
    → ML re-ranking is a BONUS, not a requirement
    → System must function with BM25 alone
    → Never let an ML dependency take down search

SLOW DEPENDENCY 3: Config store / metadata store
  CAUSE: ZooKeeper/etcd cluster degraded
  SYMPTOMS: Can't read cluster state, shard allocation stuck
  USER IMPACT:
    → Query serving: Unaffected (coordinators cache shard map locally)
    → Failure recovery: Delayed (can't promote replicas, can't rebalance)
    → Schema changes: Blocked
  DEGRADATION:
    → Serve from cached state indefinitely
    → Alert: "Running on stale cluster state"
    → Manual intervention if state diverges from reality
```

## Retry Storms

```
SCENARIO: Coordinator retries failed shard requests

  Normal: Shard_42 is slow → Coordinator retries to replica → Gets result
  
  Storm: ALL shards are slow (e.g., cluster-wide GC storm)
  → Coordinator retries ALL 250 shards → 500 total requests (2× load)
  → Retries also fail → retry again → 750 requests (3× load)
  → System load increases exponentially → complete collapse

  MITIGATION:
  1. RETRY BUDGET: Max 10% retries per query (25 out of 250 shards)
     → If > 25 shards fail, return partial results, don't retry more
  2. CIRCUIT BREAKER per shard: If shard fails 5× in 10 seconds,
     stop sending requests for 30 seconds
  3. JITTER: Add random delay to retries to avoid synchronized retry waves
  4. SPECULATIVE RETRY (hedged request): Send to second replica
     BEFORE first times out (after 80th percentile latency). Cancel
     whichever responds second. Cost: ~10% more reads, but eliminates
     tail latency from slow replicas.
```

## Data Corruption

```
CORRUPTION 1: Index segment corruption
  CAUSE: Disk failure, incomplete write, bit rot
  DETECTION: Checksum mismatch on segment open
  IMPACT: Shard cannot read corrupted segment → missing data for those documents
  RECOVERY:
    → Failover to replica (immediate)
    → Rebuild corrupted shard from transaction log + other replicas
    → If all replicas corrupted: Rebuild from source of truth (hours)
  PREVENTION: Checksums on every segment, periodic integrity checks

CORRUPTION 2: Silent data corruption (wrong content, not detected by checksum)
  CAUSE: Bug in text analysis pipeline, schema mismatch, encoding error
  DETECTION: Hard — only noticed when users report wrong results
  IMPACT: Documents searchable but with wrong content → relevance degradation
  RECOVERY:
    → Identify scope of corruption (which documents, which fields)
    → Reindex affected documents from source of truth
    → If widespread: Full reindex
  PREVENTION:
    → Validate indexed content against source (sample-based verification)
    → Canary new analyzer/pipeline changes on a small subset before full rollout

CORRUPTION 3: Stale deletion bitmap
  CAUSE: Bitmap not updated after deletion, replication lag
  DETECTION: Deleted documents still appearing in search results
  IMPACT: Users see content that should not exist (privacy, legal risk)
  RECOVERY:
    → Force refresh on affected shards
    → If persistent: Rebuild shard from transaction log
  PREVENTION:
    → Monitor "ghost documents" (docs in index but not in source of truth)
    → Periodic reconciliation between index and source
```

## Control-Plane Failures

```
FAILURE: Cluster manager leader crashes
  IMPACT:
    → Data serving: UNAFFECTED (coordinators and shards operate independently)
    → Failure recovery: BLOCKED (no new primary elections, no rebalancing)
    → Admin operations: BLOCKED (no schema changes, no index creation)
  RECOVERY:
    → Leader election selects new cluster manager leader
    → Time: 10-30 seconds
    → During this time, the system is fully functional for reads and writes
      (just can't respond to failures)
  STAFF INSIGHT:
    The cluster manager being down is LOW urgency if nothing else is failing.
    It's HIGH urgency if a node failure coincides with cluster manager downtime.
    Design: Make cluster manager highly available (3-5 replicas with leader election).

FAILURE: Config store (ZooKeeper) loses quorum
  IMPACT:
    → Cluster manager can't update state
    → All nodes use cached last-known-good state
    → System is frozen in current configuration
  RECOVERY:
    → Restore ZooKeeper quorum (restart members, add new members)
    → System resumes normal operation from last committed state
  STAFF INSIGHT:
    ZooKeeper quorum loss is a RARE but HIGH-IMPACT event.
    Mitigation: Run ZooKeeper across 3+ AZs. Practice recovery regularly.
```

## Failure Timeline Walkthrough

```
T=0:00  Node 7 experiences disk failure
        → 8 shards on Node 7 become unreachable (5 primaries, 3 replicas)

T=0:01  Coordinators detect timeouts from Node 7's shards
        → Queries to those shards fail over to replicas on other nodes
        → User impact: None (replica failover is transparent)

T=0:30  Cluster manager detects Node 7 heartbeat timeout
        → Marks Node 7 as dead
        → Promotes 5 replica shards to primary (on other nodes)
        → Primary election complete

T=0:35  New primaries start accepting writes
        → Write path fully restored
        → Cluster is UNDER-REPLICATED: 8 shards have fewer than 3 copies

T=1:00  Cluster manager schedules re-replication
        → New replicas allocated on surviving nodes
        → Replication starts from new primaries

T=2:00  Re-replication in progress
        → Throttled to avoid impacting query serving
        → Each shard: 40 GB × 3 copies = 120 GB network transfer
        → At 100 MB/s throttle: ~20 minutes per shard

T=0:25  Re-replication complete for all 8 shards
        → Cluster fully healthy
        → Node 7 replaced, new node joins cluster
        → Rebalance shards to include new node

TOTAL USER IMPACT: ~0 seconds downtime (replica failover at T=0:01)
TOTAL CLUSTER RECOVERY: ~25 minutes
```

## Cascading Failure: Write Path Poisoning the Read Path

```
THE MOST DANGEROUS FAILURE MODE IN SEARCH:
A write-path overload cascades into read-path degradation.

This is the failure that takes down production search. It's not a single
component failure — it's a chain reaction where each step makes the next worse.

STEP-BY-STEP CASCADING TIMELINE:

T=0:00  TRIGGER: Tenant A starts bulk reindex (500K docs/minute)
        → Indexing pipeline accepts all writes (no per-tenant quota in V2)
        → Shard primaries begin buffering mutations

T=0:05  Shard indexing buffers fill faster than normal
        → Refresh cycle creates 5× more segments than usual
        → 5× more segments = 5× more files per shard to search

T=0:15  SEGMENT MERGE TRIGGERED (background process)
        → Merge process reads old segments + writes new merged segment
        → Disk I/O doubles: Merge I/O + query I/O compete for the same SSD
        → Page cache evicted by merge reads → query I/O now hits disk

T=0:20  QUERY LATENCY DEGRADES (propagation to read path)
        → P99 query latency rises from 100ms → 500ms
        → Coordinators start timing out shard requests
        → Coordinators issue speculative retries → 1.3× shard load

T=0:25  RETRY AMPLIFICATION
        → More timeouts → more retries → more shard load
        → Shard CPU saturated: Serve merge + queries + retries
        → P99 → 2000ms, partial results on 30% of queries

T=0:30  CLIENT RETRIES (user-visible)
        → Product teams' services start retrying failed searches
        → External QPS doubles: 12K → 24K
        → Coordinators overwhelmed → query queue grows

T=0:35  CASCADING COLLAPSE
        → Query queue full → coordinators reject new queries (503)
        → 50% of queries failing
        → On-call paged: "Search is down"

T=0:40  MANUAL INTERVENTION
        → On-call identifies bulk reindex as root cause
        → Kills Tenant A's reindex job
        → But: Merge storm continues (merges in progress can't be cancelled)

T=0:55  GRADUAL RECOVERY
        → Merges complete, I/O pressure drops
        → Page cache warms up, queries return to SSD/cache
        → P99 drops to 200ms

T=1:10  FULL RECOVERY
        → All metrics back to normal
        → Post-incident: Add per-tenant indexing quotas, tie merge
          throttle to query latency, add circuit breaker on coordinator retries

CONTAINMENT MECHANISMS (what V3 adds to prevent this):
  1. Per-tenant indexing rate limits (prevent unbounded writes)
  2. Merge throttle tied to query latency:
     IF query_p99 > 2× baseline: PAUSE all merges
     → Queries recover immediately; merges resume when latency normalizes
  3. Coordinator retry budget: Max 10% retries per query
  4. Write-path I/O isolation: Separate disk I/O queues for merges vs queries
     (using OS-level I/O scheduling or dedicated merge disks)
  5. Automatic load shedding: If coordinator queue > threshold,
     shed Tier 3-4 queries before affecting Tier 1

STAFF INSIGHT:
  This cascading failure is the #1 reason search systems have outages.
  It's not a single component failing — it's a positive feedback loop
  where write load creates I/O contention that degrades reads, which
  triggers retries that add more load. The ONLY way to break the loop
  is proactive throttling at the write path BEFORE it affects the read path.
  Reactive responses (killing the job after collapse) always take too long.
```

## Observability & Monitoring Architecture

```
SEARCH OBSERVABILITY IS A FIRST-CLASS SUBSYSTEM, NOT AN AFTERTHOUGHT.

A search system that returns results is not necessarily healthy.
Staleness, relevance degradation, and slow tail latency are invisible
without explicit monitoring. The observability architecture must answer
three questions at all times:
  1. Are queries fast? (Latency SLOs)
  2. Is the index fresh? (Freshness SLOs)
  3. Are results relevant? (Quality SLOs)

TIER 1: QUERY PATH METRICS (real-time, per-second granularity)

  LATENCY:
    → P50, P95, P99, P999 query latency (per tenant, per index, global)
    → Per-phase breakdown: Parse, scatter, shard execution, gather, re-rank
    → Per-shard latency distribution (identify slow shards)
    → Autocomplete latency (separate from search — different SLO)
  
  THROUGHPUT:
    → QPS by tenant, by index, by query type (search vs suggest vs scroll)
    → Error rate by type: timeout, shard failure, rate limited, rejected
    → Partial result rate: % of queries with missing shards
  
  ALERTS:
    → P99 > 300ms for 5 minutes → PAGE (immediate)
    → Error rate > 1% for 2 minutes → PAGE
    → Partial result rate > 5% for 5 minutes → WARN
    → QPS drop > 30% vs same time yesterday → WARN (possible upstream issue)

TIER 2: INDEXING PATH METRICS (near-real-time, per-minute granularity)

  FRESHNESS:
    → Indexing lag: Time between document mutation and searchability
      Measured per-tenant, per-shard, per-pipeline-stage
    → Lag percentiles: P50, P95, P99 indexing lag
    → Queue depth: Messages waiting in indexing queue (per tenant)
  
  THROUGHPUT:
    → Documents indexed per second (per tenant)
    → Indexing errors per second (schema violations, pipeline failures)
    → Segment merge rate: Merges per minute, merge duration, merge I/O
  
  ALERTS:
    → Indexing lag P95 > 30 seconds → PAGE (freshness SLO violated)
    → Queue depth growing for > 10 minutes → WARN
    → Indexing error rate > 5% → PAGE
    → Zero documents indexed for 5 minutes (pipeline stuck) → PAGE

TIER 3: CLUSTER HEALTH METRICS (background, per-minute)

  NODE HEALTH:
    → CPU, memory, disk I/O, disk usage per node
    → GC pause frequency and duration (per JVM node)
    → Network throughput between nodes
  
  SHARD HEALTH:
    → Shard allocation status: Unassigned, initializing, relocating
    → Replica lag per shard (transaction log position delta)
    → Segment count per shard (too many = query slowdown)
    → Under-replicated shard count (redundancy at risk)
  
  ALERTS:
    → Disk usage > 85% on any node → WARN
    → Unassigned shards > 0 for 5 minutes → PAGE
    → Under-replicated shards > 10% → WARN
    → GC pause > 5 seconds → WARN

TIER 4: RELEVANCE QUALITY METRICS (daily + per-deployment)

  OFFLINE METRICS:
    → NDCG@10 (Normalized Discounted Cumulative Gain) on judgment sets
    → Precision@K on editorial ratings
    → Zero-result rate: % of queries returning 0 results
  
  ONLINE METRICS:
    → Click-through rate (CTR) on search results
    → Mean Reciprocal Rank (MRR) of first clicked result
    → Reformulation rate: % of users who immediately search again
      (high reformulation = bad relevance)
    → Abandonment rate: % of searches with no click (bad relevance or no intent)
  
  ALERTS:
    → NDCG drops > 5% after deployment → BLOCK deployment, auto-rollback
    → Zero-result rate > 2× baseline → WARN
    → CTR drops > 10% vs yesterday → INVESTIGATE

DASHBOARD STRUCTURE:
  → PLATFORM OVERVIEW: Global QPS, latency, error rate, indexing lag
  → PER-TENANT VIEW: Tenant-specific latency, freshness, quota usage
  → SHARD EXPLORER: Per-shard latency, segment count, disk usage
  → INCIDENT VIEW: Timeline of alerts, deployments, config changes
  → RELEVANCE DASHBOARD: NDCG trends, CTR, zero-result rate

STAFF INSIGHT ON OBSERVABILITY:
  Most search incidents are detected by TENANT TEAMS, not the platform team.
  "Our search results look wrong" is the most common report.
  This means the platform's observability FAILED to detect the problem first.
  
  The fix: Freshness monitoring (indexing lag), relevance monitoring (NDCG),
  and per-tenant dashboards that tenant teams can self-serve.
  The platform team should detect problems BEFORE tenants report them.
```

---

# Part 10: Performance Optimization & Hot Paths

## Critical Paths

```
THE HOTTEST PATH: Query → Posting List Intersection → Scoring → Top-K

  This path executes for EVERY query, on EVERY shard.
  At 12K QPS × 250 shards = 3 million shard-level operations per second.

  BREAKDOWN:
  1. Term dictionary lookup: O(log V) where V = vocabulary size (~10M terms)
     Implementation: FST (Finite State Transducer) in memory
     → ~1µs per term lookup

  2. Posting list decompression: Read compressed posting list from disk/cache
     → ~10µs for short lists (<1K entries)
     → ~100µs for long lists (>100K entries)

  3. Intersection: AND of multiple posting lists
     → Skip-list based intersection: O(min(|L1|, |L2|) × log(max(|L1|, |L2|)))
     → For "running" (50K) AND "shoes" (80K): ~50K × 17 = 850K comparisons
     → ~500µs

  4. Scoring (BM25): O(|intersection|)
     → 12K matching docs × 3 terms × 5 multiplications = 180K operations
     → ~200µs

  5. Top-K selection: Priority queue of size K
     → O(|intersection| × log(K))
     → ~100µs

  TOTAL per shard: 1-5ms for typical queries, 10-50ms for complex queries
```

## Caching Strategies

```
CACHE LAYER 1: Query result cache (coordinator level)
  WHAT: Full query response cached by (query_string, filters, sort, tenant_id)
  HIT RATE: 15-30% (popular queries repeat often)
  TTL: 1-5 minutes (balance freshness vs cache hit rate)
  SIZE: 10 GB per coordinator node
  
  WHY: A cached query avoids ALL shard fan-out.
  → 30% hit rate at 12K QPS = 3,600 queries/sec served from cache
  → Saves 3,600 × 250 = 900K shard requests/sec

  INVALIDATION:
  → Time-based: TTL eviction (simple, good enough for most cases)
  → Event-based: Invalidate when index refreshes (complex, better freshness)
  → Per-tenant TTL: Critical tenants get shorter TTL (fresher results)

CACHE LAYER 2: Filter cache (shard level)
  WHAT: Pre-computed bitsets for frequently used filters
  EXAMPLE: filter "in_stock = true" → bitset of all in-stock doc IDs
  HIT RATE: 60-80% (filters repeat more than queries)
  SIZE: Auto-managed, evicts least-recently-used

  WHY: Applying a filter during query is O(posting_list_size).
  With cached filter bitset: O(1) per document (bit check).
  For popular filters, this is a 10-100× speedup.

CACHE LAYER 3: OS page cache (shard level)
  WHAT: Memory-mapped index files cached by OS in RAM
  HIT RATE: 80-95% (working set fits in memory)
  SIZE: Managed by OS, proportional to available RAM

  WHY: Disk reads for index files are 10-100× slower than memory reads.
  Keeping the inverted index in page cache eliminates most disk I/O.
  This is why search nodes need lots of RAM even though the index is on disk.

CACHE ANTI-PATTERN: Caching personalized results
  → Personalized results differ per user → cache key includes user_id
  → Cache hit rate drops to < 1% (each user has unique results)
  → WASTE of cache space
  → SOLUTION: Cache the retrieval phase (non-personalized BM25 results),
    apply personalization in re-ranking (not cached)
```

## Precomputation vs Runtime Work

```
PRECOMPUTATION (at index time):
  → Text analysis (tokenize, stem, normalize): Done once at index time,
    NOT at query time. Query-time analysis only on the query string.
  → Doc values (column store): Pre-computed per field for fast sorting/faceting
  → Popularity scores: Pre-computed daily from analytics pipeline
  → Autocomplete suggestions: Pre-built from query logs + document titles

RUNTIME (at query time):
  → Posting list intersection: Must be done at query time (query-dependent)
  → BM25 scoring: Must be done at query time (query-dependent)
  → ML re-ranking: Must be done at query time (personalization signals)
  → Facet counting: Must be done at query time (depends on query match set)

WHAT WE INTENTIONALLY DO NOT PRECOMPUTE:
  → All possible query results: Combinatorial explosion (impossible)
  → Global document ranking: Rankings are query-dependent (BM25 × IDF)
  → Cross-shard merge: Must be done at query time (query determines merge)

STAFF INSIGHT:
  The art is moving as much work as possible from query time to index time
  WITHOUT sacrificing flexibility. Every precomputation is a bet that the
  precomputed result will be useful. Over-precomputation wastes storage and
  indexing resources. Under-precomputation wastes query-time resources.
```

## Backpressure & Load Shedding

```
BACKPRESSURE (slow down producers when consumers are overloaded):

  1. Query queue depth > threshold:
     → Reject new queries with 503 (Service Unavailable)
     → Clients retry with exponential backoff
     → Prevents query queue from growing unbounded

  2. Indexing queue depth > threshold:
     → Reject new mutations with 429 (Too Many Requests)
     → Source systems buffer and retry
     → Prevents indexing pipeline from overwhelming shards

  3. Per-shard indexing buffer > 90% full:
     → Pipeline workers slow writes to that shard
     → Other shards unaffected
     → Prevents shard-level memory pressure

LOAD SHEDDING (drop lower-priority work when overloaded):

  1. Priority tiers:
     Tier 1 (never shed): Live user search queries
     Tier 2 (shed at 80% capacity): Analytics/reporting queries
     Tier 3 (shed at 60% capacity): Bulk export queries, reindex operations
     Tier 4 (shed at 40% capacity): Background integrity checks

  2. Per-tenant shedding:
     → Tenants with lower SLA tier are shed first
     → Enterprise tenants shed last
     → Prevents one tenant's spike from affecting premium tenants

  3. Query cost estimation:
     → Before executing, estimate query cost based on:
       term frequency (high-frequency terms = expensive)
       number of shards to query
       presence of wildcards or regex
     → If estimated cost > budget, reject or simplify query
     → Prevents "query of death" (one expensive query that brings down a shard)
```

## Query-of-Death Detection and Kill

```
A "QUERY OF DEATH" IS A SINGLE QUERY THAT CAN BRING DOWN A SHARD.

EXAMPLES:
  → Wildcard on high-cardinality field: field:* → enumerate all terms
  → Unbounded regex: field:/.*pattern.*/ → catastrophic backtracking
  → Leading wildcard: *shoes → cannot use inverted index, must scan
  → Massive disjunction: term1 OR term2 OR ... OR term10000
  → Deep pagination with sorting: Get page 10,000 sorted by price
    (must score and sort top 200,000 documents)

WHY THIS IS A STAFF-LEVEL CONCERN:
  → One user's bad query can affect ALL users on the same shard
  → The shard has no per-query resource isolation (shared CPU, shared memory)
  → A single stuck query consumes a thread/goroutine, reducing shard concurrency
  → If the query triggers excessive memory allocation → GC pause → all queries slow

DETECTION AND PREVENTION:

  LAYER 1: QUERY COST ESTIMATION (coordinator, before scatter)
    FUNCTION estimate_query_cost(parsed_query):
      cost = 0
      FOR term IN parsed_query.terms:
        df = term_stats.get_doc_frequency(term)    // Cached term statistics
        cost += df                                  // More matches = more work
      IF parsed_query.has_wildcard:
        cost *= 100                                 // Wildcards are 100× more expensive
      IF parsed_query.has_regex:
        cost *= 1000                                // Regex is 1000× more expensive
      IF parsed_query.page_offset > 1000:
        cost += parsed_query.page_offset            // Deep pagination is expensive
      
      IF cost > MAX_QUERY_COST:
        REJECT with 400: "Query too expensive. Simplify or add filters."
      RETURN cost

  LAYER 2: PER-QUERY TIMEOUT (shard level)
    → Each shard enforces a per-query execution timeout (e.g., 100ms)
    → If query exceeds timeout: Kill the query, return partial results
    → Log: Query text, estimated cost, actual execution time, shard ID
    → This prevents a single query from monopolizing a shard's CPU

  LAYER 3: CIRCUIT BREAKER ON EXPENSIVE QUERIES
    → Track per-query-pattern execution cost
    → If the same query pattern (normalized) exceeds timeout 3× in 1 minute:
      → Block that pattern for 5 minutes
      → Return cached "This query is temporarily unavailable" error
    → Prevents retry loops on inherently expensive queries

  LAYER 4: PER-SHARD CONCURRENCY LIMIT
    → Each shard allows max N concurrent queries (e.g., 50)
    → If all slots are occupied: New queries queue with short timeout
    → If queue is full: Reject with 503
    → One expensive query consumes 1 slot; it can't consume all 50
    → Ensures fast queries aren't blocked by slow ones

STAFF INSIGHT:
  Query-of-death is a multi-tenancy concern as much as a technical one.
  In a shared cluster, Tenant A's developer writing SELECT * equivalent
  can degrade Tenant B's production search. The coordinator MUST reject
  dangerous queries BEFORE they reach the shards. Rejection at the
  coordinator is cheap; execution at the shard is expensive and damages
  everyone on that shard.
```

## Why Some Optimizations Are Intentionally NOT Done

```
NOT DONE: Pre-joining posting lists for common term pairs
  WHY ATTRACTIVE: "running shoes" queries could use a pre-joined list
  WHY REJECTED: Combinatorial explosion — 10M terms × 10M terms = 100T pairs
  INSTEAD: Fast intersection algorithms (skip-list) handle common pairs well

NOT DONE: Real-time ML re-ranking on every query
  WHY ATTRACTIVE: Better relevance on every query
  WHY REJECTED: ML model inference adds 20-50ms latency to every query.
  At 12K QPS, this is 12K × 50ms = 600 CPU-seconds per real-second.
  INSTEAD: Two-phase approach — BM25 retrieval (cheap) + ML on top-100 only

NOT DONE: Global consistent snapshots for scrolling
  WHY ATTRACTIVE: Page 1 and page 10 show consistent results
  WHY REJECTED: Holding shard-level snapshots for every scroll session
  consumes resources. At 10K concurrent scrolls × 250 shards = 2.5M snapshots.
  INSTEAD: search_after with a sort tiebreaker (deterministic ordering
  without server-side state)

NOT DONE: Exact global term statistics for IDF
  WHY ATTRACTIVE: More accurate BM25 scoring across shards
  WHY REJECTED: Requires cross-shard coordination on every query.
  Per-shard IDF statistics are close enough (shards have similar distributions).
  INSTEAD: Use shard-local statistics, which are accurate within ~5%
  for uniformly distributed data
```

---

# Part 11: Cost & Efficiency

## Major Cost Drivers

```
COST BREAKDOWN (approximate, for 110-node cluster):

  1. COMPUTE (50% of total cost):
     → 110 data nodes × 16 cores = 1,760 cores
     → 10 coordinator nodes × 16 cores = 160 cores
     → 10 pipeline workers × 8 cores = 80 cores
     → Total: ~2,000 cores

  2. STORAGE (30% of total cost):
     → 30 TB NVMe SSD across data nodes (hot tier)
     → 50 TB object storage (cold tier)
     → Transaction logs: 5 TB replicated storage

  3. MEMORY (15% of total cost):
     → 110 data nodes × 64 GB = 7 TB RAM
     → Most used for OS page cache (keeping index in memory)
     → Direct memory cost + opportunity cost of RAM-heavy nodes

  4. NETWORK (5% of total cost):
     → Cross-AZ replication: 3× write amplification
     → Scatter-gather: 250 shard responses per query
     → 12K QPS × 250 × 4 KB response = 12 GB/sec aggregate network
```

## How Cost Scales with Traffic

```
SCALING DIMENSIONS:

  QUERY THROUGHPUT (QPS) → Scale COORDINATORS + REPLICAS
  → More QPS = more coordinator CPU + more shard replicas
  → Linear cost increase per QPS unit
  → Optimization: Query caching reduces effective QPS at shard level

  CORPUS SIZE (documents) → Scale STORAGE + SHARDS
  → More documents = more shards = more nodes
  → Sub-linear cost increase (larger shards before adding new ones)
  → Optimization: Tiered storage (cold tier is 10× cheaper than hot)

  INDEXING THROUGHPUT → Scale PIPELINE + PRIMARY SHARD I/O
  → More writes = more pipeline workers + more I/O budget
  → Non-linear cost increase (merging costs grow with write rate)
  → Optimization: Batch writes, reduce refresh frequency

  COST PER QUERY AT SCALE:
  Cluster cost: ~$100K/month
  Queries/month: 15 billion
  Cost per query: $0.000007 (7 millionths of a dollar)
  → Search is cheap per query, expensive in aggregate
```

## Trade-offs Between Cost and Reliability

```
TRADE-OFF 1: Replica count
  2 replicas: Tolerates 1 node failure, costs 3× storage
  3 replicas: Tolerates 2 node failures, costs 4× storage
  DECISION: 2 replicas for most data, 3 replicas for critical tenants

TRADE-OFF 2: Refresh interval
  100ms refresh: Documents searchable in 100ms, high I/O (more segments)
  1s refresh: Documents searchable in 1s, moderate I/O
  30s refresh: Documents searchable in 30s, low I/O
  DECISION: 1s default, configurable per tenant (trade freshness vs cost)

TRADE-OFF 3: Query timeout
  100ms timeout: Fast failures, but complex queries may not complete
  500ms timeout: Most queries complete, but slow queries waste resources
  DECISION: 200ms default with per-tenant override; adaptive timeout
  based on query complexity estimation

TRADE-OFF 4: Hot/warm/cold tiers
  All hot: Best performance, highest cost
  Tiered: Good performance for recent data, cheaper for old data
  DECISION: Tiered — 30 days hot, 180 days warm, rest cold
  Monthly savings: ~40% vs all-hot
```

## What Over-Engineering Looks Like

```
OVER-ENGINEERING 1: Real-time ML re-ranking on every query
  → Adds 20-50ms latency, requires ML serving infrastructure
  → For most use cases, BM25 + simple boosts is 90% as good
  → Add ML only when relevance is measurably worse without it

OVER-ENGINEERING 2: Per-query consistency guarantees
  → Ensuring every query sees the absolute latest data
  → Requires synchronous refresh after every write → kills write throughput
  → 99.9% of queries don't need this — eventual consistency is fine

OVER-ENGINEERING 3: Dedicated cluster per tenant
  → Full isolation, but 10 tenants × 110 nodes = 1,100 nodes
  → Most tenants can share infrastructure with logical isolation
  → Dedicated clusters only for tenants with fundamentally different SLAs

OVER-ENGINEERING 4: Cross-region strong consistency
  → Ensuring all regions see exactly the same results at the same time
  → Requires consensus protocol across regions → inter-region latency on writes
  → Each region having its own eventually-consistent replica is sufficient
```

## Cost-Aware Redesign

```
SCENARIO: Budget cut — reduce search infrastructure cost by 40%

APPROACH:
  1. IMPLEMENT TIERED STORAGE (saves 25%)
     → Move documents older than 30 days to warm tier (cheaper SSD)
     → Move documents older than 180 days to cold tier (object storage)
     → 70% of documents are cold → 70% × 30% storage cost share × 90% savings

  2. INCREASE QUERY CACHE HIT RATE (saves 10%)
     → Increase cache TTL from 1 min to 5 min (tolerate more staleness)
     → Implement request coalescing (deduplicate identical concurrent queries)
     → Cache hit rate: 30% → 50% → 20% reduction in shard load

  3. REDUCE REPLICA COUNT FOR NON-CRITICAL TENANTS (saves 15%)
     → Premium tenants: 3 replicas (unchanged)
     → Standard tenants: 2 replicas → 1 replica
     → Saves 33% storage for standard tenants

  4. RIGHT-SIZE NODES (saves 5%)
     → Some nodes are under-utilized (low CPU, high storage)
     → Move to storage-optimized instances (cheaper per GB)

  RESULT: 40% cost reduction with:
  → Slightly higher latency for cold-tier queries
  → Slightly staler cache results
  → Lower fault tolerance for standard tenants
  → All changes are REVERSIBLE if SLOs are violated
```

---

# Part 12: Multi-Region & Global Considerations

## Why Multi-Region for Search

```
REASONS:
  1. LATENCY: Users in Europe shouldn't wait 200ms round-trip to US servers.
     Cross-region network latency: 80-150ms one way.
     With multi-region: Users query the nearest region → <50ms network RTT.

  2. AVAILABILITY: Single-region failure should not take down search globally.
     With multi-region: If US-East fails, US-West and EU serve all traffic.

  3. DATA LOCALITY: Some data must stay in specific regions (GDPR, data residency).
     With multi-region: EU user data indexed and served from EU cluster.

  4. SCALE: Single cluster has operational limits (~500 nodes before
     cluster management becomes unwieldy).
     With multi-region: Spread load across independent regional clusters.
```

## Replication Strategies

```
STRATEGY 1: FULL REPLICATION (every region has everything)
  
  ┌──────────────────────────────────────────────────-───-┐
  │                                                       │
  │   US-EAST              US-WEST            EU-WEST     │
  │   ┌──────────┐        ┌──────────┐       ┌──────────┐ |
  │   │ Full     │        │ Full     │       │ Full     │ |
  │   │ Index    │  ←───→ │ Index    │ ←───→ │ Index    │ |
  │   │ (2B docs)│        │ (2B docs)│       │ (2B docs)│ |
  │   └──────────┘        └──────────┘       └──────────┘ |
  │                                                       │
  │   WRITE:One region is primary writer, others replicate│
  │   READ: Each region serves local queries              │
  └─────────────────────────────────────────────────────--┘

  PROS: Any region can serve any query. Simple failover (any region takes all traffic).
  CONS: 3× storage cost. Cross-region replication bandwidth. Write amplification.
  WHEN: Global products where any user can search any data (e.g., marketplace).

STRATEGY 2: PARTITIONED REPLICATION (regional data stays regional)
  
  ┌─────────────────────────────────────────────────────--┐
  │                                                       │
  │   US-EAST              US-WEST           EU-WEST      │
  │   ┌──────────┐        ┌──────────┐       ┌──────────┐ |
  │   │ US Data  │        │ US Data  │       │ EU Data  │ |
  │   │ (1B docs)│  ←───→ │ (1B docs)│       │ (1B docs)│ |
  │   └──────────┘        └──────────┘       └──────────┘ |
  │                                                       │
  │   US data replicated within US regions                │
  │   EU data stays in EU (GDPR compliance)               │
  │   Cross-region queries: Federated search              │
  └────────────────────────────────────────────────--─────┘

  PROS: Data locality compliance. Less replication. Smaller per-region clusters.
  CONS: Cross-region queries require federation (higher latency).
        Failover is regional (EU can't fail over to US for EU-only data).
  WHEN: Data residency requirements, regional products.

STRATEGY 3: LEADER-FOLLOWER REPLICATION
  
  One region is the indexing leader (accepts all writes).
  Other regions are followers (receive replicated index segments).

  PROS: No write conflicts (single writer). Simpler consistency model.
  CONS: Write latency from non-leader regions (must route to leader).
        Leader region is a single point of failure for writes.
  WHEN: Write volume is low relative to read volume.
        Simpler operational model preferred.

STAFF RECOMMENDATION:
  Start with Strategy 3 (Leader-Follower) for simplicity.
  Move to Strategy 1 (Full Replication with multi-leader writes)
  when write latency from non-leader regions becomes unacceptable.
  Use Strategy 2 only when data residency mandates it.
```

## Traffic Routing

```
ROUTING STRATEGY:

LAYER 1: DNS-based geo-routing
  → Route users to nearest region based on IP geolocation
  → Latency-based routing (AWS Route 53, GCP Cloud DNS)
  → Failover: If region unhealthy, DNS routes to next-nearest region

LAYER 2: Application-level routing
  → For federated queries: Coordinator determines which regions have data
  → For failover: Application detects regional failure, redirects to backup

FAILOVER SEQUENCE:
  1. Health checker detects US-East cluster degraded (latency > SLO)
  2. DNS weight for US-East reduced to 0
  3. Traffic shifts to US-West (increased load)
  4. US-West scales up to handle additional load
  5. When US-East recovers, gradually restore DNS weight (canary)

CROSS-REGION QUERY (federated search):
  User in US queries for data that exists in both US and EU:
  → US coordinator handles query locally for US data
  → US coordinator sends sub-query to EU for EU data
  → EU returns results to US coordinator
  → US coordinator merges results from both regions
  → Total latency: max(local_latency, cross_region_latency + remote_latency)
  → Cross-region adds 80-150ms → federated queries are slower
  → OPTIMIZATION: Only federate if query explicitly requests cross-region data
```

## Failure Across Regions

```
SCENARIO: EU-West region completely fails

  IMPACT (with full replication):
  → EU users routed to US-East or US-West (higher latency)
  → All data available from US regions
  → Write path: Mutations queue for EU-West, applied when recovered
  → User impact: 80-150ms additional latency, no data loss

  IMPACT (with partitioned replication):
  → EU-only data: UNAVAILABLE from other regions
  → Shared/US data: Available from US regions
  → Compliance consideration: Even in failure, EU data must not be served
    from US if data residency requires EU-only hosting

SCENARIO: Cross-region replication lag > 1 hour

  IMPACT:
  → Follower regions serve stale data
  → New content not searchable in follower regions
  → Writes still accepted by leader region
  → If leader fails during lag: 1 hour of data could be temporarily lost
    from follower regions (recoverable from leader's transaction log)

  MITIGATION:
  → Monitor cross-region replication lag as a first-class metric
  → Alert at > 5 minutes lag
  → Investigate at > 15 minutes lag
  → Pause non-critical replication consumers to prioritize search index replication
```

## When Multi-Region Is NOT Worth It

```
SKIP MULTI-REGION WHEN:
  1. All users are in one geography (single-country product)
  2. Corpus is small enough for single-cluster (<100 nodes)
  3. Availability requirement is < 99.95% (single-region achieves this)
  4. Budget doesn't support 2-3× infrastructure cost
  5. Write latency from non-local regions is acceptable (use CDN/edge caching)

THE COST OF MULTI-REGION SEARCH:
  → 2-3× infrastructure cost (full replication)
  → Operational complexity: Coordinating deployments, monitoring, failover
  → Cross-region debugging: Incidents span multiple clusters
  → Consistency challenges: Replication lag creates divergent views

STAFF INSIGHT:
  Don't go multi-region because it's "best practice."
  Go multi-region because your latency SLO, availability SLO, or data
  residency requirements DEMAND it. The cost and complexity are real.
  Many successful search systems run in a single region with
  multi-AZ redundancy and achieve 99.95% availability.
```

---

# Part 13: Security & Abuse Considerations

## Abuse Vectors

```
ABUSE 1: Query-based denial of service
  ATTACK: Flood search API with expensive queries
  → Wildcard queries: "*" matches every document → full index scan
  → Regex queries: Complex regex can cause catastrophic backtracking
  → Deep pagination: Request page 10,000 → must score top 200,000 results
  
  MITIGATION:
  → Per-tenant QPS rate limiting
  → Query cost estimation: Reject queries estimated to exceed cost budget
  → Wildcard/regex restrictions: Require minimum prefix length (3+ chars)
  → Max page depth: Limit pagination to 10,000 results
  → Timeout: Kill queries that exceed per-query time budget

ABUSE 2: Index pollution
  ATTACK: Submit millions of spam documents to dilute search quality
  
  MITIGATION:
  → Per-tenant indexing rate limits
  → Content quality scoring during indexing
  → Spam detection in indexing pipeline
  → Rate limiting on new document creation (vs updates)
  → Manual review triggers for sudden volume spikes

ABUSE 3: Data harvesting via search
  ATTACK: Systematically query to extract the entire corpus
  → Iterate through all possible queries to enumerate documents
  → Deep pagination to access all results
  
  MITIGATION:
  → Rate limiting per user/IP
  → Max results per query (cap at 1,000)
  → Require authentication for search API
  → Monitor for systematic enumeration patterns
  → Captcha or token bucket for suspected harvesters
```

## Data Exposure

```
RISK 1: Cross-tenant data leakage
  → Multi-tenant index must enforce tenant isolation
  → Every query MUST include tenant_id filter
  → Enforced at platform level (not optional for callers)
  → Defense in depth: Tenant filter applied in coordinator AND on each shard

RISK 2: Autocomplete reveals existence of sensitive data
  → User types "salary" → suggestions include "salary negotiation leaked doc"
  → Autocomplete suggestions should be filtered by user's access permissions
  → Defense: Separate suggestion index per access level, or filter at query time

RISK 3: Facet counts reveal data distribution
  → "0 results in category: top_secret_project" confirms project exists
  → Facet counts on sensitive fields should be suppressed or fuzzed
  → Defense: Only show facets for categories the user has access to

RISK 4: Search logs contain PII
  → Users search for names, addresses, phone numbers
  → Query logs are gold mines for attackers
  → Defense: Hash or redact PII in logs, strict access control on log pipeline,
    auto-expire logs after retention period
```

## Privilege Boundaries

```
PRIVILEGE MODEL:

  SEARCH USER (product service calling search API):
  → Can: Query their tenant's index, index documents, delete documents
  → Cannot: Query other tenants, modify schema, access admin APIs

  TENANT ADMIN (team lead managing their search configuration):
  → Can: Update schema, manage aliases, configure relevance, view metrics
  → Cannot: Access other tenants, modify cluster settings, access raw data

  PLATFORM ADMIN (search platform team):
  → Can: Everything — cluster management, multi-tenant configuration, debugging
  → Audit: All admin actions logged with actor identity

  PRINCIPLE: Least privilege at every layer.
  → Query API: Mandatory tenant filter, scoped credentials
  → Admin API: Role-based access, audit logging
  → Data access: No direct shard access for non-platform users
```

## Why Perfect Security Is Impossible

```
REALITY:
  → Multi-tenant search on shared infrastructure has inherent timing side channels
    (query latency reveals index size, posting list length)
  → Full text search by definition exposes content to the search system
    (can't search encrypted data without decrypting)
  → Autocomplete and faceting inherently reveal data existence
  → Query logs contain sensitive user intent

PRAGMATIC APPROACH:
  → Strong authentication and tenant isolation (prevent unauthorized access)
  → Rate limiting and abuse detection (prevent scraping and DoS)
  → Audit logging (detect and investigate breaches)
  → Minimal retention (reduce exposure window)
  → Accept that the search platform team has access to all indexed data
    (trust boundary at the platform team level, not at the individual document level)
```

---

# Part 14: Evolution Over Time (CRITICAL FOR STAFF)

## V1: Naive Design

```
V1: SINGLE-NODE SEARCH

  Architecture:
  → One server with inverted index library (e.g., Lucene)
  → Source system pushes documents directly to the search server
  → Clients query the search server directly
  → No replication, no sharding, no pipeline

  Works for:
  → < 10M documents
  → < 100 QPS
  → Single product team
  → Acceptable to be unavailable during restarts

  Deployment:
  → One VM with 64GB RAM, 1TB SSD
  → Full index in memory → fast queries
  → Single process → simple operations
```

## What Breaks First

```
BREAK POINT 1: Single node can't hold entire index (~50M documents)
  → Index exceeds available RAM → page cache misses → disk I/O → latency spikes
  → SOLUTION: Shard the index across multiple nodes

BREAK POINT 2: Single node can't handle query load (~500 QPS)
  → CPU saturated by query execution → queue builds → timeout
  → SOLUTION: Add read replicas

BREAK POINT 3: Single node restart = total downtime
  → No redundancy → restart for maintenance = search outage
  → SOLUTION: Primary-replica architecture

BREAK POINT 4: Direct push indexing can't keep up (~1K mutations/sec)
  → Synchronous indexing blocks source systems
  → Burst writes cause backpressure on source
  → SOLUTION: Asynchronous indexing pipeline with queue

BREAK POINT 5: One team's traffic impacts another (~3 product teams)
  → No tenant isolation → one team's bulk import slows all queries
  → SOLUTION: Multi-tenant quotas and isolation

BREAK POINT 6: Schema changes require downtime
  → Changing analyzer or field type requires full reindex
  → Full reindex on live server = degraded performance
  → SOLUTION: Zero-downtime reindex with alias swapping
```

## V2: Intermediate Design

```
V2: SHARDED, REPLICATED, SINGLE-CLUSTER

  Architecture:
  → 20-50 nodes in one datacenter
  → Sharded inverted index (50-100 shards)
  → Primary + 2 replicas per shard
  → Dedicated coordinator nodes (stateless)
  → Async indexing pipeline with message queue
  → Cluster manager for shard allocation and failover
  → Multi-tenant support with per-tenant quotas

  Handles:
  → 500M documents
  → 10,000 QPS
  → 5 product teams
  → Rolling restarts without downtime
  → Automatic failover on node failure

  Limitations:
  → Single datacenter → single region latency for distant users
  → One cluster → operational ceiling (~200 nodes)
  → One failure domain → datacenter failure = total outage
  → Relevance tuning is cluster-wide (not per-tenant)
```

## V3: Long-Term Stable Architecture

```
V3: MULTI-REGION, MULTI-TENANT SEARCH PLATFORM

  Architecture:
  → 3 regional clusters (US-East, US-West, EU-West)
  → Each cluster: 100-200 nodes, 200-500 shards
  → Leader-follower replication across regions
  → Global indexing pipeline with regional consumers
  → Per-tenant relevance configuration
  → Tiered storage (hot/warm/cold)
  → Federated query support for cross-region data
  → Self-service tenant onboarding (schema, quotas, relevance)
  → Automated capacity management (scale up/down based on load)

  Handles:
  → 2+ billion documents
  → 100,000 QPS globally
  → 20+ product teams
  → Regional failure with automatic failover
  → Multi-year data retention with cost efficiency

  OPERATIONAL MODEL:
  → Platform team owns: Cluster management, capacity, reliability
  → Tenant teams own: Schema, relevance tuning, data quality
  → Clear ownership boundary at the API level
```

## How Incidents Drive Redesign

```
INCIDENT 1: "The Merge Storm" (V1 → V2 driver)
  
  What happened:
  → Bulk import of 5M documents during peak hours
  → Triggered aggressive segment merging
  → Merge I/O consumed all disk bandwidth
  → Query latency spiked to 10+ seconds
  → Search effectively down for 45 minutes
  
  Root cause: No separation between indexing and serving I/O
  Redesign: Dedicated indexing pipeline with rate limiting,
  merge throttling tied to query latency, separate indexing budget

INCIDENT 2: "The Noisy Neighbor" (V2 → V3 driver)
  
  What happened:
  → Team A ran a reindex job (500K docs/minute)
  → Consumed 80% of cluster indexing capacity
  → Team B's real-time product updates queued for 20 minutes
  → Team B's products not searchable → revenue impact
  
  Root cause: No per-tenant indexing quotas
  Redesign: Per-tenant indexing rate limits, priority queues,
  tenant-aware resource allocation

INCIDENT 3: "The Cross-Continental Query" (V2 → V3 driver)
  
  What happened:
  → European users experiencing 250ms search latency (vs 50ms target)
  → Root cause: All search traffic going to US-East cluster
  → 150ms network round-trip + 100ms query = 250ms total
  
  Root cause: Single-region deployment
  Redesign: Multi-region deployment with geo-routing,
  EU cluster for EU users

INCIDENT 4: "The Ghost Results" (ongoing concern)
  
  What happened:
  → Users found products that were sold out 6 hours ago
  → Indexing pipeline had a silent failure (consumer offset stuck)
  → No alerting on indexing lag
  → Duration: 6 hours before manual detection
  
  Root cause: No indexing freshness monitoring
  Redesign: Indexing lag SLO with automated alerting,
  periodic reconciliation between index and source of truth,
  "freshness" field in every search result for debugging
```

## Platform Code Deployment Strategy

```
DEPLOYING SEARCH PLATFORM CODE IS DIFFERENT FROM DEPLOYING APPLICATION CODE.

The search platform has three independently deployable components:
  1. Coordinator (stateless) — query parsing, scatter-gather, ranking
  2. Indexing pipeline (stateless) — document processing, text analysis
  3. Shard software (stateful) — index management, segment operations

Each has different deployment risk profiles.

COORDINATOR DEPLOYMENT (LOW RISK):
  → Stateless: No data to migrate, no sessions to drain
  → Rolling restart: Replace one coordinator at a time
  → Canary: Deploy to 1 coordinator, observe for 30 minutes
  → Ramp: 1 → 25% → 50% → 100% over 2 hours
  → Rollback: Replace with previous version (seconds)
  → Verification: P99 latency, error rate, partial result rate unchanged
  → Risk: Query parsing bug could return wrong results for all queries

PIPELINE DEPLOYMENT (MEDIUM RISK):
  → Stateless processing, but stateful queue offsets
  → Rolling restart: Replace one worker at a time
  → Risk: Text analysis bug could corrupt newly indexed documents
  → Canary: Deploy to 1 worker, monitor indexed document quality
  → Verification: Sample indexed documents, compare against expected analysis
  → Rollback: Replace with previous version, re-process queue from checkpoint
  → Critical: Bad pipeline code CANNOT be fixed by rollback alone —
    documents indexed by the bad version must be re-indexed

SHARD SOFTWARE DEPLOYMENT (HIGH RISK):
  → Stateful: Manages on-disk index, in-memory buffers, transaction logs
  → Rolling restart: One node at a time, with shard migration
  → Before restart: Migrate primary shards away from target node
    (promote replicas elsewhere, so target node has only replicas)
  → Restart node with new version → replicas sync from primaries
  → Canary: One node for 24 hours (observe shard health, query latency,
    merge behavior, disk I/O patterns)
  → Ramp: 1 node → 10% → 25% → 50% → 100% over 1 week
  → Rollback: Reverse the process (long — requires re-syncing shards)
  → Risk: Data format changes, segment compatibility, merge policy changes
  → Critical: Shard software versions must be backward-compatible
    across at least 2 versions (mixed-version cluster during rollout)

DEPLOYMENT GATES:
  → All unit tests pass
  → Integration tests with production-like data pass
  → Offline relevance evaluation shows no regression
  → Canary runs for minimum duration without alerts
  → No error budget violations in the past 24 hours
  → Human approval for shard software changes (high risk)
```

## Tenant Onboarding & Self-Service

```
ONBOARDING A NEW TENANT IS AN ORGANIZATIONAL AND TECHNICAL PROCESS.

SELF-SERVICE ONBOARDING WORKFLOW:

  STEP 1: INTAKE (Tenant team, 30 minutes)
    → Tenant fills out request form:
      - Data description (what are the documents?)
      - Expected scale (document count, QPS, growth rate)
      - Freshness requirement (seconds, minutes, hours)
      - SLO tier (Premium, Standard, Best-effort)
      - Schema (field names, types, which fields are searchable)
    → Automated validation: Schema compliance, reasonable scale estimates

  STEP 2: PROVISIONING (Automated, 5 minutes)
    → Create logical index within shared cluster
    → Allocate shards based on estimated scale
    → Configure per-tenant quotas (QPS, indexing rate, storage)
    → Generate API credentials scoped to tenant
    → Set up per-tenant monitoring dashboard
    → Create alias pointing to tenant's index

  STEP 3: DATA LOADING (Tenant team, hours to days)
    → Tenant uses bulk indexing API to load initial data
    → Rate-limited to avoid impacting other tenants
    → Platform provides progress dashboard
    → Validation: Sample search queries to verify indexing correctness

  STEP 4: INTEGRATION (Tenant team, days)
    → Tenant integrates search API into their product
    → Configures synonym dictionaries, boost factors
    → Tests with production-like queries
    → Platform team reviews for anti-patterns (expensive queries, missing filters)

  STEP 5: PRODUCTION (Ongoing)
    → Tenant configures their own relevance tuning via admin API
    → Tenant monitors their own SLO dashboard
    → Platform team monitors cluster-wide health
    → Quarterly review: Usage, cost, SLO compliance

OWNERSHIP BOUNDARY:

  PLATFORM TEAM OWNS:
  → Cluster infrastructure (nodes, disks, network)
  → Core software (coordinator, pipeline, shard manager)
  → Global SLOs (cluster-wide latency, availability)
  → Capacity planning and scaling
  → Incident response for infrastructure issues
  → Multi-tenant isolation and quota enforcement
  → Platform-level security (authentication, tenant isolation)

  TENANT TEAMS OWN:
  → Data quality (what documents to index, correctness)
  → Schema design (field selection, analyzers)
  → Relevance tuning (boost factors, synonyms, scoring)
  → Indexing pipeline integration (pushing data to search)
  → Product-level SLOs (how search fits into their product)
  → Query pattern optimization (avoiding expensive queries)

  WHY THIS BOUNDARY:
  → Platform team can't know what "relevant" means for each tenant's domain
  → Tenant team can't operate distributed infrastructure
  → Clear ownership prevents "works on my machine" for search quality
  → Platform team scales with infrastructure, not with tenant count

STAFF INSIGHT:
  The sign of a mature search platform is that new tenants can onboard
  WITHOUT a platform engineer being involved. Self-service tooling
  (schema builder, synonym editor, relevance dashboard) is not a "nice to have" —
  it's the mechanism that prevents the platform team from becoming a bottleneck
  as the organization grows from 5 to 50 tenant teams.
```

---

# Part 15: Alternatives & Explicit Rejections

## Alternative 1: Use the Primary Database for Search (PostgreSQL Full-Text Search)

```
WHY ATTRACTIVE:
  → No separate system to operate
  → Always consistent (queries against the source of truth)
  → Simpler architecture (one database, one query language)
  → PostgreSQL FTS is surprisingly capable for small datasets

WHY A STAFF ENGINEER REJECTS IT (at scale):
  → Full-text search load competes with transactional workload
    (a complex search query can block a product purchase)
  → PostgreSQL FTS lacks: distributed sharding, replica-based read scaling,
    configurable analyzers, tiered storage, faceting, multi-tenancy
  → At 10M+ documents and 1K+ QPS, PostgreSQL FTS latency degrades
  → No independent scaling: Can't scale reads and writes independently
  → No separation of concerns: Search team and database team are the same

  WHEN ACCEPTABLE:
  → < 1M documents
  → < 100 QPS
  → Single-tenant, single-team
  → Search is not a critical product path
```

## Alternative 2: Pre-Compute All Possible Query Results

```
WHY ATTRACTIVE:
  → O(1) query latency — just look up the precomputed result
  → No per-query computation → deterministic, fast, cheap
  → Works great for autocomplete (finite prefix space)

WHY A STAFF ENGINEER REJECTS IT (for general search):
  → COMBINATORIAL EXPLOSION: With 10M unique terms and multi-term queries,
    the number of possible queries is practically infinite
    (10M choose 2 = 50 trillion two-term combinations)
  → Can't pre-compute filters (price ranges, categories add more dimensions)
  → Can't pre-compute personalization (per-user results)
  → Storage: Even for top-1M queries, storing results = 1M × 20 results × 1KB = 20GB
    Plus invalidation when documents change

  WHEN ACCEPTABLE:
  → Autocomplete: Finite prefix space, pre-computable
  → "Top searches" / "trending searches": Small, cacheable set
  → Navigation-based search (category + sort): Pre-computable for common categories
```

## Alternative 3: Search-as-a-Service (Managed Elasticsearch / Algolia / Typesense)

```
WHY ATTRACTIVE:
  → No operational burden (managed service handles upgrades, scaling)
  → Fast to start (minutes to first search result)
  → Built-in dashboards, monitoring, relevance tuning
  → Competitive at small-to-medium scale

WHY A STAFF ENGINEER REJECTS IT (at Google-scale):
  → COST: At 2B documents and 100K QPS, managed service costs are 5-10× self-hosted
  → CONTROL: Can't customize analyzers, merge policies, or scoring at deep level
  → LATENCY: Data lives outside your infrastructure → cross-network round trips
  → MULTI-TENANCY: Limited tenant isolation controls
  → DATA RESIDENCY: May not support required regions or compliance certifications
  → VENDOR LOCK-IN: Migrating 2B documents between providers takes weeks

  WHEN ACCEPTABLE:
  → < 100M documents
  → < 10K QPS
  → Team doesn't have search infrastructure expertise
  → Speed of development is more important than cost optimization
  → Acceptable vendor dependency
```

---

# Part 16: Interview Calibration (Staff Signal)

## How Interviewers Probe This System

```
PROBE 1: "How do you handle a query that matches millions of documents?"
  Testing: Understanding of retrieval pipeline, top-K optimization,
  and why scanning all matches is unnecessary.

PROBE 2: "What happens when one shard is slow?"
  Testing: Partial failure handling, tail latency management,
  trade-off between completeness and latency.

PROBE 3: "How do you ensure freshness while maintaining query performance?"
  Testing: Understanding of segment architecture, refresh/flush trade-offs,
  and the tension between write throughput and query latency.

PROBE 4: "You have 10 teams using this system. How do you prevent
          one team from impacting others?"
  Testing: Multi-tenancy design, resource isolation, quota management,
  and organizational ownership boundaries.

PROBE 5: "How do you roll out a new relevance model without breaking search?"
  Testing: Canary/shadow deployment, A/B testing for relevance,
  rollback strategy, and understanding that "better" is measurable.

PROBE 6: "Walk me through what happens when a user types 'r-u-n-n-i-n-g' 
          one character at a time."
  Testing: Autocomplete design, prefix index vs full search,
  latency budget for typeahead, debouncing strategy.

PROBE 7: "How do you migrate the schema for 2 billion documents
          without downtime?"
  Testing: Zero-downtime migration, alias swapping, dual-write strategy,
  and understanding of the operational risk.
```

## Common L5 Mistakes

```
MISTAKE 1: "I'll use Elasticsearch"
  → Naming a technology is not designing a system.
  → The interviewer wants to know HOW it works, not what brand to use.
  → Mention concepts (inverted index, BM25, segment merge) not products.

MISTAKE 2: Ignoring the write path
  → Spending 40 minutes on query serving, 0 on indexing
  → The write path is where most operational complexity lives
  → Staff Engineers design both paths and their interaction

MISTAKE 3: "Shard by category" (or other content-based partitioning)
  → Leads to uneven shard sizes (fashion has 10× more products than tools)
  → Hot shards for popular categories
  → Can't serve cross-category queries without fan-out anyway
  → Hash-based partitioning is the correct default

MISTAKE 4: Not addressing partial failure
  → "If a shard is down, the query fails"
  → L5 answer: Return partial results, don't fail the whole query
  → Users tolerate incomplete results; they don't tolerate errors

MISTAKE 5: "Make it strongly consistent"
  → Search is a derived view — eventual consistency is correct
  → Strong consistency between index and source requires distributed
    transactions → prohibitive latency
  → State: "The index is eventually consistent, and here's why that's fine
    for this use case — users tolerate 1-2 second staleness."

MISTAKE 6: No capacity estimation
  → Jumping to architecture without knowing QPS, corpus size, latency budget
  → Staff Engineers start with scale to determine whether to shard,
    how many shards, how many replicas
```

## Staff-Level Answers

```
STAFF ANSWER 1: "The search index is a derived, denormalized read projection
  of the source of truth. Because it's derived, we can make aggressive trade-offs:
  eventual consistency, approximate results, and tiered freshness — trade-offs
  we'd never make on the source of truth itself."

STAFF ANSWER 2: "I'd implement a three-phase ranking pipeline: BM25 retrieval
  on the inverted index for cheap candidate generation, feature-based re-ranking
  on the top 1,000 for quality, and business rules on the top 100 for policy.
  Each phase has its own latency budget, and each can be independently bypassed
  under degradation."

STAFF ANSWER 3: "Multi-tenancy is the hardest part of this system. Not because
  of data isolation — that's a filter. But because of resource isolation:
  one tenant's reindex shouldn't spike another tenant's query latency.
  I'd implement per-tenant indexing quotas, per-tenant query QPS limits,
  and tenant-aware shard routing so that tenant queries don't fan out
  to shards that don't hold their data."

STAFF ANSWER 4: "The biggest operational risk is silent staleness. A system
  that returns results is 'up,' but if those results are 6 hours stale,
  it's effectively broken. I'd monitor indexing lag as a first-class SLO,
  with per-tenant freshness dashboards and automated alerts."
```

## Example Phrases a Staff Engineer Uses

```
"Let me first understand the read:write ratio, because that fundamentally
changes the architecture."

"The inverted index is the right data structure because query time is
proportional to result set size, not corpus size."

"I'm designing for eventual consistency because the search index is a
derived view. The question is: what's the acceptable staleness bound?"

"I'd return partial results rather than a timeout. Users tolerate missing
a few results; they don't tolerate a blank page."

"Multi-tenancy isn't just about data isolation — it's about resource
isolation. One tenant's bulk import shouldn't spike another's P99."

"Let me walk through a failure scenario: what happens when 2 of 12
shards are slow? The system returns results from the other 10 and
signals incompleteness to the client."

"Schema migration is the most dangerous operation. I'd build the new
index alongside the old one, dual-write, validate, then swap the alias.
At no point is the old index unavailable."

"The merge policy is one of the most important tuning knobs.
Too aggressive and we waste I/O. Too lazy and query latency increases
because we're searching too many segments."
```

---

# Part 17: Diagrams (MANDATORY)

## Diagram 1: Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SEARCH SYSTEM ARCHITECTURE                               │
│                                                                             │
│                      ┌──────────────┐                                       │
│                      │   Clients    │                                       │
│                      └──────┬───────┘                                       │
│                             │                                               │
│                      ┌──────▼───────┐                                       │
│                      │ Query Gateway │ ← Auth, rate limit, tenant routing   │
│                      └──────┬───────┘                                       │
│                             │                                               │
│               ┌─────────────┼─────────────┐                                 │
│               ▼                           ▼                                 │
│     ┌────────────────-─┐         ┌─────────────────┐                        │
│     │ Query Coordinator│         │Indexing Pipeline│                        │
│     │   (stateless)    │         │   (stateless)   │                        │
│     │                  │         │                 │                        │
│     │ Parse → Plan     │         │ Validate→Analyze│                        │
│     │ Scatter → Gather │         │ Route → Write   │                        │
│     │ Rank → Respond   │         │                 │                        │
│     └────────┬─────────┘         └────────┬────────┘                        │
│              │                            │                                 │
│              │         ┌──────────────────┤                                 │
│              │         │  Message Queue   │                                 │
│              │         └────────┬─────────┘                                 │
│              │                  │                                           │
│              ▼                  ▼                                           │
│     ┌────────────────────────────────────────┐                              │
│     │              SHARD LAYER               │                              │
│     │                                        │                              │
│     │  ┌─────┐ ┌─────┐ ┌─────┐     ┌─────┐   │                              │
│     │  │ S0  │ │ S1  │ │ S2  │ ... │ S249│   │                              │
│     │  │P R R│ │P R R│ │P R R│     │P R R│   │                              │
│     │  └─────┘ └─────┘ └─────┘     └─────┘   │                              │
│     │                                        │                              │
│     │  Each shard: Inverted index + Stored   │                              │
│     │  fields + Doc values + TX log          │                              │
│     └────────────────────────────────────────┘                              │
│                                                                             │
│     ┌─────────--─────┐        ┌──────────────┐                              │
│     │Cluster Manager │        │ Config Store │                              │
│     │(leader-elected)│        │(ZK / etcd)   │                              │
│     └──────────────--┘        └──────────────┘                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 2: Query Execution Flow (Timing)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    QUERY EXECUTION TIMELINE                                 │
│                                                                             │
│   TIME   COMPONENT          ACTION                                          │
│   ─────  ─────────────────  ───────────────────────────────────────────     │
│   0ms    Client             Send query: "red running shoes"                 │
│   1ms    Gateway            Auth + rate limit check                         │
│   2ms    Coordinator        Parse query, expand synonyms, spell check       │
│   5ms    Coordinator        Plan: select all 250 shards                     │
│   6ms    Coordinator        SCATTER: fan out to 250 shard replicas          │
│          │                                                                  │
│          │  ┌─ Shard 0:   Lookup postings, intersect, score → 15ms          │
│          │  ├─ Shard 1:   Lookup postings, intersect, score → 12ms          │
│          │  ├─ Shard 2:   Lookup postings, intersect, score → 18ms          │
│          │  ├─ ...                                                          │
│          │  ├─ Shard 249: Lookup postings, intersect, score → 22ms          │
│          │  └─ (all shards execute IN PARALLEL)                             │
│          │                                                                  │
│   28ms   Coordinator        GATHER: All 250 responses received              │
│   30ms   Coordinator        Merge top-20 from each shard (priority queue)   │
│   32ms   Coordinator        ML re-rank top-100 candidates                   │
│   34ms   Coordinator        Apply business rules on top-20                  │
│   35ms   Coordinator        Compute facet aggregations                      │
│   36ms   Coordinator        Format response                                 │
│   37ms   Client             Receive response                                │
│                                                                             │
│   TOTAL: 37ms (P50)                                                         │
│                                                                             │
│   BUDGET ALLOCATION:                                                        │
│   ├── Gateway overhead:     1ms   (2.7%)                                    │
│   ├── Query parsing:        4ms   (10.8%)                                   │
│   ├── Shard execution:      22ms  (59.5%) ← THIS IS THE BOTTLENECK          │
│   ├── Merge + re-rank:      8ms   (21.6%)                                   │
│   └── Response formatting:  2ms   (5.4%)                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 3: Failure Propagation — Slow Shard

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FAILURE: SLOW SHARD → PARTIAL RESULTS                    │
│                                                                             │
│   T=0ms   Query arrives at coordinator                                      │
│           Scatter to 250 shards                                             │
│                                                                             │
│   T=25ms  248 shards have responded ✓                                       │
│           Shard 42: No response yet (slow — segment merge in progress)      │
│           Shard 99: No response yet (slow — GC pause)                       │
│                                                                             │
│   T=50ms  Shard 99 responds ✓ (recovered from GC)                           │
│           Shard 42: Still no response                                       │
│                                                                             │
│   T=80ms  Per-shard timeout: 100ms approaching                              │
│           Coordinator decision: Send speculative retry to Shard 42 replica  │
│                                                                             │
│   T=95ms  Shard 42 replica responds ✓                                       │
│                                                                             │
│   T=100ms All 250 results collected                                         │
│           Merge and respond to client                                       │
│                                                                             │
│   ALTERNATIVE SCENARIO (replica also slow):                                 │
│                                                                             │
│   T=100ms Per-shard timeout reached for Shard 42                            │
│           Coordinator: Return results from 249/250 shards                   │
│           Response includes: partial_results=true, missing_shards=[42]      │
│           User sees results — slightly incomplete but functional            │
│                                                                             │
│   KEY INSIGHT:                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  The coordinator's job is to PROTECT users from infrastructure      │   │
│   │  problems. A slow shard is the coordinator's problem, not the       │   │
│   │  user's problem. Return the best results available within the       │   │
│   │  latency budget, and signal incompleteness metadata for debugging.  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 4: Evolution Over Time

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SEARCH SYSTEM EVOLUTION                                  │
│                                                                             │
│   V1: SINGLE NODE                     │  LIMITS:                            │
│   ┌─────────────┐                     │  < 10M docs, < 100 QPS              │
│   │ App Server  │                     │  Single point of failure            │
│   │ ┌─────────┐ │                     │                                     │
│   │ │  Index  │ │                     │  BREAKS: Index exceeds memory,      │
│   │ └─────────┘ │                     │  QPS exceeds single CPU             │
│   └─────────────┘                     │                                     │
│         │                                                                   │
│         ▼                                                                   │
│   V2: SINGLE CLUSTER                  │  LIMITS:                            │
│   ┌────────────────────────────┐      │  < 500M docs, < 10K QPS             │
│   │   Coordinator  Coordinator │      │  Single region                      │
│   │       │            │       │      │                                     │
│   │   ┌───┴───┐    ┌───┴───┐   │      │  BREAKS: Cross-region latency,      │
│   │   │ Shards│    │ Shards│   │      │  multi-team resource contention     │
│   │   │ + Repl│    │ + Repl│   │      │                                     │
│   │   └───────┘    └───────┘   │      │                                     │
│   │      Message Queue         │      │                                     │
│   │      Pipeline Workers      │      │                                     │
│   └────────────────────────────┘      │                                     │
│         │                                                                   │
│         ▼                                                                   │
│   V3: MULTI-REGION PLATFORM           │  HANDLES:                           │
│   ┌──────────┐ ┌──────────┐ ┌──────┐  │  2B+ docs, 100K+ QPS                │
│   │ US-East  │ │ US-West  │ │  EU  │  │  Multi-region failover              │
│   │ Cluster  │ │ Cluster  │ │Clus- │  │  20+ tenant teams                   │
│   │          │ │          │ │ -ter │  │  Tiered storage                     │
│   │ 100 nodes│ │ 100 nodes│ │  80  │  │  Per-tenant SLOs                    │
│   │          │ │          │ │nodes │  │                                     │
│   └──────────┘ └──────────┘ └──────┘  │                                     │
│        ↕            ↕           ↕     │                                     │
│   ┌────────────────────────────────┐  │                                     │
│   │  Global Indexing Pipeline      │  │                                     │
│   │  Cross-Region Replication      │  │                                     │
│   │  Federated Query Support       │  │                                     │
│   └────────────────────────────────┘  │                                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 18: Brainstorming, Exercises & Redesigns

## "What If X Changes?" Questions

```
1. What if query volume increases 10× overnight (viral event)?
   → Query cache absorbs repeated queries (popular search terms repeat)
   → Coordinator auto-scales horizontally (stateless)
   → If shards are overloaded: Shed analytics queries, increase replicas
   → Medium-term: Add read replicas, increase cache TTL (tolerate more staleness)

2. What if document corpus grows from 2B to 20B?
   → Shard count increases: 250 → 2,500 shards
   → Scatter-gather to 2,500 shards → coordinator bottleneck
   → SOLUTION: Two-level routing — partition by tenant, then by content
   → Tenant queries only fan out to their shard subset (not all 2,500)
   → Cold tier becomes essential (80% of documents are rarely accessed)

3. What if freshness requirement changes from seconds to milliseconds?
   → Need search-on-write: Documents searchable as they enter the buffer
   → No waiting for refresh/flush cycle
   → Cost: More complex concurrency (reads and writes on same in-memory buffer)
   → Lucene's NRT reader provides this: Open reader from buffer without flush

4. What if you need to support vector/semantic search in addition to lexical?
   → Hybrid retrieval: BM25 + ANN (approximate nearest neighbor)
   → Add vector index (HNSW graph) alongside inverted index
   → Phase 1 becomes: BM25 candidates ∪ ANN candidates → combined candidate set
   → Phase 2 re-ranks combined candidates with unified scoring
   → Storage impact: Vector embeddings (768 floats × 4 bytes = 3KB per doc)
     → 2B docs × 3KB = 6TB additional storage

5. What if one tenant has 10× the QPS of all others combined?
   → Dedicated shard allocation for the large tenant
   → Separate coordinator pool (isolate scatter-gather load)
   → Potentially dedicated cluster if isolation requirements are strict
   → Per-tenant query result caching (high QPS = high cache hit rate)

6. What if you need to support real-time relevance updates (e.g., trending boosts)?
   → Trending signals change every minute — can't rebuild index
   → SOLUTION: External signal service queried at ranking time (Phase 2)
   → Trending scores fetched per-query for top-K candidates (100 lookups)
   → Not in the inverted index (too dynamic, would require constant reindexing)
```

## Redesign Under New Constraints

```
CONSTRAINT 1: Cost must decrease 60% while maintaining current SLOs

  Approach:
  → Aggressive tiered storage (90% of docs to cold tier)
  → Reduce replicas to 1 (accept lower fault tolerance)
  → Increase query cache TTL to 10 minutes (accept staleness)
  → Reduce refresh interval to 30 seconds (accept more indexing lag)
  → Use smaller, storage-optimized nodes instead of compute-optimized
  → Trade: Slower P99 for cold-tier queries, lower fault tolerance,
    staler results — all within SLO if SLOs are relaxed slightly

CONSTRAINT 2: Add document-level access control (every doc has an ACL)

  Approach:
  → ACLs stored as indexed fields on each document
  → Query-time security filter: "user_id IN acl_list OR acl = public"
  → Challenge: ACL lists can be large (1000 users per doc) → large postings
  → Optimization: Group-based ACLs (index group membership, not individual users)
  → Cost: Every query gets an additional filter → 10-20% slower
  → Cache impact: Query cache keyed by (query + user_id) → lower hit rate
  → Trade: Significant complexity and performance cost for security guarantee

CONSTRAINT 3: Latency budget reduced from 200ms to 50ms (P99)

  Approach:
  → Reduce shard count (fewer shards = less scatter-gather overhead)
  → Keep entire working set in memory (no disk reads)
  → Remove ML re-ranking from hot path (BM25-only, re-rank async)
  → Speculative retries on ALL shard requests (hedge at P50 latency)
  → Pre-warm filter caches aggressively
  → Trade: Higher memory cost, less sophisticated relevance, more network
    traffic (speculative retries)
```

## Failure Injection Exercises

```
EXERCISE 1: Kill 3 nodes simultaneously during peak query load
  OBSERVE:
  → How many shards lose primary? How many are under-replicated?
  → Does query latency spike? For how long?
  → Does the cluster manager promote replicas correctly?
  → How long until full replication is restored?

EXERCISE 2: Inject 500ms latency on network between coordinators and shards
  OBSERVE:
  → Do coordinators return partial results?
  → Does speculative retry kick in?
  → Is the user experience degraded or maintained?
  → Do circuit breakers activate?

EXERCISE 3: Corrupt the transaction log on one shard primary
  OBSERVE:
  → Does the shard detect the corruption?
  → Does it stop accepting writes?
  → Is the shard rebuilt from a replica?
  → How much data is lost (if any)?

EXERCISE 4: Flood the indexing pipeline with 100× normal write volume
  OBSERVE:
  → Does the queue grow unboundedly?
  → Does backpressure kick in?
  → Are query latencies affected?
  → Is per-tenant rate limiting effective?

EXERCISE 5: Deploy a bad relevance model that makes all results irrelevant
  OBSERVE:
  → Is there automated detection? (Relevance metrics should degrade)
  → How quickly can you roll back to the previous model?
  → Is there a canary process that catches this before full rollout?
```

## Trade-Off Debates

```
DEBATE 1: Single large cluster vs multiple small clusters
  LARGE CLUSTER:
  → Simpler operations (one cluster to manage)
  → Better resource utilization (shared capacity)
  → Single shard map, single metadata store
  → Risk: Blast radius is the entire platform
  
  MULTIPLE SMALL CLUSTERS:
  → Tenant isolation (dedicated clusters for critical tenants)
  → Independent upgrades (upgrade one cluster at a time)
  → Smaller blast radius per cluster
  → Risk: More clusters to operate, potential resource waste
  
  STAFF DECISION: Shared cluster with logical isolation for most tenants,
  dedicated clusters for tenants with extreme SLAs or regulatory requirements.

DEBATE 2: Push-based vs pull-based indexing
  PUSH (source pushes to search):
  → Lower latency (no polling interval)
  → Source controls timing
  → Risk: Source can overwhelm search pipeline
  
  PULL (search pulls from source):
  → Search controls ingestion rate (built-in backpressure)
  → Can pause pulling during maintenance
  → Risk: Polling interval adds latency, must track cursor/checkpoint
  
  STAFF DECISION: Push into a message queue (decouples source from search),
  search pipeline pulls from queue at controlled rate.

DEBATE 3: Index-time vs query-time synonym expansion
  INDEX-TIME:
  → "shoe" indexed as ["shoe", "sneaker", "footwear"]
  → Larger index (3× tokens for synonym-heavy fields)
  → Changing synonyms requires reindex
  → Query is simpler (just look up "shoe")
  
  QUERY-TIME:
  → Query for "shoe" expanded to "shoe OR sneaker OR footwear"
  → Normal index size
  → Changing synonyms takes effect immediately
  → Query is more complex (3× posting list lookups)
  
  STAFF DECISION: Query-time expansion for flexibility. Index-time
  only when query-time expansion creates unacceptable latency
  (very high-cardinality synonym lists).

DEBATE 4: Exact vs approximate total hit counts
  EXACT:
  → Must visit every posting in every matching shard
  → Cost: O(total_matching_documents) — prohibitive for broad queries
  → Value: Users rarely care about exact count past "thousands"
  
  APPROXIMATE:
  → Count up to 10,000, estimate beyond
  → Cost: O(10,000) — bounded, fast
  → Trade: "About 1.2 million results" instead of "1,234,567 results"
  
  STAFF DECISION: Approximate by default (almost always sufficient),
  exact on explicit request (with warning about latency impact).
```

---

# Summary

This chapter has covered the design of a Search / Indexing System at Staff Engineer depth, addressing every aspect from the foundational mechanics of inverted indexes through multi-region deployment, multi-tenancy, and system evolution.

### Key Staff-Level Takeaways

```
1. Search is infrastructure, not a feature.
   Every product team depends on it. Treat it with database-tier criticality.

2. The write path is harder than the read path.
   Indexing, segment merging, replication, and freshness management consume
   most of the design and operational effort.

3. The index is derived — exploit that.
   Eventual consistency, approximate results, and tiered freshness are
   acceptable trade-offs because the source of truth lives elsewhere.

4. Multi-tenancy is the Staff differentiator.
   Data isolation is table stakes. Resource isolation — preventing one
   tenant from impacting another — is what separates L5 from L6.

5. Silent staleness is worse than downtime.
   Monitor indexing lag as a first-class SLO. A system that returns
   stale results is effectively broken but looks healthy.

6. Partial results beat timeouts.
   Return results from 249/250 shards rather than timing out.
   Users tolerate incomplete results; they don't tolerate blank pages.

7. Evolution, not revolution.
   V1 → V2 → V3 progression driven by real breakpoints and incidents.
   Don't build V3 on day one. Build V1, learn what breaks, iterate.
```

### How to Use This Chapter in an Interview

```
OPENING (0-5 min):
  → Clarify: What's the corpus? What's the QPS? What's the freshness requirement?
  → State: "The search index is a derived view of the source of truth,
    which means I can make aggressive trade-offs on consistency and durability."

FRAMEWORK (5-15 min):
  → Requirements: Full-text search, autocomplete, multi-tenant, freshness SLO
  → Scale: 2B docs, 12K QPS peak, 300 mutations/sec
  → NFRs: P99 < 200ms, eventual consistency acceptable, 99.95% availability

ARCHITECTURE (15-30 min):
  → Draw: Clients → Gateway → Coordinators → Shards (with replicas)
  → Draw: Source → Queue → Pipeline → Shards
  → Explain: Stateless coordinators, stateful shards, segment architecture

DEEP DIVES (30-45 min):
  → When asked about failure: Partial results, circuit breakers, degradation
  → When asked about scale: Sharding, tiered storage, multi-region
  → When asked about relevance: Multi-phase ranking pipeline
  → When asked about operations: Schema migration, reindex strategy, monitoring
```
