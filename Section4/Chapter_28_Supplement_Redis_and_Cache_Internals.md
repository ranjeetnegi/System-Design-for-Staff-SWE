# Chapter 28 Supplement: Redis & Cache Internals — Persistence, Cluster, Key Design, and Poisoning

---

# Introduction

Chapter 22 provides the Staff-level framework for caching—protection, cost, invalidation strategies, and failure modes. But when the interview dives deeper into implementation details, you need to understand *how* Redis actually works, how cache keys influence hit rates, how cache poisoning emerges, and how specialized systems (time-series, search) differ from general-purpose caches. Video topics 259–266 assume familiarity with these internals. This supplement fills that gap.

These are not academic topics. At Staff level, you're asked to explain *why* a cache key design causes 5% hit rates, *why* cache poisoning persists for hours, *why* Redis Cluster uses hash slots instead of consistent hashing, and *when* to reach for a time-series DB instead of PostgreSQL. This supplement gives you the internals needed to answer those questions with depth and precision.

**The Staff Engineer's Cache Internals Principle**: You don't need to implement Redis from scratch. You do need to understand key design trade-offs, poisoning prevention, persistence semantics, cluster routing, time-series optimization, and inverted indexes—because these drive production behavior, debugging, and architecture decisions.

**How to use this supplement**: Read it alongside Chapter 22. When the main chapter mentions Redis, cache invalidation, or CDN, this supplement provides the "how" and "why." For interview prep, focus on the L5 vs L6 table, the key design patterns, the poisoning prevention checklist, and the Redis Cluster routing flow. For deep dives, work through the ASCII diagrams and the operational guidance sections. The goal is not to memorize configuration parameters but to build intuition—so you can reason about cache internals when the interviewer asks "why" or "what happens when."

---

## Quick Visual: Cache Internals at a Glance

```
┌─────────────────────────────────────────────────────────────────────────────┐
│     CACHE INTERNALS: THE LAYERS THAT MATTER AT STAFF LEVEL                  │
│                                                                             │
│   L5 Framing: "Cache stores key-value pairs; Redis is fast"                  │
│   L6 Framing: "Cache is layered: key design drives hit rate and correctness,│
│                poisoning corrupts data for all readers, persistence trades   │
│                durability for performance, cluster routing determines       │
│                scalability—and each layer has operational implications"     │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  KEY DESIGN (Topic 261):                                            │   │
│   │  • Key = resource + ID + variant params → hit rate & correctness     │   │
│   │  • Bad keys = 0% hit rate or data leakage                            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  CACHE POISONING (Topic 262):                                        │   │
│   │  • Wrong data under a key → all readers see it until TTL              │   │
│   │  • Prevention: validate, sanitize, monitor                           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  REDIS PERSISTENCE (Topic 265):                                       │   │
│   │  • RDB = snapshots, AOF = append log, hybrid = both                  │   │
│   │  • fsync policy = durability vs latency trade-off                    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  REDIS CLUSTER (Topic 266):                                          │   │
│   │  • 16,384 hash slots, MOVED redirects, hash tags for co-location      │   │
│   │  • Smart clients cache slot→node mapping                             │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  TIME-SERIES (Topic 259):                                            │   │
│   │  • Append-only, time-partitioned, Gorilla compression                │   │
│   │  • Different workload than general-purpose cache                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  INVERTED INDEX (Topic 260):                                         │   │
│   │  • Word → document list; posting lists; TF-IDF, BM25                 │   │
│   │  • Elasticsearch/Lucene internals                                    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## L5 vs L6 Cache Internals Thinking

| Scenario | L5 Approach | L6 Approach |
|----------|-------------|-------------|
| **Low cache hit rate** | "Increase TTL" | "Inspect key design. Is timestamp in the key? That makes every request unique = 0% hit rate. Is the key too specific (e.g., full query hash)? Too generic (e.g., user:123) for user-specific content? Right key = resource type + ID + variant parameters that actually affect the response." |
| **Cache poisoning incident** | "Flush the cache" | "Flushing causes stampede. Who poisoned it? App bug? Race? Error response cached? Validate before caching, never cache 5xx, sanitize keys. Targeted invalidation for known bad keys. Monitor for anomalous patterns." |
| **Redis data loss on restart** | "Enable AOF" | "AOF with fsync=always = safe but slow. everysec = up to 1 sec loss. RDB alone = up to N minutes loss (snapshot interval). Hybrid (RDB + AOF since last snapshot) gives fast recovery + minimal loss. Match persistence to data criticality." |
| **Redis Cluster multi-key ops** | "Use pipeline" | "Pipeline doesn't help cross-slot. Keys must be in same slot. Use hash tags: {user:123}:profile and {user:123}:settings both hash on user:123. Enables MGET, transactions, Lua scripts across those keys." |
| **Choosing time-series DB** | "PostgreSQL with timestamp index" | "TS data: append-only, range queries, downsampling. PostgreSQL indexes grow large, range scans costly. Time-series DB: time-partitioned, columnar, Gorilla compression. Use InfluxDB/TimescaleDB when write volume > 10K points/sec or retention > 90 days with aggregation." |
| **Search performance** | "Add Elasticsearch" | "Elasticsearch uses inverted index: term → posting list. TF-IDF/BM25 for ranking. Source of truth must be elsewhere—ES is a search index. Sync pipeline (CDC, batch) is critical. Don't let ES be primary." |

**Key Difference**: L6 engineers connect internal mechanisms to observable symptoms. They know which knob to turn—and which knob turning will cause a new problem elsewhere.

---

# Part 1: Cache Key Design — What to Include (Topic 261)

## The Cache Key: Identity and Determinism

The **cache key** is the identifier for cached data. It determines three things:
1. **Hit rate**: Keys that vary unnecessarily yield lower hit rates.
2. **Correctness**: Keys that omit varying dimensions cause wrong data to be served.
3. **Debuggability**: Keys that are opaque (random hashes) make debugging impossible.

At Staff level, key design is a first-class design decision—not an afterthought.

## What to Include in a Cache Key

**Include: resource type + ID + variant parameters.**

| Component | Purpose | Example |
|-----------|---------|---------|
| **Resource type** | Disambiguates entity types | `user`, `order`, `product` |
| **ID** | Identifies the specific resource | `123`, `789` |
| **Variant parameters** | Parameters that change the response | `lang:en-US`, `role:admin`, `version:v2` |

**Example**: `user:123:profile:en-US`
- `user` = resource type
- `123` = user ID
- `profile` = what we're caching (field or endpoint)
- `en-US` = language—response differs by locale

**Why variant parameters matter**: If the API returns different content for `?lang=es` vs `?lang=en`, both must have distinct keys. Otherwise, the first cached response overwrites the second—wrong language served to users.

## Namespacing: Preventing Cross-Service Collisions

**Prefix with service name**: `{service}:{entity}:{id}:{variant}`

**Example**: `order-svc:order:789:summary`

When multiple services share a Redis cluster (common in microservices), keys can collide. Service A might use `order:789` for an order, while Service B uses `order:789` for a different concept (e.g., a report ID). **Namespacing prevents collisions.**

```
Without namespacing:
  order-svc writes: order:789 → order data
  report-svc writes: order:789 → report data   ← COLLISION: overwrites!

With namespacing:
  order-svc:order:789 → order data
  report-svc:order:789 → report data   ← No collision
```

## Include What Varies

**Rule**: Include every dimension that changes the response.

| Dimension | Include in Key? | Example |
|-----------|-----------------|---------|
| Language/locale | Yes | `user:123:profile:en-US` |
| User role | Yes (if response differs) | `product:456:price:wholesale` |
| API version | Yes | `user:123:v2:profile` |
| A/B test variant | Yes (if response differs) | `feed:user:123:variant:B` |
| Request timestamp | **No** | Causes 0% hit rate |
| Random nonce | **No** | Causes 0% hit rate |
| Full request body hash | **No** (usually) | Too specific, low hit rate |

## What NOT to Include

| Anti-pattern | Why It's Bad | Fix |
|--------------|--------------|-----|
| **Request timestamp** | Every request is unique → 0% hit rate | Use TTL for freshness; key should be deterministic for same logical request |
| **Random nonce** | Same as timestamp | Remove; use deterministic key |
| **Full request body hash** | Very specific; similar requests (slightly different params) miss | Include only params that materially change the response |
| **Session ID** (when not needed) | User-specific cache becomes non-shared | Cache shared data with user_id; cache user-specific with user_id only if necessary |

## Key Length Trade-offs

- **Longer keys** = more memory (Redis stores keys in memory), slower lookups (more bytes to compare), larger network payload.
- **Shorter keys** = less readable, harder to debug.
- **Guideline**: Keep keys under **100 bytes**. Use abbreviations if needed: `u` for user, `p` for profile, etc. Balance readability with efficiency.

## Key Design for Pagination

**Pattern**: `feed:user:123:page:2:size:20`

**Problem**: When the feed changes (new post added), *all* pages become stale. Invalidating "all pages for user 123" requires either:
1. **Version in key**: `feed:user:123:v:456:page:2`—invalidate by bumping version.
2. **Cursor-based**: Cache cursor identifiers; invalidation is trickier.
3. **Short TTL**: Accept stale pages; TTL limits exposure.

**Trade-off**: Fine-grained keys (per page) = high hit rate for repeated page visits, but invalidation is expensive. Coarse keys (whole feed) = easy invalidation, but low hit rate for partial reads.

## Common Key Patterns

| Pattern | Format | Use Case |
|---------|--------|----------|
| Entity field | `{entity_type}:{id}:{field}` | `user:123:profile`, `order:789:total` |
| Service namespaced | `{service}:{entity}:{id}:{variant}` | `order-svc:order:789:summary` |
| Multi-tenant | `tenant:{tid}:{entity}:{id}` | `tenant:456:user:123:profile` |
| List/set | `{entity}:{id}:{list_name}:{params}` | `user:123:followers:page:1` |
| Rate limit | `ratelimit:{scope}:{identifier}:{window}` | `ratelimit:api:user:123:60` |

## Multi-Tenant Key Design

**Include tenant ID** when data is tenant-scoped: `tenant:456:user:123:profile`

**Why**: Without tenant ID, User 123's data in Tenant A could be served to User 123 in Tenant B (if user IDs are scoped per tenant but key omits tenant). **Never assume tenant from context when designing keys—make it explicit.**

## ASCII Diagram: Good vs Bad Key Design

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CACHE KEY DESIGN: HIT RATE IMPACT                         │
│                                                                             │
│   BAD KEYS (Low/Zero Hit Rate):                                             │
│                                                                             │
│   Key: user:123:profile:1739123456                                          │
│         ↑         ↑         ↑                                                │
│         │         │         └── TIMESTAMP! Every request different key      │
│         │         │             Hit rate: 0%                                 │
│         │         └── OK                                                      │
│         └── OK                                                                │
│                                                                             │
│   Key: req:a1b2c3d4e5f6... (full request hash)                              │
│         ↑                                                                    │
│         └── Too specific. Slight param change = different key.               │
│             Hit rate: < 5%                                                   │
│                                                                             │
│   ─────────────────────────────────────────────────────────────────────    │
│                                                                             │
│   GOOD KEYS (High Hit Rate):                                                │
│                                                                             │
│   Key: order-svc:user:123:profile:en-US                                     │
│         ↑         ↑    ↑   ↑       ↑                                         │
│         │         │    │   │       └── Variant: affects response             │
│         │         │    │   └── Field: what we cache                          │
│         │         │    └── ID: which resource                                 │
│         │         └── Entity type                                            │
│         └── Service namespace: prevents collision                            │
│                                                                             │
│   Same user, same locale → same key → HIT. Hit rate: 70-95%                  │
│                                                                             │
│   ─────────────────────────────────────────────────────────────────────    │
│                                                                             │
│   PAGINATION TRADEOFF:                                                      │
│                                                                             │
│   feed:user:123:page:2:size:20    ← Fine-grained: good hit, hard invalidate  │
│   feed:user:123                   ← Coarse: easy invalidate, low hit         │
│   feed:user:123:v:456:page:2      ← Versioned: bump v to invalidate all     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Operational Guidance: Key Design Checklist

Before deploying a new cache:
1. **List all dimensions** that affect the response (user, role, locale, version, etc.).
2. **Include each dimension** in the key if it varies and changes the response.
3. **Exclude** timestamps, nonces, and request-specific randomness.
4. **Namespace** with service name if sharing a cluster.
5. **Include tenant ID** for multi-tenant data.
6. **Keep keys under 100 bytes**; abbreviate if necessary.
7. **Design invalidation**—how will you invalidate when the source data changes?

## Monitoring: Key Design Metrics

| Metric | What to Watch | Action if Bad |
|--------|---------------|---------------|
| **Cache hit rate** | < 50% for a cache layer | Audit key design; look for timestamp/nonce in keys |
| **Key cardinality** | Explosive growth (millions of unique keys) | Keys too granular; consolidate where possible |
| **Key length distribution** | Many keys > 100 bytes | Abbreviate; refactor key structure |
| **Memory per key** | High overhead | Shorter keys; smaller values; consider compression |

**Practical Redis commands for key audit**:
```bash
# Sample random keys to inspect patterns
redis-cli --scan --pattern '*' | head -100

# Count keys by prefix (requires redis-cli or script)
redis-cli --scan --pattern 'user:*' | wc -l
redis-cli --scan --pattern 'order-svc:*' | wc -l

# Key size distribution (MEMORY USAGE key — Redis 4+)
redis-cli MEMORY USAGE some_key
```

## L5 vs L6: Key Design in Practice

| Scenario | L5 Key | L6 Key | Why L6 Wins |
|----------|--------|--------|-------------|
| User profile API | `profile:${userId}` | `user-svc:user:${userId}:profile:${locale}` | Locale affects response; service namespace prevents collision |
| Product listing | `products:${category}` | `catalog-svc:products:${category}:page:${page}:sort:${sort}` | Pagination and sort affect response; deterministic for same logical request |
| Rate limiter | `rate:${ip}` | `ratelimit:api:${scope}:${id}:${windowSec}` | Scope (API vs login), identifier, window—explicit and debuggable |
| Dashboard (user-specific) | `dashboard` | `dashboard:user:${userId}` | **Critical**: Generic key = data leakage; user-specific = correct |

---

# Part 2: Cache Poisoning — How to Prevent (Topic 262)

## What Is Cache Poisoning?

**Cache poisoning** occurs when **wrong data** is stored under a cache key. Every reader of that key receives the corrupted data until the entry expires (TTL) or is invalidated.

Unlike a cache miss (which triggers a backend fetch), a poison **hit** serves incorrect data. The system believes it's working correctly—that's what makes it dangerous.

## How Cache Poisoning Happens

| Cause | Mechanism | Example |
|-------|-----------|---------|
| **App bug** | Code writes wrong value to a key | Bug caches User B's data under User A's key |
| **Race condition** | Stale overwrites fresh | Two requests; older response overwrites newer due to timing |
| **Error response cached** | 5xx or error cached as valid | 500 response cached; served to all users for TTL |
| **Malicious input** | Attacker manipulates key construction | Crafted input injects into key → wrong key used |
| **Serialization bug** | Corrupt serialization | Partial/corrupted value stored; deserialization fails or returns wrong data |

## Impact: Persistence Until TTL

**Poisoned data persists until TTL expires.** If TTL = 1 hour, every user requesting that key sees wrong data for 1 hour. There is no "self-healing" until expiration or manual invalidation.

**Blast radius**: One bad key can affect:
- All users (if key is global, e.g., `config:feature_x`)
- All users in a region (if cache is regional)
- A subset of users (if key includes user/tenant ID—smaller but still impactful)

## Prevention Strategies

### 1. Validate Before Caching

**Never cache error responses.** 5xx, 4xx (except perhaps 404 for "not found" with short TTL), empty responses—do not cache these. Validate that the response is successful and non-empty before writing to cache.

```python
# BAD: Cache whatever comes back
response = db.fetch(user_id)
cache.set(key, response, ttl=3600)  # Caches 500 errors!

# GOOD: Validate before cache
response = db.fetch(user_id)
if response and response.status == 200 and response.body:
    cache.set(key, response, ttl=3600)
else:
    # Don't cache; let next request try again
    pass
```

### 2. Integrity Checks

Store a **hash** of the cached value (or use integrity-preserving serialization). On read, verify the hash matches. If corrupted, treat as miss and refetch. This catches serialization bugs and bit flips.

### 3. Short TTLs for Sensitive Data

Sensitive data (permissions, PII) should have shorter TTLs. Reduces exposure window if poisoning occurs.

### 4. Cache Key Sanitization

**Prevent injection** into key construction. If user input influences the key (e.g., `user:${user_input}:profile`), validate and sanitize. Malicious input like `user:123:profile:en-US\x00` could cause key collision or unexpected behavior. Use allowlists, escape special characters, or hash the user-controlled part.

### 5. Monitoring and Alerting

- **Anomalous patterns**: Sudden spike in cache reads for a single key (everyone hitting one poisoned key).
- **Error rate correlation**: Cache hit rate up but error rate up → possible poisoning.
- **Stale data reports**: User reports of wrong data; correlate with recent cache writes.

## HTTP Response Caching Poisoning

In HTTP caching (CDN, reverse proxy), poisoning can occur via:

1. **Host header manipulation**: Attacker sends `Host: evil.com`. Response cached under `evil.com` key. Next user requesting `evil.com` (e.g., via DNS rebinding) gets attacker's content.
2. **URL manipulation**: Unusual query params or path segments can create distinct cache keys. Attacker crafts a request that caches a response; victims with "normal" URLs might get served that response if cache key logic is buggy.

**Prevention**: Validate and normalize `Host` and URL before using in cache key. Reject suspicious values.

## Server-Side Cache Poisoning

**Classic mistake**: Caching a **user-specific** response under a **generic** key.

Example: API returns `GET /dashboard` → personalized dashboard. Developer caches under `dashboard` (no user ID). First user's dashboard is cached. All subsequent users get User 1's dashboard. **Data leakage.**

**Fix**: Include user ID (or session ID) in key: `dashboard:user:123`.

## Recovery Options

| Option | Pros | Cons |
|-------|------|------|
| **Full cache flush** | Removes all poison | Stampede: all requests hit backend at once. Can take down backend. |
| **Targeted invalidation** | Removes only bad keys | Requires knowing which keys are poisoned. Not always possible. |
| **Wait for TTL** | No operational action | Users see wrong data until expiry. Unacceptable for critical data. |

**Best practice**: Have a runbook. For known bad keys: targeted invalidation. For widespread poisoning: consider controlled flush (e.g., flush one shard at a time with delay) to avoid stampede. Use cache-aside with lock or coalescing to mitigate stampede during repopulation.

## Poisoning Runbook Template

```
1. DETECT: User reports wrong data; metrics show anomalous hit pattern
2. IDENTIFY: Which keys? Check recent cache writes; correlate with reports
3. CONTAIN: Targeted invalidation for known bad keys (DEL key)
4. IF WIDESPREAD: 
   a. Flush one shard at a time with 60s delay between shards
   b. Enable request coalescing / singleflight for repopulation
   c. Consider temporary traffic shed to protect backend
5. ROOT CAUSE: App bug? Race? Error cached? Fix and deploy
6. PREVENT: Add validation, sanitization; update monitoring
```

## Practical Monitoring Queries (Cache Poisoning)

| Alert Condition | Likely Cause | Response |
|-----------------|--------------|----------|
| Single key receives 10× normal read rate | Possible poisoning—everyone hitting one bad key | Investigate key; check if wrong data |
| Cache hit rate up + user error reports up | Poisoned responses being served | Correlate keys with errors; invalidate |
| Spike in cache writes from one service | Bug or attack writing bad data | Throttle or block; fix service |

## L5 vs L6: Poisoning Response

| Action | L5 | L6 |
|--------|-----|-----|
| Discovery | "Users see wrong data" | "Which keys? What pattern? When did it start?" |
| Remediation | "Flush everything" | "Targeted invalidation if known; controlled flush if not" |
| Prevention | "Be more careful" | "Add validation gate, sanitize keys, alert on anomalies" |
| Blast radius | Doesn't consider | Models: global vs tenant vs user-scoped keys |

## ASCII Diagram: Poisoning Flow and Prevention Layers

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CACHE POISONING: FLOW AND PREVENTION                       │
│                                                                             │
│   POISONING FLOW:                                                            │
│                                                                             │
│   ┌──────────┐     Bad Write     ┌──────────┐     Read      ┌──────────┐   │
│   │  App     │ ─────────────────►│  Cache   │◄──────────────│  Users   │   │
│   │  (bug,   │   (wrong value    │  (stores │   (all get    │  (see     │   │
│   │  race,   │    under key)     │   poison)│    poison)    │  wrong    │   │
│   │  attack) │                   │          │               │  data)    │   │
│   └──────────┘                   └──────────┘               └──────────┘   │
│         │                              │                          │         │
│         │                              │ TTL                      │         │
│         │                              └──────────────────────────┘         │
│         │                              Persists until expiry                │
│                                                                             │
│   ─────────────────────────────────────────────────────────────────────    │
│                                                                             │
│   PREVENTION LAYERS:                                                        │
│                                                                             │
│   Layer 1: VALIDATE BEFORE CACHE                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  if status != 200 or body empty → DO NOT CACHE                       │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   Layer 2: SANITIZE KEYS                                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  user_input → allowlist, escape, or hash before key construction    │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   Layer 3: INTEGRITY CHECK (optional)                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  Store hash(value); on read: verify hash, else treat as miss        │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   Layer 4: MONITOR                                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  Alert: single-key read spike, hit rate up + error rate up          │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 3: Redis Persistence — RDB vs AOF (Topic 265)

## The Problem: Redis Is In-Memory

Redis stores data in **memory**. If the process dies (crash, OOM kill, restart), all data is lost. **Persistence** saves data to disk so it can be recovered after restart.

The trade-off: durability vs performance. Writing to disk is slower than writing to memory. Every persistence choice has a performance and data-loss profile.

## RDB (Redis Database Backup)

**RDB** = periodic **point-in-time snapshot** of the entire dataset.

### How It Works

1. Redis triggers `BGSAVE` (background save) based on configuration or manual command.
2. Redis **forks** the process. Child process gets a copy of memory (copy-on-write).
3. Child **serializes** all data to a compact binary file (`dump.rdb`).
4. When done, replaces the old dump file atomically.

### Pros

- **Fast recovery**: Load one file; dataset restored. Much faster than replaying a log.
- **Compact**: Binary format; smaller than AOF.
- **Good for backups**: Snapshot file is self-contained; easy to copy for backups.

### Cons

- **Data loss between snapshots**: If Redis crashes 4 minutes after the last save, you lose 4 minutes of data.
- **Fork overhead**: `BGSAVE` forks the process. On large datasets (e.g., 50GB), fork can take **seconds**—during which Redis may pause (depending on OS and Redis version). Copy-on-write means the child shares pages with parent until writes occur.

### Configuration

```
save 900 1      # Save if at least 1 key changed in 900 seconds (15 min)
save 300 10     # Save if at least 10 keys changed in 300 seconds (5 min)
save 60 10000   # Save if at least 10000 keys changed in 60 seconds
```

First matching rule wins. More frequent saves = less data loss, more I/O and fork overhead.

## AOF (Append-Only File)

**AOF** = log of **every write command** appended to a file. On restart, Redis replays the log to reconstruct state.

### How It Works

1. Every `SET`, `INCR`, `DEL`, etc. is appended to the AOF file as a Redis protocol command.
2. On restart: Redis reads the AOF from the beginning and re-executes each command.

### Pros

- **Much less data loss** (depending on fsync policy): Can achieve near-zero loss with `appendfsync always`.
- **Human-readable**: AOF is text; you can inspect and repair manually if needed.

### Cons

- **File grows large**: Every write adds to the file. Over time, AOF can be huge.
- **Slower recovery**: Replaying millions of commands takes time—longer than loading RDB.
- **Rewrite required**: AOF rewrite compacts the file by producing the minimal command sequence for current state.

### fsync Options

| Option | Behavior | Data Loss | Performance |
|--------|----------|-----------|-------------|
| `always` | fsync after every write | None (modulo OS) | Slowest; limits throughput |
| `everysec` | fsync once per second | Up to 1 second | Good balance; default |
| `no` | OS decides when to fsync | Up to 30 seconds (Linux default) | Fastest; risky |

**Production recommendation**: `appendfsync everysec`. Balance between durability and performance. Use `always` only for critical data when latency is acceptable.

## AOF Rewrite

Over time, AOF accumulates redundant commands. Example: `SET user:123 1`, then `SET user:123 2`, then `SET user:123 3` → AOF has three commands, but only the last matters. **AOF rewrite** creates a new AOF with the minimal commands to reproduce current state.

- Triggered automatically when AOF size exceeds a threshold (or growth factor).
- Redis forks; child writes new compacted AOF; parent continues logging new commands to the old AOF and a rewrite buffer.
- When child finishes, Redis appends buffered commands to the new AOF and atomically switches.

## Hybrid Persistence (Redis 4.0+)

**Hybrid** = RDB snapshot + AOF of changes **since** the last snapshot.

On restart:
1. Load RDB (fast)—restores state as of last snapshot.
2. Replay AOF tail (small)—replays only changes since snapshot.

**Result**: Fast recovery (RDB) + minimal data loss (AOF delta). Best of both.

### Configuration

```
appendonly yes
aof-use-rdb-preamble yes
```

With `aof-use-rdb-preamble`, the AOF file starts with an RDB snapshot when a rewrite happens, followed by incremental AOF commands. Efficient and durable.

## Fork Overhead: The 50GB Problem

**BGSAVE** and **AOF rewrite** both fork. On Linux, fork uses **copy-on-write (COW)**. Child shares pages with parent until either writes. For a 50GB dataset:
- Fork itself can take 1–5 seconds (copying page tables).
- During COW, if parent writes to many pages, each written page must be copied. Can cause latency spikes.

**Mitigation**:
- Use Redis on systems with fast fork (Linux with transparent huge pages tuned).
- Avoid huge instances (e.g., 100GB+) if latency is critical; shard into smaller instances.
- Schedule BGSAVE during low-traffic windows.
- Monitor `latest_fork_usec` in Redis `INFO`—alert if fork time grows.

## Practical Advice

| Scenario | Recommendation |
|----------|----------------|
| **Cache only (data loss acceptable)** | RDB with long interval, or no persistence |
| **Session data** | AOF with `everysec` or hybrid |
| **Critical data (e.g., rate limit counters)** | AOF with `everysec`, or hybrid; consider `always` if acceptable |
| **Large instance (50GB+)** | Monitor fork time; consider smaller shards |

**Key takeaway**: Use **hybrid persistence** in production when data durability matters. Use `appendfsync everysec` unless you have a compelling reason for `always`. Monitor fork time on large instances.

## Redis Persistence: Configuration Quick Reference

| Parameter | Purpose | Recommended |
|-----------|---------|-------------|
| `save` | RDB trigger (seconds, key count) | `900 1`, `300 10`, `60 10000` for balance |
| `appendonly` | Enable AOF | `yes` for durability |
| `appendfsync` | When to fsync AOF | `everysec` (default) |
| `aof-use-rdb-preamble` | Hybrid format | `yes` (Redis 4+) |
| `stop-writes-on-bgsave-error` | Refuse writes if BGSAVE fails | `yes` (safety) |

## Monitoring: Persistence Metrics

```bash
# Redis INFO persistence section
redis-cli INFO persistence

# Key metrics:
# rdb_last_save_time - Unix timestamp of last successful RDB save
# rdb_last_bgsave_status - ok or err
# rdb_last_bgsave_time_sec - duration of last BGSAVE
# aof_last_write_status - ok or err
# aof_current_size - current AOF file size
# latest_fork_usec - microseconds for last fork (alert if > 1_000_000)
```

**Alert on**: `rdb_last_bgsave_status` = err, `aof_last_write_status` = err, `latest_fork_usec` > 1 second for large instances.

## L5 vs L6: Persistence Decisions

| Scenario | L5 | L6 |
|----------|-----|-----|
| "We need Redis to survive restarts" | "Turn on AOF" | "AOF with what fsync? everysec = up to 1s loss. always = slow. Hybrid gives fast recovery + minimal loss. What's our RPO?" |
| "Redis is slow during backups" | "Disable persistence during backup" | "BGSAVE forks; fork is the cost. On 50GB, fork takes seconds. Schedule BGSAVE during low traffic. Consider smaller shards." |
| "We lost 10 minutes of data" | "Must have been a bug" | "RDB-only with 10-min interval? That's expected. Add AOF or hybrid. Match persistence to data criticality." |

---

# Part 4: Redis Cluster — Slots and Routing (Topic 266)

## Why Redis Cluster?

Single Redis instance has limits: memory, CPU, network. **Redis Cluster** distributes data across multiple Redis nodes for horizontal scaling and high availability.

## Hash Slots: 16,384 Slots

Redis Cluster divides the key space into **16,384 hash slots**. Each key maps to exactly one slot:

```
slot = CRC16(key) mod 16384
```

**CRC16** is a deterministic hash. Each node is assigned a subset of slots. Example: 3 nodes might have:
- Node 1: slots 0–5460
- Node 2: slots 5461–10922
- Node 3: slots 10923–16383

## Client Routing: MOVED and ASK

When a client sends a command (e.g., `GET user:123`):

1. Client hashes the key → slot (e.g., 1234).
2. Client may not know which node owns that slot. It sends to *any* node (or a known entry point).
3. If the key is on that node: **process locally**, return result.
4. If the key is on another node: node responds with **`MOVED 1234 10.0.0.2:6379`**. Client should retry the command by sending it directly to `10.0.0.2:6379`.
5. **Smart clients** cache the slot → node mapping. Next time, they send directly to the correct node—no redirect.

### ASK Redirect

During **slot migration** (adding/removing nodes), some keys may be in transit. If the key is being migrated, the node responds with **`ASK 1234 10.0.0.3:6379`**. Client sends `ASKING` to the new node, then the command. ASK is temporary; MOVED is permanent (update your slot cache).

## Smart Clients

**Smart clients** (Jedis, Lettuce, redis-py with cluster support) maintain a **slot → node** mapping. They:
1. Hash the key to a slot.
2. Look up the node for that slot.
3. Send the command directly to that node.

On `MOVED` or `ASK`, they update the mapping and retry. This avoids repeated redirects and reduces latency.

## Adding and Removing Nodes

- **Adding a node**: Admin triggers rebalancing. Slots are moved from existing nodes to the new node. Data migrates; during migration, `ASK` redirects for keys in transit.
- **Removing a node**: Its slots are distributed to remaining nodes. Same migration process.

## Replication

Each **master** node can have one or more **replicas**. If a master fails, the cluster promotes a replica. Failover is automatic (with proper configuration). Data is replicated asynchronously from master to replicas.

## Multi-Key Operations and Hash Tags

**Constraint**: Commands that operate on multiple keys (e.g., `MGET`, `MULTI`/`EXEC` transaction) require all keys to be on the **same slot**. Otherwise, Redis returns `CROSSSLOT` error.

**Solution: Hash tags.** Use `{tag}` in the key. Only the part inside `{}` is hashed for slot calculation.

```
{user:123}:profile   → hashes on "user:123" → slot X
{user:123}:settings  → hashes on "user:123" → slot X
```

Both keys are on the same slot. You can `MGET {user:123}:profile {user:123}:settings` or use them in a transaction.

## Cluster Limitations

| Limitation | Implication |
|------------|-------------|
| No multi-key across slots | Use hash tags for co-location |
| Lua scripts | All keys in script must be in same slot (use hash tags) |
| Transactions | Same—all keys in MULTI must be same slot |
| Higher latency | Extra hop if client doesn't have correct mapping; cross-node operations |

## Cluster Sizing

- Each node: typically 100K–500K ops/sec (depends on hardware).
- 16,384 slots can be distributed across 3 to 100+ nodes.
- Minimum 3 masters for a working cluster; add replicas for HA.

## Hash Tags: Deep Dive

**Syntax**: `{user:123}`—only the string inside `{}` is hashed. `user:123` determines the slot; the rest of the key is ignored for hashing.

**Valid hash tags**:
- `{user:123}:profile` and `{user:123}:settings` → same slot
- `order:{456}:items` and `order:{456}:total` → same slot

**Invalid** (different slots):
- `user:123:profile` and `user:123:settings` → full key hashed; likely different slots
- `{a}{b}` → only `a` is used (first `{}` block wins)

**Use cases**: MGET, MULTI/EXEC transactions, Lua scripts that touch multiple keys. Co-locate related keys for atomicity.

## Cluster Failover and Replication

- Each master has 1+ replicas. Replicas replicate asynchronously.
- **Automatic failover**: When master is detected down (by other nodes via gossip), a replica is promoted. Cluster continues.
- **Manual failover**: `CLUSTER FAILOVER` for maintenance.
- **Replication lag**: Replicas may be behind. Reads from replica (if allowed) can return stale data. Use for read scaling where stale is OK.

## Operational Guidance: Redis Cluster

| Task | Command / Approach |
|------|---------------------|
| Check cluster state | `redis-cli -c CLUSTER INFO` |
| List nodes and slots | `redis-cli -c CLUSTER NODES` |
| Add node | `redis-cli -c CLUSTER MEET <ip> <port>` |
| Rebalance slots | `redis-cli --cluster rebalance` |
| Migrate slot | `redis-cli --cluster reshard` |

**Common pitfall**: Application uses naive client (no cluster support). Connects to one node, gets MOVED, doesn't retry. Use smart client (Jedis Cluster, Lettuce, redis-py cluster mode).

## L5 vs L6: Redis Cluster

| Scenario | L5 | L6 |
|----------|-----|-----|
| "MGET fails with CROSSSLOT" | "Use separate GETs" | "Use hash tags: {id}:field1, {id}:field2. Enables atomic multi-key ops." |
| "Adding nodes is slow" | "Just add more Redis" | "Slot migration moves data. Plan rebalance during low traffic. Each migrating key may trigger ASK redirect." |
| "Some keys are hot" | "Add more replicas" | "Hot key = single slot = single node. Replicas help read distribution but writes hit one node. Consider splitting the hot key (e.g., shard by sub-id) if possible." |

## ASCII Diagram: Redis Cluster Routing

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    REDIS CLUSTER: SLOTS AND ROUTING                         │
│                                                                             │
│   KEY → SLOT:  CRC16(key) mod 16384                                         │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  SLOT RING (simplified: 12 slots shown, actual = 16384)              │   │
│   │                                                                      │   │
│   │       Slot 0─2          Slot 3─5          Slot 6─8          Slot 9─11 │   │
│   │    ┌──────────┐      ┌──────────┐      ┌──────────┐      ┌──────────┐ │   │
│   │    │ Node A   │      │ Node B   │      │ Node C   │      │ Node D   │ │   │
│   │    │ Master   │      │ Master   │      │ Master   │      │ Master   │ │   │
│   │    └──────────┘      └──────────┘      └──────────┘      └──────────┘ │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   CLIENT ROUTING FLOW:                                                       │
│                                                                             │
│   Client                    Node A                      Node B              │
│     │                         │                            │                │
│     │  GET user:123            │                            │                │
│     │ ───────────────────────►│                            │                │
│     │                         │  Key hashes to slot 7       │                │
│     │                         │  Slot 7 owned by Node B     │                │
│     │  MOVED 7 B:6379         │                            │                │
│     │ ◄───────────────────────│                            │                │
│     │                         │                            │                │
│     │  GET user:123                                            │                │
│     │ ───────────────────────────────────────────────────────►│                │
│     │                         │                            │  Process        │
│     │  "value"                │                            │  Return         │
│     │ ◄───────────────────────────────────────────────────────│                │
│     │                         │                            │                │
│   Smart client: caches slot 7 → Node B for future requests                  │
│                                                                             │
│   HASH TAGS:                                                                 │
│   {user:123}:profile  and  {user:123}:settings  → same slot → MGET works    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 5: Time-Series DB Internals (Topic 259)

## Why Time-Series Data Is Different

Time-series data has distinct access patterns:

| Characteristic | Implication |
|----------------|-------------|
| **Write-heavy** | High ingest rate; append-only |
| **Append-only** | Rarely update or delete; optimizations possible |
| **Time-ordered** | Queries are range scans by timestamp |
| **Range queries** | "Give me data from 2pm to 4pm" |
| **Downsampling** | Store 1-sec resolution for 7 days; 1-min for 30 days; 1-hour for 1 year |
| **Rarely updated** | No need for complex update/delete machinery |

General-purpose databases (PostgreSQL, MySQL) are built for mixed read/write, random access, and updates. Time-series workloads stress them differently.

## Regular DB Problems with Time-Series

- **Indexes grow too large**: B-tree on timestamp for billions of rows → huge index, slow inserts.
- **Range queries on timestamp**: Can be slow if not partition-aligned.
- **No native downsampling**: Must aggregate in application or via complex queries.
- **VACUUM/compaction**: Append-only still creates dead tuples from compression; maintenance overhead.

## Time-Series Optimizations

### Time-Based Partitioning

Each partition = one time range (e.g., one day, one hour). New data goes to the current partition. Old partitions can be compressed, moved to cold storage, or dropped. Range queries touch only relevant partitions.

### Columnar Storage

Store each column separately (timestamp column, value column, tag columns). Compression works better (similar values in a column). Queries that need only one column read less data.

### Gorilla Compression (Facebook)

**Timestamp compression**: Timestamps are sequential. Delta between consecutive timestamps is small. Delta-of-delta is often zero or very small. Store deltas of deltas in fewer bits. **Value compression**: Consecutive values are often similar. XOR current value with previous → small number → fewer bits. **Result**: ~10× compression for typical metrics.

### Downsampling

| Resolution | Retention | Purpose |
|------------|-----------|---------|
| 1 second | 7 days | Raw data, debugging |
| 1 minute | 30 days | Operational dashboards |
| 1 hour | 1 year | Trend analysis |
| 1 day | 5 years | Long-term analytics |

Reduces storage dramatically. 1-second data for 7 days = 604,800 points per metric. 1-minute for 30 days = 43,200 points. 1-hour for 1 year = 8,760 points.

## Examples: InfluxDB, TimescaleDB, Prometheus

| System | Storage | Notable Features |
|--------|---------|------------------|
| **InfluxDB** | Custom TSM (Time-Structured Merge) | Optimized for metrics; downsampling, retention policies |
| **TimescaleDB** | PostgreSQL extension | Hypertables; automatic partitioning; SQL |
| **Prometheus** | Local TSDB | Pull-based; no long-term storage by default |
| **Victoria Metrics** | Prometheus-compatible | Efficient storage; long-term retention |

## When to Use Time-Series DB

- Monitoring and metrics (Prometheus, Grafana, etc.)
- IoT sensor data
- Financial time-series (ticks, OHLCV)
- Log analytics (with time ordering)
- Application events (clicks, views)

## When NOT to Use

- General CRUD (updates, deletes)
- Relational queries (joins, foreign keys)
- Transaction-heavy workloads
- Data that isn't time-centric

**Staff insight**: Reach for a time-series DB when write volume exceeds ~10K points/sec, retention is long (90+ days), and you need efficient range queries and downsampling. For low volume or short retention, PostgreSQL with a timestamp index may suffice.

## Gorilla Compression: Technical Detail

**Timestamp delta-of-delta encoding**:
- Timestamps are often at regular intervals (e.g., every 10 seconds). Delta = 10. Delta-of-delta = 0 (no change). Store 0 in 1 bit.
- Irregular: store actual delta with variable-length encoding (fewer bits for small values).

**Value XOR encoding**:
- Consecutive metric values (e.g., CPU%) often similar. XOR(current, previous) = small number when values are close.
- Small numbers need fewer bits. Leading zeros can be omitted (run-length encoding).

**Result**: ~12 bytes per data point (raw) → ~1.2 bytes (compressed) for typical metrics. 10× compression.

## Time-Series: Capacity Estimation

| Metric | Formula | Example |
|--------|---------|---------|
| Raw points per day | metrics × (86400 / interval_sec) | 1000 metrics × (86400/10) = 8.64M points/day |
| Compressed storage | points × ~2 bytes (Gorilla) | 8.64M × 2 ≈ 17 MB/day |
| 90-day retention | daily × 90 | ~1.5 GB |
| With downsampling | 1-sec for 7d, 1-min for 30d, 1-hr for 1y | Much less for long retention |

## L5 vs L6: Time-Series Decisions

| Scenario | L5 | L6 |
|----------|-----|-----|
| "We need to store metrics" | "PostgreSQL with timestamp column" | "At 100K points/sec? PostgreSQL will struggle. Time-series DB: time-partitioned, columnar, compression. Or Prometheus for pull-based, Victoria Metrics for long-term." |
| "Retention is 2 years" | "Store everything" | "Downsample: 1-sec for 7 days, 1-min for 30 days, 1-hour for 2 years. Raw 1-sec for 2 years = massive storage." |
| "Queries are slow" | "Add index" | "Time-series: range queries by time. Partition by time; query touches only relevant partitions. B-tree on timestamp in PostgreSQL can work for modest scale but doesn't match TS optimizations." |

---

# Part 6: Inverted Index Internals (Topic 260)

## Forward vs Inverted Index

**Forward index**: Document → list of words. "Document 1 contains words A, B, C."
**Inverted index**: Word → list of documents. "Word A appears in documents 1, 3, 7."

"Inverted" = flip the perspective from document-centric to term-centric.

## Building the Inverted Index

1. **Tokenize** documents: split text into terms (words, optionally normalized).
2. For each term, maintain a **posting list**: sorted list of document IDs containing that term.
3. Optionally store **positions** (for phrase search) and **frequency** (for ranking).

## Posting List

**Posting list** = sorted list of document IDs. Example: term "redis" → [3, 7, 12, 45, 100].

**Compression**: Consecutive IDs are similar. Store **deltas** (differences) instead of absolute IDs. Deltas are smaller → more compressible. Example: [3, 7, 12, 45, 100] → deltas [3, 4, 5, 33, 55].

## Querying

1. Look up each term → get posting lists.
2. **Intersect** posting lists for AND queries (e.g., "redis" AND "cache").
3. **Union** for OR queries.
4. **Rank** results (TF-IDF, BM25).
5. Return top K.

## TF-IDF

**TF (Term Frequency)**: How often does the term appear in the document? More occurrences → higher score.
**IDF (Inverse Document Frequency)**: How rare is the term across all documents? Rare terms (e.g., "quantum") get higher IDF. Common terms (e.g., "the") get low IDF.

**TF-IDF = TF × IDF**

Rare terms that appear often in a document score highly. Common terms don't dominate.

## BM25

**BM25** = improved TF-IDF with:
- **Document length normalization**: Long documents don't get unfair advantage from having more term occurrences.
- **Saturation**: Term frequency has diminishing returns—10 occurrences isn't 10× better than 1.

Used by **Elasticsearch** (and Lucene) as the default ranking algorithm for full-text search.

## Position Indexes

For **phrase matching** ("machine learning"), we need both words to appear and be **adjacent**. Store positions of each term in each document. At query time, check that positions are consecutive.

## Stemming and Lemmatization

- **Stemming**: "running" → "run", "better" → "better" (or "good" depending on stemmer). Reduces words to root form.
- **Lemmatization**: "running" → "run", "better" → "good". Uses dictionary; more accurate.

Both increase **recall**—a query for "run" can match "running" and "runs".

## Elasticsearch/Lucene Internals

- **Segments**: Index is stored in immutable segments. New documents → new segment. Segments are periodically **merged** (compaction)—similar to LSM compaction.
- **Inverted index per segment**: Each segment has its own inverted index.
- **Query**: Search across all segments; merge results. Merge policy controls segment count and size.

## ASCII Diagram: Inverted Index Structure

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    INVERTED INDEX STRUCTURE                                  │
│                                                                             │
│   DOCUMENTS (Forward view):                                                 │
│   Doc 1: "Redis is a cache"                                                 │
│   Doc 2: "Cache improves performance"                                       │
│   Doc 3: "Redis and Memcached are caches"                                  │
│                                                                             │
│   INVERTED INDEX (Term → Posting list):                                     │
│                                                                             │
│   Term          Posting List (doc IDs)     (with positions)                 │
│   ─────────────────────────────────────────────────────────────────────   │
│   redis         [1, 3]                     1:[0], 3:[0]                      │
│   cache         [1, 2, 3]                 1:[3], 2:[0], 3:[5]              │
│   performance   [2]                       2:[2]                             │
│   memcached     [3]                       3:[4]                             │
│   ...                                                                       │
│                                                                             │
│   QUERY "redis cache":                                                      │
│   1. Look up "redis" → [1, 3]                                              │
│   2. Look up "cache" → [1, 2, 3]                                           │
│   3. Intersect → [1, 3]                                                    │
│   4. Rank by TF-IDF/BM25 → return Doc 1, Doc 3                             │
│                                                                             │
│   PHRASE "redis cache":                                                     │
│   Check positions: Doc 1 has "redis" at 0, "cache" at 3 → adjacent?       │
│   Depends on tokenization. "redis" at 0, "cache" at 3 → gap of 2 tokens.  │
│   If phrase requires adjacency, Doc 1 might not match "redis cache" phrase. │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Operational Guidance

- **Source of truth**: Never make Elasticsearch the primary store. Sync from primary DB (PostgreSQL, etc.) via CDC or batch jobs.
- **Index design**: Mapping (analyzers, tokenizers) affects recall and precision. Test with real queries.
- **Segments**: Too many segments → slower queries. Merge policy and refresh interval matter.
- **Capacity**: Posting lists for high-cardinality terms (e.g., unique IDs) can be large. Consider whether you need to index those fields for search.

## Inverted Index: Query Optimization

| Query Type | Strategy | Notes |
|------------|----------|-------|
| **Single term** | Direct lookup → posting list | O(1) for term, O(K) for K documents in list |
| **AND (conjunction)** | Intersect posting lists | Use smallest list first; skip-list or binary search for intersect |
| **OR (disjunction)** | Union posting lists | Merge sorted lists |
| **Phrase** | Position check | Both terms must appear; positions must be consecutive |
| **Fuzzy** | Expand to similar terms | "redis" → "redis", "radis", etc.; union posting lists |

**Skip lists**: Posting lists can be augmented with skip pointers for faster intersection—skip ahead when current doc ID is smaller than the other list's current. Reduces comparisons for long lists.

## Elasticsearch Index Lifecycle

```
Document ingest → In-memory buffer → Refresh (every 1s default) → New segment
                                                                    ↓
Older segments ────────────────────────────────────────────► Merge (compaction)
                                                                    ↓
                                                           Fewer, larger segments
```

**Refresh**: Makes documents searchable. Default 1 second. Near-real-time, not immediate.
**Flush**: Writes segment to disk. Durability.
**Merge**: Combines segments. Reduces segment count; reclaims deleted document space.

## L5 vs L6: Search and Inverted Indexes

| Scenario | L5 | L6 |
|----------|-----|-----|
| "Add Elasticsearch for search" | "Index everything, full-text search" | "What's the source of truth? How do we sync? CDC or batch? Never make ES primary. Design mapping for your query patterns." |
| "Search is slow" | "Add more nodes" | "Check: too many segments? High-cardinality fields bloating posting lists? Complex aggregations? Profile with Explain API. Optimize mapping and query." |
| "We need exact match and search" | "Use ES for both" | "ES optimized for full-text. Exact match (e.g., by ID) is better in primary DB or cache. Use ES for search; primary for lookup." |

---

# Summary: Key Takeaways

1. **Cache Key Design**: Include resource type + ID + variant parameters. Exclude timestamps and nonces. Namespace with service. Include tenant for multi-tenant. Key design drives hit rate and correctness.

2. **Cache Poisoning**: Wrong data under a key; persists until TTL. Prevent via: validate before cache, sanitize keys, integrity checks, monitoring. Never cache 5xx. Have recovery runbook (targeted invalidation vs controlled flush).

3. **Redis Persistence**: RDB = snapshots, fast recovery, data loss between snapshots. AOF = command log, less loss, slower recovery. Hybrid = RDB + AOF delta. Use `appendfsync everysec`. Monitor fork time on large instances.

4. **Redis Cluster**: 16,384 hash slots. CRC16(key) mod 16384. MOVED/ASK redirects. Smart clients cache slot→node. Hash tags `{tag}` for multi-key operations. No cross-slot multi-key without hash tags.

5. **Time-Series**: Append-only, time-partitioned, columnar, compression (Gorilla). Downsampling for retention. Use when write-heavy, range queries, long retention. InfluxDB, TimescaleDB, Prometheus.

6. **Inverted Index**: Term → posting list. TF-IDF, BM25 for ranking. Position data for phrases. Elasticsearch/Lucene use segments and merging. Source of truth elsewhere—sync to search index.

---

# Appendix: Interview-Oriented One-Liners

- **"What goes in a cache key?"** — Resource type + ID + variant parameters that affect the response. Never timestamps or nonces.
- **"How do you prevent cache poisoning?"** — Validate before caching (no 5xx), sanitize keys, short TTLs for sensitive data, monitor for anomalies.
- **"RDB vs AOF?"** — RDB = snapshots, fast recovery, loss between snapshots. AOF = command log, less loss, slower recovery. Hybrid = both.
- **"Redis Cluster routing?"** — CRC16(key) mod 16384 → slot. Node owns slot range. MOVED redirect. Smart clients cache slot→node. Hash tags for multi-key.
- **"When time-series DB?"** — Append-heavy, range queries, downsampling, long retention. Use when PostgreSQL can't keep up.
- **"Inverted index?"** — Word → document list. TF-IDF/BM25 for ranking. Elasticsearch/Lucene. Never primary store.

## Extended Interview Q&A

**Q: "Our cache hit rate is 5%. Why?"**
A: Inspect key design. Common causes: (1) Timestamp in key—every request unique. (2) Request hash too specific—slight param change = different key. (3) Keys too generic—user-specific content cached under global key, first user's data cached, others miss. Fix: deterministic key with resource + ID + variant params.

**Q: "Redis lost data after restart. What happened?"**
A: Check persistence config. No persistence = data lost. RDB only = loss since last snapshot. AOF with fsync=no = up to 30 sec loss. Verify `appendonly yes` and `appendfsync everysec` (or `always` for critical). Use hybrid for production.

**Q: "Why does Redis Cluster use hash slots instead of consistent hashing?"**
A: Hash slots (CRC16 mod 16384) give fixed, predictable key distribution. Adding/removing nodes triggers slot migration—well-defined. Consistent hashing can have hotspots. Slots also enable hash tags for co-locating keys.

**Q: "When would you use a time-series DB over PostgreSQL?"**
A: When (1) write volume > 10K points/sec, (2) retention > 90 days with aggregation, (3) need efficient range queries and downsampling, (4) append-only workload. PostgreSQL with timestamp index works for modest scale; time-series DBs optimize for this pattern.

**Q: "How does Elasticsearch differ from a cache?"**
A: ES is a search index built on inverted indexes. Optimized for full-text search, fuzzy matching, aggregations. Cache (Redis) is key-value, O(1) lookup by exact key. ES is not a cache—it's a search engine. Source of truth should be elsewhere; sync to ES.

---

# Troubleshooting Decision Tree: Cache and Redis

```
Symptom: Low cache hit rate
├── Keys include timestamp/nonce?
│   └── Remove from key; use deterministic key
├── Keys too granular (full request hash)?
│   └── Include only variant params that affect response
├── Keys too coarse (global for user-specific)?
│   └── Add user/tenant ID to key
└── TTL too short?
    └── Balance freshness vs hit rate; consider invalidation strategy

Symptom: Cache poisoning / wrong data served
├── Error responses cached?
│   └── Add validation gate: never cache 5xx, empty
├── User input in key without sanitization?
│   └── Sanitize, allowlist, or hash user input
├── Race condition (stale overwrites fresh)?
│   └── Use version in key, or lock on write
└── Recovery: Known bad keys → targeted invalidation
             Widespread → controlled flush, coalesce repopulation

Symptom: Redis data loss on restart
├── No persistence?
│   └── Enable AOF or RDB; match to RPO
├── RDB only, long interval?
│   └── Add AOF with everysec, or hybrid
└── AOF with fsync=no?
    └── Change to everysec or always

Symptom: Redis Cluster CROSSSLOT error
├── Multi-key command (MGET, MULTI)?
│   └── Use hash tags: {id}:field1, {id}:field2
└── Lua script with multiple keys?
    └── Same: hash tags so all keys in same slot

Symptom: Redis slow during BGSAVE
├── Large dataset (50GB+)?
│   └── Fork overhead. Schedule during low traffic; consider smaller shards
└── Disk saturated?
    └── RDB/AOF on separate disk; or faster storage
```

---

# Cross-Topic Integration: How the Pieces Fit

A request that uses caching, Redis Cluster, and potentially search flows through multiple layers:

1. **Key design** determines whether the request hits cache or misses. Bad key = miss = backend load.
2. **Cache poisoning** can corrupt responses even on hits. Validation and sanitization are defenses.
3. **Redis persistence** ensures data survives restarts. Match RDB/AOF/hybrid to data criticality.
4. **Redis Cluster** distributes keys across nodes. Hash tags enable multi-key ops.
5. **Time-series** and **inverted indexes** are specialized stores—use when general-purpose cache or DB doesn't fit the access pattern.

**Staff synthesis**: When designing a system that caches, ask: What's our key design? How do we prevent poisoning? What's our Redis persistence and cluster strategy? When do we need time-series or search instead of cache? These questions connect the internals to the architecture.

---

# Staff Interview Walkthrough: "Design a High-Traffic User Profile Service with Caching"

**Interviewer**: "We need to serve 100K profile reads per second. Discuss cache design, key structure, and Redis internals."

**Strong Answer Structure**:

1. **Key design**: "Profile responses can vary by locale (en-US vs es), API version (v1 vs v2), and possibly A/B test variant. Key format: `profile-svc:user:{userId}:profile:{locale}:{version}`. Deterministic—same request always hits same key. No timestamp. We namespace with service to avoid collisions if we share a Redis cluster with other services. For 100K reads/sec with 80% hit rate, we'd serve 80K from cache, 20K from DB. Hit rate depends on key design—wrong design could give us 10%."

2. **Cache poisoning prevention**: "We never cache 5xx or empty responses. Validation gate before SET. User ID comes from auth token—we don't allow user input to influence the key directly. If we had a bug that cached User B's data under User A's key, we'd need targeted invalidation. Runbook: identify bad keys from reports, DEL those keys, deploy fix. Avoid full flush—would cause stampede. Use request coalescing for repopulation."

3. **Redis persistence**: "Profile data is user-specific, not mission-critical like payments. We'd use hybrid persistence (RDB + AOF) with appendfsync everysec. Accept up to 1 second loss on crash. For session data in same Redis, maybe stricter. Monitor latest_fork_usec—at 100K ops/sec we might have a large dataset; fork could cause latency spikes. Consider smaller shards if fork exceeds 1 second."

4. **Redis Cluster**: "At 100K reads/sec, single Redis might be enough, but for HA we'd use cluster. Keys would distribute across slots via CRC16. If we need to MGET profile + settings for same user, we'd use hash tags: `{user:123}:profile`, `{user:123}:settings`—same slot, atomic multi-key. Smart client (Lettuce, Jedis) to cache slot→node and avoid MOVED redirects."

5. **When NOT to use cache**: "Search across profiles (by name, filters)—that's inverted index, Elasticsearch. Don't cache search results the same way—different access pattern. Time-series (profile view counts, analytics)—time-series DB or aggregations, not cache. Cache is for point lookups by primary key."

**Key Staff Signal**: The candidate connects key design to hit rate, poisoning to validation and recovery, persistence to data criticality, and cluster to multi-key operations. They don't just say "use Redis"—they reason through the internals.

---

# Operational Scenarios — Putting It Together

## Scenario 1: Hit Rate Dropped from 80% to 15%

**Symptom**: Cache hit rate collapsed after a deployment. **Diagnosis**: New deployment changed key format. Keys now include request ID or timestamp. Every request is unique. **Resolution**: Audit key construction in the new code. Remove request-specific values. Restore deterministic key: resource + ID + variant params. Rollback if urgent.

## Scenario 2: Users Reporting Wrong Data (Possible Poisoning)

**Symptom**: Multiple users report seeing another user's data. **Diagnosis**: Either (1) cache poisoning—wrong data under key, or (2) bug serving wrong data without cache. Check: are affected users hitting same key? Correlate user reports with cache keys. **Resolution**: If poisoning: identify bad keys, targeted invalidation, fix validation in code. If not cache: fix application bug. Add validation gate: never cache non-200, non-empty. Add monitoring for single-key read spikes.

## Scenario 3: Redis Restart Lost Session Data

**Symptom**: After Redis restart, all sessions gone. **Diagnosis**: No persistence, or RDB-only with long interval and restart happened between saves. **Resolution**: Enable AOF with appendfsync everysec, or hybrid. For sessions, even 1 second loss may be acceptable (users re-login). For critical data, use always. Document RPO (recovery point objective) and match persistence config.

## Scenario 4: MGET Failing with CROSSSLOT in Redis Cluster

**Symptom**: Application uses MGET for user profile + settings; CROSSSLOT error. **Diagnosis**: Keys hash to different slots. MGET requires same slot. **Resolution**: Use hash tags. Change keys to `{user:123}:profile` and `{user:123}:settings`. Both hash on `user:123`. MGET works. Deploy key format change; migrate or repopulate cache with new keys.

## Scenario 5: Redis Fork Causing Latency Spikes

**Symptom**: p99 latency spikes to 2 seconds every 5 minutes. **Diagnosis**: BGSAVE runs every 5 min (save 300 10). Fork on 40GB dataset takes 1–2 seconds. During fork, Redis can block (depending on version and OS). **Resolution**: Schedule BGSAVE during low-traffic window. Or reduce dataset size per instance—shard into smaller Redis nodes. Monitor latest_fork_usec; alert if > 1_000_000 (1 second). Consider AOF-only if RDB fork is unacceptable (AOF rewrite also forks but can be less frequent).

## Scenario 6: Time-Series Data Overwhelming PostgreSQL

**Symptom**: Metrics table in PostgreSQL: 1M inserts/sec, queries slow, disk full. **Diagnosis**: PostgreSQL not optimized for append-only time-series. B-tree indexes on timestamp grow large; VACUUM can't keep up. **Resolution**: Migrate to time-series DB (InfluxDB, TimescaleDB, Victoria Metrics). Or use PostgreSQL with TimescaleDB extension—hypertables, time-based partitioning, compression. Plan downsampling: 1-sec for 7 days, 1-min for 30 days, 1-hour for 1 year.

## Common Misconceptions

| Misconception | Reality |
|---------------|---------|
| "Longer TTL = better hit rate" | Only if data doesn't change. Stale data can be wrong. Balance TTL with freshness and invalidation. |
| "Cache key should be unique per request" | Unique key = 0% hit rate. Key should be deterministic for same logical request. |
| "Flush cache to fix poisoning" | Flush causes stampede. Target bad keys if known. Controlled flush (shard by shard) if not. |
| "Redis Cluster = consistent hashing" | Redis uses hash slots (CRC16 mod 16384), not consistent hashing. Different mechanics. |
| "AOF means no data loss" | Only with appendfsync always. everysec = up to 1 sec loss. no = up to 30 sec. |
| "Elasticsearch can be our primary database" | ES is a search index. Use for search; sync from primary. Don't treat as source of truth. |
| "Time-series is just PostgreSQL with timestamp" | At scale, TS DBs optimize: partitioning, columnar, compression. PostgreSQL can work for modest scale. |

---

# Recommended Redis Monitoring Commands

```bash
# Overall stats
redis-cli INFO stats
# hits, misses, keyspace_hits, keyspace_misses → hit rate

# Memory
redis-cli INFO memory
# used_memory, used_memory_rss, mem_fragmentation_ratio

# Persistence
redis-cli INFO persistence
# rdb_last_save_time, aof_last_write_status, latest_fork_usec

# Cluster (if cluster mode)
redis-cli -c CLUSTER INFO
redis-cli -c CLUSTER NODES

# Slow log
redis-cli SLOWLOG GET 10

# Key sampling (understand key patterns)
redis-cli --scan --pattern 'user:*' | head -20
```

**Alert thresholds**: Hit rate < 50%, memory > 80% maxmemory, rdb_last_bgsave_status = err, latest_fork_usec > 1_000_000 (1 sec), slow log growing.

---

# Capacity Estimation: Cache and Redis Sizing

## Cache Memory Sizing

| Component | Formula | Example |
|-----------|---------|---------|
| Key size | avg key bytes × num keys | 50 bytes × 10M keys = 500 MB |
| Value size | avg value bytes × num keys | 2 KB × 10M = 20 GB |
| Overhead | ~50–100 bytes per key (Redis) | 10M × 75 ≈ 750 MB |
| **Total** | | ~21 GB + buffer |

**Rule of thumb**: Size for 2× expected growth. Eviction (LRU) kicks in when full; plan to avoid eviction of hot keys.

## Redis Cluster Throughput

| Node spec | Ops/sec (estimate) | Notes |
|-----------|---------------------|-------|
| 4 vCPU, 16 GB | ~50K–100K | Single node |
| 8 vCPU, 32 GB | ~100K–200K | |
| 16 vCPU, 64 GB | ~200K–500K | |

**Bottlenecks**: Network, single-threaded command execution (Redis is mostly single-threaded for commands), persistence (fsync). Scaling: add nodes; data distributes across slots.

## Time-Series Storage (Recap)

| Resolution | Points/day (per metric) | 90-day raw (1 metric) | Compressed (Gorilla) |
|------------|-------------------------|------------------------|----------------------|
| 1 sec | 86,400 | ~7.5M points | ~15 MB |
| 1 min | 1,440 | ~130K points | ~260 KB |
| 1 hour | 24 | ~2,160 points | ~4 KB |

For 10,000 metrics at 1-sec resolution, 90 days: 10K × 15 MB ≈ 150 GB compressed.

## Inverted Index: Storage and Query Cost

| Component | Size (rough) | Notes |
|-----------|--------------|-------|
| Posting list per term | doc_count × (4–8 bytes) compressed | Delta encoding + compression |
| High-cardinality terms | Large lists | e.g., UUID field → every doc different term |
| Query cost (AND) | Intersect smallest lists first | Minimize comparisons |
| Segments | Many small = slower | Merge policy controls |

**Design implication**: Avoid indexing high-cardinality fields for full-text search unless necessary. Field like `user_id` (millions of unique values) creates huge posting lists. Use for exact match in primary store; don't put in ES text field without good reason.

## Summary Table: When to Use What

| Need | Use | Why |
|------|-----|-----|
| Point lookup by key, < 1ms | Redis / Memcached | In-memory, O(1) hash |
| User session, rate limit | Redis (with AOF/hybrid) | Persistence + speed |
| Full-text search | Elasticsearch | Inverted index, BM25 |
| Metrics, monitoring | Prometheus, InfluxDB | Time-series optimized |
| Long-term metrics, downsampling | TimescaleDB, Victoria Metrics | Retention + aggregation |
| Relational, transactions | PostgreSQL | ACID, B-trees |
| Horizontal scale + strong consistency | NewSQL (CockroachDB, Spanner) | Distributed consensus |

**Staff takeaway**: Match the store to the access pattern. Cache for point lookups. Time-series for append-only metrics. Inverted index for search. Don't force one store to do everything.
