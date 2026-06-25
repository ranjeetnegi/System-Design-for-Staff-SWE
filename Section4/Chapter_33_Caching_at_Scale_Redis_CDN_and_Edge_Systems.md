# Chapter 31 — Part A: Caching at Scale
### Redis, CDN, and Edge Systems — Fundamentals, Hierarchy, and the Four Read/Write Patterns

> "There are only two hard things in Computer Science: cache invalidation and naming things."
> — Phil Karlton, 1996. Still true thirty years later.

---

## Table of Contents

1. What Is a Cache? (From Zero)
2. The Staff Engineer Framing
3. The Cache Hierarchy: From Nanoseconds to Seconds
4. Cache Hit and Miss — The Math Every Engineer Knows
5. The Four Cache Read Patterns
6. The Four Cache Write Invalidation Strategies
7. Cache Eviction Policies: When the Cache Is Full
8. Choosing Between Redis and Memcached

---

## 1. What Is a Cache? (From Zero)

### Start with a library

Imagine a university library with 200,000 books spread across five floors and twelve rooms. You need to find a copy of *Operating Systems: Three Easy Pieces*. Without any help, you walk the floors, scan shelf labels, and read spines until you find it. That might take 20 minutes.

Now imagine the library has a card catalogue — a set of small drawers near the entrance, each drawer holding index cards. Every book in the library has an index card that says: *"Operating Systems: Three Easy Pieces — Floor 3, Room B, Shelf 14."* You walk to the catalogue, pull the right card in 30 seconds, then walk straight to that exact shelf. Total time: 3 minutes instead of 20.

The card catalogue is a cache.

It is not the books themselves. It is a smaller, faster-to-search copy of the information you need most often (location) so you can skip the slow full search. The catalogue trades away some accuracy risk (what if a book was moved and the card not updated?) in exchange for dramatically faster access.

**This trade-off — speed versus freshness — is the core tension in every caching decision you will ever make.**

### Formal definition

A **cache** is a copy of data stored in a location that is faster to access than the original source.

That is the whole definition. Everything else — Redis, CDN, TTLs, eviction — is engineering machinery built around that one idea.

The original source (the database, the API, the disk) is called the **origin** or the **backing store**. The cache sits between the caller and the origin, intercepting requests and answering them quickly when it can.

```
  Caller
    |
    |  "Give me user 42's profile"
    v
 +----------+
 |  Cache   |  <-- fast, small, may be stale
 +----------+
    |  (if not in cache)
    v
 +----------+
 |  Origin  |  <-- slow, large, always correct
 | (DB/API) |
 +----------+
```

### The three properties that make data cache-worthy

Not every piece of data deserves to live in a cache. Before you cache anything, ask whether it has all three of these properties:

**Property 1 — Expensive to compute or fetch.**
If fetching the data takes 50ms from a database, caching makes sense. If the data is already in RAM and takes 0.1ms to produce, caching adds overhead, not savings. A cache is only beneficial if the speedup from a cache hit outweighs the complexity of managing the cache.

**Property 2 — Read more often than it changes.**
A user's profile photo URL might be read 10,000 times a day and changed once a month. That is an excellent cache candidate — you get 10,000 fast reads and only one invalidation event. But if a stock price changes every 50 milliseconds and is read 60 times per second, you need to think very carefully about how stale is acceptable.

**Property 3 — Tolerable to be slightly stale.**
This is the one engineers skip and then regret. A cache copy may not reflect the very latest state of the origin. If your system cannot tolerate any stale reads — for example, a bank account balance during a transaction — caching becomes dangerous without strong guarantees. If a 30-second-old profile picture is fine — and for most products it is — then cache away.

When all three properties are true, caching is a straightforward win. When one or more properties are missing, you are taking on real risk.

---

## 2. The Staff Engineer Framing

### How seniority changes the conversation

When a system is slow, different engineers reach different conclusions:

**Junior engineer:** "Things are slow. Add Redis. Fixed."
This is not wrong — sometimes it literally is this simple. But it skips the questions that determine whether the fix is safe.

**Senior engineer:** "Cache invalidation is hard. We need a strategy for keeping the cache consistent with the database."
Better. Now correctness is on the table alongside performance.

**Staff engineer:** "Caching is a reliability strategy that happens to improve performance. We need to understand the failure modes before we introduce this dependency."

The staff engineer sees the cache not just as a speed optimization but as a new component in a distributed system — one that can fail, go empty, become stale, or cause a cascade of load when it misbehaves. The performance improvement is real, but so are the new failure modes.

### The five questions BEFORE adding any cache

Every time someone proposes adding a cache to a system design, a staff engineer asks these five questions. If you cannot answer all five, you are not ready to cache yet.

```
 +----------------------------------------------------------+
 |         THE 5 QUESTIONS BEFORE YOU CACHE                |
 +----------------------------------------------------------+
 |                                                          |
 |  1. COLD START: What happens when the cache is EMPTY?   |
 |     (First deploy, cache restart — who absorbs the load?)|
 |                                                          |
 |  2. FAILURE MODE: What if the cache goes DOWN?          |
 |     (Does your database suddenly get 100x the traffic?) |
 |                                                          |
 |  3. STALENESS: How old can the data be?                 |
 |     (30 seconds? 5 minutes? Real-time only?)            |
 |                                                          |
 |  4. INVALIDATION: How does stale data get removed?      |
 |     (TTL? Explicit delete? Write-through?)              |
 |                                                          |
 |  5. COST: Is the operational complexity worth it?        |
 |     (Another system to deploy, monitor, and debug)      |
 |                                                          |
 +----------------------------------------------------------+
```

Let's make each of these concrete.

**Question 1 — Cold start.** When you deploy a new Redis instance, it starts completely empty. Every request will miss the cache and hit the database — all at once. If your system normally handles 100K QPS because 99% are served from cache, a cold start sends 100K QPS straight to a database that is sized for 1K QPS. This is called a **thundering herd** or **cache stampede**. You need a warm-up strategy: pre-populate the cache, use circuit breakers to limit database traffic, or gradually shift load.

**Question 2 — Cache failure.** Redis crashes. The network between your application servers and Redis becomes partitioned. What happens? If your code is `cache.get() → if miss: db.get()`, then failing Redis simply makes everything slower but still correct — every request falls through to the database. But if the database is not sized for that traffic, you have turned a cache failure into a database outage. The cache that was supposed to protect the database is now the thing that kills it.

**Question 3 — Staleness tolerance.** "How stale is acceptable?" is a product and business question, not just a technical one. For a news article's view count, 60-second staleness is perfectly fine. For an e-commerce product's inventory ("3 left in stock"), 60-second staleness might oversell. Know your tolerance before you set your TTL.

**Question 4 — Invalidation.** How does the cache find out that the origin data changed? This is the hard part — the part that gave cache invalidation its reputation. TTL is the simplest answer. Explicit event-driven invalidation is more precise but more complex. We will cover all four strategies in Section 6.

**Question 5 — Operational cost.** A cache is another system you have to deploy, monitor, alert on, scale, and debug. At a startup with two engineers, adding Redis for a modest performance gain might not be worth the operational overhead. At Google scale, the same decision is obvious. Be honest about where you are.

---

## 3. The Cache Hierarchy: From Nanoseconds to Seconds

### Multiple layers of cache already exist in your computer

Before you even write a single line of application code, your hardware and operating system have already built several layers of caching for you. Understanding this hierarchy explains why software caches are placed where they are.

Think of it like a city's information infrastructure. The CEO of a company (your CPU) has a personal assistant (L1 cache) with notes on the 10 things they deal with every hour. When those notes don't have the answer, they call the department secretary (L2 cache), who has records on the last few weeks of work. When that fails, they go to the filing room on the same floor (L3 cache). If nothing there, they send a runner to the main archive in the basement (RAM). If the archive doesn't have it, they call an outside vendor (the network / disk / Redis).

Each layer is bigger but slower than the one before it.

```
          CACHE HIERARCHY — SPEED vs CAPACITY
          (smaller = faster, larger = slower)

        +---------------------------------+
        |   L1 Cache  (0.5ns, ~32 KB)    |  <- CPU itself
        +---------------------------------+
                      | miss
        +---------------------------------+
        |   L2 Cache  (7ns,  ~256 KB)    |  <- CPU chip
        +---------------------------------+
                      | miss
        +---------------------------------+
        |   L3 Cache  (30ns, ~8 MB)      |  <- Shared on CPU die
        +---------------------------------+
                      | miss
        +---------------------------------+
        |   RAM / In-Process Cache       |  <- You can use this
        |   (100ns,  16-64 GB)           |     (JVM heap, local dict)
        +---------------------------------+
                      | miss
        +---------------------------------+
        |   Local SSD (100,000ns / 0.1ms)|  <- OS page cache lives here
        +---------------------------------+
                      | miss
        +---------------------------------+
        |   Redis / Memcached            |  <- You design this
        |   (500,000ns / 0.5-1ms)        |     (distributed cache)
        +---------------------------------+
                      | miss
        +---------------------------------+
        |   CDN PoP (5-20ms)             |  <- You configure this
        |   (nearest edge server)        |     (Cloudflare, Akamai)
        +---------------------------------+
                      | miss
        +---------------------------------+
        |   Origin Database / API        |  <- Authoritative truth
        |   (10-100ms same datacenter)   |
        +---------------------------------+
                      | miss
        +---------------------------------+
        |   Cross-continent origin       |  <- Worst case
        |   (250-500ms)                  |
        +---------------------------------+
```

### Latency numbers every staff engineer knows cold

These numbers are a famous piece of systems knowledge, originally from Jeff Dean at Google. You should be able to recite the order-of-magnitude for each:

| Layer | Latency | Size | Who controls it |
|---|---|---|---|
| L1 CPU cache | 0.5 ns | 32 KB | Hardware (automatic) |
| L2 CPU cache | 7 ns | 256 KB | Hardware (automatic) |
| L3 CPU cache | 30 ns | 8 MB | Hardware (automatic) |
| RAM / in-process | 100 ns | 16–64 GB | You (application code) |
| Local SSD read | 100,000 ns (0.1 ms) | TBs | OS (transparent) |
| Redis same datacenter | 500,000 ns (0.5–1 ms) | GBs–TBs | You (cache server) |
| CDN PoP (edge) | 5–20 ms | TBs | You (CDN config) |
| Origin server same DC | 10–100 ms | Unlimited | Database |
| Cross-continent origin | 250–500 ms | Unlimited | Physics |

### Why every miss is expensive

The critical insight from this table: every time data is not found at one layer, the request falls through to the next layer, which is typically **10x to 1,000x slower**.

- L1 miss → L2: 14x slower
- L3 miss → RAM: 3x slower
- RAM miss → SSD: 1,000x slower
- Redis miss → Database: 20–200x slower
- CDN miss → Origin: 10–20x slower

A system designer's job is to choose what data lives at which layer, and to engineer what happens when a miss occurs at each layer. Most of the hard problems in system design — thundering herds, cache stampedes, hot spots, cold starts — are miss-path problems. The hit path is easy. The miss path is where systems fall over.

---

## 4. Cache Hit and Miss — The Math Every Engineer Knows

### The two outcomes of a cache lookup

When your application asks the cache for a piece of data, exactly one of two things happens:

**Cache hit:** The data is in the cache. The cache returns it immediately. Latency: ~1ms for Redis.

**Cache miss:** The data is not in the cache. The application must go to the origin (the database or upstream API). Latency: ~50ms for a typical database query. After fetching, the data is usually written into the cache for future requests.

### Hit rate: the single most important cache metric

**Hit rate** = (number of cache hits) / (total requests) × 100%

If your cache receives 1,000,000 requests and 980,000 are hits, your hit rate is 98%.

Hit rate is the most important cache metric because it directly determines how much load reaches your database. And the relationship is not linear — small changes in hit rate create large changes in database load.

### The impact of hit rate at 100,000 QPS

Let's make this concrete. Your system gets 100,000 requests per second total. Your database can comfortably handle 5,000 requests per second. Here is what different hit rates mean:

| Hit Rate | Requests/sec to DB | DB Status |
|---|---|---|
| 99% | 1,000 | Comfortable (20% of capacity) |
| 95% | 5,000 | At the limit |
| 90% | 10,000 | 2x overload — incidents likely |
| 80% | 20,000 | 4x overload — crisis |
| 50% | 50,000 | 10x overload — catastrophic failure |

Read that table carefully. The difference between a 99% hit rate and a 95% hit rate is not 4%. It is the difference between "comfortable" and "database is at its limit." A 4% drop in hit rate can take you from healthy to outage.

This means: **a 1% improvement in hit rate saves 1,000 QPS at the database (at 100K total).** At Google-scale (millions of QPS), improving hit rate by 0.1% can eliminate the need for multiple database servers.

### The miss penalty

When a cache miss happens, the application must fetch from origin. That extra round-trip is the **miss penalty**.

If cache latency is 1ms and database latency is 50ms, the miss penalty is 49ms. The user who hit a miss waits 50ms instead of 1ms.

The **average latency** across all requests is:

```
avg_latency = (hit_rate × cache_latency) + (miss_rate × origin_latency)
```

Plugging in numbers at 99% hit rate with 1ms cache and 50ms database:

```
avg_latency = (0.99 × 1ms) + (0.01 × 50ms)
            = 0.99ms + 0.50ms
            = 1.49ms
```

At 95% hit rate:

```
avg_latency = (0.95 × 1ms) + (0.05 × 50ms)
            = 0.95ms + 2.50ms
            = 3.45ms
```

At 80% hit rate:

```
avg_latency = (0.80 × 1ms) + (0.20 × 50ms)
            = 0.80ms + 10ms
            = 10.8ms
```

The average latency jumped from 1.49ms to 10.8ms as hit rate fell from 99% to 80%. Users feel this. P99 latency gets much worse than the averages suggest.

---

## 5. The Four Cache Read Patterns

When data is requested, the cache and application can interact in four distinct ways. Each pattern has different trade-offs for simplicity, performance, and failure handling. Knowing all four — and when to use each — is a staff-level expectation.

---

### Pattern 1: Cache-Aside (Lazy Loading)

**Cache-aside** is the most common caching pattern in the real world. The application code is responsible for managing the cache directly: it checks the cache first, handles misses by fetching from the database, and populates the cache itself.

The cache sits "aside" from the main data flow — the application reaches out to it explicitly rather than the cache being in the mandatory path.

#### The two paths through Cache-Aside:

**Hit path:**
```
  Application
      |
      |  cache.get("user:42")
      v
  +---------+
  |  Cache  |  --> HIT --> returns value --> Application
  +---------+
```

**Miss path:**
```
  Application
      |
      |  cache.get("user:42")
      v
  +---------+
  |  Cache  |  --> MISS
  +---------+
      |
      |  db.query("SELECT * FROM users WHERE id=42")
      v
  +---------+
  | Database|  --> returns row
  +---------+
      |
      | cache.set("user:42", row, ttl=3600)
      v
  +---------+
  |  Cache  |  <-- now stored for next time
  +---------+
      |
      v
  Application  <-- receives value (slow this time, fast next time)
```

#### Pseudocode:

```python
def get_user(user_id):
    cache_key = f"user:{user_id}"

    # Step 1: Check the cache
    cached_value = cache.get(cache_key)
    if cached_value is not None:
        return cached_value          # Fast path: cache hit

    # Step 2: Cache miss — fetch from database
    user = db.query("SELECT * FROM users WHERE id = ?", user_id)

    # Step 3: Populate the cache for next time
    cache.set(cache_key, user, ttl=3600)   # expire in 1 hour

    return user                      # Slow path: miss
```

#### Pros:
- **Only caches what is actually requested.** You never waste memory storing data that no one reads. If user 1,000,000 is never looked up, their data never enters the cache.
- **Resilient to cache failure.** If Redis goes down, the application still works — it just falls back to the database every time. Slower, but not broken.
- **Easy to understand and debug.** The caching logic is visible in the application code.

#### Cons:
- **The first request after a miss is slow.** This is unavoidable — someone always has to pay the miss penalty. If the cache is empty (cold start), every user's first request is slow.
- **Thundering herd risk on popular items.** Suppose a popular item's cache entry expires. One hundred requests arrive simultaneously, all miss the cache, all query the database at the same time. You've just sent 100 queries where normally 1 per hour would go. This is the **thundering herd** problem.

Cache-aside is the right default for most cases. It's what you get when you write `if not in cache: fetch from DB and store`.

---

### Pattern 2: Read-Through

In **read-through** caching, the application always talks to the cache, and the cache itself is responsible for fetching from the database on a miss. The application never talks to the database directly.

Think of the cache as a smart proxy: when it doesn't have an answer, it goes and gets one, stores it, and returns it — all transparently from the application's perspective.

```
  Application
      |
      |  cache.get("user:42")
      v
  +------------------+
  |  Cache           |
  |                  |  HIT --> returns value to Application
  |  (on miss):      |
  |  db.fetch("42")  |  <-- cache fetches internally
  |  stores result   |
  |  returns result  |
  +------------------+
      |  (if MISS, cache goes here internally)
      v
  +---------+
  | Database|
  +---------+
```

From the application's view, there is no miss handling code. It always calls `cache.get()` and always gets an answer (eventually).

#### Pros:
- **Application code is simpler.** No miss-handling logic in the application. The cache layer handles everything.
- **Consistent data loading logic.** All fetching from the database is in one place (the cache's loader), not scattered across multiple service code paths.

#### Cons:
- **The first user still pays the miss penalty.** The cache still has to go to the database on a miss — read-through doesn't eliminate the miss latency, it just moves the fetch logic.
- **The cache becomes a required dependency.** Unlike cache-aside (where a failed cache just means slower performance), a read-through cache that fails means the application cannot get data at all. You've introduced a harder dependency.
- **Harder to implement.** You need a cache that supports configurable "loaders" — functions it can call when a key is missing. Not all caching systems support this natively.

**Real examples:** Guava Cache in Java (with a `CacheLoader`), Caffeine with a loader function, or a reverse proxy like Nginx configured to fetch from an origin on cache miss.

---

### Pattern 3: Write-Through

The first two patterns were about reads. Now let's talk about writes. **Write-through** is a write pattern: every time the application writes new data, it writes to both the cache and the database at the same time, as a single operation.

The application does not write to the database alone. It writes to cache + database together. The cache is always kept up-to-date with every write.

```
  Application
      |
      |  user.name = "Alice"
      |  save(user)
      v
  +----------------------------------+
  |  Write-Through Cache Layer       |
  |                                  |
  |  1. cache.set("user:42", user)   |
  |  2. db.update(user)              |
  |                                  |
  |  Return success only after BOTH  |
  |  succeed                         |
  +----------------------------------+
       |               |
       v               v
   +---------+   +---------+
   |  Cache  |   | Database|
   +---------+   +---------+
   (updated)     (updated)
```

#### Pros:
- **The cache is always fresh.** Because every write goes to both places, there is no window where the cache holds stale data from a recent update. Reads after writes are always correct.
- **No cache invalidation needed for write events.** You do not need a separate invalidation strategy — the write itself keeps the cache current.

#### Cons:
- **Every write is slower.** Write latency = max(cache write time, database write time). Since the database write is usually slower (disk I/O, replication), every write now waits for both. You've traded write speed for read freshness.
- **You cache data that may never be read.** Every write populates the cache, whether or not that data will ever be read. If you write 1,000 user records and only 10 are ever read, 990 cache slots are wasted.

Write-through is a natural companion to read-through: read-through handles miss fetching, write-through handles keeping the cache current on updates.

---

### Pattern 4: Write-Behind (Write-Back)

**Write-behind** (also called **write-back**) is the most aggressive write optimization. The application writes to the cache immediately and gets back a success response — and then the cache asynchronously flushes those writes to the database in the background, later.

From the application's perspective, writes feel instantaneous. From the database's perspective, writes arrive delayed and potentially batched.

```
  Application
      |
      |  save(user)
      v
  +---------+
  |  Cache  |  <-- write succeeds immediately
  +---------+
      |
      |  (marks entry as "dirty" — needs DB sync)
      |
      |  ... (background worker runs every few seconds) ...
      |
      v
  +---------+
  | Database|  <-- updated asynchronously, maybe batched
  +---------+
```

The cache tracks which entries have been modified but not yet written to the database. These are called **dirty entries**. A background process (sometimes called a "write-back worker" or "flush process") periodically reads the dirty entries and writes them to the database.

```
  Cache Memory:
  +--------------------+--------+
  | Key       | Value  | Dirty? |
  +--------------------+--------+
  | user:42   | Alice  |  YES   |  <-- not yet in DB
  | user:99   | Bob    |  NO    |  <-- already synced
  | product:7 | $19.99 |  YES   |  <-- not yet in DB
  +--------------------+--------+
               |
               | background flush every 5 seconds
               v
          +---------+
          | Database|
          +---------+
```

#### Pros:
- **Write latency = cache latency only (~0.1ms).** The application is not waiting for the database at all on writes. This is a massive improvement for write-heavy workloads.
- **Natural write batching and burst absorption.** If 1,000 writes arrive in one second, the background process can batch them into a single database transaction instead of 1,000 individual queries. Huge efficiency gain.

#### Cons:
- **Data loss if the cache crashes.** If Redis crashes between the application's write and the background flush to the database, those dirty entries are gone. You've lost data that the application thought was successfully saved. For financial systems, this is unacceptable.
- **Ordering complexity.** If 10 writes to the same key arrive quickly, the flush process must apply them in the right order. Out-of-order writes can corrupt data.
- **More complex to implement correctly.** You need crash recovery logic, ordering guarantees, and observability into the dirty-entry queue.

**Real use cases:** Database buffer pools (InnoDB's buffer pool is essentially write-behind — writes go to memory, get flushed to disk later). High-throughput gaming leaderboards where losing a few score updates in a crash is acceptable.

#### The four patterns at a glance:

```
 PATTERN         | Who handles miss? | Write goes to?    | Complexity
 ----------------+-----------------+--------------------+-----------
 Cache-Aside     | Application      | DB only (cache    | Low
                 |                  | updated on read)  |
 Read-Through    | Cache itself     | DB only           | Medium
 Write-Through   | Cache itself     | Cache + DB        | Medium
 Write-Behind    | Cache itself     | Cache (DB later)  | High
```

---

## 6. The Four Cache Write Invalidation Strategies

Putting data in the cache is the easy part. The hard part is knowing when that data is no longer valid — and getting rid of it before a caller gets a wrong answer. This is cache invalidation, and it has a deserved reputation for being one of the most nuanced problems in distributed systems.

Here are the four strategies you need to know.

---

### Strategy 1: TTL (Time To Live)

**TTL** is the simplest invalidation strategy. Every entry in the cache is given an expiration time when it is stored. When that time passes, the entry is treated as if it doesn't exist — the next access is a miss.

**Analogy:** milk in your fridge has an expiration date printed on the carton. When that date passes, you throw it out and buy fresh milk. You don't check the dairy farm to see if the cows produced something new. You just go by the date.

```
  cache.set("user:42", user_data, ttl=3600)
                                   ^^^
                              expires in 3600 seconds (1 hour)

  -- 1 hour later --

  cache.get("user:42")
  --> MISS (TTL expired, treated as if key doesn't exist)
  --> Application fetches from DB, repopulates cache
```

#### Choosing TTL values

The right TTL depends on how often data changes and how stale is acceptable:

| Data Type | Typical TTL | Reasoning |
|---|---|---|
| Static HTML pages | 24 hours | Changes rarely |
| User profile data | 1 hour | Changes occasionally |
| Product prices | 5 minutes | Could change frequently |
| Shopping cart | 30 minutes | User-specific, active session |
| Session tokens | 15–30 minutes | Security-sensitive |
| Stock prices | 10–30 seconds | Changes constantly |
| Real-time scores | No cache | Must be live |

#### The TTL stampede problem

Here is a subtle failure mode that trips up many engineers. Suppose your application starts up and caches 10,000 user records, all with a TTL of 3,600 seconds. You set all 10,000 at time T=0. At time T=3,600, all 10,000 entries expire simultaneously. Every request in that second gets a cache miss. All 10,000 go to the database at the same moment. The database, which normally handles a trickle of misses, suddenly gets a flood.

This is the **TTL stampede** (also called the **thundering herd from expiry**).

**Fix: add random jitter to TTL.** Instead of `ttl = 3600`, use:

```python
import random

base_ttl = 3600
jitter = random.randint(0, int(base_ttl * 0.3))   # ±30%
ttl = base_ttl + jitter
# result: each key expires somewhere between 3600 and 4680 seconds
# expirations spread out over 1,080 seconds instead of happening simultaneously
```

Now expirations spread across an 18-minute window. The database sees a steady trickle of misses instead of a spike.

---

### Strategy 2: Explicit Invalidation (Event-Driven)

Instead of waiting for a TTL to expire, the application **explicitly deletes or updates the cache entry** the moment the underlying data changes.

```
  User updates their profile name:

  1. db.update("UPDATE users SET name='Bob' WHERE id=42")
  2. cache.delete("user:42")          <-- explicit invalidation
  
  Next read:
  cache.get("user:42") --> MISS (deleted)
  --> Fetches fresh data from DB
  --> Repopulates cache with correct data
```

**Pros:** The cache is exactly correct immediately after the update. There is no window where stale data is served.

**Cons:** Every write path must include the cache invalidation call. This is easy when one service owns the data. It gets hard when multiple services can modify the same data.

#### The distributed invalidation problem

Suppose five different services can all update a user's data:
- The profile service (name, photo)
- The preferences service (settings)
- The payment service (billing address)
- The admin service (account status)
- The identity service (email, password)

All five must call `cache.delete("user:42")` when they make a change. If any one of them forgets — or is deployed by a different team that doesn't know about the cache — the cache will silently serve stale data.

This is not hypothetical. It is one of the most common sources of cache-related bugs in large organizations. The solution is usually an event bus (Kafka, Pub/Sub) where any service publishes a "user 42 updated" event, and a dedicated cache-invalidation consumer subscribes and deletes the key. This centralizes the invalidation logic rather than scattering it across every service that writes.

---

### Strategy 3: Cache-Aside with Versioned Keys

Instead of deleting a key, you change the key itself on every update. Old entries are not explicitly invalidated — they simply become unreachable because no one asks for them anymore.

```
  Version table in DB: user_42_version = 5

  Cache key: "user:42:v5"    <-- current
  Old keys:  "user:42:v1" through "user:42:v4"  <-- abandoned

  When user 42 updates their profile:
  1. db.update(...)
  2. db.update version: user_42_version = 6
  3. No cache deletion needed

  Next read:
  1. Fetch version from DB: v = 6
  2. cache.get("user:42:v6") --> MISS (new key, never stored)
  3. Fetch from DB, store as "user:42:v6"
  4. Old key "user:42:v5" stays in cache until evicted
```

**Pros:** No race condition between "delete" and "write." Old entries simply age out via TTL or eviction.

**Cons:** Old versions consume memory until evicted. Requires an extra DB lookup to get the current version number on every read (which partially defeats the purpose of caching). Works best for immutable or append-only data.

---

### Strategy 4: Write-Through Invalidation (Cache Updated on Every Write)

As covered in Pattern 3: write-through ensures the cache is always up-to-date because every write goes to the cache simultaneously. There is no separate invalidation step — the write IS the invalidation, because it replaces the old value with the new one.

This is invalidation by replacement rather than deletion.

```
  User updates profile:
  
  write_through_cache.set("user:42", new_user_data)
  db.update(new_user_data)
  
  -- no separate delete/invalidate step needed --
  -- cache already has the fresh value --
```

This is the simplest correctness story for invalidation, at the cost of slower writes and potential memory waste (covered in Pattern 3).

---

## 7. Cache Eviction Policies: When the Cache Is Full

### The fundamental problem

A cache has a fixed amount of memory. It cannot grow forever. When it is full and a new entry needs to be stored, something already in the cache must be removed to make room. The **eviction policy** is the rule that decides what gets removed.

This is a resource allocation problem under uncertainty: you don't know which cached items will be requested next. You have to make your best guess about which currently-cached items are least likely to be needed, and remove those.

**Analogy:** Your desk has space for 10 folders. You have 15 folders you use to various degrees. When your desk is full and you need to add an 11th folder, which one do you put back in the filing cabinet? The one you haven't touched in months? The one you only opened once a year ago? The random one? Different answers give different eviction policies.

---

### The six eviction policies

**LRU — Least Recently Used**

Remove the item that was accessed the longest time ago. The logic: if you haven't needed something recently, you probably won't need it soon.

```
  Cache state (most recent access on left):
  [user:1, user:5, user:9, user:3, user:7]
   (newest)                          (oldest)

  New entry needs to fit: store user:42
  Evict: user:7  (oldest access time)

  Result: [user:42, user:1, user:5, user:9, user:3]
```

LRU is the default for most caches (Redis, Memcached, most in-process caches) because it performs well across a wide variety of real access patterns. Most real workloads have **temporal locality** — recently accessed data is likely to be accessed again soon.

**LFU — Least Frequently Used**

Remove the item accessed the fewest total times. The logic: if something has been accessed only once over a long period, it is probably not important to keep around.

LFU is better than LRU when your hot items stay hot for a long time. Consider a popular product page that gets 10,000 hits per day. LRU keeps it in cache if it was accessed recently. LFU keeps it in cache because it has been accessed 10,000 times. Under a large sequential scan (which temporarily makes many items look "recently accessed"), LFU correctly identifies the truly popular items.

**FIFO — First In, First Out**

Remove the item that was inserted into the cache first, regardless of how often it has been accessed. Simple to implement, but ignores usage patterns entirely.

**Random**

Remove a randomly selected item. Surprisingly, random eviction performs comparably to LRU in many workloads, at much lower implementation complexity. It is used in some embedded systems where the overhead of tracking access order is unacceptable.

**TTL-based**

Remove the item closest to its expiration time. This is a variant — you are proactively evicting items that will expire soon anyway.

**Redis-specific: allkeys-lru vs volatile-lru**

Redis gives you a useful distinction: `allkeys-lru` applies LRU eviction to every key in the cache, while `volatile-lru` applies LRU eviction only to keys that have a TTL set. This matters because in Redis it is common to store some keys without a TTL (permanent data) and some with a TTL (expiring data). `volatile-lru` protects your permanent keys from eviction.

---

### Eviction policy comparison

| Policy | When to use | Weakness |
|---|---|---|
| LRU | Default — works for most workloads | Fails under sequential scans (scan evicts all hot keys) |
| LFU | Long-lived hot items (product pages, config) | Slow to respond to new hot items (needs time to accumulate count) |
| FIFO | Very simple workloads, embedded systems | Ignores whether items are popular |
| Random | When LRU overhead is too high | No access-pattern awareness |
| TTL-based | When expiry-awareness matters | Ignores access patterns |
| volatile-lru (Redis) | Mixed TTL/permanent key workloads | Only evicts TTL-set keys |

### When LRU fails: the sequential scan problem

There is one important case where LRU gives you the wrong answer. Suppose your cache happily holds your 10,000 most popular product pages. Then a batch analytics job runs that reads every product in your catalogue — 500,000 products — sequentially. Each of those 500,000 products gets cached briefly as the job reads them. But since the cache is full, LRU evicts items to make room for each new one.

After the batch job completes, your cache is full of 10,000 obscure products that the batch job happened to read last. Your 10,000 popular products are gone. Cache hit rate crashes. Database gets slammed with the popular product traffic.

LRU was betrayed by the scan. It thought all the recently-accessed items (the scan items) were important — but "recently accessed" was not a signal for popularity here.

**Fix options:** Use LFU instead (popular products have high frequency, scan items have frequency 1). Or use SCAN-resistant LRU variants like ARC (Adaptive Replacement Cache), which maintains separate lists for "recently used" and "frequently used" items.

---

## 8. Choosing Between Redis and Memcached

Both Redis and Memcached are distributed in-memory caches that have been production-proven at enormous scale. Twitter, Facebook, Pinterest, GitHub, and thousands of other companies run one or both. The question of which to choose comes up in almost every system design interview that touches caching.

The short answer: **use Redis unless you have a specific reason not to.** Redis is strictly more capable, and for the vast majority of use cases the performance difference is negligible. But understanding why Memcached still exists — and when it wins — shows depth.

---

### Comparison across ten dimensions

| Dimension | Redis | Memcached |
|---|---|---|
| **Data structures** | Strings, hashes, lists, sets, sorted sets, streams, bitmaps, HyperLogLog | Strings only |
| **Persistence** | Yes — RDB snapshots and AOF log. Survives restarts. | No — cache is entirely in-memory, lost on restart |
| **Clustering / HA** | Redis Cluster (native sharding) + Redis Sentinel (failover) | Client-side sharding only — no built-in clustering |
| **Pub/Sub messaging** | Yes — built-in publish/subscribe channels | No |
| **Lua scripting** | Yes — atomic server-side scripts | No |
| **Max value size** | 512 MB per value | 1 MB per value |
| **Threading model** | Single-threaded command processing (multi-threaded I/O since v6) | Fully multi-threaded |
| **Memory efficiency for simple strings** | Slightly less efficient (richer metadata per key) | Slightly more efficient for pure string workload |
| **Atomic operations** | Yes — INCR, DECR, SETNX, sorted set operations | Basic CAS only |
| **Operational maturity** | Excellent — rich monitoring, Redis Insight, wide cloud support | Excellent — simpler system, less operational surface area |

---

### When Memcached wins

Memcached has one meaningful advantage over Redis: its fully multi-threaded architecture can squeeze more throughput out of a single machine for pure get/set workloads.

If you are running at a scale where a single Redis node is becoming a bottleneck (think 100K+ QPS of simple string get/set from a single node) and you need to extract maximum throughput from one machine rather than scaling horizontally, Memcached's threading model can help.

Facebook, for example, still runs Memcached at massive scale for exactly this reason — they have optimized their infrastructure around its threading model over many years.

For every other use case, Redis wins. It does everything Memcached does plus vastly more.

---

### When Redis is obviously the right answer

- You need sorted sets for leaderboards
- You need pub/sub for real-time notifications
- You need data to survive cache restarts (partial persistence)
- You need Lua scripts for atomic multi-step operations
- You need native cluster failover without client-side sharding logic
- You need to store values larger than 1 MB
- You need rate limiting (atomic INCR + expire)
- You are not operating at scales where single-node threading is the bottleneck

**The default recommendation:** Redis, for new systems at any reasonable scale. Memcached is a valid choice only if you are operating at the rare scale where its threading model provides a measurable advantage and you are willing to forgo Redis's richer features.

---

### Redis as more than a cache

One important nuance for staff-level interviews: Redis is frequently used for things that are not caching at all.

- **Rate limiting:** `INCR user:42:request_count` and check the result atomically
- **Distributed locks:** `SET lock:resource UNIQUE_ID NX EX 30` (set only if not exists, expire in 30 seconds)
- **Session storage:** User session data stored as hashes
- **Leaderboards:** Sorted sets with scores updated on every game event
- **Message queues:** Redis Streams as a lightweight Kafka substitute
- **Pub/Sub notifications:** Real-time events pushed to subscribers

When you recommend Redis in an interview, you are not just recommending a cache — you may be recommending an entire category of infrastructure. Make sure you are clear about what role it is playing.

---

## Summary: Key Takeaways from Part A

Before we move to Part B (Redis internals, CDN configuration, and edge caching), here are the ideas from this chapter that you should be able to explain in an interview without notes.

**On fundamentals:**
- A cache is a faster copy of data. The trade-off is speed versus freshness.
- Data is cache-worthy if it is expensive to fetch, read more than it changes, and tolerable to be slightly stale.

**On the staff engineer mindset:**
- Ask the five questions before adding any cache: cold start, failure mode, staleness tolerance, invalidation strategy, operational cost.
- A cache is a reliability decision, not just a performance decision.

**On the hierarchy:**
- Cache misses cascade down the hierarchy. Every level is 10–1,000x slower than the one above.
- Your job as a designer: decide what lives where, and engineer the miss path carefully.

**On hit rate math:**
- At 100K QPS, a 1% improvement in hit rate saves 1,000 QPS to the database.
- Average latency = (hit_rate × cache_latency) + (miss_rate × origin_latency).
- Small drops in hit rate cause disproportionately large database load increases.

**On read patterns:**
- Cache-aside: application manages the cache. Most common. Resilient but requires miss handling.
- Read-through: cache fetches on miss. Simpler application code. Cache is a hard dependency.
- Write-through: every write goes to cache + DB. Always fresh. Slower writes.
- Write-behind: write to cache, flush to DB asynchronously. Fastest writes. Risk of data loss.

**On invalidation:**
- TTL: simplest. Add jitter to avoid stampedes.
- Explicit deletion: precise but requires all write paths to cooperate.
- Versioned keys: no deletion needed, old versions waste memory.
- Write-through: invalidation by replacement.

**On eviction:**
- LRU is the correct default. LFU is better for long-lived popularity. Watch out for sequential scans defeating LRU.
- Redis: use `allkeys-lru` for pure cache workloads, `volatile-lru` when you mix TTL and permanent keys.

**On Redis vs Memcached:**
- Use Redis by default. It has data structures, persistence, native clustering, pub/sub, and scripting.
- Memcached wins only at very high QPS on simple get/set from a single node, where multi-threading matters.

---

*Part B continues with: Redis data structures in depth, Redis Cluster and Sentinel, CDN architecture, edge caching patterns, cache warming strategies, and the thundering herd problem and its solutions.*
# Chapter 31: Caching at Scale — Redis, CDN, and Edge Systems
## Part B: Redis Internals, Data Structures, Persistence, and High Availability

---

## 1. Inside Redis: How It Actually Works

Before you can use Redis well in a system design interview, you need to understand what Redis actually is under the hood. Most people treat it as a magic fast key-value store. The reality is more interesting — and knowing the internals will help you avoid critical mistakes.

### The Single-Threaded Event Loop

Redis processes commands using a single-threaded event loop. This means Redis handles exactly one command at a time, from start to finish, before moving on to the next one.

Here is what happens when a client sends a command:

```
Client A  ──\
Client B  ───┼──► [ Network Queue ] ──► [ Event Loop ] ──► [ Execute Command ] ──► [ Send Response ]
Client C  ──/          (waiting)           (one at a time)       (one at a time)
```

The event loop picks up one request from the queue, executes it completely in memory, sends the response, then picks up the next request. While it is processing Client A's command, Clients B and C are waiting in line.

### Why Single-Threaded Is Actually Fast

Your first reaction might be: that sounds slow. It is not. Here is why.

The bottleneck for most programs is not CPU — it is locks, context switching, and waiting. When you have multiple threads sharing data, they have to lock shared resources so they do not corrupt each other. Threads fight over those locks. The OS constantly pauses threads and switches between them (context switching). All of this overhead adds up.

Redis avoids all of that. Because there is exactly one thread executing commands, there is no shared mutable state, no locks, no context switching between competing threads. The single thread runs hot in the CPU cache, processes data, and moves on.

A good analogy: imagine a cashier at a store. One very fast cashier processing customers one by one is often faster than ten slow cashiers fighting over a shared cash register, yelling at each other, waiting for the other person to finish, and constantly bumping into each other.

For Redis, most operations complete in microseconds because everything lives in memory. The bottleneck is network I/O, not computation. A single thread can handle 100,000+ operations per second on a single core.

### Redis 6+ I/O Threading

Redis 6 added multi-threaded networking I/O. The distinction matters:

- **Network I/O** (reading bytes off the socket, writing bytes back): now multi-threaded
- **Command execution** (actually running GET, SET, ZADD): still single-threaded

This means Redis 6+ can handle more concurrent connections and higher network throughput, but the core execution model has not changed. Commands still execute one at a time.

### The Critical Implication: Slow Commands Block Everything

Because command execution is single-threaded, any slow command blocks every other client waiting in the queue.

The classic example is `KEYS *`. This command scans every key in the database and returns them all. If you have 10 million keys, this takes hundreds of milliseconds. During that entire time, every other client is frozen — no gets, no sets, nothing.

**Never run KEYS * in production.** Use SCAN instead:

```
SCAN 0 MATCH user:* COUNT 100
→ returns cursor + up to 100 matching keys

SCAN <cursor> MATCH user:* COUNT 100
→ continue from where you left off

...repeat until cursor returns 0 (full scan complete)
```

SCAN is a cursor-based iterator. Each call does a small amount of work and returns a cursor. You call it repeatedly, each time doing a little scanning, and you never block the server for long.

Similarly, `SMEMBERS` on a set with 1 million members returns all 1 million at once — slow. `LRANGE list 0 -1` on a huge list returns everything — slow. Be careful with any command whose runtime scales with the size of the data.

### Memory Model

Every value Redis stores lives in RAM as an object in a global hash table. The key is a string, the value is a Redis object (which can be a string, list, hash, set, sorted set, etc.). When you call GET, Redis looks up the key in the hash table and returns the value from memory. No disk involved unless persistence is configured.

---

## 2. Redis Data Structures — Deep Dive with Real Use Cases

Redis is not just a key-value store where values are strings. It gives you seven distinct data structure types, each optimized for different problems. Choosing the right one is the difference between an elegant solution and a memory disaster.

---

### 2.1 String — The Basic Building Block

A Redis String stores any binary-safe value up to 512MB. "Binary-safe" means it can hold raw bytes, JSON, serialized objects, integers — anything.

**Under the hood: SDS (Simple Dynamic String)**

Redis does not use C's built-in null-terminated strings. It uses its own string type called SDS. SDS stores the string length explicitly in a header, rather than scanning for a null byte. This makes `STRLEN` O(1) instead of O(n), and lets strings contain null bytes (useful for binary data).

```
SDS Header:
[ len: 5 ][ alloc: 8 ][ flags: 1 ][ buf: "hello\0" ]
              ^-- allocated space                ^-- actual bytes
```

**Core commands:**

```
SET key value                   -- store a value
GET key                         -- retrieve it
SETEX key 3600 value            -- store with 3600 second TTL
SET key value EX 3600           -- same, modern syntax
SETNX key value                 -- set only if key does not exist (set if not exists)
INCR key                        -- atomically increment integer value by 1
INCRBY key 5                    -- atomically increment by 5
DECR key                        -- atomically decrement by 1
```

**Use case 1: Session tokens**

```
SET session:abc123 '{"user_id":456,"role":"admin"}' EX 3600
GET session:abc123
→ '{"user_id":456,"role":"admin"}'
```

The TTL (EX 3600) means this session expires in one hour automatically. No cleanup job needed.

**Use case 2: Atomic counters**

```
INCR page:views:homepage
→ 1
INCR page:views:homepage
→ 2
INCR page:views:homepage
→ 3
```

INCR is atomic. Even if 10,000 clients call INCR simultaneously (one at a time due to single threading), each increment is exact. No race conditions. No two clients get the same value.

**Use case 3: Rate limiting with INCR + EXPIRE**

```
-- First request in this minute window:
INCR rate:user:123:minute:2024-01-15:14:30     → 1
EXPIRE rate:user:123:minute:2024-01-15:14:30 60

-- Subsequent requests:
INCR rate:user:123:minute:2024-01-15:14:30     → 2
INCR rate:user:123:minute:2024-01-15:14:30     → 3
...
INCR rate:user:123:minute:2024-01-15:14:30     → 101

-- Application logic: if result > 100, reject the request
-- After 60 seconds, key expires, counter resets automatically
```

The key encodes the user ID and the time window. Each minute gets its own key. After 60 seconds, the key expires and the counter resets naturally.

---

### 2.2 Hash — Like a Dictionary Inside a Key

A Redis Hash maps field names to values within a single key. Think of it as a Python dict or a JavaScript object stored under one Redis key.

**Core commands:**

```
HSET user:123 name "Alice" email "alice@example.com" plan "pro" login_count 47
HGET user:123 email          → "alice@example.com"
HMGET user:123 name plan     → ["Alice", "pro"]
HGETALL user:123             → all fields and values
HDEL user:123 plan           → delete the plan field
HINCRBY user:123 login_count 1   → 48 (atomic increment on a hash field)
HEXISTS user:123 email       → 1 (exists) or 0 (does not exist)
```

**Why not just store the whole user as a JSON string?**

If you store user data as a JSON string:
```
SET user:123 '{"name":"Alice","email":"alice@example.com","login_count":47}'
```

To increment `login_count`, you must:
1. GET the whole JSON string
2. Deserialize it in your application
3. Increment the field
4. Serialize it back to JSON
5. SET the whole thing back

That is five steps, involves your application, and has a race condition window between GET and SET.

With a Hash:
```
HINCRBY user:123 login_count 1
```

One command. Atomic. No race condition.

**Memory efficiency**

Redis uses a compact encoding called ziplist for hashes with fewer than 128 fields where each value is under 64 bytes. Ziplist stores everything in a contiguous block of memory with no pointers — very memory-efficient.

A rule of thumb: storing 100 user fields as separate string keys (user:123:name, user:123:email, ...) uses roughly 10 times more memory than one hash with 100 fields. For a system with millions of users, that difference matters enormously.

---

### 2.3 List — Ordered Queue or Stack

A Redis List is an ordered sequence of strings. You can push and pop from either end. For small lists Redis uses ziplist internally; for large lists it switches to a doubly-linked list.

**Core commands:**

```
RPUSH queue:emails job1 job2 job3   -- push to right end
LPUSH history:session1 action3       -- push to left end
LPOP queue:emails                    -- pop from left (FIFO with RPUSH + LPOP)
RPOP queue:emails                    -- pop from right (LIFO with RPUSH + RPOP)
LRANGE feed:user:123 0 9            -- get first 10 items (0-indexed)
LLEN feed:user:123                  -- length of list
LTRIM feed:user:123 0 999           -- keep only items 0-999, discard the rest
BLPOP queue:emails 0                -- blocking pop: wait forever until item available
```

**Use case 1: Simple job queue**

Producer:
```
RPUSH queue:emails '{"to":"user@example.com","template":"welcome"}'
```

Consumer:
```
BLPOP queue:emails 0    -- blocks until a job appears
→ ["queue:emails", '{"to":"user@example.com","template":"welcome"}']
```

`BLPOP` with timeout 0 means "wait forever." The consumer sleeps at the OS level until Redis wakes it up when something is pushed. No polling needed.

**Use case 2: Activity feed (last N items)**

```
LPUSH feed:user:123 '{"type":"like","post_id":789}'
LTRIM feed:user:123 0 999   -- keep only the 1000 most recent
```

After each push, LTRIM trims the list back to 1000 items. The feed never grows beyond 1000 entries. Cheap to maintain.

**Use case 3: Undo history**

```
LPUSH history:session:abc action_A    -- push action onto stack
LPUSH history:session:abc action_B
LPOP history:session:abc             → action_B   -- undo most recent
LPOP history:session:abc             → action_A
```

LPUSH + LPOP gives you a LIFO stack — natural for undo.

---

### 2.4 Set — Unique Members, No Order

A Redis Set is an unordered collection of unique strings. Adding the same value twice has no effect. Redis uses a hash table internally for O(1) add, remove, and membership checks.

**Core commands:**

```
SADD friends:alice bob charlie dave
SREM friends:alice dave              -- remove dave
SISMEMBER friends:alice bob         → 1 (is bob in alice's friends? yes)
SCARD friends:alice                 → 2 (how many friends?)
SMEMBERS friends:alice              → {bob, charlie}   -- all members (dangerous on large sets)
SUNION friends:alice friends:bob    -- all friends of alice OR bob
SINTER friends:alice friends:bob    -- mutual friends (intersection)
SDIFF friends:alice friends:bob     -- friends of alice but NOT bob
```

**Use case 1: Tracking unique visitors**

```
SADD visitors:homepage:2024-01-15 user:123
SADD visitors:homepage:2024-01-15 user:456
SADD visitors:homepage:2024-01-15 user:123   -- duplicate, ignored
SCARD visitors:homepage:2024-01-15           → 2
```

**Warning on memory:** This works for small pages. If your homepage gets 1 million unique visitors per day, the set holds 1 million members. At roughly 50 bytes per member, that is 50MB just for one day's unique visitor count. For approximate counts at massive scale, use HyperLogLog (covered next).

**Use case 2: Mutual friends**

```
SADD friends:alice bob charlie dave frank
SADD friends:bob alice charlie eve

SINTER friends:alice friends:bob    → {charlie}
```

One command, O(min(set sizes)) time.

**Use case 3: Tag-based lookups**

```
SADD tag:redis article:123 article:456 article:789
SADD tag:databases article:123 article:101

SINTER tag:redis tag:databases      → {article:123}   -- articles tagged both redis AND databases
```

---

### 2.5 Sorted Set (ZSet) — Ordered by Score

A Sorted Set is like a Set, but every member has a floating-point score. Redis keeps members ordered by score at all times. Internally it uses a skip list combined with a hash table — the skip list maintains order, the hash table gives O(1) lookup by member.

```
Skip list structure (simplified):
Level 3: -------- alice:9850 --------------------------------- frank:9100
Level 2: -------- alice:9850 ------------ charlie:9500 ------- frank:9100
Level 1: bob:9200 alice:9850 dave:9300    charlie:9500 eve:8900 frank:9100
```

**Core commands:**

```
ZADD leaderboard 9850 alice
ZADD leaderboard 9200 bob
ZADD leaderboard 9500 charlie

ZREVRANGE leaderboard 0 9 WITHSCORES    -- top 10, highest score first
→ [alice, 9850, charlie, 9500, bob, 9200]

ZRANK leaderboard bob                   -- rank (0-indexed, lowest score = rank 0)
→ 0  (bob has lowest score, rank 0 from bottom)

ZREVRANK leaderboard bob                -- rank from top
→ 2  (bob is 3rd from top)

ZINCRBY leaderboard 300 bob             -- increase bob's score by 300
→ 9500 (new score)

ZRANGEBYSCORE leaderboard 9000 9999    -- everyone with score between 9000-9999
ZCARD leaderboard                       -- total number of members
```

**Use case 1: Game leaderboard**

```
-- Player finishes a game:
ZINCRBY leaderboard <points_earned> <player_id>

-- Fetch top 10 for display:
ZREVRANGE leaderboard 0 9 WITHSCORES

-- Fetch a specific player's rank:
ZREVRANK leaderboard <player_id>
```

Updates and rank queries are O(log n). For a leaderboard with 10 million players, that is about 23 operations — fast.

**Use case 2: Sliding window rate limiting**

```
-- Each request: add to sorted set with score = current timestamp (milliseconds)
ZADD rate:user:123 1705312230000 req_uuid_abc
ZADD rate:user:123 1705312231500 req_uuid_def

-- Remove entries older than 60 seconds:
ZREMRANGEBYSCORE rate:user:123 0 1705312170000   -- (now_ms - 60000)

-- Count remaining entries = requests in last 60 seconds:
ZCARD rate:user:123
→ 2

-- If count > 100: reject
```

This is a true sliding window, unlike the INCR approach which uses fixed time buckets.

**Use case 3: Scheduled job queue**

```
-- Schedule a job for the future (score = unix timestamp when job should run):
ZADD job_queue 1705312800 '{"job":"send_report","user_id":456}'

-- Worker loop: fetch jobs due now or earlier:
ZPOPMIN job_queue     -- atomically pop the member with lowest score

-- Or fetch without removing, check if score <= now:
ZRANGEBYSCORE job_queue 0 <now_unix> LIMIT 0 10
```

The sorted set naturally keeps jobs ordered by their scheduled time. The worker always processes the next due job without sorting.

---

### 2.6 HyperLogLog — Count Unique Things at Scale

HyperLogLog is a probabilistic data structure. It does not store the actual items — it estimates how many unique items have been added. The estimate has at most 0.81% error, and the data structure uses only 12KB of memory regardless of how many items you have added.

**The memory problem it solves:**

If you want to count exactly how many unique users visited a page today:
- Exact tracking with a Set: store each user ID as a member. With 1 billion unique users, each ID is ~8 bytes → 8GB of memory for one page, one day.
- With HyperLogLog: always 12KB, with 0.81% error (±8.1 million users at 1 billion scale).

For analytics and reporting, 0.81% error is usually fine.

**Commands:**

```
PFADD visitors:homepage:2024-01-15 user:123 user:456 user:789
→ 1 (structure was modified)

PFADD visitors:homepage:2024-01-15 user:123
→ 0 (no change, user:123 already counted)

PFCOUNT visitors:homepage:2024-01-15
→ 3

-- Merge multiple HyperLogLogs into one:
PFMERGE visitors:homepage:2024-01-15 visitors:homepage:2024-01-14 visitors:homepage:2024-01-13
PFCOUNT visitors:homepage:2024-01-15
→ approximate unique visitors over 3 days combined
```

**When to use at L6:**

Any time a system needs approximate unique counts at scale — unique page views, daily active users for analytics dashboards, A/B test reach counts — HyperLogLog is the answer. If an interviewer asks "how do you track 1 billion unique visitors per day without running out of memory," this is the answer. Never store one entry per user in a Set for aggregate analytics.

---

### 2.7 Streams — Kafka-Lite for Redis

A Redis Stream is an append-only log of messages. Each message has a unique auto-generated ID (timestamp-sequence, e.g. `1705312230000-0`) and a set of key-value fields.

```
XADD events * action "purchase" user_id 123 amount 49.99
XREAD COUNT 10 STREAMS events 0          -- read from the beginning
XREADGROUP GROUP my_group worker1 COUNT 10 STREAMS events >  -- consumer group
XACK events my_group 1705312230000-0     -- acknowledge processed message
```

Consumer groups let multiple workers split a stream's messages between them — each message goes to exactly one worker, analogous to a Kafka consumer group.

**When to use:** Ordered, replayable event queues within a single system where Kafka is overkill — audit logs, activity events, lightweight pub/sub. If you need multi-datacenter replication or multi-terabyte retention, use Kafka.

---

## 3. Redis Persistence: When the Server Restarts

### The Problem

Redis stores everything in memory. If the server process crashes, loses power, or is restarted for maintenance, all data is gone. For some use cases this is fine. For others it is catastrophic.

```
Which category does your data fall into?

Cache (TTL-based, reconstructable from DB) ──► Loss OK, no persistence needed
Session store (users re-login if lost)      ──► Loss acceptable
Rate limit counters                         ──► Loss OK (resets, slightly unfair)
Shopping cart (no other record)             ──► Loss BAD — use persistence
Leaderboard (sole source of truth)          ──► Loss BAD — use persistence
Primary data store                          ──► Loss CATASTROPHIC — use both RDB + AOF
```

Redis gives you two persistence mechanisms. You can use one, both, or neither.

---

### RDB — Redis Database Backup (Snapshots)

RDB takes a complete point-in-time snapshot of all data and writes it to a binary file on disk (dump.rdb by default).

**How it works:**

```
Redis Primary Process
        │
        │ fork()
        ├──────────────────► Child Process
        │                          │
        │ (continues serving       │ writes snapshot
        │  client requests)        │ to dump.rdb
        │                          │
        │ OS Copy-on-Write:        │
        │ Parent modifies page X   │
        │ → OS copies page X for   │
        │   child before writing   │
        │                          │
        │◄─────────────────────────┘
        │ (child exits, snapshot complete)
```

The key insight is `fork()`. The OS creates a child process that shares all memory with the parent. The child writes the snapshot; the parent keeps serving requests. When either the parent or child modifies a memory page, the OS creates a separate copy just for that process (copy-on-write). So the child sees a consistent point-in-time view of all data, even while the parent continues accepting writes.

**Configuration:**

```
# In redis.conf:
save 900 1         -- if at least 1 key changed in 900 seconds (15 min), save
save 300 10        -- if at least 10 keys changed in 300 seconds (5 min), save
save 60 10000      -- if at least 10,000 keys changed in 60 seconds, save
```

All three rules are applied: whichever triggers first causes a save.

**What you lose on crash:** All writes since the last snapshot. If your last snapshot was 14 minutes ago and the server crashes now, you lose 14 minutes of data.

**File characteristics:** Compressed binary format. Typically 30-50% of the in-memory data size. Loads quickly on restart — Redis just reads the file and loads objects into memory.

**Performance cost:** The `fork()` call itself is fast (milliseconds) even for large datasets, because it only copies the process's page table, not the actual memory. However, if the dataset is large and many pages are modified after forking (high write rate), copy-on-write creates many page copies, increasing memory usage temporarily. On a busy server with a 10GB dataset, you might need 12-15GB of RAM available to handle RDB saves safely.

---

### AOF — Append-Only File (Write Log)

AOF records every write command that changes data, in order, to a log file. On restart, Redis replays this log to reconstruct the full dataset.

Every write command that changes data is appended to a log file in order. On restart, Redis replays this log from the beginning to rebuild the full dataset. If the server crashed at command 50,000, Redis replays commands 1 through 49,999 and the state is restored.

**fsync modes — the durability vs performance tradeoff:**

```
┌─────────────┬──────────────────────────────┬──────────────┬────────────────────┐
│ Mode        │ When data is flushed to disk │ Performance  │ Max data loss      │
├─────────────┼──────────────────────────────┼──────────────┼────────────────────┤
│ always      │ After every command          │ Slowest      │ 0 commands         │
│ everysec    │ Once per second (background) │ Good         │ ~1 second of cmds  │
│ no          │ When OS decides (minutes)    │ Fastest      │ Up to minutes      │
└─────────────┴──────────────────────────────┴──────────────┴────────────────────┘
```

For most production systems, `everysec` is the right choice. You accept losing at most one second of writes in exchange for good performance.

**AOF rewrite — keeping the file small:**

If you INCR a counter one million times, the AOF contains one million lines saying `INCR counter`. But the actual state is just `SET counter 1000000`. AOF rewrite compacts the log by replacing the full history with the minimal set of commands needed to reproduce the current state.

```
Before rewrite:
INCR counter      (line 1)
INCR counter      (line 2)
...               (lines 3 through 999,999)
INCR counter      (line 1,000,000)

After rewrite:
SET counter 1000000   (one line)
```

Redis performs AOF rewrites automatically in the background using the same fork() mechanism as RDB.

---

### RDB vs AOF vs Both — Choosing the Right Option

```
┌────────────────────┬──────────────────┬──────────────────┬──────────────────┐
│ Property           │ RDB only         │ AOF only         │ RDB + AOF        │
├────────────────────┼──────────────────┼──────────────────┼──────────────────┤
│ Max data loss      │ Minutes          │ ~1 second        │ ~1 second        │
│ Restart time       │ Fast (load file) │ Slow (replay log)│ Fast (load RDB,  │
│                    │                  │                  │ apply recent AOF)│
│ File size          │ Small (compact)  │ Large (grows)    │ Both files       │
│ Perf impact        │ Low (periodic)   │ Low (everysec)   │ Slightly higher  │
│ Complexity         │ Simple           │ Moderate         │ Higher           │
└────────────────────┴──────────────────┴──────────────────┴──────────────────┘
```

**Recommendation by use case:**

- **Cache only (sessions, temp data, rate limits):** No persistence. If Redis restarts, it starts empty. Clients re-authenticate, counters reset. Fine.
- **Durable store (sole source of truth for data):** Use both RDB and AOF. On restart, Redis loads the RDB snapshot (fast), then replays only the AOF entries that happened after the snapshot (short, fast replay). Best of both.
- **Default for most production systems:** AOF with `everysec`. Lose at most 1 second of data, good performance, manageable complexity.

---

## 4. Redis High Availability: Sentinel and Cluster

### The Single-Instance Problem

Running one Redis instance is fine for development. In production, a single instance is a single point of failure.

```
Normal operation:
App Servers ──────► Redis (Primary) ──── database is warm, fast

Redis crashes:
App Servers ──────► Redis (DEAD)
                       │
                       ▼
           All requests fall through to:
App Servers ──────► Database (Postgres/MySQL)
                       │
           Database gets 100× normal traffic
                       │
           Database CPU spikes to 100%
                       │
           Database slows down → requests time out
                       │
           App servers pile up requests → OOM
                       │
           Cascading failure: entire system down
```

The cache layer absorbing traffic is what keeps the database alive. Lose the cache, lose the system.

---

### Redis Sentinel — High Availability for a Single Primary

Sentinel is Redis's built-in HA system. It handles automatic failover without you intervening manually at 3am.

**Typical setup:**

```
                    ┌────────────────────────────────────────────┐
                    │            Sentinel Processes              │
                    │  ┌──────────┐  ┌──────────┐  ┌─────────┐ │
                    │  │Sentinel 1│  │Sentinel 2│  │Sentinel3│ │
                    │  └────┬─────┘  └────┬─────┘  └────┬────┘ │
                    └───────┼─────────────┼──────────────┼──────┘
                            │  (monitoring)│              │
               ┌────────────▼─────────────▼──────────────▼──────┐
               │                                                  │
          ┌────▼─────┐               ┌────────────┐  ┌──────────┐
          │ Primary  │──replication─►│  Replica 1 │  │Replica 2 │
          │ (writes) │               │ (read only)│  │(read only│
          └──────────┘               └────────────┘  └──────────┘
```

**What Sentinel does, step by step:**

1. Each Sentinel pings the primary every second
2. If a Sentinel does not hear back from the primary for `down-after-milliseconds` (default 30 seconds), it marks the primary as "subjectively down"
3. Sentinel asks other Sentinels: "Do you also think the primary is down?"
4. If a quorum (majority) of Sentinels agree (e.g., 2 out of 3), the primary is marked "objectively down"
5. One Sentinel is elected leader to conduct the failover
6. That Sentinel picks the most up-to-date replica (least replication lag) and promotes it to primary
7. Other replicas are reconfigured to replicate from the new primary
8. Sentinel notifies all connected clients of the new primary address

**Why quorum? Preventing split-brain:**

If only one Sentinel could declare the primary down, a network partition could cause two nodes to each think they are the primary. With quorum, a majority must agree. In a network partition, only one side can have a majority — the other side stays read-only, preventing two primaries accepting conflicting writes.

**Replication and potential data loss:**

Redis replication is asynchronous. The primary writes data in memory and sends commands to replicas, but does not wait for acknowledgment before telling the client the write succeeded. Under load, replicas can lag 100 milliseconds to 5 seconds behind the primary.

```
Primary: write SET user:123 "alice"  ──► client: OK (write acknowledged)
         │
         │ (sends to replicas... but this takes time)
         │
         ▼
Replica: applies SET user:123 "alice" ... (100ms-5s later)

If primary crashes NOW:
- The write was acknowledged to the client
- The replica never received it
- Replica is promoted to primary
- SET user:123 "alice" is LOST
```

This is the cost of asynchronous replication: up to a few seconds of acknowledged writes can be lost on failover. For most caching use cases this is fine. For financial data or shopping carts as the sole data source, you need a different strategy (synchronous writes, or using Redis as cache with a durable database as the source of truth).

**Failover time:** Typically 10-30 seconds from failure detection to the new primary accepting writes. During this window, all writes fail.

**Client behavior:** Clients do not connect directly to the primary's IP. They connect to a Sentinel first, ask "who is the current primary?", get the address, then connect to that. On failover, clients reconnect to Sentinel and get the new primary address.

---

### Redis Cluster — HA Plus Horizontal Sharding

Sentinel gives you failover for one primary. Redis Cluster gives you failover AND distributes your data across multiple primaries, so you can exceed the memory limit of one machine.

**Topology:**

```
┌──────────────────────────────────────────────────────────────┐
│                      Redis Cluster                           │
│                                                              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐      │
│  │  Primary-1  │    │  Primary-2  │    │  Primary-3  │      │
│  │ Slots 0-5460│    │Slots 5461-  │    │Slots 10923- │      │
│  │             │    │   10922     │    │   16383     │      │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘      │
│         │                  │                  │              │
│  ┌──────▼──────┐    ┌──────▼──────┐    ┌──────▼──────┐      │
│  │  Replica-1  │    │  Replica-2  │    │  Replica-3  │      │
│  └─────────────┘    └─────────────┘    └─────────────┘      │
└──────────────────────────────────────────────────────────────┘
```

**Hash slots — how keys are distributed:**

The keyspace is divided into exactly 16,384 hash slots. Every key maps to exactly one slot:

```
slot = CRC16(key) mod 16384
```

Each primary in the cluster owns a contiguous range of slots. When a client sets a key, Redis computes the slot, figures out which primary owns that slot, and routes the request there.

```
SET user:123 "alice"
→ CRC16("user:123") mod 16384 = 5649
→ Primary-2 owns slots 5461-10922
→ request goes to Primary-2
```

**MOVED and ASK redirects:**

A client might send a request to the wrong node (especially after slots are migrated). The node responds with:
```
-MOVED 5649 192.168.1.2:6381
```
This tells the client: slot 5649 is at 192.168.1.2:6381 — send your request there. Cluster-aware clients update their slot map and retry automatically.

**Hash tags — colocating related keys:**

Multi-key operations (like `MGET key1 key2 key3`) fail in cluster mode if the keys are on different primaries. To force related keys onto the same primary, use hash tags: the part inside `{}` is used for the slot calculation instead of the full key.

```
{user:123}:profile  → CRC16("user:123") mod 16384 = slot X
{user:123}:sessions → CRC16("user:123") mod 16384 = slot X (same slot!)
{user:123}:cart     → CRC16("user:123") mod 16384 = slot X (same slot!)

Now you can MGET all three in one command — they all live on the same primary.
```

**Adding capacity (live resharding):**

To add a new primary, you:
1. Start a new Redis node and join it to the cluster
2. Move some hash slots from existing primaries to the new node
3. Keys in those slots automatically migrate

No downtime. During migration, clients transparently get ASK redirects for migrating slots.

**When to use Cluster vs Sentinel:**

```
┌─────────────────────────┬──────────────────────┬──────────────────────┐
│ Need                    │ Use Sentinel          │ Use Cluster          │
├─────────────────────────┼──────────────────────┼──────────────────────┤
│ Data fits in one node   │ Yes                  │ Overkill             │
│ Data > 25GB             │ No                   │ Yes                  │
│ Write throughput > 200K │ No                   │ Yes                  │
│ QPS                     │                      │                      │
│ Simple ops only         │ Yes                  │ Yes                  │
│ Cross-key transactions  │ Yes (all one primary)│ Only with hash tags  │
│ Operational complexity  │ Lower                │ Higher               │
└─────────────────────────┴──────────────────────┴──────────────────────┘
```

**Minimum cluster size:** 3 primaries + 3 replicas (6 nodes). Each primary needs a replica for failover. You cannot run cluster with fewer than 3 primaries.

---

### Replication Mechanics

Whether you use Sentinel or Cluster, replication works the same way at the node level.

**Initial sync (full resync):**

```
New Replica joins:
1. Replica sends PSYNC to Primary
2. Primary forks → generates RDB snapshot
3. Primary sends RDB file to Replica
4. Replica loads RDB (overwrites any existing data)
5. Primary streams all write commands that happened during RDB generation
6. Replica is now caught up — enters incremental replication mode
```

**Ongoing replication (incremental):**

```
Primary receives: SET user:456 "bob"
→ Executes in memory
→ Writes to replication buffer
→ Streams to all replicas: "SET user:456 bob\r\n"
→ Replicas execute the command on their copy
```

**Partial resync after brief disconnect:**

If a replica disconnects briefly and reconnects, Redis does not need to send a full RDB again. The primary keeps a circular replication backlog buffer (default 1MB). If the replica's last processed offset is still within the buffer, the primary sends only the missed commands.

```
Replica disconnects at offset 10000
Replica reconnects 3 seconds later
Primary's backlog: offsets 9000 to 11000 (still in buffer)
Primary sends: commands from offset 10001 onward
No full resync needed.
```

If the disconnect lasts long enough that the replica's offset falls out of the backlog, a full resync is required.

---

## 5. Key Design Patterns for Redis Keys

Good key design prevents subtle bugs, memory waste, and operational headaches.

**Naming convention: colon-separated namespaces**

```
Pattern:  <entity>:<id>:<field>
Examples:
  user:123:profile
  session:abc123
  rate:user:123:minute:2024-01-15:14:30
  leaderboard:game:chess:2024-01
  cache:api:v2:/products/featured
```

Colons are purely conventional — Redis treats keys as opaque strings — but consistent naming lets you reason about your key space and use SCAN patterns effectively.

**Bad naming (avoid):**

```
user123profile           -- no delimiters, unreadable
sess_abc123              -- inconsistent delimiter
u:123                    -- over-abbreviated, unclear
```

**Key size matters:**

Redis stores keys in its global hash table. Long keys consume more memory and take longer to compare. The theoretical maximum key size is 512MB — do not approach it.

```
Practical guidance:
Under 64 bytes:  ideal
64-256 bytes:    acceptable
Over 256 bytes:  reconsider your design
```

If you find yourself building very long keys by concatenating many fields, consider whether a hash would be more appropriate.

**Avoid key enumeration via SCAN unless necessary:**

Do not design systems that need to regularly list all keys matching a pattern. SCAN is O(n) over the full keyspace — on a database with 50 million keys, even a SCAN that matches few keys still iterates over many.

If you need to enumerate all keys of a type (e.g., all active sessions), maintain a separate Redis Set as an index:

```
-- When creating a session:
SET session:abc123 <data> EX 3600
SADD active_sessions session:abc123

-- When deleting a session:
DEL session:abc123
SREM active_sessions session:abc123

-- To list all active sessions:
SMEMBERS active_sessions   -- or SSCAN for large sets
```

---

## 6. Memory Optimization

Redis memory is expensive. On cloud providers, a 64GB Redis instance costs more than a 64GB database instance because Redis needs dedicated RAM — it cannot page to disk. Memory efficiency is not optional at scale.

**Rule 1: Use hashes for objects, not flat string keys**

```
-- Inefficient: one string key per field
SET user:123:name "Alice"
SET user:123:email "alice@example.com"
SET user:123:plan "pro"
SET user:123:login_count "47"
-- Each key has overhead: key name stored, hash table entry, object header
-- ~200 bytes overhead per key → 800 bytes for 4 fields

-- Efficient: one hash
HSET user:123 name "Alice" email "alice@example.com" plan "pro" login_count 47
-- All four fields in one hash → ~80 bytes total
-- ~10× more memory efficient
```

**Rule 2: Set TTLs on everything**

An unbounded cache grows until the server runs out of memory. When Redis hits its memory limit (configured with `maxmemory`), it either refuses new writes or evicts old keys depending on your `maxmemory-policy` setting.

```
maxmemory-policy options:
  noeviction      -- reject writes when full (safest, most explicit)
  allkeys-lru     -- evict least recently used keys from anywhere
  volatile-lru    -- evict LRU keys that have a TTL set
  allkeys-lfu     -- evict least frequently used keys (Redis 4+)
  volatile-ttl    -- evict keys with shortest remaining TTL first
```

Set TTLs even on data you expect to keep long-term. Use a very long TTL (30 days) rather than no TTL, so Redis has something to evict when memory is needed.

**Rule 3: Check actual encoding with OBJECT ENCODING**

Redis automatically uses compact encodings for small data structures. Knowing which encoding is active helps you understand memory usage:

```
OBJECT ENCODING user:123
→ "ziplist"    -- compact, contiguous memory, good

HSET user:123 field1 val1 ... field129 val129   -- add 129th field
OBJECT ENCODING user:123
→ "hashtable"  -- switched to full hash table (threshold is 128 fields by default)
```

When a data structure grows past Redis's internal thresholds, it upgrades to a more powerful (but less memory-efficient) encoding. You can tune these thresholds:

```
hash-max-ziplist-entries 128     -- max hash fields before switching from ziplist
hash-max-ziplist-value 64        -- max field value size before switching
zset-max-ziplist-entries 128
list-max-ziplist-size -2         -- max 8KB per ziplist node
```

If you know your hashes will always have fewer than 128 small fields, ziplist encoding saves significant memory.

**Rule 4: Right-size your data structures**

Sorted sets have the richest feature set but the highest overhead (skip list + hash table). Do not reach for ZADD when a plain list or hash will do. If you have five items and just need insertion order, use RPUSH. Use sorted sets only when you need score-based ordering or range-by-score queries.

**Rule 5: Monitor with INFO memory**

```
redis-cli INFO memory
→ used_memory_human: 4.52G
→ mem_fragmentation_ratio: 1.43
```

`mem_fragmentation_ratio` above 1.5 means Redis holds more memory from the OS than it actually uses — fragmentation wasting 50%+ of allocated RAM. Enable `activedefrag yes` in Redis 4+ to reclaim it online.

---

## Summary: Key Concepts for L6 Interviews

These topics come up as follow-up questions the moment you mention Redis in a design interview. Have the following ready:

| Topic | The one-line answer |
|---|---|
| Why is Redis fast? | Single-threaded, everything in RAM, no lock contention |
| What blocks Redis? | Any O(n) command on a large dataset: KEYS *, SMEMBERS, LRANGE |
| Strings vs Hashes | Use Hashes for objects — 10× memory savings, atomic field updates |
| Unique count at scale | HyperLogLog: 12KB memory, 0.81% error, vs GBs for an exact Set |
| Leaderboards | Sorted Set: ZADD, ZREVRANGE, ZRANK — O(log n) for all |
| Sliding rate limit | Sorted Set: score = timestamp, ZREMRANGEBYSCORE + ZCARD |
| Cache-only persistence | None — let it start empty on restart |
| Durable persistence | RDB + AOF: fast restart from snapshot + minimal data loss from log |
| Single-node HA | Sentinel: quorum-based failover, 10-30s downtime, async replication |
| Multi-node HA + scale | Cluster: 16,384 slots, MOVED redirects, hash tags for colocation |
| Replication safety | Asynchronous — up to seconds of acknowledged writes can be lost on failover |
| Memory discipline | TTL everything, hashes over flat keys, OBJECT ENCODING to check internals |
# Chapter 31: Caching at Scale — Redis, CDN, and Edge Systems
## Part C: CDN Internals, Edge Computing, Cache-Control Headers, and Invalidation Strategies

---

## 1. What is a CDN? (From First Principles)

Let's start with the problem that CDNs were invented to solve.

You built a web application. Your servers live in a data center in northern Virginia, USA. That's where your origin server sits — the machine that actually runs your application code and stores your content.

Now imagine your users:

- A user in **Tokyo, Japan** opens your website.
- A user in **Berlin, Germany** opens your website.
- A user in **São Paulo, Brazil** opens your website.
- A user in **Mumbai, India** opens your website.

Every single one of them is reaching across the ocean to a server in Virginia. The laws of physics are not optional. Light travels at roughly 200,000 km/s through fiber optic cables. The distance from Tokyo to Virginia is about 14,000 km. Round-trip (request goes there, response comes back) is 28,000 km. At the speed of light in fiber, that's about 140ms just for physics. Add routing overhead and you're at **150–200ms** of latency before your server even starts doing any work.

That 200ms adds to every page load, every image, every CSS file, every API call. For a page that loads 30 resources, even if they load in parallel, you're still paying that trans-Pacific tax repeatedly. Users in distant locations experience your site as slow even if your servers are blazing fast.

**The CDN solution:** Instead of making every user come all the way to Virginia, put copies of your content in data centers spread around the world. These distributed locations are called **Points of Presence**, or **PoPs** (pronounced "pops").

Now:
- The user in Tokyo fetches from a CDN PoP in Tokyo: **5ms** latency.
- The user in Berlin fetches from a CDN PoP in Frankfurt: **10ms** latency.
- The user in São Paulo fetches from a CDN PoP in São Paulo: **8ms** latency.
- The user in Mumbai fetches from a CDN PoP in Mumbai: **7ms** latency.

Each PoP holds a **cache** of your content. When the Tokyo PoP doesn't have a resource yet, it fetches it from your origin server in Virginia (paying the 200ms penalty once), stores a copy, and then serves all future Tokyo users from its local cache.

Here is what this looks like geographically:

```
                         ORIGIN SERVER
                         [Virginia, USA]
                              |
          +-------------------+-------------------+
          |                   |                   |
    [Frankfurt              [Virginia           [São Paulo
     CDN PoP]               CDN PoP]            CDN PoP]
     ~10ms to               ~5ms to             ~8ms to
     Berlin user            NYC user            SP user
          |                   |                   |
    Berlin User           New York User       São Paulo User


                    ALSO:

          [Tokyo CDN PoP] -----5ms----> Tokyo User
          [Mumbai CDN PoP] ----7ms----> Mumbai User
          [Sydney CDN PoP] ----6ms----> Sydney User


    WITHOUT CDN:
    Tokyo User ----150ms----> Virginia Origin ----150ms----> Tokyo User
    Total: 300ms round trip

    WITH CDN:
    Tokyo User ----5ms----> Tokyo PoP (cache hit) ----5ms----> Tokyo User
    Total: 10ms round trip

    Speed improvement: 30x faster
```

**How many PoPs do major CDNs have?**

| CDN Provider  | Number of PoPs (approx.) | Notes                              |
|---------------|--------------------------|-------------------------------------|
| Cloudflare    | 300+                     | Very dense in major cities          |
| AWS CloudFront| 450+                     | Includes AWS edge locations          |
| Fastly        | 80+                      | Fewer but high-capacity PoPs        |
| Akamai        | 4,000+                   | Oldest CDN, most distributed        |

More PoPs generally means users are physically closer to a PoP, which means lower latency. But PoP count alone does not tell the whole story — bandwidth capacity and peering agreements matter too.

**What exactly does a PoP store?**

A PoP is essentially a large caching server (or cluster of servers). It stores copies of responses it has fetched from the origin. These copies are stored according to rules the origin sets via HTTP response headers (which we will cover in depth in Section 3).

**How does a PoP know where your origin server is?**

The answer is DNS routing. When you set up a CDN, you point your domain's DNS to the CDN provider. When any user's browser looks up `example.com`, the CDN's DNS infrastructure looks at where that DNS query is coming from (specifically, the location of the user's DNS resolver) and returns the IP address of the nearest PoP. The browser then connects to that PoP — it has no idea it is not talking directly to your origin.

```
User in Tokyo types: example.com

1. Browser asks local DNS resolver: "What is the IP for example.com?"
2. DNS resolver asks Cloudflare's nameservers
3. Cloudflare nameserver sees DNS query comes from Tokyo area resolver
4. Cloudflare nameserver returns: IP of Tokyo PoP (e.g., 104.21.34.56)
5. Browser connects to 104.21.34.56 (Tokyo PoP), not Virginia origin
6. Tokyo PoP handles the request
```

This is called **anycast routing** in practice — the CDN advertises the same IP address from multiple locations, and the internet's routing infrastructure naturally directs traffic to the closest one.

---

## 2. How a CDN Request Works (Step by Step)

Understanding the exact sequence of events for both a cache miss and a cache hit is fundamental. Interviewers often ask you to trace through a request, and getting this right shows you understand the system deeply.

### First Request: Cache Miss

```
User in Tokyo requests: https://example.com/hero-image.jpg
(This image has never been requested from the Tokyo PoP before)

Step 1: DNS Lookup
  User's browser → DNS resolver → CDN nameserver
  CDN nameserver returns: Tokyo PoP IP address

Step 2: Request arrives at Tokyo PoP
  Browser → [TCP connection] → Tokyo PoP
  Browser sends: GET /hero-image.jpg HTTP/1.1

Step 3: Tokyo PoP checks its cache
  Cache lookup for: example.com/hero-image.jpg
  Result: MISS (not in cache)

Step 4: Origin Pull
  Tokyo PoP → [TCP connection across Pacific] → Virginia Origin
  PoP sends: GET /hero-image.jpg HTTP/1.1
  Round-trip time: ~200ms
  Origin responds: 200 OK, image bytes, Cache-Control: max-age=86400

Step 5: Tokyo PoP caches the response
  Stores: hero-image.jpg + response headers + timestamp
  TTL: 86,400 seconds (24 hours) from Cache-Control header

Step 6: Tokyo PoP responds to user
  PoP → User: 200 OK, image bytes
  Latency for this step: ~5ms (PoP is in Tokyo)

Total perceived latency for first user: ~205ms (200ms origin pull + 5ms PoP-to-user)
```

That first request is slow. But here is the important part: **every subsequent Tokyo user benefits.**

### Subsequent Requests: Cache Hit

```
A different user in Tokyo (or the same user again) requests the same image

Step 1: DNS Lookup
  Returns Tokyo PoP IP address (same as before)

Step 2: Request arrives at Tokyo PoP
  Browser → Tokyo PoP
  Browser sends: GET /hero-image.jpg HTTP/1.1

Step 3: Tokyo PoP checks its cache
  Cache lookup for: example.com/hero-image.jpg
  Result: HIT (cached, TTL has not expired)

Step 4: Tokyo PoP responds immediately
  PoP → User: 200 OK, image bytes (served from cache)
  Latency: ~5ms

Step 5: No origin contact at all.

Total perceived latency: ~5ms
```

Here is a combined flow diagram:

```
                    CACHE MISS FLOW
                    ---------------
[User in Tokyo]
      |
      | GET /hero-image.jpg
      v
[Tokyo CDN PoP] ---> Cache lookup: MISS
      |
      | Origin Pull (200ms round trip)
      v
[Virginia Origin] ---> Returns image + Cache-Control: max-age=86400
      |
      v
[Tokyo CDN PoP] ---> Stores in cache
      |
      | Returns image to user (~5ms)
      v
[User in Tokyo] <--- Receives image (total ~205ms)


                    CACHE HIT FLOW
                    --------------
[User in Tokyo]
      |
      | GET /hero-image.jpg
      v
[Tokyo CDN PoP] ---> Cache lookup: HIT
      |
      | Returns image from cache (~5ms)
      v
[User in Tokyo] <--- Receives image (total ~5ms)

    No origin contact. Origin never knows this request happened.
```

One nuance worth knowing: different CDN PoPs do NOT share caches with each other. The Tokyo PoP cache is separate from the Frankfurt PoP cache. If a resource is popular globally, each PoP independently builds its own cached copy by doing its own origin pull the first time a user in that region requests it. After that, each PoP serves its own region from local cache.

---

## 3. Cache-Control Headers: The Language Between Server and CDN

This is where most engineers get fuzzy, and where L6 candidates need to be crisp. Cache-Control headers are the mechanism through which your origin server communicates caching rules to both browsers and CDN PoPs. If you set them wrong, your CDN either caches nothing (wasting the CDN entirely) or caches the wrong things (serving wrong content to users).

The origin sets these headers in HTTP responses. The CDN reads and obeys them.

### Cache-Control: max-age=86400

```http
HTTP/1.1 200 OK
Content-Type: image/jpeg
Cache-Control: max-age=86400
```

This tells both the browser and the CDN: cache this resource for 86,400 seconds (24 hours). After 24 hours, the cache entry is considered "stale" and must be revalidated with the origin before serving again.

`max-age` is measured from the time the response was received, not from when the origin created it.

### Cache-Control: public vs. private

```http
Cache-Control: public, max-age=3600
```

`public` means: **any cache can store this**, including CDN PoPs, proxy servers, and browsers. Use this for content that is the same for every user — images, CSS files, JavaScript bundles, product pages (if not personalized).

```http
Cache-Control: private, max-age=3600
```

`private` means: **only the user's own browser may cache this**, not shared caches like CDN PoPs. Use this for user-specific responses — a user's profile page, their shopping cart, their inbox.

**The critical mistake engineers make:** Setting `public` on user-specific responses. If user Alice's profile page is cached at the CDN PoP with `Cache-Control: public`, then user Bob (who lives in the same city and hits the same PoP) might receive Alice's cached profile page. This is a serious privacy and correctness bug, and it has actually happened to real companies.

```
WRONG (dangerous):
GET /api/user/profile
Response: Cache-Control: public, max-age=3600
          { "name": "Alice", "email": "alice@example.com" }

Now cached at CDN PoP. Next user in same city hits same PoP.
They get Alice's profile. Data leak.

CORRECT:
GET /api/user/profile
Response: Cache-Control: private, max-age=3600
          { "name": "Alice", "email": "alice@example.com" }

CDN never caches this. Each user's browser caches only their own copy.
```

### Cache-Control: no-cache vs. no-store

These two directives look similar but behave very differently. Confusing them is a common mistake.

**`no-cache`:** The cache (browser or CDN) **may** store a copy, but it **must revalidate** with the origin before serving it on any subsequent request. It always checks "is this still fresh?" before using the cached copy. If the origin says nothing changed (304 Not Modified), the cache serves its stored copy. The name is misleading — `no-cache` does not mean "do not cache." It means "do not serve from cache without checking first."

```http
Cache-Control: no-cache
```

Use case: content that changes frequently, where you want the CDN to always verify it has the latest version, but you want to save bandwidth by not re-downloading the full response if nothing changed.

**`no-store`:** Do NOT store a copy anywhere. Not in the CDN, not in the browser. Every request goes all the way to the origin, fetches the full response, and nothing is kept. This is the truly "do not cache" directive.

```http
Cache-Control: no-store
```

Use case: banking account balances, health records, one-time tokens, any data so sensitive that having a stale copy anywhere is unacceptable.

```
no-cache behavior:
  Request 1 → CDN → Miss → Origin: "Here it is" → CDN stores it
  Request 2 → CDN → Has copy → Calls origin: "I have version abc123, still good?"
              Origin: "Yes, nothing changed" → CDN serves stored copy (304 saved bandwidth)
              OR
              Origin: "New version here" → CDN stores new version, serves it (200)

no-store behavior:
  Request 1 → CDN → Goes to origin → Returns to user (does NOT store)
  Request 2 → CDN → Goes to origin again → Returns to user (does NOT store)
  Every single request hits the origin. No caching ever.
```

### s-maxage: CDN-Specific TTL

The browser and the CDN are different audiences. Sometimes you want different caching behavior for each.

`s-maxage` (shared-maxage) applies specifically to **shared caches** like CDN PoPs. If `s-maxage` is present, CDNs use it instead of `max-age`. Browsers ignore `s-maxage` and use `max-age`.

```http
Cache-Control: max-age=3600, s-maxage=86400
```

This says:
- **Browser:** cache for 3,600 seconds (1 hour). After 1 hour, re-fetch (from CDN).
- **CDN:** cache for 86,400 seconds (24 hours). After 24 hours, re-fetch from origin.

Why would you want this split? Consider a news article that updates a few times a day. You want users to see reasonably fresh content (browser cache expires in 1 hour, so users re-fetch hourly). But you do not want millions of hourly re-fetches hammering your origin — you want the CDN to absorb them. The CDN holds its cache for 24 hours, so origin only gets one request per PoP per day, while users still see updates within an hour.

```
                      ORIGIN
                        |
                        | CDN re-fetches every 24 hours (s-maxage)
                        |
                    [CDN PoP]
                        |
                        | Browser re-fetches from CDN every 1 hour (max-age)
                        |
                    [Browser]

Daily origin requests per PoP: 1
Hourly CDN requests per PoP: could be millions (CDN serves from cache)
Origin is shielded from load spikes.
```

### Vary Header

The `Vary` header tells the CDN which **request headers** should be considered part of the cache key. Normally, the cache key is just the URL. With `Vary`, the CDN stores different cached copies for different header values.

```http
Vary: Accept-Encoding
```

This means: cache a separate copy for each value of `Accept-Encoding`. A request with `Accept-Encoding: gzip` gets a gzip-compressed copy. A request with `Accept-Encoding: br` gets a brotli-compressed copy. Without `Vary: Accept-Encoding`, the CDN might cache only the gzip version and serve it to all users, including those whose browsers expect brotli — which would break decompression.

```
URL: /bundle.js

Cache entry 1: key = "/bundle.js + Accept-Encoding: gzip"   → gzip-compressed bytes
Cache entry 2: key = "/bundle.js + Accept-Encoding: br"     → brotli-compressed bytes
Cache entry 3: key = "/bundle.js + Accept-Encoding: (none)" → uncompressed bytes

Each browser gets the right encoding for it.
```

**The Vary: Cookie danger:**

```http
Vary: Cookie
```

This tells the CDN: store a different cached copy for each unique Cookie header value. Since every logged-in user has a unique session cookie, this means effectively every logged-in user gets their own cache entry. With millions of users, you get millions of cache entries that each have a hit rate of 1. The CDN cache is completely defeated for logged-in traffic.

Avoid `Vary: Cookie` on content you want CDN-cached. Instead, split public content (no cookie in cache key) from personalized content (not cached at CDN at all).

### ETag and Last-Modified: Conditional Requests

These headers enable **revalidation** — the mechanism that lets a cache verify whether its stored copy is still fresh without downloading the full response body.

When the origin serves a response, it can include:

```http
HTTP/1.1 200 OK
ETag: "a3f4b2c1"
Last-Modified: Thu, 12 Jun 2026 10:00:00 GMT
Cache-Control: max-age=3600
```

After 3,600 seconds (when max-age expires), the CDN does not immediately throw away its cached copy and download fresh content. Instead, it sends a **conditional request** to the origin:

```http
GET /article.html HTTP/1.1
If-None-Match: "a3f4b2c1"
If-Modified-Since: Thu, 12 Jun 2026 10:00:00 GMT
```

This says: "I have a copy with ETag `a3f4b2c1`. Has it changed?"

If the content has **not** changed, the origin returns:

```http
HTTP/1.1 304 Not Modified
ETag: "a3f4b2c1"
```

No body. The CDN keeps its cached copy and resets the TTL. This saves bandwidth significantly — if most cached content has not changed (which is true for most static assets), revalidation costs almost nothing.

If the content **has** changed, the origin returns:

```http
HTTP/1.1 200 OK
ETag: "d9e8f7g6"
Cache-Control: max-age=3600
[new full response body]
```

The CDN replaces its cached copy with the new one.

```
After max-age expires:

CDN ---[If-None-Match: "a3f4b2c1"]--> Origin

Case A (no change):
Origin ---[304 Not Modified, no body]--> CDN
CDN keeps stored copy, refreshes TTL
Bandwidth saved: 100% of body size

Case B (changed):
Origin ---[200 OK + new body + new ETag]--> CDN
CDN stores new copy
Bandwidth used: full response
```

---

## 4. What Belongs at the Edge (and What Doesn't)

The CDN is not a magic box you can put in front of everything. You have to understand which content is cacheable at the edge and which is not. Getting this wrong results in either serving wrong content or getting no CDN benefit.

**The core rule:** CDN-cacheable content is content where the response is **identical for everyone** (or identical for everyone in a region).

### Always Cache at CDN

These are safe bets. The response does not depend on who is asking:

- Images (`.jpg`, `.png`, `.webp`, `.svg`)
- CSS stylesheets
- JavaScript bundles
- Web fonts (`.woff2`, `.ttf`)
- Static HTML pages (marketing pages, landing pages, documentation)
- Video files and audio files
- PDF downloads
- Zip archives

Set long TTLs here. `Cache-Control: public, max-age=31536000` (one year) is common for versioned static assets (where the URL changes when content changes).

### Potentially Cache at CDN

These require judgment — the content might be the same for all users, or it might not be:

- Product pages on an e-commerce site: if the page HTML is the same for all users (personalization is loaded separately via JavaScript), this can be cached for hours.
- API responses for non-personalized data: `GET /api/exchange-rates`, `GET /api/weather/tokyo`, `GET /api/sports/scores` — these responses are the same for everyone. Cache for 1–15 minutes.
- Search results for common queries: if product searches return the same results regardless of who is searching, the results page HTML could be cached.

### Never Cache at CDN

These must always come from the origin or from a user-specific API call:

- Shopping cart contents
- User inbox or notifications
- User profile data
- Authentication tokens or session data
- Payment information
- Admin pages
- Real-time financial data (stock trades, account balances)
- Any response that depends on the user's identity

### The Personalization Problem

Here is the practical challenge: almost every modern web page is a **mix** of shared content and user-specific content.

Take a product page on Amazon. The product title, description, images, and price are identical for every user. But the "Add to Wish List" button shows whether you have already wishlisted it. The "Items in Cart" badge in the header shows your cart count. The "Recommended for you" section is personalized.

**Bad approach:** Treat the whole page as user-specific. Set `Cache-Control: private`. The CDN caches nothing. Every user's product page request hits the origin. Origin servers handle millions of requests per second. This is expensive and slow.

**Staff Engineer approach:** Decompose the page. Recognize that most of the HTML is public. Fetch only the user-specific parts separately.

```
PAGE LOAD SEQUENCE (Personalization-Safe CDN Architecture)

Step 1: Browser requests /products/123
  → CDN cache hit (public HTML, cached for 1 hour)
  → User receives page skeleton: title, description, images, price HTML
  → This HTML is identical for all users
  → Served in ~5ms from CDN

Step 2: JavaScript in page runs (client-side)
  → Browser calls /api/user/cart-count      → origin (private, not CDN-cached)
  → Browser calls /api/user/wishlist/123    → origin (private, not CDN-cached)
  → Browser calls /api/recommendations      → origin or user-specific cache

Step 3: Page fills in user-specific parts dynamically
  → Cart count badge updates to "3"
  → Wishlist button shows "Added to Wishlist"
  → Recommendations section populates

Result: CDN serves the heavy HTML (fast), origin only serves lightweight JSON APIs
```

This pattern has several names: **Edge Side Includes (ESI)** when the CDN itself assembles fragments, or more commonly just **client-side hydration** or **client-side data fetching** when JavaScript does it in the browser.

The key insight is that the big, heavy, static parts of your page (all the HTML structure, CSS, JavaScript code) are served by the CDN at 5ms latency. The small, lightweight, user-specific parts (a few JSON fields) are fetched from the origin after the page loads. Users see content instantly and personalization fills in a moment later.

---

## 5. CDN Invalidation: When Content Changes

Caching creates a fundamental tension: you want content cached for a long time (performance), but you also want content to be up to date when it changes (correctness). Invalidation is how you resolve this tension.

**The scenario:** You cached your homepage with `max-age=86400` (24 hours). At noon, someone notices that a critical product price on the homepage is wrong — it shows $9.99 instead of $999.99. You fix the origin server. But now 23 hours of stale content sit in CDN PoPs worldwide. Every user for the next 23 hours sees the wrong price.

You need a way to force the CDN to forget its cached copy and fetch fresh content.

### Method 1: Purge API (URL-Based and Tag-Based)

Every major CDN provides an API to invalidate cached content immediately, before TTL expires.

**URL-based purge:** You specify exact URLs to invalidate.

```bash
# Cloudflare example: purge specific URLs
curl -X POST "https://api.cloudflare.com/client/v4/zones/{zone_id}/purge_cache" \
  -H "Authorization: Bearer {api_token}" \
  -H "Content-Type: application/json" \
  --data '{"files":["https://example.com/homepage","https://example.com/product/123"]}'
```

When you send this API call, Cloudflare immediately invalidates those URLs across all its PoPs (propagation typically takes 1–5 seconds globally). The next request to those URLs triggers a fresh origin pull.

**URL-based purge works fine** when you know exactly which URLs are affected. But consider a product like product #123. That product might appear on:
- `/products/123` (direct product page)
- `/category/electronics` (category listing)
- `/deals` (featured in a deal)
- `/search?q=headphones` (in search results)
- `/homepage` (featured product)

Keeping track of every URL that displays product 123 and purging each one after a product update is complex and error-prone. What if you miss one?

**Tag-based (surrogate key) purge:** Instead of tracking URLs, you attach semantic tags to cached responses at origin time. The CDN indexes these tags. To invalidate, you purge by tag — which instantly invalidates all cached content with that tag, regardless of URL.

```http
# Origin includes this header in its response:
HTTP/1.1 200 OK
Cache-Control: public, max-age=3600
Surrogate-Key: product:123 category:electronics featured-deals homepage
```

Now, when product 123's price changes:

```bash
# Purge all content tagged with product:123
curl -X POST "https://api.fastly.com/service/{service_id}/purge/product:123" \
  -H "Fastly-Key: {api_key}"
```

This purges the product page, the category page listing it, the deals page, the homepage — all at once, with a single API call. The CDN knows which cached objects carry that tag because it indexed them at cache time.

- Cloudflare calls these **Cache Tags**
- Fastly calls them **Surrogate Keys**
- Both work the same way conceptually

### Method 2: Versioned URLs (Cache Busting)

Instead of invalidating cached content, change the URL when content changes. Old URL = old content (still cached, never requested again). New URL = new content (cache miss on first request, then cached normally).

```
Before code change:
  /static/app.js           (cached at CDN for 1 year)

After code change:
  /static/app.a7b3c2d1.js  (the hash is derived from the file's contents)

Old URL: still cached, but no links in your HTML point to it anymore
New URL: cache miss on first request, CDN fetches from origin, then cached
```

Build tools like Webpack and Vite do this automatically. They compute a content hash of each file and append it to the filename. When you change one line of JavaScript, the hash changes, the filename changes, and all users automatically get the new file (because the filename in your HTML changed too).

**Why is this better than purging for static assets?**
- No API call needed — URL change happens automatically at build time
- Zero risk of serving stale content — old URL is simply never requested
- Old content can stay cached with 1-year TTL — it does not matter that it never expires because no one asks for it
- Works reliably across all CDNs simultaneously

**When versioned URLs do not work:** You cannot use this for HTML pages themselves. If `index.html` changes its URL, users with old bookmarks and external links stop working. HTML pages use purging or short TTLs instead.

### Method 3: Short TTL + stale-while-revalidate

This approach avoids the need for explicit invalidation entirely, at the cost of accepting short periods of staleness.

```http
Cache-Control: max-age=60, stale-while-revalidate=3600
```

Here is what this means:

- For the first **60 seconds**: serve from cache, no questions asked. Fast.
- After 60 seconds but within 3,600 seconds: the cached copy is "stale" but not "expired." The CDN **immediately serves the stale copy** (so the user gets a fast response), but **also kicks off a background request to the origin** to fetch a fresh copy. When the fresh copy arrives, the CDN updates its cache for the next request.
- After 3,600 seconds: the cached copy is too old. Must revalidate before serving.

```
Timeline for a cached response:

t=0s: Origin fetch. Fresh copy cached. max-age starts.
t=1s-59s: Cache hit. Serves instantly. No origin contact.
t=60s: max-age expires. Copy is now "stale."

t=61s (user request arrives):
  - CDN serves stale copy immediately (user gets fast response, ~5ms)
  - CDN simultaneously: GET origin (background, user does not wait)
  - Origin returns new version
  - CDN caches new version

t=62s (next user request):
  - CDN serves the fresh version fetched in background
  - User does not know anything changed

Net effect: users almost always get a fast cached response.
Content is never more than 60 seconds stale (max).
Origin is only called once per 60-second window per PoP, not once per request.
```

This is excellent for content that can tolerate a minute of staleness — sports scores, exchange rates, product inventory counts, weather data. Users always get a fast response because they are never blocked waiting for origin revalidation.

### Method 4: Surrogate Keys (Deep Dive)

We touched on surrogate keys in Method 1, but they deserve deeper treatment because they are the most powerful invalidation tool available.

The idea: every cached object has a set of **logical tags** describing what content it contains. The CDN maintains an index from tag → list of cached objects. When data changes, you invalidate by tag — which cascades to all affected cached objects.

```
ORIGIN SERVER RESPONSE for /products/123:
  Cache-Control: public, max-age=3600
  Surrogate-Key: product:123 category:electronics vendor:sony featured:homepage

ORIGIN SERVER RESPONSE for /category/electronics:
  Cache-Control: public, max-age=1800
  Surrogate-Key: category:electronics product:121 product:122 product:123 product:124

ORIGIN SERVER RESPONSE for /homepage:
  Cache-Control: public, max-age=300
  Surrogate-Key: homepage featured:homepage product:123 product:456 product:789


CDN INDEX:
  product:123      → [/products/123, /category/electronics, /homepage]
  category:electronics → [/products/121, /products/122, /products/123,
                           /products/124, /category/electronics]
  featured:homepage → [/products/123, /products/456, /homepage]


WHEN PRODUCT 123 IS UPDATED:
  Purge tag: product:123
  CDN invalidates: /products/123, /category/electronics, /homepage
  All three pages are immediately fresh on next request.
  No code needed to track which pages show product 123.
  The origin declared the dependency when it served the page.
```

This is the cleanest invalidation architecture for complex sites. The origin knows what data each page uses. It declares that as tags. The CDN manages the dependency graph. When data changes, invalidate the tag, trust that everything dependent on that data will refresh.

---

## 6. Edge Computing: More Than Just Caching

Modern CDNs have evolved far beyond serving static files. Today, CDN PoPs run arbitrary code. This is called **edge computing** — your application logic runs at the CDN PoP (close to the user), not at your origin server (far from the user).

The major platforms:

| Platform                   | CDN              | Runtime             |
|----------------------------|------------------|---------------------|
| Cloudflare Workers         | Cloudflare       | JavaScript / WASM   |
| Fastly Compute             | Fastly           | WebAssembly (Rust, Go, JS) |
| AWS Lambda@Edge            | AWS CloudFront   | Node.js / Python    |
| Vercel Edge Functions      | Vercel (Cloudflare) | JavaScript        |
| Netlify Edge Functions     | Netlify (Deno)   | JavaScript          |

Instead of your server in Virginia handling a request, a small piece of code runs in the Tokyo PoP, processes the request, and responds. The result: logic that previously added 200ms of origin round-trip now runs in 5ms.

### What You Can Do at the Edge

**1. A/B Testing**

Without edge computing, A/B testing requires either the origin to assign variants (adds 200ms) or client-side JavaScript to assign variants (causes layout shift when the page loads and then changes).

With edge:

```javascript
// Cloudflare Worker
addEventListener('fetch', event => {
  event.respondWith(handleRequest(event.request))
})

async function handleRequest(request) {
  const url = new URL(request.url)

  // Assign variant based on cookie (or random if new user)
  let variant = getCookieValue(request, 'ab_variant')
  if (!variant) {
    variant = Math.random() < 0.5 ? 'control' : 'treatment'
  }

  // Rewrite URL to serve correct version
  if (variant === 'treatment') {
    url.pathname = '/v2' + url.pathname
  }

  const response = await fetch(url.toString(), request)

  // Set variant cookie on response
  const newResponse = new Response(response.body, response)
  newResponse.headers.append('Set-Cookie', `ab_variant=${variant}; Path=/`)
  return newResponse
}
```

This runs at the PoP. The user gets the correct variant immediately, without any origin round-trip. No layout shift. No origin overhead.

**2. Authentication at the Edge**

Without edge: every request goes to origin to validate the JWT token. Even for requests where the token is invalid (bots, expired sessions), the origin handles the connection.

With edge: validate the JWT signature at the PoP. Reject invalid tokens in ~5ms without touching origin. Legitimate requests are forwarded to origin. Bad requests are killed at the edge.

```javascript
async function handleRequest(request) {
  const token = request.headers.get('Authorization')?.replace('Bearer ', '')

  if (!token) {
    return new Response('Unauthorized', { status: 401 })
  }

  // Verify JWT signature at edge (no origin call needed for verification)
  const isValid = await verifyJWT(token, PUBLIC_KEY)
  if (!isValid) {
    return new Response('Unauthorized', { status: 401 })
  }

  // Valid token: forward to origin
  return fetch(request)
}
```

**3. Personalization at the Edge**

Combine edge computing with an edge-local key-value store to serve personalized content without hitting origin. User's region, language preference, or subscription tier is stored in a fast edge KV. Edge code reads it and customizes the response.

**4. Redirects at the Edge**

URL redirects and rewrites happen at the PoP with no origin involvement. A redirect that previously required an origin round-trip (200ms) now resolves in 5ms. This matters for redirect chains on mobile devices where every round-trip is expensive.

**5. Bot Detection**

Analyze request headers, IP reputation, request frequency, and behavioral patterns at the edge. Block bot traffic before it reaches your origin, which protects origin capacity and reduces costs. Cloudflare's bot management is built on Workers.

### Cloudflare Workers KV

Edge computing is much more useful when your edge code can read data — feature flags, user segments, geo-block rules, redirect mappings.

Cloudflare Workers KV is a globally replicated key-value store. Data written to Workers KV propagates to all 300+ PoPs within approximately 60 seconds. Reads are served from the local PoP with 1–5ms latency anywhere in the world.

```
Workers KV characteristics:

Read latency:  1-5ms    (served from local PoP cache)
Write latency: 200ms+   (writes go to central store first)
Write propagation: ~60 seconds to all PoPs (eventual consistency)
Data types: string values (often JSON-serialized)
Limits: values up to 25MB, key-value pairs up to 1 billion

Good for:
  - Feature flags (read constantly, change rarely)
  - User tier/subscription data (read constantly, change on purchase)
  - Geo-block rules (read constantly, change rarely)
  - Redirect tables (read on every request, update infrequently)

Bad for:
  - Real-time counters (writes conflict, eventual consistency causes issues)
  - Per-user session state with frequent writes
  - Financial transactions requiring strong consistency
```

The eventual consistency model is fine for most edge use cases because feature flags, user segments, and redirect rules do not need to be perfectly consistent across every PoP at exactly the same millisecond. A 60-second propagation delay when you toggle a feature flag is acceptable.

---

## 7. Multi-CDN Strategy (for Reliability)

Depending on a single CDN provider is a single point of failure. If your CDN has an outage, your users cannot reach your site regardless of how resilient your origin infrastructure is. The CDN sits in front of everything — if it goes down, nothing works.

**Real incident:** On July 17, 2023, Cloudflare experienced a significant outage affecting multiple services for approximately 37 minutes. Websites that relied solely on Cloudflare were either unreachable or severely degraded for that period. Sites using a multi-CDN strategy experienced near-zero impact because their traffic manager automatically rerouted to backup CDNs.

### How Multi-CDN Works

```
                         DNS TRAFFIC MANAGER
                    (NS1 / Route 53 / Fastly DNS)
                              |
              +---------------+---------------+
              |               |               |
        [Cloudflare]      [Fastly]      [CloudFront]
           60%              30%             10%
              |               |               |
              +---------------+---------------+
                              |
                       [Origin Servers]
                         (Virginia)


Normal state: weighted routing distributes traffic
  60% of users → Cloudflare PoPs
  30% of users → Fastly PoPs
  10% of users → CloudFront PoPs


Cloudflare outage detected (health check fails):
  Traffic manager detects: Cloudflare health check failing
  Action: shift Cloudflare's 60% to Fastly
  New distribution:
    0% → Cloudflare (down)
    80% → Fastly
    20% → CloudFront

Failover time: 30-90 seconds (DNS TTL dependent)
```

**Health checks:** The traffic manager continuously sends test requests through each CDN to verify it is working. If N consecutive checks fail within a time window, it marks that CDN as unhealthy and reroutes its traffic.

### Costs and Complications of Multi-CDN

**Cache warming:** Each CDN builds its cache independently. Cloudflare's PoP in Tokyo has its own cache. Fastly's PoP in Tokyo has its own cache. If you normally send 60% of traffic through Cloudflare, Fastly's cache is only warmed by its 30% share. When you fail over all 100% of traffic to Fastly, Fastly's cache hit rate drops because it was not seeing the full traffic pattern. Expect increased origin load during failover until Fastly's caches warm up.

**Purging:** When content changes, you must send purge requests to **all CDNs**. If you only purge Cloudflare, 30% of users (on Fastly) still see stale content. This requires your deployment pipeline to call all CDN purge APIs on every content change.

**Cost:** Running multiple CDN contracts simultaneously costs more than a single CDN. The reliability benefit must be weighed against this cost. For high-revenue services (e-commerce during peak season, media streaming), the cost of 37 minutes of downtime vastly exceeds the cost of multi-CDN. For a small startup, single CDN is probably fine.

**When multi-CDN is worth it:**
- Services where 99.99% uptime is contractually required (SLA penalties for downtime)
- High-revenue peak periods (Black Friday for e-commerce)
- Services where a 37-minute outage causes regulatory problems (financial services)

---

## 8. Cache Warming: Preventing Cold Start at the Edge

Every time the CDN cache is empty — after a major purge, after a new CDN is added, after a new PoP comes online, after a CDN failover — users start hitting cache misses. All those misses go to your origin server simultaneously. This is called a **cache stampede** or **thundering herd**.

```
CACHE STAMPEDE SCENARIO

t=0: Major deployment. All cached content purged.
t=1s: Traffic resumes (100k requests/second globally)
t=1s: Every request is a cache miss (CDN cache empty)
t=1s: Every miss triggers origin pull
t=1s: 100k requests/second hitting origin
t=2s: Origin falls over (it normally handles 1k requests/second behind CDN)
t=2s: Site is down

Normal operation:
  CDN absorbs 99% of traffic (cache hit rate 99%)
  Origin sees: 1k requests/second
  Origin is sized for this load

After purge without warming:
  CDN absorbs 0% (all misses)
  Origin sees: 100k requests/second
  Origin is NOT sized for this load → outage
```

### Cache Warming Strategies

**Strategy 1: Pre-Population (Synthetic Requests)**

Before going live after a purge or deployment, send synthetic HTTP requests to your most popular URLs. This triggers origin pulls that warm the CDN cache without real user traffic driving the misses.

```bash
# Simplified example: warm top 100 product pages
cat top_100_urls.txt | while read url; do
  curl -s -o /dev/null "$url" &
done
wait
echo "Cache warming complete"
```

In practice, you would use a tool like Locust or a CDN-specific warming service. You send requests from multiple geographic locations (or use the CDN's API to trigger cache fills per-PoP).

**Strategy 2: Gradual Traffic Shift**

Instead of switching all traffic to a new CDN or resuming all traffic after a purge at once, shift traffic gradually.

```
Traffic shift timeline:

t=0:  Send 1% of traffic through new/empty CDN
      (Cache warms for the most popular 1% of content)
t=5m: Send 5% of traffic
      (Cache warms for more content, top 5% of requests now hitting)
t=15m: Send 20% of traffic
t=30m: Send 50% of traffic
t=1h:  Send 100% of traffic
       (Cache is now warm from gradual ramp, hit rate is high from the start)

At each step: monitor cache hit rate, origin error rate, latency
If metrics look bad: hold at current percentage or roll back
```

**Strategy 3: Origin Protection During Cold Start**

Even with best efforts at warming, your origin must be able to handle higher-than-normal load during the warming period. Always have:

- Load testing results showing what your origin can handle at peak
- Auto-scaling configured to add origin capacity quickly if traffic spikes
- Circuit breakers that shed load gracefully (return cached error pages) rather than crashing

The CDN is not a substitute for a robust origin — it is a multiplier that makes a robust origin scale to global traffic.

---

## 9. Caching for Specific Content Types

Different types of content have different caching requirements. This section shows how to apply everything above to the most common real-world scenarios.

### API Response Caching

REST APIs that return non-personalized data are excellent CDN caching candidates.

```
Example: Product details API

GET /api/v1/products/123
Response: {
  "id": 123,
  "name": "Sony WH-1000XM5 Headphones",
  "price": 349.99,
  "in_stock": true,
  "description": "..."
}

This response is identical for every user who asks for product 123.
Cache it.

Response headers:
  Cache-Control: public, max-age=300, s-maxage=3600
  Surrogate-Key: product:123
  ETag: "a3b4c5d6"

Interpretation:
  - Browser: cache 5 minutes (user sees prices update if they navigate away and return)
  - CDN: cache 1 hour (origin gets at most 1 request per PoP per hour)
  - Surrogate key: when product 123 changes, CDN can be instantly invalidated

When product 123 price changes:
  - Application calls: POST /api/cdn/purge with tag "product:123"
  - CDN invalidates all cached API responses tagged product:123
  - Next request to /api/v1/products/123 fetches fresh from origin
  - New response cached for next hour
```

For personalized API responses (user's cart, user's wishlist status for this product), the response must vary per user. These should **not** be CDN-cached:

```http
GET /api/v1/user/wishlist/123
Cache-Control: private, max-age=60
```

### Video Streaming and CDN

Video delivery is where CDNs earn their cost. A 4K video stream requires 15–25 Mbps sustained bandwidth. Delivering this from a single origin to millions of simultaneous viewers would require petabits of origin bandwidth. CDNs make video streaming economically viable.

Modern video streaming uses **adaptive bitrate streaming** — the video is split into short chunks and the player picks the right bitrate for the user's current network conditions.

```
VIDEO FILE STRUCTURE (HLS — HTTP Live Streaming)

video.m3u8              ← master manifest: lists available quality levels
  ├── 360p.m3u8         ← variant manifest for 360p: lists all 360p chunks
  ├── 720p.m3u8         ← variant manifest for 720p
  └── 1080p.m3u8        ← variant manifest for 1080p

Each variant manifest:
  #EXTM3U
  #EXT-X-TARGETDURATION:6
  #EXTINF:6.0,
  segment_000.ts        ← 6-second video chunk, 360p
  #EXTINF:6.0,
  segment_001.ts        ← next 6-second chunk
  #EXTINF:6.0,
  segment_002.ts
  ...

Each .ts chunk: a complete, independently cacheable video segment
```

CDN caching strategy for video:

```
Master manifest (video.m3u8):
  Cache-Control: public, max-age=30
  (Changes rarely, but keep TTL short so player sees updates like new quality levels)

Variant manifests (720p.m3u8):
  Cache-Control: public, max-age=5
  (For live streams: must be very short so player gets new segments.
   For VOD: can be longer, e.g., 3600s, since segments are fixed)

Video chunks (.ts files):
  Cache-Control: public, max-age=3600
  (Chunks are immutable — once recorded, they never change. Long cache is fine.
   CDN serves 95%+ of video bytes from cache.)

RESULT:
  For a 2-hour movie with 100,000 simultaneous viewers:
  Without CDN: 100,000 × 10 Mbps = 1,000 Gbps origin bandwidth needed
  With CDN: Most chunks already cached. Origin bandwidth ~1-5 Gbps (serving cache misses)
  CDN absorbs 99.9% of bandwidth.
```

For live streaming, the manifest file must have very short TTL (5–30 seconds) so players continuously poll for new segments and see the live feed advance. New chunk files (which have new filenames) are always cache misses on first request, then immediately cached.

### Database Query Result Caching (Application-Level, Redis)

CDN caching works for HTTP responses. But what about expensive database queries inside your application? The results of those queries are cached in Redis — this is application-level caching, not CDN-level, but it is part of the same caching hierarchy.

```
Request path with Redis cache:

User request
  → Application server
  → Check Redis: GET "products:123"
      HIT: deserialize cached result, return (skip database)
      MISS: query PostgreSQL:
              SELECT * FROM products WHERE id = 123
              (slow: 50-200ms)
            Store in Redis: SET "products:123" <result> EX 3600
            Return result

Redis key design for query caching:
  "products:123"           → product 123 data
  "search:electronics:p1"  → first page of electronics search results
  "user:456:cart"          → user 456's cart (NOT shared, user-specific)
  "exchange_rates:USD"     → USD exchange rates (shared, non-personal)
```

**Cache key must encode all query parameters.** A common approach is to hash the query string and parameters:

```python
import hashlib
import json

def cache_key(query: str, params: dict) -> str:
    payload = json.dumps({"query": query, "params": params}, sort_keys=True)
    hash_value = hashlib.md5(payload.encode()).hexdigest()
    return f"query:{hash_value}"

# Usage:
key = cache_key(
    "SELECT * FROM products WHERE category=? AND price<? ORDER BY rating DESC",
    {"category": "electronics", "price": 500}
)
# key = "query:a3f4b2c1..."
```

**Invalidation for database caches — the hardest part:**

When data in the database changes, the Redis cache is stale. How does the cache know to update?

Option A: Short TTL, accept staleness. Set `EX 60` (expire in 60 seconds). Accept that product data might be up to 60 seconds stale. Simple to implement. Works for most use cases.

Option B: Explicit invalidation on writes. Whenever your application writes to the `products` table, it also deletes all Redis keys that might contain that product:

```python
def update_product(product_id: int, new_data: dict):
    # 1. Write to database
    db.execute("UPDATE products SET ... WHERE id=?", product_id)

    # 2. Immediately invalidate Redis keys
    redis.delete(f"products:{product_id}")
    redis.delete(f"search:electronics:*")  # if product is in electronics
    # etc.
```

This is correct but requires you to know all the cache keys that contain a given piece of data — the same dependency-tracking problem as CDN invalidation, just at the application level.

Option C: Change Data Capture (CDC). The database publishes a stream of change events (via tools like Debezium for PostgreSQL/MySQL, or DynamoDB Streams for DynamoDB). Your application subscribes to this stream and invalidates the relevant cache keys when it sees a change event.

```
CDC ARCHITECTURE

[PostgreSQL DB]
  → Debezium (reads WAL/binlog)
    → Kafka topic: "db.products.changes"
      → Cache Invalidation Service (subscriber)
          → On event: UPDATE products SET price=... WHERE id=123
          → Invalidate: Redis key "products:123"
          → Invalidate: CDN tag "product:123" (via CDN purge API)

RESULT:
  Within ~1 second of a database write, both Redis and CDN caches
  are invalidated and serve fresh data on next request.
  No manual invalidation code needed per write path.
  Works even when writes come from multiple services.
```

CDC is the most robust invalidation strategy for complex microservices architectures where data can be written by multiple services. It decouples the write path from invalidation logic — each service just writes to the database, and the CDC pipeline handles cache consistency automatically.

---

## Summary: Cache-Control Header Quick Reference

```
Header                          | Who obeys  | Effect
--------------------------------|------------|------------------------------------------
Cache-Control: public           | CDN + browser | CDN may cache this response
Cache-Control: private          | Browser only  | CDN must NOT cache this response
Cache-Control: max-age=N        | CDN + browser | Cache for N seconds
Cache-Control: s-maxage=N       | CDN only   | CDN caches N seconds (overrides max-age)
Cache-Control: no-cache         | CDN + browser | Must revalidate before serving
Cache-Control: no-store         | CDN + browser | Do not store anywhere
Cache-Control: stale-while-revalidate=N | CDN | Serve stale up to N seconds while updating
Surrogate-Key: tag1 tag2        | CDN only   | Tag this response for group invalidation
Vary: Accept-Encoding           | CDN + browser | Different cache entry per encoding
Vary: Cookie                    | CDN + browser | Different cache entry per cookie (avoid!)
ETag: "hash"                    | CDN + browser | Used for conditional validation requests
```

---

## Summary: Invalidation Strategy Decision Tree

```
Content changed. Need to invalidate cache.

Is the content a static asset (JS/CSS/image)?
  YES → Use versioned URLs (content hash in filename)
        Old URL expires naturally. No purge needed.

  NO (it is an HTML page or API response):
    Do you need it invalidated in < 5 seconds?
      YES → Use CDN Purge API
              Do you know all affected URLs?
                YES → URL-based purge
                NO  → Tag-based purge (attach surrogate keys at serve time)

      NO → Can you tolerate up to 60 seconds of staleness?
              YES → Use stale-while-revalidate (max-age=60, swr=3600)
                    No manual purging needed.
              NO  → Shorten max-age TTL + use conditional requests (ETag)
                    Content refreshes quickly, origin validates efficiently.
```

---

## Summary: What Runs Where

```
CACHING HIERARCHY

[Browser Cache]
  What: Everything with Cache-Control: max-age > 0
  Latency: 0ms (local disk read)
  Scope: One user's device

    |
    | (on cache miss)
    v

[CDN PoP Cache] (5-15ms from user)
  What: Cache-Control: public responses
  Latency: 5-15ms
  Scope: All users in a geographic region sharing this PoP
  Runs: Edge compute (Cloudflare Workers / Lambda@Edge)

    |
    | (on cache miss or private content)
    v

[Application Redis Cache] (1-5ms from app server)
  What: Database query results, session data, computed aggregates
  Latency: 1-5ms
  Scope: All application servers in a region

    |
    | (on cache miss)
    v

[Database] (10-200ms query time)
  What: Source of truth
  Latency: 10-200ms depending on query complexity
  Scope: Single authoritative data store (with replicas)
```

At each layer, a cache hit prevents the request from falling to the next (slower) layer. An L6 engineer designs systems where the vast majority of traffic is handled at the CDN layer (cheapest, fastest), only cache misses reach the application tier, and only genuine data needs hit the database.
# Chapter 31: Caching at Scale — Redis, CDN, and Edge Systems
## Part D: Failure Modes, Multi-Region Caching, Capacity Planning, Observability, and Rate Limiting

---

## What This Part Covers

Caches are not reliable by default. When they fail, they fail in specific, well-understood patterns. Every senior engineer has been woken up at 3 AM by at least one of these. This part is your field guide.

After the failure modes you will learn how to scale caching across multiple geographic regions, how to size a Redis deployment before you ship, what numbers to watch at runtime, and how to build a rate limiter on top of Redis that actually works at scale.

A mental model before diving in: think of the cache as a dam between your database and your users. A healthy dam means the database sees only a trickle of traffic. The failure modes in this chapter are all different ways the dam breaks or gets bypassed:

- **Stampede**: a hole opens (key expires) and everything flows through at once
- **Hot key**: too much water is aimed at one narrow pipe
- **Avalanche**: the entire dam wall crumbles simultaneously
- **Penetration**: attackers find a route around the dam entirely
- **Cold start**: the dam is not built yet and someone opened the floodgates

Understanding these patterns by name is useful in interviews — interviewers expect you to proactively mention them when designing caching layers.

---

## 1. Cache Stampede (The Thundering Herd on Expiry)

### Setting the Scene

Your service handles 10,000 requests per second. The homepage is cached in Redis with a 60-second TTL. 95% of requests are cache hits. Your database handles the remaining 500 requests per second.

At exactly 12:00:00.000 the homepage cache key expires.

Every one of the 10,000 concurrent requests finds the cache empty at the same microsecond. All 10,000 go to the database simultaneously. The database goes from 500 req/sec to 10,000 req/sec in under one millisecond. Connection pools fill, query queues back up, the database crashes. This is a **cache stampede** — also called a dogpile or cache breakdown.

```
Time:          11:59:59     12:00:00     12:00:00.001   12:00:00.010
Cache:         [HIT x10K]  [EXPIRED]    [MISS x10K]    [MISS x10K]
DB req/sec:    500          500          10,000          10,000
DB state:      healthy      healthy      overwhelmed     crashing
```

### Fix 1: Mutex / Cache Lock

Only the first request that finds the cache empty is allowed to fetch from the database. All others wait (sleep and retry) or return stale data while one request reloads the cache.

Implementation uses Redis `SETNX` (SET if Not eXists), which is atomic:

```redis
SETNX lock:homepage 1 EX 30
```

Returns `1` if you got the lock, `0` if another process already holds it. The 30-second expiry is a safety net: if the locking process crashes, the lock releases automatically.

```python
def get_homepage():
    cached = r.get("homepage")
    if cached:
        return cached

    lock_acquired = r.set("lock:homepage", "1", nx=True, ex=30)
    if lock_acquired:
        try:
            data = fetch_from_database()
            r.setex("homepage", 60, data)
            return data
        finally:
            r.delete("lock:homepage")
    else:
        time.sleep(0.05)
        return get_homepage()  # retry — probably a cache hit now
```

### Fix 2: Probabilistic Early Expiry (XFetch)

Instead of waiting for expiry, start refreshing the key before it expires. As the TTL gets close to zero, you probabilistically trigger a background refresh. Only one request wins the lottery; everyone else keeps reading the current (slightly stale) cached value.

```
TTL remaining:  60s     30s     10s     2s      0s
Refresh prob:   ~0%     ~2%     ~15%    ~60%    [too late — already expired]
                                  ^
                          One request fires here, triggers background
                          refresh, everyone else still gets a cache HIT
```

Result: the cache is never empty. No stampede.

### Fix 3: TTL Jitter (Randomize Expiry Times)

If you pre-warm the cache with 50,000 products all set to `TTL = 3600`, they all expire at the same moment one hour later — a stampede of 50,000 simultaneous misses.

Fix: add a random offset to every TTL.

```python
for product in products:
    ttl = 3600 + random.randint(-300, 300)  # ±5 minutes
    cache.set(f"product:{product.id}", product.data, ex=ttl)
```

Expirations are now spread over a 10-minute window. Instead of 50,000 misses per second, you get roughly 83 per second — completely manageable. Apply this everywhere as a default practice.

Which fix should you use? In practice, the answer is usually "all three, layered":

1. **Jitter** everywhere as a cheap baseline — costs nothing, prevents mass expiry
2. **Mutex or probabilistic expiry** for your highest-traffic keys — the 5-10 keys that account for the majority of your cache traffic
3. **Stale-while-revalidate** when you can tolerate a few seconds of staleness — eliminates wait time for end users entirely

---

## 2. Hot Key (Single Key Overload)

### The Problem

A celebrity posts on your platform. Every profile view hits `user:celebrity123`. Your traffic spikes to 1,000,000 requests per second on that single key. Redis handles ~100,000 simple ops/sec per shard. One shard is 10x overloaded. 900,000 requests per second queue behind one CPU core; p99 latency climbs to 500ms.

```
100 App Servers → ALL pointing to Redis Shard 3
                         |
               [ Redis Shard 3 ] <-- 1,000,000 req/sec
                 Single thread         capacity: 100K
                 900K queued
                 p99: 500ms
```

### Fix 1: Local In-Process Cache

Add a tiny in-memory cache inside each application server (LRU, 5-second TTL):

```python
from cachetools import TTLCache

local_cache = TTLCache(maxsize=1000, ttl=5)

def get_user(user_id):
    key = f"user:{user_id}"
    if key in local_cache:
        return local_cache[key]
    value = redis.get(key)
    if value:
        local_cache[key] = value
    return value
```

Effect: each of your 100 app servers caches the value locally. Redis receives at most 100 requests every 5 seconds for that key instead of 1,000,000 per second. Trade-off: 5 seconds of staleness, small per-server memory cost.

| Language | Library              |
|----------|----------------------|
| Java     | Guava Cache          |
| Python   | cachetools.TTLCache  |
| Node.js  | node-cache           |
| Go       | patrickmn/go-cache   |

### Fix 2: Key Replication

Copy the hot key to N shards, distribute reads randomly:

```python
NUM_REPLICAS = 10

# Write: fan out to all replicas
def write_celebrity_profile(data):
    pipe = redis.pipeline()
    for i in range(NUM_REPLICAS):
        pipe.setex(f"user:celebrity123:r:{i}", 3600, data)
    pipe.execute()

# Read: pick one at random
def read_celebrity_profile():
    i = random.randint(0, NUM_REPLICAS - 1)
    return redis.get(f"user:celebrity123:r:{i}")
```

1,000,000 req/sec spread across 10 shards = 100,000 per shard — within capacity. Trade-off: 10x memory for hot keys, write fan-out complexity.

### Fix 3: Read Replicas

Redis primary handles writes; replicas handle reads. Route reads to replicas. Trade-off: replication lag of 10–100ms (acceptable for profile data).

### Detecting Hot Keys

```redis
redis-cli --hotkeys        # Redis 4.0+, scan-based
redis-cli MONITOR          # real-time, but halves throughput — use briefly only
```

Better: track per-key access counts in your application. Alert when any key exceeds 10% of total Redis traffic.

---

## 3. Cache Avalanche (Mass Expiry)

### The Difference From Stampede

Cache stampede is one key causing a spike. Cache avalanche is **thousands of keys expiring simultaneously**, each individually triggering a cache miss and a DB call. The total effect overwhelms the database even though each individual miss looks normal.

### How It Happens

You deploy a new service and your startup code loads 50,000 products into Redis:

```python
# BAD: every key gets the exact same TTL
for product in products:
    cache.set(f"product:{product.id}", product.data, ex=3600)
```

At T+0: 50,000 keys cached. At T+3600: all 50,000 expire in the same one-second window. Your database receives 50,000 simultaneous queries. If each query takes 10ms and you have 50,000 queries per second: 500 concurrent queries at once. Most databases fall over well before that.

The same scenario happens with time-of-day patterns: if most of your users are active between 9 AM and 5 PM, many cache keys are written in that window and expire together the next morning.

### Prevention

Always jitter TTLs on bulk loads (same Fix 3 as above). Never set the same TTL for a large batch of keys:

```python
# GOOD: expirations spread over 10 minutes
for product in products:
    ttl = 3600 + random.randint(-300, 300)
    cache.set(f"product:{product.id}", product.data, ex=ttl)
```

Secondary defense: **circuit breakers**. If your application detects that the cache miss rate has spiked above a threshold (say, 50% misses for 30 seconds), trip the circuit and return a degraded response (empty product list, cached 503 page) rather than letting every miss hit the database. Tools like Netflix Hystrix or Resilience4j implement circuit breakers for the JVM. Most languages have equivalents.

---

## 4. Cache Penetration (Non-Existent Keys)

### The Problem

Someone requests `GET /api/users/99999999999` — a user that does not exist anywhere.

```
Cache lookup: MISS (key not in cache)
DB lookup:    NOT FOUND
Nothing cached — next request for same ID hits DB again, forever
```

An attacker sending 1,000,000 requests for different non-existent IDs bypasses the cache entirely. Every request hits the database. This is an effective denial-of-service attack that costs the attacker almost nothing.

### Fix 1: Cache Negative Results

When the database returns "not found," cache that fact with a short TTL:

```python
user = db.query("SELECT * FROM users WHERE id = %s", user_id)

if user is None:
    redis.setex(f"user:{user_id}", 60, "NOT_FOUND")
    return None
else:
    redis.setex(f"user:{user_id}", 3600, serialize(user))
    return user
```

Trade-off: a legitimately new user with that ID gets "not found" from the cache for up to 60 seconds. Use a shorter TTL (10 seconds) if that window matters.

### Fix 2: Bloom Filter

A Bloom filter answers: "Is this element definitely NOT in the set?"

- "Definitely not" → guaranteed correct; return 404 immediately, zero DB call
- "Probably yes" → may have a small false positive rate (~0.1%); proceed to cache/DB lookup

```
Request: user_id X
      |
      v
Bloom filter check
      |
  Definitely not     Probably yes
      |                    |
      v                    v
  Return 404         Cache → DB
  (no DB hit)        (normal path)
```

Memory comparison for 100 million users:

| Structure    | Memory  | Accuracy         |
|--------------|---------|------------------|
| Hash set     | ~800 MB | 100%             |
| Bloom filter | ~120 MB | ~99.9%           |

```python
from pybloom_live import BloomFilter

bf = BloomFilter(capacity=100_000_000, error_rate=0.001)

# At startup: load all valid IDs
for user_id in db.query("SELECT id FROM users"):
    bf.add(user_id)

def get_user(user_id):
    if user_id not in bf:
        return None  # definitely does not exist
    return check_cache_then_db(user_id)
```

---

## 5. Cold Start: When the Cache is Empty

After a new deployment, cache flush, or initial launch, the cache is completely empty. Every request is a miss. The full load falls on the origin, which was sized to handle traffic WITH the cache in place.

The autoscaler trap:
```
Cache was handling 95% of traffic → DB scaled to handle 5% of peak
Cache flushes → DB receives 20x its designed load
Autoscaler needs 3-5 minutes to spin up new DB nodes
During those 3-5 minutes: outage
```

**Fix 1: Pre-warming at deploy time.** Before routing any traffic to the new cache, run a warming script that reads the top-N most popular items from the database and populates the cache. Only then switch traffic over.

```python
def warm_cache(redis_client, db):
    # Query DB for most-accessed products (sorted by view count)
    products = db.query("""
        SELECT id, data FROM products
        ORDER BY view_count DESC
        LIMIT 10000
    """)

    pipe = redis_client.pipeline()
    for product in products:
        ttl = 3600 + random.randint(-300, 300)  # jitter even during warm
        pipe.setex(f"product:{product.id}", ttl, serialize(product.data))
    pipe.execute()

    print(f"Warmed {len(products)} products into cache")
```

After warming, the cache starts at a healthy hit rate (maybe 70% instead of 0%) and the database is never surprised by full load.

**Fix 2: Shadow traffic.** Mirror a percentage of production traffic to the new cache instance before cutover. The cache warms under realistic load patterns without affecting any users.

```
Production traffic
        |
        +----------> Old cache (serves users, responses counted)
        |
        +----------> New cache (shadow, responses discarded)
                     Warms from real access patterns over 30 minutes
```

After 30 minutes of shadow traffic, the new cache's hot items match the real-world distribution.

**Fix 3: Gradual promotion.**

```
Time +0:00   1% traffic → new cache,   99% → old cache
Time +0:05   5% traffic → new cache,   95% → old cache
Time +0:10  20% traffic → new cache,   80% → old cache
Time +0:20  50% traffic → new cache,   50% → old cache
Time +0:30 100% traffic → new cache
```

At each step, monitor hit rate, p99 latency, and DB load. If metrics degrade, pause the promotion and investigate. Keep the old cache alive as a fallback read target during the entire promotion window.

---

## 6. Eviction Storms

When Redis reaches its `maxmemory` limit, every new write triggers an eviction scan (LRU or LFU lookup), which consumes CPU and adds latency. The death spiral:

```
Memory at 98%
  → New write → eviction scan → latency increases
  → Clients retry → more writes → more scans → more latency
  → Timeouts → application errors → cascade failure
```

Prevention: never let Redis get close to its limit.

```redis
# redis.conf
maxmemory 11gb                 # 70% of a 16GB server
maxmemory-policy allkeys-lru   # evict least-recently-used when at limit
```

`allkeys-lru` is correct for cache workloads: Redis removes the data you accessed least recently, making room for fresh data. The default `noeviction` policy returns errors when full — the wrong behavior for a cache.

Alert thresholds:

| Memory Used | Action                                 |
|-------------|----------------------------------------|
| 60%         | Notice: plan capacity review this week |
| 70%         | Warning: schedule capacity addition    |
| 80%         | Alert: add capacity within 24 hours    |
| 90%         | Critical: immediate action             |

---

## 7. Stale Data Propagation (Write-Behind Failure)

In the write-behind pattern: cache is updated immediately, database write is async. If the background writer fails before the DB write commits:

```
Cache: {name: "Alice"}   (what the user sees — correct)
DB:    {name: "Bob"}     (old value — write never arrived)

If cache is evicted before DB write succeeds:
  Cache: MISS → loads from DB → {name: "Bob"} again
  User sees their change silently reverted
```

Mitigation: persist the write queue to durable storage.

**Option 1 — Redis AOF (Append-Only File)**: Redis writes every command to disk before acknowledging the client. On a crash and restart, Redis replays the AOF log from the beginning and reconstructs the exact in-memory state. Slightly slower writes (one disk flush per command), but nothing is lost on crash.

```
# redis.conf
appendonly yes
appendfsync everysec   # flush to disk once per second (balance of safety vs speed)
                       # "always" is safer but much slower
```

**Option 2 — Transactional outbox pattern**: write to cache AND to a durable `outbox` table in the database in the same transaction. A background worker reads the outbox and writes to the main tables, then deletes the outbox entry. If the worker crashes, the outbox survives; the worker picks up where it left off on restart.

```
Outbox table schema:
  id         | BIGINT PRIMARY KEY AUTO_INCREMENT
  cache_key  | VARCHAR(255)
  new_value  | TEXT (JSON)
  status     | ENUM('pending', 'done')
  created_at | TIMESTAMP

Write flow:
  1. Update cache (fast, in-memory)
  2. INSERT INTO outbox (cache_key, new_value, status) VALUES (..., 'pending')
     -- this INSERT is in the same DB transaction as any related DB changes
  3. Return success to user

Background worker:
  1. SELECT * FROM outbox WHERE status = 'pending' LIMIT 100
  2. For each row: apply the value to the canonical DB table
  3. UPDATE outbox SET status = 'done' WHERE id = ...
  4. Repeat every 100ms
```

The outbox pattern guarantees that even if the background worker is killed, the pending writes survive in the database and will be processed when the worker restarts. It is the standard solution for reliable write-behind caching.

---

## 8. Multi-Region Caching

### The Problem

Your Redis is in US-East (Virginia). EU users experience 150ms round-trip to Virginia, making the cache useless (a 300ms cache hit is worse than a local DB query).

```
Without regional caching:
  EU user → 150ms → Virginia Redis → 150ms back = 300ms

With regional caching:
  EU user → 5ms → EU Redis → 5ms back = 10ms
```

### Active-Passive vs Active-Active

**Active-Passive**: one primary region accepts writes; others are read-only replicas.

```
US-East (Primary)  ←— replication —→  EU-West (Replica)  ←— replication —→  AP-SE (Replica)
Writes go here                         EU reads here                           AP reads here
```

Write latency for an EU user: 150ms (must reach the US primary). Read latency: 5ms (hits local replica). Best for read-heavy workloads with infrequent writes.

**Active-Active**: every region accepts reads and writes, replicated bi-directionally.

Write latency for EU user: 5ms (writes to local EU cluster). Reads: 5ms. The complication is **write conflicts**: if a US user and an EU user update the same key simultaneously, which value wins?

| Conflict Strategy | Description                            | Use Case                  |
|-------------------|----------------------------------------|---------------------------|
| Last Write Wins   | Higher timestamp overwrites            | Simple, can lose data     |
| CRDT              | Data structures that merge correctly   | Counters, sets            |
| Application merge | App resolves conflicts explicitly      | Complex, most flexible    |

Redis Enterprise supports active-active with configurable conflict resolution. Open-source Redis does not.

### Geo-Routing

DNS latency routing (e.g., AWS Route 53) sends users to the nearest regional cache automatically:

```
User in Singapore → AP-SE Redis endpoint
User in Germany   → EU-West Redis endpoint
User in Ohio      → US-East Redis endpoint
```

Cross-region reads still happen — user 123 (Singapore) viewing user 456 (US)'s profile. User 456's canonical data is in the US Redis cluster. The AP-SE cluster does not have it.

Options when this happens:
1. **Fetch directly from US Redis** — 150ms penalty for this one request, then the response is not cached locally (so next Singapore user pays 150ms again)
2. **Cache the foreign data locally in AP-SE** with a short TTL (5 minutes) — next Singapore request hits the local cache in 5ms. Trade-off: the data is up to 5 minutes stale for cross-region viewers.

For most applications, option 2 is correct. Profile data does not change every 5 minutes, and the 5-minute staleness window is invisible to users.

### Data Residency Compliance

GDPR (EU) and similar regulations require that personal data stays within its home region. Never cache EU user PII in a US Redis cluster, even temporarily.

```python
def get_user_data(user_id, user_region):
    cache_client = {
        "EU": eu_redis,
        "APAC": apac_redis,
        "US": us_redis,
    }[user_region]
    return cache_client.get(f"user:{user_id}")
```

Maintain a `user_id → region` mapping table (contains no PII — just a mapping — so it is safe to replicate globally). Enforce the correct regional client at every cache read and write. This enforcement must happen at the cache layer itself, not just at the application layer, because engineers sometimes add caching shortcuts that bypass the application logic.

Common GDPR mistakes to avoid in caching:
- Logging cache keys that contain PII (e.g., `user:email@example.com`) to a US-hosted logging system
- Storing EU user session tokens in a globally replicated cache
- Caching EU user search results in a CDN node located in the US

---

## 9. Capacity Planning for Redis

Four questions to answer before provisioning:

1. How many keys?
2. What is the average key+value size?
3. What is your QPS?
4. What is the TTL distribution (how fast do keys turn over)?

### Memory Estimation

Every Redis key has ~50 bytes of overhead (hash table entry, object header, alignment), plus the key length, plus the value length.

```
Example: 10 million user sessions
  Avg key:   "session:abc123def456" = 22 bytes
  Avg value: 450 bytes (JSON)

Per key: 50 + 22 + 450 = 522 bytes
Total:   10,000,000 × 522 = 5.22 GB
+25% buffer for Redis internals: 5.22 × 1.25 = 6.53 GB
Round up to next standard size:  8 GB
```

Quick reference:

| Avg Value Size | 1M Keys | 10M Keys | 100M Keys |
|----------------|---------|----------|-----------|
| 100 bytes      | 0.2 GB  | 1.9 GB   | 19 GB     |
| 500 bytes      | 0.7 GB  | 6.9 GB   | 69 GB     |
| 2 KB           | 2.2 GB  | 22 GB    | 220 GB    |
| 10 KB          | 10 GB   | 101 GB   | 1 TB      |

For values above 10KB, reconsider whether Redis is the right tool. Redis is optimized for small, frequently accessed values.

### QPS and CPU Planning

Redis is single-threaded per shard. Approximate throughput on a modern server:

| Command Type       | Throughput per shard      |
|--------------------|---------------------------|
| GET / SET          | 100,000–200,000 ops/sec   |
| HGET / HSET        | 80,000–150,000 ops/sec    |
| ZADD / ZRANGE      | 50,000–80,000 ops/sec     |
| SORT (large list)  | 1,000–5,000 ops/sec       |

Planning for 500,000 GET/SET QPS:
- 500,000 / 150,000 = 3.3 shards → round up to 5 → add 50% headroom → 6 shards
- Deploy as Redis Cluster with 6 primary shards (plus replicas for HA)

Warning: a handful of SORT or LRANGE commands on large collections can saturate a shard that handles 100K GETs. Route complex commands to dedicated shards.

### TTL Churn Rate

If average TTL is 60 seconds and you have 10M keys: each key is replaced 1,440 times per day.
That is 10M × 1,440 / 86,400 = **167,000 key writes per second** just from TTL churn — before you count user-initiated writes. Include this in your QPS calculation.

High-churn workloads (short TTLs, frequent writes) need more CPU per unit of stored data than low-churn workloads. If you are storing 10M session tokens with 60-second TTLs, you are actually write-heavy even if reads dominate — because the cache is constantly re-writing all those tokens as users stay active.

### Putting It Together: A Sample Sizing Calculation

Workload: social media feed service
- 50M active users, each with a cached feed (avg 2 KB per feed)
- TTL: 5 minutes (300 seconds)
- Read QPS: 800,000 per second
- Write QPS: 50,000 per second (new posts invalidate feeds)

Memory:
```
50M users × (2,048 + 50) bytes = 50M × 2,098 = ~105 GB
Add 25% buffer: 105 × 1.25 = 131 GB
Provision: 6 × 24GB Redis nodes = 144GB total
```

QPS:
```
Read QPS:    800,000 / 150,000 per shard = 5.3 → 8 shards (with headroom)
Write QPS:    50,000 / 150,000 per shard = 0.3 → absorbed within read capacity
TTL churn:   50M / 300 seconds = 167,000 writes/sec → add to write QPS
Total write: 217,000 writes/sec / 150,000 per shard = 1.5 → 3 additional shards
```

Final cluster: 11 primary shards, each with 1 replica = 22 Redis nodes total.

---

## 10. Observability: What to Monitor

### The Redis INFO Command

```redis
redis-cli INFO all   # snapshot of every internal metric
```

Key fields to read:

```
# Stats
keyspace_hits:1823741293
keyspace_misses:83941823

# Memory
used_memory_human:8.00G
maxmemory_human:10.00G
mem_fragmentation_ratio:1.23   # > 1.5 = fragmentation issue

# Clients
connected_clients:847
blocked_clients:12             # waiting on BLPOP/BRPOP

# Replication
repl_backlog_size:1048576      # grows when replica is lagging

# Keyspace
db0:keys=10423841,expires=9891234,avg_ttl=58241
```

### Latency Monitoring with LATENCY HISTORY

Beyond point-in-time snapshots, Redis records a histogram of slow command latencies over time:

```redis
CONFIG SET latency-monitor-threshold 5   # record events slower than 5ms
LATENCY HISTORY event                    # latency over time for a specific event type
LATENCY LATEST                           # worst latency per event type
LATENCY RESET                            # clear history
```

If `LATENCY LATEST` shows a 200ms spike at 3:15 AM, cross-reference it with your eviction metrics to confirm whether it was an eviction storm. This is how you debug intermittent latency complaints that do not reproduce during business hours.

### Metrics and Alert Thresholds

**Cache hit rate** — the most important single number:

```
hit_rate = keyspace_hits / (keyspace_hits + keyspace_misses)

> 95%:   excellent
90-95%:  acceptable
80-90%:  investigate (TTL too short? cache undersized?)
< 80%:   alert immediately
```

**Memory pressure**:

```
used_memory / maxmemory × 100

< 60%:   comfortable
60-70%:  notice (plan capacity review)
70-80%:  warning (add capacity soon)
> 80%:   critical (evictions accelerating)
```

**p99 latency**:

```redis
CONFIG SET latency-monitor-threshold 5   # log events > 5ms
LATENCY LATEST                           # current maximums
```

```
p99 < 1ms:   excellent
p99 < 5ms:   acceptable
p99 > 10ms:  investigate (memory pressure? network?)
p99 > 50ms:  critical (eviction storm or fragmentation)
```

**Eviction rate**: should be near zero. Any nonzero `evicted_keys` means your cache is undersized.

**Replication lag**: `INFO replication → slave0: lag=X`. Alert if lag > 5 seconds.

Complete alert ruleset (Prometheus format):

```yaml
- alert: RedisCacheHitRateLow
  expr: redis_hit_rate < 0.80
  for: 5m
  severity: critical

- alert: RedisMemoryHigh
  expr: redis_memory_usage_pct > 75
  for: 2m
  severity: warning

- alert: RedisMemoryCritical
  expr: redis_memory_usage_pct > 90
  for: 1m
  severity: critical

- alert: RedisHighLatency
  expr: redis_p99_latency_ms > 10
  for: 2m
  severity: warning

- alert: RedisEvictingKeys
  expr: increase(redis_evicted_keys_total[5m]) > 100
  for: 1m
  severity: warning

- alert: RedisReplicationLag
  expr: redis_replication_lag_seconds > 5
  for: 30s
  severity: critical
```

---

## 11. Rate Limiting Using Redis

### Why Redis for Rate Limiting?

Rate limiting has three requirements: it must be fast (sub-millisecond decision), it must be shared across all application servers (so limits apply globally, not per-server), and it must be atomic (concurrent requests from different servers must not both be allowed to exceed the limit).

A per-server counter fails: if you have 10 application servers each allowing 100 requests per minute per user, your actual limit is 1,000 requests per minute. Redis is the standard solution because it is fast enough (1ms round-trip), centralized (all servers share the same Redis), and supports atomic operations (INCR, Lua scripts).

### Pattern 1: Fixed Window Counter

Count requests per user per fixed time window.

```redis
INCR  rate:user123:2024-01-15-14:00   # increment counter for this minute
EXPIRE rate:user123:2024-01-15-14:00 60
```

```python
def is_rate_limited(user_id, limit=100):
    window = datetime.now().strftime("%Y-%m-%d-%H:%M")
    key = f"rate:{user_id}:{window}"
    pipe = redis.pipeline()
    pipe.incr(key)
    pipe.expire(key, 60)
    count = pipe.execute()[0]
    return count > limit
```

The boundary problem: a user can make 100 requests at 14:00:59 and 100 more at 14:01:00 — 200 requests in 1 second at the window boundary. For security-critical rate limiting, use the sliding window.

### Pattern 2: Sliding Window with Sorted Set

Maintain a log of every request timestamp. At each request, remove old entries and count what remains.

```redis
ZADD  rate:user123  <now_ms>  <request_uuid>          # log this request
ZREMRANGEBYSCORE rate:user123  0  <now_ms - 60000>    # remove entries > 60s old
ZCARD rate:user123                                     # count in last 60s
EXPIRE rate:user123  70                                # auto-clean if idle
```

```python
def is_rate_limited_sliding(user_id, limit=100, window_seconds=60):
    now_ms = int(time.time() * 1000)
    window_ms = window_seconds * 1000
    key = f"rate:{user_id}"
    request_id = str(uuid.uuid4())

    pipe = redis.pipeline()
    pipe.zadd(key, {request_id: now_ms})
    pipe.zremrangebyscore(key, 0, now_ms - window_ms)
    pipe.zcard(key)
    pipe.expire(key, window_seconds + 10)
    count = pipe.execute()[2]
    return count > limit
```

No boundary problem: the window slides with time. A user cannot double up at the minute boundary.

Comparison:

| Dimension       | Fixed Window     | Sliding Window (Sorted Set) |
|-----------------|------------------|-----------------------------|
| Accuracy        | Boundary leakage | Exact                       |
| Time complexity | O(1)             | O(log N)                    |
| Memory per user | 1 integer        | N entries (N = limit)       |
| Good for        | General limits   | Security-critical limits    |

### Making It Atomic with Lua

The pipeline is not atomic — another process could interleave. For high-concurrency correctness, wrap in a Lua script (Lua scripts execute atomically in Redis):

```lua
-- rate_limit.lua
local key      = KEYS[1]
local now      = tonumber(ARGV[1])
local window   = tonumber(ARGV[2])
local limit    = tonumber(ARGV[3])
local req_id   = ARGV[4]

redis.call('ZADD', key, now, req_id)
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
redis.call('EXPIRE', key, math.ceil(window / 1000) + 10)

return count > limit and 1 or 0
```

```python
# Load once at startup
with open("rate_limit.lua") as f:
    rl_script = redis.register_script(f.read())

def is_rate_limited(user_id, limit=100, window_ms=60000):
    return rl_script(
        keys=[f"rate:{user_id}"],
        args=[int(time.time() * 1000), window_ms, limit, str(uuid.uuid4())]
    ) == 1
```

---

## Chapter Summary: The Failure Mode Taxonomy

| Failure Mode        | Root Cause                              | Primary Fix                          |
|---------------------|-----------------------------------------|--------------------------------------|
| Cache Stampede      | Single key expires under high load      | Mutex lock, probabilistic expiry     |
| Hot Key             | One key exceeds shard capacity          | Local cache, key replication         |
| Cache Avalanche     | Many keys expire simultaneously         | TTL jitter on bulk loads             |
| Cache Penetration   | Non-existent keys bypass cache          | Cache negative results, Bloom filter |
| Cold Start          | Empty cache after deployment            | Pre-warming, shadow traffic          |
| Eviction Storm      | Memory at limit triggers scan loop      | maxmemory at 70%, allkeys-lru        |
| Write-Behind Loss   | Async DB write fails before completing  | Durable write queue, AOF             |

Multi-region caching trades consistency for latency. Active-passive handles most read-heavy workloads with less complexity. Active-active reduces write latency for non-primary regions but requires conflict resolution.

Capacity planning: estimate memory per key, multiply by key count, add 25%, round up. Estimate QPS, divide by per-shard throughput, add 50% headroom. Always account for TTL churn as additional write load.

Observability starts with three numbers: hit rate above 90%, memory below 70%, p99 latency below 5ms. If any of these is out of range, you have a problem to investigate.

Rate limiting: O(1) fixed-window counter is simple and works for most cases. O(log N) sliding-window sorted set is accurate at boundaries. Use Lua scripts when concurrent writers share the same rate limit key.

---

*End of Chapter 31, Part D*
# Chapter 31 — Supplementary Section A
### Caching at Scale: Applied Examples, Scale Phases, Blast Radius, and Stale Data Prevention

> This section builds directly on Chapter 31 Part A. Where Part A gave you the concepts and
> vocabulary, this section gives you the applied engineering judgment. The goal: walk into a
> Staff-level design interview and not just know what Redis is, but know *when* to add it,
> *how* it fails, and *how* you stop bad data from spreading silently.

---

## Table of Contents

1. Three Complete Applied Examples
   - A: Social Media News Feed (Twitter / Instagram model)
   - B: User Session Management
   - C: Public API Response Caching (GitHub / Stripe model)
2. How Caching Strategy Evolves With Scale — Four Phases
3. Blast Radius Analysis: What Breaks When Cache Fails
4. Stale Data Propagation Prevention — Deep Dive

---

## 1. Three Complete Applied Examples

Reading about LRU eviction and write-through patterns in the abstract is useful. But interviewers
at the Staff level want to see you apply those patterns to a concrete system with real constraints.
The following three examples each walk through a complete design — what to cache, where to put it,
how to read it, and what breaks if it disappears.

---

### Example A: Social Media News Feed Cache (Twitter / Instagram model)

#### The problem in plain language

When you open Twitter and see your feed, you are looking at posts from hundreds of people you
follow, sorted by time (or by a ranking algorithm). There are 500 million users. Across the
platform, roughly 500,000 new posts are created every day, and the average user opens the app
7–8 times per day. If every feed load hit the database directly, the database would be crushed
within minutes.

Caching is not optional here. It is what makes the product possible.

#### What to cache — and what not to cache

First decision: what even goes in the cache?

**Cache: post content**

A post, once written, almost never changes. The text, author ID, timestamp, and like count (to a
reasonable approximation) are stable. Every user who follows the author will read the same post
object. Storing it once in cache serves millions of readers. This is an ideal cache candidate.

**Cache: user profile data**

Username, avatar URL, bio. Changes infrequently. Read constantly. Cache it.

**Cache: follower counts and following lists**

The list of "who does user 12345 follow?" changes only when the user explicitly follows or
unfollows someone. Cache it. Invalidate on follow/unfollow events.

**Do NOT cache: the personalized feed order as a single blob**

Every user's feed order is different — not just different data, but produced by a ranking algorithm
that takes recency, engagement signals, relationship strength, and dozens of other factors into
account. Caching the final sorted feed per user means storing 500 million different lists. At 10KB
per feed list, that is 5 TB of cache for one tier. Worse, any new post from a followed user
invalidates the cached order immediately.

The right model: cache the raw building blocks (post content, following lists, individual
timelines), not the assembled result.

#### Three-tier cache architecture

```
+----------------------------------------------------------+
|                     USER REQUEST                         |
|              "Load my feed for user 88001"               |
+----------------------------------------------------------+
                          |
                          v
+----------------------------------------------------------+
|   L1: In-Process Cache (per app server)                  |
|   - LRU, ~100MB RAM per server                           |
|   - Holds: post content objects fetched THIS request     |
|   - TTL: 5 minutes (short, because per-process)         |
|   - Miss rate: HIGH (many posts, small cache)            |
+----------------------------------------------------------+
                          |
              (L1 miss — most requests)
                          |
                          v
+----------------------------------------------------------+
|   L2: Redis Cluster                                      |
|   - post:{post_id}        → full post content (JSON)    |
|   - user:{user_id}        → profile data                 |
|   - timeline:{user_id}    → sorted set of post IDs      |
|   - followers:{user_id}   → set of follower IDs         |
|   - TTL: 24 hours for post content, 1 hour for timelines |
|   - Hit rate target: 95%+                                |
+----------------------------------------------------------+
                          |
              (L2 miss — ~5% of requests)
                          |
                          v
+----------------------------------------------------------+
|   L3: CDN (Cloudflare / Fastly)                          |
|   - Images, videos, audio attached to posts             |
|   - Static HTML snippets for crawler bots (SEO)         |
|   - Cache-Control: max-age=3600 for media assets        |
|   - NOT used for personalized data                       |
+----------------------------------------------------------+
                          |
              (origin fetch — images only)
                          |
                          v
+----------------------------------------------------------+
|   Origin: Cassandra + Object Storage (S3)                |
|   - Cassandra: posts, user profiles, timelines           |
|   - S3: images and videos (served via CDN)               |
+----------------------------------------------------------+
```

#### Feed read flow — step by step

Here is exactly what happens when user 88001 opens their feed:

```
Step 1: Get following list
  App server → check L1 cache for following:88001
  L1 miss → Redis SMEMBERS following:88001
  Returns: [user_ids: 101, 205, 988, 3041, ...]  (say, 300 accounts)

Step 2: Fetch per-user timelines (post IDs, sorted by time)
  For each followed user_id, get their recent post IDs:
  Redis ZREVRANGE timeline:101 0 9   (10 most recent posts from user 101)
  Redis ZREVRANGE timeline:205 0 9
  ... (300 pipeline calls, batched in one Redis round-trip)
  Collect: ~3,000 post IDs across all followed accounts

Step 3: Rank post IDs
  Apply ranking algorithm in-memory on the app server
  Select top 50 post IDs to show

Step 4: Fetch post content (batch)
  Redis MGET post:id1 post:id2 post:id3 ... post:id50
  Returns: JSON blobs for each post

Step 5: Cache miss handling (some posts not in Redis)
  For any post IDs that returned nil from MGET:
    Batch fetch from Cassandra
    Write back to Redis:
      SET post:{id} {json} EX 86400
```

Diagrammed as a flow:

```
App Server
    |
    |--1--> Redis: SMEMBERS following:88001
    |<--1-- [101, 205, 988, ...]
    |
    |--2--> Redis: PIPELINE [ZREVRANGE timeline:101 0 9,
    |                         ZREVRANGE timeline:205 0 9, ...]
    |<--2-- [[post_id_A, post_id_B, ...], [post_id_C, ...], ...]
    |
    |  (rank post IDs in memory → top 50)
    |
    |--3--> Redis: MGET post:A post:B post:C ... post:50
    |<--3-- [json, json, nil, json, nil, ...]  (some misses)
    |
    |--4--> Cassandra: SELECT * FROM posts WHERE id IN (miss_ids)
    |<--4-- [rows for missed posts]
    |
    |--5--> Redis: SET post:miss_id1 {json} EX 86400
    |       Redis: SET post:miss_id2 {json} EX 86400
    |
    |--6--> Return assembled feed to user
```

The entire flow, excluding Cassandra fallback, completes in ~5ms because all Redis operations are
batched into 2–3 round-trips using pipelining.

#### Failure handling

**Redis goes down entirely**

The app server falls back to reading from Cassandra directly. The MGET becomes individual
Cassandra reads (or a batch select). Response time jumps from ~5ms to ~50–100ms. The database
load increases dramatically. This is survivable for minutes but not hours — you need Redis back.

**Thundering herd on a new post**

When a popular user posts, thousands of their followers hit the feed endpoint simultaneously. All
their app servers try to fetch the same new post from Cassandra (it is not in Redis yet), write it
to Redis, and return it — all at once. This is the thundering herd.

Solution: **mutex lock on cache population**. One request gets a Redis lock (SET post:id LOCKED NX
EX 5), fetches from Cassandra, writes to cache, releases lock. Other requests that try to acquire
the lock wait briefly, then re-read the now-populated cache.

**The hot celebrity problem (the Justin Bieber problem)**

Justin Bieber has 100 million followers. When he posts, the naive approach is **fan-out on write**:
for every follower, add the new post ID to their Redis timeline sorted set. That means 100 million
ZADD operations triggered by one post. This takes tens of minutes and creates enormous Redis write
load.

The alternative is **fan-out on read**: when user X opens their feed, compute the feed on the fly
by fetching Justin's most recent posts and merging them. No pre-population needed.

The problem with pure fan-out on read: for regular users with 300 followers, it requires 300 Redis
ZREVRANGE calls per feed load. That is acceptable. For Justin, the ZREVRANGE call for his
timeline is one call regardless of follower count — perfectly fine.

The practical solution used by Twitter (documented in their engineering blog): **hybrid fan-out**:

```
If followed_user.follower_count <= 10,000:
    Fan-out on write: pre-populate all followers' timeline caches
Else (celebrity account):
    Fan-out on read: at feed-load time, fetch celebrity's timeline
    and merge it with the pre-populated timelines from normal accounts
```

```
Regular user posts (300 followers):
    Post created → ZADD timeline:follower1 ... (300 writes, fast)

Celebrity posts (100M followers):
    Post created → No fan-out writes
    Feed load → merge celebrity's ZREVRANGE result in real-time
```

This hybrid approach keeps write load bounded while keeping read latency acceptable.

---

### Example B: User Session Management

#### The problem in plain language

A **session** is proof that you logged in. When you log into a website, the server needs a way to
remember who you are on every subsequent request — HTTP is stateless by design, so without session
management, you would have to log in on every click.

There are two broad approaches: **client-side sessions** (store session data in the browser) and
**server-side sessions** (store session data on the server, give the browser only a reference ID).

#### Why Redis, not just cookies

**Client-side session (JWT or encrypted cookie):**

```
Browser                            Server
  |                                  |
  |-- POST /login (user+password) -->|
  |                                  | Verify password OK
  |<-- Set-Cookie: session=JWT ------|  (JWT contains: user_id, role, expiry)
  |                                  |
  |-- GET /dashboard (Cookie: JWT) ->|
  |                                  | Decode JWT → user_id=12345, role=admin
  |<-- Dashboard HTML ---------------|
```

The browser holds the full session state. The server is stateless — it does not remember you; it
just re-reads the cookie on every request.

**The problem:** You cannot revoke a JWT before it expires. If a user logs out, you delete the
cookie from their browser — but anyone who copied that JWT (from a compromised machine, a network
intercept, etc.) can still use it until it expires. If the expiry is 24 hours, a stolen JWT is
valid for up to 24 hours after logout.

**Server-side session (Redis-backed):**

```
Browser                     App Server              Redis
  |                              |                    |
  |-- POST /login -------------->|                    |
  |                              | Generate UUID:     |
  |                              | session_id =       |
  |                              | "a7f3-9c2e-..."    |
  |                              |                    |
  |                              |-- HSET session:a7f3 user_id 12345
  |                              |         role admin
  |                              |         last_seen 1720000000 -->|
  |                              |-- EXPIRE session:a7f3 86400 --->|
  |                              |                    |
  |<-- Set-Cookie: sid=a7f3 -----|                    |
  |                              |                    |
  |-- GET /dashboard (sid=a7f3)->|                    |
  |                              |-- HGETALL session:a7f3 -------->|
  |                              |<-- {user_id:12345, role:admin} -|
  |<-- Dashboard HTML -----------|                    |
  |                              |                    |
  |-- POST /logout (sid=a7f3) -->|                    |
  |                              |-- DEL session:a7f3 ------------>|
  |                              |                    | Key gone
  |<-- 200 OK ------------------|                    |
```

After the DEL, the session ID in the browser cookie is useless — the server will look it up in
Redis, find nothing, and redirect to the login page. Logout is instant and global (works across
all devices if you delete all sessions for a user).

#### Redis session structure

```redis
HSET session:{session_id} \
    user_id   12345        \
    role      admin        \
    last_seen 1720000000   \
    ip        "192.168.1.1" \
    user_agent "Mozilla/5.0 ..."
```

Using a **hash** (HSET) rather than a string (SET) lets you update individual fields (like
`last_seen`) without serializing and deserializing the entire session object.

#### Key design: preventing enumeration attacks

The session key is `session:{UUID}`. A UUID like `a7f3b9c2-e541-4d78-9a2c-3b5f01e22dc9` has
$2^{122}$ possible values. An attacker cannot guess session IDs by incrementing a counter the way
they could with `session:1`, `session:2`, etc. This is a **security requirement**, not just a
convention.

#### TTL strategy: sliding expiration

A fixed TTL (set once at login, expire 24h later) is simple but annoying. If you use an app
for 23 hours straight, your session expires mid-use.

**Sliding expiration**: on every authenticated request, reset the TTL:

```redis
-- On every request that passes auth:
EXPIRE session:{session_id} 86400
```

Now the session lives 24 hours from the **last activity**, not from login. It naturally expires
for inactive sessions without kicking out active users.

#### High availability: Redis Sentinel

For sessions, you need **high availability**, not just performance. Sessions are not just a cache
— they are the source of truth for who is logged in. If Redis goes down, every authenticated
request fails (user is logged out or cannot be authenticated).

**Redis Sentinel** monitors a primary Redis node and one or more replicas. If the primary fails,
Sentinel promotes a replica to primary and notifies all clients. App servers reconnect to the new
primary automatically.

```
                   +------------------+
                   |  Redis Sentinel  | (monitoring cluster health)
                   +------------------+
                      |          |
            +---------+          +---------+
            v                              v
   +------------------+         +-------------------+
   | Redis Primary    |-------->| Redis Replica     |
   | (writes here)    | repl.   | (reads optional)  |
   +------------------+         +-------------------+

If Primary dies:
  Sentinel detects failure (heartbeat timeout)
  Sentinel promotes Replica to Primary
  App servers reconnect to new Primary
  ~30-120 seconds of failover time
  Sessions created during failover: may be lost
```

Losing sessions during a 60-second failover window is acceptable. The alternative — distributed
session storage with full consistency guarantees — adds enormous complexity for a marginal
benefit. Users affected during failover simply log in again.

#### Compliance: GDPR session data

GDPR (Europe's privacy law) requires that personal data about EU citizens be stored in the EU and
not transferred outside without explicit consent. Sessions contain personal data (user ID, IP
address, behavior timing).

Solution: **regional session clusters**. When a user registers, store their region in the account
record. Route their session writes to the Redis cluster in their region:

```
EU user logs in → App server (EU-West) → Redis EU cluster only
US user logs in → App server (US-East) → Redis US cluster only
```

Session IDs include a region prefix (`EU_a7f3b9c2...`) so any app server can route lookups to
the correct regional Redis without a global lookup table.

---

### Example C: Public API Response Caching (GitHub / Stripe model)

#### The problem in plain language

GitHub's REST API serves data about repositories, commits, issues, and pull requests. At peak,
it handles hundreds of thousands of requests per second. A naive implementation would query
PostgreSQL on every API call — the database would instantly become the bottleneck.

The additional constraint: GitHub's API has both **public endpoints** (anyone can call
`GET /repos/torvalds/linux` without logging in) and **authenticated endpoints** (your account's
private repos). These require completely different caching strategies, for a critical reason:
a CDN that caches an authenticated response might accidentally serve User A's private data to User B.

#### Multi-layer caching strategy

```
                         API Request
                              |
              +---------------+----------------+
              |                                |
              v                                v
    PUBLIC endpoint                  AUTHENTICATED endpoint
    GET /repos/{owner}/{repo}        GET /user/repos
              |                                |
              v                                v
    +------------------+           +------------------------+
    | Layer 1:          |           | Layer 1: Client-side   |
    | Client-side cache |           | Cache-Control: no-store|
    | Cache-Control:    |           | (NEVER cache auth resp)|
    | max-age=60        |           +------------------------+
    +------------------+                       |
              |                                v
              v                    +------------------------+
    +------------------+           | Layer 3: Redis         |
    | Layer 2: CDN     |           | Key: apicache:         |
    | Cloudflare /     |           |   user:{id}:repos:v2   |
    | Fastly caches    |           | TTL: 30 seconds        |
    | public responses |           | (short — auth data     |
    | by URL           |           |  changes frequently)   |
    +------------------+           +------------------------+
              |                                |
              +---------------+----------------+
                              |
                              v
                   +--------------------+
                   | Layer 4: Database  |
                   | (PostgreSQL)       |
                   | Materialized views |
                   | for expensive agg. |
                   +--------------------+
```

#### Layer 1: Client-side caching headers

```http
HTTP/1.1 200 OK
Cache-Control: public, max-age=60, s-maxage=300
ETag: "abc123def456"
Last-Modified: Sat, 13 Jun 2026 10:00:00 GMT
Vary: Accept-Encoding
```

- `max-age=60`: Browser may serve this response from its local cache for 60 seconds without
  re-validating.
- `s-maxage=300`: CDN (shared cache) may serve this for 300 seconds.
- `ETag`: A fingerprint of the response. On revalidation, client sends `If-None-Match: abc123`.
  If unchanged, server returns `304 Not Modified` — same data, no body, saves bandwidth.

For authenticated endpoints:

```http
Cache-Control: private, no-store
```

`no-store` tells every intermediary (browser, CDN, proxy) to never cache this response. It must
always be fetched fresh.

#### Layer 2: CDN with surrogate key purging

Public API responses for popular repositories are cached at CDN edge nodes globally. When
`torvalds` pushes a commit to the Linux kernel, the API response for
`GET /repos/torvalds/linux` is stale.

**Problem:** The CDN is caching this URL across hundreds of PoPs. How do you purge it everywhere
instantly?

**Surrogate keys** (also called cache tags):

When the origin serves the response, it includes a header:

```http
Surrogate-Key: repo:12345 user:789 commit:latest
```

The CDN indexes this response under all three tags. When a push event arrives:

```
GitHub receives push webhook for repo 12345
  → API server calls CDN purge API:
      DELETE /purge?tag=repo:12345
  → CDN invalidates ALL cached responses tagged repo:12345
     across all PoPs, within ~1 second
```

This is far better than trying to enumerate every URL that might be affected by a push.

#### Layer 3: Application cache (Redis) for authenticated endpoints

Authenticated API responses cannot use the CDN (privacy risk). Instead, they use Redis with short
TTLs.

```redis
-- Cache key includes: API version, user ID, endpoint path
-- Prevents v1 response being served for v2 request
-- Prevents User A's data being served to User B

SET "apicache:v2:user:12345:/user/repos" {json_response} EX 30

-- On write event (user creates new repo):
DEL "apicache:v2:user:12345:/user/repos"
```

The 30-second TTL is short enough that stale data is not a major user-experience issue (you might
wait 30 seconds to see your new repo in the list), but long enough to absorb burst traffic.

#### The API versioning trap

A subtle but critical point: **cache keys must include the API version**.

If your cache key is `apicache:user:12345:/user/repos`, a client using API v1 and a client using
API v2 share the same cache entry — but v1 and v2 might return different fields, different formats,
or different data shapes. One will get the wrong response.

Correct key design:

```
apicache:{api_version}:user:{user_id}:{endpoint_path}
```

When you roll out API v2, old v1 cache entries are simply ignored (different key prefix), and v2
entries populate naturally on first use.

#### Rate limit counters must NEVER be cached

A common mistake: caching the response to any API call, including the API infrastructure logic
that checks rate limits. Rate limit counters must always hit Redis (or the authoritative rate limit
store) directly:

```
Incoming request
  |
  +----> Rate limit check: INCR ratelimit:user:12345
  |      If > 1000, return 429 (Too Many Requests)
  |      (NEVER cache this check — must be real-time)
  |
  +----> Cache check: GET apicache:v2:user:12345:/repos
         (This is where you cache API responses)
```

If you accidentally served a cached response that included a stale rate limit decision, a user
could bypass rate limits entirely by hammering an endpoint until they get a cached 200 OK.

---

## 2. How Caching Strategy Evolves With Scale — Four Phases

This is one of the most important frameworks for Staff-level system design. Engineers who add
Redis "because it is what you do" are optimizing prematurely. Engineers who skip Redis until 10
million users are dealing with a production fire. The right answer depends on where you are in
the growth curve.

---

### Phase 1: No Cache (0 to ~10,000 users)

```
Browser → App Server → Database (direct)
```

```
+-----------+         +----------------+         +------------+
|  Browser  |-------->|  App Server    |-------->|  Database  |
|           |<--------|  (stateless)   |<--------|  (Postgres)|
+-----------+         +----------------+         +------------+
```

At this scale, the database handles all reads comfortably. A single Postgres instance with proper
indexes can handle thousands of QPS. Response times are fast. Your bottleneck is not the database
— it is probably feature development velocity.

**What you should do instead of caching:**
- Add database indexes for your most common queries
- Use connection pooling (PgBouncer) so app servers do not exhaust database connections
- Optimize expensive queries (use EXPLAIN ANALYZE to find sequential scans)
- Cache nothing — every caching layer you add is a layer you must understand, maintain, debug, and
  operate

**The Staff-level warning:** Junior engineers sometimes add Redis to every new project "because
Netflix uses it." At 5,000 users, Redis adds operational complexity (you need to manage a Redis
deployment, handle its failures, reason about cache coherence) with near-zero performance benefit.
You are solving a problem you do not have. The correct response to "should we add Redis?" at
Phase 1 is almost always: **"What is the actual bottleneck? Let me look at the query logs first."**

---

### Phase 2: Application-Level Cache (10,000 to ~100,000 users)

At this scale, you start to see a real pattern: a small number of objects are read extremely
frequently. Your 10 most popular product pages account for 30% of all database reads. The same
user profile is fetched 50 times per minute across different app servers.

**First bottleneck:** Repeated identical queries for popular data hammering the database.

```
+-----------+      +--------------+      +-------+      +------------+
|  Browser  |----->| App Server 1 |----->|       |      |            |
+-----------+      +--------------+      |       |      |            |
                                         | Redis |----->| Database   |
+-----------+      +--------------+      | (one  |      | (Postgres) |
|  Browser  |----->| App Server 2 |----->| node) |      |            |
+-----------+      +--------------+      |       |      |            |
                                         |       |      |            |
+-----------+      +--------------+      +-------+      +------------+
|  Browser  |----->| App Server 3 |----->
+-----------+      +--------------+
```

You introduce a **single Redis instance** shared across all app servers. This is better than an
in-process cache per app server because:

- In-process cache is not shared — all three app servers might have the same popular object cached
  separately, and an update to one does not propagate to the others (cache incoherence)
- Redis is shared — one cache, consistent across all app servers

**What to cache at Phase 2:**
- User profiles (read on almost every authenticated request)
- Product catalog, configuration data, feature flags
- Results of expensive DB queries that are stable for at least 60 seconds

**What to monitor:**
- Database query rate (should drop as cache hit rate climbs)
- p99 response time (should improve)
- Cache hit rate (target >80% before celebrating)
- Redis memory usage (set a maxmemory limit, choose eviction policy)

---

### Phase 3: Distributed Cache (100,000 to ~1,000,000 users)

A single Redis node hits its limits:
- Memory: a single instance can hold ~100GB on a large machine, but 100M user profiles at 1KB
  each is 100GB — one node is at its limit
- Hot keys: a single node handles ~100,000 ops/sec; if one key is accessed 200,000 times per
  second (a viral post's like count), that one node is the bottleneck
- Single point of failure: Redis node goes down, everything misses to the database simultaneously

**Solution: Redis Cluster**

Redis Cluster automatically shards your keyspace across N primary nodes using consistent hashing
with 16,384 slots. Each key is assigned to a slot via CRC16(key) % 16384, and each node owns a
range of slots.

```
                 +------------------+
                 |   App Servers    |
                 |  (all of them)   |
                 +------------------+
                    /     |     \
                   /      |      \
                  v       v       v
   +-----------+  +-----------+  +-----------+
   | Redis     |  | Redis     |  | Redis     |
   | Primary 1 |  | Primary 2 |  | Primary 3 |
   | slots     |  | slots     |  | slots     |
   | 0-5460    |  | 5461-10922|  |10923-16383|
   +-----------+  +-----------+  +-----------+
        |               |               |
   +-----------+  +-----------+  +-----------+
   | Replica 1 |  | Replica 2 |  | Replica 3 |
   +-----------+  +-----------+  +-----------+
```

Each primary has one or more replicas for HA. If Primary 2 fails, its replica promotes
automatically, and slots 5461-10922 are served by the new primary after ~30 seconds.

**Add CDN at Phase 3:**

Static assets (images, CSS, JS, videos) should not be served by your app servers. A CDN absorbs
60–80% of your total outbound bandwidth and reduces app server load substantially:

```
Before CDN:
  User requests image → App server → S3 → return image through app server
  Costs: app server CPU, outbound bandwidth (expensive), latency

After CDN:
  User requests image → Nearest CDN PoP → CDN serves from cache
  On CDN miss → CDN fetches from S3 directly (not through app server)
  Costs: CDN bandwidth (cheap), lower latency, zero app server involvement
```

**Cache warming on deployment:**

When you deploy a new app server or restart a Redis node, the local/in-process cache starts cold.
If 10 new app servers start simultaneously under heavy load, they all miss everything and hit Redis
(or the DB) at the same time — **cold start crush**.

Solution: before bringing new nodes into the load balancer rotation, pre-warm their caches by
replaying recent read traffic against them. Or: accept slightly elevated DB load for 2–3 minutes
and monitor closely.

---

### Phase 4: Multi-Region Cache (1,000,000+ users)

You now have users in Europe, Asia, and the Americas. Your Redis cluster is in US-East. A cache
lookup from an app server in Frankfurt to US-East adds ~100ms network round-trip. Your p99
response time is dominated by this latency.

```
BEFORE multi-region:

  User in Germany
      |
      v
  App server (Frankfurt)
      |
      | ~100ms network latency
      v
  Redis Cluster (US-East)
      |
      v
  Response back to Germany (~100ms return)

Total cache lookup: ~200ms (worse than a local DB query!)
```

**Solution: regional cache clusters**

```
                    DNS geo-routing
                          |
        +-----------------+-----------------+
        |                 |                 |
        v                 v                 v
  +-----------+     +-----------+     +-----------+
  |  US-East  |     |  EU-West  |     |  AP-South |
  |  App +    |     |  App +    |     |  App +    |
  |  Redis    |     |  Redis    |     |  Redis    |
  |  Cluster  |     |  Cluster  |     |  Cluster  |
  +-----------+     +-----------+     +-----------+
        |                 |                 |
        +--------+--------+-----------------+
                 |
                 v
         Global Database
         (primary region)
         + read replicas
```

User in Germany → DNS routes to EU-West → local Redis lookup (~1ms) → local DB replica on miss
(~5ms). Latency drops from 200ms to ~6ms.

**The read-your-writes consistency problem:**

A user in the US updates their profile, then their colleague in Germany reads it 2 seconds later.
The write went to US-East primary DB. The EU-West DB replica may not have replicated it yet
(replication lag: 1–10 seconds typical). The EU-West cache definitely does not have the new value
yet.

Germany reads the EU cache → stale data.

Solutions:
1. **Session affinity**: For 30 seconds after a write, route that user's reads back to the primary
   region. Implemented via a short-lived flag (`read_from_primary:user_id → expire 30s`).
2. **Write-through to multiple regions**: On profile update, invalidate caches in all regions
   simultaneously via an event bus (Kafka with regional consumers).
3. **Accept eventual consistency**: For non-critical data (profile bio, avatar), stale data for
   a few seconds is acceptable. Design your UI to indicate "Changes may take a moment to reflect."

**GDPR: EU data must stay in EU**

If your EU-West Redis cluster replicates user data to US-East, you may be violating GDPR. EU user
session data, profile data, and behavioral data must reside in EU infrastructure. Never let your
multi-region replication logic blindly copy EU user data across the Atlantic.

Implementation: tag every user record with their data-residency region. Cache invalidation events
are region-scoped — an event about EU user 12345's profile only invalidates caches in EU-West,
never US-East or AP-South.

#### V1 → 10× → 100× growth summary

```
+----------+--------+--------------------------------------------+
| Scale    | Users  | Caching Architecture                       |
+----------+--------+--------------------------------------------+
| V1       | <10K   | No cache. DB + indexes only.               |
+----------+--------+--------------------------------------------+
| 10x      | ~100K  | Single Redis node. CDN for static assets.  |
|          |        | In-process LRU for hot config data.        |
+----------+--------+--------------------------------------------+
| 100x     | ~1M    | Redis Cluster (sharded). Sentinel HA.      |
|          |        | CDN with surrogate-key purging.            |
|          |        | Cache warming on deploy. Write-through.    |
+----------+--------+--------------------------------------------+
| 1000x    | ~10M+  | Multi-region clusters. DNS geo-routing.    |
|          |        | Event-driven invalidation (Kafka).         |
|          |        | Multi-CDN failover. GDPR-aware routing.    |
|          |        | Dedicated cache platform team.             |
+----------+--------+--------------------------------------------+
```

---

## 3. Blast Radius Analysis: What Breaks When Cache Fails

A Staff Engineer is responsible for the systems they design even during incidents at 3 AM. The
difference between a Senior Engineer and a Staff Engineer in an incident is that the Staff Engineer
already knew what would break — they had mapped it out before deploying.

**Blast radius** is a way of measuring the damage when a component fails:

```
Blast Radius = (Number of services affected)
             × (Severity of degradation per service)
             × (Time to recover)
```

Before you ship a caching system, you must be able to answer for each tier: "If this disappears
right now, what is the first thing a user notices? In how many seconds? How many users are
affected? What percentage of requests fail?"

---

### Scenario 1: One Redis Cluster Shard Goes Down

In a 6-shard Redis Cluster, each shard owns roughly 2,730 of the 16,384 hash slots. Keys assigned
to those slots are held on that shard only.

```
Redis Cluster (6 shards):

  Shard 1 [slots 0-2730]       Shard 4 [slots 8192-10922]
  Shard 2 [slots 2731-5460]    Shard 5 [slots 10923-13652]
  Shard 3 [slots 5461-8191] X  Shard 6 [slots 13653-16383]
               ^
               |
          SHARD 3 FAILS

Keys hashing to slots 5461-8191 → all miss → go to DB
Affected keys: ~1/6 of your keyspace (~16% of all cache lookups)
```

**With replication (replica for Shard 3 exists):**

Redis Cluster automatically promotes the Shard 3 replica to primary. During the failover window
(typically 30–120 seconds):
- Requests to Shard 3 keys return CLUSTERDOWN errors or are retried
- Smart clients detect the topology change and reroute to the new primary
- DB receives increased load for Shard 3's keys during this window

**Without replication:**

Shard 3's keys are gone. Every request for a Shard 3 key misses to the DB indefinitely (until
you restore the shard). If Shard 3 held session data or popular content, the impact is significant.

**Containment: circuit breaker on the DB path**

```
if cache_error_rate > 5%:
    open circuit breaker on cache
    all requests go directly to DB
    alert on-call engineer

if db_error_rate > threshold_during_failover:
    return stale data from secondary snapshot (if available)
    or return 503 with Retry-After: 30
```

Do not let a single shard failure cascade into a full DB overload. The circuit breaker trades
slightly degraded service (DB-only mode, higher latency) for continued availability.

---

### Scenario 2: Entire Redis Cluster Goes Down

This is the worst-case cache failure. All cache lookups miss. The database suddenly receives
100% of the read traffic that was previously absorbed by Redis.

The critical insight: **databases are typically sized assuming the cache will handle most reads.**

```
Normal operation:
  Total read QPS: 100,000
  Cache hit rate: 90%
  DB read QPS:    10,000  (cache absorbs 90,000 QPS)
  DB is sized for: ~15,000 QPS (20% headroom)

Redis cluster dies at time T:
  T+0s:   All 100,000 read QPS hit DB
  T+5s:   DB at 100,000 QPS, max capacity 15,000 QPS
          Connection pool exhausted
  T+10s:  DB starts rejecting connections
          App servers timeout waiting for DB responses
  T+15s:  App servers retry (making load worse)
  T+20s:  App servers time out, return 500 errors
  T+30s:  Total service outage
```

```
Timeline of Cascading Failure:

  Redis dies ─────────────────────────────────────────────
                 |
                 v
  DB QPS spikes 10x ──────────────────────────────────────
                       |
                       v
  DB connection pool exhausted ───────────────────────────
                              |
                              v
                 App server timeouts ────────────────────
                                       |
                                       v
                          Client retries multiply load ──
                                                    |
                                                    v
                                             Total outage
```

This cascade is extremely common. It has caused major outages at many companies.

**Mitigations:**

1. **Size the DB for 20–30% of traffic without cache** — not 5–10%. Yes, this costs money. An
   outage costs more.

2. **Circuit breaker on the cache path** — if cache response time exceeds 200ms (not just down,
   but slow), treat it as a miss and go to DB. Do not wait for the full timeout. A slow Redis is
   more dangerous than a dead Redis because it ties up app server threads while waiting.

3. **Rate limiting to the DB during failover** — if the DB is receiving more QPS than its safe
   limit, start shedding requests with 503 Retry-After responses rather than letting the DB
   collapse. Controlled degradation beats total collapse.

4. **Stale-while-revalidate** — serve the last cached value even after it expires, while
   asynchronously fetching a fresh value. A stale response is better than a 500 error.

5. **Read-only mode** — for some applications (social feeds, news, product catalogs), if the
   cache is down, switch to a read-only mode that serves only pre-rendered static snapshots
   (generated by a periodic batch job) rather than live DB queries.

---

### Scenario 3: CDN PoP Goes Down

A CDN **Point of Presence** (PoP) is an edge server in a specific city or region. Major CDN
providers (Cloudflare, Akamai, Fastly) operate hundreds of PoPs globally.

```
Normal:
  User in Chicago ──→ CDN PoP Chicago ──→ cached response (<10ms)

CDN PoP Chicago fails:
  User in Chicago ──→ Anycast routes to next-nearest PoP (Dallas)
                  ──→ cached response from Dallas (<20ms instead of <10ms)
```

CDN providers use **Anycast routing**: the same IP address is advertised from multiple geographic
locations. BGP routing automatically sends you to the nearest healthy PoP. If Chicago fails, the
next-nearest PoP (Dallas, perhaps) begins answering Chicago users with a 10–30ms latency increase.

This is the most graceful failure mode in the caching stack. CDN PoP failures are:
- Automatically handled by the CDN provider's routing infrastructure
- Invisible to users beyond a small latency increase
- Resolved by the CDN provider without your involvement

The main operational concern: **origin server must be able to handle the increased traffic** if
a large PoP fails and its traffic falls back to origin (CDN misses increase). Monitor your origin
traffic rate as a leading indicator of CDN health.

---

### Blast Radius Containment Strategies (Summary Table)

```
+---------------------------+------------+----------+----------------------------+
| Failure                   | Impact     | Duration | Mitigation                 |
+---------------------------+------------+----------+----------------------------+
| One Redis shard (w/ repl) | 16% misses | 30-120s  | Auto-failover, circuit     |
|                           |            |          | breaker on DB path         |
+---------------------------+------------+----------+----------------------------+
| One Redis shard (no repl) | 16% misses | Until    | Shard recovery procedure,  |
|                           |            | restored | DB rate limiting           |
+---------------------------+------------+----------+----------------------------+
| Entire Redis cluster      | 100% miss  | Until    | DB sized for 30% traffic,  |
|                           | to DB      | restored | circuit breaker, rate      |
|                           |            |          | limiting, stale serving    |
+---------------------------+------------+----------+----------------------------+
| CDN PoP                   | Latency    | Minutes  | Anycast auto-reroute,      |
|                           | increase   |          | multi-CDN failover         |
|                           | in region  |          |                            |
+---------------------------+------------+----------+----------------------------+
| CDN entire provider       | Origin     | Hours    | Multi-CDN setup (primary + |
|                           | traffic    |          | fallback provider),        |
|                           | surge      |          | pre-provisioned origin     |
+---------------------------+------------+----------+----------------------------+
```

**Staggered TTL expiry** — a final technique worth naming explicitly:

If you populate 1 million cache entries simultaneously (after a deployment or a cache flush) and
give them all `TTL=3600`, they all expire at the same moment one hour later. At T+3600, 1 million
DB reads happen simultaneously — a **cache stampede**.

Solution: add random jitter to TTLs:

```redis
-- Instead of:
SET key value EX 3600

-- Use:
SET key value EX {3600 + random(0, 300)}
  -- Expires somewhere between 60 and 65 minutes
  -- Spreads expiry across a 5-minute window
  -- No simultaneous DB stampede
```

---

## 4. Stale Data Propagation Prevention — Deep Dive

Stale data is the most common correctness bug in cached systems. The database has the truth. The
cache has a copy. Between a write to the database and the corresponding cache update, there is a
window — possibly milliseconds, possibly minutes — during which reads return wrong data.

At small scale, stale data is a minor annoyance (you refresh the page and see the new value). At
large scale, stale data causes:
- Users seeing their own profile changes revert after a second (write made it to DB, cache served
  old value)
- Prices, inventory levels, or financial balances shown incorrectly
- Security decisions based on stale authorization data

**The fundamental question:** What is the maximum acceptable staleness window for each data type?

```
+------------------------+---------------------------+----------------+
| Data Type              | Acceptable Staleness      | Strategy       |
+------------------------+---------------------------+----------------+
| User profile (bio)     | Minutes                   | TTL (5 min)    |
| Product price          | Seconds                   | Write-through  |
| Account balance        | Zero                      | No caching     |
| Post content           | Minutes                   | TTL (1 hour)   |
| Authorization/ACLs     | Seconds                   | Event-driven   |
| Feature flags          | Seconds                   | Event-driven   |
| Session data           | Zero (must be live)       | No TTL caching |
+------------------------+---------------------------+----------------+
```

---

### Prevention Strategy 1: Versioned Cache Keys

The standard approach uses a cache key like `user:12345`. The problem: when user 12345 updates
their profile, you invalidate `user:12345`. But what if two app servers are simultaneously writing
to the cache — one with the old value, one with the new? You have a race condition.

**Versioned cache keys** eliminate this problem structurally:

```
Database record:
  users table:
    user_id: 12345
    name: "Alice"
    cache_version: 3       <-- stored alongside user data

Old cache entry:
  key: "user:12345:v2"    <-- version 2 (stale, will expire naturally)
  value: {"name": "Old Alice", ...}

After profile update:
  DB writes: name="Alice", cache_version=4

Next read flow:
  App server reads DB → gets cache_version=4
  Looks up cache key "user:12345:v4" → MISS (new version not yet cached)
  Fetches from DB → caches under "user:12345:v4"
  Returns fresh data

  Old key "user:12345:v3" still exists in Redis
  but is never requested again
  It expires naturally when its TTL ends
```

No explicit delete needed. The old key is simply never accessed again and expires on its own TTL.

**Trade-off:** old versioned keys accumulate in Redis memory until they expire. If you have
frequent updates, you might have several stale versioned keys per object consuming memory. Set
a TTL on all versioned keys to bound this growth.

---

### Prevention Strategy 2: Emergency Purge Capability

Every production caching system must have a **break glass purge operation** — the ability to
immediately remove stale data when correctness is more important than performance.

**Use case:** A product price was entered incorrectly in the database. The correct price is $49.99,
but due to a data entry error, the price was stored as $4.99 for 2 minutes before being caught.
During those 2 minutes, the CDN and Redis both cached the wrong price. Even after correcting the
DB, both caches continue serving $4.99 until their TTLs expire.

You need to purge immediately.

**Redis purge — the WRONG way:**

```redis
-- NEVER do this in production:
KEYS user:*
-- This is O(N) over ALL keys in Redis
-- On a Redis node with 10 million keys, this blocks Redis
-- for several seconds, causing timeouts for ALL clients
```

**Redis purge — the RIGHT way (SCAN):**

```redis
-- Safe pattern-based purge using SCAN:
-- SCAN is O(1) per call, iterates in small batches

cursor = 0
loop:
    cursor, keys = SCAN cursor MATCH "user:*" COUNT 100
    if keys is not empty:
        DEL keys          -- batch delete
    if cursor == 0:
        break             -- full iteration complete
```

This is slow (takes minutes for millions of keys) but safe — it does not block Redis.

**CDN purge — surrogate keys (cache tags):**

```http
-- Cloudflare: purge by cache tag
DELETE https://api.cloudflare.com/client/v4/zones/{zone_id}/purge_cache
Body: {"tags": ["product:99871"]}

-- Fastly: purge by surrogate key
PURGE https://api.fastly.com/service/{id}/purge/product:99871
```

One API call purges all CDN-cached responses tagged with `product:99871` across all PoPs globally,
typically within 1–2 seconds. This is why surrogate keys are non-optional in any serious CDN
caching strategy.

**Tag → key mapping for application cache:**

For your Redis application cache, maintain a secondary index mapping tags to cache keys:

```redis
-- When you cache a product response:
SET product:99871 {json_response} EX 3600
SADD tag:product:99871 "product:99871"
SADD tag:category:electronics "product:99871"

-- When product 99871 is updated:
keys = SMEMBERS tag:product:99871
DEL keys                          -- purge all cache entries for this product
DEL tag:product:99871             -- clean up the tag index
```

Now you can purge all cached content related to a product (including any aggregate pages that
included it) by tag, not by enumeration.

---

### Prevention Strategy 3: Cache-Busting via Events (Change Data Capture)

**Change Data Capture (CDC)** is a technique where a system reads the database's write-ahead log
(WAL) — the internal log that records every database write — and publishes each change as an event
to a message bus. The cache invalidation system subscribes to these events.

This approach decouples the application from cache invalidation. The application writes to the
database normally. A separate infrastructure component handles cache consistency.

```
Full CDC-based invalidation pipeline:

  +------------+
  | App Server |
  |            |
  | INSERT INTO|
  | users SET  |
  | name=...   |
  +------------+
         |
         | SQL write
         v
  +------------------+
  |   PostgreSQL     |
  |                  |
  |   users table    |
  |   (row updated)  |
  |                  |
  |   Write-Ahead    |
  |   Log (WAL):     |
  |   UPDATE users   |
  |   SET name=...   |
  |   WHERE id=12345 |
  +------------------+
         |
         | WAL tail read
         v
  +------------------+
  |    Debezium      |  (open-source CDC tool by Red Hat)
  |                  |
  |  Reads Postgres  |
  |  WAL in real     |
  |  time; converts  |
  |  row changes to  |
  |  JSON events     |
  +------------------+
         |
         | Publishes to Kafka topic:
         | "db.public.users"
         v
  +------------------+
  |     Kafka        |
  |                  |
  |  Topic: db.users |
  |  Message:        |
  |  {               |
  |    op: "UPDATE", |
  |    table:"users",|
  |    id: 12345,    |
  |    after: {...}  |
  |  }               |
  +------------------+
         |
         | Consumer reads events
         v
  +------------------+
  |  Cache           |
  |  Invalidation    |
  |  Service         |
  |                  |
  |  Sees UPDATE for |
  |  users:12345     |
  |  → DEL user:12345|
  |  (Redis)         |
  |  → Purge CDN tag |
  |  user:12345      |
  +------------------+
         |
         v
  +------------------+
  |   Redis          |
  |                  |
  |   DEL user:12345 |
  |   (key removed)  |
  +------------------+
```

**End-to-end latency:** approximately 200–800ms from the DB commit to the cache key deletion,
depending on Kafka consumer lag and Debezium configuration.

**Why this is better than application-level invalidation:**

Application-level invalidation (where the app server calls `DEL user:12345` after writing to the
DB) has a subtle race condition:

```
Time 0: Write succeeds in DB
Time 1: App server calls DEL user:12345 in Redis
Time 2: Another request fetches user:12345, gets a cache MISS
Time 3: That request reads from DB (gets new value), writes to Redis cache

RACE CONDITION:
What if step 3 (read from DB + write to cache) happens BEFORE step 1 (DEL)?
  - The request that triggered the DEL sees the delete as a cleanup of nothing
  - The concurrent request has already cached the OLD value from the DB
    (because the DB write had not committed yet when it read at time 2.5)
  - Result: stale data in cache even after the DEL

CDC avoids this: the event is triggered AFTER the WAL record is written
(i.e., after the transaction commits), guaranteeing the invalidation always
happens after the new data is durable.
```

**When to use CDC versus simpler approaches:**

CDC is powerful but operationally complex — you need Debezium, Kafka, a consumer service, and
robust monitoring for each. Use it when:
- You have many services that need to react to DB changes (not just cache invalidation)
- Your cache invalidation bugs are causing real user impact
- Your team has the operational maturity to run a Kafka cluster

For smaller deployments, **write-through cache** (application writes to DB and Redis in the same
code path) is simpler and correct for most cases.

---

### Putting It All Together: Defense in Depth

No single strategy eliminates stale data risk. A production system combines multiple layers:

```
Layer 1: TTL as baseline
  All cache entries have a TTL.
  Even if every other mechanism fails, staleness is bounded.
  Choose TTL based on acceptable staleness per data type.

Layer 2: Write-through for high-stakes data
  On any write, update both DB and cache in the same transaction (or
  write to DB and immediately DEL from cache, forcing next read to refresh).
  Ensures freshness within milliseconds for data you control.

Layer 3: Event-driven invalidation for cross-service data
  When Service A updates data that Service B caches, use CDC/Kafka
  to propagate invalidation events across service boundaries.
  Handles the case where you cannot modify the writer to do write-through.

Layer 4: Emergency purge capability
  For correctness incidents (wrong price, security fix, data breach cleanup),
  have a tested, documented purge procedure that can clear caches
  within 60 seconds without blocking production traffic.
  Run a purge drill quarterly — you do not want to learn the procedure
  during an incident.

+-------------+   +---------------+   +-------------------+   +----------+
|  TTL        |   | Write-through |   | Event-driven      |   | Emergency|
|  (baseline) |-->| (high-stakes) |-->| invalidation      |-->| purge    |
|             |   |               |   | (cross-service)   |   | (break   |
|  All data   |   | Prices,       |   | CDC → Kafka →     |   | glass)   |
|  TTL set    |   | auth, session |   | consumer → DEL    |   |          |
+-------------+   +---------------+   +-------------------+   +----------+
```

---

## Summary: Staff-Level Caching Judgment Framework

When you sit down for a system design interview and caching comes up, the Staff-level answer is
not "use Redis." It is a structured judgment that covers five dimensions:

```
1. WHAT to cache
   - Shared across users? Yes = cache candidate
   - Changes frequently? How frequently? → determines TTL
   - PII? GDPR or compliance constraints? → determines regional routing

2. WHERE to cache
   - In-process (LRU): for hot config data, not user data
   - Redis (shared): for session, auth, popular objects
   - CDN: for public, static, unauthenticated content only

3. HOW to read
   - Cache-aside: standard, simple, most common
   - Read-through: cleaner application code, higher vendor coupling
   - Refresh-ahead: for predictable access patterns

4. HOW to invalidate
   - TTL: simplest, always use as baseline
   - Write-through: when freshness matters more than write latency
   - Event-driven CDC: when cross-service, or write-through is not feasible
   - Versioned keys: when race conditions on invalidation are a concern

5. WHAT HAPPENS WHEN IT FAILS
   - Blast radius of each tier
   - DB sized for 20-30% traffic without cache
   - Circuit breaker + rate limiting on DB path
   - Stale-serve fallback before 503
   - Emergency purge capability (tested, not just documented)
```

A cache is not a performance optimization you bolt on after the fact. It is an architectural
component with correctness, availability, and compliance implications. Design it deliberately,
from the first principles of what data changes, who reads it, how fast it must be fresh, and
what happens when the cache lies.
# Chapter 31 — Part B: Advanced Caching for Staff Engineers
### Distributed Locking, Cache Coherence, Security, Write-Path Failures, Testing, and Serialization

> "A cache is not a database. Treat it like one and you will be surprised. Treat it like a cache and you will be surprised less often."

---

## Table of Contents

1. Distributed Locking with Redis (Deep Dive)
2. Cache Coherence in Distributed Systems
3. Cache Security (Deep Dive)
4. Write-Path Failure Handling
5. Testing Cache Behavior
6. Serialization Format Trade-offs in Cache

---

## 1. Distributed Locking with Redis (Deep Dive)

### Why distributed locks exist at all

Imagine a movie ticket booth with one physical ticket remaining for tonight's showing of a sold-out film. One cashier at one window — easy. If somebody asks "is there a ticket?" the cashier checks, says yes, takes their money, and marks the ticket sold. No problem.

Now imagine ten ticket booths, all connected to the same inventory database, and 50 people rush in simultaneously. Every cashier checks the database at the same time, every cashier sees "1 ticket remaining," every cashier sells the ticket, and fifty people show up to the cinema with a valid receipt. That is the classic **race condition** on shared mutable state.

A **lock** is a rule that says: "only one person can check-and-change the ticket count at a time." On a single machine, the operating system gives you a **mutex** (mutual exclusion lock). Every thread that wants the ticket count must acquire the mutex first. If another thread holds it, you wait. Simple.

The problem begins when you have ten application servers. Each server has its own mutex in its own process memory. Server 1's mutex has no idea Server 2 even exists. Server 2's mutex does not protect Server 1. So you have ten completely independent mutexes, none of which coordinate with each other, all of which think they are the only lock in the universe.

```
Without distributed lock — 10 servers, 1 item left:

  Server 1          Server 2          Server 3
     |                  |                  |
  read inventory     read inventory     read inventory
     |                  |                  |
   sees: 1            sees: 1            sees: 1
     |                  |                  |
  decrement          decrement          decrement
     |                  |                  |
   write: 0          write: 0          write: 0
                                           |
                                     (actual DB: -2)
```

Every server read the same value before any server wrote back. The final state is nonsense. This is called a **lost update**.

A **distributed lock** lives outside every application server — in a place all servers can reach, typically Redis. Now all ten servers compete for the same lock object. Whoever gets it, proceeds. Everyone else waits or fails fast.

```
With distributed lock — 10 servers, 1 item left:

  Server 1         Server 2         Server 3
     |                 |                |
  LOCK REQUEST     LOCK REQUEST     LOCK REQUEST
     |                 |                |
     +----> Redis <----+----------------+
               |
         Server 1 wins
               |
     Server 1 holds lock
     Server 2 gets nil (retries)
     Server 3 gets nil (retries)
               |
     Server 1 reads inventory = 1
     Server 1 decrements → 0
     Server 1 RELEASES LOCK
               |
         Server 2 tries again → gets lock → reads 0 → "sold out"
```

Exactly one server proceeds at a time. Inventory stays consistent.

---

### The basic pattern: SET NX PX

Redis gives you a single command that is **atomic** (cannot be interrupted halfway):

```
SET lock:inventory:item_123 {worker_id} NX PX 5000
```

Breaking that down:

- `SET lock:inventory:item_123` — store a value at this key
- `{worker_id}` — store a unique ID identifying which worker holds this lock
- `NX` — only set if the key does **N**ot e**X**ist (this is the lock check — if the key exists, someone else holds it)
- `PX 5000` — expire in 5000 milliseconds (auto-release if the worker crashes)

The whole command is atomic. There is no gap between "check if key exists" and "set the key." That gap is where race conditions live, and Redis closes it completely with a single command.

**If SET returns OK**: you hold the lock. Do your work. Then delete the key to release.

**If SET returns nil**: someone else holds the lock. Fail fast ("item currently being purchased, try again") or retry after a short backoff.

```python
import redis
import uuid
import time

def acquire_lock(client, lock_name, timeout_ms=5000):
    worker_id = str(uuid.uuid4())
    result = client.set(
        f"lock:{lock_name}",
        worker_id,
        nx=True,        # NX: only set if not exists
        px=timeout_ms   # PX: expire in milliseconds
    )
    if result:
        return worker_id   # caller uses this to release safely
    return None            # lock not acquired

def release_lock(client, lock_name, worker_id):
    # Must use Lua for atomicity — see below
    lua_script = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    else
        return 0
    end
    """
    client.eval(lua_script, 1, f"lock:{lock_name}", worker_id)
```

**The crash problem** is why you set an expiry: if the worker that holds the lock crashes at line 7 of its code, it never calls `release_lock`. Without an expiry, the lock lives forever and no other worker can ever proceed. The expiry is a **dead man's switch** — if the holder disappears, the lock dissolves on its own after `timeout_ms`.

**The wrong-worker-deletes problem** is subtler and why you store `worker_id` in the lock value:

```
Timeline of a bug:

t=0s   Worker A acquires lock, stores worker_id="A"
t=0s   Worker A starts slow DB operation
t=5s   Lock expires (A took too long)
t=5s   Worker B acquires lock, stores worker_id="B"
t=6s   Worker A finishes, calls DEL lock:inventory:item_123
         (A deletes B's lock! B doesn't know.)
t=6s   Worker C acquires lock
         (Now B and C both think they hold the lock.)
```

If you just `DEL` without checking who owns the lock, you can delete someone else's lock. The fix is the Lua script above: it atomically checks that the value still matches your `worker_id` before deleting. If it doesn't match (someone else acquired it after yours expired), the script returns 0 and does nothing.

**Why Lua?** Because you need to check-and-delete as a single atomic operation. If you used `GET` followed by `DEL` as two separate Redis commands, another worker could sneak in between them. Lua scripts in Redis execute as a single atomic unit — no other command can run while your script is executing.

---

### Redlock: locking across multiple Redis nodes

Single-node locking has a fatal flaw in high-availability setups. Redis replication is **asynchronous**: the master accepts a write and sends it to replicas a few milliseconds later. If the master crashes after accepting your lock but before replication completes, the replica that gets promoted has no record of your lock. When the new master comes up, it looks empty. Another worker acquires the same lock. Now two workers both hold the lock simultaneously — the exact situation you were trying to prevent.

**Redlock** is an algorithm designed by Redis creator Salvatore Sanfilippo that solves this by using multiple independent Redis nodes (not replicas — genuinely independent masters, each on its own hardware):

```
Redlock with 5 independent Redis nodes:

Client                Node1   Node2   Node3   Node4   Node5
  |                     |       |       |       |       |
  +--SET lock NX PX-->  |       |       |       |       |
  +--SET lock NX PX----------->|       |       |       |
  +--SET lock NX PX------------------->|       |       |
  +--SET lock NX PX-------------------------->|       |
  +--SET lock NX PX---------------------------------->|
  |                     |       |       |       |       |
  |   OK (t=2ms)        |       |       |       |       |
  |             OK (t=3ms)      |       |       |       |
  |                     nil (t=3ms)     |       |       |
  |                             OK (t=4ms)      |       |
  |                                     nil (t=5ms)     |
  |
  Acquired on 3 of 5 nodes (majority).
  Total elapsed: 5ms. Lock TTL: 5000ms. Valid time remaining: 4995ms.
  LOCK GRANTED.
```

The rules for Redlock success:

1. The client sends `SET lock:X {token} NX PX {ttl}` to all N nodes at roughly the same time
2. **Majority**: the client must receive `OK` from at least `floor(N/2) + 1` nodes. For N=5, that is 3.
3. **Time check**: the total time to acquire across all nodes must be less than the lock TTL. If it takes 4.9 seconds to acquire a 5-second lock, your valid window is 0.1 seconds — not useful.
4. If either condition fails: send `DEL lock:X` to every node where you did get `OK`, then wait a random backoff period and retry.

Why majority? Because if any single node fails, the lock still exists on the remaining four. A majority (3 of 4) can still be formed, but only by the node that held the original lock. The failed node cannot be used to form a fraudulent majority that grants the lock to a second client.

**The Martin Kleppmann controversy**: In 2016, distributed systems researcher Martin Kleppmann published a detailed critique arguing Redlock is unsafe even with correct implementations, because it relies on timing assumptions that clock drift can violate. If one Redis node's system clock runs slightly fast, its lock expires a few milliseconds before the others. In that window, a second client can acquire the lock on that node, form a new majority, and now two clients hold the lock.

His proposed solution is **fencing tokens**, covered next.

Salvatore Sanfilippo responded that Redlock is designed for environments where approximate mutual exclusion is acceptable, and that absolute safety requires a consensus system like ZooKeeper or etcd. Both are correct — they were describing different requirements.

**When to use Redlock**: financial inventory deductions, payment idempotency, license seat counting. Places where two workers holding the lock simultaneously has real monetary or correctness consequences.

**When single-node is fine**: user preference writes, UI personalization state, non-critical counters. If two workers briefly both proceed, the worst case is a mildly inconsistent UI for one user for a few seconds.

---

### Fencing Tokens: the right answer to split-brain

A **fencing token** is a monotonically increasing number that a lock service hands out each time a lock is granted. The storage layer (database, file system, external API) refuses any write that arrives with a token lower than the highest token it has already seen.

```
Fencing token flow:

t=0   Worker A acquires lock.  Gets token=33.
t=0   Worker A starts writing to DB. Sends: WRITE data, token=33
t=2s  DB records: highest_seen_token=33. Write accepted.

t=5s  Lock expires (Worker A is still running — it was slow).
t=5s  Worker B acquires lock.  Gets token=34.
t=5s  Worker B writes to DB. Sends: WRITE data, token=34
t=5s  DB records: highest_seen_token=34. Write accepted.

t=6s  Worker A finishes its slow path. Tries to write. Sends: WRITE data, token=33
t=6s  DB checks: 33 < 34 (highest seen). REJECTED.
      Worker A learns it lost the lock. Handles the error gracefully.
```

The database does not need to know anything about locks. It only needs to track the highest token it has seen and enforce the monotonicity rule. Even if the lock service has a clock problem, the storage layer's ordering guarantee remains correct.

This is the **correct** solution to the "Worker A completes after losing the lock" problem. The Lua script for release prevents accidental deletion of another worker's lock, but it does not prevent Worker A from successfully completing its DB write after its lock expired. Fencing tokens close that gap.

```
Without fencing tokens (dangerous):

  Lock expires    New lock granted    A writes DB    Stale write succeeds!
       |               |                  |                 |
  -----+---------------+------------------+-----------------+--->  time
  A holds lock   B holds lock       A's work lands    Corrupts B's work

With fencing tokens (safe):

  Lock expires    New lock granted    A writes (token 33)    B's write (token 34)
       |               |                  |                       |
  -----+---------------+------------------+-----------------------+--->  time
  A: token=33   B: token=34          DB rejects 33          DB accepts 34
```

---

## 2. Cache Coherence in Distributed Systems

### The problem: many caches, one truth

**Cache coherence** is the problem of keeping multiple copies of the same data in sync when the original data changes. It is well-studied in CPU hardware design (L1/L2/L3 caches across cores) and it reappears at every level of distributed systems.

Consider a realistic production setup:

```
20 app servers — each has an in-process LRU cache (e.g., Caffeine, in-memory dict)
1 Redis cluster — shared cache layer
1 CDN (Cloudflare, Fastly) — edge cache for rendered pages and API responses
1 database — the source of truth
```

User Alice updates her display name from "Alice Smith" to "Alice Johnson."

```
After Alice's update — what knows what?

  App Server 7 (where Alice's request landed):
    in-process cache: "Alice Johnson"  <-- updated
    
  App Servers 1-6, 8-20:
    in-process cache: "Alice Smith"    <-- STALE
    
  Redis cluster:
    user:alice: "Alice Smith"          <-- STALE (write was DB-only)
    
  CDN:
    /profile/alice page: "Alice Smith" <-- STALE (cached HTML)
    
  Database:
    users table: "Alice Johnson"       <-- CORRECT
```

The next request for Alice's profile that lands on Server 3 reads Server 3's stale in-process cache, serves "Alice Smith" to whoever asked, and Alice calls support wondering why her profile won't update.

Three main solutions exist, each with different trade-offs.

---

### Solution 1: Centralized Invalidation (broadcast approach)

On every write to the database, publish an **invalidation event** to a channel that all application servers subscribe to. Each server receives the event and clears the affected key from its local in-process cache.

```
Centralized Invalidation Flow:

  User Alice
      |
      v
  App Server 7
      |
  1. Write to DB: UPDATE users SET name='Alice Johnson' WHERE id=alice
      |
  2. Publish to Kafka topic "cache-invalidations":
     { "key": "user:alice", "timestamp": 1718400000 }
      |
      v
  Kafka Topic: cache-invalidations
      |
      +-------+-------+-------+-------+-------+
      |       |       |       |       |       |
  Server 1  Srv 2  Srv 3  Srv 4  ...  Srv 20
      |
  Each server receives event, calls:
    local_cache.delete("user:alice")
    redis.delete("user:alice")
```

**Advantages**: fast invalidation (sub-second), relatively simple to understand, works for arbitrary cache topologies.

**Disadvantages**:

- Network fan-out: 20 servers means 20 messages per invalidation. At 10,000 writes per second, that is 200,000 invalidation messages per second — non-trivial traffic.
- Ordering not guaranteed: if two updates to the same key happen in rapid succession, Server 3 might receive them out of order and cache the older value.
- Missed messages: if a server restarts mid-stream, it misses invalidation events that arrived during its downtime. It comes back with a stale in-process cache and no way to know what it missed.
- Mitigation for missed messages: combine with a short TTL (60 seconds) as a safety net. Even if an invalidation is missed, the stale value expires on its own.

---

### Solution 2: Version-Based Invalidation (lazy approach)

Instead of broadcasting when something changes, embed a **version number** in every cache key. On each read, the application checks the current version from a fast version store (Redis or a dedicated small DB table) before trusting the cached value.

```
Version-based Invalidation:

  Cache key format: user:{user_id}:v{version}
  Example: user:alice:v7  -->  { name: "Alice Smith", ... }

  Alice updates her profile:
    DB write: UPDATE users SET name='Alice Johnson', version=8 WHERE id=alice
    (No cache write needed. Just increment the version.)

  Next request for Alice's profile on any server:
    1. Read user_versions hash from Redis: HGET user_versions alice  --> "8"
    2. Check local cache for key "user:alice:v8"  --> MISS (we have v7)
    3. Fetch fresh data from DB
    4. Store in cache as "user:alice:v8"
    5. Old key "user:alice:v7" can be left to expire on its own
```

**Advantages**: no fan-out, no pub/sub infrastructure needed, no missed-message problem. Staleness is bounded to one version check.

**Disadvantages**: every cache read now requires an extra lookup to the version store. If the version store is Redis, that is one extra round-trip per request. For latency-sensitive paths this matters.

**Optimization**: store all versions in a single Redis Hash (`user_versions`). Instead of a separate round-trip, you can fetch the version as part of a Redis pipeline alongside other data, keeping the overhead sub-millisecond.

```
Redis Hash for versions:

  HGET user_versions alice   -->  "8"
  HGET user_versions bob     -->  "4"
  HGET user_versions carol   -->  "12"

  One small hash, one HGET per request, negligible overhead.
```

---

### Solution 3: Lease-Based Caching

A **lease** is a contract: "this cached value is valid until something specific happens, not just until a clock ticks." Facebook described this approach in their 2013 Memcached at Scale paper as a solution to two problems simultaneously: stale reads and cache stampedes.

When the cache stores a value, it also stores the **token** that was current at write time. Separately, a monotonically increasing global write counter tracks every mutation. On each cache read:

1. Read the cached value and its associated write token
2. Read the current global write counter
3. If the cached token equals the current counter, the value is fresh
4. If the cached token is older (lower), something changed — invalidate and refetch

```
Lease-Based Cache Flow:

  Global write counter stored in Redis: "write_counter" = 4721

  Cache entry for user:alice:
    { data: {...}, lease_token: 4721 }

  Alice updates her profile:
    DB write succeeds
    Redis: INCR write_counter  -->  4722

  Next read for user:alice:
    Read cache: { data: {...}, lease_token: 4721 }
    Read write_counter: 4722
    4721 < 4722 --> stale! Refetch from DB.
    Store: { data: fresh_data, lease_token: 4722 }

  Next read for user:bob (bob has not changed):
    Read cache: { data: {...}, lease_token: 4721 }
    Read write_counter: 4722
    --- Wait: bob's token is 4721, counter is 4722.
    --- That means SOMETHING changed, but maybe not bob.
    
    This is the weakness: a global counter creates false invalidations.
    Solution: per-key counters (more infrastructure) or accept the false miss rate.
```

The global counter version is simple but causes false cache misses whenever any key changes, even unrelated ones. Per-key version counters eliminate false misses but require a version-store entry per cached key, which brings you back to Solution 2. In practice, lease-based caching is most useful when write volume is low relative to read volume, and the exact token can be derived from the data itself (e.g., a `last_modified` timestamp from the DB row).

---

## 3. Cache Security (Deep Dive)

### Why security matters for caches

Most engineers think of Redis as an internal system protected by a firewall, not something that needs strong access controls. This assumption has repeatedly proven catastrophic.

In 2018, a security researcher used Shodan (an internet scanning tool) to find **72,000 Redis instances** with no authentication, bound to public IP addresses. Because Redis can execute `CONFIG SET dir /root/.ssh` and `CONFIG SET dbfilename authorized_keys` followed by `SET payload "ssh-rsa AAAA..."` and `BGSAVE`, an unauthenticated attacker can write their SSH public key into the root user's authorized keys file and gain full shell access to the server. This is not a theoretical attack — it was actively exploited in multiple major breaches.

Even in properly firewalled environments, a single compromised internal service with access to Redis can read every session token, impersonate any user, and modify any cached data to serve malicious content.

---

### Redis Security Checklist

**1. Network isolation**: bind Redis to the private network interface only.

In `redis.conf`:
```
bind 10.0.1.42 127.0.0.1
```
Never `bind 0.0.0.0` in production. That binds to all interfaces, including public ones.

**2. Authentication**: `requirepass` with a long random password.

```
requirepass Xk9!mPq2@vLn8$rTw5#yHj7^bNc3&dFz
```

32+ characters, randomly generated. Redis processes millions of commands per second, which means it can check millions of passwords per second. Short passwords are brute-forceable in minutes.

**3. ACLs (Redis 6+)**: per-user access control lists let you give each service only the commands and key patterns it actually needs.

```
# In redis.conf or via ACL SETUSER command:

ACL SETUSER session_service on >svc_password_here \
    ~session:* \
    +GET +SET +DEL +EXPIRE +TTL

ACL SETUSER analytics_service on >analytics_password_here \
    ~analytics:* \
    +GET +INCR +INCRBY +HGET +HSET

ACL SETUSER admin on >admin_password_here ~* +@all
```

The `session_service` user can only access keys that start with `session:` and can only run GET, SET, DEL, EXPIRE, and TTL. Even if this service is fully compromised, the attacker cannot read user data stored in other key prefixes, cannot run FLUSHALL, and cannot reconfigure Redis.

**4. TLS**: enable encrypted transport, especially for cross-datacenter Redis traffic.

```
tls-port 6380
port 0          # disable plain port entirely
tls-cert-file /etc/redis/redis.crt
tls-key-file  /etc/redis/redis.key
tls-ca-cert-file /etc/redis/ca.crt
```

**5. Rename or disable dangerous commands**: prevent accidental or malicious use of destructive operations.

```
# In redis.conf:
RENAME-COMMAND FLUSHALL  ""        # disabled entirely
RENAME-COMMAND FLUSHDB   ""        # disabled entirely
RENAME-COMMAND CONFIG    "XCONFIG_7f3k9p"   # renamed to secret name
RENAME-COMMAND DEBUG     ""        # disabled entirely
RENAME-COMMAND KEYS      ""        # disabled — use SCAN instead
```

**6. maxmemory**: always set a memory limit with an appropriate eviction policy.

```
maxmemory 4gb
maxmemory-policy allkeys-lru
```

Without this, a cache stampede or a runaway key generator can cause Redis to consume all available RAM, taking down the Redis host and potentially the rest of the services on that machine.

---

### Data Classification in Cache

Not all data belongs in a cache. The data classification question is asked at Staff-level interviews because it shows you understand compliance, security, and the trust model of your infrastructure.

| Data Type | Can Cache in Redis? | Can Cache in CDN? | Notes |
|-----------|--------------------|--------------------|-------|
| Session tokens | Yes, short TTL | Never | Session = authenticated context, must not be public |
| User display names | Yes | Only on public profiles | PII — CDN is fine for public data |
| Email addresses | Yes, internally | Never | PII, CDN is a public cache |
| Raw passwords | Never | Never | No reason to ever cache passwords |
| Password hashes | Never | Never | Unnecessary; DB lookup on auth is fine |
| Payment card numbers | Never (PCI-DSS) | Never | Out-of-scope for cache entirely |
| Health records | Only PCI/HIPAA zone | Never | HIPAA requires encryption at rest |
| JWT access tokens | Yes, to check revocation | Never | Short TTL matching token expiry |
| Encryption keys | Never | Never | Use a secret manager (Vault, KMS) |
| Rendered HTML pages | Yes | Yes, for public pages | Add Cache-Control: private for authenticated pages |

The most common interview trap is candidates saying "sure, cache everything for speed." The follow-up is: "what about a user's payment method, or their health history?" The right answer is a classification framework, not a blanket yes or no.

---

### Cache Poisoning Attacks

**Cache poisoning** is an attack where an adversary injects malicious content into a cache, so that all subsequent requests for that content receive the attacker's version.

**CDN host header poisoning**:

```
Normal request:
  GET /homepage HTTP/1.1
  Host: www.example.com

CDN caches the response under the key: www.example.com/homepage

Poisoning request:
  GET /homepage HTTP/1.1
  Host: www.example.com
  X-Forwarded-Host: evil-attacker.com

If the application uses X-Forwarded-Host to generate absolute URLs in the response:
  <a href="https://evil-attacker.com/login">Click here to log in</a>

CDN caches this poisoned response. Now every user visiting /homepage
sees links pointing to the attacker's phishing site.
```

**Prevention**: CDN must include only the canonical `Host` header in the cache key. The application must not trust `X-Forwarded-Host` for generating URLs without strict allowlist validation.

**Authenticated response poisoning**:

```
Scenario: Your CDN caches API responses but you forgot to add Vary: Authorization.

User A requests GET /api/profile  with Authorization: Bearer token_A
CDN cache: MISS. Fetches from origin. Gets User A's profile. Caches it.

User B requests GET /api/profile  with Authorization: Bearer token_B
CDN cache: HIT (same URL, no Vary header, so CDN ignores the auth header).
CDN returns User A's profile to User B.
```

**Prevention**: every response to an authenticated request must include `Cache-Control: private, no-store`. The `private` directive tells caches (CDN included) that this response is specific to one user and must not be stored in a shared cache. The `no-store` directive prevents it from being stored at all, even in a private cache.

---

## 4. Write-Path Failure Handling

### The problem: DB write succeeds, cache invalidation fails

The most common production bug pattern in caching systems:

```
Write path failure timeline:

  t=0    Application receives: update user 12345's email
  t=1ms  DB write: UPDATE users SET email='new@email.com' WHERE id=12345
           Status: SUCCESS. DB now has new email.
  t=2ms  Redis DEL user:12345
           Status: FAIL. Redis timeout (Redis is under load, slow response).
  t=2ms  Application returns 200 OK to the user.
           "Your email has been updated."

  t=30s  User opens profile in another browser tab.
  t=30s  Request hits a different app server.
           Cache HIT: user:12345 still has old email (TTL=5 minutes).
  t=30s  User sees their old email address despite just changing it.
  t=5min TTL expires, cache evicts old entry.
  t=5min+1ms  Next request fetches fresh data from DB.  Fixed.

  Impact: 5 minutes of stale data. Severity depends on the use case.
  For email: mildly annoying. For access control or inventory: potentially serious.
```

The severity scales with TTL length. A 5-second TTL means at most 5 seconds of stale data from a failed invalidation. A 24-hour TTL means a full day of stale data. This is one of the strongest arguments for keeping TTLs short.

---

### Defensive Write Pattern

The correct pattern does not let a cache invalidation failure cause the overall write request to fail. The DB write is the source of truth; the cache invalidation is a best-effort optimization. Fail the request if the DB write fails. Do not fail the request if the cache invalidation fails.

```python
def update_user_profile(user_id, data):
    # Step 1: Write to the source of truth.
    # If this fails, raise the exception — the write did not happen.
    db.execute(
        "UPDATE users SET name=?, email=? WHERE id=?",
        data['name'], data['email'], user_id
    )

    # Step 2: Try to invalidate the cache.
    # If this fails, log it and schedule a retry — do NOT fail the request.
    try:
        redis.delete(f"user:{user_id}")
    except RedisError as e:
        log.warning(
            "Cache invalidation failed",
            key=f"user:{user_id}",
            error=str(e)
        )
        # Push to an async retry queue
        retry_queue.push({
            "operation": "delete",
            "key":       f"user:{user_id}",
            "retry_at":  time.time() + 5,   # retry in 5 seconds
            "max_retries": 5
        })

    return {"status": "success"}
```

The key insight: the user's data is correct in the database immediately. The cache will either be invalidated now (best case) or within a few seconds via the retry queue (acceptable case) or after TTL expiry (worst case but bounded). None of these cases mean incorrect data was persisted — they only mean stale data was served briefly.

---

### Invalidation Queue Pattern

For high-volume systems where cache invalidation failures need durable tracking, use a dedicated invalidation queue:

```
Invalidation Queue Architecture:

  App Server
      |
      v
  DB Write (synchronous)
      |
      v
  Publish invalidation event to Kafka
  Topic: cache-invalidations
  Event: { key: "user:12345", op: "delete", ts: 1718400001234 }
      |
  (Returns success to user — Kafka publish is fast and durable)
      |
      v
  Kafka: cache-invalidations topic
      |
      v
  Cache Invalidation Worker (separate process, N replicas)
      |
      +---> Redis DEL user:12345
      |
      If Redis is down:
        Kafka consumer pauses. Events accumulate in Kafka.
        When Redis recovers, worker resumes. Processes backlog.
        No events lost — Kafka retains messages for 7 days.
```

**Why Kafka instead of a Redis List**: if Redis itself is down, you cannot write to a Redis List to track that Redis invalidations are failing. That is circular. Use an independent durable queue (Kafka, SQS, RabbitMQ) that is not Redis.

**Event ordering**: Kafka preserves order within a partition. Use `user_id` as the partition key so all invalidation events for the same user arrive in order. This prevents an older invalidation event from overwriting a newer one.

```
Without partition key ordering (dangerous):

  t=0   User updates name. Invalidation event 1 published.
  t=1ms User updates email. Invalidation event 2 published.
  t=2ms Worker processes event 2 first (different partition).
          Redis DEL user:12345. Fresh data loaded: name old, email new.
  t=3ms Worker processes event 1.
          Redis DEL user:12345. Fine here, but ordering issues can cause
          cache to hold version 1 data after version 2 data was already served.

With user_id partition key (safe):

  Events for user:12345 always go to partition 7.
  Worker for partition 7 processes them in order: event 1, then event 2.
  No ordering anomalies.
```

---

## 5. Testing Cache Behavior

### Unit Testing with a Mock Cache

Unit tests should not depend on a real Redis instance. A mock cache lets you test the caching logic (hit/miss/invalidation) in isolation, with no network calls and no setup.

```python
class MockRedis:
    """Minimal Redis mock for unit testing."""
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None, px=None, nx=False):
        if nx and key in self.store:
            return None    # NX: do not overwrite
        self.store[key] = value
        return True

    def delete(self, key):
        existed = key in self.store
        self.store.pop(key, None)
        return int(existed)

    def exists(self, key):
        return int(key in self.store)


def test_user_profile_cache_hit():
    cache = MockRedis()
    mock_db = MagicMock()
    mock_db.query.return_value = {"id": 123, "name": "Alice", "email": "alice@example.com"}

    service = UserService(cache=cache, db=mock_db)

    # First call: cache miss — should query DB and populate cache
    profile1 = service.get_user(123)
    assert profile1["name"] == "Alice"
    assert mock_db.query.call_count == 1

    # Second call: cache hit — should NOT query DB
    profile2 = service.get_user(123)
    assert profile2["name"] == "Alice"
    assert mock_db.query.call_count == 1   # still 1, not 2


def test_user_profile_invalidated_on_update():
    cache = MockRedis()
    mock_db = MagicMock()
    mock_db.query.return_value = {"id": 123, "name": "Alice"}

    service = UserService(cache=cache, db=mock_db)
    service.get_user(123)          # populates cache
    service.update_user(123, {"name": "Alice Johnson"})  # should invalidate

    # Cache should be empty now
    assert cache.get("user:123") is None

    # Next read should hit DB again
    mock_db.query.return_value = {"id": 123, "name": "Alice Johnson"}
    profile = service.get_user(123)
    assert profile["name"] == "Alice Johnson"
    assert mock_db.query.call_count == 2
```

---

### Integration Testing with a Real Cache

Some cache behaviors only manifest with a real Redis: pipeline execution order, Lua script atomicity, TTL behavior, and pub/sub delivery. Use **testcontainers** to spin up an actual Redis container for integration tests.

```python
import pytest
import time
import json
from concurrent.futures import ThreadPoolExecutor
from testcontainers.redis import RedisContainer

@pytest.fixture(scope="session")
def redis_client():
    """Start a real Redis container for the test session."""
    with RedisContainer("redis:7-alpine") as container:
        yield container.get_client()


def test_cache_stampede_prevention(redis_client):
    """
    Verify that only one DB call is made when many requests arrive
    simultaneously for a key that is about to expire.
    """
    db_call_counter = {"count": 0}
    lock = threading.Lock()

    def fake_db_fetch(user_id):
        with lock:
            db_call_counter["count"] += 1
        time.sleep(0.05)   # simulate DB latency
        return {"id": user_id, "name": f"User {user_id}"}

    service = UserService(
        cache=redis_client,
        db_fetch_fn=fake_db_fetch,
        lock_ttl_ms=500
    )

    # Pre-populate cache with a key about to expire
    redis_client.set("user:999", json.dumps({"id": 999, "name": "User 999"}), ex=1)
    time.sleep(0.95)  # almost expired

    # Fire 50 concurrent requests
    with ThreadPoolExecutor(max_workers=50) as pool:
        futures = [pool.submit(service.get_user, 999) for _ in range(50)]
        results = [f.result() for f in futures]

    # All 50 requests should return valid data
    assert all(r["name"] == "User 999" for r in results)

    # Only 1 DB call should have happened (lock prevented stampede)
    assert db_call_counter["count"] == 1, (
        f"Expected 1 DB call, got {db_call_counter['count']}. "
        "Stampede prevention is not working."
    )


def test_distributed_lock_mutual_exclusion(redis_client):
    """Verify that two concurrent lock attempts grant the lock to exactly one."""
    results = []
    lock_name = "test:exclusive:resource"

    def try_acquire():
        worker_id = str(uuid.uuid4())
        acquired = redis_client.set(lock_name, worker_id, nx=True, px=1000)
        results.append(bool(acquired))

    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = [pool.submit(try_acquire) for _ in range(20)]
        [f.result() for f in futures]

    # Exactly one attempt should have succeeded
    assert results.count(True) == 1
    assert results.count(False) == 19
```

---

### Chaos Testing for Cache

**Chaos testing** is deliberately breaking parts of your system to verify it degrades gracefully instead of catastrophically. For caching systems, three scenarios cover the most important failure modes.

**Scenario 1 — Redis shard failure**:

Kill one Redis node in a cluster. Verify:
- Traffic routes to replicas within a few seconds
- DB hit rate increases (expected — the cache is partially unavailable)
- Overall error rate stays below your SLA threshold
- The service does not crash, does not throw 500s to users, does not lock up

Tools: `kill -9` on the Redis process, or use a container orchestrator to stop the Redis pod.

**Scenario 2 — Slow Redis (latency injection)**:

Inject artificial latency (100-300ms) on all Redis responses. Verify:
- Circuit breaker opens after a configurable number of timeouts
- Traffic falls back to DB reads (with DB-level rate limiting to prevent DB overload)
- When Redis returns to normal, circuit breaker closes and caching resumes

Tool: **Toxiproxy** — a TCP proxy that sits between your application and Redis, with an API for injecting latency, jitter, packet loss, and connection resets at runtime.

```
With Toxiproxy:

  App Server ---> Toxiproxy (port 6380) ---> Redis (port 6379)

  Inject latency:
  curl -X POST http://toxiproxy:8474/proxies/redis/toxics \
    -d '{"name":"latency", "type":"latency", "attributes":{"latency":200}}'

  Now every Redis call takes 200ms extra.
  Watch your circuit breaker metrics in your APM tool.
```

**Scenario 3 — Cache cold start**:

Run `FLUSHALL` against the Redis cluster to simulate a complete cache loss (Redis restart after a crash, Redis failover with empty replica). Verify:
- DB load spikes sharply but does not exceed DB max connection limit
- Rate limiter and circuit breaker protect the DB from being overwhelmed
- Cache warms back up within a predictable time window
- No cascading failure (the DB spike should not cause the DB to slow down, causing more cache misses, causing more DB load — a feedback loop)

Monitor: DB query throughput, DB connection pool exhaustion, application p99 latency during the warm-up window.

---

## 6. Serialization Format Trade-offs in Cache

### Why serialization format matters at scale

Every cache read **deserializes** the stored bytes into a programming language object. Every cache write **serializes** a language object into bytes. This is pure CPU work — no DB, no network, just computation.

At low traffic (100 requests/second), this is invisible. At 100,000 requests/second, it is not. If JSON deserialization takes 100 microseconds per object, that is 10 CPU seconds per second of traffic — roughly 10 CPU cores dedicated entirely to JSON parsing. Switching to a binary format like Protobuf or MessagePack at the same throughput might cost 10-20 microseconds per object instead — a 5-10x reduction in serialization CPU usage.

```
Serialization CPU cost at 100,000 QPS:

  Format        Deser time    CPU cores for deser only
  --------      ----------    -------------------------
  JSON           ~100µs        ~10 cores
  MessagePack    ~30µs         ~3 cores
  Protobuf       ~15µs         ~1.5 cores
  Python pickle  ~50µs         ~5 cores (and insecure)
```

The numbers above are approximate and workload-dependent, but the relative ordering is consistent across benchmarks.

---

### Format Comparison

| Format | Wire size | Serialize speed | Deserialize speed | Human-readable | Schema enforcement | Safe for untrusted data |
|--------|-----------|-----------------|-------------------|----------------|--------------------|------------------------|
| JSON | Largest | Medium | Medium | Yes | No (flexible) | Yes |
| MessagePack | Medium (-30-50%) | Fast | Fast | No | No (flexible) | Yes |
| Protobuf | Smallest (-60-70%) | Fastest | Fastest | No | Yes (strict) | Yes |
| Avro | Small | Fast | Fast | No | Yes (registry) | Yes |
| Python pickle | Medium | Fast | Fast | No | No | **Never** |
| Java serialization | Large | Slow | Slow | No | No | **Never** |

**JSON**: default choice for teams that need debugging ease. You can `redis-cli GET user:123` and read the value directly. No tooling required. Flexible schema evolution — add fields freely, remove fields carefully. Downside: the largest payload size and slowest parse speed.

**MessagePack**: a drop-in binary replacement for JSON. Same data model (objects, arrays, strings, numbers), but binary encoded. No schema required. Roughly 20-30% smaller than JSON and 2-3x faster to parse. Good middle ground.

**Protobuf**: the highest-performance option with enforced schema. Fields are numbered (not named) in the wire format, which is how schema evolution works safely. Adding a new field with a new number is backward compatible. Removing a field is forward compatible (old readers see the default value). Requires a `.proto` schema file and a code generation step. Best choice for high-QPS systems where you can invest in the tooling.

**Python pickle / Java serialization**: never use these for cached data that any external process might read, or for data that comes from an external source. These formats execute arbitrary code during deserialization. If an attacker can write a crafted value into your Redis cache (via a cache poisoning attack, a compromised internal service, or a direct Redis access), deserializing it with pickle or Java serialization gives the attacker code execution on your server.

---

### The Schema Evolution Problem with Cached Data

Protobuf's schema evolution guarantees are well-understood for live RPC calls. They are less obviously applied to cached data, where objects written by version N of your code will be read by version N+1 after a deployment.

```
Schema Evolution with Cached Protobuf:

  v1 UserProfile proto:
    message UserProfile {
      int64 id = 1;
      string name = 2;
      string email = 3;
    }

  v2 UserProfile proto (new field added):
    message UserProfile {
      int64 id = 1;
      string name = 2;
      string email = 3;
      UserPreferences preferences = 4;  // NEW field
    }

  Deployment scenario:
    - Redis contains v1 objects (missing field 4)
    - New v2 code is being deployed (10-minute rolling deploy)
    - During deploy: half the fleet runs v1, half runs v2

  What happens when v2 code reads a v1 cached object?
    Field 4 (preferences) is absent in the bytes.
    Protobuf treats absent fields as their default value.
    preferences = null / empty message.
    v2 code must handle null preferences gracefully. (It should anyway.)
    SAFE.

  What happens when v1 code reads a v2 cached object?
    Field 4 exists in the bytes but v1 code has no definition for field 4.
    Protobuf silently ignores unknown fields.
    v1 code sees id, name, email as expected.
    SAFE.
```

The dangerous scenario is removing a field:

```
  v3 UserProfile proto (field removed):
    message UserProfile {
      int64 id = 1;
      string name = 2;
      // email removed
      UserPreferences preferences = 4;
    }

  Problem: v2 cached objects in Redis contain field 3 (email).
  v3 code reads them — Protobuf ignores field 3 (unknown field). Silently dropped.

  If v3 code then re-caches the object, the re-cached version has no email.
  Any v2 code still running reads the re-cached object and gets empty email.
  This can corrupt user-visible data if not handled carefully.

  Rule: Never remove a field number. Deprecate the field instead.
  In Proto3, mark it reserved:
    reserved 3;
    reserved "email";
  This prevents accidental reuse of field number 3 for a different field.
```

**The deployment window rule**: your cache TTL should be shorter than your deployment window if you are making schema changes. If deployment takes 10 minutes to complete (all servers running new code), and your cache TTL is 5 minutes, then by the time the last old-code server is replaced, all v1-schema objects in Redis have already expired. No old-schema objects remain for new code to misread.

```
TTL vs. deployment window:

  TTL: 5 minutes
  Deployment duration: 10 minutes

  t=0    Deploy starts. 50% of fleet on v1 code, 50% on v2.
  t=5min All objects cached before t=0 have expired.
         New objects are written by a mix of v1 and v2 code.
  t=10min Deploy complete. 100% of fleet on v2 code.
  t=15min All objects cached during the mixed phase (t=0 to t=10min) have expired.
          Redis now contains only v2-schema objects.
          Safe from this point forward.

  If TTL were 60 minutes:
  t=0    Deploy starts.
  t=10min Deploy complete.
  t=10min to t=60min: Redis still contains old v1-schema objects.
          v2 code reads them — safe only if schema change is backward-compatible.
          Any non-backward-compatible change causes errors for 50 more minutes.
```

The combination of short TTLs and backward-compatible schema changes (only add fields, never remove or repurpose field numbers) gives you safe deployments without cache flush operations.

---

## Summary of Staff-Level Caching Principles

The six topics in this section represent the gap between "I know Redis" and "I can design and defend a caching system at scale." Here is the condensed view:

**Distributed locking**: use `SET NX PX` with a unique worker ID and a Lua script for safe release. Use Redlock for multi-node safety in financial systems. Add fencing tokens when the storage layer must reject stale writes from workers whose locks expired mid-operation.

**Cache coherence**: choose between broadcast invalidation (fast but fan-out), version-based invalidation (no fan-out but extra lookup per read), and lease-based caching (sophisticated but eliminates stampedes simultaneously). Combine with short TTLs as a safety net for all three approaches.

**Cache security**: bind to private interfaces, require authentication, use ACLs to limit each service to its own key namespace and command set, disable destructive commands, and never cache PCI/HIPAA data outside compliant zones. Know the Cache-Control: private directive and when it is legally and architecturally required.

**Write-path failures**: never fail the user request because cache invalidation failed. Log, queue, and retry invalidations asynchronously. Use Kafka (not Redis) as the invalidation queue so a Redis outage does not prevent you from tracking that Redis needs to be invalidated.

**Testing**: mock caches for unit tests (fast, isolated), real Redis in containers for integration tests (accurate behavior), and deliberate chaos (latency injection, kill -9, FLUSHALL) to verify graceful degradation before it happens in production at 2am.

**Serialization**: use JSON for developer convenience, MessagePack or Protobuf when CPU or bandwidth is a constraint. Never use pickle or Java serialization for cached data. Keep TTLs shorter than deployment windows when making schema changes.
# Chapter 31 — Supplement C: Caching at Scale
### Migration Strategies, Cost Optimization, Cross-Team Standards, and Interview Calibration

> "The difference between an L5 and an L6 isn't knowing Redis commands. It's knowing what happens when Redis dies, what it costs, and how to keep three teams from destroying each other's data."

---

## Table of Contents

1. Cache Migration Strategies
2. Cache Rollback and Canary Deployments
3. Cache Cost Optimization
4. Cross-Team Cache Standards
5. Interview Calibration: Caching Discussion
6. Self-Assessment Rubric
7. Visual Summary: Chapter 31 in One Picture

---

## 1. Cache Migration Strategies

### The Problem: You Cannot Move 50 Million Sessions at Once

Imagine you have a grocery store that has been using one type of shelf labeling system for five years. You want to switch to a better system. But you cannot close the store for a weekend to relabel everything — the store is open 24/7 and customers are always shopping. If you tear down all the old labels at midnight Saturday, Sunday morning customers cannot find anything.

That is exactly the cache migration problem.

In technical terms: you have **Memcached** running in production. It holds 50 million active user sessions. You want to migrate to **Redis** because Redis supports persistence (sessions survive a restart), richer data structures, and Redis Cluster for horizontal scaling. The problem is you cannot do this all at once. If you delete all sessions from Memcached and move to an empty Redis cluster, every single user gets logged out instantly. For a consumer app, that is a catastrophic user experience event and likely a revenue incident.

You need **zero-downtime migration** — a process where at no point does the service degrade, and at any point in the migration you can safely roll back.

The core challenge has three parts:

1. **Data consistency**: old system and new system must agree on values during the transition.
2. **Traffic continuity**: users must not experience errors or logouts during the move.
3. **Rollback safety**: if anything goes wrong at any phase, you must be able to go back.

---

### Strategy 1: Shadow Traffic (Write to Both, Read from New Gradually)

This is the most careful strategy. Think of it like making a photocopy of every document as it gets updated, building a parallel filing cabinet, then eventually switching to reading from the new cabinet.

The migration happens in four phases:

```
TIME ──────────────────────────────────────────────────────────────────────────►

WEEK 1-2         WEEK 3-4              WEEK 5-6         WEEK 7-8
┌──────────────┐ ┌──────────────────┐ ┌──────────────┐ ┌─────────────────────┐
│ PHASE 1      │ │ PHASE 2          │ │ PHASE 3      │ │ PHASE 4             │
│ Dual Write   │ │ Shadow Read      │ │ Flip Reads   │ │ Decommission        │
│              │ │                  │ │              │ │                     │
│ SET → both   │ │ Read Memcached   │ │ Read Redis   │ │ Stop writing        │
│ DEL → both   │ │ Read Redis too   │ │ Write both   │ │ to Memcached        │
│ Read: MC only│ │ Compare results  │ │ still        │ │                     │
│              │ │ Log diffs        │ │              │ │ Decommission MC     │
└──────────────┘ └──────────────────┘ └──────────────┘ └─────────────────────┘
     │                  │                    │                    │
     ▼                  ▼                    ▼                    ▼
  MC: source        MC: source           Redis: source       Redis: only
  Redis: copy       Redis: shadow        MC: safety net      copy
```

**Phase 1 — Dual Write (Weeks 1-2)**

Every write operation goes to both Memcached and Redis simultaneously. Your application code changes from:

```python
# Before migration
def set_session(session_id, data, ttl=86400):
    memcached.set(session_id, serialize(data), expire=ttl)

def get_session(session_id):
    return deserialize(memcached.get(session_id))
```

```python
# Phase 1: Dual write
def set_session(session_id, data, ttl=86400):
    serialized = serialize(data)
    memcached.set(session_id, serialized, expire=ttl)
    try:
        redis.setex(session_id, ttl, serialized)
    except RedisError as e:
        # Redis failure is non-fatal in Phase 1
        log.warning("Redis shadow write failed: %s", e)

def get_session(session_id):
    # Still reading from Memcached in Phase 1
    return deserialize(memcached.get(session_id))
```

Redis failures are non-fatal here. The authoritative system is still Memcached. Redis is just being populated. Reads still go to Memcached.

**Phase 2 — Shadow Read (Weeks 3-4)**

Now you read from both systems and compare. You do not change what value you return to the user (still Memcached), but you log any discrepancy.

```python
# Phase 2: Shadow read
def get_session(session_id):
    mc_value = memcached.get(session_id)
    try:
        redis_value = redis.get(session_id)
        if mc_value != redis_value:
            log.warning("SHADOW_MISMATCH key=%s", session_id)
            metrics.increment("cache.shadow.mismatch")
    except RedisError:
        pass
    return deserialize(mc_value)  # Still return Memcached value
```

Your target: get the mismatch rate below **0.01%**. At 50 million keys, 0.01% is 5,000 keys — those are 5,000 sessions you need to investigate and fix before switching reads over. Common causes of mismatches:

- **Serialization differences**: Memcached client used Python pickle protocol 2, Redis client defaults to protocol 5. Pickled objects are not cross-compatible.
- **Timezone differences**: a session timestamp stored as a naive datetime in Memcached, a timezone-aware datetime in Redis.
- **Encoding differences**: Memcached client stores strings as bytes, Redis client stores as UTF-8 strings.
- **Race conditions**: a write happened between the Memcached read and Redis read, so values genuinely differ momentarily.

Fix each class of mismatch. Do not move to Phase 3 until you have been under 0.01% for 72 consecutive hours.

**Phase 3 — Flip Reads (Weeks 5-6)**

Change the primary read to Redis. Keep writing to both as a safety net.

```python
# Phase 3: Reads from Redis, writes to both
def get_session(session_id):
    redis_value = redis.get(session_id)
    if redis_value is None:
        # Cache miss in Redis — fall back to Memcached
        mc_value = memcached.get(session_id)
        if mc_value:
            redis.setex(session_id, DEFAULT_TTL, mc_value)  # backfill
            return deserialize(mc_value)
        return None
    return deserialize(redis_value)
```

Monitor the Redis hit rate. In the first days it may be 75-85% as old sessions expire from Memcached and get replaced with new writes that go to both. Over time it climbs to 95%+.

**Phase 4 — Decommission (Weeks 7-8)**

Stop writing to Memcached. Monitor for any anomalies for one full week. Then shut down the Memcached cluster.

**Downsides of Shadow Traffic**: you pay double write cost for 6 weeks. Your code is more complex during migration. The migration requires two production deploys (Phase 1→2 and Phase 3→4). But it is the safest strategy for high-stakes data like sessions.

---

### Strategy 2: Blue-Green Cache

**Blue-Green deployment** is a classic zero-downtime deployment technique: you spin up an identical new environment (Green), warm it up, then switch traffic over. The old environment (Blue) stays alive as a rollback option.

For caches, it works like this:

```
                         FEATURE FLAG / TRAFFIC SPLITTER
                                      │
              ┌───────────────────────┴───────────────────────┐
              │                                               │
              ▼                                               ▼
    ┌─────────────────┐                           ┌─────────────────┐
    │   BLUE          │                           │   GREEN         │
    │   (Memcached)   │                           │   (Redis)       │
    │   Original      │                           │   New Cluster   │
    │   cluster       │                           │   (warming up)  │
    └─────────────────┘                           └─────────────────┘

    Week 1:  99% reads ──────────────────────────► Blue
             1% reads  ─────────────────────────────────────────────► Green
    Week 2:  95% Blue / 5% Green
    Week 3:  75% Blue / 25% Green
    Week 4:  0% Blue / 100% Green
    Week 5:  Blue kept alive for rollback
    Week 6:  Blue decommissioned
```

**Warming up Green**: before sending any production traffic, run a background job that copies data from Blue to Green:

```python
def warm_green_cache():
    """
    Background job: scan Memcached (Blue) and copy all keys to Redis (Green).
    Runs continuously until traffic cutover is complete.
    """
    cursor = 0
    while True:
        # Memcached does not support SCAN natively — use a key tracker
        # or use a proxy like mcrouter that supports key enumeration
        batch = memcached_proxy.scan_keys(count=1000)
        for key in batch:
            value = memcached.get(key)
            ttl = memcached.get_ttl(key)
            if value and ttl > 60:  # Only copy keys with >60s remaining
                redis.setex(key, ttl, value)
        if len(batch) < 1000:
            break  # Done with initial pass, continue monitoring new writes
        time.sleep(0.01)  # Avoid overwhelming source cluster
```

The traffic splitter is usually a feature flag evaluated per request:

```python
def get_session(session_id):
    user_bucket = hash(session_id) % 100  # 0-99
    green_percentage = feature_flags.get("redis_green_percentage")  # starts at 1

    if user_bucket < green_percentage:
        return redis.get(session_id)   # Green
    else:
        return memcached.get(session_id)  # Blue
```

**Monitoring during ramp**: at each percentage step, wait 24 hours and check:
- Green hit rate (should be climbing as more writes go to Green)
- Error rate on Green vs Blue (should be equal)
- Latency p99 on Green vs Blue (should be equal or better)

**Rollback**: drop the feature flag percentage back to 0. All traffic goes to Blue. Green is discarded and re-warmed if you retry the migration.

---

### Anti-Patterns to Avoid During Migration

**Anti-Pattern 1: The Big Bang Cutover**

"We'll migrate everything on Saturday night at 2 AM." This means: if anything goes wrong, rolling back requires re-migrating 50 million sessions back to the old system. That takes hours. Hours of downtime. Never do this with stateful data.

**Anti-Pattern 2: Skipping Shadow Reads**

Assume the new cache is correct without comparing. At 50 million keys, a 3% discrepancy rate is 1.5 million corrupted sessions. You will not discover this until production traffic starts getting errors. Shadow reads are boring and slow, but they catch real bugs.

**Anti-Pattern 3: Rushing the Warm-Up**

Send production traffic to the new empty cache before it has enough data. Your hit rate starts at 0%. Every request is a cache miss. Every miss hits the database. If your database handles 5,000 requests per second normally and you suddenly send 50,000 requests per second (the other 90% are now misses), you have caused a database outage as part of your "migration."

**Real Incident (serialization trap)**

A mid-size e-commerce company migrated 12 million user sessions from Memcached to Redis over one weekend. They had tested in staging. They had run shadow reads in staging. What they missed: staging used Python 3.7 everywhere, which defaulted to pickle protocol 4. Production still had a mix of Python 3.6 servers (pickle protocol 2 max) and Python 3.8 servers (pickle protocol 5 default).

When they flipped reads to Redis, the Python 3.6 app servers could not deserialize sessions pickled by Python 3.8 (which had written them to Redis). Result: 12 million sessions unreadable. Every user got logged out. They rolled back Sunday night (back to Memcached) and spent the following week standardizing pickle protocol version across all app servers before re-migrating.

The fix was one line: `pickle.dumps(data, protocol=2)`. The lesson: serialization compatibility must be tested across every app server Python version in production, not just staging.

---

### Memcached to Redis: Real Migration Timeline

```
WEEK    ACTION                              WHAT TO WATCH
──────  ──────────────────────────────────  ──────────────────────────────────────
Week 1  Deploy Redis alongside Memcached    Redis cluster healthy, dual writes
        Write to both, read from Memcached  working, no errors

Week 2  Enable shadow reads                 Mismatch rate: starts at 2.1%
        Fix discrepancies found:            Found: timezone serialization diff
        - Timezone in Python datetime       Fixed with normalize_datetime() util
        Mismatch falls to 0.008%            Below 0.01% threshold — proceed

Week 3  Route 10% reads to Redis            Redis hit rate: 67% (warming up)
        Monitor for 48h                     No errors; latency Redis < Memcached

Week 4  50% reads to Redis                  Redis hit rate: 85% (mostly warmed)
        DB load unchanged                   DB at normal levels — good sign

Week 5  100% reads to Redis                 Redis hit rate: 94%
        Disable Memcached writes            Memcached cluster still up (safety)

Week 6  Decommission Memcached cluster      Save: $1,400/month
        On-call incidents:                  Before: 8/month
        sessions-related                    After: 1/month (persistence = no
                                            lost sessions on Redis restart)
```

---

## 2. Cache Rollback and Canary Deployments

### What Can Go Wrong with Cache Changes

People think of "deployments" as application code changes. But changes to your **cache configuration** are equally risky deployments, and they can fail in subtle ways that are harder to diagnose.

**Problem 1: Changing TTL**

Reduce user session TTL from 1 hour to 5 minutes (a product decision: "keep sessions fresher"). Effect: sessions that were sitting safely in Redis for 45 minutes now expire in 5 minutes. Suddenly the volume of cache misses increases **12×** (from 1/hour to 12/hour per session). Your database query rate spikes from 5,000 QPS to 60,000 QPS. Your database is sized for 10,000 QPS. You have caused a database outage with a one-line config change.

**Problem 2: Changing Key Schema**

Old code used `user:{id}` as the cache key. New code uses `u:{id}:{version}` (you added a version for cache busting). On deploy, every app server is now looking for `u:{id}:{version}` in Redis. None of those keys exist — the cache was full of `user:{id}` entries. **100% cache miss** on deploy. Every request hits the database simultaneously. This is the cold start / thundering herd problem.

**Problem 3: Changing Eviction Policy**

You switch from `allkeys-lru` (evict least recently used) to `allkeys-lfu` (evict least frequently used). For your workload, there are many keys accessed exactly once (search result pages). LFU will keep those longer than LRU would. Net effect: your most frequently-accessed keys start getting evicted to make room for rarely-accessed keys. Hit rate drops. DB load rises. The issue is invisible until you check `INFO stats` and see evicted_keys spiking.

**Problem 4: Changing Serialization**

You migrate cached API responses from JSON to Protobuf for size savings. On deploy, new code writes Protobuf. Old cached values are JSON. New code calls `proto.ParseFromString(redis.get(key))` — and crashes because it is trying to parse JSON as Protobuf. Every cache hit becomes an error until all old JSON entries expire.

---

### Canary Deployment for Cache Changes

A **canary deployment** is like sending one miner into the mine with a canary bird before sending the whole crew. If the canary dies, the crew stays out. In software, you deploy to 1% of servers first, watch for problems, then proceed.

```
                       PRODUCTION: 100 APP SERVERS
                       ┌─────────────────────────────┐
                       │                             │
        ┌──────────────┴──────────────┐              │
        │       CANARY (1 server)     │   BASELINE (99 servers)
        │                             │              │
        │  New cache config:          │   Old cache config:
        │  - key prefix "u:{id}:v2"   │   - key prefix "user:{id}"
        │  - TTL 5 min                │   - TTL 60 min
        │  - LFU eviction             │   - LRU eviction
        └──────────────┬──────────────┘              │
                       │                             │
                       ▼                             ▼
                  ┌────────────────────────────────────┐
                  │         SHARED REDIS CLUSTER        │
                  │   (both key patterns coexist safely │
                  │    because they use diff prefixes)  │
                  └────────────────────────────────────┘

MONITOR FOR 24h:
  cache hit rate:   canary vs baseline    (should be similar after warm-up)
  DB hit rate:      canary vs baseline    (canary should NOT be higher)
  error rate:       canary vs baseline    (canary should be ≤ baseline)
  latency p99:      canary vs baseline    (canary should be ≤ baseline)
```

Only if all four metrics look equivalent do you proceed to 10% → 50% → 100%.

Key trick: use **different key prefixes** for canary vs baseline when testing key schema changes. This lets both old and new key formats coexist in the same Redis cluster during the canary period without interference. Old servers read `user:{id}`, new servers read `u:{id}:v2`, both exist in Redis. When canary is validated and you go to 100%, the old `user:{id}` keys expire naturally (TTL) or you run a background cleanup job.

---

### Rollback Strategies by Change Type

| Change Type | Rollback Difficulty | Rollback Strategy | Risk If You Skip Canary |
|---|---|---|---|
| TTL reduction | Easy | Redeploy with old TTL value | DB overload from miss rate spike |
| TTL increase | Low | Redeploy with old TTL | Stale data served for longer |
| Key schema change | Medium | Deploy old code; old keys still in Redis | 100% miss rate on deploy |
| Eviction policy change | Easy | Change redis.conf, reload | Wrong keys evicted, hit rate drop |
| Serialization format | Hard | Must support both formats until old entries TTL expire | Deserialization errors on all hits |
| Cluster topology | Hard | Keep old cluster alive for ≥1 max-TTL period | Split-brain, data loss |

**Serialization rollback in detail** (because it is the nastiest):

```python
# Dual-format deserializer during rollback window
def get_cached_object(key):
    raw = redis.get(key)
    if raw is None:
        return None

    # Try new format first (Protobuf)
    try:
        return MyProtoMessage.FromString(raw)
    except Exception:
        pass

    # Fall back to old format (JSON)
    try:
        data = json.loads(raw.decode("utf-8"))
        # Optionally re-cache in new format to speed up migration
        redis.setex(key, DEFAULT_TTL, MyProtoMessage(**data).SerializeToString())
        return data
    except Exception:
        return None  # Corrupted entry — treat as miss
```

You maintain this dual-format reader until all old JSON entries have expired (max one full TTL cycle). Then remove the JSON fallback path.

---

## 3. Cache Cost Optimization

### Understanding What Actually Costs Money

Before optimizing, you need to know what you are paying for. Cache cost has four components, and most engineers only think about the first one.

```
REDIS COST BREAKDOWN (typical $10K/month Redis spend):

  ┌────────────────────────────────────────────────────────────────┐
  │                                                                │
  │  Memory (instance cost)                         $6,200 (62%)  │
  │  ████████████████████████████████████░░░░░░░░                 │
  │                                                                │
  │  Network (cross-AZ data transfer)               $1,800 (18%)  │
  │  █████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░                │
  │                                                                │
  │  Operations (monitoring, on-call time)          $1,600 (16%)  │
  │  ████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░                 │
  │                                                                │
  │  CPU (Redis per-shard compute)                    $400  (4%)  │
  │  ███░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░                │
  └────────────────────────────────────────────────────────────────┘
```

100 GB Redis on AWS ElastiCache runs approximately three `r6g.2xlarge` nodes (for primary + 2 replicas) at ~$400/month each = **$1,200/month for memory alone**. At enterprise scale (1 TB), this is $12,000/month, which gets attention from finance.

---

### Optimization 1: Right-Size Your TTLs

TTL is the most overlooked cost lever. The relationship between TTL and cost is indirect but real: shorter TTL = more cache misses = more DB queries = larger DB needed = more cost.

**Quantifying the tradeoff**:

```
Scenario: 100,000 requests/second, product catalog cache

TTL = 1 hour:
  Hit rate = 95%  (product updates are rare, 1h is almost always fresh enough)
  Cache misses per second = 100,000 × 5% = 5,000/sec hitting DB
  DB needs to handle: 5,000 QPS

TTL = 5 minutes:
  Hit rate = 70%  (many short-lived caches expire, causing re-fetches)
  Cache misses per second = 100,000 × 30% = 30,000/sec hitting DB
  DB needs to handle: 30,000 QPS

Cost impact:
  DB for 5K QPS:  2× RDS db.r6g.xlarge   = $400/month
  DB for 30K QPS: 4× RDS db.r6g.4xlarge  = $6,400/month
  Difference: $6,000/month extra DB cost to support the shorter TTL
  This must be weighed against the value of "fresher" data
```

Before shortening a TTL, ask: is my database sized for the increased miss rate? If not, either keep the longer TTL or scale the DB first.

**Staggering TTLs to prevent avalanche**: if you set TTL = 3600 for all user profiles, and they all got cached at roughly the same time (say, after a deploy that emptied the cache), they all expire at roughly the same time — and you get a thundering herd. The fix is simple:

```python
def cache_user_profile(user_id, profile_data):
    # Base TTL + random jitter of up to 5 minutes
    import random
    ttl = 3600 + random.randint(0, 300)
    redis.setex(f"user:{user_id}", ttl, serialize(profile_data))
```

The random jitter of 0-300 seconds spreads expirations over a 5-minute window instead of hitting simultaneously.

---

### Optimization 2: Compress Cached Values

Think of compression like vacuum-sealing food in your freezer. The original food (data) takes the same amount of space if you store it loose, but vacuum-sealed it takes 25% of the space. The vacuum sealing takes a few seconds of effort (CPU time for compression), but you fit 4× as much in your freezer (Redis memory).

**The math**:

```
Without compression:
  1,000,000 product catalog entries
  × 10 KB average value size (JSON with descriptions, images URLs, metadata)
  = 10 GB Redis memory needed
  = 3× r6g.2xlarge nodes
  = $1,200/month

With gzip compression (typical 4× ratio for JSON):
  10 GB ÷ 4 = 2.5 GB Redis memory needed
  = 1× r6g.xlarge node
  = $400/month

Savings: $800/month
CPU cost of compression: ~5 microseconds per call
  At 100K RPS: 100,000 × 5µs = 0.5 CPU-seconds per second = 0.5 CPU cores
  Cost of 0.5 CPU cores: ~$20/month
Net saving: $780/month
```

**Implementation**:

```python
import gzip
import json

def cache_set(key, value, ttl):
    serialized = json.dumps(value).encode("utf-8")
    # Only compress if value is large enough to benefit
    if len(serialized) > 100:
        compressed = gzip.compress(serialized, compresslevel=6)
        redis.setex(key, ttl, b"gz:" + compressed)
    else:
        redis.setex(key, ttl, serialized)

def cache_get(key):
    raw = redis.get(key)
    if raw is None:
        return None
    if raw.startswith(b"gz:"):
        return json.loads(gzip.decompress(raw[3:]))
    return json.loads(raw)
```

**When NOT to compress**: values smaller than 100 bytes. The gzip header alone is ~18 bytes, and the compressed output is often larger than the input for very small values. You pay CPU cost and get negative benefit.

Also avoid compressing values that are already compressed (JPEG images, ZIP files, already-gzipped content). You will use CPU and get 0% size reduction.

---

### Optimization 3: Tiered Caching (The Biggest Cost Lever)

The most powerful optimization is recognizing that **not all data deserves the same cache tier**. Redis is expensive per GB because it is fast, in-memory, and highly available. But most of your data does not need all three of those properties at full strength.

Think of it like office storage: your most important documents stay on your desk (expensive prime space, instantly accessible). Frequently-referenced documents go in a filing cabinet (cheaper, one room away). Archived documents go in a warehouse (very cheap, takes effort to retrieve).

```
TIERED CACHE ARCHITECTURE

  ACCESS          TIER             SYSTEM           COST/GB/MONTH
  FREQUENCY       ─────────────    ──────────────    ─────────────
  > 100×/day      Tier 1 (Hot)     Redis             $15-25/GB
  10-100×/day     Tier 2 (Warm)    Memcached         $8-12/GB
  < 10×/day       Tier 3 (Cold)    S3 / Disk         $0.02-0.03/GB
  < 1×/day        No cache         DB direct         N/A

  ┌─────────────────────────────────────────────────────────────┐
  │  REQUEST                                                    │
  │     │                                                       │
  │     ▼                                                       │
  │  ┌──────────┐  miss  ┌──────────┐  miss  ┌──────────┐      │
  │  │  Redis   │──────► │Memcached │──────► │   S3     │      │
  │  │  (hot)   │        │  (warm)  │        │  (cold)  │      │
  │  └──────────┘        └──────────┘        └──────────┘      │
  │     hit: ~1ms          hit: ~2ms           hit: ~50ms       │
  │     │                     │                    │           │
  │     └─────────────────────┴────────────────────┘           │
  │                           │                                 │
  │                           ▼                                 │
  │                    RETURN TO CLIENT                         │
  │                    + promote to hotter tier if needed       │
  └─────────────────────────────────────────────────────────────┘
```

**Real example — E-commerce product catalog (50 million products)**:

Analysis showed access frequency was extremely skewed (Pareto distribution):
- Top 100,000 products (0.2% of catalog): accessed 500+ times/day each
- Next 1,000,000 products (2%): accessed 10-100 times/day
- Remaining 49,000,000 products (97.8%): accessed < 5 times/day

**Before tiering**: All 50M products cached in Redis. 200 GB Redis. $4,800/month.

**After tiering**:
- Top 100K products × 2KB each = 200MB in Redis (24h TTL). Cost: $5/month.
- Next 1M products × 2KB each = 2GB in Memcached (1h TTL). Cost: $25/month.
- Bottom 49M products: no cache. DB query takes 15ms but happens rarely enough that it is acceptable.

**Total cache cost after: $30/month. Savings: $4,770/month.**

The DB handles slightly more load from the uncached long tail, but that long tail was being accessed rarely enough that the DB handled it fine.

---

### Optimization 4: Eviction Policy Tuning

When Redis runs out of memory and needs to evict something to make room for new data, the **eviction policy** determines what gets deleted. Choosing the wrong one silently kills your hit rate.

```
EVICTION POLICIES AND WHEN TO USE THEM

  Policy            What It Does                      Best For
  ────────────────  ────────────────────────────────  ─────────────────────────
  allkeys-lru       Evict least recently used         General purpose caches
                    among ALL keys                    (most common choice)

  volatile-lru      Evict least recently used         When some keys MUST
                    only among keys WITH a TTL        never be evicted (no TTL)

  allkeys-lfu       Evict least frequently used       Skewed access patterns
                    among ALL keys                    (some keys accessed rarely)

  volatile-lfu      Evict least frequently used       Combination of above
                    only among keys WITH a TTL

  allkeys-random    Evict a random key                Almost never the right choice

  noeviction        Return error when memory full     Only for queues where
                                                      data loss is unacceptable
```

**Memory management best practice**:

```
redis.conf:
  maxmemory 80gb           # Set to 80% of instance RAM
  maxmemory-policy allkeys-lru

Alert thresholds:
  70% memory usage → alert: "Redis memory at 70%, review key sizes"
  80% memory usage → alert: "Redis memory at 80%, scale up within 48h"
  90% memory usage → URGENT: "Redis at 90%, evictions occurring NOW"
```

**Monitoring evictions**:

```bash
redis-cli INFO stats | grep evicted_keys
# evicted_keys:0        <- healthy, no evictions occurring
# evicted_keys:45230    <- unhealthy, 45K keys evicted since restart
```

If evicted_keys is non-zero and growing, your cache is undersized. Either reduce the data you store, compress values, or scale up the cluster.

---

### The Two Actual Cost Drivers Staff Engineers Track

**Driver 1: Memory waste from unused keys**

You cached 5 million product recommendations 6 months ago. The recommendation algorithm changed. The old keys are still in Redis, taking up memory, but they never get accessed. They have a TTL of 7 days, so they do eventually expire — but they are being refreshed by a background job that still runs. You are paying for 5 million keys that serve zero user requests.

Fix: instrument access frequency per key pattern using Redis keyspace notifications or a proxy layer, then audit keys with zero hits in the past 30 days.

**Driver 2: Cross-AZ network costs**

AWS charges $0.01 per GB for data transfer between Availability Zones within the same region. For a high-traffic service, this adds up fast:

```
Example: 500K requests/second, each Redis GET returns 2KB
Data transferred per second: 500,000 × 2KB = 1 GB/second
Cross-AZ transfer if app servers are in different AZ than Redis:
  1 GB/s × 3600s × 24h × 30 days = 2,592 TB/month
  × $0.01/GB = $25,920/month in JUST network transfer costs

Fix: configure Redis client to prefer same-AZ replicas for reads
  Client reads go to same-AZ replica: ~0 cross-AZ cost
  Only writes and replica sync go cross-AZ: ~10× less traffic
  Savings: ~$23,000/month
```

Most Redis client libraries support `preferred_availability_zone` configuration. This is one of the highest-ROI configuration changes a Staff Engineer can make.

---

## 4. Cross-Team Cache Standards

### Why Standards Matter (A Story About Key Collisions)

Imagine three roommates sharing one refrigerator with no labeling rules. Roommate A puts their leftovers in an unlabeled container. Roommate B throws away what they think is old food — it was Roommate A's lunch. Roommate C uses the same container Roommate A uses for leftovers to store their meal prep. Chaos.

That is exactly what happens when three engineering teams share a Redis cluster with no key naming standards.

**Real collision scenario**:
- Team A (sessions): stores distributed locks as `lock:user:{id}` when a user is editing their profile
- Team C (background jobs): stores distributed locks as `lock:user:{id}` when a background job processes a user event

Both teams use the same key format. When Team C's background job deletes `lock:user:12345` after finishing its work, it is simultaneously deleting Team A's session lock that user 12345 is still actively holding. The user's profile edit now has no lock, another request comes in, and the profile gets corrupted by a race condition.

This happened. The incident took four hours to diagnose because the symptoms (occasional profile corruption) had no obvious connection to background job processing.

---

### The Cache Standards Document

A platform team should own and publish a cache standards document. Below is a realistic example:

```
CACHE STANDARDS v2.1
Published by: Platform Engineering
Last Updated: 2025-Q3
Applies to: All services using shared Redis clusters

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

KEY NAMING CONVENTION
Format: {service}:{entity}:{id}[:{sub-field}]

Approved examples:
  userservice:user:12345                    — user profile
  userservice:session:{uuid}                — user session
  productservice:product:67890              — product catalog entry
  productservice:search:{query_hash}        — search result page
  orderservice:order:99999                  — order detail
  orderservice:cart:{user_id}               — shopping cart
  searchservice:suggest:{prefix}            — autocomplete suggestions

Prohibited patterns:
  - Keys without a service prefix (e.g., "user:12345" — which team?)
  - Keys longer than 128 bytes (Redis key memory overhead matters)
  - Keys containing user PII (e.g., "user:jane@example.com" — use ID)
  - Generic keys like "temp", "test", "debug" in production

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TTL POLICY
  - ALL keys MUST have a TTL. Keys without TTL are a memory leak.
  - Approved TTL ranges by data type:

    Sessions:              86400      (24 hours)
    User profiles:         3600       (1 hour)
    Product catalog:       3600       (1 hour)
    Search results:        300        (5 minutes)
    Config/feature flags:  300        (5 minutes)
    Distributed locks:     ≤ 30       (30 seconds max)

  - No key may have TTL > 604800 (7 days) without platform review.
  - Use TTL jitter: add random(0, TTL*0.1) to prevent avalanche.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MEMORY QUOTAS
  Each service is allocated a keyspace with a memory quota:
    Tier 1 (session-critical): 50 GB reserved
    Tier 2 (general purpose):  shared pool, fair-share eviction
    Tier 3 (best-effort):      shared pool, first evicted under pressure

  Quota enforcement:
    At 80% of quota: alert fires, service team is paged
    At 100%: keys evicted (allkeys-lru), alert escalates to on-call

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PROHIBITED COMMANDS (enforced via ACL)
  KEYS *        — use SCAN with cursor instead; KEYS * blocks Redis
  FLUSHDB       — deletes all keys in the database; use targeted DEL/SCAN
  FLUSHALL      — deletes all keys on the server; catastrophic
  DEBUG         — can crash Redis; reserved for platform team
  CONFIG SET    — can change cluster behavior; reserved for platform team
  EVAL (Lua)    — allowed only with platform review; can block Redis

REQUIRED ACL FOR SERVICE ACCOUNTS:
  ~{service}:*    — keyspace restricted to service's prefix
  +GET +SET +DEL +EXPIRE +TTL +SCAN +HGET +HSET +ZADD +ZRANGE
  -KEYS -FLUSHDB -FLUSHALL -DEBUG -CONFIG
```

---

### Who Owns What

A common source of organizational friction is unclear ownership. The following table prevents arguments:

```
RESPONSIBILITY MATRIX

  Domain                                   Owner
  ───────────────────────────────────────  ──────────────────────────────
  Redis cluster provisioning               Platform / Infra Team
  Redis version upgrades and patching      Platform / Infra Team
  HA configuration (sentinel / cluster)    Platform / Infra Team
  Monitoring dashboards                    Platform / Infra Team
  Capacity planning (memory sizing)        Platform / Infra Team

  What to cache (business logic)           Service Team
  Key naming (within standards)            Service Team
  Cache invalidation logic                 Service Team
  TTL selection (within approved ranges)   Service Team
  Hit rate targets for their service       Service Team

  Data classification policy               Security Team
  PII-in-cache rules                       Security Team
  Encryption requirements                  Security Team
  Audit logging for cache access           Security Team
```

The platform team does not decide what the user service caches. The user service team does not provision Redis nodes. The security team sets the rules that everyone else follows.

---

### When Cache Becomes a Platform Service

At some scale, informal cache ownership breaks down. The trigger is usually: **three or more teams sharing a Redis cluster with different availability requirements**.

The problem: Team A (sessions) needs 99.99% availability. If their users get logged out, it is a major incident. Team B (search suggestions) is fine with 99.5% — if autocomplete breaks for an hour, nobody calls the CEO. If they share a cluster, Team A's SLA is impossible to guarantee because Team B's bad query (a `KEYS *` that blocks the server for 5 seconds) will affect everyone.

The solution: **Cache-as-a-Service with tiered SLAs**:

```
CACHE PLATFORM SERVICE TIERS

  ┌────────────────────────────────────────────────────────────────────┐
  │  TIER 1 — SESSION CRITICAL                                         │
  │  SLA: 99.99% (52 minutes downtime/year)                            │
  │  Architecture: Redis Cluster (6 shards, 3 replicas each)           │
  │  Dedicated nodes — no sharing with other tenants                   │
  │  Use for: user sessions, payment state, auth tokens                │
  │  Cost: $4,500/month                                                │
  ├────────────────────────────────────────────────────────────────────┤
  │  TIER 2 — GENERAL PURPOSE                                          │
  │  SLA: 99.9% (8.7 hours downtime/year)                              │
  │  Architecture: Redis Cluster, namespace isolation per service       │
  │  Shared nodes with fair-share memory quotas                        │
  │  Use for: product catalog, user profiles, search results           │
  │  Cost: $800/month per 10 GB quota                                  │
  ├────────────────────────────────────────────────────────────────────┤
  │  TIER 3 — BEST EFFORT                                              │
  │  SLA: 99.0% (3.65 days downtime/year)                              │
  │  Architecture: Single Redis with persistence, no HA guarantee       │
  │  Use for: feature flags, non-critical recommendations, dev/test     │
  │  Cost: $200/month shared                                           │
  └────────────────────────────────────────────────────────────────────┘
```

Service teams choose a tier based on their availability requirement. The platform team enforces ACLs and quotas per tier. Billing is charged back to the service team's budget.

---

## 5. Interview Calibration: Caching Discussion

### What L6 Interviewers Listen For

Staff-level interviews probe whether you think in **systems**, not just **solutions**. When a candidate says "I'd add Redis here," the interviewer's next question is one of these four:

1. "What happens to your system when Redis is unavailable?"
2. "How does your hit rate change at 10× scale?"
3. "Walk me through how you'd invalidate this cache when the underlying data changes."
4. "What's the first thing that will break when this goes to 10× traffic?"

An L5 candidate answers these questions when asked. An L6 candidate addresses them **before being asked**. The mental model is: an L6 candidate has already played out the failure scenarios in their head and is proactively noting the tradeoffs. This signals that they have built and operated systems at scale, not just designed them on paper.

**The framing Staff Engineers use**:

When proposing a cache, lead with the bottleneck analysis before the solution:

```
L5 answer: "I'd put Redis here to cache user profiles."

L6 answer: "The read:write ratio on user profiles is probably 1000:1 —
users read their profile on every page load but change it maybe once a
week. That makes this a perfect candidate for cache-aside with a 1-hour
TTL. The risk to call out: if Redis goes down, all reads fall through to
the DB simultaneously. I'd want the DB sized for that worst-case load
and a circuit breaker that returns a degraded response (no profile
personalization) instead of erroring — because a degraded experience
is better than a 500 error."
```

Same conclusion, but the L6 version demonstrates you have thought about failure modes and graceful degradation.

---

### Phrases Staff Engineers Use in Interviews

These are not magic words. They represent real thinking patterns. Use them because the thinking is correct, not to impress.

- **On starting with bottleneck analysis**: "Before I add caching, let me confirm caching is actually the bottleneck here. If the query is slow because of a missing index, adding Redis caches a slow thing instead of fixing it."

- **On hit rate as a prerequisite**: "Cache hit rate is the key metric. If we are below 80% hit rate, caching is adding operational complexity without proportional latency benefit. I'd want to understand why misses are happening before adding more cache."

- **On consistency requirements**: "The invalidation strategy depends entirely on the consistency requirement. Can this service tolerate 5 minutes of stale data? If yes, TTL-based expiration is simple and sufficient. If no, we need event-driven invalidation with a message queue."

- **On write strategy**: "I'd use write-through here because the write path — profile updates — happens maybe 100 times per day. The added latency of writing to Redis on every profile update is negligible compared to the benefit of always having fresh data in cache."

- **On fan-out**: "This is a fan-out write problem. With 1 million followers, fan-out on write means 1 million Redis writes per tweet. I'd threshold it: for users with under 10,000 followers, fan-out on write is fine. Above 10,000, I'd use fan-out on read and merge the celebrity's feed at read time."

- **On CDN**: "For the CDN layer, I'd tag product pages with surrogate keys like `product:{id}` so when a price changes, one CDN API call purges all product-related pages simultaneously — the product detail page, the category page, the search results page that featured this product. Without surrogate keys, I'd have to know and enumerate every URL that shows this product, which is impractical."

---

### How to Explain Caching to Leadership (Non-Technical)

Staff Engineers often need to justify caching infrastructure costs to VPs or directors who are not engineers. Practice this explanation:

**The analogy**: "Caching is like a grocery store keeping frequently-bought items at the front of the store instead of in the back warehouse. Most customers find what they need immediately — that is a cache hit — without warehouse trips, which represent database queries. When we run out of something at the front — a cache miss — we restock from the warehouse. This saves time and money because warehouse trips are slow and expensive."

**The cost justification**: "Right now our database handles 50,000 requests per second at full cost. With caching, roughly 90% of those requests will be answered from cache, which is much cheaper than a database query. Only 10% reach the database. This means we can use a smaller, cheaper database tier — saving approximately $8,000 per month — while actually improving response times for users. The Redis cluster costs $1,200 per month. Net savings: $6,800 per month."

**The risk framing**: "The main risk is cache failures. If the cache becomes unavailable, all traffic falls to the database. We mitigate this by keeping the database sized to handle 2× normal load as a safety net and having automatic fallback logic. A cache outage degrades performance but does not cause a service outage."

---

### Full Interview Walk-Through: "Design Caching for a Product Catalog"

This is a question that appears in Staff-level system design interviews. Here is a strong L6 answer structure to use as a template:

**Step 1 — Clarify Requirements (2 minutes)**

"Before designing, a few questions: What is the read-to-write ratio on the catalog? I assume product updates are rare — maybe 100 updates per day across 1 million products — is that right? What consistency is required for price changes — can a user see a 5-minute stale price, or must price always be current? What is the expected QPS for product reads?"

(Assume answers: 99% reads, price must be current within 5 minutes, 500K reads/sec at peak.)

**Step 2 — Identify the Bottleneck**

"At 500K reads/sec, no database can handle this directly. The catalog is read-heavy and write-rarely, which is the ideal profile for caching. The bottleneck is read throughput, not write throughput."

**Step 3 — Choose Cache Strategy**

"Cache-aside pattern with explicit invalidation on price changes. On read: check Redis → miss → query DB → write to Redis with 1-hour TTL. On price update: write to DB first, then immediately DELETE the corresponding Redis key. The 1-hour TTL is a safety net for missed invalidations, not the primary freshness mechanism."

**Step 4 — Address Failure Modes**

"Three failure modes to plan for:

One: Redis is unavailable. All reads fall to DB. DB must handle full load. I'd deploy with 2× normal DB capacity. Add a circuit breaker that, after 5 consecutive Redis failures, bypasses Redis for 30 seconds to let it recover rather than hammering a sick Redis.

Two: Cache stampede on popular product. If the product for a viral marketing campaign gets its key deleted simultaneously by 10,000 users all missing at once. I'd use probabilistic early expiration or a distributed lock on the miss path to let only one process regenerate the cache entry.

Three: Price change must propagate in 5 minutes. Explicit DEL on write covers this. I would also add a TTL of 5 minutes as a belt-and-suspenders measure — even if the DEL is missed, the entry expires within the consistency window."

**Step 5 — Scale Considerations**

"At 10× scale (5M reads/sec), the strategy is the same but the infrastructure scales:
- Redis Cluster with 10 shards instead of 1
- CDN in front of Redis for product HTML pages (cache the rendered page, not just the data)
- The product detail page itself is almost entirely static from the CDN; only the price widget is dynamic and calls the API

At 100× scale, I'd add a regional CDN layer — product pages cached at CDN edge nodes globally — with surrogate key invalidation. A price change triggers a CDN purge for all product-related URLs in under 1 second."

**Step 6 — Metrics**

"Three metrics I'd set up immediately:

Cache hit rate per key pattern — target 95%+ for product detail. Below 85%, investigate why misses are happening before scaling.

Eviction rate — should be zero with proper memory sizing. Non-zero evictions mean the cache is undersized and the eviction policy is silently destroying your hit rate.

Price staleness — a separate monitor that, every minute, picks 100 random products and compares the cached price to the DB price. Any discrepancy > 5 minutes old is a bug."

---

### Common L5 Mistakes to Avoid in Cache Interviews

These are the traps. Interviewers at Staff level will probe these explicitly.

**Mistake 1: "Cache everything"**

The interviewer will ask: "What's your hit rate?" and "What's the consistency requirement?" Caching everything without answering these first signals you haven't thought about whether caching helps.

**Mistake 2: "TTL solves all invalidation problems"**

They will immediately ask: "A product's price just changed. How long before the customer sees it?" If your answer is "up to 1 hour" and the requirement is 5 minutes, TTL alone is insufficient. Know when explicit invalidation is required.

**Mistake 3: "Redis is always faster"**

A slow Redis (blocking command, network partition, hot key) is slower than a well-tuned database with a warm connection pool. Do not blindly add Redis as a performance layer without characterizing the actual bottleneck.

**Mistake 4: "Cache and database are always consistent after a write"**

They will ask: "What happens if your cache write fails but your DB write succeeded?" Understand the failure scenarios for write-through and write-around, and what partial failure means for consistency.

**Mistake 5: "Add more Redis nodes to fix any problem"**

If the problem is a **hot key** (one product key getting 1 million reads/sec), adding more Redis shards does not help — the hot key still lands on one shard. The fix is to use local in-process caching for the hot key, or to read from multiple replicas via client-side load balancing.

---

## 6. Self-Assessment Rubric

Use this table honestly. The goal of this chapter series is to move you from the level you are at today to L6. Each level's signals are concrete and testable.

| Level | What You Can Do | What You Cannot Yet Do |
|---|---|---|
| Intern | Knows Redis exists. Has used `redis.set()` and `redis.get()`. Knows TTL is "expiry time." | Explain cache stampede. Reason about hit rate. Choose between cache patterns. |
| L3 / L4 | Can implement cache-aside. Knows Redis commands. Has heard of cache stampede. Understands TTL for freshness. | Design failure modes. Reason about cluster sharding. Build invalidation strategy from scratch. |
| L5 | Implements all 4 read patterns and 4 write patterns. Knows Redis Sentinel for HA. Understands CDN basics. Has done a Redis migration. | Drive cross-team cache standards. Reason about blast radius. Explain Redlock limitations. Design cost optimization across tiers. |
| L6 (target) | Designs multi-tier cache architecture with explicit failure mode analysis. Reasons about blast radius of cache failure at each layer. Knows Redlock CAP tradeoffs. Drives cross-team cache standards documents. Can explain any invalidation strategy given any consistency requirement. Quantifies cache cost vs. benefit. | (You are here — keep operating at this level until it is fluent.) |

**Practical self-test**: can you answer all of the following without looking anything up?

```
1. Your Redis cluster loses the primary shard for 45 seconds. What happens to your
   application? What happens to your DB? What is your recovery plan?

2. Your product page cache has a 95% hit rate. The business wants to change TTL
   from 1 hour to 5 minutes for "fresher data". Calculate the impact on DB load.
   What is your recommendation?

3. Team B wants to share your Redis cluster. They plan to use keys named "product:{id}".
   You also use "product:{id}". How do you resolve this before there is an incident?

4. Your service just deployed a new cache key format. The old format is still in Redis.
   Describe the rollback plan if the new format has a deserialization bug.

5. Your Redis is at 78% memory. Evicted_keys shows 5,000 evictions in the last hour.
   What are the three things you check first?
```

If you can answer all five in under 5 minutes, you are operating at L6 on caching.

---

## 7. Visual Summary: Chapter 31 in One Picture

This diagram is the full mental model. Every caching decision you make in an interview can be mapped back to some part of this picture. Study it until you can redraw it from memory.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    CHAPTER 31: CACHING AT SCALE — FULL PICTURE                  │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  LATENCY     LAYER              WHAT LIVES HERE         FAILURE MODE            │
│  ─────────   ────────────────   ─────────────────────   ─────────────────────   │
│  ~1 ns       CPU L1/L2 cache   CPU registers, hot ops   N/A                     │
│  ~10 ns      CPU L3 cache      Hot code, JIT cache       N/A                    │
│  ~100 ns     In-process (RAM)  Hot keys, local sessions  Server restart         │
│  ~1 ms       Redis (local AZ)  User data, sessions       Stampede, hot key      │
│  ~5 ms       Redis (cluster)   Distributed state         Shard failure          │
│  ~10-50 ms   CDN edge          Static assets, HTML        PoP outage (rare)     │
│  ~100-200 ms Origin DB         Source of truth            Thundering herd       │
│                                                                                 │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  THE 5 FAILURE MODES AND WHERE THEY STRIKE                                      │
│                                                                                 │
│  Stampede:        Redis ─────────────────────► All users hit DB simultaneously  │
│                   (key expires, 10K concurrent misses)                          │
│                                                                                 │
│  Hot key:         Redis shard ───────────────► 1 shard at 100% CPU, others idle │
│                   (viral product, 1M reads/sec to 1 key)                        │
│                                                                                 │
│  Avalanche:       Redis ─────────────────────► Mass simultaneous expiry         │
│                   (all keys set at same time, all TTL at same time)             │
│                                                                                 │
│  Cold start:      Redis (empty after deploy) ► 0% hit rate, DB takes all load   │
│                   (new key schema, new cluster, post-deploy flush)              │
│                                                                                 │
│  Cache poisoning: CDN edge ──────────────────► Wrong data served to all users   │
│                   (wrong data cached at CDN, hard to purge without surr-keys)   │
│                                                                                 │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  WHEN TO USE WHAT LAYER                                                         │
│                                                                                 │
│  In-process cache: hot keys accessed >10,000×/sec per server, immutable data    │
│  Redis:            user sessions, distributed state, leaderboards, pub/sub      │
│  CDN:              static files, HTML pages, API responses with surrogate keys  │
│                                                                                 │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  SCALE DECISION TREE                                                            │
│                                                                                 │
│  < 10K DAU:   No cache needed. DB direct. Optimize queries first.               │
│  < 100K DAU:  Single Redis + CDN for static assets.                             │
│  < 1M DAU:    Redis Cluster + CDN + cache warming on deploy.                    │
│  < 10M DAU:   Multi-AZ Redis Cluster + Multi-CDN + cache platform team.         │
│  > 10M DAU:   Multi-region + per-region Redis + globally distributed CDN.       │
│                                                                                 │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  MIGRATION STRATEGY SELECTION                                                   │
│                                                                                 │
│  High-stakes data (sessions, payments):  Shadow traffic (4-phase, 8 weeks)      │
│  Medium-stakes (product catalog):        Blue-green cache (gradual traffic ramp) │
│  Low-stakes (search suggestions):        Big-bang with rollback plan             │
│                                                                                 │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  COST OPTIMIZATION PRIORITY                                                     │
│                                                                                 │
│  1. Tiered caching (biggest lever): right data in right tier                    │
│  2. Same-AZ reads: eliminate cross-AZ network cost                              │
│  3. Value compression: 3-5x memory reduction for JSON/HTML                      │
│  4. TTL staggering: prevent avalanche, reduce burst miss spikes                 │
│  5. Eviction policy tuning: allkeys-lru for general, allkeys-lfu for skewed     │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

### Chapter 31 Supplement C — Connections to Other Chapters

This supplement covered the operational half of caching. How it connects:

- **Supplement A (Fundamentals)** gave you the four read patterns and four write strategies. This supplement showed you when each fails and how to migrate between them.
- **Supplement B (Redis Internals and Advanced Patterns)** covered Redlock, pub/sub, and cluster internals. This supplement showed how to own and operate those patterns at organizational scale.
- **Chapter 28 (Databases)** is where cache failures ultimately land. Your DB must be sized for the worst-case cache-miss scenario, which this supplement quantified.
- **Chapter 34 (Distributed Systems Fundamentals)** will cover CAP theorem. Redlock, consistency requirements, and cross-region replication all connect back to the CAP tradeoffs introduced there.

The mental model to carry forward: **every caching decision is a tradeoff between consistency, cost, and operational complexity**. An L6 engineer can articulate the specific numbers for each axis — not "Redis improves performance," but "a 95% hit rate at 500K RPS reduces DB load from 500K QPS to 25K QPS, dropping DB cost by $6,000/month at the expense of up to 5-minute staleness on product data, which is acceptable given the business requirement."

---

*End of Chapter 31 Supplement C*
*Supplement A: Fundamentals, Hierarchy, the Four Read and Write Patterns*
*Supplement B: Redis Internals, Advanced Patterns, Cluster Architecture, CDN Deep Dive*
*Supplement C (this document): Migration Strategies, Cost Optimization, Cross-Team Standards, Interview Calibration*
# Chapter 31: Caching at Scale — Redis, CDN, and Edge Systems
## Part E: Production Incidents, L5 vs L6 Calibration, and Exercises

---

## 1. Production Incidents

These are real incidents where caching either caused the outage directly or amplified the blast radius far beyond what the underlying trigger warranted. Read each one as a design pattern — not a horror story. The same failure can show up in an interview as "what could go wrong here?" and if you know these five cases, you will have concrete, real-world answers.

---

### Incident 1: Facebook — Cache Thundering Herd at Scale (2010)

**Background**

Facebook in 2010 was running one of the largest Memcached deployments in the world, serving billions of requests per day. The architecture was straightforward: web servers read from Memcached first; on a miss, they queried MySQL and wrote the result back to Memcached. MySQL was the source of truth but was effectively shielded from the request path under normal conditions. The entire system depended on Memcached absorbing the overwhelming majority of read traffic.

**The trigger**

A routine maintenance cycle took one Memcached shard offline briefly — a planned operation that engineers had done many times before. That shard held millions of cache keys.

**What happened**

The moment the shard went offline, every web server in the fleet that requested one of those keys received a cache miss. This was not one server or ten servers — Facebook's fleet was enormous. During the ten-second failover window, tens of millions of requests per second hit MySQL directly instead of Memcached. MySQL was dimensioned to handle the load that normally leaked past Memcached, not the full request volume. Latency spiked immediately. The database query queue backed up. The cascade spread to adjacent database nodes as queries for related data also missed the cache. Pages became slow, then unresponsive.

The fundamental problem: every single web server independently decided "I missed the cache, I will query MySQL." Five thousand web servers each sent the same query to the same database table in the same half-second window. There was no coordination, no queuing, no back-pressure. The database received a coordinated accidental denial-of-service attack from its own application tier.

**Root cause**

No stampede protection. The cache had no mechanism to signal "someone is already fetching this, you should wait for the result." Every requester acted with full autonomy.

**The fix**

Facebook published a research paper on this that became a canonical reference in distributed systems. Their solution was the "lease" mechanism. When a cache miss occurs, the cache does not simply return empty. It returns a special token to the first requester. Every other requester that arrives for the same key while it is being refreshed receives a "wait and retry" response along with the token. Only the token-holder is authorized to query the database and write the result back. All other requesters poll briefly and then read the freshly-populated cache value.

This means that regardless of how many concurrent requesters arrive during a cache miss, exactly one database query is issued. The rest wait a short time (typically 10–50 milliseconds) and then read the result. The database load is reduced by roughly the concurrency factor — 5,000 concurrent requesters become 1 database query.

**What L6 engineers take from this**

Cache-aside is safe when concurrency on a single key is low. It becomes unsafe when concurrency is high and cache misses can be coordinated by time. The three practical fixes are: a lease or lock mechanism (SETNX in Redis — set if not exists — to let exactly one requester populate the key), stale-while-revalidate (serve the old value while refreshing in the background, so the miss never reaches the database under normal operations), and local in-process caches on each app server with a short TTL (5 seconds) for the hottest keys so individual servers absorb most of the load locally before reaching the shared cache.

When a cache shard fails, the first question is not "how do we bring it back?" It is "what is the blast radius?" Specifically: what percentage of keys land on that shard, what is the QPS that will suddenly redirect to the database, and does the database have the capacity to survive for the ten seconds it takes Sentinel to complete a failover?

---

### Incident 2: Reddit — Cache Stampede Brings Down the Site (2015)

**Background**

Reddit ran a Python application stack backed by Memcached and PostgreSQL. The front page — what a logged-out user sees when they visit reddit.com — was one of the most-fetched pages on the internet. Generating the front page required querying hundreds of posts, their vote counts, their comment counts, and their thumbnails. This was computationally expensive. Caching it as a single key with a TTL was the obvious optimization, and it worked well under normal traffic.

**The trigger**

A post went viral during a period of already-elevated traffic. The concurrent user count spiked to approximately 500,000 simultaneous users, all actively refreshing the front page.

**What happened**

The Memcached key for the front page expired at the worst possible moment — during the peak of the viral traffic spike, while all 500,000 users were actively refreshing. All 500,000 simultaneous requests got a cache miss. All 500,000 attempted to query PostgreSQL to regenerate the front page. PostgreSQL received a load it was never designed to handle at that concurrency level. The query queue backed up. Latency climbed past the application's timeout threshold. The application servers began returning errors. Reddit went down for 40 minutes.

The deeply ironic aspect of this incident: the cache key that caused the outage was for the most popular content on the site. Popularity made it dangerous. A page that only 100 users accessed simultaneously when its cache expired would create 100 concurrent database queries — annoying but survivable. A page that 500,000 users access simultaneously creates 500,000 concurrent queries — catastrophic.

**Root cause**

No stampede protection on the single most-trafficked cache key in the entire system. The combination of high popularity and a hard TTL expiry created a deterministic failure mode.

**The fix**

Two mechanisms were added. The first was probabilistic early refresh: instead of letting the cache key expire hard at TTL, start computing a refresh probabilistically as the key approaches its expiry time. If a key has a 5-minute TTL and there is a 20% chance of refresh on each request in the final 30 seconds of TTL, the cache is almost certainly refreshed before it expires to all requesters. The math: within 30 seconds, with 500,000 requests per minute, the key will be refreshed within milliseconds of entering the refresh window. The cache never goes cold.

The second was a circuit breaker on the database side: if PostgreSQL response latency exceeded a configured threshold (for example, 1 second), stop sending new generation requests and instead serve the stale (expired) cache value. The stale front page is much better than no front page at all. Users see content that is slightly old; they do not see a 500 error.

**What L6 engineers take from this**

The most popular content in your system is the most dangerous content to cache with a hard TTL. Treat the top-N hottest keys differently from the rest. Give them probabilistic early refresh. Give them stale-serving capability behind a circuit breaker. Consider replicating them across multiple cache nodes for redundancy.

Hard TTL expiry is a sharp edge. Every production caching system at scale should have stale-while-revalidate or equivalent behavior on high-traffic keys. The moment you allow hard expiry on a popular key at arbitrary wallclock time, you have created a time-bomb that fires unpredictably under high load.

---

### Incident 3: Slack — Redis Memory Exhaustion During Black Friday (2020)

**Background**

Slack's presence system — the green dot that shows whether a user is online — was backed by Redis. Every active user had a key in Redis representing their current presence state. This data was queried constantly: when a channel loaded, when a user composed a message, when the @mention autocomplete ran. The presence system was one of the highest-read components in Slack's infrastructure.

**The trigger**

Black Friday 2020. A combination of large company-wide all-hands meetings (enterprises doing end-of-year syncs across globally distributed teams) and general holiday traffic drove a massive concurrent user spike. More simultaneous active users meant more simultaneous active presence keys in Redis.

**What happened**

The presence keys for all active users filled Redis to its configured maxmemory limit. Redis does not crash when it hits maxmemory — it evicts keys according to the configured eviction policy to make room for new writes. But the eviction policy was set incorrectly for this use case. Keys for active user sessions — the data that should have been most protected — were evicted to make room for new data.

The result: users who were actively working in Slack appeared as offline. @mentions went to users who appeared unavailable. Channels showed incorrect presence indicators, creating confusion and noise. Teams believed colleagues were offline when they were actually online. This degraded the core communication experience for a large portion of Slack's user base during a period of peak usage.

The failure had a compounding character. As keys were evicted, new presence updates tried to write to Redis (which was still at maxmemory), triggering more evictions. The system was in a continuous eviction storm.

**Root cause**

Two compounding problems. First, maxmemory was set too close to actual usage with no headroom. The configuration assumed steady-state traffic, not a 2× spike. The gap between configured maxmemory and actual peak usage was insufficient to absorb the Black Friday surge. Second, the eviction policy was misconfigured. The correct policy for a system with both permanent/critical keys and ephemeral/short-lived keys is volatile-lru: evict only keys that have a TTL set, leaving keys without a TTL (the permanent ones) protected. The presence system's key TTL configuration was inconsistent, which caused the wrong keys to be evicted.

**The fix**

Raise the maxmemory threshold to include substantial headroom — the guideline that emerged was to plan for 50% headroom above expected peak, not 10% or 20%. Add layered alerting: a warning at 60% memory utilization and a critical alert at 75%, giving the on-call engineer time to take action before the system is in distress. The alert at 95% is too late — by the time you are at 95%, the system is already in an eviction storm and degrading.

Switch to volatile-lru as the eviction policy across all Redis instances that hold a mix of permanent and ephemeral data. This ensures that permanent keys (those without a TTL) are never evicted regardless of memory pressure.

Run load tests at 2× expected peak traffic before any major event — product launches, Black Friday, and major company announcements. The goal is to discover the memory ceiling before users discover it for you.

**What L6 engineers take from this**

Memory is a hard ceiling in Redis in a way that disk space is not for a relational database. A PostgreSQL database under memory pressure will slow down, swap to disk, degrade gracefully. A Redis instance that hits maxmemory stops accepting writes or starts evicting keys — immediately and without warning. This difference is fundamental to operating Redis safely.

Know your eviction policy. Allkeys-lru evicts any key. Volatile-lru evicts only keys with a TTL. Noeviction returns errors on new writes when full. For most production systems, volatile-lru is the correct default — protect permanent keys, allow ephemeral keys to be evicted under pressure.

Alert at 70–75% memory, not 90%. The time between 75% and 100% during a traffic spike can be measured in minutes.

---

### Incident 4: GitHub — CDN Misconfiguration Serves Cached Private Data (2020)

**Background**

GitHub's repository pages — the web UI for viewing source code, commits, pull requests, and issues — were served through a CDN layer. Public repository pages were cached normally; private repository pages were supposed to either bypass the CDN entirely or carry headers that prevented the CDN from caching them. The distinction between public and private was enforced through Cache-Control headers set by the application.

**The trigger**

A code change introduced a bug in the Cache-Control header generation logic. For a specific class of private repository pages, the application began setting `Cache-Control: public, max-age=300` instead of the correct `Cache-Control: private, no-store`.

**What happened**

The CDN received a response for a private repository page with `Cache-Control: public, max-age=300`. The CDN's behavior was correct according to the HTTP specification: it cached the response and served it to any subsequent requester for the same URL. The next user who happened to request the same URL path — a different user, potentially a completely unrelated person with no association to the repository — received the first user's private source code in their browser. The exposure window for each cached entry was five minutes, the configured max-age. During those five minutes, any user who requested the URL received the original owner's private data.

The bug was detected within a few hours through anomalous access patterns. GitHub invalidated all affected CDN entries and notified affected repository owners. A post-mortem documented the incident publicly.

**Root cause**

The Cache-Control header generation code did not correctly distinguish between public and private content under all code paths. A conditional branch that should have set private headers instead fell through to the public default. No automated validation caught the error before it reached production.

**The fix**

Two changes. Immediate: strict manual code review of all code paths that produce Cache-Control headers, with a verified test for every content-type category.

Structural: a CI pipeline check was added that uses a test suite to validate Cache-Control headers on known private-data endpoints. The check parses the header value and fails the build if the `public` directive appears on any endpoint categorized as private. This makes it impossible to deploy a misconfiguration of this class — the CI gate prevents it from shipping.

**What L6 engineers take from this**

CDN caching is invisible to users. Unlike a slow page load or a 500 error, a cached private data exposure does not announce itself. The user who receives someone else's private code has no indication that anything is wrong. They simply see content. This makes the failure mode uniquely dangerous compared to performance bugs.

The `public` versus `private` Cache-Control directive is not a performance tuning decision. It is a security boundary. Every engineer who touches response headers needs to understand this distinction. The default should be `private, no-store` for any authenticated or user-specific content, and `public` must be explicitly added only after confirming the content is safe to share with any user.

Automated header validation in CI is non-optional for any product that handles private user data through a CDN. Do not rely on code review to catch this class of bug — humans make mistakes. The automated check is the last line of defense.

---

### Incident 5: Robinhood — Cache Invalidation Race Causes Wrong Stock Prices (2021)

**Background**

Robinhood displayed real-time stock prices to users as they made trading decisions. The price display was backed by a Redis cache with write-through invalidation: when a new price arrived from the market data feed, the application wrote it to Redis and then wrote it to the backing database. The architecture appeared simple and correct — every new price update flows through to the cache immediately.

**The trigger**

High-volatility trading during the GameStop saga. Stock prices were updating multiple times per second for the most-active tickers. Multiple concurrent price update events were arriving continuously for the same set of stock symbols.

**What happened**

The following race condition occurred, and it is worth working through slowly because it is subtle.

Consider two concurrent price updates for the same stock: Write A (older price) and Write B (newer price). They arrive milliseconds apart.

- T=0ms: Write A begins processing. Application starts a Redis SETEX call for the price key.
- T=0.1ms: Write B begins processing. Application starts a Redis SETEX call for the same key.
- T=0.5ms: Write B completes its Redis write. The key now holds the newer price. Write B also begins its database write.
- T=0.8ms: Write B completes its database write. The database holds the newer price.
- T=1.0ms: Write A completes its Redis write. The key now holds the older price (Write A won the race to Redis last).
- T=1.5ms: Write A completes its database write. The database updates to the older price — but wait, the database had already stored the newer price from Write B, and depending on the database's internal serialization, the final state depends on the commit order.

In the worst case: the database correctly holds the newer price (Write B committed last, which is correct because B arrived later). But Redis holds the older price (Write A set it last). The cache is now stale. Every read for this stock's price for the next several minutes — until the TTL expires — returns the wrong value. Users make trading decisions based on an incorrect price.

**Root cause**

Write-through caching without serialization guarantees between concurrent writers. The application-layer write-through pattern assumes that writes happen sequentially. Under concurrent load, two writers can interleave their Redis writes in any order determined by network timing, thread scheduling, and Redis latency jitter. The "last write wins" in Redis is not guaranteed to be the "most recent event" from the application's perspective.

**The fix**

Replace application-level write-through with database-driven cache invalidation using Change Data Capture (CDC). The new flow:

1. Application writes to the database only. It does not touch Redis.
2. The database's replication log (PostgreSQL WAL) emits change events captured by a CDC tool (such as Debezium).
3. CDC events are published to a Kafka topic, partitioned by stock symbol, preserving order within a partition.
4. A cache invalidation consumer reads from Kafka and updates or deletes the Redis key based on the event.

Because Kafka preserves ordering within a partition, and the CDC stream reflects the true commit order from the database's perspective, the cache invalidation consumer always processes events in the order that commits happened. The final value in Redis is the last committed value in the database. The race condition is eliminated because the serialization happens at the database level, not the application level.

**What L6 engineers take from this**

Write-through caching looks simple on a whiteboard. It is safe only when writes to the same key are serialized — one at a time, with the later write always executing after the earlier one in both the cache and the database. Under concurrent writes without serialization, the cache can hold a stale value indefinitely (until TTL expiry), and there is no automatic correction mechanism.

CDC-driven cache invalidation is the correct pattern for high-concurrency, high-write-rate systems where consistency matters. The database's commit order becomes the cache's update order. The cost is additional infrastructure (CDC pipeline, Kafka, consumer service) and additional latency between a write and the cache update (typically 100–500ms for CDC propagation). Whether that trade-off is acceptable depends on your staleness tolerance.

This is a real interview question in disguise: "Your write-through cache is returning stale data under concurrent load. What is happening and how do you fix it?" The answer is this incident.

---

## 2. L5 vs L6 Calibration

This table represents twelve dimensions where L5 and L6 engineers diverge. The L5 answers are not wrong — they are competent starting points. The L6 answers are more complete because they anticipate failure modes, ask "what are the second-order effects," and define success metrics before building anything.

| Dimension | L5 Answer | L6 Answer |
|-----------|-----------|-----------|
| **Slow endpoint** | "Add Redis with a 5-minute TTL." | "Why is it slow? Profile the query first. Cache only if the database is the actual bottleneck and the data tolerates staleness. Then: what's the invalidation strategy? What happens on the first request after deploy when the cache is cold? Is the endpoint even safe to cache — is it idempotent, is it user-specific?" |
| **Cache hit rate** | "We'll know if it becomes a problem — the app will slow down." | "Monitor hit rate continuously, broken down by key namespace. Target above 90%. Below 80%, investigate — likely wrong key design, TTL too short, or wrong eviction policy. Below 70%, the cache may be net-negative: it adds latency on miss without proportionally reducing database load, and you should question whether it is helping." |
| **Key expiry** | "All keys expire in 1 hour, that's simple and consistent." | "Different TTLs per data type — prices may be 30 seconds, product descriptions 10 minutes, user preferences 1 hour. Add TTL jitter (±10–15%) on every key to spread expiry events across time and prevent synchronized avalanche. Top-N hottest keys get probabilistic early refresh so they never go cold." |
| **Cache failure** | "Users get slower responses, it degrades gracefully." | "Model the blast radius explicitly. If the cache layer goes down, how many QPS suddenly hit the database? Does the database have the headroom to survive it for the 10–30 seconds Sentinel takes to complete failover? If not, you need a circuit breaker that stops database traffic and serves stale data, plus pre-approved runbooks for the on-call engineer." |
| **Invalidation** | "Delete the key on write — the next read will repopulate it." | "Event-driven invalidation via CDC for strict consistency. TTL-based with tolerated staleness for simpler systems. Write-through only with serialization guarantees between concurrent writers. Never write-behind without a durable queue — if the queue or the consumer crashes, the cache will hold data that the database does not, which is the worst possible inconsistency direction." |
| **Hot key** | "That's a Redis problem — it should handle high QPS." | "A single Redis key is served by a single shard — that is a hard ceiling of roughly 100–200K ops/sec. Fix: local in-process LRU cache on each app server for the top-N hottest keys with a 5-second TTL. Read from replicas for read-heavy hot keys. In extreme cases, shard the key across multiple Redis nodes with a consistent hash suffix and read from all shards. Detect hot keys via per-key access metrics before they become incidents." |
| **CDN setup** | "Put static files on CloudFront and that's it." | "Define Cache-Control headers explicitly for every content category before the CDN goes live: `immutable` for content-hashed assets, `s-maxage=300` for product pages, `private, no-store` for anything user-specific or authenticated. Design the purge strategy before launch — tag-based purging for efficiency, not path-based. Plan edge logic for auth header passthrough, A/B test routing, and geographic redirects." |
| **Redis Cluster vs Sentinel** | "Use whichever is easier to set up." | "Sentinel for high availability of a single dataset up to approximately 25GB or up to approximately 200K QPS. Cluster for larger datasets or higher throughput where horizontal sharding is needed. Cluster adds significant operational complexity: hash slot management, hash tags required for multi-key operations, no cross-slot commands. The default recommendation is Sentinel until you have a measured reason to move to Cluster." |
| **Redis persistence** | "Redis is just a cache, we don't need persistence." | "Depends entirely on what is in Redis and what the recovery story is on restart. Session cache backed by a database: no persistence — lose it on restart and rebuild from DB. Rate limit counters: AOF with everysec sync — tolerate up to 1 second of counter data loss. Primary data store with no DB backing: RDB snapshots plus AOF together. Always define the answer to: what happens if Redis restarts right now? Is that acceptable?" |
| **Multi-region cache** | "Point all global traffic at the same Redis cluster." | "Regional Redis deployment per geographic zone with geo-routing sending users to the nearest cache. This is also a legal compliance requirement — GDPR requires EU user data to remain in EU infrastructure. For reads, active-passive is simpler. For writes with strict consistency, you need a strategy: either route all writes to a primary region (accept cross-region write latency) or use active-active with conflict resolution (accept eventual consistency between regions)." |
| **Cache for auth** | "Store the JWT in Redis and validate it there." | "JWT validation is stateless — verify the signature with the public key locally, no network call needed. Do not cache JWTs in Redis as a validation mechanism. For token revocation (logout before token expiry), maintain a Redis-backed blocklist keyed by token JTI with TTL equal to the remaining token lifetime. For scale, put a Bloom filter in front: false positives check Redis, true negatives (the vast majority of tokens) skip Redis entirely." |
| **Observability** | "Alert when the application response time degrades." | "Cache-specific metrics, collected and alerted on independently from application metrics: hit rate per key namespace, memory utilization percentage with alert at 75%, p99 get and set latency, evicted_keys per second (alert if nonzero in production), connected_clients count, replication lag on replicas. Application latency is a lagging indicator. Cache metrics give you the warning before users feel it." |

---

## 3. Cross-Topic Brainstorming Questions

These questions are open-ended design problems. There is no single correct answer. The goal is to demonstrate that you can reason through trade-offs, identify failure modes, quantify constraints, and make defensible architectural decisions with incomplete information.

### Theme A: Cache Strategy Design

**1.** You are designing a personalized news feed for 50 million users.
- Each user's feed is unique — reflects who they follow, what topics they have engaged with, and their location.
- Caching 50 million individual full-feed snapshots is impractical (storage cost, invalidation complexity).
- How do you cache feed data at scale without storing 50 million complete copies?
- What can be pre-computed and cached, and what must be assembled at read time?
- How do you handle the celebrity-user asymmetry (a user who follows 100 people vs a celebrity followed by 10 million people)?
- What happens to feed caches when a user unfollows someone or when a post is deleted?

**2.** A product detail page displays five pieces of information: the product name, the price, the current inventory count, whether the logged-in user has wishlisted the item, and whether the item is in the user's cart.
- Which of these five can you safely cache at the CDN level (no user context required)?
- Which are cacheable in Redis (per-user but tolerate some staleness)?
- Which require a fresh database read on every single request, and why?
- How does your answer change if the product is a flash-sale item with inventory that could drop to zero in seconds?

**3.** You need to cache the results of a complex ML recommendation query that takes 500ms to run.
- The results are personalized — different per user.
- Each result set is approximately 10KB.
- Results go stale after 1 hour.
- You have 10 million daily active users with roughly uniform activity throughout the day.
- Calculate the worst-case memory requirements to cache results for all active users at once.
- How does the number change if you only cache results for users active in the last 30 minutes?
- Design the key structure, TTL strategy, and cache warm-up approach.
- What happens during a cold start when all 10 million users request recommendations simultaneously?

**4.** A payment service must never return stale account balance information to the user.
- Queries to the database take 8ms.
- Is there any caching layer you can safely apply to balance reads?
- If the balance itself cannot be cached, are there adjacent pieces of data on the same page (user name, payment methods on file, recent transaction history) where caching is safe?
- How do you decompose a page into cacheable and non-cacheable components?
- What is the correct Cache-Control header for the balance endpoint?

**5.** Your cache hit rate dropped from 93% to 71% overnight. No code was deployed. No traffic spike occurred. System logs show normal request volume.
- List at least five distinct hypotheses for why hit rate would drop silently.
- For each hypothesis: what specific metric or log entry would confirm or rule it out?
- What is the correct order of investigation — which hypothesis do you rule out first and why?
- At what point do you escalate vs continue investigating alone?
- What monitoring would have caught this before the drop reached 71%?

---

### Theme B: Failure Mode Design

**6.** Walk through what happens when your Redis primary fails in a Sentinel setup (1 primary, 2 replicas, 3 Sentinels).
- Start from the moment the primary stops responding.
- What does each Sentinel do in sequence?
- What determines how long failover takes?
- What do application clients experience during the failover window?
- Which clients recover automatically and which require a restart?
- What is the state of the promoted replica — is any data lost?
- What happens to writes that arrived at the primary in the final second before it crashed?

**7.** You are running a Redis Cluster with 3 primary shards and 1 replica each (6 nodes total). You need to add a 4th primary shard to the live cluster without downtime.
- Walk through the procedure from start to finish.
- How does Redis redistribute hash slots to the new shard?
- What percentage of hash slots move to the new shard?
- What happens to keys mid-migration when a request arrives for them?
- What monitoring do you set up to detect errors during resharding?
- What is the rollback plan if resharding fails halfway?

**8.** One hundred thousand users simultaneously try to load a trending article. The article's cache key expired 200 milliseconds ago. Your database can handle 500 QPS for this query.
- Describe at least two complete system designs that prevent 100,000 concurrent database queries.
- For each design: what happens in the first 200ms after cache expiry?
- What do users experience — do some wait? do some see stale content?
- What is the implementation complexity cost of each approach?
- Which approach do you choose, and why?

**9.** Your CDN is serving stale product prices. TTL is 6 hours. Prices changed 30 minutes ago. Users are buying at the wrong price.
- Walk through the immediate 5-minute response plan.
- How do you purge the stale entries from the CDN?
- What TTL would you set going forward, and why?
- What purge strategy do you implement to handle future price changes?
- How do you validate that prices are now fresh at the CDN edge before declaring the incident resolved?
- What monitoring do you add to detect this class of problem automatically in the future?

**10.** Your application has an in-process LRU cache on each of 50 application server instances. A critical feature flag updates. It propagates to the database and Redis within 100ms. But all 50 app servers hold the old value in local memory with a 10-minute remaining TTL.
- How do you invalidate the in-process cache on all 50 servers simultaneously?
- Describe at least three approaches: at least one push-based and one pull-based.
- For each: what is the propagation latency? What is the operational complexity?
- What happens if an app server is under heavy load when the invalidation arrives?
- What happens if 5 of the 50 servers miss the invalidation signal?

---

### Theme C: Scale and Cost

**11.** Your platform receives 1 billion product page views per day. 95% of views are for the same 10,000 popular products. The remaining 5% are spread across 40 million long-tail products.
- Average product page: 50KB HTML, 200KB images, 5KB API data.
- Describe the complete caching architecture from the user's browser to the database.
- For each cache layer: what does it hold, what is the TTL, what hit rate do you expect, and how much storage does it require?
- How do you handle long-tail products that may only be viewed once per day?
- What is the total bandwidth savings from the CDN for the image assets alone?

**12.** Your Redis cluster is at 80% memory utilization. New nodes will not be provisioned for 30 days.
- List at least five operational actions you can take today without code changes.
- Order them by expected impact.
- For each action: what does it do, what is the risk, and how do you measure whether it helped?
- Which actions are reversible if they cause unexpected side effects?
- After exhausting operational actions, if memory is still growing, what is your escalation path?

**13.** A video streaming platform serves 10 gigabits per second of traffic globally. Videos are static after upload. Each video averages 500 views in its first 24 hours.
- Explain how CDN caching reduces origin bandwidth cost.
- What percentage of traffic can realistically be served from CDN edge nodes?
- Describe three conditions under which CDN hit rate would fall significantly for this content type.
- How does geographic distribution of viewers affect CDN hit rate per PoP?
- At $0.01/GB CDN transfer vs $0.08/GB origin transfer, estimate the monthly savings.

**14.** Your platform serves EU users (GDPR: personal data must remain in EU infrastructure) and US users (no geographic data residency constraint). Product catalog data is shared globally.
- Design the Redis and CDN architecture for this constraint set.
- How are requests routed to the correct regional cache?
- What happens when one region's cache layer fails — does the other region serve as fallback?
- How do you prevent EU user data from ever being cached in US infrastructure?
- How do you manage cache invalidation events across two independent regional deployments?
- What does the compliance audit trail look like for demonstrating EU data residency?

**15.** At $0.08/GB data transfer, your CDN saves $50,000/month vs serving from origin. An infrastructure team proposes removing the CDN to reduce vendor dependencies. Engineering cost of removal: 2 weeks.
- What questions do you ask before evaluating this proposal?
- What data do you gather?
- What risks does removal introduce beyond the bandwidth cost?
- What is the performance impact on users in regions far from your origin data center?
- What would have to be true — about traffic patterns, budget, or architecture — for removal to be the correct decision?
- What is your recommendation given the numbers provided?

---

### Theme D: Cross-Topic Integration

**16.** Your cache invalidation system is driven by Kafka events sourced via CDC from PostgreSQL.
- Design the full pipeline from a database write to a Redis cache update.
- How does a PostgreSQL row update become a Kafka event?
- How do you ensure ordering within a key? (Two updates to the same product must be applied in commit order.)
- What happens if the Kafka consumer is 30 seconds behind due to a processing backlog?
- What happens if the consumer crashes and restarts — can it safely replay events?
- What are the risks of double-applying a cache invalidation event?

**17.** You are building a rate limiter. Requirements: 50M users, max 1,000 requests/hour per user, max 10 requests/second burst.
- Compare the fixed window counter (INCR + EXPIRE on an hourly key) with the sliding window sorted set (ZADD, ZREMRANGEBYSCORE, ZCARD).
- Evaluate each on: accuracy at window boundaries, Redis memory per user, commands per request, and behavior when Redis is temporarily unavailable.
- Which do you choose for this scale, and why?
- How does your answer change if users are allowed to make exactly 1,000 calls — no over-counting permitted?

**18.** Your cache invalidation consumer reads Avro-encoded events from Kafka. The Avro schema currently has a field `product_price`. A schema evolution renames it to `listing_price`.
- The Kafka topic contains a mix of old events (with `product_price`) and new events (with `listing_price`).
- What breaks if you deploy the new consumer before all old events have been consumed?
- What breaks if you keep the old consumer running after new events with `listing_price` start arriving?
- Describe the safe migration procedure that avoids any cache inconsistency window.
- What does this incident reveal about the coupling between schema evolution and cache invalidation systems?

**19.** Design the caching strategy for a Google Docs-style collaborative text editor. Multiple users edit simultaneously.
- All users must see changes within 1 second.
- The system uses CRDTs or operational transforms for conflict resolution.
- What data can be cached, at what layer, with what TTL?
- What data fundamentally cannot be cached, and why?
- How does your answer change as simultaneous editors of a single document grow from 1 to 10 to 1,000?
- Where does the "cache" concept break down entirely for this use case?

**20.** Three companies are each considering a caching investment.
- Company A: startup, 1,000 daily active users, 50ms database queries, no current caching.
- Company B: growth stage, 1M users, static marketing content, 200ms page loads due to origin latency for international users.
- Company C: large platform, 100M users, working dataset has grown to 90GB — no longer fits in a single Redis instance.
- Evaluate each investment decision on its merits.
- For which company is the investment most clearly justified right now?
- For which company is it least urgent, and what should they do instead?
- What would change your recommendation for each company?

---

## 4. Homework Exercises

Work through these in writing, not just mentally. Write out the design, produce the diagram, and then critique your own answer — identify what you are not sure about, what assumptions you made, and what would change at 10× the stated scale.

---

### Exercise 1: Design the Cache Layer for a Social Media Platform

**Platform specifications**

- 100 million registered users; 10 million daily active users
- 500 million posts total in the system
- 2 billion feed load requests per day (approximately 23,000 requests per second at peak)
- User follow graph is heavy-tailed: most users follow fewer than 200 accounts, but top celebrities have 10+ million followers
- Each post includes text (up to 500 characters), one optional image, and engagement counters (likes, comments, reshares)

**Design requirements**

Produce a complete caching architecture for each of the following four subsystems:

1. The personalized home feed — an ordered list of recent posts from accounts the user follows, shown on login and on refresh.
2. Post content — the post text, author information, and associated image or video.
3. Trending posts — the top 50 posts by engagement in the past 1 hour, displayed in a sidebar.
4. Cache invalidation — when a post is deleted or edited, or when a user blocks another user (affecting what they see in their feed).

For each subsystem: what cache layer (CDN, Redis, in-process, or some combination), what is the key structure, what is the TTL, what is the write strategy (cache-aside, write-through, or event-driven), and what is the expected cache hit rate?

**L6 depth hints**

The feed generation problem splits on follow-count asymmetry. For regular users following fewer than approximately 1,000 accounts, pre-compute the feed on write (fan-out on write): when a new post is created, push its ID to the Redis feed list for each of the author's followers. Feed read is then just a Redis LRANGE — O(1) with no computation. For celebrity accounts (followed by millions), fan-out on write would require millions of Redis writes for each post — too expensive and too slow. Instead, maintain a separate celebrity post list per author and merge it into the user's feed at read time (fan-out on read), combining the pre-computed follower feed with the celebrity timelines.

Post images and videos belong at the CDN. These are static blobs that do not change after upload. Use content-addressed URLs (the URL path includes a hash of the content) and set `Cache-Control: max-age=31536000, immutable`. This maximizes CDN cache lifetime and eliminates the need for cache invalidation on these assets.

Trending posts is a shared key — the same sorted set is read by all users. Protect the trending post refresh with a distributed lock (SETNX). If the key expires and 50,000 users simultaneously request the trending sidebar, only one should trigger the recomputation. The rest should either wait briefly or receive the slightly-stale previous result.

Deletion and editing are the hard part. A deleted post cached in 50,000 users' feed lists in Redis cannot be removed from all of them efficiently. The practical answer is: store a deletion flag in a fast lookup (a Redis Set of deleted post IDs), and filter it out at read time. Accept a short window (TTL duration) during which the deleted post may still appear in some feeds.

---

### Exercise 2: Redis Failure Mode Analysis

**Setup**

You operate a Redis Sentinel deployment with the following topology: 1 primary node, 2 replica nodes (each replicating from the primary), and 3 Sentinel processes, each running on a separate host. Your application uses a Sentinel-aware Redis client library that queries Sentinel for the current primary address and reconnects automatically on failover.

Replication is asynchronous. Sentinel quorum is set to 2 (default for 3 Sentinels). The `min-replicas-to-write` setting is 0 (the primary accepts writes even if no replicas are connected).

**Analyze each scenario in writing**

**Scenario A: The primary node hard-crashes (power failure)**

Walk through the Sentinel failover sequence. At what point do Sentinels declare the primary subjectively down? At what point is it declared objectively down? Which replica is promoted? How is the promotion decision made (which replica is chosen if the two replicas have different replication offsets)? What do application clients connected to the old primary experience during the failover? How long is the service in a degraded state? Is any data permanently lost?

**Scenario B: Network partition splits the Sentinel cluster asymmetrically**

A network fault puts 2 Sentinel processes and the primary on network segment X, and 1 Sentinel process and both replicas on network segment Y. Application servers are split: 40 are on segment X and 10 are on segment Y.

Analyze each side independently. Can segment Y's single Sentinel initiate a failover? Why or why not? What do the 10 application servers on segment Y experience — can they write to the primary? Can they read from replicas? What happens after the partition heals? Is there a split-brain risk here, and what Sentinel/Redis configuration settings mitigate it?

**Scenario C: All 3 Sentinel processes crash simultaneously; primary and replicas are alive**

The primary and both replicas are healthy and fully synchronized. But all 3 Sentinel hosts have failed (OS crash, accidental termination). What happens to clients that are currently connected to the primary? What happens to new client connections that try to discover the primary through Sentinel? Can you still write to the primary? What is the operational procedure to restore Sentinel monitoring without disrupting the live primary?

**L6 depth hints**

Sentinel requires quorum to declare a primary objectively down and initiate failover. Quorum of 2 means at least 2 Sentinels must agree. In Scenario B, the single Sentinel on segment Y cannot reach quorum alone and therefore cannot initiate failover. This is intentional — it prevents split-brain where both sides promote a replica and you end up with two primaries. However, the trade-off is that segment Y is stuck: its Sentinel cannot help, and the application servers on segment Y cannot reach the primary on segment X.

In Scenario C, existing application connections to the primary continue working — Sentinel is not in the request path for established connections. But new connections that use the Sentinel discovery protocol (SENTINEL get-master-addr-by-name) will fail because Sentinel is unavailable. This argues for having a static DNS entry for the primary that is updated by Sentinel automation on failover — it provides a fallback discovery mechanism when Sentinel is down.

---

### Exercise 3: CDN Cache-Control Audit

**Context**

You are reviewing HTTP response headers for an e-commerce platform. For each endpoint, write the complete, correct Cache-Control header value and provide a one-paragraph explanation of each choice.

**Endpoints**

1. `GET /static/app.bundle.a1b2c3d4.js` — The JavaScript application bundle. The filename includes a SHA-256 content hash. Each deployment produces a new bundle with a new hash in the filename.

2. `GET /api/products/123` — A product detail API response returning name, description, price, and inventory count as JSON. Price and inventory can change every few minutes during flash sales. The endpoint requires no authentication — any user can view any product.

3. `GET /api/users/me` — An authenticated user's profile API response: name, email, shipping addresses, and saved payment method metadata.

4. `POST /api/checkout` — The checkout submission endpoint. It creates an order and initiates payment processing.

5. `GET /images/product-123-main.jpg` — A product image uploaded by the seller. The image never changes once uploaded; a new image gets a new URL.

**L6 depth hints**

For the content-hashed JS bundle: the hash in the filename is a guarantee that this URL will never serve different content. The correct headers are `Cache-Control: public, max-age=31536000, immutable`. The `immutable` directive tells compliant browsers not to send conditional requests on reload — if the content never changes, there is no reason to check. This is safe only because a new deployment generates a new filename.

For the product API: `Cache-Control: public, s-maxage=300, stale-while-revalidate=60`. The `s-maxage` value applies to shared caches (CDN) and overrides `max-age` for them. The `stale-while-revalidate=60` allows the CDN to serve a stale response for up to 60 additional seconds while it fetches a fresh copy in the background, eliminating a synchronous origin fetch on cache expiry. You may also want `Surrogate-Key: product-123` (or equivalent vendor tag header) to enable tag-based purging when the product is updated.

For the user profile: `Cache-Control: private, no-store`. The `private` directive tells the CDN not to cache this response. The `no-store` directive tells the browser not to cache it either. Both are needed because omitting `no-store` could allow the browser to store the response in its local cache, which is a security concern on shared devices.

For the checkout POST: `Cache-Control: no-store`. POST requests are not cached by CDNs by default, but making this explicit prevents any unusual CDN behavior. More important: ensure the endpoint has idempotency key support (via a client-generated idempotency key in the request header) so that a network retry cannot create a duplicate order.

For the product image: `Cache-Control: public, max-age=31536000, immutable`. Same logic as the JS bundle — the URL is stable and the content never changes at that URL.

---

### Exercise 4: Rate Limiter Design at Scale

**Requirements**

- 50 million users
- Per-user limit: 1,000 API calls per hour
- Per-user burst limit: 10 calls per second
- Peak throughput: 500,000 requests per second across the system

**Design the following components in writing**

1. The Redis data structure and commands for the per-user hourly limit. Include the key naming convention, the commands executed on each request (showing the full command sequence), and the time complexity per request.

2. The Redis data structure for the per-user burst limit. Explain how you represent the time window and how you clean up stale entries.

3. The Redis Cluster sharding strategy. How do you ensure all rate limit keys for a given user land on the same shard? Why does this matter for multi-key operations?

4. Failure handling: what does the system do when Redis is unavailable? Describe at least two strategies with their trade-offs on safety vs availability.

5. Multi-region complication: a user makes 800 calls to EU servers and then connects to US servers. How do you prevent them from getting an additional 1,000 calls in the US region within the same hour window?

**L6 depth hints**

For the hourly limit with a fixed window: `INCR ratelimit:{user:123}:hour:2024010215` (key includes the hour bucket), `EXPIRE` only on first increment (check return value of INCR — if it equals 1, call EXPIRE to set TTL of 3600 seconds). This is O(1) but allows boundary burst: a user can make 1,000 calls at 14:59:59 and another 1,000 at 15:00:01.

For the sliding window: `ZADD ratelimit:{user:123}:sliding <timestamp_ms> <request_uuid>`, `ZREMRANGEBYSCORE 0 <now_minus_one_hour_ms>`, `ZCARD`. This is O(log N + M) where M is the number of removed entries. More accurate but more memory-intensive — each entry stores a timestamp and UUID. At 1,000 entries per user, 50M users storing active rate limit data is 50 billion entries in the worst case — you would not store all of them simultaneously (most users are not near their limit).

For the hash tag: use `{user:123}` as the hash tag component, so Redis Cluster hashes only the user ID portion when determining the slot. This ensures `{user:123}:hourly` and `{user:123}:burst` land on the same slot, enabling MULTI/EXEC transactions across both keys.

For the multi-region problem: a global rate limiter in a single region is accurate but adds cross-region network latency (50–150ms) to every API call from the remote region — usually unacceptable. The practical trade-off is regional limits with a synchronization mechanism: each region enforces its own counter, and a background process periodically reconciles. Accept some over-limit requests at region boundaries in exchange for low latency.

---

### Exercise 5: Migrate from No Cache to Multi-Layer Cache

**Current state**

- A PostgreSQL database serving a product catalog
- 5,000 requests per second at peak
- 70% of queries are reads for the same 1,000 products (these are the popular products on the landing page and search results)
- Current latency: p50 = 120ms, p99 = 800ms
- Database CPU at 75% utilization at peak
- No caching anywhere in the stack; no code changes to the application are permitted (infrastructure-only changes)

**Goal**

- p50 latency target: 10ms
- p99 latency target: 100ms
- No schema or query changes to PostgreSQL allowed

**Design the migration plan step by step**

For each step: what do you add, what performance change do you expect, how do you validate success before proceeding, and what is the rollback plan if this step causes issues?

Include: the order in which you introduce each cache layer, how you warm each cache before putting traffic on it, and what monitoring dashboards you need at each stage.

**L6 depth hints**

Step 1 (highest leverage): Redis cache-aside for the top-1,000 product records. At 70% of 5,000 QPS, these products receive 3,500 QPS. At 95% hit rate, Redis absorbs 3,325 of those QPS. Database load drops from 5,000 to approximately 1,675 QPS — a 66% reduction. Validate by watching database QPS (should drop within minutes of enabling the cache) and Redis hit rate (should climb to 90%+ within 30 minutes as the cache warms).

Rollback for Step 1: a feature flag. If hit rate does not materialize or if cache latency is unexpectedly high, flip the flag to disable the cache layer and route all traffic to the database. Keep the flag for at least one week after confirming stability.

Step 2 (if needed after validating Step 1): add a CDN cache for product page HTML if your application serves server-rendered pages. The CDN deflects traffic before it reaches your application servers entirely. Validate by checking CDN hit rate in the CDN dashboard and watching application server request rate drop.

Step 3 (for extreme hot-key scenarios): in-process LRU cache on application servers for the top-100 products with a 5-second TTL. This eliminates the Redis network round-trip for the highest-volume keys. Validate by measuring p50 latency for requests that hit these specific product IDs — should approach 1ms or below.

Cache warm-up procedure: before enabling any cache layer for live traffic, run a warm-up job that reads all top-1,000 product records from the database and writes them to Redis. This prevents the cold-start period where all traffic hits the database while the cache fills. The warm-up job should run during low-traffic hours and complete before the cache layer is enabled.

---

## 5. Common Mistakes and Anti-Patterns

These are the answers that cost engineers the offer at L6 interviews. Most of them sound reasonable on the surface. The interviewer will probe, and the probe is where these answers fall apart.

---

### Anti-Pattern 1: Using Cache to Fix a Broken Query

**What it sounds like:** "The product page is slow. We'll add a Redis cache in front of the database."

**Why it fails:** If the page is slow because of a missing index or an N+1 query, adding a cache hides the problem instead of fixing it. The next feature will introduce a similar slow query. The cache layer grows in complexity. When the cache misses — during cold starts, after deployments, during stampedes — the broken query is still there, slower than ever.

**What L6 engineers say instead:**
- Profile first. Is the database the bottleneck, or is it network, a downstream service, or compute?
- If it is the database: is the query using indexes? Is it fetching more data than needed? Is there an N+1 pattern?
- Fix the root cause. Then add a cache if the data genuinely tolerates staleness and the volume justifies it.

---

### Anti-Pattern 2: One TTL for Everything

**What it sounds like:** "We'll set everything to expire in 1 hour. Simple, consistent, easy to reason about."

**Why it fails:** A 1-hour TTL is probably wrong for most of your data simultaneously. Stock prices need 30-second TTLs. User profile data can live for hours. Static configuration can be cached indefinitely and invalidated on deploy. A uniform TTL means some data is unnecessarily stale and some data is refreshed far more often than needed.

**What L6 engineers say instead:**
- Categorize data by: how often it changes, how badly staleness hurts, and what the cost of a miss is.
- Set TTLs per category, not per system.
- Add TTL jitter (±10–15%) to every key regardless of category to prevent synchronized expiry events.

---

### Anti-Pattern 3: No Plan for Cache Cold Start

**What it sounds like:** "When we deploy, the cache will warm up as traffic comes in."

**Why it fails:** During the warm-up window, all traffic hits the database directly. If you are deploying to fix a high-load incident, you deploy to an empty cache — and immediately reproduce the high-load conditions. Cold start can last 5–30 minutes depending on traffic volume and TTL length. For systems with high peak-to-trough ratios, cold start during off-peak hours may never fully warm the cache before peak hits.

**What L6 engineers say instead:**
- Run a pre-warm job before the cache layer opens to traffic.
- The warm-up job reads the top-N most-accessed keys from the database or from access logs and writes them to the cache.
- Deploy the warm-up job, verify hit rate is above 80%, then flip traffic to the cache layer.

---

### Anti-Pattern 4: Write-Through Without Thinking About Concurrency

**What it sounds like:** "We write to the cache and the database on every write. The cache is always current."

**Why it fails:** Under concurrent writes to the same key, the final cache value is determined by network timing and thread scheduling — not by which write is the most recent. As shown in Incident 5 (Robinhood), write A and write B can interleave such that the cache holds the value from write A even though write B was committed later in the database. The cache and database diverge silently.

**What L6 engineers say instead:**
- Write-through is safe only when writes to the same key are serialized.
- Under concurrency, use CDC-driven cache invalidation: database is the source of truth, and cache is updated from the database's commit log in commit order.
- Or use versioned keys: include a monotonically increasing version in the key name, and never overwrite a higher-version key with a lower-version one.

---

### Anti-Pattern 5: Forgetting the CDN Is a Security Boundary

**What it sounds like:** "We'll cache all API responses at the CDN to reduce origin load."

**Why it fails:** If any of those API responses are user-specific or access-controlled, caching them at the CDN (a shared cache) serves one user's data to a different user. The bug in GitHub's 2020 incident was exactly this: `Cache-Control: public` on a private repository page. The CDN behaved correctly according to the HTTP spec — it was the application that was wrong.

**What L6 engineers say instead:**
- Explicitly enumerate which endpoints are safe to cache at a shared CDN and which are not.
- Default to `Cache-Control: private, no-store` for any authenticated or user-specific response.
- Add CI validation that scans Cache-Control headers on known private endpoints and fails the build on misconfiguration.
- Never assume "the CDN will know not to cache this." It will cache exactly what the headers tell it to cache.

---

### Anti-Pattern 6: Alerting at 90% Redis Memory

**What it sounds like:** "We'll alert the on-call engineer when Redis memory hits 90%."

**Why it fails:** By the time Redis is at 90% memory, you have very little time before you hit the eviction storm. During a traffic spike, the gap between 90% and 100% can close in minutes. The on-call engineer wakes up to the alert, opens their laptop, reads the runbook, and by then the eviction storm has already started. Presence keys are being evicted. Rate limit counters are being evicted. Users are experiencing degradation.

**What L6 engineers say instead:**
- Alert at 70% memory with a warning (investigate, plan to add capacity).
- Alert at 80% with a higher-severity (may need to take action today).
- Alert at 90% as a critical incident (immediate action required, degradation may already be occurring).
- The 70% alert gives you time to act before users are affected.

---

### Anti-Pattern 7: Treating Cache Failure as Graceful Degradation by Default

**What it sounds like:** "If Redis goes down, requests just go to the database. It degrades gracefully."

**Why it fails:** "Graceful degradation" assumes the database can handle the redirected load. If your cache has a 95% hit rate and absorbs 19× the database's capacity, then cache failure means the database receives 20× its normal load. That is not graceful degradation — that is a guaranteed database failure. Graceful degradation requires explicit modeling of the blast radius.

**What L6 engineers say instead:**
- Model the blast radius before launch: if cache hit rate is X% and cache goes down, what QPS hits the database? Can the database handle it?
- If the database cannot handle the redirected load: add a circuit breaker that serves stale data instead of hammering the database.
- Size the database with capacity for "cache-down" operation as a defined, tested failure mode — not an assumption.

---

## 6. Interview Day Mindset

### How to Open a Caching Question

When an interviewer describes a slow endpoint or a scalability problem, resist the reflex to say "cache it" in the first 30 seconds. Instead, open with diagnostic questions. This signals that you think before you build — which is exactly what L6 engineers do.

The opening frame:

1. "Before I propose a caching solution, can I ask a few questions about the current system?"
2. "What is the actual bottleneck — is it database read latency, write contention, network, or computation?"
3. "Does this data change frequently, and how badly do users notice if they see a slightly stale value?"
4. "What is the expected request pattern — is this read-heavy, or does every read have a corresponding write?"

Once you establish that a cache is warranted, move through the design in this order:
- What data to cache (not everything, just the hot path)
- Where to cache it (CDN, Redis, in-process — or a layered combination)
- What the key structure is (avoid hot keys, consider namespacing)
- What the TTL is (per data type, with jitter)
- What the invalidation strategy is (TTL-only, event-driven, or write-through)
- What the failure mode looks like (blast radius, circuit breaker, stale fallback)
- How you measure success (hit rate target, alert thresholds, dashboards)

### What Interviewers Listen For at L6

Interviewers at L6 are not listening for the right answer. They are listening for the right reasoning process. Specifically, they watch for:

- **Quantification before architecture.** An L6 engineer says "at 95% hit rate, the database receives 250 QPS" before drawing a box labeled Redis. They have numbers, not just boxes.
- **Failure mode awareness.** An L6 engineer proactively describes what happens when the cache is empty, when it is full, when it fails, and when concurrent writes race. They do not wait to be asked.
- **Staleness as a first-class concern.** An L6 engineer specifies the acceptable staleness window for each piece of data and explains why. They do not treat "consistent" as binary.
- **Operational reality.** An L6 engineer mentions Sentinel failover time, alert thresholds, eviction policies, and key TTL jitter. They are designing something they would actually operate, not just something that fits on a whiteboard.

### The One Sentence That Wins Points Every Time

At some point in the caching discussion, say this: "The cache is not the source of truth — the database is. The cache is an optimization with a defined staleness window. When cache and database disagree, the database wins."

This one sentence demonstrates that you understand caching as an architectural trade-off, not a magic performance button. It is the sentence that distinguishes engineers who have operated caches in production from engineers who have only read about them.

---

## 7. Quick Reference Card

Use this as a pre-interview checklist and as a mental model during the design discussion.

### Cache Pattern Selector

| Scenario | Pattern | Reason |
|----------|---------|--------|
| Read-heavy, data changes rarely (product descriptions, static config) | Cache-aside with a long TTL | Simplest to implement; application handles miss logic; staleness is tolerable |
| Data must be fresh immediately after every write (user profile, permissions) | Write-through | Cache is always current after write; adds write latency; requires serialization under concurrency |
| Write-heavy workload, batch DB persistence acceptable (logging, counters) | Write-behind (write-back) | Absorbs write bursts; reduces DB write pressure; risk of data loss if queue crashes |
| Cache miss is expensive (downstream API call, heavy computation) | Read-through | Cache layer handles miss logic transparently; application treats cache as the data layer |
| Frequent updates, strict freshness required (account balance, inventory during flash sale) | No cache or very short TTL (5–10 seconds) | Cache adds complexity and staleness risk without proportional benefit |

### Key Numbers for Interviews

| Metric | Value |
|--------|-------|
| Redis single-instance throughput | 100,000 – 200,000 ops/sec |
| Redis get/set latency (same data center) | 0.5 – 1ms |
| L1 CPU cache access time | ~0.5ns |
| L2 CPU cache access time | ~7ns |
| Main memory (DRAM) access time | ~100ns |
| CDN PoP latency to a nearby city | 5 – 20ms |
| Cross-continental network round-trip | 80 – 150ms |
| Redis Sentinel failover time | 10 – 30 seconds |
| Bloom filter memory for 100M keys (1% false positive rate) | ~120MB |
| Target cache hit rate for a well-tuned system | > 90% |
| Redis memory alert threshold | > 70% utilization |
| Redis Cluster recommended per-shard dataset size | < 25GB |
| Recommended Redis memory headroom at steady state | 40 – 50% free |
| CDN cache hit rate for static assets (real-world) | 85 – 99% |
| CDN tag-based purge propagation time | 5 – 30 seconds (provider-dependent) |

### The Three Questions to Ask Before Adding Any Cache

**Before proposing a cache in an interview, say these three things — they signal L6 thinking.**

First: "Why is this slow? Have we profiled it? Is the database actually the bottleneck, or is it a slow external API call, a missing index, an N+1 query pattern, or a computation-heavy transformation that should be optimized before adding infrastructure?"

Second: "Does this data tolerate staleness? For how long? What happens to users if they see a value that is 30 seconds old? 5 minutes? 1 hour? Different parts of the same page have different staleness tolerances — be precise about which data you are caching and what the acceptable window is."

Third: "What is the invalidation strategy? How do we guarantee that the cache reflects reality after a write? What is the worst-case staleness window if a write and an invalidation race? Is that window acceptable to the business?"

If you cannot answer all three clearly, you are not ready to add the cache. This is the most reliable signal that separates an L5 engineer who adds caching because it is the obvious next step from an L6 engineer who treats every cache as an architectural decision with a specific problem statement, a defined consistency model, and a measured success criterion.

---

*End of Chapter 31.*
## Supplemental Brainstorming: Chapter 31 -- Caching at Scale

*Questions 6-52: Complete topic coverage and cross-chapter integration.*

*These questions extend the five questions already in the main chapter. They are organized by topic cluster so you can drill any area independently or use the cross-chapter section for integrated review.*

---

### Section A: Cache Fundamentals and Math (Q6-Q14)

---

**Question 6 -- Hit rate math and the miss penalty equation**

Your application makes 10,000 requests per second to a cached user-profile service. Redis hit rate is 85%. Each cache hit costs 1ms. Each cache miss costs 40ms (a full database round-trip). A product manager asks: "Is our caching working well?" You need to give a quantitative answer.

- Calculate the average request latency at 85% hit rate. Formula: (hit_rate x hit_cost) + (miss_rate x miss_cost). At 85%: (0.85 x 1ms) + (0.15 x 40ms) = 0.85 + 6.0 = 6.85ms average.
- Compare to the two extremes: 0% hit rate (100% misses) = 40ms average; 100% hit rate = 1ms average. At 85%, you are at 6.85ms -- much closer to 40ms than to 1ms. This surprises most people: an 85% hit rate is not "mostly good." The 15% misses dominate because the miss penalty (40ms) is 40x the hit cost (1ms).
- The miss penalty ratio determines how much each percentage point of hit rate improvement is worth. If miss cost is 40x hit cost, moving from 85% to 90% hit rate cuts average latency from 6.85ms to 4.9ms -- a 28% improvement from just 5 percentage points. Moving from 90% to 95% cuts from 4.9ms to 2.95ms -- another 40% improvement.
- Follow-up: Your miss cost is 200ms instead of 40ms (database is overloaded). Now at 85% hit rate, average latency is (0.85 x 1) + (0.15 x 200) = 30.85ms. The cache is "working" but the system is still slow. What does this tell you about diagnosing cache problems?

---

**Question 7 -- The minimum hit rate that justifies a cache**

You are evaluating whether to keep a Redis cache in front of a PostgreSQL database. Redis costs $500/month to run. Without Redis, the database needs to be upgraded to handle full traffic -- estimated at $800/month extra. But adding Redis introduces operational complexity (one more system to monitor, incidents to handle, engineers to train). What is the minimum hit rate that makes Redis worth keeping?

- The financial break-even is easy: if Redis saves $800/month in database costs and costs $500/month itself, you need it to actually provide $300/month in net savings. But operational complexity is harder to price. If Redis causes one extra incident per month and each incident costs 4 engineering-hours at $150/hour blended rate, that is $600/month in hidden cost -- more than the financial savings.
- The minimum viable hit rate depends on your system's miss penalty ratio. If your database can handle 100% of traffic without degradation, the hit rate needed to justify Redis is theoretically infinite -- the cache adds no reliability benefit, only cost. Redis is only clearly justified when either (a) the database cannot handle full traffic or (b) hit rate is high enough that latency savings have direct revenue impact (e.g., e-commerce where 100ms = 1% conversion loss).
- Rule of thumb that experienced engineers use: below 70% hit rate, question whether your cache key design is wrong (you are caching things that are not actually reused). Between 70-90%, the cache is helping but there is room to improve. Above 90%, the cache is well-designed for your access patterns. Below 50% hit rate, the cache may be making things worse by adding latency to every request (cache lookup + miss + DB lookup > just DB lookup).
- Follow-up: You discover your hit rate is 40% because your cache key includes a user-specific timestamp that changes every request. This means almost every request is a unique key that will never be hit again. How do you redesign the key space? What is the principle that this illustrates about cache key granularity?

---

**Question 8 -- Cache sizing: how big should the cache be?**

You are building a product recommendation service. The product catalog has 5 million items. Each item's recommendation list is 2KB of JSON. You want to cache as many recommendation lists as possible in Redis. Your Redis instance has 10GB of RAM. Redis uses approximately 70% of allocated RAM for data (30% overhead for internal structures). How many items can you cache, and what hit rate should you expect?

- Usable RAM: 10GB x 0.70 = 7GB = 7,340,032 KB. Each item is 2KB. Maximum cached items: 7,340,032 / 2 = approximately 3.67 million items out of 5 million total -- 73% of the catalog.
- If access follows a Zipf distribution (the top 20% of items get 80% of traffic), then caching 73% of the catalog means you cover essentially all high-traffic items and most medium-traffic items. Expected hit rate: likely 85-92%, because the 27% of items you cannot cache are the long-tail items that get minimal traffic.
- If access were perfectly uniform (every item equally likely), caching 73% of items gives a 73% hit rate -- much worse. The key insight is that real-world access is almost always skewed. Cache sizing math only makes sense when you combine it with your access distribution.
- Follow-up: Your Redis is full (3.67M keys) and eviction kicks in. With LRU eviction, what is evicted? With LFU eviction, what is evicted? Which policy is better for the recommendation use case where popular items should stay cached and long-tail items should be evicted? What Redis config parameter controls this?

---

**Question 9 -- When NOT to cache: the five anti-patterns**

A junior engineer proposes caching every database query result in Redis "to make everything faster." As the staff engineer, you need to explain the five situations where adding a cache makes things worse, not better.

- Anti-pattern 1 -- Unique data per request: If each request produces a unique result (e.g., "get all transactions for user 42 with custom date range filter"), the cache key is unique to each call. Hit rate approaches 0%. Every request pays the cost of a cache lookup (1ms) plus a database query (20ms) instead of just a database query (20ms). The cache adds latency without any benefit.
- Anti-pattern 2 -- Highly mutable data with zero-staleness requirement: Financial account balances, inventory counts during a purchase, seat availability for an event 10 seconds before it sells out. Any staleness causes incorrect behavior. The "freshness" requirement eliminates the core benefit of caching.
- Anti-pattern 3 -- Write-heavy workloads: If a value is written 1,000 times per second and read 500 times per second, you spend more time invalidating and repopulating the cache than you save on reads. The write-to-read ratio is inverted -- caching makes sense when reads dominate.
- Anti-pattern 4 -- Very fast origin: If your database query runs in 0.5ms (because the data is already in PostgreSQL's shared_buffers page cache), and Redis takes 1ms round-trip, the cache is slower than the origin. Cache only makes sense when the origin is materially slower than the cache layer.
- Anti-pattern 5 -- Large fanout invalidation: If updating one record requires invalidating 50,000 cache keys (e.g., a category name change that affects all products in that category), the invalidation cost itself becomes a performance problem. The cache is correct but managing it is expensive.
- Follow-up: You have a search results cache. The query "iphone 14 case black" is run by 10,000 different users but with slightly different filter combinations, so each generates a different cache key. Hit rate is 3%. What is the right caching strategy here? (Hint: cache the component parts, not the assembled result.)

---

**Question 10 -- Negative caching: caching "not found" results**

Your user service receives 1 million requests per second for user profiles. 30% of those requests are for user IDs that do not exist (bots probing for valid accounts, deleted accounts, old links). Every non-existent user ID misses the cache (because there is nothing to cache) and hits the database for a SELECT that returns 0 rows. This SELECT still costs 5ms each, and 300,000 of them per second is overwhelming the database. Design a negative caching strategy.

- Cache the absence: when the database returns 0 rows for user ID 99999, store the key "user:99999" with a sentinel value (null, empty string, or a special "NOT_FOUND" marker) in Redis. Set a short TTL -- 60 seconds is typical for negative cache entries. The next request for user 99999 within that 60 seconds gets a cache hit (returning the sentinel), skips the database, and returns a 404 to the caller in 1ms instead of 5ms.
- TTL tuning for negative entries: negative cache TTLs should be shorter than positive cache TTLs. A user profile might be cached for 5 minutes, but a "user not found" entry should be cached for 30-60 seconds. Why? Because a user account can be created at any moment. If you cache "not found" for 5 minutes, a newly created account will get 404 responses for 5 minutes -- a poor user experience. Short negative TTLs bound the staleness window.
- Watch for the attack surface: negative caching changes your security posture. An attacker who knows your system has negative caching can deliberately probe 10 million unique user IDs to fill your Redis with negative cache entries, exhausting your memory. Solutions: use a Bloom filter to pre-check if a user ID could possibly exist before touching Redis or the database; use a separate lower-priority cache namespace for negative entries with a smaller memory allocation and more aggressive eviction.
- Follow-up: You implement negative caching. A user deletes their account. Their profile was previously cached with a 5-minute TTL as a positive entry (real data). After deletion, the database has no record. But the cache still has the old positive entry. For up to 5 minutes, your system serves data for a deleted account. How do you handle account deletion to avoid this? What does this illustrate about cache invalidation being a two-sided problem?

---

**Question 11 -- Cache hit rate diagnosis: why is your hit rate low?**

Your Redis cache for a product catalog has been running for 3 weeks. You expected 85% hit rate but you are seeing 55%. The product catalog has 200,000 products. You are caching product detail pages. Walk through the diagnostic process to identify why hit rate is low.

- Step 1 -- Key inspection: Use `redis-cli --scan --pattern "product:*" | head -100` to sample actual keys. Are they what you expect? Do you see keys like "product:42" (good -- reusable) or "product:42:user:789:session:abc" (bad -- session-specific cache keys that can never be hit again)? If keys include per-user or per-session components, you have a key design bug, not a cache sizing problem.
- Step 2 -- TTL analysis: Use `redis-cli --scan --pattern "product:*" | xargs -I {} redis-cli TTL {}` to sample TTLs. Are they what you configured? If TTLs are 60 seconds instead of the intended 3600 seconds, products are expiring 60x faster than intended, causing far more misses. Configuration bugs are surprisingly common.
- Step 3 -- Eviction check: Run `redis-cli INFO stats | grep evicted_keys`. If eviction rate is high, your cache is full and items are being evicted before they can be hit. The solution is either more memory or a different eviction policy. Also check `redis-cli INFO memory` for `used_memory` vs `maxmemory`.
- Step 4 -- Access pattern analysis: If keys and TTLs are correct and eviction is not occurring, your access pattern may simply not be cacheable. Run a sample of what product IDs are being requested. If they are uniformly distributed across 200,000 products, hit rate is mathematically bounded by (cache_size / catalog_size). With 10GB of cache and 200,000 products at 5KB each (1GB total catalog), you have room for all products -- so uniform access should give near-100% hit rate after warm-up.
- Follow-up: You discover the hit rate is low because your deployment system restarts the application servers every 6 hours, and each restart flushes the local in-process cache. The Redis cache has high hit rate, but the application is bypassing Redis on every new app server instance for the first 10 minutes. What is the correct fix? (Hint: the answer involves understanding the difference between L1 local cache and L2 Redis cache.)

---

**Question 12 -- The effective latency calculation for a cache hierarchy**

You have a two-tier cache: an in-process LRU cache (L1, 500ms average hit time -- wait, 0.5ms) and a Redis cache (L2, 2ms average hit time). Database queries take 30ms. L1 hit rate is 40%. Of the L1 misses, L2 hit rate is 75%. Calculate the average effective latency seen by requests, and explain what the numbers tell you about where to invest optimization effort.

- Break it into segments. Of all requests: 40% hit L1 (cost: 0.5ms each). 60% miss L1. Of those 60%, 75% hit L2 (cost: 2ms each) = 45% of all requests. Of the 60% that miss L1, 25% miss L2 too (cost: 30ms each) = 15% of all requests.
- Average latency: (0.40 x 0.5ms) + (0.45 x 2ms) + (0.15 x 30ms) = 0.2 + 0.9 + 4.5 = 5.6ms average.
- The 15% that go to the database contribute 4.5ms out of 5.6ms total average -- 80% of the total latency load. The 40% that hit L1 contribute only 0.2ms. So improving the database hit path (those 15% of requests) has dramatically more impact than improving L1 hit rate. If you increase L2 hit rate from 75% to 90%, the DB-miss rate drops from 15% to 6%, and average latency becomes (0.40 x 0.5) + (0.54 x 2) + (0.06 x 30) = 0.2 + 1.08 + 1.8 = 3.08ms -- a 45% improvement.
- This is the key insight of layered cache math: the deepest, most expensive layer dominates the average, even if it handles the smallest percentage of requests. Optimize the miss path first.
- Follow-up: You are asked to increase L1 cache size (in-process RAM) from 200MB to 500MB to raise L1 hit rate. An alternative is to add a second Redis replica to reduce Redis latency from 2ms to 1ms. Which investment improves average latency more? Work through the math for both.

---

**Question 13 -- Cache stampede probability: the math**

Your system has 1,000 application server instances all making requests to the same product catalog cache. The cache entry for "top-100-trending-products" expires at 2pm. Requests arrive at 5,000 per second. The TTL is exactly 3,600 seconds (1 hour). Calculate the probability that a cache stampede occurs when the key expires, and explain the three engineering solutions with their trade-offs.

- Probability of stampede: when the key expires, all requests for that key that arrive before the cache is repopulated will miss and hit the database. The repopulation time (database query time) is 200ms. At 5,000 requests/second, in 200ms you get 1,000 requests that all miss. All 1,000 hit the database simultaneously. This is a guaranteed stampede every hour, on the hour.
- Solution 1 -- Probabilistic early expiration (also called "jitter + early recompute"): Instead of every instance waiting for the TTL to expire, each instance independently decides to recompute early with probability P = e^(-beta * remaining_TTL). Tuning beta controls how early recomputation starts. This ensures the value is recomputed before it expires, so the stampede never happens. Trade-off: the cache entry is refreshed slightly early, so staleness is slightly reduced (a benefit) but computation runs more often (a small cost).
- Solution 2 -- Mutex / lock-based recomputation: When a cache miss occurs, the first instance to notice sets a distributed lock (using Redis SET NX with TTL). Only the lock-holder queries the database and repopulates the cache. All other instances that miss see the lock is held and either (a) wait briefly and retry, or (b) serve a stale value if one is available. Trade-off: correctly implementing distributed locks with proper expiry and failure handling is complex. If the lock-holder crashes mid-recomputation, the lock must expire automatically and another instance must take over.
- Solution 3 -- Stale-while-revalidate: The cache stores the value with two TTLs: a "freshness TTL" (3,600 seconds) and a "max staleness TTL" (7,200 seconds). When the freshness TTL expires, one request triggers a background recomputation but the cache continues serving the stale value to all other requests until the recomputation completes. After recomputation, the stale value is replaced. Trade-off: callers explicitly see stale data for the recomputation window. Acceptable for trending products (stale by 1-5 seconds is fine). Not acceptable for account balances.
- Follow-up: You implement mutex-based locking. The lock TTL is 30 seconds. The database query takes 3 seconds. A deployment happens mid-day and kills the lock-holder process after 1 second. The lock is held for 29 more seconds. All 1,000 app servers are either blocked waiting or serving no data. What is the correct lock TTL, and how do you handle the case where lock expiry is too short vs too long?

---

**Question 14 -- Cache coherence in distributed systems**

You have 20 application servers. Each has a local in-process cache (L1) caching user preferences. A user changes their notification preferences from "email" to "none." The change is written to the database. How does this change propagate to all 20 in-process caches, and what are the three coherence strategies with their failure modes?

- The problem: each of the 20 servers has its own copy of user 42's preferences cached locally. The database now has the new value. The 19 servers that did not handle the write request still have the old value. Requests that land on any of those 19 servers for the next TTL period will serve the old "email" preference. The user will receive notification emails they explicitly asked to stop.
- Strategy 1 -- TTL-based expiry: Set a short TTL (e.g., 30 seconds) on preference cache entries. Each server naturally expires its local copy within 30 seconds. After expiry, the next request re-fetches the latest value from Redis or the database. Simple. Requires zero inter-server coordination. Trade-off: the user receives unwanted emails for up to 30 seconds after making the change. Acceptable for preferences. Not acceptable for security-sensitive data (e.g., "account suspended" status).
- Strategy 2 -- Pub/sub invalidation: When the database write completes, publish an invalidation event to a Redis pub/sub channel ("user:42:preferences:invalidated"). All 20 app servers subscribe to this channel. Each one deletes its local copy of user 42's preferences immediately. Trade-off: the pub/sub message must be delivered reliably. Redis pub/sub is fire-and-forget -- if a server is briefly disconnected when the message fires, it misses it and keeps the stale value. Use Redis Streams (persistent) instead of pub/sub for guaranteed delivery.
- Strategy 3 -- Version-based cache keys: Cache user 42's preferences under the key "user:42:preferences:v7" where v7 is the current version number stored in the database. When preferences change, the database increments the version to v8. The next request for user 42 constructs the key "user:42:preferences:v8", which does not exist in the cache, forcing a cache miss and a fresh database read. Old key "user:42:preferences:v7" expires naturally. Trade-off: requires an extra database read to get the current version number on every request -- which may negate the performance benefit of caching.
- Follow-up: You use pub/sub invalidation. A network partition isolates 5 of your 20 app servers for 2 minutes. During those 2 minutes, 300 preference changes occur. When the partition heals, those 5 servers have no knowledge of any of the 300 invalidation events. They will serve stale preferences for all 300 changed users until their TTLs expire. How do you design the system to detect and recover from this "missed invalidation" scenario?

---

### Section B: Cache Patterns Deep Dive (Q15-Q22)

---

**Question 15 -- Cache-aside vs read-through: when does the distinction matter?**

Two teams at your company implement user profile caching differently. Team A uses cache-aside: application code checks the cache, on miss fetches from DB, then writes to cache. Team B uses read-through: the cache itself knows how to fetch from the database on a miss, transparently. Both work correctly in steady state. Under what conditions does the distinction between these two patterns create materially different behavior, and which should you use?

- Cold start behavior: with cache-aside, the application code handles the miss -- it has full context about what went wrong and can add retry logic, fallback logic, or circuit breaking. With read-through, the cache infrastructure handles the miss. If the database is down during a miss, the read-through cache may throw an exception that your application code is not designed to handle cleanly, because it expected the cache layer to always succeed. Cache-aside makes the failure mode explicit in application code.
- Consistency window: with cache-aside, there is a race condition on write. After a write to the database, if two requests simultaneously miss the cache and both fetch from the database, both will write to the cache -- the second write overwrites the first, and you may have a brief inconsistency. Read-through caches often use internal locking to prevent this (only one fetch per cache miss). For high-concurrency workloads on the same key, read-through provides better consistency.
- Deployment and testing: cache-aside logic lives in your application code -- you can test it, mock the cache, and deploy changes independently. Read-through logic lives in a cache plugin or middleware -- it is often harder to test, harder to customize, and creates a tighter coupling between your caching layer and your data layer. For most teams, cache-aside is the pragmatic choice because it is transparent and testable.
- Follow-up: You decide to switch from cache-aside to read-through for a heavily accessed key. During the switchover, your old application code still writes to the cache after database writes (part of cache-aside). Your new read-through middleware also writes to the cache on misses. You now have two code paths writing to the same cache key simultaneously. How do you manage the transition, and what is the risk of running both patterns in parallel?

---

**Question 16 -- Write-through vs write-behind: correctness and performance trade-offs**

Your e-commerce platform updates product view counts. Each product view triggers a write (increment the view count). You have 10,000 writes per second. You are evaluating write-through (every write goes to cache AND database synchronously) versus write-behind/write-back (write to cache immediately, defer database write). Design both and explain where each breaks.

- Write-through: every increment writes to Redis first, then to PostgreSQL within the same request. Latency per write: Redis write (1ms) + PostgreSQL write (5ms) = 6ms total. At 10,000 writes/second, PostgreSQL handles 10,000 writes/second -- no problem for a well-tuned database. Data is always consistent between cache and database. If the service crashes, no writes are lost. Trade-off: write latency is dominated by the slower system (PostgreSQL). You cannot do better than 5ms per write regardless of cache speed.
- Write-behind: every increment writes to Redis immediately (1ms). A background worker reads the Redis write queue and batches writes to PostgreSQL every 5 seconds. At 10,000 writes/second, write latency is 1ms from the user's perspective. But in each 5-second window, you accumulate 50,000 view count increments that are not yet in the database. If the Redis instance crashes in that window, those 50,000 increments are lost forever. View counts are wrong by up to 50,000.
- For view counts, write-behind is acceptable: losing some view count data in a crash is a tolerable business risk. For order quantities or financial data, write-behind is not acceptable. The durability trade-off is a product decision, not just a technical one.
- Key implementation detail for write-behind: do not write the raw increment events to the queue. Write idempotent state ("product 42 view count = 9,842,001") rather than operations ("increment product 42 by 1"). This makes replaying the queue after a partial failure safe -- replaying an idempotent state write is safe; replaying 50,000 increments may double-count if some already landed.
- Follow-up: Your write-behind worker falls behind. It has a backlog of 200,000 queued writes. A deploy restarts the worker. It begins processing from the tail of the queue (newest first). The oldest writes in the queue are now 30 minutes old. If you process newest-first, the database may never receive the older writes if the queue keeps growing. How do you design the worker to handle backlog without losing old writes and without double-applying writes?

---

**Question 17 -- TTL design: short TTL vs long TTL trade-offs**

Your product description cache uses a 5-minute TTL. The operations team argues it should be 24 hours to reduce database load. The engineering team argues it should be 30 seconds to reduce staleness risk. Design the TTL selection framework and explain what happens at each extreme.

- At 30-second TTL: a product description that is never changed will be fetched from the database 2,880 times per day per key. If you have 200,000 products and 5 application servers, each server re-fetches every product every 30 seconds -- 200,000 / 30 = ~6,667 database queries per second just for cache misses. Your database has to handle the read load as if caching were barely helping.
- At 24-hour TTL: a product description that is updated (e.g., a price correction) at 10am will continue to serve the old price until 10am the next day to any user who was cached before the update. In e-commerce, showing a wrong price for 24 hours is a legal and financial problem. You cannot use long TTLs without a parallel invalidation mechanism.
- The right framework: TTL should be set based on the "maximum acceptable staleness window" for the data type, NOT based on cache efficiency targets. Efficiency is a secondary concern. If product prices can be wrong for at most 5 minutes (your business decision), set TTL to 5 minutes. Then separately investigate whether 5-minute TTL creates unacceptable database load. If it does, add explicit invalidation (delete the cache key on write) so that updates take effect immediately AND the TTL serves only as a safety net for missed invalidations.
- TTL jitter: if you set TTL to exactly 3,600 seconds for all product keys, and you load 200,000 keys at startup at time T=0, all 200,000 keys expire simultaneously at T=3,600. This causes a cache stampede every hour. Add random jitter: TTL = 3,600 + random(0, 300). Keys now expire spread across a 5-minute window instead of all at once.
- Follow-up: You implement jitter correctly. Three days later, you notice the database has a periodic spike every hour, but it is spread across a 5-minute window rather than instantaneous. The total query volume in that 5-minute window is still very high. What does this tell you, and what is the correct fix? (Hint: the problem is the key loading pattern, not the TTL itself.)

---

**Question 18 -- Explicit cache invalidation: event-driven cache purging**

You have a content management system where editors publish articles. An article's rendered HTML is cached in Redis for 1 hour. An editor fixes a factual error in a published article. The fix must appear to all users within 10 seconds -- not within the next hour. Design the explicit invalidation system.

- Trigger point: the invalidation must be triggered by the write event. When the editor hits "save," the CMS writes the updated article to the database AND issues a cache delete command to Redis: `DEL article:rendered:4521`. From that point forward, any new request for article 4521 misses the cache and fetches the updated version from the database.
- Multi-level invalidation: if your system also has a CDN in front of Redis (e.g., CloudFront or Fastly caching the final HTTP response), the Redis delete alone is not enough. The CDN still has the stale rendered page cached at its edge nodes. You must also issue a CDN purge API call. Most CDNs support purge-by-URL or purge-by-cache-tag. Cache tags are more powerful: you tag the rendered article page with "article:4521" and can purge all cached objects with that tag in one API call.
- Failure handling: what if the cache delete fails? The Redis DELETE command failed (network blip). The article is now updated in the database but the cache still has the old version. Users will see the wrong version for up to 59 more minutes. Mitigation: use a write-through pattern where the invalidation is retried with exponential backoff. Or: after the database write, issue both DELETE and SET with a 10-second TTL (forcing expiry within 10 seconds regardless of the delete succeeding).
- Follow-up: You have 50 different article pages that embed a "related articles" widget. When you publish a new article, the "related articles" widget on each of those 50 pages must be invalidated, because the new article should appear in their related list. You now have 1 publication event that requires 51 cache invalidations (1 for the article itself + 50 for related pages). This is called "cache fanout." How do you design the invalidation system to handle fanout without creating a synchronous bottleneck in the publish flow?

---

**Question 19 -- Versioned cache keys as an invalidation strategy**

Your team is debating between TTL-based invalidation and versioned keys for a user settings cache. With TTL, stale data can live for up to 5 minutes. With versioned keys, you cache under "user:42:settings:v15" and increment the version on every write. A junior engineer says versioned keys are better because data is never stale. A senior engineer says TTL is better because versioned keys have a hidden complexity cost. Who is right, and what is the actual trade-off?

- The junior engineer is partially correct: versioned keys ensure the application always sees the latest data because the version number (from the database) generates a unique key that only exists after the write. There is no window of staleness. For security-sensitive data (user permissions, account suspension status, payment methods), zero-staleness is a hard requirement. Versioned keys deliver this.
- The senior engineer is also partially correct: versioned keys create "orphaned keys." After user 42's settings are updated and the version moves from v15 to v16, the key "user:42:settings:v15" still lives in the cache until its TTL expires. If each user has 1,000 setting updates per day and you cache 1 million users, you accumulate 1 billion stale orphaned keys per day in your cache. Redis memory explodes. You need TTLs on versioned keys anyway -- you just use them as a safety net for garbage collection, not as the primary freshness mechanism.
- The hidden complexity cost the senior engineer means: every request now requires reading the current version number from somewhere authoritative (the database or a "version counter" cache key). This is an extra network round-trip. You have traded the staleness problem for a latency problem. If the version lookup costs 1ms and your cache hit saves 10ms, the net saving drops from 10ms to 9ms per request. But the version lookup must never be cached with a long TTL (that recreates the staleness problem).
- Follow-up: Design a system that uses versioned keys for a user's security permissions (account_suspended, is_admin, rate_limit_tier) where zero staleness is required. How do you store the version counter, how do you look it up efficiently, and how do you handle the case where the version counter lookup fails (Redis is down)?

---

**Question 20 -- LRU vs LFU eviction: a concrete scenario**

Your Redis cache holds 1 million product detail pages. Memory is full. You are choosing between LRU (evict the least recently used key) and LFU (evict the least frequently used key). Your traffic pattern is: 95% of requests are for the top 10,000 "trending" products that change daily. The remaining 5% are spread across the long-tail 990,000 products, each accessed rarely. Which eviction policy is correct and why?

- LRU behavior: LRU evicts the key that has not been accessed for the longest time. In this scenario, the long-tail products (990,000 of them) are accessed rarely but sporadically. A long-tail product accessed once yesterday will sit in the LRU queue. If a trending product was not accessed in the last 2 minutes (e.g., its popularity just spiked), LRU may evict it in favor of keeping the long-tail product that was accessed yesterday. LRU cannot distinguish "accessed once three days ago" from "accessed once three minutes ago" -- it only considers recency.
- LFU behavior: LFU tracks access frequency (how many times a key has been hit, with a decay factor). Trending products accumulate high frequency counts quickly. Long-tail products have low frequency counts. When memory is full, LFU evicts the long-tail items first, keeping the high-frequency trending items. This is the correct behavior for your access pattern.
- When LRU is better: LRU outperforms LFU when your access pattern does not have persistent hot keys -- for example, a session cache where every session is accessed roughly uniformly. Or a news site during a breaking news event where different articles become "hot" for hours and then go cold forever. LFU's frequency counts would be dominated by yesterday's hot articles, causing it to keep stale-trending content and evict actually-trending new content. (Redis LFU uses a logarithmic counter with a decay function to mitigate this, but LRU is simpler and often better for bursty-then-cold patterns.)
- Follow-up: Redis offers `maxmemory-policy allkeys-lru` and `maxmemory-policy allkeys-lfu`. You want to run an A/B test to measure which policy gives you higher hit rate. You have two Redis instances, one per policy. How do you route requests fairly to compare them, and what metric do you track to declare a winner?

---

**Question 21 -- Hot key problem: diagnosis and solutions**

Your Redis monitoring shows one key -- "leaderboard:global" -- receiving 50,000 requests per second. All 500 application servers read this key every time a user views the home page. Redis is single-threaded for key operations. This single key is consuming 60% of your Redis CPU and causing 150ms tail latency on reads. Diagnose and fix the hot key problem.

- Diagnosis: use `redis-cli --hotkeys` (available in Redis 4.0+ with `maxmemory-policy` set to LFU) or `redis-cli MONITOR` (dangerous in production -- it outputs every command) or a sampling proxy like Twitter's Twemproxy or Envoy's Redis filter to detect hot keys without impacting Redis. Alternatively, instrument at the application layer: log the top-N most-requested keys and count requests per second.
- Solution 1 -- Local in-process cache (L1 caching): instead of every app server request going to Redis, each app server caches the leaderboard locally in memory (e.g., a Java HashMap or Python dict) with a short TTL (1-5 seconds). 500 app servers each cache the leaderboard locally. Redis now receives at most 500 requests per second (one per server per TTL expiry) instead of 50,000. Trade-off: up to 5 seconds of staleness for leaderboard data. For a global leaderboard, this is typically acceptable. The local cache requires no coordination.
- Solution 2 -- Key sharding (replication): store the leaderboard under multiple keys: "leaderboard:global:shard:0" through "leaderboard:global:shard:9". Each app server picks a shard at random (or based on server ID) and reads from that shard. The write path writes to all 10 shards. Redis now receives 5,000 requests per second per shard instead of 50,000 on one shard. Trade-off: writes become more complex (you must write to all shards). A write failure on any shard leaves shards inconsistent.
- Solution 3 -- Redis Cluster with key distribution: use Redis Cluster with multiple nodes. Use a hash tag to force the leaderboard onto a specific node currently. Remove the hash tag to allow natural distribution. But "leaderboard:global" is a single key -- you cannot distribute a single key across multiple nodes. Key sharding (solution 2) is required to actually spread the load.
- Follow-up: You implement local in-process caching with 5-second TTL. During a Redis deployment (rolling restart), the leaderboard key is deleted and takes 500ms to repopulate. During those 500ms, all 500 app servers simultaneously try to refresh their local caches and hit Redis. Your "hot key fix" has recreated a mini-stampede. How do you modify the local cache TTL strategy to avoid this?

---

**Question 22 -- Cache warm-up strategies for high-traffic systems**

You are launching a major product sale in 6 hours. Your Redis cache is currently empty (new deployment). You expect 500,000 requests in the first minute of the sale. Your database can handle 5,000 queries per second before degrading. If the cache starts cold, the first 60 seconds will send all 500,000 requests to the database -- 8,333 per second, nearly double the database's capacity. Design the cache warm-up strategy.

- Strategy 1 -- Offline pre-population: before launch, run a script that queries the database for the top 10,000 most-accessed products (based on historical traffic data) and loads them into Redis. This is a targeted warm-up of the most critical keys. Done 30 minutes before launch, the cache is already populated with high-traffic items before users arrive. Time to implement: a few hours. Risk: the pre-population list may miss newly trending items.
- Strategy 2 -- Traffic replay: capture a sample of real traffic from the previous day (using access logs) and replay it against the new Redis instance at 10x speed before launch. The cache warms up with the actual keys that were popular yesterday. This is more accurate than a static list but requires infrastructure to capture and replay traffic. Tools: Apache JMeter, custom scripts, or a shadow traffic system.
- Strategy 3 -- Gradual traffic shift: instead of sending 100% of traffic to the new Redis-backed system at launch, use a load balancer to send 5% of traffic to the new system and 95% to the old system. The 5% of traffic warms the cache over 5-10 minutes. Then shift to 20%, then 50%, then 100%. At each stage, monitor cache hit rate and database load. This requires feature flag infrastructure or canary deployment capability.
- Strategy 4 -- Dual-read during warm-up (shadow reads): for the first 30 minutes, serve all requests from the database AND simultaneously write results to the cache. This is equivalent to cache-aside with a deliberately short warm-up period. But limit the database write rate with a token bucket so that warm-up traffic does not overwhelm the database. Once hit rate exceeds 70%, switch to standard cache-aside.
- Follow-up: You warm the cache successfully. The sale launches, hit rate is 92%, everything is fine. Three hours into the sale, a Redis node fails and the cluster promotes a replica. The replica has been receiving writes for 3 hours (replication lag: <1 second). Hit rate drops to 89% temporarily. Is this the Redis failure mode you should be worried about, or is there a more dangerous failure scenario to design for?

---

### Section C: Cache Problems at Scale (Q23-Q30)

---

**Question 23 -- Thundering herd: the complete scenario**

Your API gateway caches the list of available payment methods for each country. The cache for "payment_methods:US" expires at exactly midnight. At midnight, you have 3,000 concurrent users in the US going through checkout. All 3,000 simultaneously miss the cache and issue a database query for US payment methods. Each query takes 800ms (the database is suddenly under load). During those 800ms, 4,000 more requests arrive and also miss the cache, because the cache has not been repopulated yet. Your database receives a spike of 7,000 queries for the same data. Walk through the thundering herd in slow motion and design the prevention system.

- Timeline of the stampede: T=0.000s -- key expires. T=0.001s -- first request misses cache, queries DB. T=0.001s to T=0.800s -- 7,000 more requests arrive, all miss cache (because repopulation takes 800ms), all query DB. DB connection pool exhausted at T=0.050s. DB starts queuing queries. T=0.800s -- first query completes, cache is repopulated. T=0.800s to T=3.200s -- 6,999 queued DB queries complete (redundantly) and try to write to cache. Cache is written 7,000 times with the same data. DB is overloaded for 3+ seconds.
- Prevention mechanism 1 -- Single-flight / cache fill lock: the first request to detect a miss acquires a lock ("payment_methods:US:lock") using Redis SET NX. It queries the database. All other requests that detect a miss see the lock is held and either (a) wait 50ms and retry the cache lookup, or (b) immediately return a "loading" response to the user (graceful degradation). When the lock-holder completes, it sets the cache value and releases the lock. All waiting requests now hit the cache. DB receives exactly 1 query instead of 7,000.
- Prevention mechanism 2 -- Background refresh with stale serving: the cache entry stores both the value and a "freshness" timestamp. At T=-30s (30 seconds before expiry), the first request that reads the entry detects "this will expire in 30 seconds" and asynchronously triggers a background refresh. The refresh completes before T=0. No stampede occurs because the key never actually expires -- it is always refreshed before it expires.
- Prevention mechanism 3 -- TTL jitter at population time: instead of setting TTL = 86400 (exactly midnight), set TTL = 86400 + random(0, 3600). Different geographic payment method keys expire at different times, spreading the refresh load across an hour window. For a single high-traffic key, jitter alone does not prevent stampede -- it only prevents multiple keys from stampeding simultaneously.
- Follow-up: You implement the lock mechanism. During a network partition, the lock-holder cannot release the lock because Redis is unreachable. The lock TTL is 5 seconds. For 5 seconds, all 3,000 concurrent users get "loading" responses. Is this acceptable? What if the lock TTL is too long (10 seconds) -- describe the user experience. What if too short (500ms) -- what happens when the DB query takes 800ms?

---

**Question 24 -- Cache coherence across microservices**

You have 8 microservices. Four of them (Order Service, Recommendation Service, Notification Service, Analytics Service) all cache user profile data independently. The User Service owns the source of truth for user profiles. A user updates their email address. The User Service updates the database. Now user profile caches in 4 services have stale data. Design the cache coherence protocol.

- Option 1 -- Event-driven invalidation via message broker: User Service publishes a "user.profile.updated" event to Kafka (or RabbitMQ). Each of the 4 services subscribes to this topic. On receiving the event, each service deletes its local cache entry for that user. Advantages: decoupled, async, no direct coupling between User Service and consumers. Disadvantages: if any consumer is down when the event fires, it misses the invalidation and must rely on TTL expiry to recover.
- Option 2 -- Shared cache with single ownership: all 4 services read user profiles from a single shared Redis instance that is owned and written to exclusively by User Service. No service has its own independent copy. When User Service updates the profile, it atomically updates the shared cache. Cache coherence is guaranteed because there is only one copy. Disadvantage: creates a single point of failure and a tight coupling between services -- the shared Redis becomes part of User Service's internal state but is accessed by external services.
- Option 3 -- Cache-aside with short TTL and no invalidation: each service caches profiles with a 60-second TTL and simply accepts up to 60 seconds of staleness. No inter-service coordination needed. Simple, robust to service outages, easy to understand. Appropriate when 60-second staleness is acceptable. Most profile data (display name, avatar, preferences) is fine with 60 seconds. Email address may not be (if used for real-time authentication).
- Option 4 -- Hybrid: use event-driven invalidation for security-sensitive fields (email, role, account_status) and short TTL for non-sensitive fields (display name, avatar). The events flow only for high-value fields, reducing event volume by 80%.
- Follow-up: You choose event-driven invalidation. A new microservice (Billing Service) is added and starts caching user profiles independently. Nobody updates the Kafka consumer configuration for Billing Service to subscribe to the "user.profile.updated" topic. User email changes will never invalidate Billing Service's cache. How do you prevent this "new service forgotten in invalidation topology" problem architecturally? (Hint: think about where the responsibility for cache invalidation should live.)

---

**Question 25 -- Two-tier caching: when and how**

Your product image service serves 2 million images per second globally. Today you use only Redis (L2 cache). Average Redis latency is 3ms. You want to add an in-process L1 cache to each of your 200 application servers to reduce latency below 1ms for the most popular images. Design the two-tier cache, including sizing, eviction, and consistency.

- Sizing the L1 cache: each application server has 4GB of RAM allocated to the process. Images average 50KB each. If you dedicate 500MB to the L1 cache, you can hold 10,000 image objects per server. Your catalog has 10 million images but traffic follows Zipf -- the top 1,000 images get 60% of traffic. An L1 cache of 10,000 items easily holds the top 1,000 items with room to spare for the next tier of popularity.
- TTL consistency between tiers: if your Redis L2 TTL is 1 hour, your L1 TTL should be shorter -- say, 5 minutes. Why? When an image is updated and the Redis key is explicitly deleted, the L1 caches on all 200 servers still have the old copy. The L1 TTL is the staleness window for image updates. You cannot push invalidations to in-process caches without inter-server coordination (pub/sub), so TTL must do the job. 5 minutes of image staleness is acceptable for most use cases.
- Eviction: L1 uses LRU. The 10,000-item capacity is small enough that LRU works correctly -- the top 1,000 items stay hot and the rest cycle through on access. No LFU needed because the L1 is small and the access pattern is predictable.
- Hit rate math: L1 hit rate 60% (top items). Of the 40% L1 misses, L2 (Redis) hit rate is 90%. DB miss rate: 40% x 10% = 4% of all requests. Average latency: (0.60 x 0.3ms) + (0.40 x 3ms) + (0.04 x 30ms) = 0.18 + 1.2 + 1.2 = 2.58ms. Wait -- the L1 cache actually saved little here. Why? Because the 40% L1 misses dominate. The correct target is improving L1 hit rate above 80% or reducing L2 latency.
- Follow-up: You deploy the L1 cache. Memory on your application servers begins growing unboundedly overnight. By morning, several servers are OOM-killed. What went wrong? (Consider: image sizes vary from 10KB to 5MB. Your L1 cache size was set in number of items, not bytes. 10,000 5MB images = 50GB, not 500MB.)

---

**Question 26 -- Cache as a session store: design and failure modes**

You are migrating a monolith to microservices. The monolith stored user sessions in local memory (sticky sessions via load balancer). You need a session store that all microservices can access. You choose Redis as the session store. A session contains: user ID, auth token, cart contents, CSRF token, last activity timestamp. Sessions expire after 30 minutes of inactivity. Design the session store.

- Key structure: "session:{session_id}" maps to a hash of session fields. Use Redis HSET to store individual fields. This allows you to read only the fields you need (e.g., just the user_id and auth_token for authentication) without deserializing the entire session. It also allows atomic updates of individual fields (HSET session:abc123 last_activity 1718400000) without read-modify-write.
- TTL management for sliding expiration: the 30-minute TTL should reset on every request (sliding expiration, not fixed expiration). After every authenticated request, call EXPIRE session:{session_id} 1800. This resets the TTL clock. If a user is active, their session never expires. If inactive for 30 minutes, the TTL fires and the session is automatically deleted by Redis. Redis handles the cleanup -- no background job needed.
- What happens when Redis goes down: every request to any microservice fails because session validation fails. Redis as a session store is now a critical path dependency. You need Redis high availability: use Redis Sentinel (automatic failover from primary to replica) or Redis Cluster. Aim for 99.99% availability (52 minutes downtime per year maximum) because every user-facing request depends on it.
- Cart contents in the session: cart contents can be large (hundreds of items). Storing large blobs in Redis sessions wastes memory and increases serialization overhead. Consider: store cart in a separate Redis key ("cart:{user_id}") referenced from the session, not embedded. Set the cart TTL to match the session TTL. This separates concerns and allows independent access to cart data without loading the entire session.
- Follow-up: A user's session is stored in Redis primary. Redis primary fails. Redis Sentinel promotes the replica to primary. The replica was 2 seconds behind (replication lag). The user's last 2 seconds of session writes (including their just-added cart item) are lost. They see a stale cart. How do you handle this without synchronous replication (which would add latency to every session write)?

---

**Question 27 -- Cache for rate limiting: sliding window implementation**

You are building an API rate limiter. Limit: 100 requests per minute per user. You implement this using Redis. Design the rate limiting algorithm, explain why naive TTL-based counting fails, and implement the sliding window counter correctly.

- Naive approach (fixed window counter): at the start of each minute, reset the counter to 0. Each request increments the counter. If counter > 100, reject the request. Problem: a user can make 100 requests at 12:00:59 and 100 more requests at 12:01:01 -- 200 requests in 2 seconds, exploiting the window boundary. This is the "fixed window edge burst" problem.
- Sliding window log: store a sorted set per user with timestamps of recent requests: ZADD rate_limit:user:42 {current_timestamp} {unique_id}. On each request: ZREMRANGEBYSCORE rate_limit:user:42 0 (current_time - 60) to remove entries older than 60 seconds. ZCARD rate_limit:user:42 to count remaining entries. If count >= 100, reject. Otherwise, add the new timestamp and allow. This gives a perfect sliding window -- exactly 100 requests per any 60-second window. Trade-off: memory grows with the number of requests in the window. At 100 requests per user per minute and 1 million active users, you store 100 million sorted set entries.
- Sliding window counter (approximate, memory-efficient): keep two counters per user: "requests in the previous minute" and "requests in the current minute." On each request, compute approximate current window count = (previous_minute_count x fraction_of_previous_minute_remaining) + current_minute_count. If this exceeds 100, reject. This uses two integers per user (vs 100 sorted set entries) and approximates the sliding window with typically less than 1% error. This is what many production rate limiters use.
- Atomic operations: use a Redis Lua script to atomically combine the ZADD, ZREMRANGEBYSCORE, and ZCARD operations. Without atomicity, a race condition allows two simultaneous requests to both see count=99 and both proceed, resulting in 101 requests being allowed.
- Follow-up: Your rate limiter is working. A distributed denial-of-service attack generates 50,000 requests per second for user "attacker_123." Your Redis rate limiter correctly rejects them after the first 100. But the Redis operations for those 50,000 requests per second still consume CPU and network. How do you add a pre-Redis tier to block obviously bad actors without touching Redis at all?

---

**Question 28 -- Cache eviction under memory pressure: what actually happens**

Your Redis instance is configured with maxmemory=8GB and maxmemory-policy=allkeys-lru. You load 10GB of data into it. Walk through exactly what Redis does when memory exceeds maxmemory, what the eviction cycle looks like, and what observable effects appear in your application.

- What Redis does internally: Redis does not have a background GC thread watching memory. Instead, on each write operation (SET, HSET, LPUSH, etc.), Redis checks if used_memory > maxmemory. If yes, it runs an eviction cycle before completing the write. The eviction cycle selects a victim key using the eviction policy and deletes it, freeing memory. This happens synchronously in the write path.
- LRU eviction is approximate in Redis: true LRU requires tracking the access time of every key, which is expensive. Redis instead samples a configurable number of keys (default: 5, controlled by maxmemory-samples) and evicts the one with the oldest access time among those 5. This is approximate LRU -- not exactly the global least-recently-used key, but close. Increasing maxmemory-samples to 10 improves accuracy at the cost of more CPU per eviction.
- Observable effects in your application: (1) Evicted keys cause cache misses. Watch `redis-cli INFO stats | grep evicted_keys` -- if this number is growing rapidly, you are under memory pressure. (2) Write latency increases because every write triggers eviction overhead. (3) Hit rate drops. (4) If eviction cannot keep up with incoming writes (you are writing faster than Redis can evict), Redis may start refusing writes with OOM errors -- `(error) OOM command not allowed when used memory > 'maxmemory'.`
- Redis memory fragmentation: when many small keys are written and deleted, the Redis allocator (jemalloc) may hold memory that appears "allocated" at the OS level but is not used by actual key data. `mem_fragmentation_ratio` > 1.5 indicates fragmentation. In extreme cases, Redis may report used_memory=7GB but the OS shows 11GB allocated, meaning Redis cannot use 4GB that it has already claimed. Fix: set config activedefrag yes in Redis 4.0+ to enable active memory defragmentation.
- Follow-up: Your Redis eviction rate is 50,000 keys per second and your miss rate is climbing. Your options are: (a) add more memory (scale up Redis), (b) reduce key sizes (serialize data more efficiently), (c) add a second Redis node and shard keys. Walk through the decision criteria for each option and which one you should try first.

---

**Question 29 -- CDN cache-control headers: designing the header strategy**

Your web application serves three types of content: (1) static assets (JavaScript bundles, CSS, images) that change only on deploy, (2) semi-static API responses (product catalog, pricing) that change every few hours, (3) dynamic user-specific API responses (cart, profile) that must never be shared between users. Design the Cache-Control header strategy for each content type.

- Type 1 -- Static assets: use content-hash filenames (e.g., "main.a3b4c5.js" changes name on every deploy). Set Cache-Control: max-age=31536000, immutable. The CDN (and browser) can cache this for 1 year. Because the filename changes on every deploy, a new deploy automatically causes new requests for new filenames -- no stale asset problem. The "immutable" directive tells the browser "even if you are forced to revalidate, this file will never change, do not bother." This is the gold standard for static asset caching.
- Type 2 -- Semi-static API responses: use Cache-Control: max-age=3600, s-maxage=14400, stale-while-revalidate=300. This means: browsers cache for 1 hour (max-age=3600). CDN edge nodes cache for 4 hours (s-maxage=14400 overrides max-age for shared caches). The CDN will serve stale responses for up to 5 minutes (stale-while-revalidate=300) while asynchronously revalidating in the background. Add a Surrogate-Key or Cache-Tag header (supported by Fastly and Cloudflare) so you can purge all product catalog responses with a single API call on update.
- Type 3 -- User-specific dynamic responses: Cache-Control: no-store, private. "no-store" means never cache, not even in the browser. "private" means this is user-specific data that shared caches (CDN) must not store. If you accidentally omit "private" and a CDN caches a user's cart response, the next user whose request hits the same CDN edge node could see the first user's cart -- a serious data privacy violation. Always use "no-store, private" for authenticated user-specific content.
- Edge case: authenticated API responses that are user-specific but share common data (e.g., a product detail page with personalized pricing overlay). The product detail is cacheable; the personalized pricing is not. Use Edge Side Includes (ESI) to separate the cacheable and non-cacheable parts, or use the Vary: Authorization header to cache per-user (with CDN support -- most CDNs support Vary: Cookie or Vary: Authorization for creating user-specific cache entries, but this can create a cache entry explosion).
- Follow-up: You set Cache-Control: max-age=3600 on your product catalog API. You push a pricing update. The CDN still serves old prices for up to 1 hour. You need to push the update in under 10 seconds. Design the end-to-end cache invalidation flow that clears CDN edge caches within 10 seconds of a pricing update, across 5 CDN PoPs globally.

---

**Question 30 -- CDN for dynamic content: Edge Side Includes and cache bypass**

Your e-commerce homepage is 90% the same for all users (product carousel, promotions, category navigation) but 10% is user-specific (welcome message, cart count, personalized recommendations). The 90% shared content is expensive to render (200ms backend render time). The 10% user-specific content must be fresh. Design the caching strategy so that 90% of the homepage is served from CDN cache and only 10% requires an origin request.

- Option 1 -- Edge Side Includes (ESI): split the homepage into cacheable and non-cacheable fragments. The CDN assembles the final page at the edge by including: a cached fragment for the product carousel (cached 1 hour), a cached fragment for the navigation (cached 24 hours), and a non-cached request to the origin for the personalized section (cart count, welcome message). The user gets a complete page assembled at the CDN edge. Total request time: max(edge cache fetch, origin request for personal data) ~ 50ms instead of 200ms. ESI is supported natively by Varnish, Fastly, Akamai, and Cloudflare (with Workers). Not supported by CloudFront natively.
- Option 2 -- Deferred loading (two-request pattern): serve the 90% shared page immediately from CDN cache. The page JavaScript then makes a second API call for the personalized 10%. The user sees the page instantly (from CDN, sub-10ms) and the personalized section fills in 200ms later (from origin). No ESI required. Trade-off: the user sees a brief flash of the generic page before personalization loads. For complex personalization (layout changes based on user tier), this looks worse than option 1.
- Option 3 -- Vary header with user segments: instead of per-user personalization, define 5 user segments (new user, returning user, premium user, cart abandoner, high-value customer). Serve a cached page variant per segment. Vary: X-User-Segment with 5 possible values means 5 cached page variants at each CDN edge node instead of millions of per-user variants. The CDN caches 5 variants. The origin renders 5 templates. User-to-segment assignment happens in a lightweight edge function with no origin request. Trade-off: personalization is coarser (segment-level, not individual-level).
- Follow-up: You implement option 2 (deferred loading). The personalized API request is made from the user's browser to your origin API. Your origin API is in US-East. A user in Singapore makes the request. The RTT from Singapore to US-East is 220ms. The API call takes 30ms at the origin. Total wait for personalization: 220ms x 2 (round-trip) + 30ms = 470ms. Users in Asia have a poor experience. How do you fix the personalization API latency for Asian users without replicating your entire data stack to Asia?

---

### Section D: CDN and Edge Caching (Q31-Q38)

---

**Question 31 -- CDN PoP architecture: how edge caching actually works**

A colleague says "CDN just caches files close to users." Design a whiteboard explanation of how a modern CDN's Point of Presence (PoP) actually works -- from request arrival to cache hit, cache miss, and origin fetch. Include the role of Anycast routing, multi-tier CDN architecture, and origin shield.

- Request routing: when a user in Tokyo requests "images.example.com/product.jpg", DNS resolves "images.example.com" to the nearest CDN PoP IP address using Anycast routing. With Anycast, multiple CDN nodes advertise the same IP address (e.g., 198.51.100.1) via BGP. The internet's routing protocol automatically routes the user's request to the topologically nearest node advertising that IP. No application-level routing decision is needed -- it happens at the network layer.
- At the PoP (cache hit path): the PoP's cache daemon (Nginx, Varnish, or proprietary) looks up the cache key (derived from the URL and any Vary header values). Cache hit: the cached bytes are served directly from the PoP's SSD or RAM. Time to first byte: typically 5-30ms depending on PoP-to-user distance. The origin server receives no request.
- At the PoP (cache miss path): the PoP does not have the object. Without Origin Shield, the PoP contacts the origin server directly. If you have 50 PoPs worldwide and a cache miss happens at all 50 simultaneously (after a deploy that clears CDN caches), the origin receives 50 simultaneous requests for the same object -- a mini thundering herd at the CDN level.
- Origin Shield (mid-tier caching): a designated "shield PoP" sits between the edge PoPs and the origin. When edge PoPs miss, they go to the shield PoP instead of the origin. The shield PoP aggregates misses and sends at most one request per object to the origin. This collapses origin traffic dramatically. For global deployments, the shield PoP is typically in the same region as the origin (e.g., US-East if your origin is AWS us-east-1). The shield does not reduce edge-to-user latency -- it only protects the origin.
- Follow-up: Your CDN has 80 PoPs. You push a deploy that changes 500 static assets. You do NOT use a CDN purge API call. How long does it take for all 80 PoPs to serve the new assets? Walk through the mechanism (TTL expiry, miss-and-fill at each PoP on first user request per PoP). In the meantime, users at different PoPs see different versions of your site -- version mixing. How do you prevent this?

---

**Question 32 -- Multi-CDN strategy: why and how**

Your video streaming platform serves 10 petabytes of video per month globally. You use Cloudflare as your single CDN. Cloudflare has a major outage (this has happened). For 2 hours, your service is completely down. Design a multi-CDN strategy using both Cloudflare and AWS CloudFront, including how you route traffic and how you switch during an outage.

- Why multi-CDN: no CDN has 100% uptime. Major CDN outages affect millions of customers simultaneously. Multi-CDN is the only way to achieve CDN-layer high availability. Additionally, different CDNs have different PoP locations and peering relationships -- using multiple CDNs can improve performance in regions where your primary CDN has weak coverage.
- Traffic distribution approach 1 -- Active/passive: 100% of traffic goes to Cloudflare (primary). CloudFront is warm but receives no traffic (passive standby). On Cloudflare outage, switch DNS to CloudFront. Problem: DNS TTLs mean the switch takes minutes to hours to propagate globally. During the propagation window, users are split between Cloudflare (which is down) and CloudFront.
- Traffic distribution approach 2 -- Active/active with weighted routing: 70% of traffic to Cloudflare, 30% to CloudFront (or split by geography: Cloudflare for EMEA, CloudFront for Americas). Both CDNs are actively caching content and serving traffic. On Cloudflare outage, shift the 70% to CloudFront (which already has warm caches from its 30% share). DNS-based weighted routing (Route 53 weighted records) allows the shift. CloudFront's cache hit rate improves quickly as traffic increases.
- Content synchronization: both CDNs pull from the same origin. No special configuration needed for pull CDNs -- they fetch on first miss. For push CDNs, you must publish to both simultaneously. For video, use pull CDN and ensure your origin has sufficient capacity to serve cache-miss traffic to two CDNs simultaneously during a transition period.
- Follow-up: You implement active/active multi-CDN. Your analytics team complains that CDN-level cache hit rates are lower than with single CDN. Why? (Each CDN has half the traffic, so each CDN's cache warms up more slowly -- the same content may need to be cached in two separate CDN systems.) How does this affect your total origin traffic cost, and at what traffic volume does the reliability benefit outweigh the cache efficiency cost?

---

**Question 33 -- Cache-Control and Vary header interaction**

Your API serves responses with Vary: Accept-Encoding, Accept-Language. You have users from 5 language locales (en, fr, de, ja, zh) and 3 encoding types (gzip, br, identity). How many cached variants does the CDN potentially store per URL? Explain the Vary header semantics and when Vary becomes a caching anti-pattern.

- Variants per URL: Vary instructs the CDN to cache a separate response for each unique combination of the Vary header values. With Accept-Encoding (3 variants) and Accept-Language (5 variants), the CDN stores up to 3 x 5 = 15 cached variants per URL. For 10,000 URLs in your catalog, that is up to 150,000 cached objects vs 10,000 without Vary -- a 15x cache storage increase, with corresponding eviction pressure.
- When Vary is essential: Accept-Encoding is almost always correct to Vary on -- you must not serve a gzip-compressed response to a client that requested identity encoding. Browsers handle this correctly. Accept-Language is correct for localized content where different languages return different body content. Without Vary: Accept-Language, a French user might get a cached English response.
- When Vary becomes an anti-pattern: Vary: Cookie or Vary: Authorization causes the CDN to create a separate cache entry per unique cookie or authorization header value. With 1 million authenticated users, each with a unique session cookie, you create 1 million cache entries for the same URL -- none of which will ever be hit by another user. Your CDN becomes useless for authenticated content. This is a common mistake with poorly configured authentication.
- Better approach for authenticated content: use Cache-Control: private, no-store for truly user-specific content. For content that is user-specific only in small ways, strip the user-specific parts at the origin and serve them via JavaScript after page load, allowing the base page to be cached without Vary: Cookie.
- Follow-up: Your API returns Vary: Accept-Language but your mobile app always sends Accept-Language: en regardless of the device locale. Your web app sends the real device locale. The CDN correctly caches per-language variants for web users but stores redundant identical "en" variants from mobile (because they appear as separate entries due to minor header differences). How do you normalize Vary headers to collapse identical responses into the same cache entry?

---

**Question 34 -- CDN for APIs: when it helps and when it hurts**

Your REST API has 3 types of endpoints: GET /products/{id} (public, same response for all users), GET /users/{id}/cart (user-specific, requires auth), POST /orders (writes, no caching applicable). Your team proposes putting a CDN in front of all three. Design the correct CDN configuration and explain why undiscriminating CDN usage can cause security and correctness bugs.

- GET /products/{id}: ideal for CDN caching. Public, same response for all users, changes infrequently. Set Cache-Control: public, max-age=3600, s-maxage=14400. CDN caches each product ID for 4 hours. Edge nodes worldwide serve product data at <10ms latency. Origin receives only cache-miss traffic (~1% of requests after warm-up). No security concern -- data is public.
- GET /users/{id}/cart: must NOT be cached by CDN. Set Cache-Control: no-store, private. If this is accidentally cached (e.g., you forget the header and the CDN has a default caching policy), user A's cart could be served to user B if user B happens to request the same URL at the same CDN node. This is a serious data privacy bug. When using a CDN in front of authenticated APIs, always explicitly set Cache-Control: no-store, private on every authenticated response -- never rely on CDN defaults.
- POST /orders: must never be cached. POST requests are not cached by CDN by default per HTTP spec. However, some CDNs can be configured to cache POST responses (for idempotent APIs). Never cache POST responses for order creation -- a cached response could cause the CDN to return a stale "order confirmed" without actually creating the order on a subsequent retry.
- CDN-specific security risk -- cache poisoning: if your API accepts query parameters that affect the response (e.g., GET /products?currency=USD vs GET /products?currency=EUR) but you did not configure the CDN to vary on the currency parameter, the CDN may cache the USD response and serve it to EUR users. This is called cache poisoning. Always configure your CDN's "cache key normalization" to include all query parameters that affect the response.
- Follow-up: You enable CDN for GET /products/{id}. A security researcher discovers that your CDN is caching responses that include a Set-Cookie header (your backend sets a session cookie on every response, including public API responses -- a design bug). The CDN is caching the first user's cookie and serving it to subsequent users. How widespread is this vulnerability, how do you detect it, and what is the fix?

---

**Question 35 -- CDN purge strategies: time-critical content updates**

Your news site publishes breaking news. An article title has a typo ("Presidetn Biden" instead of "President Biden"). The article page is cached at the CDN with a 24-hour TTL (you set a long TTL to reduce origin load). The article was published 1 hour ago and has been shared 500,000 times on social media. All those links hit CDN-cached pages with the typo. You need to fix the title and push the fix to all CDN edge nodes within 60 seconds. Design the CDN purge system.

- Purge by URL: most CDNs offer an API call to instantly purge a specific URL from all edge nodes. Cloudflare: POST /zones/{zone_id}/purge_cache with {"files": ["https://example.com/article/12345"]}. AWS CloudFront: CreateInvalidation API with paths. Fastly: PURGE https://example.com/article/12345. A single URL purge typically propagates to all global edge nodes within 1-5 seconds (CDN SLA for purge propagation is often 60 seconds but practically much faster).
- Purge by cache tag (surrogate keys): when the article is served, include a response header: Surrogate-Key: article:12345 category:politics author:john. This tags the cached response with multiple identifiers. Fastly and Cloudflare support instant purge by cache tag: "purge all responses tagged with article:12345." This allows purging all content related to an article (the article page, its thumbnail cache, its API response) in one API call. CloudFront does not natively support cache tags -- you must track URLs manually.
- Automatic purge on publish: integrate the purge API call into your CMS publish workflow. When an editor saves a correction: (1) update the database, (2) call the CDN purge API, (3) return success to the editor. If the purge API call fails (CDN API downtime), log the failure and add the URL to a retry queue. Do not block the editor's save on purge success -- the purge is a best-effort improvement, not a correctness requirement (TTL will eventually fix it).
- Rate limits on purge APIs: CDN purge APIs are rate-limited. CloudFront allows 1,000 invalidation paths per distribution per month for free, with charges beyond that. Fastly has higher limits but still enforces them. For high-frequency content updates (news sites), design your purge system to batch URL invalidations and avoid per-save purges for minor updates.
- Follow-up: You implement automatic purge on publish. A bug in the CMS causes 10,000 purge requests to be sent to the CloudFront API in 5 minutes. CloudFront rate-limits your purge requests. Your legitimate purge requests (for actual content updates) are now also being rate-limited. How do you design the purge queue to be resilient to rate limits without blocking legitimate purges?

---

**Question 36 -- Stale-while-revalidate: user experience vs consistency**

You add the stale-while-revalidate directive to your CDN caching strategy for product catalog pages: Cache-Control: max-age=3600, stale-while-revalidate=600. Explain exactly what this means for user experience, how CDN revalidation works, and what the edge cases are when an origin server is slow or down.

- Semantics: max-age=3600 means the response is "fresh" for 1 hour. After 1 hour, the response is "stale." stale-while-revalidate=600 means: if the cached response is stale but no more than 600 seconds (10 minutes) stale, serve the stale response immediately AND asynchronously trigger a background revalidation request to the origin. If the response is more than 3600+600=4200 seconds old, do not serve it -- fetch fresh content synchronously.
- User experience: during the stale-while-revalidate window (hour 1 to hour 1:10), users always get an instant response (<10ms from CDN edge). They never wait for the origin. The page they see is up to 10 minutes stale. For product catalog (prices, descriptions), 10 minutes of staleness is typically acceptable. The CDN simultaneously fetches the fresh version in the background. The next user after revalidation completes gets the fresh version.
- When origin is slow: the background revalidation request may take 500ms if the origin is under load. During those 500ms, subsequent requests to the CDN continue to get the stale response (they do not wait for the background fetch to complete). This is the key benefit of stale-while-revalidate: origin latency does not affect user-perceived latency during the stale window.
- When origin is down: the background revalidation request fails. The CDN is now holding a stale response. What happens after the stale-while-revalidate window closes? The cached response is now too old to serve even stale. The CDN must wait for the origin, which is down. Users get errors. Solution: add stale-if-error=86400 -- serve the stale response even if the origin returns an error (5xx or network failure) for up to 86400 seconds (24 hours). This trades staleness for availability during origin outages.
- Follow-up: You have stale-while-revalidate=600. A price change occurs 55 minutes into the cache TTL. The CDN is still serving the page fresh (max-age=3600). 5 minutes later, the TTL expires. The stale-while-revalidate window begins. The CDN serves the old price (now 65 minutes old -- 5 minutes older than the update) while revalidating. The revalidation fetches the new price. But the CDN started 5 minutes late due to max-age. Total time with wrong price shown: up to 10 minutes after TTL expiry + the 55 minutes where it was still "fresh." For price-sensitive content, how do you handle the freshness-vs-availability trade-off?

---

**Question 37 -- CDN selection: CloudFront vs Fastly vs Cloudflare for your use case**

You are choosing a CDN for a global SaaS application. Requirements: (1) API caching with custom cache keys, (2) edge compute capability (run business logic at the edge), (3) real-time cache purge (<5 seconds globally), (4) DDoS protection, (5) detailed per-URL analytics. Compare CloudFront, Fastly, and Cloudflare across these dimensions and explain which trade-offs matter most for different company stages.

- CloudFront: tightest AWS integration (IAM, Lambda@Edge, VPC origins). Edge compute via Lambda@Edge (runs Node.js at edge) and CloudFront Functions (lightweight, lower latency but limited runtime). Purge propagation: 1-5 minutes typically (not real-time -- fails requirement 3 for strict SLAs). Cache key customization: supported via Cache Policies. DDoS: AWS Shield Standard included. Analytics: CloudFront access logs to S3 (not real-time). Best for: AWS-native shops, when Lambda@Edge integration value outweighs purge speed limitations.
- Fastly: designed specifically for API caching and real-time purge. Purge propagation: <1 second globally (industry-leading). Edge compute: Compute@Edge (Wasm runtime, runs Rust or AssemblyScript -- more powerful but more complex). Surrogate key cache tags: native, first-class feature. Analytics: real-time streaming log data. Best for: teams with strict purge requirements (news sites, e-commerce with frequent price changes), API-first architectures, teams comfortable with VCL (Varnish Configuration Language) for complex cache logic.
- Cloudflare: largest network (300+ PoPs vs Fastly's ~100). Edge compute: Cloudflare Workers (V8 isolates, JavaScript/WASM, very low cold start). Cache Rules for custom cache key configuration. Purge: fast (seconds, not as guaranteed as Fastly). DDoS: industry-leading, included in all plans. Analytics: real-time in dashboard. Price: generally lowest at comparable traffic volumes. Best for: DDoS-sensitive workloads, global reach requirements, budget-conscious teams, teams that want "one vendor for CDN + DDoS + DNS + edge compute."
- For a seed-stage startup: Cloudflare. Easiest setup, generous free tier, good DDoS protection, Workers for edge logic, reasonable purge speed. For a growth-stage e-commerce platform where wrong prices cost real money: Fastly (purge speed + cache tags). For an AWS-native enterprise: CloudFront (IAM integration, VPC origins, Lambda@Edge for complex auth logic at edge).
- Follow-up: Your team implements Fastly. Six months later, you are acquired by a company standardized on AWS. They require all external traffic to go through CloudFront. Describe the migration plan -- which capabilities you will lose (real-time purge SLA), which equivalents exist in CloudFront (Lambda@Edge), and what re-engineering your cache invalidation system requires.

---

**Question 38 -- CDN cost optimization: hit rate economics**

Your CDN bill is $12,000/month for 1.5 petabytes of egress. Your cache hit rate is 72%. Your origin egress (data leaving your origin to the CDN on cache misses) costs $0.09/GB and runs 420TB/month (28% of 1.5PB that missed the CDN). Analyze the cost structure, calculate what a 10% improvement in hit rate saves, and design the optimization strategy.

- Current cost breakdown: CDN egress: 1,500TB x $0.0080/GB = $12,000/month (using $0.008/GB blended Fastly rate). Origin egress: 420TB x $0.09/GB = $37,800/month (AWS egress is expensive -- this is the hidden cost of cache misses). Total actual infrastructure cost: $49,800/month. The CDN bill is only 24% of total cost -- origin egress is the dominant cost, not CDN egress.
- If hit rate improves from 72% to 82%: misses drop from 28% to 18% of traffic. New origin egress: 1,500TB x 18% = 270TB x $0.09/GB = $24,300/month. Savings: $37,800 - $24,300 = $13,500/month. CDN egress stays similar (total traffic unchanged). Net monthly saving: $13,500 from a 10% hit rate improvement. Annual: $162,000. This is likely worth significant engineering investment.
- Optimization strategies ranked by impact: (1) Identify the top 100 URLs with the lowest hit rates using CDN analytics. Investigate why -- are TTLs too short? Cache-Control headers missing? Vary header creating too many variants? Fix these individually. (2) Increase TTLs on content that changes infrequently (documentation pages, product images). Going from 1-hour to 24-hour TTLs on static content can move hit rate from 72% to 85%+ if that content is a significant fraction of your traffic. (3) Add Origin Shield -- a mid-tier cache between edge PoPs and origin. This primarily reduces origin requests, cutting origin egress cost without necessarily improving end-user hit rate.
- Follow-up: Increasing TTLs from 1 hour to 24 hours increases hit rate to 87% but creates a new problem: your marketing team pushes urgent content updates and sees 24 hours of stale content. They demand you revert to 1-hour TTLs. How do you give the marketing team the ability to push immediate updates (via a CMS-triggered purge) while maintaining 24-hour TTLs for cache efficiency? What is the engineering effort to build this, and how do you make sure the marketing team actually uses the purge feature correctly?

---

### Section E: Advanced Patterns (Q39-Q45)

---

**Question 39 -- Cache stampede: the probability formula and prevention threshold**

Your Redis key "homepage:featured_products" has TTL = 3,600 seconds. Request rate for this key is 2,000 requests/second. Database recomputation time is 250ms. Cache population time after recomputation is 50ms (total miss-to-populate = 300ms). Calculate: how many requests will simultaneously miss and hit the database when the key expires? At what request rate does the thundering herd become a database-threatening problem?

- Stampede magnitude: when the key expires, all requests that arrive during the 300ms repopulation window will miss the cache and hit the database. Number of stampede requests: 2,000 req/s x 0.300s = 600 simultaneous database requests. If your database can handle 100 concurrent queries before degrading, 600 simultaneous queries is a 6x overload -- catastrophic.
- At what rate does it become dangerous: your database starts degrading at 100 concurrent queries. Concurrent queries during stampede = request_rate x repopulation_time = request_rate x 0.300s. For 100 concurrent queries: 100 / 0.300 = ~333 requests/second is the threshold. Above 333 req/s for this key, a cache expiry causes database overload. Your current rate (2,000 req/s) is 6x over the danger threshold.
- Prevention math: if you add a mutex lock, only 1 database query runs during the 300ms window. The other 599 requests wait (with 10ms retry intervals) or receive a queued response. Database load: 1 query instead of 600. If you add probabilistic early expiration with delta=1 and beta=0.5 (tuning parameters from the XFetch algorithm), recomputation begins approximately 30 seconds before expiry. Zero requests experience a miss because the key is always populated before expiry.
- Economic analysis: the XFetch probabilistic early expiration means the database gets one extra query every 3,600 seconds per hot key. With 100 hot keys, that is 100/3600 = 0.028 extra database queries per second -- negligible. The mutex approach adds 1ms of lock contention latency to 599 requests every 3,600 seconds -- also negligible. Both solutions are worth implementing; XFetch is more elegant but requires modifying how you read from the cache; mutex is simpler to add to existing code.
- Follow-up: You implement mutex-based prevention. Three months later, a new engineer adds a new cache key without the mutex pattern. At 3am, that key's TTL expires and 800 simultaneous requests hit the database. The on-call engineer gets paged. How do you prevent this from recurring? (Think: code review requirements, cache client wrapper that enforces the pattern, automated detection of keys without stampede prevention.)

---

**Question 40 -- Cache warm-up for machine learning model results**

Your recommendation engine uses a machine learning model that takes 2 seconds to compute personalized recommendations for each user. You have 5 million active users. You cannot afford to compute recommendations on-demand (2 seconds latency is too slow). You pre-compute recommendations nightly in a batch job and store them in Redis. Each user's recommendations are 5KB. Design the warm-up and rotation strategy.

- Storage calculation: 5 million users x 5KB = 25GB of recommendation data. A Redis instance with 30GB RAM can hold all recommendations with headroom. This is a fixed dataset -- no eviction needed if sized correctly.
- The stale recommendation problem: recommendations computed at midnight may be 23 hours stale by 11pm. A user who bought a product at 9am may still see that product recommended at 10pm. The batch job runs at midnight, replacing all recommendations. Design "freshness bands": nightly batch for baseline recommendations + hourly mini-batch for users who have made purchases or significant interactions in the last hour. The mini-batch refreshes only active-session users, reducing compute load vs full recompute.
- The rotation problem: the nightly batch job takes 4 hours (midnight to 4am). During those 4 hours, you cannot atomically swap 25GB of recommendation data. You write to a "recommendations:batch:v2" namespace while "recommendations:batch:v1" is live. After the batch job completes, you update a Redis key "recommendations:current_version" from "v1" to "v2" (atomic write). All application servers that read this version key now route to v2. Old v1 keys expire via TTL (set during the v1 write, e.g., TTL = 28 hours, long enough to overlap with the next batch cycle).
- Cold start on Redis restart: if Redis is restarted during the day, all 25GB of recommendations are lost. All user requests for the next 4 hours (until the batch job runs) fall back to a generic "popular items" fallback. Enable Redis persistence (RDB snapshot or AOF) for this use case -- the data must survive restarts. The RDB snapshot of 25GB takes approximately 2-3 minutes to restore, which is acceptable for a planned restart.
- Follow-up: Your recommendations are GDPR-sensitive (they reflect user behavior and preferences). Redis persistence writes the data to disk. A disk is replaced and the old disk is sent for refurbishment without being wiped. EU regulators audit your data handling. How do you handle GDPR compliance for persisted Redis data? (Think: encryption at rest, data retention policies for persistence files, process for secure disk disposal.)

---

**Question 41 -- Cache for search autocomplete: design and update strategies**

You are building a search autocomplete service for an e-commerce site. When users type "iph", you return ["iphone 14", "iphone case", "iphone charger", "iphone 13 pro max", "iphone screen protector"] in under 20ms. Your product catalog has 2 million items. Design the caching strategy.

- Do not cache raw search results: search results for "iph" may change as inventory changes, new products are added, and seasonal items appear. Caching the entire result set per prefix creates a near-infinite key space (every unique prefix is a cache key) and requires complex invalidation.
- Cache the prefix trie, not the results: pre-compute a prefix-to-suggestions mapping offline. Store "autocomplete:iph" -> ["iphone 14", "iphone case", ...] as a Redis sorted set (sorted by popularity score). The sorted set allows you to ZRANGEBYSCORE to get top-N suggestions in O(log N) time. This is a read-heavy, write-occasional data structure -- perfect for caching.
- Update strategy: the autocomplete suggestions change slowly (new products added daily, popularity scores updated hourly). Use a background job that runs every hour to recompute the top-50 suggestions for every prefix (all 3-character prefixes, then 4-character, etc.) and update the Redis sorted sets. The update is a full replace: ZADD replaces the old entries. Apply a 2-hour TTL as a safety net in case the job fails.
- Multi-character prefix explosion: if users can type up to 20 characters, and you pre-compute all prefixes from 1 to 20 characters for 2 million products, you have an enormous number of prefix keys. Limit pre-computation to prefixes up to 10 characters (covers 99% of user queries). For longer prefixes, fall back to a real-time search index (Elasticsearch) which is fast enough for infrequent long-query cases.
- Follow-up: Your autocomplete cache is working. A product goes out of stock and you want it removed from autocomplete within 5 minutes. The background job runs hourly. Design an event-driven invalidation mechanism that allows near-real-time removal of out-of-stock products from autocomplete suggestions without requiring a full recompute every 5 minutes.

---

**Question 42 -- Cache for aggregated metrics: fan-in patterns**

Your analytics dashboard shows "total orders in the last 24 hours" which must update every 60 seconds. The raw orders table in PostgreSQL has 500 million rows. A COUNT(*) query with 24-hour filter takes 4 seconds. 200 engineers refresh this dashboard every minute = 200 queries per minute = 3.3 queries per second. Each takes 4 seconds. Your database cannot handle this. Design the caching strategy.

- Simple approach (cache the count): run the COUNT(*) query once per minute in a background job. Store the result in Redis with a 60-second TTL: SET analytics:orders:24h:count 1234567 EX 60. All 200 dashboard requests hit Redis (1ms) instead of the database. The background job runs 1 query per minute (0.017 QPS). This works and is simple.
- Why the background job approach can fail: if the background job runs at T=0 and stores count=X, at T=59 the cache expires. At T=60, the background job has not run yet (it is scheduled for T=60 but may be a few seconds late). From T=59 to T=63 (when the job actually runs), 200 engineers hitting refresh at T=59, T=60, T=61, T=62 all miss the cache and trigger database queries. Thundering herd at the minute boundary.
- Better approach: overlap TTL and job interval. Set TTL = 120 seconds (2x the refresh interval). The job still runs every 60 seconds. The cache entry is always 30-120 seconds fresh. When the job runs at T=60, it overwrites the T=0 entry. The cache never expires between job runs (because TTL=120 > job interval=60). No thundering herd.
- Further optimization -- pre-aggregated materialized view: maintain a PostgreSQL materialized view "orders_last_24h_summary" that is refreshed every 5 minutes. Query the materialized view (returns in 10ms) instead of the raw 500M-row table. Cache the materialized view result with 60-second TTL. Now even cache misses are fast (10ms vs 4 seconds). The database load is minimal.
- Follow-up: The business team asks for "orders in the last 1 hour, 6 hours, 12 hours, 24 hours, 7 days" -- 5 different time windows, all updating every 60 seconds. Do you cache each separately or design a single aggregated data structure? What happens to database load if you use 5 separate background jobs vs a single job that computes all 5 windows?

---

**Question 43 -- Cache poisoning attacks: detection and prevention**

A security researcher demonstrates a cache poisoning attack against your CDN. They send a request with a custom "X-Forwarded-Host: evil.com" header. Your backend includes this header in the response body (for CORS configuration). The CDN caches the response. Subsequent legitimate users who request the same URL receive the poisoned cached response with "evil.com" in the CORS configuration, causing their browsers to send cross-origin requests to evil.com. Design the prevention strategy.

- Root cause: cache poisoning occurs when unkeyed inputs influence cached outputs. "X-Forwarded-Host" is an unkeyed input -- the CDN does not include it in the cache key (because it is a header, not the URL), so different values of X-Forwarded-Host all map to the same cache entry. But your backend uses this header to construct the response, creating a response that varies with an unkeyed input. The first response (with the attacker's value) is cached and served to everyone.
- Prevention mechanism 1 -- Normalize and validate inputs at origin: never trust X-Forwarded-Host in response generation unless you have explicitly validated it against an allowlist of known-good hostnames. Your backend should generate CORS headers based on an internal allowlist, not based on the request header. This eliminates the vulnerability regardless of CDN configuration.
- Prevention mechanism 2 -- Extend the cache key to include relevant headers: configure your CDN to include X-Forwarded-Host in the cache key. Fastly: use VCL to set bereq.http.X-Forwarded-Host in vcl_hash. Cloudflare: use Cache Rules with "Cache Key" configuration to include the header. Now different X-Forwarded-Host values produce different cache entries -- an attacker cannot poison the shared cache with their value.
- Prevention mechanism 3 -- Strip unrecognized headers at the CDN edge: configure the CDN to remove X-Forwarded-Host (and other potentially dangerous headers) before forwarding to the origin. The origin never sees the header, so it cannot be influenced by it.
- Detection: monitor your CDN logs for unusual header values in requests. Set up alerts for requests with X-Forwarded-Host values that do not match your known domain list. Test for cache poisoning in your security review pipeline: send requests with unexpected header values and verify that subsequent cache responses do not reflect those values.
- Follow-up: You fix the X-Forwarded-Host vulnerability. The researcher returns and demonstrates a second attack via "X-Original-URL" header injection that changes the path component seen by the backend. Your CDN caches based on URL path (the correct path) but your backend serves content based on X-Original-URL (the attacker-controlled path). Same class of vulnerability, different vector. Design a systematic approach to auditing all headers that your backend reads and ensuring none can influence cached responses without being part of the cache key.

---

**Question 44 -- Cache design for feature flags**

Your application uses feature flags to enable/disable features for specific users or percentages of traffic. Feature flag evaluation takes 5ms per request (it calls an external feature flag service). At 10,000 requests/second, that is 50 seconds of cumulative flag evaluation time per second -- clearly unsustainable. Design the caching strategy for feature flag evaluation results.

- What to cache: do not cache the raw flag definitions (those change infrequently). Cache the evaluated flag state per user per flag: "flag:show_new_checkout:user:42" -> true. This caches the result of evaluating the flag rule (percentage rollout, user segment, override) for a specific user, not the rule itself.
- TTL design: feature flags must be responsive to changes -- if you turn off a feature due to a bug, all users should see the change within 30-60 seconds, not within the next hour. Set TTL = 30 seconds. This means flag evaluations are at most 30 seconds stale. At 10,000 req/s with 30-second TTL and 100,000 active users, cache hit rate after warm-up: very high (most users' flags are cached from recent requests). Cache miss rate: at 30-second TTL and 100,000 users, you need to refresh 100,000 / 30 = ~3,333 flag evaluations per second -- the external flag service receives 3,333 QPS (vs 10,000 without caching). A 67% reduction.
- Emergency flag kill switch: if a feature is causing a production incident, you need to turn it off in under 5 seconds (not 30 seconds). Add an event-driven invalidation channel: when a flag is changed, publish a "flag_changed:show_new_checkout" event to Redis pub/sub. All application servers delete their local copies of that flag's cache entries immediately. This gives you near-instant propagation for emergency changes while TTL handles normal staleness for unchanged flags.
- In-process vs Redis: for flag evaluations, consider a two-tier approach. Redis (L2) reduces external service calls from 10,000 to 3,333 QPS. An in-process cache (L1) with 5-second TTL further reduces Redis calls. Application server receives 10,000 flag requests. L1 hit rate ~85% (most users request flags multiple times per 5 seconds). L1 misses: 1,500 go to Redis. L2 hit rate ~95%. L2 misses: 75 go to the external flag service. External flag service load: 75 QPS instead of 10,000.
- Follow-up: You cache flag results in-process with 5-second TTL. A user's account is suspended (security incident). The flag evaluation for "is_account_active" is cached as "true" in the in-process cache with 4.5 seconds remaining. For 4.5 seconds, API requests from the suspended account are served normally. Is this acceptable? For what categories of flags (feature experiments vs security gates) should you NOT cache, and how do you enforce this distinction across a team of 50 engineers?

---

**Question 45 -- Redis persistence: RDB vs AOF and the caching use case paradox**

Your Redis instance serves two workloads simultaneously: (1) a cache layer where data loss on restart is acceptable (the app can re-warm from the database), and (2) a session store where data loss on restart means all users are logged out (a bad user experience). Redis persistence options are RDB (periodic snapshots) and AOF (append-only log of every write). Design the persistence configuration and explain why using Redis as both a cache AND a durable store creates a fundamental tension.

- RDB (snapshot) semantics: Redis forks and saves the entire dataset to disk every N minutes or after M writes (configurable). On restart, Redis loads the RDB file. Data written between the last snapshot and the crash is lost. Typical RDB config: save 900 1 (save if 1 write in 900 seconds), save 300 10 (save if 10 writes in 300 seconds), save 60 10000 (save if 10,000 writes in 60 seconds). For a session store with 10,000 writes/second, RDB loses at most 60 seconds of writes. For a pure cache, RDB is unnecessary overhead.
- AOF (append-only log) semantics: every write command is appended to a file on disk. On restart, Redis replays the AOF log to rebuild state. AOF with fsync=always means zero data loss (every write is fsynced to disk before the client gets a response) but adds 1-5ms of disk I/O latency to every write. AOF with fsync=everysec means at most 1 second of data loss with minimal latency impact. For a session store, fsync=everysec is the right trade-off (1 second of session loss vs 5ms added latency to every login).
- The fundamental tension: if Redis serves as both a cache and a session store, any persistence configuration is wrong for one of the two workloads. With AOF enabled, your cache layer pays the AOF write overhead for every cache SET command -- but cache data loss is acceptable, so this overhead is pure waste. With AOF disabled, your session store has no durability -- crash = all sessions lost.
- Correct solution -- separate Redis instances: run two Redis instances. Instance 1 (cache): no persistence (save ""), maxmemory-policy=allkeys-lru. Instance 2 (session store): AOF with fsync=everysec, maxmemory-policy=noeviction (never evict sessions). Different connection strings in the application, different monitoring thresholds, different SLAs.
- Follow-up: You separate the instances. Instance 2 (session store) runs out of memory (maxmemory-policy=noeviction means Redis refuses new writes when full rather than evicting). New login attempts fail with OOM errors. Users cannot log in. How do you size Instance 2 to avoid this, how do you monitor for approaching memory limits, and what is the right emergency response if Instance 2 fills up unexpectedly?

---

### Section F: Cross-Chapter Integration (Q46-Q52)

---

**Question 46 -- Ch31 + Ch28: Redis hit rate 45% -- is the cache worth keeping?**

You add a Redis cache in front of PostgreSQL. After 2 weeks of production traffic, the cache hit rate is 45%. Your PostgreSQL database is handling the load fine. The Redis instance costs $400/month and requires occasional maintenance. Your team debates: "Should we remove the cache, or fix it?" Design the decision framework and the diagnosis process.

- First: 45% hit rate is a signal of a design problem, not a performance number to optimize directly. A well-designed cache for a real workload should achieve 70-90%+ hit rate. 45% suggests one of: (a) your cache key includes dynamic components that prevent reuse, (b) your TTL is so short that items expire before being requested again, (c) your data is genuinely not cache-worthy (high churn, low reuse), or (d) your cache is undersized and evicting items before they can be hit again.
- Diagnosis process: Step 1 -- sample 1,000 cache misses and classify them. Are the missed keys ones that have never been in the cache ("cold miss") or ones that were previously cached but expired or were evicted ("warm miss" / "capacity miss")? Cold misses indicate items that are never reused -- suggesting the data is not cache-worthy. Warm misses indicate capacity or TTL issues. Step 2 -- check eviction rate (INFO stats). High eviction = cache too small. Step 3 -- check key diversity. If your top 1,000 keys account for 90% of misses, the problem is clear.
- When 45% hit rate still justifies the cache: the cache is worth keeping if (a) those 45% hits save a significant latency spike (e.g., the uncached queries are 500ms each and you are saving 45,000 database queries per day), (b) the database is actually struggling without the cache and would need expensive scaling, or (c) the cache provides a circuit-breaker function (database outage tolerance) beyond just performance.
- When to remove the cache: remove it if (a) the database handles all traffic without degradation, (b) the 45% hit rate cannot be improved (data is genuinely not cacheable), and (c) the operational overhead (maintenance, incidents, added latency on every cache miss) exceeds the benefit. Before removing, run a 24-hour load test with the cache disabled to measure database behavior under full traffic.
- What hit rate justifies added complexity: there is no universal number. The break-even depends on miss cost (database query time), hit benefit (cache response time), and operational cost. If database queries are 50ms and cache hits are 1ms, even a 30% hit rate provides meaningful latency reduction for 30% of traffic. The question is whether that latency reduction justifies the operational cost. For most teams, below 60% hit rate should trigger a redesign of the caching strategy before keeping the cache as-is.
- Follow-up: You diagnose that hit rate is 45% because your application generates session-specific cache keys (including user ID in keys that are not actually user-specific -- e.g., "product:42:session:abc123" when "product:42" would suffice). Fixing the key naming would increase hit rate to 85%. But 50+ microservices generate these keys. How do you coordinate the key naming fix across 50 services without a "big bang" deployment, and how do you avoid the mixed-key-format transition period causing a stampede?

---

**Question 47 -- Ch31 + Ch29: three layers of cache -- reasoning about layered cache sizing**

PostgreSQL has a shared_buffers setting (its internal page cache, typically 25% of RAM). Your application adds a Redis cache on top. Now you have three cache layers: PostgreSQL's page cache (L1 from the database's perspective), Redis (L2), and optionally your application's in-process cache (L3). How do you reason about sizing each layer when they overlap in function?

- What each layer caches: PostgreSQL shared_buffers caches raw 8KB data pages. Redis caches application-level objects (serialized JSON, computed results). The application in-process cache caches deserialized objects (live Java/Python objects, no serialization overhead). These are different representations of overlapping data -- "product 42's details" may live as a PostgreSQL data page in shared_buffers AND as a serialized JSON blob in Redis AND as a deserialized Product object in the in-process cache.
- The double-caching problem: if Redis has a 90% hit rate, 90% of requests are served by Redis and never touch PostgreSQL. PostgreSQL's shared_buffers only receives traffic for the 10% of requests that miss Redis. Sizing shared_buffers for "full traffic" is wasteful -- PostgreSQL only needs to serve 10% of traffic. A smaller shared_buffers setting is appropriate when Redis hit rate is high. Rule of thumb: size shared_buffers for (expected_cache_miss_rate x total_data_size x 1.5x buffer). At 10% miss rate and 100GB of hot data, size shared_buffers for ~15GB of hot data access patterns.
- Interaction effect: if you increase Redis TTL (to improve hit rate), PostgreSQL's shared_buffers becomes less critical (fewer requests reach it). If you reduce Redis memory (to save cost), more requests fall through to PostgreSQL, and shared_buffers becomes more critical. The layers interact -- you cannot size them independently.
- The correct reasoning approach: work top-down. Start with expected application-layer miss rate (your target for the in-process cache). Then model Redis miss rate given the in-process cache miss rate. Then model PostgreSQL query load given the Redis miss rate. Size each layer based on the actual traffic it will receive, not theoretical total traffic.
- Follow-up: Your Redis is sized at 10GB and serves a dataset where 80% of traffic goes to 2GB of "hot" data. PostgreSQL shared_buffers is 16GB (25% of a 64GB database server). The hot data is almost certainly in shared_buffers. When Redis misses (10% of traffic), the PostgreSQL query hits shared_buffers and returns in 0.5ms instead of the 5ms you planned for. Your latency model was wrong -- cache misses are faster than expected. Does this change your Redis sizing decision? Should you make Redis smaller and rely more on PostgreSQL's own caching?

---

**Question 48 -- Ch31 + Ch32: diagnosing Redis eviction with 50M keys**

Your Redis cache key space has 50 million keys. Eviction rate is spiking (1 million evictions per minute). Hit rate drops to 60%. Redis INFO memory shows mem_fragmentation_ratio=2.1. Walk through the full Redis internals diagnosis using Redis-specific tools and metrics, and explain what changes you make.

- Step 1 -- Understand what is being evicted: run `redis-cli --scan | redis-cli DEBUG OBJECT` on a sample of keys to see key sizes and LRU idle times. Better: use `redis-cli --hotkeys` (requires LFU policy) or `redis-cli OBJECT FREQ` to find which keys have low frequency scores (LFU eviction candidates) or high idle times (LRU eviction candidates). Are the evicted keys items you actually wanted to keep? Or are they genuinely cold items?
- Step 2 -- Memory fragmentation analysis: mem_fragmentation_ratio of 2.1 means Redis is using 2.1x more RSS memory than it actually needs for data. This is high -- normal is 1.0-1.5. At maxmemory=10GB and fragmentation_ratio=2.1, Redis is using 21GB of OS memory but only 10GB is actual data. The 11GB of fragmentation is "wasted" memory that Redis has allocated but cannot use effectively. This can cause premature eviction -- Redis thinks it is at maxmemory when it actually has fragmentation headroom.
- Step 3 -- Fix fragmentation: enable activedefrag yes in Redis 6.0+ config. This runs an online defragmentation process that moves keys to consolidate memory without requiring a restart. Set active-defrag-threshold-lower 10 (start defrag when fragmentation exceeds 10%) and active-defrag-threshold-upper 100 (max CPU for defrag). After enabling, watch mem_fragmentation_ratio over 1-2 hours -- it should decrease toward 1.2-1.5.
- Step 4 -- Key size analysis: use `redis-cli --bigkeys` to identify the top 10 keys by memory consumption. A single key with 500MB of data is unusual and may indicate a design problem (e.g., a list that is never trimmed, a sorted set that grows indefinitely). Fixing large keys frees significant memory.
- Step 5 -- Eviction policy tuning: if eviction is still high after fixing fragmentation, and you confirm that evicted keys are ones you wanted to keep, you have a genuine capacity problem. Options: increase maxmemory (upgrade Redis instance), switch from allkeys-lru to allkeys-lfu (if your access pattern has clear hot/cold distinction -- LFU will preferentially keep hot keys), or reduce the number of keys by aggregating data (instead of one key per product per attribute, use one hash per product with all attributes).
- Follow-up: You enable activedefrag and fragmentation drops from 2.1 to 1.3. But eviction rate is still high (800K evictions/minute instead of 1M). You upgrade the Redis instance from 16GB to 32GB RAM. Eviction rate drops to 0. Three months later, eviction spikes again (the key space has grown from 50M to 80M keys). Is the right response to keep scaling up RAM, or is there a fundamental key management problem to fix? How do you implement key lifecycle management (automatic cleanup of stale keys) to prevent unbounded key space growth?

---

**Question 49 -- Ch31 + Ch33/34: Kafka-driven cache invalidation and crash recovery**

You use Kafka to propagate cache invalidation events across 10 services. A service goes down for 2 hours. When it comes back: its cache has stale data AND it has 2 hours of Kafka invalidation events to consume. Design the recovery strategy.

- The dual problem: the restarting service has two sources of incorrectness. (1) Its local Redis cache may contain stale entries for any key that was invalidated during the 2-hour downtime. (2) Its Kafka consumer has a 2-hour backlog of invalidation events to process. If it processes the backlog slowly while serving traffic, it may serve stale cache data for minutes or hours after restart.
- Option 1 -- Flush the cache on restart: when the service restarts, flush its entire cache (FLUSHDB or FLUSHALL). This guarantees zero stale data. The service starts with a cold cache and warms up from traffic. Backlog of Kafka invalidation events can be skipped (seek to latest offset) because the cache is already empty. Trade-off: cold cache on restart causes thundering herd on the upstream database. Only acceptable if the service's cache is not a critical hot-path cache (i.e., cold-cache performance is tolerable).
- Option 2 -- Process the Kafka backlog first, then start serving traffic: the service restarts in "recovery mode." It consumes the Kafka backlog from its last committed offset until it reaches the current head (head offset can be queried from Kafka). For each invalidation event, it deletes the corresponding cache key. After catching up to the current head, the service switches to "serving mode." Trade-off: the service is unavailable for the 2-hour backlog processing time. If backlog processing takes 30 minutes, the service is down for 30 extra minutes. During this time, other service instances must handle traffic.
- Option 3 -- Serve traffic with TTL safety net, process backlog in background: the service restarts immediately and begins serving traffic (with potentially stale cache). Simultaneously, it processes the Kafka backlog in background at high speed. For each invalidation event it processes, it deletes the cache key. The cache gradually becomes consistent as the backlog is consumed. Stale data window: depends on backlog consumption speed vs serving rate. If the backlog takes 10 minutes to consume, stale data may persist for 10 minutes after restart. The TTL on cache entries acts as a final safety net for any invalidation events that were missed.
- Option 4 -- Versioned cache with database-authoritative version check: instead of relying on invalidation events for consistency, compare the cache entry's stored version number against the database's current version number on every read. If the cache version is behind the database version, treat it as a miss. This makes the recovery trivial (no need to process Kafka backlog for cache consistency -- the database comparison handles it) but adds a database read to every cache hit for the version check.
- Follow-up: You choose Option 3. The Kafka backlog contains 2 million invalidation events from the 2 hours of downtime. Events arrived at 280 events/second. Your Kafka consumer in recovery mode processes 5,000 events/second. The backlog will be consumed in 2,000,000 / 5,000 = 400 seconds (6.7 minutes). During those 6.7 minutes, all serving traffic from this service instance may serve stale cache data. What percentage of served requests will have stale data, and how does this affect your decision between Options 2 and 3?

---

**Question 50 -- Ch31 + Ch35: batch pre-computation and warm cache rotation**

Your batch pipeline pre-computes results (top 100 trending products) every 4 hours. The results are cached in Redis. During the 4-hour compute window, users get stale results. At the end of the 4-hour window, the new results are loaded and all users see a sudden "jump" in the trending list (a jarring UX). Design the warm cache rotation strategy.

- The problem statement precisely: at T=0 (batch starts), trending list is [product A, B, C, ...]. The batch runs until T=4h. At T=4h, trending is now [product X, Y, Z, ...] (completely different -- market shifted during the compute). The cache is atomically replaced. Every user who refreshes at T=4h:01 sees a completely different list. This is acceptable for a "trending" list but jarring.
- Strategy 1 -- Blue/green cache rotation: maintain two Redis namespaces: "trending:blue" and "trending:green", with a pointer key "trending:active" set to "blue" or "green". While the batch runs, it writes to the inactive namespace (e.g., "trending:green" while "trending:blue" is serving traffic). When the batch completes, atomically flip "trending:active" from "blue" to "green". Application servers read the pointer on every request (or every 5 seconds) and route to the active namespace. No downtime, no stale data from the old namespace continuing to serve after the flip.
- Strategy 2 -- Incremental rolling update: instead of replacing all results at T=4h, run a lighter mini-batch every 30 minutes that updates only the top 10 products (the most time-sensitive ones). Run the full 4-hour batch for the full top-100 update. Users see gradual changes every 30 minutes rather than a sudden swap. The mini-batch is cheap because it only computes the top-10 re-ranking (not the full 100) and can use pre-computed partial results from the last full batch.
- Strategy 3 -- Continuous streaming with Kafka: replace the batch job with a streaming pipeline (Apache Flink or Spark Streaming) that continuously processes clickstream events and updates the trending list. Redis is updated in near-real-time (every 60 seconds). No "stale during batch compute" problem. Trade-off: streaming infrastructure is significantly more complex and expensive to operate than a nightly batch job. Justified at Netflix/Amazon scale; probably not at smaller scale.
- The "staleness is OK for trending" argument: trending products are by definition an approximation of recent popularity. A 4-hour-old trending list is still useful -- it shows products that were trending 4 hours ago, which is likely still roughly correct. The business should define the maximum acceptable staleness for the use case. If the marketing team is fine with 4-hour-old trending data, strategy 1 (blue/green rotation) is sufficient and simple. If they need 30-minute freshness, strategy 2. If they need real-time, strategy 3.
- Follow-up: You implement blue/green rotation. The batch job writes to the green namespace while blue is serving traffic. Halfway through the batch (2 hours in), the batch job crashes. Green namespace is half-written (partially correct data -- trending for categories A-M is new, N-Z is missing). "trending:active" still points to blue (the complete but 2-hour-old data). What do you do? When should the "active" pointer be flipped -- at the start of the batch, halfway through, or only on successful completion? Design the batch job's commit protocol.

---

**Question 51 -- Ch31 + Ch36: multi-region cache invalidation for user profiles**

You have Redis caches in US-East and EU-West. A user's profile is updated in EU-West (where the user is). The US-East cache still has the old version. The TTL is 5 minutes. Design the invalidation strategy. For what data types is eventual cache consistency acceptable vs not?

- The eventual consistency window: with TTL-only invalidation, US-East may serve stale profile data for up to 5 minutes. For a display name or profile picture change, 5 minutes is acceptable. For an email address change (used for login and notifications), 5 minutes of stale email may cause emails to be sent to the old address during those 5 minutes. For account suspension ("this user violated our terms"), 5 minutes of stale "account active" data means the suspended user can make 5 minutes of API requests.
- Cross-region invalidation architecture: when the EU-West user service writes a profile update, it publishes an "invalidate:profile:user:42" event to a global message bus (e.g., a Kafka cluster with multi-region replication, or AWS EventBridge with cross-region event delivery). The US-East user service subscribes to this event bus. On receiving the event, US-East deletes "profile:user:42" from its Redis cache. Propagation time: typically 200-500ms across regions (network round-trip + Kafka propagation latency).
- What data types allow eventual cache consistency: (1) display preferences (theme, language setting), (2) profile display data (name, bio, avatar URL), (3) non-security notification preferences, (4) analytics and behavioral data. For these, 5-minute or even 15-minute TTL staleness is acceptable. The product experience is not materially harmed.
- What data types require strong consistency (zero-tolerance for stale cache): (1) account suspension / active status (security -- a suspended user must be blocked immediately), (2) user permissions and roles (security), (3) payment method validity (financial -- a removed credit card must not be chargeable), (4) email address (used for auth -- wrong address during password reset is a serious UX and security issue). For these, use explicit invalidation events AND set a short TTL (30-60 seconds) as a safety net.
- Multi-region invalidation failure mode: the Kafka event is published in EU-West. Due to a network partition, the event does not reach US-East for 8 minutes (exceeding your 5-minute TTL). During those 8 minutes, the TTL expires anyway and US-East re-fetches from its local database (which may be a read replica that is itself 500ms behind EU-West due to replication lag). US-East now has data that is correct as of 500ms ago -- essentially fresh. The network partition scenario is self-healing through TTL + replica replication.
- Follow-up: Your EU-West to US-East Kafka replication fails for 2 hours (network partition between regions). During those 2 hours, 50,000 profile updates occur in EU-West. When the partition heals, 50,000 invalidation events flood into US-East in a burst. US-East Redis receives 50,000 DEL commands in a few seconds. How do you rate-limit the invalidation burst to avoid overwhelming US-East Redis, and how do you prioritize security-sensitive invalidations (account suspension) over display-preference invalidations in the burst processing order?

---

**Question 52 -- Ch31 + Ch37 + Ch38: GDPR-compliant CDN caching and cost optimization**

EU user profile data is cached in a US-East CDN edge node (CloudFront). This is a GDPR violation -- EU personal data stored in the US without explicit consent or legal basis. Simultaneously, your CDN serves 500TB/month globally and you want to reduce cost. CloudFront charges $0.0085/GB. Your cache hit rate is 70% (30% goes to origin). Origin egress: 150TB/month at $0.09/GB. Calculate total costs, design the GDPR-compliant caching strategy, and find the cost optimization.

- Current cost calculation: CDN egress: 500TB x 1024 GB/TB x $0.0085/GB = approximately $4,352/month. Origin egress: 500TB x 30% = 150TB x 1024 GB/TB x $0.09/GB = approximately $13,824/month. Total: approximately $18,176/month. Origin egress is 76% of the total CDN cost -- hidden and often overlooked.
- GDPR-compliant caching architecture: GDPR Article 44 prohibits transferring EU personal data to countries outside the EU without appropriate safeguards (adequacy decision, SCCs, BCRs). Cached EU user profile data in a US CDN node is a transfer. Solution: use CloudFront's geo-restriction and price class features to restrict EU user traffic to EU edge locations only (CloudFront Price Class 100 includes EU + US; use geo-restriction rules to route EU users to EU-only PoPs). For Cloudflare: use Data Localization Suite to ensure EU data never leaves EU edge nodes.
- What can be cached at US edge nodes: non-personal data. Static assets (CSS, JS, images not tied to a specific user), public product catalog data, marketing content, documentation. Per GDPR, "personal data" is any information that relates to an identified or identifiable natural person. A user's name, email, preferences, behavioral data -- all personal. Product descriptions, public pricing, general content -- not personal.
- What must stay in EU: any EU user's profile data, purchase history, behavioral analytics, session data, personalization data. These must only be cached in EU-located cache nodes.
- Cost optimization via hit rate improvement: if you increase TTL on static assets (currently 1 hour) to 24 hours, hit rate for static assets improves from 70% to 92%. Total traffic: 500TB, of which 60% is static (300TB) and 40% is dynamic/user-specific (200TB). After TTL improvement, static hit rate: 92%, dynamic hit rate: 70% (user-specific, cannot cache in US for EU users). Blended hit rate: (0.60 x 0.92) + (0.40 x 0.70) = 0.552 + 0.280 = 83.2%. New origin egress: 500TB x 16.8% = 84TB x $0.09/GB x 1024 = approximately $7,741/month. Cost saving: $13,824 - $7,741 = $6,083/month on origin egress alone.
- Impact of increasing TTL from 1 hour to 24 hours on cost: static assets serve 60% of traffic. Increasing TTL means fewer origin fetches for static content. As calculated, origin egress drops from 150TB to 84TB/month, saving $6,083/month. However, CDN storage costs increase marginally (more objects cached longer -- typically negligible at CloudFront pricing). The 24-hour TTL also requires implementing the cache purge system (designed in Q35) for the marketing team to push urgent updates.
- Follow-up: You implement EU data localization. Six months later, the UK exits its data adequacy agreement with the EU (hypothetical). Your CloudFront UK edge nodes (which you had classified as "EU-equivalent") are now legally equivalent to US nodes -- EU personal data cannot be cached there. You have UK edge nodes that are currently caching EU user profiles. Design the emergency response: how quickly can you implement geo-restriction rules in CloudFront to exclude UK nodes from EU personal data caching, how do you verify the change is working, and how do you audit historical CDN logs to determine whether any EU personal data has already been served from UK nodes to non-EU users?

---

*End of Supplemental Brainstorming: Chapter 31 -- Caching at Scale*

*Total questions: 52 (Q1-Q5 in main chapter, Q6-Q52 here = 47 supplemental questions across 6 sections)*

*Cross-chapter coverage: Ch28 (databases), Ch29 (DB internals), Ch32 (Redis internals), Ch33/34 (Kafka), Ch35 (batch processing), Ch36 (multi-region), Ch37 (compliance), Ch38 (cost)*

---

## Exercises

**Exercise 1 — Cache strategy selection.** Choose a caching strategy for each scenario: (a) user profile reads (10M users, updated rarely, 500KB profile), (b) product inventory (updated frequently, must be accurate for checkout), (c) social feed (100M items, personalized, 5-minute staleness OK), (d) rate limiting counter (must be accurate, fast, durable). Justify each choice.

**Exercise 2 — Cache hit rate calculation.** Your database handles 50K RPS. You add a cache with a 90% hit rate. How many requests reach the database now? If cache hit rate drops to 70%, what happens to database load? At what hit rate does the database become the bottleneck (max 20K RPS)?

**Exercise 3 — Cache invalidation strategy.** You cache user profile data. A user updates their display name. Design 3 invalidation strategies: (a) TTL only (5 minutes), (b) delete-on-write, (c) write-through. For each: max staleness, implementation complexity, failure behavior when cache is unavailable.

**Exercise 4 — CDN configuration design.** You're serving a web app with: HTML pages (change per deploy), CSS/JS (immutable, versioned), user-uploaded images (never change), API responses (vary by user). For each asset type: cache-control header, CDN TTL, purge strategy, and whether to serve from edge or origin.

**Exercise 5 — Redis cluster sizing.** You need to cache 100GB of data with 100K operations/second. Single Redis node can handle 200K ops/second and 25GB memory. Design the Redis cluster: number of nodes, sharding strategy, replication factor, and failover behavior.

**Exercise 6 — Thundering herd prevention.** Your cache warms up after a deploy. For 30 seconds, all cache misses go to the database simultaneously. Your database can handle 10K RPS but receives 200K RPS during warmup. Design three solutions: probabilistic early expiration, request coalescing, and tiered warmup.

---

## Homework

**Assignment 1 — Cache hit rate audit.** Find the cache hit rate for every cache your team uses. For any cache with hit rate below 80%: analyze why (key structure, TTL too short, cold keys, thundering herd) and propose a fix. Document the expected impact.

**Assignment 2 — CDN configuration review.** Pull your CDN access logs. Find: top 10 most-requested URLs, cache hit rate per URL type, and any URLs with unexpectedly low hit rates. Propose TTL changes that would improve hit rate without increasing staleness risk.

**Assignment 3 — Interview practice: caching design.** Practice "design a caching layer for a social media feed" in 20 minutes. Cover: what to cache, where to cache it (client/CDN/app/DB), cache invalidation on updates, failure behavior, and the consistency model you're accepting.

**Assignment 4 — Read the Facebook Memcache paper ("Scaling Memcache at Facebook," 2013).** Write a one-paragraph summary: what was the thundering herd problem they encountered, what was "lease" and how did it solve it, and what does this tell you about cache design at scale?
