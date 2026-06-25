# Chapter 75: Typeahead / Autocomplete (L5)

> "Design an autocomplete system" is the single most common L5 warmup question.
> It appears constantly as a 30-minute opener before a harder question, or as the main
> question for candidates who need a more structured assessment. The trap is treating it
> as trivial: "just use a trie." A complete L5 answer requires a trie explanation, a
> discussion of why the production answer is a prefix hash in Redis, an offline aggregation
> pipeline to build suggestion data, and a serving path that hits sub-100ms p99 latency.
> This chapter walks through all four.

---

## AT A GLANCE

```
╔══════════════════════════════════════════════════════════════════════════════╗
║              CHAPTER 75 — TYPEAHEAD / AUTOCOMPLETE (L5) AT A GLANCE        ║
╠═══════════════════════════╦══════════════════════════════════════════════════╣
║  System                   ║  Core Design Choices                            ║
╠═══════════════════════════╬══════════════════════════════════════════════════╣
║  Data structure           ║  Prefix hash table (Redis ZSETs)               ║
║                           ║  Key = prefix, Value = sorted top-K suggestions ║
╠═══════════════════════════╬══════════════════════════════════════════════════╣
║  Build pipeline           ║  Daily batch job over query logs               ║
║                           ║  → aggregation → score → populate Redis        ║
╠═══════════════════════════╬══════════════════════════════════════════════════╣
║  Serving path             ║  Client debounce → API server → Redis lookup   ║
║                           ║  Return top 5-10 suggestions in < 100ms p99    ║
╠═══════════════════════════╬══════════════════════════════════════════════════╣
║  Latency budget           ║  Client debounce: 100-150ms                    ║
║                           ║  Network RTT: 20-50ms (CDN/PoP proximity)      ║
║                           ║  Redis lookup: 1-5ms                           ║
║                           ║  Total: < 100ms p99 at the server              ║
╠═══════════════════════════╬══════════════════════════════════════════════════╣
║  Storage estimate         ║  10M unique prefixes × 5 suggestions = 50M     ║
║                           ║  entries in Redis. ~5-20 GB Redis memory.      ║
╠═══════════════════════════╬══════════════════════════════════════════════════╣
║  Scale targets            ║  10B queries/day (Google scale)                ║
║                           ║  100M QPS suggestion requests                  ║
╠═══════════════════════════╬══════════════════════════════════════════════════╣
║  Key insight              ║  Prefix hash trades memory for speed.          ║
║                           ║  Each prefix is a separate key → O(1) lookup.  ║
╠═══════════════════════════╬══════════════════════════════════════════════════╣
║  Scope OUT (L5)           ║  Personalization, fuzzy/typo matching,         ║
║                           ║  multi-language, federated search              ║
╠═══════════════════════════╬══════════════════════════════════════════════════╣
║  Staff level (Ch102)      ║  Compressed trie, offline Spark pipeline,      ║
║                           ║  real-time trending, typo correction, sharding ║
╚═══════════════════════════╩══════════════════════════════════════════════════╝
```

**Parts in this chapter:**
- Part 1: The Problem — What Autocomplete Actually Means
- Part 2: Requirements
- Part 3: High-Level Design
- Part 4: API Design
- Part 5: Database Schema
- Part 6: The Trie — Core Data Structure
- Part 7: The Production Answer — Prefix Hash Table in Redis
- Part 8: Building the Data — Offline Aggregation Pipeline
- Part 9: The Serving Layer — Sub-100ms
- Part 10: Scaling
- Part 11: Real-Time Trending Updates
- Part 12: Interview Application
- Part 13: Pre-Interview Drill

---

## Why This Chapter Matters

Typeahead appears in virtually every search-adjacent product:
- Google / Bing / DuckDuckGo: search box autocomplete
- Amazon / eBay: product search autocomplete
- YouTube / Spotify / Netflix: content search
- Twitter/X: user and hashtag autocomplete
- IDE code completion (a specialized variant)
- Address and location autocomplete (Google Maps)

As an interview question, it is often used as a **warmup** (30 minutes) before a harder
question, or as the main question when an interviewer wants to assess how you handle a
problem that looks simple but has depth. Many L5 candidates answer "just use a trie" and
get probed into difficulty when asked: "How do you store a trie for 1 billion queries?
How do you update it when new trending queries emerge? How do you serve it at 100,000
requests per second with p99 < 100ms?"

This chapter gives you the complete L5 answer: the trie as the conceptual foundation,
the prefix hash table as the production implementation, an offline aggregation pipeline
to build and update the data, and a serving layer that hits the latency target.

---

## Part 1: The Problem — What Autocomplete Actually Means

### 1.1 The User Experience

A user types in a search box. After each keystroke, a dropdown of suggestions appears
within milliseconds. The user sees:

```
  User types: "sta"
  
  Suggestions appear immediately:
  ┌─────────────────────────────┐
  │  🔍  stack overflow         │
  │  🔍  star wars              │
  │  🔍  stanford university    │
  │  🔍  starbucks menu         │
  │  🔍  stardew valley         │
  └─────────────────────────────┘
  
  User types: "stac"
  
  ┌─────────────────────────────┐
  │  🔍  stack overflow         │
  │  🔍  stack exchange         │
  │  🔍  stacking cups          │
  │  🔍  stackblitz             │
  │  🔍  stack overflow jobs    │
  └─────────────────────────────┘
```

The dropdown must:
- Appear within 100ms of the keystroke (imperceptible to humans)
- Show the most popular / most relevant suggestions for the prefix
- Update with each new character
- Work for any prefix in any language (at L5: English only)

### 1.2 The Two Hard Sub-Problems

The interview question has exactly two hard sub-problems:

**Problem 1: Data Structure for Fast Prefix Lookup**
Given a prefix like "stac", find all queries that start with "stac" — fast enough
to return results before the user types the next character.

Naive approach: `SELECT * FROM queries WHERE query LIKE 'stac%'` — SQL table scan
is O(N) over all queries. Unacceptable for sub-100ms at 100M rows.

Right approach: pre-index by prefix. Store the top-K suggestions for every possible
prefix, retrievable in O(1).

**Problem 2: Ranking Suggestions by Relevance**
When a user types "st", there are tens of thousands of queries starting with "st".
Which 5-10 do you show? You must score and rank them.

At L5: frequency-based scoring. The most-searched queries for this prefix get shown.
"stackoverflow" gets more searches than "stalling economy", so it ranks higher.

### 1.3 Scale Numbers to Know

For a Google-scale search engine (memorize for the interview):

| Metric | Number | Why It Matters |
|--------|--------|----------------|
| Queries per day (Google) | 8.5 billion | Sets size of query log |
| Unique queries | ~15% of daily queries | Many queries repeat |
| Unique prefixes to index | ~1-2 billion | Storage sizing for prefix table |
| Suggestion requests/second | ~100M QPS | Must handle every keystroke |
| Target latency (p99) | < 100ms total | Including network |
| Suggestions shown to user | 5-10 | Only top-K needed per prefix |
| Typical prefix length | 3-6 characters | Short prefixes are most common |

For a medium platform (your interview scope):
- 100M queries per day
- 10M unique prefix strings to index
- 10,000-50,000 suggestion requests per second
- p99 server latency: < 20ms (network adds another 30-50ms)

### 1.4 The User Journey (End to End)

Understanding the full journey reveals all the components you must design:

```
USER JOURNEY
=============

  QUERY LOGGING PATH (write side):
  1. User submits a search query: "stack overflow tutorials"
  2. Client sends the completed query to your logging service
  3. Query is appended to a query log (Kafka topic or log file)
  4. Daily batch job reads query logs → counts frequencies → scores → writes to Redis

  SUGGESTION SERVING PATH (read side):
  1. User is typing in the search box: "stac"
  2. Client waits 100ms (debounce) before sending request
  3. Client sends: GET /api/v1/suggest?q=stac
  4. API server receives request
  5. API server queries Redis: key = "stac" → returns top-5 sorted set
  6. API server returns JSON: [suggestions array]
  7. Client renders dropdown before user types next character

  THE CONNECTION:
  The offline batch pipeline (Step 4 write side) populates the Redis store
  that the serving layer (Steps 5-6 read side) queries. The two sides are
  completely decoupled.
```

### 1.5 Brainstorming Q&A — Part 1

**Q: How often does the client send a request — every keystroke?**

Without optimization, yes. But that is wasteful and causes visible flicker.
The standard pattern: **debouncing**. The client waits until the user has not
typed for 100-150 milliseconds before sending the API request. If the user types
"s", "t", "a", "c" in quick succession (< 100ms between each), only one request
fires — for "stac". This reduces API calls by 3-5× compared to every keystroke,
with no perceptible delay.

Second optimization: **prefix caching in the browser**. If the user types "stac"
and receives suggestions, and then types "stack" — the client can filter the
already-fetched "stac" suggestions locally without a new API call. This works
because "stack" suggestions are a subset of "stac" suggestions. This reduces API
calls further by ~40%.

**Q: What counts as a "query" for the purposes of this system?**

Good clarifying question for the interview. Typically:
- Completed searches (user pressed Enter or clicked a result) — full signal
- Abandoned queries (user stopped typing) — partial signal, used with lower weight
- Clicks on suggestions — strong signal (user confirmed this was what they wanted)

For L5, simplify: only count completed searches. Each submission adds one unit of
frequency to the query in the logs.

**Q: Does autocomplete need to handle multi-word queries?**

Yes — real autocomplete handles multi-word queries ("how to make pasta", "new york
times"). The prefix matching applies to the entire query string, not just the first
word. "how to" would show suggestions starting with "how to": "how to make pasta",
"how to draw", "how to lose weight". This doesn't change the architecture — the prefix
is the first N characters of the entire query string.

---

## Part 2: Requirements

### 2.1 Functional Requirements

- Given a prefix of 1+ characters, return the top-K suggestions (K = 5-10)
- Suggestions are ordered by popularity (most searched first)
- Suggestions are prefix-matched (every suggestion starts with the query prefix)
- Suggestions update within 24 hours of trending query frequency changes
- Users can type their full query and submit (the autocomplete is additive, not required)

### 2.2 Non-Functional Requirements

| Requirement | Target | Why |
|-------------|--------|-----|
| Server latency (p99) | < 20ms | Total p99 including network < 100ms |
| Server latency (p50) | < 5ms | Typical case feels instant |
| Availability | 99.9% | Search degrades gracefully without autocomplete |
| Freshness | 24 hours | Suggestions reflect yesterday's trends |
| Accuracy | Top-5 in the true top-10 | Approximate ranking is fine |
| QPS | 50,000+ | Peak suggestion requests per second |
| Storage | < 30 GB | Must fit in Redis RAM |

**Why 99.9% and not 99.99%?**
Autocomplete is a non-critical enhancement. If it goes down, users can still
search — they just don't get suggestions. It's acceptable to serve stale or
empty suggestions rather than block the search experience. This makes it a good
candidate for graceful degradation (return empty array if Redis is unavailable).

### 2.3 Clarifying Questions for the Interview

1. "Is this for search queries, or product names, or both?"
2. "How many suggestions to show? (default: 5)"
3. "Are suggestions global (same for everyone) or personalized per user?"
4. "How fresh must suggestions be — real-time, hourly, or daily?"
5. "English only, or multi-language?"

At L5: global suggestions, 5 results, daily freshness, English only.

### 2.4 What We Are NOT Building (Scope Boundaries)

- **Not in scope**: Personalized suggestions (user's own history), typo correction,
  multi-language, federated search (combining results from multiple backends)
- **Simplified**: Freshness is daily (not real-time trending). Ranking is pure
  frequency (not click-through rate, seasonal signals, or ML ranking).

---

## Part 3: High-Level Design

### 3.1 Three Main Components

```
HIGH-LEVEL ARCHITECTURE
=========================

  WRITE SIDE (offline — runs daily):

  User Searches
       │ (query log event per search)
       ▼
  [Query Log] ←── Kafka topic / log files
       │
       ▼
  [Batch Aggregation Job] (daily, runs overnight)
       │ Counts query frequency per prefix
       │ Scores and ranks top-K per prefix
       ▼
  [Redis Cluster] ←── Prefix store: key="stac", value=[(q1, score1), ...]

  READ SIDE (online — real-time):

  User types "stac" in search box
       │ (after 100ms debounce)
       ▼
  [Client App]
       │ GET /suggest?q=stac
       ▼
  [API Server] (stateless, N replicas)
       │ ZREVRANGE "stac" 0 4 WITHSCORES
       ▼
  [Redis Cluster] → top-5 suggestions in < 5ms
       │
       ▼
  [API Server] → JSON response
       │
       ▼
  [Client App] → renders dropdown
```

### 3.2 Why These Components?

| Component | Role | Why This Technology |
|-----------|------|---------------------|
| Query log | Record every search | Kafka: high-throughput append, durable |
| Batch job | Aggregate query frequencies | Spark/MapReduce: parallelizes over billions of events |
| Redis | Store prefix → top-K mapping | Sub-millisecond reads, ZSET native top-K |
| API server | Serve suggestions | Stateless Go/Node: simple lookup proxy |
| Client debounce | Reduce API traffic | Browser-side: no infrastructure needed |

---

## Part 4: API Design

### 4.1 Suggestion Endpoint

```
GET /api/v1/suggest
Query params:
  q        (required) — the current prefix, e.g. "stac"
  limit    (optional) — number of suggestions, default 5, max 10
  lang     (optional) — language code, default "en" (L5 scope: ignored)

Response (200 OK):
{
  "prefix": "stac",
  "suggestions": [
    { "text": "stack overflow", "score": 1240000 },
    { "text": "stack exchange", "score": 890000 },
    { "text": "stacking cups",  "score": 432000 },
    { "text": "stackblitz",     "score": 218000 },
    { "text": "stack overflow jobs", "score": 97000 }
  ]
}

Errors:
  400 — q parameter missing or empty
  400 — limit > 10
  429 — rate limited (too many requests from this IP)

Notes:
  - score is the frequency-based relevance score (not shown to the user — internal only)
  - If no suggestions exist for prefix, return empty array (not 404)
  - Response time: p99 < 20ms (server-side, not including network)
```

### 4.2 Query Log Endpoint

```
POST /api/v1/searches
(Called when user submits a completed search, not on every keystroke)

Request:
{
  "query": "stack overflow tutorial",
  "result_clicked": "https://stackoverflow.com/...",  ← optional
  "session_id": "abc123"
}

Response: 204 No Content

Notes:
  - Fire-and-forget from client perspective
  - Server publishes to Kafka topic "search.queries"
  - No need to wait for this before returning search results
  - If this endpoint fails, the search still works — just loses the log event
```

---

## Part 5: Database Schema

### 5.1 Query Log Table (Persistent Store)

The Kafka topic is not permanent — it has a retention window (e.g., 30 days).
For longer-term analytics, persist to a data warehouse table:

```sql
CREATE TABLE search_query_logs (
  log_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  query_text   TEXT NOT NULL,
  user_id      UUID,                  -- nullable (anonymous searches)
  session_id   VARCHAR(64),
  result_clicked TEXT,                -- URL clicked, if any
  logged_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Partition by date for efficient batch processing
CREATE INDEX idx_query_logs_date ON search_query_logs(logged_at);
CREATE INDEX idx_query_logs_text ON search_query_logs(query_text);
```

**At L5 scale (100M queries/day)**:
- ~100M rows/day inserted
- 30-day retention = 3 billion rows
- Each row ≈ 200 bytes → 600 GB raw → ~60 GB compressed (10:1 compression)
- Use columnar storage (Parquet on S3) for the batch job — not row-oriented PostgreSQL

### 5.2 Aggregated Query Frequency Table (Snapshot)

Optionally, store the post-aggregation snapshot for auditing and debugging:

```sql
CREATE TABLE query_frequency_snapshots (
  snapshot_date DATE NOT NULL,
  query_text    TEXT NOT NULL,
  frequency     BIGINT NOT NULL,        -- total searches in last 30 days
  recency_score DECIMAL(10,4),          -- weighted by recency
  computed_at   TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (snapshot_date, query_text)
);

CREATE INDEX idx_snapshot_freq ON query_frequency_snapshots
  (snapshot_date, frequency DESC);
```

This table is populated by the batch job after aggregation. It serves as an
audit log — you can inspect exactly what scores were computed for a given date.
Redis is populated from this table, not directly from raw logs.

### 5.3 What Lives in Redis (Not a SQL Schema)

Redis doesn't use SQL schemas, but document the data model:

```
Redis Key Pattern: suggest:{prefix}
Redis Type: Sorted Set (ZSET)

Key:    "suggest:stac"
Value:  Sorted set where:
          member = suggestion text ("stack overflow")
          score  = recency-weighted frequency (1240000.0)

Top-K retrieval: ZREVRANGE suggest:stac 0 4 WITHSCORES
  → Returns top 5 members ordered by score descending

Example Redis contents:
  suggest:s   → {("stackoverflow", 5.2M), ("spotify", 4.1M), ...}
  suggest:st  → {("stackoverflow", 5.2M), ("steam", 2.8M), ...}
  suggest:sta → {("stackoverflow", 5.2M), ("star wars", 1.9M), ...}
  suggest:stac → {("stack overflow", 1.2M), ("stack exchange", 890K), ...}
  suggest:stack → {("stack overflow", 1.2M), ("stack exchange", 890K), ...}
```

---

## Part 6: The Trie — Core Data Structure

### 6.1 What a Trie Is

A trie (also called a prefix tree) is a tree where each path from root to node spells
out a string. It is the natural data structure for prefix search.

```
TRIE EXAMPLE (partial, for "sta" queries)
==========================================

                        root
                       /    \
                      s      ...
                      |
                      t
                     / \
                    a   e
                   / \   \
                  r   c   a
                 / \   \   \
                k   ...stack  ...
               /
            "star wars"

  To find suggestions for prefix "sta":
  1. Walk the trie: root → 's' → 't' → 'a'
  2. DFS/BFS all subtrees below 'a' node
  3. Collect all complete words found
  4. Return the top-K by frequency
```

### 6.2 Top-K at Each Trie Node

The naive approach (DFS to collect all completions) is too slow for the "s" node —
there could be billions of queries starting with "s". The optimization:
**store top-K suggestions at every internal node** during the build phase.

```
TRIE WITH TOP-K AT EACH NODE
==============================

  Node 's': top_5 = [("stackoverflow", 5.2M), ("spotify", 4.1M),
                      ("steam", 2.8M), ("snapchat", 1.9M), ("skype", 1.1M)]

  Node 'st': top_5 = [("stackoverflow", 5.2M), ("steam", 2.8M),
                       ("star wars", 1.9M), ("starbucks", 1.7M), ("steve jobs", 800K)]

  Node 'sta': top_5 = [("star wars", 1.9M), ("starbucks", 1.7M),
                        ("stack overflow", 1.2M), ("stanford", 900K), ("starbucks menu", 700K)]
  
  LOOKUP:
  User types "sta" → navigate to node 'sta' → return node.top_5
  O(prefix_length) time — constant per character depth.
```

Building this: a bottom-up pass during trie construction. Leaf nodes initialize
their top-K from their own frequency. Internal nodes compute their top-K as the
merge of all child nodes' top-K lists. Merging two sorted lists of K elements
each takes O(K log K). This is done offline during the batch build.

### 6.3 Memory Usage of a Trie

The trie looks elegant but has serious memory problems at production scale:

- 1 billion unique query strings
- Average 40 characters per query
- Worst case: 40 nodes per query (one per character), minimal sharing
- Each node: 26 children pointers (English alphabet) × 8 bytes + metadata = ~256 bytes
- 1 billion queries × 40 nodes × 256 bytes = **~10 TB of memory**

This is not fit for a single machine. A distributed in-memory trie across many
machines is possible but complex. The production answer avoids the trie entirely.

### 6.4 Compressed Trie (Patricia Trie)

A compressed trie (Patricia trie, radix trie) collapses chains of single-child
nodes into one edge labeled with the full substring:

```
COMPRESSED TRIE (partial)
===========================

  Instead of:  s → t → a → c → k → (end)
  Compressed:  s → "tack" → (end)   [entire suffix stored in one edge]

  Savings: long unique suffixes become single edges rather than one node per char.
  Compression ratio: 3-5× reduction in node count for typical query sets.
```

Even with compression, memory remains a concern for billions of unique queries.
The key insight: **in practice, the production answer is not a trie at all**.

### 6.5 Intern → Staff Progression: Trie

**Intern**: "Use a trie to store all queries. For a prefix, traverse the trie to the
prefix node and do a DFS to find all completions."

**L3**: "Use a trie with top-K stored at each node. To find suggestions for prefix
'sta', traverse to the node for 'a' and return its precomputed top-K list. O(L) lookup
where L is the prefix length."

**L4**: "A trie has a memory problem: billions of unique queries × 40 chars × node size
= terabytes. The production approach is a prefix hash table: store (prefix → top-K list)
directly in a hash map (Redis ZSET). Trade memory for simplicity. O(1) lookup per prefix."

**L5**: "Trie is the conceptual answer that I'd explain first, then pivot to the
implementation answer: Redis sorted sets keyed by prefix. The trie is too memory-heavy
and too difficult to update incrementally (rebuilding is easier than in-place updates).
The Redis approach: each prefix is an independent key, daily batch job replaces each
key's sorted set atomically. No locking, no in-place updates, trivially shardable by
hashing the prefix key."

---

## Part 7: The Production Answer — Prefix Hash Table in Redis

### 7.1 The Core Idea

Instead of a trie, store a flat mapping:

```
every_possible_prefix → sorted list of top-K suggestions

"s"     → [("stackoverflow", 5.2M), ("spotify", 4.1M), ...]
"st"    → [("stackoverflow", 5.2M), ("steam", 2.8M), ...]
"sta"   → [("star wars", 1.9M), ("starbucks", 1.7M), ...]
"stac"  → [("stack overflow", 1.2M), ("stack exchange", 890K), ...]
"stack" → [("stack overflow", 1.2M), ("stack exchange", 890K), ...]
```

Lookup: given prefix "stac", hash-lookup "stac" → get the pre-sorted top-K list. O(1).
No tree traversal, no complex data structure, no pointer chasing.

### 7.2 Redis ZSET — Native Top-K

Redis Sorted Sets (ZSET) are perfect for this:

```
Redis commands:

  BUILD (during batch job):
  ZADD suggest:stac 1240000 "stack overflow"
  ZADD suggest:stac  890000 "stack exchange"
  ZADD suggest:stac  432000 "stacking cups"
  ZADD suggest:stac  218000 "stackblitz"
  ZADD suggest:stac   97000 "stack overflow jobs"

  QUERY (at serve time):
  ZREVRANGE suggest:stac 0 4 WITHSCORES
  → Returns top-5 elements sorted by score descending
  → O(log N + K) time, where N = size of the sorted set, K = elements returned
  → In practice: < 1ms

  STORAGE SIZE:
  Each (member, score) pair in a ZSET: ~50-100 bytes overhead
  Top-5 per prefix key: ~500 bytes per key
  10M prefixes × 500 bytes = 5 GB — fits in a single Redis instance
```

### 7.3 Storage Calculation

Key calculation for the interview:

```
PREFIX COUNT:
  English words: ~500,000 common words
  Prefix lengths: average 4 characters per query
  Unique prefixes: For 100M unique queries, each of length 4-40 chars:
    - 26 1-char prefixes (a-z)
    - 26^2 2-char prefixes = 676 (but not all common)
    - For N-char prefixes: roughly N × (unique_queries) in the worst case
  
  Practical estimate for 100M unique queries:
  Each query generates (length-1) prefix keys.
  Average query length: 20 chars → 19 prefix keys per query.
  100M queries × 19 prefixes / average prefix reuse factor (100×)
  = ~19M prefix keys (many queries share the same prefix)
  
  STORAGE:
  19M prefix keys × 5 suggestions × 100 bytes/entry = ~9.5 GB
  
  For a top-10 per prefix, 100-char queries: ~20-30 GB
  Fits comfortably in a Redis cluster with 2-3 nodes.
```

### 7.4 Why Redis and Not PostgreSQL?

| Criteria | Redis ZSET | PostgreSQL (prefix LIKE query) |
|----------|------------|-------------------------------|
| Lookup latency | < 1ms (in-memory) | 5-50ms (disk I/O) |
| Index type | Hash + sorted set | B-tree (not optimal for prefix) |
| QPS at 50K RPS | Handles easily | Needs query plan + connection pool overhead |
| Updates | Atomic ZADD | UPDATE + B-tree rebalance |
| Data fits in RAM? | Yes (5-30 GB) | Not required (but slower on disk) |
| Sharding | Trivial (key hash) | Complex (application-level) |

At p99 < 20ms server target, PostgreSQL would require heavy optimization (connection
pooling, read replicas, index tuning) to achieve what Redis gives for free. Redis is
the correct choice.

### 7.5 Brainstorming Q&A — Part 7

**Q: What if a prefix doesn't exist in Redis?**

Return an empty suggestions array (not a 404). This happens for rare or novel
prefixes that didn't appear in the query logs. The client gracefully shows no
suggestions without an error state. Do not throw an error for a missing Redis key —
`ZREVRANGE` on a nonexistent key returns an empty list, not an error.

**Q: How do you handle prefix keys when queries are case-insensitive?**

Normalize to lowercase before storing. The batch job lowercases all queries before
computing prefix keys. The API server lowercases the incoming prefix parameter before
the Redis lookup. This means "Stack" and "stack" and "STACK" all resolve to the same
key "stack". Store one canonical lowercase version per query.

**Q: Should the score exposed to the API consumer include the raw frequency number?**

No — raw frequency numbers like "5.2 million" are implementation details. The client
only needs the ordered list of suggestions, not their scores. The API response can
include scores internally (useful for debugging), but the score field should be either
omitted or treated as opaque by the client. The relative order is what matters for
rendering the dropdown.

---

## Part 8: Building the Data — Offline Aggregation Pipeline

### 8.1 The Input: Query Logs

Every search produces a log event:
```json
{
  "query": "stack overflow tutorial",
  "timestamp": "2026-06-25T14:32:11Z",
  "user_id": "u_abc123",
  "session_id": "sess_xyz"
}
```

These stream into a Kafka topic: `search.queries`. The topic retains 30 days of events.
Daily batch job reads the last 30 days of events (or since the last run).

### 8.2 The Aggregation Pipeline (Daily Batch)

```
DAILY BATCH JOB (runs at ~2 AM UTC when traffic is lowest)
============================================================

  INPUT: Kafka topic "search.queries" (last 30 days)
  
  STEP 1: COUNT QUERY FREQUENCIES
  For each query text (normalized to lowercase, trimmed):
    count += 1
  
  Result: { "stack overflow": 1,240,000, "star wars": 890,000, ... }
  
  STEP 2: APPLY RECENCY WEIGHTING
  Queries searched yesterday count more than queries from 30 days ago.
  
  For each event:
    days_ago = today - event.date   (0 = today, 29 = 30 days ago)
    weight = 1.0 / (1 + 0.1 × days_ago)   ← linear decay
  
  score(query) = SUM of weights across all occurrences
  
  Example: a query searched 100 times yesterday scores higher than
           a query searched 100 times last week.
  
  STEP 3: GENERATE PREFIX KEYS
  For each query and its score:
    For length L from 1 to min(len(query), MAX_PREFIX_LENGTH=20):
      prefix = query[0:L]
      emit (prefix, query, score)
  
  STEP 4: TOP-K PER PREFIX
  Group by prefix. For each prefix:
    Sort by score descending
    Keep only top-10
  
  Result: { "stac": [("stack overflow", 1.24M), ("stack exchange", 890K), ...], ... }
  
  STEP 5: WRITE TO REDIS
  For each (prefix, top-K list):
    Pipeline:
      DEL suggest:{prefix}
      ZADD suggest:{prefix} score1 text1
      ZADD suggest:{prefix} score2 text2
      ...
      EXPIRE suggest:{prefix} 172800  (48 hour TTL — safety fallback)
  
  OUTPUT: Redis cluster updated with fresh prefix data
  
  TOTAL RUNTIME: ~2-4 hours for 3 billion log events on a 20-node Spark cluster
```

### 8.3 Why Recency Weighting?

A query that was popular 3 weeks ago but is no longer searched should not dominate
over a query that is currently trending. Recency weighting achieves this:

```
RECENCY WEIGHTING EXAMPLE
==========================

  Query: "olympic games"
  - 1 year ago (before the Olympics): 50,000 searches/day
  - During the Olympics: 2,000,000 searches/day
  - After the Olympics (today): 30,000 searches/day

  WITHOUT recency weighting:
    30-day total: roughly reflects the Olympic period → still very high
    Result: "olympic games" ranks very high even months after the Olympics

  WITH recency weighting (last 7 days have most weight):
    Recent 7 days at 30K/day: score ≈ 210,000 × high weight
    Result: appropriately reflects current interest level
```

**Decay function trade-off**:
- Steep decay (weight drops quickly with age): very responsive to trending, but
  misses seasonal patterns (holiday queries drop off entirely in off-season)
- Shallow decay: more stable, but slower to respond to trends
- L5 choice: 30-day rolling window with linear decay. Simple, predictable, testable.

### 8.4 The 30-Day Window

Why 30 days? Trade-offs:
- **7 days**: Very responsive to trends, but misses legitimate stable queries
  ("weather forecast") that are searched consistently every week
- **30 days**: Captures a full monthly cycle, including weekday/weekend patterns
- **1 year**: Too slow to respond to trends; "covid vaccine" would rank high forever

30 days is the industry default (used by Google and others historically).

### 8.4a Score Normalization

Raw counts are not directly usable as scores in all cases. Consider:
- Platform A has 100M queries/day. "Pizza" gets 500,000 searches.
- Platform B has 1M queries/day. "Pizza" gets 50,000 searches.

If you compare raw counts across deployments or over time (as the platform grows),
scores become incomparable. Two approaches:

**Relative frequency** (normalize by total queries):
```
score = (query_count_30d / total_queries_30d) × 1,000,000
```
This makes scores portable across platforms and time periods.

**Log frequency** (compress the distribution):
```
score = log10(query_count_30d + 1)
```
Prevents billion-search queries from completely overwhelming 100K-search queries.
More useful when you want to show varied suggestions rather than just the same
top 5 queries for every prefix.

At L5: raw counts are fine for the interview. Mention normalization as a "would
consider in production" item when discussing scoring.

### 8.4b Handling Seasonal Queries

Some queries are strongly seasonal: "christmas gifts" in December, "tax filing"
in April, "super bowl" in February. A recency-weighted 30-day window naturally
handles this: these queries surge into the top-K during their season and fade
out of the top-K afterward. No special handling needed.

The only edge case: a query that was extremely popular exactly 31 days ago gets
completely cut off when the 30-day window advances past it. If you want smoother
handling: use a 90-day window with steeper decay (recent events weigh more, old
events weigh much less). The math is the same; the window is wider.

### 8.5 Brainstorming Q&A — Part 8

**Q: What if the batch job fails partway through? Is Redis left in a bad state?**

The safe approach: write to a new Redis key prefix (e.g., `suggest_new:{prefix}`)
during the build phase. After the entire build completes successfully, atomically
swap: `RENAME suggest_new:{prefix} suggest:{prefix}`. If the build fails before
completing, the swap never happens — the old data remains in place. Users see
slightly stale suggestions until the next successful run. This is an atomic
double-buffering pattern: build into a shadow store, swap on completion.

**Q: What if the Kafka topic doesn't go back 30 days?**

Your Kafka topic may only retain 7 days of events (to save disk). Solution:
store the daily aggregated counts in a database or S3 (columnar, compressed).
Each day's batch job:
1. Read today's query events from Kafka (just today, fast)
2. Read the last 29 days of daily aggregates from S3
3. Combine and weight
4. Compute top-K and write to Redis

This decouples event retention from aggregation history. Kafka only needs today's
events; S3 holds the pre-aggregated daily summaries (much smaller than raw events).

**Q: How do you handle offensive or inappropriate query completions?**

A blocklist applied as a post-processing step after scoring. Before writing to Redis,
filter out any suggestions that match a list of blocked terms. The blocklist is
maintained by a human trust-and-safety team and applied at build time. This is
separate from real-time filtering (which would require checking every API response,
but that's too slow). For L5: mention "apply a blocklist during the batch build
step before writing to Redis."

---

## Part 9: The Serving Layer — Sub-100ms

### 9.1 The Request Flow

```
REQUEST FLOW (serve time)
===========================

  Client                     API Server (Go/Node)           Redis
  
  User types "stac"          
  [100ms debounce fires]     
       │                          
       ├── GET /suggest?q=stac ──►  
                                    1. Lowercase: "stac"
                                    2. Validate: 1 ≤ len ≤ 20 chars
                                    3. Check local cache (in-process LRU)
                                       HIT: return immediately (skip Redis)
                                       MISS: continue
                                    4. ─── ZREVRANGE suggest:stac 0 4 ───►  
                                                                        │
                                                                        │ < 1ms
                                                                        ◄
                                    5. Serialize top-5 to JSON
                                    6. Add to local LRU cache
       ◄── suggestions JSON ────────
```

### 9.2 Latency Budget Breakdown

The sub-100ms total latency is split:

```
LATENCY BUDGET
===============

  Client → Server (network RTT): 20-50ms
    (CDN PoP proximity brings API server close to user)
  
  Server processing: 3-8ms
    - Debounce wait: 0ms (already done on client)
    - Input validation: < 0.1ms
    - Local LRU cache check: < 0.1ms
    - Redis ZREVRANGE: 0.5-2ms (local network, Redis in same DC)
    - JSON serialization: 0.5-1ms
    - Total: < 5ms p99
  
  Server → Client (network): 5-20ms (small JSON, < 1 KB)
  
  Client rendering: 1-3ms
  
  TOTAL p99: 30-80ms ← well under 100ms
  
  KEY: the Redis lookup must be on the same network segment as the API server.
       Redis in a different region (100ms away) would blow the budget.
```

### 9.3 In-Process LRU Cache (API Server)

For ultra-hot prefixes (short prefixes like "a", "th", "st"), even Redis is over-killed.
Every API server maintains a small in-memory LRU cache:

```
LRU CACHE (per API server, in-process)
=========================================

  Capacity: 10,000 entries (hot prefixes only)
  TTL: 60 seconds
  
  Key: prefix string ("st", "sta", "stac", ...)
  Value: serialized JSON response
  
  HIT RATE for short prefixes (1-3 chars): ~99% (very few such prefixes, all hot)
  HIT RATE for longer prefixes (4-6 chars): ~40-60%
  
  BENEFIT:
  Short prefixes account for ~60% of traffic (Zipf distribution — more users
  are typing "st" at any moment than "stackoverflow"). Caching them in-process
  eliminates even the Redis round-trip for most of the traffic.
```

### 9.4 Client-Side Debouncing

```
CLIENT DEBOUNCE IMPLEMENTATION (pseudocode)
=============================================

  let debounceTimer = null
  let prefixCache = {}  // local cache: prefix → suggestions

  function onKeystroke(currentInput):
    // Clear any pending request
    clearTimeout(debounceTimer)

    // Check prefix cache first
    if currentInput in prefixCache:
      renderSuggestions(prefixCache[currentInput])
      return

    // Also check if current input extends a cached prefix
    for length from currentInput.length - 1 down to 1:
      shorterPrefix = currentInput[0:length]
      if shorterPrefix in prefixCache:
        // Filter cached suggestions to those matching longer prefix
        filtered = prefixCache[shorterPrefix].filter(
          s => s.text.startsWith(currentInput)
        )
        if filtered.length >= 3:  // enough results to show
          renderSuggestions(filtered)
          return  // don't fire API call

    // Schedule API call after 100ms of inactivity
    debounceTimer = setTimeout(() => {
      fetchSuggestions(currentInput)
    }, 100)

  function fetchSuggestions(prefix):
    response = GET /api/v1/suggest?q={prefix}
    prefixCache[prefix] = response.suggestions
    renderSuggestions(response.suggestions)
```

The "extend from cached prefix" optimization avoids API calls when the user types
additional characters that can be filtered from an already-cached shorter prefix.
In practice this eliminates 30-40% of API calls.

### 9.5 Intern → Staff Progression: Serving Layer

**Intern**: "The API server gets the prefix from the request, queries the database, and
returns matching suggestions."

**L3**: "The API server queries Redis with ZREVRANGE on the key for the prefix. Returns
top-5 sorted by score. Redis is sub-millisecond in-memory lookup."

**L4**: "The client debounces keystrokes — waits 100ms before sending a request. This
reduces API calls by 3-5×. API servers add an in-process LRU cache for hot prefixes
(1-3 character prefixes account for 60% of traffic due to Zipf distribution). Cache hit
eliminates the Redis call."

**L5**: "The latency budget is: 20-50ms network, 3-8ms server processing, 5-20ms return
network. Server processing includes local LRU check (0.1ms), Redis ZREVRANGE (0.5-2ms),
serialization (0.5ms). P99 total < 100ms requires Redis to be in the same datacenter as
the API servers (not across regions). Client-side prefix extension (filter cached longer
prefix suggestions locally) eliminates ~35% of API calls without any server involvement."

---

## Part 10: Scaling

### 10.1 Redis Sharding

As query volume grows, one Redis instance may not hold all prefix keys (or the
read QPS exceeds one instance's capacity). Shard the Redis cluster by prefix:

```
REDIS SHARDING BY PREFIX
=========================

  Shard 0: prefixes starting with a-h
  Shard 1: prefixes starting with i-r
  Shard 2: prefixes starting with s-z
  
  API server routing:
  prefix = "stac"
  shard = hash(prefix[0]) % num_shards  ← route by first character
  redis_client = shards[shard]
  redis_client.ZREVRANGE(...)

  OR: use Redis Cluster which handles sharding automatically via
  consistent hashing on the key.
```

**Hot shard problem**: If prefix distribution is uneven (more queries start with
"s" than "x"), some shards handle more load. Mitigations:
- Hash the full prefix (not just first char) to distribute more evenly
- Use Redis Cluster's built-in hash slots (16,384 slots, keys distributed by CRC16)
- Add read replicas to overloaded shards

### 10.2 Read Replicas for High QPS

Each Redis primary has 1-2 read replicas:
- Writes (batch job updates) go to primaries only
- Reads (suggestion queries) are distributed across primary + replicas

At 50,000 RPS and 1ms per Redis operation, one Redis server handles ~50,000 ops/second.
Redis can actually handle 100,000-300,000 ops/second on modern hardware, so one server
handles the load. Read replicas add redundancy (not just capacity) and allow zero-downtime
batch updates (write to replicas first, then primary).

### 10.3 Graceful Degradation

If Redis is unavailable:
- **Option 1**: Return empty suggestions array. Search still works; autocomplete is down.
  Users see no suggestions, not an error. Acceptable for a non-critical feature.
- **Option 2**: Fall back to a secondary store (PostgreSQL LIKE query on a cached table).
  Much slower (10-50ms per query) but returns some suggestions.
- **Option 3**: Serve cached static fallback — a predefined list of globally popular
  queries for common prefixes, hardcoded in the API server.

At L5: Option 1 (return empty) is the simplest and safest fallback. Log the Redis error,
trigger an alert, return 200 with an empty suggestions array.

### 10.3a Monitoring the Autocomplete Service

An L5 answer to "how would you operate this in production" includes knowing which
metrics to watch:

```
KEY METRICS TO MONITOR
=======================

  LATENCY:
  - p50, p95, p99 server response time (target: p99 < 20ms)
  - Redis ZREVRANGE latency (target: < 2ms p99)
  - End-to-end client time (target: < 100ms including network)

  THROUGHPUT:
  - Suggestion API QPS (baseline, alert on sudden drops = broken client)
  - Cache hit rate: LRU (target: > 50%), Redis (effectively 100% — key exists)
  - Redis missed keys rate (prefix not found → empty suggestions)
  
  DATA FRESHNESS:
  - Time since last successful batch job completion
    Alert: if > 28 hours (daily job is late)
  - Redis key count (should be stable day-over-day unless corpus changes)
  
  ERRORS:
  - 5xx error rate on /suggest endpoint (target: < 0.01%)
  - Redis connection errors (alert immediately — autocomplete will degrade)
  - Rate limiting events per user/IP (unusual spikes = bot or bug)
  
  BUSINESS METRICS:
  - Click-through rate on suggestions (what % of suggestions are selected)
  - "Suggestion helped" rate (did user accept a suggestion vs. type full query)
  - Zero-suggestion rate (prefix returned empty array — may indicate stale data)
```

A healthy system has: p99 latency < 20ms, LRU hit rate > 50%, zero-suggestion
rate < 2%, and the batch job running successfully within the last 26 hours.

### 10.4 Capacity Planning Exercise

```
CAPACITY SIZING
================

  Given: 50,000 suggestion requests per second

  REDIS:
  Each ZREVRANGE: ~0.1ms CPU, ~0.5ms wall time
  One Redis instance: ~200,000 ops/second capacity
  Safety factor 2×: 100,000 ops/second per instance
  Instances needed: 50,000 RPS / 100,000 ops = 1 instance (+ 1 replica)
  
  API SERVERS:
  Each server: handles 5,000-10,000 RPS (mostly I/O wait on Redis)
  With in-process LRU at 60% hit rate: effective Redis load = 20,000 RPS
  Servers needed: 50,000 RPS / 7,500 per server = ~7 API servers
  (scale to 10-15 for redundancy)
  
  BATCH JOB:
  Runs daily, not on critical path. Use a dedicated Spark cluster.
  Not included in serving capacity.
```

---

## Part 11: Real-Time Trending Updates

### 11.1 The Problem

The daily batch job runs at 2 AM. A news event breaks at 10 AM — "earthquake japan" surges
from 0 searches to 5 million searches in 2 hours. The batch suggestions won't reflect this
until tomorrow's run.

For a platform where freshness matters (news site, social media search), this is a problem.

### 11.2 Stream Processing Layer (Lightweight)

```
REAL-TIME TRENDING PIPELINE
=============================

  All query events on Kafka
         │
         ▼
  [Stream Processor] (Flink / Kafka Streams)
    - Tumbling window: count queries per 5-minute window
    - Sliding window: count queries over last 30 minutes
    - Compute "velocity": is this query accelerating rapidly?
    - Velocity = (last 5 min count) / (previous 30 min average)
    - If velocity > 10× (trending threshold): mark as trending
         │
         ▼
  [Trending Store] (separate Redis hash, key = "trending")
    trending_queries = [
      ("earthquake japan", velocity=50x, score=8500),
      ("apple announcement", velocity=20x, score=4200),
    ]
    Updated every 5 minutes.
         │
         ▼
  [API Server] serves trending queries for SHORT prefixes (1-3 chars)
    If prefix = "e" and trending contains "earthquake japan":
      Inject "earthquake japan" into suggestions at the top
      (blending trending into standard prefix results)
```

### 11.3 Blending Trending with Base Suggestions

The API server combines two sources:

```
SUGGESTION BLENDING
====================

  For prefix "e":
  
  Base suggestions (from daily batch):  ["email", "ebay", "espn", "etsy", "epic games"]
  Trending now:                          ["earthquake japan" (50x velocity)]
  
  Blended result:
  1. "earthquake japan"  ← injected at top if velocity > threshold
  2. "email"
  3. "ebay"
  4. "espn"
  5. "etsy"
  
  Blending rules:
  - Trending items capped at 1-2 spots (don't take over the dropdown)
  - Must still be prefix-matched ("e..." qualifies for prefix "e")
  - Trending injection disabled for prefixes > 4 chars (too specific; trending
    won't match — "emai" won't be trending)
```

### 11.3a Count-Min Sketch for Real-Time Frequency Estimation

For high-scale trending detection, storing exact counts for every query in a
streaming window requires too much memory (billions of unique queries × window
size). A probabilistic data structure called the **Count-Min Sketch** solves this:

```
COUNT-MIN SKETCH
=================

  A matrix of W × D counters, initialized to 0.
  For each query event:
    For each row i from 1 to D:
      hash_i(query) → column j
      matrix[i][j] += 1

  To estimate frequency of a query:
    For each row i:
      j = hash_i(query)
      estimate_i = matrix[i][j]
    Return min(estimate_1, ..., estimate_D)

  PROPERTIES:
  - Overestimates frequency (due to hash collisions), never underestimates
  - Error bound: with probability 1-δ, error ≤ ε × total_events
  - Memory: W × D integers, where W = e/ε (about 2.718/error_rate)
                                      D = ln(1/δ) (about -ln(confidence))
  - For 1% error at 99% confidence: W=272, D=5 → 1,360 counters
    vs. storing every unique query exactly: millions of counters

  At L5: mention as a memory-efficient alternative to exact counts in streaming.
  The sketch trades a small error rate for orders of magnitude less memory.
```

At L5: knowing Count-Min Sketch exists and why it's useful (probabilistic frequency
in bounded memory) is enough. You don't need to derive the error bounds from scratch.

### 11.4 Why Keep Trending Separate?

Merging trending signals back into the main batch pipeline (running hourly instead
of daily) would cause: expensive infrastructure, complex pipeline maintenance, risk
of unstable scores. The separation is cleaner: stable base (updated daily) + volatile
trending overlay (updated every 5 minutes). Each component is independently testable
and replaceable.

---

## Part 12: Interview Application

### 12.1 This Is Often a Warmup Question

"Design an autocomplete system" frequently appears as a 30-minute warmup before
a 45-minute main question. Signs it's a warmup:
- Interview is 1.5 hours with two problems
- Interviewer says "let's start with a simpler one"
- Problem is framed as just the search box, not the full search engine

**In 30 minutes**: Cover data structure (trie concept, then pivot to prefix hash),
Redis as storage, serving path. Skip: offline pipeline details, real-time trending,
scaling.

**In 45 minutes**: Cover everything above including offline pipeline and basic scaling.

### 12.2 Common Mistakes

**Mistake 1: Stopping at "use a trie"**
A trie is the correct conceptual answer but not the production answer. For 1 billion
unique queries, a trie requires terabytes of RAM and is difficult to update. Always
pivot: "A trie works for the conceptual model, but in practice I'd use a prefix hash
table in Redis — one ZSET per prefix storing the top-K suggestions."

**Mistake 2: Not discussing how suggestions are ranked**
Many candidates answer the data structure question but forget to explain why
"stack overflow" appears before "stacking chairs" for prefix "stack". Ranking by
frequency is the L5 answer. Explain the offline aggregation that computes these
scores from query logs.

**Mistake 3: Not calculating storage**
"Use Redis for the prefix store" without a size calculation leaves the interviewer
wondering: does this fit in RAM? 10M prefixes × 5 suggestions × 100 bytes = 5 GB.
That's the reassurance they want — always do the calculation.

**Mistake 4: Missing client-side optimizations**
Some interviewers ask "how would you reduce the load on your servers?" The answer
involves client-side debouncing (easy to implement, 3-5× traffic reduction) and
prefix extension caching (filter already-fetched suggestions locally). These are
not infrastructure changes — they're client patterns.

**Mistake 5: Conflating autocomplete with search**
Autocomplete suggests completions for the current prefix. Search returns results for
a completed query. Different systems, different requirements, different data. Don't
conflate them. Autocomplete doesn't rank search results — it only suggests query
completions.

### 12.3 Key Numbers to Memorize

| Fact | Number |
|------|--------|
| Target server latency p99 | < 20ms (total with network: < 100ms) |
| Redis ZREVRANGE latency | < 1ms |
| Suggestions shown | 5-10 |
| Prefix hash storage estimate | 5-30 GB (fits in Redis) |
| Client debounce delay | 100-150ms |
| Batch job frequency | Daily (nightly) |
| Lookback window | 30 days |
| Short prefix (1-3 chars) traffic share | ~60% (Zipf distribution) |

### 12.4 L5 vs L6 Answer Comparison

**Question**: "How would you handle a viral trending query appearing in autocomplete
within minutes, not 24 hours?"

**L4 answer**: "Run the batch job more frequently — hourly instead of daily."

**L5 answer**: "Running the batch job hourly is expensive (full log processing every
hour) and still leaves up to 1 hour of lag. I'd separate the trending signal from the
base suggestions: a stream processor (Flink) computes query velocity over a 5-minute
tumbling window from the Kafka topic. Queries with velocity > 10× baseline are marked
trending and stored in a separate Redis key. The API server blends trending queries
into the top 1-2 positions for matching prefixes, overriding the daily batch ranking.
This gives near-real-time trending (< 5 minutes latency) without re-running the expensive
batch pipeline."

---

## Part 13: Pre-Interview Drill

### 13.1 Five Concepts You Must Explain in 60 Seconds Each

**1. What is a trie and why is it the conceptual answer?**
"A trie is a tree where each path from root to a node spells a string. To find
suggestions for prefix 'sta', traverse from root: s → t → a, then collect all
complete words below that node. To make it fast, store the top-K suggestions at
every internal node during the build phase. Traversal is O(prefix_length). This
is the correct concept. The memory problem is that a 1-billion-query trie needs
terabytes of RAM, which is why production systems use prefix hash tables instead."

**2. What is a prefix hash table?**
"Instead of a tree, store a flat hash map from prefix to top-K suggestions.
Key = 'stac', value = sorted list of top-5 queries starting with 'stac'. Redis
sorted sets (ZSETs) implement this natively: ZADD 'suggest:stac' 1240000
'stack overflow'. At serve time: ZREVRANGE 'suggest:stac' 0 4 returns the top-5
in < 1ms. Every possible prefix gets its own ZSET. Storage: ~5-30 GB for a
medium platform — fits in Redis RAM."

**3. How do you build the suggestion data?**
"A daily batch job reads the query logs from the last 30 days. It counts how often
each query was searched, applies a recency weight (recent searches count more), then
for each query generates all its prefixes and emits (prefix, query, score) tuples.
After grouping by prefix and keeping only the top-K per prefix, it writes all prefix
ZSET keys to Redis. The job runs overnight and takes 2-4 hours. Users get fresh
suggestions each morning."

**4. What is debouncing and why does it matter?**
"Debouncing means waiting for a pause in keystrokes before firing an API call.
Instead of sending a request on every single keystroke, the client waits 100ms.
If the user types 'stack' in 200ms (5 keystrokes in 40ms each), only one API call
fires — not five. This reduces server load by 3-5× with no perceptible difference
to the user. Combined with prefix extension caching (filtering cached suggestions
locally for longer prefixes), the actual API call rate drops even further."

**5. How do you achieve sub-100ms end-to-end?**
"The budget: 20-50ms network to a nearby API server (deploy API servers close to
users), 3-8ms server processing (Redis ZREVRANGE < 1ms, plus overhead), 5-20ms
return network. The key is colocation — Redis must be in the same datacenter as
the API server, not across a WAN link. Additionally: an in-process LRU cache on
the API server eliminates Redis calls for the hottest short prefixes (1-3 chars),
which account for 60% of requests."

### 13.2 Diagrams to Draw Cold

**Diagram 1: System overview (2 paths)**
```
  WRITE (daily):
  Query logs → Batch Job → Redis prefix store

  READ (real-time):
  User types → [debounce 100ms] → API server → Redis ZREVRANGE → dropdown
```

**Diagram 2: Prefix hash table contents**
```
  suggest:s    → [("stackoverflow", 5.2M), ("spotify", 4.1M), ...]
  suggest:st   → [("stackoverflow", 5.2M), ("steam", 2.8M), ...]
  suggest:sta  → [("star wars", 1.9M), ("starbucks", 1.7M), ...]
  suggest:stac → [("stack overflow", 1.2M), ("stack exchange", 890K), ...]
```

**Diagram 3: Trie with top-K at nodes (explain then dismiss)**
```
  root
   └─ s (top5: [stackoverflow, spotify, steam, ...])
       └─ t (top5: [stackoverflow, steam, star wars, ...])
           └─ a (top5: [star wars, starbucks, stack overflow, ...])
               └─ c (top5: [stack overflow, stack exchange, ...])
  
  "The trie is the concept. Redis prefix hash is the implementation."
```

### 13.3 Questions That Expose Depth

**Q: "Why store the top-K at build time instead of at query time?"**
Because query time is latency-critical (< 20ms), you cannot afford to scan all queries
starting with a prefix and rank them on the fly. At query time, you have 1ms for Redis.
Computing top-K from scratch would require reading all matching prefix entries (potentially
millions) and sorting them — taking seconds, not milliseconds. Pre-computing top-K
at build time trades storage (slightly more Redis keys) for query speed.

**Q: "What happens if a new query goes viral and it's not in Redis yet?"**
Answer the two layers: (1) The base suggestions (from yesterday's batch) won't include
it. (2) The real-time trending overlay (stream processor watching Kafka) detects
high-velocity queries and injects them into suggestions for matching prefixes within
5 minutes. For a platform where recency matters, the streaming overlay is necessary.
For a platform where daily freshness is fine (e.g., product search for an e-commerce
site), the daily batch alone is acceptable.

**Q: "How would you add personalized suggestions?"**
Personal suggestions require knowing what the user has searched before. A simple
approach: store the last 20 searches per user in Redis (key = `user_history:{user_id}`,
type = list). When serving suggestions for prefix "stac", merge the global top-K with
any items from the user's history that match the prefix. Boost user history items by a
fixed multiplier. This is O(1) extra Redis lookups. Privacy: user history is per-session
only (clear on logout) or opt-in with explicit consent.

---

## Part 14: Capacity Estimation Deep Dive

### 14.1 Prefix Count Estimation (Walk-Through)

The most common gap in autocomplete interviews: "How much storage does this take?"
Walk through this explicitly.

```
PREFIX COUNT ESTIMATION
========================

  INPUT PARAMETERS:
  - 100M distinct queries in the corpus (after deduplication)
  - Average query length: 20 characters
  - Max prefix length stored: 20 characters
  - Prefixes are normalized to lowercase English

  WORST CASE (no sharing):
  If every query were unique character by character:
  100M queries × 20 chars/query = 2B prefix keys

  REALISTIC CASE (with sharing):
  Short prefixes are shared by many queries:
  - "s" is a prefix for every query starting with "s" (~4-5% of queries)
    → 4M queries share the key "s"
  - "st" → shared by all "star wars", "stackoverflow", "steam", etc.
    → 2M queries share the key "st"
  - "stac" → shared by ~50K queries
  - "stack" → shared by ~30K queries
  
  Each unique prefix key is stored ONCE regardless of how many queries share it.
  The question is: how many distinct prefix strings exist across all queries?
  
  A rough model:
  - 1-char prefixes: 26 (all used)
  - 2-char prefixes: 26×26 = 676, maybe 70% used ≈ 473
  - 3-char prefixes: 26^3 = 17,576, maybe 60% used ≈ 10,500
  - 4-char prefixes: 26^4 ≈ 456K, maybe 30% used ≈ 137K
  - 5-char prefixes: ≈ 11.8M combinations, maybe 10% used ≈ 1.2M
  - 6-20 char prefixes: long tail, roughly another 5-10M unique

  TOTAL DISTINCT PREFIX KEYS: ~7-12M for 100M distinct queries.
  Let's use 10M as our estimate.

  REDIS MEMORY:
  10M prefix keys × top-10 suggestions × (30 char avg + 8 byte score + overhead)
  = 10M × 10 × 80 bytes
  = 8 GB of raw data
  
  Redis overhead (hash table + ZSET internal structure): ~2× multiplier
  Total Redis memory estimate: ~16 GB
  
  Fits comfortably on two Redis instances (32 GB RAM each, 50% utilization).
```

### 14.2 QPS and Latency Math

```
QPS ESTIMATION
===============

  USER BEHAVIOR:
  - 10M daily active users on the search feature
  - Average user performs 5 searches/day
  - Each search: user types ~4 characters before selecting a suggestion or pressing Enter
  - With debouncing (100ms wait): ~2 API calls per search on average
  
  QPS: 10M users × 5 searches × 2 API calls / 86,400 seconds = ~1,160 QPS average
  
  Peak factor: 5× average during peak hours (evening, weekdays)
  Peak QPS: ~5,800 QPS
  
  With 20% headroom: provision for 7,000 QPS.
  
  API SERVER CAPACITY:
  Each API server (8 vCPU, 16 GB RAM):
    - Connection overhead: ~0.5ms
    - Redis lookup: ~1ms
    - JSON serialization: ~0.5ms
    - Total: ~2ms per request
    - Max RPS per server: 1000ms / 2ms × CPU parallelism = ~4,000 RPS
  
  Servers needed: 7,000 / 4,000 = 2 servers (provision 3-4 for redundancy + headroom)
  
  REDIS QPS CAPACITY:
  Single Redis instance: ~200,000 ops/sec
  With our 7,000 RPS × 60% cache miss rate → 4,200 Redis ops/sec
  Well within single instance capacity.
```

### 14.3 Batch Job Resource Estimation

```
DAILY BATCH JOB SIZING
=======================

  INPUT DATA:
  - 100M queries/day × 30 days = 3B events
  - Each event: 200 bytes raw / 20 bytes compressed (Parquet)
  - Compressed input: 3B × 20 bytes = 60 GB/day to read
  
  STEP 1 — AGGREGATE QUERY FREQUENCY:
  Spark shuffles all query events by query_text to count occurrences.
  Shuffle data: 100M unique queries × ~30 bytes per key = 3 GB
  With 3B input records × 8 byte key = 24 GB shuffle → manageable
  
  STEP 2 — GENERATE PREFIX KEYS:
  For each query, emit up to 20 prefix keys.
  Output: 100M queries × 10 avg prefixes × (30 char + 8 float) = 38 GB
  
  STEP 3 — TOP-K PER PREFIX:
  Shuffle by prefix, keep top-10 per prefix.
  Reduce: 10M prefix keys × 10 entries × 80 bytes = 8 GB output
  
  STEP 4 — WRITE TO REDIS:
  10M prefix keys → pipeline ZADD commands
  10M keys × 10 ZADDs × 0.1ms / 1000 (pipeline batching) = 10,000ms = 10 sec
  (pipeline sends 1000 commands per round trip, reducing round trips 1000×)
  
  SPARK CLUSTER:
  20 executors × 8 vCPU × 32 GB RAM
  Total compute: 160 cores, 640 GB RAM
  Estimated runtime: 2-3 hours (bottleneck is shuffle in Step 2)
  Cost (EC2 spot): 20 × $0.20/hr × 3 hours = $12/run = ~$360/month
```

### 14.4 The Zipf Distribution and Why It Matters for Caching

The Zipf distribution is a mathematical law that describes many natural frequency
distributions: the most common item appears twice as often as the second most common,
three times as often as the third, and so on.

Query prefix frequencies follow Zipf:
- Prefix "s" is typed billions of times per day
- Prefix "st" is typed hundreds of millions of times
- Prefix "stackoverflow" is typed thousands of times
- Prefix "stackoverflow-tutorial-python-2" is typed tens of times

```
ZIPF DISTRIBUTION IN PRACTICE
===============================

  Top 100 prefixes (1-2 character prefixes) → 60% of all API traffic
  Next 900 prefixes (3-character prefixes)  → 25% of all API traffic
  Next 9,000 prefixes (4-character)         → 10% of all API traffic
  Remaining 9.99M prefixes                  → 5% of all API traffic

  For caching strategy:
  Cache the top 10,000 prefixes in API server LRU (covers 95% of traffic)
  LRU memory: 10,000 × 500 bytes (serialized JSON) = 5 MB per server
  That's cheap RAM for a huge reduction in Redis calls.

  Cache hit rate = 95% for traffic even though we're only caching
  10,000 / 10,000,000 = 0.1% of all prefix keys.
  
  This is why the in-process LRU cache is so powerful: the Zipf distribution
  means a tiny fraction of prefix keys handles nearly all the traffic.
```

---

## Part 15: Edge Cases and Production Gotchas

### 15.1 Empty and Very Short Prefixes

A user types one character: "a". The suggestion for "a" is:
- "amazon" (billions of searches)
- "apple" (billions)
- "airbnb"
- "amazon prime"
- "amazon music"

These are all correct. But consider: "a" is typed by every user who searches for
anything starting with "a". This prefix alone generates massive Redis load.

Mitigation: For 1-character prefixes, serve from the API server LRU (always warm,
never cache miss). Alternatively, embed the top-K for 1-char prefixes directly in
the API server binary as hardcoded data (refreshed at deploy time). These 26 keys
are trivially small (26 × 10 suggestions × ~30 bytes = ~8 KB total).

### 15.2 Non-ASCII and Emoji Queries

Users search with emoji: "pizza 🍕", "heart ❤️". Edge cases:
- Emoji are multi-byte UTF-8 sequences (4 bytes each)
- Prefix calculation must be done on Unicode code points, not bytes
- "🍕" as a prefix would match "🍕 delivery", "🍕 near me", etc.

At L5: normalize to lowercase UTF-8, handle multi-byte correctly. The Redis ZSET
key is the UTF-8 string directly — Redis handles arbitrary bytes in keys.

### 15.3 Toxic / Harmful Completions

A user types "how to". The top queries might include harmful instructions.
The blocklist applied at batch time covers known harmful strings, but new harmful
queries can emerge between batch runs.

A secondary real-time filter: the trending stream processor also monitors for
high-velocity queries that match a toxicity classifier. These are immediately added
to a Redis blocklist (`blocklist:{prefix}`) that the API server checks before returning
suggestions. This is the "fast blocklist" path — effective within 5 minutes, without
waiting for the nightly batch.

### 15.3a The MAX_PREFIX_LENGTH Parameter

Your batch job only generates prefixes up to `MAX_PREFIX_LENGTH` characters. Why?

- Most users select a suggestion before typing the full query
- After 15-20 characters, suggestions are so specific that almost no one else has
  typed the exact same prefix → very low value, high storage cost
- The Zipf distribution: long prefix keys receive tiny fractions of total traffic

Trade-off:
```
MAX_PREFIX_LENGTH  Storage     % of Queries Covered
─────────────────  ─────────   ────────────────────
10 characters      3 GB         ~85% of suggestion requests
15 characters      6 GB         ~93%
20 characters      10 GB        ~97%
30 characters      18 GB        ~99%
∞                  Enormous     100%
```

At L5: MAX_PREFIX_LENGTH = 20 covers 97% of queries at reasonable storage cost.
For the remaining 3% of long-prefix requests, return an empty suggestions array —
these are power users who type very specifically and don't need help.

### 15.4 A/B Testing Suggestion Ranking

Your ML team wants to test a new ranking model that uses click-through rate (CTR)
instead of raw frequency. Two approaches:

**Option 1: Server-side A/B**
API server reads the user's experiment bucket from request headers (set by the
experiment framework). Bucket A: query Redis key `suggest:{prefix}`. Bucket B:
query Redis key `suggest_v2:{prefix}`. Two parallel Redis key spaces, populated
by two different batch pipelines.

**Option 2: Client-side A/B**
Both suggestion lists are returned to the client; client picks which to display
based on its experiment bucket assignment. Doubles the payload size but requires
no server-side branching logic.

At L5: Option 1 is cleaner. The key insight: you must be able to run the new batch
pipeline without breaking the existing one — two independent Redis key spaces is the
safe approach.

---

## KEY TAKEAWAYS

```
╔══════════════════════════════════════════════════════════════════════════════╗
║           CHAPTER 75: TYPEAHEAD / AUTOCOMPLETE (L5) KEY TAKEAWAYS          ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  1. TRIE = CONCEPT. PREFIX HASH TABLE = PRODUCTION.                         ║
║     Explain the trie first (shows you know the theory).                     ║
║     Pivot to Redis ZSETs: one sorted set per prefix, O(1) lookup.           ║
║     A 1-billion-query trie needs TB of RAM; Redis prefix hash: 5-30 GB.    ║
║                                                                              ║
║  2. PRE-COMPUTE TOP-K AT BUILD TIME                                         ║
║     Query time must be < 20ms. You cannot rank millions of queries then.    ║
║     Offline batch job computes top-K per prefix and stores it in Redis.     ║
║     Query time: ZREVRANGE → O(1) → done.                                    ║
║                                                                              ║
║  3. OFFLINE PIPELINE = QUERY LOGS → AGGREGATE → SCORE → REDIS              ║
║     Daily batch over last 30 days of query logs.                            ║
║     Score = frequency × recency weight (recent searches count more).        ║
║     Output: Redis ZSETs populated for every prefix up to 20 chars.         ║
║                                                                              ║
║  4. DEBOUNCE ON THE CLIENT, NOT THE SERVER                                  ║
║     Wait 100ms after last keystroke before firing API request.              ║
║     Reduces API calls by 3-5×. Zero infrastructure cost.                    ║
║     Prefix extension cache: filter locally before calling API.              ║
║                                                                              ║
║  5. LATENCY BUDGET: KNOW EACH COMPONENT                                     ║
║     Network: 20-50ms. Redis: < 1ms. Server: 2-5ms. Return: 5-20ms.        ║
║     Total < 100ms. Requires Redis in the same datacenter as API servers.   ║
║                                                                              ║
║  6. GRACEFUL DEGRADATION                                                    ║
║     If Redis is down: return empty array (not 500 error).                  ║
║     Autocomplete is non-critical. Never block search for it.               ║
║                                                                              ║
║  7. TRENDING REQUIRES A STREAMING LAYER                                     ║
║     Daily batch → 24h lag. Viral queries need < 5 min to appear.           ║
║     Separate stream processor (Flink) watches Kafka for velocity spikes.   ║
║     Trending overlay injected at API serve time — not baked into batch.    ║
║                                                                              ║
║  8. STORAGE IS MANAGEABLE                                                   ║
║     10M prefixes × 5 suggestions × 100 bytes = 5 GB.                       ║
║     Fits in one Redis instance. Easy to shard if needed.                   ║
║                                                                              ║
║  ONE-SENTENCE SUMMARY:                                                       ║
║  "Autocomplete = daily batch pipeline that aggregates query logs into        ║
║   frequency-ranked top-K suggestions per prefix, stored as Redis ZSETs,    ║
║   served via a debouncing client and stateless API servers at < 20ms p99." ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

---

## Exercises

**Exercise 1: Storage Calculation**
Your platform has 50 million unique query strings. Average query length: 25 characters.
You store top-10 suggestions per prefix. Average suggestion text: 30 characters.

(a) How many total prefix keys do you need in Redis?
    (Hint: each unique query of length L generates L prefix keys. Many queries share
    short prefixes. Assume 100× reuse factor for prefixes.)
(b) Estimate total Redis memory in GB.
    (Hint: each sorted set entry ≈ 64 bytes for text + score + overhead)
(c) If Redis uses 30 GB and you have 2 Redis instances with 32 GB RAM each,
    do you have headroom? What Redis configuration would you use to avoid OOM?

**Exercise 2: Batch Job Sizing**
Your batch job processes 30 days × 100M queries/day = 3 billion query log events.
Each log record is 200 bytes (compressed: 20 bytes in Parquet).

(a) How much data does the batch job read from S3 each day (compressed)?
(b) If each Spark executor processes 100 MB/s, how many executors do you need
    to finish the job in 2 hours?
(c) The batch job must write top-10 suggestions for 10M prefix keys to Redis.
    Each Redis ZADD is 0.1ms. The batch job pipelines 1,000 commands per round trip.
    How long does the Redis population step take?

**Exercise 3: Debounce Trade-offs**
Your current debounce is 100ms. Your product team wants to reduce it to 50ms
(more responsive) or increase it to 200ms (less load).

(a) For a user typing at 5 characters per second (200ms between keystrokes):
    How many API calls does a 10-character query generate with 50ms, 100ms, 200ms debounce?
(b) For a user typing at 10 characters per second (100ms between keystrokes):
    Same question.
(c) What user experience differences would the user notice between 50ms and 200ms debounce?
    Are these differences worth the traffic reduction?

**Exercise 4: Trie vs. Prefix Hash Comparison**
You must choose between storing suggestions as:
- Option A: In-memory trie on each API server (updated daily from batch output)
- Option B: Redis cluster with prefix hash table

| Criteria | Option A (Trie) | Option B (Redis) |
|----------|-----------------|------------------|
| Lookup latency | 5M keys × 20 chars, one char per node |  |
| Memory per server (5M prefixes, top-5 each) |  |  |
| How to update daily? |  |  |
| What happens when 1 of 10 API servers is restarted? |  |  |
| Horizontal scaling (add 5 more servers) |  |  |

Fill in the table. Which option wins and why?

**Exercise 5: Trending Detection Design**
You want to detect "trending" queries in near-real-time (within 5 minutes).
Define "trending" as: a query's 5-minute search count is > 10× its typical
5-minute search count (based on the last 7 days at the same time of day).

(a) What data structure would you maintain in the stream processor?
    (Hint: you need to compare current window to historical baseline)
(b) A query surges from 10 searches/5min to 500 searches/5min. Is this trending?
(c) A query has 10,000 searches/5min normally and 15,000 searches/5min right now.
    Is this trending?
(d) Why is comparing to historical baseline (same time-of-day, same day-of-week)
    better than comparing to an overall average?

**Exercise 6: API Rate Limiting**
Your autocomplete endpoint receives 50,000 RPS normally. A bug in a client app
causes it to send 10 requests per second per user (no debouncing). With 500,000
affected users, this generates 5M RPS — 100× your normal load.

(a) How would you detect this is happening? (What metrics would spike?)
(b) Design a rate limit: per-IP, per-user, or both? What limits?
(c) The legitimate 50K RPS must continue unaffected. How do you distinguish
    legitimate traffic from the buggy client?
(d) What does the API return when a client is rate-limited? What HTTP status
    code and what response body?

---

**Exercise 7: Batch Job Failure Recovery**
Your nightly batch job ran successfully at 2 AM Tuesday and failed at 2 AM Wednesday
(a Spark executor ran out of memory on a large partition).

(a) At what stage did the job fail: aggregation, prefix generation, or Redis population?
    How would you tell from the job logs?
(b) Redis still has Tuesday's data. Users are getting slightly stale suggestions.
    Is this acceptable? For how long?
(c) You fix the memory issue (increase executor memory) and restart the job at 10 AM Wednesday.
    The job will read 30 days of logs again. Will it produce correct results?
    Is there any data duplication concern?
(d) How would you set up a job monitoring alert so you are notified within 30 minutes
    of a batch job failure?

**Exercise 8: Scaling from 1,000 to 100,000 QPS**
Your autocomplete service starts at 1,000 QPS and needs to scale to 100,000 QPS over
the next year as the product grows.

Current architecture: 3 API servers, 1 Redis primary + 1 replica, 1 Spark cluster (batch).

(a) At 10,000 QPS, what is the first bottleneck? (API servers? Redis? Network?)
    Calculate to justify your answer.
(b) At 50,000 QPS with a 60% in-process cache hit rate, how many Redis reads/second
    go to Redis? How many Redis instances do you need?
(c) At 100,000 QPS, you are sharding Redis across 5 instances. A single Redis
    instance handles prefix keys for letters "t" and "u" (15% of traffic = 15,000 RPS).
    Is this balanced? What would you do if "t" prefixes account for 12% alone?
(d) API server count at 100,000 QPS (assume 4,000 RPS per server)? What deployment
    strategy ensures zero-downtime scaling (rolling deploy, blue-green)?

## Homework

**Homework 1: Inspect Real Autocomplete**
Go to Google or DuckDuckGo and open your browser's developer tools (Network tab).
Start typing in the search box.

Observe:
- What is the API endpoint being called?
- How many requests per keystroke? Is there debouncing?
- What does the response JSON look like?
- How long does each request take (check the Timing tab)?
- Does the response include scores / ranking information?

Write a 1-paragraph analysis: what design choices can you infer from the observed behavior?

**Homework 2: Implement a Tiny In-Memory Trie**
In the language of your choice, implement a trie that supports:
- `insert(query, frequency)` — add a query with its frequency
- `get_suggestions(prefix, k=5)` — return top-K suggestions for the prefix

Then extend it: store top-K at each internal node (updated during insert).
Benchmark: how many operations per second can your trie handle for 1 million entries?
At what point does memory become an issue?

**Homework 3: Redis ZSET Experiment**
If you have Redis installed locally, run these commands and observe:

```
ZADD suggest:st 5200000 "stackoverflow"
ZADD suggest:st 4100000 "spotify"
ZADD suggest:st 2800000 "steam"
ZADD suggest:st 1900000 "snapchat"
ZADD suggest:st 1100000 "skype"

ZREVRANGE suggest:st 0 4 WITHSCORES
ZADD suggest:st 3500000 "starbucks"
ZREVRANGE suggest:st 0 4 WITHSCORES  ← does starbucks appear in top-5?

MEMORY USAGE suggest:st
```

How much memory does the key use? How does ZADD handle duplicates?
What command would you use to remove the lowest-scoring entry if you want to maintain
exactly top-K entries (hint: ZREMRANGEBYRANK)?

---

**Homework 4: Design a Personalized Autocomplete**
Current design: global suggestions (same for everyone). Now add personalization:
show suggestions from the user's own search history first, followed by global suggestions.

Design a complete solution:
- What new data store do you add? (User search history)
- What is the key schema? How many entries per user? What TTL?
- How does the API server merge personal + global suggestions?
- What happens for a new user (cold start) with no history?
- How do you handle privacy: user deletes their account → purge their history?
- Estimate storage: 10M users × last 20 searches × 30 bytes = ?

Write the modified GET /suggest endpoint pseudocode that handles personal + global blending.

---

## L5 vs L6 Answer Calibration Reference

| Question | L4 Answer | L5 Answer | L6 Answer |
|----------|-----------|-----------|-----------|
| Data structure? | "Trie" | "Prefix hash table in Redis ZSETs; trie is the concept but too memory-heavy at scale" | "Compressed trie with lazy evaluation OR prefix hash — depends on update frequency and latency SLA" |
| How to rank? | "By frequency" | "Frequency × recency weight from 30-day query logs; daily batch builds scores" | "CTR-adjusted frequency, seasonal signals, personalization re-ranking, ML ranker" |
| How to scale? | "Add more servers" | "Shard Redis by prefix key; in-process LRU covers 60% of traffic (Zipf); read replicas for redundancy" | "Consistent hashing with virtual nodes; hot key detection and automatic re-routing; adaptive TTL per key based on query velocity" |
| Freshness? | "Run batch more often" | "Separate streaming layer for trending (5-min window); daily batch for baseline; blend at serve time" | "Continuous pipeline ingesting query stream; probabilistic count-min sketch for real-time frequency estimation; merge with batch at configurable weight per prefix popularity tier" |
| Latency? | "Redis is fast" | "Latency budget: 20-50ms network + 3-8ms server. Redis < 1ms. LRU cache eliminates Redis for top 10K prefixes. Redis must be co-located with API servers." | "Geographic distribution: prefix store replicated to regional PoPs; client measures server response time and switches PoP if p99 > 80ms; adaptive prefetching for next predicted prefix" |

## What to Read Next

- **Ch102 — Typeahead / Autocomplete (Staff)**: The same system at full depth. Adds
  compressed trie internals, Spark offline pipeline, real-time trending with Flink,
  trigram-based typo correction, multi-language support, and sharding strategy.

- **Ch78 — News Feed (Staff)**: Related problem — serving personalized content fast.
  Similar Redis + fan-out patterns.

- **Ch75 sister chapter — Ch73 News Feed (L5)**: Next high-frequency L5 question.

- **Ch33 — Caching at Scale**: Deep dive on Redis, including ZSET internals, memory
  optimization, and eviction policies relevant to the prefix store.

---

---

## Interview Self-Check

Before your interview, make sure you can answer all of these without looking at notes:

**Data structure:**
- [ ] What is a trie? How does prefix search work in it?
- [ ] Why does a production system use a prefix hash table instead?
- [ ] What Redis data type stores the top-K suggestions per prefix?
- [ ] What Redis command retrieves the top-5 suggestions for a prefix?

**Building data:**
- [ ] Where do query frequencies come from?
- [ ] How often does the batch job run?
- [ ] What is recency weighting and why does it matter?
- [ ] What does the batch job output to Redis?

**Serving path:**
- [ ] What is debouncing and how does it reduce server load?
- [ ] What is the latency budget breakdown (network + server + return)?
- [ ] Why must Redis be in the same datacenter as the API server?
- [ ] What is the in-process LRU cache and why is it effective?

**Scaling:**
- [ ] How do you shard the Redis prefix store?
- [ ] What is the Zipf distribution and how does it affect cache strategy?
- [ ] What happens if Redis is unavailable?

**Trending:**
- [ ] Why does daily batch fail for viral queries?
- [ ] How does a stream processor detect trending queries?
- [ ] How do trending results get blended into API responses?

If you can answer all of these clearly and concisely, you are ready.

**Bonus check — numbers:**
- [ ] How much Redis memory for 10M prefixes × top-10? (~16 GB)
- [ ] What is the target p99 server latency? (< 20ms)
- [ ] How long is the lookback window for the batch job? (30 days)
- [ ] What debounce delay is standard? (100ms)
- [ ] What fraction of traffic do 1-3 char prefixes account for? (~60%)

**Bonus check — design decisions:**
- [ ] Why normalize to lowercase before computing prefix keys?
- [ ] Why use an EXPIRE TTL on Redis prefix keys?
- [ ] Why apply the blocklist at batch time, not at query time?
- [ ] Why is MAX_PREFIX_LENGTH typically 20 characters?
- [ ] Why use double-buffering (write to shadow Redis namespace before swapping)?

---

*Chapter 75 — Section 5: Senior SWE L5 Case Studies.*
*Pairs with: Ch102 (Typeahead Staff level), Ch33 (Caching/Redis internals), Ch73 (News Feed L5).*
*Last updated: 2026-06-25.*

---

<!-- END OF CHAPTER 75 -->
<!-- Total parts: 15 + Exercises + Homework + Interview Self-Check -->
<!-- Line count target: 2,000+ lines -->
<!-- Scope: L5 single-region. Skip: fuzzy matching, personalization, multi-language. Staff: Ch102. -->
<!-- Key data structures: Redis ZSET (sorted set), in-process LRU, Count-Min Sketch (trending) -->
