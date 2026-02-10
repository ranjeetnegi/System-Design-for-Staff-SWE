# Chapter 22: Caching at Scale — Redis, CDN, and Edge Systems

---

# Introduction

Caching is the most misunderstood tool in a system designer's toolkit. Junior engineers treat it as a performance optimization—add Redis, things get faster. Senior engineers understand cache invalidation is hard. But Staff Engineers see caching differently: **caching is a reliability and cost strategy that happens to improve performance**.

When designed well, caching:
- Absorbs traffic spikes that would crush your database
- Enables graceful degradation when backends fail
- Reduces infrastructure costs by 10-100x for read-heavy workloads
- Makes global distribution economically feasible

When designed poorly, caching:
- Creates consistency bugs that take months to diagnose
- Introduces new failure modes (cache stampedes, thundering herds)
- Masks underlying performance problems until they become critical
- Adds operational complexity that outweighs benefits

This section teaches caching as Staff Engineers practice it: as a system-wide architecture decision with profound implications for reliability, consistency, and operational complexity. We'll cover when to cache, what to cache, and perhaps most importantly, when NOT to cache.

---

## Quick Visual: Caching Strategy at a Glance

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CACHING: THE STAFF ENGINEER VIEW                         │
│                                                                             │
│   WRONG Framing: "Add cache to make things faster"                          │
│   RIGHT Framing: "Design cache strategy for reliability at scale"           │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Before adding ANY cache, answer:                                   │   │
│   │                                                                     │   │
│   │  1. What happens when this cache is empty? (Cold start)             │   │
│   │  2. What happens when this cache is down? (Failure mode)            │   │
│   │  3. How stale can this data be? (Consistency requirement)           │   │
│   │  4. How do we invalidate? (Correctness strategy)                    │   │
│   │  5. Is the operational cost worth it? (Complexity budget)           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   If you can't answer all five, you're not ready to add caching.            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## L5 vs L6 Caching Decisions

| Scenario | L5 Approach | L6 Approach |
|----------|-------------|-------------|
| **Slow database query** | "Add Redis cache, 5-minute TTL" | "Why is it slow? Fix the query first. Cache hides problems. If we must cache, what's our invalidation strategy?" |
| **High traffic endpoint** | "Cache everything in Redis" | "What's the cache hit rate? 50% hit rate means we're still hitting the DB for half the traffic. What's our consistency model?" |
| **API responses** | "Cache in Redis, invalidate on write" | "Who writes? How many writers? Distributed invalidation is hard. Consider CDN for public content, Redis for personalized." |
| **Session data** | "Redis with 24-hour TTL" | "What happens if Redis goes down? Sticky sessions as backup? Can we tolerate session loss? What's our persistence strategy?" |
| **Feed content** | "Cache the entire feed" | "Cache post content, not the feed. Feeds change per-user, post content is shared. Different TTLs for different tiers." |
| **EU user data** | "Cache in Redis like everything else" | "Where does this cache live? EU data must stay in EU. Regional cache pools only; no global CDN for PII." |
| **Cost reduction request** | "Cache more to reduce DB load" | "What's our hit rate today? Below 70%, caching adds cost without proportional benefit. Fix the query first." |

**Key Difference**: L6 engineers think about failure modes, consistency requirements, operational complexity, and compliance constraints before adding caching.

### Staff vs Senior: The Caching Judgment Gap

| Dimension | Senior (L5) | Staff (L6) |
|-----------|-------------|------------|
| **Decision trigger** | "It's slow, add cache" | "What's the first bottleneck? Fix that first. Cache when protection or cost justify it." |
| **Blast radius** | Thinks in terms of "cache down = slower" | Models: cache down → N× backend load → cascading failure. Designs containment. |
| **Partial failure** | Treats cache as up or down | Reasons about: one shard down, elevated latency, eviction storms, hot keys. |
| **Time horizon** | "Works at current scale" | "What breaks at 10×? What's the first bottleneck by year 2?" |
| **Org impact** | Optimizes own service | Considers shared cache clusters, cross-team standards, platform ownership. |

**L6 signal**: Staff Engineers articulate *why* they are not caching something as often as *why* they are.

---

# Part 1: Why Caching Exists (Staff Perspective)

## The Three Reasons to Cache

Most engineers think caching is about speed. It's actually about three things, and speed is often the least important.

### 1. Protection: Caching as a Shield

Your database can handle 10,000 queries per second. Your traffic spikes to 100,000 queries per second during a product launch. Without caching, your database melts, and everyone has a bad day.

**Caching protects your backend from traffic it can't handle.**

This is the most important reason to cache, and it has nothing to do with latency. A 95% cache hit rate means your database only sees 5,000 queries per second during that spike—well within capacity.

**Real-world example**: A social media company's database could handle their normal load of 50,000 reads/second. During a major news event, traffic spiked to 500,000 reads/second. Their Redis cache absorbed 95% of reads, and the database handled the remaining 25,000. Without caching, they would have had a 6-hour outage.

### 2. Cost: Caching as Economics

Database capacity is expensive. A PostgreSQL RDS instance that handles 50,000 queries/second might cost $10,000/month. A Redis cluster that handles the same read load costs $500/month.

**Caching shifts load from expensive resources to cheap ones.**

The math is compelling:
- 1M reads/day from PostgreSQL: $X in database costs
- Same reads from Redis: $X/20 in cache costs
- Same reads from CDN: $X/100 in edge costs

For read-heavy workloads (and most workloads are read-heavy), caching is primarily a cost optimization.

### 3. Latency: Caching as Speed

Yes, caching makes things faster. But this is often the least important benefit.

- Redis: ~1ms latency
- PostgreSQL (indexed query): ~5-10ms latency
- PostgreSQL (complex query): ~50-200ms latency

The difference between 1ms and 10ms is rarely user-perceptible. The difference between your system staying up under load and crashing—that's perceptible.

**Staff Insight**: If you're adding caching primarily for latency, question whether you need it. If you're adding caching for protection or cost, you probably do need it.

### Cache Invariants: What Must Never Happen

Staff Engineers define invariants—conditions that must hold regardless of cache state. Violations indicate design bugs.

| Invariant | Violation Example | Mitigation |
|-----------|-------------------|------------|
| **No user A sees user B's data** | CDN caches response keyed only by path; user param changes content | Include all request dimensions that affect response in cache key, or do not cache |
| **Stale permissions never grant access** | Cached permission with 1-hour TTL; user revoked 5 minutes ago | Fail closed: short TTL, sync invalidation, or do not cache |
| **Cache failure does not cause data loss** | Write-through cache; cache down during write | Origin is source of truth; cache is performance layer only |
| **Eviction does not corrupt semantics** | LRU evicts "user logged out" marker; next request treats user as logged in | Negative cache with distinct marker; short TTL; or avoid caching auth state |

**One-liner**: "Cache is a performance optimization, never a correctness requirement."

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    WHY WE CACHE: PRIORITY ORDER                             │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. PROTECTION (Most Important)                                     │   │
│   │     Cache absorbs traffic spikes that would overwhelm backend       │   │
│   │     Cache enables graceful degradation during backend failures      │   │
│   │     Cache provides breathing room during incidents                  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  2. COST (Often Overlooked)                                         │   │
│   │     Cache is 10-100x cheaper than database for reads                │   │
│   │     CDN is 100-1000x cheaper than origin for static content         │   │
│   │     At scale, caching is a significant line item in cloud bills     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  3. LATENCY (Often Overemphasized)                                  │   │
│   │     Important for user experience at the margins                    │   │
│   │     But 5ms vs 50ms rarely matters as much as we think              │   │
│   │     Don't add caching complexity just for latency                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Cache as a Reliability Layer

This is the insight that separates Staff Engineers from Senior Engineers: **a well-designed cache is a reliability feature, not just a performance feature**.

### Graceful Degradation with Cache

When your database goes down, what happens?

**Without cache strategy**:
- Database fails → All reads fail → Users see errors → Outage

**With cache as reliability layer**:
- Database fails → Cache still serves reads → Users see slightly stale data → Degraded but working
- Stale data is often better than no data

**Example implementation**:
```
FUNCTION get_user_profile(user_id):
    // Try cache first
    cached = cache.GET("user:" + user_id)
    IF cached EXISTS:
        RETURN deserialize(cached)
    
    // Try database
    TRY:
        profile = database.query_user(user_id)
        // Cache for future requests (with TTL)
        cache.SET("user:" + user_id, serialize(profile), TTL=3600)
        RETURN profile
    CATCH DatabaseError:
        // Database is down - try stale cache
        stale = cache.GET("user:" + user_id + ":stale")
        IF stale EXISTS:
            log.warning("Serving stale data for user " + user_id)
            metrics.increment("cache.stale_served")
            RETURN deserialize(stale)
        
        // No stale cache available - this user will see an error
        THROW ServiceUnavailableError("Unable to load profile")
```

### The Stale-While-Revalidate Pattern

For many use cases, stale data is acceptable. The stale-while-revalidate pattern serves cached data immediately while refreshing in the background:

```
FUNCTION get_with_stale_while_revalidate(key, fetch_function, ttl, stale_ttl):
    // Stale-While-Revalidate pattern
    // ttl: How long data is considered fresh
    // stale_ttl: How long stale data can be served while revalidating
    
    cached = cache.GET(key)
    
    IF cached EXISTS:
        data, timestamp = deserialize_with_timestamp(cached)
        age = current_time() - timestamp
        
        IF age < ttl:
            // Fresh - serve immediately
            RETURN data
        ELSE IF age < stale_ttl:
            // Stale but usable - serve and refresh in background
            SPAWN_ASYNC refresh_cache(key, fetch_function, ttl, stale_ttl)
            RETURN data
        // Too stale - fall through to refresh
    
    // No cache or too stale - fetch fresh
    fresh_data = fetch_function()
    cache_with_timestamp(key, fresh_data, stale_ttl)
    RETURN fresh_data

FUNCTION refresh_cache(key, fetch_function, ttl, stale_ttl):
    // Background refresh - doesn't block the request
    TRY:
        fresh_data = fetch_function()
        cache_with_timestamp(key, fresh_data, stale_ttl)
    CATCH Exception AS e:
        log.error("Background refresh failed for " + key + ": " + e)
        // Don't propagate - stale data is already being served
```

**Why this pattern matters**:
- Users always get fast responses (cached data)
- Data stays reasonably fresh (background refresh)
- Backend failures don't immediately impact users
- No thundering herd (only one refresh per stale item)

---

## The Cache Complexity Budget

Every cache you add is complexity you must manage:

**Operational costs**:
- Another system to monitor
- Another system that can fail
- Another on-call page at 3 AM

**Correctness costs**:
- Cache invalidation bugs
- Stale data serving when freshness matters
- Debugging "why is this user seeing old data?"

**Development costs**:
- Invalidation logic in every write path
- Cache warming strategies
- Testing cache behavior

**Staff Insight**: Before adding a cache, ask: "Is the benefit worth the complexity?" Sometimes the answer is no. A faster database query, more read replicas, or accepting higher latency is simpler than adding a cache layer.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CACHE COMPLEXITY CHECKLIST                               │
│                                                                             │
│   Add a cache only if you've considered:                                    │
│                                                                             │
│   Operational:                                                              │
│   ☐ How do we monitor cache hit rate?                                       │
│   ☐ What alerts do we need?                                                 │
│   ☐ What's the runbook if cache fails?                                      │
│   ☐ Who pages when cache is down at 3 AM?                                   │
│                                                                             │
│   Correctness:                                                              │
│   ☐ How do we invalidate on writes?                                         │
│   ☐ What's our consistency model? (eventual, read-your-writes, etc.)        │
│   ☐ How stale is acceptable?                                                │
│   ☐ How do we debug "user sees old data" reports?                           │
│                                                                             │
│   Performance:                                                              │
│   ☐ What's expected hit rate? (<80% is often not worth it)                  │
│   ☐ What happens on cold start?                                             │
│   ☐ What happens on cache failure?                                          │
│   ☐ Have we prevented thundering herd?                                      │
│                                                                             │
│   If you can't answer these, you're not ready to add the cache.             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 2: Application-Level Caching (Redis / Memcached)

## Choosing Between Redis and Memcached

Both are in-memory key-value stores, but they serve different needs:

### Redis

**Strengths**:
- Rich data structures (lists, sets, sorted sets, hashes)
- Persistence options (RDB snapshots, AOF log)
- Pub/sub for cache invalidation
- Lua scripting for atomic operations
- Cluster mode for horizontal scaling

**Use when**:
- You need data structures beyond key-value
- You need persistence (session data, rate limits)
- You need pub/sub for invalidation
- You're building features on top of cache (leaderboards, queues)

### Memcached

**Strengths**:
- Simpler (just key-value, nothing else)
- Multi-threaded (better per-node throughput for simple operations)
- Predictable memory usage (slab allocator)
- Lower memory overhead per key

**Use when**:
- You only need simple key-value caching
- You want maximum simplicity
- You have very high throughput needs
- You don't need persistence

**Staff recommendation**: Default to Redis unless you have a specific reason for Memcached. Redis's additional features rarely hurt and often help. Memcached's simplicity advantage is marginal.

---

## What to Cache (And What NOT to Cache)

### Cache These

**1. Computed results that are expensive to recalculate**
```
// Good: Cache complex aggregation
@CACHE(ttl = 5 minutes)
FUNCTION get_user_stats(user_id):
    RETURN database.query(
        "SELECT COUNT(*) as post_count,
                SUM(likes) as total_likes,
                AVG(engagement_rate) as avg_engagement
         FROM posts
         WHERE user_id = ? AND created_at > NOW() - 30 DAYS",
        user_id
    )
```

**2. Data that's read far more than written**
- User profiles (read on every request, updated rarely)
- Product information (read millions of times, updated occasionally)
- Configuration data (read constantly, changed rarely)

**3. External API responses**
```
// Good: Cache third-party API responses
@CACHE(ttl = 1 hour)
FUNCTION get_weather(city):
    RETURN weather_api.get_current(city)  // Slow, rate-limited, costs money
```

**4. Rendered content**
- Pre-rendered HTML fragments
- Serialized API responses
- Computed recommendations

### DO NOT Cache These

**1. Data that changes frequently and must be fresh**
```
// Bad: Caching inventory counts with 5-minute TTL
// User could see "10 in stock", try to buy, and get "out of stock"
@CACHE(ttl = 5 minutes)  // DON'T DO THIS
FUNCTION get_inventory(product_id):
    RETURN database.get_inventory_count(product_id)
```

**2. User-specific data with low reuse**
```
// Bad: Cache hit rate will be near 0%
// Each user's cart is unique, rarely re-accessed quickly
@CACHE(ttl = 10 minutes)
FUNCTION get_cart(user_id):
    RETURN database.get_cart(user_id)
```

**3. Security-sensitive data**
```
// Dangerous: Permission cache can cause security bugs
// If permissions change, stale cache grants unauthorized access
@CACHE(ttl = 1 hour)  // DON'T DO THIS
FUNCTION get_user_permissions(user_id):
    RETURN database.get_permissions(user_id)

// Better: Short TTL or synchronous invalidation
@CACHE(ttl = 30 seconds)  // 30 seconds max staleness
FUNCTION get_user_permissions(user_id):
    RETURN database.get_permissions(user_id)
```

**4. Data where stale reads cause business problems**
- Financial balances
- Order status
- Inventory for limited items

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CACHE SUITABILITY MATRIX                                 │
│                                                                             │
│                        Read Frequency                                       │
│                   LOW ─────────────────────── HIGH                          │
│                                                                             │
│           HIGH  ┌─────────────────┬─────────────────┐                       │
│    Staleness    │  DON'T CACHE    │   CACHE (short  │                       │
│    Tolerance    │  (not worth it) │   TTL, careful) │                       │
│                 ├─────────────────┼─────────────────┤                       │
│           LOW   │  DON'T CACHE    │   CACHE         │                       │
│                 │  (freshness     │   (big win!)    │                       │
│                 │   required)     │                 │                       │
│                 └─────────────────┴─────────────────┘                       │
│                                                                             │
│   Sweet spot: High read frequency + High staleness tolerance                │
│   Danger zone: High read frequency + Low staleness tolerance                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## TTL Trade-offs

TTL (Time-To-Live) is the most important parameter in your caching strategy. Choose it carefully.

### Short TTL (seconds to minutes)

**Pros**:
- Data stays relatively fresh
- Less risk from stale data
- Invalidation is less critical

**Cons**:
- Lower hit rate
- More database load
- Less protection during spikes

**Use for**:
- Data that changes frequently
- Data where some staleness is OK but not much
- Cases where invalidation is hard to implement correctly

### Long TTL (hours to days)

**Pros**:
- Higher hit rate
- Better database protection
- Lower costs

**Cons**:
- Data can become very stale
- Requires explicit invalidation
- Bugs in invalidation = long-lived bad data

**Use for**:
- Static or near-static content
- Cases where you have reliable invalidation
- Content where freshness doesn't matter much

### TTL Selection Framework

```
FUNCTION choose_ttl(data_type):
    // Framework for choosing TTL
    
    // How often does this data change?
    change_frequency = estimate_change_frequency(data_type)
    
    // How bad is it if users see stale data?
    staleness_cost = estimate_staleness_cost(data_type)
    
    // Can we reliably invalidate on change?
    invalidation_reliability = assess_invalidation(data_type)
    
    IF staleness_cost == "critical":
        // Financial, security, inventory
        RETURN 0  // Don't cache, or cache with immediate invalidation
    
    IF invalidation_reliability == "high":
        // We can invalidate reliably
        // Use longer TTL as safety net, rely on invalidation
        RETURN 24 hours
    
    IF change_frequency == "high":
        RETURN 1 minute
    ELSE IF change_frequency == "medium":
        RETURN 15 minutes
    ELSE:
        RETURN 1 hour
```

### Real-World TTL Examples

| Data Type | TTL | Reasoning |
|-----------|-----|-----------|
| User profile (name, bio) | 1 hour | Changes rarely, not critical if stale |
| User session | 24 hours | Security-relevant, but we invalidate on logout |
| Product price | 5 minutes | Changes occasionally, stale price is bad |
| Product description | 1 hour | Changes rarely, staleness acceptable |
| Feed post content | 4 hours | Immutable after creation |
| Like/comment counts | 30 seconds | Changes constantly, slight staleness OK |
| Weather data | 15 minutes | External API, not real-time anyway |
| Feature flags | 1 minute | Changes rarely, want fast propagation |

---

## Cache Invalidation Strategies

"There are only two hard things in Computer Science: cache invalidation and naming things." — Phil Karlton

### Strategy 1: Time-Based Expiration (TTL)

The simplest strategy: cache expires after a fixed time.

```
// Set with TTL
cache.SET("user:123", serialize(user), TTL = 1 hour)
```

**Pros**: Simple, no invalidation logic needed, self-healing
**Cons**: Data can be stale for up to TTL duration

**Use when**: Staleness is acceptable, invalidation is complex

### Strategy 2: Write-Through

Every write updates both database and cache.

```
FUNCTION update_user(user_id, data):
    // Update database
    database.update_user(user_id, data)
    
    // Update cache immediately
    user = database.get_user(user_id)
    cache.SET("user:" + user_id, serialize(user), TTL = 1 hour)
```

**Pros**: Cache is always fresh (for this writer)
**Cons**: Complexity in every write path, distributed systems challenges

**Use when**: Freshness is critical, write paths are well-defined

### Strategy 3: Write-Behind (Write-Back)

Writes go to cache first, database is updated asynchronously.

```
FUNCTION update_user(user_id, data):
    // Update cache immediately
    cache.SET("user:" + user_id, serialize(data), TTL = 1 hour)
    
    // Queue database update
    queue.publish("db_writes", {
        table: "users",
        id: user_id,
        data: data
    })
```

**Pros**: Fast writes, can batch database updates
**Cons**: Data loss risk if cache fails before DB write, complexity

**Use when**: Write latency is critical, can tolerate some data loss risk

### Strategy 4: Cache-Aside (Lazy Loading)

Application manages cache explicitly.

```
FUNCTION get_user(user_id):
    // Try cache
    cached = cache.GET("user:" + user_id)
    IF cached EXISTS:
        RETURN deserialize(cached)
    
    // Miss - load from database
    user = database.get_user(user_id)
    
    // Populate cache
    cache.SET("user:" + user_id, serialize(user), TTL = 1 hour)
    RETURN user

FUNCTION update_user(user_id, data):
    // Update database
    database.update_user(user_id, data)
    
    // Invalidate cache (don't update - let next read populate)
    cache.DELETE("user:" + user_id)
```

**Pros**: Simple, resilient to cache failures, no write-path complexity
**Cons**: Cache miss on first read after write, potential race conditions

**Use when**: Default choice for most scenarios

### Strategy 5: Event-Driven Invalidation

Changes published as events, cache subscribers invalidate.

```
// Publisher (write path)
FUNCTION update_user(user_id, data):
    database.update_user(user_id, data)
    event_bus.publish("user_updated", {user_id: user_id})

// Subscriber (cache service)
FUNCTION handle_user_updated(event):
    cache.DELETE("user:" + event.user_id)
```

**Pros**: Decoupled, works across services, scalable
**Cons**: Eventual consistency, event delivery guarantees needed

**Use when**: Microservices architecture, multiple caches to invalidate

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    INVALIDATION STRATEGY SELECTION                          │
│                                                                             │
│   Question                                 Recommended Strategy             │
│   ──────────────────────────────────────────────────────────────────────    │
│   "Staleness is fine, keep it simple"     TTL only                          │
│   "Must be fresh for the writer"          Write-through                     │
│   "Write speed is critical"               Write-behind (with care)          │
│   "Simple is better, eventual OK"         Cache-aside with delete           │
│   "Many services, decoupled"              Event-driven                      │
│   "Must be fresh for everyone"            Write-through + short TTL backup  │
│                                                                             │
│   Golden rule: Start with cache-aside + TTL.                                │
│                Add complexity only when needed.                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Consistency vs Freshness

Caching inherently trades consistency for performance. Understand what you're trading.

### Consistency Models for Caching

**Strong consistency**: Readers always see the latest write.
- Requires synchronous cache invalidation
- Essentially defeats the purpose of caching
- Rarely needed, rarely achievable with caching

**Read-your-writes consistency**: You see your own writes immediately.
- After you update, you see the update
- Others may see stale data briefly
- Achievable with write-through for the writing user

**Eventual consistency**: Everyone eventually sees all writes.
- After TTL expires, cache refreshes
- Standard for most caching scenarios
- Simple to implement, good enough for most cases

### Implementing Read-Your-Writes

For many applications, users must see their own changes. Here's how:

```
FUNCTION get_user(user_id, requesting_user_id):
    // If user is viewing their own profile, bypass cache
    IF user_id == requesting_user_id:
        RETURN database.get_user(user_id)
    
    // For other users, cache is fine
    cached = cache.GET("user:" + user_id)
    IF cached EXISTS:
        RETURN deserialize(cached)
    
    user = database.get_user(user_id)
    cache.SET("user:" + user_id, serialize(user), TTL = 1 hour)
    RETURN user
```

Or with version tracking:

```
FUNCTION get_user(user_id, min_version = NULL):
    cached = cache.GET("user:" + user_id)
    IF cached EXISTS:
        data = deserialize(cached)
        IF min_version IS NULL OR data.version >= min_version:
            RETURN data
        // Cached version is too old for this reader
    
    RETURN database.get_user(user_id)

FUNCTION update_user(user_id, data):
    new_version = database.update_user_returning_version(user_id, data)
    // Return version to client, client includes in subsequent reads
    RETURN {version: new_version}
```

---

# Part 3: CDN & Edge Caching

## What is Edge Caching?

Edge caching places content physically close to users. Instead of every request traveling to your origin servers (potentially across the globe), requests are served from the nearest "edge" server.

**The numbers matter**:
- US East Coast to US West Coast: ~80ms round-trip
- US to Europe: ~120ms
- US to Asia: ~200ms
- User to nearest edge (CDN): ~10-30ms

For a web page making 50 requests, the difference between 200ms and 20ms per request is 9 seconds of total load time reduction.

### CDN Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CDN ARCHITECTURE                                         │
│                                                                             │
│                         [Origin Server]                                     │
│                         San Francisco                                       │
│                               │                                             │
│                               │                                             │
│              ┌────────────────┼────────────────┐                            │
│              │                │                │                            │
│              ▼                ▼                ▼                            │
│       [Edge: NYC]      [Edge: London]    [Edge: Tokyo]                      │
│           10ms             15ms             20ms                            │
│              │                │                │                            │
│              ▼                ▼                ▼                            │
│        [US East Users]  [EU Users]     [APAC Users]                         │
│                                                                             │
│   Without CDN: All users hit origin (80-200ms)                              │
│   With CDN: Users hit nearest edge (10-30ms)                                │
│             Origin only hit on cache miss                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## What Belongs at the Edge

### Perfect for CDN

**1. Static assets**: Images, CSS, JavaScript, fonts
- Never change (versioned filenames)
- Same for all users
- High volume, easy to cache

**2. Public API responses that are the same for everyone**
```
GET /api/countries          → Cache for 24 hours
GET /api/products/popular   → Cache for 15 minutes
GET /api/config/public      → Cache for 1 hour
```

**3. Rendered HTML for public pages**
- Homepage
- Product pages (for logged-out users)
- Blog posts, documentation

### NOT for CDN

**1. Personalized content**
```
GET /api/me                  → User-specific, don't cache at edge
GET /api/feed                → Personalized, don't cache at edge
GET /api/recommendations     → User-specific, don't cache at edge
```

**2. Authenticated API endpoints**
```
POST /api/orders            → Write operations, never cache
GET /api/orders/my          → User-specific, needs origin
```

**3. Highly dynamic data**
```
GET /api/stock-price/GOOG   → Changes every second
GET /api/scores/live        → Real-time updates
```

**4. Sensitive data**
```
GET /api/user/payment-methods  → Security-sensitive, never cache at edge
```

### Hybrid Approach: Edge + Personalization

For content that's mostly public but needs personalization:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    EDGE-SIDE INCLUDES (ESI) PATTERN                         │
│                                                                             │
│   Problem: Product page is 95% public, 5% personalized (user's cart)        │
│                                                                             │
│   Solution: Edge-Side Includes                                              │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  CDN-cached HTML:                                                   │   │
│   │  <html>                                                             │   │
│   │    <body>                                                           │   │
│   │      <h1>Product: Widget</h1>                                       │   │
│   │      <p>Price: $29.99</p>                                           │   │
│   │      <!-- ESI include for personalized content -->                  │   │
│   │      <esi:include src="/api/user/cart-widget" />                    │   │
│   │    </body>                                                          │   │
│   │  </html>                                                            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Flow:                                                                     │
│   1. CDN serves cached HTML (fast)                                          │
│   2. CDN makes small request to origin for ESI fragment                     │
│   3. CDN assembles final page                                               │
│   4. User gets personalized page with edge speed                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Static vs Dynamic Content Caching

### Static Content Strategy

Static content has immutable semantics—the content at a given URL never changes. This enables aggressive caching.

**Best practice: Content-addressable URLs**
```
/static/app.a1b2c3d4.js    ← Hash in filename
/static/styles.e5f6g7h8.css
/images/logo.v2.png
```

With content-addressed URLs:
- Cache for 1 year (browser and CDN)
- Never invalidate (new content = new URL)
- Deploying new code automatically busts cache

**CDN headers for static content**:
```
Cache-Control: public, max-age=31536000, immutable
```

### Dynamic Content Strategy

Dynamic content changes, so caching is more nuanced.

**Strategy 1: Short TTL**
```
Cache-Control: public, max-age=60, s-maxage=300
```
- Browser caches for 60 seconds
- CDN caches for 5 minutes
- Good for content that updates regularly

**Strategy 2: Stale-While-Revalidate**
```
Cache-Control: public, max-age=60, stale-while-revalidate=300
```
- Serve cached content immediately
- Revalidate in background if older than 60s
- Users get fast responses, content stays fresh

**Strategy 3: Surrogate Keys (Cache Tags)**
```
# Response header
Surrogate-Key: product-123 category-electronics

# Purge all pages containing product 123
cdn.purge_by_tag("product-123")
```

This enables instant invalidation without knowing all affected URLs.

---

## Cache Poisoning and Correctness Risks

Edge caching introduces risks that application caching doesn't have.

### Cache Poisoning

**The attack**: Attacker sends a request that causes the CDN to cache malicious content.

**Example**:
```http
GET /api/search?q=shoes HTTP/1.1
Host: example.com
X-Forwarded-Host: evil.com
```

If your app uses `X-Forwarded-Host` to generate links, and the CDN caches the response, all users might see links to `evil.com`.

**Prevention**:
- Normalize all cache keys
- Validate and sanitize headers that affect response
- Use `Vary` header correctly
- Audit what headers influence response content

### Caching Authenticated Content

**The bug**: Accidentally caching a response meant for one user, serving it to another.

**Example**:
```
// Dangerous: Personal data cached publicly
ENDPOINT GET /api/me:
    user = get_current_user()
    RETURN json(user.to_dict())
// Response cached at CDN → next user sees previous user's data!
```

**Prevention**:
```
ENDPOINT GET /api/me:
    user = get_current_user()
    response = json(user.to_dict())
    response.headers["Cache-Control"] = "private, no-store"
    RETURN response
```

**Rules**:
- Always set `Cache-Control: private, no-store` for authenticated endpoints
- Audit CDN cache hits for authenticated paths
- Consider separate domains for cacheable vs non-cacheable content

### Vary Header Misuse

The `Vary` header tells caches what request headers affect the response.

**Correct**:
```http
Vary: Accept-Encoding
```
Different cache entry for gzip vs non-gzip clients.

**Incorrect**:
```http
Vary: Cookie
```
Effectively disables caching (every user has different cookies).

**Danger**:
```http
Vary: User-Agent
```
Creates thousands of cache entries (one per browser version). Cache becomes useless.

---

# Part 4: Cache Failure Modes

Staff Engineers must understand how caches fail, not just how they work.

## Cache Stampede

**What it is**: When a popular cached item expires, many requests simultaneously try to regenerate it, overwhelming the backend.

**Example scenario**:
- 10,000 requests/second for homepage data
- Cache TTL: 60 seconds
- At T=60, cache expires
- All 10,000 requests hit the database simultaneously
- Database can only handle 1,000 requests/second
- Database melts

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CACHE STAMPEDE                                           │
│                                                                             │
│   Normal operation:                                                         │
│   [10,000 req/s] ──→ [Cache] ──(1% miss)──→ [Database: 100 req/s] ✓         │
│                                                                             │
│   Cache expires:                                                            │
│   [10,000 req/s] ──→ [Cache MISS] ──(100% miss)──→ [Database: 10K req/s] ✗  │
│                                                          │                  │
│                                                          ▼                  │
│                                                    [OVERLOAD]               │
│                                                          │                  │
│                                                          ▼                  │
│                                                    [Timeouts]               │
│                                                          │                  │
│                                                          ▼                  │
│                                                    [OUTAGE]                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Prevention: Lock and Single-Fetch

```
FUNCTION get_with_stampede_prevention(key, fetch_function, ttl):
    // Try cache first
    cached = cache.GET(key)
    IF cached EXISTS:
        RETURN deserialize(cached)
    
    // Cache miss - try to acquire lock
    lock_key = "lock:" + key
    acquired = cache.SET(lock_key, "1", IF_NOT_EXISTS=true, TTL=30 seconds)
    
    IF acquired:
        // We got the lock - fetch and cache
        TRY:
            data = fetch_function()
            cache.SET(key, serialize(data), TTL=ttl)
            RETURN data
        FINALLY:
            cache.DELETE(lock_key)
    ELSE:
        // Someone else is fetching - wait and retry
        FOR i = 1 TO 10:  // Retry up to 10 times
            SLEEP(100 milliseconds)
            cached = cache.GET(key)
            IF cached EXISTS:
                RETURN deserialize(cached)
        
        // Still no cache - fall back to database (rare)
        RETURN fetch_function()
```

### Cascading Failure Timeline: Cache Stampede in Production

**Staff Engineer Insight**: Understanding the exact failure propagation timeline is critical for incident response and prevention. Here's a concrete example showing how a cache stampede cascades through the system:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│         CACHE STAMPEDE: CASCADING FAILURE TIMELINE (Concrete Example)       │
│                                                                             │
│   Scenario: News feed homepage cache expires during peak traffic            │
│   System: 100K req/s normal, 95% cache hit rate, DB capacity: 10K req/s     │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  TRIGGER PHASE                                                      │   │
│   │  ────────────────────────────────────────────────────────────────   │   │
│   │  T+0s:    Popular homepage cache key expires (TTL=60s reached)      │   │
│   │  T+0.1s:  First 1,000 requests hit cache → MISS                     │   │
│   │  T+0.2s:  All 1,000 requests simultaneously query database          │   │
│   │  T+0.3s:  Database connection pool saturated (100 connections)      │   │
│   │                                                                     │   │
│   │  PROPAGATION PHASE                                                  │   │
│   │  ────────────────────────────────────────────────────────────────   │   │
│   │  T+1s:    Database query latency increases: 10ms → 200ms            │   │
│   │  T+2s:    Application servers: request queue depth = 500            │   │
│   │  T+3s:    Database CPU: 40% → 95% (thrashing)                       │   │
│   │  T+5s:    Database query timeout: 200ms → 5s (timeout threshold)    │   │
│   │  T+7s:    Application threads blocked waiting for DB: 80%           │   │
│   │  T+10s:   New cache writes fail (DB too slow to fetch data)         │   │
│   │  T+12s:   Cache remains empty, 100% miss rate sustained             │   │
│   │                                                                     │   │
│   │  USER-VISIBLE IMPACT PHASE                                          │   │
│   │  ────────────────────────────────────────────────────────────────   │   │
│   │  T+15s:   User-facing latency: p50=500ms, p99=5s                    │   │
│   │  T+20s:   Error rate: 0.1% → 15% (timeouts)                         │   │
│   │  T+25s:   Users see "Something went wrong" errors                   │   │
│   │  T+30s:   Dependent services (recommendations, ads) start timing out│   │
│   │  T+35s:   Load balancer health checks fail (app servers overloaded) │   │
│   │  T+40s:   Traffic shifts to healthy regions → overloads them too    │   │
│   │                                                                     │   │
│   │  CONTAINMENT PHASE                                                  │   │
│   │  ────────────────────────────────────────────────────────────────   │   │
│   │  T+45s:   On-call engineer receives alert: "DB p99 latency > 2s"    │   │
│   │  T+50s:   Circuit breaker opens for DB (stops new requests)         │   │
│   │  T+55s:   Rate limiter activated: 5K req/s max to DB                │   │
│   │  T+60s:   Single-fetch lock implemented: only 1 DB query per key    │   │
│   │  T+90s:   First successful cache write (lock winner)                │   │
│   │  T+120s:  Cache hit rate: 0% → 30% (recovering)                     │   │
│   │  T+180s:  Cache hit rate: 30% → 85% (near normal)                   │   │
│   │  T+300s:  System fully recovered, cache hit rate: 95%               │   │
│   │                                                                     │   │
│   │  ROOT CAUSE ANALYSIS                                                │   │
│   │  ────────────────────────────────────────────────────────────────   │   │
│   │  Why did this happen?                                               │   │
│   │  • No lock mechanism for cache misses                               │   │
│   │  • Synchronized TTL expiration (all keys expire at once)            │   │
│   │  • No circuit breaker on database path                              │   │
│   │  • Database sized for normal load, not stampede load                │   │
│   │                                                                     │   │
│   │  PREVENTION (Applied After Incident)                                │   │
│   │  ────────────────────────────────────────────────────────────────   │   │
│   │  • Implemented single-fetch locks (see code above)                  │   │
│   │  • Added jitter to TTL: TTL ± 10% random                            │   │
│   │  • Circuit breaker on DB with 50% failure threshold                 │   │
│   │  • Database capacity increased 2× (headroom for stampedes)          │   │
│   │  • Cache warming before traffic ramp                                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key Takeaway**: The failure propagates from cache → database → application servers → user experience → dependent services. Each phase has specific symptoms and containment strategies. Staff Engineers design systems to detect and contain failures at each phase, not just prevent the initial trigger.

### Prevention: Probabilistic Early Recomputation

Refresh cache before it expires, with some randomness to prevent synchronized expiration:

```
FUNCTION get_with_early_recompute(key, fetch_function, ttl):
    cached = cache.GET(key)
    IF cached EXISTS:
        data, expiry_time = deserialize_with_expiry(cached)
        time_until_expiry = expiry_time - current_time()
        
        // Probabilistically refresh before expiry
        // Probability increases as expiry approaches
        IF random() < exp(-time_until_expiry / (ttl * 0.1)):
            // Refresh in background
            SPAWN_ASYNC refresh(key, fetch_function, ttl)
        
        RETURN data
    
    // Cache miss - normal fetch
    RETURN fetch_and_cache(key, fetch_function, ttl)
```

---

## Thundering Herd

Similar to stampede, but happens when cache is completely unavailable.

**What it is**: Cache goes down, all traffic immediately hits the backend.

**The math**:
- Cache normally handles 95% of traffic
- Traffic: 100,000 requests/second
- Cache handles: 95,000 requests/second
- Database handles: 5,000 requests/second
- Cache fails: Database suddenly sees 100,000 requests/second
- Database is sized for 10,000 requests/second (with headroom)
- Result: 10× overload, immediate failure

### Prevention: Circuit Breaker

```
CLASS CircuitBreaker:
    CONSTRUCTOR(failure_threshold = 5, timeout = 30):
        this.failures = 0
        this.threshold = failure_threshold
        this.timeout = timeout
        this.state = "closed"  // closed = normal, open = failing
        this.last_failure = 0
    
    FUNCTION call(function):
        IF this.state == "open":
            IF current_time() - this.last_failure > this.timeout:
                this.state = "half-open"  // Try one request
            ELSE:
                THROW CircuitOpenError("Service unavailable")
        
        TRY:
            result = function()
            IF this.state == "half-open":
                this.state = "closed"
                this.failures = 0
            RETURN result
        CATCH Exception AS e:
            this.failures = this.failures + 1
            this.last_failure = current_time()
            IF this.failures >= this.threshold:
                this.state = "open"
            THROW e

// Usage
db_breaker = NEW CircuitBreaker(failure_threshold = 10, timeout = 60)

FUNCTION get_data(key):
    // Try cache
    TRY:
        cached = cache.GET(key)
        IF cached EXISTS:
            RETURN deserialize(cached)
    CATCH CacheError:
        PASS  // Cache failed, try database
    
    // Cache miss or failure - try database with circuit breaker
    TRY:
        RETURN db_breaker.call(() => database.get(key))
    CATCH CircuitOpenError:
        // Database is overloaded - return error or stale data
        THROW ServiceUnavailableError("Please try again later")
```

### Prevention: Rate Limiting to Backend

```
// Limit concurrent requests to database
db_semaphore = NEW Semaphore(max_concurrent = 100)

FUNCTION get_with_backend_limit(key):
    cached = cache.GET(key)
    IF cached EXISTS:
        RETURN deserialize(cached)
    
    // Limit concurrent database access
    TRY:
        WITH TIMEOUT(5 seconds):
            ACQUIRE db_semaphore:
                RETURN fetch_from_db(key)
    CATCH TimeoutError:
        THROW ServiceUnavailableError("System overloaded")
```

---

## Hot Key: Single Key Overload

**Staff Engineer Insight**: Total cache failure and thundering herd are obvious. The **hot key** problem is subtler: one key (or a small set) receives disproportionate traffic, overloading a single shard while the rest of the cluster sits idle. This is a partial failure mode—most of the cache works, but one slice fails.

**What it is**: In a sharded cache cluster, keys are distributed by hash. A "hot key" is one that receives 10–100× more traffic than the average. That key lives on one shard. That shard becomes the bottleneck.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    HOT KEY: TRAFFIC vs KEY DISTRIBUTION                      │
│                                                                             │
│   Sharded cache (10 shards):                                                │
│   [Shard 0] [Shard 1] [Shard 2] ... [Shard 9]                               │
│       │         │         │              │                                  │
│   5K/s      40K/s      5K/s    ...    5K/s     ← Traffic per shard         │
│   ✓          ✗         ✓              ✓                                     │
│                                                                             │
│   product:12345 (Black Friday deal) hashes to Shard 1                        │
│   40% of all requests hit this one key → Shard 1 overloaded                 │
│   Other shards idle. Adding more shards doesn't fix it (same key, same shard)│
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Example scenario**:
- Redis Cluster with 10 shards, 100K ops/sec total
- Popular product "Black Friday Deal" cached at key `product:12345`
- 40% of all requests hit this one product → 40K ops/sec to one shard
- Shard capacity: 15K ops/sec
- Result: That shard's CPU at 100%, latency spiking from 1ms to 200ms

**Why it matters at L6**: Staff Engineers anticipate hot keys before they cause incidents. Viral content, celebrity profiles, and flash-sale products create natural hot keys. The fix is not "add more shards"—hashing distributes keys, not traffic. You need to reason about access patterns.

**Concrete prevention**:

```
// Hot key mitigation: Local read-through cache for ultra-hot keys
CLASS HotKeyAwareCache:
    CONSTANT HOT_THRESHOLD = 1000  // accesses per second
    
    CONSTRUCTOR(remote_cache, local_cache):
        this.remote = remote_cache
        this.local = local_cache
        this.access_counts = NEW CounterMap()
    
    FUNCTION get(key, fetch_function):
        // Track access frequency
        count = this.access_counts.increment(key)
        
        // If hot, serve from local cache first
        IF count > HOT_THRESHOLD:
            local_value = this.local.GET(key)
            IF local_value EXISTS:
                RETURN deserialize(local_value)
        
        // Remote cache
        remote_value = this.remote.GET(key)
        IF remote_value EXISTS:
            IF count > HOT_THRESHOLD:
                this.local.SET(key, remote_value, TTL = 30 seconds)
            RETURN deserialize(remote_value)
        
        // Miss - fetch and populate both
        data = fetch_function()
        this.remote.SET(key, serialize(data), TTL = 1 hour)
        IF count > HOT_THRESHOLD:
            this.local.SET(key, serialize(data), TTL = 30 seconds)
        RETURN data
```

**Trade-offs**:
- **Local cache**: Reduces load on hot key's shard, but adds inconsistency (local can be stale). Use only for data where brief staleness is acceptable.
- **Key splitting**: Store hot data under multiple keys (e.g., `product:12345:replica_0` through `product:12345:replica_9`), read from random replica. Spreads load across shards. Trade-off: 10× memory for that item, more complex invalidation.

**One-liner**: "Hashing distributes keys, not traffic. Hot keys overload one shard—design for them."

---

## Eviction Storms

**What it is**: When cache memory is full, Redis evicts keys (LRU, LFU, etc.). Under memory pressure, eviction happens continuously. If eviction rate exceeds the rate at which new data is written, you get an **eviction storm**: most requests become cache misses, database load spikes, and the system degrades.

**Why it matters at L6**: Eviction storms are a *partial* failure—the cache is "up" but ineffective. Senior engineers might see "cache hit rate dropped" and add memory. Staff Engineers ask: "Why did we hit memory limit? Is our working set larger than we thought? Are we caching the wrong things?"

**Propagation timeline**:
```
T+0:    Memory reaches maxmemory-policy threshold
T+1s:   Eviction begins; new writes trigger evictions
T+5s:   Eviction rate = 500/sec; hit rate drops from 90% to 70%
T+30s:  Working set churn; evictions evict hot data
T+60s:  Hit rate 50%; database load 2× normal
T+5m:   Cascading slowness; app threads block on DB
```

**Prevention**: Right-size memory, monitor eviction rate, tune eviction policy. Add alert when `eviction_rate > 100/sec` sustained. For critical data, use separate cache pool with `noeviction` (fail instead of evict) so critical keys are never evicted.

**One-liner**: "Eviction storms mean cache is up but useless. Monitor eviction rate; it's a leading indicator of capacity problems."

---

## Cold Start

**What it is**: Cache is empty (after restart, new deploy, or new cache cluster), and every request is a miss.

**Why it's dangerous**:
- Normal: 5% cache miss rate → 5K requests/second to database
- Cold start: 100% cache miss rate → 100K requests/second to database
- This is the same as thundering herd, but self-inflicted

### Prevention: Cache Warming

```
FUNCTION warm_cache():
    // Run before accepting traffic after deploy/restart
    
    // Get list of most frequently accessed keys
    hot_keys = analytics.get_top_keys(limit = 10000)
    
    // Warm cache in batches
    batch_size = 100
    FOR i = 0 TO LENGTH(hot_keys) STEP batch_size:
        batch = hot_keys[i : i + batch_size]
        PARALLEL FOR EACH key IN batch:
            warm_key(key)
        // Pace ourselves to not overwhelm database
        SLEEP(100 milliseconds)
    
    log.info("Warmed " + LENGTH(hot_keys) + " cache entries")

FUNCTION warm_key(key):
    TRY:
        data = database.get(key)
        cache.SET(key, serialize(data), TTL = 1 hour)
    CATCH Exception AS e:
        log.warning("Failed to warm key " + key + ": " + e)
```

### Prevention: Gradual Traffic Shift

Don't send all traffic to a cold cache. Ramp up gradually:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    GRADUAL TRAFFIC SHIFT                                    │
│                                                                             │
│   Old cache cluster ──────────────────────────── 100% traffic               │
│                                                                             │
│   Deploy new cluster with cold cache                                        │
│                                                                             │
│   T+0:  Old: 100%  New: 0%    (new cluster warming)                         │
│   T+5:  Old: 90%   New: 10%   (observe hit rates)                           │
│   T+10: Old: 70%   New: 30%   (cache warming)                               │
│   T+15: Old: 50%   New: 50%   (cache nearly warm)                           │
│   T+20: Old: 20%   New: 80%   (commit to new)                               │
│   T+25: Old: 0%    New: 100%  (decommission old)                            │
│                                                                             │
│   Key: Monitor backend load at each step. Roll back if overloaded.          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Stale Data Propagation

**What it is**: Bad data enters the cache and persists, causing widespread incorrect behavior.

**Example scenario**:
1. Bug in code writes corrupted user data to database
2. Corrupted data is cached (TTL: 24 hours)
3. Bug is fixed, database is corrected
4. Cache still serves corrupted data for up to 24 hours
5. Thousands of users affected until cache expires

### Prevention: Versioned Cache Keys

```
// Include version in cache key
CACHE_VERSION = "v3"  // Increment when data format changes

FUNCTION cache_key(entity_type, entity_id):
    RETURN CACHE_VERSION + ":" + entity_type + ":" + entity_id

// Deploy new version → all old keys are effectively invalidated
// No explicit purge needed
```

### Prevention: Emergency Purge Capability

```
FUNCTION emergency_purge_user(user_id):
    // Emergency purge for incident response
    keys = [
        "user:" + user_id,
        "user:" + user_id + ":profile",
        "user:" + user_id + ":settings",
        "user:" + user_id + ":permissions"
    ]
    cache.DELETE(keys)
    
    // Also purge from CDN if applicable
    cdn.purge_by_tag("user-" + user_id)
    
    log.info("Emergency purge for user " + user_id)
    metrics.increment("cache.emergency_purge")

// Build a UI or CLI for on-call to trigger this
```

### Prevention: Poison Pill Detection

```
FUNCTION get_user(user_id):
    cached = cache.GET("user:" + user_id)
    IF cached EXISTS:
        user = deserialize(cached)
        
        // Sanity checks on cached data
        IF user.id IS EMPTY:
            log.error("Corrupted cache: missing id for user:" + user_id)
            cache.DELETE("user:" + user_id)
            // Fall through to database fetch
        ELSE IF user.email EXISTS AND "@" NOT IN user.email:
            log.error("Corrupted cache: invalid email for user:" + user_id)
            cache.DELETE("user:" + user_id)
            // Fall through to database fetch
        ELSE:
            RETURN user
    
    // Fetch from database
    RETURN fetch_and_cache_user(user_id)
```

---

# Part 5: Applied Examples

## Example 1: News Feed Reads

### Requirements

- 10 million daily active users
- Each user checks feed 20 times/day
- 200 million feed reads/day
- Feed must load in < 200ms (p99)
- Feed can be slightly stale (30 seconds acceptable)

### Caching Strategy

**What we're caching**: Pre-computed feed content, not raw posts.

**Why**: A feed read involves:
1. Get list of followed users
2. Get recent posts from each followed user
3. Rank and sort
4. Hydrate with author info, engagement counts

Without caching: 5-10 database queries, 100-500ms
With caching: 1 cache lookup, 5-10ms

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FEED CACHING ARCHITECTURE                                │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Layer 1: Per-User Feed Cache (Redis)                               │   │
│   │                                                                     │   │
│   │  Key: "feed:{user_id}:page:{page_num}"                              │   │
│   │  Value: List of post IDs with basic metadata                        │   │
│   │  TTL: 60 seconds                                                    │   │
│   │                                                                     │   │
│   │  • Personalized per user                                            │   │
│   │  • Short TTL for freshness                                          │   │
│   │  • Invalidated when user's feed changes significantly               │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Layer 2: Post Content Cache (Redis)                                │   │
│   │                                                                     │   │
│   │  Key: "post:{post_id}"                                              │   │
│   │  Value: Full post content (text, images, author info)               │   │
│   │  TTL: 4 hours                                                       │   │
│   │                                                                     │   │
│   │  • Shared across all users                                          │   │
│   │  • Post content is immutable after creation                         │   │
│   │  • Higher hit rate due to sharing                                   │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Layer 3: Engagement Counts Cache (Redis)                           │   │
│   │                                                                     │   │
│   │  Key: "engagement:{post_id}"                                        │   │
│   │  Value: {likes: 1234, comments: 56, shares: 78}                     │   │
│   │  TTL: 30 seconds                                                    │   │
│   │                                                                     │   │
│   │  • Changes frequently                                               │   │
│   │  • Short TTL acceptable (exact count not critical)                  │   │
│   │  • Write-behind pattern for updates                                 │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Feed Read Flow

```
FUNCTION get_feed(user_id, page = 0):
    // Layer 1: Try per-user feed cache
    feed_key = "feed:" + user_id + ":page:" + page
    cached_feed = cache.GET(feed_key)
    
    IF cached_feed EXISTS:
        post_ids = deserialize(cached_feed)
    ELSE:
        // Cache miss - compute feed
        post_ids = compute_feed(user_id, page)
        cache.SET(feed_key, serialize(post_ids), TTL = 60 seconds)
    
    // Layer 2 & 3: Hydrate posts with content and engagement
    posts = hydrate_posts(post_ids)
    
    RETURN FeedResponse(posts = posts)

FUNCTION hydrate_posts(post_ids):
    posts = []
    
    // Batch fetch from cache
    content_keys = ["post:" + pid FOR pid IN post_ids]
    engagement_keys = ["engagement:" + pid FOR pid IN post_ids]
    
    cached_content = cache.MGET(content_keys)
    cached_engagement = cache.MGET(engagement_keys)
    
    // Identify misses
    content_misses = []
    FOR i, (pid, content) IN ENUMERATE(ZIP(post_ids, cached_content)):
        IF content IS NULL:
            content_misses.APPEND((i, pid))
    
    // Fetch misses from database
    IF content_misses IS NOT EMPTY:
        db_posts = database.get_posts([pid FOR (_, pid) IN content_misses])
        FOR ((i, pid), post) IN ZIP(content_misses, db_posts):
            cached_content[i] = serialize(post)
            // Cache for next time
            cache.SET("post:" + pid, serialize(post), TTL = 4 hours)
    
    // Assemble response
    FOR (pid, content, engagement) IN ZIP(post_ids, cached_content, cached_engagement):
        post = deserialize(content)
        IF engagement EXISTS:
            post.engagement = deserialize(engagement)
        posts.APPEND(post)
    
    RETURN posts
```

### Failure Handling

**Redis unavailable**:
```
FUNCTION get_feed_with_fallback(user_id, page):
    TRY:
        RETURN get_feed(user_id, page)
    CATCH CacheError:
        log.warning("Cache unavailable, falling back to DB for " + user_id)
        // Rate limit database access
        ACQUIRE db_semaphore:
            RETURN compute_feed_from_db(user_id, page)
```

---

## Example 2: User Session Data

### Requirements

- Sessions created on login, destroyed on logout
- Session must be valid across all servers (stateless app servers)
- Session lookup on every authenticated request
- 5 million active sessions at any time
- Session data: user_id, permissions, preferences (~2KB)

### Why Redis (Not Cookies)

**Cookie-based sessions**:
- Client stores session data (signed/encrypted)
- No server-side storage needed
- But: Can't invalidate (user logs out, cookie still valid until expiry)
- And: Size limits (~4KB), bandwidth on every request

**Redis-based sessions**:
- Server stores session data
- Client stores only session ID
- Instant invalidation (delete key)
- Large session data possible
- But: Redis dependency, network hop

**Decision**: Redis for invalidation capability and flexibility.

### Session Caching Strategy

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SESSION DATA ARCHITECTURE                                │
│                                                                             │
│   Storage: Redis with persistence (AOF)                                     │
│   Why AOF: Session loss = users logged out = bad UX                         │
│                                                                             │
│   Key: "session:{session_id}"                                               │
│   Value: {                                                                  │
│     "user_id": "12345",                                                     │
│     "created_at": 1699999999,                                               │
│     "last_active": 1700000000,                                              │
│     "permissions": ["read", "write"],                                       │
│     "preferences": {...}                                                    │
│   }                                                                         │
│   TTL: 24 hours (sliding)                                                   │
│                                                                             │
│   Operations:                                                               │
│   • Login: SET with 24h TTL                                                 │
│   • Request: GET, then EXPIRE to extend TTL                                 │
│   • Logout: DELETE                                                          │
│   • Inactivity timeout: Redis TTL handles automatically                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Session Operations

```
CLASS SessionManager:
    CONSTRUCTOR(cache_client):
        this.cache = cache_client
        this.ttl = 24 hours
    
    FUNCTION create_session(user_id, permissions):
        session_id = generate_secure_random_token(32)
        session_data = {
            user_id: user_id,
            created_at: current_time(),
            last_active: current_time(),
            permissions: permissions
        }
        
        this.cache.SET(
            "session:" + session_id,
            serialize(session_data),
            TTL = this.ttl
        )
        
        // Also track user's active sessions (for "log out everywhere")
        this.cache.SET_ADD("user_sessions:" + user_id, session_id)
        
        RETURN session_id
    
    FUNCTION validate_session(session_id):
        session_data = this.cache.GET("session:" + session_id)
        IF session_data IS NULL:
            RETURN NULL
        
        // Extend TTL on activity (sliding expiration)
        this.cache.EXPIRE("session:" + session_id, this.ttl)
        
        RETURN deserialize(session_data)
    
    FUNCTION destroy_session(session_id):
        // Get user_id before deleting
        session_data = this.cache.GET("session:" + session_id)
        IF session_data EXISTS:
            data = deserialize(session_data)
            this.cache.SET_REMOVE("user_sessions:" + data.user_id, session_id)
        
        this.cache.DELETE("session:" + session_id)
    
    FUNCTION destroy_all_user_sessions(user_id):
        // Log out user from all devices
        session_ids = this.cache.SET_MEMBERS("user_sessions:" + user_id)
        IF session_ids IS NOT EMPTY:
            keys = ["session:" + sid FOR sid IN session_ids]
            this.cache.DELETE(keys)
        this.cache.DELETE("user_sessions:" + user_id)
```

### Session Failure Handling

**Redis unavailable**: This is critical—sessions are required for authentication.

```
FUNCTION get_session_with_fallback(session_id):
    TRY:
        RETURN session_manager.validate_session(session_id)
    CATCH CacheError:
        // Cache down - what do we do?
        // Option 1: Fail closed (secure, bad UX)
        // Option 2: Use backup session store
        // Option 3: Short-term JWT validation
        
        // Most common: Fail closed for security
        log.error("Session store unavailable")
        RETURN NULL  // User must re-authenticate
```

**Recommendation**: For sessions, have a Redis replica that can be promoted. Session loss is a significant user experience issue.

---

## Example 3: Public API Responses

### Requirements

- Public API serving mobile apps and third-party integrations
- Endpoints like /api/v1/products, /api/v1/categories
- 1 million requests/day
- Same response for all unauthenticated requests
- Data changes infrequently (product catalog)

### Multi-Layer Caching Strategy

Public APIs are perfect for aggressive caching because:
- Response is same for all users (no personalization)
- Content is relatively static
- High volume, repeated requests
- CDN can handle most traffic

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PUBLIC API CACHING LAYERS                                │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Layer 1: CDN (Cloudflare, Fastly, CloudFront)                      │   │
│   │                                                                     │   │
│   │  • Handles 95% of traffic                                           │   │
│   │  • TTL: 15 minutes                                                  │   │
│   │  • Instant invalidation via purge API                               │   │
│   │  • Global distribution = low latency worldwide                      │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                          │ (5% cache miss)                                  │
│                          ▼                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Layer 2: Application Cache (Redis)                                 │   │
│   │                                                                     │   │
│   │  • Handles CDN misses                                               │   │
│   │  • TTL: 1 hour                                                      │   │
│   │  • Shared across app servers                                        │   │
│   │  • Faster than database, absorbs CDN miss spikes                    │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                          │ (1% cache miss)                                  │
│                          ▼                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Layer 3: Database                                                  │   │
│   │                                                                     │   │
│   │  • Source of truth                                                  │   │
│   │  • Only sees ~1% of traffic                                         │   │
│   │  • Can be modestly sized                                            │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Cache hit rates:                                                          │
│   • CDN: 95% → 950K requests/day served at edge                             │
│   • Redis: 80% of remaining → 40K requests/day                              │
│   • Database: ~10K requests/day (from 1M)                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Implementation

```
ENDPOINT GET /api/v1/products:
    // Set CDN caching headers
    response = get_products_response()
    
    // Cache at CDN for 15 minutes
    response.headers["Cache-Control"] = "public, max-age=900, s-maxage=900"
    
    // Surrogate key for targeted purging
    response.headers["Surrogate-Key"] = "products product-list"
    
    // ETag for conditional requests
    response.headers["ETag"] = compute_etag(response.data)
    
    RETURN response

FUNCTION get_products_response():
    // Try cache first
    cached = cache.GET("api:products:list")
    IF cached EXISTS:
        RETURN make_response(cached)
    
    // Compute response
    products = database.get_all_products()
    response_data = serialize({products: products})
    
    // Cache in Redis
    cache.SET("api:products:list", response_data, TTL = 1 hour)
    
    RETURN make_response(response_data)

// Invalidation on product update
FUNCTION on_product_updated(product_id):
    // Invalidate cache
    cache.DELETE("api:products:list")
    cache.DELETE("api:products:" + product_id)
    
    // Invalidate CDN
    cdn.purge_by_tag("products")
    cdn.purge_by_tag("product-" + product_id)
```

### API Versioning and Cache Keys

```
FUNCTION cache_key_for_request(request):
    // Generate cache key that accounts for relevant variations
    RETURN "api:" + request.path + ":v" + get_api_version(request) + ":" + hash_query_params(request.args)

FUNCTION get_api_version(request):
    // Support both header and path versioning
    IF "X-API-Version" IN request.headers:
        RETURN request.headers["X-API-Version"]
    // Extract from path: /api/v1/... → v1
    match = regex_match("/api/(v\\d+)/", request.path)
    RETURN match[1] IF match EXISTS ELSE "v1"
```

---

# Part 6: Failure & Evolution

## Failure Propagation Through Cache Layers

**Staff Engineer Insight**: Understanding failure propagation paths is critical for designing resilient systems. Failures don't happen in isolation—they cascade through cache layers.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│         FAILURE PROPAGATION PATH THROUGH CACHE LAYERS                       │
│                                                                             │
│   Example: Multi-tier caching architecture (CDN → Redis → Database)         │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  NORMAL OPERATION                                                   │   │
│   │  ────────────────────────────────────────────────────────────────   │   │
│   │                                                                     │   │
│   │  [User Request]                                                     │   │
│   │       │                                                             │   │
│   │       ▼                                                             │   │
│   │  [CDN Edge] ──(60% hit)──→ [Response: 5ms]                          │   │
│   │       │                                                             │   │
│   │       └─(40% miss)──→ [App Server]                                  │   │
│   │                          │                                          │   │
│   │                          ▼                                          │   │
│   │                     [Redis Cache] ──(85% hit)──→ [Response: 10ms]   │   │
│   │                          │                                          │   │
│   │                          └─(15% miss)──→ [Database]                 │   │
│   │                                              │                      │   │
│   │                                              ▼                      │   │
│   │                                         [Response: 50ms]            │   │
│   │                                                                     │   │
│   │  Overall: 60% CDN hit (5ms), 34% Redis hit (10ms), 6% DB (50ms)     │   │
│   │  Average latency: ~12ms                                             │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  FAILURE SCENARIO 1: CDN Outage                                     │   │
│   │  ────────────────────────────────────────────────────────────────   │   │
│   │                                                                     │   │
│   │  [User Request]                                                     │   │
│   │       │                                                             │   │
│   │       ▼                                                             │   │
│   │  [CDN Edge] ──(FAILURE)──→ [Timeout: 5s]                            │   │
│   │       │                                                             │   │
│   │       └─(100% miss)──→ [App Server]                                 │   │
│   │                          │                                          │   │
│   │                          ▼                                          │   │
│   │                     [Redis Cache] ──(85% hit)──→ [Response: 10ms]   │   │
│   │                          │                                          │   │
│   │                          └─(15% miss)──→ [Database]                 │   │
│   │                                              │                      │   │
│   │                                              ▼                      │   │
│   │                                         [Response: 50ms]            │   │
│   │                                                                     │   │
│   │  Impact:                                                            │   │
│   │  • 60% of traffic loses CDN benefit (5ms → 10ms or 50ms)            │   │
│   │  • App servers see 2.5× traffic increase (60% → 100%)               │   │
│   │  • If app servers can't handle 2.5×: cascading failure              │   │
│   │  • Containment: App servers must handle 2.5× load                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  FAILURE SCENARIO 2: Redis Outage                                   │   │
│   │  ────────────────────────────────────────────────────────────────   │   │
│   │                                                                     │   │
│   │  [User Request]                                                     │   │
│   │       │                                                             │   │
│   │       ▼                                                             │   │
│   │  [CDN Edge] ──(60% hit)──→ [Response: 5ms]                          │   │
│   │       │                                                             │   │
│   │       └─(40% miss)──→ [App Server]                                  │   │
│   │                          │                                          │   │
│   │                          ▼                                          │   │
│   │                     [Redis Cache] ──(FAILURE)──→ [Timeout: 100ms]   │   │
│   │                          │                                          │   │
│   │                          └─(100% miss)──→ [Database]                │   │
│   │                                              │                      │   │
│   │                                              ▼                      │   │
│   │                                         [Response: 50ms]            │   │
│   │                                                                     │   │
│   │  Impact:                                                            │   │
│   │  • 34% of traffic loses Redis benefit (10ms → 50ms)                 │   │
│   │  • Database sees 6.7× traffic increase (6% → 40% of total)          │   │
│   │  • Database overloaded → timeouts → cascading failure               │   │
│   │  • Containment: Circuit breaker on DB, rate limiting                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  FAILURE SCENARIO 3: Database Outage                                │   │
│   │  ────────────────────────────────────────────────────────────────   │   │
│   │                                                                     │   │
│   │  [User Request]                                                     │   │
│   │       │                                                             │   │
│   │       ▼                                                             │   │
│   │  [CDN Edge] ──(60% hit)──→ [Response: 5ms]                          │   │
│   │       │                                                             │   │
│   │       └─(40% miss)──→ [App Server]                                  │   │
│   │                          │                                          │   │
│   │                          ▼                                          │   │
│   │                     [Redis Cache] ──(85% hit)──→ [Response: 10ms]   │   │
│   │                          │                                          │   │
│   │                          └─(15% miss)──→ [Database]                 │   │
│   │                                              │                      │   │
│   │                                              ▼                      │   │
│   │                                         [FAILURE: 5s timeout]       │   │
│   │                                                                     │   │
│   │  Impact:                                                            │   │
│   │  • 6% of requests fail completely (no fallback)                     │   │
│   │  • Users see errors for cache misses                                │   │
│   │  • Containment: Serve stale cache data (if acceptable)              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  FAILURE SCENARIO 4: Cascading Failure (CDN → Redis → DB)           │   │
│   │  ────────────────────────────────────────────────────────────────   │   │
│   │                                                                     │   │
│   │  Trigger: CDN outage                                                │   │
│   │                                                                     │   │
│   │  T+0s:   CDN fails → 100% traffic hits app servers                  │   │
│   │  T+5s:   App servers overloaded (2.5× traffic)                      │   │
│   │  T+10s:  App servers slow → Redis timeouts increase                 │   │
│   │  T+15s:  Redis appears "down" (actually app servers slow)           │   │
│   │  T+20s:  All traffic falls back to database                         │   │
│   │  T+25s:  Database overloaded → timeouts                             │   │
│   │  T+30s:  Full system outage                                         │   │
│   │                                                                     │   │
│   │  Root cause: CDN failure                                            │   │
│   │  Propagation: CDN → App servers → Redis → Database                  │   │
│   │  Blast radius: All user-facing requests                             │   │
│   │                                                                     │   │
│   │  Prevention:                                                        │   │
│   │  • App servers sized for 3× normal load (headroom)                  │   │
│   │  • Circuit breakers between each layer                              │   │
│   │  • Rate limiting on database path                                   │   │
│   │  • Graceful degradation (serve stale data)                          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   KEY INSIGHTS:                                                             │
│   ──────────────────────────────────────────────────────────────────────    │
│   1. Each cache layer failure increases load on next layer                  │
│   2. Failure propagation is exponential (not linear)                        │
│   3. Containment requires headroom at each layer                            │
│   4. Circuit breakers prevent cascading failures                            │
│   5. Stale data is better than no data (for most use case                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Design Principles for Failure Propagation**:

1. **Headroom at each layer**: Each layer must handle failure of the layer above it
2. **Circuit breakers**: Fail fast rather than cascade slowly
3. **Graceful degradation**: Serve stale data rather than fail completely
4. **Monitoring**: Detect failures at each layer before they propagate
5. **Blast radius containment**: Limit impact of single-layer failures

## What Happens When Cache Goes Down

### Immediate Impact

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CACHE FAILURE IMPACT                                     │
│                                                                             │
│   Before failure:                                                           │
│   [100K req/s] → [Redis: 95K] → [DB: 5K] ✓                                  │
│                                                                             │
│   Redis fails:                                                              │
│   [100K req/s] → [Redis: ✗] → [DB: 100K] ← 20× normal load                  │
│                                                                             │
│   Impact timeline:                                                          │
│   T+0s:    Redis unreachable, all requests hit DB                           │
│   T+5s:    DB connection pool saturated                                     │
│   T+10s:   Request timeouts begin                                           │
│   T+30s:   Error rate > 50%, alerts firing                                  │
│   T+60s:   Cascading failures to dependent services                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Graceful Degradation Strategy

```
CLASS CacheWithDegradation:
    CONSTRUCTOR(cache_client, db_client):
        this.cache = cache_client
        this.db = db_client
        this.db_limiter = NEW Semaphore(max_concurrent = 100)
        this.circuit_breaker = NEW CircuitBreaker()
    
    FUNCTION get(key, fetch_function):
        // Try cache
        TRY:
            WITH TIMEOUT(100 milliseconds):
                cached = this.cache.GET(key)
            IF cached EXISTS:
                RETURN deserialize(cached)
        CATCH (CacheError, TimeoutError):
            metrics.increment("cache.failure")
        
        // Cache miss or failure - try database with protection
        IF NOT this.circuit_breaker.is_closed():
            // Circuit is open - shed load
            THROW ServiceDegradedError("Service temporarily unavailable")
        
        TRY:
            WITH TIMEOUT(1 second):
                ACQUIRE this.db_limiter:
                    RETURN fetch_function()
        CATCH TimeoutError:
            this.circuit_breaker.record_failure()
            THROW ServiceDegradedError("High load, please retry")
```

### Slow Cache Dependency: The Silent Killer

**Staff Engineer Insight**: Total cache failure is obvious, but slow cache dependencies are insidious. When Redis latency increases from 1ms to 500ms, your system doesn't fail completely—it degrades slowly, making diagnosis harder.

**The Problem**: Cache is "up" but slow, causing cascading timeouts:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│         SLOW CACHE DEPENDENCY: PARTIAL FAILURE TIMELINE                     │
│                                                                             │
│   Scenario: Redis network partition causes latency spikes                   │
│   Normal Redis latency: 1ms, Degraded latency: 500ms                        │
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │  T+0s:    Redis primary node loses network connectivity               │ │
│   │  T+1s:    Redis Sentinel detects failure, starts failover             │ │
│   │  T+2s:    Client connections timeout: 1ms → 100ms (timeout)           │ │
│   │  T+3s:    Clients retry → hit replica (not yet promoted)              │ │
│   │  T+5s:    Replica read latency: 1ms → 500ms (network issues)          │ │
│   │  T+10s:   Application cache.get() calls: 1ms → 500ms                  │ │
│   │  T+15s:   Request latency increases: p50=50ms → p50=550ms             │ │
│   │  T+20s:   Application thread pool exhausted (threads waiting on cache)│ │
│   │  T+30s:   New requests queued, user-facing latency: p99=2s            │ │
│   │  T+45s:   Some requests timeout (5s threshold) → hit database         │ │
│   │  T+60s:   Database load increases: 5K → 15K req/s (timeout fallback)  │ │
│   │  T+90s:   Database CPU spikes, query latency increases                │ │
│   │  T+120s:  Full system degradation (cache slow + DB overloaded)        │ │
│   │                                                                       │ │
│   │  Why This Is Worse Than Total Failure:                                │ │
│   │  • No clear "cache is down" signal (it's "up" but slow)               │ │
│   │  • Timeouts cause retries → amplifies load                            │ │
│   │  • Fallback to DB happens gradually → DB overloads slowly             │ │
│   │  • Harder to diagnose (is it cache? network? DB? all of them?)        │ │
│   │  • Circuit breaker may not trigger (requests eventually succeed)      │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Prevention: Aggressive Timeouts and Circuit Breakers**

```
CLASS CacheWithLatencyProtection:
    CONSTRUCTOR(cache_client, db_client):
        this.cache = cache_client
        this.db = db_client
        this.cache_timeout = 50 milliseconds  // Aggressive timeout
        this.circuit_breaker = NEW CircuitBreaker(
            failure_threshold = 10,
            latency_threshold = 100 milliseconds,  // Trip if p50 > 100ms
            timeout = 30 seconds
        )
    
    FUNCTION get(key, fetch_function):
        // Try cache with aggressive timeout
        TRY:
            WITH TIMEOUT(this.cache_timeout):
                cached = this.cache.GET(key)
            IF cached EXISTS:
                this.circuit_breaker.record_success()
                RETURN deserialize(cached)
        CATCH (CacheError, TimeoutError):
            // Cache slow or down - record failure
            this.circuit_breaker.record_failure()
            metrics.increment("cache.slow_or_down")
        
        // If circuit is open OR cache is consistently slow, skip cache
        IF this.circuit_breaker.is_open():
            log.warning("Cache circuit open, skipping cache for " + key)
            RETURN fetch_function()  // Go straight to DB
        
        // Cache miss - try database
        RETURN fetch_function()
    
    FUNCTION monitor_cache_health():
        // Background task: monitor cache latency
        WHILE true:
            start = current_time()
            TRY:
                WITH TIMEOUT(100 milliseconds):
                    this.cache.GET("__health_check__")
                latency = current_time() - start
                
                IF latency > 50 milliseconds:
                    metrics.histogram("cache.latency.degraded", latency)
                    alert.warn("Cache latency elevated: " + latency + "ms")
                
                this.circuit_breaker.record_latency(latency)
            CATCH Exception:
                this.circuit_breaker.record_failure()
            
            SLEEP(10 seconds)
```

**Key Design Decisions**:

1. **Aggressive timeouts (50ms)**: Fail fast rather than wait 500ms. Better to hit DB immediately than wait on slow cache.
2. **Latency-based circuit breaker**: Trip not just on errors, but on sustained high latency.
3. **Skip cache when degraded**: If cache is consistently slow, bypass it entirely rather than degrading the whole system.
4. **Separate health check**: Monitor cache latency independently from request path.

**Trade-offs**:
- **Pro**: System degrades gracefully, doesn't cascade failures
- **Pro**: Clear signal when cache is slow (circuit breaker state)
- **Con**: Lower cache hit rate during degradation (but that's acceptable)
- **Con**: More complex than simple cache-aside pattern

**When to use**: Critical paths where cache latency directly impacts user experience (API gateway, rate limiters, session lookups).

### Redis High Availability Setup

For production systems, single Redis is unacceptable:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    REDIS HIGH AVAILABILITY                                  │
│                                                                             │
│   Option 1: Redis Sentinel                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │     [Sentinel 1]    [Sentinel 2]    [Sentinel 3]                    │   │
│   │          │               │               │                          │   │
│   │          └───────────────┼───────────────┘                          │   │
│   │                          │ (monitors & elects)                      │   │
│   │                          ▼                                          │   │
│   │     [Primary] ←───────────→ [Replica]                               │   │
│   │                                                                     │   │
│   │   • Automatic failover (10-30 seconds)                              │   │
│   │   • Sentinels vote to promote replica                               │   │
│   │   • Some writes may be lost during failover                         │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Option 2: Redis Cluster                                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   [Primary A] ─ [Replica A']     Hash slots 0-5460                  │   │
│   │   [Primary B] ─ [Replica B']     Hash slots 5461-10922              │   │
│   │   [Primary C] ─ [Replica C']     Hash slots 10923-16383             │   │
│   │                                                                     │   │
│   │   • Data sharded across nodes                                       │   │
│   │   • Each shard has its own replica                                  │   │
│   │   • Node failure affects only its slots                             │   │
│   │   • Horizontal scalability                                          │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Recommendation: Start with Sentinel, move to Cluster when sharding        │
│                   needed (>100GB data or >100K ops/sec per node)            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## How Caching Strategy Evolves with Scale

### Phase 1: No Cache (< 10K users)

```
[App Server] → [Database]

• Database handles all traffic directly
• Simple, no cache complexity
• Good enough for early stage
```

**When to add caching**: When database becomes bottleneck OR costs become significant.

### Phase 2: Application Cache (10K - 100K users)

```
[App Server] → [Redis] → [Database]

• Redis handles frequently accessed data
• Hit rate: 70-90%
• Database load reduced significantly
• Simple cache-aside pattern
```

**Add when**: Traffic exceeds database capacity, want cost savings.

### Phase 3: Multi-Tier Cache (100K - 1M users)

```
[CDN] → [App Server] → [Redis] → [Database]

• CDN handles static content and public API responses
• Redis handles personalized/dynamic content
• Database only sees cache misses
• Most traffic never reaches your servers
```

**Add when**: Global users need low latency, want to reduce server costs.

### Phase 4: Distributed Cache (1M+ users)

```
[CDN] → [App Server] → [Redis Cluster] → [Database Cluster]
              ↓
         [Local Cache]

• Redis Cluster for horizontal scale
• Local in-process cache for ultra-hot data
• Multi-region CDN presence
• Database sharded or using NewSQL
```

**Add when**: Single Redis node is bottleneck, need multi-region.

### V1 → 10× → 100× Growth Model: Bottleneck Identification Before Failure

**Staff Engineer Insight**: Design caching strategy not just for current scale, but with explicit growth modeling. Identify bottlenecks BEFORE they become failures.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│         CACHING EVOLUTION: V1 → 10× → 100× GROWTH MODEL                     │
│                                                                             │
│   Example: News feed API caching strategy evolution                         │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  V1: 10K users, 1K req/s                                            │   │
│   │  ────────────────────────────────────────────────────────────────   │   │
│   │  Architecture:                                                      │   │
│   │  [App] → [PostgreSQL]                                               │   │
│   │                                                                     │   │
│   │  Metrics:                                                           │   │
│   │  • DB CPU: 20%                                                      │   │
│   │  • DB cost: $200/month                                              │   │
│   │  • p99 latency: 50ms                                                │   │
│   │  • No caching needed                                                │   │
│   │                                                                     │   │
│   │  Bottleneck Analysis (Projected to 10×):                            │   │
│   │  • At 10K req/s: DB CPU would be 200% (impossible)                  │   │
│   │  • At 10K req/s: DB cost would be $2,000/month                      │   │
│   │  • At 10K req/s: p99 latency would be 500ms (SLO violation)         │   │
│   │                                                                     │   │
│   │  Decision: Add Redis cache BEFORE hitting 10× scale                 │   │
│   │  Trigger: When traffic reaches 5K req/s (50% of 10× threshold)      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  10×: 100K users, 10K req/s                                         │   │
│   │  ────────────────────────────────────────────────────────────────   │   │
│   │  Architecture:                                                      │   │
│   │  [App] → [Redis] → [PostgreSQL]                                     │   │
│   │                                                                     │   │
│   │  Metrics:                                                           │   │
│   │  • Cache hit rate: 90%                                              │   │
│   │  • DB CPU: 25% (handles 1K req/s after cache)                       │   │
│   │  • Redis CPU: 40%                                                   │   │
│   │  • Redis memory: 8GB / 16GB                                         │   │
│   │  • Total cost: $200 (DB) + $300 (Redis) = $500/month                │   │
│   │  • p99 latency: 10ms (cache) / 50ms (DB miss)                       │   │
│   │                                                                     │   │
│   │  Bottleneck Analysis (Projected to 100×):                           │   │
│   │  • At 100K req/s: Redis CPU would be 400% (impossible)              │   │
│   │  • At 100K req/s: Redis memory would be 80GB (single node limit)    │   │
│   │  • At 100K req/s: DB would see 10K req/s (still manageable)         │   │
│   │  • At 100K req/s: Network bandwidth: 1Gbps → 10Gbps needed          │   │
│   │                                                                     │   │
│   │  Decision: Plan Redis Cluster BEFORE hitting 100× scale             │   │
│   │  Trigger: When traffic reaches 50K req/s (50% of 100× threshold)    │   │
│   │                                                                     │   │
│   │  Pre-emptive Actions:                                               │   │
│   │  • Test Redis Cluster in staging                                    │   │
│   │  • Implement cache sharding logic                                   │   │
│   │  • Add CDN for public feed endpoints                                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  100×: 1M users, 100K req/s                                         │   │
│   │  ────────────────────────────────────────────────────────────────   │   │
│   │  Architecture:                                                      │   │
│   │  [CDN] → [App] → [Redis Cluster] → [PostgreSQL Cluster]             │   │
│   │         ↓                                                           │   │
│   │    [Local Cache]                                                    │   │
│   │                                                                     │   │
│   │  Metrics:                                                           │   │
│   │  • CDN hit rate: 60% (public feeds)                                 │   │
│   │  • Redis hit rate: 85% (personalized feeds)                         │   │
│   │  • Local cache hit rate: 5% (ultra-hot data)                        │   │
│   │  • DB CPU: 30% (handles 10K req/s after all caches)                 │   │
│   │  • Redis Cluster: 6 nodes, 30% CPU each                             │   │
│   │  • Total cost: $1,000 (DB) + $1,800 (Redis) + $500 (CDN) = $3,300   │   │
│   │  • p99 latency: 5ms (CDN) / 8ms (Redis) / 50ms (DB miss)            │   │
│   │                                                                     │   │
│   │  Bottleneck Analysis (Projected to 1000×):                          │   │
│   │  • At 1M req/s: CDN bandwidth costs would be $50K/month             │   │
│   │  • At 1M req/s: Redis Cluster would need 60 nodes                   │   │
│   │  • At 1M req/s: Multi-region becomes mandatory                      │   │
│   │  • At 1M req/s: Database sharding required                          │   │
│   │                                                                     │   │
│   │  Decision: Plan multi-region caching BEFORE hitting 1000×           │   │
│   │  Trigger: When traffic reaches 500K req/s (50% of 1000× threshold)  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   KEY PRINCIPLES:                                                           │
│   ──────────────────────────────────────────────────────────────────────    │
│   1. Identify bottlenecks at 10× BEFORE they become failures at 10×     │   │
│   2. Model costs at each scale point (V1, 10×, 100×, 1000×)             │   │
│   3. Test next-tier architecture BEFORE you need it                     │   │
│   4. Document capacity limits explicitly (CPU, memory, network, cost)   │   │
│   5. Set trigger thresholds at 50% of next scale point                  │   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Bottleneck Identification Framework**:

For each scale point, explicitly model:
1. **CPU**: Can current architecture handle 10× CPU load?
2. **Memory**: Will data fit in available memory at 10×?
3. **Network**: Will bandwidth be sufficient at 10×?
4. **Cost**: Is cost growth linear or exponential? Can we afford 10×?
5. **Latency**: Will p99 latency meet SLO at 10×?
6. **Operational complexity**: Can team operate this at 10×?

**Example Bottleneck Analysis**:

```
FUNCTION analyze_cache_bottlenecks(current_traffic, cache_config):
    // Model bottlenecks at 10× and 100× scale
    projected_10x = current_traffic * 10
    projected_100x = current_traffic * 100
    
    bottlenecks = []
    
    // CPU bottleneck
    current_cpu = cache_config.cpu_utilization_percent
    IF current_cpu * 10 > 100:
        bottlenecks.append({
            type: "CPU",
            scale: "10×",
            current: current_cpu + "%",
            projected: (current_cpu * 10) + "%",
            action: "Add Redis Cluster or increase node size"
        })
    
    // Memory bottleneck
    current_memory_gb = cache_config.memory_used_gb
    max_memory_gb = cache_config.memory_max_gb
    projected_memory_10x = current_memory_gb * 10
    
    IF projected_memory_10x > max_memory_gb:
        bottlenecks.append({
            type: "Memory",
            scale: "10×",
            current: current_memory_gb + "GB",
            projected: projected_memory_10x + "GB",
            max: max_memory_gb + "GB",
            action: "Shard data across Redis Cluster"
        })
    
    // Cost bottleneck
    current_cost = cache_config.monthly_cost_usd
    projected_cost_10x = current_cost * 10
    
    IF projected_cost_10x > cache_config.cost_budget_usd:
        bottlenecks.append({
            type: "Cost",
            scale: "10×",
            current: "$" + current_cost + "/month",
            projected: "$" + projected_cost_10x + "/month",
            budget: "$" + cache_config.cost_budget_usd + "/month",
            action: "Optimize TTLs, compress data, or use cheaper tier"
        })
    
    RETURN bottlenecks
```

**When to Evolve**: Set explicit thresholds, not vague "when needed":

- **Add Redis**: When DB CPU > 50% OR traffic > 50% of DB capacity
- **Add CDN**: When global users > 3 regions OR CDN cost < origin cost
- **Add Redis Cluster**: When single node CPU > 60% OR memory > 70%
- **Add local cache**: When Redis p99 latency > 10ms AND hit rate > 95%

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CACHE EVOLUTION TRIGGERS                                 │
│                                                                             │
│   Add caching when:                                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Database CPU > 70% sustained                                     │   │
│   │  • Database costs > $X/month (your threshold)                       │   │
│   │  • p99 latency exceeds SLO                                          │   │
│   │  • Need to survive traffic spikes                                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Add CDN when:                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Users in multiple geographic regions                             │   │
│   │  • Significant static content                                       │   │
│   │  • Public API with high traffic                                     │   │
│   │  • Origin server costs are significant                              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Add Redis Cluster when:                                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Data > 50GB (approaching single-node memory limits)              │   │
│   │  • > 100K ops/sec (approaching single-node CPU limits)              │   │
│   │  • Need multi-master for write throughput                           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Add local (in-process) cache when:                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Redis network latency matters for hot path                       │   │
│   │  • Very small, very hot dataset (<1000 items)                       │   │
│   │  • Can tolerate slight inconsistency across servers                 │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 7: Summary and Key Takeaways

## Caching Principles for Staff Engineers

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    STAFF ENGINEER CACHING PRINCIPLES                        │
│                                                                             │
│   1. CACHE FOR PROTECTION FIRST                                             │
│      Primary goal: Protect backend from overload                            │
│      Secondary goal: Cost reduction                                         │
│      Tertiary goal: Latency improvement                                     │
│                                                                             │
│   2. DESIGN FOR CACHE FAILURE                                               │
│      Cache will go down. Plan for it.                                       │
│      Graceful degradation > hoping for the best                             │
│                                                                             │
│   3. UNDERSTAND YOUR HIT RATE                                               │
│      < 80% hit rate: Question if caching is worth the complexity            │
│      > 95% hit rate: You're getting good value                              │
│      Monitor continuously, not just at launch                               │
│                                                                             │
│   4. INVALIDATION IS HARD                                                   │
│      Start with TTL-only if possible                                        │
│      Add explicit invalidation only when TTL isn't sufficient               │
│      Test invalidation thoroughly before production                         │
│                                                                             │
│   5. CACHE THE RIGHT LAYER                                                  │
│      Raw database rows: Easy to invalidate, low reuse                       │
│      Computed results: Harder to invalidate, high value                     │
│      Rendered responses: Highest value, careful with personalization        │
│                                                                             │
│   6. CDN FOR PUBLIC, REDIS FOR PRIVATE                                      │
│      Public content → CDN (cheap, global, high volume)                      │
│      Personalized content → Redis (centralized, invalidatable)              │
│      Never cache private data at CDN                                        │
│                                                                             │
│   7. COMPLEXITY HAS COST                                                    │
│      Every cache layer is operational burden                                │
│      Simple > clever                                                        │
│      Sometimes the answer is "don't cache"                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Mental Models and One-Liners for Caching

Memorable phrases help Staff Engineers make fast decisions and teach others.

| Mental Model | One-Liner |
|--------------|-----------|
| **Cache as shield** | "Cache protects the backend from traffic it can't handle." |
| **Cache as economic layer** | "Cheap reads (Redis, CDN) displace expensive reads (database, origin)." |
| **Correctness vs performance** | "Cache is a performance optimization, never a correctness requirement." |
| **Failure design** | "Cache will go down. Plan for it. Graceful degradation > hoping for the best." |
| **Invariant** | "Stale permissions never grant access; stale data never leaks another user's data." |
| **Trust boundary** | "If a single header or param can change the response, it must be in the cache key or the response must not be cached." |
| **First bottleneck** | "Cache the first bottleneck. Fix the query before you hide it with cache." |
| **Complexity budget** | "Every cache layer is operational burden. Simple > clever." |
| **Sustainability** | "Right-sized cache reduces total system energy. Over-provisioned cache is waste." |
| **Compliance** | "Cache must not extend the blast radius of a compliance violation. If you can't purge it on demand, don't cache it." |
| **Hot key** | "Hashing distributes keys, not traffic. Hot keys overload one shard—design for them." |
| **Eviction storm** | "Eviction storms mean cache is up but useless. Monitor eviction rate; it's a leading indicator of capacity problems." |
| **Platform ownership** | "When three teams share a cache, it's platform. When one team has a cache, it's application." |

**Teaching tip**: When mentoring, lead with the one-liner, then unpack the trade-offs. "Cache is a performance optimization, never a correctness requirement" → means: source of truth is always the backend; cache miss or failure must never cause wrong data to be returned.

---

# Part 8: Staff-Level Deep Dives

## Blast Radius Analysis for Cache Failures

Staff Engineers must understand and contain the blast radius of cache failures. Unlike database failures (which typically have well-understood failover), cache failures often cascade in unexpected ways.

### Understanding Cache Blast Radius

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CACHE FAILURE BLAST RADIUS                               │
│                                                                             │
│   Scenario: Redis cluster loses one of three shards                         │
│                                                                             │
│   Direct Impact:                                                            │
│   • 33% of cache keys unavailable                                           │
│   • Those requests hit database                                             │
│                                                                             │
│   Cascade Level 1:                                                          │
│   • Database load increases 33%                                             │
│   • If DB was at 70% capacity → now at 93%                                  │
│   • Query latency increases for ALL requests                                │
│                                                                             │
│   Cascade Level 2:                                                          │
│   • Slow DB queries cause app server threads to block                       │
│   • Thread pool exhaustion                                                  │
│   • Timeout errors for unrelated requests                                   │
│                                                                             │
│   Cascade Level 3:                                                          │
│   • Retry storms from clients seeing errors                                 │
│   • Traffic amplification                                                   │
│   • Complete service degradation                                            │
│                                                                             │
│   Blast radius: 33% cache failure → 100% service degradation                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Containment Strategies

**Strategy 1: Bulkhead Pattern**

Separate cache pools for different criticality levels:

```
CLASS BulkheadedCache:
    // Separate cache pools to contain failures.
    // Critical data gets more protection.
    
    CONSTRUCTOR():
        this.pools = {
            "critical": NEW CachePool("redis-critical", size = 10),    // Sessions, auth
            "standard": NEW CachePool("redis-standard", size = 50),    // User data
            "ephemeral": NEW CachePool("redis-ephemeral", size = 100)  // Computed caches
        }
    
    FUNCTION get_pool(data_type):
        classification = this.classify(data_type)
        RETURN this.pools[classification]
    
    FUNCTION classify(data_type):
        IF data_type IN ["session", "auth_token", "permissions"]:
            RETURN "critical"
        ELSE IF data_type IN ["user_profile", "cart"]:
            RETURN "standard"
        ELSE:
            RETURN "ephemeral"
```

**Why this matters**: If the ephemeral cache pool fails, sessions and auth continue working. The blast radius is contained to non-critical data.

**Strategy 2: Request Shedding**

When cache fails, don't try to serve all traffic:

```
CLASS LoadSheddingCache:
    CONSTRUCTOR(max_db_qps = 5000):
        this.max_db_qps = max_db_qps
        this.current_db_qps = NEW AtomicCounter()
        this.shedding_active = FALSE
    
    FUNCTION get(key, fetch_function):
        // Try cache
        TRY:
            cached = this.cache.GET(key)
            IF cached EXISTS:
                RETURN deserialize(cached)
        CATCH CacheError:
            this.activate_shedding()
        
        // Cache miss or failure
        IF this.shedding_active:
            // Only allow subset of requests through
            IF this.current_db_qps.value > this.max_db_qps:
                THROW ServiceUnavailableError("Load shedding active")
        
        this.current_db_qps.increment()
        TRY:
            RETURN fetch_function()
        FINALLY:
            this.current_db_qps.decrement()
    
    FUNCTION activate_shedding():
        IF NOT this.shedding_active:
            this.shedding_active = TRUE
            log.critical("Load shedding activated due to cache failure")
            metrics.increment("cache.load_shedding.activated")
```

**The key insight**: It's better to return errors to 80% of users than to have 100% of users see degraded performance or complete failure.

---

## Observability and Debuggability for Cache

Staff Engineers design cache visibility so that when things go wrong, the path from symptom to root cause is short. Cache sits in the middle of the request path—without proper instrumentation, one request can touch CDN, Redis, and database, and correlating behavior across layers is hard.

### Trace Correlation Across Cache Layers

When a user reports "slow page load," the request may have hit:
1. CDN miss → origin fetch
2. Redis timeout → database fallback
3. Database slow query

**Staff approach**: Propagate a request ID (or trace ID) through every layer. Each cache operation logs: `{trace_id, key, result: hit|miss|timeout, latency_ms}`. In your observability system, one trace shows the full path.

| Layer | What to log | What to metric |
|-------|-------------|----------------|
| CDN | Cache key (sanitized), hit/miss, origin fetch time | Hit rate by path, miss latency histogram |
| Redis | Key pattern (not full key if PII), operation, latency | Hit rate, p99 latency, connection errors |
| Database fallback | Trigger reason (miss, timeout, error) | Fallback rate, database latency when used as fallback |

**One-liner**: "If you can't trace one request through CDN → Redis → DB, you can't debug cache issues."

### When Traces Don't Reveal the Answer

**Staff Engineer Insight**: Sometimes the trace shows the path but not the cause. Cache bugs can be subtle: wrong key, wrong TTL, invalidation race, or schema mismatch. When traces show "cache hit" but the user sees wrong data, you need a different approach.

**Debugging playbook when traces aren't enough**:
1. **Reproduce with controlled params**: Same user, same key, same path. Does the bug reproduce? If yes, it's deterministic; if no, it's timing-dependent.
2. **Check cache key construction**: Log the exact key used. Could a missing dimension (user_id, version, locale) cause wrong-data hit?
3. **Verify invalidation path**: On write, do we invalidate? Is the invalidation synchronous or eventual? Could a race window explain stale reads?
4. **Inspect cached value**: For the specific key, what's actually stored? Serialization bug? Old schema?
5. **Eliminate layers**: Bypass CDN (direct to origin), bypass Redis (direct to DB). Which layer serves wrong data?

**Concrete example**: Users reported seeing another user's cart. Traces showed cache hit. The cache key was `cart:{user_id}`—correct. Root cause: a bug in session resolution returned the wrong `user_id` for 0.1% of requests. The cache was correct; the input was wrong. Fix: trace back to session handling, not cache.

**Trade-off**: Deeper debugging takes time. Staff Engineers invest in deterministic reproduction and layer elimination before changing code. "Fix the symptom" (e.g., shorter TTL) can mask the real bug.

### First-Bottleneck Analysis

Before adding caching, Staff Engineers identify the *first* bottleneck—the resource that will limit growth soonest. Caching that resource has the highest leverage.

| Scale Stage | Typical First Bottleneck | When to Add Cache |
|--------------|--------------------------|-------------------|
| 0–10K req/s | Database connections or query latency | Add Redis when DB CPU > 50% or connection pool > 70% |
| 10K–100K req/s | Database throughput | Cache must be in place; focus on hit rate and key design |
| 100K+ req/s | Redis memory or network | Add CDN for public content; consider Redis Cluster |
| Global users | Origin latency for distant regions | CDN at edge before adding regions |

**Example**: A feed service at 5K req/s might see DB at 30% CPU. The first bottleneck is not DB yet—it's likely application logic or lack of indexes. Adding cache here *hides* the real bottleneck. Staff move: fix the query first; add cache when approaching 50% DB capacity.

---

## Cache Key Design Best Practices

Poor cache key design causes subtle bugs and performance issues. Staff Engineers design keys deliberately.

### Key Design Principles

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CACHE KEY DESIGN PRINCIPLES                              │
│                                                                             │
│   1. HIERARCHICAL STRUCTURE                                                 │
│      {service}:{entity}:{id}:{variant}                                      │
│                                                                             │
│      Good: "user-service:profile:12345:full"                                │
│      Bad:  "12345" or "user_12345"                                          │
│                                                                             │
│   2. INCLUDE VERSION                                                        │
│      {version}:{service}:{entity}:{id}                                      │
│                                                                             │
│      Good: "v3:user:profile:12345"                                          │
│      Enables: Schema changes without explicit purge                         │
│                                                                             │
│   3. PREDICTABLE PATTERNS                                                   │
│      Keys must be reconstructable from request context                      │
│                                                                             │
│      Good: "feed:{user_id}:page:{page_num}"                                 │
│      Bad:  "feed_abc123def456" (random suffix)                              │
│                                                                             │
│   4. BOUNDED KEY SPACE                                                      │
│      Prevent unbounded key growth                                           │
│                                                                             │
│      Danger: "search:{query}" where query is user-provided                  │
│      Better: "search:{hash(query)[:16]}"                                    │
│                                                                             │
│   5. INVALIDATION FRIENDLY                                                  │
│      Design for wildcard deletion if needed                                 │
│                                                                             │
│      Good: "user:12345:*" can be pattern-deleted                            │
│      Note: Pattern deletion is expensive - prefer explicit invalidation     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Design Implementation

```
CLASS CacheKeyBuilder:
    // Consistent cache key generation.
    // All cache access goes through this.
    
    CONSTANT VERSION = "v3"
    CONSTANT SERVICE = "api-gateway"
    
    STATIC FUNCTION user_profile(user_id):
        RETURN VERSION + ":" + SERVICE + ":user:profile:" + user_id
    
    STATIC FUNCTION user_feed(user_id, page):
        RETURN VERSION + ":" + SERVICE + ":feed:" + user_id + ":page:" + page
    
    STATIC FUNCTION search_results(query, filters):
        // Hash to prevent unbounded key space
        query_hash = sha256(lowercase(query)).substring(0, 16)
        filter_hash = sha256(serialize(filters, sorted = true)).substring(0, 8)
        RETURN VERSION + ":" + SERVICE + ":search:" + query_hash + ":" + filter_hash
    
    STATIC FUNCTION rate_limit(client_id, window):
        // Rate limit keys need to be reconstructable
        RETURN VERSION + ":ratelimit:" + client_id + ":" + window
    
    STATIC FUNCTION invalidation_pattern(entity, entity_id):
        // For batch invalidation - use sparingly
        RETURN VERSION + ":" + SERVICE + ":" + entity + ":" + entity_id + ":*"
```

### Common Key Design Mistakes

| Mistake | Problem | Fix |
|---------|---------|-----|
| User input in key | Unbounded key space, potential injection | Hash user input |
| No version | Can't evolve schema | Include version prefix |
| No service prefix | Key collisions across services | Include service name |
| Inconsistent format | Hard to debug, invalidate | Use key builder class |
| Embedding timestamps | Low hit rate, high cardinality | Use rounded time buckets |

---

## Write-Path Failure Handling

What happens when the cache write fails after you've already returned data to the user? This is a subtle but important failure mode.

### The Problem

```
// Common but problematic pattern
FUNCTION get_user(user_id):
    cached = cache.GET("user:" + user_id)
    IF cached EXISTS:
        RETURN deserialize(cached)
    
    user = database.get_user(user_id)
    
    // What if this fails?
    cache.SET("user:" + user_id, serialize(user), TTL = 1 hour)  // <-- FAILURE
    
    RETURN user  // User gets data, but cache is never populated
```

**Why it matters**: If cache writes consistently fail (network issue, Redis out of memory), every request becomes a cache miss, defeating the purpose of caching entirely.

### Solution: Defensive Write Pattern

```
FUNCTION get_user_defensive(user_id):
    cached = cache.GET("user:" + user_id)
    IF cached EXISTS:
        RETURN deserialize(cached)
    
    user = database.get_user(user_id)
    
    // Non-blocking cache write with monitoring
    SPAWN_ASYNC cache_with_monitoring("user:" + user_id, user)
    
    RETURN user

FUNCTION cache_with_monitoring(key, value):
    TRY:
        WITH TIMEOUT(500 milliseconds):
            cache.SET(key, serialize(value), TTL = 1 hour)
    CATCH TimeoutError:
        metrics.increment("cache.write.timeout")
        log.warning("Cache write timeout for " + key)
    CATCH CacheError AS e:
        metrics.increment("cache.write.error")
        log.error("Cache write failed for " + key + ": " + e)
        
        // If write errors are sustained, something is wrong
        IF check_sustained_failures():
            alerting.page("cache-write-failures-sustained")
```

### Invalidation Write Failures

Even more critical: what if cache invalidation fails?

```
FUNCTION update_user(user_id, data):
    // Update database
    database.update_user(user_id, data)
    
    // Invalidate cache - what if this fails?
    TRY:
        cache.DELETE("user:" + user_id)
    CATCH CacheError:
        // Cache invalidation failed - stale data will be served!
        log.critical("Cache invalidation failed for user:" + user_id)
        
        // Options:
        // 1. Retry with exponential backoff
        // 2. Queue for later invalidation
        // 3. Alert for manual intervention
        // 4. Accept staleness until TTL expires
        
        enqueue_invalidation("user:" + user_id)
        metrics.increment("cache.invalidation.failed")
```

### Invalidation Queue Pattern

```
CLASS InvalidationQueue:
    // Reliable invalidation with at-least-once delivery.
    // Used when cache invalidation is critical.
    
    CONSTRUCTOR():
        this.queue = NEW Queue()
        this.retry_delay = 1 second
    
    FUNCTION enqueue(key):
        this.queue.put({
            key: key,
            attempts: 0,
            first_attempt: current_time()
        })
    
    FUNCTION process_loop():
        LOOP FOREVER:
            item = this.queue.get()
            
            TRY:
                cache.DELETE(item.key)
                metrics.increment("cache.invalidation.success")
            CATCH CacheError:
                item.attempts = item.attempts + 1
                
                IF item.attempts < 10:
                    // Retry with backoff
                    delay = MIN(this.retry_delay * (2 ^ item.attempts), 60 seconds)
                    SLEEP(delay)
                    this.queue.put(item)
                ELSE:
                    // Too many retries - alert
                    age = current_time() - item.first_attempt
                    log.critical(
                        "Invalidation failed after " + item.attempts + " attempts "
                        "for " + item.key + ", age: " + age + "s"
                    )
                    metrics.increment("cache.invalidation.exhausted")
```

---

## Testing Cache Behavior

Caching bugs are notoriously hard to reproduce. Staff Engineers build testable caching systems.

### Unit Testing Caches

```
CLASS TestCacheAside:
    FIXTURE cache_service:
        cache = MockCache()
        db = MockDatabase()
        RETURN NEW CacheService(cache, db)
    
    TEST cache_hit_returns_cached_value(cache_service):
        cache_service.cache.get.returns('{"id": 1, "name": "Alice"}')
        
        result = cache_service.get_user(1)
        
        ASSERT result.name == "Alice"
        ASSERT cache_service.db.get_user.was_not_called()  // DB should not be hit
    
    TEST cache_miss_fetches_from_db(cache_service):
        cache_service.cache.get.returns(NULL)
        cache_service.db.get_user.returns({id: 1, name: "Bob"})
        
        result = cache_service.get_user(1)
        
        ASSERT result.name == "Bob"
        ASSERT cache_service.db.get_user.was_called_once_with(1)
        ASSERT cache_service.cache.set.was_called()  // Should cache the result
    
    TEST cache_failure_falls_back_to_db(cache_service):
        cache_service.cache.get.throws(CacheError("Connection failed"))
        cache_service.db.get_user.returns({id: 1, name: "Charlie"})
        
        result = cache_service.get_user(1)
        
        ASSERT result.name == "Charlie"  // Should work despite cache failure
    
    TEST invalidation_after_update(cache_service):
        cache_service.update_user(1, {name: "Updated"})
        
        ASSERT cache_service.db.update_user.was_called_once()
        ASSERT cache_service.cache.delete.was_called_with("user:1")
```

### Integration Testing with Real Cache

```
FIXTURE cache_client:
    client = connect_cache(host = "localhost", port = 6379, db = 15)  // Use separate DB for tests
    YIELD client
    client.flush_database()  // Clean up after tests

CLASS TestCacheIntegration:
    TEST cache_hit_rate_under_load(cache_client):
        // Verify hit rate matches expectations
        cache = NEW CacheService(cache_client)
        
        // Populate cache
        FOR i = 0 TO 100:
            cache.get_user(i)
        
        // Measure hit rate
        hits = 0
        total = 1000
        FOR _ = 1 TO total:
            user_id = random_int(0, 99)
            start = current_time()
            cache.get_user(user_id)
            IF current_time() - start < 1 millisecond:  // Fast response = likely cache hit
                hits = hits + 1
        
        hit_rate = hits / total
        ASSERT hit_rate > 0.9, "Hit rate " + hit_rate + " below expected 90%"
    
    TEST ttl_expiration(cache_client):
        // Verify TTL works correctly
        cache = NEW CacheService(cache_client, ttl = 1 second)
        
        cache.set_user(1, {name: "Test"})
        ASSERT cache.get_user(1) == {name: "Test"}
        
        SLEEP(1.5 seconds)  // Wait for TTL
        
        // Should be cache miss now
        ASSERT cache_client.GET("user:1") IS NULL
```

### Chaos Testing for Caches

```
CLASS CacheChaosTest:
    // Chaos tests for cache resilience.
    // Run in staging, not production.
    
    TEST cache_failure_resilience():
        // Simulate complete cache failure
        // Start with healthy system
        ASSERT this.health_check() == "healthy"
        
        // Kill cache
        this.chaos.kill_service("redis-primary")
        
        // System should degrade gracefully
        SLEEP(5 seconds)
        status = this.health_check()
        ASSERT status IN ["degraded", "healthy"], "System failed: " + status
        
        // Error rate should be elevated but bounded
        error_rate = this.get_error_rate()
        ASSERT error_rate < 0.5, "Error rate " + error_rate + " too high"
        
        // Restore cache
        this.chaos.restore_service("redis-primary")
        
        // System should recover
        SLEEP(30 seconds)
        ASSERT this.health_check() == "healthy"
    
    TEST cache_partition():
        // Simulate network partition to cache
        this.chaos.partition_network("app-servers", "redis-cluster")
        
        // Verify circuit breaker activates
        SLEEP(10 seconds)
        ASSERT this.circuit_breaker_state() == "open"
        
        // Verify system continues serving (degraded)
        response = this.make_request("/api/users/1")
        ASSERT response.status_code IN [200, 503]  // Either cached or unavailable
        
        this.chaos.heal_network()
```

---

## Cache Security

Beyond CDN poisoning (covered earlier), cache systems have unique security concerns.

### Trust Boundaries and Cache

Staff Engineers explicitly model trust boundaries. A trust boundary is where data or control crosses from a trusted to a less-trusted (or untrusted) domain. Caching amplifies risk at boundaries.

| Boundary | Trusted Side | Untrusted Side | Cache Risk |
|----------|--------------|----------------|------------|
| **CDN edge ↔ User** | CDN serves cached content | User (or attacker) can influence request | Cache poisoning via crafted headers/params |
| **App ↔ Redis** | App servers | Redis (shared infra; other apps may use same cluster) | Key collision, data leakage if keys not namespaced |
| **Region A ↔ Region B** | Local cache | Replicated data from another region | Stale data from replication lag; compliance (e.g., GDPR) |

**Staff principle**: Never cache at a boundary without ensuring the cache key captures all untrusted dimensions. One malicious request must not affect other users.

### Redis Security Checklist

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    REDIS SECURITY CHECKLIST                                 │
│                                                                             │
│   Network Security:                                                         │
│   ☐ Redis not exposed to public internet                                    │
│   ☐ VPC/private network only                                                │
│   ☐ Security groups limit access to app servers only                        │
│   ☐ TLS enabled for data in transit                                         │
│                                                                             │
│   Authentication:                                                           │
│   ☐ AUTH password set (requirepass)                                         │
│   ☐ ACL configured (Redis 6+) for fine-grained permissions                  │
│   ☐ Different credentials per environment                                   │
│   ☐ Credentials rotated regularly                                           │
│                                                                             │
│   Data Protection:                                                          │
│   ☐ No sensitive data in cache keys (visible in logs)                       │
│   ☐ PII cached only when necessary, with short TTL                          │
│   ☐ Encryption at rest enabled (cloud managed Redis)                        │
│   ☐ Data classification applied to cache contents                           │
│                                                                             │
│   Operational:                                                              │
│   ☐ Dangerous commands disabled (KEYS, FLUSHALL, DEBUG)                     │
│   ☐ Monitoring for unusual access patterns                                  │
│   ☐ Audit logs for connection attempts                                      │
│   ☐ Rename-command for sensitive operations                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Secure Redis Configuration

```
# redis.conf security settings

# Bind to private interface only
bind 10.0.0.1 127.0.0.1

# Require authentication
requirepass "$(REDIS_PASSWORD)"

# TLS
tls-port 6379
port 0  # Disable non-TLS port
tls-cert-file /etc/redis/tls/redis.crt
tls-key-file /etc/redis/tls/redis.key
tls-ca-cert-file /etc/redis/tls/ca.crt

# Disable dangerous commands
rename-command KEYS ""
rename-command FLUSHALL ""
rename-command FLUSHDB ""
rename-command DEBUG ""
rename-command CONFIG "CONFIG_a8f3b9c2"  # Rename to obscure name

# ACL (Redis 6+)
user default off  # Disable default user
user app-read on >$(APP_READ_PASSWORD) ~* +get +mget +exists
user app-write on >$(APP_WRITE_PASSWORD) ~* +set +setex +del +expire
user admin on >$(ADMIN_PASSWORD) ~* +@all
```

### Data Classification in Cache

```
CLASS SecureCacheService:
    // Cache service with data classification.
    // Different handling for different sensitivity levels.
    
    // Data classification
    CONSTANT SENSITIVE_FIELDS = ["password", "ssn", "credit_card", "api_key"]
    CONSTANT PII_FIELDS = ["email", "phone", "address", "name"]
    
    FUNCTION cache_user(user_id, user_data):
        // Never cache sensitive data
        safe_data = {}
        FOR EACH (key, value) IN user_data:
            IF key NOT IN SENSITIVE_FIELDS:
                safe_data[key] = value
        
        // Hash PII in cache keys (not values)
        cache_key = this.safe_key("user:" + user_id)
        
        // Short TTL for PII-containing data
        has_pii = ANY key IN user_data WHERE key IN PII_FIELDS
        ttl = 5 minutes IF has_pii ELSE 1 hour
        
        this.cache.SET(cache_key, serialize(safe_data), TTL = ttl)
        
        // Log what was cached (without actual values)
        log.info("Cached user " + user_id + ", fields: " + KEYS(safe_data))
    
    FUNCTION safe_key(key):
        // Ensure no sensitive data in cache keys
        // Keys are visible in logs, monitoring
        FOR EACH sensitive IN SENSITIVE_FIELDS:
            IF sensitive IN lowercase(key):
                THROW ValueError("Sensitive data in cache key: " + key)
        RETURN key
```

### Compliance and Cached Data

**Staff Engineer Insight**: Caching crosses regulatory boundaries. Regulators care where data lives, how long it persists, and whether it can be audited. Staff Engineers reason about compliance *before* caching, not after an audit finding.

| Compliance Consideration | Cache Impact | L6 Approach |
|-------------------------|--------------|-------------|
| **Data residency** | CDN and Redis may replicate data across regions. EU user data cached in US edge violates GDPR. | Cache only in regions where origin data is permitted. Use regional cache pools; never cache PII at global CDN edge. |
| **Retention** | TTL determines how long data persists. Long TTLs may exceed retention limits. | Align TTL with retention policy. Financial data: short TTL or no cache. Audit logs: never cache. |
| **Right to erasure** | Cached data survives deletion requests. User requests account deletion; cache still serves profile for TTL duration. | Implement purge-on-delete: deletion must invalidate all cache keys for that entity. Synchronous invalidation for compliance-critical data. |
| **Audit trail** | Caches are ephemeral; no built-in audit log. Regulators may require evidence of who accessed what. | Don't cache audit-sensitive data. For cached data, document: what is cached, TTL, invalidation path. Log cache purges for compliance. |
| **Encryption** | Data at rest in Redis, in transit to CDN. | Encryption at rest (managed Redis). TLS for all cache connections. CDN over HTTPS. |

**Concrete example**: A healthcare application caches patient lookup results. Regulatory frameworks require: data stays in authorized regions, access is auditable, deletion is immediate. Staff approach: (1) Regional Redis only, no cross-region replication for patient data. (2) Short TTL (5 minutes) with invalidation on record update or deletion. (3) No caching of audit logs or access records. (4) Runbook for emergency purge documented for compliance reviews.

**One-liner**: "Cache must not extend the blast radius of a compliance violation. If you can't purge it on demand, don't cache it."

---

## Rate Limiter Caching Example

Rate limiting is a critical use case for caching that differs from typical read caching.

### Requirements

- Limit each API client to 1000 requests per minute
- Must be accurate (no over-granting)
- Must be fast (< 1ms overhead per request)
- Must work across multiple app servers

### Implementation with Redis

```
CLASS SlidingWindowRateLimiter:
    // Sliding window rate limiter using sorted sets.
    // More accurate than fixed windows, more efficient than true sliding window.
    
    CONSTRUCTOR(cache_client, requests_per_minute = 1000):
        this.cache = cache_client
        this.limit = requests_per_minute
        this.window_seconds = 60
    
    FUNCTION is_allowed(client_id):
        // Returns (allowed, info) where info includes remaining quota.
        key = "ratelimit:" + client_id
        now = current_time()
        window_start = now - this.window_seconds
        
        // Atomic operation - remove old entries and count
        ATOMIC_SCRIPT:
            cache.SORTED_SET_REMOVE_BY_SCORE(key, MIN, window_start)
            count = cache.SORTED_SET_COUNT(key)
            
            IF count < limit:
                // Add this request
                cache.SORTED_SET_ADD(key, now, unique_id())
                cache.EXPIRE(key, window_seconds)
                RETURN {allowed: TRUE, remaining: limit - count - 1}
            ELSE:
                // Over limit - find when oldest entry expires
                oldest = cache.SORTED_SET_GET_FIRST(key)
                retry_after = oldest.score + window_seconds - now
                RETURN {allowed: FALSE, remaining: 0, retry_after: retry_after}
        
        RETURN result

// Usage in API middleware
MIDDLEWARE rate_limit_middleware(request, next):
    client_id = get_client_id(request)  // API key or IP
    
    allowed, info = rate_limiter.is_allowed(client_id)
    
    IF NOT allowed:
        RETURN Response(
            status = 429,
            body = {error: "Rate limit exceeded"},
            headers = {
                "X-RateLimit-Limit": info.limit,
                "X-RateLimit-Remaining": "0",
                "Retry-After": info.retry_after
            }
        )
    
    response = next(request)
    response.headers["X-RateLimit-Limit"] = info.limit
    response.headers["X-RateLimit-Remaining"] = info.remaining
    
    RETURN response
```

### Failure Handling for Rate Limiting

**Critical question**: What happens when Redis is unavailable?

```
CLASS ResilientRateLimiter:
    // Rate limiter with fallback behavior when cache fails.
    
    FUNCTION is_allowed(client_id):
        TRY:
            RETURN this._check_cache(client_id)
        CATCH CacheError:
            RETURN this._fallback_behavior(client_id)
    
    FUNCTION _fallback_behavior(client_id):
        // When cache fails, what do we do?
        //
        // Options:
        // 1. Allow all (open fail): Risky, enables abuse
        // 2. Deny all (closed fail): Safe but bad UX
        // 3. Local in-memory limit: Inaccurate but functional
        // 4. Probabilistic allow: Statistical rate limiting
        
        // Option 3: Local fallback (our choice)
        IF client_id NOT IN this.local_limits:
            this.local_limits[client_id] = {
                count: 0,
                window_start: current_time()
            }
        
        limit_info = this.local_limits[client_id]
        
        // Reset window if expired
        IF current_time() - limit_info.window_start > 60 seconds:
            limit_info.count = 0
            limit_info.window_start = current_time()
        
        // More conservative limit when in fallback mode
        // (each server limits independently, so use limit/server_count)
        local_limit = this.limit / this.expected_server_count
        
        IF limit_info.count < local_limit:
            limit_info.count = limit_info.count + 1
            RETURN TRUE, {remaining: local_limit - limit_info.count, fallback: TRUE}
        ELSE:
            RETURN FALSE, {remaining: 0, retry_after: 60, fallback: TRUE}
```

---

## Negative Caching (Caching "Not Found")

A subtle but critical caching pattern: what happens when users request data that doesn't exist?

### The Problem

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    THE NEGATIVE CACHE PROBLEM                               │
│                                                                             │
│   Scenario: User profile lookup for non-existent user                       │
│                                                                             │
│   Without negative caching:                                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Request 1: GET user:999999 → Cache MISS → DB query → NOT FOUND     │   │
│   │  Request 2: GET user:999999 → Cache MISS → DB query → NOT FOUND     │   │
│   │  Request 3: GET user:999999 → Cache MISS → DB query → NOT FOUND     │   │
│   │  ...                                                                │   │
│   │  Request N: Every request hits database                             │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Attack vector: Malicious user requests random IDs                         │
│   • 100K requests/sec for non-existent users                                │
│   • 0% cache hit rate (nothing to cache!)                                   │
│   • Database overwhelmed                                                    │
│                                                                             │
│   This is a Cache Penetration Attack                                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Solution: Cache the Absence

```
FUNCTION get_user_with_negative_cache(user_id):
    cache_key = "user:" + user_id
    
    // Check cache
    cached = cache.GET(cache_key)
    
    IF cached == "NULL_MARKER":
        // We cached that this user doesn't exist
        metrics.increment("cache.negative_hit")
        RETURN NULL
    
    IF cached EXISTS:
        metrics.increment("cache.hit")
        RETURN deserialize(cached)
    
    // Cache miss - query database
    user = database.get_user(user_id)
    
    IF user IS NULL:
        // User doesn't exist - cache this fact
        // Short TTL to handle eventual creation
        cache.SET(cache_key, "NULL_MARKER", TTL = 5 minutes)
        metrics.increment("cache.negative_miss")
        RETURN NULL
    ELSE:
        // User exists - cache normally
        cache.SET(cache_key, serialize(user), TTL = 1 hour)
        metrics.increment("cache.miss")
        RETURN user
```

### Negative Caching Considerations

| Aspect | Recommendation | Rationale |
|--------|----------------|-----------|
| TTL for null values | Short (1-5 min) | Data might be created soon |
| Marker value | Distinct sentinel | Must distinguish from empty data |
| Invalidation | On create, not just update | New record should clear null cache |
| Memory impact | Monitor null key count | Can grow unbounded under attack |

### Bloom Filter Alternative

For very large key spaces, use a Bloom filter to quickly reject non-existent keys:

```
CLASS BloomFilterCache:
    // Bloom filter: probabilistic "definitely not" or "maybe exists"
    // False positives possible, false negatives impossible
    
    CONSTRUCTOR():
        this.bloom = NEW BloomFilter(expected_items = 10_000_000, 
                                     false_positive_rate = 0.01)
        this.cache = redis_client
    
    FUNCTION get(key):
        // Fast check: does this key definitely NOT exist?
        IF NOT this.bloom.might_contain(key):
            // Bloom filter says definitely not - skip cache and DB
            metrics.increment("bloom.reject")
            RETURN NULL
        
        // Bloom filter says maybe - check cache
        cached = this.cache.GET(key)
        IF cached EXISTS:
            RETURN cached
        
        // Cache miss - check database
        value = database.get(key)
        IF value EXISTS:
            this.cache.SET(key, value)
        
        RETURN value
    
    FUNCTION set(key, value):
        // Add to bloom filter when data is created
        this.bloom.add(key)
        this.cache.SET(key, value)
        database.set(key, value)
```

**Trade-off**: Bloom filter has ~1% false positive rate, but saves DB queries for 99% of non-existent key requests.

### When to Use Negative Caching

| Scenario | Use Negative Cache? | Rationale |
|----------|---------------------|-----------|
| User profile by ID | Yes | Common to request deleted/non-existent users |
| Product by SKU | Yes | Bots scan for product IDs |
| Session by token | No | Invalid tokens should fail fast (security) |
| Permission check | No | Security-sensitive, don't cache absence |
| Search results | Maybe | Empty results are legitimate |

---

## Distributed Locking with Cache

Caches like Redis are often used for distributed locking. This is powerful but dangerous territory.

### Why Distributed Locks?

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DISTRIBUTED LOCK USE CASES                               │
│                                                                             │
│   1. Prevent duplicate processing                                           │
│      • Only one server processes a webhook                                  │
│      • Only one worker runs a scheduled job                                 │
│                                                                             │
│   2. Coordinate cache population                                            │
│      • Only one request fetches on cache miss                               │
│      • Prevent thundering herd                                              │
│                                                                             │
│   3. Rate limiting writes                                                   │
│      • Ensure ordered updates to a resource                                 │
│      • Prevent lost updates                                                 │
│                                                                             │
│   WARNING: Distributed locks are NOT as reliable as local locks             │
│   They can fail in subtle ways - understand the failure modes               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Basic Lock Pattern

```
FUNCTION acquire_lock(lock_name, ttl_seconds):
    lock_key = "lock:" + lock_name
    lock_value = generate_unique_id()  // Used to ensure we only release our own lock
    
    // SET NX = only set if not exists (atomic)
    acquired = cache.SET(lock_key, lock_value, IF_NOT_EXISTS = TRUE, TTL = ttl_seconds)
    
    IF acquired:
        RETURN lock_value  // Return token for release
    ELSE:
        RETURN NULL  // Lock held by someone else

FUNCTION release_lock(lock_name, lock_value):
    lock_key = "lock:" + lock_name
    
    // Only release if we own the lock (atomic check-and-delete)
    ATOMIC_SCRIPT:
        current_value = cache.GET(lock_key)
        IF current_value == lock_value:
            cache.DELETE(lock_key)
            RETURN TRUE
        ELSE:
            RETURN FALSE  // Lock was taken by someone else

FUNCTION with_lock(lock_name, ttl_seconds, work_function):
    lock_value = acquire_lock(lock_name, ttl_seconds)
    
    IF lock_value IS NULL:
        RETURN {success: FALSE, reason: "Could not acquire lock"}
    
    TRY:
        result = work_function()
        RETURN {success: TRUE, result: result}
    FINALLY:
        release_lock(lock_name, lock_value)
```

### The Redlock Algorithm

For critical locks, single Redis instance isn't safe enough. Redlock uses multiple independent Redis instances:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    REDLOCK ALGORITHM                                        │
│                                                                             │
│   Setup: 5 independent Redis masters (not replicated)                       │
│                                                                             │
│   To acquire lock:                                                          │
│   1. Get current time T1                                                    │
│   2. Try to acquire lock on all 5 Redis instances sequentially              │
│   3. If lock acquired on majority (3+) within validity time:                │
│      → Lock acquired, validity = original_ttl - (T2 - T1)                   │
│   4. If failed, release lock on all instances                               │
│                                                                             │
│   Why this works:                                                           │
│   • Single Redis failure doesn't break locking                              │
│   • Network partition to minority doesn't grant lock                        │
│   • Clock drift accounted for in validity calculation                       │
│                                                                             │
│   When to use:                                                              │
│   • Critical operations (payment processing, inventory)                     │
│   • When correctness > availability                                         │
│                                                                             │
│   When NOT to use:                                                          │
│   • Cache stampede prevention (basic lock is fine)                          │
│   • Non-critical operations                                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Redlock Implementation

```
CLASS RedlockManager:
    CONSTANT QUORUM = 3
    CONSTANT CLOCK_DRIFT_FACTOR = 0.01
    
    CONSTRUCTOR(redis_instances):
        // 5 independent Redis instances
        this.instances = redis_instances
        ASSERT LENGTH(this.instances) == 5
    
    FUNCTION acquire(resource, ttl_ms):
        lock_value = generate_unique_id()
        start_time = current_time_ms()
        
        // Try to acquire on all instances
        acquired_count = 0
        FOR EACH redis IN this.instances:
            TRY:
                WITH TIMEOUT(ttl_ms / 10):  // Fast timeout per instance
                    IF redis.SET("lock:" + resource, lock_value, 
                                 IF_NOT_EXISTS = TRUE, TTL = ttl_ms):
                        acquired_count = acquired_count + 1
            CATCH TimeoutError, ConnectionError:
                CONTINUE  // Instance unavailable, try next
        
        // Calculate validity time
        elapsed = current_time_ms() - start_time
        drift = ttl_ms * CLOCK_DRIFT_FACTOR
        validity_time = ttl_ms - elapsed - drift
        
        // Check if we got quorum
        IF acquired_count >= QUORUM AND validity_time > 0:
            RETURN {
                acquired: TRUE,
                lock_value: lock_value,
                validity_ms: validity_time
            }
        ELSE:
            // Failed to get quorum - release all locks
            this.release(resource, lock_value)
            RETURN {acquired: FALSE}
    
    FUNCTION release(resource, lock_value):
        FOR EACH redis IN this.instances:
            TRY:
                release_lock_on_instance(redis, resource, lock_value)
            CATCH:
                CONTINUE  // Best effort
```

### Fencing Tokens

Even with Redlock, locks can fail. Use fencing tokens for true safety:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FENCING TOKEN PATTERN                                    │
│                                                                             │
│   Problem: Client A gets lock, pauses (GC), lock expires,                   │
│            Client B gets lock, Client A resumes and writes (corruption!)    │
│                                                                             │
│   Solution: Include monotonically increasing token with lock                │
│                                                                             │
│   Timeline:                                                                 │
│   T1: Client A acquires lock, gets token 33                                 │
│   T2: Client A pauses (GC/network)                                          │
│   T3: Lock expires                                                          │
│   T4: Client B acquires lock, gets token 34                                 │
│   T5: Client B writes with token 34 → accepted                              │
│   T6: Client A resumes, writes with token 33 → REJECTED (token < 34)        │
│                                                                             │
│   The storage system rejects writes with older tokens                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

```
CLASS FencedLockManager:
    FUNCTION acquire_with_fencing(resource, ttl_ms):
        // Atomically get lock and increment token
        ATOMIC_SCRIPT:
            IF cache.SET("lock:" + resource, lock_value, IF_NOT_EXISTS = TRUE):
                token = cache.INCREMENT("fence:" + resource)
                cache.EXPIRE("lock:" + resource, ttl_ms)
                RETURN token
            ELSE:
                RETURN NULL
    
    FUNCTION write_with_fence(resource, token, data):
        // Storage checks token before accepting write
        current_token = storage.get_fence_token(resource)
        
        IF token < current_token:
            THROW StaleTokenError("Token " + token + " < current " + current_token)
        
        storage.set_fence_token(resource, token)
        storage.write(resource, data)
```

### When Distributed Locks Fail

| Failure Mode | What Happens | Mitigation |
|--------------|--------------|------------|
| Redis master fails | Lock state lost on failover | Use Redlock with 5 instances |
| Network partition | Split-brain, dual lock holders | Fencing tokens |
| GC pause / slow client | Lock expires while holding | Shorter TTL + renewal, fencing |
| Clock skew | Inconsistent TTL interpretation | Account for drift in Redlock |
| Deadlock | Two processes waiting for each other | Lock ordering, timeouts |

---

## Serialization Format Trade-offs

How you serialize data for caching significantly impacts performance, memory usage, and debugging.

### Format Comparison

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SERIALIZATION FORMAT COMPARISON                          │
│                                                                             │
│   Example data: User profile with 20 fields, ~500 bytes logical size        │
│                                                                             │
│   Format        │ Size   │ Encode  │ Decode  │ Human    │ Schema            │
│   ────────────────────────────────────────────────────────────────────────  │
│   JSON          │ 650B   │ Fast    │ Fast    │ ✓ Yes    │ No                │
│   MessagePack   │ 450B   │ Faster  │ Faster  │ ✗ No     │ No                │
│   Protocol Buf  │ 350B   │ Fastest │ Fastest │ ✗ No     │ Yes (required)    │
│   Gzip(JSON)    │ 280B   │ Slow    │ Slow    │ ✗ No     │ No                │
│                                                                             │
│   Recommendation by use case:                                               │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Debugging/Development: JSON (human readable)                       │   │
│   │  General production:    MessagePack (good balance)                  │   │
│   │  High performance:      Protocol Buffers (if you have schemas)      │   │
│   │  Large values (>10KB):  Compressed JSON or MessagePack              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Implementation Patterns

```
CLASS CacheSerializer:
    // Pluggable serialization with format detection
    
    CONSTANT FORMAT_JSON = 0x01
    CONSTANT FORMAT_MSGPACK = 0x02
    CONSTANT FORMAT_PROTOBUF = 0x03
    CONSTANT FORMAT_COMPRESSED = 0x80  // Flag bit
    
    FUNCTION serialize(data, format = "auto"):
        // Auto-select format based on size
        IF format == "auto":
            estimated_size = estimate_size(data)
            IF estimated_size < 1000:
                format = "json"  // Small: prioritize debuggability
            ELSE IF estimated_size < 10000:
                format = "msgpack"  // Medium: balance
            ELSE:
                format = "compressed"  // Large: prioritize size
        
        // Serialize
        IF format == "json":
            serialized = json_encode(data)
            header = BYTE(FORMAT_JSON)
        ELSE IF format == "msgpack":
            serialized = msgpack_encode(data)
            header = BYTE(FORMAT_MSGPACK)
        ELSE IF format == "compressed":
            json_data = json_encode(data)
            serialized = gzip_compress(json_data)
            header = BYTE(FORMAT_JSON | FORMAT_COMPRESSED)
        
        // Prepend format header for deserialization
        RETURN header + serialized
    
    FUNCTION deserialize(bytes):
        // Read format header
        header = bytes[0]
        payload = bytes[1:]
        
        is_compressed = (header & FORMAT_COMPRESSED) != 0
        format = header & 0x7F
        
        IF is_compressed:
            payload = gzip_decompress(payload)
        
        IF format == FORMAT_JSON:
            RETURN json_decode(payload)
        ELSE IF format == FORMAT_MSGPACK:
            RETURN msgpack_decode(payload)
        ELSE IF format == FORMAT_PROTOBUF:
            RETURN protobuf_decode(payload)
```

### Schema Evolution with Cached Data

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SCHEMA EVOLUTION IN CACHE                                │
│                                                                             │
│   Problem: You add a new field, but cache has old format                    │
│                                                                             │
│   Old format: {name: "Alice", email: "a@b.com"}                             │
│   New format: {name: "Alice", email: "a@b.com", phone: "555-1234"}          │
│                                                                             │
│   Solutions:                                                                │
│                                                                             │
│   1. VERSIONED KEYS (recommended)                                           │
│      v1:user:123 → old format                                               │
│      v2:user:123 → new format                                               │
│      Bump version, old keys expire naturally                                │
│                                                                             │
│   2. NULLABLE NEW FIELDS                                                    │
│      Code handles missing fields gracefully                                 │
│      phone = cached.phone OR NULL                                           │
│                                                                             │
│   3. CACHE FLUSH                                                            │
│      Clear all on deploy (simple but cold cache)                            │
│                                                                             │
│   Anti-pattern: Breaking changes without version bump                       │
│   Result: Deserialization errors, corrupted data                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Performance Benchmarks

```
// Real-world benchmark: 1M cache operations

BENCHMARK serialization_formats:
    data = generate_user_profile()  // ~500 bytes logical
    
    // JSON
    json_encode_time = 15 microseconds
    json_decode_time = 12 microseconds
    json_size = 650 bytes
    
    // MessagePack
    msgpack_encode_time = 8 microseconds
    msgpack_decode_time = 6 microseconds
    msgpack_size = 450 bytes
    
    // Protocol Buffers
    protobuf_encode_time = 3 microseconds
    protobuf_decode_time = 2 microseconds
    protobuf_size = 350 bytes
    
    // Impact at scale (1M ops/sec):
    //
    // JSON:     15 CPU-seconds/sec for encoding, 650 MB memory
    // MsgPack:  8 CPU-seconds/sec for encoding, 450 MB memory
    // Protobuf: 3 CPU-seconds/sec for encoding, 350 MB memory
    //
    // Savings: Protobuf uses 80% less CPU and 46% less memory than JSON
```

---

## Redis Data Structure Selection

Redis offers multiple data structures. Choosing the right one impacts performance, memory, and functionality.

### Data Structure Decision Tree

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    REDIS DATA STRUCTURE SELECTION                           │
│                                                                             │
│   What are you storing?                                                     │
│   │                                                                         │
│   ├─► Single value (string, number, blob)                                   │
│   │   └─► STRING                                                            │
│   │       Commands: GET, SET, INCR, EXPIRE                                  │
│   │       Use: Caching objects, counters, locks                             │
│   │                                                                         │
│   ├─► Object with fields (need partial access)                              │
│   │   └─► HASH                                                              │
│   │       Commands: HGET, HSET, HMGET, HINCRBY                              │
│   │       Use: User profiles, settings, counters by category                │
│   │                                                                         │
│   ├─► Ordered collection (ranking, time-series)                             │
│   │   └─► SORTED SET (ZSET)                                                 │
│   │       Commands: ZADD, ZRANGE, ZRANK, ZRANGEBYSCORE                      │
│   │       Use: Leaderboards, rate limiting, event timelines                 │
│   │                                                                         │
│   ├─► Unordered unique collection                                           │
│   │   └─► SET                                                               │
│   │       Commands: SADD, SMEMBERS, SISMEMBER, SINTER                       │
│   │       Use: Tags, followers, online users                                │
│   │                                                                         │
│   ├─► Ordered collection (queue, recent items)                              │
│   │   └─► LIST                                                              │
│   │       Commands: LPUSH, RPOP, LRANGE, LTRIM                              │
│   │       Use: Recent activity, job queues, feeds                           │
│   │                                                                         │
│   └─► Approximate counting (unique visitors)                                │
│       └─► HYPERLOGLOG                                                       │
│           Commands: PFADD, PFCOUNT, PFMERGE                                 │
│           Use: Unique visitor counts (0.81% error, 12KB fixed)              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Practical Examples

```
// Example 1: User Profile - HASH vs STRING

// BAD: Storing as STRING
cache.SET("user:123", serialize({
    name: "Alice",
    email: "a@b.com",
    settings: {theme: "dark", lang: "en"},
    stats: {posts: 42, followers: 1000}
}))

// Problem: To update just stats.followers, must:
// 1. GET entire object (network)
// 2. Deserialize (CPU)
// 3. Modify
// 4. Serialize (CPU)
// 5. SET entire object (network)

// GOOD: Storing as HASH
cache.HSET("user:123", {
    name: "Alice",
    email: "a@b.com",
    "settings.theme": "dark",
    "settings.lang": "en",
    "stats.posts": "42",
    "stats.followers": "1000"
})

// Update followers: single command
cache.HINCRBY("user:123", "stats.followers", 1)

// Get just name and email:
cache.HMGET("user:123", ["name", "email"])


// Example 2: Rate Limiter - SORTED SET

CLASS SlidingWindowRateLimiter:
    FUNCTION is_allowed(user_id, limit, window_seconds):
        key = "ratelimit:" + user_id
        now = current_time()
        window_start = now - window_seconds
        
        // Remove old entries, count current, add new - all atomic
        ATOMIC:
            // Remove entries outside window
            cache.ZREMRANGEBYSCORE(key, MIN, window_start)
            
            // Count entries in window
            count = cache.ZCARD(key)
            
            IF count < limit:
                // Add this request
                cache.ZADD(key, now, now + ":" + random())
                cache.EXPIRE(key, window_seconds)
                RETURN TRUE
            ELSE:
                RETURN FALSE


// Example 3: Leaderboard - SORTED SET

CLASS Leaderboard:
    FUNCTION update_score(user_id, score):
        cache.ZADD("leaderboard:global", score, user_id)
    
    FUNCTION get_rank(user_id):
        // 0-indexed rank, ascending order
        rank = cache.ZREVRANK("leaderboard:global", user_id)
        RETURN rank + 1 IF rank IS NOT NULL ELSE NULL
    
    FUNCTION get_top(count):
        // Get top N with scores, descending
        RETURN cache.ZREVRANGE("leaderboard:global", 0, count - 1, WITHSCORES = TRUE)
    
    FUNCTION get_around_user(user_id, count):
        // Get users around this user's rank
        rank = cache.ZREVRANK("leaderboard:global", user_id)
        start = MAX(0, rank - count / 2)
        end = rank + count / 2
        RETURN cache.ZREVRANGE("leaderboard:global", start, end, WITHSCORES = TRUE)


// Example 4: Unique Visitors - HYPERLOGLOG

CLASS UniqueVisitorCounter:
    // Counts unique visitors with 0.81% error, using only 12KB
    
    FUNCTION record_visit(page_id, visitor_id):
        cache.PFADD("visitors:" + page_id + ":" + today(), visitor_id)
    
    FUNCTION get_unique_count(page_id, date):
        RETURN cache.PFCOUNT("visitors:" + page_id + ":" + date)
    
    FUNCTION get_weekly_uniques(page_id):
        // Merge 7 days of HyperLogLogs
        keys = []
        FOR i = 0 TO 6:
            keys.APPEND("visitors:" + page_id + ":" + date_minus_days(i))
        
        // Merge into temporary key
        cache.PFMERGE("temp:weekly:" + page_id, keys)
        RETURN cache.PFCOUNT("temp:weekly:" + page_id)
```

### Memory Efficiency Comparison

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MEMORY USAGE BY DATA STRUCTURE                           │
│                                                                             │
│   Storing 1 million items:                                                  │
│                                                                             │
│   Structure    │ Example Use              │ Memory    │ Notes               │
│   ────────────────────────────────────────────────────────────────────────  │
│   STRING       │ 1M user profiles (1KB)   │ ~1.2 GB   │ Key overhead        │
│   HASH         │ 1M users, 10 fields each │ ~800 MB   │ Ziplist encoding    │
│   SET          │ 1M items per set         │ ~80 MB    │ Intset if integers  │
│   SORTED SET   │ 1M scores                │ ~120 MB   │ Skiplist + hash     │
│   LIST         │ 1M items                 │ ~70 MB    │ Quicklist encoding  │
│   HYPERLOGLOG  │ Count 1M uniques         │ 12 KB     │ Fixed size!         │
│                                                                             │
│   Key insight: HASH with <512 fields uses ziplist (very compact)            │
│   Tune: hash-max-ziplist-entries, hash-max-ziplist-value                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Anti-Patterns

| Anti-Pattern | Problem | Better Approach |
|--------------|---------|-----------------|
| STRING for object with partial updates | Full serialize/deserialize on every change | Use HASH |
| Multiple STRINGs for related data | N network round trips | Use HASH or MGET |
| LIST for random access | O(N) for index access | Use HASH with index keys |
| SET for ranked data | Can't sort or rank | Use SORTED SET |
| SORTED SET for simple counting | Overkill, more memory | Use STRING with INCR |
| Storing huge values (>1MB) | Blocks Redis | Split into chunks or use external storage |

---

## Cache Coherence in Distributed Systems

When you have multiple cache layers or multiple cache nodes, keeping them consistent becomes challenging. This is the cache coherence problem.

### The Problem

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CACHE COHERENCE PROBLEM                                  │
│                                                                             │
│   Scenario: User updates their profile                                      │
│                                                                             │
│   1. Write goes to Server A                                                 │
│   2. Server A updates database                                              │
│   3. Server A invalidates its local cache                                   │
│   4. CDN still has old data                                                 │
│   5. Redis still has old data                                               │
│   6. Server B's local cache still has old data                              │
│                                                                             │
│   Result: User sees different data depending on which server they hit       │
│                                                                             │
│   [Server A]         [Server B]         [CDN Edge NYC]    [CDN Edge London] │
│      ✓ new              ✗ old              ✗ old              ✗ old         │
│                                                                             │
│   This is the cache coherence problem at scale                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Solution 1: Centralized Invalidation

Use a message bus to notify all caches of changes:

```
// When data changes, publish invalidation event
FUNCTION update_user_profile(user_id, data):
    // 1. Update database
    database.update_user(user_id, data)
    
    // 2. Publish invalidation to all caches
    event_bus.publish("cache_invalidation", {
        type: "user_profile",
        id: user_id,
        keys: [
            "user:" + user_id,
            "user:" + user_id + ":profile"
        ],
        cdn_tags: ["user-" + user_id]
    })

// Each cache layer subscribes
FUNCTION handle_invalidation(event):
    // Local cache
    local_cache.delete(event.keys)
    
    // Remote cache
    cache.DELETE(event.keys)
    
    // CDN
    cdn.purge_by_tags(event.cdn_tags)
```

**Trade-off**: Adds latency to writes, requires reliable message delivery, eventual consistency.

### Solution 2: Version-Based Invalidation

Include version in cache keys, increment on write:

```
CLASS VersionedCache:
    FUNCTION get_version(entity_type, entity_id):
        // Get current version from fast store (cache)
        version = cache.GET("version:" + entity_type + ":" + entity_id)
        RETURN version IF version EXISTS ELSE 0
    
    FUNCTION increment_version(entity_type, entity_id):
        // Increment version, invalidating all caches
        RETURN cache.INCREMENT("version:" + entity_type + ":" + entity_id)
    
    FUNCTION get(entity_type, entity_id, fetch_function):
        version = this.get_version(entity_type, entity_id)
        key = entity_type + ":" + entity_id + ":v" + version
        
        cached = cache.GET(key)
        IF cached EXISTS:
            RETURN deserialize(cached)
        
        data = fetch_function()
        cache.SET(key, serialize(data), TTL = 1 hour)
        RETURN data

// On update
FUNCTION update_user(user_id, data):
    database.update_user(user_id, data)
    versioned_cache.increment_version("user", user_id)
    // Old version keys will expire naturally
```

**Trade-off**: Old versions linger until TTL, requires version lookup on every read.

### Solution 3: Lease-Based Caching

Caches must obtain a "lease" before caching, leases are invalidated on write:

```
CLASS LeaseBasedCache:
    // Lease-based caching prevents stale reads during concurrent updates.
    // Based on Memcache lease concept from Facebook's TAO.
    
    FUNCTION get_with_lease(key, fetch_function):
        // Try to get cached value
        cached = cache.GET(key)
        IF cached EXISTS:
            RETURN deserialize(cached)
        
        // Cache miss - try to get lease
        lease_key = "lease:" + key
        lease = cache.SET(lease_key, "1", IF_NOT_EXISTS = TRUE, TTL = 10 seconds)
        
        IF lease:
            // We got the lease - we're responsible for fetching
            TRY:
                data = fetch_function()
                cache.SET(key, serialize(data), TTL = 1 hour)
                RETURN data
            FINALLY:
                cache.DELETE(lease_key)
        ELSE:
            // Someone else is fetching - wait for them
            FOR i = 1 TO 50:  // 5 second max wait
                SLEEP(100 milliseconds)
                cached = cache.GET(key)
                IF cached EXISTS:
                    RETURN deserialize(cached)
            // Timeout - fetch ourselves
            RETURN fetch_function()
    
    FUNCTION invalidate(key):
        // Delete both value and any lease
        cache.DELETE(key, "lease:" + key)
```

---

## Multi-Region Caching

Global applications need caches close to users, but consistency across regions is hard.

### The Challenge

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MULTI-REGION CACHING CHALLENGE                           │
│                                                                             │
│   User in London updates profile                                            │
│   User in Tokyo views same profile                                          │
│                                                                             │
│   ┌─────────────┐                              ┌─────────────┐              │
│   │  London     │                              │  Tokyo      │              │
│   │  ┌───────┐  │     100ms network delay      │  ┌───────┐  │              │
│   │  │ Cache │◄─┼──────────────────────────────┼─►│ Cache │  │              │
│   │  └───────┘  │                              │  └───────┘  │              │
│   │      │      │                              │      │      │              │
│   │      ▼      │                              │      ▼      │              │
│   │  ┌───────┐  │                              │  ┌───────┐  │              │
│   │  │  DB   │◄─┼────── Replication ───────────┼─►│  DB   │  │              │
│   │  └───────┘  │       (100-500ms lag)        │  └───────┘  │              │
│   └─────────────┘                              └─────────────┘              │
│                                                                             │
│   Question: How long until Tokyo sees London's update?                      │
│                                                                             │
│   With local cache + DB replication lag:                                    │
│   • DB replication: 100-500ms                                               │
│   • Cache TTL: could be minutes                                             │
│   • Total delay: potentially minutes                                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Strategy 1: Regional Cache, Global Invalidation

Each region has its own cache, but invalidations are broadcast globally:

```
// Invalidation service
CLASS GlobalInvalidator:
    CONSTRUCTOR(regions):
        this.regions = regions  // ["us-east", "eu-west", "ap-northeast"]
        this.region_caches = {}
        FOR EACH region IN regions:
            this.region_caches[region] = get_cache_for_region(region)
    
    FUNCTION invalidate_globally(keys):
        // Broadcast invalidation to all regions
        tasks = []
        FOR EACH (region, cache_client) IN this.region_caches:
            tasks.APPEND(this._invalidate_region(region, cache_client, keys))
        PARALLEL_EXECUTE(tasks, ignore_exceptions = TRUE)
    
    FUNCTION _invalidate_region(region, cache_client, keys):
        TRY:
            cache_client.DELETE(keys)
            log.info("Invalidated " + LENGTH(keys) + " keys in " + region)
        CATCH Exception AS e:
            log.error("Invalidation failed in " + region + ": " + e)
            // Don't fail the write - invalidation is best-effort
```

**Trade-off**: Invalidations add latency, cross-region network can fail, eventual consistency.

### Strategy 2: Write-Through to Primary, Read from Local

All writes go to primary region, reads prefer local:

```
CLASS MultiRegionCache:
    CONSTRUCTOR(primary_region, local_region):
        this.primary_cache = get_cache_for_region(primary_region)
        this.local_cache = get_cache_for_region(local_region)
        this.is_primary = (primary_region == local_region)
    
    FUNCTION get(key, fetch_function):
        // Always try local first
        cached = this.local_cache.GET(key)
        IF cached EXISTS:
            RETURN deserialize(cached)
        
        // Local miss - fetch and cache
        data = fetch_function()
        this.local_cache.SET(key, serialize(data), TTL = 5 minutes)
        RETURN data
    
    FUNCTION set(key, value, ttl):
        // Write to primary
        this.primary_cache.SET(key, serialize(value), TTL = ttl)
        
        // Also update local if not primary
        IF NOT this.is_primary:
            this.local_cache.SET(key, serialize(value), TTL = MIN(ttl, 60 seconds))
    
    FUNCTION invalidate(key):
        // Invalidate primary
        this.primary_cache.DELETE(key)
        
        // Invalidate local
        this.local_cache.DELETE(key)
```

### Strategy 3: Lease-Based with Region Affinity

Direct writes to the region that "owns" the data:

```
FUNCTION get_owning_region(entity_id):
    // Deterministically map entities to regions
    // Could be based on user's home region, data residency, or hash
    hash_value = hash(entity_id) MOD 100
    IF hash_value < 40:
        RETURN "us-east"
    ELSE IF hash_value < 70:
        RETURN "eu-west"
    ELSE:
        RETURN "ap-northeast"

CLASS RegionAffinityCache:
    FUNCTION write(entity_id, key, value):
        owning_region = get_owning_region(entity_id)
        
        IF owning_region == this.local_region:
            // We own this entity - write locally
            this.local_cache.SET(key, serialize(value), TTL = 1 hour)
        ELSE:
            // Forward to owning region
            this.forward_write(owning_region, key, value)
    
    FUNCTION read(entity_id, key, fetch_function):
        // Try local cache first (may be stale for non-owned entities)
        cached = this.local_cache.GET(key)
        IF cached EXISTS:
            RETURN deserialize(cached)
        
        owning_region = get_owning_region(entity_id)
        IF owning_region == this.local_region:
            // We own this - fetch from our DB
            data = fetch_function()
        ELSE:
            // Fetch from owning region
            data = this.fetch_from_region(owning_region, key)
        
        this.local_cache.SET(key, serialize(data), TTL = 5 minutes)
        RETURN data
```

---

## Cache Cost Optimization

At scale, caching costs can become significant. Staff Engineers must optimize.

### Understanding Cache Costs

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CACHE COST BREAKDOWN                                     │
│                                                                             │
│   Redis/Memcached:                                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Memory: $X per GB per month                                      │   │
│   │  • Compute: $Y per node per month                                   │   │
│   │  • Network: $Z per GB transferred                                   │   │
│   │                                                                     │   │
│   │  Example (AWS ElastiCache):                                         │   │
│   │  • cache.r6g.large (13GB): ~$200/month                              │   │
│   │  • 10-node cluster: $2,000/month                                    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   CDN:                                                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Bandwidth: $0.01-0.10 per GB                                     │   │
│   │  • Requests: $0.01 per 10,000 requests                              │   │
│   │  • Storage: Often included                                          │   │
│   │                                                                     │   │
│   │  Example (10TB/month, 100M requests):                               │   │
│   │  • Bandwidth: $400-1000                                             │   │
│   │  • Requests: $100                                                   │   │
│   │  • Total: $500-1100/month                                           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Optimization 1: Right-Size Your TTLs

Longer TTLs = higher hit rate = lower costs, but staleness increases.

```
FUNCTION analyze_cache_efficiency(cache_name):
    // Analyze if TTL is optimal
    stats = get_cache_stats(cache_name)
    
    hit_rate = stats.hits / (stats.hits + stats.misses)
    avg_ttl = stats.avg_ttl_seconds
    memory_used = stats.memory_mb
    
    // If hit rate is low but memory is high, TTL might be too long
    // (caching items that aren't reused)
    IF hit_rate < 0.7 AND memory_used > 1000:
        PRINT("Consider shorter TTL for " + cache_name)
        PRINT("  Current TTL: " + avg_ttl + "s, Hit rate: " + hit_rate)
    
    // If hit rate is high and memory is low, could increase TTL
    IF hit_rate > 0.95 AND memory_used < 500:
        PRINT("Could increase TTL for " + cache_name + " to improve efficiency")
```

### Optimization 2: Compress Cached Data

```
CLASS CompressedCache:
    CONSTRUCTOR(cache_client, compression_threshold = 1000):
        this.cache = cache_client
        this.threshold = compression_threshold  // Compress if > 1KB
    
    FUNCTION set(key, value, ttl):
        serialized = serialize(value)
        
        IF LENGTH(serialized) > this.threshold:
            // Compress large values
            compressed = compress(serialized, level = 6)
            this.cache.SET("z:" + key, compressed, TTL = ttl)
            
            // Track compression savings
            savings = LENGTH(serialized) - LENGTH(compressed)
            metrics.increment("cache.compression.savings", savings)
        ELSE:
            this.cache.SET(key, serialized, TTL = ttl)
    
    FUNCTION get(key):
        // Try compressed key first
        compressed = this.cache.GET("z:" + key)
        IF compressed EXISTS:
            decompressed = decompress(compressed)
            RETURN deserialize(decompressed)
        
        // Try uncompressed
        value = this.cache.GET(key)
        IF value EXISTS:
            RETURN deserialize(value)
        
        RETURN NULL
```

**Real impact**: Compression can reduce memory usage by 60-80% for JSON data.

### Optimization 3: Tiered Caching

Use cheaper storage for less-accessed data:

```
CLASS TieredCache:
    CONSTRUCTOR():
        this.hot = redis_cache        // Fast, expensive (in-memory)
        this.warm = disk_cache        // Slower, cheaper (local SSD)
        this.hot_threshold = 10       // Items accessed 10+ times go to hot tier
    
    FUNCTION get(key, fetch_function):
        // Check hot tier
        cached = this.hot.GET(key)
        IF cached EXISTS:
            RETURN cached
        
        // Check warm tier
        cached = this.warm.GET(key)
        IF cached EXISTS:
            // Promote to hot if frequently accessed
            access_count = this.increment_access(key)
            IF access_count >= this.hot_threshold:
                this.hot.SET(key, cached)
            RETURN cached
        
        // Fetch and cache in warm tier
        data = fetch_function()
        this.warm.SET(key, data)
        RETURN data
```

### Top 2 Cost Drivers: What Actually Costs Money

**Staff Engineer Insight**: At scale, 80% of cache costs come from 2 sources. Optimize these first.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│         CACHE COST ANALYSIS: TOP 2 DRIVERS (80/20 Rule)                     │
│                                                                             │
│   Example: 100M requests/day, 90% hit rate, 10KB average value size         │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  COST DRIVER #1: MEMORY (60% of total cost)                         │   │
│   │  ────────────────────────────────────────────────────────────────   │   │
│   │  Why it dominates:                                                  │   │
│   │  • Memory is the most expensive component of Redis/ElastiCache      │   │
│   │  • Memory scales linearly with data size                            │   │
│   │  • Can't easily "scale down" memory (unlike CPU)                    │   │
│   │                                                                     │   │
│   │  Cost breakdown:                                                    │   │
│   │  • 100M requests/day × 10% miss rate = 10M cache writes/day         │   │
│   │  • 10M writes × 10KB = 100GB/day written                            │   │
│   │  • With 24h TTL: ~100GB memory needed                               │   │
│   │  • AWS ElastiCache r6g.xlarge (26GB): $400/month                    │   │
│   │  • Need 4 nodes: $1,600/month                                       │   │
│   │                                                                     │   │
│   │  Optimization strategies:                                           │   │
│   │  1. Compress values: 10KB → 3KB = 70% memory reduction              │   │
│   │     → 1 node instead of 4 = $1,200/month savings                    │   │
│   │  2. Shorter TTLs: 24h → 1h = 96% memory reduction                   │   │
│   │     → But increases DB load (trade-off)                             │   │
│   │  3. Evict cold data aggressively: LRU with maxmemory-policy         │   │
│   │  4. Don't cache everything: Only cache hot data (top 20%)           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  COST DRIVER #2: NETWORK BANDWIDTH (20% of total cost)              │   │
│   │  ────────────────────────────────────────────────────────────────   │   │
│   │  Why it matters:                                                    │   │
│   │  • CDN bandwidth costs scale with traffic                           │   │
│   │  • Cross-region cache replication bandwidth                         │   │
│   │  • Data transfer out of cloud (egress costs)                        │   │
│   │                                                                     │   │
│   │  Cost breakdown:                                                    │   │
│   │  • 100M requests/day × 10KB = 1TB/day = 30TB/month                  │   │
│   │  • CDN bandwidth: $0.01-0.10/GB                                     │   │
│   │  • 30TB × $0.05/GB = $1,500/month                                   │   │
│   │  • Cloud egress: $0.09/GB (first 10TB free)                         │   │
│   │  • 20TB × $0.09/GB = $1,800/month                                   │   │
│   │                                                                     │   │
│   │  Optimization strategies:                                           │   │
│   │  1. Higher cache hit rate: 90% → 95% = 50% bandwidth reduction      │   │
│   │     → $750-900/month savings                                        │   │
│   │  2. Compress responses: 10KB → 3KB = 70% bandwidth reduction        │   │
│   │  3. Use regional CDN: Lower egress costs                            │   │
│   │  4. Cache at edge: Reduce origin bandwidth                          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Other costs (20% combined):                                               │
│   • CPU: Usually not a bottleneck, scales well                              │
│   • Storage: Included in memory costs                                       │
│   • Requests: Negligible for Redis, small for CDN                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Cost Scaling Model: How Costs Grow

**Staff Engineer Insight**: Model cost growth explicitly. Is it linear, sub-linear, or exponential?

```
FUNCTION model_cache_costs(traffic_req_per_sec, hit_rate, avg_value_size_kb):
    // Model costs at different scale points
    scale_points = [1, 10, 100, 1000]  // 1×, 10×, 100×, 1000×
    
    costs = []
    
    FOR EACH scale IN scale_points:
        traffic = traffic_req_per_sec * scale
        daily_requests = traffic * 86400  // requests per day
        
        // Memory cost (dominant)
        cache_writes_per_day = daily_requests * (1 - hit_rate)
        memory_needed_gb = (cache_writes_per_day * avg_value_size_kb / 1024 / 1024) * ttl_days
        memory_cost = (memory_needed_gb / 26) * 400  // $400 per 26GB node
        
        // Bandwidth cost
        bandwidth_gb_per_month = (daily_requests * avg_value_size_kb / 1024 / 1024) * 30
        bandwidth_cost = bandwidth_gb_per_month * 0.05  // $0.05/GB CDN
        
        total_cost = memory_cost + bandwidth_cost
        
        costs.append({
            scale: scale + "×",
            traffic_req_per_sec: traffic,
            memory_cost: "$" + memory_cost + "/month",
            bandwidth_cost: "$" + bandwidth_cost + "/month",
            total_cost: "$" + total_cost + "/month",
            cost_per_request: "$" + (total_cost / (daily_requests * 30) * 1000000) + " per 1M requests"
        })
    
    RETURN costs

// Example output:
// Scale | Traffic | Memory Cost | Bandwidth Cost | Total Cost | Cost/1M reqs
// 1×    | 1K/s    | $400        | $150           | $550       | $0.21
// 10×   | 10K/s   | $4,000      | $1,500         | $5,500     | $0.21 (linear)
// 100×  | 100K/s  | $40,000     | $15,000        | $55,000    | $0.21 (linear)
// 1000× | 1M/s    | $400,000    | $150,000       | $550,000   | $0.21 (linear)

// Key insight: Cache costs scale LINEARLY with traffic
// This is why caching is cost-effective: DB costs scale worse (connection pools, etc.)
```

**Cost Scaling Characteristics**:

1. **Memory costs**: Linear with data size (not traffic directly, but data size grows with traffic)
2. **Bandwidth costs**: Linear with traffic volume
3. **CPU costs**: Sub-linear (can handle 2-3× traffic on same CPU)
4. **Total**: Approximately linear with traffic

**When caching becomes expensive**: When hit rate is low (<70%). At 50% hit rate, you're paying for cache AND database.

### Cost Sustainability Over Years

**Staff Engineer Insight**: Cache costs grow with traffic. At L6, you plan for 2–3 year horizons. A cache that costs $5K/month today can become $50K/month at 10× scale. Budget planning must be explicit.

**Multi-year projection framework**:
- **Year 1**: Current traffic × 1.5 (growth buffer). Model cost at this level.
- **Year 2**: Traffic × 2–3 (typical product growth). Model cost; identify when Redis Cluster or CDN tier changes are needed.
- **Year 3**: Traffic × 5 (aggressive growth). Model cost; identify when multi-region or architectural changes are required.

**Concrete example**: A product catalog cache costs $2K/month at 10K req/s. At 2× (20K req/s), cost is ~$4K (linear). At 10× (100K req/s), single Redis node hits limits—Redis Cluster adds ~$8K. Total: $12K/month. At 50× (500K req/s), CDN becomes necessary; CDN adds $5K. Without planning, the team is surprised by a $15K/month bill when they "just" 5×'d.

**Why it matters at L6**: Leadership asks "what will this cost in 2 years?" Staff Engineers have the model. They also know when to push back: "If we're not growing, we don't need to over-provision. Right-size for current + 6 months."

**Trade-off**: Over-provisioning for 3 years wastes budget. Under-provisioning causes incidents during growth. The sweet spot: plan for 12–18 months, re-evaluate quarterly.

---

### Cache and Sustainability

**Staff Engineer Insight**: At L6, cost thinking extends beyond dollars. Sustainability—energy use, carbon footprint, resource efficiency—increasingly influences design decisions. Caching has both positive and negative sustainability implications.

**Positive impact**: Caching reduces database load, which often means fewer database servers, lower energy consumption, and less redundant computation. A 95% cache hit rate means 20× fewer database queries—significant energy savings at scale. CDN edge caching reduces origin traffic and distributes load closer to users, often reducing total network energy.

**Negative impact**: In-memory caches (Redis) consume power 24/7 regardless of hit rate. Over-provisioned cache clusters—"we'll add headroom for Black Friday"—run at 30% utilization the rest of the year. Duplicate cache layers across regions multiply this waste.

**Trade-offs**:
- **Right-size aggressively**: Run cache at 60–70% memory utilization. Add capacity only when forecasts justify it. Avoid "just in case" over-provisioning.
- **Prefer TTL over infinite retention**: Stale data that never expires consumes memory and energy indefinitely. Short TTLs plus eviction keep the working set lean.
- **Measure before optimizing**: Don't add sustainability complexity (tiered caches, cold storage) without data. A simple well-tuned cache often beats a complex "green" design.

**One-liner**: "Right-sized cache reduces total system energy. Over-provisioned cache is waste."

### What Staff Engineers Do NOT Build

**Staff Engineer Insight**: The best optimization is not building unnecessary complexity. Here's what Staff Engineers intentionally avoid:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│         WHAT STAFF ENGINEERS DO NOT BUILD                                   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. DO NOT: Cache Everything                                        │   │
│   │  ────────────────────────────────────────────────────────────────   │   │
│   │  Why: Low hit rate = wasted memory + complexity                     │   │
│   │                                                                     │   │
│   │  Example mistake:                                                   │   │
│   │  • Cache user search queries (unique per user)                      │   │
│   │  • Hit rate: 5% (queries rarely repeated)                           │   │
│   │  • Cost: $2,000/month for cache, saves $200/month in DB             │   │
│   │  • Net: -$1,800/month (losing money)                                │   │
│   │                                                                     │   │
│   │  Staff approach:                                                    │   │
│   │  • Only cache data with >70% hit rate potential                     │   │
│   │  • Measure hit rate BEFORE adding cache                             │   │
│   │  • If hit rate < 50%, don't cache (not worth complexity)            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  2. DO NOT: Over-Engineer Cache Invalidation                        │   │
│   │  ────────────────────────────────────────────────────────────────   │   │
│   │  Why: Complex invalidation is bug-prone and expensive               │   │
│   │                                                                     │   │
│   │  Example mistake:                                                   │   │
│   │  • Build distributed invalidation system with event bus             │   │
│   │  • Complex: 5 services, 3 message queues, eventual consistency      │   │
│   │  • Cost: 2 engineers × 3 months = $120K                             │   │
│   │  • Benefit: 1ms faster cache updates                                │   │
│   │  • ROI: Negative (1ms not worth $120K)                              │   │
│   │                                                                     │   │
│   │  Staff approach:                                                    │   │
│   │  • Start with TTL (simplest)                                        │   │
│   │  • Only add invalidation if staleness causes business problems      │   │
│   │  • Prefer versioned keys over distributed invalidation              │   │
│   │  • Accept 5-minute staleness if it saves 3 months of engineering    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  3. DO NOT: Build Custom Cache Infrastructure                       │   │
│   │  ────────────────────────────────────────────────────────────────   │   │
│   │  Why: Redis/Memcached/CDN exist and are battle-tested               │   │
│   │                                                                     │   │
│   │  Example mistake:                                                   │   │
│   │  • Build custom distributed cache in application code               │   │
│   │  • 6 months of development, ongoing maintenance                     │   │
│   │  • Bugs: Memory leaks, race conditions, consistency issues          │   │
│   │  • Cost: $200K+ engineering time                                    │   │
│   │  • Benefit: None (Redis does this better)                           │   │
│   │                                                                     │   │
│   │  Staff approach:                                                    │   │
│   │  • Use Redis for application cache                                  │   │
│   │  • Use CDN for static/public content                                │   │
│   │  • Use managed services (ElastiCache, Cloud CDN)                    │   │
│   │  • Only build custom if existing solutions don't fit (rare)         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  4. DO NOT: Cache Security-Critical Data                            │   │
│   │  ────────────────────────────────────────────────────────────────   │   │
│   │  Why: Stale security data = security vulnerability                  │   │
│   │                                                                     │   │
│   │  Example mistake:                                                   │   │
│   │  • Cache user permissions with 1-hour TTL                           │   │
│   │  • User's permissions revoked → still cached for 1 hour             │   │
│   │  • User accesses data they shouldn't (security breach)              │   │
│   │  • Cost: Security incident, potential legal liability               │   │
│   │                                                                     │   │
│   │  Staff approach:                                                    │   │
│   │  • Never cache: Permissions, auth tokens, PII                       │   │
│   │  • Cache with immediate invalidation: User profile (non-security)   │   │
│   │  • Accept performance hit for security-critical paths               │   │
│   │  • Use cache for performance, not for security bypass               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  5. DO NOT: Optimize Prematurely                                    │   │
│   │  ────────────────────────────────────────────────────────────────   │   │
│   │  Why: Optimize when you have data, not speculation                  │   │
│   │                                                                     │   │
│   │  Example mistake:                                                   │   │
│   │  • Add Redis cluster for 1K req/s traffic                           │   │
│   │  • Cost: $2,000/month                                               │   │
│   │  • Benefit: None (single Redis node handles 100K req/s)             │   │
│   │  • Over-engineering: 100× more complex than needed                  │   │
│   │                                                                     │   │
│   │  Staff approach:                                                    │   │
│   │  • Start simple: Single Redis node                                  │   │
│   │  • Measure: Hit rate, latency, costs                                │   │
│   │  • Optimize when metrics show bottleneck                            │   │
│   │  • Rule: Don't optimize until you have data proving need            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Decision Framework**: Before adding any cache optimization, ask:

1. **Do we have data?** (hit rate, latency, costs)
2. **Is the problem real?** (not hypothetical)
3. **Is the ROI positive?** (savings > engineering cost)
4. **Can we measure impact?** (before/after metrics)
5. **Is it the simplest solution?** (avoid over-engineering)

If any answer is "no", don't build it.

### Optimization 4: Eviction Policy Tuning

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    EVICTION POLICY COMPARISON                               │
│                                                                             │
│   LRU (Least Recently Used):                                                │
│   • Evicts items not accessed recently                                      │
│   • Good for: Most workloads                                                │
│   • Redis default: allkeys-lru                                              │
│                                                                             │
│   LFU (Least Frequently Used):                                              │
│   • Evicts items accessed least overall                                     │
│   • Good for: When some items are always hot                                │
│   • Redis: allkeys-lfu                                                      │
│                                                                             │
│   TTL (Time-Based):                                                         │
│   • Evicts items by expiration                                              │
│   • Good for: When freshness is the priority                                │
│   • Redis: volatile-ttl                                                     │
│                                                                             │
│   Recommendation:                                                           │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Start with allkeys-lru                                           │   │
│   │  • Switch to allkeys-lfu if you have clear hot/cold patterns        │   │
│   │  • Use volatile-* variants if mixing cached and persistent data     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Observability for Caching Systems

You can't optimize what you can't measure.

### Essential Metrics

```
// Metrics to track for every cache
CACHE_METRICS = {
    // Performance
    hit_rate: "Percentage of requests served from cache",
    miss_rate: "Percentage of requests that miss cache",
    latency_p50: "Median cache operation latency",
    latency_p99: "99th percentile latency",
    
    // Capacity
    memory_used: "Current memory usage",
    memory_max: "Maximum memory available",
    evictions: "Number of items evicted",
    key_count: "Number of keys stored",
    
    // Health
    connections: "Number of active connections",
    replication_lag: "Lag behind primary (if replica)",
    errors: "Number of cache errors",
    
    // Business
    cost_per_hit: "Infrastructure cost per cache hit",
    db_load_reduction: "Percentage of DB load absorbed"
}

// Dashboard example
FUNCTION create_cache_dashboard():
    RETURN {
        panels: [
            {
                title: "Cache Hit Rate",
                query: "rate(cache_hits[5m]) / (rate(cache_hits[5m]) + rate(cache_misses[5m]))",
                threshold: {warning: 0.8, critical: 0.6}
            },
            {
                title: "Cache Latency P99",
                query: "histogram_quantile(0.99, cache_operation_duration_bucket)",
                threshold: {warning: "10ms", critical: "50ms"}
            },
            {
                title: "Memory Utilization",
                query: "cache_memory_used / cache_memory_max",
                threshold: {warning: 0.8, critical: 0.95}
            },
            {
                title: "Eviction Rate",
                query: "rate(cache_evictions[5m])",
                threshold: {warning: 100, critical: 1000}
            }
        ]
    }
```

### Alerting Strategy

```yaml
# Example alerting rules
alerts:
  - name: CacheHitRateLow
    condition: cache_hit_rate < 0.7 for 5m
    severity: warning
    runbook: |
      1. Check if recent deploy changed access patterns
      2. Verify TTLs are appropriate
      3. Check for cache capacity issues
      4. Look for new traffic patterns
  
  - name: CacheLatencyHigh
    condition: cache_latency_p99 > 50ms for 2m
    severity: critical
    runbook: |
      1. Check cache server CPU/memory
      2. Look for slow operations (keys, scan)
      3. Check network latency to cache
      4. Consider if cache is undersized
  
  - name: CacheEvictionSpike
    condition: rate(cache_evictions) > 1000/min for 5m
    severity: warning
    runbook: |
      1. Cache may be undersized for workload
      2. Check if new data is being cached
      3. Verify TTLs aren't too long
      4. Consider adding cache capacity
  
  - name: CacheUnreachable
    condition: cache_connection_errors > 0 for 1m
    severity: critical
    runbook: |
      1. Check cache server health
      2. Verify network connectivity
      3. Check for authentication issues
      4. Prepare for graceful degradation
```

---

## Cache Capacity Planning

Staff Engineers don't wait for caches to run out of memory. They proactively plan capacity based on data, not guesses.

### The Capacity Planning Framework

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CACHE CAPACITY PLANNING FRAMEWORK                        │
│                                                                             │
│   Step 1: MEASURE Current State                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Current memory usage: X GB                                       │   │
│   │  • Current key count: Y million                                     │   │
│   │  • Average value size: Z KB                                         │   │
│   │  • Current hit rate: W%                                             │   │
│   │  • Current QPS: N thousand                                          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Step 2: FORECAST Growth                                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • User growth rate: A% per month                                   │   │
│   │  • Data growth rate: B% per month                                   │   │
│   │  • Feature launches that affect cache: list them                    │   │
│   │  • Seasonal patterns: holiday peaks, etc.                           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Step 3: CALCULATE Future Needs                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  memory_needed = current_memory × (1 + growth_rate) ^ months        │   │
│   │  Add 30% headroom for safety                                        │   │
│   │  Add 20% for burst handling                                         │   │
│   │  Total = memory_needed × 1.5                                        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Step 4: PLAN Scaling Actions                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • When to add nodes (memory utilization > 70%)                     │   │
│   │  • How to add nodes (online resharding vs. maintenance window)      │   │
│   │  • Budget approval process (lead time for procurement)              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Capacity Calculation Example

**Scenario**: E-commerce platform planning for Black Friday

```
FUNCTION calculate_cache_capacity(current_state, forecast):
    // Current state
    current_memory_gb = 50
    current_keys_millions = 10
    current_peak_qps = 100000
    
    // Black Friday forecast
    traffic_multiplier = 5        // 5x normal traffic
    new_products = 500000         // New products for sale
    avg_product_size_kb = 2       // Average cached product size
    
    // Calculate memory for new products
    new_product_memory_gb = (new_products × avg_product_size_kb) / 1024 / 1024
    // = (500000 × 2) / 1024 / 1024 = ~1 GB
    
    // Calculate memory for increased hot set
    // Higher traffic = more items in working set
    hot_set_growth_factor = 1.5   // 50% more items become "hot"
    adjusted_memory = current_memory_gb × hot_set_growth_factor
    // = 50 × 1.5 = 75 GB
    
    // Total needed
    base_memory = adjusted_memory + new_product_memory_gb
    // = 75 + 1 = 76 GB
    
    // Add headroom
    headroom_factor = 1.3         // 30% safety margin
    burst_factor = 1.2            // 20% for traffic bursts
    
    total_needed = base_memory × headroom_factor × burst_factor
    // = 76 × 1.3 × 1.2 = ~119 GB
    
    // Current capacity: 50 GB across 5 nodes
    // Needed: 119 GB
    // Action: Add 7 more nodes (12 total × 10 GB each = 120 GB)
    
    RETURN {
        current_capacity: current_memory_gb,
        needed_capacity: total_needed,
        nodes_to_add: CEILING((total_needed - current_memory_gb) / 10),
        action_deadline: "2 weeks before Black Friday"
    }
```

### Key Capacity Metrics to Track

| Metric | Warning Threshold | Critical Threshold | Action |
|--------|-------------------|--------------------| -------|
| Memory utilization | > 70% | > 85% | Add nodes or increase TTL evictions |
| Key count growth | > 20%/week | > 50%/week | Investigate new caching patterns |
| Eviction rate | > 100/sec | > 1000/sec | Cache is undersized |
| Connection count | > 70% of max | > 90% of max | Add nodes or optimize connections |

### Capacity Planning Cadence

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CAPACITY REVIEW SCHEDULE                                 │
│                                                                             │
│   Weekly:                                                                   │
│   • Review key metrics (memory, hit rate, evictions)                        │
│   • Check for anomalies in growth patterns                                  │
│                                                                             │
│   Monthly:                                                                  │
│   • Update 3-month capacity forecast                                        │
│   • Review cost vs. performance trade-offs                                  │
│   • Adjust TTLs if cache is over/under-utilized                             │
│                                                                             │
│   Quarterly:                                                                │
│   • Full capacity planning review                                           │
│   • Budget planning for next quarter                                        │
│   • Architecture review (right technology? right topology?)                 │
│                                                                             │
│   Before Major Events:                                                      │
│   • Load testing at expected scale                                          │
│   • Pre-provision capacity (can't add nodes during peak)                    │
│   • Runbook review for capacity-related incidents                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Cache Migration Strategies

Migrating caches at scale is one of the riskiest operations a Staff Engineer faces. Data loss is permanent, and performance cliffs can cascade into outages.

### Common Migration Scenarios

| Scenario | Complexity | Risk Level | Key Concern |
|----------|------------|------------|-------------|
| Memcached → Redis | Medium | High | Different APIs, feature differences |
| Single Redis → Redis Cluster | High | Critical | Resharding, multi-key operations break |
| Self-managed → Managed (ElastiCache) | Medium | Medium | Endpoint changes, feature parity |
| Redis version upgrade | Low | Medium | Breaking changes, new defaults |
| Cross-region migration | High | Critical | Data sync, latency changes |

### Migration Pattern 1: Shadow Traffic

Run both old and new cache simultaneously, gradually shifting traffic:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SHADOW TRAFFIC MIGRATION                                 │
│                                                                             │
│   Phase 1: Shadow Writes (1 week)                                           │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  [App] ──write──> [Old Cache] (primary)                             │   │
│   │         └─write──> [New Cache] (shadow, fire-and-forget)            │   │
│   │         ──read───> [Old Cache] only                                 │   │
│   │                                                                     │   │
│   │  Validate: New cache is receiving data correctly                    │   │
│   │  Risk: Low (new cache failures don't affect production)             │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Phase 2: Shadow Reads (1 week)                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  [App] ──read───> [Old Cache] (return this)                         │   │
│   │         └─read───> [New Cache] (compare, log differences)           │   │
│   │                                                                     │   │
│   │  Validate: New cache returns same data as old cache                 │   │
│   │  Track: Consistency rate should be >99.9%                           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Phase 3: Traffic Shift (2-4 weeks)                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Week 1: 10% reads from new cache                                   │   │
│   │  Week 2: 50% reads from new cache                                   │   │
│   │  Week 3: 90% reads from new cache                                   │   │
│   │  Week 4: 100% reads from new cache, writes still dual               │   │
│   │                                                                     │   │
│   │  Monitor: Hit rate, latency, error rate at each step                │   │
│   │  Rollback: Feature flag to instantly revert to old cache            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Phase 4: Cutover (1 week)                                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Stop writes to old cache                                         │   │
│   │  • New cache is now primary                                         │   │
│   │  • Keep old cache running (read fallback) for 1 week                │   │
│   │  • Decommission old cache after bake period                         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Migration Pattern 2: Blue-Green Cache

For cases where shadow traffic isn't possible (different data models):

```
FUNCTION blue_green_cache_migration():
    // Phase 1: Prepare green (new) cache
    green_cache = provision_new_cache_cluster()
    
    // Phase 2: Warm green cache
    // Option A: Bulk load from database
    FOR EACH hot_key IN get_hot_keys_from_analytics():
        data = database.get(hot_key)
        green_cache.SET(hot_key, data, TTL = 1 hour)
    
    // Option B: Real-time mirroring
    start_write_mirroring(blue_cache, green_cache)
    WAIT(24 hours)  // Let cache warm naturally
    
    // Phase 3: Canary traffic to green
    FOR percentage = 1 TO 100 STEP varies:
        set_traffic_split(blue = 100 - percentage, green = percentage)
        
        // Monitor for 1 hour minimum at each step
        WAIT(1 hour)
        
        IF error_rate_increased() OR latency_increased():
            ROLLBACK to blue = 100%
            ALERT("Migration failed at " + percentage + "%, investigating")
            RETURN FAILURE
    
    // Phase 4: Decommission blue
    WAIT(1 week)  // Bake period
    IF no_issues():
        decommission(blue_cache)
        RETURN SUCCESS
```

### Migration Anti-Patterns

| Anti-Pattern | Why It Fails | Better Approach |
|--------------|--------------|-----------------|
| "Big bang" cutover | No rollback if problems | Gradual traffic shift |
| Migrating without warming | Cold cache = database overload | Pre-warm before cutover |
| Ignoring multi-key ops | Redis Cluster breaks MGET across slots | Audit and fix code first |
| Same-time migration across regions | Global outage risk | Region-by-region |
| No rollback plan | Stuck with broken state | Always have instant rollback |

### Real Migration Example: Memcached to Redis

**Context**: 50-node Memcached cluster serving 200K QPS, migrating to Redis Cluster for features (TTL per key, persistence, pub/sub).

```
Migration Timeline (8 weeks):

Week 1-2: Preparation
  • Audit all Memcached client code
  • Identified 23 places using Memcached-specific APIs
  • Created Redis-compatible abstraction layer
  • Set up Redis Cluster in parallel (shadow cluster)

Week 3: Shadow Writes
  • All writes go to both Memcached and Redis
  • Reads still from Memcached
  • Discovered: 3 serialization incompatibilities
  • Fixed and redeployed

Week 4: Shadow Reads + Comparison
  • Read from both, return Memcached, log differences
  • 99.2% consistency (goal: >99.9%)
  • Root cause: TTL precision differences
  • Fixed TTL handling, reached 99.95%

Week 5-6: Traffic Shift
  • Day 1: 1% to Redis → no issues
  • Day 3: 10% to Redis → latency spike (fixed connection pooling)
  • Day 7: 25% to Redis → stable
  • Day 10: 50% to Redis → stable
  • Day 14: 100% to Redis → stable

Week 7: Dual-Write Monitoring
  • All traffic on Redis
  • Memcached still receiving writes (hot standby)
  • Zero production incidents

Week 8: Decommission
  • Stopped writes to Memcached
  • Decommissioned Memcached cluster
  • Migration complete

Total downtime: 0
Rollbacks triggered: 2 (both during shadow phase)
Issues found in production: 0 (all caught in shadow)
```

---

## Rollback & Canary for Cache Changes

Cache configuration changes (TTLs, invalidation logic, key structures) can cause subtle bugs that only appear at scale. Staff Engineers deploy cache changes carefully.

### What Can Go Wrong

| Change Type | Risk | Failure Mode |
|-------------|------|--------------|
| TTL reduction | High | Cache misses spike → database overload |
| TTL increase | Medium | Stale data served longer than acceptable |
| New invalidation logic | Critical | Data inconsistency, security issues |
| Key format change | Critical | Cache miss storm (old keys not found) |
| New cache layer | High | Unexpected interactions, increased latency |

### Canary Deployment for Cache Changes

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CACHE CHANGE CANARY PROCESS                              │
│                                                                             │
│   Example: Changing user profile TTL from 1 hour to 15 minutes              │
│                                                                             │
│   Step 1: Feature Flag Setup                                                │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  cache_config:                                                      │   │
│   │    user_profile_ttl:                                                │   │
│   │      control: 3600      # Current: 1 hour                           │   │
│   │      treatment: 900     # New: 15 minutes                           │   │
│   │    rollout_percentage: 0                                            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Step 2: Gradual Rollout                                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Hour 0:  1% of users get new TTL                                   │   │
│   │  Hour 4:  5% (if metrics stable)                                    │   │
│   │  Hour 12: 25%                                                       │   │
│   │  Day 2:   50%                                                       │   │
│   │  Day 3:   100%                                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Step 3: Metrics to Watch                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Cache hit rate (should decrease, but by how much?)               │   │
│   │  • Database QPS (should increase, but within capacity?)             │   │
│   │  • P99 latency (should not increase significantly)                  │   │
│   │  • Error rate (should not change)                                   │   │
│   │  • User-facing freshness complaints (should decrease)               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Step 4: Rollback Triggers                                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Automatic rollback if:                                             │   │
│   │  • Hit rate drops > 20% vs control                                  │   │
│   │  • Database QPS exceeds 80% capacity                                │   │
│   │  • P99 latency increases > 50%                                      │   │
│   │  • Error rate increases > 0.1%                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Implementation Pattern

```
CLASS CacheConfigWithCanary:
    FUNCTION get_ttl(entity_type, user_id):
        config = feature_flags.get("cache_ttl_" + entity_type)
        
        IF config IS NULL:
            RETURN default_ttls[entity_type]
        
        // Determine if user is in treatment group
        rollout_percentage = config.rollout_percentage
        user_bucket = hash(user_id) MOD 100
        
        IF user_bucket < rollout_percentage:
            // Treatment group - new TTL
            metrics.increment("cache.ttl.treatment", {entity: entity_type})
            RETURN config.treatment
        ELSE:
            // Control group - old TTL
            metrics.increment("cache.ttl.control", {entity: entity_type})
            RETURN config.control
    
    FUNCTION set_with_canary(key, value, entity_type, user_id):
        ttl = this.get_ttl(entity_type, user_id)
        cache.SET(key, value, TTL = ttl)
        
        // Track for analysis
        metrics.histogram("cache.ttl.applied", ttl, {
            entity: entity_type,
            group: get_experiment_group(user_id)
        })
```

### Rollback Strategies by Change Type

| Change | Rollback Strategy | Time to Rollback |
|--------|-------------------|------------------|
| TTL change | Feature flag flip | Instant |
| Invalidation logic | Feature flag + manual purge | Minutes |
| Key format | Dual-read (old + new format) | Instant |
| New cache layer | Circuit breaker bypass | Instant |
| Cache technology | Traffic shift back | Minutes |

---

## Production Incident Examples

Real cache failures teach lessons that theory cannot. These examples are composites of real incidents.

### Incident 1: The Thundering Herd Outage

**What happened**: A social media platform experienced a 45-minute outage during a celebrity's viral post.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    INCIDENT TIMELINE: THUNDERING HERD                       │
│                                                                             │
│   14:00 - Celebrity posts viral content                                     │
│   14:02 - Post goes viral, 10x normal traffic to post endpoint              │
│   14:05 - Redis cluster reaches memory limit, starts evicting               │
│   14:06 - Post content evicted (LRU), immediate cache miss storm            │
│   14:07 - 500K concurrent requests hit PostgreSQL for same post             │
│   14:08 - PostgreSQL connection pool exhausted (max 500 connections)        │
│   14:09 - All database queries timing out                                   │
│   14:10 - Cascading failures: auth, feed, notifications all failing         │
│   14:15 - On-call paged, begins investigation                               │
│   14:25 - Root cause identified: single post overwhelming DB                │
│   14:30 - Mitigation: manually cached viral post with long TTL              │
│   14:35 - Traffic stabilizing                                               │
│   14:45 - Full recovery                                                     │
│                                                                             │
│   Impact: 45 minutes degraded service, ~$500K estimated revenue loss        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Root Causes**:
1. No request coalescing for cache misses
2. No circuit breaker between cache and database
3. Hot content treated same as cold content (same eviction policy)
4. No automatic detection of "viral" content

**Fixes Implemented**:
```
// Fix 1: Request coalescing
FUNCTION get_post_with_coalescing(post_id):
    cached = cache.GET("post:" + post_id)
    IF cached EXISTS:
        RETURN cached
    
    // Only one request fetches, others wait
    lock_key = "lock:post:" + post_id
    IF cache.SET(lock_key, "1", IF_NOT_EXISTS = TRUE, TTL = 5 seconds):
        // We got the lock - fetch and cache
        post = database.get_post(post_id)
        cache.SET("post:" + post_id, post, TTL = 1 hour)
        cache.DELETE(lock_key)
        RETURN post
    ELSE:
        // Someone else is fetching - wait and retry
        WAIT(100 milliseconds)
        RETURN get_post_with_coalescing(post_id)  // Retry

// Fix 2: Hot content detection
FUNCTION cache_post(post_id, post_data):
    // Track access frequency
    access_count = cache.INCREMENT("access:" + post_id)
    
    IF access_count > 1000 per minute:
        // Hot content - cache in dedicated hot tier with longer TTL
        hot_cache.SET("post:" + post_id, post_data, TTL = 24 hours)
    ELSE:
        // Normal content
        cache.SET("post:" + post_id, post_data, TTL = 1 hour)
```

### Incident 2: The Silent Data Corruption

**What happened**: An e-commerce platform served wrong prices for 6 hours before detection.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    INCIDENT TIMELINE: CACHE CORRUPTION                      │
│                                                                             │
│   02:00 - Deployment with new price calculation logic                       │
│   02:05 - New code writes prices to cache in new format                     │
│   02:06 - Old code (on servers still rolling out) reads cache               │
│   02:07 - Old code misinterprets new format: $99.99 read as $9.99           │
│   02:08 - Users see wrong prices, start ordering                            │
│   02:10 - Deployment completes, all servers on new code                     │
│   02:11 - New servers read their own format correctly                       │
│           BUT: Some prices already corrupted in cache with wrong values     │
│   02:15 - Corruption persists (1-hour TTL)                                  │
│   08:00 - Finance team notices revenue anomaly in morning reports           │
│   08:30 - Engineering investigation begins                                  │
│   09:00 - Root cause identified: format incompatibility during rollout      │
│   09:05 - Emergency cache flush                                             │
│   09:10 - Correct prices restored                                           │
│                                                                             │
│   Impact: ~$200K in undercharged orders, customer trust damage              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Root Causes**:
1. Cache format change without versioning
2. Mixed old/new code during rolling deployment
3. No validation of cached data on read
4. No alerting on price anomalies

**Fixes Implemented**:
```
// Fix 1: Versioned cache keys
CONSTANT CACHE_VERSION = "v3"

FUNCTION cache_price(product_id, price_data):
    key = CACHE_VERSION + ":price:" + product_id
    cache.SET(key, serialize(price_data), TTL = 1 hour)
    
    // On version bump, old keys are simply ignored (cache miss)
    // They expire naturally, no corruption possible

// Fix 2: Validation on read
FUNCTION get_price(product_id):
    cached = cache.GET(CACHE_VERSION + ":price:" + product_id)
    
    IF cached EXISTS:
        price = deserialize(cached)
        
        // Sanity checks
        IF price.amount < 0:
            log.error("Invalid cached price: negative amount")
            cache.DELETE(key)
            RETURN fetch_from_database(product_id)
        
        IF price.amount > price.original_amount × 2:
            log.error("Invalid cached price: exceeds 2x original")
            cache.DELETE(key)
            RETURN fetch_from_database(product_id)
        
        RETURN price
    
    RETURN fetch_from_database(product_id)

// Fix 3: Price anomaly alerting
ALERT price_anomaly:
    condition: |
        avg(order_price) < avg(historical_order_price) × 0.5
        for 15 minutes
    severity: critical
    action: page on-call immediately
```

### Incident 3: The Cold Start Cascade

**What happened**: A payment processor's cache restart caused a 2-hour degradation.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    INCIDENT TIMELINE: COLD START CASCADE                    │
│                                                                             │
│   03:00 - Scheduled Redis maintenance (expected 5 min downtime)             │
│   03:05 - Redis back online, completely empty (cold cache)                  │
│   03:06 - 100% cache miss rate, all traffic hitting PostgreSQL              │
│   03:07 - PostgreSQL CPU at 100%, queries slowing                           │
│   03:10 - Query timeouts begin, payment processing failing                  │
│   03:15 - Circuit breaker opens, rejecting new payments                     │
│   03:20 - Attempted fix: scale up PostgreSQL read replicas                  │
│   03:30 - Read replicas online but still overwhelmed (no cache warming)     │
│   03:45 - Decision: rate limit traffic to allow cache to warm               │
│   04:00 - 50% traffic allowed, cache hit rate climbing (now 60%)            │
│   04:30 - 75% traffic, cache hit rate 85%                                   │
│   05:00 - Full traffic, cache hit rate 95%, normal operations               │
│                                                                             │
│   Impact: 2 hours degraded, ~$1M in delayed payments, SLA breach            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Root Causes**:
1. No cache warming before cutover
2. Cold cache traffic not rate limited
3. Maintenance during peak hours (03:00 is peak for global customers)
4. No gradual traffic ramp after cache restart

**Fixes Implemented**:
```
// Fix 1: Pre-maintenance cache warming
FUNCTION prepare_for_maintenance():
    // Export hot keys from current cache
    hot_keys = current_cache.get_hot_keys(limit = 100000)
    
    // Save to persistent storage
    FOR EACH key IN hot_keys:
        value = current_cache.GET(key)
        backup_store.SET(key, value)
    
    RETURN hot_keys.count

FUNCTION restore_after_maintenance():
    // Warm cache from backup before accepting traffic
    keys_restored = 0
    
    FOR EACH (key, value) IN backup_store.scan():
        new_cache.SET(key, value, TTL = 1 hour)
        keys_restored = keys_restored + 1
        
        // Pace restoration to not overwhelm cache
        IF keys_restored MOD 1000 == 0:
            SLEEP(100 milliseconds)
    
    log.info("Restored " + keys_restored + " keys to cache")
    
    // Verify cache is warm enough
    IF cache.GET_HIT_RATE() < 0.5:
        RETURN FALSE  // Don't accept traffic yet
    
    RETURN TRUE

// Fix 2: Traffic ramp after cold start
FUNCTION post_maintenance_traffic_ramp():
    FOR percentage = 10 TO 100 STEP 10:
        load_balancer.set_traffic_percentage(percentage)
        log.info("Traffic at " + percentage + "%")
        
        // Wait for cache to warm at this level
        WAIT(5 minutes)
        
        // Check if we're overwhelming the database
        IF database.cpu_percent() > 70:
            log.warn("Database under pressure, holding at " + percentage + "%")
            WAIT(10 minutes)  // Extra wait
        
        IF cache.hit_rate() < 0.8:
            log.warn("Cache still warming, holding at " + percentage + "%")
            WAIT(5 minutes)
    
    log.info("Traffic ramp complete")
```

### Incident 4: CDN Cache Poisoning (Structured Postmortem Format)

This incident illustrates the full postmortem structure Staff Engineers use: Context → Trigger → Propagation → User impact → Engineer response → Root cause → Design change → Lesson learned.

| Field | Content |
|-------|---------|
| **Context** | E-commerce platform serving product pages globally. CDN caches product HTML at edge. Product pages include user-specific elements (wishlist status, cart count) via JavaScript; base HTML was considered "public." Vary header was `Accept-Language` only. |
| **Trigger** | Attacker sent request with crafted `Accept-Language: en; id=1` (or similar) to fetch product page. Application incorrectly used the `id` parameter to include pricing for product ID 1. Response was cached at CDN. |
| **Propagation** | Next legitimate user with `Accept-Language: en` received cached response—with attacker's product data. Affected users saw wrong product, wrong price, or in worst case, another user's cart preview. Trust boundary violation: CDN treated response as cacheable when it should have been user-scoped. |
| **User impact** | 2,400 users over 90 minutes saw incorrect product data. 12 users reported "seeing someone else's cart." No financial loss (checkout was server-side), but significant trust damage. |
| **Engineer response** | User report at T+45min. On-call checked CDN cache keys → found language-based keys only. Traced request to product endpoint. Emergency purge of affected product paths. Added `Vary: Cookie` for product routes (breaking CDN hit rate short-term). Root cause analysis within 4 hours. |
| **Root cause** | Application returned user-influenced data (from query param) while declaring cacheability via weak Vary. CDN key did not include the attacker-controlled dimension. Multiple teams assumed "product page = cacheable" without auditing which headers influenced response. |
| **Design change** | (1) Audit all CDN-cached endpoints for cache key completeness. (2) Never cache responses influenced by query params unless param is in cache key. (3) Add automated tests: "same path, different params → different cache key." (4) Default to `Cache-Control: private` for product pages until proven safe. |
| **Lesson learned** | CDN caching crosses a trust boundary: once cached, one malicious request can poison many users. Staff-level rule: "If a single header or param can change the response, it must be in the cache key or the response must not be cached." |

**Why this format matters at L6**: Structured postmortems enable organizational learning, consistent incident response, and clear accountability. Interviewers and leadership expect Staff Engineers to produce and teach this format.

### Incident 5: Data Residency Violation (Structured Postmortem Format)

| Field | Content |
|-------|---------|
| **Context** | SaaS platform serving EU customers. User profiles cached in a shared Redis cluster in US region for latency. EU launch was 6 months ago; caching was not revisited for compliance. Legal assumed all EU data stayed in EU per contract. |
| **Trigger** | Customer audit requested data flow documentation. Engineering produced architecture diagram showing Redis (US) in the read path for EU user profiles. |
| **Propagation** | Legal reviewed and identified breach: EU user PII (names, emails) was cached in US region. Cache TTL was 1 hour; replication to Redis replicas meant copies existed in US for up to 1 hour per user. No purge-on-delete for EU users; GDPR deletion requests did not invalidate cache. |
| **User impact** | No direct user-visible impact. Regulatory risk: potential fines, contract breach with EU customers. 12 enterprise customers affected. |
| **Engineer response** | Immediate: partitioned EU user data to EU-only Redis cluster. Added purge-on-delete for EU users in deletion workflows. Short-term: audit of all cached data for residency; documented cache topology per region. |
| **Root cause** | Caching was added for performance without compliance review. No data residency classification in cache design. EU expansion did not trigger architecture review for cached data. |
| **Design change** | (1) Cache design requires compliance sign-off for regulated data. (2) Regional cache pools: EU data in EU Redis only; US data in US. (3) Purge-on-delete for all compliance-sensitive entities. (4) Architecture review checklist includes "Where does cached data live?" |
| **Lesson learned** | Cache extends the blast radius of data. Staff-level rule: "If you can't document where cached data lives and how it's purged, don't cache it." |

---

## Cross-Team Cache Standards

Staff Engineers don't just build caching for their own systems—they establish standards that help the entire organization.

### Why Standards Matter

Without cache standards, every team:
- Invents their own key naming schemes (debugging nightmare)
- Uses different TTL strategies (inconsistent user experience)
- Handles failures differently (unpredictable behavior)
- Monitors different metrics (incomplete visibility)

### Recommended Cache Standards Document

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    COMPANY CACHE STANDARDS (Template)                       │
│                                                                             │
│   1. KEY NAMING CONVENTION                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Format: {version}:{service}:{entity}:{id}:{variant}                │   │
│   │                                                                     │   │
│   │  Examples:                                                          │   │
│   │  • v2:user-service:profile:12345:full                               │   │
│   │  • v1:product-catalog:product:SKU123:summary                        │   │
│   │  • v3:feed-service:feed:user456:page0                               │   │
│   │                                                                     │   │
│   │  Rules:                                                             │   │
│   │  • Always include version prefix                                    │   │
│   │  • Always include service name                                      │   │
│   │  • Never include PII in key names                                   │   │
│   │  • Use colons as separators                                         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   2. TTL GUIDELINES                                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Category          │ Default TTL │ Max TTL │ Notes                  │   │
│   │  ─────────────────────────────────────────────────────────────────  │   │
│   │  User-specific     │ 15 min      │ 1 hour  │ Profile, preferences   │   │
│   │  Session/auth      │ 24 hours    │ 7 days  │ Sliding expiration     │   │
│   │  Content           │ 1 hour      │ 24 hours│ Posts, articles        │   │
│   │  Configuration     │ 5 min       │ 15 min  │ Feature flags          │   │
│   │  Computed/agg      │ 5 min       │ 1 hour  │ Stats, counts          │   │
│   │  Static reference  │ 24 hours    │ 7 days  │ Country codes, etc.    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   3. REQUIRED METRICS (Every Cache Client Must Emit)                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • cache_operation_total{operation, result, service}                │   │
│   │  • cache_operation_duration_seconds{operation, service}             │   │
│   │  • cache_value_size_bytes{entity_type, service}                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   4. FAILURE HANDLING REQUIREMENTS                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • All cache clients MUST have timeouts (default: 100ms)            │   │
│   │  • All cache clients MUST handle connection failures gracefully     │   │
│   │  • Critical paths MUST have circuit breakers                        │   │
│   │  • Cache failures MUST NOT cause request failures (degrade only)    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   5. SHARED CACHE INFRASTRUCTURE                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Production clusters:                                               │   │
│   │  • redis-primary.internal (sessions, auth - high durability)        │   │
│   │  • redis-cache.internal (general caching - ephemeral)               │   │
│   │  • redis-ratelimit.internal (rate limiting - dedicated)             │   │
│   │                                                                     │   │
│   │  Do NOT provision your own Redis without platform team approval     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### When Caching Becomes a Platform Service

**Staff Engineer Insight**: At scale, shared cache infrastructure becomes a platform concern. Staff Engineers recognize the trigger points.

**Decision framework—when to make caching a platform service**:

| Signal | Implication |
|--------|-------------|
| 5+ teams use the same Redis cluster | Platform should own provisioning, scaling, monitoring |
| Cache incidents affect multiple products | Single point of failure; platform owns reliability |
| Teams debate TTL strategies and key formats | Standards needed; platform or central library team owns |
| Cache costs are a significant line item | Platform owns cost attribution and optimization |
| Compliance (GDPR, residency) applies to cached data | Platform owns regional topology and purge-on-delete |

**When to keep caching application-owned**:
- Single team, single product
- Cache is a performance optimization, not critical path
- No shared infrastructure

**Trade-off**: Platform ownership increases consistency and reduces per-team operational burden, but adds process (RFCs, capacity requests). Application ownership is faster to iterate but leads to fragmentation at scale.

**One-liner**: "When three teams share a cache, it's platform. When one team has a cache, it's application."

---

### Ownership Boundaries: Who Owns What

**Staff Engineer Insight**: Unclear ownership causes incidents. Define explicit boundaries for cache infrastructure, cache clients, and cache usage.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│         CACHE OWNERSHIP BOUNDARIES                                          │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  PLATFORM TEAM (Infrastructure Ownership)                           │   │
│   │  ────────────────────────────────────────────────────────────────   │   │
│   │  Owns:                                                              │   │
│   │  • Redis cluster provisioning, scaling, monitoring                  │   │
│   │  • CDN configuration and edge location management                   │   │
│   │  • Cache infrastructure SLAs (uptime, latency)                      │   │
│   │  • Capacity planning for shared cache clusters                      │   │
│   │  • Security: Network isolation, authentication                      │   │
│   │  • Incident response: Cache infrastructure failures                 │   │
│   │                                                                     │   │
│   │  Does NOT own:                                                      │   │
│   │  • What data teams cache (application decision)                     │   │
│   │  • Cache key naming (application decision)                          │   │
│   │  • TTL values (application decision)                                │   │
│   │  • Cache invalidation logic (application decision)                  │   │
│   │                                                                     │   │
│   │  Escalation path:                                                   │   │
│   │  • "Redis cluster is down" → Platform team                          │   │
│   │  • "Cache hit rate is low" → Application team                       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  PLATFORM LIBRARIES TEAM (Client Ownership)                         │   │
│   │  ────────────────────────────────────────────────────────────────   │   │
│   │  Owns:                                                              │   │
│   │  • Standard cache client library                                    │   │
│   │  • Key naming validation                                            │   │
│   │  • Default timeouts, retries, circuit breakers                      │   │
│   │  • Standard metrics and observability                               │   │
│   │  • Documentation and examples                                       │   │
│   │                                                                     │   │
│   │  Does NOT own:                                                      │   │
│   │  • Application-specific cache logic                                 │   │
│   │  • Business logic for cache invalidation                            │   │
│   │  • Cache key design (validates format, not content)                 │   │
│   │                                                                     │   │
│   │  Escalation path:                                                   │   │
│   │  • "Cache client bug" → Libraries team                              │   │
│   │  • "How do I cache X?" → Libraries team (documentation)             │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  APPLICATION TEAMS (Usage Ownership)                                │   │
│   │  ────────────────────────────────────────────────────────────────   │   │
│   │  Owns:                                                              │   │
│   │  • What to cache (data selection)                                   │   │
│   │  • Cache key design (content, not format)                           │   │
│   │  • TTL values (staleness tolerance)                                 │   │
│   │  • Cache invalidation logic (when to invalidate)                    │   │
│   │  • Cache hit rate targets                                           │   │
│   │  • Application-specific cache patterns                              │   │
│   │                                                                     │   │
│   │  Does NOT own:                                                      │   │
│   │  • Cache infrastructure (uses Platform team's clusters)             │   │
│   │  • Cache client implementation (uses Libraries team's client)       │   │
│   │  • Cache infrastructure SLAs (Platform team responsibility)         │   │
│   │                                                                     │   │
│   │  Escalation path:                                                   │   │
│   │  • "My cache hit rate is low" → Application team (optimize usage)   │   │
│   │  • "Cache client doesn't support X" → Libraries team (feature req)  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   SHARED RESPONSIBILITY:                                                    │
│   • Cache capacity planning (Platform provides capacity, Apps forecast)     │
│   • Cost optimization (Platform optimizes infra, Apps optimize usage)       │
│   • Incident response (Platform fixes infra, Apps fix usage bugs)           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Common Ownership Conflicts**:

1. **"Cache is slow"**: 
   - Platform team: "Your keys are too large, optimize your data"
   - Application team: "Your Redis cluster is overloaded, scale it"
   - **Resolution**: Define SLAs. Platform guarantees <5ms p99 for standard-sized keys. Apps guarantee key size <10KB.

2. **"Cache hit rate is low"**:
   - Platform team: "Not our problem, optimize your caching strategy"
   - Application team: "Cache client doesn't support our use case"
   - **Resolution**: Libraries team provides guidance. Apps own hit rate, Libraries provide tools.

3. **"Cache costs are high"**:
   - Platform team: "Apps are caching too much"
   - Application team: "Platform charges too much"
   - **Resolution**: Shared cost model. Platform shows per-team costs. Apps optimize usage.

### Operational Burden: What Running Cache at Scale Actually Costs

**Staff Engineer Insight**: Every cache layer is operational burden. Staff Engineers quantify this before adding it. The 3 AM page is real—cache incidents often surface during traffic spikes (evenings, launches) when the system is under stress.

**What on-call for cache actually involves**:
- **Interpretation load**: Cache metrics (hit rate, latency, evictions) can be misleading. "Hit rate dropped" could mean: cold start, hot key, eviction storm, wrong TTL, or a bug. The on-call engineer must triage quickly.
- **Blast radius decisions**: When cache fails, do we serve stale data, fail closed, or shed load? The runbook must be explicit. Ambiguous runbooks lead to 5-minute debates at 3 AM.
- **Escalation paths**: Cache is often shared. Is it platform infra (their page) or application logic (our page)? Unclear ownership delays resolution.

**Concrete example**: A team added a Redis cache for a high-traffic endpoint. Hit rate was 95%. Six months later, a new feature caused cache key cardinality to explode—10M unique keys. Memory filled, evictions began, hit rate dropped to 50%. The on-call engineer saw "high latency" and "database CPU spike" but didn't immediately connect it to cache. The runbook said "check cache hit rate" but didn't say "if hit rate dropped and key count grew recently, suspect cardinality explosion." The incident lasted 30 minutes longer than it should have.

**Why it matters at L6**: Staff Engineers design runbooks that reduce cognitive load. They include: "If you see X and Y, the likely cause is Z." They define ownership so no one hesitates at 3 AM. They add cache-specific alerts (eviction rate, key count growth) so the signal is clear.

**Trade-off**: More operational preparation (runbooks, alerts, ownership docs) increases upfront cost but reduces incident duration and on-call fatigue. The complexity budget must include operational burden, not just code complexity.

---

### Human Failure Modes: How Teams Fail with Caching

**Staff Engineer Insight**: Most cache incidents are caused by human error, not infrastructure failure. Design systems to prevent common mistakes.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│         HUMAN FAILURE MODES IN CACHING                                      │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  FAILURE MODE #1: Copy-Paste Cache Keys                             │   │
│   │  ────────────────────────────────────────────────────────────────   │   │
│   │  What happens:                                                      │   │
│   │  • Engineer copies cache key from another service                   │   │
│   │  • Forgets to change service name in key                            │   │
│   │  • Two services share same cache key → data corruption              │   │
│   │                                                                     │   │
│   │  Example:                                                           │   │
│   │  Service A: "v1:user-service:profile:123"                           │   │
│   │  Service B: "v1:user-service:profile:123" (copied, forgot to change)│   │
│   │  Result: Service B overwrites Service A's cache                     │   │
│   │                                                                     │   │
│   │  Prevention:                                                        │   │
│   │  • Cache client validates service name matches application name     │   │
│   │  • Code review checklist: "Did you change service name?"            │   │
│   │  • Automated test: Verify cache keys are unique per service         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  FAILURE MODE #2: Infinite TTL                                      │   │
│   │  ────────────────────────────────────────────────────────────────   │   │
│   │  What happens:                                                      │   │
│   │  • Engineer sets TTL = 0 (infinite) for "performance"               │   │
│   │  • Data becomes stale, users see wrong data                         │   │
│   │  • No way to invalidate (no invalidation logic)                     │   │
│   │  • Requires emergency cache purge                                   │   │
│   │                                                                     │   │
│   │  Example:                                                           │   │
│   │  cache.SET("user:123", data, TTL = 0)  // Infinite TTL              │   │
│   │  User updates profile → cache never updates                         │   │
│   │  Users see stale profile for days/weeks                             │   │
│   │                                                                     │   │
│   │  Prevention:                                                        │   │
│   │  • Cache client enforces max TTL (e.g., 7 days)                     │   │
│   │  • Code review: Flag TTL = 0 or TTL > max                           │   │
│   │  • Monitoring: Alert on keys with TTL > threshold                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  FAILURE MODE #3: Cache Stampede During Deploy                      │   │
│   │  ────────────────────────────────────────────────────────────────   │   │
│   │  What happens:                                                      │   │
│   │  • Deploy clears cache (intentional or bug)                         │   │
│   │  • All traffic hits cold cache → 100% miss rate                     │   │
│   │  • Database overloaded, service degrades                            │   │
│   │                                                                     │   │
│   │  Example:                                                           │   │
│   │  Deploy script: redis.FLUSHALL()  // Clears all cache               │   │
│   │  Traffic: 100K req/s → all miss → DB sees 100K req/s                │   │
│   │  Database capacity: 10K req/s → overloaded                          │   │
│   │                                                                     │   │
│   │  Prevention:                                                        │   │
│   │  • Never flush cache in production (use versioned keys instead)     │   │
│   │  • Gradual traffic shift (10% → 50% → 100%)                         │   │
│   │  • Cache warming before traffic ramp                                │   │
│   │  • Circuit breaker on database path                                 │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  FAILURE MODE #4: Wrong Cache for Use Case                          │   │
│   │  ────────────────────────────────────────────────────────────────   │   │
│   │  What happens:                                                      │   │
│   │  • Engineer uses Redis for session storage (fine)                   │   │
│   │  • Later uses same Redis for rate limiting (fine)                   │   │
│   │  • Then uses same Redis for job queue (wrong!)                      │   │
│   │  • Job queue blocks Redis → sessions and rate limits fail           │   │
│   │                                                                     │   │
│   │  Prevention:                                                        │   │
│   │  • Separate Redis clusters per use case (sessions, cache, queues)   │   │
│   │  • Documentation: "Which Redis cluster should I use?"               │   │
│   │  • Code review: Verify Redis cluster matches use case               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  FAILURE MODE #5: No Monitoring                                     │   │
│   │  ────────────────────────────────────────────────────────────────   │   │
│   │  What happens:                                                      │   │
│   │  • Cache hit rate drops from 90% → 50%                              │   │
│   │  • No alerts configured                                             │   │
│   │  • Database costs increase 2×                                       │   │
│   │  • Discovered 2 weeks later in cost review                          │   │
│   │                                                                     │   │
│   │  Prevention:                                                        │   │
│   │  • Required metrics: hit rate, latency, error rate                  │   │
│   │  • Alerts: hit rate < threshold, latency > threshold                │   │
│   │  • Cost alerts: cache costs increase > 20%                          │   │
│   │  • Dashboard: Cache health visible to all teams                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  FAILURE MODE #6: Cache Key Collisions                              │   │
│   │  ────────────────────────────────────────────────────────────────   │   │
│   │  What happens:                                                      │   │
│   │  • Two different data types use same key format                     │   │
│   │  • Key collision → wrong data returned                              │   │
│   │  • Hard to debug (data looks valid, just wrong type)                │   │
│   │                                                                     │   │
│   │  Example:                                                           │   │
│   │  Service A: "user:123" = UserProfile                                │   │
│   │  Service B: "user:123" = UserSettings                               │   │
│   │  Result: Service A gets UserSettings, deserialization fails         │   │
│   │                                                                     │   │
│   │  Prevention:                                                        │   │
│   │  • Enforce key naming standard: "v1:service:entity:id"              │   │
│   │  • Cache client validates key format                                │   │
│   │  • Code review: Verify key uniqueness                               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Prevention Strategy**: Build guardrails into cache client:

```
CLASS StandardCacheClient:
    // ... existing code ...
    
    FUNCTION set(key, value, ttl):
        // Validate TTL
        IF ttl == 0:
            THROW InvalidTTLError("TTL cannot be 0 (infinite). Max: " + MAX_TTL)
        IF ttl > MAX_TTL:
            THROW InvalidTTLError("TTL exceeds maximum: " + MAX_TTL)
        
        // Validate key format
        IF NOT this.validate_key_format(key):
            THROW InvalidKeyError("Key must match format: v{version}:{service}:{entity}:{id}")
        
        // Check for collisions (in development)
        IF ENVIRONMENT == "development":
            existing = this.cache.GET(key)
            IF existing EXISTS AND NOT this.is_same_type(existing, value):
                log.warning("Potential key collision: " + key)
        
        // Set with monitoring
        this.cache.SET(key, serialize(value), TTL = ttl)
        this.metrics.increment("cache.set", {service: this.service})
    
    FUNCTION validate_key_format(key):
        // Enforce: v{version}:{service}:{entity}:{id}
        RETURN KEY_PATTERN.matches(key) AND 
               key.starts_with("v") AND
               this.service IN key  // Service name must be in key
```

### Building Consensus

Staff Engineers drive adoption through:

1. **Shared libraries**: Build a cache client that enforces standards
2. **Documentation**: Make the right thing easy to find
3. **Code review**: Catch deviations early
4. **Metrics dashboards**: Show value of standards (debugging time saved)
5. **Incident postmortems**: Reference standards violations as root causes
6. **Ownership clarity**: Define who owns what (prevents finger-pointing)
7. **Human failure prevention**: Build guardrails into tools (prevents mistakes)

```
// Shared cache client that enforces standards
CLASS StandardCacheClient:
    CONSTANT KEY_PATTERN = /^v\d+:[a-z-]+:[a-z-]+:.+$/
    CONSTANT MAX_TTL_SECONDS = 604800  // 7 days
    CONSTANT DEFAULT_TIMEOUT_MS = 100
    
    CONSTRUCTOR(service_name, cache_pool):
        this.service = service_name
        this.cache = cache_pool
        this.metrics = Metrics.for_service(service_name)
    
    FUNCTION get(entity_type, entity_id, variant = NULL):
        key = this.build_key(entity_type, entity_id, variant)
        
        start_time = current_time()
        TRY:
            WITH TIMEOUT(DEFAULT_TIMEOUT_MS):
                result = this.cache.GET(key)
            
            this.metrics.record("cache_operation", {
                operation: "get",
                result: "hit" IF result EXISTS ELSE "miss"
            })
            
            RETURN result
        CATCH TimeoutError:
            this.metrics.record("cache_operation", {
                operation: "get",
                result: "timeout"
            })
            RETURN NULL  // Graceful degradation
        FINALLY:
            this.metrics.histogram("cache_operation_duration", 
                current_time() - start_time)
    
    FUNCTION build_key(entity_type, entity_id, variant):
        key = CACHE_VERSION + ":" + this.service + ":" + 
              entity_type + ":" + entity_id
        
        IF variant IS NOT NULL:
            key = key + ":" + variant
        
        // Validate key format
        IF NOT KEY_PATTERN.matches(key):
            THROW InvalidKeyError("Key does not match standard: " + key)
        
        // Check for PII in key
        IF contains_pii(key):
            THROW SecurityError("PII detected in cache key")
        
        RETURN key
```

---

# Part 9: Interview Calibration

## What Interviewers Probe in Caching Discussions

Interviewers at Staff level probe for *judgment*, not just knowledge. Typical probes:

| Probe | What They're Testing |
|-------|----------------------|
| "What happens when the cache goes down?" | Failure mode reasoning, blast radius |
| "How stale can this data be?" | Consistency model selection |
| "Would you cache this? Why or why not?" | Judgment, not defaulting to "yes" |
| "What's the first bottleneck as you scale?" | Scale and time thinking |
| "How would you debug a user seeing wrong data?" | Observability, trace correlation |
| "Who owns the cache—platform or app team?" | Cross-team impact |
| "How do you explain this design to a non-engineer?" | Leadership communication |
| "We're expanding to EU. How does caching change?" | Compliance, data residency |
| "What's the sustainability impact of this cache design?" | Cost and sustainability thinking |

## What Interviewers Look For in Caching Discussions

| Signal | What Demonstrates It | What's Missing If Absent |
|--------|---------------------|-------------------------|
| **Systems thinking** | Discusses caching as part of overall architecture, not in isolation | Just talks about Redis features |
| **Failure awareness** | Proactively addresses cache failures, cold starts, stampedes | Assumes cache always works |
| **Trade-off articulation** | Explicitly states what we gain and lose with each choice | Makes choices without explaining trade-offs |
| **Consistency reasoning** | Understands and chooses appropriate consistency model | Ignores staleness implications |
| **Operational maturity** | Discusses monitoring, alerting, runbooks | Only covers happy path |
| **Cost awareness** | Considers infrastructure costs in design | Ignores economic factors |

## Example Phrases Staff Engineers Use

**When discussing caching strategy**:
- "Before adding a cache, I need to understand what happens when it fails."
- "The hit rate tells me if caching is worth the operational complexity."
- "I'm choosing eventual consistency here because exact freshness isn't required, and it simplifies the invalidation story."

**When discussing failure modes**:
- "A cache miss storm during cold start could overwhelm the database, so we need cache warming or gradual traffic ramp."
- "If Redis is down, I'd rather serve stale data from a backup than fail completely—for this use case."
- "The blast radius of cache failure is all read traffic hitting the database—we need circuit breakers."

**When discussing trade-offs**:
- "CDN caching gives us global low latency, but we trade instant invalidation for 15-minute staleness."
- "We could cache user permissions, but a security bug where stale permissions grant access is worse than the performance hit of checking every time."
- "I'm deliberately not caching this because the invalidation complexity isn't worth the latency savings."

## Common L5 Mistake: Cache-Everything Thinking

**Scenario**: Design a session management system

**L5 Response**:
> "I'll use Redis to store sessions. We'll cache the session data with a 24-hour TTL. Redis is fast, so every request will be quick. We can use Redis Cluster for high availability."

**What's missing**:
- What happens when Redis fails?
- What's the consistency model? (read-your-writes after password change?)
- What about session invalidation on logout?
- How does "log out from all devices" work?
- What's the security implication of caching auth state?

**L6 Response**:
> "Sessions are critical—users must be able to log out immediately, and security changes like password updates must invalidate sessions system-wide. So I need:
>
> 1. **Redis with persistence** (AOF) since session loss means users are logged out
> 2. **Sentinel for failover**, with the application handling brief unavailability during promotion
> 3. **Session structure**: Store session ID → {user_id, permissions, created_at, last_active}
> 4. **Also maintain user_id → [session_ids]** for "log out everywhere" functionality
> 5. **On password change**: Delete all sessions for that user (security requirement)
> 6. **Fallback if Redis is down**: Fail closed (user must re-authenticate) rather than caching in application memory, because cached auth state is a security risk
> 7. **TTL strategy**: 24-hour sliding expiration, extended on each request
>
> The trade-off is that Redis failure causes users to re-authenticate, but that's better than security bugs from cached auth state."

**Key difference**: L6 thinks about failure modes, security implications, and operational requirements—not just the happy path.

## Common L5 Mistake: Debugging Without a Model

**Scenario**: User reports "I updated my profile but still see old data."

**L5 Response**:
> "Let me check the cache. Maybe we need to invalidate. I'll add a shorter TTL for profiles."

**What's missing**:
- No systematic hypothesis formation (Is it cache? Which layer? Which key?)
- No trace correlation (Can we follow this user's request through CDN → Redis → DB?)
- No consistency model clarity (Is read-your-writes expected? Is it a bug or by design?)
- Jumping to a fix (TTL change) without understanding root cause

**L6 Response**:
> "First, I need to understand the expected behavior. Do we promise read-your-writes for profile updates? If yes, we have a bug. If no, we need to set user expectations.
>
> To debug: (1) Get the user's request ID and trace it through CDN, Redis, and application. Check if the response came from cache or DB. (2) If from cache, check the cache key—did we invalidate on update? (3) Is the writer and reader the same service? (4) Could there be replication lag? (5) Only after we know the path do we change TTL or invalidation logic. Otherwise we're guessing."

**Key difference**: L6 forms a hypothesis, traces the request path, and verifies the consistency model before changing anything. They don't guess; they instrument and observe.

## Signals of Strong Staff Thinking

| Signal | What It Sounds Like |
|--------|---------------------|
| **Leads with constraints** | "The first thing I need to understand is how stale this data can be." |
| **Names trade-offs** | "We're trading instant invalidation for 15-minute staleness—that's acceptable for this use case." |
| **Models blast radius** | "If Redis goes down, 100% of reads hit the DB. Our DB handles 5K QPS; we'd see 100K. We need a circuit breaker." |
| **Rejects complexity** | "I wouldn't cache this. The invalidation story is too complex for the latency gain." |
| **Considers org impact** | "This would affect the shared Redis cluster—we need platform alignment before we add this workload." |

## How to Explain Caching to Leadership

Staff Engineers translate technical decisions into business language:

| Technical Concept | Leadership Framing |
|-------------------|-------------------|
| Cache hit rate | "We're serving 95% of reads from cache—that's 20× cheaper than the database." |
| Cache failure | "If cache goes down, we degrade to slower responses instead of an outage. We've designed for that." |
| CDN cost | "Edge caching cuts our bandwidth costs by 80% for static content." |
| Cache stampede | "We prevent thundering herd: one request repopulates the cache, others wait—no database overload." |

**Principle**: Lead with business impact (cost, reliability, latency), then briefly mention the mechanism. Avoid jargon unless asked.

## How to Teach Caching to Junior Engineers

1. **Start with the "why"**: Protection, cost, latency—in that order. Most juniors think only of speed.
2. **Ask "what happens when it fails?"** early. Build failure-first thinking.
3. **Use the one-liners**: "Cache is a performance optimization, never a correctness requirement."
4. **Pair on a real incident**: Walk through a postmortem together. Structure: Context → Trigger → Propagation → Impact → Fix.
5. **Assign ownership**: "You own the cache hit rate for this service. What would you monitor?"

---

# Quick Reference Card

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CACHING QUICK REFERENCE                                  │
│                                                                             │
│   BEFORE ADDING CACHE:                                                      │
│   □ What happens when cache is empty?                                       │
│   □ What happens when cache is down?                                        │
│   □ How stale can data be?                                                  │
│   □ How do we invalidate?                                                   │
│   □ Is complexity worth it?                                                 │
│   □ What's the blast radius of cache failure?                               │
│                                                                             │
│   TTL GUIDELINES:                                                           │
│   • Seconds: High-frequency changes, some staleness OK                      │
│   • Minutes: Moderate changes, freshness matters                            │
│   • Hours: Rare changes, explicit invalidation                              │
│   • Days: Static content, versioned URLs                                    │
│                                                                             │
│   INVALIDATION CHEAT SHEET:                                                 │
│   • Default: Cache-aside + TTL                                              │
│   • Need fresh for writer: Write-through                                    │
│   • Microservices: Event-driven                                             │
│   • Can't invalidate reliably: Short TTL only                               │
│                                                                             │
│   FAILURE PREVENTION:                                                       │
│   • Stampede: Lock + single fetch                                           │
│   • Thundering herd: Circuit breaker + rate limiting                        │
│   • Cold start: Cache warming + gradual traffic                             │
│   • Stale propagation: Versioned keys + emergency purge                     │
│   • Write failures: Invalidation queue + monitoring                         │
│   • Hot key: Local cache or key splitting for ultra-hot keys               │
│   • Eviction storm: Monitor eviction rate; right-size memory                 │
│                                                                             │
│   LAYER SELECTION:                                                          │
│   • CDN: Public, static, globally accessed                                  │
│   • Redis: Private, dynamic, needs invalidation                             │
│   • Local: Ultra-hot, tiny, can be inconsistent                             │
│                                                                             │
│   KEY DESIGN:                                                               │
│   • Format: {version}:{service}:{entity}:{id}                               │
│   • Hash user input to prevent unbounded keys                               │
│   • Never put sensitive data in key names                                   │
│                                                                             │
│   SECURITY ESSENTIALS:                                                      │
│   • Redis: Auth, TLS, VPC-only, disable dangerous commands                  │
│   • Never cache: passwords, tokens, credit cards                            │
│   • Short TTL for PII                                                       │
│                                                                             │
│   MONITORING ESSENTIALS:                                                    │
│   • Hit rate (target: >90%)                                                 │
│   • P99 latency (<10ms for Redis)                                           │
│   • Memory utilization (<80%)                                               │
│   • Eviction rate (should be stable)                                        │
│   • Write failure rate (should be ~0)                                       │
│                                                                             │
│   CAPACITY PLANNING:                                                        │
│   • Review weekly: memory, hit rate, evictions                              │
│   • Forecast monthly: 3-month projection                                    │
│   • Pre-provision for events: 2 weeks ahead minimum                         │
│   • Headroom: current × 1.3 (safety) × 1.2 (burst) = 1.5x                   │
│                                                                             │
│   MIGRATION CHECKLIST:                                                      │
│   □ Shadow writes first (validate data flow)                                │
│   □ Shadow reads + comparison (validate consistency)                        │
│   □ Gradual traffic shift (1% → 10% → 50% → 100%)                           │
│   □ Rollback plan tested and ready                                          │
│   □ Keep old cache running for bake period                                  │
│                                                                             │
│   CHANGE DEPLOYMENT:                                                        │
│   • TTL changes: canary with feature flag                                   │
│   • Key format changes: versioned keys                                      │
│   • New cache layer: gradual traffic shift                                  │
│   • Always have instant rollback capability                                 │
│                                                                             │
│   NEGATIVE CACHING:                                                         │
│   • Cache "not found" with short TTL (1-5 min)                              │
│   • Use distinct NULL_MARKER value                                          │
│   • Invalidate on CREATE, not just update                                   │
│   • Consider Bloom filter for large key spaces                              │
│                                                                             │
│   DISTRIBUTED LOCKING:                                                      │
│   • Basic: SET NX with TTL                                                  │
│   • Critical: Redlock with 5 instances + quorum                             │
│   • Safety: Fencing tokens for true correctness                             │
│   • Always release with check (only release your own lock)                  │
│                                                                             │
│   SERIALIZATION SELECTION:                                                  │
│   • <1KB: JSON (debuggable)                                                 │
│   • 1-10KB: MessagePack (balanced)                                          │
│   • >10KB: Compressed or Protobuf                                           │
│   • Always version your format                                              │
│                                                                             │
│   REDIS DATA STRUCTURES:                                                    │
│   • Single value: STRING                                                    │
│   • Object with fields: HASH (partial access)                               │
│   • Ranking/time-series: SORTED SET                                         │
│   • Unique collection: SET                                                  │
│   • Queue/recent: LIST                                                      │
│   • Approximate counting: HYPERLOGLOG                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 10: Brainstorming Questions & Exercises

## Section A: Cache Strategy Questions

### Warm-up (5-10 minutes each)

1. **You're building a product catalog with 1 million products. Each product page gets 1000 views/day on average, but the top 100 products get 1 million views/day. How do you design the caching strategy?**

2. **Your cache hit rate is 60%. The team suggests lowering TTL will help freshness. What questions do you ask before making changes?**

3. **A service caches user permissions with a 1-hour TTL. A security audit flags this as a risk. How do you balance security with performance?**

4. **You have a feed that's personalized per user. Another engineer suggests caching the entire feed per user. What's your analysis?**

5. **A junior engineer proposes adding Redis cache to every database read. What's your response, and how do you guide them?**

### Intermediate (15-20 minutes each)

6. **Design a caching strategy for a live sports score application:**
   - Scores update every 10 seconds
   - 50 million concurrent users during major events
   - Users expect near-real-time updates
   - What do you cache? What TTLs? What about consistency?

7. **Your e-commerce platform has a flash sale starting at noon:**
   - 10x normal traffic expected
   - Inventory is limited (100 units)
   - Price changes at exactly noon
   - How do you ensure cache consistency while handling the traffic spike?

8. **You're building a multi-tenant SaaS application:**
   - 10,000 tenants with isolated data
   - Some tenants are 1000x larger than others
   - How do you design cache key structure?
   - How do you prevent one tenant from filling the cache?

9. **A critical production bug causes corrupted user profile data to be cached:**
   - Bug is fixed, database is corrected
   - Cache still has corrupted data for 500,000 users
   - TTL is 24 hours
   - How do you recover without causing an outage?

10. **Your company is expanding from US-only to global:**
    - Adding EU and APAC regions
    - Users should see low latency reads
    - Writes must be strongly consistent
    - Design the multi-region caching strategy

---

## Section B: Failure Scenario Questions

### System Failure Analysis

11. **Redis cluster experiences a network partition. Half your cache is unreachable. How does your application behave, and how should it behave?**

12. **A bug in your invalidation logic causes stale data to be served for 6 hours. How do you detect this, and how do you recover?**

13. **Cache warming after a deploy is overwhelming your database. What's your immediate response, and your long-term fix?**

14. **CDN is serving a cached error page (500 response was cached). How did this happen, and how do you prevent it?**

15. **Your Redis primary fails over to replica, but 30 seconds of writes are lost. What data is affected? How do you detect and recover?**

### Cascading Failure Prevention

16. **Walk through exactly what happens in the first 60 seconds when your cache becomes unavailable. Identify every failure point and propose mitigations.**

17. **Your database can handle 10,000 QPS. Your cache handles 95% of 200,000 QPS. If cache fails, what happens? Design the protection mechanisms.**

18. **A cache stampede is happening right now on production. You're on-call. Walk through your response minute by minute.**

19. **Post-incident: Your cache was down for 10 minutes. Traffic during that time was 5x database capacity. Design a system that survives this.**

20. **Your CDN provider has a global outage. All traffic is hitting your origin. What happens, and what should your runbook say?**

---

## Section C: Trade-off Questions

### Making Hard Choices

21. **You can either cache at the CDN (cheap, 15-minute TTL) or Redis (expensive, instant invalidation). The data changes every 5 minutes. Which do you choose?**

22. **The business wants real-time inventory counts. Engineering wants to cache for performance. How do you navigate this?**

23. **You're adding caching to a legacy system with no cache invalidation hooks. What's your strategy?**

24. **A microservice doesn't own its data—it calls another service. Should it cache those responses? What are the risks?**

25. **You can afford either 100GB of Redis OR 10TB of CDN. Traffic is 70% dynamic (personalized), 30% static. How do you allocate?**

### Cost vs Performance vs Consistency

26. **Your current cache costs $50K/month. Finance asks you to cut it by 50%. What do you sacrifice, and what are the implications?**

27. **Two teams are arguing:**
    - Team A: "Cache everything with 1-hour TTL for performance"
    - Team B: "No caching, data must be fresh"
    - You're the Staff Engineer mediating. What's your framework for resolution?

28. **A customer reports they changed their email but still see the old one. Investigation shows cache is working correctly (5-minute TTL). How do you handle this?**

29. **Your cache hit rate is 99%, but user complaints about stale data are increasing. What's happening, and how do you investigate?**

30. **You can implement either read-your-writes consistency OR 50% cost reduction. The business values both. How do you decide?**

---

## Section D: Design Exercises

### Exercise 1: Cache Strategy That Survives Outage (90 minutes)

**Scenario:**

You are designing the caching layer for a high-traffic e-commerce platform:

- **Traffic**: 500,000 requests/minute during peak hours
- **Product catalog**: 2 million products
- **User sessions**: 10 million active sessions
- **Workload distribution**:
  - 60% product page views
  - 25% search queries
  - 10% cart operations
  - 5% checkout/payment

Currently, the system uses a single Redis cluster that handles:
- Product data caching (2-hour TTL)
- User session storage (24-hour TTL)
- Search result caching (15-minute TTL)
- Shopping cart state (persistent until checkout)

**The Problem:**

Last month, a Redis cluster failure caused a 4-hour outage:
1. Redis became unreachable due to network issues
2. All traffic hit the database
3. Database connection pool exhausted in 30 seconds
4. Database crashed under load
5. Full outage until Redis was restored and database recovered

**Your Task:**

Design a caching architecture that:

1. **Survives complete Redis failure** without full outage
2. **Degrades gracefully** under partial failure
3. **Recovers automatically** when cache is restored
4. **Maintains consistency** for critical data (cart, checkout)
5. **Provides observability** into cache health

**Deliverables:**

1. **Architecture Diagram**
   - Show all caching layers
   - Mark which components are cache vs. persistent storage
   - Show failover paths

2. **Data Classification Matrix**

   | Data Type | Cache Layer | TTL | Invalidation | If Cache Unavailable | Consistency Req |
   |-----------|-------------|-----|--------------|---------------------|-----------------|
   | Product catalog | ? | ? | ? | ? | ? |
   | User session | ? | ? | ? | ? | ? |
   | Shopping cart | ? | ? | ? | ? | ? |
   | Search results | ? | ? | ? | ? | ? |
   | Inventory counts | ? | ? | ? | ? | ? |

3. **Failure Handling Matrix**

   | Failure Scenario | Impact | Mitigation | Recovery Time |
   |-----------------|--------|------------|---------------|
   | Redis primary down | ? | ? | ? |
   | Redis cluster partition | ? | ? | ? |
   | Full Redis outage | ? | ? | ? |
   | CDN outage | ? | ? | ? |
   | Database overload | ? | ? | ? |

4. **Degradation Modes**
   
   For each mode, specify what functionality is available:
   - Normal operation
   - Cache degraded (elevated miss rate)
   - Cache unavailable
   - Database stressed

5. **On-Call Runbook**
   
   Write the response procedure for:
   - "Redis cluster unreachable" alert
   - "Cache hit rate < 50%" alert
   - "Database connection pool saturated" alert

**Evaluation Criteria:**

| Criterion | Weight | What We're Looking For |
|-----------|--------|----------------------|
| Resilience | 30% | Can the system survive component failures? |
| Graceful degradation | 25% | Does it fail softly, not catastrophically? |
| Operational clarity | 20% | Is it clear how to respond to incidents? |
| Complexity management | 15% | Is the complexity justified? |
| Trade-off articulation | 10% | Are trade-offs explicit and reasoned? |

**Hints:**

Consider:
- Multiple cache layers (CDN, Redis, in-process)
- Different strategies for different data types
- Circuit breakers and rate limiters
- Cache-aside vs. read-through for different scenarios
- What data MUST be fresh vs. what can be stale
- Separating critical path (checkout) from browsing

**Example Starting Point:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    POSSIBLE ARCHITECTURE                                    │
│                                                                             │
│   [CDN Layer]                                                               │
│       │                                                                     │
│       ├── Static assets (images, CSS, JS)                                   │
│       └── Public product data (for logged-out users)                        │
│                                                                             │
│   [Application Layer]                                                       │
│       │                                                                     │
│       ├── In-process cache (config, feature flags, ultra-hot data)          │
│       │                                                                     │
│       ├── Redis Primary (sessions, carts, personalized data)                │
│       │       └── Sentinel/Cluster for HA                                   │
│       │                                                                     │
│       └── Redis Secondary (product cache, search cache)                     │
│               └── Can be rebuilt from DB                                    │
│                                                                             │
│   [Database Layer]                                                          │
│       │                                                                     │
│       ├── Primary: Sessions, Carts, Orders (critical, consistent)           │
│       └── Read Replicas: Product catalog, Search (can be slightly stale)    │
│                                                                             │
│   Key Insight: Separate caches by criticality and rebuildability            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### Exercise 2: Multi-Region Cache Design (60 minutes)

**Scenario:**

Your social media platform is expanding globally:
- Currently US-only, 50M DAU
- Expanding to EU (GDPR) and APAC
- User profiles, posts, and feeds are the primary data
- Target: <100ms p99 latency for reads in all regions
- Writes can have higher latency but must be durable

**Constraints:**
- GDPR requires EU user data to stay in EU
- Some content is global (public posts)
- Some content is regional (user-specific data)
- Budget: $100K/month for caching infrastructure

**Your Task:**

1. **Design the multi-region cache topology**
   - Where are caches located?
   - What data goes where?
   - How does invalidation work across regions?

2. **Solve the consistency problem**
   - User in EU updates profile
   - User in US views that profile
   - How stale can it be? How do you minimize?

3. **Handle GDPR requirements**
   - EU user data must stay in EU
   - But what about caching at CDN?
   - What about when EU user travels to US?

4. **Design the invalidation flow**
   - Post is created in US
   - Followers are in EU and APAC
   - How do their feeds get updated?

**Deliverables:**
- Architecture diagram showing all regions
- Data flow for read and write operations
- Invalidation sequence diagram
- GDPR compliance strategy

---

### Exercise 3: Cache Migration (45 minutes)

**Scenario:**

You're migrating from Memcached to Redis Cluster:
- 50-node Memcached cluster
- 200K QPS, 80GB data
- Zero-downtime requirement
- 4-week timeline

**Challenges:**
- Different serialization (Memcached uses different client)
- Different key limitations (Redis Cluster has slot restrictions)
- Multi-key operations (MGET) used extensively
- Team has no Redis experience

**Your Task:**

1. **Create the migration plan**
   - Week-by-week breakdown
   - Risk mitigation at each stage
   - Rollback procedures

2. **Identify and solve technical issues**
   - Serialization compatibility
   - Multi-key operation handling
   - Key slot distribution

3. **Design the traffic cutover**
   - How to run both systems?
   - How to validate correctness?
   - How to gradually shift traffic?

4. **Plan for failure**
   - What if Redis performance is worse?
   - What if data corruption is discovered?
   - What's the "abort" criteria?

---

### Exercise 4: Cache Security Audit (30 minutes)

**Scenario:**

Security team has flagged your caching infrastructure for audit:

Current state:
- Redis on port 6379, no auth (internal network)
- Cache keys include user emails for lookup
- Session tokens cached with 7-day TTL
- API responses cached including user PII
- No encryption in transit or at rest

**Your Task:**

1. **Identify all security vulnerabilities**
   - Prioritize by severity
   - Estimate blast radius for each

2. **Create remediation plan**
   - Immediate fixes (this week)
   - Short-term fixes (this month)
   - Long-term improvements (this quarter)

3. **Design secure cache architecture**
   - Authentication and authorization
   - Data classification
   - Key design that doesn't leak information
   - PII handling

4. **Create security monitoring**
   - What to monitor for intrusion?
   - What alerts to create?
   - How to detect data exfiltration?

---

### Exercise 5: Incident Response Simulation (30 minutes)

**Scenario:**

It's 3 AM. You're on-call. These alerts fire simultaneously:

```
CRITICAL: redis-primary CPU 100% for 5 minutes
WARNING:  cache_hit_rate dropped from 95% to 45%
CRITICAL: database_connections at 95% of pool
WARNING:  api_latency_p99 increased from 50ms to 2000ms
```

**Your Task:**

1. **Triage (5 minutes)**
   - What's the root cause?
   - What's the user impact?
   - What's the priority order for investigation?

2. **Immediate Response (10 minutes)**
   - What commands do you run first?
   - Who do you page?
   - What's your hypothesis?

3. **Mitigation (10 minutes)**
   - What do you do to stop the bleeding?
   - How do you prevent cascade failure?
   - What's your communication to stakeholders?

4. **Post-Incident (5 minutes)**
   - What would you investigate tomorrow?
   - What permanent fixes would you propose?
   - How would you prevent recurrence?

---

## Section E: Interview Practice Questions

These questions simulate what you might face in a Staff Engineer interview.

### Question 1: Design Twitter's Home Timeline Cache

**Interviewer prompt:**
"Design the caching strategy for Twitter's home timeline. Users see tweets from people they follow. Assume 500M DAU, average 300 follows per user, 500M tweets per day."

**What they're looking for:**
- Fan-out on read vs. fan-out on write trade-off
- Hot user problem (celebrities with 100M followers)
- Cache consistency when tweets are deleted
- Read-your-writes consistency
- Multi-region considerations

**Time:** 35 minutes

---

### Question 2: Design a Rate Limiter

**Interviewer prompt:**
"Design a distributed rate limiter that limits each API client to 1000 requests per minute. It must work across 100 application servers."

**What they're looking for:**
- Sliding window vs. fixed window trade-off
- Redis vs. local counter approaches
- What happens when Redis is down?
- Accuracy vs. performance trade-off
- Client experience (rate limit headers)

**Time:** 25 minutes

---

### Question 3: Cache Invalidation Problem

**Interviewer prompt:**
"You have a product catalog service with 10M products. Product data is cached in Redis with 1-hour TTL. The business wants instant price updates when prices change. How do you solve this?"

**What they're looking for:**
- Event-driven invalidation
- Pub/sub for cache invalidation
- Version-based cache keys
- Trade-off between complexity and freshness
- CDN considerations

**Time:** 20 minutes

---

### Question 4: Debugging Production Issue

**Interviewer prompt:**
"Users report they're seeing other users' data. You suspect cache poisoning. How do you investigate and fix?"

**What they're looking for:**
- Systematic debugging approach
- Cache key design analysis
- Vary header investigation
- Security implications
- Immediate mitigation vs. root cause fix

**Time:** 20 minutes

---

### Question 5: Cache Cost Optimization

**Interviewer prompt:**
"Your cache infrastructure costs $500K/year. The CFO asks for 40% reduction. Current hit rate is 85%. How do you approach this?"

**What they're looking for:**
- Data-driven analysis first
- TTL optimization opportunities
- Compression strategies
- Tiered caching
- Trade-off articulation (cost vs. performance)

**Time:** 20 minutes

---

## Section F: Self-Assessment Rubric

After completing exercises, evaluate yourself:

| Competency | L5 (Senior) | L6 (Staff) | L7 (Principal) |
|------------|-------------|------------|----------------|
| **Cache selection** | Knows Redis vs. Memcached | Chooses based on failure modes and ops cost | Defines caching strategy for org |
| **Failure thinking** | Handles cache misses | Designs for cold start, stampede, cascade | Prevents failure classes via architecture |
| **Trade-off articulation** | Explains consistency/latency | Quantifies cost/performance/consistency | Frames trade-offs for exec communication |
| **Multi-region** | Understands replication | Designs regional cache strategy | Defines global cache architecture |
| **Security** | Knows to use auth | Designs data classification for cache | Creates security standards for cache |
| **Operations** | Can debug cache issues | Writes runbooks, defines SLOs | Establishes monitoring standards |
| **Cross-team impact** | Works within standards | Creates standards for team | Drives org-wide cache strategy |

---

## Section G: Further Reading & Resources

### Papers
1. "Scaling Memcache at Facebook" - Facebook Engineering
2. "Dynamo: Amazon's Highly Available Key-value Store" - Amazon
3. "TAO: Facebook's Distributed Data Store for the Social Graph"

### Topics to Explore Next
- Write-behind caching with change data capture
- Distributed caching with consistent hashing
- Cache-as-a-service architectures
- Machine learning for cache eviction (LeCaR, etc.)
- Database-integrated caching (MySQL query cache, PostgreSQL pg_prewarm)

---

# Master Review Prompt Check

Use this checklist to verify chapter completeness before release.

## 11-Point Verification

| # | Check | Status |
|---|-------|--------|
| 1 | Judgment & decision-making: Staff-level frameworks and trade-offs articulated | ✓ |
| 2 | Failure & incident thinking: Partial failures, blast radius, cascading failures | ✓ |
| 3 | Scale & time: Growth over years, first bottlenecks, when to add cache | ✓ |
| 4 | Cost & sustainability: Cost drivers, optimization strategies | ✓ |
| 5 | Real-world engineering: Operational burdens, human errors, on-call scenarios | ✓ |
| 6 | Learnability & memorability: Mental models, one-liners, frameworks | ✓ |
| 7 | Data, consistency & correctness: Invariants, consistency models | ✓ |
| 8 | Security & compliance: Trust boundaries, cache poisoning, Redis security | ✓ |
| 9 | Observability & debuggability: Metrics, logs, trace correlation | ✓ |
| 10 | Cross-team & org impact: Standards, ownership boundaries | ✓ |
| 11 | Structured incident: Full format (Context \| Trigger \| Propagation \| User impact \| Engineer response \| Root cause \| Design change \| Lesson learned) | ✓ |

## L6 Dimension Coverage Table (A–J)

| Dimension | Coverage | Where to Find |
|-----------|----------|---------------|
| **A. Judgment & decision-making** | Staff vs Senior table, TTL framework, cache suitability matrix, debugging contrast | Part 1, Part 2, Part 7, Part 9 |
| **B. Failure & incident thinking** | Stampede, thundering herd, cold start, hot key, eviction storms, cascading timeline, blast radius | Part 4, Part 6, Part 8 |
| **C. Scale & time** | First-bottleneck analysis, growth stages, when to add Redis/CDN, cost sustainability over years | Part 6, Part 8 (Observability, Cache Cost Optimization) |
| **D. Cost & sustainability** | Cost breakdown, optimization, tiered caching, cost sustainability over years, cache sustainability (energy, right-sizing) | Part 8 (Cache Cost Optimization, Cache and Sustainability) |
| **E. Real-world engineering** | Human failure modes, operational burden/on-call reality, ownership conflicts | Part 8 (Cross-Team, Human Failure Modes, Operational Burden) |
| **F. Learnability & memorability** | Mental models, one-liners (incl. hot key, eviction storm, platform ownership), teaching tips | Part 7, Part 9 |
| **G. Data, consistency & correctness** | Invariants, consistency models, read-your-writes | Part 1, Part 2 |
| **H. Security & compliance** | Trust boundaries, Redis security, CDN poisoning, compliance and cached data (residency, retention, audit) | Part 3, Part 8 (Cache Security, Compliance and Cached Data) |
| **I. Observability & debuggability** | Trace correlation, metrics, first-bottleneck analysis, when traces don't reveal the answer | Part 8 (Observability) |
| **J. Cross-team & org impact** | Cache standards, ownership boundaries, platform vs app, when caching becomes platform service | Part 8 (Cross-Team Cache Standards) |

---

*End of Volume 4, Part 2: Caching at Scale*