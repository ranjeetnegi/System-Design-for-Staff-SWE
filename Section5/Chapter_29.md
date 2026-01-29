# Chapter 29: Distributed Cache

---

# Introduction

Caching is the most impactful optimization in distributed systems—and the most dangerous when done wrong. I've seen caches turn 500ms database queries into 1ms lookups, and I've seen cache bugs cause data corruption that took weeks to remediate. I've debugged incidents where cache invalidation failures showed users stale data for hours, and incidents where cache stampedes took down entire clusters.

This chapter covers distributed caching as Staff Engineers practice it: understanding not just how caches work, but when they help, when they hurt, and what breaks when you get it wrong.

**The Staff Engineer's First Law of Caching**: A cache is a lie you tell the system about what the truth is. Every cache is eventually wrong. The question is: how wrong, for how long, and does it matter?

---

## Quick Visual: Caching at a Glance

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CACHING: THE STAFF ENGINEER VIEW                         │
│                                                                             │
│   WRONG Framing: "Cache everything to make it faster"                       │
│   RIGHT Framing: "Cache strategically, understand staleness,                │
│                   and design for cache failure"                             │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Before adding a cache, understand:                                 │   │
│   │                                                                     │   │
│   │  1. What's the hit rate? (< 80% often means cache isn't worth it)   │   │
│   │  2. What's the staleness tolerance? (Seconds? Minutes? Never?)      │   │
│   │  3. What happens on cache miss? (Thundering herd? Slow fallback?)   │   │
│   │  4. How do you invalidate? (TTL? Event-driven? Manual?)             │   │
│   │  5. What's the failure mode? (Fail open? Fail closed? Degrade?)     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   THE UNCOMFORTABLE TRUTH:                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Caching trades consistency for performance.                        │   │
│   │  Every cache hit is stale data—the question is whether you care.    │   │
│   │  Cache invalidation is one of the two hard problems in CS.          │   │
│   │  A cache that's always empty is worse than no cache at all.         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## L5 vs L6 Caching Decisions

| Scenario | L5 Approach | L6 Approach |
|----------|-------------|-------------|
| **Adding cache to slow endpoint** | "Let's add Redis caching with 5-minute TTL" | "What's the access pattern? 80% of requests for 20% of keys? What's acceptable staleness? What happens during cache failure?" |
| **Cache invalidation** | "Invalidate on every write" | "What's the cost of stale data vs. cost of invalidation traffic? Can we use TTL for most cases and explicit invalidation only for critical updates?" |
| **Cache sizing** | "Use the biggest instance available" | "What's our working set? Memory for hot data only. Cold data eviction is fine—that's what the database is for." |
| **Cache failure** | "If cache is down, hit the database" | "At our traffic, cache failure = database overload = full outage. We need cache redundancy, graceful degradation, and circuit breakers." |
| **Multi-region cache** | "Replicate cache across regions" | "Cross-region cache sync adds latency and complexity. Local caches with regional databases might be simpler and faster." |

**Key Difference**: L6 engineers understand that caching is a trade-off, not a solution. They design for cache failure, cache miss storms, and staleness—not just the happy path.

---

# Part 1: Foundations — What Caching Is and Why It Exists

## What Is a Distributed Cache?

A cache is a high-speed storage layer that stores a subset of data, typically transient, so that future requests for that data are served faster than accessing the primary data source. A distributed cache spreads this storage across multiple machines to handle more data and higher throughput.

### The Simplest Mental Model

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CACHING: THE LIBRARY ANALOGY                             │
│                                                                             │
│   Imagine a library with millions of books (database).                      │
│                                                                             │
│   Without cache:                                                            │
│   • Every request: Walk to the stacks, find book, bring it back             │
│   • Time: 5 minutes per request                                             │
│   • Bottleneck: Only so many people can be in the stacks                    │
│                                                                             │
│   With cache (popular books on front desk):                                 │
│   • Popular books: Grab from front desk (1 second)                          │
│   • Rare books: Still go to stacks (5 minutes)                              │
│   • Most requests: 1 second (if book is popular)                            │
│                                                                             │
│   COMPLICATIONS:                                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  What if the book on the front desk is an old edition?              │   │
│   │  → Staleness problem. Someone checked out latest, you have old.     │   │
│   │                                                                     │   │
│   │  What if everyone wants the same book at once?                      │   │
│   │  → Cache stampede. 1000 people rush to stacks simultaneously.       │   │
│   │                                                                     │   │
│   │  What if the front desk is closed?                                  │   │
│   │  → Cache failure. Everyone goes to stacks = stacks overwhelmed.     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Why Distributed Caching Exists

### 1. Latency Reduction

The primary purpose: serve data faster than the source of truth.

```
TYPICAL LATENCIES:

L1 CPU cache:        0.5 nanoseconds
L2 CPU cache:        7 nanoseconds
RAM:                 100 nanoseconds
SSD read:            150,000 nanoseconds (150 μs)
Network round-trip:  500,000 nanoseconds (0.5 ms) same datacenter
Database query:      1-50 milliseconds (simple to complex)
Cross-region:        50-150 milliseconds

CACHE IMPACT:
Database query: 10ms
Cached response: 0.5ms
Improvement: 20x faster

For 10,000 requests/second:
Without cache: 10,000 × 10ms = 100 seconds of DB time per second (impossible)
With 95% hit rate: 500 × 10ms = 5 seconds of DB time (feasible)
```

### 2. Throughput Amplification

Caches handle more requests per second than databases.

```
THROUGHPUT COMPARISON (same hardware cost):

PostgreSQL:     5,000 reads/second (complex queries)
MySQL:          10,000 reads/second (simple queries)
Redis:          100,000+ reads/second
Memcached:      200,000+ reads/second

Cache lets you serve 10-20x more requests with same backend.
```

### 3. Backend Protection

Caches shield slow or expensive backends from traffic spikes.

```
SCENARIO: Product page traffic spike

Without cache:
├── Normal: 1,000 req/sec to database
├── Spike: 50,000 req/sec to database
├── Database overwhelmed, connections exhausted
└── Full outage for all users

With cache (95% hit rate):
├── Normal: 50 req/sec to database (95% cached)
├── Spike: 2,500 req/sec to database (still 95% cached)
├── Database handles spike
└── Users served (mostly from cache)
```

### 4. Cost Reduction

Caches reduce load on expensive resources.

```
COST COMPARISON:

Database: $1,000/month for 10,000 QPS capacity
Cache: $100/month for 100,000 QPS capacity

For 50,000 QPS workload:
Without cache: 5 × $1,000 = $5,000/month (5 DB instances)
With cache (90% hit rate): 1 × $1,000 + 1 × $100 = $1,100/month

Cost reduction: 78%
```

## What Happens If Caching Does NOT Exist

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SYSTEMS WITHOUT CACHING                                  │
│                                                                             │
│   FAILURE MODE 1: LATENCY CEILING                                           │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Every request hits the database                                    │   │
│   │  P50 latency: 50ms, P99 latency: 500ms                              │   │
│   │  Users perceive system as "slow"                                    │   │
│   │  Engagement drops, revenue decreases                                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   FAILURE MODE 2: DATABASE OVERLOAD                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Database handles 100% of read traffic                              │   │
│   │  Connection pool exhausted during peaks                             │   │
│   │  Writes blocked waiting for read connections                        │   │
│   │  System becomes unresponsive                                        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   FAILURE MODE 3: COST EXPLOSION                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Need 10x database capacity to handle read load                     │   │
│   │  Database licensing/hosting costs dominate budget                   │   │
│   │  Still can't match latency of cached responses                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   FAILURE MODE 4: THIRD-PARTY DEPENDENCY AMPLIFICATION                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Every request calls external API                                   │   │
│   │  API rate limits reached quickly                                    │   │
│   │  API latency adds to every request                                  │   │
│   │  API outage = your outage                                           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 2: Functional Requirements

## Core Use Cases

### 1. Key-Value Lookup Cache

The most common use case: cache database query results by key.

```
Use Case: Get user profile by user_id

Without cache:
    profile = database.query("SELECT * FROM users WHERE id = ?", user_id)
    // Latency: 5-10ms

With cache:
    cache_key = "user:" + user_id
    profile = cache.get(cache_key)
    IF profile IS NULL:
        profile = database.query("SELECT * FROM users WHERE id = ?", user_id)
        cache.set(cache_key, profile, ttl=300)  // Cache for 5 minutes
    RETURN profile
    // Latency: 0.5ms (hit) or 5-10ms (miss)
```

### 2. Computed Result Cache

Cache expensive computations to avoid recomputing.

```
Use Case: Get user's personalized feed

Computation:
├── Fetch user preferences (1 DB query)
├── Fetch following list (1 DB query)
├── Fetch recent posts from followed users (complex query)
├── Rank posts by relevance (CPU-intensive)
├── Filter by user preferences
└── Total time: 200-500ms

With cache:
    cache_key = "feed:" + user_id + ":" + current_hour()
    feed = cache.get(cache_key)
    IF feed IS NULL:
        feed = compute_feed(user_id)
        cache.set(cache_key, feed, ttl=3600)  // Cache for 1 hour
    RETURN feed
    // Latency: 0.5ms (hit) or 200-500ms (miss)
```

### 3. Session Cache

Store user session data for fast access.

```
Use Case: Store and retrieve user session

On login:
    session_id = generate_session_id()
    session_data = {user_id, permissions, preferences, login_time}
    cache.set("session:" + session_id, session_data, ttl=86400)
    RETURN session_id

On each request:
    session = cache.get("session:" + session_id)
    IF session IS NULL:
        RETURN UNAUTHORIZED  // Session expired or invalid
    RETURN session
    // Latency: 0.5ms
```

### 4. Rate Limit Counter Cache

Fast counters for rate limiting (see Chapter 28).

```
Use Case: Track request count per user per minute

FUNCTION check_rate_limit(user_id, limit):
    cache_key = "rate:" + user_id + ":" + current_minute()
    count = cache.increment(cache_key)
    IF count == 1:
        cache.expire(cache_key, 60)  // Expire after 1 minute
    RETURN count <= limit
```

### 5. Distributed Lock Cache

Use cache for distributed coordination.

```
Use Case: Prevent duplicate processing of same job

FUNCTION acquire_lock(resource_id, ttl):
    lock_key = "lock:" + resource_id
    // SET if Not eXists
    success = cache.set_nx(lock_key, current_instance_id, ttl)
    RETURN success

FUNCTION release_lock(resource_id):
    lock_key = "lock:" + resource_id
    // Only release if we own the lock
    IF cache.get(lock_key) == current_instance_id:
        cache.delete(lock_key)
```

## Read Paths

```
// Pseudocode: Cache read with fallback (Cache-Aside pattern)

FUNCTION get_with_cache(key, fetch_function, ttl):
    // Try cache first
    cached_value = cache.get(key)
    
    IF cached_value IS NOT NULL:
        metrics.increment("cache_hit")
        RETURN deserialize(cached_value)
    
    // Cache miss - fetch from source
    metrics.increment("cache_miss")
    value = fetch_function()
    
    IF value IS NOT NULL:
        cache.set(key, serialize(value), ttl)
    
    RETURN value

// Usage
user = get_with_cache(
    key = "user:123",
    fetch_function = lambda: database.get_user(123),
    ttl = 300
)
```

## Write Paths

```
// Pseudocode: Cache write strategies

// Strategy 1: Write-Through (write to cache and DB synchronously)
FUNCTION write_through(key, value):
    database.write(key, value)
    cache.set(key, value, ttl)
    // Pros: Cache always consistent after write
    // Cons: Write latency includes both DB and cache

// Strategy 2: Write-Behind (write to cache, async to DB)
FUNCTION write_behind(key, value):
    cache.set(key, value, ttl)
    async_queue.enqueue({operation: "write", key: key, value: value})
    // Pros: Low write latency
    // Cons: Data loss risk if cache fails before DB write

// Strategy 3: Write-Invalidate (invalidate cache, write to DB)
FUNCTION write_invalidate(key, value):
    cache.delete(key)
    database.write(key, value)
    // Next read will repopulate cache
    // Pros: Simple, avoids race conditions
    // Cons: First read after write is slow
```

## Control / Admin Paths

```
// Administrative operations

FUNCTION flush_cache(pattern):
    // Emergency cache clear
    keys = cache.keys(pattern + "*")
    FOR key IN keys:
        cache.delete(key)
    log_audit("Cache flush", pattern, current_user())

FUNCTION get_cache_stats():
    RETURN {
        hit_rate: metrics.get("cache_hit") / (metrics.get("cache_hit") + metrics.get("cache_miss")),
        memory_used: cache.info("memory_used"),
        memory_max: cache.info("memory_max"),
        evictions: cache.info("evicted_keys"),
        connections: cache.info("connected_clients")
    }

FUNCTION warm_cache(keys):
    // Pre-populate cache with known hot data
    FOR key IN keys:
        value = database.get(key)
        cache.set(key, value, ttl)
```

## Edge Cases

### Edge Case 1: Cache Miss Storm (Thundering Herd)

```
Popular item's cache entry expires
1000 concurrent requests arrive
All 1000 see cache miss
All 1000 hit database simultaneously

SOLUTION: Request coalescing
FUNCTION get_with_coalescing(key, fetch_function, ttl):
    cached = cache.get(key)
    IF cached IS NOT NULL:
        RETURN cached
    
    // Only one request fetches; others wait
    lock_key = "fetch_lock:" + key
    IF cache.set_nx(lock_key, "1", ttl=5):  // Got the lock
        TRY:
            value = fetch_function()
            cache.set(key, value, ttl)
            RETURN value
        FINALLY:
            cache.delete(lock_key)
    ELSE:
        // Another request is fetching; wait and retry
        sleep(10ms)
        RETURN get_with_coalescing(key, fetch_function, ttl)
```

### Edge Case 2: Cache Stampede on Expiration

```
TTL-based expiration causes synchronized cache misses

SOLUTION: Staggered TTL with jitter
FUNCTION set_with_jitter(key, value, base_ttl):
    jitter = random(0, base_ttl * 0.1)  // ±10% jitter
    actual_ttl = base_ttl + jitter
    cache.set(key, value, actual_ttl)
```

### Edge Case 3: Hot Key Problem

```
Single key receives disproportionate traffic
One cache node overloaded while others idle

SOLUTION: Key replication or local caching
// Option 1: Replicate hot keys across multiple nodes
FUNCTION get_hot_key(key):
    shard = hash(key + random(0, N_REPLICAS)) % N_SHARDS
    RETURN cache_nodes[shard].get(key)

// Option 2: Local in-memory cache for hot keys
local_cache = LRUCache(max_size=1000)
FUNCTION get_with_local_cache(key):
    IF key IN local_cache:
        RETURN local_cache[key]
    value = distributed_cache.get(key)
    IF is_hot_key(key):
        local_cache[key] = value
    RETURN value
```

### Edge Case 4: Negative Caching (Caching "Not Found")

```
PROBLEM: Database overloaded by repeated lookups for non-existent keys

Attacker pattern:
├── Request user:999999999 (doesn't exist)
├── Cache miss → Database query → NULL
├── No cache entry created
├── Next request → Same flow
├── Result: Database hit for every request

SOLUTION: Cache negative results

FUNCTION get_with_negative_cache(key, fetch_function, ttl, negative_ttl):
    cached = cache.get(key)
    
    IF cached == NEGATIVE_MARKER:
        metrics.increment("negative_cache_hit")
        RETURN NULL
    
    IF cached IS NOT NULL:
        RETURN cached
    
    // Cache miss
    value = fetch_function()
    
    IF value IS NULL:
        // Cache the "not found" result
        cache.set(key, NEGATIVE_MARKER, negative_ttl)  // Shorter TTL
        metrics.increment("negative_cache_set")
        RETURN NULL
    ELSE:
        cache.set(key, value, ttl)
        RETURN value

NEGATIVE_TTL CONSIDERATIONS:
├── Too short: Attackers still hit database
├── Too long: Newly created entities not visible
├── Recommendation: 60-300 seconds for negative entries
├── Exception: Invalidate negative cache on entity creation

SECURITY IMPLICATION:
├── Negative caching can confirm entity non-existence
├── "User not found" cached = attacker knows user doesn't exist
├── Mitigation: Rate limit lookups, don't differentiate responses
```

### Edge Case 5: Cache Inconsistency After Write

```
Thread A: Read user (cache miss, reads from DB: version 1)
Thread B: Update user in DB (version 2)
Thread B: Invalidate cache
Thread A: Write to cache (version 1)  // STALE DATA CACHED

Result: Cache has stale version 1, DB has version 2

SOLUTION: Version-based invalidation
FUNCTION write_with_version(key, value, version):
    cache_entry = {value: value, version: version}
    cache.set(key, cache_entry, ttl)

FUNCTION read_with_version(key, fetch_function):
    cached = cache.get(key)
    IF cached IS NOT NULL:
        db_version = database.get_version(key)
        IF cached.version >= db_version:
            RETURN cached.value
        // Cached version is stale
    
    value, version = fetch_function()
    cache.set(key, {value: value, version: version}, ttl)
    RETURN value
```

## What Is Intentionally OUT of Scope

```
OUT OF SCOPE:
├── Persistent storage: Cache is ephemeral; use database for durability
├── Complex queries: Cache is key-value; use database for joins/aggregations
├── Transactions: Cache doesn't support ACID; use database for transactions
├── Large objects: Cache is memory-bound; use object storage for files
└── Real-time sync: Cache is eventually consistent; use pub/sub for real-time

WHY SCOPE IS LIMITED:
├── Caches optimize for speed, not durability or consistency
├── Adding these features would make cache as slow as database
├── Each feature has better specialized solutions
└── Trying to do everything makes cache unreliable for what it's good at
```

---

# Part 3: Non-Functional Requirements

## Latency Expectations

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CACHE LATENCY EXPECTATIONS                               │
│                                                                             │
│   CACHE HIT LATENCY (same datacenter):                                      │
│   ├── Target P50: < 1ms                                                     │
│   ├── Target P95: < 2ms                                                     │
│   ├── Target P99: < 5ms                                                     │
│   └── Unacceptable: > 10ms (defeats purpose of caching)                     │
│                                                                             │
│   CACHE MISS LATENCY:                                                       │
│   ├── = Backend latency + cache overhead                                    │
│   ├── Overhead should be < 5ms                                              │
│   └── Must not be worse than no-cache scenario                              │
│                                                                             │
│   WRITE LATENCY:                                                            │
│   ├── Cache-aside invalidation: < 1ms                                       │
│   ├── Write-through: < 5ms (includes cache write)                           │
│   └── Write-behind: < 1ms (async DB write)                                  │
│                                                                             │
│   STAFF INSIGHT:                                                            │
│   If cache P50 > 5ms, you have a problem:                                   │
│   • Network issues between app and cache                                    │
│   • Cache overloaded (CPU, memory, or connections)                          │
│   • Serialization/deserialization overhead                                  │
│   • Wrong cache architecture (too much data per key)                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Availability Expectations

```
CACHE AVAILABILITY REQUIREMENTS:

Tier 1 (Critical path cache):
├── Availability: 99.9% (8.7 hours downtime/year)
├── Failure mode: Application still works (degrades to DB)
├── Recovery time: < 5 minutes
└── Example: Session cache, rate limiting cache

Tier 2 (Performance cache):
├── Availability: 99% (3.6 days downtime/year acceptable)
├── Failure mode: Slower responses, DB handles load
├── Recovery time: < 1 hour
└── Example: Query result cache, computed value cache

Tier 3 (Optional cache):
├── Availability: 95% (18 days downtime/year acceptable)
├── Failure mode: Feature degrades gracefully
├── Recovery time: Best effort
└── Example: Recommendation cache, precomputed analytics
```

## Consistency Expectations

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CACHE CONSISTENCY SPECTRUM                               │
│                                                                             │
│   STRONG CONSISTENCY (rare for caches):                                     │
│   ├── Cache always reflects latest write                                    │
│   ├── Requires: Write-through + synchronous invalidation                    │
│   ├── Cost: Higher latency, lower throughput                                │
│   └── Use case: Financial balances, inventory counts                        │
│                                                                             │
│   EVENTUAL CONSISTENCY (common):                                            │
│   ├── Cache may be stale for bounded time (TTL)                             │
│   ├── Typical staleness: seconds to minutes                                 │
│   ├── Cost: Much higher performance                                         │
│   └── Use case: User profiles, product details, content                     │
│                                                                             │
│   READ-YOUR-WRITES (hybrid):                                                │
│   ├── User sees their own writes immediately                                │
│   ├── Other users may see stale data                                        │
│   ├── Implementation: Invalidate cache on write + version check             │
│   └── Use case: User settings, social posts                                 │
│                                                                             │
│   STAFF PRINCIPLE:                                                          │
│   "Strong consistency in a distributed cache is expensive and               │
│    often unnecessary. Know your staleness tolerance."                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Durability

```
CACHE DURABILITY: NONE (by design)

Key insight: Cache is NOT durable storage.
├── Cache data can be evicted anytime (LRU, memory pressure)
├── Cache nodes can restart anytime (losing all data)
├── Cache cluster can fail completely
└── This is FINE—source of truth is the database

IMPLICATION:
├── Never store data ONLY in cache
├── Always have a fallback to source of truth
├── Design for 100% cache miss scenario
└── Cache loss should cause slowness, not data loss
```

## How Requirements Conflict

```
CONFLICT 1: Latency vs. Consistency
├── Strong consistency requires synchronous operations
├── Synchronous operations add latency
├── Resolution: Accept eventual consistency for most use cases

CONFLICT 2: Hit Rate vs. Memory Cost
├── Higher hit rate requires caching more data
├── More data requires more memory (expensive)
├── Resolution: Cache only hot data; evict cold data

CONFLICT 3: Availability vs. Consistency
├── High availability requires replication
├── Replication across regions means eventual consistency
├── Resolution: Local consistency, cross-region eventual consistency

CONFLICT 4: Simplicity vs. Performance
├── Simple caching (TTL only) is easy to implement
├── Optimal caching (smart invalidation) is complex
├── Resolution: Start simple; optimize when proven necessary
```

---

# Part 4: Scale & Load Modeling

## Concrete Numbers Example: E-Commerce Product Cache

```
SCENARIO: E-commerce platform product catalog cache

USER BASE:
├── Monthly active users: 10M
├── Daily active users: 1M
├── Concurrent users (peak): 100K

TRAFFIC PATTERN:
├── Product page views: 50M/day
├── Average QPS: 580 req/sec
├── Peak QPS (sales event): 5,000 req/sec
├── Peak-to-average ratio: 8.6x

DATA CHARACTERISTICS:
├── Total products: 5M
├── Active products (viewed in last 30 days): 500K
├── Hot products (top 20%): 100K
├── Average product data size: 2KB
├── Product images: stored separately (CDN)

READ/WRITE RATIO:
├── Product reads: 99.9%
├── Product updates: 0.1%
├── Update frequency: 5,000 updates/day
└── Heavily read-dominant (ideal for caching)
```

## Cache Sizing Calculation

```
WORKING SET CALCULATION:

Hot data (must cache):
├── 100K products × 2KB = 200MB
├── Access: 80% of traffic
└── Hit rate target: 99%

Warm data (should cache if space):
├── 400K products × 2KB = 800MB
├── Access: 15% of traffic
└── Hit rate target: 80%

Cold data (don't cache):
├── 4.5M products × 2KB = 9GB
├── Access: 5% of traffic
└── Cache misses acceptable

TOTAL CACHE SIZE:
├── Minimum: 200MB (hot data only)
├── Recommended: 1GB (hot + warm)
├── Maximum useful: 2GB (diminishing returns beyond)
└── Allocate: 2GB with LRU eviction
```

## QPS and Throughput Requirements

```
CACHE THROUGHPUT REQUIREMENTS:

Normal operation:
├── Cache reads: 580 × 0.95 = 550 req/sec (95% hit rate)
├── Cache writes: 580 × 0.05 + updates = ~50 req/sec
└── Total: 600 req/sec

Peak operation:
├── Cache reads: 5,000 × 0.95 = 4,750 req/sec
├── Cache writes: 5,000 × 0.05 + updates = ~300 req/sec
└── Total: 5,050 req/sec

Safety margin (2x peak):
├── Required capacity: 10,000 req/sec
├── Single Redis node: ~100,000 req/sec
└── Single node sufficient for this scale

WHEN TO SHARD:
├── If QPS > 50,000: Consider sharding
├── If memory > 25GB: Must shard (RAM limits)
├── If write-heavy: Consider sharding for write distribution
```

## What Breaks First at Scale

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CACHE SCALING BOTTLENECKS                                │
│                                                                             │
│   BOTTLENECK 1: MEMORY                                                      │
│   ├── Symptom: Evictions increase, hit rate drops                           │
│   ├── Threshold: Memory utilization > 80%                                   │
│   ├── Solution: Add nodes, increase sharding                                │
│   └── Warning sign: Hit rate dropping while traffic stable                  │
│                                                                             │
│   BOTTLENECK 2: NETWORK BANDWIDTH                                           │
│   ├── Symptom: Latency increases, especially for large values               │
│   ├── Threshold: Network utilization > 70%                                  │
│   ├── Solution: Compress values, split large objects, add nodes             │
│   └── Warning sign: Large value operations slower than small                │
│                                                                             │
│   BOTTLENECK 3: CPU (serialization/deserialization)                         │
│   ├── Symptom: Latency increases uniformly                                  │
│   ├── Threshold: CPU utilization > 80%                                      │
│   ├── Solution: Optimize serialization, add nodes                           │
│   └── Warning sign: CPU high even when memory and network are fine          │
│                                                                             │
│   BOTTLENECK 4: CONNECTIONS                                                 │
│   ├── Symptom: Connection errors, timeouts                                  │
│   ├── Threshold: Connections near max (typically 10K)                       │
│   ├── Solution: Connection pooling, reduce clients, add nodes               │
│   └── Warning sign: Sporadic failures under load                            │
│                                                                             │
│   BOTTLENECK 5: HOT KEY                                                     │
│   ├── Symptom: One node overloaded, others idle                             │
│   ├── Threshold: Single key > 10K req/sec                                   │
│   ├── Solution: Key replication, local caching, key splitting               │
│   └── Warning sign: Uneven load distribution across shards                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Dangerous Assumptions

```
ASSUMPTION 1: "Cache will always be fast"
├── Reality: Cache can be slow (network, CPU, overload)
├── Risk: No timeout/fallback, requests hang
├── Mitigation: Always set timeouts, have fallback

ASSUMPTION 2: "Hit rate will stay constant"
├── Reality: Access patterns change (new features, viral content)
├── Risk: Hit rate drops, DB overloaded
├── Mitigation: Monitor hit rate, alert on drops, capacity plan for misses

ASSUMPTION 3: "Cache size is sufficient"
├── Reality: Data grows, working set expands
├── Risk: Evictions increase, hit rate drops
├── Mitigation: Monitor evictions, plan for growth

ASSUMPTION 4: "TTL is appropriate"
├── Reality: Access patterns determine optimal TTL
├── Risk: Too short = low hit rate; too long = stale data
├── Mitigation: Analyze access patterns, adjust TTL per key type

ASSUMPTION 5: "One cache serves all use cases"
├── Reality: Different data has different caching requirements
├── Risk: Suboptimal for all use cases
├── Mitigation: Consider separate caches for different workloads
```

---

# Part 5: High-Level Architecture

## Core Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DISTRIBUTED CACHE ARCHITECTURE                           │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        CLIENT LAYER                                 │   │
│   │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐                 │   │
│   │  │  App 1  │  │  App 2  │  │  App 3  │  │  App N  │                 │   │
│   │  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘                 │   │
│   │       │            │            │            │                      │   │
│   │       └────────────┴─────┬──────┴────────────┘                      │   │
│   │                          │                                          │   │
│   │                  ┌───────▼───────┐                                  │   │
│   │                  │ Cache Client  │  Connection pooling,             │   │
│   │                  │    Library    │  serialization, routing          │   │
│   │                  └───────┬───────┘                                  │   │
│   └──────────────────────────┼──────────────────────────────────────────┘   │
│                              │                                              │
│   ┌──────────────────────────┼──────────────────────────────────────────┐   │
│   │                    CACHE LAYER                                      │   │
│   │                          │                                          │   │
│   │              ┌───────────┼───────────┐                              │   │
│   │              │    Routing / Proxy    │  Optional: Smart routing     │   │
│   │              └───────────┬───────────┘                              │   │
│   │                          │                                          │   │
│   │    ┌─────────────────────┼─────────────────────┐                    │   │
│   │    │                     │                     │                    │   │
│   │    ▼                     ▼                     ▼                    │   │
│   │  ┌──────────┐      ┌──────────┐       ┌──────────┐                  │   │
│   │  │  Shard 1 │      │  Shard 2 │       │  Shard N │                  │   │
│   │  │  Primary │      │  Primary │       │  Primary │                  │   │
│   │  └────┬─────┘      └────┬─────┘       └────┬─────┘                  │   │
│   │       │                 │                  │                        │   │
│   │  ┌────▼─────┐      ┌────▼─────┐       ┌────▼─────┐                  │   │
│   │  │ Replica  │      │ Replica  │       │ Replica  │    (Optional)    │   │
│   │  └──────────┘      └──────────┘       └──────────┘                  │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    BACKEND LAYER                                    │   │
│   │                                                                     │   │
│   │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │   │
│   │  │   Database   │  │   Database   │  │  External    │               │   │
│   │  │   (Primary)  │  │  (Replica)   │  │    APIs      │               │   │
│   │  └──────────────┘  └──────────────┘  └──────────────┘               │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

```
COMPONENT: Cache Client Library
├── Responsibility: Interface between application and cache
├── Functions:
│   ├── Connection pooling (reuse connections)
│   ├── Serialization/deserialization
│   ├── Key routing (consistent hashing)
│   ├── Retry logic with backoff
│   ├── Timeout handling
│   └── Local buffering (optional)
├── Stateless: Yes (connections are pooled, not stateful)
└── Failure handling: Retry, fallback, circuit breaker

COMPONENT: Cache Shard (Node)
├── Responsibility: Store and serve cached data
├── Functions:
│   ├── Key-value storage in memory
│   ├── TTL management and expiration
│   ├── LRU/LFU eviction when memory full
│   ├── Replication to replicas (if configured)
│   └── Persistence to disk (optional)
├── Stateful: Yes (holds cached data)
└── Failure handling: Replica promotion, data loss acceptable

COMPONENT: Cache Proxy (Optional)
├── Responsibility: Intelligent routing and load balancing
├── Functions:
│   ├── Request routing to correct shard
│   ├── Connection multiplexing
│   ├── Hot key detection and handling
│   ├── Traffic shaping
│   └── Protocol translation
├── Stateless: Yes (routing rules only)
└── Failure handling: Redundant proxies, direct client fallback
```

## Data Flow

### Read Path

```
// Pseudocode: Cache read flow

1. Application calls cache_client.get("user:123")

2. Cache Client:
   ├── Serialize key
   ├── Hash key to determine shard: hash("user:123") % num_shards = 2
   ├── Get connection from pool for shard 2
   └── Send GET command

3. Cache Shard 2:
   ├── Look up key in hash table: O(1)
   ├── Check if expired: compare TTL with current time
   ├── If valid: return value
   └── If expired or missing: return NULL

4. Cache Client:
   ├── Receive response
   ├── Deserialize value
   └── Return to application

5. Application (if cache miss):
   ├── Fetch from database
   ├── Call cache_client.set("user:123", user_data, ttl=300)
   └── Return data

LATENCY BREAKDOWN (cache hit):
├── Client serialization: 0.1ms
├── Network to cache: 0.2ms
├── Cache lookup: 0.05ms
├── Network from cache: 0.2ms
├── Client deserialization: 0.1ms
└── Total: ~0.65ms
```

### Write Path

```
// Pseudocode: Cache write flow (Cache-Aside with invalidation)

1. Application updates user in database

2. Application calls cache_client.delete("user:123")

3. Cache Client:
   ├── Hash key to determine shard
   ├── Get connection from pool
   └── Send DELETE command

4. Cache Shard:
   ├── Remove key from hash table
   ├── Free memory
   └── Return success

5. Next read will miss cache and repopulate from database

ALTERNATIVE: Write-Through
1. Application updates user
2. cache_client.set("user:123", updated_user, ttl=300)
3. database.update("user:123", updated_user)
4. Cache now has fresh data immediately
```

---

# Part 6: Deep Component Design

## Cache Client Library

### Internal Data Structures

```
CLASS CacheClient:
    // Connection pools per shard
    connection_pools: Map<ShardId, ConnectionPool>
    
    // Consistent hash ring for key routing
    hash_ring: ConsistentHashRing
    
    // Local cache for hot keys (optional)
    local_cache: LRUCache<Key, Value>
    
    // Circuit breakers per shard
    circuit_breakers: Map<ShardId, CircuitBreaker>
    
    // Serializer for values
    serializer: Serializer  // JSON, MessagePack, Protobuf

STRUCT ConnectionPool:
    connections: List<Connection>
    max_size: int
    min_size: int
    max_idle_time: Duration
    health_check_interval: Duration

STRUCT ConsistentHashRing:
    ring: SortedMap<HashValue, ShardId>
    virtual_nodes_per_shard: int  // Typically 100-200
    
    FUNCTION get_shard(key: String) -> ShardId:
        hash = hash_function(key)
        // Find first node >= hash, or wrap around
        RETURN ring.ceiling(hash) OR ring.first()
```

### Connection Pooling Algorithm

```
// Pseudocode: Connection pool management

FUNCTION get_connection(shard_id):
    pool = connection_pools[shard_id]
    
    // Try to get existing connection
    connection = pool.try_acquire(timeout=10ms)
    IF connection IS NOT NULL:
        IF connection.is_healthy():
            RETURN connection
        ELSE:
            pool.remove(connection)
            // Fall through to create new
    
    // Create new connection if pool not at max
    IF pool.size() < pool.max_size:
        connection = create_connection(shard_id)
        pool.add(connection)
        RETURN connection
    
    // Pool exhausted, wait for available connection
    connection = pool.acquire(timeout=100ms)
    IF connection IS NULL:
        THROW ConnectionPoolExhausted()
    RETURN connection

FUNCTION release_connection(connection):
    IF connection.is_healthy() AND pool.size() <= pool.max_size:
        pool.release(connection)
    ELSE:
        connection.close()
        pool.remove(connection)
```

### Failure Handling

```
// Pseudocode: Cache client with circuit breaker

FUNCTION get_with_resilience(key):
    shard_id = hash_ring.get_shard(key)
    circuit_breaker = circuit_breakers[shard_id]
    
    IF circuit_breaker.is_open():
        // Shard is known to be failing, skip it
        metrics.increment("cache_circuit_open")
        RETURN NULL  // Let caller fall back to database
    
    TRY:
        connection = get_connection(shard_id)
        result = connection.get(key, timeout=5ms)
        circuit_breaker.record_success()
        RETURN result
    CATCH TimeoutException:
        circuit_breaker.record_failure()
        metrics.increment("cache_timeout")
        RETURN NULL
    CATCH ConnectionException:
        circuit_breaker.record_failure()
        metrics.increment("cache_connection_error")
        RETURN NULL
    FINALLY:
        release_connection(connection)

// Circuit breaker state machine
CLASS CircuitBreaker:
    state: CLOSED | OPEN | HALF_OPEN
    failure_count: int
    failure_threshold: int = 5
    reset_timeout: Duration = 30 seconds
    last_failure_time: Timestamp
    
    FUNCTION record_failure():
        failure_count++
        last_failure_time = now()
        IF failure_count >= failure_threshold:
            state = OPEN
    
    FUNCTION record_success():
        failure_count = 0
        state = CLOSED
    
    FUNCTION is_open():
        IF state == OPEN:
            IF now() - last_failure_time > reset_timeout:
                state = HALF_OPEN  // Allow one test request
                RETURN FALSE
            RETURN TRUE
        RETURN FALSE
```

## Cache Shard (Node) Internals

### Memory Data Structures

```
// Cache node internal structure

STRUCT CacheNode:
    // Main hash table for key-value storage
    data: HashMap<Key, CacheEntry>
    
    // Expiration tracking (sorted by expiration time)
    expiration_queue: MinHeap<ExpirationEntry>
    
    // LRU tracking for eviction
    lru_list: DoublyLinkedList<Key>
    lru_map: HashMap<Key, ListNode>
    
    // Memory tracking
    memory_used: AtomicLong
    memory_limit: Long
    
    // Statistics
    stats: CacheStats

STRUCT CacheEntry:
    value: Bytes
    ttl: Duration
    created_at: Timestamp
    expires_at: Timestamp
    last_accessed: Timestamp
    size: int

STRUCT ExpirationEntry:
    key: Key
    expires_at: Timestamp
```

### Get Operation

```
// Pseudocode: Cache GET operation

FUNCTION get(key):
    entry = data.get(key)
    
    IF entry IS NULL:
        stats.misses++
        RETURN NULL
    
    // Check expiration
    IF entry.expires_at < now():
        // Lazy expiration: delete expired entry
        delete(key)
        stats.misses++
        RETURN NULL
    
    // Update LRU tracking
    lru_list.move_to_front(lru_map[key])
    entry.last_accessed = now()
    
    stats.hits++
    RETURN entry.value
```

### Set Operation

```
// Pseudocode: Cache SET operation

FUNCTION set(key, value, ttl):
    entry_size = sizeof(key) + sizeof(value) + OVERHEAD
    
    // Check if we need to evict
    WHILE memory_used + entry_size > memory_limit:
        evict_one()
    
    // Check if key already exists
    old_entry = data.get(key)
    IF old_entry IS NOT NULL:
        memory_used -= old_entry.size
        expiration_queue.remove(old_entry)
        lru_list.remove(lru_map[key])
    
    // Create new entry
    entry = CacheEntry{
        value: value,
        ttl: ttl,
        created_at: now(),
        expires_at: now() + ttl,
        last_accessed: now(),
        size: entry_size
    }
    
    // Store entry
    data.put(key, entry)
    memory_used += entry_size
    
    // Track for expiration
    expiration_queue.add(ExpirationEntry{key, entry.expires_at})
    
    // Track for LRU
    node = lru_list.add_to_front(key)
    lru_map[key] = node
    
    RETURN SUCCESS
```

### Eviction Algorithm

```
// Pseudocode: LRU eviction

FUNCTION evict_one():
    // Remove least recently used entry
    lru_node = lru_list.remove_from_back()
    IF lru_node IS NULL:
        RETURN  // Cache is empty
    
    key = lru_node.key
    entry = data.remove(key)
    
    IF entry IS NOT NULL:
        memory_used -= entry.size
        lru_map.remove(key)
        // Note: expiration_queue will lazily clean up
        stats.evictions++

// Alternative: LFU eviction (approximated)
FUNCTION evict_one_lfu():
    // Find entry with lowest access count
    // Often implemented with multiple LRU lists per frequency bucket
    min_freq_bucket = frequency_buckets.get_min()
    key = min_freq_bucket.remove_oldest()
    // ... rest similar to LRU
```

### Expiration Handling

```
// Pseudocode: Background expiration

// Option 1: Lazy expiration (check on access)
// Already shown in GET operation above

// Option 2: Active expiration (background thread)
FUNCTION expiration_thread():
    WHILE running:
        // Process expired entries in batches
        batch_size = 100
        now_time = now()
        
        FOR i IN range(batch_size):
            IF expiration_queue.is_empty():
                BREAK
            
            entry = expiration_queue.peek()
            IF entry.expires_at > now_time:
                BREAK  // No more expired entries
            
            expiration_queue.pop()
            
            // Verify entry still exists and is actually expired
            cache_entry = data.get(entry.key)
            IF cache_entry IS NOT NULL AND cache_entry.expires_at <= now_time:
                delete(entry.key)
        
        // Sleep between batches to avoid CPU spike
        sleep(100ms)
```

## Why Simpler Alternatives Fail

```
SIMPLE ALTERNATIVE 1: In-Memory HashMap
├── Works for: Single-process applications
├── Fails when: Multiple app instances need shared cache
├── Problem: Each instance has separate cache, low hit rate
└── Solution: Distributed cache (Redis, Memcached)

SIMPLE ALTERNATIVE 2: Local Disk Cache
├── Works for: Large data that doesn't fit in RAM
├── Fails when: Low latency required
├── Problem: Disk I/O adds 1-10ms per access
└── Solution: Memory-based cache for hot data

SIMPLE ALTERNATIVE 3: Single Cache Node
├── Works for: Small to medium workloads
├── Fails when: Data exceeds RAM or throughput exceeds capacity
├── Problem: Vertical scaling has limits
└── Solution: Sharded cache cluster

SIMPLE ALTERNATIVE 4: No TTL (Never Expire)
├── Works for: Static data that never changes
├── Fails when: Data can be updated
├── Problem: Cache becomes infinitely stale
└── Solution: TTL-based expiration or explicit invalidation
```

---

# Part 7: Data Model & Storage Decisions

## What Data Is Stored

```
CACHE DATA CATEGORIES:

1. QUERY RESULTS
   Key: "query:" + hash(sql_query + parameters)
   Value: Serialized query result set
   TTL: 60-300 seconds (depends on data volatility)
   Example: "query:a1b2c3d4" → [{id: 1, name: "Alice"}, {id: 2, name: "Bob"}]

2. ENTITY OBJECTS
   Key: entity_type + ":" + entity_id
   Value: Serialized entity
   TTL: 300-3600 seconds
   Example: "user:12345" → {id: 12345, name: "Alice", email: "alice@example.com"}

3. COMPUTED VALUES
   Key: "computed:" + computation_name + ":" + parameters
   Value: Computation result
   TTL: 3600-86400 seconds (expensive to recompute)
   Example: "computed:user_feed:12345" → [post_1, post_2, post_3, ...]

4. SESSION DATA
   Key: "session:" + session_id
   Value: Session object
   TTL: 86400 seconds (24 hours) or sliding expiration
   Example: "session:abc123" → {user_id: 12345, permissions: [...], login_time: ...}

5. COUNTERS / RATE LIMITS
   Key: "counter:" + entity + ":" + time_bucket
   Value: Integer count
   TTL: Time window duration
   Example: "counter:user:12345:2024-01-15-14:30" → 47

6. LOCKS
   Key: "lock:" + resource_id
   Value: Owner identifier
   TTL: Lock timeout
   Example: "lock:order:67890" → "worker-3"
```

## How Data Is Keyed

```
KEY DESIGN PRINCIPLES:

1. NAMESPACE PREFIX
   Purpose: Avoid key collisions between different data types
   Pattern: "{type}:{subtype}:{id}"
   Examples:
   ├── "user:profile:12345"
   ├── "user:settings:12345"
   ├── "product:details:67890"
   └── "order:status:11111"

2. HIERARCHICAL KEYS
   Purpose: Group related data, enable pattern-based operations
   Pattern: "{entity}:{id}:{attribute}"
   Examples:
   ├── "user:12345:profile"
   ├── "user:12345:friends"
   ├── "user:12345:feed"

3. VERSIONED KEYS
   Purpose: Cache invalidation without explicit delete
   Pattern: "{type}:{id}:v{version}"
   Examples:
   ├── "user:12345:v1" (old version, ignored)
   ├── "user:12345:v2" (current version)

4. TIME-BUCKETED KEYS
   Purpose: Automatic expiration, time-series data
   Pattern: "{type}:{id}:{time_bucket}"
   Examples:
   ├── "rate:12345:2024-01-15-14:30" (per-minute bucket)
   ├── "analytics:pageviews:2024-01-15" (daily bucket)

KEY ANTI-PATTERNS:
├── Too long: Wastes memory, slower operations
├── No namespace: Risk of collisions
├── User input in key: Security risk (injection)
├── Non-deterministic: Can't invalidate reliably
```

## How Data Is Partitioned (Sharding)

```
SHARDING STRATEGIES:

1. CONSISTENT HASHING (Recommended)
   Algorithm:
   ├── Hash each shard to multiple points on ring (virtual nodes)
   ├── Hash key to point on ring
   ├── Key belongs to next shard clockwise
   Pros:
   ├── Minimal data movement when adding/removing shards
   ├── Load balancing across shards
   Cons:
   ├── Hot keys still go to single shard
   ├── Slightly more complex client logic

   // Pseudocode
   FUNCTION get_shard(key):
       hash = md5(key)
       position = hash % RING_SIZE
       FOR node IN sorted_ring_positions:
           IF node.position >= position:
               RETURN node.shard_id
       RETURN first_node.shard_id  // Wrap around

2. HASH MOD N (Simple but inflexible)
   Algorithm: shard_id = hash(key) % num_shards
   Pros:
   ├── Simple to implement
   ├── Predictable distribution
   Cons:
   ├── Adding/removing shards moves ~all data
   ├── Hot keys still problematic

3. RANGE-BASED (For ordered access)
   Algorithm: Assign key ranges to shards
   Pros:
   ├── Range queries possible
   ├── Predictable data location
   Cons:
   ├── Uneven distribution common
   ├── Hot ranges overload single shard
```

## Retention Policies

```
TTL STRATEGIES BY DATA TYPE:

1. HOT DATA (frequently accessed)
   TTL: 60-300 seconds
   Refresh: On access (sliding) or fixed
   Example: Product details during sale

2. WARM DATA (periodically accessed)
   TTL: 300-3600 seconds
   Refresh: On cache miss
   Example: User profiles

3. COLD DATA (rarely accessed)
   TTL: Don't cache OR very short TTL
   Example: Historical records

4. STATIC DATA (never changes)
   TTL: 86400+ seconds OR no TTL
   Invalidation: On deployment
   Example: Configuration, feature flags

5. COMPUTED DATA (expensive to generate)
   TTL: As long as acceptable staleness allows
   Invalidation: On source data change
   Example: Aggregated reports, ML predictions

EVICTION POLICIES:
├── LRU (Least Recently Used): Good general-purpose
├── LFU (Least Frequently Used): Better for stable access patterns
├── Random: Simple, surprisingly effective
└── TTL-based: Predictable expiration
```

## Schema Evolution

```
CACHE SCHEMA VERSIONING:

Problem: Application deploys with new data format
Old cached data has old format
Deserialization fails or produces wrong results

SOLUTION 1: Versioned Keys
    // Include version in key
    key = "user:12345:v2"
    
    // On schema change, increment version
    key = "user:12345:v3"
    
    // Old keys naturally expire via TTL
    Pros: Clean separation, no migration needed
    Cons: Temporary cache misses for all keys

SOLUTION 2: Versioned Values
    // Include version in value
    cached_value = {
        version: 2,
        data: {...}
    }
    
    // On read, check version
    IF cached_value.version < CURRENT_VERSION:
        // Ignore stale version, fetch fresh
        RETURN NULL
    
    Pros: Gradual migration
    Cons: Extra storage per entry

SOLUTION 3: Backward-Compatible Schemas
    // Design schemas to be backward compatible
    // Add fields, don't remove
    // Use default values for missing fields
    
    Pros: No versioning needed
    Cons: Schema constraints, can't remove fields

SOLUTION 4: Cache Flush on Deploy
    // Clear all cache on schema-changing deploy
    // Drastic but simple
    
    Pros: Clean slate
    Cons: Thundering herd, cold cache
```

---

# Part 8: Consistency, Concurrency & Ordering

## Strong vs. Eventual Consistency

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CACHE CONSISTENCY MODELS                                 │
│                                                                             │
│   MODEL 1: EVENTUAL CONSISTENCY (Most Common for Caches)                    │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Cache may serve stale data for a bounded time                      │   │
│   │  Staleness = min(TTL, time since last write)                        │   │
│   │                                                                     │   │
│   │  Timeline:                                                          │   │
│   │  T0: Cache has User{name: "Alice"}                                  │   │
│   │  T1: Database updated to User{name: "Alicia"}                       │   │
│   │  T2: Cache still has "Alice" (stale)                                │   │
│   │  T3: TTL expires, cache miss, fetch "Alicia"                        │   │
│   │  Staleness window: T1 → T3                                          │   │
│   │                                                                     │   │
│   │  Acceptable when: User can tolerate seeing old data briefly         │   │
│   │  Example: Profile name, product description                         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   MODEL 2: READ-YOUR-WRITES                                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  User sees their own writes immediately                             │   │
│   │  Other users may see stale data                                     │   │
│   │                                                                     │   │
│   │  Implementation:                                                    │   │
│   │  T0: User updates name to "Alicia"                                  │   │
│   │  T0: Invalidate cache for user:12345                                │   │
│   │  T1: Same user reads → cache miss → fresh from DB                   │   │
│   │  T1: Other user reads → may hit stale cache                         │   │
│   │                                                                     │   │
│   │  Acceptable when: Users expect to see their changes immediately     │   │
│   │  Example: Settings, own profile                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   MODEL 3: STRONG CONSISTENCY (Rare for Caches)                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Cache always reflects latest write                                 │   │
│   │  Requires: Synchronous invalidation on every write                  │   │
│   │                                                                     │   │
│   │  Implementation:                                                    │   │
│   │  T0: Start transaction                                              │   │
│   │  T1: Update database                                                │   │
│   │  T2: Invalidate all cache replicas (synchronous)                    │   │
│   │  T3: Commit transaction (only after cache invalidated)              │   │
│   │                                                                     │   │
│   │  Cost: Higher latency, complex coordination                         │   │
│   │  Use sparingly: Financial data, inventory counts                    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Race Conditions

### Race Condition 1: Cache Invalidation Race

```
SCENARIO: Two threads updating same entity

Thread A (Update)          Thread B (Read)           Cache State
──────────────────────────────────────────────────────────────────
                                                     user:123 = v1
T1: Read from DB (v1)
T2:                        Read from cache (v1)      user:123 = v1
T3: Update DB to v2
T4: Invalidate cache                                 user:123 = DELETED
T5:                        Cache miss
T6:                        Read from DB (v2)
T7: Write to cache (v1!)                             user:123 = v1 ← WRONG!
T8:                        Write to cache (v2)       user:123 = v2

PROBLEM: Thread A's stale write (v1) can overwrite Thread B's fresh write (v2)
if timing is different.

SOLUTION: Don't write to cache after update; let next read populate

Thread A (Update)          Thread B (Read)           Cache State
──────────────────────────────────────────────────────────────────
                                                     user:123 = v1
T1: Update DB to v2
T2: Invalidate cache                                 user:123 = DELETED
T3:                        Cache miss
T4:                        Read from DB (v2)
T5:                        Write to cache (v2)       user:123 = v2 ✓
```

### Race Condition 2: Thundering Herd

```
SCENARIO: Popular key expires, many simultaneous requests

T0: Cache entry "product:hot" expires
T1: 1000 requests arrive simultaneously
T2: All 1000 see cache miss
T3: All 1000 hit database
T4: Database overwhelmed

SOLUTION: Request coalescing with locking

FUNCTION get_with_lock(key, fetch_function, ttl):
    value = cache.get(key)
    IF value IS NOT NULL:
        RETURN value
    
    lock_key = "lock:" + key
    IF cache.set_nx(lock_key, "1", ttl=5):
        // Won the lock, we fetch
        TRY:
            value = fetch_function()
            cache.set(key, value, ttl)
            RETURN value
        FINALLY:
            cache.delete(lock_key)
    ELSE:
        // Another request is fetching, wait
        FOR i IN range(10):
            sleep(10ms)
            value = cache.get(key)
            IF value IS NOT NULL:
                RETURN value
        // Timeout, fetch ourselves
        RETURN fetch_function()
```

## Idempotency

```
CACHE OPERATIONS AND IDEMPOTENCY:

GET: Naturally idempotent
├── get("key") always returns same value (if unchanged)
├── Safe to retry

SET: Idempotent (last write wins)
├── set("key", value) can be called multiple times
├── Final state is the same

DELETE: Idempotent
├── delete("key") can be called multiple times
├── Key is deleted regardless

INCREMENT: NOT idempotent
├── incr("counter") changes value each time
├── Retry can cause over-counting

PROBLEM: Retrying increment on timeout
Request: incr("counter")
Timeout occurred
Did it succeed? Unknown.
Retry: incr("counter") → May double-count

SOLUTION: Use idempotency keys
FUNCTION idempotent_increment(counter_key, request_id):
    idempotency_key = "idem:" + request_id
    IF cache.exists(idempotency_key):
        RETURN cache.get(counter_key)  // Already processed
    
    new_value = cache.incr(counter_key)
    cache.set(idempotency_key, "1", ttl=300)
    RETURN new_value
```

## Multi-Key Consistency Challenges

```
PROBLEM: Application logic requires multiple cache keys to be consistent

Example: Shopping cart display
├── Key 1: cart:user123 → [item1, item2, item3]
├── Key 2: product:item1 → {name: "Widget", price: 10.00}
├── Key 3: product:item2 → {name: "Gadget", price: 20.00}
├── Key 4: product:item3 → {name: "Doohickey", price: 15.00}

Problem scenario:
├── Product item2 price changes from $20 to $25
├── product:item2 cache invalidated
├── User requests cart
├── cart:user123 returned (lists item2)
├── product:item2 cache miss, fetches new price ($25)
├── User sees inconsistent state (cart total calculated with old cart + new price)

WHY MULTI-KEY CONSISTENCY IS IMPOSSIBLE IN DISTRIBUTED CACHE:
├── No transactions across keys (unlike database)
├── Keys may be on different shards
├── Invalidation not atomic across keys
└── This is a fundamental limitation, not a bug

STRATEGIES FOR MULTI-KEY SCENARIOS:

Strategy 1: Denormalize (embed related data)
├── Store cart with embedded product data
├── Key: cart:user123 → [{item: item1, name: "Widget", price: 10.00, ...}, ...]
├── Pro: Single key read, always consistent
├── Con: Product update requires invalidating all carts containing that product
├── Best for: Read-heavy, infrequent product updates

Strategy 2: Accept inconsistency (design for it)
├── Display cart with "prices may have changed" warning
├── Re-validate prices at checkout (source of truth)
├── Pro: Simple caching, clear UX
├── Con: Users see stale prices (but checkout is correct)
├── Best for: Most e-commerce scenarios

Strategy 3: Version-based consistency
├── Each product has version number
├── Cart stores product versions at time of add
├── On display, check if cached product version matches cart version
├── If mismatch, show "price changed" indicator
├── Pro: Detects inconsistency, user can refresh
├── Con: More complex logic

Strategy 4: Short TTL for related data
├── Products with TTL of 60 seconds
├── Cart with TTL of 60 seconds
├── Maximum inconsistency window: 60 seconds
├── Pro: Simple, bounded staleness
├── Con: More cache misses, higher DB load

STAFF INSIGHT:
"Don't try to make cache transactional. Accept that cache provides
performance, not consistency. Critical consistency checks belong
at the transaction boundary (checkout), not in the cache layer."
```

## Ordering Guarantees

```
CACHE ORDERING PROPERTIES:

SINGLE KEY:
├── Reads/writes to same key are ordered
├── Last write wins
├── Read after write sees the write (on same node)

MULTIPLE KEYS:
├── No ordering guarantee across keys
├── set("a", 1); set("b", 2) may be seen as b=2 before a=1
├── Must use transactions if ordering matters

REPLICATION:
├── Primary → replica replication is async
├── Read from replica may not see recent write to primary
├── For consistency: read from primary

MULTI-NODE WRITES:
├── Writes to different nodes are independent
├── No global ordering
├── Each node has its own timeline
```

## What Bugs Appear If Mishandled

```
BUG 1: STALE CACHE AFTER UPDATE
Symptom: User updates profile but keeps seeing old version
Cause: Cache not invalidated after database update
Fix: Always invalidate/update cache when DB changes

BUG 2: CACHE STAMPEDE
Symptom: Database CPU spikes when popular item expires
Cause: Many simultaneous cache misses for same key
Fix: Request coalescing, staggered TTL, pre-warming

BUG 3: DOUBLE COUNTING
Symptom: Counters show inflated numbers
Cause: Retry of INCREMENT operation
Fix: Idempotency keys for non-idempotent operations

BUG 4: INCONSISTENT CACHE AFTER FAILOVER
Symptom: Stale data after cache node recovery
Cause: New node doesn't have recent writes
Fix: Accept cold cache after failover, let it warm up

BUG 5: MEMORY EXHAUSTION
Symptom: Cache evicting entries faster than expected
Cause: Data growth exceeded capacity planning
Fix: Monitor eviction rate, scale proactively
```

---

# Part 9: Failure Modes & Degradation

## Cache Failure Taxonomy

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CACHE FAILURE MODES                                      │
│                                                                             │
│   FAILURE 1: SINGLE NODE FAILURE                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Cause: Node crash, network partition, OOM                          │   │
│   │  Blast radius: 1/N of cached data (if sharded)                      │   │
│   │  Symptom: Cache misses spike for affected keys                      │   │
│   │  User impact: Increased latency for affected requests               │   │
│   │  Recovery: Replica promotion OR cold restart                        │   │
│   │  Duration: Seconds (replica) to minutes (cold)                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   FAILURE 2: CLUSTER-WIDE FAILURE                                           │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Cause: Control plane failure, network partition, misconfiguration  │   │
│   │  Blast radius: 100% of cached data                                  │   │
│   │  Symptom: All cache requests fail or timeout                        │   │
│   │  User impact: Full application slowdown or outage                   │   │
│   │  Recovery: Fix root cause, restart cluster, warm cache              │   │
│   │  Duration: Minutes to hours                                         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   FAILURE 3: SLOW CACHE                                                     │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Cause: Overload, GC pauses, network congestion                     │   │
│   │  Blast radius: All requests to affected nodes                       │   │
│   │  Symptom: P99 latency spikes, timeouts                              │   │
│   │  User impact: Overall application latency increases                 │   │
│   │  Recovery: Reduce load, scale up, fix bottleneck                    │   │
│   │  Duration: Until fixed                                              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   FAILURE 4: DATA CORRUPTION                                                │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Cause: Bug in serialization, stale data cached incorrectly         │   │
│   │  Blast radius: All reads of corrupted keys                          │   │
│   │  Symptom: Application errors, wrong data displayed                  │   │
│   │  User impact: Users see incorrect information                       │   │
│   │  Recovery: Flush affected keys, fix bug, repopulate                 │   │
│   │  Duration: Until detected and fixed                                 │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   FAILURE 5: CACHE STAMPEDE                                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Cause: Popular key expires, many simultaneous misses               │   │
│   │  Blast radius: Database and all dependent services                  │   │
│   │  Symptom: Database overwhelmed, cascading failures                  │   │
│   │  User impact: Full outage                                           │   │
│   │  Recovery: Rate limit to DB, stagger cache population               │   │
│   │  Duration: Until stampede subsides                                  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Degradation Strategies

```
// Pseudocode: Graceful degradation when cache fails

FUNCTION get_with_degradation(key, fetch_function):
    // Level 1: Try distributed cache
    TRY:
        value = distributed_cache.get(key, timeout=5ms)
        IF value IS NOT NULL:
            RETURN value
    CATCH CacheException:
        metrics.increment("cache_error")
    
    // Level 2: Try local cache (if available)
    IF local_cache.contains(key):
        metrics.increment("local_cache_hit")
        RETURN local_cache.get(key)
    
    // Level 3: Circuit breaker check
    IF circuit_breaker.is_open("database"):
        // Database overloaded, return stale data or error
        IF stale_value = local_cache.get_stale(key):
            metrics.increment("stale_fallback")
            RETURN stale_value
        RETURN ERROR("Service temporarily unavailable")
    
    // Level 4: Fetch from database with rate limiting
    IF NOT rate_limiter.acquire("database", key):
        // Too many requests to DB, queue or reject
        RETURN ERROR("Rate limited, try again")
    
    TRY:
        value = fetch_function()
        local_cache.set(key, value, ttl=60)
        async: distributed_cache.set(key, value, ttl=300)
        RETURN value
    CATCH DatabaseException:
        circuit_breaker.record_failure("database")
        THROW

// Fail-open vs fail-closed decision
FUNCTION should_fail_open(use_case):
    SWITCH use_case:
        CASE "read_product":
            RETURN TRUE   // Show stale product, don't fail
        CASE "read_price":
            RETURN FALSE  // Price must be accurate
        CASE "read_inventory":
            RETURN FALSE  // Inventory affects ordering
        CASE "read_recommendations":
            RETURN TRUE   // Recommendations can be stale
```

## Failure Timeline Walkthrough

```
SCENARIO: Primary cache node dies during peak traffic

TIME    EVENT                                   SYSTEM STATE
────────────────────────────────────────────────────────────────────────────
T+0s    Node 2 (of 4) crashes due to OOM       25% of keys unavailable
T+0s    Clients see connection errors to Node 2 Error rate: 25% (keys on Node 2)
T+1s    Clients retry, hash ring redirects      Some requests go to wrong node
T+2s    Health check detects Node 2 failure     Automatic failover triggered
T+3s    Replica 2 promoted to primary           Node 2 keys available again
T+5s    Clients update routing                  Normal operation resuming
T+10s   Cache warming for cold keys             Hit rate recovering
T+60s   Hit rate stabilized                     Back to normal

METRICS DURING INCIDENT:
├── Cache error rate: 0% → 25% → 0%
├── Database QPS: 100 → 2000 → 500 → 100
├── P99 latency: 5ms → 50ms → 10ms → 5ms
├── Application error rate: 0% → 0.5% → 0%
└── Duration: ~60 seconds total

WHAT WENT WELL:
├── Automatic replica promotion
├── Clients handled errors gracefully
├── Database handled increased load
└── System self-healed without intervention

WHAT COULD BE IMPROVED:
├── OOM should have been prevented (better memory limits)
├── Proactive alerting before OOM
├── Pre-warming hot keys after failover
```

## Slow Cache Dependency Handling

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    THE SLOW CACHE PROBLEM                                   │
│                                                                             │
│   A slow cache is WORSE than a dead cache.                                  │
│                                                                             │
│   Dead cache:                                                               │
│   ├── Immediate detection (connection refused)                              │
│   ├── Circuit breaker opens quickly                                         │
│   ├── Fallback to database immediately                                      │
│   └── Clear failure mode                                                    │
│                                                                             │
│   Slow cache (responding in 500ms instead of 1ms):                          │
│   ├── Requests pile up waiting for slow responses                           │
│   ├── Thread pools exhausted                                                │
│   ├── Timeouts eventually fire (but damage already done)                    │
│   ├── Database gets hit after timeout (adding more load)                    │
│   └── Cascading slowdown across all services                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

SCENARIO: Cache becomes slow (network congestion, overloaded node)

Timeline:
T+0s    Cache P99 latency increases from 2ms to 200ms
        └── Symptom: API P99 increases, no errors yet
T+5s    Application thread pools filling up (threads blocked on cache)
        └── Symptom: Request queue growing, new requests delayed
T+10s   Thread pool exhausted (100/100 threads busy)
        └── Symptom: New requests rejected (503 errors)
T+15s   Timeouts start firing (default 5s timeout)
        └── Symptom: Cache errors logged, fallback to DB triggered
T+20s   Database receives spike of fallback requests
        └── Symptom: Database latency increases
T+30s   Database connection pool exhausted
        └── Symptom: Full outage—nothing works

STAFF INSIGHT:
A 5-second cache timeout is far too long. If cache isn't responding
in 10ms, it's not providing value—fail fast.

SOLUTION: Aggressive timeouts + adaptive behavior

// Pseudocode: Slow cache handling
FUNCTION get_with_adaptive_timeout(key):
    // Start with normal timeout
    timeout = 10ms
    
    // Check recent latency history
    recent_p99 = metrics.get_cache_p99_last_minute()
    IF recent_p99 > 5ms:
        // Cache is degraded, reduce timeout further
        timeout = 5ms
        metrics.increment("cache_degraded_mode")
    
    IF recent_p99 > 20ms:
        // Cache is too slow to be useful, skip it
        metrics.increment("cache_bypassed")
        RETURN fetch_from_database(key)
    
    TRY:
        start = now()
        value = cache.get(key, timeout=timeout)
        latency = now() - start
        metrics.record("cache_latency", latency)
        
        IF latency > 5ms:
            // This request was slow, but succeeded
            metrics.increment("cache_slow_success")
        
        RETURN value
    CATCH TimeoutException:
        metrics.increment("cache_timeout")
        RETURN fetch_from_database(key)

ADAPTIVE THRESHOLD TABLE:
┌─────────────────────────────────────────────────────────────────────────────┐
│  Cache P99 Latency   │  Action                                              │
│  ────────────────────┼─────────────────────────────────────────────-────────│
│  < 2ms               │  Normal operation                                    │
│  2-5ms               │  Alert (degraded performance)                        │
│  5-20ms              │  Reduce timeout, increase DB capacity warning        │
│  20-100ms            │  Bypass cache for 50% of requests                    │
│  > 100ms             │  Bypass cache entirely, page on-call                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Cascading Failure Timeline: Cache Overload

```
SCENARIO: Black Friday traffic spike overwhelms cache cluster

NORMAL STATE:
├── Traffic: 10,000 req/sec
├── Cache hit rate: 95%
├── Cache latency P50: 0.5ms, P99: 2ms
├── Database load: 500 req/sec
└── All healthy

T+0min (Traffic spike begins)
├── Traffic: 10,000 → 50,000 req/sec (5x normal)
├── Cache load: 50,000 × 0.95 = 47,500 req/sec
├── Cache CPU: 40% → 85%
├── Cache latency: P50 0.5ms → 1ms, P99 2ms → 10ms
├── DATABASE LOAD: 500 → 2,500 req/sec (handling increased misses)
└── Status: DEGRADED (latency increasing)

T+2min (Cache CPU saturated)
├── Cache CPU: 85% → 98%
├── Cache latency: P50 1ms → 5ms, P99 10ms → 100ms
├── Application thread pools: 50% utilized → 90% utilized
├── Some requests timing out
├── Database load: 2,500 → 4,000 req/sec (more fallbacks)
└── Status: CRITICAL (timeouts beginning)

T+4min (Thread pool exhaustion)
├── Cache latency: P50 5ms → 50ms (severely degraded)
├── Application thread pools: 90% → 100% (exhausted)
├── New requests rejected (503 errors)
├── Error rate: 0% → 15%
├── Database load: 4,000 → 6,000 req/sec
├── Database latency: 5ms → 50ms
└── Status: PARTIAL OUTAGE

T+6min (Database overwhelmed)
├── Database connection pool: 80% → 100% (exhausted)
├── Database latency: 50ms → 500ms
├── Error rate: 15% → 60%
├── Revenue loss: ~$10,000/minute
└── Status: FULL OUTAGE

T+8min (Circuit breakers activate)
├── Circuit breaker opens for cache (too many failures)
├── Circuit breaker opens for database (too many failures)
├── All requests return cached error response
├── Error rate: 60% → 95% (controlled failure)
├── Database load: 6,000 → 0 (circuit open, recovering)
└── Status: CONTROLLED OUTAGE (damage limited)

T+12min (Traffic subsides, recovery begins)
├── Traffic decreases to 30,000 req/sec
├── Database recovers (connections available)
├── Circuit breaker enters half-open state
├── Gradual traffic restoration
└── Status: RECOVERING

T+20min (Full recovery)
├── Cache hit rate restored to 95%
├── Database load back to sustainable levels
├── Error rate: < 0.1%
└── Status: NORMAL

METRICS SUMMARY:
├── Total duration: 20 minutes
├── Full outage duration: 6 minutes
├── Revenue impact: ~$60,000
├── Root cause: Insufficient cache capacity for 5x traffic
├── Contributing factor: Too-long cache timeouts (5s instead of 10ms)
└── Missing protection: Load shedding before cascade
```

## Protection Mechanisms

```
// Pseudocode: Cache protection mechanisms

// 1. REQUEST COALESCING (prevent stampede)
CLASS RequestCoalescer:
    in_flight: Map<Key, Future<Value>>
    
    FUNCTION get(key, fetch_function):
        IF key IN in_flight:
            RETURN in_flight[key].await()
        
        future = new Future()
        in_flight[key] = future
        
        TRY:
            value = fetch_function()
            future.complete(value)
            RETURN value
        FINALLY:
            in_flight.remove(key)

// 2. BACKGROUND REFRESH (prevent expiration stampede)
FUNCTION set_with_background_refresh(key, value, ttl):
    cache.set(key, value, ttl)
    schedule_refresh(key, ttl * 0.8)  // Refresh at 80% of TTL

FUNCTION scheduled_refresh(key):
    IF cache.ttl(key) < original_ttl * 0.2:
        // Less than 20% TTL remaining, refresh
        new_value = fetch_from_source(key)
        cache.set(key, new_value, ttl)

// 3. CIRCUIT BREAKER (protect backend)
CLASS CacheCircuitBreaker:
    failures: int = 0
    threshold: int = 5
    state: CLOSED | OPEN | HALF_OPEN
    
    FUNCTION execute(operation):
        IF state == OPEN:
            IF time_since_open > 30s:
                state = HALF_OPEN
            ELSE:
                THROW CircuitOpenException
        
        TRY:
            result = operation()
            IF state == HALF_OPEN:
                state = CLOSED
                failures = 0
            RETURN result
        CATCH:
            failures++
            IF failures >= threshold:
                state = OPEN
            THROW

// 4. BULKHEAD (isolate failures)
CLASS CacheBulkhead:
    // Separate thread pools per cache
    session_cache_pool: ThreadPool(size=20)
    product_cache_pool: ThreadPool(size=50)
    analytics_cache_pool: ThreadPool(size=10)
    
    // Failure in one doesn't affect others
```

---

# Part 10: Performance Optimization & Hot Paths

## Critical Paths

```
HOT PATH 1: Cache Hit
├── Time budget: < 1ms
├── Operations: Hash lookup, memory read, deserialize
├── Optimization: Keep values small, efficient serialization

HOT PATH 2: Cache Miss + DB Fetch + Cache Write
├── Time budget: < 50ms
├── Operations: Cache lookup, DB query, cache write
├── Optimization: Async cache write, connection pooling

HOT PATH 3: Cache Invalidation
├── Time budget: < 5ms
├── Operations: Delete from all replicas
├── Optimization: Async invalidation, eventual consistency

COLD PATH: Cache Warming
├── Time budget: Minutes (background)
├── Operations: Bulk read from DB, bulk write to cache
├── Optimization: Batch operations, off-peak scheduling
```

## Caching Strategy Optimization

```
// Pseudocode: Multi-tier caching

TIER 1: L1 CACHE (In-Process)
├── Location: Application memory
├── Size: 100MB per instance
├── Latency: ~0.001ms
├── Use for: Ultra-hot keys, config, static data
├── Invalidation: TTL or process restart

TIER 2: L2 CACHE (Distributed)
├── Location: Redis/Memcached cluster
├── Size: 10GB+ shared
├── Latency: ~0.5ms
├── Use for: All cacheable data
├── Invalidation: TTL + explicit

TIER 3: ORIGIN (Database)
├── Location: Database server
├── Size: Full dataset
├── Latency: 5-50ms
├── Use for: Cache misses
├── Source of truth

FUNCTION multi_tier_get(key):
    // Try L1 first
    IF local_cache.has(key):
        RETURN local_cache.get(key)
    
    // Try L2
    value = distributed_cache.get(key)
    IF value IS NOT NULL:
        local_cache.set(key, value, ttl=60)  // Promote to L1
        RETURN value
    
    // Hit origin
    value = database.get(key)
    distributed_cache.set(key, value, ttl=300)
    local_cache.set(key, value, ttl=60)
    RETURN value
```

## Serialization Optimization

```
SERIALIZATION COMPARISON:

Format      | Size  | Serialize | Deserialize | Human-Readable
────────────────────────────────────────────────────────────────
JSON        | 100%  | Slow      | Slow        | Yes
MessagePack | 70%   | Fast      | Fast        | No
Protobuf    | 60%   | Fast      | Fast        | No
Avro        | 55%   | Fast      | Fast        | No (with schema)

RECOMMENDATION:
├── Development/debugging: JSON (readable)
├── Production (general): MessagePack (good balance)
├── Production (schema): Protobuf (best for structured data)
├── Large values: Compression (LZ4 or Snappy)

// Pseudocode: Conditional compression
FUNCTION serialize(value):
    serialized = msgpack.encode(value)
    IF len(serialized) > 1000:
        compressed = lz4.compress(serialized)
        RETURN PREFIX_COMPRESSED + compressed
    RETURN PREFIX_UNCOMPRESSED + serialized

FUNCTION deserialize(data):
    IF data.starts_with(PREFIX_COMPRESSED):
        data = lz4.decompress(data[1:])
    RETURN msgpack.decode(data)
```

## Backpressure and Load Shedding

```
// Pseudocode: Load shedding when cache is overloaded

FUNCTION get_with_load_shedding(key, priority):
    // Check current load
    current_load = cache.get_connection_count()
    max_load = cache.get_max_connections()
    load_ratio = current_load / max_load
    
    // Shed low-priority requests when overloaded
    IF load_ratio > 0.9:
        IF priority == LOW:
            metrics.increment("shed_low_priority")
            RETURN NULL  // Caller falls back to DB
    
    IF load_ratio > 0.95:
        IF priority != HIGH:
            metrics.increment("shed_medium_priority")
            RETURN NULL
    
    IF load_ratio > 0.99:
        // Only HIGH priority survives
        IF priority != HIGH:
            metrics.increment("shed_all_but_high")
            RETURN NULL
    
    RETURN cache.get(key)

// Request priority classification
FUNCTION classify_priority(request):
    IF request.user.is_paying:
        RETURN HIGH
    IF request.endpoint.is_critical:
        RETURN HIGH
    IF request.is_background:
        RETURN LOW
    RETURN MEDIUM
```

## Why Some Optimizations Are NOT Done

```
OPTIMIZATION NOT DONE: Cache Everything
├── Why attractive: Maximum hit rate, minimum DB load
├── Why rejected: Memory cost, diminishing returns
├── Staff thinking: Cache hot data only. 80% of requests hit 20% of keys.
├── Hit rate 95% vs 99%: 4x cost for 4% improvement. Not worth it.

OPTIMIZATION NOT DONE: Synchronous Replication
├── Why attractive: Strong consistency, no stale reads
├── Why rejected: 2-3x latency increase
├── Staff thinking: Eventual consistency acceptable for most caches.
├── If you need strong consistency, cache might not be the answer.

OPTIMIZATION NOT DONE: Complex Eviction Policies
├── Why attractive: Optimal cache utilization
├── Why rejected: CPU overhead, complexity
├── Staff thinking: LRU is "good enough" for 99% of cases.
├── If LRU doesn't work, rethink caching strategy.

OPTIMIZATION NOT DONE: Predictive Pre-warming
├── Why attractive: Zero cache misses
├── Why rejected: Hard to predict, wasted resources
├── Staff thinking: Reactive warming is simpler and sufficient.
├── Pre-warm only for known patterns (sales events, deployments).
```

---

# Part 11: Cost & Efficiency

## Major Cost Drivers

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CACHE COST BREAKDOWN                                     │
│                                                                             │
│   COST COMPONENT          PROPORTION    SCALING FACTOR                      │
│   ─────────────────────────────────────────────────────────────────────     │
│   Memory (RAM)            60-70%        Linear with data size               │
│   Network transfer        10-15%        Linear with QPS × value size        │
│   Compute (CPU)           5-10%         Linear with QPS (serialization)     │
│   Replication             15-20%        Multiplier on memory (1x-3x)        │
│   Management/Operations   5-10%         Roughly fixed                       │
│                                                                             │
│   COST EXAMPLES (managed Redis-like service):                               │
│   ├── 1GB cache, single node:     $25/month                                 │
│   ├── 10GB cache, single node:    $200/month                                │
│   ├── 10GB cache, with replica:   $400/month (2x)                           │
│   ├── 100GB cache, clustered:     $2,000/month                              │
│   └── 100GB cache, multi-region:  $6,000/month (3x)                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## How Cost Scales with Traffic

```
COST SCALING ANALYSIS:

Scenario: E-commerce product cache

TRAFFIC GROWTH:
├── Year 1: 1M daily users, 5M requests/day
├── Year 2: 5M daily users, 25M requests/day
├── Year 3: 20M daily users, 100M requests/day

CACHE SIZING:
├── Year 1: 1GB (hot products), $30/month
├── Year 2: 5GB (more products popular), $150/month
├── Year 3: 20GB (catalog growth), $500/month

COST PER 1000 REQUESTS:
├── Year 1: $30 / 150M requests = $0.0002
├── Year 2: $150 / 750M requests = $0.0002
├── Year 3: $500 / 3B requests = $0.00017

INSIGHT: Cache cost per request DECREASES with scale
Because: More requests amortize fixed memory cost

COMPARE TO DATABASE COST:
├── Database handling 100% traffic: $5,000/month
├── With 95% cache hit rate: $500/month (10x savings)
├── Cache cost: $500/month
├── Net savings: $4,000/month
```

## Trade-offs Between Cost and Reliability

```
TRADE-OFF 1: Replication
├── Without replicas: $X/month, single point of failure
├── With 1 replica: $2X/month, survives 1 node failure
├── With 2 replicas: $3X/month, survives 2 node failures
├── Decision: For production, 1 replica minimum. 2 for critical data.

TRADE-OFF 2: Memory vs Hit Rate
├── Smaller cache: Lower cost, more cache misses
├── Larger cache: Higher cost, fewer cache misses
├── Sweet spot: Cache working set only
├── Decision: Monitor eviction rate. If > 1%/hour, consider scaling.

TRADE-OFF 3: TTL Length
├── Shorter TTL: More DB hits, fresher data, lower cache value
├── Longer TTL: Fewer DB hits, staler data, higher cache value
├── Decision: Choose based on data volatility, not cost.

TRADE-OFF 4: Multi-Region
├── Single region: 1x cost, higher latency for remote users
├── Multi-region: 3x cost, low latency everywhere
├── Decision: Only if user latency justifies 3x cost.
```

## What Over-Engineering Looks Like

```
OVER-ENGINEERING EXAMPLE 1: Caching Everything
├── Symptom: 99.9% hit rate, 50GB cache for 50K daily users
├── Problem: Caching data that's rarely accessed
├── Reality: 90% hit rate with 5GB cache would be sufficient
├── Fix: Cache only hot data, let cold data miss

OVER-ENGINEERING EXAMPLE 2: Complex Invalidation
├── Symptom: Event-driven invalidation for every data change
├── Problem: Invalidation system more complex than the cache
├── Reality: TTL-based expiration would work for most data
├── Fix: Use TTL, explicit invalidation only for critical updates

OVER-ENGINEERING EXAMPLE 3: Perfect Consistency
├── Symptom: Distributed locks, 2PC for cache updates
├── Problem: Cache is now slower than database
├── Reality: Eventual consistency acceptable for most caches
├── Fix: Accept staleness, use simpler invalidation

OVER-ENGINEERING EXAMPLE 4: Over-Sharding
├── Symptom: 20 shards for 5GB of data
├── Problem: Coordination overhead exceeds benefits
├── Reality: Single node handles 100K+ ops/sec
├── Fix: Shard when you need to, not before
```

## Cost-Aware Redesign

```
SCENARIO: Cache costs growing faster than value

CURRENT STATE:
├── 100GB cache cluster: $3,000/month
├── 90% hit rate
├── Growing 20%/month
├── Projected Year 2: 600GB, $18,000/month

ANALYSIS:
├── What's in the cache?
│   ├── 60% user sessions (30-day TTL)
│   ├── 25% product data (1-hour TTL)
│   └── 15% search results (5-minute TTL)
├── What's the access pattern?
│   ├── Sessions: High hit rate, but long TTL inflates size
│   ├── Products: Moderate hit rate, reasonable
│   └── Search: Low hit rate (unique queries)

REDESIGN:
1. Sessions: Reduce TTL from 30 days to 7 days
   ├── Size reduction: 75%
   ├── Trade-off: Users re-login after 7 days
   └── Impact: 45GB → 11GB

2. Search: Remove from cache (low hit rate)
   ├── Size reduction: 100% of search cache
   ├── Trade-off: Search latency increases
   └── Impact: 15GB → 0GB

3. Products: Maintain (good ROI)
   └── Impact: 25GB → 25GB

RESULT:
├── Before: 100GB, $3,000/month
├── After: 36GB, $1,200/month
├── Savings: 60% cost reduction
├── Trade-off: Slightly more re-logins, slower search
```

---

# Part 12: Multi-Region & Global Considerations

## Data Locality

```
MULTI-REGION CACHE TOPOLOGY:

OPTION 1: Global Cache (Single Region)
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   US-West Users ──────────────────┐                                         │
│                                   │                                         │
│   US-East Users ──────────────────┼──────► Cache Cluster ──► Database       │
│                                   │         (US-Central)     (US-Central)   │
│   EU Users ───────────────────────┘                                         │
│                                                                             │
│   Pros: Simple, consistent                                                  │
│   Cons: High latency for EU users (100-150ms)                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

OPTION 2: Regional Caches with Global Database
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   US-West Users ──► US-West Cache ──┐                                       │
│                                     │                                       │
│   US-East Users ──► US-East Cache ──┼──────► Database (US-Central)          │
│                                     │                                       │
│   EU Users ──────► EU Cache ────────┘                                       │
│                                                                             │
│   Pros: Low latency for cache hits                                          │
│   Cons: Cache inconsistency across regions                                  │
│   Cons: Cache misses still have high latency to central DB                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

OPTION 3: Regional Caches with Regional Databases
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   US Users ──► US Cache ──► US Database ◄──────┐                            │
│                                                 │ Replication               │
│   EU Users ──► EU Cache ──► EU Database ◄──────┘                            │
│                                                                             │
│   Pros: Low latency everywhere                                              │
│   Cons: Complex replication, eventual consistency                           │
│   Cons: Highest cost                                                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Replication Strategies

```
STRATEGY 1: No Cross-Region Replication
├── Each region has independent cache
├── Cache misses go to local or central database
├── Simplest approach
├── Trade-off: Cold cache after failover to new region

STRATEGY 2: Async Cross-Region Replication
├── Writes replicate to other regions asynchronously
├── Typical lag: 50-200ms
├── Trade-off: Regions may have stale data

STRATEGY 3: Invalidation Broadcast
├── Don't replicate data, only invalidations
├── On write: broadcast invalidation to all regions
├── Each region repopulates on next read
├── Trade-off: More cache misses, but simpler

// Pseudocode: Invalidation broadcast
FUNCTION update_with_broadcast(key, value):
    // Update local database
    database.write(key, value)
    
    // Invalidate local cache
    local_cache.delete(key)
    
    // Broadcast invalidation to other regions
    FOR region IN other_regions:
        async: region.invalidate(key)
```

## Multi-Region Failure Handling

```
FAILURE SCENARIO: Regional Cache Failure

Region A cache fails completely
├── Option 1: Route to Region B cache (cross-region latency)
├── Option 2: Hit database directly (DB load increases)
├── Option 3: Serve stale data from local backup (inconsistency)

DECISION FACTORS:
├── How critical is latency? → Option 2 or 3
├── How critical is consistency? → Option 1 or 2
├── Can database handle the load? → Option 1 or 3

FAILURE SCENARIO: Cross-Region Network Partition

Regions A and B can't communicate
├── Each region operates independently
├── Invalidations don't propagate
├── Data may diverge

RESOLUTION:
├── Detect partition (heartbeat failures)
├── Accept stale data during partition
├── After partition heals: reconcile or flush

// Pseudocode: Partition detection
FUNCTION check_region_connectivity():
    FOR region IN other_regions:
        IF NOT heartbeat(region, timeout=5s):
            mark_region_partitioned(region)
            // Stop relying on cross-region invalidation
            // Reduce TTL to limit staleness
            reduce_ttl_for_all_keys(max_ttl=60s)
```

## When Multi-Region Is NOT Worth It

```
CRITERIA: Skip multi-region caching if:

1. User base is geographically concentrated
   ├── 90% of users in one region
   ├── Other regions can tolerate extra 50-100ms
   └── Simple > Complex

2. Data changes frequently
   ├── Cross-region consistency is hard
   ├── TTL-based caching would be very short
   └── Benefit of caching diminishes

3. Cache hit rate is low
   ├── Most requests hit database anyway
   ├── Multi-region cache adds cost without proportional benefit
   └── Focus on improving hit rate first

4. Cost exceeds benefit
   ├── Multi-region is 3x+ cost
   ├── Latency improvement: 100ms → 5ms (for cache hits)
   ├── If hit rate is 50%, average improvement is 47.5ms
   └── Is 47.5ms worth 3x cost?

5. Operational complexity is too high
   ├── Small team can't manage multi-region
   ├── Incidents become harder to debug
   └── Start simple, add regions when needed
```

---

# Part 13: Security & Abuse Considerations

## Abuse Vectors

```
ABUSE 1: CACHE POISONING
├── Attack: Inject malicious data into cache
├── Method: Exploit application bug to cache attacker-controlled content
├── Impact: All users receive malicious content
├── Prevention: Validate data before caching, sign cached values

ABUSE 2: CACHE KEY MANIPULATION
├── Attack: Craft keys to access other users' data
├── Method: Predict or guess cache key format
├── Impact: Data leakage, privacy violation
├── Prevention: Include user ID in key, validate ownership

ABUSE 3: DENIAL OF SERVICE (Cache Busting)
├── Attack: Send unique keys to bypass cache, overload backend
├── Method: Add random parameters to requests
├── Impact: Cache useless, backend overwhelmed
├── Prevention: Normalize keys, rate limit cache misses

ABUSE 4: INFORMATION DISCLOSURE VIA TIMING
├── Attack: Measure response time to infer cache contents
├── Method: Cached = fast (1ms), not cached = slow (50ms)
├── Impact: Attacker learns what data exists
├── Prevention: Add random delay, or always return same timing

ABUSE 5: CACHE OVERFLOW
├── Attack: Store huge values to exhaust cache memory
├── Method: Upload large data that gets cached
├── Impact: Legitimate data evicted, performance degrades
├── Prevention: Limit value size, per-user quotas
```

## Data Exposure Risks

```
RISK 1: Sensitive Data in Cache
├── Problem: Passwords, tokens, PII cached in memory
├── Impact: Memory dump exposes sensitive data
├── Mitigation: Don't cache sensitive data, or encrypt it

RISK 2: Shared Cache Between Tenants
├── Problem: Multi-tenant app uses single cache
├── Impact: Key collision exposes data across tenants
├── Mitigation: Prefix keys with tenant ID, separate caches

RISK 3: Cache Logs Expose Data
├── Problem: Cache access logs include keys and values
├── Impact: Log access reveals user data
├── Mitigation: Redact sensitive data from logs

RISK 4: Unencrypted Cache Traffic
├── Problem: Cache traffic is plaintext on network
├── Impact: Network sniffer captures cached data
├── Mitigation: TLS for cache connections
```

## Privilege Boundaries

```
ACCESS CONTROL MODEL:

PRINCIPLE 1: Least Privilege
├── Application has read/write to its namespace only
├── Admin has cluster-wide access
├── Monitoring has read-only access

PRINCIPLE 2: Namespace Isolation
├── Each service has isolated key prefix
├── Service A cannot access service B's keys
├── Implemented via key prefix + auth

PRINCIPLE 3: Command Restriction
├── Restrict dangerous commands (FLUSHALL, KEYS *)
├── Production: Disable DEBUG, CONFIG commands
├── Only admin can run administrative commands

// Pseudocode: ACL for cache
RULES:
    service_a:
        prefix: "service_a:*"
        commands: GET, SET, DELETE, EXPIRE
    
    service_b:
        prefix: "service_b:*"
        commands: GET, SET, DELETE, EXPIRE
    
    admin:
        prefix: "*"
        commands: ALL
    
    monitoring:
        prefix: "*"
        commands: GET, INFO, SCAN
```

## Why Perfect Security Is Impossible

```
ACCEPT THESE RISKS:

1. Memory is readable
   ├── If attacker has server access, they can read memory
   ├── Cache is in-memory, therefore exposed
   ├── Mitigation: Limit server access, not cache design

2. Network is sniffable
   ├── Even with TLS, metadata (key names) may leak
   ├── Traffic analysis possible
   ├── Mitigation: Use TLS, monitor for anomalies

3. Cached data can be stale
   ├── User permissions may have changed
   ├── Cached authorization decisions may be wrong
   ├── Mitigation: Short TTL for permission data, re-validate critical ops

4. Timing attacks are hard to prevent
   ├── Constant-time cache operations add latency
   ├── Trade-off may not be worth it for most apps
   ├── Mitigation: Accept risk for non-critical data

STAFF PRINCIPLE:
"Design for defense in depth. Cache is one layer.
Authentication, authorization, encryption, monitoring are others.
No single layer is perfect."
```

---

# Part 14: Evolution Over Time

## V1: Naive Design

```
V1 ARCHITECTURE: Single-Node In-Memory Cache

┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   Application ──────────────────► Single Redis Node ◄──── Database          │
│                                   (16GB RAM)                                │
│                                                                             │
│   Implementation:                                                           │
│   • Simple GET/SET with TTL                                                 │
│   • No replication                                                          │
│   • No clustering                                                           │
│   • Cache-aside pattern                                                     │
│                                                                             │
│   Works well for:                                                           │
│   • 10K requests/second                                                     │
│   • 5GB working set                                                         │
│   • Single application                                                      │
│   • Acceptable if cache fails (fallback to DB)                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## What Breaks First

```
BREAKING POINT 1: Single Point of Failure
├── Symptom: Cache node restarts, database overwhelmed
├── Cause: No redundancy
├── Solution: Add replica for failover

BREAKING POINT 2: Memory Limit
├── Symptom: Hit rate drops, evictions spike
├── Cause: Working set exceeds 16GB
├── Solution: Scale up RAM or shard across nodes

BREAKING POINT 3: Connection Limit
├── Symptom: Connection errors during traffic spikes
├── Cause: Too many application instances connecting
├── Solution: Connection pooling, or add nodes

BREAKING POINT 4: Hot Key
├── Symptom: Single node CPU saturated
├── Cause: One key receives 50%+ of traffic
├── Solution: Key replication, or local caching

BREAKING POINT 5: Cross-Region Latency
├── Symptom: Remote users experience slow cache hits
├── Cause: Single region, users distributed globally
├── Solution: Regional caches
```

## V2: Production-Hardened Design

```
V2 ARCHITECTURE: Clustered Cache with Replicas

┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │                    APPLICATION LAYER                            │       │
│   │  ┌─────────┐  ┌─────────┐  ┌─────────┐                          │       │
│   │  │  App 1  │  │  App 2  │  │  App N  │                          │       │
│   │  └────┬────┘  └────┬────┘  └────┬────┘                          │       │
│   │       │            │            │                               │       │
│   │       └──────┬─────┴────────────┘                               │       │
│   │              │                                                  │       │
│   │      ┌───────▼───────┐                                          │       │
│   │      │ Cache Client  │  Connection pooling, consistent hashing  │       │
│   │      └───────┬───────┘                                          │       │
│   └──────────────┼──────────────────────────────────────────────────┘       │
│                  │                                                          │
│   ┌──────────────┼──────────────────────────────────────────────────┐       │
│   │              │           CACHE CLUSTER                          │       │
│   │    ┌─────────┴──────────┬──────────────────┐                    │       │
│   │    ▼                    ▼                  ▼                    │       │
│   │  ┌──────-┐            ┌────-──┐          ┌─────-─┐              │       │
│   │  │Shard1 │            │Shard2 │          │Shard3 │              │       │
│   │  │Primary│            │Primary│          │Primary│              │       │
│   │  └──┬───-┘            └──┬───-┘          └──┬───-┘              │       │
│   │     │                    │                  │                   │       │
│   │  ┌──▼───-┐            ┌──▼──-─┐          ┌──▼───-┐              │       │
│   │  │Replica│            │Replica│          │Replica│              │       │
│   │  └─────-─┘            └──────-┘          └──────-┘              │       │
│   └─────────────────────────────────────────────────────────────────┘       │
│                                                                             │
│   Improvements over V1:                                                     │
│   • 3 shards for 3x memory and throughput                                   │
│   • Replicas for failover                                                   │
│   • Consistent hashing for minimal reshuffling                              │
│   • Connection pooling for efficiency                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## V3: Long-Term Stable Architecture

```
V3 ARCHITECTURE: Multi-Tier, Multi-Region Cache

┌─────────────────────────────────────────────────────────────────────────────┐
│                          US-WEST REGION                                     │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │  App Instances with L1 Cache (in-process)                       │       │
│   │  ┌──────┐  ┌──────┐  ┌──────┐                                   │       │
│   │  │App+L1│  │App+L1│  │App+L1│                                   │       │
│   │  └──┬───┘  └──┬───┘  └──┬───┘                                   │       │
│   │     └────────┬┴────────┬┘                                       │       │
│   │              ▼         ▼                                        │       │
│   │  ┌────────────────────────────────────────┐                     │       │
│   │  │    L2 Distributed Cache (Redis Cluster)│                     │       │
│   │  │    6 shards, each with replica         │                     │       │
│   │  └────────────────────┬───────────────────┘                     │       │
│   │                       │                                         │       │
│   │  ┌────────────────────▼───────────────────┐                     │       │
│   │  │    Regional Database (PostgreSQL)       │                    │       │
│   │  └────────────────────┬───────────────────┘                     │       │
│   └───────────────────────┼─────────────────────────────────────────┘       │
│                           │                                                 │
│                           │ Replication                                     │
│                           ▼                                                 │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │                   EU REGION (similar structure)                 │       │
│   └─────────────────────────────────────────────────────────────────┘       │
│                                                                             │
│   Evolution drivers:                                                        │
│   • L1 cache: Reduce L2 load for ultra-hot keys                             │
│   • Multi-region: Serve global users with low latency                       │
│   • Regional databases: Full stack in each region                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Cache Migration Strategies

```
SCENARIO: Migrating from old cache cluster to new cache cluster
(e.g., Redis 4 → Redis 7, or Elasticache → self-managed Redis)

THE HARD PROBLEM:
├── Can't just switch over (cold cache = DB overwhelmed)
├── Can't run forever in dual-write mode (cost, complexity)
├── Data in old cache must be accessible during migration
└── Rollback must be possible if new cache has issues

STRATEGY 1: Dual-Write, Gradual Read Migration

Phase 1 (Dual-Write):
├── Writes go to BOTH old and new cache
├── Reads go to old cache only
├── Duration: Until new cache is warm
├── Metric: New cache hit rate approaching old cache hit rate

// Pseudocode
FUNCTION set_during_migration(key, value, ttl):
    old_cache.set(key, value, ttl)
    async: new_cache.set(key, value, ttl)  // Async to not add latency

FUNCTION get_during_migration(key):
    RETURN old_cache.get(key)  // Still reading from old

Phase 2 (Shadow Read):
├── Writes go to BOTH caches
├── Reads go to old cache, but also read new cache in background
├── Compare results, log discrepancies
├── Duration: Until discrepancy rate < 0.1%

FUNCTION get_during_shadow(key):
    value = old_cache.get(key)
    async: compare_with_new_cache(key, value)
    RETURN value

Phase 3 (Gradual Cutover):
├── Writes go to BOTH caches
├── Reads gradually shift to new cache (10% → 50% → 100%)
├── Monitor latency and error rate at each step
├── Duration: 1-2 weeks

FUNCTION get_during_cutover(key, user_id):
    IF hash(user_id) % 100 < migration_percentage:
        RETURN new_cache.get(key) OR old_cache.get(key)
    ELSE:
        RETURN old_cache.get(key)

Phase 4 (Cleanup):
├── Reads 100% from new cache
├── Stop writing to old cache
├── Decommission old cache after 1 week buffer
└── Total migration: 3-4 weeks

STRATEGY 2: Key-by-Key Migration (for large caches)

Migrate keys in batches, partition by key prefix or hash range.

// Pseudocode
FUNCTION migrate_key_range(start_hash, end_hash):
    FOR key IN old_cache.scan(start_hash, end_hash):
        value = old_cache.get(key)
        IF value IS NOT NULL:
            ttl = old_cache.ttl(key)
            new_cache.set(key, value, ttl)
            migrated_keys.add(key)

FUNCTION get_during_key_migration(key):
    IF key IN migrated_keys:
        RETURN new_cache.get(key)
    ELSE:
        RETURN old_cache.get(key)

MIGRATION RISKS AND MITIGATIONS:

Risk 1: New cache slower than old
├── Detection: Compare P99 latencies during shadow read
├── Mitigation: Tune new cache before cutover
└── Rollback: Revert to old cache immediately

Risk 2: Data loss during migration
├── Detection: Compare key counts, sample values
├── Mitigation: Dual-write ensures new writes are in both
└── Note: Old data naturally expires via TTL; not a loss

Risk 3: Inconsistency during migration
├── Detection: Shadow comparison logs
├── Mitigation: Accept brief inconsistency (cache is best-effort)
└── Resolution: Full cache flush if critical inconsistency detected

STAFF INSIGHT:
"Cache migration is lower risk than database migration because cache
is ephemeral. The worst case is a cold cache, which is recoverable.
Don't over-engineer cache migrations."
```

## How Incidents Drive Redesign

```
INCIDENT 1: Cache Stampede Takes Down Database
├── What happened: Popular product cache expired, 10K concurrent DB hits
├── Impact: Database crashed, 30-minute outage
├── Fix: Implement request coalescing, staggered TTL
├── Redesign: Added background cache refresh for hot keys

INCIDENT 2: Stale Cache Shows Wrong Price
├── What happened: Product price updated, cache not invalidated
├── Impact: Customers saw old price for 5 hours
├── Fix: Reduced TTL, added explicit invalidation on price update
├── Redesign: Event-driven invalidation for critical data

INCIDENT 3: Memory Exhaustion Kills Cache Node
├── What happened: Large values cached without size limit
├── Impact: Node OOM, traffic spike to DB
├── Fix: Added max value size limit, better eviction
├── Redesign: Monitoring for memory utilization, capacity planning

INCIDENT 4: Serialization Bug Causes Data Corruption
├── What happened: Schema changed, old cached data unreadable
├── Impact: Application errors for 1 hour
├── Fix: Flushed cache, deployed schema-aware deserialization
├── Redesign: Versioned cache entries, backward-compatible schemas
```

---

# Part 14B: Operational Realities

## On-Call Runbook Essentials

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CACHE INCIDENT RESPONSE RUNBOOK                          │
│                                                                             │
│   ALERT: Cache Hit Rate Drop (< 80%)                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. Check cache memory utilization                                  │   │
│   │     └── > 90%? Evictions causing misses. Scale up or reduce TTL.    │   │
│   │  2. Check for hot key (single key > 10% of traffic)                 │   │
│   │     └── Hot key? Enable local caching for that key.                 │   │
│   │  3. Check recent deployments                                        │   │
│   │     └── Key format changed? Schema incompatibility?                 │   │
│   │  4. Check traffic pattern                                           │   │
│   │     └── New traffic hitting cold keys? Normal during viral event.   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ALERT: Cache Latency Spike (P99 > 10ms)                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. Check cache CPU utilization                                     │   │
│   │     └── > 80%? Overloaded. Scale out or shed load.                  │   │
│   │  2. Check network between app and cache                             │   │
│   │     └── Packet loss? Route change? Contact network team.            │   │
│   │  3. Check for large values (> 100KB)                                │   │
│   │     └── Large values added? Compress or split.                      │   │
│   │  4. Check connection count                                          │   │
│   │     └── Near limit? Add connection pooling or scale out.            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ALERT: Cache Node Down                                                    │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. Verify failover occurred (replica promoted)                     │   │
│   │     └── Yes? Monitor hit rate during warm-up.                       │   │
│   │     └── No? Manual failover or restart node.                        │   │
│   │  2. Check database load                                             │   │
│   │     └── Spiking? Enable aggressive caching, extend TTLs.            │   │
│   │  3. Check other nodes for similar symptoms                          │   │
│   │     └── Multiple failures? Check underlying infra.                  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ALERT: Database Overload (Cache-Related)                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. Check if cache is functioning                                   │   │
│   │     └── Cache down? Focus on cache recovery first.                  │   │
│   │  2. Check for thundering herd                                       │   │
│   │     └── Many requests for same key? Enable request coalescing.      │   │
│   │  3. Enable emergency mode                                           │   │
│   │     └── Extend all TTLs, serve stale data, reduce DB queries.       │   │
│   │  4. Shed non-critical traffic                                       │   │
│   │     └── Disable background jobs, analytics, non-essential features. │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Monitoring Dashboards

```
CACHE HEALTH DASHBOARD - KEY METRICS:

Row 1: Traffic & Performance
├── Panel 1: Cache QPS (reads, writes, deletes)
├── Panel 2: Latency (P50, P95, P99) by operation
├── Panel 3: Hit Rate (target: > 90%)
└── Panel 4: Error Rate (connection errors, timeouts)

Row 2: Resource Utilization
├── Panel 1: Memory Utilization (% of max, by node)
├── Panel 2: CPU Utilization (by node)
├── Panel 3: Network I/O (bytes in/out)
└── Panel 4: Connection Count (vs. max connections)

Row 3: Cache Behavior
├── Panel 1: Eviction Rate (keys evicted/sec)
├── Panel 2: Expiration Rate (keys expired/sec)
├── Panel 3: Key Count (total keys stored)
└── Panel 4: Average Value Size

Row 4: Downstream Impact
├── Panel 1: Database QPS (should be low if cache healthy)
├── Panel 2: Application Latency (by endpoint)
├── Panel 3: Error Rate (by endpoint)
└── Panel 4: Cache-related errors (by type)

ALERTING THRESHOLDS:
├── Hit rate < 80%: Warning
├── Hit rate < 60%: Critical (page on-call)
├── P99 latency > 10ms: Warning
├── P99 latency > 50ms: Critical
├── Memory > 85%: Warning
├── Memory > 95%: Critical
├── Eviction rate > 1000/sec: Warning
├── Error rate > 1%: Critical
```

## Cache Ownership Across Teams

```
OWNERSHIP MODEL:

PLATFORM TEAM OWNS:
├── Cache infrastructure (cluster provisioning, scaling)
├── Monitoring and alerting framework
├── Client library (connection pooling, circuit breakers)
├── Capacity planning and cost tracking
└── Cache migration tooling

APPLICATION TEAMS OWN:
├── Cache key design and naming conventions
├── TTL selection for their data
├── Invalidation logic
├── Fallback behavior on cache failure
└── Testing cache behavior

SHARED RESPONSIBILITIES:
├── Incident response (platform for infra, app for logic)
├── Performance optimization
├── Security review
└── Cost allocation

COMMON OWNERSHIP FAILURES:
├── No owner: "Cache just works" → Nobody monitors it → Outage
├── Platform-only: App teams don't understand cache behavior
├── App-only: Cache infra becomes inconsistent across teams
└── Solution: Clear RACI matrix, regular cross-team reviews

STAFF INSIGHT:
"Cache is infrastructure that application teams consume. Platform
provides the capability; application teams use it responsibly.
Neither can succeed without the other."
```

---

# Part 15: Alternatives & Explicit Rejections

## Alternative 1: No Cache (Hit Database Directly)

```
WHY IT SEEMS ATTRACTIVE:
├── Simplest architecture
├── No cache invalidation problems
├── No stale data
├── No additional infrastructure

WHY STAFF ENGINEER REJECTS IT:
├── Database can't handle read load at scale
├── Latency is 10-100x higher than cached
├── Cost of scaling database is prohibitive
├── Some data is expensive to compute on every request

WHEN IT'S ACTUALLY CORRECT:
├── Very low traffic (< 100 req/sec)
├── Database is already fast enough
├── Data changes constantly (cache would never hit)
├── Strong consistency is absolutely required
```

## Alternative 2: CDN as Primary Cache

```
WHY IT SEEMS ATTRACTIVE:
├── Managed, highly available
├── Global distribution built-in
├── Edge caching for low latency
├── Handles traffic spikes

WHY STAFF ENGINEER REJECTS IT (for most backend caching):
├── CDN is optimized for static content, not dynamic
├── Invalidation is slow (seconds to minutes)
├── Can't cache per-user personalized data effectively
├── Not designed for high-frequency updates
├── Limited control over caching logic

WHEN IT'S ACTUALLY CORRECT:
├── Static assets (images, JS, CSS)
├── Mostly static pages (blog posts, landing pages)
├── Public API responses that rarely change
├── When edge latency is critical
```

## Alternative 3: Database Read Replicas Instead of Cache

```
WHY IT SEEMS ATTRACTIVE:
├── Data is always fresh (replication lag only)
├── No cache invalidation needed
├── Scales reads horizontally
├── Same query interface as primary

WHY STAFF ENGINEER REJECTS IT (as sole solution):
├── Replication lag means eventual consistency anyway
├── Read replicas still have query overhead
├── Can't compete with in-memory cache latency
├── Costs more than cache per request served
├── Doesn't help with expensive computation caching

WHEN IT'S ACTUALLY CORRECT:
├── Complex queries that can't be easily cached
├── When consistency requirements are high
├── As second tier behind cache (cache miss → replica → primary)
├── Analytics queries that shouldn't hit primary
```

## Alternative 4: Application-Local Cache Only

```
WHY IT SEEMS ATTRACTIVE:
├── Fastest possible (no network)
├── No additional infrastructure
├── Simple implementation
├── No cache cluster to manage

WHY STAFF ENGINEER REJECTS IT (as sole solution):
├── Each instance has separate cache (low hit rate)
├── Memory limited per instance
├── Cache cold after deploy/restart
├── No sharing between instances

WHEN IT'S ACTUALLY CORRECT:
├── As L1 cache in front of distributed cache
├── For truly static configuration data
├── For ultra-hot keys (few keys, accessed constantly)
├── Single-instance applications
```

---

# Part 16: Interview Calibration (Staff Signal)

## How Interviewers Probe Caching

```
PROBE 1: "Your API is slow. How would you add caching?"
├── L5: "Add Redis with 5-minute TTL"
├── L6: "First, I'd identify what's slow. Is it database? Computation?
│        Then I'd analyze access patterns—hit rate, staleness tolerance.
│        Cache makes sense if hit rate > 80% and staleness is acceptable.
│        I'd design for cache failure—what happens when Redis is down?"

PROBE 2: "How do you handle cache invalidation?"
├── L5: "Delete the cache key when data changes"
├── L6: "It depends on consistency requirements. For most data, TTL is
│        sufficient—simpler and handles edge cases. For critical data
│        that users must see updated immediately, I'd use explicit
│        invalidation. I'd also consider the race condition between
│        database write and cache delete."

PROBE 3: "What happens when your cache fails?"
├── L5: "We fall back to the database"
├── L6: "At our scale, all traffic to database would overwhelm it.
│        I'd implement circuit breakers, rate limiting to DB, and
│        graceful degradation. Maybe serve stale data from local
│        cache. I'd also have cache replicas to reduce failure likelihood."

PROBE 4: "How do you size your cache?"
├── L5: "As big as possible to maximize hit rate"
├── L6: "I'd analyze the working set—what data is accessed frequently?
│        Usually 20% of keys serve 80% of traffic. I'd cache that hot
│        data, monitor eviction rate, and scale when evictions impact
│        hit rate. Larger cache has diminishing returns."
```

## Common L5 Mistakes

```
MISTAKE 1: Treating Cache as Primary Storage
├── L5: "We'll just store it in Redis"
├── Problem: Cache is ephemeral; data can be lost
├── L6: "Cache is always backed by a source of truth"

MISTAKE 2: Ignoring Cache Failure
├── L5: "If cache is down, we hit the database"
├── Problem: Database can't handle full load
├── L6: "Cache failure is a critical scenario that needs specific design"

MISTAKE 3: Caching Everything
├── L5: "We cache all database queries"
├── Problem: Low-value caching wastes resources
├── L6: "Cache selectively based on access patterns and value"

MISTAKE 4: Assuming Perfect Invalidation
├── L5: "We invalidate on every write, so cache is always fresh"
├── Problem: Race conditions, missed invalidations
├── L6: "Cache is eventually consistent; design for staleness"

MISTAKE 5: Ignoring Serialization Cost
├── L5: "We use JSON for cache entries"
├── Problem: JSON is slow and large
├── L6: "Serialization format affects latency and memory; choose wisely"
```

## Staff-Level Phrases

```
ON CACHE STRATEGY:
"Caching trades consistency for performance. The key question is:
what's our staleness tolerance?"

"Before adding cache, I'd analyze the access pattern. If hit rate
will be below 80%, cache might not be worth the complexity."

ON INVALIDATION:
"TTL-based expiration handles 90% of cases. Explicit invalidation
is for the 10% where staleness is unacceptable."

"There's a race between database write and cache invalidation.
I'd delete-then-write, not write-then-delete."

ON FAILURE:
"Cache failure is when the system is most vulnerable. I'd design
for it explicitly—circuit breakers, degradation, rate limiting."

"If our cache fails and all traffic hits the database, we'll have
a cascading failure. We need cache redundancy."

ON SIZING:
"Memory is finite. I'd cache the working set—hot data that serves
most requests—not the entire dataset."

ON ARCHITECTURE:
"I'd consider multi-tier caching: L1 in-process for ultra-hot keys,
L2 distributed for everything else."
```

---

# Part 17: Diagrams

## Diagram 1: Cache Read/Write Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CACHE-ASIDE READ/WRITE PATTERN                           │
│                                                                             │
│   READ PATH:                                                                │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   Application                                                       │   │
│   │       │                                                             │   │
│   │       ├──► 1. GET key ──────────────► Cache                         │   │
│   │       │                                  │                          │   │
│   │       │    ┌──────────────────────────┐  │                          │   │
│   │       │    │ HIT: Return cached value │◄─┤                          │   │
│   │       │    └──────────────────────────┘  │                          │   │
│   │       │                                  │                          │   │
│   │       │    ┌──────────────────────────┐  │                          │   │
│   │       │◄───┤ MISS: Return null        │◄─┘                          │   │
│   │       │    └──────────────────────────┘                             │   │
│   │       │                                                             │   │
│   │       ├──► 2. Query ─────────────────► Database                     │   │
│   │       │                                  │                          │   │
│   │       │◄─── Return data ◄────────────────┘                          │   │
│   │       │                                                             │   │
│   │       └──► 3. SET key, value ────────► Cache                        │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   WRITE PATH (Invalidation):                                                │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   Application                                                       │   │
│   │       │                                                             │   │
│   │       ├──► 1. DELETE key ────────────► Cache (invalidate first)     │   │
│   │       │                                                             │   │
│   │       └──► 2. UPDATE ────────────────► Database                     │   │
│   │                                                                     │   │
│   │   Next read will miss cache and fetch fresh data                    │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   WHY DELETE BEFORE UPDATE:                                                 │
│   • If update fails, cache is already invalidated (safe)                    │
│   • If delete fails, update still succeeds (DB is truth)                    │
│   • Opposite order risks stale cache if delete fails after update           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 2: Cache Stampede and Solution

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CACHE STAMPEDE PROBLEM & SOLUTION                        │
│                                                                             │
│   THE PROBLEM:                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   T=0: Cache entry "hot_product" expires                            │   │
│   │                                                                     │   │
│   │   Request 1 ────► Cache MISS ────► Database ────┐                   │   │
│   │   Request 2 ────► Cache MISS ────► Database ────┤                   │   │
│   │   Request 3 ────► Cache MISS ────► Database ────┤                   │   │
│   │   ...                              ...          │                   │   │
│   │   Request 1000 ─► Cache MISS ────► Database ────┤                   │   │
│   │                                                 ▼                   │   │
│   │                                         DATABASE OVERLOADED         │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   THE SOLUTION (Request Coalescing):                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   T=0: Cache entry "hot_product" expires                            │   │
│   │                                                                     │   │
│   │   Request 1 ────► Cache MISS ────► Acquire Lock ──► Database        │   │
│   │                                         ▲                 │         │   │
│   │   Request 2 ────► Cache MISS ────► Lock taken, WAIT       │         │   │
│   │   Request 3 ────► Cache MISS ────► Lock taken, WAIT       │         │   │
│   │   ...                                   │                 │         │   │
│   │   Request 1000 ─► Cache MISS ────► Lock taken, WAIT       │         │   │
│   │                                         │                 │         │   │
│   │                                         │    ┌────────────┘         │   │
│   │                                         │    ▼                      │   │
│   │                                         │  Cache populated          │   │
│   │                                         │    │                      │   │
│   │   All waiting ◄─────────────────────────┴────┘                      │   │
│   │   requests get                                                      │   │
│   │   cached value                                                      │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ONLY ONE DATABASE QUERY instead of 1000                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 3: Multi-Tier Cache Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MULTI-TIER CACHING ARCHITECTURE                          │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        L1: In-Process Cache                         │   │
│   │                                                                     │   │
│   │   ┌─────────┐    ┌─────────┐    ┌─────────┐                         │   │
│   │   │  App 1  │    │  App 2  │    │  App 3  │                         │   │
│   │   │ ┌─────┐ │    │ ┌─────┐ │    │ ┌─────┐ │                         │   │
│   │   │ │ L1  │ │    │ │ L1  │ │    │ │ L1  │ │   Size: 100MB/instance  │   │
│   │   │ │Cache│ │    │ │Cache│ │    │ │Cache│ │   Latency: 0.01ms       │   │
│   │   │ └─────┘ │    │ └─────┘ │    │ └─────┘ │   Use: Ultra-hot keys   │   │
│   │   └────┬────┘    └────┬────┘    └────┬────┘                         │   │
│   │        │              │              │                              │   │
│   └────────┼──────────────┼──────────────┼──────────────────────────────┘   │
│            │              │              │                                  │
│            └──────────────┼──────────────┘                                  │
│                           │                                                 │
│   ┌───────────────────────┼─────────────────────────────────────────────┐   │
│   │                       ▼        L2: Distributed Cache                │   │
│   │                                                                     │   │
│   │     ┌──────────────────────────────────────────────────┐            │   │
│   │     │                 Redis Cluster                    │            │   │
│   │     │   ┌───────┐  ┌───────┐  ┌───────┐  ┌───────┐     │            │   │
│   │     │   │Shard 1│  │Shard 2│  │Shard 3│  │Shard 4│     │            │   │
│   │     │   └───────┘  └───────┘  └───────┘  └───────┘     │            │   │
│   │     └──────────────────────┬───────────────────────────┘            │   │
│   │                            │                                        │   │
│   │                            │   Size: 50GB total                     │   │
│   │                            │   Latency: 0.5ms                       │   │
│   │                            │   Use: All cacheable data              │   │
│   │                            │                                        │   │
│   └────────────────────────────┼────────────────────────────────────────┘   │
│                                │                                            │
│                                │                                            │
│   ┌────────────────────────────┼────────────────────────────────────────┐   │
│   │                            ▼        L3: Database (Origin)           │   │
│   │                                                                     │   │
│   │                    ┌──────────────────┐                             │   │
│   │                    │    PostgreSQL    │   Size: 500GB               │   │
│   │                    │ (Source of Truth)│   Latency: 5-50ms           │   │
│   │                    └──────────────────┘   Use: Cache misses         │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   REQUEST FLOW:                                                             │
│   1. Check L1 (in-process) → Hit: 0.01ms                                    │
│   2. Check L2 (distributed) → Hit: 0.5ms                                    │
│   3. Query L3 (database) → Response: 5-50ms, populate L1 and L2             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Diagram 4: Cache Failure and Degradation

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CACHE FAILURE DEGRADATION PATH                           │
│                                                                             │
│   NORMAL STATE:                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   Requests ──95%──► Cache Hit ──────────► Response (1ms)            │   │
│   │            └──5%──► Cache Miss ──► DB ──► Response (10ms)           │   │
│   │                                                                     │   │
│   │   Database load: 5% of requests                                     │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   CACHE FAILURE - NO PROTECTION:                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   Requests ──100%─► Cache Fail ──► All to DB ──► DB OVERWHELMED     │   │
│   │                                                     │               │   │
│   │                                                     ▼               │   │
│   │                                            CASCADING FAILURE        │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   CACHE FAILURE - WITH PROTECTION:                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   Requests ────────────────────────────────────────────────────     │   │
│   │       │                                                             │   │
│   │       ├──► Cache Fail ──► Circuit Breaker ──► Check local cache     │   │
│   │       │                                              │              │   │
│   │       │                        ┌─────────────────────┴────────┐     │   │
│   │       │                        │                              │     │   │
│   │       │                        ▼                              ▼     │   │
│   │       │               Local cache hit           Local cache miss    │   │
│   │       │               (stale OK)                      │             │   │
│   │       │                   │                           ▼             │   │
│   │       │                   │                 Rate limiter to DB      │   │
│   │       │                   │                      │        │         │   │
│   │       │                   │                 Allowed    Rejected     │   │
│   │       │                   │                    │           │        │   │
│   │       │                   ▼                    ▼           ▼        │   │
│   │       │              Response              Response   Degraded      │   │
│   │       │              (stale)               (fresh)    Response      │   │
│   │                                                                     │   │
│   │   Database load: Rate limited to sustainable level                  │   │
│   │   User experience: Some stale data, some errors, but no outage      │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 17B: Google L6 Interview Follow-Ups This Design Must Survive

```
┌─────────────────────────────────────────────────────────────────────────────┐
│           INTERVIEWER FOLLOW-UP QUESTIONS AND HOW TO ANSWER                 │
│                                                                             │
│   These are questions Google L6 interviewers will ask to probe depth.       │
│   Your cache design must have answers ready.                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

QUESTION 1: "What happens if your cache gets 10x traffic tomorrow?"

What they're probing:
├── Do you understand cache scaling limits?
├── Have you thought about capacity planning?
└── Can you identify breaking points?

Strong answer:
"At 10x traffic, I'd first check if we're CPU-bound or memory-bound.
For our current design:
- CPU: Single Redis node handles ~100K ops/sec. At 10x, we'd need 
  to shard across 3-4 nodes using consistent hashing.
- Memory: If hit rate stays the same, memory needs don't change much.
  But higher traffic might mean more unique keys, so I'd monitor
  eviction rate.
- Hot keys: At 10x, any hot key becomes critical. I'd add L1 in-process
  caching for the top 100 keys to prevent single-node overload.
- The first thing that would break: connection limits. I'd increase
  connection pooling and add a proxy layer."

QUESTION 2: "How do you handle a cache key that gets 50% of all traffic?"

What they're probing:
├── Do you understand hot key problems?
├── Can you propose multiple solutions?
└── Do you understand trade-offs?

Strong answer:
"This is the hot key problem. Several approaches:

1. L1 in-process cache: Cache this key locally in each app instance.
   Pro: Near-zero latency. Con: Invalidation is harder across instances.

2. Key replication: Replicate the key to multiple shards with random
   suffix (e.g., hot_key:1, hot_key:2, hot_key:3). Read from random shard.
   Pro: Distributes load. Con: More cache memory, invalidation complexity.

3. Request coalescing: If key expires, only one request fetches while
   others wait. Pro: Prevents stampede. Con: Slight latency increase.

For this case, I'd use L1 cache with short TTL (5-10 seconds) to absorb
most reads, with L2 distributed cache as backup. Invalidation would
broadcast to all app instances via pub/sub."

QUESTION 3: "Your cache shows 95% hit rate but users complain about slowness. What's happening?"

What they're probing:
├── Can you debug non-obvious issues?
├── Do you understand cache as part of larger system?
└── Do you look at the right metrics?

Strong answer:
"95% hit rate sounds good, but I'd investigate:

1. Cache latency: Is the cache itself slow? Check P99, not just P50.
   A slow cache at P99 = 100ms affects 5% of requests significantly.

2. The 5% misses: Are they on critical paths? If the 5% misses are
   for user-specific data that's accessed on every request, that's
   a problem. I'd segment hit rate by key type.

3. Miss latency amplification: The 5% cache misses might be hitting
   an overloaded database. Cache miss + slow DB = very slow response.

4. Wrong data cached: Are we caching data that's not on the hot path?
   High hit rate on unimportant data doesn't help user experience.

I'd look at end-to-end latency by cache hit vs miss, and identify
which specific cache misses correlate with user complaints."

QUESTION 4: "How do you prevent stale data from causing user-visible bugs?"

What they're probing:
├── Do you understand consistency trade-offs?
├── Can you design for specific consistency requirements?
└── Do you distinguish between different data types?

Strong answer:
"First, I'd categorize data by staleness tolerance:

Critical (must be fresh): Prices, inventory, account balance
├── Short TTL (30-60 seconds)
├── Explicit invalidation on write
├── Consider read-through for strongest consistency

Important (should be fresh): User profile, settings
├── Moderate TTL (5-15 minutes)
├── Invalidate on write by user (read-your-writes)
├── Other users can see slightly stale data

Nice-to-have (staleness OK): Recommendations, analytics
├── Long TTL (1-24 hours)
├── Background refresh
├── Stale data is acceptable

For critical data, I'd also implement:
- Version checking: Cache stores version; on read, verify against DB version
- Stale-while-revalidate: Serve stale, async refresh in background
- Monitoring: Alert if cache staleness exceeds expected bounds"

QUESTION 5: "Your cache cluster fails completely during peak traffic. Walk me through what happens."

What they're probing:
├── Have you designed for failure?
├── Do you understand cascading failure?
└── Can you design graceful degradation?

Strong answer:
"Cache failure during peak is a critical scenario. Here's the cascade:

Without protection:
T+0: Cache fails, 100% requests hit database
T+1min: Database overwhelmed (10x normal load)
T+2min: DB connection pool exhausted
T+3min: Full outage for all users

With protection (our design):
T+0: Cache fails, circuit breaker detects failures
T+10s: Circuit breaker opens, requests bypass cache
T+10s: Rate limiter kicks in for database (max 2x normal load)
T+10s: Local L1 cache starts serving stale data where possible
T+20s: Load shedding for non-critical endpoints
T+5min: Cache recovery begins (replica promotion or restart)
T+10min: Cache warming, gradual traffic restoration
T+30min: Full recovery

Key protections:
- Circuit breaker: Fast failure detection
- Rate limiting to DB: Prevent DB overload
- Local cache: Serve stale data as fallback
- Load shedding: Sacrifice non-critical requests
- Graceful degradation: Maintain core functionality"
```

---

# Part 18: Brainstorming, Exercises & Redesigns

## "What If X Changes?" Questions

```
1. What if data size grows 10x?
   ├── Current: 10GB cache
   ├── Future: 100GB needed
   ├── Options: More shards, tiered storage, selective caching
   └── Challenge: Cost grows linearly; may need to cache only hot data

2. What if consistency requirements become stricter?
   ├── Current: 5-minute TTL acceptable
   ├── Future: Must see updates within 1 second
   ├── Options: Shorter TTL, event-driven invalidation, write-through
   └── Challenge: More cache misses, more DB load

3. What if we need to cache personalized data?
   ├── Current: Same data for all users
   ├── Future: Each user sees different data
   ├── Options: Per-user keys, compute on read, segment caching
   └── Challenge: Hit rate drops dramatically, cache size explodes

4. What if cache latency becomes critical path?
   ├── Current: 1ms acceptable
   ├── Future: Must be < 0.1ms
   ├── Options: In-process cache, move cache closer, optimize serialization
   └── Challenge: Network latency is floor; may need L1 cache

5. What if we expand to 10 regions?
   ├── Current: 2 regions
   ├── Future: 10 regions globally
   ├── Options: Regional caches, global invalidation, accept staleness
   └── Challenge: Coordination complexity, cost multiplier
```

## Redesign Under New Constraints

```
EXERCISE 1: Redesign for Zero Downtime Deploys

Constraint: Cache must remain available during deploys
Current problem: Deploy clears in-process cache, cold start

Redesign:
├── Separate long-lived distributed cache from application
├── Pre-warm cache before cutting traffic
├── Gradual rollout to warm local caches
└── Share cache across old and new versions (schema compatibility)

EXERCISE 2: Redesign for Cost Reduction

Constraint: Reduce cache cost by 50%
Current: 100GB cache, $3,000/month

Redesign:
├── Analyze access patterns—what's actually hot?
├── Reduce TTL for low-value data (let it expire)
├── Compress values (LZ4 typically 50% reduction)
├── Remove rarely accessed data from cache
└── Consider tiered caching (hot in RAM, warm in SSD)

EXERCISE 3: Redesign for Strong Consistency

Constraint: Users must always see latest data
Current: TTL-based eventual consistency

Redesign:
├── Write-through caching (update cache on write)
├── Synchronous invalidation before DB commit
├── Read-through from database on critical paths
├── Accept higher latency as trade-off
└── Consider: is cache still valuable? Maybe read replicas instead.
```

## Failure Injection Exercises

```
EXERCISE 1: Cache Node Failure
├── Scenario: Kill one cache node without warning
├── Expected: Requests to that shard fail, then recover
├── Measure: Error rate, latency spike, recovery time
├── Questions:
│   ├── How long until failover completed?
│   ├── What happened to in-flight requests?
│   └── How long to warm the new node?

EXERCISE 2: Network Partition
├── Scenario: Isolate cache from half the application servers
├── Expected: Affected servers see timeouts, fallback to DB
├── Measure: Error rate by server, DB load spike
├── Questions:
│   ├── Did circuit breakers activate?
│   ├── Did DB handle the increased load?
│   └── Was data consistent after partition healed?

EXERCISE 3: Slow Cache
├── Scenario: Inject 100ms latency into cache responses
├── Expected: Application latency increases, may timeout
├── Measure: P99 latency, timeout rate, user impact
├── Questions:
│   ├── At what latency does application break?
│   ├── Do timeouts trigger fallback correctly?
│   └── Is slow cache worse than no cache?

EXERCISE 4: Cache Stampede
├── Scenario: Expire popular key at traffic peak
├── Expected: Many simultaneous DB hits
├── Measure: DB query rate, latency, success rate
├── Questions:
│   ├── Did request coalescing work?
│   ├── Did DB survive the spike?
│   └── How quickly was cache repopulated?
```

## Trade-off Debates

```
DEBATE 1: TTL vs Event-Driven Invalidation
├── TTL side: Simple, predictable, handles all cases
├── Event side: Fresher data, less wasted caching
├── Staff judgment: Start with TTL, add events for critical data

DEBATE 2: One Large Cache vs Many Small Caches
├── Large side: Better hit rate, shared hot data
├── Small side: Isolation, independent scaling, simpler failure
├── Staff judgment: Shared cache for common data, separate for isolation

DEBATE 3: Redis vs Memcached
├── Redis side: Rich data structures, persistence, replication
├── Memcached side: Simpler, faster for basic use cases
├── Staff judgment: Redis for features, Memcached for pure speed

DEBATE 4: Cache in Application vs Sidecar
├── Application: Lowest latency, simplest deployment
├── Sidecar: Language-agnostic, easier to update
├── Staff judgment: In-app for performance, sidecar for polyglot

DEBATE 5: Buy vs Build
├── Build: Full control, no vendor lock-in
├── Buy: Managed, reliable, less operational burden
├── Staff judgment: Buy unless you have specific requirements
```

---

# Summary

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              DISTRIBUTED CACHE: STAFF ENGINEER PRINCIPLES                   │
│                                                                             │
│   1. Caching is a trade-off, not a solution                                 │
│      └── You trade consistency for performance                              │
│                                                                             │
│   2. Every cache is eventually wrong                                        │
│      └── Design for staleness, not against it                               │
│                                                                             │
│   3. Cache failure is when you're most vulnerable                           │
│      └── Design degradation paths explicitly                                │
│                                                                             │
│   4. Hit rate determines cache value                                        │
│      └── Below 80%, reconsider if cache is worth it                         │
│                                                                             │
│   5. Cache the working set, not the whole dataset                           │
│      └── 20% of keys serve 80% of traffic                                   │
│                                                                             │
│   6. Invalidation is harder than caching                                    │
│      └── TTL handles most cases; explicit invalidation for the rest         │
│                                                                             │
│   7. Thundering herd will happen                                            │
│      └── Request coalescing and staggered TTL are essential                 │
│                                                                             │
│   8. Monitor what matters                                                   │
│      └── Hit rate, latency, evictions, memory utilization                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# End of Chapter 29

This chapter covered Distributed Caching at Staff Engineer depth—from foundational concepts through production-hardened architectures, failure handling, and evolution. The key insight: caching is powerful but dangerous. Used well, it makes systems fast and resilient. Used poorly, it introduces subtle bugs, inconsistency, and operational complexity. Staff Engineers understand these trade-offs and design accordingly.
