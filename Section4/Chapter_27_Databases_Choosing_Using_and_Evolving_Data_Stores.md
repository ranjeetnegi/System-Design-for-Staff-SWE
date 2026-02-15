# Chapter 27: Databases — Choosing, Using, and Evolving Data Stores

---

# Introduction

Every system design interview involves a database decision. And nearly every candidate makes the same mistake: they reach for a familiar database first and justify it afterward.

Staff Engineers do the opposite. They understand the problem deeply—data shape, access patterns, consistency requirements, failure modes—and let those constraints guide them to the right data store. Sometimes that's PostgreSQL. Sometimes it's Bigtable. Sometimes it's a combination of three different systems with careful synchronization between them.

This section teaches the database decision framework that Staff Engineers apply instinctively. We'll move beyond the shallow "SQL vs NoSQL" debate and into the real questions that matter at scale. We'll examine when relational databases remain the correct choice (more often than you'd think), when document stores make sense (less often than vendors claim), and when you need the complexity of distributed SQL systems.

More importantly, we'll explore how database choices evolve. The database that's right for your system at 10,000 users might strangle you at 10 million. Staff Engineers don't just pick databases—they plan migration paths, anticipate scaling boundaries, and design systems that can evolve without catastrophic rewrites.

By the end of this section, you'll have a principled framework for database selection, the vocabulary to discuss trade-offs in interviews, and the judgment to reject fashionable choices that don't fit your context.

---

## Quick Visual: The Database Decision at a Glance

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DATABASE SELECTION: WHAT ACTUALLY MATTERS                │
│                                                                             │
│   WRONG First Question: "SQL or NoSQL?"                                     │
│   RIGHT First Question: "What are my access patterns?"                      │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Step 1: UNDERSTAND YOUR DATA                                       │   │
│   │  • What is the data shape? (Structured, Semi-structured, Blobs?)    │   │
│   │  • How does data relate to other data?                              │   │
│   │  • How frequently does the schema change?                           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Step 2: UNDERSTAND YOUR ACCESS                                     │   │
│   │  • Read vs Write ratio?                                             │   │
│   │  • Point lookups vs Range scans vs Aggregations?                    │   │
│   │  • Hot keys or uniform distribution?                                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Step 3: UNDERSTAND YOUR CONSTRAINTS                                │   │
│   │  • Consistency requirements?                                        │   │
│   │  • Latency requirements? (p99, not average)                         │   │
│   │  • Scale requirements? (Now and in 3 years)                         │   │
│   │  • Team expertise?                                                  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   THEN choose technology. Not before.                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Simple Example: L5 vs L6 Database Decisions

| Scenario | L5 Approach | L6 Approach |
|----------|-------------|-------------|
| **User profile service** | "MongoDB—it's flexible and documents fit user data" | "PostgreSQL. Profiles have stable schema, need strong consistency for settings, and we query by multiple fields. Document store flexibility isn't needed and costs us in query capability." |
| **Rate limiter** | "Redis—it's fast for counters" | "Redis for hot path, but we need persistence semantics. What happens on Redis restart? Use Redis with AOF, or accept counter reset with graceful degradation." |
| **Activity feed** | "Cassandra—it's write-optimized" | "Cassandra for storage, but read patterns matter. Fan-out on write or fan-out on read? That choice drives our Cassandra schema design more than Cassandra drives the choice." |
| **Shopping cart** | "DynamoDB—it's serverless and scales" | "What's the access pattern? Cart by user_id is simple. But cart abandonment analytics needs different access. Two tables, or one table with GSI? DynamoDB GSI costs can explode." |
| **Search functionality** | "Elasticsearch for everything" | "Elasticsearch for search. But what's the source of truth? Never let ES be the primary store. Design the sync pipeline before the search index." |

**Key Difference:** L6 engineers think about access patterns, failure modes, and operational cost before reaching for technology names.

---

# Part 1: Database Decision Framework (Staff-Level)

## What Problems Databases Actually Solve

Before comparing databases, understand what they do. At their core, databases solve four problems:

**1. Persistence**: Data survives process restarts, machine failures, and power outages.

**2. Concurrent Access**: Multiple clients can read and write simultaneously without corrupting data.

**3. Efficient Retrieval**: Data can be found without scanning everything (indexes, partitioning, caching).

**4. Data Integrity**: Constraints ensure data remains valid (types, relationships, business rules).

Different databases solve these problems with different trade-offs:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    HOW DATABASES TRADE OFF CORE PROBLEMS                    │
│                                                                             │
│                    Persistence   Concurrency   Retrieval   Integrity        │
│                    ──────────────────────────────────────────────────       │
│   PostgreSQL       Excellent     Excellent     Excellent   Excellent        │
│   (Single node)    (WAL)         (MVCC)        (B-trees)   (Constraints)    │
│                                                                             │
│   Redis            Configurable  Single-thread Very Fast   None             │
│                    (RDB/AOF)     (no locks!)   (Hash O(1)) (App layer)      │
│                                                                             │
│   Cassandra        Excellent     Excellent     Good*       Minimal          │
│                    (Replicated)  (No ACID)     (*by key)   (App layer)      │
│                                                                             │
│   DynamoDB         Excellent     Good          Good*       Minimal          │
│                    (Managed)     (Optimistic)  (*by key)   (App layer)      │
│                                                                             │
│   MongoDB          Excellent     Good          Flexible    Optional         │
│                    (Replica set) (Doc-level)   (Indexes)   (Validation)     │
│                                                                             │
│   * = Retrieval efficiency depends heavily on access pattern matching       │
│       partition/sort key design. Cross-partition queries are expensive.     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Staff Insight**: When someone says "we need a database," ask: which of these four problems is most critical? A rate limiter cares most about retrieval speed and can compromise on durability. A payment system needs all four at full strength.

---

## Why "SQL vs NoSQL" Is the Wrong First Question

The "SQL vs NoSQL" framing obscures more than it reveals. Here's why:

**1. It conflates multiple orthogonal decisions**

"NoSQL" includes:
- Key-value stores (Redis, Memcached)
- Document stores (MongoDB, CouchDB)  
- Wide-column stores (Cassandra, HBase, Bigtable)
- Graph databases (Neo4j, Neptune)

These have almost nothing in common except "not relational." Choosing between MongoDB and Cassandra is as significant as choosing between MongoDB and PostgreSQL.

**2. It implies a false dichotomy**

Most production systems use multiple databases. A typical Google-scale system might have:
- PostgreSQL for user accounts (relational, transactional)
- Redis for session data (fast, ephemeral)
- Bigtable for event logs (wide-column, append-heavy)
- Elasticsearch for search (inverted indexes)

The question isn't "SQL or NoSQL"—it's "which database for which data?"

**3. It overweights schema flexibility**

NoSQL advocates often emphasize "schema-less" flexibility. But:
- Your application has a schema whether the database enforces it or not
- Schema-on-read pushes complexity to every reader
- Schema changes in production are hard regardless of database
- "Flexible schema" often means "inconsistent data"

**4. It underweights operational maturity**

PostgreSQL has 25+ years of production hardening. It has solved problems you don't know you have yet. Newer databases often rediscover these problems painfully.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    THE REAL QUESTIONS (Not SQL vs NoSQL)                    │
│                                                                             │
│   1. Do I need ACID transactions across multiple records?                   │
│      YES → Relational or NewSQL                                             │
│      NO  → Wider options (but are you sure?)                                │
│                                                                             │
│   2. Do I need to query data by multiple attributes?                        │
│      YES → Relational or Document with indexes                              │
│      NO  → Key-value or Wide-column might suffice                           │
│                                                                             │
│   3. What's my read:write ratio?                                            │
│      READ-HEAVY  → Optimize for indexes, consider caching                   │
│      WRITE-HEAVY → Optimize for append, consider LSM trees                  │
│                                                                             │
│   4. How will this scale?                                                   │
│      VERTICALLY  → Relational can go surprisingly far                       │
│      HORIZONTALLY → Need partition strategy from day one                    │
│                                                                             │
│   5. What's my team's expertise?                                            │
│      POSTGRES EXPERTS → PostgreSQL can do more than you think               │
│      MIXED/NEW TEAM   → Managed services reduce operational burden          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Data Shape, Access Patterns, and Change Rate

### Data Shape

**Structured data** has a fixed schema known at design time:
- User accounts: id, email, name, created_at
- Orders: id, user_id, items[], total, status
- Products: id, name, price, category_id

Best fit: Relational databases. They enforce structure, enable efficient joins, and catch errors early.

**Semi-structured data** has variable attributes:
- Product catalogs where different categories have different attributes
- User preferences that evolve over time
- API response caching with varying schemas

Best fit: Document stores, or PostgreSQL's JSONB column for hybrid approach.

**Unstructured data** is opaque blobs:
- Images, videos, documents
- Serialized application objects

Best fit: Object storage (S3, GCS) with metadata in a database.

**Time-series data** is append-heavy with time-based access:
- Metrics, logs, events
- Sensor readings, financial ticks

Best fit: Time-series databases (InfluxDB, TimescaleDB) or wide-column stores (Bigtable).

### Access Patterns

This is where most database decisions should start:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ACCESS PATTERN → DATABASE GUIDANCE                       │
│                                                                             │
│   Pattern                        Best Fit              Avoid                │
│   ───────────────────────────────────────────────────────────────────       │
│   Point lookup by primary key    Any                   N/A                  │
│                                                                             │
│   Point lookup by secondary key  Relational, Doc       Wide-column (costly) │
│                                                                             │
│   Range scan by sort key         Wide-column, Rel      Key-value            │
│                                                                             │
│   Complex joins across tables    Relational            All NoSQL            │
│                                                                             │
│   Aggregation (COUNT, SUM, AVG)  Relational, OLAP      Key-value, Doc       │
│                                                                             │
│   Full-text search               Search engines        Relational           │
│                                                                             │
│   Graph traversal (friends of)   Graph DB              Relational (slow)    │
│                                                                             │
│   High-volume writes             Wide-column, TS       Relational (limits)  │
│                                                                             │
│   Random writes to large records Document              Wide-column          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Staff Insight**: Access patterns change. Design for known patterns today, but leave room for evolution. The most dangerous patterns are those that seem simple but become expensive at scale—like "query all items for a user" when users can have millions of items.

### Read/Write Flow Through the System

Understanding how data flows through your system is critical for identifying bottlenecks and failure points. Here's how Staff Engineers visualize read/write flows:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    READ FLOW: User Profile Service                          │
│                                                                             │
│   Request: GET /api/users/12345                                             │
│                                                                             │
│   ┌─────────────┐                                                           │
│   │   Client    │                                                           │
│   └──────┬──────┘                                                           │
│          │                                                                  │
│          │ HTTP Request                                                     │
│          ▼                                                                  │
│   ┌─────────────────┐                                                       │
│   │  Load Balancer  │                                                       │
│   └────────┬────────┘                                                       │
│            │                                                                │
│            │ Route to healthy instance                                      │
│            ▼                                                                │
│   ┌─────────────────┐                                                       │
│   │  API Service    │                                                       │
│   │  (Instance 1)   │                                                       │
│   └────────┬────────┘                                                       │
│            │                                                                │
│            │ 1. Check cache first                                           │
│            ▼                                                                │
│   ┌─────────────────┐                                                       │
│   │  Redis Cache    │  Cache Hit? ──YES──→ Return cached data               │
│   │  (Session Store)│                                                       │
│   └────────┬────────┘                                                       │
│            │                                                                │
│            │ Cache Miss                                                     │
│            ▼                                                                │
│   ┌─────────────────┐                                                       │
│   │  Connection Pool│  Get connection (wait if pool exhausted)              │
│   │  (PgBouncer)    │                                                       │
│   └────────┬────────┘                                                       │
│            │                                                                │
│            │ Route to read replica (not primary)                            │
│            ▼                                                                │
│   ┌─────────────────┐                                                       │
│   │  PostgreSQL     │  Execute: SELECT * FROM users WHERE id = 12345        │
│   │  Read Replica   │                                                       │
│   └────────┬────────┘                                                       │
│            │                                                                │
│            │ Return user data                                               │
│            ▼                                                                │
│   ┌─────────────────┐                                                       │
│   │  API Service    │  Serialize response, set cache TTL                    │
│   └────────┬────────┘                                                       │
│            │                                                                │
│            │ Write to cache (async, don't block response)                   │
│            ▼                                                                │
│   ┌─────────────────┐                                                       │
│   │  Redis Cache    │  SET user:12345 <data> EX 3600                        │
│   └─────────────────┘                                                       │
│                                                                             │
│   Response: HTTP 200 OK {user data}                                         │
│                                                                             │
│   Failure Points (L6 Thinking):                                             │
│   • Redis down: Cache miss → hit database (acceptable degradation)          │
│   • Connection pool exhausted: Request fails (need circuit breaker)         │
│   • Read replica lag: Stale data (acceptable for reads)                     │
│   • Database timeout: Return error or cached data (graceful degradation)    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                    WRITE FLOW: User Profile Update                          │
│                                                                             │
│   Request: PUT /api/users/12345 {email: "new@example.com"}                  │
│                                                                             │
│   ┌─────────────┐                                                           │
│   │   Client    │                                                           │
│   └──────┬──────┘                                                           │
│          │                                                                  │
│          │ HTTP Request                                                     │
│          ▼                                                                  │
│   ┌─────────────────┐                                                       │
│   │  Load Balancer  │                                                       │
│   └────────┬────────┘                                                       │
│            │                                                                │
│            │ Route to instance                                              │
│            ▼                                                                │
│   ┌─────────────────┐                                                       │
│   │  API Service    │  1. Validate input                                    │
│   │  (Instance 1)   │  2. Check authorization                               │
│   └────────┬────────┘                                                       │
│            │                                                                │
│            │ Begin transaction                                              │
│            ▼                                                                │
│   ┌─────────────────┐                                                       │
│   │  Connection Pool│  Get connection to PRIMARY (writes go to primary)     │
│   │  (PgBouncer)    │                                                       │
│   └────────┬────────┘                                                       │
│            │                                                                │
│            │ Transaction: BEGIN                                             │
│            ▼                                                                │
│   ┌─────────────────┐                                                       │
│   │  PostgreSQL     │  UPDATE users SET email = 'new@example.com'           │
│   │  Primary        │       WHERE id = 12345                                │
│   └────────┬────────┘                                                       │
│            │                                                                │
│            │ Commit transaction                                             │
│            │ (WAL written, data persisted)                                  │
│            ▼                                                                │
│   ┌─────────────────┐                                                       │
│   │  PostgreSQL     │  Transaction committed                                │
│   │  Primary        │                                                       │
│   └────────┬────────┘                                                       │
│            │                                                                │
│            │ Async: Invalidate cache                                        │
│            ▼                                                                │
│   ┌─────────────────┐                                                       │
│   │  Redis Cache    │  DEL user:12345 (remove stale data)                   │
│   └─────────────────┘                                                       │
│            │                                                                │
│            │ Async: Stream to replicas                                      │
│            ▼                                                                │
│   ┌─────────────────┐                                                       │
│   │  PostgreSQL     │  Replication lag: 50ms (eventual consistency)         │
│   │  Read Replicas  │                                                       │
│   └─────────────────┘                                                       │
│                                                                             │
│   Response: HTTP 200 OK {updated user data}                                 │
│                                                                             │
│   Failure Points (L6 Thinking):                                             │
│   • Primary down: Write fails (need failover to replica)                    │
│   • Transaction timeout: Rollback, return error                             │
│   • Cache invalidation fails: Stale cache (acceptable, TTL expires)         │
│   • Replication lag: Reads might be stale (acceptable for most use cases)   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Staff Engineer insight**: Visualizing read/write flows reveals:
- **Bottlenecks**: Where requests queue (connection pool, database)
- **Failure points**: What breaks first (cache, connection pool, database)
- **Degradation paths**: How to gracefully degrade (cache miss → database, stale data)
- **Optimization opportunities**: Where to add caching, connection pooling, read replicas

### Change Rate

How often does your data model change?

**Stable schema** (changes < monthly):
- Core business entities
- Financial records
- User accounts

Relational databases excel here. Schema enforcement catches bugs before they reach production.

**Evolving schema** (changes weekly):
- Feature flags and experiments
- A/B test configurations
- Content with varying attributes

Document stores or JSONB columns provide flexibility while maintaining some structure.

**Highly dynamic** (changes per request):
- User-generated content with arbitrary attributes
- Integration data from external systems
- Configuration that varies by client

Consider schema-on-read approaches, but invest heavily in validation at application boundaries.

---

## Read vs Write Heavy Workloads

This distinction profoundly affects database choice:

### Read-Heavy Workloads (>90% reads)

Characteristics:
- Data is written once, read many times
- Caching is highly effective
- Indexes have high ROI

Optimization strategies:
- Add read replicas
- Use read-through caching (Redis, Memcached)
- Denormalize for read efficiency
- Pre-compute expensive aggregations

Database guidance:
- Relational databases handle read-heavy workloads well
- Add caching layer before changing databases
- Consider materialized views for complex queries

### Write-Heavy Workloads (>50% writes)

Characteristics:
- Data arrives faster than it can be indexed
- Caching is less effective
- Index maintenance becomes expensive

Optimization strategies:
- Batch writes where possible
- Use append-only structures (LSM trees)
- Delay index updates
- Partition aggressively

Database guidance:
- Wide-column stores (Cassandra, Bigtable) are optimized for writes
- Time-series databases for temporal data
- Consider write-behind caching patterns

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    READ/WRITE PATTERNS AND DATABASE FIT                     │
│                                                                             │
│                          Write Latency Requirement                          │
│                      LOW (<10ms)           HIGH (acceptable)                │
│                                                                             │
│   Read        LOW    ┌─────────────────┬─────────────────────┐              │
│   Latency     (<10ms)│ Redis/Memcached │ PostgreSQL + Cache  │              │
│   Requirement        │(but durability?)│ (most common case)  │              │
│                      ├─────────────────┼─────────────────────┤              │
│               HIGH   │ Cassandra       │ Bigtable/DynamoDB   │              │
│         (acceptable) │ Wide-column     │ Write-optimized     │              │
│                      │ stores          │ with eventual read  │              │
│                      └─────────────────┴─────────────────────┘              │
│                                                                             │
│   Note: "Low latency for both reads AND writes" is expensive.               │
│         Make sure you actually need it before paying that cost.             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 2: SQL Systems (Relational Databases)

## Strengths: Transactions, Consistency, Constraints

Relational databases remain the default choice for most applications for good reasons:

### ACID Transactions

```sql
BEGIN;
  UPDATE accounts SET balance = balance - 100 WHERE id = 'alice';
  UPDATE accounts SET balance = balance + 100 WHERE id = 'bob';
COMMIT;
```

This either happens completely or not at all. No other system provides this guarantee as reliably. When people ask "why PostgreSQL in 2025?", the answer often starts here.

**Atomicity**: All operations in a transaction succeed or all fail. No partial updates.

**Consistency**: Transactions move the database from one valid state to another. Constraints are never violated.

**Isolation**: Concurrent transactions don't interfere with each other (configurable levels).

**Durability**: Committed transactions survive crashes, power failures, and disk failures.

### Declarative Queries

SQL lets you describe *what* you want, not *how* to get it:

```sql
SELECT users.name, COUNT(orders.id) as order_count
FROM users
LEFT JOIN orders ON orders.user_id = users.id
WHERE users.created_at > '2024-01-01'
GROUP BY users.id
HAVING COUNT(orders.id) > 5
ORDER BY order_count DESC
LIMIT 10;
```

The query optimizer figures out execution plans, chooses indexes, and adapts to data distribution. This is decades of computer science working for you.

### Schema Enforcement

```sql
CREATE TABLE orders (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    total DECIMAL(10,2) NOT NULL CHECK (total > 0),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Every constraint is a bug that can never happen:
- `NOT NULL`: No mysterious empty values
- `REFERENCES`: No orphaned records
- `CHECK`: No invalid states
- Types: No "undefined" in a number field

**Staff Insight**: People complain about schema rigidity until they're debugging why 0.03% of their documents have `user_id` as a string instead of an integer, and that's causing subtle failures in their recommendation pipeline.

---

## Limits at Scale

Relational databases have real limits, but they're often misunderstood:

### Write Throughput

Single-node PostgreSQL can handle ~10,000-50,000 writes/second depending on complexity. This is enough for most applications.

**When you hit this limit**:
- Batch writes where possible
- Reduce indexes (each index adds write overhead)
- Consider partitioning within the same instance
- Then consider sharding or changing databases

### Connection Limits

Each connection consumes memory (~10MB baseline). With 1,000 connections, that's 10GB just for connection overhead.

**Solutions before changing databases**:
- Connection pooling (PgBouncer, application-level)
- Async connection management
- Reduce connection hold times

### Join Performance

Joins across large tables can be expensive. But:
- Proper indexing solves most join problems
- Query planners are sophisticated—profile before optimizing
- Denormalization is a valid optimization

### Single Point of Failure

A single PostgreSQL instance is a SPOF. But:
- Streaming replication provides read replicas
- Synchronous replication provides failover protection
- Patroni/stolon provide automated failover

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    POSTGRESQL SCALING BOUNDARIES                            │
│                                                                             │
│   Users/Day        Typical PostgreSQL Setup                                 │
│   ───────────────────────────────────────────────────────────────────       │
│   < 100K           Single node, no replicas                                 │
│                    (Don't over-engineer)                                    │
│                                                                             │
│   100K - 1M        Primary + read replicas                                  │
│                    Connection pooling, query optimization                   │
│                                                                             │
│   1M - 10M         Partitioning, read replicas, caching layer               │
│                    Consider splitting databases by domain                   │
│                                                                             │
│   10M - 100M       Sharding becomes necessary                               │
│                    Citus, Vitess, or application-level sharding             │
│                    OR move hot data to specialized stores                   │
│                                                                             │
│   > 100M           Hybrid architecture likely                               │
│                    Relational for some data, specialized stores for others  │
│                                                                             │
│   Note: These are order-of-magnitude guidelines. Actual limits depend       │
│         heavily on data size, query complexity, and hardware.               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Vertical vs Horizontal Scaling

### Vertical Scaling (Scale Up)

Add more resources to a single machine:
- More CPU cores
- More RAM
- Faster disks (NVMe)
- More disk space

**Advantages**:
- No application changes
- No distributed systems complexity
- Transactions still work
- Joins still work

**When to use**: Always try this first. Modern cloud instances are massive—128 cores, 4TB RAM, NVMe storage. This handles more than people think.

**Limits**: Eventually you hit the largest available instance, or cost becomes prohibitive.

### Horizontal Scaling (Scale Out)

Distribute data across multiple machines:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    HORIZONTAL SCALING APPROACHES                            │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  READ REPLICAS                                                      │   │
│   │  • Primary handles writes, replicas handle reads                    │   │
│   │  • Simple to implement                                              │   │
│   │  • No change to write path                                          │   │
│   │  • Eventual consistency for reads (replication lag)                 │   │
│   │                                                                     │   │
│   │  Primary ──write──→ [Replica 1]                                     │   │
│   │     ↑                [Replica 2]  ←── reads distributed             │   │
│   │     │                [Replica 3]                                    │   │
│   │   writes                                                            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  SHARDING (Partitioning across machines)                            │   │
│   │  • Data split by shard key (user_id, tenant_id, etc.)               │   │
│   │  • Each shard is a full database instance                           │   │
│   │  • Cross-shard queries are expensive/impossible                     │   │
│   │  • Rebalancing is painful                                           │   │
│   │                                                                     │   │
│   │  [Shard 1: users A-L]  [Shard 2: users M-Z]                         │   │
│   │         ↑                       ↑                                   │   │
│   │         └───── Router ──────────┘                                   │   │
│   │                  ↑                                                  │   │
│   │              Application                                            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  FUNCTIONAL PARTITIONING                                            │   │
│   │  • Different data types go to different databases                   │   │
│   │  • Users in PostgreSQL, Logs in Bigtable, Cache in Redis            │   │
│   │  • Each database does what it's best at                             │   │
│   │  • Cross-database transactions impossible                           │   │
│   │                                                                     │   │
│   │  [PostgreSQL]  [Bigtable]  [Redis]                                  │   │
│   │    Users        Events      Sessions                                │   │
│   │    Orders       Logs        Rate limits                             │   │
│   │    Products     Metrics     Cache                                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Staff Insight**: Sharding is often discussed but rarely needed. Most companies that think they need sharding actually need better indexing, connection pooling, or to separate read and write workloads. Sharding has enormous operational cost—don't pay it until you must.

---

## Where SQL Is Still the Correct Choice at Google Scale

Even at Google's scale, relational databases remain the right choice for certain workloads:

### 1. Financial Transactions

Money requires ACID guarantees. When you transfer funds, you cannot tolerate partial failures or eventual consistency. This is PostgreSQL territory (or Spanner when you need global distribution).

### 2. User Account Data

User accounts have:
- Stable schema
- Complex querying needs (by email, by phone, by OAuth ID)
- Strong consistency requirements (password changes must be immediately effective)
- Audit requirements

Document stores add complexity without benefit here.

### 3. Access Control and Permissions

Permission systems need:
- Complex joins (user → roles → permissions → resources)
- Immediate consistency (revocation must be instant)
- Transactional updates (adding permission to role updates all users atomically)

Relational databases express these relationships naturally.

### 4. Inventory and Reservation Systems

When you book a hotel room or buy a limited item:
- You need atomic check-and-decrement
- Overselling is catastrophic
- Eventual consistency means lost revenue and angry customers

### 5. Multi-Tenant SaaS Platforms

When different customers share infrastructure:
- Schema is consistent across tenants
- Complex queries per tenant
- Tenant isolation is critical
- PostgreSQL row-level security works well

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    WHEN SQL IS (STILL) THE ANSWER                           │
│                                                                             │
│   Data Characteristic           SQL Advantage                               │
│   ───────────────────────────────────────────────────────────────────       │
│   Needs ACID transactions       Built-in, battle-tested                     │
│   Multi-table relationships     Native JOINs, foreign keys                  │
│   Complex ad-hoc queries        Expressive SQL, query planner               │
│   Stable, known schema          Constraint enforcement                      │
│   Audit/compliance needs        Triggers, logging, constraints              │
│   Team knows SQL well           Faster development, fewer bugs              │
│   <10TB of data                 Single instance handles it                  │
│                                                                             │
│   Rule of Thumb: Start with PostgreSQL unless you have a specific           │
│                  reason not to. "NoSQL" is not a reason.                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 3: NoSQL Systems

## Key-Value Stores

### What They Are

The simplest data model: a key maps to a value.

```
"user:12345:session" → {"token": "abc123", "expires": 1699999999}
"rate:api:10.0.0.1" → 42
"cache:product:789" → <serialized product object>
```

### When to Use

**Session storage**: Fast lookups by session ID, no complex queries needed.

**Caching**: Cache invalidation is simple (delete by key), no relationships.

**Rate limiting**: Increment counters by key, TTL for expiration.

**Feature flags**: Simple key→value, infrequent writes, many reads.

### When to Avoid

**When you need secondary indexes**: "Find all sessions for user X" requires scanning all keys.

**When you need transactions across keys**: Most key-value stores don't support this (or support it poorly).

**When keys aren't predictable**: If you can't construct the key from request context, you can't retrieve the value efficiently.

### Representative Systems

**Redis**: Single-threaded, in-memory, incredibly fast. Rich data structures (lists, sets, sorted sets, hashes). Persistence is configurable but has trade-offs.

**Memcached**: Pure caching, no persistence, multi-threaded. Simpler than Redis, sometimes faster for pure cache workloads.

**DynamoDB**: Managed, durable, scalable. More expensive, higher latency than Redis. Good when you need durability without operational burden.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    KEY-VALUE STORE DECISION                                 │
│                                                                             │
│   Question                              Guidance                            │
│   ───────────────────────────────────────────────────────────────────       │
│   Need durability?                      NO  → Memcached (pure cache)        │
│                                         YES → Redis w/AOF or DynamoDB       │
│                                                                             │
│   Need data structures (lists, sets)?   YES → Redis                         │
│                                         NO  → Any key-value works           │
│                                                                             │
│   Want managed service?                 YES → DynamoDB, ElastiCache         │
│                                         NO  → Self-hosted Redis             │
│                                                                             │
│   Sub-millisecond latency required?     YES → Redis/Memcached (in-memory)   │
│                                         NO  → DynamoDB acceptable           │
│                                                                             │
│   Multi-region needed?                  YES → DynamoDB Global Tables        │
│                                         NO  → Single-region options work    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Document Stores

### What They Are

Documents are self-contained data units, typically JSON:

```json
{
  "_id": "user_12345",
  "name": "Alice Chen",
  "email": "alice@example.com",
  "preferences": {
    "theme": "dark",
    "notifications": {
      "email": true,
      "push": false
    }
  },
  "addresses": [
    {"type": "home", "city": "Seattle", "zip": "98101"},
    {"type": "work", "city": "Bellevue", "zip": "98004"}
  ]
}
```

### When to Use

**Content management**: Blog posts, product descriptions, articles with varying structure.

**Product catalogs**: Different product types have different attributes (books have ISBN, electronics have wattage).

**User profiles with preferences**: Core fields are consistent, preferences are variable.

**Prototyping**: When schema is genuinely uncertain and you're iterating rapidly.

### When to Avoid

**When relationships matter**: "Find all products in Alice's wishlist that are on sale" requires joins that document stores do poorly.

**When consistency is critical**: Document stores often default to eventual consistency. MongoDB's transactions exist but have limitations.

**When you need aggregations**: "Average order value by category" is inefficient in document stores without pre-computation.

**When schema is actually stable**: You're not gaining flexibility, just losing constraints.

### The Schema Myth

Document stores are called "schema-less." This is misleading.

Your application code expects documents to have certain fields. That's a schema—it's just implicit instead of explicit, and enforced in application code instead of the database.

**Implicit schema problems**:
- Each service that reads the data must handle schema variations
- Old documents might be missing new fields
- Type coercion differs across programming languages
- Debugging "why is this field null?" is harder

**Staff Insight**: "Schema-less" usually means "schema spread across application code and hope." For rapidly evolving products with small teams, this trade-off might be worth it. For mature products with multiple teams, explicit schemas catch more bugs than they prevent flexibility.

### Representative Systems

**MongoDB**: Most popular, flexible indexes, aggregation pipeline. Transactions across documents now supported but with limitations.

**Couchbase**: Adds caching layer, good for session data. N1QL provides SQL-like querying.

**Firestore**: Managed, real-time sync to clients. Good for mobile apps with offline support.

---

## Wide-Column Stores

### What They Are

Think of spreadsheets with sparse columns:

```
Row Key          | Column Family: profile    | Column Family: activity
─────────────────────────────────────────────────────────────────────────
user:alice       | name: "Alice"             | login:2024-01-15: "web"
                 | email: "alice@x.com"      | login:2024-01-16: "mobile"
                 | created: "2023-06-01"     | login:2024-01-17: "web"
─────────────────────────────────────────────────────────────────────────
user:bob         | name: "Bob"               | login:2024-01-16: "web"
                 | email: "bob@y.com"        |
```

Key insight: Rows can have millions of columns. Columns are grouped into families. Storage is optimized for column families.

### When to Use

**Time-series data**: Events, logs, metrics. Row key is entity + time bucket, columns are individual events.

**High-write throughput**: LSM trees optimize for writes. Can handle millions of writes per second.

**Sparse data**: Not every row has every column. No storage wasted on nulls.

**Range scans by row key**: "Get all events for user X in January" is a single scan.

### When to Avoid

**When you need secondary indexes**: Finding "all users who logged in today" requires scanning all rows.

**When you need ACID transactions**: Most wide-column stores provide only row-level atomicity.

**When you need complex queries**: No joins, limited aggregation. You compute in application code.

**When data fits in memory**: Wide-column stores are designed for disk-based scale. For small datasets, simpler is better.

### Representative Systems

**Bigtable/HBase**: The original wide-column stores. Bigtable is Google-managed, HBase is open-source Hadoop-based.

**Cassandra**: Masterless (no single point of failure), tunable consistency. Wide adoption.

**ScyllaDB**: C++ rewrite of Cassandra, claims 10x performance.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    WIDE-COLUMN DATA MODEL                                   │
│                                                                             │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │  Row Key: "sensor:temp:building-a:floor-3"                           │  │
│   │                                                                      │  │
│   │  Column Family: readings                                             │  │
│   │  ┌───────────────┬───────────────┬───────────────┬─────────────────┐ │  │
│   │  │ 2024-01-15T00 │ 2024-01-15T01 │ 2024-01-15T02 │ ... millions    │ │  │
│   │  │ value: 72.3   │ value: 71.8   │ value: 72.1   │     more ...    │ │  │
│   │  │ unit: F       │ unit: F       │ unit: F       │                 │ │  │
│   │  └───────────────┴───────────────┴───────────────┴─────────────────┘ │  │
│   │                                                                      │  │
│   │  Access pattern: Get all readings for sensor X in time range Y-Z     │  │
│   │  → Single row scan, extremely efficient                              │  │
│   │                                                                      │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   Key design principle: Row key = partition key + sort key                  │
│   All your access patterns must be expressible through row key ranges       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Trade-offs in Consistency and Querying

### Consistency Trade-offs

NoSQL databases typically offer tunable consistency:

**Cassandra/DynamoDB style**:
- Write consistency: How many replicas must acknowledge?
- Read consistency: How many replicas must respond?
- QUORUM = majority (more consistent, higher latency)
- ONE = single replica (faster, might read stale)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CASSANDRA CONSISTENCY LEVELS                             │
│                                                                             │
│   Write CL     Read CL      Guarantee          Latency    Availability      │
│   ───────────────────────────────────────────────────────────────────       │
│   ONE          ONE          None (stale OK)    Lowest     Highest           │
│   QUORUM       ONE          Read-your-writes*  Medium     High              │
│   QUORUM       QUORUM       Strong*            Higher     Medium            │
│   ALL          ALL          Linearizable       Highest    Lowest            │
│                                                                             │
│   * Within a single datacenter. Cross-DC adds complexity.                   │
│                                                                             │
│   Formula: W + R > N guarantees reading latest write                        │
│            (W = write replicas, R = read replicas, N = total replicas)      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Querying Trade-offs

NoSQL databases sacrifice query flexibility for scale and performance:

**What you lose**:
- Arbitrary ad-hoc queries
- Joins across entities
- Complex aggregations
- Subqueries, CTEs, window functions

**What you must do instead**:
- Design schema around query patterns
- Pre-compute aggregations
- Denormalize data
- Maintain secondary indexes manually (or accept their cost)

**Staff Insight**: The NoSQL query limitation isn't just about features—it's about flexibility. When requirements change, relational databases often require only query changes. NoSQL databases often require data model changes, which means migrations.

---

## Schema Evolution Challenges

### The Problem

All data systems face schema evolution. But NoSQL databases make it harder:

**Relational migration**:
```sql
ALTER TABLE users ADD COLUMN phone VARCHAR(20);
-- Old code ignores new column
-- New code uses new column
-- Clear moment of transition
```

**Document store "migration"**:
```javascript
// Some documents have "phone", some don't
// Every read must handle both cases
// No clear moment of transition
// "Schema" is scattered across code
```

### Evolution Strategies

**1. Lazy Migration**
Update documents when read:
```javascript
function getUser(id) {
  const user = await db.get(id);
  if (!user.version || user.version < 2) {
    user.phone = user.phone || null;
    user.version = 2;
    await db.put(user);
  }
  return user;
}
```

**Pros**: No downtime, no bulk migration
**Cons**: Never-read documents never update, code carries legacy forever

**2. Bulk Migration**
Background job updates all documents:
```javascript
// Background job
for await (const user of db.scan()) {
  if (!user.version || user.version < 2) {
    user.phone = user.phone || null;
    user.version = 2;
    await db.put(user);
  }
}
```

**Pros**: Clean cutover possible
**Cons**: Resource-intensive, can take days for large datasets

**3. Multiple Versions in Flight**
Application handles multiple versions simultaneously:

**Pros**: Maximum flexibility
**Cons**: Code complexity explodes with versions

### Staff Insight

Schema evolution in NoSQL isn't easier—it's just deferred. Relational databases force you to think about migration at deploy time. NoSQL databases let you defer it, but the work still exists, and it's often harder because it's spread across application code.

---

## Operational Complexity Hidden Behind "Simple APIs"

The marketing pitch: "Just put and get! No schemas! No joins! Simple!"

The operational reality is far more complex. NoSQL databases trade away database-managed complexity in exchange for application-managed complexity. The work doesn't disappear—it just moves to your team.

**A cautionary tale**: A startup chose MongoDB because "it's easy—no schema migrations!" Two years later:
- They had 47 different "versions" of user documents in production
- Every query included defensive code: `if (user.address) { if (user.address.zip) { ... } }`
- A junior engineer's bug wrote `userId` as a string (not ObjectId) in 0.3% of documents
- Finding those documents required a full collection scan (2 hours)
- The "easy" database had created far more work than PostgreSQL migrations ever would

### Cassandra Example

Let's look at what "simple" really means in production.

**Simple API**: `INSERT INTO users (id, name) VALUES (uuid(), 'Alice');`

Yes, that's the API. Here's what you actually need to understand to run Cassandra in production:

**Hidden complexity**:

1. **Partition key design determines data distribution**: 
   - Your choice of partition key decides which node stores which data
   - Bad choice (e.g., `date` as partition key) = all today's data on one node
   - Changing partition key requires migrating all data to a new table

2. **Poor key design = hot partitions = cluster meltdown**:
   - Cassandra can handle 100K writes/second across the cluster
   - But if they all go to one partition, that node melts
   - You discover this at 3 AM during a traffic spike

3. **Compaction strategies affect read/write performance**:
   - Cassandra writes to SSTables, which accumulate
   - Compaction merges them (like garbage collection for data)
   - Wrong strategy → reads scan 50 files instead of 2
   - Right strategy depends on your workload (no one-size-fits-all)

4. **Tombstone management**:
   - Deletes don't remove data—they write "tombstones"
   - Reading scans tombstones too
   - 100K tombstones in a partition → 30-second queries
   - You need to understand and manage TTLs, compaction, and gc_grace_seconds

5. **Repair operations**:
   - Replicas can diverge due to network issues
   - "Repair" synchronizes them
   - Running repair can saturate your network and CPU
   - Not running repair = silent data loss
   - Scheduling repairs correctly is an ongoing operational task

6. **Sizing decisions**:
   - How many nodes? Depends on throughput, data size, replication factor
   - Which instance types? Cassandra is memory and I/O hungry
   - How much disk? SSDs required, provisioned IOPS if cloud
   - All of these are your problem to figure out

### DynamoDB Example

**Simple API**: `dynamodb.putItem({TableName: 'users', Item: {...}})`

**Hidden complexity**:
- Capacity planning (provisioned vs on-demand)
- Partition key design (same hot partition problem)
- GSI consistency (eventual, not immediate)
- GSI projection choices (all, keys only, include)
- Cost modeling (reads, writes, storage, data transfer)
- Streams for change data capture
- TTL configuration and behavior

### MongoDB Example

**Simple API**: `db.users.insertOne({name: 'Alice'})`

**Hidden complexity**:
- Replica set configuration and elections
- Write concern and read preference settings
- Sharding key selection (immutable after creation!)
- Chunk splitting and balancing
- Index build strategies (background vs foreground)
- WiredTiger cache sizing
- Oplog sizing for replication

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    OPERATIONAL COMPLEXITY REALITY                           │
│                                                                             │
│   What they say:     "Easy to get started!"                                 │
│   What they mean:    "Easy to insert first document"                        │
│                                                                             │
│   What they say:     "Scales horizontally!"                                 │
│   What they mean:    "CAN scale if you designed partition keys correctly"   │
│                                                                             │
│   What they say:     "Schema-less flexibility!"                             │
│   What they mean:    "Schema bugs are now application bugs"                 │
│                                                                             │
│   What they say:     "No DBA needed!"                                       │
│   What they mean:    "You are now the DBA"                                  │
│                                                                             │
│   Staff Insight: Operational complexity doesn't disappear.                  │
│                  It either lives in the database, or in your team.          │
│                  PostgreSQL's complexity is documented and understood.      │
│                  Your custom NoSQL operations are not.                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 4: NewSQL / Distributed SQL

## Why They Exist

The promise: SQL semantics + NoSQL scale.

The motivation:
1. SQL is productive and well-understood
2. Relational databases don't scale past certain points
3. NoSQL sacrifices too much functionality
4. Can we have both?

NewSQL systems attempt to provide:
- Horizontal scalability (like NoSQL)
- ACID transactions (like traditional SQL)
- SQL query interface (familiar to developers)
- Automatic sharding (without manual partition management)

---

## What Problems They Solve

### Global Distribution with Strong Consistency

**Traditional approach**: Master in one region, replicas in others, cross-region writes slow.

**NewSQL approach** (e.g., Spanner, CockroachDB):
- Data automatically partitioned and replicated
- Transactions span regions with consistency
- Reads can be local for most data

### OLTP at Scale

Traditional RDBMS hits limits around:
- 100,000 writes/second
- 10TB of actively queried data
- Single-region deployment

NewSQL systems push these limits by:
- Distributing writes across many nodes
- Automatic sharding
- Parallel query execution

### Avoiding NoSQL Trade-offs

NoSQL forced choices:
- Give up joins? → Use NewSQL
- Give up transactions? → Use NewSQL
- Give up SQL? → Use NewSQL

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    NEWSQL POSITIONING                                       │
│                                                                             │
│                              Scaling Capability                             │
│                          LOW ─────────────────── HIGH                       │
│                                                                             │
│   SQL      HIGH ┌────────────────────┬────────────────────┐                 │
│   Feature       │                    │                    │                 │
│   Support       │   PostgreSQL       │   Spanner          │                 │
│                 │   MySQL            │   CockroachDB      │                 │
│                 │   (Single node)    │   TiDB             │                 │
│                 │                    │   (NewSQL)         │                 │
│                 ├────────────────────┼────────────────────┤                 │
│            LOW  │                    │                    │                 │
│                 │   SQLite           │   Cassandra        │                 │
│                 │   (Embedded)       │   DynamoDB         │                 │
│                 │                    │   (NoSQL)          │                 │
│                 └────────────────────┴────────────────────┘                 │
│                                                                             │
│   NewSQL occupies the top-right: high SQL support + high scale              │
│   The question is: at what cost?                                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Where They Still Fall Short

### Latency

Distributed transactions require coordination. Even with clever optimizations (TrueTime in Spanner, Hybrid Logical Clocks in CockroachDB), cross-node transactions add latency.

**Single-node PostgreSQL**: 1-5ms for a transaction
**Distributed NewSQL**: 10-100ms for a cross-partition transaction

For latency-sensitive workloads, this matters.

### Complexity

NewSQL systems are complex:
- More failure modes than single-node databases
- Harder to debug (where did my query execute?)
- More configuration options
- Less mature tooling
- Fewer experts available

### Cost

Running a distributed database cluster is expensive:
- Minimum 3 nodes (usually more)
- Network traffic between nodes
- More operational overhead
- Managed services are pricier than managed PostgreSQL

### Partial SQL Support

Most NewSQL systems don't support all SQL features:
- Some PostgreSQL extensions don't work
- Advanced features may be missing (CTEs, window functions, etc.)
- Stored procedures often unsupported or different
- Query planner may not be as sophisticated

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    NEWSQL LIMITATIONS                                       │
│                                                                             │
│   Claim                      Reality                                        │
│   ───────────────────────────────────────────────────────────────────       │
│   "Drop-in PostgreSQL        Often 80-90% compatible. That 10-20%           │
│    replacement"              can require significant code changes.          │
│                                                                             │
│   "Horizontal scale"         True, but only if your workload partitions     │
│                              well. Hot partitions still exist.              │
│                                                                             │
│   "Global distribution"      True, but with latency implications.           │
│                              Cross-region transactions are slow.            │
│                                                                             │
│   "Easier than sharding"     True, but not zero effort. You still           │
│                              design for distributed behavior.               │
│                                                                             │
│   "ACID transactions"        True, but distributed transactions             │
│                              are slower than local transactions.            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## When Staff Engineers Avoid Them

### When Scale Isn't the Problem

If single-node PostgreSQL handles your load, NewSQL adds complexity without benefit. Most applications don't need horizontal scale.

**Heuristic**: If your data fits on one machine (<10TB) and your write rate is manageable (<50k writes/second), you probably don't need NewSQL.

### When Latency Is Critical

Sub-10ms transaction latency is hard to achieve with distributed databases. For real-time trading, gaming, or other latency-sensitive applications, single-node databases (with failover) may be better.

### When Team Expertise Is Limited

NewSQL systems require understanding of:
- Distributed systems fundamentals
- Partition design
- Consistency trade-offs
- New failure modes

If your team isn't ready, you'll make expensive mistakes.

### When Cost Is a Concern

A 3-node CockroachDB cluster costs 3x a single PostgreSQL instance, plus network, plus operational overhead. For startups and cost-sensitive applications, this premium may not be justified.

### When Vendor Lock-in Matters

Spanner is Google-only. Migrating away means rewriting. CockroachDB and TiDB are more portable, but still have unique behaviors. PostgreSQL is a commodity with many compatible implementations.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    NEWSQL DECISION FRAMEWORK                                │
│                                                                             │
│   Consider NewSQL when:                                                     │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  ✓ You need >100k writes/second sustained                           │   │
│   │  ✓ You need >10TB of actively queried data                          │   │
│   │  ✓ You need global distribution with strong consistency             │   │
│   │  ✓ You've outgrown single-node + read replicas                      │   │
│   │  ✓ You need ACID transactions that NoSQL can't provide              │   │
│   │  ✓ Your team has distributed systems experience                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Stay with traditional SQL when:                                           │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  ✓ Single-node PostgreSQL handles your load                         │   │
│   │  ✓ Read replicas solve your scaling problem                         │   │
│   │  ✓ Latency is critical (<10ms transactions)                         │   │
│   │  ✓ Cost is a primary concern                                        │   │
│   │  ✓ Team expertise is in traditional databases                       │   │
│   │  ✓ You need full PostgreSQL compatibility                           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Most companies should stay with traditional SQL.                          │
│   NewSQL is for specific scale/distribution problems, not general use.      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 5: Applied Examples

This section walks through three complete examples of database selection, showing the reasoning process a Staff Engineer uses. For each example, we'll:
1. Understand the requirements deeply
2. Analyze access patterns
3. Choose a database with explicit justification
4. Reject alternatives with reasoning
5. Design the architecture
6. Plan for failures and evolution

---

## Example 1: User Profile Service

### The Problem

Every application has user profiles. It seems simple—just store user data. But the decisions you make here affect authentication, personalization, compliance, and more. Let's think through it carefully.

### Requirements

- 50 million registered users
- 5 million daily active users
- Read-heavy: 99% reads, 1% writes
- Queries: by user_id (primary), by email (login), by phone (account recovery)
- Strong consistency for security-related fields (password, 2FA settings)
- Sub-100ms p99 latency for reads

### Thinking Through Access Patterns

Before choosing a database, let's understand exactly how this data will be accessed:

**Read patterns**:
1. **Login flow**: Given email, find user and verify password → Query by email, frequent (every login)
2. **Session validation**: Given user_id, get profile → Query by primary key, very frequent (every request)
3. **Account recovery**: Given phone, find user → Query by phone, infrequent
4. **Admin search**: Given partial name/email, find users → Complex query, rare but important

**Write patterns**:
1. **Registration**: Insert new user → Needs email/phone uniqueness check
2. **Profile update**: Update name, preferences → Point update by user_id
3. **Password change**: Update password_hash → Must be immediately consistent
4. **Email change**: Update email → Must atomically update unique constraint

**Key observations**:
- We need **secondary indexes** on email and phone (can't just use user_id)
- Password changes require **strong consistency** (security-critical)
- Email changes require **transactions** (uniqueness enforcement)
- The data has a **stable schema**—all users have the same fields

### Data Model

The data model separates stable core data from flexible preferences:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    USER PROFILE DATA MODEL                                  │
│                                                                             │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │  Core Profile (Stable Schema)                                      │    │
│   │  • user_id (PK): UUID                                              │    │
│   │  • email: string (unique, indexed)                                 │    │
│   │  • phone: string (indexed)                                         │    │
│   │  • password_hash: string                                           │    │
│   │  • name: string                                                    │    │
│   │  • created_at: timestamp                                           │    │
│   │  • updated_at: timestamp                                           │    │
│   │  • status: enum (active, suspended, deleted)                       │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │  User Preferences (Semi-Structured)                                │    │
│   │  • user_id (FK): UUID                                              │    │
│   │  • preferences: JSONB                                              │    │
│   │    {                                                               │    │
│   │      "theme": "dark",                                              │    │
│   │      "language": "en-US",                                          │    │
│   │      "notifications": {"email": true, "push": false}               │    │
│   │    }                                                               │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Database Choice: PostgreSQL

**Why PostgreSQL**:

1. **Schema stability**: User profiles have a well-known schema. Email, password, and name don't change shape. Schema enforcement catches bugs.

2. **Secondary indexes needed**: Login queries email, account recovery queries phone. PostgreSQL handles this naturally.

3. **Transactional updates**: Changing email must atomically update the unique constraint. Password changes must be immediately consistent.

4. **Query flexibility**: "Find all users who signed up in January from California" is a SQL query, not a map-reduce job.

5. **Team expertise**: Every engineer knows SQL. Onboarding is instant.

6. **Scale fits**: 50M users × 1KB = 50GB. That's one modestly-sized database.

### Why Not MongoDB (Rejected)

**Claimed benefit**: "User profiles are documents! Flexible schema!"

**Reality check**:
- The schema isn't flexible—user profiles have the same fields
- We need secondary indexes (email, phone)—MongoDB can do this, but PostgreSQL does it better
- We need transactions for email changes—MongoDB transactions exist but are less mature
- We gain nothing from document model and lose constraint enforcement

**Verdict**: MongoDB adds complexity without benefit for this use case.

### Why Not DynamoDB (Rejected)

**Claimed benefit**: "Scales infinitely! Managed!"

**Reality check**:
- We need secondary access patterns (email, phone)—requires GSIs
- GSIs have eventual consistency—dangerous for login/password
- 50M users is tiny for PostgreSQL
- DynamoDB query flexibility is limited

**Verdict**: DynamoDB is overkill. We don't need infinite scale, and we lose query flexibility.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    USER PROFILE SERVICE ARCHITECTURE                        │
│                                                                             │
│   ┌─────────────┐      ┌─────────────┐      ┌───────────────────────────┐   │
│   │   Client    │──────│   Profile   │──────│       PostgreSQL          │   │
│   │             │      │   Service   │      │                           │   │
│   └─────────────┘      └─────────────┘      │  ┌─────────────────────┐  │   │
│                              │              │  │  users              │  │   │
│                              │              │  │  ─────              │  │   │
│                              ▼              │  │  id (PK)            │  │   │
│                        ┌───────────┐        │  │  email (UNIQUE)     │  │   │
│                        │   Redis   │        │  │  phone (INDEX)      │  │   │
│                        │   Cache   │        │  │  password_hash      │  │   │
│                        │           │        │  │  ...                │  │   │
│                        │ user:{id} │        │  └─────────────────────┘  │   │
│                        │    ↓      │        │                           │   │
│                        │ profile   │        │  ┌─────────────────────┐  │   │
│                        └───────────┘        │  │  user_preferences   │  │   │
│                                             │  │  ─────              │  │   │
│                                             │  │  user_id (FK)       │  │   │
│   Write path: Direct to PostgreSQL          │  │  preferences JSONB  │  │   │
│   Read path: Redis → PostgreSQL (on miss)   │  └─────────────────────┘  │   │
│                                             │                           │   │
│   Cache invalidation: Write-through         └───────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Scaling Path

**Phase 1 (Current)**: Single PostgreSQL instance with Redis cache. Handles 50M users easily.

**Phase 2 (10x growth)**: Add read replicas. Route read queries to replicas, writes to primary.

**Phase 3 (100x growth)**: Shard by user_id. Each shard handles a subset of users. Email lookup needs a routing table or separate index.

---

## Example 2: Rate Limiter Counters

### The Problem

Rate limiting seems straightforward—count requests and reject when over limit. But at 100K requests/second, every millisecond matters. The wrong database choice here means either crushing your backend or blocking legitimate users.

### Requirements

- Track API requests per user per time window
- 100,000 requests/second peak
- Latency: <5ms for rate check
- Rules: 1000 requests/minute per user, 10,000 requests/hour per user
- Graceful degradation: If rate limiter fails, allow requests (don't block)

### Thinking Through Access Patterns

Let's understand what happens for every single API request:

**For each request (100K/second)**:
1. Construct a key: `ratelimit:{user_id}:{window}`
2. Increment counter for that key
3. Check if counter exceeds limit
4. If yes, reject; if no, proceed

**Critical observations**:
- This happens on **every single request**—the hot path
- 100K requests/second = 100K+ database operations/second
- Latency adds directly to every request's latency
- If rate limiter is slow, the entire API is slow

**What we DON'T need**:
- Complex queries (we know the exact key)
- Joins (single key lookup)
- Transactions (atomic increment is enough)
- Durability (losing counts on restart is acceptable)
- Secondary indexes (we construct the key from request context)

**What we DO need**:
- Sub-millisecond operations
- Atomic increment
- Automatic expiration (TTL)
- High throughput (100K+ ops/sec)

This profile points strongly toward an in-memory key-value store.

### Data Model

The sliding window counter approach balances accuracy and simplicity:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    RATE LIMITER DATA MODEL                                  │
│                                                                             │
│   Sliding Window Counter Approach:                                          │
│                                                                             │
│   Key: "ratelimit:{user_id}:{window}"                                       │
│   Value: counter (integer)                                                  │
│   TTL: window duration                                                      │
│                                                                             │
│   Example:                                                                  │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │  Key                                  Value    TTL                 │    │
│   │  ratelimit:user123:minute:202401151030   42    60s                 │    │
│   │  ratelimit:user123:hour:2024011510       847   3600s               │    │
│   │  ratelimit:user456:minute:202401151030   15    60s                 │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│   Operation: INCR + GET (atomic)                                            │
│   If counter > limit, reject request                                        │
│   TTL ensures automatic cleanup                                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Database Choice: Redis

**Why Redis**:

1. **Speed**: In-memory, sub-millisecond operations. INCR is O(1).

2. **Atomic operations**: INCR is atomic—no race conditions when multiple servers check the same user.

3. **TTL built-in**: Keys expire automatically. No cleanup job needed.

4. **Simple data model**: Key-value is exactly what we need. Nothing more.

5. **Failure mode is acceptable**: If Redis dies, we allow requests until it recovers. Better than blocking all traffic.

### Why Not PostgreSQL (Rejected)

**Claimed benefit**: "Already have it! Consistency!"

**Reality check**:
- 100k req/sec means 100k+ writes/sec to rate limit table
- Each rate check is a round trip to database
- PostgreSQL can't sustain this write rate without sharding
- Connection pool contention under load
- Latency: 5-20ms vs <1ms for Redis

**Verdict**: PostgreSQL is the wrong tool. Rate limiting needs speed over durability.

### Why Not DynamoDB (Rejected)

**Claimed benefit**: "Scales! Managed!"

**Reality check**:
- Latency: 5-10ms vs <1ms for Redis
- Cost: Per-request pricing adds up at 100k req/sec
- Complexity: Conditional updates for atomic increment
- TTL exists but has up to 48-hour delay for deletion

**Verdict**: DynamoDB works but is slower and more expensive than Redis for this use case.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    RATE LIMITER ARCHITECTURE                                │
│                                                                             │
│   ┌─────────────┐      ┌─────────────┐      ┌───────────────────────────┐   │
│   │   Request   │──────│  API Gate   │──────│         Redis             │   │
│   │             │      │             │      │        Cluster            │   │
│   └─────────────┘      └─────────────┘      │                           │   │
│                              │              │  ┌─────────────────────┐  │   │
│                              │              │  │ Node 1 (keys a-m)   │  │   │
│                              ▼              │  └─────────────────────┘  │   │
│                        ┌───────────┐        │  ┌─────────────────────┐  │   │
│                        │   Allow   │        │  │ Node 2 (keys n-z)   │  │   │
│                        │    or     │        │  └─────────────────────┘  │   │
│                        │   Deny    │        │                           │   │
│                        └───────────┘        │  Replication for HA       │   │
│                                             │  (async, may lose counts) │   │
│                                             └───────────────────────────┘   │
│                                                                             │
│   Failure Behavior:                                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Redis timeout → Allow request (fail open)                          │   │
│   │  Redis cluster partition → Allow request from affected nodes        │   │
│   │  Complete Redis failure → Degrade to IP-based limiting (backup)     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Why fail-open: Blocking legitimate users is worse than occasional         │
│                  over-limit requests during Redis failures.                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Handling Redis Failures

**Key insight**: Rate limiting is a guardrail, not a transaction. Temporary failure to rate limit is acceptable.

```python
async def check_rate_limit(user_id: str, limit: int, window: int) -> bool:
    key = f"ratelimit:{user_id}:{window}:{current_window_id()}"
    try:
        # INCR creates key if not exists, returns new value
        count = await redis.incr(key)
        if count == 1:
            # First request in window, set TTL
            await redis.expire(key, window)
        return count <= limit
    except RedisError:
        # Redis failure: fail open (allow request)
        # Log for monitoring, but don't block the user
        logger.warning(f"Rate limit check failed for {user_id}, allowing request")
        return True
```

---

## Example 3: Feed Storage

### The Problem

News feeds are deceptively complex. What looks like "show posts from people I follow" involves billions of relationships, real-time updates, and latency expectations that users have been trained to expect by Facebook, Twitter, and Instagram.

### Requirements

- 10 million users, 1 million daily active
- Each user follows average 200 other users
- Average user posts 2 items/day
- Feed shows latest 100 items from followed users
- Feed must be fresh (items appear within seconds)
- 10k feed reads/second at peak

### Let's Do The Math

Before choosing a database, let's understand the scale:

**Posts generated**:
- 10M users × 2 posts/day = 20M posts/day
- 20M / 86,400 seconds = ~230 posts/second

**Feed reads**:
- 10K feed reads/second at peak
- Each feed needs latest 100 posts from ~200 followed users

**The naive approach (fan-out on read)**:
- User opens feed → Query 200 users' posts → Merge and sort
- 10K feeds/second × 200 queries = 2M queries/second to posts table
- That's a lot of database load for reads

**The alternative (fan-out on write)**:
- User posts → Push to all followers' feeds
- Average followers per user: ~100 (power law, most have few)
- 230 posts/second × 100 followers = 23K writes/second to feed tables
- But reads are single query per user

**The celebrity problem**:
- What if a celebrity has 10 million followers?
- One post = 10 million writes
- That's impossible to do synchronously

This math reveals why feed systems need hybrid approaches.

### The Core Decision: Fan-Out Strategy

This is the defining architectural decision for feed systems. Let's understand each approach deeply:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FAN-OUT STRATEGIES                                       │
│                                                                             │
│   FAN-OUT ON WRITE (Push Model)                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  When Alice posts:                                                  │   │
│   │    For each of Alice's 1000 followers:                              │   │
│   │      Append post to follower's pre-built feed                       │   │
│   │                                                                     │   │
│   │  When Bob reads feed:                                               │   │
│   │    Return Bob's pre-built feed (one lookup)                         │   │
│   │                                                                     │   │
│   │  Pros: Fast reads, feed is pre-computed                             │   │
│   │  Cons: Slow writes (fan to all followers), storage heavy            │   │
│   │        Celebrity problem (million followers = million writes)       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   FAN-OUT ON READ (Pull Model)                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  When Alice posts:                                                  │   │
│   │    Store post in Alice's posts table (one write)                    │   │
│   │                                                                     │   │
│   │  When Bob reads feed:                                               │   │
│   │    Get list of people Bob follows                                   │   │
│   │    Query each person's recent posts                                 │   │
│   │    Merge and sort (expensive)                                       │   │
│   │                                                                     │   │
│   │  Pros: Fast writes, storage efficient                               │   │
│   │  Cons: Slow reads (query many tables)                               │   │
│   │        Read amplification (200 queries per feed load)               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   HYBRID (What production systems use)                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  For normal users: Fan-out on write                                 │   │
│   │  For celebrities (>10k followers): Fan-out on read                  │   │
│   │                                                                     │   │
│   │  When Bob reads feed:                                               │   │
│   │    Get pre-built feed (normal users' posts)                         │   │
│   │    Query celebrity posts separately                                 │   │
│   │    Merge (limited celebrity count)                                  │   │
│   │                                                                     │   │
│   │  Best of both: Fast reads, manageable writes                        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Understanding the Hybrid Approach

Let's walk through exactly how the hybrid approach works with a concrete example.

**When Alice (normal user, 500 followers) posts**:
1. Post saved to PostgreSQL (source of truth)
2. Message published to Kafka: "Alice posted XYZ"
3. Fan-out worker reads message
4. Worker fetches Alice's 500 followers from follow graph
5. For each follower, worker appends post to their feed in Cassandra
6. For active followers (online now), also update Redis cache

Total time: 100-500ms (async, Alice doesn't wait)
Total writes: 500 Cassandra writes, ~50 Redis writes

**When Taylor Swift (celebrity, 50M followers) posts**:
1. Post saved to PostgreSQL (source of truth)
2. Message published to Kafka: "Taylor posted XYZ"
3. Fan-out worker reads message
4. Worker sees Taylor is flagged as "celebrity" (>10K followers)
5. **No fan-out happens**—post stays only in Taylor's posts table
6. Post ID added to "celebrity recent posts" cache

Total time: <50ms (no fan-out)
Total writes: 1 PostgreSQL write, 1 cache update

**When Bob loads his feed**:
1. Check Redis for cached feed → if hit, return immediately
2. Query Bob's pre-computed feed from Cassandra (normal users' posts)
3. Query "who does Bob follow who is a celebrity?"
4. For each celebrity, fetch their recent posts
5. Merge celebrity posts with pre-computed feed
6. Cache result in Redis
7. Return to Bob

Total time: 30-80ms
Total queries: 1 Cassandra + ~3 celebrity queries + 1 Redis

**Why this works**: Normal users (99%) get fan-out on write (fast reads). Celebrities (1%) get fan-out on read (manageable writes). The merge at read time is small because users follow few celebrities.

### Database Choice: Cassandra + Redis

**Why Cassandra** (for feed storage):

Understanding why Cassandra fits requires understanding its data model:

1. **Write-optimized**: Cassandra uses LSM trees—writes go to an in-memory table, then flush to disk. No read-before-write. This handles 23K+ writes/second easily.

2. **Natural time-series model**: In Cassandra, a "row" can have millions of columns. We use row key = user_id, columns = time-ordered post IDs. Fetching a feed is scanning one row, not joining tables.

3. **Efficient range scans**: "Get latest 100 posts for user X" is: go to user X's row, scan backwards from newest, stop at 100. Single partition, single scan, extremely fast.

4. **Horizontal scale**: Need more capacity? Add nodes. Cassandra automatically rebalances. No sharding logic in application code.

5. **Tunable consistency**: For feeds, we use CL=ONE (fast, eventually consistent). Slightly stale feeds are acceptable.

**Why Redis** (for feed caching):

1. **Sub-millisecond reads**: Active users' feeds are cached.

2. **List operations**: LPUSH for adding to feed, LRANGE for reading.

3. **TTL**: Inactive users' feeds expire automatically.

### Why Not PostgreSQL (Rejected for Feed Storage)

**Claimed benefit**: "JOINs! Transactions! We know it!"

**Reality check**:
- Fan-out on write with PostgreSQL = 1000+ inserts per post
- Insert rate at scale: millions of inserts/minute
- Index maintenance becomes bottleneck
- Sharding PostgreSQL is complex

**Verdict**: PostgreSQL works for small scale but becomes write-bottlenecked.

### Why Not MongoDB (Rejected)

**Claimed benefit**: "Documents! Flexible!"

**Reality check**:
- Feed is an ordered list of post IDs—not really a document
- MongoDB's append-to-array has size limits (16MB doc)
- No advantage over Cassandra for this access pattern
- Cassandra's wide-column model fits better

**Verdict**: MongoDB doesn't offer advantages for this use case.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FEED SYSTEM ARCHITECTURE                                 │
│                                                                             │
│   Post Flow (Write Path)                                                    │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │  Alice posts ──→ Posts Service ──→ PostgreSQL (posts table)         │   │
│   │                       │                                             │   │
│   │                       ▼                                             │   │
│   │                 [Kafka Queue]                                       │   │
│   │                       │                                             │   │
│   │                       ▼                                             │   │
│   │              Fan-Out Workers                                        │   │
│   │                   │     │                                           │   │
│   │                   ▼     ▼                                           │   │
│   │            [Cassandra] [Redis]                                      │   │
│   │            (persistent) (cache)                                     │   │
│   │                                                                     │   │
│   │  • Posts stored in PostgreSQL (source of truth, queryable)          │   │
│   │  • Fan-out workers read Alice's followers                           │   │
│   │  • For non-celebrities: write to each follower's feed in Cassandra  │   │
│   │  • For active users: also update Redis cache                        │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Feed Read Flow                                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │  Bob requests feed                                                  │   │
│   │        │                                                            │   │
│   │        ▼                                                            │   │
│   │  [Check Redis Cache]                                                │   │
│   │        │                                                            │   │
│   │   Hit? ├──YES──→ Return cached feed ──→ Done                        │   │
│   │        │                                                            │   │
│   │        NO                                                           │   │
│   │        │                                                            │   │
│   │        ▼                                                            │   │
│   │  [Query Cassandra]                                                  │   │
│   │  Get Bob's pre-built feed (post IDs)                                │   │
│   │        │                                                            │   │
│   │        ▼                                                            │   │
│   │  [Hydrate from Posts Service]                                       │   │
│   │  Get full post content                                              │   │
│   │        │                                                            │   │
│   │        ▼                                                            │   │
│   │  [Cache in Redis] ──→ Return feed                                   │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Cassandra Schema

```
CREATE TABLE user_feeds (
    user_id     UUID,
    post_time   TIMEUUID,
    post_id     UUID,
    author_id   UUID,
    PRIMARY KEY (user_id, post_time)
) WITH CLUSTERING ORDER BY (post_time DESC);

-- Access pattern: Get latest 100 posts for user
SELECT * FROM user_feeds 
WHERE user_id = ? 
LIMIT 100;

-- Single partition scan, extremely efficient
```

---

# Part 6: Failure & Evolution

## What Happens When Traffic Spikes

### PostgreSQL Under Load

**Symptoms**:
- Connection pool exhausted
- Query latency increases
- CPU/memory spike
- Replica lag increases

**Mitigations**:
```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    POSTGRESQL TRAFFIC SPIKE RESPONSE                        │
│                                                                             │
│   Immediate (minutes)                                                       │
│   ├── Enable query timeout to prevent runaway queries                       │
│   ├── Kill slow queries blocking others                                     │
│   ├── Scale up instance (if cloud)                                          │
│   └── Shift more reads to replicas                                          │
│                                                                             │
│   Short-term (hours)                                                        │
│   ├── Add read replicas                                                     │
│   ├── Increase connection pool size (with limits)                           │
│   ├── Enable more aggressive caching                                        │
│   └── Add circuit breakers to non-critical queries                          │
│                                                                             │
│   Medium-term (days)                                                        │
│   ├── Optimize hot queries                                                  │
│   ├── Add missing indexes                                                   │
│   ├── Denormalize expensive joins                                           │
│   └── Move analytics queries to replica                                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Redis Under Load

**Symptoms**:
- Latency increases (normally <1ms, now 10ms+)
- Memory pressure
- Evictions increase
- Connections rejected

**Mitigations**:
- Add Redis cluster nodes
- Increase memory
- Review key expiration policies
- Identify and optimize hot keys
- Consider read replicas for read-heavy workloads

### Cassandra Under Load

**Symptoms**:
- Write latency increases
- Read latency increases
- Compaction falling behind
- Hints piling up

**Mitigations**:
- Add nodes (Cassandra scales horizontally)
- Review consistency levels (QUORUM → ONE for less critical reads)
- Increase compaction throughput
- Review data model for hot partitions

---

## What Happens When Nodes Fail

### Single PostgreSQL Node Failure

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    POSTGRESQL NODE FAILURE SCENARIOS                        │
│                                                                             │
│   Scenario 1: Primary fails, no sync replica                                │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • All writes fail                                                  │   │
│   │  • Data loss possible (uncommitted in WAL)                          │   │
│   │  • Promote async replica = some data loss                           │   │
│   │  • Recovery time: minutes to hours                                  │   │
│   │                                                                     │   │
│   │  Prevention: Synchronous replica for critical data                  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Scenario 2: Primary fails, sync replica exists                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Writes paused during failover                                    │   │
│   │  • No data loss (sync commit)                                       │   │
│   │  • Patroni/stolon promotes replica                                  │   │
│   │  • Recovery time: seconds to minutes                                │   │
│   │                                                                     │   │
│   │  Trade-off: Sync replication adds ~1-5ms latency                    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Scenario 3: Read replica fails                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Reads route to other replicas                                    │   │
│   │  • No data loss                                                     │   │
│   │  • Automatic with load balancer health checks                       │   │
│   │  • Recovery time: immediate (transparent)                           │   │
│   │                                                                     │   │
│   │  Best practice: Always have 2+ read replicas                        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Redis Node Failure

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    REDIS FAILURE SCENARIOS                                  │
│                                                                             │
│   Standalone Redis (No replication)                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • All cached data lost                                             │   │
│   │  • Service degrades (cache misses hit database)                     │   │
│   │  • Rate limiters reset (temporary over-admission)                   │   │
│   │  • Recovery: Restart and warm cache gradually                       │   │
│   │                                                                     │   │
│   │  Acceptable for: Pure cache, rate limiting (fail-open)              │   │
│   │  Not acceptable for: Session storage, any primary data              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Redis Sentinel (Primary-Replica)                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Sentinel detects failure (configurable timeout)                  │   │
│   │  • Promotes replica to primary                                      │   │
│   │  • Some writes may be lost (async replication)                      │   │
│   │  • Clients reconnect to new primary                                 │   │
│   │  • Recovery time: 10-30 seconds typical                             │   │
│   │                                                                     │   │
│   │  Trade-off: Complexity vs availability                              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Redis Cluster                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Node failure affects only its hash slots                         │   │
│   │  • Replica promoted for affected slots                              │   │
│   │  • Other slots unaffected                                           │   │
│   │  • Recovery time: seconds (automatic)                               │   │
│   │                                                                     │   │
│   │  Best practice: 3+ masters, each with 1+ replicas                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Cassandra Node Failure

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CASSANDRA FAILURE SCENARIOS                              │
│                                                                             │
│   Single Node Failure (Replication Factor 3)                                │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Data still available on 2 other replicas                         │   │
│   │  • Reads: QUORUM still achievable (2 of 3)                          │   │
│   │  • Writes: QUORUM still achievable                                  │   │
│   │  • Hinted handoff queues writes for failed node                     │   │
│   │  • Recovery: Node rejoins, receives hints, runs repair              │   │
│   │                                                                     │   │
│   │  Impact: Minimal if using QUORUM or lower consistency               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Two Node Failure (Replication Factor 3)                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • QUORUM no longer achievable for affected partitions              │   │
│   │  • CL=ONE still works (degraded consistency)                        │   │
│   │  • Risk of data loss if remaining node fails                        │   │
│   │  • Hints may overflow (configurable limit)                          │   │
│   │                                                                     │   │
│   │  Response: Emergency priority on recovery                           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Key Insight: Cassandra tolerates failure by design.                       │
│                RF=3 means any single node can fail without impact.          │
│                This is why Cassandra is chosen for high-availability.       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Partial Failures: The More Dangerous Reality

Total node failures are dramatic but rare. **Partial failures are common and more insidious**—they degrade performance, cause inconsistent behavior, and are harder to detect. Staff Engineers design for partial failures because they're what actually happens in production.

### What Are Partial Failures?

Partial failures occur when a database component degrades rather than completely failing:

- **Slow queries**: Some queries work, but take 10× longer than normal
- **Degraded consistency**: Reads return stale data, but writes still succeed
- **Resource exhaustion**: Database accepts connections but can't process them efficiently
- **Network issues**: Intermittent timeouts, not complete disconnection
- **Disk I/O saturation**: Database responds, but writes queue up

**Why partial failures are dangerous**: Unlike total failures (which are obvious), partial failures:
- Are harder to detect (metrics look "okay" in aggregate)
- Cause inconsistent user experience (some users see errors, others don't)
- Can persist for hours before someone notices
- Often cascade into total failures if not addressed

### Partial Failure Patterns

#### Pattern 1: Slow Dependency (The Silent Killer)

**Scenario**: PostgreSQL is experiencing disk I/O saturation. It's not down, but queries that normally take 10ms now take 2 seconds.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SLOW DEPENDENCY PARTIAL FAILURE                          │
│                                                                             │
│   Normal Operation:                                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   [API Request] → [Service] → [PostgreSQL: 10ms] → Response         │   │
│   │   Total latency: 15ms                                               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Partial Failure (Disk I/O Saturated):                                     │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   [API Request] → [Service] → [PostgreSQL: 2000ms] → Timeout        │   │
│   │   • PostgreSQL is "up" (health checks pass)                         │   │
│   │   • But queries are 200× slower                                     │   │
│   │   • Service waits for timeout (30 seconds)                          │   │
│   │   • Connection pool fills up (all connections waiting)              │   │
│   │   • New requests fail (no available connections)                    │   │
│   │                                                                     │   │
│   │   User Impact:                                                      │   │
│   │   • First 100 requests: Slow but succeed (2-30 seconds)             │   │
│   │   • Next 1000 requests: Fail immediately (connection pool full)     │   │
│   │   • Appears as "intermittent failures" to users                     │   │
│   │                                                                     │   │
│   │   Detection Challenge:                                              │   │
│   │   • Average latency might look okay (if most queries still fast)    │   │
│   │   • p99 latency spikes, but p50 might be normal                     │   │
│   │   • Error rate increases, but not obviously correlated              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   L6 Mitigation:                                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   • Set aggressive query timeouts (100ms, not 30s)                      │   │
│   • Monitor p95/p99 latency, not just average                           │   │
│   • Circuit breaker on slow queries (fail fast)                         │   │
│   • Graceful degradation (serve cached data, skip non-critical queries) │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Real-world example**: A messaging service had this exact pattern. Their PostgreSQL instance was "healthy" (CPU 40%, memory 60%), but disk I/O was saturated due to a background vacuum operation. User messages took 5-10 seconds to send instead of <100ms. The service appeared "up" but was effectively unusable.

#### Pattern 2: Degraded Consistency (Stale Reads)

**Scenario**: Read replicas are lagging behind the primary. Writes succeed immediately, but reads return stale data.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DEGRADED CONSISTENCY PARTIAL FAILURE                     │
│                                                                             │
│   Normal Operation (Replication Lag: <100ms):                               │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   Write: [User updates profile] → Primary → Replica (100ms lag)     │   │
│   │   Read:  [User views profile] → Replica → Returns latest data       │   │
│   │   User experience: Consistent                                       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Partial Failure (Replication Lag: 30 seconds):                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   Write: [User changes email] → Primary (succeeds immediately)      │   │
│   │   Read:  [User views profile] → Replica → Returns OLD email         │   │
│   │                                                                     │   │
│   │   User Impact:                                                      │   │
│   │   • User updates email, then immediately views profile              │   │
│   │   • Profile shows old email (confusing!)                            │   │
│   │   • User tries again, sees same old email                           │   │
│   │   • User reports "bug" - data not saving                            │   │
│   │                                                                     │   │
│   │   Why This Happens:                                                 │   │
│   │   • Replica is overloaded (can't keep up with write rate)           │   │
│   │   • Network issues between primary and replica                      │   │
│   │   • Replica is running expensive queries (blocking replication)     │   │
│   │                                                                     │   │
│   │   Detection Challenge:                                              │   │
│   │   • Database is "up" (both primary and replica responding)          │   │
│   │   • Error rate is zero (no failures)                                │   │
│   │   • But user experience is broken (stale data)                      │   │
│   │   • Only detected via user complaints or replication lag metrics    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   L6 Mitigation:                                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   • Monitor replication lag (alert if >1 second for critical data)      │   │
│   • Route reads to primary for "read-after-write" patterns              │   │
│   • Use session consistency (same user always reads from same replica)  │   │
│   • Graceful degradation: Show "updating..." indicator during lag       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Real-world example**: A social media platform experienced this during a viral event. Their read replicas couldn't keep up with write volume (millions of posts per minute). Users who posted content immediately tried to view it, but saw "no posts found" because reads hit stale replicas. The platform appeared "up" but core functionality was broken.

#### Pattern 3: Resource Exhaustion (Death by a Thousand Cuts)

**Scenario**: Database connections are exhausted, but the database itself is healthy. New requests fail, but existing connections work fine.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    RESOURCE EXHAUSTION PARTIAL FAILURE                      │
│                                                                             │
│   Normal Operation:                                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   Connection Pool: 500 max connections                              │   │
│   │   Active: 200 (40% utilization)                                     │   │
│   │   New requests: Get connection immediately                          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Partial Failure (Connection Pool Exhausted):                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   Connection Pool: 500 max connections                              │   │
│   │   Active: 500/500 (100% utilization)                                │   │
│   │   • All connections in use (some slow queries holding them)         │   │
│   │   • New requests: Fail immediately (no connections available)       │   │
│   │   • Existing requests: Still work (they have connections)           │   │
│   │                                                                     │   │
│   │   User Impact:                                                      │   │
│   │   • User A (has connection): Request succeeds (slowly)              │   │
│   │   • User B (needs new connection): Request fails immediately        │   │
│   │   • Appears as "intermittent failures" (50% success rate)           │   │
│   │   • No clear pattern (seems random)                                 │   │
│   │                                                                     │   │
│   │   Why This Happens:                                                 │   │
│   │   • Slow queries hold connections longer than expected              │   │
│   │   • Connection leak (connections not returned to pool)              │   │
│   │   • Traffic spike (more requests than pool can handle)              │   │
│   │   • Deadlock or long-running transaction                            │   │
│   │                                                                     │   │
│   │   Detection Challenge:                                              │   │
│   │   • Database CPU/memory look fine (not the bottleneck)              │   │
│   │   • Error messages say "connection pool exhausted" (clear!)         │   │
│   │   • But root cause (slow queries) might not be obvious              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   L6 Mitigation:                                                            │
│   • Monitor connection pool utilization (alert at 80%)                  │   │
│   • Set query timeouts (prevent slow queries from holding connections)  │   │
│   • Connection pool per service (isolate blast radius)                  │   │
│   • Circuit breaker when pool exhausted (fail fast, don't wait)         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Real-world example**: An e-commerce platform had this during Black Friday. Their PostgreSQL connection pool (500 connections) was exhausted by slow product search queries. Checkout requests (which needed new connections) failed immediately, while product browsing (which reused existing connections) worked fine. The platform appeared "up" but core revenue functionality was broken.

### Designing for Partial Failures

Staff Engineers design systems assuming partial failures will occur:

**1. Timeout aggressively**: Don't wait 30 seconds for a slow query. Fail fast at 100ms and serve degraded content.

**2. Monitor percentiles, not averages**: p95 and p99 latency reveal partial failures that averages hide.

**3. Circuit breakers**: When a dependency is slow, stop calling it temporarily rather than making it worse.

**4. Graceful degradation**: Design systems to work with partial data. A feed that shows 80% of posts is better than a feed that shows nothing.

**5. Blast radius isolation**: One slow query shouldn't exhaust all connections. Use separate pools, timeouts, and circuit breakers per critical path.

**Staff Engineer insight**: Total failures are obvious and get fixed quickly. Partial failures persist for hours or days, causing more user impact than total outages. Design for partial failures first.

---

## What Happens When Schema Changes Are Required

Schema changes are inevitable. How each database handles them differs dramatically:

### PostgreSQL Schema Changes

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    POSTGRESQL SCHEMA CHANGES                                │
│                                                                             │
│   Safe Operations (No/minimal locking)                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • ADD COLUMN (without default, nullable)                           │   │
│   │  • DROP COLUMN (just marks invisible)                               │   │
│   │  • CREATE INDEX CONCURRENTLY                                        │   │
│   │  • ADD CONSTRAINT NOT VALID (deferred validation)                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Dangerous Operations (Table lock, blocks all access)                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • ADD COLUMN with DEFAULT (rewrites table in PG < 11)              │   │
│   │  • ALTER COLUMN TYPE (may rewrite table)                            │   │
│   │  • ADD CONSTRAINT (validates existing rows)                         │   │
│   │  • CREATE INDEX (without CONCURRENTLY)                              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Best Practices                                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. Add nullable columns without defaults                           │   │
│   │  2. Backfill in batches with application code                       │   │
│   │  3. Add NOT NULL constraint after backfill                          │   │
│   │  4. Use CREATE INDEX CONCURRENTLY (slower but non-blocking)         │   │
│   │  5. Test migrations on production-size data in staging              │   │
│   │  6. Monitor lock wait times during deployment                       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Example: Adding a Required Column Safely

```sql
-- WRONG: This locks the table and rewrites it
ALTER TABLE users ADD COLUMN phone VARCHAR(20) NOT NULL DEFAULT '';

-- RIGHT: Three-step migration
-- Step 1: Add nullable column (instant, no lock)
ALTER TABLE users ADD COLUMN phone VARCHAR(20);

-- Step 2: Backfill in batches (application code)
UPDATE users SET phone = '' 
WHERE id IN (SELECT id FROM users WHERE phone IS NULL LIMIT 1000);
-- Repeat until all rows updated

-- Step 3: Add constraint (after backfill complete)
ALTER TABLE users ALTER COLUMN phone SET NOT NULL;
ALTER TABLE users ALTER COLUMN phone SET DEFAULT '';
```

### Cassandra Schema Changes

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CASSANDRA SCHEMA CHANGES                                 │
│                                                                             │
│   Schema Distribution                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Schema changes propagate across cluster                          │   │
│   │  • May take seconds to reach all nodes                              │   │
│   │  • Temporary schema disagreement possible                           │   │
│   │  • Use schema_agreement timeout before proceeding                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Safe Operations                                                           │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • ADD column (new column, null for existing rows)                  │   │
│   │  • DROP column (tombstones created, data still on disk)             │   │
│   │  • CREATE TABLE / DROP TABLE                                        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Impossible Operations                                                     │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Change PRIMARY KEY (requires new table + migration)              │   │
│   │  • Change CLUSTERING ORDER (requires new table)                     │   │
│   │  • Add column to PRIMARY KEY (requires new table)                   │   │
│   │                                                                     │   │
│   │  These require: Create new table → migrate data → swap → drop old   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Staff Insight: Cassandra's data model is harder to change than SQL.       │
│                  Get the PRIMARY KEY right the first time, or plan for      │
│                  expensive migrations.                                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Document Store Schema Evolution

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MONGODB/DOCUMENT STORE SCHEMA CHANGES                    │
│                                                                             │
│   The Myth: "Schema-less means no migrations!"                              │
│   The Reality: Migrations are just deferred and distributed.                │
│                                                                             │
│   Lazy Migration Pattern                                                    │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │  // Version field in each document                                  │   │
│   │  {                                                                  │   │
│   │    "_id": "user123",                                                │   │
│   │    "_v": 2,                                                         │   │
│   │    "email": "user@example.com",                                     │   │
│   │    "phone": "+1234567890"  // Added in v2                           │   │
│   │  }                                                                  │   │
│   │                                                                     │   │
│   │  // Read code handles all versions                                  │   │
│   │  function getUser(id) {                                             │   │
│   │    const doc = db.users.findOne({_id: id});                         │   │
│   │    if (doc._v < 2) {                                                │   │
│   │      doc.phone = doc.phone || null;                                 │   │
│   │      doc._v = 2;                                                    │   │
│   │      db.users.updateOne({_id: id}, doc);  // Lazy upgrade           │   │
│   │    }                                                                │   │
│   │    return doc;                                                      │   │
│   │  }                                                                  │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Problems with Lazy Migration                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Never-read documents never upgrade                               │   │
│   │  • Code must handle all historical versions forever                 │   │
│   │  • Queries must account for missing/different fields                │   │
│   │  • Testing matrix explodes with version combinations                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Better Approach: Batch Migration                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. Deploy code that handles v1 and v2                              │   │
│   │  2. Run background job to upgrade all v1 → v2                       │   │
│   │  3. Wait for migration to complete                                  │   │
│   │  4. Deploy code that only handles v2                                │   │
│   │  5. Remove v1 handling code                                         │   │
│   │                                                                     │   │
│   │  This is identical to SQL migrations, just less tooling support.    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## How Database Choices Evolve Over Time

### The Evolution Pattern

Most systems follow a predictable database evolution:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DATABASE EVOLUTION TIMELINE                              │
│                                                                             │
│   Phase 1: Early Stage (0 → 100K users)                                     │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Architecture:                                                      │   │
│   │    [App] ──→ [Single PostgreSQL]                                    │   │
│   │                                                                     │   │
│   │  Characteristics:                                                   │   │
│   │    • Everything in one database                                     │   │
│   │    • Simple to develop and debug                                    │   │
│   │    • No replication complexity                                      │   │
│   │    • Backups are straightforward                                    │   │
│   │                                                                     │   │
│   │  Staff guidance: Don't over-engineer. PostgreSQL is enough.         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Phase 2: Growth (100K → 1M users)                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Architecture:                                                      │   │
│   │    [App] ──→ [Redis Cache] ──→ [PostgreSQL Primary]                 │   │
│   │                                    ↓                                │   │
│   │                               [Read Replicas]                       │   │
│   │                                                                     │   │
│   │  What changed:                                                      │   │
│   │    • Added Redis for session/cache                                  │   │
│   │    • Added read replicas for query load                             │   │
│   │    • Connection pooling becomes critical                            │   │
│   │    • Query optimization matters                                     │   │
│   │                                                                     │   │
│   │  Staff guidance: Cache and replicas before sharding.                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Phase 3: Scale (1M → 10M users)                                           │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Architecture:                                                      │   │
│   │    [App] ──→ [Redis Cluster]                                        │   │
│   │         ├──→ [PostgreSQL] (users, orders, accounts)                 │   │
│   │         ├──→ [Elasticsearch] (search)                               │   │
│   │         └──→ [Cassandra] (events, feeds)                            │   │
│   │                                                                     │   │
│   │  What changed:                                                      │   │
│   │    • Specialized databases for specialized workloads                │   │
│   │    • Search moved to Elasticsearch                                  │   │
│   │    • High-write data moved to Cassandra                             │   │
│   │    • PostgreSQL focused on transactional data                       │   │
│   │                                                                     │   │
│   │  Staff guidance: Use the right tool for each job.                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Phase 4: Massive Scale (10M+ users)                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Architecture:                                                      │   │
│   │    [App] ──→ [Redis Cluster] (cache, rate limiting)                 │   │
│   │         ├──→ [Vitess/Citus] (sharded PostgreSQL)                    │   │
│   │         ├──→ [Elasticsearch Cluster] (search)                       │   │
│   │         ├──→ [Cassandra/Bigtable] (events, logs)                    │   │
│   │         ├──→ [Kafka] (event streaming)                              │   │
│   │         └──→ [Data Warehouse] (analytics)                           │   │
│   │                                                                     │   │
│   │  What changed:                                                      │   │
│   │    • PostgreSQL sharded or moved to NewSQL                          │   │
│   │    • Event-driven architecture for decoupling                       │   │
│   │    • Separate OLTP and OLAP systems                                 │   │
│   │    • Multi-region deployment                                        │   │
│   │                                                                     │   │
│   │  Staff guidance: This is where distributed systems expertise        │   │
│   │                  becomes essential.                                 │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Migration Strategies

When evolving databases, you need a migration strategy:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DATABASE MIGRATION STRATEGIES                            │
│                                                                             │
│   Strategy 1: Strangler Fig (Gradual Migration)                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │  Before:   [App] ──────────────────→ [Old DB]                       │   │
│   │                                                                     │   │
│   │  During:   [App] ───→ [Router] ───→ [Old DB]                        │   │
│   │                           ├───────→ [New DB] (new features)         │   │
│   │                           └───────→ [Sync] (dual writes)            │   │
│   │                                                                     │   │
│   │  After:    [App] ──────────────────→ [New DB]                       │   │
│   │                                                                     │   │
│   │  Pros: Zero downtime, reversible, gradual risk                      │   │
│   │  Cons: Dual-write complexity, longer timeline                       │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Strategy 2: Blue-Green (Cutover)                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │  Prepare:  [Old DB] ───sync───→ [New DB]                            │   │
│   │                                                                     │   │
│   │  Cutover:  [App] ─── switch ──→ [New DB]                            │   │
│   │                  (at low-traffic moment)                            │   │
│   │                                                                     │   │
│   │  Pros: Clean cutover, simpler sync logic                            │   │
│   │  Cons: Requires maintenance window, harder to rollback              │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Strategy 3: Shadow Mode (Validation)                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │            [App] ──────────────────→ [Old DB] (primary)             │   │
│   │              │                                                      │   │
│   │              └── async ──→ [New DB] (shadow, read-only)             │   │
│   │                               │                                     │   │
│   │                               ▼                                     │   │
│   │                        [Compare Results]                            │   │
│   │                                                                     │   │
│   │  Run both databases, compare results, build confidence              │   │
│   │  Then switch when new DB proves correct                             │   │
│   │                                                                     │   │
│   │  Pros: High confidence, catches edge cases                          │   │
│   │  Cons: Double the infrastructure cost during validation             │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Real Evolution Example: Feed System

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FEED SYSTEM DATABASE EVOLUTION                           │
│                                                                             │
│   Year 1: Simple Start                                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  PostgreSQL:                                                        │   │
│   │    posts (id, user_id, content, created_at)                         │   │
│   │    follows (follower_id, followed_id)                               │   │
│   │                                                                     │   │
│   │  Feed query:                                                        │   │
│   │    SELECT * FROM posts                                              │   │
│   │    WHERE user_id IN (SELECT followed_id FROM follows WHERE ...)     │   │
│   │    ORDER BY created_at DESC LIMIT 100                               │   │
│   │                                                                     │   │
│   │  Works fine for 10K users.                                          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Year 2: Performance Problems                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Problem: Feed query takes 500ms+ for users following 500+ people   │   │
│   │                                                                     │   │
│   │  Solution: Add Redis caching                                        │   │
│   │    • Cache feed results for 5 minutes                               │   │
│   │    • Invalidate on new posts from followed users                    │   │
│   │                                                                     │   │
│   │  Works fine for 100K users.                                         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Year 3: Scale Challenges                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Problem: 1M users, 10K posts/minute. Cache invalidation storms.    │   │
│   │                                                                     │   │
│   │  Solution: Fan-out on write                                         │   │
│   │    • Pre-compute feeds in Redis (sorted sets)                       │   │
│   │    • When Alice posts, push to all followers' feeds                 │   │
│   │    • PostgreSQL remains source of truth                             │   │
│   │                                                                     │   │
│   │  Works fine for 1M users, but Redis memory is expensive.            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Year 4: Hybrid Architecture                                               │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Problem: Redis costs exploding. Celebrity problem (1M followers).  │   │
│   │                                                                     │   │
│   │  Solution: Tiered storage                                           │   │
│   │    • Active users: Redis (pre-computed feeds)                       │   │
│   │    • Inactive users: Cassandra (fan-out on write)                   │   │
│   │    • Celebrities: Fan-out on read (don't push to 1M feeds)          │   │
│   │    • PostgreSQL: Posts source of truth + metadata                   │   │
│   │                                                                     │   │
│   │  Four databases, but each doing what it's best at.                  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Key Insight: This evolution was driven by specific problems.              │
│                Don't jump to Year 4 architecture on Day 1.                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 6.5: Mental Models and One-Liners

Staff Engineers internalize decision frameworks as memorable one-liners. These accelerate judgment under pressure and make reasoning teachable.

## Database Selection One-Liners

| One-Liner | When to Use |
|-----------|-------------|
| "Access patterns first, technology second." | Before naming any database. |
| "PostgreSQL until you have a reason not to." | Default choice for transactional data. |
| "Every database you add is another system to operate." | Justifying tool consolidation. |
| "Schema-less usually means schema spread across application code." | Pushing back on document-store enthusiasm. |
| "The partition key is the contract. Get it wrong once, pay forever." | Wide-column and key-value design. |
| "What breaks first?" | Scale and failure-mode analysis. |
| "Fail-open for guards, fail-safe for money." | Rate limiters vs. payment systems. |
| "Cache is a performance optimization until it becomes your source of truth." | Avoiding cache-as-primary mistakes. |
| "Sharding is the last resort, not the first step." | Resisting premature sharding. |
| "Boring is a feature." | Choosing battle-tested over novel. |
| "If you can't trace it, you're guessing." | Advocating for distributed tracing. |
| "Uniform distribution is an assumption, not a guarantee." | Designing for hot-partition skew. |

## First Bottleneck Analysis

Staff Engineers ask: "At 10× scale, what breaks first?" Not "will it scale?"—but *what specifically* fails.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FIRST BOTTLENECK BY DATABASE TYPE                         │
│                                                                             │
│   PostgreSQL (single node)                                                   │
│   • FIRST: Connection pool (hits at ~500–1000 connections)                   │
│   • THEN: Write throughput (~10–50K writes/sec)                            │
│   • THEN: Disk I/O (large tables, index maintenance)                         │
│                                                                             │
│   Redis                                                                     │
│   • FIRST: Memory (eviction or OOM)                                         │
│   • THEN: Single-threaded CPU (commands block)                             │
│   • THEN: Network (replication, clients)                                   │
│                                                                             │
│   Cassandra / Wide-column                                                   │
│   • FIRST: Hot partition (bad partition key)                                │
│   • THEN: Compaction lag (read amplification)                               │
│   • THEN: Tombstone accumulation (deletes/updates)                         │
│                                                                             │
│   L6 Question: "For our specific workload, which of these do we hit first?" │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Scale Analysis: Growth Over Years

Staff Engineers model *when* bottlenecks appear, not just *what* they are. Growth is rarely linear; first bottlenecks often hit in a predictable sequence:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SCALE OVER YEARS: TYPICAL BOTTLENECK SEQUENCE             │
│                                                                             │
│   Year 1 (0–100K users)                                                     │
│   • Architecture: Single PostgreSQL, maybe Redis for sessions                │
│   • First bottleneck: Usually NONE (underprovisioned from day 1 is rare)     │
│   • Risk: Over-engineering (sharding too early)                             │
│   • Staff action: Right-size, don't over-build                              │
│                                                                             │
│   Year 2 (100K–1M users)                                                    │
│   • First bottleneck: Connection pool (often first)                         │
│   • Second: Missing indexes (slow queries at scale)                          │
│   • Next: Read replica needed (separate read/write load)                    │
│   • Staff action: Add connection pooling, read replicas, caching            │
│                                                                             │
│   Year 3 (1M–10M users)                                                     │
│   • First bottleneck: Disk I/O (write rate, vacuum, compaction)              │
│   • Second: Single-node write throughput limit                              │
│   • Next: Hot partition (if using distributed DB)                            │
│   • Staff action: Functional partitioning, move hot data to specialized     │
│                   stores (e.g., events to Cassandra)                        │
│                                                                             │
│   Year 4+ (10M+ users)                                                      │
│   • First bottleneck: Sharding or NewSQL needed                              │
│   • Second: Multi-region (latency, compliance)                               │
│   • Staff action: Architectural change—sharding, geo-partitioning,          │
│                   event-driven sync. Requires 3–6 month project.             │
│                                                                             │
│   Key: "First bottleneck" = what breaks first at that scale.                │
│        Plan capacity 6–12 months before you hit it.                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Scale transition diagram**: Growth over years rarely hits all limits at once. Staff Engineers map: Year 1 → first bottleneck (often connections or cache size). Year 2 → second (often write throughput or disk). Year 3+ → architectural change (sharding, functional split). Plan evolution, not just current state.

---

# Part 7: Summary Diagrams

## Database Selection Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DATABASE SELECTION DECISION TREE                         │
│                                                                             │
│                          START                                              │
│                            │                                                │
│                            ▼                                                │
│                ┌──────────────────────┐                                     │
│                │  Need ACID across    │                                     │
│                │  multiple records?   │                                     │
│                └──────────────────────┘                                     │
│                     │            │                                          │
│                    YES          NO                                          │
│                     │            │                                          │
│                     ▼            ▼                                          │
│        ┌────────────────┐      ┌────────────────┐                           │
│        │ Scale > 10TB   │      │  Access pattern│                           │
│        │ or > 100K w/s? │      │  is key-value? │                           │
│        └────────────────┘      └────────────────┘                           │
│           │         │             │        │                                │
│          YES       NO             YES       NO                              │
│           │         │             │         │                               │
│           ▼         ▼             ▼         ▼                               │
│   ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐                   │
│   │ NewSQL   │ │PostgreSQL│ │Key-Value │ │Need secondary│                   │
│   │(Spanner, │ │ MySQL    │ │(Redis,   │ │   queries?   │                   │
│   │CockroachDB)│          │ │DynamoDB) │ └──────────────┘                   │
│   └──────────┘ └──────────┘ └──────────┘      │     │                       │
│                                              YES    NO                      │
│                                               │     │                       │
│                                               ▼     ▼                       │
│                                     ┌──────────┐ ┌───────-───┐              │
│                                     │Document  │ │Wide-Column|              │
│                                     │(MongoDB, │ │(Cassandra,│              │
│                                     │Firestore)│ │Bigtable)  │              │
│                                     └──────────┘ └──────────-┘              │
│                                                                             │
│   Legend:                                                                   │
│     w/s = writes per second                                                 │
│     Secondary queries = queries by non-primary-key fields                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Read/Write Path Architectures

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    COMMON READ/WRITE ARCHITECTURES                          │
│                                                                             │
│   Pattern 1: Simple (Most Applications)                                     │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │    Client ──→ App Server ──→ Connection Pool ──→ PostgreSQL         │   │
│   │                                                                     │   │
│   │    All reads and writes go to single database.                      │   │
│   │    Good for: < 1M users, < 10K requests/second                      │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Pattern 2: Read Replicas                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │    Client ──→ App Server ──┬──(writes)──→ Primary                   │   │
│   │                            │                  │                     │   │
│   │                            └──(reads)───→ Replicas                  │   │
│   │                                                                     │   │
│   │    Writes to primary, reads distributed to replicas.                │   │
│   │    Note: Replication lag means eventual consistency for reads.      │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Pattern 3: Cache Layer                                                    │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │    Client ──→ App Server ──→ Redis Cache ──(miss)──→ Database       │   │
│   │                    │              ▲                                 │   │
│   │                    │              │                                 │   │
│   │                    └──(writes)────┴────────────────→ Database       │   │
│   │                                                                     │   │
│   │    Reads check cache first. Writes update database and invalidate.  │   │
│   │    Strategies: Write-through, write-behind, read-through.           │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Pattern 4: CQRS (Command Query Responsibility Segregation)                │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │    Client ──→ App Server ──┬──(commands)──→ Write DB (PostgreSQL)   │   │
│   │                            │                      │                 │   │
│   │                            │                      ▼ (events)        │   │
│   │                            │               [Event Bus/Kafka]        │   │
│   │                            │                      │                 │   │
│   │                            └──(queries)────→ Read DB (Elasticsearch,│   │
│   │                                              Denormalized views)    │   │
│   │                                                                     │   │
│   │    Separate read and write models. Eventual consistency.            │   │
│   │    Good for: Complex queries on write-heavy data.                   │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Scaling Evolution Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SCALING EVOLUTION PATHS                                  │
│                                                                             │
│   Users        Architecture Evolution                                       │
│   ─────────────────────────────────────────────────────────────────────     │
│                                                                             │
│   10K    ┌─────────┐                                                        │
│          │ Single  │  ← Start here. Always.                                 │
│          │   DB    │                                                        │
│          └─────────┘                                                        │
│               │                                                             │
│               ▼                                                             │
│   100K   ┌─────────┐    ┌─────────┐                                         │
│          │ Primary │───→│ Replica │  ← Add read replicas                    │
│          └─────────┘    └─────────┘                                         │
│               │                                                             │
│               ▼                                                             │
│   500K   ┌─────────┐    ┌─────────┐    ┌─────────┐                          │
│          │ Primary │───→│Replicas │←───│  Redis  │  ← Add caching           │
│          └─────────┘    └─────────┘    │  Cache  │                          │
│               │                        └─────────┘                          │
│               ▼                                                             │
│   1M     ┌─────────┐    ┌─────────┐    ┌─────────┐                          │
│          │ Primary │    │Replicas │    │  Redis  │                          │
│          └─────────┘    └─────────┘    └─────────┘                          │
│               │              │                                              │
│               │    ┌─────────────────┐                                      │
│               └───→│  Elasticsearch  │  ← Offload search                    │
│                    └─────────────────┘                                      │
│                                                                             │
│   5M          ┌──────────────────────────────────────┐                      │
│               │     Functional Partitioning          │                      │
│               │                                      │                      │
│               │  ┌────────┐  ┌─────────┐  ┌───────┐  │                      │
│               │  │  PG 1  │  │  PG 2   │  │Cassan-│  │  ← Separate DBs      │
│               │  │ Users  │  │ Orders  │  │ dra   │  │    by domain         │
│               │  └────────┘  └─────────┘  │Events │  │                      │
│               │                           └───────┘  │                      │
│               └──────────────────────────────────────┘                      │
│                                                                             │
│   10M+        ┌──────────────────────────────────────┐                      │
│               │     Horizontal Sharding              │                      │
│               │                                      │                      │
│               │  ┌────────┐  ┌────────┐  ┌────────┐  │                      │
│               │  │Shard 1 │  │Shard 2 │  │Shard N │  │  ← Shard each        │
│               │  │ A-L    │  │ M-Z    │  │  ...   │  │    database          │
│               │  └────────┘  └────────┘  └────────┘  │                      │
│               │                                      │                      │
│               │  (or migrate to Spanner/CockroachDB) │                      │
│               └──────────────────────────────────────┘                      │
│                                                                             │
│   Key: Each step adds complexity. Don't jump ahead.                         │
│        Solve today's problem, not tomorrow's hypothetical.                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 8: Staff-Level Deep Dives

This section covers topics that separate L6 thinking from L5 thinking. These are areas where strong Senior engineers often have gaps, and where Staff Engineers demonstrate system-wide ownership.

## Blast Radius Containment for Database Decisions

**What is blast radius?** The scope of impact when something fails. A Staff Engineer's job is to minimize blast radius through architectural choices.

### Why Blast Radius Matters for Database Selection

Every database you add is a potential failure domain. Every dependency you create is a blast radius you must contain.

**A Real-World Story**: At a fintech company, a single PostgreSQL database stored everything—user accounts, transaction logs, audit records, and real-time analytics. One day, an analytics query locked a critical table for 45 seconds. During that time:
- No users could log in (authentication table locked)
- No payments could process (transaction table waiting)
- The mobile app showed spinning loaders for 2 million users
- Customer support was flooded with calls
- Revenue loss: estimated $50,000 for that single incident

The root cause wasn't the query—it was the architectural decision to share one database across unrelated workloads. A slow analytics query should never block a payment.

**The lesson**: Blast radius is not about preventing failures (failures happen). It's about limiting how far they spread.

Consider this analogy: On a ship, watertight compartments ensure that a hole in one section doesn't sink the entire vessel. Your database architecture should have similar compartmentalization.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    BLAST RADIUS ANALYSIS                                    │
│                                                                             │
│   Single Database (Maximum Blast Radius)                                    │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │       [Service A]  [Service B]  [Service C]  [Service D]            │   │
│   │            │            │            │            │                 │   │
│   │            └────────────┴─────┬──────┴────────────┘                 │   │
│   │                               │                                     │   │
│   │                               ▼                                     │   │
│   │                     ┌─────────────────┐                             │   │
│   │                     │   PostgreSQL    │  ← Single point of failure  │   │
│   │                     └─────────────────┘                             │   │
│   │                                                                     │   │
│   │   When PostgreSQL fails: ALL services fail                          │   │
│   │   Blast radius: 100%                                                │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Contained Blast Radius (Better)                                           │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   [Critical Path]           [Non-Critical Path]                     │   │
│   │        │                           │                                │   │
│   │        ▼                           ▼                                │   │
│   │   [PostgreSQL]              [Cassandra]                             │   │
│   │   ↓ (with fallback)         ↓ (degraded mode)                       │   │
│   │   [Redis Cache]             [Redis Cache]                           │   │
│   │                                                                     │   │
│   │   When PostgreSQL fails:                                            │   │
│   │     • Critical path degrades to cache-only (stale reads OK)         │   │
│   │     • Non-critical path unaffected                                  │   │
│   │   Blast radius: 50% (and degraded, not dead)                        │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Staff-Level Blast Radius Questions

When choosing a database, ask:

1. **What happens to upstream services if this database fails?**
   - Can they degrade gracefully?
   - Do they have timeouts and circuit breakers?
   - What's the user experience during failure?

2. **What happens to downstream services?**
   - Does failure cascade to dependent systems?
   - Are there fallback data sources?

3. **How do we detect and contain failure?**
   - Health checks with appropriate granularity
   - Automatic failover vs manual intervention
   - Alerting thresholds

4. **What's the blast radius of a bad deploy?**
   - Schema migrations that lock tables
   - Index changes that cause timeouts
   - Configuration changes that affect capacity

### Real Example: Notification System Blast Radius

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    NOTIFICATION SYSTEM BLAST RADIUS DESIGN                  │
│                                                                             │
│   Requirements:                                                             │
│   • Send push/email/SMS notifications                                       │
│   • Store notification preferences                                          │
│   • Track delivery status                                                   │
│   • Handle 100K notifications/minute                                        │
│                                                                             │
│   L5 Design (Shared Database):                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   [Notification Service] ──────→ [PostgreSQL]                       │   │
│   │          │                        • preferences                     │   │
│   │          │                        • notification_log                │   │
│   │          ▼                        • delivery_status                 │   │
│   │   [Push/Email/SMS]                                                  │   │
│   │                                                                     │   │
│   │   Problem: notification_log writes (100K/min) compete with          │   │
│   │            preference reads. Log table growth slows everything.     │   │
│   │   Blast radius: Log backup → preferences unreadable → no delivery   │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   L6 Design (Contained Blast Radius):                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   [Notification Service]                                            │   │
│   │          │                                                          │   │
│   │   ┌──────┼──────┬──────────────────┐                                │   │
│   │   │      │      │                  │                                │   │
│   │   ▼      ▼      ▼                  ▼                                │   │
│   │  [PG]  [Redis] [Cassandra]    [Kafka → ...]                         │   │
│   │  prefs  cache   logs           analytics                            │   │
│   │                                                                     │   │
│   │   • PostgreSQL: Small, stable, preferences only                     │   │
│   │   • Redis: Cache preferences, handle PG blips                       │   │
│   │   • Cassandra: High-write log storage, can lag                      │   │
│   │   • Kafka: Async analytics, can buffer                              │   │
│   │                                                                     │   │
│   │   Blast radius:                                                     │   │
│   │   • Cassandra fails → Notifications still send (logs lost)          │   │
│   │   • Redis fails → Slower, but PostgreSQL handles it                 │   │
│   │   • PostgreSQL fails → Redis cache serves preferences (stale OK)    │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Key L6 Insight: The L6 design has MORE databases but LESS blast radius.   │
│                   Complexity is justified by isolation.                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Cascading Failures Between Databases

One of the most dangerous failure patterns is when one database failure triggers failures in others. Unlike a simple outage where one component fails, cascading failures create a domino effect that can take down your entire system in minutes.

### Understanding Cascading Failures

**Why cascading failures are so dangerous**: A single component failure is predictable—you lose that component's functionality. A cascading failure is multiplicative—one failure causes two, which cause four, which cause eight. By the time you understand what's happening, your entire system may be down.

**Real-World Incident**: A social media company experienced this in 2019. Their Redis cache cluster had a network blip lasting only 3 seconds. Here's what happened next:

1. **T+0 seconds**: Redis unreachable for 3 seconds
2. **T+3 seconds**: 50,000 requests/second suddenly hit PostgreSQL directly
3. **T+5 seconds**: PostgreSQL connection pool (max 500 connections) exhausted
4. **T+8 seconds**: All services waiting for PostgreSQL connections, requests timing out
5. **T+15 seconds**: Load balancer health checks failing, servers marked unhealthy
6. **T+30 seconds**: Auto-scaler spins up new servers, which immediately overwhelm PostgreSQL further
7. **T+60 seconds**: Complete outage across all services

The 3-second Redis blip caused a 47-minute outage. This is the nature of cascading failures—they amplify small problems into catastrophic ones.

### Cascading Failure Timeline: A Step-by-Step Breakdown

Understanding cascading failures requires seeing them as a sequence of phases. Each phase creates conditions for the next, turning a small problem into a system-wide outage. Here's the structured timeline that Staff Engineers use to analyze and prevent cascades:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CASCADING FAILURE TIMELINE STRUCTURE                     │
│                                                                             │
│   PHASE 1: TRIGGER (T+0 to T+5 seconds)                                     │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   Initial failure event:                                            │   │
│   │   • Component fails (network blip, node crash, overload)            │   │
│   │   • Duration: Usually seconds (3-5 seconds typical)                 │   │
│   │   • Impact: Direct users of that component affected                 │   │
│   │                                                                     │   │
│   │   Example: Redis cluster network partition for 3 seconds            │   │
│   │   • Cache misses spike from 5% to 100%                              │   │
│   │   • Requests that hit Redis fail                                    │   │
│   │   • But: Most requests retry or fall back to database               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   PHASE 2: PROPAGATION (T+5 to T+30 seconds)                                │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   Failure spreads to dependent systems:                             │   │
│   │   • Downstream systems receive unexpected load                      │   │
│   │   • Resource exhaustion begins (connections, memory, CPU)           │   │
│   │   • Latency increases as systems struggle                           │   │
│   │                                                                     │   │
│   │   Example: PostgreSQL receives 20× normal load                      │   │
│   │   • Connection pool fills (500 → 500/500 in seconds)                │   │
│   │   • Query latency increases (10ms → 500ms → timeout)                │   │
│   │   • CPU spikes to 95%+                                              │   │
│   │   • Replication lag increases (replicas can't keep up)              │   │
│   │                                                                     │   │
│   │   Key insight: This phase is where containment should happen,       │   │
│   │                but often doesn't because monitoring lags reality.   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   PHASE 3: USER-VISIBLE IMPACT (T+30 to T+120 seconds)                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   End users begin experiencing failures:                            │   │
│   │   • Request timeouts (30s+ wait times)                              │   │
│   │   • Error rates spike (5xx responses)                               │   │
│   │   • Partial functionality loss                                      │   │
│   │   • Health checks fail, load balancers mark services unhealthy      │   │
│   │                                                                     │   │
│   │   Example: User profile service becomes unavailable                 │   │
│   │   • All requests timeout (waiting for PostgreSQL)                   │   │
│   │   • Health checks fail → load balancer stops routing                │   │
│   │   • Auto-scaler sees "unhealthy" → spins up MORE servers            │   │
│   │   • New servers immediately hit same overloaded database            │   │
│   │   • Cascade amplifies: more servers = more load = worse failure     │   │
│   │                                                                     │   │
│   │   Staff Engineer insight: Auto-scaling during cascades makes        │   │
│   │                           things worse. Need circuit breakers.      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   PHASE 4: CONTAINMENT (T+120 seconds to T+300+ seconds)                    │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   Human intervention or automated systems begin recovery:           │   │
│   │   • On-call engineer pages                                          │   │
│   │   • Root cause identified (often takes 5-10 minutes)                │   │
│   │   • Mitigation applied (circuit breakers, load shedding, failover)  │   │
│   │   • Systems begin recovery                                          │   │
│   │                                                                     │   │
│   │   Example: Recovery actions                                         │   │
│   │   • Enable circuit breaker on PostgreSQL (fail fast, don't wait)    │   │
│   │   • Shed non-critical load (analytics, background jobs)             │   │
│   │   • Promote read replica to handle some read traffic                │   │
│   │   • Gradually restore full functionality                            │   │
│   │                                                                     │   │
│   │   Total outage duration: 47 minutes                                 │   │
│   │   • 3 seconds: Initial trigger                                      │   │
│   │   • 27 seconds: Propagation and amplification                       │   │
│   │   • 90 seconds: User-visible impact                                 │   │
│   │   • 45 minutes: Containment and recovery                            │   │
│   │                                                                     │   │
│   │   L6 Prevention: Design systems to contain in Phase 2, not Phase 4. │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Why this structure matters**: Staff Engineers use this timeline to design prevention mechanisms at each phase:

- **Phase 1 (Trigger)**: Can't prevent all triggers, but can detect them quickly
- **Phase 2 (Propagation)**: This is where containment MUST happen. Circuit breakers, rate limiting, load shedding
- **Phase 3 (User Impact)**: Too late for prevention, but graceful degradation can limit damage
- **Phase 4 (Containment)**: Runbooks and automation reduce recovery time

**The Staff Engineer question**: "At which phase does my system detect and contain this failure?" If the answer is Phase 3 or 4, you're designing reactively. If it's Phase 2, you're designing proactively.

### Structured Incident: Database Migration Lockout

When no structured incident exists in a section, Staff Engineers create one. Here is a database-specific incident in the prescribed format:

| Section | Content |
|---------|---------|
| **Context** | A B2B SaaS platform with 2M users. Single PostgreSQL instance for core data (users, subscriptions, billing). Team planned a schema migration to add an index on `subscriptions.company_id` for a new analytics feature. Staging had 10K rows; production had 45M rows. |
| **Trigger** | Engineer ran `CREATE INDEX CONCURRENTLY idx_subscriptions_company ON subscriptions(company_id)` at 2 PM. Staging completed in 8 seconds. Production began at 2:01 PM. |
| **Propagation** | Index build held AccessShareLock (non-blocking reads) but triggered heavy I/O. At 2:15 PM, disk I/O saturated. Query latency climbed from 15ms to 2.5s. Connection pool exhausted by 2:22 PM. Writes began failing. Health checks failed. Load balancer marked primary unhealthy. |
| **User impact** | 47 minutes of degraded service. Login failures, checkout timeouts, API 5xx errors. ~15,000 affected sessions. Estimated revenue impact: $80K. Customer support inundated. |
| **Engineer response** | On-call paged at 2:25 PM. Initially suspected primary failure. Checked disk I/O—saturated. Identified long-running index build. Decision: cancel index build (cannot roll back CONCURRENTLY mid-build without leaving invalid index). Let build complete (estimated 2 more hours) or kill it. Killed build. Disk I/O recovered in 8 minutes. Full recovery by 3:12 PM. |
| **Root cause** | Migration tested only on staging scale. No estimation of index build time on production data size. No load shedding or migration window. Index build on 45M rows wrote 12GB of index data, overwhelming shared disk. |
| **Design change** | 1) All migrations require production-size data test and time estimate. 2) Index builds run in maintenance window with load shedding. 3) Use `pg_stat_progress_create_index` for visibility. 4) Consider online index creation tools for large tables. 5) Add disk I/O to migration runbook checks. |
| **Lesson learned** | "Works in staging" is not a migration validation. Production data volume and I/O characteristics differ by orders of magnitude. Staff Engineers mandate: estimate migration duration on production-scale data before running in production. |

**Staff insight**: This incident format (Context | Trigger | Propagation | User impact | Engineer response | Root cause | Design change | Lesson learned) is reusable for post-mortems and interview calibration. Memorize it.

### Structured Incident: Hot Partition Meltdown

A second incident illustrates a different failure class—not migration, but partition key design:

| Section | Content |
|---------|---------|
| **Context** | A social analytics platform stored event counts in a wide-column store, partitioned by `(date, event_type)`. Daily active users (DAU) were computed by scanning partitions. The system served 5M DAU with 50M events/day. |
| **Trigger** | A viral campaign drove 10× normal traffic to a single event type ("campaign_click"). All writes for that type hit one partition: `(2024-01-15, campaign_click)`. |
| **Propagation** | The partition's node reached 100% CPU. Writes to that partition timed out. The application retried, increasing load. Other partitions on the same node (shared machine) became slow. Within 15 minutes, the entire node was unresponsive. Replication could not keep up. |
| **User impact** | 30 minutes of missing analytics for the campaign. Client dashboards showed stale data. No core product outage, but the marketing team could not measure campaign performance. |
| **Engineer response** | On-call identified the hot partition via per-partition metrics. Temporarily rate-limited writes to the hot key. Added salting to the partition key: `(date, event_type, hash(user_id) % 16)`. Deployed partition key change over 2 days. |
| **Root cause** | Partition key designed for uniform distribution assumed all event types would have similar volume. No consideration for power-law or viral skew. No hot-partition detection or rate limiting. |
| **Design change** | 1) All partition keys must include a salt or high-cardinality dimension for high-volume entities. 2) Per-partition metrics and alerting (skew ratio > 2). 3) Rate limiting on hot keys as circuit breaker. 4) Capacity planning assumes 10× skew for viral events. |
| **Lesson learned** | "Uniform distribution" is an assumption, not a guarantee. Staff Engineers design partition keys for worst-case skew, not average-case. |

### Pattern 1: Thundering Herd on Cache Miss

The thundering herd problem occurs when a cache failure causes all requests to simultaneously hit the backend database. Let's walk through exactly how this happens and why it's so destructive.

**Normal operation**: Imagine you have 1,000 requests per second hitting your user profile service. With a 95% cache hit rate, only 50 requests per second actually reach PostgreSQL. Your database is sized for ~100 requests per second, so you have comfortable headroom.

**When cache fails**: Suddenly, all 1,000 requests per second hit PostgreSQL. That's 20× your normal load, hitting instantaneously. PostgreSQL doesn't gracefully handle this—it tries to serve all requests, slows down under load, timeouts cascade, connection pools fill up, and soon every service sharing that database is affected.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    THUNDERING HERD CASCADE                                  │
│                                                                             │
│   Normal Operation:                                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   [1000 requests/sec] ──→ [Redis] ──(5% miss)──→ [PostgreSQL]       │   │
│   │                            95% hit                 50 req/sec       │   │
│   │                                                    (handles fine)   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Redis Failure:                                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   [1000 requests/sec] ──→ [Redis ✗] ──(100% miss)──→ [PostgreSQL]   │   │
│   │                                                       1000 req/sec  │   │
│   │                                                       (overloaded!) │   │
│   │                                                             │       │   │
│   │                               ┌─────────────────────────────┘       │   │
│   │                               ▼                                     │   │
│   │                          [PG Timeout]                               │   │
│   │                               │                                     │   │
│   │                               ▼                                     │   │
│   │                       [Connection Pool                              │   │
│   │                        Exhausted]                                   │   │
│   │                               │                                     │   │
│   │                               ▼                                     │   │
│   │                   [All Services Using PG Fail]                      │   │
│   │                                                                     │   │
│   │   Cascade: Redis → PostgreSQL → ALL dependent services              │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Prevention (L6 Approach):                                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   1. Rate limiting on database connections (shed load)              │   │
│   │   2. Request coalescing (one fetch per key during miss)             │   │
│   │   3. Stale-while-revalidate (serve old cache, async refresh)        │   │
│   │   4. Circuit breaker (fail fast when PG is overwhelmed)             │   │
│   │   5. Separate connection pools per service (contain blast)          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Failure Propagation Path: Visualizing the Cascade

Staff Engineers visualize failure propagation to understand blast radius and design containment:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FAILURE PROPAGATION PATH DIAGRAM                         │
│                                                                             │
│   Initial Trigger: Redis Network Partition (3 seconds)                      │
│                                                                             │
│   T+0s:  [Redis Cluster] ✗ Network partition                                │
│          │                                                                  │
│          │ All cache requests fail                                          │
│          ▼                                                                  │
│   T+1s:  [API Service] Cache miss rate: 5% → 100%                           │
│          │                                                                  │
│          │ Fallback: Hit database directly                                  │
│          ▼                                                                  │
│   T+3s:  [PostgreSQL] Request rate: 50/sec → 1000/sec (20× spike)           │
│          │                                                                  │
│          │ Connection pool: 200/500 → 500/500 (exhausted)                   │
│          │ Query latency: 10ms → 500ms → timeout                            │
│          │ CPU: 40% → 95%                                                   │
│          │                                                                  │
│          ├─→ [User Profile Service] Waiting for DB connections              │
│          │   • Requests queue (30s timeout)                                 │
│          │   • Health checks fail                                           │
│          │                                                                  │
│          ├─→ [Order Service] Waiting for DB connections                     │
│          │   • Checkout requests timeout                                    │
│          │   • Health checks fail                                           │
│          │                                                                  │
│          ├─→ [Feed Service] Waiting for DB connections                      │
│          │   • Feed generation timeout                                      │
│          │   • Health checks fail                                           │
│          │                                                                  │
│          ▼                                                                  │
│   T+15s: [Load Balancer] Health checks failing                              │
│          │                                                                  │
│          │ Marks services as unhealthy                                      │
│          │ Stops routing traffic                                            │
│          │                                                                  │
│          ├─→ [Auto-scaler] Sees "unhealthy" services                        │
│          │   • Spins up 10 new instances                                    │
│          │   • New instances immediately hit PostgreSQL                     │
│          │   • Amplifies the problem (more load)                            │
│          │                                                                  │
│          ▼                                                                  │
│   T+30s: [All Services] Complete failure                                    │
│          │                                                                  │
│          │ • User Profile Service: Down                                     │
│          │ • Order Service: Down                                            │
│          │ • Feed Service: Down                                             │
│          │ • All dependent services: Down                                   │
│          │                                                                  │
│          ▼                                                                  │
│   T+60s: [On-Call Engineer] Paged                                           │
│          │                                                                  │
│          │ Identifies root cause (PostgreSQL overload)                      │
│          │ Enables circuit breaker (fail fast, don't wait)                  │
│          │                                                                  │
│          ▼                                                                  │
│   T+120s: [Recovery] Circuit breaker active                                 │
│          │                                                                  │
│          │ • Requests fail fast (no 30s wait)                               │
│          │ • PostgreSQL load decreases                                      │
│          │ • Services begin responding (with errors, but fast)              │
│          │                                                                  │
│          ▼                                                                  │
│   T+300s: [Full Recovery] Redis partition heals                             │
│          │                                                                  │
│          │ • Cache begins working                                           │
│          │ • Circuit breaker resets                                         │
│          │ • Normal operation resumes                                       │
│                                                                             │
│   Blast Radius Analysis:                                                    │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   Direct Impact:                                                    │   │
│   │   • Redis: 3-second partition (minor)                               │   │
│   │                                                                     │   │
│   │   Cascading Impact:                                                 │   │
│   │   • PostgreSQL: Overloaded for 5 minutes                            │   │
│   │   • All services using PostgreSQL: Down for 2 minutes               │   │
│   │   • All users: Unable to use platform for 2 minutes                 │   │
│   │                                                                     │   │
│   │   Containment Points (L6 Design):                                   │   │
│   │   • Circuit breaker at T+60s (should be T+5s)                       │   │
│   │   • Rate limiting on database (should prevent overload)             │   │
│   │   • Graceful degradation (should serve stale cache)                 │   │
│   │                                                                     │   │
│   │   Prevention (L6 Design):                                           │   │
│   │   • Stale-while-revalidate: Serve old cache during Redis failure    │   │
│   │   • Circuit breaker: Fail fast when PostgreSQL slow                 │   │
│   │   • Rate limiting: Shed load before PostgreSQL overloads            │   │
│   │   • Monitoring: Alert on connection pool utilization (80%)          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Staff Engineer insight**: Failure propagation diagrams reveal:
- **Blast radius**: How far the failure spreads (Redis → PostgreSQL → All services)
- **Containment points**: Where to stop the cascade (circuit breaker, rate limiting)
- **Recovery time**: How long until full recovery (5 minutes in this case)
- **Prevention opportunities**: Where to add safeguards (stale cache, circuit breakers)

The key question: "At which point does my system contain this failure?" If containment happens at T+60s (human intervention), you're designing reactively. If it happens at T+5s (automated circuit breaker), you're designing proactively.

### Pattern 2: Synchronous Chain Failure

Synchronous chain failures occur when services call each other in sequence, each waiting for the next to complete. When any link in the chain slows down, everything upstream backs up like cars behind a traffic accident.

**The mathematics of synchronous chains**: If you have 3 database calls in sequence, each with a 30-second timeout, your worst-case latency is 90 seconds. But worse than the latency is the resource consumption. While waiting for that slow database, your service holds onto:
- A thread (or goroutine/connection)
- Memory for the request context
- An HTTP connection to the caller
- A database connection (if acquired before the slow part)

At 100 requests per second with 30-second timeouts, you'd need 3,000 threads just to handle the backlog. Most services crash well before that.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SYNCHRONOUS CHAIN FAILURE                                │
│                                                                             │
│   Anti-Pattern:                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   [Request] → [Service A] → [Service B] → [PostgreSQL]              │   │
│   │                   │              │                                  │   │
│   │                   ▼              ▼                                  │   │
│   │               [MongoDB]      [Redis]                                │   │
│   │                                                                     │   │
│   │   If ANY database is slow, the entire request is slow.              │   │
│   │   Default timeout: 30 seconds × 3 databases = 90 second worst case  │   │
│   │                                                                     │   │
│   │   What happens at scale:                                            │   │
│   │   • PostgreSQL slow → requests queue in Service B                   │   │
│   │   • Service B backs up → requests queue in Service A                │   │
│   │   • Service A backs up → requests queue at load balancer            │   │
│   │   • Thread pools exhaust → entire system unresponsive               │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   L6 Pattern: Timeout Budgets                                               │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   Total request budget: 500ms                                       │   │
│   │                                                                     │   │
│   │   [Request] → [Service A: 200ms budget]                             │   │
│   │                     │                                               │   │
│   │                     └──→ [Service B: 150ms remaining]               │   │
│   │                                │                                    │   │
│   │                                └──→ [PostgreSQL: 100ms]             │   │
│   │                                                                     │   │
│   │   • Each hop subtracts from remaining budget                        │   │
│   │   • If budget exhausted, fail fast (don't wait)                     │   │
│   │   • Return degraded response rather than timeout                    │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Implementing Timeout Budgets in Practice**:

Here's a concrete example of how timeout budgets work in code:

```python
class TimeoutBudget:
    def __init__(self, total_ms: int):
        self.deadline = time.time() + (total_ms / 1000)
    
    def remaining_ms(self) -> int:
        remaining = (self.deadline - time.time()) * 1000
        return max(0, int(remaining))
    
    def is_exhausted(self) -> bool:
        return self.remaining_ms() <= 0

# Usage in request handler
async def handle_feed_request(user_id: str, budget: TimeoutBudget):
    # Each downstream call uses remaining budget, not a fixed timeout
    
    # Step 1: Get user preferences (give it 30% of remaining budget)
    prefs_timeout = min(budget.remaining_ms() * 0.3, 100)  # Cap at 100ms
    try:
        preferences = await user_service.get_preferences(
            user_id, 
            timeout_ms=prefs_timeout
        )
    except TimeoutError:
        preferences = DEFAULT_PREFERENCES  # Graceful degradation
    
    if budget.is_exhausted():
        return degraded_response(preferences)
    
    # Step 2: Get feed from database
    feed_timeout = min(budget.remaining_ms() * 0.5, 200)
    try:
        feed = await feed_service.get_feed(
            user_id,
            timeout_ms=feed_timeout
        )
    except TimeoutError:
        return cached_feed_response(user_id)  # Serve stale data
    
    # Step 3: Hydrate with post details (use remaining budget)
    try:
        enriched = await enrich_posts(feed, timeout_ms=budget.remaining_ms())
    except TimeoutError:
        enriched = feed  # Return un-enriched if time runs out
    
    return full_response(enriched)
```

The key insight: **fail fast and return something useful** rather than waiting until the user gives up. A feed with slightly stale data served in 200ms is better than a timeout after 30 seconds.

### Pattern 3: Dual-Write Inconsistency

When writing to multiple databases, partial failure creates inconsistency. This is one of the most common—and most dangerous—patterns in distributed systems.

**The problem explained**: You want to write data to two places (e.g., PostgreSQL and Elasticsearch). You write to the first, then the second. What if the second write fails? Now your databases are inconsistent. What if your service crashes between the two writes? Same problem.

**Real-world example**: An e-commerce platform stores products in PostgreSQL (source of truth) and Elasticsearch (for search). A product is added to PostgreSQL successfully, but the Elasticsearch write fails due to a network timeout. Result:
- Product exists in database (you can view it by ID)
- Product doesn't exist in search (customers can't find it)
- Revenue lost until someone notices and fixes it

**The frequency**: In a system doing 1,000 writes/second with 99.9% success rate to each database:
- 1 failure per 1,000 × 2 databases = ~2 inconsistencies per second
- That's 172,800 inconsistent records per day
- This is why "just retry" isn't a solution

```python
# Anti-Pattern: Silent inconsistency
def create_user(user_data):
    # Write to PostgreSQL (succeeds)
    pg_result = postgres.insert("users", user_data)
    
    # Write to Elasticsearch (fails silently)
    try:
        es.index("users", user_data)
    except ElasticsearchException:
        logger.warning("ES write failed")  # Silent inconsistency!
    
    # Write to Redis cache (succeeds)
    redis.set(f"user:{user_data.id}", user_data)
    
    # Result: PostgreSQL and Redis have user, ES doesn't
    # Search won't find this user until next sync
    return pg_result
```

**The solution: Transactional Outbox Pattern**

Instead of writing to multiple databases directly, write to one database atomically (using a transaction), including an "outbox" entry. A background worker then reliably propagates changes to other systems.

```python
# L6 Pattern: Transactional outbox
def create_user(user_data):
    with postgres.transaction() as tx:
        # Write user
        user = tx.insert("users", user_data)
        
        # Write to outbox (same transaction)
        tx.insert("outbox", {
            "event_type": "user_created",
            "payload": user_data,
            "targets": ["elasticsearch", "redis"],
            "status": "pending"
        })
        # Transaction commits atomically
    
    # Background worker:
    # - Reads outbox
    # - Writes to ES and Redis
    # - Retries on failure
    # - Marks complete only when ALL targets succeed
    # - Guaranteed eventual consistency
    return user
```

**Why the outbox pattern works**:
1. **Atomicity**: User and outbox entry commit together or not at all
2. **Durability**: Outbox survives crashes (it's in PostgreSQL)
3. **Reliability**: Worker retries until all targets succeed
4. **Visibility**: You can query outbox for stuck entries

**The trade-off**: Eventual consistency. The user exists in PostgreSQL immediately but may take seconds to appear in search. For most use cases, this is acceptable. For the rare cases where it's not, you need distributed transactions (which have their own costs).

### Structured Incident: Dual-Write Search Index Drift

When data exists in multiple stores without a transactional outbox, silent inconsistency can accumulate into a major incident:

| Section | Content |
|---------|---------|
| **Context** | A B2C marketplace stored products in PostgreSQL (source of truth) and Elasticsearch (search). Product catalog updates were dual-written: application wrote to both PostgreSQL and Elasticsearch in sequence. On success, it cached the product in Redis. No outbox or CDC. 500K products, 10K catalog updates/day. |
| **Trigger** | A network partition during a 2-hour maintenance window caused 15% of Elasticsearch writes to fail. The application logged the error but did not retry or queue. PostgreSQL and Redis were updated; Elasticsearch was not. |
| **Propagation** | Over 2 weeks, the failure rate varied (5–20%). No alert on search index vs. DB mismatch. Customer support reported "can't find product X" but search returned nothing. Engineering assumed a search bug. |
| **User impact** | ~8% of products were in the database but not in search. Customers could not find products by name or category. Affected high-margin items. Estimated 12% drop in search-to-purchase conversion over 2 weeks. Revenue impact: ~$180K. |
| **Engineer response** | On-call received a consolidated support ticket. Ran reconciliation job: count products in PostgreSQL vs. documents in Elasticsearch. Found 42K missing. Root cause: dual-write failures with no retry. Rebuilt search index from PostgreSQL (12 hours). Deployed retry logic for failed ES writes. |
| **Root cause** | Dual-write without transactional outbox. No reconciliation or alerting on index drift. Application treated ES write failure as log-only; no retry queue. |
| **Design change** | 1) Implement transactional outbox: write product + outbox event in one PostgreSQL transaction. 2) Worker consumes outbox, writes to Elasticsearch, retries on failure. 3) Daily reconciliation job: compare counts, alert if drift > 0.1%. 4) Search index rebuilt from source of truth weekly. |
| **Lesson learned** | "Dual-write without an outbox is a time bomb. Every failure is a permanent inconsistency. Staff Engineers use transactional outbox or CDC for any cross-system writes that must eventually match." |

**Staff insight**: This incident format reinforces why the outbox pattern exists. It is not theoretical—it prevents real incidents from real dual-write failures.

---

## Capacity Planning at Staff Level

Staff Engineers don't just react to capacity problems—they predict and prevent them. This is one of the clearest differentiators between L5 and L6 thinking.

**L5 mindset**: "The database is slow. Let's add more capacity."
**L6 mindset**: "At our current growth rate, we'll hit database limits in 4 months. Let's start the capacity project now, so we have headroom when we need it."

### Why Proactive Capacity Planning Matters

**The lead time problem**: Adding database capacity isn't instant. Consider what's involved:

- **Provisioning**: 1-2 days (cloud) to 2-4 weeks (on-prem)
- **Testing**: 1-2 weeks to validate new configuration
- **Migration**: Hours to days, depending on data size
- **Stabilization**: 1-2 weeks to monitor for issues

If you wait until you're at 90% capacity, you're already in crisis mode. You don't have 4-6 weeks—you have days. This leads to rushed decisions, skipped testing, and often makes things worse.

**The cost of reactive planning**: A payment company learned this the hard way. They noticed their PostgreSQL primary was at 85% CPU during peaks but assumed they had time. Two weeks later, a marketing campaign drove 3× normal traffic. The database melted. They lost 6 hours of transaction processing capability—estimated cost: $2.3 million in delayed payments and customer trust.

If they had planned ahead, a $500/month replica could have prevented a $2.3 million incident.

### The Capacity Planning Framework

The framework below provides a systematic approach to capacity planning. Think of it as a continuous cycle, not a one-time exercise.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CAPACITY PLANNING PROCESS                                │
│                                                                             │
│   Step 1: Establish Baselines                                               │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   Metrics to track per database:                                    │   │
│   │   • Current utilization (CPU, memory, disk I/O, connections)        │   │
│   │   • Current request rate (reads/sec, writes/sec)                    │   │
│   │   • Current latency (p50, p95, p99)                                 │   │
│   │   • Growth rate (month-over-month)                                  │   │
│   │   • Seasonal patterns (daily, weekly, annual peaks)                 │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Step 2: Define Thresholds                                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   Resource         Warning      Critical     Headroom Reason        │   │
│   │   ──────────────────────────────────────────────────────────────    │   │
│   │   CPU              60%          80%          Spikes during peaks    │   │
│   │   Memory           70%          85%          OOM kills are fatal    │   │
│   │   Connections      60%          80%          Burst capacity needed  │   │
│   │   Disk I/O         50%          70%          Compaction spikes      │   │
│   │   Disk Space       60%          80%          Growth + compaction    │   │
│   │   Replication Lag  10s          60s          Failover readiness     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Step 3: Project Forward                                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   Time to threshold = (Threshold - Current) / Growth Rate           │   │
│   │                                                                     │   │
│   │   Example:                                                          │   │
│   │   • Current disk: 40% used                                          │   │
│   │   • Warning threshold: 60%                                          │   │
│   │   • Growth rate: 5% per month                                       │   │
│   │   • Time to warning: (60-40)/5 = 4 months                           │   │
│   │                                                                     │   │
│   │   Action: Plan capacity increase for month 3                        │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Step 4: Plan for Events                                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   • Marketing campaigns (2-5x normal traffic)                       │   │
│   │   • Product launches (unknown, plan for 10x)                        │   │
│   │   • Seasonal peaks (Black Friday, New Year)                         │   │
│   │   • Viral events (impossible to predict, plan for graceful shed)    │   │
│   │                                                                     │   │
│   │   L6 Approach: Pre-provision for known events.                      │   │
│   │                Design load shedding for unknown events.             │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Capacity Planning Applied: Rate Limiter Example

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    RATE LIMITER CAPACITY PLANNING                           │
│                                                                             │
│   Current State:                                                            │
│   • Redis cluster: 3 nodes, 32GB each                                       │
│   • Peak traffic: 50K req/sec                                               │
│   • Memory usage: 25% (8GB per node)                                        │
│   • Key count: 5M active rate limit keys                                    │
│   • Key size: ~100 bytes average                                            │
│                                                                             │
│   Growth Projection:                                                        │
│   • Traffic growing 20%/quarter                                             │
│   • New features adding rate limit dimensions                               │
│   │                                                                         │
│   │   Quarter     Traffic      Keys         Memory      % Used              │
│   │   ─────────────────────────────────────────────────────────             │
│   │   Q1 (now)    50K/sec      5M           8GB         25%                 │
│   │   Q2          60K/sec      7M           11GB        35%                 │
│   │   Q3          72K/sec      10M          16GB        50%                 │
│   │   Q4          86K/sec      14M          22GB        70%  ← Warning      │
│   │   Q5          104K/sec     20M          32GB        100% ← Out of room  │
│   │                                                                         │
│   Decision Point: Q3 - add nodes or increase memory                         │
│                                                                             │
│   Options Analysis:                                                         │
│   ┌───────────────────┬────────────────────┬───────────────────────┐        │
│   │ Option            │ Pros               │ Cons                  │        │
│   ├───────────────────┼────────────────────┼───────────────────────┤        │
│   │ Upgrade to 64GB   │ Simple, no shards  │ Still vertical limit  │        │
│   │ nodes             │                    │ Expensive instances   │        │
│   ├───────────────────┼────────────────────┼───────────────────────┤        │
│   │ Add 3 more nodes  │ Linear capacity    │ Cluster complexity    │        │
│   │ (6 total)         │ growth path        │ Resharding risk       │        │
│   ├───────────────────┼────────────────────┼───────────────────────┤        │
│   │ Reduce TTL from   │ Zero cost          │ Less accurate limits  │        │
│   │ 1hr to 15min      │ Immediate relief   │ Product trade-off     │        │
│   ├───────────────────┼────────────────────┼───────────────────────┤        │
│   │ Move cold keys    │ Optimizes hot path │ Complexity added      │        │
│   │ to Cassandra      │                    │ Two-tier system       │        │
│   └───────────────────┴────────────────────┴───────────────────────┘        │
│                                                                             │
│   L6 Recommendation:                                                        │
│   Q3: Add 3 nodes (creates runway for Q5+)                                  │
│   Parallel: Evaluate TTL reduction with product (low-cost option)           │
│   Defer: Tiered storage (only if growth exceeds projections)                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Dangerous Assumptions in Capacity Planning

Staff Engineers identify and challenge assumptions that lead to capacity crises. These assumptions feel reasonable but break down at scale:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DANGEROUS CAPACITY PLANNING ASSUMPTIONS                  │
│                                                                             │
│   Assumption 1: "Linear Growth"                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   What you assume: Traffic grows 10% per month, predictably         │   │
│   │   Reality: Growth is non-linear and event-driven                    │   │
│   │   • Viral content: 100× traffic spike in hours                      │   │
│   │   • Marketing campaigns: 5× traffic spike                           │   │
│   │   • Product launches: Unknown multiplier                            │   │
│   │   • Seasonal peaks: 3× normal (Black Friday, New Year)              │   │
│   │                                                                     │   │
│   │   L6 Approach: Plan for 2-3× normal traffic, design load            │   │
│   │                shedding for 10× spikes                              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Assumption 2: "Average Metrics Tell the Story"                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   What you assume: "CPU is 50% on average, we're fine"              │   │
│   │   Reality: Averages hide spikes and hot partitions                  │   │
│   │   • Average CPU: 50%                                                │   │
│   │   • Peak CPU: 95% (during traffic spikes)                           │   │
│   │   • One hot partition: 200% (overloaded)                            │   │
│   │                                                                     │   │
│   │   L6 Approach: Monitor p95/p99, not averages. Track per-node        │   │
│   │                metrics, not cluster aggregates                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Assumption 3: "Storage Scales Linearly"                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   What you assume: 1TB today, 2TB next year, simple                 │   │
│   │   Reality: Storage growth accelerates and has hidden costs          │   │
│   │   • Data grows: 1TB → 2TB → 5TB → 15TB (exponential)                │   │
│   │   • Indexes grow faster than data (2-3× multiplier)                 │   │
│   │   • Backups grow: 1TB → 2TB → 5TB (same as data)                    │   │
│   │   • Replication: 3× storage (RF=3)                                  │   │
│   │   • Vacuum/compaction overhead: 20-30% additional                   │   │
│   │                                                                     │   │
│   │   L6 Approach: Model storage as: data × (1 + index_overhead) ×      │   │
│   │                replication_factor × (1 + compaction_overhead)       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Assumption 4: "Adding Nodes Solves Everything"                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   What you assume: "When we hit limits, we'll add nodes"            │   │
│   │   Reality: Adding nodes has limits and costs                        │   │
│   │   • Network overhead: More nodes = more coordination traffic        │   │
│   │   • Rebalancing cost: Moving data takes days/weeks                  │   │
│   │   • Diminishing returns: 3 nodes → 6 nodes ≠ 2× capacity            │   │
│   │   • Operational complexity: More nodes = more failure modes         │   │
│   │                                                                     │   │
│   │   L6 Approach: Vertical scaling first (cheaper, simpler).           │   │
│   │                Horizontal scaling only when vertical hits limits    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Assumption 5: "We Can Migrate Quickly"                                    │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   What you assume: "If this database doesn't work, we'll migrate"   │   │
│   │   Reality: Migrations take months and have risks                    │   │
│   │   • Schema migration: Weeks to months                               │   │
│   │   • Data migration: Days to weeks (for TB-scale)                    │   │
│   │   • Application changes: Weeks                                      │   │
│   │   • Testing: Weeks                                                  │   │
│   │   • Rollback plan: Often impossible                                 │   │
│   │                                                                     │   │
│   │   L6 Approach: Choose database for 3-year horizon, not 3-month      │   │
│   │                horizon. Migration is expensive—avoid if possible    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### What Fails First at Scale: The Bottleneck Hierarchy

Staff Engineers identify bottlenecks in order of likelihood. This helps prioritize capacity planning:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    WHAT FAILS FIRST AT SCALE (Bottleneck Order)             │
│                                                                             │
│   At 2× Scale:                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   1. Connection Pool (most common)                                  │   │
│   │      • Symptoms: "Connection pool exhausted" errors                 │   │
│   │      • Why: Applications create too many connections                │   │
│   │      • Fix: Connection pooling (PgBouncer, app-level)               │   │
│   │                                                                     │   │
│   │   2. Missing Indexes                                                │   │
│   │      • Symptoms: Slow queries, high CPU                             │   │
│   │      • Why: Queries that worked at small scale scan tables          │   │
│   │      • Fix: Add indexes on frequently queried columns               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   At 5× Scale:                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   1. Disk I/O Saturation                                            │   │
│   │      • Symptoms: Write latency increases, replication lag           │   │
│   │      • Why: Disk can't keep up with write rate                      │   │
│   │      • Fix: Faster disks (NVMe), more write replicas, batching      │   │
│   │                                                                     │   │
│   │   2. Memory Pressure                                                │   │
│   │      • Symptoms: OOM kills, swap usage, query performance degrades  │   │
│   │      • Why: Working set exceeds available RAM                       │   │
│   │      • Fix: Increase instance memory, optimize queries, cache       │   │
│   │                                                                     │   │
│   │   3. Hot Partitions                                                 │   │
│   │      • Symptoms: One node overloaded, others idle                   │   │
│   │      • Why: Poor partition key design (skewed distribution)         │   │
│   │      • Fix: Redesign partition key, add salting                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   At 10× Scale:                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   1. Single-Node Write Throughput                                   │   │
│   │      • Symptoms: Write latency spikes, queue buildup                │   │
│   │      • Why: Single primary can't handle write volume                │   │
│   │      • Fix: Sharding, write partitioning, or specialized stores     │   │
│   │                                                                     │   │
│   │   2. Network Bandwidth                                              │   │
│   │      • Symptoms: Replication lag, slow cross-region queries         │   │
│   │      • Why: Network becomes bottleneck for data transfer            │   │
│   │      • Fix: Regional deployments, data locality optimization        │   │
│   │                                                                     │   │
│   │   3. Query Planner Limits                                           │   │
│   │      • Symptoms: Complex queries timeout or use wrong plans         │   │
│   │      • Why: Query planner can't optimize for large datasets         │   │
│   │      • Fix: Denormalize, pre-compute, materialized views            │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   At 50×+ Scale:                                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   1. Distributed Coordination Overhead                              │   │
│   │      • Symptoms: Transaction latency increases, coordination fails  │   │
│   │      • Why: Cross-partition transactions are expensive              │   │
│   │      • Fix: Redesign data model to minimize cross-partition ops     │   │
│   │                                                                     │   │
│   │   2. Schema Evolution Becomes Impossible                            │   │
│   │      • Symptoms: Migrations take weeks, cause outages               │   │
│   │      • Why: Schema changes on TB-scale data are slow                │   │
│   │      • Fix: Schema-on-read, versioned schemas, gradual migration    │   │
│   │                                                                     │   │
│   │   3. Operational Complexity Explodes                                │   │
│   │      • Symptoms: Incidents increase, recovery takes longer          │   │
│   │      • Why: More components = more failure modes                    │   │
│   │      • Fix: Automation, standardization, runbooks                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Staff Engineer Insight: The bottleneck that fails first depends on your   │
│                          workload. Read-heavy fails at connection pool.     │
│                          Write-heavy fails at disk I/O. Identify YOUR       │
│                          bottleneck before it becomes a crisis.             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Real-world example**: A messaging platform hit these bottlenecks in sequence:
- **2× scale**: Connection pool exhausted (fixed with PgBouncer)
- **5× scale**: Disk I/O saturated (fixed with NVMe SSDs)
- **10× scale**: Single-node write throughput limit (fixed with sharding)
- **50× scale**: Distributed coordination overhead (fixed with data model redesign)

The pattern is predictable if you know what to look for.

---

## Hot Partition Detection and Prevention

Hot partitions (hot keys, hot shards) are a leading cause of database failures at scale. Understanding this problem deeply is essential for any Staff Engineer working with distributed databases.

### What Are Hot Partitions?

A **hot partition** occurs when one partition (shard, node, or key) receives disproportionately more traffic than others. While your cluster might have capacity in aggregate, that one hot partition becomes a bottleneck.

**Analogy**: Imagine a grocery store with 10 checkout lanes. On average, each lane handles 10 customers per hour. But if everyone wants to buy lottery tickets, and only lane 3 sells them, lane 3 has 100 customers while the other 9 lanes are empty. Your "average" metrics look fine (10 customers per lane), but customers in lane 3 wait for an hour.

**Why hot partitions are insidious**: 
- Aggregate metrics look normal (cluster is 20% utilized)
- But one partition is at 200% (overloaded)
- Latency for requests hitting that partition spikes
- Users affected by the hot partition see failures
- Traditional scaling (add more nodes) doesn't help—the hot partition stays hot

### Real-World Hot Partition Incidents

**Case 1: The Celebrity Problem** (Twitter-style system)
- A celebrity with 50 million followers posts a tweet
- The tweet is stored in partition based on `tweet_id`
- 50 million timeline fan-outs hit that one partition
- The partition handling that celebrity's data is crushed
- Other tweets from other users on the same partition also become slow

**Case 2: Time-Based Key Design** (Logging system)
- Partition key: `date` (e.g., "2024-01-15")
- All of today's logs go to one partition
- Yesterday's partition is cold, today's is on fire
- System designed for "uniform distribution" has 100% concentration

**Case 3: Popular Product** (E-commerce)
- Partition key: `product_id`
- Product goes viral on social media
- That partition handles 10,000× normal traffic
- All product data on that shard becomes slow
- Users see errors when viewing any product on the same shard

### Identifying Hot Partitions

The first step is detection. Hot partitions often hide in aggregate metrics.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    HOT PARTITION SYMPTOMS                                   │
│                                                                             │
│   What you see:                                                             │
│   • One node at 95% CPU, others at 30%                                      │
│   • Latency spikes for subset of requests                                   │
│   • Timeouts for specific users/entities                                    │
│   • Uneven disk usage across shards                                         │
│                                                                             │
│   Root causes:                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   Cause                        Example                              │   │
│   │   ──────────────────────────────────────────────────────────────    │   │
│   │   Celebrity users              1 user with 10M followers            │   │
│   │   Time-based keys              All "2024-01-15" data on one shard   │   │
│   │   Popular entities             Viral post, trending product         │   │
│   │   Poor hash function           user_ids 1-1000 all hash same        │   │
│   │   Organic skew                 Power-law distribution is natural    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Detection:                                                                │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   • Monitor per-node metrics (not just cluster aggregate)           │   │
│   │   • Track key access frequency (Redis OBJECT FREQ)                  │   │
│   │   • Monitor partition sizes (Cassandra cfstats)                     │   │
│   │   • Alert on skew ratio: max_node_load / avg_node_load > 2          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Prevention Strategies

There's no silver bullet for hot partitions—each strategy has trade-offs. The right choice depends on your access patterns and how much complexity you're willing to accept.

**Strategy 1: Key Salting (Scatter-Gather)**

The idea is simple: instead of one key, use many. Spread the load across multiple partitions, then gather results when reading.

**Example: Trending Hashtag Counter**

Without salting:
```
Key: "hashtag:worldcup"
Value: 50,000,000 (incremented by every tweet)
Problem: One key, one partition, millions of writes/second
```

With salting (10 shards):
```
Keys: "hashtag:worldcup:0", "hashtag:worldcup:1", ... "hashtag:worldcup:9"
Write: Pick random shard (0-9), increment that key
Read: Query all 10 shards, sum the values

Write throughput: 10× (spread across 10 partitions)
Read overhead: 10× (query 10 keys instead of 1)
```

**When to use**: High-write counters, aggregations, anything where you can tolerate read amplification.

**When NOT to use**: Data that must be read atomically or where read latency is critical.

**Code example**:
```python
import random

NUM_SHARDS = 10

def increment_counter(redis_client, base_key: str, amount: int = 1):
    shard = random.randint(0, NUM_SHARDS - 1)
    sharded_key = f"{base_key}:{shard}"
    return redis_client.incrby(sharded_key, amount)

def get_counter(redis_client, base_key: str) -> int:
    keys = [f"{base_key}:{i}" for i in range(NUM_SHARDS)]
    values = redis_client.mget(keys)  # Single round-trip for all shards
    return sum(int(v or 0) for v in values)
```

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    HOT PARTITION PREVENTION                                 │
│                                                                             │
│   Strategy 1: Key Salting (Scatter)                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   Problem key: "trending:today" → All traffic to one shard          │   │
│   │                                                                     │   │
│   │   Solution: Add salt                                                │   │
│   │   • "trending:today:0", "trending:today:1", ... "trending:today:9"  │   │
│   │   • Write: pick random salt                                         │   │
│   │   • Read: query all salts, merge                                    │   │
│   │                                                                     │   │
│   │   Trade-off: 10x read amplification for 10x write distribution      │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Strategy 2: Read Replica / Cache for Hot Keys                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   [Request] → [Is hot key?] ──YES──→ [Dedicated Cache Tier]         │   │
│   │                    │                                                │   │
│   │                   NO                                                │   │
│   │                    │                                                │   │
│   │                    ▼                                                │   │
│   │               [Normal Path]                                         │   │
│   │                                                                     │   │
│   │   Hot key detection:                                                │   │
│   │   • Predefined list (celebrity user IDs)                            │   │
│   │   • Runtime detection (access count > threshold)                    │   │
│   │   • Bloom filter for hot key membership                             │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Strategy 3: Time-Based Key Design                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   Bad:  "events:2024-01-15" (all day's events on one partition)     │   │
│   │   Good: "events:2024-01-15:shard-7" (explicit sharding)             │   │
│   │   Better: "events:{user_id}:2024-01-15" (natural distribution)      │   │
│   │                                                                     │   │
│   │   Time-based data should have non-time prefix in partition key      │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Strategy 4: Rate Limiting Hot Keys                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   If a key is too hot, it can take down the system.                 │   │
│   │   Solution: Rate limit access to hot keys.                          │   │
│   │                                                                     │   │
│   │   if key_access_rate(key) > MAX_KEY_RATE:                           │   │
│   │       return cached_value or RATE_LIMITED_ERROR                     │   │
│   │                                                                     │   │
│   │   Better to rate limit one viral post than crash the database.      │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Multi-Region Database Strategy

Going multi-region is one of the most complex database decisions. Staff Engineers must understand the fundamental trade-offs—and more importantly, must be able to explain to stakeholders why "just put databases everywhere" isn't simple.

### Why Multi-Region Is Hard

**The speed of light problem**: Data centers are physically separated. US-East to US-West is ~80ms round-trip. US to Europe is ~120ms. US to Australia is ~200ms. These are physics limits—you cannot make light travel faster.

This creates an impossible triangle:
- **Strong consistency** requires coordination across regions (adds latency)
- **Low latency** requires local reads/writes (risks inconsistency)
- **High availability** requires multiple regions (creates coordination challenges)

**You can optimize for two, but not all three.** The Staff Engineer's job is to understand which two matter most for each use case.

### Real-World Multi-Region Decisions

**Example 1: User Profile Service**
- Users expect to see their own changes immediately (read-your-writes)
- Users rarely interact with users in other regions
- Decision: Geo-partition by user's home region. User data lives in one region, replicated async for DR.
- Trade-off accepted: Cross-region friend requests have slight delay.

**Example 2: Inventory System (E-commerce)**
- Same product can be ordered from any region
- Overselling is catastrophic (legal, customer trust)
- Decision: Single primary region for inventory, synchronous confirmation before order acceptance.
- Trade-off accepted: Higher latency for users far from primary region.

**Example 3: Social Media Feed**
- Users want fast reads (sub-100ms)
- Slightly stale data is acceptable (you don't need the absolute latest post)
- Decision: Multi-primary with async replication, eventual consistency.
- Trade-off accepted: You might see a post from 2 seconds ago, not 0 seconds ago.

### The Multi-Region Trade-off Triangle

This diagram illustrates why you can only optimize for two of three properties:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MULTI-REGION TRADE-OFFS                                  │
│                                                                             │
│                         CONSISTENCY                                         │
│                            /\                                               │
│                           /  \                                              │
│                          /    \                                             │
│                         /      \                                            │
│                        / Spanner \                                          │
│                       /   (slow)  \                                         │
│                      /______________\                                       │
│                     /                \                                      │
│                    /   PICK TWO       \                                     │
│                   /                    \                                    │
│                  /                      \                                   │
│                 /   Async Repl.  Local   \                                  │
│                /   (stale reads) (active)\                                  │
│               /__________________________ \                                 │
│              LATENCY ──────────────────── AVAILABILITY                      │
│                                                                             │
│   • Strong consistency + Low latency = Single region (no availability)      │
│   • Strong consistency + High availability = High latency (Spanner)         │
│   • Low latency + High availability = Eventual consistency (async repl)     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Multi-Region Patterns

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MULTI-REGION DATABASE PATTERNS                           │
│                                                                             │
│   Pattern 1: Active-Passive (Disaster Recovery)                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   [US-West: Active]  ───async───→  [US-East: Passive]               │   │
│   │   All reads & writes              Read replicas only                │   │
│   │                                   Standby for failover              │   │
│   │                                                                     │   │
│   │   Pros: Simple, strong consistency in primary                       │   │
│   │   Cons: Cross-region latency for all users, manual failover         │   │
│   │   Use when: DR is the goal, not performance                         │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Pattern 2: Active-Active with Eventual Consistency                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   [US-West]  ←───async───→  [US-East]                               │   │
│   │   Local reads & writes      Local reads & writes                    │   │
│   │                                                                     │   │
│   │   Conflict resolution required:                                     │   │
│   │   • Last-write-wins (simple, data loss possible)                    │   │
│   │   • Vector clocks (complex, preserves both)                         │   │
│   │   • CRDTs (merge-able data types)                                   │   │
│   │                                                                     │   │
│   │   Pros: Low latency, high availability                              │   │
│   │   Cons: Conflicts, eventual consistency                             │   │
│   │   Use when: Data is partition-able, conflicts are rare/resolvable   │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Pattern 3: Geo-Partitioned (Data Sovereignty)                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   [EU: EU users only]    [US: US users only]    [APAC: APAC only]   │   │
│   │                                                                     │   │
│   │   • User data stays in region (GDPR compliance)                     │   │
│   │   • No cross-region replication of user data                        │   │
│   │   • Global data (products, config) replicated everywhere            │   │
│   │                                                                     │   │
│   │   Pros: Compliance, data locality, isolation                        │   │
│   │   Cons: Cross-region features are hard                              │   │
│   │   Use when: Regulatory requirements, regional business units        │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Pattern 4: Distributed SQL (Spanner-style)                                │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   [Spanner/CockroachDB across regions]                              │   │
│   │                                                                     │   │
│   │   • Automatic data placement                                        │   │
│   │   • Strong consistency (at latency cost)                            │   │
│   │   • Transparent multi-region transactions                           │   │
│   │                                                                     │   │
│   │   Pros: SQL semantics, automatic handling                           │   │
│   │   Cons: Latency (50-200ms cross-region), cost, vendor lock-in       │   │
│   │   Use when: Need strong consistency + global availability           │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Data Integrity Verification

At scale, data corruption happens. It's not a question of if, but when. Disk failures, software bugs, network issues, and human errors all contribute. Staff Engineers design systems that detect corruption early and recover from it before it becomes catastrophic.

### Why Data Corruption Happens

**Hardware failures**: Disks lie. They occasionally return incorrect data. Studies show that 1 in every 10^14 to 10^15 bits read from disk is incorrect. At petabyte scale, that's multiple corrupted bits per day.

**Software bugs**: Application bugs can write incorrect data. A bug in serialization, a race condition, an off-by-one error—these silently corrupt data.

**Replication issues**: In distributed systems, replicas can diverge. Network issues, clock skew, and software bugs can cause replicas to have different data.

**Human errors**: Someone runs an UPDATE without a WHERE clause. Someone drops the wrong table. Someone's migration script has a bug.

### The Silent Corruption Problem

The scariest corruption is the kind you don't detect. Consider this scenario:

1. **January**: A bug introduces corruption in 0.01% of records
2. **February**: Backups now contain corrupted data
3. **March**: Old backups expire (you keep 60 days)
4. **April**: Someone notices incorrect data
5. **Recovery**: You have no clean backup. The corruption has propagated everywhere.

**The solution**: Continuous integrity verification. Don't wait for someone to notice—actively check your data.

### Integrity Check Patterns

Different patterns serve different purposes. Use them in combination for defense in depth.

**Pattern 1: Checksums for Critical Data**

Checksums detect corruption at the record level. Store a cryptographic hash of critical fields, verify on every read.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DATA INTEGRITY PATTERNS                                  │
│                                                                             │
│   1. Checksums for Critical Data                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   CREATE TABLE financial_transactions (                             │   │
│   │     id BIGSERIAL PRIMARY KEY,                                       │   │
│   │     amount DECIMAL(15,2) NOT NULL,                                  │   │
│   │     from_account BIGINT NOT NULL,                                   │   │
│   │     to_account BIGINT NOT NULL,                                     │   │
│   │     -- Checksum of critical fields                                  │   │
│   │     checksum VARCHAR(64) NOT NULL                                   │   │
│   │   );                                                                │   │
│   │                                                                     │   │
│   │   checksum = SHA256(id || amount || from || to || secret_salt)      │   │
│   │   Verify checksum on read; alert if mismatch                        │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   2. Cross-Database Reconciliation                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   When data exists in multiple stores:                              │   │
│   │                                                                     │   │
│   │   [PostgreSQL]         [Elasticsearch]         [Redis]              │   │
│   │        │                      │                    │                │   │
│   │        └──────────────────────┴────────────────────┘                │   │
│   │                               │                                     │   │
│   │                               ▼                                     │   │
│   │                    [Reconciliation Job]                             │   │
│   │                               │                                     │   │
│   │                    • Compare record counts                          │   │
│   │                    • Sample and compare content                     │   │
│   │                    • Alert on discrepancies                         │   │
│   │                    • Auto-heal from source of truth                 │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   3. Invariant Checks                                                       │ 
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   Business invariants that should always hold:                      │   │
│   │                                                                     │   │
│   │   -- Orders should have valid status transitions                    │   │
│   │   SELECT * FROM orders                                              │   │
│   │   WHERE status = 'shipped' AND shipped_at IS NULL;                  │   │
│   │   -- Should return 0 rows                                           │   │
│   │                                                                     │   │
│   │   -- Account balances should never be negative (unless allowed)     │   │
│   │   SELECT * FROM accounts WHERE balance < 0;                         │   │
│   │   -- Should return 0 rows                                           │   │
│   │                                                                     │   │
│   │   Run these checks hourly; alert on violations                      │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 9: Interview Calibration

## What Interviewers Look For in Database Discussions

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    INTERVIEWER EVALUATION SIGNALS                           │
│                                                                             │
│   Strong L6 Signal                    Weak/L5 Signal                        │
│   ───────────────────────────────────────────────────────────────────────   │
│   "Let me understand the access       "Let's use MongoDB because it's       │
│    patterns before choosing..."        flexible"                            │
│                                                                             │
│   "We need to consider what happens   "We'll add a database for this"       │
│    when this database fails..."        (no failure discussion)              │
│                                                                             │
│   "This choice constrains our future  "This handles our current needs"      │
│    options in these ways..."           (no evolution thinking)              │
│                                                                             │
│   "I'm explicitly rejecting X because "I prefer Y" (no rejection            │
│    of these trade-offs..."             reasoning)                           │
│                                                                             │
│   "The blast radius of failure here   "If it fails, we'll fix it"           │
│    is limited to..."                   (no containment thinking)            │
│                                                                             │
│   "At 10x scale, this becomes the     "It scales horizontally"              │
│    bottleneck because..."              (no specific analysis)               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Interviewer Probe Questions

Interviewers use these questions to assess depth. Strong candidates answer with specifics; weak candidates give generic answers.

| Probe Question | Tests For | Strong Answer | Weak Answer |
|----------------|-----------|---------------|-------------|
| "What happens when this database fails?" | Failure-mode thinking | Blast radius, degradation path, detection, containment | "We'll fix it" or "We have backups" |
| "How would you migrate off this database?" | Evolution thinking | Strangler fig, dual-write, rollback plan | "We wouldn't need to" |
| "What breaks first at 10× scale?" | Bottleneck analysis | Specific limit (connections, disk I/O, hot partition) | "It scales" |
| "Why not [alternative database]?" | Trade-off articulation | Explicit rejection with reasoning | "I prefer this one" |
| "How do you debug a slow query in production?" | Observability | Traces, metrics, query plan, correlation | "We'd look at logs" |
| "Who owns this database when two teams use it?" | Cross-team impact | Ownership model, change process | "We'd figure it out" |

**Staff insight**: Interviewers probe until you show a gap or demonstrate depth. "I don't know" is acceptable if followed by how you'd find out. Guessing and hand-waving is not.

## Example Phrases Staff Engineers Use

### When Choosing a Database

> "Before I pick a database, I need to understand three things: the access patterns, the consistency requirements, and what happens when it fails. Let me walk through each..."

> "I'm going to use PostgreSQL here, and I want to explicitly explain why I'm *not* using MongoDB or DynamoDB for this case..."

> "This is read-heavy with stable schema, so relational makes sense. If the requirements were different—say, highly variable schema or 100K writes per second—I'd reconsider."

### When Discussing Failure

> "Let's talk about what happens when this database becomes unavailable. The blast radius is limited to [scope] because we have [fallback]. Here's the degraded experience..."

> "I'm designing this so that a database failure results in degraded service, not complete outage. Users can still [core action], they just can't [secondary action]."

> "The worst-case scenario is [description]. We prevent it by [mechanism], and if it happens anyway, we detect it via [monitoring] and recover by [process]."

### When Discussing Scale

> "At current scale, PostgreSQL handles this easily. I'm projecting that at 10x scale, we'll hit [specific bottleneck] around [timeframe]. Here's my evolution plan..."

> "Sharding is the right answer at massive scale, but we're not there yet. For now, read replicas and caching give us 10x headroom before we need to pay that complexity tax."

> "I want to design this so we can evolve the database layer without rewriting the application. That means [abstraction layer / interface design]."

---

## How to Explain to Leadership

Staff Engineers translate technical decisions into business language:

**Database choice**: "We're using PostgreSQL for core data because it reduces operational risk and cost. Our team has deep expertise, which speeds incident resolution. The alternative would add 3–6 months of ramp-up and higher ongoing cost."

**Migration delays**: "We're delaying the Cassandra migration because our current PostgreSQL setup has 18 months of headroom. Migrating now would consume 3 engineer-months with no user-visible benefit. We'll revisit when we approach the bottleneck."

**Cost justification**: "The managed database costs 40% more than self-hosted, but it eliminates 15 hours/month of DBA work. At our team's cost, that's a net savings of $4K/month."

**Principle**: Lead with impact (reliability, cost, velocity). Technology is the means, not the message.

## How to Teach These Concepts

**For engineers new to databases**: Start with the access-pattern matrix. "What do you need to read? What do you need to write? How often?" Map answers to the decision tree before naming technologies.

**For senior engineers**: Focus on failure modes. "What happens when this database fails? What's the blast radius? How do we detect and contain?"

**For architects**: Emphasize evolution. "What breaks at 10× scale? What's the migration path? What are we explicitly not building?"

**Teaching one-liner**: "I'll explain the framework first. Then we'll apply it to your system. You'll see why the answer falls out—it's not magic, it's constraint satisfaction."

---

## Staff vs Senior: Database Decision Contrast

At L6, the difference shows in *how* you approach database decisions, not just *what* you choose:

| Dimension | Senior (L5) Approach | Staff (L6) Approach |
|-----------|----------------------|---------------------|
| **Starting point** | "Which database fits?" | "What are the access patterns, consistency needs, and failure modes?" |
| **Rejection of alternatives** | "I prefer X" | "I'm explicitly not using Y because of [trade-off A, B]. Here's why that matters for our context." |
| **Scale thinking** | "It scales" or "We'll add replicas" | "At 10× scale, [connections / disk I/O / hot partition] breaks first. We'll hit that around [timeframe]. Plan: [concrete steps]." |
| **Failure thinking** | "We have backups" or "We'll fix it" | "Blast radius is [scope]. Degradation path: [cached data / read-only / fail-open]. Detection: [metric]. Containment: [circuit breaker / rate limit]." |
| **Evolution** | "Current design handles our needs" | "This choice constrains us in [ways]. Migration path if we outgrow: [strangler fig / dual-write]. Avoid lock-in by [abstraction]." |
| **Cost** | "Managed is easier" or "Self-hosted is cheaper" | "TCO: ops burden [X hrs/month], incident risk [Y]. At our scale, [managed/self-hosted] wins because [reason]." |
| **Cross-team** | "We'll figure out ownership" | "Ownership model: [owner]. Change process: [RFC, review]. Shared DB standards: [approved list]. Non-standard requires [approval path]." |

**Staff one-liner**: "A Senior picks a database. A Staff Engineer derives it from constraints and documents why alternatives were rejected."

---

## Common L5 Mistake: Technology-First Thinking

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    L5 vs L6 DATABASE DISCUSSION                             │
│                                                                             │
│   The Prompt: "Design a messaging system for 10M users"                     │
│                                                                             │
│   L5 Response (Technology-First):                                           │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   "For the database, I'll use Cassandra because it's write-         │   │
│   │    optimized and scales horizontally. Messages are time-series      │   │
│   │    data, which fits the wide-column model. We can partition by      │   │
│   │    conversation_id and cluster by timestamp."                       │   │
│   │                                                                     │   │
│   │   [Jumps to schema design without exploring requirements]           │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   L6 Response (Requirements-First):                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   "Before I choose a database, let me understand the access         │   │
│   │    patterns. For messaging, we have:                                │   │
│   │                                                                     │   │
│   │    • Send message: Write to conversation (high volume)              │   │
│   │    • Load conversation: Read recent messages by conversation_id     │   │
│   │    • Search messages: Full-text search (less frequent)              │   │
│   │    • Delivery status: Update status for specific message            │   │
│   │                                                                     │   │
│   │    The core pattern is time-ordered writes with point-reads by      │   │
│   │    conversation. That points toward a wide-column store like        │   │
│   │    Cassandra. But I need to consider:                               │   │
│   │                                                                     │   │
│   │    1. What consistency do we need? For messaging, read-your-writes  │   │
│   │       is essential—you must see your own message after sending.     │   │
│   │                                                                     │   │
│   │    2. What about delivery status? That's a random write to an       │   │
│   │       existing message. Cassandra handles this, but it creates      │   │
│   │       tombstones on update. I'd consider a separate table for       │   │
│   │       delivery status to avoid tombstone buildup.                   │   │
│   │                                                                     │   │
│   │    3. Search is a different access pattern—full-text across all     │   │
│   │       messages. That's Elasticsearch, not Cassandra. I'd async      │   │
│   │       index messages for search.                                    │   │
│   │                                                                     │   │
│   │    So my data layer is:                                             │   │
│   │    • Cassandra: Message storage (partition by conversation)         │   │
│   │    • PostgreSQL: User accounts, conversation metadata               │   │
│   │    • Elasticsearch: Message search (eventual, async indexed)        │   │
│   │    • Redis: Recent message cache, online status                     │   │
│   │                                                                     │   │
│   │    Let me explain why I'm NOT using a single database here..."      │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Key Differences:                                                          │
│   • L5: Names technology immediately, justifies afterward                   │
│   • L6: Explores requirements first, derives technology from constraints    │
│   • L5: Single database assumption                                          │
│   • L6: Multiple databases for different access patterns                    │
│   • L5: Mentions scaling as a feature                                       │
│   • L6: Discusses specific bottlenecks and evolution                        │
│   • L5: No failure discussion                                               │
│   • L6: Consistency, tombstones, async indexing—operational reality         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Split-Brain Scenarios and Prevention

Split-brain is one of the most dangerous failure modes in distributed databases. Staff Engineers must understand and design for it. Unlike other failures that lose availability, split-brain causes **data corruption**—the kind that can take weeks to untangle.

### What Is Split-Brain?

Split-brain occurs when a network partition causes a cluster to fragment, and multiple nodes believe they are the primary/leader, accepting writes independently. When the partition heals, you have two divergent copies of your data, and no automatic way to reconcile them.

**Why is it called "split-brain"?** The analogy is to the two hemispheres of the brain. Normally, they coordinate through the corpus callosum. If severed, each hemisphere can independently control half the body, causing conflicting actions. In databases, a network partition severs the coordination between nodes, and each "half" of the cluster tries to operate independently.

### Real-World Split-Brain Incident

**The GitHub Incident (2012)**: GitHub experienced a split-brain event that became a famous case study:

1. A network partition isolated their primary MySQL server from the rest of the cluster
2. Their failover system detected the primary as "down" and promoted a replica
3. But the old primary wasn't down—it was just isolated
4. Both the old primary and the new primary accepted writes
5. When the partition healed, they had two divergent databases
6. Some repositories had commits on one server, different commits on the other
7. Recovery took 5 hours and required manual reconciliation of data

The lesson: **A node being unreachable is not the same as a node being down.** Your failover logic must account for this.

### The Danger of Split-Brain: Concrete Examples

**Scenario 1: E-commerce Inventory**
- Single product with 10 units in stock
- Split-brain: Both primaries think they have 10 units
- Region A sells 8 units (thinks 2 remain)
- Region B sells 7 units (thinks 3 remain)
- Partition heals: You've sold 15 units of a 10-unit inventory
- Result: Angry customers, refunds, loss of trust

**Scenario 2: Banking Transfer**
- Alice has $1000
- Split-brain: Both primaries show $1000 balance
- Region A: Alice transfers $800 to Bob
- Region B: Alice transfers $900 to Charlie
- Partition heals: Alice has -$700, bank loses $700
- Result: Regulatory violation, financial loss

**Scenario 3: User Authentication**
- User changes password in Region A (old password: "abc", new: "xyz")
- Region B doesn't see the change (still thinks password is "abc")
- Attacker in Region B logs in with old password
- Result: Security breach

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SPLIT-BRAIN SCENARIO                                     │
│                                                                             │
│   Normal Operation:                                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   [Primary]  ←───sync───→  [Replica A]  ←───sync───→  [Replica B]   │   │
│   │       ↑                                                             │   │
│   │    Writes                                                           │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Network Partition (Split-Brain):                                          │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   Datacenter 1           ║        Datacenter 2                      │   │
│   │   ──────────────         ║        ──────────────                    │   │
│   │   [Primary*]             ║        [Replica A]  ←──→  [Replica B]    │   │
│   │       ↑                  ║              ↑                           │   │
│   │    Writes from           ║        Writes from                       │   │
│   │    DC1 clients           ║        DC2 clients                       │   │
│   │                          ║        (Replica A promoted!)             │   │
│   │                                                                     │   │
│   │   PROBLEM: Two primaries accepting different writes                 │   │
│   │   RESULT: Data divergence, conflicts, potential data loss           │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Split-Brain Prevention Strategies

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SPLIT-BRAIN PREVENTION                                   │
│                                                                             │
│   Strategy 1: Quorum-Based Leadership                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   Rule: Leader must have majority of votes to remain leader         │   │
│   │                                                                     │   │
│   │   3 nodes: Need 2 votes → 1 DC can have outage                      │   │
│   │   5 nodes: Need 3 votes → 2 nodes can fail                          │   │
│   │                                                                     │   │
│   │   When partition occurs:                                            │   │
│   │   • DC with majority keeps leader, continues accepting writes       │   │
│   │   • DC with minority steps down, rejects writes                     │   │
│   │   • No split-brain possible                                         │   │
│   │                                                                     │   │
│   │   Used by: PostgreSQL + Patroni, etcd, Consul, ZooKeeper            │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Strategy 2: Fencing Tokens                                                │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   Each leader gets a monotonically increasing token                 │   │
│   │   Storage layer rejects writes from old tokens                      │   │
│   │                                                                     │   │
│   │   1. Leader A has token 5, writing to storage                       │   │
│   │   2. A partitioned, B becomes leader with token 6                   │   │
│   │   3. A comes back, tries to write with token 5                      │   │
│   │   4. Storage rejects: "Token 5 < current token 6"                   │   │
│   │                                                                     │   │
│   │   Prevents: Zombie leaders from corrupting data                     │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Strategy 3: STONITH (Shoot The Other Node In The Head)                    │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   Before promoting a new leader, forcibly power off the old one     │   │
│   │                                                                     │   │
│   │   1. Old leader unreachable                                         │   │
│   │   2. Send IPMI/cloud API command to power off old leader            │   │
│   │   3. Wait for confirmation                                          │   │
│   │   4. Only then promote new leader                                   │   │
│   │                                                                     │   │
│   │   Guarantees: Old leader cannot possibly write                      │   │
│   │   Risk: If fencing fails, no failover happens                       │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Staff Insight: Split-brain prevention is table stakes for production      │
│                  databases. If your failover mechanism can create two       │
│                  primaries, you will eventually lose or corrupt data.       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Real Example: Redis Cluster Split-Brain

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    REDIS CLUSTER SPLIT-BRAIN SCENARIO                       │
│                                                                             │
│   Setup: 3 Redis masters, 3 replicas (6 nodes total)                        │
│   Each master handles 1/3 of hash slots                                     │
│                                                                             │
│   Partition occurs:                                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   Side A (2 masters)         ║   Side B (1 master + 3 replicas)     │   │
│   │   ──────────────────         ║   ─────────────────────────────      │   │
│   │   [Master 1] [Master 2]      ║   [Master 3] [Replica 1,2,3]         │   │
│   │                              ║        │                             │   │
│   │   Has 2/3 hash slots         ║   Replica of Master 1 promoted!      │   │
│   │   Continues serving          ║   Now has "majority" (4 nodes)       │   │
│   │                              ║   Accepts writes to M1's slots       │   │
│   │                                                                     │   │
│   │   SPLIT-BRAIN: Two nodes claim same hash slots                      │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Prevention Configuration:                                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   # redis.conf                                                      │   │
│   │   cluster-require-full-coverage yes  # Reject if any slot missing   │   │
│   │   min-replicas-to-write 1            # Master needs 1 sync replica  │   │
│   │   min-replicas-max-lag 10            # Replica must be <10s behind  │   │
│   │                                                                     │   │
│   │   With these settings:                                              │   │
│   │   • Side A: 2 masters but no replicas → stops accepting writes      │   │
│   │   • Side B: Promoted master has replicas → becomes authoritative    │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Trade-off: Lower availability (stops writes more often)                   │
│              Higher consistency (no data loss from split-brain)             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Total Cost of Ownership (TCO) Analysis

Staff Engineers consider the full cost of database decisions, not just licensing.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DATABASE TCO FRAMEWORK                                   │
│                                                                             │
│   Cost Category          PostgreSQL (self)  DynamoDB        Cassandra       │
│   ─────────────────────────────────────────────────────────────────────     │
│                                                                             │
│   Infrastructure                                                            │
│   ├─ Compute             $X (your choice)   Included        $X × nodes      │
│   ├─ Storage             $Y (EBS/disk)      Per GB ($0.25)  $Y × RF         │
│   ├─ Network             Minimal            Per request     Cross-AZ        │
│   └─ Backup              S3 storage         Included        Manual/S3       │
│                                                                             │
│   Operations                                                                │
│   ├─ DBA time            HIGH (tuning,      LOW (managed)   MEDIUM          │
│   │                      upgrades, HA)                      (operations)    │
│   ├─ On-call burden      HIGH               LOW             MEDIUM          │
│   ├─ Monitoring          DIY + tools        CloudWatch      DIY + tools     │
│   └─ Security patches    Your job           Automatic       Your job        │
│                                                                             │
│   Development                                                               │
│   ├─ Schema changes      Low friction       Low friction    HIGH friction   │
│   ├─ Query flexibility   Excellent          Limited         Very limited    │
│   ├─ Learning curve      LOW (SQL known)    MEDIUM          HIGH            │
│   └─ Testing complexity  LOW                MEDIUM (mocks)  HIGH            │
│                                                                             │
│   Hidden Costs                                                              │
│   ├─ Vendor lock-in      None               HIGH            Low             │
│   ├─ Migration effort    Baseline           HIGH to escape  MEDIUM          │
│   └─ Incident recovery   Your team          AWS support     Your team       │
│                                                                             │
│   When to choose:                                                           │
│   • PostgreSQL: Team has DBA, needs flexibility, cost-conscious             │
│   • DynamoDB: No DBA, predictable workload, pay-per-use preferred           │
│   • Cassandra: Write-heavy, need control, have distributed expertise        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Cost Modeling Example: API Gateway

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    API GATEWAY DATABASE COST ANALYSIS                       │
│                                                                             │
│   Workload: 1B API calls/month, need request logging + rate limiting        │
│                                                                             │
│   Option A: PostgreSQL for Everything                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   Request logs: 1B rows/month × 500 bytes = 500GB/month             │   │
│   │   After 12 months: 6TB of logs                                      │   │
│   │                                                                     │   │
│   │   Problems:                                                         │   │
│   │   • 6TB exceeds single-node practical limit                         │   │
│   │   • Log writes (30K/sec) compete with rate limit reads              │   │
│   │   • Vacuum can't keep up with write rate                            │   │
│   │   • Query performance degrades                                      │   │
│   │                                                                     │   │
│   │   Cost: $3K/month compute + $1K/month storage + $5K/month DBA       │   │
│   │         = ~$9K/month, PLUS pain and outages                         │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Option B: Right Tool for Each Job                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │   Rate limiting: Redis Cluster                                      │   │
│   │   • 3 nodes × $200/month = $600/month                               │   │
│   │   • Sub-millisecond, handles 100K+ ops/sec                          │   │
│   │                                                                     │   │
│   │   Request logs: Cassandra → S3 (cold storage)                       │   │
│   │   • Cassandra: 6 nodes × $500/month = $3K/month                     │   │
│   │   • S3 archive: $0.004/GB = $24/month for 6TB                       │   │
│   │   • Handles 30K writes/sec easily                                   │   │
│   │                                                                     │   │
│   │   API configs: PostgreSQL (small)                                   │   │
│   │   • 1 node × $500/month = $500/month                                │   │
│   │   • Low volume, needs transactions                                  │   │
│   │                                                                     │   │
│   │   Total: ~$4.2K/month, no pain, scales to 10x                       │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   L6 Insight: Three databases cost less than one overloaded database.       │
│               The "simplicity" of one database is false economy.            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Top 2 Cost Drivers: What Actually Costs Money

Staff Engineers identify the dominant cost drivers because optimizing the wrong thing wastes effort. Here are the top 2 cost drivers for most database deployments:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    TOP 2 DATABASE COST DRIVERS                              │
│                                                                             │
│   #1: OPERATIONAL OVERHEAD (60-70% of total cost)                           │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   What it includes:                                                 │   │
│   │   • On-call engineer time (incidents, debugging)                    │   │
│   │   • DBA time (tuning, optimization, migrations)                     │   │
│   │   • Infrastructure setup and maintenance                            │   │
│   │   • Monitoring and alerting setup                                   │   │
│   │   • Security patches and compliance                                 │   │
│   │   • Documentation and runbooks                                      │   │
│   │                                                                     │   │
│   │   Why it's #1:                                                      │   │
│   │   • Engineer time costs $150-300/hour                               │   │
│   │   • One incident can cost $10K+ in engineer time                    │   │
│   │   • Ongoing maintenance is 20-40% of engineer time                  │   │
│   │   • Self-hosted databases require more operational time             │   │
│   │                                                                     │   │
│   │   Example:                                                          │   │
│   │   • PostgreSQL (self-hosted): $2K/month infrastructure              │   │
│   │   • But: 20 hours/month DBA time = $3K-6K/month                     │   │
│   │   • Total: $5K-8K/month (operational overhead dominates)            │   │
│   │                                                                     │   │
│   │   L6 Insight: Managed services (RDS, DynamoDB) reduce operational   │   │
│   │               overhead, even if infrastructure costs more.          │   │
│   │               For small teams, managed is often cheaper overall.    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   #2: STORAGE COSTS (20-30% of total cost, but scales fastest)              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   What it includes:                                                 │   │
│   │   • Primary storage (data + indexes)                                │   │
│   │   • Replication storage (RF=3 means 3× data)                        │   │
│   │   • Backup storage (retention policies)                             │   │
│   │   • Snapshot storage (point-in-time recovery)                       │   │
│   │   • Archive storage (cold data)                                     │   │
│   │                                                                     │   │
│   │   Why it's #2:                                                      │   │
│   │   • Storage costs scale linearly with data growth                   │   │
│   │   • Data grows faster than compute needs (2-3× per year typical)    │   │
│   │   • Replication multiplies storage (RF=3 = 3× cost)                 │   │
│   │   • Backups add 50-100% more storage                                │   │
│   │   • Indexes can double storage requirements                         │   │
│   │                                                                     │   │
│   │   Example:                                                          │   │
│   │   • Primary data: 1TB                                               │   │
│   │   • Indexes: 500GB (50% overhead)                                   │   │
│   │   • Replication (RF=3): 4.5TB × 3 = 13.5TB                          │   │
│   │   • Backups (30-day retention): +4.5TB                              │   │
│   │   • Total: 18TB                                                     │   │
│   │   • Cost: 18TB × $0.10/GB/month = $1,800/month                      │   │
│   │                                                                     │   │
│   │   L6 Insight: Storage costs compound. 1TB today becomes 10TB in     │   │
│   │               3 years. Plan for data lifecycle (archive old data)   │   │
│   │               and optimize indexes (they're expensive).             │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   What's NOT in top 2:                                                      │
│   • Compute costs (usually 10-15% of total)                                 │
│   • Network costs (usually <5% of total)                                    │
│   • Licensing (varies, but often <10% for open-source)                      │
│                                                                             │
│   Staff Engineer Insight: Optimize operational overhead first (use          │
│                          managed services, automate). Then optimize         │
│                          storage (archive old data, optimize indexes).      │
│                          Compute optimization comes last.                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### How Cost Scales: The Multiplier Effect

Staff Engineers model how costs scale because linear thinking leads to budget surprises:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    COST SCALING ANALYSIS                                    │
│                                                                             │
│   Scenario: User profile service, starting at 1M users                      │
│                                                                             │
│   ┌──────────────┬──────────────┬──────────────┬──────────────┬──────────┐  │
│   │ Scale        │ Users        │ Data Size    │ Monthly Cost │ Cost/User│  │
│   ├──────────────┼──────────────┼──────────────┼──────────────┼──────────┤  │
│   │ 1× (baseline)│ 1M           │ 100GB        │ $500         │ $0.0005  │  │
│   │ 2×           │ 2M           │ 250GB        │ $1,200       │ $0.0006  │  │
│   │ 5×           │ 5M           │ 1TB          │ $4,500       │ $0.0009  │  │
│   │ 10×          │ 10M          │ 3TB          │ $15,000      │ $0.0015  │  │
│   │ 50×          │ 50M          │ 20TB         │ $120,000     │ $0.0024  │  │
│   └──────────────┴──────────────┴──────────────┴──────────────┴──────────┘  │
│                                                                             │
│   Why cost per user increases:                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   1. Storage scales faster than users (indexes, replication)        │   │
│   │      • 1M users: 100GB data + 50GB indexes = 150GB                  │   │
│   │      • 10M users: 2TB data + 1TB indexes = 3TB (20×, not 10×)       │   │
│   │                                                                     │   │
│   │   2. Operational overhead doesn't scale linearly                    │   │
│   │      • 1M users: 1 DBA, 1 on-call engineer                          │   │
│   │      • 10M users: 2 DBAs, 2 on-call engineers (more complex)        │   │
│   │      • 50M users: 5 DBAs, 3 on-call engineers (specialized)         │   │
│   │                                                                     │   │
│   │   3. Infrastructure needs scale non-linearly                        │   │
│   │      • 1M users: Single region, 2 replicas                          │   │
│   │      • 10M users: Multi-region, 6 replicas (3× regions)             │   │
│   │      • 50M users: Multi-region, 15 replicas + specialized infra     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Cost Breakdown at 10× Scale:                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   Operational overhead: $8,000/month (53%)                          │   │
│   │   • 2 DBAs × $10K/month = $20K/year = $1.7K/month                   │   │
│   │   • On-call burden: $2K/month                                       │   │
│   │   • Infrastructure setup/maintenance: $4K/month                     │   │
│   │   • Monitoring/alerting: $300/month                                 │   │
│   │                                                                     │   │
│   │   Storage: $5,000/month (33%)                                       │   │
│   │   • Primary data: 2TB × $0.10/GB = $200/month                       │   │
│   │   • Indexes: 1TB × $0.10/GB = $100/month                            │   │
│   │   • Replication (RF=3): 3TB × 3 × $0.10/GB = $900/month             │   │
│   │   • Backups: 3TB × $0.05/GB = $150/month                            │   │
│   │   • Archive: 5TB × $0.01/GB = $50/month                             │   │
│   │   • Total storage: ~$1,300/month (but scales to $5K with growth)    │   │
│   │                                                                     │   │
│   │   Compute: $2,000/month (13%)                                       │   │
│   │   • Primary: 1 instance × $1K/month                                 │   │
│   │   • Replicas: 2 instances × $500/month = $1K/month                  │   │
│   │                                                                     │   │
│   │   Total: $15,000/month                                              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   L6 Cost Optimization Strategy:                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   1. Reduce operational overhead (biggest win)                      │   │
│   │      • Use managed services (RDS, DynamoDB)                         │   │
│   │      • Automate common tasks (migrations, backups)                  │   │
│   │      • Standardize on one database (reduce expertise needed)        │   │
│   │                                                                     │   │
│   │   2. Optimize storage (scales fastest)                              │   │
│   │      • Archive old data (move to S3/Glacier)                        │   │
│   │      • Optimize indexes (remove unused, partial indexes)            │   │
│   │      • Compress data (PostgreSQL compression, columnar formats)     │   │
│   │                                                                     │   │
│   │   3. Right-size compute (smallest impact, but easy)                 │   │
│   │      • Use reserved instances (30-40% discount)                     │   │
│   │      • Scale down non-critical replicas                             │   │
│   │      • Use spot instances for batch workloads                       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Staff Engineer insight**: Cost per user increases with scale because:
1. **Storage overhead** (indexes, replication) grows faster than data
2. **Operational complexity** requires more specialized expertise
3. **Infrastructure needs** (multi-region, specialized hardware) don't scale linearly

The solution: Plan for cost per user to increase 2-3× as you scale 10×. Budget accordingly, and optimize operational overhead first (it's the biggest cost driver).

### Sustainability: Environmental Cost of Data at Scale

**Why this matters at L6**: At Google-scale, data centers consume significant energy. Database choices affect power consumption: more replicas, more storage, more compute. Staff Engineers in organizations with sustainability commitments consider environmental cost alongside financial cost.

**What drives database energy consumption**:
- **Replication factor**: RF=3 uses ~3× storage and compute vs RF=1
- **Idle capacity**: Over-provisioned clusters run 24/7 even during low traffic
- **Storage tier**: Hot storage (SSD) vs cold (object storage) has different energy profiles
- **Query efficiency**: Inefficient queries waste CPU; indexed queries finish faster

**Concrete example**: A 100TB Cassandra cluster with RF=3 stores 300TB across nodes. Moving cold data (80% of data, rarely accessed) to object storage with lifecycle policies reduces active cluster size. Result: 40% less compute, lower energy cost, same user experience for hot data.

**Trade-offs**: Sustainability optimizations can conflict with latency (cold storage is slower) or availability (fewer replicas). Staff Engineers balance these—archive old data, right-size replicas, optimize queries—without compromising core requirements.

**L6 one-liner**: "Every byte you store and every query you run has a carbon cost. Design for efficiency; it's good for cost and for the planet."

**Staff vs Senior contrast**: An L5 engineer optimizes for cost and performance; sustainability is rarely considered. An L6 engineer asks: "What does our data footprint cost the organization in energy and carbon?" and incorporates that into capacity planning and architecture reviews. At scale, this thinking prevents runaway consumption and aligns technical decisions with organizational sustainability commitments.

### What Staff Engineers Intentionally DON'T Build

Staff Engineers avoid over-engineering by explicitly choosing what NOT to build:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    WHAT L6 ENGINEERS INTENTIONALLY DON'T BUILD              │
│                                                                             │
│   Don't Build: Multi-Region from Day One                                    │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   Why: Multi-region adds 3-5× complexity and cost                   │   │
│   │   • Data replication across regions (latency, consistency)          │   │
│   │   • Conflict resolution (which region wins?)                        │   │
│   │   • Failover complexity (automatic vs manual)                       │   │
│   │   • 3× storage cost (data in 3 regions)                             │   │
│   │                                                                     │   │
│   │   When to build:                                                    │   │
│   │   • Regulatory requirement (data must be in-region)                 │   │
│   │   • Latency requirement (<50ms globally)                            │   │
│   │   • Scale requirement (single region can't handle load)             │   │
│   │                                                                     │   │
│   │   L6 Approach: Start single-region. Add multi-region when           │   │
│   │                requirements demand it, not "just in case."          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Don't Build: Sharding Before You Need It                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   Why: Sharding adds operational complexity and limits flexibility  │   │
│   │   • Cross-shard queries become impossible                           │   │
│   │   • Rebalancing is painful (days/weeks)                             │   │
│   │   • Application must know shard routing                             │   │
│   │   • More failure modes (what if one shard fails?)                   │   │
│   │                                                                     │   │
│   │   When to build:                                                    │   │
│   │   • Single-node limits hit (10-50K writes/sec)                      │   │
│   │   • Data size exceeds single-node capacity (10-50TB)                │   │
│   │   • Vertical scaling is cost-prohibitive                            │   │
│   │                                                                     │   │
│   │   L6 Approach: Use read replicas, caching, partitioning first.      │   │
│   │                Shard only when you've exhausted simpler options.    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Don't Build: Custom Database Solutions                                    │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   Why: Building databases is hard, maintaining them is harder       │   │
│   │   • Query optimization is decades of research                       │   │
│   │   • Failure modes are subtle and hard to debug                      │   │
│   │   • Operational burden is enormous                                  │   │
│   │   • Team expertise is rare                                          │   │
│   │                                                                     │   │
│   │   When to build:                                                    │   │
│   │   • No existing solution fits (extremely rare)                      │   │
│   │   • You have database experts on staff                              │   │
│   │   • You can commit to long-term maintenance                         │   │
│   │                                                                     │   │
│   │   L6 Approach: Use existing databases. Customize at application     │   │
│   │                layer, not database layer.                           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Don't Build: Perfect Consistency Everywhere                               │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   Why: Strong consistency is expensive and often unnecessary        │   │
│   │   • Cross-region consistency adds latency (100-300ms)               │   │
│   │   • Distributed transactions are slow (10-100ms)                    │   │
│   │   • Availability suffers (can't write if quorum unavailable)        │   │
│   │                                                                     │   │
│   │   When to build:                                                    │   │
│   │   • Financial transactions (money must be consistent)               │   │
│   │   • Critical state changes (account deletion)                       │   │
│   │   • Regulatory requirements                                         │   │
│   │                                                                     │   │
│   │   L6 Approach: Use eventual consistency for most data. Strong       │   │
│   │                consistency only where business requires it.         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Staff Engineer Principle: "Perfect is the enemy of good." Build what      │
│                             you need today. Evolve as requirements change.  │
│                             Over-engineering costs more than under-         │
│                             engineering.                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Part 10: L6-Critical Operational Topics

These topics are often overlooked in system design interviews but separate Staff Engineers from Senior Engineers. They demonstrate operational maturity and organizational thinking.

## Observability & Monitoring Strategy

**Why this matters at L6**: A Senior Engineer monitors what's already set up. A Staff Engineer defines what should be monitored and why.

### Database Monitoring Philosophy

Don't monitor everything—monitor what matters for decision-making:

**1. Capacity Indicators** (Are we running out of headroom?)
- CPU utilization (warning: 60%, critical: 80%)
- Memory usage (warning: 70%, critical: 85%)
- Disk space (warning: 60%, critical: 80%)
- Connection pool utilization (warning: 60%, critical: 80%)

**2. Performance Indicators** (Is user experience degrading?)
- Query latency p50, p95, p99 (not just average!)
- Replication lag (warning: 10s, critical: 60s)
- Lock wait time
- Slow query count

**3. Error Indicators** (Is something broken?)
- Connection errors
- Query failures
- Deadlock frequency
- OOM kills

**4. Business-Correlated Metrics** (What does this mean for users?)
- Login success rate (correlate with auth DB health)
- Checkout completion rate (correlate with transaction DB)
- Search result time (correlate with ES cluster health)

### Alerting Strategy

**L5 mistake**: Alert on every metric, get paged constantly, develop alert fatigue.
**L6 approach**: Alert on actionable conditions only.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ALERTING PHILOSOPHY                                      │
│                                                                             │
│   Only alert if ALL of these are true:                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  1. Someone needs to take action                                    │   │
│   │  2. That action cannot wait until business hours                    │   │
│   │  3. A human judgment is required (not automatable)                  │   │
│   │  4. There's a runbook for what to do                                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Otherwise:                                                                │
│   • Log for investigation                                                   │
│   • Create a ticket for review                                              │
│   • Add to daily/weekly report                                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Distributed Tracing for Database Debugging

**Why this matters at L6**: Latency issues often span multiple services and databases. A request might touch Redis, PostgreSQL, and a search index. Without tracing, you cannot distinguish "database slow" from "network slow" from "application slow." Staff Engineers instrument database calls in trace spans to answer: *where* did the 200ms go?

**What to trace**:
- Database connection acquisition time (pool wait)
- Query execution time (per query in a request)
- Transaction duration (begin to commit)
- Cross-database request flow (which DB contributed what latency)

**Concrete example**: A feed load takes 450ms p99. Metrics show PostgreSQL p99 at 80ms and Redis at 5ms. Without tracing, the remaining 365ms is a mystery. With traces: 200ms in connection pool wait (exhausted), 80ms in PostgreSQL, 50ms in cache lookups, 120ms in serialization. Root cause: connection pool too small, not database speed.

**Trade-offs**: Tracing adds overhead (~1–5% latency). Sample rather than trace everything. Use trace IDs to correlate logs and metrics. Staff Engineers argue for tracing when debugging cross-service latency—the cost of one incident outweighs the overhead.

**L6 one-liner**: "If you can't trace a request from API to database and back, you're guessing when latency spikes."

**Staff vs Senior contrast**: An L5 engineer checks individual service logs and database metrics when latency spikes. A Staff Engineer instruments the full request path so that a single trace shows where time was spent across all hops—and advocates for tracing as a prerequisite for debugging distributed systems, not an afterthought.

### Sample Runbook: PostgreSQL Primary Unresponsive

```markdown
## Trigger
PostgreSQL primary not responding to health checks for >30 seconds

## Immediate Actions (First 5 minutes)
1. Check if it's a false alarm: Can you connect manually? `psql -h primary -U app`
2. Check cloud provider status page for region outage
3. Check if primary is up but overloaded: SSH and run `top`, check connections

## If Primary is Down
1. Page secondary on-call if not already engaged
2. Initiate failover to replica: [link to failover runbook]
3. Notify stakeholders: #incidents channel, PagerDuty

## If Primary is Overloaded
1. Identify runaway queries: `SELECT * FROM pg_stat_activity WHERE state != 'idle'`
2. Kill problematic queries if identified
3. Check recent deployments for correlation
4. Consider read replica promotion if CPU > 95%

## Post-Incident
1. Create incident report
2. Update this runbook with learnings
```

### When the Pager Goes Off: Operational Burden at L6

**Why this matters at L6**: Staff Engineers own the operational burden of their decisions. A database choice that "scales" but requires 3 AM pages every month is a bad choice. The cost of on-call is not just engineer time—it's burnout, context switching, and slowed feature delivery.

**What actually happens on-call**:
- **Detection lag**: Metrics may show "elevated latency" for 5–10 minutes before someone notices. Is it a real problem or a blip?
- **Blame game**: "Is it the database or the app?" Without tracing, engineers guess. With traces, they know.
- **Recovery pressure**: "Fix it now" leads to hasty fixes. Rollback? Restart? Scale up? Each has different risk.
- **Post-incident fatigue**: The 2 AM page bleeds into the next day. Documentation and runbook updates often slip.

**Staff-level trade-off**: A managed database adds cost but reduces on-call burden. A self-hosted database saves money but requires DBA expertise and incident readiness. For small teams, managed often wins on total cost (including sanity). For large teams with dedicated ops, self-hosted can be justified.

**L6 one-liner**: "Every database you add is another system to operate at 2 AM. Choose databases that your team can debug when it breaks."

---

## Security & Compliance for Databases

**Why this matters at L6**: Staff Engineers own security posture for their systems. "The security team handles that" is not an L6 answer.

### Encryption

**At rest**: All production databases must encrypt data at disk level.
- PostgreSQL: Use full-disk encryption (LUKS, AWS EBS encryption)
- MongoDB: Enable encryption at rest with WiredTiger
- Redis: Enterprise has encryption; open-source requires TLS + disk encryption

**In transit**: All database connections must use TLS.
- PostgreSQL: `sslmode=require` in connection strings
- Redis: TLS tunneling or Redis 6+ native TLS
- Internal networks are NOT an excuse to skip encryption

### Access Control Patterns

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DATABASE ACCESS CONTROL                                  │
│                                                                             │
│   Principle of Least Privilege:                                             │
│                                                                             │
│   Application accounts:                                                     │
│   • Separate accounts per service (user-service, order-service)             │
│   • Read-only accounts for reporting/analytics                              │
│   • No DDL privileges for application accounts                              │
│                                                                             │
│   Human access:                                                             │
│   • No direct production access by default                                  │
│   • Break-glass procedure for emergencies (audited)                         │
│   • Separate read-only vs read-write roles                                  │
│   • Time-limited access grants                                              │
│                                                                             │
│   Secrets management:                                                       │
│   • Database credentials in secrets manager (Vault, AWS Secrets Manager)    │
│   • Rotation policy (90 days minimum)                                       │
│   • Never in code, config files, or environment variables in plaintext      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### PII and Compliance Considerations

**GDPR requirements affecting database design**:
- Right to be forgotten → Need ability to delete user data across all databases
- Data portability → Need ability to export user data in portable format
- Data minimization → Don't store what you don't need

**Implementation pattern**:
```sql
-- Soft delete with anonymization
UPDATE users SET
  email = CONCAT('deleted_', id, '@anonymized.invalid'),
  name = 'Deleted User',
  phone = NULL,
  deleted_at = NOW()
WHERE id = ?;

-- Don't actually DELETE - you lose audit trail
-- Keep anonymized record for referential integrity
```

### Trust Boundaries and Data Sensitivity

**Why this matters at L6**: Staff Engineers define where trust boundaries lie and how data sensitivity affects database design. A single misclassification can cause compliance violations or unnecessary complexity.

**Data sensitivity classification** (from least to most sensitive):
- **Public**: No restrictions (product catalog, marketing content)
- **Internal**: Company-only (analytics, logs, feature flags)
- **Confidential**: Business-critical (pricing, strategy)
- **Restricted**: Regulated (PII, financial, health)
- **Prohibited**: Never store (passwords plaintext, full credit card numbers)

**Trust boundary implications**:
- Restricted data must never share a database instance with public data
- Cross-boundary queries (e.g., search indexing PII) require explicit pipelines with audit logging
- Backup and replication paths must respect jurisdictional requirements (GDPR, data residency)

**Staff-level trade-off**: Over-classifying everything as Restricted adds cost (encryption, audit, isolation) without benefit. Under-classifying creates compliance risk. Classify based on actual regulatory and business requirements, not paranoia.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    TRUST BOUNDARIES AND DATABASE PLACEMENT                   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Trust Boundary 1: PUBLIC (no PII)                                  │   │
│   │  • Product catalog, marketing content, open APIs                     │   │
│   │  • DB: Shared PostgreSQL, Elasticsearch, CDN                         │   │
│   │  • Isolation: Optional (separate schema if shared)                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Trust Boundary 2: INTERNAL (company-only)                            │   │
│   │  • Analytics, logs, feature flags                                   │   │
│   │  • DB: Shared PostgreSQL, data warehouse                             │   │
│   │  • Isolation: Row-level or schema-level, no cross-region for PII     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Trust Boundary 3: RESTRICTED (PII, financial, health)                │   │
│   │  • User accounts, payments, health records                           │   │
│   │  • DB: DEDICATED instance or schema                                  │   │
│   │  • Isolation: NEVER share with public data. Encryption, audit.       │   │
│   │  • Cross-boundary: Explicit pipelines only (e.g., search index       │   │
│   │    of PII requires audit, access control, data residency)             │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Staff Insight: Crossing a trust boundary (e.g., indexing PII in search)   │
│                  must be intentional, documented, and audited.              │
│                  Do not replicate Restricted data across boundaries without   │
│                  explicit compliance approval.                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Cross-Region Compliance

When data spans regions, database placement drives compliance:
- **Data residency**: Some regulations require data stored in-country (EU, China)
- **Replication**: Async replica in another region may violate residency rules
- **Backup location**: Backup destination matters for compliance

**L6 decision**: Document data classification and residency requirements before choosing multi-region database topology. A design that replicates EU user data to a US region may be illegal regardless of technical elegance.

---

## Backup & Disaster Recovery

**Why this matters at L6**: When disaster strikes, it's too late to design your recovery strategy.

### RTO and RPO Trade-offs

**RPO (Recovery Point Objective)**: How much data can you afford to lose?
**RTO (Recovery Time Objective)**: How long can you be down?

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    RPO/RTO TRADE-OFFS                                       │
│                                                                             │
│   Strategy              RPO            RTO           Cost                   │
│   ─────────────────────────────────────────────────────────────────────     │
│   Daily backups         24 hours       4-8 hours     Low                    │
│   Hourly backups        1 hour         1-2 hours     Medium                 │
│   Sync replication      ~0 seconds     5-30 minutes  High                   │
│   Multi-region active   ~0 seconds     1-5 minutes   Very high              │
│                                                                             │
│   What to choose:                                                           │
│   • Payment system: Sync replication, RTO <30 min, RPO ~0                   │
│   • User profiles: Hourly backups, RTO 2 hours, RPO 1 hour acceptable       │
│   • Analytics data: Daily backups, can reconstruct from source              │
│   • Logs: No backup needed, regeneratable from retained sources             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Backup Validation

**A backup you haven't tested is not a backup.**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    BACKUP VALIDATION CHECKLIST                              │
│                                                                             │
│   Weekly:                                                                   │
│   ☐ Verify backup job completed without errors                              │
│   ☐ Check backup size is reasonable (not 0 bytes, not wildly different)     │
│                                                                             │
│   Monthly:                                                                  │
│   ☐ Restore backup to test environment                                      │
│   ☐ Run validation queries (row counts, checksums)                          │
│   ☐ Verify application can connect and query                                │
│                                                                             │
│   Quarterly:                                                                │
│   ☐ Full disaster recovery drill                                            │
│   ☐ Restore from scratch, measure actual RTO                                │
│   ☐ Document gaps and update procedures                                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Testing Database Changes

**Why this matters at L6**: Staff Engineers don't hope deployments work—they prove they will.

### Load Testing Databases

Before any significant change, validate under realistic load:

```python
# Example: Load testing a new index
# 1. Capture production query patterns
# 2. Replay at 2x production rate
# 3. Measure latency impact of new index

from locust import HttpUser, task, between

class DatabaseLoadTest(HttpUser):
    wait_time = between(0.1, 0.5)
    
    @task(10)  # Weight: 10 (most common)
    def read_user_by_id(self):
        user_id = random.randint(1, 1000000)
        self.client.get(f"/users/{user_id}")
    
    @task(5)   # Weight: 5
    def read_user_by_email(self):
        email = f"user{random.randint(1, 1000000)}@example.com"
        self.client.get(f"/users?email={email}")
    
    @task(1)   # Weight: 1 (less common)
    def create_user(self):
        self.client.post("/users", json={...})
```

### Chaos Engineering for Databases

Proactively break things to find weaknesses:

**Database failure scenarios to test**:
1. Kill primary node → Does failover work? How long?
2. Saturate connections → Does app gracefully degrade?
3. Inject network latency → Does timeout budget work?
4. Fill disk → Does alerting catch it? Does app handle errors?
5. Kill cache → Does thundering herd protection work?

**Tool**: Netflix's Chaos Monkey, Gremlin, or simple scripts:
```bash
# Simulate network latency to database
sudo tc qdisc add dev eth0 root netem delay 100ms

# Watch application behavior
curl -w "@curl-format.txt" http://localhost:8080/health

# Cleanup
sudo tc qdisc del dev eth0 root
```

---

## Rollback Strategies for Database Changes

**Why this matters at L6**: Every change must be reversible. "We can't roll back" is never acceptable.

### Schema Change Rollback

**Forward-only migrations (dangerous)**:
```sql
-- Migration: Add NOT NULL column
ALTER TABLE users ADD COLUMN phone VARCHAR(20) NOT NULL;

-- Rollback: IMPOSSIBLE without data loss
-- The column has data now, can't recreate old state
```

**Reversible migrations (L6 approach)**:
```sql
-- Forward migration
ALTER TABLE users ADD COLUMN phone VARCHAR(20); -- Nullable first
-- Application deploys, starts writing phone
-- Backfill existing users
-- Later: ALTER TABLE users ALTER COLUMN phone SET NOT NULL;

-- Rollback: Simply don't use the column
-- Old code ignores it, new code is optional
-- Clean up column later if migration abandoned
```

### Data Migration Rollback

For migrations between databases:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    REVERSIBLE MIGRATION PATTERN                             │
│                                                                             │
│   Phase 1: Dual Write                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Write to BOTH old and new database                               │   │
│   │  • Read from OLD database                                           │   │
│   │  • Rollback: Just stop writing to new                               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Phase 2: Shadow Read                                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Write to BOTH                                                    │   │
│   │  • Read from BOTH, compare results, use OLD                         │   │
│   │  • Log any discrepancies                                            │   │
│   │  • Rollback: Just stop shadow reading                               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Phase 3: Flip Read                                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Write to BOTH                                                    │   │
│   │  • Read from NEW                                                    │   │
│   │  • Rollback: Feature flag back to old                               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Phase 4: Decommission Old                                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Stop writing to old                                              │   │
│   │  • Keep old database in read-only for 30 days                       │   │
│   │  • Then delete                                                      │   │
│   │  • Rollback: At this point, you're committed                        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Cross-Team Database Decisions

**Why this matters at L6**: L6 impact extends beyond your team. You influence organizational direction.

### Building Consensus on Database Choices

When multiple teams share a database decision:

**1. Start with requirements, not technology**
```
WRONG: "I think we should use Cassandra for the new platform"
RIGHT: "Our access patterns require X, Y, Z. Let's evaluate options against those."
```

**2. Create evaluation criteria collaboratively**
- Involve all stakeholders in defining what matters
- Weight criteria based on actual priorities
- Document the decision framework

**3. Present trade-offs, not recommendations**
```
WRONG: "We should use PostgreSQL"
RIGHT: "Here are three options. PostgreSQL gives us X but costs us Y. 
        Cassandra gives us Z but costs us W. Given our priorities, I 
        recommend PostgreSQL, but I want to hear concerns."
```

**4. Document decisions for posterity**
- Write ADRs (Architecture Decision Records)
- Include what was decided, why, and what was rejected
- Future engineers will thank you

### Creating Database Standards

At L6, you might be asked to set organizational standards:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DATABASE STANDARDS TEMPLATE                              │
│                                                                             │
│   Approved Databases:                                                       │
│   • PostgreSQL: Default for transactional data                              │
│   • Redis: Caching, session storage, rate limiting                          │
│   • Elasticsearch: Search (never as primary store)                          │
│   • Cassandra: High-write time-series (requires review)                     │
│                                                                             │
│   To Use a Non-Standard Database:                                           │
│   1. Document why approved options don't work                               │
│   2. Get architecture review approval                                       │
│   3. Commit to operational ownership (your team's on-call)                  │
│   4. Provide migration path if it doesn't work out                          │
│                                                                             │
│   Why We Have Standards:                                                    │
│   • Shared expertise (everyone can help debug PostgreSQL)                   │
│   • Operational efficiency (one set of runbooks, monitoring)                │
│   • Hiring (PostgreSQL skills are common)                                   │
│   • Flexibility != chaos                                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Human Failure Modes: The Operational Reality

Staff Engineers design systems accounting for human error because it's the most common cause of incidents. Database systems are particularly vulnerable to human mistakes:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    HUMAN FAILURE MODES IN DATABASE OPERATIONS               │
│                                                                             │
│   Failure Mode 1: Misconfiguration During Setup                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   What happens:                                                     │   │
│   │   • Engineer sets up database with wrong configuration              │   │
│   │   • Example: PostgreSQL max_connections = 100 (too low)             │   │
│   │   • Example: Redis eviction policy = noeviction (memory fills up)   │   │
│   │   • Example: Cassandra replication factor = 1 (no redundancy)       │   │
│   │                                                                     │   │
│   │   Why it happens:                                                   │   │
│   │   • Copy-paste from documentation (wrong defaults)                  │   │
│   │   • Testing on small dataset (works fine, breaks at scale)          │   │
│   │   • Assumptions about requirements (didn't ask)                     │   │
│   │                                                                     │   │
│   │   Impact:                                                           │   │
│   │   • System works initially, fails under load                        │   │
│   │   • Hard to detect (works in staging, breaks in production)         │   │
│   │   • Recovery requires downtime (change config, restart)             │   │
│   │                                                                     │   │
│   │   L6 Prevention:                                                    │   │
│   │   • Infrastructure as Code (IaC) with peer review                   │   │
│   │   • Configuration validation (fail fast on bad config)              │   │
│   │   • Load testing in staging (catch config issues early)             │   │
│   │   • Runbooks with explicit configuration checks                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Failure Mode 2: Schema Migration Mistakes                                 │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   What happens:                                                     │   │
│   │   • Engineer runs migration that locks table for hours              │   │
│   │   • Example: ALTER TABLE ADD COLUMN with DEFAULT (rewrites table)   │   │
│   │   • Example: CREATE INDEX without CONCURRENTLY (locks writes)       │   │
│   │   • Example: DROP COLUMN on large table (takes hours)               │   │
│   │                                                                     │   │
│   │   Why it happens:                                                   │   │
│   │   • Migration works on small test dataset (100 rows)                │   │
│   │   • Assumes production is same size (it's not, 100M rows)           │   │
│   │   • Doesn't understand locking behavior                             │   │
│   │   • No rollback plan (can't undo once started)                      │   │
│   │                                                                     │   │
│   │   Impact:                                                           │   │
│   │   • Production outage (writes blocked for hours)                    │   │
│   │   • Can't rollback (migration partially applied)                    │   │
│   │   • Requires manual intervention (kill migration, restore backup)   │   │
│   │                                                                     │   │
│   │   L6 Prevention:                                                    │   │
│   │   • Test migrations on production-size data in staging              │   │
│   │   • Use safe migration patterns (ADD COLUMN nullable, backfill)     │   │
│   │   • Migration review process (Staff Engineer approval)              │   │
│   │   • Rollback plan documented before migration                       │   │
│   │   • Gradual rollout (migrate 10% of data, verify, then 100%)        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Failure Mode 3: Operational Runbook Errors                                │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   What happens:                                                     │   │
│   │   • On-call engineer follows runbook incorrectly                    │   │
│   │   • Example: Promotes wrong replica (async, data loss)              │   │
│   │   • Example: Kills wrong process (kills primary instead of replica) │   │
│   │   • Example: Runs command on wrong environment (prod vs staging)    │   │
│   │                                                                     │   │
│   │   Why it happens:                                                   │   │
│   │   • Runbook is unclear or outdated                                  │   │
│   │   • Stress during incident (2 AM, pressure to fix quickly)          │   │
│   │   • Copy-paste error (wrong hostname, wrong command)                │   │
│   │   • Assumptions (didn't verify before executing)                    │   │
│   │                                                                     │   │
│   │   Impact:                                                           │   │
│   │   • Makes incident worse (extends outage)                           │   │
│   │   • Data loss (wrong replica promotion)                             │   │
│   │   • Requires recovery (restore from backup, re-sync replicas)       │   │
│   │                                                                     │   │
│   │   L6 Prevention:                                                    │   │
│   │   • Clear, step-by-step runbooks with verification steps            │   │
│   │   • Confirmation prompts ("Are you sure? Type 'yes' to confirm")    │   │
│   │   • Automation for common operations (reduce human error)           │   │
│   │   • Runbook testing (practice incidents in staging)                 │   │
│   │   • Two-person verification for critical operations                 │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Failure Mode 4: Cross-Team Communication Breakdown                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   What happens:                                                     │   │
│   │   • Team A changes database schema without telling Team B           │   │
│   │   • Example: Adds NOT NULL column (breaks Team B's writes)          │   │
│   │   • Example: Drops column (breaks Team B's reads)                   │   │
│   │   • Example: Changes index (breaks Team B's query performance)      │   │
│   │                                                                     │   │
│   │   Why it happens:                                                   │   │
│   │   • Teams don't communicate (assume they own the database)          │   │
│   │   • No change notification process                                  │   │
│   │   • Shared database, but no shared ownership                        │   │
│   │   • Assumptions about who uses what                                 │   │
│   │                                                                     │   │
│   │   Impact:                                                           │   │
│   │   • Team B's service breaks (unexpected errors)                     │   │
│   │   • Blame game (Team A: "Why are you using our database?")          │   │
│   │   • Requires rollback or emergency fix (Team B updates code)        │   │
│   │                                                                     │   │
│   │   L6 Prevention:                                                    │   │
│   │   • Database ownership model (who owns what)                        │   │
│   │   • Change notification process (RFC, Slack, email)                 │   │
│   │   • Schema change review (all stakeholders notified)                │   │
│   │   • Deprecation process (warn before breaking changes)              │   │
│   │   • Database standards (prevent breaking changes)                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Failure Mode 5: Knowledge Gaps                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │   What happens:                                                     │   │
│   │   • Engineer doesn't understand database behavior                   │   │
│   │   • Example: Assumes PostgreSQL handles 1M connections (it doesn't) │   │
│   │   • Example: Assumes Redis persists by default (it doesn't)         │   │
│   │   • Example: Assumes Cassandra handles cross-partition queries      │   │
│   │                efficiently (it doesn't)                             │   │
│   │                                                                     │   │
│   │   Why it happens:                                                   │   │
│   │   • New to the database (recently adopted)                          │   │
│   │   • Assumptions based on other databases                            │   │
│   │   • Documentation is unclear or incomplete                          │   │
│   │   • No training or mentorship                                       │   │
│   │                                                                     │   │
│   │   Impact:                                                           │   │
│   │   • System designed incorrectly (doesn't work at scale)             │   │
│   │   • Requires redesign (expensive, time-consuming)                   │   │
│   │   • Production incidents (unexpected behavior)                      │   │
│   │                                                                     │   │
│   │   L6 Prevention:                                                    │   │
│   │   • Database standards (limit choices, build expertise)             │   │
│   │   • Training and documentation (internal wiki, runbooks)            │   │
│   │   • Architecture review (Staff Engineer catches mistakes)           │   │
│   │   • Mentorship (pair junior with senior on database work)           │   │
│   │   • Start simple (PostgreSQL before Cassandra)                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   Staff Engineer Insight: Human error is the #1 cause of incidents.         │
│                          Design systems to be forgiving of mistakes.        │
│                          Use automation, validation, and clear processes    │
│                          to reduce human error surface area.                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Operational Realities: What Actually Happens

Staff Engineers understand the gap between ideal design and operational reality:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    OPERATIONAL REALITY VS IDEAL DESIGN                      │
│                                                                             │
│   Ideal: "We'll use the right database for each use case"                   │
│   Reality: "We use PostgreSQL for everything because that's what the team   │
│            knows. When it breaks, we can debug it."                         │
│                                                                             │
│   Why:                                                                      │
│   • Team expertise matters more than perfect fit                            │
│   • Operational familiarity reduces incident time                           │
│   • Debugging unknown databases takes hours (not minutes)                   │
│   • Hiring is easier (PostgreSQL skills are common)                         │
│                                                                             │
│   L6 Approach: Standardize on 2-3 databases max. Accept suboptimal          │
│                fit for operational simplicity.                              │
│                                                                             │
│   ────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│   Ideal: "We'll migrate to the better database when we need it"             │
│   Reality: "We're stuck with this database forever because migration is     │
│            too risky and expensive."                                        │
│                                                                             │
│   Why:                                                                      │
│   • Migrations take months (not weeks)                                      │
│   • Risk of data loss or downtime                                           │
│   • Application changes required (expensive)                                │
│   • No business value (just technical debt)                                 │
│                                                                             │
│   L6 Approach: Choose database for 3-year horizon. Migration is last        │
│                resort, not evolution strategy.                              │
│                                                                             │
│   ────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│   Ideal: "We'll optimize queries and indexes proactively"                   │
│   Reality: "We optimize when pager goes off at 2 AM."                       │
│                                                                             │
│   Why:                                                                      │
│   • Proactive optimization has no immediate business value                  │
│   • Incidents create urgency (and budget)                                   │
│   • Hard to justify time for "prevention"                                   │
│   • Monitoring catches problems eventually                                  │
│                                                                             │
│   L6 Approach: Set up monitoring and alerting. Optimize reactively,         │
│                but with good tooling (fast to fix).                         │
│                                                                             │
│   ────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│   Ideal: "We'll test all failure scenarios"                                 │
│   Reality: "We test happy path. Failures are discovered in production."     │
│                                                                             │
│   Why:                                                                      │
│   • Chaos engineering is expensive (time, infrastructure)                   │
│   • Hard to simulate all failure modes                                      │
│   • Production failures are "real" tests (unfortunately)                    │
│                                                                             │
│   L6 Approach: Test critical failure modes (primary down, network           │
│                partition). Accept that edge cases will be discovered        │
│                in production. Have good monitoring and runbooks.            │
│                                                                             │
│   ────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│   Ideal: "We'll document everything"                                        │
│   Reality: "Documentation is outdated. We ask the person who built it."     │
│                                                                             │
│   Why:                                                                      │
│   • Documentation maintenance is thankless work                             │
│   • Code changes faster than docs                                           │
│   • People are faster to ask than to read                                   │
│                                                                             │
│   L6 Approach: Document critical decisions (ADRs). Keep runbooks updated.   │
│                Accept that some knowledge is tribal (person-to-person).     │
│                                                                             │
│   Staff Engineer Principle: Design for operational reality, not ideal       │
│                             conditions. Systems that work in practice       │
│                             beat systems that work in theory.               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# Brainstorming Questions

Use these questions to deepen your understanding and prepare for interview discussions:

## Database Selection

1. **You're building a user authentication service that must handle 10K logins/second. The team suggests MongoDB because "user profiles are documents." How do you respond?**

2. **Your rate limiting service is currently using PostgreSQL. It's working, but latency is 50ms and you need it under 5ms. What's your migration strategy?**

3. **A junior engineer proposes using Cassandra for a shopping cart because "it scales." What questions do you ask before agreeing or disagreeing?**

4. **You're designing a system that needs both strong consistency for payments and high write throughput for activity logging. How do you architect the data layer?**

5. **The team wants to use DynamoDB for everything because it's "managed and scalable." What trade-offs would you highlight?**

## Failure Scenarios

6. **Your primary PostgreSQL instance fails at 2 AM. You have async replicas but no automatic failover. What's your runbook?**

7. **Redis cluster is experiencing a network partition. Half your rate limiting is failing. What's your immediate response, and what's your long-term fix?**

8. **Your Cassandra cluster shows increasing read latency. Compaction is falling behind. What do you investigate, and what are potential solutions?**

9. **A schema migration adds a NOT NULL column with DEFAULT to a 500M row table. Production goes down. What happened, and how do you recover?**

## Evolution & Migration

10. **You inherited a monolithic PostgreSQL database with 50 tables. Product wants to split into microservices. How do you approach database decomposition?**

11. **Your single-region system needs to go multi-region. What database changes are required, and what trade-offs do you face?**

12. **You're migrating from MongoDB to PostgreSQL. How do you handle documents with inconsistent schemas?**

13. **A legacy system stores user data in both PostgreSQL and Redis, with no clear source of truth. How do you resolve this?**

## Trade-offs

14. **Strong consistency vs. availability: For a notification system, which do you choose and why?**

15. **Managed service (DynamoDB) vs. self-hosted (Cassandra): What factors drive your decision for a startup vs. an enterprise?**

16. **Single powerful database vs. multiple specialized databases: When does each approach win?**

17. **Your organization has PostgreSQL expertise but the problem seems ideal for Cassandra. How do you weigh team skills vs. technical fit?**

---

# Homework Assignment

## Part A: Analysis Exercise

Take a system you've built or worked on and answer:

1. **What databases does it use?** List each database and its purpose.

2. **Why were these choices made?** Were they conscious decisions or defaults?

3. **What access patterns exist?** Categorize by read/write ratio and query type.

4. **What would break at 10x scale?** Identify the first bottleneck.

5. **What would you change today?** With hindsight, what would you do differently?

## Part B: Redesign Challenge

**Scenario**: You have a social media feed system currently using:
- PostgreSQL for all data (users, posts, follows, feeds)
- Single region deployment
- 1M users, 100K DAU
- Feed query takes 200ms average

**Requirements**:
- Support 10M users, 2M DAU
- Feed query must be < 50ms p99
- Multi-region (US + Europe)
- Budget is a concern

**Your task**:

1. **Analyze current limitations**: What specifically makes the current design unable to meet new requirements?

2. **Propose new architecture**: What databases would you use? Draw the data flow for:
   - User posts a new item
   - User loads their feed
   - User updates their profile

3. **Justify rejections**: For each database you DON'T choose, explain why not.

4. **Migration plan**: How do you get from current state to new state without downtime?

5. **Failure handling**: What happens when each component fails?

## Part C: Interview Practice

Practice explaining these three scenarios aloud (5 minutes each):

1. **User Profile Service**: Why PostgreSQL over MongoDB? Walk through the decision.

2. **Rate Limiter**: Why Redis? What happens when Redis fails? How do you prevent abuse during failure?

3. **Feed Storage**: Why the hybrid approach? How does fan-out work? What's the celebrity problem solution?

For each, practice:
- Leading with requirements (not technology)
- Explicitly rejecting alternatives
- Discussing failure modes
- Explaining evolution over time

---

# Master Review Prompt Check

Before considering this chapter complete, verify:

- [x] **A. Judgment & decision-making**: Requirements-first framework, explicit rejection of alternatives, trade-off articulation
- [x] **B. Failure & incident thinking**: Partial failures, blast radius, cascading failures, structured incident format (3 incidents: Migration Lockout, Hot Partition Meltdown, Dual-Write Search Drift)
- [x] **C. Scale & time**: Evolution timeline, first-bottleneck analysis, scale-over-years sequence, scaling boundaries by database type
- [x] **D. Cost & sustainability**: TCO framework, cost drivers, scaling cost analysis, environmental sustainability
- [x] **E. Real-world engineering**: Operational complexity, human failure modes, on-call burden ("When the Pager Goes Off"), runbooks
- [x] **F. Learnability & memorability**: Mental models, one-liners, decision trees
- [x] **G. Data, consistency & correctness**: ACID, consistency models, invariants, data integrity verification
- [x] **H. Security & compliance**: Encryption, access control, PII, trust boundaries, data sensitivity
- [x] **I. Observability & debuggability**: Monitoring philosophy, alerting, runbooks, distributed tracing
- [x] **J. Cross-team & org impact**: Database standards, consensus-building, ownership model
- [x] **Exercises & Brainstorming**: Brainstorming questions and homework assignment present

## L6 Dimension Coverage Table (A–J)

| Dimension | Coverage | Key Sections |
|-----------|----------|--------------|
| **A. Judgment & decision-making** | ✓ | L5 vs L6 examples, decision framework, requirements-first, probe questions |
| **B. Failure & incident thinking** | ✓ | Partial failures, blast radius, cascading failures, 3 structured incidents |
| **C. Scale & time** | ✓ | Evolution timeline, first bottleneck, scale-over-years sequence, scaling boundaries |
| **D. Cost & sustainability** | ✓ | TCO analysis, cost drivers, scaling cost, environmental sustainability |
| **E. Real-world engineering** | ✓ | Operational complexity, human failure modes, on-call burden, runbooks |
| **F. Learnability & memorability** | ✓ | Mental models, one-liners, decision trees |
| **G. Data, consistency & correctness** | ✓ | ACID, consistency models, invariants (L6 discussion), integrity verification |
| **H. Security & compliance** | ✓ | Encryption, access control, PII, trust boundaries (diagram), data sensitivity |
| **I. Observability & debuggability** | ✓ | Monitoring, alerting, runbooks, distributed tracing |
| **J. Cross-team & org impact** | ✓ | Standards, consensus, ownership, human failure modes |

---

# Key Takeaways

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    STAFF ENGINEER DATABASE PRINCIPLES                       │
│                                                                             │
│   1. ACCESS PATTERNS FIRST                                                  │
│      Start with how data is read and written, not with technology names.    │
│      The question is "what do I need?" not "what's trendy?"                 │
│                                                                             │
│   2. POSTGRESQL IS USUALLY RIGHT                                            │
│      For most applications, PostgreSQL + Redis handles scale fine.          │
│      Don't reach for NoSQL until you have specific problems SQL can't solve.│
│                                                                             │
│   3. COMPLEXITY HAS COST                                                    │
│      Every database you add is another system to operate, monitor, and      │
│      debug. Multiple databases should solve specific problems, not add      │
│      resume keywords.                                                       │
│                                                                             │
│   4. SCHEMA ISN'T OPTIONAL                                                  │
│      Your application has a schema whether the database enforces it or not. │
│      The question is whether bugs get caught in the database or production. │
│                                                                             │
│   5. PLAN FOR FAILURE                                                       │
│      Every database fails. Design for graceful degradation.                 │
│      Fail-open for non-critical paths. Fail-safe for financial/security.    │
│                                                                             │
│   6. EVOLUTION IS INEVITABLE                                                │
│      Today's perfect choice becomes tomorrow's bottleneck.                  │
│      Design for migration. Avoid lock-in. Keep data portable.               │
│                                                                             │
│   7. BORING IS GOOD                                                         │
│      Battle-tested databases have solved problems you don't know exist yet. │
│      Excitement about new databases should be tempered by operational       │
│      reality.                                                               │
│                                                                             │
│   8. BLAST RADIUS MATTERS                                                   │
│      Multiple isolated databases can have smaller blast radius than one.    │
│      Design for containment, not just functionality.                        │
│                                                                             │
│   9. CAPACITY PLANNING IS PROACTIVE                                         │
│      Know your growth rate. Know your thresholds. Plan before crisis.       │
│      The best incident is the one that never happens.                       │
│                                                                             │
│   10. TOTAL COST INCLUDES OPERATIONS                                        │
│       Licensing is the smallest part of database cost.                      │
│       DBA time, on-call burden, incident recovery—count them all.           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Remaining Considerations

While this section is comprehensive, candidates should also:

1. **Practice verbal explanation** — Reading is not the same as explaining. Practice the examples aloud.

2. **Connect to personal experience** — Interviewers value war stories. Map these concepts to systems you've built.

3. **Stay current** — Database technology evolves. Monitor developments in areas relevant to your interviews.

4. **Complement with Volume 3** — Consistency models (Volume 3) and database selection (Volume 4) are deeply connected. Review both.

---