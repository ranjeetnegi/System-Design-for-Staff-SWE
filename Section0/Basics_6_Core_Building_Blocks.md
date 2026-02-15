# Basics Chapter 6: Core Building Blocks — Hash, Cache, State, Idempotency, Queues, Sync/Async

---

## Introduction

Every distributed system is built from a small set of fundamental building blocks. A rate limiter uses hash functions to distribute keys and state to track usage. A payment flow uses idempotency keys to safely retry. A notification system uses queues to decouple senders and delivery. A feed service uses caching to reduce database load. These blocks are everywhere—**hash functions** that distribute data, **caches** that accelerate reads, **state** (or its absence) that determines scalability, **idempotency** that enables safe retries, **queues** that decouple producers and consumers, and **sync vs async** patterns that shape latency and consistency.

Staff Engineers don't just use these blocks; they understand the trade-offs. When to cache and when to invalidate. When to be stateless and where to put state. When to make an operation idempotent and how. When to use a queue instead of a direct call. When sync is appropriate and when async changes the game. This chapter gives you that depth—the intuition, the mechanics, and the Staff-level judgment that turns building blocks into robust architectures.

---

## Part 1: Hash Functions

### What Is a Hash Function?

A **hash function** maps an input of arbitrary size to a fixed-size output (the "hash" or "digest"). It has three key properties:

| Property | Meaning |
|----------|---------|
| **Deterministic** | Same input → always same output |
| **Fixed output size** | Output length is constant regardless of input size |
| **One-way** (for cryptographic hashes) | Given the hash, you cannot recover the input |

**Example**: SHA-256("hello") always produces the same 256-bit (32-byte) output. Change one character, and the output changes completely (avalanche effect).

### Common Hash Functions

| Hash | Output Size | Use Case |
|------|-------------|----------|
| **MD5** | 128 bits | Deprecated for security; still used for checksums |
| **SHA-256** | 256 bits | Cryptographic integrity, content addressing |
| **xxHash, MurmurHash** | 32–64 bits | Non-cryptographic; fast for hash tables, partitioning |
| **bcrypt, Argon2** | Variable | Password hashing (slow by design) |

**When to use which**: For distributing data across nodes (consistent hashing, sharding), use fast non-cryptographic hashes. For integrity (checksums, content-addressable storage), use SHA-256. For passwords, use bcrypt or Argon2—never MD5 or raw SHA.

### Collisions: When Two Inputs Produce the Same Hash

A **collision** occurs when two different inputs produce the same hash. Good hash functions make collisions astronomically rare (SHA-256: 2^256 possible outputs). For non-cryptographic use (hash tables), occasional collisions are handled by chaining or probing.

**Why it matters for system design**: When you hash a key to choose a server, a collision means two keys map to the same server. With a good hash and enough servers, collision rate is negligible. For security (password hashing), collisions would let an attacker find another password that hashes the same—cryptographic hashes are designed to prevent this.

### Uses in System Design

| Use Case | How Hash Is Used |
|----------|------------------|
| **Hash tables** | Key → hash → bucket index. O(1) lookup. |
| **Consistent hashing** | Hash keys and server IDs onto a ring. Key goes to nearest server. |
| **Sharding** | hash(user_id) % N → shard index. Even distribution. |
| **Checksums** | Hash content to verify integrity (file transfer, storage). |
| **Cache keys** | Hash query parameters → cache key. Deduplicate identical requests. |
| **Password storage** | Hash(password + salt). Never store plaintext. |
| **Content addressing** | Hash(content) = content ID (e.g., Git, IPFS). |

### Consistent Hashing: The Key to Distributed Caches and Databases

**Problem**: Simple modulo hashing—`hash(key) % N`—redistributes almost all keys when N changes (when you add or remove a server). That causes a thundering herd of cache misses or data migration.

**Consistent hashing**: Map both keys and servers onto a ring (0 to 2^32 or 2^64). A key maps to the first server clockwise from its position. Add a server: only keys between its predecessor and it move. Remove a server: only its keys move to the next server.

```
    ┌─────────────────────────────────────────────────────────────────────────┐
    │                    CONSISTENT HASHING RING                               │
    │                                                                         │
    │                          0 / 2^32                                       │
    │                              │                                          │
    │                    Node A ●───┼───● Node D                               │
    │                          ╲   │   ╱                                      │
    │                           ╲  │  ╱                                       │
    │                    Key K1 ●  │  ● Key K2                                │
    │                           ╱  │  ╲                                       │
    │                    Node B ●───┼───● Node C                              │
    │                              │                                          │
    │   Key K1 → hashes to point between Node D and Node A → goes to Node A   │
    │   Key K2 → hashes to point between Node C and Node D → goes to Node D    │
    │                                                                         │
    │   Add Node E between A and D: only keys in that arc move to E           │
    │   Remove Node B: only B's keys move to C                                 │
    │                                                                         │
    └─────────────────────────────────────────────────────────────────────────┘
```

**Virtual nodes (vnodes)**: To reduce imbalance, each physical server is hashed multiple times (e.g., 100–200 "virtual" positions). This smooths distribution when servers are added or removed.

### ASCII Diagram: Hash Ring with Virtual Nodes

```
                         Ring (0 to 2^32)
    ┌──────────────────────────────────────────────────────┐
    │                                                       │
    │   A1    B1    C1    D1    A2    B2    C2    D2       │
    │    ●-----●-----●-----●-----●-----●-----●-----●       │
    │   ╱                                           ╲      │
    │  ●                                             ●     │
    │  D3                                            A3    │
    │   ╲                                           ╱      │
    │    ●-----●-----●-----●-----●-----●-----●-----●       │
    │   C3    D4    A4    B3    C4    D5    A5    B4       │
    │                                                       │
    │   A1, A2, A3, A4, A5 = virtual nodes for Server A    │
    │   Better distribution than 4 nodes with 1 position    │
    │                                                       │
    └──────────────────────────────────────────────────────┘
```

### Consistent Hashing Deep Dive: Algorithm Walkthrough

**Hash ring construction**: Map the output space (0 to 2^32 - 1) to a ring. Each node gets one or more positions on the ring via `hash(node_id)` or `hash(node_id + "#" + vnode_index)`. Each key maps to a position via `hash(key)`. The key belongs to the first node clockwise from its position.

**Algorithm**:
1. Sort node positions on the ring (ascending order)
2. For key K: find smallest node position ≥ hash(K). If none (wraparound), use first node
3. Binary search or jump table for O(log N) lookup

**Adding a node**: Insert new node's position(s) on the ring. Keys between the new node and its predecessor (counter-clockwise) move to the new node. Only ~1/N of keys relocate.

**Removing a node**: Remove node's position(s). Its keys move to the next node clockwise. Again ~1/N of keys move.

**Virtual nodes (vnodes)**: Each physical node is hashed 100–200 times with different suffixes (e.g., "A#0", "A#1", ... "A#149"). Distributes one node's share across the ring. Without vnodes: if you have 3 nodes, one might get 50% of keys by chance. With 150 vnodes each, distribution smooths. Adding/removing a node spreads the movement across many arcs.

**Worked example with ASCII**:

```
    BEFORE: 3 nodes (A, B, C), ring 0–360 simplified

                        0
                        │
              C ●───────┼───────● A
                 ╲      │      ╱
                  ╲     │     ╱
              K1 ● │     │     ● K2
                  ╱     │     ╲
                 ╱      │      ╲
              B ●───────┼───────●
                      180

    K1 hashes to 45°  → clockwise to A  (K1 → A)
    K2 hashes to 270° → clockwise to B  (K2 → B)

    ADD node D at 30° (between C and A):

                        0
                        │
              C ●───────┼──● D  (NEW)
                 ╲      │  ╱
                  ╲     │ ╱
              K1 ● │    │ ● K2
                  ╱     │ ╲
                 ╱      │  ╲
              B ●───────┼────● A

    Keys between C and D (arc from ~330° to 30°) move to D.
    K1 (at 45°) still maps to A. Keys in arc 330°–30° move to D.
    Only ~1/4 of keys move (one arc of four).

    REMOVE node B:

    B's keys (arc 180°–270° roughly) move to C (next clockwise).
    K2 moves from B to C. Only B's keys are affected.
```

### Hash-Based Sharding vs Consistent Hashing

**Simple hash sharding**: `shard = hash(key) % N`. Problem: when N changes (add/remove node), almost all keys remap. If you go from 10 to 11 shards, ~90% of keys move. That's a lot of cache invalidation or data migration.

**Consistent hashing**: Only K/N keys move when you add or remove a node (K = total keys, N = nodes). Adding one node: ~1/N of keys move to it. Removing one: its keys go to the next node. This is why distributed caches (Memcached, Redis Cluster) and storage systems (Dynamo, Cassandra) use it. Staff Engineers understand both and choose based on resize frequency and tolerance for movement.

### Hash Collisions in Distributed Systems

For partitioning, collisions (two keys to same hash) aren't a problem—you want many keys per partition. For content-addressable storage (hash of content = ID), collisions are catastrophic: two different contents with same hash would be indistinguishable. SHA-256's 2^256 space makes this negligible. For password hashing, collisions would let an attacker find another password that hashes the same—use bcrypt/Argon2, which are designed to be collision-resistant and slow.

### L5 vs L6: Hash Functions in System Design

| Aspect | L5 Thinking | L6 Thinking |
|--------|-------------|-------------|
| **Sharding** | "We'll use user_id % 10" | "Modulo causes full redistribution on resize. We'll use consistent hashing or range-based with pre-splitting" |
| **Cache** | "Redis caches by key" | "Our cache uses consistent hashing; adding a node moves ~1/N of keys, not all" |
| **Collisions** | "Hash tables handle them" | "For our 1B keys and 32-bit hash, birthday paradox gives ~50K collisions—acceptable with chaining" |

**Staff-Level Insight**: Hash function choice affects distribution quality, resize behavior, and security. Don't default—choose based on the problem. Consistent hashing is the standard for distributed caches and key-value stores; understand it cold.

---

## Part 2: Caching — The Everyday Analogy

### Cache = Faster, Smaller Copy of Frequently Accessed Data

A **cache** is a store that holds a subset of data in a faster (and usually smaller) medium than the primary store. The goal: serve most requests from the cache, reducing load on the primary store and improving latency.

**Analogy**: Your desk (cache) vs. the filing cabinet (database). You keep frequently used files on your desk. When you need one, you check the desk first. If it's there, you use it. If not, you walk to the cabinet, fetch it, and optionally put a copy on your desk for next time.

### Types of Caches

| Cache Type | Where It Lives | What It Caches | Typical Hit Rate |
|------------|----------------|----------------|-------------------|
| **Browser cache** | Client | Static assets, API responses | Varies by user |
| **CDN cache** | Edge (near users) | Static assets, sometimes dynamic | 80–95% for static |
| **Application cache** | Server (Redis, Memcached) | DB results, computed data | 80–99% |
| **Database query cache** | Inside DB | Query results | 50–90% |
| **CPU cache (L1/L2/L3)** | CPU | Memory accesses | 95%+ |

**Layered caching**: A single request might hit browser cache → CDN → application cache → database. Each layer reduces load on the next.

### Cache-Aside (Lazy Loading) Pattern

The most common pattern: the application manages the cache. The cache doesn't know about the database.

```
    1. Receive request for key K
    2. Check cache
    3. If HIT: return cached value
    4. If MISS: fetch from DB
    5. Store in cache (for future requests)
    6. Return value
```

```
    ┌─────────────────────────────────────────────────────────────────────┐
    │                    CACHE-ASIDE PATTERN                               │
    │                                                                     │
    │   Request for key "user:123"                                         │
    │                                                                     │
    │   ┌─────────┐     1. Get user:123    ┌─────────┐                   │
    │   │  App    │ ───────────────────►  │  Cache  │                   │
    │   │ Server  │                        │ (Redis) │                   │
    │   │         │  2a. MISS               │         │                   │
    │   │         │ ◄───────────────────   │         │                   │
    │   │         │                         │         │                   │
    │   │         │  3. SELECT * FROM users  │         │                   │
    │   │         │ ───────────────────►   │         │                   │
    │   │         │                        │         │  ┌─────────┐      │
    │   │         │  4. Return row          │         │  │   DB    │      │
    │   │         │ ◄───────────────────   │         │  └─────────┘      │
    │   │         │                         │         │                   │
    │   │         │  5. SET user:123        │         │                   │
    │   │         │ ───────────────────►   │         │                   │
    │   │         │                         │         │                   │
    │   │         │  6. Return to client    │         │                   │
    │   └─────────┘                         └─────────┘                   │
    │                                                                     │
    └─────────────────────────────────────────────────────────────────────┘
```

**Write path**: On write (create/update/delete), the app typically invalidates the cache (delete the key) or updates it. This keeps the cache consistent with the DB, at the cost of a possible cache miss on the next read.

### Cache Hit Rate: The Multiplier Effect

If 95% of requests hit the cache, only **5%** reach the database. That's a **20×** reduction in DB load. A system that would need 100 DB replicas to handle 2M read QPS needs only 5 replicas if cache handles 95%—and the cache might be 10–20 Redis nodes. The cost and complexity drop dramatically.

**Target hit rates by use case**:
- **Session data**: 99%+ (same user, same session)
- **User profile**: 90–95% (frequently accessed, moderately changing)
- **Product catalog**: 95–99% (mostly static)
- **Real-time feed**: 70–90% (more dynamic, harder to cache)
- **Search results**: 50–80% (high cardinality, many unique queries)

If your DB can handle 10K QPS and you have 200K read QPS, you need a 95% hit rate (10K DB reads) or better. Cache hit rate directly determines how far your DB can stretch.

**What affects hit rate**:
- **Working set size**: Can your cache hold the hot data? If hot data is 10 GB and cache is 1 GB, you'll miss often.
- **TTL**: Too short = more misses. Too long = stale data.
- **Eviction policy**: LRU (Least Recently Used) is common. LFU (Least Frequently Used) for skewed access patterns.
- **Key design**: Poor key design (e.g., user_id + timestamp for every second) leads to low reuse.

### TTL: Time To Live

**TTL** = how long a cached value is valid. After TTL seconds, the entry expires and is removed (or considered stale). Next request triggers a refresh from DB.

| TTL | Use Case | Trade-off |
|-----|----------|-----------|
| **Short (60–300 s)** | Frequently changing data (prices, inventory) | Fresh, but lower hit rate |
| **Medium (1–24 h)** | User profiles, content metadata | Balance freshness and hit rate |
| **Long (24–72 h)** | Static content, rarely changing data | High hit rate, may serve stale |

**Staff-level**: TTL is a trade-off. No single "right" value. Match TTL to the acceptable staleness of your data. For user-facing "last login" you might use 60 s. For "user's display name" you might use 1 hour.

### Cache Invalidation: The Hard Problem

Phil Karlton: "There are only two hard things in Computer Science: cache invalidation and naming things."

**Why it's hard**: You have multiple sources of truth (cache, DB, other caches). When data changes, you must ensure all copies are updated or invalidated. Miss one, and you serve stale data. Invalidate too aggressively, and you destroy hit rate.

**Strategies**:
| Strategy | How It Works | When to Use |
|----------|--------------|-------------|
| **TTL only** | Rely on expiration. No explicit invalidation. | When eventual consistency is OK |
| **Invalidate on write** | On DB write, delete/update cache key | When strong consistency needed |
| **Write-through** | Write to cache and DB together. Cache is always fresh. | When reads heavily outweigh writes |
| **Write-behind** | Write to cache immediately, async write to DB | When writes are very frequent; risk of loss |
| **Version in key** | Key includes version. Old keys expire. | When you can't invalidate easily (e.g., CDN) |

### Why Staff Engineers Care About Caching

| Concern | Why It Matters |
|---------|----------------|
| **Consistency** | Cache can serve stale data. What's acceptable? |
| **Complexity** | Cache invalidation, stampede, hot keys add complexity |
| **Cost** | Redis/cluster costs money. Is the hit rate worth it? |
| **Failure mode** | Cache down: do you fail or fall through to DB? Fall-through can thundering-herd the DB |
| **Debugging** | "User says data is wrong" — is it cache? DB? Which layer? |

**Staff-Level Insight**: Caching decisions affect consistency, complexity, cost, and user experience. Get it wrong and you either drown your database or serve stale data that confuses users. Design the cache layer with the same rigor as the database layer.

### Cache Stampede and Mitigation

When a popular key expires, many requests suddenly miss the cache and hit the database simultaneously—a **stampede**. One request could refresh; instead, 1000 do. Mitigations:
- **Locking**: First requester acquires a lock, refreshes, releases. Others wait or get stale.
- **Probabilistic early expiration**: When TTL is near end, one request (probabilistic) refreshes early. Spreads load.
- **Background refresh**: Don't expire on read; refresh in background before TTL. Serve stale while refreshing.
- **Bloom filters**: For "does this exist?" queries, a Bloom filter can prevent DB hits for non-existent keys.

Staff Engineers anticipate stampede when designing cache invalidation and choose a mitigation that fits their consistency and load profile.

### Write-Through, Write-Around, Write-Behind

| Pattern | Flow | When to Use |
|---------|------|--------------|
| **Write-through** | Write to cache and DB together. Cache always has latest. | Strong consistency, read-heavy |
| **Write-around** | Write to DB only. Cache populated on read (cache-aside). | Write-heavy, can tolerate read miss |
| **Write-behind** | Write to cache immediately, async write to DB. | Very write-heavy; risk of data loss if cache fails |

Write-through is simplest but doubles write load (cache + DB). Write-behind is fastest but requires careful handling of failures—what if the cache dies before flushing to DB? Most systems use write-around (cache-aside) for simplicity.

### Hot Keys: When One Key Dominates

A **hot key** is a key with disproportionate traffic. Example: a celebrity's profile, a best-selling product, a global config. All requests hit the same cache node or DB shard. That node becomes the bottleneck. Mitigations:
- **Replicate the hot key** across multiple cache nodes (with a layer that fans out reads)
- **Local cache** in the application (each server caches the hot key)
- **Shard the key** (split the value, or use multiple keys for different aspects)
- **Rate limit** if it's abuse

Staff Engineers identify hot keys early (via metrics) and design for them—"every system has a hot path."

---

## Part 3: State vs Stateless

### Stateful: Server Remembers

A **stateful** server keeps information between requests. Examples: session data in memory, in-memory caches, connection state. Request 1 and Request 2 can interact through server-side state.

**Problem**: If the server dies, state is lost. If you have multiple servers, state is fragmented—Request 1 might hit Server A, Request 2 might hit Server B, and B doesn't have A's state. Load balancers must use "sticky sessions" (send same user to same server), which complicates scaling and failover.

### Stateless: Each Request Is Independent

A **stateless** server treats each request in isolation. All information needed to process the request is in the request itself (or in an external store the server looks up). The server does not rely on in-memory state from previous requests.

**Benefit**: Any server can handle any request. Load balancer can round-robin freely. Add servers = add capacity. A server dies = no state lost. Horizontal scaling is straightforward.

### Where to Put State: External Store

When you need state (sessions, user preferences, etc.), put it in an **external store**—Redis, database, etc.—not in the application server's memory. Then the application server can be stateless: it fetches state from the store per request.

```
    ┌─────────────────────────────────────────────────────────────────────┐
    │                    STATEFUL vs STATELESS                              │
    ├─────────────────────────────────────────────────────────────────────┤
    │                                                                     │
    │   STATEFUL (Session in server memory):                               │
    │                                                                     │
    │   Request 1 ──► Server A (stores session) ──► Response                │
    │   Request 2 ──► Load balancer ──► Server B (no session!) ──► Fail    │
    │                                                                     │
    │   Must use sticky sessions: always send User X to Server A           │
    │   Server A dies = lose all sessions. Hard to scale.                 │
    │                                                                     │
    │   ─────────────────────────────────────────────────────────────    │
    │                                                                     │
    │   STATELESS (Session in Redis):                                      │
    │                                                                     │
    │   Request 1 ──► Any Server ──► Redis (session) ──► Response           │
    │   Request 2 ──► Any Server ──► Redis (session) ──► Response          │
    │                                                                     │
    │   Any server can handle any request. Add servers = scale out.       │
    │   Redis dies = sessions lost (mitigate with Redis cluster)           │
    │                                                                     │
    └─────────────────────────────────────────────────────────────────────┘
```

### Stateless Services + Stateful Stores = Standard Pattern

The standard microservice pattern: **stateless application servers** front a **stateful store** (database, cache, queue). The servers scale horizontally. The store is the source of truth. Servers are interchangeable.

### JWT vs Session Cookies

| Approach | Where State Lives | Stateless? | Trade-off |
|----------|-------------------|------------|-----------|
| **Session cookie** | Server (or Redis keyed by session ID) | Server is stateless if session in Redis; otherwise stateful | Server must look up session. Easy to invalidate. |
| **JWT (JSON Web Token)** | In the token itself (signed, client sends it) | Yes—server validates signature, no lookup | Server doesn't store sessions. Hard to invalidate before expiry. |

**JWT**: Token contains payload (user_id, roles, expiry). Server verifies signature. No DB/Redis lookup. Truly stateless. But revoking a user requires either short expiry (more re-auth) or a blocklist (which is state).

**Session**: Server stores session in Redis. Cookie carries session ID. Server looks up session. Stateless servers, stateful store. Revocation = delete key from Redis.

### ASCII Diagram: Stateful vs Stateless Architecture

```
    STATEFUL (avoid for scale):

    ┌─────────┐     ┌─────────┐     ┌─────────┐
    │ Client  │────►│ Server A│     │ Server B│
    │         │     │(session │     │(no      │
    │         │     │ in mem) │     │ session)│
    └─────────┘     └─────────┘     └─────────┘
                          │
                    Sticky routing required
                    A dies = session lost


    STATELESS (preferred):

    ┌─────────┐     ┌─────────┐     ┌─────────┐
    │ Client  │────►│ Server A│     │ Server B│
    │         │     │         │     │         │
    │         │     └────┬────┘     └────┬────┘
    │         │          │               │
    │         │          └───────┬───────┘
    │         │                  │
    │         │                  ▼
    │         │           ┌─────────────┐
    │         │           │ Redis / DB   │
    │         │           │ (session,    │
    │         │           │  state)     │
    │         │           └─────────────┘
    │         │
    └─────────┘     Any server, any request.
                    Scale by adding servers.
```

### L5 vs L6: State Design

| Aspect | L5 Thinking | L6 Thinking |
|--------|-------------|-------------|
| **Sessions** | "We use in-memory sessions" | "Sessions are in Redis; our app servers are stateless; we scale horizontally" |
| **Scaling** | "We'll add more servers" | "Our servers are stateless; we add servers and they join the pool immediately" |
| **Failover** | "We have 2 servers" | "Any server can handle any request; no sticky sessions; clean failover" |

---

## Part 4: Idempotency

### Definition: Same Effect, Multiple Times

An operation is **idempotent** if performing it multiple times has the **same effect** as performing it once.

- **GET /users/123**: Same every time. Idempotent.
- **DELETE /users/123**: First time deletes. Second time, 404. Effect: user is gone. Idempotent.
- **PUT /users/123** with body: Replaces resource. Same body, same result. Idempotent.
- **POST /orders**: Each call creates a new order. Not idempotent.

### Why It Matters: Retries Create Duplicates

Networks fail. Clients time out. Servers crash. When a request fails, the client retries. If the operation is **not** idempotent, the retry can cause duplicates:

- **"Charge $100"** retried = user charged twice.
- **"Create order"** retried = two orders.
- **"Send email"** retried = user gets two emails.

If the operation **is** idempotent, the retry is safe. "Charge $100 with idempotency key X" — server checks: have I already processed X? If yes, return same result. If no, process and record X. Retry with same X = no double charge.

### Idempotency Keys

**Mechanism**: Client generates a unique key per logical operation (e.g., UUID). Sends it with the request. Server stores processed keys. If the same key arrives again, server returns the stored response without re-executing.

**Implementation details**:
- **Storage**: Processed keys must be stored somewhere—Redis, DB, or a dedicated store. Key: idempotency_key → (response, timestamp).
- **TTL**: You can't keep keys forever. 24 hours is common. After that, a retry with the same key might be treated as new (and could duplicate). For payments, 24h is usually enough—users don't retry after days.
- **Key format**: UUID v4 is standard. Ensure client doesn't reuse keys across different operations. "Create order" and "Create order line item" must have different keys.
- **Idempotency key header**: Many APIs use `Idempotency-Key: <uuid>` header. Stripe, Square, and others use this pattern.

```
    Request 1: POST /charges { amount: 100, idempotency_key: "abc-123" }
    → Server processes, stores result for "abc-123", returns 201

    Request 2 (retry): POST /charges { amount: 100, idempotency_key: "abc-123" }
    → Server finds "abc-123" already processed, returns same 201 (no new charge)
```

**Key scope**: One key per logical operation. "Create order" = one key. "Create order line item 1" = different key. Client must not reuse keys for different operations.

### Which Operations Should Be Idempotent?

| Operation | Idempotent? | Notes |
|-----------|-------------|-------|
| **GET** | Yes | Read-only |
| **PUT** | Yes | Replace; same body = same result |
| **DELETE** | Yes | Delete; second call = 404 |
| **PATCH** | Depends | If PATCH is "set X to Y" and Y is in request, can be idempotent |
| **POST** | No (by default) | Creates new resource each time. Use idempotency keys for payments, orders, etc. |

### Payment Example: Without vs With Idempotency

**Without**:
```
    Client: Charge $100 (request sent, network timeout before response)
    Client: Retry charge $100
    Server: Processes both. User charged $200. Bug.
```

**With idempotency key**:
```
    Client: Charge $100, idempotency_key=req-555
    Server: Processes, records req-555, returns success
    (Network timeout—client doesn't receive response)

    Client: Retry charge $100, idempotency_key=req-555
    Server: Sees req-555 already processed. Returns cached success. No second charge.
```

### Caching Strategy Decision Framework

```
    START: Do you need to cache?
           │
           ▼ YES
    ┌──────────────────────────────────────┐
    │  How fresh must data be?              │
    │  - Strong consistency required?       │
    │  - Eventual OK (seconds/minutes)?     │
    └──────────────────────────────────────┘
           │
           ├── Strong consistency ──► Write-through (write to cache + DB together)
           │                          Cache always has latest. Higher write load.
           │
           ├── Eventual OK, read-heavy ──► Cache-aside (lazy load)
           │                               Read: cache → miss → DB → populate cache.
           │                               Write: invalidate or update cache.
           │                               Simpler. Possible stampede on miss.
           │
           └── Very write-heavy, can tolerate loss ──► Write-back (write-behind)
                                                      Write to cache; async to DB.
                                                      Risk: cache fail = data loss.
```

| Strategy | Consistency | Write Load | When to Use | Real Example |
|----------|-------------|------------|-------------|--------------|
| **Cache-aside** | Eventual | Low (invalidate only) | Most web apps, product catalog | E-commerce product pages, user profiles |
| **Write-through** | Strong | High (every write hits cache + DB) | Session data, config that must be fresh | User session, feature flags |
| **Write-back** | Eventual, loss risk | Lowest | Analytics events, click tracking | Metrics, view counts |
| **Write-around** | Eventual | Low | Write-heavy, read miss OK | Log aggregation, audit trail |

**Impact on consistency**: Write-through guarantees cache and DB match. Cache-aside can serve stale until TTL or invalidation. Write-back can lose recent writes if cache fails. Choose based on domain: payments → strong. Product description → eventual.

### Idempotency in Practice: Implementation Patterns

**Database-level idempotency**: Use unique constraints. `INSERT ... ON CONFLICT DO NOTHING` or unique on (idempotency_key). DB rejects duplicate. Application checks affected rows; if 0, it's a retry—return cached response.

```sql
-- Unique constraint ensures duplicate key = no insert
CREATE UNIQUE INDEX idx_orders_idempotency ON orders(idempotency_key);
INSERT INTO orders (idempotency_key, user_id, amount, ...)
VALUES ('req-555', 123, 100, ...)
ON CONFLICT (idempotency_key) DO UPDATE SET updated_at = NOW()
RETURNING *;
-- First call: insert. Retry: update (no-op), return row. Idempotent.
```

**Application-level idempotency**: Store processed keys in Redis or a table. Before processing: `GET idempotency:req-555`. If exists, return stored response. If not, process, `SET idempotency:req-555 → response` with TTL (e.g., 24h).

```python
# Pseudocode
def process_payment(idempotency_key, amount):
    cached = redis.get(f"idempotency:{idempotency_key}")
    if cached:
        return json.loads(cached)  # Same response as first call
    
    result = charge_card(amount)
    redis.setex(f"idempotency:{idempotency_key}", 86400, json.dumps(result))
    return result
```

**Distributed idempotency (consensus)**: In a distributed system, two nodes might receive the same retry. Both check "have we processed req-555?" Need a shared store (Redis, DB) that both can read/write. Or use a distributed lock: first to acquire lock processes; second finds result already stored.

**Payment systems case study**: Stripe, Adyen, PayPal all require idempotency keys for charges, refunds, payouts. Without: network retry = double charge. With: client sends `Idempotency-Key: uuid`. Server stores (key → response) for 24h. Retry with same key = return cached response. No second charge. Industry standard for financial APIs.

### Staff-Level Insight: Design for Retries

**Every write API** that has financial, consistency, or user-visible side effects should be designed for idempotent retries. That means:
- Accept idempotency keys for non-GET operations
- Store processed keys (with TTL—you can't keep them forever)
- On duplicate key: return same response as original, don't re-execute

**L5 vs L6**: L5 builds the feature. L6 asks: "What happens when the client retries? Are we safe?"

---

## Part 5: Queues — The Buffer Between Producer and Consumer

### Queue = Decoupling Producer and Consumer

A **queue** sits between producers (who put messages) and consumers (who process them). The producer doesn't wait for the consumer. It enqueues and continues. The consumer processes at its own pace. If the producer is fast and the consumer is slow, the queue buffers. If the consumer is down, the queue holds messages until it's back.

### Why Queues?

| Benefit | Explanation |
|---------|-------------|
| **Decoupling** | Producer and consumer don't need to know about each other. Change one without the other. |
| **Async** | Producer doesn't block. Better throughput. |
| **Buffering** | Absorbs traffic spikes. Consumer doesn't get overwhelmed. |
| **Reliability** | Messages persist. Consumer can retry on failure. |
| **Load leveling** | Smooth out bursty traffic into steady processing. |

### Types of Queues

| Type | Behavior | Example |
|------|----------|---------|
| **Simple FIFO** | First in, first out | SQS FIFO, RabbitMQ queue |
| **Priority queue** | High-priority messages first | RabbitMQ priority queues |
| **Dead-letter queue (DLQ)** | Failed messages go here for inspection/retry | SQS DLQ, RabbitMQ DLX |
| **Log (Kafka)** | Append-only log; consumers read from offset. Not "pop" semantics | Kafka |

**Queue vs Log**: A queue typically removes a message when consumed. A log keeps messages; consumers track their offset. Kafka is a log. SQS is a queue. Both decouple producer and consumer, but semantics differ.

### Examples: SQS, RabbitMQ, Redis, Kafka

| System | Model | Best For |
|--------|-------|----------|
| **SQS** | Queue, at-least-once delivery | Simple async processing, AWS-native |
| **RabbitMQ** | Queue, flexible routing | Complex routing, acknowledgments |
| **Redis Lists** | Simple queue (LPUSH, BRPOP) | Low latency, simple use cases |
| **Kafka** | Log, consumer groups | High throughput, event sourcing, replay |

### Use Cases

| Use Case | Why Queue |
|----------|-----------|
| **Email sending** | Don't block user. Worker sends async. |
| **Order processing** | Decouple checkout from inventory/payment. |
| **Image/video processing** | Heavy work. Queue job, process in background. |
| **Event distribution** | One event, many consumers. Fan-out via queue. |
| **Rate limiting** | Queue smooths request rate to downstream. |

### ASCII Diagram: Producer → Queue → Consumers

```
    ┌─────────────────────────────────────────────────────────────────────┐
    │                    QUEUE PATTERN                                     │
    │                                                                     │
    │   ┌──────────┐    ┌──────────┐    ┌──────────┐                     │
    │   │Producer 1│    │Producer 2│    │Producer 3│  ...                 │
    │   └────┬─────┘    └────┬─────┘    └────┬─────┘                     │
    │        │                │                │                          │
    │        └────────────────┼────────────────┘                          │
    │                         │                                           │
    │                         ▼                                           │
    │                  ┌─────────────┐                                    │
    │                  │    QUEUE    │  (SQS, RabbitMQ, Kafka)            │
    │                  │  (FIFO or   │                                    │
    │                  │   Priority) │                                    │
    │                  └──────┬──────┘                                    │
    │                         │                                           │
    │        ┌────────────────┼────────────────┐                          │
    │        │                │                │                          │
    │        ▼                ▼                ▼                          │
    │   ┌─────────┐     ┌─────────┐     ┌─────────┐                       │
    │   │Worker 1 │     │Worker 2 │     │Worker 3 │  ...                   │
    │   └─────────┘     └─────────┘     └─────────┘                       │
    │                                                                     │
    │   Producers enqueue and continue. Workers process at their pace.   │
    │   Queue absorbs spikes. Workers scale independently.                │
    │                                                                     │
    └─────────────────────────────────────────────────────────────────────┘
```

### L5 vs L6: Queue Design

| Aspect | L5 Thinking | L6 Thinking |
|--------|-------------|-------------|
| **Choice** | "We use SQS" | "SQS for simple async; Kafka for event streaming and replay" |
| **Failure** | "Worker retries" | "We have DLQ, retry with backoff, alert on DLQ depth" |
| **Scaling** | "We add workers" | "We scale workers based on queue depth; each partition has one consumer" |

### Queue Delivery Semantics: At-Most-Once, At-Least-Once, Exactly-Once

| Semantic | Guarantee | Trade-off |
|-----------|------------|-----------|
| **At-most-once** | Message may be lost, never duplicated | Fast, simple; use when loss is acceptable |
| **At-least-once** | Message delivered at least once; may duplicate | Safe for critical work; consumers must be idempotent |
| **Exactly-once** | Message delivered precisely once | Hard to achieve; often "effectively once" via idempotency |

Most systems aim for at-least-once with idempotent consumers. True exactly-once requires distributed transactions or log-based deduplication—complex. Staff Engineers choose the right semantic per use case: at-most-once for metrics, at-least-once for payments.

### Kafka vs SQS: When to Use Which

| Aspect | SQS | Kafka |
|--------|-----|-------|
| **Model** | Queue (message consumed, removed) | Log (retained, consumers track offset) |
| **Replay** | No | Yes—re-read from offset |
| **Ordering** | FIFO queues only, per partition | Per partition |
| **Throughput** | 3K/sec default, 300K with batching | Millions/sec |
| **Use case** | Simple async, task queues | Event streaming, high throughput, replay |

Choose SQS when you need simple, managed, fire-and-forget. Choose Kafka when you need high throughput, replay, or event sourcing.

### Queue Patterns: Fan-Out, Competing Consumers, Priority, DLQ, Delay

**Fan-out pattern**: One message, many consumers. Publish to a topic; multiple subscriber queues or consumer groups each get a copy. Use for: event distribution (order placed → inventory, notifications, analytics all receive it).

```
    ┌─────────┐     ┌──────────┐     ┌─────────────┐
    │Producer │────►│  Topic   │────►│ Consumer A  │
    │         │     │ (fan-out)│     │ (inventory) │
    │         │     │          │────►│ Consumer B  │
    │         │     │          │     │ (notify)    │
    │         │     │          │────►│ Consumer C  │
    └─────────┘     └──────────┘     │ (analytics) │
                                     └─────────────┘
```

**Competing consumers**: Multiple workers consume from the same queue. Each message goes to one consumer. Scales processing horizontally. Use for: task queues, job processing.

```
    ┌─────────┐     ┌──────────┐
    │Producer │────►│  Queue   │──┬──► Worker 1
    │         │     │          │  ├──► Worker 2
    │         │     │          │  └──► Worker 3
    └─────────┘     └──────────┘
    (Each message delivered to exactly one worker)
```

**Priority queues**: Messages have priority. High-priority messages processed first. Use for: urgent vs normal (VIP user actions, critical alerts).

```
    ┌─────────┐     ┌─────────────────────┐     ┌─────────┐
    │Producer │────►│  Priority Queue      │────►│ Worker  │
    │ (high)  │     │  [P1][P1][P2][P2]   │     │         │
    │ (low)   │     │  High dequeued first │     │         │
    └─────────┘     └─────────────────────┘     └─────────┘
```

**Dead-letter queue (DLQ)**: Messages that fail after N retries go to a separate queue. For inspection, manual retry, or alerting. Use for: failed payments, corrupted data, poison messages.

```
    ┌─────────┐     ┌──────────┐     ┌─────────┐
    │Producer │────►│  Queue   │────►│ Worker  │
    │         │     │          │     │ (fails) │
    │         │     │          │     └────┬────┘
    │         │     │          │          │ retries exhausted
    │         │     │          │          ▼
    │         │     │          │     ┌─────────┐
    │         │     │          │     │   DLQ   │  (inspect, retry)
    │         │     │          │     └─────────┘
    └─────────┘     └──────────┘
```

**Delay queues**: Message visible only after a delay. Use for: scheduled jobs, retry with backoff, "send email in 1 hour."

```
    ┌─────────┐     ┌──────────────┐     ┌─────────┐
    │Producer │────►│ Delay Queue  │     │ Worker  │
    │         │     │ (visibility  │────►│         │
    │         │     │  timeout=5m) │     │         │
    └─────────┘     └──────────────┘     └─────────┘
    Message in queue 5 min before worker can process it.
```

| Pattern | When to Use | Example |
|---------|-------------|---------|
| **Fan-out** | One event, many independent consumers | OrderPlaced → inventory, email, analytics |
| **Competing consumers** | Scale processing, any worker can handle | Image resize, email send, report generation |
| **Priority** | Urgent messages first | VIP support, critical alerts |
| **DLQ** | Handle failures, avoid poison messages | Failed payments, bad data |
| **Delay** | Schedule for later | Reminder in 1h, retry with backoff |

**Queue pattern selection guide**: Fan-out when one event triggers multiple independent actions. Competing consumers when you need to scale processing and any worker can handle any message. Priority when some messages are more urgent. DLQ always—failed messages need a place to go. Delay when you need scheduled or deferred processing.

---

## Part 6: Synchronous vs Asynchronous

### Synchronous: Caller Waits

**Synchronous** = the caller sends a request and **blocks** until the response arrives. "I'll wait here until you're done."

**Examples**: HTTP request-response. Function call. REST API. Browser loading a page.

```
    Client ──► Request ──► Server ──► Process ──► Response ──► Client
              (blocks)                    (blocks)         (continues)
```

### Asynchronous: Caller Doesn't Wait

**Asynchronous** = the caller sends a request and **continues**. It gets the result later—via callback, polling, webhook, or event. "Here's my order, call me when it's ready."

**Examples**: Message queue. Webhook. Email sending. Event-driven architecture. Server-Sent Events.

```
    Client ──► Request ──► Server/Queue ──► (Client continues)
                                    │
                                    ▼
                            Worker processes
                                    │
                                    ▼
                            Callback / Webhook / Event
```

### Sync in System Design

| Scenario | Pattern |
|----------|---------|
| **User needs immediate response** | Sync: login, read data, checkout |
| **Service A calls Service B** | Sync: A sends HTTP/gRPC, waits for B's response |
| **API gateway → backend** | Sync: gateway forwards, waits for backend |

**When sync**: When the user or caller needs the result to proceed. You can't show "Order confirmed" without the payment result. Sync is simpler: one request, one response, easy to reason about.

### Async in System Design

| Scenario | Pattern |
|----------|---------|
| **Work can be deferred** | Async: send email, generate report, process video |
| **High volume, batch processing** | Async: ingest events, process in background |
| **Decoupling** | Async: Service A publishes event; B, C, D subscribe |

**When async**: When the user doesn't need the result immediately, or when you want to decouple. "Your video is processing—we'll email when done." Async improves throughput and resilience but adds complexity.

### Async Challenges

| Challenge | Why |
|-----------|-----|
| **Eventual consistency** | Result isn't available immediately. User might see stale state. |
| **Error handling** | Sync: return error to caller. Async: where does the error go? DLQ? Retry? Notify? |
| **Debugging** | Sync: one call stack. Async: trace across services, queues, workers. |
| **Ordering** | Sync: natural order. Async: messages can arrive out of order. Need sequencing. |

### Staff-Level: Choosing Sync vs Async

Every interaction is a choice. Staff Engineers ask:

- **Does the caller need the result now?** If yes, sync (or sync facade over async).
- **Can we tolerate eventual consistency?** If yes, async is an option.
- **What's the failure mode?** Sync: caller gets error. Async: need retry, DLQ, monitoring.
- **What's the scale?** Sync under heavy load can back up. Async absorbs spikes.

**Rule of thumb**: Default to sync for user-facing, result-dependent flows. Use async for side effects, notifications, and heavy processing. Don't async-ify everything—it adds operational burden.

### ASCII Diagram: Sync vs Async

```
    SYNCHRONOUS (A waits for B):

    ┌─────────┐                    ┌─────────┐
    │   A     │ ─── Request ──────► │   B     │
    │ (block) │                    │ process │
    │         │ ◄── Response ──────│         │
    │(continue)│                    └─────────┘
    └─────────┘

    Latency = round-trip. A is blocked. Simple. Easy to debug.


    ASYNCHRONOUS (A doesn't wait):

    ┌─────────┐       ┌─────────┐       ┌─────────┐
    │   A     │ ─────► │  Queue  │ ─────► │   B     │
    │(continues)       │         │        │ process │
    └─────────┘       └─────────┘       └────┬────┘
                                               │
                                               ▼
    ┌─────────┐       ┌─────────┐       Callback / Event
    │   A     │ ◄───── │ Webhook  │ ◄─────┘
    │(later)  │        │ or Poll  │
    └─────────┘       └─────────┘

    A continues immediately. B processes when it can. Result arrives later.
```

### L5 vs L6: Sync vs Async

| Aspect | L5 Thinking | L6 Thinking |
|--------|-------------|-------------|
| **Choice** | "We'll use a queue" | "Sync for checkout—user needs confirmation. Async for email and analytics" |
| **Consistency** | "It's eventually consistent" | "We use async for side effects; core flow is sync so user sees immediate result" |
| **Failure** | "The worker will retry" | "We have retries, DLQ, and alerts. User-facing path stays sync so we can return errors" |

**Staff-Level Insight**: Choosing sync vs async per interaction is a KEY architectural decision. It affects latency, consistency, complexity, and operability. Make the choice explicitly, per use case, and document the trade-off.

### Hybrid Patterns: Sync Facade Over Async

Sometimes you want async internally but sync externally. Example: "Create order" API. User expects immediate response. Internally: API writes to queue, returns "processing." Worker processes, updates DB. But user got a quick response with an order ID. For "get order status," they poll or use webhooks. The *creation* is async (queue), but the *API response* is sync (immediate 202 Accepted + order ID). This is a **sync facade**: the caller gets a fast sync response; the heavy work happens async. Staff Engineers use this pattern when user experience requires responsiveness but the work is slow or variable.

### Event-Driven Architecture: Async at Scale

When many services need to react to the same event, you don't call them all synchronously—that would create a web of dependencies and amplify latency. Instead: **publish an event**. Interested services subscribe. They process asynchronously. Order service publishes "OrderCreated." Inventory service subscribes and reserves stock. Notification service subscribes and sends email. Analytics subscribes and updates dashboards. No single orchestrator; each service is independent. Trade-off: eventual consistency, harder tracing, and the need for idempotent consumers (same event might be delivered more than once).

### Sync vs Async Decision Matrix

| Component / Use Case | Sync or Async? | Rationale | Real Example |
|---------------------|----------------|-----------|--------------|
| **User login** | Sync | User must see success/fail immediately | Auth API returns token or 401 |
| **Product page load** | Sync | User waits for page; can't proceed without data | REST API; DB/cache read |
| **Payment charge** | Sync (or sync facade) | User needs confirmation; retry is dangerous | Stripe API: wait for charge result |
| **Order confirmation email** | Async | User doesn't wait; send in background | Queue → worker sends email |
| **Analytics event** | Async | Fire-and-forget; no user blocking | Kafka/queue; batch to warehouse |
| **Inventory reservation** | Sync | Checkout needs to know if in stock | Sync call to inventory service |
| **Recommendation engine** | Async or sync with timeout | Can show "loading" or cached; not critical path | Pre-compute; cache; async refresh |
| **Search indexing** | Async | Index updates don't block writes | CDC → queue → Elasticsearch |
| **Webhook to partner** | Async | Partner may be slow; don't block our flow | Queue → worker POSTs to partner URL |
| **Multi-service orchestration** | Mixed | Critical path sync; side effects async | Checkout: sync payment; async email, analytics |

**Decision framework**:
1. Does the caller need the result to proceed? → Sync
2. Can we tolerate eventual consistency? → Async is an option
3. Is it a side effect (logging, notification, analytics)? → Async
4. Does the operation have high variance (slow downstream)? → Async to avoid blocking
5. Is it financial or correctness-critical? → Prefer sync (or sync with async confirmation)

**5+ real examples**:
- **Stripe checkout**: Sync. Charge API returns success/decline. User sees result. Webhook for async notification to merchant.
- **Netflix play**: Sync for license/DRM; async for playback analytics and recommendations.
- **Uber match**: Sync for "finding driver" (user waits); async for driver location updates (WebSocket push).
- **Slack message**: Sync for send (user sees "sent"); async for delivery receipts, read receipts, push to other clients.
- **AWS S3 upload**: Sync for small uploads (PUT returns on complete); async/multipart for large files (client manages chunks).

### Request-Response vs Fire-and-Forget vs Publish-Subscribe

| Pattern | Caller Waits? | Use Case |
|---------|---------------|----------|
| **Request-response** | Yes | User needs result (login, read, checkout) |
| **Fire-and-forget** | No, doesn't care about result | Logging, analytics, non-critical side effects |
| **Publish-subscribe** | No, many consumers | Event distribution, fan-out |

Understanding these three clarifies when to use sync (request-response), async with callback (fire-and-forget with notification), or event bus (pub-sub).

---

# Example in Depth: How Idempotency and Queues Fit in a Checkout Flow

**Scenario**: User clicks "Place order." Payment, inventory, and shipping must stay consistent; no double charge, no oversell.

**Sync path (user waits)**: (1) **Idempotency**: Request includes `Idempotency-Key: order_abc123`. Server: lookup key → if exists, return stored result (same order ID); if not, create order, store key → result, return. Retries (network, LB, client) don't create duplicate orders. (2) **State**: Order and payment state in **DB**; idempotency key → result in **cache or DB** (e.g. 24h TTL). (3) **Hash**: If orders are sharded by `user_id`, the same user's orders hit same shard; idempotency key can be scoped per user or global.

**Async path (after order accepted)**: (4) **Queue**: "Send confirmation email," "Update analytics," "Reserve shipping slot" → **queue** (e.g. Kafka, SQS). Workers consume; at-least-once delivery. (5) **Idempotency again**: Consumers must be **idempotent** (e.g. "send email" keyed by order_id + action so duplicate messages don't send twice). (6) **Cache**: Don't cache order creation result for long (user needs fresh status); cache product catalog, inventory counts (with invalidation on reserve).

**What we didn't do**: We didn't put payment on a queue without sync confirmation—user must see "paid" or "declined" before leaving. We didn't skip idempotency—one retry could double-charge. Staff-level: **sync for critical user-facing outcome**; **queue for side effects**; **idempotency on every write and every consumer**.

## Breadth: Building Block Combinations and Failure Scenarios

| Combination | Use case | Watch out for |
|-------------|----------|----------------|
| **Cache + DB** | Read-through cache for hot data | Stampede on miss; invalidation on write; cache-aside vs write-through choice |
| **Queue + Idempotency** | Async workers with at-least-once | Duplicate messages; consumer must dedupe by key or idempotent action |
| **Hash + State** | Sharded storage by user_id | Hot partition if one key dominates; rebalance when adding nodes |
| **Sync + Timeout** | Call downstream with deadline | Timeout too short → false failures; too long → cascading delay; circuit breaker when downstream is down |
| **State + Failover** | Session in Redis; Redis failover | Session loss or duplicate; use sticky sessions or short TTL and re-auth |

**Failure scenarios**: **Cache down**: Fall through to DB; ensure DB can take full load or degrade (e.g. return stale from backup cache). **Queue backlog**: Consumers can't keep up; add workers or partition; alert on lag; DLQ for poison messages. **Idempotency key collision**: Two different requests same key → second gets first's result. Key must be unique per logical operation (e.g. client-generated UUID per "place order" click). **Hash rebalance**: Adding node moves keys; during rebalance some reads may miss—use consistent hashing and gradual rebalance, or dual-read during migration.

---

## Summary: Building Blocks as Design Decisions

This chapter covered six building blocks that appear in every system:

1. **Hash functions** — Distribution, sharding, consistent hashing. Choose the right tool for distribution vs security.
2. **Caching** — Speed and load reduction. TTL, invalidation, hit rate. Design for consistency and failure.
3. **State vs stateless** — Stateless servers scale. Put state in external stores. Standard pattern for microservices.
4. **Idempotency** — Safe retries. Idempotency keys for every important write. Non-negotiable for payments and orders.
5. **Queues** — Decoupling and buffering. Use when work can be deferred or when you need to absorb spikes.
6. **Sync vs async** — Per-interaction choice. Sync when caller needs result now. Async when you can defer and absorb load.

**Staff-Level Insight**: These aren't implementation details. They're architectural primitives. When you design a system, you're composing these blocks—and the quality of your composition depends on understanding their trade-offs. Master the blocks; then master the decisions that combine them into systems that scale.

---

## Composing Building Blocks: A Design Lens

When you approach a new system design, ask:

1. **Hash** — How is data distributed? Sharding key? Consistent hashing? What happens on resize?
2. **Cache** — What's cached? Where? TTL? Invalidation strategy? What's the hit rate?
3. **State** — Are services stateless? Where does state live? Sessions, config, user data?
4. **Idempotency** — Which writes need retry safety? Do we use idempotency keys?
5. **Queue** — What's async? What's the queue? Delivery semantics? DLQ?
6. **Sync vs Async** — Which interactions are sync (user waits) vs async (fire-and-forget)?

This lens ensures you don't miss a critical block. A design that's stateless but forgets idempotency will double-charge on retries. A design that caches aggressively but has no invalidation strategy will serve stale data. A design that uses async everywhere will be hard to debug and reason about.

**Example: Applying the lens to a "Design a payment system" prompt**

- **Hash**: Not primary (payments are not sharded by hash in the same way as caches). But we might partition payment records by user_id or merchant_id for scaling.
- **Cache**: Cache merchant config, currency rates. Don't cache the actual payment result for the payer (they need immediate confirmation)—but we might cache for idempotency key lookup.
- **State**: Stateless API servers. Payment state in DB. Idempotency key store (Redis or DB).
- **Idempotency**: Critical. Every charge, refund, transfer must accept idempotency keys. Non-negotiable.
- **Queue**: Payment processing might be async (3DS, bank approval). Queue the "confirm payment" step; return "processing" to user. Webhook or poll for result.
- **Sync vs Async**: User-initiated charge: sync response with "success" or "declined" (or redirect for 3DS). Internal reconciliation: async. Webhook to merchant: async (we retry).

Running this checklist in 30 seconds ensures you don't miss idempotency (disaster) or over-complicate with async where sync is needed. A design that caches aggressively but has no invalidation strategy will serve stale data. Staff Engineers run this checklist consciously.

---

## Failure Mode Cheat Sheet

| Block | Failure Mode | Mitigation |
|-------|--------------|------------|
| **Hash** | Poor distribution, hot partition | Virtual nodes, rebalance |
| **Cache** | Down, stampede, stale | Fall-through to DB, locking, TTL |
| **State** | Lost on server death | External store (Redis, DB) |
| **Idempotency** | Missing → duplicates | Idempotency keys on all writes |
| **Queue** | Message lost, duplicate, DLQ overflow | Delivery semantics, retry, alert on DLQ |
| **Async** | Result never arrives, ordering | Timeouts, callbacks, sequence numbers |

Every block has failure modes. Design for them.

---

## L5 vs L6: Building Block Mastery

| Block | L5 | L6 |
|-------|----|----|
| **Hash** | "We hash the key" | "We use consistent hashing; vnodes for balance; adding a node moves ~1/N keys" |
| **Cache** | "We cache frequently accessed data" | "We cache with 5-min TTL; invalidate on write; stampede protection via probabilistic refresh" |
| **State** | "Our servers are stateless" | "Stateless app servers; session in Redis with 24h TTL; we scale by adding servers" |
| **Idempotency** | "We retry on failure" | "All write APIs accept idempotency keys; we dedupe for 24h; payments use it" |
| **Queue** | "We use a queue for async" | "Kafka for events, at-least-once; idempotent consumers; DLQ with 7-day retention" |
| **Sync/Async** | "We use async for slow stuff" | "Checkout is sync—user needs confirmation. Email and analytics are async—we use a queue" |

The L6 answer includes *how* and *why* and *what happens when it fails*. That's the bar.
