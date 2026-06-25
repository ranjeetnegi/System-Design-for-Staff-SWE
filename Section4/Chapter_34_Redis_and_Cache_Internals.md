# Chapter 32: Redis and Cache Internals

## How Redis Actually Works Under the Hood

---

## Before You Start: What This Chapter Is About

The previous chapter (Chapter 31) answered two questions: **what** should you cache, and **when** should you cache it. It covered TTL strategy, eviction policies, and which layers of your system benefit from caching. If you have not read Chapter 31 yet, read it first. This chapter builds directly on top of it.

This chapter answers a different question: **how does Redis work internally**, and what does that mean for the decisions you make as a Staff engineer?

At an L6 interview, you will not be asked "what is Redis." You will be asked questions like these:

- "Your cache hit rate is 5%. What went wrong?" — You need to know what makes a cache key good or bad.
- "Redis lost all its data when the server restarted. How do you fix that permanently?" — You need to know RDB vs AOF persistence.
- "An MGET call is throwing CROSSSLOT errors in production." — You need to know how Redis Cluster distributes keys and how hash tags fix it.
- "Users are seeing wrong data even though the cache has a valid entry." — You need to know how cache poisoning happens and how to recover.

This chapter covers exactly those four topics, in that order.

```
+-------------------+      +--------------------+      +---------------------+      +-------------------+
|  1. KEY DESIGN    |  ->  |  2. POISONING       |  ->  |  3. PERSISTENCE     |  ->  |  4. CLUSTER       |
|                   |      |                    |      |                     |      |                   |
| Why do your keys  |      | Why is the cached  |      | Why did Redis lose  |      | Why did MGET      |
| cause 0% hits?    |      | value WRONG?       |      | data on restart?    |      | throw CROSSSLOT?  |
+-------------------+      +--------------------+      +---------------------+      +-------------------+
```

Read in order — each section builds on the previous.

---

## Section 2: Cache Key Design — The Most Underrated Skill

### 2.1 The Hotel Room Key Analogy

Imagine a hotel key card programmed to open Room 412. That card is **deterministic** — the same card, every time, opens the same door. Now imagine a key card that opens a different room depending on the time of day. You would never find your room.

Cache keys work the same way. A cache key must be **deterministic**: the same logical request must always produce the same key so that the cached value answers this specific request. If the key changes for the same logical request — because you put a timestamp in it, or a random nonce — you will never hit the cache. Your hit rate will be 0%.

**Cache key correctness rule**: same logical request → same key → cache HIT.

---

### 2.2 What a Good Cache Key Must Include

Think about a user profile API: `/api/v2/users/123/profile?lang=en-US`. What goes into the cache key?

You need four things:

**1. Resource type** — what kind of thing are you caching?
- Examples: `user`, `product`, `order`, `feed`

**2. Resource ID** — which specific instance?
- Examples: `123`, `456`, `9f3a...`

**3. Variant parameters** — anything that changes the response for the same resource
- Language (`en-US` vs `es-MX`) → different content
- Role (`admin` vs `viewer`) → different fields visible
- API version (`v1` vs `v2`) → different response structure
- If you miss any of these, a Spanish user gets English content, or a viewer gets admin fields.

**4. Service namespace** — who owns this key?
- Prevents collisions when multiple teams share the same Redis cluster
- Example: `user-svc:`, `order-svc:`, `reporting-svc:`

---

### 2.3 Building a Good Key: Full Example

Scenario: You have a user profile API. It returns different content depending on locale, user role, and API version. You share a Redis cluster with three other teams.

**Bad key:**
```
profile:123
```
What is wrong with this?
- No namespace: `order-svc` might also use `profile:123` for something entirely different
- No locale: English and Spanish users get the same cached response
- No role: admin users see extra fields, but viewers get the admin response
- No version: v1 and v2 have different JSON shapes, but share a cache entry

This key will return wrong data to most users most of the time.

**Good key:**
```
user-svc:user:123:profile:en-US:admin:v2
```

Let us break down every segment:

```
user-svc       :  user  :  123  :  profile  :  en-US  :  admin  :  v2
^               ^         ^      ^            ^          ^         ^
Service         Resource  ID     What we're   Locale     Role      API
namespace       type             caching                           version
(prevents                        (sub-type)
collision)
```

Now:
- `user-svc:user:123:profile:en-US:viewer:v2` → viewer response in English
- `user-svc:user:123:profile:es-MX:admin:v2` → admin response in Spanish
- `user-svc:user:123:profile:en-US:admin:v1` → admin response in English on the old API

Each is a different logical response. Each gets its own cache slot. Correct data every time.

---

### 2.4 The 0% Hit Rate Anti-Patterns

Here are three key design mistakes that guarantee a near-zero hit rate.

**Anti-Pattern 1: Timestamp in the key**
```python
# BAD
key = f"user:{user_id}:profile:{int(time.time())}"
# Result: key changes every second → every request = unique key → 0% hit rate
```

**Anti-Pattern 2: Request nonce**
```python
# BAD
key = f"user:{user_id}:profile:{request.trace_id}"
# Result: every request has a unique trace ID → every request misses → 0% hit rate
```

**Anti-Pattern 3: Full request body hash**
```python
# BAD
key = f"search:{hash(json.dumps(request.body))}"
# Result: tiny unrelated parameter (like a page-load timestamp in body) -> different hash -> miss
```

```
SAME LOGICAL REQUEST  ->  different keys each time  ->  ALWAYS A MISS

  Request A (user 123)  key: user:123:1720000000   MISS -> goes to DB
  Request B (user 123)  key: user:123:1720000001   MISS -> goes to DB
  (one second later)    key: user:123:1720000002   MISS -> goes to DB
                                           ^
                                    timestamp in key
```

Fix: strip out anything time-based, request-specific, or random. Include only things that describe the logical identity of the resource.

---

### 2.5 Multi-Tenant Key Design: The Data Leak Trap

This is one of the most dangerous mistakes in multi-tenant SaaS systems.

Imagine your product is used by Company A and Company B. Both have a user with ID `123` (common with auto-increment primary keys per tenant). Without a tenant prefix, they share the same cache key:

```
WITHOUT tenant prefix:
  Company A, User 123: key = "user:123:profile"
    Cache MISS -> DB returns Company A's data -> stored under "user:123:profile"
  
  Company B, User 123: key = "user:123:profile"   <- same key!
    Cache HIT -> returns Company A's data to Company B's user
    RESULT: data leak across tenants = GDPR violation

WITH tenant prefix:
  Company A: key = "tenant:11:user:123:profile"
  Company B: key = "tenant:22:user:123:profile"
  No collision. No leak.
```

The rule: **if data is scoped to a tenant, always include the tenant ID in the key**.

---

### 2.6 Key Length Trade-offs

Redis stores **all keys in memory**. If you have 50 million cached entries and each key is 200 bytes, that is 10GB just for keys — before storing any values. Key length matters.

Guidelines:
- Keep keys **under 100 bytes** for most use cases
- Long enough to be readable and debuggable
- Short enough to not waste memory

When keys get long:
1. Abbreviate well-known prefixes: `user-svc` → `u-svc`, `product` → `prod`
2. Hash the variable part: if query parameters are long, `SHA1(sorted_params)` → 40 chars

```
Full key (too long, 180 bytes):
  user-service:user-profile:user_id=123:locale=en-US:role=admin:api_version=v2

Abbreviated (55 bytes):
  u-svc:up:123:en-US:admin:v2

Even with hashed params (45 bytes):
  u-svc:up:123:a3f9b2c1
                ^
                SHA1 of "locale=en-US|role=admin|ver=v2"
```

The abbreviation is fine in production. You just need a way to decode it when debugging.

---

### 2.7 The Pagination Key Problem

Pagination creates a subtle invalidation challenge that trips up many engineers.

Suppose you cache pages of a user's feed:
```
feed:user:123:page:1:size:20   -> posts 1-20
feed:user:123:page:2:size:20   -> posts 21-40
feed:user:123:page:3:size:20   -> posts 41-60
```

A new post arrives. Now **every single page is stale simultaneously**. Pages shift: what was post 1 is now post 2. You need to invalidate all N pages at once. But you do not know how many pages exist unless you scan for them.

Three strategies:

```
+------------------+---------------------------+-----------------------+-------------------+
| Strategy         | How it works              | Hit rate              | Invalidation cost |
+------------------+---------------------------+-----------------------+-------------------+
| Short TTL        | Pages expire in 30s       | High during TTL       | Zero: auto-expire |
|                  | Accept stale pages        | ~30s of stale data    |                   |
+------------------+---------------------------+-----------------------+-------------------+
| Versioned keys   | feed:user:123:v:456:pg:2  | Very high             | Single INCR on    |
|                  | Bump version on new post  | Fresh immediately     | version key       |
|                  | Old pages naturally orphan|                       |                   |
+------------------+---------------------------+-----------------------+-------------------+
| Cursor-based     | Cache keyed by post ID,   | Moderate (first page  | Complex: must     |
|                  | not page number           | always stale)         | manage cursors    |
+------------------+---------------------------+-----------------------+-------------------+
```

The **versioned key** strategy is the cleanest for Staff-level design:

```
feed:user:123:v:456:page:1   (current version = 456)
feed:user:123:v:456:page:2

New post arrives -> INCR feed:user:123:version  (version 456 -> 457)

Next request:
  reads version = 457
  key = feed:user:123:v:457:page:1  -> MISS -> fetches fresh data
  Old v:456 entries sit orphaned until TTL expires (no manual cleanup needed)
```

---

### 2.8 Namespacing to Prevent Key Collisions

This is a real type of incident at companies that run shared Redis clusters.

**Real incident scenario**: Team A caches order data under `order:789`. Team B uses the same key format for a reporting job that also uses an entity it calls "order 789" but with completely different data shape. Both teams write to the same Redis cluster. Team B's background job silently overwrites Team A's order cache entry with a different data structure. Team A's service starts throwing deserialization errors at 2 AM.

```
WITHOUT namespacing:
  Team A writes: SET order:789 '{"id":789,"items":[...],"total":99.00}'
  Team B writes: SET order:789 '{"report_id":789,"generated_at":"...","rows":100}'
  
  Team A reads:  GET order:789
  Returns Team B's report data -> JSON parse error in Team A's service

WITH namespacing:
  Team A writes: SET order-svc:order:789 '{"id":789,...}'
  Team B writes: SET reporting-svc:order:789 '{"report_id":789,...}'
  
  No collision. Each team owns their key prefix.
```

Enforce this with **Redis ACLs** (Access Control Lists):
```
# In Redis ACL config:
# order-svc service account can only write to order-svc:* keys
ACL SETUSER order-svc on >password ~order-svc:* +@all
ACL SETUSER reporting-svc on >password ~reporting-svc:* +@all
```

Now even if a team makes a mistake, Redis rejects the write. The collision is impossible.

---

### 2.9 Common Key Patterns Reference Table

```
+---------------------+--------------------------------------------------+--------------------------------+
| Pattern             | Example Key                                      | Notes                          |
+---------------------+--------------------------------------------------+--------------------------------+
| Entity (basic)      | user-svc:user:123                                | type + ID                      |
| Entity field        | user-svc:user:123:email                          | specific field of entity       |
| Service namespaced  | order-svc:order:789:status                       | prevents cross-team collision  |
| Multi-tenant        | tenant:99:user:123:profile                       | required for SaaS products     |
| Paginated list      | feed-svc:feed:123:v:456:page:2                   | versioned pagination           |
| Rate limit          | ratelimit:api-write:ip:203.0.113.5:min:1720000  | includes time window           |
| Session             | session:a3f9b2c1d4e5f6a7                         | opaque token as ID             |
| Feature flag        | flags:svc:order-svc:flag:new-checkout:user:123  | per-user feature flags         |
| Distributed lock    | lock:job:nightly-report:2026-06-14              | includes date for uniqueness   |
| Negative cache      | neg:user-svc:user:99999:exists                  | "this user does NOT exist"     |
| Aggregate/computed  | analytics:product:456:views:2026-06-14          | pre-computed metric + date     |
+---------------------+--------------------------------------------------+--------------------------------+
```

---

## Section 3: Cache Poisoning — Wrong Data Under a Good Key

### 3.1 What Poisoning Means

Imagine a restaurant with a big chalkboard menu. Every morning, staff update the board with today's prices. One day, someone forgets to erase yesterday's prices before adding today's specials. The board now shows a mix of old and new prices. Every customer reads the board and gets charged incorrectly. The kitchen is working fine. The waitstaff are working fine. The problem is the board shows wrong information.

**Cache poisoning** is when the key is correct — it points to the right logical resource — but the **value stored under that key is wrong**. The system operates normally. Requests hit the cache. Hit rate looks great. But users get the wrong data.

This is worse than a cache miss. A cache miss triggers a fresh database read. A cache miss is self-healing. A **poisoned hit silently returns wrong data**, and the system has no way to know on its own that anything is wrong.

```
Cache MISS (safe):
  Request  ->  Cache MISS  ->  DB read  ->  correct fresh data
                                         ->  also stores in cache

Cache HIT (normal):
  Request  ->  Cache HIT  ->  correct data returned  ->  fast, good

Cache HIT (POISONED):
  Request  ->  Cache HIT  ->  WRONG data returned     ->  fast, SILENT CORRUPTION
                              (no error, no warning)
```

---

### 3.2 Five Ways Poisoning Happens

**Cause 1: Application Bug — Write Under the Wrong Key**

A race condition in a user profile service. Two concurrent requests arrive almost simultaneously:
- Request for User 123 starts
- Request for User 456 starts
- Both hit the DB around the same time
- Due to a threading bug, the handler for User 123 accidentally uses User 456's data when writing to the cache

```
Thread A (User 123)         Thread B (User 456)
  reads DB -> gets data_123    reads DB -> gets data_456
  [slow path, context switch]
                               writes: SET user:456 data_456   <- correct
  writes:   SET user:123 data_456   <- BUG: wrong data under user 123's key!
```

Now every request for User 123 returns User 456's profile until TTL expires.

**Cause 2: Error Response Cached**

The database is under load and returns an HTTP 500 error. Your caching code does not check the response status before storing it:

```python
# BAD code:
response = db.get_user(user_id)
cache.set(key, response, ttl=300)   # stores 500 error for 5 minutes!

# Every request for the next 5 minutes:
#   Cache HIT -> returns "Internal Server Error"
#   User thinks the service is broken
#   DB error has cleared but cache still serves the error
```

**Cause 3: Race Condition — Stale Write Overwrites Fresh Write**

This is subtle. Request 1 starts, queries the DB (slow query, 200ms). Request 2 starts 50ms later, queries the DB (uses an index, finishes in 50ms). Request 2 writes fresh data to the cache. Then Request 1 finishes its slow query and writes its result — which is now stale relative to Request 2's result — overwriting the fresh value.

```
Timeline:
  t=0ms    Request 1 starts, reads DB (slow)
  t=50ms   Request 2 starts, reads DB (fast)
  t=100ms  Request 2 finishes DB read, writes FRESH data to cache
  t=200ms  Request 1 finishes DB read, writes STALE data to cache  <- OVERWRITES FRESH!
  t=200ms  Cache now contains stale data
```

Fix: use **compare-and-set** (CAS) — only write to cache if the cache entry was not already written, or include a version number and only write if your version is newer.

**Cause 4: User Input Injected Into Key**

When you build a key from user-supplied input without sanitizing it:

```python
# BAD:
key = "user:" + request.query_params["user_id"] + ":profile"
```

If the user supplies `admin:456` as the user_id:
```
key = "user:admin:456:profile"
```

That might collide with a legitimate admin key. Or the user could enumerate other users' data by crafting key segments. This is key injection — analogous to SQL injection, but for your cache.

```
Attacker input: user_id = "123:profile"
Constructed key: "user:123:profile:profile"

Attacker input: user_id = "456"
Constructed key: "user:456:profile"
                         ^
                         Attacker reads a different user's data
```

**Cause 5: CDN Host Header Poisoning**

A CDN caches responses keyed partly by the `Host` request header. An attacker sends a crafted request with `Host: evil.example.com`. The CDN caches the response under that key. Future legitimate requests to `evil.example.com` are served the attacker's cached response.

This affects any CDN or reverse proxy that does not normalize and validate the Host header before using it as a cache key.

---

### 3.3 Prevention Checklist

These are the five gates every write to the cache should pass through:

```
Before writing to cache, ask ALL of these:

  1. Is the response status 2xx?
     NO  -> do NOT cache (could be a 500 error or transient failure)
  
  2. Is the response body non-empty?
     NO  -> do NOT cache (empty body usually signals an error)
  
  3. Does the response type match the expected schema?
     NO  -> do NOT cache (wrong data shape = deserialization bomb)
  
  4. Was the key built from validated/sanitized inputs only?
     NO  -> sanitize first, or reject the request
  
  5. Is this a 4xx error that I intentionally want to negative-cache?
     YES -> cache with a very short TTL (5-10 seconds max)
     NO  -> do NOT cache 4xx errors
```

Additional defenses:
- **Short TTL for sensitive data**: even if poisoning occurs, it expires quickly. A 5-minute TTL means poison lasts at most 5 minutes.
- **Integrity check**: when caching, also store `hash(value)`. On read, verify the hash before returning. If hashes do not match, treat as a miss.
- **Anomaly monitoring**: a single cache key getting 10× its normal read rate is a signal that something is wrong with that key. Set up alerts.

---

### 3.4 Recovery From Poisoning: Decision Tree

When poisoning is detected, the recovery path depends on what you know:

```
Poisoning detected
        |
        v
Do you know EXACTLY which keys are bad?
        |
   +----+----+
   |         |
  YES        NO
   |         |
   v         v
DELETE    Can you estimate
specific  how many bad keys?
bad keys       |
(targeted   +--+--+
DEL)        |     |
            FEW   MANY / UNKNOWN
            |         |
            v         v
         DEL by    Controlled shard-by-shard flush:
         pattern     1. Flush shard 1
         (SCAN +     2. Wait 60 seconds
          DEL)       3. Flush shard 2
                     4. Wait 60 seconds
                     5. Continue...
                     
                  ALWAYS enable singleflight during flush
                  to prevent stampede
                  
          NEVER:    FLUSHALL -> instant DB overload
                               = takes down entire system
```

**Singleflight** (request coalescing): when 10,000 requests all miss the cache simultaneously, only one DB query runs — the rest wait and share the result. Essential during a flush to protect the DB from stampede.

---

### 3.5 Poisoning Runbook: What a Staff Engineer Does

```
STEP 1 DETECT:    User reports wrong data / anomaly alert fires
                  Inspect: GET <key>, DEBUG OBJECT <key>, TTL <key>

STEP 2 IDENTIFY:  Which keys are bad? Correlate with user IDs and resource types.
                  Check: recent deploys that touched cache writes? DB errors in last hour?

STEP 3 CONTAIN:   Known bad keys -> DEL them directly
                  Unknown pattern -> SCAN 0 MATCH user-svc:user:*:profile COUNT 100
                  (SCAN is non-blocking; never use KEYS in production)

STEP 4 WIDER:     Many keys bad -> enable singleflight, flush one shard at a time,
                  wait 60 seconds between shards, watch DB CPU (keep under 70%)

STEP 5 POST-MORTEM: What let poison in?
                  Add validation gate, fix root cause, update runbook + monitoring.
```

---

## Section 4: Redis Persistence — Surviving Restarts

### 4.1 The Fundamental Problem

Redis is in-memory only. Kill the process — all data is gone. For a pure cache this is acceptable (just a temporary surge of misses). But for other Redis use cases, losing data on restart is catastrophic:
- **Sessions**: users are logged out
- **Rate limiters**: all counters reset to 0 — API protection disappears
- **Leaderboards**: all scores gone
- **Distributed locks**: held locks are silently released

**Persistence** = write data to disk so Redis survives a restart. Two options: **RDB** and **AOF**.

---

### 4.2 RDB — Snapshots: The Photograph Analogy

**RDB** (Redis Database) is like taking a photograph of your data at a point in time.

Every N minutes, Redis takes a complete snapshot of everything in memory and writes it to a file called `dump.rdb`. The file is a compact binary representation of the entire dataset.

How it works without blocking:

```
fork() called
     |
+----+----+
|         |
[Parent]  [Child]
keeps     writes entire dataset
serving   to dump.rdb
requests  (2-10 seconds for large datasets)
               |
          dump.rdb complete, atomically swapped in
          child exits

  Next restart: load dump.rdb -> full state restored
```

**Configuration:**
```
# In redis.conf:
# Save a snapshot if AT LEAST N key changes happened in M seconds
save 3600 1        # after 1 hour if at least 1 key changed
save 300 100       # after 5 minutes if at least 100 keys changed
save 60 10000      # after 1 minute if at least 10,000 keys changed
```

**Data loss window with RDB only:**

```
10:00:00  Snapshot taken (dump.rdb = state at 10:00)
10:04:59  Server crashes
10:05:00  Restart -> loads dump.rdb

  State restored to 10:00:00 -> 4 minutes 59 seconds of changes LOST
```

This is the core trade-off of RDB: **fast restart, but data loss equal to the snapshot interval**.

```
RDB PROS: fast restart (one file load), compact binary, easy to back up to S3
RDB CONS: up to 5+ minutes of data loss on crash, fork overhead on large datasets
```

---

### 4.3 AOF — Append-Only File: The Transaction Log Analogy

A bank does not guess your balance after a crash — it replays every logged transaction. **AOF** (Append-Only File) is the same idea. Every write command Redis executes is appended to `appendonly.aof`.

```
Redis command:                    Appended to AOF file:
  SET user:123 "Alice"    ->    *3\r\n$3\r\nSET\r\n$8\r\nuser:123\r\n$5\r\nAlice\r\n
  INCR counter:visits     ->    *2\r\n$4\r\nINCR\r\n$15\r\ncounter:visits\r\n
  HSET order:789 ...      ->    ... (Redis protocol format)
```

On restart, Redis replays every command from the beginning, arriving at the exact pre-crash state.

```
AOF PROS: near-zero data loss (down to 0 with fsync=always), human-readable format,
          self-healing if file is truncated mid-crash
AOF CONS: slower restart (replays millions of commands), file grows forever without rewrite
```

---

### 4.4 fsync Modes: The Three-Way Trade-off

**fsync** forces the OS to flush its kernel buffers to physical disk. Without it, a `write()` call succeeds but data lives in memory — a power cut before the OS flushes means data loss. Redis AOF offers three modes:

```
+----------------+------------------------------------------+-------------------+----------------------------+
| Mode           | What it does                             | Max data loss     | Write throughput           |
+----------------+------------------------------------------+-------------------+----------------------------+
| always         | fsync after EVERY single command         | ~0 (near zero)    | ~10,000 writes/second      |
|                | OS forced to flush after each write      |                   | (fsync is expensive)       |
+----------------+------------------------------------------+-------------------+----------------------------+
| everysec       | fsync in background, once per second     | Up to 1 second    | ~100,000+ writes/second    |
| (DEFAULT)      | Separate thread handles the flush        |                   | Excellent balance          |
+----------------+------------------------------------------+-------------------+----------------------------+
| no             | Let OS decide when to flush              | Up to 30 seconds  | Fastest possible           |
|                | Typically flushes every 30s on Linux     | (OS buffer window)|                            |
+----------------+------------------------------------------+-------------------+----------------------------+
```

**When to use each:**
- `always`: billing rate-limit counters, audit logs — correctness over throughput
- `everysec`: sessions, leaderboards, user data — the default for most production systems
- `no`: Redis used purely as a disposable cache (rare; almost never correct for persistent data)

```
# redis.conf
appendonly yes
appendfsync everysec    # recommended for most production use
```

---

### 4.5 AOF Rewrite: Solving the "Grows Forever" Problem

Imagine a bank that keeps every transaction since 1980 in one log file and never deletes old entries. To find your current balance, the bank must replay 40 years of transactions. That is 40 years of log file to read on every restart.

AOF has the same problem. A key overwritten 1,000 times has 1,000 log entries, but only the last one matters.

```
BEFORE rewrite:                     AFTER rewrite:
  SET user:123 "v1"                   SET user:123 "v3"
  SET user:123 "v2"                   SET user:456 "Carol"
  SET user:123 "v3"    <-- only this
  SET user:456 "Alice"                File is 80% smaller, restart 80% faster.
  SET user:456 "Bob"
  SET user:456 "Carol" <-- only this
  DEL user:789         <-- deleted, nothing to record
```

Rewrite process: Redis forks a child, child writes minimal command set to a new AOF file, parent buffers new commands, on completion the new file is atomically swapped in plus the buffer is appended.

```
# Configure automatic rewrite:
auto-aof-rewrite-percentage 100    # trigger when AOF is 100% larger than last rewrite size
auto-aof-rewrite-min-size 64mb     # but only if AOF is at least 64MB
```

---

### 4.6 Hybrid Persistence: The Best of Both (Redis 4.0+)

Starting in Redis 4.0, you can use both RDB and AOF together in a smarter way called **hybrid persistence**. This gives you:
- Fast restart (load binary snapshot in seconds)
- Minimal data loss (only replay the short AOF tail since the snapshot)

When an AOF rewrite runs, instead of writing commands in text format, Redis writes the current state as a compact RDB binary snapshot first, then appends new commands in AOF text format after it.

```
appendonly.aof (hybrid enabled):
  +-------------------------+  +-----------------------------+
  | RDB binary snapshot     |  | AOF commands since snapshot |
  | (entire state, compact) |  | (last few seconds only)     |
  +-------------------------+  +-----------------------------+

Restart sequence:
  1. Load RDB section (binary, fast) -> 99% of state in ~2 seconds
  2. Replay short AOF tail           -> remaining seconds
  Total: much faster than pure AOF, much less loss than pure RDB
```

**Configuration (recommended for most production systems):**
```
# redis.conf
appendonly yes
aof-use-rdb-preamble yes    # hybrid mode
appendfsync everysec
```

When an interviewer asks "how do you configure Redis persistence," this is the answer.

---

### 4.7 The Fork Overhead Problem at Scale

Both RDB and AOF rewrite use `fork()`. Linux `fork()` is copy-on-write (COW) for data pages, but **it must always copy the entire page table** (the map of virtual to physical memory addresses). The page table grows proportionally with dataset size.

```
Redis dataset size -> fork time
  1 GB dataset    -> fork takes ~50 milliseconds
  10 GB dataset   -> fork takes ~200-500 milliseconds
  50 GB dataset   -> fork takes ~1-5 seconds   <- PROBLEM
```

During those seconds, **Redis is paused** copying the page table. Requests time out. p99 spikes.

**Detect it:**
```
redis-cli INFO stats | grep latest_fork_usec
latest_fork_usec:250000    # 250ms: warning
latest_fork_usec:1500000   # 1.5s: critical, alert now
```

**Telltale pattern:** p99 latency spikes at perfectly regular intervals (every 5 minutes, every hour) = BGSAVE is the culprit.

```
Time:   03:00:00  03:00:03  03:00:05  03:00:10
p99:    2ms       850ms     1200ms    2ms
                  ^                   ^
             BGSAVE starts       fork completes
```

**Three fixes:**
```
Option 1: Schedule BGSAVE during low-traffic window (3–4 AM)
          Only works if traffic has a clear low point

Option 2: Shard into smaller Redis instances
          1 x 50GB -> 5s fork   vs   5 x 10GB -> 0.5s fork per shard
          Also increases throughput and reduces blast radius

Option 3: Offload persistence to a replica
          CONFIG SET save "" on master  (master never forks, never pauses)
          CONFIG SET save "3600 1" on replica  (replica handles all snapshots)
```

Alert threshold: `latest_fork_usec` > 1,000,000 (1 second) → open a ticket to shard or offload.

---

## Section 5: Redis Cluster — Scaling Beyond One Node

### 5.1 Why You Need Redis Cluster

A single Redis node holds roughly **100-150GB of data** and handles ~**1 million ops/second**. For many products that is enough. But a large social network has 100M users × 500 bytes per session = 50GB just for sessions, plus another 200GB for feeds and caches, with 830K ops/sec at peak. One node cannot hold 250GB. You need **Redis Cluster**: data and load distributed across multiple nodes.

---

### 5.2 The Problem With Naive Sharding

**Range-based sharding** ("users 1-1000 on Node 1, 1001-2000 on Node 2") fails badly when you add a node: you must move huge ranges of data between nodes, hours of disruption for a large dataset.

**Consistent hashing** (used by Memcached) is better — adding a node moves only adjacent arc data — but hot spots develop when popular keys cluster on one node.

Redis Cluster chose a different approach: **fixed hash slots**.

---

### 5.3 How Redis Cluster Works: 16,384 Hash Slots

Redis Cluster divides the entire key space into exactly **16,384 slots**, numbered 0 through 16,383.

Every key maps to exactly one slot using this formula:
```
slot = CRC16(key) mod 16384
```

CRC16 is deterministic: same key always produces the same slot. Routing depends entirely on this. Each node owns a contiguous range of slots. In a 3-node cluster:

```
16,384 slots divided across 3 nodes:

Slot:   0                   5460  5461              10922  10923              16383
        |____________________|    |__________________|     |__________________|
               Node A                   Node B                   Node C
            (slots 0-5460)          (slots 5461-10922)      (slots 10923-16383)

Each node owns ~5,461 slots (about 1/3 of the total).
```

To find which node owns a key: `CRC16("user:123") mod 16384 = 5798` → slot 5798 is in range 5461-10922 → **Node B** owns it.

---

### 5.4 Request Routing: MOVED Redirects

A client can send a request to any node. That node handles it if it owns the key's slot, or sends a redirect.

```
Client: GET user:123  ->  Node A
Node A: slot = CRC16("user:123") mod 16384 = 5798 -> owned by Node B
Node A: -MOVED 5798 10.0.0.2:6379
Client: retries GET user:123  ->  Node B  ->  returns value
```

MOVED = permanent redirect. The client updates its local map: "slot 5798 is at Node B" — next time it goes directly there. **Smart Redis clients** (Jedis Cluster, Lettuce for Java; redis-py-cluster; ioredis for Node.js) do this automatically: on startup they fetch the full slot-to-node map via `CLUSTER SLOTS`, cache it locally, and route directly with zero redirects for the steady state. On a MOVED response they refresh the affected entry and retry.

---

### 5.5 ASK Redirect During Slot Migration

When a node is added or removed, slots migrate between nodes. Keys in a migrating slot can be on the source, the destination, or in transit. Redis handles this with a second redirect type: **ASK**.

```
During migration of slot 5798 from Node B to Node D:

Client sends: GET user:123  to Node B (slot 5798, partially migrated)

If the key hasn't been moved yet:
  Node B handles it normally

If the key HAS been moved to Node D:
  Node B responds: -ASK 5798 10.0.0.4:6379
  
Client:
  Sends ASKING to Node D  (this is a one-time permission token)
  Sends GET user:123 to Node D
  Node D handles it
```

Key difference between MOVED and ASK:
```
MOVED  -> permanent: update your slot map, always go here from now on
ASK    -> temporary: do NOT update your map, migration in progress
                     just try this one request at the new node
```

This distinction is critical. If a client incorrectly treated ASK as MOVED during a migration, it would update its map too early and route some keys to the wrong node.

---

### 5.6 The CROSSSLOT Problem and Hash Tags

Here is where many engineers run into trouble with Redis Cluster for the first time.

Multi-key commands — `MGET`, `MSET`, `DEL` with multiple keys, `MULTI`/`EXEC` transactions, Lua scripts — require all the keys involved to be on the **same node** (same slot). If they are on different nodes, Redis Cluster cannot execute the command atomically.

```
Without hash tags:
  MGET user:123:profile user:123:settings user:123:preferences
  
  CRC16("user:123:profile")     mod 16384 = 4821  -> Node A
  CRC16("user:123:settings")    mod 16384 = 9143  -> Node B
  CRC16("user:123:preferences") mod 16384 = 13002 -> Node C

  Redis Cluster returns:
    CROSSSLOT Keys in request don't hash to the same slot
```

The fix is **hash tags**: put the routing portion of the key in curly braces `{}`. Redis Cluster hashes only the content of the **first** `{}` block, ignoring the rest.

```
{user:123}:profile      -> CRC16("user:123") mod 16384 = 6542 -> Node B
{user:123}:settings     -> CRC16("user:123") mod 16384 = 6542 -> Node B
{user:123}:preferences  -> CRC16("user:123") mod 16384 = 6542 -> Node B

MGET {user:123}:profile {user:123}:settings {user:123}:preferences
All on Node B -> command succeeds

Rules:
  "{user:123}:profile"          -> hashes "user:123" only
  "abc{user:123}def{other}ghi"  -> hashes "user:123" only (first {} wins)
  "no-braces"                   -> hashes entire key (normal behavior)
```

**Trade-off:** hash tags concentrate keys onto one node. A very active user can create a hot spot. Use hash tags for atomicity requirements, not as the default key format.

---

### 5.7 Replication Within Redis Cluster

Each master has one or more replicas receiving writes asynchronously. Standard topology: 3 masters × 1 replica each (6 total nodes).

```
Node A master (slots 0-5460)         <-> Node A-replica
Node B master (slots 5461-10922)     <-> Node B-replica
Node C master (slots 10923-16383)    <-> Node C-replica
```

**Failover**: if Node B stops responding to PING, after ~15 seconds of timeout, Node B-replica is promoted to master and the cluster updates routing for slots 5461-10922. Total failover time: **15-30 seconds**. During failover, requests to those slots fail — design your app to retry with exponential backoff.

---

### 5.8 Sentinel vs Cluster: When to Use Each

```
+-------------------+-----------------------------------------------+------------------------------------------+
| Mode              | What it does                                  | When to use                              |
+-------------------+-----------------------------------------------+------------------------------------------+
| Redis Sentinel    | High availability for ONE logical Redis       | Your data fits on one server             |
|                   | instance (1 master + N replicas)              | You need automatic failover but NOT      |
|                   | Sentinel processes monitor and auto-failover  | horizontal scaling                       |
|                   |                                               | Simpler: no slot management, no hash tags|
+-------------------+-----------------------------------------------+------------------------------------------+
| Redis Cluster     | Horizontal scale: data split across           | Data does NOT fit on one server          |
|                   | multiple masters (each owns a slot range)     | OR throughput exceeds one node's limit   |
|                   | Each master has replicas for HA               | Requires smart clients                   |
|                   |                                               | Multi-key ops need hash tags             |
+-------------------+-----------------------------------------------+------------------------------------------+
```

A common mistake: using Redis Cluster when Sentinel would suffice. Cluster adds real operational complexity — slot management, hash tags for multi-key ops, smart clients required. Start with Sentinel. Only move to Cluster when you have concrete evidence a single node is the bottleneck.

```
Decision:
  Data fits on one server (<100GB) AND throughput <1M ops/sec?  -> Sentinel
  Data does NOT fit on one server, OR throughput exceeds limits? -> Cluster
```

---

## Chapter 32 Summary: What to Remember for the Interview

**"Why is your cache hit rate 5%?"**
Key is non-deterministic: timestamp, nonce, or overly specific parameter included. Strip anything time-based or request-specific. Include only resource type, ID, stable variant parameters, and service namespace.

**"Redis lost all data on restart."**
Persistence not enabled or only RDB with a long snapshot interval. Fix: hybrid persistence — `appendonly yes` + `aof-use-rdb-preamble yes` + `appendfsync everysec`. Fast restarts AND minimal data loss.

**"MGET fails with CROSSSLOT."**
Keys hash to different slots. Fix: hash tags — `{user:123}:profile` and `{user:123}:settings` both route via `user:123`, landing on the same node.

**"Cache is serving wrong data."**
Poisoning: a bug, race condition, error response, or key injection wrote bad data under a valid key. Fix: validation gate before every write (check status, schema, sanitize keys). Recover with targeted DEL, or controlled shard-by-shard flush with singleflight.

```
+------------------+---------------------------+------------------------------------------+
| Topic            | The mistake               | The fix                                  |
+------------------+---------------------------+------------------------------------------+
| Key design       | Timestamp / nonce in key  | Deterministic keys: type + ID + stable   |
|                  |                           | variant params + namespace               |
+------------------+---------------------------+------------------------------------------+
| Poisoning        | No validation before      | Validate status + schema before caching  |
|                  | caching, error cached     | Sanitize user inputs in keys             |
+------------------+---------------------------+------------------------------------------+
| Persistence      | No persistence, or only   | Hybrid: RDB preamble + AOF everysec      |
|                  | RDB with long interval    |                                          |
+------------------+---------------------------+------------------------------------------+
| Cluster          | Keys hash to different    | Hash tags: {user:123}:profile            |
|                  | slots (CROSSSLOT error)   | ensures co-location on same slot         |
+------------------+---------------------------+------------------------------------------+
```

**What separates L5 from L6 answers:**
- The interaction between fork() and COW write amplification during BGSAVE on a 50GB instance
- Why MOVED and ASK are different (permanent vs temporary redirect during slot migration)
- That `aof-use-rdb-preamble yes` exists and is strictly better than pure AOF for production
- That multi-tenant systems without tenant ID in the key are a GDPR time bomb
- That versioned key pagination beats KEYS-pattern scanning for invalidation at scale

Those are the details that show you have operated Redis at scale, not just read the docs.

---

*Next: Chapter 33 covers messaging systems — Kafka internals, consumer groups, partition assignment, and designing event-driven systems that do not lose messages or process them twice.*
# Chapter 32 — Part B: Redis and Cache Internals
### Time-Series Databases, Inverted Indexes, and Operational Mastery

---

## Table of Contents

1. Time-Series Databases: Why Normal Databases Struggle With Metrics
2. Inverted Index: How Search Engines Find Documents
3. Operational Scenarios: Putting It All Together
4. Cross-Topic Integration: How Cache Internals Connect

---

## 1. Time-Series Databases: Why Normal Databases Struggle With Metrics

### What is time-series data?

Picture a hospital that has 500 patients, each wearing a heart-rate monitor. Every 5 seconds, every monitor sends a reading to a central server. That is 100 readings per second, 8.64 million readings per day, 3.15 billion readings per year — and not a single reading is ever updated. You only ever append new ones.

That is **time-series data**: measurements where **time is the primary dimension**, the data only flows forward, and you almost never go back to change old values.

Time-series data is everywhere:

- Stock prices: AAPL closes at $195.42 at 4pm. That record is immutable. Tomorrow it gets a new record.
- Server CPU usage: your monitoring system records CPU every 10 seconds on every machine.
- IoT sensors: temperature, humidity, vibration — thousands of sensors each sending readings constantly.
- Application metrics: request latency, error rate, active users — your dashboards depend on these.

The four defining characteristics:

1. **Always appended** — new readings come in constantly. Old readings are never changed.
2. **Time-ordered** — queries are almost always "give me readings between 2pm and 4pm" or "show me the last 24 hours".
3. **High write volume** — 1,000 IoT sensors each sending 10 readings per second = 10,000 writes per second. Sustained, forever.
4. **Needs downsampling** — keeping every second of data for 5 years is impossible. You need to squash old data into hourly or daily averages.

### The PostgreSQL problem with metrics at scale

Imagine you are a junior engineer at a startup and you need to store server CPU metrics. You know PostgreSQL. So you create a table:

```sql
CREATE TABLE metrics (
    id          BIGSERIAL PRIMARY KEY,
    recorded_at TIMESTAMPTZ NOT NULL,
    metric_name TEXT NOT NULL,
    value       FLOAT NOT NULL
);

CREATE INDEX ON metrics (recorded_at);
```

Looks fine. Let's do the math on what actually happens.

**At 10,000 metric writes per second:**

```
10,000 writes/sec × 86,400 seconds/day = 864,000,000 rows per day
                                        = 864 million rows every single day
```

After one week: 6 billion rows. After one month: 25 billion rows.

**The B-Tree index problem:**

PostgreSQL's default index is a **B-Tree** (short for Balanced Tree). It is excellent for general-purpose lookups. But for time-series data, it has a fundamental problem.

A B-Tree is like a phone book sorted alphabetically — you can flip to the right section fast. But think about what happens when you are constantly adding new entries: the phone book keeps growing. The tree nodes split. The index pages on disk get shuffled around. Every new write must update the tree at the right position, and that position requires reading multiple index pages from disk.

At 864 million rows per day, the B-Tree index grows to **hundreds of gigabytes**. Inserting into it requires reading and writing multiple disk pages per insert. At 10K writes per second, PostgreSQL simply cannot keep up.

```
PostgreSQL row-oriented B-Tree storage (what you get by default):

Disk page 1: [row][row][row][row][row][row][row]   <- rows from 3 months ago
Disk page 2: [row][row][row][row][row][row][row]   <- rows from 3 months ago
...
Disk page 8,000,000: [row][row][row][row][row]    <- rows from yesterday
Disk page 8,000,001: [row][row][row][row][row]    <- rows from today

B-Tree index:
         [2023-01 ... 2025-06]
          /                  \
  [2023-01..2024-01]     [2024-01..2025-06]
    /           \             /           \
[2023-01]   [2023-07]   [2024-01]    [2025-01]
   |             |           |            |
[page IDs] [page IDs]  [page IDs]   [page IDs]

Problem: Every new write touches the rightmost leaf of this tree.
         At 10K writes/sec, that leaf is a hot spot — all writers
         compete for the same tree node. Contention explodes.

Range query "last 24 hours":
  Must traverse the B-Tree to find the start timestamp,
  then read ALL pages between that point and now.
  At 864M rows/day, that is millions of disk page reads.
```

**The VACUUM problem:**

When you eventually delete old data (say, data older than 1 year), PostgreSQL does not immediately reclaim that space. It marks rows as "dead" and waits for VACUUM to clean them up. But VACUUM is a background process. At 10K writes per second with 864M new rows per day, VACUUM cannot keep up. The table bloats with dead rows, queries slow further, and disk usage skyrockets.

**The reality:** PostgreSQL handles roughly **1,000 to 5,000 metric writes per second** on typical hardware before these problems become severe. At 10K+ writes per second, you need a purpose-built time-series database.

---

### How time-series databases solve this

Time-series databases are not magic. They are databases engineered specifically around the four characteristics of time-series data. Here are the four techniques they use.

---

#### Technique 1: Time-Based Partitioning

Instead of one giant table, the database automatically splits data into **time buckets** — each bucket covers a fixed window (one hour, one day, or one week).

```
Time-partitioned storage (what TimescaleDB / InfluxDB do):

2025-06-01 |== partition ==|   <- sealed, compressed, read-only
2025-06-02 |== partition ==|   <- sealed, compressed, read-only
2025-06-03 |== partition ==|   <- sealed, compressed, read-only
2025-06-04 |== partition ==|   <- sealed, compressed, read-only
2025-06-05 |== partition ==|   <- sealed, compressed, read-only
2025-06-06 |== partition ==|   <- sealed, compressed, read-only
2025-06-07 |== partition ==| * <- active write target (today)

Query: "Show me data from June 3 to June 5"
  -> touches exactly 3 partitions, skips all others
  -> No B-Tree traversal across 6 billion rows
  -> Directly open 3 partition files and read them

PostgreSQL with same data:
  -> Must scan B-Tree to find start point
  -> B-Tree spans ALL rows ever written
  -> Then reads disk pages scattered everywhere
```

The key insight is that old partitions are **frozen**: once a time window passes, no new writes go into that partition. A frozen partition can be compressed aggressively because its contents will never change. A range query "last 7 days" only needs to open 7 partition files — not traverse a tree spanning years of data.

TimescaleDB (a PostgreSQL extension) does this automatically. You declare a table as a "hypertable" and it handles the partitioning transparently. You still write normal SQL.

---

#### Technique 2: Columnar Storage

This one requires understanding how databases physically store rows on disk.

**Row-oriented storage** (how PostgreSQL stores data by default):

Each disk block holds complete rows, packed one after another.

```
Row-oriented storage:

Block 1: [10:00:00 | cpu_usage | 45.2] [10:00:01 | cpu_usage | 45.8] [10:00:02 | cpu_usage | 44.9]
Block 2: [10:00:03 | cpu_usage | 46.1] [10:00:04 | cpu_usage | 45.5] [10:00:05 | cpu_usage | 47.2]

To read just the VALUES for one hour:
  -> Must read EVERY block (because timestamp and metric_name are mixed in)
  -> For 3600 seconds of data: read 3600 full rows
  -> You wanted: 45.2, 45.8, 44.9, 46.1, 45.5, 47.2
  -> You got:    timestamp + metric_name + value, repeated 3600 times
  -> Wasted I/O: roughly 2/3 of every byte read was unnecessary
```

**Columnar storage** (how time-series DBs store data):

Each disk block holds values from ONE column only. All timestamps together. All values together. All metric names together.

```
Columnar storage:

Timestamps block: [10:00:00] [10:00:01] [10:00:02] [10:00:03] [10:00:04] [10:00:05]
Values block:     [   45.2 ] [   45.8 ] [   44.9 ] [   46.1 ] [   45.5 ] [   47.2 ]
Metric names:     [cpu_usage] [cpu_usage] [cpu_usage] [cpu_usage] [cpu_usage] [cpu_usage]

To read just the VALUES for one hour:
  -> Open only the Values block
  -> Read 3600 floats sequentially
  -> Zero wasted I/O from timestamps or metric names
  -> Sequential disk read = maximum throughput
```

The practical impact: for typical dashboard queries that aggregate values over time (average CPU, max memory, sum of requests), columnar storage gives **5 to 10 times less I/O** than row storage. Queries that took 30 seconds now take 3.

Compression also dramatically improves with columnar storage. A column of timestamps that are all 10 seconds apart is extremely repetitive — it compresses 10 to 20 times better than rows where timestamp, string, and float are interleaved.

---

#### Technique 3: Gorilla Compression (Invented at Facebook)

Facebook's monitoring system needed to store hundreds of billions of data points per day in 2015. They published a paper describing how they compressed time-series data by 12x on average. The technique is called **Gorilla** (also called delta-of-delta + XOR encoding).

The insight: **time-series data is extremely predictable**. CPU readings do not jump from 45% to 9000% between consecutive seconds. Timestamps are almost always exactly 10 seconds apart. This predictability means you can store the *deviation from the expected* rather than the actual value, and deviations are tiny numbers that compress extremely well.

**Part 1: Timestamp compression (delta-of-delta encoding)**

Start with raw timestamps (one reading every 10 seconds):

```
Raw timestamps:     10:00:00  10:00:10  10:00:20  10:00:30  10:00:40
                    (stored as Unix timestamps, 8 bytes each = 40 bytes total)

Step 1 — compute deltas (difference from previous):
Deltas:             ---         10        10        10        10
                    (all 10s — regular interval)

Step 2 — compute delta-of-deltas (difference of the differences):
Delta-of-deltas:    ---        ---         0         0         0
                    (zeros! The intervals are perfectly regular)

Encoding:
- Zero delta-of-delta = 1 bit (just store "0")
- Instead of 8 bytes (64 bits) per timestamp, store 1 bit for regular intervals
- Savings: 64x compression for perfectly regular time series

What about irregular timestamps? (e.g., a delayed reading):
Raw:     10:00:00  10:00:10  10:00:20  10:00:31  10:00:40
Deltas:     ---       10        10        11        9
D-of-D:     ---      ---         0        +1       -2

+1 and -2 are tiny numbers -> stored with variable-length encoding
A small non-zero delta-of-delta costs ~5 bits instead of 64 bits
```

**Part 2: Value compression (XOR encoding)**

CPU readings that barely change between samples:

```
Raw values:   45.2%  46.1%  45.8%  45.9%  46.2%

In IEEE 754 float binary (64 bits each):
45.2: 0100000001000110100110011001100110011001100110011010
46.1: 0100000001000111000011001100110011001100110011001101
45.8: 0100000001000110111010111000010100011110101110000101
45.9: 0100000001000110111100110011001100110011001100110011

XOR consecutive values (highlight the bits that CHANGED):
45.2 XOR 46.1: 0000000000000001100101010101010101010101010101010111
               |                                                      |
               Most bits are ZERO (unchanged) -- only last 20 bits changed

Key observation: when consecutive values are close, XOR has many leading zeros.
Encoding: store only the number of leading zeros + the meaningful non-zero bits.
Result: instead of 64 bits, store ~12-15 bits for small changes.

Full example: encode 5 values
  First value:   45.2 -> stored in full: 64 bits
  Change to 46.1 -> XOR has 17 leading zeros -> store: (leading zeros = 17) + (non-zero portion = ~20 bits) = ~25 bits
  Change to 45.8 -> large jump -> ~40 bits
  Change to 45.9 -> tiny change -> ~12 bits
  Change to 46.2 -> tiny change -> ~10 bits

  Total: 64 + 25 + 40 + 12 + 10 = 151 bits
  Raw:   5 × 64 = 320 bits
  Compression ratio: 320/151 = ~2.1x just for values

Combined with timestamp compression and metric name deduplication:
  Real-world result: ~12 bytes/point raw -> ~1-2 bytes compressed = 6-12x overall
```

This is why Facebook could keep 26 hours of full-resolution metrics entirely in RAM for fast querying — compression made it feasible.

---

#### Technique 4: Downsampling

No matter how good your compression is, keeping 1-second resolution for 5 years is impractical. The solution is **downsampling**: as data ages, compress it into lower-resolution aggregates.

```
Data retention tiers (typical configuration):

NOW -----> 7 days -----> 30 days -----> 1 year -----> 5 years
  1-second    1-minute      1-hour        1-day

Timeline visualization:

|<------ 7 days ------->|<-- 23 days -->|<--- 11 months -->|<--- 4+ years --->|
[sssssssssssssssssssssss][mmmmmmmmmmmmm ][hhhhhhhhhhhhhhhhh][ddddddddddddddddd]

s = 1-second data points (full resolution, hot data)
m = 1-minute data points (each point = avg/min/max of 60 seconds)
h = 1-hour data points   (each point = avg/min/max of 60 minutes)
d = 1-day data points    (each point = avg/min/max of 24 hours)

Storage savings per step:
1 second -> 1 minute: 60x fewer points
1 minute -> 1 hour:   60x fewer points
1 hour -> 1 day:      24x fewer points

Practical example for ONE metric on ONE host:
  1-second for 7 days:  7 × 86,400 × 2 bytes = ~1.2 MB
  1-minute for 30 days: 30 × 1,440 × 2 bytes = ~86 KB
  1-hour for 1 year:    365 × 24 × 2 bytes    = ~17 KB
  1-day for 5 years:    5 × 365 × 2 bytes     = ~3.6 KB

Total per metric: ~1.3 MB
For 10,000 metrics: ~13 GB -- easily fits in a medium-sized server
```

The trade-off: once 1-second data is aggregated to 1-minute, you can no longer ask "what happened exactly at 10:00:37?" You can only ask "what was the average between 10:00 and 10:01?" For most use cases (dashboards, alerting, capacity planning), this is completely fine. You only need second-level resolution for very recent debugging.

---

### Time-series database options compared

| System | Storage Engine | Best For | Typical Retention |
|--------|---------------|----------|-------------------|
| Prometheus | Custom TSDB (local disk) | Infrastructure metrics, Kubernetes alerting | Short-term (days to weeks) |
| InfluxDB | TSM (Time-Structured Merge) | IoT, application metrics, moderate scale | Medium to long-term |
| TimescaleDB | PostgreSQL extension + columnar | SQL queries needed, existing PG team, joins | Long-term |
| VictoriaMetrics | Custom compressed store | Prometheus-compatible, very large scale | Long-term |
| Apache Druid | Columnar + OLAP segments | Time-series combined with analytics queries | Long-term |

**The staff engineer decision framework:**

- Use a time-series DB when: more than 5,000 metric writes per second, retention beyond 90 days with aggregation needed, downsampling is required.
- Use PostgreSQL when: fewer than 1,000 writes per second, already have PostgreSQL infrastructure, need SQL joins from metrics to other tables.
- Use TimescaleDB as the middle ground: PostgreSQL SQL syntax, time partitioning automatically, columnar compression, downsampling policies — all without leaving the PostgreSQL ecosystem.

---

### Capacity estimation worked example

Scenario: 1,000 IoT temperature sensors, each sending one reading every 10 seconds.

```
Step 1: Write rate
  1,000 sensors × (86,400 seconds / 10 second interval) = 8,640,000 points/day
  = 8.64 million data points per day
  = 100 writes per second (comfortable for any TSDB)

Step 2: Raw storage
  8.64M points × 12 bytes/point (8-byte timestamp + 4-byte float) = 103.7 MB/day uncompressed

Step 3: After Gorilla compression (8x average)
  103.7 MB / 8 = ~13 MB/day compressed

Step 4: With retention policy
  7 days at 1-second:   7 × 13 MB  = 91 MB
  30 days at 1-minute:  30 × (13/60) MB = 6.5 MB
  1 year at 1-hour:     365 × (13/3600) MB = 1.3 MB
  5 years at 1-day:     5×365 × (13/86400) MB = 0.27 MB

  Total: ~99 MB for 5 years of data for all 1,000 sensors combined.
  This fits entirely in RAM on a single machine.

Real-world scaling rule:
  For 1,000 sensors: single InfluxDB node, 4GB RAM, 500GB SSD is vastly over-provisioned
  For 100,000 sensors: single large InfluxDB node or small cluster
  For 10 million sensors (industrial scale): VictoriaMetrics cluster
```

---

## 2. Inverted Index: How Search Engines Find Documents

### The library card catalog analogy

Imagine you walk into a library and ask: "Which books mention machine learning on more than three pages?"

A traditional catalog is organized as **Book → [information about that book]**. You would have to pick up every single book, flip through it, and count occurrences of "machine learning." With 200,000 books, that takes years.

Now imagine a different kind of catalog. Instead of organizing by book, it organizes by word: **Word → [list of books containing that word]**. You look up "machine learning", and the catalog immediately hands you a list of 847 books. That is an **inverted index**.

```
Forward index (traditional catalog, useless for text search):
  "Operating Systems: Three Easy Pieces" -> [author: Arpaci-Dusseau, year: 2018, ...]
  "Designing Data-Intensive Applications"  -> [author: Kleppmann, year: 2017, ...]
  "Clean Code"                             -> [author: Martin, year: 2008, ...]

Inverted index (what search engines use):
  "database"  -> [Designing Data-Intensive Applications, Clean Code, ...]
  "process"   -> [Operating Systems: Three Easy Pieces, Clean Code, ...]
  "refactor"  -> [Clean Code, ...]
  "consensus" -> [Designing Data-Intensive Applications, ...]
```

It is called "inverted" because you invert the direction of the mapping: instead of document → words, you build word → documents.

---

### Building an inverted index from scratch

Start with three documents:

```
Doc 1: "Redis is fast"
Doc 2: "Redis uses memory"
Doc 3: "Memcached is also fast"
```

**Step 1: Tokenize** — split each document into individual words (tokens), lowercase them, remove punctuation.

```
Doc 1 tokens: [redis, is, fast]
Doc 2 tokens: [redis, uses, memory]
Doc 3 tokens: [memcached, is, also, fast]
```

**Step 2: Build the index** — for each token, record which documents contain it.

```
Document corpus:                    Inverted Index:
+--------+---------------------+    +------------+---------------+
| Doc ID | Content             |    | Term       | Documents     |
+--------+---------------------+    +------------+---------------+
|   1    | Redis is fast       |    | redis      | [1, 2]        |
|   2    | Redis uses memory   |    | is         | [1, 3]        |
|   3    | Memcached is also   |    | fast       | [1, 3]        |
|        | fast                |    | uses       | [2]           |
+--------+---------------------+    | memory     | [2]           |
                                    | memcached  | [3]           |
                                    | also       | [3]           |
                                    +------------+---------------+
```

That right-hand table is the inverted index. Building it once lets you answer any search query in milliseconds, regardless of how many documents exist.

---

### Posting lists: the core data structure

The list of document IDs for a given term is called a **posting list** (or **postings**). It is the heart of an inverted index.

```
Posting list for "fast": [1, 3]
Posting list for "redis": [1, 2]

At web scale (billions of documents):
Posting list for "the":       [1, 2, 3, 4, 5, ... 800,000,000]   <- billions of entries
Posting list for "consensus": [44, 1203, 987654, 1000003]        <- thousands of entries
```

Storing billions of document IDs requires compression. The key technique is **delta encoding**: instead of storing absolute IDs, store the *difference* from the previous ID.

```
Raw posting list:      [1,   100,   10000,  10001,  50000]
                        (each ID stored as a 4-byte integer = 20 bytes total)

Delta-encoded:         [1,    99,    9900,      1,  39999]
                        (first value as-is, then differences)

Why this helps:
  99 and 1 are small numbers. Small numbers compress well.
  Variable-length encoding: small numbers take 1-2 bytes instead of 4.
  Result: the same list might take 8-10 bytes instead of 20 bytes.

Sorted order is required for delta encoding to work.
That is why posting lists are always kept sorted by document ID.
```

For phrase searches, the index also stores **positions**: not just which document contains a term, but at which word offset within that document.

```
Posting list with positions:
"redis"     -> [(Doc 1, pos 0), (Doc 2, pos 0)]
"is"        -> [(Doc 1, pos 1), (Doc 3, pos 1)]
"fast"      -> [(Doc 1, pos 2), (Doc 3, pos 3)]

Doc 1: "Redis[0] is[1] fast[2]"
Doc 3: "Memcached[0] is[1] also[2] fast[3]"
```

---

### Querying the inverted index: AND, OR, Phrase

**AND query: "redis" AND "fast"**

Goal: find all documents containing BOTH terms.

```
Posting list for "redis": [1, 2]
Posting list for "fast":  [1, 3]

Two-pointer intersection (both lists are sorted):

  i ->  [1, 2]   j -> [1, 3]
        ^              ^
  redis[i]=1, fast[j]=1  -> MATCH! Add Doc 1 to results. Advance both.

  i ->  [1, 2]   j -> [1, 3]
           ^               ^
  redis[i]=2, fast[j]=3  -> 2 < 3, advance i.

  i -> [1, 2]   (i past end, stop)

Result: [Doc 1]

Algorithm: O(n + m) where n = size of first list, m = size of second list.

Optimization: always start the intersection with the SMALLEST posting list.
  If one list has 3 entries and another has 3,000,000,
  starting with the 3-entry list means at most 3 steps before you are done.

Posting list: [1, 2]     Posting list: [1, 3]
             +---+---+               +---+---+
             | 1 | 2 |               | 1 | 3 |
             +---+---+               +---+---+
              ^                       ^
              Match (both = 1) --------+------> Add Doc 1
                  advance both pointers
                  ^
                  redis=2, fast=3 -> 2 < 3, advance redis pointer
                  (past end) -> done
```

**OR query: "redis" OR "fast"**

Union the two lists: [1, 2] union [1, 3] = [1, 2, 3]. All three documents match.

**Phrase query: "redis is"**

Phrase queries require positions. "redis" and "is" must appear in the same document AND "is" must be exactly one position after "redis".

```
Step 1: Find documents containing BOTH "redis" AND "is".
  "redis" -> [Doc 1 (pos 0), Doc 2 (pos 0)]
  "is"    -> [Doc 1 (pos 1), Doc 3 (pos 1)]
  Intersection: Doc 1 (both terms appear in Doc 1)

Step 2: Check positions within Doc 1.
  "redis" in Doc 1: position 0
  "is" in Doc 1:    position 1
  Difference: 1 - 0 = 1 (exactly what we need for adjacent words)
  -> PHRASE MATCH: Doc 1 contains "redis is"

If "redis" was at position 0 and "is" was at position 5:
  Difference: 5 - 0 = 5 (not adjacent) -> NOT a phrase match
```

---

### Ranking: TF-IDF and BM25

Finding documents that contain your query term is step one. But if 10 million documents contain "database", you need to rank them so the most relevant ones appear first.

**TF-IDF (Term Frequency — Inverse Document Frequency)**

Two factors combined:

**Term Frequency (TF)**: how many times does the query term appear in this specific document? A document where "database" appears 50 times is probably more about databases than one where it appears once.

**Inverse Document Frequency (IDF)**: how rare is this term across all documents? Common words like "the", "is", "a" appear in nearly every document — they are useless for distinguishing relevant from irrelevant. Rare words like "Paxos" or "Gorilla" appear in very few documents — finding them is informative.

```
IDF formula (conceptual):
  IDF = log(total documents / documents containing the term)

  "the" appears in 9,999,000 of 10,000,000 documents:
    IDF = log(10M / 9.999M) = log(1.0001) ≈ 0.0001  <- almost zero, useless term

  "Paxos" appears in 200 of 10,000,000 documents:
    IDF = log(10M / 200) = log(50,000) ≈ 4.7  <- high, very discriminating term

Final TF-IDF score = TF × IDF
  Document with "Paxos" appearing 5 times: 5 × 4.7 = 23.5  <- ranked high
  Document with "the" appearing 200 times: 200 × 0.0001 = 0.02 <- ranked low
```

**BM25 (Best Match 25) — the modern improvement**

TF-IDF has a flaw: it rewards documents that repeat a term 100 times far more than documents that repeat it 5 times. But intuitively, a document is not 20x more relevant just because it uses the word 20x more.

**BM25** fixes this with two additions:

1. **Saturation**: term frequency has diminishing returns. Going from 1 occurrence to 5 is a big signal. Going from 50 to 100 is almost meaningless. BM25 applies a saturation curve so that after a certain point, additional occurrences stop boosting the score.

2. **Document length normalization**: a 10,000-word document naturally has more occurrences of every word than a 200-word document. BM25 divides by (a function of) document length so long documents are not unfairly rewarded just for being long.

```
TF-IDF vs BM25 comparison (query: "database"):

Document A: "database" appears 5 times, document length 100 words
Document B: "database" appears 50 times, document length 10,000 words

TF-IDF scores (simplified):
  Doc A: (5/100) × IDF = 0.05 × 4.5 = 0.225
  Doc B: (50/10000) × IDF = 0.005 × 4.5 = 0.0225
  -> TF-IDF ranks Doc A higher (correct)

Now consider:
Document C: "database" appears 5 times, document length 100 words  (same as A)
Document D: "database" appears 100 times, document length 100 words

TF-IDF scores:
  Doc C: (5/100) × IDF = 0.225
  Doc D: (100/100) × IDF = 4.5
  -> TF-IDF ranks Doc D 20x higher than Doc C
  -> But is a document that just repeats "database database database..."
     really 20x more relevant? No. BM25 caps this.

BM25 saturation curve:
  Occurrences: 1    5    10   20   50   100  200
  TF value:    1    5    10   20   50   100  200  <- grows linearly
  BM25 value:  0.6  1.7  2.2  2.6  2.9  3.0  3.0  <- plateaus
                                               ^^^
                                          Diminishing returns kicks in here
```

BM25 is the default ranking algorithm in **Elasticsearch**, **Apache Solr**, and most modern full-text search systems. If you are designing a search feature at any serious company, BM25 is the baseline you start from.

---

### Stemming and Lemmatization: how "running" matches "run"

Without any text processing, a user searching for "running" will not find a document that only says "run" or "ran". The search engine sees them as different strings.

**Stemming** reduces words to their root form algorithmically:

```
"running"   -> "run"
"databases" -> "databas"  <- not a real word, but consistent
"faster"    -> "faster"   (some stemmers are imperfect)
"quickly"   -> "quickli"  <- imperfect but consistent

The Porter stemmer is the classic algorithm (1980).
It applies a series of rules: remove "ing", remove "s", etc.
Fast, simple, not always linguistically correct.
```

**Lemmatization** uses a real dictionary to find the proper root form:

```
"running"   -> "run"    (dictionary: running is a form of the verb "run")
"better"    -> "good"   (dictionary: better is the comparative of "good")
"databases" -> "database" (dictionary: databases is plural of "database")
"was"       -> "be"     (dictionary: was is past tense of "be")

More accurate than stemming. Slower (requires dictionary lookup).
Used in higher-quality search systems.
```

Both approaches increase **recall** (you find more relevant documents) at a small cost to **precision** (you occasionally find false positives). For most search applications, the recall improvement is worth it.

---

### Elasticsearch and Lucene Architecture

Elasticsearch is built on top of **Apache Lucene**, the Java library that actually implements the inverted index. Understanding how Lucene organizes data on disk explains many Elasticsearch behaviors you will encounter in production.

**Segments: immutable building blocks**

```
How new documents flow through Elasticsearch:

New documents arrive
     |
     v
[In-memory buffer]
(not searchable yet)
     |
     | (refresh: default every 1 second)
     v
[Segment 1] <- new, small, searchable    <- lives on disk
[Segment 2] <- slightly older, small
[Segment 3] <- older, medium
[Segment 4] <- old, large (merged)

Search query:
  -> search ALL segments in parallel
  -> merge results from each segment
  -> return final ranked list
```

Each **segment** is an immutable mini-inverted-index. Once written, a segment is never modified. New documents go into a new segment. This immutability is what makes Lucene fast: no lock contention on writes, no need to update existing structures.

The downside: many small segments means many parallel mini-searches per query. The background **merge** process combines small segments into larger ones to keep query performance healthy.

```
Segment merge:

Before merge:
  [seg-1: 100 docs] [seg-2: 150 docs] [seg-3: 80 docs] [seg-4: 200 docs]
  -> Each query searches 4 segments, merges 4 result sets

After background merge:
  [seg-merged: 530 docs]
  -> Each query searches 1 segment

Merge trade-off:
  Merging is expensive I/O (reading and rewriting hundreds of MB)
  But it reduces ongoing query cost
  Elasticsearch manages merge scheduling automatically
```

**The refresh cycle (near-real-time, not real-time):**

When you index a document into Elasticsearch, it is NOT immediately searchable. It sits in an in-memory buffer. Every **1 second** (by default), Elasticsearch performs a **refresh**: it flushes the buffer to a new segment on disk, making those documents searchable.

This means there is up to a 1-second delay between indexing and searchability. For most applications this is fine. If you need lower latency: reduce `refresh_interval` (costs more I/O). For bulk ingestion: set `refresh_interval: -1` (disable during load), then set it back when done.

---

### When to use Elasticsearch vs other stores

**Use Elasticsearch when:**
- You need full-text search with ranking (BM25)
- You need fuzzy matching ("elasticsarch" should find "elasticsearch")
- You need faceted search (filter by category, price range, date while searching)
- You need aggregations over search results (how many results per category?)
- Multi-field search (search title, description, tags with different weights)

**Do NOT use Elasticsearch as your primary data store.** Elasticsearch does not have the same durability guarantees as a traditional database. If an Elasticsearch node crashes mid-write, you can lose recently indexed documents. Always treat ES as a **secondary index**, keeping the source of truth in a durable primary database (PostgreSQL, MySQL, DynamoDB).

```
The correct sync architecture:

Application writes                    Application reads
      |                                      |
      v                                      v
[PostgreSQL]  <- primary store        [Elasticsearch] <- search index
      |
      | (Change Data Capture via Debezium)
      v
  [Kafka]
      |
      | (Elasticsearch consumer)
      v
[Elasticsearch] <- kept in sync

If ES is unavailable: app still reads/writes PostgreSQL.
ES is eventually consistent with PostgreSQL. This is acceptable.

NEVER do this:
  Application -> writes directly to Elasticsearch only
  (if ES is down or loses data, you have no source of truth)
```

**Elasticsearch operational realities every staff engineer must know:**

1. **Mapping must be designed upfront.** In ES, "mapping" is the schema — it defines field types. If you declare a field as `text` and later want it to be `keyword`, you must reindex the entire dataset. On 100 million documents, reindex takes hours.

2. **`text` vs `keyword` types:** Use `text` for full-text search (it gets tokenized, analyzed, stemmed). Use `keyword` for exact-match filtering and sorting (it is stored as-is, case-sensitive). A product category field like "Electronics > Computers" should be `keyword`. A product description should be `text`.

3. **Text analysis must be consistent.** When you index a document, Elasticsearch runs it through an **analyzer**: tokenize, lowercase, remove stop words, stem. When you query, it runs the query through the SAME analyzer. If your index analyzer applies stemming but your query does not, "running" at query time will not match "run" in the index. They must match.

4. **High-cardinality `keyword` fields are expensive.** If you have a `keyword` field with 10 million unique values (like user IDs), Elasticsearch builds a posting list for each unique value. Memory usage explodes. Use `keyword` fields only when you actually need exact-match or aggregation on them.

---

## 3. Operational Scenarios: Putting It All Together

This section covers the scenarios that actually appear in L6 interviews and on-call incidents. For each scenario: what happened, how to diagnose it, how to fix it, and how to prevent it.

---

### Scenario 1: "Cache hit rate dropped from 80% to 5% after deployment"

**Symptom:** immediately after deploying a new version, your monitoring shows cache hit rate crashed from 80% to 5%. Database CPU and query rate spiked. Latency went up 10x. Users are not directly impacted yet but the database is at 90% capacity.

**What happened:** the new deployment changed the cache key format.

**How to diagnose:**

```
Look at the old code:
  cache_key = f"user_profile:{user_id}"

Look at the new code:
  cache_key = f"user_profile:{user_id}:{request_timestamp}"
                                        ^^^^^^^^^^^^^^^^^^^^^
                                        This was added "for debugging"
                                        Every request is now a unique key
                                        Nothing ever hits the cache
```

Every single request generates a unique key that was never cached before. The 5% hit rate comes from users who made a request before the deploy (their keys still exist in the old format, which is different from the new format — those won't hit either). Actually 5% might come from a small number of repeat requests within the same second getting the same timestamp.

**How to fix:**
1. Identify the non-deterministic component in the key (timestamp, random nonce, request ID).
2. Roll back the key format to remove it, or deploy a hotfix.
3. The cache will warm back up within minutes as requests come in and get cached.

**How to prevent:**
- Code review checklist item: "Does the cache key include any value that changes between requests for the same logical resource?" Timestamps, random IDs, session tokens, IP addresses, and nonces all disqualify a key from being reusable.
- Unit test for cache key generation: assert that calling `generate_key(user_id=123)` twice returns the same string.

---

### Scenario 2: "Users are seeing each other's private data"

**Symptom:** users report seeing another user's dashboard, another user's account settings, or another user's cart items.

**What happened:** user-specific data was cached under a generic key.

**The bug:**

```python
# Broken code:
def get_dashboard(user_id):
    cached = redis.get("dashboard")     # <- same key for ALL users!
    if cached:
        return cached
    data = db.query_dashboard(user_id)  # <- user-specific query
    redis.set("dashboard", data, ex=300)
    return data

# What this causes:
# User 123 visits first -> query runs, User 123's dashboard is cached under "dashboard"
# User 456 visits next  -> cache hit! User 123's dashboard is returned to User 456.
```

**How to fix immediately:**
1. Delete the poisoned cache key: `redis.del("dashboard")`
2. Deploy the fixed code: `cache_key = f"dashboard:user:{user_id}"`
3. Assess privacy impact: how long was the bug running? How many users were affected?

**The correct key:**
```python
# Fixed code:
def get_dashboard(user_id):
    cache_key = f"dashboard:user:{user_id}"  # <- user-specific key
    cached = redis.get(cache_key)
    if cached:
        return cached
    data = db.query_dashboard(user_id)
    redis.set(cache_key, data, ex=300)
    return data
```

**Rule:** every dimension that changes the response must appear in the cache key. For user-specific data: include user_id. For locale-specific data: include locale. For A/B test variants: include variant ID. If you are unsure, err on the side of making keys more specific.

---

### Scenario 3: "Redis lost all data when the pod restarted"

**Symptom:** after a routine Kubernetes pod restart (rolling deployment, node drain, OOM kill), all user sessions are invalidated. Every user is logged out. Session-based rate limits are reset. Shopping carts are empty.

**What happened:** Redis was deployed without persistence.

```
Redis default behavior:
  Data lives in RAM only.
  Pod restarts = new empty Redis = all data gone.

Redis INFO persistence output (the problem):
  rdb_last_bgsave_status:ok
  aof_enabled:0            <- AOF disabled!
  rdb_bgsave_in_progress:0

After restart:
  [empty Redis] <- all sessions lost
  User A: "please log in again"
  User B: "please log in again"
  User C: "why is my cart empty?"
```

**How to fix:**

For sessions (can tolerate up to 1 second of data loss):
```
Enable AOF with everysec:
  appendonly yes
  appendfsync everysec

On restart: Redis replays the AOF log, recovering all data written more than 1 second ago.
Overhead: ~5-10% write performance cost. Worth it for production sessions.
```

For higher durability needs (rate limiters, idempotency keys):
```
Hybrid persistence:
  save 900 1      <- RDB snapshot if 1 write in 15 minutes
  save 300 10     <- RDB snapshot if 10 writes in 5 minutes
  appendonly yes  <- also keep AOF

On restart: load from RDB (fast), then replay AOF log from the point after the RDB snapshot.
Best of both worlds: fast startup + minimal data loss.
```

**Prevention:** never deploy Redis to production without an explicit persistence decision in your configuration. Make "persistence = none" a deliberate, documented choice (e.g., for a pure L1 cache where all data is in a backing DB anyway), not an accidental default.

---

### Scenario 4: "MGET fails with CROSSSLOT error in Redis Cluster"

**Symptom:** your application uses Redis Cluster for horizontal scaling. After migrating from standalone Redis, you start seeing errors: `CROSSSLOT Keys in request don't hash to the same slot`.

**What happened:** Redis Cluster distributes keys across 16,384 hash slots. Keys that fall into different slots live on different nodes. Multi-key commands (`MGET`, `MSET`, `DEL key1 key2`, `pipeline`) require all keys to live on the same node.

```
Redis Cluster key distribution:

Key: "user:123:profile"  -> hash -> slot 8292 -> Node A
Key: "user:123:settings" -> hash -> slot 5461 -> Node B
Key: "user:123:cart"     -> hash -> slot 11000 -> Node C

MGET user:123:profile user:123:settings user:123:cart
  -> ERROR: CrossSlot - keys are on different nodes!
  -> Redis does not do cross-node operations
```

**How to fix:** use **hash tags** — a portion of the key surrounded by `{}` that Redis uses as the ONLY input to the hash function.

```
Without hash tags (each key hashes its entire string):
  "user:123:profile"  -> hash("user:123:profile")  -> slot 8292
  "user:123:settings" -> hash("user:123:settings") -> slot 5461

With hash tags (only the portion inside {} is hashed):
  "{user:123}:profile"  -> hash("user:123") -> slot 6257
  "{user:123}:settings" -> hash("user:123") -> slot 6257  <- SAME SLOT!
  "{user:123}:cart"     -> hash("user:123") -> slot 6257  <- SAME SLOT!

MGET {user:123}:profile {user:123}:settings {user:123}:cart
  -> All keys on the same node -> Works!
```

**Caution:** if you put the same hash tag on all keys (e.g., `{app}:user:123`, `{app}:session:456`), all keys will land on the same slot and you have effectively bypassed all cluster distribution. Use hash tags to group related keys that need multi-key operations, not to group everything.

---

### Scenario 5: "p99 latency spikes to 3 seconds every 5 minutes, exactly"

**Symptom:** your service has stable p99 latency of 15ms most of the time. But exactly every 5 minutes, for about 2–3 seconds, latency spikes to 3,000ms. The pattern is perfectly regular.

**What happened:** Redis background saves (`BGSAVE`) are causing multi-second latency spikes.

```
BGSAVE mechanics:
  Redis calls fork() to create a child process.
  Child process writes the RDB snapshot to disk.
  Parent process continues serving requests.

The problem is fork() itself:
  On Linux, fork() copies the page table (the OS structure mapping virtual to physical memory).
  For a 60 GB Redis instance, the page table is huge.
  fork() pauses the parent process while copying it.

  On 60 GB Redis: fork() takes 2-3 seconds
  During those 2-3 seconds: Redis parent is frozen, no requests served
  All client connections time out or queue up
  -> p99 latency = 2-3 seconds

Timeline:
  T+0:00  BGSAVE triggered (every 5 minutes by config)
  T+0:00  fork() starts, Redis freezes
  T+0:02  fork() completes, Redis resumes
  T+0:02  All queued requests served (latency spike)
  T+4:58  All quiet
  T+5:00  Next BGSAVE triggered -> repeat
```

**How to diagnose:**
```
redis-cli INFO persistence
  -> latest_fork_usec: 2,400,000  <- 2.4 seconds! (2,400,000 microseconds)

Alert threshold: latest_fork_usec > 1,000,000 (1 second)
```

**How to fix:**

Option 1: Shard the Redis instance.
```
Instead of one 60 GB Redis:
  -> Six 10 GB Redis instances (application hashes keys across them)

Fork time for 10 GB: ~350ms (well under 1 second)
No more multi-second freezes.
```

Option 2: Schedule BGSAVE during low-traffic windows.
```
redis.conf:
  save 14400 1   <- only save if 1 write in 4 hours (instead of every 5 minutes)
  
Or: disable scheduled BGSAVE, do manual BGSAVE at 3am from a cronjob.
```

Option 3: Switch to AOF only, disable RDB.
```
appendonly yes
save ""           <- disables RDB snapshots entirely

AOF writes are incremental (append one command at a time).
No fork() for large snapshots. No multi-second freezes.
Trade-off: AOF log can grow large; needs periodic AOF rewrite (also uses fork, but rarer).
```

---

### Scenario 6: "Metrics table in PostgreSQL is 5 TB and queries are timing out"

**Symptom:** your infrastructure team stored 2 years of IoT sensor data in PostgreSQL. The table is now 5 TB. Dashboard queries that used to take 200ms now time out after 30 seconds. `pg_stat_activity` shows dozens of slow queries piled up. The database server is at 100% I/O.

**What happened:** time-series data in a general-purpose relational database hit its scaling wall.

```
Back of the envelope:
  10,000 IoT sensors × 86,400 readings/day × 730 days (2 years) = 630 billion rows
  At ~8 bytes/row: 5 TB raw (matches the observation)

Why queries are slow:
  Query: "average temperature per sensor for the last 7 days"
  -> Must scan rows from 7 days ago to now
  -> Even with an index on (sensor_id, recorded_at): 10,000 sensors × 604,800 rows/week
  -> Must read ~6 billion rows for just one week of data
  -> B-Tree traversal across 5 TB = massive I/O
  -> VACUUM can't keep up with writes -> table bloat -> even more I/O

PostgreSQL is doing the best it can. The data model is the problem.
```

**Migration plan:**

**Option A: TimescaleDB (least disruptive)**
```sql
-- 1. Install TimescaleDB extension (same PostgreSQL server)
CREATE EXTENSION timescaledb;

-- 2. Convert existing table to hypertable (automatic time partitioning)
SELECT create_hypertable('metrics', 'recorded_at',
  chunk_time_interval => INTERVAL '1 day',
  migrate_data => true  -- moves existing data into partitions
);
-- This runs in background, table remains available during migration

-- 3. Enable compression on old chunks
ALTER TABLE metrics SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'sensor_id',
  timescaledb.compress_orderby = 'recorded_at DESC'
);

SELECT add_compression_policy('metrics',
  compress_after => INTERVAL '7 days');  -- compress chunks older than 7 days

-- 4. Add downsampling policy
SELECT add_continuous_aggregate_policy('metrics_hourly',
  start_offset => INTERVAL '7 days',
  end_offset => INTERVAL '1 hour',
  schedule_interval => INTERVAL '1 hour');
```

Benefits: keep all existing SQL queries, same connection strings, same ORM code. Just add the extension and migration runs in the background.

**Option B: InfluxDB (better long-term for pure time-series)**
```
Migration steps:
1. Stand up InfluxDB cluster
2. Rewrite ingest service to write to InfluxDB instead of PostgreSQL
3. Backfill historical data (export from PG, import to InfluxDB)
4. Migrate dashboard queries to InfluxQL or Flux query language
5. Decommission metrics table in PostgreSQL

Time: 2-4 weeks engineering effort
Benefit: purpose-built for this workload, better compression, built-in downsampling
Cost: migration effort, team must learn new query language
```

**Downsampling plan after migration:**
```
Policy: for data older than 7 days, aggregate to 1-minute resolution.
        for data older than 90 days, aggregate to 1-hour resolution.
        for data older than 1 year, aggregate to 1-day resolution.

Effect on existing 5 TB:
  Rows older than 7 days (99.7% of data) compressed to 1-minute:
    630 billion rows -> 630 billion / 60 = 10.5 billion rows
  Rows older than 90 days compressed to 1-hour:
    10.5 billion -> 10.5 billion / 60 = 175 million rows
  Rows older than 1 year compressed to 1-day:
    175 million / 24 = 7.3 million rows

  Final: ~20 million total rows (down from 630 billion)
  Storage: from 5 TB to ~2 GB
  Query latency: from 30-second timeouts to sub-second
```

---

## 4. Cross-Topic Integration: How Cache Internals Connect

### Key design -> hit rate -> database load

Cache key design is not an aesthetic choice. It directly determines how much load your database sees. The math makes this concrete:

```
Scenario: service receives 100,000 requests per second

Case A: good key design (90% cache hit rate)
  Cache hits:  90,000 req/sec  <- served from Redis, ~0.5ms latency
  Cache misses: 10,000 req/sec  <- must query database
  Database load: 10,000 QPS

Case B: bad key design (5% cache hit rate, e.g., timestamp in key)
  Cache hits:   5,000 req/sec
  Cache misses: 95,000 req/sec  <- must query database
  Database load: 95,000 QPS

  Your database needs to be designed for 95K QPS, not 10K QPS.
  That is a 9.5x difference in required database capacity.
  At $0.50/hour per DB replica: Case B costs $4.75/hour more in replicas alone.

The formula:
  DB load = Total QPS × (1 - hit rate)
  
  At 100K QPS:
    hit rate 0.99 -> DB load = 1,000 QPS   (1 replica handles it)
    hit rate 0.90 -> DB load = 10,000 QPS  (2-3 replicas)
    hit rate 0.50 -> DB load = 50,000 QPS  (10+ replicas)
    hit rate 0.05 -> DB load = 95,000 QPS  (20+ replicas, or database overloads)
```

This is why key design belongs in the design review, not as an implementation detail.

---

### Persistence choice -> high availability architecture decisions

The persistence configuration you choose for Redis determines your entire HA strategy:

```
No persistence (cache-only mode):
  Redis is a pure L2 cache.
  All data exists in the backing database.
  Pod restart -> Redis empty -> warm-up period (all requests hit DB until cache fills)
  HA decision: can restart any Redis node freely; no replica needed for data safety
  Use for: computed results, rendered pages, DB query results

AOF + everysec (session store mode):
  Redis survives pod restarts with at most 1 second of data loss.
  Sessions, rate limiters, idempotency keys survive deploys.
  HA decision: need at least one replica (Redis Sentinel or Cluster) for failover
  If primary fails, replica is promoted; AOF replicated to replica means near-zero data loss
  Use for: user sessions, rate limiting, distributed locks with short leases

Hybrid (RDB + AOF):
  Fastest restart (load RDB, then replay AOF since RDB)
  Best durability short of Redis Enterprise with sync replication
  HA decision: Sentinel or Cluster with at least 2 replicas
  Use for: anything where data loss is unacceptable (billing, payments should use a real DB though)
```

---

### Redis Cluster constraints -> application design requirements

Redis Cluster gives you horizontal write scaling, but it imposes constraints that must be designed for before deployment:

```
Constraint 1: Multi-key operations require hash tags.
  Impact: key naming conventions must be established team-wide.
  Design decision: define hash tag schemas in your architecture document.
  Example: all keys for a user group by {user:<id}>, all keys for an order by {order:<id>}

Constraint 2: No KEYS * command.
  KEYS * scans all keys on one node (and is O(N) blocking).
  In Cluster: even if you send KEYS * to every node, you get a partial picture.
  Use SCAN instead: cursor-based, non-blocking, works per-node.
  Design decision: if your application needs to enumerate keys, redesign to
  either keep a separate index (a Redis Set) or use a naming convention + SCAN.

Constraint 3: Lua scripts must only reference keys in the same slot.
  Lua scripts run atomically on a single Redis node.
  If your script references keys that might be on different nodes, it will fail.
  Design decision: if you use Lua scripts (for atomic multi-key operations like
  rate limiting), ensure all keys used in the script share a hash tag.

Constraint 4: Pipeline operations require same-slot keys.
  Pipelines batch multiple commands to reduce round-trips.
  In Cluster, pipelining only works within a single node's key space.
  Design decision: if performance requires pipelining, group related keys
  with hash tags so they land on the same node.

These constraints must be identified BEFORE deployment.
Retrofitting hash tags into a system with millions of existing keys
requires a coordinated migration (rename all keys, update all application code).
Far more expensive to fix later than to design for upfront.
```

---

### When to replace Redis with a specialized store

Redis is excellent at what it does: in-memory key-value operations with optional persistence, Pub/Sub, sorted sets, and streams. But it is not the right tool for every problem. Staff engineers recognize when to reach for something more specialized.

| What you are storing | Better specialized option | Why Redis falls short |
|---------------------|--------------------------|----------------------|
| 1-second IoT metrics for 2+ years | TimescaleDB or InfluxDB | Redis has no time partitioning, no downsampling, no columnar compression; memory cost is prohibitive at scale |
| Full-text product search | Elasticsearch or OpenSearch | Redis has no BM25 ranking, no stemming, no phrase search, no faceted aggregations |
| Graph relationships and traversals | Neo4j or AWS Neptune | Redis has no native graph traversal; simulating it with sorted sets is painful and slow |
| Geospatial range queries at scale | PostgreSQL + PostGIS | Redis GEO works for simple proximity queries but lacks the polygon, routing, and complex spatial operations of PostGIS |
| Sequential transaction log (Kafka replacement) | Apache Kafka or AWS Kinesis | Redis Streams lack Kafka's consumer group durability guarantees and multi-datacenter replication |
| Simple K-V lookups, sessions, rate limiting | Redis (stay here) | Redis is best-in-class for this; replacing it with something heavier is over-engineering |

The guiding question: **what does this data structure need to do, and is Redis's data model the natural fit?** If you are fighting Redis to make it do something (simulating a time-series with sorted sets, building a text search on top of KEYS pattern matching), that friction is a signal to use the right tool.

```
Decision flowchart:

Data arrives -> Is it primarily time-ordered metrics?
                  YES -> Is write rate > 5K/sec or retention > 90 days?
                           YES -> Time-series DB (Prometheus/InfluxDB/TimescaleDB)
                           NO  -> PostgreSQL with a good index
                  NO  -> Does it need full-text search with ranking?
                           YES -> Elasticsearch
                           NO  -> Is it graph-structured (nodes + edges)?
                                    YES -> Neo4j / graph DB
                                    NO  -> Is it session / cache / rate-limit?
                                             YES -> Redis
                                             NO  -> PostgreSQL / your primary DB
```

---

### Putting it all together: the staff engineer mental model

At the L6 level, interviewers are not checking whether you know the commands. They are checking whether you understand the **why** behind each tool's design, and whether you can reason about failure modes before they happen.

The mental model:

```
For any data storage decision, ask four questions:

1. WRITE PATTERN: How fast does data arrive? Is it appended, updated, or deleted?
   -> High append rate + time-ordered = time-series DB
   -> High write + random access = Redis / Cassandra
   -> Mixed transactional = PostgreSQL / MySQL

2. READ PATTERN: What queries does this data need to support?
   -> "Give me all data between time A and time B" = time-series DB
   -> "Find documents containing these words, ranked by relevance" = Elasticsearch
   -> "Fetch by exact key in < 1ms" = Redis
   -> "Join with other tables" = relational DB

3. SCALE: What is the data volume and query rate?
   -> Millions of metric points per second = purpose-built TSDB
   -> Billions of documents, text search = ES cluster
   -> <1ms latency, millions of req/sec = Redis

4. DURABILITY vs SPEED: What is the cost of losing data?
   -> Sessions: tolerable to lose last 1 second = AOF everysec
   -> Billing: zero data loss = primary database, not Redis
   -> Pure cache: fine to lose everything = no persistence
```

Every system you design at the staff level will involve at least three of these layers simultaneously: a durable primary store, a search index, a cache, and possibly a time-series store for operational metrics. Knowing where each layer starts and ends — and what happens when they fall out of sync — is the core of staff-level distributed systems design.

---

*End of Chapter 32 — Part B*
# Chapter 32: Redis and Cache Internals — Part C
## L6 Calibration, Production Incidents, and Interview Mastery

---

## Section 1: L5 vs L6 Calibration Table

The gap between L5 and L6 is not knowing more facts. It is reasoning from first principles, anticipating second-order failures, and proposing solutions that hold under production conditions.

| # | Dimension | L5 Answer | L6 Answer |
|---|-----------|-----------|-----------|
| 1 | **Low cache hit rate diagnosis** | "Maybe the TTL is too short. Increase it." | "First instrument: run `INFO stats` for `keyspace_hits` and `keyspace_misses`. Then sample the keyspace with `SCAN` and inspect key patterns. Low hit rate has three causes: (a) cache keys are non-deterministic (timestamps, request IDs baked in), (b) TTL is shorter than the request interval so the cache expires before the next read, (c) the cache was just flushed or a new deploy introduced a new key format without a warm-up period. I'd start with key pattern analysis because a key bug causes 0% hit rate instantly and the deployment timeline usually confirms it." |
| 2 | **Redis data loss after restart** | "Enable AOF persistence." | "It depends on the RPO. AOF with `appendfsync always` guarantees zero data loss but costs one fsync per write command — throughput drops to ~10K ops/sec. `appendfsync everysec` loses up to 1 second of writes and handles ~100K ops/sec. For most workloads I'd use hybrid persistence: RDB + AOF delta. RDB gives a clean snapshot for fast recovery; AOF covers the delta since the last snapshot. Restart time is bounded by the RDB load time, not by replaying years of AOF commands. I'd also verify at startup that the persistence config matches what the app expects — a missing config flag is the #1 cause of surprise data loss." |
| 3 | **Slow cache performance** | "Add more memory or upgrade the instance." | "I triage in layers. First, `INFO commandstats` to find which commands are slow. Second, `SLOWLOG GET 25` to inspect actual slow commands. Third, check `INFO memory` for `mem_fragmentation_ratio` — above 1.5 means fragmentation is eating memory efficiency. Fourth, check for large keys with `DEBUG OBJECT <key>` — a single SMEMBERS on a 2M-member set blocks the event loop. Fifth, check if BGSAVE is running: fork on a 50GB dataset takes 2–5 seconds and causes p99 latency spikes every time it runs. The fix depends on root cause: hot key sharding, key size reduction, or adjusting BGSAVE schedule." |
| 4 | **Cache poisoning response** | "Flush the cache and let it rebuild." | "Flushing all at once causes a thundering herd — every request misses simultaneously and hammers the database. Instead: (1) identify the exact bad key pattern from logs or by inspecting recent write paths, (2) DEL the specific bad keys or use a targeted SCAN + DEL with a matching pattern, (3) if the blast radius is a whole shard and pattern is unclear, rotate one shard at a time with a 30-second window between shards, keeping the rest serving stale-but-present data. Root cause: the write path cached without validating the response (e.g., cached a 500 error). Add a validation gate: only cache if `status == 200 and body is not None`." |
| 5 | **Redis Cluster CROSSSLOT error** | "You can't do multi-key operations in Redis Cluster." | "CROSSSLOT happens when keys in the same command hash to different slots. Redis Cluster routes each key to a slot using CRC16(key) mod 16384, and a single command cannot span nodes. The fix is hash tags: `{user:123}:session` and `{user:123}:requests` both use `user:123` as the hash tag (the part inside `{}`), so they land on the same slot and the same node. Multi-key commands, MULTI/EXEC transactions, and Lua scripts all work as long as all keys share the same hash tag. Migration path: dual-write both old and new key formats for one TTL cycle, then cut reads over to the new format." |
| 6 | **Fork latency spikes (BGSAVE)** | "Disable BGSAVE or increase the interval." | "BGSAVE calls `fork()`, which on Linux uses copy-on-write. The fork itself is O(number of memory pages in page table) — for a 50GB Redis instance this takes 2–5 seconds because the OS must copy the page table even though no pages are copied yet. During those 2–5 seconds, the main thread is blocked. Options: (1) reduce dataset size — shard data across more Redis instances so each instance holds less; (2) use huge pages disabled — transparent huge pages increase fork time significantly, disable with `echo never > /sys/kernel/mm/transparent_hugepage/enabled`; (3) schedule BGSAVE during known low-traffic windows; (4) switch to AOF-only if snapshots aren't needed. I'd start with disabling transparent huge pages — it's a 1-line OS change that often halves fork time." |
| 7 | **Multi-key operations in Redis Cluster** | "Use a pipeline." | "Pipelining does not solve CROSSSLOT — it batches commands but each command still executes on its designated node, and a single command like MGET still requires all keys on the same node. The correct approaches are: (a) hash tags to co-locate related keys, (b) client-side fan-out for truly independent keys (split MGET into per-node batches in the client, then merge results), or (c) use a Lua script that runs entirely on one node (Lua scripts require all keys to be on the same slot). For session data — user profile, cart, preferences — hash tags on `{user_id}` is the clean solution." |
| 8 | **Choosing persistence mode** | "Use AOF for safety, RDB for performance." | "The question is: what is the RPO, and what is the RTO? RDB: RPO = time since last snapshot (up to hours), RTO = fast (just load the file). AOF-only: RPO = 1 second with `everysec`, RTO = slow for large AOF files (replaying 200GB of commands takes 45+ minutes). Hybrid: RPO = 1 second (AOF covers the delta since last RDB), RTO = fast (load RDB first, then replay only the delta). For production I default to hybrid. Exception: ephemeral caches where data loss is acceptable — disable persistence entirely and get maximum write throughput. Exception 2: financial counters or session stores that must survive restarts — hybrid with `everysec`." |
| 9 | **Time-series workload at 10K writes/sec** | "Use a time-series database like InfluxDB." | "At 10K writes/sec the concern is write amplification and index overhead. PostgreSQL's B-tree index on a timestamp column must update for every insert, causing write amplification and constant VACUUM pressure. Three paths: (a) TimescaleDB — PostgreSQL extension, hypertables auto-partition by time (7-day chunks), same SQL, near-zero app code change, 10x better compression with columnar compression on old chunks; (b) InfluxDB — purpose-built, Gorilla compression (12 bytes/point → 1-2 bytes), excellent for single-metric queries but weaker for relational joins; (c) Redis time-series (RedisTimeSeries module) — fast ingestion, limited retention. My default at 10K writes/sec with SQL query needs: TimescaleDB. Above 100K writes/sec: InfluxDB or VictoriaMetrics." |
| 10 | **Adding full-text search to an app** | "Use Elasticsearch or add a LIKE query." | "LIKE '%term%' in PostgreSQL requires a full table scan — it cannot use a B-tree index. Options: (a) PostgreSQL full-text search with `tsvector` / `tsquery` — works well up to ~10M rows, no new infrastructure, GIN index makes it fast; (b) Elasticsearch — better ranking (BM25), more featureful (autocomplete, fuzzy match, aggregations), but introduces a sync pipeline with failure modes; (c) Typesense or Meilisearch — simpler ops than ES, good for product search. Key principle: never use ES as the primary store. PostgreSQL owns the data; ES is a search index populated via CDC (Change Data Capture). The sync lag is typically 1-5 seconds via Debezium → Kafka → ES consumer." |
| 11 | **Redis Sentinel vs Redis Cluster choice** | "Use Cluster for large data, Sentinel for smaller data." | "Sentinel provides high availability for a single primary-replica setup — it monitors the primary, promotes a replica on failure. It does not provide horizontal scaling. Cluster shards data across multiple primaries, giving both HA and horizontal scale. Choose Sentinel when: dataset fits on one machine (<50GB typical), you need simpler operations, or your client library has poor Cluster support. Choose Cluster when: dataset exceeds single-node memory, write throughput exceeds single-node capacity, or you need to scale horizontally. Gotcha: Cluster breaks multi-key operations without hash tags and breaks Lua scripts that span slots. Migration from Sentinel to Cluster is non-trivial — plan for it up front if scale is expected." |
| 12 | **Cache key design for multi-tenant SaaS** | "Prefix keys with the tenant ID." | "Yes, but the devil is in the details. The key must be `{tenant_id}:{resource_type}:{resource_id}:{variant_dimensions}`. The vulnerability with just `resource_type:resource_id` is cross-tenant data leakage — two tenants with the same internal record ID share a cache entry. Beyond correctness: (a) tenant isolation also means per-tenant TTL policies (a free-tier tenant might get shorter TTLs or a smaller cache quota), (b) in Redis Cluster, including tenant_id in the hash tag ensures all keys for a tenant land on the same shard (useful for atomic operations per tenant), (c) cache eviction: LRU evicts globally, which means a noisy tenant can evict keys for quiet tenants — consider separate Redis instances per tier (enterprise vs free) or namespaced eviction policies." |

---

## Section 2: Production Incidents

### Incident 1: Twitter's Cache Key Timestamp Bug — 0% Hit Rate

**Scenario.** A developer adds `?timestamp=<epoch_ms>` to cache-busted API requests during debugging — a common trick to bypass the cache during development. The code ships to production without removing the timestamp parameter. The cache key generation function hashes the full request URL including query parameters.

**Blast radius.** Every single request generates a unique cache key. Cache hit rate drops from 85% to 0% instantaneously at deploy time. The database, previously handling 15% of traffic (the natural misses), now handles 100%. Database CPU climbs from 20% to 100%. Connection pool exhausts. Response latency climbs from 80ms to 12 seconds. Cascading timeout failures across dependent services. 300M users experience degraded or unavailable service for 4 hours.

**Detection.** Monitoring shows cache hit rate → 0% and DB CPU → 100% simultaneously at deploy time. The correlation is immediate in hindsight but the on-call engineer initially investigates the database directly.

**Root cause.** The timestamp parameter is a non-deterministic cache key dimension. Two requests for the same logical resource — same user, same product, same data — generate different keys because millisecond timestamps differ. Cache always misses. Every miss writes a unique entry that is never read again, so the cache fills with one-time-use entries and evicts legitimate entries.

**Immediate fix.** Roll back the deployment. Cache key returns to deterministic format. Over the next 30 minutes, the cache warms up organically as traffic hits the database and each result is stored. Hit rate recovers to 85%.

**Prevention.** Two controls: (1) CI lint rule that fails the build if cache key construction logic contains calls to `time.now()`, `datetime.now()`, UUID generation, or random number functions; (2) code review checklist item: "Does this cache key produce the same value for logically equivalent requests?" The first control catches it mechanically; the second catches it conceptually.

**L6 takeaway.** A 0% hit rate at a specific deploy time with a simultaneous database CPU spike is almost always a cache key bug introduced in that deploy. The first question is: what changed in the key generation logic?

---

### Incident 2: Session Loss During Redis Upgrade — Pinterest 2019

**Scenario.** The infrastructure team performs a rolling restart of the Redis cluster to upgrade the Redis version. The upgrade procedure: drain one pod, restart it, verify it joins the cluster, proceed to the next pod. Standard procedure. What the team does not verify: the Redis pods were deployed six months ago from a configuration template that did not include persistence settings. Redis defaults to no persistence.

**Blast radius.** Each pod restart flushes all sessions stored on that pod. Because the cluster uses consistent hashing, approximately 1/N of all sessions live on each pod (N = number of pods). As the rolling restart proceeds across all pods over 4 hours, every session in the cluster is destroyed at least once. 20 million users are randomly logged out. The randomness (different users at different times) makes it harder to detect as a systemic issue — it looks like intermittent session bugs rather than a full cache wipe.

**Detection.** Customer support tickets spike within 20 minutes of the first pod restart. Search term: "being randomly logged out." On-call engineer initially suspects a session expiry bug in the application. The pattern — support ticket volume correlating exactly with pod restart times — takes 90 minutes to identify.

**Fix.** Three-layer response:
- **Immediate:** Stop the rolling restart. Enable AOF persistence (`CONFIG SET appendonly yes`) on all remaining pods without restart. This is a live config change — Redis accepts it while running.
- **Medium-term:** Add a startup readiness check that verifies persistence is enabled before the pod accepts connections. If `appendonly no` and `save ""` are both set (no persistence), the pod refuses to join the cluster and alerts the operator.
- **Long-term:** Infrastructure-as-code template for Redis always includes explicit persistence configuration. The absence of a persistence config line is treated as a linting error, not a valid default.

**L6 takeaway.** Redis defaults are optimized for simplicity, not production safety. Persistence is off by default. Cluster auth is off by default. Max memory eviction policy is `noeviction` by default (returns errors instead of evicting). Always explicitly configure production Redis — never rely on defaults.

---

### Incident 3: Cache Poisoning via Error Response — DoorDash 2020

**Scenario.** The restaurant menu service caches API responses from a downstream menu data service. The caching logic is simple: make the request, store the response, return the cached response on future requests. The validation logic is: none.

A database replication event causes the replica (which serves read traffic) to fall behind the master by 3 minutes. During this window, the replica returns HTTP 500 for restaurant menu requests (the query times out against the lagging replica). The master would return correct data but the read path is pinned to the replica.

The caching layer receives the 500 error response, does not check the status code, and caches it with a 5-minute TTL.

**Blast radius.** Every restaurant menu page now returns a cached "menu unavailable" error for 5 minutes — not because the backend is still failing (replication catches up within 3 minutes), but because the cache is now serving the stored error. Approximately $200K in lost orders during the 5-minute window.

**Root cause.** Missing validation gate before the cache write. The fix is one conditional:
```
if response.status_code == 200 and response.body is not None:
    cache.set(key, response.body, ttl=300)
```

**Fix.** Deploy the validation gate. Cache TTLs expire naturally — maximum 5 minutes, no manual flush needed. Service recovers without intervention once the new code is deployed.

**Prevention.** (1) Never cache non-2xx responses. (2) In staging, run a test scenario that returns 500 errors from dependencies and verifies the cache does not store them. (3) Add a metric: `cache_writes_with_error_status` — this should be zero in production. Alert if it is not.

**L6 takeaway.** Cache poisoning via error responses is insidious because the system appears to recover (the backend error resolves) but users continue experiencing the error until the TTL expires. The window is bounded by TTL, which is why short TTLs (under 5 minutes) for health-sensitive data matter.

---

### Incident 4: CROSSSLOT Error After Redis Cluster Migration — Netflix 2021

**Scenario.** Netflix migrates its session validation service from a single Redis instance (primary-replica with Sentinel) to Redis Cluster for horizontal scalability. The migration is planned carefully: data migrated, clients updated, slot map distributed. The application code is not changed — it is assumed to be compatible.

The session validation service uses MULTI/EXEC transactions to atomically validate and rate-limit requests:
```
MULTI
SET user:123:session <token> EX 3600
INCR user:123:requests
EXEC
```

On the single Redis instance, this works perfectly. On Redis Cluster: `user:123:session` hashes to slot 8854 (node A); `user:123:requests` hashes to slot 14781 (node B). Redis Cluster returns `CROSSSLOT Keys in request don't hash to the same slot`. The EXEC fails. Every session validation transaction fails.

**Blast radius.** Auth service is effectively down. All users attempting to authenticate receive errors. All existing sessions cannot be validated. Effectively a full auth outage.

**Root cause.** Multi-key operations in Redis Cluster require all keys to hash to the same slot. The application assumed single-Redis semantics would carry over to Cluster.

**Fix.** Migrate keys to use hash tags:
```
MULTI
SET {user:123}:session <token> EX 3600
INCR {user:123}:requests
EXEC
```

Both keys now hash on `user:123` (the content of `{}`), landing on the same slot. The transaction succeeds. Migration: dual-write both key formats for one TTL cycle (1 hour), then cut reads to the new format.

**Prevention.** Redis Cluster compatibility testing must be a mandatory pre-migration gate. Run the full application against a Cluster in staging. MULTI/EXEC transactions, Lua scripts, and MGET/MSET commands are the most common failure points. A grep for these patterns in code, flagged for Cluster compatibility review, would have caught this before production.

---

### Incident 5: Metrics Overload — Datadog-Inspired PostgreSQL Migration

**Scenario.** An internal monitoring team stores 500K metric time series in PostgreSQL. Each metric sends one reading every 5 seconds. At steady state: 100K writes/sec. This was fine at 10K metrics (2K writes/sec) when the system was designed. Over 18 months, the monitored fleet grew 50x.

**Symptoms.** Insert latency climbs from 5ms to 2,000ms over 6 weeks. Dashboard queries for "last 24 hours of CPU usage for host X" take 45 seconds. PostgreSQL VACUUM runs continuously and still falls behind. Replication lag grows to 30 minutes. Engineers keep adding read replicas, which helps query performance temporarily but does nothing for insert latency.

**Root cause.** 500K metrics × 86,400 seconds/day ÷ 5 seconds per reading = 8.64 billion rows/day. The `timestamp` column has a B-tree index to support range queries. Every insert must update this index. At 8.64B rows/day, the index becomes enormous and must be partially loaded from disk on every insert — this is the primary write amplification source. VACUUM struggles because rows are being inserted faster than dead tuple cleanup can run.

**Fix.** Migrate to TimescaleDB.

TimescaleDB is a PostgreSQL extension — the same SQL, same connection strings, no application code changes. It introduces hypertables: logical tables backed by time-partitioned physical chunks (configured at 7-day intervals). Each chunk is a separate physical table with its own index. A B-tree index on a 7-day chunk is small enough to stay in memory. Insert performance is determined by the current chunk only, not the full 3-year dataset.

Additional: enable columnar compression on chunks older than 7 days. Time-series data compresses at 10x ratios because adjacent readings are correlated. Compression reduces disk from 15TB to ~1.5TB.

Results: insert latency returns to 2ms. 24-hour range query returns to 3 seconds. VACUUM pressure disappears (compressed chunks are immutable — no VACUUM needed). Replication lag returns to zero.

**Migration timeline.** 18 months of historical data (10 billion rows) migrated in 3 weeks using parallel monthly batches. Dual-write maintained throughout: new data written to both PostgreSQL and TimescaleDB. Reads cut over after validation (COUNT and checksum comparison per daily partition).

**L6 takeaway.** The failure mode here is design debt. At 2K writes/sec, PostgreSQL is fine. At 100K writes/sec with unbounded retention, it is not. The signal that you've outgrown PostgreSQL for time-series: VACUUM can't keep up, index size exceeds available RAM, insert latency is growing week over week. The correct intervention is to recognize this at the design phase: if the write rate is expected to grow with fleet size and fleet size is expected to grow, build in the TimescaleDB path from the start.

---

## Section 3: Cross-Topic Brainstorming Questions

### Theme A: Cache Key Design

**Question 1.** You're caching product recommendations for a user. The recommendations change based on: `user_id`, `country`, `experiment_group` (A/B test), and `time_of_day` (morning vs evening). Design the cache key and explain what happens to hit rate if you include each dimension. What if you add a real-time "trending" component?

Consider: each dimension you add reduces the probability that two requests share a key. `user_id` alone: one key per user (high hit rate if users return frequently). Adding `country`: fine, users don't change countries. Adding `experiment_group`: fine, stable per user. Adding `time_of_day` as a binary (morning/evening): divides the keyspace in two — acceptable. Adding `time_of_day` as a raw hour (0-23): divides keyspace by 24 — hit rate drops sharply. Adding a real-time "trending" component that changes every few minutes: effectively makes every request a miss unless you separate the trending component into its own cache entry and merge at read time. What is the correct architecture for the trending component?

**Question 2.** Your multi-tenant SaaS product has a bug: two tenants share user ID 12345. The current cache key is `user:12345:profile`. Tenant 1's data is returned to Tenant 2. You've been running this code for 6 months. What's the vulnerability? Design the correct key. How do you migrate from the bad key to the good key without a full cache flush (which would cause a thundering herd)?

Think through: which tenants are affected? How do you identify the blast radius? What is the migration sequence (write new key format, deprecate old format, set a sunset TTL on old keys)? What is the monitoring signal that tells you migration is complete?

**Question 3.** You're caching paginated search results: "results for 'redis', page 2, sorted by relevance." A new document matching 'redis' is indexed. The cached page 2 is now wrong — it may be missing the new document or have incorrect pagination offsets. How do you design the cache key and invalidation strategy? Is TTL-based or event-driven invalidation better here?

Consider: event-driven invalidation requires knowing which cached queries are affected by a new document — this is the inverse index problem. TTL is simpler but trades freshness for correctness. What TTL is acceptable for search results? How does this change for an internal tool vs a customer-facing product?

**Question 4.** Your e-commerce platform caches product prices with a 5-minute TTL. The product manager wants price updates reflected within 5 seconds of an admin change. What are the options? Design a cache invalidation strategy that achieves <5-second update latency without causing thundering herd on every price change.

Consider: write-through cache (update cache on every price write), event-driven invalidation (delete the key when price changes, next read rebuilds), short TTL (5-second TTL — hits the database every 5 seconds), cache with pub/sub invalidation (Redis keyspace notifications or application-level events). What is the database read amplification for each approach at 1M products × 1K price changes/day?

**Question 5.** A developer proposes: "I'll hash the entire HTTP request — URL + all headers + body — as the cache key. This makes every unique request unique." What are the problems with this approach? Under what conditions is it actually correct?

Consider: headers include User-Agent, Accept-Language, Authorization tokens, request timestamps, and tracing IDs — most of which are not semantically meaningful to the response. A correct cache key includes only dimensions that affect the response. When is hashing the full request correct? (When the cache is a transparent proxy that cannot interpret the request semantics, e.g., a CDN caching signed URLs.)

---

### Theme B: Redis Internals

**Question 6.** A Redis instance with 50GB of data runs BGSAVE every 5 minutes. Users report p99 latency spikes of 2–5 seconds every 5 minutes, perfectly correlated with BGSAVE timing. Walk through exactly what is happening at the OS level. What are all the options to fix this? Which do you recommend and why?

Walk through: `fork()` system call semantics on Linux, copy-on-write page table behavior, why page table size scales with dataset size, transparent huge pages and their impact on fork time. Options: (1) shard to smaller instances, (2) disable transparent huge pages, (3) switch to AOF-only and reduce BGSAVE frequency, (4) schedule BGSAVE at off-peak hours, (5) use a replica for BGSAVE so the primary never forks.

**Question 7.** Your team argues: "We should use `appendfsync always` for our session Redis to prevent any data loss." Walk through the trade-offs. Under what conditions is `always` appropriate vs `everysec`? For session data specifically, what can you afford to lose?

Consider: `always` means one fsync per write command — throughput drops to ~10K ops/sec on typical NVMe, ~3K ops/sec on spinning disk. `everysec` means one fsync per second — lose up to 1 second of writes, but throughput stays at ~100K ops/sec. For session data: losing 1 second of session writes means users who logged in within the last second must log in again. Is that acceptable? Compare to the cost of `always`: your session service now handles 10x less traffic.

**Question 8.** In Redis Cluster, `MGET user:123:cart user:123:wishlist user:123:recommendations` sometimes works and sometimes fails with CROSSSLOT. Explain why it is intermittent, not always failing. Propose the complete fix.

The "intermittent" behavior is the key insight: the error occurs only when the keys hash to different slots, which is deterministic. If it is intermittent, why? Consider: keys being added or removed over time, different code paths generating different key formats, or a slot migration in progress (slots temporarily in transit between nodes). The fix for the cross-slot case: hash tags `{user:123}:cart`, `{user:123}:wishlist`, `{user:123}:recommendations`.

**Question 9.** You are designing a distributed rate limiter using Redis Cluster. The key is `ratelimit:{user_id}:60sec`. You need to check the current count and increment it atomically. The limit is 100 requests per 60 seconds. Write the Lua script. What guarantees does Lua provide in Redis Cluster? What happens if the user's shard goes down during the check-and-increment?

The script must: GET the current count, compare to limit, INCR if under limit, SET EXPIRE on first use. Lua scripts execute atomically on a single node. All keys referenced in the script must be on the same slot (enforced by the cluster at runtime). What is the failure mode when the node goes down mid-script? How do you handle it gracefully (hint: idempotency, timeouts, fail-open vs fail-closed)?

**Question 10.** Your production Redis has AOF persistence. The AOF file has grown to 200GB. Restarts take 45 minutes. You need to bring the restart time under 2 minutes without data loss. Walk through the exact steps.

The solution: AOF rewrite + switch to hybrid persistence. Step 1: trigger `BGREWRITEAOF` — this compacts the AOF file to the minimal set of commands needed to reconstruct current state. Step 2: after rewrite completes, enable RDB (`CONFIG SET save "3600 1 300 100 60 10000"`). Step 3: wait for the next RDB snapshot. Step 4: switch persistence to hybrid mode. Now on restart: load RDB (fast), replay only the delta AOF (small). Target: restart in 2–5 minutes. What is the data safety window during the BGREWRITEAOF operation?

---

### Theme C: Time-Series and Search

**Question 11.** You are building a real-time analytics dashboard: last 7 days of user activity at 1-second granularity, plus trends for the last year at hourly granularity. Design the storage and query strategy. Should you use PostgreSQL, Redis, or a time-series database? Why not a single storage layer?

Consider: 1-second granularity for 7 days = 604,800 data points per user. If you have 1M active users, that is 600 billion data points — not feasible to store individually per user. The correct pattern: raw 1-second data for recent window (7 days), pre-aggregated hourly rollups for historical data. Redis TimeSeries for the hot 7-day window (in-memory, fast reads), TimescaleDB for the cold historical data with continuous aggregates for hourly rollups.

**Question 12.** Your IoT platform ingests temperature readings from 100,000 sensors every second (100K writes/sec). Data must be queryable for 2 years, and "average temperature per hour" must be available for the full 2-year period. Design the complete storage solution including downsampling strategy and estimated storage requirements.

Calculate: 100K sensors × 86,400 seconds/day = 8.64 billion raw readings/day. At 12 bytes per reading (uncompressed), that is 103 GB/day or 75 TB/year. With Gorilla-style compression (10x ratio): 7.5 TB/year. With downsampling: keep raw data for 30 days (225 TB raw, 22.5 TB compressed), downsample to 1-minute averages for months 2-6 (180x reduction), downsample to 1-hour averages for year 2 (3600x reduction). What is the total storage for 2 years? What is the tradeoff of downsampling (can't reconstruct raw data)?

**Question 13.** An e-commerce platform needs: exact product lookup by ID, full-text search by name and description, filter by price range and category, and "customers also bought" recommendations. Map each requirement to the correct data store. How do you keep them in sync?

No single store handles all four optimally. Exact lookup by ID: PostgreSQL (primary key lookup, O(1)). Full-text search: Elasticsearch (inverted index, BM25 ranking). Price range + category filter: Elasticsearch (numeric range filters + term filters, fast on indexed fields). Recommendations: graph database (Neo4j) or Redis (sorted set with "also bought" scores), or PostgreSQL with collaborative filtering precomputed offline. Sync strategy: PostgreSQL is the source of truth, CDC pipeline (Debezium → Kafka) feeds all secondary stores. What is the consistency model? What happens when a product is deleted?

**Question 14.** Elasticsearch is returning stale product data — price updates in PostgreSQL are not reflected in ES search results for up to 10 minutes. You need to reduce this to under 5 seconds. Walk through the sync architecture you would design. What are the failure modes?

Current lag of 10 minutes suggests a batch sync job (polling at 10-minute intervals). Target of 5 seconds requires near-real-time CDC. Architecture: PostgreSQL WAL → Debezium → Kafka topic → ES consumer (updates ES via bulk API). Debezium captures every row change within milliseconds. Kafka provides durability and replay. ES consumer processes in micro-batches (every 1-2 seconds). ES refresh interval (default 1 second) introduces the remaining lag. Failure modes: Debezium losing connection to PostgreSQL, Kafka consumer lag growing, ES indexing backlog during traffic spikes, ES cluster splits during updates.

**Question 15.** A developer says: "I'll use Elasticsearch as the primary data store for our product catalog because it's fast for search." What are the specific technical problems with this approach? How do you explain the correct architecture?

ES is optimized for search, not for primary storage. Specific issues: (1) ES segments are immutable — updates are implemented as delete + re-insert, then segment merge, not in-place updates; (2) ES does not support ACID transactions — concurrent updates can result in lost writes; (3) ES is eventually consistent within the cluster — a write acknowledged by the primary shard may not yet be visible on replicas; (4) ES has no foreign key constraints or referential integrity; (5) ES has poor support for relational queries (joins). The correct architecture: PostgreSQL as the primary store (ACID, relational, durable), ES as a derived search index (eventually consistent, read-optimized, populated via CDC).

---

### Theme D: Cross-Topic Design

**Question 16.** Design the complete storage and caching strategy for a global multiplayer game with 10M active players and peak 1M concurrent. Players have: current game session state (changes every 100ms), leaderboard scores (updated on game end, read frequently), and historical stats (all-time records, rarely changes, read on profile view).

Map each to a store: session state → Redis (in-memory, low latency, key-value); leaderboard → Redis Sorted Sets (ZADD/ZRANK operations, O(log N)); historical stats → PostgreSQL (durable, relational). Caching for historical stats: cache aside with 10-minute TTL (rarely changes, read frequently). For leaderboard: Redis IS the cache and the data store simultaneously. For session state: no caching layer needed — Redis is already the fastest available store. What is the failure mode if Redis goes down? How do you handle regional distribution?

**Question 17.** An online banking app caches account balances. A deposit arrives. The cache and database diverge. The customer sees the old balance. Present three different architectural approaches to solve the stale balance problem, with trade-offs.

Approach 1 — Write-through: update the cache synchronously when the database is updated. Consistent but tightly couples the write path to cache availability. If cache is unavailable, does the write fail? Approach 2 — Cache-aside with short TTL: let the cache expire in 5 seconds. Simple, but 5-second windows of stale data in a banking context may violate regulatory requirements. Approach 3 — Event-driven invalidation: when a deposit is confirmed, publish an event that deletes the cached balance key. The next read rebuilds from the database. Stale window is bounded by event processing latency (typically <1 second). What happens if the invalidation event is lost? Which approach do you recommend for banking? (Answer: write-through with circuit breaker, with the database as source of truth for anything regulated.)

**Question 18.** Your team is experiencing a thundering herd: all user sessions expire simultaneously because they were created during a marketing campaign launch and given a fixed 24-hour TTL. How do you fix the current thundering herd in real time? How do you prevent it in the future?

Immediate mitigation: the thundering herd has already started — you cannot prevent the expiration, but you can add jitter to TTLs of newly written sessions right now (even if the damage from the current wave is happening). To slow the stampede: add a probabilistic early expiration check (serve the cached value 80% of the time even after TTL, recompute 20% of the time — this is the "cache warming lottery" pattern). Background refresh: before a session expires, a background job refreshes it. Future prevention: always add random jitter to TTLs — `TTL = base_ttl + random(0, base_ttl * 0.1)`. A 24-hour TTL becomes `24 hours ± 2.4 hours`, spreading expiration over a 4.8-hour window instead of a single second.

**Question 19.** Design the caching strategy for a social media platform's "trending topics" feature. Topics trend globally, per country (50 countries), and per language (20 languages). The trend list updates every 5 minutes. How many distinct cache keys do you need? What is the total cache size? How do you handle the 5-minute refresh?

Keyspace: 1 global + 50 countries + 20 languages + 50×20 country-language combinations = 1,071 distinct cache entries. If each trending topics list is 100 topics × 50 bytes average = 5KB per entry. Total: 1,071 × 5KB ≈ 5.4MB — trivially small. Refresh strategy: a background job computes all 1,071 lists every 5 minutes and writes them atomically to Redis using a pipeline. The TTL is 6 minutes (slightly longer than the compute interval to avoid a gap). The key design: `trending:{scope}:{scope_value}` where scope is `global`, `country`, or `language`. What happens if the background job fails? How do you detect staleness?

**Question 20.** You discover that a cache key bug has been leaking User A's data to User B for 72 hours. Walk through the complete incident response: detection, containment, investigation, remediation, and post-mortem. What data do you need to determine the blast radius?

Detection: likely via a user report ("I can see someone else's data") or an automated anomaly detection alert on data access patterns. Containment: immediately flush the affected cache namespace (targeted, not full flush — scope to the buggy key pattern). This stops new leakage. Investigation: (1) identify the key pattern that caused the collision, (2) query access logs for all reads from that key pattern in the 72-hour window, (3) determine which user IDs were affected and which data was exposed. Blast radius requires: cache read logs (which keys were read, which sessions/IPs read them), user-to-key mapping (which users own which keys), data classification (was the leaked data PII, financial, health data?). Remediation: fix the key generation code, deploy, verify no further collisions. Notify affected users per your breach notification policy (GDPR: 72-hour notification requirement if PII is involved). Post-mortem: root cause, timeline, detection gap (why did it take 72 hours to detect?), controls added (key namespace testing, cross-tenant access monitoring).

---

## Section 4: Homework Exercises

### Exercise 1: Design Cache Keys for a Healthcare Platform (30 minutes)

**Scenario.** A healthcare platform has five types of data:

- **Patient records**: name, date of birth, diagnosis history, medications. Highly sensitive PHI (Protected Health Information). HIPAA-regulated.
- **Doctor schedules**: which doctors are available on which days. Updated daily by office staff.
- **Appointment availability**: which 15-minute slots are open for booking. Updated every 30 minutes by a scheduling service.
- **Medical history**: lab results, imaging reports, visit notes. Read rarely (typically only by the treating physician during a visit). Never changes after creation.
- **Insurance verification**: result of an API call to the insurance provider verifying coverage for a specific procedure. Expensive call (3-second latency). Valid for 24 hours.

**Your deliverable.** For each data type, specify:
1. Cache key format
2. TTL
3. What to do on cache miss
4. Invalidation strategy
5. HIPAA compliance consideration: can this data be cached? Where? With what protections?

**Guidance for L6 thinking.**

HIPAA requires that PHI at rest is encrypted. Caching PHI in plaintext Redis violates this. Options: encrypt at the application layer before storing in Redis (key rotation is complex), use Redis with encryption at rest enabled (available in Redis Enterprise and managed cloud offerings), or avoid caching PHI entirely (trade performance for compliance simplicity).

Consider separation of sensitivity tiers: insurance verification results (coverage status for a procedure) may not be PHI if it doesn't contain diagnosis information. Doctor schedules are not PHI. Appointment availability is not PHI. Segment your cache: a compliance-scoped Redis instance for any PHI-adjacent data with stricter access controls and encryption, a standard Redis instance for non-PHI operational data.

Medical history that never changes is a strong candidate for long-TTL caching (weeks) with event-driven invalidation on the rare case that a record is amended. Insurance verification is a textbook TTL cache with a 23-hour TTL (slightly under the 24-hour validity window to avoid serving stale results at the boundary).

---

### Exercise 2: Debug a Production Redis Issue (20 minutes)

**The alert.** PagerDuty at 14:32 UTC: "Redis cache hit rate dropped from 85% to 12%." Simultaneously: "Database CPU spiked from 20% to 95%." Deployment history: code push at 14:30 UTC.

**Your investigation.** Walk through each step, including the exact Redis commands you would run:

1. **First 60 seconds**: What three Redis commands do you run immediately? What are you looking for?
2. **Minutes 2–5**: You have the metrics. The deployment diff shows 200 lines changed across 15 files. How do you narrow down which file caused the issue?
3. **Root cause identification**: The deployment diff shows a change to the cache key construction function. What specifically in that change would cause a drop from 85% to 12%?
4. **Immediate fix**: You don't have time for a full deploy cycle. What can you do in the next 10 minutes?
5. **Validation**: How do you confirm the fix is working? What metric do you watch and at what cadence?

**Guidance for L6 thinking.**

Step 1 commands: `INFO stats` (get `keyspace_hits` and `keyspace_misses` for hit rate), `SLOWLOG GET 25` (check for slow commands), `DBSIZE` (check if keyspace exploded — a key namespace bug can cause millions of unique keys to accumulate).

For the deployment diff: grep for changes to any function that constructs cache keys. Look for newly introduced calls to timestamp functions, UUID generators, or request-scoped variables (session IDs, request IDs, user-agent strings) being baked into keys.

The 12% hit rate (not 0%) is a clue: a partial bug. Perhaps only some code paths use the new key format. Some requests still hit the old keys (which are still cached and haven't expired). Over time, the hit rate would drop toward 0% as old keys expire. This helps confirm the hypothesis.

Immediate fix without deployment: if the bug is in a configuration value (not code), update the config. If it requires a code change, a fast rollback (revert the deploy) is the right call. A new deploy with the fix takes as long as the original deploy.

---

### Exercise 3: Design Persistence for a Financial Rate Limiter (20 minutes)

**Context.** A rate limiter tracks API calls per user per minute using Redis INCR + EXPIRE. If a user is allowed 1,000 requests per minute, the Redis key `ratelimit:{user_id}:minute:{minute_bucket}` holds the current count for the current 60-second window.

**Requirements.**

- If Redis restarts, rate limit counters must survive. A restart must not give users a free pass to bypass rate limits.
- Redis restart must complete within 2 minutes.
- It is acceptable to lose at most 5 seconds of counter state on a crash (a user might get up to 5 seconds of "free" requests beyond their limit after a crash).

**Your deliverable.**

1. What persistence configuration satisfies all three requirements?
2. What is the RPO (Recovery Point Objective) of your configuration?
3. What is the RTO (Recovery Time Objective)?
4. How do you test that your configuration actually meets the requirements? Describe the exact test procedure.
5. What are the operational trade-offs of your configuration vs no persistence?

**Guidance for L6 thinking.**

The 5-second data loss tolerance maps directly to `appendfsync everysec` — worst case is 1 second of loss, which is well within the 5-second tolerance. The 2-minute restart requirement rules out AOF-only persistence for large datasets (replaying hours of AOF commands takes much longer). Hybrid persistence (RDB + AOF delta) satisfies both: RDB gives fast recovery (load snapshot, then replay only the delta since the snapshot). With hourly RDB snapshots and `appendfsync everysec` AOF, restart time is: time to load RDB + time to replay at most 1 hour of AOF commands. Size the test: if your Redis holds 1GB of rate limit data and writes 10MB/min of commands, the AOF delta after 1 hour is ~600MB, which replays in ~30 seconds. Well within 2 minutes.

Test procedure: (1) run 5 minutes of synthetic traffic at maximum rate (all users at 95% of their rate limit), (2) `kill -9` the Redis process (hard crash, not graceful shutdown), (3) restart Redis, (4) measure: how many increment commands were lost (compare expected count to actual count in the first minute after restart), (5) confirm loss is under 5 seconds worth of traffic.

---

### Exercise 4: Migrate 10 Billion Rows of Metrics to TimescaleDB (45 minutes)

**Background.** 3 years of IoT sensor data in PostgreSQL. 500 sensors, 1 reading per second, 3 years = approximately 47 billion rows (500 × 86,400 × 1,095 days). Current state: queries for the last 24 hours take 10+ minutes, insert latency has grown to 500ms, replication lag is 4 hours.

**Your deliverable.** Design the complete migration plan:

1. How do you migrate 47 billion historical rows without losing new data during the migration?
2. Old data (older than 6 months) will be downsampled to 1-minute averages. How do you execute the downsampling as part of the migration?
3. How do you validate that the migration is correct before cutting over?
4. How do you cut over production reads and writes to TimescaleDB with minimal downtime?
5. What is your rollback plan if something goes wrong after cutover?

**Guidance for L6 thinking.**

Dual-write is the key to zero data loss during migration. Start writing new sensor readings to both PostgreSQL and TimescaleDB simultaneously. While dual-write runs, migrate historical data in parallel monthly batches (47 billion rows ÷ 36 months ≈ 1.3 billion rows/month). Use 12 parallel workers, one per month of data for the most recent year. Each worker: `INSERT INTO timescaledb_table SELECT * FROM postgres_table WHERE ts >= '2024-01-01' AND ts < '2024-02-01'`.

Downsampling as part of migration: for data older than 6 months, run the downsampling query in PostgreSQL, insert the aggregated data into TimescaleDB at 1-minute granularity, then discard the raw rows. This reduces the migration volume significantly.

Validation: for each migrated month, run `SELECT DATE(ts), COUNT(*) FROM postgres_table GROUP BY 1` and `SELECT DATE(ts), COUNT(*) FROM timescaledb_table GROUP BY 1` — row counts must match. For a sample (10 random days per month): compare MIN, MAX, AVG for each sensor.

Cutover: with dual-write running and all historical data migrated, flip the read path to TimescaleDB. Monitor for 30 minutes. Stop writing to PostgreSQL (write to TimescaleDB only). PostgreSQL remains running for 2 weeks as the rollback target.

---

### Exercise 5: Design an Elasticsearch Sync Pipeline (30 minutes)

**Background.** Product catalog in PostgreSQL: 5 million products. Each product has: name, description (up to 2,000 words), price, inventory count, category, and status (active/inactive). Products update 10,000 times per day from various sources: pricing engine, inventory management, editorial team, automated scrapers.

**Your deliverable.**

1. Initial load: how do you get all 5 million products into Elasticsearch for the first time?
2. Ongoing sync: how do you keep ES updated within 5 seconds of PostgreSQL changes?
3. ES downtime: ES goes down for 2 hours for maintenance. How do you handle the backlog of changes that occurred during the outage?
4. Deletes: a product is soft-deleted in PostgreSQL (status set to 'deleted'). How do you remove it from ES search results?
5. Validation: how do you verify that ES and PostgreSQL are in sync, and how often do you run this check?

**Guidance for L6 thinking.**

Initial load: `pg_dump --format=copy | parallel --jobs=8 ./es_bulk_import.sh`. Split the 5M products into batches of 1,000. ES bulk API ingests at ~10K documents/sec per shard. 5M products / 10K per sec = ~500 seconds (8 minutes) for initial load. During initial load, disable ES indexing optimizations: set `refresh_interval = -1` and `number_of_replicas = 0`, then re-enable after bulk import completes. This speeds bulk import by 3-5x.

Ongoing sync: PostgreSQL WAL → Debezium CDC connector (runs as a Kafka Connect worker) → Kafka topic `products.changes` → ES sink connector (Kafka Connect) → ES. Debezium captures every UPDATE, INSERT, and DELETE from the products table within milliseconds. The ES sink connector processes in micro-batches every 1 second. ES refresh interval (default 1 second) introduces the final latency. Total pipeline latency: 2-3 seconds, within the 5-second target.

ES downtime backlog: Kafka retains messages with a 7-day retention policy. When ES comes back, the Kafka consumer resumes from where it left off. 2 hours of backlog at 10,000 changes/day = ~833 changes — the consumer will catch up in seconds.

Delete handling: Debezium emits a delete event with the `before` image of the row (including the product ID). The ES sink connector translates this to an ES `DELETE /products/_doc/{product_id}` call. For soft deletes (status = 'deleted'), Debezium emits an UPDATE event. The ES sink connector updates the product's status field. The search query must filter `status: active` to exclude soft-deleted products.

Validation: daily job samples 1% of products (50,000 products) randomly from PostgreSQL. For each, fetches the corresponding ES document and compares: name, price, status, updated_at timestamp. Acceptable drift: documents updated in the last 5 seconds may legitimately differ. Documents updated more than 5 seconds ago that differ indicate a sync failure. Alert if drift rate exceeds 0.1%.

---

## Section 5: Interview Quick Reference Card

This section is designed for 15-minute review before an interview. Read it once. Then close the document and see how much you can reconstruct.

### Cache Key Design

- "Resource type + ID + every dimension that changes the response. Never timestamps, never nonces."
- "Multi-tenant SaaS: always include tenant ID in the key or you will leak data across tenants."
- "Bad key = 0% hit rate. Good key = deterministic for the same logical request."
- "Each dimension you add to a cache key reduces the hit rate. Add only what changes the response."
- "Thundering herd prevention: add jitter to TTLs. Base TTL plus random 0–10% of base."

### Cache Poisoning

- "Poisoning = wrong value under a valid key. Unlike a miss, a poisoned HIT silently returns wrong data."
- "Always validate before caching: status 200, body non-empty, type matches expected. Never cache 5xx responses."
- "Recovery: targeted DEL for known bad keys; controlled shard-by-shard flush for unknown scope. Never flush all at once."
- "Error responses cached with 5-minute TTL = 5-minute outage even after the backend recovers."

### Redis Persistence

- "RDB = point-in-time snapshot. Fast restart. Lose data since last snapshot (minutes to hours)."
- "AOF = command log. Minimal loss (1 second with everysec). Slow restart for large files."
- "Hybrid = RDB + AOF delta. Fast restart (load snapshot first) + minimal loss (replay only delta). Use this in production."
- "appendfsync always: zero data loss, ~10K ops/sec. appendfsync everysec: 1-second loss, ~100K ops/sec."
- "Fork overhead: 50GB Redis → fork takes 2–5 seconds → p99 spikes. Disable transparent huge pages, shard smaller instances, or use a replica for BGSAVE."

### Redis Cluster

- "16,384 hash slots. CRC16(key) mod 16384 → slot → node."
- "MOVED error = permanent redirect (the slot has moved, update your slot map)."
- "ASK error = temporary redirect (slot is currently migrating, follow the redirect but don't update your map)."
- "CROSSSLOT: multi-key operations require all keys on the same slot. Fix with hash tags: {user:123}:profile."
- "Hash tag: only the content inside the first {} is hashed. Everything else in the key is ignored for slot assignment."
- "Smart clients cache the slot-to-node mapping: no redirect overhead for the common case."
- "Minimum viable Redis Cluster: 3 master nodes + 3 replicas (6 total nodes)."

### Time-Series Databases

- "Use time-series DB when: write rate exceeds 5K/sec, retention exceeds 90 days, or you need downsampling."
- "Gorilla compression: delta-of-delta encoding for timestamps, XOR encoding for values. 12 bytes → 1–2 bytes per data point."
- "TimescaleDB: PostgreSQL extension, hypertables partition by time, same SQL interface, no app code change."
- "Downsampling: keep raw data for recent window, aggregate to 1-minute then 1-hour buckets for historical data."
- "PostgreSQL VACUUM falls behind on append-heavy time-series workloads. This is a design signal, not a tuning problem."

### Elasticsearch and Inverted Index

- "Inverted index: word → sorted list of document IDs (posting list). O(1) lookup per term."
- "BM25 (Best Match 25): ranking formula considering term frequency (TF) and inverse document frequency (IDF)."
- "Segments are immutable. Updates = delete + re-insert. Periodic segment merge = compact and remove deleted docs."
- "ES refresh interval: 1 second default. New documents visible in search after ~1 second, not instantly."
- "Never use ES as a primary data store. No ACID transactions, no referential integrity, eventually consistent."
- "Correct architecture: PostgreSQL (primary) → CDC pipeline → Elasticsearch (search index)."
- "CDC stack: Debezium (reads PostgreSQL WAL) → Kafka → ES consumer. Lag: 1–3 seconds end-to-end."

### Key Numbers to Memorize

| Metric | Value |
|--------|-------|
| Redis single-node throughput | 100K–500K ops/sec |
| Redis Cluster hash slots | 16,384 |
| Redis Cluster minimum nodes | 6 (3 primary + 3 replica) |
| AOF everysec data loss | Up to 1 second |
| Fork overhead (50GB dataset) | 2–5 seconds |
| Gorilla compression ratio | 6–12x (12 bytes → 1–2 bytes per point) |
| ES refresh interval (default) | 1 second |
| TimescaleDB vs raw PG compression | ~10x better for time-series |
| TimescaleDB vs raw PG query speed | 10–50x faster for time-range queries |
| Debezium → Kafka → ES end-to-end lag | 1–3 seconds |

### The Three Questions an L6 Always Asks

When approaching any caching or storage design question at the staff level, the first three questions are always:

1. **What is the failure mode?** Not "does this work?" but "what breaks first, and what is the blast radius when it does?"
2. **What are the second-order effects?** A fix that solves the immediate problem but creates a thundering herd, a key namespace explosion, or a replication bottleneck is not a fix.
3. **How do you validate it is working?** Metrics, alerts, and runbooks are part of the design, not afterthoughts.

An L5 engineer describes what a system does. An L6 engineer describes what a system does, what it does when it fails, how you detect that failure, and what you do next.

---

*End of Chapter 32: Redis and Cache Internals*

*End of Section 4: Storage Systems Deep Dive*
## Supplemental Brainstorming: Chapter 32 -- Redis Internals

*Questions 21-40: Advanced patterns and cross-chapter integration.*

---

### Section A: Advanced Redis Patterns (Q21-Q30)

---

**Question 21 -- Redis Pub/Sub vs Redis Streams: Pick One**

A product manager asks you to add real-time notifications to your e-commerce app. Events include order placed, payment confirmed, and shipment updated. You reach for Redis. There are two options: Pub/Sub and Streams. Your interviewer wants you to choose one and justify it.

- Redis Pub/Sub delivers messages only to subscribers connected at the time of publish. If a subscriber disconnects for 2 seconds during a traffic spike, those messages are gone permanently. There is no replay, no persistence, no consumer group acknowledgment. The failure mode is silent data loss.
- Redis Streams stores messages in an append-only log. Consumer groups read with explicit acknowledgment (XACK). If a consumer crashes mid-processing, its pending messages appear in XPENDING and are re-assigned via XAUTOCLAIM after a configurable idle timeout. Messages persist until XTRIM or MAXLEN trims them.
- For order lifecycle events, Streams is almost always correct. Missing an "order confirmed" event is not acceptable -- the customer may never receive the confirmation email. Pub/Sub is appropriate only for ephemeral signals: live presence indicators, game state, dashboard counters where a missed update is corrected by the next one arriving in milliseconds.

Follow-up: Your team argues Pub/Sub is simpler to implement. You agree it is simpler. Under what load and what message loss tolerance does the simplicity advantage disappear and Streams becomes mandatory? Frame your answer in concrete terms: at what percentage of missed events does your on-call team start getting paged?

---

**Question 22 -- Redis Streams as a Lightweight Kafka Alternative**

Your startup cannot afford a Kafka cluster. You are already running Redis. An engineer proposes using Redis Streams for your internal event bus -- order events, inventory updates, audit logs. Your interviewer asks you to compare Redis Streams to Kafka and identify the three points where Streams breaks down at scale.

- Redis Streams supports consumer groups, XACK acknowledgment, XPENDING pending-entry lists, and replay from any stream offset. This covers a large fraction of Kafka's core use cases and is a legitimate choice for small to medium systems.
- Limitation 1 -- memory cost of retention: all Streams data lives in memory. At 1TB of event history, Redis is prohibitively expensive (a 209GB managed instance costs roughly $5,000/month). Kafka stores data on commodity SSDs at $0.01-0.02 per GB per month. Limitation 2 -- no partition-level ordering across nodes: a single Redis Stream must reside on one hash slot for ordering to be meaningful. Kafka partitions provide parallel ordered consumption across multiple brokers by design. Limitation 3 -- no connector ecosystem: Kafka Connect offers 200+ source and sink connectors, schema registry, and exactly-once producer semantics. Redis Streams has none of this natively.
- Decision rule: Redis Streams is right when retention fits in memory (hours to a few days), total event volume is under 50GB, and the team is small. Plan a Kafka migration when you hit those thresholds.

Follow-up: You use Redis Streams and your stream grows to 50 million entries over 3 months, consuming 80% of memory. Some consumer groups are 6 hours behind (nightly batch jobs). How do you trim safely without losing events not yet consumed? What does XTRIM with MINID do differently from XTRIM with MAXLEN?

---

**Question 23 -- Pipeline Batching to Reduce Round-Trip Time**

Your Redis client makes 50 individual GET calls in a tight loop to build a single API response. Redis latency is 1ms. Your API response time is 60ms. Your interviewer asks you to fix this without changing Redis data structures and without using MGET.

- The root cause is serial round-trips. Each command waits for the previous reply before the next is sent. At 1ms RTT, 50 serial commands = 50ms in network latency alone, before Redis execution time. The fix is not to speed up Redis -- it is to eliminate the serial waiting.
- Redis pipelines batch multiple commands into a single TCP write. The client buffers all 50 GETs, flushes them in one packet, Redis processes them in order and sends all 50 replies in one response. Network cost drops from 50 round-trips to 1 round-trip. Expected latency improvement: ~50ms removed from the network portion.
- Pipelines are not atomic. Other client connections can interleave commands between pipeline entries. Pipelines guarantee execution order within the batch but not isolation from other clients. For atomic multi-command writes, use MULTI/EXEC or Lua scripts. Most Redis client libraries recommend pipeline batch sizes of 100-1000 commands; above 10,000, outbound buffer overhead becomes counterproductive.

Follow-up: You pipeline 1,000 GET commands and notice a brief 200MB spike in Redis server-side memory. Explain why (Redis buffers the full reply in memory before sending it). Your operations team asks for a maximum pipeline size that keeps the server-side reply buffer under 50MB. Estimate that limit, showing your calculation.

---

**Question 24 -- SCAN vs KEYS: Why KEYS is a Production Outage Waiting to Happen**

A junior engineer writes a background job that runs `KEYS user:*` every 5 minutes to count active user sessions and post the count to a metrics dashboard. In staging (100K keys) it runs in 2ms. In production (15 million keys) Redis blocks all commands for 3 seconds every 5 minutes. Explain what happened and fix the entire approach.

- Redis is single-threaded for command execution. KEYS is O(N) over the entire keyspace: for 15 million keys, Redis must scan every hash table bucket before returning any result. During those 3 seconds, no other commands execute -- no GETs, no SETs, no health check replies. Every client waiting for Redis times out. Your monitoring system is causing the outage it was meant to detect.
- SCAN cursor MATCH user:* COUNT 100 iterates incrementally. Each call processes a small batch of hash table buckets and returns immediately. Other commands execute between SCAN calls. Total work is the same O(N) but spread over thousands of fast, non-blocking iterations.
- Better fix for this specific use case: do not scan at all. Maintain a dedicated counter key `sessions:active:count` that you INCR on session creation and DECR on deletion. Handle TTL-based expiry with keyspace notifications. The dashboard reads one key in microseconds.

Follow-up: SCAN is non-atomic. Keys can be created or deleted between calls. If you need a point-in-time consistent snapshot of all keys matching a pattern -- for an audit report -- SCAN cannot guarantee completeness. Design a consistent inventory mechanism that uses neither KEYS nor SCAN and does not require Redis 7.0+ features.

---

**Question 25 -- Lua Scripting for Atomic Multi-Step Operations**

You implement a token bucket rate limiter with two separate Redis commands: GET current tokens, then DECR if tokens > 0. Your interviewer points out a race condition that allows 2x the permitted burst at high concurrency. Fix it using Lua, and explain the operational risk of Lua in production.

- The race condition: two simultaneous requests for user 42 with 1 token remaining both execute GET and see 1. Both conclude they can proceed. Both execute DECR. Count becomes -1. Two requests proceed when the limit was 1. At high concurrency, this allows unlimited bursts past the limit.
- Redis evaluates Lua scripts atomically: the entire EVAL or EVALSHA script runs to completion before any other command from any connection executes. Encoding the GET-check-DECR logic in Lua eliminates the race. Use SCRIPT LOAD to upload the script once and get its SHA. Call EVALSHA on every request to avoid resending the script text (hundreds of bytes) on each call.
- Lua scripts block Redis for their entire duration. A well-written rate limiter script completes in under 1ms. Never put file I/O, network calls, or unbounded loops inside a Redis Lua script. Redis kills scripts exceeding `lua-time-limit` (default 5000ms) with a BUSY error, which blocks Redis in the same way KEYS does.

Follow-up: You need the rate limit check atomic across 3 keys in Redis Cluster: user limit, IP limit, and global API limit. Your Lua script references all 3 keys. It fails with CROSSSLOT. Explain the cluster constraint, and redesign the key layout using hash tags to colocate all 3 keys on the same slot without changing the semantic meaning of each limit.

---

**Question 26 -- Redlock: Distributed Locking and Its Controversy**

You need a distributed lock so only one invoice generation job runs at a time across 50 app servers. A colleague proposes `SET lock:invoice:{id} {uuid} NX EX 30`. You propose Redlock. Your interviewer wants you to explain Redlock, defend it, and then explain why a prominent database researcher said it is not safe.

- The simple SET NX lock has two failure modes: if the Redis instance fails while the lock is held, the lock disappears and all workers race to acquire it. With Sentinel, there is a window where the lock has been SET on the primary but not yet replicated -- if the primary fails, the promoted replica has no lock record and two workers acquire the "same" lock concurrently.
- Redlock uses 5 independent Redis primaries (not a cluster). To acquire: record the start time, then send SET key uuid NX PX ttl to all 5. The lock is considered acquired if at least 3 of 5 succeed AND the elapsed time to acquire is less than ttl minus a clock drift factor. To release, a Lua script on all 5 nodes checks that the stored value matches uuid before deleting, preventing release of another client's lock.
- Martin Kleppmann's critique: a GC pause can cause a client to believe it holds the lock after the TTL has expired. Client A acquires the lock, GC pause for 35 seconds, lock expires, Client B acquires the lock, Client A resumes thinking it still holds it -- both clients are in the critical section. Antirez responded that fencing tokens at the resource layer solve this: each lock acquisition returns a monotonically increasing token; the resource server rejects operations with stale tokens. The practical takeaway: Redlock is safer than single-instance locks but should not be the sole correctness mechanism for financial operations without fencing tokens on the resource side.

Follow-up: You are using Redlock to protect a payment deduction. The client acquires the lock, deducts $100, then GC pauses for 45 seconds. The lock expires. Another client acquires the lock and deducts $100 again. The user is charged twice. What change outside of Redis prevents this double-charge regardless of what the lock does?

---

**Question 27 -- Sorted Sets for Leaderboards**

You are building a competitive game leaderboard for 5 million players. Requirements: (1) update a player's score in real time, (2) get a player's current rank, (3) display the top 100 players, (4) show the 50 players above and below a given player. You must support 50,000 score updates per second at peak. Pick your data structure and justify every operation's complexity.

- Redis Sorted Sets (ZSET) handle all four operations natively. ZADD updates or inserts a score in O(log N). ZREVRANK returns rank in O(log N). ZREVRANGE with indices 0-99 returns the top 100 in O(log N + 100). For nearby players: ZREVRANK for rank R, then ZREVRANGE from R-50 to R+50 -- O(log N + 100). At 5 million members: log2(5M) ≈ 23 comparisons per operation. At 50,000 updates/second, this is well within single-node throughput capacity.
- Memory estimate: each entry requires a 64-bit double score plus the member string. For member strings like "user:7823451" (12 bytes), each entry uses roughly 80-100 bytes in hashtable encoding. At 5 million members: 400-500MB. Fits on a single Redis instance with headroom.
- Tie-breaking: sorted sets order equal-score members lexicographically by member name. If tie-breaking should favor earlier achievement, encode time into the score: `effective_score = points * 1_000_000 + (1_000_000 - seconds_since_epoch_mod_1000000)`. The player who reached the score earlier has a slightly higher fractional value and ranks above equal-score opponents.

Follow-up: You also need per-country leaderboards for 50 countries. Naively: 51 sorted sets, 51 ZADDs per score update. At 50,000 updates/second that is 2.55 million Redis commands/second -- approaching single-node throughput limits. Design an approach that reduces ZADD fan-out while still supporting per-country top-100 queries with sub-second latency.

---

**Question 28 -- Sorted Sets for Sliding Window Rate Limiting**

Your API allows 100 requests per user per 60-second window. Your current INCR+EXPIRE implementation uses a fixed window. A user discovers they can make 100 requests at 11:59:59 and 100 more at 12:00:01, sending 200 requests in 2 seconds without triggering the limit. Replace this with a sliding window using a Redis Sorted Set.

- For each user, maintain a sorted set where the score is the request timestamp in milliseconds and the member is a unique request ID (UUID or timestamp+nonce). On each request, run a Lua script atomically: (1) ZREMRANGEBYSCORE to remove entries older than now_ms - 60000, (2) ZCARD to count remaining entries in the window, (3) if count >= 100 return -1 (rejected), (4) ZADD with the new entry, (5) EXPIRE the key to 60 seconds so inactive user keys do not accumulate.
- Lua is required for atomicity. Without it, two simultaneous requests at count 99 both pass the ZCARD check and both get added, bringing the count to 101. The Lua script makes the check-and-insert atomic.
- Memory cost: at 100 entries per window per user, each sorted set uses at most ~10KB. At 1 million concurrently active users: 10GB. A dedicated rate-limiting Redis cluster with 16GB RAM handles this with room to spare -- worth calculating before deploying to avoid surprises.

Follow-up: The rate limit key `ratelimit:user:42` and a separate metadata key `ratelimit:meta:user:42` (storing user tier and custom limit) land on different hash slots in Redis Cluster. Your Lua script needs both keys. It fails with CROSSSLOT. Solve this using hash tags and explain the trade-off: colocating all hot-user keys on one slot concentrates load on one node. At what per-user request rate does this hot-spot actually become a problem?

---

**Question 29 -- Replication Lag and Split-Brain in Redis Sentinel**

Your Redis Sentinel setup has one primary in us-east-1a and two replicas in us-east-1b and us-east-1c. `down-after-milliseconds = 5000`. Network latency between the primary and one replica spikes to 800ms for 30 seconds. Walk through what users experience during the spike, then model a full partition that triggers split-brain and describe the permanent data loss.

- During the latency spike: Redis replication is asynchronous -- the primary confirms writes to clients immediately without waiting for replica acknowledgment. The affected replica receives writes with 800ms delay. Reads from that replica return data up to 800ms stale. For session validation or cart reads, 800ms staleness may be acceptable. For checkout balance validation, this replica must not be used -- the price of reading stale data is overselling or incorrect charges.
- Split-brain scenario: the primary becomes completely unreachable to Sentinel. Sentinel quorum declares it ODOWN. A replica is promoted. Writes now go to the new primary. The old primary has not crashed -- some clients can still reach it and continue writing. When the partition heals, the old primary discovers a higher-epoch primary exists, demotes itself to a replica, and discards all writes it accumulated during the partition. Those writes are permanently and silently lost.
- Mitigation: configure `min-replicas-to-write 1` and `min-replicas-max-lag 10`. This forces the primary to stop accepting writes if no replica is replicating with lag under 10 seconds. The isolated primary cannot accumulate writes that will be discarded at failover. The trade-off: if replicas fall behind, the primary returns errors. This is a deliberate CP choice -- consistency over availability.

Follow-up: You set `min-replicas-to-write 1` and `min-replicas-max-lag 10`. A replica lag spike causes your primary to stop accepting writes for 8 seconds. Your on-call team asks: should we disable this setting to restore availability? What business data would you consult before making this decision? What is the reversible way to test disabling it without permanently changing the configuration?

---

**Question 30 -- Redis Cluster vs Redis Sentinel: When to Choose Which**

A new team is launching a recommendation feature with 80GB of cached data, 150K writes/second at peak, and a requirement for automatic failover. They ask you: Cluster or Sentinel? Your interviewer wants a decision framework with concrete thresholds, not definitions from the Redis documentation.

- Redis Sentinel provides high availability for a single logical Redis instance. It monitors the primary, detects failure, and promotes a replica automatically. It does not increase data capacity or write throughput -- you still have one primary. Use Sentinel when: your entire dataset fits on one node AND your write throughput fits within single-node capacity (~100K-200K ops/second depending on command mix). Multi-key commands work normally. Operationally simpler: 1 primary + 2 replicas + 3 Sentinel processes.
- Redis Cluster shards data across multiple primaries using 16,384 hash slots. This scales both data capacity (more nodes = more total memory) and write throughput (each primary handles a subset of writes). The cost: CROSSSLOT errors on multi-key operations across different slots, hash tag discipline required for co-location, and minimum 6 nodes (3 primaries + 3 replicas). At 80GB data and 150K writes/second: a single large instance might hold 80GB but 150K writes/second approaches saturation. Two primaries each handle 75K writes/second and 40GB of data -- a cleaner fit.
- Common mistake to call out: teams use Cluster "for HA" when they actually fit within Sentinel's capacity. The 6-node minimum and CROSSSLOT complexity are not worth it if a single node is sufficient. Always calculate both thresholds before recommending Cluster.

Follow-up: Your dataset is 40GB today, growing at 5GB/month. Your current node has 64GB RAM. You have roughly 4 months before you outgrow it. Walk through the Sentinel-to-Cluster migration: what happens to existing keys, how do you resolve the CROSSSLOT errors that appear in application code after the migration, and how do you run a zero-downtime cutover in production?

---

### Section B: Cross-Chapter Integration (Q31-Q40)

---

**Question 31 -- Ch32 + Ch28: Session Storage -- Redis vs PostgreSQL at 10M Users**

You store session tokens in Redis with a 30-minute TTL. 10 million users, 2 active sessions each = 20 million session keys. Your VP of Engineering proposes moving sessions to PostgreSQL (which you already operate) to simplify the stack. Do the math on both options and identify the one scenario where PostgreSQL is actually the better choice.

- Redis memory calculation: each session stores a token (32 bytes), user ID (8 bytes), permissions bitmap (16 bytes), locale (8 bytes), device fingerprint (64 bytes), plus ~50 bytes of Redis key and hash table overhead = roughly 310 bytes per session. 20 million sessions x 310 bytes = 6.2GB. A single managed Redis node (13GB RAM, ~$160/month) holds this with growth room. Each session GET returns in under 1ms.
- PostgreSQL throughput analysis: assume 50% of 10M users are online at peak = 5M active sessions. At one session validation SELECT per request, and requests arriving every 10 seconds per session: 500K SELECTs/second. A well-tuned PostgreSQL primary handles 10K-40K simple indexed SELECTs/second. You need 3-5 read replicas behind PgBouncer to reach 500K reads/second. Per-lookup latency: 2-10ms vs sub-millisecond for Redis. This is operationally complex and significantly slower.
- When PostgreSQL beats Redis for sessions: session data requires JOINs to validate (e.g., linked subscription object), session creation must be transactionally atomic with another write, or user count is small enough that SELECT load is under 5K/second. At 10M users with the above profile, Redis is the correct choice.

Follow-up: You keep sessions in Redis. A security incident requires immediate enumeration of all active sessions for user 42 (who may have dozens across devices) and revocation. Redis does not support secondary index lookups by value. Design the additional data structure that makes this O(1) without a SCAN, and show the write path that keeps the index consistent when sessions expire naturally via TTL.

---

**Question 32 -- Ch32 + Ch28: TTL Precision and the Thundering Herd at Expiry**

You run a batch cache warm-up job every hour. It writes 10,000 product listing cache entries to Redis, all with `TTL = 3600`. Exactly one hour later, all 10,000 keys expire within the same second. Your catalog database receives 10,000 concurrent queries, overwhelms the connection pool (100 connections), and query latency spikes to 30 seconds. Users see timeouts. Diagnose the root cause and propose three independent mitigations.

- Root cause: synchronized expiry from deterministic TTLs on keys written at the same time. The batch warm-up created a time bomb: a perfectly effective cache that expires all at once. The database connection pool (100 connections) faces 10,000 simultaneous queries. Queue depth grows. Latency rises. Timeouts cascade. This is the textbook thundering herd.
- Mitigation 1 -- jitter the TTL at write time: replace `TTL = 3600` with `TTL = 3600 + randint(-300, 300)`. Keys expire over a 10-minute window. Database receives ~17 queries/second instead of 10,000 in one second. Mitigation 2 -- proactive background refresh: a background process watches TTLs and refreshes keys when TTL drops below 10% of the original (360 seconds for a 3600-second TTL). The key never actually expires from the application's perspective. Mitigation 3 -- probabilistic early expiration (PER): on a cache read, before returning the value, calculate `if (TTL_remaining < beta * log(random())) { refresh_now() }`. This is the algorithm from the cache stampede prevention literature. Worth naming in a Staff interview -- it shows you have read beyond the obvious.
- All three can be combined. Jitter is the lowest-effort fix. PER is the most elegant (no background process required). Background refresh is the most predictable for traffic patterns.

Follow-up: You implement jitter. After a Redis flush (node replacement with data loss), all keys are written simultaneously during post-flush warm-up. Jitter does not help because every key is new at the same moment. The thundering herd occurs on the first load after a cold start. Design a warm-up sequence for the cold-start case that staggers key writes to prevent the initial thundering herd.

---

**Question 33 -- Ch32 + Ch31: In-Process LRU Cache Warm-Up After Rolling Restart**

Your Redis cache serves product listings with 95% hit rate. You add a local in-process LRU cache (10K entries, Caffeine) on each of 20 app servers as a first tier. Hit rate rises to 99.9%. You deploy via rolling restart. Each restarted server has a cold in-process cache. Design the warm-up strategy and address the cache invalidation gap.

- Organic warm-up impact: a cold server handles 5% of traffic. Its effective hit rate is 0% (local) + 95% (Redis fallback) = 95%. Fleet-wide effective hit rate: 0.95 x 5% + 0.999 x 95% = 99.7%. This is acceptable. But with 20 sequential restarts at 5 minutes each to warm up organically, you run with degraded hit rate for 100 minutes. Quantify this tradeoff before deciding whether pre-warming is worth the complexity.
- Pre-warming strategy -- popularity-based: maintain a sorted set `cache:popularity` where each member is a cache key and the score is hit count. Every server increments the score on each local cache miss (ZINCRBY). When a server restarts, before entering load balancer rotation (enforced via a readiness probe), it calls ZREVRANGE cache:popularity 0 9999, fetches those 10K keys from Redis via pipeline, and populates the in-process cache. Warm-up takes seconds. Server enters rotation with a pre-warmed cache.
- Invalidation gap: the in-process cache has no invalidation channel. If a product price changes in the database, you delete the Redis key, but all 20 servers still serve the old price from their local caches until the local TTL expires. Solution: set local TTL much shorter than Redis TTL -- local TTL = 30 seconds, Redis TTL = 5 minutes. Maximum staleness = 30 seconds. For most use cases this bounds the problem acceptably.

Follow-up: A flash sale starts. Prices change for 500 products. You need in-process cache invalidation on all 20 servers within 1 second. You cannot use Redis Pub/Sub (too unreliable for this). You cannot afford Kafka for this internal signal. Design the simplest mechanism that achieves sub-second invalidation on all 20 servers with at-least-once delivery.

---

**Question 34 -- Ch32 + Ch33: Real-Time Notifications -- Pub/Sub vs Streams vs Kafka**

You are building a real-time notification system. When an order ships, you must push a notification to all of the customer's connected devices (1-3 per customer) and update 3 internal dashboards. Peak: 1 million connected customers. Evaluate Redis Pub/Sub, Redis Streams, and Kafka on persistence, delivery guarantee, consumer groups, and replay.

- Redis Pub/Sub: no persistence, at-most-once delivery, no consumer groups, no replay. A subscriber disconnected at publish time misses the message permanently. For device notifications: acceptable as a best-effort signal if you have an APNs/FCM fallback for disconnected clients. For dashboards: acceptable if the next event corrects any missed update. Not acceptable if every notification must be delivered exactly once.
- Redis Streams: persistent until trimmed, at-least-once delivery via XACK, consumer groups with re-delivery on crash, replay from any entry ID. A fan-out worker reads stream events and delivers to each subscriber's device via push service. Streams does not natively broadcast to 1 million recipients simultaneously -- you build the fan-out layer on top.
- Kafka: built for this use case at scale. Partitioned topics allow parallel consumption. Exactly-once semantics with transactional producers and idempotent consumers. Configurable retention (hours to years). Replay from any offset. Kafka Connect ecosystem. The fan-out architecture is the same as Streams -- Kafka does not push to devices directly -- but Kafka's retention and consumer group maturity handle compliance and scale naturally. Operational cost: 3-broker cluster adds 2-3 days of SRE setup. For a startup, Redis Streams is pragmatic. For 1 million subscribers with SLA requirements, Kafka's guarantees are worth the overhead.

Follow-up: You choose Redis Streams. Six months later, legal requires all shipment notifications retained for 2 years for consumer dispute resolution. Redis Streams at 2-year retention would require 500GB-1TB of memory just for this one stream. Design the migration path to Kafka without breaking existing consumers in the transition window.

---

**Question 35 -- Ch32 + Ch33: Exactly-Once Delivery in Redis Streams**

Your Redis Stream consumer reads a payment event (deduct $50 from a wallet), executes the deduction, and ACKs with XACK. The consumer crashes after the deduction but before the ACK. XAUTOCLAIM re-delivers the event on restart. The wallet is deducted twice. Fix this without migrating to Kafka, using idempotency at the consumer layer.

- Redis Streams consumer groups guarantee at-least-once delivery. A message is re-delivered if it remains in the pending-entry list past the idle timeout. There is no built-in exactly-once. You must implement idempotency at the consumer.
- Idempotency pattern: each stream entry has a unique ID (e.g., 1719000000000-3). Before processing, the consumer checks a deduplication record in PostgreSQL. If the record exists, skip the deduction and ACK immediately. If not: begin a database transaction, check again inside the transaction (to prevent phantom reads), execute the wallet deduction, insert the deduplication record, commit, then ACK in Redis with XACK. The database transaction makes the deduction and deduplication record atomic. If the consumer crashes after the commit but before the ACK, re-delivery hits the deduplication check and is skipped.
- The deduplication record must live in PostgreSQL, not Redis. If Redis loses the deduplication SET (crash, eviction), re-delivery gets no protection. Storing it in the same durable system as the wallet balance guarantees the deduplication survives any Redis failure.

Follow-up: Your stream processes 10,000 payment events/second across 10 consumers. Each deduplication SELECT adds 2ms. At 1,000 events/second per consumer, this adds 2 seconds of database query time per second per consumer -- unsustainable. Design a deduplication approach that handles 10,000 events/second without adding per-event database reads on the critical path.

---

**Question 36 -- Ch32 + Ch36: Network Partition Across 3 Redis Regions**

You run Redis Cluster across 3 regions: US-East (slots 0-5461), EU-West (slots 5462-10922), AP-South (slots 10923-16383). A BGP routing issue isolates EU-West for 4 minutes. Describe: what writes succeed, what data is lost, and design a strategy to minimize loss for inventory counts specifically.

- What Redis Cluster does: it requires a majority of cluster nodes reachable to accept writes. EU-West cannot reach US-East or AP-South. After `cluster-node-timeout` (default 15 seconds), EU-West primaries detect they lack majority and stop accepting writes. EU-West becomes read-only. This is the safe behavior -- but there is a 15-second window at the start of the partition where EU-West may still accept writes.
- Data loss window: writes accepted during those 15 seconds exist only on EU-West nodes. When the partition heals and epochs reconcile, EU-West writes from that window may be rolled back. This is permanent, silent data loss. For inventory counts, lost writes mean wrong counts, which cause overselling.
- Mitigation: (1) reduce cluster-node-timeout to 5 seconds (cuts the loss window from 15s to 5s). (2) Store inventory counts in PostgreSQL as the source of truth and use Redis only as a read cache -- a 15-second cache outage causes slow reads, not inventory loss. (3) Use `min-replicas-to-write 1` with a cross-region replica requiring acknowledgment before confirming a write -- eliminates the data loss window but adds 15ms write latency per operation.

Follow-up: Reducing cluster-node-timeout to 5 seconds means a 5-second GC pause (not a real failure) will trigger a false failover. Calculate the right timeout for a system where P99 GC pause is 2.5 seconds and typical network partition duration is 8 seconds. What is the minimum timeout that avoids false positives from GC pauses while still detecting real partitions before they cause excessive data loss?

---

**Question 37 -- Ch32 + Ch36: Cache Invalidation Across Multi-Region Redis Deployments**

Your application runs in 3 regions, each with its own Redis cluster. When a product price changes, the pricing service (running in US-East) must invalidate cached prices in all 3 regional Redis clusters. Design the invalidation system and quantify the staleness window for each approach.

- Approach 1 -- synchronous cross-region DEL: pricing service sends DEL to all 3 regions before returning success. Latency added: US-East to EU-West ~100ms + US-East to AP-South ~180ms = ~280ms added to every price change. Unacceptable for a user-facing API. Risk: if AP-South Redis is temporarily unavailable, the entire price change fails or leaves a stale cache indefinitely with no retry.
- Approach 2 -- async invalidation via event bus: pricing service writes the price and publishes `price.changed` to a Kafka topic. Each region has a local consumer group that executes DEL on its local Redis on receipt. Pricing service returns success in <10ms. Invalidation propagates to all regions within ~500ms (typical cross-region Kafka consumer lag). Staleness window: up to 500ms.
- Approach 3 -- layered TTL as a safety net: even if the invalidation consumer crashes, cached prices refresh when TTL expires. Set product TTL = 5 minutes. Normal case (invalidation works): <500ms staleness. Worst case (invalidation system down): 5 minutes staleness. A Staff engineer presents the layered approach (event bus + TTL) as defense-in-depth. Neither mechanism alone is sufficient; combined, they bound staleness even under failure.

Follow-up: Your Kafka invalidation consumer processes `price.changed` in EU-West and DELetes the EU-West Redis key. 200ms later, a cache read re-populates the key with the new price. A second price change arrives, its invalidation DELetes the key, and the next read fetches the correct (second) price. This is safe. Now model the race where the re-cache of the OLD price happens AFTER the DEL for the second invalidation. How do you prevent stale data from being written back to the cache after the invalidation has already run?

---

**Question 38 -- Ch32 + Ch37: GDPR Deletion -- Finding All Redis Keys for a User**

A GDPR right-to-erasure request arrives. The user's data is in Redis across 3 namespaces: `session:`, `cart:`, `recommendation:`. None of these keys contain the user ID directly -- they use opaque tokens as identifiers. Design the deletion strategy, ensure completeness, and address the cross-slot atomicity problem in Redis Cluster.

- The core problem: SCAN with a user ID pattern cannot find the user's keys because the user ID is not in the key name. You cannot query Redis by value. The only solution is a reverse index maintained at key creation time.
- Reverse index design: for each user, maintain a Redis SET `user:42:keys`. When creating `session:f3a9b2c1d4e5` for user 42, run a Lua script that atomically executes SADD user:42:keys session:f3a9b2c1d4e5 AND SET session:f3a9b2c1d4e5 {data}. On GDPR deletion: SMEMBERS user:42:keys returns all 14 keys, DEL each, then DEL user:42:keys. The reverse index must also be stored in PostgreSQL as the authoritative source -- if Redis is flushed and rebuilt, the PostgreSQL copy is used to reconstruct the deletion.
- Cross-slot atomicity: `user:42:keys` and `session:f3a9b2c1d4e5` almost certainly hash to different slots in Redis Cluster. A Lua script referencing both fails with CROSSSLOT. Fix: use hash tags. Designate a convention: all keys for user 42 include `{u42}`. Keys become `{u42}:session:f3a9b2c1d4e5`, `{u42}:cart:abc123`, `{u42}:keys`. All hash to the same slot. Lua scripts work. Trade-off: all of user 42's data is pinned to one Redis node.

Follow-up: The hash tag approach creates hot spots for enterprise power users. User 1 (a SaaS admin) has 500,000 active sessions. All their data lands on one Redis Cluster node, saturating its memory and CPU. Design a sharding strategy that enables GDPR deletion enumeration without concentrating all of one user's data on a single node.

---

**Question 39 -- Ch32 + Ch38: Memory Fragmentation Cost Analysis**

Your Redis cluster costs $8,000/month (cache.r6g.2xlarge x 6 nodes, 64GB RAM each). You observe `redis_mem_fragmentation_ratio = 1.35` on all nodes. Calculate the wasted memory, translate it to monthly cost, and evaluate four remediation options with their trade-offs.

- Fragmentation calculation: fragmentation_ratio = used_memory_rss / used_memory. A ratio of 1.35 means the OS allocated 35% more memory than Redis claims to use for data. Total OS-allocated: 6 x 64GB = 384GB. Total Redis data memory: 384GB / 1.35 = 284GB. Wasted (fragmented, unusable): 100GB (26% of total). Dollar cost: $8,000/month x (100GB / 384GB) = approximately $2,083/month in wasted spend. Equivalently: you could defer a cluster expansion by several months if you eliminated fragmentation.
- Remediation option 1 -- MEMORY PURGE: one-time jemalloc defragmentation pass. Brief CPU spike (5-10 seconds). No data risk. Safe to run during off-peak. Fragmentation creeps back over time. Option 2 -- activedefrag yes: continuous background defragmentation at low intensity. Keeps fragmentation below 1.10 with <5% CPU overhead. Best long-term option for stable systems. Option 3 -- rolling restart: restart nodes one at a time (via Cluster replica promotion or Sentinel failover). Each fresh instance starts at ratio 1.0. Most impactful but most disruptive: 5-10 minutes per node. Option 4 -- value size normalization: if workload has highly variable value sizes (1KB then 500B then 10KB in the same slot), switching to uniform serialization reduces allocator churn long-term.

Follow-up: You enable activedefrag. Over 48 hours, fragmentation drops from 1.35 to 1.08, freeing 25GB across the cluster. Your dataset grows at 4GB/month. The freed 25GB buys roughly 6 months before hitting the memory ceiling. Your architecture review asks: is this a one-time savings or ongoing? Explain how activedefrag maintains low fragmentation going forward, and describe the conditions under which it stops being effective (hint: extremely high write throughput with large, variable-size values).

---

**Question 40 -- Ch32 + Ch38: Redis Encoding Types and Memory Optimization at Scale**

You cache 10 million user preference objects in Redis as JSON strings. Average JSON size: 800 bytes. Total memory for this key type: ~9GB. Your infrastructure budget is constrained. Show how Redis internal encoding types can reduce this to under 3.5GB without changing application behavior.

- Current storage breakdown: 800 bytes of JSON data + 32 bytes Redis object header + ~64 bytes hash table overhead = approximately 896 bytes per key-value pair. At 10 million entries: 8.96GB.
- Hash encoding optimization: split the JSON into a Redis Hash using HSET user:pref:42 field1 val1 field2 val2 ... If the hash has fewer than 128 fields (hash-max-listpack-entries) AND all field values are under 64 bytes (hash-max-listpack-value), Redis uses listpack encoding internally. Listpack stores all entries in a single contiguous memory block with no per-entry pointer overhead and no hash table. A 20-field preference hash in listpack uses approximately 300-400 bytes versus 896 bytes as a JSON string -- a 55-65% reduction. Verify encoding with OBJECT ENCODING user:pref:42; you want to see "listpack". If it returns "hashtable", the thresholds have been exceeded and the savings are lost.
- Risk of encoding promotion: adding any new field over 64 bytes causes listpack-to-hashtable conversion for that key. The conversion is irreversible (Redis does not downgrade) until the key is deleted and rewritten. Make it a code review requirement that new field additions are checked against encoding thresholds before deployment, with a monitoring alert if the listpack percentage in production drops below 95%.

Follow-up: After the optimization, memory drops from 9GB to 3.2GB. Three months later, you add `custom_theme_css` (up to 2KB for some users). 20% of 10 million users set a custom theme. Those 2 million hashes convert from listpack (~350 bytes) to hashtable (~1,100 bytes). Calculate the net memory increase from this one field, and design a hybrid encoding strategy: store the 20 small fields in a listpack hash, store `custom_theme_css` separately as a standalone string key only for users who have set it. Show the key naming convention and the read/write code path for both cases.

---

*End of Supplemental Brainstorming -- Chapter 32.*

---

## Exercises

**Exercise 1 — Data structure selection.** Choose the right Redis data structure for each use case: (a) top 10 leaderboard (update score, get rank), (b) session storage (get/set by token, TTL 30 min), (c) rate limiting (count requests per user per second), (d) pub/sub for real-time notifications, (e) unique visitor count per day (approximate OK). Justify each with the specific command(s) you'd use.

**Exercise 2 — Memory optimization.** You have a Redis instance with 10M keys. Average key size: 50 bytes. Average value (JSON string): 200 bytes. Total: ~2.5GB. You learn that 90% of keys are small user metadata (5 fields). Design the hash encoding optimization: convert individual string keys to hash fields. Calculate memory before and after.

**Exercise 3 — Replication lag analysis.** Your Redis primary handles 100K writes/second. Replication to secondaries runs async. At 10ms average replication lag, how many operations can a secondary be behind? What's the maximum data loss on a primary failure? How does this change your application's consistency strategy?

**Exercise 4 — Redis Cluster routing.** You have a Redis Cluster with 3 primary shards. Key distribution uses CRC16. You need to store a user session and their shopping cart together (to avoid cross-shard operations). Design the key naming convention using hash tags. What's the trade-off?

**Exercise 5 — Eviction policy selection.** Your Redis instance is at 90% memory capacity. Choose the eviction policy for each workload: (a) session storage (all sessions are equally important), (b) cache layer (recently accessed data is most valuable), (c) rate limiting counters (all counters equally important, but expired keys are useless). Justify each policy choice.

**Exercise 6 — Lua script atomicity.** You need to implement a rate limiter: check if count exceeds limit, if not increment and set TTL. Why can't you do this with separate GET/INCR/EXPIRE commands? Write the Lua script. What does Redis guarantee about Lua script execution?

---

## Homework

**Assignment 1 — Redis memory audit.** Run `redis-cli INFO memory` and `redis-cli --bigkeys` on a production Redis instance. Identify the top memory consumers by key pattern. For any key pattern using >10% of total memory: is the encoding efficient? What optimization would you apply?

**Assignment 2 — Read the Redis documentation on data structures.** Focus on the internal encoding section: when does a list use ziplist vs. linkedlist? When does a hash use ziplist vs. hashtable? Write a one-paragraph summary of how these encoding thresholds affect memory usage for your workloads.

**Assignment 3 — Interview practice: Redis design.** Practice "design a distributed rate limiter using Redis" in 15 minutes. Cover: data structure choice, key naming, TTL strategy, what happens if Redis is unavailable, and how you handle a Redis cluster resharding event while rate limiters are active.

**Assignment 4 — Implement a Redis-backed feature.** Choose a feature your team could add that would benefit from Redis (leaderboard, cache, rate limiter, distributed lock). Implement it with production-quality error handling: what happens when Redis is slow, when it's unavailable, when the connection pool is exhausted?
