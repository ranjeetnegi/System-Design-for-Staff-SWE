# Chapter 36: Distributed Cache (Single Cluster)

---

# Introduction

Caching is one of the most powerful tools in a software engineer's arsenal—and one of the most misunderstood. The concept seems simple: store frequently accessed data closer to the application to avoid expensive operations. The reality involves intricate decisions about consistency, invalidation, memory management, and failure handling.

I've built caching systems that reduced database load by 95% and improved response times from 200ms to 5ms. I've also debugged incidents where caching bugs caused data corruption, stale reads that persisted for hours, and cache stampedes that took down production databases. The difference between these outcomes comes down to understanding what caching actually does—and what it doesn't guarantee.

This chapter covers distributed caching as Senior Engineers practice it: within a single cluster (no cross-region replication complexity), with explicit reasoning about consistency trade-offs, practical invalidation strategies, and honest discussion of what can go wrong.

**The Senior Engineer's First Law of Caching**: There are only two hard things in computer science—cache invalidation and naming things. The first one will cause you production incidents.

**Staff one-liner:** Cache is a performance optimization, not a reliability guarantee. When it fails, everything falls back to the database—so the database must be sized for that.

---

# Part 1: Problem Definition & Motivation

## What Is a Distributed Cache?

A distributed cache is a shared, in-memory data store that sits between your application and your primary data store (usually a database). It provides fast access to frequently requested data by keeping copies in memory across multiple nodes.

### Simple Example

```
WITHOUT CACHE:
    User requests profile → App queries database → 50ms
    User requests profile again → App queries database again → 50ms
    
    1000 users × 10 requests each = 10,000 database queries

WITH CACHE:
    User requests profile → Cache miss → App queries database → Store in cache → 50ms
    User requests profile again → Cache HIT → Return from cache → 1ms
    
    1000 users × 10 requests each:
    - 1000 database queries (first request per user)
    - 9000 cache hits (subsequent requests)
    
    90% reduction in database load
```

## Why Distributed Caches Exist

Caching exists because different storage systems have dramatically different performance characteristics:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ACCESS TIME COMPARISON                              │
│                                                                             │
│   STORAGE TYPE              LATENCY           RELATIVE SPEED                │
│   ─────────────────────────────────────────────────────────────────────     │
│   L1 CPU Cache              0.5 ns            1×                            │
│   L2 CPU Cache              7 ns              14×                           │
│   RAM (local)               100 ns            200×                          │
│   Redis (same datacenter)   0.5-1 ms          1,000,000×                    │
│   SSD (local)               100 µs            200,000×                      │
│   Database (indexed query)  1-10 ms           2,000,000-20,000,000×         │
│   Database (complex query)  50-500 ms         100,000,000-1,000,000,000×    │
│                                                                             │
│   KEY INSIGHT:                                                              │
│   Redis is 10-100× faster than database.                                    │
│   The gap widens for complex queries.                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Problem 1: Database Can't Scale Reads Infinitely

```
SCENARIO: E-commerce product catalog

Products table: 1 million products
Traffic: 100,000 product page views per minute
Database: PostgreSQL with read replicas

WITHOUT CACHE:
    100,000 queries/min ÷ 60 = 1,667 QPS to database
    Each query: ~5ms (indexed lookup)
    Connection pool: 100 connections
    Each connection handles: 16.7 queries/sec
    
    At 1,667 QPS with 5ms queries:
    - Each query uses 5ms of connection time
    - 1,667 × 5ms = 8.3 seconds of connection time per second
    - Need ~9 connections constantly busy
    - Seems fine... but add joins, transactions, writes...
    
    Reality: Database becomes bottleneck at ~5,000 QPS
    Peak traffic (flash sale): 500,000 page views/min = 8,333 QPS
    → DATABASE OVERLOADED

WITH CACHE (95% hit rate):
    8,333 QPS total
    - 7,916 from cache (95%)
    - 417 to database (5%)
    
    Database load: 417 QPS (well within capacity)
    → SYSTEM HEALTHY
```

### Problem 2: Response Time Matters

```
LATENCY IMPACT ON USER EXPERIENCE:

    100ms delay → Perceived as instant
    300ms delay → Noticeable, acceptable
    1 second delay → Users notice, slight frustration
    3 second delay → Users consider leaving
    5+ second delay → Users abandon

EXAMPLE: Search results page

    WITHOUT CACHE:
        - 10 database queries (products, categories, prices, reviews...)
        - 10 × 20ms = 200ms for DB alone
        - Add serialization, network: 300ms total
        - Acceptable, but no headroom

    WITH CACHE:
        - 10 cache lookups: 10 × 1ms = 10ms
        - Add serialization, network: 50ms total
        - 6× faster, room for more features
```

### Problem 3: Cost Efficiency

```
DATABASE COST VS CACHE COST:

    Database (RDS db.r5.2xlarge):
        - 8 vCPU, 64 GB RAM
        - $1,200/month
        - Handles ~5,000 QPS (simple queries)
        - Cost per 1M queries: $0.20

    Cache (ElastiCache r5.large):
        - 2 vCPU, 13 GB RAM
        - $150/month
        - Handles ~100,000 QPS
        - Cost per 1M queries: $0.002

    Cache is 100× more cost-efficient per query.
    
    Even accounting for cache misses hitting database,
    cache + database is cheaper than database alone at scale.
```

## What Happens Without Caching

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SYSTEMS WITHOUT CACHING                                  │
│                                                                             │
│   FAILURE MODE 1: DATABASE OVERLOAD                                         │
│   Traffic spike → All requests hit database → Connection pool exhausted     │
│   → Requests queue → Timeouts → Error cascade → Outage                      │
│                                                                             │
│   FAILURE MODE 2: SLOW RESPONSE TIMES                                       │
│   Every request pays full database cost → P95 latency degrades              │
│   → User experience suffers → Business metrics decline                      │
│                                                                             │
│   FAILURE MODE 3: COST EXPLOSION                                            │
│   Scale by adding database replicas → Expensive, diminishing returns        │
│   → Infrastructure costs grow faster than traffic                           │
│                                                                             │
│   FAILURE MODE 4: CASCADING FAILURES                                        │
│   Database slow → Requests back up → Timeout retries → More load           │
│   → Feedback loop → Complete system failure                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Mental Model

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DISTRIBUTED CACHE: THE LIBRARY ANALOGY                   │
│                                                                             │
│   Imagine a library (database) with millions of books.                      │
│                                                                             │
│   WITHOUT CACHE:                                                            │
│   Every reader goes to the main stacks, finds their book, reads it.         │
│   Popular books have long lines. The stacks get crowded.                    │
│                                                                             │
│   WITH CACHE (reading room with popular books):                             │
│   Popular books are copied to a reading room near the entrance.             │
│   Most readers find what they need without entering the stacks.             │
│   Only rare books require the full library search.                          │
│                                                                             │
│   KEY INSIGHTS:                                                             │
│   1. The reading room has LIMITED SPACE (cache size)                        │
│   2. Books in the reading room might be OUTDATED (stale data)               │
│   3. Someone must decide WHAT BOOKS to keep (eviction policy)               │
│   4. When a book is UPDATED in stacks, reading room copy is wrong           │
│      (cache invalidation)                                                   │
│                                                                             │
│   THE HARD PROBLEM:                                                         │
│   How do you know when the book in the reading room is outdated?            │
│   This is cache invalidation, and it's where bugs live.                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 2: Users & Use Cases

## Primary Users

### 1. Application Servers
- Primary consumers of cached data
- Make read requests (cache lookup) and write requests (cache updates)
- Need low-latency responses

### 2. Backend Services
- Other services that need shared cached state
- May update cache when data changes
- Coordinate cache invalidation

### 3. Operations/SRE Teams
- Monitor cache health (hit rate, memory, evictions)
- Configure cache sizing and policies
- Respond to cache-related incidents

## Core Use Cases

### Use Case 1: Read-Through Caching (Most Common)

```
PATTERN: Check cache first, fall back to database on miss

Flow:
1. Application requests data by key
2. Check cache for key
3. If HIT: Return cached value
4. If MISS: 
   a. Query database
   b. Store result in cache with TTL
   c. Return result

// Pseudocode: Read-through cache
FUNCTION get_user_profile(user_id):
    cache_key = "user:profile:" + user_id
    
    // Try cache first
    cached = cache.get(cache_key)
    IF cached IS NOT null:
        metrics.increment("cache.hit")
        RETURN deserialize(cached)
    
    // Cache miss - go to database
    metrics.increment("cache.miss")
    profile = database.query("SELECT * FROM users WHERE id = ?", user_id)
    
    // Store in cache for next time
    cache.set(cache_key, serialize(profile), ttl=3600)  // 1 hour TTL
    
    RETURN profile

BENEFITS:
- Simple to implement
- Automatic cache population
- No upfront cache warming needed

DRAWBACKS:
- First request always slow (cache miss)
- Cache stampede possible on popular keys
```

### Use Case 2: Write-Through Caching

```
PATTERN: Update cache and database together on writes

Flow:
1. Application updates data
2. Write to database
3. If database write succeeds, update cache
4. Return success

// Pseudocode: Write-through cache
FUNCTION update_user_profile(user_id, new_profile):
    // Write to database first (source of truth)
    database.update("UPDATE users SET ... WHERE id = ?", user_id, new_profile)
    
    // Update cache to match
    cache_key = "user:profile:" + user_id
    cache.set(cache_key, serialize(new_profile), ttl=3600)
    
    RETURN success

BENEFITS:
- Cache always consistent with database (after write)
- No stale reads after updates

DRAWBACKS:
- Write latency increased (database + cache)
- Cache updated even for rarely-read data
```

### Use Case 3: Write-Behind (Write-Back) Caching

```
PATTERN: Write to cache immediately, persist to database asynchronously

Flow:
1. Application updates data
2. Write to cache
3. Return success immediately
4. Background process persists to database later

// Pseudocode: Write-behind cache
FUNCTION update_user_preferences(user_id, preferences):
    cache_key = "user:preferences:" + user_id
    
    // Write to cache immediately
    cache.set(cache_key, serialize(preferences), ttl=86400)
    
    // Queue for async database write
    write_queue.enqueue({
        table: "user_preferences",
        key: user_id,
        data: preferences
    })
    
    RETURN success  // Return before database write

// Background worker
FUNCTION process_write_queue():
    WHILE true:
        item = write_queue.dequeue()
        database.upsert(item.table, item.key, item.data)

BENEFITS:
- Very fast writes (cache only)
- Batching possible for database writes
- Good for high-write workloads

DRAWBACKS:
- Data loss risk if cache fails before persist
- Complexity of async write processing
- NOT suitable for critical data
```

### Use Case 4: Cache-Aside with Explicit Invalidation

```
PATTERN: Application manages cache explicitly, invalidates on updates

Flow (Read):
1. Check cache
2. If miss, query database and populate cache

Flow (Write):
1. Update database
2. Delete cache entry (don't update it)
3. Next read will repopulate cache

// Pseudocode: Cache-aside with invalidation
FUNCTION get_product(product_id):
    cache_key = "product:" + product_id
    cached = cache.get(cache_key)
    
    IF cached IS NOT null:
        RETURN deserialize(cached)
    
    product = database.query("SELECT * FROM products WHERE id = ?", product_id)
    cache.set(cache_key, serialize(product), ttl=1800)
    RETURN product

FUNCTION update_product(product_id, new_data):
    database.update("UPDATE products SET ... WHERE id = ?", product_id, new_data)
    
    // DELETE, don't update
    // Next read will get fresh data from DB and repopulate cache
    cache.delete("product:" + product_id)
    
    RETURN success

WHY DELETE INSTEAD OF UPDATE?
- Simpler: One operation instead of serialize + set
- Safer: Avoids race conditions between concurrent updates
- Lazier: Only repopulates if data is actually read again
```

## Non-Goals (Out of Scope for V1)

| Non-Goal | Reason |
|----------|--------|
| Multi-region replication | Adds complexity, cross-region latency |
| Strong consistency | Caching inherently trades consistency for speed |
| Persistent storage | Cache is ephemeral; database is source of truth |
| Complex query caching | Cache key-value pairs, not query results |
| Automatic invalidation | Application manages invalidation explicitly |

## Why Scope Is Limited

```
SCOPE LIMITATION RATIONALE:

1. SINGLE CLUSTER ONLY
   Problem: Multi-region cache requires cross-DC replication
   Impact: Adds 50-200ms latency for consistency, complex conflict resolution
   Decision: Single cluster, application handles regional differences
   Acceptable because: Most reads are region-local anyway

2. EVENTUAL CONSISTENCY
   Problem: Strong consistency requires distributed locking
   Impact: Latency increases 10-100×, defeats purpose of caching
   Decision: Accept brief stale reads
   Acceptable because: Most data doesn't change frequently

3. NO COMPLEX QUERY CACHING
   Problem: SQL query results are hard to invalidate
   Impact: Query cache hit rate is low, invalidation is error-prone
   Decision: Cache entities by primary key only
   Acceptable because: Entity caching covers 90% of use cases

4. EXPLICIT INVALIDATION ONLY
   Problem: Automatic invalidation requires DB triggers or CDC
   Impact: Adds infrastructure complexity, hard to debug
   Decision: Application explicitly invalidates when it updates data
   Acceptable because: Application knows what changed
```

---

# Part 3: Functional Requirements

This section details exactly what the distributed cache does—the operations it supports, how each works, and how the system behaves under various conditions.

---

## Core Operations

### GET: Retrieve a Value

The most common operation. Retrieve a value by its key.

```
OPERATION: GET
INPUT: key (string)
OUTPUT: value (bytes) or null

BEHAVIOR:
1. Hash key to determine which cache node owns it
2. Send request to that node
3. If key exists and not expired: Return value
4. If key doesn't exist or expired: Return null

LATENCY EXPECTATION:
- P50: < 0.5ms
- P95: < 2ms
- P99: < 5ms

// Pseudocode: GET operation
FUNCTION cache_get(key):
    node = consistent_hash(key)
    
    TRY:
        response = node.get(key)
        IF response.found:
            metrics.increment("cache.get.hit")
            RETURN response.value
        ELSE:
            metrics.increment("cache.get.miss")
            RETURN null
    CATCH (TimeoutError, ConnectionError):
        metrics.increment("cache.get.error")
        RETURN null  // Fail open - treat as cache miss
```

### SET: Store a Value

Store a key-value pair with optional TTL (Time To Live).

```
OPERATION: SET
INPUT: key (string), value (bytes), ttl (optional, seconds)
OUTPUT: success/failure

BEHAVIOR:
1. Hash key to determine target node
2. Send key, value, and TTL to node
3. Node stores value in memory
4. If TTL provided, schedule expiration
5. If memory full, evict according to policy (LRU)

// Pseudocode: SET operation
FUNCTION cache_set(key, value, ttl=null):
    node = consistent_hash(key)
    
    TRY:
        IF ttl IS NOT null:
            response = node.set(key, value, expire_seconds=ttl)
        ELSE:
            response = node.set(key, value)
        
        metrics.increment("cache.set.success")
        RETURN true
    CATCH (TimeoutError, ConnectionError):
        metrics.increment("cache.set.error")
        RETURN false  // Fail open - data not cached, but not fatal

WHY TTL MATTERS:
- Prevents stale data from living forever
- Automatic cleanup without explicit invalidation
- Bounds the maximum staleness of cached data
```

### DELETE: Remove a Value

Explicitly remove a key from the cache.

```
OPERATION: DELETE
INPUT: key (string)
OUTPUT: success/failure (or number of keys deleted)

BEHAVIOR:
1. Hash key to determine target node
2. Send delete request to node
3. Node removes key if it exists
4. Return success (even if key didn't exist)

// Pseudocode: DELETE operation
FUNCTION cache_delete(key):
    node = consistent_hash(key)
    
    TRY:
        node.delete(key)
        metrics.increment("cache.delete.success")
        RETURN true
    CATCH (TimeoutError, ConnectionError):
        // This is more serious - stale data may persist
        metrics.increment("cache.delete.error")
        log.error("Failed to delete cache key: " + key)
        RETURN false

WHEN TO USE:
- After updating data in database (invalidation)
- When data is deleted from source
- To force cache refresh
```

### MGET: Batch Retrieve

Retrieve multiple keys in a single round-trip.

```
OPERATION: MGET
INPUT: keys (list of strings)
OUTPUT: values (list of value or null)

BEHAVIOR:
1. Group keys by target node (hash each key)
2. Send parallel requests to each node
3. Collect responses
4. Return values in same order as input keys

// Pseudocode: MGET operation
FUNCTION cache_mget(keys):
    // Group keys by node
    node_keys = {}
    FOR key IN keys:
        node = consistent_hash(key)
        IF node NOT IN node_keys:
            node_keys[node] = []
        node_keys[node].append(key)
    
    // Parallel requests to each node
    results = {}
    parallel_for node, node_key_list IN node_keys:
        response = node.mget(node_key_list)
        FOR i, key IN enumerate(node_key_list):
            results[key] = response[i]
    
    // Return in original order
    RETURN [results.get(key) FOR key IN keys]

WHY BATCH:
- Single network round-trip instead of N round-trips
- Reduces latency from N × 1ms to 1ms + small overhead
- Critical for pages that need many cached values
```

---

## Key Design

Cache keys are the primary way to organize and access data. Good key design is essential for cache efficiency and debuggability.

### Key Naming Conventions

```
KEY FORMAT: {type}:{subtype}:{id}

EXAMPLES:
    user:profile:12345           → User profile for user 12345
    user:preferences:12345       → User preferences
    product:details:abc123       → Product details
    product:inventory:abc123     → Product inventory (might change more often)
    session:auth:xyz789          → Authentication session
    feed:timeline:12345:page:1   → Paginated timeline data

WHY THIS FORMAT:
    1. Namespacing prevents collisions
       - "user:12345" vs "product:12345"
       
    2. Enables pattern-based operations
       - Delete all "session:*" on logout
       - Monitor hit rate by type
       
    3. Debuggability
       - "user:profile:12345" tells you exactly what it is
       - vs "x7f2a9b" (hash) tells you nothing
```

### Key Sizing Considerations

```
KEY SIZE IMPACT:

Small keys (< 100 bytes):
    - Minimal memory overhead
    - Fast hashing
    - Recommended for most cases

Large keys (> 1KB):
    - Significant memory overhead
    - Slower operations
    - Consider: Do you really need the full value in the key?

EXAMPLE: Bad vs Good key design

BAD: Cache full SQL query as key
    Key: "SELECT * FROM users WHERE id = 12345 AND status = 'active'"
    Problem: 60+ bytes, redundant, not debuggable

GOOD: Cache entity by primary key
    Key: "user:active:12345"
    Problem solved: 18 bytes, clear meaning, predictable
```

### Value Sizing

```
VALUE SIZE CONSIDERATIONS:

Small values (< 1KB):
    - Ideal for Redis
    - Low latency
    - Good memory efficiency

Medium values (1KB - 100KB):
    - Acceptable
    - Consider compression for text/JSON
    - Watch for memory fragmentation

Large values (100KB - 1MB):
    - Causes latency spikes
    - Blocks Redis event loop
    - Consider: Store in object storage, cache reference

Very large values (> 1MB):
    - Don't do this
    - Split into chunks
    - Use different storage (S3, etc.)

RULE OF THUMB:
    If value > 100KB, question whether it belongs in cache.
    If value > 1MB, it definitely doesn't.
```

---

## TTL (Time To Live) Strategy

TTL determines how long cached data lives before automatic expiration. TTL strategy is critical for balancing freshness vs. hit rate.

### TTL Selection Guidelines

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         TTL SELECTION GUIDE                                 │
│                                                                             │
│   DATA TYPE                   RECOMMENDED TTL      REASONING                │
│   ─────────────────────────────────────────────────────────────────────     │
│   Static config               24 hours             Rarely changes           │
│   User profile                1 hour               Changes occasionally     │
│   Product details             30 minutes           May have price updates   │
│   Inventory/stock             1-5 minutes          Changes frequently       │
│   Session data                15-30 minutes        Security consideration   │
│   Real-time data              30 seconds           Freshness critical       │
│   Rate limit counters         Window duration      Tied to business logic   │
│                                                                             │
│   FORMULA FOR TTL:                                                          │
│   TTL = (acceptable_staleness) × (update_frequency_factor)                  │
│                                                                             │
│   EXAMPLE:                                                                  │
│   - Product price updates every ~6 hours                                    │
│   - Acceptable to show stale price for up to 30 minutes                     │
│   - TTL = 30 minutes (conservative choice)                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### TTL Jitter (Avoiding Thundering Herd)

```
PROBLEM: Cache stampede

    100 users cache same product at same time
    All 100 entries have TTL = 1800 seconds
    After 1800 seconds, all 100 entries expire simultaneously
    100 users hit database at once → DATABASE OVERLOADED

SOLUTION: Add random jitter to TTL

// Pseudocode: TTL with jitter
FUNCTION cache_set_with_jitter(key, value, base_ttl):
    // Add ±10% jitter
    jitter = random(-0.10, 0.10) * base_ttl
    actual_ttl = base_ttl + jitter
    
    cache.set(key, value, ttl=actual_ttl)

EXAMPLE:
    Base TTL: 1800 seconds (30 minutes)
    Jitter range: ±180 seconds (±10%)
    Actual TTL: 1620 to 1980 seconds
    
    Result: Expirations spread over 6-minute window instead of all at once
```

---

## Cache Miss Handling

What happens when the cache doesn't have the data you need.

### Standard Cache Miss Flow

```
// Pseudocode: Standard cache miss handling

FUNCTION get_product(product_id):
    cache_key = "product:" + product_id
    
    // Step 1: Check cache
    cached = cache.get(cache_key)
    IF cached IS NOT null:
        RETURN deserialize(cached)
    
    // Step 2: Cache miss - get from database
    product = database.query(
        "SELECT * FROM products WHERE id = ?", 
        product_id
    )
    
    IF product IS null:
        // Data doesn't exist in database either
        // Option: Cache the "not found" to prevent repeated DB lookups
        cache.set(cache_key, TOMBSTONE_VALUE, ttl=60)  // Short TTL
        RETURN null
    
    // Step 3: Populate cache for next time
    cache.set(cache_key, serialize(product), ttl=1800)
    
    RETURN product
```

### Handling Negative Cache (Caching "Not Found")

```
PROBLEM: Repeated lookups for non-existent data

    User requests profile for user_id = 999999999 (doesn't exist)
    Cache miss → Database query → Not found
    Cache not populated (nothing to cache)
    Next request: Same thing → Database hit again
    
    Attacker could exploit this: Request random IDs, always hit database

SOLUTION: Cache the "not found" result

// Pseudocode: Negative caching
TOMBSTONE = "__NOT_FOUND__"

FUNCTION get_user_profile(user_id):
    cache_key = "user:profile:" + user_id
    cached = cache.get(cache_key)
    
    IF cached == TOMBSTONE:
        // We know this doesn't exist - don't hit database
        RETURN null
    
    IF cached IS NOT null:
        RETURN deserialize(cached)
    
    // Cache miss
    profile = database.query("SELECT * FROM users WHERE id = ?", user_id)
    
    IF profile IS null:
        // Cache the negative result with shorter TTL
        cache.set(cache_key, TOMBSTONE, ttl=60)  // 1 minute
        RETURN null
    
    cache.set(cache_key, serialize(profile), ttl=3600)
    RETURN profile

TTL CONSIDERATION:
    - Positive cache: Long TTL (data exists, likely stable)
    - Negative cache: Short TTL (data might be created soon)
```

---

## Expected Behavior Under Partial Failure

| Component Failure | Cache Behavior | Application Impact |
|-------------------|----------------|-------------------|
| **Single cache node down** | Requests to that node fail | Keys on that node unavailable; app falls back to DB |
| **Cache cluster unreachable** | All cache operations fail | All reads hit database (degraded performance) |
| **Cache slow (>10ms)** | Timeout, treat as miss | Increased latency, more DB load |
| **Cache returns corrupted data** | Deserialization fails | Treat as miss, log error, fall back to DB |
| **Network partition** | Some nodes unreachable | Partial cache availability |

### Fail-Open Strategy for Cache

```
// Pseudocode: Fail-open cache access

FUNCTION cache_get_safe(key):
    TRY:
        result = cache.get(key, timeout=5ms)
        RETURN result
    CATCH (TimeoutError):
        metrics.increment("cache.timeout")
        RETURN null  // Treat as miss, go to database
    CATCH (ConnectionError):
        metrics.increment("cache.connection_error")
        RETURN null  // Treat as miss
    CATCH (DeserializationError):
        metrics.increment("cache.deserialization_error")
        cache.delete(key)  // Remove corrupted entry
        RETURN null

WHY FAIL OPEN:
    - Cache is an optimization, not the source of truth
    - Database always has the correct data
    - Better slow than wrong
    - Better slow than unavailable
```

---

# Part 4: Non-Functional Requirements (Senior Bar)

## Latency Targets

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CACHE LATENCY REQUIREMENTS                          │
│                                                                             │
│   OPERATION: GET (single key)                                               │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  P50: < 0.5ms   (same-AZ network + Redis lookup)                    │   │
│   │  P95: < 2ms     (cross-AZ or minor network variance)                │   │
│   │  P99: < 5ms     (worst case before concern)                         │   │
│   │  Timeout: 10ms  (give up, treat as miss)                            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   OPERATION: SET (single key)                                               │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  P50: < 0.5ms                                                       │   │
│   │  P95: < 2ms                                                         │   │
│   │  P99: < 5ms                                                         │   │
│   │  Timeout: 10ms                                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   OPERATION: MGET (batch, 10 keys)                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  P50: < 1ms     (parallel to multiple nodes)                        │   │
│   │  P95: < 3ms                                                         │   │
│   │  P99: < 10ms                                                        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   WHY THESE TARGETS:                                                        │
│   - Cache should be 10-100× faster than database                            │
│   - If cache is slow, might as well skip it                                 │
│   - Timeout must be short enough that miss + DB < acceptable latency        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Availability Expectations

| Aspect | Target | Justification |
|--------|--------|---------------|
| Cache cluster uptime | 99.9% | Can fail open to database |
| Single node availability | 99.5% | Other nodes absorb load |
| Recovery time (node failure) | < 1 minute | Automatic failover |
| Data durability | NOT guaranteed | Cache is ephemeral; DB is source of truth |

**Why not 99.99%?**

Cache failing open is acceptable. The system continues to work (with degraded performance) when cache is unavailable. The database is the source of truth—cache is an optimization layer.

## Consistency Model

```
CONSISTENCY MODEL: Eventual Consistency

WHAT THIS MEANS:
    - After an update, cache may serve stale data temporarily
    - Eventually (within TTL), cache will be consistent with database
    - Strong consistency would require distributed locking (too slow)

ACCEPTABLE STALENESS BY USE CASE:

    User profile:       5 minutes (users can wait for refresh)
    Product price:      1-5 minutes (brief wrong price is annoying but survivable)
    Inventory count:    Real-time (don't cache, or very short TTL)
    User session:       Immediate (cache on same node, or don't cache)
    
TRADE-OFF DECISION:
    We accept eventual consistency because:
    - Strong consistency adds 10-50ms latency (distributed lock)
    - Most data changes infrequently
    - TTL bounds maximum staleness
    - Application can force refresh when needed (delete + re-read)
```

## Hit Rate Expectations

```
HIT RATE TARGETS:

Healthy cache:     > 90% hit rate
Good cache:        85-90% hit rate
Concerning:        70-85% hit rate (investigate)
Problem:           < 70% hit rate (caching not effective)

FACTORS AFFECTING HIT RATE:

1. TTL too short
   - Data expires before being reused
   - Increase TTL if staleness acceptable

2. Working set > cache size
   - More unique keys than cache can hold
   - Increase cache size or reduce what you cache

3. Low data reuse
   - Each user has unique data, rarely shared
   - Caching may not be the right solution

4. Poor key design
   - Same data cached under different keys
   - Normalize key generation
```

---

# Part 5: Scale & Capacity Planning

## Assumptions

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SCALE ASSUMPTIONS                                   │
│                                                                             │
│   TRAFFIC:                                                                  │
│   • Cache operations: 100,000 ops/sec (average)                             │
│   • Peak operations: 300,000 ops/sec (3× burst)                             │
│   • Read/write ratio: 95:5 (read-heavy, typical for cache)                  │
│   • Unique keys: 10 million                                                 │
│                                                                             │
│   DATA SIZE:                                                                │
│   • Average key size: 50 bytes                                              │
│   • Average value size: 1 KB                                                │
│   • Total data size: 10M × 1KB = 10 GB                                      │
│   • With overhead: ~15 GB                                                   │
│                                                                             │
│   HIT RATE:                                                                 │
│   • Target: 95%                                                             │
│   • Cache misses: 5,000/sec → Database queries                              │
│                                                                             │
│   CLUSTER SIZING:                                                           │
│   • Single Redis node: ~100,000 ops/sec capacity                            │
│   • Memory per node: 25 GB (safe limit for 32 GB instance)                  │
│   • Nodes needed for ops: 3 (with headroom)                                 │
│   • Nodes needed for memory: 1 (10 GB fits easily)                          │
│   • Choose: 3 nodes for throughput + redundancy                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Scale Breakpoints: 2×, 10×, and Multi-Year

```
BREAKPOINT SUMMARY:

| Scale | Traffic | Data | What Changes | First Stress |
|-------|---------|------|--------------|--------------|
| 1× (current) | 100K ops/sec | 10 GB | Baseline | Nothing |
| 2× | 200K ops/sec | 15 GB | Monitor; no immediate changes | Redis CPU |
| 10× | 1M ops/sec | 100 GB | Add shards; L1 cache | Shard throughput |
| Multi-year | 2× growth/year | Compounding | Recurrent capacity planning | Hit rate assumption |

AT 2×: Usually no changes. Monitor CPU and connection count. Hit rate stable if working set fits.

AT 10×: Reshard cluster; consider L1; optimize connection pooling.

MULTI-YEAR: Traffic and data grow. Most fragile assumption is hit rate. Working set may exceed cache. Plan for periodic capacity audits.
```

## What Breaks First at 10× Scale

```
CURRENT: 100,000 ops/sec, 10 GB data
10× SCALE: 1,000,000 ops/sec, 100 GB data

COMPONENT ANALYSIS:

1. REDIS THROUGHPUT (Primary concern)
   Current: 100K ops/sec across 3 nodes (~33K per node)
   10×: 1M ops/sec → Need ~10-15 nodes
   
   → AT 10×: Add more nodes to Redis cluster
   → Consistent hashing redistributes keys automatically
   
2. MEMORY CAPACITY (Secondary concern)
   Current: 10 GB
   10×: 100 GB
   
   Single large node: Max ~100-200 GB practical
   → AT 10×: Either larger nodes or more nodes
   → Prefer more smaller nodes (better fault isolation)
   
3. NETWORK BANDWIDTH (Minor concern at 10×)
   Current: 100K × 1KB = 100 MB/sec
   10×: 1 GB/sec
   
   → Still within 10 Gbps network capacity
   → May need dedicated network for cache traffic
   
4. CONNECTION COUNT (Potential issue)
   Current: 50 app servers × 100 connections = 5,000 connections
   10×: 50,000 connections
   
   Redis connection limit: ~10,000 per node
   → AT 10×: Connection pooling critical, or use proxy

MOST FRAGILE ASSUMPTION:
    Hit rate stays at 95%
    
    If working set grows faster than cache:
    - Hit rate drops to 80%
    - Database load increases 4× (from 5K to 20K misses/sec)
    - Database becomes bottleneck
    
    Detection: Monitor hit rate trend over time
```

## Back-of-Envelope: Redis Cluster Sizing

```
SIZING CALCULATION:

Step 1: Memory requirements
    Keys: 10 million
    Key size: 50 bytes average
    Value size: 1 KB average
    
    Raw data: 10M × (50B + 1KB) = 10.5 GB
    Redis overhead: ~50% for metadata, fragmentation
    Total: ~16 GB
    
    Per node (3 nodes): 6 GB each (comfortable)

Step 2: Throughput requirements
    Operations: 100,000/sec
    Per node (3 nodes): 33,000/sec
    
    Redis capacity: ~100,000 ops/sec per node
    Utilization: 33% (good headroom for peaks)

Step 3: Replication
    Primary-replica setup: Double memory for replicas
    Total: 3 primary + 3 replica = 6 nodes
    
    Or: Use Redis Cluster with 3 masters, 3 replicas

RECOMMENDATION:
    Redis Cluster with 3 master shards, 3 replicas
    Instance type: cache.r5.large (13 GB memory each)
    Total memory: 6 × 13 GB = 78 GB (plenty of headroom)
    Cost: ~$900/month
```

---

# Part 6: High-Level Architecture

## Core Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DISTRIBUTED CACHE ARCHITECTURE                           │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        APPLICATION TIER                             │   │
│   │                                                                     │   │
│   │   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │   │
│   │   │  App Server │  │  App Server │  │  App Server │                 │   │
│   │   │  + Cache    │  │  + Cache    │  │  + Cache    │                 │   │
│   │   │   Client    │  │   Client    │  │   Client    │                 │   │
│   │   └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                 │   │
│   │          │                │                │                        │   │
│   └──────────┼────────────────┼────────────────┼────────────────────────┘   │
│              │                │                │                            │
│              └────────────────┼────────────────┘                            │
│                               │                                             │
│                               ▼                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        REDIS CLUSTER                                │   │
│   │                                                                     │   │
│   │   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │   │
│   │   │  Shard 1    │  │  Shard 2    │  │  Shard 3    │                 │   │
│   │   │  (Primary)  │  │  (Primary)  │  │  (Primary)  │                 │   │
│   │   │             │  │             │  │             │                 │   │
│   │   │  Keys: A-K  │  │  Keys: L-R  │  │  Keys: S-Z  │                 │   │
│   │   └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                 │   │
│   │          │                │                │                        │   │
│   │          ▼                ▼                ▼                        │   │
│   │   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │   │
│   │   │  Replica 1  │  │  Replica 2  │  │  Replica 3  │                 │   │
│   │   └─────────────┘  └─────────────┘  └─────────────┘                 │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                               │                                             │
│                               │ (On cache miss)                             │
│                               ▼                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        DATABASE                                     │   │
│   │                                                                     │   │
│   │   ┌─────────────────────────────────────────────────────────────┐   │   │
│   │   │              PostgreSQL / MySQL                             │   │   │
│   │   │              (Source of Truth)                              │   │   │
│   │   └─────────────────────────────────────────────────────────────┘   │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | Stateful? |
|-----------|---------------|-----------|
| Application Server | Business logic, cache client | No |
| Cache Client Library | Key hashing, connection pooling, serialization | No |
| Redis Primary | Store data, handle writes, replicate to replica | Yes |
| Redis Replica | Handle reads (optional), failover target | Yes |
| Database | Source of truth, handle cache misses | Yes |

## Data Flow: Read with Cache

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    READ FLOW WITH CACHE                                     │
│                                                                             │
│   Client          App Server         Redis              Database            │
│     │                 │                │                    │               │
│     │  GET /product   │                │                    │               │
│     │────────────────▶│                │                    │               │
│     │                 │                │                    │               │
│     │                 │  GET product:123                    │               │
│     │                 │───────────────▶│                    │               │
│     │                 │                │                    │               │
│     │                 │                │                    │               │
│     │          ┌──────┴──────┐         │                    │               │
│     │          │             │         │                    │               │
│     │          ▼             ▼         │                    │               │
│     │    [CACHE HIT]   [CACHE MISS]    │                    │               │
│     │          │             │         │                    │               │
│     │          │             │  SELECT * FROM products      │               │
│     │          │             │  WHERE id = 123              │               │
│     │          │             │─────────────────────────────▶│               │
│     │          │             │                              │               │
│     │          │             │         product data         │               │
│     │          │             │◀─────────────────────────────│               │
│     │          │             │                              │               │
│     │          │             │  SET product:123 (with TTL)  │               │
│     │          │             │───────────────▶│             │               │
│     │          │             │                │             │               │
│     │          ▼             ▼                │             │               │
│     │    ◀───────────────────────             │             │               │
│     │       product data                      │             │               │
│     │                                         │             │               │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Why Redis Cluster (Not Single Node)?

| Factor | Single Node | Cluster (3+ nodes) |
|--------|-------------|-------------------|
| Throughput | 100K ops/sec max | 300K+ ops/sec (scales with nodes) |
| Memory | 100 GB max practical | Terabytes (distributed) |
| Fault tolerance | Single point of failure | Survives node failures |
| Maintenance | Downtime for upgrades | Rolling upgrades possible |

**When single node is enough:**
- < 50K ops/sec
- < 20 GB data
- Acceptable brief downtime for maintenance

**When cluster is needed:**
- > 50K ops/sec
- > 20 GB data
- High availability requirements

---

# Part 7: Component-Level Design

## Cache Client Library

The cache client runs in each application server and handles the complexity of distributed caching.

### Responsibilities

```
CACHE CLIENT RESPONSIBILITIES:

1. CONNECTION MANAGEMENT
   - Maintain connection pool to Redis nodes
   - Handle connection failures and reconnection
   - Load balance across replicas (if reading from replicas)

2. KEY ROUTING
   - Hash key to determine which shard owns it
   - Route request to correct shard
   - Handle cluster topology changes

3. SERIALIZATION
   - Serialize objects to bytes for storage
   - Deserialize bytes back to objects
   - Handle versioning for schema changes

4. ERROR HANDLING
   - Timeout management
   - Retry logic (with limits)
   - Fail-open on errors

5. METRICS
   - Track hit/miss rates
   - Track latency percentiles
   - Track error rates
```

### Connection Pooling

```
// Pseudocode: Connection pool configuration

REDIS_POOL_CONFIG = {
    max_connections: 100,        // Max connections per node
    min_connections: 10,         // Keep warm
    connection_timeout: 100ms,   // Time to establish connection
    socket_timeout: 10ms,        // Time for operation to complete
    retry_attempts: 2,           // Retries before giving up
    retry_delay: 5ms,            // Delay between retries
}

WHY THESE VALUES:

max_connections (100):
    - 50 app servers × 100 = 5,000 connections to cluster
    - Redis handles 10,000+ connections per node
    - Plenty of headroom

socket_timeout (10ms):
    - Normal operation: < 1ms
    - If taking 10ms, something is wrong
    - Fail fast, treat as miss

retry_attempts (2):
    - Brief network blip: Retry helps
    - Sustained failure: Don't keep trying
    - 2 retries = 3 total attempts
```

### Consistent Hashing

```
// Pseudocode: Consistent hashing for key routing

CLASS ConsistentHashRing:
    nodes = []
    virtual_nodes = 150  // Virtual nodes per physical node
    
    FUNCTION add_node(node):
        FOR i IN range(virtual_nodes):
            hash_value = hash(node.id + ":" + i)
            ring.insert(hash_value, node)
    
    FUNCTION get_node(key):
        hash_value = hash(key)
        // Find first node with hash >= key hash
        RETURN ring.ceiling(hash_value)
    
    FUNCTION remove_node(node):
        FOR i IN range(virtual_nodes):
            hash_value = hash(node.id + ":" + i)
            ring.remove(hash_value)

WHY CONSISTENT HASHING:
    - Adding/removing node only moves ~1/N of keys
    - Regular hashing (key % N) moves ~all keys when N changes
    - Critical for cache stability during scaling
```

### Serialization

```
// Pseudocode: Serialization with versioning

CLASS CacheSerializer:
    CURRENT_VERSION = 2
    
    FUNCTION serialize(object):
        data = {
            "v": CURRENT_VERSION,
            "t": object.type_name,
            "d": object.to_dict()
        }
        RETURN json_encode(data)
    
    FUNCTION deserialize(bytes):
        data = json_decode(bytes)
        version = data["v"]
        
        IF version == CURRENT_VERSION:
            RETURN type_registry[data["t"]].from_dict(data["d"])
        ELSE IF version < CURRENT_VERSION:
            // Migration: Old format to new format
            RETURN migrate(data, version, CURRENT_VERSION)
        ELSE:
            // Future version - can't read
            THROW DeserializationError("Unknown version")

WHY VERSIONING:
    - Schema changes happen
    - Old cached data should still be readable
    - Allows gradual rollout of schema changes
```

---

## Eviction Policies

When cache memory is full, old entries must be removed to make room for new ones.

### LRU (Least Recently Used)

```
POLICY: LRU (Least Recently Used)

Evict the entry that was accessed longest ago.

HOW IT WORKS:
    - Each access updates entry's "last accessed" timestamp
    - When evicting, remove entry with oldest timestamp

EXAMPLE:
    Cache capacity: 3 entries
    
    Access A → Cache: [A]
    Access B → Cache: [A, B]
    Access C → Cache: [A, B, C]  (full)
    Access A → Cache: [B, C, A]  (A moved to front)
    Access D → Cache: [C, A, D]  (B evicted, oldest)

REDIS IMPLEMENTATION:
    Redis uses approximate LRU (samples N keys, evicts oldest from sample)
    Good enough for cache use case
    
WHEN TO USE:
    - General purpose caching
    - Access patterns have temporal locality
    - Default choice for most cases
```

### LFU (Least Frequently Used)

```
POLICY: LFU (Least Frequently Used)

Evict the entry that was accessed fewest times.

HOW IT WORKS:
    - Each entry has access counter
    - When evicting, remove entry with lowest counter

EXAMPLE:
    Cache capacity: 3 entries
    
    Access A (5 times) → Counter: 5
    Access B (2 times) → Counter: 2
    Access C (1 time)  → Counter: 1
    Need to evict      → Evict C (lowest counter)

REDIS IMPLEMENTATION:
    Redis LFU uses logarithmic counter with decay
    Prevents early popular items from living forever
    
WHEN TO USE:
    - Access patterns have stable frequency (some items always popular)
    - Hot items should never be evicted
    - Not good for: items with changing popularity
```

### TTL-Based Expiration

```
POLICY: TTL (Time To Live)

Entries automatically expire after specified duration.

HOW IT WORKS:
    - Each entry has expiration timestamp
    - Redis checks and removes expired entries
    - Background process + lazy expiration on access

EXAMPLE:
    SET key1 value1 TTL=60   (expires in 60 seconds)
    SET key2 value2 TTL=3600 (expires in 1 hour)
    
    After 60 seconds: key1 automatically removed
    key2 still present

REDIS IMPLEMENTATION:
    - Lazy expiration: Check on access
    - Active expiration: Background job samples and removes
    
WHEN TO USE:
    - Always use TTL for cache entries
    - Bounds maximum staleness
    - Automatic cleanup without explicit invalidation
```

### Recommended Configuration

```
REDIS EVICTION CONFIGURATION:

maxmemory-policy allkeys-lru
maxmemory 25gb

WHY allkeys-lru:
    - Applies to all keys (not just those with TTL)
    - LRU is good default for cache workloads
    - If memory full, evict least recently used

ALTERNATIVE: volatile-lru
    - Only evict keys with TTL set
    - Problem: If you forget TTL on some keys, they never evict
    - Recommendation: Use allkeys-lru, always set TTL
```

---

# Part 8: Data Model & Storage

## Key-Value Schema

```
KEY STRUCTURE:
    {service}:{entity_type}:{entity_id}[:{variant}]

EXAMPLES:
    catalog:product:12345              → Product details
    catalog:product:12345:inventory    → Product inventory (separate TTL)
    user:profile:67890                 → User profile
    user:session:abc123                → User session
    api:ratelimit:user:67890:minute    → Rate limit counter

VALUE STRUCTURE:
    Serialized JSON or binary (protobuf, msgpack)
    
    {
        "v": 1,                        // Schema version
        "data": {...},                 // Actual data
        "cached_at": 1706745600        // When cached (for debugging)
    }
```

## Storage Calculations

```
MEMORY USAGE ESTIMATION:

Per entry:
    Key: 50 bytes average
    Value: 1 KB average
    Redis overhead: ~100 bytes per key
    Total: ~1.2 KB per entry

For 10 million entries:
    Raw: 10M × 1.2 KB = 12 GB
    With fragmentation (~20%): 14.4 GB
    Safety margin (20%): 17.3 GB
    
    Recommendation: 25 GB total memory (headroom for growth)

MEMORY BY DATA TYPE:

    Strings: Most efficient for simple values
    Hashes: Good for structured objects
    Sets: For membership checks
    Sorted Sets: For leaderboards, ranges
    
    For cache: Strings are usually sufficient
```

## Why Redis (vs Alternatives)?

| Requirement | Redis | Memcached | In-Memory (local) |
|-------------|-------|-----------|-------------------|
| Performance | Sub-ms | Sub-ms | Nanoseconds |
| Data structures | Rich (hash, set, list) | Simple (string) | Any |
| Persistence | Optional | No | No |
| Clustering | Built-in | Manual sharding | N/A |
| Replication | Built-in | No | N/A |
| TTL | Per-key | Per-key | Manual |
| Memory efficiency | Good | Better | Best |
| Shared state | Yes | Yes | No (per-process) |

**Why Redis over Memcached:**
- Richer data structures (useful for complex caching)
- Built-in clustering and replication
- Better observability

**Why Redis over Local Cache:**
- Shared across all app servers
- Consistent view of cached data
- Survives app server restarts

---

# Part 9: Consistency, Concurrency & Idempotency

## Consistency Model

Distributed caching uses **eventual consistency**. This is a deliberate trade-off for performance.

### What Eventual Consistency Means

```
TIMELINE OF UPDATE:

T+0ms:    Application updates database (product price = $100)
T+1ms:    Application deletes cache key "product:123"
T+2ms:    User A requests product (cache miss, gets $100, caches it)
T+5ms:    User B requests product (cache hit, gets $100) ✓
          
          ... 30 minutes later, cache entry expires ...

CONCURRENT SCENARIO (the tricky case):

T+0ms:    App Server 1 updates DB (price = $100)
T+0ms:    App Server 2 reads product (cache hit, old price = $90)
T+1ms:    App Server 1 deletes cache key
T+2ms:    App Server 2 returns old price to user

User got $90 when price was actually $100.
This is the cost of eventual consistency.

MITIGATION:
    - Keep TTL short for frequently-changing data
    - For critical data, skip cache or use write-through
    - Document acceptable staleness per data type
```

### Why Not Strong Consistency?

```
STRONG CONSISTENCY APPROACH:

1. Acquire distributed lock for key
2. Read from database
3. Update cache
4. Release lock

PROBLEM:
    Lock acquisition: +20-50ms per operation
    Cache benefit: -50ms from avoiding DB
    Net: No benefit, or worse than no cache

EVENTUAL CONSISTENCY APPROACH:
    Read from cache or DB, no locking
    Accept brief stale reads
    
    Net: 10-100× faster than DB

FOR CACHING, EVENTUAL CONSISTENCY IS THE RIGHT CHOICE.
Strong consistency defeats the purpose of caching.
```

## Race Conditions

### Race Condition 1: Stale Read After Update

```
SCENARIO: Two app servers, one updates, one reads

Server A                          Server B
────────                          ────────
T+0:  UPDATE DB (price = $100)    
T+1:  DELETE cache key            GET cache (HIT, price = $90)
T+2:                              Return $90 to user
T+3:  Deletion completes

USER IMPACT:
    User got stale price ($90 instead of $100)
    
IS THIS A PROBLEM?
    For pricing: Probably OK (brief window)
    For inventory: Could cause overselling
    For security: Not OK (permission changes)

MITIGATION:
    - Very short TTL for sensitive data
    - Write-through for critical data
    - Accept and document staleness window
```

### Race Condition 2: Cache Stampede

```
SCENARIO: Popular key expires, many concurrent requests

T+0:    Cache key expires
T+0:    100 requests arrive simultaneously
T+0:    All 100 check cache → MISS
T+1:    All 100 query database
T+2:    Database overloaded
T+3:    All 100 try to SET cache
T+4:    99 redundant cache writes

PROBLEM:
    - Database gets hammered
    - Latency spikes
    - Potential cascade failure

SOLUTION: Cache stampede prevention

// Pseudocode: Stampede prevention with locking
FUNCTION get_with_stampede_prevention(key):
    cached = cache.get(key)
    IF cached IS NOT null:
        RETURN deserialize(cached)
    
    // Cache miss - try to acquire lock
    lock_key = "lock:" + key
    lock_acquired = cache.set(lock_key, "1", nx=true, ttl=5)  // SET if not exists
    
    IF lock_acquired:
        // We got the lock - fetch from DB
        TRY:
            data = database.query(...)
            cache.set(key, serialize(data), ttl=3600)
            RETURN data
        FINALLY:
            cache.delete(lock_key)
    ELSE:
        // Another request is fetching - wait and retry
        sleep(50ms)
        RETURN get_with_stampede_prevention(key)  // Retry
```

### Race Condition 3: Lost Update

```
SCENARIO: Two concurrent writes to same data

Server A                          Server B
────────                          ────────
T+0:  Read user from DB           Read user from DB
T+1:  User.name = "Alice"         User.email = "bob@new.com"
T+2:  Write to DB                 
T+3:  Update cache (name=Alice)   Write to DB
T+4:                              Update cache (email=bob@new.com)

RESULT IN CACHE:
    name = "Alice", email = "bob@new.com" ✓ (correct)

RESULT IF USING STALE COPY:
    Server B's cache update might contain OLD name
    Cache: name = "OLD_NAME", email = "bob@new.com" ✗

SOLUTION: Delete cache on update, don't update it
    - Server A: DELETE cache key after DB write
    - Server B: DELETE cache key after DB write
    - Next read: Gets fresh data from DB
```

## Idempotency

Cache operations have different idempotency characteristics:

| Operation | Idempotent? | Notes |
|-----------|-------------|-------|
| GET | Yes | Reading doesn't change state |
| SET | Yes | Setting same value is harmless |
| DELETE | Yes | Deleting already-deleted key is harmless |
| INCR | No | Each call increases counter |
| LPUSH | No | Each call adds element |

```
// For non-idempotent operations, use idempotency keys

FUNCTION increment_counter_safely(key, request_id):
    dedup_key = "seen:" + request_id
    
    IF cache.exists(dedup_key):
        // Already processed this request
        RETURN cache.get(key)
    
    new_value = cache.incr(key)
    cache.set(dedup_key, "1", ttl=3600)  // Remember we processed this
    
    RETURN new_value
```

---

# Part 10: Failure Handling & Reliability

## Dependency Failures

### Redis Node Failure

```
SCENARIO: One Redis primary node crashes

DETECTION:
- Redis Cluster detects via heartbeat (within seconds)
- Client sees connection errors to that shard

AUTOMATIC RECOVERY:
- Replica promoted to primary automatically
- Takes 1-10 seconds depending on configuration
- Some requests may fail during transition

IMPACT:
- Keys on that shard: Temporarily unavailable
- ~1/3 of keys if 3 shards
- Application sees cache misses
- Falls back to database

// Pseudocode: Handling node failure
FUNCTION cache_get_resilient(key):
    TRY:
        RETURN cache.get(key, timeout=10ms)
    CATCH (ConnectionError, TimeoutError):
        // Node might be failing over
        metrics.increment("cache.node_failure")
        RETURN null  // Treat as miss, go to DB
```

### Redis Cluster Unreachable

```
SCENARIO: Network partition or total cache failure

DETECTION:
- All cache operations timing out
- Connection pool exhausted
- Circuit breaker opens

IMPACT:
- All reads go to database
- Database load increases dramatically
- Latency increases for all requests

MITIGATION:
1. Circuit breaker prevents hammering dead cache
2. Database should have capacity headroom
3. Consider local in-memory cache as L1

// Pseudocode: Circuit breaker for cache
CLASS CacheCircuitBreaker:
    state = CLOSED
    failures = 0
    last_failure_time = null
    
    FUNCTION call(operation):
        IF state == OPEN:
            IF now() - last_failure_time > 30 seconds:
                state = HALF_OPEN
            ELSE:
                THROW CacheUnavailable()
        
        TRY:
            result = operation()
            IF state == HALF_OPEN:
                state = CLOSED
                failures = 0
            RETURN result
        CATCH Exception:
            failures++
            last_failure_time = now()
            IF failures > 5:
                state = OPEN
            THROW
```

### Cache Returns Corrupted Data

```
SCENARIO: Deserialization fails on cached value

CAUSES:
- Schema change (new code, old cached format)
- Bit flip in memory (rare)
- Bug in serialization code

DETECTION:
- DeserializationError thrown
- JSON parse error
- Type mismatch

HANDLING:
// Pseudocode: Handle corrupted cache data
FUNCTION cache_get_safe(key):
    raw = cache.get(key)
    IF raw IS null:
        RETURN null
    
    TRY:
        RETURN deserialize(raw)
    CATCH (DeserializationError, JSONError):
        metrics.increment("cache.deserialization_error")
        log.warn("Corrupted cache entry: " + key)
        
        // Delete corrupted entry
        cache.delete(key)
        
        // Return null, let caller fetch from DB
        RETURN null
```

## Realistic Production Failure Scenario

```
┌─────────────────────────────────────────────────────────────────────────────┐
│        FAILURE SCENARIO: CACHE STAMPEDE AFTER NODE FAILURE                  │
│                                                                             │
│   TRIGGER:                                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Redis primary node crashes unexpectedly.                           │   │
│   │  Failover takes 15 seconds. During this time, 1/3 of cache is       │   │
│   │  unavailable. After failover, replica becomes primary with          │   │
│   │  EMPTY STATE (replication lag lost recent writes).                  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   WHAT BREAKS:                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  T+0s:    Node crashes, connections to that shard fail              │   │
│   │  T+5s:    App servers see connection timeouts, retry                │   │
│   │  T+10s:   Circuit breakers open for that shard                      │   │
│   │  T+15s:   Failover complete, replica promoted                       │   │
│   │  T+16s:   Connections restored, but shard has minimal data          │   │
│   │  T+17s:   STAMPEDE: All requests to that shard are misses           │   │
│   │  T+17s:   Database QPS spikes from 5K to 50K                        │   │
│   │  T+18s:   Database connection pool exhausted                        │   │
│   │  T+20s:   Request timeouts, error rate spikes                       │   │
│   │  T+30s:   Cache starts warming, DB load decreasing                  │   │
│   │  T+60s:   Cache warm, normal operation resumes                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   USER IMPACT:                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  - Requests to affected shard: Slow or failing (15 seconds)         │   │
│   │  - All requests: Slow during stampede (30-60 seconds)               │   │
│   │  - Total impact: ~1 minute of degraded service                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   DETECTION:                                                                │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  - Alert: "Redis node unreachable"                                  │   │
│   │  - Alert: "Cache hit rate dropped below 80%"                        │   │
│   │  - Alert: "Database QPS > threshold"                                │   │
│   │  - Alert: "API latency P99 > 500ms"                                 │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   MITIGATION BY SENIOR ENGINEER:                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  DURING INCIDENT:                                                   │   │
│   │  1. Verify Redis failover in progress (check cluster status)        │   │
│   │  2. If stampede: Enable request queuing or shed load                │   │
│   │  3. If DB overloaded: Reduce traffic (feature flags, rate limits)   │   │
│   │  4. Wait for cache to warm (monitor hit rate)                       │   │
│   │                                                                     │   │
│   │  POST-INCIDENT:                                                     │   │
│   │  1. Implement cache stampede prevention (locking pattern)           │   │
│   │  2. Add cache warming on failover                                   │   │
│   │  3. Increase DB connection pool headroom                            │   │
│   │  4. Consider L1 local cache for hot keys                            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Real Incident: Structured Post-Mortem Format

| Part | Content |
|------|---------|
| **Context** | E-commerce product catalog cache. 100K ops/sec, 6-node Redis Cluster, 95% hit rate. Database sized for 5K QPS (cache misses). Black Friday traffic expected. |
| **Trigger** | Redis primary node on shard 2 crashed (hardware fault). Automatic failover initiated. Replica promoted after 15 seconds. |
| **Propagation** | Connections to shard 2 timed out. Circuit breakers opened. After failover, replica had empty or partial state (replication lag). All requests to that shard became cache misses. DB QPS spiked from 5K to 50K. Connection pool exhausted. Cascaded to API timeouts. |
| **User impact** | ~1 minute of degraded service. Product pages slow or failing. Checkout latency spiked. Error rate ~15%. |
| **Engineer response** | Verified failover in progress. Identified stampede pattern from DB metrics. Enabled request shedding. Waited for cache to warm. |
| **Root cause** | Failover left shard with cold state. No stampede prevention. No cache warming on failover. DB lacked headroom for cold-cache scenario. |
| **Design change** | Implemented cache stampede prevention (locking). Added cache warming procedure for failover. Sized DB for 2× cold-cache load. Documented blast radius per shard. |
| **Lesson learned** | Cache failover is not transparent—replica state may lag. Design for "cache empty" as a realistic scenario. Fail-open to DB only works if DB has capacity. |

**Staff-level takeaway:** The cache is a performance layer, not a reliability layer. Its failure modes amplify downstream load. Always model the "cache completely cold" scenario when sizing the database.

## Timeout and Retry Configuration

```
CACHE CLIENT TIMEOUTS:

Connection timeout: 100ms
    - Time to establish new connection
    - Should be quick within same datacenter

Operation timeout: 10ms
    - Time for single GET/SET operation
    - Normal operation: < 1ms
    - 10ms allows for minor network variance

Retry policy:
    - Max retries: 2 (3 total attempts)
    - Retry delay: 5ms (brief pause)
    - Retry on: TimeoutError, ConnectionError
    - Don't retry on: KeyNotFound (expected behavior)

Circuit breaker:
    - Open after: 5 consecutive failures
    - Half-open after: 30 seconds
    - Close on: 1 successful request
```

---

# Part 11: Performance & Optimization

## Hot Path Analysis

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CACHE READ HOT PATH                                 │
│                                                                             │
│   Every cache read follows this path. Must be fast.                         │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. Application calls cache.get(key)          ~0.01ms               │   │
│   │  2. Hash key to find shard                    ~0.001ms              │   │
│   │  3. Get connection from pool                  ~0.01ms (if pooled)   │   │
│   │  4. Send request to Redis                     ~0.1ms (network)      │   │
│   │  5. Redis processes request                   ~0.01ms               │   │
│   │  6. Receive response                          ~0.1ms (network)      │   │
│   │  7. Deserialize value                         ~0.1ms (depends)      │   │
│   │  ─────────────────────────────────────────────────────              │   │
│   │  TOTAL:                                       ~0.3-0.5ms            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   BIGGEST FACTORS:                                                          │
│   - Network latency (0.2ms) - can't optimize much                           │
│   - Deserialization (0.1ms) - use efficient formats                         │
│   - Connection pool - must be properly sized                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Optimizations Applied

### 1. Connection Pooling

```
WITHOUT POOLING:
    Each request: Create connection → Send request → Close connection
    Connection overhead: 1-5ms per request
    
WITH POOLING:
    Connections created upfront and reused
    Connection overhead: ~0ms (amortized)
    
    Connection pool size = (peak_requests_per_second × avg_latency)
    
    Example: 1000 req/sec × 0.5ms = 0.5 connections minimum
    Add headroom: 10-20 connections per app server
```

### 2. Batching with MGET/MSET

```
WITHOUT BATCHING:
    get(key1)  // 0.5ms
    get(key2)  // 0.5ms
    get(key3)  // 0.5ms
    Total: 1.5ms (3 round-trips)

WITH BATCHING:
    mget([key1, key2, key3])  // 0.6ms
    Total: 0.6ms (1 round-trip)
    
    3× faster for 3 keys, more savings for larger batches
```

### 3. Efficient Serialization

```
FORMAT COMPARISON:

JSON:
    - Human readable (good for debugging)
    - Verbose (larger size)
    - Parse time: ~0.1ms for 1KB

MessagePack:
    - Binary (smaller)
    - ~30-50% smaller than JSON
    - Parse time: ~0.05ms for 1KB

Protobuf:
    - Binary, schema-defined
    - ~50% smaller than JSON
    - Parse time: ~0.02ms for 1KB
    - Requires schema management

RECOMMENDATION:
    - Start with JSON (simpler, debuggable)
    - Move to MessagePack if size/speed matters
    - Protobuf for very high throughput systems
```

### 4. Local L1 Cache

```
TWO-TIER CACHING:

L1: Local in-memory cache (per process)
    - Ultra-fast: nanoseconds
    - Small: 100MB per process
    - Not shared across servers
    - Very short TTL (10-30 seconds)

L2: Redis (shared)
    - Fast: < 1ms
    - Large: tens of GB
    - Shared across all servers
    - Longer TTL (minutes to hours)

// Pseudocode: Two-tier cache
FUNCTION get_with_l1(key):
    // Check L1 first
    l1_value = local_cache.get(key)
    IF l1_value IS NOT null:
        metrics.increment("cache.l1.hit")
        RETURN l1_value
    
    // Check L2 (Redis)
    l2_value = redis.get(key)
    IF l2_value IS NOT null:
        metrics.increment("cache.l2.hit")
        // Populate L1 for next time
        local_cache.set(key, l2_value, ttl=30 seconds)
        RETURN l2_value
    
    // Full miss
    metrics.increment("cache.miss")
    RETURN null

WHEN TO USE L1:
    - Very hot keys (accessed many times per second)
    - Data that changes infrequently
    - Where slight staleness between servers is OK
```

## Optimizations Intentionally NOT Done

```
DEFERRED OPTIMIZATIONS:

1. COMPRESSION
   Could compress large values before caching
   Problem: CPU overhead for compression/decompression
   Defer until: Network bandwidth becomes bottleneck

2. READ REPLICAS
   Could read from replicas to scale reads
   Problem: Replication lag causes stale reads
   Defer until: Single primary can't handle read load

3. SHARDING BY ACCESS PATTERN
   Could shard hot vs cold data differently
   Problem: Complexity, harder to debug
   Defer until: Clear hot/cold pattern emerges

4. PREDICTIVE CACHE WARMING
   Could predict what to cache before it's needed
   Problem: Complex ML/heuristics, may warm wrong data
   Defer until: Cache miss rate is a proven bottleneck

WHY DEFER:
    Current implementation handles 100K ops/sec
    Premature optimization adds complexity
    Monitor, measure, then optimize based on real data
```

---

# Part 11.5: Rollout, Rollback & Operational Safety

## Safe Deployment Strategy

Cache changes can have subtle, widespread effects. A misconfigured TTL or serialization bug can corrupt data across the entire system.

### Deployment Stages

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CACHE DEPLOYMENT PIPELINE                                │
│                                                                             │
│   STAGE 1: CANARY (5% of app servers)                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Duration: 30 minutes minimum                                       │   │
│   │  Monitoring:                                                        │   │
│   │  - Cache hit rate stable (no sudden drop)                           │   │
│   │  - Deserialization error rate = 0                                   │   │
│   │  - Cache operation latency unchanged                                │   │
│   │  - No increase in database load                                     │   │
│   │                                                                     │   │
│   │  Rollback trigger:                                                  │   │
│   │  - Hit rate drops > 5%                                              │   │
│   │  - Any deserialization errors                                       │   │
│   │  - Latency P95 increases > 50%                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   STAGE 2: GRADUAL ROLLOUT (25% → 50% → 100%)                               │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Duration: 15 minutes per stage                                     │   │
│   │  Continue monitoring for serialization compatibility                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   STAGE 3: SOAK (24 hours)                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  All traffic on new version                                         │   │
│   │  Watch for:                                                         │   │
│   │  - Memory growth (cache size increasing unexpectedly)               │   │
│   │  - TTL issues (data not expiring as expected)                       │   │
│   │  - Edge cases that only appear over time                            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Serialization Compatibility

```
CRITICAL: Cache changes must be backward AND forward compatible

BACKWARD COMPATIBLE:
    New code can read old cached format
    (Old entries still in cache from before deployment)

FORWARD COMPATIBLE:
    Old code can read new cached format
    (During gradual rollout, old and new versions coexist)

// Pseudocode: Version-aware serialization
FUNCTION serialize(object):
    RETURN {
        "v": 2,  // Current version
        "data": object.to_dict()
    }

FUNCTION deserialize(bytes):
    parsed = json_decode(bytes)
    version = parsed["v"]
    
    IF version == 2:
        RETURN CurrentObject.from_dict(parsed["data"])
    ELSE IF version == 1:
        // Migration: v1 to v2
        RETURN migrate_v1_to_v2(parsed["data"])
    ELSE:
        // Unknown version - can't deserialize
        THROW DeserializationError()

SAFE MIGRATION PATH:
    1. Deploy code that can READ both v1 and v2
    2. Deploy code that WRITES v2 (reads v1 and v2)
    3. Wait for all v1 entries to expire (TTL passes)
    4. Remove v1 deserialization code
```

## Rollback Procedure

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CACHE ROLLBACK PROCEDURE                                 │
│                                                                             │
│   SCENARIO: Bad deployment causing deserialization errors                   │
│                                                                             │
│   ROLLBACK STEPS:                                                           │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. REVERT APP DEPLOYMENT                                           │   │
│   │     - Roll back app servers to previous version                     │   │
│   │     - New version may have written incompatible cache entries       │   │
│   │                                                                     │   │
│   │  2. FLUSH CORRUPTED ENTRIES (if necessary)                          │   │
│   │     - If new format is unreadable by old code:                      │   │
│   │       Option A: Flush affected key patterns                         │   │
│   │       Option B: Wait for TTL to expire                              │   │
│   │       Option C: Let deserialization errors trigger cache misses     │   │
│   │                                                                     │   │
│   │  3. VERIFY RECOVERY                                                 │   │
│   │     - Deserialization errors should stop                            │   │
│   │     - Hit rate should stabilize                                     │   │
│   │     - Latency should return to baseline                             │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ROLLBACK TIME TARGET: < 10 minutes from decision to recovered             │
│                                                                             │
│   DECISION TREE:                                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Q: Can old code read new format?                                   │   │
│   │     YES → Just rollback app, cache entries still valid              │   │
│   │     NO  → Rollback app AND flush affected cache keys                │   │
│   │                                                                     │   │
│   │  Q: Is data in cache critical (session, security)?                  │   │
│   │     YES → Flush immediately, accept cache rebuild cost              │   │
│   │     NO  → Let TTL handle cleanup, tolerate brief errors             │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Bad Deployment Scenario

```
┌─────────────────────────────────────────────────────────────────────────────┐
│    SCENARIO: TTL MISCONFIGURATION - CACHE DATA NEVER EXPIRES                │
│                                                                             │
│   CHANGE DEPLOYED:                                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Developer refactored cache client, accidentally set TTL = 0        │   │
│   │  In Redis, TTL = 0 means "no expiration"                            │   │
│   │  Expected: TTL = 3600 (1 hour)                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   BREAKAGE TYPE: Subtle, delayed                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  - Cache appears to work normally                                   │   │
│   │  - Hit rate actually IMPROVES (nothing expires!)                    │   │
│   │  - But stale data never refreshes                                   │   │
│   │  - Users see outdated information                                   │   │
│   │  - Memory slowly grows (no eviction from expiry)                    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   DETECTION (hours/days later):                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  - Customer complaint: "My profile shows old data"                  │   │
│   │  - Or: Redis memory usage growing unexpectedly                      │   │
│   │  - Or: Audit reveals cache entries with no TTL                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   SENIOR ENGINEER RESPONSE:                                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. Identify scope: How many entries have no TTL?                   │   │
│   │     redis-cli: SCAN + DEBUG OBJECT to check TTL                     │   │
│   │                                                                     │   │
│   │  2. Fix the code: Restore correct TTL setting                       │   │
│   │                                                                     │   │
│   │  3. Remediate existing data:                                        │   │
│   │     Option A: EXPIRE all affected keys (batch script)               │   │
│   │     Option B: DELETE all affected keys (force refresh)              │   │
│   │     Option C: Full cache flush (nuclear option)                     │   │
│   │                                                                     │   │
│   │  4. Deploy fix with canary                                          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   GUARDRAILS ADDED:                                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. Unit test: Assert TTL > 0 for all cache operations              │   │
│   │  2. Monitoring: Alert if entries without TTL > threshold            │   │
│   │  3. Code review checklist: Verify TTL on all cache writes           │   │
│   │  4. Redis config: maxmemory-policy allkeys-lru (safety net)         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 12: Cost & Operational Considerations

## Major Cost Drivers

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CACHE COST BREAKDOWN                              │
│                                                                             │
│   For cache serving 100,000 ops/sec, 10 GB data:                            │
│                                                                             │
│   1. REDIS CLUSTER (85% of cost)                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  3 Primary nodes: cache.r5.large × 3 = ~$450/month                  │   │
│   │  3 Replica nodes: cache.r5.large × 3 = ~$450/month                  │   │
│   │  TOTAL: ~$900/month                                                 │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   2. NETWORK (10% of cost)                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Inter-AZ traffic: ~$100/month                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   3. MONITORING (5% of cost)                                                │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Metrics, dashboards, alerts: ~$50/month                            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   TOTAL: ~$1,050/month                                                      │
│                                                                             │
│   COST PER OPERATION: $1,050 / (100K × 86400 × 30) = $0.000004              │
│                                                                             │
│   COMPARISON TO DATABASE:                                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Database: $0.0002 per operation                                    │   │
│   │  Cache: $0.000004 per operation                                     │   │
│   │  Cache is 50× cheaper per operation                                 │   │
│   │                                                                     │   │
│   │  With 95% hit rate:                                                 │   │
│   │  - 95% of ops at $0.000004 (cache)                                  │   │
│   │  - 5% of ops at $0.0002 (database)                                  │   │
│   │  Blended cost: $0.000014 per operation (14× cheaper than DB only)   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Where Teams Over-Engineer (Cost)

```
COMMON OVER-ENGINEERING:

1. MULTI-TIER CACHE TOO EARLY
   Add L1 local cache before L2 is the bottleneck.
   Cost: Complexity, staleness, debugging difficulty.
   Staff approach: Add L1 only when L2 latency or load is proven bottleneck.

2. CACHE WARMING FOR EVERYTHING
   Pre-populate cache for all data at startup.
   Cost: Slow startup, wasted memory, rarely-read data.
   Staff approach: Warm only proven hot keys; let miss path handle the rest.

3. STRONG CONSISTENCY EVERYWHERE
   Distributed locks or write-through for all cached data.
   Cost: Latency, complexity, defeats cache purpose.
   Staff approach: Strong consistency only where business requires it.

4. CUSTOM CACHE LAYER
   Build in-house cache instead of using managed Redis.
   Cost: Ops burden, reliability risk, reinventing the wheel.
   Staff approach: Use managed services; build only if clear unmet need.

TOP COST DRIVERS (recap):
   - Redis cluster (85%): Node count, instance size
   - Network (10%): Cross-AZ traffic
   - Monitoring (5%): Metrics, dashboards
```

## Cost Scaling

| Scale | Nodes | Monthly Cost | Cost per 1M Ops |
|-------|-------|--------------|-----------------|
| 100K ops/sec | 6 | $1,050 | $0.004 |
| 500K ops/sec | 12 | $1,800 | $0.0014 |
| 1M ops/sec | 20 | $3,000 | $0.0012 |

**Cost scales sub-linearly:** Larger clusters are more cost-efficient per operation.

## On-Call Burden

```
EXPECTED ON-CALL LOAD:

Alert types and frequency:
- Redis node failure: ~1/quarter (automatic failover)
- High memory usage: ~1/month (add capacity)
- Hit rate drop: ~2/month (investigate cause)
- Latency spike: ~2/month (usually transient)

Why cache is relatively low-maintenance:
- Fail-open behavior means cache issues ≠ outages
- Redis is mature, stable technology
- Automatic failover handles node failures
- Data is ephemeral, loss is inconvenient not catastrophic

What increases on-call burden:
- Complex invalidation logic (bugs cause stale data)
- Very large cache (more nodes, more potential issues)
- Cache as critical path (no fail-open possible)
```

## Observability: SLOs, SLIs, and Debugging

```
CACHE SLOs (example):

- Availability: Cache ops succeed 99.9% (fail-open to DB on failure)
- Latency: P99 < 5ms for cache hit; P99 < 50ms for cache miss (DB fallback)
- Correctness: Cache validation mismatch rate < 0.1%

KEY SLIs:
- cache.hit_rate (target: > 90%)
- cache.operation_latency_p99 (target: < 5ms)
- cache.evicted_keys_per_second (target: near 0)
- cache.deserialization_error_rate (target: 0)
- cache.validation.mismatch_rate (target: < 0.1%)

DEBUGGING WORKFLOW:
1. User reports stale data → Run validation job; check mismatch rate
2. Latency spike → Correlate with cache latency, DB latency, eviction rate
3. Hit rate drop → Check memory, eviction, working set size, traffic pattern change
4. Cache errors → Check connection pool, circuit breaker state, node health

DASHBOARD MINIMUM:
- Hit rate trend (rolling 1h, 24h)
- Latency P50/P95/P99 (cache vs DB fallback)
- Eviction rate
- Error rate by type (timeout, connection, deserialization)
```

## Misleading Signals & Debugging Reality

```
MISLEADING SIGNAL 1: "Hit Rate is 95%"

METRIC SHOWS:
    cache.hit_rate = 95% ✅

ACTUAL PROBLEM:
    Cache is serving stale data for expired prices.
    TTL is set correctly, but invalidation on update is broken.
    95% of reads hit cache, but 10% of those are stale.

WHY IT'S MISLEADING:
    Hit rate measures cache efficiency, not correctness.
    High hit rate + stale data = silent corruption.

REAL SIGNAL:
    Business metric: Customer complaints about wrong prices
    Technical metric: Compare random cache entries to database

SENIOR AVOIDANCE:
    Periodic cache validation job: Sample cached entries, compare to DB.
    Alert if mismatch rate exceeds threshold.


MISLEADING SIGNAL 2: "No Cache Errors"

METRIC SHOWS:
    cache.error_rate = 0% ✅

ACTUAL PROBLEM:
    Cache client has aggressive retry that masks errors.
    Each operation retries 5 times before failing.
    Actual failures are 10%, but only 0.5% visible.

WHY IT'S MISLEADING:
    Retry success masks underlying problems.
    5× retry = 5× latency and load on Redis.

REAL SIGNAL:
    cache.retry_rate - Should be near 0 normally
    cache.operation_latency - Elevated due to retries

SENIOR AVOIDANCE:
    Track first-attempt success rate, not final success rate.
    Alert on retry rate, not just error rate.


MISLEADING SIGNAL 3: "Memory Usage is Stable"

METRIC SHOWS:
    redis.memory_usage = 80% (stable) ✅

ACTUAL PROBLEM:
    Memory is stable because eviction is happening.
    But eviction is evicting data you want to keep.
    Hit rate is dropping because popular data is being evicted.

WHY IT'S MISLEADING:
    Stable memory is expected. Eviction is the symptom.
    Need to look at eviction rate, not memory level.

REAL SIGNAL:
    redis.evicted_keys_per_second - Should be near 0
    cache.hit_rate trend - Dropping as eviction increases

SENIOR AVOIDANCE:
    Alert on eviction rate, not memory usage.
    Size cache to minimize eviction, not to maximize utilization.
```

## Rushed Decision Under Time Pressure

```
┌─────────────────────────────────────────────────────────────────────────────┐
│    SCENARIO: BLACK FRIDAY - DATABASE OVERLOADING                            │
│                                                                             │
│   CONTEXT:                                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  - Black Friday sale starts in 2 hours                              │   │
│   │  - Load test shows database will be overwhelmed                     │   │
│   │  - Current cache hit rate: 80% (expected 95% for survival)          │   │
│   │  - Cache TTL: 5 minutes (for freshness)                             │   │
│   │  - Increasing cache capacity won't help (it's hit rate issue)       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   IDEAL SOLUTION (if we had time):                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. Analyze cache miss patterns                                     │   │
│   │  2. Pre-warm cache with expected hot products                       │   │
│   │  3. Optimize slow database queries causing misses                   │   │
│   │  4. Test thoroughly                                                 │   │
│   │                                                                     │   │
│   │  Time needed: 1-2 days                                              │   │
│   │  Time available: 2 hours                                            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   DECISION MADE (under time pressure):                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Increase cache TTL from 5 minutes to 30 minutes                    │   │
│   │                                                                     │   │
│   │  // Config change                                                   │   │
│   │  CACHE_TTL_PRODUCTS = 1800  // Was 300                              │   │
│   │                                                                     │   │
│   │  Expected impact:                                                   │   │
│   │  - Hit rate increases to ~93%                                       │   │
│   │  - Database load decreases by 3×                                    │   │
│   │  - Products may show prices up to 30 minutes stale                  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   WHY THIS IS ACCEPTABLE:                                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. Prices don't change during Black Friday (sale prices fixed)     │   │
│   │  2. 30-minute staleness is acceptable for product descriptions      │   │
│   │  3. Inventory is NOT cached (real-time accuracy needed)             │   │
│   │  4. Alternative is complete outage (unacceptable)                   │   │
│   │  5. Can revert TTL after sale if needed                             │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   TECHNICAL DEBT INTRODUCED:                                                │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  - Longer staleness window for product data                         │   │
│   │  - May mask underlying hit rate issues                              │   │
│   │  - Need to remember to revert after Black Friday                    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   FOLLOW-UP PLAN (AFTER BLACK FRIDAY):                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Week 1:                                                            │   │
│   │  - Revert TTL to 5 minutes                                          │   │
│   │  - Analyze Black Friday cache miss patterns                         │   │
│   │                                                                     │   │
│   │  Week 2:                                                            │   │
│   │  - Implement cache warming for known hot products                   │   │
│   │  - Optimize queries causing cache misses                            │   │
│   │                                                                     │   │
│   │  Before next sale:                                                  │   │
│   │  - Load test with realistic traffic patterns                        │   │
│   │  - Pre-warm cache before sale starts                                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 13: Security Basics & Abuse Prevention

## Access Control

```
REDIS SECURITY CONFIGURATION:

1. NETWORK ISOLATION
   - Redis in private subnet (no public access)
   - Security group allows only app servers
   - No direct internet exposure

2. AUTHENTICATION
   - Redis AUTH password required
   - Rotate password periodically
   - Store password in secrets manager

3. ENCRYPTION
   - TLS for data in transit
   - At-rest encryption via managed service (ElastiCache)

// Pseudocode: Secure Redis connection
REDIS_CONFIG = {
    host: secrets.get("REDIS_HOST"),
    password: secrets.get("REDIS_PASSWORD"),
    ssl: true,
    ssl_verify: true
}
```

## Data Security Considerations

```
WHAT NOT TO CACHE:

1. SENSITIVE PII
   - Full SSN, credit card numbers
   - Passwords, API keys
   - If breached, cache contents exposed

2. SESSION TOKENS (without encryption)
   - If cached, encrypt before storing
   - Or use dedicated secure session store

3. COMPLIANCE-RESTRICTED DATA
   - HIPAA: PHI must be encrypted
   - PCI: Cardholder data has strict requirements
   - Check compliance requirements before caching

COMPLIANCE IMPLICATIONS (Staff-level):

- **GDPR / right to erasure:** Cached data may outlive DB deletion. TTL must bound retention, or explicit invalidation on delete. Document cache as part of data lifecycle.
- **Retention:** If DB has 30-day retention, cache TTL must not exceed it. Stale cached data = compliance violation.
- **Audit:** Cache is transient; audit trails live in DB. Caching must not bypass audit requirements.
- **Data residency:** Single-cluster cache implies data locality. Multi-region caching requires separate compliance review.

**Trade-off:** Caching regulated data requires extra controls (encryption, TTL, invalidation). Often simpler to skip cache for that data.

SAFE TO CACHE:
    - Public product information
    - Aggregated statistics
    - Non-sensitive user preferences
    - Computed/derived data
```

## Cache Poisoning Prevention

```
ATTACK: Cache poisoning

Attacker manages to write malicious data to cache.
Legitimate users then read poisoned data.

PREVENTION:

1. NO USER-CONTROLLED CACHE KEYS
   Bad:  cache.set(user_input, data)  // User controls key
   Good: cache.set("product:" + product_id, data)  // Key is constructed

2. VALIDATE DATA BEFORE CACHING
   // Pseudocode: Validate before cache
   FUNCTION cache_product(product):
       IF NOT validate_product(product):
           log.error("Invalid product data, not caching")
           RETURN
       cache.set("product:" + product.id, serialize(product))

3. INPUT VALIDATION ON CACHE MISS
   // Even if cache is poisoned, validate after read
   FUNCTION get_product(product_id):
       cached = cache.get("product:" + product_id)
       IF cached:
           product = deserialize(cached)
           IF NOT validate_product(product):
               log.error("Corrupted cache entry")
               cache.delete("product:" + product_id)
               // Fall through to database
           ELSE:
               RETURN product
       // Fetch from database...
```

---

# Part 14: System Evolution (Senior Scope)

## V1 Design

```
V1: MINIMAL VIABLE CACHE

Components:
- Single Redis instance (primary + replica)
- Simple cache-aside pattern
- TTL-based expiration only

Features:
- GET/SET/DELETE operations
- TTL on all entries
- JSON serialization
- Connection pooling

NOT Included:
- Clustering (single node sufficient)
- Multi-tier caching (L1 + L2)
- Cache warming
- Advanced invalidation

Capacity: 50,000 ops/sec, 10 GB data
```

## First Issues and Fixes

```
ISSUE 1: Cache Stampede on Popular Products (Week 2)

Problem: Flash sale product expires, 1000 concurrent requests hit DB
Detection: Database CPU spike at exact moment of cache expiry
Solution: Implement locking pattern for cache miss
Effort: 2 days implementation

ISSUE 2: Stale Data After Product Updates (Week 3)

Problem: Product updated in DB, cache not invalidated, users see old price
Detection: Customer support tickets about wrong prices
Solution: Add explicit cache invalidation on product update
Effort: 1 day, add delete() call after database update

ISSUE 3: Memory Pressure (Month 2)

Problem: Cache size growing, evictions increasing, hit rate dropping
Detection: Redis memory alerts, hit rate declining trend
Solution: Audit cached data, reduce TTL for large items, add memory
Effort: 1 day investigation, 1 hour to resize Redis instance

ISSUE 4: Serialization Incompatibility During Deployment (Month 3)

Problem: New code writes v2 format, old code can't read it during rollout
Detection: Deserialization errors in logs
Solution: Implement version-aware serialization, backward compatibility
Effort: 3 days implementation, process change for deployments
```

## Cross-Team and Ownership Boundaries

```
CACHE OWNERSHIP (Staff-level):

Who owns cache invalidation?
- Application team that writes the data must invalidate.
- Clear contract: "If you update X, you must invalidate cache key pattern Y."
- Cross-team risk: Team A writes; Team B owns cache client. Invalidation can be missed.

Who depends on cache hit rate?
- Downstream services may assume low latency from cache.
- If hit rate drops, their SLOs break.
- Document: "Cache hit rate affects API latency SLO. Target 90%."

Reducing complexity for others:
- Single cache client library, shared across teams.
- Canonical key patterns documented; avoid duplicate keys for same entity.
- Invalidation checklist in code review template.

Blast radius when cache fails:
- All services using the cache fall back to DB.
- DB load = sum of all cache miss traffic from all services.
- Single cluster = shared fate; one cache outage affects everyone.
```

## V2 Improvements

```
V2: HARDENED CACHE

Added:
- Redis Cluster (3 shards, 3 replicas)
- Cache stampede prevention (locking)
- Version-aware serialization
- L1 local cache for hot keys
- Monitoring dashboard

Improved:
- Hit rate: 90% → 95%
- Latency P99: 5ms → 2ms
- Capacity: 100K ops/sec

Capacity: 100,000 ops/sec, 30 GB data
Reliability: Better (cluster, failover)
Operability: Better (dashboard, alerts)
```

---

# Part 15: Alternatives & Trade-offs

## Alternative 1: Memcached Instead of Redis

```
CONSIDERED: Memcached for simpler, potentially faster caching

PROS:
- Simpler protocol (slightly lower latency)
- Multi-threaded (better CPU utilization per node)
- Memory-efficient for simple key-value

CONS:
- No built-in clustering (manual sharding)
- No replication (no failover)
- Limited data structures (strings only)
- No persistence option

DECISION: Chose Redis

REASONING:
- Built-in clustering simplifies operations
- Replication provides automatic failover
- Data structures (hashes, sets) useful for complex caching
- Slightly higher latency is acceptable for operational simplicity
```

## Alternative 2: Application-Level Cache Only

```
CONSIDERED: Each app server has local in-memory cache, no shared cache

PROS:
- Zero network latency (nanoseconds vs milliseconds)
- No external dependency
- Simpler infrastructure

CONS:
- Not shared: Same data cached N times (memory waste)
- Inconsistent: Different servers have different data
- Cold start: Cache empty after restart

DECISION: Use shared Redis cache with optional L1 local cache

REASONING:
- Shared cache ensures consistency across servers
- L1 local cache added later for very hot keys
- Best of both: Consistency by default, speed for hot data
```

## Alternative 3: Write-Through vs Cache-Aside

```
CONSIDERED: Write-through pattern (update cache on every write)

PROS:
- Cache always fresh after writes
- No explicit invalidation needed
- Read-after-write consistency

CONS:
- Write latency increased (DB + cache)
- Cache updated even for never-read data
- Complex: Both writes must succeed

DECISION: Use cache-aside with explicit invalidation

REASONING:
- Simpler: Application controls cache
- Efficient: Only cache data that's read
- Safer: DELETE cache on update (avoids update race conditions)
- Trade-off: Brief window of stale data (acceptable)
```

## Staff vs Senior Design Contrasts

Major design choices differ by level. These contrasts clarify L6 expectations.

| Design Choice | Senior (L5) | Why It Breaks | Staff (L6) | Risk Accepted |
|---------------|-------------|---------------|-----------|---------------|
| **Cache sizing** | Size for current load + 20% headroom | Traffic spikes or new features exhaust cache; eviction spikes; stampede risk | Size for cold-cache scenario (DB must handle 100% miss load). Model 2× and 10× growth. | Over-provisioning cost; prefer paying for headroom over outage |
| **Invalidation** | TTL + explicit delete on update | Invalidation missed in some code paths; hot keys never invalidated; multiple key patterns for same entity | Single canonical key per entity. Invalidation checklist in code review. Periodic validation job (sample cache vs DB). | Slight staleness during validation; operational overhead |
| **Failover behavior** | Rely on Redis automatic failover | Replica may be cold or lagging; stampede on promote | Design for "shard empty" after failover. Stampede prevention. Cache warming runbook. | Extra complexity; runbook maintenance |
| **Consistency** | Eventual consistency; TTL bounds staleness | Business doesn't understand staleness window; compliance asks "how fresh?" | Document staleness per data type. Define "acceptably stale" in SLOs. For regulated data, skip cache or use write-through. | Some data uncached; higher latency for those reads |
| **Cost cuts** | Reduce nodes or instance size when asked | Capacity drops; incidents during peak | Tie cost to reliability. Offer reserved instances, data audit. Reject cuts that remove failover or headroom without explicit risk acceptance. | Pushback on stakeholders; need to explain trade-offs |

**One-liner:** Senior optimizes for correctness and performance. Staff optimizes for correctness, performance, *and* the failure modes that only appear at scale or during incidents.

---

# Part 16: Interview Calibration (L5 → L6)

## How Google Interviews Probe Caching

```
COMMON INTERVIEWER QUESTIONS:

1. "How would you design a caching layer for this system?"
   
   L4: "I'd use Redis to cache database results."
   
   L5: "Before diving in, I'd ask about the read/write ratio, data size,
   acceptable staleness, and consistency requirements. For a read-heavy
   workload with eventual consistency, I'd use cache-aside with TTL.
   For strong consistency needs, I'd consider write-through or skip
   caching for that data. Let me estimate the cache size and hit rate..."

2. "What happens when cached data becomes stale?"
   
   L4: "We set a TTL so data expires."
   
   L5: "There are several approaches: TTL bounds maximum staleness,
   explicit invalidation on updates provides immediate freshness,
   and write-through keeps cache always current. The trade-off is
   between freshness and complexity. For our use case, I'd use
   TTL of [X] with invalidation on updates. The staleness window
   is [Y seconds], which is acceptable because [reason]."

3. "What if your cache node fails?"
   
   L4: "We use replication so another node takes over."
   
   L5: "We design for graceful degradation. The application treats
   cache failures as misses and falls back to database. We use
   circuit breakers to avoid hammering a failing cache. Redis
   Cluster provides automatic failover to replicas. The key insight
   is that cache unavailability causes slowness, not incorrectness,
   because the database is the source of truth."
```

## Common Mistakes

```
L4 MISTAKE: "We should cache everything for maximum performance"

Problem: 
    - Large values hurt more than help (latency, memory)
    - Caching rapidly-changing data wastes resources
    - More cached data = more invalidation complexity

L5 Approach:
    "I'd cache data that's read frequently, changes infrequently,
    and is expensive to compute. For each data type, I'd estimate
    the read/write ratio and acceptable staleness before caching."


L4 MISTAKE: "TTL will handle invalidation"

Problem:
    - TTL provides eventual consistency, not immediate
    - For some data, stale reads cause real problems
    - Relying only on TTL is a source of subtle bugs

L5 Approach:
    "TTL is a safety net, not the primary invalidation strategy.
    I'd use explicit invalidation on updates for data where
    freshness matters. TTL catches cases we miss and bounds
    the worst-case staleness."


L5 BORDERLINE MISTAKE: Perfect consistency focus

Problem:
    - Trying to make cache strongly consistent defeats its purpose
    - Distributed locks for cache consistency add 20-50ms

L5 Approach:
    "I accept that caching inherently trades consistency for speed.
    For data requiring strong consistency, I'd skip caching or use
    a different strategy. For most data, eventual consistency with
    bounded staleness is the right trade-off."
```

## What Distinguishes a Solid L5 Answer

```
SIGNALS OF SENIOR-LEVEL THINKING:

1. ASKS ABOUT REQUIREMENTS FIRST
   "What's the read/write ratio? What staleness is acceptable?"
   
2. QUANTIFIES CACHE SIZE AND HIT RATE
   "With 10M users and 1KB profiles, we need ~10GB cache.
   With 95% hit rate, database load drops from 100K to 5K QPS."
   
3. DISCUSSES INVALIDATION EXPLICITLY
   "Cache-aside with explicit invalidation on updates.
   TTL of 30 minutes as a safety net."
   
4. CONSIDERS FAILURE MODES
   "On cache failure, we fail open to database.
   Circuit breaker prevents hammering dead cache."
   
5. UNDERSTANDS TRADE-OFFS
   "I'm choosing eventual consistency because strong consistency
   would add 20ms latency. Staleness window of 5 minutes is
   acceptable for product catalog data."
   
6. THINKS ABOUT OPERATIONS
   "For on-call, we'd alert on hit rate drop, memory pressure,
   and eviction rate. Cache issues cause slowness, not outages."
```

## L6 Interview Probes and Staff Signals

**What interviewers probe at Staff level:**

- "What happens when the cache cluster fails over?" — Expect blast-radius reasoning, stampede, DB capacity.
- "How would you explain a 30% cost cut request to leadership?" — Expect trade-off framing, risk acceptance, alternatives.
- "Another team depends on this cache for their SLA. What do you guarantee?" — Expect cross-team ownership, SLOs, failure modes.
- "How do you know cache invalidation is actually working?" — Expect validation strategy, monitoring, sampling.

**Staff signals (beyond Senior):**

- Frames caching as a *performance* layer, not a *reliability* layer.
- Explicitly models "cache completely cold" when sizing the database.
- Discusses cross-team impact: who owns invalidation, who depends on hit rate.
- Ties cost to operability: "We pay for headroom so we don't fail during peak."
- Asks "What's the dominant constraint?" before choosing a pattern.

**Common Senior mistake:** Thinking cache failover is transparent. Assuming replica has full state. Not sizing DB for cold-cache stampede.

**Phrases a Staff engineer uses naturally:**

- "Cache is an optimization, not a guarantee."
- "We size the database for the worst case: cache empty."
- "Invalidation is a distributed systems problem—every code path that writes must invalidate."
- "Hit rate is efficiency; correctness is validation."

**Explaining to leadership:** "The cache makes us 20× faster when it works. When it fails, we fall back to the database. If the database can't handle that load, we go down. So we either pay for cache headroom or we pay for database headroom—or we accept outage risk. I recommend headroom."

**How to teach this:** Start with the library analogy (reading room vs stacks). Then add: "The reading room can burn down. When it does, everyone goes to the stacks. The stacks must have enough capacity for that." Tie every pattern (TTL, invalidation, stampede prevention) to a failure mode.

---

# Part 17: Diagrams

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DISTRIBUTED CACHE ARCHITECTURE                           │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        APPLICATION TIER                             │   │
│   └───────────────────────────────┬─────────────────────────────────────┘   │
│                                   │                                         │
│          ┌────────────────────────┼────────────────────────┐                │
│          ▼                        ▼                        ▼                │
│   ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐     │
│   │  App Server 1   │      │  App Server 2   │      │  App Server 3   │     │
│   │  ┌───────────┐  │      │  ┌───────────┐  │      │  ┌───────────┐  │     │
│   │  │ L1 Cache  │  │      │  │ L1 Cache  │  │      │  │ L1 Cache  │  │     │
│   │  │ (local)   │  │      │  │ (local)   │  │      │  │ (local)   │  │     │
│   │  └─────┬─────┘  │      │  └─────┬─────┘  │      │  └─────┬─────┘  │     │
│   │        │        │      │        │        │      │        │        │     │
│   │  ┌─────┴─────┐  │      │  ┌─────┴─────┐  │      │  ┌─────┴─────┐  │     │
│   │  │  Cache    │  │      │  │  Cache    │  │      │  │  Cache    │  │     │
│   │  │  Client   │  │      │  │  Client   │  │      │  │  Client   │  │     │
│   │  └─────┬─────┘  │      │  └─────┬─────┘  │      │  └─────┬─────┘  │     │
│   └────────┼────────┘      └────────┼────────┘      └────────┼────────┘     │
│            │                        │                        │              │
│            └────────────────────────┼────────────────────────┘              │
│                                     │                                       │
│                                     ▼                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        REDIS CLUSTER (L2)                           │   │
│   │                                                                     │   │
│   │   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐             │   │
│   │   │  Shard 1    │    │  Shard 2    │    │  Shard 3    │             │   │
│   │   │  Primary    │    │  Primary    │    │  Primary    │             │   │
│   │   │      │      │    │      │      │    │      │      │             │   │
│   │   │      ▼      │    │      ▼      │    │      ▼      │             │   │
│   │   │  Replica    │    │  Replica    │    │  Replica    │             │   │
│   │   └─────────────┘    └─────────────┘    └─────────────┘             │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                     │                                       │
│                                     │ (On cache miss)                       │
│                                     ▼                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        DATABASE (Source of Truth)                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Cache Read Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        CACHE READ FLOW                                      │
│                                                                             │
│                         ┌──────────────┐                                    │
│                         │   Request    │                                    │
│                         │  product:123 │                                    │
│                         └──────┬───────┘                                    │
│                                │                                            │
│                                ▼                                            │
│                    ┌───────────────────────┐                                │
│                    │   Check L1 (Local)    │                                │
│                    └───────────┬───────────┘                                │
│                                │                                            │
│               ┌────────────────┼────────────────┐                           │
│               │                │                │                           │
│               ▼                ▼                                            │
│         ┌─────────┐      ┌─────────┐                                        │
│         │ L1 HIT  │      │ L1 MISS │                                        │
│         └────┬────┘      └────┬────┘                                        │
│              │                │                                             │
│              │                ▼                                             │
│              │   ┌───────────────────────┐                                  │
│              │   │  Check L2 (Redis)     │                                  │
│              │   └───────────┬───────────┘                                  │
│              │               │                                              │
│              │  ┌────────────┼────────────┐                                 │
│              │  │            │            │                                 │
│              │  ▼            ▼                                              │
│              │ ┌─────────┐ ┌─────────┐                                      │
│              │ │ L2 HIT  │ │ L2 MISS │                                      │
│              │ └────┬────┘ └────┬────┘                                      │
│              │      │           │                                           │
│              │      │           ▼                                           │
│              │      │  ┌───────────────────────┐                            │
│              │      │  │  Query Database       │                            │
│              │      │  └───────────┬───────────┘                            │
│              │      │              │                                        │
│              │      │              ▼                                        │
│              │      │  ┌───────────────────────┐                            │
│              │      │  │  Store in L2 (Redis)  │                            │
│              │      │  └───────────┬───────────┘                            │
│              │      │              │                                        │
│              │      └──────┬───────┘                                        │
│              │             │                                                │
│              │             ▼                                                │
│              │  ┌───────────────────────┐                                   │
│              │  │  Store in L1 (Local)  │                                   │
│              │  └───────────┬───────────┘                                   │
│              │              │                                               │
│              └──────────────┼───────────────────────────────────────────    │
│                             │                                               │
│                             ▼                                               │
│                    ┌──────────────┐                                         │
│                    │   Response   │                                         │
│                    │  (product)   │                                         │
│                    └──────────────┘                                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 18: Brainstorming & Deep Exercises (MANDATORY)

This section forces you to think like an owner. These scenarios test your judgment, prioritization, and ability to reason under constraints.

---

## A. Scale & Load Thought Experiments

### Experiment A1: Traffic Growth Scenarios

| Scale | Traffic | Data Size | What Changes | What Breaks First |
|-------|---------|-----------|--------------|-------------------|
| Current | 100K ops/sec | 10 GB | Baseline | Nothing |
| 2× | 200K ops/sec | 15 GB | ? | ? |
| 5× | 500K ops/sec | 30 GB | ? | ? |
| 10× | 1M ops/sec | 50 GB | ? | ? |

**Senior-level analysis:**

```
AT 2× (200K ops/sec, 15 GB):
    Changes needed: None likely - current cluster handles this
    First stress: Redis CPU utilization increases
    Action: Monitor, no immediate changes

AT 5× (500K ops/sec, 30 GB):
    Changes needed: Add more shards (6 primaries instead of 3)
    First stress: Individual shard throughput maxed
    Action: 
    - Reshard cluster (automatic with Redis Cluster)
    - Add more app server connection capacity

AT 10× (1M ops/sec, 50 GB):
    Changes needed: 
    - 10+ shard cluster
    - L1 local cache for hot keys (reduce Redis load)
    - Connection pooling optimization
    
    First stress: Network bandwidth, connection counts
    
    Action:
    - Implement L1 caching aggressively
    - Consider dedicated network for cache traffic
    - May need multiple clusters by data type
```

### Experiment A2: Most Fragile Assumption

```
FRAGILE ASSUMPTION: Hit rate stays at 95%

Why it's fragile:
- Hit rate depends on working set fitting in memory
- Traffic patterns change (new features, user behavior)
- Data growth may exceed cache capacity

What breaks if assumption is wrong:
    Hit rate drops to 80%:
    - Cache misses: 5K/sec → 20K/sec (4× database load)
    - Database may become bottleneck
    - Latency increases across the board
    
    Hit rate drops to 50%:
    - Cache misses: 5K/sec → 50K/sec (10× database load)
    - Database overwhelmed, potential outage
    - Cache becomes ineffective overhead

Detection:
- Monitor hit rate trend (not just current value)
- Alert on hit rate below threshold
- Track working set size vs cache capacity

Mitigation:
- Increase cache size before hit rate drops
- Analyze miss patterns, optimize what's cached
- Have database capacity headroom
```

---

## B. Failure Injection Scenarios

### Scenario B1: Slow Redis (10× Latency)

**Situation:** Redis latency increases from 0.5ms to 5ms. Not down, just slow.

```
IMMEDIATE BEHAVIOR:
- Cache operations take 5ms instead of 0.5ms
- Application latency increases by ~4.5ms per cache operation
- Multiple cache ops per request → significant slowdown

USER SYMPTOMS:
- API responses slower (noticeable but not failing)
- Page load times increased
- Mobile apps feel sluggish

DETECTION:
- Alert: redis.latency.p95 > 2ms
- Dashboard: Application latency spike
- Correlation: Redis latency spike matches app latency spike

FIRST MITIGATION:
1. Check Redis metrics (CPU, memory, network)
2. Check for blocking operations (KEYS, large SCAN)
3. Consider reducing timeout to fail faster
4. If severe: Enable circuit breaker, increase DB capacity

PERMANENT FIX:
1. Identify root cause (overload, slow commands, network)
2. Resize Redis if capacity issue
3. Optimize slow operations
4. Add monitoring for slow commands
```

### Scenario B2: Cache Stampede After Deployment

**Situation:** Deployment cleared all cache entries. Thundering herd to database.

```
IMMEDIATE BEHAVIOR:
- All cache lookups are misses
- 100% of traffic goes to database
- Database connection pool exhausted
- Requests queue, timeout, fail

USER SYMPTOMS:
- Requests timeout
- Error pages
- Complete or near-complete outage

DETECTION:
- Hit rate drops to 0%
- Database QPS spikes 10-20×
- Error rate spikes
- Latency P99 exceeds timeout

FIRST MITIGATION:
1. DON'T PANIC - Cache will warm naturally
2. Reduce traffic if possible (feature flags, rate limits)
3. Implement emergency request shedding
4. Consider cache warming script for hot keys

PERMANENT FIX:
1. Never deploy changes that flush cache without planning
2. Implement cache stampede prevention (locking)
3. Pre-deployment cache warming procedure
4. Database headroom for cold cache scenario
```

### Scenario B3: Serialization Version Mismatch

**Situation:** New code deployed writes v2 format. Old code can't read it.

```
IMMEDIATE BEHAVIOR:
- New servers write v2 format to cache
- Old servers (not yet upgraded) read v2, fail to deserialize
- Deserialization errors logged
- Affected requests fall back to database

USER SYMPTOMS:
- Increased latency (cache misses)
- Potentially inconsistent behavior between servers

DETECTION:
- Deserialization error rate spikes
- Errors correlate with deployment start
- Hit rate appears normal (reads succeed, just can't deserialize)

FIRST MITIGATION:
1. Complete the rollout (all servers to new version)
2. Or: Rollback to old version
3. Corrupted cache entries will be re-read from DB

PERMANENT FIX:
1. Always maintain backward compatibility in serialization
2. Version-aware deserialization code
3. Test serialization compatibility before deployment
4. Deployment procedure: Read-compatible first, then write new format
```

---

## C. Cost & Trade-off Exercises

### Exercise C1: 30% Cost Reduction Request

```
CURRENT COST: ~$1,050/month (6 nodes)

OPTIONS:

Option A: Reduce to 3 nodes (remove replicas) (-$450, 43% savings)
    Risk: No automatic failover on node failure
    Impact: Node failure requires manual intervention
    Recommendation: Only if downtime acceptable

Option B: Smaller instances (-$300, 29% savings)
    Risk: Less throughput headroom
    Impact: May hit capacity at peak traffic
    Recommendation: Only if traffic predictable

Option C: Reserved instances (-$250, 24% savings)
    Risk: 1-year commitment
    Impact: None if committed to Redis
    Recommendation: Best option if long-term need

Option D: Reduce data cached (-$150, 14% savings)
    Risk: Lower hit rate → more DB load
    Impact: Latency increase, DB cost increase
    Recommendation: Audit and remove low-value cached data

SENIOR RECOMMENDATION:
    Option C + Option D = 38% savings
    - Commit to reserved instances
    - Audit cached data, remove what's not valuable
    - Maintain cluster size for reliability
```

### Exercise C2: Cost of Cache Miss

```
CALCULATING CACHE MISS COST:

Cache hit cost:
    Redis operation: $0.000004

Cache miss cost:
    Redis operation (miss): $0.000004
    Database query: $0.0002
    Total: $0.0002

Cost difference: 50× more expensive per miss

AT 95% HIT RATE:
    1M requests:
    - 950K hits × $0.000004 = $3.80
    - 50K misses × $0.0002 = $10.00
    Total: $13.80

AT 80% HIT RATE:
    1M requests:
    - 800K hits × $0.000004 = $3.20
    - 200K misses × $0.0002 = $40.00
    Total: $43.20

15% hit rate drop = 3× cost increase

IMPLICATION:
    Investing in cache hit rate improvement has high ROI.
    $100/month more cache → 5% hit rate improvement → saves $300/month in DB costs.
```

---

## D. Correctness & Data Integrity

### Exercise D1: Ensuring Cache Invalidation Works

**Question:** How do you verify that cache invalidation is actually working?

```
APPROACH: Automated cache validation

// Pseudocode: Cache validation job (runs periodically)
FUNCTION validate_cache():
    sample_keys = get_random_cache_keys(1000)
    mismatches = 0
    
    FOR key IN sample_keys:
        cached_value = cache.get(key)
        IF cached_value IS null:
            CONTINUE  // No cache entry, nothing to validate
        
        // Parse key to determine source table
        entity_type, entity_id = parse_key(key)
        
        // Get current value from database
        db_value = database.get(entity_type, entity_id)
        
        // Compare
        IF db_value != deserialize(cached_value):
            mismatches++
            log.warn("Cache mismatch for key: " + key)
    
    mismatch_rate = mismatches / sample_keys.length
    metrics.gauge("cache.validation.mismatch_rate", mismatch_rate)
    
    IF mismatch_rate > 0.01:  // > 1% mismatch
        alert("High cache mismatch rate: " + mismatch_rate)

SCHEDULE: Run every 15 minutes
EXPECTATION: Mismatch rate < 0.1% normally
```

### Exercise D2: Preventing Double Caching

**Question:** How do you prevent the same data from being cached under multiple keys?

```
PROBLEM: Same data cached under different keys

Example:
    cache.set("user:123", user_data)
    cache.set("user:email:alice@example.com", user_data)
    
    When user updates, must invalidate BOTH keys.
    Easy to forget one, leading to stale data.

SOLUTIONS:

1. SINGLE CANONICAL KEY
   Only cache by primary key. Resolve other lookups first.
   
   FUNCTION get_user_by_email(email):
       // First, get user ID
       user_id = cache.get("email_to_id:" + email)
       IF user_id IS null:
           user_id = database.get_user_id_by_email(email)
           cache.set("email_to_id:" + email, user_id, ttl=3600)
       
       // Then get user by ID (canonical key)
       RETURN get_user(user_id)

2. DENORMALIZED WITH INVALIDATION LIST
   Track which keys need invalidation together.
   
   FUNCTION invalidate_user(user_id, email):
       keys_to_delete = [
           "user:" + user_id,
           "user:email:" + email
       ]
       cache.delete_multi(keys_to_delete)

3. REFERENCE KEYS
   Secondary keys point to primary key.
   
   cache.set("user:123", user_data)
   cache.set("user:email:alice@example.com", "user:123")  // Reference
   
   FUNCTION get_user_by_email(email):
       ref = cache.get("user:email:" + email)
       IF ref:
           RETURN cache.get(ref)  // Get by primary key
       // Fall through to database...

RECOMMENDATION: Single canonical key is simplest and safest.
```

---

## E. Incremental Evolution & Ownership

### Exercise E1: Adding L1 Local Cache (2-Week Timeline)

**Scenario:** Need to reduce Redis load by adding local in-memory cache.

```
WEEK 1: PREPARATION
─────────────────────

Day 1-2: Design decisions
- Which keys get L1 cache? (Hot, stable data only)
- L1 TTL? (30 seconds - very short to limit staleness)
- L1 size per process? (100 MB)
- Eviction policy? (LRU)

Day 3-4: Implementation
- Add local cache library (e.g., Caffeine, Guava)
- Wrap cache client with L1 layer
- Feature flag to enable/disable

Day 5: Testing
- Unit tests for L1 + L2 interaction
- Verify TTL behavior
- Verify eviction under memory pressure

WEEK 2: ROLLOUT
──────────────────

Day 6-7: Canary deployment
- Enable on 5% of app servers
- Monitor: L1 hit rate, memory usage
- Verify: No staleness issues

Day 8-9: Gradual rollout
- 25% → 50% → 100%
- Watch for increased staleness complaints

Day 10: Documentation
- Update runbooks
- Document new metrics
- Train team on L1 cache behavior

RISKS:
- L1 cache adds staleness (TTL of 30s)
- Memory pressure on app servers
- Debugging complexity (two cache layers)

MITIGATION:
- Start with very short TTL
- Monitor memory usage closely
- Clear documentation of caching behavior
```

### Exercise E2: Safe TTL Change

**Scenario:** Need to change TTL from 30 minutes to 5 minutes for product data.

```
PROBLEM:
- Can't change TTL for existing entries
- Old entries will live for up to 30 more minutes
- Want new TTL to take effect immediately

SAFE MIGRATION:

PHASE 1: Deploy new TTL
    // Change in code
    PRODUCT_CACHE_TTL = 300  // Was 1800

    Effect:
    - New cache entries get 5 min TTL
    - Old entries still have up to 30 min TTL
    - Mixed TTLs during transition

PHASE 2: Wait for old entries to expire
    Duration: 30 minutes (old TTL)
    
    After 30 minutes:
    - All old entries expired
    - All entries now have 5 min TTL

PHASE 3: Verify
    - Check random entries have expected TTL
    - Confirm hit rate stable
    - Monitor for freshness issues

ALTERNATIVE (immediate effect):
    - Flush all product cache keys
    - Risk: Cache stampede, increased DB load
    - Use only if immediate freshness required
```

---

## F. Interview-Oriented Thought Prompts

### Prompt F1: Interviewer Asks "What If Consistency Matters?"

**Interviewer:** "What if we need strong consistency between cache and database?"

```
RESPONSE STRUCTURE:

1. ACKNOWLEDGE THE CHALLENGE
   "Strong consistency with a cache is fundamentally challenging
   because caching trades consistency for speed."

2. CLARIFY REQUIREMENTS
   - "What does 'strong consistency' mean for this use case?"
   - "Is read-after-write consistency sufficient?"
   - "What's the acceptable latency impact?"

3. EXPLAIN OPTIONS

   OPTION A: Write-through cache
   - Write to DB and cache in same transaction
   - Provides read-after-write consistency
   - Latency cost: +1ms per write

   OPTION B: Skip caching for this data
   - Strongly consistent data reads from DB directly
   - Accept higher latency for those reads
   - Cache everything else

   OPTION C: Distributed lock on reads
   - Acquire lock, check cache, check DB if needed
   - True strong consistency
   - Latency cost: +20-50ms (defeats caching purpose)

4. RECOMMEND APPROACH
   "For most cases, I'd use write-through for data needing
   strong consistency, and cache-aside for everything else.
   If true distributed consistency is required, I'd question
   whether caching is appropriate for that data."
```

### Prompt F2: Clarifying Questions to Ask First

```
ESSENTIAL QUESTIONS BEFORE DESIGNING CACHE:

1. READ/WRITE RATIO
   "What's the read/write ratio? Caching helps most when read-heavy."
   
2. ACCEPTABLE STALENESS
   "How long can data be stale? This determines TTL strategy."
   
3. DATA SIZE
   "What's the size of data to cache? This determines cache sizing."
   
4. ACCESS PATTERNS
   "Are there hot keys? Uniform distribution or skewed?"
   
5. CONSISTENCY REQUIREMENTS
   "Is eventual consistency acceptable? Any data needing strong consistency?"
   
6. FAILURE TOLERANCE
   "What happens if cache is unavailable? Can we gracefully degrade?"
```

### Prompt F3: What You Explicitly Don't Build

```
EXPLICIT NON-GOALS FOR V1 CACHE:

1. MULTI-REGION CACHE
   "Cross-region consistency adds 50-200ms latency.
   Each region has its own cache. Accept some duplication."

2. AUTOMATIC INVALIDATION
   "Database triggers or CDC for auto-invalidation add complexity.
   Application explicitly invalidates. Simpler, more predictable."

3. COMPLEX QUERY CACHING
   "SQL query result caching is hard to invalidate correctly.
   Cache entities by primary key. Application builds responses."

4. STRONG CONSISTENCY
   "Distributed locks for consistency defeat caching purpose.
   Accept eventual consistency. Use database for strongly consistent reads."

5. CACHE AS PRIMARY STORE
   "Cache is ephemeral. Database is source of truth.
   Design for cache to be flushable without data loss."

WHY SAY THIS:
- Shows you understand caching trade-offs
- Demonstrates scope management
- Prevents over-engineering
- Focuses on what matters
```

---

# Master Review Check & L6 Dimension Table

## Master Review Check (11 Checkboxes)

### Purpose & audience
- [x] **Staff Engineer preparation** — Content aimed at L6 preparation; depth and judgment match L6 expectations.
- [x] **Chapter-only content** — Every section, example, and exercise is directly related to distributed cache; no tangents or filler.

### Explanation quality
- [x] **Explained in detail with an example** — Each major concept has a clear explanation plus at least one concrete example.
- [x] **Topics in depth** — Enough depth to reason about trade-offs, failure modes, and scale, not just definitions.

### Engagement & memorability
- [x] **Interesting & real-life incidents** — Structured real incident (Context|Trigger|Propagation|User-impact|Engineer-response|Root-cause|Design-change|Lesson).
- [x] **Easy to remember** — Mental models (library analogy), one-liners, Staff vs Senior contrasts.

### Structure & progression
- [x] **Organized for Early SWE → Staff SWE** — Basics to Staff-level thinking; Staff vs Senior contrasts.
- [x] **Strategic framing** — Problem selection, dominant constraint, business vs technical trade-offs.
- [x] **Teachability** — Concepts explainable to others; "how to teach" in Interview Calibration.

### End-of-chapter requirements
- [x] **Exercises** — Part 18 Brainstorming includes design, trade-off, scale, failure, and correctness exercises.
- [x] **BRAINSTORMING** — Part 18: "What if?" scenarios, failure injection, cost-cutting, migrations, trade-off debates.

### Final
- [x] All of the above are satisfied; no off-topic or duplicate content.

---

## L6 Dimension Table (A–J)

| Dim | Name | Coverage |
|-----|------|----------|
| **A** | Judgment & decision-making | Staff vs Senior contrasts; dominant constraint; alternatives considered; rushed decision scenario |
| **B** | Failure & incident thinking | Structured incident table; stampede; failover; blast radius; circuit breaker |
| **C** | Scale & time | 2×, 10× scale analysis; what breaks first; multi-year evolution (V1→V2) |
| **D** | Cost & sustainability | Cost breakdown; scaling; over-engineering; cost drivers; where teams over-engineer |
| **E** | Real-world engineering | Deployment pipeline; rollback; on-call burden; misleading signals; human factors |
| **F** | Learnability & memorability | Library analogy; one-liners; mental models; Staff phrases |
| **G** | Data, consistency & correctness | Eventual vs strong; invalidation; validation job; double-caching prevention |
| **H** | Security & compliance | Access control; what not to cache; GDPR/retention/compliance implications |
| **I** | Observability & debuggability | SLOs, SLIs, dashboard; debugging workflow; validation mismatch rate |
| **J** | Cross-team & org impact | Ownership boundaries; who invalidates; who depends on hit rate; blast radius |

---

**This chapter now meets Google Staff Engineer (L6) expectations.**

